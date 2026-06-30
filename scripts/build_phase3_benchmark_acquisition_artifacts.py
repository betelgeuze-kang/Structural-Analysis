#!/usr/bin/env python3
"""Build Phase 3 non-seed benchmark acquisition policy artifacts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from release_evidence_metadata import git_head, input_checksums  # noqa: E402
from structural_analysis import ANALYSIS_ENGINE_VERSION, CLAIM_BOUNDARY_VERSION  # noqa: E402
from structural_analysis.benchmark.acquisition import build_phase3_acquisition_plan  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "phase3_benchmark_acquisition_plan.json"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _strip_volatile(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_volatile(value)
            for key, value in payload.items()
            if key not in {"generated_at"}
        }
    if isinstance(payload, list):
        return [_strip_volatile(item) for item in payload]
    return payload


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return payload


def build_phase3_benchmark_acquisition_artifact(
    *,
    repo_root: Path = ROOT,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    payload = build_phase3_acquisition_plan()
    payload.update(
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_commit_sha": source_commit_sha or git_head(repo_root),
            "engine_version": ANALYSIS_ENGINE_VERSION,
            "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
            "input_checksums": input_checksums(
                [
                    Path("src/structural_analysis/benchmark/acquisition.py"),
                    Path("scripts/build_phase3_benchmark_acquisition_artifacts.py"),
                    Path("scripts/build_phase3_buildingsmart_ifc_acquisition_receipt.py"),
                    Path("scripts/build_phase3_buildingsmart_dirty_ifc_acquisition_receipt.py"),
                    Path("scripts/build_phase3_ifc_query_gui_readiness_receipt.py"),
                    Path("scripts/build_phase3_ifc_source_license_receipt.py"),
                    Path("scripts/build_phase3_opensees_source_license_receipt.py"),
                    Path("scripts/build_phase3_medium_model_scorecard_readiness_receipt.py"),
                    Path("scripts/run_phase3_medium_model_scorecard_receipt.py"),
                    Path("scripts/build_phase3_large_model_runner_readiness_receipt.py"),
                    Path("scripts/run_phase3_large_model_execution_receipt.py"),
                    Path("scripts/build_phase4_commercial_comparison_import_template.py"),
                    Path("scripts/build_phase4_commercial_cross_solver_readiness_receipt.py"),
                    Path("scripts/build_phase4_commercial_operator_reference_contract.py"),
                    Path("scripts/build_phase4_commercial_operator_reference_ingest_validator.py"),
                    Path("implementation/phase1/open_data/megastructure/opensees/SCBF16B_shell_beam_mix.tcl"),
                    Path("implementation/phase1/open_data/megastructure/opensees/SCBF16B.tcl"),
                    Path("implementation/phase1/opensees_topology_report.json"),
                    Path("implementation/phase1/release/benchmark_expansion/opensees_canonical_breadth_report.json"),
                ],
                repo_root=repo_root,
            ),
        }
    )
    return payload


def write_phase3_benchmark_acquisition_artifact(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    payload = build_phase3_benchmark_acquisition_artifact(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    return payload


def check_phase3_benchmark_acquisition_artifact(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    source_commit_sha: str | None = None,
) -> tuple[bool, str]:
    expected = build_phase3_benchmark_acquisition_artifact(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    if not resolved.exists():
        return False, f"phase3_benchmark_acquisition_missing:{out_path.as_posix()}"
    try:
        existing = _load_json(resolved)
    except Exception as exc:
        return False, f"phase3_benchmark_acquisition_unreadable:{out_path.as_posix()}:{exc.__class__.__name__}"
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "phase3_benchmark_acquisition_mismatch"
    return True, "phase3_benchmark_acquisition_consistent"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--source-commit-sha", default=None)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        ok, message = check_phase3_benchmark_acquisition_artifact(
            out_path=args.out,
            source_commit_sha=args.source_commit_sha,
        )
        print(f"Phase 3 benchmark acquisition check: {message}")
        return 0 if ok else 1
    payload = write_phase3_benchmark_acquisition_artifact(
        out_path=args.out,
        source_commit_sha=args.source_commit_sha,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "Phase 3 benchmark acquisition plan: "
            f"{payload['status']} | lanes={payload['non_seed_lane_count']} | "
            f"ready_sources={payload['ready_source_count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
