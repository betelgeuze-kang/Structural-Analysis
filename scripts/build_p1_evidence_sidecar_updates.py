#!/usr/bin/env python3
"""Build EB/RH sidecar updates from a real P1 evidence intake manifest."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from check_p1_benchmark_breadth_status import (  # noqa: E402
    DEFAULT_EXTERNAL_BENCHMARK_SUBMISSION_UPDATES,
    DEFAULT_RESIDUAL_HOLDOUT_CLOSURE_UPDATES,
)
from preflight_p1_evidence_sidecar_intake import (  # noqa: E402
    EXTERNAL_EXPECTED_QUEUE_IDS,
    EXTERNAL_WORK_ITEM_IDS,
    RESIDUAL_EXPECTED_WORK_ITEM_IDS,
    _is_placeholder,
    _is_url,
    _load_json,
    _reference_exists,
    build_preflight,
)
from release_evidence_metadata import input_checksums  # noqa: E402


SCHEMA_VERSION = "p1-evidence-sidecar-intake.v1"
ENGINE_VERSION = "structural-optimization-workbench@1.0.0"
DEFAULT_EXTERNAL_OUT = DEFAULT_EXTERNAL_BENCHMARK_SUBMISSION_UPDATES
DEFAULT_RESIDUAL_OUT = DEFAULT_RESIDUAL_HOLDOUT_CLOSURE_UPDATES
EXTERNAL_SUBMISSION_IDS = {
    "hardest_external_10case": "p1-hardest-external-10case",
    "tpu_hffb": "p1-tpu-hffb",
    "peer_spd_hinge": "p1-peer-spd-hinge",
    "korean_public_structures": "p1-korean-public-structures",
}
EXTERNAL_CLOSURE_REQUIRED = {
    "hardest_external_10case": "hardest_external_10case_submission_receipt",
    "tpu_hffb": "tpu_hffb_submission_receipt",
    "peer_spd_hinge": "peer_spd_hinge_submission_receipt",
    "korean_public_structures": "korean_public_structures_submission_receipt_or_authority_review_hold",
}
RESIDUAL_DEFAULTS = {
    "RH-001": {
        "owner": "licensed_engineer",
        "queue_name": "licensed_engineer_review_queue",
        "queue_status": "closure_evidence_attached",
        "closure_evidence_required": "signed_engineer_review_packet",
        "sla_hours": 72,
        "sla_label": "72h",
        "due_date": "assignment_plus_3_business_days",
    },
    "RH-002": {
        "owner": "legacy_tool_owner",
        "queue_name": "legacy_tool_cross_validation_queue",
        "queue_status": "closure_evidence_attached",
        "closure_evidence_required": "legacy_tool_cross_validation_report",
        "sla_hours": 120,
        "sla_label": "120h",
        "due_date": "assignment_plus_5_business_days",
    },
    "RH-003": {
        "owner": "authority_workflow_owner",
        "queue_name": "legal_authority_signoff_queue",
        "queue_status": "closure_evidence_attached",
        "closure_evidence_required": "authority_signoff_receipt_or_formal_hold",
        "sla_hours": 168,
        "sla_label": "168h",
        "due_date": "authority_submission_window",
    },
}


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _rows(payload: dict[str, Any], key: str, *, id_keys: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    rows: Any = payload.get(key, {})
    if isinstance(rows, list):
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            for id_key in id_keys:
                row_id = _text(row.get(id_key, ""))
                if row_id:
                    result[row_id] = row
                    break
        return result
    if isinstance(rows, dict):
        return {str(row_id): row for row_id, row in rows.items() if isinstance(row, dict)}
    return {}


def _existing_updates(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None or not path.exists():
        return {}
    payload = _load_json(path)
    updates = payload.get("updates", {})
    return {str(row_id): row for row_id, row in updates.items() if isinstance(row, dict)} if isinstance(updates, dict) else {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_head(repo_root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def _metadata_fields(*, repo_root: Path, reused_evidence: bool, input_paths: list[Path]) -> dict[str, Any]:
    return {
        "source_commit_sha": _git_head(repo_root),
        "engine_version": ENGINE_VERSION,
        "input_checksums": input_checksums(input_paths, repo_root=repo_root),
        "reused_evidence": reused_evidence,
    }


def _normalize_reference(reference: str, *, repo_root: Path) -> str:
    reference = _text(reference)
    if _is_placeholder(reference) or _is_url(reference):
        return reference
    path = Path(reference)
    if not path.is_absolute():
        return reference
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return reference


def _require_reference(reference: str, *, repo_root: Path, label: str) -> str:
    normalized = _normalize_reference(reference, repo_root=repo_root)
    if not _reference_exists(normalized, repo_root=repo_root):
        raise ValueError(f"{label} evidence reference is missing or does not exist: {reference or 'pending'}")
    return normalized


def _external_reference(row: dict[str, Any]) -> str:
    return (
        _text(row.get("receipt_url", ""))
        or _text(row.get("receipt_path", ""))
        or _text(row.get("submission_receipt", ""))
        or _text(row.get("closure_evidence_path", ""))
    )


def _external_update(
    queue_id: str,
    row: dict[str, Any],
    *,
    base_row: dict[str, Any],
    repo_root: Path,
    generated_at: str,
) -> dict[str, Any]:
    reference = _require_reference(_external_reference(row), repo_root=repo_root, label=queue_id)
    submitted_at = _text(row.get("submitted_at_utc", "")) or generated_at
    last_checked = _text(row.get("last_checked_at_utc", "")) or generated_at
    closure_path = _text(row.get("closure_evidence_path", "")) or reference
    closure_path = _require_reference(closure_path, repo_root=repo_root, label=f"{queue_id} closure")
    return {
        **base_row,
        "work_item_id": _text(row.get("work_item_id", "")) or EXTERNAL_WORK_ITEM_IDS.get(queue_id, ""),
        "submission_id": _text(row.get("submission_id", "")) or EXTERNAL_SUBMISSION_IDS.get(queue_id, ""),
        "receipt_url": reference,
        "submission_receipt": reference,
        "submission_receipt_status": "attached",
        "receipt_status": "attached",
        "submission_status": "submitted_receipt_attached",
        "submission_lifecycle_status": "submitted_receipt_attached",
        "submission_owner_action": "submission_receipt_attached_verify_roundtrip",
        "closure_evidence_required": _text(row.get("closure_evidence_required", ""))
        or _text(base_row.get("closure_evidence_required", ""))
        or EXTERNAL_CLOSURE_REQUIRED.get(queue_id, "external_submission_receipt"),
        "closure_evidence_path": closure_path,
        "closure_evidence_status": "attached",
        "submitted_at_utc": submitted_at,
        "last_checked_at_utc": last_checked,
    }


def _residual_update(
    work_item_id: str,
    row: dict[str, Any],
    *,
    base_row: dict[str, Any],
    repo_root: Path,
    generated_at: str,
) -> dict[str, Any]:
    defaults = RESIDUAL_DEFAULTS.get(work_item_id, {})
    reference = _require_reference(_text(row.get("closure_evidence_path", "")), repo_root=repo_root, label=work_item_id)
    return {
        **defaults,
        **base_row,
        "status": "closed",
        "queue_status": _text(row.get("queue_status", "")) or "closure_evidence_attached",
        "closure_evidence_path": reference,
        "closure_evidence_required": _text(row.get("closure_evidence_required", ""))
        or _text(base_row.get("closure_evidence_required", ""))
        or _text(defaults.get("closure_evidence_required", "")),
        "closure_evidence_status": "attached",
        "owner": _text(row.get("owner", "")) or _text(base_row.get("owner", "")) or _text(defaults.get("owner", "")),
        "last_checked_at_utc": _text(row.get("last_checked_at_utc", "")) or generated_at,
        "closed_at_utc": _text(row.get("closed_at_utc", "")) or generated_at,
    }


def build_sidecars(
    *,
    intake_manifest: Path,
    base_external_updates: Path | None,
    base_residual_updates: Path | None,
    repo_root: Path,
    require_complete: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    intake = _load_json(intake_manifest)
    generated_at = _text(intake.get("generated_at", "")) or _now()
    external_intake = _rows(
        intake,
        "external_benchmark_receipts",
        id_keys=("queue_id", "work_item_id", "id"),
    )
    residual_intake = _rows(
        intake,
        "residual_holdout_closures",
        id_keys=("work_item_id", "category_id", "id"),
    )
    base_external = _existing_updates(base_external_updates)
    base_residual = _existing_updates(base_residual_updates)

    def has_external_intake(queue_id: str) -> bool:
        return queue_id in external_intake or EXTERNAL_WORK_ITEM_IDS.get(queue_id, "") in external_intake

    external_updates: dict[str, dict[str, Any]] = {}
    for queue_id in EXTERNAL_EXPECTED_QUEUE_IDS:
        base_row = dict(base_external.get(queue_id, {}))
        row = external_intake.get(queue_id) or external_intake.get(EXTERNAL_WORK_ITEM_IDS.get(queue_id, "")) or {}
        external_updates[queue_id] = (
            _external_update(queue_id, row, base_row=base_row, repo_root=repo_root, generated_at=generated_at)
            if row
            else base_row
        )

    residual_updates: dict[str, dict[str, Any]] = {}
    for work_item_id in RESIDUAL_EXPECTED_WORK_ITEM_IDS:
        base_row = dict(base_residual.get(work_item_id, {}))
        row = residual_intake.get(work_item_id) or {}
        residual_updates[work_item_id] = (
            _residual_update(work_item_id, row, base_row=base_row, repo_root=repo_root, generated_at=generated_at)
            if row
            else base_row
        )

    if require_complete:
        missing_external = [queue_id for queue_id in EXTERNAL_EXPECTED_QUEUE_IDS if not has_external_intake(queue_id)]
        missing_residual = [work_item_id for work_item_id in RESIDUAL_EXPECTED_WORK_ITEM_IDS if work_item_id not in residual_intake]
        if missing_external or missing_residual:
            raise ValueError(
                "complete intake required but missing rows: "
                f"external={','.join(missing_external) or 'none'}; residual={','.join(missing_residual) or 'none'}"
            )

    external_payload = {
        "schema_version": "external-benchmark-submission-updates.v1",
        "generated_at": generated_at,
        **_metadata_fields(
            repo_root=repo_root,
            reused_evidence=False,
            input_paths=[intake_manifest, *(path for path in (base_external_updates,) if path is not None)],
        ),
        "evidence_basis": {
            "basis_kind": "p1_evidence_intake_manifest",
            "intake_manifest": str(intake_manifest),
            "actual_external_submission_receipts_attached": all(bool(row) for row in external_updates.values()),
        },
        "claim_boundary": (
            "External benchmark update sidecars are generated only from intake manifest rows "
            "or preserved pending rows. They do not synthesize submission receipts."
        ),
        "updates": external_updates,
    }
    residual_payload = {
        "schema_version": "residual-holdout-closure-updates.v1",
        "generated_at": generated_at,
        **_metadata_fields(
            repo_root=repo_root,
            reused_evidence=False,
            input_paths=[intake_manifest, *(path for path in (base_residual_updates,) if path is not None)],
        ),
        "evidence_basis": {
            "basis_kind": "p1_evidence_intake_manifest",
            "intake_manifest": str(intake_manifest),
            "actual_closure_evidence_attached": all(bool(row) for row in residual_updates.values()),
        },
        "claim_boundary": (
            "Residual holdout update sidecars are generated only from intake manifest rows "
            "or preserved pending rows. They do not synthesize closure evidence."
        ),
        "updates": residual_updates,
    }
    return external_payload, residual_payload


def build_metadata_only_sidecars(
    *,
    base_external_updates: Path | None,
    base_residual_updates: Path | None,
    repo_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    generated_at = _now()
    external_updates = {
        queue_id: dict(_existing_updates(base_external_updates).get(queue_id, {}))
        for queue_id in EXTERNAL_EXPECTED_QUEUE_IDS
    }
    residual_updates = {
        work_item_id: dict(_existing_updates(base_residual_updates).get(work_item_id, {}))
        for work_item_id in RESIDUAL_EXPECTED_WORK_ITEM_IDS
    }
    external_payload = {
        "schema_version": "external-benchmark-submission-updates.v1",
        "generated_at": generated_at,
        **_metadata_fields(
            repo_root=repo_root,
            reused_evidence=True,
            input_paths=[*(path for path in (base_external_updates,) if path is not None)],
        ),
        "evidence_basis": {
            "basis_kind": "existing_sidecar_metadata_refresh",
            "base_external_updates": str(base_external_updates or ""),
            "actual_external_submission_receipts_attached": all(bool(row.get("receipt_url")) for row in external_updates.values()),
        },
        "claim_boundary": (
            "Metadata-only refresh preserves existing external benchmark sidecar rows and "
            "marks reused_evidence=true. It does not create, infer, or attach receipts."
        ),
        "updates": external_updates,
    }
    residual_payload = {
        "schema_version": "residual-holdout-closure-updates.v1",
        "generated_at": generated_at,
        **_metadata_fields(
            repo_root=repo_root,
            reused_evidence=True,
            input_paths=[*(path for path in (base_residual_updates,) if path is not None)],
        ),
        "evidence_basis": {
            "basis_kind": "existing_sidecar_metadata_refresh",
            "base_residual_updates": str(base_residual_updates or ""),
            "actual_closure_evidence_attached": all(
                bool(row.get("closure_evidence_path")) for row in residual_updates.values()
            ),
        },
        "claim_boundary": (
            "Metadata-only refresh preserves existing residual holdout sidecar rows and "
            "marks reused_evidence=true. It does not create, infer, or attach closure evidence."
        ),
        "updates": residual_updates,
    }
    return external_payload, residual_payload


def _summary(
    *,
    external_payload: dict[str, Any],
    residual_payload: dict[str, Any],
    external_out: Path,
    residual_out: Path,
    repo_root: Path,
) -> dict[str, Any]:
    temp_external = external_out
    temp_residual = residual_out
    _write_json(temp_external, external_payload)
    _write_json(temp_residual, residual_payload)
    preflight = build_preflight(
        external_benchmark_submission_updates=temp_external,
        residual_holdout_closure_updates=temp_residual,
        repo_root=repo_root,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "contract_pass": bool(preflight["contract_pass"]),
        "reason_code": preflight["reason_code"],
        "summary": preflight["summary"],
        "blockers": preflight["blockers"],
        "artifacts": {
            "external_benchmark_submission_updates": str(external_out),
            "residual_holdout_closure_updates": str(residual_out),
            "repo_root": str(repo_root),
        },
    }


def _failure_summary(
    *,
    error: Exception,
    args: argparse.Namespace,
) -> dict[str, Any]:
    message = str(error)
    return {
        "schema_version": SCHEMA_VERSION,
        "contract_pass": False,
        "reason_code": "ERR_P1_EVIDENCE_SIDECAR_BUILD_FAILED",
        "summary": {
            "external_expected_queue_count": len(EXTERNAL_EXPECTED_QUEUE_IDS),
            "residual_expected_work_item_count": len(RESIDUAL_EXPECTED_WORK_ITEM_IDS),
            "error": message,
        },
        "blockers": [message],
        "artifacts": {
            "intake_manifest": str(args.intake_manifest),
            "external_benchmark_submission_updates": str(args.external_out),
            "residual_holdout_closure_updates": str(args.residual_out),
            "repo_root": str(args.repo_root),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intake-manifest", type=Path)
    parser.add_argument("--base-external-updates", type=Path, default=DEFAULT_EXTERNAL_BENCHMARK_SUBMISSION_UPDATES)
    parser.add_argument("--base-residual-updates", type=Path, default=DEFAULT_RESIDUAL_HOLDOUT_CLOSURE_UPDATES)
    parser.add_argument("--external-out", type=Path, default=DEFAULT_EXTERNAL_OUT)
    parser.add_argument("--residual-out", type=Path, default=DEFAULT_RESIDUAL_OUT)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--summary-out", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--metadata-only-existing", action="store_true")
    parser.add_argument("--fail-open", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.metadata_only_existing:
            external_payload, residual_payload = build_metadata_only_sidecars(
                base_external_updates=args.base_external_updates,
                base_residual_updates=args.base_residual_updates,
                repo_root=args.repo_root,
            )
        else:
            if args.intake_manifest is None:
                raise ValueError("--intake-manifest is required unless --metadata-only-existing is set")
            external_payload, residual_payload = build_sidecars(
                intake_manifest=args.intake_manifest,
                base_external_updates=args.base_external_updates,
                base_residual_updates=args.base_residual_updates,
                repo_root=args.repo_root,
                require_complete=args.require_complete,
            )
        summary = _summary(
            external_payload=external_payload,
            residual_payload=residual_payload,
            external_out=args.external_out,
            residual_out=args.residual_out,
            repo_root=args.repo_root,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        summary = _failure_summary(error=exc, args=args)
        if args.summary_out:
            _write_json(args.summary_out, summary)
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(summary["reason_code"])
        print(f"P1 evidence sidecar build failed: {exc}", file=sys.stderr)
        return 2

    if args.summary_out:
        _write_json(args.summary_out, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) if args.json else summary["reason_code"])
    return 1 if args.fail_open and not bool(summary["contract_pass"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
