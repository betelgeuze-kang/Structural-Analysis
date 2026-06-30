#!/usr/bin/env python3
"""Build a conservative Phase 3 large-model runner readiness receipt."""

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
DEFAULT_OUT = PRODUCTIZATION / "phase3_large_model_runner_readiness_receipt.json"
LARGE_RECEIPT_DIR = PRODUCTIZATION / "large_model_execution_receipts"
LARGE_RECEIPT_SCHEMA_VERSION = "phase3-large-model-execution-receipt.v1"
LARGE_MODEL_INPUTS = [
    LARGE_RECEIPT_DIR,
    Path("src/structural_analysis/benchmark/acquisition.py"),
    Path("scripts/build_phase3_large_model_runner_readiness_receipt.py"),
    Path("scripts/run_phase3_large_model_execution_receipt.py"),
]
RUNNER_SCRIPT = Path("scripts/run_phase3_large_model_execution_receipt.py")
RUNNER_COMMAND_TEMPLATE = (
    "python3 scripts/run_phase3_large_model_execution_receipt.py "
    "--model OPERATOR_ATTACHED_MODEL.json "
    "--source-id OPERATOR_ATTACHED_SOURCE_ID "
    "--case-id OPERATOR_ATTACHED_CASE_ID "
    "--source-sha256 OPERATOR_ATTACHED_SHA256 "
    "--scorecard-or-review OPERATOR_ATTACHED_SCORECARD_OR_REVIEW.json "
    "--out implementation/phase1/release_evidence/productization/"
    "large_model_execution_receipts/OPERATOR_ATTACHED_CASE_ID.execution_receipt.json "
    "--result-out implementation/phase1/release_evidence/productization/"
    "large_model_execution_receipts/OPERATOR_ATTACHED_CASE_ID.result.json "
    "--report-out implementation/phase1/release_evidence/productization/"
    "large_model_execution_receipts/OPERATOR_ATTACHED_CASE_ID.validation_report.json "
    "--analysis-type model_health --fail-blocked"
)
RESOURCE_ENVELOPE = {
    "default_timeout_seconds": 7200,
    "default_memory_limit_gb": 64.0,
    "artifact_retention_policy": "operator_attached_execution_receipt_result_and_validation_report",
    "execution_scope": "operator_workstation_or_scheduled_self_hosted_runner",
}
REQUIRED_EVIDENCE = (
    {
        "id": "authoritative_source",
        "required": "Verified upstream source URL or DOI for each selected large model.",
        "status": "missing",
        "blocker": "source_url_verification_pending",
    },
    {
        "id": "license_approval",
        "required": "License review that permits the intended local/workstation execution scope.",
        "status": "missing",
        "blocker": "license_review_pending",
    },
    {
        "id": "source_checksum",
        "required": "SHA256 for each acquired source file or archive.",
        "status": "missing",
        "blocker": "checksum_missing",
    },
    {
        "id": "reference_outputs",
        "required": "Reference displacement/reaction/member/modal outputs or approved REVIEW baseline.",
        "status": "missing",
        "blocker": "reference_outputs_missing",
    },
    {
        "id": "canonical_normalization",
        "required": "Canonical model normalization with units, coordinates, and mapping coverage.",
        "status": "missing",
        "blocker": "normalization_not_implemented",
    },
    {
        "id": "execution_receipt",
        "required": "Runtime, peak memory, exit status, crash status, and OOM status per large model.",
        "status": "missing",
        "blocker": "large_model_execution_receipt_missing",
    },
    {
        "id": "scorecard_or_review",
        "required": "Large-model scorecard pass or explicit approved REVIEW decision.",
        "status": "missing",
        "blocker": "large_model_scorecard_or_review_missing",
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


def _try_load_json(path: Path) -> dict[str, Any]:
    try:
        return _load_json(path)
    except Exception:
        return {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _receipt_files(repo_root: Path, receipt_dir: Path) -> list[Path]:
    resolved = receipt_dir if receipt_dir.is_absolute() else repo_root / receipt_dir
    if not resolved.exists():
        return []
    return sorted(path for path in resolved.glob("*.json") if path.is_file())


def _large_model_execution_receipt_inventory(repo_root: Path) -> dict[str, Any]:
    receipt_rows: list[dict[str, Any]] = []
    execution_case_ids: set[str] = set()
    crash_oom_free_case_ids: set[str] = set()
    scorecard_or_review_case_ids: set[str] = set()
    checksum_case_ids: set[str] = set()
    for path in _receipt_files(repo_root, LARGE_RECEIPT_DIR):
        payload = _try_load_json(path)
        relative_path = path.relative_to(repo_root).as_posix() if path.is_relative_to(repo_root) else path.as_posix()
        schema_pass = payload.get("schema_version") == LARGE_RECEIPT_SCHEMA_VERSION
        case_id = str(payload.get("case_id") or path.stem)
        blockers = [str(blocker) for blocker in _safe_list(payload.get("blockers")) if str(blocker)]
        contract_pass = bool(payload.get("contract_pass") is True)
        validation_pass = bool(payload.get("validation_contract_pass") is True)
        crashed = bool(payload.get("crashed") is True)
        oom = bool(payload.get("oom") is True)
        exit_code = payload.get("exit_code")
        source_sha256 = str(payload.get("source_sha256") or "")
        source_sha256_match = bool(payload.get("source_sha256_match") is True)
        scorecard_or_review_path = str(payload.get("scorecard_or_review_path") or "")
        execution_pass = bool(
            schema_pass
            and contract_pass
            and validation_pass
            and not crashed
            and not oom
            and exit_code == 0
        )
        crash_oom_free_pass = bool(execution_pass and not crashed and not oom)
        scorecard_or_review_pass = bool(execution_pass and scorecard_or_review_path)
        checksum_pass = bool(
            schema_pass
            and source_sha256.startswith("sha256:")
            and source_sha256_match
        )
        if execution_pass:
            execution_case_ids.add(case_id)
        if crash_oom_free_pass:
            crash_oom_free_case_ids.add(case_id)
        if scorecard_or_review_pass:
            scorecard_or_review_case_ids.add(case_id)
        if checksum_pass:
            checksum_case_ids.add(case_id)
        receipt_rows.append(
            {
                "path": relative_path,
                "schema_pass": schema_pass,
                "case_id": case_id,
                "contract_pass": contract_pass,
                "validation_contract_pass": validation_pass,
                "exit_code": exit_code,
                "crashed": crashed,
                "oom": oom,
                "source_sha256": source_sha256,
                "source_sha256_match": source_sha256_match,
                "scorecard_or_review_path": scorecard_or_review_path,
                "execution_pass": execution_pass,
                "crash_oom_free": crash_oom_free_pass,
                "scorecard_or_review": scorecard_or_review_pass,
                "checksum_pass": checksum_pass,
                "blockers": blockers,
            }
        )
    return {
        "schema_version": "phase3-large-model-execution-receipt-inventory.v1",
        "receipt_directory": LARGE_RECEIPT_DIR.as_posix(),
        "receipt_file_count": len(receipt_rows),
        "valid_execution_case_count": len(execution_case_ids),
        "crash_oom_free_execution_count": len(crash_oom_free_case_ids),
        "scorecard_or_review_count": len(scorecard_or_review_case_ids),
        "source_checksum_count": len(checksum_case_ids),
        "receipts": receipt_rows,
        "claim_boundary": (
            "Only operator-attached large execution receipts with the expected schema, "
            "contract_pass=true, validation_contract_pass=true, exit_code=0, and no "
            "crash/OOM are counted as large executions. This inventory does not create "
            "source authority, license, reference-output, or normalization evidence."
        ),
    }


def _counted_evidence_row(
    row: dict[str, Any],
    *,
    current: int,
    required: int,
    current_key: str,
    required_key: str,
) -> dict[str, Any]:
    enriched = dict(row)
    ready = current >= required
    enriched.update(
        {
            "status": "ready" if ready else ("partial" if current else "missing"),
            "contract_pass": ready,
            "blocker": "" if ready else row["blocker"],
            current_key: current,
            required_key: required,
        }
    )
    return enriched


def build_phase3_large_model_runner_readiness_receipt(
    *,
    repo_root: Path = ROOT,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    receipt_inventory = _large_model_execution_receipt_inventory(repo_root)
    required_large_model_count = 2
    execution_count = int(receipt_inventory["valid_execution_case_count"])
    crash_oom_free_count = int(receipt_inventory["crash_oom_free_execution_count"])
    scorecard_or_review_count = int(receipt_inventory["scorecard_or_review_count"])
    source_checksum_count = int(receipt_inventory["source_checksum_count"])
    runner_script = repo_root / RUNNER_SCRIPT
    runner_command_ready = runner_script.exists()
    evidence_rows: list[dict[str, Any]] = []
    for row in REQUIRED_EVIDENCE:
        if row["id"] == "source_checksum":
            evidence_rows.append(
                _counted_evidence_row(
                    row,
                    current=source_checksum_count,
                    required=required_large_model_count,
                    current_key="current_source_checksum_count",
                    required_key="required_source_checksum_count",
                )
            )
        elif row["id"] == "execution_receipt":
            evidence_rows.append(
                _counted_evidence_row(
                    row,
                    current=execution_count,
                    required=required_large_model_count,
                    current_key="current_large_model_execution_receipt_count",
                    required_key="required_large_model_execution_receipt_count",
                )
            )
        elif row["id"] == "scorecard_or_review":
            evidence_rows.append(
                _counted_evidence_row(
                    row,
                    current=scorecard_or_review_count,
                    required=required_large_model_count,
                    current_key="current_scorecard_or_review_count",
                    required_key="required_scorecard_or_review_count",
                )
            )
        else:
            evidence_rows.append(dict(row, contract_pass=False))
    evidence_rows.extend(
        [
            {
                "id": "runner_command",
                "required": (
                    "Repeatable large-model runner command with selected model inputs "
                    "and output paths."
                ),
                "status": "ready" if runner_command_ready else "missing",
                "contract_pass": runner_command_ready,
                "blocker": "" if runner_command_ready else "large_model_runner_not_implemented",
                "runner_command_template": RUNNER_COMMAND_TEMPLATE,
                "runner_script": RUNNER_SCRIPT.as_posix(),
            },
            {
                "id": "resource_envelope",
                "required": (
                    "Declared workstation/nightly CPU, memory, timeout, and artifact "
                    "retention limits."
                ),
                "status": "ready",
                "contract_pass": True,
                "blocker": "",
                "resource_envelope": RESOURCE_ENVELOPE,
            },
        ]
    )
    blockers = sorted(
        {
            str(row["blocker"])
            for row in evidence_rows
            if row.get("contract_pass") is not True and str(row.get("blocker", ""))
        }
    )
    required_evidence_pass_count = sum(1 for row in evidence_rows if row.get("contract_pass") is True)
    return {
        "schema_version": "phase3-large-model-runner-readiness-receipt.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": source_commit_sha or git_head(repo_root),
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "input_checksums": input_checksums(LARGE_MODEL_INPUTS, repo_root=repo_root),
        "source_id": "opensees_megatall_model_2_large",
        "lanes": ["opensees-megatall", "large-model-performance"],
        "status": "blocked",
        "contract_pass": False,
        "phase3_closure_claim": False,
        "developer_preview_release_candidate_claim": False,
        "large_model_execution_claim": False,
        "required_large_model_count": required_large_model_count,
        "current_large_model_execution_receipt_count": execution_count,
        "crash_oom_free_execution_count": crash_oom_free_count,
        "scorecard_or_review_count": scorecard_or_review_count,
        "source_checksum_count": source_checksum_count,
        "execution_receipt_inventory": receipt_inventory,
        "required_evidence_count": len(evidence_rows),
        "required_evidence_pass_count": required_evidence_pass_count,
        "required_evidence": evidence_rows,
        "runner_command_ready": runner_command_ready,
        "runner_command_template": RUNNER_COMMAND_TEMPLATE,
        "resource_envelope": RESOURCE_ENVELOPE,
        "runner_receipt_template": {
            "schema_version": "phase3-large-model-execution-receipt.v1",
            "source_id": "OPERATOR_ATTACHED_SOURCE_ID",
            "case_id": "OPERATOR_ATTACHED_CASE_ID",
            "source_sha256": "OPERATOR_ATTACHED_SHA256",
            "runner_command": "OPERATOR_RECORDED_COMMAND",
            "platform": "linux|windows|workstation",
            "cpu_model": "OPERATOR_RECORDED_CPU",
            "memory_limit_gb": "OPERATOR_RECORDED_MEMORY_LIMIT",
            "timeout_seconds": "OPERATOR_RECORDED_TIMEOUT",
            "exit_code": "OPERATOR_RECORDED_EXIT_CODE",
            "runtime_seconds": "OPERATOR_RECORDED_RUNTIME",
            "peak_memory_gb": "OPERATOR_RECORDED_PEAK_MEMORY",
            "crashed": False,
            "oom": False,
            "scorecard_or_review_path": "OPERATOR_ATTACHED_SCORECARD_OR_REVIEW",
            "contract_pass": False,
        },
        "blocked_by": blockers,
        "blockers": blockers,
        "owner_action": (
            "Acquire two licensed large OpenSees/reference models, attach checksums and "
            "reference outputs, normalize them into the canonical model, run the "
            "operator execution receipt command for each model, then attach crash/"
            "OOM-free execution receipts and scorecard or approved REVIEW evidence."
        ),
        "summary_line": (
            "Phase 3 large-model runner readiness: BLOCKED | executions=0/2 | "
            f"evidence={required_evidence_pass_count}/{len(evidence_rows)}"
        ),
        "claim_boundary": (
            "This receipt is a readiness contract for large-model execution evidence. "
            "The runner command and resource envelope are implemented, but this does "
            "not acquire sources, approve licenses, run mega-tall models, prove crash/"
            "OOM-free behavior, create scorecards, satisfy 2/2 large executions, or "
            "close Phase 3/Developer Preview RC."
        ),
    }


def write_phase3_large_model_runner_readiness_receipt(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    payload = build_phase3_large_model_runner_readiness_receipt(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    return payload


def check_phase3_large_model_runner_readiness_receipt(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    source_commit_sha: str | None = None,
) -> tuple[bool, str]:
    expected = build_phase3_large_model_runner_readiness_receipt(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    if not resolved.exists():
        return False, f"phase3_large_model_runner_readiness_missing:{out_path.as_posix()}"
    try:
        existing = _load_json(resolved)
    except Exception as exc:
        return False, f"phase3_large_model_runner_readiness_unreadable:{out_path.as_posix()}:{exc.__class__.__name__}"
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "phase3_large_model_runner_readiness_mismatch"
    return True, "phase3_large_model_runner_readiness_consistent"


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
        ok, message = check_phase3_large_model_runner_readiness_receipt(
            out_path=args.out,
            source_commit_sha=args.source_commit_sha,
        )
        print(f"Phase 3 large-model runner readiness check: {message}")
        return 0 if ok else 1
    payload = write_phase3_large_model_runner_readiness_receipt(
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
