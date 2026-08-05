from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/check_stack_feature_surface.py"
MANIFEST = ROOT / ".github/feature-surfaces/planar-corpus.json"
spec = importlib.util.spec_from_file_location("check_stack_feature_surface_test", SCRIPT)
assert spec is not None and spec.loader is not None
checker = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = checker
spec.loader.exec_module(checker)


def _write_manifest(root: Path, payload: dict) -> Path:
    path = root / ".github/feature-surfaces/test.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _base_manifest() -> dict:
    return {
        "schema_version": checker.SCHEMA_VERSION,
        "feature_id": "test-feature",
        "core_feature_paths": ["src/example.py"],
        "guard_paths": ["tests/test_example.py"],
        "workflow_path": ".github/workflows/example.yml",
        "workflow_referenced_paths": ["src/example.py", "tests/test_example.py"],
        "import_modules": [],
    }


def test_committed_planar_corpus_feature_surface_is_complete_and_importable() -> None:
    report = checker.validate_feature_surface(MANIFEST, repo_root=ROOT)

    assert report["contract_pass"] is True, report
    assert report["missing_paths"] == []
    assert report["missing_workflow_references"] == []
    assert report["import_failures"] == []


def test_missing_feature_file_blocks_the_contract(tmp_path: Path) -> None:
    payload = _base_manifest()
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_example.py").write_text("# guard\n", encoding="utf-8")
    workflow = tmp_path / ".github/workflows/example.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("run: python src/example.py tests/test_example.py\n", encoding="utf-8")

    report = checker.validate_feature_surface(
        _write_manifest(tmp_path, payload),
        repo_root=tmp_path,
        run_import_probes=False,
    )

    assert report["contract_pass"] is False
    assert report["missing_paths"] == ["src/example.py"]


def test_missing_literal_workflow_reference_blocks_the_contract(tmp_path: Path) -> None:
    payload = _base_manifest()
    for relative in ("src/example.py", "tests/test_example.py"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# present\n", encoding="utf-8")
    workflow = tmp_path / ".github/workflows/example.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("run: python src/example.py\n", encoding="utf-8")

    report = checker.validate_feature_surface(
        _write_manifest(tmp_path, payload),
        repo_root=tmp_path,
        run_import_probes=False,
    )

    assert report["contract_pass"] is False
    assert report["missing_workflow_references"] == ["tests/test_example.py"]


def test_unsafe_or_duplicate_manifest_paths_are_rejected(tmp_path: Path) -> None:
    unsafe = _base_manifest()
    unsafe["core_feature_paths"] = ["../outside.py"]
    with pytest.raises(checker.FeatureSurfaceError, match="unsafe relative path"):
        checker.validate_feature_surface(
            _write_manifest(tmp_path, unsafe),
            repo_root=tmp_path,
            run_import_probes=False,
        )

    duplicate = _base_manifest()
    duplicate["guard_paths"] = ["src/example.py"]
    with pytest.raises(checker.FeatureSurfaceError, match="overlap"):
        checker.validate_feature_surface(
            _write_manifest(tmp_path, duplicate),
            repo_root=tmp_path,
            run_import_probes=False,
        )
