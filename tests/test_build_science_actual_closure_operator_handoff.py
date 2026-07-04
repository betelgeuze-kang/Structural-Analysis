from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_science_actual_closure_operator_handoff.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "build_science_actual_closure_operator_handoff",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _slots_by_id(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    slots = payload["row_slot_handoffs"]
    assert isinstance(slots, list)
    return {
        str(slot["row_input_id"]): slot
        for slot in slots
        if isinstance(slot, dict) and "row_input_id" in slot
    }


def test_science_actual_closure_operator_handoff_exposes_all_row_slots() -> None:
    payload = module.build_science_actual_closure_operator_handoff(repo_root=REPO_ROOT)
    slots = _slots_by_id(payload)

    assert payload["schema_version"] == "science-actual-closure-operator-handoff.v1"
    assert payload["status"] == "operator_rows_required"
    assert payload["contract_pass"] is True
    assert payload["science_actual_closure_contract_pass"] is False
    assert payload["summary"] == {
        "blocker_count": 10,
        "blocked_component_operator_action_count": 2,
        "closes_actual_closure_criteria_count": 19,
        "component_count": 3,
        "expected_slot_count": 6,
        "missing_row_template_artifact_count": 0,
        "missing_slot_count": 2,
        "operator_rows_packet_missing_input_count": 2,
        "provided_slot_count": 4,
        "row_template_artifact_count": 6,
        "science_actual_closure_blocker_count": 2,
        "slot_count": 6,
        "upstream_source_blocker_count": 8,
        "upstream_source_context_count": 2,
    }
    assert payload["blocker_count"] == 10
    assert payload["science_actual_closure_blockers"] == [
        (
            "public_benchmark_phase2_actual_closure::"
            "vina_gnina_comparison_adapter::vina_gnina_rows_not_provided"
        ),
        "pocketmd_lite_topk_actual_closure::pocketmd_lite_topk_rows_not_provided",
    ]
    assert payload["blockers"][:2] == [
        (
            "science_actual_closure::public_benchmark_phase2_actual_closure::"
            "vina_gnina_comparison_adapter::vina_gnina_rows_not_provided"
        ),
        (
            "science_actual_closure::pocketmd_lite_topk_actual_closure::"
            "pocketmd_lite_topk_rows_not_provided"
        ),
    ]
    assert payload["blockers"][2:] == payload["upstream_source_blockers"]
    assert list(slots) == [
        "subset_rows",
        "pose_rows",
        "enrichment_rows",
        "vina_gnina_rows",
        "gpcr_rows",
        "pocketmd_rows",
    ]
    assert payload["missing_row_inputs"] == [
        "vina_gnina_rows",
        "pocketmd_rows",
    ]
    assert payload["operator_rows_packet"]["status"] == "operator_rows_required"
    assert payload["operator_rows_packet"]["missing_row_inputs"] == [
        "vina_gnina_rows",
        "pocketmd_rows",
    ]
    assert payload["operator_rows_packet"]["row_input_contract_count"] == 2
    assert payload["operator_rows_packet"]["first_missing_row_input"] == (
        "vina_gnina_rows"
    )
    row_contracts = payload["row_input_materialization_contracts"]
    assert sorted(row_contracts) == ["pocketmd_rows", "vina_gnina_rows"]
    assert row_contracts["vina_gnina_rows"]["operator_action"] == (
        "attach_vina_gnina_rows_at_"
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_vina_gnina_rows.json"
    )
    vina_contract_detail = row_contracts["vina_gnina_rows"][
        "row_input_slot_detail"
    ]
    assert vina_contract_detail["status"] == "execution_plan_blocked"
    assert vina_contract_detail["required_engine_run_count"] == 24
    assert vina_contract_detail["ready_engine_run_slot_count"] == 0
    assert vina_contract_detail["blocked_engine_run_slot_count"] == 24
    assert vina_contract_detail["missing_engine_ids"] == ["vina", "gnina"]
    assert vina_contract_detail["engine_run_status_summary"][
        "first_blocked_engine_run_slot"
    ]["case_id"] == "casf2016_4llx"
    assert row_contracts["pocketmd_rows"]["row_template_artifact"].endswith(
        "pocketmd_lite_topk_rows_template.csv"
    )
    pocketmd_contract_detail = row_contracts["pocketmd_rows"][
        "row_input_slot_detail"
    ]
    assert pocketmd_contract_detail["missing_candidate_slot_count"] == 6
    assert pocketmd_contract_detail["provided_candidate_slot_count"] == 0
    assert pocketmd_contract_detail["first_missing_candidate_slot"] == {
        "case_id": "pocketmd_lite_case_001",
        "operator_action": (
            "attach_pocketmd_topk_row_for_pocketmd_lite_case_001_rank_01"
        ),
        "slot_id": "pocketmd_lite_case_001_rank_01",
        "top_k_rank": 1,
    }
    blocked_actions = {
        row["component_id"]: row for row in payload["blocked_component_operator_actions"]
    }
    assert blocked_actions["public_benchmark_phase2_actual_closure"][
        "missing_row_input_ids"
    ] == ["vina_gnina_rows"]
    public_action = blocked_actions["public_benchmark_phase2_actual_closure"][
        "missing_row_input_actions"
    ][0]
    assert blocked_actions["public_benchmark_phase2_actual_closure"][
        "missing_row_input_action_count"
    ] == 1
    assert public_action["row_input_id"] == "vina_gnina_rows"
    assert public_action["operator_action"] == (
        "attach_vina_gnina_rows_at_"
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_vina_gnina_rows.json"
    )
    assert public_action["preferred_default_row_path"].endswith(
        "public_benchmark_vina_gnina_rows.json"
    )
    assert public_action["row_template_artifact"].endswith(
        "public_benchmark_vina_gnina_rows_template.csv"
    )
    assert public_action["source_acquisition_operator_action"] == (
        "resolve_public_benchmark_phase2_source_acquisition_blockers"
    )
    assert public_action["source_acquisition_row_action"]["operator_action"] == (
        "attach_vina_gnina_rows_then_run_phase2_row_audit"
    )
    assert public_action["source_acquisition_row_action"][
        "runtime_readiness_command"
    ].startswith("python3 scripts/build_public_benchmark_vina_gnina_runtime_readiness.py")
    assert "engine_config_checksum" in public_action["source_acquisition_row_action"][
        "receipt_fields"
    ]
    public_manifest_action = public_action["source_acquisition_row_action"][
        "engine_input_manifest_action_packet"
    ]
    assert public_manifest_action["expected_manifest_artifact"].endswith(
        "public_benchmark_vina_gnina_input_manifest.csv"
    )
    assert public_manifest_action["template_safety_policy"][
        "template_is_not_evidence"
    ] is True
    public_adapter_preflight_action = public_action["source_acquisition_row_action"][
        "adapter_row_preflight_action_packet"
    ]
    assert public_adapter_preflight_action["status"] == "row_artifact_missing"
    assert public_adapter_preflight_action["supported_candidate_paths"][3].endswith(
        "public_benchmark_vina_gnina_rows.csv"
    )
    assert public_adapter_preflight_action["template_safety_policy"][
        "preflight_does_not_run_engines"
    ] is True
    assert "public_benchmark_vina_gnina_engine_runtime_not_ready" in public_action[
        "upstream_source_blockers"
    ]
    assert blocked_actions["pocketmd_lite_topk_actual_closure"][
        "missing_row_input_ids"
    ] == ["pocketmd_rows"]
    pocketmd_action = blocked_actions["pocketmd_lite_topk_actual_closure"][
        "missing_row_input_actions"
    ][0]
    assert blocked_actions["pocketmd_lite_topk_actual_closure"][
        "missing_row_input_action_count"
    ] == 1
    assert pocketmd_action["row_input_id"] == "pocketmd_rows"
    assert pocketmd_action["operator_action"] == (
        "attach_pocketmd_rows_at_implementation/phase1/release_evidence/"
        "productization/pocketmd_lite_topk_rows.json"
    )
    assert pocketmd_action["preferred_default_row_path"].endswith(
        "pocketmd_lite_topk_rows.json"
    )
    assert pocketmd_action["row_template_artifact"].endswith(
        "pocketmd_lite_topk_rows_template.csv"
    )
    assert pocketmd_action["source_acquisition_operator_action"] == (
        "resolve_pocketmd_lite_source_acquisition_blockers"
    )
    assert pocketmd_action["source_acquisition_row_action"]["operator_action"] == (
        "attach_pocketmd_rows_at_implementation/phase1/release_evidence/"
        "productization/pocketmd_lite_topk_rows.json"
    )
    assert "materialize_survival" in pocketmd_action["source_acquisition_row_action"][
        "commands"
    ]
    assert "uncertainty_interval_receipt" in pocketmd_action[
        "source_acquisition_row_action"
    ]["required_receipt_roles"]
    pocketmd_preflight_action = pocketmd_action["source_acquisition_row_action"][
        "row_preflight_action_packet"
    ]
    assert pocketmd_preflight_action["status"] == "row_artifact_missing"
    assert pocketmd_preflight_action["supported_candidate_paths"][4].endswith(
        "pocketmd_lite_topk_rows.tsv"
    )
    assert len(pocketmd_preflight_action["missing_required_slots"]) == 6
    assert pocketmd_preflight_action["template_safety_policy"][
        "preflight_does_not_run_refinement"
    ] is True
    pocketmd_topk_action = pocketmd_action["source_acquisition_row_action"][
        "top_k_rows_action_packet"
    ]
    assert pocketmd_topk_action["expected_rows_artifact"].endswith(
        "pocketmd_lite_topk_rows.json"
    )
    assert pocketmd_topk_action["template_safety_policy"][
        "placeholder_or_fixture_rows_do_not_promote"
    ] is True
    pocketmd_rows_arg = (
        "--pocketmd-rows implementation/phase1/release_evidence/productization/"
        "pocketmd_lite_topk_rows.json"
    )
    assert (
        pocketmd_rows_arg
        in pocketmd_topk_action["verify_science_actual_closure_command"]
    )
    assert "--source-url <source-url>" in pocketmd_topk_action[
        "verify_science_actual_closure_command"
    ]
    assert "pocketmd_lite_topk_rows_not_acquired" in pocketmd_action[
        "upstream_source_blockers"
    ]
    assert len(payload["upstream_source_blockers"]) == 8
    assert payload["upstream_source_acquisition"]["public_benchmark_phase2"][
        "present"
    ] is True
    assert payload["upstream_source_acquisition"]["pocketmd_lite"]["present"] is True
    assert payload["missing_row_template_artifacts"] == []
    assert payload["row_template_artifacts"] == {
        "enrichment_rows": (
            "implementation/phase1/release_evidence/productization/"
            "public_benchmark_enrichment_rows_template.csv"
        ),
        "gpcr_rows": (
            "implementation/phase1/release_evidence/productization/"
            "gpcr_hard_decoy_rows_template.csv"
        ),
        "pocketmd_rows": (
            "implementation/phase1/release_evidence/productization/"
            "pocketmd_lite_topk_rows_template.csv"
        ),
        "pose_rows": (
            "implementation/phase1/release_evidence/productization/"
            "public_benchmark_pose_rows_template.csv"
        ),
        "subset_rows": (
            "implementation/phase1/release_evidence/productization/"
            "public_benchmark_subset_rows_template.csv"
        ),
        "vina_gnina_rows": (
            "implementation/phase1/release_evidence/productization/"
            "public_benchmark_vina_gnina_rows_template.csv"
        ),
    }
    assert payload["first_missing_slot"]["row_input_id"] == "vina_gnina_rows"

    subset = slots["subset_rows"]
    assert subset["status"] == "provided"
    assert subset["missing"] is False
    assert subset["row_template_present"] is True
    assert subset["row_template_artifact"].endswith(
        "public_benchmark_subset_rows_template.csv"
    )
    assert subset["preferred_default_row_path"].endswith(
        "public_benchmark_subset_rows.json"
    )
    assert subset["actual_closure_component_id"] == (
        "public_benchmark_phase2_actual_closure"
    )
    assert "casf_pdbbind_pose_success_harness_ready" in subset[
        "closes_actual_closure_criteria"
    ]
    assert "source_receipt_required_fields" in subset["contract_field_groups"]
    assert any(
        "materialize_public_benchmark" in step
        for step in subset["materialization_chain"]
    )

    pose = slots["pose_rows"]
    assert pose["status"] == "provided"
    assert {
        "symmetry_aware_ligand_rmsd_ready",
        "posebusters_style_pose_validity_ready",
    }.issubset(set(pose["closes_actual_closure_criteria"]))
    assert "required_pose_fields" in pose["contract_field_groups"]

    enrichment = slots["enrichment_rows"]
    assert enrichment["status"] == "provided"

    vina_gnina = slots["vina_gnina_rows"]
    assert vina_gnina["status"] == "operator_input_required"
    assert vina_gnina["missing"] is True
    assert vina_gnina["upstream_source_id"] == "public_benchmark_phase2"
    assert vina_gnina["source_acquisition_operator_action"] == (
        "resolve_public_benchmark_phase2_source_acquisition_blockers"
    )
    assert "public_benchmark_vina_gnina_engine_runtime_not_ready" in vina_gnina[
        "upstream_source_blockers"
    ]
    assert "public_benchmark_vina_gnina_input_manifest_not_detected" in vina_gnina[
        "upstream_source_blockers"
    ]
    vina_detail = vina_gnina["row_input_slot_detail"]
    assert vina_detail["artifact"].endswith(
        "public_benchmark_vina_gnina_runtime_readiness.json"
    )
    assert vina_detail["engine_run_status_summary"] == {
        "blocked_engine_run_slot_count": 24,
        "first_blocked_engine_run_slot": vina_detail["engine_run_slots"][0],
        "first_ready_engine_run_slot": {},
        "ready_engine_run_slot_count": 0,
        "required_engine_run_count": 24,
    }
    assert vina_detail["engine_run_slots"][0]["operator_actions"] == [
        "resolve_vina_gnina_case_inputs_for_casf2016_4llx",
        "configure_vina_runtime",
        "attach_vina_gnina_adapter_row_for_casf2016_4llx_vina",
    ]
    assert vina_detail["operator_unblock_packet"]["status"] == (
        "engine_inputs_required"
    )
    assert vina_detail["operator_unblock_packet"][
        "input_manifest_template_artifact"
    ].endswith("public_benchmark_vina_gnina_input_manifest_template.csv")
    assert vina_detail["operator_unblock_packet"][
        "blocked_engine_run_slot_count"
    ] == 24
    assert vina_detail["engine_run_slots"][0]["required_adapter_engine_run_fields"] == [
        "engine_id",
        "docking_run_id",
        "predicted_ligand_path_or_pose_ref",
        "predicted_ligand_checksum",
        "engine_version",
        "engine_config_checksum",
        "engine_run_provenance_ref",
        "symmetry_aware_rmsd_angstrom",
        "pose_success",
        "score",
        "score_direction",
    ]

    gpcr = slots["gpcr_rows"]
    assert gpcr["actual_closure_component_id"] == "gpcr_hard_decoy_actual_closure"
    assert gpcr["status"] == "provided"
    assert gpcr["missing"] is False
    assert gpcr["row_template_present"] is True
    assert gpcr["row_template_artifact"].endswith(
        "gpcr_hard_decoy_rows_template.csv"
    )
    assert "raw_hard_decoy_rows_actual_closure" in gpcr[
        "closes_actual_closure_criteria"
    ]
    assert gpcr["materialization_command"].startswith(
        "python3 scripts/materialize_science_actual_closure_from_rows.py --gpcr-rows"
    )
    assert gpcr["contract_field_groups"]["source_receipt_required_fields"] == [
        "source_id",
        "source_url",
        "source_license",
        "source_artifact_sha256",
    ]
    gpcr_detail = gpcr["row_input_slot_detail"]
    assert gpcr_detail["artifact"].endswith("gpcr_hard_decoy_suite_report.json")
    assert gpcr_detail["status"] == "ready"
    assert gpcr_detail["actual_closure_ready"] is True
    assert gpcr_detail["phase3_exit_gate_status"] == "ready"
    assert gpcr_detail["phase3_failed_criteria"] == []
    assert gpcr_detail["target_count"] == 3
    assert gpcr_detail["target_pass_count"] == 3
    assert gpcr_detail["exit_criteria"] == {
        "decoys_above_positive_count_max": 0,
        "positive_out_anchored_by_top_decoys_allowed": False,
        "ranking_pr_auc_ci_low_min": 0.45,
        "top20_hit_rate_min": 0.2,
    }
    assert gpcr_detail["observed_threshold_metrics"] == {
        "decoys_above_positive_count_max_observed": 0,
        "positive_out_anchored_target_count": 0,
        "ranking_pr_auc_ci_low_min_observed": 1,
        "top20_hit_rate_min_observed": 0.6,
    }
    assert gpcr_detail["target_rows"][0] == {
        "blockers": [],
        "contract_pass": True,
        "criteria": {
            "decoys_above_positive_count_max": 0,
            "positive_out_anchored_by_top_decoys_allowed": False,
            "ranking_pr_auc_ci_low_min": 0.45,
            "top20_hit_rate_min": 0.2,
        },
        "decoys_above_positive_count": 0,
        "positive_out_anchored_by_top_decoys": False,
        "ranking_pr_auc_ci_low": 1,
        "status": "pass",
        "target_id": "DRD2",
        "top20_hit_rate": 0.6,
    }

    pocketmd = slots["pocketmd_rows"]
    assert pocketmd["actual_closure_component_id"] == (
        "pocketmd_lite_topk_actual_closure"
    )
    assert pocketmd["status"] == "operator_input_required"
    assert pocketmd["missing"] is True
    assert pocketmd["row_template_present"] is True
    assert pocketmd["row_template_artifact"].endswith(
        "pocketmd_lite_topk_rows_template.csv"
    )
    assert pocketmd["upstream_source_id"] == "pocketmd_lite"
    assert pocketmd["source_acquisition_operator_action"] == (
        "resolve_pocketmd_lite_source_acquisition_blockers"
    )
    assert "pocketmd_lite_topk_rows_not_acquired" in pocketmd[
        "upstream_source_blockers"
    ]
    assert "top_k_refinement_rows_present" in pocketmd[
        "closes_actual_closure_criteria"
    ]
    assert "broad_all_atom_fep_claims_locked" in pocketmd[
        "closes_actual_closure_criteria"
    ]
    assert "required_case_fields" in pocketmd["contract_field_groups"]
    assert "uncertainty_field_modes" in pocketmd["contract_field_groups"]
    assert pocketmd["row_input_slot_detail"]["artifact"].endswith(
        "pocketmd_lite_refinement_execution_plan.json"
    )
    assert pocketmd["row_input_slot_detail"]["top_k_slot_status_summary"][
        "missing_candidate_slot_count"
    ] == 6
    assert pocketmd["row_input_slot_detail"]["operator_unblock_packet"]["status"] == (
        "operator_refinement_rows_required"
    )
    assert pocketmd["row_input_slot_detail"]["operator_unblock_packet"][
        "row_template_artifact"
    ].endswith("pocketmd_lite_topk_rows_template.csv")
    assert pocketmd["row_input_slot_detail"]["candidate_slot_statuses"][0] == {
        "case_id": "pocketmd_lite_case_001",
        "expected_rows_artifact": (
            "implementation/phase1/release_evidence/productization/"
            "pocketmd_lite_topk_rows.json"
        ),
        "missing": True,
        "operator_action": (
            "attach_pocketmd_topk_row_for_pocketmd_lite_case_001_rank_01"
        ),
        "provided": False,
        "required_metric_fields": [
            "local_min_survived",
            "contact_persistence_rate",
            "h_bond_persistence_rate",
            "clash_count_before",
            "clash_count_after",
            "uncertainty_low",
            "uncertainty_high",
            "uncertainty_unit",
        ],
        "required_receipt_fields": [
            "upstream_top_k_provenance_ref",
            "upstream_top_k_source_checksum",
            "provenance_ref",
            "source_checksum",
            "operator_input_source.source_artifact",
            "operator_input_source.source_artifact_sha256",
            "operator_input_source.source_id",
            "operator_input_source.source_url",
            "operator_input_source.source_license",
        ],
        "slot_id": "pocketmd_lite_case_001_rank_01",
        "status": "row_slot_missing",
        "top_k_rank": 1,
    }

    component_summaries = {
        row["component_id"]: row for row in payload["component_slot_summary"]
    }
    assert component_summaries["public_benchmark_phase2_actual_closure"][
        "missing_row_input_ids"
    ] == ["vina_gnina_rows"]
    assert component_summaries["gpcr_hard_decoy_actual_closure"][
        "missing_row_input_ids"
    ] == []
    assert component_summaries["pocketmd_lite_topk_actual_closure"][
        "missing_row_input_ids"
    ] == ["pocketmd_rows"]


def test_science_actual_closure_operator_handoff_cli_writes_json_and_markdown(
    tmp_path: Path,
) -> None:
    out = tmp_path / "handoff.json"
    out_md = tmp_path / "handoff.md"

    assert module.main(
        [
            "--repo-root",
            str(REPO_ROOT),
            "--out",
            str(out),
            "--out-md",
            str(out_md),
        ]
    ) == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    markdown = out_md.read_text(encoding="utf-8")
    assert payload["contract_pass"] is True
    assert payload["row_slot_handoff_count"] == 6
    assert payload["summary"]["row_template_artifact_count"] == 6
    assert payload["summary"]["missing_slot_count"] == 2
    assert payload["input_checksums"][
        "scripts/build_science_actual_closure_operator_handoff.py"
    ].startswith("sha256:")
    assert payload["input_checksums"][
        "implementation/phase1/release_evidence/productization/"
        "pocketmd_lite_refinement_execution_plan.json"
    ].startswith("sha256:")
    assert payload["input_checksums"][
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_vina_gnina_runtime_readiness.json"
    ].startswith("sha256:")
    assert payload["input_checksums"][
        "implementation/phase1/release_evidence/productization/"
        "gpcr_hard_decoy_suite_report.json"
    ].startswith("sha256:")
    assert "| `subset_rows` | `provided` |" in markdown
    assert "| `vina_gnina_rows` | `operator_input_required` |" in markdown
    assert "| `pocketmd_rows` | `operator_input_required` |" in markdown
    assert "- `blocker_count`: `10`" in markdown
    assert "## Missing Row Packet" in markdown
    assert "## Blocked Component Actions" in markdown
    assert "public_benchmark_phase2_actual_closure" in markdown
    assert "pocketmd_lite_topk_actual_closure" in markdown
    assert "Source Row Action" in markdown
    assert "Source Command" in markdown
    assert "Required Receipts" in markdown
    assert "attach_vina_gnina_rows_then_run_phase2_row_audit" in markdown
    assert "build_public_benchmark_vina_gnina_runtime_readiness.py" in markdown
    assert "engine_config_checksum" in markdown
    assert "materialize_pocketmd_lite_operator_intake_from_rows.py" in markdown
    assert "uncertainty_interval_receipt" in markdown
    assert "### Vina/GNINA Input Manifest Action" in markdown
    assert "public_benchmark_vina_gnina_input_manifest.csv" in markdown
    assert "`do_not_treat_blank_prepared_checksums_as_ready`: `True`" in markdown
    assert "### Vina/GNINA Adapter Row Preflight Action" in markdown
    assert "public_benchmark_vina_gnina_rows.csv" in markdown
    assert "`operator_rows_must_be_real_engine_outputs`: `True`" in markdown
    assert "### PocketMD Top-k Rows Action" in markdown
    assert "### PocketMD Row Preflight Action" in markdown
    assert "pocketmd_lite_topk_rows.tsv" in markdown
    assert "`operator_rows_must_be_real_top_k_refinement_outputs`: `True`" in markdown
    assert "operator_input_source.source_artifact_sha256" in markdown
    assert "`placeholder_or_fixture_rows_do_not_promote`: `True`" in markdown
    assert "attach_pocketmd_rows_at_" in markdown
    assert "CSV Starter" in markdown
    assert "## Upstream Source Blockers" in markdown
    assert "public_benchmark_vina_gnina_engine_runtime_not_ready" in markdown
    assert (
        "public_benchmark_vina_gnina_engine_binaries_or_container_images_missing"
        in markdown
    )
    assert "public_benchmark_vina_gnina_input_manifest_not_detected" in markdown
    assert "### Vina/GNINA Engine Run Slots" in markdown
    assert "`operator_unblock_status`: `engine_inputs_required`" in markdown
    assert "public_benchmark_vina_gnina_input_manifest_template.csv" in markdown
    assert "casf2016_4llx_vina_casf2016_4llx_vina_run" in markdown
    assert "configure_vina_runtime" in markdown
    assert "## Provided Closure Evidence" in markdown
    assert "### GPCR Phase 3 Gate" in markdown
    assert "| `DRD2` | `1.0` | `0.6` | `0` | `False` | `pass` |" in markdown
    assert "pocketmd_lite_topk_rows_not_acquired" in markdown
    assert "### PocketMD Top-k Candidate Slots" in markdown
    assert "`operator_unblock_status`: `operator_refinement_rows_required`" in markdown
    assert "pocketmd_lite_case_001_rank_01" in markdown
    assert "attach_pocketmd_topk_row_for_pocketmd_lite_case_001_rank_01" in markdown
    assert "public_benchmark_subset_rows_template.csv" in markdown
    assert "gpcr_hard_decoy_rows_template.csv" in markdown
    assert "pocketmd_lite_topk_rows_template.csv" in markdown
    assert (
        "--pocketmd-rows implementation/phase1/release_evidence/productization/"
        "pocketmd_lite_topk_rows.json"
    ) in markdown
    assert "--source-license <license>" in markdown
    assert "materialize_science_actual_closure_from_rows.py --fail-blocked" in markdown
