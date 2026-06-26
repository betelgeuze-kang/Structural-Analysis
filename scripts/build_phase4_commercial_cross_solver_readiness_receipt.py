#!/usr/bin/env python3
"""Build a blocked Phase 4 commercial cross-solver readiness receipt."""

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


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "phase4_commercial_cross_solver_readiness_receipt.json"
IMPORT_TEMPLATE = PRODUCTIZATION / "phase4_commercial_comparison_import_template.json"
OPERATOR_CONTRACT = PRODUCTIZATION / "phase4_commercial_operator_reference_contract.json"
INGEST_VALIDATOR = PRODUCTIZATION / "phase4_commercial_operator_reference_ingest_validator.json"
CROSS_SOLVER_INPUTS = [
    Path("scripts/build_phase4_commercial_cross_solver_readiness_receipt.py"),
    Path("scripts/build_phase4_commercial_comparison_import_template.py"),
    Path("scripts/build_phase4_commercial_operator_reference_contract.py"),
    Path("scripts/build_phase4_commercial_operator_reference_ingest_validator.py"),
    Path("src/structure-viewer/viewer-commercial-tool-crosswalk-model.js"),
    Path("src/structure-viewer/viewer-report-export.js"),
    IMPORT_TEMPLATE,
    OPERATOR_CONTRACT,
    INGEST_VALIDATOR,
]


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
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return payload


def _contract_pass(payload: dict[str, Any]) -> bool:
    return bool(payload.get("contract_pass") is True or str(payload.get("status", "")).lower() in {"ready", "pass"})


def build_phase4_commercial_cross_solver_readiness_receipt(
    *,
    repo_root: Path = ROOT,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    import_template = _load_json(repo_root / IMPORT_TEMPLATE)
    operator_contract = _load_json(repo_root / OPERATOR_CONTRACT)
    ingest_validator = _load_json(repo_root / INGEST_VALIDATOR)
    gui_traceability = operator_contract.get("gui_traceability_contract")
    gui_traceability = gui_traceability if isinstance(gui_traceability, dict) else {}
    comparison_policy = operator_contract.get("comparison_diagnostic_policy")
    comparison_policy = comparison_policy if isinstance(comparison_policy, dict) else {}
    operator_blockers = [
        str(blocker)
        for blocker in operator_contract.get("remaining_blockers", [])
        if str(blocker)
    ]
    ingest_blockers = [
        str(blocker)
        for blocker in ingest_validator.get("blockers", [])
        if str(blocker)
    ]
    evidence_rows = [
        {
            "id": "import_template",
            "status": "ready" if _contract_pass(import_template) else "missing_or_blocked",
            "contract_pass": _contract_pass(import_template),
            "blocker": "" if _contract_pass(import_template) else "commercial_import_template_not_ready",
            "evidence": str(IMPORT_TEMPLATE),
        },
        {
            "id": "operator_package",
            "status": "missing",
            "contract_pass": False,
            "blocker": "operator_reference_package_missing",
            "evidence": str(OPERATOR_CONTRACT),
        },
        {
            "id": "permission_scope",
            "status": "missing",
            "contract_pass": False,
            "blocker": "license_or_customer_permission_missing",
            "evidence": str(OPERATOR_CONTRACT),
        },
        {
            "id": "operator_file_checksums",
            "status": "missing",
            "contract_pass": False,
            "blocker": "operator_file_checksums_missing",
            "evidence": str(INGEST_VALIDATOR),
        },
        {
            "id": "two_reference_solvers",
            "status": "blocked",
            "contract_pass": False,
            "blocker": "two_reference_solver_comparison_not_available",
            "required": int(operator_contract.get("required_reference_solver_count", 2) or 2),
            "current": int(operator_contract.get("current_reference_solver_count", 0) or 0),
            "evidence": str(OPERATOR_CONTRACT),
        },
        {
            "id": "modeling_conventions",
            "status": "missing_operator_declarations",
            "contract_pass": False,
            "blocker": "modeling_convention_declarations_missing",
            "required_fields": list(operator_contract.get("required_package_fields", [])),
            "evidence": str(OPERATOR_CONTRACT),
        },
        {
            "id": "modeling_assumption_first_diagnosis",
            "status": "policy_ready_execution_missing",
            "contract_pass": False,
            "blocker": "modeling_assumption_diagnosis_execution_missing",
            "diagnostic_order": list(comparison_policy.get("diagnostic_order", [])),
            "evidence": str(OPERATOR_CONTRACT),
        },
        {
            "id": "operator_ingest_validation",
            "status": str(ingest_validator.get("status", "blocked")),
            "contract_pass": _contract_pass(ingest_validator),
            "blocker": "" if _contract_pass(ingest_validator) else "operator_reference_ingest_validator_blocked",
            "evidence": str(INGEST_VALIDATOR),
        },
        {
            "id": "gui_operator_traceability",
            "status": "schema_ready_operator_rows_missing",
            "contract_pass": False,
            "blocker": "operator_comparison_trace_rows_missing",
            "required_trace_dimensions": list(gui_traceability.get("required_trace_dimensions", [])),
            "evidence": str(OPERATOR_CONTRACT),
        },
        {
            "id": "commercial_execution",
            "status": "missing",
            "contract_pass": False,
            "blocker": "commercial_cross_solver_execution_missing",
            "evidence": str(OPERATOR_CONTRACT),
        },
    ]
    blockers = sorted(
        {
            str(row["blocker"])
            for row in evidence_rows
            if str(row.get("blocker", ""))
        }
        | set(operator_blockers)
        | set(ingest_blockers)
    )
    pass_count = sum(1 for row in evidence_rows if row["contract_pass"] is True)
    return {
        "schema_version": "phase4-commercial-cross-solver-readiness-receipt.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": source_commit_sha or git_head(repo_root),
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "input_checksums": input_checksums(CROSS_SOLVER_INPUTS, repo_root=repo_root),
        "source_id": "commercial_cross_solver_operator_imports",
        "lanes": ["commercial-cross-solver"],
        "status": "blocked",
        "contract_pass": False,
        "phase3_closure_claim": False,
        "phase4_closure_claim": False,
        "developer_preview_release_candidate_claim": False,
        "commercial_outputs_are_absolute_truth": False,
        "required_reference_solver_count": int(operator_contract.get("required_reference_solver_count", 2) or 2),
        "current_reference_solver_count": int(operator_contract.get("current_reference_solver_count", 0) or 0),
        "operator_package_attached": False,
        "operator_permission_attached": False,
        "operator_checksum_count": 0,
        "operator_trace_rows_available": bool(gui_traceability.get("operator_trace_rows_available") is True),
        "required_evidence_count": len(evidence_rows),
        "required_evidence_pass_count": pass_count,
        "required_evidence": evidence_rows,
        "readiness_inputs": {
            "import_template": str(IMPORT_TEMPLATE),
            "operator_reference_contract": str(OPERATOR_CONTRACT),
            "ingest_validator": str(INGEST_VALIDATOR),
        },
        "operator_package_template": operator_contract.get("operator_reference_package_template", {}),
        "blocked_by": blockers,
        "blockers": blockers,
        "owner_action": (
            "Attach an operator-approved comparison package with two independent reference "
            "solver outputs, permission scope, raw and normalized file checksums, modeling "
            "convention declarations, ingest validation, modeling-assumption-first diagnostics, "
            "and GUI story/member/mode trace rows."
        ),
        "summary_line": (
            "Phase 4 commercial cross-solver readiness: BLOCKED | "
            f"reference_solvers={int(operator_contract.get('current_reference_solver_count', 0) or 0)}/"
            f"{int(operator_contract.get('required_reference_solver_count', 2) or 2)} | "
            f"evidence={pass_count}/{len(evidence_rows)}"
        ),
        "claim_boundary": (
            "This receipt summarizes commercial cross-solver readiness only. It does not "
            "include operator files, grant customer permission, record real operator checksums, "
            "ingest commercial outputs, run comparisons, prove solver correctness, or close "
            "Phase 4, Phase 3, or Developer Preview RC."
        ),
    }


def write_phase4_commercial_cross_solver_readiness_receipt(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    payload = build_phase4_commercial_cross_solver_readiness_receipt(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    return payload


def check_phase4_commercial_cross_solver_readiness_receipt(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    source_commit_sha: str | None = None,
) -> tuple[bool, str]:
    expected = build_phase4_commercial_cross_solver_readiness_receipt(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    if not resolved.exists():
        return False, f"phase4_commercial_cross_solver_readiness_missing:{out_path.as_posix()}"
    try:
        existing = _load_json(resolved)
    except Exception as exc:
        return False, f"phase4_commercial_cross_solver_readiness_unreadable:{out_path.as_posix()}:{exc.__class__.__name__}"
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "phase4_commercial_cross_solver_readiness_mismatch"
    return True, "phase4_commercial_cross_solver_readiness_consistent"


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
        ok, message = check_phase4_commercial_cross_solver_readiness_receipt(
            out_path=args.out,
            source_commit_sha=args.source_commit_sha,
        )
        print(f"Phase 4 commercial cross-solver readiness check: {message}")
        return 0 if ok else 1
    payload = write_phase4_commercial_cross_solver_readiness_receipt(
        out_path=args.out,
        source_commit_sha=args.source_commit_sha,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(payload["summary_line"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
