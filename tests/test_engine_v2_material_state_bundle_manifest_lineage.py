from __future__ import annotations

from copy import deepcopy

import pytest

from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.contracts.material_state_bundle import (
    MaterialStateBundleError,
    MaterialStateInput,
    create_initial_material_state_bundle,
    open_trial_material_state_bundle,
    validate_material_state_bundle_manifest,
)


MODEL_HASH = "sha256:" + "1" * 64
PLAN_HASH = "sha256:" + "2" * 64
STATE_INITIAL_HASH = "sha256:" + "3" * 64
STATE_TRIAL_HASH = "sha256:" + "4" * 64


def _initial_manifest() -> dict:
    bundle = create_initial_material_state_bundle(
        bundle_id="material-state.initial",
        model_ir_content_hash=MODEL_HASH,
        execution_plan_hash=PLAN_HASH,
        solver_state_hash=STATE_INITIAL_HASH,
        entries=(
            MaterialStateInput(
                entity_id="element.e1",
                integration_point_id="ip.0",
                material_type_id="steel.combined-hardening",
                material_schema_version="steel-state.v1",
                state_bytes=b"initial-state",
            ),
        ),
    )
    return bundle.to_manifest()


def _trial_manifest() -> dict:
    initial = create_initial_material_state_bundle(
        bundle_id="material-state.initial",
        model_ir_content_hash=MODEL_HASH,
        execution_plan_hash=PLAN_HASH,
        solver_state_hash=STATE_INITIAL_HASH,
        entries=(
            MaterialStateInput(
                entity_id="element.e1",
                integration_point_id="ip.0",
                material_type_id="steel.combined-hardening",
                material_schema_version="steel-state.v1",
                state_bytes=b"initial-state",
            ),
        ),
    )
    trial = open_trial_material_state_bundle(
        initial,
        solver_state_hash=STATE_TRIAL_HASH,
        entries=(
            MaterialStateInput(
                entity_id="element.e1",
                integration_point_id="ip.0",
                material_type_id="steel.combined-hardening",
                material_schema_version="steel-state.v1",
                state_bytes=b"trial-state",
            ),
        ),
    )
    return trial.to_manifest()


def _rehash(manifest: dict) -> dict:
    payload = deepcopy(manifest)
    for entry in payload["entries"]:
        unsigned = dict(entry)
        unsigned.pop("content_hash", None)
        entry["content_hash"] = canonical_hash(unsigned)
    payload["integration_point_order_hash"] = canonical_hash(
        [
            {
                "index": entry["index"],
                "entity_id": entry["entity_id"],
                "integration_point_id": entry["integration_point_id"],
                "material_type_id": entry["material_type_id"],
                "material_schema_version": entry["material_schema_version"],
            }
            for entry in payload["entries"]
        ]
    )
    unsigned_bundle = dict(payload)
    unsigned_bundle.pop("bundle_hash", None)
    payload["bundle_hash"] = canonical_hash(unsigned_bundle)
    return payload


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload.update(
            {
                "role": "trial",
                "parent_bundle_hash": "sha256:" + "5" * 64,
            }
        ),
        lambda payload: payload.update(
            {
                "epoch": 1,
                "parent_bundle_hash": None,
            }
        ),
        lambda payload: payload["entries"][0].update(
            {"parent_state_data_hash": "sha256:" + "6" * 64}
        ),
    ],
)
def test_coherently_rehashed_initial_lifecycle_tamper_is_rejected(mutator) -> None:
    manifest = _initial_manifest()
    mutator(manifest)
    tampered = _rehash(manifest)
    with pytest.raises(
        MaterialStateBundleError,
        match="material_state_manifest_schema_invalid",
    ):
        validate_material_state_bundle_manifest(tampered)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload.update({"epoch": 0}),
        lambda payload: payload.update({"parent_bundle_hash": None}),
        lambda payload: payload["entries"][0].update({"parent_state_data_hash": None}),
    ],
)
def test_coherently_rehashed_noninitial_lifecycle_tamper_is_rejected(mutator) -> None:
    manifest = _trial_manifest()
    mutator(manifest)
    tampered = _rehash(manifest)
    with pytest.raises(
        MaterialStateBundleError,
        match="material_state_manifest_schema_invalid",
    ):
        validate_material_state_bundle_manifest(tampered)


def test_valid_initial_and_trial_manifests_still_validate() -> None:
    initial = _initial_manifest()
    trial = _trial_manifest()
    assert validate_material_state_bundle_manifest(initial) == initial
    assert validate_material_state_bundle_manifest(trial) == trial


def test_coherently_rehashed_manifest_rejects_noncontiguous_entry_index() -> None:
    manifest = _initial_manifest()
    manifest["entries"][0]["index"] = 1
    tampered = _rehash(manifest)

    with pytest.raises(
        MaterialStateBundleError,
        match="material_state_entry_index_mismatch",
    ):
        validate_material_state_bundle_manifest(tampered)
