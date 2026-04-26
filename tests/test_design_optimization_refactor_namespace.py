from design_optimization import (
    DESIGN_OPT_RELEASE_DIR,
    ENTRYPOINTS,
    EXTERNAL_FULL_ARTIFACTS_DESIGN_OPT,
    EXTERNAL_LIGHT_ARTIFACTS_DESIGN_OPT,
    artifact_path,
    entrypoint_group_rows,
    entrypoint_status_rows,
    entrypoint_rows,
    load_design_opt_reports,
    write_blocked_action_artifacts,
    write_candidate_explain_artifacts,
    write_cost_reduction_support_artifacts,
    write_design_optimization_report,
    write_design_change_artifacts,
    write_stage_report,
)
from design_optimization.report_builder import build_report_payload, build_stage_report_payload


def test_artifact_path_uses_design_opt_release_dir() -> None:
    target = artifact_path("design_optimization_budgeted_report.json")
    assert target.startswith(str(DESIGN_OPT_RELEASE_DIR))
    assert target.endswith("design_optimization_budgeted_report.json")


def test_entrypoints_registry_has_expected_keys() -> None:
    assert "budgeted" in ENTRYPOINTS
    assert "cost_reduction" in ENTRYPOINTS
    assert "ablation" in ENTRYPOINTS
    rows = entrypoint_rows()
    assert len(rows) >= 6
    assert any(row["name"] == "budgeted" for row in rows)


def test_external_design_opt_artifact_groups_are_nonempty() -> None:
    assert EXTERNAL_FULL_ARTIFACTS_DESIGN_OPT
    assert EXTERNAL_LIGHT_ARTIFACTS_DESIGN_OPT
    assert any(path.endswith("design_optimization_ablation_report.json") for path in EXTERNAL_FULL_ARTIFACTS_DESIGN_OPT)
    assert any(path.endswith("design_optimization_cost_reduction_report.json") for path in EXTERNAL_LIGHT_ARTIFACTS_DESIGN_OPT)


def test_entrypoint_primary_reports_are_absolute_in_repo() -> None:
    rows = entrypoint_rows()
    for row in rows:
        assert row["primary_report"].startswith(str(DESIGN_OPT_RELEASE_DIR))


def test_entrypoint_status_rows_match_registry_shape() -> None:
    rows = entrypoint_status_rows(load_design_opt_reports())
    assert len(rows) == len(ENTRYPOINTS)
    assert all("report_exists" in row for row in rows)


def test_entrypoint_group_rows_cover_registry_rows() -> None:
    status_rows = entrypoint_status_rows(load_design_opt_reports())
    grouped = entrypoint_group_rows(status_rows)
    assert grouped
    assert sum(int(row["entrypoint_count"]) for row in grouped) == len(status_rows)
    assert any(row["group"] == "stage_a" for row in grouped)
    assert any(row["group"] == "profile" for row in grouped)


def test_report_builder_emits_common_design_opt_shape() -> None:
    payload = build_report_payload(
        run_id="unit-test",
        summary={"solver_feasible_final": True},
        inputs={"budget": "low"},
        artifacts={"report_out": "x.json"},
        contract_pass=True,
        reason_code="PASS",
        reason="ok",
    )
    assert payload["report_family"] == "design_optimization"
    assert payload["summary_schema_version"] == "2.0"
    assert payload["summary"]["solver_feasible_final"] is True


def test_namespace_exports_cost_reduction_writer() -> None:
    assert callable(write_cost_reduction_support_artifacts)
    assert callable(write_design_optimization_report)
    assert callable(write_design_change_artifacts)
    assert callable(write_blocked_action_artifacts)
    assert callable(write_candidate_explain_artifacts)


def test_namespace_exports_stage_report_writer(tmp_path) -> None:
    target = tmp_path / "stage_report.json"
    payload = write_stage_report(
        target,
        run_id="stage-write-unit-test",
        summary={"stage": "stage_a"},
        contract_pass=True,
        reason_code="PASS",
        reason="ok",
        head_blocks={"accepted_head": [{"i": idx} for idx in range(40)]},
    )
    assert target.exists()
    assert payload["report_family"] == "design_optimization"
    assert len(payload["accepted_head"]) == 32


def test_namespace_exports_main_report_writer(tmp_path) -> None:
    target = tmp_path / "report.json"
    payload = write_design_optimization_report(
        target,
        run_id="main-write-unit-test",
        summary={"solver_feasible_final": True},
        contract_pass=True,
        reason_code="PASS",
        reason="ok",
        extra={"accepted_head": [{"i": 1}]},
    )
    assert target.exists()
    assert payload["report_family"] == "design_optimization"
    assert payload["summary"]["solver_feasible_final"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["accepted_head"] == [{"i": 1}]


def test_stage_report_builder_limits_head_rows() -> None:
    payload = build_stage_report_payload(
        run_id="stage-unit-test",
        summary={"stage": "stage_a"},
        contract_pass=True,
        reason_code="PASS",
        reason="ok",
        head_blocks={"accepted_head": [{"i": idx} for idx in range(40)]},
    )
    assert len(payload["accepted_head"]) == 32
