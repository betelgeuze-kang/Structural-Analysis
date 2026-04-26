from __future__ import annotations

from implementation.phase1.layered_shell_wall import (
    evaluate_layered_panel_response,
    evaluate_layered_panel_cyclic_evidence,
    evaluate_layered_panel_mesh_sensitivity,
    make_layered_slab_section,
    make_layered_wall_section,
)


def test_evaluate_layered_panel_response_surfaces_diaphragm_coupling() -> None:
    response = evaluate_layered_panel_response(
        section=make_layered_slab_section(),
        panel_width_m=6.0,
        panel_height_m=4.0,
        membrane_strain_x=2.0e-4,
        membrane_strain_y=1.2e-4,
        shear_strain_xy=8.0e-5,
        curvature_x_per_m=0.003,
        curvature_y_per_m=0.002,
        diaphragm_strain=1.0e-4,
    )
    assert response.panel_area_m2 == 24.0
    assert response.diaphragm_force_n > 0.0
    assert 0.0 < response.diaphragm_coupling_ratio <= 1.0
    assert response.total_membrane_energy_like > 0.0
    assert response.total_shear_force_n > 0.0
    assert response.assembled_response is not None
    assert response.assembled_response.torsional_coupling_moment_n_m > 0.0
    assert response.assembled_response.force_balance_error_n < 1.0e-6


def test_layered_panel_wall_response_tracks_cracking_on_both_axes() -> None:
    response = evaluate_layered_panel_response(
        section=make_layered_wall_section(),
        panel_width_m=3.0,
        panel_height_m=3.5,
        membrane_strain_x=2.5e-4,
        membrane_strain_y=2.0e-4,
        shear_strain_xy=5.0e-5,
        curvature_x_per_m=0.004,
        curvature_y_per_m=0.003,
        diaphragm_strain=0.0,
    )
    assert response.x_response.cracked_layer_count >= 1
    assert response.y_response.cracked_layer_count >= 1
    assert response.total_membrane_energy_like > 0.0


def test_layered_panel_cyclic_evidence_surfaces_pinching_crushing_and_degradation() -> None:
    evidence = evaluate_layered_panel_cyclic_evidence(
        section=make_layered_wall_section(),
        panel_width_m=3.0,
        panel_height_m=3.5,
        membrane_strain_x=2.5e-4,
        membrane_strain_y=2.0e-4,
        curvature_x_per_m=0.004,
        curvature_y_per_m=0.003,
        diaphragm_strain=0.0,
    )

    assert evidence is not None
    assert evidence.section_family == "wall"
    assert evidence.concrete_layer_count == 2
    assert evidence.reversal_count >= 1
    assert evidence.pinching_observed is True
    assert evidence.crushing_observed is True
    assert evidence.degradation_observed is True
    assert evidence.crack_open is True
    assert evidence.min_pinching_ratio < 1.0
    assert evidence.max_crushing_ratio > 0.0
    assert evidence.max_stiffness_degradation > 0.0
    assert evidence.max_strength_degradation > 0.0
    assert evidence.cyclic_energy_like > 0.0
    assert "pinching" in evidence.evidence_tags
    assert "crushing" in evidence.evidence_tags


def test_layered_panel_response_embeds_cyclic_evidence_for_slab_sections() -> None:
    response = evaluate_layered_panel_response(
        section=make_layered_slab_section(),
        panel_width_m=6.0,
        panel_height_m=4.0,
        membrane_strain_x=2.0e-4,
        membrane_strain_y=1.2e-4,
        shear_strain_xy=8.0e-5,
        curvature_x_per_m=0.003,
        curvature_y_per_m=0.002,
        diaphragm_strain=1.0e-4,
    )

    assert response.cyclic_evidence is not None
    assert response.cyclic_evidence.section_family == "slab"
    assert response.cyclic_evidence.pinching_observed is True
    assert response.cyclic_evidence.crushing_observed is True
    assert response.cyclic_evidence.degradation_observed is True


def test_layered_panel_response_surfaces_corner_force_distribution_for_assembled_panel() -> None:
    response = evaluate_layered_panel_response(
        section=make_layered_wall_section(),
        panel_width_m=3.0,
        panel_height_m=3.5,
        membrane_strain_x=2.5e-4,
        membrane_strain_y=2.0e-4,
        shear_strain_xy=5.0e-5,
        curvature_x_per_m=0.004,
        curvature_y_per_m=0.003,
        diaphragm_strain=8.0e-5,
    )

    assembled = response.assembled_response
    assert assembled is not None
    assert assembled.membrane_stiffness_matrix_n_per_m[0][0] > 0.0
    assert assembled.membrane_stiffness_matrix_n_per_m[1][1] > 0.0
    assert assembled.membrane_stiffness_matrix_n_per_m[2][2] > 0.0
    assert assembled.diaphragm_coupling_vector_n_per_m[0] > 0.0
    assert assembled.diaphragm_coupling_vector_n_per_m[1] > 0.0
    assert len(assembled.corner_nodal_force_vector_n) == 8

    sum_fx = (
        assembled.corner_nodal_force_vector_n[0]
        + assembled.corner_nodal_force_vector_n[2]
        + assembled.corner_nodal_force_vector_n[4]
        + assembled.corner_nodal_force_vector_n[6]
    )
    sum_fy = (
        assembled.corner_nodal_force_vector_n[1]
        + assembled.corner_nodal_force_vector_n[3]
        + assembled.corner_nodal_force_vector_n[5]
        + assembled.corner_nodal_force_vector_n[7]
    )
    assert abs(sum_fx) < 1.0e-6
    assert abs(sum_fy) < 1.0e-6
    assert assembled.force_balance_error_n < 1.0e-6
    assert abs(assembled.torsional_coupling_moment_n_m) > 0.0


def test_layered_panel_mesh_sensitivity_surfaces_hotspots_and_convergence() -> None:
    sensitivity = evaluate_layered_panel_mesh_sensitivity(
        section=make_layered_wall_section(),
        panel_width_m=3.0,
        panel_height_m=3.5,
        membrane_strain_x=2.5e-4,
        membrane_strain_y=2.0e-4,
        shear_strain_xy=5.0e-5,
        curvature_x_per_m=0.004,
        curvature_y_per_m=0.003,
        diaphragm_strain=8.0e-5,
        mesh_divisions=(4, 6, 8),
    )

    assert sensitivity.mesh_division_sequence == (4, 6, 8)
    assert len(sensitivity.representative_element_sizes_m) == 3
    assert sensitivity.coarse_to_fine_membrane_ratio > 1.0
    assert sensitivity.coarse_to_fine_shear_ratio > 1.0
    assert sensitivity.convergence_error_ratio > 0.0
    assert len(sensitivity.hotspot_rows) == 5
    assert sensitivity.max_hotspot_utilization_ratio >= 1.0
    assert sensitivity.hotspot_rows[0].location_label.startswith("corner")
    assert "Layered panel mesh sensitivity" in sensitivity.summary_line
