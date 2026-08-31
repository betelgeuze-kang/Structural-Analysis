#!/usr/bin/env python3
"""Build, relocate, archive, or replay the non-promoting gfx1100 intake gate."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import tarfile
from typing import Any, Iterable
import zipfile

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
SRC_ROOT = ROOT / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import build_engine_v2_hip_fgmres_stage4_status as stage4_builder  # noqa: E402
import build_g1_hip_residual_jvp_worker_contract as worker_builder  # noqa: E402
from release_evidence_metadata import git_head  # noqa: E402
from structural_analysis.engine_v2_backends.hip_residual_jvp_worker import (  # noqa: E402
    validate_preexecution_receipt,
)

SCHEMA_VERSION = "g1-mgt-gfx1100-cross-device-gate.v3"
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/g1_mgt_cross_device_gate_v3.schema.json"
)
MAX_RETAINED_FILE_BYTES = 512 * 1024 * 1024
MAX_RETAINED_FILES = 16
MAX_ARCHIVE_BYTES = MAX_RETAINED_FILE_BYTES
AUTHORITY_BLOCKERS = (
    "trusted_gfx1100_hardware_identity_attestation_missing",
    "independent_hardware_operator_review_missing",
    "signed_retained_bundle_provenance_not_imported",
    "independently_attested_cpu_fallback_zero_missing",
    "gfx1030_gfx1100_terminal_resultir_diagnosticir_parity_missing",
    "atomic_wheel_identity_measurement_missing",
    "end_to_end_cross_device_performance_sweep_missing",
    "release_authority_missing",
)
FORBIDDEN_AUTHORITY_KEYS = (
    "stage4_cross_device_evidence",
    "independent_gfx1100_actual_hardware",
)
CLAIM_BOUNDARY = (
    "This portable v3 diagnostic gate replays the current Engine-v2 Stage 4 "
    "validator but serializes only path-independent technical identity gates and "
    "receipt hashes. It binds a fixed current-source pre-execution contract, "
    "GitHub run and runner identity, and regular retained artifact bytes under a "
    "caller-supplied artifact root. The outer pre/post hashes narrow wheel "
    "mutation risk but do not create an atomic hardware-run measurement. Raw "
    "Stage 4 authority fields are not embedded. Hardware execution proof, signed "
    "provenance, release, performance, and production readiness remain false."
)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _receipt_hash(payload: dict[str, Any]) -> str:
    body = {key: value for key, value in payload.items() if key != "receipt_hash"}
    return _sha256_bytes(_canonical_bytes(body))


def _relative_path(path: Path) -> Path:
    raw = path.as_posix()
    pure = PurePosixPath(raw)
    if (
        path.is_absolute()
        or not raw
        or raw in {".", ".."}
        or "\\" in raw
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        raise ValueError(f"g1_cross_device_artifact_relative_path_required:{path}")
    return Path(*pure.parts)


def _artifact_path(artifact_root: Path, declared: Path) -> Path:
    relative = _relative_path(declared)
    current = artifact_root
    for part in relative.parts[:-1]:
        current = current / part
        metadata = current.lstat()
        if current.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
            raise ValueError(f"g1_cross_device_artifact_parent_invalid:{declared}")
    return artifact_root / relative


def _hash_regular_file(
    path: Path,
    *,
    capture: bool = False,
) -> tuple[dict[str, Any], bytes | None]:
    metadata = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"g1_cross_device_retained_regular_file_required:{path}")
    if metadata.st_size <= 0 or metadata.st_size > MAX_RETAINED_FILE_BYTES:
        raise ValueError(f"g1_cross_device_retained_size_invalid:{path}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    chunks: list[bytes] = []
    try:
        observed = os.fstat(descriptor)
        if not stat.S_ISREG(observed.st_mode):
            raise ValueError(f"g1_cross_device_retained_regular_file_required:{path}")
        if (observed.st_dev, observed.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise ValueError(f"g1_cross_device_retained_identity_changed:{path}")
        if observed.st_size != metadata.st_size:
            raise ValueError(f"g1_cross_device_retained_size_changed:{path}")
        digest = hashlib.sha256()
        remaining = observed.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise ValueError(f"g1_cross_device_retained_short_read:{path}")
            digest.update(chunk)
            if capture:
                chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise ValueError(f"g1_cross_device_retained_size_changed:{path}")
    finally:
        os.close(descriptor)
    row = {
        "size_bytes": metadata.st_size,
        "sha256": "sha256:" + digest.hexdigest(),
    }
    return row, b"".join(chunks) if capture else None


def _read_json_regular(path: Path, *, error_prefix: str) -> dict[str, Any]:
    _row, raw = _hash_regular_file(path, capture=True)
    assert raw is not None
    try:
        value = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"{error_prefix}_json_invalid") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{error_prefix}_object_required")
    return value


def _optional_artifact_file(artifact_root: Path, declared: Path) -> Path:
    resolved = _artifact_path(artifact_root, declared)
    try:
        _hash_regular_file(resolved)
    except FileNotFoundError:
        pass
    return resolved


def _worker_contract(
    declared: Path | None,
    *,
    artifact_root: Path,
) -> dict[str, Any] | None:
    if declared is None:
        return None
    resolved = _artifact_path(artifact_root, declared)
    try:
        value = _read_json_regular(resolved, error_prefix="g1_cross_device_worker")
    except FileNotFoundError:
        return None
    return validate_preexecution_receipt(value)


def _worker_matches_current_source(
    worker: dict[str, Any] | None,
    *,
    root: Path,
    source_sha: str,
) -> bool:
    if worker is None or worker["source"]["repository_commit_sha"] != source_sha:
        return False
    checksums = worker["source"]["input_checksums"]
    required = {path.as_posix() for path in worker_builder.SOURCE_PATHS}
    if set(checksums) != required:
        return False
    for declared, expected in checksums.items():
        try:
            observed, _raw = _hash_regular_file(root / _relative_path(Path(declared)))
        except (OSError, ValueError):
            return False
        if observed["sha256"] != expected:
            return False
    return True


def _retained_files(
    paths: Iterable[Path],
    *,
    artifact_root: Path,
) -> list[dict[str, Any]]:
    declared_paths = [_relative_path(path) for path in paths]
    if len(declared_paths) > MAX_RETAINED_FILES:
        raise ValueError("g1_cross_device_retained_file_count_exceeded")
    if len(set(declared_paths)) != len(declared_paths):
        raise ValueError("g1_cross_device_retained_path_duplicate")
    rows: list[dict[str, Any]] = []
    for declared in sorted(declared_paths, key=lambda path: path.as_posix()):
        row, _raw = _hash_regular_file(_artifact_path(artifact_root, declared))
        row["path"] = declared.as_posix()
        rows.append(row)
    return rows


def _stage4_diagnostic(stage4: dict[str, Any]) -> dict[str, Any]:
    return {
        "diagnostic_only": True,
        "receipt_hashes": {
            "local_legacy_gfx1030": stage4["local_legacy_gfx1030"]["receipt_hash"],
            "gfx1030": stage4["device_receipts"]["gfx1030"]["receipt_hash"],
            "gfx1100": stage4["device_receipts"]["gfx1100"]["receipt_hash"],
        },
        "technical_identity_gates": dict(sorted(stage4["identity_gates"].items())),
        "authority": {
            "hardware_execution_proven": False,
            "signed_provenance": False,
            "release": False,
            "performance": False,
            "production_ready": False,
        },
    }


def _required_retained_paths(
    *,
    artifact_root: Path,
    candidates: Iterable[Path | None],
) -> set[str]:
    required: set[str] = set()
    for candidate in candidates:
        if candidate is None:
            continue
        relative = _relative_path(candidate)
        try:
            _hash_regular_file(_artifact_path(artifact_root, relative))
        except FileNotFoundError:
            continue
        required.add(relative.as_posix())
    return required


def _invocation_identity(
    *,
    github_run_id: str,
    github_run_attempt: int,
    artifact_prefix: str,
    expected_runner_id: str,
) -> dict[str, Any]:
    if (
        not isinstance(github_run_id, str)
        or not github_run_id.isdecimal()
        or github_run_id.startswith("0")
    ):
        raise ValueError("g1_cross_device_github_run_id_invalid")
    if (
        type(github_run_attempt) is bool
        or not isinstance(github_run_attempt, int)
        or github_run_attempt <= 0
    ):
        raise ValueError("g1_cross_device_github_run_attempt_invalid")
    expected_prefix = f"g1-mgt-gfx1100-{github_run_id}-{github_run_attempt}"
    if artifact_prefix != expected_prefix:
        raise ValueError("g1_cross_device_artifact_prefix_invalid")
    if (
        not isinstance(expected_runner_id, str)
        or not expected_runner_id
        or any(character in expected_runner_id for character in "\r\n")
        or "::github_run_id=" in expected_runner_id
        or "::run_attempt=" in expected_runner_id
    ):
        raise ValueError("g1_cross_device_expected_runner_id_invalid")
    return {
        "github_run_id": github_run_id,
        "github_run_attempt": github_run_attempt,
        "artifact_prefix": artifact_prefix,
        "expected_runner_id": expected_runner_id,
        "receipt_runner_id": (
            f"{expected_runner_id}::github_run_id={github_run_id}::"
            f"run_attempt={github_run_attempt}"
        ),
    }


def build_gate(
    *,
    root: Path = ROOT,
    artifact_root: Path,
    gfx1030_path: Path,
    gfx1100_path: Path,
    worker_contract_path: Path | None = None,
    retained_wheel_path: Path | None = None,
    retained_paths: Iterable[Path] = (),
    github_run_id: str,
    github_run_attempt: int,
    artifact_prefix: str,
    expected_runner_id: str,
) -> dict[str, Any]:
    root = root.resolve()
    artifact_root = artifact_root.resolve(strict=True)
    invocation = _invocation_identity(
        github_run_id=github_run_id,
        github_run_attempt=github_run_attempt,
        artifact_prefix=artifact_prefix,
        expected_runner_id=expected_runner_id,
    )
    local_resolved = _optional_artifact_file(artifact_root, gfx1030_path)
    external_resolved = _optional_artifact_file(artifact_root, gfx1100_path)
    stage4 = stage4_builder.build_stage4_status(
        repo_root=root,
        gfx1030_device_path=local_resolved,
        gfx1100_device_path=external_resolved,
        generated_at="1970-01-01T00:00:00+00:00",
    )
    worker = _worker_contract(worker_contract_path, artifact_root=artifact_root)
    retained_wheel = None
    if retained_wheel_path is not None:
        retained_wheel, _raw = _hash_regular_file(
            _artifact_path(artifact_root, retained_wheel_path)
        )
        retained_wheel["path"] = _relative_path(retained_wheel_path).as_posix()
    retained = _retained_files(retained_paths, artifact_root=artifact_root)
    retained_names = {row["path"] for row in retained}
    required_names = _required_retained_paths(
        artifact_root=artifact_root,
        candidates=(
            gfx1030_path,
            gfx1100_path,
            worker_contract_path,
            retained_wheel_path,
        ),
    )
    if not required_names <= retained_names:
        raise ValueError("g1_cross_device_required_retained_file_missing")

    source_sha = git_head(root)
    local = stage4["device_receipts"]["gfx1030"]
    external = stage4["device_receipts"]["gfx1100"]
    worker_current = _worker_matches_current_source(
        worker,
        root=root,
        source_sha=source_sha,
    )
    if worker is not None and worker["run_identity"] != invocation:
        raise ValueError("g1_cross_device_worker_invocation_identity_mismatch")
    expected_signer = (
        worker["signer_policy"]["expected_public_key_sha256"]
        if worker is not None
        else None
    )
    if (
        external["signature_verified"]
        and expected_signer is not None
        and external["public_key_sha256"] != expected_signer
    ):
        raise ValueError("g1_cross_device_gfx1100_signer_policy_mismatch")
    receipt_runner = invocation["receipt_runner_id"] if worker is not None else None
    if external["attached"] and receipt_runner != external["runner_id"]:
        raise ValueError("g1_cross_device_gfx1100_cross_run_identity_mismatch")
    run_identity_bound = bool(external["attached"] and receipt_runner)
    retained_bound = bool(
        retained_wheel is not None
        and external["attached"]
        and external["wheel_bound_at_execution"]
        and worker_current
        and run_identity_bound
        and retained_wheel["sha256"] == external["wheel_sha256"]
        and worker is not None
        and retained_wheel["sha256"] == worker["retained_wheel"]["sha256"]
        and retained_wheel["size_bytes"] == worker["retained_wheel"]["size_bytes"]
    )
    if (
        external["attached"]
        and retained_wheel is not None
        and (retained_wheel["sha256"] != external["wheel_sha256"])
    ):
        raise ValueError("g1_cross_device_gfx1100_retained_wheel_hash_mismatch")
    if (
        worker is not None
        and retained_wheel is not None
        and not (
            retained_wheel["sha256"] == worker["retained_wheel"]["sha256"]
            and retained_wheel["size_bytes"] == worker["retained_wheel"]["size_bytes"]
        )
    ):
        raise ValueError("g1_cross_device_worker_retained_wheel_mismatch")

    blockers = list(stage4["blockers_remaining"])
    if not local["attached"]:
        blockers.append("current_source_gfx1030_receipt_missing")
    if not external["attached"]:
        blockers.append("current_source_gfx1100_receipt_missing")
    if worker is None:
        blockers.append("preexecution_worker_contract_missing")
    elif not worker_current:
        blockers.append("preexecution_worker_source_set_not_current")
    if not run_identity_bound:
        blockers.append("gfx1100_exact_run_and_runner_identity_not_bound")
    if not external["signature_verified"]:
        blockers.append("gfx1100_expected_signer_signature_not_verified")
    if not retained_bound:
        blockers.append("gfx1100_retained_wheel_bytes_not_bound")
    blockers.extend(AUTHORITY_BLOCKERS)
    blockers = list(dict.fromkeys(blockers))
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "receipt_hash": "sha256:" + "0" * 64,
        "status": "blocked",
        "contract_pass": True,
        "source_sha": source_sha,
        "invocation_identity": invocation,
        "inputs": {
            "gfx1030": _relative_path(gfx1030_path).as_posix(),
            "gfx1100": _relative_path(gfx1100_path).as_posix(),
            "worker_contract": (
                _relative_path(worker_contract_path).as_posix()
                if worker_contract_path is not None
                else None
            ),
            "retained_wheel": (
                _relative_path(retained_wheel_path).as_posix()
                if retained_wheel_path is not None
                else None
            ),
        },
        "stage4_diagnostic": _stage4_diagnostic(stage4),
        "preexecution_contract": worker,
        "retained_wheel": retained_wheel,
        "retained_files": retained,
        "claims": {
            "gfx1100_device_receipt_attached": external["attached"],
            "exact_run_and_runner_identity_bound": run_identity_bound,
            "retained_gfx1100_wheel_bound": retained_bound,
            "cross_device_pair_consistent": stage4["identity_gates"][
                "stage4_contract_pass"
            ],
            "hardware_execution_proven": False,
            "signed_provenance": False,
            "release": False,
            "performance": False,
            "production_ready": False,
        },
        "blockers_remaining": blockers,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    payload["receipt_hash"] = _receipt_hash(payload)
    _validate_schema_and_hash(payload, root=root)
    serialized = _canonical_bytes(payload).decode("utf-8")
    if '"status":"ready"' in serialized:
        raise ValueError("g1_cross_device_raw_stage4_ready_status_forbidden")
    for forbidden in FORBIDDEN_AUTHORITY_KEYS:
        if forbidden in serialized:
            raise ValueError(
                f"g1_cross_device_raw_authority_field_forbidden:{forbidden}"
            )
    return payload


def _validate_schema_and_hash(payload: dict[str, Any], *, root: Path) -> None:
    schema = json.loads((root / SCHEMA_PATH).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    if payload["receipt_hash"] != _receipt_hash(payload):
        raise ValueError("g1_cross_device_gate_receipt_hash_mismatch")


def validate_gate(
    payload: dict[str, Any],
    *,
    root: Path = ROOT,
    artifact_root: Path,
    github_run_id: str,
    github_run_attempt: int,
    artifact_prefix: str,
    expected_runner_id: str,
) -> dict[str, Any]:
    root = root.resolve()
    artifact_root = artifact_root.resolve(strict=True)
    _validate_schema_and_hash(payload, root=root)
    invocation = _invocation_identity(
        github_run_id=github_run_id,
        github_run_attempt=github_run_attempt,
        artifact_prefix=artifact_prefix,
        expected_runner_id=expected_runner_id,
    )
    if payload["invocation_identity"] != invocation:
        raise ValueError("g1_cross_device_gate_invocation_identity_mismatch")
    inputs = payload["inputs"]
    expected = build_gate(
        root=root,
        artifact_root=artifact_root,
        gfx1030_path=Path(inputs["gfx1030"]),
        gfx1100_path=Path(inputs["gfx1100"]),
        worker_contract_path=(
            Path(inputs["worker_contract"])
            if inputs["worker_contract"] is not None
            else None
        ),
        retained_wheel_path=(
            Path(inputs["retained_wheel"])
            if inputs["retained_wheel"] is not None
            else None
        ),
        retained_paths=[Path(row["path"]) for row in payload["retained_files"]],
        github_run_id=github_run_id,
        github_run_attempt=github_run_attempt,
        artifact_prefix=artifact_prefix,
        expected_runner_id=expected_runner_id,
    )
    if payload != expected:
        raise ValueError("g1_cross_device_gate_replay_mismatch")
    return payload


def _gate_file_bytes(payload: dict[str, Any]) -> bytes:
    body = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    return body.encode("utf-8")


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    _atomic_write_bytes(
        path,
        _gate_file_bytes(payload),
        error_prefix="g1_cross_device_gate_output",
    )


def _atomic_write_bytes(path: Path, raw: bytes, *, error_prefix: str) -> Path:
    absolute = Path(os.path.abspath(path))
    directory_flag = getattr(os, "O_DIRECTORY", 0)
    nofollow_flag = getattr(os, "O_NOFOLLOW", 0)
    parent_fd = os.open(absolute.anchor, os.O_RDONLY | directory_flag)
    temporary_name: str | None = None
    temporary_fd: int | None = None
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
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow_flag,
                    0o644,
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
    return absolute


def _archive_inputs(
    *,
    artifact_root: Path,
    gate_path: Path,
    payload: dict[str, Any],
) -> list[tuple[str, dict[str, Any], bytes]]:
    names = [gate_path.as_posix(), *(row["path"] for row in payload["retained_files"])]
    if len(set(names)) != len(names):
        raise ValueError("g1_cross_device_archive_member_duplicate")
    rows: list[tuple[str, dict[str, Any], bytes]] = []
    retained_by_name = {row["path"]: row for row in payload["retained_files"]}
    for name in sorted(names):
        lowered = name.casefold()
        if "private-key" in lowered or Path(name).suffix.casefold() in {
            ".key",
            ".pem",
            ".p12",
            ".pfx",
        }:
            raise ValueError("g1_cross_device_archive_private_key_forbidden")
        observed, raw = _hash_regular_file(
            _artifact_path(artifact_root, Path(name)), capture=True
        )
        assert raw is not None
        if name == gate_path.as_posix() and raw != _gate_file_bytes(payload):
            raise ValueError("g1_cross_device_archive_gate_bytes_mismatch")
        if b"PRIVATE KEY-----" in raw:
            raise ValueError("g1_cross_device_archive_private_key_forbidden")
        if Path(name).suffix.casefold() == ".whl":
            with zipfile.ZipFile(io.BytesIO(raw)) as wheel:
                expanded_bytes = 0
                for member in wheel.infolist():
                    expanded_bytes += member.file_size
                    if (
                        member.file_size > MAX_RETAINED_FILE_BYTES
                        or expanded_bytes > MAX_RETAINED_FILE_BYTES
                    ):
                        raise ValueError(
                            "g1_cross_device_archive_wheel_expansion_exceeded"
                        )
                    member_name = member.filename.casefold()
                    if Path(member_name).suffix in {".key", ".p12", ".pfx"}:
                        raise ValueError(
                            "g1_cross_device_archive_private_key_forbidden"
                        )
                    if b"PRIVATE KEY-----" in wheel.read(member):
                        raise ValueError(
                            "g1_cross_device_archive_private_key_forbidden"
                        )
        expected = retained_by_name.get(name)
        if expected is not None and any(
            observed[key] != expected[key] for key in ("size_bytes", "sha256")
        ):
            raise ValueError("g1_cross_device_archive_manifest_mismatch")
        rows.append((name, observed, raw))
    if sum(row[1]["size_bytes"] for row in rows) > MAX_ARCHIVE_BYTES:
        raise ValueError("g1_cross_device_archive_size_exceeded")
    return rows


def build_archive(
    *,
    artifact_root: Path,
    gate_path: Path,
    payload: dict[str, Any],
    out: Path,
) -> dict[str, Any]:
    artifact_root = artifact_root.resolve(strict=True)
    gate_path = _relative_path(gate_path)
    rows = _archive_inputs(
        artifact_root=artifact_root,
        gate_path=gate_path,
        payload=payload,
    )
    out = Path(os.path.abspath(out))
    try:
        out.relative_to(artifact_root)
    except ValueError:
        pass
    else:
        raise ValueError("g1_cross_device_archive_must_be_outside_artifact_root")
    raw_archive = _canonical_archive_bytes(rows)
    out = _atomic_write_bytes(
        out,
        raw_archive,
        error_prefix="g1_cross_device_archive_output",
    )
    descriptor, _raw = _hash_regular_file(out)
    return descriptor


def _canonical_archive_bytes(
    rows: list[tuple[str, dict[str, Any], bytes]],
) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for name, row, raw in rows:
            info = tarfile.TarInfo(name=name)
            info.size = row["size_bytes"]
            info.mode = 0o644
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mtime = 0
            tar.addfile(info, io.BytesIO(raw))
    return buffer.getvalue()


def validate_archive(
    *,
    artifact_root: Path,
    gate_path: Path,
    payload: dict[str, Any],
    archive_path: Path,
) -> dict[str, Any]:
    expected_rows = _archive_inputs(
        artifact_root=artifact_root.resolve(strict=True),
        gate_path=_relative_path(gate_path),
        payload=payload,
    )
    expected = {name: (row, raw) for name, row, raw in expected_rows}
    descriptor, raw_archive = _hash_regular_file(archive_path, capture=True)
    assert raw_archive is not None
    expected_archive = _canonical_archive_bytes(expected_rows)
    if raw_archive != expected_archive:
        raise ValueError("g1_cross_device_archive_noncanonical_bytes")
    with tarfile.open(fileobj=io.BytesIO(raw_archive), mode="r:") as tar:
        members = tar.getmembers()
        if [member.name for member in members] != sorted(expected):
            raise ValueError("g1_cross_device_archive_allowlist_mismatch")
        for member in members:
            if (
                not member.isfile()
                or member.mode != 0o644
                or member.uid != 0
                or member.gid != 0
                or member.uname
                or member.gname
                or member.mtime != 0
            ):
                raise ValueError("g1_cross_device_archive_header_invalid")
            extracted = tar.extractfile(member)
            if extracted is None:
                raise ValueError("g1_cross_device_archive_member_missing")
            raw = extracted.read(MAX_RETAINED_FILE_BYTES + 1)
            row, expected_raw = expected[member.name]
            if len(raw) > MAX_RETAINED_FILE_BYTES or raw != expected_raw:
                raise ValueError("g1_cross_device_archive_member_bytes_mismatch")
            if member.size != row["size_bytes"] or _sha256_bytes(raw) != row["sha256"]:
                raise ValueError("g1_cross_device_archive_member_identity_mismatch")
    return descriptor


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--gfx1030", type=Path, required=True)
    parser.add_argument("--gfx1100", type=Path, required=True)
    parser.add_argument("--worker-contract", type=Path)
    parser.add_argument("--retained-wheel", type=Path)
    parser.add_argument("--retained-file", type=Path, action="append", default=[])
    parser.add_argument("--github-run-id", required=True)
    parser.add_argument("--github-run-attempt", type=int, required=True)
    parser.add_argument("--artifact-prefix", required=True)
    parser.add_argument("--expected-runner-id", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--archive-out", type=Path)
    parser.add_argument("--build-archive", action="store_true")
    parser.add_argument("--check-archive", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if not worker_builder._worktree_clean(ROOT):
        raise ValueError("g1_cross_device_exact_clean_checkout_required")
    artifact_root = args.artifact_root.resolve(strict=True)
    out_relative = _relative_path(args.out)
    out = _artifact_path(artifact_root, out_relative)
    if args.check:
        payload = _read_json_regular(out, error_prefix="g1_cross_device_gate")
        validate_gate(
            payload,
            root=ROOT,
            artifact_root=artifact_root,
            github_run_id=args.github_run_id,
            github_run_attempt=args.github_run_attempt,
            artifact_prefix=args.artifact_prefix,
            expected_runner_id=args.expected_runner_id,
        )
    else:
        payload = build_gate(
            root=ROOT,
            artifact_root=artifact_root,
            gfx1030_path=args.gfx1030,
            gfx1100_path=args.gfx1100,
            worker_contract_path=args.worker_contract,
            retained_wheel_path=args.retained_wheel,
            retained_paths=args.retained_file,
            github_run_id=args.github_run_id,
            github_run_attempt=args.github_run_attempt,
            artifact_prefix=args.artifact_prefix,
            expected_runner_id=args.expected_runner_id,
        )
        _write_atomic(out, payload)
    if args.build_archive or args.check_archive:
        if args.archive_out is None:
            raise ValueError("g1_cross_device_archive_out_required")
        if args.build_archive:
            build_archive(
                artifact_root=artifact_root,
                gate_path=out_relative,
                payload=payload,
                out=args.archive_out,
            )
        if args.check_archive:
            validate_archive(
                artifact_root=artifact_root,
                gate_path=out_relative,
                payload=payload,
                archive_path=args.archive_out,
            )
    print(
        "blocked | hardware_execution_proven=False | signed_provenance=False | "
        "production_ready=False"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
