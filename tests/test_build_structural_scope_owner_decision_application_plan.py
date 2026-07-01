from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "build_structural_scope_owner_decision_application_plan.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_structural_scope_owner_decision_application_plan", SCRIPT_PATH
)
assert SPEC is not None
application_plan = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = application_plan
SPEC.loader.exec_module(application_plan)


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


def _decision_row(path: str, decision: str, index: int) -> dict:
    return {
        "path": path,
        "owner_decision": decision,
        "owner_identity": "scope-owner",
        "owner_role": "product_owner",
        "decision_timestamp_utc": "2026-07-02T00:00:00Z",
        "evidence_reference": f"owner-review://scope-cleanup/{index:03d}",
        "signed_owner_exception_reference": (
            f"signed-exception://scope-cleanup/{index:03d}"
        ),
        "external_archive_reference": f"archive://molecular-scope/{index:03d}",
    }


def _decision_payload(*decisions: tuple[str, str]) -> dict:
    return {
        "schema_version": application_plan.owner_review.DECISION_SCHEMA_VERSION,
        "decision_rows": [
            _decision_row(path, decision, index + 1)
            for index, (path, decision) in enumerate(decisions)
        ],
    }


def _write_inputs(tmp_path: Path) -> tuple[Path, Path]:
    audit = tmp_path / "audit.json"
    manifest = tmp_path / "manifest.json"
    _write_json(audit, _audit_payload())
    _write_json(manifest, _manifest_payload())
    return audit, manifest


def test_application_plan_waits_for_owner_decisions(tmp_path: Path) -> None:
    audit, manifest = _write_inputs(tmp_path)

    payload = application_plan.build_application_plan(
        repo_root=tmp_path,
        audit_path=audit,
        quarantine_manifest_path=manifest,
        owner_decisions_path=tmp_path / "missing_decisions.json",
    )

    assert payload["status"] == "pending_owner_decisions"
    assert payload["summary_line"] == (
        "Structural scope owner decision application plan: "
        "PENDING_OWNER_DECISIONS | recorded=0 | pending=2 | "
        "cleanup_pending=0 | delete=0 | extract=0 | retain=0 | "
        "unquarantined=0"
    )
    assert payload["contract_pass"] is True
    assert payload["application_ready"] is False
    assert payload["evidence_closure_pass"] is False
    assert payload["owner_decision_validation_pass"] is False
    assert payload["owner_decision_validation_blockers"] == [
        "owner_decisions_missing",
        "owner_decision_pending_count=2",
    ]
    assert payload["owner_decision_pending_count"] == 2
    assert payload["post_decision_cleanup_pending_count"] == 0
    assert payload["plan_blockers"] == ["owner_decision_pending_count=2"]
    assert payload["application_blockers"] == [
        "owner_decisions_missing",
        "owner_decision_pending_count=2",
    ]
    assert payload["blockers"] == payload["plan_blockers"]
    assert payload["pending_owner_decision_path_area_counts"] == {
        "implementation_phase1": 1,
        "productization_evidence": 1,
    }
    assert payload["pending_owner_decision_family_counts"] == {
        "molecular_docking": 1,
        "molecular_dynamics": 1,
    }
    assert payload["pending_owner_decision_recommended_owner_decision_counts"] == {
        "delete_from_structural_repository_or_extract_only_if_owner_requires_history": 1,
        "extract_to_molecular_or_science_repository_or_delete_if_obsolete": 1,
    }
    assert payload["pending_owner_decision_primary_counts"] == {
        "delete_from_structural_repository": 1,
        "extract_to_molecular_or_science_repository": 1,
    }
    assert payload["next_owner_review_batch"]["batch_id"] == (
        "productization_evidence_second"
    )
    assert payload["next_owner_review_batch"]["path_count"] == 1
    assert payload["next_owner_review_batch"]["paths"] == [
        (
            "implementation/phase1/release_evidence/productization/"
            "gpcr_hard_decoy_product_report.json"
        )
    ]
    assert [
        row["batch_id"] for row in payload["owner_review_priority_batches"]
    ] == [
        "productization_evidence_second",
        "implementation_phase1_cleanup_fifth",
    ]
    assert payload["release_surface_owner_decision_required_count"] == 0
    assert payload["owner_decision_template_paths"] == {
        "json": (
            "implementation/phase1/release_evidence/productization/"
            "structural_scope_owner_decisions.template.json"
        ),
        "csv": (
            "implementation/phase1/release_evidence/productization/"
            "structural_scope_owner_decisions.template.csv"
        ),
        "markdown": (
            "implementation/phase1/release_evidence/productization/"
            "structural_scope_owner_decisions.template.md"
        ),
    }
    assert payload["cleanup_required_count"] == 0
    assert payload["cleanup_command_manifest"]["manual_application_required"] is False
    assert payload["next_actions"][0].startswith(
        "fill structural_scope_owner_decisions"
    )
    assert len(payload["pending_owner_decision_rows"]) == 2


def test_application_plan_prioritizes_pending_release_surface_owner_review(
    tmp_path: Path,
) -> None:
    audit = _audit_payload()
    manifest = _manifest_payload()
    release_surface_path = (
        "implementation/phase1/release_evidence/surface/"
        "pocketmd_lite_science_product_surface.json"
    )
    audit["quarantined_non_structural_rows"].append(
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
    manifest["paths"].append(
        {
            "path": release_surface_path,
            "excluded_from_structural_release_surface": True,
        }
    )
    audit_path = tmp_path / "audit.json"
    manifest_path = tmp_path / "manifest.json"
    _write_json(audit_path, audit)
    _write_json(manifest_path, manifest)

    payload = application_plan.build_application_plan(
        repo_root=tmp_path,
        audit_path=audit_path,
        quarantine_manifest_path=manifest_path,
        owner_decisions_path=tmp_path / "missing_decisions.json",
    )

    assert payload["status"] == "pending_owner_decisions"
    assert payload["release_surface_owner_decision_required_count"] == 1
    assert payload["next_owner_review_batch"]["batch_id"] == "release_surface_first"
    assert payload["next_owner_review_batch"]["priority"] == 1
    assert payload["next_owner_review_batch"]["paths"] == [release_surface_path]
    batch_template = payload["next_owner_review_batch_decision_template"]
    assert batch_template["schema_version"] == (
        application_plan.owner_review.DECISION_SCHEMA_VERSION
    )
    assert batch_template["batch_id"] == "release_surface_first"
    assert batch_template["path_area"] == "release_surface"
    assert batch_template["decision_pending_count"] == 1
    assert batch_template["canonical_owner_decisions_path"] == (
        "implementation/phase1/release_evidence/productization/"
        "structural_scope_owner_decisions.json"
    )
    assert batch_template["decision_rows"] == [
        {
            "row_id": "release_surface_first-001",
            "path": release_surface_path,
            "path_area": "release_surface",
            "families": ["molecular_dynamics"],
            "matched_tokens": ["pocketmd"],
            "current_release_action": (
                "keep_quarantined_until_owner_delete_or_extract_decision"
            ),
            "recommended_owner_decision": (
                "delete_from_structural_repository_or_extract_only_if_owner_requires_history"
            ),
            "recommended_owner_decision_primary": "delete_from_structural_repository",
            "recommended_owner_decision_alternate": (
                "extract_to_molecular_or_science_repository"
            ),
            "allowed_owner_decisions": list(
                application_plan.owner_review.ALLOWED_OWNER_DECISIONS
            ),
            "owner_decision": "",
            "owner_identity": "",
            "owner_role": "",
            "decision_timestamp_utc": "",
            "evidence_reference": "",
            "signed_owner_exception_reference": "",
            "external_archive_reference": "",
            "post_decision_required_action": (
                "delete_or_extract_path_then_rerun_scope_audit"
            ),
        }
    ]
    assert batch_template["primary_cleanup_preview"] == {
        "safe_to_auto_apply": False,
        "owner_decision_required": True,
        "primary_delete_path_count": 1,
        "primary_delete_paths": [release_surface_path],
        "primary_delete_git_rm_args": ["git", "rm", "--", release_surface_path],
        "primary_extract_path_count": 0,
        "primary_extract_paths": [],
        "primary_extract_post_archive_git_rm_args": [],
        "preconditions": [
            (
                "owner fills matching decision rows in "
                "structural_scope_owner_decisions.json or CSV"
            ),
            "owner_decision_validation_pass=true for these rows",
            "human confirms the batch cleanup scope",
        ],
    }
    assert [
        row["batch_id"] for row in payload["owner_review_priority_batches"]
    ] == [
        "release_surface_first",
        "productization_evidence_second",
        "implementation_phase1_cleanup_fifth",
    ]


def test_application_plan_routes_delete_and_extract_decisions(tmp_path: Path) -> None:
    audit, manifest = _write_inputs(tmp_path)
    decisions = tmp_path / "owner_decisions.json"
    _write_json(
        decisions,
        _decision_payload(
            ("implementation/phase1/md3bead_soa.py", "extract_to_molecular_or_science_repository"),
            (
                "implementation/phase1/release_evidence/productization/"
                "gpcr_hard_decoy_product_report.json",
                "delete_from_structural_repository",
            ),
        ),
    )

    payload = application_plan.build_application_plan(
        repo_root=tmp_path,
        audit_path=audit,
        quarantine_manifest_path=manifest,
        owner_decisions_path=decisions,
    )

    assert payload["status"] == "ready_for_cleanup_application"
    assert payload["application_ready"] is True
    assert payload["evidence_closure_pass"] is False
    assert payload["owner_decision_validation_pass"] is True
    assert payload["owner_decision_validation_blockers"] == []
    assert payload["owner_decision_pending_count"] == 0
    assert payload["post_decision_cleanup_pending_count"] == 2
    assert payload["cleanup_required_count"] == 2
    assert payload["cleanup_path_area_counts"] == {
        "implementation_phase1": 1,
        "productization_evidence": 1,
    }
    assert payload["cleanup_family_counts"] == {
        "molecular_docking": 1,
        "molecular_dynamics": 1,
    }
    assert payload["delete_decision_count"] == 1
    assert payload["extract_decision_count"] == 1
    assert payload["delete_path_count"] == 1
    assert payload["extract_path_count"] == 1
    assert len(payload["cleanup_rows"]) == 2
    manifest = payload["cleanup_command_manifest"]
    assert manifest["safe_to_auto_apply"] is False
    assert manifest["manual_application_required"] is True
    assert manifest["delete_from_structural_repository"]["batched_git_rm_args"] == [
        "git",
        "rm",
        "--",
        (
            "implementation/phase1/release_evidence/productization/"
            "gpcr_hard_decoy_product_report.json"
        ),
    ]
    assert manifest["extract_to_molecular_or_science_repository"][
        "post_extract_batched_git_rm_args"
    ] == ["git", "rm", "--", "implementation/phase1/md3bead_soa.py"]
    rows = {row["path"]: row for row in payload["cleanup_rows"]}
    assert rows["implementation/phase1/md3bead_soa.py"]["required_action"] == (
        "extract_elsewhere_then_remove_from_structural_repository"
    )
    assert rows[
        "implementation/phase1/release_evidence/productization/"
        "gpcr_hard_decoy_product_report.json"
    ]["suggested_git_rm_args"] == [
        "git",
        "rm",
        "--",
        "implementation/phase1/release_evidence/productization/"
        "gpcr_hard_decoy_product_report.json",
    ]


def test_application_plan_accepts_owner_decision_csv(tmp_path: Path) -> None:
    audit, manifest = _write_inputs(tmp_path)
    decisions = tmp_path / "owner_decisions.csv"
    decisions.write_text(
        "\n".join(
            [
                ",".join(application_plan.owner_review.OWNER_DECISION_COLUMNS),
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

    payload = application_plan.build_application_plan(
        repo_root=tmp_path,
        audit_path=audit,
        quarantine_manifest_path=manifest,
        owner_decisions_path=decisions,
    )

    assert payload["status"] == "ready_for_cleanup_application"
    assert payload["application_ready"] is True
    assert payload["owner_decision_validation_pass"] is True
    assert payload["owner_decision_validation_blockers"] == []
    assert payload["owner_decision_pending_count"] == 0
    assert payload["post_decision_cleanup_pending_count"] == 2


def test_application_plan_prioritizes_release_surface_cleanup_commands(
    tmp_path: Path,
) -> None:
    audit = _audit_payload()
    manifest = _manifest_payload()
    release_surface_path = (
        "implementation/phase1/release_evidence/surface/"
        "pocketmd_lite_science_product_surface.json"
    )
    audit["quarantined_non_structural_rows"].append(
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
    manifest["paths"].append(
        {
            "path": release_surface_path,
            "excluded_from_structural_release_surface": True,
        }
    )
    audit_path = tmp_path / "audit.json"
    manifest_path = tmp_path / "manifest.json"
    decisions = tmp_path / "owner_decisions.json"
    _write_json(audit_path, audit)
    _write_json(manifest_path, manifest)
    _write_json(
        decisions,
        _decision_payload(
            (
                "implementation/phase1/md3bead_soa.py",
                "extract_to_molecular_or_science_repository",
            ),
            (
                "implementation/phase1/release_evidence/productization/"
                "gpcr_hard_decoy_product_report.json",
                "delete_from_structural_repository",
            ),
            (release_surface_path, "delete_from_structural_repository"),
        ),
    )

    payload = application_plan.build_application_plan(
        repo_root=tmp_path,
        audit_path=audit_path,
        quarantine_manifest_path=manifest_path,
        owner_decisions_path=decisions,
    )

    assert payload["cleanup_required_count"] == 3
    assert payload["release_surface_cleanup_required_count"] == 1
    assert payload["release_surface_owner_decision_required_count"] == 0
    assert payload["release_surface_cleanup_paths"] == [release_surface_path]
    assert payload["cleanup_command_manifest"]["release_surface_first_paths"] == [
        release_surface_path
    ]
    assert release_surface_path in payload["cleanup_command_manifest"][
        "delete_from_structural_repository"
    ]["paths"]


def test_application_plan_closes_retain_exception_decisions(tmp_path: Path) -> None:
    audit, manifest = _write_inputs(tmp_path)
    decisions = tmp_path / "owner_decisions.json"
    _write_json(
        decisions,
        _decision_payload(
            (
                "implementation/phase1/md3bead_soa.py",
                "retain_quarantined_with_signed_owner_exception",
            ),
            (
                "implementation/phase1/release_evidence/productization/"
                "gpcr_hard_decoy_product_report.json",
                "retain_quarantined_with_signed_owner_exception",
            ),
        ),
    )

    payload = application_plan.build_application_plan(
        repo_root=tmp_path,
        audit_path=audit,
        quarantine_manifest_path=manifest,
        owner_decisions_path=decisions,
    )

    assert payload["status"] == "complete"
    assert payload["application_ready"] is False
    assert payload["evidence_closure_pass"] is True
    assert payload["owner_decision_validation_pass"] is True
    assert payload["owner_decision_validation_blockers"] == []
    assert payload["owner_decision_pending_count"] == 0
    assert payload["post_decision_cleanup_pending_count"] == 0
    assert payload["retain_quarantined_exception_count"] == 2
    assert payload["cleanup_required_count"] == 0
    assert payload["next_actions"] == []
    assert payload["cleanup_rows"] == []
    assert len(payload["retain_exception_rows"]) == 2
    assert {
        row["signed_owner_exception_reference"]
        for row in payload["retain_exception_rows"]
    } == {
        "signed-exception://scope-cleanup/001",
        "signed-exception://scope-cleanup/002",
    }


def test_application_plan_closes_after_delete_extract_cleanup_applied(
    tmp_path: Path,
) -> None:
    audit = tmp_path / "audit.json"
    manifest = tmp_path / "manifest.json"
    decisions = tmp_path / "owner_decisions.json"
    _write_json(audit, _post_cleanup_audit_payload())
    _write_json(manifest, _manifest_payload())
    _write_json(
        decisions,
        _decision_payload(
            (
                "implementation/phase1/md3bead_soa.py",
                "extract_to_molecular_or_science_repository",
            ),
            (
                "implementation/phase1/release_evidence/productization/"
                "gpcr_hard_decoy_product_report.json",
                "delete_from_structural_repository",
            ),
        ),
    )

    payload = application_plan.build_application_plan(
        repo_root=tmp_path,
        audit_path=audit,
        quarantine_manifest_path=manifest,
        owner_decisions_path=decisions,
    )

    assert payload["status"] == "complete"
    assert payload["application_ready"] is False
    assert payload["evidence_closure_pass"] is True
    assert payload["owner_decision_validation_pass"] is True
    assert payload["owner_decision_pending_count"] == 0
    assert payload["post_decision_cleanup_pending_count"] == 0
    assert payload["post_decision_cleanup_applied_count"] == 2
    assert payload["cleanup_required_count"] == 0
    assert payload["next_actions"] == []
    assert payload["cleanup_rows"] == []
    assert len(payload["post_decision_cleanup_applied_rows"]) == 2


def test_application_plan_writes_json_and_markdown(tmp_path: Path) -> None:
    audit, manifest = _write_inputs(tmp_path)
    out = tmp_path / "plan.json"
    out_md = tmp_path / "plan.md"

    payload = application_plan.write_application_plan(
        repo_root=tmp_path,
        audit_path=audit,
        quarantine_manifest_path=manifest,
        owner_decisions_path=tmp_path / "missing_decisions.json",
        out=out,
        out_md=out_md,
    )

    assert payload["status"] == "pending_owner_decisions"
    assert json.loads(out.read_text(encoding="utf-8"))["schema_version"] == (
        application_plan.SCHEMA_VERSION
    )
    markdown = out_md.read_text(encoding="utf-8")
    assert "# Structural Scope Owner Decision Application Plan" in markdown
    assert "summary_line" in markdown
    assert "Pending Owner Decision Buckets" in markdown
    assert "owner_decision_validation_pass" in markdown
    assert "cleanup_required_count" in markdown
    assert "Cleanup Command Manifest" in markdown
    assert "owner_decision_pending_count=2" in markdown


def test_application_plan_fail_invalid_owner_decisions_exit_code(
    tmp_path: Path,
) -> None:
    audit, manifest = _write_inputs(tmp_path)
    invalid_exit = application_plan.main(
        [
            "--repo-root",
            str(tmp_path),
            "--audit",
            str(audit),
            "--quarantine-manifest",
            str(manifest),
            "--owner-decisions",
            str(tmp_path / "missing_decisions.json"),
            "--out",
            str(tmp_path / "invalid_plan.json"),
            "--out-md",
            str(tmp_path / "invalid_plan.md"),
            "--fail-invalid-owner-decisions",
        ]
    )
    assert invalid_exit == 1

    decisions = tmp_path / "owner_decisions.json"
    _write_json(
        decisions,
        _decision_payload(
            ("implementation/phase1/md3bead_soa.py", "extract_to_molecular_or_science_repository"),
            (
                "implementation/phase1/release_evidence/productization/"
                "gpcr_hard_decoy_product_report.json",
                "delete_from_structural_repository",
            ),
        ),
    )
    valid_exit = application_plan.main(
        [
            "--repo-root",
            str(tmp_path),
            "--audit",
            str(audit),
            "--quarantine-manifest",
            str(manifest),
            "--owner-decisions",
            str(decisions),
            "--out",
            str(tmp_path / "valid_plan.json"),
            "--out-md",
            str(tmp_path / "valid_plan.md"),
            "--fail-invalid-owner-decisions",
        ]
    )
    assert valid_exit == 0
    assert json.loads((tmp_path / "valid_plan.json").read_text(encoding="utf-8"))[
        "owner_decision_validation_pass"
    ] is True
