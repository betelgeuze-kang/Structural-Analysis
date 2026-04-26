from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any
import zipfile

from implementation.phase1.hardest_external_10case_catalog import (
    REPO_ROOT,
    catalog_map,
    extract_case_kpis,
    load_case_payloads,
    primary_summary_head,
)


DEFAULT_EXECUTION_MANIFEST = Path(
    "implementation/phase1/release/external_benchmark_kickoff/external_benchmark_execution_manifest.json"
)
DEFAULT_RUNS_DIR = Path("implementation/phase1/release/external_benchmark_kickoff/runs")
DEFAULT_STATUS_UPDATER = Path("implementation/phase1/update_external_benchmark_execution_status.py")
DEFAULT_WIND_EXECUTOR = Path("implementation/phase1/build_wind_raw_mapping_artifact.py")
DEFAULT_RELEASE_SIGNING_KEY = Path("implementation/phase1/release/signing/release_registry_ed25519.pem")
DEFAULT_RELEASE_SIGNING_PUB = Path("implementation/phase1/release/signing/release_registry_ed25519.pub.pem")
DEFAULT_MIDAS_NATIVE_ROUNDTRIP_REPORT = Path(
    "implementation/phase1/release/midas_native_roundtrip/midas_native_writeback_diff_receipts_report.json"
)
DEFAULT_MIDAS_NATIVE_APPENDIX_MD = Path(
    "implementation/phase1/release/midas_native_roundtrip/unsupported_lossy_card_family_appendix.md"
)
DEFAULT_MIDAS_NATIVE_APPENDIX_JSON = Path(
    "implementation/phase1/release/midas_native_roundtrip/unsupported_lossy_card_family_appendix.json"
)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _truthy(report: dict[str, Any]) -> bool:
    if "contract_pass" in report:
        return bool(report.get("contract_pass", False))
    if "all_pass" in report:
        return bool(report.get("all_pass", False))
    if "pass" in report:
        return bool(report.get("pass", False))
    return False


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sign_manifest_bytes(payload: dict[str, Any], *, private_key: Path) -> str:
    with tempfile.NamedTemporaryFile(delete=False) as payload_file:
        payload_file.write(_canonical_bytes(payload))
        payload_path = Path(payload_file.name)
    sig_path = payload_path.with_suffix(".sig")
    try:
        proc = subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-sign",
                "-inkey",
                str(private_key),
                "-rawin",
                "-in",
                str(payload_path),
                "-out",
                str(sig_path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "openssl sign failed").strip())
        return base64.b64encode(sig_path.read_bytes()).decode("ascii")
    finally:
        payload_path.unlink(missing_ok=True)
        sig_path.unlink(missing_ok=True)


def _task_lookup(execution_manifest: dict[str, Any], task_id: str) -> dict[str, Any]:
    for bucket in ("ready_tasks", "blocked_tasks"):
        rows = execution_manifest.get(bucket) if isinstance(execution_manifest.get(bucket), list) else []
        for row in rows:
            if isinstance(row, dict) and str(row.get("task_id", "") or "") == task_id:
                return row
    return {}


def _load_midas_native_roundtrip_appendix() -> tuple[dict[str, Any], list[Path]]:
    report = _load_json(REPO_ROOT / DEFAULT_MIDAS_NATIVE_ROUNDTRIP_REPORT)
    batch_rows = report.get("structure_type_batches") if isinstance(report.get("structure_type_batches"), list) else []
    artifact_paths: list[Path] = []
    for candidate in (
        REPO_ROOT / DEFAULT_MIDAS_NATIVE_APPENDIX_MD,
        REPO_ROOT / DEFAULT_MIDAS_NATIVE_APPENDIX_JSON,
    ):
        if candidate.exists():
            artifact_paths.append(candidate)
    for row in batch_rows:
        if not isinstance(row, dict):
            continue
        batch_md = Path(str(row.get("batch_markdown", "") or "").strip())
        if not batch_md:
            continue
        resolved = batch_md if batch_md.is_absolute() else REPO_ROOT / batch_md
        if resolved.exists():
            artifact_paths.append(resolved)
    deduped: list[Path] = []
    seen: set[str] = set()
    for path in artifact_paths:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(path)
    return report, deduped


def _sanitize_task_id(task_id: str) -> str:
    return (
        task_id.replace("::", "_")
        .replace("/", "_")
        .replace("\\", "_")
        .replace(" ", "_")
        .strip("._")
        or "task"
    )


def _default_updates_json(execution_manifest_path: Path) -> Path:
    return execution_manifest_path.parent / "external_benchmark_execution_updates.json"


def _default_status_manifest_out(execution_manifest_path: Path) -> Path:
    return execution_manifest_path.parent / "external_benchmark_execution_status_manifest.json"


def _run_status_update(
    *,
    execution_manifest_path: Path,
    updates_json: Path,
    status_manifest_out: Path,
    task_id: str,
    lifecycle_status: str,
    note: str,
    artifact_path: Path,
    kpi_receipt_path: Path | None,
    case_bundle_dir: Path | None,
    case_bundle_zip_path: Path | None,
    bundle_id: str,
    refresh_release_surfaces: bool,
    dry_run: bool,
) -> tuple[int, dict[str, Any], str]:
    cmd = [
        sys.executable,
        str(DEFAULT_STATUS_UPDATER),
        "--execution-manifest",
        str(execution_manifest_path),
        "--updates-json",
        str(updates_json),
        "--status-manifest-out",
        str(status_manifest_out),
        "--task-id",
        task_id,
        "--set-status",
        lifecycle_status,
        "--note",
        note,
        "--artifact-path",
        str(artifact_path),
    ]
    if kpi_receipt_path is not None:
        cmd.extend(["--kpi-receipt-path", str(kpi_receipt_path)])
    if case_bundle_dir is not None:
        cmd.extend(["--case-bundle-dir", str(case_bundle_dir)])
    if case_bundle_zip_path is not None:
        cmd.extend(["--case-bundle-zip-path", str(case_bundle_zip_path)])
    if bundle_id.strip():
        cmd.extend(["--bundle-id", bundle_id])
    if refresh_release_surfaces:
        cmd.append("--refresh-release-surfaces")
    if dry_run:
        cmd.append("--dry-run")
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    try:
        payload = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except Exception:
        payload = {}
    return proc.returncode, payload, proc.stderr.strip()


def _execute_component_wind(
    *,
    task: dict[str, Any],
    run_dir: Path,
    midas_json: str,
    midas_conversion: str,
    wind_gate_report: str,
    dry_run: bool,
) -> tuple[bool, str, dict[str, Any], Path]:
    source_manifest_path = Path(str(task.get("input_path", "") or ""))
    source_manifest = _load_json(source_manifest_path)
    raw_wind_path = Path(str(source_manifest.get("data_path", "") or ""))
    result_path = run_dir / "benchmark_task_result.json"
    command = [
        sys.executable,
        str(DEFAULT_WIND_EXECUTOR),
        "--raw-wind",
        str(raw_wind_path),
        "--raw-wind-manifest",
        str(source_manifest_path),
        "--midas-json",
        str(midas_json),
        "--midas-conversion",
        str(midas_conversion),
        "--out",
        str(result_path),
    ]
    if str(wind_gate_report).strip():
        command.extend(["--wind-gate-report", str(wind_gate_report)])

    execution_payload: dict[str, Any] = {
        "executor": "build_wind_raw_mapping_artifact",
        "command": command,
        "source_manifest_path": str(source_manifest_path),
        "raw_wind_path": str(raw_wind_path),
    }

    if dry_run:
        execution_payload.update(
            {
                "contract_pass": True,
                "reason_code": "PASS_DRY_RUN",
                "summary": {"mode": "preview_only"},
            }
        )
        return True, "PASS_DRY_RUN", execution_payload, result_path

    run_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(command, check=False, capture_output=True, text=True)
    execution_payload["stdout"] = proc.stdout.strip()
    execution_payload["stderr"] = proc.stderr.strip()
    if proc.returncode != 0 or not result_path.exists():
        execution_payload["contract_pass"] = False
        execution_payload["reason_code"] = "ERR_WIND_EXECUTOR_FAILED"
        return False, "ERR_WIND_EXECUTOR_FAILED", execution_payload, result_path

    artifact = _load_json(result_path)
    execution_payload["artifact"] = artifact
    contract_pass = bool(artifact.get("contract_pass", False))
    reason_code = str(artifact.get("reason_code", "PASS" if contract_pass else "ERR_WIND_TASK_FAILED"))
    execution_payload["contract_pass"] = contract_pass
    execution_payload["reason_code"] = reason_code
    execution_payload["summary"] = artifact.get("summary", {})
    return contract_pass, reason_code, execution_payload, result_path


def _execute_component_hinge(
    *,
    task: dict[str, Any],
    run_dir: Path,
    dry_run: bool,
) -> tuple[bool, str, dict[str, Any], Path]:
    fixture_path = Path(str(task.get("input_path", "") or ""))
    result_path = run_dir / "benchmark_task_result.json"
    fixture = _load_json(fixture_path) if fixture_path.exists() else {}
    execution_payload: dict[str, Any] = {
        "executor": "peer_spd_hinge_fixture_validation",
        "fixture_path": str(fixture_path),
    }

    if dry_run:
        execution_payload.update(
            {
                "contract_pass": True,
                "reason_code": "PASS_DRY_RUN",
                "summary": {"mode": "preview_only"},
            }
        )
        return True, "PASS_DRY_RUN", execution_payload, result_path

    specimen_summary = fixture.get("specimen_summary") if isinstance(fixture.get("specimen_summary"), dict) else {}
    hysteresis_summary = fixture.get("hysteresis_summary") if isinstance(fixture.get("hysteresis_summary"), dict) else {}
    hinge_refresh_targets = (
        fixture.get("hinge_refresh_targets") if isinstance(fixture.get("hinge_refresh_targets"), dict) else {}
    )
    point_count = int(hysteresis_summary.get("point_count", 0) or 0)
    peak_abs_drift_ratio = float(hysteresis_summary.get("peak_abs_drift_ratio", 0.0) or 0.0)
    contract_pass = bool(
        fixture_path.exists()
        and bool(fixture.get("contract_pass", False))
        and str(fixture.get("seed_id", "") or "") == str(task.get("task_id", "") or "").split("::", 1)[-1]
        and point_count > 0
        and str(specimen_summary.get("specimen_id", "") or "")
    )
    reason_code = "PASS" if contract_pass else "ERR_HINGE_FIXTURE_INVALID"
    artifact_payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "summary": {
            "seed_id": str(fixture.get("seed_id", "") or ""),
            "holdout_split": str(fixture.get("holdout_split", "") or ""),
            "specimen_id": str(specimen_summary.get("specimen_id", "") or ""),
            "point_count": point_count,
            "peak_abs_drift_ratio": peak_abs_drift_ratio,
            "rebar_sensitive_expected": bool(hinge_refresh_targets.get("rebar_sensitive_expected", False)),
            "confinement_sensitive_expected": bool(hinge_refresh_targets.get("confinement_sensitive_expected", False)),
            "axial_load_sensitive_expected": bool(hinge_refresh_targets.get("axial_load_sensitive_expected", False)),
        },
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(result_path, artifact_payload)
    execution_payload["artifact"] = artifact_payload
    execution_payload["summary"] = artifact_payload["summary"]
    execution_payload["contract_pass"] = contract_pass
    execution_payload["reason_code"] = reason_code
    return contract_pass, reason_code, execution_payload, result_path


def _execute_system_anchor(
    *,
    task: dict[str, Any],
    run_dir: Path,
    dry_run: bool,
) -> tuple[bool, str, dict[str, Any], Path]:
    report_path = Path(str(task.get("input_path", "") or ""))
    result_path = run_dir / "benchmark_task_result.json"
    report_payload = _load_json(report_path) if report_path.exists() else {}
    execution_payload: dict[str, Any] = {
        "executor": "system_anchor_report_validation",
        "report_path": str(report_path),
    }

    if dry_run:
        execution_payload.update(
            {
                "contract_pass": True,
                "reason_code": "PASS_DRY_RUN",
                "summary": {"mode": "preview_only"},
            }
        )
        return True, "PASS_DRY_RUN", execution_payload, result_path

    report_summary = report_payload.get("summary") if isinstance(report_payload.get("summary"), dict) else {}
    contract_pass = bool(report_path.exists() and bool(report_payload.get("contract_pass", False)))
    reason_code = str(report_payload.get("reason_code", "PASS" if contract_pass else "ERR_SYSTEM_ANCHOR_INVALID"))
    artifact_payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "summary": {
            "benchmark_family": str(task.get("benchmark_family", "") or ""),
            "source_report_path": str(report_path),
            "case_count": int(report_summary.get("case_count", report_summary.get("selected_case_count", 0)) or 0),
            "summary_head": {
                key: report_summary.get(key)
                for key in list(report_summary.keys())[:8]
            },
        },
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(result_path, artifact_payload)
    execution_payload["artifact"] = artifact_payload
    execution_payload["summary"] = artifact_payload["summary"]
    execution_payload["contract_pass"] = contract_pass
    execution_payload["reason_code"] = reason_code
    return contract_pass, reason_code, execution_payload, result_path


def _execute_hardest_case(
    *,
    task: dict[str, Any],
    run_dir: Path,
    dry_run: bool,
) -> tuple[bool, str, dict[str, Any], Path]:
    case_id = str(task.get("case_id", "") or "")
    case_catalog = catalog_map()
    case_row = case_catalog.get(case_id, {})
    result_path = run_dir / "benchmark_task_result.json"
    kpi_receipt_json = run_dir / "benchmark_task_kpi_receipt.json"
    kpi_receipt_md = run_dir / "benchmark_task_kpi_receipt.md"
    bundle_dir = run_dir / "signed_case_bundle"
    bundle_manifest_path = bundle_dir / "case_bundle_manifest.json"
    bundle_signature_path = bundle_dir / "case_bundle_manifest.signature.b64"
    bundle_zip_path = run_dir / "signed_case_bundle.zip"

    execution_payload: dict[str, Any] = {
        "executor": "hardest_external_case_receipt_and_bundle",
        "case_id": case_id,
        "case_label": str(task.get("case_label", "") or ""),
    }
    if not case_row:
        execution_payload["contract_pass"] = False
        execution_payload["reason_code"] = "ERR_UNKNOWN_HARDEST_CASE"
        return False, "ERR_UNKNOWN_HARDEST_CASE", execution_payload, result_path

    if dry_run:
        execution_payload.update(
            {
                "contract_pass": True,
                "reason_code": "PASS_DRY_RUN",
                "summary": {"mode": "preview_only", "case_id": case_id},
                "kpi_receipt_path": str(kpi_receipt_json),
                "case_bundle_dir": str(bundle_dir),
                "case_bundle_zip_path": str(bundle_zip_path),
                "bundle_id": f"{case_id}-preview",
            }
        )
        return True, "PASS_DRY_RUN", execution_payload, result_path

    primary_payload, supporting_payloads = load_case_payloads(case_row)
    supporting_status = {
        role: _truthy(payload) for role, payload in supporting_payloads.items()
    }
    contract_pass = bool(_truthy(primary_payload) and all(supporting_status.values()))
    reason_code = "PASS" if contract_pass else "ERR_HARDEST_CASE_SOURCE_INVALID"
    kpi_rows = extract_case_kpis(case_row, primary_payload, supporting_payloads)
    supporting_artifacts = []
    for role, raw_path in (case_row.get("supporting_reports") or {}).items():
        report_path = Path(str(raw_path))
        supporting_artifacts.append(
            {
                "role": str(role),
                "path": str(report_path),
                "reason_code": str(supporting_payloads.get(role, {}).get("reason_code", "") or ""),
                "contract_pass": bool(supporting_status.get(role, False)),
            }
        )
    native_roundtrip_report, native_roundtrip_appendix_artifacts = _load_midas_native_roundtrip_appendix()
    native_roundtrip_summary = (
        native_roundtrip_report.get("summary")
        if isinstance(native_roundtrip_report.get("summary"), dict)
        else {}
    )
    native_roundtrip_summary_line = str(native_roundtrip_report.get("summary_line", "") or "").strip()

    receipt_payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "case_id": case_id,
        "case_label": str(case_row.get("label", "") or ""),
        "benchmark_family": str(case_row.get("benchmark_family", "") or ""),
        "hazard_family": str(case_row.get("hazard_family", "") or ""),
        "topology_family": str(case_row.get("topology_family", "") or ""),
        "load_path_family": str(case_row.get("load_path_family", "") or ""),
        "primary_report": {
            "path": str(case_row.get("primary_report_path", "") or ""),
            "reason_code": str(primary_payload.get("reason_code", "") or ""),
            "contract_pass": bool(_truthy(primary_payload)),
            "summary_head": primary_summary_head(primary_payload),
        },
        "supporting_reports": supporting_artifacts,
        "kpi_rows": kpi_rows,
        "summary": {
            "kpi_count": len(kpi_rows),
            "supporting_report_count": len(supporting_artifacts),
        },
        "native_midas_roundtrip_appendix": {
            "summary_line": native_roundtrip_summary_line,
            "public_native_ready_count": int(native_roundtrip_summary.get("public_native_writeback_ready_count", 0) or 0),
            "public_preview_ready_count": int(
                native_roundtrip_summary.get("public_archive_preview_writeback_ready_count", 0) or 0
            ),
            "public_source_ready_count": int(native_roundtrip_summary.get("public_source_writeback_ready_count", 0) or 0),
            "structure_type_count": int(native_roundtrip_summary.get("structure_type_count", 0) or 0),
            "appendix_markdown": str(DEFAULT_MIDAS_NATIVE_APPENDIX_MD),
            "appendix_json": str(DEFAULT_MIDAS_NATIVE_APPENDIX_JSON),
            "batch_markdowns": [str(path.relative_to(REPO_ROOT)) for path in native_roundtrip_appendix_artifacts if path.suffix == ".md"],
        },
    }
    receipt_lines = [
        "# Hardest External Benchmark Case KPI Receipt",
        "",
        f"- `case_id`: `{case_id}`",
        f"- `case_label`: `{case_row.get('label', '')}`",
        f"- `benchmark_family`: `{case_row.get('benchmark_family', '')}`",
        f"- `hazard_family`: `{case_row.get('hazard_family', '')}`",
        f"- `topology_family`: `{case_row.get('topology_family', '')}`",
        f"- `load_path_family`: `{case_row.get('load_path_family', '')}`",
        f"- `primary_report`: `{case_row.get('primary_report_path', '')}`",
        "",
        "## KPI Rows",
        "",
        "| KPI | Value | Source |",
        "|---|---|---|",
    ]
    for row in kpi_rows:
        receipt_lines.append(
            f"| {row['label']} | {row['value']} | {row['source']} |"
        )
    if native_roundtrip_summary_line:
        receipt_lines.extend(
            [
                "",
                "## Appendix: MIDAS Native Roundtrip / Write-Back",
                "",
                f"- `summary`: `{native_roundtrip_summary_line}`",
                (
                    "- `honest_counts`: "
                    f"public_native_ready={int(native_roundtrip_summary.get('public_native_writeback_ready_count', 0) or 0)} | "
                    f"public_preview_ready={int(native_roundtrip_summary.get('public_archive_preview_writeback_ready_count', 0) or 0)} | "
                    f"public_source_ready={int(native_roundtrip_summary.get('public_source_writeback_ready_count', 0) or 0)} | "
                    f"structure_types={int(native_roundtrip_summary.get('structure_type_count', 0) or 0)}"
                ),
                f"- `appendix_md`: `{DEFAULT_MIDAS_NATIVE_APPENDIX_MD}`",
                f"- `appendix_json`: `{DEFAULT_MIDAS_NATIVE_APPENDIX_JSON}`",
            ]
        )
        batch_markdowns = [
            path for path in native_roundtrip_appendix_artifacts if path.suffix == ".md" and path.name != DEFAULT_MIDAS_NATIVE_APPENDIX_MD.name
        ]
        if batch_markdowns:
            receipt_lines.append("- `structure_type_batches`:")
            for path in batch_markdowns:
                receipt_lines.append(f"  - `{path.relative_to(REPO_ROOT)}`")
    receipt_text = "\n".join(receipt_lines) + "\n"

    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(kpi_receipt_json, receipt_payload)
    _write_text(kpi_receipt_md, receipt_text)
    _write_json(result_path, receipt_payload)

    bundle_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{case_id}"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    copied_artifacts: list[dict[str, Any]] = []
    for src in [(REPO_ROOT / str(case_row.get("primary_report_path", "") or "")).resolve()] + [
        (REPO_ROOT / str(path)).resolve()
        for path in (case_row.get("supporting_reports") or {}).values()
    ]:
        if not src.exists():
            continue
        dst = bundle_dir / src.name
        shutil.copy2(src, dst)
        copied_artifacts.append(
            {
                "path": str(dst),
                "source_path": str(src),
                "sha256": _sha256_file(dst),
                "bytes": int(dst.stat().st_size),
            }
        )
    shutil.copy2(kpi_receipt_json, bundle_dir / kpi_receipt_json.name)
    shutil.copy2(kpi_receipt_md, bundle_dir / kpi_receipt_md.name)
    if DEFAULT_RELEASE_SIGNING_PUB.exists():
        shutil.copy2(DEFAULT_RELEASE_SIGNING_PUB, bundle_dir / DEFAULT_RELEASE_SIGNING_PUB.name)
    for src in native_roundtrip_appendix_artifacts:
        dst = bundle_dir / src.name
        shutil.copy2(src, dst)
        copied_artifacts.append(
            {
                "path": str(dst),
                "source_path": str(src),
                "sha256": _sha256_file(dst),
                "bytes": int(dst.stat().st_size),
            }
        )
    bundle_manifest = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bundle_id": bundle_id,
        "case_id": case_id,
        "case_label": str(case_row.get("label", "") or ""),
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "artifacts": copied_artifacts
        + [
            {
                "path": str(bundle_dir / kpi_receipt_json.name),
                "source_path": str(kpi_receipt_json),
                "sha256": _sha256_file(kpi_receipt_json),
                "bytes": int(kpi_receipt_json.stat().st_size),
            },
            {
                "path": str(bundle_dir / kpi_receipt_md.name),
                "source_path": str(kpi_receipt_md),
                "sha256": _sha256_file(kpi_receipt_md),
                "bytes": int(kpi_receipt_md.stat().st_size),
            },
            {
                "path": str(bundle_dir / DEFAULT_RELEASE_SIGNING_PUB.name),
                "source_path": str(DEFAULT_RELEASE_SIGNING_PUB),
                "sha256": _sha256_file(DEFAULT_RELEASE_SIGNING_PUB),
                "bytes": int(DEFAULT_RELEASE_SIGNING_PUB.stat().st_size),
            }
            if DEFAULT_RELEASE_SIGNING_PUB.exists()
            else {},
        ],
    }
    bundle_manifest["artifacts"] = [
        row for row in bundle_manifest["artifacts"] if isinstance(row, dict) and row
    ]
    _write_json(bundle_manifest_path, bundle_manifest)
    signature_b64 = _sign_manifest_bytes(
        bundle_manifest,
        private_key=DEFAULT_RELEASE_SIGNING_KEY,
    )
    _write_text(bundle_signature_path, signature_b64 + "\n")
    with zipfile.ZipFile(bundle_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in bundle_dir.rglob("*"):
            if path.is_file():
                zf.write(path, arcname=path.relative_to(bundle_dir))

    execution_payload["artifact"] = receipt_payload
    execution_payload["summary"] = {
        "kpi_count": len(kpi_rows),
        "bundle_id": bundle_id,
        "supporting_report_count": len(supporting_artifacts),
    }
    execution_payload["contract_pass"] = contract_pass
    execution_payload["reason_code"] = reason_code
    execution_payload["kpi_receipt_path"] = str(kpi_receipt_json)
    execution_payload["case_bundle_dir"] = str(bundle_dir)
    execution_payload["case_bundle_zip_path"] = str(bundle_zip_path)
    execution_payload["bundle_id"] = bundle_id
    execution_payload["bundle_signature_path"] = str(bundle_signature_path)
    execution_payload["bundle_manifest_path"] = str(bundle_manifest_path)
    execution_payload["bundle_public_key_path"] = str(DEFAULT_RELEASE_SIGNING_PUB)
    return contract_pass, reason_code, execution_payload, result_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution-manifest", default=str(DEFAULT_EXECUTION_MANIFEST))
    parser.add_argument("--runs-dir", default=str(DEFAULT_RUNS_DIR))
    parser.add_argument("--updates-json", default="")
    parser.add_argument("--status-manifest-out", default="")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--note", default="")
    parser.add_argument("--midas-json", default="implementation/phase1/midas_model.json")
    parser.add_argument("--midas-conversion", default="implementation/phase1/midas_mgt_conversion_report.json")
    parser.add_argument("--wind-gate-report", default="implementation/phase1/wind_time_history_gate_report.json")
    parser.add_argument("--refresh-release-surfaces", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=False)
    args = parser.parse_args()

    execution_manifest_path = Path(args.execution_manifest)
    execution_manifest = _load_json(execution_manifest_path)
    if not execution_manifest:
        raise SystemExit(f"invalid execution manifest: {execution_manifest_path}")

    updates_json = Path(str(args.updates_json).strip() or _default_updates_json(execution_manifest_path))
    status_manifest_out = Path(
        str(args.status_manifest_out).strip() or _default_status_manifest_out(execution_manifest_path)
    )
    task_id = str(args.task_id).strip()
    task = _task_lookup(execution_manifest, task_id)
    if not task:
        report = {
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_TASK_NOT_FOUND",
            "task_id": task_id,
            "execution_manifest": str(execution_manifest_path),
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    run_dir = Path(args.runs_dir) / _sanitize_task_id(task_id)
    execution_log_json = run_dir / "benchmark_task_execution.json"
    execution_log_md = run_dir / "benchmark_task_execution.md"
    benchmark_family = str(task.get("benchmark_family", "") or "")
    phase = str(task.get("phase", "") or "")

    if benchmark_family == "tpu_raw_hffb_mapping" and phase == "component_wind":
        contract_pass, reason_code, execution_payload, artifact_path = _execute_component_wind(
            task=task,
            run_dir=run_dir,
            midas_json=str(args.midas_json),
            midas_conversion=str(args.midas_conversion),
            wind_gate_report=str(args.wind_gate_report),
            dry_run=bool(args.dry_run),
        )
    elif benchmark_family == "peer_spd_column_hinge" and phase == "component_hinge":
        contract_pass, reason_code, execution_payload, artifact_path = _execute_component_hinge(
            task=task,
            run_dir=run_dir,
            dry_run=bool(args.dry_run),
        )
    elif phase == "system_anchor":
        contract_pass, reason_code, execution_payload, artifact_path = _execute_system_anchor(
            task=task,
            run_dir=run_dir,
            dry_run=bool(args.dry_run),
        )
    elif phase == "hardest_case":
        contract_pass, reason_code, execution_payload, artifact_path = _execute_hardest_case(
            task=task,
            run_dir=run_dir,
            dry_run=bool(args.dry_run),
        )
    else:
        report = {
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_UNSUPPORTED_BENCHMARK_FAMILY",
            "task_id": task_id,
            "benchmark_family": benchmark_family,
            "phase": phase,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    now = datetime.now(timezone.utc).isoformat()
    task_note = str(args.note or f"executed {benchmark_family}")
    lifecycle_status = "completed" if contract_pass else "failed"

    execution_log = {
        "schema_version": "1.0",
        "generated_at": now,
        "task_id": task_id,
        "phase": phase,
        "benchmark_family": benchmark_family,
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "note": task_note,
        "artifact_path": str(artifact_path),
        "execution_payload": execution_payload,
    }
    if not args.dry_run:
        run_dir.mkdir(parents=True, exist_ok=True)
        _write_json(execution_log_json, execution_log)
        execution_log_md.write_text(json.dumps(execution_log, ensure_ascii=False, indent=2), encoding="utf-8")

    rc, update_report, update_stderr = _run_status_update(
        execution_manifest_path=execution_manifest_path,
        updates_json=updates_json,
        status_manifest_out=status_manifest_out,
        task_id=task_id,
        lifecycle_status=lifecycle_status,
        note=task_note,
        artifact_path=artifact_path,
        kpi_receipt_path=(
            Path(str(execution_payload.get("kpi_receipt_path", "") or ""))
            if str(execution_payload.get("kpi_receipt_path", "") or "").strip()
            else None
        ),
        case_bundle_dir=(
            Path(str(execution_payload.get("case_bundle_dir", "") or ""))
            if str(execution_payload.get("case_bundle_dir", "") or "").strip()
            else None
        ),
        case_bundle_zip_path=(
            Path(str(execution_payload.get("case_bundle_zip_path", "") or ""))
            if str(execution_payload.get("case_bundle_zip_path", "") or "").strip()
            else None
        ),
        bundle_id=str(execution_payload.get("bundle_id", "") or ""),
        refresh_release_surfaces=bool(args.refresh_release_surfaces),
        dry_run=bool(args.dry_run),
    )

    report = {
        "schema_version": "1.0",
        "generated_at": now,
        "contract_pass": contract_pass and rc == 0,
        "reason_code": reason_code if rc == 0 else "ERR_STATUS_UPDATE_FAILED",
        "dry_run": bool(args.dry_run),
        "task_id": task_id,
        "benchmark_family": benchmark_family,
        "phase": phase,
        "run_dir": str(run_dir),
        "execution_log_json": str(execution_log_json),
        "execution_log_md": str(execution_log_md),
        "artifact_path": str(artifact_path),
        "kpi_receipt_path": str(execution_payload.get("kpi_receipt_path", "") or ""),
        "case_bundle_dir": str(execution_payload.get("case_bundle_dir", "") or ""),
        "case_bundle_zip_path": str(execution_payload.get("case_bundle_zip_path", "") or ""),
        "bundle_id": str(execution_payload.get("bundle_id", "") or ""),
        "lifecycle_status_set": lifecycle_status,
        "update_report": update_report,
    }
    if rc != 0:
        report["status_update_stderr"] = update_stderr
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
