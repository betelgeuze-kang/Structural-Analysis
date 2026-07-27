from __future__ import annotations

from copy import deepcopy

import pytest

from structural_analysis.dynamics import (
    SourceAuthenticCheckpointError,
    TransientCheckpointReplayError,
    build_transient_checkpoint_authority,
)


def _result() -> dict:
    return {
        "trace": [
            {
                "step": 0,
                "u_m": 0.0,
                "v_mps": 0.0,
                "a_mps2": -0.981,
                "residual_n": 0.0,
                "e_mech_j": 0.0,
            },
            {
                "step": 1,
                "u_m": -0.001,
                "v_mps": -0.02,
                "a_mps2": -0.4,
                "residual_n": 1.0e-9,
                "e_mech_j": 0.2,
            },
        ],
        "metrics": {
            "equilibrium_residual_max_n": 1.0e-9,
            "equilibrium_residual_ratio": 1.0e-12,
            "dissipated_energy_j": 0.03,
            "input_work_j": 0.23,
            "final_mechanical_energy_j": 0.2,
            "energy_balance_relative_error": 0.0,
        },
        "system": {
            "mass_kg": 1000.0,
            "newmark_beta": 0.25,
            "newmark_gamma": 0.5,
        },
    }


def test_source_authentic_checkpoint_binds_all_required_evidence() -> None:
    source = _result()
    checkpoint = build_transient_checkpoint_authority(
        parent_content=b"time_s,accel_g\n0.0,0.1\n0.1,0.2\n",
        force_history=(-981.0, -1962.0),
        initial_state={
            "displacement_m": 0.0,
            "velocity_mps": 0.0,
            "acceleration_mps2": -0.981,
        },
        source_result=source,
        replay_result=deepcopy(source),
        source_authentic_requested=True,
    )

    assert checkpoint.authority == "source_authentic_checkpoint"
    assert checkpoint.self_consistent_checkpoint is True
    assert checkpoint.source_authentic_checkpoint is True
    assert checkpoint.parent_content_bound is True
    assert checkpoint.parent_content_hash.startswith("sha256:")
    assert checkpoint.force_history_hash.startswith("sha256:")
    assert checkpoint.initial_state_hash.startswith("sha256:")
    assert checkpoint.newmark_replay_pass is True
    assert checkpoint.equilibrium_replay_pass is True
    assert checkpoint.work_dissipation_replay_pass is True


def test_self_consistent_checkpoint_does_not_claim_source_authenticity() -> None:
    source = _result()
    checkpoint = build_transient_checkpoint_authority(
        parent_content=None,
        force_history=(-981.0, -1962.0),
        initial_state={"displacement_m": 0.0},
        source_result=source,
        replay_result=deepcopy(source),
        source_authentic_requested=False,
    )

    assert checkpoint.authority == "self_consistent_checkpoint"
    assert checkpoint.self_consistent_checkpoint is True
    assert checkpoint.source_authentic_checkpoint is False
    assert checkpoint.parent_content_bound is False
    assert checkpoint.parent_content_hash is None


def test_source_authentic_checkpoint_requires_parent_content() -> None:
    source = _result()

    with pytest.raises(
        SourceAuthenticCheckpointError,
        match="requires_parent_content",
    ):
        build_transient_checkpoint_authority(
            parent_content=None,
            force_history=(-981.0, -1962.0),
            initial_state={"displacement_m": 0.0},
            source_result=source,
            replay_result=deepcopy(source),
            source_authentic_requested=True,
        )


def test_tampered_replay_cannot_mint_either_checkpoint_authority() -> None:
    source = _result()
    replay = deepcopy(source)
    replay["trace"][1]["u_m"] = 0.125

    with pytest.raises(
        TransientCheckpointReplayError,
        match="newmark_replay",
    ):
        build_transient_checkpoint_authority(
            parent_content=b"ground-motion",
            force_history=(-981.0, -1962.0),
            initial_state={"displacement_m": 0.0},
            source_result=source,
            replay_result=replay,
            source_authentic_requested=True,
        )


def test_tampered_work_replay_is_rejected_explicitly() -> None:
    source = _result()
    replay = deepcopy(source)
    replay["metrics"]["input_work_j"] = 99.0

    with pytest.raises(
        TransientCheckpointReplayError,
        match="work_dissipation_replay",
    ):
        build_transient_checkpoint_authority(
            parent_content=b"ground-motion",
            force_history=(-981.0, -1962.0),
            initial_state={"displacement_m": 0.0},
            source_result=source,
            replay_result=replay,
            source_authentic_requested=True,
        )
