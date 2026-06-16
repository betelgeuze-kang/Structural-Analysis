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


def _p0_status(path: Path, *, p0_closed: bool = False, core_evidence_closed: bool = True) -> Path:
    return _write_json(
        path,
        {
            "schema_version": "p0-closure-status.v1",
            "p0_closed": p0_closed,
            "core_evidence_closed": core_evidence_closed,
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


def _row_provenance(
    path: Path,
    *,
    include_midas_kds: bool = True,
    include_midas_kds_row: bool = True,
    midas_kds_exact_geometry_bridge_pass_count: int = 3,
) -> Path:
    summary = {
        "row_count": 3 if include_midas_kds else 2,
        "required_source_families_present": True,
        "all_rows_have_required_fields": True,
        "release_surface_allowed_count": 0,
    }
    if include_midas_kds:
        summary.update(
            {
                "midas_kds_validation_present": True,
                "midas_kds_validation_artifact_count": 3,
                "midas_kds_exact_geometry_bridge_pass_count": midas_kds_exact_geometry_bridge_pass_count,
                "midas_kds_exact_row_provenance_count": 3168,
                "midas_kds_review_row_count": 3168,
            }
        )
    source_rows = [
        {"source_id": "koneps_turnkey_design_docs", "release_surface_allowed": False},
        {"source_id": "peer_tbi_tall_buildings", "release_surface_allowed": False},
    ]
    if include_midas_kds and include_midas_kds_row:
        source_rows.append(
            {
                "source_id": "midas_kds_geometry_bridge_validation",
                "release_surface_allowed": False,
                "parser_contract": {
                    "contract_pass": True,
                    "artifact_count": 3,
                    "exact_geometry_bridge_pass_count": midas_kds_exact_geometry_bridge_pass_count,
                    "review_row_count_total": 3168,
                    "exact_mapped_row_provenance_count_total": 3168,
                },
            }
        )
    return _write_json(
        path,
        {
            "schema_version": "real_project_row_provenance_report.v1",
            "contract_pass": True,
            "row_provenance_coverage": 1.0,
            "raw_redistribution_default_blocked": True,
            "summary": summary,
            "source_provenance_rows": source_rows,
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

    assert status["p0_core_evidence_closed"] is True
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


def test_p1_readiness_treats_missing_generated_report_as_blocked(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    missing_row_provenance = tmp_path / "missing" / "real_project_row_provenance_report.json"
    paths["row_provenance"] = missing_row_provenance

    status = check_p1_readiness.build_status(**paths)

    assert status["p1_inputs_ready"] is False
    assert status["gates"][4]["label"] == "Real-project row provenance"
    assert status["gates"][4]["status"] == "blocked"


def test_p1_readiness_requires_midas_kds_row_provenance_evidence(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths["row_provenance"] = _row_provenance(tmp_path / "row.json", include_midas_kds=False)

    status = check_p1_readiness.build_status(**paths)
    row_gate = status["gates"][4]

    assert status["p1_inputs_ready"] is False
    assert row_gate["status"] == "blocked"
    assert row_gate["midas_kds_validation_present"] is False
    assert row_gate["midas_kds_exact_row_provenance_count"] == 0


def test_p1_readiness_surfaces_midas_kds_row_provenance_breadth(tmp_path: Path) -> None:
    status = check_p1_readiness.build_status(**_paths(tmp_path))
    row_gate = status["gates"][4]

    assert status["p1_inputs_ready"] is True
    assert row_gate["midas_kds_validation_present"] is True
    assert row_gate["midas_kds_validation_artifact_count"] == 3
    assert row_gate["midas_kds_exact_geometry_bridge_pass_count"] == 3
    assert row_gate["midas_kds_exact_row_provenance_count"] == 3168
    assert row_gate["midas_kds_review_row_count"] == 3168


def test_p1_readiness_blocks_when_midas_kds_exact_artifact_breadth_is_incomplete(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths["row_provenance"] = _row_provenance(
        tmp_path / "row.json",
        midas_kds_exact_geometry_bridge_pass_count=2,
    )

    status = check_p1_readiness.build_status(**paths)
    row_gate = status["gates"][4]

    assert status["p1_inputs_ready"] is False
    assert row_gate["status"] == "blocked"
    assert row_gate["midas_kds_exact_geometry_bridge_pass_count"] == 2


def test_p1_readiness_rejects_summary_only_midas_kds_evidence_claim(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths["row_provenance"] = _row_provenance(
        tmp_path / "row.json",
        include_midas_kds=True,
        include_midas_kds_row=False,
    )

    status = check_p1_readiness.build_status(**paths)
    row_gate = status["gates"][4]

    assert status["p1_inputs_ready"] is False
    assert row_gate["status"] == "blocked"
    assert row_gate["midas_kds_validation_row_present"] is False


def test_p1_readiness_passes_publication_evidence_index_when_building_p0(
    tmp_path: Path,
    monkeypatch,
) -> None:
    paths = _paths(tmp_path)
    paths.pop("p0_status")
    publication_index = tmp_path / "release-publication-evidence-index.json"

    def fake_build_p0_status(*, publication_evidence_index=None, **_kwargs):
        assert publication_evidence_index == publication_index
        return {
            "schema_version": "p0-closure-status.v1",
            "p0_closed": True,
            "core_evidence_closed": True,
            "release_publication_closed": True,
            "publication_evidence_index": str(publication_index),
        }

    monkeypatch.setattr(check_p1_readiness, "build_p0_status", fake_build_p0_status)

    status = check_p1_readiness.build_status(publication_evidence_index=publication_index, **paths)

    assert status["p1_execution_unblocked"] is True
    assert status["publication_evidence_index"] == str(publication_index)


def test_p1_readiness_fail_core_open_ignores_release_publication_blocker(
    tmp_path: Path,
    capsys,
) -> None:
    paths = _paths(tmp_path)

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
            "--json",
            "--fail-core-open",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"p0_core_evidence_closed": true' in captured.out
    assert '"p1_execution_unblocked": false' in captured.out


def test_p1_readiness_fail_core_open_fails_when_core_evidence_is_open(
    tmp_path: Path,
    capsys,
) -> None:
    paths = _paths(tmp_path)
    paths["p0_status"] = _p0_status(tmp_path / "p0.json", core_evidence_closed=False)

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
            "--json",
            "--fail-core-open",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert '"p0_core_evidence_closed": false' in captured.out


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
    markdown = out_md.read_text(encoding="utf-8")
    assert exit_code == 1
    assert "P1 Readiness Status" in captured.out
    assert "P1 work slice: `quality/fallback/benchmark breadth`" in captured.out
    assert "P1 Readiness Status" in markdown
    assert "P1 work slice: `quality/fallback/benchmark breadth`" in markdown
