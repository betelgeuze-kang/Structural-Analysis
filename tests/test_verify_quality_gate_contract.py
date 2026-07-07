from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_quality_gate_module() -> ModuleType:
    script_path = REPO_ROOT / "scripts" / "verify_quality_gate.py"
    spec = importlib.util.spec_from_file_location("verify_quality_gate_contract", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pytest_targets(commands: list[list[str]]) -> set[str]:
    targets: set[str] = set()
    for command in commands:
        if "pytest" not in command:
            continue
        targets.update(item for item in command if item.startswith("tests/"))
    return targets


def test_pr_quality_gate_keeps_core_adapter_and_viewer_regression_tests() -> None:
    gate = _load_quality_gate_module()

    targets = _pytest_targets(gate._command_groups("pr"))

    assert "tests/test_structural_analysis_core_api.py" in targets
    assert "tests/test_midas_mgt_nodal_load_contract.py" in targets
    assert "tests/test_structure_viewer_dom_safety_contract.py" in targets
    assert "tests/test_verify_quality_gate_contract.py" in targets
