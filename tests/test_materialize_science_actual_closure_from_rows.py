from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "materialize_science_actual_closure_from_rows.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location("materialize_science_actual_closure_from_rows", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _sha(seed: str) -> str:
    return f"sha256:{hashlib.sha256(seed.encode('utf-8')).hexdigest()}"


def _provenance_ref(case_id: str, candidate_id: str) -> str:
    return (
        "https://zenodo.org/records/2468135/files/"
        f"pocketmd-lite-{case_id}-{candidate_id}.json#row"
    )


def _write_gpcr_rows(path: Path) -> None:
    fieldnames = [
        "target_id",
        "score_direction",
        "molecule_id",
        "score",
        "is_positive",
        "is_decoy",
    ]
    rows = []
    for target_id in ("DRD2", "HTR2A", "OPRM1"):
        for index in range(1, 5):
            rows.append(
                [
                    target_id,
                    "higher_is_better",
                    f"{target_id}_positive_{index}",
                    f"{1.0 - index / 100:.2f}",
                    "true",
                    "false",
                ]
            )
        for index in range(1, 21):
            rows.append(
                [
                    target_id,
                    "higher_is_better",
                    f"{target_id}_decoy_{index}",
                    f"{0.50 - index / 100:.2f}",
                    "false",
                    "true",
                ]
            )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(fieldnames)
        writer.writerows(rows)


def _pocketmd_row(
    *,
    case_id: str,
    candidate_id: str,
    rank: int,
    local_min_survived: bool,
    contact_rate: float,
    h_bond_rate: float,
    clash_before: int,
    clash_after: int,
) -> dict[str, object]:
    return {
        "case_id": case_id,
        "source_family": "CASF/PDBBind operator intake",
        "top_k_rank": rank,
        "candidate_id": candidate_id,
        "pre_refinement_energy_proxy": -8.0 + rank,
        "post_refinement_energy_proxy": -8.5 + rank,
        "local_min_survived": local_min_survived,
        "contact_persistence_rate": contact_rate,
        "h_bond_persistence_rate": h_bond_rate,
        "clash_count_before": clash_before,
        "clash_count_after": clash_after,
        "uncertainty_low": -0.2 + rank / 10,
        "uncertainty_high": 0.2 + rank / 10,
        "uncertainty_unit": "energy_proxy_delta",
        "provenance_ref": _provenance_ref(case_id, candidate_id),
        "source_checksum": _sha(f"{case_id}:{candidate_id}"),
    }


def _write_pocketmd_rows(path: Path) -> None:
    payload = {
        "top_k_refinement_rows": [
            _pocketmd_row(
                case_id="case_a",
                candidate_id="pose_1",
                rank=1,
                local_min_survived=True,
                contact_rate=0.8,
                h_bond_rate=0.6,
                clash_before=4,
                clash_after=1,
            ),
            _pocketmd_row(
                case_id="case_a",
                candidate_id="pose_2",
                rank=2,
                local_min_survived=False,
                contact_rate=0.7,
                h_bond_rate=0.4,
                clash_before=2,
                clash_after=2,
            ),
            _pocketmd_row(
                case_id="case_b",
                candidate_id="pose_1",
                rank=1,
                local_min_survived=True,
                contact_rate=1.0,
                h_bond_rate=0.9,
                clash_before=5,
                clash_after=3,
            ),
            _pocketmd_row(
                case_id="case_b",
                candidate_id="pose_2",
                rank=2,
                local_min_survived=False,
                contact_rate=0.7,
                h_bond_rate=0.4,
                clash_before=2,
                clash_after=2,
            ),
            _pocketmd_row(
                case_id="case_c",
                candidate_id="pose_1",
                rank=1,
                local_min_survived=True,
                contact_rate=0.8,
                h_bond_rate=0.6,
                clash_before=4,
                clash_after=1,
            ),
            _pocketmd_row(
                case_id="case_c",
                candidate_id="pose_2",
                rank=2,
                local_min_survived=False,
                contact_rate=0.7,
                h_bond_rate=0.4,
                clash_before=2,
                clash_after=2,
            ),
        ]
    }
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def test_science_actual_closure_audit_blocks_without_operator_rows(tmp_path: Path) -> None:
    audit = module.build_science_actual_closure_audit(
        repo_root=REPO_ROOT,
        gpcr_template_out=tmp_path / "gpcr_template.json",
        gpcr_report_out=tmp_path / "gpcr_report.json",
        gpcr_surface_out=tmp_path / "gpcr_surface.json",
        pocketmd_intake_out=tmp_path / "pocketmd_intake.json",
        pocketmd_report_out=tmp_path / "pocketmd_report.json",
        pocketmd_surface_out=tmp_path / "pocketmd_surface.json",
    )

    assert audit["status"] == "operator_evidence_required"
    assert audit["contract_pass"] is False
    assert audit["component_ready_count"] == 0
    assert audit["blockers"] == [
        "gpcr_hard_decoy_actual_closure::gpcr_hard_decoy_rows_not_provided",
        "pocketmd_lite_topk_actual_closure::pocketmd_lite_topk_rows_not_provided",
    ]
    assert audit["summary"]["requirement_count"] == 14
    assert audit["summary"]["blocked_requirement_count"] == 13
    assert audit["summary"]["passing_requirement_count"] == 1
    assert audit["summary"]["actual_closure_ready"] is False
    assert audit["missing_row_inputs"] == ["gpcr_rows", "pocketmd_rows"]
    requirement_summary = audit["actual_closure_requirement_summary"]
    assert requirement_summary["gpcr_phase3_requirement_count"] == 5
    assert requirement_summary["gpcr_phase3_passing_requirement_count"] == 0
    assert requirement_summary["pocketmd_phase4_requirement_count"] == 9
    assert requirement_summary["pocketmd_phase4_passing_requirement_count"] == 1
    assert requirement_summary["blocked_component_ids"] == [
        "gpcr_hard_decoy_actual_closure",
        "pocketmd_lite_topk_actual_closure",
    ]
    component_summaries = {
        row["component_id"]: row["requirement_summary"]
        for row in audit["components"]
    }
    assert audit["component_requirement_summaries"] == [
        component_summaries["gpcr_hard_decoy_actual_closure"],
        component_summaries["pocketmd_lite_topk_actual_closure"],
    ]
    assert component_summaries["gpcr_hard_decoy_actual_closure"] == {
        "actual_closure_ready": False,
        "blocked_requirement_count": 5,
        "blocker_count": 15,
        "component_id": "gpcr_hard_decoy_actual_closure",
        "failed_criteria": [
            "ranking_pr_auc_ci_low_min",
            "top20_hit_rate_min",
            "decoys_above_positive_count_max",
            "no_positive_out_anchored_by_top_decoys",
            "raw_hard_decoy_rows_actual_closure",
        ],
        "failed_criterion_count": 5,
        "passing_requirement_count": 0,
        "requirement_count": 5,
    }
    assert audit["components"][0]["actual_closure_ready"] is False
    assert audit["components"][0]["failed_criteria"] == [
        "ranking_pr_auc_ci_low_min",
        "top20_hit_rate_min",
        "decoys_above_positive_count_max",
        "no_positive_out_anchored_by_top_decoys",
        "raw_hard_decoy_rows_actual_closure",
    ]
    assert component_summaries["pocketmd_lite_topk_actual_closure"] == {
        "actual_closure_ready": False,
        "blocked_requirement_count": 8,
        "blocker_count": 13,
        "component_id": "pocketmd_lite_topk_actual_closure",
        "failed_criteria": [
            "top_k_refinement_rows_present",
            "top_k_refinement_case_coverage",
            "local_min_survival_materialized",
            "contact_persistence_materialized",
            "h_bond_persistence_materialized",
            "clash_relief_materialized",
            "uncertainty_summary_materialized",
            "report_blockers_resolved",
        ],
        "failed_criterion_count": 8,
        "passing_requirement_count": 1,
        "requirement_count": 9,
    }
    assert audit["components"][1]["actual_closure_ready"] is False
    assert audit["components"][1]["failed_criteria"] == [
        "top_k_refinement_rows_present",
        "top_k_refinement_case_coverage",
        "local_min_survival_materialized",
        "contact_persistence_materialized",
        "h_bond_persistence_materialized",
        "clash_relief_materialized",
        "uncertainty_summary_materialized",
        "report_blockers_resolved",
    ]
    gpcr_requirements = [
        row
        for row in audit["actual_closure_requirements"]
        if row["component_id"] == "gpcr_hard_decoy_actual_closure"
    ]
    assert [row["criterion_id"] for row in gpcr_requirements] == [
        "ranking_pr_auc_ci_low_min",
        "top20_hit_rate_min",
        "decoys_above_positive_count_max",
        "no_positive_out_anchored_by_top_decoys",
        "raw_hard_decoy_rows_actual_closure",
    ]
    assert gpcr_requirements[0]["required"] == ">=0.45"
    assert gpcr_requirements[0]["failed_targets"] == ["DRD2", "HTR2A", "OPRM1"]
    assert gpcr_requirements[-1]["current_by_target"] == {
        "DRD2": "missing",
        "HTR2A": "missing",
        "OPRM1": "missing",
    }
    pocketmd_requirements = [
        row
        for row in audit["actual_closure_requirements"]
        if row["component_id"] == "pocketmd_lite_topk_actual_closure"
    ]
    assert [row["criterion_id"] for row in pocketmd_requirements] == [
        "top_k_refinement_rows_present",
        "top_k_refinement_case_coverage",
        "local_min_survival_materialized",
        "contact_persistence_materialized",
        "h_bond_persistence_materialized",
        "clash_relief_materialized",
        "uncertainty_summary_materialized",
        "report_blockers_resolved",
        "broad_all_atom_fep_claims_locked",
    ]
    assert pocketmd_requirements[0]["required"] == ">=6"
    assert pocketmd_requirements[-1]["pass"] is True
    assert "broad_all_atom_md_claim" in (
        pocketmd_requirements[-1]["blocked_claims_that_remain_locked"]
    )
    gpcr_contract = audit["row_intake_contracts"]["gpcr_rows"]
    assert gpcr_contract["required_targets"] == ["DRD2", "HTR2A", "OPRM1"]
    assert gpcr_contract["phase3_exit_criteria"] == {
        "decoys_above_positive_count_max": 0,
        "positive_out_anchored_by_top_decoys_allowed": False,
        "ranking_pr_auc_ci_low_min": 0.45,
        "top20_hit_rate_min": 0.2,
    }
    assert gpcr_contract["raw_row_quality_minimums"] == {
        "min_decoy_count_per_target": 20,
        "min_positive_count_per_target": 4,
        "min_total_row_count_per_target": 24,
    }
    assert gpcr_contract["required_flat_row_fields"] == [
        "target_id",
        "molecule_id",
        "score",
        "is_positive",
        "is_decoy",
    ]
    pocketmd_contract = audit["row_intake_contracts"]["pocketmd_rows"]
    assert "h_bond_persistence_rate" in pocketmd_contract["required_case_fields"]
    assert "uncertainty_width_median" in (
        pocketmd_contract["required_component_metrics"]
    )
    assert pocketmd_contract["top_k_row_quality_minimums"] == {
        "min_candidate_count_per_case": 2,
        "min_real_refinement_case_count": 3,
        "min_top_k_rank_coverage_per_case": 2,
        "min_total_top_k_candidate_count": 6,
    }
    assert pocketmd_contract["source_receipt_required_fields"] == [
        "source_id",
        "source_url",
        "source_license",
        "source_artifact_sha256",
        "per_row_source_checksum",
        "per_row_provenance_ref",
    ]
    assert pocketmd_contract["per_row_source_actuality_policy"][
        "placeholder_provenance_prefixes_rejected"
    ] == [
        "operator://",
        "local-evidence://",
        "local://",
        "fixture://",
        "mock://",
        "synthetic://",
        "placeholder://",
        "test://",
        "unit-test://",
    ]
    assert "broad_all_atom_md_claim" in (
        pocketmd_contract["blocked_claims_that_remain_locked"]
    )
    assert not (tmp_path / "gpcr_report.json").exists()
    assert not (tmp_path / "pocketmd_report.json").exists()


def test_science_actual_closure_audit_materializes_both_ready_surfaces(
    tmp_path: Path,
) -> None:
    gpcr_rows = tmp_path / "gpcr_rows.csv"
    pocketmd_rows = tmp_path / "pocketmd_rows.json"
    pocketmd_contract = tmp_path / "pocketmd_contract.json"
    _write_gpcr_rows(gpcr_rows)
    _write_pocketmd_rows(pocketmd_rows)
    pocketmd_contract.write_text(
        json.dumps({"schema_version": "pocketmd-lite-contract.v1", "contract_pass": True}),
        encoding="utf-8",
    )

    audit = module.build_science_actual_closure_audit(
        repo_root=REPO_ROOT,
        gpcr_rows_path=gpcr_rows,
        pocketmd_rows_path=pocketmd_rows,
        gpcr_template_out=tmp_path / "gpcr_template.json",
        gpcr_report_out=tmp_path / "gpcr_report.json",
        gpcr_surface_out=tmp_path / "gpcr_surface.json",
        pocketmd_intake_out=tmp_path / "pocketmd_intake.json",
        pocketmd_report_out=tmp_path / "pocketmd_report.json",
        pocketmd_surface_out=tmp_path / "pocketmd_surface.json",
        pocketmd_contract_path=pocketmd_contract,
        source_id="operator_attached_science_actual_closure_rows",
        source_url="https://zenodo.org/records/2468135",
        source_license="CC-BY-4.0",
    )

    assert audit["status"] == "ready"
    assert audit["contract_pass"] is True
    assert audit["component_ready_count"] == 2
    assert audit["blockers"] == []
    assert audit["missing_row_inputs"] == []
    assert audit["actual_closure_requirement_summary"] == {
        "actual_closure_ready": True,
        "blocked_component_ids": [],
        "blocked_requirement_count": 0,
        "gpcr_phase3_passing_requirement_count": 5,
        "gpcr_phase3_requirement_count": 5,
        "missing_row_input_count": 0,
        "missing_row_inputs": [],
        "passing_requirement_count": 14,
        "pocketmd_phase4_passing_requirement_count": 9,
        "pocketmd_phase4_requirement_count": 9,
        "ready_component_count": 2,
        "required_component_count": 2,
        "requirement_count": 14,
    }
    assert audit["row_intake_contracts"]["pocketmd_rows"]["max_top_k"] == 20

    gpcr = audit["components"][0]
    pocketmd = audit["components"][1]
    assert gpcr["phase3_exit_gate_status"] == "ready"
    assert len(gpcr["phase3_exit_gate_criteria"]) == 5
    assert gpcr["target_pass_count"] == 3
    assert gpcr["actual_closure_ready"] is True
    assert gpcr["failed_criteria"] == []
    assert gpcr["requirement_summary"] == {
        "actual_closure_ready": True,
        "blocked_requirement_count": 0,
        "blocker_count": 0,
        "component_id": "gpcr_hard_decoy_actual_closure",
        "failed_criteria": [],
        "failed_criterion_count": 0,
        "passing_requirement_count": 5,
        "requirement_count": 5,
    }
    assert pocketmd["phase4_exit_gate_status"] == "ready"
    assert len(pocketmd["phase4_exit_gate_criteria"]) == 9
    assert pocketmd["real_refinement_case_count"] == 3
    assert pocketmd["actual_closure_ready"] is True
    assert pocketmd["failed_criteria"] == []
    assert pocketmd["requirement_summary"] == {
        "actual_closure_ready": True,
        "blocked_requirement_count": 0,
        "blocker_count": 0,
        "component_id": "pocketmd_lite_topk_actual_closure",
        "failed_criteria": [],
        "failed_criterion_count": 0,
        "passing_requirement_count": 9,
        "requirement_count": 9,
    }
    assert audit["component_requirement_summaries"] == [
        gpcr["requirement_summary"],
        pocketmd["requirement_summary"],
    ]
    assert (tmp_path / "gpcr_surface.json").exists()
    assert (tmp_path / "pocketmd_surface.json").exists()
