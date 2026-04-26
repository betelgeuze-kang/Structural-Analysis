#!/usr/bin/env python3
"""Run Top-k residual/meta learning benchmark and emit HF KPI contract.

No fallback path is provided. If training/evaluation cannot satisfy KPI gates,
the process exits with non-zero status.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path


SCHEMA_VERSION = "1.2"
RUN_ID = "phase1-hf-benchmark-topk-residual-meta-prod"
EPS = 1e-9

TOPOLOGIES = ["rahmen", "truss", "outrigger", "wall-frame"]
HAZARDS = ["wind", "seismic", "combined"]
METRICS = [
    "drift_ratio_pct",
    "base_shear_kN",
    "mode_shape_mac",
    "buckling_factor",
    "equilibrium_residual",
]
METRIC_WEIGHTS = {
    "drift_ratio_pct": 1.0,
    "base_shear_kN": 1.0,
    "mode_shape_mac": 1.0,
    "buckling_factor": 1.0,
    "equilibrium_residual": 0.5,
}

REASON_CODES = {
    "PASS": "top-k residual/meta benchmark KPI thresholds satisfied",
    "ERR_BENCHMARK_KPI_FAIL": "benchmark KPI thresholds violated",
}


def _require_torch():
    try:
        import torch  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"torch is required for top-k benchmark training: {exc}")
    return torch


def _parse_csv_set(value: str) -> set[str]:
    parts = [x.strip() for x in str(value).split(",")]
    return {x for x in parts if x}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _load_cases(path: Path, require_direct_metrics: bool, accepted_metric_sources: set[str]) -> tuple[list[dict], dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if not isinstance(cases, list) or len(cases) == 0:
        raise SystemExit(f"invalid benchmark case file: {path}")
    source = payload.get("source", {})
    global_metric_source = source.get("metric_source") if isinstance(source, dict) else None

    required = {"case_id", "split", "topology_type", "hazard_type", "residual_norm", "load_scale", "metrics"}
    missing_metric_source_case_ids: list[str] = []
    invalid_metric_source_case_ids: list[str] = []
    for i, case in enumerate(cases):
        if not isinstance(case, dict):
            raise SystemExit(f"case[{i}] must be object")
        missing = [k for k in required if k not in case]
        if missing:
            raise SystemExit(f"case[{i}] missing required keys: {missing}")
        topo = str(case["topology_type"])
        hazard = str(case["hazard_type"])
        if topo not in TOPOLOGIES:
            raise SystemExit(f"case[{i}] invalid topology_type: {topo}")
        if hazard not in HAZARDS:
            raise SystemExit(f"case[{i}] invalid hazard_type: {hazard}")
        metrics = case.get("metrics", {})
        for m in METRICS:
            row = metrics.get(m)
            if not isinstance(row, dict) or "hf" not in row or "lf" not in row:
                raise SystemExit(f"case[{i}] metric '{m}' missing hf/lf")
        case["source_family"] = str(case.get("source_family", "")).strip() or "unknown"

        metric_source = case.get("metric_source", global_metric_source)
        if require_direct_metrics:
            case_id = str(case.get("case_id", f"case-{i}"))
            if not isinstance(metric_source, str) or not metric_source.strip():
                missing_metric_source_case_ids.append(case_id)
            elif metric_source not in accepted_metric_sources:
                invalid_metric_source_case_ids.append(case_id)

    metric_source_validation = {
        "enabled": bool(require_direct_metrics),
        "accepted_metric_sources": sorted(accepted_metric_sources),
        "global_metric_source": global_metric_source,
        "missing_metric_source_case_ids": missing_metric_source_case_ids,
        "invalid_metric_source_case_ids": invalid_metric_source_case_ids,
        "pass": (not require_direct_metrics)
        or (len(missing_metric_source_case_ids) == 0 and len(invalid_metric_source_case_ids) == 0),
    }
    if require_direct_metrics and not metric_source_validation["pass"]:
        raise SystemExit(
            "direct metric source validation failed: "
            f"missing={missing_metric_source_case_ids}, invalid={invalid_metric_source_case_ids}, "
            f"accepted={sorted(accepted_metric_sources)}"
        )
    return cases, metric_source_validation


def _make_param_vector(torch, dim: int):
    return torch.nn.Parameter(torch.zeros(dim, dtype=torch.float32))


def _make_directions(torch, dim: int, branches: int, seed: int):
    g = torch.Generator()
    g.manual_seed(seed)
    raw = torch.randn(branches, dim, generator=g, dtype=torch.float32)
    out = []
    for i in range(branches):
        v = raw[i]
        for q in out:
            v = v - torch.dot(v, q) * q
        n = torch.linalg.vector_norm(v)
        if float(n.item()) <= 1e-8:
            v = torch.zeros(dim, dtype=torch.float32)
            v[i % dim] = 1.0
            n = torch.linalg.vector_norm(v)
        out.append(v / n)
    return torch.stack(out, dim=0)


def _metric_indices() -> dict:
    return {k: i for i, k in enumerate(METRICS)}


def _source_family_order(cases: list[dict]) -> list[str]:
    families = sorted({str(case.get("source_family", "")).strip() or "unknown" for case in cases if isinstance(case, dict)})
    return families or ["unknown"]


def _predict_case(torch, params, case: dict, source_families: list[str]) -> dict:
    # params layout:
    # [0:5] metric_gain
    # [5:10] metric_load_gain
    # [10:14] topo_bias
    # [14:17] hazard_bias
    # [17:] family_metric_bias[family, metric]
    gains = params[0:5]
    load_gains = params[5:10]
    topo_bias = params[10:14]
    hazard_bias = params[14:17]
    family_bias = params[17:].reshape(len(source_families), len(METRICS))

    topo_i = TOPOLOGIES.index(str(case["topology_type"]))
    hazard_i = HAZARDS.index(str(case["hazard_type"]))
    family_i = source_families.index(str(case.get("source_family", "")).strip() or "unknown")
    residual_norm = float(case["residual_norm"])
    load_scale = float(case["load_scale"])

    meta_scale = torch.clamp(1.0 + topo_bias[topo_i] + hazard_bias[hazard_i], min=0.2, max=2.4)
    m_idx = _metric_indices()
    out = {}
    for m in METRICS:
        idx = m_idx[m]
        lf = torch.tensor(float(case["metrics"][m]["lf"]), dtype=torch.float32)
        g = gains[idx]
        lg = load_gains[idx]
        fb = family_bias[family_i, idx]
        if m == "mode_shape_mac":
            pred = lf + g * residual_norm * meta_scale + lg * (load_scale - 1.0) * 0.03 + fb
            pred = torch.clamp(pred, min=0.0, max=1.0)
        elif m == "equilibrium_residual":
            pred = lf * (1.0 - g * residual_norm * meta_scale - lg * (load_scale - 1.0) * 0.08 - fb * 0.2)
            pred = torch.relu(pred)
        else:
            pred = lf * (1.0 - g * residual_norm * meta_scale - lg * (load_scale - 1.0) * 0.08 - fb * 0.2)
        out[m] = pred
    return out


def _case_loss(torch, params, case: dict, source_families: list[str]):
    preds = _predict_case(torch, params, case, source_families)
    loss = torch.tensor(0.0, dtype=torch.float32)
    for m in METRICS:
        hf = torch.tensor(float(case["metrics"][m]["hf"]), dtype=torch.float32)
        pred = preds[m]
        if m in {"mode_shape_mac", "equilibrium_residual"}:
            err = torch.abs(pred - hf)
        else:
            err = torch.abs(pred - hf) / max(abs(float(hf.item())), EPS)
        loss = loss + float(METRIC_WEIGHTS[m]) * err
    return loss


def _split_loss(torch, params, cases: list[dict], source_families: list[str]):
    if not cases:
        return torch.tensor(0.0, dtype=torch.float32)
    losses = [_case_loss(torch, params, c, source_families) for c in cases]
    return torch.stack(losses).mean()


def _softmax(xs: list[float], temperature: float) -> list[float]:
    if not xs:
        return []
    t = max(float(temperature), 1e-6)
    zs = [-(x / t) for x in xs]
    m = max(zs)
    exps = [math.exp(z - m) for z in zs]
    s = sum(exps)
    if s <= EPS:
        return [1.0 / len(xs) for _ in xs]
    return [e / s for e in exps]


def _train_topk(torch, train_cases: list[dict], branches: int, top_k: int, epochs: int, lr: float, epsilon: float, temperature: float, seed: int, source_families: list[str]):
    dim = len(METRICS) * 2 + len(TOPOLOGIES) + len(HAZARDS) + len(source_families) * len(METRICS)
    params = _make_param_vector(torch, dim)
    optimizer = torch.optim.Adam([params], lr=lr)
    history = []

    for ep in range(epochs):
        dirs = _make_directions(torch, dim=dim, branches=branches, seed=seed + ep + 11)

        with torch.no_grad():
            scout = []
            base = params.detach()
            for i in range(branches):
                cand = base + float(epsilon) * dirs[i]
                loss_i = float(_split_loss(torch, cand, train_cases, source_families).item())
                scout.append({"branch_id": i, "loss": loss_i})
            scout_sorted = sorted(scout, key=lambda x: x["loss"])
            k = min(max(2, top_k), len(scout_sorted))
            selected = scout_sorted[:k]
            weights = _softmax([float(x["loss"]) for x in selected], temperature=temperature)

        optimizer.zero_grad()
        weighted_loss = torch.tensor(0.0, dtype=torch.float32)
        for w, s in zip(weights, selected):
            b = int(s["branch_id"])
            cand = params + float(epsilon) * dirs[b]
            weighted_loss = weighted_loss + float(w) * _split_loss(torch, cand, train_cases, source_families)
        reg = 5e-4 * torch.sum(params * params)
        total_loss = weighted_loss + reg
        total_loss.backward()
        optimizer.step()

        history.append(
            {
                "epoch": ep + 1,
                "selected_branch_ids": [int(x["branch_id"]) for x in selected],
                "selected_losses": [float(x["loss"]) for x in selected],
                "normalized_weights": weights,
                "weighted_loss": float(weighted_loss.detach().item()),
                "total_loss": float(total_loss.detach().item()),
            }
        )
    return params.detach(), history


def _rel_err(pred: float, ref: float) -> float:
    return abs(pred - ref) / max(abs(ref), EPS)


def _evaluate_split(torch, params, cases: list[dict], source_families: list[str]) -> dict:
    if not cases:
        return {
            "case_count": 0,
            "drift_error_pct": 0.0,
            "base_shear_error_pct": 0.0,
            "mode_shape_mac": 0.0,
            "buckling_factor_error_pct": 0.0,
            "equilibrium_residual_mean": 0.0,
            "rows": [],
        }

    rows = []
    drift_errs = []
    base_errs = []
    buckling_errs = []
    mac_preds = []
    residual_preds = []

    for case in cases:
        preds = _predict_case(torch, params, case, source_families)
        row = {
            "case_id": case["case_id"],
            "split": case["split"],
            "ood_tag": case.get("ood_tag", "unknown"),
            "topology_type": case["topology_type"],
            "hazard_type": case["hazard_type"],
            "metrics": {},
        }
        for m in METRICS:
            hf = float(case["metrics"][m]["hf"])
            lf = float(case["metrics"][m]["lf"])
            pred = float(preds[m].item())
            row["metrics"][m] = {
                "hf": hf,
                "lf": lf,
                "topk_pred": pred,
            }
            if m == "drift_ratio_pct":
                drift_errs.append(_rel_err(pred, hf) * 100.0)
            elif m == "base_shear_kN":
                base_errs.append(_rel_err(pred, hf) * 100.0)
            elif m == "buckling_factor":
                buckling_errs.append(_rel_err(pred, hf) * 100.0)
            elif m == "mode_shape_mac":
                mac_preds.append(pred)
            elif m == "equilibrium_residual":
                residual_preds.append(pred)
        rows.append(row)

    return {
        "case_count": len(cases),
        "drift_error_pct": sum(drift_errs) / len(drift_errs),
        "base_shear_error_pct": sum(base_errs) / len(base_errs),
        "mode_shape_mac": sum(mac_preds) / len(mac_preds),
        "buckling_factor_error_pct": sum(buckling_errs) / len(buckling_errs),
        "equilibrium_residual_mean": sum(residual_preds) / len(residual_preds),
        "rows": rows,
    }


def _evaluate_baseline(cases: list[dict]) -> dict:
    if not cases:
        return {
            "case_count": 0,
            "drift_error_pct": 0.0,
            "base_shear_error_pct": 0.0,
            "mode_shape_mac": 0.0,
            "buckling_factor_error_pct": 0.0,
            "equilibrium_residual_mean": 0.0,
        }

    drift_errs = []
    base_errs = []
    buckling_errs = []
    mac_vals = []
    residual_vals = []
    for case in cases:
        m = case["metrics"]
        drift_errs.append(_rel_err(float(m["drift_ratio_pct"]["lf"]), float(m["drift_ratio_pct"]["hf"])) * 100.0)
        base_errs.append(_rel_err(float(m["base_shear_kN"]["lf"]), float(m["base_shear_kN"]["hf"])) * 100.0)
        buckling_errs.append(_rel_err(float(m["buckling_factor"]["lf"]), float(m["buckling_factor"]["hf"])) * 100.0)
        mac_vals.append(float(m["mode_shape_mac"]["lf"]))
        residual_vals.append(float(m["equilibrium_residual"]["lf"]))
    return {
        "case_count": len(cases),
        "drift_error_pct": sum(drift_errs) / len(drift_errs),
        "base_shear_error_pct": sum(base_errs) / len(base_errs),
        "mode_shape_mac": sum(mac_vals) / len(mac_vals),
        "buckling_factor_error_pct": sum(buckling_errs) / len(buckling_errs),
        "equilibrium_residual_mean": sum(residual_vals) / len(residual_vals),
    }


def _delta_pct(before: float, after: float, higher_better: bool) -> float:
    if higher_better:
        d = max(abs(before), EPS)
        return (after - before) / d * 100.0
    d = max(abs(before), EPS)
    return (before - after) / d * 100.0


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cases", default="implementation/phase1/commercial_benchmark_cases.json")
    p.add_argument("--out", default="implementation/phase1/hf_benchmark_report.json")
    p.add_argument("--comparison-out", default="implementation/phase1/topk_comparison_experiment_report.json")
    p.add_argument("--target-split", choices=["all", "train", "val", "test"], default="test")
    p.add_argument("--epochs", type=int, default=180)
    p.add_argument("--branches", type=int, default=8)
    p.add_argument("--top-k", type=int, default=3)
    p.add_argument("--lr", type=float, default=0.06)
    p.add_argument("--epsilon", type=float, default=0.12)
    p.add_argument("--temperature", type=float, default=0.35)
    p.add_argument("--seed", type=int, default=23)
    p.add_argument("--max-drift-error-pct", type=float, default=5.0)
    p.add_argument("--max-base-shear-error-pct", type=float, default=5.0)
    p.add_argument("--min-mode-shape-mac", type=float, default=0.95)
    p.add_argument("--max-buckling-factor-error-pct", type=float, default=5.0)
    p.add_argument("--require-direct-metrics", action="store_true")
    p.add_argument(
        "--accepted-metric-sources",
        default="engine_export_direct,commercial_solver_export",
        help="comma-separated accepted metric_source values when --require-direct-metrics is enabled",
    )
    args = p.parse_args()

    if args.top_k < 2:
        raise SystemExit("--top-k must be >= 2")
    if args.top_k > args.branches:
        raise SystemExit("--top-k cannot exceed --branches")

    accepted_metric_sources = _parse_csv_set(args.accepted_metric_sources)
    if args.require_direct_metrics and len(accepted_metric_sources) == 0:
        raise SystemExit("--accepted-metric-sources cannot be empty when --require-direct-metrics is enabled")

    cases_path = Path(args.cases)
    torch = _require_torch()
    cases, metric_source_validation = _load_cases(
        cases_path,
        require_direct_metrics=bool(args.require_direct_metrics),
        accepted_metric_sources=accepted_metric_sources,
    )
    source_families = _source_family_order(cases)

    train_cases = [c for c in cases if c.get("split") == "train"]
    val_cases = [c for c in cases if c.get("split") == "val"]
    test_cases = [c for c in cases if c.get("split") == "test"]
    if len(train_cases) == 0 or len(test_cases) == 0:
        raise SystemExit("cases must include at least train and test splits")

    params, history = _train_topk(
        torch=torch,
        train_cases=train_cases,
        branches=args.branches,
        top_k=args.top_k,
        epochs=args.epochs,
        lr=args.lr,
        epsilon=args.epsilon,
        temperature=args.temperature,
        seed=args.seed,
        source_families=source_families,
    )

    model_train = _evaluate_split(torch, params, train_cases, source_families)
    model_val = _evaluate_split(torch, params, val_cases, source_families)
    model_test = _evaluate_split(torch, params, test_cases, source_families)
    model_all = _evaluate_split(torch, params, cases, source_families)

    baseline_train = _evaluate_baseline(train_cases)
    baseline_val = _evaluate_baseline(val_cases)
    baseline_test = _evaluate_baseline(test_cases)
    baseline_all = _evaluate_baseline(cases)

    target = {
        "all": model_all,
        "train": model_train,
        "val": model_val,
        "test": model_test,
    }[args.target_split]
    baseline_target = {
        "all": baseline_all,
        "train": baseline_train,
        "val": baseline_val,
        "test": baseline_test,
    }[args.target_split]

    metrics = {
        "drift_error_pct": float(target["drift_error_pct"]),
        "base_shear_error_pct": float(target["base_shear_error_pct"]),
        "mode_shape_mac": float(target["mode_shape_mac"]),
        "buckling_factor_error_pct": float(target["buckling_factor_error_pct"]),
    }
    checks = {
        "drift_ok": metrics["drift_error_pct"] <= args.max_drift_error_pct,
        "base_shear_ok": metrics["base_shear_error_pct"] <= args.max_base_shear_error_pct,
        "mac_ok": metrics["mode_shape_mac"] >= args.min_mode_shape_mac,
        "buckling_factor_ok": metrics["buckling_factor_error_pct"] <= args.max_buckling_factor_error_pct,
        "improves_over_lf": (
            metrics["drift_error_pct"] < baseline_target["drift_error_pct"]
            and metrics["base_shear_error_pct"] < baseline_target["base_shear_error_pct"]
            and metrics["buckling_factor_error_pct"] < baseline_target["buckling_factor_error_pct"]
            and metrics["mode_shape_mac"] > baseline_target["mode_shape_mac"]
        ),
    }
    kpi_pass = all(checks.values())
    reason_code = "PASS" if kpi_pass else "ERR_BENCHMARK_KPI_FAIL"

    report = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "algorithm": "topk_weighted_residual_correction_with_meta_learning",
        "source_cases_path": str(cases_path),
        "source_cases_sha256": _sha256(cases_path),
        "source_family_order": source_families,
        "contract_pass": kpi_pass,
        "reason_code": reason_code,
        "reason": REASON_CODES[reason_code],
        "kpi_pass": kpi_pass,
        "metrics": metrics,
        "checks": checks,
        "target_split": args.target_split,
        "comparison": {
            "baseline_lf": {
                "train": baseline_train,
                "val": baseline_val,
                "test": baseline_test,
                "all": baseline_all,
            },
            "topk_residual_meta": {
                "train": {k: v for k, v in model_train.items() if k != "rows"},
                "val": {k: v for k, v in model_val.items() if k != "rows"},
                "test": {k: v for k, v in model_test.items() if k != "rows"},
                "all": {k: v for k, v in model_all.items() if k != "rows"},
            },
            "improvement_pct": {
                "drift_error_reduction_pct": _delta_pct(
                    baseline_target["drift_error_pct"], metrics["drift_error_pct"], higher_better=False
                ),
                "base_shear_error_reduction_pct": _delta_pct(
                    baseline_target["base_shear_error_pct"], metrics["base_shear_error_pct"], higher_better=False
                ),
                "buckling_error_reduction_pct": _delta_pct(
                    baseline_target["buckling_factor_error_pct"], metrics["buckling_factor_error_pct"], higher_better=False
                ),
                "mode_shape_mac_gain_pct": _delta_pct(
                    baseline_target["mode_shape_mac"], metrics["mode_shape_mac"], higher_better=True
                ),
            },
        },
        "training": {
            "epochs": int(args.epochs),
            "branches": int(args.branches),
            "top_k": int(args.top_k),
            "lr": float(args.lr),
            "epsilon": float(args.epsilon),
            "temperature": float(args.temperature),
            "seed": int(args.seed),
            "final_total_loss": history[-1]["total_loss"] if history else None,
            "final_weighted_loss": history[-1]["weighted_loss"] if history else None,
            "last_selected_branch_ids": history[-1]["selected_branch_ids"] if history else [],
            "last_selected_weights": history[-1]["normalized_weights"] if history else [],
            "param_vector": [float(v) for v in params.tolist()],
        },
        "metric_source_validation": metric_source_validation,
    }

    comparison = {
        "schema_version": "1.0",
        "run_id": "phase1-topk-comparison-experiment",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_split": args.target_split,
        "source_cases_path": str(cases_path),
        "source_cases_sha256": _sha256(cases_path),
        "source_family_order": source_families,
        "rows": model_all["rows"],
        "history_tail": history[-20:],
        "summary": {
            "baseline_target": baseline_target,
            "topk_target": {k: v for k, v in target.items() if k != "rows"},
            "kpi_pass": kpi_pass,
        },
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote HF benchmark contract report: {out}")

    cmp_out = Path(args.comparison_out)
    cmp_out.parent.mkdir(parents=True, exist_ok=True)
    cmp_out.write_text(json.dumps(comparison, indent=2), encoding="utf-8")
    print(f"Wrote Top-k comparison report: {cmp_out}")

    if not kpi_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
