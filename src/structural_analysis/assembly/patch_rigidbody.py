"""Narrow axial constant-strain patch and rigid-body nullspace helpers."""

from __future__ import annotations

from typing import Any

import numpy as np

from structural_analysis.assembly.linear_static import DOF_LABELS, assemble_linear_static
from structural_analysis.elements.axial import axial_element_properties
from structural_analysis.model.schema import CanonicalModel
from structural_analysis.solvers.linear.static import solve_linear_static

STRAIN_TOLERANCE = 1.0e-10
DISPLACEMENT_TOLERANCE_M = 1.0e-10
PATCH_ELEMENT_COUNTS = (1, 2, 4)
PATCH_LOAD_FX_KN = 100.0
PATCH_TOTAL_LENGTH_M = 2.0
PATCH_ELASTIC_MODULUS = 200000.0
PATCH_AREA = 0.01


def build_axial_constant_strain_patch_payload(
    *,
    case_id: str,
    element_count: int,
    load_fx: float = PATCH_LOAD_FX_KN,
    total_length_m: float = PATCH_TOTAL_LENGTH_M,
) -> dict[str, Any]:
    if element_count <= 0:
        raise ValueError("element_count must be positive.")
    nodes = [
        {
            "id": f"N{index + 1}",
            "coordinates": [total_length_m * index / element_count, 0.0, 0.0],
        }
        for index in range(element_count + 1)
    ]
    elements = [
        {
            "id": f"E{index + 1}",
            "type": "truss",
            "nodes": [f"N{index + 1}", f"N{index + 2}"],
            "section": "S1",
            "material": "M1",
        }
        for index in range(element_count)
    ]
    supports = [{"id": "SUP1", "node": "N1", "dofs": "all"}]
    supports.extend(
        {
            "id": f"SUP{index + 1}",
            "node": f"N{index + 1}",
            "dofs": ["UY", "UZ"],
        }
        for index in range(1, element_count + 1)
    )
    expected_tip_ux = load_fx * total_length_m / (PATCH_ELASTIC_MODULUS * PATCH_AREA)
    return {
        "schema_version": "structural-analysis-canonical-model.v1",
        "units": {"length": "m", "force": "kN"},
        "coordinate_system": {"axis_order": ["X", "Y", "Z"], "up_axis": "Z"},
        "nodes": nodes,
        "elements": elements,
        "materials": [{"id": "M1", "type": "elastic", "elastic_modulus": PATCH_ELASTIC_MODULUS}],
        "sections": [{"id": "S1", "type": "bar", "area": PATCH_AREA}],
        "loads": [
            {
                "id": "P1",
                "node": f"N{element_count + 1}",
                "components": [load_fx, 0.0, 0.0],
            }
        ],
        "supports": supports,
        "unsupported_features": [],
        "warnings": [],
        "metadata": {
            "case_id": case_id,
            "truth_class": "analytic_truth",
            "expected_tip_ux": expected_tip_ux,
            "expected_axial_strain": expected_tip_ux / total_length_m,
            "claim_boundary": "linear_axial_constant_strain_component_patch_only",
        },
    }


def build_rigid_body_free_translation_payload(
    *,
    case_id: str = "phase2_axial_rigid_body_free_translation",
) -> dict[str, Any]:
    payload = build_axial_constant_strain_patch_payload(
        case_id=case_id,
        element_count=1,
    )
    payload["supports"] = [
        {"id": "SUP1", "node": "N1", "dofs": ["UY", "UZ"]},
        {"id": "SUP2", "node": "N2", "dofs": ["UY", "UZ"]},
    ]
    payload["metadata"] = {
        "case_id": case_id,
        "truth_class": "negative_rigid_body_guard",
        "expected_nullspace_modes": ["UX_translation"],
        "claim_boundary": "rigid_body_free_translation_nullspace_guard_only",
    }
    return payload


def _model_from_payload(payload: dict[str, Any]) -> CanonicalModel:
    from tempfile import TemporaryDirectory
    from pathlib import Path
    import json

    from structural_analysis import load_model

    with TemporaryDirectory() as tmp_dir:
        model_path = Path(tmp_dir) / "model.json"
        model_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return load_model(model_path)


def axial_element_strains(
    model: CanonicalModel,
    displacements: np.ndarray,
) -> list[dict[str, Any]]:
    node_ids = tuple(str(node.get("id", "")) for node in model.nodes)
    node_index = {node_id: index for index, node_id in enumerate(node_ids)}
    coordinates = {
        str(node.get("id", "")): tuple(float(value) for value in node["coordinates"])
        for node in model.nodes
    }
    materials = {str(row.get("id", "")): row for row in model.materials}
    sections = {str(row.get("id", "")): row for row in model.sections}
    rows: list[dict[str, Any]] = []
    for element in model.elements:
        element_id = str(element.get("id", ""))
        raw_nodes = element.get("nodes")
        if not isinstance(raw_nodes, list) or len(raw_nodes) != 2:
            continue
        node_pair = (str(raw_nodes[0]), str(raw_nodes[1]))
        material = materials.get(str(element.get("material", "")))
        section = sections.get(str(element.get("section", "")))
        properties = axial_element_properties(
            element_id=element_id,
            node_ids=node_pair,
            start_coordinates=coordinates[node_pair[0]],
            end_coordinates=coordinates[node_pair[1]],
            elastic_modulus=float(material.get("elastic_modulus")),
            area=float(section.get("area")),
        )
        base_i = 3 * node_index[node_pair[0]]
        base_j = 3 * node_index[node_pair[1]]
        displacement_i = displacements[base_i : base_i + 3]
        displacement_j = displacements[base_j : base_j + 3]
        direction = np.array(properties.direction_cosines, dtype=float)
        delta_axial = float(direction @ (displacement_j - displacement_i))
        axial_strain = delta_axial / properties.length
        rows.append(
            {
                "element_id": element_id,
                "length_m": properties.length,
                "axial_strain": axial_strain,
            }
        )
    return rows


def free_stiffness_nullspace_detail(model: CanonicalModel) -> dict[str, Any]:
    assembly, unsupported = assemble_linear_static(model)
    if assembly is None:
        return {
            "pass": False,
            "unsupported": unsupported,
        }
    constrained = set(assembly.constrained_dofs)
    all_dofs = set(range(assembly.loads.shape[0]))
    free = sorted(all_dofs - constrained)
    free_stiffness = assembly.stiffness[np.ix_(free, free)]
    dense = np.asarray(free_stiffness, dtype=float)
    rank = int(np.linalg.matrix_rank(dense))
    order = int(dense.shape[0])
    deficiency = order - rank
    return {
        "pass": True,
        "free_dof_count": order,
        "free_stiffness_rank": rank,
        "nullspace_dimension": deficiency,
        "free_dof_labels": [
            {
                "node_id": assembly.node_ids[dof_index // 3],
                "dof": DOF_LABELS[dof_index % 3],
            }
            for dof_index in free
        ],
    }


def constant_strain_patch_check(
    *,
    element_count: int,
    tolerance: float = 1.0e-8,
) -> dict[str, Any]:
    case_id = f"phase2_constant_strain_patch_e{element_count}"
    payload = build_axial_constant_strain_patch_payload(case_id=case_id, element_count=element_count)
    model = _model_from_payload(payload)
    solution = solve_linear_static(model, tolerance=tolerance)
    metrics = solution.metrics
    expected_tip_ux = float(payload["metadata"]["expected_tip_ux"])
    expected_strain = float(payload["metadata"]["expected_axial_strain"])
    tip_node = f"N{element_count + 1}"
    actual_tip_ux = float(metrics["displacements"][tip_node]["UX"])
    node_ids = tuple(str(node.get("id", "")) for node in model.nodes)
    displacement_vector = np.zeros(len(node_ids) * 3, dtype=float)
    for node_index, node_id in enumerate(node_ids):
        for offset, label in enumerate(DOF_LABELS):
            displacement_vector[3 * node_index + offset] = float(
                metrics["displacements"][node_id][label]
            )
    strain_rows = axial_element_strains(model, displacement_vector)
    strains = [row["axial_strain"] for row in strain_rows]
    strain_spread = max(strains) - min(strains) if strains else float("inf")
    contract_pass = (
        solution.status == "ready"
        and abs(actual_tip_ux - expected_tip_ux) <= DISPLACEMENT_TOLERANCE_M
        and strain_spread <= STRAIN_TOLERANCE
        and all(abs(strain - expected_strain) <= STRAIN_TOLERANCE for strain in strains)
        and float(metrics["relative_residual"]) <= tolerance
        and metrics["regularization_used"] is False
        and metrics["fallback_used"] is False
    )
    return {
        "case_id": case_id,
        "element_count": element_count,
        "status": solution.status,
        "contract_pass": contract_pass,
        "expected_tip_ux": expected_tip_ux,
        "actual_tip_ux": actual_tip_ux,
        "expected_axial_strain": expected_strain,
        "element_strains": strain_rows,
        "axial_strain_spread": strain_spread,
        "relative_residual": float(metrics["relative_residual"]),
        "regularization_used": metrics["regularization_used"],
        "fallback_used": metrics["fallback_used"],
        "constant_strain_gate_passed": contract_pass,
    }


def run_constant_strain_patch_suite(
    *,
    element_counts: tuple[int, ...] = PATCH_ELEMENT_COUNTS,
    tolerance: float = 1.0e-8,
) -> dict[str, Any]:
    rows = [constant_strain_patch_check(element_count=count, tolerance=tolerance) for count in element_counts]
    tip_values = [row["actual_tip_ux"] for row in rows]
    tip_spread = max(tip_values) - min(tip_values) if tip_values else float("inf")
    mesh_independence_passed = tip_spread <= DISPLACEMENT_TOLERANCE_M
    suite_passed = (
        all(row["constant_strain_gate_passed"] for row in rows)
        and mesh_independence_passed
    )
    return {
        "element_counts": list(element_counts),
        "rows": rows,
        "tip_displacements_m": tip_values,
        "tip_displacement_spread_m": tip_spread,
        "mesh_independence_gate_passed": mesh_independence_passed,
        "constant_strain_patch_suite_passed": suite_passed,
        "claim_boundary": (
            "Linear axial truss constant-strain component patch only. "
            "Not a general 2D/3D continuum, frame, or shell patch test."
        ),
    }


def rigid_body_translation_guard_check(*, tolerance: float = 1.0e-8) -> dict[str, Any]:
    payload = build_rigid_body_free_translation_payload()
    model = _model_from_payload(payload)
    solution = solve_linear_static(model, tolerance=tolerance)
    nullspace = free_stiffness_nullspace_detail(model)
    unsupported_kinds = {row.get("kind") for row in solution.unsupported_features}
    blocked_without_regularization = (
        solution.status == "blocked"
        and "linear_static_singular_stiffness" in unsupported_kinds
        and solution.metrics["regularization_used"] is False
        and solution.metrics["fallback_used"] is False
    )
    nullspace_passed = (
        nullspace.get("pass") is True
        and nullspace.get("nullspace_dimension") == 1
        and nullspace.get("free_stiffness_rank") == 1
        and nullspace.get("free_dof_count") == 2
    )
    contract_pass = blocked_without_regularization and nullspace_passed
    return {
        "case_id": payload["metadata"]["case_id"],
        "status": solution.status,
        "contract_pass": contract_pass,
        "blocked_without_regularization": blocked_without_regularization,
        "unsupported_kinds": sorted(unsupported_kinds),
        "nullspace_detail": nullspace,
        "nullspace_gate_passed": nullspace_passed,
        "regularization_used": solution.metrics.get("regularization_used"),
        "fallback_used": solution.metrics.get("fallback_used"),
        "free_stiffness_order": solution.metrics.get("free_stiffness_order"),
        "rigid_body_translation_guard_passed": contract_pass,
        "claim_boundary": (
            "Rigid-body free X translation nullspace guard on a 2-node axial truss only. "
            "Does not cover general 6-DOF frame/shell rigid-body modes or production guards."
        ),
    }
