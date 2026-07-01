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
        "closes_actual_closure_criteria_count": 19,
        "component_count": 3,
        "expected_slot_count": 6,
        "missing_slot_count": 6,
        "provided_slot_count": 0,
        "science_actual_closure_blocker_count": 8,
        "slot_count": 6,
    }
    assert list(slots) == [
        "subset_rows",
        "pose_rows",
        "enrichment_rows",
        "vina_gnina_rows",
        "gpcr_rows",
        "pocketmd_rows",
    ]
    assert payload["missing_row_inputs"] == list(slots)
    assert payload["first_missing_slot"]["row_input_id"] == "subset_rows"

    subset = slots["subset_rows"]
    assert subset["status"] == "operator_input_required"
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
    assert {
        "symmetry_aware_ligand_rmsd_ready",
        "posebusters_style_pose_validity_ready",
    }.issubset(set(pose["closes_actual_closure_criteria"]))
    assert "required_pose_fields" in pose["contract_field_groups"]

    gpcr = slots["gpcr_rows"]
    assert gpcr["actual_closure_component_id"] == "gpcr_hard_decoy_actual_closure"
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
    assert "top_k_refinement_rows_present" in pocketmd[
        "closes_actual_closure_criteria"
    ]
    assert "broad_all_atom_fep_claims_locked" in pocketmd[
        "closes_actual_closure_criteria"
    ]
    assert "required_case_fields" in pocketmd["contract_field_groups"]
    assert "uncertainty_field_modes" in pocketmd["contract_field_groups"]

    component_summaries = {
        row["component_id"]: row for row in payload["component_slot_summary"]
    }
    assert component_summaries["public_benchmark_phase2_actual_closure"][
        "missing_row_input_ids"
    ] == [
        "subset_rows",
        "pose_rows",
        "enrichment_rows",
        "vina_gnina_rows",
    ]
    assert component_summaries["gpcr_hard_decoy_actual_closure"][
        "missing_row_input_ids"
    ] == ["gpcr_rows"]
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
    assert payload["input_checksums"][
        "scripts/build_science_actual_closure_operator_handoff.py"
    ].startswith("sha256:")
    assert "| `subset_rows` | `operator_input_required` |" in markdown
    assert "materialize_science_actual_closure_from_rows.py --fail-blocked" in markdown
