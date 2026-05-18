#!/usr/bin/env python3
"""Validate a filled P1 EB/RH evidence intake manifest before sidecar promotion."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_p1_evidence_sidecar_updates import (  # noqa: E402
    EXTERNAL_EXPECTED_QUEUE_IDS,
    EXTERNAL_WORK_ITEM_IDS,
    RESIDUAL_EXPECTED_WORK_ITEM_IDS,
)
from preflight_p1_evidence_sidecar_intake import _is_placeholder, _is_url  # noqa: E402


SCHEMA_VERSION = "p1-evidence-intake-validation.v1"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _rows(payload: dict[str, Any], key: str, *, id_keys: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    raw_rows: Any = payload.get(key, {})
    if isinstance(raw_rows, dict):
        return {str(row_id): row for row_id, row in raw_rows.items() if isinstance(row, dict)}
    if not isinstance(raw_rows, list):
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        for id_key in id_keys:
            row_id = _text(row.get(id_key))
            if row_id:
                rows[row_id] = row
                break
    return rows


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_reference(reference: str, *, repo_root: Path) -> Path | None:
    if _is_placeholder(reference) or _is_url(reference):
        return None
    path = Path(reference)
    return path if path.is_absolute() else repo_root / path


def _reference_inventory(label: str, reference: str, *, repo_root: Path) -> dict[str, Any]:
    reference = _text(reference)
    row = {
        "label": label,
        "reference": reference,
        "kind": "missing",
        "exists": False,
        "bytes": 0,
        "sha256": "",
    }
    if _is_placeholder(reference):
        return row
    if _is_url(reference):
        row["kind"] = "url"
        row["exists"] = True
        return row
    path = _resolve_reference(reference, repo_root=repo_root)
    row["kind"] = "local_path"
    row["exists"] = bool(path and path.exists())
    if path and path.exists():
        row["bytes"] = path.stat().st_size
        row["sha256"] = _sha256(path)
    return row


def _iso_timestamp_ok(value: Any) -> bool:
    text = _text(value)
    if _is_placeholder(text):
        return False
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _external_reference(row: dict[str, Any]) -> str:
    for key in ("receipt_url", "receipt_path", "submission_receipt", "closure_evidence_path"):
        value = _text(row.get(key))
        if not _is_placeholder(value):
            return value
    return ""


def _external_validation_row(
    queue_id: str,
    row: dict[str, Any],
    *,
    repo_root: Path,
) -> dict[str, Any]:
    expected_work_item = EXTERNAL_WORK_ITEM_IDS.get(queue_id, "")
    receipt_reference = _external_reference(row)
    closure_reference = _text(row.get("closure_evidence_path")) or receipt_reference
    receipt_inventory = _reference_inventory(f"{queue_id}:receipt", receipt_reference, repo_root=repo_root)
    closure_inventory = _reference_inventory(f"{queue_id}:closure", closure_reference, repo_root=repo_root)
    blockers: list[str] = []
    if not row:
        blockers.append(f"external_intake_missing:{queue_id}")
    if _text(row.get("work_item_id")) and _text(row.get("work_item_id")) != expected_work_item:
        blockers.append(f"external_work_item_mismatch:{queue_id}")
    if not receipt_inventory["exists"]:
        blockers.append(f"external_receipt_reference_missing:{queue_id}")
    if not closure_inventory["exists"]:
        blockers.append(f"external_closure_reference_missing:{queue_id}")
    if not _iso_timestamp_ok(row.get("submitted_at_utc")):
        blockers.append(f"external_submitted_at_utc_invalid:{queue_id}")
    if not _iso_timestamp_ok(row.get("last_checked_at_utc")):
        blockers.append(f"external_last_checked_at_utc_invalid:{queue_id}")
    return {
        "queue_id": queue_id,
        "work_item_id": _text(row.get("work_item_id")) or expected_work_item,
        "valid": not blockers,
        "blockers": blockers,
        "receipt_reference": receipt_reference,
        "closure_evidence_reference": closure_reference,
        "evidence_inventory": [receipt_inventory, closure_inventory],
    }


def _residual_validation_row(
    work_item_id: str,
    row: dict[str, Any],
    *,
    repo_root: Path,
) -> dict[str, Any]:
    closure_reference = _text(row.get("closure_evidence_path"))
    closure_inventory = _reference_inventory(f"{work_item_id}:closure", closure_reference, repo_root=repo_root)
    blockers: list[str] = []
    if not row:
        blockers.append(f"residual_intake_missing:{work_item_id}")
    if _text(row.get("work_item_id")) and _text(row.get("work_item_id")) != work_item_id:
        blockers.append(f"residual_work_item_mismatch:{work_item_id}")
    if not closure_inventory["exists"]:
        blockers.append(f"residual_closure_reference_missing:{work_item_id}")
    if not _iso_timestamp_ok(row.get("closed_at_utc")):
        blockers.append(f"residual_closed_at_utc_invalid:{work_item_id}")
    if not _iso_timestamp_ok(row.get("last_checked_at_utc")):
        blockers.append(f"residual_last_checked_at_utc_invalid:{work_item_id}")
    return {
        "work_item_id": work_item_id,
        "valid": not blockers,
        "blockers": blockers,
        "closure_evidence_reference": closure_reference,
        "evidence_inventory": [closure_inventory],
    }


def validate_intake_manifest(*, intake_manifest: Path, repo_root: Path) -> dict[str, Any]:
    payload = _load_json(intake_manifest)
    external_rows = _rows(
        payload,
        "external_benchmark_receipts",
        id_keys=("queue_id", "work_item_id", "id"),
    )
    residual_rows = _rows(
        payload,
        "residual_holdout_closures",
        id_keys=("work_item_id", "category_id", "id"),
    )
    external_validation = [
        _external_validation_row(
            queue_id,
            external_rows.get(queue_id) or external_rows.get(EXTERNAL_WORK_ITEM_IDS.get(queue_id, "")) or {},
            repo_root=repo_root,
        )
        for queue_id in EXTERNAL_EXPECTED_QUEUE_IDS
    ]
    residual_validation = [
        _residual_validation_row(work_item_id, residual_rows.get(work_item_id, {}), repo_root=repo_root)
        for work_item_id in RESIDUAL_EXPECTED_WORK_ITEM_IDS
    ]
    evidence_inventory = [
        inventory
        for row in [*external_validation, *residual_validation]
        for inventory in row["evidence_inventory"]
    ]
    blockers = [
        blocker
        for row in [*external_validation, *residual_validation]
        for blocker in row["blockers"]
    ]
    local_evidence_rows = [
        row for row in evidence_inventory if row["kind"] == "local_path" and row["exists"]
    ]
    url_evidence_rows = [row for row in evidence_inventory if row["kind"] == "url" and row["exists"]]
    contract_pass = not blockers
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_P1_EVIDENCE_INTAKE_INVALID",
        "summary": {
            "external_expected_queue_count": len(EXTERNAL_EXPECTED_QUEUE_IDS),
            "external_valid_count": sum(1 for row in external_validation if row["valid"]),
            "residual_expected_work_item_count": len(RESIDUAL_EXPECTED_WORK_ITEM_IDS),
            "residual_valid_count": sum(1 for row in residual_validation if row["valid"]),
            "local_evidence_count": len(local_evidence_rows),
            "url_evidence_count": len(url_evidence_rows),
            "local_evidence_bytes": sum(int(row["bytes"]) for row in local_evidence_rows),
            "blocker_count": len(blockers),
        },
        "blockers": blockers,
        "external_benchmark_receipts": external_validation,
        "residual_holdout_closures": residual_validation,
        "evidence_inventory": evidence_inventory,
        "artifacts": {
            "intake_manifest": str(intake_manifest),
            "repo_root": str(repo_root),
        },
    }


def _markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# P1 Evidence Intake Validation",
        "",
        f"- `contract_pass`: `{bool(payload['contract_pass'])}`",
        f"- `reason_code`: `{payload['reason_code']}`",
        f"- `external_valid_count`: `{summary['external_valid_count']}/{summary['external_expected_queue_count']}`",
        f"- `residual_valid_count`: `{summary['residual_valid_count']}/{summary['residual_expected_work_item_count']}`",
        f"- `local_evidence_count`: `{summary['local_evidence_count']}`",
        f"- `url_evidence_count`: `{summary['url_evidence_count']}`",
        f"- `blockers`: `{', '.join(payload['blockers']) or 'none'}`",
        "",
        "## External Benchmark Receipts",
        "",
        "| Queue | Valid | Receipt | Closure | Blockers |",
        "|---|---|---|---|---|",
    ]
    for row in payload["external_benchmark_receipts"]:
        lines.append(
            f"| {row['queue_id']} | {row['valid']} | {row['receipt_reference'] or 'missing'} | "
            f"{row['closure_evidence_reference'] or 'missing'} | {', '.join(row['blockers']) or 'none'} |"
        )
    lines.extend(
        [
            "",
            "## Residual Holdout Closures",
            "",
            "| Work Item | Valid | Closure Evidence | Blockers |",
            "|---|---|---|---|",
        ]
    )
    for row in payload["residual_holdout_closures"]:
        lines.append(
            f"| {row['work_item_id']} | {row['valid']} | "
            f"{row['closure_evidence_reference'] or 'missing'} | {', '.join(row['blockers']) or 'none'} |"
        )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intake-manifest", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path)
    parser.add_argument("--out-md", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-open", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = validate_intake_manifest(intake_manifest=args.intake_manifest, repo_root=args.repo_root)
    if args.out:
        _write_json(args.out, payload)
    if args.out_md:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else _markdown(payload))
    return 1 if args.fail_open and not bool(payload["contract_pass"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
