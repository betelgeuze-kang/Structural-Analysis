"""Explicit model bridge for experimental corotational RC control.

Compilation validates authored data; it neither executes the solver nor inherits
small-displacement J1--J5 engineering authority.
"""

from dataclasses import dataclass
import math

from structural_analysis.api.nonlinear_fiber_frame import _compile
from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    StatefulCorotationalFiberFrame2DMember,
    StatefulCorotationalFiberFrame2DProblem,
)
from structural_analysis.elements.stateful_corotational_fiber_beam2d import (
    StatefulCorotationalFiberBeam2D,
)
from structural_analysis.model.schema import CanonicalModel


RC_COROTATIONAL_MODEL_PROFILE = "experimental_rc_corotational_control_model.v1"
RC_COROTATIONAL_PORTAL_MODEL_PROFILE = (
    "experimental_rc_corotational_portal_control_model.v1"
)


@dataclass(frozen=True)
class CompiledRCCorotationalControlModel:
    problem: StatefulCorotationalFiberFrame2DProblem
    node_ids: tuple[str, ...]
    source_model_checksum: str
    source_input_checksum: str
    support_node_ids: tuple[str, ...]
    warnings: tuple[str, ...]
    compiler_profile: str = RC_COROTATIONAL_MODEL_PROFILE


def compile_rc_corotational_control_model(
    model: CanonicalModel,
    *,
    fixed_nodal_loads: tuple[tuple[str, str, float], ...] = (),
    experimental_pin_roller_beam: bool = False,
    experimental_fixed_guided_axial: bool = False,
    experimental_portal_frame: bool = False,
) -> CompiledRCCorotationalControlModel:
    """Compile existing supported RC geometry/materials with explicit dead loads.

    Model nodal loads remain proportional reference loads. Each additional fixed
    row is (node ID, FX/FY/MZ, value in kN or kN*m). These dead global loads are
    additive; no model load is silently reclassified. The caller must explicitly
    establish preload equilibrium before lateral control.
    """
    if type(model) is not CanonicalModel:
        raise ValueError("model must be an exact CanonicalModel")
    if type(fixed_nodal_loads) is not tuple or len(fixed_nodal_loads) > 48:
        raise ValueError("fixed_nodal_loads must be a tuple with at most 48 rows")
    flags = (
        experimental_pin_roller_beam,
        experimental_fixed_guided_axial,
        experimental_portal_frame,
    )
    if any(type(flag) is not bool for flag in flags) or sum(flags) > 1:
        raise ValueError("support profiles require mutually exclusive boolean flags")
    snapshot = model.detached_analysis_snapshot()
    if experimental_portal_frame:
        # Reuse the native portal compiler without widening the fixed-chord API.
        from structural_analysis.api.nonlinear_frame import _compile_portal

        if snapshot.unsupported_features:
            raise ValueError("unsupported corotational portal model input")
        compiled = _compile_portal(snapshot, general_profile=False)
        warnings = snapshot.warnings
        support_node_ids = compiled.support_node_ids
    else:
        compiled, unsupported, warnings = _compile(
            snapshot,
            experimental_pin_roller_beam=experimental_pin_roller_beam,
            experimental_fixed_guided_axial=experimental_fixed_guided_axial,
        )
        if compiled is None or unsupported:
            raise ValueError(f"unsupported corotational model input: {unsupported!r}")
        support_node_ids = compiled.support_node_ids or (compiled.support_node_id,)
    small = compiled.problem
    node_index = {name: index for index, name in enumerate(compiled.node_ids)}
    components = {"FX": 0, "FY": 1, "MZ": 2}
    fixed = {}
    for row in fixed_nodal_loads:
        if type(row) is not tuple or len(row) != 3:
            raise ValueError(
                "fixed nodal load must be a (node, component, value) tuple"
            )
        node, component, value = row
        if type(node) is not str or node not in node_index:
            raise ValueError("fixed nodal load references an unknown node")
        if type(component) is not str or component not in components:
            raise ValueError("fixed nodal load component must be FX, FY or MZ")
        if type(value) not in (int, float):
            raise ValueError("fixed nodal load value must be finite and numeric")
        try:
            normalized = float(value)
        except OverflowError as exc:
            raise ValueError("fixed nodal load value exceeds finite range") from exc
        if not math.isfinite(normalized):
            raise ValueError("fixed nodal load value must be finite and numeric")
        dof = 3 * node_index[node] + components[component]
        if dof in fixed:
            raise ValueError("duplicate fixed nodal load component")
        fixed[dof] = normalized
    if experimental_portal_frame:
        roof = set(range(len(compiled.node_ids))) - {
            node_index[node] for node in support_node_ids
        }
        if (
            not small.reference_external_loads
            or any(
                dof % 3 != 0 or dof // 3 not in roof
                for dof, _value in small.reference_external_loads
            )
            or set(fixed) != {3 * node + 1 for node in roof}
            or any(value >= 0.0 for value in fixed.values())
        ):
            raise ValueError(
                "portal requires roof FX reference loads and one negative FY "
                "gravity load at each roof node"
            )
    members = (
        small.members
        if experimental_portal_frame
        else tuple(
            StatefulCorotationalFiberFrame2DMember(
                member_id=member.member_id,
                node_i=member.node_i,
                node_j=member.node_j,
                element=StatefulCorotationalFiberBeam2D(
                    node_coordinates_m=(
                        small.node_coordinates_m[member.node_i],
                        small.node_coordinates_m[member.node_j],
                    ),
                    section=member.element.section,
                    integration_order=member.element.integration_order,
                    element_id=member.element.element_id,
                ),
            )
            for member in small.members
        )
    )
    problem = StatefulCorotationalFiberFrame2DProblem(
        case_id="rc_corotational_"
        + snapshot.canonical_model_checksum.removeprefix("sha256:"),
        node_coordinates_m=small.node_coordinates_m,
        members=members,
        fixed_global_dofs=small.fixed_global_dofs,
        reference_external_loads=small.reference_external_loads,
        rotation_coordinate_scale_m=small.rotation_coordinate_scale_m,
        fixed_external_loads=tuple(sorted(fixed.items())),
    )
    return CompiledRCCorotationalControlModel(
        problem=problem,
        node_ids=compiled.node_ids,
        source_model_checksum=snapshot.canonical_model_checksum,
        source_input_checksum=snapshot.input_checksum,
        support_node_ids=support_node_ids,
        warnings=tuple(warnings),
        compiler_profile=(
            RC_COROTATIONAL_PORTAL_MODEL_PROFILE
            if experimental_portal_frame
            else RC_COROTATIONAL_MODEL_PROFILE
        ),
    )


def validate_rc_portal_control_selection(
    compiled: CompiledRCCorotationalControlModel,
    node: str | None,
    component: str | None,
    observation: object,
) -> None:
    """Keep the portal entry point limited to one authored roof UX control."""
    if compiled.compiler_profile == RC_COROTATIONAL_PORTAL_MODEL_PROFILE and (
        observation is not None
        or node not in compiled.node_ids
        or node in compiled.support_node_ids
        or component != "UX"
    ):
        raise ValueError("portal control must select one roof node UX")
