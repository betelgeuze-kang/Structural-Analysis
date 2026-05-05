#!/usr/bin/env python3
"""Materialize the clean-checkout evidence chain for release/P1 readiness."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "clean_checkout_evidence_chain.v1"
PUBLICATION_EVIDENCE_INDEX_SCHEMA = "release-publication-evidence-index.v1"
DEFAULT_EXTERNAL_BENCHMARK_SUBMISSION_READINESS = Path(
    "implementation/phase1/release/external_benchmark_submission_readiness.json"
)
DEFAULT_EXTERNAL_BENCHMARK_SUBMISSION_UPDATES = Path(
    "implementation/phase1/release_evidence/productization/external_benchmark_submission_updates.json"
)
DEFAULT_RESIDUAL_HOLDOUT_CLOSURE_UPDATES = Path(
    "implementation/phase1/release_evidence/productization/residual_holdout_closure_updates.json"
)
EXPECTED_EXTERNAL_BENCHMARK_UPDATE_IDS = (
    "hardest_external_10case",
    "tpu_hffb",
    "peer_spd_hinge",
    "korean_public_structures",
)
EXPECTED_RESIDUAL_HOLDOUT_UPDATE_IDS = ("RH-001", "RH-002", "RH-003")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _publication_index_paths(path: Path | None) -> dict[str, Path]:
    if path is None:
        return {}
    payload = _load_json(path)
    if payload.get("schema_version") != PUBLICATION_EVIDENCE_INDEX_SCHEMA:
        raise ValueError(f"publication evidence index has unsupported schema: {path}")
    paths = payload.get("paths")
    if not isinstance(paths, dict):
        raise ValueError(f"publication evidence index paths must be an object: {path}")

    def resolve(key: str, value: object) -> tuple[str, Path] | None:
        if not value:
            return None
        candidate = Path(str(value))
        if candidate.exists():
            return key, candidate
        sibling = path.parent / candidate.name
        return key, sibling if sibling.exists() else candidate

    resolved: dict[str, Path] = {}
    for key in (
        "p0_status_json",
        "manifest",
        "release_assets_json",
        "artifact_root",
        "upload_plan_json",
        "metadata_preflight_json",
        "post_publish_roundtrip_json",
    ):
        entry = resolve(key, paths.get(key))
        if entry is not None:
            resolved[entry[0]] = entry[1]
    if "p0_status_json" in resolved:
        resolved["p0_status"] = resolved["p0_status_json"]
    return resolved


def _compact_summary(summary: object) -> dict[str, Any]:
    if not isinstance(summary, dict):
        return {}
    compact: dict[str, Any] = {}
    for key, value in summary.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            compact[str(key)] = value
    return compact


def _json_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "ok": False, "path": str(path)}
    try:
        payload = _load_json(path)
    except Exception as exc:
        return {"exists": True, "ok": False, "path": str(path), "reason": f"invalid_json: {exc}"}
    return {
        "exists": True,
        "ok": bool(payload.get("contract_pass", payload.get("pass", payload.get("ok", False)))),
        "path": str(path),
        "reason_code": str(payload.get("reason_code", "") or ""),
        "summary": _compact_summary(payload.get("summary")),
    }


def _materialize_evidence(
    *,
    label: str,
    source: Path,
    destination: Path,
    force: bool,
) -> dict[str, Any]:
    if destination.exists() and not force:
        summary = _json_summary(destination)
        summary.update(
            {
                "label": label,
                "source_evidence": str(source),
                "hydrated_from_source": False,
            }
        )
        return summary

    if not source.exists():
        return {
            "label": label,
            "exists": destination.exists(),
            "ok": False,
            "path": str(destination),
            "source_evidence": str(source),
            "hydrated_from_source": False,
            "reason": "source_evidence_missing",
        }

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    summary = _json_summary(destination)
    summary.update(
        {
            "label": label,
            "source_evidence": str(source),
            "hydrated_from_source": True,
        }
    )
    return summary


def _extract_update_ids(payload: dict[str, Any]) -> tuple[set[str], int]:
    rows: Any = payload.get("updates", payload.get("submission_updates", payload.get("residual_holdout_updates", payload)))
    if isinstance(rows, dict) and "external_benchmark_submission_work_items" in rows:
        rows = rows.get("external_benchmark_submission_work_items", [])
    elif isinstance(rows, dict) and "residual_holdout_work_items" in rows:
        rows = rows.get("residual_holdout_work_items", [])
    elif rows is payload and isinstance(payload.get("queues"), dict):
        queue_payload = payload["queues"]
        if isinstance(queue_payload, dict):
            rows = (
                queue_payload.get("external_benchmark_submission_work_items")
                or queue_payload.get("residual_holdout_work_items")
                or queue_payload
            )
    elif rows is payload:
        rows = payload.get("submission_queue", payload.get("residual_holdout_work_items", payload))

    update_ids: set[str] = set()
    update_count = 0
    if isinstance(rows, dict):
        update_count = len(rows)
        for row_id, row in rows.items():
            update_ids.add(str(row_id))
            if isinstance(row, dict):
                for key in ("queue_id", "work_item_id", "category_id", "id", "submission_id"):
                    value = str(row.get(key, "") or "").strip()
                    if value:
                        update_ids.add(value)
    elif isinstance(rows, list):
        update_count = len([row for row in rows if isinstance(row, dict)])
        for row in rows:
            if not isinstance(row, dict):
                continue
            for key in ("queue_id", "work_item_id", "category_id", "id", "submission_id"):
                value = str(row.get(key, "") or "").strip()
                if value:
                    update_ids.add(value)
    return update_ids, update_count


def _json_summary_or_present(
    path: Path,
    *,
    ok_when_present: bool = False,
    expected_update_ids: tuple[str, ...] = (),
) -> dict[str, Any]:
    summary = _json_summary(path)
    if not summary.get("exists") or "reason" in summary:
        return summary
    if expected_update_ids:
        payload = _load_json(path)
        update_ids, update_count = _extract_update_ids(payload)
        missing_update_ids = sorted(set(expected_update_ids) - update_ids)
        summary.update(
            {
                "update_count": update_count,
                "expected_update_count": len(expected_update_ids),
                "missing_update_ids": missing_update_ids,
                "all_expected_updates_present": not missing_update_ids,
            }
        )
        summary["ok"] = not missing_update_ids
    elif ok_when_present:
        summary["ok"] = True
    return summary


def _materialize_package_json(
    *,
    label: str,
    source_artifact_root: Path | None,
    destination: Path,
    direct_asset_name: str,
    package_member: str,
    force: bool,
    ok_when_present: bool = False,
    expected_update_ids: tuple[str, ...] = (),
) -> dict[str, Any]:
    if destination.exists() and not force and source_artifact_root is None:
        summary = _json_summary_or_present(
            destination,
            ok_when_present=ok_when_present,
            expected_update_ids=expected_update_ids,
        )
        summary.update(
            {
                "label": label,
                "source_evidence": str(destination),
                "hydrated_from_source": False,
            }
        )
        return summary

    if source_artifact_root is None:
        return {
            "label": label,
            "exists": destination.exists(),
            "ok": False,
            "path": str(destination),
            "source_evidence": "",
            "hydrated_from_source": False,
            "reason": "publication_artifact_root_missing",
        }

    direct_source = source_artifact_root / direct_asset_name
    package_source = source_artifact_root / "project_package.zip"
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_evidence = ""
    try:
        if direct_source.exists():
            shutil.copyfile(direct_source, destination)
            source_evidence = str(direct_source)
        elif package_source.exists():
            with zipfile.ZipFile(package_source) as archive:
                with archive.open(package_member) as handle:
                    destination.write_bytes(handle.read())
            source_evidence = str(package_source)
        else:
            return {
                "label": label,
                "exists": destination.exists(),
                "ok": False,
                "path": str(destination),
                "source_evidence": str(source_artifact_root),
                "hydrated_from_source": False,
                "reason": f"{direct_asset_name}_source_missing",
            }
    except (KeyError, OSError, zipfile.BadZipFile) as exc:
        return {
            "label": label,
            "exists": destination.exists(),
            "ok": False,
            "path": str(destination),
            "source_evidence": str(package_source),
            "hydrated_from_source": False,
            "reason": f"{direct_asset_name}_hydration_failed: {exc}",
        }

    summary = _json_summary_or_present(
        destination,
        ok_when_present=ok_when_present,
        expected_update_ids=expected_update_ids,
    )
    summary.update(
        {
            "label": label,
            "source_evidence": source_evidence,
            "hydrated_from_source": True,
        }
    )
    return summary


def _materialize_external_submission_readiness(
    *,
    source_artifact_root: Path | None,
    destination: Path,
    force: bool,
) -> dict[str, Any]:
    return _materialize_package_json(
        label="external benchmark submission readiness",
        source_artifact_root=source_artifact_root,
        destination=destination,
        direct_asset_name="external_benchmark_submission_readiness.json",
        package_member="artifacts/external_benchmark_submission_readiness.json",
        force=force,
    )


def _p1_sidecar_final_summary(
    *,
    label: str,
    path: Path,
    expected_update_ids: tuple[str, ...],
    preflight_summary: dict[str, Any],
    preflight_keys: tuple[str, ...],
    updated_by_intake: bool,
) -> dict[str, Any]:
    summary = _json_summary_or_present(
        path,
        ok_when_present=True,
        expected_update_ids=expected_update_ids,
    )
    summary.update(
        {
            "label": label,
            "final_sidecar_state": True,
            "updated_by_p1_evidence_intake": updated_by_intake,
        }
    )
    for key in preflight_keys:
        if key in preflight_summary:
            summary[key] = preflight_summary[key]
    return summary


def _run_command(command: list[str]) -> dict[str, Any]:
    proc = subprocess.run(command, check=False, capture_output=True, text=True)
    return {
        "command": command,
        "returncode": proc.returncode,
        "ok": proc.returncode == 0,
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
    }


def _run_json_command(command: list[str]) -> dict[str, Any]:
    proc = subprocess.run(command, check=False, capture_output=True, text=True)
    result = {
        "command": command,
        "returncode": proc.returncode,
        "ok": proc.returncode == 0,
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
    }
    payload: dict[str, Any] = {}
    if proc.stdout:
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {}
    result["json"] = payload
    return result


def _commercial_scope(path: Path) -> dict[str, Any]:
    payload = _load_json(path) if path.exists() else {}
    grade = payload.get("grade") if isinstance(payload.get("grade"), dict) else {}
    deployment = payload.get("deployment_model") if isinstance(payload.get("deployment_model"), dict) else {}
    return {
        "grade": str(grade.get("label", "unknown") or "unknown"),
        "commercial_pass": bool(grade.get("commercial_pass", payload.get("contract_pass", False))),
        "engineer_in_loop_accelerated_coverage_ready": bool(
            deployment.get("engineer_in_loop_accelerated_coverage_ready", False)
        ),
        "full_commercial_replacement_ready": bool(deployment.get("full_commercial_replacement_ready", False)),
        "accelerated_coverage_target_pct_range": deployment.get("accelerated_coverage_target_pct_range", []),
        "residual_holdout_target_pct_range": deployment.get("residual_holdout_target_pct_range", []),
    }


def build_chain(args: argparse.Namespace) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    index_paths = _publication_index_paths(args.publication_evidence_index)
    p0_status_path = args.p0_status or index_paths.get("p0_status")
    publication_step: dict[str, Any] | None = None

    if args.publication_evidence_index is not None and "release_assets_json" in index_paths:
        publication_cmd = [
            sys.executable,
            "scripts/check_p0_closure_status.py",
            "--publication-evidence-index",
            str(args.publication_evidence_index),
            "--json",
            "--fail-open",
        ]
        publication_step = _run_json_command(publication_cmd)
        publication_step.update({"label": "release publication evidence status"})
        steps.append(publication_step)

    midas_step = _materialize_evidence(
        label="MIDAS/KDS validation report",
        source=args.midas_kds_source_evidence,
        destination=args.midas_kds_validation_report,
        force=args.force_hydrate,
    )
    steps.append(midas_step)

    commercial_step = _materialize_evidence(
        label="commercial readiness report",
        source=args.commercial_readiness_source_evidence,
        destination=args.commercial_readiness,
        force=args.force_hydrate,
    )
    steps.append(commercial_step)

    external_submission_step = _materialize_external_submission_readiness(
        source_artifact_root=index_paths.get("artifact_root"),
        destination=args.external_benchmark_submission_readiness,
        force=args.force_hydrate,
    )
    steps.append(external_submission_step)

    external_submission_updates_step = _materialize_package_json(
        label="external benchmark submission updates",
        source_artifact_root=index_paths.get("artifact_root"),
        destination=args.external_benchmark_submission_updates,
        direct_asset_name="external_benchmark_submission_updates.json",
        package_member="artifacts/external_benchmark_submission_updates.json",
        force=args.force_hydrate,
        ok_when_present=True,
        expected_update_ids=EXPECTED_EXTERNAL_BENCHMARK_UPDATE_IDS,
    )
    steps.append(external_submission_updates_step)

    residual_holdout_updates_step = _materialize_package_json(
        label="residual holdout closure updates",
        source_artifact_root=index_paths.get("artifact_root"),
        destination=args.residual_holdout_closure_updates,
        direct_asset_name="residual_holdout_closure_updates.json",
        package_member="artifacts/residual_holdout_closure_updates.json",
        force=args.force_hydrate,
        ok_when_present=True,
        expected_update_ids=EXPECTED_RESIDUAL_HOLDOUT_UPDATE_IDS,
    )
    steps.append(residual_holdout_updates_step)

    p1_evidence_sidecar_build_step: dict[str, Any] | None = None
    p1_evidence_sidecar_build_payload: dict[str, Any] = {}
    if args.p1_evidence_intake:
        sidecar_build_cmd = [
            sys.executable,
            "scripts/build_p1_evidence_sidecar_updates.py",
            "--intake-manifest",
            str(args.p1_evidence_intake),
            "--base-external-updates",
            str(args.external_benchmark_submission_updates),
            "--base-residual-updates",
            str(args.residual_holdout_closure_updates),
            "--external-out",
            str(args.external_benchmark_submission_updates),
            "--residual-out",
            str(args.residual_holdout_closure_updates),
            "--repo-root",
            str(Path.cwd()),
            "--require-complete",
            "--fail-open",
            "--json",
        ]
        if args.p1_evidence_sidecar_build_summary_out:
            sidecar_build_cmd.extend(["--summary-out", str(args.p1_evidence_sidecar_build_summary_out)])
        p1_evidence_sidecar_build_step = _run_json_command(sidecar_build_cmd)
        p1_evidence_sidecar_build_step.update(
            {
                "label": "P1 evidence sidecar build",
                "path": str(args.p1_evidence_intake),
                "summary_path": (
                    str(args.p1_evidence_sidecar_build_summary_out)
                    if args.p1_evidence_sidecar_build_summary_out
                    else ""
                ),
            }
        )
        p1_evidence_sidecar_build_payload = (
            p1_evidence_sidecar_build_step.get("json")
            if isinstance(p1_evidence_sidecar_build_step.get("json"), dict)
            else {}
        )
        steps.append(p1_evidence_sidecar_build_step)

    evidence_sidecar_preflight_step = _run_json_command(
        [
            sys.executable,
            "scripts/preflight_p1_evidence_sidecar_intake.py",
            "--external-benchmark-submission-updates",
            str(args.external_benchmark_submission_updates),
            "--residual-holdout-closure-updates",
            str(args.residual_holdout_closure_updates),
            "--repo-root",
            str(Path.cwd()),
            "--json",
        ]
    )
    evidence_sidecar_preflight_step.update({"label": "P1 evidence sidecar intake preflight"})
    steps.append(evidence_sidecar_preflight_step)

    coverage_cmd = [
        sys.executable,
        "implementation/phase1/generate_real_project_parser_coverage_matrix.py",
        "--manifest",
        str(args.manifest),
        "--out",
        str(args.coverage_matrix),
    ]
    coverage_step = _run_command(coverage_cmd)
    coverage_step.update({"label": "real-project parser coverage matrix", "path": str(args.coverage_matrix)})
    steps.append(coverage_step)

    peer_cmd = [
        sys.executable,
        "implementation/phase1/build_peer_tbi_benchmark_metric_records.py",
        "--manifest",
        str(args.manifest),
        "--coverage-matrix",
        str(args.coverage_matrix),
        "--out",
        str(args.peer_metric_records),
    ]
    peer_step = _run_command(peer_cmd)
    peer_step.update({"label": "PEER TBI benchmark metric records", "path": str(args.peer_metric_records)})
    steps.append(peer_step)

    row_cmd = [
        sys.executable,
        "implementation/phase1/build_real_project_row_provenance_report.py",
        "--manifest",
        str(args.manifest),
        "--coverage-matrix",
        str(args.coverage_matrix),
        "--peer-metric-records",
        str(args.peer_metric_records),
        "--midas-kds-validation-report",
        str(args.midas_kds_validation_report),
        "--out",
        str(args.row_provenance),
    ]
    row_step = _run_command(row_cmd)
    row_step.update({"label": "real-project row provenance", "path": str(args.row_provenance)})
    steps.append(row_step)

    p1_cmd = [
        sys.executable,
        "scripts/check_p1_readiness_status.py",
        "--coverage-matrix",
        str(args.coverage_matrix),
        "--peer-metric-records",
        str(args.peer_metric_records),
        "--row-provenance",
        str(args.row_provenance),
        "--json",
    ]
    if p0_status_path is not None:
        p1_cmd.extend(["--p0-status", str(p0_status_path)])
    p1_step = _run_json_command(p1_cmd)
    p1_step.update({"label": "P1 readiness status"})
    steps.append(p1_step)

    p1_readiness_path = args.p1_readiness_out
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    if p1_readiness_path is None:
        temp_dir = tempfile.TemporaryDirectory(prefix="clean-checkout-evidence-chain-")
        p1_readiness_path = Path(temp_dir.name) / "p1-readiness-status.json"

    benchmark_cmd = [
        sys.executable,
        "scripts/check_p1_benchmark_breadth_status.py",
        "--commercial-readiness",
        str(args.commercial_readiness),
        "--external-benchmark-submission-readiness",
        str(args.external_benchmark_submission_readiness),
        "--external-benchmark-submission-updates",
        str(args.external_benchmark_submission_updates),
        "--residual-holdout-closure-updates",
        str(args.residual_holdout_closure_updates),
        "--json",
    ]
    p1_status = p1_step.get("json") if isinstance(p1_step.get("json"), dict) else {}
    _write_json(p1_readiness_path, p1_status)
    benchmark_cmd.extend(["--p1-readiness-status", str(p1_readiness_path)])
    benchmark_step = _run_json_command(benchmark_cmd)
    benchmark_step.update({"label": "P1 benchmark breadth status"})
    steps.append(benchmark_step)

    if temp_dir is not None:
        temp_dir.cleanup()

    if args.p1_benchmark_out and isinstance(benchmark_step.get("json"), dict):
        _write_json(args.p1_benchmark_out, benchmark_step["json"])

    operational_step: dict[str, Any] | None = None
    operational_payload: dict[str, Any] = {}
    operational_temp_dir: tempfile.TemporaryDirectory[str] | None = None
    if args.p1_operational_queues_out:
        p1_benchmark_path = args.p1_benchmark_out
        if p1_benchmark_path is None:
            operational_temp_dir = tempfile.TemporaryDirectory(prefix="p1-operational-queues-")
            p1_benchmark_path = Path(operational_temp_dir.name) / "p1-benchmark-breadth-status.json"
            if isinstance(benchmark_step.get("json"), dict):
                _write_json(p1_benchmark_path, benchmark_step["json"])
        operational_cmd = [
            sys.executable,
            "scripts/materialize_p1_operational_queues.py",
            "--commercial-readiness",
            str(args.commercial_readiness),
            "--external-benchmark-submission-readiness",
            str(args.external_benchmark_submission_readiness),
            "--external-benchmark-submission-updates",
            str(args.external_benchmark_submission_updates),
            "--residual-holdout-closure-updates",
            str(args.residual_holdout_closure_updates),
            "--p1-benchmark-breadth-status",
            str(p1_benchmark_path),
            "--out",
            str(args.p1_operational_queues_out),
            "--json",
        ]
        if args.p1_operational_queues_out_md:
            operational_cmd.extend(["--out-md", str(args.p1_operational_queues_out_md)])
        operational_step = _run_json_command(operational_cmd)
        operational_step.update({"label": "P1 operational queues", "path": str(args.p1_operational_queues_out)})
        operational_payload = operational_step.get("json") if isinstance(operational_step.get("json"), dict) else {}
        steps.append(operational_step)
    if operational_temp_dir is not None:
        operational_temp_dir.cleanup()

    p1_evidence_intake_template_step: dict[str, Any] | None = None
    p1_evidence_intake_template_payload: dict[str, Any] = {}
    if args.p1_evidence_intake_template_out:
        if not args.p1_operational_queues_out:
            p1_evidence_intake_template_step = {
                "label": "P1 evidence intake template",
                "path": str(args.p1_evidence_intake_template_out),
                "ok": False,
                "returncode": 2,
                "reason": "p1_operational_queues_out_required",
            }
        elif operational_step is not None and not operational_step.get("ok"):
            p1_evidence_intake_template_step = {
                "label": "P1 evidence intake template",
                "path": str(args.p1_evidence_intake_template_out),
                "ok": False,
                "returncode": 2,
                "reason": "p1_operational_queues_failed",
            }
        elif not args.p1_operational_queues_out.exists():
            p1_evidence_intake_template_step = {
                "label": "P1 evidence intake template",
                "path": str(args.p1_evidence_intake_template_out),
                "ok": False,
                "returncode": 2,
                "reason": "p1_operational_queues_missing",
            }
        else:
            template_cmd = [
                sys.executable,
                "scripts/generate_p1_evidence_intake_template.py",
                "--p1-operational-queues",
                str(args.p1_operational_queues_out),
                "--out",
                str(args.p1_evidence_intake_template_out),
                "--json",
            ]
            if args.p1_evidence_intake_template_out_md:
                template_cmd.extend(["--out-md", str(args.p1_evidence_intake_template_out_md)])
            p1_evidence_intake_template_step = _run_json_command(template_cmd)
            p1_evidence_intake_template_step.update(
                {
                    "label": "P1 evidence intake template",
                    "path": str(args.p1_evidence_intake_template_out),
                    "markdown_path": (
                        str(args.p1_evidence_intake_template_out_md)
                        if args.p1_evidence_intake_template_out_md
                        else ""
                    ),
                }
            )
            p1_evidence_intake_template_payload = (
                p1_evidence_intake_template_step.get("json")
                if isinstance(p1_evidence_intake_template_step.get("json"), dict)
                else {}
            )
        steps.append(p1_evidence_intake_template_step)

    midas_payload = _json_summary(args.midas_kds_validation_report)
    commercial_payload = _json_summary(args.commercial_readiness)
    row_payload = _json_summary(args.row_provenance)
    p1_readiness = p1_step.get("json") if isinstance(p1_step.get("json"), dict) else {}
    p1_benchmark = benchmark_step.get("json") if isinstance(benchmark_step.get("json"), dict) else {}
    p1_evidence_sidecar_preflight = (
        evidence_sidecar_preflight_step.get("json")
        if isinstance(evidence_sidecar_preflight_step.get("json"), dict)
        else {}
    )
    p1_evidence_sidecar_preflight_summary = (
        p1_evidence_sidecar_preflight.get("summary")
        if isinstance(p1_evidence_sidecar_preflight.get("summary"), dict)
        else {}
    )
    external_submission_updates_final = _p1_sidecar_final_summary(
        label="external benchmark submission updates final",
        path=args.external_benchmark_submission_updates,
        expected_update_ids=EXPECTED_EXTERNAL_BENCHMARK_UPDATE_IDS,
        preflight_summary=p1_evidence_sidecar_preflight_summary,
        preflight_keys=(
            "external_expected_queue_count",
            "external_update_row_count",
            "external_expected_rows_present",
            "external_receipt_attached_count",
            "external_closure_evidence_attached_count",
            "external_receipt_pending_count",
        ),
        updated_by_intake=bool(p1_evidence_sidecar_build_step and p1_evidence_sidecar_build_step.get("ok")),
    )
    residual_holdout_updates_final = _p1_sidecar_final_summary(
        label="residual holdout closure updates final",
        path=args.residual_holdout_closure_updates,
        expected_update_ids=EXPECTED_RESIDUAL_HOLDOUT_UPDATE_IDS,
        preflight_summary=p1_evidence_sidecar_preflight_summary,
        preflight_keys=(
            "residual_expected_work_item_count",
            "residual_update_row_count",
            "residual_expected_rows_present",
            "residual_closed_count",
            "residual_closure_evidence_attached_count",
            "residual_closure_pending_count",
        ),
        updated_by_intake=bool(p1_evidence_sidecar_build_step and p1_evidence_sidecar_build_step.get("ok")),
    )
    inputs_contract_pass = bool(
        (publication_step is None or publication_step.get("ok"))
        and midas_payload.get("ok")
        and commercial_payload.get("ok")
        and row_payload.get("ok")
        and p1_readiness.get("p1_inputs_ready", False)
        and p1_benchmark.get("benchmark_breadth_inputs_ready", False)
    )
    p0_closure_evidence_consumed = bool(
        p0_status_path is not None
        and not bool(p1_readiness.get("p0_release_blocker", True))
        and bool(p1_readiness.get("p1_execution_unblocked", False))
    )
    p1_benchmark_execution_unblocked = bool(p1_benchmark.get("p1_benchmark_execution_unblocked", False))
    operational_queues_pass = bool(
        operational_step is None or (operational_step.get("ok") and operational_payload.get("contract_pass", False))
    )
    p1_evidence_intake_template_pass = bool(
        p1_evidence_intake_template_step is None
        or (
            p1_evidence_intake_template_step.get("ok")
            and p1_evidence_intake_template_payload.get("template_kind") == "p1_evidence_intake_fill_in"
        )
    )
    p1_evidence_sidecar_build_pass = bool(
        p1_evidence_sidecar_build_step is None
        or (
            p1_evidence_sidecar_build_step.get("ok")
            and p1_evidence_sidecar_build_payload.get("contract_pass", False)
        )
    )
    publication_sidecars_pass = bool(
        external_submission_updates_step.get("ok") and residual_holdout_updates_step.get("ok")
    )
    contract_pass = bool(
        inputs_contract_pass
        and p0_closure_evidence_consumed
        and p1_benchmark_execution_unblocked
        and operational_queues_pass
        and p1_evidence_intake_template_pass
        and p1_evidence_sidecar_build_pass
        and publication_sidecars_pass
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_CLEAN_CHECKOUT_EVIDENCE_CHAIN_INCOMPLETE",
        "inputs_contract_pass": inputs_contract_pass,
        "p0_closure_evidence_consumed": p0_closure_evidence_consumed,
        "publication_sidecars_pass": publication_sidecars_pass,
        "p1_evidence_intake_ready": bool(p1_evidence_sidecar_preflight.get("contract_pass", False)),
        "artifacts": {
            "manifest": str(args.manifest),
            "publication_evidence_index": (
                str(args.publication_evidence_index) if args.publication_evidence_index else ""
            ),
            "p0_status": str(p0_status_path) if p0_status_path else "",
            "coverage_matrix": str(args.coverage_matrix),
            "peer_metric_records": str(args.peer_metric_records),
            "midas_kds_validation_report": str(args.midas_kds_validation_report),
            "commercial_readiness": str(args.commercial_readiness),
            "external_benchmark_submission_readiness": str(args.external_benchmark_submission_readiness),
            "external_benchmark_submission_updates": str(args.external_benchmark_submission_updates),
            "residual_holdout_closure_updates": str(args.residual_holdout_closure_updates),
            "row_provenance": str(args.row_provenance),
            "p1_operational_queues": str(args.p1_operational_queues_out) if args.p1_operational_queues_out else "",
            "p1_evidence_intake": str(args.p1_evidence_intake) if args.p1_evidence_intake else "",
            "p1_evidence_sidecar_build_summary": (
                str(args.p1_evidence_sidecar_build_summary_out)
                if args.p1_evidence_sidecar_build_summary_out
                else ""
            ),
            "p1_evidence_intake_template": (
                str(args.p1_evidence_intake_template_out) if args.p1_evidence_intake_template_out else ""
            ),
            "p1_evidence_intake_template_md": (
                str(args.p1_evidence_intake_template_out_md) if args.p1_evidence_intake_template_out_md else ""
            ),
        },
        "release_publication_evidence_status": (
            publication_step.get("json", {}) if isinstance(publication_step, dict) else {}
        ),
        "midas_kds_validation": midas_payload,
        "commercial_readiness": {
            **commercial_payload,
            "commercial_scope": _commercial_scope(args.commercial_readiness),
        },
        "row_provenance": row_payload,
        "external_benchmark_submission_updates": external_submission_updates_step,
        "residual_holdout_closure_updates": residual_holdout_updates_step,
        "external_benchmark_submission_updates_final": external_submission_updates_final,
        "residual_holdout_closure_updates_final": residual_holdout_updates_final,
        "p1_evidence_sidecar_build": p1_evidence_sidecar_build_payload,
        "p1_evidence_sidecar_build_pass": p1_evidence_sidecar_build_pass,
        "p1_evidence_sidecar_preflight": p1_evidence_sidecar_preflight,
        "p1_readiness_status": p1_readiness,
        "p1_benchmark_breadth_status": p1_benchmark,
        "p1_operational_queues": operational_payload,
        "p1_operational_queues_pass": operational_queues_pass,
        "p1_evidence_intake_template": p1_evidence_intake_template_payload,
        "p1_evidence_intake_template_pass": p1_evidence_intake_template_pass,
        "p0_release_blocker": bool(p1_readiness.get("p0_release_blocker", False)),
        "p1_execution_unblocked": bool(p1_readiness.get("p1_execution_unblocked", False)),
        "p1_benchmark_execution_unblocked": p1_benchmark_execution_unblocked,
        "steps": steps,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("implementation/phase1/real_project_corpus_seed_manifest.json"))
    parser.add_argument("--coverage-matrix", type=Path, default=Path("implementation/phase1/real_project_parser_coverage_matrix.json"))
    parser.add_argument("--peer-metric-records", type=Path, default=Path("implementation/phase1/peer_tbi_benchmark_metric_records.json"))
    parser.add_argument("--row-provenance", type=Path, default=Path("implementation/phase1/real_project_row_provenance_report.json"))
    parser.add_argument(
        "--midas-kds-validation-report",
        type=Path,
        default=Path("implementation/phase1/midas_kds_geometry_bridge_validation_report.json"),
    )
    parser.add_argument(
        "--midas-kds-source-evidence",
        type=Path,
        default=Path("implementation/phase1/release_evidence/midas/midas_kds_geometry_bridge_validation_report.json"),
    )
    parser.add_argument("--commercial-readiness", type=Path, default=Path("implementation/phase1/commercial_readiness_report.json"))
    parser.add_argument(
        "--external-benchmark-submission-readiness",
        type=Path,
        default=DEFAULT_EXTERNAL_BENCHMARK_SUBMISSION_READINESS,
    )
    parser.add_argument(
        "--external-benchmark-submission-updates",
        type=Path,
        default=DEFAULT_EXTERNAL_BENCHMARK_SUBMISSION_UPDATES,
    )
    parser.add_argument(
        "--residual-holdout-closure-updates",
        type=Path,
        default=DEFAULT_RESIDUAL_HOLDOUT_CLOSURE_UPDATES,
    )
    parser.add_argument(
        "--commercial-readiness-source-evidence",
        type=Path,
        default=Path("implementation/phase1/release_evidence/commercial/commercial_readiness_report.json"),
    )
    parser.add_argument(
        "--p0-status",
        type=Path,
        default=None,
        help="Published P0 closure status JSON. When provided, P1 readiness is evaluated against the closed release gate.",
    )
    parser.add_argument(
        "--publication-evidence-index",
        type=Path,
        default=None,
        help="Release publication evidence index. Supplies --p0-status for P1 handoff when --p0-status is omitted.",
    )
    parser.add_argument("--p1-readiness-out", type=Path, default=None)
    parser.add_argument("--p1-benchmark-out", type=Path, default=None)
    parser.add_argument("--p1-operational-queues-out", type=Path, default=None)
    parser.add_argument("--p1-operational-queues-out-md", type=Path, default=None)
    parser.add_argument("--p1-evidence-intake", type=Path, default=None)
    parser.add_argument("--p1-evidence-sidecar-build-summary-out", type=Path, default=None)
    parser.add_argument("--p1-evidence-intake-template-out", type=Path, default=None)
    parser.add_argument("--p1-evidence-intake-template-out-md", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--force-hydrate", action="store_true")
    args = parser.parse_args()

    payload = build_chain(args)
    if args.out:
        _write_json(args.out, payload)
    if args.json or not args.out:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
