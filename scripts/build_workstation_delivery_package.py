#!/usr/bin/env python3
"""Build a self-contained workstation delivery package zip."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any
import zipfile


SCHEMA_VERSION = "workstation-delivery-package-manifest.v1"
JOB_SCHEMA_VERSION = "workstation-job-record.v1"
DEFAULT_PACKAGE_OUT = Path("implementation/phase1/release/workstation_delivery/project_package.zip")
DEFAULT_MANIFEST_OUT = Path("implementation/phase1/workstation_delivery_package_manifest.json")
DEFAULT_JOB_RECORD_OUT = Path("implementation/phase1/workstation_job_record.json")
DEFAULT_JOB_ROOT = Path("implementation/phase1/workstation_jobs")
DEFAULT_VIEWER_HTML = Path("implementation/phase1/release/visualization/structural_viewer_midas33_pr_singlefile.html")
DEFAULT_VIEWER_HTML_FALLBACK = Path("src/structure-viewer/index.html")
DEFAULT_REPORT_PDF = Path(
    "implementation/phase1/release/visualization/optimized_drawing_expert_review_batch/"
    "optimized_drawing_expert_review.default.pdf"
)
DEFAULT_DRAWINGS_DIR = Path("implementation/phase1/output/structural_svg")
DEFAULT_CLIENT_VALIDATION_REPORT = Path("implementation/phase1/client_input_validation_report.json")
DEFAULT_HARDWARE_PROFILE = Path("implementation/phase1/workstation_hardware_profile.json")
DEFAULT_SERVICE_BUDGET = Path("implementation/phase1/workstation_service_budget.json")
DEFAULT_VIEWER_BROWSER_PERFORMANCE_PROBE = Path("implementation/phase1/structure_viewer_browser_performance_probe.json")
DEFAULT_VIEWER_VISUAL_REGRESSION_BASELINE = Path("implementation/phase1/structure_viewer_visual_regression_baseline.json")
DEFAULT_SUPPORT_BUNDLE_MANIFEST = Path("implementation/phase1/support_bundle_manifest.json")
DEFAULT_SOURCE_MODEL = Path("implementation/phase1/open_data/midas/midas_model.json")


CLAIM_BOUNDARY = (
    "Workstation-based structural analysis/optimization deliverable preparation service with structural engineer "
    "review. This package is not an autonomous engineer replacement, not an independent SaaS structural solver "
    "claim, and not a customer-device FPS claim."
)


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _copy_if_exists(source: Path, destination: Path) -> bool:
    if not source.exists():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return True


def _write_minimal_pdf(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
        b"4 0 obj << /Length 109 >> stream\n"
        b"BT /F1 12 Tf 72 720 Td (Workstation delivery report placeholder. See manifest for claim boundary.) Tj ET\n"
        b"endstream endobj\n"
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
        b"xref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n"
        b"0000000115 00000 n \n0000000268 00000 n \n0000000427 00000 n \n"
        b"trailer << /Root 1 0 R /Size 6 >>\nstartxref\n497\n%%EOF\n"
    )
    path.write_bytes(payload)


def _readme_text() -> str:
    return """# Workstation Delivery Package

Open `viewer.html` for the interactive review surface and `report.pdf` for the printable review summary.

Package sections:
- `drawings/`: SVG drawing sheets and callout references.
- `data/`: JSON/CSV artifacts, hardware profile, service budget, and client input validation.
- `evidence/`: local viewer probes, visual regression evidence, and support/readiness manifests.
- `manifest.json`: package file list, checksums, source references, and claim boundary.
- `checksums.sha256`: SHA-256 verification rows for package contents.

Claim boundary:
This is a workstation-generated structural analysis/optimization deliverable for structural engineer review. It is not an autonomous engineer replacement, not a public SaaS throughput claim, and not a customer-device FPS claim.

Revision rule:
Every redelivery must be rebuilt as a new package with a fresh manifest and checksum file.
"""


def _delivery_index_text() -> str:
    return """# Delivery Index

## Open Order

1. `report.pdf` for the printable engineering review summary.
2. `viewer.html` for the interactive model/result review.
3. `drawings/` for SVG sheets and callout references.
4. `data/client_input_validation_report.json` for input readiness and missing-data status.
5. `manifest.json` and `checksums.sha256` for file provenance and integrity.

## Acceptance Checklist

- Report, viewer, drawings, data, and evidence sections are present.
- Package checksums match extracted files.
- Proxy/fallback values are explicitly labeled in the manifest.
- Structural engineer review remains required before external use.

## Claim Boundary

This is a workstation-generated delivery package for structural engineer review. It is not an autonomous engineer replacement, not an independent SaaS structural solver claim, and not a customer-device FPS claim.
"""


def _revision_history_text(generated_at: str) -> str:
    return f"""# Revision History

| Revision | Generated At | Change Type | Notes |
|---|---|---|---|
| R0 | {generated_at} | initial_delivery | Workstation package generated with manifest, checksums, viewer, report, drawings, data, and evidence. |

Every redelivery must create a new package, manifest, checksum file, and job record. Do not overwrite a previously delivered package without preserving its manifest and job folder.
"""


def _revision_policy_payload(generated_at: str) -> dict[str, Any]:
    return {
        "schema_version": "workstation-delivery-revision-policy.v1",
        "generated_at": generated_at,
        "policy": {
            "redelivery_requires_new_package": True,
            "redelivery_requires_new_manifest": True,
            "redelivery_requires_new_checksums": True,
            "redelivery_requires_new_job_record": True,
            "previous_deliveries_must_remain_traceable": True,
            "revision_label_format": "R<number>",
        },
        "claim_boundary": CLAIM_BOUNDARY,
    }


def _job_identity(input_refs: list[dict[str, Any]], timestamp: str) -> tuple[str, str]:
    input_hash = _sha256_bytes(json.dumps(input_refs, sort_keys=True).encode("utf-8"))[:16]
    job_id = f"{timestamp.replace(':', '').replace('-', '')[:15]}-{input_hash}"
    return job_id, input_hash


def _previous_delivery_rows(job_root: Path, *, limit: int = 5) -> list[dict[str, Any]]:
    if not job_root.exists():
        return []
    latest_path = job_root / "latest_job_id.txt"
    latest_job_id = latest_path.read_text(encoding="utf-8").strip() if latest_path.exists() else ""
    rows = []
    for job_dir in sorted((path for path in job_root.iterdir() if path.is_dir()), reverse=True):
        output_manifest = _load_json(job_dir / "output_manifest.json")
        rows.append(
            {
                "job_id": job_dir.name,
                "job_dir": str(job_dir),
                "package_path": str(output_manifest.get("package_path", "")),
                "output_manifest": str(job_dir / "output_manifest.json"),
                "checksums": str(job_dir / "checksums.sha256"),
                "is_previous_latest": job_dir.name == latest_job_id,
            }
        )
    return rows[:limit]


def _acceptance_packet_text(*, generated_at: str, current_job_id: str) -> str:
    return f"""# Customer Acceptance Packet

Generated at: `{generated_at}`
Current job id: `{current_job_id}`

## Acceptance Decision

- [ ] Accepted for structural engineer review.
- [ ] Accepted with comments; redelivery not required.
- [ ] Redelivery requested; comments are attached separately.
- [ ] Rejected; scope or input package must be corrected.

## Package Integrity

- Verify `checksums.sha256` before review.
- Confirm `manifest.json` lists `report.pdf`, `viewer.html`, drawings, data, and evidence.
- Confirm `data/redelivery_comparison_manifest.json` links this package to the previous delivery history.

## Engineer Review Required

This package is for structural engineer review. It is not an autonomous approval, not an independent SaaS structural solver claim, and not a customer-device FPS claim.

## Client Comments

Record comments outside the package and preserve this package manifest for traceability.
"""


def _redelivery_comparison_payload(
    *,
    generated_at: str,
    current_job_id: str,
    previous_deliveries: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": "workstation-delivery-redelivery-comparison.v1",
        "generated_at": generated_at,
        "current_job_id": current_job_id,
        "previous_delivery_count": len(previous_deliveries),
        "previous_latest_job_id": next(
            (row["job_id"] for row in previous_deliveries if row.get("is_previous_latest")),
            "",
        ),
        "comparison_scope": "traceability_only",
        "engineer_review_required": True,
        "previous_deliveries": previous_deliveries,
        "redelivery_policy": {
            "previous_packages_must_not_be_overwritten": True,
            "current_package_requires_new_manifest": True,
            "current_package_requires_new_checksums": True,
            "current_package_requires_new_job_record": True,
        },
        "claim_boundary": CLAIM_BOUNDARY,
    }


def _checksum_rows(root: Path, *, include_manifest: bool = True) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        rel = path.relative_to(root).as_posix()
        if rel == "checksums.sha256":
            continue
        if not include_manifest and rel == "manifest.json":
            continue
        rows.append(
            {
                "path": rel,
                "bytes": path.stat().st_size,
                "sha256": _sha256_path(path),
            }
        )
    return rows


def _write_checksums(root: Path, rows: list[dict[str, Any]]) -> None:
    text = "".join(f"{row['sha256']}  {row['path']}\n" for row in rows)
    (root / "checksums.sha256").write_text(text, encoding="utf-8")


def _write_zip(root: Path, package_path: Path) -> None:
    package_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for directory in ("drawings", "data", "evidence"):
            archive.writestr(f"{directory}/", "")
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            archive.write(path, path.relative_to(root).as_posix())


def _verify_checksums(root: Path) -> dict[str, Any]:
    checksum_path = root / "checksums.sha256"
    if not checksum_path.exists():
        return {"pass": False, "reason": "checksums_file_missing", "checked_rows": 0}
    checked = 0
    mismatches = []
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, _, rel = line.partition("  ")
        path = root / rel
        checked += 1
        if not path.exists():
            mismatches.append(f"missing:{rel}")
        elif _sha256_path(path) != expected:
            mismatches.append(f"sha256_mismatch:{rel}")
    return {
        "pass": not mismatches and checked > 0,
        "reason": "PASS" if not mismatches and checked > 0 else "checksum_mismatch",
        "checked_rows": checked,
        "mismatches": mismatches,
    }


def _zip_file_rows(package_path: Path) -> list[dict[str, Any]]:
    rows = []
    with zipfile.ZipFile(package_path) as archive:
        for info in sorted(archive.infolist(), key=lambda item: item.filename):
            if info.is_dir():
                continue
            payload = archive.read(info.filename)
            rows.append(
                {
                    "path": info.filename,
                    "bytes": info.file_size,
                    "sha256": _sha256_bytes(payload),
                }
            )
    return rows


def verify_package_manifest_consistency(package_path: Path) -> dict[str, Any]:
    if not package_path.exists():
        return {"pass": False, "reason": "package_missing", "checked_rows": 0, "mismatches": []}
    with zipfile.ZipFile(package_path) as archive:
        try:
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            return {"pass": False, "reason": f"manifest_unreadable:{exc}", "checked_rows": 0, "mismatches": []}
        actual_by_path = {row["path"]: row for row in _zip_file_rows(package_path)}
    output_rows = manifest.get("output_rows", [])
    if not isinstance(output_rows, list):
        return {"pass": False, "reason": "manifest_output_rows_invalid", "checked_rows": 0, "mismatches": []}
    mismatches = []
    checked = 0
    for row in output_rows:
        if not isinstance(row, dict):
            mismatches.append("row_not_object")
            continue
        path = str(row.get("path", ""))
        actual = actual_by_path.get(path)
        checked += 1
        if actual is None:
            mismatches.append(f"missing_from_zip:{path}")
            continue
        if int(row.get("bytes", -1)) != int(actual.get("bytes", -2)):
            mismatches.append(f"bytes_mismatch:{path}")
        if str(row.get("sha256", "")) != str(actual.get("sha256", "")):
            mismatches.append(f"sha256_mismatch:{path}")
    return {
        "pass": not mismatches and checked > 0,
        "reason": "PASS" if not mismatches and checked > 0 else "manifest_zip_rows_mismatch",
        "checked_rows": checked,
        "mismatches": mismatches,
    }


def _write_job_folder(*, job_root: Path, job_record: dict[str, Any], package_path: Path) -> dict[str, Any]:
    job_id = str(job_record.get("job_id", ""))
    if not job_id:
        return {"pass": False, "reason": "job_id_missing", "job_dir": "", "required_paths": {}}

    job_dir = job_root / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    input_manifest = {
        "schema_version": "workstation-job-input-manifest.v1",
        "job_id": job_id,
        "input_hash": str(job_record.get("input_hash", "")),
        "input_refs": job_record.get("input_manifest", []),
    }
    output_manifest = {
        "schema_version": "workstation-job-output-manifest.v1",
        "job_id": job_id,
        "package_path": str(package_path),
        "output_rows": job_record.get("output_manifest", []),
    }
    (job_dir / "input_manifest.json").write_text(
        json.dumps(input_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (job_dir / "output_manifest.json").write_text(
        json.dumps(output_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    run_log_rows = job_record.get("run_log", [])
    if not isinstance(run_log_rows, list):
        run_log_rows = []
    (job_dir / "run_log.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in run_log_rows),
        encoding="utf-8",
    )
    checksum_rows = [
        {"path": rel, "sha256": _sha256_path(job_dir / rel), "bytes": (job_dir / rel).stat().st_size}
        for rel in ("input_manifest.json", "run_log.jsonl", "output_manifest.json")
    ]
    (job_dir / "checksums.sha256").write_text(
        "".join(f"{row['sha256']}  {row['path']}\n" for row in checksum_rows),
        encoding="utf-8",
    )
    latest = job_root / "latest_job_id.txt"
    latest.write_text(job_id + "\n", encoding="utf-8")
    return verify_job_folder(job_dir)


def verify_job_folder(job_dir: Path) -> dict[str, Any]:
    required = {
        "input_manifest.json": (job_dir / "input_manifest.json").exists(),
        "run_log.jsonl": (job_dir / "run_log.jsonl").exists(),
        "output_manifest.json": (job_dir / "output_manifest.json").exists(),
        "checksums.sha256": (job_dir / "checksums.sha256").exists(),
    }
    checksums = _verify_checksums(job_dir)
    return {
        "pass": all(required.values()) and checksums["pass"],
        "reason": "PASS" if all(required.values()) and checksums["pass"] else "job_folder_contract_failed",
        "job_dir": str(job_dir),
        "required_paths": required,
        "checksum_self_test": checksums,
    }


def restore_package_smoke(package_path: Path) -> dict[str, Any]:
    if not package_path.exists():
        return {"pass": False, "reason": "package_missing", "required_paths": {}}
    with tempfile.TemporaryDirectory(prefix="workstation-package-restore-") as temp:
        root = Path(temp)
        with zipfile.ZipFile(package_path) as archive:
            archive.extractall(root)
        names = set()
        for item in root.rglob("*"):
            rel = item.relative_to(root).as_posix()
            names.add(f"{rel}/" if item.is_dir() else rel)
        required = {
            "ACCEPTANCE_PACKET.md": (root / "ACCEPTANCE_PACKET.md").exists(),
            "DELIVERY_INDEX.md": (root / "DELIVERY_INDEX.md").exists(),
            "REVISION_HISTORY.md": (root / "REVISION_HISTORY.md").exists(),
            "report.pdf": (root / "report.pdf").exists(),
            "viewer.html": (root / "viewer.html").exists(),
            "drawings/": (root / "drawings").is_dir(),
            "data/": (root / "data").is_dir(),
            "data/revision_policy.json": (root / "data" / "revision_policy.json").exists(),
            "data/redelivery_comparison_manifest.json": (root / "data" / "redelivery_comparison_manifest.json").exists(),
            "evidence/": (root / "evidence").is_dir(),
            "manifest.json": (root / "manifest.json").exists(),
            "checksums.sha256": (root / "checksums.sha256").exists(),
            "README_DELIVERY.md": (root / "README_DELIVERY.md").exists(),
        }
        viewer_text = (root / "viewer.html").read_text(encoding="utf-8", errors="replace") if required["viewer.html"] else ""
        viewer_shell_marker_pass = (
            "Structural Insight Viewer" in viewer_text
            or "structure-viewer" in viewer_text
            or "<html" in viewer_text.lower()
        )
        delivery_index_text = (
            (root / "DELIVERY_INDEX.md").read_text(encoding="utf-8", errors="replace")
            if required["DELIVERY_INDEX.md"]
            else ""
        )
        delivery_index_marker_pass = "Open Order" in delivery_index_text and "Acceptance Checklist" in delivery_index_text
        acceptance_text = (
            (root / "ACCEPTANCE_PACKET.md").read_text(encoding="utf-8", errors="replace")
            if required["ACCEPTANCE_PACKET.md"]
            else ""
        )
        acceptance_packet_marker_pass = (
            "Acceptance Decision" in acceptance_text
            and "Package Integrity" in acceptance_text
            and "Engineer Review Required" in acceptance_text
        )
        report_path = root / "report.pdf"
        pdf_magic_pass = report_path.read_bytes().startswith(b"%PDF-") if required["report.pdf"] else False
        manifest_payload = _load_json(root / "manifest.json") if required["manifest.json"] else {}
        output_rows = manifest_payload.get("output_rows", [])
        manifest_output_paths = {
            str(row.get("path", ""))
            for row in output_rows
            if isinstance(row, dict)
        } if isinstance(output_rows, list) else set()
        manifest_report_reference_pass = "report.pdf" in manifest_output_paths and "viewer.html" in manifest_output_paths
        manifest_acceptance_reference_pass = (
            "ACCEPTANCE_PACKET.md" in manifest_output_paths
            and "data/redelivery_comparison_manifest.json" in manifest_output_paths
        )
        manifest_claim_boundary_pass = "structural engineer review" in str(
            manifest_payload.get("package_claim_boundary", "")
        ).lower()
        revision_policy_pass = False
        if required["data/revision_policy.json"]:
            revision_policy = _load_json(root / "data" / "revision_policy.json")
            revision_policy_pass = (
                revision_policy.get("schema_version") == "workstation-delivery-revision-policy.v1"
                and bool(revision_policy.get("policy", {}).get("redelivery_requires_new_package", False))
            )
        redelivery_comparison_pass = False
        if required["data/redelivery_comparison_manifest.json"]:
            redelivery_comparison = _load_json(root / "data" / "redelivery_comparison_manifest.json")
            redelivery_comparison_pass = (
                redelivery_comparison.get("schema_version") == "workstation-delivery-redelivery-comparison.v1"
                and bool(redelivery_comparison.get("current_job_id"))
                and bool(redelivery_comparison.get("engineer_review_required", False))
                and bool(redelivery_comparison.get("redelivery_policy", {}).get("previous_packages_must_not_be_overwritten", False))
            )
        checksums = _verify_checksums(root)
        restore_pass = (
            all(required.values())
            and checksums["pass"]
            and viewer_shell_marker_pass
            and delivery_index_marker_pass
            and acceptance_packet_marker_pass
            and pdf_magic_pass
            and manifest_report_reference_pass
            and manifest_acceptance_reference_pass
            and manifest_claim_boundary_pass
            and revision_policy_pass
            and redelivery_comparison_pass
        )
        return {
            "pass": restore_pass,
            "reason": (
                "PASS"
                if restore_pass
                else "restore_checksum_viewer_pdf_manifest_index_or_revision_policy_failed"
            ),
            "required_paths": required,
            "checksum_self_test": checksums,
            "viewer_shell_marker_pass": viewer_shell_marker_pass,
            "delivery_index_marker_pass": delivery_index_marker_pass,
            "acceptance_packet_marker_pass": acceptance_packet_marker_pass,
            "pdf_magic_pass": pdf_magic_pass,
            "manifest_report_reference_pass": manifest_report_reference_pass,
            "manifest_acceptance_reference_pass": manifest_acceptance_reference_pass,
            "manifest_claim_boundary_pass": manifest_claim_boundary_pass,
            "revision_policy_pass": revision_policy_pass,
            "redelivery_comparison_pass": redelivery_comparison_pass,
            "zip_entry_count": len(names),
        }


def _input_hash(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(str(path).encode("utf-8"))
        if path.exists() and path.is_file():
            digest.update(_sha256_path(path).encode("utf-8"))
    return digest.hexdigest()[:16]


def _build_job_record(
    *,
    package_path: Path,
    input_refs: list[dict[str, Any]],
    manifest_rows: list[dict[str, Any]],
    timestamp: str | None = None,
    job_id: str | None = None,
    input_hash: str | None = None,
) -> dict[str, Any]:
    timestamp = timestamp or _now_utc_iso()
    resolved_job_id, resolved_input_hash = _job_identity(input_refs, timestamp)
    job_id = job_id or resolved_job_id
    input_hash = input_hash or resolved_input_hash
    return {
        "schema_version": JOB_SCHEMA_VERSION,
        "job_id": job_id,
        "generated_at": timestamp,
        "input_hash": input_hash,
        "run_log": [
            {
                "timestamp": timestamp,
                "command": "python3 scripts/build_workstation_delivery_package.py",
                "artifact_path": str(package_path),
                "status": "pass",
            }
        ],
        "input_manifest": input_refs,
        "output_manifest": manifest_rows,
    }


def build_workstation_delivery_package(
    *,
    out: Path = DEFAULT_PACKAGE_OUT,
    manifest_out: Path = DEFAULT_MANIFEST_OUT,
    job_record_out: Path = DEFAULT_JOB_RECORD_OUT,
    job_root: Path = DEFAULT_JOB_ROOT,
    viewer_html: Path = DEFAULT_VIEWER_HTML,
    report_pdf: Path = DEFAULT_REPORT_PDF,
    drawings_dir: Path = DEFAULT_DRAWINGS_DIR,
    client_validation_report: Path = DEFAULT_CLIENT_VALIDATION_REPORT,
    hardware_profile: Path = DEFAULT_HARDWARE_PROFILE,
    service_budget: Path = DEFAULT_SERVICE_BUDGET,
    viewer_browser_performance_probe: Path = DEFAULT_VIEWER_BROWSER_PERFORMANCE_PROBE,
    viewer_visual_regression_baseline: Path = DEFAULT_VIEWER_VISUAL_REGRESSION_BASELINE,
    support_bundle_manifest: Path = DEFAULT_SUPPORT_BUNDLE_MANIFEST,
    source_model: Path = DEFAULT_SOURCE_MODEL,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="workstation-delivery-build-") as temp:
        generated_at = _now_utc_iso()
        root = Path(temp)
        data_dir = root / "data"
        evidence_dir = root / "evidence"
        drawings_out = root / "drawings"
        data_dir.mkdir(parents=True, exist_ok=True)
        evidence_dir.mkdir(parents=True, exist_ok=True)
        drawings_out.mkdir(parents=True, exist_ok=True)

        viewer_source = viewer_html if viewer_html.exists() else DEFAULT_VIEWER_HTML_FALLBACK
        _copy_if_exists(viewer_source, root / "viewer.html")
        if report_pdf.exists():
            _copy_if_exists(report_pdf, root / "report.pdf")
            report_generated_fallback = False
        else:
            _write_minimal_pdf(root / "report.pdf")
            report_generated_fallback = True

        copied_drawings = []
        if drawings_dir.exists():
            for drawing in sorted(drawings_dir.glob("*.svg"))[:12]:
                destination = drawings_out / drawing.name
                if _copy_if_exists(drawing, destination):
                    copied_drawings.append(destination.relative_to(root).as_posix())
        if not copied_drawings:
            (drawings_out / "README_DRAWINGS.md").write_text(
                "No SVG drawing sheets were available for this package build.\n",
                encoding="utf-8",
            )

        data_sources = [
            ("client_input_validation_report.json", client_validation_report),
            ("workstation_hardware_profile.json", hardware_profile),
            ("workstation_service_budget.json", service_budget),
            ("source_model.json", source_model),
        ]
        evidence_sources = [
            ("viewer_browser_performance_probe.json", viewer_browser_performance_probe),
            ("viewer_visual_regression_baseline.json", viewer_visual_regression_baseline),
            ("support_bundle_manifest.json", support_bundle_manifest),
        ]
        for name, source in data_sources:
            _copy_if_exists(source, data_dir / name)
        for name, source in evidence_sources:
            _copy_if_exists(source, evidence_dir / name)

        input_refs = [
            {"label": "viewer_html", "path": str(viewer_source), "available": viewer_source.exists()},
            {"label": "report_pdf", "path": str(report_pdf), "available": report_pdf.exists()},
            {"label": "drawings_dir", "path": str(drawings_dir), "available": drawings_dir.exists()},
            {"label": "client_validation_report", "path": str(client_validation_report), "available": client_validation_report.exists()},
            {"label": "hardware_profile", "path": str(hardware_profile), "available": hardware_profile.exists()},
            {"label": "service_budget", "path": str(service_budget), "available": service_budget.exists()},
            {"label": "source_model", "path": str(source_model), "available": source_model.exists()},
        ]
        current_job_id, input_hash = _job_identity(input_refs, generated_at)
        previous_deliveries = _previous_delivery_rows(job_root)

        (root / "README_DELIVERY.md").write_text(_readme_text(), encoding="utf-8")
        (root / "DELIVERY_INDEX.md").write_text(_delivery_index_text(), encoding="utf-8")
        (root / "ACCEPTANCE_PACKET.md").write_text(
            _acceptance_packet_text(generated_at=generated_at, current_job_id=current_job_id),
            encoding="utf-8",
        )
        (root / "REVISION_HISTORY.md").write_text(_revision_history_text(generated_at), encoding="utf-8")
        (data_dir / "revision_policy.json").write_text(
            json.dumps(_revision_policy_payload(generated_at), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (data_dir / "redelivery_comparison_manifest.json").write_text(
            json.dumps(
                _redelivery_comparison_payload(
                    generated_at=generated_at,
                    current_job_id=current_job_id,
                    previous_deliveries=previous_deliveries,
                ),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        content_rows = _checksum_rows(root, include_manifest=False)
        manifest_inside = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": _now_utc_iso(),
            "current_job_id": current_job_id,
            "package_claim_boundary": CLAIM_BOUNDARY,
            "delivery_formats_v1": ["HTML", "PDF", "SVG", "JSON", "CSV"],
            "dxf_dwg_roundtrip": "v2_extension",
            "proxy_or_fallback": {
                "allowed": True,
                "explicitly_labeled": True,
                "report_pdf_generated_fallback": report_generated_fallback,
            },
            "input_refs": input_refs,
            "output_rows": content_rows,
        }
        (root / "manifest.json").write_text(
            json.dumps(manifest_inside, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        checksum_rows = _checksum_rows(root, include_manifest=True)
        _write_checksums(root, checksum_rows)
        _write_zip(root, out)

    restore = restore_package_smoke(out)
    manifest_rows = _zip_file_rows(out)
    manifest_consistency = verify_package_manifest_consistency(out)
    job_record = _build_job_record(
        package_path=out,
        input_refs=input_refs,
        manifest_rows=manifest_rows,
        timestamp=generated_at,
        job_id=current_job_id,
        input_hash=input_hash,
    )
    job_record_out.parent.mkdir(parents=True, exist_ok=True)
    job_record_out.write_text(json.dumps(job_record, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    job_folder_contract = _write_job_folder(job_root=job_root, job_record=job_record, package_path=out)

    required_sections = {
        "report.pdf": any(row["path"] == "report.pdf" for row in manifest_rows),
        "viewer.html": any(row["path"] == "viewer.html" for row in manifest_rows),
        "ACCEPTANCE_PACKET.md": any(row["path"] == "ACCEPTANCE_PACKET.md" for row in manifest_rows),
        "DELIVERY_INDEX.md": any(row["path"] == "DELIVERY_INDEX.md" for row in manifest_rows),
        "REVISION_HISTORY.md": any(row["path"] == "REVISION_HISTORY.md" for row in manifest_rows),
        "drawings": any(row["path"].startswith("drawings/") for row in manifest_rows),
        "data": any(row["path"].startswith("data/") for row in manifest_rows),
        "data/revision_policy.json": any(row["path"] == "data/revision_policy.json" for row in manifest_rows),
        "data/redelivery_comparison_manifest.json": any(row["path"] == "data/redelivery_comparison_manifest.json" for row in manifest_rows),
        "evidence": any(row["path"].startswith("evidence/") for row in manifest_rows),
        "manifest.json": any(row["path"] == "manifest.json" for row in manifest_rows),
        "checksums.sha256": any(row["path"] == "checksums.sha256" for row in manifest_rows),
        "README_DELIVERY.md": any(row["path"] == "README_DELIVERY.md" for row in manifest_rows),
    }
    blockers = [
        *(f"required_section_missing:{name}" for name, ok in required_sections.items() if not ok),
        *(["package_restore_smoke_failed"] if not restore["pass"] else []),
        *(["package_manifest_consistency_failed"] if not manifest_consistency["pass"] else []),
        *(["job_folder_contract_failed"] if not job_folder_contract["pass"] else []),
    ]
    contract_pass = not blockers
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_WORKSTATION_DELIVERY_PACKAGE_BLOCKED",
        "summary_line": (
            f"Workstation delivery package: {'PASS' if contract_pass else 'BLOCKED'} | "
            f"files={len(manifest_rows)} | restore={restore['pass']}"
        ),
        "package_path": str(out),
        "package_claim_boundary": CLAIM_BOUNDARY,
        "input_refs": input_refs,
        "required_sections": required_sections,
        "file_rows": manifest_rows,
        "checksum_self_test": restore.get("checksum_self_test", {}),
        "manifest_consistency_self_test": manifest_consistency,
        "restore_smoke": restore,
        "job_record": job_record,
        "job_record_path": str(job_record_out),
        "job_folder_contract": job_folder_contract,
        "blockers": blockers,
    }
    manifest_out.parent.mkdir(parents=True, exist_ok=True)
    manifest_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_PACKAGE_OUT)
    parser.add_argument("--manifest-out", type=Path, default=DEFAULT_MANIFEST_OUT)
    parser.add_argument("--job-record-out", type=Path, default=DEFAULT_JOB_RECORD_OUT)
    parser.add_argument("--job-root", type=Path, default=DEFAULT_JOB_ROOT)
    parser.add_argument("--viewer-html", type=Path, default=DEFAULT_VIEWER_HTML)
    parser.add_argument("--report-pdf", type=Path, default=DEFAULT_REPORT_PDF)
    parser.add_argument("--drawings-dir", type=Path, default=DEFAULT_DRAWINGS_DIR)
    parser.add_argument("--client-validation-report", type=Path, default=DEFAULT_CLIENT_VALIDATION_REPORT)
    parser.add_argument("--hardware-profile", type=Path, default=DEFAULT_HARDWARE_PROFILE)
    parser.add_argument("--service-budget", type=Path, default=DEFAULT_SERVICE_BUDGET)
    parser.add_argument("--viewer-browser-performance-probe", type=Path, default=DEFAULT_VIEWER_BROWSER_PERFORMANCE_PROBE)
    parser.add_argument("--viewer-visual-regression-baseline", type=Path, default=DEFAULT_VIEWER_VISUAL_REGRESSION_BASELINE)
    parser.add_argument("--support-bundle-manifest", type=Path, default=DEFAULT_SUPPORT_BUNDLE_MANIFEST)
    parser.add_argument("--source-model", type=Path, default=DEFAULT_SOURCE_MODEL)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_workstation_delivery_package(
        out=args.out,
        manifest_out=args.manifest_out,
        job_record_out=args.job_record_out,
        job_root=args.job_root,
        viewer_html=args.viewer_html,
        report_pdf=args.report_pdf,
        drawings_dir=args.drawings_dir,
        client_validation_report=args.client_validation_report,
        hardware_profile=args.hardware_profile,
        service_budget=args.service_budget,
        viewer_browser_performance_probe=args.viewer_browser_performance_probe,
        viewer_visual_regression_baseline=args.viewer_visual_regression_baseline,
        support_bundle_manifest=args.support_bundle_manifest,
        source_model=args.source_model,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else payload["summary_line"])
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
