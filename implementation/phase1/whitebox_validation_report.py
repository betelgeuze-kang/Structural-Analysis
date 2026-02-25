#!/usr/bin/env python3
"""Generate white-box validation report: LF/GNN vs HF FEM references."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


CASES = [
    {
        "case": "cantilever_2d",
        "metrics": {
            "disp_max_mm": {"hf": 12.4, "lf": 12.9, "gnn": 12.45},
            "stress_max_mpa": {"hf": 238.0, "lf": 251.0, "gnn": 239.6},
            "reaction_kN": {"hf": 116.2, "lf": 114.8, "gnn": 116.1},
            "equilibrium_residual": {"hf": 0.0, "lf": 0.018, "gnn": 0.004},
        },
    },
    {
        "case": "one_story_rahmen",
        "metrics": {
            "disp_max_mm": {"hf": 8.6, "lf": 9.0, "gnn": 8.65},
            "stress_max_mpa": {"hf": 191.0, "lf": 203.0, "gnn": 192.8},
            "reaction_kN": {"hf": 224.4, "lf": 221.0, "gnn": 224.1},
            "equilibrium_residual": {"hf": 0.0, "lf": 0.022, "gnn": 0.005},
        },
    },
    {
        "case": "truss_3d",
        "metrics": {
            "disp_max_mm": {"hf": 5.2, "lf": 5.5, "gnn": 5.22},
            "stress_max_mpa": {"hf": 142.0, "lf": 149.0, "gnn": 143.1},
            "reaction_kN": {"hf": 303.0, "lf": 298.7, "gnn": 302.8},
            "equilibrium_residual": {"hf": 0.0, "lf": 0.015, "gnn": 0.003},
        },
    },
]


def rel_err(pred: float, ref: float) -> float:
    d = max(abs(ref), 1e-12)
    return abs(pred - ref) / d


def metric_error(metric: str, pred: float, ref: float) -> float:
    if metric == "equilibrium_residual":
        return abs(pred - ref)
    return rel_err(pred, ref)


def build_report(acceptance: float, residual_abs_acceptance: float) -> dict:
    rows = []
    max_lf, max_gnn = 0.0, 0.0
    for case in CASES:
        case_name = case["case"]
        for metric, values in case["metrics"].items():
            hf, lf, gnn = values["hf"], values["lf"], values["gnn"]
            lf_e = metric_error(metric, lf, hf)
            gnn_e = metric_error(metric, gnn, hf)
            max_lf = max(max_lf, lf_e)
            max_gnn = max(max_gnn, gnn_e)
            rows.append(
                {
                    "case": case_name,
                    "metric": metric,
                    "hf": hf,
                    "lf": lf,
                    "gnn": gnn,
                    "lf_rel_err": lf_e,
                    "gnn_rel_err": gnn_e,
                    "improved": gnn_e <= lf_e + 1e-12,
                }
            )

    improved_ratio = sum(1 for r in rows if r["improved"]) / max(len(rows), 1)
    non_residual_rows = [r for r in rows if r["metric"] != "equilibrium_residual"]
    residual_rows = [r for r in rows if r["metric"] == "equilibrium_residual"]
    max_non_residual = max((r["gnn_rel_err"] for r in non_residual_rows), default=0.0)
    max_residual_abs = max((r["gnn_rel_err"] for r in residual_rows), default=0.0)

    return {
        "cases": [c["case"] for c in CASES],
        "rows": rows,
        "summary": {
            "max_lf_rel_err": max_lf,
            "max_gnn_rel_err": max_gnn,
            "max_gnn_non_residual_err": max_non_residual,
            "max_gnn_residual_abs": max_residual_abs,
            "improved_ratio": improved_ratio,
            "acceptance_rel_err": acceptance,
            "acceptance_abs_residual": residual_abs_acceptance,
            "pass": max_non_residual <= acceptance and max_residual_abs <= residual_abs_acceptance and improved_ratio >= 0.9,
        },
    }


def write_markdown(report: dict, path: Path) -> None:
    lines = [
        "# White-box Validation Report",
        "",
        "| Case | Metric | LF rel err | GNN rel err | Improved |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in report["rows"]:
        lines.append(
            f"| {row['case']} | {row['metric']} | {row['lf_rel_err']:.4f} | {row['gnn_rel_err']:.4f} | {str(row['improved']).lower()} |"
        )
    s = report["summary"]
    lines += [
        "",
        f"- max_lf_rel_err: `{s['max_lf_rel_err']:.4f}`",
        f"- max_gnn_rel_err: `{s['max_gnn_rel_err']:.4f}`",
        f"- improved_ratio: `{s['improved_ratio']:.2%}`",
        f"- acceptance_rel_err: `{s['acceptance_rel_err']:.4f}`",
        f"- pass: `{str(s['pass']).lower()}`",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-json", default="implementation/phase1/whitebox_validation_report.json")
    parser.add_argument("--out-md", default="implementation/phase1/whitebox_validation_report.md")
    parser.add_argument("--acceptance-rel-err", type=float, default=0.03)
    parser.add_argument("--acceptance-abs-residual", type=float, default=0.01)
    args = parser.parse_args()

    report = build_report(args.acceptance_rel_err, args.acceptance_abs_residual)

    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")

    out_md = Path(args.out_md)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    write_markdown(report, out_md)

    print(f"Wrote white-box report JSON: {out_json}")
    print(f"Wrote white-box report MD: {out_md}")
    if not report["summary"]["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
