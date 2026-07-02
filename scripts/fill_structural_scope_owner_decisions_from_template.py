#!/usr/bin/env python3
"""Fill a structural-scope owner decision template without mutating files."""

from __future__ import annotations

import argparse
import csv
from io import StringIO
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_structural_scope_owner_review_packet as owner_review  # noqa: E402
from release_evidence_metadata import release_evidence_metadata  # noqa: E402


SCHEMA_VERSION = "structural-scope-owner-decision-template-fill.v1"
PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_TEMPLATE = PRODUCTIZATION / "structural_scope_owner_decisions.template.csv"
DEFAULT_OUT = PRODUCTIZATION / "structural_scope_owner_decisions.filled.json"
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
DEFAULT_OUT_CSV = DEFAULT_OUT.with_suffix(".csv")
DECISION_RECOMMENDED_PRIMARY = "recommended_primary"
ALLOWED_FILL_DECISIONS = (
    DECISION_RECOMMENDED_PRIMARY,
    "delete_from_structural_repository",
    "extract_to_molecular_or_science_repository",
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _text(value: Any) -> str:
    return str(value or "").strip()


def _split_list_field(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = str(value or "").replace(",", ";").split(";")
    return [str(item).strip() for item in raw_items if str(item).strip()]


def _increment(counter: dict[str, int], key: str) -> None:
    counter[key] = counter.get(key, 0) + 1


def _counts_by_key(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = _text(row.get(key)) or "unknown"
        _increment(counts, value)
    return dict(sorted(counts.items()))


def _family_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        families = row.get("families")
        items = families if isinstance(families, list) else _split_list_field(families)
        if not items:
            items = ["unknown"]
        for family in items:
            _increment(counts, str(family))
    return dict(sorted(counts.items()))


def _load_template_rows(
    repo_root: Path,
    path: Path,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    resolved = _resolve(repo_root, path)
    if not resolved.exists():
        return [], [], ["template_missing"]
    with resolved.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = [dict(row) for row in reader]
        columns = list(reader.fieldnames or [])
    missing_columns = [
        column for column in owner_review.OWNER_DECISION_COLUMNS if column not in columns
    ]
    return rows, columns, [
        f"template_column_missing:{column}" for column in missing_columns
    ]


def _load_decision_override_rows(
    repo_root: Path,
    path: Path | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    if path is None:
        return [], []
    resolved = _resolve(repo_root, path)
    if not resolved.exists():
        return [], ["decision_overrides_missing"]
    if resolved.suffix.lower() == ".json":
        payload = json.loads(resolved.read_text(encoding="utf-8"))
        raw_rows = payload.get("decision_rows") if isinstance(payload, dict) else None
        if raw_rows is None and isinstance(payload, dict):
            raw_rows = payload.get("rows")
        if raw_rows is None and isinstance(payload, dict):
            raw_rows = payload.get("overrides")
        if not isinstance(raw_rows, list):
            return [], ["decision_overrides_json_rows_missing"]
        rows = [dict(row) for row in raw_rows if isinstance(row, dict)]
    else:
        with resolved.open(newline="", encoding="utf-8") as handle:
            rows = [dict(row) for row in csv.DictReader(handle)]
    blockers: list[str] = []
    seen_paths: set[str] = set()
    duplicate_paths: set[str] = set()
    for row in rows:
        override_path = _text(row.get("path"))
        if not override_path:
            blockers.append("decision_override_empty_path")
            continue
        if override_path in seen_paths:
            duplicate_paths.add(override_path)
        seen_paths.add(override_path)
        override_decision = _text(row.get("owner_decision"))
        if override_decision and override_decision not in owner_review.ALLOWED_OWNER_DECISIONS:
            blockers.append(
                f"{override_path}::unsupported_override_decision:{override_decision}"
            )
    blockers.extend(
        f"decision_override_duplicate_path:{override_path}"
        for override_path in sorted(duplicate_paths)
    )
    return rows, blockers


def _decision_for_row(row: dict[str, Any], requested_decision: str) -> str:
    if requested_decision == DECISION_RECOMMENDED_PRIMARY:
        return _text(row.get("recommended_owner_decision_primary"))
    return requested_decision


def _field_blockers(
    *,
    owner_identity: str,
    owner_role: str,
    decision_timestamp_utc: str,
    evidence_reference: str,
    decision: str,
    external_archive_reference: str,
    signed_owner_exception_reference: str,
) -> list[str]:
    blockers: list[str] = []
    if not owner_identity:
        blockers.append("owner_identity_missing")
    elif owner_review._is_placeholder_text(owner_identity):
        blockers.append("owner_identity_placeholder")
    if not owner_role:
        blockers.append("owner_role_missing")
    elif owner_review._is_placeholder_text(owner_role):
        blockers.append("owner_role_placeholder")
    if not decision_timestamp_utc:
        blockers.append("decision_timestamp_utc_missing")
    elif not owner_review._is_utc_timestamp(decision_timestamp_utc):
        blockers.append("decision_timestamp_utc_not_utc")
    if not evidence_reference:
        blockers.append("evidence_reference_missing")
    elif owner_review._is_placeholder_text(evidence_reference):
        blockers.append("evidence_reference_placeholder")
    if decision == "extract_to_molecular_or_science_repository":
        if not external_archive_reference:
            blockers.append("external_archive_reference_missing_for_extract")
        elif owner_review._is_placeholder_text(external_archive_reference):
            blockers.append("external_archive_reference_placeholder")
    if decision == "retain_quarantined_with_signed_owner_exception":
        if not signed_owner_exception_reference:
            blockers.append("signed_owner_exception_reference_missing_for_retain")
        elif owner_review._is_placeholder_text(signed_owner_exception_reference):
            blockers.append("signed_owner_exception_reference_placeholder")
    return blockers


def _csv_text(rows: list[dict[str, Any]]) -> str:
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=list(owner_review.OWNER_DECISION_COLUMNS),
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                column: (
                    ";".join(str(item) for item in row[column])
                    if isinstance(row.get(column), list)
                    else str(row.get(column, ""))
                )
                for column in owner_review.OWNER_DECISION_COLUMNS
            }
        )
    return output.getvalue()


def build_filled_decisions(
    *,
    repo_root: Path = ROOT,
    template_path: Path = DEFAULT_TEMPLATE,
    owner_identity: str,
    owner_role: str,
    decision_timestamp_utc: str,
    evidence_reference: str,
    decision: str = DECISION_RECOMMENDED_PRIMARY,
    external_archive_reference: str = "",
    decision_overrides_path: Path | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    template_rows, template_columns, blockers = _load_template_rows(repo_root, template_path)
    override_rows, override_blockers = _load_decision_override_rows(
        repo_root,
        decision_overrides_path,
    )
    blockers.extend(override_blockers)
    override_by_path = {
        _text(row.get("path")): row for row in override_rows if _text(row.get("path"))
    }
    template_path_order = [
        _text(row.get("path")) for row in template_rows if _text(row.get("path"))
    ]
    unknown_override_paths = sorted(set(override_by_path) - set(template_path_order))
    blockers.extend(
        f"decision_override_unknown_path:{override_path}"
        for override_path in unknown_override_paths
    )
    missing_override_paths = (
        [
            template_path
            for template_path in template_path_order
            if template_path not in override_by_path
        ]
        if decision_overrides_path
        else []
    )
    blockers.extend(
        f"decision_override_missing_path:{template_path}"
        for template_path in missing_override_paths
    )
    if decision not in ALLOWED_FILL_DECISIONS:
        blockers.append(f"unsupported_fill_decision:{decision}")

    decision_rows: list[dict[str, Any]] = []
    row_summaries: list[dict[str, Any]] = []
    for row in template_rows:
        path = _text(row.get("path"))
        override = override_by_path.get(path, {})
        row_requested_decision = (
            _text(override.get("owner_decision"))
            if decision_overrides_path
            else decision
        )
        row_decision = _decision_for_row(row, row_requested_decision)
        row_external_archive_reference = (
            _text(override.get("external_archive_reference"))
            or external_archive_reference
        )
        row_signed_owner_exception_reference = _text(
            override.get("signed_owner_exception_reference")
        )
        row_evidence_reference = (
            _text(override.get("evidence_reference"))
            or evidence_reference
        )
        allowed_decisions = _split_list_field(row.get("allowed_owner_decisions"))
        row_blockers: list[str] = []
        if decision_overrides_path and path not in override_by_path:
            row_blockers.append("decision_override_missing_for_path")
        if decision_overrides_path and not row_requested_decision:
            row_blockers.append("decision_override_owner_decision_missing")
        if row_requested_decision and row_requested_decision not in ALLOWED_FILL_DECISIONS and row_requested_decision not in owner_review.ALLOWED_OWNER_DECISIONS:
            row_blockers.append(
                f"unsupported_override_decision:{row_requested_decision}"
            )
        if row_decision and row_decision not in allowed_decisions:
            row_blockers.append(f"owner_decision_not_allowed:{row_decision}")
        row_blockers.extend(
            _field_blockers(
                owner_identity=owner_identity,
                owner_role=owner_role,
                decision_timestamp_utc=decision_timestamp_utc,
                evidence_reference=row_evidence_reference,
                decision=row_decision,
                external_archive_reference=row_external_archive_reference,
                signed_owner_exception_reference=(
                    row_signed_owner_exception_reference
                ),
            )
        )
        blockers.extend(f"{path or 'unknown_path'}::{item}" for item in row_blockers)
        filled_row = {
            **row,
            "families": _split_list_field(row.get("families")),
            "matched_tokens": _split_list_field(row.get("matched_tokens")),
            "allowed_owner_decisions": allowed_decisions,
            "owner_decision": row_decision,
            "owner_identity": owner_identity,
            "owner_role": owner_role,
            "decision_timestamp_utc": decision_timestamp_utc,
            "evidence_reference": row_evidence_reference,
            "signed_owner_exception_reference": (
                row_signed_owner_exception_reference
                if row_decision == "retain_quarantined_with_signed_owner_exception"
                else ""
            ),
            "external_archive_reference": (
                row_external_archive_reference
                if row_decision == "extract_to_molecular_or_science_repository"
                else ""
            ),
        }
        decision_rows.append(filled_row)
        row_summaries.append(
            {
                "row_id": _text(row.get("row_id")),
                "path": path,
                "path_area": _text(row.get("path_area")),
                "families": _split_list_field(row.get("families")),
                "matched_tokens": _split_list_field(row.get("matched_tokens")),
                "owner_decision": row_decision,
                "allowed_owner_decisions": allowed_decisions,
                "override_applied": path in override_by_path,
                "external_archive_reference": (
                    row_external_archive_reference
                    if row_decision == "extract_to_molecular_or_science_repository"
                    else ""
                ),
                "signed_owner_exception_reference": (
                    row_signed_owner_exception_reference
                    if row_decision == "retain_quarantined_with_signed_owner_exception"
                    else ""
                ),
                "row_blockers": row_blockers,
            }
        )

    unique_blockers = sorted(set(item for item in blockers if item))
    delete_count = sum(
        1
        for row in decision_rows
        if row["owner_decision"] == "delete_from_structural_repository"
    )
    extract_count = sum(
        1
        for row in decision_rows
        if row["owner_decision"] == "extract_to_molecular_or_science_repository"
    )
    retain_count = sum(
        1
        for row in decision_rows
        if row["owner_decision"] == "retain_quarantined_with_signed_owner_exception"
    )
    return {
        "schema_version": owner_review.DECISION_SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/fill_structural_scope_owner_decisions_from_template.py"),
                Path("scripts/build_structural_scope_owner_review_packet.py"),
                template_path,
                *([decision_overrides_path] if decision_overrides_path else []),
            ],
            reused_evidence=False,
            reuse_policy="structural_scope_owner_decision_fill_from_template",
            repo_root=repo_root,
        ),
        "fill_schema_version": SCHEMA_VERSION,
        "status": "filled" if not unique_blockers else "blocked",
        "contract_pass": not unique_blockers,
        "template_path": template_path.as_posix(),
        "decision_overrides_path": (
            decision_overrides_path.as_posix() if decision_overrides_path else ""
        ),
        "decision_override_count": len(override_rows),
        "decision_override_paths": sorted(override_by_path),
        "unknown_decision_override_paths": unknown_override_paths,
        "missing_decision_override_paths": missing_override_paths,
        "template_column_count": len(template_columns),
        "decision_row_count": len(decision_rows),
        "delete_decision_count": delete_count,
        "extract_decision_count": extract_count,
        "retain_decision_count": retain_count,
        "owner_identity": owner_identity,
        "owner_role": owner_role,
        "decision_timestamp_utc": decision_timestamp_utc,
        "evidence_reference": evidence_reference,
        "requested_decision": decision,
        "path_area_counts": _counts_by_key(decision_rows, "path_area"),
        "family_counts": _family_counts(decision_rows),
        "owner_decision_counts": _counts_by_key(decision_rows, "owner_decision"),
        "blockers": unique_blockers,
        "row_summaries": row_summaries,
        "decision_rows": decision_rows,
        "validation_commands": [
            (
                "python3 scripts/build_structural_scope_owner_decision_application_plan.py "
                "--owner-decisions <filled-owner-decisions.json> "
                "--fail-invalid-owner-decisions"
            ),
            (
                "python3 scripts/merge_structural_scope_owner_decision_batch.py "
                "--batch-owner-decisions <filled-owner-decisions.json> "
                "--out <candidate-owner-decisions.json> "
                "--out-md <candidate-owner-decisions.md> "
                "--fail-invalid-owner-decisions"
            ),
        ],
        "claim_boundary": (
            "This helper only fills owner-decision rows from explicit owner "
            "metadata and a template. It does not delete files, extract files, "
            "or close structural scope cleanup. Manual cleanup and refreshed "
            "post-decision structural-scope receipts remain required."
        ),
    }


def write_outputs(
    *,
    payload: dict[str, Any],
    repo_root: Path = ROOT,
    out: Path,
    out_md: Path | None = None,
    out_csv: Path | None = None,
) -> None:
    resolved_out = _resolve(repo_root, out)
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    resolved_out.write_text(_json_text(payload), encoding="utf-8")
    if out_md is not None:
        resolved_md = _resolve(repo_root, out_md)
        resolved_md.parent.mkdir(parents=True, exist_ok=True)
        resolved_md.write_text(_markdown(payload), encoding="utf-8")
    if out_csv is not None:
        resolved_csv = _resolve(repo_root, out_csv)
        resolved_csv.parent.mkdir(parents=True, exist_ok=True)
        resolved_csv.write_text(
            _csv_text([row for row in payload["decision_rows"] if isinstance(row, dict)]),
            encoding="utf-8",
        )


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Structural Scope Owner Decision Template Fill",
        "",
        f"- `status`: `{payload['status']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `decision_row_count`: `{payload['decision_row_count']}`",
        f"- `delete_decision_count`: `{payload['delete_decision_count']}`",
        f"- `extract_decision_count`: `{payload['extract_decision_count']}`",
        f"- `retain_decision_count`: `{payload['retain_decision_count']}`",
        f"- `template_path`: `{payload['template_path']}`",
        f"- `decision_overrides_path`: `{payload['decision_overrides_path']}`",
        f"- `decision_override_count`: `{payload['decision_override_count']}`",
        f"- `requested_decision`: `{payload['requested_decision']}`",
        "",
        "## Counts",
        "",
        f"- `path_area_counts`: `{payload['path_area_counts']}`",
        f"- `family_counts`: `{payload['family_counts']}`",
        f"- `owner_decision_counts`: `{payload['owner_decision_counts']}`",
        "",
        "## Rows",
        "",
        "| Row | Area | Path | Decision | Override | External Archive Reference | Signed Exception | Blockers |",
        "|---|---|---|---|---:|---|---|---|",
    ]
    for row in payload["row_summaries"]:
        blockers = ", ".join(f"`{item}`" for item in row["row_blockers"]) or "none"
        lines.append(
            f"| `{row['row_id']}` | `{row['path_area']}` | `{row['path']}` | "
            f"`{row['owner_decision']}` | `{row['override_applied']}` | "
            f"`{row['external_archive_reference']}` | "
            f"`{row['signed_owner_exception_reference']}` | {blockers} |"
        )
    lines.extend(["", "## Blockers", ""])
    if payload["blockers"]:
        lines.extend(f"- `{item}`" for item in payload["blockers"])
    else:
        lines.append("- none")
    lines.extend(["", "## Claim Boundary", "", str(payload["claim_boundary"]), ""])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--out-csv", type=Path, default=DEFAULT_OUT_CSV)
    parser.add_argument("--owner-identity", required=True)
    parser.add_argument("--owner-role", required=True)
    parser.add_argument("--decision-timestamp-utc", required=True)
    parser.add_argument("--evidence-reference", required=True)
    parser.add_argument("--external-archive-reference", default="")
    parser.add_argument(
        "--decision-overrides",
        type=Path,
        help=(
            "Optional CSV or JSON rows keyed by path with owner_decision, "
            "optional evidence_reference, external_archive_reference for extract, "
            "and signed_owner_exception_reference for retain."
        ),
    )
    parser.add_argument(
        "--decision",
        choices=ALLOWED_FILL_DECISIONS,
        default=DECISION_RECOMMENDED_PRIMARY,
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_filled_decisions(
        repo_root=args.repo_root,
        template_path=args.template,
        owner_identity=args.owner_identity,
        owner_role=args.owner_role,
        decision_timestamp_utc=args.decision_timestamp_utc,
        evidence_reference=args.evidence_reference,
        decision=args.decision,
        external_archive_reference=args.external_archive_reference,
        decision_overrides_path=args.decision_overrides,
    )
    write_outputs(
        payload=payload,
        repo_root=args.repo_root,
        out=args.out,
        out_md=args.out_md,
        out_csv=args.out_csv,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "structural-scope owner decision fill: "
            f"{payload['status'].upper()} | "
            f"rows={payload['decision_row_count']} | "
            f"delete={payload['delete_decision_count']} | "
            f"extract={payload['extract_decision_count']} | "
            f"retain={payload['retain_decision_count']} | "
            f"blockers={len(payload['blockers'])}"
        )
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
