"""Report assembly contracts using explicit evaluation stubs, with no solver work."""

from copy import deepcopy
from pathlib import Path

import pytest

from structural_analysis.api.nonlinear_fiber_frame import PublicRCFiberFrameConfig
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.io.neutral.loader import load_neutral_json


CONFIG = PublicRCFiberFrameConfig(load_steps=2)
SOURCE = "a" * 40
PRICES = design.FiberFrameMaterialPrices(100.0, 1.0, "KRW", "2026-09-09", "test only")
TERMINAL = design.FiberFrameTerminalLimits(1.0, 1.0)
HISTORY = design.FiberFrameHistoryLimits(1.0, 1.0)
MATERIAL = design.FiberFrameMaterialHistoryLimits(1.0, 1.0, 1.0)
CANDIDATES = tuple(
    design.FiberFrameDesignCandidate(
        name, (design.FiberFrameSectionChange("RC1", width_m=width),)
    )
    for name, width in (("beta", 0.36), ("alpha", 0.38))
)
# Full report hashes captured from the pre-extraction implementation with these
# explicit stub rows and a fixed 500 ns elapsed interval. These are not physics.
ORIGINAL_REPORT_HASHES = {
    1: "sha256:41d985a6989f06f360276ba7d8cd6b217c02b6144044be05e02e1f749d853231",
    2: "sha256:5994c7ac7fce0c1fe7d0951bcd6c121d00e888f05b3232cb3941e8cc25920cc7",
    3: "sha256:0ebd330de5a9d2fd6dea7ae3b8aa104999e74d908f895a7b123cbd1f28ef7506",
}


def _model():
    return load_neutral_json(
        Path(__file__).parents[1] / "examples/public_rc_fiber_frame_cantilever.json"
    )


def _options(version):
    return {
        "prices": PRICES,
        "terminal_limits": TERMINAL,
        "source_revision": SOURCE,
        **({"history_limits": HISTORY} if version >= 2 else {}),
        **({"material_history_limits": MATERIAL} if version == 3 else {}),
    }


def _row(candidate_id, model, _config, prices, _terminal, _density, **options):
    offset = {"baseline": 0.0, "beta": 1.0, "alpha": 2.0}[candidate_id]
    row = {
        "candidate_id": candidate_id,
        "model_checksum": model.canonical_model_checksum,
        "canonical_model": model.canonical_payload(),
        "status": "ready",
        "full_reference_verification_pass": True,
        "solver_executed": {"baseline": True, "beta": None, "alpha": False}[
            candidate_id
        ],
        "result": {"synthetic_evaluation": True},
        "validation": {"synthetic_evaluation": True},
        "quantities": {
            "totals": {
                "gross_concrete_volume_m3": 10.0 - offset,
                "longitudinal_rebar_mass_kg": 5.0,
            }
        },
        "material_estimate": {
            "total": 10.0 if candidate_id == "baseline" else 2.0,
            "currency": "KRW",
        }
        if prices is not None
        else None,
        "performance": {
            "terminal_maximum_translation_m": 0.1 + offset * 0.01,
            "terminal_maximum_absolute_fiber_strain": 0.001 + offset * 0.0001,
        },
        "terminal_limit_status": "pass",
    }
    if "history_limits" in options:
        row.update(full_history_verification_pass=True, history_limit_status="pass")
    if "material_history_limits" in options:
        row.update(
            full_material_history_verification_pass=True,
            material_history_limit_status="pass",
        )
    return row


def _assembly_inputs(version=3, count=2, prices=PRICES):
    original = _model().detached_analysis_snapshot()
    selected = CANDIDATES[:count]
    models = [
        original,
        *(
            design.apply_fiber_frame_section_changes(original, item)
            for item in selected
        ),
    ]
    identity = design._build_design_comparison_identity(
        models[0].canonical_model_checksum,
        selected,
        [model.canonical_model_checksum for model in models[1:]],
        CONFIG,
        prices=prices,
        terminal_limits=TERMINAL,
        history_limits=HISTORY if version >= 2 else None,
        material_history_limits=MATERIAL if version == 3 else None,
        source_revision=SOURCE,
        rebar_density_kg_per_m3=7850.0,
    )
    history = {
        key: value
        for key, value in _options(version).items()
        if key.endswith("history_limits")
    }
    rows = [
        _row(candidate_id, model, CONFIG, prices, TERMINAL, 7850.0, **history)
        for candidate_id, model in zip(
            ["baseline", *(item.candidate_id for item in selected)], models, strict=True
        )
    ]
    return identity, rows


@pytest.mark.parametrize("version", [1, 2, 3])
def test_default_full_report_matches_pre_extraction_hash(version, monkeypatch):
    events = []
    times = iter([100, 600])

    def clock():
        events.append("clock")
        return next(times)

    def evaluate(candidate_id, *args, **options):
        events.append(candidate_id)
        assert set(options) == (
            set()
            if version == 1
            else {"history_limits"}
            if version == 2
            else {"history_limits", "material_history_limits"}
        )
        return _row(candidate_id, *args, **options)

    monkeypatch.setattr(design, "perf_counter_ns", clock)
    monkeypatch.setattr(design, "_evaluate_design", evaluate)
    report = design.compare_public_rc_fiber_frame_designs(
        _model(), CANDIDATES, CONFIG, **_options(version)
    ).to_dict()
    assert report["report_hash"] == ORIGINAL_REPORT_HASHES[version]
    assert report["schema_version"].endswith(f".v{version}")
    assert events == ["clock", "baseline", "beta", "alpha", "clock"]
    assert report["selection"]["candidate_id"] == "alpha"
    assert report["runtime"]["total_wall_ns"] == 500
    assert report["runtime"]["reference_analysis_request_count"] == 3
    assert report["runtime"]["known_solver_execution_count"] == 1
    assert report["runtime"]["unknown_solver_execution_count"] == 1


def test_prefix_assembly_contains_only_once_evaluated_rows(monkeypatch):
    identity, rows = _assembly_inputs(count=1)
    original_result = deepcopy([row["result"] for row in rows])

    def unexpected(*_args, **_kwargs):
        raise AssertionError("assembly must not execute an evaluation or public solve")

    monkeypatch.setattr(design, "_evaluate_design", unexpected)
    monkeypatch.setattr(design.public_api, "analyze_public_rc_fiber_frame", unexpected)
    monkeypatch.setattr(design, "perf_counter_ns", lambda: 600)
    result = design._assemble_design_comparison(
        identity, rows, prices=PRICES, started_ns=100
    )
    report = result.to_dict()
    assert [row["candidate_id"] for row in report["rows"]] == ["baseline", "beta"]
    assert [item["candidate_id"] for item in report["identity"]["candidates"]] == [
        "beta"
    ]
    assert report["selection"]["candidate_id"] == "beta"
    assert report["selection"]["evaluated_pool_size"] == 2
    assert report["runtime"]["reference_analysis_request_count"] == 2
    assert report["runtime"]["known_solver_execution_count"] == 1
    assert report["runtime"]["unknown_solver_execution_count"] == 1
    assert report["runtime"]["total_wall_ns"] == 500
    assert [row["result"] for row in rows] == original_result
    assert report["experiment_identity_hash"] == canonical_hash(identity)
    assert report["report_hash"] == canonical_hash(
        {key: value for key, value in report.items() if key != "report_hash"}
    )
    rows[0]["result"]["synthetic_evaluation"] = False
    identity["source_revision"] = "b" * 40
    report["rows"].clear()
    detached = result.to_dict()
    assert detached["rows"][0]["result"]["synthetic_evaluation"] is True
    assert detached["identity"]["source_revision"] == SOURCE


@pytest.mark.parametrize(
    "flag",
    [
        "full_reference_verification_pass",
        "full_history_verification_pass",
        "full_material_history_verification_pass",
    ],
)
def test_failed_baseline_scope_blocks_choice_but_keeps_comparable_terminal_data(
    flag, monkeypatch
):
    identity, rows = _assembly_inputs()
    rows[0][flag] = False
    monkeypatch.setattr(design, "perf_counter_ns", lambda: 600)
    report = design._assemble_design_comparison(
        identity, rows, prices=PRICES, started_ns=100
    ).to_dict()
    assert report["status"] == "partial"
    assert report["selection"]["candidate_id"] is None
    assert report["selection"]["eligible_count"] == 2
    assert all(row["material_estimate"] is not None for row in report["rows"])
    assert all(
        (row["difference_from_baseline"] is None)
        == (flag == "full_reference_verification_pass")
        for row in report["rows"]
    )


def test_verified_material_failure_keeps_ready_report_without_a_winner(monkeypatch):
    identity, rows = _assembly_inputs()
    for row in rows:
        row["material_history_limit_status"] = "fail"
    monkeypatch.setattr(design, "perf_counter_ns", lambda: 600)
    report = design._assemble_design_comparison(
        identity, rows, prices=PRICES, started_ns=100
    ).to_dict()
    assert report["status"] == "ready"
    assert report["selection"]["candidate_id"] is None
    assert report["selection"]["eligible_count"] == 0
    assert report["claims"]["all_requested_material_history_verified"] is True
    assert all(row["quantities"] is not None for row in report["rows"])


def test_missing_prices_do_not_create_a_cost_choice(monkeypatch):
    identity, rows = _assembly_inputs(prices=None)
    monkeypatch.setattr(design, "perf_counter_ns", lambda: 600)
    report = design._assemble_design_comparison(
        identity, rows, prices=None, started_ns=100
    ).to_dict()
    assert report["status"] == "ready"
    assert report["price_basis"] is None
    assert report["selection"]["candidate_id"] is None


def test_assembly_retains_nonfinite_payload_rejection(monkeypatch):
    identity, rows = _assembly_inputs()
    rows[1]["performance"]["terminal_maximum_translation_m"] = float("nan")
    monkeypatch.setattr(design, "perf_counter_ns", lambda: 600)
    with pytest.raises(design.FiberFrameDesignError, match="nonfinite"):
        design._assemble_design_comparison(
            identity, rows, prices=PRICES, started_ns=100
        )
