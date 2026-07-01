#!/usr/bin/env python3
"""Materialize PocketMD Lite operator intake from raw top-k refinement rows."""

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

from materialize_pocketmd_lite_topk_survival_report import (  # noqa: E402
    PLACEHOLDER_PROVENANCE_PREFIXES,
    PLACEHOLDER_SOURCE_TEXT_MARKERS,
    REQUIRED_CASE_FIELDS,
    SOURCE_CHECKSUM_PATTERN,
    TOP_K_RANK_PREFIX_POLICY,
    TOPK_ROW_QUALITY_CRITERIA,
)
from release_evidence_metadata import file_sha256, release_evidence_metadata  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "pocketmd_lite_operator_intake.json"
SCHEMA_VERSION = "pocketmd-lite-operator-intake.v1"
SUPPORTED_ROW_FORMATS = ("csv", "tsv", "json", "jsonl", "ndjson")
DEFAULT_MAX_TOP_K = 20
UNCERTAINTY_FLAT_FIELDS = ("uncertainty_low", "uncertainty_high", "uncertainty_unit")


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    token = str(value).strip()
    if not token:
        return None
    try:
        return float(token)
    except ValueError:
        return None


def _integer(value: Any) -> int | None:
    parsed = _number(value)
    if parsed is None or not parsed.is_integer():
        return None
    return int(parsed)


def _boolean(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    token = str(value or "").strip().lower()
    if token in {"1", "true", "t", "yes", "y"}:
        return True
    if token in {"0", "false", "f", "no", "n"}:
        return False
    return None


def _rate(value: Any) -> float | None:
    parsed = _number(value)
    if parsed is None or parsed < 0.0 or parsed > 1.0:
        return None
    return parsed


def _contains_marker(value: str, markers: tuple[str, ...]) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in markers)


def _has_placeholder_provenance_prefix(value: str) -> bool:
    lowered = value.lower()
    return any(lowered.startswith(prefix) for prefix in PLACEHOLDER_PROVENANCE_PREFIXES)


def _is_repeated_placeholder_checksum(value: str) -> bool:
    if not SOURCE_CHECKSUM_PATTERN.fullmatch(value):
        return False
    digest = value.split(":", 1)[1].lower()
    return len(set(digest)) == 1


def _read_delimited_rows(path: Path, *, delimiter: str) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        return [dict(row) for row in reader]


def _flat_rows_from_json(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ("cases", "rows", "top_k_refinement_rows"):
            rows = _as_list(payload.get(key))
            if rows:
                return [row for row in rows if isinstance(row, dict)]
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    raise ValueError("json_input_must_be_cases_rows_or_rows_list")


def _read_json_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _flat_rows_from_json(payload)


def _read_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        token = line.strip()
        if not token:
            continue
        row = json.loads(token)
        if not isinstance(row, dict):
            raise ValueError(f"line_{line_number}:jsonl_row_must_be_object")
        rows.append(row)
    return rows


def _read_source_rows(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return _read_json_rows(path)
    if suffix in {".jsonl", ".ndjson"}:
        return _read_jsonl_rows(path)
    if suffix == ".tsv":
        return _read_delimited_rows(path, delimiter="\t")
    if suffix == ".csv":
        return _read_delimited_rows(path, delimiter=",")
    raise ValueError(
        "unsupported_pocketmd_lite_row_format:"
        f"{suffix or '<none>'}; expected one of {', '.join(SUPPORTED_ROW_FORMATS)}"
    )


def _required_string(raw_row: dict[str, Any], *, field: str, row_index: int) -> str:
    if field not in raw_row:
        raise ValueError(f"row_{row_index}:missing_required_field:{field}")
    value = _string(raw_row.get(field))
    if not value:
        raise ValueError(f"row_{row_index}:{field}_blank")
    return value


def _required_number(raw_row: dict[str, Any], *, field: str, row_index: int) -> float:
    if field not in raw_row:
        raise ValueError(f"row_{row_index}:missing_required_field:{field}")
    value = _number(raw_row.get(field))
    if value is None:
        raise ValueError(f"row_{row_index}:{field}_invalid")
    return value


def _required_integer(
    raw_row: dict[str, Any],
    *,
    field: str,
    row_index: int,
    minimum: int | None = None,
) -> int:
    if field not in raw_row:
        raise ValueError(f"row_{row_index}:missing_required_field:{field}")
    value = _integer(raw_row.get(field))
    if value is None or (minimum is not None and value < minimum):
        raise ValueError(f"row_{row_index}:{field}_invalid")
    return value


def _required_boolean(raw_row: dict[str, Any], *, field: str, row_index: int) -> bool:
    if field not in raw_row:
        raise ValueError(f"row_{row_index}:missing_required_field:{field}")
    value = _boolean(raw_row.get(field))
    if value is None:
        raise ValueError(f"row_{row_index}:{field}_invalid")
    return value


def _required_rate(raw_row: dict[str, Any], *, field: str, row_index: int) -> float:
    if field not in raw_row:
        raise ValueError(f"row_{row_index}:missing_required_field:{field}")
    value = _rate(raw_row.get(field))
    if value is None:
        raise ValueError(f"row_{row_index}:{field}_invalid")
    return value


def _parsed_interval_value(value: Any, *, row_index: int) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    token = value.strip()
    if not token:
        return None
    try:
        parsed = json.loads(token)
    except json.JSONDecodeError as exc:
        raise ValueError(f"row_{row_index}:uncertainty_interval_invalid_json") from exc
    if not isinstance(parsed, dict):
        return None
    return parsed


def _uncertainty_interval(raw_row: dict[str, Any], *, row_index: int) -> dict[str, Any]:
    interval = None
    if "uncertainty_interval" in raw_row and _string(raw_row.get("uncertainty_interval")):
        interval = _parsed_interval_value(raw_row.get("uncertainty_interval"), row_index=row_index)
    if interval is None and {
        "uncertainty_low",
        "uncertainty_high",
    }.issubset(raw_row):
        interval = {
            "low": raw_row.get("uncertainty_low"),
            "high": raw_row.get("uncertainty_high"),
            "unit": raw_row.get("uncertainty_unit") or "energy_proxy_delta",
        }
    if interval is None:
        raise ValueError(
            f"row_{row_index}:missing_required_field:"
            "uncertainty_interval_or_uncertainty_low_high"
        )

    low = _number(interval.get("low"))
    high = _number(interval.get("high"))
    unit = _string(interval.get("unit") or "energy_proxy_delta")
    if low is None or high is None or high < low:
        raise ValueError(f"row_{row_index}:uncertainty_interval_invalid")
    if not unit:
        raise ValueError(f"row_{row_index}:uncertainty_unit_blank")
    return {"low": low, "high": high, "unit": unit}


def _normalize_row(
    raw_row: dict[str, Any],
    *,
    row_index: int,
    max_top_k: int,
) -> dict[str, Any]:
    case_id = _required_string(raw_row, field="case_id", row_index=row_index)
    source_family = _required_string(raw_row, field="source_family", row_index=row_index)
    candidate_id = _required_string(raw_row, field="candidate_id", row_index=row_index)
    provenance_ref = _required_string(raw_row, field="provenance_ref", row_index=row_index)
    source_checksum = _required_string(raw_row, field="source_checksum", row_index=row_index)
    if not SOURCE_CHECKSUM_PATTERN.fullmatch(source_checksum):
        raise ValueError(f"row_{row_index}:{case_id}:source_checksum_invalid")
    if _is_repeated_placeholder_checksum(source_checksum):
        raise ValueError(f"row_{row_index}:{case_id}:source_checksum_placeholder_digest")
    if (
        _has_placeholder_provenance_prefix(provenance_ref)
        or _contains_marker(provenance_ref, PLACEHOLDER_SOURCE_TEXT_MARKERS)
    ):
        raise ValueError(f"row_{row_index}:{case_id}:provenance_ref_placeholder")

    top_k_rank = _required_integer(
        raw_row,
        field="top_k_rank",
        row_index=row_index,
        minimum=1,
    )
    if top_k_rank > max_top_k:
        raise ValueError(
            f"row_{row_index}:{case_id}:top_k_rank_exceeds_max:{max_top_k}"
        )

    clash_before = _required_integer(
        raw_row,
        field="clash_count_before",
        row_index=row_index,
        minimum=0,
    )
    clash_after = _required_integer(
        raw_row,
        field="clash_count_after",
        row_index=row_index,
        minimum=0,
    )

    return {
        "case_id": case_id,
        "source_family": source_family,
        "top_k_rank": top_k_rank,
        "candidate_id": candidate_id,
        "pre_refinement_energy_proxy": _required_number(
            raw_row,
            field="pre_refinement_energy_proxy",
            row_index=row_index,
        ),
        "post_refinement_energy_proxy": _required_number(
            raw_row,
            field="post_refinement_energy_proxy",
            row_index=row_index,
        ),
        "local_min_survived": _required_boolean(
            raw_row,
            field="local_min_survived",
            row_index=row_index,
        ),
        "contact_persistence_rate": _required_rate(
            raw_row,
            field="contact_persistence_rate",
            row_index=row_index,
        ),
        "h_bond_persistence_rate": _required_rate(
            raw_row,
            field="h_bond_persistence_rate",
            row_index=row_index,
        ),
        "clash_count_before": clash_before,
        "clash_count_after": clash_after,
        "uncertainty_interval": _uncertainty_interval(raw_row, row_index=row_index),
        "provenance_ref": provenance_ref,
        "source_checksum": source_checksum,
    }


def _validate_topk_integrity(rows: list[dict[str, Any]]) -> None:
    ranks_by_case: set[tuple[str, int]] = set()
    candidates_by_case: set[tuple[str, str]] = set()
    ranks_for_case: dict[str, set[int]] = {}
    for row in rows:
        case_id = str(row["case_id"])
        top_k_rank = int(row["top_k_rank"])
        candidate_id = str(row["candidate_id"])
        ranks_for_case.setdefault(case_id, set()).add(top_k_rank)
        rank_key = (case_id, top_k_rank)
        if rank_key in ranks_by_case:
            raise ValueError(f"{case_id}:top_k_rank_{top_k_rank}_duplicate")
        ranks_by_case.add(rank_key)
        candidate_key = (case_id, candidate_id)
        if candidate_key in candidates_by_case:
            raise ValueError(f"{case_id}:candidate_id_{candidate_id}_duplicate")
        candidates_by_case.add(candidate_key)
    for case_id, ranks in sorted(ranks_for_case.items()):
        expected_prefix = set(range(1, max(ranks) + 1))
        missing = sorted(expected_prefix - ranks)
        if missing:
            missing_text = ",".join(str(rank) for rank in missing)
            raise ValueError(f"{case_id}:top_k_rank_prefix_gap:{missing_text}")


def _topk_rank_prefixes(rows: list[dict[str, Any]]) -> dict[str, list[int]]:
    case_ids = sorted({str(row["case_id"]) for row in rows})
    return {
        case_id: sorted(
            {int(row["top_k_rank"]) for row in rows if row["case_id"] == case_id}
        )
        for case_id in case_ids
    }


def build_pocketmd_lite_operator_intake_from_rows(
    *,
    rows_path: Path,
    repo_root: Path = ROOT,
    source_id: str = "",
    source_url: str = "",
    source_license: str = "",
    source_version: str = "",
    max_top_k: int = DEFAULT_MAX_TOP_K,
) -> dict[str, Any]:
    if max_top_k < 1:
        raise ValueError("max_top_k_must_be_positive")
    resolved_rows_path = rows_path if rows_path.is_absolute() else repo_root / rows_path
    flat_rows = _read_source_rows(resolved_rows_path)
    if not flat_rows:
        raise ValueError("pocketmd_lite_rows_required")

    cases = [
        _normalize_row(raw_row, row_index=index, max_top_k=max_top_k)
        for index, raw_row in enumerate(flat_rows, start=1)
    ]
    _validate_topk_integrity(cases)
    case_ids = sorted({str(row["case_id"]) for row in cases})
    case_row_counts = {
        case_id: sum(1 for row in cases if row["case_id"] == case_id)
        for case_id in case_ids
    }

    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/materialize_pocketmd_lite_operator_intake_from_rows.py"),
                rows_path,
            ],
            reused_evidence=False,
            reuse_policy="pocketmd_lite_operator_intake_materialized_from_raw_topk_refinement_rows",
            repo_root=repo_root,
        ),
        "cases": cases,
        "operator_input_source": {
            "mode": "raw_top_k_refinement_rows",
            "source_artifact": str(rows_path),
            "source_artifact_sha256": file_sha256(resolved_rows_path),
            "source_id": source_id,
            "source_url": source_url,
            "source_license": source_license,
            "source_version": source_version,
            "supported_source_formats": list(SUPPORTED_ROW_FORMATS),
            "required_case_fields": list(REQUIRED_CASE_FIELDS),
            "flat_uncertainty_fields": list(UNCERTAINTY_FLAT_FIELDS),
            "row_count": len(flat_rows),
            "case_count": len(case_ids),
            "top_k_candidate_count": len(cases),
            "max_top_k": max_top_k,
            "case_row_counts": case_row_counts,
            "top_k_rank_prefix_policy": TOP_K_RANK_PREFIX_POLICY,
            "case_top_k_rank_prefixes": _topk_rank_prefixes(cases),
            "top_k_row_quality_minimums": dict(TOPK_ROW_QUALITY_CRITERIA),
        },
        "claim_boundary": (
            "Operator intake materialized from bounded top-k refinement rows. The "
            "PocketMD Lite survival materializer must still pass Phase 4 before the "
            "bounded top-k refinement surface is ready; broad all-atom MD and FEP "
            "claims remain locked."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument(
        "--rows",
        type=Path,
        required=True,
        help="CSV, TSV, JSON, JSONL, or NDJSON top-k refinement rows.",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--source-id", default="")
    parser.add_argument("--source-url", default="")
    parser.add_argument("--source-license", default="")
    parser.add_argument("--source-version", default="")
    parser.add_argument("--max-top-k", type=int, default=DEFAULT_MAX_TOP_K)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = build_pocketmd_lite_operator_intake_from_rows(
            rows_path=args.rows,
            repo_root=args.repo_root,
            source_id=args.source_id,
            source_url=args.source_url,
            source_license=args.source_license,
            source_version=args.source_version,
            max_top_k=args.max_top_k,
        )
    except Exception as exc:
        print(f"pocketmd-lite-operator-intake-from-rows: blocked | {exc}", file=sys.stderr)
        return 2
    out = args.out if args.out.is_absolute() else args.repo_root / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_json_text(payload), encoding="utf-8")
    source = payload["operator_input_source"]
    print(
        "pocketmd-lite-operator-intake-from-rows: ready | "
        f"cases={source['case_count']} | rows={source['top_k_candidate_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
