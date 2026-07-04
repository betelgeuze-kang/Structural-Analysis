#!/usr/bin/env python3
"""Materialize PocketMD Lite refinement receipt templates from a ready plan."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from materialize_pocketmd_lite_operator_intake_from_rows import (  # noqa: E402
    DEFAULT_MAX_TOP_K,
    row_value_contract,
)
from release_evidence_metadata import release_evidence_metadata  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_REFINEMENT_PLAN = PRODUCTIZATION / "pocketmd_lite_refinement_execution_plan.json"
DEFAULT_OUT = PRODUCTIZATION / "pocketmd_lite_refinement_receipt_bundle.json"
DEFAULT_ROWS_OUT = PRODUCTIZATION / "pocketmd_lite_topk_rows.json"
DEFAULT_ROWS_FROM_RECEIPT_BUNDLE_REPORT = (
    PRODUCTIZATION / "pocketmd_lite_topk_rows_from_receipt_bundle_report.json"
)
DEFAULT_RECEIPT_ROOT = Path("operator_attached/pocketmd_lite_refinement_receipts")
SCHEMA_VERSION = "pocketmd-lite-refinement-receipt-bundle.v1"
RECEIPT_TEMPLATE_SCHEMA_VERSION = "pocketmd-lite-refinement-receipt-template.v1"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


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


def _write_json(repo_root: Path, path: Path, payload: dict[str, Any]) -> None:
    resolved = _resolve(repo_root, path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_path_part(value: Any) -> str:
    text = str(value or "").strip()
    safe = "".join(char if char.isalnum() or char in "-_" else "_" for char in text)
    return safe.strip("_") or "slot"


def _required_flat_row_fields(slot: dict[str, Any]) -> list[str]:
    fields = [str(row) for row in _as_list(slot.get("required_row_fields")) if str(row)]
    if fields:
        return fields
    return [
        "case_id",
        "source_family",
        "top_k_rank",
        "candidate_id",
        "upstream_top_k_provenance_ref",
        "upstream_top_k_source_checksum",
        "pre_refinement_energy_proxy",
        "post_refinement_energy_proxy",
        "local_min_survived",
        "contact_persistence_rate",
        "h_bond_persistence_rate",
        "clash_count_before",
        "clash_count_after",
        "uncertainty_low",
        "uncertainty_high",
        "uncertainty_unit",
        "provenance_ref",
        "source_checksum",
    ]


def _slot_rows(
    plan: dict[str, Any],
    *,
    receipt_root: Path,
    max_top_k: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    source_slots = _as_list(plan.get("candidate_slot_statuses")) or _as_list(
        plan.get("candidate_slots")
    )
    rows: list[dict[str, Any]] = []
    blockers: list[str] = []
    seen_slots: set[tuple[str, int]] = set()
    for index, raw_slot in enumerate(source_slots, start=1):
        if not isinstance(raw_slot, dict):
            continue
        case_id = str(raw_slot.get("case_id") or "").strip()
        try:
            top_k_rank = int(raw_slot.get("top_k_rank"))
        except (TypeError, ValueError):
            blockers.append(f"slot_{index}:top_k_rank_invalid")
            continue
        if not case_id:
            blockers.append(f"slot_{index}:case_id_missing")
            continue
        if top_k_rank < 1 or top_k_rank > max_top_k:
            blockers.append(f"{case_id}::rank_{top_k_rank}:top_k_rank_invalid")
            continue
        slot_key = (case_id, top_k_rank)
        if slot_key in seen_slots:
            blockers.append(f"{case_id}::rank_{top_k_rank}:duplicate_slot")
            continue
        seen_slots.add(slot_key)
        candidate_id = str(
            raw_slot.get("candidate_id")
            or raw_slot.get("candidate_id_placeholder")
            or f"{case_id}_rank_{top_k_rank:02d}"
        ).strip()
        source_family = str(
            raw_slot.get("source_family") or "upstream_ranked_top_k_candidate_set"
        ).strip()
        receipt_ref = (
            receipt_root
            / _safe_path_part(case_id)
            / f"rank_{top_k_rank:02d}_refinement_receipt.json"
        )
        required_row_fields = _required_flat_row_fields(raw_slot)
        operator_input_required_fields = [
            "source_id",
            "source_url",
            "source_license",
            "source_artifact",
            "source_artifact_sha256",
        ]
        receipt_template = {
            "schema_version": RECEIPT_TEMPLATE_SCHEMA_VERSION,
            "status": "operator_refinement_receipt_required",
            "case_id": case_id,
            "source_family": source_family,
            "top_k_rank": top_k_rank,
            "candidate_id": candidate_id,
            "upstream_top_k_provenance_ref": "",
            "upstream_top_k_source_checksum": "",
            "pre_refinement_energy_proxy": "",
            "post_refinement_energy_proxy": "",
            "local_min_survived": "",
            "contact_persistence_rate": "",
            "h_bond_persistence_rate": "",
            "clash_count_before": "",
            "clash_count_after": "",
            "uncertainty_low": "",
            "uncertainty_high": "",
            "uncertainty_unit": "energy_proxy_delta",
            "provenance_ref": "",
            "source_checksum": "",
            "operator_input_source": {
                field: "" for field in operator_input_required_fields
            },
            "operator_required_fields": [
                *required_row_fields,
                *[
                    f"operator_input_source.{field}"
                    for field in operator_input_required_fields
                ],
            ],
            "row_value_contract": row_value_contract(max_top_k=max_top_k),
            "claim_boundary": (
                "This receipt template is not PocketMD Lite evidence. Complete it "
                "only with real upstream top-k provenance, bounded lite refinement "
                "metrics, interaction persistence metrics, uncertainty intervals, "
                "and source checksums for this one case/rank candidate."
            ),
        }
        template_checksum = _sha256_text(_json_text(receipt_template))
        rows.append(
            {
                "slot_id": str(
                    raw_slot.get("slot_id") or f"{case_id}_rank_{top_k_rank:02d}"
                ),
                "case_id": case_id,
                "top_k_rank": top_k_rank,
                "candidate_id_placeholder": candidate_id,
                "source_family": source_family,
                "receipt_ref": str(receipt_ref),
                "receipt_template_checksum": template_checksum,
                "receipt_template_payload": receipt_template,
                "required_row_fields": required_row_fields,
                "required_metric_fields": [
                    str(row)
                    for row in _as_list(raw_slot.get("required_metric_fields"))
                    if str(row)
                ],
                "required_receipt_fields": [
                    str(row)
                    for row in _as_list(raw_slot.get("required_receipt_fields"))
                    if str(row)
                ],
                "status": "operator_receipt_required",
            }
        )
    if not rows:
        blockers.append("pocketmd_lite_candidate_slots_missing")
    return rows, list(dict.fromkeys(blockers))


def _write_receipt_template_files(
    *,
    repo_root: Path,
    bundle_rows: list[dict[str, Any]],
    overwrite: bool,
) -> tuple[list[dict[str, Any]], list[str]]:
    statuses: list[dict[str, Any]] = []
    blockers: list[str] = []
    for row in bundle_rows:
        case_id = str(row.get("case_id") or "")
        rank = str(row.get("top_k_rank") or "")
        receipt_ref = str(row.get("receipt_ref") or "")
        receipt_template = row.get("receipt_template_payload")
        if not receipt_ref or not isinstance(receipt_template, dict):
            blocker = f"{case_id}::rank_{rank}:receipt_template_missing"
            blockers.append(blocker)
            statuses.append(
                {
                    "case_id": case_id,
                    "top_k_rank": row.get("top_k_rank"),
                    "receipt_ref": receipt_ref,
                    "status": "template_missing",
                    "written": False,
                    "skipped_existing": False,
                    "blockers": [blocker],
                }
            )
            continue
        resolved = _resolve(repo_root, Path(receipt_ref))
        if resolved.exists() and not overwrite:
            statuses.append(
                {
                    "case_id": case_id,
                    "top_k_rank": row.get("top_k_rank"),
                    "receipt_ref": receipt_ref,
                    "status": "skipped_existing",
                    "written": False,
                    "skipped_existing": True,
                    "blockers": [],
                }
            )
            continue
        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(_json_text(receipt_template), encoding="utf-8")
        except OSError as exc:
            blocker = f"{case_id}::rank_{rank}:{exc.__class__.__name__}"
            blockers.append(blocker)
            statuses.append(
                {
                    "case_id": case_id,
                    "top_k_rank": row.get("top_k_rank"),
                    "receipt_ref": receipt_ref,
                    "status": "write_failed",
                    "written": False,
                    "skipped_existing": False,
                    "blockers": [blocker],
                }
            )
        else:
            statuses.append(
                {
                    "case_id": case_id,
                    "top_k_rank": row.get("top_k_rank"),
                    "receipt_ref": receipt_ref,
                    "status": "template_file_written",
                    "written": True,
                    "skipped_existing": False,
                    "blockers": [],
                }
            )
    return statuses, list(dict.fromkeys(blockers))


def materialize_pocketmd_lite_refinement_receipt_bundle(
    *,
    repo_root: Path = ROOT,
    refinement_plan: Path = DEFAULT_REFINEMENT_PLAN,
    out: Path = DEFAULT_OUT,
    receipt_root: Path = DEFAULT_RECEIPT_ROOT,
    rows_out: Path = DEFAULT_ROWS_OUT,
    max_top_k: int = DEFAULT_MAX_TOP_K,
    write_template_files: bool = False,
    overwrite_template_files: bool = False,
) -> dict[str, Any]:
    if max_top_k < 1:
        raise ValueError("max_top_k_must_be_positive")
    plan = _load_json(repo_root, refinement_plan)
    execution_plan_ready = bool(plan.get("execution_plan_ready"))
    bundle_rows, row_blockers = _slot_rows(
        plan,
        receipt_root=receipt_root,
        max_top_k=max_top_k,
    )
    bundle_materialized = execution_plan_ready and not row_blockers
    template_file_statuses: list[dict[str, Any]] = []
    template_file_blockers: list[str] = []
    if bundle_materialized and write_template_files:
        template_file_statuses, template_file_blockers = _write_receipt_template_files(
            repo_root=repo_root,
            bundle_rows=bundle_rows,
            overwrite=overwrite_template_files,
        )
    blockers: list[str] = []
    if not execution_plan_ready:
        blockers.append("pocketmd_lite_refinement_execution_plan_not_ready")
    blockers.extend(row_blockers)
    blockers.extend(template_file_blockers)
    blockers = list(dict.fromkeys(blockers))
    materialization_pass = bundle_materialized and not template_file_blockers
    if bundle_materialized:
        status = "receipt_bundle_materialized"
    elif execution_plan_ready:
        status = "receipt_bundle_materialization_blocked"
    else:
        status = "refinement_execution_plan_not_ready"
    report = {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/materialize_pocketmd_lite_refinement_receipt_bundle.py"),
                refinement_plan,
            ],
            reused_evidence=False,
            reuse_policy="pocketmd_lite_refinement_receipt_bundle_from_execution_plan",
            repo_root=repo_root,
        ),
        "status": status,
        "contract_pass": materialization_pass,
        "bundle_materialized": bundle_materialized,
        "execution_plan_ready": execution_plan_ready,
        "operator_receipts_ready": False,
        "template_files_requested": write_template_files,
        "template_files_written": sum(
            1 for row in template_file_statuses if row.get("written")
        ),
        "template_files_skipped_existing": sum(
            1 for row in template_file_statuses if row.get("skipped_existing")
        ),
        "template_file_statuses": template_file_statuses,
        "refinement_plan_artifact": str(refinement_plan),
        "out_artifact": str(out),
        "receipt_root": str(receipt_root),
        "out_rows_artifact": str(rows_out),
        "required_candidate_slot_count": len(bundle_rows),
        "receipt_template_count": len(bundle_rows) if bundle_materialized else 0,
        "bundle_rows": bundle_rows,
        "blockers": blockers,
        "commands": {
            "rerun_refinement_execution_plan": (
                "python3 scripts/build_pocketmd_lite_refinement_execution_plan.py "
                f"--out {refinement_plan}"
            ),
            "rerun_receipt_bundle": (
                "python3 scripts/materialize_pocketmd_lite_refinement_receipt_bundle.py "
                f"--refinement-plan {refinement_plan} --out {out} "
                f"--receipt-root {receipt_root}"
            ),
            "write_receipt_template_files": (
                "python3 scripts/materialize_pocketmd_lite_refinement_receipt_bundle.py "
                f"--refinement-plan {refinement_plan} --out {out} "
                f"--receipt-root {receipt_root} --write-template-files"
            ),
            "materialize_rows_from_receipt_bundle": (
                "python3 scripts/materialize_pocketmd_lite_topk_rows_from_receipt_bundle.py "
                f"--receipt-bundle {out} --out-rows {rows_out} "
                f"--out-report {DEFAULT_ROWS_FROM_RECEIPT_BUNDLE_REPORT} "
                "--fail-blocked"
            ),
            "materialize_rows_from_template": (
                "python3 scripts/materialize_pocketmd_lite_topk_rows_from_template.py "
                f"--out-rows {rows_out} --fail-blocked"
            ),
            "materialize_operator_intake": (
                "python3 scripts/materialize_pocketmd_lite_operator_intake_from_rows.py "
                f"--rows {rows_out} "
                f"--out {PRODUCTIZATION / 'pocketmd_lite_operator_intake.json'} "
                "--source-id <source-id> --source-url <source-url> "
                "--source-license <license>"
            ),
            "materialize_survival_report": (
                "python3 scripts/materialize_pocketmd_lite_topk_survival_report.py "
                f"--intake {PRODUCTIZATION / 'pocketmd_lite_operator_intake.json'} "
                f"--contract {PRODUCTIZATION / 'pocketmd_lite_contract.json'} "
                f"--out-report {PRODUCTIZATION / 'pocketmd_lite_topk_survival_report.json'} "
                "--out-surface implementation/phase1/release_evidence/surface/"
                "pocketmd_lite_science_product_surface.json --fail-blocked"
            ),
        },
        "summary": {
            "execution_plan_ready": execution_plan_ready,
            "bundle_materialized": bundle_materialized,
            "required_candidate_slot_count": len(bundle_rows),
            "receipt_template_count": len(bundle_rows) if bundle_materialized else 0,
            "template_files_requested": write_template_files,
            "template_files_written": sum(
                1 for row in template_file_statuses if row.get("written")
            ),
            "template_files_skipped_existing": sum(
                1 for row in template_file_statuses if row.get("skipped_existing")
            ),
            "blocker_count": len(blockers),
        },
        "claim_boundary": (
            "This helper embeds per-slot receipt templates for bounded PocketMD "
            "Lite top-k refinement. It does not run refinement, fill metrics, "
            "write top-k rows, or close Phase 4 without completed operator "
            "receipts and downstream survival validation."
        ),
    }
    _write_json(repo_root, out, report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--refinement-plan", type=Path, default=DEFAULT_REFINEMENT_PLAN)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--receipt-root", type=Path, default=DEFAULT_RECEIPT_ROOT)
    parser.add_argument("--rows-out", type=Path, default=DEFAULT_ROWS_OUT)
    parser.add_argument("--max-top-k", type=int, default=DEFAULT_MAX_TOP_K)
    parser.add_argument("--write-template-files", action="store_true")
    parser.add_argument("--overwrite-template-files", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = materialize_pocketmd_lite_refinement_receipt_bundle(
        repo_root=args.repo_root,
        refinement_plan=args.refinement_plan,
        out=args.out,
        receipt_root=args.receipt_root,
        rows_out=args.rows_out,
        max_top_k=args.max_top_k,
        write_template_files=args.write_template_files,
        overwrite_template_files=args.overwrite_template_files,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "pocketmd-lite-refinement-receipt-bundle: "
            f"{payload['status']} | slots={payload['required_candidate_slot_count']} | "
            f"written={payload['bundle_materialized']}"
        )
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
