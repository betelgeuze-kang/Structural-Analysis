from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_core_quality.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_core_quality", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_core_quality_manifest_contract() -> None:
    module = _load_module()
    payload = module.load_manifest()

    module.check_contract(payload)

    assert payload["coverage"]["minimum_percent"] == 85
    assert payload["compatibility_matrix"]["required_coordinate_count"] == 9
    assert len(payload["coverage"]["tests"]) == 8


def test_core_quality_commands_are_manifest_driven(tmp_path: Path) -> None:
    module = _load_module()
    payload = module.load_manifest()

    typecheck = module.typecheck_command(payload)
    coverage_run, coverage_report = module.coverage_commands(
        payload,
        data_file=tmp_path / ".coverage",
    )

    assert typecheck[:3] == [sys.executable, "-m", "mypy"]
    assert set(payload["typecheck"]["paths"]).issubset(typecheck)
    assert coverage_run[:5] == [sys.executable, "-m", "coverage", "run", "-m"]
    assert set(payload["coverage"]["tests"]).issubset(coverage_run)
    assert "--fail-under=85" in coverage_report


def test_workflow_matches_manifest_matrix() -> None:
    manifest = json.loads(
        (ROOT / "artifacts" / "manifests" / "core_quality.json").read_text(
            encoding="utf-8"
        )
    )
    workflow = (ROOT / manifest["compatibility_matrix"]["workflow"]).read_text(
        encoding="utf-8"
    )

    for os_name in manifest["compatibility_matrix"]["operating_systems"]:
        assert os_name in workflow
    for version in manifest["compatibility_matrix"]["python_versions"]:
        assert f'"{version}"' in workflow
    assert "python scripts/check_core_quality.py" in workflow
