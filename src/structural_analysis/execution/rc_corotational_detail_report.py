"""Read-only, source-ordered projections of saved corotational member responses.

No element integration, equilibrium solve, engineering recovery or replay occurs
here. The only new force calculation is an explicitly declared coordinate
rotation of the stored physical element-end net force. Basic-beam force vectors
and tangents are never presented as physical member-end results.
"""

from __future__ import annotations

import json
import math
from typing import Any

from structural_analysis.api.rc_corotational_control_model import (
    compile_rc_corotational_control_model,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_checkpoint_io import (
    _restore_corotational_element_state,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_state import (
    StatefulCorotationalFiberFrame2DCheckpoint,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.materials.stateful_fiber_section import (
    FIBER_SECTION_RESULTANT_DEFINITION,
    FIBER_SECTION_STRAIN_RELATION,
)

from .rc_corotational_job_request import (
    RCCorotationalJobRequest,
    rc_corotational_job_canonical_bytes,
)
from .rc_corotational_report import RCCorotationalReportTooLargeError, _sha


RC_COROTATIONAL_DETAIL_REPORT_SCHEMA_VERSION = (
    "durable-rc-corotational-detail-report.v1"
)
RC_COROTATIONAL_DETAIL_REPORT_MAX_BYTES = 64 * 1024 * 1024
RC_COROTATIONAL_DETAIL_REPORT_UNITS = {
    "end_force_components": ["FX_i", "FY_i", "MZ_i", "FX_j", "FY_j", "MZ_j"],
    "end_force_units": ["kN", "kN", "kN*m", "kN", "kN", "kN*m"],
    "global_frame": "global",
    "local_frame": "current_chord_i_to_j",
    "local_projection": "FX=c*FX_global+s*FY_global;FY=-s*FX_global+c*FY_global;MZ=MZ_global",
    "end_force_definition": "element_internal_minus_scaled_consistent_member_dead_load",
    "section_resultant_units": ["kN", "kN*m"],
    "section_strain_relation": FIBER_SECTION_STRAIN_RELATION,
    "section_resultant_definition": FIBER_SECTION_RESULTANT_DEFINITION,
    "curvature": "1/m",
    "fiber_stress": "MPa",
    "fiber_strain": "1",
    "integration_coordinate": "xi_in_[-1,1]_along_initial_member_i_to_j",
}
RC_COROTATIONAL_DETAIL_REPORT_CLAIM_BOUNDARY = (
    "Saved experimental corotational RC accepted member, section and fiber "
    "responses only. Local end forces are a declared current-chord coordinate "
    "rotation of stored global element net end forces, not a new equilibrium "
    "or engineering-recovery validation. Source order, member i-to-j orientation "
    "and preload/subdivision states are retained. Fiber indices identify stored "
    "integration samples, not individual reinforcing bars. Source revision is "
    "a caller declaration. No fresh analysis, verification or source fingerprint; "
    "no independent physical validation, design approval or release readiness."
)


def _number(value: Any) -> int | float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("saved detail requires finite JSON numbers")
    if type(value) is int and int(float(value)) != value:
        raise ValueError("saved detail number must be lossless binary64")
    return value


def _vector(value: Any, count: int) -> list[int | float]:
    if type(value) is not list or len(value) != count:
        raise ValueError("saved detail vector length differs")
    return [_number(item) for item in value]


def _same(left: Any, right: Any) -> None:
    # Canonical JSON comparison retains bool/number distinctions and signed zero.
    if rc_corotational_job_canonical_bytes(left) != rc_corotational_job_canonical_bytes(
        right
    ):
        raise ValueError("saved detail source linkage differs")


def _close(left: float, right: float) -> None:
    if not math.isfinite(left) or not math.isclose(
        left, right, rel_tol=1e-12, abs_tol=1e-12
    ):
        raise ValueError("saved detail coordinate or force projection differs")


def _member_projection(member, raw, *, node_ids, load_factor, state_index):
    if raw["member_id"] != member.member_id:
        raise ValueError("saved member source order differs")
    dofs = [
        3 * node + axis for node in (member.node_i, member.node_j) for axis in range(3)
    ]
    _same(raw["global_dofs"], dofs)
    response = raw["element_response"]
    if response["schema_version"] != "stateful-corotational-fiber-beam2d.v1":
        raise ValueError("unsupported saved element response")
    state = _restore_corotational_element_state(
        member.element.initial_state(),
        response["trial_state"],
        path="/member/trial_state",
    )
    member.element.validate_state(state)
    if state.step_index != state_index + 1:
        raise ValueError("saved member step differs from accepted state")
    feature = raw["member_feature_response"]
    if feature["schema_version"] != "corotational-frame2d-member-features.v1":
        raise ValueError("unsupported saved member feature response")
    if feature["feature_contract_hash"] != member.features.contract_hash:
        raise ValueError("saved member feature contract differs")
    if feature["response_hash"] != canonical_hash(
        {key: value for key, value in feature.items() if key != "response_hash"}
    ):
        raise ValueError("saved member feature response hash differs")
    _same(feature["element_response"], response)
    _same(
        feature["element_displacements"],
        response["trial_state"]["element_displacements"],
    )
    _same(feature["target_load_factor"], load_factor)
    _same(raw["internal_load_global"], feature["nodal_internal_load_global"])
    _same(
        raw["equivalent_external_load_global"],
        feature["nodal_equivalent_external_load_global"],
    )
    net = _vector(feature["element_net_end_force_global"], 6)
    internal = _vector(feature["element_internal_load_global"], 6)
    external = _vector(feature["element_equivalent_external_load_global"], 6)
    for force, inside, outside in zip(net, internal, external, strict=True):
        # The stored equivalent vector is already scaled (applied_dead_load).
        _close(force, inside - outside)
    kinematics = response["kinematics"]
    _same(
        kinematics["global_dof_order"],
        ["ux_i_m", "uy_i_m", "theta_i_rad", "ux_j_m", "uy_j_m", "theta_j_rad"],
    )
    direction = _vector(kinematics["current_direction"], 2)
    length = _number(kinematics["current_length_m"])
    initial_length = _number(kinematics["initial_length_m"])
    if length <= 0 or initial_length <= 0:
        raise ValueError("saved member length must be positive")
    _close(initial_length, member.element.initial_length_m)
    displacement = _vector(feature["element_displacements"], 6)
    coordinates = member.element.node_coordinates_m
    dx = coordinates[1][0] + displacement[3] - coordinates[0][0] - displacement[0]
    dy = coordinates[1][1] + displacement[4] - coordinates[0][1] - displacement[1]
    _close(length, math.hypot(dx, dy))
    _close(direction[0], dx / length)
    _close(direction[1], dy / length)
    _close(math.hypot(*direction), 1.0)
    c, s = direction
    local = []
    for offset in (0, 3):
        fx, fy, mz = net[offset : offset + 3]
        x, y = _number(c * fx + s * fy), _number(-s * fx + c * fy)
        _close(c * x - s * y, fx)
        _close(s * x + c * y, fy)
        local.extend((x, y, mz))
    beam = response["fiber_beam_response"]
    _same(beam["trial_state"], response["trial_state"]["basic_beam_state"])
    points, weights = member.element.basic_beam.quadrature
    xi = _vector(beam["integration_point_xi"], len(points))
    weight = _vector(beam["integration_point_weights"], len(points))
    _same(xi, list(points))
    _same(weight, list(weights))
    section_rows = beam["section_responses"]
    if type(section_rows) is not list or len(section_rows) != len(points):
        raise ValueError("saved integration-point count differs")
    sections = []
    section = member.element.section
    for index, row in enumerate(section_rows):
        saved_state = row["trial_state"]
        _same(saved_state, beam["trial_state"]["integration_point_states"][index])
        _same(row["strain_relation"], FIBER_SECTION_STRAIN_RELATION)
        _same(row["resultant_definition"], FIBER_SECTION_RESULTANT_DEFINITION)
        strain = row["generalized_strain"]
        axial = _number(strain["axial_strain"])
        curvature = _number(strain["curvature_z_per_m"])
        _same(axial, saved_state["axial_strain"])
        _same(curvature, saved_state["curvature_z_per_m"])
        fiber_strains = _vector(row["fiber_strains"], len(section.fibers))
        stresses = _vector(row["fiber_stresses_mpa"], len(section.fibers))
        fibers = row["fiber_responses"]
        if type(fibers) is not list or len(fibers) != len(section.fibers):
            raise ValueError("saved fiber count differs")
        projected_fibers = []
        for fiber_index, (fiber, sample) in enumerate(
            zip(section.fibers, fibers, strict=True)
        ):
            _same(sample["trial_state"], saved_state["fiber_states"][fiber_index])
            _same(_number(sample["total_strain"]), fiber_strains[fiber_index])
            _same(_number(sample["stress_mpa"]), stresses[fiber_index])
            projected_fibers.append(
                {
                    "fiber_index": fiber_index,
                    "material_kind": fiber.material_kind,
                    "strain": fiber_strains[fiber_index],
                    "stress_mpa": stresses[fiber_index],
                    "state_hash": sample["trial_state"]["state_hash"],
                }
            )
        sections.append(
            {
                "integration_point_index": index,
                "xi": xi[index],
                "weight": weight[index],
                "section_id": saved_state["section_id"],
                "section_contract_hash": saved_state["section_contract_hash"],
                "state_hash": saved_state["state_hash"],
                "step_index": saved_state["step_index"],
                "axial_strain": axial,
                "curvature_z_per_m": curvature,
                "axial_force_kn": _number(row["resultants"]["axial_force_kn"]),
                "moment_z_kn_m": _number(row["resultants"]["moment_z_kn_m"]),
                "fibers": projected_fibers,
            }
        )
    return {
        "member_id": member.member_id,
        "node_i": node_ids[member.node_i],
        "node_j": node_ids[member.node_j],
        "element_contract_hash": state.element_contract_hash,
        "member_feature_contract_hash": feature["feature_contract_hash"],
        "member_feature_response_hash": feature["response_hash"],
        "initial_length_m": initial_length,
        "current_length_m": length,
        "current_direction": direction,
        "end_force_global_kn_knm": net,
        "end_force_local_kn_knm": local,
        "sections": sections,
    }, state


def build_rc_corotational_detail_report(
    *, request: RCCorotationalJobRequest, result: dict[str, Any], nodal_report: bytes
) -> bytes:
    """Project originals after their service-authenticated snapshot validation."""
    nodal = json.loads(nodal_report)
    config = request.config
    compiled = compile_rc_corotational_control_model(
        request.model,
        fixed_nodal_loads=config.fixed_nodal_loads,
        experimental_pin_roller_beam=config.experimental_pin_roller_beam,
        experimental_fixed_guided_axial=config.experimental_fixed_guided_axial,
        experimental_portal_frame=config.experimental_portal_frame,
    )
    responses = []
    response_bytes = 0
    for index, row in enumerate(result["api_result"]["responses"]):
        members = row["members"]
        if type(members) is not list or len(members) != len(compiled.problem.members):
            raise ValueError("saved member count differs")
        projected, states = [], []
        for member_index, (member, raw) in enumerate(
            zip(compiled.problem.members, members, strict=True)
        ):
            item, state = _member_projection(
                member,
                raw,
                node_ids=compiled.node_ids,
                load_factor=row["load_factor"],
                state_index=index,
            )
            projected.append({"member_index": member_index, **item})
            states.append(state)
        checkpoint = StatefulCorotationalFiberFrame2DCheckpoint(
            case_id=compiled.problem.case_id,
            problem_contract_hash=compiled.problem.contract_hash,
            epoch=index + 1,
            step_index=index + 1,
            load_factor=row["load_factor"],
            parent_state_hash=row["parent_checkpoint_hash"],
            global_displacements=tuple(
                value
                for node in row["nodes"]
                for value in _vector(node["displacements_m_rad"], 3)
            ),
            element_states=tuple(states),
            state_hash=row["checkpoint_hash"],
        )
        if checkpoint.compute_state_hash() != row["checkpoint_hash"]:
            raise ValueError("saved member states differ from accepted checkpoint")
        responses.append(
            {
                "state_index": index,
                **{
                    key: row[key]
                    for key in (
                        "phase",
                        "checkpoint_hash",
                        "parent_checkpoint_hash",
                        "load_factor",
                    )
                },
                "members": projected,
            }
        )
        response_bytes += len(rc_corotational_job_canonical_bytes(responses[-1]))
        if response_bytes > RC_COROTATIONAL_DETAIL_REPORT_MAX_BYTES:
            raise RCCorotationalReportTooLargeError(
                "corotational detail history exceeds its byte bound"
            )
    payload = {
        "schema_version": RC_COROTATIONAL_DETAIL_REPORT_SCHEMA_VERSION,
        "bindings": nodal["bindings"],
        "nodal_report_hash": nodal["report_hash"],
        "units": RC_COROTATIONAL_DETAIL_REPORT_UNITS,
        "responses": responses,
        "structural_authority": nodal["structural_authority"],
        "derivation": {
            "version": "rc_corotational_stored_detail_projection.v1",
            "fresh_analysis_invocations": 0,
            "fresh_verification_invocations": 0,
            "source_fingerprint_invocations": 0,
            "new_structural_authority": False,
        },
        "claim_boundary": RC_COROTATIONAL_DETAIL_REPORT_CLAIM_BOUNDARY,
    }
    raw = rc_corotational_job_canonical_bytes(
        {**payload, "report_hash": _sha(rc_corotational_job_canonical_bytes(payload))}
    )
    if len(raw) > RC_COROTATIONAL_DETAIL_REPORT_MAX_BYTES:
        raise RCCorotationalReportTooLargeError(
            "corotational detail report exceeds its byte bound"
        )
    return raw
