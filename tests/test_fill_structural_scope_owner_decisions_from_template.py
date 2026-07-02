from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent.parent


def _load_script(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


fill_decisions = _load_script(
    "fill_structural_scope_owner_decisions_from_template",
    ROOT / "scripts" / "fill_structural_scope_owner_decisions_from_template.py",
)
application_plan = _load_script(
    "build_structural_scope_owner_decision_application_plan_for_template_fill_test",
    ROOT / "scripts" / "build_structural_scope_owner_decision_application_plan.py",
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _scope_rows() -> list[dict]:
    return [
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
        {
            "path": "scripts/run_gpcr_hard_decoy.py",
            "git_state": "tracked",
            "path_area": "script",
            "families": ["molecular_docking"],
            "matched_tokens": ["gpcr"],
            "quarantine_status": "quarantined",
            "excluded_from_structural_release_surface": True,
        },
        {
            "path": (
                "implementation/phase1/release_evidence/productization/"
                "md3bead_operator_packet.json"
            ),
            "git_state": "tracked",
            "path_area": "productization_evidence",
            "families": ["molecular_dynamics"],
            "matched_tokens": ["md3bead"],
            "quarantine_status": "quarantined",
            "excluded_from_structural_release_surface": True,
        },
    ]


def _template_row(row: dict, index: int, primary: str) -> dict:
    alternate = (
        "delete_from_structural_repository"
        if primary == "extract_to_molecular_or_science_repository"
        else "extract_to_molecular_or_science_repository"
    )
    return {
        "row_id": f"scope-cleanup-{index:03d}",
        "path": row["path"],
        "path_area": row["path_area"],
        "families": ";".join(row["families"]),
        "matched_tokens": ";".join(row["matched_tokens"]),
        "recommended_owner_decision": f"{primary}_or_{alternate}",
        "recommended_owner_decision_primary": primary,
        "recommended_owner_decision_alternate": alternate,
        "owner_decision": "",
        "owner_identity": "",
        "owner_role": "",
        "decision_timestamp_utc": "",
        "evidence_reference": "",
        "signed_owner_exception_reference": "",
        "external_archive_reference": "",
        "allowed_owner_decisions": ";".join(
            fill_decisions.owner_review.RELEASE_SURFACE_ALLOWED_OWNER_DECISIONS
            if row["path_area"] == "release_surface"
            else fill_decisions.owner_review.ALLOWED_OWNER_DECISIONS
        ),
        "origin_wave": "test_scope_wave",
        "first_added_commit_sha": f"{index:040d}",
        "first_added_commit_short_sha": f"{index:08d}",
        "first_added_commit_date": "2026-07-03",
        "first_added_commit_subject": "seed non-structural structural-scope row",
    }


def _write_template(path: Path) -> None:
    rows = _scope_rows()
    template_rows = [
        _template_row(
            rows[0],
            1,
            "delete_from_structural_repository",
        ),
        _template_row(
            rows[1],
            2,
            "extract_to_molecular_or_science_repository",
        ),
        _template_row(
            rows[2],
            3,
            "delete_from_structural_repository",
        ),
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(fill_decisions.owner_review.OWNER_DECISION_COLUMNS),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(template_rows)


def _write_decision_overrides(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "path",
                "owner_decision",
                "external_archive_reference",
                "signed_owner_exception_reference",
                "evidence_reference",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _write_scope_inputs(tmp_path: Path) -> tuple[Path, Path]:
    rows = _scope_rows()
    audit = tmp_path / "audit.json"
    manifest = tmp_path / "manifest.json"
    _write_json(
        audit,
        {
            "schema_version": "structural-scope-contamination-audit.v1",
            "status": "quarantined",
            "contract_pass": True,
            "blockers": [],
            "quarantined_non_structural_rows": rows,
            "unquarantined_non_structural_rows": [],
        },
    )
    _write_json(
        manifest,
        {
            "schema_version": "structural-scope-quarantine-manifest.v1",
            "status": "active",
            "paths": [
                {
                    "path": row["path"],
                    "excluded_from_structural_release_surface": True,
                }
                for row in rows
            ],
        },
    )
    return audit, manifest


def test_full_template_fill_blocks_extract_without_archive_reference(
    tmp_path: Path,
) -> None:
    template = tmp_path / "structural_scope_owner_decisions.template.csv"
    _write_template(template)

    payload = fill_decisions.build_filled_decisions(
        repo_root=tmp_path,
        template_path=template,
        owner_identity="scope-owner",
        owner_role="repository_owner",
        decision_timestamp_utc="2026-07-03T00:00:00Z",
        evidence_reference="owner-review://scope-cleanup/full-template",
    )

    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["decision_row_count"] == 3
    assert payload["delete_decision_count"] == 2
    assert payload["extract_decision_count"] == 1
    assert any(
        blocker.endswith("external_archive_reference_missing_for_extract")
        for blocker in payload["blockers"]
    )


def test_full_template_fill_validates_delete_and_extract_cleanup_plan(
    tmp_path: Path,
) -> None:
    template = tmp_path / "structural_scope_owner_decisions.template.csv"
    _write_template(template)

    payload = fill_decisions.build_filled_decisions(
        repo_root=tmp_path,
        template_path=template,
        owner_identity="scope-owner",
        owner_role="repository_owner",
        decision_timestamp_utc="2026-07-03T00:00:00Z",
        evidence_reference="owner-review://scope-cleanup/full-template",
        external_archive_reference="archive://molecular-scope/owner-reviewed-export",
    )

    assert payload["status"] == "filled"
    assert payload["contract_pass"] is True
    assert payload["path_area_counts"] == {
        "productization_evidence": 1,
        "release_surface": 1,
        "script": 1,
    }
    assert payload["owner_decision_counts"] == {
        "delete_from_structural_repository": 2,
        "extract_to_molecular_or_science_repository": 1,
    }

    owner_decisions_path = tmp_path / "filled-owner-decisions.json"
    fill_decisions.write_outputs(
        payload=payload,
        repo_root=tmp_path,
        out=owner_decisions_path,
        out_md=tmp_path / "filled-owner-decisions.md",
        out_csv=tmp_path / "filled-owner-decisions.csv",
    )
    audit, manifest = _write_scope_inputs(tmp_path)
    plan = application_plan.build_application_plan(
        repo_root=tmp_path,
        audit_path=audit,
        quarantine_manifest_path=manifest,
        owner_decisions_path=owner_decisions_path,
    )

    assert plan["owner_decision_validation_pass"] is True
    assert plan["owner_decision_pending_count"] == 0
    assert plan["post_decision_cleanup_pending_count"] == 3
    assert plan["cleanup_application_preflight"]["ready"] is True
    assert plan["release_surface_first_batch_application_ready"] is True
    assert plan["cleanup_command_manifest"]["delete_from_structural_repository"][
        "path_count"
    ] == 2
    assert plan["cleanup_command_manifest"][
        "extract_to_molecular_or_science_repository"
    ]["path_count"] == 1
    assert plan["cleanup_command_manifest"]["manual_application_required"] is True


def test_full_template_fill_mixed_decision_overrides_validate_cleanup_plan(
    tmp_path: Path,
) -> None:
    template = tmp_path / "structural_scope_owner_decisions.template.csv"
    overrides = tmp_path / "structural_scope_owner_decisions.overrides.csv"
    _write_template(template)
    scope_rows = _scope_rows()
    _write_decision_overrides(
        overrides,
        [
            {
                "path": scope_rows[0]["path"],
                "owner_decision": "delete_from_structural_repository",
                "external_archive_reference": "",
                "signed_owner_exception_reference": "",
                "evidence_reference": "",
            },
            {
                "path": scope_rows[1]["path"],
                "owner_decision": "extract_to_molecular_or_science_repository",
                "external_archive_reference": "archive://molecular-scope/gpcr",
                "signed_owner_exception_reference": "",
                "evidence_reference": "owner-review://scope-cleanup/gpcr",
            },
            {
                "path": scope_rows[2]["path"],
                "owner_decision": "retain_quarantined_with_signed_owner_exception",
                "external_archive_reference": "",
                "signed_owner_exception_reference": (
                    "signed-exception://scope-cleanup/md3bead"
                ),
                "evidence_reference": "owner-review://scope-cleanup/md3bead",
            },
        ],
    )

    payload = fill_decisions.build_filled_decisions(
        repo_root=tmp_path,
        template_path=template,
        owner_identity="scope-owner",
        owner_role="repository_owner",
        decision_timestamp_utc="2026-07-03T00:00:00Z",
        evidence_reference="owner-review://scope-cleanup/full-template",
        decision_overrides_path=overrides,
    )

    assert payload["status"] == "filled"
    assert payload["contract_pass"] is True
    assert payload["decision_override_count"] == 3
    assert payload["decision_override_paths"] == sorted(row["path"] for row in scope_rows)
    assert payload["unknown_decision_override_paths"] == []
    assert payload["missing_decision_override_paths"] == []
    assert payload["owner_decision_counts"] == {
        "delete_from_structural_repository": 1,
        "extract_to_molecular_or_science_repository": 1,
        "retain_quarantined_with_signed_owner_exception": 1,
    }
    assert all(row["override_applied"] for row in payload["row_summaries"])

    owner_decisions_path = tmp_path / "filled-owner-decisions.json"
    fill_decisions.write_outputs(
        payload=payload,
        repo_root=tmp_path,
        out=owner_decisions_path,
        out_md=tmp_path / "filled-owner-decisions.md",
        out_csv=tmp_path / "filled-owner-decisions.csv",
    )
    audit, manifest = _write_scope_inputs(tmp_path)
    plan = application_plan.build_application_plan(
        repo_root=tmp_path,
        audit_path=audit,
        quarantine_manifest_path=manifest,
        owner_decisions_path=owner_decisions_path,
    )

    assert plan["owner_decision_validation_pass"] is True
    assert plan["owner_decision_pending_count"] == 0
    assert plan["post_decision_cleanup_pending_count"] == 2
    assert plan["retain_quarantined_exception_count"] == 1
    assert plan["cleanup_command_manifest"]["delete_from_structural_repository"][
        "paths"
    ] == [scope_rows[0]["path"]]
    assert plan["cleanup_command_manifest"][
        "extract_to_molecular_or_science_repository"
    ]["archive_reference_rows"] == [
        {
            "path": scope_rows[1]["path"],
            "external_archive_reference": "archive://molecular-scope/gpcr",
        }
    ]


def test_full_template_fill_decision_overrides_require_explicit_decisions(
    tmp_path: Path,
) -> None:
    template = tmp_path / "structural_scope_owner_decisions.template.csv"
    overrides = tmp_path / "structural_scope_owner_decisions.overrides.csv"
    _write_template(template)
    scope_rows = _scope_rows()
    _write_decision_overrides(
        overrides,
        [
            {
                "path": row["path"],
                "owner_decision": "",
                "external_archive_reference": "",
                "signed_owner_exception_reference": "",
                "evidence_reference": "",
            }
            for row in scope_rows
        ],
    )

    payload = fill_decisions.build_filled_decisions(
        repo_root=tmp_path,
        template_path=template,
        owner_identity="scope-owner",
        owner_role="repository_owner",
        decision_timestamp_utc="2026-07-03T00:00:00Z",
        evidence_reference="owner-review://scope-cleanup/full-template",
        decision_overrides_path=overrides,
    )

    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["delete_decision_count"] == 0
    assert payload["extract_decision_count"] == 0
    assert payload["retain_decision_count"] == 0
    assert payload["missing_decision_override_paths"] == []
    assert all(
        row["row_blockers"] == ["decision_override_owner_decision_missing"]
        for row in payload["row_summaries"]
    )
    assert {
        blocker.rsplit("::", 1)[-1] for blocker in payload["blockers"]
    } == {"decision_override_owner_decision_missing"}
