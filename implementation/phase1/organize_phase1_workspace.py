#!/usr/bin/env python3
"""Organize Phase1 files into a workspace index for easier management.

Non-destructive by default: copies artifacts/reports into workspace and emits
catalogs that classify scripts and generated files.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
from pathlib import Path
import shutil


EXCLUDE_DIRS = {".git", "__pycache__", "workspace", "rust_hip_md3bead_hook/target"}
GENERATED_MARKERS = (
    "report",
    "summary",
    "manifest",
    "hf_benchmark_report",
    "topk_",
    "ci_gate_report",
    "static_artifact_validation_report",
    "zero_copy",
    "lf_to_gnn",
    "krylov_projection",
    "material_map",
    "physics_branching",
    "physics_residual",
    "bifurcation_detector",
    "buckling_contract",
    "winning_ticket_backprop",
    "rust_md3bead_parity",
    "nonlinear_lj_mapping",
    "pipeline_",
    "three_bead_cache_budget",
    "commercial_benchmark_cases.from_csv",
    "commercial_benchmark_cases.rwth_zenodo",
    "track_lf_solver_report",
    "moving_load_integrator_report",
    "vti_coupled_solver_report",
    "track_irregularity_report",
    "phaseb_track_summary_report",
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _is_excluded(path: Path) -> bool:
    s = path.as_posix()
    return any(token in s for token in EXCLUDE_DIRS)


def _group_script(name: str) -> str:
    n = name.lower()
    if "run_" in n or n.startswith("run"):
        return "pipelines"
    if "contract" in n or "gate" in n or "validate" in n:
        return "contracts_validation"
    if "benchmark" in n or "topk" in n or "cases" in n:
        return "benchmark_data"
    if "hook" in n or "probe" in n or "bridge" in n:
        return "hooks_runtime"
    if "md3bead" in n or "projection" in n or "gnn" in n:
        return "core_models"
    return "misc"


def _group_report(name: str) -> str:
    n = name.lower()
    if n.endswith(".parquet") or n.startswith("ulf_"):
        return "artifacts"
    if "ci" in n or "manifest" in n or "validation" in n:
        return "ci"
    if "benchmark" in n or "topk" in n or "commercial_benchmark_cases" in n:
        return "benchmark"
    if "contract" in n or "branching" in n or "bifurcation" in n:
        return "contracts"
    if "parity" in n or "cache_budget" in n:
        return "parity_cache"
    if "probe" in n or "runtime" in n or "step" in n or "smoke" in n:
        return "runtime"
    return "misc"


def _sync_file(src: Path, dst: Path, move: bool) -> dict:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if move:
        shutil.move(str(src), str(dst))
    else:
        shutil.copy2(src, dst)
    return {
        "src": str(src),
        "dst": str(dst),
        "bytes": dst.stat().st_size,
        "sha256": _sha256(dst),
        "mode": "move" if move else "copy",
    }


def _iter_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if _is_excluded(p):
            continue
        out.append(p)
    return out


def _is_generated_report(path: Path) -> bool:
    if path.suffix.lower() not in {".json", ".csv", ".parquet"}:
        return False
    rel = path.as_posix().lower()
    if "/step_outputs/" in rel:
        return True
    n = path.name.lower()
    if "schema" in n:
        return False
    return any(m in n for m in GENERATED_MARKERS)


def _is_script_file(path: Path) -> bool:
    return path.suffix.lower() == ".py"


def _is_input_data(path: Path) -> bool:
    n = path.name.lower()
    if n.endswith(".zip"):
        return True
    return any(
        fnmatch.fnmatch(n, pat)
        for pat in [
            "*sample*.csv",
            "*sample*.json",
            "commercial_hf_export*.csv",
            "commercial_lf_export*.csv",
            "material_input*.csv",
            "material_input*.json",
        ]
    )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default="implementation/phase1")
    p.add_argument("--workspace", default="implementation/phase1/workspace")
    p.add_argument("--clean", action="store_true", help="remove workspace before sync")
    p.add_argument("--move-reports", action="store_true", help="move report files into workspace instead of copying")
    args = p.parse_args()

    root = Path(args.root).resolve()
    workspace = Path(args.workspace).resolve()

    if args.clean and workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True, exist_ok=True)

    scripts_dir = workspace / "catalog" / "scripts"
    reports_dir = workspace / "reports"
    inputs_dir = workspace / "inputs"

    copied_reports: list[dict] = []
    copied_inputs: list[dict] = []
    script_groups: dict[str, list[str]] = {}

    for f in _iter_files(root):
        rel = f.relative_to(root)
        name = f.name

        if _is_script_file(f):
            g = _group_script(name)
            script_groups.setdefault(g, []).append(str(rel))
            continue

        if _is_input_data(f):
            dst = inputs_dir / rel
            copied_inputs.append(_sync_file(f, dst, move=False))
            continue

        if _is_generated_report(f):
            g = _group_report(name)
            dst = reports_dir / g / rel.name
            copied_reports.append(_sync_file(f, dst, move=bool(args.move_reports)))

    for g in script_groups:
        script_groups[g] = sorted(script_groups[g])

    scripts_dir.mkdir(parents=True, exist_ok=True)
    scripts_index = {
        "schema_version": "1.0",
        "run_id": "phase1-workspace-script-catalog",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "group_count": len(script_groups),
        "groups": script_groups,
    }
    (scripts_dir / "scripts_by_group.json").write_text(json.dumps(scripts_index, indent=2), encoding="utf-8")

    report_index = {
        "schema_version": "1.0",
        "run_id": "phase1-workspace-report-catalog",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workspace": str(workspace),
        "report_file_count": len(copied_reports),
        "input_file_count": len(copied_inputs),
        "reports": copied_reports,
        "inputs": copied_inputs,
    }
    (workspace / "catalog" / "report_catalog.json").parent.mkdir(parents=True, exist_ok=True)
    (workspace / "catalog" / "report_catalog.json").write_text(json.dumps(report_index, indent=2), encoding="utf-8")

    summary = {
        "schema_version": "1.0",
        "run_id": "phase1-workspace-organizer",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workspace": str(workspace),
        "script_groups": sorted(script_groups.keys()),
        "report_file_count": len(copied_reports),
        "input_file_count": len(copied_inputs),
        "catalog_scripts": str((scripts_dir / "scripts_by_group.json")),
        "catalog_reports": str((workspace / "catalog" / "report_catalog.json")),
    }
    out = workspace / "workspace_organization_report.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote workspace organization report: {out}")


if __name__ == "__main__":
    main()
