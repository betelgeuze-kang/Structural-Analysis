"""Public bounded canonical two-bar material-geometric truss API.

The adapter accepts a canonical model only when it exactly represents the
symmetric three-node/two-bar planar scope verified by the retained nonlinear
kernel.  Unsupported topology, properties, loads, supports, units, axes, or
asymmetry fail closed before solve.

This is a public Developer Preview vertical slice, not a general truss solver or
an Engine v2 authoritative result path.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping

from structural_analysis.benchmark.material_geometric_truss import (
    StatefulTwoBarTrussLoadPathResult,
    StatefulTwoBarTrussProblem,
    run_stateful_two_bar_truss_load_path,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
)
from structural_analysis.model.schema import CanonicalModel
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig


PUBLIC_TWO_BAR_TRUSS_SCHEMA_VERSION = "public-two-bar-truss-result.v1"
PUBLIC_TWO_BAR_TRUSS_REPORT_SCHEMA_VERSION = (
    "public-two-bar-truss-validation-report.v1"
)
PUBLIC_TWO_BAR_TRUSS_SOLVER_ID = "public_cpu_stateful_two_bar_truss_newton_v1"
PUBLIC_TWO_BAR_TRUSS_CLAIM_BOUNDARY = (
    "This public Developer Preview path accepts only one symmetric, planar, "
    "three-node/two-bar truss with two fully restrained base nodes, one free "
    "apex, identical area and bilinear combined-hardening steel in both bars, "
    "and one downward proportional apex nodal load. It reuses the bounded "
    "same-parent material-geometric Newton path with atomic state commit or "
    "exact rollback. It does not establish arbitrary truss topology, 3D, "
    "cables, frame/shell behavior, multiple load cases, prescribed movement, "
    "arc-length, production sparse/HIP execution, Engine v2 result authority, "
    "design/code compliance, full-building equilibrium, or G1 closure."
)

_SUPPORTED_MATERIAL_TYPES = {
    "bilinear_combined_hardening_steel",
    "steel_bilinear_combined_hardening_1d",
    "bilinear_steel",
}


@dataclass(frozen=True)
class PublicTwoBarTrussConfig:
    load_steps: int = 10
    residual_tolerance_kn: float = 1.0e-10
    increment_tolerance_m: float = 1.0e-12
    maximum_iterations: int = 40

    def __post_init__(self) -> None:
        if type(self.load_steps) is not int or self.load_steps <= 0:
            raise ValueError("load_steps must be a positive integer")
        if type(self.maximum_iterations) is not int or self.maximum_iterations <= 0:
            raise ValueError("maximum_iterations must be a positive integer")
        for name in ("residual_tolerance_kn", "increment_tolerance_m"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be finite and positive")
            normalized = float(value)
            if not math.isfinite(normalized) or normalized <= 0.0:
                raise ValueError(f"{name} must be finite and positive")
            object.__setattr__(self, name, normalized)

    @property
    def target_load_factors(self) -> tuple[float, ...]:
        return tuple(
            step / self.load_steps for step in range(1, self.load_steps + 1)
        )


@dataclass(frozen=True)
class PublicTwoBarTrussResult:
    status: str
    contract_pass: bool
    result_hash: str
    canonical_model_checksum: str
    input_checksum: str
    solver_id: str
    configuration: Mapping[str, Any]
    node_displacements: tuple[Mapping[str, Any], ...]
    support_reactions: tuple[Mapping[str, Any], ...]
    element_results: tuple[Mapping[str, Any], ...]
    convergence_history: tuple[Mapping[str, Any], ...]
    metrics: Mapping[str, Any]
    unsupported_features: tuple[Mapping[str, Any], ...]
    warnings: tuple[str, ...]
    claim_boundary: str = PUBLIC_TWO_BAR_TRUSS_CLAIM_BOUNDARY

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PUBLIC_TWO_BAR_TRUSS_SCHEMA_VERSION,
            "status": self.status,
            "contract_pass": self.contract_pass,
            "result_hash": self.result_hash,
            "canonical_model_checksum": self.canonical_model_checksum,
            "input_checksum": self.input_checksum,
            "solver_id": self.solver_id,
            "configuration": dict(self.configuration),
            "node_displacements": [dict(row) for row in self.node_displacements],
            "support_reactions": [dict(row) for row in self.support_reactions],
            "element_results": [dict(row) for row in self.element_results],
            "convergence_history": [dict(row) for row in self.convergence_history],
            "metrics": dict(self.metrics),
            "unsupported_features": [
                dict(row) for row in self.unsupported_features
            ],
            "warnings": list(self.warnings),
            "claim_boundary": self.claim_boundary,
        }


@dataclass(frozen=True)
class PublicTwoBarTrussValidationReport:
    status: str
    contract_pass: bool
    result_hash: str
    unsupported_feature_count: int
    warning_count: int
    rollback_exact: bool | None
    fallback_count: int
    regularization_count: int
    claim_boundary: str = PUBLIC_TWO_BAR_TRUSS_CLAIM_BOUNDARY

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PUBLIC_TWO_BAR_TRUSS_REPORT_SCHEMA_VERSION,
            "status": self.status,
            "contract_pass": self.contract_pass,
            "result_hash": self.result_hash,
            "unsupported_feature_count": self.unsupported_feature_count,
            "warning_count": self.warning_count,
            "rollback_exact": self.rollback_exact,
            "fallback_count": self.fallback_count,
            "regularization_count": self.regularization_count,
            "claim_boundary": self.claim_boundary,
        }


@dataclass(frozen=True)
class _CompiledTwoBarModel:
    problem: StatefulTwoBarTrussProblem
    left_base_id: str
    right_base_id: str
    apex_id: str
    left_element_id: str
    right_element_id: str


def analyze_public_two_bar_truss(
    model: CanonicalModel,
    config: PublicTwoBarTrussConfig | None = None,
) -> PublicTwoBarTrussResult:
    """Compile and solve the exact bounded canonical two-bar scope."""

    cfg = config or PublicTwoBarTrussConfig()
    snapshot = model.detached_analysis_snapshot()
    compiled, unsupported, warnings = _compile(snapshot)
    configuration = {
        "load_steps": cfg.load_steps,
        "target_load_factors": list(cfg.target_load_factors),
        "residual_tolerance_kn": cfg.residual_tolerance_kn,
        "increment_tolerance_m": cfg.increment_tolerance_m,
        "maximum_iterations": cfg.maximum_iterations,
    }
    if compiled is None:
        return _build_result(
            snapshot,
            configuration=configuration,
            status="blocked",
            path=None,
            compiled=None,
            unsupported=unsupported,
            warnings=warnings,
        )

    path = run_stateful_two_bar_truss_load_path(
        compiled.problem,
        cfg.target_load_factors,
        config=NewtonRaphsonConfig(
            residual_tolerance=cfg.residual_tolerance_kn,
            increment_tolerance=cfg.increment_tolerance_m,
            max_iterations=cfg.maximum_iterations,
        ),
    )
    return _build_result(
        snapshot,
        configuration=configuration,
        status=path.status,
        path=path,
        compiled=compiled,
        unsupported=unsupported,
        warnings=warnings,
    )


def validate_public_two_bar_truss_result(
    result: PublicTwoBarTrussResult,
) -> PublicTwoBarTrussValidationReport:
    """Return a stable validation envelope without creating result authority."""

    if type(result) is not PublicTwoBarTrussResult:
        raise ValueError("result must be a PublicTwoBarTrussResult")
    return PublicTwoBarTrussValidationReport(
        status="ready" if result.contract_pass else "blocked",
        contract_pass=result.contract_pass,
        result_hash=result.result_hash,
        unsupported_feature_count=len(result.unsupported_features),
        warning_count=len(result.warnings),
        rollback_exact=result.metrics.get("rollback_exact"),
        fallback_count=int(result.metrics.get("fallback_count", 0)),
        regularization_count=int(result.metrics.get("regularization_count", 0)),
    )


def _compile(
    model: CanonicalModel,
) -> tuple[_CompiledTwoBarModel | None, list[Mapping[str, Any]], list[str]]:
    unsupported: list[Mapping[str, Any]] = list(model.unsupported_features)
    warnings = list(model.warnings)
    if model.units.length != "m" or model.units.force != "kN":
        unsupported.append({"kind": "two_bar_units_not_supported"})
    if (
        tuple(str(value).upper() for value in model.coordinate_system.axis_order)
        != ("X", "Y", "Z")
        or str(model.coordinate_system.up_axis).upper() != "Z"
    ):
        unsupported.append({"kind": "two_bar_coordinate_system_not_supported"})
    if len(model.nodes) != 3:
        unsupported.append(
            {"kind": "two_bar_node_count_invalid", "node_count": len(model.nodes)}
        )
    if len(model.elements) != 2:
        unsupported.append(
            {
                "kind": "two_bar_element_count_invalid",
                "element_count": len(model.elements),
            }
        )
    if len(model.loads) != 1:
        unsupported.append(
            {"kind": "two_bar_load_count_invalid", "load_count": len(model.loads)}
        )

    nodes: dict[str, tuple[float, float]] = {}
    for row in model.nodes:
        node_id = str(row.get("id", "")).strip()
        raw = row.get("coordinates")
        if (
            not node_id
            or not isinstance(raw, (list, tuple))
            or len(raw) != 3
        ):
            unsupported.append({"kind": "two_bar_node_invalid", "node": node_id})
            continue
        try:
            x, y, z = (float(value) for value in raw)
        except (TypeError, ValueError):
            unsupported.append({"kind": "two_bar_node_invalid", "node": node_id})
            continue
        if not all(math.isfinite(value) for value in (x, y, z)) or abs(z) > 1e-12:
            unsupported.append({"kind": "two_bar_node_not_planar", "node": node_id})
            continue
        nodes[node_id] = (x, y)
    if len(nodes) != 3:
        return None, unsupported, warnings

    support_dofs: dict[str, set[str]] = {node_id: set() for node_id in nodes}
    for row in model.supports:
        node_id = str(row.get("node", row.get("node_id", "")))
        raw_dofs = row.get("dofs", row.get("restrained_dofs", ()))
        dofs = ("UX", "UY") if raw_dofs == "all" else raw_dofs
        if node_id not in nodes or not isinstance(dofs, (list, tuple)):
            unsupported.append({"kind": "two_bar_support_invalid", "node": node_id})
            continue
        support_dofs[node_id].update(str(value).upper() for value in dofs)
    base_ids = sorted(
        node_id
        for node_id, dofs in support_dofs.items()
        if {"UX", "UY"}.issubset(dofs)
    )
    apex_ids = sorted(node_id for node_id in nodes if node_id not in base_ids)
    if len(base_ids) != 2 or len(apex_ids) != 1:
        unsupported.append(
            {
                "kind": "two_bar_support_pattern_invalid",
                "fully_restrained_base_count": len(base_ids),
            }
        )
        return None, unsupported, warnings
    apex_id = apex_ids[0]
    if support_dofs[apex_id] & {"UX", "UY"}:
        unsupported.append({"kind": "two_bar_apex_must_be_free", "node": apex_id})

    base_rows = sorted((nodes[node_id][0], node_id) for node_id in base_ids)
    left_base_id, right_base_id = base_rows[0][1], base_rows[1][1]
    left = nodes[left_base_id]
    right = nodes[right_base_id]
    apex = nodes[apex_id]
    center_x = 0.5 * (left[0] + right[0])
    base_y = 0.5 * (left[1] + right[1])
    half_span = 0.5 * (right[0] - left[0])
    rise = apex[1] - base_y
    scale = max(abs(left[0]), abs(right[0]), abs(apex[0]), abs(apex[1]), 1.0)
    tolerance = 1.0e-12 * scale
    if (
        half_span <= 0.0
        or rise <= 0.0
        or abs(left[1] - right[1]) > tolerance
        or abs(apex[0] - center_x) > tolerance
        or abs(apex[1] - (base_y + rise)) > tolerance
    ):
        unsupported.append({"kind": "two_bar_geometry_not_symmetric"})

    element_by_base: dict[str, Mapping[str, Any]] = {}
    for row in model.elements:
        element_id = str(row.get("id", "")).strip()
        if str(row.get("type", "")).lower() not in {"truss", "axial"}:
            unsupported.append(
                {"kind": "two_bar_element_type_invalid", "element": element_id}
            )
            continue
        connectivity = row.get("nodes")
        if not isinstance(connectivity, (list, tuple)) or len(connectivity) != 2:
            unsupported.append(
                {"kind": "two_bar_connectivity_invalid", "element": element_id}
            )
            continue
        pair = {str(connectivity[0]), str(connectivity[1])}
        if apex_id not in pair or len(pair) != 2:
            unsupported.append(
                {"kind": "two_bar_connectivity_invalid", "element": element_id}
            )
            continue
        base_id = next(iter(pair - {apex_id}))
        if base_id not in base_ids or base_id in element_by_base:
            unsupported.append(
                {"kind": "two_bar_connectivity_invalid", "element": element_id}
            )
            continue
        element_by_base[base_id] = row
    if set(element_by_base) != set(base_ids):
        unsupported.append({"kind": "two_bar_connectivity_incomplete"})
        return None, unsupported, warnings

    left_element = element_by_base[left_base_id]
    right_element = element_by_base[right_base_id]
    property_pairs = {
        (
            str(left_element.get("material", "")),
            str(left_element.get("section", "")),
        ),
        (
            str(right_element.get("material", "")),
            str(right_element.get("section", "")),
        ),
    }
    if len(property_pairs) != 1:
        unsupported.append({"kind": "two_bar_properties_must_match"})
        return None, unsupported, warnings
    material_id, section_id = next(iter(property_pairs))
    material_row = next(
        (row for row in model.materials if str(row.get("id", "")) == material_id),
        None,
    )
    section_row = next(
        (row for row in model.sections if str(row.get("id", "")) == section_id),
        None,
    )
    try:
        material = _material(material_row)
        area = _positive_number(
            None if section_row is None else section_row.get("area", section_row.get("A_m2")),
            "section area",
        )
    except ValueError as exc:
        unsupported.append(
            {"kind": "two_bar_property_invalid", "detail": str(exc)}
        )
        return None, unsupported, warnings

    if len(model.loads) == 1:
        load = model.loads[0]
        node_id = str(load.get("node", load.get("node_id", "")))
        components = _components(load)
        if node_id != apex_id or components is None:
            unsupported.append({"kind": "two_bar_load_invalid"})
            vertical_load = 0.0
        else:
            fx, fy, fz, mx, my, mz = components
            if (
                abs(fx) > tolerance
                or fy >= 0.0
                or any(abs(value) > tolerance for value in (fz, mx, my, mz))
            ):
                unsupported.append({"kind": "two_bar_load_must_be_downward_apex"})
            vertical_load = -fy
    else:
        vertical_load = 0.0
    if unsupported:
        return None, unsupported, warnings

    problem = StatefulTwoBarTrussProblem(
        half_span_m=half_span,
        rise_m=rise,
        area_m2=area,
        reference_vertical_load_kn=vertical_load,
        material=material,
        case_id=f"public_two_bar_{model.canonical_model_checksum.split(':')[-1][:16]}",
    )
    return (
        _CompiledTwoBarModel(
            problem=problem,
            left_base_id=left_base_id,
            right_base_id=right_base_id,
            apex_id=apex_id,
            left_element_id=str(left_element.get("id", "left-bar")),
            right_element_id=str(right_element.get("id", "right-bar")),
        ),
        unsupported,
        warnings,
    )


def _material(row: Mapping[str, Any] | None) -> BilinearCombinedHardeningSteel:
    if row is None:
        raise ValueError("material row is missing")
    material_type = str(row.get("type", "")).lower()
    if material_type not in _SUPPORTED_MATERIAL_TYPES:
        raise ValueError(f"unsupported material type: {material_type or '<missing>'}")
    modulus = row.get("elastic_modulus_mpa")
    if modulus is None:
        modulus = _positive_number(
            row.get("elastic_modulus", row.get("E_kN_per_m2")),
            "elastic modulus",
        ) / 1000.0
    return BilinearCombinedHardeningSteel(
        elastic_modulus_mpa=_positive_number(modulus, "elastic_modulus_mpa"),
        yield_stress_mpa=_positive_number(
            row.get("yield_stress_mpa"),
            "yield_stress_mpa",
        ),
        isotropic_hardening_modulus_mpa=_nonnegative_number(
            row.get("isotropic_hardening_modulus_mpa", 0.0),
            "isotropic_hardening_modulus_mpa",
        ),
        kinematic_hardening_modulus_mpa=_nonnegative_number(
            row.get("kinematic_hardening_modulus_mpa", 0.0),
            "kinematic_hardening_modulus_mpa",
        ),
        material_id=str(row.get("id", "material")),
    )


def _components(row: Mapping[str, Any]) -> tuple[float, ...] | None:
    raw = row.get("components")
    labels = ("FX", "FY", "FZ", "MX", "MY", "MZ")
    if isinstance(raw, Mapping):
        values = [raw.get(label, raw.get(label.lower(), 0.0)) for label in labels]
    elif isinstance(raw, (list, tuple)) and len(raw) in (3, 6):
        values = list(raw)
        if len(values) == 3:
            values.extend((0.0, 0.0, 0.0))
    else:
        values = [row.get(label, row.get(label.lower(), 0.0)) for label in labels]
    try:
        result = tuple(float(value) for value in values)
    except (TypeError, ValueError):
        return None
    return result if all(math.isfinite(value) for value in result) else None


def _build_result(
    model: CanonicalModel,
    *,
    configuration: Mapping[str, Any],
    status: str,
    path: StatefulTwoBarTrussLoadPathResult | None,
    compiled: _CompiledTwoBarModel | None,
    unsupported: list[Mapping[str, Any]],
    warnings: list[str],
) -> PublicTwoBarTrussResult:
    displacements: tuple[Mapping[str, Any], ...] = ()
    reactions: tuple[Mapping[str, Any], ...] = ()
    elements: tuple[Mapping[str, Any], ...] = ()
    history: list[Mapping[str, Any]] = []
    metrics: dict[str, Any] = {
        "solver_executed": path is not None,
        "fallback_count": 0,
        "regularization_count": 0,
        "rollback_exact": None,
    }
    if path is not None and compiled is not None:
        final = path.final_state
        displacements = (
            {"node_id": compiled.left_base_id, "UX_m": 0.0, "UY_m": 0.0},
            {"node_id": compiled.right_base_id, "UX_m": 0.0, "UY_m": 0.0},
            {
                "node_id": compiled.apex_id,
                "UX_m": final.apex_displacements_m[0],
                "UY_m": final.apex_displacements_m[1],
            },
        )
        for step_index, step in enumerate(path.steps, start=1):
            for row in step.trial_solution.convergence_history:
                history.append(
                    {
                        "load_step": step_index,
                        "target_load_factor": step.trial_solution.metrics.get(
                            "target_load_factor",
                            step.accepted_state.load_factor,
                        ),
                        **dict(row),
                    }
                )
        committed_steps = [step for step in path.steps if step.committed]
        final_step = committed_steps[-1] if committed_steps else None
        if final_step is not None:
            assembly = final_step.final_assembly
            left_response, right_response = assembly.element_responses
            reactions = (
                {
                    "node_id": compiled.left_base_id,
                    "FX_kN": -float(left_response.internal_force_kn[0]),
                    "FY_kN": -float(left_response.internal_force_kn[1]),
                },
                {
                    "node_id": compiled.right_base_id,
                    "FX_kN": -float(right_response.internal_force_kn[0]),
                    "FY_kN": -float(right_response.internal_force_kn[1]),
                },
            )
            elements = tuple(
                {
                    "element_id": element_id,
                    "engineering_strain": response.engineering_strain,
                    "axial_force_kN": response.axial_force_kn,
                    "material_state_hash": material_state.state_hash,
                    "dissipated_energy_density_MJ_per_m3": (
                        material_state.dissipated_energy_density_mj_per_m3
                    ),
                }
                for element_id, response, material_state in zip(
                    (compiled.left_element_id, compiled.right_element_id),
                    assembly.element_responses,
                    final.material_states,
                    strict=True,
                )
            )
        rollback_steps = [step for step in path.steps if not step.committed]
        metrics.update(path.metrics)
        metrics.update(
            {
                "accepted_load_factor": final.load_factor,
                "final_state_hash": final.state_hash,
                "rollback_exact": (
                    rollback_steps[-1].metrics.get("rollback_exact")
                    if rollback_steps
                    else None
                ),
            }
        )
    contract_pass = bool(status == "ready" and not unsupported and path is not None)
    payload = {
        "schema_version": PUBLIC_TWO_BAR_TRUSS_SCHEMA_VERSION,
        "status": status,
        "contract_pass": contract_pass,
        "canonical_model_checksum": model.canonical_model_checksum,
        "input_checksum": model.input_checksum,
        "solver_id": PUBLIC_TWO_BAR_TRUSS_SOLVER_ID,
        "configuration": dict(configuration),
        "node_displacements": [dict(row) for row in displacements],
        "support_reactions": [dict(row) for row in reactions],
        "element_results": [dict(row) for row in elements],
        "convergence_history": [dict(row) for row in history],
        "metrics": metrics,
        "unsupported_features": [dict(row) for row in unsupported],
        "warnings": list(warnings),
        "claim_boundary": PUBLIC_TWO_BAR_TRUSS_CLAIM_BOUNDARY,
    }
    return PublicTwoBarTrussResult(
        status=status,
        contract_pass=contract_pass,
        result_hash=canonical_hash(payload),
        canonical_model_checksum=model.canonical_model_checksum,
        input_checksum=model.input_checksum,
        solver_id=PUBLIC_TWO_BAR_TRUSS_SOLVER_ID,
        configuration=dict(configuration),
        node_displacements=displacements,
        support_reactions=reactions,
        element_results=elements,
        convergence_history=tuple(history),
        metrics=metrics,
        unsupported_features=tuple(unsupported),
        warnings=tuple(warnings),
    )


def _positive_number(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be finite and positive")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be finite and positive") from exc
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name} must be finite and positive")
    return result


def _nonnegative_number(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be finite and non-negative")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be finite and non-negative") from exc
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return result


__all__ = [
    "PUBLIC_TWO_BAR_TRUSS_CLAIM_BOUNDARY",
    "PUBLIC_TWO_BAR_TRUSS_SCHEMA_VERSION",
    "PUBLIC_TWO_BAR_TRUSS_SOLVER_ID",
    "PublicTwoBarTrussConfig",
    "PublicTwoBarTrussResult",
    "PublicTwoBarTrussValidationReport",
    "analyze_public_two_bar_truss",
    "validate_public_two_bar_truss_result",
]
