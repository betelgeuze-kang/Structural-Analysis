"""Unit tests for phase3 mega NDTHA halo coupling primitives."""
from __future__ import annotations

import numpy as np

from run_mega_ndtha_partitioned_stress import _compute_partition_coupling_forces


def test_two_partition_coupling_force_balance():
    top = np.array([0.10, -0.20], dtype=np.float64)
    coupling_k = np.array([2.0, 4.0], dtype=np.float64)
    net, metrics = _compute_partition_coupling_forces(top, coupling_k)

    # Single edge with averaged stiffness for 2 partitions.
    expected_k = 0.5 * (2.0 + 4.0)
    expected_f01 = expected_k * float(top[1] - top[0])
    assert net.shape == (2,)
    assert float(net[0]) == expected_f01
    assert float(net[1]) == -expected_f01
    assert abs(float(np.sum(net))) < 1e-12
    assert metrics["force_balance_residual"] < 1e-12
    assert metrics["edge_count"] == 1


def test_ring_coupling_force_balance_three_partitions():
    top = np.array([0.0, 0.12, -0.05], dtype=np.float64)
    coupling_k = np.array([10.0, 8.0, 12.0], dtype=np.float64)
    net, metrics = _compute_partition_coupling_forces(top, coupling_k)

    assert net.shape == (3,)
    assert np.isfinite(net).all()
    assert abs(float(np.sum(net))) < 1e-12
    assert metrics["max_gap_abs_m"] > 0.0
    assert metrics["max_edge_force_abs_n"] > 0.0
    assert metrics["force_balance_residual"] < 1e-12
    assert metrics["edge_count"] == 3
