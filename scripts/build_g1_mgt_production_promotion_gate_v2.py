#!/usr/bin/env python3
"""Build the fail-closed G1 production-worker promotion gate v2."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys
from typing import Any, Sequence

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "scripts", ROOT / "src", ROOT / "implementation/phase1"):
    sys.path.insert(0, str(candidate))

import build_g1_mgt_hardware_envelope as envelope_gate  # noqa: E402
import build_g1_mgt_production_performance_sweep_v2 as performance_gate  # noqa: E402
import build_g1_mgt_production_worker_receipt_v2 as worker_gate  # noqa: E402
import build_g1_mgt_terminal_checkpoint_bundle_v2 as checkpoint_gate  # noqa: E402
from g1_receipt_provenance import (  # noqa: E402
    build_provenance,
    validate_provenance,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "g1_mgt_production_promotion_gate_v2.json"
SCHEMA = Path(
    "src/structural_analysis/schemas/g1_mgt_production_promotion_gate_v2.schema.json"
)
VERSION = "g1-mgt-production-promotion-gate.v2"
TRUST_POLICY_VERSION = "g1-mgt-hardware-trust-policy.v2"
FALLBACK_VERSION = "g1-mgt-cpu-fallback-zero-receipt.v2"
REQUIREMENT_NAMES = (
    "trusted_hardware_identity_pair",
    "cpu_fallback_zero",
    "terminal_resultir_diagnosticir_parity",
    "cross_device_production_performance_sweep",
    "nonlinear_material_family_breadth",
)
SOURCE_PATHS = (
    Path("scripts/build_g1_mgt_production_promotion_gate_v2.py"),
    Path("scripts/g1_receipt_provenance.py"),
    SCHEMA,
    Path("tests/test_build_g1_mgt_production_promotion_gate_v2.py"),
)


def _resolve(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"g1_promotion_duplicate_json_key:{key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"g1_promotion_nonfinite_json_constant:{value}")


def _check_finite(value: Any, path: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"g1_promotion_nonfinite_number:{path}")
    if isinstance(value, dict):
        for key, item in value.items():
            _check_finite(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _check_finite(item, f"{path}[{index}]")


def secure_read_json(path: Path, *, allowed_root: Path) -> dict[str, Any]:
    """Read a regular in-tree JSON file with duplicate/nonfinite rejection."""

    allowed = allowed_root.resolve()
    absolute = path if path.is_absolute() else allowed / path
    lexical = Path(os.path.abspath(absolute))
    try:
        relative = lexical.relative_to(allowed)
    except ValueError as error:
        raise ValueError("g1_promotion_input_outside_allowed_root") from error
    current = allowed
    for component in relative.parts:
        current = current / component
        if current.is_symlink():
            raise ValueError("g1_promotion_symlink_input_forbidden")
    if not lexical.is_file():
        raise ValueError("g1_promotion_regular_file_required")
    payload = json.loads(
        lexical.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_pairs,
        parse_constant=_reject_constant,
    )
    if not isinstance(payload, dict):
        raise ValueError("g1_promotion_json_object_required")
    _check_finite(payload)
    return payload


def _hash(payload: dict[str, Any]) -> str:
    return canonical_hash(
        {key: value for key, value in payload.items() if key != "receipt_hash"}
    )


def _is_hash(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _is_commit(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(character in "0123456789abcdef" for character in value)
    )


def _time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("g1_promotion_timestamp_invalid") from error
    if parsed.tzinfo is None:
        raise ValueError("g1_promotion_timestamp_timezone_required")
    return parsed


def validate_trust_policy(
    policy: dict[str, Any], *, expected_hash: str | None, now: datetime
) -> dict[str, Any]:
    _check_finite(policy)
    required = {
        "schema_version",
        "receipt_hash",
        "issued_at",
        "expires_at",
        "identities",
    }
    if set(policy) != required or policy.get("schema_version") != TRUST_POLICY_VERSION:
        raise ValueError("g1_promotion_trust_policy_shape_invalid")
    if policy["receipt_hash"] != _hash(policy):
        raise ValueError("g1_promotion_trust_policy_hash_mismatch")
    if expected_hash is None or expected_hash != policy["receipt_hash"]:
        raise ValueError("g1_promotion_trust_policy_not_externally_pinned")
    issued = _time(policy["issued_at"])
    expires = _time(policy["expires_at"])
    if now.tzinfo is None:
        raise ValueError("g1_promotion_trust_policy_now_timezone_required")
    if not issued <= now <= expires:
        raise ValueError("g1_promotion_trust_policy_expired_or_not_yet_valid")
    identities = policy["identities"]
    if not isinstance(identities, list) or len(identities) < 2:
        raise ValueError("g1_promotion_trust_policy_identity_pair_required")
    required_identity = {
        "architecture",
        "signer_id",
        "public_key_sha256",
        "organization_id",
        "runner_id",
        "execution_location",
        "source_commit_sha",
        "wheel_sha256",
        "revoked",
    }
    keys: set[str] = set()
    for identity in identities:
        if not isinstance(identity, dict) or set(identity) != required_identity:
            raise ValueError("g1_promotion_trust_identity_shape_invalid")
        key = identity["public_key_sha256"]
        if key in keys:
            raise ValueError("g1_promotion_trust_identity_duplicate_key")
        keys.add(key)
        if identity["architecture"] not in ("gfx1030", "gfx1100"):
            raise ValueError("g1_promotion_trust_identity_architecture_invalid")
        for name in (
            "signer_id",
            "organization_id",
            "runner_id",
            "execution_location",
        ):
            if not isinstance(identity[name], str) or not identity[name]:
                raise ValueError(f"g1_promotion_trust_identity_{name}_invalid")
        if not _is_hash(identity["public_key_sha256"]):
            raise ValueError("g1_promotion_trust_identity_public_key_invalid")
        if not _is_commit(identity["source_commit_sha"]):
            raise ValueError("g1_promotion_trust_identity_source_commit_invalid")
        if not _is_hash(identity["wheel_sha256"]):
            raise ValueError("g1_promotion_trust_identity_wheel_invalid")
        if type(identity["revoked"]) is not bool:
            raise ValueError("g1_promotion_trust_identity_revocation_invalid")
    return policy


def _identity_from_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    evidence = envelope["evidence_payload"]
    signature = envelope["signature"]
    runner = evidence["runner_attestation"]
    hardware = evidence["hardware"]
    source = evidence["source"]
    return {
        "architecture": hardware["gcn_arch_name"],
        "signer_id": signature["signer_id"],
        "public_key_sha256": signature["public_key_sha256"],
        "organization_id": runner["organization_id"],
        "runner_id": runner["runner_id"],
        "execution_location": runner["execution_location"],
        "source_commit_sha": source["repository_commit_sha"],
        "wheel_sha256": hardware["wheel_sha256"],
    }


def validate_trusted_identity_pair(
    envelopes: Sequence[dict[str, Any]], policy: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    if len(envelopes) != 2:
        raise ValueError("g1_promotion_two_hardware_envelopes_required")
    observed = tuple(_identity_from_envelope(envelope) for envelope in envelopes)
    if {row["architecture"] for row in observed} != {"gfx1030", "gfx1100"}:
        raise ValueError("g1_promotion_cross_architecture_pair_required")
    for envelope, identity in zip(envelopes, observed, strict=True):
        if not (
            envelope["signature"]["state"] == "verified"
            and envelope["claims"]["signed_receipt"] is True
        ):
            raise ValueError("g1_promotion_signed_envelope_required")
        matches = [
            row
            for row in policy["identities"]
            if row["public_key_sha256"] == identity["public_key_sha256"]
        ]
        if not matches:
            raise ValueError("g1_promotion_unknown_signer_key")
        trusted = matches[0]
        if trusted["revoked"]:
            raise ValueError("g1_promotion_revoked_signer_key")
        expected = {key: trusted[key] for key in identity}
        if identity != expected:
            raise ValueError("g1_promotion_self_declared_identity_mismatch")
    for field in (
        "organization_id",
        "runner_id",
        "execution_location",
        "signer_id",
        "public_key_sha256",
    ):
        if observed[0][field] == observed[1][field]:
            raise ValueError(f"g1_promotion_identity_collision:{field}")
    if observed[0]["source_commit_sha"] != observed[1]["source_commit_sha"]:
        raise ValueError("g1_promotion_source_epoch_drift")
    if observed[0]["wheel_sha256"] != observed[1]["wheel_sha256"]:
        raise ValueError("g1_promotion_wheel_drift")
    return observed


def validate_fallback_zero_receipt(
    receipt: dict[str, Any], workers: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    _check_finite(receipt)
    required = {
        "schema_version",
        "receipt_hash",
        "source_commit_sha",
        "wheel_sha256",
        "workload_hash",
        "checkpoint_sha256",
        "architectures",
    }
    if set(receipt) != required or receipt.get("schema_version") != FALLBACK_VERSION:
        raise ValueError("g1_promotion_fallback_receipt_shape_invalid")
    if receipt["receipt_hash"] != _hash(receipt):
        raise ValueError("g1_promotion_fallback_receipt_hash_mismatch")
    if not _is_commit(receipt["source_commit_sha"]):
        raise ValueError("g1_promotion_fallback_source_commit_invalid")
    for name in ("wheel_sha256", "workload_hash", "checkpoint_sha256"):
        if not _is_hash(receipt[name]):
            raise ValueError(f"g1_promotion_fallback_{name}_invalid")
    architectures = receipt["architectures"]
    if architectures != {"gfx1030": 0, "gfx1100": 0}:
        raise ValueError("g1_promotion_cpu_fallback_nonzero_or_incomplete")
    sources = {worker["source"]["repository_commit_sha"] for worker in workers}
    wheels = {worker["source"]["wheel_sha256"] for worker in workers}
    if sources != {receipt["source_commit_sha"]}:
        raise ValueError("g1_promotion_fallback_source_epoch_drift")
    if wheels != {receipt["wheel_sha256"]}:
        raise ValueError("g1_promotion_fallback_wheel_drift")
    return receipt


def validate_cross_receipt_bindings(
    *,
    performance: dict[str, Any],
    fallback: dict[str, Any],
    checkpoint: dict[str, Any],
    workers: Sequence[dict[str, Any]],
) -> None:
    """Bind fallback and repeated-performance evidence to the worker pair."""

    if fallback["checkpoint_sha256"] != checkpoint["checkpoint"]["file_sha256"]:
        raise ValueError("g1_promotion_fallback_checkpoint_drift")
    identity = performance["identity"]
    if not performance["claims"]["cross_device_production_performance_sweep"]:
        return
    source_commits = {worker["source"]["repository_commit_sha"] for worker in workers}
    wheel_hashes = {worker["source"]["wheel_sha256"] for worker in workers}
    parity_digests = {worker["terminal_parity"]["parity_digest"] for worker in workers}
    if source_commits != {identity["source_commit_sha"]}:
        raise ValueError("g1_promotion_performance_source_epoch_drift")
    if wheel_hashes != {identity["wheel_sha256"]}:
        raise ValueError("g1_promotion_performance_wheel_drift")
    if identity["workload_hash"] != fallback["workload_hash"]:
        raise ValueError("g1_promotion_performance_workload_drift")
    if identity["checkpoint_sha256"] != fallback["checkpoint_sha256"]:
        raise ValueError("g1_promotion_performance_checkpoint_drift")
    if parity_digests != {identity["terminal_parity_digest"]}:
        raise ValueError("g1_promotion_performance_terminal_parity_drift")


def create_hashed_receipt(**values: Any) -> dict[str, Any]:
    payload = {"receipt_hash": "", **values}
    payload["receipt_hash"] = _hash(payload)
    return payload


def build(
    *,
    root: Path = ROOT,
    gfx1030_worker: dict[str, Any] | None = None,
    gfx1100_worker: dict[str, Any] | None = None,
    gfx1030_envelope: dict[str, Any] | None = None,
    gfx1100_envelope: dict[str, Any] | None = None,
    trust_policy: dict[str, Any] | None = None,
    expected_trust_policy_hash: str | None = None,
    fallback_zero_receipt: dict[str, Any] | None = None,
    performance_receipt: dict[str, Any] | None = None,
    generated_at: str | None = None,
    provenance_source_commit_sha: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    for name, value in (
        ("gfx1030_worker", gfx1030_worker),
        ("gfx1100_worker", gfx1100_worker),
        ("gfx1030_envelope", gfx1030_envelope),
        ("gfx1100_envelope", gfx1100_envelope),
        ("trust_policy", trust_policy),
        ("fallback_zero_receipt", fallback_zero_receipt),
        ("performance_receipt", performance_receipt),
    ):
        if value is not None:
            _check_finite(value, f"$.{name}")
    local_worker = gfx1030_worker or worker_gate.validate(
        secure_read_json(worker_gate.DEFAULT_OUT, allowed_root=root),
        root=root,
        current=True,
    )
    if local_worker["source"]["device_architecture"] != "gfx1030":
        raise ValueError("g1_promotion_local_worker_must_be_gfx1030")
    checkpoint = checkpoint_gate.validate(
        secure_read_json(checkpoint_gate.DEFAULT_OUT, allowed_root=root),
        root=root,
        current=True,
    )
    performance = performance_receipt or performance_gate.validate(
        secure_read_json(performance_gate.DEFAULT_OUT, allowed_root=root), root=root
    )
    local_envelope = gfx1030_envelope or envelope_gate.validate(
        secure_read_json(envelope_gate.DEFAULT_OUT, allowed_root=root),
        root=root,
        require_current_sources=True,
    )
    if local_envelope["evidence_payload"]["hardware"]["gcn_arch_name"] != "gfx1030":
        raise ValueError("g1_promotion_local_envelope_must_be_gfx1030")

    requirements = {name: False for name in REQUIREMENT_NAMES}
    sources: dict[str, Any] = {
        "gfx1030_worker_receipt_hash": local_worker["receipt_hash"],
        "gfx1100_worker_receipt_hash": None,
        "checkpoint_bundle_hash": checkpoint["receipt_hash"],
        "performance_receipt_hash": performance["receipt_hash"],
        "trust_policy_hash": None,
        "fallback_zero_receipt_hash": None,
    }
    optional_complete = all(
        value is not None
        for value in (
            gfx1100_worker,
            gfx1100_envelope,
            trust_policy,
            expected_trust_policy_hash,
            fallback_zero_receipt,
        )
    )
    if optional_complete:
        remote_worker = worker_gate.validate(gfx1100_worker, root=root)
        if remote_worker["source"]["device_architecture"] != "gfx1100":
            raise ValueError("g1_promotion_remote_worker_must_be_gfx1100")
        remote_envelope = envelope_gate.validate(
            gfx1100_envelope, root=root, require_current_sources=False
        )
        policy = validate_trust_policy(
            trust_policy,
            expected_hash=expected_trust_policy_hash,
            now=_time(generated_at or datetime.now(timezone.utc).isoformat()),
        )
        identities = validate_trusted_identity_pair(
            (local_envelope, remote_envelope), policy
        )
        workers = (local_worker, remote_worker)
        if {worker["source"]["repository_commit_sha"] for worker in workers} != {
            identities[0]["source_commit_sha"]
        }:
            raise ValueError("g1_promotion_worker_envelope_source_epoch_drift")
        if {worker["source"]["wheel_sha256"] for worker in workers} != {
            identities[0]["wheel_sha256"]
        }:
            raise ValueError("g1_promotion_worker_envelope_wheel_drift")
        result_digests = {
            worker["terminal_parity"]["parity_digest"] for worker in workers
        }
        diagnostic_digests = {
            worker["terminal_parity"]["diagnostic_parity_digest"] for worker in workers
        }
        if len(result_digests) != 1 or len(diagnostic_digests) != 1:
            raise ValueError("g1_promotion_terminal_result_diagnostic_parity_drift")
        validate_fallback_zero_receipt(fallback_zero_receipt, workers)
        validate_cross_receipt_bindings(
            performance=performance,
            fallback=fallback_zero_receipt,
            checkpoint=checkpoint,
            workers=workers,
        )
        requirements["trusted_hardware_identity_pair"] = True
        requirements["cpu_fallback_zero"] = True
        requirements["terminal_resultir_diagnosticir_parity"] = True
        sources.update(
            {
                "gfx1100_worker_receipt_hash": remote_worker["receipt_hash"],
                "trust_policy_hash": policy["receipt_hash"],
                "fallback_zero_receipt_hash": fallback_zero_receipt["receipt_hash"],
            }
        )
    elif any(
        value is not None
        for value in (
            gfx1100_worker,
            gfx1100_envelope,
            trust_policy,
            expected_trust_policy_hash,
            fallback_zero_receipt,
        )
    ):
        raise ValueError("g1_promotion_optional_input_set_incomplete")

    requirements["cross_device_production_performance_sweep"] = bool(
        performance["claims"]["cross_device_production_performance_sweep"]
    )
    promotion_ready = all(requirements.values())
    blockers = [name for name in REQUIREMENT_NAMES if not requirements[name]]
    payload: dict[str, Any] = {
        "schema_version": VERSION,
        "receipt_hash": "sha256:" + "0" * 64,
        "generated_at": generated_at
        or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "ready" if promotion_ready else "partial",
        "contract_pass": True,
        "provenance": build_provenance(
            root,
            SOURCE_PATHS,
            source_commit_sha=provenance_source_commit_sha,
        ),
        "sources": sources,
        "promotion_requirements": requirements,
        "claims": {
            "production_worker_ready": promotion_ready,
            "trusted_identity_derived_from_external_policy": requirements[
                "trusted_hardware_identity_pair"
            ],
            "self_declared_identity_promoted": False,
            "gfx1100_workflow_executed_by_this_builder": False,
            "g1_closure": False,
        },
        "blockers_remaining": blockers,
        "claim_boundary": (
            "This v2 promotion gate accepts only an externally hash-pinned, unexpired "
            "hardware identity policy, two verified non-colliding signer/runner "
            "identities, same-source and same-wheel worker receipts, independently "
            "bound CPU-fallback-zero evidence, terminal ResultIR and invariant "
            "DiagnosticIR parity digests, and a repeated production performance sweep. "
            "Missing inputs stay partial; self-declared identity, synthetic performance, "
            "and the detached local self-signature are never discovered or promoted. "
            "This gate has no bound nonlinear material-family breadth receipt, so "
            "production readiness and G1 closure remain false."
        ),
    }
    payload["receipt_hash"] = _hash(payload)
    return payload


def validate(
    payload: dict[str, Any],
    *,
    root: Path = ROOT,
    require_commit_bound: bool = False,
    current: bool = False,
) -> dict[str, Any]:
    schema = secure_read_json(SCHEMA, allowed_root=root)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    if payload["receipt_hash"] != _hash(payload):
        raise ValueError("g1_promotion_gate_receipt_hash_mismatch")
    validate_provenance(
        payload["provenance"],
        root=root.resolve(),
        expected_paths=SOURCE_PATHS,
        require_commit_bound=require_commit_bound,
    )
    requirements = payload["promotion_requirements"]
    expected_ready = all(requirements.values())
    claims = payload["claims"]
    if (
        (payload["status"] == "ready") != expected_ready
        or claims["production_worker_ready"] != expected_ready
        or claims["trusted_identity_derived_from_external_policy"]
        != requirements["trusted_hardware_identity_pair"]
    ):
        raise ValueError("g1_promotion_semantic_claim_mismatch")
    expected_blockers = [name for name in REQUIREMENT_NAMES if not requirements[name]]
    if payload["blockers_remaining"] != expected_blockers:
        raise ValueError("g1_promotion_blocker_set_mismatch")
    trusted_sources = (
        payload["sources"]["gfx1100_worker_receipt_hash"],
        payload["sources"]["trust_policy_hash"],
        payload["sources"]["fallback_zero_receipt_hash"],
    )
    trusted_source_count = sum(value is not None for value in trusted_sources)
    if trusted_source_count not in (0, len(trusted_sources)):
        raise ValueError("g1_promotion_trusted_source_set_incomplete")
    if requirements["trusted_hardware_identity_pair"] != (
        trusted_source_count == len(trusted_sources)
    ):
        raise ValueError("g1_promotion_trusted_source_set_mismatch")
    if (
        requirements["cpu_fallback_zero"]
        != requirements["trusted_hardware_identity_pair"]
        or requirements["terminal_resultir_diagnosticir_parity"]
        != requirements["trusted_hardware_identity_pair"]
    ):
        raise ValueError("g1_promotion_trusted_requirement_set_mismatch")
    if current:
        if any(value is not None for value in trusted_sources):
            raise ValueError("g1_promotion_external_current_replay_inputs_required")
        expected = build(
            root=root,
            generated_at=payload["generated_at"],
            provenance_source_commit_sha=payload["provenance"]["source_commit_sha"],
        )
        if payload != expected:
            raise ValueError("g1_promotion_current_replay_mismatch")
    return payload


def write(*, root: Path = ROOT, out: Path = DEFAULT_OUT) -> dict[str, Any]:
    payload = build(root=root)
    target = _resolve(root, out)
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return validate(payload, root=root, current=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    target = _resolve(ROOT, args.out)
    if args.check:
        validate(
            secure_read_json(target, allowed_root=ROOT),
            root=ROOT,
            require_commit_bound=True,
            current=True,
        )
        print("g1_mgt_production_promotion_gate_v2_consistent")
        return 0
    payload = write(out=args.out)
    print(
        f"{payload['status']} | production_worker_ready="
        f"{str(payload['claims']['production_worker_ready']).lower()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
