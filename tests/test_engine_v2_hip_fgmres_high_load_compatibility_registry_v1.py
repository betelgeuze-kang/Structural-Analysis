from __future__ import annotations

import copy
import gc
import inspect
import json
from pathlib import Path
import weakref

from jsonschema import Draft202012Validator
import numpy as np
import pytest

from structural_analysis.engine_v2.assembly_backend import (
    fgmres_high_load_compatibility_registry_v1 as registry_module,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_high_load_compatibility_registry_v1 import (
    HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_PARENT_REGISTRY_BYTES_SHA256_V1,
    HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_PARENT_REGISTRY_HASH_V1,
    HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_PARENT_SCHEMA_BYTES_SHA256_V1,
    HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_REQUIRED_SLOT_IDS_V1,
    HipFgmresHighLoadCompatibilityRegistryV1Error,
    load_hip_fgmres_high_load_compatibility_registry_v1,
    validate_hip_fgmres_high_load_compatibility_registry_result_v1,
)
from structural_analysis.engine_v2.contracts._canonical import sha256_prefixed


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (
    ROOT
    / "src/structural_analysis/schemas"
    / "hip_fgmres_high_load_compatibility_registry_v1.schema.json"
)
RESOURCE_DIR = (
    ROOT
    / "src/structural_analysis/engine_v2/assembly_backend/fixtures"
    / "fgmres_high_load_compatibility_v1"
)
REGISTRY = RESOURCE_DIR / "registry.v1.json"
PARENT_REGISTRY = (
    ROOT
    / "src/structural_analysis/engine_v2/assembly_backend/fixtures"
    / "fgmres_all_converged_v1/registry.v1.json"
)
PARENT_SCHEMA = (
    ROOT
    / "src/structural_analysis/schemas"
    / "hip_fgmres_all_converged_fixture_registry_v1.schema.json"
)


@pytest.fixture(scope="module")
def registry():
    return load_hip_fgmres_high_load_compatibility_registry_v1()


def test_high_load_registry_schema_is_full_const_and_parent_v0247_is_frozen() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    manifest = json.loads(REGISTRY.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
    assert schema["const"] == manifest
    assert sha256_prefixed(REGISTRY.read_bytes()) == (
        "sha256:7411b02b72500b7448ed97dd3470d27e8fb129a7d98ee600b2ff06374a1b113d"
    )
    assert manifest["registry_hash"] == (
        "sha256:72ea556471edb72a2262f870e76d4fc423e9d665da82f6d8e4d03dd6ae953f9e"
    )
    assert sha256_prefixed(SCHEMA.read_bytes()) == (
        "sha256:5883c16075f8ebabdc7e8a6dfdb2b300e3c89973cc14ea6e955bbd1d16f9ac75"
    )
    assert sha256_prefixed(PARENT_REGISTRY.read_bytes()) == (
        HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_PARENT_REGISTRY_BYTES_SHA256_V1
    )
    assert manifest["parent_registry"]["registry_hash"] == (
        HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_PARENT_REGISTRY_HASH_V1
    )
    assert sha256_prefixed(PARENT_SCHEMA.read_bytes()) == (
        HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_PARENT_SCHEMA_BYTES_SHA256_V1
    )
    assert manifest["parent_registry"]["source_registry_mutated"] is False


def test_registry_replays_three_original_scale_compatible_cpu_cases(registry) -> None:
    assert (
        tuple(
            inspect.signature(
                load_hip_fgmres_high_load_compatibility_registry_v1
            ).parameters
        )
        == ()
    )
    assert tuple(row.slot_id for row in registry.slots) == (
        HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_REQUIRED_SLOT_IDS_V1
    )
    assert tuple(row.high_load_value_si for row in registry.slots) == (
        -10000.0,
        100000.0,
        100000.0,
    )
    assert tuple(row.load_scale_factor for row in registry.slots) == (
        10000.0,
        100000.0,
        100000.0,
    )
    assert tuple(row.cpu_result.iteration_count for row in registry.slots) == (6, 4, 5)
    for row in registry.slots:
        assert row.cpu_result.status == "converged"
        assert row.cpu_result.solver_tolerance_passed
        assert row.cpu_result.authoritative_plan_tolerance_passed
        assert len(row.cpu_result.history) == 1
        assert row.compatibility.unchanged_sparse_plan_array_count == 16
        assert row.compatibility.unchanged_sparse_plan_arrays_byte_equal
        assert row.compatibility.exact_global_load_scaling_verified
        assert row.compatibility.direct_solution_linear_scaling_verified
        assert row.compatibility.cpu_solution_linear_scaling_verified
        assert row.execution_plan.symbolic_reuse_hash == (
            row.base_slot.execution_plan.symbolic_reuse_hash
        )
        assert row.execution_plan.partition_hash == (
            row.base_slot.execution_plan.partition_hash
        )
        assert row.execution_plan.recovery_operator_hash == (
            row.base_slot.execution_plan.recovery_operator_hash
        )
        assert np.array_equal(
            row.execution_plan.array("global_load"),
            row.base_slot.execution_plan.array("global_load") * row.load_scale_factor,
        )

    receipt = registry.to_manifest()
    assert (
        receipt["package_global_dof_count"],
        receipt["package_element_count"],
        receipt["package_free_dof_count"],
        receipt["package_csr_nnz"],
    ) == (78, 10, 60, 1188)
    assert receipt["claims"]["historical_unit_load_registry_bytes_preserved"]
    assert receipt["claims"]["exact_three_original_scale_derivatives_verified"]
    assert not receipt["claims"]["actual_hip_execution_verified"]
    assert not receipt["claims"]["result_ir_v3_aggregate_verified"]
    assert not receipt["claims"]["commercial_ready"]


def test_registry_resources_are_package_owned_and_generator_is_current(
    registry,
) -> None:
    manifest = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert len({row.model_bytes_sha256 for row in registry.slots}) == 3
    for replay, row in zip(registry.slots, manifest["slots"], strict=True):
        raw = (RESOURCE_DIR / replay.model_resource).read_bytes()
        assert sha256_prefixed(raw) == replay.model_bytes_sha256
        assert row["model_bytes_sha256"] == replay.model_bytes_sha256
        payload = json.loads(raw)
        assert payload["provenance"]["source_ref"] == replay.source_ref
        assert payload["provenance"]["source_sha256"] == sha256_prefixed(
            replay.source_ref.encode("utf-8")
        )


def test_registry_rejects_root_and_model_byte_mutation_before_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = registry_module._read_fixed_resource
    monkeypatch.setattr(
        registry_module,
        "_read_fixed_resource",
        lambda name: (
            original(name) + b" " if name == "registry.v1.json" else original(name)
        ),
    )
    with pytest.raises(HipFgmresHighLoadCompatibilityRegistryV1Error) as root_error:
        registry_module._replay_package_registry()
    assert (
        root_error.value.code == "hip_fgmres_high_load_registry_resource_hash_mismatch"
    )

    monkeypatch.setattr(registry_module, "_read_fixed_resource", original)
    target = registry_module._SPECS[0].model_resource
    monkeypatch.setattr(
        registry_module,
        "_read_fixed_resource",
        lambda name: original(name) + b" " if name == target else original(name),
    )
    with pytest.raises(HipFgmresHighLoadCompatibilityRegistryV1Error) as model_error:
        registry_module._replay_package_registry()
    assert (
        model_error.value.code
        == "hip_fgmres_high_load_registry_model_bytes_hash_mismatch"
    )


def test_registry_schema_rejects_reorder_parent_relabel_and_unknown_fields() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    manifest = json.loads(REGISTRY.read_text(encoding="utf-8"))
    candidates = []
    reordered = copy.deepcopy(manifest)
    reordered["slots"] = list(reversed(reordered["slots"]))
    candidates.append(reordered)
    parent = copy.deepcopy(manifest)
    parent["parent_registry"]["source_registry_mutated"] = True
    candidates.append(parent)
    unknown = copy.deepcopy(manifest)
    unknown["caller_registry_path"] = "/tmp/forged.json"
    candidates.append(unknown)
    for candidate in candidates:
        assert list(validator.iter_errors(candidate))


def test_private_registry_transaction_is_exact_refreshable_and_weak(registry) -> None:
    transaction = registry_module._issue_high_load_registry_transaction_v1(registry)
    assert (
        registry_module._registry_from_high_load_transaction_v1(transaction) is registry
    )
    assert (
        registry_module._refresh_high_load_registry_transaction_v1(transaction)
        is registry
    )
    clone = copy.copy(transaction)
    with pytest.raises(HipFgmresHighLoadCompatibilityRegistryV1Error) as clone_error:
        registry_module._registry_from_high_load_transaction_v1(clone)
    assert clone_error.value.code == (
        "hip_fgmres_high_load_registry_transaction_issuance_unavailable"
    )
    assert "_HighLoadRegistryTransactionV1" not in registry_module.__all__

    def issue_once():
        issued = registry_module._issue_high_load_registry_transaction_v1(registry)
        with registry_module._TRANSACTION_LOCK:
            mint = registry_module._TRANSACTION_ISSUANCES[issued].mint
            size = len(registry_module._TRANSACTION_ISSUANCES)
        return weakref.ref(issued), mint, size

    reference, old_mint, during = issue_once()
    gc.collect()
    assert reference() is None
    assert len(registry_module._TRANSACTION_ISSUANCES) < during
    replacement = registry_module._issue_high_load_registry_transaction_v1(registry)
    with registry_module._TRANSACTION_LOCK:
        assert registry_module._TRANSACTION_ISSUANCES[replacement].mint is not old_mint


def test_registry_result_validator_full_replays_package(registry) -> None:
    assert (
        validate_hip_fgmres_high_load_compatibility_registry_result_v1(registry)
        is registry
    )
