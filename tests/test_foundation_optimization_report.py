from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _foundation_fixture_path(name: str) -> Path:
    return Path(__file__).resolve().parent / "fixtures" / "foundation_realish" / name


def test_foundation_optimization_report_flags_missing_artifact_when_foundation_scope_exists(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {
                "member_count": 19,
                "group_count": 7,
                "member_type_counts": {
                    "beam": 8,
                    "column": 5,
                    "foundation": 4,
                    "pile": 2,
                },
            },
        },
    )
    out = tmp_path / "foundation_optimization_report.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_foundation_optimization_report.py",
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
    assert payload["reason_code"] == "ERR_NO_FOUNDATION_OPTIMIZATION_ARTIFACT"
    assert payload["summary"]["optimization_mode"] == "foundation_members_present_but_no_active_optimization"
    assert payload["summary"]["foundation_member_type_count"] == 6
    assert payload["checks"]["foundation_members_present"] is True
    assert payload["checks"]["foundation_artifact_present"] is False


def test_foundation_optimization_report_passes_with_foundation_artifact(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {
                "member_count": 24,
                "group_count": 9,
                "member_type_counts": {
                    "beam": 8,
                    "mat": 3,
                    "pile": 4,
                    "pilecap": 2,
                },
            },
        },
    )
    artifact = tmp_path / "foundation_optimization_artifact.json"
    _write_json(
        artifact,
        {
            "contract_pass": True,
            "summary": {"optimized_foundation_member_count": 9},
        },
    )
    out = tmp_path / "foundation_optimization_report.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_foundation_optimization_report.py",
            "--design-optimization-dataset",
            str(dataset),
            "--foundation-optimization-artifact",
            str(artifact),
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
    assert payload["summary"]["optimization_mode"] == "active_foundation_member_optimization"
    assert payload["summary"]["foundation_member_type_count"] == 9
    assert payload["summary"]["foundation_artifact_present"] is True
    assert payload["summary"]["foundation_artifact_contract_pass"] is True
    assert payload["summary"]["foundation_artifact_optimized_count"] == 9


def test_foundation_optimization_report_uses_artifact_scope_when_dataset_summary_is_stale(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 24, "group_count": 9, "member_type_counts": {"beam": 8}},
        },
    )
    artifact = tmp_path / "foundation_optimization_artifact.json"
    _write_json(
        artifact,
        {
            "contract_pass": True,
            "summary": {
                "foundation_member_type_count": 5,
                "optimized_foundation_member_count": 5,
                "foundation_member_type_counts": {"foundation": 3, "pile": 2},
            },
        },
    )
    out = tmp_path / "foundation_optimization_report.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_foundation_optimization_report.py",
            "--design-optimization-dataset",
            str(dataset),
            "--foundation-optimization-artifact",
            str(artifact),
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
    assert payload["summary"]["foundation_member_type_count"] == 5
    assert payload["summary"]["foundation_scope_source"] == "artifact_scan"


def test_foundation_optimization_report_discovers_sibling_artifact_when_flag_is_omitted(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 24, "group_count": 9, "member_type_counts": {"foundation": 3}},
        },
    )
    artifact = tmp_path / "foundation_optimization_artifact.json"
    _write_json(
        artifact,
        {
            "contract_pass": True,
            "summary": {
                "foundation_member_type_count": 3,
                "optimized_foundation_member_count": 2,
                "optimized_foundation_group_count": 2,
            },
        },
    )
    out = tmp_path / "foundation_optimization_report.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_foundation_optimization_report.py",
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
    assert payload["reason_code"] == "PASS"
    assert payload["inputs"]["foundation_optimization_artifact"] == str(artifact)
    assert payload["summary"]["foundation_artifact_present"] is True
    assert payload["summary"]["foundation_artifact_optimized_group_count"] == 2


def test_foundation_optimization_report_accepts_hard_gate_candidate_evidence(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 24, "group_count": 9, "member_type_counts": {"foundation": 3}},
        },
    )
    artifact = tmp_path / "foundation_optimization_artifact.json"
    _write_json(
        artifact,
        {
            "contract_pass": True,
            "summary": {
                "foundation_member_type_count": 3,
                "optimized_foundation_member_count": 0,
                "optimized_foundation_group_count": 0,
                "accepted_foundation_candidate_group_count": 2,
            },
        },
    )
    out = tmp_path / "foundation_optimization_report.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_foundation_optimization_report.py",
            "--design-optimization-dataset",
            str(dataset),
            "--foundation-optimization-artifact",
            str(artifact),
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
    assert payload["summary"]["optimization_mode"] == "foundation_candidate_optimization_evidence"
    assert payload["summary"]["foundation_artifact_optimized_group_count"] == 0
    assert payload["summary"]["accepted_foundation_candidate_group_count"] == 2
    assert payload["summary"]["foundation_evidence_group_count"] == 2


def test_foundation_optimization_report_flags_upstream_foundation_scope_not_promoted(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 24, "group_count": 9, "member_type_counts": {"beam": 8}},
        },
    )
    artifact = tmp_path / "foundation_optimization_artifact.json"
    _write_json(
        artifact,
        {
            "contract_pass": False,
            "summary": {
                "foundation_member_type_count": 0,
                "optimized_foundation_member_count": 0,
                "candidate_scan_mode": "npz_full_empty",
                "upstream_foundation_label_count": 2,
                "upstream_foundation_provenance_mode": "parsed_model_labels_present",
            },
        },
    )
    out = tmp_path / "foundation_optimization_report.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_foundation_optimization_report.py",
            "--design-optimization-dataset",
            str(dataset),
            "--foundation-optimization-artifact",
            str(artifact),
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
    assert payload["reason_code"] == "ERR_UPSTREAM_FOUNDATION_SCOPE_NOT_PROMOTED"
    assert payload["summary"]["optimization_mode"] == "upstream_foundation_scope_not_promoted_into_dataset"
    assert payload["summary"]["upstream_foundation_label_count"] == 2
    assert payload["checks"]["upstream_foundation_label_present"] is True


def test_foundation_optimization_report_flags_parser_drop_from_raw_source(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 24, "group_count": 9, "member_type_counts": {"beam": 8}},
        },
    )
    artifact = tmp_path / "foundation_optimization_artifact.json"
    _write_json(
        artifact,
        {
            "contract_pass": False,
            "summary": {
                "foundation_member_type_count": 0,
                "optimized_foundation_member_count": 0,
                "candidate_scan_mode": "npz_full_empty",
                "upstream_foundation_label_count": 0,
                "raw_source_foundation_label_count": 2,
                "upstream_foundation_provenance_mode": "parser_drop_suspected",
            },
        },
    )
    out = tmp_path / "foundation_optimization_report.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_foundation_optimization_report.py",
            "--design-optimization-dataset",
            str(dataset),
            "--foundation-optimization-artifact",
            str(artifact),
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
    assert payload["reason_code"] == "ERR_FOUNDATION_PARSER_DROP_SUSPECTED"
    assert payload["summary"]["optimization_mode"] == "foundation_scope_lost_between_raw_source_and_parsed_model"
    assert payload["summary"]["raw_source_foundation_label_count"] == 2
    assert payload["source_provenance"]["upstream_provenance_mode"] == "parser_drop_suspected"
    assert payload["checks"]["raw_source_foundation_label_present"] is True
    assert "raw_labels=2" in payload["reason"]


def test_foundation_optimization_report_passes_for_synthetic_foundation_source_end_to_end(tmp_path: Path) -> None:
    model = {
        "model": {
            "nodes": [
                {"id": 1, "x": 0.0, "y": 0.0, "z": 0.0},
                {"id": 2, "x": 4.0, "y": 0.0, "z": 0.0},
                {"id": 3, "x": 4.0, "y": 4.0, "z": 0.0},
                {"id": 4, "x": 0.0, "y": 4.0, "z": 0.0},
                {"id": 5, "x": 0.0, "y": 0.0, "z": -2.0},
                {"id": 6, "x": 4.0, "y": 0.0, "z": -2.0},
            ],
            "elements": [
                {"id": 101, "type": "PLATE", "section": 21, "nodes": [1, 2, 3, 4], "name": "MAT-A"},
                {"id": 102, "type": "BEAM", "section": 22, "nodes": [5, 6], "name": "PILECAP-B1"},
            ],
            "sections": [
                {"id": 21, "name": "RAFT-1200"},
                {"id": 22, "name": "PILE-CAP-700"},
            ],
            "metadata": {
                "groups": [
                    {"name": "FOUNDATION_ZONE", "element_ids": [101, 102]},
                ]
            },
        }
    }
    code_check = {
        "rows": [
            {"member_id": "101", "max_dcr": 0.74, "governing_component": "punching"},
            {"member_id": "102", "max_dcr": 0.81, "governing_component": "shear"},
        ],
        "member_check_rows": [
            {
                "member_id": "101",
                "member_type": "foundation",
                "rule_family": "strength",
                "clause": "KDS-RC-FOUND-PUNCH-001",
                "dcr": 0.74,
            },
            {
                "member_id": "102",
                "member_type": "foundation",
                "rule_family": "strength",
                "clause": "KDS-RC-FOUND-SHEAR-001",
                "dcr": 0.81,
            },
        ],
    }
    pbd = {"metrics": {"drift_envelope_max_pct": 0.92}}
    ndtha = {"summary": {"residual_drift_ratio_pct_max_abs": 0.18}}
    changes = {
        "changes": [
            {
                "group_id": "foundation_zone",
                "member_type": "foundation",
                "semantic_group": "foundation_zone",
                "action_name": "mat_down",
            }
        ]
    }
    blocked = {"blocked_rows": []}

    model_path = tmp_path / "midas_model.json"
    code_path = tmp_path / "code_check.json"
    pbd_path = tmp_path / "pbd.json"
    ndtha_path = tmp_path / "ndtha.json"
    changes_path = tmp_path / "design_optimization_cost_reduction_changes.json"
    blocked_path = tmp_path / "design_optimization_cost_reduction_blocked_actions.json"
    npz_out = tmp_path / "design_optimization_dataset.npz"
    dataset_out = tmp_path / "design_optimization_dataset_report.json"
    artifact_out = tmp_path / "foundation_optimization_artifact.json"
    report_out = tmp_path / "foundation_optimization_report.json"
    _write_json(model_path, model)
    _write_json(code_path, code_check)
    _write_json(pbd_path, pbd)
    _write_json(ndtha_path, ndtha)
    _write_json(changes_path, changes)
    _write_json(blocked_path, blocked)

    dataset_proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_design_optimization_dataset.py",
            "--midas-model",
            str(model_path),
            "--code-check",
            str(code_path),
            "--pbd-review",
            str(pbd_path),
            "--ndtha-residual",
            str(ndtha_path),
            "--dataset-npz-out",
            str(npz_out),
            "--summary-out",
            str(dataset_out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert dataset_proc.returncode == 0, dataset_proc.stderr

    artifact_proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_foundation_optimization_artifact.py",
            "--design-optimization-dataset",
            str(dataset_out),
            "--design-optimization-npz",
            str(npz_out),
            "--midas-model",
            str(model_path),
            "--cost-reduction-changes",
            str(changes_path),
            "--cost-reduction-blocked-actions",
            str(blocked_path),
            "--out",
            str(artifact_out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert artifact_proc.returncode == 0, artifact_proc.stderr

    report_proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_foundation_optimization_report.py",
            "--design-optimization-dataset",
            str(dataset_out),
            "--foundation-optimization-artifact",
            str(artifact_out),
            "--out",
            str(report_out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert report_proc.returncode == 0, report_proc.stderr

    artifact = json.loads(artifact_out.read_text(encoding="utf-8"))
    report = json.loads(report_out.read_text(encoding="utf-8"))
    assert artifact["contract_pass"] is True
    assert artifact["summary"]["foundation_member_type_count"] == 2
    assert artifact["summary"]["optimized_foundation_group_count"] == 1
    assert artifact["summary"]["candidate_scan_mode"] == "npz_full"
    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS"
    assert report["summary"]["optimization_mode"] == "active_foundation_member_optimization"
    assert report["summary"]["foundation_member_type_count"] == 2
    assert report["summary"]["foundation_artifact_optimized_group_count"] == 1


def test_foundation_optimization_report_distinguishes_empty_full_npz_scan_from_missing_summary(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 24, "group_count": 9, "member_type_counts": {"beam": 8}},
        },
    )
    artifact = tmp_path / "foundation_optimization_artifact.json"
    _write_json(
        artifact,
        {
            "contract_pass": False,
            "summary": {
                "candidate_scan_mode": "npz_full_empty",
                "foundation_member_type_count": 0,
            },
        },
    )
    out = tmp_path / "foundation_optimization_report.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_foundation_optimization_report.py",
            "--design-optimization-dataset",
            str(dataset),
            "--foundation-optimization-artifact",
            str(artifact),
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
    assert payload["reason_code"] == "ERR_DATASET_ABSENT"
    assert payload["summary"]["foundation_scope_source"] == "artifact_empty_scan"
    assert "full NPZ scan" in payload["reason"]


def test_foundation_optimization_report_normalizes_hyphenated_member_type_keys(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {
                "member_count": 24,
                "group_count": 9,
                "member_type_counts": {
                    "beam": 8,
                    "pile-cap": 2,
                    "raft": 3,
                },
            },
        },
    )
    out = tmp_path / "foundation_optimization_report.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_foundation_optimization_report.py",
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
    assert payload["summary"]["foundation_member_type_count"] == 5
    assert payload["checks"]["foundation_members_present"] is True


def test_foundation_scope_promotes_from_synthetic_dataset_generator_output(tmp_path: Path) -> None:
    model = tmp_path / "midas_model.json"
    code = tmp_path / "code_check.json"
    pbd = tmp_path / "pbd.json"
    ndtha = tmp_path / "ndtha.json"
    dataset_npz = tmp_path / "design_optimization_dataset.npz"
    dataset_report = tmp_path / "design_optimization_dataset_report.json"
    artifact = tmp_path / "foundation_optimization_artifact.json"
    changes = tmp_path / "design_optimization_cost_reduction_changes.json"
    blocked = tmp_path / "design_optimization_cost_reduction_blocked_actions.json"
    report = tmp_path / "foundation_optimization_report.json"

    _write_json(
        model,
        {
            "model": {
                "nodes": [
                    {"id": 1, "x": 0.0, "y": 0.0, "z": 0.0},
                    {"id": 2, "x": 4.0, "y": 0.0, "z": 0.0},
                    {"id": 3, "x": 4.0, "y": 4.0, "z": 0.0},
                    {"id": 4, "x": 0.0, "y": 4.0, "z": 0.0},
                    {"id": 5, "x": 0.0, "y": 0.0, "z": -2.0},
                    {"id": 6, "x": 4.0, "y": 0.0, "z": -2.0},
                ],
                "elements": [
                    {"id": 101, "type": "PLATE", "section": 21, "nodes": [1, 2, 3, 4], "name": "MAT-A"},
                    {"id": 102, "type": "BEAM", "section": 22, "nodes": [5, 6], "name": "PILECAP-B1"},
                ],
                "sections": [
                    {"id": 21, "name": "RAFT-1200"},
                    {"id": 22, "name": "PILE-CAP-700"},
                ],
                "metadata": {
                    "groups": [
                        {"name": "FOUNDATION_ZONE", "element_ids": [101, 102]},
                    ]
                },
            }
        },
    )
    _write_json(
        code,
        {
            "rows": [
                {"member_id": "101", "max_dcr": 0.74, "governing_component": "punching"},
                {"member_id": "102", "max_dcr": 0.81, "governing_component": "shear"},
            ],
            "member_check_rows": [
                {
                    "member_id": "101",
                    "member_type": "foundation",
                    "rule_family": "strength",
                    "clause": "KDS-RC-FOUND-PUNCH-001",
                    "dcr": 0.74,
                },
                {
                    "member_id": "102",
                    "member_type": "foundation",
                    "rule_family": "strength",
                    "clause": "KDS-RC-FOUND-SHEAR-001",
                    "dcr": 0.81,
                },
            ],
        },
    )
    _write_json(pbd, {"metrics": {"drift_envelope_max_pct": 0.92}})
    _write_json(ndtha, {"summary": {"residual_drift_ratio_pct_max_abs": 0.18}})

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_design_optimization_dataset.py",
            "--midas-model",
            str(model),
            "--code-check",
            str(code),
            "--pbd-review",
            str(pbd),
            "--ndtha-residual",
            str(ndtha),
            "--dataset-npz-out",
            str(dataset_npz),
            "--summary-out",
            str(dataset_report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    dataset_payload = json.loads(dataset_report.read_text(encoding="utf-8"))
    foundation_rows = [row for row in dataset_payload["rows_head"] if str(row.get("member_type")) == "foundation"]
    assert len(foundation_rows) == 2
    foundation_group_id = str(foundation_rows[0]["group_id"])
    foundation_member_id = str(foundation_rows[0]["member_id"])
    foundation_semantic_group = str(foundation_rows[0]["semantic_group"])

    _write_json(
        changes,
        {
            "changes": [
                {
                    "group_id": foundation_group_id,
                    "member_id": foundation_member_id,
                    "member_type": "foundation",
                    "semantic_group": foundation_semantic_group,
                    "action_name": "rebar_down",
                }
            ]
        },
    )
    _write_json(blocked, {"blocked_rows": []})

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_foundation_optimization_artifact.py",
            "--design-optimization-dataset",
            str(dataset_report),
            "--design-optimization-npz",
            str(dataset_npz),
            "--midas-model",
            str(model),
            "--cost-reduction-changes",
            str(changes),
            "--cost-reduction-blocked-actions",
            str(blocked),
            "--out",
            str(artifact),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    artifact_payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert artifact_payload["contract_pass"] is True
    assert artifact_payload["reason_code"] == "PASS"
    assert artifact_payload["summary"]["candidate_scan_mode"] == "npz_full"
    assert artifact_payload["summary"]["foundation_member_type_count"] == 2
    assert artifact_payload["summary"]["optimized_foundation_group_count"] == 1
    assert artifact_payload["summary"]["upstream_foundation_provenance_mode"] == "dataset_scope_only"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_foundation_optimization_report.py",
            "--design-optimization-dataset",
            str(dataset_report),
            "--foundation-optimization-artifact",
            str(artifact),
            "--out",
            str(report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["summary"]["optimization_mode"] == "active_foundation_member_optimization"
    assert payload["summary"]["foundation_member_type_count"] == 2
    assert payload["summary"]["foundation_scope_source"] == "dataset_summary"
    assert payload["summary"]["foundation_artifact_scan_mode"] == "npz_full"
    assert payload["summary"]["upstream_foundation_provenance_mode"] == "dataset_scope_only"


def test_foundation_scope_promotes_from_realish_fixture_end_to_end(tmp_path: Path) -> None:
    model = _foundation_fixture_path("foundation_small_model.json")
    code = _foundation_fixture_path("foundation_small_code_check.json")
    pbd = _foundation_fixture_path("foundation_small_pbd.json")
    ndtha = _foundation_fixture_path("foundation_small_ndtha.json")
    dataset_npz = tmp_path / "design_optimization_dataset.npz"
    dataset_report = tmp_path / "design_optimization_dataset_report.json"
    artifact = tmp_path / "foundation_optimization_artifact.json"
    changes = tmp_path / "design_optimization_cost_reduction_changes.json"
    blocked = tmp_path / "design_optimization_cost_reduction_blocked_actions.json"
    report = tmp_path / "foundation_optimization_report.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_design_optimization_dataset.py",
            "--midas-model",
            str(model),
            "--code-check",
            str(code),
            "--pbd-review",
            str(pbd),
            "--ndtha-residual",
            str(ndtha),
            "--dataset-npz-out",
            str(dataset_npz),
            "--summary-out",
            str(dataset_report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    dataset_payload = json.loads(dataset_report.read_text(encoding="utf-8"))
    foundation_rows = [row for row in dataset_payload["rows_head"] if str(row.get("member_type")) == "foundation"]
    assert len(foundation_rows) == 2
    foundation_group_id = str(foundation_rows[0]["group_id"])
    foundation_member_id = str(foundation_rows[0]["member_id"])
    foundation_semantic_group = str(foundation_rows[0]["semantic_group"])
    _write_json(
        changes,
        {
            "changes": [
                {
                    "group_id": foundation_group_id,
                    "member_id": foundation_member_id,
                    "member_type": "foundation",
                    "semantic_group": foundation_semantic_group,
                    "action_name": "rebar_down",
                }
            ]
        },
    )
    _write_json(blocked, {"blocked_rows": []})

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_foundation_optimization_artifact.py",
            "--design-optimization-dataset",
            str(dataset_report),
            "--design-optimization-npz",
            str(dataset_npz),
            "--midas-model",
            str(model),
            "--cost-reduction-changes",
            str(changes),
            "--cost-reduction-blocked-actions",
            str(blocked),
            "--out",
            str(artifact),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    artifact_payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert artifact_payload["contract_pass"] is True
    assert artifact_payload["reason_code"] == "PASS"
    assert artifact_payload["summary"]["candidate_scan_mode"] == "npz_full"
    assert artifact_payload["summary"]["foundation_member_type_count"] == 2
    assert artifact_payload["summary"]["optimized_foundation_group_count"] == 1
    assert artifact_payload["summary"]["upstream_foundation_provenance_mode"] == "dataset_scope_only"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_foundation_optimization_report.py",
            "--design-optimization-dataset",
            str(dataset_report),
            "--foundation-optimization-artifact",
            str(artifact),
            "--out",
            str(report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["summary"]["optimization_mode"] == "active_foundation_member_optimization"
    assert payload["summary"]["foundation_member_type_count"] == 2
    assert payload["summary"]["foundation_scope_source"] == "dataset_summary"
    assert payload["summary"]["foundation_artifact_scan_mode"] == "npz_full"
    assert payload["summary"]["upstream_foundation_provenance_mode"] == "dataset_scope_only"


def test_foundation_scope_promotes_from_realish_mgt_fixture_via_parser(tmp_path: Path) -> None:
    mgt = _foundation_fixture_path("foundation_small.mgt")
    code = _foundation_fixture_path("foundation_small_code_check.json")
    pbd = _foundation_fixture_path("foundation_small_pbd.json")
    ndtha = _foundation_fixture_path("foundation_small_ndtha.json")
    parsed_model = tmp_path / "foundation_small_model.parsed.json"
    parser_npz = tmp_path / "foundation_small_graph.npz"
    parser_report = tmp_path / "foundation_small_parse_report.json"
    dataset_npz = tmp_path / "design_optimization_dataset.npz"
    dataset_report = tmp_path / "design_optimization_dataset_report.json"
    artifact = tmp_path / "foundation_optimization_artifact.json"
    changes = tmp_path / "design_optimization_cost_reduction_changes.json"
    blocked = tmp_path / "design_optimization_cost_reduction_blocked_actions.json"
    report = tmp_path / "foundation_optimization_report.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/parse_midas_mgt_to_json_npz.py",
            "--mgt",
            str(mgt),
            "--json-out",
            str(parsed_model),
            "--npz-out",
            str(parser_npz),
            "--report-out",
            str(parser_report),
            "--min-nodes",
            "4",
            "--min-elements",
            "3",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    parse_payload = json.loads(parser_report.read_text(encoding="utf-8"))
    assert parse_payload["contract_pass"] is True
    assert parse_payload["reason_code"] == "PASS"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_design_optimization_dataset.py",
            "--midas-model",
            str(parsed_model),
            "--code-check",
            str(code),
            "--pbd-review",
            str(pbd),
            "--ndtha-residual",
            str(ndtha),
            "--dataset-npz-out",
            str(dataset_npz),
            "--summary-out",
            str(dataset_report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    dataset_payload = json.loads(dataset_report.read_text(encoding="utf-8"))
    foundation_rows = [row for row in dataset_payload["rows_head"] if str(row.get("member_type")) == "foundation"]
    assert len(foundation_rows) == 2
    foundation_group_id = str(foundation_rows[0]["group_id"])
    foundation_member_id = str(foundation_rows[0]["member_id"])
    foundation_semantic_group = str(foundation_rows[0]["semantic_group"])
    _write_json(
        changes,
        {
            "changes": [
                {
                    "group_id": foundation_group_id,
                    "member_id": foundation_member_id,
                    "member_type": "foundation",
                    "semantic_group": foundation_semantic_group,
                    "action_name": "rebar_down",
                }
            ]
        },
    )
    _write_json(blocked, {"blocked_rows": []})

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_foundation_optimization_artifact.py",
            "--design-optimization-dataset",
            str(dataset_report),
            "--design-optimization-npz",
            str(dataset_npz),
            "--midas-model",
            str(parsed_model),
            "--cost-reduction-changes",
            str(changes),
            "--cost-reduction-blocked-actions",
            str(blocked),
            "--out",
            str(artifact),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    artifact_payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert artifact_payload["contract_pass"] is True
    assert artifact_payload["reason_code"] == "PASS"
    assert artifact_payload["summary"]["candidate_scan_mode"] == "npz_full"
    assert artifact_payload["summary"]["foundation_member_type_count"] == 2
    assert artifact_payload["summary"]["optimized_foundation_group_count"] == 1
    assert artifact_payload["summary"]["upstream_foundation_provenance_mode"] == "dataset_scope_only"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_foundation_optimization_report.py",
            "--design-optimization-dataset",
            str(dataset_report),
            "--foundation-optimization-artifact",
            str(artifact),
            "--out",
            str(report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["summary"]["optimization_mode"] == "active_foundation_member_optimization"
    assert payload["summary"]["foundation_member_type_count"] == 2
    assert payload["summary"]["foundation_scope_source"] == "dataset_summary"
    assert payload["summary"]["foundation_artifact_scan_mode"] == "npz_full"
    assert payload["summary"]["upstream_foundation_provenance_mode"] == "dataset_scope_only"
