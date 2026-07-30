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
                "force_n": 0.0,
                "u_m": 0.0,
                "v_mps": 0.0,
                "a_mps2": 0.0,
                "residual_n": 0.0,
                "e_mech_j": 0.0,
                "external_work_increment_j": 0.0,
                "damping_dissipation_increment_j": 0.0,
                "plastic_dissipation_increment_j": 0.0,
            },
            {
                "step": 1,
                "force_n": 8.7,
                "u_m": 0.01,
                "v_mps": 0.2,
                "a_mps2": 4.0,
                "residual_n": 0.0,
                "e_mech_j": 0.0405,
                "external_work_increment_j": 0.174,
                "damping_dissipation_increment_j": 0.012,
                "plastic_dissipation_increment_j": 0.0,
            },
        ],
        "metrics": {
            "equilibrium_residual_max_n": 0.0,
            "equilibrium_residual_ratio": 0.0,
            "damping_dissipation_j": 0.012,
            "plastic_dissipation_j": 0.0,
            "dissipated_energy_j": 0.012,
            "input_work_j": 0.174,
            "final_mechanical_energy_j": 0.0405,
            "energy_balance_relative_error": (
                abs(0.0405 + 0.012 - 0.174) / 0.174
            ),
        },
        "system": {
            "mass_kg": 2.0,
            "stiffness_n_per_m": 10.0,
            "damping_n_s_per_m": 3.0,
            "nonlinear_stiffness_n_per_m2": 0.0,
            "time_step_s": 0.1,
            "newmark_beta": 0.25,
            "newmark_gamma": 0.5,
            "plastic_dissipation_model": "none",
        },
    }


def _complete_initial_state() -> dict[str, float]:
    return {
        "displacement_m": 0.0,
        "velocity_mps": 0.0,
        "acceleration_mps2": 0.0,
    }


def test_source_authentic_checkpoint_binds_all_required_evidence() -> None:
    source = _result()
    checkpoint = build_transient_checkpoint_authority(
        parent_content=b"time_s,accel_g\n0.0,0.1\n0.1,0.2\n",
        force_history=(0.0, 8.7),
        initial_state=_complete_initial_state(),
        source_result=source,
        replay_result=deepcopy(source),
        source_authentic_requested=True,
    )

    assert checkpoint.authority == "source_authentic_checkpoint"
    assert checkpoint.schema_version == "transient-checkpoint-authority.v2"
    assert checkpoint.self_consistent_checkpoint is True
    assert checkpoint.source_authentic_checkpoint is True
    assert checkpoint.parent_content_bound is True
    assert checkpoint.parent_content_hash.startswith("sha256:")
    assert checkpoint.force_history_hash.startswith("sha256:")
    assert checkpoint.initial_state_hash.startswith("sha256:")
    assert checkpoint.force_history_complete is True
    assert checkpoint.initial_state_replay_pass is True
    assert checkpoint.deterministic_replay_pass is True
    assert checkpoint.newmark_replay_pass is True
    assert checkpoint.equilibrium_replay_pass is True
    assert checkpoint.work_dissipation_replay_pass is True


def test_self_consistent_checkpoint_does_not_claim_source_authenticity() -> None:
    source = _result()
    checkpoint = build_transient_checkpoint_authority(
        parent_content=None,
        force_history=(0.0, 8.7),
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
            force_history=(0.0, 8.7),
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
            force_history=(0.0, 8.7),
            initial_state=_complete_initial_state(),
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
            force_history=(0.0, 8.7),
            initial_state=_complete_initial_state(),
            source_result=source,
            replay_result=replay,
            source_authentic_requested=True,
        )


def test_identical_rehashed_fabrication_fails_independent_newmark_replay() -> None:
    fabricated = _result()
    fabricated["trace"][1]["u_m"] = 0.125

    with pytest.raises(
        TransientCheckpointReplayError,
        match="newmark_replay",
    ):
        build_transient_checkpoint_authority(
            parent_content=b"ground-motion",
            force_history=(0.0, 8.7),
            initial_state=_complete_initial_state(),
            source_result=fabricated,
            replay_result=deepcopy(fabricated),
            source_authentic_requested=True,
        )


def test_source_authentic_checkpoint_requires_complete_force_history() -> None:
    source = _result()
    source["trace"] = source["trace"][:1]

    with pytest.raises(
        TransientCheckpointReplayError,
        match="force_history_replay",
    ):
        build_transient_checkpoint_authority(
            parent_content=b"ground-motion",
            force_history=(0.0, 8.7),
            initial_state=_complete_initial_state(),
            source_result=source,
            replay_result=deepcopy(source),
            source_authentic_requested=True,
        )


def test_source_authentic_checkpoint_requires_complete_initial_state() -> None:
    source = _result()

    with pytest.raises(
        SourceAuthenticCheckpointError,
        match="requires_complete_initial_state",
    ):
        build_transient_checkpoint_authority(
            parent_content=b"ground-motion",
            force_history=(0.0, 8.7),
            initial_state={"displacement_m": 0.0},
            source_result=source,
            replay_result=deepcopy(source),
            source_authentic_requested=True,
        )
