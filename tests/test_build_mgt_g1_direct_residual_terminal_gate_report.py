from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "build_mgt_g1_direct_residual_terminal_gate_report.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_mgt_g1_direct_residual_terminal_gate_report",
    SCRIPT_PATH,
)
assert SPEC is not None
build_mgt_g1_direct_residual_terminal_gate_report = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_mgt_g1_direct_residual_terminal_gate_report)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _fixtures(tmp_path: Path, *, terminal_stop_reason: str = "residual_gate_stationary_no_descent_increment_gate_met") -> dict[str, Path]:
    direct = _write_json(
        tmp_path / "direct.json",
        {
            "schema_version": "mgt-direct-residual-newton-probe.v1",
            "status": "partial",
            "direct_residual_newton_ready": False,
            "final_direct_residual": {"direct_residual_inf_n": 1.0e-6},
            "gate_assessment": {
                "residual_tolerance_n": 1.0e-3,
                "direct_residual_gate_passed": True,
                "relative_increment_tolerance": 1.0e-4,
                "relative_increment_gate_verified": False,
            },
            "blockers": ["relative_increment_gate_not_closed_or_not_verified"],
        },
    )
    terminal = _write_json(
        tmp_path / "terminal.json",
        {
            "schema_version": "mgt-equilibrium-newton-focused-probe.v1",
            "status": "ready",
            "equilibrium_newton_ready": True,
            "blockers": [],
            "residual_tolerance_n": 5.0e-4,
            "final_residual_inf_n": 1.0e-6,
            "newton_iterations": [
                {
                    "relative_increment": 0.0,
                    "stop_reason": terminal_stop_reason,
                }
            ],
        },
    )
    summary = _write_json(
        tmp_path / "summary.json",
        {
            "schema_version": "mgt-g1-followup362-365-attached-equilibrium-newton-gate-summary.v1",
            "status": "partial",
            "latest_direct_residual_inf_n": 1.0e-6,
            "direct_residual_gate_passed": True,
            "direct_residual_gate_replay": {
                "gate_assessment": {"relative_increment_gate_verified": False}
            },
        },
    )
    return {"direct": direct, "terminal": terminal, "summary": summary}


def test_terminal_gate_report_cross_checks_direct_residual_and_increment_receipts(tmp_path: Path) -> None:
    fixtures = _fixtures(tmp_path)

    payload = build_mgt_g1_direct_residual_terminal_gate_report.build_report(
        direct_replay_path=fixtures["direct"],
        terminal_equilibrium_path=fixtures["terminal"],
        gate_summary_path=fixtures["summary"],
    )

    assert payload["status"] == "ready"
    assert payload["direct_residual_terminal_gate_ready"] is True
    assert payload["direct_residual_newton_gate_ready"] is True
    assert payload["checks"]["strict_residual_gate_passed"] is True
    assert payload["checks"]["terminal_increment_gate_passed"] is True
    assert "does not close full-mesh/full-load" in payload["claim_boundary"]


def test_terminal_gate_report_blocks_when_terminal_increment_is_not_verified(tmp_path: Path) -> None:
    fixtures = _fixtures(tmp_path, terminal_stop_reason="residual_gate_already_met")

    payload = build_mgt_g1_direct_residual_terminal_gate_report.build_report(
        direct_replay_path=fixtures["direct"],
        terminal_equilibrium_path=fixtures["terminal"],
        gate_summary_path=fixtures["summary"],
    )

    assert payload["status"] == "partial"
    assert payload["direct_residual_terminal_gate_ready"] is False
    assert "terminal_increment_gate_passed" in payload["blockers"]


def test_cli_writes_report_and_fails_when_blocked(tmp_path: Path) -> None:
    fixtures = _fixtures(tmp_path)
    out = tmp_path / "out.json"

    assert build_mgt_g1_direct_residual_terminal_gate_report.main(
        [
            "--direct-replay",
            str(fixtures["direct"]),
            "--terminal-equilibrium",
            str(fixtures["terminal"]),
            "--gate-summary",
            str(fixtures["summary"]),
            "--out",
            str(out),
            "--fail-blocked",
        ]
    ) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["direct_residual_terminal_gate_ready"] is True

    blocked = _fixtures(tmp_path / "blocked", terminal_stop_reason="residual_gate_already_met")
    assert build_mgt_g1_direct_residual_terminal_gate_report.main(
        [
            "--direct-replay",
            str(blocked["direct"]),
            "--terminal-equilibrium",
            str(blocked["terminal"]),
            "--gate-summary",
            str(blocked["summary"]),
            "--out",
            str(tmp_path / "blocked.json"),
            "--fail-blocked",
        ]
    ) == 1
