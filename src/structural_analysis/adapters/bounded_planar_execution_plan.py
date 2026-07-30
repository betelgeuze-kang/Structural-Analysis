"""Source-bound ExecutionPlan receipt for the bounded nonlinear planar profile."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
import json
import re
from types import MappingProxyType
from typing import Any, Literal, NoReturn

from structural_analysis.assembly.stateful_fiber_frame2d_execution_topology import (
    FIBER_FRAME_PHYSICAL_DOF_COMPONENTS,
    FIBER_FRAME_SOLVER_DOF_COMPONENTS,
    FiberFrame2DTopologyProblem,
    FiberFrameNonlinearExecutionTopologyPlan,
    validate_fiber_frame_execution_topology_against_problem,
)
from structural_analysis.assembly.stateful_fiber_frame2d_physical_equation_scaling import (
    FiberFramePhysicalEquationScalingBinding,
    validate_fiber_frame_physical_equation_scaling_against_problem,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.adapters.bounded_planar_model_ir import (
    BoundedPlanarModelIRAdapter,
    validate_bounded_planar_model_ir_adapter,
)


BOUNDED_PLANAR_EXECUTION_PLAN_SCHEMA_VERSION = (
    "bounded-planar-nonlinear-execution-plan-binding.v1"
)
BOUNDED_PLANAR_EXECUTION_PLAN_AUTHORITY_PROFILE = (
    "bounded_planar_execution_topology_candidate.v1"
)
_ZERO_HASH = "sha256:" + "0" * 64
_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_MANIFEST_KEYS = {
    "schema_version",
    "authority_profile",
    "binding_hash",
    "model_ir_content_hash",
    "model_ir_semantic_hash",
    "model_ir_provenance_hash",
    "model_ir_adapter_hash",
    "canonical_model_checksum",
    "load_pattern_id",
    "problem_contract_hash",
    "topology_plan_hash",
    "topology_hash",
    "entity_mapping_hash",
    "node_ids",
    "member_ids",
    "physical_dof_components",
    "solver_dof_components",
    "physical_dof_count",
    "solver_dof_count",
    "physical_dof_ordering_hash",
    "solver_dof_ordering_hash",
    "solver_coordinate_scaling_hash",
    "equation_scaling_status",
    "equation_scaling_unavailable_reason",
    "physical_equation_scaling_binding_hash",
    "engine_equation_scaling_hash",
    "equation_order_hash",
    "authority_axes",
    "claim_boundary",
}
_AUTHORITY_AXES = {
    "model_ir_input": "schema_validated_bounded_profile",
    "entity_ordering": "source_bound",
    "physical_dof_ordering": "source_bound_node_major_six_dof",
    "solver_dof_mapping": "source_bound_planar_three_dof",
    "nonlinear_topology": "source_bound_candidate",
    "solver_convergence": "not_authoritative",
    "numerical_result": "not_authoritative",
    "engineering_recovery": "not_authoritative",
    "external_vv": "not_attached",
    "engineering_design": "not_authoritative",
    "release_readiness": "not_authoritative",
}


class BoundedPlanarExecutionPlanError(ValueError):
    def __init__(self, code: str, path: str, detail: str) -> None:
        self.code = code
        self.path = path
        self.detail = detail
        super().__init__(f"{code}@{path}: {detail}")


@dataclass(frozen=True)
class BoundedPlanarExecutionPlanBinding:
    schema_version: str
    authority_profile: str
    binding_hash: str
    model_ir_content_hash: str
    model_ir_semantic_hash: str
    model_ir_provenance_hash: str
    model_ir_adapter_hash: str
    canonical_model_checksum: str
    load_pattern_id: str
    problem_contract_hash: str
    topology_plan_hash: str
    topology_hash: str
    entity_mapping_hash: str
    node_ids: tuple[str, ...]
    member_ids: tuple[str, ...]
    physical_dof_components: tuple[str, ...]
    solver_dof_components: tuple[str, ...]
    physical_dof_count: int
    solver_dof_count: int
    physical_dof_ordering_hash: str
    solver_dof_ordering_hash: str
    solver_coordinate_scaling_hash: str
    equation_scaling_status: Literal["available", "unavailable"]
    equation_scaling_unavailable_reason: str | None
    physical_equation_scaling_binding_hash: str | None
    engine_equation_scaling_hash: str | None
    equation_order_hash: str | None
    authority_axes: Mapping[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "authority_profile": self.authority_profile,
            "binding_hash": self.binding_hash,
            "model_ir_content_hash": self.model_ir_content_hash,
            "model_ir_semantic_hash": self.model_ir_semantic_hash,
            "model_ir_provenance_hash": self.model_ir_provenance_hash,
            "model_ir_adapter_hash": self.model_ir_adapter_hash,
            "canonical_model_checksum": self.canonical_model_checksum,
            "load_pattern_id": self.load_pattern_id,
            "problem_contract_hash": self.problem_contract_hash,
            "topology_plan_hash": self.topology_plan_hash,
            "topology_hash": self.topology_hash,
            "entity_mapping_hash": self.entity_mapping_hash,
            "node_ids": list(self.node_ids),
            "member_ids": list(self.member_ids),
            "physical_dof_components": list(self.physical_dof_components),
            "solver_dof_components": list(self.solver_dof_components),
            "physical_dof_count": self.physical_dof_count,
            "solver_dof_count": self.solver_dof_count,
            "physical_dof_ordering_hash": self.physical_dof_ordering_hash,
            "solver_dof_ordering_hash": self.solver_dof_ordering_hash,
            "solver_coordinate_scaling_hash": self.solver_coordinate_scaling_hash,
            "equation_scaling_status": self.equation_scaling_status,
            "equation_scaling_unavailable_reason": (
                self.equation_scaling_unavailable_reason
            ),
            "physical_equation_scaling_binding_hash": (
                self.physical_equation_scaling_binding_hash
            ),
            "engine_equation_scaling_hash": self.engine_equation_scaling_hash,
            "equation_order_hash": self.equation_order_hash,
            "authority_axes": dict(self.authority_axes),
            "claim_boundary": (
                "Source-bound bounded nonlinear topology and DOF-ordering identity "
                "only. This is distinct from linear-static Engine v2 ExecutionPlan "
                "v1 and creates no convergence, result, design, V&V, or release authority."
            ),
        }


def create_bounded_planar_execution_plan_binding(
    *,
    model_ir_adapter: BoundedPlanarModelIRAdapter,
    problem: FiberFrame2DTopologyProblem,
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    equation_scaling: FiberFramePhysicalEquationScalingBinding | None,
) -> BoundedPlanarExecutionPlanBinding:
    adapter = validate_bounded_planar_model_ir_adapter(model_ir_adapter)
    plan = validate_fiber_frame_execution_topology_against_problem(
        problem, topology_plan
    )
    if plan.model_ir_content_hash != adapter.model_ir_content_hash:
        _fail(
            "bounded_planar_execution_plan_model_ir_mismatch",
            "/model_ir_content_hash",
            "Nonlinear topology plan belongs to another ModelIR document.",
        )
    if plan.node_ids != adapter.node_ids or plan.member_ids != adapter.member_ids:
        _fail(
            "bounded_planar_execution_plan_entity_order_mismatch",
            "/entity_order",
            "Topology entity order differs from the ModelIR adapter.",
        )
    if equation_scaling is None:
        scaling_status: Literal["available", "unavailable"] = "unavailable"
        unavailable_reason = "no_free_reference_load"
        physical_scaling_hash = None
        engine_scaling_hash = None
        equation_order_hash = None
    else:
        scaling = validate_fiber_frame_physical_equation_scaling_against_problem(
            problem,
            plan,
            equation_scaling,
        )
        scaling_status = "available"
        unavailable_reason = None
        physical_scaling_hash = scaling.binding_hash
        engine_scaling_hash = scaling.engine_equation_scaling_hash
        equation_order_hash = scaling.equation_order_hash
    physical_ordering_hash = canonical_hash(
        {
            "node_ids": list(plan.node_ids),
            "components": list(FIBER_FRAME_PHYSICAL_DOF_COMPONENTS),
            "index_base": 0,
            "ordering": "node_major",
        }
    )
    solver_ordering_hash = canonical_hash(
        {
            "node_ids": list(plan.node_ids),
            "components": list(FIBER_FRAME_SOLVER_DOF_COMPONENTS),
            "index_base": 0,
            "ordering": "node_major",
            "entity_mapping_hash": plan.entity_mapping_hash,
        }
    )
    provisional = BoundedPlanarExecutionPlanBinding(
        schema_version=BOUNDED_PLANAR_EXECUTION_PLAN_SCHEMA_VERSION,
        authority_profile=BOUNDED_PLANAR_EXECUTION_PLAN_AUTHORITY_PROFILE,
        binding_hash=_ZERO_HASH,
        model_ir_content_hash=adapter.model_ir_content_hash,
        model_ir_semantic_hash=adapter.model_ir_semantic_hash,
        model_ir_provenance_hash=adapter.model_ir_provenance_hash,
        model_ir_adapter_hash=adapter.adapter_hash,
        canonical_model_checksum=adapter.canonical_model_checksum,
        load_pattern_id=adapter.load_pattern_id,
        problem_contract_hash=problem.contract_hash,
        topology_plan_hash=plan.plan_hash,
        topology_hash=plan.topology_hash,
        entity_mapping_hash=plan.entity_mapping_hash,
        node_ids=plan.node_ids,
        member_ids=plan.member_ids,
        physical_dof_components=FIBER_FRAME_PHYSICAL_DOF_COMPONENTS,
        solver_dof_components=FIBER_FRAME_SOLVER_DOF_COMPONENTS,
        physical_dof_count=plan.physical_dof_count,
        solver_dof_count=plan.solver_dof_count,
        physical_dof_ordering_hash=physical_ordering_hash,
        solver_dof_ordering_hash=solver_ordering_hash,
        solver_coordinate_scaling_hash=plan.solver_coordinate_scaling_hash,
        equation_scaling_status=scaling_status,
        equation_scaling_unavailable_reason=unavailable_reason,
        physical_equation_scaling_binding_hash=physical_scaling_hash,
        engine_equation_scaling_hash=engine_scaling_hash,
        equation_order_hash=equation_order_hash,
        authority_axes=MappingProxyType(dict(_AUTHORITY_AXES)),
    )
    binding = replace(
        provisional,
        binding_hash=canonical_hash(
            _binding_payload(provisional, include_binding_hash=False)
        ),
    )
    return validate_bounded_planar_execution_plan_binding(
        binding,
        model_ir_adapter=adapter,
        problem=problem,
        topology_plan=plan,
        equation_scaling=equation_scaling,
    )


def validate_bounded_planar_execution_plan_binding(
    binding: BoundedPlanarExecutionPlanBinding,
    *,
    model_ir_adapter: BoundedPlanarModelIRAdapter | None = None,
    problem: FiberFrame2DTopologyProblem | None = None,
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan | None = None,
    equation_scaling: FiberFramePhysicalEquationScalingBinding | None = None,
) -> BoundedPlanarExecutionPlanBinding:
    if type(binding) is not BoundedPlanarExecutionPlanBinding:
        _fail(
            "bounded_planar_execution_plan_type_invalid",
            "/",
            "Expected a BoundedPlanarExecutionPlanBinding.",
        )
    validate_bounded_planar_execution_plan_manifest(binding.to_dict())
    if not isinstance(binding.authority_axes, MappingProxyType):
        _fail(
            "bounded_planar_execution_plan_authority_mutable",
            "/authority_axes",
            "Authority axes must be immutable.",
        )
    if model_ir_adapter is not None:
        adapter = validate_bounded_planar_model_ir_adapter(model_ir_adapter)
        if (
            binding.model_ir_content_hash != adapter.model_ir_content_hash
            or binding.model_ir_adapter_hash != adapter.adapter_hash
            or binding.canonical_model_checksum != adapter.canonical_model_checksum
        ):
            _fail(
                "bounded_planar_execution_plan_adapter_mismatch",
                "/model_ir_adapter_hash",
                "Execution plan belongs to another ModelIR adapter.",
            )
    if problem is not None and topology_plan is not None:
        plan = validate_fiber_frame_execution_topology_against_problem(
            problem, topology_plan
        )
        if (
            binding.problem_contract_hash != problem.contract_hash
            or binding.topology_plan_hash != plan.plan_hash
            or binding.entity_mapping_hash != plan.entity_mapping_hash
        ):
            _fail(
                "bounded_planar_execution_plan_topology_mismatch",
                "/topology_plan_hash",
                "Execution plan belongs to another nonlinear topology.",
            )
        if equation_scaling is not None:
            scaling = validate_fiber_frame_physical_equation_scaling_against_problem(
                problem, plan, equation_scaling
            )
            if (
                binding.physical_equation_scaling_binding_hash != scaling.binding_hash
                or binding.engine_equation_scaling_hash
                != scaling.engine_equation_scaling_hash
                or binding.equation_order_hash != scaling.equation_order_hash
            ):
                _fail(
                    "bounded_planar_execution_plan_scaling_mismatch",
                    "/physical_equation_scaling_binding_hash",
                    "Execution plan belongs to another EquationScaling binding.",
                )
    return binding


def validate_bounded_planar_execution_plan_manifest(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or set(payload) != _MANIFEST_KEYS:
        _fail(
            "bounded_planar_execution_plan_manifest_fields_invalid",
            "/",
            "Execution-plan receipt has missing or unknown fields.",
        )
    normalized = json.loads(json.dumps(dict(payload), allow_nan=False))
    if normalized["schema_version"] != BOUNDED_PLANAR_EXECUTION_PLAN_SCHEMA_VERSION:
        _fail(
            "bounded_planar_execution_plan_schema_invalid",
            "/schema_version",
            "Unsupported execution-plan binding schema.",
        )
    if (
        normalized["authority_profile"]
        != BOUNDED_PLANAR_EXECUTION_PLAN_AUTHORITY_PROFILE
    ):
        _fail(
            "bounded_planar_execution_plan_authority_profile_invalid",
            "/authority_profile",
            "Unsupported execution-plan authority profile.",
        )
    required_hashes = (
        "binding_hash",
        "model_ir_content_hash",
        "model_ir_semantic_hash",
        "model_ir_provenance_hash",
        "model_ir_adapter_hash",
        "canonical_model_checksum",
        "problem_contract_hash",
        "topology_plan_hash",
        "topology_hash",
        "entity_mapping_hash",
        "physical_dof_ordering_hash",
        "solver_dof_ordering_hash",
        "solver_coordinate_scaling_hash",
    )
    for key in required_hashes:
        if not isinstance(normalized[key], str) or not _HASH_PATTERN.fullmatch(
            normalized[key]
        ):
            _fail(
                "bounded_planar_execution_plan_hash_invalid",
                f"/{key}",
                "Expected a lowercase sha256 hash.",
            )
    if normalized["physical_dof_components"] != list(
        FIBER_FRAME_PHYSICAL_DOF_COMPONENTS
    ) or normalized["solver_dof_components"] != list(FIBER_FRAME_SOLVER_DOF_COMPONENTS):
        _fail(
            "bounded_planar_execution_plan_dof_components_invalid",
            "/physical_dof_components",
            "Execution-plan DOF components differ from the bounded profile.",
        )
    if normalized["physical_dof_count"] != 6 * len(normalized["node_ids"]):
        _fail(
            "bounded_planar_execution_plan_physical_dof_count_invalid",
            "/physical_dof_count",
            "Physical DOF count must equal node_count*6.",
        )
    if normalized["solver_dof_count"] != 3 * len(normalized["node_ids"]):
        _fail(
            "bounded_planar_execution_plan_solver_dof_count_invalid",
            "/solver_dof_count",
            "Solver DOF count must equal node_count*3.",
        )
    if normalized["authority_axes"] != _AUTHORITY_AXES:
        _fail(
            "bounded_planar_execution_plan_authority_axes_invalid",
            "/authority_axes",
            "Execution-plan authority axes changed.",
        )
    status = normalized["equation_scaling_status"]
    optional_hashes = (
        "physical_equation_scaling_binding_hash",
        "engine_equation_scaling_hash",
        "equation_order_hash",
    )
    if status == "available":
        if normalized["equation_scaling_unavailable_reason"] is not None:
            _fail(
                "bounded_planar_execution_plan_scaling_status_invalid",
                "/equation_scaling_unavailable_reason",
                "Available scaling cannot carry an unavailable reason.",
            )
        for key in optional_hashes:
            if not isinstance(normalized[key], str) or not _HASH_PATTERN.fullmatch(
                normalized[key]
            ):
                _fail(
                    "bounded_planar_execution_plan_scaling_hash_invalid",
                    f"/{key}",
                    "Available EquationScaling requires exact hashes.",
                )
    elif status == "unavailable":
        if normalized[
            "equation_scaling_unavailable_reason"
        ] != "no_free_reference_load" or any(
            normalized[key] is not None for key in optional_hashes
        ):
            _fail(
                "bounded_planar_execution_plan_scaling_status_invalid",
                "/equation_scaling_status",
                "Unavailable EquationScaling requires the exact reason and null hashes.",
            )
    else:
        _fail(
            "bounded_planar_execution_plan_scaling_status_invalid",
            "/equation_scaling_status",
            "Unknown EquationScaling availability status.",
        )
    body = dict(normalized)
    claimed = body.pop("binding_hash")
    if claimed != canonical_hash(body):
        _fail(
            "bounded_planar_execution_plan_binding_hash_mismatch",
            "/binding_hash",
            "Execution-plan binding hash is stale.",
        )
    return normalized


def _binding_payload(
    binding: BoundedPlanarExecutionPlanBinding,
    *,
    include_binding_hash: bool,
) -> dict[str, Any]:
    payload = binding.to_dict()
    if not include_binding_hash:
        payload.pop("binding_hash")
    return payload


def _fail(code: str, path: str, detail: str) -> NoReturn:
    raise BoundedPlanarExecutionPlanError(code, path, detail)


__all__ = [
    "BOUNDED_PLANAR_EXECUTION_PLAN_AUTHORITY_PROFILE",
    "BOUNDED_PLANAR_EXECUTION_PLAN_SCHEMA_VERSION",
    "BoundedPlanarExecutionPlanBinding",
    "BoundedPlanarExecutionPlanError",
    "create_bounded_planar_execution_plan_binding",
    "validate_bounded_planar_execution_plan_binding",
    "validate_bounded_planar_execution_plan_manifest",
]
