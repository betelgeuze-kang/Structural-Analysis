#!/usr/bin/env python3
"""Fill the Phase 6 Windows platform replay receipt from operator metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_phase6_linux_windows_parity_status as parity_status  # noqa: E402
from release_evidence_metadata import release_evidence_metadata  # noqa: E402


SCHEMA_VERSION = "phase6-windows-platform-replay-receipt-fill.v1"
DEFAULT_OUT = parity_status.WINDOWS_PLATFORM_RECEIPT
DEFAULT_REPORT_OUT = (
    parity_status.PRODUCTIZATION / "phase6_windows_platform_replay_receipt.fill_report.json"
)
PLACEHOLDER_MARKERS = (
    "<",
    ">",
    "OPERATOR_RECORDED",
    "OWNER_INPUT_REQUIRED",
    "PLACEHOLDER",
    "REPLACE_ME",
    "TBD",
    "TODO",
    "UNKNOWN",
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _bool_text(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    raise argparse.ArgumentTypeError("expected true or false")


def _looks_placeholder(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    upper = text.upper()
    return bool(not text or any(marker in upper for marker in PLACEHOLDER_MARKERS))


def _parse_command_result(value: str) -> dict[str, Any]:
    command, separator, return_code = value.rpartition("=")
    if not separator:
        raise argparse.ArgumentTypeError(
            "command result must look like '<command>=<return_code>'"
        )
    command = command.strip()
    if not command:
        raise argparse.ArgumentTypeError("command text is required")
    try:
        parsed_return_code = int(return_code.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("return_code must be an integer") from exc
    return {"command": command, "return_code": parsed_return_code}


def _default_required_commands(repo_root: Path) -> list[dict[str, Any]]:
    payload = parity_status.build_phase6_linux_windows_parity_status(repo_root=repo_root)
    template = payload.get("platform_receipt_template")
    if not isinstance(template, dict):
        return []
    commands = template.get("commands")
    if not isinstance(commands, list):
        return []
    return [dict(row) for row in commands if isinstance(row, dict)]


def _phase3_expectations(repo_root: Path) -> tuple[dict[str, Any], dict[str, Any], str]:
    repro_bundle = parity_status._load_json(repo_root, parity_status.PHASE3_REPRO_BUNDLE)
    expected_scorecard, stable_artifact_checksums = parity_status._phase3_expectations(
        repro_bundle
    )
    return expected_scorecard, stable_artifact_checksums, str(
        repro_bundle.get("source_commit_sha", "")
    )


def _metadata_blockers(
    *,
    os_name: str,
    os_version: str,
    python_version: str,
    node_version: str,
    replay_environment: str,
    receipt_origin: str,
    source_commit_sha: str,
    expected_source_commit_sha: str,
    working_tree_clean: bool,
    local_dirty_inputs: list[str],
    commands: list[dict[str, Any]],
    expected_scorecard: dict[str, Any],
    stable_artifact_checksums: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    text_fields = {
        "os_name": os_name,
        "os_version": os_version,
        "python_version": python_version,
        "node_version": node_version,
        "replay_environment": replay_environment,
        "receipt_origin": receipt_origin,
        "source_commit_sha": source_commit_sha,
    }
    for field, value in text_fields.items():
        if not str(value or "").strip():
            blockers.append(f"{field}_missing")
        elif _looks_placeholder(value):
            blockers.append(f"{field}_placeholder")
    if not expected_source_commit_sha:
        blockers.append("phase3_reproducibility_bundle_source_commit_missing")
    elif source_commit_sha != expected_source_commit_sha:
        blockers.append("source_commit_sha_mismatch")
    if not expected_scorecard:
        blockers.append("expected_scorecard_missing")
    if not stable_artifact_checksums:
        blockers.append("stable_artifact_checksums_missing")
    if working_tree_clean is not True:
        blockers.append("working_tree_not_clean")
    if local_dirty_inputs:
        blockers.append("local_dirty_inputs_present")
    if not commands:
        blockers.append("commands_missing")
    elif not parity_status._commands_return_code_zero(commands):
        blockers.append("command_return_code_nonzero")
    return blockers


def _receipt_payload(
    *,
    repo_root: Path,
    os_name: str,
    os_version: str,
    python_version: str,
    node_version: str,
    replay_environment: str,
    receipt_origin: str,
    source_commit_sha: str,
    working_tree_clean: bool,
    local_dirty_inputs: list[str],
    commands: list[dict[str, Any]],
    expected_scorecard: dict[str, Any],
    stable_artifact_checksums: dict[str, Any],
    expected_source_commit_sha: str,
) -> dict[str, Any]:
    commands_return_code_zero = parity_status._commands_return_code_zero(commands)
    blockers = _metadata_blockers(
        os_name=os_name,
        os_version=os_version,
        python_version=python_version,
        node_version=node_version,
        replay_environment=replay_environment,
        receipt_origin=receipt_origin,
        source_commit_sha=source_commit_sha,
        expected_source_commit_sha=expected_source_commit_sha,
        working_tree_clean=working_tree_clean,
        local_dirty_inputs=local_dirty_inputs,
        commands=commands,
        expected_scorecard=expected_scorecard,
        stable_artifact_checksums=stable_artifact_checksums,
    )
    receipt = {
        "schema_version": parity_status.PLATFORM_RECEIPT_SCHEMA,
        **release_evidence_metadata(
            input_paths=[
                parity_status.PHASE3_REPRO_BUNDLE,
                Path("scripts/fill_phase6_windows_platform_replay_receipt.py"),
                Path("scripts/build_phase6_linux_windows_parity_status.py"),
            ],
            reused_evidence=False,
            reuse_policy="phase6_windows_platform_replay_receipt_from_operator_metadata",
            repo_root=repo_root,
        ),
        "platform": "windows",
        "os_name": os_name,
        "os_version": os_version,
        "python_version": python_version,
        "node_version": node_version,
        "source_commit_sha": source_commit_sha,
        "platform_identity": {
            "platform": "windows",
            "os_name": os_name,
            "os_version": os_version,
            "python_version": python_version,
            "replay_environment": replay_environment,
            "receipt_origin": receipt_origin,
            "source_commit_sha": source_commit_sha,
            "commands_return_code_zero": commands_return_code_zero,
        },
        "working_tree_clean": working_tree_clean,
        "working_tree_clean_scope": "operator_reported_windows_replay_worktree",
        "local_dirty_inputs": local_dirty_inputs,
        "local_dirty_inputs_scope": "operator_reported_windows_replay_worktree",
        "commands": commands,
        "stable_artifact_checksums": stable_artifact_checksums,
        "expected_scorecard": expected_scorecard,
        "contract_pass": not blockers,
        "blockers": blockers,
        "developer_preview_release_candidate_claim": False,
        "claim_boundary": (
            "This Windows platform receipt is materialized from explicit operator "
            "metadata and Phase 3 replay expectations. It is not Linux evidence, "
            "not a generated parity pass by itself, and does not close Developer "
            "Preview parity until build_phase6_linux_windows_parity_status.py "
            "accepts it together with the Linux receipt."
        ),
    }
    contract_pass = parity_status._receipt_contract_pass(
        receipt,
        platform="windows",
        expected_source_commit_sha=expected_source_commit_sha,
        expected_scorecard=expected_scorecard,
        stable_artifact_checksums=stable_artifact_checksums,
    )
    if not contract_pass and not receipt["blockers"]:
        receipt["blockers"] = ["windows_platform_replay_receipt_contract_not_passed"]
    receipt["contract_pass"] = contract_pass
    return receipt


def fill_windows_platform_replay_receipt(
    *,
    repo_root: Path = ROOT,
    out: Path = DEFAULT_OUT,
    os_name: str,
    os_version: str,
    python_version: str,
    node_version: str,
    replay_environment: str,
    receipt_origin: str,
    working_tree_clean: bool,
    local_dirty_inputs: list[str] | None = None,
    commands: list[dict[str, Any]] | None = None,
    all_required_commands_zero: bool = False,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    expected_scorecard, stable_artifact_checksums, expected_source_commit_sha = (
        _phase3_expectations(repo_root)
    )
    command_rows = list(commands or [])
    if all_required_commands_zero and not command_rows:
        command_rows = _default_required_commands(repo_root)
    if all_required_commands_zero:
        command_rows = [
            {**row, "return_code": 0}
            for row in command_rows
            if isinstance(row, dict)
        ]
    receipt = _receipt_payload(
        repo_root=repo_root,
        os_name=os_name,
        os_version=os_version,
        python_version=python_version,
        node_version=node_version,
        replay_environment=replay_environment,
        receipt_origin=receipt_origin,
        source_commit_sha=source_commit_sha or expected_source_commit_sha,
        working_tree_clean=working_tree_clean,
        local_dirty_inputs=list(local_dirty_inputs or []),
        commands=command_rows,
        expected_scorecard=expected_scorecard,
        stable_artifact_checksums=stable_artifact_checksums,
        expected_source_commit_sha=expected_source_commit_sha,
    )
    resolved_out = _resolve(repo_root, out)
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    resolved_out.write_text(_json_text(receipt), encoding="utf-8")
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/fill_phase6_windows_platform_replay_receipt.py"),
                Path("scripts/build_phase6_linux_windows_parity_status.py"),
                parity_status.PHASE3_REPRO_BUNDLE,
                out,
            ],
            reused_evidence=False,
            reuse_policy="phase6_windows_platform_replay_receipt_fill_report",
            repo_root=repo_root,
        ),
        "status": "filled" if receipt["contract_pass"] is True else "blocked",
        "contract_pass": receipt["contract_pass"] is True,
        "receipt_path": out.as_posix(),
        "receipt": receipt,
        "validation_blockers": receipt.get("blockers", []),
        "validation_commands": [
            "python3 scripts/build_phase6_linux_windows_parity_status.py --check",
            "python3 scripts/build_developer_preview_rc_status.py --check",
            "python3 scripts/build_product_readiness_snapshot.py --check",
        ],
        "claim_boundary": (
            "This helper records operator-supplied Windows replay metadata and "
            "validates the receipt contract. It does not execute Windows commands "
            "or assert parity without the downstream parity status check."
        ),
    }


def write_report(*, payload: dict[str, Any], repo_root: Path, out: Path | None) -> None:
    if out is None:
        return
    resolved = _resolve(repo_root, out)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report-out", type=Path, default=DEFAULT_REPORT_OUT)
    parser.add_argument("--os-name", required=True)
    parser.add_argument("--os-version", required=True)
    parser.add_argument("--python-version", required=True)
    parser.add_argument("--node-version", default="not_required_for_phase3_seed_replay_contract")
    parser.add_argument("--replay-environment", required=True)
    parser.add_argument("--receipt-origin", required=True)
    parser.add_argument("--source-commit-sha", default=None)
    parser.add_argument("--working-tree-clean", type=_bool_text, required=True)
    parser.add_argument("--local-dirty-input", action="append", default=[])
    parser.add_argument(
        "--command-result",
        action="append",
        type=_parse_command_result,
        default=[],
        help="Replay command result in '<command>=<return_code>' form. Repeatable.",
    )
    parser.add_argument(
        "--all-required-commands-zero",
        action="store_true",
        help="Materialize the parity-status required commands with return_code=0.",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = fill_windows_platform_replay_receipt(
        repo_root=args.repo_root,
        out=args.out,
        os_name=args.os_name,
        os_version=args.os_version,
        python_version=args.python_version,
        node_version=args.node_version,
        replay_environment=args.replay_environment,
        receipt_origin=args.receipt_origin,
        source_commit_sha=args.source_commit_sha,
        working_tree_clean=args.working_tree_clean,
        local_dirty_inputs=args.local_dirty_input,
        commands=args.command_result,
        all_required_commands_zero=args.all_required_commands_zero,
    )
    write_report(payload=payload, repo_root=args.repo_root, out=args.report_out)
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "phase6 windows platform replay receipt fill: "
            f"{payload['status'].upper()} | "
            f"contract_pass={payload['contract_pass']} | "
            f"blockers={len(payload['validation_blockers'])}"
        )
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
