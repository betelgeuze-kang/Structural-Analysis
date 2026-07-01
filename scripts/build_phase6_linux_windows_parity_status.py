#!/usr/bin/env python3
"""Build a conservative Phase 6 Linux/Windows parity status receipt."""

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
DEFAULT_OUT = PRODUCTIZATION / "phase6_linux_windows_parity_status.json"
PHASE3_REPRO_BUNDLE = PRODUCTIZATION / "phase3_benchmark_factory_seed_reproducibility_bundle.json"
PHASE3_CLEAN_CHECKOUT = PRODUCTIZATION / "phase3_benchmark_factory_seed_clean_checkout_reproduction.json"
PHASE3_GIT_CLEAN_CLONE = PRODUCTIZATION / "phase3_benchmark_factory_seed_git_clean_clone_reproduction.json"
LINUX_PLATFORM_RECEIPT = PRODUCTIZATION / "phase6_linux_platform_replay_receipt.json"
WINDOWS_PLATFORM_RECEIPT = PRODUCTIZATION / "phase6_windows_platform_replay_receipt.json"
SCHEMA_VERSION = "phase6-linux-windows-parity-status.v1"
PLATFORM_RECEIPT_SCHEMA = "phase6-linux-windows-platform-replay-receipt.v1"
REQUIRED_PLATFORMS = ["linux", "windows"]


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _strip_volatile(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_volatile(value)
            for key, value in payload.items()
            if key not in {"generated_at", "source_commit_sha"}
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


def _platform_receipts(repo_root: Path) -> dict[str, dict[str, Any]]:
    return {
        "linux": _load_json(repo_root, LINUX_PLATFORM_RECEIPT),
        "windows": _load_json(repo_root, WINDOWS_PLATFORM_RECEIPT),
    }


def _phase3_expectations(repro_bundle: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    expected_scorecard = (
        repro_bundle.get("expected_scorecard")
        if isinstance(repro_bundle.get("expected_scorecard"), dict)
        else {}
    )
    stable_artifact_checksums = (
        repro_bundle.get("stable_artifact_checksums")
        if isinstance(repro_bundle.get("stable_artifact_checksums"), dict)
        else {}
    )
    return expected_scorecard, stable_artifact_checksums


def _receipt_contract_pass(
    receipt: dict[str, Any],
    *,
    platform: str,
    expected_scorecard: dict[str, Any],
    stable_artifact_checksums: dict[str, Any],
) -> bool:
    return bool(
        receipt
        and receipt.get("schema_version") == PLATFORM_RECEIPT_SCHEMA
        and receipt.get("platform") == platform
        and receipt.get("contract_pass") is True
        and receipt.get("working_tree_clean") is True
        and receipt.get("local_dirty_inputs") == []
        and receipt.get("expected_scorecard") == expected_scorecard
        and receipt.get("stable_artifact_checksums") == stable_artifact_checksums
    )


def _parity_blocker_grouping_metadata(blockers: list[str]) -> dict[str, Any]:
    group_specs = [
        (
            "platform_receipt_presence",
            {
                "scope": "direct_linux_windows_parity_gate",
                "description": "Missing required Linux/Windows replay receipts.",
                "matches": (
                    "linux_windows_parity_receipts_missing",
                    "platform_replay_receipt_missing:",
                ),
            },
        ),
        (
            "platform_receipt_contract",
            {
                "scope": "direct_linux_windows_parity_gate",
                "description": "Present platform replay receipts that do not satisfy the contract.",
                "matches": ("platform_replay_receipt_not_passed:",),
            },
        ),
        (
            "git_clean_clone_spillover",
            {
                "scope": "tracked_elsewhere_clean_checkout_gate",
                "description": (
                    "Git clean-clone replay blocker tracked by the separate clean-checkout "
                    "RC final gate."
                ),
                "matches": ("git_clean_clone_reproduction_not_passed",),
            },
        ),
    ]
    groups: dict[str, dict[str, Any]] = {}
    classified: set[str] = set()
    for group_name, spec in group_specs:
        matches = tuple(str(match) for match in spec["matches"])
        grouped = [
            blocker
            for blocker in blockers
            if blocker not in classified
            and any(blocker == match or blocker.startswith(match) for match in matches)
        ]
        classified.update(grouped)
        groups[group_name] = {
            "scope": spec["scope"],
            "description": spec["description"],
            "blocker_count": len(grouped),
            "blockers": grouped,
        }
    unassigned_blockers = [blocker for blocker in blockers if blocker not in classified]
    return {
        "schema_version": "phase6-linux-windows-parity-blocker-groups.v1",
        "grouping_policy": (
            "Preserve every blocker while separating direct platform parity receipt "
            "gaps from git clean-clone spillover that is tracked by the separate "
            "clean-checkout RC gate."
        ),
        "blocker_count": len(blockers),
        "unassigned_blocker_count": len(unassigned_blockers),
        "unassigned_blockers": unassigned_blockers,
        "groups": groups,
    }


def _missing_platform_receipt_handoff(
    *,
    missing_platforms: list[str],
    receipt_paths: dict[str, str],
    platform_receipt_template: dict[str, Any],
    comparison_requirements: list[str],
) -> list[dict[str, Any]]:
    handoff: list[dict[str, Any]] = []
    for platform in missing_platforms:
        handoff.append(
            {
                "platform": platform,
                "receipt_path": receipt_paths[platform],
                "schema_version": PLATFORM_RECEIPT_SCHEMA,
                "status": "operator_receipt_required",
                "contract_pass": False,
                "required_source_commit_sha": platform_receipt_template.get(
                    "source_commit_sha"
                ),
                "required_replay_commands": platform_receipt_template.get(
                    "commands", []
                ),
                "required_receipt_fields": sorted(platform_receipt_template),
                "expected_scorecard": platform_receipt_template.get(
                    "expected_scorecard", {}
                ),
                "stable_artifact_checksums": platform_receipt_template.get(
                    "stable_artifact_checksums", {}
                ),
                "comparison_requirements": comparison_requirements,
                "validation_commands_after_attachment": [
                    "python3 scripts/build_phase6_linux_windows_parity_status.py --check",
                    "python3 scripts/build_developer_preview_rc_status.py --check",
                ],
                "forbidden_shortcuts": [
                    "do_not_copy_linux_receipt_as_windows_receipt",
                    "do_not_set_contract_pass_true_without_command_return_code_zero",
                    "do_not_omit_stable_artifact_checksums",
                    "do_not_attach_dirty_worktree_receipt",
                ],
                "claim_boundary": (
                    "This handoff is an operator checklist for the missing platform "
                    "receipt. It is not a platform replay receipt and cannot close "
                    "Linux/Windows parity until the receipt exists and passes the "
                    "parity status check."
                ),
            }
        )
    return handoff


def _validation_commands() -> list[str]:
    return [
        "python3 scripts/build_phase6_linux_windows_parity_status.py --check",
        "python3 scripts/build_developer_preview_rc_status.py --check",
        "python3 scripts/build_product_readiness_snapshot.py --check",
    ]


def _next_actions(*, missing_platforms: list[str], blocked_platforms: list[str], contract_pass: bool) -> list[str]:
    if contract_pass:
        return []
    actions: list[str] = []
    for platform in missing_platforms:
        actions.append(f"attach_{platform}_platform_replay_receipt")
    for platform in blocked_platforms:
        actions.append(f"repair_{platform}_platform_replay_receipt")
    actions.append("rerun_linux_windows_parity_and_dp_rc_checks")
    return actions


def _gate_unblock_plan(
    *,
    missing_platform_handoff: list[dict[str, Any]],
    blocked_platforms: list[str],
    receipt_paths: dict[str, str],
    validation_commands: list[str],
    contract_pass: bool,
) -> list[dict[str, Any]]:
    if contract_pass:
        return []
    plan: list[dict[str, Any]] = []
    for row in missing_platform_handoff:
        platform = str(row.get("platform", ""))
        plan.append(
            {
                "slot_id": f"attach_{platform}_platform_replay_receipt",
                "platform": platform,
                "required_artifact": str(row.get("receipt_path", "")),
                "schema_version": PLATFORM_RECEIPT_SCHEMA,
                "required_source_commit_sha": str(row.get("required_source_commit_sha", "")),
                "minimum_evidence": [
                    "receipt exists at the required artifact path",
                    "receipt platform matches the required platform",
                    "contract_pass=true only after replay commands return zero",
                    "working_tree_clean=true and local_dirty_inputs=[]",
                    "expected_scorecard and stable_artifact_checksums match the Phase 3 seed replay bundle",
                ],
                "required_replay_commands": row.get("required_replay_commands", []),
                "forbidden_shortcuts": row.get("forbidden_shortcuts", []),
                "validation_commands_after_attachment": row.get(
                    "validation_commands_after_attachment",
                    validation_commands,
                ),
            }
        )
    for platform in blocked_platforms:
        plan.append(
            {
                "slot_id": f"repair_{platform}_platform_replay_receipt",
                "platform": platform,
                "required_artifact": receipt_paths.get(platform, ""),
                "schema_version": PLATFORM_RECEIPT_SCHEMA,
                "minimum_evidence": [
                    "existing receipt schema_version, platform, replay commands, cleanliness, scorecard, and checksums all satisfy the parity status contract",
                    "platform_replay_receipt_not_passed blocker disappears from phase6_linux_windows_parity_status.json",
                ],
                "validation_commands_after_attachment": validation_commands,
            }
        )
    plan.append(
        {
            "slot_id": "rerun_linux_windows_parity_and_dp_rc_checks",
            "validation_commands": validation_commands,
            "minimum_evidence": [
                "phase6_linux_windows_parity_status.json contract_pass=true",
                "developer_preview_rc_status no longer blocks linux_windows_reproducibility_confirmed",
                "product_readiness_snapshot remains semantically consistent",
            ],
        }
    )
    return plan


def build_phase6_linux_platform_replay_receipt(*, repo_root: Path = ROOT) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    repro_bundle = _load_json(repo_root, PHASE3_REPRO_BUNDLE)
    clean_checkout = _load_json(repo_root, PHASE3_CLEAN_CHECKOUT)
    expected_scorecard, stable_artifact_checksums = _phase3_expectations(repro_bundle)
    expected_clean_checksums = (
        clean_checkout.get("expected_stable_artifact_checksums")
        if isinstance(clean_checkout.get("expected_stable_artifact_checksums"), dict)
        else {}
    )
    generated_clean_checksums = (
        clean_checkout.get("generated_stable_artifact_checksums")
        if isinstance(clean_checkout.get("generated_stable_artifact_checksums"), dict)
        else {}
    )
    source_commit_sha = str(repro_bundle.get("source_commit_sha", ""))
    clean_source_commit_sha = str(clean_checkout.get("source_commit_sha", ""))
    blockers = []
    if clean_checkout.get("contract_pass") is not True:
        blockers.append("phase3_clean_checkout_reproduction_not_passed")
    if clean_checkout.get("clean_checkout_executed") is not True:
        blockers.append("phase3_clean_checkout_replay_not_executed")
    if clean_checkout.get("clean_checkout_execution_mode") != "isolated_minimal_worktree_copy":
        blockers.append("phase3_clean_checkout_execution_mode_not_isolated_minimal_worktree_copy")
    if clean_source_commit_sha != source_commit_sha:
        blockers.append("phase3_clean_checkout_source_commit_mismatch")
    if not expected_scorecard or not stable_artifact_checksums:
        blockers.append("phase3_reproducibility_bundle_expectations_missing")
    if expected_clean_checksums != stable_artifact_checksums:
        blockers.append("phase3_clean_checkout_expected_checksum_mismatch")
    if generated_clean_checksums != stable_artifact_checksums:
        blockers.append("phase3_clean_checkout_generated_checksum_mismatch")
    contract_pass = not blockers
    return {
        "schema_version": PLATFORM_RECEIPT_SCHEMA,
        **release_evidence_metadata(
            input_paths=[
                PHASE3_REPRO_BUNDLE,
                PHASE3_CLEAN_CHECKOUT,
                Path("scripts/build_phase6_linux_windows_parity_status.py"),
            ],
            reused_evidence=True,
            reuse_policy="phase6_linux_platform_replay_receipt_from_phase3_local_clean_checkout",
            repo_root=repo_root,
        ),
        "platform": "linux",
        "os_name": "Linux",
        "os_version": "local_clean_checkout_replay_receipt",
        "python_version": "recorded_by_phase3_clean_checkout_command_results",
        "node_version": "not_required_for_phase3_seed_replay_contract",
        "source_commit_sha": source_commit_sha,
        "working_tree_clean": contract_pass,
        "working_tree_clean_scope": "isolated_minimal_worktree_copy",
        "local_dirty_inputs": [],
        "local_dirty_inputs_scope": "isolated_replay_checkout",
        "commands": list(clean_checkout.get("command_results", [])),
        "stable_artifact_checksums": stable_artifact_checksums,
        "expected_scorecard": expected_scorecard,
        "source_clean_checkout_receipt": PHASE3_CLEAN_CHECKOUT.as_posix(),
        "source_clean_checkout_status": str(clean_checkout.get("status", "missing")),
        "source_clean_checkout_contract_pass": clean_checkout.get("contract_pass") is True,
        "source_clean_checkout_execution_mode": str(
            clean_checkout.get("clean_checkout_execution_mode", "")
        ),
        "source_git_clean_clone_receipt": PHASE3_GIT_CLEAN_CLONE.as_posix(),
        "contract_pass": contract_pass,
        "blockers": blockers,
        "developer_preview_release_candidate_claim": False,
        "claim_boundary": (
            "This Linux platform receipt is derived only from the passing local isolated "
            "clean-checkout Phase 3 seed replay. It is not a Windows receipt, not a "
            "git-clean-clone pass, not Linux/Windows parity, and does not promote "
            "Developer Preview RC readiness."
        ),
    }


def build_phase6_linux_windows_parity_status(*, repo_root: Path = ROOT) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    repro_bundle = _load_json(repo_root, PHASE3_REPRO_BUNDLE)
    clean_checkout = _load_json(repo_root, PHASE3_CLEAN_CHECKOUT)
    git_clean_clone = _load_json(repo_root, PHASE3_GIT_CLEAN_CLONE)
    expected_scorecard, stable_artifact_checksums = _phase3_expectations(repro_bundle)
    receipts = _platform_receipts(repo_root)
    receipt_paths = {
        "linux": LINUX_PLATFORM_RECEIPT.as_posix(),
        "windows": WINDOWS_PLATFORM_RECEIPT.as_posix(),
    }
    platform_rows = []
    for platform in REQUIRED_PLATFORMS:
        receipt = receipts[platform]
        present = bool(receipt)
        contract_pass = _receipt_contract_pass(
            receipt,
            platform=platform,
            expected_scorecard=expected_scorecard,
            stable_artifact_checksums=stable_artifact_checksums,
        )
        platform_rows.append(
            {
                "platform": platform,
                "receipt_path": receipt_paths[platform],
                "receipt_present": present,
                "status": "ready" if contract_pass else "missing" if not present else "blocked",
                "contract_pass": contract_pass,
                "blockers": []
                if contract_pass
                else [
                    f"platform_replay_receipt_missing:{platform}"
                    if not present
                    else f"platform_replay_receipt_not_passed:{platform}"
                ],
            }
        )
    missing_platforms = [
        row["platform"] for row in platform_rows if row["receipt_present"] is not True
    ]
    blocked_platforms = [
        row["platform"]
        for row in platform_rows
        if row["receipt_present"] is True and row["contract_pass"] is not True
    ]
    parity_comparison_contract = {
        "required_platform_receipt_count": len(REQUIRED_PLATFORMS),
        "current_platform_receipt_count": len(REQUIRED_PLATFORMS) - len(missing_platforms),
        "required_platforms": REQUIRED_PLATFORMS,
        "missing_platforms": missing_platforms,
        "blocked_platforms": blocked_platforms,
        "checksum_keys": sorted(stable_artifact_checksums),
        "scorecard_identity_fields": [
            "case_count",
            "pass_count",
            "expected_output_comparison_count",
            "expected_output_comparison_pass_count",
            "lane_case_counts",
        ],
        "local_dirty_inputs_allowed": False,
        "contract_pass": all(row["contract_pass"] for row in platform_rows),
    }
    blockers = []
    if len(missing_platforms) == len(REQUIRED_PLATFORMS):
        blockers.append("linux_windows_parity_receipts_missing")
    blockers.extend(
        blocker for row in platform_rows for blocker in row["blockers"] if row["blockers"]
    )
    if git_clean_clone.get("contract_pass") is not True:
        blockers.append("git_clean_clone_reproduction_not_passed")
    blockers = sorted(dict.fromkeys(blockers))
    contract_pass = bool(not blockers and parity_comparison_contract["contract_pass"])
    platform_receipt_template = {
        "schema_version": PLATFORM_RECEIPT_SCHEMA,
        "platform": "linux|windows",
        "os_name": "OPERATOR_RECORDED_OS_NAME",
        "os_version": "OPERATOR_RECORDED_OS_VERSION",
        "python_version": "OPERATOR_RECORDED_PYTHON_VERSION",
        "node_version": "OPERATOR_RECORDED_NODE_VERSION",
        "source_commit_sha": str(repro_bundle.get("source_commit_sha", "")),
        "working_tree_clean": True,
        "local_dirty_inputs": [],
        "commands": [
            {
                "command": "python3 scripts/build_phase3_benchmark_factory_artifacts.py --check",
                "return_code": 0,
            },
            {
                "command": (
                    "python3 -m structural_analysis.benchmark.cli --manifest-out "
                    "/tmp/phase3_seed_manifest.json --scorecard-out "
                    "/tmp/phase3_seed_scorecard.json --summary-out "
                    "/tmp/phase3_seed_runner_summary.json --fail-blocked"
                ),
                "return_code": 0,
            },
        ],
        "stable_artifact_checksums": stable_artifact_checksums,
        "expected_scorecard": expected_scorecard,
        "contract_pass": False,
    }
    comparison_requirements = [
        "same source_commit_sha or explicit commit mapping",
        "same expected_scorecard.case_count",
        "same expected_scorecard.pass_count",
        "same expected_scorecard.lane_case_counts",
        "same residual_formula",
        "stable manifest and scorecard SHA256 values",
        "working_tree_clean=true and local_dirty_inputs=[]",
    ]
    missing_platform_handoff = _missing_platform_receipt_handoff(
        missing_platforms=missing_platforms,
        receipt_paths=receipt_paths,
        platform_receipt_template=platform_receipt_template,
        comparison_requirements=comparison_requirements,
    )
    validation_commands = _validation_commands()
    gate_unblock_plan = _gate_unblock_plan(
        missing_platform_handoff=missing_platform_handoff,
        blocked_platforms=blocked_platforms,
        receipt_paths=receipt_paths,
        validation_commands=validation_commands,
        contract_pass=contract_pass,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                PHASE3_REPRO_BUNDLE,
                PHASE3_CLEAN_CHECKOUT,
                PHASE3_GIT_CLEAN_CLONE,
                LINUX_PLATFORM_RECEIPT,
                WINDOWS_PLATFORM_RECEIPT,
                Path("scripts/build_phase6_linux_windows_parity_status.py"),
            ],
            reused_evidence=True,
            reuse_policy="phase6_parity_status_aggregates_phase3_seed_replay_expectations",
            repo_root=repo_root,
        ),
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "developer_preview_release_candidate_claim": contract_pass,
        "blockers": blockers,
        "required_platforms": REQUIRED_PLATFORMS,
        "platform_receipt_schema": PLATFORM_RECEIPT_SCHEMA,
        "platform_receipt_paths": receipt_paths,
        "platform_rows": platform_rows,
        "current_platform_receipts": [
            row["platform"] for row in platform_rows if row["receipt_present"] is True
        ],
        "missing_platform_receipts": missing_platforms,
        "expected_stable_artifact_checksums": stable_artifact_checksums,
        "expected_scorecard": expected_scorecard,
        "linux_local_replay_receipt_source": {
            "receipt": PHASE3_CLEAN_CHECKOUT.as_posix(),
            "status": str(clean_checkout.get("status", "missing")),
            "contract_pass": clean_checkout.get("contract_pass") is True,
            "execution_mode": str(clean_checkout.get("clean_checkout_execution_mode", "")),
            "claim_boundary": (
                "Linux local replay evidence is limited to the isolated minimal "
                "worktree-copy clean-checkout receipt and does not satisfy Windows "
                "parity or the git clean-clone gate."
            ),
        },
        "platform_receipt_template": platform_receipt_template,
        "missing_platform_receipt_handoff": missing_platform_handoff,
        "parity_comparison_contract": parity_comparison_contract,
        "blocked_by": blockers,
        "blocker_grouping_metadata": _parity_blocker_grouping_metadata(blockers),
        "gate_unblock_plan": gate_unblock_plan,
        "gate_unblock_plan_count": len(gate_unblock_plan),
        "next_actions": _next_actions(
            missing_platforms=missing_platforms,
            blocked_platforms=blocked_platforms,
            contract_pass=contract_pass,
        ),
        "operator_next_actions": gate_unblock_plan,
        "recommended_next_actions": gate_unblock_plan,
        "validation_commands": validation_commands,
        "required_commands": [
            "python3 scripts/build_phase3_benchmark_factory_artifacts.py --check",
            "python3 -m structural_analysis.benchmark.cli --manifest-out /tmp/phase3_seed_manifest.json --scorecard-out /tmp/phase3_seed_scorecard.json --summary-out /tmp/phase3_seed_runner_summary.json --fail-blocked",
            "python3 scripts/run_phase3_benchmark_factory_git_clean_clone_reproduction.py",
            "python3 scripts/run_phase3_benchmark_factory_clean_checkout_reproduction.py",
            "python3 scripts/build_phase6_linux_windows_parity_status.py --check",
        ],
        "comparison_requirements": comparison_requirements,
        "owner_action": (
            "Attach passing Linux and Windows platform replay receipts from the same "
            "tracked source state, then rerun this parity status receipt before "
            "promoting the RC parity gate."
        ),
        "summary": {
            "required_platform_receipt_count": len(REQUIRED_PLATFORMS),
            "current_platform_receipt_count": len(REQUIRED_PLATFORMS) - len(missing_platforms),
            "missing_platforms": missing_platforms,
            "blocked_platforms": blocked_platforms,
            "required_platforms": REQUIRED_PLATFORMS,
            "platform_receipt_schema": PLATFORM_RECEIPT_SCHEMA,
            "platform_receipt_paths": receipt_paths,
            "owner_action": (
                "Attach passing Linux and Windows platform replay receipts from the same "
                "tracked source state, then rerun this parity status receipt before "
                "promoting the RC parity gate."
            ),
            "developer_preview_release_candidate_claim": contract_pass,
        },
        "summary_line": (
            "Phase 6 Linux/Windows parity: "
            f"{'READY' if contract_pass else 'BLOCKED'} | receipts="
            f"{len(REQUIRED_PLATFORMS) - len(missing_platforms)}/{len(REQUIRED_PLATFORMS)} | "
            f"missing={','.join(missing_platforms) if missing_platforms else 'none'}"
        ),
        "claim_boundary": (
            "This receipt defines and checks the Linux/Windows platform replay evidence "
            "required for the Developer Preview RC parity gate. It does not prove parity "
            "until independent passing Linux and Windows receipts are attached, and it "
            "does not replace the separate git clean-clone reproduction gate."
        ),
    }


def write_phase6_linux_windows_parity_status(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
) -> dict[str, Any]:
    payload = build_phase6_linux_windows_parity_status(repo_root=repo_root)
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    return payload


def write_phase6_linux_platform_replay_receipt(
    *,
    repo_root: Path = ROOT,
    out_path: Path = LINUX_PLATFORM_RECEIPT,
) -> dict[str, Any]:
    payload = build_phase6_linux_platform_replay_receipt(repo_root=repo_root)
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    return payload


def check_phase6_linux_platform_replay_receipt(
    *,
    repo_root: Path = ROOT,
    out_path: Path = LINUX_PLATFORM_RECEIPT,
) -> tuple[bool, str]:
    expected = build_phase6_linux_platform_replay_receipt(repo_root=repo_root)
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    if not resolved.exists():
        return False, f"phase6_linux_platform_replay_receipt_missing:{out_path.as_posix()}"
    try:
        existing = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"phase6_linux_platform_replay_receipt_unreadable:{exc.__class__.__name__}"
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "phase6_linux_platform_replay_receipt_mismatch"
    return True, "phase6_linux_platform_replay_receipt_consistent"


def check_phase6_linux_windows_parity_status(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
) -> tuple[bool, str]:
    expected = build_phase6_linux_windows_parity_status(repo_root=repo_root)
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    if not resolved.exists():
        return False, f"phase6_linux_windows_parity_status_missing:{out_path.as_posix()}"
    try:
        existing = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"phase6_linux_windows_parity_status_unreadable:{exc.__class__.__name__}"
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "phase6_linux_windows_parity_status_mismatch"
    return True, "phase6_linux_windows_parity_status_consistent"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        linux_ok, linux_message = check_phase6_linux_platform_replay_receipt()
        if not linux_ok:
            print(f"Phase 6 Linux platform replay receipt check: {linux_message}")
            return 1
        ok, message = check_phase6_linux_windows_parity_status(out_path=args.out)
        print(f"Phase 6 Linux platform replay receipt check: {linux_message}")
        print(f"Phase 6 Linux/Windows parity status check: {message}")
        return 0 if ok else 1
    write_phase6_linux_platform_replay_receipt()
    payload = write_phase6_linux_windows_parity_status(out_path=args.out)
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(payload["summary_line"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
