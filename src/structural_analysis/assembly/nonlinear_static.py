"""Global nonlinear static assembly for a narrow 1D axial chain seed."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

from structural_analysis.model.schema import CanonicalModel
from structural_analysis.solvers.nonlinear.newton import RESIDUAL_FORMULA


class AxialMaterialLaw(Protocol):
    """Scalar axial constitutive law evaluated on element elongation."""

    def internal_force(self, elongation_m: float) -> float: ...

    def tangent_stiffness(self, elongation_m: float) -> float: ...


@dataclass(frozen=True)
class CubicSpringAxialMaterialLaw:
    """Cubic spring law reused from the Phase 2 material breadth seed."""

    linear_stiffness_kn_per_m: float = 100.0
    cubic_stiffness_kn_per_m3: float = 1000.0
    model_kind: str = "scalar_nonlinear_axial_cubic_spring"

    def internal_force(self, elongation_m: float) -> float:
        u = float(elongation_m)
        return (
            self.linear_stiffness_kn_per_m * u
            + self.cubic_stiffness_kn_per_m3 * u**3
        )

    def tangent_stiffness(self, elongation_m: float) -> float:
        u = float(elongation_m)
        return self.linear_stiffness_kn_per_m + 3.0 * self.cubic_stiffness_kn_per_m3 * u**2


@dataclass(frozen=True)
class StrainCubicAxialMaterialLaw:
    """Length-aware cubic axial law for deterministic mesh refinement checks."""

    length_m: float
    linear_strain_stiffness_kn: float = 200.0
    cubic_strain_stiffness_kn: float = 1000.0
    model_kind: str = "strain_nonlinear_axial_cubic_bar"

    def internal_force(self, elongation_m: float) -> float:
        strain = float(elongation_m) / self.length_m
        return (
            self.linear_strain_stiffness_kn * strain
            + self.cubic_strain_stiffness_kn * strain**3
        )

    def tangent_stiffness(self, elongation_m: float) -> float:
        strain = float(elongation_m) / self.length_m
        return (
            self.linear_strain_stiffness_kn
            + 3.0 * self.cubic_strain_stiffness_kn * strain**2
        ) / self.length_m


@dataclass(frozen=True)
class AxialChainElement:
    element_id: str
    node_i: int
    node_j: int
    length_m: float
    material: AxialMaterialLaw


@dataclass(frozen=True)
class AxialChainMeshProblem:
    """Deterministic 1D axial chain with fixed nodes and nodal external loads."""

    case_id: str
    node_count: int
    elements: tuple[AxialChainElement, ...]
    fixed_nodes: tuple[int, ...]
    external_forces_kn: tuple[tuple[int, float], ...]
    initial_displacements_m: tuple[float, ...]

    def reference_force_scale(self) -> float:
        external = sum(abs(force) for _, force in self.external_forces_kn)
        return max(external, 1.0)


@dataclass(frozen=True)
class AxialChainAssemblyState:
    residual_formula: str
    free_node_indices: tuple[int, ...]
    displacements_m: np.ndarray
    residual_kn: np.ndarray
    jacobian_kn_per_m: np.ndarray
    internal_forces_kn: np.ndarray
    external_forces_kn: np.ndarray
    reactions_kn: np.ndarray
    element_forces_kn: tuple[dict[str, Any], ...]


def default_phase2_axial_chain_mesh_problem() -> AxialChainMeshProblem:
    """3-node / 2-element axial chain using the cubic-spring breadth material law."""
    material = CubicSpringAxialMaterialLaw()
    return AxialChainMeshProblem(
        case_id="phase2_material_mesh_newton_axial_chain_cubic_spring",
        node_count=3,
        elements=(
            AxialChainElement("e1", 0, 1, 1.0, material),
            AxialChainElement("e2", 1, 2, 1.0, material),
        ),
        fixed_nodes=(0,),
        external_forces_kn=((2, 100.0),),
        initial_displacements_m=(0.0, 0.0, 0.0),
    )


def axial_chain_mesh_problem_from_canonical_model(
    model: CanonicalModel,
) -> tuple[AxialChainMeshProblem | None, list[dict[str, Any]]]:
    """Build the narrow 1D material Newton seed problem from a canonical model."""
    unsupported: list[dict[str, Any]] = []
    if model.units.length != "m" or model.units.force != "kN":
        unsupported.append(
            {
                "kind": "nonlinear_material_mesh_units_not_supported",
                "detail": "Developer Preview material mesh seed requires m/kN units.",
            }
        )
    node_ids = tuple(str(node.get("id", "")) for node in model.nodes)
    if not node_ids:
        unsupported.append({"kind": "nonlinear_material_mesh_nodes_missing"})
        return None, unsupported
    if len(set(node_ids)) != len(node_ids):
        unsupported.append({"kind": "nonlinear_material_mesh_duplicate_nodes"})
        return None, unsupported
    node_index = {node_id: index for index, node_id in enumerate(node_ids)}
    coordinates = _canonical_node_coordinates(model.nodes, unsupported)
    materials = {str(row.get("id", "")): row for row in model.materials}

    elements: list[AxialChainElement] = []
    for element in model.elements:
        element_id = str(element.get("id", ""))
        element_type = str(element.get("type", "")).lower()
        if element_type not in {"truss", "axial"}:
            unsupported.append(
                {
                    "kind": "nonlinear_material_mesh_element_not_supported",
                    "element": element_id,
                    "element_type": element.get("type", ""),
                }
            )
            continue
        raw_nodes = element.get("nodes")
        if not isinstance(raw_nodes, list) or len(raw_nodes) != 2:
            unsupported.append(
                {"kind": "nonlinear_material_mesh_element_connectivity_invalid", "element": element_id}
            )
            continue
        start_id, end_id = str(raw_nodes[0]), str(raw_nodes[1])
        if start_id not in node_index or end_id not in node_index:
            unsupported.append({"kind": "nonlinear_material_mesh_element_node_missing", "element": element_id})
            continue
        length_m = _axis_aligned_x_length(
            element_id=element_id,
            start_coordinates=coordinates.get(start_id),
            end_coordinates=coordinates.get(end_id),
            unsupported=unsupported,
        )
        material = _cubic_material_law(
            materials.get(str(element.get("material", ""))),
            element_id=element_id,
            unsupported=unsupported,
        )
        if length_m is None or material is None:
            continue
        elements.append(
            AxialChainElement(
                element_id=element_id,
                node_i=node_index[start_id],
                node_j=node_index[end_id],
                length_m=length_m,
                material=material,
            )
        )

    fixed_nodes = _canonical_fixed_nodes(model.supports, node_index, unsupported)
    external_forces = _canonical_external_forces(model.loads, node_index, unsupported)
    if not elements:
        unsupported.append({"kind": "nonlinear_material_mesh_elements_missing"})
    if not fixed_nodes:
        unsupported.append({"kind": "nonlinear_material_mesh_supports_missing"})
    if not external_forces:
        unsupported.append({"kind": "nonlinear_material_mesh_loads_missing"})
    if unsupported:
        return None, unsupported
    return (
        AxialChainMeshProblem(
            case_id=str(
                model.metadata.get(
                    "case_id",
                    "developer_preview_material_mesh_newton_canonical_axial_chain",
                )
            ),
            node_count=len(node_ids),
            elements=tuple(elements),
            fixed_nodes=tuple(sorted(set(fixed_nodes))),
            external_forces_kn=tuple(external_forces),
            initial_displacements_m=tuple(0.0 for _ in node_ids),
        ),
        [],
    )


def single_element_axial_chain_mesh_problem() -> AxialChainMeshProblem:
    """2-node / 1-element chain with the same total length and load for partition checks."""
    material = CubicSpringAxialMaterialLaw()
    return AxialChainMeshProblem(
        case_id="phase2_material_mesh_newton_axial_chain_single_element",
        node_count=2,
        elements=(AxialChainElement("e1", 0, 1, 2.0, material),),
        fixed_nodes=(0,),
        external_forces_kn=((1, 100.0),),
        initial_displacements_m=(0.0, 0.0),
    )


def refined_strain_cubic_axial_chain_mesh_problem(
    *,
    element_count: int,
    total_length_m: float = 2.0,
    external_force_kn: float = 100.0,
) -> AxialChainMeshProblem:
    """Build a length-aware 1D chain for mesh-refinement invariance checks."""
    if element_count <= 0:
        raise ValueError("element_count must be positive")
    if total_length_m <= 0.0:
        raise ValueError("total_length_m must be positive")
    element_length_m = total_length_m / float(element_count)
    elements = tuple(
        AxialChainElement(
            element_id=f"e{index + 1}",
            node_i=index,
            node_j=index + 1,
            length_m=element_length_m,
            material=StrainCubicAxialMaterialLaw(length_m=element_length_m),
        )
        for index in range(element_count)
    )
    return AxialChainMeshProblem(
        case_id=f"phase2_material_mesh_refinement_strain_cubic_{element_count}_element",
        node_count=element_count + 1,
        elements=elements,
        fixed_nodes=(0,),
        external_forces_kn=((element_count, external_force_kn),),
        initial_displacements_m=tuple(0.0 for _ in range(element_count + 1)),
    )


def _full_displacement_vector(
    problem: AxialChainMeshProblem,
    free_displacements_m: np.ndarray,
) -> np.ndarray:
    displacements = np.array(problem.initial_displacements_m, dtype=float)
    for index, node_index in enumerate(_free_node_indices(problem)):
        displacements[node_index] = float(free_displacements_m[index])
    for node_index in problem.fixed_nodes:
        displacements[node_index] = 0.0
    return displacements


def _canonical_node_coordinates(
    nodes: list[dict[str, Any]],
    unsupported: list[dict[str, Any]],
) -> dict[str, tuple[float, float, float]]:
    coordinates: dict[str, tuple[float, float, float]] = {}
    for node in nodes:
        node_id = str(node.get("id", ""))
        raw = node.get("coordinates")
        if not isinstance(raw, list) or len(raw) != 3:
            unsupported.append({"kind": "nonlinear_material_mesh_node_coordinates_invalid", "node": node_id})
            continue
        try:
            coordinates[node_id] = (float(raw[0]), float(raw[1]), float(raw[2]))
        except (TypeError, ValueError):
            unsupported.append({"kind": "nonlinear_material_mesh_node_coordinates_invalid", "node": node_id})
    return coordinates


def _axis_aligned_x_length(
    *,
    element_id: str,
    start_coordinates: tuple[float, float, float] | None,
    end_coordinates: tuple[float, float, float] | None,
    unsupported: list[dict[str, Any]],
) -> float | None:
    if start_coordinates is None or end_coordinates is None:
        unsupported.append({"kind": "nonlinear_material_mesh_element_coordinates_missing", "element": element_id})
        return None
    dx = end_coordinates[0] - start_coordinates[0]
    dy = end_coordinates[1] - start_coordinates[1]
    dz = end_coordinates[2] - start_coordinates[2]
    if abs(dy) > 1.0e-12 or abs(dz) > 1.0e-12 or dx <= 0.0:
        unsupported.append(
            {
                "kind": "nonlinear_material_mesh_element_not_1d_x_axis",
                "element": element_id,
            }
        )
        return None
    return float(dx)


def _cubic_material_law(
    material: dict[str, Any] | None,
    *,
    element_id: str,
    unsupported: list[dict[str, Any]],
) -> CubicSpringAxialMaterialLaw | None:
    if not material:
        unsupported.append({"kind": "nonlinear_material_mesh_material_missing", "element": element_id})
        return None
    material_type = str(material.get("type", "")).lower()
    if material_type not in {"cubic_spring", "nonlinear_cubic_axial"}:
        unsupported.append(
            {
                "kind": "nonlinear_material_mesh_material_law_not_supported",
                "element": element_id,
                "material_type": material.get("type", ""),
            }
        )
        return None
    try:
        linear = float(material.get("linear_stiffness"))
        cubic = float(material.get("cubic_stiffness"))
    except (TypeError, ValueError):
        unsupported.append({"kind": "nonlinear_material_mesh_material_parameters_invalid", "element": element_id})
        return None
    if linear <= 0.0 or cubic < 0.0:
        unsupported.append({"kind": "nonlinear_material_mesh_material_parameters_invalid", "element": element_id})
        return None
    return CubicSpringAxialMaterialLaw(
        linear_stiffness_kn_per_m=linear,
        cubic_stiffness_kn_per_m3=cubic,
    )


def _canonical_fixed_nodes(
    supports: list[dict[str, Any]],
    node_index: dict[str, int],
    unsupported: list[dict[str, Any]],
) -> list[int]:
    fixed_nodes: list[int] = []
    for support in supports:
        node_id = str(support.get("node", support.get("node_id", "")))
        if node_id not in node_index:
            unsupported.append({"kind": "nonlinear_material_mesh_support_node_missing", "node": node_id})
            continue
        dofs = support.get("dofs", [])
        if not isinstance(dofs, list) or "UX" not in {str(dof) for dof in dofs}:
            unsupported.append({"kind": "nonlinear_material_mesh_support_ux_missing", "node": node_id})
            continue
        fixed_nodes.append(node_index[node_id])
    return fixed_nodes


def _canonical_external_forces(
    loads: list[dict[str, Any]],
    node_index: dict[str, int],
    unsupported: list[dict[str, Any]],
) -> list[tuple[int, float]]:
    external_forces: list[tuple[int, float]] = []
    for load in loads:
        node_id = str(load.get("node", load.get("node_id", "")))
        if node_id not in node_index:
            unsupported.append({"kind": "nonlinear_material_mesh_load_node_missing", "node": node_id})
            continue
        fx = _load_fx(load, unsupported)
        if fx is None:
            continue
        external_forces.append((node_index[node_id], fx))
    return external_forces


def _load_fx(load: dict[str, Any], unsupported: list[dict[str, Any]]) -> float | None:
    raw = load.get("components")
    if isinstance(raw, dict):
        try:
            fy = float(raw.get("FY", 0.0))
            fz = float(raw.get("FZ", 0.0))
            if abs(fy) > 0.0 or abs(fz) > 0.0:
                unsupported.append({"kind": "nonlinear_material_mesh_load_not_1d_x_axis"})
                return None
            return float(raw.get("FX", 0.0))
        except (TypeError, ValueError):
            unsupported.append({"kind": "nonlinear_material_mesh_load_components_invalid"})
            return None
    if isinstance(raw, list) and len(raw) == 3:
        try:
            if abs(float(raw[1])) > 0.0 or abs(float(raw[2])) > 0.0:
                unsupported.append({"kind": "nonlinear_material_mesh_load_not_1d_x_axis"})
                return None
            return float(raw[0])
        except (TypeError, ValueError):
            unsupported.append({"kind": "nonlinear_material_mesh_load_components_invalid"})
            return None
    unsupported.append({"kind": "nonlinear_material_mesh_load_components_invalid"})
    return None


def _free_node_indices(problem: AxialChainMeshProblem) -> tuple[int, ...]:
    fixed = set(problem.fixed_nodes)
    return tuple(index for index in range(problem.node_count) if index not in fixed)


def _external_force_vector(problem: AxialChainMeshProblem) -> np.ndarray:
    forces = np.zeros(problem.node_count, dtype=float)
    for node_index, force_kn in problem.external_forces_kn:
        forces[int(node_index)] += float(force_kn)
    return forces


def assemble_axial_chain_state(
    problem: AxialChainMeshProblem,
    free_displacements_m: np.ndarray,
) -> AxialChainAssemblyState:
    """Assemble global residual F_internal - F_external and consistent tangent on free DOFs."""
    free_nodes = _free_node_indices(problem)
    dof_count = len(free_nodes)
    displacements = _full_displacement_vector(problem, free_displacements_m)
    internal_forces = np.zeros(problem.node_count, dtype=float)
    jacobian = np.zeros((dof_count, dof_count), dtype=float)
    node_to_free = {node_index: free_index for free_index, node_index in enumerate(free_nodes)}
    element_forces: list[dict[str, Any]] = []

    for element in problem.elements:
        elongation_m = displacements[element.node_j] - displacements[element.node_i]
        force_kn = element.material.internal_force(elongation_m)
        tangent_kn_per_m = element.material.tangent_stiffness(elongation_m)
        internal_forces[element.node_i] -= force_kn
        internal_forces[element.node_j] += force_kn
        element_forces.append(
            {
                "element_id": element.element_id,
                "node_i": element.node_i,
                "node_j": element.node_j,
                "length_m": element.length_m,
                "elongation_m": elongation_m,
                "internal_force_kn": force_kn,
                "tangent_kn_per_m": tangent_kn_per_m,
            }
        )
        for node_a, sign_a in ((element.node_i, -1), (element.node_j, 1)):
            if node_a not in node_to_free:
                continue
            free_a = node_to_free[node_a]
            for node_b, sign_b in ((element.node_i, -1), (element.node_j, 1)):
                if node_b not in node_to_free:
                    continue
                free_b = node_to_free[node_b]
                jacobian[free_a, free_b] += sign_a * sign_b * tangent_kn_per_m

    external_forces = _external_force_vector(problem)
    residual = internal_forces[list(free_nodes)] - external_forces[list(free_nodes)]
    reactions = np.zeros(problem.node_count, dtype=float)
    for node_index in problem.fixed_nodes:
        reactions[node_index] = internal_forces[node_index] - external_forces[node_index]

    return AxialChainAssemblyState(
        residual_formula=RESIDUAL_FORMULA,
        free_node_indices=free_nodes,
        displacements_m=displacements,
        residual_kn=residual,
        jacobian_kn_per_m=jacobian,
        internal_forces_kn=internal_forces,
        external_forces_kn=external_forces,
        reactions_kn=reactions,
        element_forces_kn=tuple(element_forces),
    )


def finite_difference_assembled_jacobian_check(
    problem: AxialChainMeshProblem,
    free_displacements_m: np.ndarray,
    *,
    epsilon: float = 1.0e-7,
) -> dict[str, Any]:
    """Verify assembled tangent matches dR/du on free DOFs via central differences."""
    base_state = assemble_axial_chain_state(problem, free_displacements_m)
    analytic = base_state.jacobian_kn_per_m.copy()
    numeric = np.zeros_like(analytic)
    free_count = len(base_state.free_node_indices)
    for dof_index in range(free_count):
        forward = np.array(free_displacements_m, dtype=float)
        backward = np.array(free_displacements_m, dtype=float)
        forward[dof_index] += epsilon
        backward[dof_index] -= epsilon
        forward_residual = assemble_axial_chain_state(problem, forward).residual_kn
        backward_residual = assemble_axial_chain_state(problem, backward).residual_kn
        numeric[:, dof_index] = (forward_residual - backward_residual) / (2.0 * epsilon)
    error = float(np.max(np.abs(numeric - analytic)))
    return {
        "free_dof_count": free_count,
        "finite_difference_epsilon": epsilon,
        "analytic_jacobian_kn_per_m": analytic.tolist(),
        "finite_difference_jacobian_kn_per_m": numeric.tolist(),
        "max_abs_error": error,
        "pass": error <= 1.0e-6,
    }


def mesh_series_force_equilibrium_check(state: AxialChainAssemblyState) -> dict[str, Any]:
    """Check equal internal force in series elements at convergence."""
    if len(state.element_forces_kn) < 2:
        return {
            "element_count": len(state.element_forces_kn),
            "pass": True,
            "detail": "single_element_chain",
        }
    forces = [row["internal_force_kn"] for row in state.element_forces_kn]
    spread = max(forces) - min(forces)
    return {
        "element_count": len(state.element_forces_kn),
        "element_internal_forces_kn": forces,
        "force_spread_kn": spread,
        "pass": spread <= 1.0e-10,
    }


@dataclass(frozen=True)
class AxialChainMeshNewtonAdapter:
    """Bridge assembled axial-chain state to the vector Newton solver."""

    mesh_problem: AxialChainMeshProblem

    @property
    def case_id(self) -> str:
        return self.mesh_problem.case_id

    def reference_force_scale(self) -> float:
        return self.mesh_problem.reference_force_scale()

    def initial_free_displacements_m(self) -> np.ndarray:
        free_nodes = _free_node_indices(self.mesh_problem)
        initial = np.array(self.mesh_problem.initial_displacements_m, dtype=float)
        return initial[list(free_nodes)].copy()

    def assemble(
        self,
        free_displacements_m: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        state = assemble_axial_chain_state(self.mesh_problem, free_displacements_m)
        return state.residual_kn, state.jacobian_kn_per_m


def solve_axial_chain_mesh(
    mesh_problem: AxialChainMeshProblem,
    *,
    config: Any | None = None,
) -> tuple[Any, AxialChainAssemblyState]:
    from structural_analysis.solvers.nonlinear.newton import (
        NewtonRaphsonConfig,
        newton_raphson_vector,
    )

    adapter = AxialChainMeshNewtonAdapter(mesh_problem=mesh_problem)
    solution = newton_raphson_vector(adapter, config=config or NewtonRaphsonConfig())
    final_state = assemble_axial_chain_state(mesh_problem, solution.free_displacements_m)
    return solution, final_state


def mesh_problem_with_scaled_external_load(
    mesh_problem: AxialChainMeshProblem,
    *,
    load_factor: float,
    initial_displacements_m: tuple[float, ...] | None = None,
) -> AxialChainMeshProblem:
    scaled_forces = tuple(
        (node_index, force_kn * load_factor) for node_index, force_kn in mesh_problem.external_forces_kn
    )
    return AxialChainMeshProblem(
        case_id=mesh_problem.case_id,
        node_count=mesh_problem.node_count,
        elements=mesh_problem.elements,
        fixed_nodes=mesh_problem.fixed_nodes,
        external_forces_kn=scaled_forces,
        initial_displacements_m=(
            mesh_problem.initial_displacements_m
            if initial_displacements_m is None
            else initial_displacements_m
        ),
    )
