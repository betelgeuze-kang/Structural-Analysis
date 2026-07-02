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


fill_batch = _load_script(
    "fill_structural_scope_release_surface_owner_decisions",
    ROOT / "scripts" / "fill_structural_scope_release_surface_owner_decisions.py",
)
application_plan = _load_script(
    "build_structural_scope_owner_decision_application_plan_for_fill_test",
    ROOT / "scripts" / "build_structural_scope_owner_decision_application_plan.py",
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _release_surface_paths() -> list[str]:
    return [
        "implementation/phase1/release_evidence/surface/gpcr_hard_decoy_evidence_surface.json",
        "implementation/phase1/release_evidence/surface/h_bond_backmap_evidence_surface.json",
        "implementation/phase1/release_evidence/surface/pocketmd_lite_science_product_surface.json",
    ]


def _write_release_surface_template(path: Path) -> None:
    rows = [
        {
            "row_id": f"release_surface_first-{index + 1:03d}",
            "path": release_path,
            "path_area": "release_surface",
            "families": family,
            "matched_tokens": token,
            "recommended_owner_decision": "delete_from_structural_repository_or_extract_only_if_owner_requires_history",
            "recommended_owner_decision_primary": "delete_from_structural_repository",
            "recommended_owner_decision_alternate": "extract_to_molecular_or_science_repository",
            "owner_decision": "",
            "owner_identity": "",
            "owner_role": "",
            "decision_timestamp_utc": "",
            "evidence_reference": "",
            "signed_owner_exception_reference": "",
            "external_archive_reference": "",
            "allowed_owner_decisions": "delete_from_structural_repository;extract_to_molecular_or_science_repository",
            "origin_wave": "test_scope_seed",
            "first_added_commit_sha": "abc123",
            "first_added_commit_short_sha": "abc123",
            "first_added_commit_date": "2026-07-03",
            "first_added_commit_subject": "seed non-structural surface",
        }
        for index, (release_path, family, token) in enumerate(
            zip(
                _release_surface_paths(),
                ["molecular_docking", "molecular_science_evidence", "molecular_dynamics"],
                ["gpcr", "h_bond", "pocketmd"],
            )
        )
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(fill_batch.owner_review.OWNER_DECISION_COLUMNS),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _write_scope_inputs(tmp_path: Path) -> tuple[Path, Path]:
    rows = [
        {
            "path": path,
            "git_state": "tracked",
            "path_area": "release_surface",
            "families": [family],
            "matched_tokens": [token],
            "quarantine_status": "quarantined",
            "excluded_from_structural_release_surface": True,
        }
        for path, family, token in zip(
            _release_surface_paths(),
            ["molecular_docking", "molecular_science_evidence", "molecular_dynamics"],
            ["gpcr", "h_bond", "pocketmd"],
        )
    ]
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


def test_fill_release_surface_delete_batch_validates_for_manual_cleanup(tmp_path: Path) -> None:
    template = tmp_path / "release_surface_first.template.csv"
    _write_release_surface_template(template)
    filled = fill_batch.build_filled_batch(
        repo_root=tmp_path,
        template_path=template,
        owner_identity="scope-owner",
        owner_role="repository_owner",
        decision_timestamp_utc="2026-07-03T00:00:00Z",
        evidence_reference="owner-review://scope-cleanup/release-surface-first",
    )

    assert filled["status"] == "filled"
    assert filled["contract_pass"] is True
    assert filled["decision_row_count"] == 3
    assert filled["delete_decision_count"] == 3
    assert filled["extract_decision_count"] == 0
    assert filled["blockers"] == []
    assert filled["decision_rows"][0]["owner_decision"] == "delete_from_structural_repository"

    owner_decisions_path = tmp_path / "filled-owner-decisions.json"
    fill_batch.write_outputs(
        payload=filled,
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
    assert plan["release_surface_first_batch_application_ready"] is True
    assert plan["cleanup_application_preflight"]["ready"] is True
    assert plan["cleanup_command_manifest"]["delete_from_structural_repository"][
        "path_count"
    ] == 3
    assert plan["cleanup_command_manifest"]["manual_application_required"] is True


def test_fill_release_surface_extract_requires_archive_reference(tmp_path: Path) -> None:
    template = tmp_path / "release_surface_first.template.csv"
    _write_release_surface_template(template)

    filled = fill_batch.build_filled_batch(
        repo_root=tmp_path,
        template_path=template,
        owner_identity="scope-owner",
        owner_role="repository_owner",
        decision_timestamp_utc="2026-07-03T00:00:00Z",
        evidence_reference="owner-review://scope-cleanup/release-surface-first",
        decision="extract_to_molecular_or_science_repository",
    )

    assert filled["status"] == "blocked"
    assert filled["contract_pass"] is False
    assert filled["extract_decision_count"] == 3
    assert any(
        blocker.endswith("external_archive_reference_missing_for_extract")
        for blocker in filled["blockers"]
    )
