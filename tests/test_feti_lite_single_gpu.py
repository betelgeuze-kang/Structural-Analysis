from __future__ import annotations

from feti_lite_single_gpu import emulate_feti_sync


def _partition_report() -> dict:
    return {
        "schema_version": "1.0",
        "run_id": "phase3-graph-partition-metis",
        "contract_pass": True,
        "reason_code": "PASS",
        "result": {
            "node_count": 10000,
            "partition_sizes": [2500, 2500, 2500, 2500],
            "estimated_comm_bytes": 180000.0,
            "halo_node_ratio": 0.03,
        },
    }


def test_feti_lite_sync_returns_required_metrics():
    report = _partition_report()
    result = emulate_feti_sync(
        report,
        steps=60,
        dt_s=0.01,
        bandwidth_gbps=32.0,
        latency_us=40.0,
        compute_us_per_node=0.2,
        overlap_cap=0.7,
        jitter_pct=0.05,
        seed=23,
        max_feti_iters=12,
        gap_tol=8e-4,
        force_tol=1e-3,
        rho=0.6,
        relax=0.45,
        state_components=5,
    )
    for key in (
        "backend",
        "p99_step_ms",
        "sync_stall_ratio",
        "straggler_ratio",
        "comm_overlap_ratio",
        "converged_step_ratio",
        "max_gap_norm",
        "max_force_imbalance",
    ):
        assert key in result
    assert result["backend"] == "feti_lite_single_gpu"
    assert float(result["converged_step_ratio"]) >= 0.99
    assert float(result["max_gap_norm"]) <= 8e-4
    assert float(result["max_force_imbalance"]) <= 1e-3
