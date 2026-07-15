"""Private output-integrity helpers for the two-file public CLI contract.

Each target receives an atomic per-file replacement. If a caught exception
interrupts the second replacement, already-replaced targets are restored on a
best-effort basis. This is not a crash- or power-loss-safe cross-file
transaction; that stronger guarantee would require a journal or pointer-based
publication design.

Path comparison follows existing symlinks and uses ``normcase``. It detects
case aliases on Windows, but cannot reliably detect every non-existent alias on
a case-insensitive filesystem whose Python platform reports POSIX semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import secrets
import stat
from typing import Mapping


class OutputPathCollisionError(ValueError):
    """Raised when CLI outputs alias or conflict as file/directory paths."""


class OutputRollbackError(OSError):
    """Raised when an output write fails and best-effort rollback is incomplete."""


@dataclass(frozen=True)
class _OriginalTarget:
    payload: bytes
    mode: int


def resolve_distinct_output_paths(
    result_path: Path,
    report_path: Path,
) -> tuple[Path, Path]:
    """Resolve output targets and reject path aliases before any write."""

    if _same_existing_file(result_path, report_path):
        raise OutputPathCollisionError(
            "--out and --report-out must refer to distinct output targets"
        )

    resolved_result = _resolved_output_path(result_path)
    resolved_report = _resolved_output_path(report_path)
    if (
        _comparison_key(resolved_result) == _comparison_key(resolved_report)
        or _is_parent_target(resolved_result, resolved_report)
        or _is_parent_target(resolved_report, resolved_result)
    ):
        raise OutputPathCollisionError(
            "--out and --report-out must be distinct, non-nested output targets"
        )
    return resolved_result, resolved_report


def write_json_pair(
    result_path: Path,
    result_payload: Mapping[str, object],
    report_path: Path,
    report_payload: Mapping[str, object],
) -> None:
    """Serialize and replace both JSON outputs with bounded rollback behavior."""

    targets = resolve_distinct_output_paths(result_path, report_path)

    # Complete both serializations before creating directories or temp files.
    rendered = (
        _serialize_json(result_payload),
        _serialize_json(report_payload),
    )

    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)

    originals = tuple(_snapshot_target(target) for target in targets)
    staged: list[Path | None] = []
    replaced: list[int] = []

    try:
        for target, text, original in zip(targets, rendered, originals, strict=True):
            staged.append(
                _stage_text(
                    target,
                    text,
                    mode=original.mode if original is not None else None,
                )
            )

        for index, target in enumerate(targets):
            temp_path = staged[index]
            if temp_path is None:  # pragma: no cover - internal invariant
                raise RuntimeError("staged output disappeared before replacement")
            os.replace(temp_path, target)
            staged[index] = None
            replaced.append(index)
    except Exception as write_error:
        rollback_errors: list[tuple[Path, Exception]] = []
        for index in reversed(replaced):
            try:
                _restore_target(targets[index], originals[index])
            except Exception as rollback_error:  # pragma: no cover - rare OS fault
                rollback_errors.append((targets[index], rollback_error))

        if rollback_errors:
            details = ", ".join(
                f"{path}: {error}" for path, error in rollback_errors
            )
            raise OutputRollbackError(
                "CLI output replacement failed and rollback was incomplete: "
                f"{details}"
            ) from write_error
        raise
    finally:
        for temp_path in staged:
            if temp_path is not None:
                _unlink_if_present(temp_path)


def _resolved_output_path(path: Path) -> Path:
    return Path(os.path.realpath(os.path.abspath(os.fspath(path))))


def _comparison_key(path: Path) -> str:
    return os.path.normcase(os.fspath(path))


def _is_parent_target(parent: Path, child: Path) -> bool:
    parent_key = _comparison_key(parent)
    return any(parent_key == _comparison_key(candidate) for candidate in child.parents)


def _same_existing_file(left: Path, right: Path) -> bool:
    try:
        return os.path.samefile(left, right)
    except OSError:
        return False


def _serialize_json(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _snapshot_target(target: Path) -> _OriginalTarget | None:
    try:
        with target.open("rb") as handle:
            payload = handle.read()
            mode = stat.S_IMODE(os.fstat(handle.fileno()).st_mode)
    except FileNotFoundError:
        return None
    return _OriginalTarget(payload=payload, mode=mode)


def _stage_text(target: Path, text: str, *, mode: int | None) -> Path:
    final_mode = mode if mode is not None else _probe_new_file_mode(target)
    file_descriptor, temp_path = _create_temp_file(target, ".tmp")
    try:
        handle = os.fdopen(file_descriptor, "w", encoding="utf-8")
        file_descriptor = -1
        with handle:
            handle.write(text)
            handle.flush()
            _apply_final_mode(handle.fileno(), temp_path, final_mode)
            os.fsync(handle.fileno())
        return temp_path
    except Exception:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        _unlink_if_present(temp_path)
        raise


def _stage_bytes(target: Path, payload: bytes, *, mode: int) -> Path:
    file_descriptor, temp_path = _create_temp_file(target, ".rollback.tmp")
    try:
        handle = os.fdopen(file_descriptor, "wb")
        file_descriptor = -1
        with handle:
            handle.write(payload)
            handle.flush()
            _apply_final_mode(handle.fileno(), temp_path, mode)
            os.fsync(handle.fileno())
        return temp_path
    except Exception:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        _unlink_if_present(temp_path)
        raise


def _create_temp_file(
    target: Path,
    suffix: str,
) -> tuple[int, Path]:
    return _open_unique_temp(target, suffix, 0o600)


def _probe_new_file_mode(target: Path) -> int:
    """Observe ``0666 & umask`` without exposing staged output contents."""

    file_descriptor, probe_path = _open_unique_temp(target, ".mode.tmp", 0o666)
    try:
        return stat.S_IMODE(os.fstat(file_descriptor).st_mode)
    finally:
        os.close(file_descriptor)
        _unlink_if_present(probe_path)


def _open_unique_temp(
    target: Path,
    suffix: str,
    create_mode: int,
) -> tuple[int, Path]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0)
    for _ in range(100):
        temp_path = target.parent / (
            f".{target.name}.{secrets.token_hex(8)}{suffix}"
        )
        try:
            return os.open(temp_path, flags, create_mode), temp_path
        except FileExistsError:
            continue
    raise FileExistsError(f"unable to allocate temporary output beside {target}")


def _apply_final_mode(file_descriptor: int, path: Path, mode: int) -> None:
    if hasattr(os, "fchmod"):
        os.fchmod(file_descriptor, mode)
    else:  # pragma: no cover - exercised by the Windows runtime
        os.chmod(path, mode)


def _restore_target(target: Path, original: _OriginalTarget | None) -> None:
    if original is None:
        _unlink_if_present(target)
        return

    restore_path = _stage_bytes(target, original.payload, mode=original.mode)
    try:
        os.replace(restore_path, target)
    finally:
        _unlink_if_present(restore_path)


def _unlink_if_present(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
