#!/usr/bin/env python3
"""Validate public benchmark license, checksum, and provenance receipts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any


SCHEMA_VERSION = "public-benchmark-external-receipt-validation.v1"
REQUIRED_RECEIPT_FIELDS = (
    "source_license_or_accession",
    "source_checksum",
    "provenance_ref",
)
REQUIRED_SUBSET_RECEIPT_FIELDS = (
    *REQUIRED_RECEIPT_FIELDS,
    "source_file_checksums",
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string(value: Any) -> str:
    return str(value or "").strip()


def _is_sha256_ref(value: Any) -> bool:
    return bool(re.fullmatch(r"sha256:[0-9a-fA-F]{64}", _string(value)))


def _receipt_blockers(
    row: dict[str, Any],
    *,
    row_key: str,
    required_fields: tuple[str, ...],
) -> list[str]:
    blockers: list[str] = []
    for field in required_fields:
        if field not in row:
            blockers.append(f"{row_key}:{field}_missing")
            continue
        if field == "source_file_checksums":
            checksums = _as_dict(row.get(field))
            if not checksums:
                blockers.append(f"{row_key}:{field}_missing")
                continue
            for checksum_index, (path_key, checksum) in enumerate(checksums.items()):
                if not _string(path_key):
                    blockers.append(
                        f"{row_key}:source_file_checksum_{checksum_index}_path_missing"
                    )
                if not _is_sha256_ref(checksum):
                    blockers.append(
                        f"{row_key}:source_file_checksum_{checksum_index}_invalid"
                    )
            continue
        if not _string(row.get(field)):
            blockers.append(f"{row_key}:{field}_blank")
    checksum = row.get("source_checksum")
    if checksum not in (None, "") and not _is_sha256_ref(checksum):
        blockers.append(f"{row_key}:source_checksum_invalid")
    return blockers


def _row_key(prefix: str, row: dict[str, Any], index: int) -> str:
    row_id = (
        _string(row.get("case_id"))
        or _string(row.get("target_id"))
        or f"row_{index + 1}"
    )
    return f"{prefix}:{row_id}"


def validate_external_receipts(
    *,
    subset_manifest: dict[str, Any],
    enrichment_scorecard: dict[str, Any],
    vina_gnina_comparison_adapter: dict[str, Any],
) -> dict[str, Any]:
    receipt_rows: list[dict[str, Any]] = []

    for index, row in enumerate(_as_list(subset_manifest.get("case_rows"))):
        if not isinstance(row, dict):
            continue
        row_key = _row_key("subset_manifest", row, index)
        blockers = _receipt_blockers(
            row,
            row_key=row_key,
            required_fields=REQUIRED_SUBSET_RECEIPT_FIELDS,
        )
        receipt_rows.append(
            {
                "artifact_role": "casf_pdbbind_subset_manifest",
                "row_key": row_key,
                "status": "pass" if not blockers else "blocked",
                "contract_pass": not blockers,
                "required_receipt_fields": list(REQUIRED_SUBSET_RECEIPT_FIELDS),
                "blockers": blockers,
            }
        )

    for index, row in enumerate(_as_list(enrichment_scorecard.get("target_rows"))):
        if not isinstance(row, dict):
            continue
        row_key = _row_key("enrichment_scorecard", row, index)
        blockers = _receipt_blockers(
            row,
            row_key=row_key,
            required_fields=REQUIRED_RECEIPT_FIELDS,
        )
        receipt_rows.append(
            {
                "artifact_role": "dud_e_lit_pcba_enrichment_scorecard",
                "row_key": row_key,
                "status": "pass" if not blockers else "blocked",
                "contract_pass": not blockers,
                "required_receipt_fields": list(REQUIRED_RECEIPT_FIELDS),
                "blockers": blockers,
            }
        )

    for index, row in enumerate(
        _as_list(vina_gnina_comparison_adapter.get("case_rows"))
    ):
        if not isinstance(row, dict):
            continue
        row_key = _row_key("vina_gnina_comparison_adapter", row, index)
        blockers = _receipt_blockers(
            row,
            row_key=row_key,
            required_fields=REQUIRED_RECEIPT_FIELDS,
        )
        receipt_rows.append(
            {
                "artifact_role": "vina_gnina_comparison_adapter",
                "row_key": row_key,
                "status": "pass" if not blockers else "blocked",
                "contract_pass": not blockers,
                "required_receipt_fields": list(REQUIRED_RECEIPT_FIELDS),
                "blockers": blockers,
            }
        )

    blockers = [
        blocker
        for row in receipt_rows
        for blocker in _as_list(row.get("blockers"))
    ]
    if not receipt_rows:
        blockers.append("public_benchmark_external_receipts_missing")
    ready = bool(receipt_rows and not blockers)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ready" if ready else "operator_receipts_required",
        "contract_pass": True,
        "public_benchmark_external_receipts_ready": ready,
        "materialized_row_count": len(receipt_rows),
        "receipt_complete_row_count": sum(
            1 for row in receipt_rows if row["contract_pass"]
        ),
        "receipt_blocked_row_count": sum(
            1 for row in receipt_rows if not row["contract_pass"]
        ),
        "required_receipt_fields": list(REQUIRED_RECEIPT_FIELDS),
        "required_subset_receipt_fields": list(REQUIRED_SUBSET_RECEIPT_FIELDS),
        "receipt_rows": receipt_rows,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "claim_boundary": (
            "This validator checks operator-attached license/accession, checksum, "
            "and provenance receipt fields already present in materialized benchmark "
            "rows. It does not fetch public data, approve licenses, or claim Tier beta "
            "without materialized benchmark evidence."
        ),
    }


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subset-manifest", type=Path, required=True)
    parser.add_argument("--enrichment-scorecard", type=Path, required=True)
    parser.add_argument("--vina-gnina-comparison-adapter", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--fail-blocked", action="store_true")
    args = parser.parse_args(argv)

    result = validate_external_receipts(
        subset_manifest=_load_json(args.subset_manifest),
        enrichment_scorecard=_load_json(args.enrichment_scorecard),
        vina_gnina_comparison_adapter=_load_json(args.vina_gnina_comparison_adapter),
    )
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(_json_text(result), encoding="utf-8")
    print(
        "public-benchmark-external-receipts: "
        f"{result['status']} | receipts={result['receipt_complete_row_count']}/"
        f"{result['materialized_row_count']} | blockers={result['blocker_count']}"
    )
    return (
        1
        if args.fail_blocked
        and not result["public_benchmark_external_receipts_ready"]
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
