from __future__ import annotations

import ast
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
CORE_ROOTS = (
    REPO_ROOT / "src/structural_analysis/engine_v2",
    REPO_ROOT / "src/structural_analysis/model_ir",
)
ALLOWED_EXTERNAL_ROOTS = {"jsonschema", "numpy", "structural_analysis"}
ALLOWED_INTERNAL_PREFIXES = (
    "structural_analysis.engine_v2.cpu_fgmres",
    "structural_analysis.engine_v2.contracts",
    "structural_analysis.model_ir",
)
FORBIDDEN_LEGACY_PREFIXES = (
    "structural_analysis.api",
    "structural_analysis.model",
    "structural_analysis.reporting",
    "structural_analysis.results",
)
FORBIDDEN_FRAGMENTS = (
    ".assembly_backend",
    ".backends",
    ".hip",
    ".rocm",
    ".results",
    ".solvers",
)


def _python_sources() -> tuple[Path, ...]:
    return tuple(sorted(path for root in CORE_ROOTS for path in root.rglob("*.py")))


def test_engine_v2_core_import_graph_is_backend_and_solver_neutral() -> None:
    violations: list[str] = []

    for path in _python_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names.append(node.module)
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "__import__"
            ):
                violations.append(f"{path}: dynamic __import__ is forbidden")

            for name in names:
                root = name.split(".", 1)[0]
                if root not in sys.stdlib_module_names | ALLOWED_EXTERNAL_ROOTS:
                    violations.append(f"{path}: undeclared dependency {name}")
                if name.startswith("structural_analysis") and not name.startswith(
                    ALLOWED_INTERNAL_PREFIXES
                ):
                    violations.append(f"{path}: non-core internal dependency {name}")
                if any(
                    name == prefix or name.startswith(f"{prefix}.")
                    for prefix in FORBIDDEN_LEGACY_PREFIXES
                ):
                    violations.append(f"{path}: legacy public API dependency {name}")
                if any(fragment in name.lower() for fragment in FORBIDDEN_FRAGMENTS):
                    violations.append(f"{path}: later-PR dependency {name}")

    assert violations == []


def test_engine_v2_core_source_inventory_is_explicit_and_backend_neutral() -> None:
    relative_sources = {
        path.relative_to(REPO_ROOT).as_posix() for path in _python_sources()
    }

    assert all(
        not any(fragment in source.lower() for fragment in FORBIDDEN_FRAGMENTS)
        for source in relative_sources
    )
    assert relative_sources == {
        "src/structural_analysis/engine_v2/__init__.py",
        "src/structural_analysis/engine_v2/cpu_fgmres.py",
        "src/structural_analysis/engine_v2/cpu_fgmres_checkpoint.py",
        "src/structural_analysis/engine_v2/cpu_fgmres_tangent.py",
        "src/structural_analysis/engine_v2/contracts/__init__.py",
        "src/structural_analysis/engine_v2/contracts/_canonical.py",
        "src/structural_analysis/engine_v2/contracts/current_tangent_operator.py",
        "src/structural_analysis/engine_v2/contracts/engineering_result.py",
        "src/structural_analysis/engine_v2/contracts/equation_scaling.py",
        "src/structural_analysis/engine_v2/contracts/execution_plan.py",
        "src/structural_analysis/engine_v2/contracts/execution_plan_reduced_csr.py",
        "src/structural_analysis/engine_v2/contracts/material_state_bundle.py",
        "src/structural_analysis/engine_v2/contracts/nonlinear_recovery.py",
        "src/structural_analysis/engine_v2/contracts/nonlinear_result.py",
        "src/structural_analysis/engine_v2/contracts/result_ir.py",
        "src/structural_analysis/engine_v2/contracts/result_quantity.py",
        "src/structural_analysis/engine_v2/contracts/solver_episode.py",
        "src/structural_analysis/engine_v2/contracts/spectral_result.py",
        "src/structural_analysis/engine_v2/contracts/state_ir.py",
        "src/structural_analysis/engine_v2/contracts/state_ir_binary.py",
        "src/structural_analysis/engine_v2/contracts/transient_result.py",
        "src/structural_analysis/engine_v2/contracts/vector_artifact.py",
        "src/structural_analysis/model_ir/__init__.py",
        "src/structural_analysis/model_ir/loader.py",
        "src/structural_analysis/model_ir/types.py",
        "src/structural_analysis/model_ir/validation.py",
    }
