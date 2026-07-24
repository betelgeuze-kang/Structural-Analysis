from pathlib import Path

source_path = Path(
    "src/structural_analysis/assembly/stateful_corotational_fiber_frame2d_j1_j5.py"
)
source = source_path.read_text(encoding="utf-8")
old = '''def _validate_portal_profile(
    problem: StatefulCorotationalFiberFrame2DProblem,
) -> tuple[tuple[int, int], tuple[int, int]]:
    coordinates = problem.node_coordinates_m
    if len(coordinates) != 4 or len(problem.members) != 3:
'''
new = '''def _validate_portal_profile(
    problem: StatefulCorotationalFiberFrame2DProblem,
) -> tuple[tuple[int, int], tuple[int, int]]:
    coordinates = problem.node_coordinates_m
    if problem.prescribed_displacements:
        _fail(
            "corotational_portal_prescribed_displacement_unsupported",
            "/prescribed_displacements",
            "The v1 portal profile requires zero prescribed displacement.",
        )
    if len(coordinates) != 4 or len(problem.members) != 3:
'''
if source.count(old) != 1:
    raise SystemExit(f"source replacement count was {source.count(old)} instead of 1")
source_path.write_text(source.replace(old, new), encoding="utf-8")

test_path = Path("tests/test_corotational_fiber_frame_j1_j5.py")
tests = test_path.read_text(encoding="utf-8")
marker = '''        (
            replace(_portal_problem(), reference_external_loads=((0, 20.0),)),
            "corotational_portal_load_location_invalid",
        ),
        (
            _portal_problem(
'''
replacement = '''        (
            replace(_portal_problem(), reference_external_loads=((0, 20.0),)),
            "corotational_portal_load_location_invalid",
        ),
        (
            replace(
                _portal_problem(),
                prescribed_displacements=((0, 1.0e-4),),
            ),
            "corotational_portal_prescribed_displacement_unsupported",
        ),
        (
            _portal_problem(
'''
if tests.count(marker) != 1:
    raise SystemExit(f"test replacement count was {tests.count(marker)} instead of 1")
test_path.write_text(tests.replace(marker, replacement), encoding="utf-8")
