from __future__ import annotations

from implementation.phase1.rc_constitutive_library import (
    bond_slip_cyclic_probe,
    concrete_cyclic_probe,
    concrete_cyclic_step_series_evidence,
    ConcreteCyclicState,
    ConcreteMaterial,
    concrete_cyclic_response,
    concrete_response,
)


def test_concrete_cyclic_response_matches_monotonic_envelope_before_reversal() -> None:
    mat = ConcreteMaterial(fc_mpa=35.0)

    monotonic = concrete_response(-0.0012, mat)
    cyclic = concrete_cyclic_response(-0.0012, mat=mat)

    assert cyclic.reversal_count == 0
    assert cyclic.pinching_ratio == 1.0
    assert cyclic.restoring.state_tag == "monotonic+compression_hardening"
    assert cyclic.restoring.stress_mpa == monotonic.stress_mpa
    assert cyclic.strength_degradation == 0.0


def test_concrete_cyclic_response_pinches_on_small_reloading_after_reversal() -> None:
    mat = ConcreteMaterial(fc_mpa=38.0, eps_c0=0.0021, eps_cu=0.0040)
    state = ConcreteCyclicState()

    first = concrete_cyclic_response(-0.0024, state=state, mat=mat)
    second = concrete_cyclic_response(0.00012, state=first.state, mat=mat)
    monotonic_reload = concrete_response(0.00012, mat)

    assert second.reversal_count == 1
    assert second.pinching_ratio < 0.5
    assert "reversal" in second.evidence_tags
    assert "pinching" in second.evidence_tags
    assert second.restoring.stress_mpa < monotonic_reload.stress_mpa
    assert second.crack_open is True
    assert second.restoring.state_tag.startswith("cyclic-cracked-pinched")
    assert second.restoring.state_tag.endswith("+tension_softening")


def test_concrete_cyclic_response_accumulates_crushing_damage_history() -> None:
    mat = ConcreteMaterial(fc_mpa=42.0, eps_c0=0.0022, eps_cu=0.0036, residual_comp_ratio=0.18)
    state = ConcreteCyclicState()

    severe = concrete_cyclic_response(-0.0044, state=state, mat=mat)
    reload = concrete_cyclic_response(-0.0027, state=severe.state, mat=mat)

    assert severe.crushing_ratio == 1.0
    assert severe.state.crushing_index == 1.0
    assert "crushing" in severe.evidence_tags
    assert severe.restoring.state_tag.startswith("crushing-degrading+compression_crushed")
    assert reload.state.crushing_index == 1.0
    assert reload.stiffness_degradation >= severe.stiffness_degradation
    assert abs(reload.restoring.stress_mpa) <= abs(reload.envelope.stress_mpa)


def test_concrete_cyclic_probe_surfaces_bounded_library_evidence() -> None:
    evidence = concrete_cyclic_probe()

    assert evidence.probe_id == "rc_concrete_cyclic_probe_v1"
    assert evidence.reversal_count >= 1
    assert evidence.pinching_observed is True
    assert evidence.crushing_observed is True
    assert evidence.degradation_observed is True
    assert evidence.crack_open is True
    assert evidence.min_pinching_ratio < 1.0
    assert evidence.max_crushing_ratio > 0.0
    assert evidence.max_stiffness_degradation > 0.0
    assert evidence.max_strength_degradation > 0.0
    assert "reversal" in evidence.evidence_tags
    assert "pinching" in evidence.evidence_tags
    assert "crushing" in evidence.evidence_tags
    assert evidence.final_history_tag.startswith("cyclic")


def test_concrete_cyclic_step_series_evidence_couples_probe_and_series_depth() -> None:
    probe = concrete_cyclic_probe()

    evidence = concrete_cyclic_step_series_evidence(
        probe=probe,
        cyclic_case_count=3,
        wall_slab_case_count=1,
        rc_case_count=2,
        response_case_count=3,
        series_case_count=3,
        step_series_depth=2400,
        solver_event_count_total=7200,
        recommended_dt_scale_min=0.5,
        response_storage_modes=("npz_external+inline_head",),
        source_mode="ndtha_response_npz",
    )

    assert evidence.source_mode == "ndtha_response_npz"
    assert evidence.response_case_count == 3
    assert evidence.series_case_count == 3
    assert evidence.step_series_depth == 2400
    assert evidence.response_coverage_ratio == 1.0
    assert evidence.wall_slab_coverage_ratio == 1.0
    assert evidence.rc_step_density == 1200.0
    assert evidence.solver_event_density == 1.0
    assert evidence.series_link_pass is True
    assert evidence.wall_slab_series_pass is True
    assert evidence.rc_series_link_pass is True
    assert "step_series" in evidence.evidence_tags
    assert "response_series" in evidence.evidence_tags
    assert "wall_slab" in evidence.evidence_tags
    assert "rc_lock" in evidence.evidence_tags
    assert "solver_events" in evidence.evidence_tags
    assert "cutback_window" in evidence.evidence_tags


def test_bond_slip_cyclic_probe_surfaces_unloading_and_deterioration() -> None:
    evidence = bond_slip_cyclic_probe()

    assert evidence.probe_id == "bond_slip_cyclic_probe_v1"
    assert evidence.reversal_count >= 1
    assert evidence.unloading_observed is True
    assert evidence.residual_observed is True
    assert evidence.degradation_observed is True
    assert evidence.min_unloading_stiffness_ratio < 1.0
    assert evidence.max_strength_degradation > 0.0
    assert evidence.max_slip_ratio > 1.0
    assert evidence.terminal_residual_force_ratio > 0.0
    assert "reversal" in evidence.evidence_tags
    assert "unloading" in evidence.evidence_tags
    assert "degradation" in evidence.evidence_tags
    assert "residual" in evidence.evidence_tags
    assert evidence.final_history_tag.startswith("cyclic")
