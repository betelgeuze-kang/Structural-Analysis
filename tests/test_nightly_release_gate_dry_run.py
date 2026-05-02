from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "panel_zone_3d"


def test_nightly_release_gate_dry_run_includes_global_authority(tmp_path: Path) -> None:
    out = tmp_path / "nightly_release_gate_report.json"
    ci_report = tmp_path / "ci_gate_report.json"
    ci_report.write_text(
        json.dumps(
            {
                "midas_section_library_summary_line": "MIDAS section-library: ok | artifacts=3 | embedded=3 | representative_links=3",
                "midas_kds_geometry_bridge_summary_line": "MIDAS kds-geometry-bridge: ok | mapped_review_ids=0/12 | rows=1056 | strategies=unmapped:12 | source=kds_codecheck_bridge_metadata | registry=none 0/0",
                "midas_loadcomb_roundtrip_summary_line": "MIDAS loadcomb-roundtrip: ok | entry_row_coverage=midas_generator_33.json=1.00 | artifacts=3",
                "solver_breadth_summary_line": "Solver breadth: PASS | shell=yes(elems=5,cases=31) | wall=yes(rows=1,cases=14,material=rc_composite) | interface=yes(ssi_nonlinear_boundary) | contact=interface_compression_surrogate",
                "material_constitutive_summary_line": "Material constitutive gate: PASS | concrete_damage=yes(matrix=10/10,max=1.000) | cyclic_degradation=yes(matrix=8/8,residual_max=1.914%) | bond_interface=yes(matrix=11/11,bond_max=0.980) | matrix=29/29",
                "midas_kds_row_provenance_export_summary_line": "MIDAS KDS row provenance export: PASS | combos=6 | rows=144 | members=12 | clauses=6 | exact_rows=144",
                "contact_readiness_summary_line": "Contact readiness: PASS | scope=wheel_rail_hertzian_contact_only | schema=yes | solver=yes(ratio=0.994,max_force=6.52235N) | whitebox=yes(err=0.0048) | structural_contact=interface_compression_surrogate",
                "surface_interaction_benchmark_summary_line": "Surface interaction benchmark: PASS | ready=7/7 | family_matrix=35/35 | source_families=3/3 | shell_surface=yes | interface_transfer=yes | interface_gap=yes | foundation=yes | ssi=yes | soil_tunnel=yes | direct_contact=6/6 | groups=shell-shell=4,shell-wall=4,footing-soil=4",
                "midas_interoperability_summary_line": "MIDAS interoperability/export readiness: PASS | seeds=3/3 | patterns=3/3 | preview=3/3 | roundtrip=3/3 exact_entry_row_min=1.00 | bounded_subset=editor_seed+raw_recovery+preview_roundtrip | limits=solver_ready_reconstruction_pending, normalized_factor_maps_pending, summary_grade_preview_only, primitive_load_cards_pending",
                "korean_source_ingest_gate_summary_line": (
                    "Korean source ingest gate: PASS | sources=4 | classes=4 | "
                    "collected=0 | fingerprinted=0 | metadata_only=4 | rejected=0 | duplicate_sha_groups=0 | "
                    "seed_complete=4 | exact_topology=1 | native_writeback=1 | p0_focus=3"
                ),
                "midas_native_roundtrip_summary_line": "MIDAS native roundtrip: PASS | corpus=6 | native_text=1 | archives=4 | ready=1 | receipts=1/1 | topology=1/1 | load=1/1 | loadcomb=1/1 exact | pending_review=2",
                "performance_profiling_summary_line": "Performance profiling: PASS | ndtha=103.19s(cov=0.003,vram=0.0MB) | ssi_contact=160steps/1.64iters/newton=1052 | moving_load=euler=1.304s,timo=0.001s,warmup=1809.3x | gpu_host_ops=2 unavoidable/0 optimizable | sprint=3(ndtha_partitioned_runtime,ssi_contact_convergence_path,moving_load_kernel_warmup_observability)",
                "irregular_structure_collection_gate_summary_line": "Irregular structure collection gate: PASS | families=20 | sources=22 | local_ready=7 | remote_candidates=15 | collected=7 | top5=5",
                "irregular_top5_execution_manifest_summary_line": "Irregular top5 execution manifest: PASS | top5=5 | native_roundtrip_candidates=14 | solver_benchmark_candidates=11 | ai_learning_candidates=22",
                "solver_truthfulness_summary_line": "Solver truthfulness: PASS | reports=4/4 | explicit=4/4 | surrogate_free=4/4 | cpu_fallback=0/4",
                "hardest_external_10case_kickoff_summary_line": "Hardest external 10-case kickoff: PASS | ready=10/10 | start_now=yes | mode=start_now_limited_external_benchmark | full_submission=no | review_pending=2 | measured_families=8 | measured_cases=120",
                "commercial_readiness_summary_line": "Commercial readiness: PASS | grade=Commercial | strict_measured=True | families=3 | measured_families=2 | measured_cases=51 | shell_beam_mix=31",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    cmd = [
        sys.executable,
        "implementation/phase1/run_nightly_release_gate.py",
        "--dry-run",
        "--skip-promotion",
        "--allow-cpu-required",
        "--ci-report",
        str(ci_report),
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["reason_code"] == "PASS"
    assert report["contract_pass"] is True
    commercial_readiness_summary_line = str(
        report["committee_summary_snapshot"].get("commercial_readiness_summary_line", "")
    )
    assert commercial_readiness_summary_line.startswith(
        "Commercial readiness: PASS | grade=Commercial | strict_measured=True"
    )
    assert "measured_families=" in commercial_readiness_summary_line
    assert "measured_cases=" in commercial_readiness_summary_line
    assert "shell_beam_mix=31" in commercial_readiness_summary_line
    assert "Solver breadth: PASS" in str(report["committee_summary_snapshot"].get("solver_breadth_summary_line", ""))
    assert "Material constitutive gate: PASS" in str(report["committee_summary_snapshot"].get("material_constitutive_summary_line", ""))
    assert "MIDAS KDS row provenance export: PASS" in str(
        report["committee_summary_snapshot"].get("midas_kds_row_provenance_export_summary_line", "")
    )
    assert "Contact readiness: PASS" in str(report["committee_summary_snapshot"].get("contact_readiness_summary_line", ""))
    assert "MIDAS interoperability/export readiness: PASS" in str(
        report["committee_summary_snapshot"].get("midas_interoperability_summary_line", "")
    )
    assert "Korean source ingest gate: PASS" in str(
        report["committee_summary_snapshot"].get("korean_source_ingest_gate_summary_line", "")
    )
    assert "MIDAS native roundtrip: PASS" in str(
        report["committee_summary_snapshot"].get("midas_native_roundtrip_summary_line", "")
    )
    assert "Performance profiling: PASS" in str(
        report["committee_summary_snapshot"].get("performance_profiling_summary_line", "")
    )
    assert "Irregular structure collection gate: PASS" in str(
        report["committee_summary_snapshot"].get("irregular_structure_collection_gate_summary_line", "")
    )
    assert "Irregular top5 execution manifest: PASS" in str(
        report["committee_summary_snapshot"].get("irregular_top5_execution_manifest_summary_line", "")
    )
    solver_truthfulness_summary_line = str(report["committee_summary_snapshot"]["solver_truthfulness_summary_line"])
    assert solver_truthfulness_summary_line.startswith("Solver truthfulness: PASS | reports=4/4 | explicit=4/4")
    assert "surrogate_free=4/4" in solver_truthfulness_summary_line
    assert "cpu_fallback=0/4" in solver_truthfulness_summary_line
    assert "Hardest external 10-case kickoff: PASS" in str(
        report["committee_summary_snapshot"].get("hardest_external_10case_kickoff_summary_line", "")
    )
    steps = report.get("steps", [])
    step_names = [str(s.get("step")) for s in steps]
    assert "global_authority_gate" in step_names
    assert "hardest_external_10case_kickoff_gate" in step_names
    assert "midas_kds_geometry_bridge_backfill" in step_names
    assert "midas_kds_geometry_bridge_backfill_after_phase3_pipeline" in step_names
    backfill_step = next(step for step in steps if step.get("step") == "midas_kds_geometry_bridge_backfill")
    assert "--report implementation/phase1/release/kds_compliance/code_check_report.json" in str(
        backfill_step.get("command", "")
    )
    kds_step = next(step for step in steps if step.get("step") == "kds_compliance_gate")
    assert "--code-check-report implementation/phase1/release/kds_compliance/code_check_report.json" in str(
        kds_step.get("command", "")
    )
    pbd_step = next(step for step in steps if step.get("step") == "pbd_review_package")
    assert "--no-run-ndtha" in str(pbd_step.get("command", ""))
    assert "--ndtha-report implementation/phase1/nonlinear_ndtha_stress_report.pbd7.json" in str(
        pbd_step.get("command", "")
    )
    pbd_slice_step = next(step for step in steps if step.get("step") == "pbd_compliance_slice")
    assert "implementation/phase1/release_evidence/kds/design_optimization_solver_loop_long_report.json" in str(
        pbd_slice_step.get("command", "")
    )
    wind_step = next(step for step in steps if step.get("step") == "wind_benchmark_gate")
    assert "--allow-cpu-required" in str(wind_step.get("command", ""))
    ssi_step = next(step for step in steps if step.get("step") == "ssi_boundary_gate")
    assert "--allow-cpu-required" in str(ssi_step.get("command", ""))
    solver_hip_step = next(step for step in steps if step.get("step") == "solver_hip_e2e_contract")
    assert "materialize-evidence" in str(solver_hip_step.get("command", ""))
    assert "implementation/phase1/release_evidence/gpu/solver_hip_e2e_contract_report.json" in str(
        solver_hip_step.get("command", "")
    )
    scaleout_step = next(step for step in steps if step.get("step") == "scaleout_io_profile")
    assert "--allow-cpu-required" in str(scaleout_step.get("command", ""))
    assert "--gpu-strict" not in str(scaleout_step.get("command", ""))
    assert "surface_interaction_benchmark_gate" in step_names
    assert "solver_breadth_gate" in step_names
    assert "contact_readiness_gate" in step_names
    assert "midas_interoperability_gate" in step_names
    assert "korean_source_catalog" in step_names
    assert "korean_public_structure_collection" in step_names
    assert "korean_source_ingest_report" in step_names
    assert "korean_source_ingest_gate" in step_names
    assert "korean_solver_ready_reconstruction" in step_names
    assert "public_native_corpus" in step_names
    assert "midas_native_corpus_manifest" in step_names
    assert "midas_native_writeback_diff_receipts" in step_names
    assert "midas_native_roundtrip_gate" in step_names
    assert "performance_profiling_gate" in step_names
    assert "irregular_top5_execution_manifest" in step_names
    assert "irregular_structure_collection_gate" in step_names
    assert "phase1_ci_gate_nightly" in step_names
    assert "design_optimization_cost_reduction_smoke" in step_names
    assert "design_optimization_dataset_refresh" in step_names
    assert "design_optimization_rebar_payload_projection" in step_names
    assert "design_optimization_connection_detailing_payload_projection" in step_names
    assert "design_optimization_detailing_payload_projection" in step_names
    assert "mgt_export_direct_patch" in step_names
    assert "pbd_hinge_refresh_source" in step_names
    assert "pbd_hinge_refresh_artifact" in step_names
    assert "panel_zone_solver_export_bundle" in step_names
    assert "panel_zone_joint_geometry_source" in step_names
    assert "panel_zone_rebar_anchorage_source" in step_names
    assert "panel_zone_clash_verification_source" in step_names
    assert "panel_zone_joint_geometry_contract" in step_names
    assert "panel_zone_rebar_anchorage_contract" in step_names
    assert "panel_zone_clash_verification_contract" in step_names
    assert "panel_zone_clash_artifact" in step_names
    assert "panel_zone_solver_verified_inbox_status" in step_names
    assert "foundation_optimization_artifact" in step_names
    assert "wind_raw_mapping_artifact" in step_names
    assert "pbd_hinge_refresh_report" in step_names
    assert "panel_zone_clash_report" in step_names
    assert "foundation_optimization_report" in step_names
    assert "wind_tunnel_raw_mapping_report" in step_names
    assert "tpu_hffb_benchmark_gate" in step_names
    assert "pbd_hinge_benchmark_asset_registry" in step_names
    assert "peer_spd_hinge_benchmark_gate" in step_names
    assert "peer_spd_hinge_fixture_regression" in step_names
    assert "peer_spd_hinge_alignment" in step_names
    assert "release_gap_report" in step_names
    assert "external_benchmark_submission_readiness" in step_names
    assert "external_benchmark_kickoff_package" in step_names
    assert "external_benchmark_execution_manifest" in step_names
    assert "external_benchmark_execution_status_manifest" in step_names
    assert "audit_review_decision_batch_template" in step_names
    assert "audit_review_decision_batch_examples" in step_names
    assert "audit_review_decision_batch_previews" in step_names
    assert "structural_optimization_viewer" in step_names
    assert "optimized_drawing_review" in step_names
    assert "release_registry_gate" in step_names
    assert step_names.index("pbd_review_package") < step_names.index("pbd_compliance_slice")
    assert step_names.index("pbd_compliance_slice") < step_names.index("kds_compliance_gate")
    assert step_names.index("global_authority_gate") < step_names.index("phase1_ci_gate_nightly")
    assert step_names.index("hardest_external_10case_kickoff_gate") < step_names.index("phase1_ci_gate_nightly")
    assert step_names.index("midas_mgt_conversion_gate") < step_names.index("midas_kds_geometry_bridge_backfill")
    assert step_names.index("midas_kds_geometry_bridge_backfill") < step_names.index("phase1_ci_gate_nightly")
    assert step_names.index("phase3_pipeline_nightly") < step_names.index(
        "midas_kds_geometry_bridge_backfill_after_phase3_pipeline"
    )
    assert step_names.index("midas_kds_geometry_bridge_backfill_after_phase3_pipeline") < step_names.index(
        "phase1_ci_gate_nightly"
    )
    assert step_names.index("solver_breadth_gate") < step_names.index("phase1_ci_gate_nightly")
    assert step_names.index("contact_readiness_gate") < step_names.index("phase1_ci_gate_nightly")
    assert step_names.index("midas_interoperability_gate") < step_names.index("phase1_ci_gate_nightly")
    assert step_names.index("midas_interoperability_gate") < step_names.index("public_native_corpus")
    assert step_names.index("midas_interoperability_gate") < step_names.index("korean_source_catalog")
    assert step_names.index("korean_source_catalog") < step_names.index("korean_public_structure_collection")
    assert step_names.index("korean_public_structure_collection") < step_names.index("korean_source_ingest_report")
    assert step_names.index("korean_source_ingest_report") < step_names.index("korean_source_ingest_gate")
    assert step_names.index("korean_source_ingest_gate") < step_names.index("korean_solver_ready_reconstruction")
    assert step_names.index("korean_solver_ready_reconstruction") < step_names.index("midas_native_corpus_manifest")
    assert step_names.index("public_native_corpus") < step_names.index("midas_native_corpus_manifest")
    assert step_names.index("midas_native_corpus_manifest") < step_names.index("midas_native_writeback_diff_receipts")
    assert step_names.index("midas_native_writeback_diff_receipts") < step_names.index("midas_native_roundtrip_gate")
    assert step_names.index("solver_truthfulness_gate") < step_names.index("performance_profiling_gate")
    assert step_names.index("performance_profiling_gate") < step_names.index("phase1_ci_gate_nightly")
    assert step_names.index("irregular_top5_execution_manifest") < step_names.index("irregular_structure_collection_gate")
    assert step_names.index("irregular_structure_collection_gate") < step_names.index("phase1_ci_gate_nightly")
    assert step_names.index("midas_native_roundtrip_gate") < step_names.index("phase1_ci_gate_nightly")
    assert step_names.index("surface_interaction_benchmark_gate") < step_names.index("solver_breadth_gate")
    assert step_names.index("phase1_ci_gate_nightly") < step_names.index("design_optimization_cost_reduction_smoke")
    assert step_names.index("design_optimization_dataset_refresh") < step_names.index("pbd_hinge_refresh_source")
    assert step_names.index("design_optimization_dataset_refresh") < step_names.index("design_optimization_rebar_payload_projection")
    assert step_names.index("design_optimization_rebar_payload_projection") < step_names.index("design_optimization_connection_detailing_payload_projection")
    assert step_names.index("design_optimization_connection_detailing_payload_projection") < step_names.index("design_optimization_detailing_payload_projection")
    assert step_names.index("design_optimization_detailing_payload_projection") < step_names.index("mgt_export_direct_patch")
    assert step_names.index("design_optimization_rebar_payload_projection") < step_names.index("mgt_export_direct_patch")
    assert step_names.index("mgt_export_direct_patch") < step_names.index("pbd_hinge_refresh_source")
    assert step_names.index("pbd_hinge_refresh_source") < step_names.index("pbd_hinge_refresh_artifact")
    assert step_names.index("design_optimization_dataset_refresh") < step_names.index("pbd_hinge_refresh_report")
    assert step_names.index("design_optimization_dataset_refresh") < step_names.index("pbd_hinge_refresh_artifact")
    assert step_names.index("pbd_hinge_refresh_artifact") < step_names.index("pbd_hinge_refresh_report")
    assert step_names.index("design_optimization_dataset_refresh") < step_names.index("panel_zone_solver_export_bundle")
    assert step_names.index("panel_zone_solver_export_bundle") < step_names.index("panel_zone_joint_geometry_source")
    assert step_names.index("pbd_hinge_refresh_report") < step_names.index("panel_zone_joint_geometry_contract")
    assert step_names.index("pbd_hinge_refresh_report") < step_names.index("panel_zone_joint_geometry_source")
    assert step_names.index("panel_zone_joint_geometry_source") < step_names.index("panel_zone_rebar_anchorage_source")
    assert step_names.index("panel_zone_rebar_anchorage_source") < step_names.index("panel_zone_clash_verification_source")
    assert step_names.index("panel_zone_clash_verification_source") < step_names.index("panel_zone_joint_geometry_contract")
    assert step_names.index("panel_zone_joint_geometry_contract") < step_names.index("panel_zone_rebar_anchorage_contract")
    assert step_names.index("panel_zone_rebar_anchorage_contract") < step_names.index("panel_zone_clash_verification_contract")
    assert step_names.index("design_optimization_dataset_refresh") < step_names.index("panel_zone_clash_artifact")
    assert step_names.index("panel_zone_clash_artifact") < step_names.index("panel_zone_solver_verified_inbox_status")
    assert step_names.index("panel_zone_solver_verified_inbox_status") < step_names.index("foundation_optimization_artifact")
    assert step_names.index("design_optimization_dataset_refresh") < step_names.index("foundation_optimization_artifact")
    assert step_names.index("panel_zone_clash_artifact") < step_names.index("panel_zone_clash_report")
    assert step_names.index("foundation_optimization_artifact") < step_names.index("foundation_optimization_report")
    assert step_names.index("wind_raw_mapping_artifact") < step_names.index("wind_tunnel_raw_mapping_report")
    assert step_names.index("wind_tunnel_raw_mapping_report") < step_names.index("tpu_hffb_benchmark_gate")
    assert step_names.index("tpu_hffb_benchmark_gate") < step_names.index("pbd_hinge_benchmark_asset_registry")
    assert step_names.index("pbd_hinge_benchmark_asset_registry") < step_names.index("peer_spd_hinge_benchmark_gate")
    assert step_names.index("peer_spd_hinge_benchmark_gate") < step_names.index("peer_spd_hinge_fixture_regression")
    assert step_names.index("peer_spd_hinge_fixture_regression") < step_names.index("peer_spd_hinge_alignment")
    assert step_names.index("peer_spd_hinge_alignment") < step_names.index("release_gap_report")
    assert step_names.index("release_gap_report") < step_names.index("external_benchmark_submission_readiness")
    assert step_names.index("external_benchmark_submission_readiness") < step_names.index("external_benchmark_kickoff_package")
    assert step_names.index("external_benchmark_kickoff_package") < step_names.index("external_benchmark_execution_manifest")
    assert step_names.index("external_benchmark_execution_manifest") < step_names.index("external_benchmark_execution_status_manifest")
    assert step_names.index("external_benchmark_execution_status_manifest") < step_names.index("audit_review_decision_batch_template")
    assert step_names.index("audit_review_decision_batch_template") < step_names.index("audit_review_decision_batch_examples")
    assert step_names.index("audit_review_decision_batch_examples") < step_names.index("audit_review_decision_batch_previews")
    assert step_names.index("audit_review_decision_batch_previews") < step_names.index("structural_optimization_viewer")
    assert step_names.index("structural_optimization_viewer") < step_names.index("optimized_drawing_review")
    assert step_names.index("optimized_drawing_review") < step_names.index("release_registry_gate")
    assert step_names.index("external_benchmark_execution_status_manifest") < step_names.index("release_registry_gate")
    ci_step = next(step for step in steps if str(step.get("step")) == "phase1_ci_gate_nightly")
    ci_command = str(ci_step.get("command", ""))
    midas_manifest_step = next(step for step in steps if str(step.get("step")) == "midas_native_corpus_manifest")
    midas_manifest_command = str(midas_manifest_step.get("command", ""))
    assert "--midas-section-library-artifact implementation/phase1/open_data/midas/midas_generator_33.json" in ci_command
    assert "--midas-section-library-artifact implementation/phase1/open_data/midas/midas_generator_33.pr_recheck.json" in ci_command
    assert "--midas-section-library-artifact implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json" in ci_command
    assert "--midas-kds-geometry-bridge-artifact implementation/phase1/open_data/midas/midas_generator_33.json" in ci_command
    assert "--midas-kds-geometry-bridge-artifact implementation/phase1/open_data/midas/midas_generator_33.pr_recheck.json" in ci_command
    assert "--midas-kds-geometry-bridge-artifact implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json" in ci_command
    assert "--midas-loadcomb-roundtrip-artifact implementation/phase1/open_data/midas/midas_generator_33.json" in ci_command
    assert "--midas-loadcomb-roundtrip-artifact implementation/phase1/open_data/midas/midas_generator_33.pr_recheck.json" in ci_command
    assert "--midas-loadcomb-roundtrip-artifact implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json" in ci_command
    assert "--general-fe-contact-benchmark-report implementation/phase1/general_fe_contact_benchmark_gate_report.json" in ci_command
    assert "--surface-interaction-benchmark-report implementation/phase1/surface_interaction_benchmark_gate_report.json" in ci_command
    assert "--korean-source-ingest-gate-report implementation/phase1/korean_source_ingest_gate_report.json" in ci_command
    assert "--hardest-external-10case-kickoff-report implementation/phase1/hardest_external_10case_kickoff_gate_report.json" in ci_command
    assert "--midas-native-roundtrip-report implementation/phase1/midas_native_roundtrip_gate_report.json" in ci_command
    assert "--performance-profiling-report implementation/phase1/performance_profiling_gate_report.json" in ci_command
    assert "--irregular-structure-collection-gate-report implementation/phase1/irregular_structure_collection_gate_report.json" in ci_command
    assert "--irregular-top5-execution-manifest implementation/phase1/open_data/irregular/irregular_top5_execution_manifest.json" in ci_command
    assert "--korean-source-catalog implementation/phase1/open_data/korea/korean_source_catalog.json" in midas_manifest_command
    assert "--korean-solver-ready-reconstruction-report implementation/phase1/release/midas_native_roundtrip/korean_solver_ready_reconstruction_report.json" in midas_manifest_command
    irregular_manifest_step = next(step for step in steps if str(step.get("step")) == "irregular_top5_execution_manifest")
    irregular_manifest_command = str(irregular_manifest_step.get("command", ""))
    assert "generate_irregular_top5_execution_manifest.py" in irregular_manifest_command
    assert "--priority-families implementation/phase1/open_data/irregular/priority_irregular_structure_families.json" in irregular_manifest_command
    irregular_collection_step = next(step for step in steps if str(step.get("step")) == "irregular_structure_collection_gate")
    irregular_collection_command = str(irregular_collection_step.get("command", ""))
    assert "run_irregular_structure_collection_gate.py" in irregular_collection_command
    assert "surface_interaction_benchmark_summary_line" in report["committee_summary_snapshot"]
    assert "midas_kds_row_provenance_export_summary_line" in report["committee_summary_snapshot"]
    assert "hardest_external_10case_kickoff_summary_line" in report["committee_summary_snapshot"]
    assert "midas_native_roundtrip_summary_line" in report["committee_summary_snapshot"]
    assert "performance_profiling_summary_line" in report["committee_summary_snapshot"]
    assert "irregular_structure_collection_gate_summary_line" in report["committee_summary_snapshot"]
    assert "irregular_top5_execution_manifest_summary_line" in report["committee_summary_snapshot"]
    assert report["inputs"]["enable_design_opt_cost_smoke"] is True
    assert report["inputs"]["strict_design_opt_cost_smoke"] is True
    assert report["inputs"]["design_opt_cost_smoke_history_limit"] == 10
    assert report["reports"]["design_opt_cost_reduction_smoke"].endswith("design_optimization_cost_reduction_smoke_report.json")
    assert report["reports"]["design_opt_cost_reduction_smoke_history"].endswith("design_optimization_cost_reduction_smoke_history.json")
    assert report["reports"]["design_opt_dataset"].endswith("design_optimization_dataset_report.json")
    assert report["reports"]["design_opt_rebar_payload_projection"].endswith("midas_generator_33.rebar_payload_projection.json")
    assert report["reports"]["design_opt_connection_detailing_payload_projection"].endswith(
        "midas_generator_33.connection_detailing_payload_projection.json"
    )
    assert report["reports"]["design_opt_detailing_payload_projection"].endswith(
        "midas_generator_33.detailing_payload_projection.json"
    )
    assert report["reports"]["mgt_export_output_mgt"].endswith("midas_generator_33.optimized.mgt")
    assert report["reports"]["mgt_export"].endswith("midas_generator_33.optimized.export_report.json")
    assert report["reports"]["mgt_export_patch_manifest"].endswith("midas_generator_33.optimized.patch_manifest.json")
    assert report["reports"]["mgt_export_instruction_sidecar"].endswith("midas_generator_33.optimized.instruction_sidecar.json")
    assert report["reports"]["mgt_export_audit_review_manifest"].endswith("midas_generator_33.optimized.audit_review_manifest.json")
    assert report["reports"]["mgt_export_audit_review_packet_manifest"].endswith("midas_generator_33.optimized.audit_review_packets.json")
    assert report["reports"]["mgt_export_audit_review_packet_directory"].endswith("midas_generator_33.optimized.audit_review_packet_files")
    assert report["reports"]["mgt_export_audit_review_queue_manifest"].endswith("midas_generator_33.optimized.audit_review_queue.json")
    assert report["reports"]["mgt_export_audit_review_queue_status_directory"].endswith("midas_generator_33.optimized.audit_review_queue_status_files")
    assert report["reports"]["pbd_hinge_refresh_source"].endswith("pbd_hinge_refresh_source.json")
    assert report["reports"]["pbd_hinge_refresh_artifact"].endswith("pbd_hinge_refresh_artifact.json")
    assert report["reports"]["pbd_hinge_refresh"].endswith("pbd_hinge_refresh_report.json")
    assert report["reports"]["panel_zone_solver_export_bundle"].endswith("panel_zone_solver_export_bundle.json")
    assert report["reports"]["panel_zone_joint_geometry_source"].endswith("panel_zone_joint_geometry_3d.json")
    assert report["reports"]["panel_zone_rebar_anchorage_source"].endswith("panel_zone_rebar_anchorage_3d.json")
    assert report["reports"]["panel_zone_clash_verification_source"].endswith("panel_zone_clash_verification_3d.json")
    assert report["reports"]["panel_zone_joint_geometry_contract"].endswith("panel_zone_joint_geometry_3d_contract.json")
    assert report["reports"]["panel_zone_rebar_anchorage_contract"].endswith("panel_zone_rebar_anchorage_3d_contract.json")
    assert report["reports"]["panel_zone_clash_verification_contract"].endswith("panel_zone_clash_verification_3d_contract.json")
    assert report["reports"]["panel_zone_clash"].endswith("panel_zone_clash_report.json")
    assert report["reports"]["panel_zone_solver_verified_inbox_status"].endswith(
        "panel_zone_solver_verified_inbox_status.json"
    )
    assert report["reports"]["foundation_optimization"].endswith("foundation_optimization_report.json")
    assert report["reports"]["wind_tunnel_raw_mapping"].endswith("wind_tunnel_raw_mapping_report.json")
    assert report["reports"]["tpu_hffb_benchmark"].endswith("tpu_hffb_benchmark_gate_report.json")
    assert report["reports"]["pbd_hinge_benchmark_asset_registry"].endswith("pbd_hinge_benchmark_asset_registry.json")
    assert report["reports"]["peer_spd_hinge_benchmark"].endswith("peer_spd_hinge_benchmark_gate_report.json")
    assert report["reports"]["peer_spd_hinge_fixture_regression"].endswith("peer_spd_hinge_fixture_regression_report.json")
    assert report["reports"]["peer_spd_hinge_alignment"].endswith("peer_spd_hinge_refresh_alignment_report.json")
    assert report["reports"]["release_gap_report"].endswith("release_gap_report.json")
    assert report["reports"]["external_benchmark_submission_readiness"].endswith(
        "external_benchmark_submission_readiness.json"
    )
    assert report["reports"]["external_benchmark_kickoff_package"].endswith(
        "external_benchmark_kickoff_package.json"
    )
    assert report["reports"]["external_benchmark_execution_manifest"].endswith(
        "external_benchmark_execution_manifest.json"
    )
    assert report["reports"]["external_benchmark_execution_status_manifest"].endswith(
        "external_benchmark_execution_status_manifest.json"
    )
    assert report["reports"]["hardest_external_10case_kickoff"].endswith(
        "hardest_external_10case_kickoff_gate_report.json"
    )
    assert report["reports"]["irregular_structure_collection_gate"].endswith(
        "irregular_structure_collection_gate_report.json"
    )
    assert report["reports"]["irregular_top5_execution_manifest"].endswith(
        "irregular_top5_execution_manifest.json"
    )
    assert report["reports"]["audit_review_decision_batch_template"].endswith(
        "audit_review_decision_batch_template.json"
    )
    assert report["reports"]["audit_review_decision_batch_approve_all_attested_example"].endswith(
        "audit_review_decision_batch_approve_all.attested_example.json"
    )
    assert report["reports"]["audit_review_decision_batch_mixed_attested_example"].endswith(
        "audit_review_decision_batch_mixed.attested_example.json"
    )
    assert report["reports"]["audit_review_decision_batch_approve_all_preview_input"].endswith(
        "audit_review_decision_batch_approve_all.preview.json"
    )
    assert report["reports"]["audit_review_decision_batch_reject_one_preview_input"].endswith(
        "audit_review_decision_batch_reject_one.preview.json"
    )
    assert report["reports"]["external_benchmark_submission_preview_approve_all"].endswith(
        "external_benchmark_submission_readiness_preview.approve_all.json"
    )
    assert report["reports"]["external_benchmark_submission_preview_reject_one"].endswith(
        "external_benchmark_submission_readiness_preview.reject_one.json"
    )
    assert report["reports"]["audit_review_decision_batch_live_preview"].endswith(
        "audit_review_decision_batch.live_preview.json"
    )
    assert report["reports"]["audit_review_decision_batch_run_report"].endswith(
        "audit_review_decision_batch_run_report.json"
    )
    assert report["reports"]["audit_review_decision_batch_preview_artifacts_report"].endswith(
        "audit_review_decision_batch_preview_artifacts_report.json"
    )
    assert report["reports"]["structural_optimization_viewer_json"].endswith(
        "structural_optimization_viewer.json"
    )
    assert report["reports"]["structural_optimization_viewer_html"].endswith(
        "structural_optimization_viewer.html"
    )
    assert report["reports"]["optimized_drawing_review_html"].endswith(
        "optimized_drawing_review.html"
    )
    assert report["reports"]["optimized_drawing_review_summary_json"].endswith(
        "optimized_drawing_review_summary.json"
    )
    assert report["inputs"]["panel_zone_solver_export_bundle"].endswith("panel_zone_solver_export_bundle.json")
    assert report["inputs"]["panel_zone_joint_geometry_artifact"].endswith("panel_zone_solver_export_bundle.json")
    assert report["inputs"]["panel_zone_rebar_anchorage_artifact"].endswith("panel_zone_solver_export_bundle.json")
    assert report["inputs"]["panel_zone_clash_verification_artifact"].endswith("panel_zone_solver_export_bundle.json")
    assert report["inputs"]["panel_zone_joint_geometry_source_output"].endswith("panel_zone_joint_geometry_3d.json")
    assert report["inputs"]["panel_zone_rebar_anchorage_source_output"].endswith("panel_zone_rebar_anchorage_3d.json")
    assert report["inputs"]["panel_zone_clash_verification_source_output"].endswith("panel_zone_clash_verification_3d.json")
    assert report["inputs"]["panel_zone_joint_geometry_contract"].endswith("panel_zone_joint_geometry_3d_contract.json")
    assert report["inputs"]["panel_zone_rebar_anchorage_contract"].endswith("panel_zone_rebar_anchorage_3d_contract.json")
    assert report["inputs"]["panel_zone_clash_verification_contract"].endswith("panel_zone_clash_verification_3d_contract.json")
    assert report["inputs"]["panel_zone_solver_verified_inbox_status_report"].endswith(
        "panel_zone_solver_verified_inbox_status.json"
    )
    assert report["inputs"]["pbd_hinge_refresh_source_input"].endswith("pbd_hinge_refresh_source.json")
    assert report["inputs"]["pbd_hinge_refresh_source_output"].endswith("pbd_hinge_refresh_source.json")
    assert report["inputs"]["pbd_hinge_refresh_artifact"].endswith("pbd_hinge_refresh_artifact.json")
    assert report["inputs"]["design_opt_cost_reduction_changes"].endswith("design_optimization_cost_reduction_changes.json")
    assert report["inputs"]["design_opt_rebar_payload_projection_json"].endswith("midas_generator_33.rebar_payload_projection.json")
    assert report["inputs"]["design_opt_connection_detailing_payload_projection_json"].endswith(
        "midas_generator_33.connection_detailing_payload_projection.json"
    )
    assert report["inputs"]["design_opt_detailing_payload_projection_json"].endswith(
        "midas_generator_33.detailing_payload_projection.json"
    )
    assert report["inputs"]["mgt_export_output_mgt"].endswith("midas_generator_33.optimized.mgt")
    assert report["inputs"]["mgt_export_report"].endswith("midas_generator_33.optimized.export_report.json")
    assert report["inputs"]["mgt_export_patch_manifest"].endswith("midas_generator_33.optimized.patch_manifest.json")
    assert report["inputs"]["mgt_export_instruction_sidecar"].endswith("midas_generator_33.optimized.instruction_sidecar.json")
    assert report["inputs"]["mgt_export_audit_review_manifest"].endswith("midas_generator_33.optimized.audit_review_manifest.json")
    assert report["inputs"]["panel_zone_solver_verified_drop_dir"].endswith("implementation/phase1/inbox/panel_zone_solver_verified")
    assert report["inputs"]["wind_benchmark_asset_registry"].endswith("wind_benchmark_asset_registry.json")
    assert report["inputs"]["tpu_hffb_benchmark_report"].endswith("tpu_hffb_benchmark_gate_report.json")
    assert report["inputs"]["peer_spd_column_seed_manifest"].endswith("peer_spd_column_seed_manifest.json")
    assert report["inputs"]["peer_spd_column_materialize_report"].endswith("peer_spd_column_materialize_report.json")
    assert report["inputs"]["pbd_hinge_benchmark_asset_registry"].endswith("pbd_hinge_benchmark_asset_registry.json")
    assert report["inputs"]["peer_spd_hinge_benchmark_report"].endswith("peer_spd_hinge_benchmark_gate_report.json")
    assert report["inputs"]["peer_spd_hinge_fixture_regression_report"].endswith("peer_spd_hinge_fixture_regression_report.json")
    assert report["inputs"]["peer_spd_hinge_alignment_report"].endswith("peer_spd_hinge_refresh_alignment_report.json")
    assert report["inputs"]["external_benchmark_kickoff_dir"].endswith(
        "implementation/phase1/release/external_benchmark_kickoff"
    )
    assert report["inputs"]["external_benchmark_kickoff_package_report"].endswith(
        "external_benchmark_kickoff_package.json"
    )
    assert report["inputs"]["external_benchmark_execution_manifest_report"].endswith(
        "external_benchmark_execution_manifest.json"
    )
    assert report["inputs"]["external_benchmark_execution_updates_json"].endswith(
        "external_benchmark_execution_updates.json"
    )
    assert report["inputs"]["external_benchmark_execution_status_manifest_report"].endswith(
        "external_benchmark_execution_status_manifest.json"
    )
    assert report["inputs"]["audit_review_decision_batch_template_json"].endswith(
        "audit_review_decision_batch_template.json"
    )
    assert report["inputs"]["audit_review_decision_batch_preview_artifacts_report"].endswith(
        "audit_review_decision_batch_preview_artifacts_report.json"
    )
    assert report["inputs"]["structural_optimization_viewer_dir"].endswith(
        "implementation/phase1/release/visualization"
    )
    smoke_payload = report.get("design_optimization_cost_reduction_smoke", {})
    assert "trial_solver" not in smoke_payload
    assert "design_optimization_cost_reduction_smoke_history" in report
    assert isinstance(report.get("summary_cards"), list)
    labels = [str(card.get("label")) for card in report["summary_cards"]]
    assert "Design Opt Smoke" in labels
    assert "MIDAS Section Library" in labels
    assert "MIDAS KDS Geometry Bridge" in labels
    assert "MIDAS LOADCOMB Roundtrip" in labels
    assert "Comparable Chain Reference" in labels
    assert "Authority Routing Diff" in labels
    midas_card = next(card for card in report["summary_cards"] if str(card.get("label")) == "MIDAS Section Library")
    assert midas_card.get("value") == "embedded ok"
    assert "MIDAS section-library: ok |" in str(midas_card.get("note", ""))
    bridge_card = next(card for card in report["summary_cards"] if str(card.get("label")) == "MIDAS KDS Geometry Bridge")
    assert bridge_card.get("value") == "tracked"
    assert "MIDAS kds-geometry-bridge: ok |" in str(bridge_card.get("note", ""))
    assert "exact=12 | heuristic=0" in str(bridge_card.get("note", ""))
    assert "registry=merged_registry 12/12" in str(bridge_card.get("note", ""))
    loadcomb_card = next(card for card in report["summary_cards"] if str(card.get("label")) == "MIDAS LOADCOMB Roundtrip")
    assert loadcomb_card.get("value") == "exact ok"
    assert "MIDAS loadcomb-roundtrip: ok |" in str(loadcomb_card.get("note", ""))
    committee_snapshot = report.get("committee_summary_snapshot", {})
    assert "MIDAS section-library: ok |" in str(committee_snapshot.get("midas_section_library_summary_line", ""))
    assert "MIDAS kds-geometry-bridge: ok |" in str(committee_snapshot.get("midas_kds_geometry_bridge_summary_line", ""))
    assert "exact=12 | heuristic=0" in str(committee_snapshot.get("midas_kds_geometry_bridge_summary_line", ""))
    assert "registry=merged_registry 12/12" in str(committee_snapshot.get("midas_kds_geometry_bridge_summary_line", ""))
    assert "MIDAS loadcomb-roundtrip: ok |" in str(committee_snapshot.get("midas_loadcomb_roundtrip_summary_line", ""))
    assert "Solver breadth: PASS" in str(committee_snapshot.get("solver_breadth_summary_line", ""))
    assert committee_snapshot.get("measured_chain_comparable_reference_deployment_model") == "engineer_in_the_loop_accelerated_coverage"
    assert committee_snapshot.get("measured_chain_comparable_reference_strict_design_opt_cost_smoke") is True
    assert isinstance(committee_snapshot.get("panel_zone_3d_clash_ready"), bool)
    assert "panel_zone_solver_verified_inbox_status_mode" in committee_snapshot
    assert committee_snapshot.get("panel_zone_constructability_mode") in {
        "",
        "topology_projected_midas_panel_bridge",
        "internal_engine_panel_zone_3d_clash_and_anchorage_complete",
        "scalar_proxy_hard_gate_only",
        "panel_zone_3d_clash_and_anchorage_verified",
    }
    assert committee_snapshot.get("panel_zone_source_contract_mode") in {
        "",
        "rows_head_proxy_scan",
        "topology_projected_3d_clash_and_anchorage_bridge",
        "true_3d_clash_and_anchorage_verified",
    }
    assert int(committee_snapshot.get("panel_zone_proxy_candidate_count", 0) or 0) >= 0
    assert isinstance(committee_snapshot.get("foundation_optimization_ready"), bool)
    assert committee_snapshot.get("foundation_scope_source") in {"", "artifact_empty_scan", "dataset_summary"}
    assert committee_snapshot.get("upstream_foundation_label_count") == 0
    steps_by_name = {str(step.get("step")): str(step.get("command", "")) for step in report.get("steps", [])}
    foundation_artifact_cmd = steps_by_name["foundation_optimization_artifact"]
    rebar_projection_cmd = steps_by_name["design_optimization_rebar_payload_projection"]
    connection_projection_cmd = steps_by_name["design_optimization_connection_detailing_payload_projection"]
    detailing_projection_cmd = steps_by_name["design_optimization_detailing_payload_projection"]
    assert "implementation/phase1/generate_group_local_rebar_payloads.py" in rebar_projection_cmd
    assert "--parsed-model-json" in rebar_projection_cmd
    assert report["inputs"]["mgt_json_out"] in rebar_projection_cmd
    assert "--dataset-npz" in rebar_projection_cmd
    assert report["inputs"]["design_opt_dataset_npz"] in rebar_projection_cmd
    assert "--changes-json" in rebar_projection_cmd
    assert report["inputs"]["design_opt_cost_reduction_changes"] in rebar_projection_cmd
    assert "--projection-json-out" in rebar_projection_cmd
    assert report["inputs"]["design_opt_rebar_payload_projection_json"] in rebar_projection_cmd
    assert "implementation/phase1/generate_group_local_connection_detailing_payloads.py" in connection_projection_cmd
    assert report["inputs"]["design_opt_connection_detailing_payload_projection_json"] in connection_projection_cmd
    assert "implementation/phase1/generate_group_local_detailing_payloads.py" in detailing_projection_cmd
    assert report["inputs"]["design_opt_detailing_payload_projection_json"] in detailing_projection_cmd
    mgt_export_cmd = steps_by_name["mgt_export_direct_patch"]
    structural_viewer_cmd = steps_by_name["structural_optimization_viewer"]
    optimized_drawing_review_cmd = steps_by_name["optimized_drawing_review"]
    assert "implementation/phase1/export_design_optimization_to_mgt.py" in mgt_export_cmd
    assert "--source-mgt" in mgt_export_cmd
    assert report["inputs"]["mgt_input"] in mgt_export_cmd
    assert "--parsed-model-json" in mgt_export_cmd
    assert report["inputs"]["mgt_json_out"] in mgt_export_cmd
    assert "--dataset-npz" in mgt_export_cmd
    assert report["inputs"]["design_opt_dataset_npz"] in mgt_export_cmd
    assert "--changes-json" in mgt_export_cmd
    assert report["inputs"]["design_opt_cost_reduction_changes"] in mgt_export_cmd
    assert "--rebar-payload-projection-json" in mgt_export_cmd
    assert "implementation/phase1/generate_optimized_drawing_review_ui.py" in optimized_drawing_review_cmd
    assert report["reports"]["structural_optimization_viewer_json"] in optimized_drawing_review_cmd
    assert report["reports"]["optimized_drawing_review_html"] in optimized_drawing_review_cmd
    assert report["inputs"]["design_opt_rebar_payload_projection_json"] in mgt_export_cmd
    assert "--connection-detailing-payload-projection-json" in mgt_export_cmd
    assert report["inputs"]["design_opt_connection_detailing_payload_projection_json"] in mgt_export_cmd
    assert "--detailing-payload-projection-json" in mgt_export_cmd
    assert report["inputs"]["design_opt_detailing_payload_projection_json"] in mgt_export_cmd
    assert "--output-mgt" in mgt_export_cmd
    assert report["inputs"]["mgt_export_output_mgt"] in mgt_export_cmd
    assert "--report-out" in mgt_export_cmd
    assert report["inputs"]["mgt_export_report"] in mgt_export_cmd
    assert "--patch-manifest-out" in mgt_export_cmd
    assert report["inputs"]["mgt_export_patch_manifest"] in mgt_export_cmd
    assert "--instruction-sidecar-out" in mgt_export_cmd
    assert report["inputs"]["mgt_export_instruction_sidecar"] in mgt_export_cmd
    assert "--audit-review-manifest-out" in mgt_export_cmd
    assert report["inputs"]["mgt_export_audit_review_manifest"] in mgt_export_cmd
    assert "--audit-review-packet-manifest-out" in mgt_export_cmd
    assert report["inputs"]["mgt_export_audit_review_packet_manifest"] in mgt_export_cmd
    assert "implementation/phase1/generate_structural_optimization_visualization_viewer.py" in structural_viewer_cmd
    assert "--design-optimization-npz" in structural_viewer_cmd
    assert report["inputs"]["design_opt_dataset_npz"] in structural_viewer_cmd
    assert "--model-json" in structural_viewer_cmd
    assert report["inputs"]["mgt_json_out"] in structural_viewer_cmd
    assert "--changes-report" in structural_viewer_cmd
    assert report["inputs"]["design_opt_cost_reduction_changes"] in structural_viewer_cmd
    assert "--design-optimization-npz" in foundation_artifact_cmd
    assert "implementation/phase1/release/design_optimization/design_optimization_dataset.npz" in foundation_artifact_cmd
    assert "--midas-model" in foundation_artifact_cmd
    assert report["inputs"]["mgt_json_out"] in foundation_artifact_cmd
    recommendation = report.get("design_optimization_cost_reduction_smoke_strict_recommendation", {})
    assert recommendation.get("recommendation") in {"collect_more_history", "keep_non_blocking", "candidate_for_strict_enable"}


def test_nightly_release_gate_dry_run_reuses_panel_fixture_sources_in_commands_and_wiring(tmp_path: Path) -> None:
    out = tmp_path / "nightly_release_gate_report.json"
    joint_contract = tmp_path / "joint_geometry_contract.json"
    anchorage_contract = tmp_path / "rebar_anchorage_contract.json"
    clash_contract = tmp_path / "clash_verification_contract.json"
    joint_source_output = tmp_path / "panel_zone_joint_geometry_3d.json"
    anchorage_source_output = tmp_path / "panel_zone_rebar_anchorage_3d.json"
    clash_source_output = tmp_path / "panel_zone_clash_verification_3d.json"
    cmd = [
        sys.executable,
        "implementation/phase1/run_nightly_release_gate.py",
        "--dry-run",
        "--skip-promotion",
        "--panel-zone-joint-geometry-artifact",
        str(FIXTURE_DIR / "joint_geometry_source.json"),
        "--panel-zone-rebar-anchorage-artifact",
        str(FIXTURE_DIR / "rebar_anchorage_source.json"),
        "--panel-zone-clash-verification-artifact",
        str(FIXTURE_DIR / "clash_verification_source.json"),
        "--panel-zone-joint-geometry-source-output",
        str(joint_source_output),
        "--panel-zone-rebar-anchorage-source-output",
        str(anchorage_source_output),
        "--panel-zone-clash-verification-source-output",
        str(clash_source_output),
        "--panel-zone-joint-geometry-contract",
        str(joint_contract),
        "--panel-zone-rebar-anchorage-contract",
        str(anchorage_contract),
        "--panel-zone-clash-verification-contract",
        str(clash_contract),
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    report = json.loads(out.read_text(encoding="utf-8"))
    steps = {str(step.get("step")): str(step.get("command", "")) for step in report.get("steps", [])}
    assert str(FIXTURE_DIR / "joint_geometry_source.json") in steps["panel_zone_joint_geometry_source"]
    assert str(FIXTURE_DIR / "rebar_anchorage_source.json") in steps["panel_zone_rebar_anchorage_source"]
    assert str(FIXTURE_DIR / "clash_verification_source.json") in steps["panel_zone_clash_verification_source"]
    assert str(joint_source_output) in steps["panel_zone_joint_geometry_contract"]
    assert str(anchorage_source_output) in steps["panel_zone_rebar_anchorage_contract"]
    assert str(clash_source_output) in steps["panel_zone_clash_verification_contract"]
    assert str(joint_contract) in steps["panel_zone_clash_artifact"]
    assert str(anchorage_contract) in steps["panel_zone_clash_artifact"]
    assert str(clash_contract) in steps["panel_zone_clash_artifact"]
    assert report["inputs"]["panel_zone_joint_geometry_artifact"].endswith("joint_geometry_source.json")
    assert report["inputs"]["panel_zone_rebar_anchorage_artifact"].endswith("rebar_anchorage_source.json")
    assert report["inputs"]["panel_zone_clash_verification_artifact"].endswith("clash_verification_source.json")
    assert report["inputs"]["panel_zone_joint_geometry_source_output"] == str(joint_source_output)
    assert report["inputs"]["panel_zone_rebar_anchorage_source_output"] == str(anchorage_source_output)
    assert report["inputs"]["panel_zone_clash_verification_source_output"] == str(clash_source_output)
    assert report["inputs"]["panel_zone_joint_geometry_contract"] == str(joint_contract)
    assert report["inputs"]["panel_zone_rebar_anchorage_contract"] == str(anchorage_contract)
    assert report["inputs"]["panel_zone_clash_verification_contract"] == str(clash_contract)
    assert report["reports"]["panel_zone_joint_geometry_source"].endswith("panel_zone_joint_geometry_3d.json")
    assert report["reports"]["panel_zone_rebar_anchorage_source"].endswith("panel_zone_rebar_anchorage_3d.json")
    assert report["reports"]["panel_zone_clash_verification_source"].endswith("panel_zone_clash_verification_3d.json")
    assert report["reports"]["panel_zone_joint_geometry_contract"].endswith("joint_geometry_contract.json")
    assert report["reports"]["panel_zone_rebar_anchorage_contract"].endswith("rebar_anchorage_contract.json")
    assert report["reports"]["panel_zone_clash_verification_contract"].endswith("clash_verification_contract.json")
    assert report["reports"]["panel_zone_clash"].endswith("panel_zone_clash_report.json")


def test_nightly_release_gate_dry_run_routes_panel_source_inputs_through_contract_steps(tmp_path: Path) -> None:
    out = tmp_path / "nightly_release_gate_report.json"
    joint_source = tmp_path / "joint_geometry_source.json"
    anchorage_source = tmp_path / "rebar_anchorage_source.json"
    clash_source = tmp_path / "clash_verification_source.json"
    joint_source_output = tmp_path / "panel_zone_joint_geometry_3d.json"
    anchorage_source_output = tmp_path / "panel_zone_rebar_anchorage_3d.json"
    clash_source_output = tmp_path / "panel_zone_clash_verification_3d.json"
    joint_contract = tmp_path / "joint_geometry_contract.json"
    anchorage_contract = tmp_path / "rebar_anchorage_contract.json"
    clash_contract = tmp_path / "clash_verification_contract.json"
    cmd = [
        sys.executable,
        "implementation/phase1/run_nightly_release_gate.py",
        "--dry-run",
        "--skip-promotion",
        "--panel-zone-joint-geometry-artifact",
        str(joint_source),
        "--panel-zone-rebar-anchorage-artifact",
        str(anchorage_source),
        "--panel-zone-clash-verification-artifact",
        str(clash_source),
        "--panel-zone-joint-geometry-source-output",
        str(joint_source_output),
        "--panel-zone-rebar-anchorage-source-output",
        str(anchorage_source_output),
        "--panel-zone-clash-verification-source-output",
        str(clash_source_output),
        "--panel-zone-joint-geometry-contract",
        str(joint_contract),
        "--panel-zone-rebar-anchorage-contract",
        str(anchorage_contract),
        "--panel-zone-clash-verification-contract",
        str(clash_contract),
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    report = json.loads(out.read_text(encoding="utf-8"))
    steps = {str(step.get("step")): str(step.get("command", "")) for step in report.get("steps", [])}
    assert str(joint_source) in steps["panel_zone_joint_geometry_source"]
    assert str(anchorage_source) in steps["panel_zone_rebar_anchorage_source"]
    assert str(clash_source) in steps["panel_zone_clash_verification_source"]
    assert str(joint_source_output) in steps["panel_zone_joint_geometry_source"]
    assert str(anchorage_source_output) in steps["panel_zone_rebar_anchorage_source"]
    assert str(clash_source_output) in steps["panel_zone_clash_verification_source"]
    assert str(joint_source_output) in steps["panel_zone_joint_geometry_contract"]
    assert str(anchorage_source_output) in steps["panel_zone_rebar_anchorage_contract"]
    assert str(clash_source_output) in steps["panel_zone_clash_verification_contract"]
    assert str(joint_contract) in steps["panel_zone_clash_artifact"]
    assert str(anchorage_contract) in steps["panel_zone_clash_artifact"]
    assert str(clash_contract) in steps["panel_zone_clash_artifact"]
    assert str(joint_source) not in steps["panel_zone_clash_artifact"]
    assert str(anchorage_source) not in steps["panel_zone_clash_artifact"]
    assert str(clash_source) not in steps["panel_zone_clash_artifact"]


def test_nightly_release_gate_dry_run_fans_out_panel_solver_export_bundle(tmp_path: Path) -> None:
    out = tmp_path / "nightly_release_gate_report.json"
    joint_source_output = tmp_path / "panel_zone_joint_geometry_3d.json"
    anchorage_source_output = tmp_path / "panel_zone_rebar_anchorage_3d.json"
    clash_source_output = tmp_path / "panel_zone_clash_verification_3d.json"
    joint_contract = tmp_path / "joint_geometry_contract.json"
    anchorage_contract = tmp_path / "rebar_anchorage_contract.json"
    clash_contract = tmp_path / "clash_verification_contract.json"
    bundle = FIXTURE_DIR / "panel_zone_solver_export_bundle.json"
    cmd = [
        sys.executable,
        "implementation/phase1/run_nightly_release_gate.py",
        "--dry-run",
        "--skip-promotion",
        "--panel-zone-solver-export-bundle",
        str(bundle),
        "--panel-zone-joint-geometry-source-output",
        str(joint_source_output),
        "--panel-zone-rebar-anchorage-source-output",
        str(anchorage_source_output),
        "--panel-zone-clash-verification-source-output",
        str(clash_source_output),
        "--panel-zone-joint-geometry-contract",
        str(joint_contract),
        "--panel-zone-rebar-anchorage-contract",
        str(anchorage_contract),
        "--panel-zone-clash-verification-contract",
        str(clash_contract),
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    report = json.loads(out.read_text(encoding="utf-8"))
    steps = {str(step.get("step")): str(step.get("command", "")) for step in report.get("steps", [])}
    assert str(bundle) in steps["panel_zone_joint_geometry_source"]
    assert str(bundle) in steps["panel_zone_rebar_anchorage_source"]
    assert str(bundle) in steps["panel_zone_clash_verification_source"]
    assert str(bundle) not in steps["panel_zone_clash_artifact"]
    assert report["inputs"]["panel_zone_solver_export_bundle"] == str(bundle)
    assert report["inputs"]["panel_zone_joint_geometry_artifact"] == str(bundle)
    assert report["inputs"]["panel_zone_rebar_anchorage_artifact"] == str(bundle)
    assert report["inputs"]["panel_zone_clash_verification_artifact"] == str(bundle)


def test_nightly_release_gate_dry_run_uses_explicit_solver_verified_panel_bundle_without_autogen(tmp_path: Path) -> None:
    out = tmp_path / "nightly_release_gate_report.json"
    joint_source_output = tmp_path / "panel_zone_joint_geometry_3d.json"
    anchorage_source_output = tmp_path / "panel_zone_rebar_anchorage_3d.json"
    clash_source_output = tmp_path / "panel_zone_clash_verification_3d.json"
    joint_contract = tmp_path / "joint_geometry_contract.json"
    anchorage_contract = tmp_path / "rebar_anchorage_contract.json"
    clash_contract = tmp_path / "clash_verification_contract.json"
    bundle = FIXTURE_DIR / "panel_zone_solver_verified_export_bundle.json"
    cmd = [
        sys.executable,
        "implementation/phase1/run_nightly_release_gate.py",
        "--dry-run",
        "--skip-promotion",
        "--panel-zone-solver-export-bundle",
        str(bundle),
        "--panel-zone-joint-geometry-source-output",
        str(joint_source_output),
        "--panel-zone-rebar-anchorage-source-output",
        str(anchorage_source_output),
        "--panel-zone-clash-verification-source-output",
        str(clash_source_output),
        "--panel-zone-joint-geometry-contract",
        str(joint_contract),
        "--panel-zone-rebar-anchorage-contract",
        str(anchorage_contract),
        "--panel-zone-clash-verification-contract",
        str(clash_contract),
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    report = json.loads(out.read_text(encoding="utf-8"))
    steps = {str(step.get("step")): str(step.get("command", "")) for step in report.get("steps", [])}
    step_names = [str(step.get("step")) for step in report.get("steps", [])]
    assert "panel_zone_solver_export_bundle" not in steps
    assert str(bundle) in steps["panel_zone_joint_geometry_source"]
    assert str(bundle) in steps["panel_zone_rebar_anchorage_source"]
    assert str(bundle) in steps["panel_zone_clash_verification_source"]
    assert step_names.index("panel_zone_joint_geometry_source") < step_names.index("panel_zone_joint_geometry_contract")
    assert step_names.index("panel_zone_rebar_anchorage_source") < step_names.index("panel_zone_rebar_anchorage_contract")
    assert step_names.index("panel_zone_clash_verification_source") < step_names.index("panel_zone_clash_verification_contract")
    assert step_names.index("panel_zone_joint_geometry_contract") < step_names.index("panel_zone_clash_artifact")
    assert step_names.index("panel_zone_rebar_anchorage_contract") < step_names.index("panel_zone_clash_artifact")
    assert step_names.index("panel_zone_clash_verification_contract") < step_names.index("panel_zone_clash_artifact")
    assert report["inputs"]["panel_zone_solver_export_bundle"] == str(bundle)
    assert report["inputs"]["panel_zone_joint_geometry_artifact"] == str(bundle)
    assert report["inputs"]["panel_zone_rebar_anchorage_artifact"] == str(bundle)
    assert report["inputs"]["panel_zone_clash_verification_artifact"] == str(bundle)


def test_nightly_release_gate_dry_run_accepts_preferred_verified_bundle_alias(tmp_path: Path) -> None:
    out = tmp_path / "nightly_release_gate_report.json"
    joint_source_output = tmp_path / "panel_zone_joint_geometry_3d.json"
    anchorage_source_output = tmp_path / "panel_zone_rebar_anchorage_3d.json"
    clash_source_output = tmp_path / "panel_zone_clash_verification_3d.json"
    joint_contract = tmp_path / "joint_geometry_contract.json"
    anchorage_contract = tmp_path / "rebar_anchorage_contract.json"
    clash_contract = tmp_path / "clash_verification_contract.json"
    bundle = FIXTURE_DIR / "panel_zone_solver_verified_export_bundle.json"
    cmd = [
        sys.executable,
        "implementation/phase1/run_nightly_release_gate.py",
        "--dry-run",
        "--skip-promotion",
        "--panel-zone-solver-verified-export-bundle",
        str(bundle),
        "--panel-zone-joint-geometry-source-output",
        str(joint_source_output),
        "--panel-zone-rebar-anchorage-source-output",
        str(anchorage_source_output),
        "--panel-zone-clash-verification-source-output",
        str(clash_source_output),
        "--panel-zone-joint-geometry-contract",
        str(joint_contract),
        "--panel-zone-rebar-anchorage-contract",
        str(anchorage_contract),
        "--panel-zone-clash-verification-contract",
        str(clash_contract),
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    report = json.loads(out.read_text(encoding="utf-8"))
    steps = {str(step.get("step")): str(step.get("command", "")) for step in report.get("steps", [])}
    assert str(bundle) in steps["panel_zone_joint_geometry_source"]
    assert str(bundle) in steps["panel_zone_rebar_anchorage_source"]
    assert str(bundle) in steps["panel_zone_clash_verification_source"]
    assert report["inputs"]["panel_zone_solver_export_bundle"] == str(bundle)


def test_nightly_release_gate_dry_run_autogenerates_solver_verified_panel_bundle_from_raw_sources(tmp_path: Path) -> None:
    out = tmp_path / "nightly_release_gate_report.json"
    joint_source_output = tmp_path / "panel_zone_joint_geometry_3d.json"
    anchorage_source_output = tmp_path / "panel_zone_rebar_anchorage_3d.json"
    clash_source_output = tmp_path / "panel_zone_clash_verification_3d.json"
    joint_contract = tmp_path / "joint_geometry_contract.json"
    anchorage_contract = tmp_path / "rebar_anchorage_contract.json"
    clash_contract = tmp_path / "clash_verification_contract.json"
    bundle_out = tmp_path / "panel_zone_solver_verified_export_bundle.json"
    cmd = [
        sys.executable,
        "implementation/phase1/run_nightly_release_gate.py",
        "--dry-run",
        "--skip-promotion",
        "--panel-zone-solver-export-bundle",
        str(bundle_out),
        "--panel-zone-solver-verified-joint-geometry-source",
        str(FIXTURE_DIR / "joint_geometry_source.json"),
        "--panel-zone-solver-verified-rebar-anchorage-source",
        str(FIXTURE_DIR / "rebar_anchorage_source.json"),
        "--panel-zone-solver-verified-clash-verification-source",
        str(FIXTURE_DIR / "clash_verification_source.json"),
        "--panel-zone-joint-geometry-source-output",
        str(joint_source_output),
        "--panel-zone-rebar-anchorage-source-output",
        str(anchorage_source_output),
        "--panel-zone-clash-verification-source-output",
        str(clash_source_output),
        "--panel-zone-joint-geometry-contract",
        str(joint_contract),
        "--panel-zone-rebar-anchorage-contract",
        str(anchorage_contract),
        "--panel-zone-clash-verification-contract",
        str(clash_contract),
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    report = json.loads(out.read_text(encoding="utf-8"))
    steps = {str(step.get("step")): str(step.get("command", "")) for step in report.get("steps", [])}
    step_names = [str(step.get("step")) for step in report.get("steps", [])]
    assert "panel_zone_solver_verified_export_bundle" in steps
    assert "implementation/phase1/generate_panel_zone_solver_verified_export_bundle.py" in steps[
        "panel_zone_solver_verified_export_bundle"
    ]
    assert str(FIXTURE_DIR / "joint_geometry_source.json") in steps["panel_zone_solver_verified_export_bundle"]
    assert str(FIXTURE_DIR / "rebar_anchorage_source.json") in steps["panel_zone_solver_verified_export_bundle"]
    assert str(FIXTURE_DIR / "clash_verification_source.json") in steps["panel_zone_solver_verified_export_bundle"]
    assert str(bundle_out) in steps["panel_zone_solver_verified_export_bundle"]
    assert str(bundle_out) in steps["panel_zone_joint_geometry_source"]
    assert str(bundle_out) in steps["panel_zone_rebar_anchorage_source"]
    assert str(bundle_out) in steps["panel_zone_clash_verification_source"]
    assert step_names.index("panel_zone_solver_verified_export_bundle") < step_names.index("panel_zone_joint_geometry_source")
    assert step_names.index("panel_zone_joint_geometry_source") < step_names.index("panel_zone_joint_geometry_contract")
    assert step_names.index("panel_zone_joint_geometry_contract") < step_names.index("panel_zone_clash_artifact")
    assert report["inputs"]["panel_zone_solver_export_bundle"] == str(bundle_out)
    assert report["inputs"]["panel_zone_solver_verified_joint_geometry_source"].endswith("joint_geometry_source.json")
    assert report["inputs"]["panel_zone_solver_verified_rebar_anchorage_source"].endswith("rebar_anchorage_source.json")
    assert report["inputs"]["panel_zone_solver_verified_clash_verification_source"].endswith(
        "clash_verification_source.json"
    )
    assert report["reports"]["panel_zone_solver_verified_export_bundle"] == str(bundle_out)


def test_nightly_release_gate_dry_run_discovers_solver_verified_panel_inputs_from_drop_dir(tmp_path: Path) -> None:
    out = tmp_path / "nightly_release_gate_report.json"
    joint_source_output = tmp_path / "panel_zone_joint_geometry_3d.json"
    anchorage_source_output = tmp_path / "panel_zone_rebar_anchorage_3d.json"
    clash_source_output = tmp_path / "panel_zone_clash_verification_3d.json"
    joint_contract = tmp_path / "joint_geometry_contract.json"
    anchorage_contract = tmp_path / "rebar_anchorage_contract.json"
    clash_contract = tmp_path / "clash_verification_contract.json"
    bundle_out = tmp_path / "panel_zone_solver_verified_export_bundle.json"
    drop_dir = FIXTURE_DIR / "drop_package"
    cmd = [
        sys.executable,
        "implementation/phase1/run_nightly_release_gate.py",
        "--dry-run",
        "--skip-promotion",
        "--panel-zone-solver-verified-drop-dir",
        str(drop_dir),
        "--panel-zone-solver-export-bundle",
        str(bundle_out),
        "--panel-zone-joint-geometry-source-output",
        str(joint_source_output),
        "--panel-zone-rebar-anchorage-source-output",
        str(anchorage_source_output),
        "--panel-zone-clash-verification-source-output",
        str(clash_source_output),
        "--panel-zone-joint-geometry-contract",
        str(joint_contract),
        "--panel-zone-rebar-anchorage-contract",
        str(anchorage_contract),
        "--panel-zone-clash-verification-contract",
        str(clash_contract),
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    report = json.loads(out.read_text(encoding="utf-8"))
    steps = {str(step.get("step")): str(step.get("command", "")) for step in report.get("steps", [])}
    step_names = [str(step.get("step")) for step in report.get("steps", [])]
    discovered_joint = str((FIXTURE_DIR / "joint_geometry_source.json").resolve())
    discovered_anchorage = str((FIXTURE_DIR / "rebar_anchorage_source.json").resolve())
    discovered_clash = str((FIXTURE_DIR / "clash_verification_source.json").resolve())
    assert "panel_zone_solver_verified_export_bundle" in steps
    assert discovered_joint in steps["panel_zone_solver_verified_export_bundle"]
    assert discovered_anchorage in steps["panel_zone_solver_verified_export_bundle"]
    assert discovered_clash in steps["panel_zone_solver_verified_export_bundle"]
    assert "--source-origin-class fixture_sample" in steps["panel_zone_solver_verified_export_bundle"]
    assert str(bundle_out) in steps["panel_zone_solver_verified_export_bundle"]
    assert step_names.index("panel_zone_solver_verified_export_bundle") < step_names.index("panel_zone_joint_geometry_source")
    assert report["inputs"]["panel_zone_solver_verified_drop_dir"] == str(drop_dir)
    assert report["inputs"]["panel_zone_solver_verified_drop_dir_discovered_joint_geometry_source"] == discovered_joint
    assert report["inputs"]["panel_zone_solver_verified_drop_dir_discovered_rebar_anchorage_source"] == discovered_anchorage
    assert report["inputs"]["panel_zone_solver_verified_drop_dir_discovered_clash_verification_source"] == discovered_clash
    assert report["inputs"]["panel_zone_solver_verified_source_origin_class"] == "fixture_sample"
    assert report["inputs"]["panel_zone_solver_verified_drop_dir_discovered_source_origin_class"] == "fixture_sample"
    assert report["inputs"]["panel_zone_solver_verified_joint_geometry_source"] == discovered_joint
    assert report["inputs"]["panel_zone_solver_verified_rebar_anchorage_source"] == discovered_anchorage
    assert report["inputs"]["panel_zone_solver_verified_clash_verification_source"] == discovered_clash


def test_nightly_release_gate_dry_run_uses_staged_default_inbox_when_explicit_drop_dir_is_omitted(tmp_path: Path) -> None:
    inbox = tmp_path / "panel_inbox"
    stage_proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/stage_panel_zone_solver_verified_drop.py",
            "--source-drop-dir",
            str(FIXTURE_DIR / "drop_package"),
            "--inbox-dir",
            str(inbox),
            "--clean",
            "--out",
            str(tmp_path / "stage_report.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert stage_proc.returncode == 0, stage_proc.stderr

    out = tmp_path / "nightly_release_gate_report.json"
    bundle_out = tmp_path / "panel_zone_solver_verified_export_bundle.json"
    cmd = [
        sys.executable,
        "implementation/phase1/run_nightly_release_gate.py",
        "--dry-run",
        "--skip-promotion",
        "--panel-zone-solver-verified-drop-dir",
        str(inbox),
        "--panel-zone-solver-export-bundle",
        str(bundle_out),
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    report = json.loads(out.read_text(encoding="utf-8"))
    steps = {str(step.get("step")): str(step.get("command", "")) for step in report.get("steps", [])}
    assert "panel_zone_solver_verified_export_bundle" in steps
    assert str((inbox / "joint_geometry.json").resolve()) in steps["panel_zone_solver_verified_export_bundle"]
    assert str((inbox / "rebar_anchorage.json").resolve()) in steps["panel_zone_solver_verified_export_bundle"]
    assert str((inbox / "clash_verification.json").resolve()) in steps["panel_zone_solver_verified_export_bundle"]


def test_nightly_release_gate_dry_run_reads_trusted_source_origin_from_drop_dir(tmp_path: Path) -> None:
    out = tmp_path / "nightly_release_gate_report.json"
    bundle_out = tmp_path / "panel_zone_solver_verified_export_bundle.json"
    cmd = [
        sys.executable,
        "implementation/phase1/run_nightly_release_gate.py",
        "--dry-run",
        "--skip-promotion",
        "--panel-zone-solver-verified-drop-dir",
        str(FIXTURE_DIR / "trusted_drop_package"),
        "--panel-zone-solver-export-bundle",
        str(bundle_out),
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    report = json.loads(out.read_text(encoding="utf-8"))
    steps = {str(step.get("step")): str(step.get("command", "")) for step in report.get("steps", [])}
    assert report["inputs"]["panel_zone_solver_verified_source_origin_class"] == "trusted_external_solver_source"
    assert report["inputs"]["panel_zone_solver_verified_drop_dir_discovered_source_origin_class"] == "trusted_external_solver_source"
    assert "--source-origin-class trusted_external_solver_source" in steps["panel_zone_solver_verified_export_bundle"]


def test_nightly_release_gate_dry_run_routes_hinge_source_through_artifact_step(tmp_path: Path) -> None:
    out = tmp_path / "nightly_release_gate_report.json"
    hinge_source = tmp_path / "hinge_refresh_source.json"
    hinge_artifact = tmp_path / "pbd_hinge_refresh_artifact.json"
    cmd = [
        sys.executable,
        "implementation/phase1/run_nightly_release_gate.py",
        "--dry-run",
        "--skip-promotion",
        "--pbd-hinge-refresh-source-input",
        str(hinge_source),
        "--pbd-hinge-refresh-artifact",
        str(hinge_artifact),
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    report = json.loads(out.read_text(encoding="utf-8"))
    steps = {str(step.get("step")): str(step.get("command", "")) for step in report.get("steps", [])}
    assert "pbd_hinge_refresh_source" not in steps
    assert str(hinge_source) in steps["pbd_hinge_refresh_artifact"]
    assert str(hinge_artifact) in steps["pbd_hinge_refresh_artifact"]
    assert "--design-optimization-npz" in steps["pbd_hinge_refresh_artifact"]
    assert "--cost-reduction-changes" in steps["pbd_hinge_refresh_artifact"]
    assert str(hinge_artifact) in steps["pbd_hinge_refresh_report"]
    assert str(hinge_source) not in steps["pbd_hinge_refresh_report"]
    assert report["inputs"]["pbd_hinge_refresh_source_input"] == str(hinge_source)
    assert report["inputs"]["pbd_hinge_refresh_artifact"] == str(hinge_artifact)
    assert report["reports"]["pbd_hinge_refresh_artifact"] == str(hinge_artifact)


def test_nightly_release_gate_dry_run_autogenerates_hinge_source_before_artifact(tmp_path: Path) -> None:
    out = tmp_path / "nightly_release_gate_report.json"
    hinge_source_output = tmp_path / "pbd_hinge_refresh_source.json"
    hinge_artifact = tmp_path / "pbd_hinge_refresh_artifact.json"
    cmd = [
        sys.executable,
        "implementation/phase1/run_nightly_release_gate.py",
        "--dry-run",
        "--skip-promotion",
        "--pbd-hinge-refresh-source-output",
        str(hinge_source_output),
        "--pbd-hinge-refresh-artifact",
        str(hinge_artifact),
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    report = json.loads(out.read_text(encoding="utf-8"))
    steps = {str(step.get("step")): str(step.get("command", "")) for step in report.get("steps", [])}
    assert str(hinge_source_output) in steps["pbd_hinge_refresh_source"]
    assert str(hinge_source_output) in steps["pbd_hinge_refresh_artifact"]
    assert "--design-optimization-npz" in steps["pbd_hinge_refresh_source"]
    assert "--cost-reduction-changes" in steps["pbd_hinge_refresh_source"]
    step_names = [str(step.get("step")) for step in report.get("steps", [])]
    assert step_names.index("pbd_hinge_refresh_source") < step_names.index("pbd_hinge_refresh_artifact")
    assert report["inputs"]["pbd_hinge_refresh_source_input"] == str(hinge_source_output)
    assert report["inputs"]["pbd_hinge_refresh_source_output"] == str(hinge_source_output)
    assert report["reports"]["pbd_hinge_refresh_source"] == str(hinge_source_output)


def test_nightly_release_gate_dry_run_prefers_explicit_panel_source_over_bundle(tmp_path: Path) -> None:
    out = tmp_path / "nightly_release_gate_report.json"
    joint_source = tmp_path / "joint_geometry_source.json"
    joint_source_output = tmp_path / "panel_zone_joint_geometry_3d.json"
    anchorage_source_output = tmp_path / "panel_zone_rebar_anchorage_3d.json"
    clash_source_output = tmp_path / "panel_zone_clash_verification_3d.json"
    joint_contract = tmp_path / "joint_geometry_contract.json"
    anchorage_contract = tmp_path / "rebar_anchorage_contract.json"
    clash_contract = tmp_path / "clash_verification_contract.json"
    bundle = FIXTURE_DIR / "panel_zone_solver_export_bundle.json"
    cmd = [
        sys.executable,
        "implementation/phase1/run_nightly_release_gate.py",
        "--dry-run",
        "--skip-promotion",
        "--panel-zone-solver-export-bundle",
        str(bundle),
        "--panel-zone-joint-geometry-artifact",
        str(joint_source),
        "--panel-zone-joint-geometry-source-output",
        str(joint_source_output),
        "--panel-zone-rebar-anchorage-source-output",
        str(anchorage_source_output),
        "--panel-zone-clash-verification-source-output",
        str(clash_source_output),
        "--panel-zone-joint-geometry-contract",
        str(joint_contract),
        "--panel-zone-rebar-anchorage-contract",
        str(anchorage_contract),
        "--panel-zone-clash-verification-contract",
        str(clash_contract),
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    report = json.loads(out.read_text(encoding="utf-8"))
    steps = {str(step.get("step")): str(step.get("command", "")) for step in report.get("steps", [])}
    assert str(joint_source) in steps["panel_zone_joint_geometry_source"]
    assert str(bundle) not in steps["panel_zone_joint_geometry_source"]
    assert str(bundle) in steps["panel_zone_rebar_anchorage_source"]
    assert str(bundle) in steps["panel_zone_clash_verification_source"]
    assert report["inputs"]["panel_zone_solver_export_bundle"] == str(bundle)
    assert report["inputs"]["panel_zone_joint_geometry_artifact"] == str(joint_source)
    assert report["inputs"]["panel_zone_rebar_anchorage_artifact"] == str(bundle)
    assert report["inputs"]["panel_zone_clash_verification_artifact"] == str(bundle)


def test_nightly_release_gate_dry_run_threads_custom_mgt_export_paths_into_release_gap(tmp_path: Path) -> None:
    out = tmp_path / "nightly_release_gate_report.json"
    projection_json = tmp_path / "custom.rebar_payload_projection.json"
    connection_projection_json = tmp_path / "custom.connection_detailing_payload_projection.json"
    detailing_projection_json = tmp_path / "custom.detailing_payload_projection.json"
    output_mgt = tmp_path / "custom.optimized.mgt"
    export_report = tmp_path / "custom.optimized.export_report.json"
    patch_manifest = tmp_path / "custom.optimized.patch_manifest.json"
    instruction_sidecar = tmp_path / "custom.optimized.instruction_sidecar.json"
    audit_review_manifest = tmp_path / "custom.optimized.audit_review_manifest.json"
    audit_review_packet_manifest = tmp_path / "custom.optimized.audit_review_packets.json"
    audit_review_packet_directory = tmp_path / "custom.optimized.audit_review_packet_files"
    audit_review_queue_manifest = tmp_path / "custom.optimized.audit_review_queue.json"
    audit_review_queue_status_directory = tmp_path / "custom.optimized.audit_review_queue_status_files"
    audit_review_followup_manifest = tmp_path / "custom.optimized.audit_review_followup_manifest.json"
    cmd = [
        sys.executable,
        "implementation/phase1/run_nightly_release_gate.py",
        "--dry-run",
        "--skip-promotion",
        "--design-opt-rebar-payload-projection-json",
        str(projection_json),
        "--design-opt-connection-detailing-payload-projection-json",
        str(connection_projection_json),
        "--design-opt-detailing-payload-projection-json",
        str(detailing_projection_json),
        "--mgt-export-output-mgt",
        str(output_mgt),
        "--mgt-export-report",
        str(export_report),
        "--mgt-export-patch-manifest",
        str(patch_manifest),
        "--mgt-export-instruction-sidecar",
        str(instruction_sidecar),
        "--mgt-export-audit-review-manifest",
        str(audit_review_manifest),
        "--mgt-export-audit-review-packet-manifest",
        str(audit_review_packet_manifest),
        "--mgt-export-audit-review-packet-directory",
        str(audit_review_packet_directory),
        "--mgt-export-audit-review-queue-manifest",
        str(audit_review_queue_manifest),
        "--mgt-export-audit-review-queue-status-directory",
        str(audit_review_queue_status_directory),
        "--mgt-export-audit-review-followup-manifest",
        str(audit_review_followup_manifest),
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    report = json.loads(out.read_text(encoding="utf-8"))
    steps = {str(step.get("step")): str(step.get("command", "")) for step in report.get("steps", [])}
    assert report["inputs"]["design_opt_rebar_payload_projection_json"] == str(projection_json)
    assert report["inputs"]["design_opt_connection_detailing_payload_projection_json"] == str(connection_projection_json)
    assert report["inputs"]["design_opt_detailing_payload_projection_json"] == str(detailing_projection_json)
    assert report["inputs"]["mgt_export_output_mgt"] == str(output_mgt)
    assert report["inputs"]["mgt_export_report"] == str(export_report)
    assert report["inputs"]["mgt_export_patch_manifest"] == str(patch_manifest)
    assert report["inputs"]["mgt_export_instruction_sidecar"] == str(instruction_sidecar)
    assert report["inputs"]["mgt_export_audit_review_manifest"] == str(audit_review_manifest)
    assert report["inputs"]["mgt_export_audit_review_packet_manifest"] == str(audit_review_packet_manifest)
    assert report["inputs"]["mgt_export_audit_review_packet_directory"] == str(audit_review_packet_directory)
    assert report["inputs"]["mgt_export_audit_review_queue_manifest"] == str(audit_review_queue_manifest)
    assert report["inputs"]["mgt_export_audit_review_queue_status_directory"] == str(audit_review_queue_status_directory)
    assert report["inputs"]["mgt_export_audit_review_followup_manifest"] == str(audit_review_followup_manifest)
    assert report["reports"]["design_opt_rebar_payload_projection"] == str(projection_json)
    assert report["reports"]["design_opt_connection_detailing_payload_projection"] == str(connection_projection_json)
    assert report["reports"]["design_opt_detailing_payload_projection"] == str(detailing_projection_json)
    assert report["reports"]["mgt_export_output_mgt"] == str(output_mgt)
    assert report["reports"]["mgt_export"] == str(export_report)
    assert report["reports"]["mgt_export_patch_manifest"] == str(patch_manifest)
    assert report["reports"]["mgt_export_instruction_sidecar"] == str(instruction_sidecar)
    assert report["reports"]["mgt_export_audit_review_manifest"] == str(audit_review_manifest)
    assert report["reports"]["mgt_export_audit_review_packet_manifest"] == str(audit_review_packet_manifest)
    assert report["reports"]["mgt_export_audit_review_packet_directory"] == str(audit_review_packet_directory)
    assert report["reports"]["mgt_export_audit_review_queue_manifest"] == str(audit_review_queue_manifest)
    assert report["reports"]["mgt_export_audit_review_queue_status_directory"] == str(audit_review_queue_status_directory)
    assert report["reports"]["mgt_export_audit_review_followup_manifest"] == str(audit_review_followup_manifest)
    assert str(projection_json) in steps["design_optimization_rebar_payload_projection"]
    assert str(connection_projection_json) in steps["design_optimization_connection_detailing_payload_projection"]
    assert str(detailing_projection_json) in steps["design_optimization_detailing_payload_projection"]
    assert str(output_mgt) in steps["mgt_export_direct_patch"]
    assert str(export_report) in steps["mgt_export_direct_patch"]
    assert str(patch_manifest) in steps["mgt_export_direct_patch"]
    assert str(instruction_sidecar) in steps["mgt_export_direct_patch"]
    assert str(audit_review_packet_directory) in steps["mgt_export_direct_patch"]
    assert str(audit_review_queue_manifest) in steps["mgt_export_direct_patch"]
    assert str(audit_review_queue_status_directory) in steps["mgt_export_direct_patch"]
    assert str(audit_review_followup_manifest) in steps["mgt_export_direct_patch"]
    assert str(output_mgt) in steps["release_gap_report"]
    assert str(export_report) in steps["release_gap_report"]
    assert str(audit_review_queue_manifest) in steps["release_gap_report"]
    assert str(audit_review_followup_manifest) in steps["release_gap_report"]
