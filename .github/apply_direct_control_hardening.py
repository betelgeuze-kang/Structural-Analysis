from pathlib import Path

source_path = Path(
    "src/structural_analysis/assembly/"
    "stateful_corotational_fiber_frame2d_displacement_control.py"
)
source = source_path.read_text(encoding="utf-8")

helper_marker = '''def _controlled_free_index(
    problem: StatefulCorotationalFiberFrame2DProblem,
    control_global_dof: int,
) -> int:
    if type(control_global_dof) is not int:
        raise ValueError("control_global_dof must be an integer")
    if control_global_dof not in problem.free_global_dofs:
        raise ValueError("control_global_dof must be a free global DOF")
    if control_global_dof % 3 not in (0, 1):
        raise ValueError("control_global_dof must be translational UX or UY")
    return problem.free_global_dofs.index(control_global_dof)
'''
helper_replacement = helper_marker + '''

def _require_connected_member_graph(
    problem: StatefulCorotationalFiberFrame2DProblem,
) -> None:
    node_count = len(problem.node_coordinates_m)
    adjacency: list[set[int]] = [set() for _ in range(node_count)]
    for member in problem.members:
        adjacency[member.node_i].add(member.node_j)
        adjacency[member.node_j].add(member.node_i)
    visited = {0}
    frontier = [0]
    while frontier:
        node = frontier.pop()
        for neighbor in adjacency[node]:
            if neighbor not in visited:
                visited.add(neighbor)
                frontier.append(neighbor)
    if len(visited) != node_count:
        raise ValueError("problem member graph must be connected")
'''
if source.count(helper_marker) != 1:
    raise SystemExit("controlled-index helper marker did not match exactly once")
source = source.replace(helper_marker, helper_replacement)

solver_entry = '''    if type(step_problem) is not (
        StatefulCorotationalFiberFrame2DDisplacementControlStepProblem
    ):
        raise ValueError("step_problem type is invalid")
    config = step_problem.config
'''
solver_entry_replacement = '''    if type(step_problem) is not (
        StatefulCorotationalFiberFrame2DDisplacementControlStepProblem
    ):
        raise ValueError("step_problem type is invalid")
    _require_connected_member_graph(step_problem.problem)
    config = step_problem.config
'''
if source.count(solver_entry) != 1:
    raise SystemExit("solver entry marker did not match exactly once")
source = source.replace(solver_entry, solver_entry_replacement)

trial_block = '''        for alpha in config.line_search_alphas:
            trial_coordinates = coordinates + alpha * correction
            trial = step_problem.assemble(trial_coordinates)
            trial_merit = _merit(step_problem, trial)
            accepted = trial_merit < merit_before
            attempts.append(
                {
                    "alpha": alpha,
                    "trial_load_factor": (
                        float(trial_coordinates[-1])
                        / config.load_factor_coordinate_scale_m
                    ),
                    "trial_relative_equilibrium_residual": _relative_equilibrium(
                        step_problem,
                        trial,
                    ),
                    "trial_control_error_m": trial.control_error_m,
                    "trial_merit": trial_merit,
                    "accepted": accepted,
                }
            )
'''
trial_replacement = '''        for alpha in config.line_search_alphas:
            trial_coordinates = coordinates + alpha * correction
            try:
                trial = step_problem.assemble(trial_coordinates)
            except (TypeError, ValueError, ArithmeticError, AttributeError, LookupError):
                attempts.append(
                    {
                        "alpha": alpha,
                        "trial_load_factor": (
                            float(trial_coordinates[-1])
                            / config.load_factor_coordinate_scale_m
                        ),
                        "trial_relative_equilibrium_residual": None,
                        "trial_control_error_m": None,
                        "trial_merit": None,
                        "accepted": False,
                        "failure": "invalid_trial_assembly",
                    }
                )
                continue
            trial_merit = _merit(step_problem, trial)
            accepted = trial_merit < merit_before
            attempts.append(
                {
                    "alpha": alpha,
                    "trial_load_factor": (
                        float(trial_coordinates[-1])
                        / config.load_factor_coordinate_scale_m
                    ),
                    "trial_relative_equilibrium_residual": _relative_equilibrium(
                        step_problem,
                        trial,
                    ),
                    "trial_control_error_m": trial.control_error_m,
                    "trial_merit": trial_merit,
                    "accepted": accepted,
                }
            )
'''
if source.count(trial_block) != 1:
    raise SystemExit("line-search trial block did not match exactly once")
source = source.replace(trial_block, trial_replacement)

path_entry = '''    _controlled_free_index(problem, control_global_dof)
    targets = tuple(
'''
path_replacement = '''    _require_connected_member_graph(problem)
    _controlled_free_index(problem, control_global_dof)
    targets = tuple(
'''
if source.count(path_entry) != 1:
    raise SystemExit("path entry marker did not match exactly once")
source = source.replace(path_entry, path_replacement)
source_path.write_text(source, encoding="utf-8")

test_path = Path(
    "tests/test_stateful_corotational_fiber_frame2d_displacement_control.py"
)
tests = test_path.read_text(encoding="utf-8")
import_marker = '''    run_stateful_corotational_fiber_frame2d_displacement_control_path,
    solve_stateful_corotational_fiber_frame2d_displacement_control_step,
)
'''
import_replacement = '''    run_stateful_corotational_fiber_frame2d_displacement_control_path,
    solve_stateful_corotational_fiber_frame2d_displacement_control,
    solve_stateful_corotational_fiber_frame2d_displacement_control_step,
)
'''
if tests.count(import_marker) != 1:
    raise SystemExit("test import marker did not match exactly once")
tests = tests.replace(import_marker, import_replacement)

insertion_marker = '''def test_failed_direct_control_step_rolls_back_exact_parent() -> None:
'''
new_tests = '''def test_invalid_full_step_trial_is_rejected_and_backtracking_continues(
    monkeypatch,
) -> None:
    coordinates = ((0.0, 0.0), (1.0, 0.0))
    problem = StatefulCorotationalFiberFrame2DProblem(
        case_id="direct-control-invalid-full-alpha",
        node_coordinates_m=coordinates,
        members=(_member(coordinates, "bar", 0, 1),),
        fixed_global_dofs=(0, 1, 2, 4, 5),
        reference_external_loads=((3, 2.0),),
        rotation_coordinate_scale_m=1.0,
    )
    parent = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
    step_problem = StatefulCorotationalFiberFrame2DDisplacementControlStepProblem(
        problem=problem,
        accepted_checkpoint=parent,
        control_global_dof=3,
        target_control_displacement_m=1.0e-3,
        config=StatefulCorotationalFiberFrame2DDisplacementControlConfig(
            maximum_iterations=30,
        ),
    )
    step_type = StatefulCorotationalFiberFrame2DDisplacementControlStepProblem
    original_assemble = step_type.assemble
    call_count = 0

    def assemble_with_invalid_full_trial(self, coordinates_m):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise ValueError("synthetic collapsed trial chord")
        return original_assemble(self, coordinates_m)

    monkeypatch.setattr(step_type, "assemble", assemble_with_invalid_full_trial)
    solution = solve_stateful_corotational_fiber_frame2d_displacement_control(
        step_problem
    )

    assert solution.status == "ready"
    assert solution.metrics["contract_pass"] is True
    first_attempts = solution.line_search_history[0]["attempts"]
    assert first_attempts[0]["alpha"] == 1.0
    assert first_attempts[0]["accepted"] is False
    assert first_attempts[0]["failure"] == "invalid_trial_assembly"
    assert len(first_attempts) >= 2
    assert any(row["accepted"] is True for row in first_attempts[1:])


def test_direct_control_rejects_disconnected_member_graph() -> None:
    coordinates = ((0.0, 0.0), (1.0, 0.0), (3.0, 0.0), (4.0, 0.0))
    problem = StatefulCorotationalFiberFrame2DProblem(
        case_id="direct-control-disconnected",
        node_coordinates_m=coordinates,
        members=(
            _member(coordinates, "controlled", 0, 1),
            _member(coordinates, "isolated-fixed", 2, 3),
        ),
        fixed_global_dofs=(0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11),
        reference_external_loads=((3, 1.0),),
        rotation_coordinate_scale_m=1.0,
    )

    with pytest.raises(ValueError, match="member graph must be connected"):
        run_stateful_corotational_fiber_frame2d_displacement_control_path(
            problem,
            (1.0e-4,),
            control_global_dof=3,
        )


def test_failed_direct_control_step_rolls_back_exact_parent() -> None:
'''
if tests.count(insertion_marker) != 1:
    raise SystemExit("test insertion marker did not match exactly once")
tests = tests.replace(insertion_marker, new_tests)
test_path.write_text(tests, encoding="utf-8")
