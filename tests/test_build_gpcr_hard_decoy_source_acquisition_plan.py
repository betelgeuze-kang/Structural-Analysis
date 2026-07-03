from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_gpcr_hard_decoy_source_acquisition_plan.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "build_gpcr_hard_decoy_source_acquisition_plan",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_gpcr_hard_decoy_source_acquisition_plan_exposes_verified_targets() -> None:
    payload = module.build_gpcr_hard_decoy_source_acquisition_plan(
        repo_root=REPO_ROOT,
    )
    sources = {row["target_id"]: row for row in payload["target_sources"]}

    assert payload["schema_version"] == (
        "gpcr-hard-decoy-source-acquisition-plan.v1"
    )
    assert payload["status"] == "operator_acquisition_required"
    assert payload["contract_pass"] is True
    assert payload["actual_closure_ready"] is False
    assert payload["required_targets"] == ["DRD2", "HTR2A", "OPRM1"]
    assert payload["target_source_count"] == 3
    assert payload["target_source_ids"] == {
        "DRD2": {
            "chembl_target_id": "CHEMBL217",
            "uniprot_accession": "P14416",
        },
        "HTR2A": {
            "chembl_target_id": "CHEMBL224",
            "uniprot_accession": "P28223",
        },
        "OPRM1": {
            "chembl_target_id": "CHEMBL233",
            "uniprot_accession": "P35372",
        },
    }
    assert sources["DRD2"]["chembl_pref_name"] == "D(2) dopamine receptor"
    assert sources["HTR2A"]["chembl_pref_name"] == (
        "5-hydroxytryptamine receptor 2A"
    )
    assert sources["OPRM1"]["chembl_pref_name"] == "Mu-type opioid receptor"
    for target_id, row in sources.items():
        assert row["organism"] == "Homo sapiens"
        assert row["target_type"] == "SINGLE PROTEIN"
        assert row["source_role"] == "target_activity_candidate_source_only"
        assert row["minimum_positive_rows_required"] == 4
        assert row["minimum_decoy_rows_required"] == 20
        assert row["minimum_total_rows_required"] == 24
        assert row["chembl_target_record_url"].endswith(
            f"/target/{row['chembl_target_id']}.json"
        )
        assert row["target_specific_row_filter"]["target_id"] == target_id

    assert payload["row_artifact_contract"]["default_output"] == (
        "implementation/phase1/release_evidence/productization/"
        "gpcr_hard_decoy_rows.json"
    )
    assert payload["row_artifact_contract"]["source_attached_candidate_artifact"] == (
        "implementation/phase1/release_evidence/productization/"
        "gpcr_hard_decoy_chembl_activity_rows.json"
    )
    assert payload["row_artifact_contract"]["required_flat_row_fields"] == [
        "target_id",
        "molecule_id",
        "score",
        "is_positive",
        "is_decoy",
        "score_direction",
        "source_checksum",
        "provenance_ref",
    ]
    assert payload["positive_source_snapshot"]["artifact"] == (
        "implementation/phase1/release_evidence/productization/"
        "gpcr_hard_decoy_positive_source_snapshot.json"
    )
    assert payload["positive_source_snapshot"]["actual_closure_ready"] is False
    assert payload["positive_source_snapshot"]["positive_source_ready"] is True
    assert payload["positive_source_snapshot"]["target_candidate_counts"] == {
        "DRD2": 12,
        "HTR2A": 12,
        "OPRM1": 12,
    }
    assert payload["decoy_source_snapshot"]["artifact"] == (
        "implementation/phase1/release_evidence/productization/"
        "gpcr_hard_decoy_decoy_source_snapshot.json"
    )
    assert payload["decoy_source_snapshot"]["actual_closure_ready"] is False
    assert payload["decoy_source_snapshot"]["decoy_candidate_source_ready"] is True
    assert payload["decoy_source_snapshot"]["minimum_decoy_rows_per_target"] == 20
    assert payload["decoy_source_snapshot"]["target_candidate_counts"] == {
        "DRD2": 20,
        "HTR2A": 20,
        "OPRM1": 20,
    }
    assert payload["chembl_activity_rows"]["artifact"] == (
        "implementation/phase1/release_evidence/productization/"
        "gpcr_hard_decoy_chembl_activity_rows.json"
    )
    assert payload["chembl_activity_rows"]["actual_closure_ready"] is False
    assert payload["chembl_activity_rows"]["raw_rows_ready"] is True
    assert payload["chembl_activity_rows"]["row_count"] == 96
    assert payload["chembl_activity_rows"]["target_counts"] == {
        "DRD2": {"decoy_count": 20, "positive_count": 12, "total_count": 32},
        "HTR2A": {"decoy_count": 20, "positive_count": 12, "total_count": 32},
        "OPRM1": {"decoy_count": 20, "positive_count": 12, "total_count": 32},
    }
    assert payload["acceptable_source_roles"][0]["candidate_snapshot"] == (
        payload["positive_source_snapshot"]
    )
    assert payload["acceptable_source_roles"][1]["candidate_snapshot"] == (
        payload["decoy_source_snapshot"]
    )
    assert payload["acceptable_source_roles"][2]["candidate_snapshot"] == (
        payload["chembl_activity_rows"]
    )
    assert payload["summary"]["actual_closure_ready"] is False
    assert payload["summary"]["blocker_count"] == 3
    assert payload["summary"]["minimum_decoy_rows_total"] == 60
    assert payload["summary"]["minimum_positive_rows_total"] == 12
    assert payload["summary"]["decoy_candidate_source_ready"] is True
    assert payload["summary"]["total_decoy_candidate_count"] == 60
    assert payload["summary"]["positive_source_ready"] is True
    assert payload["summary"]["total_positive_candidate_count"] == 36
    assert payload["summary"]["chembl_activity_rows_ready"] is True
    assert payload["summary"]["chembl_activity_row_count"] == 96
    assert payload["summary"]["chembl_activity_rows_status"] == (
        "raw_activity_rows_ready"
    )
    assert payload["summary"]["required_target_count"] == 3
    assert payload["summary"]["target_source_count"] == 3
    assert payload["summary"]["target_source_mapping_complete"] is True
    assert payload["blockers"] == [
        "gpcr_activity_ranked_rows_require_operator_promotion_review",
        "gpcr_activity_ranked_rows_not_imported_to_operator_template",
        "gpcr_suite_not_rematerialized_from_raw_rows",
    ]
    assert payload["commands"]["import_rows"].startswith(
        "python3 scripts/materialize_gpcr_hard_decoy_operator_template_from_rows.py"
    )
    assert payload["commands"]["build_positive_source_snapshot"].startswith(
        "python3 scripts/build_gpcr_hard_decoy_positive_source_snapshot.py"
    )
    assert payload["commands"]["build_decoy_source_snapshot"].startswith(
        "python3 scripts/build_gpcr_hard_decoy_decoy_source_snapshot.py"
    )
    assert payload["commands"]["build_chembl_activity_rows"].startswith(
        "python3 scripts/build_gpcr_hard_decoy_chembl_activity_rows.py"
    )


def test_gpcr_hard_decoy_source_acquisition_plan_cli_writes_markdown(
    tmp_path: Path,
) -> None:
    out = tmp_path / "gpcr_hard_decoy_source_acquisition_plan.json"
    out_md = tmp_path / "gpcr_hard_decoy_source_acquisition_plan.md"

    assert module.main(["--repo-root", str(REPO_ROOT), "--out", str(out), "--out-md", str(out_md)]) == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    markdown = out_md.read_text(encoding="utf-8")
    assert payload["contract_pass"] is True
    assert payload["target_source_ids"]["DRD2"]["chembl_target_id"] == "CHEMBL217"
    assert "# GPCR Hard-Decoy Source Acquisition Plan" in markdown
    assert "`DRD2` | `P14416` | `CHEMBL217`" in markdown
    assert "`HTR2A` | `P28223` | `CHEMBL224`" in markdown
    assert "`OPRM1` | `P35372` | `CHEMBL233`" in markdown
    assert "gpcr_hard_decoy_positive_source_snapshot.json" in markdown
    assert "gpcr_hard_decoy_decoy_source_snapshot.json" in markdown
    assert "materialize_gpcr_hard_decoy_operator_template_from_rows.py" in markdown
