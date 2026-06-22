#!/usr/bin/env python3
"""Build a conservative Phase 6 medium/large benchmark-scale status receipt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import release_evidence_metadata  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "phase6_benchmark_scale_status.json"
PHASE3_MEDIUM_MODEL_SCORECARD = PRODUCTIZATION / "phase3_medium_model_scorecard_readiness_receipt.json"
PHASE3_LARGE_MODEL_RUNNER = PRODUCTIZATION / "phase3_large_model_runner_readiness_receipt.json"
PHASE3_ACQUISITION_PLAN = PRODUCTIZATION / "phase3_benchmark_acquisition_plan.json"
PHASE3_FACTORY_SUMMARY = PRODUCTIZATION / "phase3_benchmark_factory_seed_summary.json"
SCHEMA_VERSION = "phase6-benchmark-scale-status.v1"


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


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _blockers(payload: dict[str, Any]) -> list[str]:
    return [str(blocker) for blocker in payload.get("blockers", []) if str(blocker)]


def build_phase6_benchmark_scale_status(*, repo_root: Path = ROOT) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    medium = _load_json(repo_root, PHASE3_MEDIUM_MODEL_SCORECARD)
    large = _load_json(repo_root, PHASE3_LARGE_MODEL_RUNNER)
    summary = _load_json(repo_root, PHASE3_FACTORY_SUMMARY)

    medium_required = int(medium.get("required_medium_model_count", 5) or 5)
    medium_current = int(medium.get("current_medium_model_scorecard_count", 0) or 0)
    medium_review = int(medium.get("pass_or_approved_review_count", 0) or 0)
    medium_pass = bool(
        medium.get("contract_pass") is True
        and medium_current >= medium_required
        and medium_review >= medium_required
    )
    large_required = int(large.get("required_large_model_count", 2) or 2)
    large_execution = int(large.get("current_large_model_execution_receipt_count", 0) or 0)
    large_crash_oom_free = int(large.get("crash_oom_free_execution_count", 0) or 0)
    large_scorecard_or_review = int(large.get("scorecard_or_review_count", 0) or 0)
    large_pass = bool(
        large.get("contract_pass") is True
        and large_execution >= large_required
        and large_crash_oom_free >= large_required
        and large_scorecard_or_review >= large_required
    )
    medium_blockers = _blockers(medium)
    large_blockers = _blockers(large)
    if medium_current < medium_required:
        medium_blockers.append(f"medium_structural_models_current_below_required:{medium_current}/{medium_required}")
    if medium_review < medium_required:
        medium_blockers.append(f"medium_model_pass_or_review_below_required:{medium_review}/{medium_required}")
    if large_execution < large_required:
        large_blockers.append(f"large_model_execution_count_below_required:{large_execution}/{large_required}")
    if large_crash_oom_free < large_required:
        large_blockers.append(
            f"large_model_crash_oom_free_count_below_required:{large_crash_oom_free}/{large_required}"
        )
    if large_scorecard_or_review < large_required:
        large_blockers.append(
            f"large_model_scorecard_or_review_count_below_required:{large_scorecard_or_review}/{large_required}"
        )
    medium_blockers = sorted(dict.fromkeys(medium_blockers))
    large_blockers = sorted(dict.fromkeys(large_blockers))
    contract_pass = bool(medium_pass and large_pass)
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                PHASE3_MEDIUM_MODEL_SCORECARD,
                PHASE3_LARGE_MODEL_RUNNER,
                PHASE3_ACQUISITION_PLAN,
                PHASE3_FACTORY_SUMMARY,
                Path("scripts/build_phase6_benchmark_scale_status.py"),
            ],
            reused_evidence=True,
            reuse_policy="phase6_benchmark_scale_status_aggregates_phase3_medium_large_receipts",
            repo_root=repo_root,
        ),
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "developer_preview_release_candidate_claim": contract_pass,
        "seed_benchmark_status": str(summary.get("status", "missing")),
        "medium_gate": {
            "status": "ready" if medium_pass else "blocked",
            "contract_pass": medium_pass,
            "required_medium_model_count": medium_required,
            "current_medium_model_scorecard_count": medium_current,
            "pass_or_approved_review_count": medium_review,
            "local_candidate_artifact_count": int(medium.get("local_candidate_artifact_count", 0) or 0),
            "local_topology_contract_pass": bool(medium.get("local_topology_contract_pass") is True),
            "required_evidence_pass_count": int(medium.get("required_evidence_pass_count", 0) or 0),
            "blockers": medium_blockers,
            "receipt": PHASE3_MEDIUM_MODEL_SCORECARD.as_posix(),
            "claim_boundary": str(medium.get("claim_boundary", "")),
        },
        "large_gate": {
            "status": "ready" if large_pass else "blocked",
            "contract_pass": large_pass,
            "required_large_model_count": large_required,
            "current_large_model_execution_receipt_count": large_execution,
            "crash_oom_free_execution_count": large_crash_oom_free,
            "scorecard_or_review_count": large_scorecard_or_review,
            "required_evidence_pass_count": int(large.get("required_evidence_pass_count", 0) or 0),
            "blockers": large_blockers,
            "receipt": PHASE3_LARGE_MODEL_RUNNER.as_posix(),
            "claim_boundary": str(large.get("claim_boundary", "")),
        },
        "acquisition_plan": PHASE3_ACQUISITION_PLAN.as_posix(),
        "readiness_inputs": {
            "medium_model_scorecard_readiness_receipt": PHASE3_MEDIUM_MODEL_SCORECARD.as_posix(),
            "large_model_runner_readiness_receipt": PHASE3_LARGE_MODEL_RUNNER.as_posix(),
            "benchmark_acquisition_plan": PHASE3_ACQUISITION_PLAN.as_posix(),
            "benchmark_seed_summary": PHASE3_FACTORY_SUMMARY.as_posix(),
        },
        "blockers": sorted(dict.fromkeys([*medium_blockers, *large_blockers])),
        "owner_action": (
            "Attach five medium-model scorecards with PASS or pre-approved REVIEW evidence, "
            "attach two licensed large-model crash/OOM-free execution receipts with scorecard "
            "or review evidence, then rerun this status before promoting RC benchmark scale."
        ),
        "summary_line": (
            "Phase 6 benchmark scale: "
            f"{'READY' if contract_pass else 'BLOCKED'} | medium={medium_current}/{medium_required} | "
            f"large_exec={large_execution}/{large_required}"
        ),
        "claim_boundary": (
            "This receipt aggregates Phase 3 medium and large benchmark readiness for RC "
            "scale gates. parser-only topology evidence is not medium-model pass evidence, "
            "policy-only acquisition rows are not large-model execution evidence, and this "
            "receipt does not acquire sources, prove crash/OOM-free large execution, close "
            "Phase 3, or promote Developer Preview RC readiness."
        ),
    }


def write_phase6_benchmark_scale_status(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
) -> dict[str, Any]:
    payload = build_phase6_benchmark_scale_status(repo_root=repo_root)
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    return payload


def check_phase6_benchmark_scale_status(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
) -> tuple[bool, str]:
    expected = build_phase6_benchmark_scale_status(repo_root=repo_root)
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    if not resolved.exists():
        return False, f"phase6_benchmark_scale_status_missing:{out_path.as_posix()}"
    try:
        existing = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"phase6_benchmark_scale_status_unreadable:{exc.__class__.__name__}"
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "phase6_benchmark_scale_status_mismatch"
    return True, "phase6_benchmark_scale_status_consistent"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        ok, message = check_phase6_benchmark_scale_status(out_path=args.out)
        print(f"Phase 6 benchmark scale status check: {message}")
        return 0 if ok else 1
    payload = write_phase6_benchmark_scale_status(out_path=args.out)
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(payload["summary_line"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
