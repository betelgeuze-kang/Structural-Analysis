from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from run_partitioned_scaleout import main as run_partitioned_scaleout_main


def _write_graph(path: Path, *, node_count: int) -> None:
    edges = [[i, i + 1] for i in range(node_count - 1)]
    path.write_text(
        json.dumps({"node_count": node_count, "edges": edges}, ensure_ascii=False),
        encoding="utf-8",
    )


def _fake_run_factory(*, cut_ratio: float = 0.02, halo_node_ratio: float = 0.05, feti_pass: bool = True) -> callable:
    def _fake_run(cmd: list[str]):
        out_path = ""
        is_partition = False
        is_feti = False
        for i, token in enumerate(cmd):
            if token == "--out" and i + 1 < len(cmd):
                out_path = cmd[i + 1]
            if "graph_partition_metis.py" in token:
                is_partition = True
            if "feti_lite_single_gpu.py" in token:
                is_feti = True

        if not out_path:
            raise RuntimeError("no --out captured")

        if is_partition:
            # partition pass payload
            payload = {
                "schema_version": "1.0",
                "contract_pass": True,
                "result": {
                    "partition_id_per_node": [0, 0, 1, 1],
                    "partition_sizes": [2, 2],
                    "cut_ratio": float(cut_ratio),
                    "halo_node_ratio": float(halo_node_ratio),
                    "partition_balance_ratio": 1.2,
                    "estimated_comm_bytes": 128,
                    "edge_cut_count": 1,
                },
            }
        elif is_feti:
            payload = {
                "schema_version": "1.0",
                "contract_pass": bool(feti_pass),
                "result": {
                    "backend": "feti_lite_boundary_sync",
                    "converged_step_ratio": 1.0 if feti_pass else 0.0,
                    "sync_stall_ratio": 0.2,
                    "p99_step_ms": 42.0,
                    "straggler_ratio": 1.2,
                    "comm_overlap_ratio": 0.6,
                    "p95_feti_iterations": 2.0,
                },
            }
        else:
            # scaleout pass payload
            payload = {
                "schema_version": "1.0",
                "contract_pass": True,
                "checks": {
                    "gpu_strict_pass": True,
                    "scaleout_1m_microbatch_pass": True,
                },
                "level_rows": [{"recommended_working_set_mb": 4.0, "recommended_avg_branch_ms": 0.1}],
            }
        Path(out_path).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return True, 0.01, 0, "", ""

    return _fake_run


@pytest.mark.parametrize(
    "dof_levels, sample_nodes, max_projection_ratio, expect_pass, expected_reason",
    [
        ("1000", "1000", 2.0, False, "ERR_REAL_GRAPH_FAIL"),
        ("1000000,3000000", "1000", 40000.0, True, "PASS"),
    ],
)
def test_partition_projection_ratio_gate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    dof_levels: str,
    sample_nodes: str,
    max_projection_ratio: float,
    expect_pass: bool,
    expected_reason: str,
) -> None:
    graph_path = tmp_path / "graph.json"
    _write_graph(graph_path, node_count=100)
    report_path = tmp_path / "partitioned_scaleout_report.json"
    work_dir = tmp_path / "work"

    # force fast path: replace external subprocess calls with deterministic fixtures
    monkeypatch.setattr("run_partitioned_scaleout._run", _fake_run_factory())
    monkeypatch.setattr("run_partitioned_scaleout._archive_outputs", lambda *_a, **_k: "")

    sys.argv = [
        "run_partitioned_scaleout.py",
        "--dof-levels",
        dof_levels,
        "--partitions",
        "4",
        "--branches",
        "4",
        "--edge-list-json",
        str(graph_path),
        "--require-real-graph",
        "--min-graph-nodes",
        "10",
        "--max-projection-ratio",
        str(max_projection_ratio),
        "--sample-nodes",
        sample_nodes,
        "--work-dir",
        str(work_dir),
        "--out",
        str(report_path),
        "--ci-mode",
        "pr",
    ]

    if expect_pass:
        run_partitioned_scaleout_main()
    else:
        with pytest.raises(SystemExit):
            run_partitioned_scaleout_main()

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is expect_pass
    assert payload["reason_code"] == expected_reason
    assert isinstance(payload.get("checks", {}).get("projection_ratio_pass"), bool)
    assert payload["checks"]["projection_ratio_pass"] is expect_pass
    assert payload.get("level_rows")
    assert all(row["projection_ratio_pass"] is expect_pass for row in payload["level_rows"])


def test_partition_quality_threshold_gate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.json"
    _write_graph(graph_path, node_count=100)
    report_path = tmp_path / "partitioned_scaleout_report.json"
    work_dir = tmp_path / "work"

    # Force partition contract pass but violate raw threshold to verify hard gate.
    monkeypatch.setattr(
        "run_partitioned_scaleout._run",
        _fake_run_factory(cut_ratio=0.50, halo_node_ratio=0.05),
    )
    monkeypatch.setattr("run_partitioned_scaleout._archive_outputs", lambda *_a, **_k: "")

    sys.argv = [
        "run_partitioned_scaleout.py",
        "--dof-levels",
        "1000000,3000000",
        "--partitions",
        "4",
        "--branches",
        "4",
        "--edge-list-json",
        str(graph_path),
        "--require-real-graph",
        "--min-graph-nodes",
        "10",
        "--max-projection-ratio",
        "40000",
        "--sample-nodes",
        "1000",
        "--edge-cut-ratio-max",
        "0.12",
        "--halo-node-ratio-max",
        "0.18",
        "--work-dir",
        str(work_dir),
        "--out",
        str(report_path),
        "--ci-mode",
        "pr",
    ]

    with pytest.raises(SystemExit):
        run_partitioned_scaleout_main()

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_PARTITION_FAIL"
    assert payload["checks"]["partition_quality_threshold_pass"] is False
    assert any(not row["partition_quality_threshold_pass"] for row in payload["level_rows"])


def test_partitioned_scaleout_requires_feti_for_3m(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.json"
    _write_graph(graph_path, node_count=100)
    report_path = tmp_path / "partitioned_scaleout_report.json"
    work_dir = tmp_path / "work"

    monkeypatch.setattr("run_partitioned_scaleout._run", _fake_run_factory(feti_pass=True))
    monkeypatch.setattr("run_partitioned_scaleout._archive_outputs", lambda *_a, **_k: "")

    sys.argv = [
        "run_partitioned_scaleout.py",
        "--dof-levels",
        "1000000,3000000",
        "--partitions",
        "4",
        "--branches",
        "4",
        "--edge-list-json",
        str(graph_path),
        "--require-real-graph",
        "--min-graph-nodes",
        "10",
        "--max-projection-ratio",
        "40000",
        "--sample-nodes",
        "1000",
        "--work-dir",
        str(work_dir),
        "--out",
        str(report_path),
        "--ci-mode",
        "pr",
        "--require-feti-at-or-above-dof",
        "3000000",
    ]

    run_partitioned_scaleout_main()
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    by_n = {int(row["node_count"]): row for row in payload["level_rows"]}
    assert by_n[1_000_000]["feti_required"] is False
    assert by_n[3_000_000]["feti_required"] is True
    assert by_n[3_000_000]["feti_sync_contract_pass"] is True
    assert payload["checks"]["feti_required_levels_pass"] is True
