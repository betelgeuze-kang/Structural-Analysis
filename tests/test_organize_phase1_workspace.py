from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "implementation" / "phase1" / "organize_phase1_workspace.py"
SPEC = importlib.util.spec_from_file_location("organize_phase1_workspace", SCRIPT_PATH)
assert SPEC is not None
organize_phase1_workspace = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(organize_phase1_workspace)


def test_excludes_generated_directory_parts_without_runtime_specific_names() -> None:
    excluded = [
        Path("implementation/phase1/workspace/reports/report.json"),
        Path("implementation/phase1/structural_rust_solver/target/debug/build.log"),
        Path("implementation/phase1/pkg/__pycache__/module.pyc"),
    ]

    for path in excluded:
        assert organize_phase1_workspace._is_excluded(path)

    assert not organize_phase1_workspace._is_excluded(
        Path("implementation/phase1/src/structural_solver.py")
    )


def test_groups_core_model_scripts_without_domain_specific_runtime_names() -> None:
    assert organize_phase1_workspace._group_script("krylov_projection_solver.py") == "core_models"
    assert organize_phase1_workspace._group_script("gnn_core_model.py") == "core_models"
