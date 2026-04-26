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
    module_path = Path(__file__).resolve().parents[1] / "implementation/phase1/consume_panel_zone_solver_verified_inbox.py"
    sys.path.insert(0, str(module_path.parent))
    spec = importlib.util.spec_from_file_location("consume_panel_zone_solver_verified_inbox_module", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _stage_into_inbox(tmp_path: Path, drop_dir_name: str = "drop_package") -> Path:
    inbox = tmp_path / "inbox"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/stage_panel_zone_solver_verified_drop.py",
            "--source-drop-dir",
            str(FIXTURE_DIR / drop_dir_name),
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


def test_consume_panel_zone_solver_verified_inbox_dry_run_uses_staged_inputs(tmp_path: Path) -> None:
    inbox = _stage_into_inbox(tmp_path)
    pbd = tmp_path / "pbd_review_package_report.json"
    pbd.write_text(json.dumps({"contract_pass": True}, ensure_ascii=False, indent=2), encoding="utf-8")
    consume_report = tmp_path / "consume_report.json"
    handoff_report = tmp_path / "handoff_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/consume_panel_zone_solver_verified_inbox.py",
            "--inbox-dir",
            str(inbox),
            "--handoff-report-out",
            str(handoff_report),
            "--design-optimization-dataset",
            str(FIXTURE_DIR / "design_optimization_dataset_report.json"),
            "--pbd-review-package",
            str(pbd),
            "--panel-zone-solver-export-bundle",
            str(tmp_path / "panel_zone_solver_verified_export_bundle.json"),
            "--panel-zone-joint-geometry-source-output",
            str(tmp_path / "panel_zone_joint_geometry_3d.json"),
            "--panel-zone-rebar-anchorage-source-output",
            str(tmp_path / "panel_zone_rebar_anchorage_3d.json"),
            "--panel-zone-clash-verification-source-output",
            str(tmp_path / "panel_zone_clash_verification_3d.json"),
            "--panel-zone-joint-geometry-contract",
            str(tmp_path / "panel_zone_joint_geometry_3d_contract.json"),
            "--panel-zone-rebar-anchorage-contract",
            str(tmp_path / "panel_zone_rebar_anchorage_3d_contract.json"),
            "--panel-zone-clash-verification-contract",
            str(tmp_path / "panel_zone_clash_verification_3d_contract.json"),
            "--panel-zone-clash-artifact",
            str(tmp_path / "panel_zone_clash_artifact.json"),
            "--panel-zone-clash-report",
            str(tmp_path / "panel_zone_clash_report.json"),
            "--dry-run",
            "--out",
            str(consume_report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    consume_payload = _load_json(consume_report)
    assert consume_payload["contract_pass"] is True
    assert consume_payload["reason_code"] == "PASS"
    assert consume_payload["summary"]["handoff_reason_code"] == "PASS"
    assert consume_payload["summary"]["source_origin_class"] == "fixture_sample"
    assert consume_payload["checks"]["handoff_contract_pass"] is True
    handoff_payload = _load_json(handoff_report)
    assert handoff_payload["contract_pass"] is True
    assert handoff_payload["summary"]["source_input_mode"] == "raw_sources"


def test_consume_panel_zone_solver_verified_inbox_archives_and_cleans_success(tmp_path: Path) -> None:
    inbox = _stage_into_inbox(tmp_path)
    pbd = tmp_path / "pbd_review_package_report.json"
    pbd.write_text(json.dumps({"contract_pass": True}, ensure_ascii=False, indent=2), encoding="utf-8")
    archive_dir = tmp_path / "archive"
    consume_report = tmp_path / "consume_report.json"
    handoff_report = tmp_path / "handoff_report.json"
    inbox_status_report = tmp_path / "inbox_status.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/consume_panel_zone_solver_verified_inbox.py",
            "--inbox-dir",
            str(inbox),
            "--handoff-report-out",
            str(handoff_report),
            "--inbox-status-report",
            str(inbox_status_report),
            "--design-optimization-dataset",
            str(FIXTURE_DIR / "design_optimization_dataset_report.json"),
            "--pbd-review-package",
            str(pbd),
            "--panel-zone-solver-export-bundle",
            str(tmp_path / "panel_zone_solver_verified_export_bundle.json"),
            "--panel-zone-joint-geometry-source-output",
            str(tmp_path / "panel_zone_joint_geometry_3d.json"),
            "--panel-zone-rebar-anchorage-source-output",
            str(tmp_path / "panel_zone_rebar_anchorage_3d.json"),
            "--panel-zone-clash-verification-source-output",
            str(tmp_path / "panel_zone_clash_verification_3d.json"),
            "--panel-zone-joint-geometry-contract",
            str(tmp_path / "panel_zone_joint_geometry_3d_contract.json"),
            "--panel-zone-rebar-anchorage-contract",
            str(tmp_path / "panel_zone_rebar_anchorage_3d_contract.json"),
            "--panel-zone-clash-verification-contract",
            str(tmp_path / "panel_zone_clash_verification_3d_contract.json"),
            "--panel-zone-clash-artifact",
            str(tmp_path / "panel_zone_clash_artifact.json"),
            "--panel-zone-clash-report",
            str(tmp_path / "panel_zone_clash_report.json"),
            "--archive-dir",
            str(archive_dir),
            "--archive-on-success",
            "--clean-inbox-on-success",
            "--out",
            str(consume_report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    consume_payload = _load_json(consume_report)
    assert consume_payload["contract_pass"] is True
    assert consume_payload["summary"]["source_origin_class"] == "fixture_sample"
    assert consume_payload["checks"]["status_refresh_pass"] is True
    archive_payload = consume_payload["artifacts"]["archive"]
    assert archive_payload["archive_dir"].startswith(str(archive_dir))
    archived_dir = Path(archive_payload["archive_dir"])
    assert (archived_dir / "joint_geometry.json").exists()
    assert (archived_dir / "rebar_anchorage.json").exists()
    assert (archived_dir / "clash_verification.json").exists()
    assert not (inbox / "joint_geometry.json").exists()
    assert not (inbox / "rebar_anchorage.json").exists()
    assert not (inbox / "clash_verification.json").exists()
    refreshed_status = _load_json(inbox_status_report)
    assert refreshed_status["summary"]["panel_zone_solver_verified_inbox_status_mode"] == "empty_after_successful_consume"
    assert refreshed_status["summary"]["panel_zone_solver_verified_recommended_action"] == "local_closeout_closed"


def test_consume_panel_zone_solver_verified_inbox_archives_member_mapping_sidecar_for_trusted_drop(tmp_path: Path) -> None:
    inbox = _stage_into_inbox(tmp_path, "trusted_drop_package")
    pbd = tmp_path / "pbd_review_package_report.json"
    pbd.write_text(json.dumps({"contract_pass": True}, ensure_ascii=False, indent=2), encoding="utf-8")
    archive_dir = tmp_path / "archive"
    consume_report = tmp_path / "consume_report.json"
    handoff_report = tmp_path / "handoff_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/consume_panel_zone_solver_verified_inbox.py",
            "--inbox-dir",
            str(inbox),
            "--handoff-report-out",
            str(handoff_report),
            "--inbox-status-report",
            str(tmp_path / "inbox_status.json"),
            "--design-optimization-dataset",
            "implementation/phase1/release/design_optimization/design_optimization_dataset_report.json",
            "--pbd-review-package",
            str(pbd),
            "--panel-zone-solver-export-bundle",
            str(tmp_path / "panel_zone_solver_verified_export_bundle.json"),
            "--panel-zone-joint-geometry-source-output",
            str(tmp_path / "panel_zone_joint_geometry_3d.json"),
            "--panel-zone-rebar-anchorage-source-output",
            str(tmp_path / "panel_zone_rebar_anchorage_3d.json"),
            "--panel-zone-clash-verification-source-output",
            str(tmp_path / "panel_zone_clash_verification_3d.json"),
            "--panel-zone-joint-geometry-contract",
            str(tmp_path / "panel_zone_joint_geometry_3d_contract.json"),
            "--panel-zone-rebar-anchorage-contract",
            str(tmp_path / "panel_zone_rebar_anchorage_3d_contract.json"),
            "--panel-zone-clash-verification-contract",
            str(tmp_path / "panel_zone_clash_verification_3d_contract.json"),
            "--panel-zone-clash-artifact",
            str(tmp_path / "panel_zone_clash_artifact.json"),
            "--panel-zone-clash-report",
            str(tmp_path / "panel_zone_clash_report.json"),
            "--archive-dir",
            str(archive_dir),
            "--archive-on-success",
            "--clean-inbox-on-success",
            "--out",
            str(consume_report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    consume_payload = _load_json(consume_report)
    archived_dir = Path(consume_payload["artifacts"]["archive"]["archive_dir"])
    assert (archived_dir / "member_mapping_sidecar.json").exists()
    assert not (inbox / "member_mapping_sidecar.json").exists()


def test_consume_panel_zone_solver_verified_inbox_dry_run_allows_trusted_release_refresh(tmp_path: Path) -> None:
    inbox = _stage_into_inbox(tmp_path, "trusted_drop_package")
    pbd = tmp_path / "pbd_review_package_report.json"
    pbd.write_text(json.dumps({"contract_pass": True}, ensure_ascii=False, indent=2), encoding="utf-8")
    consume_report = tmp_path / "consume_report.json"
    handoff_report = tmp_path / "handoff_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/consume_panel_zone_solver_verified_inbox.py",
            "--inbox-dir",
            str(inbox),
            "--handoff-report-out",
            str(handoff_report),
            "--design-optimization-dataset",
            str(FIXTURE_DIR / "design_optimization_dataset_report.json"),
            "--pbd-review-package",
            str(pbd),
            "--panel-zone-solver-export-bundle",
            str(tmp_path / "panel_zone_solver_verified_export_bundle.json"),
            "--panel-zone-joint-geometry-source-output",
            str(tmp_path / "panel_zone_joint_geometry_3d.json"),
            "--panel-zone-rebar-anchorage-source-output",
            str(tmp_path / "panel_zone_rebar_anchorage_3d.json"),
            "--panel-zone-clash-verification-source-output",
            str(tmp_path / "panel_zone_clash_verification_3d.json"),
            "--panel-zone-joint-geometry-contract",
            str(tmp_path / "panel_zone_joint_geometry_3d_contract.json"),
            "--panel-zone-rebar-anchorage-contract",
            str(tmp_path / "panel_zone_rebar_anchorage_3d_contract.json"),
            "--panel-zone-clash-verification-contract",
            str(tmp_path / "panel_zone_clash_verification_3d_contract.json"),
            "--panel-zone-clash-artifact",
            str(tmp_path / "panel_zone_clash_artifact.json"),
            "--panel-zone-clash-report",
            str(tmp_path / "panel_zone_clash_report.json"),
            "--refresh-release-surfaces",
            "--refresh-external-validation",
            "--dry-run",
            "--out",
            str(consume_report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    consume_payload = _load_json(consume_report)
    handoff_payload = _load_json(handoff_report)
    assert consume_payload["contract_pass"] is True
    assert consume_payload["summary"]["source_origin_class"] == "trusted_external_solver_source"
    assert handoff_payload["contract_pass"] is True
    assert handoff_payload["checks"]["release_refresh_source_allowed"] is True
    assert handoff_payload["summary"]["source_origin_class"] == "trusted_external_solver_source"
    assert handoff_payload["summary"]["release_surface_refresh_guard_status"] == "allowed"


def test_consume_panel_zone_solver_verified_inbox_uses_source_drop_dir_for_handoff_sidecar_compatibility(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_module()
    inbox = _stage_into_inbox(tmp_path, "trusted_drop_package")
    consume_report = tmp_path / "consume_report.json"
    handoff_report = tmp_path / "handoff_report.json"
    commands: list[list[str]] = []

    def fake_run(cmd: list[str]) -> dict:
        commands.append(list(cmd))
        script_name = Path(str(cmd[1])).name
        if script_name == "run_panel_zone_solver_verified_handoff.py":
            assert "--source-drop-dir" in cmd
            assert cmd[cmd.index("--source-drop-dir") + 1] == str(inbox)
            assert "--joint-geometry-source" not in cmd
            assert "--rebar-anchorage-source" not in cmd
            assert "--clash-verification-source" not in cmd
            assert "--member-mapping-sidecar" not in cmd
            module._write_json(
                handoff_report,
                {
                    "contract_pass": True,
                    "reason_code": "PASS",
                    "summary": {
                        "source_origin_class": "trusted_external_solver_source",
                        "panel_zone_constructability_mode": "panel_zone_3d_clash_and_anchorage_verified",
                        "panel_zone_source_contract_mode": "solver_verified_3d_source",
                    },
                },
            )
        elif script_name == "generate_panel_zone_solver_verified_inbox_status.py":
            out = Path(cmd[cmd.index("--out") + 1])
            module._write_json(
                out,
                {
                    "contract_pass": True,
                    "summary": {
                        "panel_zone_solver_verified_inbox_status_mode": "empty_after_successful_consume",
                        "panel_zone_solver_verified_pending_input": False,
                        "panel_zone_solver_verified_source_origin_class": "trusted_external_solver_source",
                        "panel_zone_solver_verified_recommended_action": "local_closeout_closed",
                    },
                },
            )
        else:
            raise AssertionError(f"unexpected command: {cmd}")
        return {
            "command": " ".join(cmd),
            "return_code": 0,
            "ok": True,
            "stdout_tail": "",
            "stderr_tail": "",
        }

    monkeypatch.setattr(module, "_run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "consume_panel_zone_solver_verified_inbox.py",
            "--inbox-dir",
            str(inbox),
            "--handoff-report-out",
            str(handoff_report),
            "--dry-run",
            "--out",
            str(consume_report),
        ],
    )

    module.main()

    payload = _load_json(consume_report)
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["summary"]["source_origin_class"] == "trusted_external_solver_source"
    assert commands
    handoff_cmd = commands[0]
    assert "--dry-run" in handoff_cmd
