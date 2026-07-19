#!/usr/bin/env python3
"""Build or check the Engine v2 HIP FGMRES Stage 4 evidence status."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

from jsonschema import Draft202012Validator

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import run_engine_v2_hip_fgmres_device_receipt as device_runner  # noqa: E402
import run_engine_v2_hip_fgmres_recurrence as local_runner  # noqa: E402
from release_evidence_metadata import git_head, input_checksums  # noqa: E402
from structural_analysis.engine_v2_backends.hip_fgmres_recurrence import (  # noqa: E402
    fgmres_recurrence_receipt_hash,
)


SCHEMA_VERSION = "engine-v2-hip-fgmres-stage4-status.v1"
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/hip_fgmres_stage4_status_v1.schema.json"
)
DEFAULT_OUT = Path(
    "implementation/phase1/release_evidence/productization/"
    "engine_v2_hip_fgmres_stage4_status.json"
)
DEFAULT_LOCAL_LEGACY = local_runner.DEFAULT_OUT
DEFAULT_GFX1030_DEVICE = Path(
    "implementation/phase1/release_evidence/productization/"
    "engine_v2_hip_fgmres_gfx1030_device_receipt.json"
)
DEFAULT_GFX1100_DEVICE = Path(
    "implementation/phase1/release_evidence/productization/"
    "engine_v2_hip_fgmres_gfx1100_device_receipt.json"
)
CLAIM_BOUNDARY = (
    "Stage 4 is ready only when direct, clean-source, wheel-bound, Ed25519-signed "
    "gfx1030 and independent gfx1100 device receipts reproduce the same current "
    "source set, commit, wheel, fixture, numerical recurrence, and checkpoint "
    "contract. The attached local gfx1030 device receipt is actual hardware and "
    "wheel-bound evidence, but its dirty source and unsigned state prevent it "
    "from closing the cross-device gate. The legacy local receipt remains valid "
    "hardware evidence but is not wheel-bound. Stage 4 readiness does not imply a "
    "production-scale recurrence, production preconditioner effectiveness, or "
    "performance claim."
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _display_path(path: Path) -> str:
    return path.as_posix()


def _fixture_identity_hash(identity: dict[str, Any]) -> str:
    return fgmres_recurrence_receipt_hash(identity)


def _status_hash(payload: dict[str, Any]) -> str:
    return device_runner._sha256_bytes(
        device_runner._canonical_bytes(
            {key: value for key, value in payload.items() if key != "status_hash"}
        )
    )


def _missing_device_row(expected_architecture: str, path: Path) -> dict[str, Any]:
    return {
        "expected_architecture": expected_architecture,
        "path": _display_path(path),
        "attached": False,
        "receipt_hash": None,
        "gcn_arch_name": None,
        "actual_hardware": False,
        "numerical_parity": False,
        "checkpoint_resume_parity": False,
        "evidence_origin": None,
        "source_commit_sha": None,
        "source_set_hash": None,
        "exact_source_commit": False,
        "wheel_sha256": None,
        "wheel_bound_at_execution": False,
        "fixture_identity_hash": None,
        "signature_verified": False,
        "signer_id": None,
        "public_key_sha256": None,
        "organization_id": None,
        "runner_id": None,
        "execution_location": None,
        "independent_from_local_gfx1030": False,
    }


def _device_row(
    expected_architecture: str,
    path: Path,
    *,
    repo_root: Path,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    resolved = _resolve(repo_root, path)
    if not resolved.is_file():
        return _missing_device_row(expected_architecture, path), None
    receipt = _read_json(resolved)
    device_runner.validate_device_receipt(
        receipt,
        repo_root=repo_root,
        require_current_sources=True,
    )
    evidence = receipt["evidence_payload"]
    source = evidence["source"]
    wheel = evidence["wheel"]
    hardware = evidence["hardware_execution"]
    signature = receipt["signature"]
    context = evidence["operator_context"]
    claims = receipt["claims"]
    row = {
        "expected_architecture": expected_architecture,
        "path": _display_path(path),
        "attached": True,
        "receipt_hash": receipt["receipt_hash"],
        "gcn_arch_name": hardware["gcn_arch_name"],
        "actual_hardware": claims["actual_hardware_execution"],
        "numerical_parity": claims["numerical_parity"],
        "checkpoint_resume_parity": claims["checkpoint_resume_parity"],
        "evidence_origin": hardware["evidence_origin"],
        "source_commit_sha": source["repository_commit_sha"],
        "source_set_hash": source["source_set_hash"],
        "exact_source_commit": claims["exact_source_commit"],
        "wheel_sha256": wheel["sha256"],
        "wheel_bound_at_execution": claims[
            "wheel_identity_bound_at_execution"
        ],
        "fixture_identity_hash": _fixture_identity_hash(
            evidence["fixture_identity"]
        ),
        "signature_verified": signature["state"] == "verified",
        "signer_id": signature["signer_id"],
        "public_key_sha256": signature["public_key_sha256"],
        "organization_id": context["organization_id"],
        "runner_id": context["runner_id"],
        "execution_location": context["execution_location"],
        "independent_from_local_gfx1030": context[
            "independent_from_local_gfx1030"
        ],
    }
    return row, receipt


def _local_legacy_row(
    path: Path,
    *,
    repo_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    resolved = _resolve(repo_root, path)
    receipt = _read_json(resolved)
    local_runner.validate_receipt(
        receipt,
        repo_root=repo_root,
        require_current_sources=True,
    )
    hardware = receipt["hardware_execution"]
    row = {
        "path": _display_path(path),
        "receipt_hash": receipt["receipt_hash"],
        "actual_hardware": hardware["actual_hardware"],
        "contract_pass": receipt["contract_pass"],
        "gcn_arch_name": hardware["gcn_arch_name"],
        "source_commit_sha": receipt["source"]["repository_base_commit_sha"],
        "worktree_clean": receipt["source"]["worktree_clean"],
        "fixture_hash": receipt["fixture"]["fixture_hash"],
        "preconditioner_contract_hash": receipt["fixture"][
            "preconditioner_contract_hash"
        ],
        "binary_sha256": hardware["binary_sha256"],
        "signed_receipt": False,
        "wheel_identity_bound_at_execution": False,
        "cross_device_eligible": False,
    }
    return row, receipt


def _identity_gates(
    local: dict[str, Any],
    external: dict[str, Any],
) -> dict[str, bool]:
    attached_pair = local["attached"] and external["attached"]
    architecture_pair = bool(
        attached_pair
        and local["gcn_arch_name"] == "gfx1030"
        and external["gcn_arch_name"] == "gfx1100"
    )
    actual_pair = bool(
        attached_pair and local["actual_hardware"] and external["actual_hardware"]
    )
    numerical_pair = bool(
        attached_pair and local["numerical_parity"] and external["numerical_parity"]
    )
    checkpoint_pair = bool(
        attached_pair
        and local["checkpoint_resume_parity"]
        and external["checkpoint_resume_parity"]
    )
    direct_pair = bool(
        attached_pair
        and local["evidence_origin"] == "direct_device_runner"
        and external["evidence_origin"] == "direct_device_runner"
    )
    clean_pair = bool(
        attached_pair
        and local["exact_source_commit"]
        and external["exact_source_commit"]
    )
    same_commit = bool(
        attached_pair
        and local["source_commit_sha"] == external["source_commit_sha"]
    )
    same_source_set = bool(
        attached_pair and local["source_set_hash"] == external["source_set_hash"]
    )
    wheel_bound_pair = bool(
        attached_pair
        and local["wheel_bound_at_execution"]
        and external["wheel_bound_at_execution"]
    )
    same_wheel = bool(
        attached_pair and local["wheel_sha256"] == external["wheel_sha256"]
    )
    same_fixture = bool(
        attached_pair
        and local["fixture_identity_hash"] == external["fixture_identity_hash"]
    )
    signed_pair = bool(
        attached_pair
        and local["signature_verified"]
        and external["signature_verified"]
    )
    distinct_signers = bool(
        signed_pair
        and local["signer_id"] != external["signer_id"]
        and local["public_key_sha256"] != external["public_key_sha256"]
    )
    independent_org = bool(
        attached_pair
        and local["organization_id"] != external["organization_id"]
    )
    independent_runner = bool(
        attached_pair and local["runner_id"] != external["runner_id"]
    )
    independence_attested = bool(
        attached_pair and external["independent_from_local_gfx1030"]
    )
    gates = {
        "architecture_pair_exact": architecture_pair,
        "actual_hardware_pair": actual_pair,
        "numerical_parity_pair": numerical_pair,
        "checkpoint_resume_pair": checkpoint_pair,
        "direct_device_runner_pair": direct_pair,
        "clean_exact_source_pair": clean_pair,
        "same_source_commit": same_commit,
        "same_source_set": same_source_set,
        "wheel_bound_at_execution_pair": wheel_bound_pair,
        "same_wheel_hash": same_wheel,
        "same_fixture_identity": same_fixture,
        "signed_receipt_pair": signed_pair,
        "distinct_signer_pair": distinct_signers,
        "independent_organization_pair": independent_org,
        "independent_runner_pair": independent_runner,
        "gfx1100_independence_attested": independence_attested,
    }
    gates["stage4_contract_pass"] = all(gates.values())
    return gates


def _blockers(
    local: dict[str, Any],
    external: dict[str, Any],
    gates: dict[str, bool],
) -> list[str]:
    blockers: list[str] = []
    if not local["attached"]:
        blockers.append("signed_clean_gfx1030_device_receipt_not_attached")
    if not external["attached"]:
        blockers.append("independent_gfx1100_device_receipt_not_attached")
    mapping = [
        ("architecture_pair_exact", "gfx1030_gfx1100_architecture_pair_not_verified"),
        ("actual_hardware_pair", "actual_hardware_pair_not_verified"),
        ("numerical_parity_pair", "cross_device_numerical_parity_not_verified"),
        ("checkpoint_resume_pair", "cross_device_checkpoint_parity_not_verified"),
        ("direct_device_runner_pair", "direct_device_runner_pair_not_verified"),
        ("clean_exact_source_pair", "clean_exact_source_pair_not_verified"),
        ("same_source_commit", "same_source_commit_not_verified"),
        ("same_source_set", "same_source_set_not_verified"),
        (
            "wheel_bound_at_execution_pair",
            "wheel_bound_at_execution_pair_not_verified",
        ),
        ("same_wheel_hash", "same_wheel_hash_not_verified"),
        ("same_fixture_identity", "same_fixture_identity_not_verified"),
        ("signed_receipt_pair", "signed_receipt_pair_not_verified"),
        ("distinct_signer_pair", "distinct_signer_pair_not_verified"),
        (
            "independent_organization_pair",
            "independent_organization_pair_not_verified",
        ),
        ("independent_runner_pair", "independent_runner_pair_not_verified"),
        (
            "gfx1100_independence_attested",
            "gfx1100_independence_attestation_not_verified",
        ),
    ]
    blockers.extend(message for key, message in mapping if not gates[key])
    blockers.extend(
        [
            "production_scale_multi_block_operator_not_verified",
            "production_scale_preconditioner_effectiveness_not_verified",
            "model_size_performance_sweep_not_executed",
        ]
    )
    return blockers


def _input_paths(
    *,
    repo_root: Path,
    local_legacy_path: Path,
    gfx1030_device_path: Path,
    gfx1100_device_path: Path,
) -> list[Path]:
    paths = [
        local_legacy_path,
        SCHEMA_PATH,
        Path("scripts/build_engine_v2_hip_fgmres_stage4_status.py"),
        Path("scripts/run_engine_v2_hip_fgmres_device_receipt.py"),
        device_runner.SCHEMA_PATH,
        Path("tests/test_engine_v2_hip_fgmres_stage4_status.py"),
        Path("tests/test_engine_v2_hip_fgmres_device_receipt.py"),
    ]
    for candidate in (gfx1030_device_path, gfx1100_device_path):
        if _resolve(repo_root, candidate).is_file():
            paths.append(candidate)
    return paths


def build_stage4_status(
    *,
    repo_root: Path = ROOT,
    local_legacy_path: Path = DEFAULT_LOCAL_LEGACY,
    gfx1030_device_path: Path = DEFAULT_GFX1030_DEVICE,
    gfx1100_device_path: Path = DEFAULT_GFX1100_DEVICE,
    generated_at: str | None = None,
) -> dict[str, Any]:
    legacy_row, _legacy = _local_legacy_row(
        local_legacy_path,
        repo_root=repo_root,
    )
    local_row, _local = _device_row(
        "gfx1030", gfx1030_device_path, repo_root=repo_root
    )
    external_row, _external = _device_row(
        "gfx1100", gfx1100_device_path, repo_root=repo_root
    )
    gates = _identity_gates(local_row, external_row)
    stage4_ready = gates["stage4_contract_pass"]
    paths = _input_paths(
        repo_root=repo_root,
        local_legacy_path=local_legacy_path,
        gfx1030_device_path=gfx1030_device_path,
        gfx1100_device_path=gfx1100_device_path,
    )
    provisional = {
        "schema_version": SCHEMA_VERSION,
        "status_hash": "sha256:" + "0" * 64,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "status": "ready" if stage4_ready else "partial",
        "contract_pass": True,
        "source": {
            "repository_commit_sha": git_head(repo_root),
            "worktree_clean": local_runner._worktree_clean(repo_root),
            "input_checksums": input_checksums(paths, repo_root=repo_root),
        },
        "local_legacy_gfx1030": legacy_row,
        "device_receipts": {
            "gfx1030": local_row,
            "gfx1100": external_row,
        },
        "identity_gates": gates,
        "claims": {
            "local_gfx1030_actual_hardware": True,
            "independent_gfx1100_actual_hardware": bool(
                gates["architecture_pair_exact"]
                and gates["actual_hardware_pair"]
                and gates["gfx1100_independence_attested"]
                and gates["independent_organization_pair"]
            ),
            "same_source_commit_cross_device": gates["same_source_commit"],
            "same_wheel_hash_cross_device": gates["same_wheel_hash"],
            "same_fixture_cross_device": gates["same_fixture_identity"],
            "signed_cross_device_receipts": gates["signed_receipt_pair"],
            "stage4_cross_device_evidence": stage4_ready,
            "production_recurrence": False,
            "performance": False,
        },
        "blockers_remaining": _blockers(local_row, external_row, gates),
        "claim_boundary": CLAIM_BOUNDARY,
    }
    provisional["status_hash"] = _status_hash(provisional)
    _validate_schema_and_hash(provisional, repo_root=repo_root)
    return provisional


def _validate_schema_and_hash(
    payload: dict[str, Any],
    *,
    repo_root: Path,
) -> None:
    schema = _read_json(repo_root / SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    if payload["status_hash"] != _status_hash(payload):
        raise ValueError("engine_v2_hip_stage4_status_hash_mismatch")


def validate_stage4_status(
    payload: dict[str, Any],
    *,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    _validate_schema_and_hash(payload, repo_root=repo_root)
    expected = build_stage4_status(
        repo_root=repo_root,
        local_legacy_path=Path(payload["local_legacy_gfx1030"]["path"]),
        gfx1030_device_path=Path(payload["device_receipts"]["gfx1030"]["path"]),
        gfx1100_device_path=Path(payload["device_receipts"]["gfx1100"]["path"]),
        generated_at=payload["generated_at"],
    )
    if payload != expected:
        raise ValueError("engine_v2_hip_stage4_status_stale")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--local-legacy", type=Path, default=DEFAULT_LOCAL_LEGACY)
    parser.add_argument(
        "--gfx1030-device", type=Path, default=DEFAULT_GFX1030_DEVICE
    )
    parser.add_argument(
        "--gfx1100-device", type=Path, default=DEFAULT_GFX1100_DEVICE
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    out = _resolve(ROOT, args.out)
    if args.check:
        validate_stage4_status(_read_json(out), repo_root=ROOT)
        print("engine_v2_hip_fgmres_stage4_status_consistent")
        return 0
    status = build_stage4_status(
        repo_root=ROOT,
        local_legacy_path=args.local_legacy,
        gfx1030_device_path=args.gfx1030_device,
        gfx1100_device_path=args.gfx1100_device,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_json_text(status), encoding="utf-8")
    print(
        f"{status['status']} | local_gfx1030=True | "
        f"stage4={status['claims']['stage4_cross_device_evidence']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
