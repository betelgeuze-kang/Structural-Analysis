#!/usr/bin/env python3
"""Materialize a Vina/GNINA input manifest working copy from its template."""

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

from build_public_benchmark_vina_gnina_input_manifest_template_preflight import (  # noqa: E402
    DEFAULT_CASF_ARCHIVE_OUT_MANIFEST,
    DEFAULT_CASF_ARCHIVE_SOURCE_REPORT,
    DEFAULT_CASF_ARCHIVE_EXTRACT_DIR,
    DEFAULT_OUT as DEFAULT_TEMPLATE_PREFLIGHT,
    DEFAULT_OUT_MD as DEFAULT_TEMPLATE_PREFLIGHT_MD,
    DEFAULT_TEMPLATE,
    MANIFEST_REQUIRED_FIELDS,
    build_public_benchmark_vina_gnina_input_manifest_template_preflight,
)
from build_public_benchmark_vina_gnina_execution_plan import (  # noqa: E402
    DEFAULT_INPUT_MANIFEST,
    DEFAULT_OUT as DEFAULT_EXECUTION_PLAN,
)
from release_evidence_metadata import release_evidence_metadata  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT_REPORT = (
    PRODUCTIZATION
    / "public_benchmark_vina_gnina_input_manifest_from_template_report.json"
)
SCHEMA_VERSION = "public-benchmark-vina-gnina-input-manifest-from-template.v1"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _write_json(repo_root: Path, path: Path, payload: dict[str, Any]) -> None:
    resolved = _resolve(repo_root, path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")


def _read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.is_file():
        return list(MANIFEST_REQUIRED_FIELDS), []
    with path.open("r", encoding="utf-8", newline="") as handle:
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
    return header or list(MANIFEST_REQUIRED_FIELDS), rows


def _write_csv(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=header,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def materialize_public_benchmark_vina_gnina_input_manifest_from_template(
    *,
    repo_root: Path = ROOT,
    template: Path = DEFAULT_TEMPLATE,
    out_manifest: Path = DEFAULT_INPUT_MANIFEST.with_suffix(".csv"),
    out_report: Path = DEFAULT_OUT_REPORT,
    overwrite: bool = False,
) -> dict[str, Any]:
    resolved_template = _resolve(repo_root, template)
    resolved_manifest = _resolve(repo_root, out_manifest)
    preflight = build_public_benchmark_vina_gnina_input_manifest_template_preflight(
        repo_root=repo_root,
        template=template,
        expected_manifest=out_manifest,
    )
    header, rows = _read_csv_rows(resolved_template)
    template_case_coverage_complete = bool(
        preflight.get("summary", {}).get("template_case_coverage_complete")
    )
    template_usable = bool(rows) and template_case_coverage_complete
    manifest_exists = resolved_manifest.is_file()
    blockers: list[str] = []
    if not rows:
        blockers.append("public_benchmark_vina_gnina_input_manifest_template_rows_missing")
    if not template_case_coverage_complete:
        blockers.append(
            "public_benchmark_vina_gnina_input_manifest_template_case_coverage_incomplete"
        )
    wrote_manifest = False
    skipped_existing = False
    if template_usable:
        if manifest_exists and not overwrite:
            skipped_existing = True
        else:
            _write_csv(resolved_manifest, header, rows)
            wrote_manifest = True
            manifest_exists = True
    if wrote_manifest:
        status = "manifest_working_copy_materialized"
    elif skipped_existing:
        status = "manifest_already_exists"
    elif template_usable:
        status = "manifest_working_copy_not_written"
    else:
        status = "template_not_usable"
    materialized = manifest_exists and template_usable and not blockers
    report = {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path(
                    "scripts/materialize_public_benchmark_vina_gnina_input_manifest_from_template.py"
                ),
                Path(
                    "scripts/build_public_benchmark_vina_gnina_input_manifest_template_preflight.py"
                ),
                template,
            ],
            reused_evidence=False,
            reuse_policy=(
                "public_benchmark_vina_gnina_input_manifest_working_copy_from_template"
            ),
            repo_root=repo_root,
        ),
        "status": status,
        "contract_pass": materialized,
        "manifest_materialized": materialized,
        "wrote_manifest": wrote_manifest,
        "skipped_existing": skipped_existing,
        "overwrite": overwrite,
        "template_artifact": str(template),
        "out_manifest_artifact": str(out_manifest),
        "out_report_artifact": str(out_report),
        "row_count": len(rows),
        "case_count": len({str(row.get("case_id") or "") for row in rows}),
        "manifest_ready": bool(preflight.get("manifest_ready")),
        "template_preflight_status": str(preflight.get("status") or ""),
        "template_preflight_summary": dict(preflight.get("summary") or {}),
        "blockers": blockers,
        "commands": {
            "rerun_template_preflight": (
                "python3 scripts/build_public_benchmark_vina_gnina_input_manifest_template_preflight.py "
                f"--out {DEFAULT_TEMPLATE_PREFLIGHT} --out-md {DEFAULT_TEMPLATE_PREFLIGHT_MD}"
            ),
            "materialize_input_manifest_from_template": (
                "python3 scripts/materialize_public_benchmark_vina_gnina_input_manifest_from_template.py "
                f"--template {template} --out-manifest {out_manifest} "
                f"--out-report {out_report}"
            ),
            "materialize_source_files_from_casf_archive": (
                "python3 scripts/materialize_public_benchmark_vina_gnina_input_manifest_from_casf_archive.py "
                f"--archive <CASF-2016.tar.gz> --extract-dir {DEFAULT_CASF_ARCHIVE_EXTRACT_DIR} "
                f"--out-manifest {DEFAULT_CASF_ARCHIVE_OUT_MANIFEST} "
                f"--out-report {DEFAULT_CASF_ARCHIVE_SOURCE_REPORT}"
            ),
            "rerun_execution_plan": (
                "python3 scripts/build_public_benchmark_vina_gnina_execution_plan.py "
                f"--out {DEFAULT_EXECUTION_PLAN}"
            ),
        },
        "summary": {
            "manifest_materialized": materialized,
            "wrote_manifest": wrote_manifest,
            "skipped_existing": skipped_existing,
            "row_count": len(rows),
            "case_count": len({str(row.get("case_id") or "") for row in rows}),
            "manifest_ready": bool(preflight.get("manifest_ready")),
            "blocker_count": len(blockers),
        },
        "claim_boundary": (
            "This helper copies the Vina/GNINA input manifest template into the "
            "default manifest dropzone so the execution plan can see the case "
            "rows. It does not make source files local, prepare receptor/ligand "
            "inputs, run Vina/GNINA, attach engine receipts, or promote adapter "
            "rows as actual Phase 2 evidence."
        ),
    }
    _write_json(repo_root, out_report, report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument(
        "--out-manifest",
        type=Path,
        default=DEFAULT_INPUT_MANIFEST.with_suffix(".csv"),
    )
    parser.add_argument("--out-report", type=Path, default=DEFAULT_OUT_REPORT)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = materialize_public_benchmark_vina_gnina_input_manifest_from_template(
        repo_root=args.repo_root,
        template=args.template,
        out_manifest=args.out_manifest,
        out_report=args.out_report,
        overwrite=args.overwrite,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "public-benchmark-vina-gnina-input-manifest-from-template: "
            f"{payload['status']} | rows={payload['row_count']} | "
            f"written={payload['wrote_manifest']}"
        )
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
