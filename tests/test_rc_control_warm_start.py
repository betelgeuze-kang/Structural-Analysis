"""Optional RC control seeds cannot acquire equilibrium or commit authority."""

from dataclasses import replace

import numpy as np
import pytest

from structural_analysis.assembly import (
    stateful_fiber_frame2d_displacement_control as control,
)
from structural_analysis.assembly import initial_stateful_fiber_frame2d_checkpoint
from structural_analysis.benchmark.stateful_fiber_frame2d import (
    make_two_element_stateful_fiber_cantilever,
)
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig


@pytest.fixture
def case():
    problem = make_two_element_stateful_fiber_cantilever()
    parent = initial_stateful_fiber_frame2d_checkpoint(problem)
    return problem, parent


@pytest.mark.parametrize(
    "scope,expected_captures", [("all-arms", 12), ("proposal-only", 3)]
)
def test_material_capture_scope_charges_only_declared_arms(
    tmp_path, monkeypatch, scope, expected_captures
):
    import json
    from pathlib import Path
    from structural_analysis.api.rc_fiber_frame_direct_control_request import (
        BoundedRCFiberDirectControlRequest,
    )
    from structural_analysis.benchmark import rc_control_material_features as material
    from structural_analysis.benchmark import rc_control_seed_runtime as runtime
    from structural_analysis.io.neutral.loader import load_neutral_json

    captures = []
    original = material.committed_material_snapshot

    def capture(problem, checkpoint):
        captures.append(checkpoint.state_hash)
        return original(problem, checkpoint)

    monkeypatch.setattr(material, "committed_material_snapshot", capture)
    root = tmp_path / "study"
    report = runtime.benchmark_rc_control_seed_paths(
        load_neutral_json(
            Path("examples/public_rc_fiber_frame_l_frame_material_history.json")
        ),
        BoundedRCFiberDirectControlRequest(
            7, (-1e-6, -2e-6, -1.5e-6), allow_reversals=True, maximum_reversals=1
        ),
        source_revision="a" * 40,
        output_directory=root,
        proposal=runtime.secant_seed,
        proposal_identity="sha256:" + "b" * 64,
        capture_material_state=True,
        material_capture_scope=scope,
    )
    assert report["reference_repeat_exact"] and all(
        c["full_history_pass"] for c in report["comparisons"].values()
    )
    assert len(captures) == expected_captures
    for arm in ("reference", "secant", "proposal", "fresh-reference"):
        path = json.loads((root / arm / "path.json").read_bytes())
        expected = scope == "all-arms" or arm == "proposal"
        for entry in path["entries"]:
            context = json.loads(
                (root / arm / f"{entry['target_index']:03d}-context.json").read_bytes()
            )
            assert ("committed_material_state_json" in context) is expected
            assert ("committed_material_capture" in entry) is expected


def run(case, **kwargs):
    return control.solve_stateful_fiber_frame2d_displacement_control_step(
        *case, control_global_dof=7, target_control_displacement_m=-1e-6, **kwargs
    )


def test_seed_is_copied_and_only_changes_initial_coordinates(case):
    problem, parent = case
    before = parent.canonical_bytes()
    source = np.zeros(len(problem.free_global_dofs) + 1)
    adapter = control.StatefulFiberFrame2DDisplacementControlStepAdapter(
        problem,
        parent,
        7,
        -1e-6,
        control.StatefulFiberFrame2DDisplacementControlConfig(),
        source,
    )
    source[:] = 100
    assert np.array_equal(adapter.initial_free_displacements_m(), np.zeros_like(source))
    returned = adapter.initial_free_displacements_m()
    returned[:] = 200
    assert np.array_equal(adapter.initial_free_displacements_m(), np.zeros_like(source))
    assert parent.canonical_bytes() == before


def test_actual_reference_and_seeded_steps_preserve_all_original_gates(case):
    reference = run(case)
    before = case[1].canonical_bytes()
    seed = tuple(reference.trial_solution.free_displacements_m)
    seeded = run(case, initial_augmented_coordinates_m=seed)
    assert reference.committed and seeded.committed
    assert "initial_augmented_coordinates_m" not in reference.metrics
    assert seeded.metrics["initial_augmented_coordinates_m"] == list(seed)
    for key in (
        "control_gate_passed",
        "equilibrium_gate_passed",
        "solver_contract_pass",
        "parent_checkpoint_immutable",
        "section_and_element_parent_binding_passed",
        "solver_assembly_coordinate_residual_binding_passed",
    ):
        assert seeded.metrics[key] is True
    assert case[1].canonical_bytes() == before
    assert np.allclose(
        seeded.accepted_checkpoint.global_displacements,
        reference.accepted_checkpoint.global_displacements,
        rtol=1e-12,
        atol=1e-14,
    )
    assert seeded.accepted_checkpoint.load_factor == pytest.approx(
        reference.accepted_checkpoint.load_factor, rel=1e-12, abs=1e-14
    )
    # Newton still runs and tests its increment even when supplied the terminal state.
    assert seeded.trial_solution.metrics["linear_solve_count"] >= 1


@pytest.mark.parametrize(
    "seed",
    [
        True,
        1.0,
        "bad",
        (),
        (0.0,),
        [[0.0] * 7],
        [True] * 7,
        [float("nan")] * 7,
        [float("inf")] * 7,
        [2**54 + 1] * 7,
    ],
)
def test_invalid_seed_rejected_before_newton(case, seed, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid seed reached Newton")

    monkeypatch.setattr(control, "newton_raphson_vector", forbidden)
    before = case[1].canonical_bytes()
    with pytest.raises(ValueError):
        run(case, initial_augmented_coordinates_m=seed)
    assert case[1].canonical_bytes() == before


def test_seed_failure_has_exact_rollback_and_no_hidden_retry(case, monkeypatch):
    calls = 0
    original = control.newton_raphson_vector

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(control, "newton_raphson_vector", counted)
    config = control.StatefulFiberFrame2DDisplacementControlConfig(
        newton=NewtonRaphsonConfig(max_iterations=1)
    )
    result = run(
        case,
        config=config,
        initial_augmented_coordinates_m=(1e-3,) * (len(case[0].free_global_dofs) + 1),
    )
    assert result.committed is False
    assert result.accepted_checkpoint is case[1]
    assert result.metrics["rollback_exact"] is True
    assert calls == 1


def test_seed_cannot_bypass_a_failed_increment_gate(case, monkeypatch):
    original = control.newton_raphson_vector

    def forged(*args, **kwargs):
        solution = original(*args, **kwargs)
        return replace(
            solution, metrics={**solution.metrics, "increment_gate_passed": False}
        )

    monkeypatch.setattr(control, "newton_raphson_vector", forged)
    result = run(
        case,
        initial_augmented_coordinates_m=(0.0,) * (len(case[0].free_global_dofs) + 1),
    )
    assert result.committed is False and result.accepted_checkpoint is case[1]
    assert result.metrics["rollback_exact"] is True


def test_default_api_bytes_are_unchanged():
    from pathlib import Path
    from structural_analysis.api.rc_fiber_frame_direct_control import (
        analyze_bounded_rc_fiber_direct_control,
    )
    from structural_analysis.io.neutral.loader import load_neutral_json

    model = load_neutral_json(
        Path("examples/public_rc_fiber_frame_l_frame_material_history.json")
    ).detached_analysis_snapshot()
    result = analyze_bounded_rc_fiber_direct_control(
        model,
        (-1e-6, -2e-6, -1.5e-6),
        control_global_dof=7,
        allow_reversals=True,
        maximum_reversals=1,
    )
    root = Path("tests/frontend/fixtures/rc-control-design/baseline")
    assert result.result_artifact_bytes() == (root / "result.json").read_bytes()
    assert result.checkpoint_artifact_bytes() == (root / "checkpoint.json").read_bytes()


@pytest.mark.parametrize("polishing", [False, True])
def test_actual_complete_seed_paths_and_rejected_proposer(tmp_path, polishing):
    import json
    from pathlib import Path
    from structural_analysis.api.rc_fiber_frame_direct_control_request import (
        BoundedRCFiberDirectControlRequest,
    )
    from structural_analysis.benchmark.rc_control_seed_runtime import (
        benchmark_rc_control_seed_paths,
    )
    from structural_analysis.io.neutral.loader import load_neutral_json

    contexts = []

    def rejected(context):
        contexts.append(context)
        return (float("nan"),) * 7

    report = benchmark_rc_control_seed_paths(
        load_neutral_json(
            Path("examples/public_rc_fiber_frame_l_frame_material_history.json")
        ),
        BoundedRCFiberDirectControlRequest(
            7,
            (-1e-6, -2e-6, -1.5e-6),
            allow_reversals=True,
            maximum_reversals=1,
            solver_config=control.StatefulFiberFrame2DDisplacementControlConfig(
                newton=NewtonRaphsonConfig(terminal_polishing=polishing)
            ),
        ),
        source_revision="a" * 40,
        output_directory=tmp_path / "study",
        proposal=rejected,
        proposal_identity="sha256:" + "b" * 64,
    )
    assert report["reference_repeat_exact"] is True
    assert all(v["full_history_pass"] for v in report["comparisons"].values())
    assert [len(c.accepted_targets_m) for c in contexts] == [1, 2, 3]
    assert contexts[0].accepted_targets_m == (0.0,)
    for entry in report["arms"]["proposal"]["entries"]:
        assert entry["proposal_rejected_to_reference"] is True
        assert len(entry["invocations"]) == 1
        assert entry["invocations"][0]["seed_used"] is False
        assert entry["invocations"][0]["unknown_work"] is False
    for arm in ("reference", "secant", "proposal", "fresh-reference"):
        path = json.loads((tmp_path / "study" / arm / "path.json").read_bytes())
        assert path["accepted_target_count"] == 3
        assert len(path["response_history"]) == 3
        for entry in path["entries"]:
            for inv in entry["invocations"]:
                step = json.loads(
                    (
                        tmp_path
                        / "study"
                        / arm
                        / f"{entry['target_index']:03d}-{inv['ordinal']}-step.json"
                    ).read_bytes()
                )
                metrics = step["trial_solution"]["metrics"]
                assert inv["work"]["linear_solves"] == metrics["linear_solve_count"]
                assert ("terminal_polishing" in metrics) is polishing
                if polishing:
                    detail = metrics["terminal_polishing"]
                    assert (
                        detail["attempted"] and detail["assembly_exception_count"] == 0
                    )
                    assert metrics["linear_solve_count"] >= detail["linear_solve_count"]
                    if detail["accepted"]:
                        assert (
                            detail["candidate_residual_linf"]
                            < detail["original_residual_linf"]
                        )
                        assert detail["candidate_increment_abs_m"] <= 1e-12


def test_actual_numerically_rejected_seed_records_fallback_cost(tmp_path):
    from pathlib import Path
    from structural_analysis.api.rc_fiber_frame_direct_control_request import (
        BoundedRCFiberDirectControlRequest,
    )
    from structural_analysis.benchmark.rc_control_seed_runtime import (
        benchmark_rc_control_seed_paths,
    )
    from structural_analysis.io.neutral.loader import load_neutral_json

    cfg = control.StatefulFiberFrame2DDisplacementControlConfig(
        newton=NewtonRaphsonConfig(max_iterations=1)
    )
    report = benchmark_rc_control_seed_paths(
        load_neutral_json(
            Path("examples/public_rc_fiber_frame_l_frame_material_history.json")
        ),
        BoundedRCFiberDirectControlRequest(7, (-1e-6,), solver_config=cfg),
        source_revision="a" * 40,
        output_directory=tmp_path / "study",
        proposal=lambda context: (0.001,)
        * len(context.accepted_augmented_coordinates_m[-1]),
        proposal_identity="sha256:" + "b" * 64,
        arm_order=("proposal", "secant", "reference"),
    )
    entries = report["arms"]["proposal"]["entries"][0]["invocations"]
    assert len(entries) == 2
    assert entries[0]["committed"] is False and entries[0]["rollback_exact"] is True
    assert entries[1]["seed_used"] is False
    assert all(i["work"]["core_calls"] == 1 for i in entries)
    assert entries[0]["unknown_work"] is True
    assert entries[0]["work"]["newton_iterations"] is None
    assert entries[0]["work"]["linear_solves"] is None
    assert entries[1]["unknown_work"] is False
    assert report["all_execution_work_reported"] is False
    assert report["reference_repeat_exact"] is True


def test_exception_keeps_unknown_cost_without_retry(tmp_path, monkeypatch):
    from pathlib import Path
    from structural_analysis.api.rc_fiber_frame_direct_control_request import (
        BoundedRCFiberDirectControlRequest,
    )
    from structural_analysis.benchmark import rc_control_seed_runtime as runtime
    from structural_analysis.io.neutral.loader import load_neutral_json

    def raises(*args, **kwargs):
        raise RuntimeError("injected unknown entry")

    monkeypatch.setattr(
        runtime, "solve_stateful_fiber_frame2d_displacement_control_step", raises
    )
    report = runtime.benchmark_rc_control_seed_paths(
        load_neutral_json(
            Path("examples/public_rc_fiber_frame_l_frame_material_history.json")
        ),
        BoundedRCFiberDirectControlRequest(7, (-1e-6, -2e-6)),
        source_revision="a" * 40,
        output_directory=tmp_path / "study",
    )
    assert report["reference_repeat_exact"] is False
    assert not any(c["full_history_pass"] for c in report["comparisons"].values())
    for path in [*report["arms"].values(), report["fresh_reference"]]:
        assert path["status"] == "incomplete"
        assert len(path["entries"]) == 1 and len(path["entries"][0]["invocations"]) == 1
        assert path["entries"][0]["invocations"][0]["unknown_work"] is True
        assert path["entries"][0]["invocations"][0]["work"] is None


def test_invalid_control_is_rejected_before_creating_study(tmp_path, monkeypatch):
    from pathlib import Path
    from structural_analysis.api.rc_fiber_frame_direct_control_request import (
        BoundedRCFiberDirectControlRequest,
    )
    from structural_analysis.benchmark import rc_control_seed_runtime as runtime
    from structural_analysis.io.neutral.loader import load_neutral_json

    monkeypatch.setattr(
        runtime,
        "solve_stateful_fiber_frame2d_displacement_control_step",
        lambda *a, **k: pytest.fail("invalid control reached solver"),
    )
    with pytest.raises(ValueError, match="free translational"):
        runtime.benchmark_rc_control_seed_paths(
            load_neutral_json(
                Path("examples/public_rc_fiber_frame_l_frame_material_history.json")
            ),
            BoundedRCFiberDirectControlRequest(0, (-1e-6,)),
            source_revision="a" * 40,
            output_directory=tmp_path / "study",
        )
    assert not (tmp_path / "study").exists()


def test_mismatch_diagnostics_count_all_values_but_bound_examples():
    from structural_analysis.benchmark.rc_control_seed_runtime import (
        _physical_mismatch_locations,
    )

    left = [{"member_end_forces": [0.0] * 25, "checkpoint_hash": "one"}]
    right = [{"member_end_forces": [1e-7] * 25, "checkpoint_hash": "two"}]
    result = _physical_mismatch_locations(
        left, right, absolute_tolerance=1e-10, relative_tolerance=1e-8
    )
    assert result["mismatch_count"] == 25
    assert result["by_response_field"] == {"member_end_forces": 25}
    assert result["examples_truncated"] and len(result["examples"]) == 20
    assert result["examples"][0]["path"] == [0, "member_end_forces", 0]
    assert result["examples"][0]["reference"] == 0
    assert result["examples"][0]["arm"] == 1e-7
    assert result["examples"][0]["allowed_difference"] == pytest.approx(1e-10 + 1e-15)


def test_mismatch_diagnostics_retain_missing_history_and_wrong_response_structure():
    from structural_analysis.benchmark.rc_control_seed_runtime import (
        _physical_mismatch_locations,
    )

    result = _physical_mismatch_locations(
        [{"node_displacements": [0.0]}, {"load_factor": 1}],
        [{"node_displacements": "bad"}],
        absolute_tolerance=1e-10,
        relative_tolerance=1e-8,
    )
    assert result["mismatch_count"] == 2
    assert [row["kind"] for row in result["examples"]] == [
        "sequence_lengths_differ",
        "sequence_type_differ",
    ]
