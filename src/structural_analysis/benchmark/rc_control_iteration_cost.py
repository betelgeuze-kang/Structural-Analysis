"""Separate recorded convergence rows from terminal refinement work.

A smaller inclusive iteration count can merely mean a terminal correction was
rejected after its assembly was already evaluated. These diagnostics perform no
solver calls and never infer total assembly work from convergence history.
"""

from structural_analysis.engine_v2.contracts._canonical import canonical_hash


def _natural(value):
    if type(value) is not int or value < 0:
        raise ValueError("nonnegative integer recorded count required")
    return value


def _boolean(value):
    if type(value) is not bool:
        raise ValueError("explicit recorded boolean required")
    return value


def summarize_rc_control_iteration_cost(step):
    """Read a committed retained-refinement record without granting authority.

    Original file provenance, physical correctness and whole-path benefit must
    be checked separately. Failed or missing records cannot become zero work.
    """
    try:
        return _summarize(step)
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError(
            "complete refinement and convergence records required"
        ) from exc


def _summarize(step):
    payload = dict(step)
    if payload.pop("step_hash") != canonical_hash(payload):
        raise ValueError("original step hash differs")
    if step["committed"] is not True:
        raise ValueError("committed original step required")
    trial = step["trial_solution"]
    metrics = trial["metrics"]
    history = trial["convergence_history"]
    polishing = metrics["terminal_polishing"]
    attempts = polishing["attempts"]
    if (
        polishing["schema_version"] != "newton-vector-terminal-refinement.v1"
        or type(history) is not list
        or not history
        or type(attempts) is not list
        or not attempts
        or len(attempts) > _natural(polishing["refinement_limit"])
    ):
        raise ValueError("bounded terminal-refinement history required")
    total = _natural(metrics["iteration_count"])
    if total != len(history) or total != _natural(metrics["newton_iteration_count"]):
        raise ValueError("inclusive iteration count differs from history")
    if [_natural(h["iteration"]) for h in history] != list(range(total)):
        raise ValueError("ordered complete convergence rows required")
    accepted = sum(_boolean(a["accepted"]) for a in attempts)
    attempted = sum(_boolean(a["attempted"]) for a in attempts)
    base = total - accepted
    if (
        base < 1
        or accepted != _natural(polishing["accepted_correction_count"])
        or attempted != _natural(polishing["attempt_count"])
        or _natural(attempts[0]["source_iteration"]) != base - 1
    ):
        raise ValueError("primary and terminal convergence counts differ")
    terminal_work = {}
    for field in (
        "assembly_call_count",
        "assembly_exception_count",
        "linear_solve_count",
        "linear_solve_exception_count",
    ):
        terminal_work[field] = sum(_natural(a[field]) for a in attempts)
        if terminal_work[field] != _natural(polishing[field]):
            raise ValueError("terminal work total differs from attempts")
    next_iteration = base
    for i, attempt in enumerate(attempts):
        source_iteration = _natural(attempt["source_iteration"])
        if i and (
            not attempts[i - 1]["accepted"] or source_iteration != next_iteration - 1
        ):
            raise ValueError("refinement continued after rejection or changed origin")
        if attempt["accepted"]:
            if (
                not attempt["attempted"]
                or _natural(attempt["candidate_iteration"]) != next_iteration
            ):
                raise ValueError("accepted refinement must append its convergence row")
            next_iteration += 1
    linear = _natural(metrics["linear_solve_count"])
    if linear != base + terminal_work["linear_solve_count"]:
        raise ValueError("primary and terminal linear solve counts differ")
    searches = trial["line_search_history"]
    if type(searches) is not list or len(searches) != _natural(
        metrics["line_search_step_count"]
    ):
        raise ValueError("line-search step count differs")
    trials = 0
    seen = set()
    for search in searches:
        index = _natural(search["iteration"])
        if index >= base or index in seen:
            raise ValueError("line search must belong to one primary iteration")
        seen.add(index)
        count = _natural(search["attempt_count"])
        if type(search["attempts"]) is not list or count != len(search["attempts"]):
            raise ValueError("line-search trial count differs")
        trials += count
    return {
        "schema_version": "rc-control-recorded-iteration-cost.v1",
        "source_step_hash": step["step_hash"],
        "inclusive_convergence_rows": total,
        "primary_convergence_rows": base,
        "accepted_terminal_corrections": accepted,
        "attempted_terminal_refinements": attempted,
        "terminal_assembly_calls": terminal_work["assembly_call_count"],
        "terminal_assembly_exceptions": terminal_work["assembly_exception_count"],
        "terminal_linear_solves": terminal_work["linear_solve_count"],
        "terminal_linear_solve_exceptions": terminal_work[
            "linear_solve_exception_count"
        ],
        "total_recorded_linear_solves": linear,
        "line_search_steps": len(searches),
        "line_search_trials": trials,
        "total_solver_assembly_calls": None,
        "total_assembly_work_inferred_from_history": False,
        "source_file_authentication": False,
        "physical_validation": False,
        "performance_improvement": False,
        "training_admitted": False,
    }
