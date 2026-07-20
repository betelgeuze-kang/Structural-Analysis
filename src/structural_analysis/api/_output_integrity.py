"""Private output-integrity helpers for public CLI output contracts.

Each target receives an atomic per-file replacement. If a caught exception
interrupts the second replacement, already-replaced targets are restored on a
best-effort basis. This is not a crash- or power-loss-safe cross-file
transaction; that stronger guarantee would require a journal or pointer-based
publication design.

Path comparison follows existing symlinks and uses ``normcase``. It detects
case aliases on Windows, but cannot reliably detect every non-existent alias on
a case-insensitive filesystem whose Python platform reports POSIX semantics.
Existing targets must be regular files, and every not-yet-created target must
have a directory as its nearest existing ancestor.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import secrets
import stat
from typing import Mapping


class OutputPathValidationError(ValueError):
    """Base error for fail-closed CLI output path validation."""


class OutputPathCollisionError(OutputPathValidationError):
    """Raised when outputs alias or conflict with protected paths."""


class OutputTargetTypeError(OutputPathValidationError):
    """Raised when an output target or parent has an unsafe file type."""


class OutputRollbackError(OSError):
    """Raised when an output write fails and best-effort rollback is incomplete."""


@dataclass(frozen=True)
class _OriginalTarget:
    payload: bytes
    mode: int


def resolve_distinct_output_paths(
    result_path: Path,
    report_path: Path,
    *,
    protected_paths: Mapping[str, Path] | None = None,
) -> tuple[Path, Path]:
    """Resolve and validate output targets before model loading or any write."""

    original_outputs = {
        "--out": Path(result_path),
        "--report-out": Path(report_path),
    }
    if _same_existing_file(original_outputs["--out"], original_outputs["--report-out"]):
        raise OutputPathCollisionError(
            "--out and --report-out must refer to distinct output targets"
        )

    resolved_outputs = {
        label: _resolved_output_path(path) for label, path in original_outputs.items()
    }
    resolved_result = resolved_outputs["--out"]
    resolved_report = resolved_outputs["--report-out"]
    if _paths_conflict(resolved_result, resolved_report):
        raise OutputPathCollisionError(
            "--out and --report-out must be distinct, non-nested output targets"
        )

    if protected_paths is not None:
        for protected_label, protected_path_value in protected_paths.items():
            protected_path = Path(protected_path_value)
            resolved_protected = _resolved_output_path(protected_path)
            for output_label, original_output in original_outputs.items():
                resolved_output = resolved_outputs[output_label]
                if _same_existing_file(original_output, protected_path) or (
                    _paths_conflict(resolved_output, resolved_protected)
                ):
                    raise OutputPathCollisionError(
                        f"{output_label} must not alias or nest with {protected_label}"
                    )

    for label, target in resolved_outputs.items():
        _validate_output_target(target, label)

    return resolved_result, resolved_report


def resolve_distinct_output_bundle_paths(
    output_paths: Mapping[str, Path],
    *,
    protected_paths: Mapping[str, Path] | None = None,
) -> dict[str, Path]:
    """Resolve a named output bundle and reject every alias or nesting pair."""

    if not output_paths:
        raise OutputPathCollisionError("output bundle must contain at least one target")
    originals = {label: Path(path) for label, path in output_paths.items()}
    resolved = {label: _resolved_output_path(path) for label, path in originals.items()}
    labels = tuple(originals)
    for index, left_label in enumerate(labels):
        for right_label in labels[index + 1 :]:
            if _same_existing_file(
                originals[left_label],
                originals[right_label],
            ) or _paths_conflict(resolved[left_label], resolved[right_label]):
                raise OutputPathCollisionError(
                    f"{left_label} and {right_label} must be distinct, "
                    "non-nested output targets"
                )

    if protected_paths is not None:
        for protected_label, protected_path_value in protected_paths.items():
            protected_path = Path(protected_path_value)
            resolved_protected = _resolved_output_path(protected_path)
            for output_label, original_output in originals.items():
                if _same_existing_file(original_output, protected_path) or (
                    _paths_conflict(resolved[output_label], resolved_protected)
                ):
                    raise OutputPathCollisionError(
                        f"{output_label} must not alias or nest with {protected_label}"
                    )

    for label, target in resolved.items():
        _validate_output_target(target, label)
    return resolved


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
            details = ", ".join(f"{path}: {error}" for path, error in rollback_errors)
            raise OutputRollbackError(
                f"CLI output replacement failed and rollback was incomplete: {details}"
            ) from write_error
        raise
    finally:
        for temp_path in staged:
            if temp_path is not None:
                _unlink_if_present(temp_path)


def write_json_pair_and_bytes(
    result_path: Path,
    result_payload: Mapping[str, object],
    report_path: Path,
    report_payload: Mapping[str, object],
    artifact_path: Path,
    artifact_payload: bytes,
) -> None:
    """Stage and replace a JSON pair plus one artifact with bounded rollback."""

    if not isinstance(artifact_payload, bytes) or not artifact_payload:
        raise ValueError("artifact_payload must be non-empty bytes")
    resolved = resolve_distinct_output_bundle_paths(
        {
            "--out": result_path,
            "--report-out": report_path,
            "--checkpoint-out": artifact_path,
        }
    )
    targets = tuple(
        resolved[label] for label in ("--out", "--report-out", "--checkpoint-out")
    )
    payloads = (
        _serialize_json(result_payload).encode("utf-8"),
        _serialize_json(report_payload).encode("utf-8"),
        artifact_payload,
    )
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)

    originals = tuple(_snapshot_target(target) for target in targets)
    staged: list[Path | None] = []
    replaced: list[int] = []
    try:
        for target, payload, original in zip(
            targets,
            payloads,
            originals,
            strict=True,
        ):
            mode = (
                original.mode if original is not None else _probe_new_file_mode(target)
            )
            staged.append(_stage_bytes(target, payload, mode=mode))

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
            details = ", ".join(f"{path}: {error}" for path, error in rollback_errors)
            raise OutputRollbackError(
                f"CLI output replacement failed and rollback was incomplete: {details}"
            ) from write_error
        raise
    finally:
        for temp_path in staged:
            if temp_path is not None:
                _unlink_if_present(temp_path)


def write_json_pair_and_clear_artifact(
    result_path: Path,
    result_payload: Mapping[str, object],
    report_path: Path,
    report_payload: Mapping[str, object],
    artifact_path: Path,
) -> None:
    """Replace a JSON pair and remove a stale unavailable artifact target."""

    resolved = resolve_distinct_output_bundle_paths(
        {
            "--out": result_path,
            "--report-out": report_path,
            "--checkpoint-out": artifact_path,
        }
    )
    targets = tuple(resolved[label] for label in ("--out", "--report-out"))
    stale_artifact = resolved["--checkpoint-out"]
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
        _unlink_if_present(stale_artifact)
    except Exception as write_error:
        rollback_errors: list[tuple[Path, Exception]] = []
        for index in reversed(replaced):
            try:
                _restore_target(targets[index], originals[index])
            except Exception as rollback_error:  # pragma: no cover - rare OS fault
                rollback_errors.append((targets[index], rollback_error))
        if rollback_errors:
            details = ", ".join(f"{path}: {error}" for path, error in rollback_errors)
            raise OutputRollbackError(
                f"CLI output replacement failed and rollback was incomplete: {details}"
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


def _paths_conflict(left: Path, right: Path) -> bool:
    return (
        _comparison_key(left) == _comparison_key(right)
        or _is_parent_target(left, right)
        or _is_parent_target(right, left)
    )


def _is_parent_target(parent: Path, child: Path) -> bool:
    parent_key = _comparison_key(parent)
    return any(parent_key == _comparison_key(candidate) for candidate in child.parents)


def _same_existing_file(left: Path, right: Path) -> bool:
    try:
        return os.path.samefile(left, right)
    except OSError:
        return False


def _validate_output_target(target: Path, label: str) -> None:
    try:
        target_stat = target.stat()
    except (FileNotFoundError, NotADirectoryError):
        _validate_nearest_existing_parent(target.parent, label)
        return
    except OSError as error:
        raise OutputTargetTypeError(
            f"{label} target cannot be inspected safely: {error}"
        ) from error

    if not stat.S_ISREG(target_stat.st_mode):
        raise OutputTargetTypeError(
            f"{label} target must be a regular file or a new file path"
        )


def _validate_nearest_existing_parent(parent: Path, label: str) -> None:
    candidate = parent
    while True:
        try:
            parent_stat = candidate.stat()
        except FileNotFoundError:
            next_candidate = candidate.parent
            if next_candidate == candidate:  # pragma: no cover - root should exist
                raise OutputTargetTypeError(
                    f"{label} has no inspectable existing parent directory"
                )
            candidate = next_candidate
            continue
        except OSError as error:
            raise OutputTargetTypeError(
                f"{label} parent cannot be inspected safely: {error}"
            ) from error

        if not stat.S_ISDIR(parent_stat.st_mode):
            raise OutputTargetTypeError(
                f"{label} nearest existing parent must be a directory: {candidate}"
            )
        return


def _serialize_json(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _snapshot_target(target: Path) -> _OriginalTarget | None:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_BINARY", 0)
    file_descriptor = -1
    try:
        file_descriptor = os.open(target, flags)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise OutputTargetTypeError(
            f"output target cannot be opened as a regular file: {target}: {error}"
        ) from error

    try:
        target_stat = os.fstat(file_descriptor)
        if not stat.S_ISREG(target_stat.st_mode):
            raise OutputTargetTypeError(
                f"output target changed to a non-regular file: {target}"
            )
        handle = os.fdopen(file_descriptor, "rb")
        file_descriptor = -1
        with handle:
            payload = handle.read()
            mode = stat.S_IMODE(os.fstat(handle.fileno()).st_mode)
    finally:
        if file_descriptor >= 0:
            os.close(file_descriptor)
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
        temp_path = target.parent / (f".{target.name}.{secrets.token_hex(8)}{suffix}")
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
