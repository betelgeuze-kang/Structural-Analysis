from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse


SCRIPT = Path("implementation/phase1/export_midas_kds_row_provenance_table.py")


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_export_midas_kds_row_provenance_table_writes_json_csv_and_report(tmp_path: Path) -> None:
    model_json = tmp_path / "model.json"
    kds_report = tmp_path / "code_check_report.json"
    out_json = tmp_path / "row_provenance.json"
    out_csv = tmp_path / "row_provenance.csv"
    out_report = tmp_path / "row_provenance_report.json"

    _write(
        model_json,
        {
            "model": {
                "metadata": {
                    "kds_geometry_bridge": {
                        "contract_version": "0.3.0",
                        "summary": {
                            "review_row_count": 1,
                            "review_id_count": 1,
                            "mapped_review_id_count": 1,
                            "exact_mapped_review_id_count": 1,
                            "heuristic_mapped_review_id_count": 0,
                            "mapped_row_provenance_count": 1,
                            "exact_mapped_row_provenance_count": 1,
                            "heuristic_mapped_row_provenance_count": 0,
                            "confidence_counts": {"exact_id": 1},
                        },
                        "bridge_rows": [
                            {
                                "review_member_id": "C-TST-003",
                                "review_case_id": "C-TST-003",
                                "baseline_focus_member_id": "502101",
                                "match_strategy": "manual_embedding",
                                "match_confidence": "external_map",
                                "row_provenance_row_count": 1,
                                "row_provenance_combination_count": 1,
                                "row_provenance_clause_count": 1,
                                "row_provenance_component_count": 1,
                                "row_provenance_summary_label": "rows=1 | combos=1 | clauses=1 | top=KDS_ULS_2 | bending_moment_y_kNm | KDS-MOMENT-Y-001 | D/C=1.216",
                                "row_provenance_top_row_label": "KDS_ULS_2 | bending_moment_y_kNm | KDS-MOMENT-Y-001 | D/C=1.216",
                                "note": "explicit bridge to baseline member 502101",
                                "review_keys_label": "C-TST-003",
                                "member_inventory_count": 1,
                                "member_inventory_member_type_label": "column",
                                "member_inventory_summary_label": "review=C-TST-003 | case=C-TST-003 | baseline=502101 | member_types=column",
                                "clause_provenance_summary_label": "rows=1 | members=1 | rules=1 | hazards=1",
                            }
                        ],
                    }
                },
                "load_combinations_raw": [
                    "NAME=ULS1, GEN, STRENGTH, 0, 0, 1.2(D) + 1.6(L), 0, 0, 0",
                    "ST, DEAD, 1.2, ST, LIVE, 1.6",
                ],
            }
        },
    )
    _write(
        kds_report,
        {
            "combination_provenance_rows": [
                {
                    "kds_name": "KDS_ULS_2",
                    "matched_runtime_name": "ULS1",
                    "matched_runtime_factor_map": {"D": 1.2, "L": 1.6},
                    "match_score": 0.8333333333333333,
                }
            ],
            "member_check_rows": [
                {
                    "combination": "KDS_ULS_2",
                    "member_id": "C-TST-003",
                    "member_type": "column",
                    "component": "bending_moment_y_kNm",
                    "hazard_type": "gravity",
                    "rule_family": "moment",
                    "topology_type": "frame",
                    "demand": 3162.159,
                    "capacity": 2600.0,
                    "dcr": 1.2162149999999998,
                    "clause": "KDS-MOMENT-Y-001",
                }
            ],
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--model-json",
            str(model_json),
            "--kds-report",
            str(kds_report),
            "--out-json",
            str(out_json),
            "--out-csv",
            str(out_csv),
            "--out-report",
            str(out_report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    export_payload = json.loads(out_json.read_text(encoding="utf-8"))
    report_payload = json.loads(out_report.read_text(encoding="utf-8"))
    csv_text = out_csv.read_text(encoding="utf-8")

    assert export_payload["summary"]["combination_count"] == 1
    assert export_payload["summary"]["row_count"] == 1
    assert export_payload["summary"]["exact_row_count"] == 1
    assert export_payload["summary"]["clause_filter_count"] == 1
    assert export_payload["summary"]["member_filter_count"] == 1
    assert export_payload["summary"]["hazard_filter_count"] == 1
    assert export_payload["summary"]["rule_family_filter_count"] == 1
    assert export_payload["preview_rows"][0]["member_id"] == "C-TST-003"
    assert export_payload["clause_filter_rows"][0]["clause_label"] == "KDS-MOMENT-Y-001"
    assert export_payload["clause_filter_rows"][0]["viewer_row_url"]
    assert export_payload["member_filter_rows"][0]["member_id"] == "C-TST-003"
    assert export_payload["member_filter_rows"][0]["viewer_row_url"]
    assert export_payload["hazard_filter_rows"][0]["hazard_type"] == "gravity"
    assert export_payload["hazard_filter_rows"][0]["viewer_row_url"]
    assert export_payload["rule_family_filter_rows"][0]["rule_family"] == "moment"
    assert export_payload["rule_family_filter_rows"][0]["viewer_row_url"]
    assert export_payload["hazard_filter_subsets"][0]["subset_key"] == "hazard:gravity"
    assert export_payload["hazard_filter_subsets"][0]["viewer_row_url"]
    assert export_payload["hazard_filter_subsets"][0]["row_refs"][0]["combination_name"] == "ULS1"
    assert export_payload["rule_family_filter_subsets"][0]["subset_key"] == "rule_family:moment"
    assert export_payload["rule_family_filter_subsets"][0]["viewer_row_url"]
    assert export_payload["reviewer_appendix"]["schema_version"] == "filter_subset_v1"
    assert export_payload["reviewer_appendix"]["reverse_jump_contract_version"] == "viewer_subset_reverse_jump_v11"
    assert export_payload["artifacts"]["subset_root"].endswith("midas_kds_row_provenance_subsets")
    subset_index = export_payload["artifacts"]["subset_index"]
    assert subset_index["contract_version"] == "viewer_subset_reverse_jump_v11"
    assert subset_index["combination_count"] == 1
    assert subset_index["combination_rows"]["ULS1"]["all_csv"].endswith("midas_kds_row_provenance_subsets/uls1/all.csv")
    assert subset_index["combination_rows"]["ULS1"]["viewer_focus_member_id"] == "502101"
    assert subset_index["combination_rows"]["ULS1"]["viewer_row_url"]
    assert subset_index["combination_rows"]["ULS1"]["hazard"]["gravity"]["csv"].endswith(
        "midas_kds_row_provenance_subsets/uls1/hazard/gravity.csv"
    )
    assert subset_index["combination_rows"]["ULS1"]["hazard"]["gravity"]["viewer_row_url"]
    assert subset_index["combination_rows"]["ULS1"]["rule_family"]["moment"]["csv"].endswith(
        "midas_kds_row_provenance_subsets/uls1/rule_family/moment.csv"
    )
    assert subset_index["combination_rows"]["ULS1"]["rule_family"]["moment"]["viewer_row_url"]
    assert subset_index["combination_rows"]["ULS1"]["hazard_rule_family"]["gravity::moment"]["csv"].endswith(
        "midas_kds_row_provenance_subsets/uls1/hazard_rule/gravity__moment.csv"
    )
    assert subset_index["combination_rows"]["ULS1"]["hazard_rule_family"]["gravity::moment"]["viewer_row_url"]
    assert export_payload["rows"][0]["combination_name"] == "ULS1"
    assert export_payload["rows"][0]["baseline_focus_member_id"] == "502101"
    assert export_payload["rows"][0]["viewer_focus_member_id"] == "502101"
    assert export_payload["rows"][0]["viewer_reading_mode"] == "midas"
    assert export_payload["rows"][0]["viewer_focus_target"] == "interactive3d"
    assert export_payload["rows"][0]["viewer_results_card"]
    assert export_payload["rows"][0]["viewer_results_companion"] == "interactive"
    assert export_payload["rows"][0]["viewer_results_companion_item_index"] == 0
    assert export_payload["rows"][0]["viewer_codecheck_surface"] == "drilldown"
    assert export_payload["rows"][0]["viewer_codecheck_companion"] == "detail"
    assert export_payload["rows"][0]["viewer_codecheck_companion_item_index"] == 0
    assert export_payload["rows"][0]["reverse_sync_contract_version"] == "viewer_subset_reverse_jump_v11"
    assert export_payload["rows"][0]["viewer_results_companion_focus_key"].startswith("chart-marker:")
    assert export_payload["rows"][0]["viewer_results_companion_selection_key"] == "results-companion:interactive"
    assert export_payload["rows"][0]["viewer_results_detail_focus_key"].startswith("chart-marker:")
    assert export_payload["rows"][0]["viewer_results_detail_selection_key"] == "results-detail:chart"
    assert export_payload["rows"][0]["viewer_codecheck_companion_focus_key"] == "row-provenance:jump-row"
    assert export_payload["rows"][0]["viewer_codecheck_companion_selection_key"] == "row:ULS1::0::C-TST-003::C-TST-003"
    assert export_payload["rows"][0]["viewer_codecheck_detail_focus_key"] == "row-provenance:jump-row"
    assert export_payload["rows"][0]["viewer_codecheck_detail_selection_key"] == "row:ULS1::0::C-TST-003::C-TST-003"
    assert export_payload["rows"][0]["viewer_codecheck_appendix_focus_key"] == "subset:current-slice"
    assert export_payload["rows"][0]["viewer_codecheck_appendix_selection_key"] == "subset:combination:ULS1"
    assert export_payload["rows"][0]["viewer_results_sample_index"] == 0
    assert export_payload["rows"][0]["viewer_results_detail_item_index"] == 0
    assert export_payload["rows"][0]["viewer_codecheck_filtered_row_index"] == 0
    assert export_payload["rows"][0]["viewer_codecheck_clause_index"] == 0
    assert export_payload["rows"][0]["viewer_codecheck_hazard_index"] == 0
    assert export_payload["rows"][0]["viewer_codecheck_rule_family_index"] == 0
    assert export_payload["rows"][0]["viewer_codecheck_detail_item_index"] == 0
    assert export_payload["rows"][0]["viewer_codecheck_appendix_item_index"] == 0
    assert export_payload["rows"][0]["viewer_results_detail_block"] == "chart"
    assert export_payload["rows"][0]["viewer_codecheck_detail_block"] == "row-provenance"
    assert export_payload["rows"][0]["viewer_codecheck_appendix_block"] == "subset-summary"
    assert export_payload["rows"][0]["viewer_interactive_detail_more"] == "open"
    assert export_payload["rows"][0]["viewer_overlay_detail_more"] == "open"
    assert export_payload["rows"][0]["viewer_baseline_secondary"] == "elevation"
    assert export_payload["rows"][0]["viewer_row_url"]
    assert export_payload["rows"][0]["viewer_slice_url"]
    row_url = urlparse(export_payload["rows"][0]["viewer_row_url"])
    slice_url = urlparse(export_payload["rows"][0]["viewer_slice_url"])
    row_qs = parse_qs(row_url.query)
    slice_qs = parse_qs(slice_url.query)
    assert "structural_optimization_viewer.html" in row_url.path
    assert row_qs["source"] == ["row_provenance_csv"]
    assert row_qs["combination"] == ["ULS1"]
    assert row_qs["row"] == ["0"]
    assert row_qs["clause"] == ["KDS-MOMENT-Y-001"]
    assert row_qs["hazard"] == ["gravity"]
    assert row_qs["rule_family"] == ["moment"]
    assert row_qs["focus_member"] == ["502101"]
    assert row_qs["member_id"] == ["C-TST-003"]
    assert row_qs["case_id"] == ["C-TST-003"]
    assert row_qs["baseline_focus_member_id"] == ["502101"]
    assert row_qs["view"] == ["midas"]
    assert row_qs["focus"] == ["interactive3d"]
    assert row_qs["results_card"] == [export_payload["rows"][0]["viewer_results_card"]]
    assert row_qs["results_series"] == [str(export_payload["rows"][0]["viewer_results_series_index"])]
    assert row_qs["results_sample"] == ["0"]
    assert row_qs["results_detail_item_index"] == ["0"]
    assert row_qs["results_companion_item_index"] == ["0"]
    assert row_qs["results_companion_selection_key"] == ["results-companion:interactive"]
    assert row_qs["results_detail_selection_key"] == ["results-detail:chart"]
    assert row_qs["codecheck_filtered_row"] == ["0"]
    assert row_qs["codecheck_clause_index"] == ["0"]
    assert row_qs["codecheck_hazard_index"] == ["0"]
    assert row_qs["codecheck_rule_family_index"] == ["0"]
    assert row_qs["results_companion"] == ["interactive"]
    assert row_qs["results_detail_block"] == ["chart"]
    assert row_qs["codecheck_surface"] == ["drilldown"]
    assert row_qs["codecheck_companion"] == ["detail"]
    assert row_qs["codecheck_companion_item_index"] == ["0"]
    assert row_qs["codecheck_companion_selection_key"] == ["row:ULS1::0::C-TST-003::C-TST-003"]
    assert row_qs["codecheck_detail_block"] == ["row-provenance"]
    assert row_qs["codecheck_appendix_block"] == ["subset-summary"]
    assert row_qs["codecheck_detail_item_index"] == ["0"]
    assert row_qs["codecheck_appendix_item_index"] == ["0"]
    assert row_qs["codecheck_detail_selection_key"] == ["row:ULS1::0::C-TST-003::C-TST-003"]
    assert row_qs["codecheck_appendix_selection_key"] == ["subset:combination:ULS1"]
    assert row_qs["interactive_detail_more"] == ["open"]
    assert row_qs["overlay_detail_more"] == ["open"]
    assert row_qs["baseline_secondary"] == ["elevation"]
    assert "structural_optimization_viewer.html" in slice_url.path
    assert slice_qs["source"] == ["row_provenance_csv"]
    assert slice_qs["combination"] == ["ULS1"]
    assert slice_qs["row_ref"] == ["ULS1::0::C-TST-003::C-TST-003"]
    assert slice_qs["focus_member"] == ["502101"]
    assert slice_qs["member_id"] == ["C-TST-003"]
    assert slice_qs["case_id"] == ["C-TST-003"]
    assert slice_qs["baseline_focus_member_id"] == ["502101"]
    assert slice_qs["view"] == ["midas"]
    assert slice_qs["focus"] == ["interactive3d"]
    assert slice_qs["results_card"] == [export_payload["rows"][0]["viewer_results_card"]]
    assert slice_qs["results_series"] == [str(export_payload["rows"][0]["viewer_results_series_index"])]
    assert slice_qs["results_sample"] == ["0"]
    assert slice_qs["results_detail_item_index"] == ["0"]
    assert slice_qs["results_companion_item_index"] == ["0"]
    assert slice_qs["codecheck_filtered_row"] == ["0"]
    assert slice_qs["codecheck_clause_index"] == ["0"]
    assert slice_qs["codecheck_hazard_index"] == ["0"]
    assert slice_qs["codecheck_rule_family_index"] == ["0"]
    assert slice_qs["results_companion"] == ["checks"]
    assert slice_qs["results_detail_block"] == ["chart"]
    assert slice_qs["codecheck_surface"] == ["drilldown"]
    assert slice_qs["codecheck_companion"] == ["reviewer-appendix"]
    assert slice_qs["codecheck_companion_item_index"] == ["0"]
    assert slice_qs["codecheck_detail_block"] == ["row-provenance"]
    assert slice_qs["codecheck_appendix_block"] == ["subset-summary"]
    assert slice_qs["codecheck_detail_item_index"] == ["0"]
    assert slice_qs["codecheck_appendix_item_index"] == ["0"]
    assert slice_qs["interactive_detail_more"] == ["open"]
    assert slice_qs["overlay_detail_more"] == ["open"]
    assert slice_qs["baseline_secondary"] == ["elevation"]
    assert "clause" not in slice_qs
    assert "hazard" not in slice_qs
    assert "rule_family" not in slice_qs
    assert export_payload["rows"][0]["clause_provenance_summary_label"] == "rows=1 | members=1 | rules=1 | hazards=1"
    assert "combination_name,row_index,viewer_row_ref,member_id" in csv_text
    assert "ULS1::0::C-TST-003::C-TST-003" in csv_text
    assert ",C-TST-003,C-TST-003,column,bending_moment_y_kNm," in csv_text
    assert Path(subset_index["combination_rows"]["ULS1"]["all_csv"]).exists()
    assert Path(subset_index["combination_rows"]["ULS1"]["hazard"]["gravity"]["csv"]).exists()
    assert Path(subset_index["combination_rows"]["ULS1"]["rule_family"]["moment"]["csv"]).exists()
    subset_contract = json.loads(
        Path(subset_index["combination_rows"]["ULS1"]["all_metadata_json"]).read_text(encoding="utf-8")
    )
    subset_contract_qs = parse_qs(urlparse(subset_contract["viewer_slice_url"]).query)
    subset_row_qs = parse_qs(urlparse(subset_contract["viewer_row_url"]).query)
    assert subset_contract["viewer_focus_member_id"] == "502101"
    assert subset_contract["viewer_reading_mode"] == "midas"
    assert subset_contract["viewer_focus_target"] == "interactive3d"
    assert subset_contract["viewer_results_card"] == export_payload["rows"][0]["viewer_results_card"]
    assert subset_contract["viewer_results_companion"] == "checks"
    assert subset_contract["viewer_results_companion_item_index"] == 0
    assert subset_contract["viewer_codecheck_surface"] == "drilldown"
    assert subset_contract["viewer_codecheck_companion"] == "reviewer-appendix"
    assert subset_contract["viewer_codecheck_companion_item_index"] == 0
    assert subset_contract["reverse_sync_contract_version"] == "viewer_subset_reverse_jump_v11"
    assert subset_contract["viewer_results_sample_index"] == 0
    assert subset_contract["viewer_results_detail_item_index"] == 0
    assert subset_contract["viewer_codecheck_filtered_row_index"] == 0
    assert subset_contract["viewer_codecheck_clause_index"] == 0
    assert subset_contract["viewer_codecheck_hazard_index"] == 0
    assert subset_contract["viewer_codecheck_rule_family_index"] == 0
    assert subset_contract["viewer_results_detail_block"] == "chart"
    assert subset_contract["viewer_codecheck_detail_block"] == "row-provenance"
    assert subset_contract["viewer_codecheck_appendix_block"] == "subset-summary"
    assert subset_contract["viewer_codecheck_detail_item_index"] == 0
    assert subset_contract["viewer_codecheck_appendix_item_index"] == 0
    assert subset_contract["viewer_results_companion_selection_key"] == "results-companion:checks"
    assert subset_contract["viewer_results_detail_selection_key"] == "results-detail:chart"
    assert subset_contract["viewer_codecheck_companion_selection_key"] == "row:ULS1::0::C-TST-003::C-TST-003"
    assert subset_contract["viewer_codecheck_detail_selection_key"] == "row:ULS1::0::C-TST-003::C-TST-003"
    assert subset_contract["viewer_codecheck_appendix_selection_key"] == "subset:combination:ULS1"
    assert subset_contract["viewer_interactive_detail_more"] == "open"
    assert subset_contract["viewer_overlay_detail_more"] == "open"
    assert subset_contract["viewer_baseline_secondary"] == "elevation"
    assert subset_contract_qs["source"] == ["row_provenance_subset_csv"]
    assert subset_contract_qs["subset_key"] == ["combination:ULS1"]
    assert subset_contract_qs["row_ref"] == ["ULS1::0::C-TST-003::C-TST-003"]
    assert subset_contract_qs["focus_member"] == ["502101"]
    assert subset_contract_qs["view"] == ["midas"]
    assert subset_contract_qs["focus"] == ["interactive3d"]
    assert subset_contract_qs["results_card"] == [export_payload["rows"][0]["viewer_results_card"]]
    assert subset_contract_qs["results_series"] == [str(export_payload["rows"][0]["viewer_results_series_index"])]
    assert subset_contract_qs["results_sample"] == ["0"]
    assert subset_contract_qs["results_detail_item_index"] == ["0"]
    assert subset_contract_qs["results_companion_item_index"] == ["0"]
    assert subset_contract_qs["results_companion_selection_key"] == ["results-companion:checks"]
    assert subset_contract_qs["results_detail_selection_key"] == ["results-detail:chart"]
    assert subset_contract_qs["codecheck_filtered_row"] == ["0"]
    assert subset_contract_qs["codecheck_clause_index"] == ["0"]
    assert subset_contract_qs["codecheck_hazard_index"] == ["0"]
    assert subset_contract_qs["codecheck_rule_family_index"] == ["0"]
    assert subset_contract_qs["results_companion"] == ["checks"]
    assert subset_contract_qs["results_detail_block"] == ["chart"]
    assert subset_contract_qs["codecheck_surface"] == ["drilldown"]
    assert subset_contract_qs["codecheck_companion"] == ["reviewer-appendix"]
    assert subset_contract_qs["codecheck_companion_item_index"] == ["0"]
    assert subset_contract_qs["codecheck_companion_selection_key"] == ["row:ULS1::0::C-TST-003::C-TST-003"]
    assert subset_contract_qs["codecheck_detail_block"] == ["row-provenance"]
    assert subset_contract_qs["codecheck_appendix_block"] == ["subset-summary"]
    assert subset_contract_qs["codecheck_detail_item_index"] == ["0"]
    assert subset_contract_qs["codecheck_appendix_item_index"] == ["0"]
    assert subset_contract_qs["codecheck_detail_selection_key"] == ["row:ULS1::0::C-TST-003::C-TST-003"]
    assert subset_contract_qs["codecheck_appendix_selection_key"] == ["subset:combination:ULS1"]
    assert subset_contract_qs["interactive_detail_more"] == ["open"]
    assert subset_contract_qs["overlay_detail_more"] == ["open"]
    assert subset_contract_qs["baseline_secondary"] == ["elevation"]
    assert subset_row_qs["source"] == ["row_provenance_subset_csv"]
    assert subset_row_qs["row"] == ["0"]
    assert subset_row_qs["view"] == ["midas"]
    assert subset_row_qs["focus"] == ["interactive3d"]
    assert subset_row_qs["results_card"] == [export_payload["rows"][0]["viewer_results_card"]]
    assert subset_row_qs["results_series"] == [str(export_payload["rows"][0]["viewer_results_series_index"])]
    assert subset_row_qs["results_sample"] == ["0"]
    assert subset_row_qs["results_detail_item_index"] == ["0"]
    assert subset_row_qs["results_companion_item_index"] == ["0"]
    assert subset_row_qs["results_companion_selection_key"] == ["results-companion:interactive"]
    assert subset_row_qs["results_detail_selection_key"] == ["results-detail:chart"]
    assert subset_row_qs["codecheck_filtered_row"] == ["0"]
    assert subset_row_qs["codecheck_clause_index"] == ["0"]
    assert subset_row_qs["codecheck_hazard_index"] == ["0"]
    assert subset_row_qs["codecheck_rule_family_index"] == ["0"]
    assert subset_row_qs["results_companion"] == ["interactive"]
    assert subset_row_qs["results_detail_block"] == ["chart"]
    assert subset_row_qs["codecheck_surface"] == ["drilldown"]
    assert subset_row_qs["codecheck_companion"] == ["detail"]
    assert subset_row_qs["codecheck_companion_item_index"] == ["0"]
    assert subset_row_qs["codecheck_companion_selection_key"] == ["row:ULS1::0::C-TST-003::C-TST-003"]
    assert subset_row_qs["codecheck_detail_block"] == ["row-provenance"]
    assert subset_row_qs["codecheck_appendix_block"] == ["subset-summary"]
    assert subset_row_qs["codecheck_detail_item_index"] == ["0"]
    assert subset_row_qs["codecheck_appendix_item_index"] == ["0"]
    assert subset_row_qs["codecheck_detail_selection_key"] == ["row:ULS1::0::C-TST-003::C-TST-003"]
    assert subset_row_qs["codecheck_appendix_selection_key"] == ["subset:combination:ULS1"]
    assert subset_row_qs["interactive_detail_more"] == ["open"]
    assert subset_row_qs["overlay_detail_more"] == ["open"]
    assert subset_row_qs["baseline_secondary"] == ["elevation"]
    assert subset_row_qs["subset_csv"][0].endswith("midas_kds_row_provenance_subsets/uls1/all.csv")
    assert subset_row_qs["subset_manifest"][0].endswith("midas_kds_row_provenance_subsets/uls1/all.json")
    assert subset_row_qs["results_detail_block"] == ["chart"]
    assert subset_row_qs["codecheck_appendix_block"] == ["subset-summary"]
    assert report_payload["contract_pass"] is True
    assert report_payload["summary"]["row_count"] == 1
    assert report_payload["summary"]["clause_filter_count"] == 1
    assert report_payload["summary"]["member_filter_count"] == 1
    assert report_payload["summary"]["hazard_filter_count"] == 1
    assert report_payload["summary"]["rule_family_filter_count"] == 1
    assert report_payload["summary"]["hazard_subset_count"] == 1
    assert report_payload["summary"]["rule_family_subset_count"] == 1
    assert report_payload["artifacts"]["combination_subset_count"] == 1
    assert report_payload["hazard_filter_subsets"][0]["subset_slug"] == "hazard_gravity"
    assert report_payload["rule_family_filter_subsets"][0]["subset_slug"] == "rule_family_moment"
    assert report_payload["preview_rows"][0]["baseline_focus_member_id"] == "502101"
    assert report_payload["summary_line"].startswith("MIDAS KDS row provenance export: PASS")
    assert "clause_filters=1" in report_payload["summary_line"]
    assert "member_filters=1" in report_payload["summary_line"]
    assert "reverse_jump=viewer_subset_reverse_jump_v11" in report_payload["summary_line"]
