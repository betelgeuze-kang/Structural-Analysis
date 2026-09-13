"""Same native parent and complete prefix; one step is not a complete path."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.benchmark import rc_control_seed_runtime as runtime
from structural_analysis.io.neutral.loader import load_neutral_json


@pytest.fixture(
    scope="module", params=[False, True], ids=["binary64", "retained-constant"]
)
def origin(request, tmp_path_factory):
    root = tmp_path_factory.mktemp("parent-step-origin")
    model = load_neutral_json(
        Path("examples/public_rc_fiber_frame_l_frame_material_history.json")
    )
    control = BoundedRCFiberDirectControlRequest(
        7,
        (-1e-6, -2e-6, 1e-6),
        allow_reversals=True,
        maximum_reversals=3,
        constant_nodal_loads=(("N3", 0.0, -0.1, 0.0),) if request.param else (),
    )
    options = {}
    if request.param:
        control = replace(
            control,
            solver_config=replace(
                control.solver_config,
                newton=replace(control.solver_config.newton, terminal_polishing=True),
            ),
        )
        options = dict(
            strain_evaluation="exact-rational",
            coordinate_precision="twofold-increment",
            material_arithmetic="retained-strain",
            fiber_strain_evaluation="retained-coordinate",
            force_accumulation="rational",
            terminal_coordinate_precision="twofold",
            terminal_refinement_limit=2,
        )
    report = runtime.benchmark_rc_control_seed_paths(
        model,
        control,
        source_revision="a" * 40,
        output_directory=root / "original",
        proposal=runtime.secant_seed,
        proposal_identity="sha256:" + "b" * 64,
        **options,
    )
    assert report["reference_repeat_exact"] and all(
        c["full_history_pass"] for c in report["comparisons"].values()
    )
    path = root / "original/secant"
    step = json.loads((path / "002-1-step.json").read_bytes())
    parent_bytes = runtime._bytes(step["parent_checkpoint"])
    context = runtime.RCControlSeedContext(
        **json.loads((path / "002-context.json").read_bytes())
    )
    return model, control, options, parent_bytes, context, step


def run(root, origin, **changes):
    model, request, options, parent, context, _ = origin
    kwargs = dict(
        source_revision="a" * 40,
        output_directory=root,
        proposal=runtime.secant_seed,
        proposal_identity="sha256:" + "b" * 64,
        capture_material_state=True,
        material_capture_scope="proposal-only",
        parent_checkpoint_bytes=parent,
        accepted_context=context,
        **options,
    )
    kwargs.update(changes)
    return runtime.benchmark_rc_control_seed_paths(model, request, **kwargs)


def test_actual_same_parent_step_keeps_original_prefix_and_avoids_second_preload(
    origin, tmp_path
):
    report = run(
        tmp_path / "paired", origin, arm_order=("proposal", "reference", "secant")
    )
    assert (
        report["schema_version"] == "experimental-rc-control-parent-step-comparison.v1"
    )
    assert report["source_target_index"] == 2
    assert report["source_request"]["targets_m"] == [-1e-6, -2e-6, 1e-6]
    assert report["request"]["targets_m"] == [1e-6]
    assert report["reference_repeat_exact"]
    assert not report["original_complete_path_executed"]
    assert not report["prefix_reachability_verified"]
    assert not report["claims"]["causal_training_dataset_admitted"]
    assert all(
        c["step_response_pass"] and "full_history_pass" not in c
        for c in report["comparisons"].values()
    )
    assert report["maximum_numerical_core_calls"] == 6
    parents, prefixes = [], []
    calls = 0
    for name in ("reference", "secant", "proposal", "fresh-reference"):
        root = tmp_path / "paired" / name
        path = json.loads((root / "path.json").read_bytes())
        assert path["schema_version"] == "experimental-rc-control-parent-step-path.v1"
        assert path["accepted_target_count"] == 1 and len(path["entries"]) == 1
        assert path["supplied_prefix_target_count"] == 3
        assert not path["preload_reexecuted"] and not path.get("preload_invocations")
        assert not (root / "preload-started.json").exists()
        context = json.loads((root / "000-context.json").read_bytes())
        assert ("committed_material_state_json" in context) == (name == "proposal")
        context.pop("committed_material_state_json", None)
        prefixes.append(runtime._bytes(context))
        step = json.loads((root / "000-1-step.json").read_bytes())
        parents.append(runtime._bytes(step["parent_checkpoint"]))
        assert (
            step["accepted_checkpoint"]["epoch"]
            == origin[-1]["accepted_checkpoint"]["epoch"]
        )
        calls += sum(
            i["work"]["core_calls"] for e in path["entries"] for i in e["invocations"]
        )
    assert len(set(parents)) == len(set(prefixes)) == 1
    assert parents[0] == origin[3]
    assert prefixes[0] == runtime._bytes(origin[4].to_dict())
    assert calls == 4
    secant = json.loads((tmp_path / "paired/secant/000-1-step.json").read_bytes())
    assert secant["accepted_checkpoint"] == origin[-1]["accepted_checkpoint"]
    assert secant["trial_assembly"] == origin[-1]["trial_assembly"]
    from structural_analysis.benchmark.rc_control_runtime_selection import (
        _runtime_score,
    )

    with pytest.raises(ValueError, match="not complete-path runtime evidence"):
        _runtime_score(report, [])


@pytest.mark.parametrize(
    "kind",
    [
        "missing_parent",
        "bad_native",
        "old_coordinate",
        "target",
        "prefix",
        "material",
        "boolean",
    ],
)
def test_bad_origin_rejects_before_output(origin, tmp_path, kind):
    context = deepcopy(origin[4])
    changes = {}
    if kind == "missing_parent":
        changes["parent_checkpoint_bytes"] = None
    elif kind == "bad_native":
        parent = json.loads(origin[3])
        parent["state_hash"] = "sha256:" + "f" * 64
        changes["parent_checkpoint_bytes"] = runtime._bytes(parent)
    elif kind == "old_coordinate":
        context.accepted_augmented_coordinates_m[-1][0] += 0.1
    elif kind == "target":
        context = replace(context, target_m=0.5)
    elif kind == "prefix":
        context.accepted_targets_m[1] = 0.5
    elif kind == "material":
        context = replace(context, committed_material_state_json="{}")
    else:
        context.accepted_augmented_coordinates_m[0][0] = True
    with pytest.raises(ValueError):
        run(tmp_path / "rejected", origin, accepted_context=context, **changes)
    assert not (tmp_path / "rejected").exists()


def test_unknown_numerical_work_stops_before_next_arm(origin, tmp_path, monkeypatch):
    calls = []

    def fail(*args, **kwargs):
        calls.append(1)
        raise RuntimeError("unknown numerical work")

    monkeypatch.setattr(
        runtime, "solve_stateful_fiber_frame2d_displacement_control_step", fail
    )
    with pytest.raises(ValueError, match="scheduling stopped"):
        run(tmp_path / "failed", origin)
    assert len(calls) == 1
    stop = json.loads((tmp_path / "failed/scheduling-stop.json").read_bytes())
    assert stop["unknown_numerical_work"] and stop["later_arms_not_started"]
    assert not (tmp_path / "failed/secant").exists()
    assert not (tmp_path / "failed/comparison.json").exists()


def test_invalid_proposal_uses_original_parent_fallback(origin, tmp_path):
    report = run(tmp_path / "invalid-seed", origin, proposal=lambda c: (float("nan"),))
    assert report["reference_repeat_exact"]
    assert all(c["step_response_pass"] for c in report["comparisons"].values())
    entry = report["arms"]["proposal"]["entries"][0]
    assert entry["proposal_decision"] == "invalid_proposal_to_reference"
    assert entry["parent_hash"] == report["initial_parent_hash"]
    assert len(entry["invocations"]) == 1 and not entry["invocations"][0]["seed_used"]


def test_abstention_reproduces_secant_from_same_parent(origin, tmp_path):
    report = run(
        tmp_path / "abstain",
        origin,
        proposal=lambda c: None,
        proposal_abstention_strategy="secant",
    )
    assert all(c["step_response_pass"] for c in report["comparisons"].values())
    step_paths = [
        tmp_path / "abstain" / arm / "000-1-step.json" for arm in ("secant", "proposal")
    ]
    steps = [json.loads(path.read_bytes()) for path in step_paths]
    assert steps[0]["parent_checkpoint"] == steps[1]["parent_checkpoint"]
    assert steps[0]["accepted_checkpoint"] == steps[1]["accepted_checkpoint"]
    assert steps[0]["trial_assembly"] == steps[1]["trial_assembly"]
