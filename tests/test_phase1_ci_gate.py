from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parents[1] / "implementation/phase1/phase1_ci_gate.py"
    spec = importlib.util.spec_from_file_location("phase1_ci_gate_for_tests", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _touch(path: Path, content: str = "ok") -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path)


def _passing_gate_payload(tmp_path: Path) -> dict:
    pbd_artifacts = {
        "drift_envelope_png": _touch(tmp_path / "drift.png"),
        "core_hysteresis_png": _touch(tmp_path / "hysteresis.png"),
        "killshot_metrics_json": _touch(tmp_path / "killshot.json"),
        "killshot_metrics_csv": _touch(tmp_path / "killshot.csv"),
        "review_markdown": _touch(tmp_path / "review.md"),
        "review_pdf": _touch(tmp_path / "review.pdf"),
        "json_out": _touch(tmp_path / "midas.json"),
        "npz_out": _touch(tmp_path / "midas.npz"),
        "kds_frontend_payload_json": _touch(tmp_path / "kds_frontend.json"),
    }
    checks = {
        "real_source_verified": True,
        "sample_source_blocked": True,
        "shell_beam_mix_pass": True,
        "real_topology_pass": True,
        "pr_scale_pass": True,
        "nightly_scale_pass": True,
        "on_scaling_regression_pass": True,
        "real_graph_used": True,
        "graph_source_is_real": True,
        "projection_ratio_pass": True,
        "partition_quality_threshold_pass": True,
        "topology_gate_pass": True,
        "required_levels_present": True,
        "required_levels_sync_pass": True,
        "sync_stall_budget_pass": True,
        "backend_policy_pass": True,
        "sync_stress_pass": True,
        "sync_backend_policy_pass": True,
        "virtual_sync_blocked_pass": True,
        "feti_profile_pass": True,
        "inline_native_smoke_pass": True,
        "has_required_seeds": True,
        "has_seed_diversity": True,
        "includes_plus_minus_10": True,
        "includes_plus_minus_5": True,
        "case_diversity_pass": True,
        "stagewise_execution_pass": True,
        "all_converged": True,
        "scenario_count_nonzero": True,
        "build_cases_pass": True,
        "benchmark_pass": True,
        "noise_convergence_pass": True,
        "metric_source_pass": True,
        "drift_within_5pct": True,
        "base_shear_within_5pct": True,
        "buckling_within_5pct": True,
        "mac_above_095": True,
        "member_force_metric_present": True,
        "member_force_hard_pass": True,
        "member_force_soft_accept_pass": True,
        "member_force_components_5d_pass": True,
        "shell_evidence_pass": True,
        "wall_evidence_pass": True,
        "interface_boundary_pass": True,
        "benchmark_coverage_pass": True,
        "contact_surface_declared": True,
        "shell_direct_contract_pass": True,
        "wall_direct_contract_pass": True,
        "contact_interface_compression_surrogate_pass": True,
        "structural_contact_direct_contract_pass": True,
        "foundation_soil_link_direct_contract_pass": True,
        "material_model_breadth_pass": True,
        "link_model_breadth_pass": True,
        "material_capability_breadth_pass": True,
        "concrete_damage_pass": True,
        "cyclic_degradation_pass": True,
        "bond_interface_pass": True,
        "contact_schema_pass": True,
        "contact_solver_evidence_pass": True,
        "contact_whitebox_evidence_pass": True,
        "foundation_scope_ready": True,
        "foundation_artifact_ready": True,
        "foundation_link_models_ready": True,
        "bounded_contact_evidence_pass": True,
        "special_link_categories_present": True,
        "structural_contact_validation_present": True,
        "structural_contact_event_sequence_zero_pass": True,
        "all_structural_contact_categories_ready": True,
        "direct_structural_contact_pass": True,
        "foundation_soil_link_pass": True,
        "interface_transfer_pass": True,
        "shell_surface_coupling_pass": True,
        "interface_gap_continuity_pass": True,
        "foundation_soil_impedance_pass": True,
        "ssi_boundary_interaction_pass": True,
        "soil_tunnel_dynamic_interaction_pass": True,
        "direct_structural_contact_family_pass": True,
        "ssi_boundary_pass": True,
        "soil_tunnel_dynamic_pass": True,
        "all_matrix_rows_ready": True,
        "model_artifacts_present_pass": True,
        "editor_seed_present_pass": True,
        "load_pattern_library_present_pass": True,
        "export_report_pass": True,
        "loadcomb_preview_files_pass": True,
        "loadcomb_roundtrip_reports_pass": True,
        "corpus_manifest_present_pass": True,
        "native_text_case_present_pass": True,
        "native_writeback_ready_pass": True,
        "diff_receipt_coverage_pass": True,
        "per_case_writeback_pass": True,
        "topology_stability_pass": True,
        "load_contract_stability_pass": True,
        "loadcomb_exact_roundtrip_pass": True,
        "unknown_rows_zero_pass": True,
        "beam_column_generalization_pass": True,
        "fiber_section_family_pass": True,
        "layered_shell_wall_pass": True,
        "joint_panel_family_pass": True,
        "foundation_section_family_pass": True,
        "connection_section_family_pass": True,
        "substructure_section_family_pass": True,
        "device_section_family_pass": True,
        "isolation_section_family_pass": True,
        "soil_interface_section_family_pass": True,
        "bearing_section_family_pass": True,
        "retrofit_section_family_pass": True,
        "ground_improvement_section_family_pass": True,
        "production_engine_evidence_pass": True,
        "signed_release_registry_pass": True,
        "authoring_action_automation_pass": True,
        "audit_approval_flow_pass": True,
        "audit_action_automation_pass": True,
        "auto_approved_subset_pass": True,
        "signed_submission_bundle_pass": True,
        "viewer_results_surface_pass": True,
        "results_explorer_traceability_pass": True,
        "provenance_export_pass": True,
        "bounded_roundtrip_pass": True,
        "real_source_pass": True,
        "gpu_strict_pass": True,
        "rust_backend_used_pass": True,
        "all_cases_converged": True,
        "drift_p95_pass": True,
        "base_shear_p95_pass": True,
        "top_disp_metric_source_required_pass": True,
        "top_disp_p95_pass": True,
        "pdelta_enabled_pass": True,
        "dynamic_reversal_pass": True,
        "rayleigh_damping_pass": True,
        "collapse_cutoff_guard_pass": True,
        "collapse_path_pass": True,
        "no_collapse_detected": True,
        "plasticity_triggered_all_cases": True,
        "min_plastic_story_count_pass": True,
        "case_count_pass": True,
        "ndtha_contract_pass": True,
        "ndtha_no_collapse_pass": True,
        "summary_residual_finite_pass": True,
        "residual_metric_trace_pass": True,
        "residual_top_hard_pass": True,
        "residual_drift_hard_pass": True,
        "fallback_rate_pass": True,
        "opensees_pass": True,
        "sac_pass": True,
        "nheri_pass": True,
        "holdout_manifest_pass": True,
        "sac_min_case_count_pass": True,
        "nheri_min_case_count_pass": True,
        "source_manifest_pass": True,
        "wind_duration_pass": True,
        "wind_reversal_pass": True,
        "long_series_chunked_pass": True,
        "section_family_pass": True,
        "material_model_pass": True,
        "ssi_nonlinear_boundary_active": True,
        "shear_delta_pass": True,
        "source_integrity_pass": True,
        "damper_type_diversity_pass": True,
        "waveform_corr_pass": True,
        "phase_error_pass": True,
        "residual_drift_pass": True,
        "creep_shrinkage_applied": True,
        "differential_shortening_detected": True,
        "initial_stress_nonzero": True,
        "initial_stress_upper_bound_pass": True,
        "drift_guard_pass": True,
        "all_stages_converged": True,
        "shell_beam_mix_topology_pass": True,
        "flexible_diaphragm_modeled": True,
        "flex_amplification_band_pass": True,
        "slab_shear_stress_pass": True,
        "max_flexible_drift_pass": True,
        "seed_locked": True,
        "input_hashes_frozen": True,
        "model_hashes_frozen": True,
        "no_missing_model_artifacts": True,
        "replay_exact_match": True,
        "lock_manifest_written": True,
        "green_reports_pass": True,
        "lock_manifest_hash_match": True,
        "artifact_hashes_present_pass": True,
        "public_key_written_pass": True,
        "signature_generated_pass": True,
        "signature_verified_pass": True,
        "strict_probe_pass": True,
        "nonlinear_frame_gpu_pass": True,
        "ndtha_gpu_pass": True,
        "track_gpu_pass": True,
        "all_main_loops_gpu_pass": True,
        "runtime_truthfulness_pass": True,
        "no_surrogate_runtime_markers_pass": True,
        "solver_hip_production_proof_pass": True,
        "no_cpu_backend_pass": True,
        "no_cpu_required_pass": True,
        "no_cpu_fallback_pass": True,
        "finite_pass": True,
        "all_ranges_pass": True,
        "cracking_case_pass": True,
        "bond_slip_case_pass": True,
        "creep_case_pass": True,
        "slab_wall_case_pass": True,
        "has_nodes": True,
        "has_elements": True,
        "synthetic_source_blocked": True,
        "unknown_section_policy_pass": True,
        "element_skip_budget_pass": True,
        "all_runs_pass": True,
        "run_count_sufficient": True,
        "has_10m_rows": True,
        "latency_cov_pass": True,
        "working_set_cov_pass": True,
        "rust_backend_all_runs_pass": True,
        "elapsed_cov_pass": True,
        "peak_vram_cov_pass": True,
        "stagewise_monotonic_load_pass": True,
    }
    return {
        "contract_pass": True,
        "reason_code": "PASS",
        "summary_line": "Solver breadth: PASS | shell=yes(elems=5,cases=31) | wall=yes(rows=1,cases=14,material=rc_composite) | interface=yes(ssi_nonlinear_boundary) | contact=interface_compression_surrogate",
        "runtime_truthfulness": {
            "solver_path_kind": "explicit_reduced_order_physical",
            "runtime_backend": "numpy",
            "execution_backend": "cpu",
            "cpu_backend": True,
            "cpu_required": True,
            "cpu_fallback_used": False,
            "physical_runtime_declared": True,
            "reduced_order_physical_runtime_used": True,
            "force_jacobian_kernel_consistent": True,
            "surrogate_runtime_used": False,
            "simplified_runtime_used": False,
            "surrogate_runtime_markers": [],
            "contract_pass": True,
        },
        "checks": checks,
        "summary": {
            "fail_count": 0,
            "case_count": 3,
            "duration_hours": 10.0,
            "nonlinear_ratio_span": 0.25,
            "stage_count": 8,
            "sac_case_count": 3,
            "nheri_case_count": 3,
            "support_search_model_types": [
                "friction_pendulum",
                "lead_rubber_bearing",
                "p-y",
                "pile_head",
                "q-z",
                "t-z",
                "tmd",
                "viscoelastic_damper",
                "viscous_damper",
            ],
            "node_to_surface_proxy_model_types": ["friction_pendulum", "lead_rubber_bearing", "p-y", "q-z", "t-z"],
            "support_search_family_types": ["foundation", "device"],
            "node_to_surface_proxy_family_types": ["foundation_proxy", "device_proxy"],
            "support_depth_score": 21,
            "material_model": "rc_composite",
        },
        "artifacts": pbd_artifacts,
        "frontend_payload": {"summary_cards": [1, 2, 3]},
        "material_effect_rows": [
            {"material_model_pass": True},
            {"material_model_pass": True},
            {"material_model_pass": True},
        ],
        "checks": {**checks, "material_model_pass": True},
        "inputs": {
            "noise_seeds": "11,23,47",
            "convergence_seeds": "11,23,47",
            "noise_stiffness_levels_pct": "5,10",
            "convergence_stiffness_levels_pct": "5,10",
            "forbid_toy_cases": True,
            "max_val_mae_pct": 1.0,
            "max_val_mae_pct_track": 1.0,
            "max_val_mae_pct_tunnel": 1.0,
        },
        "validation_metrics": {"mae_pct": 1.0},
        "validation_track_metrics": {"case_count": 1, "mae_pct": 1.0},
        "validation_tunnel_metrics": {"case_count": 1, "mae_pct": 1.0},
        "domain_checks": {
            "overall_val_gate_pass": True,
            "track_val_gate_pass": True,
            "tunnel_val_gate_pass": True,
            "rollout_val_gate_pass": True,
        },
        "runtime": {"cpu_fallback_used": False},
        "lock_manifest": _touch(tmp_path / "lock_manifest.json"),
        "signature": {"public_key_path": _touch(tmp_path / "release_pubkey.pem")},
        "metrics": {
            "node_count": 100,
            "element_count": 100,
            "element_rows_skipped": 0,
            "earthquake_case_count": 7,
            "converged_step_ratio_min": 1.0,
            "energy_balance_relative_error_ref": 0.0,
            "all_cases_converged": True,
        },
        "source_provenance": {"source_family": "midas_mgt"},
    }


def test_run_midas_section_library_validator_tracks_explicit_artifacts(tmp_path: Path) -> None:
    module = _load_module()
    validator = tmp_path / "validator.py"
    validator.write_text(
        "import sys\n"
        "paths = [sys.argv[i + 1] for i, arg in enumerate(sys.argv) if arg == '--path']\n"
        "print(f'ok | {len(paths)}/{len(paths)} used | {len(paths)} templates | source=test-validator | {paths[0]}')\n"
        "raise SystemExit(0)\n",
        encoding="utf-8",
    )
    artifact_a = tmp_path / "a.json"
    artifact_b = tmp_path / "b.json"
    _write_json(artifact_a, {"model": {}})
    _write_json(artifact_b, {"model": {}})

    ok, details = module._run_midas_section_library_validator(
        str(validator),
        [str(artifact_a), str(artifact_b)],
    )

    assert ok is True
    assert details["checked_artifact_count"] == 2
    assert details["artifact_paths"] == [str(artifact_a), str(artifact_b)]
    assert "--path" in details["command"]
    assert details["stdout_lines"]
    assert "source=test-validator" in details["stdout_lines"][0]


def test_run_midas_loadcomb_roundtrip_validator_tracks_explicit_artifacts(tmp_path: Path) -> None:
    module = _load_module()
    validator = tmp_path / "loadcomb_validator.py"
    validator.write_text(
        "import argparse, json\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--model-json', required=True)\n"
        "p.add_argument('--out', required=True)\n"
        "args = p.parse_args()\n"
        "payload = {\n"
        "  'pass': True,\n"
        "  'exact_entry_row_coverage': 1.0,\n"
        "  'exact_header_coverage': 1.0,\n"
        "  'missing_combo_names': [],\n"
        "  'extra_combo_names': [],\n"
        "}\n"
        "open(args.out, 'w', encoding='utf-8').write(json.dumps(payload))\n"
        "print(f'ok | {args.model_json}')\n"
        "raise SystemExit(0)\n",
        encoding="utf-8",
    )
    artifact_a = tmp_path / "a.json"
    artifact_b = tmp_path / "b.json"
    _write_json(artifact_a, {"model": {}})
    _write_json(artifact_b, {"model": {}})

    ok, details = module._run_midas_loadcomb_roundtrip_validator(
        str(validator),
        [str(artifact_a), str(artifact_b)],
    )

    assert ok is True
    assert details["checked_artifact_count"] == 2
    assert details["artifact_paths"] == [str(artifact_a), str(artifact_b)]
    assert details["results"][0]["artifact_path"] == str(artifact_a)
    assert details["results"][0]["exact_entry_row_coverage"] == 1.0
    assert details["results"][1]["exact_header_coverage"] == 1.0
    assert details["summary_line"].startswith("MIDAS loadcomb-roundtrip: ok")


def test_run_midas_kds_geometry_bridge_validator_tracks_explicit_artifacts(tmp_path: Path) -> None:
    module = _load_module()
    validator = tmp_path / "kds_bridge_validator.py"
    validator.write_text(
        "import argparse, json\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--require', action='store_true')\n"
        "p.add_argument('--min-mapped-review-ids', type=int, default=0)\n"
        "p.add_argument('--path', action='append', default=[])\n"
        "p.add_argument('--out')\n"
        "args = p.parse_args()\n"
        "payload = {\n"
        "  'summary_line': 'MIDAS kds-geometry-bridge: ok | mapped_review_ids=36/36 | rows=3168 | strategies=exact:36 | source=test-validator',\n"
        "  'summary': {\n"
        "    'exact_review_load_crosswalk_count_total': 36,\n"
        "    'exact_review_load_crosswalk_expected_total': 36,\n"
        "    'exact_review_semantic_crosswalk_count_total': 36,\n"
        "    'exact_review_semantic_crosswalk_expected_total': 36,\n"
        "    'full_member_crosswalk_count_total': 242,\n"
        "    'full_member_crosswalk_expected_total': 242,\n"
        "    'full_section_crosswalk_count_total': 200,\n"
        "    'full_section_crosswalk_expected_total': 200,\n"
        "    'full_load_crosswalk_count_total': 51,\n"
        "    'full_load_crosswalk_expected_total': 51,\n"
        "  },\n"
        "  'checks': {\n"
        "    'exact_load_crosswalk_pass': True,\n"
        "    'exact_semantic_crosswalk_pass': True,\n"
        "    'full_member_crosswalk_pass': True,\n"
        "    'full_section_crosswalk_pass': True,\n"
        "    'full_load_crosswalk_pass': True,\n"
        "  },\n"
        "}\n"
        "if args.out:\n"
        "  open(args.out, 'w', encoding='utf-8').write(json.dumps(payload))\n"
        "print(payload['summary_line'])\n"
        "raise SystemExit(0)\n",
        encoding="utf-8",
    )
    artifact_a = tmp_path / "a.json"
    artifact_b = tmp_path / "b.json"
    _write_json(artifact_a, {"model": {}})
    _write_json(artifact_b, {"model": {}})

    ok, details = module._run_midas_kds_geometry_bridge_validator(
        str(validator),
        [str(artifact_a), str(artifact_b)],
        min_mapped_review_ids=0,
    )

    assert ok is True
    assert details["checked_artifact_count"] == 2
    assert details["artifact_paths"] == [str(artifact_a), str(artifact_b)]
    assert details["min_mapped_review_ids"] == 0
    assert details["summary_line"].startswith("MIDAS kds-geometry-bridge: ok")
    assert details["structured_report_available"] is True
    assert details["summary"]["full_member_crosswalk_count_total"] == 242
    assert details["summary"]["full_section_crosswalk_count_total"] == 200
    assert details["summary"]["full_load_crosswalk_count_total"] == 51
    assert details["checks"]["full_load_crosswalk_pass"] is True


def test_phase1_ci_gate_reports_section_library_failure(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    strict_path = tmp_path / "strict.json"
    rca_path = tmp_path / "rca.json"
    out_path = tmp_path / "ci_gate_report.json"
    manifest_path = tmp_path / "ci_artifact_manifest.json"
    validator = tmp_path / "validator_fail.py"
    kds_bridge_validator = tmp_path / "kds_bridge_validator_ok.py"
    artifact = tmp_path / "midas_generator_33.json"
    solver_hip = tmp_path / "solver_hip_e2e.json"
    rc_lock = tmp_path / "rc_lock.json"
    _write_json(strict_path, {"strict_rust_hip_pass": True})
    _write_json(rca_path, {"timing_breakdown_seconds": {"compute": 1.0, "host_copy": 0.05, "serialization": 0.05}})
    _write_json(artifact, {"model": {"metadata": {}}})
    _write_json(solver_hip, {})
    _write_json(rc_lock, {})
    validator.write_text("print('missing | missing | source=n/a | fail')\nraise SystemExit(1)\n", encoding="utf-8")
    kds_bridge_validator.write_text(
        "print('MIDAS kds-geometry-bridge: ok | mapped_review_ids=0/12 | rows=1056 | strategies=unmapped:12 | source=test-validator')\nraise SystemExit(0)\n",
        encoding="utf-8",
    )
    passing_payload = _passing_gate_payload(tmp_path)

    monkeypatch.setattr(module, "_validate_contract_artifacts", lambda paths: (True, []))
    monkeypatch.setattr(module, "_validate_priority3", lambda path: (True, None, None))
    monkeypatch.setattr(module, "_validate_extended_contracts", lambda *args: tuple([True] * 21))
    monkeypatch.setattr(module, "_load_json", lambda path: passing_payload)

    exit_code = module.main(
        [
            "--strict-probe",
            str(strict_path),
            "--rca",
            str(rca_path),
            "--out",
            str(out_path),
            "--manifest",
            str(manifest_path),
            "--required-contracts",
            "--midas-section-library-validator",
            str(validator),
            "--midas-section-library-artifact",
            str(artifact),
            "--midas-kds-geometry-bridge-validator",
            str(kds_bridge_validator),
            "--midas-kds-geometry-bridge-artifact",
            str(artifact),
            "--solver-hip-e2e",
            str(solver_hip),
            "--rc-benchmark-lock",
            str(rc_lock),
        ]
    )

    report = json.loads(out_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert exit_code == 1
    assert report["reason_code"] == "ERR_MIDAS_SECTION_LIBRARY_ARTIFACT_FAIL"
    assert report["midas_section_library_artifacts_pass"] is False
    assert report["midas_section_library_summary_line"].startswith("MIDAS section-library: missing")
    assert report["midas_section_library_validator"]["artifact_paths"] == [str(artifact)]
    assert report["midas_section_library_validator"]["checked_artifact_count"] == 1
    assert str(validator) in manifest["artifacts"]
    assert str(artifact) in manifest["artifacts"]


def test_phase1_ci_gate_reports_loadcomb_roundtrip_failure(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    strict_path = tmp_path / "strict.json"
    rca_path = tmp_path / "rca.json"
    out_path = tmp_path / "ci_gate_report.json"
    manifest_path = tmp_path / "ci_artifact_manifest.json"
    section_validator = tmp_path / "section_validator_ok.py"
    kds_bridge_validator = tmp_path / "kds_bridge_validator_ok.py"
    loadcomb_validator = tmp_path / "loadcomb_validator_fail.py"
    artifact = tmp_path / "midas_generator_33.json"
    solver_hip = tmp_path / "solver_hip_e2e.json"
    rc_lock = tmp_path / "rc_lock.json"
    _write_json(strict_path, {"strict_rust_hip_pass": True})
    _write_json(rca_path, {"timing_breakdown_seconds": {"compute": 1.0, "host_copy": 0.05, "serialization": 0.05}})
    _write_json(artifact, {"model": {"metadata": {"section_library": {"summary": {"used_section_count": 1}}}}})
    _write_json(solver_hip, {})
    _write_json(rc_lock, {})
    section_validator.write_text(
        "print('ok | 1/1 used | 1 templates | source=test-validator | ok')\nraise SystemExit(0)\n",
        encoding="utf-8",
    )
    kds_bridge_validator.write_text(
        "print('MIDAS kds-geometry-bridge: ok | mapped_review_ids=0/12 | rows=1056 | strategies=unmapped:12 | source=test-validator')\nraise SystemExit(0)\n",
        encoding="utf-8",
    )
    loadcomb_validator.write_text(
        "import argparse, json\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--model-json', required=True)\n"
        "p.add_argument('--out', required=True)\n"
        "args = p.parse_args()\n"
        "payload = {\n"
        "  'pass': False,\n"
        "  'exact_entry_row_coverage': 0.5,\n"
        "  'exact_header_coverage': 1.0,\n"
        "  'missing_combo_names': ['ULS1'],\n"
        "  'extra_combo_names': [],\n"
        "}\n"
        "open(args.out, 'w', encoding='utf-8').write(json.dumps(payload))\n"
        "raise SystemExit(1)\n",
        encoding="utf-8",
    )
    passing_payload = _passing_gate_payload(tmp_path)

    monkeypatch.setattr(module, "_validate_contract_artifacts", lambda paths: (True, []))
    monkeypatch.setattr(module, "_validate_priority3", lambda path: (True, None, None))
    monkeypatch.setattr(module, "_validate_extended_contracts", lambda *args: tuple([True] * 21))
    monkeypatch.setattr(module, "_load_json", lambda path: passing_payload)

    exit_code = module.main(
        [
            "--strict-probe",
            str(strict_path),
            "--rca",
            str(rca_path),
            "--out",
            str(out_path),
            "--manifest",
            str(manifest_path),
            "--required-contracts",
            "--midas-section-library-validator",
            str(section_validator),
            "--midas-section-library-artifact",
            str(artifact),
            "--midas-kds-geometry-bridge-validator",
            str(kds_bridge_validator),
            "--midas-kds-geometry-bridge-artifact",
            str(artifact),
            "--midas-loadcomb-roundtrip-validator",
            str(loadcomb_validator),
            "--midas-loadcomb-roundtrip-artifact",
            str(artifact),
            "--solver-hip-e2e",
            str(solver_hip),
            "--rc-benchmark-lock",
            str(rc_lock),
        ]
    )

    report = json.loads(out_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert exit_code == 1
    assert report["reason_code"] == "ERR_MIDAS_LOADCOMB_ROUNDTRIP_FAIL"
    assert report["midas_section_library_artifacts_pass"] is True
    assert report["midas_loadcomb_roundtrip_pass"] is False
    assert report["midas_loadcomb_roundtrip_summary_line"].startswith("MIDAS loadcomb-roundtrip: check")
    assert report["midas_loadcomb_roundtrip_validator"]["artifact_paths"] == [str(artifact)]
    assert report["midas_loadcomb_roundtrip_validator"]["results"][0]["missing_combo_count"] == 1
    assert str(loadcomb_validator) in manifest["artifacts"]
    assert str(artifact) in manifest["artifacts"]


def test_phase1_ci_gate_passes_with_green_section_library_validator(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    strict_path = tmp_path / "strict.json"
    rca_path = tmp_path / "rca.json"
    out_path = tmp_path / "ci_gate_report.json"
    manifest_path = tmp_path / "ci_artifact_manifest.json"
    validator = tmp_path / "validator_ok.py"
    kds_bridge_validator = tmp_path / "kds_bridge_validator_ok.py"
    loadcomb_validator = tmp_path / "loadcomb_validator_ok.py"
    artifact = tmp_path / "midas_generator_33.json"
    solver_hip = tmp_path / "solver_hip_e2e.json"
    solver_truthfulness = tmp_path / "solver_truthfulness_gate_report.json"
    rc_lock = tmp_path / "rc_lock.json"
    _write_json(strict_path, {"strict_rust_hip_pass": True})
    _write_json(rca_path, {"timing_breakdown_seconds": {"compute": 1.0, "host_copy": 0.05, "serialization": 0.05}})
    _write_json(artifact, {"model": {"metadata": {"section_library": {"summary": {"used_section_count": 1}}}}})
    _write_json(solver_hip, {})
    _write_json(solver_truthfulness, {})
    _write_json(rc_lock, {})
    validator.write_text(
        "import sys\n"
        "paths = [sys.argv[i + 1] for i, arg in enumerate(sys.argv) if arg == '--path']\n"
        "print(f'ok | 1/1 used | 1 templates | source=test-validator | {paths[0]}')\n"
        "raise SystemExit(0)\n",
        encoding="utf-8",
    )
    kds_bridge_validator.write_text(
        "import argparse, json\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--require', action='store_true')\n"
        "p.add_argument('--min-mapped-review-ids', type=int, default=0)\n"
        "p.add_argument('--path', action='append', default=[])\n"
        "p.add_argument('--out')\n"
        "args = p.parse_args()\n"
        "payload = {\n"
        "  'summary_line': 'MIDAS kds-geometry-bridge: ok | mapped_review_ids=36/36 | rows=3168 | strategies=exact:36 | source=test-validator | load_crosswalk=12/12 PASS | semantic_crosswalk=12/12 PASS',\n"
        "  'summary': {\n"
        "    'exact_review_load_crosswalk_count_total': 36,\n"
        "    'exact_review_load_crosswalk_expected_total': 36,\n"
        "    'exact_review_semantic_crosswalk_count_total': 36,\n"
        "    'exact_review_semantic_crosswalk_expected_total': 36,\n"
        "    'full_member_crosswalk_count_total': 242,\n"
        "    'full_member_crosswalk_expected_total': 242,\n"
        "    'full_section_crosswalk_count_total': 200,\n"
        "    'full_section_crosswalk_expected_total': 200,\n"
        "    'full_load_crosswalk_count_total': 51,\n"
        "    'full_load_crosswalk_expected_total': 51,\n"
        "  },\n"
        "  'checks': {\n"
        "    'exact_load_crosswalk_pass': True,\n"
        "    'exact_semantic_crosswalk_pass': True,\n"
        "    'full_member_crosswalk_pass': True,\n"
        "    'full_section_crosswalk_pass': True,\n"
        "    'full_load_crosswalk_pass': True,\n"
        "  },\n"
        "}\n"
        "if args.out:\n"
        "  open(args.out, 'w', encoding='utf-8').write(json.dumps(payload))\n"
        "print(payload['summary_line'])\n"
        "raise SystemExit(0)\n",
        encoding="utf-8",
    )
    loadcomb_validator.write_text(
        "import argparse, json\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--model-json', required=True)\n"
        "p.add_argument('--out', required=True)\n"
        "args = p.parse_args()\n"
        "payload = {\n"
        "  'pass': True,\n"
        "  'exact_entry_row_coverage': 1.0,\n"
        "  'exact_header_coverage': 1.0,\n"
        "  'missing_combo_names': [],\n"
        "  'extra_combo_names': [],\n"
        "}\n"
        "open(args.out, 'w', encoding='utf-8').write(json.dumps(payload))\n"
        "raise SystemExit(0)\n",
        encoding="utf-8",
    )
    passing_payload = _passing_gate_payload(tmp_path)

    monkeypatch.setattr(module, "_validate_contract_artifacts", lambda paths: (True, []))
    monkeypatch.setattr(module, "_validate_priority3", lambda path: (True, None, None))
    monkeypatch.setattr(module, "_validate_extended_contracts", lambda *args: tuple([True] * 21))
    monkeypatch.setattr(module, "_load_json", lambda path: passing_payload)

    exit_code = module.main(
        [
            "--strict-probe",
            str(strict_path),
            "--rca",
            str(rca_path),
            "--out",
            str(out_path),
            "--manifest",
            str(manifest_path),
            "--required-contracts",
            "--midas-section-library-validator",
            str(validator),
            "--midas-section-library-artifact",
            str(artifact),
            "--midas-kds-geometry-bridge-validator",
            str(kds_bridge_validator),
            "--midas-kds-geometry-bridge-artifact",
            str(artifact),
            "--midas-loadcomb-roundtrip-validator",
            str(loadcomb_validator),
            "--midas-loadcomb-roundtrip-artifact",
            str(artifact),
            "--solver-hip-e2e",
            str(solver_hip),
            "--solver-truthfulness",
            str(solver_truthfulness),
            "--rc-benchmark-lock",
            str(rc_lock),
        ]
    )

    report = json.loads(out_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert report["midas_section_library_artifacts_pass"] is True
    assert report["midas_kds_geometry_bridge_pass"] is True
    assert report["midas_loadcomb_roundtrip_pass"] is True
    assert report["solver_breadth_pass"] is True
    assert report["element_material_breadth_pass"] is True
    assert report["contact_readiness_pass"] is True
    assert (
        report["support_search_summary_line"]
        == "Support search: PASS | support_search=9 | node_surface_proxy=5 | support_depth=21 | support_families=2 | proxy_families=2"
    )
    assert report["support_search_count"] == 9
    assert report["support_families_count"] == 2
    assert report["proxy_families_count"] == 2
    assert (
        report["general_fe_contact_surface_summary_line"]
        == "General FE compact: PASS | support_search=9 | node_surface_proxy=5 | support_depth=21 | coupling_depth=0 | support_families=2 | proxy_families=2"
    )
    assert report["general_fe_contact_surface_status"] == "PASS"
    assert report["general_fe_contact_support_search_count"] == 9
    assert report["general_fe_contact_node_surface_proxy_count"] == 5
    assert report["general_fe_contact_support_depth_score"] == 21
    assert report["general_fe_contact_coupling_depth_score"] == 0
    assert report["general_fe_contact_support_family_count"] == 2
    assert report["general_fe_contact_proxy_family_count"] == 2
    assert report["general_fe_contact_surface_pass"] is True
    assert report["structural_contact_required"] is False
    assert report["midas_interoperability_pass"] is True
    assert report["all_pass"] is True
    assert report["reason_code"] == "PASS"
    assert report["workflow_results_explorer_traceability_pass"] is True
    assert report["midas_section_library_summary_line"].startswith("MIDAS section-library: ok")
    assert report["midas_kds_geometry_bridge_summary_line"].startswith("MIDAS kds-geometry-bridge: ok")
    assert report["midas_kds_geometry_bridge_load_crosswalk_summary_line"] == "load_crosswalk=36/36 PASS"
    assert report["midas_kds_geometry_bridge_load_crosswalk_count"] == 36
    assert report["midas_kds_geometry_bridge_load_crosswalk_expected"] == 36
    assert report["midas_kds_geometry_bridge_load_crosswalk_status"] == "PASS"
    assert report["midas_kds_geometry_bridge_load_crosswalk_pass"] is True
    assert report["midas_kds_geometry_bridge_semantic_crosswalk_summary_line"] == "semantic_crosswalk=36/36 PASS"
    assert report["midas_kds_geometry_bridge_semantic_crosswalk_count"] == 36
    assert report["midas_kds_geometry_bridge_semantic_crosswalk_expected"] == 36
    assert report["midas_kds_geometry_bridge_semantic_crosswalk_status"] == "PASS"
    assert report["midas_kds_geometry_bridge_semantic_crosswalk_pass"] is True
    assert report["midas_kds_geometry_bridge_full_member_crosswalk_summary_line"] == "full_member_crosswalk=242/242 PASS"
    assert report["midas_kds_geometry_bridge_full_member_crosswalk_count"] == 242
    assert report["midas_kds_geometry_bridge_full_member_crosswalk_expected"] == 242
    assert report["midas_kds_geometry_bridge_full_member_crosswalk_status"] == "PASS"
    assert report["midas_kds_geometry_bridge_full_member_crosswalk_pass"] is True
    assert report["midas_kds_geometry_bridge_full_section_crosswalk_summary_line"] == "full_section_crosswalk=200/200 PASS"
    assert report["midas_kds_geometry_bridge_full_section_crosswalk_count"] == 200
    assert report["midas_kds_geometry_bridge_full_section_crosswalk_expected"] == 200
    assert report["midas_kds_geometry_bridge_full_section_crosswalk_status"] == "PASS"
    assert report["midas_kds_geometry_bridge_full_section_crosswalk_pass"] is True
    assert report["midas_kds_geometry_bridge_full_load_crosswalk_summary_line"] == "full_load_crosswalk=51/51 PASS"
    assert report["midas_kds_geometry_bridge_full_load_crosswalk_count"] == 51
    assert report["midas_kds_geometry_bridge_full_load_crosswalk_expected"] == 51
    assert report["midas_kds_geometry_bridge_full_load_crosswalk_status"] == "PASS"
    assert report["midas_kds_geometry_bridge_full_load_crosswalk_pass"] is True
    assert report["midas_kds_geometry_bridge_full_crosswalk_depth"] == 36
    assert report["midas_kds_geometry_bridge_validator"]["load_crosswalk_summary_line"] == "load_crosswalk=36/36 PASS"
    assert report["midas_kds_geometry_bridge_validator"]["semantic_crosswalk_summary_line"] == "semantic_crosswalk=36/36 PASS"
    assert report["midas_kds_geometry_bridge_validator"]["full_member_crosswalk_summary_line"] == "full_member_crosswalk=242/242 PASS"
    assert report["midas_kds_geometry_bridge_validator"]["full_section_crosswalk_summary_line"] == "full_section_crosswalk=200/200 PASS"
    assert report["midas_kds_geometry_bridge_validator"]["full_load_crosswalk_summary_line"] == "full_load_crosswalk=51/51 PASS"
    assert report["midas_kds_geometry_bridge_validator"]["full_crosswalk_depth"] == 36
    assert report["ndtha_step_series_depth"] == 2400
    assert report["midas_loadcomb_roundtrip_summary_line"].startswith("MIDAS loadcomb-roundtrip: ok")
    assert report["solver_breadth_summary_line"].startswith("Solver breadth: PASS")
    assert report["midas_section_library_validator"]["stdout_lines"]


def test_phase1_ci_gate_reports_kds_geometry_bridge_failure(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    strict_path = tmp_path / "strict.json"
    rca_path = tmp_path / "rca.json"
    out_path = tmp_path / "ci_gate_report.json"
    manifest_path = tmp_path / "ci_artifact_manifest.json"
    section_validator = tmp_path / "section_validator_ok.py"
    kds_bridge_validator = tmp_path / "kds_bridge_validator_fail.py"
    loadcomb_validator = tmp_path / "loadcomb_validator_ok.py"
    artifact = tmp_path / "midas_generator_33.json"
    solver_hip = tmp_path / "solver_hip_e2e.json"
    rc_lock = tmp_path / "rc_lock.json"
    _write_json(strict_path, {"strict_rust_hip_pass": True})
    _write_json(rca_path, {"timing_breakdown_seconds": {"compute": 1.0, "host_copy": 0.05, "serialization": 0.05}})
    _write_json(artifact, {"model": {"metadata": {"section_library": {"summary": {"used_section_count": 1}}, "kds_geometry_bridge": {"summary": {"review_id_count": 12, "mapped_review_id_count": 0}}}}})
    _write_json(solver_hip, {})
    _write_json(rc_lock, {})
    section_validator.write_text(
        "print('ok | 1/1 used | 1 templates | source=test-validator | ok')\nraise SystemExit(0)\n",
        encoding="utf-8",
    )
    kds_bridge_validator.write_text(
        "print('MIDAS kds-geometry-bridge: missing | mapped_review_ids=0/12 | rows=1056 | strategies=unmapped:12 | source=test-validator')\nraise SystemExit(1)\n",
        encoding="utf-8",
    )
    loadcomb_validator.write_text(
        "import argparse, json\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--model-json', required=True)\n"
        "p.add_argument('--out', required=True)\n"
        "args = p.parse_args()\n"
        "open(args.out, 'w', encoding='utf-8').write(json.dumps({'pass': True, 'exact_entry_row_coverage': 1.0, 'exact_header_coverage': 1.0, 'missing_combo_names': [], 'extra_combo_names': []}))\n"
        "raise SystemExit(0)\n",
        encoding="utf-8",
    )
    passing_payload = _passing_gate_payload(tmp_path)

    monkeypatch.setattr(module, "_validate_contract_artifacts", lambda paths: (True, []))
    monkeypatch.setattr(module, "_validate_priority3", lambda path: (True, None, None))
    monkeypatch.setattr(module, "_validate_extended_contracts", lambda *args: tuple([True] * 21))
    monkeypatch.setattr(module, "_load_json", lambda path: passing_payload)

    exit_code = module.main(
        [
            "--strict-probe",
            str(strict_path),
            "--rca",
            str(rca_path),
            "--out",
            str(out_path),
            "--manifest",
            str(manifest_path),
            "--required-contracts",
            "--midas-section-library-validator",
            str(section_validator),
            "--midas-section-library-artifact",
            str(artifact),
            "--midas-kds-geometry-bridge-validator",
            str(kds_bridge_validator),
            "--midas-kds-geometry-bridge-artifact",
            str(artifact),
            "--midas-loadcomb-roundtrip-validator",
            str(loadcomb_validator),
            "--midas-loadcomb-roundtrip-artifact",
            str(artifact),
            "--solver-hip-e2e",
            str(solver_hip),
            "--rc-benchmark-lock",
            str(rc_lock),
        ]
    )

    report = json.loads(out_path.read_text(encoding="utf-8"))

    assert exit_code == 1
    assert report["reason_code"] == "ERR_MIDAS_KDS_GEOMETRY_BRIDGE_FAIL"
    assert report["midas_section_library_artifacts_pass"] is True
    assert report["midas_kds_geometry_bridge_pass"] is False
    assert report["midas_kds_geometry_bridge_summary_line"].startswith("MIDAS kds-geometry-bridge: missing")


def test_phase1_ci_gate_reports_nonlinear_generalization_failure(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    strict_path = tmp_path / "strict.json"
    rca_path = tmp_path / "rca.json"
    out_path = tmp_path / "ci_gate_report.json"
    manifest_path = tmp_path / "ci_artifact_manifest.json"
    passing_payload = _passing_gate_payload(tmp_path)

    def _load_json(path: str) -> dict:
        payload = dict(passing_payload)
        payload["checks"] = dict(passing_payload["checks"])
        if str(path).endswith("nonlinear_generalization_gate_report.json"):
            payload["checks"]["beam_column_generalization_pass"] = False
            payload["summary_line"] = "Nonlinear generalization: CHECK | beam=no"
            payload["contract_pass"] = False
        return payload

    _write_json(strict_path, {"strict_rust_hip_pass": True})
    _write_json(rca_path, {"timing_breakdown_seconds": {"compute": 1.0, "host_copy": 0.05, "serialization": 0.05}})

    monkeypatch.setattr(module, "_validate_contract_artifacts", lambda paths: (True, []))
    monkeypatch.setattr(module, "_validate_priority3", lambda path: (True, None, None))
    monkeypatch.setattr(module, "_validate_extended_contracts", lambda *args: tuple([True] * 21))
    monkeypatch.setattr(module, "_load_json", _load_json)

    exit_code = module.main(
        [
            "--strict-probe",
            str(strict_path),
            "--rca",
            str(rca_path),
            "--out",
            str(out_path),
            "--manifest",
            str(manifest_path),
            "--required-contracts",
        ]
    )

    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert report["reason_code"] == "ERR_NONLINEAR_GENERALIZATION_FAIL"
    assert report["nonlinear_generalization_pass"] is False


def test_phase1_ci_gate_reports_workflow_productization_failure(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    strict_path = tmp_path / "strict.json"
    rca_path = tmp_path / "rca.json"
    out_path = tmp_path / "ci_gate_report.json"
    manifest_path = tmp_path / "ci_artifact_manifest.json"
    passing_payload = _passing_gate_payload(tmp_path)

    def _load_json(path: str) -> dict:
        payload = dict(passing_payload)
        payload["checks"] = dict(passing_payload["checks"])
        if str(path).endswith("workflow_productization_gate_report.json"):
            payload["checks"]["results_explorer_traceability_pass"] = False
            payload["summary_line"] = "Workflow/interoperability productization: CHECK | results_explorer=no"
            payload["contract_pass"] = False
        return payload

    _write_json(strict_path, {"strict_rust_hip_pass": True})
    _write_json(rca_path, {"timing_breakdown_seconds": {"compute": 1.0, "host_copy": 0.05, "serialization": 0.05}})

    monkeypatch.setattr(module, "_validate_contract_artifacts", lambda paths: (True, []))
    monkeypatch.setattr(module, "_validate_priority3", lambda path: (True, None, None))
    monkeypatch.setattr(module, "_validate_extended_contracts", lambda *args: tuple([True] * 21))
    monkeypatch.setattr(module, "_load_json", _load_json)

    exit_code = module.main(
        [
            "--strict-probe",
            str(strict_path),
            "--rca",
            str(rca_path),
            "--out",
            str(out_path),
            "--manifest",
            str(manifest_path),
            "--required-contracts",
        ]
    )

    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert report["reason_code"] == "ERR_WORKFLOW_PRODUCTIZATION_FAIL"
    assert report["workflow_productization_pass"] is False
    assert report["workflow_results_explorer_traceability_pass"] is False


def test_phase1_ci_gate_surfaces_solver_truthfulness_summary(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    strict_path = tmp_path / "strict.json"
    rca_path = tmp_path / "rca.json"
    out_path = tmp_path / "ci_gate_report.json"
    manifest_path = tmp_path / "ci_artifact_manifest.json"
    passing_payload = _passing_gate_payload(tmp_path)
    truthfulness_report = tmp_path / "solver_truthfulness_gate_report.json"
    truthfulness_summary_line = (
        "Solver truthfulness: PASS | reports=4/4 | explicit=4/4 | surrogate_free=4/4 | cpu_fallback=0/4"
    )
    truthfulness_payload = {
        "schema_version": "1.0",
        "run_id": "solver-truthfulness-gate",
        "generated_at": "2026-03-30T00:00:00+00:00",
        "contract_pass": True,
        "reason_code": "PASS",
        "reason": "truthful runtime path verified",
        "summary_line": truthfulness_summary_line,
        "checks": {
            "runtime_truthfulness_pass": True,
            "no_surrogate_runtime_markers_pass": True,
            "no_cpu_fallback_pass": True,
        },
        "summary": {
            "runtime_report_count": 4,
            "truthful_runtime_count": 4,
            "surrogate_marker_count": 0,
            "cpu_fallback_count": 0,
        },
    }

    def _load_json(path: str) -> dict:
        payload = dict(passing_payload)
        payload["checks"] = dict(passing_payload["checks"])
        if str(path).endswith("solver_truthfulness_gate_report.json"):
            return dict(truthfulness_payload)
        return payload

    _write_json(strict_path, {"strict_rust_hip_pass": True})
    _write_json(rca_path, {"timing_breakdown_seconds": {"compute": 1.0, "host_copy": 0.05, "serialization": 0.05}})
    _write_json(truthfulness_report, truthfulness_payload)

    monkeypatch.setattr(module, "_validate_contract_artifacts", lambda paths: (True, []))
    monkeypatch.setattr(module, "_validate_priority3", lambda path: (True, None, None))
    monkeypatch.setattr(module, "_validate_extended_contracts", lambda *args: tuple([True] * 21))
    monkeypatch.setattr(module, "_load_json", _load_json)

    exit_code = module.main(
        [
            "--strict-probe",
            str(strict_path),
            "--rca",
            str(rca_path),
            "--out",
            str(out_path),
            "--manifest",
            str(manifest_path),
            "--required-contracts",
            "--solver-truthfulness",
            str(truthfulness_report),
        ]
    )

    report = json.loads(out_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert report["reason_code"] == "PASS"
    assert report["solver_truthfulness_pass"] is True
    assert report["solver_truthfulness_summary_line"] == truthfulness_summary_line
    assert report["committee_summary_snapshot"]["solver_truthfulness_summary_line"] == truthfulness_summary_line
    assert report["reports"]["solver_truthfulness"].endswith("solver_truthfulness_gate_report.json")
    assert str(truthfulness_report) in manifest["artifacts"]


def test_phase1_ci_gate_surfaces_performance_profiling_summary(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    strict_path = tmp_path / "strict.json"
    rca_path = tmp_path / "rca.json"
    out_path = tmp_path / "ci_gate_report.json"
    manifest_path = tmp_path / "ci_artifact_manifest.json"
    performance_report = tmp_path / "performance_profiling_gate_report.json"
    passing_payload = _passing_gate_payload(tmp_path)
    performance_summary_line = (
        "Performance profiling: PASS | ndtha=103.19s(cov=0.003,vram=0.0MB) | "
        "ssi_contact=160steps/1.64iters/newton=1052 | moving_load=euler=1.304s,timo=0.001s,warmup=1809.3x | "
        "gpu_host_ops=2 unavoidable/0 optimizable | "
        "sprint=3(ndtha_partitioned_runtime,ssi_contact_convergence_path,moving_load_kernel_warmup_observability)"
    )
    performance_payload = {
        "schema_version": "1.0",
        "generated_at": "2026-04-05T00:00:00+00:00",
        "contract_pass": True,
        "reason_code": "PASS",
        "reason": "performance profiling baselines, bottleneck map, and sprint targets are ready",
        "summary_line": performance_summary_line,
        "checks": {
            "p0_engine_baseline_pass": True,
            "gpu_bottleneck_audit_pass": True,
            "ndtha_long_profile_pass": True,
            "ssi_contact_runtime_evidence_pass": True,
            "moving_load_runtime_evidence_pass": True,
            "bottleneck_map_present_pass": True,
            "sprint_target_count_pass": True,
        },
        "summary": {
            "ndtha_elapsed_wall_s_mean": 103.19,
            "gpu_unavoidable_host_ops_count": 2,
            "gpu_optimizable_host_ops_count": 0,
            "first_sprint_target_count": 3,
            "first_sprint_target_ids": [
                "ndtha_partitioned_runtime",
                "ssi_contact_convergence_path",
                "moving_load_kernel_warmup_observability",
            ],
        },
        "bottleneck_map": [
            {"target_id": "ndtha_partitioned_runtime"},
            {"target_id": "ssi_contact_convergence_path"},
            {"target_id": "moving_load_kernel_warmup_observability"},
        ],
        "sprint_targets": [
            {"target_id": "ndtha_partitioned_runtime"},
            {"target_id": "ssi_contact_convergence_path"},
            {"target_id": "moving_load_kernel_warmup_observability"},
        ],
    }

    def _load_json(path: str) -> dict:
        payload = dict(passing_payload)
        payload["checks"] = dict(passing_payload["checks"])
        if str(path).endswith("performance_profiling_gate_report.json"):
            return dict(performance_payload)
        return payload

    _write_json(strict_path, {"strict_rust_hip_pass": True})
    _write_json(rca_path, {"timing_breakdown_seconds": {"compute": 1.0, "host_copy": 0.05, "serialization": 0.05}})
    _write_json(performance_report, performance_payload)

    monkeypatch.setattr(module, "_validate_contract_artifacts", lambda paths: (True, []))
    monkeypatch.setattr(module, "_validate_priority3", lambda path: (True, None, None))
    monkeypatch.setattr(module, "_validate_extended_contracts", lambda *args: tuple([True] * 21))
    monkeypatch.setattr(module, "_load_json", _load_json)

    exit_code = module.main(
        [
            "--strict-probe",
            str(strict_path),
            "--rca",
            str(rca_path),
            "--out",
            str(out_path),
            "--manifest",
            str(manifest_path),
            "--required-contracts",
            "--performance-profiling-report",
            str(performance_report),
        ]
    )

    report = json.loads(out_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert report["reason_code"] == "PASS"
    assert report["performance_profiling_pass"] is True
    assert report["performance_profiling_summary_line"] == performance_summary_line
    assert report["committee_summary_snapshot"]["performance_profiling_summary_line"] == performance_summary_line
    assert report["reports"]["performance_profiling"].endswith("performance_profiling_gate_report.json")
    assert str(performance_report) in manifest["artifacts"]


def test_phase1_ci_gate_surfaces_hardest_external_10case_kickoff_summary(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    strict_path = tmp_path / "strict.json"
    rca_path = tmp_path / "rca.json"
    out_path = tmp_path / "ci_gate_report.json"
    manifest_path = tmp_path / "ci_artifact_manifest.json"
    kickoff_report = tmp_path / "hardest_external_10case_kickoff_gate_report.json"
    passing_payload = _passing_gate_payload(tmp_path)
    kickoff_summary_line = (
        "Hardest external 10-case kickoff: PASS | ready=10/10 | start_now=yes | "
        "mode=start_now_limited_external_benchmark | full_submission=no | review_pending=2 | "
        "measured_families=8 | measured_cases=120"
    )
    kickoff_payload = {
        "schema_version": "1.0",
        "generated_at": "2026-03-30T00:00:00+00:00",
        "contract_pass": True,
        "reason_code": "PASS",
        "reason": "kickoff boundary ready",
        "summary_line": kickoff_summary_line,
        "summary": {
            "case_count": 10,
            "ready_case_count": 10,
            "blocked_case_count": 0,
            "ready_to_start_now": True,
            "ready_to_start_full_submission_now": False,
            "recommended_start_mode": "start_now_limited_external_benchmark",
            "audit_review_queue_pending_count": 2,
            "measured_source_family_count": 8,
            "measured_case_count": 120,
        },
        "checks": {
            "base_boundary_pass": True,
            "ready_cases_pass": True,
        },
    }

    def _load_json(path: str) -> dict:
        payload = dict(passing_payload)
        payload["checks"] = dict(passing_payload["checks"])
        if str(path).endswith("hardest_external_10case_kickoff_gate_report.json"):
            return dict(kickoff_payload)
        return payload

    _write_json(strict_path, {"strict_rust_hip_pass": True})
    _write_json(rca_path, {"timing_breakdown_seconds": {"compute": 1.0, "host_copy": 0.05, "serialization": 0.05}})
    _write_json(kickoff_report, kickoff_payload)

    monkeypatch.setattr(module, "_validate_contract_artifacts", lambda paths: (True, []))
    monkeypatch.setattr(module, "_validate_priority3", lambda path: (True, None, None))
    monkeypatch.setattr(module, "_validate_extended_contracts", lambda *args: tuple([True] * 21))
    monkeypatch.setattr(module, "_load_json", _load_json)

    exit_code = module.main(
        [
            "--strict-probe",
            str(strict_path),
            "--rca",
            str(rca_path),
            "--out",
            str(out_path),
            "--manifest",
            str(manifest_path),
            "--required-contracts",
            "--hardest-external-10case-kickoff-report",
            str(kickoff_report),
        ]
    )

    report = json.loads(out_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert report["reason_code"] == "PASS"
    assert report["hardest_external_10case_kickoff_pass"] is True
    assert report["hardest_external_10case_kickoff_summary_line"] == kickoff_summary_line
    assert (
        report["committee_summary_snapshot"]["hardest_external_10case_kickoff_summary_line"]
        == kickoff_summary_line
    )
    assert report["reports"]["hardest_external_10case_kickoff"].endswith(
        "hardest_external_10case_kickoff_gate_report.json"
    )
    assert str(kickoff_report) in manifest["artifacts"]


def test_phase1_ci_gate_surfaces_midas_native_roundtrip_summary(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    strict_path = tmp_path / "strict.json"
    rca_path = tmp_path / "rca.json"
    out_path = tmp_path / "ci_gate_report.json"
    manifest_path = tmp_path / "ci_artifact_manifest.json"
    native_roundtrip_report = tmp_path / "midas_native_roundtrip_gate_report.json"
    exact_roundtrip_closure_report = tmp_path / "midas_exact_roundtrip_closure_gate_report.json"
    passing_payload = _passing_gate_payload(tmp_path)
    native_roundtrip_summary_line = (
        "MIDAS native roundtrip: PASS | corpus=6 | native_text=1 | archives=4 | "
        "ready=1 | receipts=1/1 | topology=1/1 | load=1/1 | loadcomb=1/1 exact | pending_review=2"
    )
    exact_roundtrip_closure_summary_line = (
        "MIDAS exact roundtrip closure: CHECK | exact=5/6 | canonical=1 | lossy=0 | "
        "unsupported=0 | manual=0 | pending_review=0 | exact_queue=0/0 | "
        "limits=solver_ready_reconstruction_pending"
    )
    native_roundtrip_payload = {
        "schema_version": "1.0",
        "generated_at": "2026-03-31T00:00:00+00:00",
        "contract_pass": True,
        "reason_code": "PASS",
        "reason": "native roundtrip ready",
        "summary_line": native_roundtrip_summary_line,
        "summary": {
            "corpus_case_count": 6,
            "native_text_case_count": 1,
            "archive_case_count": 4,
            "native_writeback_ready_count": 1,
            "receipt_count": 1,
            "pending_review_total": 2,
        },
        "checks": {
            "corpus_manifest_present_pass": True,
            "native_text_case_present_pass": True,
            "native_writeback_ready_pass": True,
            "diff_receipt_coverage_pass": True,
            "per_case_writeback_pass": True,
            "topology_stability_pass": True,
            "load_contract_stability_pass": True,
            "loadcomb_exact_roundtrip_pass": True,
            "unknown_rows_zero_pass": True,
        },
    }
    exact_roundtrip_closure_payload = {
        "schema_version": "1.0",
        "generated_at": "2026-04-11T00:00:00+00:00",
        "contract_pass": False,
        "reason_code": "ERR_EXACT_CLOSURE_PENDING",
        "reason": "exact roundtrip closure still pending",
        "summary_line": exact_roundtrip_closure_summary_line,
        "summary": {
            "ready_case_count": 6,
            "exact_case_count": 5,
            "canonical_rewrite_case_count": 1,
            "remaining_limits": ["solver_ready_reconstruction_pending"],
        },
        "checks": {
            "native_roundtrip_gate_pass": True,
            "interoperability_gate_pass": True,
            "all_ready_cases_exact_pass": False,
            "canonical_rewrite_zero_pass": False,
            "remaining_limits_zero_pass": False,
        },
    }

    def _load_json(path: str) -> dict:
        payload = dict(passing_payload)
        payload["checks"] = dict(passing_payload["checks"])
        if str(path).endswith("midas_native_roundtrip_gate_report.json"):
            return dict(native_roundtrip_payload)
        if str(path).endswith("midas_exact_roundtrip_closure_gate_report.json"):
            return dict(exact_roundtrip_closure_payload)
        return payload

    _write_json(strict_path, {"strict_rust_hip_pass": True})
    _write_json(rca_path, {"timing_breakdown_seconds": {"compute": 1.0, "host_copy": 0.05, "serialization": 0.05}})
    _write_json(native_roundtrip_report, native_roundtrip_payload)
    _write_json(exact_roundtrip_closure_report, exact_roundtrip_closure_payload)

    monkeypatch.setattr(module, "_validate_contract_artifacts", lambda paths: (True, []))
    monkeypatch.setattr(module, "_validate_priority3", lambda path: (True, None, None))
    monkeypatch.setattr(module, "_validate_extended_contracts", lambda *args: tuple([True] * 21))
    monkeypatch.setattr(module, "_load_json", _load_json)

    exit_code = module.main(
        [
            "--strict-probe",
            str(strict_path),
            "--rca",
            str(rca_path),
            "--out",
            str(out_path),
            "--manifest",
            str(manifest_path),
            "--required-contracts",
            "--midas-native-roundtrip-report",
            str(native_roundtrip_report),
            "--midas-exact-roundtrip-closure-report",
            str(exact_roundtrip_closure_report),
        ]
    )

    report = json.loads(out_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert report["reason_code"] == "PASS"
    assert report["midas_native_roundtrip_pass"] is True
    assert report["midas_native_roundtrip_summary_line"] == native_roundtrip_summary_line
    assert report["committee_summary_snapshot"]["midas_native_roundtrip_summary_line"] == native_roundtrip_summary_line
    assert report["midas_exact_roundtrip_closure_pass"] is False
    assert report["midas_exact_roundtrip_closure_summary_line"] == exact_roundtrip_closure_summary_line
    assert report["midas_exact_roundtrip_closure_scope_available"] is False
    assert report["midas_exact_roundtrip_closure_scope_summary"] == {}
    assert (
        report["committee_summary_snapshot"]["midas_exact_roundtrip_closure_summary_line"]
        == exact_roundtrip_closure_summary_line
    )
    assert report["committee_summary_snapshot"]["midas_exact_roundtrip_closure_scope_available"] is False
    assert report["committee_summary_snapshot"]["midas_exact_roundtrip_closure_scope_summary"] == {}
    assert report["reports"]["midas_native_roundtrip"].endswith("midas_native_roundtrip_gate_report.json")
    assert report["reports"]["midas_exact_roundtrip_closure"].endswith(
        "midas_exact_roundtrip_closure_gate_report.json"
    )
    assert str(native_roundtrip_report) in manifest["artifacts"]
    assert str(exact_roundtrip_closure_report) in manifest["artifacts"]


def test_phase1_ci_gate_surfaces_midas_exact_roundtrip_closure_scope_details(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_module()
    strict_path = tmp_path / "strict.json"
    rca_path = tmp_path / "rca.json"
    out_path = tmp_path / "ci_gate_report.json"
    manifest_path = tmp_path / "ci_artifact_manifest.json"
    exact_roundtrip_closure_report = tmp_path / "midas_exact_roundtrip_closure_gate_report.json"
    passing_payload = _passing_gate_payload(tmp_path)
    exact_roundtrip_closure_payload = {
        "schema_version": "1.0",
        "generated_at": "2026-04-11T00:00:00+00:00",
        "contract_pass": False,
        "reason_code": "ERR_EXACT_CLOSURE_PENDING",
        "reason": "exact roundtrip closure still pending",
        "summary_line": "MIDAS exact roundtrip closure: CHECK | exact=4/6 | canonical=0 | lossy=0 | unsupported=0 | manual=0 | pending_review=0 | exact_queue=0/0 | limits=none",
        "summary": {
            "ready_case_count": 6,
            "exact_case_count": 4,
            "eligible_exact_candidate_count": 4,
            "eligible_exact_case_count": 4,
            "eligible_exact_exclusion_case_count": 2,
            "eligible_exact_exclusion_labels": [
                "intentional_optimized_writeback",
                "parser_drop_fixture",
            ],
            "eligible_exact_exclusion_label_counts": {
                "intentional_optimized_writeback": 1,
                "parser_drop_fixture": 1,
            },
        },
        "checks": {
            "native_roundtrip_gate_pass": True,
            "interoperability_gate_pass": True,
        },
    }

    def _load_json(path: str) -> dict:
        payload = dict(passing_payload)
        payload["checks"] = dict(passing_payload["checks"])
        if str(path).endswith("midas_exact_roundtrip_closure_gate_report.json"):
            return dict(exact_roundtrip_closure_payload)
        return payload

    _write_json(strict_path, {"strict_rust_hip_pass": True})
    _write_json(rca_path, {"timing_breakdown_seconds": {"compute": 1.0, "host_copy": 0.05, "serialization": 0.05}})
    _write_json(exact_roundtrip_closure_report, exact_roundtrip_closure_payload)

    monkeypatch.setattr(module, "_validate_contract_artifacts", lambda paths: (True, []))
    monkeypatch.setattr(module, "_validate_priority3", lambda path: (True, None, None))
    monkeypatch.setattr(module, "_validate_extended_contracts", lambda *args: tuple([True] * 21))
    monkeypatch.setattr(module, "_load_json", _load_json)

    exit_code = module.main(
        [
            "--strict-probe",
            str(strict_path),
            "--rca",
            str(rca_path),
            "--out",
            str(out_path),
            "--manifest",
            str(manifest_path),
            "--required-contracts",
            "--midas-exact-roundtrip-closure-report",
            str(exact_roundtrip_closure_report),
        ]
    )

    report = json.loads(out_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert report["midas_exact_roundtrip_closure_summary_line"] == exact_roundtrip_closure_payload["summary_line"]
    assert report["midas_exact_roundtrip_closure_scope_available"] is True
    assert report["midas_exact_roundtrip_closure_scope_summary"] == {
        "eligible_exact_candidate_count": 4,
        "eligible_exact_case_count": 4,
        "eligible_exact_exclusion_case_count": 2,
        "eligible_exact_exclusion_labels": [
            "intentional_optimized_writeback",
            "parser_drop_fixture",
        ],
        "eligible_exact_exclusion_label_counts": {
            "intentional_optimized_writeback": 1,
            "parser_drop_fixture": 1,
        },
    }
    assert report["committee_summary_snapshot"]["midas_exact_roundtrip_closure_scope_available"] is True
    assert (
        report["committee_summary_snapshot"]["midas_exact_roundtrip_closure_scope_summary"]
        == report["midas_exact_roundtrip_closure_scope_summary"]
    )


def test_phase1_ci_gate_surfaces_load_combination_engine_gate_when_absent(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_module()
    strict_path = tmp_path / "strict.json"
    rca_path = tmp_path / "rca.json"
    out_path = tmp_path / "ci_gate_report.json"
    manifest_path = tmp_path / "ci_artifact_manifest.json"
    load_combination_engine_gate_report = tmp_path / "load_combination_engine_gate_report.json"
    passing_payload = _passing_gate_payload(tmp_path)

    _write_json(strict_path, {"strict_rust_hip_pass": True})
    _write_json(
        rca_path,
        {"timing_breakdown_seconds": {"compute": 1.0, "host_copy": 0.05, "serialization": 0.05}},
    )

    monkeypatch.setattr(module, "_validate_contract_artifacts", lambda paths: (True, []))
    monkeypatch.setattr(module, "_validate_priority3", lambda path: (True, None, None))
    monkeypatch.setattr(module, "_validate_extended_contracts", lambda *args: tuple([True] * 21))
    monkeypatch.setattr(module, "_load_json", lambda path: dict(passing_payload))

    exit_code = module.main(
        [
            "--strict-probe",
            str(strict_path),
            "--rca",
            str(rca_path),
            "--out",
            str(out_path),
            "--manifest",
            str(manifest_path),
            "--required-contracts",
            "--load-combination-engine-gate-report",
            str(load_combination_engine_gate_report),
        ]
    )

    report = json.loads(out_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert report["load_combination_engine_gate_available"] is False
    assert report["load_combination_engine_gate_pass"] is False
    assert report["load_combination_engine_gate_summary"] == {}
    assert report["load_combination_engine_gate_report"] == {}
    assert report["load_combination_engine_gate_summary_line"] == "Load combination engine gate: unavailable"
    assert report["committee_summary_snapshot"]["load_combination_engine_gate_available"] is False
    assert (
        report["committee_summary_snapshot"]["load_combination_engine_gate_summary_line"]
        == "Load combination engine gate: unavailable"
    )
    assert report["committee_summary_snapshot"]["load_combination_engine_gate_summary"] == {}
    assert report["reports"]["load_combination_engine_gate"] == str(load_combination_engine_gate_report)
    assert str(load_combination_engine_gate_report) in manifest["artifacts"]


def test_phase1_ci_gate_surfaces_load_combination_engine_gate_summary_when_present(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_module()
    strict_path = tmp_path / "strict.json"
    rca_path = tmp_path / "rca.json"
    out_path = tmp_path / "ci_gate_report.json"
    manifest_path = tmp_path / "ci_artifact_manifest.json"
    load_combination_engine_gate_report = tmp_path / "load_combination_engine_gate_report.json"
    passing_payload = _passing_gate_payload(tmp_path)
    load_combination_engine_gate_payload = {
        "schema_version": "1.0",
        "generated_at": "2026-04-11T00:00:00+00:00",
        "contract_pass": False,
        "reason_code": "ERR_RAW_RECOVERY_PENDING",
        "summary": {
            "combination_count": 8,
            "case_count": 5,
            "exact_combination_count": 7,
            "pending_case_count": 1,
            "remaining_limits": [
                "raw_recovery_pending",
                "normalized_factor_maps_pending",
            ],
        },
    }

    _write_json(strict_path, {"strict_rust_hip_pass": True})
    _write_json(
        rca_path,
        {"timing_breakdown_seconds": {"compute": 1.0, "host_copy": 0.05, "serialization": 0.05}},
    )
    _write_json(load_combination_engine_gate_report, load_combination_engine_gate_payload)

    monkeypatch.setattr(module, "_validate_contract_artifacts", lambda paths: (True, []))
    monkeypatch.setattr(module, "_validate_priority3", lambda path: (True, None, None))
    monkeypatch.setattr(module, "_validate_extended_contracts", lambda *args: tuple([True] * 21))
    monkeypatch.setattr(module, "_load_json", lambda path: dict(passing_payload))

    exit_code = module.main(
        [
            "--strict-probe",
            str(strict_path),
            "--rca",
            str(rca_path),
            "--out",
            str(out_path),
            "--manifest",
            str(manifest_path),
            "--required-contracts",
            "--load-combination-engine-gate-report",
            str(load_combination_engine_gate_report),
        ]
    )

    report = json.loads(out_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert report["load_combination_engine_gate_available"] is True
    assert report["load_combination_engine_gate_pass"] is False
    assert report["load_combination_engine_gate_summary"] == {
        "contract_pass": False,
        "reason_code": "ERR_RAW_RECOVERY_PENDING",
        "combination_count": 8,
        "case_count": 5,
        "exact_combination_count": 7,
        "pending_case_count": 1,
        "remaining_limits": [
            "raw_recovery_pending",
            "normalized_factor_maps_pending",
        ],
    }
    assert report["load_combination_engine_gate_summary_line"] == (
        "Load combination engine gate: CHECK | combos=8 | cases=5 | exact=7/8 | "
        "pending=1 | limits=raw_recovery_pending,normalized_factor_maps_pending | "
        "reason=ERR_RAW_RECOVERY_PENDING"
    )
    assert report["committee_summary_snapshot"]["load_combination_engine_gate_available"] is True
    assert (
        report["committee_summary_snapshot"]["load_combination_engine_gate_summary_line"]
        == report["load_combination_engine_gate_summary_line"]
    )
    assert (
        report["committee_summary_snapshot"]["load_combination_engine_gate_summary"]
        == report["load_combination_engine_gate_summary"]
    )
    assert report["reports"]["load_combination_engine_gate"] == str(load_combination_engine_gate_report)


def test_phase1_ci_gate_surfaces_panel_zone_clash_status_when_present(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_module()
    strict_path = tmp_path / "strict.json"
    rca_path = tmp_path / "rca.json"
    out_path = tmp_path / "ci_gate_report.json"
    manifest_path = tmp_path / "ci_artifact_manifest.json"
    panel_zone_clash_report = tmp_path / "panel_zone_clash_report.json"
    passing_payload = _passing_gate_payload(tmp_path)
    panel_zone_payload = {
        "schema_version": "1.0",
        "generated_at": "2026-04-11T00:00:00+00:00",
        "contract_pass": True,
        "reason_code": "PASS",
        "reason": "Panel-zone 3D clash artifact is attached.",
        "summary": {
            "constructability_mode": "internal_engine_panel_zone_3d_clash_and_anchorage_complete",
            "panel_zone_proxy_candidate_count": 45,
            "panel_zone_source_artifact_kind": "design_optimization_dataset_npz",
            "panel_zone_source_artifact_path": "implementation/phase1/release/design_optimization/design_optimization_dataset.npz",
            "panel_zone_source_contract_mode": "topology_projected_3d_clash_and_anchorage_bridge",
            "panel_zone_internal_engine_complete": True,
            "panel_zone_external_validation_pending": True,
            "panel_zone_validation_boundary": "external_validation_only",
            "panel_zone_missing_required_sources": [],
            "panel_zone_external_validation_status_label": "advisory_only",
            "panel_zone_external_validation_advisory_only": True,
            "panel_zone_external_validation_release_blocking": False,
        },
    }

    _write_json(strict_path, {"strict_rust_hip_pass": True})
    _write_json(
        rca_path,
        {"timing_breakdown_seconds": {"compute": 1.0, "host_copy": 0.05, "serialization": 0.05}},
    )
    _write_json(panel_zone_clash_report, panel_zone_payload)

    monkeypatch.setattr(module, "_validate_contract_artifacts", lambda paths: (True, []))
    monkeypatch.setattr(module, "_validate_priority3", lambda path: (True, None, None))
    monkeypatch.setattr(module, "_validate_extended_contracts", lambda *args: tuple([True] * 21))
    monkeypatch.setattr(module, "_load_json", lambda path: dict(passing_payload))

    exit_code = module.main(
        [
            "--strict-probe",
            str(strict_path),
            "--rca",
            str(rca_path),
            "--out",
            str(out_path),
            "--manifest",
            str(manifest_path),
            "--required-contracts",
            "--panel-zone-clash-report",
            str(panel_zone_clash_report),
        ]
    )

    report = json.loads(out_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert report["panel_zone_clash_report_available"] is True
    assert report["panel_zone_3d_clash_ready"] is True
    assert report["panel_zone_constructability_mode"] == "internal_engine_panel_zone_3d_clash_and_anchorage_complete"
    assert report["panel_zone_external_validation_pending"] is True
    assert report["panel_zone_validation_boundary"] == "external_validation_only"
    assert report["panel_zone_external_validation_status_label"] == "advisory_only"
    assert report["panel_zone_external_validation_advisory_only"] is True
    assert report["panel_zone_external_validation_release_blocking"] is False
    assert report["panel_zone_status_label"] == "advisory_external_validation_only_boundary"
    assert report["panel_zone_advisory_only"] is True
    assert report["panel_zone_release_blocking"] is False
    assert report["committee_summary_snapshot"]["panel_zone_status_label"] == "advisory_external_validation_only_boundary"
    assert report["committee_summary_snapshot"]["panel_zone_external_validation_status_label"] == "advisory_only"
    assert report["reports"]["panel_zone_clash_report"] == str(panel_zone_clash_report)
    assert str(panel_zone_clash_report) in manifest["artifacts"]


def test_phase1_ci_gate_surfaces_measured_benchmark_breadth_summary(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_module()
    strict_path = tmp_path / "strict.json"
    rca_path = tmp_path / "rca.json"
    out_path = tmp_path / "ci_gate_report.json"
    manifest_path = tmp_path / "ci_artifact_manifest.json"
    measured_report = (
        tmp_path
        / "implementation"
        / "phase1"
        / "release"
        / "benchmark_expansion"
        / "measured_benchmark_breadth_report.json"
    )
    passing_payload = _passing_gate_payload(tmp_path)
    measured_payload = {
        "schema_version": "1.0",
        "generated_at": "2026-04-11T00:00:00+00:00",
        "contract_pass": True,
        "reason_code": "PASS",
        "summary_line": (
            "Measured benchmark breadth: PASS | baseline=2/51 | opensees_delta=6/7 | "
            "authority_delta=2/6 | external_delta=10/10 | measured_families=20 | "
            "measured_cases=74 | parser_ready=3"
        ),
        "summary": {
            "baseline_measured_family_count": 2,
            "baseline_measured_case_count": 51,
            "opensees_incremental_family_count": 6,
            "opensees_incremental_case_count": 7,
            "authority_incremental_family_count": 2,
            "authority_incremental_case_count": 6,
            "external_incremental_family_count": 10,
            "external_incremental_case_count": 10,
            "measured_family_count": 20,
            "measured_case_count": 74,
            "opensees_parser_ready_case_count": 3,
        },
    }

    def _load_json(path: str) -> dict:
        if str(path).endswith("measured_benchmark_breadth_report.json"):
            return json.loads(measured_report.read_text(encoding="utf-8"))
        payload = dict(passing_payload)
        payload["checks"] = dict(passing_payload["checks"])
        return payload

    _write_json(strict_path, {"strict_rust_hip_pass": True})
    _write_json(
        rca_path,
        {"timing_breakdown_seconds": {"compute": 1.0, "host_copy": 0.05, "serialization": 0.05}},
    )
    _write_json(measured_report, measured_payload)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module, "_validate_contract_artifacts", lambda paths: (True, []))
    monkeypatch.setattr(module, "_validate_priority3", lambda path: (True, None, None))
    monkeypatch.setattr(module, "_validate_extended_contracts", lambda *args: tuple([True] * 21))
    monkeypatch.setattr(module, "_load_json", _load_json)

    exit_code = module.main(
        [
            "--strict-probe",
            str(strict_path),
            "--rca",
            str(rca_path),
            "--out",
            str(out_path),
            "--manifest",
            str(manifest_path),
            "--required-contracts",
        ]
    )

    report = json.loads(out_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert exit_code == 1
    assert report["measured_benchmark_breadth_summary_line"] == measured_payload["summary_line"]
    assert report["measured_benchmark_breadth_report"] == measured_payload
    assert (
        report["committee_summary_snapshot"]["measured_benchmark_breadth_summary_line"]
        == measured_payload["summary_line"]
    )
    assert report["reason_code"] == "ERR_MIDAS_SECTION_LIBRARY_ARTIFACT_FAIL"
    assert report["reports"]["measured_benchmark_breadth"].endswith(
        "implementation/phase1/release/benchmark_expansion/measured_benchmark_breadth_report.json"
    )
    assert report["measured_benchmark_breadth_report"]["summary"]["measured_case_count"] == 74
    assert "implementation/phase1/release/benchmark_expansion/measured_benchmark_breadth_report.json" in manifest["artifacts"]


def test_phase1_ci_gate_surfaces_korean_source_ingest_summary(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    strict_path = tmp_path / "strict.json"
    rca_path = tmp_path / "rca.json"
    out_path = tmp_path / "ci_gate_report.json"
    manifest_path = tmp_path / "ci_artifact_manifest.json"
    korean_ingest_gate_report = tmp_path / "korean_source_ingest_gate_report.json"
    passing_payload = _passing_gate_payload(tmp_path)
    korean_summary_line = (
        "Korean source ingest gate: PASS | sources=4 | classes=4 | "
        "collected=0 | fingerprinted=0 | metadata_only=4 | rejected=0 | duplicate_sha_groups=0 | "
        "seed_complete=4 | exact_topology=1 | native_writeback=1 | p0_focus=3"
    )
    korean_payload = {
        "schema_version": "1.0",
        "generated_at": "2026-04-07T00:00:00+00:00",
        "contract_pass": True,
        "reason_code": "PASS",
        "reason": "korean source ingest gate passed",
        "summary_line": korean_summary_line,
        "summary": {
            "source_count": 4,
            "source_class_count": 4,
            "collected_count": 0,
            "metadata_only_remote_candidate_count": 4,
            "rejected_count": 0,
            "fingerprinted_count": 0,
            "duplicate_sha_group_count": 0,
        },
        "checks": {
            "catalog_present_pass": True,
            "source_class_coverage_pass": True,
            "collection_report_present_pass": True,
            "collection_count_match_pass": True,
            "collection_accounting_pass": True,
            "ingest_report_present_pass": True,
            "ingest_count_match_pass": True,
            "ingest_accounting_pass": True,
            "duplicate_sha_group_consistency_pass": True,
        },
    }

    def _load_json(path: str) -> dict:
        payload = dict(passing_payload)
        payload["checks"] = dict(passing_payload["checks"])
        if str(path).endswith("korean_source_ingest_gate_report.json"):
            return dict(korean_payload)
        return payload

    _write_json(strict_path, {"strict_rust_hip_pass": True})
    _write_json(rca_path, {"timing_breakdown_seconds": {"compute": 1.0, "host_copy": 0.05, "serialization": 0.05}})
    _write_json(korean_ingest_gate_report, korean_payload)

    monkeypatch.setattr(module, "_validate_contract_artifacts", lambda paths: (True, []))
    monkeypatch.setattr(module, "_validate_priority3", lambda path: (True, None, None))
    monkeypatch.setattr(module, "_validate_extended_contracts", lambda *args: tuple([True] * 21))
    monkeypatch.setattr(module, "_load_json", _load_json)

    exit_code = module.main(
        [
            "--strict-probe",
            str(strict_path),
            "--rca",
            str(rca_path),
            "--out",
            str(out_path),
            "--manifest",
            str(manifest_path),
            "--required-contracts",
            "--korean-source-ingest-gate-report",
            str(korean_ingest_gate_report),
        ]
    )

    report = json.loads(out_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert report["all_pass"] is True
    assert report["reason_code"] == "PASS"
    assert report["korean_source_ingest_gate_pass"] is True
    assert report["korean_source_ingest_gate_summary_line"] == korean_summary_line
    assert report["committee_summary_snapshot"]["korean_source_ingest_gate_summary_line"] == korean_summary_line
    assert report["reports"]["korean_source_ingest_gate"].endswith("korean_source_ingest_gate_report.json")
    assert str(korean_ingest_gate_report) in manifest["artifacts"]


def test_phase1_ci_gate_surfaces_irregular_collection_summary(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    strict_path = tmp_path / "strict.json"
    rca_path = tmp_path / "rca.json"
    out_path = tmp_path / "ci_gate_report.json"
    manifest_path = tmp_path / "ci_artifact_manifest.json"
    native_roundtrip_report = tmp_path / "midas_native_roundtrip_gate_report.json"
    irregular_gate_report = tmp_path / "irregular_structure_collection_gate_report.json"
    irregular_top5_manifest = tmp_path / "irregular_top5_execution_manifest.json"
    passing_payload = _passing_gate_payload(tmp_path)
    native_roundtrip_summary_line = (
        "MIDAS native roundtrip: PASS | corpus=6 | native_text=1 | archives=4 | "
        "ready=1 | receipts=1/1 | topology=1/1 | load=1/1 | loadcomb=1/1 exact | pending_review=2"
    )
    irregular_gate_summary_line = (
        "Irregular structure collection gate: PASS | families=20 | sources=22 | "
        "local_ready=7 | remote_candidates=15 | collected=7 | top5=5"
    )
    irregular_top5_summary_line = (
        "Irregular top5 execution manifest: PASS | top5=5 | native_roundtrip_candidates=14 | "
        "solver_benchmark_candidates=11 | ai_learning_candidates=22"
    )
    native_roundtrip_payload = {
        "schema_version": "1.0",
        "generated_at": "2026-03-31T00:00:00+00:00",
        "contract_pass": True,
        "reason_code": "PASS",
        "reason": "native roundtrip ready",
        "summary_line": native_roundtrip_summary_line,
        "summary": {
            "corpus_case_count": 6,
            "native_text_case_count": 1,
            "archive_case_count": 4,
            "native_writeback_ready_count": 1,
            "receipt_count": 1,
            "pending_review_total": 2,
        },
        "checks": {
            "corpus_manifest_present_pass": True,
            "native_text_case_present_pass": True,
            "native_writeback_ready_pass": True,
            "diff_receipt_coverage_pass": True,
            "per_case_writeback_pass": True,
            "topology_stability_pass": True,
            "load_contract_stability_pass": True,
            "loadcomb_exact_roundtrip_pass": True,
            "unknown_rows_zero_pass": True,
        },
    }
    irregular_gate_payload = {
        "schema_version": "1.0",
        "generated_at": "2026-04-02T00:00:00+00:00",
        "contract_pass": True,
        "reason_code": "PASS",
        "reason": "irregular structure source catalog processed",
        "summary_line": irregular_gate_summary_line,
        "summary": {
            "family_count": 20,
            "source_record_count": 22,
            "local_ready_count": 7,
            "remote_candidate_count": 15,
            "collected_count": 7,
            "collection_source_count": 22,
            "top5_family_count": 5,
            "top5_priority_ids": [
                "transfer_podium_tower",
                "soft_story_podium_tower",
                "torsionally_eccentric_core_tower",
                "setback_tower",
                "reentrant_corner_tower",
            ],
        },
        "checks": {
            "catalog_present_pass": True,
            "collection_report_present_pass": True,
            "top5_manifest_present_pass": True,
        },
    }
    irregular_top5_payload = {
        "schema_version": "1.0",
        "manifest_version": "0.1.0",
        "generated_at": "2026-04-02T00:00:00+00:00",
        "contract_pass": True,
        "reason_code": "PASS",
        "reason": "top5 irregular structure execution manifest prepared",
        "summary_line": irregular_top5_summary_line,
        "summary": {
            "catalog_family_count": 20,
            "catalog_source_record_count": 22,
            "collection_source_count": 22,
            "collection_collected_count": 7,
            "quick_start_local_source_count": 7,
            "native_roundtrip_candidate_count": 14,
            "solver_benchmark_candidate_count": 11,
            "ai_learning_candidate_count": 22,
            "top5_family_count": 5,
            "top5_priority_ids": [
                "transfer_podium_tower",
                "soft_story_podium_tower",
                "torsionally_eccentric_core_tower",
                "setback_tower",
                "reentrant_corner_tower",
            ],
        },
        "top5_cases": [
            {"family_id": "transfer_podium_tower"},
            {"family_id": "soft_story_podium_tower"},
            {"family_id": "torsionally_eccentric_core_tower"},
            {"family_id": "setback_tower"},
            {"family_id": "reentrant_corner_tower"},
        ],
    }

    def _load_json(path: str) -> dict:
        payload = dict(passing_payload)
        payload["checks"] = dict(passing_payload["checks"])
        if str(path).endswith("midas_native_roundtrip_gate_report.json"):
            return dict(native_roundtrip_payload)
        if str(path).endswith("irregular_structure_collection_gate_report.json"):
            return dict(irregular_gate_payload)
        if str(path).endswith("irregular_top5_execution_manifest.json"):
            return dict(irregular_top5_payload)
        return payload

    _write_json(strict_path, {"strict_rust_hip_pass": True})
    _write_json(rca_path, {"timing_breakdown_seconds": {"compute": 1.0, "host_copy": 0.05, "serialization": 0.05}})
    _write_json(native_roundtrip_report, native_roundtrip_payload)
    _write_json(irregular_gate_report, irregular_gate_payload)
    _write_json(irregular_top5_manifest, irregular_top5_payload)

    monkeypatch.setattr(module, "_validate_contract_artifacts", lambda paths: (True, []))
    monkeypatch.setattr(module, "_validate_priority3", lambda path: (True, None, None))
    monkeypatch.setattr(module, "_validate_extended_contracts", lambda *args: tuple([True] * 21))
    monkeypatch.setattr(module, "_load_json", _load_json)

    exit_code = module.main(
        [
            "--strict-probe",
            str(strict_path),
            "--rca",
            str(rca_path),
            "--out",
            str(out_path),
            "--manifest",
            str(manifest_path),
            "--required-contracts",
            "--midas-native-roundtrip-report",
            str(native_roundtrip_report),
            "--irregular-structure-collection-gate-report",
            str(irregular_gate_report),
            "--irregular-top5-execution-manifest",
            str(irregular_top5_manifest),
        ]
    )

    report = json.loads(out_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert report["all_pass"] is True
    assert report["reason_code"] == "PASS"
    assert report["irregular_structure_collection_gate_pass"] is True
    assert report["irregular_structure_collection_gate_summary_line"] == irregular_gate_summary_line
    assert report["irregular_top5_execution_manifest_summary_line"] == irregular_top5_summary_line
    assert report["committee_summary_snapshot"]["irregular_structure_collection_gate_summary_line"] == irregular_gate_summary_line
    assert report["committee_summary_snapshot"]["irregular_top5_execution_manifest_summary_line"] == irregular_top5_summary_line
    assert report["reports"]["irregular_structure_collection_gate"].endswith("irregular_structure_collection_gate_report.json")
    assert report["reports"]["irregular_top5_execution_manifest"].endswith("irregular_top5_execution_manifest.json")
    assert str(irregular_gate_report) in manifest["artifacts"]
    assert str(irregular_top5_manifest) in manifest["artifacts"]
