#!/usr/bin/env python3
"""Build a public benchmark operator bundle from row files."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import release_evidence_metadata  # noqa: E402


SCHEMA_VERSION = "public-benchmark-operator-bundle-from-rows.v1"
OPERATOR_BUNDLE_SCHEMA_VERSION = "public-benchmark-operator-bundle.v1"
DEFAULT_OUT = Path("operator_public_benchmark_bundle.json")
TARGET_FIELDS = (
    "benchmark_family",
    "target_id",
    "score_direction",
    "source_license_or_accession",
    "source_checksum",
    "provenance_ref",
)
MOLECULE_FIELDS = ("molecule_id", "is_active", "score")
VINA_CASE_FIELDS = (
    "case_id",
    "source_family",
    "benchmark_split",
    "complex_id",
    "reference_pose_id",
    "source_license_or_accession",
    "source_checksum",
    "provenance_ref",
)
VINA_ENGINE_FIELDS = (
    "engine_id",
    "docking_run_id",
    "predicted_ligand_path_or_pose_ref",
    "symmetry_aware_rmsd_angstrom",
    "pose_success",
    "score",
    "score_direction",
    "pose_success_rmsd_threshold_angstrom",
)
SOURCE_RECEIPT_FIELDS = (
    "source_license_or_accession",
    "source_checksum",
    "provenance_ref",
)
POSE_SOURCE_RECEIPT_FIELDS = ("receptor_context.provenance_ref",)
SOURCE_CHECKSUM_PATTERN = re.compile(r"^sha256:[0-9a-fA-F]{64}$")
PLACEHOLDER_SOURCE_TEXT_MARKERS = (
    "<operator",
    "dry-run",
    "dummy",
    "example.invalid",
    "example://",
    "fake",
    "fixture",
    "mock",
    "operator_supplied",
    "placeholder",
    "synthetic",
    "test-accession",
    "todo",
    "unit-test",
)
PLACEHOLDER_PROVENANCE_PREFIXES = (
    "operator://",
    "local-evidence://",
    "local://",
    "fixture://",
    "mock://",
    "synthetic://",
    "placeholder://",
    "test://",
    "unit-test://",
    "file://",
)
SOURCE_ACTUALITY_POLICY = {
    "required_source_receipt_fields": list(SOURCE_RECEIPT_FIELDS),
    "required_pose_source_receipt_fields": list(POSE_SOURCE_RECEIPT_FIELDS),
    "required_vina_engine_run_pose_ref_fields": [
        "predicted_ligand_path_or_pose_ref"
    ],
    "source_checksum_policy": "sha256:<64 hex> and not a repeated placeholder digest",
    "row_file_artifact_sha256_policy": (
        "Every operator row file materialized by this importer is recorded with "
        "sha256:<64 hex> in materialization_report.row_file_artifact_receipts."
    ),
    "placeholder_markers_rejected": list(PLACEHOLDER_SOURCE_TEXT_MARKERS),
    "placeholder_provenance_prefixes_rejected": list(PLACEHOLDER_PROVENANCE_PREFIXES),
}


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _parse_scalar(value: str) -> Any:
    text = value.strip()
    if text == "":
        return ""
    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None
    if text[0:1] in {"{", "["}:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    try:
        if any(token in text for token in (".", "e", "E")):
            return float(text)
        return int(text)
    except ValueError:
        return text


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in row.items():
        if key is None:
            continue
        if isinstance(value, str):
            normalized[str(key)] = _parse_scalar(value)
        else:
            normalized[str(key)] = value
    return normalized


def _string(value: Any) -> str:
    return str(value or "").strip()


def _contains_placeholder_marker(value: Any) -> bool:
    lowered = _string(value).lower()
    return any(marker in lowered for marker in PLACEHOLDER_SOURCE_TEXT_MARKERS)


def _has_placeholder_provenance_prefix(value: Any) -> bool:
    lowered = _string(value).lower()
    return any(lowered.startswith(prefix) for prefix in PLACEHOLDER_PROVENANCE_PREFIXES)


def _is_sha256_ref(value: Any) -> bool:
    return bool(SOURCE_CHECKSUM_PATTERN.fullmatch(_string(value)))


def _is_repeated_placeholder_checksum(value: Any) -> bool:
    text = _string(value)
    if not _is_sha256_ref(text):
        return False
    digest = text.split(":", 1)[1].lower()
    return len(set(digest)) == 1


def file_sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _row_file_artifact_receipts(
    row_files: dict[str, Path],
) -> dict[str, dict[str, Any]]:
    receipts: dict[str, dict[str, Any]] = {}
    for row_input_id, path in row_files.items():
        receipts[row_input_id] = {
            "row_input_id": row_input_id,
            "path": str(path),
            "format": path.suffix.lower().lstrip(".") or "unknown",
            "source_artifact_sha256": file_sha256(path),
        }
    return receipts


def _source_receipt_actuality_blockers(
    row: dict[str, Any],
    *,
    group_id: str,
    row_key: str,
) -> list[str]:
    blockers: list[str] = []
    prefix = f"{group_id}:{row_key}"
    for field in SOURCE_RECEIPT_FIELDS:
        value = row.get(field)
        text = _string(value)
        if not text:
            blockers.append(f"{prefix}:{field}_missing")
            continue
        if _contains_placeholder_marker(text):
            blockers.append(f"{prefix}:{field}_placeholder")
        if field == "source_checksum":
            if not _is_sha256_ref(text):
                blockers.append(f"{prefix}:source_checksum_invalid")
            elif _is_repeated_placeholder_checksum(text):
                blockers.append(f"{prefix}:source_checksum_placeholder_digest")
        if field == "provenance_ref" and _has_placeholder_provenance_prefix(text):
            blockers.append(f"{prefix}:provenance_ref_placeholder")
    return blockers


def _pose_source_actuality_blockers(row: dict[str, Any], *, row_key: str) -> list[str]:
    receptor_context = row.get("receptor_context")
    provenance_ref = ""
    if isinstance(receptor_context, dict):
        provenance_ref = _string(receptor_context.get("provenance_ref"))
    blockers: list[str] = []
    prefix = f"pose_rows:{row_key}"
    if not provenance_ref:
        blockers.append(f"{prefix}:receptor_context.provenance_ref_missing")
    elif _contains_placeholder_marker(provenance_ref) or _has_placeholder_provenance_prefix(provenance_ref):
        blockers.append(f"{prefix}:receptor_context.provenance_ref_placeholder")
    return blockers


def _vina_engine_pose_ref_actuality_blockers(
    row: dict[str, Any],
    *,
    row_key: str,
) -> list[str]:
    blockers: list[str] = []
    raw_runs = row.get("engine_runs")
    if not isinstance(raw_runs, list):
        return blockers
    for index, run in enumerate(raw_runs):
        if not isinstance(run, dict):
            continue
        pose_ref = _string(run.get("predicted_ligand_path_or_pose_ref"))
        if not pose_ref:
            continue
        if _contains_placeholder_marker(pose_ref) or _has_placeholder_provenance_prefix(
            pose_ref
        ):
            blockers.append(
                "vina_gnina_rows:"
                f"{row_key}:engine_run_{index}:"
                "predicted_ligand_path_or_pose_ref_placeholder"
            )
    return blockers


def _row_key(row: dict[str, Any], *, fallback: str, preferred_fields: tuple[str, ...]) -> str:
    for field in preferred_fields:
        value = _string(row.get(field))
        if value:
            return value
    return fallback


def _source_actuality_check(
    *,
    subset_rows: list[dict[str, Any]],
    pose_rows: list[dict[str, Any]],
    enrichment_targets: list[dict[str, Any]],
    vina_gnina_cases: list[dict[str, Any]],
) -> dict[str, Any]:
    blockers: list[str] = []
    for index, row in enumerate(subset_rows):
        blockers.extend(
            _source_receipt_actuality_blockers(
                row,
                group_id="subset_rows",
                row_key=_row_key(row, fallback=f"row_{index}", preferred_fields=("case_id", "complex_id")),
            )
        )
    for index, row in enumerate(pose_rows):
        blockers.extend(
            _pose_source_actuality_blockers(
                row,
                row_key=_row_key(row, fallback=f"row_{index}", preferred_fields=("case_id",)),
            )
        )
    for index, row in enumerate(enrichment_targets):
        blockers.extend(
            _source_receipt_actuality_blockers(
                row,
                group_id="enrichment_rows",
                row_key=_row_key(row, fallback=f"target_{index}", preferred_fields=("target_id",)),
            )
        )
    for index, row in enumerate(vina_gnina_cases):
        row_key = _row_key(
            row,
            fallback=f"case_{index}",
            preferred_fields=("case_id", "complex_id"),
        )
        blockers.extend(
            _source_receipt_actuality_blockers(
                row,
                group_id="vina_gnina_rows",
                row_key=row_key,
            )
        )
        blockers.extend(_vina_engine_pose_ref_actuality_blockers(row, row_key=row_key))
    blockers = sorted(dict.fromkeys(blockers))
    return {
        "contract_pass": not blockers,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "checked_row_counts": {
            "subset_rows": len(subset_rows),
            "pose_rows": len(pose_rows),
            "enrichment_targets": len(enrichment_targets),
            "vina_gnina_cases": len(vina_gnina_cases),
        },
        "policy": SOURCE_ACTUALITY_POLICY,
        "claim_boundary": (
            "This check rejects fixture, dry-run, placeholder, local/proxy URI, and repeated-digest "
            "source receipts before Public Benchmark Phase 2 can be promoted as actual evidence. "
            "It does not independently verify external licenses or download public benchmark data."
        ),
    }


def _rows_from_json(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = []
        for key in ("rows", "cases", "targets", "scored_molecules", "engine_runs"):
            value = payload.get(key)
            if isinstance(value, list):
                rows = value
                break
        if not rows:
            rows = [payload]
    else:
        rows = []
    return [_normalize_row(row) for row in rows if isinstance(row, dict)]


def _load_rows(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix in {".json", ".bundle"}:
        return _rows_from_json(json.loads(path.read_text(encoding="utf-8")))
    if suffix in {".jsonl", ".ndjson"}:
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            value = json.loads(stripped)
            if isinstance(value, dict):
                rows.append(_normalize_row(value))
        return rows

    with path.open("r", encoding="utf-8", newline="") as handle:
        return [_normalize_row(row) for row in csv.DictReader(handle)]


def _target_key(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(row.get(field) or "") for field in TARGET_FIELDS)


def _build_enrichment_targets(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    direct_targets = [
        row for row in rows if isinstance(row.get("scored_molecules"), list)
    ]
    flat_rows = [row for row in rows if not isinstance(row.get("scored_molecules"), list)]
    if not flat_rows:
        return direct_targets

    grouped: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in flat_rows:
        key = _target_key(row)
        target = grouped.setdefault(
            key,
            {
                field: row.get(field, "")
                for field in TARGET_FIELDS
            }
            | {"scored_molecules": []},
        )
        target["scored_molecules"].append(
            {field: row.get(field, "") for field in MOLECULE_FIELDS}
        )
    return [*direct_targets, *grouped.values()]


def _vina_case_key(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(row.get(field) or "") for field in VINA_CASE_FIELDS)


def _engine_run_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        field: row.get(field, "")
        for field in VINA_ENGINE_FIELDS
        if field in row and row.get(field, "") != ""
    }


def _build_vina_gnina_cases(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    direct_cases = [row for row in rows if isinstance(row.get("engine_runs"), list)]
    flat_rows = [row for row in rows if not isinstance(row.get("engine_runs"), list)]
    if not flat_rows:
        return direct_cases

    grouped: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in flat_rows:
        key = _vina_case_key(row)
        case = grouped.setdefault(
            key,
            {
                field: row.get(field, "")
                for field in VINA_CASE_FIELDS
            }
            | {"engine_runs": []},
        )
        case["engine_runs"].append(_engine_run_from_row(row))
    return [*direct_cases, *grouped.values()]


def build_public_benchmark_operator_bundle_from_rows(
    *,
    subset_rows_path: Path,
    pose_rows_path: Path,
    enrichment_rows_path: Path,
    vina_gnina_rows_path: Path,
    target_subset_case_count: int | None = None,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    subset_rows = _load_rows(subset_rows_path)
    pose_rows = _load_rows(pose_rows_path)
    enrichment_rows = _load_rows(enrichment_rows_path)
    vina_gnina_rows = _load_rows(vina_gnina_rows_path)
    enrichment_targets = _build_enrichment_targets(enrichment_rows)
    vina_gnina_cases = _build_vina_gnina_cases(vina_gnina_rows)
    row_file_artifact_receipts = _row_file_artifact_receipts(
        {
            "subset_rows": subset_rows_path,
            "pose_rows": pose_rows_path,
            "enrichment_rows": enrichment_rows_path,
            "vina_gnina_rows": vina_gnina_rows_path,
        }
    )
    source_actuality_check = _source_actuality_check(
        subset_rows=subset_rows,
        pose_rows=pose_rows,
        enrichment_targets=enrichment_targets,
        vina_gnina_cases=vina_gnina_cases,
    )
    target_count = target_subset_case_count or len(subset_rows)

    input_paths = [
        Path("scripts/materialize_public_benchmark_operator_bundle_from_rows.py"),
        subset_rows_path,
        pose_rows_path,
        enrichment_rows_path,
        vina_gnina_rows_path,
    ]
    return {
        "schema_version": OPERATOR_BUNDLE_SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=input_paths,
            reused_evidence=False,
            reuse_policy="public_benchmark_operator_bundle_materialized_from_rows",
            repo_root=repo_root,
        ),
        "target_subset_case_count": int(target_count),
        "casf_pdbbind_subset_intake": {
            "target_subset_case_count": int(target_count),
            "cases": subset_rows,
        },
        "pose_coordinate_intake": {"cases": pose_rows},
        "pose_validity_intake": {
            "cases": pose_rows,
            "consumer_chain": [
                "public_benchmark_pose_validity_input",
                "public_benchmark_posebusters_validity_packet",
                "public_benchmark_symmetry_rmsd_scorecard",
                "public_benchmark_pose_success_harness",
            ],
        },
        "dud_e_lit_pcba_enrichment_intake": {
            "targets": enrichment_targets
        },
        "vina_gnina_comparison_intake": {
            "cases": vina_gnina_cases
        },
        "materialization_report": {
            "schema_version": SCHEMA_VERSION,
            "subset_row_count": len(subset_rows),
            "pose_row_count": len(pose_rows),
            "pose_validity_case_count": len(pose_rows),
            "posebusters_validity_case_count": len(pose_rows),
            "enrichment_row_count": len(enrichment_rows),
            "enrichment_target_count": len(enrichment_targets),
            "vina_gnina_row_count": len(vina_gnina_rows),
            "vina_gnina_case_count": len(vina_gnina_cases),
            "accepted_row_formats": ["json", "jsonl", "ndjson", "csv"],
            "row_file_artifact_receipts": row_file_artifact_receipts,
            "source_actuality_check": source_actuality_check,
            "source_actuality_blockers": source_actuality_check["blockers"],
            "phase2_harness_inputs": {
                "casf_pdbbind_pose_success_harness": len(subset_rows) > 0 and len(pose_rows) > 0,
                "symmetry_aware_ligand_rmsd": len(pose_rows) > 0,
                "posebusters_style_pose_validity": len(pose_rows) > 0,
                "vina_gnina_comparison_adapter": len(vina_gnina_cases) > 0,
                "dud_e_lit_pcba_enrichment": len(enrichment_targets) > 0,
            },
        },
        "claim_boundary": (
            "This importer only reshapes operator-attached public benchmark row files "
            "into the existing public benchmark harness bundle format, including "
            "PoseBusters-style validity input derived from the pose-coordinate rows. "
            "It does not download data, approve licenses, run docking engines, or "
            "promote Tier beta without the downstream harness materializer passing."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subset-rows", type=Path, required=True)
    parser.add_argument("--pose-rows", type=Path, required=True)
    parser.add_argument("--enrichment-rows", type=Path, required=True)
    parser.add_argument("--vina-gnina-rows", type=Path, required=True)
    parser.add_argument("--target-subset-case-count", type=int)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_public_benchmark_operator_bundle_from_rows(
        subset_rows_path=args.subset_rows,
        pose_rows_path=args.pose_rows,
        enrichment_rows_path=args.enrichment_rows,
        vina_gnina_rows_path=args.vina_gnina_rows,
        target_subset_case_count=args.target_subset_case_count,
        repo_root=args.repo_root,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(_json_text(payload), encoding="utf-8")
    if args.json:
        print(_json_text(payload), end="")
    else:
        report = payload["materialization_report"]
        print(
            "public-benchmark-operator-bundle-from-rows: "
            f"subset_rows={report['subset_row_count']} | "
            f"pose_rows={report['pose_row_count']} | "
            f"enrichment_targets={report['enrichment_target_count']} | "
            f"vina_gnina_cases={report['vina_gnina_case_count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
