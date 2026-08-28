from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from tests.license_decision_test_support import (
    build_signed_decision_repository,
    license_status_payload,
    sign_decision,
    write_json,
)


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
    license_status = _write(
        tmp_path
        / "implementation"
        / "phase1"
        / "release"
        / "support_bundle"
        / "license_status.json",
        {"status": "not_configured"},
    )

    payload = build_license_status_closure_report.build_report(
        license_status_path=license_status,
        repo_root=tmp_path,
    )

    assert payload["contract_pass"] is False
    assert payload["source_commit_sha"] == ""
    assert payload["engine_version"] == "structural-analysis@0.3.0"
    assert payload["reused_evidence"] is False
    assert payload["status"] == "blocked"
    assert payload["template_path"] == "docs/templates/license_status.template.json"
    assert "license_status_not_active" in payload["blockers"]
    assert "license_tier_missing" in payload["blockers"]
    assert payload["summary"]["owner_action"].startswith("Populate license_status.json")
    assert payload["summary_line"] == (
        "License status: BLOCKED | status=not_configured | tier=missing | "
        f"blockers={len(payload['blockers'])}"
    )
    assert payload["gate_unblock_plan_count"] == 6
    assert payload["gate_unblock_plan"][0]["slot_id"] == "attach_license_status_record"
    assert payload["gate_unblock_plan"][-1]["slot_id"] == "regenerate_release_gate_evidence"
    assert payload["next_actions"] == [
        "fill_license_status_record_from_template",
        "attach_signed_rights_holder_decision",
        "set_paid_pilot_or_limited_commercial_scope_boundary",
        "prove_explicit_future_expiry",
        "rerun_license_status_and_release_gates",
    ]
    assert any("build_license_status_intake_packet.py" in command for command in payload["validation_commands"])


def test_license_status_closure_passes_populated_future_license(tmp_path: Path) -> None:
    fixture = build_signed_decision_repository(tmp_path)
    license_status = _write(
        tmp_path
        / "implementation"
        / "phase1"
        / "release"
        / "support_bundle"
        / "license_status.json",
        license_status_payload(fixture["decision_path"]),
    )

    payload = build_license_status_closure_report.build_report(
        license_status_path=license_status,
        repo_root=tmp_path,
        rights_holder_trust_root_path=fixture["trust_root_path"],
    )

    assert payload["contract_pass"] is True
    assert payload["source_commit_sha"]
    assert payload["engine_version"] == "structural-analysis@0.3.0"
    assert payload["reused_evidence"] is False
    assert payload["status"] == "ready"
    assert payload["blockers"] == []
    assert payload["gate_unblock_plan"] == []
    assert payload["gate_unblock_plan_count"] == 0
    assert payload["next_actions"] == []
    assert payload["summary"]["product_scope_count"] == 4
    assert payload["summary"]["evidence_ref_kind"] == "local_path"
    assert payload["checks"]["provenance_complete_pass"] is True
    assert payload["checks"]["rights_holder_signature_verified_pass"] is True
    assert payload["checks"]["rights_holder_decision_id_binding_pass"] is True
    assert payload["checks"]["rights_holder_trust_root_source_binding_pass"] is True
    assert payload["checks"]["rights_holder_canonical_trust_root_pass"] is True
    assert payload["checks"]["rights_holder_license_policy_source_binding_pass"] is True
    assert payload["checks"]["source_worktree_binding_pass"] is True
    assert payload["checks"]["rights_holder_signer_policy_authorized_pass"] is True
    assert payload["rights_holder_decision"]["third_party_material_redistribution_approved"] is False
    assert payload["rights_holder_decision"]["release_authority"] is False
    assert payload["authority"] == {
        "first_party_commercial_use_approved": True,
        "first_party_redistribution_approved": True,
        "third_party_material_redistribution_approved": False,
        "overall_release_authority": False,
    }


def test_license_evidence_hash_reuses_the_bounded_resolution_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_signed_decision_repository(tmp_path)
    license_status = _write(
        tmp_path
        / "implementation"
        / "phase1"
        / "release"
        / "support_bundle"
        / "license_status.json",
        license_status_payload(fixture["decision_path"]),
    )
    original_reader = build_license_status_closure_report._read_repository_file
    evidence_reads = 0

    def counting_reader(path: Path, *, repo_root: Path):
        nonlocal evidence_reads
        try:
            is_evidence = path.resolve() == fixture["decision_path"].resolve()
        except OSError:
            is_evidence = False
        if is_evidence:
            evidence_reads += 1
        return original_reader(path, repo_root=repo_root)

    monkeypatch.setattr(
        build_license_status_closure_report,
        "_read_repository_file",
        counting_reader,
    )

    payload = build_license_status_closure_report.build_report(
        license_status_path=license_status,
        repo_root=tmp_path,
        rights_holder_trust_root_path=fixture["trust_root_path"],
    )

    expected_sha256 = "sha256:" + hashlib.sha256(
        fixture["decision_path"].read_bytes()
    ).hexdigest()
    assert payload["contract_pass"] is True
    assert evidence_reads == 1
    assert payload["input_checksums"][str(fixture["decision_path"])] == expected_sha256


def test_license_status_closure_rejects_unsigned_approval_json(tmp_path: Path) -> None:
    evidence = _write(tmp_path / "legal-approval.json", {"approved": True})
    license_status = _write(
        tmp_path / "license_status.json",
        license_status_payload(evidence),
    )

    payload = build_license_status_closure_report.build_report(
        license_status_path=license_status,
        now=datetime(2026, 6, 16, tzinfo=timezone.utc),
        repo_root=tmp_path,
    )

    assert payload["contract_pass"] is False
    assert payload["checks"]["rights_holder_signature_verified_pass"] is False
    assert payload["authority"]["first_party_commercial_use_approved"] is False
    assert payload["authority"]["first_party_redistribution_approved"] is False
    assert payload["authority"]["overall_release_authority"] is False
    assert "rights_holder_decision_signature_not_verified" in payload["blockers"]


def test_license_status_closure_rejects_ticket_or_url_reference(tmp_path: Path) -> None:
    for index, reference in enumerate(("legal:LEGAL-123", "https://example.invalid/approval")):
        license_status = _write(
            tmp_path / f"license_status_{index}.json",
            license_status_payload(reference),
        )
        payload = build_license_status_closure_report.build_report(
            license_status_path=license_status,
            now=datetime(2026, 6, 16, tzinfo=timezone.utc),
            repo_root=tmp_path,
        )

        assert payload["contract_pass"] is False
        assert "rights_holder_decision_local_signed_artifact_required" in payload["blockers"]
        assert payload["checks"]["rights_holder_decision_contract_pass"] is False


def test_license_status_closure_never_hashes_an_outside_evidence_path(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    fixture = build_signed_decision_repository(repo)
    outside = tmp_path / "host-secret.txt"
    outside.write_text("low-entropy-host-secret\n", encoding="utf-8")
    status = license_status_payload(outside)
    license_status = _write(
        repo
        / "implementation"
        / "phase1"
        / "release"
        / "support_bundle"
        / "license_status.json",
        status,
    )

    payload = build_license_status_closure_report.build_report(
        license_status_path=license_status,
        repo_root=repo,
        rights_holder_trust_root_path=fixture["trust_root_path"],
    )

    assert payload["contract_pass"] is False
    assert payload["summary"]["evidence_ref_resolved_path"] == ""
    assert str(outside) not in payload["input_checksums"]
    outside_hash = "sha256:" + hashlib.sha256(outside.read_bytes()).hexdigest()
    assert outside_hash not in payload["input_checksums"].values()


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO requires POSIX")
@pytest.mark.parametrize("unsafe_kind", ["fifo", "directory", "oversize"])
def test_license_status_closure_rejects_unsafe_local_evidence_without_reading_it(
    tmp_path: Path,
    unsafe_kind: str,
) -> None:
    repo = tmp_path / "repo"
    fixture = build_signed_decision_repository(repo)
    unsafe = repo / "implementation" / "phase1" / "release" / "license_decisions" / "unsafe"
    unsafe.parent.mkdir(parents=True, exist_ok=True)
    if unsafe_kind == "fifo":
        os.mkfifo(unsafe)
    elif unsafe_kind == "directory":
        unsafe.mkdir()
    else:
        unsafe.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
    license_status = _write(
        repo
        / "implementation"
        / "phase1"
        / "release"
        / "support_bundle"
        / "license_status.json",
        license_status_payload(unsafe),
    )

    payload = build_license_status_closure_report.build_report(
        license_status_path=license_status,
        repo_root=repo,
        rights_holder_trust_root_path=fixture["trust_root_path"],
    )

    assert payload["contract_pass"] is False
    assert payload["checks"]["evidence_ref_resolvable_pass"] is False
    assert payload["summary"]["evidence_ref_resolved_path"] == ""
    assert str(unsafe) not in payload["input_checksums"]


def test_license_status_closure_rejects_perpetual_even_with_signed_decision(
    tmp_path: Path,
) -> None:
    fixture = build_signed_decision_repository(tmp_path)
    status = license_status_payload(fixture["decision_path"])
    status.pop("expires_at_utc")
    status["perpetual"] = True
    license_status = _write(tmp_path / "license_status.json", status)

    payload = build_license_status_closure_report.build_report(
        license_status_path=license_status,
        now=datetime(2026, 6, 16, tzinfo=timezone.utc),
        repo_root=tmp_path,
        rights_holder_trust_root_path=fixture["trust_root_path"],
    )

    assert payload["contract_pass"] is False
    assert "rights_holder_decision_explicit_expiry_required" in payload["blockers"]
    assert payload["checks"]["expiry_valid_pass"] is False
    assert payload["checks"]["approval_timeline_pass"] is False


def test_license_status_closure_rejects_caller_backdated_evaluation_time(
    tmp_path: Path,
) -> None:
    expired_at = "2021-06-10T00:00:00+00:00"
    fixture = build_signed_decision_repository(
        tmp_path,
        mutate_decision=lambda decision: decision.update(
            expires_at_utc=expired_at
        ),
    )
    license_status = _write(
        tmp_path / "license_status.json",
        license_status_payload(
            fixture["decision_path"], expires_at_utc=expired_at
        ),
    )

    payload = build_license_status_closure_report.build_report(
        license_status_path=license_status,
        now=datetime(2020, 6, 16, tzinfo=timezone.utc),
        repo_root=tmp_path,
        rights_holder_trust_root_path=fixture["trust_root_path"],
    )

    assert payload["contract_pass"] is False
    assert "caller_supplied_evaluation_time_not_allowed" in payload["blockers"]
    assert "rights_holder_decision_timeline_invalid_or_expired" in payload[
        "blockers"
    ]
    assert datetime.fromisoformat(payload["generated_at"]) > datetime.fromisoformat(
        expired_at
    )


def test_license_status_closure_rejects_scope_above_bounded_profile(
    tmp_path: Path,
) -> None:
    extra_scope = "unrestricted-all-products-and-features"
    fixture = build_signed_decision_repository(
        tmp_path,
        mutate_decision=lambda decision: decision["subject"][
            "product_scope"
        ].append(extra_scope),
    )
    status = license_status_payload(fixture["decision_path"])
    status["product_scope"].append(extra_scope)
    license_status = _write(tmp_path / "license_status.json", status)

    payload = build_license_status_closure_report.build_report(
        license_status_path=license_status,
        repo_root=tmp_path,
        rights_holder_trust_root_path=fixture["trust_root_path"],
    )

    assert payload["contract_pass"] is False
    assert "license_product_scope_not_exact" in payload["blockers"]
    assert payload["checks"]["product_scope_boundary_pass"] is False
    assert payload["rights_holder_decision"]["signature_verified"] is True


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
        repo_root=tmp_path,
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
        repo_root=tmp_path,
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
        repo_root=tmp_path,
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
    future = dict(base, approved_at_utc="2099-07-01T00:00:00+00:00")
    naive = dict(base, approved_at_utc="2026-06-01T00:00:00")

    future_payload = build_license_status_closure_report.build_report(
        license_status_path=_write(tmp_path / "future.json", future),
        now=datetime(2026, 6, 16, tzinfo=timezone.utc),
        repo_root=tmp_path,
    )
    naive_payload = build_license_status_closure_report.build_report(
        license_status_path=_write(tmp_path / "naive.json", naive),
        now=datetime(2026, 6, 16, tzinfo=timezone.utc),
        repo_root=tmp_path,
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
        repo_root=tmp_path,
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
        repo_root=tmp_path,
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
        repo_root=tmp_path,
    )

    assert payload["contract_pass"] is False
    assert "license_evidence_ref_template_artifact" in payload["blockers"]
    assert payload["checks"]["evidence_ref_not_template_artifact_pass"] is False
    assert payload["checks"]["provenance_complete_pass"] is False


def test_relative_canonical_status_path_is_verified(tmp_path: Path) -> None:
    fixture = build_signed_decision_repository(tmp_path)
    canonical_status = (
        tmp_path
        / build_license_status_closure_report.CANONICAL_LICENSE_STATUS
    )
    _write(canonical_status, license_status_payload(fixture["decision_path"]))

    payload = build_license_status_closure_report.build_report(
        license_status_path=(
            build_license_status_closure_report.CANONICAL_LICENSE_STATUS
        ),
        repo_root=tmp_path,
        rights_holder_trust_root_path=fixture["trust_root_path"],
    )

    assert payload["contract_pass"] is True
    assert payload["checks"]["license_status_path_canonical_pass"] is True
    assert payload["checks"]["license_status_stable_pass"] is True


def test_staged_status_can_be_preflighted_but_never_be_authoritative(
    tmp_path: Path,
) -> None:
    fixture = build_signed_decision_repository(tmp_path)
    canonical_status = (
        tmp_path
        / build_license_status_closure_report.CANONICAL_LICENSE_STATUS
    )
    staged_status = canonical_status.with_name(
        f".{canonical_status.name}.attacker.tmp"
    )
    _write(staged_status, license_status_payload(fixture["decision_path"]))

    ordinary = build_license_status_closure_report.build_report(
        license_status_path=staged_status,
        repo_root=tmp_path,
        rights_holder_trust_root_path=fixture["trust_root_path"],
    )
    internal_preflight = build_license_status_closure_report.build_report(
        license_status_path=staged_status,
        repo_root=tmp_path,
        rights_holder_trust_root_path=fixture["trust_root_path"],
        allow_staged_canonical_status=True,
    )

    assert ordinary["contract_pass"] is False
    assert "license_status_path_not_canonical" in ordinary["blockers"]
    assert internal_preflight["contract_pass"] is False
    assert internal_preflight["authority"][
        "first_party_commercial_use_approved"
    ] is False
    assert internal_preflight["checks"][
        "license_status_staged_validation_pass"
    ] is True
    assert internal_preflight["blockers"] == [
        "license_status_staged_not_authoritative"
    ]


def test_canonical_status_symlink_is_rejected(tmp_path: Path) -> None:
    fixture = build_signed_decision_repository(tmp_path / "repo")
    canonical_status = (
        fixture["repo_root"]
        / build_license_status_closure_report.CANONICAL_LICENSE_STATUS
    )
    outside = tmp_path / "outside-license-status.json"
    _write(outside, license_status_payload(fixture["decision_path"]))
    canonical_status.parent.mkdir(parents=True, exist_ok=True)
    canonical_status.symlink_to(outside)

    payload = build_license_status_closure_report.build_report(
        license_status_path=(
            build_license_status_closure_report.CANONICAL_LICENSE_STATUS
        ),
        repo_root=fixture["repo_root"],
        rights_holder_trust_root_path=fixture["trust_root_path"],
    )

    assert payload["contract_pass"] is False
    assert "license_status_symlink_not_allowed" in payload["blockers"]
    assert payload["checks"]["license_status_path_canonical_pass"] is False


def test_duplicate_status_keys_fail_closed(tmp_path: Path) -> None:
    fixture = build_signed_decision_repository(tmp_path)
    canonical_status = (
        tmp_path
        / build_license_status_closure_report.CANONICAL_LICENSE_STATUS
    )
    canonical_status.parent.mkdir(parents=True, exist_ok=True)
    canonical_status.write_text(
        '{"status":"not_configured","status":"active"}\n',
        encoding="utf-8",
    )

    payload = build_license_status_closure_report.build_report(
        license_status_path=(
            build_license_status_closure_report.CANONICAL_LICENSE_STATUS
        ),
        repo_root=tmp_path,
        rights_holder_trust_root_path=fixture["trust_root_path"],
    )

    assert payload["contract_pass"] is False
    assert payload["summary"]["status"] == "missing"
    assert "license_status_json_invalid_or_empty" in payload["blockers"]
    assert payload["authority"]["first_party_commercial_use_approved"] is False


def test_isolated_default_cli_can_verify_relative_canonical_status_without_pycache(
    tmp_path: Path,
) -> None:
    fixture = build_signed_decision_repository(tmp_path)
    repository_source = Path(__file__).resolve().parent.parent
    scripts = (
        "build_license_status_closure_report.py",
        "release_evidence_metadata.py",
        "verify_rights_holder_license_decision.py",
    )
    for name in scripts:
        destination = tmp_path / "scripts" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repository_source / "scripts" / name, destination)
    for name in (
        "rights-holder-license-decision.v1.schema.json",
        "rights-holder-license-trust-root.v1.schema.json",
    ):
        shutil.copy2(repository_source / "canonical" / name, tmp_path / "canonical" / name)
    subprocess.run(
        [
            "git",
            "add",
            "scripts",
            "canonical/rights-holder-license-decision.v1.schema.json",
            "canonical/rights-holder-license-trust-root.v1.schema.json",
        ],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-q", "-m", "add isolated verifier runtime"],
        cwd=tmp_path,
        check=True,
    )
    fixture["source_commit_sha"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True
    ).strip()
    fixture["decision"]["subject"]["source_commit_sha"] = fixture[
        "source_commit_sha"
    ]
    sign_decision(fixture["decision"], private_key=fixture["private_key"])
    write_json(fixture["decision_path"], fixture["decision"])
    canonical_status = (
        tmp_path
        / build_license_status_closure_report.CANONICAL_LICENSE_STATUS
    )
    _write(canonical_status, license_status_payload(fixture["decision_path"]))

    completed = subprocess.run(
        [
            "/usr/bin/python3",
            "-I",
            "-B",
            "scripts/build_license_status_closure_report.py",
            "--out",
            "cli-license-report.json",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(
        (tmp_path / "cli-license-report.json").read_text(encoding="utf-8")
    )
    assert report["contract_pass"] is True
    assert not list(tmp_path.rglob("__pycache__"))
    (tmp_path / "cli-license-report.json").unlink()

    release_check = subprocess.run(
        [
            "/usr/bin/python3",
            "-I",
            "-B",
            "scripts/build_license_status_closure_report.py",
            "--out",
            "cli-release-authority-report.json",
            "--require-release-authority",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert release_check.returncode == 1
    assert "full release authority not established" in release_check.stderr
    release_report = json.loads(
        (tmp_path / "cli-release-authority-report.json").read_text(encoding="utf-8")
    )
    assert release_report["contract_pass"] is True
    assert release_report["authority"]["first_party_commercial_use_approved"] is True
    assert release_report["authority"]["third_party_material_redistribution_approved"] is False
    assert release_report["authority"]["overall_release_authority"] is False
    assert not list(tmp_path.rglob("__pycache__"))


def test_nonisolated_closure_cli_is_rejected(tmp_path: Path) -> None:
    exit_code = build_license_status_closure_report.main(
        ["--out", str(tmp_path / "should-not-exist.json")]
    )

    assert exit_code == 2
    assert not (tmp_path / "should-not-exist.json").exists()
