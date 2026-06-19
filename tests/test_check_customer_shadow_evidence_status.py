from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent / "implementation/phase1/check_customer_shadow_evidence_status.py"
)
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "implementation/phase1/customer_shadow_evidence.schema.json"
SPEC = importlib.util.spec_from_file_location("check_customer_shadow_evidence_status", SCRIPT_PATH)
assert SPEC is not None
status_gate = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(status_gate)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _case(idx: int, *, case_id: str | None = None) -> dict[str, object]:
    return {
        "case_id": case_id or f"shadow-case-{idx:03d}",
        "project_status": "completed",
        "structure_family": "wall-frame",
        "reference_solver": "MIDAS",
        "reference_solver_version": "v1",
        "reference_output_checksum": f"sha256:{idx:064d}",
        "our_engine_commit": "b7e0b72a",
        "delta_metrics": {"max_relative_error_pct": 2.1},
        "residual_metrics": {"normalized_equilibrium_residual": 0.0004},
        "reviewer_decision": "REVIEW",
        "known_limitations": ["customer retains raw data"],
        "reproduce_bundle_id": f"bundle-{idx:03d}",
        "raw_data_retained_by_customer": True,
        "redistribution_allowed": False,
    }


def test_customer_shadow_status_blocks_when_no_evidence_dir(tmp_path: Path) -> None:
    payload = status_gate.build_status(
        evidence_dir=tmp_path / "missing",
        schema_path=SCHEMA_PATH,
    )

    assert payload["contract_pass"] is False
    assert payload["summary"]["completed_shadow_case_count"] == 0
    assert payload["checks"]["min_completed_shadow_cases_pass"] is False
    assert payload["blockers"] == [
        "evidence_directory_missing",
        "completed_shadow_case_count_below_minimum",
    ]


def test_customer_shadow_status_passes_with_three_valid_completed_cases(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "shadow"
    for idx in range(3):
        _write_json(evidence_dir / f"case-{idx}.json", _case(idx))

    payload = status_gate.build_status(
        evidence_dir=evidence_dir,
        schema_path=SCHEMA_PATH,
        min_completed_cases=3,
        target_completed_cases=5,
    )

    assert payload["contract_pass"] is True
    assert payload["summary"]["evidence_file_count"] == 3
    assert payload["summary"]["valid_evidence_file_count"] == 3
    assert payload["summary"]["completed_shadow_case_count"] == 3
    assert payload["checks"]["min_completed_shadow_cases_pass"] is True
    assert payload["checks"]["target_completed_shadow_cases_pass"] is False
    assert payload["blockers"] == []


def test_customer_shadow_status_blocks_invalid_and_duplicate_cases(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "shadow"
    _write_json(evidence_dir / "a.json", _case(1, case_id="dup"))
    _write_json(evidence_dir / "b.json", _case(2, case_id="dup"))
    invalid = _case(3)
    invalid["redistribution_allowed"] = True
    _write_json(evidence_dir / "invalid.json", invalid)

    payload = status_gate.build_status(
        evidence_dir=evidence_dir,
        schema_path=SCHEMA_PATH,
    )

    assert payload["contract_pass"] is False
    assert payload["summary"]["completed_shadow_case_count"] == 2
    assert payload["summary"]["invalid_evidence_file_count"] == 1
    assert payload["summary"]["duplicate_completed_shadow_case_ids"] == ["dup"]
    assert "completed_shadow_case_count_below_minimum" in payload["blockers"]
    assert "invalid_customer_shadow_evidence_files_present" in payload["blockers"]
    assert "duplicate_completed_shadow_case_ids" in payload["blockers"]
    assert "raw_data_policy_violation" in payload["blockers"]
