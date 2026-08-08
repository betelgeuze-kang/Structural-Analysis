#!/usr/bin/env python3
"""Build, attach, or verify a signed production-MGT HIP hardware envelope."""

from __future__ import annotations

import argparse
import base64
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Sequence

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "scripts", ROOT / "src", ROOT / "implementation/phase1"):
    sys.path.insert(0, str(candidate))

from run_g1_mgt_device_fgmres import (  # noqa: E402
    DEFAULT_OUT as DEFAULT_UPSTREAM,
    validate as validate_upstream,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "g1_mgt_gfx1030_hardware_envelope.json"
SCHEMA = Path(
    "src/structural_analysis/schemas/g1_mgt_hardware_envelope_v1.schema.json"
)
VERSION = "g1-mgt-production-hip-hardware-envelope.v1"
CLAIM_BOUNDARY = (
    "This envelope authenticates one actual production-size MGT HIP execution, "
    "its exact source/wheel/binary identities, terminal numerical gates, KPI "
    "counters, checkpoint, and source-family material lifecycle. A verified "
    "Ed25519 signature authenticates only the canonical evidence payload and "
    "runner attestation. One envelope cannot establish the required independent "
    "gfx1030/gfx1100 pair, source-authoritative nonlinear material breadth, or G1 "
    "closure."
)


def _resolve(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def _read(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("g1_hardware_envelope_json_object_required")
    return payload


def _canonical_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _receipt_hash(payload: dict[str, Any]) -> str:
    return _sha256_bytes(
        _canonical_bytes(
            {key: value for key, value in payload.items() if key != "receipt_hash"}
        )
    )


def evidence_bytes(payload: dict[str, Any]) -> bytes:
    return _canonical_bytes(payload["evidence_payload"])


def _source_set_hash(checksums: dict[str, str]) -> str:
    return _sha256_bytes(_canonical_bytes(checksums))


def _source_commit_is_ancestor(root: Path, commit_sha: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit_sha, "HEAD"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _claims(
    *, architecture: str, signed: bool, independent_attested: bool
) -> dict[str, bool]:
    return {
        "actual_production_mgt_hardware": True,
        "actual_gfx1030_hardware": architecture == "gfx1030",
        "actual_gfx1100_hardware": architecture == "gfx1100",
        "exact_source_commit": True,
        "wheel_and_binary_bound_at_execution": True,
        "terminal_numerical_contract": True,
        "checkpoint_exact_restart": True,
        "source_family_material_lifecycle": True,
        "signed_receipt": signed,
        "independent_runner_attested": independent_attested,
        "independent_gfx1100_hardware": bool(
            architecture == "gfx1100" and signed and independent_attested
        ),
        "cross_device_pair": False,
        "nonlinear_material_family_breadth": False,
        "g1_closure": False,
    }


def _blockers(
    *, architecture: str, signed: bool, independent_attested: bool
) -> list[str]:
    blockers: list[str] = []
    if not signed:
        blockers.append("ed25519_signature_not_attached")
    if architecture == "gfx1100" and not independent_attested:
        blockers.append("gfx1100_runner_independence_not_attested")
    blockers.extend(
        [
            "signed_independent_gfx1030_gfx1100_pair_not_verified",
            "source_authoritative_nonlinear_material_parameters_unavailable",
            "nonlinear_material_laws_not_connected_to_equilibrium_residual_jvp",
        ]
    )
    return blockers


def _evidence_payload(
    upstream: dict[str, Any],
    *, upstream_path: Path, organization_id: str, runner_id: str, execution_location: str,
    independent_from_local_gfx1030: bool,
) -> dict[str, Any]:
    for name, value in (
        ("organization_id", organization_id),
        ("runner_id", runner_id),
        ("execution_location", execution_location),
    ):
        if not value.strip():
            raise ValueError(f"g1_hardware_envelope_{name}_missing")
    source = upstream["source"]
    runtime = upstream["runtime"]
    hardware = upstream["hardware_execution"]
    material = upstream["material_lifecycle"]
    comparison = upstream["comparison"]
    claims = upstream["claims"]
    architecture = hardware["gcn_arch_name"]
    if architecture not in {"gfx1030", "gfx1100"}:
        raise ValueError("g1_hardware_envelope_architecture_invalid")
    if not (
        upstream["contract_pass"]
        and source["source_paths_clean_at_execution"]
        and claims["production_size_fgmres"]
        and claims["mid_iteration_d2h_zero"]
        and claims["checkpoint_emitted"]
        and claims["exact_restart"]
        and claims["actual_mgt_material_family_fixture_device_bound"]
        and not claims["nonlinear_material_family_breadth"]
    ):
        raise ValueError("g1_hardware_envelope_upstream_claims_invalid")
    return {
        "upstream": {
            "path": upstream_path.as_posix(),
            "schema_version": upstream["schema_version"],
            "receipt_hash": upstream["receipt_hash"],
            "contract_scope": upstream["contract_scope"],
        },
        "source": {
            "repository_commit_sha": source["repository_commit_sha"],
            "source_paths_clean_at_execution": True,
            "input_checksums": deepcopy(source["input_checksums"]),
            "source_set_hash": _source_set_hash(source["input_checksums"]),
        },
        "runner_attestation": {
            "organization_id": organization_id.strip(),
            "runner_id": runner_id.strip(),
            "execution_location": execution_location.strip(),
            "independent_from_local_gfx1030": bool(
                independent_from_local_gfx1030
            ),
        },
        "hardware": {
            "backend": runtime["backend"],
            "device_name": runtime["device_name"],
            "gcn_arch_name": runtime["gcn_arch_name"],
            "device_nodes": deepcopy(runtime["device_nodes"]),
            "compiler_version": runtime["compiler_version"],
            "executed_binary_sha256": runtime["binary_sha256"],
            "executed_binary_byte_length": runtime["binary_byte_length"],
            "dual_target_binary_sha256": deepcopy(
                runtime["dual_target_binary_sha256"]
            ),
            "wheel_sha256": runtime["wheel_sha256"],
        },
        "terminal": {
            "equation_count": hardware["equation_count"],
            "load_factor": upstream["accepted_state"]["load_factor"],
            "krylov_iterations": hardware["krylov_iterations"],
            "matvec_count": hardware["matvec_count"],
            "preconditioner_apply_count": hardware[
                "preconditioner_apply_count"
            ],
            "accepted_alpha": hardware["accepted_alpha"],
            "physical_residual_inf_n": hardware["physical_residual_inf_n"],
            "accepted_nonlinear_residual_inf_n": hardware[
                "accepted_nonlinear_residual_inf_n"
            ],
            "terminal_cpu_replay_error_n": comparison[
                "accepted_nonlinear_residual_cpu_replay_max_abs_error_n"
            ],
            "checkpoint_sha256": comparison["checkpoint_artifact"]["file_sha256"],
            "checkpoint_accepted_state_hash": comparison["checkpoint_artifact"][
                "accepted_state_hash"
            ],
        },
        "material": {
            "profile": material["profile"],
            "integration_point_count": material["integration_point_count"],
            "field_names": deepcopy(material["field_names"]),
            "family_fixture": deepcopy(material["family_fixture"]),
            "cpu_hip_max_scaled_error": material["cpu_hip_max_scaled_error"],
            "rollback_state_bitwise_exact": material[
                "rollback_state_bitwise_exact"
            ],
            "committed_bundle_hash": material["material_state_bundle"][
                "committed_bundle_hash"
            ],
        },
        "performance": {
            "h2d_bytes": hardware["h2d_bytes"],
            "d2h_bytes": hardware["d2h_bytes"],
            "mid_iteration_d2h_transfer_count": hardware[
                "mid_iteration_d2h_transfer_count"
            ],
            "peak_device_allocation_bytes": hardware[
                "tracked_peak_device_allocation_bytes"
            ],
            "device_lifecycle_wall_time_ms": hardware[
                "device_lifecycle_wall_time_ms"
            ],
            "speedup_vs_cpu": upstream["performance"]["speedup_vs_cpu"],
            "checkpoint_serialization_overhead_seconds": comparison[
                "checkpoint_artifact"
            ]["serialization_overhead_seconds"],
        },
    }


def build(
    *, root: Path = ROOT, upstream_path: Path = DEFAULT_UPSTREAM,
    organization_id: str, runner_id: str, execution_location: str,
    independent_from_local_gfx1030: bool,
) -> dict[str, Any]:
    root = root.resolve()
    upstream = validate_upstream(
        _read(_resolve(root, upstream_path)),
        root=root,
        current=True,
        artifacts=True,
    )
    evidence = _evidence_payload(
        upstream,
        upstream_path=upstream_path,
        organization_id=organization_id,
        runner_id=runner_id,
        execution_location=execution_location,
        independent_from_local_gfx1030=independent_from_local_gfx1030,
    )
    architecture = evidence["hardware"]["gcn_arch_name"]
    payload = {
        "schema_version": VERSION,
        "receipt_hash": "sha256:" + "0" * 64,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "partial",
        "contract_pass": True,
        "evidence_payload": evidence,
        "signature": {
            "state": "unsigned",
            "algorithm": None,
            "signer_id": None,
            "public_key_spki_base64": None,
            "public_key_sha256": None,
            "signature_base64": None,
            "signed_payload_hash": _sha256_bytes(_canonical_bytes(evidence)),
        },
        "claims": _claims(
            architecture=architecture,
            signed=False,
            independent_attested=independent_from_local_gfx1030,
        ),
        "blockers_remaining": _blockers(
            architecture=architecture,
            signed=False,
            independent_attested=independent_from_local_gfx1030,
        ),
        "claim_boundary": CLAIM_BOUNDARY,
    }
    payload["receipt_hash"] = _receipt_hash(payload)
    return validate(payload, root=root, require_current_sources=True)


def _load_public_key_der(der: bytes):
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )
    except ImportError as error:  # pragma: no cover
        raise RuntimeError("g1_hardware_envelope_cryptography_missing") from error
    key = serialization.load_der_public_key(der)
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("g1_hardware_envelope_public_key_not_ed25519")
    return key


def attach_signature(
    payload: dict[str, Any], *, signature_bytes: bytes, public_key_pem: bytes,
    signer_id: str, root: Path = ROOT,
) -> dict[str, Any]:
    if not signer_id.strip():
        raise ValueError("g1_hardware_envelope_signer_id_missing")
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )
    except ImportError as error:  # pragma: no cover
        raise RuntimeError("g1_hardware_envelope_cryptography_missing") from error
    key = serialization.load_pem_public_key(public_key_pem)
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("g1_hardware_envelope_public_key_not_ed25519")
    key.verify(signature_bytes, evidence_bytes(payload))
    public_der = key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    updated = deepcopy(payload)
    updated["signature"] = {
        "state": "verified",
        "algorithm": "ed25519",
        "signer_id": signer_id.strip(),
        "public_key_spki_base64": base64.b64encode(public_der).decode("ascii"),
        "public_key_sha256": _sha256_bytes(public_der),
        "signature_base64": base64.b64encode(signature_bytes).decode("ascii"),
        "signed_payload_hash": _sha256_bytes(evidence_bytes(payload)),
    }
    evidence = updated["evidence_payload"]
    architecture = evidence["hardware"]["gcn_arch_name"]
    independent = evidence["runner_attestation"][
        "independent_from_local_gfx1030"
    ]
    updated["claims"] = _claims(
        architecture=architecture,
        signed=True,
        independent_attested=independent,
    )
    updated["blockers_remaining"] = _blockers(
        architecture=architecture,
        signed=True,
        independent_attested=independent,
    )
    updated["receipt_hash"] = _receipt_hash(updated)
    return validate(updated, root=root, require_current_sources=True)


def validate(
    payload: dict[str, Any], *, root: Path = ROOT,
    require_current_sources: bool,
) -> dict[str, Any]:
    schema = _read(root / SCHEMA)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    if payload["receipt_hash"] != _receipt_hash(payload):
        raise ValueError("g1_hardware_envelope_receipt_hash_mismatch")
    evidence = payload["evidence_payload"]
    source = evidence["source"]
    if source["source_set_hash"] != _source_set_hash(source["input_checksums"]):
        raise ValueError("g1_hardware_envelope_source_set_hash_mismatch")
    upstream_path = Path(evidence["upstream"]["path"])
    upstream = validate_upstream(
        _read(_resolve(root, upstream_path)),
        root=root,
        current=require_current_sources,
        artifacts=True,
    )
    expected_evidence = _evidence_payload(
        upstream,
        upstream_path=upstream_path,
        organization_id=evidence["runner_attestation"]["organization_id"],
        runner_id=evidence["runner_attestation"]["runner_id"],
        execution_location=evidence["runner_attestation"]["execution_location"],
        independent_from_local_gfx1030=evidence["runner_attestation"][
            "independent_from_local_gfx1030"
        ],
    )
    if evidence != expected_evidence:
        raise ValueError("g1_hardware_envelope_evidence_replay_mismatch")
    if require_current_sources and not _source_commit_is_ancestor(
        root, source["repository_commit_sha"]
    ):
        raise ValueError("g1_hardware_envelope_source_commit_not_ancestor")
    signature = payload["signature"]
    raw = evidence_bytes(payload)
    if signature["signed_payload_hash"] != _sha256_bytes(raw):
        raise ValueError("g1_hardware_envelope_signed_payload_hash_mismatch")
    signed = signature["state"] == "verified"
    if signed:
        try:
            public_der = base64.b64decode(
                signature["public_key_spki_base64"], validate=True
            )
            signature_bytes = base64.b64decode(
                signature["signature_base64"], validate=True
            )
        except Exception as error:
            raise ValueError(
                "g1_hardware_envelope_signature_encoding_invalid"
            ) from error
        if signature["public_key_sha256"] != _sha256_bytes(public_der):
            raise ValueError("g1_hardware_envelope_public_key_hash_mismatch")
        try:
            _load_public_key_der(public_der).verify(signature_bytes, raw)
        except Exception as error:
            raise ValueError("g1_hardware_envelope_signature_invalid") from error
    architecture = evidence["hardware"]["gcn_arch_name"]
    independent = evidence["runner_attestation"][
        "independent_from_local_gfx1030"
    ]
    if payload["claims"] != _claims(
        architecture=architecture,
        signed=signed,
        independent_attested=independent,
    ):
        raise ValueError("g1_hardware_envelope_claims_invalid")
    if payload["blockers_remaining"] != _blockers(
        architecture=architecture,
        signed=signed,
        independent_attested=independent,
    ):
        raise ValueError("g1_hardware_envelope_blockers_invalid")
    return payload


def write(*, out: Path = DEFAULT_OUT, **kwargs: Any) -> dict[str, Any]:
    root = Path(kwargs.get("root", ROOT)).resolve()
    payload = build(**kwargs)
    target = _resolve(root, out)
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--upstream", type=Path, default=DEFAULT_UPSTREAM)
    parser.add_argument("--organization-id", default="local-development")
    parser.add_argument("--runner-id", default="local-gfx1030")
    parser.add_argument("--execution-location", default="local-workstation")
    parser.add_argument("--independent-from-local-gfx1030", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--attach-signature", type=Path)
    parser.add_argument("--public-key", type=Path)
    parser.add_argument("--signer-id")
    parser.add_argument("--export-evidence", type=Path)
    args = parser.parse_args(argv)
    target = _resolve(ROOT, args.out)
    if args.check:
        validate(_read(target), root=ROOT, require_current_sources=True)
        print("g1_mgt_hardware_envelope_consistent")
        return 0
    if args.export_evidence is not None:
        payload = validate(
            _read(target), root=ROOT, require_current_sources=True
        )
        export_target = _resolve(ROOT, args.export_evidence)
        export_target.write_bytes(evidence_bytes(payload))
        print(
            "exported | bytes="
            f"{export_target.stat().st_size} | "
            f"hash={payload['signature']['signed_payload_hash']}"
        )
        return 0
    if args.attach_signature is not None:
        if args.public_key is None or args.signer_id is None:
            raise ValueError("signature_public_key_and_signer_id_required")
        payload = attach_signature(
            _read(target),
            signature_bytes=args.attach_signature.read_bytes(),
            public_key_pem=args.public_key.read_bytes(),
            signer_id=args.signer_id,
            root=ROOT,
        )
        target.write_text(
            json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    else:
        payload = write(
            out=args.out,
            root=ROOT,
            upstream_path=args.upstream,
            organization_id=args.organization_id,
            runner_id=args.runner_id,
            execution_location=args.execution_location,
            independent_from_local_gfx1030=(
                args.independent_from_local_gfx1030
            ),
        )
    print(
        f"partial | arch={payload['evidence_payload']['hardware']['gcn_arch_name']} "
        f"| signed={payload['claims']['signed_receipt']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
