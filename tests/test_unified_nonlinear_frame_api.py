from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import numpy as np
import pytest

from structural_analysis.api.nonlinear_frame import (
    COROTATIONAL_GENERAL_PROFILE,
    COROTATIONAL_PORTAL_PROFILE,
    DISPLACEMENT_CONTROL_MODE,
    FIXED_CHORD_SERIAL_PROFILE,
    NonlinearFrameConfig,
    analyze_nonlinear_frame,
    validate_nonlinear_frame_manifest,
    validate_nonlinear_frame_result,
)
from structural_analysis.api import nonlinear_frame_cli
from structural_analysis.io.neutral.loader import load_neutral_json
from structural_analysis.solvers.nonlinear.newton import (
    VECTOR_MATRIX_BACKEND,
    VECTOR_SPARSE_MATRIX_BACKEND,
)


def _materials_and_sections() -> tuple[list[dict], list[dict]]:
    return (
        [
            {
                "id": "steel",
                "type": "bilinear_combined_hardening_steel",
                "elastic_modulus_mpa": 200_000.0,
                "yield_stress_mpa": 250.0,
                "isotropic_hardening_modulus_mpa": 3_000.0,
                "kinematic_hardening_modulus_mpa": 5_000.0,
                "yield_tolerance_mpa": 1.0e-10,
            },
            {
                "id": "concrete",
                "type": "asymmetric_concrete_damage",
                "elastic_modulus_mpa": 30_000.0,
                "tensile_strength_mpa": 3.0,
                "compressive_strength_mpa": 30.0,
                "tensile_softening_rate": 3_000.0,
                "compressive_softening_rate": 400.0,
                "history_tolerance": 1.0e-14,
            },
        ],
        [
            {
                "id": "RC1",
                "type": "rectangular_rc_fiber_section",
                "width_m": 0.4,
                "depth_m": 0.6,
                "cover_m": 0.05,
                "concrete_layer_count": 2,
                "top_bar_count": 4,
                "bottom_bar_count": 4,
                "bar_area_m2": 3.87e-4,
                "steel_material": "steel",
                "concrete_material": "concrete",
            }
        ],
    )


def _base_payload() -> dict:
    materials, sections = _materials_and_sections()
    return {
        "schema_version": "structural-analysis-canonical-model.v1",
        "units": {"length": "m", "force": "kN"},
        "coordinate_system": {"axis_order": ["X", "Y", "Z"], "up_axis": "Z"},
        "nodes": [],
        "elements": [],
        "materials": materials,
        "sections": sections,
        "loads": [],
        "supports": [],
        "unsupported_features": [],
        "warnings": [],
        "metadata": {"case_id": "unified-nonlinear-frame"},
    }


def _fixed_payload() -> dict:
    payload = _base_payload()
    payload.update(
        {
            "nodes": [
                {"id": "N1", "coordinates": [0.0, 0.0, 0.0]},
                {"id": "N2", "coordinates": [3.0, 0.0, 0.0]},
            ],
            "elements": [
                {
                    "id": "M1",
                    "type": "stateful_rc_fiber_frame2d",
                    "nodes": ["N1", "N2"],
                    "section": "RC1",
                    "integration_order": 2,
                }
            ],
            "loads": [
                {
                    "node": "N2",
                    "components": {
                        "FX": 0.0,
                        "FY": -10.0,
                        "FZ": 0.0,
                        "MX": 0.0,
                        "MY": 0.0,
                        "MZ": 0.0,
                    },
                }
            ],
            "supports": [{"node": "N1", "dofs": ["UX", "UY", "RZ"]}],
        }
    )
    return payload


def _portal_payload() -> dict:
    payload = _base_payload()
    payload.update(
        {
            "nodes": [
                {"id": "N1", "coordinates": [0.0, 0.0, 0.0]},
                {"id": "N2", "coordinates": [4.0, 0.0, 0.0]},
                {"id": "N3", "coordinates": [0.0, 3.0, 0.0]},
                {"id": "N4", "coordinates": [4.0, 3.0, 0.0]},
            ],
            "elements": [
                {
                    "id": member_id,
                    "type": "stateful_corotational_rc_fiber_frame2d",
                    "nodes": list(nodes),
                    "section": "RC1",
                    "integration_order": 3,
                }
                for member_id, nodes in (
                    ("column-left", ("N1", "N3")),
                    ("column-right", ("N2", "N4")),
                    ("beam-top", ("N3", "N4")),
                )
            ],
            "loads": [
                {
                    "node": "N4",
                    "components": {
                        "FX": 20.0,
                        "FY": -50.0,
                        "FZ": 0.0,
                        "MX": 0.0,
                        "MY": 0.0,
                        "MZ": 0.0,
                    },
                }
            ],
            "supports": [
                {"node": "N1", "dofs": ["UX", "UY", "RZ"]},
                {"node": "N2", "dofs": ["UX", "UY", "RZ"]},
            ],
        }
    )
    return payload


def _branching_payload() -> dict:
    payload = _base_payload()
    payload.update(
        {
            "nodes": [
                {"id": "N1", "coordinates": [0.0, 0.0, 0.0]},
                {"id": "N2", "coordinates": [4.0, 0.0, 0.0]},
                {"id": "N3", "coordinates": [0.0, 3.0, 0.0]},
                {"id": "N4", "coordinates": [4.0, 3.0, 0.0]},
                {"id": "N5", "coordinates": [2.0, 3.0, 0.0]},
                {"id": "N6", "coordinates": [2.0, 5.0, 0.0]},
            ],
            "elements": [
                {
                    "id": member_id,
                    "type": "stateful_corotational_rc_fiber_frame2d",
                    "nodes": list(nodes),
                    "section": "RC1",
                    "integration_order": 3,
                }
                for member_id, nodes in (
                    ("column-left", ("N1", "N3")),
                    ("column-right", ("N2", "N4")),
                    ("beam-left", ("N3", "N5")),
                    ("beam-right", ("N5", "N4")),
                    ("branch", ("N5", "N6")),
                )
            ],
            "loads": [
                {
                    "node": "N6",
                    "components": {
                        "FX": 5.0,
                        "FY": -10.0,
                        "FZ": 0.0,
                        "MX": 0.0,
                        "MY": 0.0,
                        "MZ": 0.0,
                    },
                }
            ],
            "supports": [
                {"node": "N1", "dofs": ["UX", "UY", "RZ"]},
                {
                    "node": "N2",
                    "dofs": ["UX", "UY", "RZ"],
                    "prescribed_values": {"UX": 2.0e-4},
                },
            ],
        }
    )
    return payload


def _member_feature_payload() -> dict:
    payload = _base_payload()
    payload.update(
        {
            "nodes": [
                {"id": "N1", "coordinates": [0.0, 0.0, 0.0]},
                {"id": "N2", "coordinates": [4.0, 0.0, 0.0]},
            ],
            "elements": [
                {
                    "id": "released-beam",
                    "type": "stateful_corotational_rc_fiber_frame2d",
                    "nodes": ["N1", "N2"],
                    "section": "RC1",
                    "integration_order": 3,
                    "rigid_offsets_global_m": {
                        "i": [0.2, 0.0],
                        "j": [-0.2, 0.0],
                    },
                    "end_releases": {"i": [], "j": ["RZ"]},
                    "uniform_distributed_load_local": {
                        "basis": "initial_member_local",
                        "behavior": "dead",
                        "qx_kN_per_m": 0.0,
                        "qy_kN_per_m": -2.0,
                    },
                }
            ],
            "loads": [],
            "supports": [
                {"node": "N1", "dofs": ["UX", "UY", "RZ"]},
                {"node": "N2", "dofs": ["RZ"]},
            ],
        }
    )
    return payload


def _model(tmp_path: Path, payload: dict, name: str = "model.json"):
    path = tmp_path / name
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return load_neutral_json(path)


def test_unified_api_preserves_fixed_chord_profile_and_normalizes_stress_to_pa(
    tmp_path: Path,
) -> None:
    result = analyze_nonlinear_frame(
        _model(tmp_path, _fixed_payload()),
        NonlinearFrameConfig(profile=FIXED_CHORD_SERIAL_PROFILE, load_steps=2),
    )
    report = validate_nonlinear_frame_result(result)

    assert report.contract_pass is True
    assert result.profile == FIXED_CHORD_SERIAL_PROFILE
    assert result.authority["reaction"] == "authoritative"
    assert result.fiber_results
    assert "stress_Pa" in result.fiber_results[0]
    assert "stress_MPa" not in result.fiber_results[0]
    assert result.checkpoint_artifact()


@pytest.fixture(scope="module")
def portal_result(tmp_path_factory: pytest.TempPathFactory):
    root = tmp_path_factory.mktemp("unified-corotational-portal")
    model = _model(root, _portal_payload())
    result = analyze_nonlinear_frame(
        model,
        NonlinearFrameConfig(profile=COROTATIONAL_PORTAL_PROFILE, load_steps=4),
    )
    return model, result


def test_corotational_profile_exposes_exact_normalized_engineering_results(
    portal_result,
) -> None:
    _, result = portal_result
    report = validate_nonlinear_frame_result(result)

    assert result.status == "ready"
    assert report.contract_pass is True
    assert report.exact_engineering_recovery is True
    assert report.exact_checkpoint_chain_replay is True
    assert report.external_level2_attached is False
    assert result.authority["reaction"] == "exact_bounded_candidate"
    assert result.authority["public_api"] == "developer_preview_candidate"
    assert len(result.node_displacements) == 4
    assert len(result.support_reactions) == 6
    assert len(result.member_end_forces) == 3
    assert len(result.section_results) == 9
    assert result.fiber_results
    assert all("stress_Pa" in row for row in result.fiber_results)
    assert result.metrics["fallback_count"] == 0
    assert result.metrics["regularization_count"] == 0
    assert validate_nonlinear_frame_manifest(result.to_dict()) == result.to_dict()


def test_corotational_public_api_exposes_native_sparse_dense_parity(
    portal_result,
) -> None:
    model, dense = portal_result
    sparse = analyze_nonlinear_frame(
        model,
        NonlinearFrameConfig(
            profile=COROTATIONAL_PORTAL_PROFILE,
            load_steps=4,
            matrix_backend=VECTOR_SPARSE_MATRIX_BACKEND,
        ),
    )

    assert dense.configuration["matrix_backend"] == VECTOR_MATRIX_BACKEND
    assert sparse.status == "ready"
    assert validate_nonlinear_frame_result(sparse).contract_pass is True
    assert sparse.configuration["matrix_backend"] == VECTOR_SPARSE_MATRIX_BACKEND
    assert sparse.configuration["stiffness_storage"] == "scipy_sparse_csr"
    assert sparse.metrics["native_sparse_assembly_used"] is True
    assert sparse.metrics["sparse_factorization_count"] > 0
    assert sparse.metrics["sparse_factorization_diagnostics_passed"] is True
    assert sparse.metrics["sparse_factorization_max_condition_number_1"] < 1.0e12
    assert sparse.metrics["sparse_factorization_max_backward_error"] <= 1.0e-12
    assert (
        len(sparse.metrics["sparse_factorization_diagnostic_hashes"])
        == sparse.metrics["sparse_factorization_count"]
    )
    assert str(sparse.metrics["sparse_factorization_policy_hash"]).startswith("sha256:")
    assert sparse.metrics["fallback_count"] == 0
    assert sparse.metrics["regularization_count"] == 0
    for sparse_row, dense_row in zip(
        sparse.node_displacements, dense.node_displacements, strict=True
    ):
        assert sparse_row["node_id"] == dense_row["node_id"]
        np.testing.assert_allclose(
            [sparse_row[key] for key in ("UX_m", "UY_m", "UZ_m")],
            [dense_row[key] for key in ("UX_m", "UY_m", "UZ_m")],
            rtol=1.0e-8,
            atol=1.0e-9,
        )
        np.testing.assert_allclose(
            [sparse_row[key] for key in ("RX_rad", "RY_rad", "RZ_rad")],
            [dense_row[key] for key in ("RX_rad", "RY_rad", "RZ_rad")],
            rtol=1.0e-8,
            atol=1.0e-10,
        )


def test_general_corotational_profile_supports_branching_multiple_supports_and_prescribed_displacement(
    tmp_path: Path,
) -> None:
    model = _model(tmp_path, _branching_payload(), "branching.json")
    config = NonlinearFrameConfig(
        profile=COROTATIONAL_GENERAL_PROFILE,
        load_steps=4,
        residual_tolerance=1.0e-9,
        matrix_backend=VECTOR_SPARSE_MATRIX_BACKEND,
    )
    result = analyze_nonlinear_frame(model, config)
    report = validate_nonlinear_frame_result(result)

    assert result.status == "ready"
    assert report.contract_pass is True
    assert result.profile == COROTATIONAL_GENERAL_PROFILE
    assert result.compiler_profile == (
        "planar_connected_branching_frame_explicit_fiber_section.v1"
    )
    assert len(result.node_displacements) == 6
    assert len(result.member_end_forces) == 5
    assert len(result.support_reactions) == 6
    assert result.node_displacements[1]["UX_m"] == 2.0e-4
    assert result.metrics["native_sparse_assembly_used"] is True
    assert result.metrics["sparse_factorization_diagnostics_passed"] is True
    assert result.authority["reaction"] == "exact_bounded_candidate"

    replayed = analyze_nonlinear_frame(
        model,
        config,
        restart_checkpoint_chain=result.checkpoint_artifact(),
    )
    assert validate_nonlinear_frame_result(replayed).contract_pass is True
    assert replayed.node_displacements == result.node_displacements
    assert replayed.support_reactions == result.support_reactions


def test_general_public_profile_executes_release_offset_and_distributed_load(
    tmp_path: Path,
) -> None:
    model = _model(tmp_path, _member_feature_payload(), "member-features.json")
    config = NonlinearFrameConfig(
        profile=COROTATIONAL_GENERAL_PROFILE,
        load_steps=4,
        residual_tolerance=1.0e-9,
        maximum_iterations=60,
    )
    result = analyze_nonlinear_frame(model, config)
    report = validate_nonlinear_frame_result(result)

    assert result.status == "ready"
    assert report.contract_pass is True
    assert result.unsupported_features == ()
    assert result.member_end_forces[0]["member_features"]["release_j_rz"] is True
    assert result.member_end_forces[0]["member_features"][
        "uniform_load_local_kn_per_m"
    ] == [0.0, -2.0]
    assert abs(result.member_end_forces[0]["local_end_j"]["MZ_Nm"]) < 1.0e-8
    reaction_by_dof = {
        (row["node_id"], row["dof"]): row["value_si"]
        for row in result.support_reactions
    }
    assert abs(reaction_by_dof[("N1", "UY")] - 7200.0) < 2.0e-6

    replayed = analyze_nonlinear_frame(
        model,
        config,
        restart_checkpoint_chain=result.checkpoint_artifact(),
    )
    assert validate_nonlinear_frame_result(replayed).contract_pass is True
    assert replayed.node_displacements == result.node_displacements
    assert replayed.support_reactions == result.support_reactions
    assert replayed.member_end_forces == result.member_end_forces


def test_general_public_profile_displacement_control_and_exact_restart(
    tmp_path: Path,
) -> None:
    model = _model(tmp_path, _member_feature_payload(), "displacement-control.json")
    config = NonlinearFrameConfig(
        profile=COROTATIONAL_GENERAL_PROFILE,
        load_steps=4,
        residual_tolerance=1.0e-9,
        maximum_iterations=60,
        matrix_backend=VECTOR_SPARSE_MATRIX_BACKEND,
        control_mode=DISPLACEMENT_CONTROL_MODE,
        control_node_id="N2",
        control_dof="UY",
        terminal_control_displacement=-1.6e-4,
    )
    result = analyze_nonlinear_frame(model, config)
    report = validate_nonlinear_frame_result(result)

    assert report.contract_pass is True
    assert result.metrics["control_mode"] == DISPLACEMENT_CONTROL_MODE
    assert result.metrics["terminal_solved_load_factor"] != 1.0
    assert result.node_displacements[1]["UY_m"] == -1.6e-4
    assert result.metrics["native_sparse_assembly_used"] is True
    assert result.metrics["sparse_factorization_diagnostics_passed"] is True

    replayed = analyze_nonlinear_frame(
        model,
        config,
        restart_checkpoint_chain=result.checkpoint_artifact(),
    )
    assert validate_nonlinear_frame_result(replayed).contract_pass is True
    assert replayed.node_displacements == result.node_displacements
    assert replayed.support_reactions == result.support_reactions
    assert replayed.member_end_forces == result.member_end_forces
    assert replayed.checkpoint_artifact() == result.checkpoint_artifact()


def test_general_corotational_profile_rejects_disconnected_graph(
    tmp_path: Path,
) -> None:
    payload = _branching_payload()
    payload["elements"] = payload["elements"][:-1]
    result = analyze_nonlinear_frame(
        _model(tmp_path, payload, "disconnected.json"),
        NonlinearFrameConfig(profile=COROTATIONAL_GENERAL_PROFILE),
    )

    assert result.status == "blocked"
    assert result.contract_pass is False
    assert result.unsupported_features[0]["kind"] == (
        "corotational_general_graph_disconnected"
    )


def test_terminal_checkpoint_chain_replays_to_identical_corotational_result(
    portal_result,
) -> None:
    model, first = portal_result
    resumed = analyze_nonlinear_frame(
        model,
        NonlinearFrameConfig(profile=COROTATIONAL_PORTAL_PROFILE, load_steps=4),
        restart_checkpoint_chain=first.checkpoint_artifact(),
    )

    assert validate_nonlinear_frame_result(resumed).contract_pass is True
    assert resumed.metrics["replayed_prefix_step_count"] == 4
    assert resumed.metrics["newly_solved_step_count"] == 0
    assert (
        resumed.contract_bindings["engineering_result_hash"]
        == (first.contract_bindings["engineering_result_hash"])
    )
    assert resumed.node_displacements == first.node_displacements
    assert resumed.support_reactions == first.support_reactions
    assert resumed.member_end_forces == first.member_end_forces
    assert resumed.section_results == first.section_results
    assert resumed.fiber_results == first.fiber_results
    assert resumed.checkpoint_artifact() == first.checkpoint_artifact()


def test_tampered_corotational_checkpoint_chain_fails_closed(portal_result) -> None:
    model, first = portal_result
    raw = bytearray(first.checkpoint_artifact())
    raw[-2] = ord("0") if raw[-2] != ord("0") else ord("1")
    blocked = analyze_nonlinear_frame(
        model,
        NonlinearFrameConfig(profile=COROTATIONAL_PORTAL_PROFILE, load_steps=4),
        restart_checkpoint_chain=raw,
    )

    assert blocked.status == "blocked"
    assert blocked.contract_pass is False
    assert blocked.metrics["exact_checkpoint_chain_replay"] is False
    assert blocked.checkpoint["available"] is False
    assert blocked.unsupported_features


def test_unified_cli_writes_result_report_and_checkpoint_atomically(
    tmp_path: Path,
    portal_result,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model, result = portal_result
    result_path = tmp_path / "result.json"
    report_path = tmp_path / "report.json"
    checkpoint_path = tmp_path / "checkpoint.json"
    monkeypatch.setattr(
        nonlinear_frame_cli,
        "analyze_nonlinear_frame",
        lambda *_args, **_kwargs: result,
    )

    exit_code = nonlinear_frame_cli.main(
        [
            model.source_path,
            "--profile",
            COROTATIONAL_PORTAL_PROFILE,
            "--out",
            str(result_path),
            "--report-out",
            str(report_path),
            "--checkpoint-out",
            str(checkpoint_path),
        ]
    )

    assert exit_code == 0
    assert json.loads(result_path.read_text(encoding="utf-8"))["contract_pass"] is True
    assert (
        json.loads(report_path.read_text(encoding="utf-8"))[
            "exact_checkpoint_chain_replay"
        ]
        is True
    )
    assert checkpoint_path.read_bytes() == result.checkpoint_artifact()


def test_unified_cli_executes_displacement_control(tmp_path: Path) -> None:
    model = _model(tmp_path, _member_feature_payload(), "cli-control-model.json")
    result_path = tmp_path / "control-result.json"
    report_path = tmp_path / "control-report.json"
    checkpoint_path = tmp_path / "control-checkpoint.json"

    exit_code = nonlinear_frame_cli.main(
        [
            model.source_path,
            "--profile",
            COROTATIONAL_GENERAL_PROFILE,
            "--matrix-backend",
            VECTOR_SPARSE_MATRIX_BACKEND,
            "--residual-tolerance",
            "1e-9",
            "--max-iterations",
            "60",
            "--control-mode",
            DISPLACEMENT_CONTROL_MODE,
            "--control-node",
            "N2",
            "--control-dof",
            "UY",
            "--terminal-control-displacement",
            "-0.00016",
            "--out",
            str(result_path),
            "--report-out",
            str(report_path),
            "--checkpoint-out",
            str(checkpoint_path),
        ]
    )

    result = json.loads(result_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert result["configuration"]["control_mode"] == DISPLACEMENT_CONTROL_MODE
    assert result["node_displacements"][1]["UY_m"] == -1.6e-4
    assert result["metrics"]["terminal_solved_load_factor"] != 1.0
    assert report["contract_pass"] is True
    assert checkpoint_path.read_bytes()


def test_profile_mismatch_and_result_hash_tampering_fail_closed(tmp_path: Path) -> None:
    blocked = analyze_nonlinear_frame(
        _model(tmp_path, _fixed_payload(), "wrong-profile.json"),
        NonlinearFrameConfig(profile=COROTATIONAL_PORTAL_PROFILE),
    )
    assert blocked.status == "blocked"
    assert blocked.unsupported_features[0]["kind"] == (
        "corotational_portal_node_count_invalid"
    )

    with pytest.raises(ValueError, match="result_hash"):
        validate_nonlinear_frame_result(
            replace(blocked, result_hash="sha256:" + "0" * 64)
        )
