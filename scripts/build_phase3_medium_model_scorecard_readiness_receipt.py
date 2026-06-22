#!/usr/bin/env python3
"""Build a blocked Phase 3 OpenSees medium scorecard readiness receipt."""

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
DEFAULT_OUT = PRODUCTIZATION / "phase3_medium_model_scorecard_readiness_receipt.json"
MEDIUM_MODEL_INPUTS = [
    Path("implementation/phase1/opensees_topology_report.json"),
    Path("implementation/phase1/release/benchmark_expansion/opensees_canonical_breadth_report.json"),
    Path("scripts/build_phase3_opensees_source_license_receipt.py"),
    Path("scripts/build_phase3_medium_model_scorecard_readiness_receipt.py"),
    Path("src/structural_analysis/benchmark/acquisition.py"),
]
REQUIRED_EVIDENCE = (
    {
        "id": "authoritative_source",
        "required": "Verified upstream source URL or DOI for each selected medium model.",
        "status": "missing",
        "contract_pass": False,
        "blocker": "source_url_verification_pending",
    },
    {
        "id": "license_approval",
        "required": "License review for local execution, redistribution boundary, and commercial-use boundary.",
        "status": "missing",
        "contract_pass": False,
        "blocker": "license_review_pending",
    },
    {
        "id": "local_candidate_parser_boundary",
        "required": "Local checksum/topology evidence recorded as parser-only, not benchmark pass evidence.",
        "status": "parser_only_ready",
        "contract_pass": True,
        "blocker": "",
    },
    {
        "id": "reference_outputs",
        "required": "Reference displacement/reaction/member/modal outputs or approved REVIEW baseline.",
        "status": "missing",
        "contract_pass": False,
        "blocker": "reference_outputs_missing",
    },
    {
        "id": "canonical_normalization",
        "required": "Canonical model normalization with units, coordinates, and mapping coverage.",
        "status": "missing",
        "contract_pass": False,
        "blocker": "normalization_not_implemented",
    },
    {
        "id": "runner_command",
        "required": "Repeatable medium-model scorecard runner command with selected model inputs and outputs.",
        "status": "missing",
        "contract_pass": False,
        "blocker": "opensees_medium_runner_command_missing",
    },
    {
        "id": "scorecard_execution",
        "required": "OpenSees medium scorecard execution retaining residual, increment, and convergence history.",
        "status": "missing",
        "contract_pass": False,
        "blocker": "opensees_medium_scorecard_execution_missing",
    },
    {
        "id": "pass_or_approved_review",
        "required": "Per-case PASS or explicit pre-approved REVIEW decision for selected medium models.",
        "status": "missing",
        "contract_pass": False,
        "blocker": "medium_model_pass_or_review_missing",
    },
)


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


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def build_phase3_medium_model_scorecard_readiness_receipt(
    *,
    repo_root: Path = ROOT,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    topology_report = _load_json(repo_root / "implementation/phase1/opensees_topology_report.json")
    canonical_report = _load_json(
        repo_root / "implementation/phase1/release/benchmark_expansion/opensees_canonical_breadth_report.json"
    )
    topology_metrics = _safe_dict(topology_report.get("metrics"))
    topology_source = _safe_dict(topology_report.get("source_provenance"))
    canonical_rows = [
        row
        for row in _safe_list(canonical_report.get("rows"))
        if isinstance(row, dict) and row.get("case_id") in {"SCBF16B", "SCBF16B_shell_beam_mix"}
    ]
    evidence_rows = [dict(row) for row in REQUIRED_EVIDENCE]
    blockers = sorted({str(row["blocker"]) for row in evidence_rows if str(row.get("blocker", ""))})
    evidence_pass_count = sum(1 for row in evidence_rows if row["contract_pass"] is True)
    return {
        "schema_version": "phase3-medium-model-scorecard-readiness-receipt.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": source_commit_sha or git_head(repo_root),
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "input_checksums": input_checksums(MEDIUM_MODEL_INPUTS, repo_root=repo_root),
        "source_id": "opensees_scbf16b_medium_candidate",
        "lanes": ["opensees-medium"],
        "status": "blocked",
        "contract_pass": False,
        "phase3_closure_claim": False,
        "developer_preview_release_candidate_claim": False,
        "medium_model_benchmark_pass_claim": False,
        "required_medium_model_count": 5,
        "current_medium_model_scorecard_count": 0,
        "pass_or_approved_review_count": 0,
        "local_candidate_artifact_count": len(canonical_rows),
        "local_topology_contract_pass": bool(topology_report.get("contract_pass")),
        "required_evidence_count": len(evidence_rows),
        "required_evidence_pass_count": evidence_pass_count,
        "required_evidence": evidence_rows,
        "local_parser_boundary": {
            "topology_receipt_path": "implementation/phase1/opensees_topology_report.json",
            "topology_contract_pass": bool(topology_report.get("contract_pass")),
            "source_path": topology_source.get("source_path"),
            "source_sha256": topology_source.get("source_sha256"),
            "node_count": topology_metrics.get("node_count"),
            "beam_element_count": topology_metrics.get("beam_element_count"),
            "shell_element_count": topology_metrics.get("shell_element_count"),
            "canonical_candidate_case_ids": sorted(str(row.get("case_id")) for row in canonical_rows),
            "claim_boundary": (
                "Local checksum and topology/parser evidence is retained only as parser input "
                "evidence. It is not reference-output ingest, normalization, medium scorecard "
                "execution, or PASS/REVIEW benchmark evidence."
            ),
        },
        "scorecard_receipt_template": {
            "schema_version": "phase3-medium-model-scorecard-receipt.v1",
            "source_id": "opensees_scbf16b_medium_candidate",
            "case_id": "OPERATOR_ATTACHED_CASE_ID",
            "source_sha256": "OPERATOR_ATTACHED_SHA256",
            "reference_output_sha256": "OPERATOR_ATTACHED_REFERENCE_OUTPUT_SHA256",
            "normalization_receipt": "OPERATOR_ATTACHED_NORMALIZATION_RECEIPT",
            "runner_command": "OPERATOR_RECORDED_COMMAND",
            "metrics": {
                "residual_formula": "F_internal_minus_F_external",
                "convergence_history_retained": True,
                "node_member_mapping_coverage": "OPERATOR_RECORDED_COVERAGE",
            },
            "decision": "PASS|APPROVED_REVIEW",
            "contract_pass": False,
        },
        "blocked_by": blockers,
        "blockers": blockers,
        "owner_action": (
            "Attach authoritative OpenSees medium source/license evidence, ingest reference "
            "outputs, normalize five selected medium models, run the medium scorecard, and "
            "record PASS or pre-approved REVIEW rows before promoting this RC gate."
        ),
        "summary_line": (
            "Phase 3 OpenSees medium scorecard readiness: BLOCKED | "
            f"scorecards=0/5 | evidence={evidence_pass_count}/{len(evidence_rows)}"
        ),
        "claim_boundary": (
            "This receipt records the evidence contract for OpenSees medium scorecards. "
            "It preserves local topology/parser evidence as parser-only and does not "
            "prove source authority, license approval, reference outputs, normalization, "
            "scorecard execution, PASS/REVIEW decisions, Phase 3 closure, or DP RC readiness."
        ),
    }


def write_phase3_medium_model_scorecard_readiness_receipt(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    payload = build_phase3_medium_model_scorecard_readiness_receipt(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    return payload


def check_phase3_medium_model_scorecard_readiness_receipt(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    source_commit_sha: str | None = None,
) -> tuple[bool, str]:
    expected = build_phase3_medium_model_scorecard_readiness_receipt(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    if not resolved.exists():
        return False, f"phase3_medium_model_scorecard_readiness_missing:{out_path.as_posix()}"
    try:
        existing = _load_json(resolved)
    except Exception as exc:
        return False, f"phase3_medium_model_scorecard_readiness_unreadable:{out_path.as_posix()}:{exc.__class__.__name__}"
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "phase3_medium_model_scorecard_readiness_mismatch"
    return True, "phase3_medium_model_scorecard_readiness_consistent"


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
        ok, message = check_phase3_medium_model_scorecard_readiness_receipt(
            out_path=args.out,
            source_commit_sha=args.source_commit_sha,
        )
        print(f"Phase 3 medium-model scorecard readiness check: {message}")
        return 0 if ok else 1
    payload = write_phase3_medium_model_scorecard_readiness_receipt(
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
