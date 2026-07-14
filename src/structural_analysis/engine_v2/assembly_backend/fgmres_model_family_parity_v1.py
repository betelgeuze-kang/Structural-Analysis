"""Fail-closed fixed-suite aggregation for exact FGMRES model-case parity.

This layer deliberately has no caller-supplied family label, slot mapping, or
architecture requirement.  It derives a case descriptor from the retained,
validated :class:`ExecutionPlanV2` source buffers and compares that descriptor
only with the package-owned suite below.

The v1 package currently declares target slots but registers no exact golden
slot hashes.  Consequently every valid aggregate is an honest pending receipt.
Adding a real slot later requires package source, schema, fixture, and hardware
evidence changes; a caller cannot promote an arbitrary case into the suite.

Serialized receipts are structural, unsigned observations.  Only the result
validator can replay the retained process-local case authorities, and even a
fully populated future v1 result remains non-promoting.
"""

from __future__ import annotations

from collections import Counter
import copy
from dataclasses import dataclass, field as dataclass_field, replace
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any, Literal, NoReturn

from jsonschema import Draft202012Validator
import numpy as np

from structural_analysis.engine_v2.backends.hip.device_identity_v1 import (
    normalize_hip_gcn_architecture_v1,
)
from structural_analysis.engine_v2.buffers import (
    SolverModelBuffers,
    validate_solver_model_buffers,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (
    ExecutionPlanV2,
    validate_execution_plan_v2,
)

from .fgmres_model_case_parity_v1 import (
    HipFgmresModelCaseParityReceiptV1,
    HipFgmresModelCaseParityResultV1,
    validate_hip_fgmres_model_case_parity_receipt_v1,
    validate_hip_fgmres_model_case_parity_result_v1,
)


HIP_FGMRES_MODEL_FAMILY_PARITY_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-model-family-parity.v1"
)
HIP_FGMRES_MODEL_FAMILY_PARITY_CAPABILITY_PROFILE_V1 = (
    "phase0_fixed_suite_frame_truss_fgmres_cpu_hip_parity_coverage"
)
HIP_FGMRES_MODEL_FAMILY_PARITY_EVIDENCE_SCOPE_V1 = (
    "process_local_fixed_suite_coverage_aggregate_unsigned_non_promoting"
)
HIP_FGMRES_MODEL_FAMILY_PARITY_SUITE_ID_V1 = (
    "phase0_execution_plan_v2_linear_frame_truss_fgmres_fixed_suite.v1"
)
HIP_FGMRES_MODEL_FAMILY_PARITY_SUITE_SCOPE_V1 = (
    "execution_plan_v2_linear_frame_truss_zero_offset_release_prescribed_fgmres_only"
)
HIP_FGMRES_MODEL_FAMILY_REQUIRED_ARCHITECTURE_BASES_V1 = (
    "gfx1030",
    "gfx1100",
)
HIP_FGMRES_MODEL_FAMILY_REQUIRED_SLOT_IDS_V1 = (
    "frame_single_axial",
    "frame_single_weak_axis_bending",
    "frame_single_strong_axis_bending",
    "frame_single_torsion",
    "frame_single_rotated_local_axis_bending",
    "frame_serial_later_column",
    "truss_single_axial",
    "recurrence_initial_or_early_terminal",
    "recurrence_later_restart_partial_final_cycle",
    "recurrence_exact_full_final_cycle_guard",
)

_ZERO_HASH = "sha256:" + "0" * 64
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ARCH_RE = re.compile(r"^gfx[0-9a-f]+(?::[a-z][a-z0-9_]*[+-])*$")
_UUID_RE = re.compile(r"^[0-9a-f]{32}$")
_PCI_BDF_RE = re.compile(r"^[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]$")
_SCHEMA_RESOURCE = "hip_fgmres_model_family_parity_v1.schema.json"
_METADATA_BUFFER_NAMES = (
    "node_coordinates_m",
    "element_connectivity",
    "element_type",
    "element_formulation_code",
    "element_material_index",
    "element_section_index",
    "material_law_code",
    "section_family_code",
    "element_local_axis_rotation_rad",
    "element_offsets_m",
    "element_release_mask",
    "support_mask",
    "prescribed_values_si",
    "load_vector_si",
)


class HipFgmresModelFamilyParityV1Error(ValueError):
    """Stable fail-closed model-family coverage error."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = message or code
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class _FixedSuiteSlotV1:
    slot_id: str
    group: Literal["model_semantics", "recurrence_semantics"]
    description: str
    expected_descriptor_hash: str | None = None
    expected_model_ir_content_hash: str | None = None
    expected_execution_plan_hash: str | None = None
    expected_policy_hash: str | None = None
    expected_cpu_result_hash: str | None = None
    expected_cpu_status: str | None = None
    expected_cpu_termination_code: str | None = None

    @property
    def registered(self) -> bool:
        values = (
            self.expected_descriptor_hash,
            self.expected_model_ir_content_hash,
            self.expected_execution_plan_hash,
            self.expected_policy_hash,
            self.expected_cpu_result_hash,
            self.expected_cpu_status,
            self.expected_cpu_termination_code,
        )
        present = tuple(value is not None for value in values)
        if any(present) and not all(present):
            _fail(
                "hip_fgmres_model_family_slot_registration_partial",
                f"/suite/slots/{self.slot_id}",
            )
        return all(present)

    def to_manifest_row(self) -> dict[str, Any]:
        return {
            "slot_id": self.slot_id,
            "group": self.group,
            "description": self.description,
            "registration_status": (
                "exact_hashes_registered" if self.registered else "unregistered"
            ),
            "expected_descriptor_hash": self.expected_descriptor_hash,
            "expected_model_ir_content_hash": self.expected_model_ir_content_hash,
            "expected_execution_plan_hash": self.expected_execution_plan_hash,
            "expected_policy_hash": self.expected_policy_hash,
            "expected_cpu_result_hash": self.expected_cpu_result_hash,
            "expected_cpu_status": self.expected_cpu_status,
            "expected_cpu_termination_code": self.expected_cpu_termination_code,
        }


_FIXED_SUITE_SLOTS_V1 = (
    _FixedSuiteSlotV1(
        "frame_single_axial",
        "model_semantics",
        "single Euler-Bernoulli frame under axial excitation",
    ),
    _FixedSuiteSlotV1(
        "frame_single_weak_axis_bending",
        "model_semantics",
        "single Euler-Bernoulli frame under weak-axis bending excitation",
    ),
    _FixedSuiteSlotV1(
        "frame_single_strong_axis_bending",
        "model_semantics",
        "single Euler-Bernoulli frame under strong-axis bending excitation",
    ),
    _FixedSuiteSlotV1(
        "frame_single_torsion",
        "model_semantics",
        "single Euler-Bernoulli frame under torsional excitation",
    ),
    _FixedSuiteSlotV1(
        "frame_single_rotated_local_axis_bending",
        "model_semantics",
        "single frame with nonzero local-axis roll under bending excitation",
    ),
    _FixedSuiteSlotV1(
        "frame_serial_later_column",
        "model_semantics",
        "serial multi-element frame exercising a later Arnoldi column",
    ),
    _FixedSuiteSlotV1(
        "truss_single_axial",
        "model_semantics",
        "single linear 3D truss under axial excitation",
    ),
    _FixedSuiteSlotV1(
        "recurrence_initial_or_early_terminal",
        "recurrence_semantics",
        "initial-residual or early-terminal recurrence path",
    ),
    _FixedSuiteSlotV1(
        "recurrence_later_restart_partial_final_cycle",
        "recurrence_semantics",
        "active later restart with a partial final recurrence cycle",
    ),
    _FixedSuiteSlotV1(
        "recurrence_exact_full_final_cycle_guard",
        "recurrence_semantics",
        "exact full final cycle with active final-guard handoff",
    ),
)


@dataclass(frozen=True, slots=True)
class HipFgmresModelFamilyElementSignatureV1:
    element_type_code: int
    formulation_code: int
    material_law_code: int
    section_family_code: int
    element_count: int

    def to_dict(self) -> dict[str, int]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresModelFamilyBufferBindingV1:
    name: str
    content_hash: str

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "content_hash": self.content_hash}


@dataclass(frozen=True, slots=True)
class HipFgmresModelFamilyCaseDescriptorV1:
    descriptor_version: Literal["authoritative_execution_plan_metadata.v1"]
    execution_plan_schema_version: str
    execution_plan_capability_profile: str
    execution_plan_hash: str
    model_ir_content_hash: str
    solver_buffer_schema_version: str
    solver_numeric_buffer_hash: str
    solver_entity_mapping_hash: str
    solver_artifact_hash: str
    operator_version: str
    source_element_operator_version: str
    operator_hash: str
    numeric_snapshot_hash: str
    symbolic_reuse_hash: str
    partition_hash: str
    node_count: int
    element_count: int
    global_dof_count: int
    free_dof_count: int
    reduced_csr_nnz: int
    element_signatures: tuple[HipFgmresModelFamilyElementSignatureV1, ...]
    metadata_buffer_bindings: tuple[HipFgmresModelFamilyBufferBindingV1, ...]
    load_nonzero_component_mask: tuple[bool, bool, bool, bool, bool, bool]
    support_component_mask: tuple[bool, bool, bool, bool, bool, bool]
    nonzero_local_axis_roll_count: int
    nonzero_offset_component_count: int
    released_dof_count: int
    descriptor_hash: str

    def to_dict(self) -> dict[str, Any]:
        return _descriptor_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class HipFgmresModelFamilySuiteSummaryV1:
    suite_id: str
    suite_scope: str
    suite_hash: str
    required_architecture_bases: tuple[str, str]
    required_slot_ids: tuple[str, ...]
    registered_slot_ids: tuple[str, ...]
    caller_override_allowed: Literal[False] = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite_id": self.suite_id,
            "suite_scope": self.suite_scope,
            "suite_hash": self.suite_hash,
            "required_architecture_bases": list(self.required_architecture_bases),
            "required_slot_ids": list(self.required_slot_ids),
            "registered_slot_ids": list(self.registered_slot_ids),
            "caller_override_allowed": self.caller_override_allowed,
        }


@dataclass(frozen=True, slots=True)
class HipFgmresModelFamilyObservedCaseV1:
    case_id: str
    case_receipt_hash: str
    model_ir_content_hash: str
    execution_plan_hash: str
    policy_hash: str
    cpu_result_hash: str
    cpu_status: str
    cpu_termination_code: str
    runtime_architecture_base: str
    compiled_architecture: str
    device_ordinal: int
    device_identity_receipt_hash: str
    device_uuid_bytes_hex: str
    device_pci_bdf: str
    registration_status: Literal["exact_slot_registered", "unregistered_case"]
    slot_id: str | None
    logical_case_key: str | None
    matrix_cell_id: str | None
    descriptor: HipFgmresModelFamilyCaseDescriptorV1

    def to_dict(self) -> dict[str, Any]:
        return {
            name: (
                self.descriptor.to_dict()
                if name == "descriptor"
                else getattr(self, name)
            )
            for name in self.__dataclass_fields__
        }


@dataclass(frozen=True, slots=True)
class HipFgmresModelFamilyMatrixCellV1:
    slot_id: str
    architecture_base: str

    def to_dict(self) -> dict[str, str]:
        return {
            "slot_id": self.slot_id,
            "architecture_base": self.architecture_base,
        }


@dataclass(frozen=True, slots=True)
class HipFgmresModelFamilyCoverageV1:
    validated_input_case_count: int
    registered_input_case_count: int
    unregistered_input_case_count: int
    required_slot_count: int
    registered_slot_definition_count: int
    required_architecture_count: int
    expected_matrix_cell_count: int
    covered_matrix_cell_count: int
    observed_architecture_bases: tuple[str, ...]
    completed_architecture_bases: tuple[str, ...]
    incomplete_architecture_bases: tuple[str, ...]
    unregistered_slot_definition_ids: tuple[str, ...]
    covered_cells: tuple[HipFgmresModelFamilyMatrixCellV1, ...]
    missing_cells: tuple[HipFgmresModelFamilyMatrixCellV1, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "validated_input_case_count": self.validated_input_case_count,
            "registered_input_case_count": self.registered_input_case_count,
            "unregistered_input_case_count": self.unregistered_input_case_count,
            "required_slot_count": self.required_slot_count,
            "registered_slot_definition_count": (self.registered_slot_definition_count),
            "required_architecture_count": self.required_architecture_count,
            "expected_matrix_cell_count": self.expected_matrix_cell_count,
            "covered_matrix_cell_count": self.covered_matrix_cell_count,
            "observed_architecture_bases": list(self.observed_architecture_bases),
            "completed_architecture_bases": list(self.completed_architecture_bases),
            "incomplete_architecture_bases": list(self.incomplete_architecture_bases),
            "unregistered_slot_definition_ids": list(
                self.unregistered_slot_definition_ids
            ),
            "covered_cells": [row.to_dict() for row in self.covered_cells],
            "missing_cells": [row.to_dict() for row in self.missing_cells],
        }


@dataclass(frozen=True, slots=True)
class HipFgmresModelFamilyClaimsV1:
    fixed_package_suite_manifest_bound: Literal[True] = True
    authoritative_execution_plan_metadata_classification: Literal[True] = True
    caller_supplied_family_or_case_labels_used: Literal[False] = False
    caller_supplied_required_architectures_used: Literal[False] = False
    all_submitted_exact_case_results_replayed: Literal[True] = True
    architecture_key_is_normalized_runtime_base: Literal[True] = True
    duplicate_logical_slot_architecture_cells_rejected: Literal[True] = True
    serialized_receipt_authoritative: Literal[False] = False
    unsigned_external_evidence_counted: Literal[False] = False
    fixed_suite_slot_registration_complete: bool = False
    fixed_suite_matrix_complete: bool = False
    full_model_family_parity_verified: bool = False
    multi_architecture_parity_verified: bool = False
    same_process_actual_two_isa_verified: bool = False
    iteration_host_copy_zero_proven: Literal[False] = False
    solution_ready: Literal[False] = False
    result_ir_ready: Literal[False] = False
    performance_or_speedup_proven: Literal[False] = False
    signed_evidence: Literal[False] = False
    commercial_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


_CoverageStatus = Literal[
    "pending_model_cases",
    "pending_external_architecture",
    "pending_model_cases_and_external_architecture",
    "fixed_suite_multiarchitecture_parity_verified_non_promoting",
]


@dataclass(frozen=True, slots=True)
class HipFgmresModelFamilyParityReceiptV1:
    schema_version: str
    capability_profile: str
    status: _CoverageStatus
    evidence_scope: str
    backend_scope: Literal["hip"]
    promotion_eligible: Literal[False]
    suite: HipFgmresModelFamilySuiteSummaryV1
    observed_cases: tuple[HipFgmresModelFamilyObservedCaseV1, ...]
    coverage: HipFgmresModelFamilyCoverageV1
    claims: HipFgmresModelFamilyClaimsV1
    receipt_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_model_family_parity_receipt_v1(self)
        return _receipt_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class HipFgmresModelFamilyParityResultV1:
    receipt: HipFgmresModelFamilyParityReceiptV1
    _case_results: tuple[HipFgmresModelCaseParityResultV1, ...] = dataclass_field(
        repr=False,
        compare=False,
    )
    _source_execution_plans: tuple[ExecutionPlanV2, ...] = dataclass_field(
        repr=False,
        compare=False,
    )
    _descriptor_hashes: tuple[str, ...] = dataclass_field(
        repr=False,
        compare=False,
    )

    def to_manifest(self) -> dict[str, Any]:
        validate_hip_fgmres_model_family_parity_result_v1(self)
        return self.receipt.to_dict()


def derive_hip_fgmres_model_family_case_descriptor_v1(
    case_result: HipFgmresModelCaseParityResultV1,
) -> HipFgmresModelFamilyCaseDescriptorV1:
    """Replay one exact case authority and derive only retained-plan metadata."""

    if type(case_result) is not HipFgmresModelCaseParityResultV1:
        _fail("hip_fgmres_model_family_case_result_type_invalid", "/case_result")
    validate_hip_fgmres_model_case_parity_result_v1(case_result)
    descriptor = _derive_descriptor(case_result._source_execution_plan)
    validate_hip_fgmres_model_case_parity_result_v1(case_result)
    if descriptor != _derive_descriptor(case_result._source_execution_plan):
        _fail("hip_fgmres_model_family_descriptor_source_changed", "/case_result")
    return descriptor


def attest_hip_fgmres_model_family_coverage_v1(
    case_results: tuple[HipFgmresModelCaseParityResultV1, ...],
) -> HipFgmresModelFamilyParityResultV1:
    """Aggregate exact live cases against the package-owned fixed suite."""

    receipt, plans, descriptor_hashes = _evaluate_case_results(case_results)
    result = HipFgmresModelFamilyParityResultV1(
        receipt=receipt,
        _case_results=case_results,
        _source_execution_plans=plans,
        _descriptor_hashes=descriptor_hashes,
    )
    return validate_hip_fgmres_model_family_parity_result_v1(
        result,
        expected_case_results=case_results,
    )


def validate_hip_fgmres_model_family_parity_receipt_v1(
    receipt: HipFgmresModelFamilyParityReceiptV1,
) -> HipFgmresModelFamilyParityReceiptV1:
    """Validate serialized consistency without asserting live provenance."""

    if type(receipt) is not HipFgmresModelFamilyParityReceiptV1:
        _fail("hip_fgmres_model_family_receipt_type_invalid", "/")
    if type(receipt.suite) is not HipFgmresModelFamilySuiteSummaryV1:
        _fail("hip_fgmres_model_family_nested_type_invalid", "/suite")
    if type(receipt.coverage) is not HipFgmresModelFamilyCoverageV1:
        _fail("hip_fgmres_model_family_nested_type_invalid", "/coverage")
    if type(receipt.claims) is not HipFgmresModelFamilyClaimsV1:
        _fail("hip_fgmres_model_family_nested_type_invalid", "/claims")
    if type(receipt.observed_cases) is not tuple or any(
        type(row) is not HipFgmresModelFamilyObservedCaseV1
        for row in receipt.observed_cases
    ):
        _fail("hip_fgmres_model_family_observed_cases_type_invalid", "/observed_cases")
    _validate_exact_nested_types(receipt)

    payload = _receipt_payload(receipt, include_hash=True)
    errors = sorted(
        _schema_validator().iter_errors(payload),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        _fail("hip_fgmres_model_family_schema_invalid", path, error.message)

    suite = _suite_summary()
    if receipt.suite != suite:
        _fail("hip_fgmres_model_family_suite_mismatch", "/suite")
    for index, observation in enumerate(receipt.observed_cases):
        _validate_observation(observation, f"/observed_cases/{index}")
    _validate_observation_set(receipt.observed_cases)
    expected = _build_receipt(receipt.observed_cases)
    if replace(receipt, receipt_hash=_ZERO_HASH) != replace(
        expected, receipt_hash=_ZERO_HASH
    ):
        _fail("hip_fgmres_model_family_semantics_invalid", "/")
    expected_hash = canonical_hash(_receipt_payload(receipt, include_hash=False))
    if (
        _HASH_RE.fullmatch(receipt.receipt_hash) is None
        or receipt.receipt_hash != expected_hash
    ):
        _fail("hip_fgmres_model_family_receipt_hash_invalid", "/receipt_hash")
    return receipt


def validate_hip_fgmres_model_family_parity_result_v1(
    result: HipFgmresModelFamilyParityResultV1,
    *,
    expected_case_results: tuple[HipFgmresModelCaseParityResultV1, ...] | None = None,
) -> HipFgmresModelFamilyParityResultV1:
    """Replay every retained exact case and the fixed-suite aggregation."""

    if type(result) is not HipFgmresModelFamilyParityResultV1:
        _fail("hip_fgmres_model_family_result_type_invalid", "/")
    validate_hip_fgmres_model_family_parity_receipt_v1(result.receipt)
    if type(result._case_results) is not tuple or any(
        type(row) is not HipFgmresModelCaseParityResultV1
        for row in result._case_results
    ):
        _fail("hip_fgmres_model_family_result_sources_invalid", "/source/cases")
    if expected_case_results is not None:
        if type(expected_case_results) is not tuple or len(
            expected_case_results
        ) != len(result._case_results):
            _fail("hip_fgmres_model_family_expected_sources_invalid", "/expected")
        if any(
            actual is not expected
            for actual, expected in zip(
                result._case_results, expected_case_results, strict=True
            )
        ):
            _fail("hip_fgmres_model_family_expected_source_mismatch", "/expected")
    replayed, plans, descriptor_hashes = _evaluate_case_results(result._case_results)
    if type(result._source_execution_plans) is not tuple or len(plans) != len(
        result._source_execution_plans
    ):
        _fail("hip_fgmres_model_family_result_plans_invalid", "/source/plans")
    if any(
        actual is not expected
        for actual, expected in zip(plans, result._source_execution_plans, strict=True)
    ):
        _fail("hip_fgmres_model_family_plan_identity_changed", "/source/plans")
    if descriptor_hashes != result._descriptor_hashes:
        _fail("hip_fgmres_model_family_descriptor_changed", "/source/descriptors")
    if replayed != result.receipt:
        _fail("hip_fgmres_model_family_result_replay_mismatch", "/")
    return result


def _evaluate_case_results(
    case_results: tuple[HipFgmresModelCaseParityResultV1, ...],
) -> tuple[
    HipFgmresModelFamilyParityReceiptV1,
    tuple[ExecutionPlanV2, ...],
    tuple[str, ...],
]:
    if type(case_results) is not tuple:
        _fail("hip_fgmres_model_family_case_results_container_invalid", "/case_results")
    if any(type(row) is not HipFgmresModelCaseParityResultV1 for row in case_results):
        _fail("hip_fgmres_model_family_case_result_type_invalid", "/case_results")

    observations: list[HipFgmresModelFamilyObservedCaseV1] = []
    plans: list[ExecutionPlanV2] = []
    descriptor_hashes: list[str] = []
    seen_input_keys: set[tuple[str, str]] = set()
    seen_cells: set[tuple[str, str]] = set()
    for index, case_result in enumerate(case_results):
        path = f"/case_results/{index}"
        validate_hip_fgmres_model_case_parity_result_v1(case_result)
        receipt_snapshot = copy.deepcopy(case_result.receipt)
        validate_hip_fgmres_model_case_parity_receipt_v1(receipt_snapshot)
        cpu_result = case_result._cpu_result
        cpu_status_snapshot = getattr(cpu_result, "status", None)
        cpu_termination_code_snapshot = getattr(cpu_result, "termination_code", None)
        plan = case_result._source_execution_plan
        if type(plan) is not ExecutionPlanV2:
            _fail("hip_fgmres_model_family_execution_plan_type_invalid", f"{path}/plan")
        descriptor = _derive_descriptor(plan)
        observation = _observe_case(
            receipt_snapshot,
            descriptor,
            cpu_status=cpu_status_snapshot,
            cpu_termination_code=cpu_termination_code_snapshot,
            path=path,
        )
        input_key = (observation.case_id, observation.runtime_architecture_base)
        if input_key in seen_input_keys:
            _fail("hip_fgmres_model_family_duplicate_input_case", path)
        seen_input_keys.add(input_key)
        if observation.slot_id is not None:
            cell_key = (observation.slot_id, observation.runtime_architecture_base)
            if cell_key in seen_cells:
                _fail("hip_fgmres_model_family_duplicate_matrix_cell", path)
            seen_cells.add(cell_key)

        validate_hip_fgmres_model_case_parity_result_v1(case_result)
        if (
            case_result.receipt != receipt_snapshot
            or case_result._source_execution_plan is not plan
            or case_result._cpu_result is not cpu_result
            or getattr(case_result._cpu_result, "status", None) != cpu_status_snapshot
            or getattr(case_result._cpu_result, "termination_code", None)
            != cpu_termination_code_snapshot
            or _derive_descriptor(plan) != descriptor
        ):
            _fail("hip_fgmres_model_family_case_source_changed", path)
        observations.append(observation)
        plans.append(plan)
        descriptor_hashes.append(descriptor.descriptor_hash)

    ordered = tuple(
        sorted(
            observations,
            key=lambda row: (
                HIP_FGMRES_MODEL_FAMILY_REQUIRED_ARCHITECTURE_BASES_V1.index(
                    row.runtime_architecture_base
                ),
                row.slot_id or "~unregistered",
                row.case_id,
            ),
        )
    )
    receipt = _build_receipt(ordered)
    return (
        validate_hip_fgmres_model_family_parity_receipt_v1(receipt),
        tuple(plans),
        tuple(descriptor_hashes),
    )


def _observe_case(
    receipt: HipFgmresModelCaseParityReceiptV1,
    descriptor: HipFgmresModelFamilyCaseDescriptorV1,
    *,
    cpu_status: str,
    cpu_termination_code: str,
    path: str,
) -> HipFgmresModelFamilyObservedCaseV1:
    bindings = receipt.bindings
    architecture = normalize_hip_gcn_architecture_v1(bindings.runtime_architecture_base)
    compiled = normalize_hip_gcn_architecture_v1(bindings.compiled_architecture)
    if (
        architecture.raw != architecture.base
        or architecture.base != bindings.runtime_architecture_base
        or compiled.base != architecture.base
    ):
        _fail(
            "hip_fgmres_model_family_architecture_binding_invalid",
            f"{path}/architecture",
        )
    if architecture.base not in HIP_FGMRES_MODEL_FAMILY_REQUIRED_ARCHITECTURE_BASES_V1:
        _fail(
            "hip_fgmres_model_family_architecture_not_in_fixed_suite",
            f"{path}/architecture",
        )
    if (
        bindings.execution_plan_hash != descriptor.execution_plan_hash
        or bindings.model_ir_content_hash != descriptor.model_ir_content_hash
        or bindings.operator_hash != descriptor.operator_hash
        or bindings.numeric_snapshot_hash != descriptor.numeric_snapshot_hash
        or bindings.symbolic_reuse_hash != descriptor.symbolic_reuse_hash
        or bindings.partition_hash != descriptor.partition_hash
    ):
        _fail("hip_fgmres_model_family_case_plan_binding_mismatch", f"{path}/bindings")
    if type(cpu_status) is not str or not cpu_status:
        _fail("hip_fgmres_model_family_cpu_status_invalid", f"{path}/cpu/status")
    if type(cpu_termination_code) is not str or not cpu_termination_code:
        _fail(
            "hip_fgmres_model_family_cpu_termination_code_invalid",
            f"{path}/cpu/termination_code",
        )

    matches = tuple(
        slot
        for slot in _validated_fixed_slots()
        if _slot_matches(
            slot,
            descriptor=descriptor,
            policy_hash=bindings.policy_hash,
            cpu_result_hash=bindings.cpu_result_hash,
            cpu_status=cpu_status,
            cpu_termination_code=cpu_termination_code,
        )
    )
    if len(matches) > 1:
        _fail("hip_fgmres_model_family_case_slot_ambiguous", f"{path}/classification")
    slot = matches[0] if matches else None
    logical_case_key = None
    matrix_cell_id = None
    if slot is not None:
        logical_case_key = canonical_hash(
            {
                "suite_hash": _suite_summary().suite_hash,
                "slot_id": slot.slot_id,
                "descriptor_hash": descriptor.descriptor_hash,
                "execution_plan_hash": bindings.execution_plan_hash,
                "policy_hash": bindings.policy_hash,
                "cpu_result_hash": bindings.cpu_result_hash,
            }
        )
        matrix_cell_id = canonical_hash(
            {
                "logical_case_key": logical_case_key,
                "runtime_architecture_base": architecture.base,
                "case_receipt_hash": receipt.receipt_hash,
                "device_identity_receipt_hash": (bindings.device_identity_receipt_hash),
            }
        )
    return HipFgmresModelFamilyObservedCaseV1(
        case_id=receipt.case_id,
        case_receipt_hash=receipt.receipt_hash,
        model_ir_content_hash=bindings.model_ir_content_hash,
        execution_plan_hash=bindings.execution_plan_hash,
        policy_hash=bindings.policy_hash,
        cpu_result_hash=bindings.cpu_result_hash,
        cpu_status=cpu_status,
        cpu_termination_code=cpu_termination_code,
        runtime_architecture_base=architecture.base,
        compiled_architecture=compiled.normalized,
        device_ordinal=bindings.device_ordinal,
        device_identity_receipt_hash=bindings.device_identity_receipt_hash,
        device_uuid_bytes_hex=bindings.device_uuid_bytes_hex,
        device_pci_bdf=bindings.device_pci_bdf,
        registration_status=(
            "exact_slot_registered" if slot is not None else "unregistered_case"
        ),
        slot_id=slot.slot_id if slot is not None else None,
        logical_case_key=logical_case_key,
        matrix_cell_id=matrix_cell_id,
        descriptor=descriptor,
    )


def _derive_descriptor(plan: ExecutionPlanV2) -> HipFgmresModelFamilyCaseDescriptorV1:
    if type(plan) is not ExecutionPlanV2:
        _fail("hip_fgmres_model_family_execution_plan_type_invalid", "/plan")
    validate_execution_plan_v2(plan)
    buffers = plan._source_buffers
    if type(buffers) is not SolverModelBuffers:
        _fail(
            "hip_fgmres_model_family_source_buffers_type_invalid",
            "/plan/source_buffers",
        )
    validate_solver_model_buffers(buffers)

    element_types = buffers.array("element_type")
    formulations = buffers.array("element_formulation_code")
    material_indices = buffers.array("element_material_index")
    section_indices = buffers.array("element_section_index")
    material_laws = buffers.array("material_law_code")
    section_families = buffers.array("section_family_code")
    signatures = Counter(
        (
            int(element_types[index]),
            int(formulations[index]),
            int(material_laws[int(material_indices[index])]),
            int(section_families[int(section_indices[index])]),
        )
        for index in range(plan.element_count)
    )
    element_signatures = tuple(
        HipFgmresModelFamilyElementSignatureV1(*signature, count)
        for signature, count in sorted(signatures.items())
    )
    descriptor_by_name = {row.name: row for row in buffers.descriptors}
    if set(_METADATA_BUFFER_NAMES) - set(descriptor_by_name):
        _fail("hip_fgmres_model_family_metadata_buffer_missing", "/plan/source_buffers")
    metadata_bindings = tuple(
        HipFgmresModelFamilyBufferBindingV1(
            name=name,
            content_hash=descriptor_by_name[name].content_hash,
        )
        for name in _METADATA_BUFFER_NAMES
    )

    load = buffers.array("load_vector_si")
    support = buffers.array("support_mask")
    if (
        load.ndim != 2
        or support.ndim != 2
        or load.shape[1] != 6
        or support.shape[1] != 6
    ):
        _fail("hip_fgmres_model_family_component_shape_invalid", "/plan/source_buffers")
    load_mask = tuple(bool(value) for value in np.any(load != 0.0, axis=0))
    support_mask = tuple(bool(value) for value in np.any(support != 0, axis=0))
    draft = HipFgmresModelFamilyCaseDescriptorV1(
        descriptor_version="authoritative_execution_plan_metadata.v1",
        execution_plan_schema_version=plan.schema_version,
        execution_plan_capability_profile=plan.capability_profile,
        execution_plan_hash=plan.plan_hash,
        model_ir_content_hash=plan.model_ir_content_hash,
        solver_buffer_schema_version=plan.solver_buffer_schema_version,
        solver_numeric_buffer_hash=plan.solver_numeric_buffer_hash,
        solver_entity_mapping_hash=plan.solver_entity_mapping_hash,
        solver_artifact_hash=plan.solver_artifact_hash,
        operator_version=plan.operator_version,
        source_element_operator_version=plan.source_element_operator_version,
        operator_hash=plan.operator_hash,
        numeric_snapshot_hash=plan.numeric_snapshot_hash,
        symbolic_reuse_hash=plan.symbolic_reuse_hash,
        partition_hash=plan.partition_hash,
        node_count=plan.node_count,
        element_count=plan.element_count,
        global_dof_count=plan.dof_count,
        free_dof_count=int(plan.array("free_dofs").size),
        reduced_csr_nnz=int(plan.array("reduced_csr_column_indices").size),
        element_signatures=element_signatures,
        metadata_buffer_bindings=metadata_bindings,
        load_nonzero_component_mask=load_mask,  # type: ignore[arg-type]
        support_component_mask=support_mask,  # type: ignore[arg-type]
        nonzero_local_axis_roll_count=int(
            np.count_nonzero(buffers.array("element_local_axis_rotation_rad"))
        ),
        nonzero_offset_component_count=int(
            np.count_nonzero(buffers.array("element_offsets_m"))
        ),
        released_dof_count=int(np.count_nonzero(buffers.array("element_release_mask"))),
        descriptor_hash=_ZERO_HASH,
    )
    descriptor = replace(
        draft,
        descriptor_hash=canonical_hash(_descriptor_payload(draft, include_hash=False)),
    )
    _validate_descriptor(descriptor, "/descriptor")
    validate_execution_plan_v2(plan)
    return descriptor


def _slot_matches(
    slot: _FixedSuiteSlotV1,
    *,
    descriptor: HipFgmresModelFamilyCaseDescriptorV1,
    policy_hash: str,
    cpu_result_hash: str,
    cpu_status: str,
    cpu_termination_code: str,
) -> bool:
    return slot.registered and (
        slot.expected_descriptor_hash == descriptor.descriptor_hash
        and slot.expected_model_ir_content_hash == descriptor.model_ir_content_hash
        and slot.expected_execution_plan_hash == descriptor.execution_plan_hash
        and slot.expected_policy_hash == policy_hash
        and slot.expected_cpu_result_hash == cpu_result_hash
        and slot.expected_cpu_status == cpu_status
        and slot.expected_cpu_termination_code == cpu_termination_code
    )


def _build_receipt(
    observations: tuple[HipFgmresModelFamilyObservedCaseV1, ...],
) -> HipFgmresModelFamilyParityReceiptV1:
    suite = _suite_summary()
    coverage = _coverage(observations)
    claims = _claims(coverage)
    primary_complete = (
        HIP_FGMRES_MODEL_FAMILY_REQUIRED_ARCHITECTURE_BASES_V1[0]
        in coverage.completed_architecture_bases
    )
    external_complete = all(
        architecture in coverage.completed_architecture_bases
        for architecture in HIP_FGMRES_MODEL_FAMILY_REQUIRED_ARCHITECTURE_BASES_V1[1:]
    )
    model_pending = not primary_complete
    external_pending = not external_complete
    if model_pending and external_pending:
        status: _CoverageStatus = "pending_model_cases_and_external_architecture"
    elif model_pending:
        status = "pending_model_cases"
    elif external_pending:
        status = "pending_external_architecture"
    else:
        status = "fixed_suite_multiarchitecture_parity_verified_non_promoting"
    draft = HipFgmresModelFamilyParityReceiptV1(
        schema_version=HIP_FGMRES_MODEL_FAMILY_PARITY_SCHEMA_VERSION_V1,
        capability_profile=HIP_FGMRES_MODEL_FAMILY_PARITY_CAPABILITY_PROFILE_V1,
        status=status,
        evidence_scope=HIP_FGMRES_MODEL_FAMILY_PARITY_EVIDENCE_SCOPE_V1,
        backend_scope="hip",
        promotion_eligible=False,
        suite=suite,
        observed_cases=observations,
        coverage=coverage,
        claims=claims,
        receipt_hash=_ZERO_HASH,
    )
    return replace(
        draft,
        receipt_hash=canonical_hash(_receipt_payload(draft, include_hash=False)),
    )


def _coverage(
    observations: tuple[HipFgmresModelFamilyObservedCaseV1, ...],
) -> HipFgmresModelFamilyCoverageV1:
    slots = _validated_fixed_slots()
    registered_slots = tuple(slot for slot in slots if slot.registered)
    required_cells = tuple(
        HipFgmresModelFamilyMatrixCellV1(slot.slot_id, architecture)
        for architecture in HIP_FGMRES_MODEL_FAMILY_REQUIRED_ARCHITECTURE_BASES_V1
        for slot in slots
    )
    covered_keys = {
        (row.slot_id, row.runtime_architecture_base)
        for row in observations
        if row.slot_id is not None
    }
    covered_cells = tuple(
        row
        for row in required_cells
        if (row.slot_id, row.architecture_base) in covered_keys
    )
    missing_cells = tuple(
        row
        for row in required_cells
        if (row.slot_id, row.architecture_base) not in covered_keys
    )
    observed_set = {row.runtime_architecture_base for row in observations}
    observed_architectures = tuple(
        architecture
        for architecture in HIP_FGMRES_MODEL_FAMILY_REQUIRED_ARCHITECTURE_BASES_V1
        if architecture in observed_set
    )
    registered_ids = {slot.slot_id for slot in registered_slots}
    completed = tuple(
        architecture
        for architecture in HIP_FGMRES_MODEL_FAMILY_REQUIRED_ARCHITECTURE_BASES_V1
        if len(registered_ids) == len(slots)
        and all((slot.slot_id, architecture) in covered_keys for slot in slots)
    )
    incomplete = tuple(
        architecture
        for architecture in HIP_FGMRES_MODEL_FAMILY_REQUIRED_ARCHITECTURE_BASES_V1
        if architecture not in completed
    )
    return HipFgmresModelFamilyCoverageV1(
        validated_input_case_count=len(observations),
        registered_input_case_count=len(covered_cells),
        unregistered_input_case_count=sum(
            row.registration_status == "unregistered_case" for row in observations
        ),
        required_slot_count=len(slots),
        registered_slot_definition_count=len(registered_slots),
        required_architecture_count=len(
            HIP_FGMRES_MODEL_FAMILY_REQUIRED_ARCHITECTURE_BASES_V1
        ),
        expected_matrix_cell_count=len(required_cells),
        covered_matrix_cell_count=len(covered_cells),
        observed_architecture_bases=observed_architectures,
        completed_architecture_bases=completed,
        incomplete_architecture_bases=incomplete,
        unregistered_slot_definition_ids=tuple(
            slot.slot_id for slot in slots if not slot.registered
        ),
        covered_cells=covered_cells,
        missing_cells=missing_cells,
    )


def _claims(coverage: HipFgmresModelFamilyCoverageV1) -> HipFgmresModelFamilyClaimsV1:
    registration_complete = (
        coverage.registered_slot_definition_count == coverage.required_slot_count
        and coverage.required_slot_count > 0
    )
    matrix_complete = (
        registration_complete
        and coverage.covered_matrix_cell_count == coverage.expected_matrix_cell_count
        and not coverage.missing_cells
    )
    multiarchitecture = (
        matrix_complete
        and len(coverage.completed_architecture_bases)
        == coverage.required_architecture_count
        and coverage.required_architecture_count >= 2
    )
    return HipFgmresModelFamilyClaimsV1(
        fixed_suite_slot_registration_complete=registration_complete,
        fixed_suite_matrix_complete=matrix_complete,
        full_model_family_parity_verified=matrix_complete,
        multi_architecture_parity_verified=multiarchitecture,
        same_process_actual_two_isa_verified=multiarchitecture,
    )


def _suite_summary() -> HipFgmresModelFamilySuiteSummaryV1:
    slots = _validated_fixed_slots()
    manifest = {
        "suite_id": HIP_FGMRES_MODEL_FAMILY_PARITY_SUITE_ID_V1,
        "suite_scope": HIP_FGMRES_MODEL_FAMILY_PARITY_SUITE_SCOPE_V1,
        "required_architecture_bases": list(
            HIP_FGMRES_MODEL_FAMILY_REQUIRED_ARCHITECTURE_BASES_V1
        ),
        "slots": [slot.to_manifest_row() for slot in slots],
        "caller_override_allowed": False,
    }
    return HipFgmresModelFamilySuiteSummaryV1(
        suite_id=HIP_FGMRES_MODEL_FAMILY_PARITY_SUITE_ID_V1,
        suite_scope=HIP_FGMRES_MODEL_FAMILY_PARITY_SUITE_SCOPE_V1,
        suite_hash=canonical_hash(manifest),
        required_architecture_bases=(
            HIP_FGMRES_MODEL_FAMILY_REQUIRED_ARCHITECTURE_BASES_V1[0],
            HIP_FGMRES_MODEL_FAMILY_REQUIRED_ARCHITECTURE_BASES_V1[1],
        ),
        required_slot_ids=tuple(slot.slot_id for slot in slots),
        registered_slot_ids=tuple(slot.slot_id for slot in slots if slot.registered),
    )


def _validated_fixed_slots() -> tuple[_FixedSuiteSlotV1, ...]:
    slots = _FIXED_SUITE_SLOTS_V1
    if type(slots) is not tuple or not slots:
        _fail("hip_fgmres_model_family_suite_slots_invalid", "/suite/slots")
    if any(type(slot) is not _FixedSuiteSlotV1 for slot in slots):
        _fail("hip_fgmres_model_family_suite_slot_type_invalid", "/suite/slots")
    ids = tuple(slot.slot_id for slot in slots)
    if ids != HIP_FGMRES_MODEL_FAMILY_REQUIRED_SLOT_IDS_V1 or len(ids) != len(set(ids)):
        _fail("hip_fgmres_model_family_suite_slot_ids_invalid", "/suite/slots")
    for index, slot in enumerate(slots):
        if (
            type(slot.slot_id) is not str
            or type(slot.group) is not str
            or slot.group not in {"model_semantics", "recurrence_semantics"}
            or type(slot.description) is not str
            or not slot.description
        ):
            _fail("hip_fgmres_model_family_suite_slot_invalid", f"/suite/slots/{index}")
        if slot.registered:
            for value in (
                slot.expected_descriptor_hash,
                slot.expected_model_ir_content_hash,
                slot.expected_execution_plan_hash,
                slot.expected_policy_hash,
                slot.expected_cpu_result_hash,
            ):
                if type(value) is not str or _HASH_RE.fullmatch(value) is None:
                    _fail(
                        "hip_fgmres_model_family_suite_slot_hash_invalid",
                        f"/suite/slots/{index}",
                    )
    return slots


def _validate_observation(
    observation: HipFgmresModelFamilyObservedCaseV1,
    path: str,
) -> None:
    if type(observation) is not HipFgmresModelFamilyObservedCaseV1:
        _fail("hip_fgmres_model_family_observation_type_invalid", path)
    _validate_descriptor(observation.descriptor, f"{path}/descriptor")
    hash_fields = (
        observation.case_id,
        observation.case_receipt_hash,
        observation.model_ir_content_hash,
        observation.execution_plan_hash,
        observation.policy_hash,
        observation.cpu_result_hash,
        observation.device_identity_receipt_hash,
    )
    if any(
        type(value) is not str or _HASH_RE.fullmatch(value) is None
        for value in hash_fields
    ):
        _fail("hip_fgmres_model_family_observation_hash_invalid", path)
    if (
        type(observation.cpu_status) is not str
        or not observation.cpu_status
        or type(observation.cpu_termination_code) is not str
        or not observation.cpu_termination_code
        or type(observation.device_ordinal) is not int
        or observation.device_ordinal < 0
        or _ARCH_RE.fullmatch(observation.compiled_architecture) is None
        or observation.runtime_architecture_base
        not in HIP_FGMRES_MODEL_FAMILY_REQUIRED_ARCHITECTURE_BASES_V1
        or normalize_hip_gcn_architecture_v1(observation.compiled_architecture).base
        != observation.runtime_architecture_base
        or _UUID_RE.fullmatch(observation.device_uuid_bytes_hex) is None
        or _PCI_BDF_RE.fullmatch(observation.device_pci_bdf) is None
    ):
        _fail("hip_fgmres_model_family_observation_binding_invalid", path)
    if (
        observation.execution_plan_hash != observation.descriptor.execution_plan_hash
        or observation.model_ir_content_hash
        != observation.descriptor.model_ir_content_hash
    ):
        _fail("hip_fgmres_model_family_observation_descriptor_mismatch", path)
    matches = tuple(
        slot
        for slot in _validated_fixed_slots()
        if _slot_matches(
            slot,
            descriptor=observation.descriptor,
            policy_hash=observation.policy_hash,
            cpu_result_hash=observation.cpu_result_hash,
            cpu_status=observation.cpu_status,
            cpu_termination_code=observation.cpu_termination_code,
        )
    )
    if len(matches) > 1:
        _fail("hip_fgmres_model_family_case_slot_ambiguous", f"{path}/classification")
    if not matches:
        if (
            observation.registration_status != "unregistered_case"
            or observation.slot_id is not None
            or observation.logical_case_key is not None
            or observation.matrix_cell_id is not None
        ):
            _fail("hip_fgmres_model_family_unregistered_case_invalid", path)
        return
    slot = matches[0]
    logical_case_key = canonical_hash(
        {
            "suite_hash": _suite_summary().suite_hash,
            "slot_id": slot.slot_id,
            "descriptor_hash": observation.descriptor.descriptor_hash,
            "execution_plan_hash": observation.execution_plan_hash,
            "policy_hash": observation.policy_hash,
            "cpu_result_hash": observation.cpu_result_hash,
        }
    )
    matrix_cell_id = canonical_hash(
        {
            "logical_case_key": logical_case_key,
            "runtime_architecture_base": observation.runtime_architecture_base,
            "case_receipt_hash": observation.case_receipt_hash,
            "device_identity_receipt_hash": observation.device_identity_receipt_hash,
        }
    )
    if (
        observation.registration_status != "exact_slot_registered"
        or observation.slot_id != slot.slot_id
        or observation.logical_case_key != logical_case_key
        or observation.matrix_cell_id != matrix_cell_id
    ):
        _fail("hip_fgmres_model_family_registered_case_invalid", path)


def _validate_observation_set(
    observations: tuple[HipFgmresModelFamilyObservedCaseV1, ...],
) -> None:
    expected_order = tuple(
        sorted(
            observations,
            key=lambda row: (
                HIP_FGMRES_MODEL_FAMILY_REQUIRED_ARCHITECTURE_BASES_V1.index(
                    row.runtime_architecture_base
                ),
                row.slot_id or "~unregistered",
                row.case_id,
            ),
        )
    )
    if observations != expected_order:
        _fail("hip_fgmres_model_family_observed_cases_order_invalid", "/observed_cases")
    input_keys = tuple(
        (row.case_id, row.runtime_architecture_base) for row in observations
    )
    if len(input_keys) != len(set(input_keys)):
        _fail("hip_fgmres_model_family_duplicate_input_case", "/observed_cases")
    cell_keys = tuple(
        (row.slot_id, row.runtime_architecture_base)
        for row in observations
        if row.slot_id is not None
    )
    if len(cell_keys) != len(set(cell_keys)):
        _fail("hip_fgmres_model_family_duplicate_matrix_cell", "/observed_cases")
    architecture_bases_by_uuid: dict[str, set[str]] = {}
    architecture_bases_by_pci_bdf: dict[str, set[str]] = {}
    for observation in observations:
        architecture_bases_by_uuid.setdefault(
            observation.device_uuid_bytes_hex,
            set(),
        ).add(observation.runtime_architecture_base)
        architecture_bases_by_pci_bdf.setdefault(
            observation.device_pci_bdf,
            set(),
        ).add(observation.runtime_architecture_base)
    if any(
        len(architecture_bases) > 1
        for architecture_bases in (
            *architecture_bases_by_uuid.values(),
            *architecture_bases_by_pci_bdf.values(),
        )
    ):
        _fail(
            "hip_fgmres_model_family_device_architecture_identity_conflict",
            "/observed_cases",
        )


def _validate_descriptor(
    descriptor: HipFgmresModelFamilyCaseDescriptorV1,
    path: str,
) -> None:
    if type(descriptor) is not HipFgmresModelFamilyCaseDescriptorV1:
        _fail("hip_fgmres_model_family_descriptor_type_invalid", path)
    hash_fields = (
        "execution_plan_hash",
        "model_ir_content_hash",
        "solver_numeric_buffer_hash",
        "solver_entity_mapping_hash",
        "solver_artifact_hash",
        "operator_hash",
        "numeric_snapshot_hash",
        "symbolic_reuse_hash",
        "partition_hash",
        "descriptor_hash",
    )
    if any(
        type(getattr(descriptor, name)) is not str
        or _HASH_RE.fullmatch(getattr(descriptor, name)) is None
        for name in hash_fields
    ):
        _fail("hip_fgmres_model_family_descriptor_hash_invalid", path)
    string_fields = (
        "execution_plan_schema_version",
        "execution_plan_capability_profile",
        "solver_buffer_schema_version",
        "operator_version",
        "source_element_operator_version",
    )
    if any(
        type(getattr(descriptor, name)) is not str or not getattr(descriptor, name)
        for name in string_fields
    ):
        _fail("hip_fgmres_model_family_descriptor_string_invalid", path)
    integer_fields = (
        "node_count",
        "element_count",
        "global_dof_count",
        "free_dof_count",
        "reduced_csr_nnz",
        "nonzero_local_axis_roll_count",
        "nonzero_offset_component_count",
        "released_dof_count",
    )
    if any(type(getattr(descriptor, name)) is not int for name in integer_fields):
        _fail("hip_fgmres_model_family_descriptor_integer_type_invalid", path)
    if (
        descriptor.node_count <= 0
        or descriptor.element_count <= 0
        or descriptor.global_dof_count <= 0
        or descriptor.free_dof_count <= 0
        or descriptor.free_dof_count > descriptor.global_dof_count
        or descriptor.reduced_csr_nnz <= 0
        or descriptor.nonzero_local_axis_roll_count < 0
        or descriptor.nonzero_offset_component_count < 0
        or descriptor.released_dof_count < 0
    ):
        _fail("hip_fgmres_model_family_descriptor_extent_invalid", path)
    if (
        type(descriptor.element_signatures) is not tuple
        or not descriptor.element_signatures
        or any(
            type(row) is not HipFgmresModelFamilyElementSignatureV1
            for row in descriptor.element_signatures
        )
        or sum(row.element_count for row in descriptor.element_signatures)
        != descriptor.element_count
    ):
        _fail("hip_fgmres_model_family_element_signatures_invalid", path)
    signature_keys = tuple(
        (
            row.element_type_code,
            row.formulation_code,
            row.material_law_code,
            row.section_family_code,
        )
        for row in descriptor.element_signatures
    )
    if signature_keys != tuple(sorted(set(signature_keys))):
        _fail("hip_fgmres_model_family_element_signature_order_invalid", path)
    for row in descriptor.element_signatures:
        if any(
            type(getattr(row, name)) is not int for name in row.__dataclass_fields__
        ):
            _fail("hip_fgmres_model_family_element_signature_type_invalid", path)
        if (
            min(
                row.element_type_code,
                row.formulation_code,
                row.material_law_code,
                row.section_family_code,
                row.element_count,
            )
            <= 0
        ):
            _fail("hip_fgmres_model_family_element_signature_invalid", path)
    if (
        type(descriptor.metadata_buffer_bindings) is not tuple
        or tuple(row.name for row in descriptor.metadata_buffer_bindings)
        != _METADATA_BUFFER_NAMES
        or any(
            type(row) is not HipFgmresModelFamilyBufferBindingV1
            or type(row.content_hash) is not str
            or _HASH_RE.fullmatch(row.content_hash) is None
            for row in descriptor.metadata_buffer_bindings
        )
    ):
        _fail("hip_fgmres_model_family_metadata_bindings_invalid", path)
    for mask in (
        descriptor.load_nonzero_component_mask,
        descriptor.support_component_mask,
    ):
        if (
            type(mask) is not tuple
            or len(mask) != 6
            or any(type(value) is not bool for value in mask)
        ):
            _fail("hip_fgmres_model_family_component_mask_invalid", path)
    expected_hash = canonical_hash(_descriptor_payload(descriptor, include_hash=False))
    if descriptor.descriptor_hash != expected_hash:
        _fail("hip_fgmres_model_family_descriptor_hash_mismatch", path)


def _validate_exact_nested_types(receipt: HipFgmresModelFamilyParityReceiptV1) -> None:
    string_fields = (
        "schema_version",
        "capability_profile",
        "status",
        "evidence_scope",
        "backend_scope",
        "receipt_hash",
    )
    if any(type(getattr(receipt, name)) is not str for name in string_fields):
        _fail("hip_fgmres_model_family_receipt_scalar_type_invalid", "/")
    if type(receipt.promotion_eligible) is not bool:
        _fail(
            "hip_fgmres_model_family_receipt_scalar_type_invalid", "/promotion_eligible"
        )
    if any(
        type(getattr(receipt.claims, name)) is not bool
        for name in receipt.claims.__dataclass_fields__
    ):
        _fail("hip_fgmres_model_family_claim_type_invalid", "/claims")
    coverage = receipt.coverage
    for name in coverage.__dataclass_fields__:
        value = getattr(coverage, name)
        if name.endswith("count") and type(value) is not int:
            _fail(
                "hip_fgmres_model_family_coverage_count_type_invalid",
                f"/coverage/{name}",
            )
    tuple_fields = (
        "observed_architecture_bases",
        "completed_architecture_bases",
        "incomplete_architecture_bases",
        "unregistered_slot_definition_ids",
        "covered_cells",
        "missing_cells",
    )
    if any(type(getattr(coverage, name)) is not tuple for name in tuple_fields):
        _fail("hip_fgmres_model_family_coverage_tuple_type_invalid", "/coverage")
    if any(
        type(row) is not HipFgmresModelFamilyMatrixCellV1
        for row in (*coverage.covered_cells, *coverage.missing_cells)
    ):
        _fail("hip_fgmres_model_family_coverage_cell_type_invalid", "/coverage")


def _descriptor_payload(
    descriptor: HipFgmresModelFamilyCaseDescriptorV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "descriptor_version": descriptor.descriptor_version,
        "execution_plan_schema_version": descriptor.execution_plan_schema_version,
        "execution_plan_capability_profile": (
            descriptor.execution_plan_capability_profile
        ),
        "execution_plan_hash": descriptor.execution_plan_hash,
        "model_ir_content_hash": descriptor.model_ir_content_hash,
        "solver_buffer_schema_version": descriptor.solver_buffer_schema_version,
        "solver_numeric_buffer_hash": descriptor.solver_numeric_buffer_hash,
        "solver_entity_mapping_hash": descriptor.solver_entity_mapping_hash,
        "solver_artifact_hash": descriptor.solver_artifact_hash,
        "operator_version": descriptor.operator_version,
        "source_element_operator_version": descriptor.source_element_operator_version,
        "operator_hash": descriptor.operator_hash,
        "numeric_snapshot_hash": descriptor.numeric_snapshot_hash,
        "symbolic_reuse_hash": descriptor.symbolic_reuse_hash,
        "partition_hash": descriptor.partition_hash,
        "node_count": descriptor.node_count,
        "element_count": descriptor.element_count,
        "global_dof_count": descriptor.global_dof_count,
        "free_dof_count": descriptor.free_dof_count,
        "reduced_csr_nnz": descriptor.reduced_csr_nnz,
        "element_signatures": [row.to_dict() for row in descriptor.element_signatures],
        "metadata_buffer_bindings": [
            row.to_dict() for row in descriptor.metadata_buffer_bindings
        ],
        "load_nonzero_component_mask": list(descriptor.load_nonzero_component_mask),
        "support_component_mask": list(descriptor.support_component_mask),
        "nonzero_local_axis_roll_count": descriptor.nonzero_local_axis_roll_count,
        "nonzero_offset_component_count": descriptor.nonzero_offset_component_count,
        "released_dof_count": descriptor.released_dof_count,
    }
    if include_hash:
        payload["descriptor_hash"] = descriptor.descriptor_hash
    return payload


def _receipt_payload(
    receipt: HipFgmresModelFamilyParityReceiptV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": receipt.schema_version,
        "capability_profile": receipt.capability_profile,
        "status": receipt.status,
        "evidence_scope": receipt.evidence_scope,
        "backend_scope": receipt.backend_scope,
        "promotion_eligible": receipt.promotion_eligible,
        "suite": receipt.suite.to_dict(),
        "observed_cases": [row.to_dict() for row in receipt.observed_cases],
        "coverage": receipt.coverage.to_dict(),
        "claims": receipt.claims.to_dict(),
    }
    if include_hash:
        payload["receipt_hash"] = receipt.receipt_hash
    return payload


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    path = Path(__file__).resolve().parents[2] / "schemas" / _SCHEMA_RESOURCE
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _fail(code: str, path: str, message: str = "") -> NoReturn:
    raise HipFgmresModelFamilyParityV1Error(code, path, message)


__all__ = [
    "HIP_FGMRES_MODEL_FAMILY_PARITY_CAPABILITY_PROFILE_V1",
    "HIP_FGMRES_MODEL_FAMILY_PARITY_EVIDENCE_SCOPE_V1",
    "HIP_FGMRES_MODEL_FAMILY_PARITY_SCHEMA_VERSION_V1",
    "HIP_FGMRES_MODEL_FAMILY_PARITY_SUITE_ID_V1",
    "HIP_FGMRES_MODEL_FAMILY_PARITY_SUITE_SCOPE_V1",
    "HIP_FGMRES_MODEL_FAMILY_REQUIRED_ARCHITECTURE_BASES_V1",
    "HIP_FGMRES_MODEL_FAMILY_REQUIRED_SLOT_IDS_V1",
    "HipFgmresModelFamilyBufferBindingV1",
    "HipFgmresModelFamilyCaseDescriptorV1",
    "HipFgmresModelFamilyClaimsV1",
    "HipFgmresModelFamilyCoverageV1",
    "HipFgmresModelFamilyElementSignatureV1",
    "HipFgmresModelFamilyMatrixCellV1",
    "HipFgmresModelFamilyObservedCaseV1",
    "HipFgmresModelFamilyParityReceiptV1",
    "HipFgmresModelFamilyParityResultV1",
    "HipFgmresModelFamilyParityV1Error",
    "HipFgmresModelFamilySuiteSummaryV1",
    "attest_hip_fgmres_model_family_coverage_v1",
    "derive_hip_fgmres_model_family_case_descriptor_v1",
    "validate_hip_fgmres_model_family_parity_receipt_v1",
    "validate_hip_fgmres_model_family_parity_result_v1",
]
