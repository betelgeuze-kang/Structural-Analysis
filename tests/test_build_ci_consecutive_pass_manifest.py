from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_ci_consecutive_pass_manifest.py"
SPEC = importlib.util.spec_from_file_location("build_ci_consecutive_pass_manifest", SCRIPT_PATH)
assert SPEC is not None
build_ci_consecutive_pass_manifest = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_ci_consecutive_pass_manifest)


def _write(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_build_manifest_counts_trailing_pass_streak(tmp_path: Path) -> None:
    pr_reports = [
        _write(tmp_path / "pr1.json", {"reason_code": "PASS"}),
        _write(tmp_path / "pr2.json", {"reason_code": "ERR"}),
        _write(tmp_path / "pr3.json", {"reason_code": "PASS"}),
    ]
    nightly_reports = [
        _write(tmp_path / "nightly1.json", {"reason_code": "PASS"}),
        _write(tmp_path / "nightly2.json", {"contract_pass": True}),
        _write(tmp_path / "nightly3.json", {"reason_code": "PASS"}),
    ]

    payload = build_ci_consecutive_pass_manifest.build_manifest(
        threshold=3,
        pr_reports=pr_reports,
        nightly_reports=nightly_reports,
    )

    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_CI_STREAK_INCOMPLETE"
    assert "pr:pr_ci_3_consecutive_pass_evidence_missing" in payload["blockers"]
    assert payload["lanes"]["pr"]["consecutive_pass_count"] == 1
    assert payload["lanes"]["pr"]["missing_consecutive_pass_count"] == 2
    assert payload["lanes"]["pr"]["threshold_pass"] is False
    assert payload["lanes"]["pr"]["blockers"] == ["pr_ci_3_consecutive_pass_evidence_missing"]
    assert payload["lanes"]["pr"]["owner_action"].startswith(
        "Collect 2 additional consecutive successful PR CI run"
    )
    assert "release streak credit requires tracked PR CI evidence" in payload["lanes"]["pr"]["claim_boundary"]
    assert payload["lanes"]["nightly"]["consecutive_pass_count"] == 3
    assert payload["lanes"]["nightly"]["missing_consecutive_pass_count"] == 0
    assert payload["lanes"]["nightly"]["threshold_pass"] is True
    assert payload["summary"]["pr_missing_consecutive_pass_count"] == 2
    assert payload["summary"]["nightly_missing_consecutive_pass_count"] == 0
    assert payload["summary"]["pr_owner_action"] == payload["lanes"]["pr"]["owner_action"]


def test_build_manifest_uses_github_actions_streak_evidence_when_available(tmp_path: Path) -> None:
    pr_reports = [
        _write(tmp_path / "pr1.json", {"reason_code": "PASS"}),
        _write(tmp_path / "pr2.json", {"reason_code": "PASS"}),
    ]
    nightly_reports = [_write(tmp_path / "nightly1.json", {"reason_code": "PASS"})]
    github_evidence = _write(
        tmp_path / "github_actions_ci_streak_evidence.json",
        {
            "schema_version": "github-actions-ci-streak-evidence.v1",
            "lanes": {
                "pr": {"consecutive_pass_count": 30},
                "nightly": {"consecutive_pass_count": 30},
            },
        },
    )

    payload = build_ci_consecutive_pass_manifest.build_manifest(
        threshold=30,
        pr_reports=pr_reports,
        nightly_reports=nightly_reports,
        github_actions_evidence_path=github_evidence,
    )

    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["blockers"] == []
    assert payload["lanes"]["pr"]["local_consecutive_pass_count"] == 2
    assert payload["lanes"]["pr"]["github_actions_consecutive_pass_count"] == 30
    assert payload["lanes"]["pr"]["consecutive_pass_count"] == 30
    assert payload["lanes"]["pr"]["missing_consecutive_pass_count"] == 0
    assert payload["lanes"]["pr"]["streak_source"] == "github_actions"
