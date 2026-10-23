"""Input/reference checks only; no GPU, compilation or protected input access."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

SPEC = importlib.util.spec_from_file_location(
    "hip_performance",
    Path(__file__).resolve().parents[1]
    / "scripts/benchmark_hip_residual_performance.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_generated_operator_matches_independent_element_scatter():
    case = MODULE.generated_case(24, 3)
    a = case["arrays"]
    expected = np.zeros_like(a["states"])
    for b, state in enumerate(a["states"]):
        for dofs, stiffness in zip(a["frame_dofs"], a["frame_stiffness"], strict=True):
            np.add.at(expected[b], dofs, stiffness @ state[dofs])
        for prefix in ("shell", "spring"):
            for row in range(case["dimension"]):
                begin, end = a[prefix + "_row_ptr"][row : row + 2]
                expected[b, row] += sum(
                    a[prefix + "_values"][p] * state[a[prefix + "_col_idx"][p]]
                    for p in range(begin, end)
                )
    expected -= a["external"]
    np.testing.assert_allclose(
        MODULE.cpu_residual(case), expected, rtol=1e-13, atol=1e-15
    )


def test_inputs_are_deterministic_and_hash_bound():
    one, two = MODULE.generated_case(24, 3), MODULE.generated_case(24, 3)
    assert one["input_hash"] == two["input_hash"]
    assert one["input_hash"] != MODULE.generated_case(24, 2)["input_hash"]
    assert one["input_bytes"] == sum(a.nbytes for a in one["arrays"].values())
    assert all(a.flags.c_contiguous for a in one["arrays"].values())


@pytest.mark.parametrize(
    "dimension,batch", [(True, 1), (6, 1), (13, 1), (24, False), (24, 0), (24, 65)]
)
def test_generated_input_limits(dimension, batch):
    with pytest.raises(ValueError):
        MODULE.generated_case(dimension, batch)


def test_timing_summary_keeps_dispersion_and_samples():
    value = MODULE.summarize([1, 3, 2])
    assert value["median"] == 2 and value["minimum"] == 1 and value["maximum"] == 3
    assert value["population_stdev"] > 0 and value["samples"] == [1, 3, 2]
