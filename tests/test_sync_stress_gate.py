from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


GATE = Path("implementation/phase1/run_sync_stress_gate.py")


def _write_partition_report(path: Path) -> None:
    payload = {
        "schema_version": "1.0",
        "run_id": "phase3-partitioned-scaleout",
        "generated_at": "2026-03-01T00:00:00+00:00",
        "contract_pass": True,
        "reason_code": "PASS",
        "reason": "ok",
        "checks": {
            "pr_scale_pass": True,
            "nightly_scale_pass": True,
            "gpu_strict_required": True,
            "gpu_strict_pass": True,
            "on_scaling_regression_pass": True,
            "real_graph_required": True,
            "real_graph_used": True,
        },
        "level_rows": [
            {
                "node_count": 1000000,
                "partition_report": str(path.parent / "partition_quality_1m.json"),
            },
            {
                "node_count": 3000000,
                "partition_report": str(path.parent / "partition_quality_3m.json"),
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_partition_quality(path: Path, node_count: int) -> None:
    payload = {
        "schema_version": "1.0",
        "run_id": "phase3-graph-partition-metis",
        "generated_at": "2026-03-01T00:00:00+00:00",
        "contract_pass": True,
        "reason_code": "PASS",
        "reason": "ok",
        "result": {
            "node_count": int(node_count),
            "partition_sizes": [node_count // 4] * 4,
            "estimated_comm_bytes": float(node_count * 2.0),
            "halo_node_ratio": 0.02,
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_topology(path: Path) -> None:
    payload = {
        "schema_version": "1.0",
        "run_id": "phase3-opensees-topology-parser",
        "generated_at": "2026-03-01T00:00:00+00:00",
        "contract_pass": True,
        "reason_code": "PASS",
        "reason": "ok",
        "checks": {"real_topology_pass": True},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_sync_stress_gate_passes_for_pr_required_levels(tmp_path: Path) -> None:
    partitioned = tmp_path / "partitioned.json"
    pq1 = tmp_path / "partition_quality_1m.json"
    pq3 = tmp_path / "partition_quality_3m.json"
    topology = tmp_path / "topology.json"
    out = tmp_path / "sync_gate.json"

    _write_partition_quality(pq1, 1000000)
    _write_partition_quality(pq3, 3000000)
    _write_partition_report(partitioned)
    _write_topology(topology)

    cmd = [
        sys.executable,
        str(GATE),
        "--partitioned-scaleout",
        str(partitioned),
        "--topology-report",
        str(topology),
        "--require-topology-gate",
        "--ci-mode",
        "pr",
        "--steps",
        "40",
        "--work-dir",
        str(tmp_path / "sync_work"),
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert report["checks"]["required_levels_sync_pass"] is True
    assert report["checks"]["sync_stall_budget_pass"] is True
    assert report["checks"]["virtual_sync_blocked_pass"] is True
    assert report["checks"]["feti_profile_pass"] is True


def test_sync_stress_gate_blocks_virtual_backend_by_default(tmp_path: Path) -> None:
    partitioned = tmp_path / "partitioned.json"
    pq1 = tmp_path / "partition_quality_1m.json"
    pq3 = tmp_path / "partition_quality_3m.json"
    topology = tmp_path / "topology.json"
    out = tmp_path / "sync_gate.json"

    _write_partition_quality(pq1, 1000000)
    _write_partition_quality(pq3, 3000000)
    _write_partition_report(partitioned)
    _write_topology(topology)

    cmd = [
        sys.executable,
        str(GATE),
        "--partitioned-scaleout",
        str(partitioned),
        "--topology-report",
        str(topology),
        "--sync-backend",
        "virtual",
        "--require-topology-gate",
        "--ci-mode",
        "pr",
        "--steps",
        "40",
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode != 0

    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["reason_code"] == "ERR_BACKEND_POLICY"
    assert report["checks"]["virtual_sync_blocked_pass"] is False


def test_sync_stress_gate_fails_feti_profile(tmp_path: Path) -> None:
    partitioned = tmp_path / "partitioned.json"
    pq1 = tmp_path / "partition_quality_1m.json"
    pq3 = tmp_path / "partition_quality_3m.json"
    topology = tmp_path / "topology.json"
    out = tmp_path / "sync_gate.json"

    _write_partition_quality(pq1, 1000000)
    _write_partition_quality(pq3, 3000000)
    _write_partition_report(partitioned)
    _write_topology(topology)

    cmd = [
        sys.executable,
        str(GATE),
        "--partitioned-scaleout",
        str(partitioned),
        "--topology-report",
        str(topology),
        "--require-topology-gate",
        "--ci-mode",
        "pr",
        "--strict-feti-profile",
        "--bandwidth-gbps",
        "10.0",
        "--steps",
        "40",
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode != 0

    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["reason_code"] == "ERR_BACKEND_POLICY"
    assert report["checks"]["feti_profile_pass"] is False
