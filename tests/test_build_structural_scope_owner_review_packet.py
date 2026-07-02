from __future__ import annotations

import importlib.util
import csv
import json
from pathlib import Path
import sys


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "build_structural_scope_owner_review_packet.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_structural_scope_owner_review_packet", SCRIPT_PATH
)
assert SPEC is not None
owner_review = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = owner_review
SPEC.loader.exec_module(owner_review)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _audit_payload() -> dict:
    return {
        "schema_version": "structural-scope-contamination-audit.v1",
        "status": "quarantined",
        "contract_pass": True,
        "blockers": [],
        "quarantined_non_structural_rows": [
            {
                "path": "implementation/phase1/md3bead_soa.py",
                "git_state": "tracked",
                "path_area": "implementation_phase1",
                "families": ["molecular_dynamics"],
                "matched_tokens": ["md3bead"],
                "quarantine_status": "quarantined",
                "excluded_from_structural_release_surface": True,
            },
            {
                "path": (
                    "implementation/phase1/release_evidence/productization/"
                    "gpcr_hard_decoy_product_report.json"
                ),
                "git_state": "tracked",
                "path_area": "productization_evidence",
                "families": ["molecular_docking"],
                "matched_tokens": ["gpcr"],
                "quarantine_status": "quarantined",
                "excluded_from_structural_release_surface": True,
            },
        ],
        "unquarantined_non_structural_rows": [],
    }


def _manifest_payload() -> dict:
    return {
        "schema_version": "structural-scope-quarantine-manifest.v1",
        "status": "active",
        "paths": [
            {
                "path": "implementation/phase1/md3bead_soa.py",
                "excluded_from_structural_release_surface": True,
            },
            {
                "path": (
                    "implementation/phase1/release_evidence/productization/"
                    "gpcr_hard_decoy_product_report.json"
                ),
                "excluded_from_structural_release_surface": True,
            },
        ],
    }


def _post_cleanup_audit_payload() -> dict:
    payload = _audit_payload()
    payload["quarantined_non_structural_rows"] = []
    payload["non_structural_rows"] = []
    payload["non_structural_path_count"] = 0
    return payload


def _decision_payload(decision: str) -> dict:
    return {
        "schema_version": owner_review.DECISION_SCHEMA_VERSION,
        "decision_rows": [
            {
                "path": "implementation/phase1/md3bead_soa.py",
                "owner_decision": decision,
                "owner_identity": "scope-owner",
                "owner_role": "product_owner",
                "decision_timestamp_utc": "2026-07-02T00:00:00Z",
                "evidence_reference": "owner-review://scope-cleanup/001",
                "signed_owner_exception_reference": (
                    "signed-exception://scope-cleanup/001"
                ),
                "external_archive_reference": "archive://molecular-scope/md3bead_soa",
            },
            {
                "path": (
                    "implementation/phase1/release_evidence/productization/"
                    "gpcr_hard_decoy_product_report.json"
                ),
                "owner_decision": decision,
                "owner_identity": "scope-owner",
                "owner_role": "product_owner",
                "decision_timestamp_utc": "2026-07-02T00:00:00Z",
                "evidence_reference": "owner-review://scope-cleanup/002",
                "signed_owner_exception_reference": (
                    "signed-exception://scope-cleanup/002"
                ),
                "external_archive_reference": "archive://molecular-scope/gpcr_hard_decoy",
            },
        ],
    }


def test_owner_review_packet_groups_quarantined_paths(tmp_path: Path) -> None:
    audit = tmp_path / "audit.json"
    manifest = tmp_path / "manifest.json"
    _write_json(audit, _audit_payload())
    _write_json(manifest, _manifest_payload())

    payload = owner_review.build_owner_review_packet(
        repo_root=tmp_path,
        audit_path=audit,
        quarantine_manifest_path=manifest,
    )

    assert payload["status"] == "ready_for_owner_review"
    assert payload["contract_pass"] is True
    assert payload["evidence_closure_pass"] is False
    assert payload["owner_decision_pending_count"] == 2
    assert payload["owner_decision_recorded_count"] == 0
    assert payload["post_decision_cleanup_pending_count"] == 0
    assert payload["closure_blockers"] == ["owner_decision_pending_count=2"]
    assert payload["release_surface_excluded_path_count"] == 2
    assert payload["unquarantined_non_structural_path_count"] == 0
    assert payload["family_counts"] == {
        "molecular_docking": 1,
        "molecular_dynamics": 1,
    }
    assert payload["path_area_counts"] == {
        "implementation_phase1": 1,
        "productization_evidence": 1,
    }
    assert payload["release_surface_path_count"] == 0
    assert payload["release_surface_paths"] == []
    assert payload["release_surface_owner_decision_required_count"] == 0
    assert payload["release_surface_owner_decision_required_paths"] == []
    assert payload["release_surface_allowed_owner_decisions"] == list(
        owner_review.RELEASE_SURFACE_ALLOWED_OWNER_DECISIONS
    )
    assert payload["release_surface_retain_quarantined_exception_allowed"] is False
    rows = {row["path"]: row for row in payload["review_rows"]}
    assert rows["implementation/phase1/md3bead_soa.py"]["structural_release_claim_eligible"] is False
    assert rows["implementation/phase1/md3bead_soa.py"]["owner_review_state"] == "pending_owner_decision"
    assert (
        rows["implementation/phase1/md3bead_soa.py"]["recommended_owner_decision"]
        == "extract_to_molecular_or_science_repository_or_delete_if_obsolete"
    )
    assert rows["implementation/phase1/md3bead_soa.py"][
        "recommended_owner_decision_primary"
    ] == "extract_to_molecular_or_science_repository"
    assert rows["implementation/phase1/md3bead_soa.py"][
        "recommended_owner_decision_alternate"
    ] == "delete_from_structural_repository"
    assert (
        rows[
            "implementation/phase1/release_evidence/productization/"
            "gpcr_hard_decoy_product_report.json"
        ]["recommended_owner_decision"]
        == "delete_from_structural_repository_or_extract_only_if_owner_requires_history"
    )
    assert rows[
        "implementation/phase1/release_evidence/productization/"
        "gpcr_hard_decoy_product_report.json"
    ]["recommended_owner_decision_primary"] == "delete_from_structural_repository"
    assert rows[
        "implementation/phase1/release_evidence/productization/"
        "gpcr_hard_decoy_product_report.json"
    ][
        "recommended_owner_decision_alternate"
    ] == "extract_to_molecular_or_science_repository"


def test_owner_review_packet_closes_with_signed_quarantine_exception_decisions(
    tmp_path: Path,
) -> None:
    audit = tmp_path / "audit.json"
    manifest = tmp_path / "manifest.json"
    decisions = tmp_path / "owner_decisions.json"
    _write_json(audit, _audit_payload())
    _write_json(manifest, _manifest_payload())
    _write_json(
        decisions,
        _decision_payload("retain_quarantined_with_signed_owner_exception"),
    )

    payload = owner_review.build_owner_review_packet(
        repo_root=tmp_path,
        audit_path=audit,
        quarantine_manifest_path=manifest,
        owner_decisions_path=decisions,
    )

    assert payload["status"] == "complete"
    assert payload["contract_pass"] is True
    assert payload["evidence_closure_pass"] is True
    assert payload["owner_decision_pending_count"] == 0
    assert payload["owner_decision_recorded_count"] == 2
    assert payload["post_decision_cleanup_pending_count"] == 0
    assert payload["closure_blockers"] == []
    assert {
        row["owner_review_state"] for row in payload["review_rows"]
    } == {"owner_decision_recorded_retained_quarantined_signed_exception"}
    assert {
        row["signed_owner_exception_reference"] for row in payload["review_rows"]
    } == {
        "signed-exception://scope-cleanup/001",
        "signed-exception://scope-cleanup/002",
    }


def test_owner_review_packet_requires_signed_reference_for_retain_exception(
    tmp_path: Path,
) -> None:
    audit = tmp_path / "audit.json"
    manifest = tmp_path / "manifest.json"
    decisions = tmp_path / "owner_decisions.json"
    _write_json(audit, _audit_payload())
    _write_json(manifest, _manifest_payload())
    payload = _decision_payload("retain_quarantined_with_signed_owner_exception")
    for row in payload["decision_rows"]:
        row["signed_owner_exception_reference"] = ""
    _write_json(decisions, payload)

    result = owner_review.build_owner_review_packet(
        repo_root=tmp_path,
        audit_path=audit,
        quarantine_manifest_path=manifest,
        owner_decisions_path=decisions,
    )

    assert result["status"] == "owner_decision_evidence_invalid"
    assert result["owner_decision_recorded_count"] == 0
    assert result["owner_decision_pending_count"] == 2
    assert "owner_decisions_invalid_path_count=2" in result["closure_blockers"]
    assert {
        tuple(row["owner_decision_missing_requirements"])
        for row in result["review_rows"]
    } == {("signed_owner_exception_reference",)}


def test_owner_review_packet_requires_utc_owner_decision_timestamp(
    tmp_path: Path,
) -> None:
    audit = tmp_path / "audit.json"
    manifest = tmp_path / "manifest.json"
    decisions = tmp_path / "owner_decisions.json"
    _write_json(audit, _audit_payload())
    _write_json(manifest, _manifest_payload())
    payload = _decision_payload("delete_from_structural_repository")
    payload["decision_rows"][0]["decision_timestamp_utc"] = "2026-07-02T00:00:00"
    payload["decision_rows"][1]["decision_timestamp_utc"] = "2026-07-02T09:00:00+09:00"
    _write_json(decisions, payload)

    result = owner_review.build_owner_review_packet(
        repo_root=tmp_path,
        audit_path=audit,
        quarantine_manifest_path=manifest,
        owner_decisions_path=decisions,
    )

    assert result["status"] == "owner_decision_evidence_invalid"
    assert result["owner_decision_recorded_count"] == 0
    assert result["owner_decision_pending_count"] == 2
    assert "owner_decisions_invalid_path_count=2" in result["closure_blockers"]
    assert {
        tuple(row["owner_decision_missing_requirements"])
        for row in result["review_rows"]
    } == {("decision_timestamp_utc_not_utc",)}


def test_owner_review_packet_routes_delete_decisions_to_post_cleanup(
    tmp_path: Path,
) -> None:
    audit = tmp_path / "audit.json"
    manifest = tmp_path / "manifest.json"
    decisions = tmp_path / "owner_decisions.json"
    _write_json(audit, _audit_payload())
    _write_json(manifest, _manifest_payload())
    _write_json(decisions, _decision_payload("delete_from_structural_repository"))

    payload = owner_review.build_owner_review_packet(
        repo_root=tmp_path,
        audit_path=audit,
        quarantine_manifest_path=manifest,
        owner_decisions_path=decisions,
    )

    assert payload["status"] == "ready_for_post_decision_cleanup"
    assert payload["contract_pass"] is True
    assert payload["evidence_closure_pass"] is False
    assert payload["owner_decision_pending_count"] == 0
    assert payload["owner_decision_recorded_count"] == 2
    assert payload["post_decision_cleanup_pending_count"] == 2
    assert payload["closure_blockers"] == ["post_decision_cleanup_pending_count=2"]
    assert {
        row["owner_review_state"] for row in payload["review_rows"]
    } == {"owner_decision_recorded_post_decision_cleanup_pending"}


def test_owner_review_packet_closes_after_delete_extract_cleanup_applied(
    tmp_path: Path,
) -> None:
    audit = tmp_path / "audit.json"
    manifest = tmp_path / "manifest.json"
    decisions = tmp_path / "owner_decisions.json"
    _write_json(audit, _post_cleanup_audit_payload())
    _write_json(manifest, _manifest_payload())
    _write_json(
        decisions,
        {
            "schema_version": owner_review.DECISION_SCHEMA_VERSION,
            "decision_rows": [
                {
                    "path": "implementation/phase1/md3bead_soa.py",
                    "owner_decision": "extract_to_molecular_or_science_repository",
                    "owner_identity": "scope-owner",
                    "owner_role": "product_owner",
                    "decision_timestamp_utc": "2026-07-02T00:00:00Z",
                    "evidence_reference": "owner-review://scope-cleanup/001",
                    "signed_owner_exception_reference": "",
                    "external_archive_reference": "archive://molecular-scope/md3bead_soa",
                },
                {
                    "path": (
                        "implementation/phase1/release_evidence/productization/"
                        "gpcr_hard_decoy_product_report.json"
                    ),
                    "owner_decision": "delete_from_structural_repository",
                    "owner_identity": "scope-owner",
                    "owner_role": "product_owner",
                    "decision_timestamp_utc": "2026-07-02T00:00:00Z",
                    "evidence_reference": "owner-review://scope-cleanup/002",
                    "signed_owner_exception_reference": "",
                    "external_archive_reference": "",
                },
            ],
        },
    )

    payload = owner_review.build_owner_review_packet(
        repo_root=tmp_path,
        audit_path=audit,
        quarantine_manifest_path=manifest,
        owner_decisions_path=decisions,
    )

    assert payload["status"] == "complete"
    assert payload["evidence_closure_pass"] is True
    assert payload["owner_decision_recorded_count"] == 2
    assert payload["owner_decision_pending_count"] == 0
    assert payload["post_decision_cleanup_pending_count"] == 0
    assert payload["post_decision_cleanup_applied_count"] == 2
    assert payload["owner_decisions"]["decision_extra_path_count"] == 0
    assert payload["owner_decisions"]["blockers"] == []
    assert {
        row["owner_decision"]
        for row in payload["post_decision_cleanup_applied_rows"]
    } == {
        "delete_from_structural_repository",
        "extract_to_molecular_or_science_repository",
    }
    rows = {row["path"]: row for row in payload["post_decision_cleanup_applied_rows"]}
    assert rows["implementation/phase1/md3bead_soa.py"][
        "external_archive_reference"
    ] == "archive://molecular-scope/md3bead_soa"


def test_owner_review_packet_requires_archive_reference_for_extract_decisions(
    tmp_path: Path,
) -> None:
    audit = tmp_path / "audit.json"
    manifest = tmp_path / "manifest.json"
    decisions = tmp_path / "owner_decisions.json"
    _write_json(audit, _audit_payload())
    _write_json(manifest, _manifest_payload())
    payload = _decision_payload("extract_to_molecular_or_science_repository")
    for row in payload["decision_rows"]:
        row["external_archive_reference"] = ""
    _write_json(decisions, payload)

    result = owner_review.build_owner_review_packet(
        repo_root=tmp_path,
        audit_path=audit,
        quarantine_manifest_path=manifest,
        owner_decisions_path=decisions,
    )

    assert result["status"] == "owner_decision_evidence_invalid"
    assert result["owner_decision_recorded_count"] == 0
    assert result["owner_decision_pending_count"] == 2
    assert "owner_decisions_invalid_path_count=2" in result["closure_blockers"]
    assert {
        tuple(row["owner_decision_missing_requirements"])
        for row in result["review_rows"]
    } == {("external_archive_reference",)}


def test_owner_review_packet_rejects_release_surface_retain_exception(
    tmp_path: Path,
) -> None:
    audit_payload = _audit_payload()
    manifest_payload = _manifest_payload()
    release_surface_path = (
        "implementation/phase1/release_evidence/surface/"
        "pocketmd_lite_science_product_surface.json"
    )
    audit_payload["quarantined_non_structural_rows"].append(
        {
            "path": release_surface_path,
            "git_state": "tracked",
            "path_area": "release_surface",
            "families": ["molecular_dynamics"],
            "matched_tokens": ["pocketmd"],
            "quarantine_status": "quarantined",
            "excluded_from_structural_release_surface": True,
        }
    )
    manifest_payload["paths"].append(
        {
            "path": release_surface_path,
            "excluded_from_structural_release_surface": True,
        }
    )
    audit = tmp_path / "audit.json"
    manifest = tmp_path / "manifest.json"
    decisions = tmp_path / "owner_decisions.json"
    _write_json(audit, audit_payload)
    _write_json(manifest, manifest_payload)
    _write_json(
        decisions,
        {
            "schema_version": owner_review.DECISION_SCHEMA_VERSION,
            "decision_rows": [
                {
                    "path": release_surface_path,
                    "owner_decision": "retain_quarantined_with_signed_owner_exception",
                    "owner_identity": "scope-owner",
                    "owner_role": "product_owner",
                    "decision_timestamp_utc": "2026-07-02T00:00:00Z",
                    "evidence_reference": "owner-review://scope-cleanup/retain",
                    "signed_owner_exception_reference": (
                        "signed-exception://scope-cleanup/retain"
                    ),
                    "external_archive_reference": "",
                }
            ],
        },
    )

    result = owner_review.build_owner_review_packet(
        repo_root=tmp_path,
        audit_path=audit,
        quarantine_manifest_path=manifest,
        owner_decisions_path=decisions,
    )

    rows = {row["path"]: row for row in result["review_rows"]}
    assert result["status"] == "owner_decision_evidence_invalid"
    assert (
        "owner_decisions_release_surface_retain_exception_count=1"
        in result["closure_blockers"]
    )
    assert result["release_surface_path_count"] == 1
    assert result["release_surface_paths"] == [release_surface_path]
    assert result["release_surface_owner_decision_required_count"] == 1
    assert result["release_surface_owner_decision_required_paths"] == [
        release_surface_path
    ]
    assert result["release_surface_post_decision_cleanup_pending_count"] == 0
    assert result["release_surface_allowed_owner_decisions"] == list(
        owner_review.RELEASE_SURFACE_ALLOWED_OWNER_DECISIONS
    )
    assert result["release_surface_retain_quarantined_exception_allowed"] is False
    assert result["release_surface_owner_review"]["retain_exception_count"] == 1
    assert rows[release_surface_path]["allowed_owner_decisions"] == list(
        owner_review.RELEASE_SURFACE_ALLOWED_OWNER_DECISIONS
    )
    assert rows[release_surface_path]["owner_decision_valid"] is False
    assert "release_surface_retain_exception_not_allowed" in rows[
        release_surface_path
    ]["owner_decision_missing_requirements"]


def test_owner_review_packet_requires_decisions_for_absent_manifest_paths(
    tmp_path: Path,
) -> None:
    audit = tmp_path / "audit.json"
    manifest = tmp_path / "manifest.json"
    _write_json(audit, _post_cleanup_audit_payload())
    _write_json(manifest, _manifest_payload())

    payload = owner_review.build_owner_review_packet(
        repo_root=tmp_path,
        audit_path=audit,
        quarantine_manifest_path=manifest,
    )

    assert payload["status"] == "owner_decision_evidence_invalid"
    assert payload["evidence_closure_pass"] is False
    assert payload["owner_decision_pending_count"] == 2
    assert payload["post_decision_cleanup_missing_owner_decision_count"] == 2
    assert (
        "post_decision_cleanup_missing_owner_decision_count=2"
        in payload["closure_blockers"]
    )


def test_owner_review_packet_blocks_unquarantined_scope_leak(tmp_path: Path) -> None:
    audit_payload = _audit_payload()
    audit_payload["contract_pass"] = False
    audit_payload["blockers"] = ["unquarantined_non_structural_path_count=1"]
    audit_payload["unquarantined_non_structural_rows"] = [
        {
            "path": "scripts/materialize_gpcr_hard_decoy_suite_report.py",
            "git_state": "tracked",
            "path_area": "script",
            "families": ["molecular_docking"],
            "matched_tokens": ["gpcr"],
            "quarantine_status": "unquarantined",
        }
    ]
    audit = tmp_path / "audit.json"
    manifest = tmp_path / "manifest.json"
    _write_json(audit, audit_payload)
    _write_json(manifest, _manifest_payload())

    payload = owner_review.build_owner_review_packet(
        repo_root=tmp_path,
        audit_path=audit,
        quarantine_manifest_path=manifest,
    )

    assert payload["status"] == "blocked_scope_cleanup"
    assert payload["contract_pass"] is False
    assert payload["evidence_closure_pass"] is False
    assert "unquarantined_non_structural_path_count=1" in payload["blockers"]
    assert payload["unquarantined_non_structural_path_count"] == 1


def test_owner_review_packet_writes_json_and_markdown(tmp_path: Path) -> None:
    audit = tmp_path / "audit.json"
    manifest = tmp_path / "manifest.json"
    out = tmp_path / "packet.json"
    out_md = tmp_path / "packet.md"
    _write_json(audit, _audit_payload())
    _write_json(manifest, _manifest_payload())

    payload = owner_review.write_owner_review_packet(
        repo_root=tmp_path,
        audit_path=audit,
        quarantine_manifest_path=manifest,
        out=out,
        out_md=out_md,
    )

    assert payload["status"] == "ready_for_owner_review"
    assert json.loads(out.read_text(encoding="utf-8"))["schema_version"] == (
        owner_review.SCHEMA_VERSION
    )
    markdown = out_md.read_text(encoding="utf-8")
    assert "# Structural Scope Owner Review Packet" in markdown
    assert "## Release Surface First" in markdown
    assert "release_surface_owner_decision_required_count" in markdown
    assert "implementation/phase1/md3bead_soa.py" in markdown


def test_owner_decision_template_writes_fillable_rows(tmp_path: Path) -> None:
    audit = tmp_path / "audit.json"
    manifest = tmp_path / "manifest.json"
    packet = tmp_path / "packet.json"
    packet_md = tmp_path / "packet.md"
    template = tmp_path / "owner_decisions.template.json"
    template_md = tmp_path / "owner_decisions.template.md"
    template_csv = tmp_path / "owner_decisions.template.csv"
    _write_json(audit, _audit_payload())
    _write_json(manifest, _manifest_payload())
    owner_review.write_owner_review_packet(
        repo_root=tmp_path,
        audit_path=audit,
        quarantine_manifest_path=manifest,
        out=packet,
        out_md=packet_md,
    )

    payload = owner_review.write_owner_decision_template(
        repo_root=tmp_path,
        owner_review_packet_path=packet,
        out=template,
        out_md=template_md,
        out_csv=template_csv,
    )

    assert payload["schema_version"] == owner_review.DECISION_SCHEMA_VERSION
    assert payload["status"] == "pending_owner_decisions"
    assert payload["contract_pass"] is True
    assert payload["decision_pending_count"] == 2
    rows = json.loads(template.read_text(encoding="utf-8"))["decision_rows"]
    assert rows[0]["owner_decision"] == ""
    assert rows[0]["owner_identity"] == ""
    assert rows[0]["signed_owner_exception_reference"] == ""
    assert rows[0]["external_archive_reference"] == ""
    assert (
        rows[0]["recommended_owner_decision_primary"]
        == "extract_to_molecular_or_science_repository"
    )
    assert rows[0]["allowed_owner_decisions"] == list(
        owner_review.ALLOWED_OWNER_DECISIONS
    )
    markdown = template_md.read_text(encoding="utf-8")
    assert "# Structural Scope Owner Decision Template" in markdown
    assert "signed_owner_exception_reference" in markdown
    assert "external_archive_reference" in markdown
    assert "extract_to_molecular_or_science_repository" in markdown
    assert "implementation/phase1/md3bead_soa.py" in markdown
    csv_rows = list(csv.DictReader(template_csv.read_text(encoding="utf-8").splitlines()))
    assert csv_rows[0]["path"] == "implementation/phase1/md3bead_soa.py"
    assert csv_rows[0]["owner_decision"] == ""
    assert csv_rows[0]["signed_owner_exception_reference"] == ""
    assert csv_rows[0]["external_archive_reference"] == ""
    assert csv_rows[0]["recommended_owner_decision"] == (
        "extract_to_molecular_or_science_repository_or_delete_if_obsolete"
    )
    assert (
        csv_rows[0]["recommended_owner_decision_primary"]
        == "extract_to_molecular_or_science_repository"
    )
    assert csv_rows[0]["recommended_owner_decision_alternate"] == (
        "delete_from_structural_repository"
    )
    assert csv_rows[0]["allowed_owner_decisions"] == ";".join(
        owner_review.ALLOWED_OWNER_DECISIONS
    )


def test_owner_review_packet_accepts_owner_decision_csv(tmp_path: Path) -> None:
    audit = tmp_path / "audit.json"
    manifest = tmp_path / "manifest.json"
    decisions = tmp_path / "owner_decisions.csv"
    _write_json(audit, _audit_payload())
    _write_json(manifest, _manifest_payload())
    decisions.write_text(
        "\n".join(
            [
                ",".join(owner_review.OWNER_DECISION_COLUMNS),
                (
                    "row-1,implementation/phase1/md3bead_soa.py,"
                    "implementation_phase1,molecular_dynamics,md3bead,"
                    "extract_to_molecular_or_science_repository_or_delete_if_obsolete,"
                    "extract_to_molecular_or_science_repository,"
                    "delete_from_structural_repository,"
                    "extract_to_molecular_or_science_repository,scope-owner,"
                    "product_owner,2026-07-02T00:00:00Z,"
                    "owner-review://scope-cleanup/001,,"
                    "archive://molecular-scope/md3bead_soa"
                ),
                (
                    "row-2,"
                    "implementation/phase1/release_evidence/productization/"
                    "gpcr_hard_decoy_product_report.json,productization_evidence,"
                    "molecular_docking,gpcr,"
                    "delete_from_structural_repository_or_extract_only_if_owner_requires_history,"
                    "delete_from_structural_repository,"
                    "extract_to_molecular_or_science_repository,"
                    "delete_from_structural_repository,scope-owner,product_owner,"
                    "2026-07-02T00:00:00Z,"
                    "owner-review://scope-cleanup/002,,"
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )

    payload = owner_review.build_owner_review_packet(
        repo_root=tmp_path,
        audit_path=audit,
        quarantine_manifest_path=manifest,
        owner_decisions_path=decisions,
    )

    assert payload["status"] == "ready_for_post_decision_cleanup"
    assert payload["owner_decisions"]["decision_format"] == "csv"
    assert payload["owner_decisions"]["blockers"] == []
    assert payload["owner_decision_pending_count"] == 0
    assert payload["post_decision_cleanup_pending_count"] == 2


def test_owner_review_packet_blocks_extra_and_duplicate_decision_paths(
    tmp_path: Path,
) -> None:
    audit = tmp_path / "audit.json"
    manifest = tmp_path / "manifest.json"
    decisions = tmp_path / "owner_decisions.json"
    _write_json(audit, _audit_payload())
    _write_json(manifest, _manifest_payload())
    payload = _decision_payload("retain_quarantined_with_signed_owner_exception")
    payload["decision_rows"].append(dict(payload["decision_rows"][0]))
    payload["decision_rows"].append(
        {
            "path": "scripts/not_in_quarantine.py",
            "owner_decision": "retain_quarantined_with_signed_owner_exception",
            "owner_identity": "scope-owner",
            "owner_role": "product_owner",
            "decision_timestamp_utc": "2026-07-02T00:00:00Z",
            "evidence_reference": "owner-review://scope-cleanup/extra",
            "signed_owner_exception_reference": (
                "signed-exception://scope-cleanup/extra"
            ),
            "external_archive_reference": "",
        }
    )
    _write_json(decisions, payload)

    result = owner_review.build_owner_review_packet(
        repo_root=tmp_path,
        audit_path=audit,
        quarantine_manifest_path=manifest,
        owner_decisions_path=decisions,
    )

    assert result["status"] == "owner_decision_evidence_invalid"
    assert "owner_decisions_extra_path_count=1" in result["closure_blockers"]
    assert "owner_decisions_duplicate_path_count=1" in result["closure_blockers"]
    assert result["owner_decisions"]["decision_duplicate_paths"] == [
        "implementation/phase1/md3bead_soa.py"
    ]
