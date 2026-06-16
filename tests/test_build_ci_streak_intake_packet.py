from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_ci_streak_intake_packet.py"
SPEC = importlib.util.spec_from_file_location("build_ci_streak_intake_packet", SCRIPT_PATH)
assert SPEC is not None
build_ci_streak_intake_packet = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_ci_streak_intake_packet)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_ci_streak_intake_packet_surfaces_missing_pr_streak(tmp_path: Path) -> None:
    manifest = _write_json(
        tmp_path / "ci_consecutive_pass_manifest.json",
        {
            "contract_pass": False,
            "threshold": 30,
            "lanes": {
                "pr": {
                    "threshold": 30,
                    "threshold_pass": False,
                    "consecutive_pass_count": 2,
                    "local_consecutive_pass_count": 2,
                    "github_actions_consecutive_pass_count": 0,
                    "missing_consecutive_pass_count": 28,
                    "streak_source": "local_artifacts",
                    "github_actions_workflow_registered": True,
                    "github_actions_queried_run_count": 2,
                    "github_actions_filtered_run_count": 0,
                    "github_actions_ignored_event_names": ["push"],
                    "owner_action": "Collect 28 additional consecutive successful PR CI run(s).",
                    "claim_boundary": "PR release streak credit requires tracked PR CI evidence.",
                    "blockers": ["pr_ci_30_consecutive_pass_evidence_missing"],
                },
                "nightly": {
                    "threshold": 30,
                    "threshold_pass": True,
                    "consecutive_pass_count": 230,
                    "local_consecutive_pass_count": 230,
                    "github_actions_consecutive_pass_count": 0,
                    "missing_consecutive_pass_count": 0,
                    "streak_source": "local_artifacts",
                    "github_actions_workflow_registered": False,
                    "github_actions_query_error": "failed to get runs: could not find any workflows named Nightly Full Quality",
                    "local_workflow_present": True,
                    "owner_action": "No release action required; consecutive pass threshold is satisfied.",
                    "claim_boundary": "Nightly release streak credit requires tracked nightly CI evidence.",
                    "blockers": [],
                },
            },
        },
    )
    github_actions = _write_json(
        tmp_path / "github_actions_ci_streak_evidence.json",
        {
            "lanes": {
                "pr": {"consecutive_pass_count": 0, "threshold_pass": False},
                "nightly": {"consecutive_pass_count": 0, "threshold_pass": False},
            }
        },
    )

    payload = build_ci_streak_intake_packet.build_packet(
        manifest_path=manifest,
        github_actions_evidence_path=github_actions,
    )
    rows = {row["lane"]: row for row in payload["lane_rows"]}

    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_CI_STREAK_EVIDENCE_INCOMPLETE"
    assert payload["summary"]["pr_missing_consecutive_pass_count"] == 28
    assert payload["summary"]["nightly_missing_consecutive_pass_count"] == 0
    assert rows["pr"]["threshold_pass"] is False
    assert rows["pr"]["github_actions_consecutive_pass_count"] == 0
    assert rows["pr"]["github_actions_workflow_registered"] is True
    assert rows["pr"]["github_actions_queried_run_count"] == 2
    assert rows["pr"]["github_actions_ignored_event_names"] == ["push"]
    assert rows["nightly"]["threshold_pass"] is True
    assert rows["nightly"]["github_actions_workflow_registered"] is False
    assert rows["nightly"]["local_workflow_present"] is True
    assert rows["nightly"]["github_actions_query_error"].startswith("failed to get runs")
    assert "pr:pr_ci_30_consecutive_pass_evidence_missing" in payload["current_blockers"]
    assert payload["summary"]["nightly_github_actions_workflow_registered"] is False
    assert any("build_ci_consecutive_pass_manifest.py" in command for command in payload["validation_commands"])


def test_ci_streak_intake_packet_passes_closed_manifest(tmp_path: Path) -> None:
    manifest = _write_json(
        tmp_path / "ci_consecutive_pass_manifest.json",
        {
            "contract_pass": True,
            "threshold": 30,
            "lanes": {
                "pr": {"threshold": 30, "threshold_pass": True, "consecutive_pass_count": 30},
                "nightly": {"threshold": 30, "threshold_pass": True, "consecutive_pass_count": 30},
            },
        },
    )

    payload = build_ci_streak_intake_packet.build_packet(
        manifest_path=manifest,
        github_actions_evidence_path=tmp_path / "missing-github.json",
    )

    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["current_blockers"] == []
    assert payload["summary"]["lane_pass_count"] == 2


def test_ci_streak_intake_packet_cli_writes_markdown(tmp_path: Path, capsys) -> None:
    manifest = _write_json(
        tmp_path / "ci_consecutive_pass_manifest.json",
        {
            "contract_pass": False,
            "threshold": 30,
            "lanes": {
                "pr": {"threshold": 30, "threshold_pass": False, "consecutive_pass_count": 2},
                "nightly": {"threshold": 30, "threshold_pass": True, "consecutive_pass_count": 30},
            },
        },
    )
    out = tmp_path / "packet.json"
    out_md = tmp_path / "packet.md"

    exit_code = build_ci_streak_intake_packet.main(
        [
            "--manifest",
            str(manifest),
            "--github-actions-evidence",
            str(tmp_path / "missing-github.json"),
            "--out",
            str(out),
            "--out-md",
            str(out_md),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "CI Streak Intake Packet" in captured.out
    assert json.loads(out.read_text(encoding="utf-8"))["summary"]["open_blocker_count"] == 1
    assert "Validation Commands" in out_md.read_text(encoding="utf-8")
    assert "Workflow Registered" in out_md.read_text(encoding="utf-8")
