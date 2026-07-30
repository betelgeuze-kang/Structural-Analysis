"""Deterministic transitive inventory for repository-local Python imports."""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path


class SourceBoundPythonInventoryError(ValueError):
    """Fail-closed invalid source inventory."""


def expand_local_python_sources(
    paths: Iterable[Path],
    *,
    repo_root: Path,
) -> tuple[Path, ...]:
    """Return seed paths plus the static closure of local Python imports.

    The returned paths are repository-relative and sorted. Imports that do not
    resolve below ``src/``, ``scripts/``, or the repository root are treated as
    standard-library/third-party dependencies and are not included.
    """

    root = repo_root.resolve()
    seeds = tuple(_repository_relative(path, root) for path in paths)
    discovered = set(seeds)
    pending = sorted(path for path in seeds if path.suffix == ".py")
    parsed: set[Path] = set()
    while pending:
        relative = pending.pop(0)
        if relative in parsed:
            continue
        parsed.add(relative)
        source = root / relative
        if not source.is_file():
            raise SourceBoundPythonInventoryError(
                f"source_inventory_file_missing:{relative.as_posix()}"
            )
        try:
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        except (OSError, SyntaxError, UnicodeError) as exc:
            raise SourceBoundPythonInventoryError(
                f"source_inventory_python_invalid:{relative.as_posix()}"
            ) from exc
        current_module, current_is_package = _module_identity(relative)
        for module_name in _imported_module_names(
            tree,
            current_module=current_module,
            current_is_package=current_is_package,
        ):
            for dependency in _resolve_local_module(module_name, root):
                if dependency not in discovered:
                    discovered.add(dependency)
                    pending.append(dependency)
        pending.sort()
    return tuple(sorted(discovered))


def _repository_relative(path: Path, root: Path) -> Path:
    candidate = path if path.is_absolute() else root / path
    try:
        relative = candidate.resolve().relative_to(root)
    except ValueError as exc:
        raise SourceBoundPythonInventoryError(
            f"source_inventory_path_outside_repository:{path}"
        ) from exc
    if not relative.parts or ".." in relative.parts:
        raise SourceBoundPythonInventoryError(
            f"source_inventory_path_invalid:{path}"
        )
    return relative


def _module_identity(relative: Path) -> tuple[tuple[str, ...], bool]:
    parts = relative.with_suffix("").parts
    if parts and parts[0] == "src":
        parts = parts[1:]
    elif parts and parts[0] == "scripts":
        parts = parts[1:]
    is_package = bool(parts and parts[-1] == "__init__")
    if is_package:
        parts = parts[:-1]
    return tuple(parts), is_package


def _imported_module_names(
    tree: ast.AST,
    *,
    current_module: tuple[str, ...],
    current_is_package: bool,
) -> tuple[str, ...]:
    names: set[str] = set()
    package = current_module if current_is_package else current_module[:-1]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level:
            remove = node.level - 1
            if remove > len(package):
                raise SourceBoundPythonInventoryError(
                    "source_inventory_relative_import_outside_package"
                )
            base_parts = package[: len(package) - remove]
            if node.module:
                base_parts = (*base_parts, *node.module.split("."))
            base = ".".join(base_parts)
        else:
            base = node.module or ""
        if base:
            names.add(base)
        for alias in node.names:
            if alias.name != "*" and base:
                names.add(f"{base}.{alias.name}")
    return tuple(sorted(names))


def _resolve_local_module(module_name: str, root: Path) -> tuple[Path, ...]:
    parts = tuple(part for part in module_name.split(".") if part)
    if not parts:
        return ()
    candidates: list[Path] = []
    search_roots = (Path("src"), Path("scripts"), Path())
    for search_root in search_roots:
        base = search_root.joinpath(*parts)
        file_candidate = base.with_suffix(".py")
        package_candidate = base / "__init__.py"
        if (root / file_candidate).is_file():
            candidates.append(file_candidate)
        if (root / package_candidate).is_file():
            candidates.append(package_candidate)
    if not candidates:
        return ()
    expanded: set[Path] = set(candidates)
    for candidate in candidates:
        parts_to_scan = candidate.parent.parts
        for index in range(1, len(parts_to_scan) + 1):
            package_init = Path(*parts_to_scan[:index]) / "__init__.py"
            if (root / package_init).is_file():
                expanded.add(package_init)
    return tuple(sorted(expanded))


__all__ = [
    "SourceBoundPythonInventoryError",
    "expand_local_python_sources",
]
