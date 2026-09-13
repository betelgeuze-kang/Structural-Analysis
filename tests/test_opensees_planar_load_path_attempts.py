"""Execute the real embedded planar driver blocks with injected solver failures."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / (
    "scripts/run_external_code_to_code_technical_receipt.py"
)
CASES = (
    "public_corotational_portal",
    "bounded_planar_member_feature",
    "bounded_planar_settlement",
)


class RevertingSolver:
    """A failed call reverts to the last accepted factor, as OpenSees does."""

    def __init__(self, failed_step: int | None) -> None:
        self.failed_step = failed_step
        self.calls = 0
        self.factor = 0.0

    def analyze(self, count: int) -> int:
        assert count == 1
        ordinal = self.calls
        self.calls += 1
        if ordinal == self.failed_step:
            return -3
        self.factor += 0.25
        return 0

    def getTime(self) -> float:
        return self.factor

    def testIter(self) -> int:
        return 81 if self.calls - 1 == self.failed_step else 3

    def testNorms(self) -> list[float]:
        return [2.0e-8, 3.3e-10, 0.0]

    def eleResponse(self, *_args: Any) -> list[float]:
        return [0.0] * 6

    def __getattr__(self, _name: str) -> Any:
        return lambda *_args: 0.0


def _driver_case(case: str) -> ast.Module:
    script = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    driver = next(
        ast.literal_eval(node.value)
        for node in script.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(t, ast.Name) and t.id == "OPENSEES_DRIVER" for t in node.targets
        )
    )
    nodes = ast.parse(driver).body
    helper = next(
        node
        for node in nodes
        if isinstance(node, ast.FunctionDef) and node.name == "run_planar_load_path"
    )
    marker = f"{case}_analyze_codes"
    position = next(
        i
        for i, node in enumerate(nodes)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(t, ast.Subscript)
            and isinstance(t.slice, ast.Constant)
            and t.slice.value == marker
            for t in node.targets
        )
    )
    wipes = [
        i
        for i, node in enumerate(nodes)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and isinstance(node.value.func.value, ast.Name)
        and node.value.func.value.id == "ops"
        and node.value.func.attr == "wipe"
    ]
    start = max(i for i in wipes if i < position)
    end = min(i for i in wipes if i > position)
    return ast.Module(body=[helper, *nodes[start:end]], type_ignores=[])


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("failed_step", [None, 0, 1, 3])
def test_original_planar_blocks_stop_without_retries_and_retain_attempts(
    case: str,
    failed_step: int | None,
) -> None:
    ops = RevertingSolver(failed_step)
    clock = iter(range(100, 200, 7))
    payload: dict[str, Any] = {"load_path_attempts": {}}
    namespace = {"ops": ops, "payload": payload, "perf_counter_ns": lambda: next(clock)}
    exec(compile(_driver_case(case), str(SCRIPT), "exec"), namespace)

    expected_count = 4 if failed_step is None else failed_step + 1
    assert ops.calls == expected_count
    codes = payload[f"{case}_analyze_codes"]
    assert codes == [0] * (expected_count - 1) + [0 if failed_step is None else -3]
    attempts = payload["load_path_attempts"][case]
    assert len(attempts) == expected_count
    for index, attempt in enumerate(attempts):
        assert attempt["target_load_factor"] == (index + 1) / 4
        assert attempt["previous_load_factor"] == index / 4
        assert (
            attempt["achieved_load_factor"]
            == (index if index == failed_step else index + 1) / 4
        )
        assert attempt["analyze_return_code"] == codes[index]
        assert attempt["analyze_wall_ns"] == 7
        assert attempt["test_iterations_reported"] == (
            81 if index == failed_step else 3
        )
        assert attempt["test_norms_reported"] == [2.0e-8, 3.3e-10, 0.0]
    # Exercise the original receipt gate even if every numeric metric matches.
    gate = next(
        node
        for node in ast.parse(SCRIPT.read_text(encoding="utf-8")).body
        if isinstance(node, ast.FunctionDef) and node.name == "_case"
    )
    exec(
        compile(ast.Module(body=[gate], type_ignores=[]), str(SCRIPT), "exec"),
        namespace,
    )
    receipt_case = namespace["_case"](
        case_id=case,
        analysis_type="test",
        reference_solver="injected reverting solver",
        product_solver_id="test",
        metrics=[{"contract_pass": True}],
        external_return_code=max(abs(int(code)) for code in codes),
        product_regularization_applied=False,
        product_fallback_used=False,
    )
    assert receipt_case["contract_pass"] is (failed_step is None)
