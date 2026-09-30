"""A rejected terminal correction still spends its recorded assembly work."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from structural_analysis.benchmark.rc_control_iteration_cost import (
    summarize_rc_control_iteration_cost,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash


def sign(step):
    step["step_hash"] = canonical_hash(
        {k: v for k, v in step.items() if k != "step_hash"}
    )
    return step


def record(*, base=3, accepted=2):
    attempts = [
        {
            "attempted": True,
            "accepted": i < accepted,
            "source_iteration": base - 1 + min(i, accepted),
            "candidate_iteration": base + i,
            "assembly_call_count": 1,
            "assembly_exception_count": 0,
            "linear_solve_count": int(i < accepted),
            "linear_solve_exception_count": 0,
        }
        for i in range(2)
    ]
    return sign(
        {
            "committed": True,
            "trial_solution": {
                "convergence_history": [
                    {"iteration": i} for i in range(base + accepted)
                ],
                "line_search_history": [
                    {"iteration": i, "attempt_count": 1, "attempts": [{}]}
                    for i in range(base - 1)
                ],
                "metrics": {
                    "iteration_count": base + accepted,
                    "newton_iteration_count": base + accepted,
                    "linear_solve_count": base + accepted,
                    "line_search_step_count": base - 1,
                    "terminal_polishing": {
                        "schema_version": "newton-vector-terminal-refinement.v1",
                        "refinement_limit": 2,
                        "attempts": attempts,
                        "attempt_count": 2,
                        "accepted_correction_count": accepted,
                        "assembly_call_count": 2,
                        "assembly_exception_count": 0,
                        "linear_solve_count": accepted,
                        "linear_solve_exception_count": 0,
                    },
                },
            },
        }
    )


def test_fewer_accepted_refinements_do_not_mean_less_primary_or_assembly_work():
    baseline, proposal = record(), record(accepted=1)
    before = deepcopy((baseline, proposal))
    a, b = map(summarize_rc_control_iteration_cost, (baseline, proposal))
    assert (a["inclusive_convergence_rows"], b["inclusive_convergence_rows"]) == (5, 4)
    assert a["primary_convergence_rows"] == b["primary_convergence_rows"] == 3
    assert a["terminal_assembly_calls"] == b["terminal_assembly_calls"] == 2
    assert (
        a["attempted_terminal_refinements"] == b["attempted_terminal_refinements"] == 2
    )
    assert a["line_search_trials"] == b["line_search_trials"] == 2
    assert (a["terminal_linear_solves"], b["terminal_linear_solves"]) == (2, 1)
    assert b["total_solver_assembly_calls"] is None
    assert not b["performance_improvement"] and not b["training_admitted"]
    assert (baseline, proposal) == before


def test_primary_row_reduction_is_reported_separately():
    result = summarize_rc_control_iteration_cost(record(base=2))
    assert result["primary_convergence_rows"] == 2
    assert result["accepted_terminal_corrections"] == 2
    assert result["inclusive_convergence_rows"] == 4
    assert result["terminal_assembly_calls"] == 2
    assert result["line_search_trials"] == 1


@pytest.mark.parametrize("value", [True, -1, 5.0, None])
def test_invalid_recorded_iteration_count_rejects(value):
    step = record()
    step["trial_solution"]["metrics"]["iteration_count"] = value
    with pytest.raises(ValueError):
        summarize_rc_control_iteration_cost(sign(step))


@pytest.mark.parametrize(
    "kind",
    [
        "hash",
        "failed",
        "missing",
        "aggregate",
        "boolean",
        "candidate",
        "search",
        "linear",
        "ordering",
    ],
)
def test_inconsistent_records_cannot_supply_work_labels(kind):
    step = record()
    trial = step["trial_solution"]
    polishing = trial["metrics"]["terminal_polishing"]
    if kind == "hash":
        step["step_hash"] = "sha256:" + "f" * 64
    elif kind == "failed":
        step["committed"] = False
    elif kind == "missing":
        del trial["metrics"]["terminal_polishing"]
    elif kind == "aggregate":
        polishing["assembly_call_count"] = 1
    elif kind == "boolean":
        polishing["attempts"][0]["accepted"] = 1
    elif kind == "candidate":
        polishing["attempts"][1]["candidate_iteration"] = 0
    elif kind == "search":
        trial["line_search_history"][0]["attempt_count"] = 0
    elif kind == "linear":
        trial["metrics"]["linear_solve_count"] = 2
    else:
        trial["convergence_history"][0]["iteration"] = 1
    if kind != "hash":
        sign(step)
    with pytest.raises(ValueError):
        summarize_rc_control_iteration_cost(step)


def test_refinement_cannot_continue_after_a_rejected_attempt():
    step = record(accepted=0)
    with pytest.raises(ValueError, match="continued after rejection"):
        summarize_rc_control_iteration_cost(step)


def test_boolean_later_source_iteration_is_not_an_integer_index():
    step = record(base=1)
    step["trial_solution"]["metrics"]["terminal_polishing"]["attempts"][1][
        "source_iteration"
    ] = True
    with pytest.raises(ValueError):
        summarize_rc_control_iteration_cost(sign(step))


def test_actual_retained_solver_records_reconcile_without_reexecution(tmp_path):
    from structural_analysis.api.rc_fiber_frame_direct_control_request import (
        BoundedRCFiberDirectControlRequest,
    )
    from structural_analysis.benchmark import rc_control_learning as learning
    from structural_analysis.benchmark import rc_control_seed_runtime as runtime
    from structural_analysis.io.neutral.loader import load_neutral_json

    model = load_neutral_json(
        Path("examples/public_rc_fiber_frame_l_frame_material_history.json")
    )
    request = BoundedRCFiberDirectControlRequest(7, (-1e-6, -2e-6, -3e-6))
    request = replace(
        request,
        solver_config=replace(
            request.solver_config,
            newton=replace(request.solver_config.newton, terminal_polishing=True),
        ),
    )
    runtime.benchmark_rc_control_seed_paths(
        model,
        request,
        source_revision="a" * 40,
        output_directory=tmp_path / "original",
        **learning._arithmetic_kwargs(learning.RETAINED_LEARNING_ARITHMETIC_PROFILE),
    )
    steps = list((tmp_path / "original").glob("*/???-?-step.json"))
    assert len(steps) == 9
    for path in steps:
        original = path.read_bytes()
        step = json.loads(original)
        report = summarize_rc_control_iteration_cost(step)
        assert (
            report["primary_convergence_rows"] + report["accepted_terminal_corrections"]
            == report["inclusive_convergence_rows"]
        )
        assert report["total_solver_assembly_calls"] is None
        assert path.read_bytes() == original
