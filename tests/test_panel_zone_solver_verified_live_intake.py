from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "panel_zone_3d"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_module():
    module_path = Path(__file__).resolve().parents[1] / "implementation/phase1/run_panel_zone_solver_verified_live_intake.py"
    sys.path.insert(0, str(module_path.parent))
    spec = importlib.util.spec_from_file_location("panel_zone_solver_verified_live_intake_module", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _stage_drop(tmp_path: Path, drop_name: str) -> Path:
    inbox = tmp_path / "inbox"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/stage_panel_zone_solver_verified_drop.py",
            "--source-drop-dir",
            str(FIXTURE_DIR / drop_name),
            "--inbox-dir",
            str(inbox),
            "--clean",
            "--out",
            str(tmp_path / "stage_report.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    return inbox


def test_panel_zone_solver_verified_live_intake_dry_run_allows_trusted_input(tmp_path: Path) -> None:
    inbox = _stage_drop(tmp_path, "trusted_drop_package")
    out = tmp_path / "live_intake_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/run_panel_zone_solver_verified_live_intake.py",
            "--inbox-dir",
            str(inbox),
            "--archive-dir",
            str(tmp_path / "archive"),
            "--inbox-status-report",
            str(tmp_path / "inbox_status.json"),
            "--consume-report-out",
            str(tmp_path / "consume_report.json"),
            "--handoff-report-out",
            str(tmp_path / "handoff_report.json"),
            "--dry-run",
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = _load_json(out)
    assert payload["contract_pass"] is True
    assert payload["checks"]["trusted_source"] is True
    assert payload["summary"]["panel_zone_solver_verified_source_origin_class"] == "trusted_external_solver_source"
    assert payload["summary"]["panel_zone_solver_verified_inbox_status_mode"] == "pending_raw_triplet"


def test_panel_zone_solver_verified_live_intake_blocks_untrusted_input(tmp_path: Path) -> None:
    inbox = _stage_drop(tmp_path, "drop_package")
    out = tmp_path / "live_intake_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/run_panel_zone_solver_verified_live_intake.py",
            "--inbox-dir",
            str(inbox),
            "--archive-dir",
            str(tmp_path / "archive"),
            "--inbox-status-report",
            str(tmp_path / "inbox_status.json"),
            "--consume-report-out",
            str(tmp_path / "consume_report.json"),
            "--handoff-report-out",
            str(tmp_path / "handoff_report.json"),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    payload = _load_json(out)
    assert payload["reason_code"] == "ERR_UNTRUSTED_SOURCE"
    assert payload["checks"]["pending_input"] is True
    assert payload["checks"]["trusted_source"] is False
    assert payload["summary"]["panel_zone_solver_verified_source_origin_class"] == "fixture_sample"


def test_panel_zone_solver_verified_live_intake_reports_no_pending_input(tmp_path: Path) -> None:
    out = tmp_path / "live_intake_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/run_panel_zone_solver_verified_live_intake.py",
            "--inbox-dir",
            str(tmp_path / "empty_inbox"),
            "--archive-dir",
            str(tmp_path / "archive"),
            "--inbox-status-report",
            str(tmp_path / "inbox_status.json"),
            "--consume-report-out",
            str(tmp_path / "consume_report.json"),
            "--handoff-report-out",
            str(tmp_path / "handoff_report.json"),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    payload = _load_json(out)
    assert payload["reason_code"] == "ERR_NO_PENDING_INPUT"
    assert payload["checks"]["pending_input"] is False


def test_panel_zone_solver_verified_live_intake_allow_untrusted_source_runs_consume_step(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_module()
    inbox_status_report = tmp_path / "inbox_status.json"
    consume_report = tmp_path / "consume_report.json"
    handoff_report = tmp_path / "handoff_report.json"
    out = tmp_path / "live_intake_report.json"
    commands: list[list[str]] = []

    def fake_run(cmd: list[str], *, dry_run: bool = False) -> dict:
        del dry_run
        commands.append(list(cmd))
        script_name = Path(cmd[1]).name
        if script_name == "generate_panel_zone_solver_verified_inbox_status.py":
            module._write_json(
                Path(cmd[cmd.index("--out") + 1]),
                {
                    "contract_pass": True,
                    "summary": {
                        "panel_zone_solver_verified_pending_input": True,
                        "panel_zone_solver_verified_source_origin_class": "fixture_sample",
                        "panel_zone_solver_verified_release_refresh_source_allowed": False,
                        "panel_zone_solver_verified_inbox_status_mode": "pending_raw_triplet",
                        "panel_zone_solver_verified_recommended_action": "consume_pending_input",
                    },
                },
            )
        elif script_name == "consume_panel_zone_solver_verified_inbox.py":
            module._write_json(
                Path(cmd[cmd.index("--out") + 1]),
                {
                    "contract_pass": True,
                    "reason_code": "PASS",
                    "summary": {},
                },
            )
            module._write_json(
                Path(cmd[cmd.index("--handoff-report-out") + 1]),
                {
                    "contract_pass": True,
                    "summary": {},
                },
            )
        else:
            raise AssertionError(f"unexpected command: {cmd}")
        return {
            "command": " ".join(cmd),
            "return_code": 0,
            "ok": True,
            "status": "ok",
            "stdout_tail": "",
            "stderr_tail": "",
        }

    monkeypatch.setattr(module, "_run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_panel_zone_solver_verified_live_intake.py",
            "--inbox-dir",
            str(tmp_path / "inbox"),
            "--archive-dir",
            str(tmp_path / "archive"),
            "--inbox-status-report",
            str(inbox_status_report),
            "--consume-report-out",
            str(consume_report),
            "--handoff-report-out",
            str(handoff_report),
            "--allow-untrusted-source",
            "--out",
            str(out),
        ],
    )

    module.main()

    payload = _load_json(out)
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["checks"]["trusted_source"] is False
    assert payload["summary"]["panel_zone_solver_verified_source_origin_class"] == "fixture_sample"
    consume_cmd = next(cmd for cmd in commands if Path(cmd[1]).name == "consume_panel_zone_solver_verified_inbox.py")
    assert "--refresh-release-surfaces" in consume_cmd
    assert "--refresh-external-validation" in consume_cmd
    assert "--archive-on-success" in consume_cmd
    assert "--clean-inbox-on-success" in consume_cmd
