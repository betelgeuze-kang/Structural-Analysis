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


def _platform_receipts(repo_root: Path) -> dict[str, dict[str, Any]]:
    return {
        "linux": _load_json(repo_root, LINUX_PLATFORM_RECEIPT),
        "windows": _load_json(repo_root, WINDOWS_PLATFORM_RECEIPT),
    }


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


def build_phase6_linux_windows_parity_status(*, repo_root: Path = ROOT) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    repro_bundle = _load_json(repo_root, PHASE3_REPRO_BUNDLE)
    git_clean_clone = _load_json(repo_root, PHASE3_GIT_CLEAN_CLONE)
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
    if missing_platforms:
        blockers.append("linux_windows_parity_receipts_missing")
    blockers.extend(
        blocker for row in platform_rows for blocker in row["blockers"] if row["blockers"]
    )
    if git_clean_clone.get("contract_pass") is not True:
        blockers.append("git_clean_clone_reproduction_not_passed")
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
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                PHASE3_REPRO_BUNDLE,
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
        "platform_receipt_template": platform_receipt_template,
        "parity_comparison_contract": parity_comparison_contract,
        "blocked_by": sorted(dict.fromkeys(blockers)),
        "required_commands": [
            "python3 scripts/build_phase3_benchmark_factory_artifacts.py --check",
            "python3 -m structural_analysis.benchmark.cli --manifest-out /tmp/phase3_seed_manifest.json --scorecard-out /tmp/phase3_seed_scorecard.json --summary-out /tmp/phase3_seed_runner_summary.json --fail-blocked",
            "python3 scripts/run_phase3_benchmark_factory_git_clean_clone_reproduction.py",
            "python3 scripts/run_phase3_benchmark_factory_clean_checkout_reproduction.py",
            "python3 scripts/build_phase6_linux_windows_parity_status.py --check",
        ],
        "comparison_requirements": [
            "same source_commit_sha or explicit commit mapping",
            "same expected_scorecard.case_count",
            "same expected_scorecard.pass_count",
            "same expected_scorecard.lane_case_counts",
            "same residual_formula",
            "stable manifest and scorecard SHA256 values",
            "working_tree_clean=true and local_dirty_inputs=[]",
        ],
        "owner_action": (
            "Attach passing Linux and Windows platform replay receipts from the same "
            "tracked source state, then rerun this parity status receipt before "
            "promoting the RC parity gate."
        ),
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
        ok, message = check_phase6_linux_windows_parity_status(out_path=args.out)
        print(f"Phase 6 Linux/Windows parity status check: {message}")
        return 0 if ok else 1
    payload = write_phase6_linux_windows_parity_status(out_path=args.out)
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(payload["summary_line"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
