from __future__ import annotations

import copy
from copy import deepcopy
import gc
from importlib import resources
import inspect
import json
from pathlib import Path
import weakref

from jsonschema import Draft202012Validator
import numpy as np
import pytest

from structural_analysis.engine_v2.assembly_backend import (
    fgmres_all_converged_fixture_registry_v1 as registry_module,
)
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_fixture_registry_v1 as termination_registry_module,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_all_converged_fixture_registry_v1 import (
    HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1,
    HipFgmresAllConvergedFixtureRegistryV1Error,
    load_hip_fgmres_all_converged_fixture_registry_v1,
    validate_hip_fgmres_all_converged_fixture_registry_result_v1,
)
from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    sha256_prefixed,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (
    ROOT
    / "src/structural_analysis/schemas"
    / "hip_fgmres_all_converged_fixture_registry_v1.schema.json"
)
RESOURCE_DIR = (
    ROOT
    / "src/structural_analysis/engine_v2/assembly_backend/fixtures"
    / "fgmres_all_converged_v1"
)
REGISTRY = RESOURCE_DIR / "registry.v1.json"
TERMINATION_REGISTRY = (
    ROOT
    / "src/structural_analysis/engine_v2/assembly_backend/fixtures"
    / "fgmres_family_v2/registry.v1.json"
)


@pytest.fixture(scope="module")
def replayed_registry():
    return load_hip_fgmres_all_converged_fixture_registry_v1()


def _manifest() -> dict[str, object]:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def _install_manifest(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, object],
) -> None:
    candidate = deepcopy(payload)
    hash_payload = dict(candidate)
    hash_payload.pop("registry_hash", None)
    candidate["registry_hash"] = canonical_hash(hash_payload)
    raw = (
        json.dumps(candidate, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    original = registry_module._read_fixed_resource
    monkeypatch.setattr(
        registry_module,
        "_REGISTRY_RESOURCE_BYTES_SHA256",
        sha256_prefixed(raw),
    )
    monkeypatch.setattr(
        registry_module,
        "_read_fixed_resource",
        lambda name: raw if name == "registry.v1.json" else original(name),
    )


def test_schema_is_strict_and_package_manifest_valid() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    manifest = _manifest()
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)

    assert schema["const"] == manifest
    assert not list(validator.iter_errors(manifest))
    slot_schemas = schema["properties"]["slots"]["prefixItems"]
    assert schema["properties"]["registry_hash"]["const"] == manifest["registry_hash"]
    expected_hash_keys = tuple(
        key for key in manifest["slots"][0]["expected"] if key.endswith("_hash")
    )
    for slot_schema, slot in zip(
        slot_schemas,
        manifest["slots"],
        strict=True,
    ):
        pinned = slot_schema["properties"]
        assert pinned["slot_id"]["const"] == slot["slot_id"]
        assert pinned["model_resource"]["const"] == slot["model_resource"]
        for key in (
            "model_bytes_sha256",
            "case_fingerprint",
            "slot_registration_hash",
        ):
            assert pinned[key]["const"] == slot[key]
        expected_pinned = pinned["expected"]["properties"]
        for key in expected_hash_keys:
            assert expected_pinned[key]["const"] == slot["expected"][key]

    zero_hash = "sha256:" + "0" * 64
    zero_forged = deepcopy(manifest)
    zero_forged["registry_hash"] = zero_hash
    for slot in zero_forged["slots"]:
        slot["model_bytes_sha256"] = zero_hash
        slot["case_fingerprint"] = zero_hash
        slot["slot_registration_hash"] = zero_hash
        for key in expected_hash_keys:
            slot["expected"][key] = zero_hash
    assert list(validator.iter_errors(zero_forged))

    semantic_forged = deepcopy(manifest)
    semantic_forged["slots"][0]["semantic_contract"]["node_count"] += 1
    policy_forged = deepcopy(manifest)
    policy_forged["slots"][0]["policy_parameters"]["max_iterations"] += 1
    count_forged = deepcopy(manifest)
    count_forged["slots"][0]["expected"]["cpu_iteration_count"] += 1
    termination_forged = deepcopy(manifest)
    termination_forged["slots"][0]["expected"]["cpu_termination_code"] = (
        "converged_tolerance"
    )
    for forged in (
        semantic_forged,
        policy_forged,
        count_forged,
        termination_forged,
    ):
        assert any(
            error.validator == "const" and not error.absolute_path
            for error in validator.iter_errors(forged)
        )

    extra_root = dict(manifest)
    extra_root["caller_fixture_path"] = "/tmp/forged.json"
    assert list(validator.iter_errors(extra_root))
    extra_slot = deepcopy(manifest)
    extra_slot["slots"][0]["caller_expected_status"] = "converged"
    assert list(validator.iter_errors(extra_slot))
    reordered_required = deepcopy(manifest)
    reordered_required["required_slot_ids"] = list(
        reversed(reordered_required["required_slot_ids"])
    )
    assert list(validator.iter_errors(reordered_required))


@pytest.mark.parametrize(
    "mutate",
    (
        lambda rows: rows.__setitem__(1, deepcopy(rows[0])),
        lambda rows: rows.__setitem__(slice(0, 2), [rows[1], rows[0]]),
        lambda rows: rows[0].__setitem__(
            "model_bytes_sha256",
            "sha256:" + "0" * 64,
        ),
        lambda rows: rows[0]["expected"].__setitem__(
            "model_ir_content_hash",
            "sha256:" + "0" * 64,
        ),
        lambda rows: rows[0]["expected"].__setitem__(
            "execution_plan_hash",
            "sha256:" + "0" * 64,
        ),
    ),
    ids=(
        "duplicate_slot",
        "reordered_slots",
        "raw_fixture_hash",
        "model_ir_hash",
        "execution_plan_hash",
    ),
)
def test_schema_rejects_duplicate_reordered_and_hash_mutated_slots(mutate) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    forged = _manifest()
    mutate(forged["slots"])

    errors = list(validator.iter_errors(forged))

    assert errors
    assert any(tuple(error.absolute_path)[:1] == ("slots",) for error in errors)


def test_public_loader_replays_ten_unique_converged_slots_and_stays_nonpromoting(
    replayed_registry,
) -> None:
    result = replayed_registry
    receipt = result.to_manifest()

    assert (
        tuple(
            inspect.signature(
                load_hip_fgmres_all_converged_fixture_registry_v1
            ).parameters
        )
        == ()
    )
    assert tuple(row.slot_id for row in result.slots) == (
        HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1
    )
    assert receipt["registered_slot_count"] == 10
    assert receipt["unique_model_bytes_hash_count"] == 10
    assert receipt["unique_model_ir_content_hash_count"] == 10
    assert receipt["unique_execution_plan_hash_count"] == 10
    assert receipt["nontrivial_solution_case_count"] == 9
    assert receipt["zero_free_rhs_edge_count"] == 1
    for claim in (
        "package_all_converged_fixture_registry_replayed",
        "fixed_suite_registration_complete",
        "ten_unique_model_ir_verified",
        "all_cpu_reference_converged",
        "all_solver_tolerance_passed",
        "all_authoritative_plan_tolerance_passed",
    ):
        assert receipt["claims"][claim]
    for claim in (
        "actual_hip_execution_verified",
        "result_ir_verified",
        "signed_evidence",
        "promotion_eligible",
        "full_model_family_parity_verified",
        "multiarchitecture_parity_verified",
        "same_process_actual_two_isa_verified",
        "iteration_host_copy_zero_verified",
        "speedup_verified",
        "end_to_end_o_n_verified",
        "commercial_ready",
    ):
        assert not receipt["claims"][claim]


def test_all_slots_use_realistic_tolerance_and_match_independent_dense_oracle(
    replayed_registry,
) -> None:
    expected_iterations = (1, 2, 2, 1, 6, 2, 1, 0, 4, 5)
    assert (
        tuple(row.cpu_result.iteration_count for row in replayed_registry.slots)
        == expected_iterations
    )
    for row in replayed_registry.slots:
        assert row.policy.relative_tolerance == 1.0e-12
        assert row.execution_plan.residual_tolerance == 1.0e-10
        assert row.cpu_result.status == "converged"
        assert row.cpu_result.solver_tolerance_passed
        assert row.cpu_result.authoritative_plan_tolerance_passed
        assert np.allclose(
            row.cpu_result.reduced_solution,
            row.direct_solution,
            rtol=1.0e-10,
            atol=1.0e-12,
        )
        assert np.max(np.abs(row.direct_residual), initial=0.0) <= 1.0e-7


def test_registry_preserves_one_explicit_zero_free_rhs_edge(
    replayed_registry,
) -> None:
    edge = replayed_registry.slot("solution_frame_zero_free_rhs_edge")
    assert edge.cpu_result.termination_code == "converged_initial_true_residual"
    assert edge.cpu_result.iteration_count == 0
    assert edge.cpu_result.history == ()
    assert (
        np.count_nonzero(
            edge.execution_plan.array("global_load")[
                edge.execution_plan.array("free_dofs")
            ]
        )
        == 0
    )


def test_registry_resources_are_package_owned_and_raw_hash_bound(
    replayed_registry,
) -> None:
    package = resources.files(
        "structural_analysis.engine_v2.assembly_backend.fixtures."
        "fgmres_all_converged_v1"
    )
    registry_raw = package.joinpath("registry.v1.json").read_bytes()
    assert sha256_prefixed(registry_raw) == replayed_registry.registry_bytes_sha256
    assert len({row.model_bytes_sha256 for row in replayed_registry.slots}) == 10
    for row in replayed_registry.slots:
        raw = package.joinpath(row.model_resource).read_bytes()
        assert sha256_prefixed(raw) == row.model_bytes_sha256


def test_private_registry_transaction_rejects_clones_transplants_and_collects(
    replayed_registry,
) -> None:
    transaction = registry_module._issue_fixed_registry_replay_transaction_v1(
        replayed_registry
    )
    assert (
        registry_module._registry_from_fixed_replay_transaction_v1(transaction)
        is replayed_registry
    )
    assert type(transaction.resource_bindings) is tuple
    with pytest.raises(TypeError):
        transaction.resource_bindings[0] = transaction.resource_bindings[0]

    clone = copy.copy(transaction)
    with pytest.raises(
        HipFgmresAllConvergedFixtureRegistryV1Error,
        match="transaction_issuance_unavailable",
    ):
        registry_module._registry_from_fixed_replay_transaction_v1(clone)

    direct = registry_module._FixedRegistryReplayTransactionV1(
        registry=transaction.registry,
        registry_snapshot_hash=transaction.registry_snapshot_hash,
        resource_bindings=transaction.resource_bindings,
        mint=transaction.mint,
    )
    with pytest.raises(
        HipFgmresAllConvergedFixtureRegistryV1Error,
        match="transaction_issuance_unavailable",
    ):
        registry_module._registry_from_fixed_replay_transaction_v1(direct)

    with registry_module._TRANSACTION_LOCK:
        original_issuance = registry_module._TRANSACTION_ISSUANCES[transaction]
        registry_module._TRANSACTION_ISSUANCES[clone] = original_issuance
    try:
        with pytest.raises(
            HipFgmresAllConvergedFixtureRegistryV1Error,
            match="transaction_binding_mismatch",
        ):
            registry_module._registry_from_fixed_replay_transaction_v1(clone)
    finally:
        with registry_module._TRANSACTION_LOCK:
            registry_module._TRANSACTION_ISSUANCES.pop(clone, None)

    original_bindings = transaction.resource_bindings
    object.__setattr__(
        transaction,
        "resource_bindings",
        tuple(reversed(original_bindings)),
    )
    try:
        with pytest.raises(
            HipFgmresAllConvergedFixtureRegistryV1Error,
            match="transaction_binding_mismatch",
        ):
            registry_module._registry_from_fixed_replay_transaction_v1(transaction)
    finally:
        object.__setattr__(transaction, "resource_bindings", original_bindings)

    for private_name in (
        "_FixedRegistryReplayTransactionV1",
        "_issue_fixed_registry_replay_transaction_v1",
        "_refresh_fixed_registry_replay_transaction_v1",
    ):
        assert private_name not in registry_module.__all__

    def issue_once():
        issued = registry_module._issue_fixed_registry_replay_transaction_v1(
            replayed_registry
        )
        with registry_module._TRANSACTION_LOCK:
            mint = registry_module._TRANSACTION_ISSUANCES[issued].mint
            size = len(registry_module._TRANSACTION_ISSUANCES)
        return weakref.ref(issued), mint, size

    reference, old_mint, during = issue_once()
    gc.collect()
    assert reference() is None
    assert len(registry_module._TRANSACTION_ISSUANCES) < during
    replacement = registry_module._issue_fixed_registry_replay_transaction_v1(
        replayed_registry
    )
    with registry_module._TRANSACTION_LOCK:
        assert registry_module._TRANSACTION_ISSUANCES[replacement].mint is not old_mint


def test_nine_resources_preserve_source_model_bytes_and_tenth_is_physical_new_model() -> (
    None
):
    source_dir = (
        ROOT
        / "src/structural_analysis/engine_v2/assembly_backend/fixtures"
        / "fgmres_family_v2"
    )
    copied = {
        "solution_frame_single_axial.model.json": "frame_single_axial.model.json",
        "solution_frame_single_weak_axis_bending.model.json": (
            "frame_single_weak_axis_bending.model.json"
        ),
        "solution_frame_single_strong_axis_bending.model.json": (
            "frame_single_strong_axis_bending.model.json"
        ),
        "solution_frame_single_torsion.model.json": "frame_single_torsion.model.json",
        "solution_frame_single_rotated_axis_bending.model.json": (
            "frame_single_rotated_local_axis_bending.model.json"
        ),
        "solution_frame_serial_two_span_axial.model.json": (
            "frame_serial_later_column.model.json"
        ),
        "solution_truss_single_axial.model.json": "truss_single_axial.model.json",
        "solution_frame_zero_free_rhs_edge.model.json": (
            "recurrence_initial_or_early_terminal.model.json"
        ),
        "solution_frame_serial_four_span_axial.model.json": (
            "recurrence_later_restart_partial_final_cycle.model.json"
        ),
    }
    for destination, source in copied.items():
        assert (RESOURCE_DIR / destination).read_bytes() == (
            source_dir / source
        ).read_bytes()
    new_model = json.loads(
        (RESOURCE_DIR / "solution_frame_serial_five_span_axial.model.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(new_model["nodes"]) == 6
    assert len(new_model["elements"]) == 5
    assert new_model["elements"][-1]["node_ids"] == ["N5", "N6"]
    assert new_model["load_patterns"][0]["nodal_loads"][0]["node_id"] == "N6"


def test_registry_root_byte_mutation_fails_before_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = registry_module._read_fixed_resource
    mutated = original("registry.v1.json") + b" "
    monkeypatch.setattr(
        registry_module,
        "_read_fixed_resource",
        lambda name: mutated if name == "registry.v1.json" else original(name),
    )
    monkeypatch.setattr(
        registry_module,
        "_parse_strict_object",
        lambda *_args, **_kwargs: pytest.fail("parser must not be reached"),
    )
    with pytest.raises(HipFgmresAllConvergedFixtureRegistryV1Error) as error:
        registry_module._replay_package_registry()
    assert error.value.code == (
        "hip_fgmres_all_converged_registry_resource_hash_mismatch"
    )


def test_model_resource_byte_mutation_fails_before_model_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = registry_module._read_fixed_resource
    target = "solution_frame_single_axial.model.json"
    mutated = original(target) + b" "
    monkeypatch.setattr(
        registry_module,
        "_read_fixed_resource",
        lambda name: mutated if name == target else original(name),
    )
    monkeypatch.setattr(
        registry_module,
        "parse_model_ir_v2",
        lambda *_args, **_kwargs: pytest.fail("ModelIR parser must not be reached"),
    )
    with pytest.raises(HipFgmresAllConvergedFixtureRegistryV1Error) as error:
        registry_module._replay_package_registry()
    assert error.value.code == (
        "hip_fgmres_all_converged_registry_model_bytes_hash_mismatch"
    )


@pytest.mark.parametrize(
    ("raw", "expected_code"),
    [
        (b'{"a":1,"a":2}', "hip_fgmres_all_converged_registry_json_duplicate_key"),
        (b"\xef\xbb\xbf{}", "hip_fgmres_all_converged_registry_json_bom_forbidden"),
        (b'{"a":1e999}', "hip_fgmres_all_converged_registry_json_nonfinite"),
        (b'{"a":NaN}', "hip_fgmres_all_converged_registry_json_invalid"),
    ],
)
def test_strict_parser_translates_ambiguous_json_into_new_error_boundary(
    raw: bytes,
    expected_code: str,
) -> None:
    with pytest.raises(HipFgmresAllConvergedFixtureRegistryV1Error) as error:
        registry_module._parse_strict_object(raw, path="/test")
    assert error.value.code == expected_code


def test_reordered_slots_fail_closed_after_valid_raw_and_content_rehash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()
    manifest["slots"] = list(reversed(manifest["slots"]))
    _install_manifest(monkeypatch, manifest)
    with pytest.raises(HipFgmresAllConvergedFixtureRegistryV1Error) as error:
        registry_module._replay_package_registry()
    assert error.value.code == (
        "hip_fgmres_all_converged_registry_schema_validation_failed"
    )


@pytest.mark.parametrize(
    ("key", "nested"),
    [
        ("slot_registration_hash", None),
        ("case_fingerprint", None),
        ("model_bytes_sha256", None),
        ("model_ir_content_hash", "expected"),
        ("execution_plan_hash", "expected"),
    ],
)
def test_duplicate_registration_case_model_and_plan_hashes_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    key: str,
    nested: str | None,
) -> None:
    manifest = _manifest()
    rows = manifest["slots"]
    if nested is None:
        rows[1][key] = rows[0][key]
    else:
        rows[1][nested][key] = rows[0][nested][key]
    _install_manifest(monkeypatch, manifest)
    with pytest.raises(HipFgmresAllConvergedFixtureRegistryV1Error) as error:
        registry_module._replay_package_registry()
    assert error.value.code == (
        "hip_fgmres_all_converged_registry_schema_validation_failed"
    )


def test_result_validator_replays_the_whole_package_once(replayed_registry) -> None:
    assert (
        validate_hip_fgmres_all_converged_fixture_registry_result_v1(replayed_registry)
        is replayed_registry
    )


def test_result_validator_rejects_foreign_type_before_replay() -> None:
    with pytest.raises(HipFgmresAllConvergedFixtureRegistryV1Error) as error:
        validate_hip_fgmres_all_converged_fixture_registry_result_v1(object())
    assert error.value.code == "hip_fgmres_all_converged_registry_result_type_invalid"


def test_historical_termination_registry_bytes_and_slot_contract_remain_frozen() -> (
    None
):
    historical_hash = (
        "sha256:bc12d11a15d23f2768e4c27e5f8449f88d26453f9579ebb741861a3176eae2fa"
    )
    assert sha256_prefixed(TERMINATION_REGISTRY.read_bytes()) == historical_hash
    assert (
        termination_registry_module._REGISTRY_RESOURCE_BYTES_SHA256 == historical_hash
    )
    assert termination_registry_module.HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1[
        -2:
    ] == (
        "recurrence_later_restart_partial_final_cycle",
        "recurrence_exact_full_final_cycle_guard",
    )
