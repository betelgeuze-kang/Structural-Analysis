from __future__ import annotations

from dataclasses import replace

import pytest

from structural_analysis.engine_v2.contracts.material_state_bundle import (
    MATERIAL_STATE_BUNDLE_AUTHORITY_PROFILE,
    MaterialStateBundleError,
    MaterialStateInput,
    commit_trial_material_state_bundle,
    create_initial_material_state_bundle,
    open_trial_material_state_bundle,
    rollback_trial_material_state_bundle,
    validate_material_state_bundle,
    validate_material_state_bundle_manifest,
    validate_material_state_entry_bytes,
)


MODEL_HASH = "sha256:" + "1" * 64
PLAN_HASH = "sha256:" + "2" * 64
STATE_E0_HASH = "sha256:" + "3" * 64
STATE_TRIAL_HASH = "sha256:" + "4" * 64
STATE_COMMITTED_HASH = "sha256:" + "5" * 64


def _initial_inputs() -> tuple[MaterialStateInput, ...]:
    return (
        MaterialStateInput(
            entity_id="element.e1",
            integration_point_id="ip.0",
            material_type_id="steel.combined-hardening",
            material_schema_version="uniaxial-combined-hardening-state.v1",
            state_bytes=b"steel-state-initial",
            artifact_uri="artifact://material/e1/ip0/state.bin",
        ),
        MaterialStateInput(
            entity_id="element.e1",
            integration_point_id="ip.1",
            material_type_id="concrete.damage",
            material_schema_version="concrete-damage-state.v1",
            state_bytes=b"concrete-state-initial",
            artifact_uri="artifact://material/e1/ip1/state.bin",
        ),
    )


def _initial_bundle():
    return create_initial_material_state_bundle(
        bundle_id="material-state.initial",
        model_ir_content_hash=MODEL_HASH,
        execution_plan_hash=PLAN_HASH,
        solver_state_hash=STATE_E0_HASH,
        entries=_initial_inputs(),
    )


def _trial_inputs() -> tuple[MaterialStateInput, ...]:
    return (
        MaterialStateInput(
            entity_id="element.e1",
            integration_point_id="ip.0",
            material_type_id="steel.combined-hardening",
            material_schema_version="uniaxial-combined-hardening-state.v1",
            state_bytes=b"steel-state-yielded",
            artifact_uri="artifact://material/e1/ip0/trial.bin",
        ),
        MaterialStateInput(
            entity_id="element.e1",
            integration_point_id="ip.1",
            material_type_id="concrete.damage",
            material_schema_version="concrete-damage-state.v1",
            state_bytes=b"concrete-state-damaged",
            artifact_uri="artifact://material/e1/ip1/trial.bin",
        ),
    )


def test_initial_trial_commit_and_exact_rollback_lifecycle() -> None:
    initial = _initial_bundle()
    assert initial.role == "committed"
    assert initial.epoch == 0
    assert initial.parent_bundle_hash is None
    assert initial.authority_profile == MATERIAL_STATE_BUNDLE_AUTHORITY_PROFILE
    assert initial.entry_count == 2
    assert all(row.parent_state_data_hash is None for row in initial.entries)

    trial = open_trial_material_state_bundle(
        initial,
        solver_state_hash=STATE_TRIAL_HASH,
        entries=_trial_inputs(),
    )
    assert trial.role == "trial"
    assert trial.epoch == 1
    assert trial.parent_bundle_hash == initial.bundle_hash
    assert [row.parent_state_data_hash for row in trial.entries] == [
        row.data_hash for row in initial.entries
    ]
    assert rollback_trial_material_state_bundle(initial, trial) is initial

    committed = commit_trial_material_state_bundle(
        initial,
        trial,
        solver_state_hash=STATE_COMMITTED_HASH,
    )
    assert committed.role == "committed"
    assert committed.epoch == 1
    assert committed.parent_bundle_hash == trial.bundle_hash
    assert committed.solver_state_hash == STATE_COMMITTED_HASH
    assert tuple(committed.state_bytes(index) for index in range(2)) == tuple(
        trial.state_bytes(index) for index in range(2)
    )
    validate_material_state_bundle(committed)
    validate_material_state_bundle_manifest(committed.to_manifest())


def test_default_lifecycle_bundle_ids_remain_bounded_across_epochs() -> None:
    accepted = create_initial_material_state_bundle(
        bundle_id="B" + "x" * 127,
        model_ir_content_hash=MODEL_HASH,
        execution_plan_hash=PLAN_HASH,
        solver_state_hash=STATE_E0_HASH,
        entries=(_initial_inputs()[0],),
    )
    observed_ids = {accepted.bundle_id}

    for epoch in range(1, 9):
        trial = open_trial_material_state_bundle(
            accepted,
            solver_state_hash=f"sha256:{epoch:064x}",
            entries=(
                MaterialStateInput(
                    entity_id="element.e1",
                    integration_point_id="ip.0",
                    material_type_id="steel.combined-hardening",
                    material_schema_version=("uniaxial-combined-hardening-state.v1"),
                    state_bytes=f"steel-state-{epoch}".encode(),
                ),
            ),
        )
        committed = commit_trial_material_state_bundle(
            accepted,
            trial,
            solver_state_hash=f"sha256:{epoch + 32:064x}",
        )

        assert len(trial.bundle_id) <= 128
        assert len(committed.bundle_id) <= 128
        assert trial.bundle_id not in observed_ids
        assert committed.bundle_id not in observed_ids
        observed_ids.update((trial.bundle_id, committed.bundle_id))
        accepted = committed


def test_bundle_manifest_is_descriptor_only_and_replayable() -> None:
    bundle = _initial_bundle()
    manifest = bundle.to_manifest()
    assert "_state_bytes" not in manifest
    assert "state_bytes" not in manifest["entries"][0]
    assert manifest["total_byte_length"] == sum(
        row["byte_length"] for row in manifest["entries"]
    )
    assert validate_material_state_bundle_manifest(manifest) == manifest


def test_external_entry_bytes_are_hash_and_length_checked() -> None:
    bundle = _initial_bundle()
    assert (
        validate_material_state_entry_bytes(
            bundle,
            index=0,
            state_bytes=b"steel-state-initial",
        )
        == b"steel-state-initial"
    )
    with pytest.raises(
        MaterialStateBundleError,
        match="material_state_data_hash_mismatch",
    ):
        validate_material_state_entry_bytes(
            bundle,
            index=0,
            state_bytes=b"steel-state-invalid",
        )
    with pytest.raises(
        MaterialStateBundleError,
        match="material_state_index_out_of_range",
    ):
        validate_material_state_entry_bytes(
            bundle,
            index=2,
            state_bytes=b"unused",
        )


def test_trial_identity_and_parent_hash_are_fail_closed() -> None:
    initial = _initial_bundle()
    reordered = tuple(reversed(_trial_inputs()))
    with pytest.raises(
        MaterialStateBundleError,
        match="material_state_identity_mismatch",
    ):
        open_trial_material_state_bundle(
            initial,
            solver_state_hash=STATE_TRIAL_HASH,
            entries=reordered,
        )

    first, second = _trial_inputs()
    stale_parent = replace(
        first,
        parent_state_data_hash="sha256:" + "9" * 64,
    )
    with pytest.raises(
        MaterialStateBundleError,
        match="material_state_entry_parent_mismatch",
    ):
        open_trial_material_state_bundle(
            initial,
            solver_state_hash=STATE_TRIAL_HASH,
            entries=(stale_parent, second),
        )


def test_trial_cannot_be_opened_from_another_trial() -> None:
    initial = _initial_bundle()
    trial = open_trial_material_state_bundle(
        initial,
        solver_state_hash=STATE_TRIAL_HASH,
        entries=_trial_inputs(),
    )
    with pytest.raises(
        MaterialStateBundleError,
        match="accepted_material_bundle_role_invalid",
    ):
        open_trial_material_state_bundle(
            trial,
            solver_state_hash=STATE_COMMITTED_HASH,
            entries=_trial_inputs(),
        )


def test_mutable_or_empty_state_artifacts_are_rejected() -> None:
    first, second = _initial_inputs()
    for invalid in (bytearray(b"mutable"), b""):
        with pytest.raises(
            MaterialStateBundleError,
            match="material_state_bytes_invalid",
        ):
            create_initial_material_state_bundle(
                bundle_id="material-state.invalid",
                model_ir_content_hash=MODEL_HASH,
                execution_plan_hash=PLAN_HASH,
                solver_state_hash=STATE_E0_HASH,
                entries=(replace(first, state_bytes=invalid), second),
            )


def test_retained_bytes_and_descriptors_cannot_be_coherently_tampered() -> None:
    bundle = _initial_bundle()
    tampered_descriptor = replace(
        bundle.entries[0],
        data_hash="sha256:" + "8" * 64,
    )
    tampered = replace(
        bundle,
        entries=(tampered_descriptor, bundle.entries[1]),
    )
    with pytest.raises(
        MaterialStateBundleError,
        match="material_state_descriptor_mismatch",
    ):
        validate_material_state_bundle(tampered)

    tampered_bytes = replace(
        bundle,
        _state_bytes=(b"different-state-bytes", bundle.state_bytes(1)),
    )
    with pytest.raises(
        MaterialStateBundleError,
        match="material_state_descriptor_mismatch",
    ):
        validate_material_state_bundle(tampered_bytes)


def test_manifest_rejects_unknown_fields_integral_floats_and_hash_tamper() -> None:
    manifest = _initial_bundle().to_manifest()

    unknown = dict(manifest)
    unknown["result_authority"] = True
    with pytest.raises(
        MaterialStateBundleError,
        match="material_state_manifest_schema_invalid",
    ):
        validate_material_state_bundle_manifest(unknown)

    integral_float = dict(manifest)
    integral_float["epoch"] = 0.0
    with pytest.raises(
        MaterialStateBundleError,
        match="material_state_manifest_schema_invalid",
    ):
        validate_material_state_bundle_manifest(integral_float)

    content_tamper = dict(manifest)
    content_tamper["entries"] = [dict(row) for row in manifest["entries"]]
    content_tamper["entries"][0]["content_hash"] = "sha256:" + "7" * 64
    with pytest.raises(
        MaterialStateBundleError,
        match="material_state_entry_content_hash_mismatch",
    ):
        validate_material_state_bundle_manifest(content_tamper)

    bundle_tamper = dict(manifest)
    bundle_tamper["bundle_hash"] = "sha256:" + "6" * 64
    with pytest.raises(
        MaterialStateBundleError,
        match="material_state_bundle_hash_mismatch",
    ):
        validate_material_state_bundle_manifest(bundle_tamper)


def test_bundle_authority_profile_cannot_be_promoted() -> None:
    bundle = _initial_bundle()
    promoted = replace(bundle, authority_profile="authoritative_engineering_result")
    with pytest.raises(
        MaterialStateBundleError,
        match="material_state_authority_profile_invalid",
    ):
        validate_material_state_bundle(promoted)
