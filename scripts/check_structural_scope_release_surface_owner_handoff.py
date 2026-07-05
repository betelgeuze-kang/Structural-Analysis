#!/usr/bin/env python3
"""Check release-surface-first structural scope owner handoff consistency."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import release_evidence_metadata  # noqa: E402


SCHEMA_VERSION = "structural-scope-release-surface-owner-handoff-check.v1"
PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_APPLICATION_PLAN = (
    PRODUCTIZATION / "structural_scope_owner_decision_application_plan.json"
)
DEFAULT_PM_REGISTER = PRODUCTIZATION / "pm_release_blocker_action_register.json"
DEFAULT_ROADMAP = PRODUCTIZATION / "structural_product_development_roadmap.json"
DEFAULT_TEMPLATE_CSV = (
    PRODUCTIZATION / "structural_scope_owner_decisions.release_surface_first.template.csv"
)
DEFAULT_TEMPLATE_JSON = DEFAULT_TEMPLATE_CSV.with_suffix(".json")
DEFAULT_OVERRIDES_CSV = (
    PRODUCTIZATION
    / "structural_scope_owner_decisions.release_surface_first.overrides.template.csv"
)
DEFAULT_OUT = (
    PRODUCTIZATION / "structural_scope_release_surface_owner_handoff_check.json"
)
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")

STRUCTURAL_SCOPE_BLOCKER_ID = "structural_scope_cleanup::owner_review_decisions_pending"
ALLOWED_RELEASE_SURFACE_DECISIONS = [
    "delete_from_structural_repository",
    "extract_to_molecular_or_science_repository",
]
REQUIRED_OWNER_FIELDS = [
    "owner_decision",
    "owner_identity",
    "owner_role",
    "decision_timestamp_utc",
    "evidence_reference",
]


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = _resolve(repo_root, path)
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_csv_rows(repo_root: Path, path: Path) -> tuple[list[dict[str, str]], list[str]]:
    resolved = _resolve(repo_root, path)
    if not resolved.exists():
        return [], []
    with resolved.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader], list(reader.fieldnames or [])


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _split_decisions(value: Any) -> list[str]:
    if isinstance(value, list):
        raw = value
    else:
        raw = str(value or "").replace(",", ";").split(";")
    return [str(item).strip() for item in raw if str(item).strip()]


def _unique(rows: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for row in rows:
        if row and row not in seen:
            seen.add(row)
            result.append(row)
    return result


def _paths_from_rows(rows: list[dict[str, Any]]) -> list[str]:
    return [_text(row.get("path")) for row in rows if _text(row.get("path"))]


def _compare_paths(
    *,
    label: str,
    expected_paths: list[str],
    actual_paths: list[str],
) -> list[str]:
    blockers: list[str] = []
    if actual_paths != expected_paths:
        blockers.append(f"{label}_path_order_or_membership_mismatch")
    missing = [path for path in expected_paths if path not in actual_paths]
    extra = [path for path in actual_paths if path not in expected_paths]
    blockers.extend(f"{label}_missing_path:{path}" for path in missing)
    blockers.extend(f"{label}_extra_path:{path}" for path in extra)
    if len(actual_paths) != len(set(actual_paths)):
        blockers.append(f"{label}_duplicate_paths")
    return blockers


def _pm_structural_scope_row(pm_register: dict[str, Any]) -> dict[str, Any]:
    for row in _as_list(pm_register.get("rows")):
        if isinstance(row, dict) and row.get("blocker_id") == STRUCTURAL_SCOPE_BLOCKER_ID:
            return row
    return {}


def _roadmap_slice(roadmap: dict[str, Any]) -> dict[str, Any]:
    for row in _as_list(roadmap.get("recommended_next_slice_details")):
        if (
            isinstance(row, dict)
            and row.get("id")
            == "close_structural_scope_owner_review_and_release_surface_cleanup"
        ):
            return row
    return {}


def _batch_id(value: Any) -> str:
    if isinstance(value, dict):
        return _text(value.get("batch_id"))
    return _text(value)


def _strip_volatile(value: Any, path: tuple[str, ...] = ()) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _strip_volatile(child, path + (str(key),))
            for key, child in value.items()
            if str(key) != "generated_at"
            and not (path == () and str(key) == "source_commit_sha")
        }
    if isinstance(value, list):
        return [_strip_volatile(item, path) for item in value]
    return value


def _differing_paths(existing: Any, generated: Any, prefix: str = "") -> list[str]:
    if existing == generated:
        return []
    if isinstance(existing, dict) and isinstance(generated, dict):
        rows: list[str] = []
        for key in sorted(set(existing) | set(generated)):
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            rows.extend(_differing_paths(existing.get(key), generated.get(key), child_prefix))
        return rows
    return [prefix or "<root>"]


def build_handoff_check(
    *,
    repo_root: Path = ROOT,
    application_plan_path: Path = DEFAULT_APPLICATION_PLAN,
    pm_register_path: Path = DEFAULT_PM_REGISTER,
    roadmap_path: Path = DEFAULT_ROADMAP,
    template_csv_path: Path = DEFAULT_TEMPLATE_CSV,
    template_json_path: Path = DEFAULT_TEMPLATE_JSON,
    overrides_csv_path: Path = DEFAULT_OVERRIDES_CSV,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    application_plan = _load_json(repo_root, application_plan_path)
    pm_register = _load_json(repo_root, pm_register_path)
    roadmap = _load_json(repo_root, roadmap_path)
    template_payload = _load_json(repo_root, template_json_path)
    template_csv_rows, template_csv_columns = _load_csv_rows(repo_root, template_csv_path)
    overrides_csv_rows, overrides_csv_columns = _load_csv_rows(repo_root, overrides_csv_path)

    action_packet = _as_dict(application_plan.get("release_surface_first_owner_action_packet"))
    intake = _as_dict(application_plan.get("release_surface_first_batch_decision_intake"))
    template_json_rows = [
        row for row in _as_list(template_payload.get("decision_rows")) if isinstance(row, dict)
    ]
    expected_paths = _unique(
        [
            *[str(path) for path in _as_list(application_plan.get("release_surface_owner_decision_required_paths"))],
            *[str(path) for path in _as_list(action_packet.get("paths"))],
            *[str(path) for path in _as_list(intake.get("expected_paths"))],
        ]
    )
    pm_row = _pm_structural_scope_row(pm_register)
    roadmap_slice = _roadmap_slice(roadmap)

    blockers: list[str] = []
    warnings: list[str] = []
    if not application_plan:
        blockers.append("application_plan_missing_or_unreadable")
    if not action_packet:
        blockers.append("release_surface_first_owner_action_packet_missing")
    if not expected_paths:
        blockers.append("release_surface_first_expected_paths_missing")
    if _batch_id(application_plan.get("next_owner_review_batch")) != "release_surface_first":
        blockers.append("next_owner_review_batch_not_release_surface_first")
    if _int(application_plan.get("release_surface_owner_decision_required_count")) != len(expected_paths):
        blockers.append("release_surface_owner_decision_required_count_mismatch")
    if action_packet.get("status") != "ready_for_owner_decision_request":
        blockers.append("owner_action_packet_not_ready_for_request")
    if action_packet.get("ready_to_request_owner_decision") is not True:
        blockers.append("owner_action_packet_ready_flag_not_true")
    if _int(action_packet.get("path_count")) != len(expected_paths):
        blockers.append("owner_action_packet_path_count_mismatch")
    if [str(item) for item in _as_list(action_packet.get("allowed_owner_decisions"))] != ALLOWED_RELEASE_SURFACE_DECISIONS:
        blockers.append("owner_action_packet_allowed_decisions_mismatch")
    if "retain_quarantined_with_signed_owner_exception" not in [
        str(item) for item in _as_list(action_packet.get("disallowed_owner_decisions"))
    ]:
        blockers.append("owner_action_packet_retain_not_explicitly_disallowed")
    for field in REQUIRED_OWNER_FIELDS:
        if field not in [str(item) for item in _as_list(action_packet.get("required_owner_fields"))]:
            blockers.append(f"owner_action_packet_required_field_missing:{field}")
    if not any(
        "external_archive_reference" in str(item)
        for item in _as_list(action_packet.get("conditional_required_fields"))
    ):
        blockers.append("owner_action_packet_extract_archive_condition_missing")

    primary_preview = _as_dict(action_packet.get("primary_cleanup_preview"))
    if primary_preview.get("owner_decision_required") is not True:
        blockers.append("primary_cleanup_preview_owner_decision_required_not_true")
    if primary_preview.get("safe_to_auto_apply") is not False:
        blockers.append("primary_cleanup_preview_safe_to_auto_apply_not_false")
    if primary_preview.get("primary_delete_paths") != expected_paths:
        blockers.append("primary_cleanup_preview_delete_paths_mismatch")

    template_csv_paths = _paths_from_rows(template_csv_rows)
    template_json_paths = _paths_from_rows(template_json_rows)
    overrides_csv_paths = _paths_from_rows(overrides_csv_rows)
    blockers.extend(
        _compare_paths(
            label="template_csv",
            expected_paths=expected_paths,
            actual_paths=template_csv_paths,
        )
    )
    blockers.extend(
        _compare_paths(
            label="template_json",
            expected_paths=expected_paths,
            actual_paths=template_json_paths,
        )
    )
    blockers.extend(
        _compare_paths(
            label="overrides_template_csv",
            expected_paths=expected_paths,
            actual_paths=overrides_csv_paths,
        )
    )
    for column in ["path", "owner_decision", "external_archive_reference", "evidence_reference"]:
        if column not in overrides_csv_columns:
            blockers.append(f"overrides_template_column_missing:{column}")
    for row in template_csv_rows:
        path = _text(row.get("path"))
        if _text(row.get("path_area")) != "release_surface":
            blockers.append(f"template_csv_non_release_surface_row:{path}")
        if _text(row.get("owner_decision")):
            blockers.append(f"template_csv_prefilled_owner_decision:{path}")
        if _text(row.get("recommended_owner_decision_primary")) != "delete_from_structural_repository":
            blockers.append(f"template_csv_primary_decision_not_delete:{path}")
        if _text(row.get("recommended_owner_decision_alternate")) != "extract_to_molecular_or_science_repository":
            blockers.append(f"template_csv_alternate_decision_not_extract:{path}")
        if _split_decisions(row.get("allowed_owner_decisions")) != ALLOWED_RELEASE_SURFACE_DECISIONS:
            blockers.append(f"template_csv_allowed_decisions_mismatch:{path}")
    for row in template_json_rows:
        path = _text(row.get("path"))
        if _text(row.get("owner_decision")):
            blockers.append(f"template_json_prefilled_owner_decision:{path}")
        if [str(item) for item in _as_list(row.get("allowed_owner_decisions"))] != ALLOWED_RELEASE_SURFACE_DECISIONS:
            blockers.append(f"template_json_allowed_decisions_mismatch:{path}")
    for row in overrides_csv_rows:
        path = _text(row.get("path"))
        if _text(row.get("owner_decision")):
            blockers.append(f"overrides_template_prefilled_owner_decision:{path}")
        if _text(row.get("external_archive_reference")):
            blockers.append(f"overrides_template_prefilled_external_archive:{path}")
        if _text(row.get("evidence_reference")):
            blockers.append(f"overrides_template_prefilled_evidence_reference:{path}")

    if not pm_row:
        blockers.append("pm_structural_scope_cleanup_blocker_row_missing")
    else:
        if pm_row.get("handoff_ready") is not True:
            blockers.append("pm_structural_scope_cleanup_handoff_not_ready")
        pm_next_action = str(pm_row.get("next_action") or "")
        for path in expected_paths:
            if path not in pm_next_action:
                blockers.append(f"pm_next_action_missing_release_surface_path:{path}")
    if not roadmap_slice:
        blockers.append("roadmap_structural_scope_next_slice_missing")
    else:
        current_position = _as_dict(roadmap_slice.get("current_position"))
        if current_position.get("next_owner_review_batch") != "release_surface_first":
            blockers.append("roadmap_next_owner_review_batch_mismatch")
        if _int(current_position.get("release_surface_pending_decision_count")) != len(expected_paths):
            blockers.append("roadmap_release_surface_pending_count_mismatch")

    if application_plan.get("release_surface_first_batch_application_ready") is True:
        warnings.append("release_surface_first_batch_already_application_ready")
    if intake.get("pending_decision_count") != len(expected_paths):
        blockers.append("release_surface_first_pending_decision_count_mismatch")

    blockers = sorted(set(item for item in blockers if item))
    warnings = sorted(set(item for item in warnings if item))
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/check_structural_scope_release_surface_owner_handoff.py"),
                application_plan_path,
                pm_register_path,
                # Roadmap is read for semantic cross-checking, but not checksummed
                # here; it already depends on the product snapshot that consumes
                # this handoff receipt, so including it creates a freshness cycle.
                template_csv_path,
                template_json_path,
                overrides_csv_path,
            ],
            reused_evidence=True,
            reuse_policy="non_mutating_release_surface_first_owner_handoff_consistency_check",
            repo_root=repo_root,
        ),
        "status": "ready_for_owner_review" if not blockers else "blocked",
        "contract_pass": not blockers,
        "handoff_check_pass": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "expected_release_surface_path_count": len(expected_paths),
        "expected_release_surface_paths": expected_paths,
        "owner_decision_state": {
            "owner_decision_pending_count": _int(application_plan.get("owner_decision_pending_count")),
            "owner_decision_recorded_count": _int(application_plan.get("owner_decision_recorded_count")),
            "release_surface_owner_decision_required_count": _int(
                application_plan.get("release_surface_owner_decision_required_count")
            ),
            "release_surface_first_batch_application_ready": bool(
                application_plan.get("release_surface_first_batch_application_ready")
            ),
            "release_surface_first_batch_ready": bool(
                application_plan.get("release_surface_first_batch_ready")
            ),
            "retain_quarantined_exception_count": _int(
                application_plan.get("retain_quarantined_exception_count")
            ),
        },
        "handoff_surfaces": {
            "application_plan_action_packet_status": action_packet.get("status"),
            "application_plan_action_packet_ready": bool(
                action_packet.get("ready_to_request_owner_decision")
            ),
            "template_csv_row_count": len(template_csv_rows),
            "template_json_row_count": len(template_json_rows),
            "overrides_template_csv_row_count": len(overrides_csv_rows),
            "pm_handoff_ready": bool(pm_row.get("handoff_ready")),
            "roadmap_slice_present": bool(roadmap_slice),
        },
        "template_paths": {
            "csv": template_csv_path.as_posix(),
            "json": template_json_path.as_posix(),
            "overrides_csv": overrides_csv_path.as_posix(),
        },
        "next_owner_input": {
            "allowed_owner_decisions": ALLOWED_RELEASE_SURFACE_DECISIONS,
            "disallowed_owner_decisions": ["retain_quarantined_with_signed_owner_exception"],
            "required_owner_fields": REQUIRED_OWNER_FIELDS,
            "conditional_required_fields": [
                "external_archive_reference when owner_decision=extract_to_molecular_or_science_repository"
            ],
            "fill_command": _as_dict(
                action_packet.get("owner_decision_submission_options")
            ).get("fill_release_surface_owner_decisions_with_overrides_command", ""),
            "merge_command": _as_dict(
                action_packet.get("owner_decision_submission_options")
            ).get("merge_and_validate_filled_csv_command", ""),
            "post_decision_verification": [
                str(item) for item in _as_list(action_packet.get("post_decision_verification"))
            ],
        },
        "claim_boundary": (
            "This check only verifies that the release-surface-first owner-review handoff "
            "is internally consistent across templates, PM handoff, and roadmap surfaces. "
            "It is not an owner decision, does not delete or extract files, and does not "
            "close structural scope cleanup."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Structural Scope Release Surface Owner Handoff Check",
        "",
        f"- `status`: `{payload['status']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `expected_release_surface_path_count`: `{payload['expected_release_surface_path_count']}`",
        "",
        "## Paths",
        "",
    ]
    lines.extend(f"- `{path}`" for path in payload["expected_release_surface_paths"])
    lines.extend(["", "## Owner Decision State", ""])
    for key, value in payload["owner_decision_state"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Blockers", ""])
    if payload["blockers"]:
        lines.extend(f"- `{item}`" for item in payload["blockers"])
    else:
        lines.append("- none")
    lines.extend(["", "## Next Owner Input", ""])
    next_owner = payload["next_owner_input"]
    lines.append(
        "- `allowed_owner_decisions`: "
        + ", ".join(f"`{item}`" for item in next_owner["allowed_owner_decisions"])
    )
    lines.append(
        "- `disallowed_owner_decisions`: "
        + ", ".join(f"`{item}`" for item in next_owner["disallowed_owner_decisions"])
    )
    if next_owner.get("fill_command"):
        lines.append(f"- `fill_command`: `{next_owner['fill_command']}`")
    if next_owner.get("merge_command"):
        lines.append(f"- `merge_command`: `{next_owner['merge_command']}`")
    lines.extend(["", "## Claim Boundary", "", str(payload["claim_boundary"]), ""])
    return "\n".join(lines)


def write_outputs(
    *,
    payload: dict[str, Any],
    repo_root: Path,
    out: Path,
    out_md: Path | None,
) -> None:
    resolved_out = _resolve(repo_root, out)
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    resolved_out.write_text(_json_text(payload), encoding="utf-8")
    if out_md is not None:
        resolved_md = _resolve(repo_root, out_md)
        resolved_md.parent.mkdir(parents=True, exist_ok=True)
        resolved_md.write_text(_markdown(payload), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--application-plan", type=Path, default=DEFAULT_APPLICATION_PLAN)
    parser.add_argument("--pm-register", type=Path, default=DEFAULT_PM_REGISTER)
    parser.add_argument("--roadmap", type=Path, default=DEFAULT_ROADMAP)
    parser.add_argument("--template-csv", type=Path, default=DEFAULT_TEMPLATE_CSV)
    parser.add_argument("--template-json", type=Path, default=DEFAULT_TEMPLATE_JSON)
    parser.add_argument("--overrides-csv", type=Path, default=DEFAULT_OVERRIDES_CSV)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = args.repo_root.resolve()
    payload = build_handoff_check(
        repo_root=repo_root,
        application_plan_path=args.application_plan,
        pm_register_path=args.pm_register,
        roadmap_path=args.roadmap,
        template_csv_path=args.template_csv,
        template_json_path=args.template_json,
        overrides_csv_path=args.overrides_csv,
    )
    if args.check:
        existing = _load_json(repo_root, args.out)
        differences = _differing_paths(_strip_volatile(existing), _strip_volatile(payload))
        if differences:
            print(
                "Structural scope release-surface owner handoff check FAILED: "
                + ", ".join(differences[:12]),
                file=sys.stderr,
            )
            return 1
        print("Structural scope release-surface owner handoff check: consistent")
    else:
        write_outputs(payload=payload, repo_root=repo_root, out=args.out, out_md=args.out_md)
        if args.json:
            print(_json_text(payload), end="")
        else:
            print(
                "Structural scope release-surface owner handoff check: "
                f"{payload['status'].upper()} | "
                f"paths={payload['expected_release_surface_path_count']} | "
                f"blockers={len(payload['blockers'])}"
            )
    if args.fail_blocked and not payload["contract_pass"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
