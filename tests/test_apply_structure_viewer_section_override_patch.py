from __future__ import annotations

import json
import html
from pathlib import Path
import subprocess
import sys
from urllib.parse import parse_qs, urlparse
import numpy as np


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_apply_structure_viewer_section_override_patch_updates_resolved_section_ids(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    patch = tmp_path / "patch.json"
    out = tmp_path / "patched.json"
    _write_json(
        source,
        {
            "model": {
                "elements": [
                    {"id": "26705", "section_id": "340", "type": "BEAM"},
                    {"id": "26706", "section_id": "340", "type": "BEAM"},
                ],
                "sections": [
                    {"id": "340", "name": "SB800X3002.00"},
                    {"id": "512", "name": "SB800X4001.72"},
                ],
            }
        },
    )
    _write_json(
        patch,
        {
            "patch_mode": "working_section_override_patch",
            "patch_entries": [
                {
                    "member_id": "26705",
                    "representative_element_id": "26705",
                    "element_ids": ["26705"],
                    "target_section": "SB800X4001.72",
                    "applied_at": "2026-04-14T00:00:00+00:00",
                    "draft_note": "upgrade section",
                }
            ],
            "patch_member_count": 1,
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/apply_structure_viewer_section_override_patch.py",
            "--patch",
            str(patch),
            "--source",
            str(source),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = _load_json(out)
    element = payload["model"]["elements"][0]
    assert element["section_id"] == "512"
    assert element["viewer_section_override_resolution"] == "resolved_to_section_id"
    assert element["viewer_section_override_resolved_section_id"] == "512"
    assert payload["viewer_section_override_patch"]["resolved_entry_count"] == 1
    assert payload["viewer_section_override_patch"]["matched_element_count"] == 1


def test_apply_structure_viewer_section_override_patch_preserves_source_when_target_unresolved(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    patch = tmp_path / "patch.json"
    out = tmp_path / "patched.json"
    _write_json(
        source,
        {
            "elements": [
                {"member_id": "M1", "section_id": 7, "type": "BEAM"},
            ],
            "sections": [{"id": 7, "name": "SB-OLD"}],
        },
    )
    _write_json(
        patch,
        {
            "patch_mode": "working_section_override_patch",
            "patch_entries": [
                {
                    "member_id": "M1",
                    "element_ids": ["M1"],
                    "target_section": "SB-NEW",
                }
            ],
            "patch_member_count": 1,
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/apply_structure_viewer_section_override_patch.py",
            "--patch",
            str(patch),
            "--source",
            str(source),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = _load_json(out)
    element = payload["elements"][0]
    assert element["section_id"] == 7
    assert element["viewer_section_override_resolution"] == "unresolved_target_section"
    assert payload["viewer_section_override_patch"]["unresolved_entry_count"] == 1


def test_apply_structure_viewer_section_override_patch_honors_exact_target_section_id(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    patch = tmp_path / "patch.json"
    out = tmp_path / "patched.json"
    _write_json(
        source,
        {
            "model": {
                "elements": [
                    {"id": "26705", "section_id": "340", "type": "BEAM"},
                ],
                "sections": [
                    {"id": "340", "name": "SB800X3002.00"},
                    {"id": "512", "name": "SB800X4001.72"},
                ],
            }
        },
    )
    _write_json(
        patch,
        {
            "patch_mode": "working_section_override_patch",
            "patch_entries": [
                {
                    "member_id": "26705",
                    "representative_element_id": "26705",
                    "element_ids": ["26705"],
                    "target_section": "catalog-display-label-not-present-in-source-sections",
                    "target_section_id": "512",
                    "target_section_catalog_label": "SB800X4001.72",
                }
            ],
            "patch_member_count": 1,
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/apply_structure_viewer_section_override_patch.py",
            "--patch",
            str(patch),
            "--source",
            str(source),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = _load_json(out)
    element = payload["model"]["elements"][0]
    assert element["section_id"] == "512"
    assert element["viewer_section_override_resolution"] == "resolved_to_section_id"
    assert element["viewer_section_override_resolved_section_id"] == "512"
    assert element["viewer_section_override_resolved_section_name"] == "SB800X4001.72"


def test_apply_structure_viewer_section_override_patch_runs_raw_midas_writeback(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    patch = tmp_path / "patch.json"
    out = tmp_path / "patched.json"
    source_mgt = tmp_path / "source.mgt"
    dataset_npz = tmp_path / "dataset.npz"
    output_mgt = tmp_path / "patched.mgt"
    writeback_report = tmp_path / "writeback_report.json"
    diff_review_json = tmp_path / "patched.section_override_writeback_diff_review.json"
    diff_review_html = tmp_path / "patched.section_override_writeback_diff_review.html"
    compare_json = tmp_path / "patched.section_override_writeback_result_compare.json"
    compare_html = tmp_path / "patched.section_override_writeback_result_compare.html"

    _write_json(
        source,
        {
            "model": {
                "elements": [
                    {"id": "1", "member_id": "1", "section_id": 10, "type": "BEAM", "family": "beam", "node_ids": [1, 2], "material_id": 1},
                ],
                "sections": [
                    {"id": 10, "name": "B-SEC"},
                    {"id": 11, "name": "B-ALT"},
                ],
                "metadata": {
                    "design_sections": [
                        {"section_id": 10, "row_tokens": [["10", "DBUSER", "B-SEC"]], "raw_row_count": 1},
                        {"section_id": 11, "row_tokens": [["11", "DBUSER", "B-ALT"]], "raw_row_count": 1},
                    ]
                },
            }
        },
    )
    _write_json(
        patch,
        {
            "patch_mode": "working_section_override_patch",
            "patch_entries": [
                {
                    "member_id": "1",
                    "representative_element_id": "1",
                    "element_ids": ["1"],
                    "target_section": "B-ALT",
                    "target_section_id": 11,
                    "target_section_catalog_label": "B-ALT",
                }
            ],
            "patch_member_count": 1,
        },
    )
    source_mgt.write_text(
        """*NODE
1, 0.0, 0.0, 0.0
2, 0.0, 0.0, 3.0
*ELEMENT
1, BEAM, 1, 10, 1, 2, 0, 0
*MATERIAL
1, STEEL
*SECTION
10, B-SEC
11, B-ALT
*SECT-SCALE
10, 1, 1, 1, 1, 1, 1, 1, , 1
11, 1, 1, 1, 1, 1, 1, 1, , 1
""",
        encoding="utf-8",
    )
    np.savez_compressed(
        dataset_npz,
        member_ids=np.asarray(["1"], dtype="<U16"),
        group_ids=np.asarray(["G1"], dtype="<U16"),
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/apply_structure_viewer_section_override_patch.py",
            "--patch",
            str(patch),
            "--source",
            str(source),
            "--out",
            str(out),
            "--source-mgt",
            str(source_mgt),
            "--dataset-npz",
            str(dataset_npz),
            "--output-mgt",
            str(output_mgt),
            "--writeback-report-out",
            str(writeback_report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = _load_json(out)
    assert payload["viewer_section_override_patch"]["raw_midas_writeback"]["contract_pass"] is True
    assert payload["viewer_section_override_patch"]["raw_midas_writeback"]["diff_review_json_out"] == str(diff_review_json)
    assert payload["viewer_section_override_patch"]["raw_midas_writeback"]["diff_review_html_out"] == str(diff_review_html)
    assert payload["viewer_section_override_patch"]["raw_midas_writeback"]["result_compare_json_out"] == str(compare_json)
    assert payload["viewer_section_override_patch"]["raw_midas_writeback"]["result_compare_html_out"] == str(compare_html)
    assert payload["viewer_section_override_patch"]["raw_midas_writeback"]["diff_review_surface_mode"] == "standalone_html_and_json"
    assert "structural_optimization_viewer.html?" in payload["viewer_section_override_patch"]["raw_midas_writeback"]["results_explorer_diff_review_url"]
    assert output_mgt.exists()
    assert writeback_report.exists()
    assert diff_review_json.exists()
    assert diff_review_html.exists()
    assert compare_json.exists()
    assert compare_html.exists()
    output_text = output_mgt.read_text(encoding="utf-8")
    assert "1, BEAM, 1, 11, 1, 2, 0, 0" in output_text
    report_payload = _load_json(writeback_report)
    assert report_payload["contract_pass"] is True
    assert report_payload["summary"]["viewer_section_override_patch_present"] is True
    assert report_payload["summary"]["section_override_writeback_diff_review_json"] == str(diff_review_json)
    assert report_payload["summary"]["section_override_writeback_diff_review_html"] == str(diff_review_html)
    assert report_payload["summary"]["section_override_writeback_result_compare_json"] == str(compare_json)
    assert report_payload["summary"]["section_override_writeback_result_compare_html"] == str(compare_html)
    assert report_payload["summary"]["section_override_writeback_result_compare_member_count"] == 1
    assert report_payload["summary"]["section_override_writeback_result_compare_matched_member_count"] == 1
    assert "actual regenerated compare" in report_payload["summary"]["section_override_writeback_result_compare_summary_line"]
    assert "structural_optimization_viewer.html?" in report_payload["summary"]["section_override_writeback_results_explorer_diff_review_url"]
    assert report_payload["section_override_writeback_diff_review"]["html_out"] == str(diff_review_html)
    assert "structural_optimization_viewer.html?" in report_payload["section_override_writeback_diff_review"]["results_explorer_diff_review_url"]
    assert report_payload["section_override_writeback_result_compare"]["json_out"] == str(compare_json)
    assert report_payload["section_override_writeback_result_compare"]["html_out"] == str(compare_html)
    diff_payload = _load_json(diff_review_json)
    assert diff_payload["contract_pass"] is True
    assert diff_payload["review_surface_mode"] == "standalone_html_and_json"
    assert "structural_optimization_viewer.html?" in diff_payload["results_explorer_diff_review_url"]
    assert diff_payload["summary"]["changed_row_count"] == 1
    assert diff_payload["summary"]["changed_element_count"] == 1
    assert diff_payload["rows"][0]["member_id"] == "1"
    assert diff_payload["rows"][0]["previous_section_ids"] == ["10"]
    assert diff_payload["rows"][0]["next_section_ids"] == ["11"]
    assert "verify member section reassignment 10 -> 11" in diff_payload["rows"][0]["writeback_action_hint"]
    compare_url = diff_payload["rows"][0]["results_explorer_compare_url"]
    assert "structural_optimization_viewer.html?" in compare_url
    compare_query = parse_qs(urlparse(compare_url).query)
    assert compare_query["source"] == ["section_override_writeback_diff_review"]
    assert compare_query["focus"] == ["results"]
    assert compare_query["results_companion"] == ["compare"]
    assert compare_query["results_detail_block"] == ["compare"]
    assert compare_query["focus_member"] == ["1"]
    assert compare_query["member_id"] == ["1"]
    assert compare_query["member_set"] == ["1"]
    assert compare_query["writeback_member_id"] == ["1"]
    assert compare_query["writeback_resolution"] == ["resolved_to_section_id"]
    assert compare_query["writeback_target_section"] == ["B-ALT"]
    assert compare_query["writeback_previous_sections"] == ["10"]
    assert compare_query["writeback_next_sections"] == ["11"]
    assert compare_query["writeback_diff_json"][0].endswith("patched.section_override_writeback_diff_review.json")
    assert compare_query["writeback_diff_html"][0].endswith("patched.section_override_writeback_diff_review.html")
    assert compare_query["writeback_compare_json"][0].endswith("patched.section_override_writeback_result_compare.json")
    assert compare_query["writeback_compare_html"][0].endswith("patched.section_override_writeback_result_compare.html")
    assert compare_query["writeback_compare_status"] == ["actual regenerated artifact compare | window_rows=1"]
    assert compare_query["writeback_compare_row_count"] == ["1"]
    assert compare_query["writeback_compare_kind_summary"] == ["replace=1"]
    assert compare_query["writeback_compare_summary"][0].startswith("actual regenerated artifact compare")
    assert compare_query["writeback_compare_row_ids"] == ["mgt-diff-row-0000"]
    patched_receipt_row = payload["viewer_section_override_patch"]["rows"][0]
    assert patched_receipt_row["writeback_action_hint"] == diff_payload["rows"][0]["writeback_action_hint"]
    assert patched_receipt_row["results_explorer_compare_url"] == compare_url
    compare_payload = _load_json(compare_json)
    assert compare_payload["summary"]["member_count"] == 1
    assert compare_payload["summary"]["matched_member_count"] == 1
    assert compare_payload["summary"]["actual_window_match_count"] == 1
    assert compare_payload["rows"][0]["member_id"] == "1"
    assert compare_payload["rows"][0]["actual_regenerated_compare_status"] == "matched_regenerated_artifact_diff_window"
    assert compare_payload["rows"][0]["actual_regenerated_compare_kind_summary"] == "replace=1"
    assert compare_payload["rows"][0]["actual_regenerated_compare_row_ids"] == ["mgt-diff-row-0000"]
    assert compare_payload["rows"][0]["results_explorer_compare_url"] == compare_url
    compare_html_text = compare_html.read_text(encoding="utf-8")
    assert "Section Override Writeback Result Compare" in compare_html_text
    assert "Results explorer diff review" in compare_html_text
    assert "Open compare console" in compare_html_text
    assert html.escape(compare_url, quote=True) in compare_html_text
    diff_html = diff_review_html.read_text(encoding="utf-8")
    assert "Section Override Writeback Diff Review" in diff_html
    assert "Results explorer diff review" in diff_html
    assert "Open compare console" in diff_html
    assert html.escape(compare_url, quote=True) in diff_html
    assert "patched.mgt" in diff_html
