"""Entity-name invariant duplicate detection for the bounded public RC profile.

This research identity is separate from authored model/checkpoint identities.
It does not establish project provenance, licensing, or general physical
equivalence under rotations, translations, or changes of numerical formulation.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from structural_analysis.api import nonlinear_fiber_frame as public_api
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.model.schema import CanonicalModel


PHYSICAL_MODEL_IDENTITY_PROFILE = "public-rc-fiber-frame-entity-invariant-model.v1"
_SECTION_FLOAT_FIELDS = ("width_m", "depth_m", "cover_m", "bar_area_m2")
_SECTION_COUNT_FIELDS = (
    "concrete_layer_count", "top_bar_count", "bottom_bar_count",
)


def _physical_float(value: float) -> float:
    # Authored -0.0 and +0.0 represent the same coordinate/load/material value.
    return float(value) if value else 0.0


def fiber_frame_physical_model_payload(model: CanonicalModel) -> dict[str, Any]:
    """Compile without solving, then expand material/section references by value.

    Unique coordinates are required by the public compiler. They give a stable
    node order under entity renaming and declaration permutations. Member endpoint
    order remains significant because it defines the element's local axes.
    """

    if type(model) is not CanonicalModel:
        raise ValueError("physical identity requires an exact CanonicalModel")
    snapshot = model.detached_analysis_snapshot()
    compiled, blockers, _ = public_api._compile(snapshot)
    if compiled is None or blockers:
        raise ValueError("physical identity requires the supported public RC profile")
    problem = compiled.problem
    node_order = sorted(
        range(len(problem.node_coordinates_m)),
        key=lambda index: problem.node_coordinates_m[index],
    )
    node_index = {original: canonical for canonical, original in enumerate(node_order)}

    def dof(value: int) -> int:
        return 3 * node_index[value // 3] + value % 3

    authored_elements = {row["id"]: row for row in snapshot.elements}
    authored_sections = {row["id"]: row for row in snapshot.sections}
    members = []
    for member in problem.members:
        element = member.element
        section = authored_sections[authored_elements[member.member_id]["section"]]
        expanded_section = {
            "type": section["type"],
            **{name: _physical_float(section[name]) for name in _SECTION_FLOAT_FIELDS},
            **{name: section[name] for name in _SECTION_COUNT_FIELDS},
            **{
                kind: {
                    name: _physical_float(value)
                    for name, value in asdict(getattr(element.section, kind)).items()
                    if name != "material_id"
                }
                for kind in ("steel", "concrete")
            },
        }
        members.append({
            "nodes": [node_index[member.node_i], node_index[member.node_j]],
            "integration_order": element.integration_order,
            "section": expanded_section,
        })
    members.sort(key=lambda row: tuple(row["nodes"]))
    return {
        "identity_profile": PHYSICAL_MODEL_IDENTITY_PROFILE,
        "compiler_profile": public_api.PUBLIC_RC_FIBER_FRAME_COMPILER_PROFILE,
        "node_coordinates_m": [
            [_physical_float(value) for value in problem.node_coordinates_m[index]]
            for index in node_order
        ],
        "members": members,
        "fixed_global_dofs": sorted(dof(value) for value in problem.fixed_global_dofs),
        "reference_external_loads": sorted(
            [dof(index), _physical_float(value)]
            for index, value in problem.reference_external_loads
        ),
        "rotation_coordinate_scale_m": problem.rotation_coordinate_scale_m,
    }


def fiber_frame_physical_model_identity(model: CanonicalModel) -> str:
    """Return the versioned, entity-name invariant duplicate-detection hash."""

    return canonical_hash(fiber_frame_physical_model_payload(model))
