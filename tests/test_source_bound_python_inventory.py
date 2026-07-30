"""Tests for deterministic repository-local Python source inventories."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.source_bound_python_inventory import (
    SourceBoundPythonInventoryError,
    expand_local_python_sources,
)


ROOT = Path(__file__).resolve().parents[1]


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_transitive_relative_imports_and_package_initializers_are_included(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "src/example/__init__.py", "from .entry import run\n")
    _write(
        tmp_path / "src/example/entry.py",
        "import json\nfrom .nested.worker import execute\nimport vendor_missing\n",
    )
    _write(tmp_path / "src/example/nested/__init__.py", "")
    _write(
        tmp_path / "src/example/nested/worker.py",
        "from ..support import VALUE\n\ndef execute():\n    return VALUE\n",
    )
    _write(tmp_path / "src/example/support.py", "VALUE = 1\n")

    actual = expand_local_python_sources(
        (Path("src/example/entry.py"),),
        repo_root=tmp_path,
    )

    assert actual == (
        Path("src/example/__init__.py"),
        Path("src/example/entry.py"),
        Path("src/example/nested/__init__.py"),
        Path("src/example/nested/worker.py"),
        Path("src/example/support.py"),
    )


def test_non_python_seed_is_preserved_without_parsing(tmp_path: Path) -> None:
    artifact = Path("schemas/receipt.json")
    _write(tmp_path / artifact, "{}\n")

    assert expand_local_python_sources((artifact,), repo_root=tmp_path) == (artifact,)


def test_path_outside_repository_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.py"

    with pytest.raises(
        SourceBoundPythonInventoryError,
        match="source_inventory_path_outside_repository",
    ):
        expand_local_python_sources((outside,), repo_root=tmp_path)


def test_missing_python_seed_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(
        SourceBoundPythonInventoryError,
        match="source_inventory_file_missing:missing.py",
    ):
        expand_local_python_sources((Path("missing.py"),), repo_root=tmp_path)


def test_invalid_python_seed_is_rejected(tmp_path: Path) -> None:
    _write(tmp_path / "broken.py", "def broken(:\n")

    with pytest.raises(
        SourceBoundPythonInventoryError,
        match="source_inventory_python_invalid:broken.py",
    ):
        expand_local_python_sources((Path("broken.py"),), repo_root=tmp_path)


def test_real_external_receipt_closure_captures_shared_scaling_dependencies() -> None:
    actual = set(
        expand_local_python_sources(
            (
                Path("scripts/run_external_code_to_code_technical_receipt.py"),
                Path("src/structural_analysis/api/core.py"),
            ),
            repo_root=ROOT,
        )
    )

    assert {
        Path("scripts/release_evidence_metadata.py"),
        Path("scripts/source_bound_python_inventory.py"),
        Path("src/structural_analysis/__init__.py"),
        Path("src/structural_analysis/assembly/linear_static.py"),
        Path("src/structural_analysis/model_ir/validation.py"),
        Path("src/structural_analysis/solvers/equation_scaling_6dof.py"),
    } <= actual
