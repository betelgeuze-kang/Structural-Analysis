from __future__ import annotations

from importlib import resources
import inspect
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

from structural_analysis.engine_v2 import (
    HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1,
    HipFgmresFixtureRegistryV1Error,
    attest_hip_fgmres_model_family_coverage_v1,
    load_hip_fgmres_fixture_registry_v1,
)
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_fixture_registry_v1 as registry_module,
)
from structural_analysis.engine_v2.contracts._canonical import sha256_prefixed


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (
    ROOT
    / "src/structural_analysis/schemas"
    / "hip_fgmres_fixture_registry_v1.schema.json"
)
REGISTRY = (
    ROOT
    / "src/structural_analysis/engine_v2/assembly_backend/fixtures"
    / "fgmres_family_v2/registry.v1.json"
)


@pytest.fixture(scope="module")
def replayed_registry():
    return load_hip_fgmres_fixture_registry_v1()


def test_registry_schema_is_strict_and_package_manifest_valid() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    manifest = json.loads(REGISTRY.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)

    assert not list(validator.iter_errors(manifest))
    extra = dict(manifest)
    extra["caller_fixture_path"] = "/tmp/forged.json"
    assert list(validator.iter_errors(extra))
    partial = dict(manifest)
    partial["slots"] = manifest["slots"][:-1]
    assert list(validator.iter_errors(partial))


def test_package_registry_replays_all_ten_exact_slots_and_stays_nonpromoting(
    replayed_registry,
) -> None:
    result = replayed_registry
    receipt = result.to_manifest()

    assert tuple(inspect.signature(load_hip_fgmres_fixture_registry_v1).parameters) == ()
    assert tuple(row.slot_id for row in result.slots) == (
        HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1
    )
    assert receipt["registered_slot_count"] == 10
    assert receipt["claims"]["package_fixture_registry_replayed"]
    assert receipt["claims"]["fixed_suite_registration_complete"]
    for claim in (
        "signed_evidence",
        "promotion_eligible",
        "full_model_family_parity_verified",
        "multiarchitecture_parity_verified",
        "same_process_actual_two_isa_verified",
        "result_ir_verified",
        "iteration_host_copy_zero_verified",
        "speedup_verified",
        "end_to_end_o_n_verified",
        "commercial_ready",
    ):
        assert not receipt["claims"][claim]
    assert len({row.slot_registration_hash for row in result.slots}) == 10
    assert len({row.case_fingerprint for row in result.slots}) == 10


def test_registry_preserves_exact_recurrence_semantics(replayed_registry) -> None:
    result = replayed_registry
    iterations = tuple(row.cpu_result.iteration_count for row in result.slots)
    assert iterations == (1, 2, 2, 1, 5, 2, 1, 0, 5, 4)

    initial = result.slot("recurrence_initial_or_early_terminal")
    assert initial.cpu_result.termination_code == "converged_initial_true_residual"
    assert initial.cpu_result.history == ()

    partial = result.slot("recurrence_later_restart_partial_final_cycle")
    full = result.slot("recurrence_exact_full_final_cycle_guard")
    assert partial.model_bytes_sha256 == full.model_bytes_sha256
    assert partial.model.content_hash == full.model.content_hash
    assert partial.execution_plan.plan_hash == full.execution_plan.plan_hash
    assert partial.policy.policy_hash != full.policy.policy_hash
    assert partial.cpu_result.result_hash != full.cpu_result.result_hash
    assert [row.arnoldi_step_count for row in partial.cpu_result.history] == [2, 2, 1]
    assert [row.arnoldi_step_count for row in full.cpu_result.history] == [2, 2]


def test_registry_resources_are_wheel_owned_and_raw_hash_bound(
    replayed_registry,
) -> None:
    package = resources.files(
        "structural_analysis.engine_v2.assembly_backend.fixtures.fgmres_family_v2"
    )
    registry_raw = package.joinpath("registry.v1.json").read_bytes()
    assert sha256_prefixed(registry_raw) == replayed_registry.registry_bytes_sha256
    for row in replayed_registry.slots:
        raw = package.joinpath(row.model_resource).read_bytes()
        assert sha256_prefixed(raw) == row.model_bytes_sha256

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"engine_v2/assembly_backend/fixtures/fgmres_family_v2/*.json"' in pyproject


def test_registry_root_byte_mutation_fails_before_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = registry_module._read_fixed_resource
    raw = original("registry.v1.json")
    mutated = raw.replace(
        b'"registration_target_slot_count": 10',
        b'"registration_target_slot_count": 11',
        1,
    )
    assert mutated != raw

    monkeypatch.setattr(
        registry_module,
        "_read_fixed_resource",
        lambda name: mutated if name == "registry.v1.json" else original(name),
    )
    with pytest.raises(HipFgmresFixtureRegistryV1Error) as error:
        registry_module._replay_package_registry()
    assert error.value.code == (
        "hip_fgmres_fixture_registry_resource_hash_mismatch"
    )


def test_model_resource_byte_mutation_fails_before_model_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = registry_module._read_fixed_resource
    target = "frame_single_axial.model.json"
    mutated = original(target) + b" "

    monkeypatch.setattr(
        registry_module,
        "_read_fixed_resource",
        lambda name: mutated if name == target else original(name),
    )
    with pytest.raises(HipFgmresFixtureRegistryV1Error) as error:
        registry_module._replay_package_registry()
    assert error.value.code == (
        "hip_fgmres_fixture_registry_model_bytes_hash_mismatch"
    )


@pytest.mark.parametrize(
    ("raw", "expected_code"),
    [
        (b'{"a":1,"a":2}', "hip_fgmres_fixture_registry_json_duplicate_key"),
        (b"\xef\xbb\xbf{}", "hip_fgmres_fixture_registry_json_bom_forbidden"),
        (b'{"a":1e999}', "hip_fgmres_fixture_registry_json_nonfinite"),
        (b'{"a":NaN}', "hip_fgmres_fixture_registry_json_invalid"),
    ],
)
def test_strict_snapshot_parser_rejects_ambiguous_json(
    raw: bytes,
    expected_code: str,
) -> None:
    with pytest.raises(HipFgmresFixtureRegistryV1Error) as error:
        registry_module._parse_strict_object(raw, path="/test")
    assert error.value.code == expected_code


def test_historical_family_v1_remains_frozen_at_zero_registered_slots() -> None:
    historical = attest_hip_fgmres_model_family_coverage_v1(())
    assert historical.receipt.suite.registered_slot_ids == ()
    assert historical.receipt.coverage.registered_slot_definition_count == 0
    assert historical.receipt.coverage.covered_matrix_cell_count == 0
    assert not historical.receipt.claims.fixed_suite_slot_registration_complete
    assert not historical.receipt.claims.full_model_family_parity_verified
