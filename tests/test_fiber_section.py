from __future__ import annotations

from implementation.phase1.fiber_section import evaluate_section_response, make_rectangular_rc_section


def test_fiber_section_reports_state_envelopes_for_zero_curvature() -> None:
    section = make_rectangular_rc_section(width_m=0.4, depth_m=0.6, cover_m=0.05)

    result = evaluate_section_response(section=section, axial_strain=5.0e-5, curvature_z_per_m=0.0)

    assert abs(result.moment_z_n_m) < 1.0e4
    assert result.axial_stiffness_n > 0.0
    assert result.neutral_axis_y_m is None
    assert result.section_strain_energy_n > 0.0
    assert result.steel_fiber_count > 0
    assert result.concrete_fiber_count > 0
    assert result.steel_yield_ratio_max < 1.0
    assert result.concrete_crack_ratio_max < 1.0


def test_fiber_section_curvature_exposes_crack_yield_and_neutral_axis_metrics() -> None:
    section = make_rectangular_rc_section(width_m=0.4, depth_m=0.6, cover_m=0.05)

    result = evaluate_section_response(section=section, axial_strain=2.0e-5, curvature_z_per_m=8.0e-3)

    assert abs(result.moment_z_n_m) > 0.0
    assert result.max_abs_strain > 0.0
    assert result.steel_max_abs_strain > 0.0
    assert result.concrete_max_tension_strain > 0.0
    assert result.concrete_max_compression_strain > 0.0
    assert result.concrete_crack_ratio_max > 1.0
    assert result.concrete_crush_ratio_max > 0.0
    assert result.cracked_concrete_ratio > 0.0
    assert result.section_strain_energy_n > 0.0
    assert result.neutral_axis_y_m is not None
    assert abs(float(result.neutral_axis_y_m) - (2.0e-5 / 8.0e-3)) < 1.0e-9
