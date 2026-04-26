from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_panel_zone_clash_report_marks_proxy_artifact_without_3d_verification_as_open(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {
                "constructability_score": 0.21,
                "detailing_complexity_score": 0.62,
            },
            "rows_head": [
                {
                    "member_id": "B101",
                    "constructability_score": 0.14,
                    "anchorage_complexity": 0.77,
                    "detailing_violation_ratio": 0.63,
                }
            ],
        },
    )
    pbd = tmp_path / "pbd_review_package_report.json"
    _write_json(pbd, {"contract_pass": True})
    clash = tmp_path / "panel_zone_clash_artifact.json"
    _write_json(
        clash,
        {
            "contract_pass": True,
            "artifacts": {"interference_row_count": 3},
            "summary": {
                "interference_count": 3,
                "verification_mode": "proxy_only",
            },
        },
    )
    out = tmp_path / "panel_zone_clash_report.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_clash_report.py",
            "--design-optimization-dataset",
            str(dataset),
            "--pbd-review-package",
            str(pbd),
            "--panel-zone-clash-artifact",
            str(clash),
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
    assert payload["reason_code"] == "ERR_PROXY_ONLY"
    assert payload["summary"]["constructability_mode"] == "proxy_artifact_attached_but_not_3d_verified"
    assert payload["summary"]["constructability_low_outlier_count"] == 1
    assert payload["summary"]["panel_zone_proxy_candidate_count"] == 0
    assert payload["checks"]["constructability_proxy_only"] is False
    assert payload["checks"]["panel_zone_clash_artifact_present"] is True
    assert payload["checks"]["panel_zone_clash_artifact_3d_verified"] is False
    assert payload["checks"]["panel_zone_required_sources_complete"] is False
    assert payload["summary"]["panel_zone_external_validation_advisory_only"] is False
    assert payload["summary"]["panel_zone_external_validation_release_blocking"] is False
    assert payload["summary"]["panel_zone_external_validation_status_label"] == "not_applicable"
    assert payload["summary"]["panel_zone_external_validation_required_evidence"] == "internal_panel_zone_3d_completion_first"
    assert "required_evidence=internal_panel_zone_3d_completion_first" in payload["summary"]["panel_zone_external_validation_summary_line"]
    assert payload["checks"]["panel_zone_external_validation_advisory_only"] is False
    assert payload["checks"]["panel_zone_external_validation_release_blocking"] is False


def test_panel_zone_clash_report_marks_missing_artifact_path_as_unattached(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {
                "constructability_score": 0.21,
                "detailing_complexity_score": 0.62,
            },
            "rows_head": [
                {
                    "member_id": "B101",
                    "constructability_score": 0.14,
                    "anchorage_complexity": 0.77,
                    "detailing_violation_ratio": 0.63,
                }
            ],
        },
    )
    pbd = tmp_path / "pbd_review_package_report.json"
    _write_json(pbd, {"contract_pass": True})
    out = tmp_path / "panel_zone_clash_report.json"
    missing_artifact = tmp_path / "missing_panel_zone_clash_artifact.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_clash_report.py",
            "--design-optimization-dataset",
            str(dataset),
            "--pbd-review-package",
            str(pbd),
            "--panel-zone-clash-artifact",
            str(missing_artifact),
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
    assert payload["reason_code"] == "ERR_NO_PANEL_ZONE_CLASH_ARTIFACT"
    assert payload["summary"]["panel_zone_clash_report_attached"] is False
    assert payload["summary"]["panel_zone_external_validation_status_label"] == "not_applicable"
    assert payload["checks"]["panel_zone_clash_artifact_present"] is False


def test_panel_zone_clash_report_uses_proxy_candidate_count_from_artifact_when_rows_head_is_clean(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {
                "constructability_score": 0.31,
                "detailing_complexity_score": 0.62,
            },
            "rows_head": [
                {
                    "member_id": "B101",
                    "constructability_score": 0.31,
                    "anchorage_complexity": 0.22,
                    "detailing_violation_ratio": 0.18,
                }
            ],
        },
    )
    npz_path = tmp_path / "design_optimization_dataset.npz"
    npz_path.write_bytes(b"npz-placeholder")
    pbd = tmp_path / "pbd_review_package_report.json"
    _write_json(pbd, {"contract_pass": True})
    clash = tmp_path / "panel_zone_clash_artifact.json"
    _write_json(
        clash,
        {
            "contract_pass": True,
            "summary": {
                "artifact_mode": "constructability_proxy_candidate_scan",
                "verification_mode": "proxy_only",
                "low_constructability_row_count": 11,
                "source_contract_mode": "topology_capable_proxy_scan",
            },
            "source_provenance": {
                "input_kind": "npz_full",
                "input_dataset_report": str(dataset),
                "input_design_optimization_npz": str(npz_path),
                "topology_capable_input": True,
                "true_3d_clash_verified": False,
                "true_3d_anchorage_verified": False,
                "missing_required_sources": [
                    "panel_zone_joint_geometry_3d",
                    "panel_zone_rebar_anchorage_3d",
                    "panel_zone_clash_verification_3d",
                ],
            },
            "inputs": {
                "design_optimization_dataset": str(dataset),
                "design_optimization_npz": str(npz_path),
            },
            "artifacts": {"interference_row_count": 11},
        },
    )
    out = tmp_path / "panel_zone_clash_report.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_clash_report.py",
            "--design-optimization-dataset",
            str(dataset),
            "--pbd-review-package",
            str(pbd),
            "--panel-zone-clash-artifact",
            str(clash),
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
    assert payload["reason_code"] == "ERR_MISSING_REQUIRED_SOURCES"
    assert payload["summary"]["constructability_low_outlier_count"] == 11
    assert payload["summary"]["panel_zone_proxy_candidate_count"] == 11
    assert payload["summary"]["panel_zone_source_artifact_kind"] == "design_optimization_dataset_npz"
    assert payload["summary"]["panel_zone_source_artifact_path"] == str(npz_path)
    assert payload["summary"]["panel_zone_source_contract_mode"] == "topology_capable_proxy_scan"
    assert payload["summary"]["panel_zone_missing_required_sources"] == [
        "panel_zone_joint_geometry_3d",
        "panel_zone_rebar_anchorage_3d",
        "panel_zone_clash_verification_3d",
    ]
    assert payload["summary"]["panel_zone_topology_capable_input"] is True
    assert payload["summary"]["panel_zone_true_3d_clash_verified"] is False
    assert payload["checks"]["panel_zone_clash_artifact_source_detected"] is True
    assert payload["checks"]["panel_zone_topology_capable_input"] is True
    assert payload["checks"]["panel_zone_missing_required_sources"] is True


def test_panel_zone_clash_report_passes_only_when_three_source_artifacts_are_attached_and_valid(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {
                "constructability_score": 0.27,
                "detailing_complexity_score": 0.44,
            },
            "rows_head": [
                {
                    "member_id": "B301",
                    "constructability_score": 0.19,
                    "anchorage_complexity": 0.71,
                    "detailing_violation_ratio": 0.48,
                }
            ],
        },
    )
    pbd = tmp_path / "pbd_review_package_report.json"
    _write_json(pbd, {"contract_pass": True})
    joint = tmp_path / "panel_zone_joint_geometry_3d.json"
    anchorage = tmp_path / "panel_zone_rebar_anchorage_3d.json"
    clash_verification = tmp_path / "panel_zone_clash_verification_3d.json"
    _write_json(joint, {"contract_pass": True})
    _write_json(anchorage, {"contract_pass": True})
    _write_json(clash_verification, {"contract_pass": True})
    clash = tmp_path / "panel_zone_clash_artifact.json"
    _write_json(
        clash,
        {
            "contract_pass": True,
            "summary": {
                "artifact_mode": "constructability_proxy_candidate_scan",
                "verification_tier": "true_3d_clash_and_anchorage_verified",
                "required_sources_complete": True,
                "true_3d_clash_verified": True,
                "true_3d_anchorage_verified": True,
                "low_constructability_row_count": 1,
                "source_contract_mode": "true_3d_clash_and_anchorage_verified",
            },
            "source_provenance": {
                "input_kind": "npz_full",
                "topology_capable_input": True,
                "required_sources_complete": True,
                "true_3d_clash_verified": True,
                "true_3d_anchorage_verified": True,
                "verification_tier": "true_3d_clash_and_anchorage_verified",
                "missing_required_sources": [],
                "source_artifacts": {
                    "panel_zone_joint_geometry_3d": {"path": str(joint), "present": True, "contract_pass": True, "valid": True},
                    "panel_zone_rebar_anchorage_3d": {"path": str(anchorage), "present": True, "contract_pass": True, "valid": True},
                    "panel_zone_clash_verification_3d": {"path": str(clash_verification), "present": True, "contract_pass": True, "valid": True},
                },
            },
            "artifacts": {"interference_row_count": 1},
        },
    )
    out = tmp_path / "panel_zone_clash_report.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_clash_report.py",
            "--design-optimization-dataset",
            str(dataset),
            "--pbd-review-package",
            str(pbd),
            "--panel-zone-clash-artifact",
            str(clash),
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
    assert payload["summary"]["constructability_mode"] == "panel_zone_3d_clash_and_anchorage_verified"
    assert payload["summary"]["panel_zone_required_sources_complete"] is True
    assert payload["summary"]["panel_zone_true_3d_bridge_complete"] is True
    assert payload["checks"]["panel_zone_clash_artifact_3d_verified"] is True
    assert payload["checks"]["panel_zone_required_sources_complete"] is True


def test_panel_zone_clash_report_marks_topology_projected_bridge_as_open_but_non_proxy(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {
                "constructability_score": 0.24,
                "detailing_complexity_score": 0.41,
            },
            "rows_head": [
                {
                    "member_id": "B501",
                    "constructability_score": 0.19,
                    "anchorage_complexity": 0.66,
                    "detailing_violation_ratio": 0.44,
                }
            ],
        },
    )
    pbd = tmp_path / "pbd_review_package_report.json"
    _write_json(pbd, {"contract_pass": True})
    clash = tmp_path / "panel_zone_clash_artifact.json"
    _write_json(
        clash,
        {
            "contract_pass": True,
            "summary": {
                "verification_mode": "topology_projected_midas_panel_bridge",
                "verification_tier": "topology_projected_3d_clash_and_anchorage_bridge",
                "required_sources_complete": True,
                "source_contract_mode": "topology_projected_3d_clash_and_anchorage_bridge",
                "low_constructability_row_count": 3,
                "validated_source_row_count_total": 9,
                "validated_source_overlap_member_count_min": 3,
                "source_producer_backends": {
                    "panel_zone_joint_geometry_3d": "midas_topology_projection",
                    "panel_zone_rebar_anchorage_3d": "midas_topology_projection",
                    "panel_zone_clash_verification_3d": "midas_topology_projection",
                },
            },
            "source_provenance": {
                "input_kind": "npz_full",
                "topology_capable_input": True,
                "required_sources_complete": True,
                "true_3d_clash_verified": False,
                "true_3d_anchorage_verified": False,
                "topology_projected_bridge_complete": True,
                "solver_verified_bridge_complete": False,
                "verification_tier": "topology_projected_3d_clash_and_anchorage_bridge",
                "missing_required_sources": [],
                "source_producer_backends": {
                    "panel_zone_joint_geometry_3d": "midas_topology_projection",
                    "panel_zone_rebar_anchorage_3d": "midas_topology_projection",
                    "panel_zone_clash_verification_3d": "midas_topology_projection",
                },
                "validated_source_row_count_total": 9,
                "validated_source_overlap_member_count_min": 3,
            },
            "artifacts": {"interference_row_count": 3},
        },
    )
    inbox_status = tmp_path / "panel_zone_solver_verified_inbox_status.json"
    _write_json(
        inbox_status,
        {
            "run_id": "phase1-panel-zone-solver-verified-inbox-status",
            "summary": {
                "panel_zone_solver_verified_inbox_status_mode": "empty_without_history",
                "panel_zone_solver_verified_inbox_has_input": False,
                "panel_zone_solver_verified_pending_input": False,
                "panel_zone_solver_verified_input_mode_detected": "empty",
                "panel_zone_solver_verified_latest_consume_report_present": False,
                "panel_zone_solver_verified_latest_consume_contract_pass": False,
                "panel_zone_solver_verified_latest_consume_reason_code": "",
                "panel_zone_solver_verified_source_origin_class": "",
                "panel_zone_solver_verified_release_refresh_source_allowed": False,
                "panel_zone_solver_verified_recommended_action": "wait_for_solver_drop",
            },
        },
    )
    out = tmp_path / "panel_zone_clash_report.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_clash_report.py",
            "--design-optimization-dataset",
            str(dataset),
            "--pbd-review-package",
            str(pbd),
            "--panel-zone-clash-artifact",
            str(clash),
            "--solver-verified-inbox-status",
            str(inbox_status),
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
    assert payload["summary"]["constructability_mode"] == "internal_engine_panel_zone_3d_clash_and_anchorage_complete"
    assert payload["summary"]["panel_zone_topology_projected_bridge_complete"] is True
    assert payload["summary"]["panel_zone_solver_verified_bridge_complete"] is False
    assert payload["summary"]["panel_zone_internal_engine_complete"] is True
    assert payload["summary"]["panel_zone_external_validation_pending"] is True
    assert payload["summary"]["panel_zone_external_validation_advisory_only"] is True
    assert payload["summary"]["panel_zone_external_validation_release_blocking"] is False
    assert payload["summary"]["panel_zone_external_validation_status_label"] == "validated_fallback_only_gap"
    assert payload["summary"]["panel_zone_external_validation_artifact_closed"] is False
    assert payload["summary"]["panel_zone_external_validation_closure_mode"] == "open_fallback_validated"
    assert payload["summary"]["panel_zone_external_validation_source_count"] == 3
    assert payload["summary"]["panel_zone_external_validation_validated_source_count"] == 3
    assert payload["summary"]["panel_zone_external_validation_exact_source_count"] == 0
    assert payload["summary"]["panel_zone_external_validation_fallback_source_count"] == 3
    assert payload["summary"]["panel_zone_external_validation_candidate_member_count"] == 3
    assert payload["summary"]["panel_zone_external_validation_validated_member_count"] == 3
    assert payload["summary"]["panel_zone_external_validation_exact_member_count"] == 0
    assert payload["summary"]["panel_zone_external_validation_fallback_member_count"] == 3
    assert payload["summary"]["panel_zone_external_validation_exact_validated_row_count"] == 0
    assert payload["summary"]["panel_zone_external_validation_fallback_validated_row_count"] == 9
    assert payload["summary"]["panel_zone_external_validation_unattributed_validated_row_count"] == 0
    assert payload["summary"]["panel_zone_external_validation_local_closure_state"] == "awaiting_solver_verified_drop"
    assert "Local closeout: no solver-verified inbox input is present" in payload["summary"]["panel_zone_external_validation_local_closure_label"]
    assert "status=validated_fallback_only_gap" in payload["summary"]["panel_zone_external_validation_closing_summary_label"]
    assert (
        payload["summary"]["panel_zone_external_validation_provenance_summary_label"]
        == "validated_sources=3/3 | exact_sources=0/3 | fallback_sources=3/3 | missing_sources=0/3 | validated_members=3/3 | exact_members=0/3 | fallback_members=3/3 | exact_rows=0/9 | fallback_rows=9/9"
    )
    assert payload["summary"]["panel_zone_external_validation_required_evidence"] == "solver_verified_3d_clash_and_anchorage_artifact"
    assert "boundary=external_validation_only" in payload["summary"]["panel_zone_external_validation_summary_line"]
    assert "artifact_closed=False" in payload["summary"]["panel_zone_external_validation_summary_line"]
    assert "closure_mode=open_fallback_validated" in payload["summary"]["panel_zone_external_validation_summary_line"]
    assert payload["summary"]["panel_zone_validation_boundary"] == "external_validation_only"
    assert payload["summary"]["panel_zone_source_producer_backends"] == {
        "panel_zone_joint_geometry_3d": "midas_topology_projection",
        "panel_zone_rebar_anchorage_3d": "midas_topology_projection",
        "panel_zone_clash_verification_3d": "midas_topology_projection",
    }
    assert payload["checks"]["panel_zone_topology_projected_artifact_present"] is True
    assert payload["checks"]["panel_zone_proxy_artifact_present"] is False
    assert payload["checks"]["panel_zone_internal_engine_complete"] is True
    assert payload["checks"]["panel_zone_external_validation_pending"] is True
    assert payload["checks"]["panel_zone_external_validation_advisory_only"] is True
    assert payload["checks"]["panel_zone_external_validation_release_blocking"] is False


def test_panel_zone_clash_report_uses_inbox_status_for_local_closeout(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {
                "constructability_score": 0.24,
                "detailing_complexity_score": 0.41,
            },
            "rows_head": [
                {
                    "member_id": "B501",
                    "constructability_score": 0.19,
                    "anchorage_complexity": 0.66,
                    "detailing_violation_ratio": 0.44,
                }
            ],
        },
    )
    pbd = tmp_path / "pbd_review_package_report.json"
    _write_json(pbd, {"contract_pass": True})
    clash = tmp_path / "panel_zone_clash_artifact.json"
    _write_json(
        clash,
        {
            "contract_pass": True,
            "summary": {
                "verification_mode": "topology_projected_midas_panel_bridge",
                "verification_tier": "topology_projected_3d_clash_and_anchorage_bridge",
                "required_sources_complete": True,
                "source_contract_mode": "topology_projected_3d_clash_and_anchorage_bridge",
                "low_constructability_row_count": 3,
                "validated_source_row_count_total": 9,
                "validated_source_overlap_member_count_min": 3,
            },
            "source_provenance": {
                "input_kind": "npz_full",
                "topology_capable_input": True,
                "required_sources_complete": True,
                "true_3d_clash_verified": False,
                "true_3d_anchorage_verified": False,
                "topology_projected_bridge_complete": True,
                "solver_verified_bridge_complete": False,
                "verification_tier": "topology_projected_3d_clash_and_anchorage_bridge",
                "missing_required_sources": [],
            },
            "artifacts": {"interference_row_count": 3},
        },
    )
    inbox_status = tmp_path / "panel_zone_solver_verified_inbox_status.json"
    _write_json(
        inbox_status,
        {
            "run_id": "phase1-panel-zone-solver-verified-inbox-status",
            "summary": {
                "panel_zone_solver_verified_inbox_status_mode": "pending_raw_triplet",
                "panel_zone_solver_verified_inbox_has_input": True,
                "panel_zone_solver_verified_pending_input": True,
                "panel_zone_solver_verified_input_mode_detected": "raw_triplet",
                "panel_zone_solver_verified_latest_consume_report_present": False,
                "panel_zone_solver_verified_latest_consume_contract_pass": False,
                "panel_zone_solver_verified_latest_consume_reason_code": "",
                "panel_zone_solver_verified_source_origin_class": "solver_verified_drop",
                "panel_zone_solver_verified_release_refresh_source_allowed": True,
                "panel_zone_solver_verified_recommended_action": "consume_pending_input",
            },
        },
    )
    out = tmp_path / "panel_zone_clash_report.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_clash_report.py",
            "--design-optimization-dataset",
            str(dataset),
            "--pbd-review-package",
            str(pbd),
            "--panel-zone-clash-artifact",
            str(clash),
            "--solver-verified-inbox-status",
            str(inbox_status),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["summary"]["panel_zone_external_validation_local_closure_state"] == "pending_solver_verified_consume"
    assert "pending_raw_triplet" in payload["summary"]["panel_zone_external_validation_local_closure_label"]
    assert payload["summary"]["panel_zone_solver_verified_inbox_status_mode"] == "pending_raw_triplet"
    assert payload["summary"]["panel_zone_solver_verified_pending_input"] is True
    assert "inbox=pending_raw_triplet" in payload["summary"]["panel_zone_external_validation_closing_summary_label"]
    assert "pending_input=True" in payload["summary"]["panel_zone_external_validation_closing_summary_label"]
    assert payload["inputs"]["solver_verified_inbox_status"] == str(inbox_status)


def test_panel_zone_clash_report_mentions_instruction_sidecar_overlap_for_topology_projected_bridge(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {
                "constructability_score": 0.24,
                "detailing_complexity_score": 0.41,
            },
            "rows_head": [
                {
                    "member_id": "B501",
                    "constructability_score": 0.19,
                    "anchorage_complexity": 0.66,
                    "detailing_violation_ratio": 0.44,
                }
            ],
        },
    )
    pbd = tmp_path / "pbd_review_package_report.json"
    _write_json(pbd, {"contract_pass": True})
    clash = tmp_path / "panel_zone_clash_artifact.json"
    _write_json(
        clash,
        {
            "contract_pass": True,
            "summary": {
                "verification_mode": "topology_projected_midas_panel_bridge",
                "verification_tier": "topology_projected_3d_clash_and_anchorage_bridge",
                "required_sources_complete": True,
                "source_contract_mode": "topology_projected_3d_clash_and_anchorage_bridge",
                "low_constructability_row_count": 3,
            },
            "source_provenance": {
                "input_kind": "npz_full",
                "topology_capable_input": True,
                "required_sources_complete": True,
                "true_3d_clash_verified": False,
                "true_3d_anchorage_verified": False,
                "topology_projected_bridge_complete": True,
                "solver_verified_bridge_complete": False,
                "verification_tier": "topology_projected_3d_clash_and_anchorage_bridge",
                "missing_required_sources": [],
                "instruction_sidecar_present": True,
                "instruction_sidecar_change_count": 17,
                "instruction_sidecar_candidate_overlap_mode": "section_signature",
                "instruction_sidecar_overlap_row_count": 4,
                "instruction_sidecar_overlap_member_count": 11,
                "instruction_sidecar_overlap_group_count": 3,
                "instruction_sidecar_evidence_model": "direct_patch_plus_structured_sidecar",
                "instruction_sidecar_rebar_delivery_mode": "structured_sidecar_only",
                "member_mapping_sidecar_present": True,
                "member_mapping_sidecar_mode": "explicit_member_id_map",
                "member_mapping_sidecar_row_count": 1,
                "member_mapping_sidecar_applied_row_count": 1,
                "member_mapping_sidecar_unmapped_source_member_count": 0,
                "validated_source_row_count_total": 9,
                "validated_source_overlap_member_count_min": 3,
            },
            "artifacts": {"interference_row_count": 3},
        },
    )
    inbox_status = tmp_path / "panel_zone_solver_verified_inbox_status.json"
    _write_json(
        inbox_status,
        {
            "run_id": "phase1-panel-zone-solver-verified-inbox-status",
            "summary": {
                "panel_zone_solver_verified_inbox_status_mode": "empty_without_history",
                "panel_zone_solver_verified_inbox_has_input": False,
                "panel_zone_solver_verified_pending_input": False,
                "panel_zone_solver_verified_input_mode_detected": "empty",
                "panel_zone_solver_verified_latest_consume_report_present": False,
                "panel_zone_solver_verified_latest_consume_contract_pass": False,
                "panel_zone_solver_verified_latest_consume_reason_code": "",
                "panel_zone_solver_verified_source_origin_class": "",
                "panel_zone_solver_verified_release_refresh_source_allowed": False,
                "panel_zone_solver_verified_recommended_action": "wait_for_solver_drop",
            },
        },
    )
    out = tmp_path / "panel_zone_clash_report.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_clash_report.py",
            "--design-optimization-dataset",
            str(dataset),
            "--pbd-review-package",
            str(pbd),
            "--panel-zone-clash-artifact",
            str(clash),
            "--solver-verified-inbox-status",
            str(inbox_status),
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
    assert "Internal engine completed panel-zone joint geometry, anchorage, and clash recomputation" in payload["reason"]
    assert payload["summary"]["panel_zone_internal_engine_complete"] is True
    assert payload["summary"]["panel_zone_external_validation_pending"] is True
    assert payload["summary"]["panel_zone_external_validation_advisory_only"] is True
    assert payload["summary"]["panel_zone_external_validation_release_blocking"] is False
    assert payload["summary"]["panel_zone_external_validation_status_label"] == "validated_fallback_only_gap"
    assert payload["summary"]["panel_zone_external_validation_artifact_closed"] is False
    assert payload["summary"]["panel_zone_external_validation_closure_mode"] == "open_fallback_validated"
    assert payload["summary"]["panel_zone_external_validation_source_count"] == 3
    assert payload["summary"]["panel_zone_external_validation_validated_source_count"] == 3
    assert payload["summary"]["panel_zone_external_validation_exact_source_count"] == 0
    assert payload["summary"]["panel_zone_external_validation_fallback_source_count"] == 3
    assert payload["summary"]["panel_zone_external_validation_candidate_member_count"] == 3
    assert payload["summary"]["panel_zone_external_validation_validated_member_count"] == 3
    assert payload["summary"]["panel_zone_external_validation_exact_validated_row_count"] == 0
    assert payload["summary"]["panel_zone_external_validation_fallback_validated_row_count"] == 9
    assert payload["summary"]["panel_zone_external_validation_unattributed_validated_row_count"] == 0
    assert payload["summary"]["panel_zone_external_validation_local_closure_state"] == "awaiting_solver_verified_drop"
    assert "Local closeout: no solver-verified inbox input is present" in payload["summary"]["panel_zone_external_validation_local_closure_label"]
    assert "status=validated_fallback_only_gap" in payload["summary"]["panel_zone_external_validation_closing_summary_label"]
    assert payload["summary"]["panel_zone_external_validation_required_evidence"] == "solver_verified_3d_clash_and_anchorage_artifact"
    assert "boundary=external_validation_only" in payload["summary"]["panel_zone_external_validation_summary_line"]
    assert "artifact_closed=False" in payload["summary"]["panel_zone_external_validation_summary_line"]
    assert "closure_mode=open_fallback_validated" in payload["summary"]["panel_zone_external_validation_summary_line"]
    assert payload["summary"]["panel_zone_validation_boundary"] == "external_validation_only"
    assert payload["summary"]["panel_zone_instruction_sidecar_present"] is True
    assert payload["summary"]["panel_zone_instruction_sidecar_change_count"] == 17
    assert payload["summary"]["panel_zone_instruction_sidecar_candidate_overlap_mode"] == "section_signature"
    assert payload["summary"]["panel_zone_instruction_sidecar_overlap_member_count"] == 11
    assert payload["summary"]["panel_zone_instruction_sidecar_evidence_model"] == "direct_patch_plus_structured_sidecar"
    assert payload["summary"]["panel_zone_instruction_sidecar_rebar_delivery_mode"] == "structured_sidecar_only"
    assert payload["summary"]["panel_zone_member_mapping_sidecar_present"] is True
    assert payload["summary"]["panel_zone_member_mapping_sidecar_mode"] == "explicit_member_id_map"
    assert payload["summary"]["panel_zone_member_mapping_sidecar_row_count"] == 1
    assert payload["summary"]["panel_zone_member_mapping_sidecar_applied_row_count"] == 1


def test_panel_zone_clash_report_rewrites_proxy_reason_when_candidate_scan_artifact_reports_pass(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"constructability_score": 0.31, "detailing_complexity_score": 0.62},
            "rows_head": [],
        },
    )
    pbd = tmp_path / "pbd_review_package_report.json"
    _write_json(pbd, {"contract_pass": True})
    clash = tmp_path / "panel_zone_clash_artifact.json"
    _write_json(
        clash,
        {
            "contract_pass": True,
            "reason_code": "PASS",
            "reason": "panel-zone clash artifact generated from low-constructability members",
            "summary": {
                "artifact_mode": "constructability_proxy_candidate_scan",
                "verification_mode": "proxy_only",
                "low_constructability_row_count": 5,
            },
            "artifacts": {"interference_row_count": 5},
        },
    )
    out = tmp_path / "panel_zone_clash_report.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_clash_report.py",
            "--design-optimization-dataset",
            str(dataset),
            "--pbd-review-package",
            str(pbd),
            "--panel-zone-clash-artifact",
            str(clash),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["reason_code"] == "ERR_PROXY_ONLY"
    assert "no 3D clash/anchorage recomputation artifact is attached" in payload["reason"]


def test_panel_zone_clash_report_keeps_unattributed_validated_rows_explicit_for_mixed_provenance_bridge(
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {
                "constructability_score": 0.24,
                "detailing_complexity_score": 0.41,
            },
            "rows_head": [
                {
                    "member_id": "B601",
                    "constructability_score": 0.19,
                    "anchorage_complexity": 0.66,
                    "detailing_violation_ratio": 0.44,
                }
            ],
        },
    )
    pbd = tmp_path / "pbd_review_package_report.json"
    _write_json(pbd, {"contract_pass": True})
    clash = tmp_path / "panel_zone_clash_artifact.json"
    _write_json(
        clash,
        {
            "contract_pass": True,
            "summary": {
                "verification_mode": "topology_projected_midas_panel_bridge",
                "verification_tier": "topology_projected_3d_clash_and_anchorage_bridge",
                "required_sources_complete": True,
                "source_contract_mode": "topology_projected_3d_clash_and_anchorage_bridge",
                "low_constructability_row_count": 3,
            },
            "source_provenance": {
                "topology_capable_input": True,
                "required_sources_complete": True,
                "topology_projected_bridge_complete": True,
                "solver_verified_bridge_complete": False,
                "verification_tier": "topology_projected_3d_clash_and_anchorage_bridge",
                "missing_required_sources": [],
                "source_valid_row_counts": {
                    "panel_zone_joint_geometry_3d": 2,
                    "panel_zone_rebar_anchorage_3d": 1,
                },
                "source_upstream_verification_tiers": {
                    "panel_zone_joint_geometry_3d": "solver_verified_direct_geometry_source",
                    "panel_zone_rebar_anchorage_3d": "panel_zone_topology_projected_validated_source",
                    "panel_zone_clash_verification_3d": "panel_zone_topology_projected_validated_source",
                },
                "validated_source_row_count_total": 9,
                "validated_source_overlap_member_count_min": 3,
            },
            "artifacts": {"interference_row_count": 3},
        },
    )
    out = tmp_path / "panel_zone_clash_report.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_clash_report.py",
            "--design-optimization-dataset",
            str(dataset),
            "--pbd-review-package",
            str(pbd),
            "--panel-zone-clash-artifact",
            str(clash),
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
    assert payload["summary"]["panel_zone_external_validation_pending"] is True
    assert payload["summary"]["panel_zone_external_validation_status_label"] == "mixed_exact_fallback_gap"
    assert payload["summary"]["panel_zone_external_validation_exact_source_count"] == 1
    assert payload["summary"]["panel_zone_external_validation_fallback_source_count"] == 2
    assert payload["summary"]["panel_zone_external_validation_exact_validated_row_count"] == 2
    assert payload["summary"]["panel_zone_external_validation_fallback_validated_row_count"] == 1
    assert payload["summary"]["panel_zone_external_validation_unattributed_validated_row_count"] == 6
    assert (
        payload["summary"]["panel_zone_external_validation_provenance_summary_label"]
        == "validated_sources=3/3 | exact_sources=1/3 | fallback_sources=2/3 | missing_sources=0/3 | validated_members=3/3 | exact_members=0/3 | fallback_members=0/3 | exact_rows=2/9 | fallback_rows=1/9 | unattributed_rows=6/9"
    )


def test_panel_zone_clash_report_passes_with_3d_clash_artifact(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {
                "constructability_score": 0.41,
                "detailing_complexity_score": 0.48,
            },
            "rows_head": [
                {
                    "member_id": "J201",
                    "constructability_score": 0.18,
                    "anchorage_complexity": 0.81,
                    "detailing_violation_ratio": 0.52,
                },
                {
                    "member_id": "J202",
                    "constructability_score": 0.34,
                    "anchorage_complexity": 0.66,
                    "detailing_violation_ratio": 0.25,
                },
            ],
        },
    )
    pbd = tmp_path / "pbd_review_package_report.json"
    _write_json(pbd, {"contract_pass": True})
    clash = tmp_path / "panel_zone_clash_artifact.json"
    _write_json(
        clash,
        {
            "contract_pass": True,
            "artifacts": {"interference_row_count": 3},
            "summary": {
                "interference_count": 3,
                "verification_mode": "3d_verified",
            },
        },
    )
    out = tmp_path / "panel_zone_clash_report.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_clash_report.py",
            "--design-optimization-dataset",
            str(dataset),
            "--pbd-review-package",
            str(pbd),
            "--panel-zone-clash-artifact",
            str(clash),
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
    assert payload["summary"]["constructability_mode"] == "panel_zone_3d_clash_and_anchorage_verified"
    assert payload["summary"]["sample_member_count"] == 2
    assert payload["summary"]["constructability_low_outlier_count"] == 1
    assert payload["summary"]["panel_zone_clash_row_count"] == 3
    assert payload["summary"]["panel_zone_external_validation_advisory_only"] is False
    assert payload["summary"]["panel_zone_external_validation_release_blocking"] is False
    assert payload["summary"]["panel_zone_external_validation_status_label"] == "verified"
    assert payload["summary"]["panel_zone_external_validation_artifact_closed"] is True
    assert payload["summary"]["panel_zone_external_validation_closure_mode"] == "closed_exact_validated"
    assert payload["summary"]["panel_zone_external_validation_source_count"] == 3
    assert payload["summary"]["panel_zone_external_validation_exact_source_count"] == 3
    assert payload["summary"]["panel_zone_external_validation_fallback_source_count"] == 0
    assert payload["summary"]["panel_zone_external_validation_exact_validated_row_count"] == 0
    assert payload["summary"]["panel_zone_external_validation_unattributed_validated_row_count"] == 0
    assert payload["summary"]["panel_zone_external_validation_local_closure_state"] == "closed_with_solver_verified_artifact"
    assert payload["summary"]["panel_zone_external_validation_local_closure_label"] == "Local closeout: closed by attached solver-verified 3D artifact."
    assert "status=verified" in payload["summary"]["panel_zone_external_validation_closing_summary_label"]
    assert payload["summary"]["panel_zone_external_validation_required_evidence"] == "none"
    assert "boundary=solver_verified" in payload["summary"]["panel_zone_external_validation_summary_line"]
    assert "artifact_closed=True" in payload["summary"]["panel_zone_external_validation_summary_line"]
    assert "closure_mode=closed_exact_validated" in payload["summary"]["panel_zone_external_validation_summary_line"]
    assert payload["checks"]["panel_zone_clash_artifact_present"] is True
    assert payload["checks"]["panel_zone_clash_artifact_contract_pass"] is True
    assert payload["checks"]["panel_zone_clash_artifact_3d_verified"] is True
    assert payload["checks"]["panel_zone_external_validation_advisory_only"] is False
    assert payload["checks"]["panel_zone_external_validation_release_blocking"] is False
