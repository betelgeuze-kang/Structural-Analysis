#!/usr/bin/env python3
"""Build a blocked Phase 3 IFC query/GUI task readiness receipt."""

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
DEFAULT_OUT = PRODUCTIZATION / "phase3_ifc_query_gui_readiness_receipt.json"
IFC_QUERY_GUI_INPUTS = [
    Path("src/structural_analysis/benchmark/acquisition.py"),
    Path("scripts/build_phase3_ifc_query_gui_readiness_receipt.py"),
    Path("scripts/build_phase3_ifc_source_license_receipt.py"),
]
WORKFLOW_STEPS = (
    {"id": "import", "label": "Import"},
    {"id": "model_health", "label": "Model Health"},
    {"id": "analysis_setup", "label": "Analysis Setup"},
    {"id": "run_monitor", "label": "Run & Monitor"},
    {"id": "compare_report", "label": "Compare & Report"},
)
REQUIRED_EVIDENCE = (
    {
        "id": "dataset_repository",
        "required": "Dataset repository URL or attached task-source package for the IFC query corpus.",
        "status": "missing",
        "contract_pass": False,
        "blocker": "dataset_repository_url_missing",
    },
    {
        "id": "per_file_license_review",
        "required": "Per-file license review for every IFC task source used by the GUI/query corpus.",
        "status": "missing",
        "contract_pass": False,
        "blocker": "per_file_license_review_pending",
    },
    {
        "id": "source_checksums",
        "required": "SHA256 for every acquired IFC source and task manifest.",
        "status": "missing",
        "contract_pass": False,
        "blocker": "checksum_missing",
    },
    {
        "id": "query_task_manifest",
        "required": "Machine-readable manifest of IFC files, query prompts, expected views, and GUI workflow tasks.",
        "status": "missing",
        "contract_pass": False,
        "blocker": "query_task_manifest_missing",
    },
    {
        "id": "expected_query_answers",
        "required": "Expected query answers with provenance and tolerance/classification rules.",
        "status": "missing",
        "contract_pass": False,
        "blocker": "query_expected_answers_missing",
    },
    {
        "id": "gui_task_runner",
        "required": "Repeatable GUI task runner command or browser automation command.",
        "status": "missing",
        "contract_pass": False,
        "blocker": "gui_task_runner_not_implemented",
    },
    {
        "id": "workflow_coverage",
        "required": "Task coverage for Import, Model Health, Analysis Setup, Run & Monitor, and Compare & Report.",
        "status": "missing",
        "contract_pass": False,
        "blocker": "gui_workflow_coverage_missing",
    },
    {
        "id": "task_execution_receipt",
        "required": "Per-task execution receipt with pass/fail, provenance, screenshots/logs, and artifact checksums.",
        "status": "missing",
        "contract_pass": False,
        "blocker": "ifc_query_gui_task_execution_missing",
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


def build_phase3_ifc_query_gui_readiness_receipt(
    *,
    repo_root: Path = ROOT,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    evidence_rows = [dict(row) for row in REQUIRED_EVIDENCE]
    blockers = sorted({str(row["blocker"]) for row in evidence_rows if str(row.get("blocker", ""))})
    return {
        "schema_version": "phase3-ifc-query-gui-readiness-receipt.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": source_commit_sha or git_head(repo_root),
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "input_checksums": input_checksums(IFC_QUERY_GUI_INPUTS, repo_root=repo_root),
        "source_id": "ifc_query_and_gui_public_corpus",
        "lanes": ["ifc-query-and-gui"],
        "status": "blocked",
        "contract_pass": False,
        "phase3_closure_claim": False,
        "developer_preview_release_candidate_claim": False,
        "fem_numerical_accuracy_claim": False,
        "query_gui_task_claim": False,
        "required_task_source_count": 1,
        "current_task_source_count": 0,
        "task_manifest_count": 0,
        "expected_answer_count": 0,
        "gui_task_execution_count": 0,
        "workflow_step_count": len(WORKFLOW_STEPS),
        "workflow_step_pass_count": 0,
        "required_workflow_steps": list(WORKFLOW_STEPS),
        "missing_workflow_steps": [str(step["id"]) for step in WORKFLOW_STEPS],
        "required_evidence_count": len(evidence_rows),
        "required_evidence_pass_count": 0,
        "required_evidence": evidence_rows,
        "task_execution_receipt_template": {
            "schema_version": "phase3-ifc-query-gui-task-execution-receipt.v1",
            "source_id": "ifc_query_and_gui_public_corpus",
            "task_id": "OPERATOR_ATTACHED_TASK_ID",
            "ifc_source_sha256": "OPERATOR_ATTACHED_IFC_SHA256",
            "task_manifest_sha256": "OPERATOR_ATTACHED_TASK_MANIFEST_SHA256",
            "runner_command": "OPERATOR_RECORDED_GUI_OR_BROWSER_COMMAND",
            "workflow_steps": list(WORKFLOW_STEPS),
            "query_answer_checks": "OPERATOR_ATTACHED_EXPECTED_ANSWER_RESULTS",
            "ui_artifacts": {
                "screenshots": [],
                "logs": [],
                "provenance_bundle": "OPERATOR_ATTACHED_PROVENANCE_BUNDLE",
            },
            "contract_pass": False,
        },
        "blocked_by": blockers,
        "blockers": blockers,
        "owner_action": (
            "Attach the IFC query/GUI dataset repository or task package, complete per-file "
            "license review and checksums, author expected query answers, implement the GUI "
            "task runner, and record execution receipts that cover the five-step workflow."
        ),
        "summary_line": (
            "Phase 3 IFC query/GUI readiness: BLOCKED | task_sources=0/1 | "
            f"workflow=0/{len(WORKFLOW_STEPS)} | evidence=0/{len(evidence_rows)}"
        ),
        "claim_boundary": (
            "This receipt records extraction, query-answer, and GUI workflow readiness. "
            "It is not FEM numerical accuracy evidence, does not execute IFC tasks, does "
            "not prove UX observation, and cannot close Phase 3 or Developer Preview RC by itself."
        ),
    }


def write_phase3_ifc_query_gui_readiness_receipt(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    payload = build_phase3_ifc_query_gui_readiness_receipt(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    return payload


def check_phase3_ifc_query_gui_readiness_receipt(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    source_commit_sha: str | None = None,
) -> tuple[bool, str]:
    expected = build_phase3_ifc_query_gui_readiness_receipt(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    if not resolved.exists():
        return False, f"phase3_ifc_query_gui_readiness_missing:{out_path.as_posix()}"
    try:
        existing = _load_json(resolved)
    except Exception as exc:
        return False, f"phase3_ifc_query_gui_readiness_unreadable:{out_path.as_posix()}:{exc.__class__.__name__}"
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "phase3_ifc_query_gui_readiness_mismatch"
    return True, "phase3_ifc_query_gui_readiness_consistent"


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
        ok, message = check_phase3_ifc_query_gui_readiness_receipt(
            out_path=args.out,
            source_commit_sha=args.source_commit_sha,
        )
        print(f"Phase 3 IFC query/GUI readiness check: {message}")
        return 0 if ok else 1
    payload = write_phase3_ifc_query_gui_readiness_receipt(
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
