#!/usr/bin/env python3
"""Run, sign, or validate the non-promoting G1 gfx1100 device receipt."""

from __future__ import annotations

import argparse
import base64
from copy import deepcopy
from email.parser import Parser
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
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

import run_engine_v2_hip_fgmres_device_receipt as legacy_runner  # noqa: E402
from release_evidence_metadata import git_head  # noqa: E402
from structural_analysis.engine_v2_backends.hip_fgmres_recurrence import (  # noqa: E402
    build_cpu_hip_fgmres_recurrence_reference,
    compare_hip_fgmres_recurrence_output,
    fgmres_recurrence_receipt_hash,
)


EXPECTED_ARCHITECTURE = "gfx1100"
SCHEMA_PATH = legacy_runner.SCHEMA_PATH
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_WHEEL_BYTES = 512 * 1024 * 1024
MAX_METADATA_BYTES = 1024 * 1024
CLAIM_BOUNDARY = (
    "This dedicated G1 receipt proves one direct bounded Engine-v2 HIP FGMRES "
    "execution on the default selected gfx1100 ROCm agent at one clean exact "
    "source commit. The HIP translation unit is compiled from the exact pre-run "
    "source bytes supplied through standard input, so compilation does not reopen "
    "the mutable checkout path. The retained wheel bytes are measured once and "
    "copied into a private execution directory, but the numerical program is not "
    "loaded from that wheel; wheel execution binding, cross-device authority, "
    "production recurrence, and performance remain false."
)


def _source_paths() -> tuple[Path, ...]:
    paths = [
        *legacy_runner._device_source_paths(),
        Path("scripts/run_g1_gfx1100_device_receipt.py"),
        Path("tests/test_run_g1_gfx1100_device_receipt.py"),
    ]
    unique = {path.as_posix(): path for path in paths}
    return tuple(unique[key] for key in sorted(unique))


SOURCE_PATHS = _source_paths()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _json_text(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _source_set_hash(checksums: dict[str, str]) -> str:
    return _sha256_bytes(_canonical_bytes(checksums))


def _open_parent(path: Path, *, error_prefix: str) -> tuple[Path, int]:
    absolute = Path(os.path.abspath(path))
    directory = getattr(os, "O_DIRECTORY", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(absolute.anchor, os.O_RDONLY | directory)
    try:
        for part in absolute.parent.parts[1:]:
            try:
                next_descriptor = os.open(
                    part,
                    os.O_RDONLY | directory | nofollow,
                    dir_fd=descriptor,
                )
            except OSError as exc:
                raise ValueError(f"{error_prefix}_parent_invalid:{part}") from exc
            os.close(descriptor)
            descriptor = next_descriptor
    except Exception:
        os.close(descriptor)
        raise
    return absolute, descriptor


def _read_regular_bytes(
    path: Path,
    *,
    error_prefix: str,
    max_bytes: int,
) -> bytes:
    absolute, parent_descriptor = _open_parent(path, error_prefix=error_prefix)
    descriptor: int | None = None
    try:
        try:
            before = os.stat(
                absolute.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise ValueError(f"{error_prefix}_missing:{absolute}") from exc
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size <= 0
            or before.st_size > max_bytes
        ):
            raise ValueError(f"{error_prefix}_regular_file_required:{absolute}")
        try:
            descriptor = os.open(
                absolute.name,
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_NONBLOCK", 0),
                dir_fd=parent_descriptor,
            )
        except OSError as exc:
            raise ValueError(f"{error_prefix}_open_failed:{absolute}") from exc
        observed = os.fstat(descriptor)
        if (
            not stat.S_ISREG(observed.st_mode)
            or (observed.st_dev, observed.st_ino) != (before.st_dev, before.st_ino)
            or observed.st_size != before.st_size
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
        os.close(parent_descriptor)


def _atomic_write_bytes(path: Path, raw: bytes, *, error_prefix: str) -> None:
    absolute, parent_descriptor = _open_parent(path, error_prefix=error_prefix)
    temporary_name: str | None = None
    temporary_descriptor: int | None = None
    try:
        try:
            existing = os.stat(
                absolute.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise ValueError(f"{error_prefix}_leaf_invalid:{absolute}") from exc
        else:
            if not stat.S_ISREG(existing.st_mode):
                raise ValueError(f"{error_prefix}_leaf_invalid:{absolute}")
        for counter in range(100):
            candidate = f".{absolute.name}.tmp-{os.getpid()}-{counter}"
            try:
                temporary_descriptor = os.open(
                    candidate,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                    dir_fd=parent_descriptor,
                )
            except FileExistsError:
                continue
            temporary_name = candidate
            break
        if temporary_descriptor is None or temporary_name is None:
            raise ValueError(f"{error_prefix}_temporary_name_exhausted")
        view = memoryview(raw)
        while view:
            written = os.write(temporary_descriptor, view)
            if written <= 0:
                raise ValueError(f"{error_prefix}_short_write")
            view = view[written:]
        os.fsync(temporary_descriptor)
        os.close(temporary_descriptor)
        temporary_descriptor = None
        os.replace(
            temporary_name,
            absolute.name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        temporary_name = None
        os.fsync(parent_descriptor)
    finally:
        if temporary_descriptor is not None:
            os.close(temporary_descriptor)
        if temporary_name is not None:
            try:
                os.unlink(temporary_name, dir_fd=parent_descriptor)
            except FileNotFoundError:
                pass
        os.close(parent_descriptor)


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"g1_gfx1100_json_duplicate_key:{key}")
        value[key] = item
    return value


def decode_gfx1100_device_receipt_bytes(raw: bytes) -> dict[str, Any]:
    """Decode receipt bytes and reject duplicate decoded keys at every depth."""

    if not raw or len(raw) > MAX_JSON_BYTES:
        raise ValueError("g1_gfx1100_json_size_invalid")
    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs
        )
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("g1_gfx1100_json_invalid") from exc
    if not isinstance(value, dict):
        raise ValueError("g1_gfx1100_json_object_required")
    return value


def load_gfx1100_device_receipt(path: Path) -> dict[str, Any]:
    return decode_gfx1100_device_receipt_bytes(
        _read_regular_bytes(
            path,
            error_prefix="g1_gfx1100_receipt_input",
            max_bytes=MAX_JSON_BYTES,
        )
    )


def _current_input_snapshot(repo_root: Path) -> dict[str, bytes]:
    snapshot: dict[str, bytes] = {}
    for relative in SOURCE_PATHS:
        snapshot[relative.as_posix()] = _read_regular_bytes(
            repo_root / relative,
            error_prefix="g1_gfx1100_source",
            max_bytes=MAX_JSON_BYTES,
        )
    return dict(sorted(snapshot.items()))


def _snapshot_checksums(snapshot: dict[str, bytes]) -> dict[str, str]:
    return {path: _sha256_bytes(raw) for path, raw in sorted(snapshot.items())}


def _current_input_checksums(repo_root: Path) -> dict[str, str]:
    return _snapshot_checksums(_current_input_snapshot(repo_root))


def _wheel_identity_from_bytes(raw: bytes, *, filename: str) -> dict[str, Any]:
    if (
        not filename.endswith(".whl")
        or filename in {".", ".."}
        or "/" in filename
        or "\\" in filename
    ):
        raise ValueError("g1_gfx1100_wheel_filename_invalid")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            metadata = [
                item
                for item in archive.infolist()
                if item.filename.endswith(".dist-info/METADATA")
            ]
            if len(metadata) != 1 or not (
                0 < metadata[0].file_size <= MAX_METADATA_BYTES
            ):
                raise ValueError("g1_gfx1100_wheel_metadata_invalid")
            parsed = Parser().parsestr(archive.read(metadata[0]).decode("utf-8"))
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("g1_gfx1100_wheel_invalid") from exc
    project_name = parsed.get("Name", "").strip()
    project_version = parsed.get("Version", "").strip()
    if not project_name or not project_version:
        raise ValueError("g1_gfx1100_wheel_identity_invalid")
    return {
        "filename": filename,
        "project_name": project_name,
        "project_version": project_version,
        "sha256": _sha256_bytes(raw),
        "bound_at_execution": False,
    }


def _write_private_wheel(directory: Path, *, filename: str, raw: bytes) -> Path:
    if stat.S_IMODE(directory.stat().st_mode) != 0o700:
        raise ValueError("g1_gfx1100_private_directory_mode_invalid")
    directory_descriptor = os.open(
        directory,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    descriptor: int | None = None
    try:
        descriptor = os.open(
            filename,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=directory_descriptor,
        )
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise ValueError("g1_gfx1100_private_wheel_short_write")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(directory_descriptor)
    result = directory / filename
    observed = result.lstat()
    if not stat.S_ISREG(observed.st_mode) or stat.S_IMODE(observed.st_mode) != 0o600:
        raise ValueError("g1_gfx1100_private_wheel_mode_invalid")
    return result


def _run_hardware_from_source_snapshot(
    *,
    repo_root: Path,
    wheel_path: Path,
    operator_context: dict[str, Any],
    hipcc: str,
    rocminfo: str,
    rocm_path: str,
    device_lib_path: str,
    source_bytes: bytes,
    source_sha256: str,
) -> dict[str, Any]:
    """Compile the captured HIP bytes without reopening the checkout source path."""

    if not source_bytes or _sha256_bytes(source_bytes) != source_sha256:
        raise ValueError("g1_gfx1100_compile_source_snapshot_mismatch")
    wheel = legacy_runner.wheel_identity(wheel_path)
    compiler = legacy_runner.local_runner._resolve_hipcc(hipcc)
    device_libs = legacy_runner.local_runner._resolve_device_lib_path(
        repo_root,
        device_lib_path,
    )
    architecture = legacy_runner.local_runner._detect_architecture(repo_root, rocminfo)
    version = legacy_runner.local_runner._run(
        [str(compiler), "--version"],
        cwd=repo_root,
        timeout=30.0,
    )
    if version.returncode != 0 or not version.stdout.strip():
        raise RuntimeError("g1_gfx1100_hipcc_version_failed")
    reference = build_cpu_hip_fgmres_recurrence_reference()
    with tempfile.TemporaryDirectory(prefix="g1-gfx1100-device-execution-") as raw:
        temporary = Path(raw)
        os.chmod(temporary, 0o700)
        fixture_path = temporary / "fixture.bin"
        checkpoint_path = temporary / "checkpoint.bin"
        binary_path = temporary / "engine_v2_fgmres_recurrence"
        _atomic_write_bytes(
            fixture_path,
            reference.fixture.to_bytes(),
            error_prefix="g1_gfx1100_fixture",
        )
        _atomic_write_bytes(
            checkpoint_path,
            reference.checkpoint.to_bytes(),
            error_prefix="g1_gfx1100_checkpoint",
        )
        compiled = subprocess.run(
            [
                str(compiler),
                f"--rocm-path={rocm_path}",
                f"--rocm-device-lib-path={device_libs}",
                f"--offload-arch={architecture}",
                "-x",
                "hip",
                "-",
                "-O2",
                "-std=c++17",
                "-o",
                str(binary_path),
            ],
            cwd=repo_root,
            input=source_bytes,
            check=False,
            capture_output=True,
            timeout=120.0,
        )
        if compiled.returncode != 0:
            stderr = compiled.stderr.decode("utf-8", errors="replace")
            raise RuntimeError(
                "g1_gfx1100_compile_failed:" + stderr[-1000:].replace("\n", " ")
            )
        binary_hash = legacy_runner.file_sha256(binary_path)
        executed = legacy_runner.local_runner._run(
            [str(binary_path), str(fixture_path), str(checkpoint_path)],
            cwd=repo_root,
            timeout=60.0,
        )
        if executed.returncode != 0:
            raise RuntimeError(
                "g1_gfx1100_execution_failed:"
                + executed.stderr[-1000:].replace("\n", " ")
            )
        try:
            runtime_output = json.loads(
                executed.stdout.strip().splitlines()[-1],
                object_pairs_hook=_reject_duplicate_pairs,
            )
        except Exception as exc:
            raise RuntimeError("g1_gfx1100_runtime_output_invalid") from exc
        if not isinstance(runtime_output, dict):
            raise RuntimeError("g1_gfx1100_runtime_output_object_required")
    runtime_output["checkpoint_hash"] = reference.checkpoint.checkpoint_hash
    runtime_output["checkpoint_artifact_data_hash"] = (
        reference.checkpoint.artifact_descriptor.data_hash
    )
    runtime_output["checkpoint_recurrence_contract_hash"] = (
        reference.checkpoint.recurrence_contract_hash
    )
    if runtime_output.get("gcn_arch_name") != architecture:
        raise RuntimeError("g1_gfx1100_compiled_runtime_arch_mismatch")
    compiler_info = {
        "path": str(compiler),
        "version_first_line": version.stdout.splitlines()[0],
        "version_output_sha256": _sha256_bytes(version.stdout.encode("utf-8")),
    }
    return legacy_runner.build_device_receipt_from_runtime_output(
        runtime_output,
        repo_root=repo_root,
        compiler=compiler_info,
        binary_sha256=binary_hash,
        operator_context=operator_context,
        wheel=wheel,
        evidence_origin="direct_device_runner",
        upstream_receipt_hash=None,
    )


def device_evidence_bytes(receipt: dict[str, Any]) -> bytes:
    return _canonical_bytes(receipt["evidence_payload"])


def _unsigned_signature(evidence_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "state": "unsigned",
        "algorithm": None,
        "signer_id": None,
        "public_key_spki_base64": None,
        "public_key_sha256": None,
        "signature_base64": None,
        "signed_payload_hash": _sha256_bytes(_canonical_bytes(evidence_payload)),
    }


def _rewrite_dedicated_receipt(
    receipt: dict[str, Any],
    *,
    repository_commit_sha: str,
    checksums: dict[str, str],
    wheel: dict[str, Any],
) -> dict[str, Any]:
    updated = deepcopy(receipt)
    evidence = updated["evidence_payload"]
    evidence["source"] = {
        "repository_commit_sha": repository_commit_sha,
        "worktree_clean": True,
        "exact_source_commit_claim": True,
        "input_checksums": deepcopy(checksums),
        "source_set_hash": _source_set_hash(checksums),
    }
    evidence["wheel"] = deepcopy(wheel)
    hardware = evidence["hardware_execution"]
    hardware["evidence_origin"] = "direct_device_runner"
    hardware["upstream_receipt_hash"] = None
    updated["signature"] = _unsigned_signature(evidence)
    updated["claims"] = legacy_runner._claims(
        exact_source_commit=True,
        wheel_bound_at_execution=False,
        signed_receipt=False,
    )
    updated["blockers_remaining"] = legacy_runner._blockers(
        exact_source_commit=True,
        wheel_bound_at_execution=False,
        signed_receipt=False,
    )
    updated["claim_boundary"] = CLAIM_BOUNDARY
    updated["receipt_hash"] = fgmres_recurrence_receipt_hash(updated)
    return updated


def _validate_signature(payload: dict[str, Any]) -> bool:
    signature = payload["signature"]
    evidence_bytes = device_evidence_bytes(payload)
    if signature["signed_payload_hash"] != _sha256_bytes(evidence_bytes):
        raise ValueError("g1_gfx1100_signed_payload_hash_mismatch")
    if signature["state"] == "unsigned":
        if signature != _unsigned_signature(payload["evidence_payload"]):
            raise ValueError("g1_gfx1100_unsigned_signature_invalid")
        return False
    try:
        public_der = base64.b64decode(
            signature["public_key_spki_base64"], validate=True
        )
        signature_bytes = base64.b64decode(signature["signature_base64"], validate=True)
    except Exception as exc:
        raise ValueError("g1_gfx1100_signature_encoding_invalid") from exc
    if signature["algorithm"] != "ed25519":
        raise ValueError("g1_gfx1100_signature_algorithm_invalid")
    if signature["public_key_sha256"] != _sha256_bytes(public_der):
        raise ValueError("g1_gfx1100_public_key_hash_mismatch")
    public_key = legacy_runner._load_ed25519_public_key(public_der)
    try:
        public_key.verify(signature_bytes, evidence_bytes)
    except Exception as exc:
        raise ValueError("g1_gfx1100_signature_invalid") from exc
    return True


def validate_gfx1100_device_receipt(
    payload: dict[str, Any],
    repo_root: Path = ROOT,
    require_current_sources: bool = True,
) -> dict[str, Any]:
    """Validate the dedicated receipt without changing legacy gfx1030 authority."""

    schema = decode_gfx1100_device_receipt_bytes(
        _read_regular_bytes(
            repo_root / SCHEMA_PATH,
            error_prefix="g1_gfx1100_schema",
            max_bytes=MAX_JSON_BYTES,
        )
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    if payload["claim_boundary"] != CLAIM_BOUNDARY:
        raise ValueError("g1_gfx1100_claim_boundary_invalid")
    if payload["receipt_hash"] != fgmres_recurrence_receipt_hash(payload):
        raise ValueError("g1_gfx1100_receipt_hash_mismatch")

    evidence = payload["evidence_payload"]
    source = evidence["source"]
    expected_keys = {path.as_posix() for path in SOURCE_PATHS}
    if set(source["input_checksums"]) != expected_keys:
        raise ValueError("g1_gfx1100_source_path_set_invalid")
    if source["source_set_hash"] != _source_set_hash(source["input_checksums"]):
        raise ValueError("g1_gfx1100_source_set_hash_mismatch")
    if (
        source["worktree_clean"] is not True
        or source["exact_source_commit_claim"] is not True
    ):
        raise ValueError("g1_gfx1100_exact_source_claim_invalid")
    if require_current_sources:
        if source["input_checksums"] != _current_input_checksums(repo_root):
            raise ValueError("g1_gfx1100_sources_stale")
        if git_head(repo_root) != source["repository_commit_sha"]:
            raise ValueError("g1_gfx1100_commit_mismatch")
        if legacy_runner.local_runner._worktree_clean(repo_root) is not True:
            raise ValueError("g1_gfx1100_current_worktree_not_clean")

    hardware = evidence["hardware_execution"]
    runtime = hardware["runtime_output"]
    if (
        hardware["evidence_origin"] != "direct_device_runner"
        or hardware["upstream_receipt_hash"] is not None
        or hardware["actual_hardware"] is not True
        or hardware["gcn_arch_name"] != EXPECTED_ARCHITECTURE
        or runtime.get("gcn_arch_name") != EXPECTED_ARCHITECTURE
        or runtime.get("device_name") != hardware["device_name"]
    ):
        raise ValueError("g1_gfx1100_direct_hardware_identity_invalid")
    context = evidence["operator_context"]
    if context["independent_from_local_gfx1030"] is not True:
        raise ValueError("g1_gfx1100_independence_claim_missing")
    if any(
        not isinstance(context[key], str)
        or not context[key].strip()
        or any(character in context[key] for character in "\x00\r\n")
        for key in ("organization_id", "runner_id", "execution_location")
    ):
        raise ValueError("g1_gfx1100_operator_context_invalid")

    wheel = evidence["wheel"]
    if wheel["bound_at_execution"] is not False:
        raise ValueError("g1_gfx1100_wheel_execution_claim_invalid")
    if evidence["fixture_identity"] != legacy_runner._fixture_identity():
        raise ValueError("g1_gfx1100_fixture_identity_mismatch")
    reference = build_cpu_hip_fgmres_recurrence_reference()
    comparison = compare_hip_fgmres_recurrence_output(reference, runtime)
    if (
        comparison != evidence["recurrence_comparison"]
        or comparison["contract_pass"] is not True
    ):
        raise ValueError("g1_gfx1100_numerical_comparison_invalid")

    signed = _validate_signature(payload)
    expected_claims = legacy_runner._claims(
        exact_source_commit=True,
        wheel_bound_at_execution=False,
        signed_receipt=signed,
    )
    if payload["claims"] != expected_claims:
        raise ValueError("g1_gfx1100_claims_invalid")
    expected_blockers = legacy_runner._blockers(
        exact_source_commit=True,
        wheel_bound_at_execution=False,
        signed_receipt=signed,
    )
    if payload["blockers_remaining"] != expected_blockers:
        raise ValueError("g1_gfx1100_blockers_invalid")
    return payload


def run_gfx1100_device_receipt(
    *,
    repo_root: Path,
    wheel_path: Path,
    expected_source_sha: str,
    operator_context: dict[str, Any],
    hipcc: str,
    rocminfo: str,
    rocm_path: str,
    device_lib_path: str,
) -> dict[str, Any]:
    before_head = git_head(repo_root)
    if before_head != expected_source_sha:
        raise ValueError("g1_gfx1100_expected_source_sha_mismatch")
    if legacy_runner.local_runner._worktree_clean(repo_root) is not True:
        raise ValueError("g1_gfx1100_worktree_not_clean")
    before_snapshot = _current_input_snapshot(repo_root)
    before_sources = _snapshot_checksums(before_snapshot)
    compile_source_path = legacy_runner.local_runner.SOURCE_PATH.as_posix()
    try:
        compile_source_bytes = before_snapshot[compile_source_path]
    except KeyError as exc:
        raise ValueError("g1_gfx1100_compile_source_not_in_snapshot") from exc
    wheel_raw = _read_regular_bytes(
        wheel_path,
        error_prefix="g1_gfx1100_wheel",
        max_bytes=MAX_WHEEL_BYTES,
    )
    wheel = _wheel_identity_from_bytes(wheel_raw, filename=wheel_path.name)
    with tempfile.TemporaryDirectory(prefix="g1-gfx1100-wheel-") as temporary_raw:
        temporary = Path(temporary_raw)
        os.chmod(temporary, 0o700)
        private_wheel = _write_private_wheel(
            temporary,
            filename=wheel_path.name,
            raw=wheel_raw,
        )
        receipt = _run_hardware_from_source_snapshot(
            repo_root=repo_root,
            wheel_path=private_wheel,
            operator_context=operator_context,
            hipcc=hipcc,
            rocminfo=rocminfo,
            rocm_path=rocm_path,
            device_lib_path=device_lib_path,
            source_bytes=compile_source_bytes,
            source_sha256=before_sources[compile_source_path],
        )
    after_head = git_head(repo_root)
    after_sources = _current_input_checksums(repo_root)
    if (
        after_head != before_head
        or after_sources != before_sources
        or legacy_runner.local_runner._worktree_clean(repo_root) is not True
    ):
        raise ValueError("g1_gfx1100_source_changed_during_execution")
    updated = _rewrite_dedicated_receipt(
        receipt,
        repository_commit_sha=before_head,
        checksums=before_sources,
        wheel=wheel,
    )
    return validate_gfx1100_device_receipt(
        updated,
        repo_root=repo_root,
        require_current_sources=True,
    )


def attach_ed25519_signature(
    receipt: dict[str, Any],
    *,
    signature_bytes: bytes,
    public_key_pem: bytes,
    signer_id: str,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    validate_gfx1100_device_receipt(
        receipt,
        repo_root=repo_root,
        require_current_sources=True,
    )
    if receipt["signature"]["state"] != "unsigned":
        raise ValueError("g1_gfx1100_receipt_already_signed")
    if not signer_id.strip() or any(character in signer_id for character in "\x00\r\n"):
        raise ValueError("g1_gfx1100_signer_id_invalid")
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as exc:  # pragma: no cover - dependency contract
        raise RuntimeError("g1_gfx1100_cryptography_missing") from exc
    public_key = serialization.load_pem_public_key(public_key_pem)
    if not isinstance(public_key, Ed25519PublicKey):
        raise ValueError("g1_gfx1100_public_key_not_ed25519")
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
    updated["claims"] = legacy_runner._claims(
        exact_source_commit=True,
        wheel_bound_at_execution=False,
        signed_receipt=True,
    )
    updated["blockers_remaining"] = legacy_runner._blockers(
        exact_source_commit=True,
        wheel_bound_at_execution=False,
        signed_receipt=True,
    )
    updated["receipt_hash"] = fgmres_recurrence_receipt_hash(updated)
    return validate_gfx1100_device_receipt(
        updated,
        repo_root=repo_root,
        require_current_sources=True,
    )


def _resolved(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--expected-source-sha")
    parser.add_argument("--organization-id")
    parser.add_argument("--runner-id")
    parser.add_argument("--execution-location")
    parser.add_argument("--independent-from-local-gfx1030", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--attach-signature", type=Path)
    parser.add_argument("--public-key", type=Path)
    parser.add_argument("--signer-id")
    parser.add_argument("--signing-payload-out", type=Path)
    parser.add_argument("--hipcc")
    parser.add_argument("--rocminfo")
    parser.add_argument("--rocm-path")
    parser.add_argument("--device-lib-path")
    args = parser.parse_args(argv)
    out = _resolved(args.out)
    generation_only_present = (
        any(
            value is not None
            for value in (
                args.wheel,
                args.expected_source_sha,
                args.organization_id,
                args.runner_id,
                args.execution_location,
                args.hipcc,
                args.rocminfo,
                args.rocm_path,
                args.device_lib_path,
            )
        )
        or args.independent_from_local_gfx1030
    )
    signature_only_present = any(
        value is not None
        for value in (args.attach_signature, args.public_key, args.signer_id)
    )

    if args.check:
        if (
            generation_only_present
            or signature_only_present
            or args.signing_payload_out is not None
        ):
            parser.error("--check accepts only --out and --check")
        validate_gfx1100_device_receipt(
            load_gfx1100_device_receipt(out),
            repo_root=ROOT,
            require_current_sources=True,
        )
        print("g1_gfx1100_device_receipt_consistent")
        return 0

    if args.attach_signature is not None:
        if generation_only_present:
            parser.error("signature attachment rejects generation/runtime selectors")
        if args.public_key is None or args.signer_id is None:
            parser.error("--attach-signature requires --public-key and --signer-id")
        receipt = attach_ed25519_signature(
            load_gfx1100_device_receipt(out),
            signature_bytes=_read_regular_bytes(
                _resolved(args.attach_signature),
                error_prefix="g1_gfx1100_signature_input",
                max_bytes=1024 * 1024,
            ),
            public_key_pem=_read_regular_bytes(
                _resolved(args.public_key),
                error_prefix="g1_gfx1100_public_key_input",
                max_bytes=1024 * 1024,
            ),
            signer_id=args.signer_id,
            repo_root=ROOT,
        )
    else:
        if args.public_key is not None or args.signer_id is not None:
            parser.error(
                "generation rejects signature selectors without --attach-signature"
            )
        if args.wheel is None or args.expected_source_sha is None:
            parser.error("generation requires --wheel and --expected-source-sha")
        if not all((args.organization_id, args.runner_id, args.execution_location)):
            parser.error(
                "generation requires --organization-id, --runner-id, "
                "and --execution-location"
            )
        if args.independent_from_local_gfx1030 is not True:
            parser.error("generation requires --independent-from-local-gfx1030")
        receipt = run_gfx1100_device_receipt(
            repo_root=ROOT,
            wheel_path=_resolved(args.wheel),
            expected_source_sha=args.expected_source_sha,
            operator_context={
                "organization_id": args.organization_id,
                "runner_id": args.runner_id,
                "execution_location": args.execution_location,
                "independent_from_local_gfx1030": True,
            },
            hipcc=args.hipcc or "/opt/rocm/bin/hipcc",
            rocminfo=args.rocminfo or "rocminfo",
            rocm_path=args.rocm_path or "/opt/rocm",
            device_lib_path=args.device_lib_path or "",
        )

    _atomic_write_bytes(
        out,
        _json_text(receipt).encode("utf-8"),
        error_prefix="g1_gfx1100_receipt_output",
    )
    if args.signing_payload_out is not None:
        _atomic_write_bytes(
            _resolved(args.signing_payload_out),
            device_evidence_bytes(receipt),
            error_prefix="g1_gfx1100_signing_payload_output",
        )
    print(
        "partial | actual_hardware=True | arch=gfx1100 | "
        f"signature={receipt['signature']['state']} | wheel_bound=False"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
