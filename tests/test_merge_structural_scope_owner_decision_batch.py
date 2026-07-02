from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path
import sys


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "merge_structural_scope_owner_decision_batch.py"
)
SPEC = importlib.util.spec_from_file_location(
    "merge_structural_scope_owner_decision_batch",
    SCRIPT_PATH,
)
assert SPEC is not None
merge_tool = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = merge_tool
SPEC.loader.exec_module(merge_tool)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(merge_tool.owner_review.OWNER_DECISION_COLUMNS),
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    column: (
                        ";".join(row[column])
                        if isinstance(row.get(column), list)
                        else row.get(column, "")
                    )
                    for column in merge_tool.owner_review.OWNER_DECISION_COLUMNS
                }
            )


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
                    "implementation/phase1/release_evidence/surface/"
                    "pocketmd_lite_science_product_surface.json"
                ),
                "git_state": "tracked",
                "path_area": "release_surface",
                "families": ["molecular_dynamics"],
                "matched_tokens": ["pocketmd"],
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
                    "implementation/phase1/release_evidence/surface/"
                    "pocketmd_lite_science_product_surface.json"
                ),
                "excluded_from_structural_release_surface": True,
            },
        ],
    }


def _base_decisions_payload() -> dict:
    return {
        "schema_version": merge_tool.owner_review.DECISION_SCHEMA_VERSION,
        "decision_rows": [
            {
                "path": "implementation/phase1/md3bead_soa.py",
                "owner_decision": "retain_quarantined_with_signed_owner_exception",
                "owner_identity": "scope-owner",
                "owner_role": "product_owner",
                "decision_timestamp_utc": "2026-07-02T00:00:00Z",
                "evidence_reference": "owner-review://scope-cleanup/001",
                "signed_owner_exception_reference": (
                    "signed-exception://scope-cleanup/md3bead"
                ),
                "external_archive_reference": "",
            }
        ],
    }


def _release_surface_decision_row(decision: str) -> dict:
    return {
        "row_id": "release_surface_first-001",
        "path": (
            "implementation/phase1/release_evidence/surface/"
            "pocketmd_lite_science_product_surface.json"
        ),
        "path_area": "release_surface",
        "families": ["molecular_dynamics"],
        "matched_tokens": ["pocketmd"],
        "recommended_owner_decision": (
            "delete_from_structural_repository_or_extract_only_if_owner_requires_history"
        ),
        "recommended_owner_decision_primary": "delete_from_structural_repository",
        "recommended_owner_decision_alternate": (
            "extract_to_molecular_or_science_repository"
        ),
        "owner_decision": decision,
        "owner_identity": "scope-owner",
        "owner_role": "product_owner",
        "decision_timestamp_utc": "2026-07-02T00:00:00Z",
        "evidence_reference": "owner-review://scope-cleanup/release-surface-001",
        "signed_owner_exception_reference": (
            "signed-exception://scope-cleanup/release-surface-001"
        ),
        "external_archive_reference": "",
        "allowed_owner_decisions": list(
            merge_tool.owner_review.RELEASE_SURFACE_ALLOWED_OWNER_DECISIONS
        ),
    }


def _write_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    audit = tmp_path / "audit.json"
    manifest = tmp_path / "manifest.json"
    base = tmp_path / "owner_decisions.json"
    _write_json(audit, _audit_payload())
    _write_json(manifest, _manifest_payload())
    _write_json(base, _base_decisions_payload())
    return audit, manifest, base


def test_batch_merge_builds_candidate_and_validates_release_surface_first(
    tmp_path: Path,
) -> None:
    audit, manifest, base = _write_inputs(tmp_path)
    batch = tmp_path / "release_surface_first.csv"
    candidate = tmp_path / "candidate_owner_decisions.json"
    report = tmp_path / "candidate_owner_decisions.md"
    _write_csv(
        batch,
        [_release_surface_decision_row("delete_from_structural_repository")],
    )

    payload = merge_tool.write_merge_candidate(
        repo_root=tmp_path,
        audit_path=audit,
        quarantine_manifest_path=manifest,
        base_owner_decisions_path=base,
        batch_owner_decisions_path=batch,
        out=candidate,
        out_md=report,
    )

    assert candidate.exists()
    assert report.exists()
    candidate_payload = json.loads(candidate.read_text(encoding="utf-8"))
    assert candidate_payload["schema_version"] == (
        merge_tool.owner_review.DECISION_SCHEMA_VERSION
    )
    assert candidate_payload["blockers"] == []
    assert [row["path"] for row in candidate_payload["decision_rows"]] == [
        "implementation/phase1/md3bead_soa.py",
        (
            "implementation/phase1/release_evidence/surface/"
            "pocketmd_lite_science_product_surface.json"
        ),
    ]
    report_payload = payload["merge_report"]
    assert report_payload["merge_contract_pass"] is True
    assert report_payload["base_decision_row_count"] == 1
    assert report_payload["batch_decision_row_count"] == 1
    assert report_payload["merged_decision_row_count"] == 2
    assert report_payload["appended_paths"] == [
        (
            "implementation/phase1/release_evidence/surface/"
            "pocketmd_lite_science_product_surface.json"
        )
    ]
    summary = payload["application_plan_summary"]
    assert summary["owner_decision_validation_pass"] is True
    assert summary["owner_decision_pending_count"] == 0
    assert summary["post_decision_cleanup_pending_count"] == 1
    assert summary["release_surface_first_batch_ready"] is True
    assert summary["release_surface_first_batch_application_ready"] is True
    assert payload["safe_to_auto_apply"] is False
    assert payload["destructive_commands_enabled"] is False
    assert payload["manual_cleanup_application_required"] is True


def test_batch_merge_surfaces_release_surface_retain_exception_blocker(
    tmp_path: Path,
) -> None:
    audit, manifest, base = _write_inputs(tmp_path)
    batch = tmp_path / "release_surface_first.csv"
    candidate = tmp_path / "candidate_owner_decisions.json"
    _write_csv(
        batch,
        [
            _release_surface_decision_row(
                "retain_quarantined_with_signed_owner_exception"
            )
        ],
    )

    payload = merge_tool.write_merge_candidate(
        repo_root=tmp_path,
        audit_path=audit,
        quarantine_manifest_path=manifest,
        base_owner_decisions_path=base,
        batch_owner_decisions_path=batch,
        out=candidate,
    )

    summary = payload["application_plan_summary"]
    assert payload["merge_report"]["merge_contract_pass"] is True
    assert summary["owner_decision_validation_pass"] is False
    assert summary["release_surface_first_batch_application_ready"] is False
    assert (
        "owner_decisions::owner_decisions_invalid_path_count=1"
        in summary["owner_decision_validation_blockers"]
    )
    assert (
        "release_surface_retain_exception_count=1"
        in summary["release_surface_first_batch_application_blockers"]
    )


def test_cli_returns_nonzero_when_release_surface_first_batch_is_blocked(
    tmp_path: Path,
) -> None:
    audit, manifest, base = _write_inputs(tmp_path)
    batch = tmp_path / "release_surface_first.csv"
    candidate = tmp_path / "candidate_owner_decisions.json"
    _write_csv(
        batch,
        [
            _release_surface_decision_row(
                "retain_quarantined_with_signed_owner_exception"
            )
        ],
    )

    exit_code = merge_tool.main(
        [
            "--repo-root",
            str(tmp_path),
            "--audit",
            str(audit),
            "--quarantine-manifest",
            str(manifest),
            "--base-owner-decisions",
            str(base),
            "--batch-owner-decisions",
            str(batch),
            "--out",
            str(candidate),
            "--fail-release-surface-first-blocked",
        ]
    )

    assert exit_code == 1
    assert candidate.exists()


def test_batch_merge_requires_explicit_base_overwrite(
    tmp_path: Path,
) -> None:
    audit, manifest, base = _write_inputs(tmp_path)
    batch = tmp_path / "release_surface_first.csv"
    _write_csv(
        batch,
        [_release_surface_decision_row("delete_from_structural_repository")],
    )

    try:
        merge_tool.write_merge_candidate(
            repo_root=tmp_path,
            audit_path=audit,
            quarantine_manifest_path=manifest,
            base_owner_decisions_path=base,
            batch_owner_decisions_path=batch,
            out=base,
        )
    except ValueError as exc:
        assert str(exc) == (
            "candidate_out_matches_base_owner_decisions_without_allow_overwrite_base"
        )
    else:
        raise AssertionError("expected base overwrite guard to raise")
