#!/usr/bin/env python3
"""Extract CASF source files and draft the Vina/GNINA input manifest."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import posixpath
import shutil
import sys
import tarfile
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_public_benchmark_vina_gnina_input_manifest_template_preflight import (  # noqa: E402
    DEFAULT_TEMPLATE,
    MANIFEST_REQUIRED_FIELDS,
    PREPARED_LOCAL_FILE_FIELDS,
    SOURCE_LOCAL_FILE_FIELDS,
)
from release_evidence_metadata import release_evidence_metadata  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT_MANIFEST = PRODUCTIZATION / "public_benchmark_vina_gnina_input_manifest.csv"
DEFAULT_OUT_REPORT = (
    PRODUCTIZATION / "public_benchmark_vina_gnina_input_manifest_from_casf_archive_report.json"
)
DEFAULT_EXTRACT_DIR = Path("tmp/public_benchmark_vina_gnina/casf2016_source_files")
SCHEMA_VERSION = "public-benchmark-vina-gnina-input-manifest-from-casf-archive.v1"
CHECKSUM_CHUNK_SIZE = 1024 * 1024
SOURCE_PATH_TO_CHECKSUM_FIELD = {
    "protein_structure_path": "protein_structure_checksum",
    "reference_ligand_path": "reference_ligand_checksum",
}


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _display_path(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _safe_relative_path(value: str) -> str:
    raw = str(value or "").strip().replace("\\", "/")
    if not raw or "\x00" in raw:
        return ""
    normalized = posixpath.normpath(raw)
    if normalized.startswith("./"):
        normalized = normalized[2:]
    if (
        not normalized
        or normalized == "."
        or normalized == ".."
        or normalized.startswith("../")
        or posixpath.isabs(normalized)
    ):
        return ""
    return normalized


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHECKSUM_CHUNK_SIZE), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _read_template_rows(repo_root: Path, template: Path) -> tuple[list[str], list[dict[str, str]]]:
    resolved = _resolve(repo_root, template)
    if not resolved.is_file():
        return list(MANIFEST_REQUIRED_FIELDS), []
    with resolved.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = [
            {
                str(key).strip(): str(value or "").strip()
                for key, value in row.items()
                if key is not None
            }
            for row in reader
        ]
    header = [str(field) for field in reader.fieldnames or []]
    if not header:
        header = list(MANIFEST_REQUIRED_FIELDS)
    return header, rows


def _write_csv(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=header, extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def _source_member_index(
    archive_path: Path,
) -> tuple[tarfile.TarFile, dict[str, tarfile.TarInfo], dict[str, Any]]:
    archive = tarfile.open(archive_path, "r:*")
    members_by_path: dict[str, tarfile.TarInfo] = {}
    duplicate_safe_names: set[str] = set()
    unsafe_member_count = 0
    member_count = 0
    file_member_count = 0
    for member in archive.getmembers():
        member_count += 1
        safe_name = _safe_relative_path(member.name)
        if not safe_name:
            unsafe_member_count += 1
            continue
        if not member.isfile():
            continue
        file_member_count += 1
        if safe_name in members_by_path:
            duplicate_safe_names.add(safe_name)
            continue
        members_by_path[safe_name] = member
    return (
        archive,
        members_by_path,
        {
            "member_count": member_count,
            "file_member_count": file_member_count,
            "indexed_file_member_count": len(members_by_path),
            "unsafe_member_count": unsafe_member_count,
            "duplicate_safe_name_count": len(duplicate_safe_names),
        },
    )


def _find_archive_member(
    members_by_path: dict[str, tarfile.TarInfo],
    required_path: str,
) -> tuple[tarfile.TarInfo | None, str, str]:
    safe_required_path = _safe_relative_path(required_path)
    if not safe_required_path:
        return None, "", "template_source_path_unsafe"
    exact = members_by_path.get(safe_required_path)
    if exact is not None:
        return exact, safe_required_path, ""
    suffix = f"/{safe_required_path}"
    matches = [
        (member_path, member)
        for member_path, member in members_by_path.items()
        if member_path.endswith(suffix)
    ]
    if not matches:
        return None, safe_required_path, "archive_member_missing"
    if len(matches) > 1:
        return None, safe_required_path, "archive_member_ambiguous"
    return matches[0][1], safe_required_path, ""


def _extract_member(
    archive: tarfile.TarFile,
    member: tarfile.TarInfo,
    destination: Path,
) -> None:
    source = archive.extractfile(member)
    if source is None:
        raise OSError("archive_member_not_readable")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source, destination.open("wb") as handle:
        shutil.copyfileobj(source, handle)


def _materialize_source_file(
    *,
    archive: tarfile.TarFile,
    members_by_path: dict[str, tarfile.TarInfo],
    repo_root: Path,
    extract_dir: Path,
    row: dict[str, str],
    path_field: str,
) -> dict[str, Any]:
    template_path = str(row.get(path_field) or "")
    checksum_field = SOURCE_PATH_TO_CHECKSUM_FIELD[path_field]
    expected_checksum = str(row.get(checksum_field) or "")
    member, safe_required_path, blocker = _find_archive_member(
        members_by_path,
        template_path,
    )
    destination_name = safe_required_path or f"unsafe_template_source_path/{path_field}"
    destination = _resolve(repo_root, extract_dir) / destination_name
    actual_checksum = ""
    checksum_verified = False
    if member is not None and not blocker:
        try:
            _extract_member(archive, member, destination)
            actual_checksum = _sha256_file(destination)
        except OSError as exc:
            blocker = exc.__class__.__name__
        else:
            if not expected_checksum:
                blocker = "expected_checksum_missing"
            elif actual_checksum.lower() != expected_checksum.lower():
                blocker = "checksum_mismatch"
            else:
                checksum_verified = True
    return {
        "field": path_field,
        "template_path": template_path,
        "safe_required_path": safe_required_path,
        "archive_member": str(member.name) if member is not None else "",
        "output_path": _display_path(repo_root, destination),
        "expected_checksum": expected_checksum,
        "actual_checksum": actual_checksum,
        "checksum_verified": checksum_verified,
        "status": "ready" if checksum_verified else "blocked",
        "blocker": blocker,
    }


def _prepared_input_gaps(row: dict[str, str]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for path_field in PREPARED_LOCAL_FILE_FIELDS:
        checksum_field = path_field.replace("_path", "_checksum")
        path_value = str(row.get(path_field) or "")
        checksum_value = str(row.get(checksum_field) or "")
        if not path_value or not checksum_value:
            gaps.append(
                {
                    "field": path_field,
                    "path": path_value,
                    "checksum_field": checksum_field,
                    "checksum_present": bool(checksum_value),
                    "blocker": (
                        "prepared_input_path_missing"
                        if not path_value
                        else "prepared_input_checksum_missing"
                    ),
                }
            )
    return gaps


def materialize_public_benchmark_vina_gnina_input_manifest_from_casf_archive(
    *,
    repo_root: Path = ROOT,
    archive_path: Path,
    template: Path = DEFAULT_TEMPLATE,
    extract_dir: Path = DEFAULT_EXTRACT_DIR,
    out_manifest: Path = DEFAULT_OUT_MANIFEST,
    out_report: Path = DEFAULT_OUT_REPORT,
) -> dict[str, Any]:
    resolved_archive = _resolve(repo_root, archive_path)
    header, template_rows = _read_template_rows(repo_root, template)
    output_rows = [dict(row) for row in template_rows]
    source_file_rows: list[dict[str, Any]] = []
    case_rows: list[dict[str, Any]] = []
    archive_index_summary = {
        "member_count": 0,
        "file_member_count": 0,
        "indexed_file_member_count": 0,
        "unsafe_member_count": 0,
        "duplicate_safe_name_count": 0,
    }
    archive_blocker = ""

    if not resolved_archive.is_file():
        archive_blocker = "casf_archive_not_found"
    elif not template_rows:
        archive_blocker = "input_manifest_template_missing_or_empty"
    else:
        try:
            archive, members_by_path, archive_index_summary = _source_member_index(
                resolved_archive
            )
        except (OSError, tarfile.TarError) as exc:
            archive_blocker = exc.__class__.__name__
        else:
            with archive:
                for row_index, row in enumerate(template_rows):
                    case_source_files = []
                    for path_field in SOURCE_LOCAL_FILE_FIELDS:
                        status = _materialize_source_file(
                            archive=archive,
                            members_by_path=members_by_path,
                            repo_root=repo_root,
                            extract_dir=extract_dir,
                            row=row,
                            path_field=path_field,
                        )
                        source_file_rows.append(
                            {
                                "case_id": str(row.get("case_id") or ""),
                                "complex_id": str(row.get("complex_id") or ""),
                                **status,
                            }
                        )
                        case_source_files.append(status)
                        output_rows[row_index][path_field] = str(status["output_path"])
                    prepared_gaps = _prepared_input_gaps(row)
                    case_blockers = [
                        str(status["blocker"])
                        for status in case_source_files
                        if str(status.get("blocker") or "")
                    ]
                    case_blockers.extend(
                        str(gap["blocker"])
                        for gap in prepared_gaps
                        if str(gap.get("blocker") or "")
                    )
                    case_rows.append(
                        {
                            "case_id": str(row.get("case_id") or ""),
                            "complex_id": str(row.get("complex_id") or ""),
                            "status": "source_files_ready"
                            if not [
                                status
                                for status in case_source_files
                                if str(status.get("blocker") or "")
                            ]
                            else "source_files_blocked",
                            "source_files": case_source_files,
                            "prepared_input_gaps": prepared_gaps,
                            "blockers": case_blockers,
                        }
                    )

    if archive_blocker and template_rows:
        for row_index, row in enumerate(template_rows):
            case_source_files = []
            for path_field in SOURCE_LOCAL_FILE_FIELDS:
                checksum_field = SOURCE_PATH_TO_CHECKSUM_FIELD[path_field]
                destination = _resolve(repo_root, extract_dir) / _safe_relative_path(
                    str(row.get(path_field) or "")
                )
                status = {
                    "field": path_field,
                    "template_path": str(row.get(path_field) or ""),
                    "safe_required_path": _safe_relative_path(
                        str(row.get(path_field) or "")
                    ),
                    "archive_member": "",
                    "output_path": _display_path(repo_root, destination),
                    "expected_checksum": str(row.get(checksum_field) or ""),
                    "actual_checksum": "",
                    "checksum_verified": False,
                    "status": "blocked",
                    "blocker": archive_blocker,
                }
                source_file_rows.append(
                    {
                        "case_id": str(row.get("case_id") or ""),
                        "complex_id": str(row.get("complex_id") or ""),
                        **status,
                    }
                )
                case_source_files.append(status)
                output_rows[row_index][path_field] = str(status["output_path"])
            prepared_gaps = _prepared_input_gaps(row)
            case_rows.append(
                {
                    "case_id": str(row.get("case_id") or ""),
                    "complex_id": str(row.get("complex_id") or ""),
                    "status": "source_files_blocked",
                    "source_files": case_source_files,
                    "prepared_input_gaps": prepared_gaps,
                    "blockers": [
                        archive_blocker,
                        *[
                            str(gap["blocker"])
                            for gap in prepared_gaps
                            if str(gap.get("blocker") or "")
                        ],
                    ],
                }
            )

    source_file_verified_count = sum(
        1 for row in source_file_rows if bool(row.get("checksum_verified"))
    )
    source_file_blocker_count = sum(
        1 for row in source_file_rows if str(row.get("blocker") or "")
    )
    prepared_gap_count = sum(len(row.get("prepared_input_gaps", [])) for row in case_rows)
    source_files_ready = bool(source_file_rows) and source_file_blocker_count == 0
    status = (
        "source_files_verified_prepared_inputs_required"
        if source_files_ready
        else "source_file_extraction_blocked"
    )
    if not template_rows:
        status = "input_manifest_template_missing_or_empty"
    elif archive_blocker == "casf_archive_not_found":
        status = "casf_archive_missing"

    resolved_manifest = _resolve(repo_root, out_manifest)
    if template_rows:
        _write_csv(resolved_manifest, header, output_rows)
    resolved_report = _resolve(repo_root, out_report)
    resolved_report.parent.mkdir(parents=True, exist_ok=True)

    archive_size_bytes = resolved_archive.stat().st_size if resolved_archive.exists() else 0
    payload = {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/materialize_public_benchmark_vina_gnina_input_manifest_from_casf_archive.py"),
                Path("scripts/build_public_benchmark_vina_gnina_input_manifest_template_preflight.py"),
                template,
            ],
            reused_evidence=False,
            reuse_policy="public_benchmark_vina_gnina_source_file_extraction_from_local_casf_archive",
            repo_root=repo_root,
        ),
        "status": status,
        "contract_pass": bool(template_rows),
        "source_files_ready": source_files_ready,
        "manifest_ready": False,
        "archive_artifact": str(archive_path),
        "archive_present": resolved_archive.is_file(),
        "archive_size_bytes": archive_size_bytes,
        "template_artifact": str(template),
        "extract_dir": str(extract_dir),
        "out_manifest_artifact": str(out_manifest),
        "out_report_artifact": str(out_report),
        "output_manifest_written": bool(template_rows),
        "archive_index_summary": archive_index_summary,
        "case_rows": case_rows,
        "source_file_rows": source_file_rows,
        "operator_actions": [
            "review_source_file_checksum_results",
            "prepare_vina_gnina_receptor_and_ligand_inputs",
            "fill_prepared_input_checksums_and_input_preparation_provenance_ref",
            "rerun_public_benchmark_vina_gnina_input_manifest_template_preflight",
            "rerun_public_benchmark_vina_gnina_execution_plan",
        ],
        "commands": {
            "rerun_source_extraction": (
                "python3 scripts/materialize_public_benchmark_vina_gnina_input_manifest_from_casf_archive.py "
                f"--archive {archive_path} --out-manifest {out_manifest} "
                f"--out-report {out_report}"
            ),
            "rerun_input_manifest_preflight": (
                "python3 scripts/build_public_benchmark_vina_gnina_input_manifest_template_preflight.py "
                f"--expected-manifest {out_manifest} --out "
                f"{PRODUCTIZATION / 'public_benchmark_vina_gnina_input_manifest_template_preflight.json'} "
                f"--out-md {PRODUCTIZATION / 'public_benchmark_vina_gnina_input_manifest_template_preflight.md'}"
            ),
            "rerun_execution_plan": (
                "python3 scripts/build_public_benchmark_vina_gnina_execution_plan.py "
                f"--input-manifest {out_manifest} --out "
                f"{PRODUCTIZATION / 'public_benchmark_vina_gnina_execution_plan.json'}"
            ),
        },
        "summary": {
            "template_row_count": len(template_rows),
            "required_source_file_count": len(source_file_rows),
            "source_file_verified_count": source_file_verified_count,
            "source_file_blocker_count": source_file_blocker_count,
            "source_files_ready": source_files_ready,
            "prepared_input_gap_count": prepared_gap_count,
            "manifest_ready": False,
            "archive_blocker": archive_blocker,
        },
        "claim_boundary": (
            "This helper extracts and checksum-verifies local CASF source files from "
            "an operator-supplied archive, then drafts the Vina/GNINA input manifest. "
            "It does not download CASF payloads, prepare receptor or ligand inputs, "
            "run Vina/GNINA, create comparison rows, or close Public Benchmark Phase 2."
        ),
    }
    resolved_report.write_text(_json_text(payload), encoding="utf-8")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--extract-dir", type=Path, default=DEFAULT_EXTRACT_DIR)
    parser.add_argument("--out-manifest", type=Path, default=DEFAULT_OUT_MANIFEST)
    parser.add_argument("--out-report", type=Path, default=DEFAULT_OUT_REPORT)
    parser.add_argument("--fail-blocked", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = materialize_public_benchmark_vina_gnina_input_manifest_from_casf_archive(
        repo_root=args.repo_root,
        archive_path=args.archive,
        template=args.template,
        extract_dir=args.extract_dir,
        out_manifest=args.out_manifest,
        out_report=args.out_report,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        summary = payload["summary"]
        print(
            "public-benchmark-vina-gnina-input-manifest-from-casf-archive: "
            f"{payload['status']} | "
            f"source_files={summary['source_file_verified_count']}/"
            f"{summary['required_source_file_count']} | "
            f"manifest_ready={payload['manifest_ready']}"
        )
    return 1 if args.fail_blocked and not payload["source_files_ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
