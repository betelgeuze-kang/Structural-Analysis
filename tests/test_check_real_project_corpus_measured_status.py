from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "implementation/phase1/check_real_project_corpus_measured_status.py"
SPEC = importlib.util.spec_from_file_location("check_real_project_corpus_measured_status", SCRIPT_PATH)
assert SPEC is not None
measured_status = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(measured_status)


REQUIRED_METADATA_FIELDS = (
    "generated_at",
    "source_commit_sha",
    "engine_version",
    "input_checksums",
    "reused_evidence",
    "reuse_policy",
)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _measured_row(idx: int, fmt: str = "mgt") -> dict[str, object]:
    return {
        "artifact_status": "measured_local_artifact_attached",
        "checksum_status_or_withheld_reason": f"{idx:064x}",
        "stable_row_pointer": f"row-{idx}",
        "manual_review_status": "pending_artifact_level_review",
        "release_eligibility": "blocked_pending_artifact_review",
        "release_surface_allowed": False,
        "parser_contract": {
            "byte_count": 100 + idx,
            "format": fmt,
            "measured_local_artifact": True,
            "source_file": f"case-{idx}.json",
        },
    }


def test_real_project_measured_status_blocks_until_peer_values_are_present(tmp_path: Path) -> None:
    row_provenance = _write_json(
        tmp_path / "rows.json",
        {
            "source_provenance_rows": [
                *[_measured_row(idx, "mgt") for idx in range(5)],
                *[_measured_row(idx, "ifc") for idx in range(5, 10)],
            ]
        },
    )
    peer_metric_records = _write_json(
        tmp_path / "peer.json",
        {
            "metric_records": [
                {"metric_group": "period", "value": None},
                {"metric_group": "base_shear", "value": None},
                {"metric_group": "story_drift", "value": None},
                {"metric_group": "nonlinear_response", "value": None},
                {"metric_group": "citation", "value": "citation"},
            ]
        },
    )

    payload = measured_status.build_status(
        row_provenance_path=row_provenance,
        peer_metric_records_path=peer_metric_records,
    )

    assert payload["contract_pass"] is False
    assert payload["checks"]["measured_provenance_rows_pass"] is True
    assert payload["checks"]["koneps_measured_format_count_pass"] is True
    assert payload["checks"]["peer_metric_bearing_groups_pass"] is False
    assert payload["summary"]["peer_metric_groups_with_value_count"] == 1
    assert payload["blockers"] == ["peer_metric_bearing_groups_pass"]


def test_real_project_measured_status_passes_complete_exit_criteria(tmp_path: Path) -> None:
    row_provenance = _write_json(
        tmp_path / "rows.json",
        {
            "source_provenance_rows": [
                *[_measured_row(idx, "mgt") for idx in range(5)],
                *[_measured_row(idx, "ifc") for idx in range(5, 10)],
            ]
        },
    )
    peer_metric_records = _write_json(
        tmp_path / "peer.json",
        {
            "metric_records": [
                {"metric_group": "period", "value": 1.2},
                {"metric_group": "base_shear", "value": 123.0},
                {"metric_group": "story_drift", "value": 0.01},
                {"metric_group": "nonlinear_response", "value": "converged"},
                {"metric_group": "citation", "value": "citation"},
            ]
        },
    )

    payload = measured_status.build_status(
        row_provenance_path=row_provenance,
        peer_metric_records_path=peer_metric_records,
    )

    assert payload["contract_pass"] is True
    assert payload["blockers"] == []
    assert payload["checks"]["checksum_or_withheld_coverage_pass"] is True
    assert payload["checks"]["stable_row_pointer_unique_pass"] is True
    assert payload["checks"]["measured_parser_contract_pass"] is True
    assert payload["summary"]["measured_parser_contract_valid_count"] == 10


def test_real_project_measured_status_blocks_placeholder_like_measured_rows(
    tmp_path: Path,
) -> None:
    bad_row = _measured_row(0, "mgt")
    bad_row["checksum_status_or_withheld_reason"] = "TODO"
    bad_row["stable_row_pointer"] = "duplicate-row"
    bad_row["parser_contract"] = {"format": "mgt"}
    duplicate_row = _measured_row(1, "ifc")
    duplicate_row["stable_row_pointer"] = "duplicate-row"
    row_provenance = _write_json(
        tmp_path / "rows.json",
        {
            "source_provenance_rows": [
                bad_row,
                duplicate_row,
                *[_measured_row(idx, "mgt") for idx in range(2, 6)],
                *[_measured_row(idx, "ifc") for idx in range(6, 10)],
            ]
        },
    )
    peer_metric_records = _write_json(
        tmp_path / "peer.json",
        {
            "metric_records": [
                {"metric_group": "period", "value": 1.2},
                {"metric_group": "base_shear", "value": 123.0},
                {"metric_group": "story_drift", "value": 0.01},
                {"metric_group": "nonlinear_response", "value": "converged"},
                {"metric_group": "citation", "value": "citation"},
            ]
        },
    )

    payload = measured_status.build_status(
        row_provenance_path=row_provenance,
        peer_metric_records_path=peer_metric_records,
    )

    assert payload["contract_pass"] is False
    assert payload["checks"]["checksum_or_withheld_coverage_pass"] is False
    assert payload["checks"]["stable_row_pointer_unique_pass"] is False
    assert payload["checks"]["measured_parser_contract_pass"] is False
    assert payload["summary"]["duplicate_measured_stable_pointers"] == ["duplicate-row"]
    assert "checksum_or_withheld_coverage_pass" in payload["blockers"]
    assert "stable_row_pointer_unique_pass" in payload["blockers"]
    assert "measured_parser_contract_pass" in payload["blockers"]


def test_real_project_measured_status_exposes_release_evidence_metadata(tmp_path: Path) -> None:
    row_provenance = _write_json(
        tmp_path / "rows.json",
        {
            "source_provenance_rows": [
                *[_measured_row(idx, "mgt") for idx in range(5)],
                *[_measured_row(idx, "ifc") for idx in range(5, 10)],
            ]
        },
    )
    peer_metric_records = _write_json(
        tmp_path / "peer.json",
        {
            "metric_records": [
                {"metric_group": "period", "value": 1.2},
                {"metric_group": "base_shear", "value": 123.0},
                {"metric_group": "story_drift", "value": 0.01},
                {"metric_group": "nonlinear_response", "value": "converged"},
                {"metric_group": "citation", "value": "citation"},
            ]
        },
    )

    payload = measured_status.build_status(
        row_provenance_path=row_provenance,
        peer_metric_records_path=peer_metric_records,
    )

    for field in REQUIRED_METADATA_FIELDS:
        assert field in payload, f"missing release evidence metadata field: {field}"
    assert isinstance(payload["input_checksums"], dict)
    assert str(row_provenance) in payload["input_checksums"]
    assert str(peer_metric_records) in payload["input_checksums"]
    assert payload["reused_evidence"] is True
    assert payload["reuse_policy"]
    assert payload["generated_at"]


def test_real_project_measured_status_metadata_present_even_when_blocked(tmp_path: Path) -> None:
    row_provenance = _write_json(tmp_path / "rows.json", {"source_provenance_rows": []})
    peer_metric_records = _write_json(
        tmp_path / "peer.json",
        {"metric_records": [{"metric_group": "citation", "value": "citation"}]},
    )

    payload = measured_status.build_status(
        row_provenance_path=row_provenance,
        peer_metric_records_path=peer_metric_records,
    )

    assert payload["contract_pass"] is False
    for field in REQUIRED_METADATA_FIELDS:
        assert field in payload, f"missing release evidence metadata field: {field}"
