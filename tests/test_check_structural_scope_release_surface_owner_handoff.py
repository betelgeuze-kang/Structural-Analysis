from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path
import sys


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "check_structural_scope_release_surface_owner_handoff.py"
)
SPEC = importlib.util.spec_from_file_location(
    "check_structural_scope_release_surface_owner_handoff", SCRIPT_PATH
)
assert SPEC is not None
handoff = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = handoff
SPEC.loader.exec_module(handoff)


PATHS = [
    "implementation/phase1/release_evidence/surface/gpcr_hard_decoy_evidence_surface.json",
    "implementation/phase1/release_evidence/surface/h_bond_backmap_evidence_surface.json",
    "implementation/phase1/release_evidence/surface/pocketmd_lite_science_product_surface.json",
]


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _template_rows(paths: list[str] = PATHS) -> list[dict]:
    return [
        {
            "row_id": f"release_surface_first-{index:03d}",
            "path": path,
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
        }
        for index, (path, family, token) in enumerate(
            zip(
                paths,
                ["molecular_docking", "molecular_science_evidence", "molecular_dynamics"],
                ["gpcr", "h_bond", "pocketmd"],
            ),
            start=1,
        )
    ]


def _template_json_rows(paths: list[str] = PATHS) -> list[dict]:
    rows = []
    for row in _template_rows(paths):
        rows.append(
            {
                **row,
                "families": row["families"].split(";"),
                "matched_tokens": row["matched_tokens"].split(";"),
                "allowed_owner_decisions": [
                    "delete_from_structural_repository",
                    "extract_to_molecular_or_science_repository",
                ],
            }
        )
    return rows


def _write_inputs(tmp_path: Path, *, template_paths: list[str] = PATHS) -> dict[str, Path]:
    app = tmp_path / "application_plan.json"
    pm = tmp_path / "pm_register.json"
    roadmap = tmp_path / "roadmap.json"
    template_csv = tmp_path / "template.csv"
    template_json = tmp_path / "template.json"
    overrides_csv = tmp_path / "overrides.csv"
    _write_json(
        app,
        {
            "next_owner_review_batch": {
                "batch_id": "release_surface_first",
                "path_count": 3,
                "paths": PATHS,
            },
            "owner_decision_pending_count": 86,
            "owner_decision_recorded_count": 0,
            "release_surface_owner_decision_required_count": 3,
            "release_surface_owner_decision_required_paths": PATHS,
            "release_surface_first_batch_application_ready": False,
            "release_surface_first_batch_ready": False,
            "retain_quarantined_exception_count": 0,
            "release_surface_first_batch_decision_intake": {
                "expected_paths": PATHS,
                "pending_decision_count": 3,
            },
            "release_surface_first_owner_action_packet": {
                "status": "ready_for_owner_decision_request",
                "ready_to_request_owner_decision": True,
                "path_count": 3,
                "paths": PATHS,
                "allowed_owner_decisions": [
                    "delete_from_structural_repository",
                    "extract_to_molecular_or_science_repository",
                ],
                "disallowed_owner_decisions": [
                    "retain_quarantined_with_signed_owner_exception"
                ],
                "required_owner_fields": [
                    "owner_decision",
                    "owner_identity",
                    "owner_role",
                    "decision_timestamp_utc",
                    "evidence_reference",
                ],
                "conditional_required_fields": [
                    "external_archive_reference when owner_decision=extract_to_molecular_or_science_repository"
                ],
                "owner_decision_submission_options": {
                    "fill_release_surface_owner_decisions_with_overrides_command": "fill",
                    "merge_and_validate_filled_csv_command": "merge",
                },
                "post_decision_verification": ["verify"],
                "primary_cleanup_preview": {
                    "owner_decision_required": True,
                    "safe_to_auto_apply": False,
                    "primary_delete_paths": PATHS,
                },
            },
        },
    )
    _write_json(
        pm,
        {
            "rows": [
                {
                    "blocker_id": handoff.STRUCTURAL_SCOPE_BLOCKER_ID,
                    "handoff_ready": True,
                    "next_action": " ".join(PATHS),
                }
            ]
        },
    )
    _write_json(
        roadmap,
        {
            "recommended_next_slice_details": [
                {
                    "id": "close_structural_scope_owner_review_and_release_surface_cleanup",
                    "current_position": {
                        "next_owner_review_batch": "release_surface_first",
                        "release_surface_pending_decision_count": 3,
                    },
                }
            ]
        },
    )
    columns = [
        "row_id",
        "path",
        "path_area",
        "families",
        "matched_tokens",
        "recommended_owner_decision",
        "recommended_owner_decision_primary",
        "recommended_owner_decision_alternate",
        "owner_decision",
        "owner_identity",
        "owner_role",
        "decision_timestamp_utc",
        "evidence_reference",
        "signed_owner_exception_reference",
        "external_archive_reference",
        "allowed_owner_decisions",
    ]
    _write_csv(template_csv, _template_rows(template_paths), columns)
    _write_json(template_json, {"decision_rows": _template_json_rows(template_paths)})
    _write_csv(
        overrides_csv,
        [
            {
                "path": path,
                "owner_decision": "",
                "external_archive_reference": "",
                "evidence_reference": "",
            }
            for path in template_paths
        ],
        ["path", "owner_decision", "external_archive_reference", "evidence_reference"],
    )
    return {
        "application_plan_path": app,
        "pm_register_path": pm,
        "roadmap_path": roadmap,
        "template_csv_path": template_csv,
        "template_json_path": template_json,
        "overrides_csv_path": overrides_csv,
    }


def test_release_surface_owner_handoff_check_passes_consistent_handoff(
    tmp_path: Path,
) -> None:
    inputs = _write_inputs(tmp_path)

    payload = handoff.build_handoff_check(repo_root=tmp_path, **inputs)

    assert payload["status"] == "ready_for_owner_review"
    assert payload["contract_pass"] is True
    assert payload["blockers"] == []
    assert payload["expected_release_surface_paths"] == PATHS
    assert payload["owner_decision_state"] == {
        "owner_decision_pending_count": 86,
        "owner_decision_recorded_count": 0,
        "release_surface_owner_decision_required_count": 3,
        "release_surface_first_batch_application_ready": False,
        "release_surface_first_batch_ready": False,
        "retain_quarantined_exception_count": 0,
    }


def test_release_surface_owner_handoff_check_blocks_template_path_drift(
    tmp_path: Path,
) -> None:
    drifted_paths = PATHS[:-1] + [
        "implementation/phase1/release_evidence/surface/unexpected_md_surface.json"
    ]
    inputs = _write_inputs(tmp_path, template_paths=drifted_paths)

    payload = handoff.build_handoff_check(repo_root=tmp_path, **inputs)

    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert "template_csv_path_order_or_membership_mismatch" in payload["blockers"]
    assert (
        "template_json_missing_path:"
        "implementation/phase1/release_evidence/surface/"
        "pocketmd_lite_science_product_surface.json"
    ) in payload["blockers"]
