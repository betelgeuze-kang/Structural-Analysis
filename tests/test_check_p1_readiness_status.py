from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "check_p1_readiness_status.py"
SPEC = importlib.util.spec_from_file_location("check_p1_readiness_status", SCRIPT_PATH)
assert SPEC is not None
check_p1_readiness = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(check_p1_readiness)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _p0_status(path: Path, *, p0_closed: bool = False) -> Path:
    return _write_json(
        path,
        {
            "schema_version": "p0-closure-status.v1",
            "p0_closed": p0_closed,
            "core_evidence_closed": True,
            "release_publication_closed": p0_closed,
        },
    )


def _open_data_plan(path: Path, *, ok: bool = True) -> Path:
    return _write_json(
        path,
        {
            "schema_version": "open_data_artifact_restore_plan.v1",
            "ok": ok,
            "summary": {
                "artifact_count": 8,
                "already_restored": 8 if ok else 7,
                "cache_ready": 0,
                "blocked": 0 if ok else 1,
                "total_bytes": 293146888,
            },
        },
    )


def _coverage_matrix(path: Path) -> Path:
    return _write_json(
        path,
        {
            "schema_version": "real_project_parser_coverage_matrix.v1",
            "contract_pass": True,
            "summary": {
                "source_family_count": 2,
                "koneps_parser_target_count": 7,
                "peer_tbi_benchmark_metric_target_count": 5,
                "raw_redistribution_auto_allowed_after_p0": False,
            },
        },
    )


def _peer_records(path: Path) -> Path:
    return _write_json(
        path,
        {
            "schema_version": "peer_tbi_benchmark_metric_records.v1",
            "contract_pass": True,
            "summary": {
                "metric_record_count": 5,
                "required_metric_group_count": 5,
                "recorded_metric_group_count": 5,
                "raw_redistribution_auto_allowed": False,
            },
        },
    )


def _row_provenance(path: Path) -> Path:
    return _write_json(
        path,
        {
            "schema_version": "real_project_row_provenance_report.v1",
            "contract_pass": True,
            "row_provenance_coverage": 1.0,
            "raw_redistribution_default_blocked": True,
            "summary": {
                "row_count": 2,
                "required_source_families_present": True,
                "all_rows_have_required_fields": True,
                "release_surface_allowed_count": 0,
            },
        },
    )


def _paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "p0_status": _p0_status(tmp_path / "p0.json"),
        "open_data_restore_plan": _open_data_plan(tmp_path / "open_data.json"),
        "coverage_matrix": _coverage_matrix(tmp_path / "coverage.json"),
        "peer_metric_records": _peer_records(tmp_path / "peer.json"),
        "row_provenance": _row_provenance(tmp_path / "row.json"),
    }


def test_p1_readiness_separates_inputs_ready_from_p0_release_blocker(tmp_path: Path) -> None:
    status = check_p1_readiness.build_status(**_paths(tmp_path))

    assert status["p1_inputs_ready"] is True
    assert status["p1_execution_unblocked"] is False
    assert status["p0_release_blocker"] is True
    assert status["next_action"] == "close P0-1 release publication before starting P1 execution"


def test_p1_readiness_closes_when_p0_and_inputs_are_ready(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths["p0_status"] = _p0_status(tmp_path / "p0.json", p0_closed=True)

    status = check_p1_readiness.build_status(**paths)

    assert status["p1_inputs_ready"] is True
    assert status["p1_execution_unblocked"] is True
    assert status["next_action"] == "start P1 quality/fallback/benchmark breadth"


def test_p1_readiness_blocks_on_missing_open_data_artifact(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths["open_data_restore_plan"] = _open_data_plan(tmp_path / "open_data.json", ok=False)

    status = check_p1_readiness.build_status(**paths)

    assert status["p1_inputs_ready"] is False
    assert status["gates"][1]["status"] == "blocked"


def test_cli_writes_markdown_and_fails_when_execution_blocked(tmp_path: Path, capsys) -> None:
    paths = _paths(tmp_path)
    out_md = tmp_path / "p1.md"

    exit_code = check_p1_readiness.main(
        [
            "--p0-status",
            str(paths["p0_status"]),
            "--open-data-restore-plan",
            str(paths["open_data_restore_plan"]),
            "--coverage-matrix",
            str(paths["coverage_matrix"]),
            "--peer-metric-records",
            str(paths["peer_metric_records"]),
            "--row-provenance",
            str(paths["row_provenance"]),
            "--out-md",
            str(out_md),
            "--fail-blocked",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "P1 Readiness Status" in captured.out
    assert "P1 Readiness Status" in out_md.read_text(encoding="utf-8")
