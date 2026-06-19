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


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _measured_row(idx: int, fmt: str = "mgt") -> dict[str, object]:
    return {
        "artifact_status": "measured_local_artifact_attached",
        "checksum_status_or_withheld_reason": f"sha256-{idx}",
        "stable_row_pointer": f"row-{idx}",
        "manual_review_status": "pending_artifact_level_review",
        "release_eligibility": "blocked_pending_artifact_review",
        "release_surface_allowed": False,
        "parser_contract": {"format": fmt},
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
