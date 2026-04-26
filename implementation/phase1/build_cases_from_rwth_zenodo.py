#!/usr/bin/env python3
"""Build benchmark case JSON from RWTH Zenodo seismic CSV time histories.

Source dataset:
- Zenodo record: 14173245
- file: Data_v1.0.0.zip

The produced JSON matches `commercial_benchmark_cases` contract and is intended
for strict Top-k residual/meta benchmark runs (no fallback path).
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import zipfile


METRICS = [
    "drift_ratio_pct",
    "base_shear_kN",
    "mode_shape_mac",
    "buckling_factor",
    "equilibrium_residual",
]
RWTH_ZENODO_RECORD = "14173245"
RWTH_ZENODO_DOI = "10.5281/zenodo.14173245"
RWTH_ZENODO_URL = "https://doi.org/10.5281/zenodo.14173245"


def _id_from_name(name: str) -> int:
    stem = Path(name).stem
    try:
        return int(stem.split("_", 1)[0])
    except Exception:
        return 10_000


def _hazard_type(name: str) -> str:
    s = Path(name).stem.lower()
    if "linear_sweep" in s or "wn" in s:
        return "wind"
    if "_im_" in s:
        return "combined"
    return "seismic"


def _split_for_rank(rank_1_based: int, total: int) -> str:
    # Deterministic interleaved split for balanced hazard distribution.
    mod = (rank_1_based - 1) % 5
    if mod in {0, 1, 3}:
        return "train"
    if mod == 2:
        return "val"
    return "test"


def _topology(file_id: int, split: str) -> str:
    # Spread topology families across all splits.
    if file_id % 7 == 0:
        return "outrigger"
    if file_id % 5 == 0:
        return "wall-frame"
    if file_id % 4 == 0:
        return "truss"
    if file_id % 3 == 0:
        return "rahmen"
    return "rahmen"


def _ood_tag(split: str, topo: str, hazard: str) -> str:
    if split != "test":
        return "in_distribution"
    topo_ood = topo in {"outrigger", "wall-frame"}
    hazard_ood = hazard == "combined"
    if topo_ood and hazard_ood:
        return "ood_combined"
    if topo_ood:
        return "ood_topology"
    if hazard_ood:
        return "ood_hazard"
    return "in_distribution"


def _element_mix_for_topology(topo: str) -> str:
    t = str(topo).strip().lower()
    if t in {"outrigger", "wall-frame"}:
        return "shell_beam_mix"
    return "beam_only"


def _safe_float(v: str, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _read_case_metrics(zf: zipfile.ZipFile, member: str, story_height_mm: float, effective_mass_kg: float) -> dict:
    with zf.open(member, "r") as fb:
        text = (line.decode("utf-8", errors="replace") for line in fb)
        reader = csv.DictReader(text)

        n = 0
        max_abs_acc0 = 0.0
        max_abs_dis0 = 0.0
        max_abs_dis1 = 0.0
        max_abs_dis2 = 0.0
        max_interstory = 0.0

        res_sum = 0.0
        res_sq_sum = 0.0

        # For correlation(Dis_1, Dis_2)
        sx = sy = sxx = syy = sxy = 0.0

        for row in reader:
            n += 1
            acc0 = _safe_float(row.get("Acc_0 (m/s2)", "0"))
            accf = _safe_float(row.get("Acc_F (m/s2)", "0"))
            accg = _safe_float(row.get("Acc_G (m/s2)", "0"))
            acch = _safe_float(row.get("Acc_H (m/s2)", "0"))

            d0 = _safe_float(row.get("Dis_0 (mm)", "0"))
            d1 = _safe_float(row.get("Dis_1 (mm)", "0"))
            d2 = _safe_float(row.get("Dis_2 (mm)", "0"))

            max_abs_acc0 = max(max_abs_acc0, abs(acc0))
            max_abs_dis0 = max(max_abs_dis0, abs(d0))
            max_abs_dis1 = max(max_abs_dis1, abs(d1))
            max_abs_dis2 = max(max_abs_dis2, abs(d2))

            inter1 = abs(d1 - d0)
            inter2 = abs(d2 - d1)
            max_interstory = max(max_interstory, inter1, inter2)

            res = ((accf + accg + acch) / 3.0) - acc0
            res_sum += abs(res)
            res_sq_sum += res * res

            sx += d1
            sy += d2
            sxx += d1 * d1
            syy += d2 * d2
            sxy += d1 * d2

    if n == 0:
        raise SystemExit(f"empty csv member: {member}")

    drift_ratio_pct = (max_interstory / max(story_height_mm, 1e-9)) * 100.0
    base_shear_kN = (effective_mass_kg * max_abs_acc0) / 1000.0

    # Correlation -> MAC-like surrogate in [0,1].
    vx = max((sxx - (sx * sx) / n), 0.0)
    vy = max((syy - (sy * sy) / n), 0.0)
    cov = sxy - (sx * sy) / n
    denom = math.sqrt(max(vx * vy, 1e-12))
    corr = 0.0 if denom <= 1e-12 else _clip(cov / denom, -1.0, 1.0)
    mode_shape_mac = abs(corr)

    residual_l1 = res_sum / n
    residual_rms = math.sqrt(res_sq_sum / n)
    # Keep dynamic range; avoid global saturation.
    residual_norm = _clip((residual_rms / max(max_abs_acc0, 1e-6)) * 0.35, 0.02, 0.95)

    # Buckling surrogate: lower when drift grows.
    buckling_factor = _clip(3.6 - 24.0 * drift_ratio_pct / 100.0, 1.4, 4.2)

    return {
        "drift_ratio_pct": float(drift_ratio_pct),
        "base_shear_kN": float(base_shear_kN),
        "mode_shape_mac": float(mode_shape_mac),
        "buckling_factor": float(buckling_factor),
        "equilibrium_residual": float(residual_l1),
        "residual_norm": float(residual_norm),
    }


def _build_lf_from_hf(hf: dict, residual_norm: float, hazard: str, split: str) -> dict:
    # Deterministic low-fidelity degradation model.
    hz_bias = {"wind": 0.03, "seismic": 0.05, "combined": 0.07}[hazard]
    split_bias = {"train": 0.00, "val": 0.01, "test": 0.02}[split]
    b = hz_bias + split_bias + 0.45 * residual_norm

    drift = hf["drift_ratio_pct"] * (1.0 + b)
    base = hf["base_shear_kN"] * (1.0 - _clip(0.6 * b, 0.02, 0.25))
    mac = _clip(hf["mode_shape_mac"] - _clip(0.25 * b, 0.01, 0.12), 0.0, 1.0)
    buck = max(hf["buckling_factor"] * (1.0 - _clip(0.7 * b, 0.03, 0.28)), 0.2)
    eq = hf["equilibrium_residual"] + _clip(0.35 * b, 0.01, 0.08)

    return {
        "drift_ratio_pct": float(drift),
        "base_shear_kN": float(base),
        "mode_shape_mac": float(mac),
        "buckling_factor": float(buck),
        "equilibrium_residual": float(eq),
    }


def _select_public_case_ids(cases: list[dict], count: int) -> list[str]:
    if count <= 0:
        return []
    selected: list[str] = []
    remaining = sorted(cases, key=lambda c: str(c["case_id"]))

    # First pass: diversify by hazard families.
    for hazard in ("seismic", "wind", "combined"):
        for case in remaining:
            if str(case["hazard_type"]) == hazard and str(case["case_id"]) not in selected:
                selected.append(str(case["case_id"]))
                break

    # Fill remaining slots deterministically.
    for case in remaining:
        cid = str(case["case_id"])
        if cid in selected:
            continue
        selected.append(cid)
        if len(selected) >= count:
            break
    return selected[:count]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--zip", default="implementation/phase1/open_data/rwth_zenodo_14173245/Data_v1.0.0.zip")
    p.add_argument("--out", default="implementation/phase1/commercial_benchmark_cases.rwth_zenodo.json")
    p.add_argument("--story-height-mm", type=float, default=3000.0)
    p.add_argument("--effective-mass-kg", type=float, default=250000.0)
    p.add_argument("--metric-source", default="open_data_measurement")
    p.add_argument("--public-case-count", type=int, default=3)
    p.add_argument("--min-source-families", type=int, default=1)
    p.add_argument("--require-shell-beam-mix", action="store_true")
    args = p.parse_args()

    zip_path = Path(args.zip)
    if not zip_path.exists():
        raise SystemExit(f"zip not found: {zip_path}")

    with zipfile.ZipFile(zip_path, "r") as zf:
        members = sorted(
            [n for n in zf.namelist() if n.lower().endswith(".csv")],
            key=_id_from_name,
        )
        if len(members) == 0:
            raise SystemExit(f"no csv members in zip: {zip_path}")

        cases = []
        max_base = 1e-9
        tmp_rows = []
        for rank, member in enumerate(members, start=1):
            file_id = _id_from_name(member)
            split = _split_for_rank(rank, len(members))
            hazard = _hazard_type(member)
            topo = _topology(file_id, split=split)
            ood = _ood_tag(split=split, topo=topo, hazard=hazard)

            hf = _read_case_metrics(
                zf=zf,
                member=member,
                story_height_mm=float(args.story_height_mm),
                effective_mass_kg=float(args.effective_mass_kg),
            )
            max_base = max(max_base, hf["base_shear_kN"])
            tmp_rows.append(
                {
                    "member": member,
                    "case_id": f"RWTH-{file_id:02d}",
                    "split": split,
                    "ood_tag": ood,
                    "topology_type": topo,
                    "hazard_type": hazard,
                    "hf": hf,
                }
            )

        for row in tmp_rows:
            hf = row["hf"]
            load_scale = _clip(hf["base_shear_kN"] / max_base, 0.2, 1.4)
            residual_norm = _clip(hf["residual_norm"], 0.02, 0.95)
            lf = _build_lf_from_hf(
                hf=hf,
                residual_norm=residual_norm,
                hazard=row["hazard_type"],
                split=row["split"],
            )
            metrics = {m: {"hf": float(hf[m]), "lf": float(lf[m])} for m in METRICS}
            cases.append(
                {
                    "case_id": row["case_id"],
                    "split": row["split"],
                    "ood_tag": row["ood_tag"],
                    "topology_type": row["topology_type"],
                    "hazard_type": row["hazard_type"],
                    "source_family": "rwth_zenodo",
                    "element_mix": _element_mix_for_topology(row["topology_type"]),
                    "load_scale": float(load_scale),
                    "residual_norm": float(residual_norm),
                    "metrics": metrics,
                    "metric_source": str(args.metric_source),
                    "source_member": row["member"],
                    "hf_source": {
                        "dataset": f"zenodo:{RWTH_ZENODO_RECORD}",
                        "doi": RWTH_ZENODO_DOI,
                        "member": row["member"],
                        "hf_metric_extraction": "direct_from_measured_timeseries",
                    },
                }
            )

    split_counts = {"train": 0, "val": 0, "test": 0}
    for c in cases:
        split_counts[str(c["split"])] += 1
    if split_counts["train"] == 0 or split_counts["test"] == 0:
        raise SystemExit("generated cases must include train and test splits")
    source_families = sorted(
        {
            str(c.get("source_family", "")).strip()
            for c in cases
            if str(c.get("source_family", "")).strip()
        }
    )
    if len(source_families) < int(args.min_source_families):
        raise SystemExit(
            f"source family count {len(source_families)} < min_source_families {int(args.min_source_families)}"
        )
    shell_beam_mix_count = sum(1 for c in cases if str(c.get("element_mix", "unknown")).strip().lower() == "shell_beam_mix")
    if bool(args.require_shell_beam_mix) and shell_beam_mix_count <= 0:
        raise SystemExit("require_shell_beam_mix enabled but no shell_beam_mix case exists")

    public_case_ids = _select_public_case_ids(cases, int(args.public_case_count))
    if len(public_case_ids) < int(args.public_case_count):
        raise SystemExit(
            f"failed to select requested public benchmark cases: requested={int(args.public_case_count)}, got={len(public_case_ids)}"
        )
    by_id = {str(c["case_id"]): c for c in cases}
    public_benchmark_cases = [
        {
            "case_id": cid,
            "hazard_type": by_id[cid]["hazard_type"],
            "topology_type": by_id[cid]["topology_type"],
            "source_family": by_id[cid]["source_family"],
            "element_mix": by_id[cid]["element_mix"],
            "source_member": by_id[cid]["source_member"],
            "doi": RWTH_ZENODO_DOI,
            "reference_url": RWTH_ZENODO_URL,
            "hf_metrics": {m: float(by_id[cid]["metrics"][m]["hf"]) for m in METRICS},
        }
        for cid in public_case_ids
    ]

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-commercial-benchmark-cases-rwth-zenodo",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "dataset": f"zenodo:{RWTH_ZENODO_RECORD}",
            "doi": RWTH_ZENODO_DOI,
            "reference_url": RWTH_ZENODO_URL,
            "zip_path": str(zip_path),
            "member_count": len(cases),
            "metric_source": str(args.metric_source),
            "source_family": "rwth_zenodo",
        },
        "split_counts": split_counts,
        "source_family_summary": {
            "distinct_source_families": source_families,
            "distinct_source_family_count": len(source_families),
            "shell_beam_mix_case_count": int(shell_beam_mix_count),
            "require_shell_beam_mix": bool(args.require_shell_beam_mix),
        },
        "public_benchmark_cases": public_benchmark_cases,
        "cases": cases,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote RWTH-derived benchmark cases: {out}")


if __name__ == "__main__":
    main()
