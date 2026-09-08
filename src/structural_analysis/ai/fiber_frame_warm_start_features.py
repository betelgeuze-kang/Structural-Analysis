"""Bounded pre-analysis geometry/load features in the actual solver ordering.

Only immutable problem, element, section and material declarations are read.
No response, state, checkpoint, assembly or constitutive trial is evaluated.
The hashes bind stored values and source identity; they do not attest provenance
or replay a physical response. These features describe the small-displacement
RC fiber formulation, whose force and moment coordinates are kN and kN*m.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
import re
from typing import Any

from structural_analysis.assembly.stateful_fiber_frame2d import (
    STATEFUL_FIBER_FRAME2D_SCHEMA_VERSION,
    STATEFUL_FIBER_FRAME2D_TRANSFORMATION,
    StatefulFiberFrame2DMember,
    StatefulFiberFrame2DProblem,
)
from structural_analysis.elements.stateful_fiber_beam2d import StatefulFiberBeam2D
from structural_analysis.elements.stateful_fiber_beam2d_contract import (
    STATEFUL_FIBER_BEAM2D_INTERNAL_FORCE,
    STATEFUL_FIBER_BEAM2D_KINEMATICS,
    STATEFUL_FIBER_BEAM2D_SCHEMA_VERSION,
    STATEFUL_FIBER_BEAM2D_TANGENT,
)
from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    canonical_json_bytes,
)
from structural_analysis.materials.concrete_damage import (
    DAMAGE_ALGORITHM,
    AsymmetricConcreteDamageMaterial,
)
from structural_analysis.materials.stateful_fiber_section import (
    FIBER_SECTION_RESULTANT_DEFINITION,
    FIBER_SECTION_STRAIN_RELATION,
    FIBER_SECTION_TANGENT_DEFINITION,
    STATEFUL_FIBER_SECTION_SCHEMA_VERSION,
    StatefulRCFiberSection,
    StatefulSectionFiber,
)
from structural_analysis.materials.uniaxial_plasticity import (
    RETURN_MAPPING_ALGORITHM,
    BilinearCombinedHardeningSteel,
)


MODEL_FEATURE_PROFILE = "rc-fiber-warm-start-model-geometry-load.v1"
MODEL_FEATURE_SCHEMA_VERSION = "fiber-frame-warm-start-model-features.v1"
MAX_MODEL_FEATURE_COUNT = 2048
_HASH = re.compile(r"sha256:[0-9a-f]{64}")
_NAME = re.compile(r"[a-z][a-z0-9_]{0,127}")


def _finite(value: Any, name: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{name}: finite Python number required")
    try:
        number = float(value)
    except OverflowError as error:
        raise ValueError(f"{name}: finite Python number required") from error
    if not math.isfinite(number):
        raise ValueError(f"{name}: finite Python number required")
    return number


@dataclass(frozen=True)
class FiberFrameWarmStartModelFeatures:
    problem_contract_hash: str
    context_hash: str
    feature_names: tuple[str, ...]
    values: tuple[float, ...]
    feature_hash: str = field(init=False)

    def __post_init__(self) -> None:
        for name in ("problem_contract_hash", "context_hash"):
            value = getattr(self, name)
            if type(value) is not str or _HASH.fullmatch(value) is None:
                raise ValueError(f"{name}: prefixed SHA-256 required")
        if (
            type(self.feature_names) is not tuple
            or type(self.values) is not tuple
            or not 1 <= len(self.feature_names) <= MAX_MODEL_FEATURE_COUNT
            or len(self.feature_names) != len(self.values)
        ):
            raise ValueError(
                "model features: bounded matching immutable tuples required"
            )
        if any(
            type(name) is not str or _NAME.fullmatch(name) is None
            for name in self.feature_names
        ) or len(set(self.feature_names)) != len(self.feature_names):
            raise ValueError("model features: unique bounded feature names required")
        object.__setattr__(
            self, "values", tuple(_finite(value, "feature") for value in self.values)
        )
        object.__setattr__(self, "feature_hash", canonical_hash(self._payload()))

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": MODEL_FEATURE_SCHEMA_VERSION,
            "feature_profile": MODEL_FEATURE_PROFILE,
            "problem_contract_hash": self.problem_contract_hash,
            "context_hash": self.context_hash,
            "feature_names": list(self.feature_names),
            "values": list(self.values),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "feature_hash": self.feature_hash}


def decode_fiber_frame_warm_start_model_features(
    value: dict[str, Any],
) -> FiberFrameWarmStartModelFeatures:
    """Strict detached JSON decode; requires no problem or numerical replay."""
    keys = {
        "schema_version",
        "feature_profile",
        "problem_contract_hash",
        "context_hash",
        "feature_names",
        "values",
        "feature_hash",
    }
    if type(value) is not dict or set(value) != keys:
        raise ValueError("model feature artifact: exact fields required")
    if (
        value["schema_version"] != MODEL_FEATURE_SCHEMA_VERSION
        or value["feature_profile"] != MODEL_FEATURE_PROFILE
        or type(value["feature_names"]) is not list
        or type(value["values"]) is not list
    ):
        raise ValueError("model feature artifact: unsupported schema/profile or arrays")
    decoded = FiberFrameWarmStartModelFeatures(
        value["problem_contract_hash"],
        value["context_hash"],
        tuple(value["feature_names"]),
        tuple(value["values"]),
    )
    if canonical_json_bytes(decoded.to_dict()) != canonical_json_bytes(value):
        raise ValueError("model feature artifact: hash or typed payload mismatch")
    return decoded


def _material_parameters(material: Any, expected: type) -> dict[str, float]:
    if type(material) is not expected:
        raise ValueError("model features require exact supported RC material laws")
    parameters = {
        name: _finite(value, "material parameter")
        for name, value in asdict(material).items()
        if name != "material_id"
    }
    # Revalidate declaration ranges only; material constructors do not integrate.
    expected(**parameters)
    return parameters


def fiber_frame_warm_start_model_features(
    problem: StatefulFiberFrame2DProblem,
) -> FiberFrameWarmStartModelFeatures:
    """Read static declarations, retaining actual node/DOF/member/fiber order.

    Context excludes geometry, loads, fiber y/area and rotation scale because
    these are explicit features. It retains topology, integration and material
    laws. Entity aliases preserve feature meaning only if solver ordering is
    preserved; arbitrary DOF permutations are deliberately not conflated.
    """
    if type(problem) is not StatefulFiberFrame2DProblem:
        raise ValueError("model features require an exact StatefulFiberFrame2DProblem")
    if (
        type(problem.node_coordinates_m) is not tuple
        or type(problem.members) is not tuple
        or type(problem.fixed_global_dofs) is not tuple
        or type(problem.reference_external_loads) is not tuple
        or len(problem.node_coordinates_m) < 2
        or not problem.members
    ):
        raise ValueError("model features require immutable problem metadata")
    feature_count = 5 * len(problem.node_coordinates_m) + 1
    for member in problem.members:
        if (
            type(member) is not StatefulFiberFrame2DMember
            or type(member.element) is not StatefulFiberBeam2D
            or type(member.element.section) is not StatefulRCFiberSection
            or type(member.element.section.fibers) is not tuple
            or not member.element.section.fibers
        ):
            raise ValueError(
                "model features require exact immutable RC member sections"
            )
        feature_count += 1 + 2 * len(member.element.section.fibers)
        if feature_count > MAX_MODEL_FEATURE_COUNT:
            raise ValueError("model features exceed bounded feature count")
    names, values = [], []

    def add(name: str, value: Any) -> None:
        names.append(name)
        values.append(_finite(value, name))

    for node, coordinate in enumerate(problem.node_coordinates_m):
        if type(coordinate) is not tuple or len(coordinate) != 2:
            raise ValueError("model features require immutable XY coordinates")
        for axis, value in zip(("x", "y"), coordinate, strict=True):
            add(f"node_{node}_{axis}_m", value)
    dof_count = 3 * len(problem.node_coordinates_m)
    fixed = problem.fixed_global_dofs
    if (
        not fixed
        or any(type(dof) is not int or not 0 <= dof < dof_count for dof in fixed)
        or tuple(sorted(set(fixed))) != fixed
    ):
        raise ValueError("model features require valid fixed DOF metadata")
    loads = {}
    for row in problem.reference_external_loads:
        if (
            type(row) is not tuple
            or len(row) != 2
            or type(row[0]) is not int
            or not 0 <= row[0] < dof_count
            or row[0] in loads
        ):
            raise ValueError("model features require unique ordered reference DOFs")
        loads[row[0]] = _finite(row[1], "reference load")
    if not loads or not any(loads.values()):
        raise ValueError("model features require a nonzero reference load")
    for dof in range(dof_count):
        component = ("fx_kn", "fy_kn", "mz_kn_m")[dof % 3]
        add(f"node_{dof // 3}_reference_{component}", loads.get(dof, 0.0))
    scale = _finite(problem.rotation_coordinate_scale_m, "rotation scale")
    if scale <= 0:
        raise ValueError("model features require positive rotation scale")
    add("rotation_coordinate_scale_m", scale)
    members = []
    for index, member in enumerate(problem.members):
        element, section = member.element, member.element.section
        if (
            any(
                type(node) is not int or not 0 <= node < dof_count // 3
                for node in (member.node_i, member.node_j)
            )
            or member.node_i == member.node_j
        ):
            raise ValueError("model features require valid oriented member endpoints")
        length = _finite(element.length_m, "member length")
        if length <= 0 or not math.isclose(
            math.dist(
                problem.node_coordinates_m[member.node_i],
                problem.node_coordinates_m[member.node_j],
            ),
            length,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise ValueError("model features require consistent member geometry")
        if type(
            element.integration_order
        ) is not int or element.integration_order not in (2, 3):
            raise ValueError("model features require supported quadrature")
        add(f"member_{index}_length_m", length)
        kinds = []
        for fiber_index, fiber in enumerate(section.fibers):
            if type(fiber) is not StatefulSectionFiber or fiber.material_kind not in (
                "steel",
                "concrete",
            ):
                raise ValueError("model features require exact supported fibers")
            if _finite(fiber.area_m2, "fiber area") <= 0:
                raise ValueError("model features require positive fiber areas")
            kinds.append(fiber.material_kind)
            add(f"member_{index}_fiber_{fiber_index}_y_m", fiber.y_m)
            add(f"member_{index}_fiber_{fiber_index}_area_m2", fiber.area_m2)
        if set(kinds) != {"steel", "concrete"}:
            raise ValueError("model features require both concrete and steel fibers")
        members.append(
            {
                "node_i": member.node_i,
                "node_j": member.node_j,
                "integration_order": element.integration_order,
                "integration_point_xi": list(element.quadrature[0]),
                "integration_point_weights": list(element.quadrature[1]),
                "fiber_material_kinds": kinds,
                "steel": _material_parameters(
                    section.steel, BilinearCombinedHardeningSteel
                ),
                "concrete": _material_parameters(
                    section.concrete, AsymmetricConcreteDamageMaterial
                ),
            }
        )
    context = {
        "feature_profile": MODEL_FEATURE_PROFILE,
        "assembly_schema": STATEFUL_FIBER_FRAME2D_SCHEMA_VERSION,
        "transformation": STATEFUL_FIBER_FRAME2D_TRANSFORMATION,
        "element_schema": STATEFUL_FIBER_BEAM2D_SCHEMA_VERSION,
        "kinematics": STATEFUL_FIBER_BEAM2D_KINEMATICS,
        "internal_force": STATEFUL_FIBER_BEAM2D_INTERNAL_FORCE,
        "tangent": STATEFUL_FIBER_BEAM2D_TANGENT,
        "section_schema": STATEFUL_FIBER_SECTION_SCHEMA_VERSION,
        "strain_relation": FIBER_SECTION_STRAIN_RELATION,
        "resultant_definition": FIBER_SECTION_RESULTANT_DEFINITION,
        "section_tangent": FIBER_SECTION_TANGENT_DEFINITION,
        "steel_algorithm": RETURN_MAPPING_ALGORITHM,
        "concrete_algorithm": DAMAGE_ALGORITHM,
        "global_dof_order": "node-major:UX,UY,RZ",
        "reference_force_units": "kN,kN,kN*m",
        "node_count": len(problem.node_coordinates_m),
        "free_global_dofs": list(problem.free_global_dofs),
        "fixed_global_dofs": list(fixed),
        "members": members,
    }
    return FiberFrameWarmStartModelFeatures(
        problem.contract_hash, canonical_hash(context), tuple(names), tuple(values)
    )
