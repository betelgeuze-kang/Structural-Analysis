#!/usr/bin/env python3
"""Build benchmark case JSON from commercial HF/LF export CSV files.

Supported modes:
1) paired csv mode:  --hf-csv + --lf-csv
2) merged csv mode:  --merged-csv with hf/lf metric prefixes

Required metadata columns:
- case_id
- split                 : train|val|test
- ood_tag               : in_distribution|ood_topology|ood_hazard|ood_combined
- topology_type         : rahmen|truss|outrigger|wall-frame
- hazard_type           : wind|seismic|combined
- load_scale            : float > 0
- residual_norm         : float >= 0

Metric columns (paired mode):
- drift_ratio_pct       : float >= 0
- base_shear_kN         : float >= 0
- mode_shape_mac        : float in [0, 1]
- buckling_factor       : float > 0
- equilibrium_residual  : float >= 0
- top_displacement_m    : float >= 0 (optional, can be required with --require-top-displacement)
- axial_force_kN        : float >= 0 (optional member-force KPI)

Metric columns (merged mode example):
- hf_drift_ratio_pct / lf_drift_ratio_pct
- hf_base_shear_kN / lf_base_shear_kN
- hf_mode_shape_mac / lf_mode_shape_mac
- hf_buckling_factor / lf_buckling_factor
- hf_equilibrium_residual / lf_equilibrium_residual
- hf_top_displacement_m / lf_top_displacement_m (optional, can be required with --require-top-displacement)
- hf_axial_force_kN / lf_axial_force_kN (optional member-force KPI)
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path


REQUIRED_COLS = [
    "case_id",
    "split",
    "ood_tag",
    "topology_type",
    "hazard_type",
    "load_scale",
    "residual_norm",
    "drift_ratio_pct",
    "base_shear_kN",
    "mode_shape_mac",
    "buckling_factor",
    "equilibrium_residual",
]
META_COLS = REQUIRED_COLS[:7]
SPLITS = {"train", "val", "test"}
OOD_TAGS = {"in_distribution", "ood_topology", "ood_hazard", "ood_combined"}
TOPOLOGIES = {"rahmen", "truss", "outrigger", "wall-frame"}
HAZARDS = {"wind", "seismic", "combined"}
ELEMENT_MIXES = {"beam_only", "shell_only", "shell_beam_mix", "unknown"}
METRICS = [
    "drift_ratio_pct",
    "base_shear_kN",
    "mode_shape_mac",
    "buckling_factor",
    "equilibrium_residual",
]
OPTIONAL_METRICS = [
    "top_displacement_m",
    "axial_force_kN",
]


def _to_float(v: str, key: str, case_id: str) -> float:
    try:
        return float(v)
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"[{case_id}] '{key}' is not numeric: {v!r} ({exc})")


def _validate_meta(row: dict, case_id: str, tag: str) -> tuple[str, str, str, str, float, float]:
    split = str(row["split"]).strip()
    if split not in SPLITS:
        raise SystemExit(f"[{case_id}] invalid split in {tag}: {split}")
    ood_tag = str(row["ood_tag"]).strip()
    if ood_tag not in OOD_TAGS:
        raise SystemExit(f"[{case_id}] invalid ood_tag in {tag}: {ood_tag}")
    topology_type = str(row["topology_type"]).strip()
    if topology_type not in TOPOLOGIES:
        raise SystemExit(f"[{case_id}] invalid topology_type in {tag}: {topology_type}")
    hazard_type = str(row["hazard_type"]).strip()
    if hazard_type not in HAZARDS:
        raise SystemExit(f"[{case_id}] invalid hazard_type in {tag}: {hazard_type}")

    load_scale = _to_float(row["load_scale"], "load_scale", case_id)
    residual_norm = _to_float(row["residual_norm"], "residual_norm", case_id)
    if load_scale <= 0.0:
        raise SystemExit(f"[{case_id}] load_scale must be > 0 in {tag}")
    if residual_norm < 0.0:
        raise SystemExit(f"[{case_id}] residual_norm must be >= 0 in {tag}")
    return split, ood_tag, topology_type, hazard_type, load_scale, residual_norm


def _optional_source_family(row: dict, default_source_family: str) -> str:
    v = str(row.get("source_family", default_source_family)).strip()
    return v if v else str(default_source_family)


def _optional_element_mix(row: dict) -> str:
    raw = str(row.get("element_mix", "")).strip().lower()
    if raw:
        v = raw
    else:
        topo = str(row.get("topology_type", "")).strip().lower()
        if topo in {"outrigger", "wall-frame"}:
            v = "shell_beam_mix"
        else:
            v = "beam_only"
    if v not in ELEMENT_MIXES:
        raise SystemExit(f"invalid element_mix: {v} (expected one of {sorted(ELEMENT_MIXES)})")
    return v


def _validate_metrics(metrics: dict[str, float], case_id: str, tag: str) -> None:
    for m, v in metrics.items():
        if m == "mode_shape_mac":
            if not (0.0 <= v <= 1.0):
                raise SystemExit(f"[{case_id}] mode_shape_mac must be in [0,1] in {tag}")
        elif m == "buckling_factor":
            if v <= 0.0:
                raise SystemExit(f"[{case_id}] buckling_factor must be > 0 in {tag}")
        else:
            if v < 0.0:
                raise SystemExit(f"[{case_id}] {m} must be >= 0 in {tag}")


def _load_single_metric_side(row: dict, case_id: str) -> dict[str, float]:
    metrics = {m: _to_float(row[m], m, case_id) for m in METRICS}
    for m in OPTIONAL_METRICS:
        if m in row and str(row.get(m, "")).strip() != "":
            metrics[m] = _to_float(row[m], m, case_id)
    _validate_metrics(metrics, case_id=case_id, tag="paired-csv")
    return metrics


def _load_csv(
    path: Path,
    tag: str,
    *,
    require_top_displacement: bool = False,
    default_source_family: str = "commercial_export",
) -> dict[str, dict]:
    if not path.exists():
        raise SystemExit(f"{tag} csv not found: {path}")
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    if len(rows) == 0:
        raise SystemExit(f"{tag} csv has no rows: {path}")
    req_cols = list(REQUIRED_COLS)
    if bool(require_top_displacement):
        req_cols.extend(OPTIONAL_METRICS)
    missing_cols = [c for c in req_cols if c not in (rows[0].keys() if rows else [])]
    if missing_cols:
        raise SystemExit(f"{tag} csv missing columns: {missing_cols}")

    out: dict[str, dict] = {}
    for row in rows:
        case_id = str(row.get("case_id", "")).strip()
        if not case_id:
            raise SystemExit(f"{tag} csv has empty case_id")
        if case_id in out:
            raise SystemExit(f"{tag} csv has duplicate case_id: {case_id}")

        split, ood_tag, topology_type, hazard_type, load_scale, residual_norm = _validate_meta(row, case_id, tag=tag)
        metrics = _load_single_metric_side(row=row, case_id=case_id)
        source_family = _optional_source_family(row, default_source_family)
        element_mix = _optional_element_mix(row)

        out[case_id] = {
            "case_id": case_id,
            "split": split,
            "ood_tag": ood_tag,
            "topology_type": topology_type,
            "hazard_type": hazard_type,
            "load_scale": load_scale,
            "residual_norm": residual_norm,
            "source_family": source_family,
            "element_mix": element_mix,
            "metrics": metrics,
        }
    return out


def _build_cases(hf: dict[str, dict], lf: dict[str, dict], metric_source: str) -> list[dict]:
    if set(hf.keys()) != set(lf.keys()):
        hf_only = sorted(set(hf.keys()) - set(lf.keys()))
        lf_only = sorted(set(lf.keys()) - set(hf.keys()))
        raise SystemExit(f"HF/LF case mismatch. hf_only={hf_only}, lf_only={lf_only}")

    cases: list[dict] = []
    for case_id in sorted(hf.keys()):
        h = hf[case_id]
        low_fidelity_case = lf[case_id]
        for key in ("split", "ood_tag", "topology_type", "hazard_type", "source_family", "element_mix"):
            if str(h[key]) != str(low_fidelity_case[key]):
                raise SystemExit(f"[{case_id}] metadata mismatch for '{key}': hf={h[key]} lf={low_fidelity_case[key]}")

        # load/residual are taken from HF side but also validated against LF closeness.
        if abs(float(h["load_scale"]) - float(low_fidelity_case["load_scale"])) > 1e-9:
            raise SystemExit(f"[{case_id}] load_scale mismatch between HF and LF")
        if abs(float(h["residual_norm"]) - float(low_fidelity_case["residual_norm"])) > 1e-9:
            raise SystemExit(f"[{case_id}] residual_norm mismatch between HF and LF")

        metrics = {}
        for m in METRICS:
            metrics[m] = {"hf": float(h["metrics"][m]), "lf": float(low_fidelity_case["metrics"][m])}
        for m in OPTIONAL_METRICS:
            if m in h["metrics"] and m in low_fidelity_case["metrics"]:
                metrics[m] = {"hf": float(h["metrics"][m]), "lf": float(low_fidelity_case["metrics"][m])}

        cases.append(
            {
                "case_id": case_id,
                "split": h["split"],
                "ood_tag": h["ood_tag"],
                "topology_type": h["topology_type"],
                "hazard_type": h["hazard_type"],
                "source_family": str(h["source_family"]),
                "element_mix": str(h["element_mix"]),
                "load_scale": float(h["load_scale"]),
                "residual_norm": float(h["residual_norm"]),
                "metrics": metrics,
                "metric_source": metric_source,
            }
        )
    return cases


def _load_merged_csv(
    path: Path,
    hf_prefix: str,
    lf_prefix: str,
    metric_source: str,
    *,
    require_top_displacement: bool = False,
    default_source_family: str = "commercial_export",
) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"merged csv not found: {path}")
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    if len(rows) == 0:
        raise SystemExit(f"merged csv has no rows: {path}")
    keys = rows[0].keys() if rows else []

    missing_meta = [c for c in META_COLS if c not in keys]
    if missing_meta:
        raise SystemExit(f"merged csv missing metadata columns: {missing_meta}")

    required_metric_cols = [f"{hf_prefix}{m}" for m in METRICS] + [f"{lf_prefix}{m}" for m in METRICS]
    if bool(require_top_displacement):
        required_metric_cols += [f"{hf_prefix}{m}" for m in OPTIONAL_METRICS] + [f"{lf_prefix}{m}" for m in OPTIONAL_METRICS]
    missing_metric_cols = [c for c in required_metric_cols if c not in keys]
    if missing_metric_cols:
        raise SystemExit(f"merged csv missing metric columns: {missing_metric_cols}")

    seen: set[str] = set()
    out: list[dict] = []
    for row in rows:
        case_id = str(row.get("case_id", "")).strip()
        if not case_id:
            raise SystemExit("merged csv has empty case_id")
        if case_id in seen:
            raise SystemExit(f"merged csv has duplicate case_id: {case_id}")
        seen.add(case_id)

        split, ood_tag, topology_type, hazard_type, load_scale, residual_norm = _validate_meta(row, case_id, tag="merged-csv")
        source_family = _optional_source_family(row, default_source_family)
        element_mix = _optional_element_mix(row)

        hf_metrics = {m: _to_float(row[f"{hf_prefix}{m}"], f"{hf_prefix}{m}", case_id) for m in METRICS}
        lf_metrics = {m: _to_float(row[f"{lf_prefix}{m}"], f"{lf_prefix}{m}", case_id) for m in METRICS}
        _validate_metrics(hf_metrics, case_id=case_id, tag="merged-csv-hf")
        _validate_metrics(lf_metrics, case_id=case_id, tag="merged-csv-lf")

        combined_metrics = {m: {"hf": float(hf_metrics[m]), "lf": float(lf_metrics[m])} for m in METRICS}
        for m in OPTIONAL_METRICS:
            h_key = f"{hf_prefix}{m}"
            l_key = f"{lf_prefix}{m}"
            if h_key in row and l_key in row and str(row.get(h_key, "")).strip() != "" and str(row.get(l_key, "")).strip() != "":
                h_val = _to_float(row[h_key], h_key, case_id)
                l_val = _to_float(row[l_key], l_key, case_id)
                _validate_metrics({m: h_val}, case_id=case_id, tag="merged-csv-hf-optional")
                _validate_metrics({m: l_val}, case_id=case_id, tag="merged-csv-lf-optional")
                combined_metrics[m] = {"hf": float(h_val), "lf": float(l_val)}

        out.append(
            {
                "case_id": case_id,
                "split": split,
                "ood_tag": ood_tag,
                "topology_type": topology_type,
                "hazard_type": hazard_type,
                "source_family": source_family,
                "element_mix": element_mix,
                "load_scale": float(load_scale),
                "residual_norm": float(residual_norm),
                "metrics": combined_metrics,
                "metric_source": metric_source,
            }
        )
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--hf-csv", help="commercial HF export csv (paired mode)")
    p.add_argument("--lf-csv", help="LF/GNN baseline export csv (paired mode)")
    p.add_argument("--merged-csv", help="single merged export csv (merged mode)")
    p.add_argument("--hf-prefix", default="hf_", help="merged mode HF metric prefix")
    p.add_argument("--lf-prefix", default="lf_", help="merged mode LF metric prefix")
    p.add_argument("--metric-source", default="engine_export_direct")
    p.add_argument("--source-family", default="commercial_export")
    p.add_argument("--min-source-families", type=int, default=1)
    p.add_argument("--require-shell-beam-mix", action="store_true")
    p.add_argument("--require-top-displacement", action="store_true", help="require top_displacement_m columns in source CSV")
    p.add_argument("--public-case-count", type=int, default=4)
    p.add_argument("--out", default="implementation/phase1/commercial_benchmark_cases.json")
    args = p.parse_args()

    merged_mode = bool(args.merged_csv)
    paired_mode = bool(args.hf_csv and args.lf_csv)
    if merged_mode == paired_mode:
        raise SystemExit("select exactly one mode: (a) --hf-csv + --lf-csv or (b) --merged-csv")

    if merged_mode:
        cases = _load_merged_csv(
            path=Path(args.merged_csv),
            hf_prefix=str(args.hf_prefix),
            lf_prefix=str(args.lf_prefix),
            metric_source=str(args.metric_source),
            require_top_displacement=bool(args.require_top_displacement),
            default_source_family=str(args.source_family),
        )
    else:
        hf = _load_csv(
            Path(args.hf_csv),
            tag="hf",
            require_top_displacement=bool(args.require_top_displacement),
            default_source_family=str(args.source_family),
        )
        lf = _load_csv(
            Path(args.lf_csv),
            tag="lf",
            require_top_displacement=bool(args.require_top_displacement),
            default_source_family=str(args.source_family),
        )
        cases = _build_cases(hf, lf, metric_source=str(args.metric_source))

    split_counts = {"train": 0, "val": 0, "test": 0}
    for c in cases:
        split_counts[str(c["split"])] += 1
    if split_counts["train"] == 0 or split_counts["test"] == 0:
        raise SystemExit("cases must include at least one train and one test split")
    families = sorted({str(c.get("source_family", "")).strip() for c in cases if str(c.get("source_family", "")).strip()})
    if len(families) < int(args.min_source_families):
        raise SystemExit(
            f"source family count {len(families)} < min_source_families {int(args.min_source_families)}"
        )
    shell_beam_count = sum(1 for c in cases if str(c.get("element_mix", "unknown")).strip().lower() == "shell_beam_mix")
    if bool(args.require_shell_beam_mix) and shell_beam_count <= 0:
        raise SystemExit("require_shell_beam_mix enabled but no shell_beam_mix case exists")

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-commercial-benchmark-cases",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "mode": "merged_csv" if merged_mode else "paired_csv",
            "hf_csv": args.hf_csv,
            "lf_csv": args.lf_csv,
            "merged_csv": args.merged_csv,
            "hf_prefix": args.hf_prefix if merged_mode else None,
            "lf_prefix": args.lf_prefix if merged_mode else None,
            "metric_source": args.metric_source,
            "source_family": args.source_family,
            "min_source_families": int(args.min_source_families),
            "require_shell_beam_mix": bool(args.require_shell_beam_mix),
            "require_top_displacement": bool(args.require_top_displacement),
            "public_case_count": int(args.public_case_count),
        },
        "source_family_summary": {
            "distinct_source_families": families,
            "distinct_source_family_count": len(families),
            "shell_beam_mix_case_count": int(shell_beam_count),
        },
        "split_counts": split_counts,
        "public_benchmark_cases": [],
        "cases": cases,
    }

    public_count = max(1, int(args.public_case_count))
    preferred = [c for c in cases if str(c.get("split", "")) == "test"]
    if len(preferred) < public_count:
        preferred = list(cases)
    payload["public_benchmark_cases"] = [
        {
            "case_id": str(c["case_id"]),
            "hazard_type": str(c["hazard_type"]),
            "topology_type": str(c["topology_type"]),
            "source_family": str(c.get("source_family", "")),
            "element_mix": str(c.get("element_mix", "unknown")),
            "hf_metrics": {
                str(m): float((c.get("metrics", {}).get(m, {}) or {}).get("hf", 0.0))
                for m in sorted((c.get("metrics", {}) or {}).keys())
            },
        }
        for c in preferred[:public_count]
    ]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote commercial benchmark cases: {out}")


if __name__ == "__main__":
    main()
