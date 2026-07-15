from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE_ROOT = REPO_ROOT / "src/structural_analysis/engine_v2"
SHARED_MODULE = "structural_analysis.engine_v2.elements.linear_frame_truss_v1"
PUBLIC_ELEMENT_NAMES = {
    "frame_local_stiffness_v1",
    "frame_reference_axis_v1",
    "frame_transform_v1",
    "truss_local_stiffness_v1",
    "validate_linear_frame_truss_references_v1",
}


def _imports(path: Path) -> list[tuple[str, tuple[str, ...]]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[tuple[str, tuple[str, ...]]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imports.append(
                (node.module or "", tuple(alias.name for alias in node.names))
            )
        elif isinstance(node, ast.Import):
            imports.extend((alias.name, ()) for alias in node.names)
    return imports


def test_sparse_plan_and_hip_assembly_do_not_depend_on_cpu_reference_internals() -> (
    None
):
    targets = (
        ENGINE_ROOT / "contracts/execution_plan_v2.py",
        ENGINE_ROOT / "assembly_backend/plan.py",
    )
    forbidden_private_names = {
        "_frame_local_stiffness",
        "_frame_transform",
        "_truss_local_stiffness",
        "_validate_buffer_contract",
        "_validate_element_references",
    }

    for target in targets:
        imports = _imports(target)
        assert all("backends.cpu_reference" not in module for module, _ in imports), (
            target
        )
        imported_names = {name for _, names in imports for name in names}
        assert forbidden_private_names.isdisjoint(imported_names), target


def test_sparse_plan_and_hip_assembly_import_the_versioned_shared_module() -> None:
    execution_imports = _imports(ENGINE_ROOT / "contracts/execution_plan_v2.py")
    assembly_imports = _imports(ENGINE_ROOT / "assembly_backend/plan.py")
    execution_names = {
        name
        for module, names in execution_imports
        if module == SHARED_MODULE
        for name in names
    }
    assembly_names = {
        name
        for module, names in assembly_imports
        if module == SHARED_MODULE
        for name in names
    }

    assert {
        "frame_local_stiffness_v1",
        "frame_transform_v1",
        "truss_local_stiffness_v1",
        "validate_linear_frame_truss_references_v1",
    } <= execution_names
    assert {"frame_reference_axis_v1", "frame_transform_v1"} <= assembly_names
    assert not any(name.startswith("_") for name in execution_names | assembly_names)


def test_cpu_reference_is_a_compatibility_consumer_of_public_shared_semantics() -> None:
    imports = _imports(ENGINE_ROOT / "backends/cpu_reference/linear_static.py")
    shared_names = {
        name for module, names in imports if module == SHARED_MODULE for name in names
    }

    assert PUBLIC_ELEMENT_NAMES - {"frame_reference_axis_v1"} <= shared_names
    assert "LINEAR_FRAME_TRUSS_OPERATOR_COMPATIBILITY_VERSION_V1" in shared_names
    assert not any(name.startswith("_") for name in shared_names)
