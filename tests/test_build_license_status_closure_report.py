from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_license_status_closure_report.py"
SPEC = importlib.util.spec_from_file_location("build_license_status_closure_report", SCRIPT_PATH)
assert SPEC is not None
build_license_status_closure_report = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_license_status_closure_report)


def _write(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_license_status_closure_blocks_not_configured_status(tmp_path: Path) -> None:
    license_status = _write(tmp_path / "license_status.json", {"status": "not_configured"})

    payload = build_license_status_closure_report.build_report(
        license_status_path=license_status,
        now=datetime(2026, 6, 16, tzinfo=timezone.utc),
    )

    assert payload["contract_pass"] is False
    assert payload["source_commit_sha"]
    assert payload["engine_version"] == "structural-optimization-workbench@1.0.0"
    assert payload["reused_evidence"] is False
    assert payload["status"] == "blocked"
    assert payload["template_path"] == "docs/templates/license_status.template.json"
    assert "license_status_not_active" in payload["blockers"]
    assert "license_tier_missing" in payload["blockers"]
    assert payload["summary"]["owner_action"].startswith("Populate license_status.json")
    assert payload["summary_line"] == (
        "License status: BLOCKED | status=not_configured | tier=missing | blockers=10"
    )
    assert payload["gate_unblock_plan_count"] == 6
    assert payload["gate_unblock_plan"][0]["slot_id"] == "attach_license_status_record"
    assert payload["gate_unblock_plan"][-1]["slot_id"] == "regenerate_release_gate_evidence"
    assert payload["next_actions"] == [
        "fill_license_status_record_from_template",
        "attach_product_or_legal_approval_evidence",
        "set_paid_pilot_or_limited_commercial_scope_boundary",
        "prove_future_expiry_or_perpetual_approval",
        "rerun_license_status_and_release_gates",
    ]
    assert any("build_license_status_intake_packet.py" in command for command in payload["validation_commands"])


def test_license_status_closure_passes_populated_future_license(tmp_path: Path) -> None:
    evidence = _write(tmp_path / "legal-approval.json", {"approved": True})
    license_status = _write(
        tmp_path / "license_status.json",
        {
            "status": "active",
            "tier": "limited-commercial",
            "license_id": "LIC-001",
            "issuer": "product-owner",
            "approver_role": "product_owner",
            "approval_ref": "LEGAL-123",
            "approved_at_utc": "2026-06-01T00:00:00+00:00",
            "evidence_ref": str(evidence),
            "product_scope": [
                "review-assist",
                "specified-structure-families",
                "specified-workflows",
                "engine-and-reviewer-evidence-package",
            ],
            "expires_at_utc": "2027-01-01T00:00:00+00:00",
        },
    )

    payload = build_license_status_closure_report.build_report(
        license_status_path=license_status,
        now=datetime(2026, 6, 16, tzinfo=timezone.utc),
    )

    assert payload["contract_pass"] is True
    assert payload["source_commit_sha"]
    assert payload["engine_version"] == "structural-optimization-workbench@1.0.0"
    assert payload["reused_evidence"] is False
    assert payload["status"] == "ready"
    assert payload["blockers"] == []
    assert payload["gate_unblock_plan"] == []
    assert payload["gate_unblock_plan_count"] == 0
    assert payload["next_actions"] == []
    assert payload["summary"]["product_scope_count"] == 4
    assert payload["summary"]["evidence_ref_kind"] == "local_path"
    assert payload["checks"]["provenance_complete_pass"] is True


def test_license_status_closure_rejects_self_referenced_evidence(tmp_path: Path) -> None:
    license_status = tmp_path / "license_status.json"
    _write(
        license_status,
        {
            "status": "active",
            "tier": "limited-commercial",
            "license_id": "LIC-001",
            "issuer": "product-owner",
            "approver_role": "product_owner",
            "approval_ref": "LEGAL-123",
            "approved_at_utc": "2026-06-01T00:00:00+00:00",
            "evidence_ref": str(license_status),
            "product_scope": [
                "review-assist",
                "specified-structure-families",
                "specified-workflows",
                "engine-and-reviewer-evidence-package",
            ],
            "expires_at_utc": "2027-01-01T00:00:00+00:00",
        },
    )

    payload = build_license_status_closure_report.build_report(
        license_status_path=license_status,
        now=datetime(2026, 6, 16, tzinfo=timezone.utc),
    )

    assert payload["contract_pass"] is False
    assert "license_evidence_ref_self_reference" in payload["blockers"]
    assert payload["checks"]["evidence_ref_resolvable_pass"] is True
    assert payload["checks"]["evidence_ref_not_self_reference_pass"] is False
    assert payload["checks"]["provenance_complete_pass"] is False


def test_license_status_closure_rejects_template_referenced_evidence(tmp_path: Path) -> None:
    template = _write(tmp_path / "license_status.template.json", {"template": True})
    license_status = _write(
        tmp_path / "license_status.json",
        {
            "status": "active",
            "tier": "limited-commercial",
            "license_id": "LIC-001",
            "issuer": "product-owner",
            "approver_role": "product_owner",
            "approval_ref": "LEGAL-123",
            "approved_at_utc": "2026-06-01T00:00:00+00:00",
            "evidence_ref": str(template),
            "product_scope": [
                "review-assist",
                "specified-structure-families",
                "specified-workflows",
                "engine-and-reviewer-evidence-package",
            ],
            "expires_at_utc": "2027-01-01T00:00:00+00:00",
        },
    )

    payload = build_license_status_closure_report.build_report(
        license_status_path=license_status,
        now=datetime(2026, 6, 16, tzinfo=timezone.utc),
        template_path=template,
        repo_root=tmp_path,
    )

    assert payload["contract_pass"] is False
    assert "license_evidence_ref_template_reference" in payload["blockers"]
    assert payload["checks"]["evidence_ref_resolvable_pass"] is True
    assert payload["checks"]["evidence_ref_not_template_reference_pass"] is False
    assert payload["checks"]["provenance_complete_pass"] is False


def test_license_status_closure_rejects_template_like_evidence_artifact(tmp_path: Path) -> None:
    approval_template = _write(tmp_path / "docs" / "templates" / "legal_approval.json", {"template": True})
    license_status = _write(
        tmp_path / "license_status.json",
        {
            "status": "active",
            "tier": "limited-commercial",
            "license_id": "LIC-001",
            "issuer": "product-owner",
            "approver_role": "product_owner",
            "approval_ref": "LEGAL-123",
            "approved_at_utc": "2026-06-01T00:00:00+00:00",
            "evidence_ref": str(approval_template),
            "product_scope": [
                "review-assist",
                "specified-structure-families",
                "specified-workflows",
                "engine-and-reviewer-evidence-package",
            ],
            "expires_at_utc": "2027-01-01T00:00:00+00:00",
        },
    )

    payload = build_license_status_closure_report.build_report(
        license_status_path=license_status,
        now=datetime(2026, 6, 16, tzinfo=timezone.utc),
        repo_root=tmp_path,
    )

    assert payload["contract_pass"] is False
    assert "license_evidence_ref_template_artifact" in payload["blockers"]
    assert payload["checks"]["evidence_ref_resolvable_pass"] is True
    assert payload["checks"]["evidence_ref_not_template_reference_pass"] is True
    assert payload["checks"]["evidence_ref_not_template_artifact_pass"] is False
    assert payload["checks"]["provenance_complete_pass"] is False


def test_license_status_closure_rejects_generated_gate_evidence_artifact(tmp_path: Path) -> None:
    generated_artifact = _write(
        tmp_path
        / "implementation"
        / "phase1"
        / "release_evidence"
        / "productization"
        / "license_status_closure_report.json",
        {"contract_pass": False},
    )
    license_status = _write(
        tmp_path / "license_status.json",
        {
            "status": "active",
            "tier": "limited-commercial",
            "license_id": "LIC-001",
            "issuer": "product-owner",
            "approver_role": "product_owner",
            "approval_ref": "LEGAL-123",
            "approved_at_utc": "2026-06-01T00:00:00+00:00",
            "evidence_ref": str(generated_artifact),
            "product_scope": [
                "review-assist",
                "specified-structure-families",
                "specified-workflows",
                "engine-and-reviewer-evidence-package",
            ],
            "expires_at_utc": "2027-01-01T00:00:00+00:00",
        },
    )

    payload = build_license_status_closure_report.build_report(
        license_status_path=license_status,
        now=datetime(2026, 6, 16, tzinfo=timezone.utc),
        repo_root=tmp_path,
    )

    assert payload["contract_pass"] is False
    assert "license_evidence_ref_generated_gate_artifact" in payload["blockers"]
    assert payload["checks"]["evidence_ref_resolvable_pass"] is True
    assert payload["checks"]["evidence_ref_not_generated_gate_artifact_pass"] is False
    assert payload["checks"]["provenance_complete_pass"] is False


def test_license_status_closure_rejects_template_placeholders(tmp_path: Path) -> None:
    license_status = _write(
        tmp_path / "license_status.json",
        {
            "status": "active",
            "tier": "limited-commercial",
            "license_id": "LICENSE-ID",
            "issuer": "product-or-legal-owner",
            "approver_role": "APPROVER-ROLE",
            "approval_ref": "LEGAL-OR-PRODUCT-APPROVAL-ID",
            "approved_at_utc": "APPROVED-AT-UTC",
            "evidence_ref": "EVIDENCE-REF",
            "product_scope": ["review-assist"],
            "expires_at_utc": "2027-01-01T00:00:00+00:00",
            "template_only": True,
            "note": "Template only. Do not use as release evidence.",
        },
    )

    payload = build_license_status_closure_report.build_report(
        license_status_path=license_status,
        now=datetime(2026, 6, 16, tzinfo=timezone.utc),
    )

    assert payload["contract_pass"] is False
    assert "license_id_placeholder" in payload["blockers"]
    assert "license_issuer_or_approver_placeholder" in payload["blockers"]
    assert "license_approver_role_placeholder" in payload["blockers"]
    assert "license_approval_reference_placeholder" in payload["blockers"]
    assert "license_approved_at_placeholder" in payload["blockers"]
    assert "license_evidence_ref_placeholder" in payload["blockers"]
    assert "license_status_template_only" in payload["blockers"]
    assert payload["checks"]["placeholder_values_absent_pass"] is False


def test_license_status_closure_rejects_missing_provenance(tmp_path: Path) -> None:
    license_status = _write(
        tmp_path / "license_status.json",
        {
            "status": "active",
            "tier": "limited-commercial",
            "license_id": "LIC-001",
            "issuer": "product-owner",
            "approval_ref": "LEGAL-123",
            "product_scope": [
                "review-assist",
                "specified-structure-families",
                "specified-workflows",
                "engine-and-reviewer-evidence-package",
            ],
            "expires_at_utc": "2027-01-01T00:00:00+00:00",
        },
    )

    payload = build_license_status_closure_report.build_report(
        license_status_path=license_status,
        now=datetime(2026, 6, 16, tzinfo=timezone.utc),
    )

    assert payload["contract_pass"] is False
    assert "license_approver_role_missing" in payload["blockers"]
    assert "license_approved_at_missing" in payload["blockers"]
    assert "license_evidence_ref_missing" in payload["blockers"]
    assert payload["checks"]["provenance_complete_pass"] is False


def test_license_status_closure_rejects_future_or_naive_approval_time(tmp_path: Path) -> None:
    base = {
        "status": "active",
        "tier": "limited-commercial",
        "license_id": "LIC-001",
        "issuer": "product-owner",
        "approver_role": "legal_counsel",
        "approval_ref": "LEGAL-123",
        "evidence_ref": "ticket:LEGAL-123",
        "product_scope": [
            "review-assist",
            "specified-structure-families",
            "specified-workflows",
            "engine-and-reviewer-evidence-package",
        ],
        "expires_at_utc": "2027-01-01T00:00:00+00:00",
    }
    future = dict(base, approved_at_utc="2026-07-01T00:00:00+00:00")
    naive = dict(base, approved_at_utc="2026-06-01T00:00:00")

    future_payload = build_license_status_closure_report.build_report(
        license_status_path=_write(tmp_path / "future.json", future),
        now=datetime(2026, 6, 16, tzinfo=timezone.utc),
    )
    naive_payload = build_license_status_closure_report.build_report(
        license_status_path=_write(tmp_path / "naive.json", naive),
        now=datetime(2026, 6, 16, tzinfo=timezone.utc),
    )

    assert "license_approved_at_future" in future_payload["blockers"]
    assert "license_approved_at_invalid" in naive_payload["blockers"]


def test_license_status_closure_rejects_unscoped_or_disallowed_license(tmp_path: Path) -> None:
    license_status = _write(
        tmp_path / "license_status.json",
        {
            "status": "active",
            "tier": "enterprise",
            "license_id": "LEGAL-123",
            "issuer": "product-owner",
            "approver_role": "sales",
            "approval_ref": "LEGAL-123",
            "approved_at_utc": "2026-06-01T00:00:00+00:00",
            "evidence_ref": "missing/legal-approval.json",
            "product_scope": ["review-assist"],
            "expires_at_utc": "2026-05-01T00:00:00+00:00",
        },
    )

    payload = build_license_status_closure_report.build_report(
        license_status_path=license_status,
        now=datetime(2026, 6, 16, tzinfo=timezone.utc),
    )

    assert payload["contract_pass"] is False
    assert "license_tier_not_allowed" in payload["blockers"]
    assert "license_approver_role_invalid" in payload["blockers"]
    assert "license_approval_ref_not_distinct" in payload["blockers"]
    assert "license_evidence_ref_unresolvable" in payload["blockers"]
    assert "license_product_scope_boundary_incomplete" in payload["blockers"]
    assert "license_approval_after_expiry" in payload["blockers"]


def test_license_status_closure_rejects_self_referenced_evidence_ref(tmp_path: Path) -> None:
    license_status = tmp_path / "license_status.json"
    _write(
        license_status,
        {
            "status": "active",
            "tier": "limited-commercial",
            "license_id": "LIC-001",
            "issuer": "product-owner",
            "approver_role": "product_owner",
            "approval_ref": "LEGAL-123",
            "approved_at_utc": "2026-06-01T00:00:00+00:00",
            "evidence_ref": str(license_status),
            "product_scope": [
                "review-assist",
                "specified-structure-families",
                "specified-workflows",
                "engine-and-reviewer-evidence-package",
            ],
            "expires_at_utc": "2027-01-01T00:00:00+00:00",
        },
    )

    payload = build_license_status_closure_report.build_report(
        license_status_path=license_status,
        now=datetime(2026, 6, 16, tzinfo=timezone.utc),
    )

    assert payload["contract_pass"] is False
    assert "license_evidence_ref_self_reference" in payload["blockers"]
    assert payload["checks"]["evidence_ref_not_self_reference_pass"] is False
    assert payload["checks"]["provenance_complete_pass"] is False


def test_license_status_closure_rejects_template_evidence_ref(tmp_path: Path) -> None:
    template = Path("docs/templates/license_status.template.json").resolve()
    license_status = _write(
        tmp_path / "license_status.json",
        {
            "status": "active",
            "tier": "limited-commercial",
            "license_id": "LIC-001",
            "issuer": "product-owner",
            "approver_role": "product_owner",
            "approval_ref": "LEGAL-123",
            "approved_at_utc": "2026-06-01T00:00:00+00:00",
            "evidence_ref": str(template),
            "product_scope": [
                "review-assist",
                "specified-structure-families",
                "specified-workflows",
                "engine-and-reviewer-evidence-package",
            ],
            "expires_at_utc": "2027-01-01T00:00:00+00:00",
        },
    )

    payload = build_license_status_closure_report.build_report(
        license_status_path=license_status,
        now=datetime(2026, 6, 16, tzinfo=timezone.utc),
    )

    assert payload["contract_pass"] is False
    assert "license_evidence_ref_template_reference" in payload["blockers"]
    assert payload["checks"]["evidence_ref_not_template_reference_pass"] is False
    assert payload["checks"]["provenance_complete_pass"] is False
