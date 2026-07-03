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
    assert blocked_actions["pocketmd_lite_topk_actual_closure"][
        "missing_row_input_ids"
    ] == ["pocketmd_rows"]
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
    assert "| `subset_rows` | `provided` |" in markdown
    assert "| `vina_gnina_rows` | `operator_input_required` |" in markdown
    assert "| `pocketmd_rows` | `operator_input_required` |" in markdown
    assert "## Missing Row Packet" in markdown
    assert "attach_pocketmd_rows_at_" in markdown
    assert "CSV Starter" in markdown
    assert "## Upstream Source Blockers" in markdown
    assert "public_benchmark_vina_gnina_engine_runtime_not_ready" in markdown
    assert (
        "public_benchmark_vina_gnina_engine_binaries_or_container_images_missing"
        in markdown
    )
    assert "public_benchmark_vina_gnina_input_manifest_not_detected" in markdown
    assert "pocketmd_lite_topk_rows_not_acquired" in markdown
    assert "### PocketMD Top-k Candidate Slots" in markdown
    assert "pocketmd_lite_case_001_rank_01" in markdown
    assert "attach_pocketmd_topk_row_for_pocketmd_lite_case_001_rank_01" in markdown
    assert "public_benchmark_subset_rows_template.csv" in markdown
    assert "gpcr_hard_decoy_rows_template.csv" in markdown
    assert "pocketmd_lite_topk_rows_template.csv" in markdown
    assert "materialize_science_actual_closure_from_rows.py --fail-blocked" in markdown
