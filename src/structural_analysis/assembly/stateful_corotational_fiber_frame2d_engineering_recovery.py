"""Exact engineering recovery for the bounded corotational portal candidate.

The recovery starts from the last accepted *parent* checkpoint and terminal
coordinates, independently repeats the constitutive/section/element/global
assembly transition, and only then freezes SI engineering artifacts.  Solver
returned force arrays are comparison evidence, never the recovery source.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from functools import lru_cache
from importlib import resources
import json
import math
import re
from types import MappingProxyType
from typing import Any, Literal, NoReturn

from jsonschema import Draft202012Validator, validators
import numpy as np

from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    StatefulCorotationalFiberFrame2DProblem,
    assemble_stateful_corotational_fiber_frame2d,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_j1_j5 import (
    CorotationalFiberFrameJ1J5Adapter,
    validate_corotational_fiber_frame_j1_j5_adapter,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_general import (
    CorotationalFiberFrameGeneralJ1J5Adapter,
    validate_corotational_fiber_frame_general_j1_j5_adapter,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_solver import (
    StatefulCorotationalFiberFrame2DLoadPathResult,
)
from structural_analysis.engine_v2.contracts._canonical import (
    array_content_hash,
    array_data_hash,
    canonical_hash,
    has_immutable_bytes_backing,
    immutable_array,
)
from structural_analysis.engine_v2.contracts.result_quantity import (
    default_result_quantity_catalog,
)
from structural_analysis.materials.stateful_fiber_section import (
    StatefulFiberSectionResponse,
    StatefulRCFiberSection,
)


COROTATIONAL_FIBER_FRAME_ENGINEERING_RESULT_SCHEMA_VERSION = (
    "corotational-fiber-frame2d-engineering-result-ir.v1"
)
COROTATIONAL_FIBER_FRAME_ENGINEERING_RECOVERY_PROFILE = (
    "exact_terminal_parent_corotational_section_global_replay.v1"
)
COROTATIONAL_FIBER_FRAME_ENGINEERING_AUTHORITY_PROFILE = (
    "exact_bounded_portal_engineering_candidate.v1"
)
COROTATIONAL_FIBER_FRAME_ENGINEERING_RESULT_KIND = (
    "corotational_portal_reaction_member_section_fiber"
)
COROTATIONAL_FIBER_FRAME_GENERAL_ENGINEERING_AUTHORITY_PROFILE = (
    "exact_connected_frame2d_engineering_candidate.v1"
)
COROTATIONAL_FIBER_FRAME_GENERAL_ENGINEERING_RESULT_KIND = (
    "corotational_connected_frame2d_reaction_member_section_fiber"
)
COROTATIONAL_FIBER_FRAME_ENGINEERING_CONSISTENCY_TOLERANCE = 1.0e-12
COROTATIONAL_FIBER_FRAME_ENGINEERING_FIBER_STRAIN_TOLERANCE = 1.0e-14

_HASH_ZERO = "sha256:" + "0" * 64
_STABLE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")

_AUTHORITY_AXES = MappingProxyType(
    {
        "convergence": "inherited_bounded_candidate",
        "displacement": "exact_bounded_candidate",
        "reaction": "exact_bounded_candidate",
        "member_force": "exact_bounded_candidate",
        "member_features": "not_supported",
        "section_resultant": "exact_bounded_candidate",
        "fiber_result": "exact_bounded_candidate",
        "fallback": "not_used",
        "public_api": "not_promoted",
        "external_vv": "not_attached",
        "engineering_design": "not_authoritative",
        "release_readiness": "not_authoritative",
    }
)
_LIMITATIONS = (
    "one_bay_one_story_portal_only",
    "zero_prescribed_displacement_only",
    "load_control_cpu_dense_newton_only",
    "member_end_releases_not_supported",
    "rigid_offsets_not_supported",
    "distributed_member_loads_not_supported",
    "external_level2_not_attached",
    "public_capability_not_promoted",
    "detached_manifest_requires_retained_artifact_bytes",
    "detached_manifest_source_authenticity_not_established",
)
_GENERAL_LIMITATIONS = (
    "connected_planar_frame_graph_only",
    "proportional_nodal_load_only",
    "prescribed_displacement_scaled_by_load_factor",
    "load_control_cpu_dense_or_native_sparse_newton_only",
    "parallel_members_not_supported",
    "disconnected_graphs_not_supported",
    "member_end_releases_not_supported",
    "rigid_offsets_not_supported",
    "distributed_member_loads_not_supported",
    "direct_displacement_control_not_supported",
    "external_level2_not_attached",
    "public_capability_not_promoted",
    "detached_manifest_requires_retained_artifact_bytes",
    "detached_manifest_source_authenticity_not_established",
)

_STRICT_JSON_TYPE_CHECKER = Draft202012Validator.TYPE_CHECKER.redefine(
    "integer", lambda _checker, value: type(value) is int
).redefine("number", lambda _checker, value: type(value) in (int, float))
_StrictDraft202012Validator = validators.extend(
    Draft202012Validator,
    type_checker=_STRICT_JSON_TYPE_CHECKER,
)

CorotationalEngineeringSourceAdapter = (
    CorotationalFiberFrameJ1J5Adapter | CorotationalFiberFrameGeneralJ1J5Adapter
)

_ARRAY_SPECS: Mapping[
    str,
    tuple[str, str, tuple[str, ...], str, Literal["output", "mapping"]],
] = MappingProxyType(
    {
        "node_translation_m": (
            "<f8",
            "m",
            ("displacement.translation",),
            "node",
            "output",
        ),
        "node_rotation_rad": (
            "<f8",
            "rad",
            ("displacement.rotation",),
            "node",
            "output",
        ),
        "reaction_force_n": (
            "<f8",
            "N",
            ("reaction.force",),
            "node",
            "output",
        ),
        "reaction_moment_nm": (
            "<f8",
            "N*m",
            ("reaction.moment",),
            "node",
            "output",
        ),
        "member_end_force_n": (
            "<f8",
            "N",
            ("member.force",),
            "member",
            "output",
        ),
        "member_end_moment_nm": (
            "<f8",
            "N*m",
            ("member.moment",),
            "member",
            "output",
        ),
        "section_axial_force_n": (
            "<f8",
            "N",
            ("section.axial_force",),
            "section",
            "output",
        ),
        "section_moment_nm": (
            "<f8",
            "N*m",
            ("section.moment",),
            "section",
            "output",
        ),
        "section_strain": (
            "<f8",
            "1",
            ("section.strain",),
            "section",
            "output",
        ),
        "section_curvature_per_m": (
            "<f8",
            "1/m",
            ("section.curvature",),
            "section",
            "output",
        ),
        "fiber_strain": (
            "<f8",
            "1",
            ("fiber.strain",),
            "fiber",
            "output",
        ),
        "fiber_stress_pa": (
            "<f8",
            "Pa",
            ("fiber.stress",),
            "fiber",
            "output",
        ),
        "member_node_indices": ("<i8", "1", (), "member", "mapping"),
        "section_offsets": ("<i8", "1", (), "member", "mapping"),
        "section_xi": ("<f8", "1", (), "section", "mapping"),
        "fiber_offsets": ("<i8", "1", (), "section", "mapping"),
        "fiber_y_m": ("<f8", "m", (), "fiber", "mapping"),
        "fiber_area_m2": ("<f8", "m^2", (), "fiber", "mapping"),
    }
)
_ARRAY_NAMES = tuple(_ARRAY_SPECS)


class CorotationalFiberFrameEngineeringRecoveryError(ValueError):
    """Stable fail-closed recovery error."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class CorotationalEngineeringArrayDescriptor:
    name: str
    dtype: str
    shape: tuple[int, ...]
    unit: str
    quantity_ids: tuple[str, ...]
    order_scope: str
    authority_role: Literal["output", "mapping"]
    order_hash: str
    data_hash: str
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dtype": self.dtype,
            "shape": list(self.shape),
            "unit": self.unit,
            "quantity_ids": list(self.quantity_ids),
            "order_scope": self.order_scope,
            "authority_role": self.authority_role,
            "order_hash": self.order_hash,
            "data_hash": self.data_hash,
            "content_hash": self.content_hash,
        }


@dataclass(frozen=True)
class CorotationalFiberFrameEngineeringResultIR:
    schema_version: str
    engineering_result_id: str
    engineering_result_hash: str
    result_kind: str
    recovery_profile: str
    authority_profile: str
    compiler_hash: str
    source_adapter_hash: str
    model_content_hash: str
    problem_contract_hash: str
    terminal_checkpoint_hash: str
    terminal_assembly_hash: str
    quantity_catalog_hash: str
    load_factor: float
    node_count: int
    member_count: int
    section_count: int
    fiber_count: int
    member_ids: tuple[str, ...]
    metrics: Mapping[str, float | bool]
    authority_axes: Mapping[str, str]
    limitations: tuple[str, ...]
    array_bundle_hash: str
    descriptors: tuple[CorotationalEngineeringArrayDescriptor, ...]
    _arrays: Mapping[str, np.ndarray] = field(repr=False, compare=False)
    _adapter: CorotationalEngineeringSourceAdapter = field(repr=False, compare=False)

    def artifact(self, name: str) -> np.ndarray:
        try:
            return self._arrays[name]
        except KeyError as exc:
            raise KeyError(
                f"Unknown corotational engineering artifact: {name}"
            ) from exc

    def to_manifest(self) -> dict[str, Any]:
        validate_corotational_fiber_frame_engineering_result_ir(self)
        return _result_payload(self, include_hash=True)


@dataclass(frozen=True)
class _RecoveryReplay:
    terminal_assembly_hash: str
    arrays: Mapping[str, np.ndarray]
    order_hashes: Mapping[str, str]
    counts: Mapping[str, int]
    member_ids: tuple[str, ...]
    metrics: Mapping[str, float | bool]


def create_corotational_fiber_frame_engineering_result_ir(
    *,
    engineering_result_id: str,
    source_adapter: CorotationalEngineeringSourceAdapter,
) -> CorotationalFiberFrameEngineeringResultIR:
    """Replay and freeze exact SI engineering results for a bounded profile."""

    adapter = _validate_source_adapter(source_adapter)
    result_kind, authority_profile, limitations = _source_profile(adapter)
    result_id = _stable_id(engineering_result_id, "/engineering_result_id")
    replay = _recover(adapter)
    descriptors = _descriptors(replay.arrays, replay.order_hashes)
    array_bundle_hash = canonical_hash([row.to_dict() for row in descriptors])
    catalog = default_result_quantity_catalog()
    compilation = adapter._compilation
    provisional = CorotationalFiberFrameEngineeringResultIR(
        schema_version=COROTATIONAL_FIBER_FRAME_ENGINEERING_RESULT_SCHEMA_VERSION,
        engineering_result_id=result_id,
        engineering_result_hash=_HASH_ZERO,
        result_kind=result_kind,
        recovery_profile=COROTATIONAL_FIBER_FRAME_ENGINEERING_RECOVERY_PROFILE,
        authority_profile=authority_profile,
        compiler_hash=adapter.compiler_hash,
        source_adapter_hash=adapter.adapter_hash,
        model_content_hash=adapter.model_content_hash,
        problem_contract_hash=adapter.problem_contract_hash,
        terminal_checkpoint_hash=adapter.terminal_checkpoint_hash,
        terminal_assembly_hash=replay.terminal_assembly_hash,
        quantity_catalog_hash=catalog.catalog_hash,
        load_factor=adapter.terminal_load_factor,
        node_count=int(replay.counts["node"]),
        member_count=int(replay.counts["member"]),
        section_count=int(replay.counts["section"]),
        fiber_count=int(replay.counts["fiber"]),
        member_ids=replay.member_ids,
        metrics=replay.metrics,
        authority_axes=_AUTHORITY_AXES,
        limitations=limitations,
        array_bundle_hash=array_bundle_hash,
        descriptors=descriptors,
        _arrays=replay.arrays,
        _adapter=adapter,
    )
    result = replace(
        provisional,
        engineering_result_hash=canonical_hash(
            _result_payload(provisional, include_hash=False)
        ),
    )
    # Retain exact identity, not merely an equivalent compiler object.
    if result._adapter._compilation is not compilation:
        _fail(
            "corotational_recovery_compiler_identity_mismatch",
            "/source_adapter/compiler_hash",
            "Recovery lost the retained compiler identity.",
        )
    return validate_corotational_fiber_frame_engineering_result_ir(result)


def validate_corotational_fiber_frame_engineering_result_ir(
    result: CorotationalFiberFrameEngineeringResultIR,
) -> CorotationalFiberFrameEngineeringResultIR:
    if type(result) is not CorotationalFiberFrameEngineeringResultIR:
        _fail(
            "corotational_engineering_result_type_invalid",
            "/",
            "Expected exact CorotationalFiberFrameEngineeringResultIR.",
        )
    adapter = _validate_source_adapter(result._adapter)
    result_kind, authority_profile, limitations = _source_profile(adapter)
    replay = _recover(adapter)
    expected_descriptors = _descriptors(replay.arrays, replay.order_hashes)
    expected_bundle_hash = canonical_hash(
        [row.to_dict() for row in expected_descriptors]
    )
    catalog_hash = default_result_quantity_catalog().catalog_hash
    expected_metadata = (
        result.schema_version
        == COROTATIONAL_FIBER_FRAME_ENGINEERING_RESULT_SCHEMA_VERSION
        and _stable_id(result.engineering_result_id, "/engineering_result_id")
        == result.engineering_result_id
        and result.result_kind == result_kind
        and result.recovery_profile
        == COROTATIONAL_FIBER_FRAME_ENGINEERING_RECOVERY_PROFILE
        and result.authority_profile == authority_profile
        and result.compiler_hash == adapter.compiler_hash
        and result.source_adapter_hash == adapter.adapter_hash
        and result.model_content_hash == adapter.model_content_hash
        and result.problem_contract_hash == adapter.problem_contract_hash
        and result.terminal_checkpoint_hash == adapter.terminal_checkpoint_hash
        and result.terminal_assembly_hash == replay.terminal_assembly_hash
        and result.quantity_catalog_hash == catalog_hash
        and result.load_factor == adapter.terminal_load_factor
        and result.node_count == replay.counts["node"]
        and result.member_count == replay.counts["member"]
        and result.section_count == replay.counts["section"]
        and result.fiber_count == replay.counts["fiber"]
        and result.member_ids == replay.member_ids
        and dict(result.metrics) == dict(replay.metrics)
        and dict(result.authority_axes) == dict(_AUTHORITY_AXES)
        and result.limitations == limitations
        and result.descriptors == expected_descriptors
        and result.array_bundle_hash == expected_bundle_hash
    )
    if not expected_metadata:
        _fail(
            "corotational_engineering_result_binding_mismatch",
            "/",
            "Result metadata differs from exact recovery replay.",
        )
    if tuple(result._arrays) != _ARRAY_NAMES:
        _fail(
            "corotational_engineering_result_array_set_invalid",
            "/artifacts",
            "Artifact set or order differs from v1.",
        )
    for name in _ARRAY_NAMES:
        stored = result._arrays[name]
        expected = replay.arrays[name]
        if not has_immutable_bytes_backing(stored) or not _exact_array(
            stored, expected
        ):
            _fail(
                "corotational_engineering_result_array_mismatch",
                f"/artifacts/{name}",
                "Stored artifact differs from immutable recovery replay.",
            )
    expected_hash = canonical_hash(_result_payload(result, include_hash=False))
    if result.engineering_result_hash != expected_hash:
        _fail(
            "corotational_engineering_result_hash_mismatch",
            "/engineering_result_hash",
            "Result hash differs from canonical manifest content.",
        )
    payload = _result_payload(result, include_hash=True)
    errors = sorted(
        _schema_validator().iter_errors(payload), key=lambda row: list(row.path)
    )
    if errors:
        first = errors[0]
        path = "/" + "/".join(str(part) for part in first.absolute_path)
        _fail("corotational_engineering_result_schema_invalid", path, first.message)
    return result


def validate_corotational_fiber_frame_engineering_result_manifest(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a detached manifest; artifact bytes remain separately required."""

    try:
        normalized = json.loads(json.dumps(dict(payload), allow_nan=False))
    except (TypeError, ValueError, OverflowError):
        _fail(
            "corotational_engineering_result_manifest_invalid",
            "/",
            "Engineering result manifest must be a finite JSON object.",
        )
    errors = sorted(
        _schema_validator().iter_errors(normalized), key=lambda row: list(row.path)
    )
    if errors:
        first = errors[0]
        path = "/" + "/".join(str(part) for part in first.absolute_path)
        _fail("corotational_engineering_result_schema_invalid", path, first.message)
    claimed = str(normalized["engineering_result_hash"])
    body = dict(normalized)
    body.pop("engineering_result_hash")
    if claimed != canonical_hash(body):
        _fail(
            "corotational_engineering_result_hash_mismatch",
            "/engineering_result_hash",
            "Manifest hash differs from canonical content.",
        )
    _validate_detached_manifest_semantics(normalized)
    return normalized


def _validate_detached_manifest_semantics(payload: Mapping[str, Any]) -> None:
    counts = payload["counts"]
    descriptors = payload["array_descriptors"]
    expected_limitations: tuple[str, ...]
    if payload["result_kind"] == COROTATIONAL_FIBER_FRAME_ENGINEERING_RESULT_KIND:
        expected_authority_profile = (
            COROTATIONAL_FIBER_FRAME_ENGINEERING_AUTHORITY_PROFILE
        )
        expected_limitations = _LIMITATIONS
        count_profile_passed = counts["node"] == 4 and counts["member"] == 3
    elif (
        payload["result_kind"]
        == COROTATIONAL_FIBER_FRAME_GENERAL_ENGINEERING_RESULT_KIND
    ):
        expected_authority_profile = (
            COROTATIONAL_FIBER_FRAME_GENERAL_ENGINEERING_AUTHORITY_PROFILE
        )
        expected_limitations = _GENERAL_LIMITATIONS
        count_profile_passed = (
            2 <= counts["node"] <= 128 and 1 <= counts["member"] <= 256
        )
    else:
        _fail(
            "corotational_engineering_result_kind_invalid",
            "/result_kind",
            "Detached result kind is not supported by v1.",
        )
    if (
        payload["quantity_catalog_hash"]
        != default_result_quantity_catalog().catalog_hash
        or payload["authority_profile"] != expected_authority_profile
        or payload["authority_axes"] != dict(_AUTHORITY_AXES)
        or payload["limitations"] != list(expected_limitations)
        or not count_profile_passed
        or len(payload["member_ids"]) != counts["member"]
    ):
        _fail(
            "corotational_engineering_result_binding_mismatch",
            "/",
            "Detached metadata differs from the fixed v1 result contract.",
        )
    if payload["array_bundle_hash"] != canonical_hash(descriptors):
        _fail(
            "corotational_engineering_array_bundle_hash_mismatch",
            "/array_bundle_hash",
            "Array bundle hash differs from the ordered descriptors.",
        )
    expected_shapes = _detached_array_shapes(counts)
    scope_hashes: dict[str, str] = {}
    if [row["name"] for row in descriptors] != list(_ARRAY_NAMES):
        _fail(
            "corotational_engineering_descriptor_set_invalid",
            "/array_descriptors",
            "Descriptor set or order differs from v1.",
        )
    for index, row in enumerate(descriptors):
        name = row["name"]
        dtype, unit, quantities, scope, role = _ARRAY_SPECS[name]
        if (
            row["dtype"] != dtype
            or row["shape"] != list(expected_shapes[name])
            or row["unit"] != unit
            or row["quantity_ids"] != list(quantities)
            or row["order_scope"] != scope
            or row["authority_role"] != role
        ):
            _fail(
                "corotational_engineering_descriptor_binding_mismatch",
                f"/array_descriptors/{index}",
                "Descriptor metadata differs from the fixed v1 artifact contract.",
            )
        previous = scope_hashes.setdefault(scope, row["order_hash"])
        if row["order_hash"] != previous:
            _fail(
                "corotational_engineering_order_hash_mismatch",
                f"/array_descriptors/{index}/order_hash",
                "Artifacts in one order scope must share the same order hash.",
            )


def _detached_array_shapes(counts: Mapping[str, int]) -> Mapping[str, tuple[int, ...]]:
    node_count = counts["node"]
    member_count = counts["member"]
    section_count = counts["section"]
    fiber_count = counts["fiber"]
    return MappingProxyType(
        {
            "node_translation_m": (node_count, 2),
            "node_rotation_rad": (node_count,),
            "reaction_force_n": (node_count, 2),
            "reaction_moment_nm": (node_count,),
            "member_end_force_n": (member_count, 4),
            "member_end_moment_nm": (member_count, 2),
            "section_axial_force_n": (section_count,),
            "section_moment_nm": (section_count,),
            "section_strain": (section_count,),
            "section_curvature_per_m": (section_count,),
            "fiber_strain": (fiber_count,),
            "fiber_stress_pa": (fiber_count,),
            "member_node_indices": (member_count, 2),
            "section_offsets": (member_count + 1,),
            "section_xi": (section_count,),
            "fiber_offsets": (section_count + 1,),
            "fiber_y_m": (fiber_count,),
            "fiber_area_m2": (fiber_count,),
        }
    )


def _validate_source_adapter(
    adapter: CorotationalEngineeringSourceAdapter,
) -> CorotationalEngineeringSourceAdapter:
    if type(adapter) is CorotationalFiberFrameJ1J5Adapter:
        return validate_corotational_fiber_frame_j1_j5_adapter(adapter)
    if type(adapter) is CorotationalFiberFrameGeneralJ1J5Adapter:
        return validate_corotational_fiber_frame_general_j1_j5_adapter(adapter)
    _fail(
        "corotational_engineering_source_adapter_type_invalid",
        "/source_adapter",
        "Expected an exact portal or connected-frame J1-J5 adapter.",
    )


def _source_profile(
    adapter: CorotationalEngineeringSourceAdapter,
) -> tuple[str, str, tuple[str, ...]]:
    if type(adapter) is CorotationalFiberFrameJ1J5Adapter:
        return (
            COROTATIONAL_FIBER_FRAME_ENGINEERING_RESULT_KIND,
            COROTATIONAL_FIBER_FRAME_ENGINEERING_AUTHORITY_PROFILE,
            _LIMITATIONS,
        )
    if type(adapter) is CorotationalFiberFrameGeneralJ1J5Adapter:
        return (
            COROTATIONAL_FIBER_FRAME_GENERAL_ENGINEERING_RESULT_KIND,
            COROTATIONAL_FIBER_FRAME_GENERAL_ENGINEERING_AUTHORITY_PROFILE,
            _GENERAL_LIMITATIONS,
        )
    _fail(
        "corotational_engineering_source_adapter_type_invalid",
        "/source_adapter",
        "Expected an exact portal or connected-frame J1-J5 adapter.",
    )


def _recover(adapter: CorotationalEngineeringSourceAdapter) -> _RecoveryReplay:
    source_manifest_before = adapter.to_manifest()
    problem: StatefulCorotationalFiberFrame2DProblem = adapter._compilation._problem
    path = adapter._path
    if not path.steps:
        _fail(
            "corotational_recovery_terminal_step_missing",
            "/source_adapter/path/steps",
            "Exact recovery requires a committed terminal step.",
        )
    terminal_step = path.steps[-1]
    terminal = path.final_checkpoint
    parent = terminal_step.parent_checkpoint
    scale = np.asarray(problem.physical_coordinate_scale, dtype=np.float64)
    terminal_displacement = np.asarray(terminal.global_displacements, dtype=np.float64)
    terminal_generalized = terminal_displacement / scale
    replay = assemble_stateful_corotational_fiber_frame2d(
        problem,
        parent,
        target_load_factor=terminal.load_factor,
        trial_free_coordinates_m=terminal_generalized[list(problem.free_global_dofs)],
    )
    terminal_assembly_hash = canonical_hash(replay.to_dict())
    if (
        not _terminal_path_target_passed(path)
        or not terminal_step.committed
        or terminal.parent_state_hash != parent.state_hash
        or replay.parent_checkpoint_hash != parent.state_hash
        or terminal_assembly_hash
        != canonical_hash(terminal_step.trial_assembly.to_dict())
        or not _exact_array(replay.global_displacements, terminal_displacement)
    ):
        _fail(
            "corotational_recovery_terminal_replay_mismatch",
            "/replay",
            "Independent terminal assembly differs from the accepted transition.",
        )

    node_count = len(problem.node_coordinates_m)
    member_count = len(problem.members)
    displacement = np.asarray(replay.global_displacements).reshape(node_count, 3)
    physical_residual = replay.internal_loads_global - replay.external_loads_global
    reaction = np.zeros(problem.global_dof_count, dtype=np.float64)
    reaction[list(problem.fixed_global_dofs)] = physical_residual[
        list(problem.fixed_global_dofs)
    ]
    if not _exact_array(reaction, replay.reactions_global):
        _fail(
            "corotational_recovery_reaction_partition_mismatch",
            "/replay/reactions",
            "Constrained residual differs from the assembly reaction partition.",
        )

    member_nodes: list[tuple[int, int]] = []
    member_force: list[np.ndarray] = []
    member_moment: list[np.ndarray] = []
    section_offsets = [0]
    section_xi: list[float] = []
    section_axial: list[float] = []
    section_moment: list[float] = []
    section_strain: list[float] = []
    section_curvature: list[float] = []
    fiber_offsets = [0]
    fiber_y: list[float] = []
    fiber_area: list[float] = []
    fiber_strain: list[float] = []
    fiber_stress_pa: list[float] = []
    member_order: list[dict[str, Any]] = []
    section_order: list[dict[str, Any]] = []
    fiber_order: list[dict[str, Any]] = []
    scatter = np.zeros(problem.global_dof_count, dtype=np.float64)
    external_scatter = (
        terminal.load_factor * problem.reference_external_load_vector()
    ).copy()
    local_global_error = 0.0
    member_feature_error = 0.0
    release_equilibrium_scaled = 0.0
    section_error = 0.0
    fiber_error = 0.0
    state_bytes_exact = True

    for member_index, (member, row, terminal_state) in enumerate(
        zip(
            problem.members,
            replay.member_assemblies,
            terminal.element_states,
            strict=True,
        )
    ):
        response = row.response
        feature_response = row.feature_response
        if (
            response.state.state_hash != terminal_state.state_hash
            or response.state.canonical_bytes() != terminal_state.canonical_bytes()
        ):
            state_bytes_exact = False
        direction = np.asarray(response.kinematics.current_direction, dtype=np.float64)
        cosine, sine = float(direction[0]), float(direction[1])
        rotation = np.asarray(
            [
                [cosine, sine, 0.0, 0.0, 0.0, 0.0],
                [-sine, cosine, 0.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, cosine, sine, 0.0],
                [0.0, 0.0, 0.0, -sine, cosine, 0.0],
                [0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )
        raw_element_force = np.asarray(
            feature_response.element_internal_load_global, dtype=np.float64
        )
        net_element_force = np.asarray(
            feature_response.element_net_end_force_global, dtype=np.float64
        )
        local_force = rotation @ net_element_force
        local_global_error = max(
            local_global_error,
            _scaled_linf(rotation.T @ local_force, net_element_force),
        )
        scatter[list(row.global_dofs)] += row.internal_load_global
        external_scatter[list(row.global_dofs)] += row.equivalent_external_load_global
        member_feature_error = max(
            member_feature_error,
            _scaled_linf(
                feature_response.node_to_element_jacobian.T @ raw_element_force,
                row.internal_load_global,
            ),
            _scaled_linf(
                feature_response.node_to_element_jacobian.T
                @ feature_response.element_equivalent_external_load_global,
                row.equivalent_external_load_global,
            ),
        )
        release_equilibrium_scaled = max(
            release_equilibrium_scaled,
            _linf(feature_response.release_residual_kn_m)
            / max(1.0, _linf(raw_element_force)),
        )
        member_nodes.append((member.node_i, member.node_j))
        member_force.append(local_force[[0, 1, 3, 4]] * 1000.0)
        member_moment.append(local_force[[2, 5]] * 1000.0)
        member_order.append(
            {
                "index": member_index,
                "member_id": member.member_id,
                "node_i": member.node_i,
                "node_j": member.node_j,
                "element_contract_hash": member.element.contract_hash,
                "member_feature_contract_hash": member.features.contract_hash,
                "member_feature_response_hash": feature_response.response_hash,
                "release_residual_kn_m": (
                    feature_response.release_residual_kn_m.tolist()
                ),
            }
        )

        fiber_response = response.fiber_beam_response
        section = member.element.section
        if type(section) is not StatefulRCFiberSection:
            _fail(
                "corotational_recovery_section_type_unsupported",
                f"/members/{member_index}/section",
                "Recovery v1 requires exact StatefulRCFiberSection.",
            )
        points, weights = member.element.basic_beam.quadrature
        jacobian = 0.5 * member.element.initial_length_m
        manual_local_force = np.zeros(6, dtype=np.float64)
        terminal_sections = terminal_state.basic_beam_state.integration_point_states
        for ip_index, (xi, weight, section_response, terminal_section) in enumerate(
            zip(
                points,
                weights,
                fiber_response.section_responses,
                terminal_sections,
                strict=True,
            )
        ):
            if type(section_response) is not StatefulFiberSectionResponse:
                _fail(
                    "corotational_recovery_section_response_type_unsupported",
                    f"/members/{member_index}/sections/{ip_index}",
                    "Recovery v1 requires exact StatefulFiberSectionResponse.",
                )
            if (
                section_response.state.state_hash != terminal_section.state_hash
                or section_response.state.canonical_bytes()
                != terminal_section.canonical_bytes()
            ):
                state_bytes_exact = False
            strain_vector = np.asarray(
                [
                    section_response.axial_strain,
                    section_response.curvature_z_per_m,
                ],
                dtype=np.float64,
            )
            b_matrix = member.element.basic_beam.strain_displacement_matrix(xi)
            section_error = max(
                section_error,
                _scaled_linf(
                    b_matrix @ fiber_response.local_displacements,
                    strain_vector,
                ),
            )
            y_values = np.asarray([fiber.y_m for fiber in section.fibers])
            areas = np.asarray([fiber.area_m2 for fiber in section.fibers])
            strains = strain_vector[0] - strain_vector[1] * y_values
            stresses_mpa = np.asarray(section_response.fiber_stresses_mpa)
            fiber_error = max(
                fiber_error,
                _linf(strains - np.asarray(section_response.fiber_strains)),
            )
            forces_kn = stresses_mpa * areas * 1000.0
            manual_resultant = np.asarray(
                [
                    math.fsum(float(value) for value in forces_kn),
                    -math.fsum(
                        float(force * y)
                        for force, y in zip(forces_kn, y_values, strict=True)
                    ),
                ],
                dtype=np.float64,
            )
            section_error = max(
                section_error,
                _scaled_linf(manual_resultant, section_response.resultants),
            )
            manual_local_force += (
                b_matrix.T @ manual_resultant * float(weight) * jacobian
            )
            section_index = len(section_xi)
            section_xi.append(float(xi))
            section_axial.append(float(manual_resultant[0] * 1000.0))
            section_moment.append(float(manual_resultant[1] * 1000.0))
            section_strain.append(float(strain_vector[0]))
            section_curvature.append(float(strain_vector[1]))
            section_order.append(
                {
                    "index": section_index,
                    "member_index": member_index,
                    "member_id": member.member_id,
                    "integration_point_index": ip_index,
                    "xi": float(xi),
                    "section_contract_hash": section.contract_hash,
                }
            )
            for fiber_index, (fiber, strain, stress) in enumerate(
                zip(section.fibers, strains, stresses_mpa, strict=True)
            ):
                fiber_y.append(float(fiber.y_m))
                fiber_area.append(float(fiber.area_m2))
                fiber_strain.append(float(strain))
                fiber_stress_pa.append(float(stress * 1.0e6))
                fiber_order.append(
                    {
                        "index": len(fiber_order),
                        "section_index": section_index,
                        "fiber_index": fiber_index,
                        "fiber_id": fiber.fiber_id,
                        "material_kind": fiber.material_kind,
                    }
                )
            fiber_offsets.append(len(fiber_y))
        section_offsets.append(len(section_xi))
        section_error = max(
            section_error,
            _scaled_linf(manual_local_force, fiber_response.internal_force_local),
        )
        manual_basic_force = member.element.basic_projection_to_local.T @ (
            manual_local_force
        )
        section_error = max(
            section_error,
            _scaled_linf(manual_basic_force, response.basic_forces),
            _scaled_linf(
                response.kinematics.basic_deformation_gradient_global.T
                @ manual_basic_force,
                raw_element_force,
            ),
        )

    scatter_error = _scaled_linf(scatter, replay.internal_loads_global)
    external_scatter_error = _scaled_linf(
        external_scatter, replay.external_loads_global
    )
    free_residual_relative = _linf(replay.residual_kn) / problem.reference_force_scale()
    no_solve_terminal = bool(
        terminal_step.metrics.get("no_solve_contract_pass") is True
        and terminal_step.trial_solution.metrics.get("solver_executed") is False
        and terminal_step.trial_solution.metrics.get("convergence_claim") is False
        and terminal_step.trial_solution.metrics.get("relative_residual") is None
        and terminal_step.trial_solution.metrics.get("residual_gate_passed") is None
        and terminal_step.trial_solution.metrics.get("increment_gate_passed") is None
    )
    terminal_relative_residual = (
        free_residual_relative
        if no_solve_terminal
        else _finite_metric(
            terminal_step.trial_solution.metrics.get("relative_residual")
        )
    )
    if (
        not state_bytes_exact
        or scatter_error > COROTATIONAL_FIBER_FRAME_ENGINEERING_CONSISTENCY_TOLERANCE
        or external_scatter_error
        > COROTATIONAL_FIBER_FRAME_ENGINEERING_CONSISTENCY_TOLERANCE
        or local_global_error
        > COROTATIONAL_FIBER_FRAME_ENGINEERING_CONSISTENCY_TOLERANCE
        or member_feature_error
        > COROTATIONAL_FIBER_FRAME_ENGINEERING_CONSISTENCY_TOLERANCE
        or release_equilibrium_scaled
        > COROTATIONAL_FIBER_FRAME_ENGINEERING_CONSISTENCY_TOLERANCE
        or section_error > COROTATIONAL_FIBER_FRAME_ENGINEERING_CONSISTENCY_TOLERANCE
        or fiber_error > COROTATIONAL_FIBER_FRAME_ENGINEERING_FIBER_STRAIN_TOLERANCE
        or free_residual_relative
        > terminal_step.trial_solution.config.residual_tolerance
        or terminal_relative_residual
        > terminal_step.trial_solution.config.residual_tolerance
    ):
        _fail(
            "corotational_recovery_consistency_gate_failed",
            "/metrics",
            "One or more exact recovery consistency gates did not pass.",
        )

    arrays = _freeze_arrays(
        {
            "node_translation_m": displacement[:, :2],
            "node_rotation_rad": displacement[:, 2],
            "reaction_force_n": reaction.reshape(node_count, 3)[:, :2] * 1000.0,
            "reaction_moment_nm": reaction.reshape(node_count, 3)[:, 2] * 1000.0,
            "member_end_force_n": member_force,
            "member_end_moment_nm": member_moment,
            "section_axial_force_n": section_axial,
            "section_moment_nm": section_moment,
            "section_strain": section_strain,
            "section_curvature_per_m": section_curvature,
            "fiber_strain": fiber_strain,
            "fiber_stress_pa": fiber_stress_pa,
            "member_node_indices": member_nodes,
            "section_offsets": section_offsets,
            "section_xi": section_xi,
            "fiber_offsets": fiber_offsets,
            "fiber_y_m": fiber_y,
            "fiber_area_m2": fiber_area,
        }
    )
    order_hashes = MappingProxyType(
        {
            "node": canonical_hash(
                [
                    {"index": index, "coordinates_m": list(coordinates)}
                    for index, coordinates in enumerate(problem.node_coordinates_m)
                ]
            ),
            "member": canonical_hash(member_order),
            "section": canonical_hash(section_order),
            "fiber": canonical_hash(fiber_order),
        }
    )
    metrics: Mapping[str, float | bool] = MappingProxyType(
        {
            "terminal_assembly_replay_exact": True,
            "terminal_state_bytes_exact": state_bytes_exact,
            "reaction_partition_exact": True,
            "no_fallback_or_regularization": True,
            "scatter_scaled_linf": scatter_error,
            "external_scatter_scaled_linf": external_scatter_error,
            "local_global_scaled_linf": local_global_error,
            "member_feature_scaled_linf": member_feature_error,
            "release_equilibrium_scaled_linf": release_equilibrium_scaled,
            "section_scaled_linf": section_error,
            "fiber_strain_linf": fiber_error,
            "free_residual_relative": free_residual_relative,
            "solver_terminal_relative_residual": terminal_relative_residual,
        }
    )
    if adapter.to_manifest() != source_manifest_before:
        _fail(
            "corotational_recovery_source_mutated",
            "/source_adapter",
            "Recovery changed the retained J1-J5 source.",
        )
    return _RecoveryReplay(
        terminal_assembly_hash=terminal_assembly_hash,
        arrays=arrays,
        order_hashes=order_hashes,
        counts=MappingProxyType(
            {
                "node": node_count,
                "member": member_count,
                "section": len(section_xi),
                "fiber": len(fiber_y),
            }
        ),
        member_ids=tuple(member.member_id for member in problem.members),
        metrics=metrics,
    )


def _terminal_path_target_passed(
    path: StatefulCorotationalFiberFrame2DLoadPathResult,
) -> bool:
    return bool(path.steps and path.final_checkpoint.load_factor == 1.0)


def _freeze_arrays(values: Mapping[str, Any]) -> Mapping[str, np.ndarray]:
    if tuple(values) != _ARRAY_NAMES:
        _fail(
            "corotational_recovery_array_set_invalid",
            "/artifacts",
            "Recovery produced a stale array set or order.",
        )
    return MappingProxyType(
        {
            name: immutable_array(values[name], dtype=_ARRAY_SPECS[name][0])
            for name in _ARRAY_NAMES
        }
    )


def _descriptors(
    arrays: Mapping[str, np.ndarray], order_hashes: Mapping[str, str]
) -> tuple[CorotationalEngineeringArrayDescriptor, ...]:
    rows: list[CorotationalEngineeringArrayDescriptor] = []
    catalog = default_result_quantity_catalog()
    known_quantities = {row.quantity_id for row in catalog.quantities}
    for name in _ARRAY_NAMES:
        dtype, unit, quantities, scope, role = _ARRAY_SPECS[name]
        if not set(quantities).issubset(known_quantities):
            _fail(
                "corotational_recovery_quantity_unknown",
                f"/artifacts/{name}/quantity_ids",
                "Artifact references an unknown quantity contract.",
            )
        array = arrays[name]
        metadata = {
            "name": name,
            "dtype": dtype,
            "shape": list(array.shape),
            "unit": unit,
            "quantity_ids": list(quantities),
            "order_scope": scope,
            "authority_role": role,
            "order_hash": order_hashes[scope],
        }
        rows.append(
            CorotationalEngineeringArrayDescriptor(
                name=name,
                dtype=dtype,
                shape=tuple(int(value) for value in array.shape),
                unit=unit,
                quantity_ids=quantities,
                order_scope=scope,
                authority_role=role,
                order_hash=order_hashes[scope],
                data_hash=array_data_hash(array),
                content_hash=array_content_hash(metadata, array),
            )
        )
    return tuple(rows)


def _result_payload(
    result: CorotationalFiberFrameEngineeringResultIR, *, include_hash: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": result.schema_version,
        "engineering_result_id": result.engineering_result_id,
        "result_kind": result.result_kind,
        "recovery_profile": result.recovery_profile,
        "authority_profile": result.authority_profile,
        "compiler_hash": result.compiler_hash,
        "source_adapter_hash": result.source_adapter_hash,
        "model_content_hash": result.model_content_hash,
        "problem_contract_hash": result.problem_contract_hash,
        "terminal_checkpoint_hash": result.terminal_checkpoint_hash,
        "terminal_assembly_hash": result.terminal_assembly_hash,
        "quantity_catalog_hash": result.quantity_catalog_hash,
        "load_factor": result.load_factor,
        "counts": {
            "node": result.node_count,
            "member": result.member_count,
            "section": result.section_count,
            "fiber": result.fiber_count,
        },
        "member_ids": list(result.member_ids),
        "metrics": dict(result.metrics),
        "authority_axes": dict(result.authority_axes),
        "limitations": list(result.limitations),
        "array_bundle_hash": result.array_bundle_hash,
        "array_descriptors": [row.to_dict() for row in result.descriptors],
    }
    if include_hash:
        payload["engineering_result_hash"] = result.engineering_result_hash
    return payload


def _stable_id(value: Any, path: str) -> str:
    text = str(value or "").strip()
    if not _STABLE_ID.fullmatch(text):
        _fail(
            "corotational_engineering_result_id_invalid",
            path,
            "Expected a stable identifier beginning with an ASCII letter.",
        )
    return text


def _exact_array(left: Any, right: Any) -> bool:
    left_array = np.ascontiguousarray(left)
    right_array = np.ascontiguousarray(right)
    return (
        left_array.dtype == right_array.dtype
        and left_array.shape == right_array.shape
        and left_array.tobytes(order="C") == right_array.tobytes(order="C")
    )


def _linf(values: Any) -> float:
    array = np.asarray(values, dtype=np.float64)
    return float(np.max(np.abs(array))) if array.size else 0.0


def _finite_metric(value: Any) -> float:
    if isinstance(value, bool):
        return math.inf
    try:
        normalized = float(value)
    except (TypeError, ValueError, OverflowError):
        return math.inf
    return normalized if math.isfinite(normalized) else math.inf


def _scaled_linf(left: Any, right: Any) -> float:
    left_array = np.asarray(left, dtype=np.float64)
    right_array = np.asarray(right, dtype=np.float64)
    return _linf(left_array - right_array) / max(
        1.0, _linf(left_array), _linf(right_array)
    )


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    path = (
        resources.files("structural_analysis")
        .joinpath("schemas")
        .joinpath("corotational_fiber_frame_engineering_result_v1.schema.json")
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("Packaged corotational engineering schema must be an object.")
    return _StrictDraft202012Validator(payload)


def _fail(code: str, path: str, message: str) -> NoReturn:
    raise CorotationalFiberFrameEngineeringRecoveryError(code, path, message)


__all__ = [
    "COROTATIONAL_FIBER_FRAME_ENGINEERING_AUTHORITY_PROFILE",
    "COROTATIONAL_FIBER_FRAME_ENGINEERING_RECOVERY_PROFILE",
    "COROTATIONAL_FIBER_FRAME_ENGINEERING_RESULT_KIND",
    "COROTATIONAL_FIBER_FRAME_ENGINEERING_RESULT_SCHEMA_VERSION",
    "COROTATIONAL_FIBER_FRAME_GENERAL_ENGINEERING_AUTHORITY_PROFILE",
    "COROTATIONAL_FIBER_FRAME_GENERAL_ENGINEERING_RESULT_KIND",
    "CorotationalEngineeringArrayDescriptor",
    "CorotationalEngineeringSourceAdapter",
    "CorotationalFiberFrameEngineeringRecoveryError",
    "CorotationalFiberFrameEngineeringResultIR",
    "create_corotational_fiber_frame_engineering_result_ir",
    "validate_corotational_fiber_frame_engineering_result_ir",
    "validate_corotational_fiber_frame_engineering_result_manifest",
]
