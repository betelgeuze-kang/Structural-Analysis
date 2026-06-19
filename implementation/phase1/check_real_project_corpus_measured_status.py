#!/usr/bin/env python3
"""Check measured real-project corpus exit criteria without overstating raw evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from release_evidence_metadata import release_evidence_metadata  # noqa: E402


SCHEMA_VERSION = "real-project-corpus-measured-status.v1"
DEFAULT_ROW_PROVENANCE = Path("implementation/phase1/real_project_row_provenance_report.json")
DEFAULT_PEER_METRIC_RECORDS = Path("implementation/phase1/peer_tbi_benchmark_metric_records.json")
DEFAULT_OUT = Path("implementation/phase1/real_project_corpus_measured_status.json")
REQUIRED_PEER_GROUPS = {"period", "base_shear", "story_drift", "nonlinear_response", "citation"}
SHA256_HEX_RE = re.compile(r"^[0-9a-fA-F]{64}$")
WITHHELD_REASON_PREFIXES = (
    "withheld_",
    "raw_",
    "validation_",
    "trace_",
    "no_raw_",
)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _value_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _checksum_or_withheld_valid(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if SHA256_HEX_RE.match(text):
        return True
    return text.startswith(WITHHELD_REASON_PREFIXES)


def _measured_parser_contract_valid(row: dict[str, Any]) -> bool:
    parser_contract = _as_dict(row.get("parser_contract"))
    return (
        parser_contract.get("measured_local_artifact") is True
        and bool(str(parser_contract.get("format", "") or "").strip())
        and bool(str(parser_contract.get("source_file", "") or "").strip())
        and int(parser_contract.get("byte_count", 0) or 0) > 0
    )


def build_status(
    *,
    row_provenance_path: Path = DEFAULT_ROW_PROVENANCE,
    peer_metric_records_path: Path = DEFAULT_PEER_METRIC_RECORDS,
    min_measured_rows: int = 10,
    min_measured_formats: int = 2,
) -> dict[str, Any]:
    row_provenance = _load_json(row_provenance_path)
    peer_metric_records = _load_json(peer_metric_records_path)
    provenance_rows = [
        row for row in _as_list(row_provenance.get("source_provenance_rows")) if isinstance(row, dict)
    ]
    measured_rows = [
        row
        for row in provenance_rows
        if str(row.get("artifact_status", "")) == "measured_local_artifact_attached"
    ]
    measured_formats = sorted(
        {
            str(_as_dict(row.get("parser_contract")).get("format", "") or "")
            for row in measured_rows
            if str(_as_dict(row.get("parser_contract")).get("format", "") or "")
        }
    )
    measured_stable_pointers = [
        str(row.get("stable_row_pointer", "") or "").strip() for row in measured_rows
    ]
    duplicate_measured_stable_pointers = sorted(
        {
            pointer
            for pointer in measured_stable_pointers
            if pointer and measured_stable_pointers.count(pointer) > 1
        }
    )
    peer_rows = [
        row for row in _as_list(peer_metric_records.get("metric_records")) if isinstance(row, dict)
    ]
    peer_groups_with_value = sorted(
        {
            str(row.get("metric_group", ""))
            for row in peer_rows
            if str(row.get("metric_group", "")) in REQUIRED_PEER_GROUPS and _value_present(row.get("value"))
        }
    )
    peer_official_reference_truth_groups = sorted(
        {
            str(row.get("metric_group", ""))
            for row in peer_rows
            if str(row.get("metric_group", "")) in REQUIRED_PEER_GROUPS
            and _value_present(row.get("value"))
            and str(row.get("reference_truth_status", "")) == "official_public_report_metric"
        }
    )
    peer_measured_bridge_groups = sorted(
        {
            str(row.get("metric_group", ""))
            for row in peer_rows
            if str(row.get("metric_group", "")) in REQUIRED_PEER_GROUPS
            and _value_present(row.get("value"))
            and str(row.get("reference_truth_status", ""))
            == "measured_run_kpi_bridge_not_external_reference_truth"
        }
    )
    checks = {
        "measured_provenance_rows_pass": len(measured_rows) >= min_measured_rows,
        "koneps_measured_format_count_pass": len(measured_formats) >= min_measured_formats,
        "peer_metric_bearing_groups_pass": REQUIRED_PEER_GROUPS <= set(peer_groups_with_value),
        "checksum_or_withheld_coverage_pass": all(
            _checksum_or_withheld_valid(row.get("checksum_status_or_withheld_reason"))
            for row in measured_rows
        ),
        "stable_row_pointer_coverage_pass": all(
            bool(str(row.get("stable_row_pointer", "") or "")) for row in measured_rows
        ),
        "stable_row_pointer_unique_pass": not duplicate_measured_stable_pointers,
        "manual_review_status_coverage_pass": all(
            bool(str(row.get("manual_review_status", "") or "")) for row in measured_rows
        ),
        "release_eligibility_coverage_pass": all(
            bool(str(row.get("release_eligibility", "") or "")) for row in measured_rows
        ),
        "measured_parser_contract_pass": all(_measured_parser_contract_valid(row) for row in measured_rows),
        "raw_redistribution_blocked_pass": all(row.get("release_surface_allowed") is False for row in measured_rows),
    }
    blockers = [key for key, passed in checks.items() if not passed]
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[row_provenance_path, peer_metric_records_path],
            reused_evidence=True,
            reuse_policy="status_rebuilt_from_existing_row_provenance_and_peer_metric_receipts",
            repo_root=REPO_ROOT,
        ),
        "contract_pass": not blockers,
        "reason_code": "PASS" if not blockers else "ERR_REAL_PROJECT_CORPUS_MEASURED_INCOMPLETE",
        "row_provenance_report": str(row_provenance_path),
        "peer_metric_records": str(peer_metric_records_path),
        "summary": {
            "measured_artifact_row_count": len(measured_rows),
            "min_measured_artifact_rows": min_measured_rows,
            "measured_file_format_count": len(measured_formats),
            "min_measured_file_formats": min_measured_formats,
            "measured_file_formats": measured_formats,
            "measured_parser_contract_valid_count": sum(
                1 for row in measured_rows if _measured_parser_contract_valid(row)
            ),
            "duplicate_measured_stable_pointers": duplicate_measured_stable_pointers,
            "peer_metric_group_count": len(REQUIRED_PEER_GROUPS),
            "peer_metric_groups_with_value_count": len(peer_groups_with_value),
            "peer_metric_groups_with_value": peer_groups_with_value,
            "peer_official_reference_truth_group_count": len(peer_official_reference_truth_groups),
            "peer_official_reference_truth_groups": peer_official_reference_truth_groups,
            "peer_measured_run_kpi_bridge_group_count": len(peer_measured_bridge_groups),
            "peer_measured_run_kpi_bridge_groups": peer_measured_bridge_groups,
            "raw_redistribution_allowed_count": sum(1 for row in measured_rows if row.get("release_surface_allowed")),
        },
        "checks": checks,
        "blockers": blockers,
        "claim_boundary": (
            "This status checks measured corpus evidence and release-readiness metadata. PASS means the "
            "initial measured-corpus row/value metadata is present; it does not turn local or public "
            "source artifacts into redistributable customer data, close external V&V, or treat measured-run "
            "KPI bridge rows as third-party reference truth."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--row-provenance", type=Path, default=DEFAULT_ROW_PROVENANCE)
    parser.add_argument("--peer-metric-records", type=Path, default=DEFAULT_PEER_METRIC_RECORDS)
    parser.add_argument("--min-measured-rows", type=int, default=10)
    parser.add_argument("--min-measured-formats", type=int, default=2)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--no-write", action="store_true", help="Print the status without writing --out.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    args = parser.parse_args(argv)

    payload = build_status(
        row_provenance_path=args.row_provenance,
        peer_metric_records_path=args.peer_metric_records,
        min_measured_rows=args.min_measured_rows,
        min_measured_formats=args.min_measured_formats,
    )
    if not args.no_write:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        summary = payload["summary"]
        print(
            "real-project-corpus-measured: "
            f"{'PASS' if payload['contract_pass'] else 'BLOCKED'} | "
            f"rows={summary['measured_artifact_row_count']}/{summary['min_measured_artifact_rows']} | "
            f"formats={summary['measured_file_format_count']}/{summary['min_measured_file_formats']} | "
            f"peer_values={summary['peer_metric_groups_with_value_count']}/{summary['peer_metric_group_count']}"
        )
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
