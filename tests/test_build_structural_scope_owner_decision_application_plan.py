from __future__ import annotations

import importlib.util
import csv
import json
from pathlib import Path
import subprocess
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


def _init_git_repo(path: Path) -> None:
    subprocess.check_call(["git", "init"], cwd=path, stdout=subprocess.DEVNULL)
    subprocess.check_call(["git", "config", "user.email", "test@example.invalid"], cwd=path)
    subprocess.check_call(["git", "config", "user.name", "Test User"], cwd=path)


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


def _write_release_surface_inputs(tmp_path: Path) -> tuple[Path, Path, Path, str]:
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
    origin_report_path = tmp_path / "origin_report.json"
    _write_json(audit_path, audit)
    _write_json(manifest_path, manifest)
    _write_json(
        origin_report_path,
        {
            "origin_rows": [
                {
                    "path": release_surface_path,
                    "origin_wave": "pocketmd_productization_evidence_wave",
                    "first_added_commit_sha": "01e6fe1b00000000000000000000000000000000",
                    "first_added_commit_short_sha": "01e6fe1b",
                    "first_added_commit_date": "2026-06-30",
                    "first_added_commit_subject": (
                        "Materialize PocketMD Lite product surface"
                    ),
                }
            ]
        },
    )
    return audit_path, manifest_path, origin_report_path, release_surface_path


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
    next_template = payload["next_owner_review_batch_decision_template"]
    assert next_template["decision_overrides_template_paths"] == {
        "csv": (
            "implementation/phase1/release_evidence/productization/"
            "structural_scope_owner_decisions.next_batch.overrides.template.csv"
        ),
        "markdown": (
            "implementation/phase1/release_evidence/productization/"
            "structural_scope_owner_decisions.next_batch.overrides.template.md"
        ),
    }
    assert next_template["decision_overrides_template_columns"] == [
        "path",
        "owner_decision",
        "external_archive_reference",
        "signed_owner_exception_reference",
        "evidence_reference",
    ]
    assert [
        row["batch_id"] for row in payload["owner_review_priority_batches"]
    ] == [
        "productization_evidence_second",
        "implementation_phase1_cleanup_fifth",
    ]
    assert payload["release_surface_owner_decision_required_count"] == 0
    assert payload["release_surface_first_batch_decision_intake"]["status"] == (
        "no_release_surface_paths"
    )
    assert payload["release_surface_first_batch_decision_intake"][
        "expected_path_count"
    ] == 0
    assert payload["release_surface_first_batch_ready"] is False
    assert payload["release_surface_first_batch_blockers"] == []
    assert payload["release_surface_first_batch_decision_template"] == {}
    assert payload["release_surface_first_owner_action_packet"] == {}
    assert payload["release_surface_first_batch_template_paths"] == {}
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
    assert payload["cleanup_application_preflight"]["status"] == "no_cleanup_required"
    assert payload["cleanup_application_preflight_ready"] is False
    assert payload["cleanup_application_preflight_blockers"] == []
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
    origin_report_path = tmp_path / "origin_report.json"
    _write_json(audit_path, audit)
    _write_json(manifest_path, manifest)
    _write_json(
        origin_report_path,
        {
            "origin_rows": [
                {
                    "path": release_surface_path,
                    "origin_wave": "pocketmd_productization_evidence_wave",
                    "first_added_commit_sha": "01e6fe1b00000000000000000000000000000000",
                    "first_added_commit_short_sha": "01e6fe1b",
                    "first_added_commit_date": "2026-06-30",
                    "first_added_commit_subject": (
                        "Materialize PocketMD Lite product surface"
                    ),
                }
            ]
        },
    )

    payload = application_plan.build_application_plan(
        repo_root=tmp_path,
        audit_path=audit_path,
        quarantine_manifest_path=manifest_path,
        owner_decisions_path=tmp_path / "missing_decisions.json",
        origin_report_path=origin_report_path,
    )

    assert payload["status"] == "pending_owner_decisions"
    assert payload["release_surface_owner_decision_required_count"] == 1
    intake = payload["release_surface_first_batch_decision_intake"]
    assert intake["schema_version"] == (
        "structural-scope-release-surface-first-batch-decision-intake.v1"
    )
    assert intake["batch_id"] == "release_surface_first"
    assert intake["status"] == "pending_owner_decisions"
    assert intake["ready_for_manual_cleanup_application"] is False
    assert intake["expected_path_count"] == 1
    assert intake["expected_paths"] == [release_surface_path]
    assert intake["submitted_decision_count"] == 0
    assert intake["valid_decision_count"] == 0
    assert intake["valid_cleanup_decision_count"] == 0
    assert intake["pending_decision_count"] == 1
    assert intake["pending_decision_paths"] == [release_surface_path]
    assert intake["invalid_submitted_decision_count"] == 0
    assert intake["blockers"] == [
        "pending_release_surface_owner_decision_count=1",
        "release_surface_cleanup_decision_count_below_expected=0/1",
    ]
    assert intake["decision_rows"][0]["allowed_owner_decisions"] == list(
        application_plan.owner_review.RELEASE_SURFACE_ALLOWED_OWNER_DECISIONS
    )
    assert payload["release_surface_first_batch_ready"] is False
    assert payload["release_surface_first_batch_blockers"] == intake["blockers"]
    release_template = payload["release_surface_first_batch_decision_template"]
    assert release_template["batch_id"] == "release_surface_first"
    assert release_template["path_area"] == "release_surface"
    assert release_template["expected_path_count"] == 1
    assert release_template["decision_pending_count"] == 1
    assert release_template["current_intake_status"] == "pending_owner_decisions"
    assert release_template["current_intake_blockers"] == intake["blockers"]
    assert release_template["generated_template_paths"] == {
        "json": (
            "implementation/phase1/release_evidence/productization/"
            "structural_scope_owner_decisions.release_surface_first.template.json"
        ),
        "csv": (
            "implementation/phase1/release_evidence/productization/"
            "structural_scope_owner_decisions.release_surface_first.template.csv"
        ),
        "markdown": (
            "implementation/phase1/release_evidence/productization/"
            "structural_scope_owner_decisions.release_surface_first.template.md"
        ),
    }
    assert release_template["decision_rows"][0]["row_id"] == (
        "release_surface_first-001"
    )
    assert release_template["decision_rows"][0]["path"] == release_surface_path
    assert release_template["origin_context_source_report"] == (
        origin_report_path.as_posix()
    )
    assert release_template["origin_context_complete"] is True
    assert release_template["decision_rows"][0]["origin_wave"] == (
        "pocketmd_productization_evidence_wave"
    )
    assert release_template["decision_rows"][0]["first_added_commit_short_sha"] == (
        "01e6fe1b"
    )
    assert release_template["decision_rows"][0]["allowed_owner_decisions"] == list(
        application_plan.owner_review.RELEASE_SURFACE_ALLOWED_OWNER_DECISIONS
    )
    assert payload["release_surface_first_batch_template_paths"] == (
        release_template["generated_template_paths"]
    )
    assert payload["release_surface_first_decision_overrides_template_paths"] == (
        release_template["mixed_decision_overrides_template_paths"]
    )
    action_packet = payload["release_surface_first_owner_action_packet"]
    assert action_packet["schema_version"] == (
        "structural-scope-release-surface-first-owner-action-packet.v1"
    )
    assert action_packet["batch_id"] == "release_surface_first"
    assert action_packet["status"] == "ready_for_owner_decision_request"
    assert action_packet["ready_to_request_owner_decision"] is True
    assert action_packet["path_area"] == "release_surface"
    assert action_packet["path_count"] == 1
    assert action_packet["paths"] == [release_surface_path]
    assert action_packet["release_surface_owner_decision_required_count"] == 1
    assert action_packet["pending_decision_count"] == 1
    assert action_packet["current_intake_status"] == "pending_owner_decisions"
    assert action_packet["current_intake_blockers"] == intake["blockers"]
    assert action_packet["allowed_owner_decisions"] == list(
        application_plan.owner_review.RELEASE_SURFACE_ALLOWED_OWNER_DECISIONS
    )
    assert action_packet["disallowed_owner_decisions"] == [
        "retain_quarantined_with_signed_owner_exception"
    ]
    assert action_packet["required_owner_fields"] == [
        "owner_decision",
        "owner_identity",
        "owner_role",
        "decision_timestamp_utc",
        "evidence_reference",
    ]
    assert action_packet["conditional_required_fields"] == [
        "external_archive_reference when owner_decision=extract_to_molecular_or_science_repository"
    ]
    assert action_packet["primary_recommendation_counts"] == {
        "delete_from_structural_repository": 1
    }
    assert action_packet["decision_request_rows"] == [
        {
            "row_id": "release_surface_first-001",
            "path": release_surface_path,
            "families": ["molecular_dynamics"],
            "matched_tokens": ["pocketmd"],
            "allowed_owner_decisions": list(
                application_plan.owner_review.RELEASE_SURFACE_ALLOWED_OWNER_DECISIONS
            ),
            "recommended_owner_decision_primary": "delete_from_structural_repository",
            "recommended_owner_decision_alternate": (
                "extract_to_molecular_or_science_repository"
            ),
            "origin_wave": "pocketmd_productization_evidence_wave",
            "first_added_commit_sha": "01e6fe1b00000000000000000000000000000000",
            "first_added_commit_short_sha": "01e6fe1b",
            "first_added_commit_date": "2026-06-30",
            "first_added_commit_subject": (
                "Materialize PocketMD Lite product surface"
            ),
            "post_decision_required_action": (
                "delete_or_extract_path_then_rerun_scope_audit"
            ),
        }
    ]
    assert action_packet["template_paths"] == release_template[
        "generated_template_paths"
    ]
    assert action_packet["mixed_decision_overrides_template_paths"] == (
        release_template["mixed_decision_overrides_template_paths"]
    )
    assert action_packet["mixed_decision_overrides_template_columns"] == [
        "path",
        "owner_decision",
        "external_archive_reference",
        "evidence_reference",
    ]
    assert action_packet["owner_decision_submission_options"] == release_template[
        "owner_decision_submission_options"
    ]
    assert action_packet["primary_cleanup_preview"] == release_template[
        "primary_cleanup_preview"
    ]
    assert action_packet["post_decision_verification"] == release_template[
        "post_batch_verification"
    ]
    assert "not an owner decision" in action_packet["claim_boundary"]
    assert "does not delete or extract files" in action_packet["claim_boundary"]
    operator_sequence = payload["release_surface_first_operator_sequence"]
    assert operator_sequence["schema_version"] == (
        "structural-scope-release-surface-first-operator-sequence.v1"
    )
    assert operator_sequence["status"] == "waiting_for_owner_decision"
    assert payload["release_surface_first_operator_sequence_status"] == (
        "waiting_for_owner_decision"
    )
    assert operator_sequence["current_step_id"] == (
        "fill_release_surface_first_owner_decisions"
    )
    assert payload["release_surface_first_current_step_id"] == (
        "fill_release_surface_first_owner_decisions"
    )
    assert operator_sequence["pending_decision_count"] == 1
    assert operator_sequence["ready_for_manual_cleanup_application"] is False
    assert operator_sequence["blockers"] == intake["blockers"]
    assert operator_sequence["step_count"] == 7
    sequence_steps = {
        step["step_id"]: step for step in operator_sequence["steps"]
    }
    assert sequence_steps["fill_release_surface_first_owner_decisions"][
        "runnable_now"
    ] is True
    assert sequence_steps["fill_release_surface_first_owner_decisions"][
        "status"
    ] == "waiting_for_owner_input"
    assert (
        release_template["mixed_decision_overrides_template_paths"]["csv"]
        in sequence_steps["fill_release_surface_first_owner_decisions"][
            "required_artifacts"
        ]
    )
    assert (
        "--decision-overrides <release-surface-decision-overrides.csv>"
        in " ".join(
            sequence_steps["fill_release_surface_first_owner_decisions"][
                "materialization_commands"
            ]
        )
    )
    assert sequence_steps["validate_filled_owner_decisions"][
        "runnable_now"
    ] is False
    assert sequence_steps["manual_cleanup_application"]["runnable_now"] is False
    assert (
        "--owner-decisions <filled-release-surface-first-owner-decisions.csv>"
        in sequence_steps["validate_filled_owner_decisions"][
            "validation_commands"
        ][0]
    )
    assert payload["next_owner_review_batch"]["batch_id"] == "release_surface_first"
    assert payload["next_owner_review_batch"]["priority"] == 1
    assert payload["next_owner_review_batch"]["paths"] == [release_surface_path]
    assert payload["next_owner_review_batch"]["review_goal"] == (
        "record owner delete/extract decisions only; retain exceptions are not "
        "allowed for release-surface paths"
    )
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
    assert batch_template["generated_template_paths"] == {
        "json": (
            "implementation/phase1/release_evidence/productization/"
            "structural_scope_owner_decisions.next_batch.template.json"
        ),
        "csv": (
            "implementation/phase1/release_evidence/productization/"
            "structural_scope_owner_decisions.next_batch.template.csv"
        ),
        "markdown": (
            "implementation/phase1/release_evidence/productization/"
            "structural_scope_owner_decisions.next_batch.template.md"
        ),
    }
    assert batch_template["decision_overrides_template_paths"] == {
        "csv": (
            "implementation/phase1/release_evidence/productization/"
            "structural_scope_owner_decisions.next_batch.overrides.template.csv"
        ),
        "markdown": (
            "implementation/phase1/release_evidence/productization/"
            "structural_scope_owner_decisions.next_batch.overrides.template.md"
        ),
    }
    assert batch_template["decision_overrides_template_columns"] == [
        "path",
        "owner_decision",
        "external_archive_reference",
        "evidence_reference",
    ]
    assert batch_template["owner_decision_submission_options"] == {
        "accepted_submission_formats": ["json", "csv"],
        "canonical_owner_decisions_path": (
            "implementation/phase1/release_evidence/productization/"
            "structural_scope_owner_decisions.json"
        ),
        "template_csv_path": (
            "implementation/phase1/release_evidence/productization/"
            "structural_scope_owner_decisions.next_batch.template.csv"
        ),
        "filled_json_placeholder": "<filled-next-batch-owner-decisions.json>",
        "filled_csv_placeholder": "<filled-next-batch-owner-decisions.csv>",
        "filled_markdown_placeholder": "<filled-next-batch-owner-decisions.md>",
        "candidate_owner_decisions_placeholder": "<candidate-owner-decisions.json>",
        "candidate_merge_report_placeholder": "<candidate-owner-decisions.md>",
        "fill_release_surface_owner_decisions_command": (
            "python3 scripts/fill_structural_scope_release_surface_owner_decisions.py "
            "--template implementation/phase1/release_evidence/productization/"
            "structural_scope_owner_decisions.next_batch.template.csv "
            "--out <filled-next-batch-owner-decisions.json> "
            "--out-md <filled-next-batch-owner-decisions.md> "
            "--out-csv <filled-next-batch-owner-decisions.csv> "
            "--decision recommended_primary "
            "--owner-identity <owner-identity> "
            "--owner-role <owner-role> "
            "--decision-timestamp-utc <decision-timestamp-utc> "
            "--evidence-reference <owner-evidence-reference> "
            "--external-archive-reference <external-archive-reference-for-extract-decisions> "
            "--fail-blocked"
        ),
        "fill_release_surface_owner_decisions_with_overrides_command": (
            "python3 scripts/fill_structural_scope_release_surface_owner_decisions.py "
            "--template implementation/phase1/release_evidence/productization/"
            "structural_scope_owner_decisions.next_batch.template.csv "
            "--decision-overrides <release-surface-decision-overrides.csv> "
            "--out <filled-next-batch-owner-decisions.json> "
            "--out-md <filled-next-batch-owner-decisions.md> "
            "--out-csv <filled-next-batch-owner-decisions.csv> "
            "--decision recommended_primary "
            "--owner-identity <owner-identity> "
            "--owner-role <owner-role> "
            "--decision-timestamp-utc <decision-timestamp-utc> "
            "--evidence-reference <owner-evidence-reference> "
            "--external-archive-reference <fallback-external-archive-reference-for-extract-decisions> "
            "--fail-blocked"
        ),
        "fill_owner_decisions_from_template_command": (
            "python3 scripts/fill_structural_scope_owner_decisions_from_template.py "
            "--template implementation/phase1/release_evidence/productization/"
            "structural_scope_owner_decisions.next_batch.template.csv "
            "--out <filled-next-batch-owner-decisions.json> "
            "--out-md <filled-next-batch-owner-decisions.md> "
            "--out-csv <filled-next-batch-owner-decisions.csv> "
            "--decision recommended_primary "
            "--owner-identity <owner-identity> "
            "--owner-role <owner-role> "
            "--decision-timestamp-utc <decision-timestamp-utc> "
            "--evidence-reference <owner-evidence-reference> "
            "--external-archive-reference <external-archive-reference-for-extract-decisions> "
            "--fail-blocked"
        ),
        "fill_owner_decisions_from_template_with_overrides_command": (
            "python3 scripts/fill_structural_scope_owner_decisions_from_template.py "
            "--template implementation/phase1/release_evidence/productization/"
            "structural_scope_owner_decisions.next_batch.template.csv "
            "--decision-overrides <owner-decision-overrides.csv> "
            "--out <filled-next-batch-owner-decisions.json> "
            "--out-md <filled-next-batch-owner-decisions.md> "
            "--out-csv <filled-next-batch-owner-decisions.csv> "
            "--decision recommended_primary "
            "--owner-identity <owner-identity> "
            "--owner-role <owner-role> "
            "--decision-timestamp-utc <decision-timestamp-utc> "
            "--evidence-reference <owner-evidence-reference> "
            "--external-archive-reference <fallback-external-archive-reference-for-extract-decisions> "
            "--fail-blocked"
        ),
        "validate_canonical_owner_decisions_command": (
            "python3 scripts/build_structural_scope_owner_decision_application_plan.py "
            "--fail-release-surface-first-blocked"
        ),
        "validate_filled_json_command": (
            "python3 scripts/build_structural_scope_owner_decision_application_plan.py "
            "--owner-decisions <filled-next-batch-owner-decisions.json> "
            "--fail-release-surface-first-blocked"
        ),
        "validate_filled_csv_command": (
            "python3 scripts/build_structural_scope_owner_decision_application_plan.py "
            "--owner-decisions <filled-next-batch-owner-decisions.csv> "
            "--fail-release-surface-first-blocked"
        ),
        "merge_filled_json_to_candidate_command": (
            "python3 scripts/merge_structural_scope_owner_decision_batch.py "
            "--batch-owner-decisions <filled-next-batch-owner-decisions.json> "
            "--out <candidate-owner-decisions.json> "
            "--out-md <candidate-owner-decisions.md>"
        ),
        "merge_filled_csv_to_candidate_command": (
            "python3 scripts/merge_structural_scope_owner_decision_batch.py "
            "--batch-owner-decisions <filled-next-batch-owner-decisions.csv> "
            "--out <candidate-owner-decisions.json> "
            "--out-md <candidate-owner-decisions.md>"
        ),
        "merge_and_validate_filled_json_command": (
            "python3 scripts/merge_structural_scope_owner_decision_batch.py "
            "--batch-owner-decisions <filled-next-batch-owner-decisions.json> "
            "--out <candidate-owner-decisions.json> "
            "--out-md <candidate-owner-decisions.md> "
            "--fail-release-surface-first-blocked"
        ),
        "merge_and_validate_filled_csv_command": (
            "python3 scripts/merge_structural_scope_owner_decision_batch.py "
            "--batch-owner-decisions <filled-next-batch-owner-decisions.csv> "
            "--out <candidate-owner-decisions.json> "
            "--out-md <candidate-owner-decisions.md> "
            "--fail-release-surface-first-blocked"
        ),
        "validate_merged_candidate_command": (
            "python3 scripts/build_structural_scope_owner_decision_application_plan.py "
            "--owner-decisions <candidate-owner-decisions.json> "
            "--fail-release-surface-first-blocked"
        ),
        "claim_boundary": (
            "A filled JSON/CSV can validate a scoped owner-review batch, but final "
            "closure still requires recorded owner evidence, manual cleanup where "
            "applicable, and refreshed structural scope receipts."
        ),
    }
    assert batch_template["conditional_required_fields"] == [
        "external_archive_reference when owner_decision=extract_to_molecular_or_science_repository"
    ]
    assert (
        "signed_owner_exception_reference when owner_decision=retain_quarantined_with_signed_owner_exception"
        not in batch_template["conditional_required_fields"]
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
            "origin_wave": "pocketmd_productization_evidence_wave",
            "first_added_commit_sha": "01e6fe1b00000000000000000000000000000000",
            "first_added_commit_short_sha": "01e6fe1b",
            "first_added_commit_date": "2026-06-30",
            "first_added_commit_subject": (
                "Materialize PocketMD Lite product surface"
            ),
            "allowed_owner_decisions": list(
                application_plan.owner_review.RELEASE_SURFACE_ALLOWED_OWNER_DECISIONS
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
            "release_surface_first_batch_application_ready=true for this batch",
            "human confirms the batch cleanup scope",
        ],
    }
    assert batch_template["post_batch_verification"][0] == (
        "python3 scripts/build_structural_scope_owner_decision_application_plan.py "
        "--fail-release-surface-first-blocked"
    )
    csv_rows = list(
        csv.DictReader(
            application_plan._csv_text(batch_template["decision_rows"]).splitlines()
        )
    )
    assert csv_rows[0]["allowed_owner_decisions"] == ";".join(
        application_plan.owner_review.RELEASE_SURFACE_ALLOWED_OWNER_DECISIONS
    )
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
    assert payload["cleanup_application_preflight"]["status"] == (
        "ready_for_manual_cleanup_application"
    )
    assert payload["cleanup_application_preflight_ready"] is True
    assert payload["cleanup_application_preflight"]["destructive_commands_enabled"] is False
    assert payload["cleanup_application_preflight"]["safe_to_auto_apply"] is False
    assert payload["cleanup_application_preflight"]["cleanup_path_count"] == 2
    assert payload["cleanup_application_preflight"]["blockers"] == []
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
    extract_manifest = manifest["extract_to_molecular_or_science_repository"]
    assert extract_manifest["external_archive_reference_count"] == 1
    assert extract_manifest["missing_external_archive_reference_count"] == 0
    assert extract_manifest["missing_external_archive_reference_paths"] == []
    assert extract_manifest["archive_reference_rows"] == [
        {
            "path": "implementation/phase1/md3bead_soa.py",
            "external_archive_reference": "archive://molecular-scope/001",
        }
    ]
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


def test_application_plan_intake_rejects_release_surface_retain_exception(
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
                release_surface_path,
                "retain_quarantined_with_signed_owner_exception",
            ),
        ),
    )

    payload = application_plan.build_application_plan(
        repo_root=tmp_path,
        audit_path=audit_path,
        quarantine_manifest_path=manifest_path,
        owner_decisions_path=decisions,
    )

    assert payload["status"] == "owner_decision_evidence_invalid"
    intake = payload["release_surface_first_batch_decision_intake"]
    assert intake["status"] == "invalid_owner_decisions"
    assert intake["ready_for_manual_cleanup_application"] is False
    assert intake["expected_path_count"] == 1
    assert intake["submitted_decision_count"] == 1
    assert intake["valid_decision_count"] == 0
    assert intake["valid_cleanup_decision_count"] == 0
    assert intake["pending_decision_count"] == 0
    assert intake["invalid_submitted_decision_count"] == 1
    assert intake["invalid_submitted_decision_paths"] == [release_surface_path]
    assert intake["retain_exception_count"] == 1
    assert intake["blockers"] == [
        "invalid_release_surface_owner_decision_count=1",
        "release_surface_retain_exception_count=1",
        "release_surface_cleanup_decision_count_below_expected=0/1",
    ]
    assert "release_surface_retain_exception_not_allowed" in intake[
        "decision_rows"
    ][0]["owner_decision_missing_requirements"]
    assert payload["release_surface_first_batch_ready"] is False
    assert payload["release_surface_first_batch_blockers"] == intake["blockers"]


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


def test_cleanup_application_preflight_blocks_unsafe_paths() -> None:
    preflight = application_plan._cleanup_application_preflight(
        [
            {
                "path": "../outside.py",
                "path_area": "release_surface",
                "owner_decision": "delete_from_structural_repository",
            },
            {
                "path": ".git/config",
                "path_area": "script",
                "owner_decision": "extract_to_molecular_or_science_repository",
                "external_archive_reference": "archive://molecular-scope/git-config",
            },
        ]
    )

    assert preflight["status"] == "blocked_cleanup_application"
    assert preflight["ready"] is False
    assert preflight["destructive_commands_enabled"] is False
    assert preflight["safe_to_auto_apply"] is False
    assert preflight["unsafe_cleanup_path_count"] == 2
    assert preflight["blockers"] == ["unsafe_cleanup_path_count=2"]
    reasons = {
        row["path"]: tuple(row["unsafe_reasons"])
        for row in preflight["unsafe_cleanup_path_rows"]
    }
    assert reasons["../outside.py"] == ("parent_traversal",)
    assert reasons[".git/config"] == ("git_metadata_path",)


def test_cleanup_application_preflight_blocks_extract_without_archive_reference() -> None:
    preflight = application_plan._cleanup_application_preflight(
        [
            {
                "path": "implementation/phase1/md3bead_soa.py",
                "path_area": "implementation_phase1",
                "owner_decision": "extract_to_molecular_or_science_repository",
                "external_archive_reference": "",
            },
        ]
    )

    assert preflight["status"] == "blocked_cleanup_application"
    assert preflight["ready"] is False
    assert preflight["extract_archive_reference_missing_count"] == 1
    assert preflight["blockers"] == ["extract_archive_reference_missing_count=1"]
    assert preflight["extract_archive_reference_missing_rows"] == [
        {
            "path": "implementation/phase1/md3bead_soa.py",
            "path_area": "implementation_phase1",
            "owner_decision": "extract_to_molecular_or_science_repository",
            "external_archive_reference": "",
            "safe_path": True,
            "unsafe_reasons": [],
        }
    ]


def test_cleanup_application_preflight_blocks_untracked_or_missing_targets(
    tmp_path: Path,
) -> None:
    _init_git_repo(tmp_path)
    tracked_path = "implementation/phase1/tracked_md3bead_soa.py"
    untracked_path = "implementation/phase1/untracked_md3bead_soa.py"
    missing_path = "implementation/phase1/missing_md3bead_soa.py"
    (tmp_path / tracked_path).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / tracked_path).write_text("tracked cleanup target\n", encoding="utf-8")
    (tmp_path / untracked_path).write_text("untracked cleanup target\n", encoding="utf-8")
    subprocess.check_call(["git", "add", tracked_path], cwd=tmp_path)

    preflight = application_plan._cleanup_application_preflight(
        [
            {
                "path": tracked_path,
                "path_area": "implementation_phase1",
                "owner_decision": "delete_from_structural_repository",
            },
            {
                "path": untracked_path,
                "path_area": "implementation_phase1",
                "owner_decision": "delete_from_structural_repository",
            },
            {
                "path": missing_path,
                "path_area": "implementation_phase1",
                "owner_decision": "delete_from_structural_repository",
            },
        ],
        repo_root=tmp_path,
    )

    assert preflight["status"] == "blocked_cleanup_application"
    assert preflight["ready"] is False
    assert preflight["repo_state_checked"] is True
    assert preflight["cleanup_path_not_tracked_count"] == 2
    assert preflight["cleanup_path_missing_count"] == 1
    assert preflight["blockers"] == [
        "cleanup_path_not_tracked_count=2",
        "cleanup_path_missing_count=1",
    ]
    rows = {row["path"]: row for row in preflight["repo_state_rows"]}
    assert rows[tracked_path] == {
        "path": tracked_path,
        "path_exists": True,
        "git_tracked": True,
        "cleanup_target_available": True,
    }
    assert rows[untracked_path] == {
        "path": untracked_path,
        "path_exists": True,
        "git_tracked": False,
        "cleanup_target_available": False,
    }
    assert rows[missing_path] == {
        "path": missing_path,
        "path_exists": False,
        "git_tracked": False,
        "cleanup_target_available": False,
    }


def test_application_plan_surfaces_partial_release_surface_cleanup_batch(
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
            (release_surface_path, "delete_from_structural_repository"),
        ),
    )

    payload = application_plan.build_application_plan(
        repo_root=tmp_path,
        audit_path=audit_path,
        quarantine_manifest_path=manifest_path,
        owner_decisions_path=decisions,
    )

    assert payload["status"] == "pending_owner_decisions"
    assert payload["application_ready"] is False
    assert payload["partial_cleanup_ready"] is True
    assert payload["release_surface_batch_cleanup_ready"] is True
    intake = payload["release_surface_first_batch_decision_intake"]
    assert intake["status"] == "ready_for_manual_cleanup_application"
    assert intake["ready_for_manual_cleanup_application"] is True
    assert intake["expected_path_count"] == 1
    assert intake["submitted_decision_count"] == 1
    assert intake["valid_decision_count"] == 1
    assert intake["valid_cleanup_decision_count"] == 1
    assert intake["pending_decision_count"] == 0
    assert intake["invalid_submitted_decision_count"] == 0
    assert intake["delete_decision_count"] == 1
    assert intake["extract_decision_count"] == 0
    assert intake["blockers"] == []
    assert payload["release_surface_first_batch_ready"] is True
    assert payload["release_surface_first_batch_blockers"] == []
    assert payload["release_surface_first_batch_application_ready"] is True
    assert payload["release_surface_first_batch_application_blockers"] == []
    assert payload["release_surface_first_batch_cleanup_application_preflight"][
        "status"
    ] == "ready_for_manual_cleanup_application"
    assert payload["release_surface_first_batch_cleanup_application_preflight"][
        "cleanup_path_count"
    ] == 1
    operator_sequence = payload["release_surface_first_operator_sequence"]
    assert operator_sequence["status"] == "ready_for_manual_cleanup_application"
    assert operator_sequence["current_step_id"] == "manual_cleanup_application"
    assert operator_sequence["ready_for_manual_cleanup_application"] is True
    assert operator_sequence["blockers"] == []
    sequence_steps = {
        step["step_id"]: step for step in operator_sequence["steps"]
    }
    assert sequence_steps["fill_release_surface_first_owner_decisions"][
        "status"
    ] == "complete"
    assert sequence_steps["manual_cleanup_preflight"]["runnable_now"] is True
    assert sequence_steps["manual_cleanup_application"]["runnable_now"] is True
    release_template = payload["release_surface_first_batch_decision_template"]
    assert release_template["expected_path_count"] == 1
    assert release_template["decision_pending_count"] == 0
    assert release_template["current_intake_status"] == (
        "ready_for_manual_cleanup_application"
    )
    assert release_template["decision_rows"][0]["path"] == release_surface_path
    assert payload["cleanup_application_preflight"]["status"] == (
        "ready_for_manual_cleanup_application"
    )
    assert payload["cleanup_application_preflight"]["release_surface_policy_violation_count"] == 0
    assert payload["owner_decision_pending_count"] == 2
    assert payload["post_decision_cleanup_pending_count"] == 1
    assert payload["cleanup_required_count"] == 1
    assert payload["release_surface_cleanup_required_count"] == 1
    assert payload["next_cleanup_application_batch"]["batch_id"] == (
        "release_surface_cleanup"
    )
    assert payload["next_cleanup_application_batch"]["paths"] == [
        release_surface_path
    ]
    assert payload["next_cleanup_application_batch"]["delete_git_rm_args"] == [
        "git",
        "rm",
        "--",
        release_surface_path,
    ]
    assert payload["next_cleanup_application_batch"]["extract_paths"] == []
    assert payload["cleanup_priority_batches"] == [
        payload["next_cleanup_application_batch"]
    ]


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


def test_application_plan_accepts_mixed_release_surface_delete_extract_batch(
    tmp_path: Path,
) -> None:
    _init_git_repo(tmp_path)
    release_surface_rows = [
        (
            "implementation/phase1/release_evidence/surface/"
            "gpcr_hard_decoy_evidence_surface.json",
            "molecular_docking",
            "gpcr",
            "delete_from_structural_repository",
        ),
        (
            "implementation/phase1/release_evidence/surface/"
            "h_bond_backmap_evidence_surface.json",
            "molecular_science_evidence",
            "h_bond",
            "extract_to_molecular_or_science_repository",
        ),
        (
            "implementation/phase1/release_evidence/surface/"
            "pocketmd_lite_science_product_surface.json",
            "molecular_dynamics",
            "pocketmd",
            "extract_to_molecular_or_science_repository",
        ),
    ]
    release_surface_paths = [row[0] for row in release_surface_rows]
    for release_surface_path in release_surface_paths:
        target = tmp_path / release_surface_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}\n", encoding="utf-8")
    subprocess.check_call(
        ["git", "add", "--", *release_surface_paths],
        cwd=tmp_path,
        stdout=subprocess.DEVNULL,
    )

    audit_path = tmp_path / "audit.json"
    manifest_path = tmp_path / "manifest.json"
    decisions_path = tmp_path / "owner_decisions.json"
    _write_json(
        audit_path,
        {
            "schema_version": "structural-scope-contamination-audit.v1",
            "status": "quarantined",
            "contract_pass": True,
            "blockers": [],
            "quarantined_non_structural_rows": [
                {
                    "path": path,
                    "git_state": "tracked",
                    "path_area": "release_surface",
                    "families": [family],
                    "matched_tokens": [token],
                    "quarantine_status": "quarantined",
                    "excluded_from_structural_release_surface": True,
                }
                for path, family, token, _decision in release_surface_rows
            ],
            "unquarantined_non_structural_rows": [],
        },
    )
    _write_json(
        manifest_path,
        {
            "schema_version": "structural-scope-quarantine-manifest.v1",
            "status": "active",
            "paths": [
                {
                    "path": path,
                    "excluded_from_structural_release_surface": True,
                }
                for path in release_surface_paths
            ],
        },
    )
    _write_json(
        decisions_path,
        _decision_payload(
            *[(path, decision) for path, _family, _token, decision in release_surface_rows]
        ),
    )

    payload = application_plan.build_application_plan(
        repo_root=tmp_path,
        audit_path=audit_path,
        quarantine_manifest_path=manifest_path,
        owner_decisions_path=decisions_path,
    )

    assert payload["status"] == "ready_for_cleanup_application"
    assert payload["owner_decision_validation_pass"] is True
    assert payload["owner_decision_pending_count"] == 0
    assert payload["cleanup_required_count"] == 3
    assert payload["release_surface_cleanup_required_count"] == 3
    intake = payload["release_surface_first_batch_decision_intake"]
    assert intake["ready_for_manual_cleanup_application"] is True
    assert intake["expected_path_count"] == 3
    assert intake["submitted_decision_count"] == 3
    assert intake["delete_decision_count"] == 1
    assert intake["extract_decision_count"] == 2
    assert intake["blockers"] == []
    assert payload["release_surface_first_batch_application_ready"] is True
    assert payload["release_surface_first_batch_application_blockers"] == []

    release_preflight = payload[
        "release_surface_first_batch_cleanup_application_preflight"
    ]
    assert release_preflight["ready"] is True
    assert release_preflight["repo_state_checked"] is True
    assert release_preflight["cleanup_path_count"] == 3
    assert release_preflight["delete_path_count"] == 1
    assert release_preflight["extract_path_count"] == 2
    assert release_preflight["cleanup_path_not_tracked_count"] == 0
    assert release_preflight["cleanup_path_missing_count"] == 0
    assert all(
        row["cleanup_target_available"]
        for row in release_preflight["repo_state_rows"]
    )

    manifest = payload["cleanup_command_manifest"]
    assert manifest["release_surface_first_paths"] == release_surface_paths
    assert manifest["delete_from_structural_repository"]["paths"] == [
        release_surface_paths[0]
    ]
    extract_manifest = manifest["extract_to_molecular_or_science_repository"]
    assert extract_manifest["paths"] == release_surface_paths[1:]
    assert extract_manifest["external_archive_reference_count"] == 2
    assert extract_manifest["missing_external_archive_reference_count"] == 0
    assert extract_manifest["missing_external_archive_reference_paths"] == []
    assert extract_manifest["archive_reference_rows"] == [
        {
            "path": release_surface_paths[1],
            "external_archive_reference": "archive://molecular-scope/002",
        },
        {
            "path": release_surface_paths[2],
            "external_archive_reference": "archive://molecular-scope/003",
        },
    ]
    assert payload["next_cleanup_application_batch"]["batch_id"] == (
        "release_surface_cleanup"
    )
    assert payload["next_cleanup_application_batch"]["delete_paths"] == [
        release_surface_paths[0]
    ]
    assert payload["next_cleanup_application_batch"]["extract_paths"] == (
        release_surface_paths[1:]
    )


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
    next_template = tmp_path / "next_batch.template.json"
    next_template_md = tmp_path / "next_batch.template.md"
    next_template_csv = tmp_path / "next_batch.template.csv"
    next_overrides_template_csv = tmp_path / "next_batch.overrides.csv"
    next_overrides_template_md = tmp_path / "next_batch.overrides.md"

    payload = application_plan.write_application_plan(
        repo_root=tmp_path,
        audit_path=audit,
        quarantine_manifest_path=manifest,
        owner_decisions_path=tmp_path / "missing_decisions.json",
        out=out,
        out_md=out_md,
        next_batch_template_out=next_template,
        next_batch_template_out_md=next_template_md,
        next_batch_template_out_csv=next_template_csv,
        next_batch_decision_overrides_template_out_csv=next_overrides_template_csv,
        next_batch_decision_overrides_template_out_md=next_overrides_template_md,
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
    assert "Release Surface First Batch Intake" in markdown
    assert "Cleanup Command Manifest" in markdown
    assert "external_archive_reference_count" in markdown
    assert "missing_external_archive_reference_count" in markdown
    assert "extract_archive_reference_missing_count" in markdown
    assert "owner_decision_pending_count=2" in markdown
    next_payload = json.loads(next_template.read_text(encoding="utf-8"))
    assert next_payload["batch_id"] == "productization_evidence_second"
    assert next_payload["decision_pending_count"] == 1
    assert next_payload["decision_rows"][0]["path"] == (
        "implementation/phase1/release_evidence/productization/"
        "gpcr_hard_decoy_product_report.json"
    )
    assert "# Structural Scope Next Batch Owner Decision Template" in (
        next_template_md.read_text(encoding="utf-8")
    )
    assert "owner_decision" in next_template_csv.read_text(encoding="utf-8")
    override_rows = list(
        csv.DictReader(
            next_overrides_template_csv.read_text(encoding="utf-8").splitlines()
        )
    )
    assert list(override_rows[0]) == [
        "path",
        "owner_decision",
        "external_archive_reference",
        "signed_owner_exception_reference",
        "evidence_reference",
    ]
    assert override_rows == [
        {
            "path": (
                "implementation/phase1/release_evidence/productization/"
                "gpcr_hard_decoy_product_report.json"
            ),
            "owner_decision": "",
            "external_archive_reference": "",
            "signed_owner_exception_reference": "",
            "evidence_reference": "",
        }
    ]
    next_overrides_markdown = next_overrides_template_md.read_text(encoding="utf-8")
    assert "Next Batch Decision Overrides Template" in next_overrides_markdown
    assert "Blank rows intentionally block validation" in next_overrides_markdown
    assert "retain_quarantined_with_signed_owner_exception" in next_overrides_markdown


def test_application_plan_check_detects_stale_main_plan(
    tmp_path: Path,
    capsys,
) -> None:
    audit, manifest = _write_inputs(tmp_path)
    out = tmp_path / "plan.json"
    out_md = tmp_path / "plan.md"
    next_template = tmp_path / "next_batch.template.json"
    next_template_md = tmp_path / "next_batch.template.md"
    next_template_csv = tmp_path / "next_batch.template.csv"
    next_overrides_template_csv = tmp_path / "next_batch.overrides.csv"
    next_overrides_template_md = tmp_path / "next_batch.overrides.md"
    check_args = [
        "--repo-root",
        str(tmp_path),
        "--audit",
        str(audit),
        "--quarantine-manifest",
        str(manifest),
        "--owner-decisions",
        str(tmp_path / "missing_decisions.json"),
        "--out",
        str(out),
        "--out-md",
        str(out_md),
        "--next-batch-template-out",
        str(next_template),
        "--next-batch-template-out-md",
        str(next_template_md),
        "--next-batch-template-out-csv",
        str(next_template_csv),
        "--next-batch-decision-overrides-template-out-csv",
        str(next_overrides_template_csv),
        "--next-batch-decision-overrides-template-out-md",
        str(next_overrides_template_md),
        "--check",
    ]
    application_plan.write_application_plan(
        repo_root=tmp_path,
        audit_path=audit,
        quarantine_manifest_path=manifest,
        owner_decisions_path=tmp_path / "missing_decisions.json",
        out=out,
        out_md=out_md,
        next_batch_template_out=next_template,
        next_batch_template_out_md=next_template_md,
        next_batch_template_out_csv=next_template_csv,
        next_batch_decision_overrides_template_out_csv=next_overrides_template_csv,
        next_batch_decision_overrides_template_out_md=next_overrides_template_md,
    )

    assert application_plan.main(check_args) == 0
    output = capsys.readouterr()
    assert "structural_scope_owner_decision_application_plan_consistent" in output.out

    stale_payload = json.loads(out.read_text(encoding="utf-8"))
    stale_payload["owner_decision_pending_count"] = 99
    _write_json(out, stale_payload)

    assert application_plan.main(check_args) == 1
    output = capsys.readouterr()
    assert "structural_scope_owner_decision_application_plan_mismatch" in output.err
    assert "mismatch:" in output.err


def test_application_plan_check_detects_stale_release_surface_template(
    tmp_path: Path,
    capsys,
) -> None:
    audit, manifest, origin_report, _release_surface_path = (
        _write_release_surface_inputs(tmp_path)
    )
    out = tmp_path / "plan.json"
    out_md = tmp_path / "plan.md"
    next_template = tmp_path / "next_batch.template.json"
    next_template_md = tmp_path / "next_batch.template.md"
    next_template_csv = tmp_path / "next_batch.template.csv"
    next_overrides_template_csv = tmp_path / "next_batch.overrides.csv"
    next_overrides_template_md = tmp_path / "next_batch.overrides.md"
    release_template = tmp_path / "release_surface_first.template.json"
    release_template_md = tmp_path / "release_surface_first.template.md"
    release_template_csv = tmp_path / "release_surface_first.template.csv"
    release_overrides_template_csv = tmp_path / "release_surface_first.overrides.csv"
    release_overrides_template_md = tmp_path / "release_surface_first.overrides.md"
    check_args = [
        "--repo-root",
        str(tmp_path),
        "--audit",
        str(audit),
        "--quarantine-manifest",
        str(manifest),
        "--origin-report",
        str(origin_report),
        "--owner-decisions",
        str(tmp_path / "missing_decisions.json"),
        "--out",
        str(out),
        "--out-md",
        str(out_md),
        "--next-batch-template-out",
        str(next_template),
        "--next-batch-template-out-md",
        str(next_template_md),
        "--next-batch-template-out-csv",
        str(next_template_csv),
        "--next-batch-decision-overrides-template-out-csv",
        str(next_overrides_template_csv),
        "--next-batch-decision-overrides-template-out-md",
        str(next_overrides_template_md),
        "--release-surface-first-batch-template-out",
        str(release_template),
        "--release-surface-first-batch-template-out-md",
        str(release_template_md),
        "--release-surface-first-batch-template-out-csv",
        str(release_template_csv),
        "--release-surface-first-decision-overrides-template-out-csv",
        str(release_overrides_template_csv),
        "--release-surface-first-decision-overrides-template-out-md",
        str(release_overrides_template_md),
        "--check",
    ]
    application_plan.write_application_plan(
        repo_root=tmp_path,
        audit_path=audit,
        quarantine_manifest_path=manifest,
        owner_decisions_path=tmp_path / "missing_decisions.json",
        origin_report_path=origin_report,
        out=out,
        out_md=out_md,
        next_batch_template_out=next_template,
        next_batch_template_out_md=next_template_md,
        next_batch_template_out_csv=next_template_csv,
        next_batch_decision_overrides_template_out_csv=next_overrides_template_csv,
        next_batch_decision_overrides_template_out_md=next_overrides_template_md,
        release_surface_first_batch_template_out=release_template,
        release_surface_first_batch_template_out_md=release_template_md,
        release_surface_first_batch_template_out_csv=release_template_csv,
        release_surface_first_decision_overrides_template_out_csv=(
            release_overrides_template_csv
        ),
        release_surface_first_decision_overrides_template_out_md=(
            release_overrides_template_md
        ),
    )

    assert application_plan.main(check_args) == 0
    output = capsys.readouterr()
    assert "structural_scope_owner_decision_application_plan_consistent" in output.out

    stale_template = json.loads(release_template.read_text(encoding="utf-8"))
    stale_template["decision_pending_count"] = 99
    _write_json(release_template, stale_template)

    assert application_plan.main(check_args) == 1
    output = capsys.readouterr()
    assert "structural_scope_owner_decision_application_plan_mismatch" in output.err
    assert "release_surface_first.template.json" in output.err


def test_application_plan_writes_release_surface_first_template(
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
    origin_report_path = tmp_path / "origin_report.json"
    _write_json(audit_path, audit)
    _write_json(manifest_path, manifest)
    _write_json(
        origin_report_path,
        {
            "origin_rows": [
                {
                    "path": release_surface_path,
                    "origin_wave": "pocketmd_productization_evidence_wave",
                    "first_added_commit_sha": "01e6fe1b00000000000000000000000000000000",
                    "first_added_commit_short_sha": "01e6fe1b",
                    "first_added_commit_date": "2026-06-30",
                    "first_added_commit_subject": (
                        "Materialize PocketMD Lite product surface"
                    ),
                }
            ]
        },
    )
    out = tmp_path / "plan.json"
    out_md = tmp_path / "plan.md"
    next_template = tmp_path / "next_batch.template.json"
    next_template_md = tmp_path / "next_batch.template.md"
    next_template_csv = tmp_path / "next_batch.template.csv"
    next_overrides_template_csv = tmp_path / "next_batch.overrides.csv"
    next_overrides_template_md = tmp_path / "next_batch.overrides.md"
    release_template = tmp_path / "release_surface_first.template.json"
    release_template_md = tmp_path / "release_surface_first.template.md"
    release_template_csv = tmp_path / "release_surface_first.template.csv"
    release_overrides_template_csv = tmp_path / "release_surface_first.overrides.csv"
    release_overrides_template_md = tmp_path / "release_surface_first.overrides.md"

    application_plan.write_application_plan(
        repo_root=tmp_path,
        audit_path=audit_path,
        quarantine_manifest_path=manifest_path,
        owner_decisions_path=tmp_path / "missing_decisions.json",
        origin_report_path=origin_report_path,
        out=out,
        out_md=out_md,
        next_batch_template_out=next_template,
        next_batch_template_out_md=next_template_md,
        next_batch_template_out_csv=next_template_csv,
        next_batch_decision_overrides_template_out_csv=next_overrides_template_csv,
        next_batch_decision_overrides_template_out_md=next_overrides_template_md,
        release_surface_first_batch_template_out=release_template,
        release_surface_first_batch_template_out_md=release_template_md,
        release_surface_first_batch_template_out_csv=release_template_csv,
        release_surface_first_decision_overrides_template_out_csv=(
            release_overrides_template_csv
        ),
        release_surface_first_decision_overrides_template_out_md=(
            release_overrides_template_md
        ),
    )

    template_payload = json.loads(release_template.read_text(encoding="utf-8"))
    assert template_payload["batch_id"] == "release_surface_first"
    assert template_payload["expected_path_count"] == 1
    assert template_payload["decision_pending_count"] == 1
    assert template_payload["decision_rows"][0]["path"] == release_surface_path
    assert template_payload["origin_context_complete"] is True
    assert template_payload["decision_rows"][0]["origin_wave"] == (
        "pocketmd_productization_evidence_wave"
    )
    assert template_payload["decision_rows"][0]["first_added_commit_short_sha"] == (
        "01e6fe1b"
    )
    assert template_payload["mixed_decision_overrides_template_paths"] == {
        "csv": (
            "implementation/phase1/release_evidence/productization/"
            "structural_scope_owner_decisions.release_surface_first.overrides.template.csv"
        ),
        "markdown": (
            "implementation/phase1/release_evidence/productization/"
            "structural_scope_owner_decisions.release_surface_first.overrides.template.md"
        ),
    }
    assert template_payload["mixed_decision_overrides_template_rows"] == [
        {
            "row_id": "release_surface_first-001",
            "path": release_surface_path,
            "recommended_owner_decision_primary": "delete_from_structural_repository",
            "recommended_owner_decision_alternate": (
                "extract_to_molecular_or_science_repository"
            ),
            "owner_decision": "",
            "external_archive_reference": "",
            "evidence_reference": "",
        }
    ]
    assert template_payload["primary_cleanup_preview"]["preconditions"] == [
        (
            "owner fills all release_surface_first rows in "
            "structural_scope_owner_decisions.json or CSV"
        ),
        "release_surface_first_batch_application_ready=true",
        "human confirms release-surface cleanup scope before any git rm",
    ]
    assert template_payload["post_batch_verification"][0] == (
        "python3 scripts/build_structural_scope_owner_decision_application_plan.py "
        "--fail-release-surface-first-blocked"
    )
    assert template_payload["owner_decision_submission_options"][
        "validate_filled_csv_command"
    ] == (
        "python3 scripts/build_structural_scope_owner_decision_application_plan.py "
        "--owner-decisions <filled-release-surface-first-owner-decisions.csv> "
        "--fail-release-surface-first-blocked"
    )
    assert template_payload["owner_decision_submission_options"][
        "merge_and_validate_filled_csv_command"
    ] == (
        "python3 scripts/merge_structural_scope_owner_decision_batch.py "
        "--batch-owner-decisions "
        "<filled-release-surface-first-owner-decisions.csv> "
        "--out <candidate-owner-decisions.json> "
        "--out-md <candidate-owner-decisions.md> "
        "--fail-release-surface-first-blocked"
    )
    next_markdown = next_template_md.read_text(encoding="utf-8")
    next_overrides_markdown = next_overrides_template_md.read_text(encoding="utf-8")
    release_markdown = release_template_md.read_text(encoding="utf-8")
    release_overrides_markdown = release_overrides_template_md.read_text(
        encoding="utf-8"
    )
    assert "Release Surface First Batch" in release_markdown
    assert "pocketmd_productization_evidence_wave" in release_markdown
    assert "01e6fe1b 2026-06-30" in release_markdown
    assert "merge_and_validate_filled_csv_command" in release_markdown
    assert "Mixed Decision Overrides Template" in release_markdown
    assert "Release Surface Mixed Decision Overrides Template" in (
        release_overrides_markdown
    )
    assert "Blank rows intentionally block validation" in release_overrides_markdown
    assert "Blank rows intentionally block validation" in next_overrides_markdown
    assert "Next Batch Decision Overrides Template" in next_overrides_markdown
    assert (
        "`external_archive_reference`: required when `owner_decision` is "
        "`extract_to_molecular_or_science_repository`"
    ) in next_markdown
    assert "signed_owner_exception_reference when owner_decision=retain_quarantined_with_signed_owner_exception" not in (
        next_markdown
    )
    assert "signed_owner_exception_reference when owner_decision=retain_quarantined_with_signed_owner_exception" not in (
        release_markdown
    )
    assert "## Post Batch Verification" in next_markdown
    assert "## Post Batch Verification" in release_markdown
    assert "## Owner Decision Submission" in next_markdown
    assert "## Owner Decision Submission" in release_markdown
    assert "fill_release_surface_owner_decisions_command" in release_markdown
    assert (
        "fill_release_surface_owner_decisions_with_overrides_command"
        in release_markdown
    )
    assert "fill_owner_decisions_from_template_command" in release_markdown
    assert (
        "fill_owner_decisions_from_template_with_overrides_command"
        in release_markdown
    )
    assert "fill_release_surface_owner_decisions_command" in next_markdown
    assert (
        "fill_release_surface_owner_decisions_with_overrides_command"
        in next_markdown
    )
    assert "fill_owner_decisions_from_template_command" in next_markdown
    assert (
        "fill_owner_decisions_from_template_with_overrides_command"
        in next_markdown
    )
    assert "--decision-overrides <release-surface-decision-overrides.csv>" in (
        release_markdown
    )
    assert "--decision-overrides <release-surface-decision-overrides.csv>" in (
        next_markdown
    )
    assert "--decision-overrides <owner-decision-overrides.csv>" in release_markdown
    assert "--decision-overrides <owner-decision-overrides.csv>" in next_markdown
    assert (
        "--external-archive-reference <external-archive-reference-for-extract-decisions>"
        in release_markdown
    )
    assert (
        "--external-archive-reference <external-archive-reference-for-extract-decisions>"
        in next_markdown
    )
    assert "--owner-decisions <filled-next-batch-owner-decisions.csv>" in next_markdown
    assert (
        "--owner-decisions <filled-release-surface-first-owner-decisions.csv>"
        in release_markdown
    )
    assert "--fail-release-surface-first-blocked" in next_markdown
    assert "--fail-release-surface-first-blocked" in release_markdown
    next_override_rows = list(
        csv.DictReader(
            next_overrides_template_csv.read_text(encoding="utf-8").splitlines()
        )
    )
    assert list(next_override_rows[0]) == [
        "path",
        "owner_decision",
        "external_archive_reference",
        "evidence_reference",
    ]
    csv_rows = list(
        csv.DictReader(release_template_csv.read_text(encoding="utf-8").splitlines())
    )
    assert csv_rows[0]["path"] == release_surface_path
    assert csv_rows[0]["allowed_owner_decisions"] == ";".join(
        application_plan.owner_review.RELEASE_SURFACE_ALLOWED_OWNER_DECISIONS
    )
    assert csv_rows[0]["origin_wave"] == "pocketmd_productization_evidence_wave"
    assert csv_rows[0]["first_added_commit_short_sha"] == "01e6fe1b"
    override_rows = list(
        csv.DictReader(
            release_overrides_template_csv.read_text(encoding="utf-8").splitlines()
        )
    )
    assert list(override_rows[0]) == [
        "path",
        "owner_decision",
        "external_archive_reference",
        "evidence_reference",
    ]
    assert override_rows == [
        {
            "path": release_surface_path,
            "owner_decision": "",
            "external_archive_reference": "",
            "evidence_reference": "",
        }
    ]


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
    valid_markdown = (tmp_path / "valid_plan.md").read_text(encoding="utf-8")
    assert "archive://molecular-scope/001" in valid_markdown
    assert (
        "extract_to_molecular_or_science_repository.external_archive_reference_count"
        in valid_markdown
    )
    assert "| Extract Path | External Archive Reference |" in valid_markdown


def test_application_plan_fail_release_surface_first_blocked_exit_code(
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

    blocked_exit = application_plan.main(
        [
            "--repo-root",
            str(tmp_path),
            "--audit",
            str(audit_path),
            "--quarantine-manifest",
            str(manifest_path),
            "--owner-decisions",
            str(tmp_path / "missing_decisions.json"),
            "--out",
            str(tmp_path / "blocked_release_surface_plan.json"),
            "--out-md",
            str(tmp_path / "blocked_release_surface_plan.md"),
            "--fail-release-surface-first-blocked",
        ]
    )
    assert blocked_exit == 1

    decisions = tmp_path / "owner_decisions.json"
    _write_json(
        decisions,
        _decision_payload(
            (release_surface_path, "delete_from_structural_repository"),
        ),
    )
    ready_exit = application_plan.main(
        [
            "--repo-root",
            str(tmp_path),
            "--audit",
            str(audit_path),
            "--quarantine-manifest",
            str(manifest_path),
            "--owner-decisions",
            str(decisions),
            "--out",
            str(tmp_path / "ready_release_surface_plan.json"),
            "--out-md",
            str(tmp_path / "ready_release_surface_plan.md"),
            "--fail-release-surface-first-blocked",
        ]
    )
    assert ready_exit == 0
    ready_payload = json.loads(
        (tmp_path / "ready_release_surface_plan.json").read_text(encoding="utf-8")
    )
    assert ready_payload["release_surface_first_batch_application_ready"] is True
    assert ready_payload["release_surface_first_batch_application_blockers"] == []
    assert ready_payload["owner_decision_pending_count"] == 2
    assert ready_payload["owner_decision_validation_pass"] is False
