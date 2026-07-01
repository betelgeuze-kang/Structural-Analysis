#!/usr/bin/env python3
"""Materialize a GPCR hard-decoy operator template from raw ranking rows."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from materialize_gpcr_hard_decoy_suite_report import (  # noqa: E402
    PLACEHOLDER_SOURCE_TEXT_MARKERS,
    RAW_RANKING_ROW_FIELDS,
    REQUIRED_TARGETS,
)
from release_evidence_metadata import file_sha256, release_evidence_metadata  # noqa: E402


DEFAULT_OUT = Path(
    "implementation/phase1/release_evidence/productization/"
    "gpcr_hard_decoy_operator_template.json"
)
SCHEMA_VERSION = "gpcr-hard-decoy-operator-intake.v1"
SUPPORTED_ROW_FORMATS = ("csv", "tsv", "json", "jsonl", "ndjson")
DEFAULT_SCORE_DIRECTION = "higher_is_better"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _target_key(value: Any) -> str:
    return str(value or "").strip().upper()


def _bool_value(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    token = str(value or "").strip().lower()
    if token in {"1", "true", "t", "yes", "y"}:
        return True
    if token in {"0", "false", "f", "no", "n"}:
        return False
    return None


def _score_value(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    token = str(value).strip()
    if not token:
        return None
    try:
        parsed = float(token)
        return parsed if math.isfinite(parsed) else None
    except ValueError:
        return None


def _score_direction(value: Any) -> str:
    token = str(value or "").strip().lower()
    if token in {"", "higher", "higher_is_better", "descending"}:
        return "higher_is_better"
    if token in {"lower", "lower_is_better", "ascending"}:
        return "lower_is_better"
    return token


def _contains_marker(value: str, markers: tuple[str, ...]) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in markers)


def _raw_rows_from_target(row: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("hard_decoy_rows", "ranking_rows", "scored_molecules"):
        rows = _as_list(row.get(key))
        if rows:
            return [item for item in rows if isinstance(item, dict)]
    return []


def _flat_rows_from_json(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("targets"), list):
        flat_rows: list[dict[str, Any]] = []
        for target in payload["targets"]:
            if not isinstance(target, dict):
                continue
            target_id = _target_key(target.get("target_id") or target.get("target"))
            score_direction = target.get("score_direction")
            for raw_row in _raw_rows_from_target(target):
                flat_rows.append(
                    {
                        **raw_row,
                        "target_id": target_id,
                        "score_direction": score_direction,
                    }
                )
        return flat_rows
    if isinstance(payload, dict) and isinstance(payload.get("rows"), list):
        return [row for row in payload["rows"] if isinstance(row, dict)]
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    raise ValueError("json_input_must_be_rows_list_or_targets_payload")


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


def _read_delimited_rows(path: Path, *, delimiter: str) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        return [dict(row) for row in reader]


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
        "unsupported_gpcr_hard_decoy_row_format:"
        f"{suffix or '<none>'}; expected one of {', '.join(SUPPORTED_ROW_FORMATS)}"
    )


def _normalize_flat_row(raw_row: dict[str, Any], *, row_index: int) -> tuple[str, str, dict[str, Any]]:
    target_id = _target_key(raw_row.get("target_id") or raw_row.get("target"))
    if not target_id:
        raise ValueError(f"row_{row_index}:target_id_required")
    missing = [
        field for field in RAW_RANKING_ROW_FIELDS if field not in raw_row
    ]
    if missing:
        raise ValueError(f"row_{row_index}:missing_required_fields:{','.join(missing)}")
    molecule_id = str(raw_row.get("molecule_id") or "").strip()
    if not molecule_id:
        raise ValueError(f"row_{row_index}:molecule_id_required")
    if _contains_marker(molecule_id, PLACEHOLDER_SOURCE_TEXT_MARKERS):
        raise ValueError(f"row_{row_index}:{molecule_id}:molecule_id_placeholder")
    score = _score_value(raw_row.get("score"))
    if score is None:
        raise ValueError(f"row_{row_index}:{molecule_id}:score_invalid")
    is_positive = _bool_value(raw_row.get("is_positive"))
    if is_positive is None:
        raise ValueError(f"row_{row_index}:{molecule_id}:is_positive_invalid")
    is_decoy = _bool_value(raw_row.get("is_decoy"))
    if is_decoy is None:
        raise ValueError(f"row_{row_index}:{molecule_id}:is_decoy_invalid")
    if is_positive is is_decoy:
        raise ValueError(f"row_{row_index}:{molecule_id}:positive_decoy_label_invalid")
    score_direction = _score_direction(raw_row.get("score_direction"))
    if score_direction not in {"higher_is_better", "lower_is_better"}:
        raise ValueError(f"row_{row_index}:{target_id}:score_direction_invalid")
    return target_id, score_direction, {
        "molecule_id": molecule_id,
        "score": score,
        "is_positive": is_positive,
        "is_decoy": is_decoy,
    }


def build_gpcr_hard_decoy_operator_template_from_rows(
    *,
    rows_path: Path,
    repo_root: Path = ROOT,
    source_id: str = "",
    source_url: str = "",
    source_license: str = "",
    source_version: str = "",
    allow_missing_targets: bool = False,
) -> dict[str, Any]:
    resolved_rows_path = rows_path if rows_path.is_absolute() else repo_root / rows_path
    flat_rows = _read_source_rows(resolved_rows_path)
    rows_by_target: dict[str, list[dict[str, Any]]] = {target_id: [] for target_id in REQUIRED_TARGETS}
    score_direction_by_target: dict[str, str] = {}
    molecule_ids_by_target: dict[str, set[str]] = {
        target_id: set() for target_id in REQUIRED_TARGETS
    }
    unexpected_targets: list[str] = []
    for index, raw_row in enumerate(flat_rows, start=1):
        target_id, score_direction, normalized_row = _normalize_flat_row(
            raw_row,
            row_index=index,
        )
        if target_id not in rows_by_target:
            unexpected_targets.append(target_id)
            continue
        previous_direction = score_direction_by_target.get(target_id)
        if previous_direction and previous_direction != score_direction:
            raise ValueError(f"{target_id}:mixed_score_direction_values")
        score_direction_by_target[target_id] = score_direction
        molecule_id = str(normalized_row["molecule_id"])
        if molecule_id in molecule_ids_by_target[target_id]:
            raise ValueError(f"{target_id}:{molecule_id}:molecule_id_duplicate")
        molecule_ids_by_target[target_id].add(molecule_id)
        rows_by_target[target_id].append(normalized_row)

    missing_targets = [
        target_id for target_id, target_rows in rows_by_target.items() if not target_rows
    ]
    if missing_targets and not allow_missing_targets:
        raise ValueError(
            "missing_required_gpcr_targets:" + ",".join(missing_targets)
        )

    targets = []
    for target_id in REQUIRED_TARGETS:
        target_rows = rows_by_target[target_id]
        targets.append(
            {
                "target_id": target_id,
                "ranking_pr_auc_ci_low": None,
                "top20_hit_rate": None,
                "decoys_above_positive_count": None,
                "positive_out_anchored_by_top_decoys": None,
                "score_direction": (
                    score_direction_by_target.get(target_id)
                    if target_rows
                    else None
                ),
                "hard_decoy_rows": target_rows or None,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/materialize_gpcr_hard_decoy_operator_template_from_rows.py"),
                rows_path,
            ],
            reused_evidence=False,
            reuse_policy="gpcr_hard_decoy_operator_template_materialized_from_raw_ranking_rows",
            repo_root=repo_root,
        ),
        "required_targets": list(REQUIRED_TARGETS),
        "targets": targets,
        "operator_input_source": {
            "mode": "raw_hard_decoy_rows",
            "source_artifact": str(rows_path),
            "source_artifact_sha256": file_sha256(resolved_rows_path),
            "source_id": source_id,
            "source_url": source_url,
            "source_license": source_license,
            "source_version": source_version,
            "supported_source_formats": list(SUPPORTED_ROW_FORMATS),
            "required_row_fields": list(RAW_RANKING_ROW_FIELDS),
            "row_count": len(flat_rows),
            "accepted_target_row_count": sum(len(rows) for rows in rows_by_target.values()),
            "unexpected_targets": sorted(set(unexpected_targets)),
            "missing_targets": missing_targets,
            "target_row_counts": {
                target_id: len(rows_by_target[target_id])
                for target_id in REQUIRED_TARGETS
            },
            "score_direction_by_target": {
                target_id: score_direction_by_target[target_id]
                for target_id in REQUIRED_TARGETS
                if target_id in score_direction_by_target
            },
        },
        "claim_boundary": (
            "Operator intake template materialized from raw hard-decoy ranking rows. "
            "The GPCR suite materializer must still compute metrics and pass all Phase 3 "
            "exit criteria before broad GPCR claims are safe."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument(
        "--rows",
        type=Path,
        required=True,
        help="CSV, TSV, JSON, JSONL, or NDJSON raw ranking rows.",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--source-id", default="")
    parser.add_argument("--source-url", default="")
    parser.add_argument("--source-license", default="")
    parser.add_argument("--source-version", default="")
    parser.add_argument(
        "--allow-missing-targets",
        action="store_true",
        help="Write null target slots instead of failing when DRD2/HTR2A/OPRM1 rows are incomplete.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = build_gpcr_hard_decoy_operator_template_from_rows(
            rows_path=args.rows,
            repo_root=args.repo_root,
            source_id=args.source_id,
            source_url=args.source_url,
            source_license=args.source_license,
            source_version=args.source_version,
            allow_missing_targets=args.allow_missing_targets,
        )
    except Exception as exc:
        print(f"gpcr-hard-decoy-operator-template-from-rows: blocked | {exc}", file=sys.stderr)
        return 2
    out = args.out if args.out.is_absolute() else args.repo_root / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_json_text(payload), encoding="utf-8")
    source = payload["operator_input_source"]
    print(
        "gpcr-hard-decoy-operator-template-from-rows: ready | "
        f"rows={source['accepted_target_row_count']} | "
        f"missing_targets={len(source['missing_targets'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
