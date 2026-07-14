"""Registry-authoritative fixed-suite aggregation for live FGMRES cases.

This v2 contract consumes only exact process-local model-case parity results
and the package fixture registry v1.  It can establish bounded fixed-suite
cell coverage, but never promotes that finite observation to full model-family,
signed, ResultIR, performance, O(N), or commercial claims.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from importlib import resources
import json
import re
from typing import Any, Literal, NoReturn

from jsonschema import Draft202012Validator

from structural_analysis.engine_v2.backends.hip.device_identity_v1 import (
    normalize_hip_gcn_architecture_v1,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash

from .fgmres_fixture_registry_v1 import (
    HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1,
    HipFgmresFixtureRegistryResultV1,
    HipFgmresFixtureReplayV1,
    load_hip_fgmres_fixture_registry_v1,
    validate_hip_fgmres_fixture_registry_result_v1,
)
from .fgmres_model_case_parity_v1 import (
    HipFgmresModelCaseParityResultV1,
    validate_hip_fgmres_model_case_parity_result_v1,
)
from .fgmres_model_family_parity_v1 import _derive_descriptor


HIP_FGMRES_MODEL_FAMILY_PARITY_SCHEMA_VERSION_V2 = (
    "structural-analysis-hip-fgmres-model-family-parity.v2"
)
HIP_FGMRES_MODEL_FAMILY_PARITY_CAPABILITY_PROFILE_V2 = (
    "phase0_registry_bound_fixed_suite_live_hardware_coverage"
)
HIP_FGMRES_MODEL_FAMILY_PARITY_EVIDENCE_SCOPE_V2 = (
    "process_local_registry_bound_unsigned_non_promoting"
)
HIP_FGMRES_MODEL_FAMILY_REQUIRED_ARCHITECTURE_BASES_V2 = (
    "gfx1030",
    "gfx1100",
)
HIP_FGMRES_MODEL_FAMILY_REQUIRED_SLOT_IDS_V2 = (
    HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1
)

_SCHEMA_RESOURCE = "hip_fgmres_model_family_parity_v2.schema.json"
_ZERO_HASH = "sha256:" + "0" * 64
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class HipFgmresModelFamilyParityV2Error(RuntimeError):
    """Stable fail-closed fixed-suite v2 aggregation error."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = message or code
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresModelFamilyObservedCellV2:
    slot_id: str
    runtime_architecture_base: str
    compiled_architecture: str
    device_ordinal: int
    device_uuid_bytes_hex: str
    device_pci_bdf: str
    runtime_library_sha256: str
    kernel_identity_hash: str
    kernel_source_sha256: str
    case_id: str
    case_receipt_hash: str
    device_identity_receipt_hash: str
    model_ir_content_hash: str
    execution_plan_hash: str
    fgmres_plan_hash: str
    recurrence_plan_hash: str
    policy_hash: str
    cpu_result_hash: str
    descriptor_hash: str
    slot_registration_hash: str
    case_fingerprint: str
    logical_case_key: str
    matrix_cell_id: str

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresModelFamilyCoverageV2:
    required_slot_count: int
    required_architecture_count: int
    expected_matrix_cell_count: int
    validated_input_case_count: int
    covered_matrix_cell_count: int
    missing_matrix_cell_count: int
    covered_cells: tuple[str, ...]
    missing_cells: tuple[str, ...]
    observed_architecture_bases: tuple[str, ...]
    completed_architecture_bases: tuple[str, ...]
    incomplete_architecture_bases: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            name: list(value) if type(value) is tuple else value
            for name, value in (
                (field_name, getattr(self, field_name))
                for field_name in self.__dataclass_fields__
            )
        }


@dataclass(frozen=True, slots=True)
class HipFgmresModelFamilyClaimsV2:
    fixed_package_registry_replayed: Literal[True] = True
    exact_registered_slot_classification: Literal[True] = True
    all_submitted_process_local_case_authorities_replayed: Literal[True] = True
    duplicate_matrix_cells_rejected: Literal[True] = True
    architecture_device_consistency_verified: Literal[True] = True
    primary_gfx1030_fixed_suite_complete: bool = False
    unsigned_fixed_suite_two_architecture_matrix_observed: bool = False
    serialized_external_evidence_counted: Literal[False] = False
    signed_evidence: Literal[False] = False
    promotion_eligible: Literal[False] = False
    full_model_family_parity_verified: Literal[False] = False
    multiarchitecture_parity_verified: Literal[False] = False
    result_ir_verified: Literal[False] = False
    iteration_host_copy_zero_verified: Literal[False] = False
    speedup_verified: Literal[False] = False
    end_to_end_o_n_verified: Literal[False] = False
    commercial_ready: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresModelFamilyParityReceiptV2:
    schema_version: str
    capability_profile: str
    status: str
    evidence_scope: str
    registry_bytes_sha256: str
    registry_hash: str
    required_architecture_bases: tuple[str, str]
    required_slot_ids: tuple[str, ...]
    observations: tuple[HipFgmresModelFamilyObservedCellV2, ...]
    coverage: HipFgmresModelFamilyCoverageV2
    claims: HipFgmresModelFamilyClaimsV2
    promotion_eligible: Literal[False]
    receipt_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_model_family_parity_receipt_v2(self)
        return _receipt_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class HipFgmresModelFamilyParityResultV2:
    receipt: HipFgmresModelFamilyParityReceiptV2
    _case_results: tuple[HipFgmresModelCaseParityResultV1, ...] = field(
        repr=False,
        compare=False,
    )
    _registry_result: HipFgmresFixtureRegistryResultV1 = field(
        repr=False,
        compare=False,
    )

    def to_manifest(self) -> dict[str, Any]:
        return self.receipt.to_dict()


def attest_hip_fgmres_model_family_coverage_v2(
    case_results: tuple[HipFgmresModelCaseParityResultV1, ...],
) -> HipFgmresModelFamilyParityResultV2:
    """Classify exact live cases against the fixed package registry only."""

    registry = load_hip_fgmres_fixture_registry_v1()
    receipt = _evaluate_case_results(case_results, registry)
    return HipFgmresModelFamilyParityResultV2(
        receipt=receipt,
        _case_results=case_results,
        _registry_result=registry,
    )


def validate_hip_fgmres_model_family_parity_result_v2(
    result: HipFgmresModelFamilyParityResultV2,
    *,
    expected_case_results: tuple[HipFgmresModelCaseParityResultV1, ...] | None = None,
) -> HipFgmresModelFamilyParityResultV2:
    """Replay retained live cases and a fresh package registry."""

    if type(result) is not HipFgmresModelFamilyParityResultV2:
        _fail("hip_fgmres_model_family_v2_result_type_invalid", "/")
    if type(result._case_results) is not tuple:
        _fail("hip_fgmres_model_family_v2_case_container_invalid", "/cases")
    if expected_case_results is not None and result._case_results is not (
        expected_case_results
    ):
        if result._case_results != expected_case_results:
            _fail(
                "hip_fgmres_model_family_v2_expected_cases_mismatch",
                "/cases",
            )
    validate_hip_fgmres_fixture_registry_result_v1(result._registry_result)
    fresh_registry = load_hip_fgmres_fixture_registry_v1()
    expected = _evaluate_case_results(result._case_results, fresh_registry)
    if result.receipt != expected:
        _fail("hip_fgmres_model_family_v2_result_replay_mismatch", "/receipt")
    _validate_receipt_against_registry(result.receipt, fresh_registry)
    return result


def validate_hip_fgmres_model_family_parity_receipt_v2(
    receipt: HipFgmresModelFamilyParityReceiptV2,
) -> HipFgmresModelFamilyParityReceiptV2:
    """Validate the structural receipt without treating it as live authority."""

    if type(receipt) is not HipFgmresModelFamilyParityReceiptV2:
        _fail("hip_fgmres_model_family_v2_receipt_type_invalid", "/")
    registry = load_hip_fgmres_fixture_registry_v1()
    return _validate_receipt_against_registry(receipt, registry)


def _validate_receipt_against_registry(
    receipt: HipFgmresModelFamilyParityReceiptV2,
    registry: HipFgmresFixtureRegistryResultV1,
) -> HipFgmresModelFamilyParityReceiptV2:
    if type(receipt) is not HipFgmresModelFamilyParityReceiptV2:
        _fail("hip_fgmres_model_family_v2_receipt_type_invalid", "/")
    if type(registry) is not HipFgmresFixtureRegistryResultV1:
        _fail("hip_fgmres_model_family_v2_registry_type_invalid", "/registry")
    if (
        type(receipt.observations) is not tuple
        or any(type(row) is not HipFgmresModelFamilyObservedCellV2 for row in receipt.observations)
        or type(receipt.coverage) is not HipFgmresModelFamilyCoverageV2
        or type(receipt.claims) is not HipFgmresModelFamilyClaimsV2
    ):
        _fail("hip_fgmres_model_family_v2_receipt_container_invalid", "/")
    payload = _receipt_payload(receipt, include_hash=True)
    errors = sorted(
        _schema_validator().iter_errors(payload),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        _fail("hip_fgmres_model_family_v2_schema_invalid", path, error.message)
    expected_hash = canonical_hash(_receipt_payload(receipt, include_hash=False))
    if receipt.receipt_hash != expected_hash:
        _fail(
            "hip_fgmres_model_family_v2_receipt_hash_mismatch",
            "/receipt_hash",
        )
    if (
        receipt.schema_version != HIP_FGMRES_MODEL_FAMILY_PARITY_SCHEMA_VERSION_V2
        or receipt.capability_profile
        != HIP_FGMRES_MODEL_FAMILY_PARITY_CAPABILITY_PROFILE_V2
        or receipt.evidence_scope
        != HIP_FGMRES_MODEL_FAMILY_PARITY_EVIDENCE_SCOPE_V2
        or receipt.required_architecture_bases
        != HIP_FGMRES_MODEL_FAMILY_REQUIRED_ARCHITECTURE_BASES_V2
        or receipt.required_slot_ids != HIP_FGMRES_MODEL_FAMILY_REQUIRED_SLOT_IDS_V2
        or receipt.promotion_eligible is not False
        or receipt.claims.promotion_eligible is not False
    ):
        _fail("hip_fgmres_model_family_v2_receipt_semantics_invalid", "/")
    if (
        receipt.registry_bytes_sha256 != registry.registry_bytes_sha256
        or receipt.registry_hash != registry.registry_hash
    ):
        _fail(
            "hip_fgmres_model_family_v2_registry_identity_mismatch",
            "/registry_hash",
        )
    for index, observation in enumerate(receipt.observations):
        _validate_observation_against_registry(
            observation,
            registry,
            path=f"/observations/{index}",
        )
    _validate_observation_set(list(receipt.observations))
    expected_order = tuple(
        sorted(
            receipt.observations,
            key=lambda row: (
                HIP_FGMRES_MODEL_FAMILY_REQUIRED_ARCHITECTURE_BASES_V2.index(
                    row.runtime_architecture_base
                ),
                HIP_FGMRES_MODEL_FAMILY_REQUIRED_SLOT_IDS_V2.index(row.slot_id),
            ),
        )
    )
    if receipt.observations != expected_order:
        _fail(
            "hip_fgmres_model_family_v2_observation_order_invalid",
            "/observations",
        )
    _validate_coverage_and_claims(receipt)
    return receipt


def _evaluate_case_results(
    case_results: tuple[HipFgmresModelCaseParityResultV1, ...],
    registry: HipFgmresFixtureRegistryResultV1,
) -> HipFgmresModelFamilyParityReceiptV2:
    if type(case_results) is not tuple:
        _fail("hip_fgmres_model_family_v2_case_container_invalid", "/cases")
    if any(type(case) is not HipFgmresModelCaseParityResultV1 for case in case_results):
        _fail("hip_fgmres_model_family_v2_case_type_invalid", "/cases")
    if type(registry) is not HipFgmresFixtureRegistryResultV1:
        _fail("hip_fgmres_model_family_v2_registry_type_invalid", "/registry")

    observations: list[HipFgmresModelFamilyObservedCellV2] = []
    for index, case in enumerate(case_results):
        path = f"/cases/{index}"
        validate_hip_fgmres_model_case_parity_result_v1(case)
        receipt = case.receipt
        bindings = receipt.bindings
        source_plan = case._source_execution_plan
        cpu = case._cpu_result
        descriptor = _derive_descriptor(source_plan)
        architecture = normalize_hip_gcn_architecture_v1(
            bindings.runtime_architecture_base
        )
        compiled = normalize_hip_gcn_architecture_v1(bindings.compiled_architecture)
        if (
            architecture.raw != architecture.base
            or architecture.base != bindings.runtime_architecture_base
            or compiled.base != architecture.base
            or architecture.base
            not in HIP_FGMRES_MODEL_FAMILY_REQUIRED_ARCHITECTURE_BASES_V2
        ):
            _fail(
                "hip_fgmres_model_family_v2_architecture_invalid",
                f"{path}/architecture",
            )
        matches = tuple(
            slot
            for slot in registry.slots
            if _slot_matches(slot, case, descriptor.descriptor_hash)
        )
        if len(matches) != 1:
            _fail(
                "hip_fgmres_model_family_v2_exact_slot_match_required",
                f"{path}/classification",
            )
        slot = matches[0]
        logical_case_key = canonical_hash(
            {
                "registry_hash": registry.registry_hash,
                "slot_registration_hash": slot.slot_registration_hash,
                "slot_id": slot.slot_id,
                "descriptor_hash": descriptor.descriptor_hash,
                "execution_plan_hash": bindings.execution_plan_hash,
                "fgmres_plan_hash": bindings.fgmres_plan_hash,
                "recurrence_plan_hash": bindings.recurrence_plan_hash,
                "policy_hash": bindings.policy_hash,
                "cpu_result_hash": bindings.cpu_result_hash,
            }
        )
        matrix_cell_id = canonical_hash(
            {
                "logical_case_key": logical_case_key,
                "runtime_architecture_base": architecture.base,
                "device_identity_receipt_hash": (
                    bindings.device_identity_receipt_hash
                ),
                "case_receipt_hash": receipt.receipt_hash,
            }
        )
        observations.append(
            HipFgmresModelFamilyObservedCellV2(
                slot_id=slot.slot_id,
                runtime_architecture_base=architecture.base,
                compiled_architecture=compiled.normalized,
                device_ordinal=bindings.device_ordinal,
                device_uuid_bytes_hex=bindings.device_uuid_bytes_hex,
                device_pci_bdf=bindings.device_pci_bdf,
                runtime_library_sha256=bindings.runtime_library_sha256,
                kernel_identity_hash=bindings.kernel_identity_hash,
                kernel_source_sha256=bindings.kernel_source_sha256,
                case_id=receipt.case_id,
                case_receipt_hash=receipt.receipt_hash,
                device_identity_receipt_hash=(
                    bindings.device_identity_receipt_hash
                ),
                model_ir_content_hash=bindings.model_ir_content_hash,
                execution_plan_hash=bindings.execution_plan_hash,
                fgmres_plan_hash=bindings.fgmres_plan_hash,
                recurrence_plan_hash=bindings.recurrence_plan_hash,
                policy_hash=bindings.policy_hash,
                cpu_result_hash=cpu.result_hash,
                descriptor_hash=descriptor.descriptor_hash,
                slot_registration_hash=slot.slot_registration_hash,
                case_fingerprint=slot.case_fingerprint,
                logical_case_key=logical_case_key,
                matrix_cell_id=matrix_cell_id,
            )
        )
        validate_hip_fgmres_model_case_parity_result_v1(case)
        if (
            case._source_execution_plan is not source_plan
            or case._cpu_result is not cpu
            or _derive_descriptor(source_plan).descriptor_hash
            != descriptor.descriptor_hash
        ):
            _fail(
                "hip_fgmres_model_family_v2_case_source_changed",
                path,
            )

    _validate_observation_set(observations)
    ordered = tuple(
        sorted(
            observations,
            key=lambda row: (
                HIP_FGMRES_MODEL_FAMILY_REQUIRED_ARCHITECTURE_BASES_V2.index(
                    row.runtime_architecture_base
                ),
                HIP_FGMRES_MODEL_FAMILY_REQUIRED_SLOT_IDS_V2.index(row.slot_id),
            ),
        )
    )
    coverage = _coverage(ordered)
    claims = HipFgmresModelFamilyClaimsV2(
        primary_gfx1030_fixed_suite_complete=(
            "gfx1030" in coverage.completed_architecture_bases
        ),
        unsigned_fixed_suite_two_architecture_matrix_observed=(
            coverage.covered_matrix_cell_count
            == coverage.expected_matrix_cell_count
        ),
    )
    if coverage.covered_matrix_cell_count == coverage.expected_matrix_cell_count:
        status = "unsigned_fixed_suite_two_architecture_matrix_observed_non_promoting"
    elif "gfx1030" in coverage.completed_architecture_bases:
        status = "primary_gfx1030_fixed_suite_complete_external_gfx1100_pending"
    elif coverage.covered_matrix_cell_count == 0:
        status = "pending_primary_gfx1030_and_external_gfx1100"
    else:
        status = "partial_fixed_suite_hardware_observation"
    draft = HipFgmresModelFamilyParityReceiptV2(
        schema_version=HIP_FGMRES_MODEL_FAMILY_PARITY_SCHEMA_VERSION_V2,
        capability_profile=HIP_FGMRES_MODEL_FAMILY_PARITY_CAPABILITY_PROFILE_V2,
        status=status,
        evidence_scope=HIP_FGMRES_MODEL_FAMILY_PARITY_EVIDENCE_SCOPE_V2,
        registry_bytes_sha256=registry.registry_bytes_sha256,
        registry_hash=registry.registry_hash,
        required_architecture_bases=(
            HIP_FGMRES_MODEL_FAMILY_REQUIRED_ARCHITECTURE_BASES_V2
        ),
        required_slot_ids=HIP_FGMRES_MODEL_FAMILY_REQUIRED_SLOT_IDS_V2,
        observations=ordered,
        coverage=coverage,
        claims=claims,
        promotion_eligible=False,
        receipt_hash=_ZERO_HASH,
    )
    receipt = replace(
        draft,
        receipt_hash=canonical_hash(_receipt_payload(draft, include_hash=False)),
    )
    return _validate_receipt_against_registry(receipt, registry)


def _slot_matches(
    slot: HipFgmresFixtureReplayV1,
    case: HipFgmresModelCaseParityResultV1,
    descriptor_hash: str,
) -> bool:
    bindings = case.receipt.bindings
    cpu = case._cpu_result
    return (
        slot.model.content_hash == bindings.model_ir_content_hash
        and slot.execution_plan.plan_hash == bindings.execution_plan_hash
        and slot.fgmres_plan.plan_hash == bindings.fgmres_plan_hash
        and slot.recurrence_plan.plan_hash == bindings.recurrence_plan_hash
        and slot.policy.policy_hash == bindings.policy_hash
        and slot.cpu_result.result_hash == bindings.cpu_result_hash
        and slot.cpu_result.result_hash == cpu.result_hash
        and slot.cpu_result.status == cpu.status
        and slot.cpu_result.termination_code == cpu.termination_code
        and slot.descriptor.descriptor_hash == descriptor_hash
    )


def _validate_observation_against_registry(
    observation: HipFgmresModelFamilyObservedCellV2,
    registry: HipFgmresFixtureRegistryResultV1,
    *,
    path: str,
) -> None:
    try:
        slot = registry.slot(observation.slot_id)
        compiled = normalize_hip_gcn_architecture_v1(
            observation.compiled_architecture
        )
    except Exception as exc:
        _fail(
            "hip_fgmres_model_family_v2_observation_binding_invalid",
            path,
            f"{type(exc).__name__}: {exc}",
        )
    if (
        compiled.base != observation.runtime_architecture_base
        or compiled.normalized != observation.compiled_architecture
    ):
        _fail(
            "hip_fgmres_model_family_v2_observation_binding_invalid",
            path,
        )
    if (
        observation.model_ir_content_hash != slot.model.content_hash
        or observation.execution_plan_hash != slot.execution_plan.plan_hash
        or observation.fgmres_plan_hash != slot.fgmres_plan.plan_hash
        or observation.recurrence_plan_hash != slot.recurrence_plan.plan_hash
        or observation.policy_hash != slot.policy.policy_hash
        or observation.cpu_result_hash != slot.cpu_result.result_hash
        or observation.descriptor_hash != slot.descriptor.descriptor_hash
        or observation.slot_registration_hash != slot.slot_registration_hash
        or observation.case_fingerprint != slot.case_fingerprint
    ):
        _fail(
            "hip_fgmres_model_family_v2_observation_registry_mismatch",
            path,
        )
    logical_case_key = canonical_hash(
        {
            "registry_hash": registry.registry_hash,
            "slot_registration_hash": slot.slot_registration_hash,
            "slot_id": slot.slot_id,
            "descriptor_hash": slot.descriptor.descriptor_hash,
            "execution_plan_hash": slot.execution_plan.plan_hash,
            "fgmres_plan_hash": slot.fgmres_plan.plan_hash,
            "recurrence_plan_hash": slot.recurrence_plan.plan_hash,
            "policy_hash": slot.policy.policy_hash,
            "cpu_result_hash": slot.cpu_result.result_hash,
        }
    )
    matrix_cell_id = canonical_hash(
        {
            "logical_case_key": logical_case_key,
            "runtime_architecture_base": observation.runtime_architecture_base,
            "device_identity_receipt_hash": (
                observation.device_identity_receipt_hash
            ),
            "case_receipt_hash": observation.case_receipt_hash,
        }
    )
    if (
        observation.logical_case_key != logical_case_key
        or observation.matrix_cell_id != matrix_cell_id
    ):
        _fail(
            "hip_fgmres_model_family_v2_observation_derived_binding_mismatch",
            path,
        )


def _validate_observation_set(
    observations: list[HipFgmresModelFamilyObservedCellV2],
) -> None:
    cells = tuple(
        (row.runtime_architecture_base, row.slot_id) for row in observations
    )
    if len(set(cells)) != len(cells):
        _fail("hip_fgmres_model_family_v2_duplicate_matrix_cell", "/cases")
    if len({row.case_id for row in observations}) != len(observations):
        _fail("hip_fgmres_model_family_v2_duplicate_case_id", "/cases")
    by_architecture: dict[str, set[tuple[Any, ...]]] = {}
    for row in observations:
        by_architecture.setdefault(row.runtime_architecture_base, set()).add(
            (
                row.device_ordinal,
                row.device_uuid_bytes_hex,
                row.device_pci_bdf,
                row.runtime_library_sha256,
                row.kernel_identity_hash,
                row.kernel_source_sha256,
                row.compiled_architecture,
            )
        )
    if any(len(values) != 1 for values in by_architecture.values()):
        _fail(
            "hip_fgmres_model_family_v2_architecture_device_inconsistent",
            "/cases",
        )
    architecture_bases_by_uuid: dict[str, set[str]] = {}
    architecture_bases_by_pci_bdf: dict[str, set[str]] = {}
    for row in observations:
        architecture_bases_by_uuid.setdefault(
            row.device_uuid_bytes_hex,
            set(),
        ).add(row.runtime_architecture_base)
        architecture_bases_by_pci_bdf.setdefault(
            row.device_pci_bdf,
            set(),
        ).add(row.runtime_architecture_base)
    if any(
        len(architectures) > 1
        for architectures in (
            *architecture_bases_by_uuid.values(),
            *architecture_bases_by_pci_bdf.values(),
        )
    ):
        _fail(
            "hip_fgmres_model_family_v2_cross_architecture_identity_conflict",
            "/cases",
        )


def _coverage(
    observations: tuple[HipFgmresModelFamilyObservedCellV2, ...],
) -> HipFgmresModelFamilyCoverageV2:
    required = tuple(
        f"{architecture}:{slot}"
        for architecture in HIP_FGMRES_MODEL_FAMILY_REQUIRED_ARCHITECTURE_BASES_V2
        for slot in HIP_FGMRES_MODEL_FAMILY_REQUIRED_SLOT_IDS_V2
    )
    covered_set = {
        f"{row.runtime_architecture_base}:{row.slot_id}" for row in observations
    }
    covered = tuple(cell for cell in required if cell in covered_set)
    missing = tuple(cell for cell in required if cell not in covered_set)
    observed_architectures = tuple(
        architecture
        for architecture in HIP_FGMRES_MODEL_FAMILY_REQUIRED_ARCHITECTURE_BASES_V2
        if any(
            row.runtime_architecture_base == architecture for row in observations
        )
    )
    completed = tuple(
        architecture
        for architecture in HIP_FGMRES_MODEL_FAMILY_REQUIRED_ARCHITECTURE_BASES_V2
        if all(
            f"{architecture}:{slot}" in covered_set
            for slot in HIP_FGMRES_MODEL_FAMILY_REQUIRED_SLOT_IDS_V2
        )
    )
    incomplete = tuple(
        architecture
        for architecture in HIP_FGMRES_MODEL_FAMILY_REQUIRED_ARCHITECTURE_BASES_V2
        if architecture not in completed
    )
    return HipFgmresModelFamilyCoverageV2(
        required_slot_count=len(HIP_FGMRES_MODEL_FAMILY_REQUIRED_SLOT_IDS_V2),
        required_architecture_count=len(
            HIP_FGMRES_MODEL_FAMILY_REQUIRED_ARCHITECTURE_BASES_V2
        ),
        expected_matrix_cell_count=len(required),
        validated_input_case_count=len(observations),
        covered_matrix_cell_count=len(covered),
        missing_matrix_cell_count=len(missing),
        covered_cells=covered,
        missing_cells=missing,
        observed_architecture_bases=observed_architectures,
        completed_architecture_bases=completed,
        incomplete_architecture_bases=incomplete,
    )


def _validate_coverage_and_claims(
    receipt: HipFgmresModelFamilyParityReceiptV2,
) -> None:
    rebuilt = _coverage(receipt.observations)
    if receipt.coverage != rebuilt:
        _fail("hip_fgmres_model_family_v2_coverage_mismatch", "/coverage")
    expected_claims = HipFgmresModelFamilyClaimsV2(
        primary_gfx1030_fixed_suite_complete=(
            "gfx1030" in rebuilt.completed_architecture_bases
        ),
        unsigned_fixed_suite_two_architecture_matrix_observed=(
            rebuilt.covered_matrix_cell_count == rebuilt.expected_matrix_cell_count
        ),
    )
    if receipt.claims != expected_claims:
        _fail("hip_fgmres_model_family_v2_claims_mismatch", "/claims")
    expected_status = (
        "unsigned_fixed_suite_two_architecture_matrix_observed_non_promoting"
        if rebuilt.covered_matrix_cell_count == rebuilt.expected_matrix_cell_count
        else (
            "primary_gfx1030_fixed_suite_complete_external_gfx1100_pending"
            if "gfx1030" in rebuilt.completed_architecture_bases
            else (
                "pending_primary_gfx1030_and_external_gfx1100"
                if rebuilt.covered_matrix_cell_count == 0
                else "partial_fixed_suite_hardware_observation"
            )
        )
    )
    if receipt.status != expected_status:
        _fail("hip_fgmres_model_family_v2_status_mismatch", "/status")


def _receipt_payload(
    receipt: HipFgmresModelFamilyParityReceiptV2,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": receipt.schema_version,
        "capability_profile": receipt.capability_profile,
        "status": receipt.status,
        "evidence_scope": receipt.evidence_scope,
        "registry_bytes_sha256": receipt.registry_bytes_sha256,
        "registry_hash": receipt.registry_hash,
        "required_architecture_bases": list(receipt.required_architecture_bases),
        "required_slot_ids": list(receipt.required_slot_ids),
        "observations": [row.to_dict() for row in receipt.observations],
        "coverage": receipt.coverage.to_dict(),
        "claims": receipt.claims.to_dict(),
        "promotion_eligible": receipt.promotion_eligible,
    }
    if include_hash:
        payload["receipt_hash"] = receipt.receipt_hash
    return payload


def _schema_validator() -> Draft202012Validator:
    schema_raw = resources.files("structural_analysis.schemas").joinpath(
        _SCHEMA_RESOURCE
    ).read_bytes()
    schema = json.loads(schema_raw.decode("utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _fail(code: str, path: str, message: str = "") -> NoReturn:
    raise HipFgmresModelFamilyParityV2Error(code, path, message)


__all__ = [
    "HIP_FGMRES_MODEL_FAMILY_PARITY_CAPABILITY_PROFILE_V2",
    "HIP_FGMRES_MODEL_FAMILY_PARITY_EVIDENCE_SCOPE_V2",
    "HIP_FGMRES_MODEL_FAMILY_PARITY_SCHEMA_VERSION_V2",
    "HIP_FGMRES_MODEL_FAMILY_REQUIRED_ARCHITECTURE_BASES_V2",
    "HIP_FGMRES_MODEL_FAMILY_REQUIRED_SLOT_IDS_V2",
    "HipFgmresModelFamilyClaimsV2",
    "HipFgmresModelFamilyCoverageV2",
    "HipFgmresModelFamilyObservedCellV2",
    "HipFgmresModelFamilyParityReceiptV2",
    "HipFgmresModelFamilyParityResultV2",
    "HipFgmresModelFamilyParityV2Error",
    "attest_hip_fgmres_model_family_coverage_v2",
    "validate_hip_fgmres_model_family_parity_receipt_v2",
    "validate_hip_fgmres_model_family_parity_result_v2",
]
