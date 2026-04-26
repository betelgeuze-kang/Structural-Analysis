from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("implementation/phase1/run_solver_truthfulness_gate.py")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _runtime_truthfulness_payload(*, runtime_kind: str, runtime_backend: str, surrogate: bool = False, cpu_fallback: bool = False) -> dict:
    return {
        "runtime_kind": runtime_kind,
        "runtime_backend": runtime_backend,
        "surrogate_runtime_used": bool(surrogate),
        "simplified_runtime_used": False,
        "surrogate_runtime_markers": ["surrogate_update"] if surrogate else [],
        "cpu_backend": False,
        "cpu_required": False,
        "cpu_fallback_used": bool(cpu_fallback),
    }


def _top_level_truthful_report(
    *,
    run_id: str,
    summary_line: str,
    runtime_kind: str,
    runtime_backend: str,
    surrogate: bool = False,
    cpu_fallback: bool = False,
) -> dict:
    runtime_truthfulness = _runtime_truthfulness_payload(
        runtime_kind=runtime_kind,
        runtime_backend=runtime_backend,
        surrogate=surrogate,
        cpu_fallback=cpu_fallback,
    )
    checks = {
        "runtime_truthfulness_pass": not surrogate and not cpu_fallback,
        "no_surrogate_runtime_markers_pass": not surrogate,
        "no_cpu_fallback_pass": not cpu_fallback,
    }
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "generated_at": "2026-03-30T00:00:00+00:00",
        "contract_pass": not surrogate and not cpu_fallback,
        "reason_code": "PASS" if not surrogate and not cpu_fallback else "ERR_SOLVER_TRUTHFULNESS_FAIL",
        "reason": "truthful runtime path verified" if not surrogate and not cpu_fallback else "truthfulness contract failed",
        "summary_line": summary_line,
        "checks": checks,
        "summary": {
            "runtime_report_count": 1,
            "truthful_runtime_count": 1 if not surrogate and not cpu_fallback else 0,
            "surrogate_marker_count": 0 if not surrogate else 1,
            "cpu_fallback_count": 0 if not cpu_fallback else 1,
        },
        "runtime_truthfulness": runtime_truthfulness,
    }


def test_solver_truthfulness_gate_passes_with_explicit_runtime_paths(tmp_path: Path) -> None:
    winning_ticket = tmp_path / "winning_ticket_backprop_report.json"
    physics_branching = tmp_path / "physics_branching_report.json"
    track_dataset = tmp_path / "track_dynamics_dataset_report.json"
    tunnel_dataset = tmp_path / "tunnel_dynamics_dataset_report.json"
    out = tmp_path / "solver_truthfulness_gate_report.json"

    truthful_summary = "Solver truthfulness: PASS | reports=4/4 | explicit=4/4 | surrogate_free=4/4 | cpu_fallback=0/4"
    _write_json(
        winning_ticket,
        _top_level_truthful_report(
            run_id="topk-weighted-backprop",
            summary_line=truthful_summary,
            runtime_kind="explicit_physical_branching",
            runtime_backend="hip",
        ),
    )
    _write_json(
        physics_branching,
        _top_level_truthful_report(
            run_id="pgob-branching",
            summary_line=truthful_summary,
            runtime_kind="explicit_physical_branching",
            runtime_backend="hip",
        ),
    )
    _write_json(
        track_dataset,
        _top_level_truthful_report(
            run_id="phase1-generate-track-dynamics-dataset",
            summary_line=truthful_summary,
            runtime_kind="explicit_physical_dataset",
            runtime_backend="numpy",
        ),
    )
    _write_json(
        tunnel_dataset,
        _top_level_truthful_report(
            run_id="phase1-generate-tunnel-dynamics-dataset",
            summary_line=truthful_summary,
            runtime_kind="explicit_physical_dataset",
            runtime_backend="numpy",
        ),
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--winning-ticket-backprop-report",
            str(winning_ticket),
            "--physics-branching-report",
            str(physics_branching),
            "--track-dynamics-dataset-report",
            str(track_dataset),
            "--tunnel-dynamics-dataset-report",
            str(tunnel_dataset),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["summary_line"].startswith("Solver truthfulness: PASS")
    assert "explicit=4/4" in payload["summary_line"]
    assert "surrogate_free=4/4" in payload["summary_line"]
    assert "cpu_fallback=0/4" in payload["summary_line"]
    assert payload["checks"]["runtime_truthfulness_pass"] is True
    assert payload["checks"]["no_surrogate_runtime_markers_pass"] is True
    assert payload["checks"]["no_cpu_fallback_pass"] is True
    assert payload["summary"]["runtime_report_count"] == 4
    assert payload["summary"]["truthful_runtime_count"] == 4
    assert payload["summary"]["surrogate_marker_count"] == 0
    assert payload["summary"]["cpu_fallback_count"] == 0


def test_solver_truthfulness_gate_flags_surrogate_runtime_as_failure(tmp_path: Path) -> None:
    winning_ticket = tmp_path / "winning_ticket_backprop_report.json"
    physics_branching = tmp_path / "physics_branching_report.json"
    track_dataset = tmp_path / "track_dynamics_dataset_report.json"
    tunnel_dataset = tmp_path / "tunnel_dynamics_dataset_report.json"
    out = tmp_path / "solver_truthfulness_gate_report.json"

    truthful_summary = "Solver truthfulness: GAP | reports=4/4 | explicit=3/4 | surrogate_free=3/4 | cpu_fallback=0/4"
    _write_json(
        winning_ticket,
        _top_level_truthful_report(
            run_id="topk-weighted-backprop",
            summary_line=truthful_summary,
            runtime_kind="explicit_physical_branching",
            runtime_backend="hip",
            surrogate=True,
        ),
    )
    _write_json(
        physics_branching,
        _top_level_truthful_report(
            run_id="pgob-branching",
            summary_line=truthful_summary,
            runtime_kind="explicit_physical_branching",
            runtime_backend="hip",
        ),
    )
    _write_json(
        track_dataset,
        _top_level_truthful_report(
            run_id="phase1-generate-track-dynamics-dataset",
            summary_line=truthful_summary,
            runtime_kind="explicit_physical_dataset",
            runtime_backend="numpy",
        ),
    )
    _write_json(
        tunnel_dataset,
        _top_level_truthful_report(
            run_id="phase1-generate-tunnel-dynamics-dataset",
            summary_line=truthful_summary,
            runtime_kind="explicit_physical_dataset",
            runtime_backend="numpy",
        ),
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--winning-ticket-backprop-report",
            str(winning_ticket),
            "--physics-branching-report",
            str(physics_branching),
            "--track-dynamics-dataset-report",
            str(track_dataset),
            "--tunnel-dynamics-dataset-report",
            str(tunnel_dataset),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )

    assert proc.returncode != 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_SOLVER_TRUTHFULNESS_FAIL"
    assert payload["summary_line"].startswith("Solver truthfulness: GAP")
    assert payload["checks"]["runtime_truthfulness_pass"] is False
    assert payload["checks"]["no_surrogate_runtime_markers_pass"] is False
    assert payload["summary"]["surrogate_marker_count"] == 1
