"""Experimental RC design comparison: one real small study plus failure contracts."""

from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path

import pytest

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.io.neutral.loader import load_neutral_json


def inputs():
    return dict(
        baseline=load_neutral_json(
            Path("examples/public_rc_fiber_frame_l_frame_material_history.json")
        ),
        candidates=(
            design.FiberFrameDesignCandidate(
                "wider", (design.FiberFrameSectionChange("RC1", width_m=0.5),)
            ),
        ),
        request=BoundedRCFiberDirectControlRequest(
            7, (-1e-6, -2e-6, -1.5e-6), allow_reversals=True, maximum_reversals=1
        ),
        history_limits=design.FiberFrameHistoryLimits(1, 1),
        material_limits=design.FiberFrameMaterialHistoryLimits(1, 1, 1),
        prices=design.FiberFrameMaterialPrices(
            100, 1, "KRW", "2026-09-09", "synthetic test only"
        ),
        source_revision="a" * 40,
    )


@pytest.fixture(scope="module")
def actual(tmp_path_factory):
    root = tmp_path_factory.mktemp("rc-control-design") / "study"
    args = inputs()
    before = args["baseline"].canonical_payload()
    args["candidates"] += (
        design.FiberFrameDesignCandidate(
            "invalid", (design.FiberFrameSectionChange("missing", width_m=0.5),)
        ),
    )
    report = study.compare_rc_control_designs(**args, output_directory=root)
    assert before == args["baseline"].canonical_payload()
    return report, root


def test_actual_full_reference_reanalysis_and_common_quantities(actual):
    report, root = actual
    assert report["candidate_denominator"] == 3
    assert report["verified_count"] == 2
    assert report["status"] == "incomplete"
    assert report["selected_candidate_id"] == "baseline"
    baseline, wider, invalid = report["rows"]
    assert invalid["status"] == "invalid_candidate"
    assert invalid["invocations"] == []
    assert wider["quantity_delta"]["gross_concrete_volume_m3"] == pytest.approx(0.21)
    assert wider["quantity_delta"]["longitudinal_rebar_mass_kg"] == 0
    assert wider["scoped_estimate_reduction"] == pytest.approx(-21)
    assert (
        baseline["material_estimate"]["price_table_hash"]
        == wider["material_estimate"]["price_table_hash"]
    )
    for row in (baseline, wider):
        assert row["full_reference_verification_pass"] is True
        assert row["performance"]["accepted_epoch_count"] == 3
        assert [i["phase"] for i in row["invocations"]] == ["analysis", "verification"]
        assert sum(i["work"]["attempted_step_count"] for i in row["invocations"]) == 6
        assert all(not i["unknown_execution_work"] for i in row["invocations"])
        result = json.loads((root / row["artifacts"]["result"]["path"]).read_bytes())
        assert result["request"]["restart_input_sha256"] is None
        assert result["path"]["initial_checkpoint"]["epoch"] == 0
    assert (
        baseline["artifacts"]["model"]["sha256"]
        != wider["artifacts"]["model"]["sha256"]
    )


def test_original_artifacts_and_report_are_bound(actual):
    report, root = actual
    for row in report["rows"]:
        for reference in row["artifacts"].values():
            raw = (root / reference["path"]).read_bytes()
            assert len(raw) == reference["byte_length"]
            assert "sha256:" + hashlib.sha256(raw).hexdigest() == reference["sha256"]
        for invocation in row["invocations"]:
            assert invocation["wall_ns"] >= 0 and invocation["process_cpu_ns"] >= 0
            assert (
                root / row["candidate_id"] / f"{invocation['phase']}-started.json"
            ).is_file()
            assert (
                root / row["candidate_id"] / f"{invocation['phase']}-outcome.json"
            ).is_file()
    assert (
        study._sha(
            study._bytes({k: v for k, v in report.items() if k != "report_hash"})
        )
        == report["report_hash"]
    )
    assert report["claims"]["confirmed_currency_savings"] is False
    assert report["source_revision_is_attestation"] is False


def retained_api_doubles(actual, monkeypatch, *, reject=False, raises=False):
    """Decision plumbing only: replay saved artifacts, not new physical evidence."""
    report, root = actual
    records = {
        r["quantities"]["model_checksum"]: r
        for r in report["rows"]
        if r["full_reference_verification_pass"]
    }

    def analyze(model, targets, **kwargs):
        assert kwargs["restart"] is None
        row = records[model.canonical_model_checksum]
        return study.api.BoundedRCFiberDirectControlResult(
            (root / row["artifacts"]["result"]["path"]).read_bytes(),
            (root / row["artifacts"]["checkpoint"]["path"]).read_bytes(),
        )

    def verify(model, targets, **kwargs):
        assert kwargs["restart"] is None
        if raises:
            raise RuntimeError("injected verification error; work unavailable")
        row = records[model.canonical_model_checksum]
        value = json.loads(
            (root / row["artifacts"]["verification"]["path"]).read_bytes()
        )
        if reject:
            value["contract_pass"] = False
            value["errors"] = ["injected source mismatch"]
        return study.api.BoundedRCFiberDirectControlValidationReport(
            study._bytes(value)
        )

    monkeypatch.setattr(study.api, "analyze_bounded_rc_fiber_direct_control", analyze)
    monkeypatch.setattr(
        study.api, "validate_bounded_rc_fiber_direct_control_artifacts", verify
    )


def test_verified_designs_without_prices_never_select_cost_winner(
    actual, monkeypatch, tmp_path
):
    retained_api_doubles(actual, monkeypatch)
    args = inputs()
    args["prices"] = None
    report = study.compare_rc_control_designs(
        **args, output_directory=tmp_path / "study"
    )
    assert report["verified_count"] == 2
    assert report["selection_status"] == "prices_unavailable"
    assert report["selected_candidate_id"] is None


@pytest.mark.parametrize("raises", [False, True])
def test_verification_failure_preserves_originals_and_blocks_selection(
    actual, monkeypatch, tmp_path, raises
):
    retained_api_doubles(actual, monkeypatch, reject=not raises, raises=raises)
    report = study.compare_rc_control_designs(
        **inputs(), output_directory=tmp_path / "study"
    )
    assert report["verified_count"] == 0
    assert report["selected_candidate_id"] is None
    for row in report["rows"]:
        assert row["quantities"] is not None and row["material_estimate"] is not None
        assert {"result", "checkpoint", "verification_outcome"} <= row[
            "artifacts"
        ].keys()
        assert row["performance"] is None and row["selection_eligible"] is False
        if raises:
            assert row["invocations"][1]["work"] is None
            assert row["invocations"][1]["unknown_execution_work"] is True


def test_failed_full_history_screen_cannot_win_by_price(actual, monkeypatch, tmp_path):
    retained_api_doubles(actual, monkeypatch)
    args = inputs()
    args["history_limits"] = design.FiberFrameHistoryLimits(1e-8, 1)
    report = study.compare_rc_control_designs(
        **args, output_directory=tmp_path / "study"
    )
    assert report["verified_count"] == 2
    assert report["selected_candidate_id"] is None
    assert all(
        r["screens"]["maximum_translation_m"]["status"] == "fail"
        for r in report["rows"]
    )


def test_original_export_failure_aborts_publication(actual, monkeypatch, tmp_path):
    retained_api_doubles(actual, monkeypatch)
    save = study._save

    def fail_result(root, relative, data):
        if relative.endswith("/result.json"):
            raise OSError("injected full disk")
        return save(root, relative, data)

    monkeypatch.setattr(study, "_save", fail_result)
    root = tmp_path / "study"
    with pytest.raises(OSError, match="full disk"):
        study.compare_rc_control_designs(**inputs(), output_directory=root)
    assert not (root / "comparison.json").exists()
    assert (root / "baseline/analysis-started.json").is_file()


def test_terminal_screen_is_preserved(actual, monkeypatch, tmp_path):
    retained_api_doubles(actual, monkeypatch)
    report = study.compare_rc_control_designs(
        **inputs(),
        output_directory=tmp_path / "study",
        terminal_limits=design.FiberFrameTerminalLimits(1e-8, 1),
    )
    assert report["verified_count"] == 2
    assert report["selected_candidate_id"] is None
    assert all(
        row["screens"]["terminal_maximum_translation_m"]["status"] == "fail"
        for row in report["rows"]
    )


def test_cli_preserves_v3_constraints_and_writes_originals(
    actual, monkeypatch, tmp_path, capsys
):
    from structural_analysis.benchmark.rc_control_design_cli import main

    retained_api_doubles(actual, monkeypatch)
    args = inputs()
    request_path = tmp_path / "request.json"
    request_path.write_bytes(study._bytes(args["request"].to_dict()))
    experiment = {
        "schema_version": "rc-fiber-design-experiment.v3",
        "candidates": [asdict(c) for c in args["candidates"]],
        "prices": asdict(args["prices"]),
        "terminal_limits": {
            "maximum_translation_m": 1e-8,
            "maximum_absolute_fiber_strain": 1,
        },
        "history_limits": asdict(args["history_limits"]),
        "material_history_limits": asdict(args["material_limits"]),
    }
    experiment_path = tmp_path / "experiment.json"
    experiment_path.write_bytes(study._bytes(experiment))
    output = tmp_path / "study"
    assert (
        main(
            [
                "--model",
                "examples/public_rc_fiber_frame_l_frame_material_history.json",
                "--request",
                str(request_path),
                "--experiment",
                str(experiment_path),
                "--output",
                str(output),
                "--source-revision",
                args["source_revision"],
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["selected_candidate_id"] is None
    report = json.loads((output / "comparison.json").read_bytes())
    assert report["terminal_limits"] == experiment["terminal_limits"]
    assert report["verified_count"] == 2


@pytest.fixture
def no_solver(monkeypatch):
    def forbidden(*args, **kwargs):
        raise RuntimeError("injected analysis failure after entry; work unavailable")

    monkeypatch.setattr(study.api, "analyze_bounded_rc_fiber_direct_control", forbidden)


def test_analysis_failure_retains_quantities_denominator_and_unknown_work(
    tmp_path, no_solver
):
    report = study.compare_rc_control_designs(
        **inputs(), output_directory=tmp_path / "study"
    )
    assert report["candidate_denominator"] == 2
    assert report["selected_candidate_id"] is None
    for row in report["rows"]:
        assert row["status"] == "execution_error"
        assert row["quantities"] is not None and row["material_estimate"] is not None
        assert row["performance"] is None and row["screens"] is None
        assert row["invocations"][0]["work"] is None
        assert row["invocations"][0]["unknown_execution_work"] is True


def test_missing_prices_do_not_select_a_cost_winner(tmp_path, no_solver):
    args = inputs()
    args["prices"] = None
    report = study.compare_rc_control_designs(
        **args, output_directory=tmp_path / "study"
    )
    assert report["selection_status"] == "prices_unavailable"
    assert report["selected_candidate_id"] is None
    assert all(r["material_estimate"] is None for r in report["rows"])


@pytest.mark.parametrize(
    "change", ["source", "duplicate", "empty", "screens", "traversal"]
)
def test_invalid_requests_fail_before_creating_output(tmp_path, no_solver, change):
    args = inputs()
    if change == "source":
        args["source_revision"] = "unknown"
    if change == "duplicate":
        args["candidates"] *= 2
    if change == "empty":
        args["request"] = replace(args["request"], targets_m=())
    if change == "screens":
        args["history_limits"] = None
    if change == "traversal":
        object.__setattr__(args["candidates"][0], "candidate_id", "../escape")
    root = tmp_path / "study"
    with pytest.raises(ValueError):
        study.compare_rc_control_designs(**args, output_directory=root)
    assert not root.exists()


def test_existing_output_is_never_overwritten(tmp_path, no_solver):
    (tmp_path / "owner.txt").write_text("keep")
    with pytest.raises(FileExistsError):
        study.compare_rc_control_designs(**inputs(), output_directory=tmp_path)
    assert (tmp_path / "owner.txt").read_text() == "keep"


def test_history_screen_uses_peak_not_terminal_and_missing_family_is_unavailable():
    history = [
        {
            "load_factor": -0.2,
            "node_displacements": [{"UX_m": 3, "UY_m": 4, "UZ_m": 0}],
            "fiber_results": [
                {
                    "strain": -0.2,
                    "material_kind": "concrete",
                    "material_state": {
                        "tensile_damage": 0.8,
                        "compressive_damage": 0.3,
                    },
                }
            ],
        },
        {
            "load_factor": 0.1,
            "node_displacements": [{"UX_m": 0, "UY_m": 1, "UZ_m": 0}],
            "fiber_results": [
                {
                    "strain": 0.01,
                    "material_kind": "concrete",
                    "material_state": {"tensile_damage": 0.1, "compressive_damage": 0},
                }
            ],
        },
    ]
    performance = study._performance(history)
    assert performance["maximum_translation_m"] == 5
    assert performance["maximum_concrete_tensile_damage"] == 0.8
    screens = study._screens(
        performance,
        design.FiberFrameHistoryLimits(4, 1),
        design.FiberFrameMaterialHistoryLimits(0, 0.7, 1),
    )
    assert screens["maximum_translation_m"]["status"] == "fail"
    assert screens["maximum_concrete_tensile_damage"]["status"] == "fail"
    assert (
        screens["maximum_steel_accumulated_plastic_strain"]["status"] == "unavailable"
    )
