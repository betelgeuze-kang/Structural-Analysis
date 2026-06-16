from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_runtime_memory_release_budget_report.py"
SPEC = importlib.util.spec_from_file_location("build_runtime_memory_release_budget_report", SCRIPT_PATH)
assert SPEC is not None
build_runtime_memory_release_budget_report = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_runtime_memory_release_budget_report)


def _write(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_runtime_memory_release_budget_report_passes_with_clean_runtime_rows(tmp_path: Path) -> None:
    nightly = _write(
        tmp_path / "nightly.json",
        {
            "summary": {"latency_10m_mean_ms": 4200, "working_set_10m_mean_mb": 900},
            "rows": [{"seconds": 12, "return_code": 0, "stderr_tail": "", "stdout_tail": ""}],
        },
    )
    _write(
        tmp_path / "release" / "phase3_nightly_hardening_1" / "nightly_10m_repro_report.json",
        {
            "summary": {"latency_10m_mean_ms": 4300, "working_set_10m_mean_mb": 950},
            "rows": [{"seconds": 14, "return_code": 0, "stderr_tail": "", "stdout_tail": ""}],
        },
    )
    workstation = _write(
        tmp_path / "workstation.json",
        {
            "contract_pass": True,
            "performance_budget": {
                "viewer_ready_ms": 5000,
                "viewer_max_ready_ms": 60000,
                "memory_budget_gib": {"available_total_gib": 16},
            },
        },
    )
    ndtha = _write(
        tmp_path / "ndtha.json",
        {
            "summary": {"peak_vram_mb_mean": 0},
            "rows": [{"elapsed_wall_s": 100, "stderr_tail": "", "stdout_tail": ""}],
        },
    )

    payload = build_runtime_memory_release_budget_report.build_report(
        nightly_10m_path=nightly,
        nightly_history_root=tmp_path / "release",
        workstation_budget_path=workstation,
        ndtha_long_profile_path=ndtha,
        nightly_10m_latency_budget_ms=6000,
        nightly_10m_command_budget_seconds=60,
        ndtha_runtime_budget_seconds=180,
    )

    assert payload["contract_pass"] is True
    assert payload["summary"]["p95_runtime_budget_exceed_rate"] == 0.0
    assert payload["summary"]["oom_count"] == 0


def test_runtime_memory_release_budget_report_blocks_oom_signature(tmp_path: Path) -> None:
    nightly = _write(
        tmp_path / "nightly.json",
        {
            "summary": {"latency_10m_mean_ms": 4200, "working_set_10m_mean_mb": 900},
            "rows": [{"seconds": 12, "stderr_tail": "CUDA out of memory", "stdout_tail": ""}],
        },
    )
    workstation = _write(
        tmp_path / "workstation.json",
        {
            "performance_budget": {
                "viewer_ready_ms": 5000,
                "viewer_max_ready_ms": 60000,
                "memory_budget_gib": {"available_total_gib": 16},
            },
        },
    )
    ndtha = _write(tmp_path / "ndtha.json", {"summary": {"peak_vram_mb_mean": 0}, "rows": [{"elapsed_wall_s": 100}]})

    payload = build_runtime_memory_release_budget_report.build_report(
        nightly_10m_path=nightly,
        nightly_history_root=tmp_path / "release",
        workstation_budget_path=workstation,
        ndtha_long_profile_path=ndtha,
        nightly_10m_latency_budget_ms=6000,
        nightly_10m_command_budget_seconds=60,
        ndtha_runtime_budget_seconds=180,
    )

    assert payload["contract_pass"] is False
    assert payload["summary"]["oom_count"] == 1
    assert "oom_zero_pass" in payload["blockers"]
