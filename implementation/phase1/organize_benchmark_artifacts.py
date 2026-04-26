#!/usr/bin/env python3
"""Organize benchmark artifacts into a reproducible run bundle.

- Separates baseline and top-k summaries
- Copies selected artifacts into a timestamped run directory
- Emits hash manifest for traceability
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import glob
import hashlib
import json
from pathlib import Path
import shutil


DEFAULT_GLOBS = [
    "implementation/phase1/hf_benchmark_report.seed_*.json",
    "implementation/phase1/topk_comparison_experiment_report.seed_*.json",
    "implementation/phase1/hf_benchmark_report.rwth_tune_*.json",
    "implementation/phase1/topk_comparison_experiment_report.rwth_tune_*.json",
]

CONTRACT_REPORTS = [
    "implementation/phase1/dynamics_boundary_report.json",
    "implementation/phase1/dynamics_boundary_report.building.json",
    "implementation/phase1/dynamics_boundary_report.track.json",
    "implementation/phase1/dynamics_boundary_report.tunnel.json",
    "implementation/phase1/phasea_contract_report.json",
    "implementation/phase1/pg_gat_contract_report.json",
    "implementation/phase1/subgraph_projection_report.json",
    "implementation/phase1/soa_dlpack_contract_report.json",
    "implementation/phase1/physics_residual_contract_report.json",
    "implementation/phase1/meta_learning_task_report.json",
    "implementation/phase1/buckling_contract_report.json",
    "implementation/phase1/physics_branching_report.json",
    "implementation/phase1/bifurcation_detector_report.json",
    "implementation/phase1/rust_onnx_native_contract_report.json",
    "implementation/phase1/winning_ticket_backprop_report.json",
    "implementation/phase1/dynamic_time_history_report.json",
    "implementation/phase1/branch64_microbatch_profile_report.json",
    "implementation/phase1/track_lf_solver_report.json",
    "implementation/phase1/moving_load_integrator_report.json",
    "implementation/phase1/vti_coupled_solver_report.json",
    "implementation/phase1/track_irregularity_report.json",
    "implementation/phase1/phaseb_track_summary_report.json",
    "implementation/phase1/track_dynamics_dataset_report.json",
    "implementation/phase1/tunnel_dynamics_dataset_report.json",
    "implementation/phase1/moving_load_attention_report.json",
    "implementation/phase1/tgnn_multidomain_report.json",
    "implementation/phase1/phased_multidomain_summary_report.json",
]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _copy(src: Path, dst: Path) -> dict:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return {
        "src": str(src),
        "dst": str(dst),
        "bytes": dst.stat().st_size,
        "sha256": _sha256(dst),
    }


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _safe_label(label: str) -> str:
    return "".join(c if (c.isalnum() or c in {"-", "_", "."}) else "-" for c in label)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out-root", default="implementation/phase1/experiments")
    p.add_argument("--label", default=None)
    p.add_argument("--cases", default="implementation/phase1/commercial_benchmark_cases.from_csv.json")
    p.add_argument("--benchmark", default="implementation/phase1/hf_benchmark_report.json")
    p.add_argument("--comparison", default="implementation/phase1/topk_comparison_experiment_report.json")
    p.add_argument("--suite", default="implementation/phase1/topk_precision_suite_report.json")
    p.add_argument("--ci", default="implementation/phase1/ci_gate_report.json")
    p.add_argument("--validation", default="implementation/phase1/static_artifact_validation_report.json")
    p.add_argument("--include-glob", action="append", default=[])
    p.add_argument("--skip-default-globs", action="store_true")
    p.add_argument("--out-report", default=None)
    args = p.parse_args()

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    label = _safe_label(args.label or f"run_{ts}")

    out_root = Path(args.out_root)
    run_dir = out_root / label
    if run_dir.exists():
        raise SystemExit(f"run directory already exists: {run_dir}")

    copied: list[dict] = []

    def maybe_copy(src_path: str, rel_dir: str) -> None:
        src = Path(src_path)
        if not src.exists():
            return
        dst = run_dir / rel_dir / src.name
        copied.append(_copy(src, dst))

    # Core artifacts
    maybe_copy(args.cases, "inputs")
    maybe_copy(args.benchmark, "benchmark")
    maybe_copy(args.comparison, "benchmark")
    maybe_copy(args.suite, "benchmark")
    maybe_copy(args.ci, "contracts")
    maybe_copy(args.validation, "contracts")

    for path in CONTRACT_REPORTS:
        maybe_copy(path, "contracts")

    globs = [] if args.skip_default_globs else list(DEFAULT_GLOBS)
    globs.extend(args.include_glob)
    seen = set()
    for pattern in globs:
        for m in sorted(glob.glob(pattern)):
            if m in seen:
                continue
            seen.add(m)
            maybe_copy(m, "benchmark/runs")

    benchmark_data = _load_json(Path(args.benchmark)) or {}
    comparison = benchmark_data.get("comparison", {}) if isinstance(benchmark_data, dict) else {}
    baseline = comparison.get("baseline_lf", {}) if isinstance(comparison, dict) else {}
    topk = comparison.get("topk_residual_meta", {}) if isinstance(comparison, dict) else {}
    improvement = comparison.get("improvement_pct", {}) if isinstance(comparison, dict) else {}

    summary_dir = run_dir / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)

    baseline_summary_path = summary_dir / "baseline_summary.json"
    baseline_summary_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "kind": "baseline",
                "source_benchmark_report": args.benchmark,
                "summary": baseline,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    copied.append(
        {
            "src": str(Path(args.benchmark)),
            "dst": str(baseline_summary_path),
            "bytes": baseline_summary_path.stat().st_size,
            "sha256": _sha256(baseline_summary_path),
        }
    )

    topk_summary_path = summary_dir / "topk_summary.json"
    topk_summary_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "kind": "topk_residual_meta",
                "source_benchmark_report": args.benchmark,
                "summary": topk,
                "improvement_pct": improvement,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    copied.append(
        {
            "src": str(Path(args.benchmark)),
            "dst": str(topk_summary_path),
            "bytes": topk_summary_path.stat().st_size,
            "sha256": _sha256(topk_summary_path),
        }
    )

    manifest = {
        "schema_version": "1.0",
        "run_id": "phase1-artifact-bundle",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bundle_label": label,
        "bundle_dir": str(run_dir),
        "artifact_count": len(copied),
        "artifacts": copied,
    }
    manifest_path = run_dir / "artifact_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    report = {
        "schema_version": "1.0",
        "run_id": "phase1-artifact-organizer",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bundle_label": label,
        "bundle_dir": str(run_dir),
        "baseline_summary": str(baseline_summary_path),
        "topk_summary": str(topk_summary_path),
        "manifest": str(manifest_path),
        "copied_count": len(copied),
    }

    out_report = Path(args.out_report) if args.out_report else run_dir / "artifact_bundle_report.json"
    out_report.parent.mkdir(parents=True, exist_ok=True)
    out_report.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Wrote artifact bundle: {run_dir}")
    print(f"Wrote organizer report: {out_report}")


if __name__ == "__main__":
    main()
