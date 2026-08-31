#!/usr/bin/env python3
"""Build, sign, or validate an architecture-neutral HIP FGMRES device receipt."""

from __future__ import annotations

import argparse
import base64
from copy import deepcopy
from datetime import datetime, timezone
from email.parser import Parser
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from typing import Any
import zipfile

from jsonschema import Draft202012Validator

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import run_engine_v2_hip_fgmres_recurrence as local_runner  # noqa: E402
from release_evidence_metadata import (  # noqa: E402
    file_sha256,
    git_head,
    input_checksums,
)
from structural_analysis.engine_v2_backends.hip_fgmres_recurrence import (  # noqa: E402
    build_cpu_hip_fgmres_recurrence_reference,
    compare_hip_fgmres_recurrence_output,
    fgmres_recurrence_receipt_hash,
)


SCHEMA_VERSION = "engine-v2-hip-fgmres-device-receipt.v1"
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/hip_fgmres_device_receipt_v1.schema.json"
)
SOURCE_PATH = local_runner.SOURCE_PATH
CLAIM_BOUNDARY = (
    "This architecture-neutral receipt proves one actual AMD ROCm/HIP device "
    "execution of the bounded 66-equation Engine v2 FGMRES fixture against the "
    "deterministic CPU numerical and checkpoint contract. A verified Ed25519 "
    "signature authenticates only the embedded evidence payload. One device "
    "receipt does not establish the required gfx1030/gfx1100 cross-device pair, "
    "production-scale recurrence or preconditioning, or performance."
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _canonical_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _open_parent(path: Path, *, error_prefix: str) -> tuple[Path, int]:
    absolute = Path(os.path.abspath(path))
    directory_flag = getattr(os, "O_DIRECTORY", 0)
    nofollow_flag = getattr(os, "O_NOFOLLOW", 0)
    parent_fd = os.open(absolute.anchor, os.O_RDONLY | directory_flag)
    try:
        for part in absolute.parent.parts[1:]:
            try:
                next_fd = os.open(
                    part,
                    os.O_RDONLY | directory_flag | nofollow_flag,
                    dir_fd=parent_fd,
                )
            except OSError as exc:
                raise ValueError(f"{error_prefix}_parent_invalid:{part}") from exc
            os.close(parent_fd)
            parent_fd = next_fd
    except Exception:
        os.close(parent_fd)
        raise
    return absolute, parent_fd


def _read_regular_bytes(
    path: Path,
    *,
    error_prefix: str,
    max_bytes: int = 512 * 1024 * 1024,
) -> bytes:
    absolute, parent_fd = _open_parent(path, error_prefix=error_prefix)
    descriptor: int | None = None
    try:
        try:
            metadata = os.stat(
                absolute.name,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise ValueError(f"{error_prefix}_missing:{absolute}") from exc
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size <= 0
            or metadata.st_size > max_bytes
        ):
            raise ValueError(f"{error_prefix}_regular_file_required:{absolute}")
        descriptor = os.open(
            absolute.name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
        observed = os.fstat(descriptor)
        if (
            not stat.S_ISREG(observed.st_mode)
            or (observed.st_dev, observed.st_ino) != (metadata.st_dev, metadata.st_ino)
            or observed.st_size != metadata.st_size
        ):
            raise ValueError(f"{error_prefix}_identity_changed:{absolute}")
        chunks: list[bytes] = []
        remaining = observed.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise ValueError(f"{error_prefix}_short_read:{absolute}")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise ValueError(f"{error_prefix}_size_changed:{absolute}")
        return b"".join(chunks)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent_fd)


def _atomic_write_bytes(path: Path, raw: bytes, *, error_prefix: str) -> None:
    absolute, parent_fd = _open_parent(path, error_prefix=error_prefix)
    temporary_name: str | None = None
    temporary_fd: int | None = None
    try:
        try:
            metadata = os.stat(
                absolute.name,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        else:
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError(f"{error_prefix}_leaf_invalid:{absolute}")
        for counter in range(100):
            candidate = f".{absolute.name}.tmp-{os.getpid()}-{counter}"
            try:
                temporary_fd = os.open(
                    candidate,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                    dir_fd=parent_fd,
                )
            except FileExistsError:
                continue
            temporary_name = candidate
            break
        if temporary_fd is None or temporary_name is None:
            raise ValueError(f"{error_prefix}_temporary_name_exhausted")
        view = memoryview(raw)
        while view:
            written = os.write(temporary_fd, view)
            if written <= 0:
                raise ValueError(f"{error_prefix}_short_write")
            view = view[written:]
        os.fsync(temporary_fd)
        os.close(temporary_fd)
        temporary_fd = None
        os.replace(
            temporary_name,
            absolute.name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        temporary_name = None
        os.fsync(parent_fd)
    finally:
        if temporary_fd is not None:
            os.close(temporary_fd)
        if temporary_name is not None:
            try:
                os.unlink(temporary_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        os.close(parent_fd)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(
        _read_regular_bytes(
            path,
            error_prefix="engine_v2_device_receipt_input",
            max_bytes=16 * 1024 * 1024,
        ).decode("utf-8")
    )
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _device_source_paths() -> list[Path]:
    return [
        *local_runner._source_paths(),
        Path("scripts/run_engine_v2_hip_fgmres_device_receipt.py"),
        SCHEMA_PATH,
        Path("tests/test_engine_v2_hip_fgmres_device_receipt.py"),
    ]


def _source_set_hash(checksums: dict[str, str]) -> str:
    return _sha256_bytes(_canonical_bytes(checksums))


def device_evidence_bytes(receipt: dict[str, Any]) -> bytes:
    """Return the exact canonical bytes covered by the detached signature."""

    return _canonical_bytes(receipt["evidence_payload"])


def wheel_identity(path: Path) -> dict[str, Any]:
    if path.suffix != ".whl":
        raise ValueError("engine_v2_device_receipt_wheel_missing_or_invalid")
    raw = _read_regular_bytes(path, error_prefix="engine_v2_device_receipt_wheel")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        metadata_names = sorted(
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        )
        if len(metadata_names) != 1:
            raise ValueError("engine_v2_device_receipt_wheel_metadata_invalid")
        metadata = Parser().parsestr(archive.read(metadata_names[0]).decode("utf-8"))
    project_name = metadata.get("Name", "").strip()
    project_version = metadata.get("Version", "").strip()
    if not project_name or not project_version:
        raise ValueError("engine_v2_device_receipt_wheel_identity_invalid")
    return {
        "filename": path.name,
        "project_name": project_name,
        "project_version": project_version,
        "sha256": _sha256_bytes(raw),
        "bound_at_execution": False,
    }


def _fixture_identity() -> dict[str, Any]:
    reference = build_cpu_hip_fgmres_recurrence_reference()
    fixture = reference.fixture
    fixture_manifest = fixture.to_manifest()
    checkpoint = reference.checkpoint
    return {
        "fixture_hash": fixture.fixture_hash,
        "execution_plan_hash": fixture.execution_plan_hash,
        "scaling_hash": fixture.scaling_hash,
        "reduced_csr_identity_hash": fixture.reduced_csr_identity_hash,
        "operator_numeric_values_hash": fixture.operator_numeric_values_hash,
        "preconditioner_profile": fixture_manifest["preconditioner_profile"],
        "preconditioner_derivation_profile": fixture_manifest[
            "preconditioner_derivation_profile"
        ],
        "preconditioner_contract_hash": fixture_manifest[
            "preconditioner_contract_hash"
        ],
        "checkpoint_hash": checkpoint.checkpoint_hash,
        "checkpoint_artifact_data_hash": checkpoint.artifact_descriptor.data_hash,
        "checkpoint_recurrence_contract_hash": (checkpoint.recurrence_contract_hash),
        "dimension": fixture.dimension,
        "nnz": fixture.nnz,
    }


def _blockers(
    *,
    exact_source_commit: bool,
    wheel_bound_at_execution: bool,
    signed_receipt: bool,
) -> list[str]:
    blockers: list[str] = []
    if not exact_source_commit:
        blockers.append("clean_exact_source_commit_not_verified")
    if not wheel_bound_at_execution:
        blockers.append("wheel_identity_not_bound_at_execution")
    if not signed_receipt:
        blockers.append("device_receipt_signature_not_attached")
    blockers.extend(
        [
            "cross_device_gfx1030_gfx1100_pair_not_verified",
            "production_scale_multi_block_operator_not_verified",
            "production_scale_preconditioner_effectiveness_not_verified",
            "model_size_performance_sweep_not_executed",
        ]
    )
    return blockers


def _claims(
    *,
    exact_source_commit: bool,
    wheel_bound_at_execution: bool,
    signed_receipt: bool,
) -> dict[str, bool]:
    return {
        "actual_hardware_execution": True,
        "numerical_parity": True,
        "checkpoint_resume_parity": True,
        "exact_source_commit": exact_source_commit,
        "wheel_identity_bound_at_execution": wheel_bound_at_execution,
        "signed_receipt": signed_receipt,
        "cross_device_stage4": False,
        "production_recurrence": False,
        "performance": False,
    }


def build_device_receipt_from_runtime_output(
    runtime_output: dict[str, Any],
    *,
    repo_root: Path = ROOT,
    compiler: dict[str, str],
    binary_sha256: str,
    operator_context: dict[str, Any],
    wheel: dict[str, Any],
    evidence_origin: str,
    upstream_receipt_hash: str | None,
) -> dict[str, Any]:
    reference = build_cpu_hip_fgmres_recurrence_reference()
    comparison = compare_hip_fgmres_recurrence_output(reference, runtime_output)
    if comparison["contract_pass"] is not True:
        raise ValueError("engine_v2_device_receipt_numerical_parity_failed")
    checksums = input_checksums(_device_source_paths(), repo_root=repo_root)
    worktree_clean = local_runner._worktree_clean(repo_root)
    exact_source_commit = bool(worktree_clean)
    wheel_bound = bool(wheel.get("bound_at_execution"))
    evidence_payload = {
        "source": {
            "repository_commit_sha": git_head(repo_root),
            "worktree_clean": worktree_clean,
            "exact_source_commit_claim": exact_source_commit,
            "input_checksums": checksums,
            "source_set_hash": _source_set_hash(checksums),
        },
        "operator_context": deepcopy(operator_context),
        "wheel": deepcopy(wheel),
        "fixture_identity": _fixture_identity(),
        "hardware_execution": {
            "evidence_origin": evidence_origin,
            "upstream_receipt_hash": upstream_receipt_hash,
            "actual_hardware": True,
            "backend": "amd_rocm_hip",
            "device_name": runtime_output["device_name"],
            "gcn_arch_name": runtime_output["gcn_arch_name"],
            "compiler": deepcopy(compiler),
            "binary_sha256": binary_sha256,
            "runtime_output": deepcopy(runtime_output),
        },
        "recurrence_comparison": comparison,
    }
    provisional = {
        "schema_version": SCHEMA_VERSION,
        "receipt_hash": "sha256:" + "0" * 64,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "partial",
        "contract_pass": True,
        "evidence_payload": evidence_payload,
        "signature": {
            "state": "unsigned",
            "algorithm": None,
            "signer_id": None,
            "public_key_spki_base64": None,
            "public_key_sha256": None,
            "signature_base64": None,
            "signed_payload_hash": _sha256_bytes(_canonical_bytes(evidence_payload)),
        },
        "claims": _claims(
            exact_source_commit=exact_source_commit,
            wheel_bound_at_execution=wheel_bound,
            signed_receipt=False,
        ),
        "blockers_remaining": _blockers(
            exact_source_commit=exact_source_commit,
            wheel_bound_at_execution=wheel_bound,
            signed_receipt=False,
        ),
        "claim_boundary": CLAIM_BOUNDARY,
    }
    provisional["receipt_hash"] = fgmres_recurrence_receipt_hash(provisional)
    validate_device_receipt(
        provisional,
        repo_root=repo_root,
        require_current_sources=True,
    )
    return provisional


def build_device_receipt_from_upstream(
    upstream: dict[str, Any],
    *,
    repo_root: Path = ROOT,
    wheel: dict[str, Any],
    operator_context: dict[str, Any],
) -> dict[str, Any]:
    local_runner.validate_receipt(
        upstream,
        repo_root=repo_root,
        require_current_sources=True,
    )
    hardware = upstream["hardware_execution"]
    migrated_wheel = deepcopy(wheel)
    migrated_wheel["bound_at_execution"] = False
    return build_device_receipt_from_runtime_output(
        hardware["runtime_output"],
        repo_root=repo_root,
        compiler=hardware["compiler"],
        binary_sha256=hardware["binary_sha256"],
        operator_context=operator_context,
        wheel=migrated_wheel,
        evidence_origin="validated_upstream_runtime_receipt",
        upstream_receipt_hash=upstream["receipt_hash"],
    )


def _load_ed25519_public_key(der_bytes: bytes):
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )
    except ImportError as exc:  # pragma: no cover - dependency contract
        raise RuntimeError("engine_v2_device_receipt_cryptography_missing") from exc
    public_key = serialization.load_der_public_key(der_bytes)
    if not isinstance(public_key, Ed25519PublicKey):
        raise ValueError("engine_v2_device_receipt_public_key_not_ed25519")
    return public_key


def attach_ed25519_signature(
    receipt: dict[str, Any],
    *,
    signature_bytes: bytes,
    public_key_pem: bytes,
    signer_id: str,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    if not signer_id.strip():
        raise ValueError("engine_v2_device_receipt_signer_id_missing")
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )
    except ImportError as exc:  # pragma: no cover - dependency contract
        raise RuntimeError("engine_v2_device_receipt_cryptography_missing") from exc
    public_key = serialization.load_pem_public_key(public_key_pem)
    if not isinstance(public_key, Ed25519PublicKey):
        raise ValueError("engine_v2_device_receipt_public_key_not_ed25519")
    public_key.verify(signature_bytes, device_evidence_bytes(receipt))
    public_der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    updated = deepcopy(receipt)
    updated["signature"] = {
        "state": "verified",
        "algorithm": "ed25519",
        "signer_id": signer_id.strip(),
        "public_key_spki_base64": base64.b64encode(public_der).decode("ascii"),
        "public_key_sha256": _sha256_bytes(public_der),
        "signature_base64": base64.b64encode(signature_bytes).decode("ascii"),
        "signed_payload_hash": _sha256_bytes(device_evidence_bytes(receipt)),
    }
    exact = updated["evidence_payload"]["source"]["exact_source_commit_claim"]
    wheel_bound = updated["evidence_payload"]["wheel"]["bound_at_execution"]
    updated["claims"] = _claims(
        exact_source_commit=exact,
        wheel_bound_at_execution=wheel_bound,
        signed_receipt=True,
    )
    updated["blockers_remaining"] = _blockers(
        exact_source_commit=exact,
        wheel_bound_at_execution=wheel_bound,
        signed_receipt=True,
    )
    updated["receipt_hash"] = fgmres_recurrence_receipt_hash(updated)
    validate_device_receipt(
        updated,
        repo_root=repo_root,
        require_current_sources=True,
    )
    return updated


def validate_device_receipt(
    payload: dict[str, Any],
    *,
    repo_root: Path = ROOT,
    require_current_sources: bool,
) -> dict[str, Any]:
    schema = _read_json(repo_root / SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    if payload["receipt_hash"] != fgmres_recurrence_receipt_hash(payload):
        raise ValueError("engine_v2_device_receipt_hash_mismatch")
    evidence = payload["evidence_payload"]
    source = evidence["source"]
    if source["source_set_hash"] != _source_set_hash(source["input_checksums"]):
        raise ValueError("engine_v2_device_receipt_source_set_hash_mismatch")
    if source["exact_source_commit_claim"] is not source["worktree_clean"]:
        raise ValueError("engine_v2_device_receipt_exact_source_claim_invalid")
    if require_current_sources:
        current = input_checksums(_device_source_paths(), repo_root=repo_root)
        if current != source["input_checksums"]:
            raise ValueError("engine_v2_device_receipt_sources_stale")
        if (
            source["exact_source_commit_claim"] is True
            and git_head(repo_root) != source["repository_commit_sha"]
        ):
            raise ValueError("engine_v2_device_receipt_commit_mismatch")
    if evidence["fixture_identity"] != _fixture_identity():
        raise ValueError("engine_v2_device_receipt_fixture_identity_mismatch")
    hardware = evidence["hardware_execution"]
    runtime = hardware["runtime_output"]
    if runtime.get("gcn_arch_name") != hardware["gcn_arch_name"]:
        raise ValueError("engine_v2_device_receipt_architecture_mismatch")
    if runtime.get("device_name") != hardware["device_name"]:
        raise ValueError("engine_v2_device_receipt_device_name_mismatch")
    if (
        hardware["evidence_origin"] == "direct_device_runner"
        and hardware["upstream_receipt_hash"] is not None
    ) or (
        hardware["evidence_origin"] == "validated_upstream_runtime_receipt"
        and hardware["upstream_receipt_hash"] is None
    ):
        raise ValueError("engine_v2_device_receipt_origin_binding_invalid")
    reference = build_cpu_hip_fgmres_recurrence_reference()
    comparison = compare_hip_fgmres_recurrence_output(reference, runtime)
    if comparison != evidence["recurrence_comparison"]:
        raise ValueError("engine_v2_device_receipt_comparison_mismatch")
    signature = payload["signature"]
    evidence_bytes = device_evidence_bytes(payload)
    if signature["signed_payload_hash"] != _sha256_bytes(evidence_bytes):
        raise ValueError("engine_v2_device_receipt_signed_payload_hash_mismatch")
    signed = signature["state"] == "verified"
    if signed:
        try:
            public_der = base64.b64decode(
                signature["public_key_spki_base64"], validate=True
            )
            signature_bytes = base64.b64decode(
                signature["signature_base64"], validate=True
            )
        except Exception as exc:
            raise ValueError(
                "engine_v2_device_receipt_signature_encoding_invalid"
            ) from exc
        if signature["public_key_sha256"] != _sha256_bytes(public_der):
            raise ValueError("engine_v2_device_receipt_public_key_hash_mismatch")
        public_key = _load_ed25519_public_key(public_der)
        try:
            public_key.verify(signature_bytes, evidence_bytes)
        except Exception as exc:
            raise ValueError("engine_v2_device_receipt_signature_invalid") from exc
    exact = source["exact_source_commit_claim"]
    wheel_bound = evidence["wheel"]["bound_at_execution"]
    expected_claims = _claims(
        exact_source_commit=exact,
        wheel_bound_at_execution=wheel_bound,
        signed_receipt=signed,
    )
    if payload["claims"] != expected_claims:
        raise ValueError("engine_v2_device_receipt_claims_invalid")
    expected_blockers = _blockers(
        exact_source_commit=exact,
        wheel_bound_at_execution=wheel_bound,
        signed_receipt=signed,
    )
    if payload["blockers_remaining"] != expected_blockers:
        raise ValueError("engine_v2_device_receipt_blockers_invalid")
    return payload


def run_hardware_device_receipt(
    *,
    repo_root: Path,
    wheel_path: Path,
    operator_context: dict[str, Any],
    hipcc: str,
    rocminfo: str,
    rocm_path: str,
    device_lib_path: str,
) -> dict[str, Any]:
    wheel = wheel_identity(wheel_path)
    compiler = local_runner._resolve_hipcc(hipcc)
    device_libs = local_runner._resolve_device_lib_path(repo_root, device_lib_path)
    architecture = local_runner._detect_architecture(repo_root, rocminfo)
    version = local_runner._run(
        [str(compiler), "--version"], cwd=repo_root, timeout=30.0
    )
    if version.returncode != 0 or not version.stdout.strip():
        raise RuntimeError("engine_v2_device_receipt_hipcc_version_failed")
    reference = build_cpu_hip_fgmres_recurrence_reference()
    with tempfile.TemporaryDirectory(prefix="engine-v2-hip-device-receipt-") as temp:
        temporary = Path(temp)
        fixture_path = temporary / "fixture.bin"
        checkpoint_path = temporary / "checkpoint.bin"
        binary_path = temporary / "engine_v2_fgmres_recurrence"
        fixture_path.write_bytes(reference.fixture.to_bytes())
        checkpoint_path.write_bytes(reference.checkpoint.to_bytes())
        compiled = local_runner._run(
            [
                str(compiler),
                f"--rocm-path={rocm_path}",
                f"--rocm-device-lib-path={device_libs}",
                f"--offload-arch={architecture}",
                str(repo_root / SOURCE_PATH),
                "-O2",
                "-std=c++17",
                "-o",
                str(binary_path),
            ],
            cwd=repo_root,
            timeout=120.0,
        )
        if compiled.returncode != 0:
            raise RuntimeError(
                "engine_v2_device_receipt_compile_failed:"
                + compiled.stderr[-1000:].replace("\n", " ")
            )
        binary_hash = file_sha256(binary_path)
        executed = local_runner._run(
            [str(binary_path), str(fixture_path), str(checkpoint_path)],
            cwd=repo_root,
            timeout=60.0,
        )
        if executed.returncode != 0:
            raise RuntimeError(
                "engine_v2_device_receipt_execution_failed:"
                + executed.stderr[-1000:].replace("\n", " ")
            )
        try:
            runtime_output = json.loads(executed.stdout.strip().splitlines()[-1])
        except Exception as exc:
            raise RuntimeError("engine_v2_device_receipt_output_invalid") from exc
    runtime_output["checkpoint_hash"] = reference.checkpoint.checkpoint_hash
    runtime_output["checkpoint_artifact_data_hash"] = (
        reference.checkpoint.artifact_descriptor.data_hash
    )
    runtime_output["checkpoint_recurrence_contract_hash"] = (
        reference.checkpoint.recurrence_contract_hash
    )
    if runtime_output.get("gcn_arch_name") != architecture:
        raise RuntimeError("engine_v2_device_receipt_compiled_runtime_arch_mismatch")
    compiler_info = {
        "path": str(compiler),
        "version_first_line": version.stdout.splitlines()[0],
        "version_output_sha256": _sha256_bytes(version.stdout.encode("utf-8")),
    }
    return build_device_receipt_from_runtime_output(
        runtime_output,
        repo_root=repo_root,
        compiler=compiler_info,
        binary_sha256=binary_hash,
        operator_context=operator_context,
        wheel=wheel,
        evidence_origin="direct_device_runner",
        upstream_receipt_hash=None,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--organization-id")
    parser.add_argument("--runner-id")
    parser.add_argument("--execution-location")
    parser.add_argument(
        "--independent-from-local-gfx1030",
        action="store_true",
    )
    parser.add_argument("--from-runtime-receipt", type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--attach-signature", type=Path)
    parser.add_argument("--public-key", type=Path)
    parser.add_argument("--signer-id")
    parser.add_argument("--signing-payload-out", type=Path)
    parser.add_argument("--hipcc", default="/opt/rocm/bin/hipcc")
    parser.add_argument("--rocminfo", default="rocminfo")
    parser.add_argument("--rocm-path", default="/opt/rocm")
    parser.add_argument("--device-lib-path", default="")
    args = parser.parse_args(argv)
    out = args.out if args.out.is_absolute() else ROOT / args.out
    if args.check:
        validate_device_receipt(
            _read_json(out), repo_root=ROOT, require_current_sources=True
        )
        print("engine_v2_hip_fgmres_device_receipt_consistent")
        return 0
    if args.attach_signature is not None:
        if args.public_key is None or args.signer_id is None:
            parser.error("--attach-signature requires --public-key and --signer-id")
        receipt = attach_ed25519_signature(
            _read_json(out),
            signature_bytes=args.attach_signature.read_bytes(),
            public_key_pem=args.public_key.read_bytes(),
            signer_id=args.signer_id,
            repo_root=ROOT,
        )
    else:
        if args.wheel is None:
            parser.error("--wheel is required for receipt generation")
        if not all((args.organization_id, args.runner_id, args.execution_location)):
            parser.error(
                "receipt generation requires --organization-id, --runner-id, "
                "and --execution-location"
            )
        operator_context = {
            "organization_id": args.organization_id,
            "runner_id": args.runner_id,
            "execution_location": args.execution_location,
            "independent_from_local_gfx1030": (args.independent_from_local_gfx1030),
        }
        resolved_wheel = args.wheel if args.wheel.is_absolute() else ROOT / args.wheel
        if args.from_runtime_receipt is not None:
            upstream_path = (
                args.from_runtime_receipt
                if args.from_runtime_receipt.is_absolute()
                else ROOT / args.from_runtime_receipt
            )
            receipt = build_device_receipt_from_upstream(
                _read_json(upstream_path),
                repo_root=ROOT,
                wheel=wheel_identity(resolved_wheel),
                operator_context=operator_context,
            )
        else:
            receipt = run_hardware_device_receipt(
                repo_root=ROOT,
                wheel_path=resolved_wheel,
                operator_context=operator_context,
                hipcc=args.hipcc,
                rocminfo=args.rocminfo,
                rocm_path=args.rocm_path,
                device_lib_path=args.device_lib_path,
            )
    _atomic_write_bytes(
        out,
        _json_text(receipt).encode("utf-8"),
        error_prefix="engine_v2_device_receipt_output",
    )
    if args.signing_payload_out is not None:
        signing_out = (
            args.signing_payload_out
            if args.signing_payload_out.is_absolute()
            else ROOT / args.signing_payload_out
        )
        _atomic_write_bytes(
            signing_out,
            device_evidence_bytes(receipt),
            error_prefix="engine_v2_device_signing_payload_output",
        )
    print(
        "partial | actual_hardware=True | "
        f"arch={receipt['evidence_payload']['hardware_execution']['gcn_arch_name']} | "
        f"signature={receipt['signature']['state']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
