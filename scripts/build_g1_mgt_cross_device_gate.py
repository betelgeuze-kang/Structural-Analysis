#!/usr/bin/env python3
"""Verify the signed same-source gfx1030/gfx1100 production-MGT pair."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "scripts", ROOT / "src", ROOT / "implementation/phase1"):
    sys.path.insert(0, str(candidate))

from build_g1_mgt_hardware_envelope import (  # noqa: E402
    DEFAULT_OUT as DEFAULT_GFX1030,
    validate as validate_envelope,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_GFX1100 = PRODUCTIZATION / "g1_mgt_gfx1100_hardware_envelope.json"
DEFAULT_OUT = PRODUCTIZATION / "g1_mgt_cross_device_gate.json"
SCHEMA = Path("src/structural_analysis/schemas/g1_mgt_cross_device_gate_v1.schema.json")
VERSION = "g1-mgt-production-hip-cross-device-gate.v1"
CLAIM_BOUNDARY = (
    "This v1 gate replays cryptographically signed, same-source and same-wheel "
    "production-MGT gfx1030/gfx1100 envelopes and compares their terminal, "
    "material, checkpoint, and KPI contracts. It cannot close G1 until separate "
    "trusted hardware-identity receipts, observed CPU fallback zero, terminal "
    "ResultIR/DiagnosticIR parity, and an end-to-end performance sweep are bound. "
    "It does not replace the separately gated N1 CPU mathematical closure or "
    "promote unsupported actual-MGT nonlinear material parameters."
)
PROMOTION_REQUIREMENTS = (
    "trusted_hardware_identity_receipts_bound",
    "cpu_fallback_zero_attested",
    "terminal_resultir_diagnosticir_parity_bound",
    "end_to_end_performance_sweep_bound",
)


def _resolve(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("g1_cross_device_json_object_required")
    return value


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _receipt_hash(payload: dict[str, Any]) -> str:
    body = {key: value for key, value in payload.items() if key != "receipt_hash"}
    return "sha256:" + hashlib.sha256(_canonical_bytes(body)).hexdigest()


def compare_envelopes(
    gfx1030: dict[str, Any], gfx1100: dict[str, Any]
) -> dict[str, bool]:
    """Compare already-validated envelopes without weakening either validator."""
    left = gfx1030["evidence_payload"]
    right = gfx1100["evidence_payload"]
    left_runner = left["runner_attestation"]
    right_runner = right["runner_attestation"]
    left_signature = gfx1030["signature"]
    right_signature = gfx1100["signature"]
    left_hardware = left["hardware"]
    right_hardware = right["hardware"]
    return {
        "architectures_exact": (
            left_hardware["gcn_arch_name"] == "gfx1030"
            and right_hardware["gcn_arch_name"] == "gfx1100"
        ),
        "both_signatures_verified": (
            left_signature["state"] == "verified"
            and right_signature["state"] == "verified"
            and gfx1030["claims"]["signed_receipt"] is True
            and gfx1100["claims"]["signed_receipt"] is True
        ),
        "same_repository_commit": (
            left["source"]["repository_commit_sha"]
            == right["source"]["repository_commit_sha"]
        ),
        "same_source_set": (
            left["source"]["source_set_hash"] == right["source"]["source_set_hash"]
            and left["source"]["input_checksums"] == right["source"]["input_checksums"]
        ),
        "same_wheel": (left_hardware["wheel_sha256"] == right_hardware["wheel_sha256"]),
        "same_dual_target_binaries": (
            left_hardware["dual_target_binary_sha256"]
            == right_hardware["dual_target_binary_sha256"]
        ),
        "executed_binary_matches_architecture": (
            left_hardware["executed_binary_sha256"]
            == left_hardware["dual_target_binary_sha256"]["gfx1030"]
            and right_hardware["executed_binary_sha256"]
            == right_hardware["dual_target_binary_sha256"]["gfx1100"]
        ),
        "terminal_contract_exact": left["terminal"] == right["terminal"],
        "material_contract_exact": left["material"] == right["material"],
        "distinct_organizations": (
            left_runner["organization_id"] != right_runner["organization_id"]
        ),
        "distinct_runners": left_runner["runner_id"] != right_runner["runner_id"],
        "distinct_execution_locations": (
            left_runner["execution_location"] != right_runner["execution_location"]
        ),
        "distinct_signers": (
            left_signature["signer_id"] != right_signature["signer_id"]
            and left_signature["public_key_sha256"]
            != right_signature["public_key_sha256"]
        ),
        "gfx1100_independence_attested": (
            right_runner["independent_from_local_gfx1030"] is True
            and gfx1100["claims"]["independent_gfx1100_hardware"] is True
        ),
        "production_contracts_true": all(
            envelope["claims"][name] is True
            for envelope in (gfx1030, gfx1100)
            for name in (
                "actual_production_mgt_hardware",
                "exact_source_commit",
                "wheel_and_binary_bound_at_execution",
                "terminal_numerical_contract",
                "checkpoint_exact_restart",
                "source_family_material_lifecycle",
            )
        ),
        "kpis_recorded": all(
            all(
                name in envelope["evidence_payload"]["performance"]
                for name in (
                    "h2d_bytes",
                    "d2h_bytes",
                    "mid_iteration_d2h_transfer_count",
                    "peak_device_allocation_bytes",
                    "checkpoint_serialization_overhead_seconds",
                    "device_lifecycle_wall_time_ms",
                    "speedup_vs_cpu",
                )
            )
            for envelope in (gfx1030, gfx1100)
        ),
    }


def pair_ready(comparisons: dict[str, bool]) -> bool:
    """Return true only when every signed cross-device comparison passes."""
    return bool(comparisons) and all(comparisons.values())


def build(
    *,
    root: Path = ROOT,
    gfx1030_path: Path = DEFAULT_GFX1030,
    gfx1100_path: Path = DEFAULT_GFX1100,
    generated_at: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    local = validate_envelope(
        _read(_resolve(root, gfx1030_path)),
        root=root,
        require_current_sources=True,
    )
    if not (
        local["evidence_payload"]["hardware"]["gcn_arch_name"] == "gfx1030"
        and local["claims"]["actual_gfx1030_hardware"] is True
    ):
        raise ValueError("g1_cross_device_gfx1030_source_required")
    external_target = _resolve(root, gfx1100_path)
    external: dict[str, Any] | None = None
    if external_target.is_file():
        external = validate_envelope(
            _read(external_target), root=root, require_current_sources=True
        )
    comparisons = (
        compare_envelopes(local, external)
        if external is not None
        else {
            name: False
            for name in (
                "architectures_exact",
                "both_signatures_verified",
                "same_repository_commit",
                "same_source_set",
                "same_wheel",
                "same_dual_target_binaries",
                "executed_binary_matches_architecture",
                "terminal_contract_exact",
                "material_contract_exact",
                "distinct_organizations",
                "distinct_runners",
                "distinct_execution_locations",
                "distinct_signers",
                "gfx1100_independence_attested",
                "production_contracts_true",
                "kpis_recorded",
            )
        }
    )
    pair_is_consistent = external is not None and pair_ready(comparisons)
    promotion_requirements = {name: False for name in PROMOTION_REQUIREMENTS}
    g1_ready = bool(pair_is_consistent and all(promotion_requirements.values()))
    blockers = [name for name, passed in comparisons.items() if not passed]
    blockers.extend(
        name for name, passed in promotion_requirements.items() if not passed
    )
    payload: dict[str, Any] = {
        "schema_version": VERSION,
        "receipt_hash": "",
        "generated_at": generated_at
        or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "partial",
        "contract_pass": True,
        "sources": {
            "gfx1030": {
                "path": gfx1030_path.as_posix(),
                "receipt_hash": local["receipt_hash"],
            },
            "gfx1100": (
                {
                    "path": gfx1100_path.as_posix(),
                    "receipt_hash": external["receipt_hash"],
                }
                if external is not None
                else None
            ),
        },
        "comparisons": comparisons,
        "promotion_requirements": promotion_requirements,
        "claims": {
            "actual_gfx1030_hardware": True,
            "actual_gfx1100_hardware": bool(
                external is not None and external["claims"]["actual_gfx1100_hardware"]
            ),
            "cryptographically_consistent_cross_device_pair": pair_is_consistent,
            "signed_independent_cross_device_pair": bool(
                pair_is_consistent
                and promotion_requirements["trusted_hardware_identity_receipts_bound"]
            ),
            "terminal_envelope_contract_parity": bool(
                pair_is_consistent and comparisons["terminal_contract_exact"]
            ),
            "g1_closure": g1_ready,
        },
        "blockers_remaining": blockers,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    payload["receipt_hash"] = _receipt_hash(payload)
    return payload


def validate(payload: dict[str, Any], *, root: Path = ROOT) -> dict[str, Any]:
    schema = _read(_resolve(root, SCHEMA))
    errors = sorted(Draft202012Validator(schema).iter_errors(payload), key=str)
    if errors:
        raise ValueError(f"g1_cross_device_schema_invalid:{errors[0].message}")
    if payload["receipt_hash"] != _receipt_hash(payload):
        raise ValueError("g1_cross_device_receipt_hash_mismatch")
    expected = build(
        root=root,
        gfx1030_path=Path(payload["sources"]["gfx1030"]["path"]),
        gfx1100_path=(
            Path(payload["sources"]["gfx1100"]["path"])
            if payload["sources"]["gfx1100"] is not None
            else DEFAULT_GFX1100
        ),
        generated_at=payload["generated_at"],
    )
    if payload != expected:
        raise ValueError("g1_cross_device_replay_mismatch")
    return payload


def write(*, out: Path = DEFAULT_OUT, **kwargs: Any) -> dict[str, Any]:
    root = Path(kwargs.get("root", ROOT)).resolve()
    payload = build(**kwargs)
    target = _resolve(root, out)
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return validate(payload, root=root)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gfx1030", type=Path, default=DEFAULT_GFX1030)
    parser.add_argument("--gfx1100", type=Path, default=DEFAULT_GFX1100)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        validate(_read(_resolve(ROOT, args.out)), root=ROOT)
        print("g1_mgt_cross_device_gate_consistent")
        return 0
    payload = write(
        out=args.out,
        root=ROOT,
        gfx1030_path=args.gfx1030,
        gfx1100_path=args.gfx1100,
    )
    print(
        f"{payload['status']} | signed_pair="
        f"{payload['claims']['signed_independent_cross_device_pair']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
