from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import numpy as np


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_foundation_optimization_artifact_produces_foundation_candidates(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {
                "member_count": 18,
                "group_count": 7,
                "member_type_counts": {
                    "beam": 8,
                    "column": 4,
                    "foundation": 3,
                    "pile": 2,
                    "mat": 1,
                },
            },
            "rows_head": [
                {
                    "member_id": "F01",
                    "member_type": "foundation",
                    "group_id": "G1",
                    "semantic_group": "foundation",
                    "section_signature": "MAT-900",
                },
                {
                    "member_id": "F02",
                    "member_type": "pile",
                    "group_id": "G2",
                    "semantic_group": "foundation",
                    "section_signature": "PILE-600",
                },
            ],
        },
    )
    changes = tmp_path / "design_optimization_cost_reduction_changes.json"
    _write_json(
        changes,
        {
            "changes": [
                {
                    "group_id": "G2",
                    "member_type": "pile",
                    "semantic_group": "foundation",
                    "action_name": "pile_down",
                }
            ]
        },
    )
    blocked = tmp_path / "design_optimization_cost_reduction_blocked_actions.json"
    _write_json(
        blocked,
        {
            "blocked_rows": [
                {
                    "group_id": "G1",
                    "member_type": "foundation",
                    "semantic_group": "foundation",
                    "action_name": "mat_down",
                    "block_reason": "ssi_gate",
                }
            ]
        },
    )
    out = tmp_path / "foundation_optimization_artifact.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_foundation_optimization_artifact.py",
            "--design-optimization-dataset",
            str(dataset),
            "--cost-reduction-changes",
            str(changes),
            "--cost-reduction-blocked-actions",
            str(blocked),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["summary"]["foundation_member_type_count"] == 6
    assert payload["summary"]["optimized_foundation_member_count"] == 1
    assert payload["summary"]["optimized_foundation_group_count"] == 1
    assert payload["summary"]["blocked_foundation_group_count"] == 1
    assert payload["artifacts"]["optimized_foundation_member_count"] == 1
    assert payload["artifacts"]["optimized_foundation_rows_head"][0]["group_id"] == "G2"
    assert payload["artifacts"]["foundation_candidate_rows_head"][0]["member_id"] == "F01"


def test_foundation_optimization_artifact_scans_full_dataset_npz_when_summary_is_empty(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 5, "group_count": 3, "member_type_counts": {"beam": 5}},
            "rows_head": [],
        },
    )
    np.savez(
        tmp_path / "design_optimization_dataset.npz",
        member_ids=np.asarray(["F01", "F02", "B01"], dtype=object),
        member_types=np.asarray(["foundation", "pile", "beam"], dtype=object),
        group_ids=np.asarray(["G1", "G2", "G3"], dtype=object),
        semantic_groups=np.asarray(["foundation", "foundation", ""], dtype=object),
        section_signatures=np.asarray(["MAT-900", "PILE-600", "B-01"], dtype=object),
    )
    changes = tmp_path / "design_optimization_cost_reduction_changes.json"
    _write_json(
        changes,
        {
            "changes": [
                {
                    "group_id": "G2",
                    "member_type": "pile",
                    "semantic_group": "foundation",
                    "action_name": "pile_down",
                }
            ]
        },
    )
    out = tmp_path / "foundation_optimization_artifact.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_foundation_optimization_artifact.py",
            "--design-optimization-dataset",
            str(dataset),
            "--design-optimization-npz",
            str(tmp_path / "design_optimization_dataset.npz"),
            "--cost-reduction-changes",
            str(changes),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["summary"]["candidate_scan_mode"] == "npz_full"
    assert payload["summary"]["foundation_member_type_count"] == 2
    assert payload["summary"]["optimized_foundation_group_count"] == 1
    assert payload["artifacts"]["optimized_foundation_member_count"] == 1


def test_foundation_optimization_artifact_marks_full_npz_scan_when_no_foundation_hits_exist(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "inputs": {"midas_model": str(tmp_path / "midas_model.json")},
            "summary": {"member_count": 3, "group_count": 2, "member_type_counts": {"beam": 3}},
            "rows_head": [
                {
                    "member_id": "B01",
                    "member_type": "beam",
                    "group_id": "G1",
                    "semantic_group": "",
                    "section_signature": "SB-01",
                }
            ],
        },
    )
    np.savez(
        tmp_path / "design_optimization_dataset.npz",
        member_ids=np.asarray(["B01", "B02", "C01"], dtype=object),
        member_types=np.asarray(["beam", "beam", "column"], dtype=object),
        group_ids=np.asarray(["G1", "G1", "G2"], dtype=object),
        semantic_groups=np.asarray(["", "", ""], dtype=object),
        section_signatures=np.asarray(["SB-01", "SB-01", "C-01"], dtype=object),
        section_names=np.asarray(["DBUSER", "DBUSER", "DBUSER"], dtype=object),
        exact_family_keys=np.asarray(["beam:a", "beam:a", "column:b"], dtype=object),
        unique_group_ids=np.asarray(["G1", "G2"], dtype=object),
        member_type_per_group=np.asarray(["beam", "column"], dtype=object),
        semantic_group_per_group=np.asarray(["", ""], dtype=object),
        section_signature_per_group=np.asarray(["SB-01", "C-01"], dtype=object),
        section_name_per_group=np.asarray(["DBUSER", "DBUSER"], dtype=object),
        group_family_key=np.asarray(["beam:G1", "column:G2"], dtype=object),
    )
    _write_json(tmp_path / "midas_model.json", {"model": {"sections": [{"name": "DBUSER"}], "metadata": {"groups": []}, "elements": []}})
    out = tmp_path / "foundation_optimization_artifact.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_foundation_optimization_artifact.py",
            "--design-optimization-dataset",
            str(dataset),
            "--design-optimization-npz",
            str(tmp_path / "design_optimization_dataset.npz"),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["summary"]["candidate_scan_mode"] == "npz_full_empty"
    assert payload["summary"]["foundation_member_type_count"] == 0
    assert payload["summary"]["npz_foundation_member_row_count"] == 0
    assert payload["summary"]["npz_foundation_group_row_count"] == 0
    assert payload["checks"]["full_dataset_scanned"] is True


def test_foundation_optimization_artifact_matches_promoted_foundation_scope_to_legacy_beam_group_id(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {
                "member_count": 3,
                "group_count": 2,
                "member_type_counts": {"foundation": 2, "beam": 1},
            },
            "rows_head": [],
        },
    )
    np.savez(
        tmp_path / "design_optimization_dataset.npz",
        member_ids=np.asarray(["5506", "5528", "B01"], dtype=object),
        member_types=np.asarray(["foundation", "foundation", "beam"], dtype=object),
        group_ids=np.asarray(
            [
                "S00:core:nogroup:foundation:SB1200X1200",
                "S00:core:nogroup:foundation:SB1200X1200",
                "S01:perimeter:nogroup:beam:SB600X400",
            ],
            dtype=object,
        ),
        semantic_groups=np.asarray(["", "", ""], dtype=object),
        section_signatures=np.asarray(["SB1200X1200", "SB1200X1200", "SB600X400"], dtype=object),
        section_names=np.asarray(["DBUSER", "DBUSER", "B-SEC-450"], dtype=object),
        exact_family_keys=np.asarray(["foundation:a", "foundation:a", "beam:b"], dtype=object),
        unique_group_ids=np.asarray(
            [
                "S00:core:nogroup:foundation:SB1200X1200",
                "S01:perimeter:nogroup:beam:SB600X400",
            ],
            dtype=object,
        ),
        member_type_per_group=np.asarray(["foundation", "beam"], dtype=object),
        semantic_group_per_group=np.asarray(["", ""], dtype=object),
        section_signature_per_group=np.asarray(["SB1200X1200", "SB600X400"], dtype=object),
        section_name_per_group=np.asarray(["DBUSER", "B-SEC-450"], dtype=object),
        group_family_key=np.asarray(["foundation:G1", "beam:G2"], dtype=object),
    )
    changes = tmp_path / "design_optimization_cost_reduction_changes.json"
    _write_json(
        changes,
        {
            "changes": [
                {
                    "group_id": "S00:core:nogroup:beam:SB1200X1200",
                    "member_type": "beam",
                    "semantic_group": "",
                    "action_name": "beam_section_down",
                }
            ]
        },
    )
    out = tmp_path / "foundation_optimization_artifact.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_foundation_optimization_artifact.py",
            "--design-optimization-dataset",
            str(dataset),
            "--design-optimization-npz",
            str(tmp_path / "design_optimization_dataset.npz"),
            "--cost-reduction-changes",
            str(changes),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["summary"]["candidate_scan_mode"] == "npz_full"
    assert payload["summary"]["foundation_member_type_count"] == 2
    assert payload["summary"]["optimized_foundation_group_count"] == 1
    assert payload["artifacts"]["optimized_foundation_rows_head"][0]["group_id"] == "S00:core:nogroup:beam:SB1200X1200"


def test_foundation_optimization_artifact_surfaces_upstream_foundation_labels_without_inventing_scope(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    midas_model = tmp_path / "midas_model.json"
    _write_json(
        midas_model,
        {
            "model": {
                "sections": [{"name": "PILECAP-01"}, {"name": "DBUSER"}],
                "elements": [{"name": "PILE_A", "type": "BEAM"}],
                "metadata": {"groups": [{"name": "FOUNDATION_ZONE"}]},
            }
        },
    )
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "inputs": {"midas_model": str(midas_model)},
            "summary": {"member_count": 2, "group_count": 1, "member_type_counts": {"beam": 2}},
            "rows_head": [],
        },
    )
    out = tmp_path / "foundation_optimization_artifact.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_foundation_optimization_artifact.py",
            "--design-optimization-dataset",
            str(dataset),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["summary"]["foundation_member_type_count"] == 0
    assert payload["summary"]["upstream_foundation_provenance_mode"] == "parsed_model_labels_present"
    assert payload["summary"]["upstream_foundation_label_count"] == 3
    assert payload["checks"]["upstream_foundation_label_present"] is True
    assert payload["artifacts"]["upstream_foundation_section_hits_head"] == ["PILECAP-01"]


def test_foundation_optimization_artifact_surfaces_upstream_section_signatures_and_group_plane_types(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    midas_model = tmp_path / "midas_model.json"
    _write_json(
        midas_model,
        {
            "model": {
                "sections": [{"name": "DBUSER", "raw_tokens": ["MAT-1500", "CC"]}],
                "elements": [{"name": "B01", "type": "BEAM"}],
                "metadata": {"groups": [{"name": "GENERAL_ZONE", "plane_type": "FOUNDATION"}]},
            }
        },
    )
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "inputs": {"midas_model": str(midas_model)},
            "summary": {"member_count": 1, "group_count": 1, "member_type_counts": {"beam": 1}},
            "rows_head": [],
        },
    )
    out = tmp_path / "foundation_optimization_artifact.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_foundation_optimization_artifact.py",
            "--design-optimization-dataset",
            str(dataset),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["summary"]["foundation_member_type_count"] == 0
    assert payload["summary"]["upstream_foundation_provenance_mode"] == "parsed_model_labels_present"
    assert payload["summary"]["upstream_foundation_label_count"] == 2
    assert payload["summary"]["upstream_section_signature_label_count"] == 1
    assert payload["summary"]["upstream_group_plane_type_label_count"] == 1
    assert payload["artifacts"]["upstream_foundation_section_signature_hits_head"] == ["MAT-1500"]
    assert payload["artifacts"]["upstream_foundation_group_plane_type_hits_head"] == ["FOUNDATION"]


def test_foundation_optimization_artifact_flags_parser_drop_when_raw_source_has_foundation_labels(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    midas_model = tmp_path / "midas_model.json"
    raw_source = tmp_path / "model.mgt"
    raw_source.write_text("*GROUP\nFOUNDATION_ZONE\n*SECTION\nPILECAP-01\n", encoding="utf-8")
    _write_json(
        midas_model,
        {
            "source": {"path": str(raw_source)},
            "model": {
                "sections": [{"name": "DBUSER"}],
                "elements": [{"name": "B01", "type": "BEAM"}],
                "metadata": {"groups": [{"name": "GENERAL"}]},
            },
        },
    )
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "inputs": {"midas_model": str(midas_model)},
            "summary": {"member_count": 2, "group_count": 1, "member_type_counts": {"beam": 2}},
            "rows_head": [],
        },
    )
    out = tmp_path / "foundation_optimization_artifact.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_foundation_optimization_artifact.py",
            "--design-optimization-dataset",
            str(dataset),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["reason"] == "raw MIDAS source carries foundation-like labels, but parsed model/dataset did not promote them"
    assert payload["summary"]["upstream_foundation_provenance_mode"] == "parser_drop_suspected"
    assert payload["summary"]["upstream_foundation_label_count"] == 0
    assert payload["summary"]["raw_source_foundation_label_count"] == 2
    assert payload["checks"]["parser_drop_suspected"] is True
    assert payload["artifacts"]["raw_source_foundation_hits_head"] == ["FOUNDATION_ZONE", "PILECAP-01"]


def test_foundation_optimization_artifact_reports_empty_full_scan_when_npz_has_no_foundation_scope(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 3, "group_count": 2, "member_type_counts": {"beam": 3}},
            "rows_head": [],
        },
    )
    np.savez(
        tmp_path / "design_optimization_dataset.npz",
        member_ids=np.asarray(["B01", "B02", "C01"], dtype=object),
        member_types=np.asarray(["beam", "beam", "column"], dtype=object),
        group_ids=np.asarray(["G1", "G1", "G2"], dtype=object),
        semantic_groups=np.asarray(["", "", ""], dtype=object),
        section_signatures=np.asarray(["B-01", "B-02", "C-01"], dtype=object),
    )
    out = tmp_path / "foundation_optimization_artifact.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_foundation_optimization_artifact.py",
            "--design-optimization-dataset",
            str(dataset),
            "--design-optimization-npz",
            str(tmp_path / "design_optimization_dataset.npz"),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_NO_FOUNDATION_SCOPE"
    assert payload["reason"] == "full design-optimization NPZ scan found no foundation members"
    assert payload["summary"]["candidate_scan_mode"] == "npz_full_empty"
    assert payload["summary"]["design_optimization_npz_present"] is True
    assert payload["checks"]["full_dataset_scanned"] is True


def test_foundation_optimization_artifact_normalizes_hyphenated_foundation_tokens(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 2, "group_count": 2, "member_type_counts": {"beam": 2}},
            "rows_head": [
                {
                    "member_id": "F01",
                    "member_type": "beam",
                    "group_id": "G1",
                    "semantic_group": "",
                    "section_signature": "PILE-CAP-600",
                },
                {
                    "member_id": "F02",
                    "member_type": "column",
                    "group_id": "G2",
                    "semantic_group": "caisson_support",
                    "section_signature": "GENERIC",
                },
            ],
        },
    )
    out = tmp_path / "foundation_optimization_artifact.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_foundation_optimization_artifact.py",
            "--design-optimization-dataset",
            str(dataset),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["summary"]["foundation_member_type_count"] == 2
    assert payload["artifacts"]["foundation_candidate_rows_head"][0]["member_id"] == "F01"
