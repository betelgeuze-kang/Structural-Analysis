#!/usr/bin/env python3
"""Build or replay the non-promoting gfx1100 pre-execution worker contract."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
SRC_ROOT = ROOT / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from release_evidence_metadata import git_head, input_checksums  # noqa: E402
import run_engine_v2_hip_fgmres_device_receipt as device_runner  # noqa: E402
import run_engine_v2_hip_fgmres_recurrence as recurrence_runner  # noqa: E402
from structural_analysis.engine_v2_backends.hip_residual_jvp_worker import (  # noqa: E402
    build_preexecution_receipt,
    validate_preexecution_receipt,
)


LANE_SOURCE_PATHS = (
    Path(".github/workflows/g1-production-mgt-gfx1100-hardware.yml"),
    Path("scripts/build_g1_hip_residual_jvp_worker_contract.py"),
    Path("scripts/build_g1_mgt_cross_device_gate.py"),
    Path("scripts/build_engine_v2_hip_fgmres_stage4_status.py"),
    Path("scripts/run_engine_v2_hip_fgmres_device_receipt.py"),
    Path("scripts/run_engine_v2_hip_fgmres_recurrence.py"),
    Path(
        "src/structural_analysis/engine_v2_backends/"
        "_hip_residual_jvp_worker_contract.py"
    ),
    Path("src/structural_analysis/engine_v2_backends/hip_residual_jvp_worker.py"),
    Path("src/structural_analysis/engine_v2_backends/hip_fgmres_recurrence.py"),
    Path("implementation/phase1/hip_kernels/engine_v2_fgmres_recurrence.hip.cpp"),
    Path("src/structural_analysis/schemas/hip_fgmres_device_receipt_v1.schema.json"),
    Path("src/structural_analysis/schemas/hip_fgmres_stage4_status_v1.schema.json"),
    Path("src/structural_analysis/schemas/g1_mgt_cross_device_gate_v3.schema.json"),
    Path("tests/test_g1_production_mgt_gfx1100_hardware_workflow.py"),
    Path("tests/test_build_g1_mgt_cross_device_gate.py"),
    Path("tests/test_engine_v2_hip_fgmres_stage4_status.py"),
    Path("tests/test_hip_residual_jvp_worker.py"),
    Path("scripts/release_evidence_metadata.py"),
)
PACKAGING_INPUTS = (
    Path("pyproject.toml"),
    Path("setup.cfg"),
    Path("README.md"),
    Path("LICENSE"),
)
CONTRACT_SOURCE_PATHS = (
    Path("src/structural_analysis/__init__.py"),
    Path("src/structural_analysis/engine_v2/contracts/__init__.py"),
    Path("src/structural_analysis/engine_v2/contracts/_canonical.py"),
    Path("src/structural_analysis/engine_v2/contracts/equation_scaling.py"),
    Path("src/structural_analysis/engine_v2/contracts/execution_plan.py"),
    Path("src/structural_analysis/engine_v2/contracts/execution_plan_reduced_csr.py"),
)
CONTRACT_SCHEMA_PATHS = (
    Path("src/structural_analysis/schemas/equation_scaling_v1.schema.json"),
    Path("src/structural_analysis/schemas/execution_plan_v1.schema.json"),
    Path("src/structural_analysis/schemas/execution_plan_reduced_csr_v1.schema.json"),
    Path("src/structural_analysis/schemas/engine_v2_vector_artifacts_v1.schema.json"),
)


def _module_aliases(path: Path) -> tuple[str, ...]:
    if path.suffix != ".py":
        return ()
    if path.parts[0] == "src":
        parts = list(path.with_suffix("").parts[1:])
        if parts[-1] == "__init__":
            parts.pop()
        return (".".join(parts),) if parts else ()
    if path.parts[0] in {"scripts", "tests"}:
        parts = list(path.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        aliases = [".".join(parts)] if parts else []
        if path.parts[0] == "scripts" and len(parts) == 2:
            aliases.append(parts[-1])
        return tuple(aliases)
    return ()


def _module_index(root: Path) -> dict[str, Path]:
    index: dict[str, Path] = {}
    for base in (root / "src", root / "scripts", root / "tests"):
        for absolute in sorted(base.rglob("*.py")):
            relative = absolute.relative_to(root)
            for alias in _module_aliases(relative):
                existing = index.get(alias)
                if existing is not None and existing != relative:
                    raise ValueError(f"g1_gfx1100_import_alias_collision:{alias}")
                index[alias] = relative
    return index


def _package_initializers(path: Path, *, root: Path) -> set[Path]:
    initializers: set[Path] = set()
    absolute = root / path
    if path.parts[0] != "src":
        return initializers
    current = absolute.parent
    source_root = root / "src"
    while current != source_root:
        candidate = current / "__init__.py"
        if candidate.is_file():
            initializers.add(candidate.relative_to(root))
        current = current.parent
    return initializers


def _resolve_import_names(
    node: ast.Import | ast.ImportFrom,
    *,
    current_path: Path,
) -> set[str]:
    if isinstance(node, ast.Import):
        return {alias.name for alias in node.names}
    current_aliases = _module_aliases(current_path)
    current_module = current_aliases[0] if current_aliases else ""
    if current_path.name == "__init__.py":
        package = current_module
    else:
        package = current_module.rpartition(".")[0]
    if node.level:
        parts = package.split(".") if package else []
        trim = node.level - 1
        if trim > len(parts):
            return set()
        parts = parts[: len(parts) - trim]
        if node.module:
            parts.extend(node.module.split("."))
        base = ".".join(parts)
    else:
        base = node.module or ""
    names = {base} if base else set()
    names.update(f"{base}.{alias.name}" for alias in node.names if base)
    return names


def repo_local_import_closure(root: Path, seeds: Iterable[Path]) -> tuple[Path, ...]:
    """Resolve a deterministic AST import closure without importing modules."""

    root = root.resolve()
    index = _module_index(root)
    closure: set[Path] = {path for path in seeds if path.suffix == ".py"}
    pending = sorted(closure, key=lambda path: path.as_posix())
    while pending:
        path = pending.pop(0)
        absolute = root / path
        try:
            tree = ast.parse(absolute.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError) as exc:
            raise ValueError(f"g1_gfx1100_import_closure_parse_failed:{path}") from exc
        discovered = _package_initializers(path, root=root)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            for name in _resolve_import_names(node, current_path=path):
                candidate = index.get(name)
                if candidate is not None:
                    discovered.add(candidate)
                    discovered.update(_package_initializers(candidate, root=root))
        for candidate in sorted(discovered, key=lambda item: item.as_posix()):
            if candidate not in closure:
                closure.add(candidate)
                pending.append(candidate)
        pending.sort(key=lambda item: item.as_posix())
    return tuple(sorted(closure, key=lambda path: path.as_posix()))


DECLARED_SOURCE_PATHS = tuple(
    sorted(
        {
            *recurrence_runner._source_paths(),
            *device_runner._device_source_paths(),
            *LANE_SOURCE_PATHS,
            *CONTRACT_SOURCE_PATHS,
            *CONTRACT_SCHEMA_PATHS,
            *PACKAGING_INPUTS,
        },
        key=lambda path: path.as_posix(),
    )
)
IMPORT_CLOSURE_PATHS = repo_local_import_closure(ROOT, DECLARED_SOURCE_PATHS)
SOURCE_PATHS = tuple(
    sorted(
        {*DECLARED_SOURCE_PATHS, *IMPORT_CLOSURE_PATHS},
        key=lambda path: path.as_posix(),
    )
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("g1_gfx1100_worker_contract_json_object_required")
    return value


def _worktree_clean(root: Path) -> bool:
    completed = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return completed.returncode == 0 and completed.stdout == ""


def _regular_file_identity(path: Path) -> tuple[int, str]:
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
        raise ValueError("g1_gfx1100_worker_wheel_regular_file_required")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    try:
        observed = os.fstat(descriptor)
        if not stat.S_ISREG(observed.st_mode):
            raise ValueError("g1_gfx1100_worker_wheel_regular_file_required")
        if (observed.st_dev, observed.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise ValueError("g1_gfx1100_worker_wheel_identity_changed")
        if observed.st_size <= 0 or observed.st_size > 512 * 1024 * 1024:
            raise ValueError("g1_gfx1100_worker_wheel_size_invalid")
        digest = hashlib.sha256()
        remaining = observed.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise ValueError("g1_gfx1100_worker_wheel_short_read")
            digest.update(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise ValueError("g1_gfx1100_worker_wheel_size_changed")
        return observed.st_size, "sha256:" + digest.hexdigest()
    finally:
        os.close(descriptor)


def build(
    *,
    root: Path,
    source_sha: str,
    wheel: Path,
    expected_signer_public_key_sha256: str,
    github_run_id: str,
    github_run_attempt: int,
    artifact_prefix: str,
    expected_runner_id: str,
    receipt_runner_id: str,
) -> dict[str, Any]:
    root = root.resolve()
    if not wheel.is_absolute() and ".." in wheel.parts:
        raise ValueError("g1_gfx1100_worker_wheel_relative_path_escape")
    wheel = wheel if wheel.is_absolute() else root / wheel
    if git_head(root) != source_sha:
        raise ValueError("g1_gfx1100_worker_source_sha_not_head")
    if not _worktree_clean(root):
        raise ValueError("g1_gfx1100_worker_source_not_clean")
    before_size, before_sha256 = _regular_file_identity(wheel)
    checksums = input_checksums(SOURCE_PATHS, repo_root=root)
    missing = [path for path, digest in checksums.items() if digest == "missing"]
    if missing:
        raise ValueError("g1_gfx1100_worker_source_inputs_missing:" + ",".join(missing))
    after_size, after_sha256 = _regular_file_identity(wheel)
    if (before_size, before_sha256) != (after_size, after_sha256):
        raise ValueError("g1_gfx1100_worker_wheel_changed_during_source_binding")
    return build_preexecution_receipt(
        source_commit_sha=source_sha,
        source_files=checksums,
        wheel_filename=wheel.name,
        wheel_sha256=after_sha256,
        wheel_size_bytes=after_size,
        expected_signer_public_key_sha256=expected_signer_public_key_sha256,
        github_run_id=github_run_id,
        github_run_attempt=github_run_attempt,
        artifact_prefix=artifact_prefix,
        expected_runner_id=expected_runner_id,
        receipt_runner_id=receipt_runner_id,
    )


def validate_replay(
    payload: dict[str, Any],
    *,
    root: Path,
    source_sha: str,
    wheel: Path,
    expected_signer_public_key_sha256: str,
    github_run_id: str,
    github_run_attempt: int,
    artifact_prefix: str,
    expected_runner_id: str,
    receipt_runner_id: str,
) -> dict[str, Any]:
    validate_preexecution_receipt(payload)
    expected = build(
        root=root,
        source_sha=source_sha,
        wheel=wheel,
        expected_signer_public_key_sha256=expected_signer_public_key_sha256,
        github_run_id=github_run_id,
        github_run_attempt=github_run_attempt,
        artifact_prefix=artifact_prefix,
        expected_runner_id=expected_runner_id,
        receipt_runner_id=receipt_runner_id,
    )
    if payload != expected:
        raise ValueError("g1_gfx1100_worker_contract_replay_mismatch")
    return payload


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    body = (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    _atomic_write_bytes(path, body.encode("utf-8"))


def _atomic_write_bytes(path: Path, raw: bytes) -> Path:
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
                raise ValueError(
                    f"g1_gfx1100_worker_output_parent_invalid:{part}"
                ) from exc
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
                raise ValueError(f"g1_gfx1100_worker_output_leaf_invalid:{absolute}")
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
            raise ValueError("g1_gfx1100_worker_output_temporary_name_exhausted")
        view = memoryview(raw)
        while view:
            written = os.write(temporary_fd, view)
            if written <= 0:
                raise ValueError("g1_gfx1100_worker_output_short_write")
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--expected-signer-public-key-sha256", required=True)
    parser.add_argument("--github-run-id", required=True)
    parser.add_argument("--github-run-attempt", type=int, required=True)
    parser.add_argument("--artifact-prefix", required=True)
    parser.add_argument("--expected-runner-id", required=True)
    parser.add_argument("--receipt-runner-id", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    out = Path(os.path.abspath(args.out))
    if args.check:
        validate_replay(
            _read_json(out),
            root=ROOT,
            source_sha=args.source_sha,
            wheel=args.wheel,
            expected_signer_public_key_sha256=(args.expected_signer_public_key_sha256),
            github_run_id=args.github_run_id,
            github_run_attempt=args.github_run_attempt,
            artifact_prefix=args.artifact_prefix,
            expected_runner_id=args.expected_runner_id,
            receipt_runner_id=args.receipt_runner_id,
        )
        print("g1_gfx1100_preexecution_worker_contract_consistent")
        return 0
    payload = build(
        root=ROOT,
        source_sha=args.source_sha,
        wheel=args.wheel,
        expected_signer_public_key_sha256=args.expected_signer_public_key_sha256,
        github_run_id=args.github_run_id,
        github_run_attempt=args.github_run_attempt,
        artifact_prefix=args.artifact_prefix,
        expected_runner_id=args.expected_runner_id,
        receipt_runner_id=args.receipt_runner_id,
    )
    _write_atomic(out, payload)
    print("blocked | hardware_execution_proven=False | production_ready=False")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
