"""Constant loads must reach every study arm, accepted origin and cost ledger."""

from dataclasses import replace
import json
from pathlib import Path

import pytest

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.benchmark import rc_control_seed_runtime as runtime
from structural_analysis.benchmark.rc_control_learning import _execution_work
from structural_analysis.io.neutral.loader import load_neutral_json


def model():
    return load_neutral_json(Path("examples/public_rc_fiber_frame_cantilever.json"))


def request(**kwargs):
    return BoundedRCFiberDirectControlRequest(
        4,
        (-1e-5, -2e-5, 1e-5),
        allow_reversals=True,
        maximum_reversals=2,
        constant_nodal_loads=(("N2", -600.0, 0.0, 0.0),),
        **kwargs,
    )


def read(root, name):
    return json.loads((root / name).read_bytes())


@pytest.mark.parametrize("retained", [False, True])
def test_every_arm_preloads_independently_and_proposal_sees_original_state(
    tmp_path, retained
):
    root = tmp_path / "study"
    contexts = []
    req = request()
    options = {}
    if retained:
        req = replace(
            req,
            solver_config=replace(
                req.solver_config,
                newton=replace(req.solver_config.newton, terminal_polishing=True),
            ),
        )
        options = dict(
            strain_evaluation="exact-rational", coordinate_precision="twofold-increment"
        )

    def proposal(context):
        contexts.append(context)
        return None

    result = runtime.benchmark_rc_control_seed_paths(
        model(),
        req,
        source_revision="a" * 40,
        output_directory=root,
        proposal=proposal,
        proposal_identity="sha256:" + "b" * 64,
        **options,
    )
    assert result["reference_repeat_exact"]
    assert result["all_execution_work_reported"]
    assert len(contexts) == 3
    assert len(contexts[0].accepted_targets_m) == 1
    assert runtime.secant_seed(contexts[0]) is None
    for arm in ("reference", "secant", "proposal", "fresh-reference"):
        path = read(root, arm + "/path.json")
        assert path["status"] == "complete"
        preload = read(root, arm + "/preload-step.json")
        assert preload["accepted_checkpoint"]["epoch"] == 1
        assert path["terminal_checkpoint"]["epoch"] == 4
        assert (
            path["entries"][0]["parent_hash"]
            == preload["accepted_checkpoint"]["state_hash"]
        )
        for response in [path["preload_response"], *path["response_history"]]:
            assert response["support_reactions"][0]["value_si"] == pytest.approx(
                600000.0, abs=1e-6
            )
        assert path["preload_invocations"][0]["work"]["core_calls"] == 1
    original = read(root, "proposal/preload-step.json")
    origin = contexts[0].accepted_augmented_coordinates_m[0]
    assert any(x != 0 for x in origin[:-1]) and origin[-1] == 0
    if retained:
        assert (
            list(origin[:-1]) == original["accepted_checkpoint"]["free_coordinates_m"]
        )
    work = _execution_work([{"report": result}])
    assert work["known_work"]["core_calls"] == 16
    assert not work["unknown_work"]


def test_nonzero_preload_origin_allows_first_zero_control_target(tmp_path):
    req = replace(
        request(), targets_m=(0.0,), constant_nodal_loads=(("N2", 0.0, -0.1, 0.0),)
    )
    contexts = []
    result = runtime.benchmark_rc_control_seed_paths(
        model(),
        req,
        source_revision="a" * 40,
        output_directory=tmp_path / "zero",
        proposal=lambda c: contexts.append(c),
        proposal_identity="sha256:" + "b" * 64,
    )
    assert result["reference_repeat_exact"]
    assert contexts[0].accepted_targets_m[0] < 0
    assert contexts[0].target_m == 0
    assert _execution_work([{"report": result}])["known_work"]["core_calls"] == 8


def test_failed_preload_preserves_original_unknown_work_and_never_proposes(tmp_path):
    req = request()
    req = replace(
        req,
        constant_nodal_loads=(("N2", -30000.0, 0.0, 0.0),),
        solver_config=replace(
            req.solver_config,
            newton=replace(req.solver_config.newton, max_iterations=1),
        ),
    )
    root = tmp_path / "failed"
    result = runtime.benchmark_rc_control_seed_paths(
        model(),
        req,
        source_revision="a" * 40,
        output_directory=root,
        proposal=lambda _: pytest.fail("failed preload reached proposal"),
        proposal_identity="sha256:" + "b" * 64,
    )
    assert not result["reference_repeat_exact"]
    assert not result["all_execution_work_reported"]
    for arm in ("reference", "secant", "proposal", "fresh-reference"):
        path = read(root, arm + "/path.json")
        assert path["failure"]["phase"] == "preload"
        assert path["entries"] == [] and path["terminal_checkpoint"]["epoch"] == 0
        assert read(root, arm + "/preload-outcome.json")["original_failure"]
        assert not list((root / arm).glob("*-proposal-started.json"))
    assert _execution_work([{"report": result}]) == {
        "known_work": {"core_calls": 4, "newton_iterations": 0, "linear_solves": 0},
        "unknown_work": True,
    }


def test_recovery_failure_retains_preload_cost_without_accepting_state(
    tmp_path, monkeypatch
):
    def fail(*args):
        raise ValueError("injected original recovery mismatch")

    monkeypatch.setattr(runtime, "_recover_preload", fail)
    root = tmp_path / "recovery"
    result = runtime.benchmark_rc_control_seed_paths(
        model(), request(), source_revision="a" * 40, output_directory=root
    )
    for arm in ("reference", "secant", "fresh-reference"):
        path = read(root, arm + "/path.json")
        assert path["failure"]["phase"] == "preload_recovery"
        assert path["terminal_checkpoint"]["epoch"] == 0
        assert path["entries"] == []
        assert read(root, arm + "/preload-step.json")["committed"]
    work = _execution_work([{"report": result}])
    assert work["known_work"]["core_calls"] == 3
    assert not work["unknown_work"]


def test_actual_preload_origin_enforces_declared_reversal_budget(tmp_path):
    # The preload bends farther downward than these targets. Starting from it
    # requires an upward leg followed by a downward leg, unlike a virgin origin.
    req = replace(
        request(),
        targets_m=(-1e-8, -2e-8),
        allow_reversals=False,
        maximum_reversals=0,
        constant_nodal_loads=(("N2", 0.0, -0.1, 0.0),),
    )
    root = tmp_path / "reversal"
    report = runtime.benchmark_rc_control_seed_paths(
        model(), req, source_revision="a" * 40, output_directory=root
    )
    assert not report["reference_repeat_exact"]
    for arm in ("reference", "secant", "fresh-reference"):
        path = read(root, arm + "/path.json")
        assert path["failure"]["phase"] == "post_preload_preflight"
        assert path["terminal_checkpoint"]["epoch"] == 1
        assert not path["entries"]
    assert _execution_work([{"report": report}])["known_work"]["core_calls"] == 3


def test_preload_interruption_leaves_started_unknown_record(tmp_path, monkeypatch):
    def interrupt(*args):
        raise KeyboardInterrupt("injected preload interruption")

    monkeypatch.setattr(runtime, "_execute_preload", interrupt)
    root = tmp_path / "interrupted"
    with pytest.raises(KeyboardInterrupt, match="injected preload interruption"):
        runtime.benchmark_rc_control_seed_paths(
            model(), request(), source_revision="a" * 40, output_directory=root
        )
    assert read(root, "reference/preload-started.json")["unknown_work"]
    assert not (root / "reference/preload-outcome.json").exists()
    assert not (root / "comparison.json").exists()
    assert not (root / "secant").exists()
