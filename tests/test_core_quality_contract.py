from __future__ import annotations

from copy import deepcopy
import importlib.util
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

    assert payload["coverage"]["branch"] is True
    assert payload["coverage"]["minimum_percent"] == 85
    assert payload["compatibility_matrix"]["required_coordinate_count"] == 9
    assert len(payload["coverage"]["tests"]) == 8
    assert len(payload["typecheck"]["paths"]) == 5


def test_core_quality_commands_are_manifest_driven() -> None:
    module = _load_module()
    payload = module.load_manifest()

    typecheck = module.typecheck_command(payload)
    coverage_run, coverage_report = module.coverage_commands(payload)

    assert typecheck[:5] == [
        sys.executable,
        "-m",
        "mypy",
        "--config-file",
        "pyproject.toml",
    ]
    assert set(payload["typecheck"]["paths"]).issubset(typecheck)
    assert coverage_run[:5] == [
        sys.executable,
        "-m",
        "coverage",
        "run",
        "--rcfile=.coveragerc",
    ]
    assert set(payload["coverage"]["tests"]).issubset(coverage_run)
    assert "--fail-under=85" in coverage_report


def test_contract_rejects_quietly_weakened_threshold_or_matrix() -> None:
    module = _load_module()
    payload = module.load_manifest()

    weakened_coverage = deepcopy(payload)
    weakened_coverage["coverage"]["minimum_percent"] = 84
    try:
        module.check_contract(weakened_coverage)
    except ValueError as exc:
        assert "may not be below 85%" in str(exc)
    else:
        raise AssertionError("weakened coverage threshold was accepted")

    weakened_matrix = deepcopy(payload)
    weakened_matrix["compatibility_matrix"]["python_versions"] = ["3.10", "3.12"]
    weakened_matrix["compatibility_matrix"]["required_coordinate_count"] = 6
    try:
        module.check_contract(weakened_matrix)
    except ValueError as exc:
        assert "Python versions were weakened" in str(exc)
    else:
        raise AssertionError("weakened compatibility matrix was accepted")


def test_workflow_matches_manifest_matrix_and_runs_bounded_gate() -> None:
    module = _load_module()
    payload = module.load_manifest()
    workflow = (ROOT / payload["compatibility_matrix"]["workflow"]).read_text(
        encoding="utf-8"
    )

    for os_name in payload["compatibility_matrix"]["operating_systems"]:
        assert os_name in workflow
    for version in payload["compatibility_matrix"]["python_versions"]:
        assert f'"{version}"' in workflow
    assert "python scripts/check_core_quality.py" in workflow
    assert "fail-fast: false" in workflow
