from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_paid_pilot_scope_guard_report.py"
SPEC = importlib.util.spec_from_file_location("build_paid_pilot_scope_guard_report", SCRIPT_PATH)
assert SPEC is not None
build_paid_pilot_scope_guard_report = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_paid_pilot_scope_guard_report)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _scope_text() -> str:
    return "\n".join(
        [
            "현재 권장 범위는 제한된 paid pilot이다.",
            "- 구조 엔지니어 검토 보조",
            "- 지정된 구조군과 지정된 workflow",
            "- engine/reviewer evidence package 포함",
            "- unsupported 또는 missing evidence 항목은 pass가 아니라 blocker로 표시",
        ]
    )


def _artifact_inputs(tmp_path: Path) -> dict[str, Path]:
    return {
        "pm_release_gate_report": _write_json(tmp_path / "pm_release_gate_report.json", {"contract_pass": True}),
        "support_bundle": _write_json(
            tmp_path / "support_bundle.json",
            {"contract_pass": True, "checks": {"bundle_roundtrip_test_pass": True}},
        ),
        "pm_blocker_register": _write_json(tmp_path / "pm_blocker_register.json", {"contract_pass": False}),
        "ci_streak_intake_packet": _write_json(tmp_path / "ci_streak.json", {"contract_pass": False}),
        "license_status_intake_packet": _write_json(tmp_path / "license.json", {"contract_pass": False}),
        "ga_enterprise_readiness_report": _write_json(tmp_path / "ga.json", {"contract_pass": False}),
    }


def test_paid_pilot_scope_guard_passes_constrained_scope_and_artifacts(tmp_path: Path) -> None:
    payload = build_paid_pilot_scope_guard_report.build_report(
        scope_source=_write_text(tmp_path / "scope.md", _scope_text()),
        **_artifact_inputs(tmp_path),
    )

    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["checks"]["all_required_scope_terms_present"] is True
    assert payload["checks"]["evidence_package_artifacts_present"] is True
    assert payload["summary_line"].startswith("Paid pilot scope guard: PASS")


def test_paid_pilot_scope_guard_blocks_missing_scope_terms(tmp_path: Path) -> None:
    payload = build_paid_pilot_scope_guard_report.build_report(
        scope_source=_write_text(tmp_path / "scope.md", "paid pilot only\n"),
        **_artifact_inputs(tmp_path),
    )

    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_PAID_PILOT_SCOPE_GUARD_BLOCKED"
    assert "scope_term_missing:review_assist_boundary" in payload["blockers"]
    assert "scope_term_missing:engine_reviewer_evidence_package" in payload["blockers"]


def test_paid_pilot_scope_guard_cli_writes_markdown(tmp_path: Path, capsys) -> None:
    inputs = _artifact_inputs(tmp_path)
    out = tmp_path / "scope_report.json"
    out_md = tmp_path / "scope_report.md"

    exit_code = build_paid_pilot_scope_guard_report.main(
        [
            "--scope-source",
            str(_write_text(tmp_path / "scope.md", _scope_text())),
            "--pm-release-gate-report",
            str(inputs["pm_release_gate_report"]),
            "--support-bundle",
            str(inputs["support_bundle"]),
            "--pm-blocker-register",
            str(inputs["pm_blocker_register"]),
            "--ci-streak-intake-packet",
            str(inputs["ci_streak_intake_packet"]),
            "--license-status-intake-packet",
            str(inputs["license_status_intake_packet"]),
            "--ga-enterprise-readiness-report",
            str(inputs["ga_enterprise_readiness_report"]),
            "--out",
            str(out),
            "--out-md",
            str(out_md),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Paid pilot scope guard: PASS" in captured.out
    assert json.loads(out.read_text(encoding="utf-8"))["contract_pass"] is True
    assert "Paid Pilot Scope Guard Report" in out_md.read_text(encoding="utf-8")
