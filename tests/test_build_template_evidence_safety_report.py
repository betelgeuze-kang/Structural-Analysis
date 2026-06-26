from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_template_evidence_safety_report.py"
SPEC = importlib.util.spec_from_file_location("build_template_evidence_safety_report", SCRIPT_PATH)
assert SPEC is not None
build_template_evidence_safety_report = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_template_evidence_safety_report)


def _copy_templates(destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    for source in Path("docs/templates").glob("*.json"):
        (destination / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return destination


def test_template_evidence_safety_report_accepts_current_templates() -> None:
    payload = build_template_evidence_safety_report.build_report(template_dir=Path("docs/templates"))

    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["summary"]["template_count"] == 7
    assert payload["summary"]["validator_probe_count"] == 7
    assert payload["summary"]["validator_probe_pass_count"] == 7
    assert payload["blockers"] == []
    assert all(row["template_only"] is True for row in payload["template_rows"])
    assert all(row["pass_signal_paths"] == [] for row in payload["template_rows"])
    assert all(row["placeholder_markers"] for row in payload["template_rows"])
    assert all(row["contract_pass"] is True for row in payload["validator_probes"])
    assert any(
        row["observed_state"] == "template_only_external_signoff_evidence"
        for row in payload["validator_probes"]
        if "observed_state" in row
    )
    assert any(
        row["state"] == "template_rejected_as_customer_shadow_evidence"
        for row in payload["validator_probes"]
        if "state" in row
    )
    assert any(
        row["state"] == "template_rejected_as_fresh_validation_evidence"
        for row in payload["validator_probes"]
        if "state" in row
    )


def test_template_evidence_safety_report_rejects_affirmative_pass_signals(tmp_path: Path) -> None:
    template_dir = _copy_templates(tmp_path / "templates")
    license_template = template_dir / "license_status.template.json"
    payload = json.loads(license_template.read_text(encoding="utf-8"))
    payload["contract_pass"] = True
    payload["reason_code"] = "PASS"
    license_template.write_text(json.dumps(payload), encoding="utf-8")

    report = build_template_evidence_safety_report.build_report(template_dir=template_dir)

    assert report["contract_pass"] is False
    assert any("template_affirmative_pass_signal" in blocker for blocker in report["blockers"])
    row = next(row for row in report["template_rows"] if row["name"] == "license_status.template.json")
    assert row["pass_signal_paths"] == ["$.contract_pass", "$.reason_code"]


def test_template_evidence_safety_report_fails_closed_on_unmapped_json(tmp_path: Path) -> None:
    template_dir = _copy_templates(tmp_path / "templates")
    (template_dir / "new_owner_handoff.json").write_text(
        json.dumps({"template_only": True, "field": "OWNER_INPUT_REQUIRED"}),
        encoding="utf-8",
    )

    report = build_template_evidence_safety_report.build_report(template_dir=template_dir)

    assert report["contract_pass"] is False
    assert "template_probe_missing:new_owner_handoff.json" in report["blockers"]
    assert any("template_validator_probe_missing" in blocker for blocker in report["blockers"])
