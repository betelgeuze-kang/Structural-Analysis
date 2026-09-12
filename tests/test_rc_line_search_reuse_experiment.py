"""Boundaries of the serial research-only, immediate assembly reuse experiment."""

import importlib.util
import ast
import json
from pathlib import Path

import numpy as np
import pytest

_spec = importlib.util.spec_from_file_location(
    "reuse_experiment",
    Path(__file__).resolve().parents[1] / "scripts/diagnose_rc_control_line_search_reuse.py",
)
experiment = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(experiment)


class Adapter:
    pass


def setup():
    calls = []
    result = (np.array([2.0]), np.array([[3.0]]))

    def dispatch(problem, coordinates, **kwargs):
        calls.append((problem, coordinates, kwargs))
        return result

    return experiment.ImmediateLineSearchReuse(dispatch, adapter_type=Adapter), calls, result


def test_one_use_copy_and_original_recorder_only_on_real_dispatch():
    reuse, calls, result = setup()
    adapter, recorder = Adapter(), object()
    reuse(adapter, np.array([1.0]), phase="line_search", recorder=recorder)
    result[0][0] = 99  # retained arrays cannot alias a mutable dispatch result
    hit = reuse(adapter, np.array([1.0]), phase="primary_iteration", recorder=recorder)
    assert hit[0][0] == 2 and reuse.hits == 1 and len(calls) == 1
    assert calls[0][2]["recorder"] is recorder
    reuse(adapter, np.array([1.0]), phase="primary_iteration", recorder=recorder)
    assert len(calls) == 2  # consumed, never a persistent coordinate cache


@pytest.mark.parametrize("boundary", [
    "new_adapter", "subclass", "compensation", "final_observation",
    "terminal_refinement", "blocked_observation", "coordinate", "dtype", "signed_zero",
])
def test_cache_does_not_cross_identity_arithmetic_or_observation_boundaries(boundary):
    reuse, calls, _ = setup()
    adapter = Adapter()
    x = np.array([0.0])
    reuse(adapter, x, phase="line_search")
    problem, phase, compensation = adapter, "primary_iteration", None
    if boundary == "new_adapter":
        problem = Adapter()
    elif boundary == "subclass":
        problem = type("Derived", (Adapter,), {})()
    elif boundary == "compensation":
        compensation = np.array([0.0])
    elif boundary in ("final_observation", "terminal_refinement", "blocked_observation"):
        phase = boundary
    elif boundary == "coordinate":
        x = np.array([1.0])
    elif boundary == "dtype":
        x = x.astype(np.float32)
    elif boundary == "signed_zero":
        x = np.array([-0.0])
    reuse(problem, x, phase=phase, compensation=compensation)
    assert len(calls) == 2 and reuse.hits == 0
    reuse(adapter, np.array([0.0]), phase="primary_iteration")
    assert len(calls) == 3  # intervening call invalidates the entry


def test_exception_is_preserved_and_invalidates_previous_entry():
    reuse, calls, _ = setup()
    adapter = Adapter()
    reuse(adapter, np.array([1.0]), phase="line_search")
    original = reuse.dispatch
    error = RuntimeError("assembly failed")

    def fail(*args, **kwargs):
        raise error

    reuse.dispatch = fail
    with pytest.raises(RuntimeError) as observed:
        reuse(adapter, np.array([2.0]), phase="line_search")
    assert observed.value is error
    reuse.dispatch = original
    reuse(adapter, np.array([1.0]), phase="primary_iteration")
    assert len(calls) == 2 and reuse.hits == 0


@pytest.mark.parametrize("repetitions", [True, 0, -2, 1, 3, 2.0])
def test_invalid_repetition_count_rejects_before_output(tmp_path, repetitions):
    output = tmp_path / "absent"
    with pytest.raises(ValueError, match="even number"):
        experiment.run(output, repetitions)
    assert not output.exists()


def test_yielded_case_reuses_exact_existing_regression_targets():
    source = Path(__file__).with_name("test_stateful_fiber_frame2d_displacement_control.py")
    tree = ast.parse(source.read_text())
    targets = next(ast.literal_eval(node.value) for node in tree.body
                   if isinstance(node, ast.Assign) and any(
                       isinstance(t, ast.Name) and t.id == "YIELDED_RC_TARGETS_M"
                       for t in node.targets))
    request = experiment.experiment_request("yielded-prefix", False)
    assert request.targets_m == targets
    assert request.solver_config.newton.max_iterations == 40
    with pytest.raises(ValueError, match="constant preload"):
        experiment.experiment_request("yielded-prefix", True)


def test_unknown_arithmetic_rejects_before_output(tmp_path):
    output = tmp_path / "absent"
    with pytest.raises(ValueError, match="arithmetic selection"):
        experiment.run(output, 2, arithmetic="unknown")
    assert not output.exists()


def test_historical_wrapper_runs_through_native_dispatch_signature(tmp_path, monkeypatch):
    wrapper = experiment.ImmediateLineSearchReuse(experiment.newton.assemble_vector)
    monkeypatch.setattr(experiment.newton, "assemble_vector", wrapper)
    model = experiment.load_neutral_json(Path("examples/public_rc_fiber_frame_l_frame_material_history.json"))
    report = experiment.runtime.benchmark_rc_control_seed_paths(
        model, experiment.experiment_request("small", False),
        source_revision="a" * 40, output_directory=tmp_path / "wrapper",
        proposal=experiment.runtime.secant_seed, proposal_identity="sha256:" + "b" * 64,
    )
    assert report["reference_repeat_exact"]
    assert all(v["full_history_pass"] for v in report["comparisons"].values())
    assert wrapper.hits > 0


@pytest.mark.parametrize("has_model,has_request,case", [
    (True, False, "supplied"), (False, True, "supplied"), (True, True, "small"),
])
def test_supplied_case_requires_explicit_paired_inputs(tmp_path, has_model, has_request, case):
    output = tmp_path / "absent"
    with pytest.raises(ValueError, match="both model and request"):
        experiment.run(output, 2, case=case,
                       model_path=tmp_path / "model" if has_model else None,
                       request_path=tmp_path / "request" if has_request else None)
    assert not output.exists()


def test_supplied_case_preserves_preload_and_targets_through_native_comparison(tmp_path):
    request = experiment.experiment_request("small", True)
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request.to_dict()))
    model_path = Path("examples/public_rc_fiber_frame_l_frame_material_history.json")
    output = tmp_path / "study"
    experiment.run(output, 2, case="supplied", arithmetic="retained",
                   model_path=model_path, request_path=request_path)
    summary = json.loads((output / "summary.json").read_bytes())
    assert summary["supplied_target_count"] == 3
    assert summary["supplied_constant_load_count"] == 1
    assert summary["supplied_request_sha256"] == experiment.hashlib.sha256(
        request_path.read_bytes()).hexdigest()
    assert [row["order"] for row in summary["rows"]] == [[False, True], [True, False]]
    for row in summary["rows"]:
        assert row["constant"] is True
        assert row["native_step_bytes_exact"]
        assert row["baseline"]["step_count"] == row["reuse"]["step_count"] == 16
        assert row["reuse"]["reused_dispatches"] > 0
