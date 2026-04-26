#!/usr/bin/env python3
"""Run nightly phase3 hardening gates and freeze/promote release artifacts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
from typing import Iterable

from design_optimization.io import entrypoint_group_rows, entrypoint_status_rows, load_json
from experiment_artifact_archive import archive_test_outputs
from run_panel_zone_solver_verified_handoff import (
    DEFAULT_PANEL_ZONE_INBOX,
    _discover_from_drop_dir,
    _drop_dir_source_origin_class,
)

DRY_RUN = False
RUN_ENV_OVERRIDES: dict[str, str] = {}
REUSE_EXISTING_IF_PRESENT = True
MIDAS_SECTION_LIBRARY_ARTIFACTS = (
    "implementation/phase1/open_data/midas/midas_generator_33.json",
    "implementation/phase1/open_data/midas/midas_generator_33.pr_recheck.json",
    "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json",
)

REASONS = {
    "PASS": "nightly gate and release freeze passed",
    "ERR_HIP_KERNEL_SMOKE": "hip kernel smoke gate failed",
    "ERR_COMMERCIAL_CSV_GATE": "commercial csv gate failed",
    "ERR_REAL_SOURCE_MULTI_GATE": "multi real-source gate failed",
    "ERR_NONLINEAR_ENGINE_GATE": "rust nonlinear engine gate failed",
    "ERR_PUSHOVER_STRESS_GATE": "nonlinear pushover stress gate failed",
    "ERR_NDTHA_STRESS_GATE": "nonlinear ndtha stress gate failed",
    "ERR_NDTHA_RESIDUAL_GATE": "ndtha residual gate failed",
    "ERR_GLOBAL_AUTHORITY_GATE": "global authority gate failed",
    "ERR_WIND_BENCHMARK_GATE": "wind benchmark gate failed",
    "ERR_SSI_BOUNDARY_GATE": "ssi boundary gate failed",
    "ERR_DAMPER_VALIDATION_GATE": "damper validation gate failed",
    "ERR_KDS_COMPLIANCE_GATE": "kds/frontend compliance gate failed",
    "ERR_CONSTRUCTION_SEQUENCE_GATE": "construction sequence gate failed",
    "ERR_FLEXIBLE_DIAPHRAGM_GATE": "flexible diaphragm gate failed",
    "ERR_REPRO_VERSION_LOCK_GATE": "reproducibility/version-lock gate failed",
    "ERR_RELEASE_REGISTRY_GATE": "signed release registry gate failed",
    "ERR_PERFORMANCE_PROFILING_GATE": "performance profiling gate failed",
    "ERR_RC_BENCHMARK_LOCK_GATE": "rc benchmark-lock gate failed",
    "ERR_HARDEST_EXTERNAL_10CASE_KICKOFF_GATE": "hardest external 10-case kickoff gate failed",
    "ERR_MIDAS_MGT_CONVERSION": "midas mgt conversion gate failed",
    "ERR_SOLVER_BREADTH_GATE": "solver breadth gate failed",
    "ERR_CONTACT_READINESS": "contact-readiness gate failed",
    "ERR_SURFACE_INTERACTION_BENCHMARK": "surface interaction benchmark gate failed",
    "ERR_MIDAS_INTEROPERABILITY": "midas interoperability/export gate failed",
    "ERR_KOREAN_SOURCE_INGEST": "korean public-source ingest gate failed",
    "ERR_MIDAS_NATIVE_ROUNDTRIP": "native MIDAS roundtrip/write-back gate failed",
    "ERR_IRREGULAR_STRUCTURE_COLLECTION_GATE": "irregular structure collection gate failed",
    "ERR_IRREGULAR_TOP5_EXECUTION_MANIFEST": "irregular top5 execution manifest generation failed",
    "ERR_NONLINEAR_GENERALIZATION_GATE": "nonlinear generalization gate failed",
    "ERR_WORKFLOW_PRODUCTIZATION_GATE": "workflow/interoperability productization gate failed",
    "ERR_COMMERCIAL_READINESS": "commercial readiness gate failed",
    "ERR_PHASE3_PIPELINE": "phase3 nightly pipeline failed",
    "ERR_SCALEOUT_IO": "scaleout io profile failed",
    "ERR_NIGHTLY_10M_REPRO": "nightly 10m reproducibility gate failed",
    "ERR_NDTHA_LONG_PROFILE": "10m ndtha long profile gate failed",
    "ERR_CI_GATE": "phase1 ci gate failed",
    "ERR_DESIGN_OPT_COST_REDUCTION_SMOKE": "design optimization cost-reduction smoke probe failed",
    "ERR_DESIGN_OPT_DATASET_REFRESH": "design optimization dataset refresh failed",
    "ERR_DESIGN_OPT_REBAR_PAYLOAD_PROJECTION": "design optimization rebar payload projection failed",
    "ERR_DESIGN_OPT_CONNECTION_DETAILING_PAYLOAD_PROJECTION": "design optimization connection-detailing payload projection failed",
    "ERR_DESIGN_OPT_DETAILING_PAYLOAD_PROJECTION": "design optimization detailing payload projection failed",
    "ERR_MGT_EXPORT_DIRECT_PATCH": "mgt direct patch export failed",
    "ERR_PBD_HINGE_REFRESH_SOURCE": "pbd hinge refresh source generation failed",
    "ERR_PBD_HINGE_REFRESH_ARTIFACT": "pbd hinge refresh artifact generation failed",
    "ERR_PBD_HINGE_REFRESH_REPORT": "pbd hinge refresh report generation failed",
    "ERR_PANEL_ZONE_SOLVER_VERIFIED_EXPORT_BUNDLE": "panel-zone solver-verified export bundle generation failed",
    "ERR_PANEL_ZONE_SOLVER_EXPORT_BUNDLE": "panel-zone solver export bundle generation failed",
    "ERR_PANEL_ZONE_JOINT_GEOMETRY_SOURCE": "panel-zone joint geometry 3D source stub failed",
    "ERR_PANEL_ZONE_REBAR_ANCHORAGE_SOURCE": "panel-zone rebar anchorage 3D source stub failed",
    "ERR_PANEL_ZONE_CLASH_VERIFICATION_SOURCE": "panel-zone clash verification 3D source stub failed",
    "ERR_PANEL_ZONE_JOINT_GEOMETRY_CONTRACT": "panel-zone joint geometry 3D source contract failed",
    "ERR_PANEL_ZONE_REBAR_ANCHORAGE_CONTRACT": "panel-zone rebar anchorage 3D source contract failed",
    "ERR_PANEL_ZONE_CLASH_VERIFICATION_CONTRACT": "panel-zone clash verification 3D source contract failed",
    "ERR_PANEL_ZONE_CLASH_ARTIFACT": "panel-zone clash artifact generation failed",
    "ERR_PANEL_ZONE_SOLVER_VERIFIED_INBOX_STATUS": "panel-zone solver-verified inbox status generation failed",
    "ERR_FOUNDATION_OPTIMIZATION_ARTIFACT": "foundation optimization artifact generation failed",
    "ERR_WIND_RAW_MAPPING_ARTIFACT": "wind raw mapping artifact generation failed",
    "ERR_RELEASE_GAP_REPORT": "release gap report generation failed",
    "ERR_EXTERNAL_BENCHMARK_SUBMISSION_READINESS": "external benchmark submission readiness report generation failed",
    "ERR_EXTERNAL_BENCHMARK_KICKOFF_PACKAGE": "external benchmark kickoff package generation failed",
    "ERR_EXTERNAL_BENCHMARK_EXECUTION_MANIFEST": "external benchmark execution manifest generation failed",
    "ERR_EXTERNAL_BENCHMARK_EXECUTION_STATUS_MANIFEST": "external benchmark execution status manifest generation failed",
    "ERR_AUDIT_REVIEW_DECISION_BATCH_TEMPLATE": "audit review decision batch template generation failed",
    "ERR_AUDIT_REVIEW_DECISION_BATCH_EXAMPLES": "audit review decision batch example generation failed",
    "ERR_AUDIT_REVIEW_DECISION_BATCH_PREVIEWS": "audit review decision batch preview artifact generation failed",
    "ERR_STRUCTURAL_OPTIMIZATION_VIEWER": "structural optimization viewer generation failed",
    "ERR_OPTIMIZED_DRAWING_REVIEW": "optimized drawing review generation failed",
    "ERR_STATIC_VALIDATION": "static artifact validation failed",
    "ERR_FREEZE_SNAPSHOT": "release snapshot freeze failed",
    "ERR_PROMOTION": "release candidate promotion failed",
    "ERR_PROMOTION_HOLD_FOR_REVIEW": "release candidate promotion is held for explicit authority routing review",
}


def _run(step: str, cmd: list[str], steps: list[dict]) -> bool:
    if DRY_RUN:
        steps.append(
            {
                "step": step,
                "seconds": 0.0,
                "return_code": 0,
                "command": shlex.join(cmd),
                "stdout_tail": "",
                "stderr_tail": "",
                "dry_run": True,
            }
        )
        return True
    t0 = time.time()
    env = dict(os.environ)
    env.update(RUN_ENV_OVERRIDES)
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True, env=env)
    dt = time.time() - t0
    steps.append(
        {
            "step": step,
            "seconds": float(dt),
            "return_code": int(proc.returncode),
            "command": shlex.join(cmd),
            "stdout_tail": (proc.stdout or "")[-2000:],
            "stderr_tail": (proc.stderr or "")[-2000:],
        }
    )
    return proc.returncode == 0


def _load_json(path: str | Path) -> dict:
    target = Path(path)
    if not target.exists():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_iso_timestamp(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _report_is_recent_success(path: str | Path, *, max_age_sec: float) -> tuple[bool, float, dict]:
    target = Path(path)
    payload = _load_json(target)
    if not target.exists() or not payload:
        return False, float("inf"), payload
    contract_pass = payload.get("contract_pass")
    reason_code = str(payload.get("reason_code", "") or "").strip()
    success = bool(contract_pass is True or reason_code == "PASS")
    if not success:
        return False, float("inf"), payload
    timestamp = _parse_iso_timestamp(payload.get("generated_at"))
    if timestamp is None:
        timestamp = datetime.fromtimestamp(target.stat().st_mtime, tz=timezone.utc)
    age_sec = max((datetime.now(timezone.utc) - timestamp).total_seconds(), 0.0)
    return age_sec <= float(max_age_sec), float(age_sec), payload


def _run_or_reuse_reports(
    step: str,
    cmd: list[str],
    steps: list[dict],
    *,
    report_paths: Iterable[str | Path],
    allow_reuse: bool,
    max_age_sec: float,
) -> bool:
    paths = [Path(p) for p in report_paths if str(p).strip()]
    if not DRY_RUN and allow_reuse and paths:
        statuses = [_report_is_recent_success(path, max_age_sec=max_age_sec) for path in paths]
        if all(ok for ok, _age, _payload in statuses):
            steps.append(
                {
                    "step": step,
                    "seconds": 0.0,
                    "return_code": 0,
                    "command": "reuse:" + ",".join(str(path) for path in paths),
                    "stdout_tail": "",
                    "stderr_tail": "",
                    "reused_reports": [str(path) for path in paths],
                    "max_report_age_sec": float(max(age for _ok, age, _payload in statuses)),
                }
            )
            return True
    return _run(step, cmd, steps)


def _normalize_reuse_value(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _normalize_reuse_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_reuse_value(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_reuse_value(item) for item in value]
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, (int, float)):
        return f"{float(value):.12g}"
    if value is None:
        return ""
    text = str(value)
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", text.strip()):
        try:
            return f"{float(text):.12g}"
        except Exception:
            return text
    return text


def _reuse_signature_payload(payload: object) -> str:
    return json.dumps(_normalize_reuse_value(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _command_expected_inputs(cmd: list[str]) -> dict[str, object]:
    expected: dict[str, object] = {}
    i = 2
    while i < len(cmd):
        token = str(cmd[i])
        if not token.startswith("--"):
            i += 1
            continue
        if token.startswith("--no-"):
            expected[token[5:].replace("-", "_")] = False
            i += 1
            continue
        key = token[2:].replace("-", "_")
        if i + 1 < len(cmd) and not str(cmd[i + 1]).startswith("--"):
            expected[key] = cmd[i + 1]
            i += 2
            continue
        expected[key] = True
        i += 1
    return expected


def _iter_reuse_path_candidates(value: object) -> list[str]:
    candidates: list[str] = []
    if isinstance(value, Path):
        return [str(value)]
    if isinstance(value, dict):
        for item in value.values():
            candidates.extend(_iter_reuse_path_candidates(item))
        return candidates
    if isinstance(value, (list, tuple)):
        for item in value:
            candidates.extend(_iter_reuse_path_candidates(item))
        return candidates
    text = str(value or "").strip()
    if not text:
        return []
    for token in text.split(","):
        cleaned = token.strip().strip('"\'')
        if cleaned and ("/" in cleaned or "\\" in cleaned):
            candidates.append(cleaned)
    return candidates


def _report_matches_command_inputs(
    report_path: Path,
    cmd: list[str],
    *,
    check_dependency_mtime: bool = True,
) -> bool:
    if not report_path.exists():
        return False
    try:
        existing = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if not isinstance(existing, dict):
        return False
    if not bool(existing.get("contract_pass", False)):
        return False
    existing_inputs = existing.get("inputs")
    if not isinstance(existing_inputs, dict):
        return False
    expected_inputs = _command_expected_inputs(cmd)
    if not expected_inputs:
        return False
    for key, expected_value in expected_inputs.items():
        if key not in existing_inputs:
            return False
        if _reuse_signature_payload(existing_inputs.get(key)) != _reuse_signature_payload(expected_value):
            return False
    try:
        report_mtime = report_path.stat().st_mtime
    except Exception:
        return False
    script_path = Path(str(cmd[1])) if len(cmd) > 1 else None
    if script_path is not None and script_path.exists():
        try:
            if script_path.stat().st_mtime > report_mtime:
                return False
        except Exception:
            return False
    if check_dependency_mtime:
        for value in expected_inputs.values():
            for candidate in _iter_reuse_path_candidates(value):
                candidate_path = Path(candidate)
                if not candidate_path.exists():
                    continue
                try:
                    if candidate_path.stat().st_mtime > report_mtime:
                        return False
                except Exception:
                    return False
    return True


def _run_reusable(
    step: str,
    cmd: list[str],
    report_path: str | Path,
    steps: list[dict],
    *,
    check_dependency_mtime: bool = True,
    reuse_note: str = "",
) -> bool:
    if DRY_RUN or not REUSE_EXISTING_IF_PRESENT:
        return _run(step, cmd, steps)
    report_path = Path(report_path)
    if _report_matches_command_inputs(report_path, cmd, check_dependency_mtime=check_dependency_mtime):
        steps.append(
            {
                "step": step,
                "seconds": 0.0,
                "return_code": 0,
                "command": shlex.join(cmd),
                "stdout_tail": reuse_note,
                "stderr_tail": "",
                "reused_existing": True,
                "report_path": str(report_path),
                "reuse_dependency_mtime_checked": bool(check_dependency_mtime),
            }
        )
        return True
    ok = _run(step, cmd, steps)
    if steps:
        steps[-1]["reused_existing"] = False
        steps[-1]["report_path"] = str(report_path)
        steps[-1]["reuse_dependency_mtime_checked"] = bool(check_dependency_mtime)
    if not ok and _report_matches_command_inputs(
        report_path,
        cmd,
        check_dependency_mtime=check_dependency_mtime,
    ):
        if steps:
            steps[-1]["report_recovered_success"] = True
            steps[-1]["stdout_tail"] = (
                str(steps[-1].get("stdout_tail", "") or "")
                + ("\n" if steps[-1].get("stdout_tail") else "")
                + "Recovered success from a valid PASS report after non-zero process exit."
            )[-2000:]
        return True
    return ok


def _write_json_report(path: str | Path, payload: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _append_generated_report_step(
    step: str,
    cmd: list[str],
    out_path: str | Path,
    payload: dict,
    steps: list[dict],
) -> bool:
    if DRY_RUN:
        steps.append(
            {
                "step": step,
                "seconds": 0.0,
                "return_code": 0,
                "command": shlex.join(cmd),
                "stdout_tail": "",
                "stderr_tail": "",
                "dry_run": True,
                "generated_artifact": str(out_path),
            }
        )
        return True
    t0 = time.time()
    try:
        _write_json_report(out_path, payload)
    except Exception as exc:
        dt = time.time() - t0
        steps.append(
            {
                "step": step,
                "seconds": float(dt),
                "return_code": 1,
                "command": shlex.join(cmd),
                "stdout_tail": "",
                "stderr_tail": str(exc),
                "generated_artifact": str(out_path),
            }
        )
        return False
    dt = time.time() - t0
    steps.append(
        {
            "step": step,
            "seconds": float(dt),
            "return_code": 0,
            "command": shlex.join(cmd),
            "stdout_tail": "",
            "stderr_tail": "",
            "generated_artifact": str(out_path),
        }
    )
    return True


def _build_irregular_top5_execution_manifest_payload(
    *,
    catalog_path: str | Path,
    triage_report_path: str | Path,
    priority_families_path: str | Path,
    collection_report_path: str | Path,
    out_path: str | Path,
) -> dict:
    catalog = _load_json(catalog_path)
    triage = _load_json(triage_report_path)
    priority = _load_json(priority_families_path)
    collection = _load_json(collection_report_path)

    families = priority.get("families") if isinstance(priority.get("families"), list) else []
    top5_families = [dict(item) for item in families[:5] if isinstance(item, dict)]
    source_records = catalog.get("source_records") if isinstance(catalog.get("source_records"), list) else []
    records_by_family: dict[str, list[dict]] = {}
    for record in source_records:
        if not isinstance(record, dict):
            continue
        family_id = str(record.get("family_id", "") or "").strip()
        if not family_id:
            continue
        records_by_family.setdefault(family_id, []).append(record)

    execution_cases: list[dict] = []
    for family in top5_families:
        family_id = str(family.get("id", "") or "").strip()
        family_records = records_by_family.get(family_id, [])
        execution_cases.append(
            {
                "family_id": family_id,
                "priority": int(family.get("priority", 0) or 0),
                "authority_fit": str(family.get("authority_fit", "") or ""),
                "ai_learning_fit": str(family.get("ai_learning_fit", "") or ""),
                "source_record_count": len(family_records),
                "source_ids": [str(record.get("source_id", "") or "") for record in family_records if str(record.get("source_id", "") or "").strip()],
                "likely_formats": list(family.get("likely_formats", [])) if isinstance(family.get("likely_formats"), list) else [],
                "irregularity_tags": list(family.get("irregularity_tags", [])) if isinstance(family.get("irregularity_tags"), list) else [],
                "recommended_kpi_or_validation_angle": str(family.get("recommended_kpi_or_validation_angle", "") or ""),
                "why_it_matters": str(family.get("why_it_matters", "") or ""),
            }
        )

    triage_summary = triage.get("summary") if isinstance(triage.get("summary"), dict) else {}
    catalog_summary = catalog.get("summary") if isinstance(catalog.get("summary"), dict) else {}
    collection_summary = collection.get("summary") if isinstance(collection.get("summary"), dict) else {}
    native_roundtrip_candidate_count = int(triage_summary.get("native_roundtrip_candidate_count", 0) or 0)
    solver_benchmark_candidate_count = int(triage_summary.get("solver_benchmark_candidate_count", 0) or 0)
    ai_learning_candidate_count = int(triage_summary.get("ai_learning_candidate_count", 0) or 0)
    quick_start_local_source_count = int(triage_summary.get("quick_start_local_source_count", 0) or 0)
    summary_line = (
        "Irregular top5 execution manifest: PASS | "
        f"top5={len(execution_cases)} | "
        f"native_roundtrip_candidates={native_roundtrip_candidate_count} | "
        f"solver_benchmark_candidates={solver_benchmark_candidate_count} | "
        f"ai_learning_candidates={ai_learning_candidate_count}"
    )
    return {
        "schema_version": "1.0",
        "manifest_version": "0.1.0",
        "catalog_path": str(catalog_path),
        "triage_report_path": str(triage_report_path),
        "collection_report_path": str(collection_report_path),
        "priority_families_path": str(priority_families_path),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": bool(catalog) and bool(triage) and bool(priority) and bool(collection) and len(execution_cases) == 5,
        "reason_code": "PASS" if bool(catalog) and bool(triage) and bool(priority) and bool(collection) and len(execution_cases) == 5 else "FAIL",
        "reason": "top5 irregular structure execution manifest prepared",
        "summary_line": summary_line,
        "summary": {
            "catalog_family_count": int(catalog_summary.get("family_count", 0) or 0),
            "catalog_source_record_count": int(catalog_summary.get("source_record_count", 0) or 0),
            "collection_source_count": int(collection_summary.get("source_count", 0) or 0),
            "collection_collected_count": int(collection_summary.get("collected_count", 0) or 0),
            "quick_start_local_source_count": quick_start_local_source_count,
            "native_roundtrip_candidate_count": native_roundtrip_candidate_count,
            "solver_benchmark_candidate_count": solver_benchmark_candidate_count,
            "ai_learning_candidate_count": ai_learning_candidate_count,
            "top5_family_count": len(execution_cases),
            "top5_priority_ids": [str(case.get("family_id", "")) for case in execution_cases],
        },
        "top5_cases": execution_cases,
        "source_record_count": len(source_records),
    }


def _build_irregular_structure_collection_gate_payload(
    *,
    catalog_path: str | Path,
    triage_report_path: str | Path,
    collection_report_path: str | Path,
    top5_manifest_path: str | Path,
) -> dict:
    catalog = _load_json(catalog_path)
    triage = _load_json(triage_report_path)
    collection = _load_json(collection_report_path)
    top5_manifest = _load_json(top5_manifest_path)

    catalog_summary = catalog.get("summary") if isinstance(catalog.get("summary"), dict) else {}
    triage_summary = triage.get("summary") if isinstance(triage.get("summary"), dict) else {}
    collection_summary = collection.get("summary") if isinstance(collection.get("summary"), dict) else {}
    top5_cases = top5_manifest.get("top5_cases") if isinstance(top5_manifest.get("top5_cases"), list) else []
    family_count = int(catalog_summary.get("family_count", 0) or 0)
    source_record_count = int(catalog_summary.get("source_record_count", 0) or 0)
    local_ready_count = int(catalog_summary.get("local_ready_count", 0) or 0)
    remote_candidate_count = int(catalog_summary.get("remote_candidate_count", 0) or 0)
    collected_count = int(collection_summary.get("collected_count", 0) or 0)
    collection_source_count = int(collection_summary.get("source_count", 0) or 0)
    top5_family_count = len(top5_cases)
    summary_line = (
        "Irregular structure collection gate: PASS | "
        f"families={family_count} | "
        f"sources={source_record_count} | "
        f"local_ready={local_ready_count} | "
        f"remote_candidates={remote_candidate_count} | "
        f"collected={collected_count} | "
        f"top5={top5_family_count}"
    )
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": bool(catalog)
        and bool(collection)
        and bool(top5_manifest)
        and bool(top5_manifest.get("contract_pass", False))
        and top5_family_count == 5,
        "reason_code": "PASS"
        if bool(catalog)
        and bool(collection)
        and bool(top5_manifest)
        and bool(top5_manifest.get("contract_pass", False))
        and top5_family_count == 5
        else "FAIL",
        "reason": "irregular structure source catalog processed",
        "catalog_path": str(catalog_path),
        "triage_report_path": str(triage_report_path),
        "collection_report_path": str(collection_report_path),
        "top5_manifest_path": str(top5_manifest_path),
        "summary_line": summary_line,
        "summary": {
            "family_count": family_count,
            "source_record_count": source_record_count,
            "local_ready_count": local_ready_count,
            "remote_candidate_count": remote_candidate_count,
            "collected_count": collected_count,
            "collection_source_count": collection_source_count,
            "native_roundtrip_candidate_count": int(triage_summary.get("native_roundtrip_candidate_count", 0) or 0),
            "solver_benchmark_candidate_count": int(triage_summary.get("solver_benchmark_candidate_count", 0) or 0),
            "ai_learning_candidate_count": int(triage_summary.get("ai_learning_candidate_count", 0) or 0),
            "top5_family_count": top5_family_count,
            "top5_priority_ids": [str(case.get("family_id", "")) for case in top5_cases],
        },
        "checks": {
            "catalog_present_pass": bool(catalog),
            "triage_report_present_pass": bool(triage),
            "collection_report_present_pass": bool(collection),
            "top5_manifest_present_pass": bool(top5_manifest),
        },
    }


def _archive_outputs(test_name: str, paths: list[str]) -> str:
    try:
        return str(
            archive_test_outputs(
                test_name=test_name,
                paths=paths,
                run_root="implementation/phase1/experiments/by_test",
                move=False,
            )
        )
    except Exception:
        return ""


def _smoke_report_payload(path: str | Path) -> dict:
    report = load_json(path)
    if not report:
        return {}
    return {
        "report_exists": True,
        "generated_at": str(report.get("generated_at", "")),
        "contract_pass": bool(report.get("contract_pass", False)),
        "reason_code": str(report.get("reason_code", "")),
        "summary": dict(report.get("summary", {})) if isinstance(report.get("summary"), dict) else {},
    }


def _update_smoke_history(history_path: str | Path, report_path: str | Path, *, limit: int) -> dict:
    report = load_json(report_path)
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    if not report:
        return {}
    target = Path(history_path)
    existing = load_json(target)
    history = list(existing.get("history", [])) if isinstance(existing.get("history"), list) else []
    row = {
        "generated_at": str(report.get("generated_at", datetime.now(timezone.utc).isoformat())),
        "contract_pass": bool(report.get("contract_pass", False)),
        "reason_code": str(report.get("reason_code", "")),
        "objective_profile": str(summary.get("objective_profile", "")),
        "smoke_step_count": int(summary.get("smoke_step_count", 0) or 0),
        "trial_action_available": bool(summary.get("trial_action_available", False)),
        "trial_action_name": str(summary.get("trial_action_name", "")),
        "trial_group_id": str(summary.get("trial_group_id", "")),
        "baseline_runtime_s": float(summary.get("baseline_runtime_s", 0.0) or 0.0),
        "trial_runtime_s": float(summary.get("trial_runtime_s", 0.0) or 0.0),
        "baseline_feasible": bool(summary.get("baseline_feasible", False)),
        "trial_feasible": bool(summary.get("trial_feasible", False)),
        "baseline_max_dcr": float(summary.get("baseline_max_dcr", 0.0) or 0.0),
        "trial_max_dcr": float(summary.get("trial_max_dcr", 0.0) or 0.0),
        "solver_backend_static": str(summary.get("solver_backend_static", "")),
        "solver_backend_ndtha": str(summary.get("solver_backend_ndtha", "")),
    }
    history.append(row)
    history = history[-max(int(limit), 1):]
    count = len(history)
    pass_count = sum(1 for item in history if bool(item.get("contract_pass", False)))
    trial_feasible_count = sum(1 for item in history if bool(item.get("trial_feasible", False)))
    baseline_feasible_count = sum(1 for item in history if bool(item.get("baseline_feasible", False)))
    avg_baseline_runtime_s = sum(float(item.get("baseline_runtime_s", 0.0) or 0.0) for item in history) / count
    avg_trial_runtime_s = sum(float(item.get("trial_runtime_s", 0.0) or 0.0) for item in history) / count
    max_trial_runtime_s = max(float(item.get("trial_runtime_s", 0.0) or 0.0) for item in history)
    summary_payload = {
        "count": count,
        "pass_count": pass_count,
        "pass_rate": float(pass_count / count),
        "baseline_feasible_rate": float(baseline_feasible_count / count),
        "trial_feasible_rate": float(trial_feasible_count / count),
        "avg_baseline_runtime_s": float(avg_baseline_runtime_s),
        "avg_trial_runtime_s": float(avg_trial_runtime_s),
        "max_trial_runtime_s": float(max_trial_runtime_s),
        "last_generated_at": str(history[-1].get("generated_at", "")),
        "last_reason_code": str(history[-1].get("reason_code", "")),
        "strict_ready": bool(count >= 3 and (pass_count / count) >= 0.95 and (trial_feasible_count / count) >= 0.90),
    }
    payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "history_limit": int(limit),
        "history": history,
        "summary": summary_payload,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _smoke_strict_recommendation(smoke_history_payload: dict) -> dict[str, object]:
    summary = smoke_history_payload.get("summary") if isinstance(smoke_history_payload.get("summary"), dict) else {}
    count = int(summary.get("count", 0) or 0)
    strict_ready = bool(summary.get("strict_ready", False))
    pass_rate = float(summary.get("pass_rate", 0.0) or 0.0)
    trial_feasible_rate = float(summary.get("trial_feasible_rate", 0.0) or 0.0)
    if strict_ready:
        return {
            "recommendation": "candidate_for_strict_enable",
            "reason": "history count and pass/feasible rates satisfy strict-ready threshold",
            "strict_ready": True,
            "count": count,
            "pass_rate": pass_rate,
            "trial_feasible_rate": trial_feasible_rate,
        }
    if count < 3:
        return {
            "recommendation": "collect_more_history",
            "reason": "need at least 3 smoke samples before strict enable review",
            "strict_ready": False,
            "count": count,
            "pass_rate": pass_rate,
            "trial_feasible_rate": trial_feasible_rate,
        }
    return {
        "recommendation": "keep_non_blocking",
        "reason": "smoke history exists but pass/feasible rates are below strict threshold",
        "strict_ready": False,
        "count": count,
        "pass_rate": pass_rate,
        "trial_feasible_rate": trial_feasible_rate,
    }


def _prefer_richer_summary_line(primary: object, fallback: object, *, required_fragments: tuple[str, ...] = ()) -> str:
    primary_line = str(primary or "").strip()
    fallback_line = str(fallback or "").strip()
    if not primary_line:
        return fallback_line
    if not fallback_line:
        return primary_line
    for fragment in required_fragments:
        if fragment in fallback_line and fragment not in primary_line:
            return fallback_line
    return primary_line


def _nightly_summary_cards(
    *,
    reason_code: str,
    smoke_payload: dict,
    smoke_history_payload: dict,
    committee_summary: dict,
    ci_summary: dict,
    runtime_summary: dict[str, object],
) -> list[dict[str, object]]:
    smoke_summary = smoke_payload.get("summary") if isinstance(smoke_payload.get("summary"), dict) else {}
    smoke_hist_summary = smoke_history_payload.get("summary") if isinstance(smoke_history_payload.get("summary"), dict) else {}
    recommendation = _smoke_strict_recommendation(smoke_history_payload)
    midas_section_library_summary_line = str(
        committee_summary.get("midas_section_library_summary_line", ci_summary.get("midas_section_library_summary_line", "")) or ""
    ).strip()
    midas_kds_geometry_bridge_summary_line = _prefer_richer_summary_line(
        committee_summary.get("midas_kds_geometry_bridge_summary_line", ""),
        ci_summary.get("midas_kds_geometry_bridge_summary_line", ""),
        required_fragments=("registry=",),
    )
    midas_loadcomb_roundtrip_summary_line = str(
        committee_summary.get("midas_loadcomb_roundtrip_summary_line", ci_summary.get("midas_loadcomb_roundtrip_summary_line", "")) or ""
    ).strip()
    cards = [
        {
            "label": "Nightly",
            "value": reason_code,
            "status": "PASS" if reason_code == "PASS" else "FAIL",
            "note": REASONS.get(reason_code, ""),
        },
        {
            "label": "Design Opt Smoke",
            "value": str(smoke_payload.get("reason_code", "")),
            "status": "PASS" if bool(smoke_payload.get("contract_pass", False)) else "FAIL",
            "note": f"profile={smoke_summary.get('objective_profile', '')}, trial_action={smoke_summary.get('trial_action_name', '')}",
        },
        {
            "label": "Smoke Pass Rate",
            "value": f"{float(smoke_hist_summary.get('pass_rate', 0.0) or 0.0):.2%}",
            "status": "PASS" if float(smoke_hist_summary.get('pass_rate', 0.0) or 0.0) >= 0.95 else "WARN",
            "note": f"count={int(smoke_hist_summary.get('count', 0) or 0)}",
        },
        {
            "label": "Smoke Trial Feasible",
            "value": f"{float(smoke_hist_summary.get('trial_feasible_rate', 0.0) or 0.0):.2%}",
            "status": "PASS" if float(smoke_hist_summary.get('trial_feasible_rate', 0.0) or 0.0) >= 0.90 else "WARN",
            "note": f"avg_trial_runtime_s={float(smoke_hist_summary.get('avg_trial_runtime_s', 0.0) or 0.0):.4f}",
        },
        {
            "label": "Smoke Strict Recommendation",
            "value": str(recommendation["recommendation"]),
            "status": "PASS" if bool(recommendation["strict_ready"]) else "INFO",
            "note": str(recommendation["reason"]),
        },
    ]
    if midas_section_library_summary_line:
        cards.append(
            {
                "label": "MIDAS Section Library",
                "value": "embedded ok" if ": ok |" in midas_section_library_summary_line.lower() else "check required",
                "status": "PASS" if ": ok |" in midas_section_library_summary_line.lower() else "WARN",
                "note": midas_section_library_summary_line,
            }
        )
    if midas_kds_geometry_bridge_summary_line:
        cards.append(
            {
                "label": "MIDAS KDS Geometry Bridge",
                "value": "tracked"
                if ": ok |" in midas_kds_geometry_bridge_summary_line.lower()
                else "check required",
                "status": "PASS" if ": ok |" in midas_kds_geometry_bridge_summary_line.lower() else "WARN",
                "note": midas_kds_geometry_bridge_summary_line,
            }
        )
    if midas_loadcomb_roundtrip_summary_line:
        cards.append(
            {
                "label": "MIDAS LOADCOMB Roundtrip",
                "value": "exact ok" if ": ok |" in midas_loadcomb_roundtrip_summary_line.lower() else "check required",
                "status": "PASS" if ": ok |" in midas_loadcomb_roundtrip_summary_line.lower() else "WARN",
                "note": midas_loadcomb_roundtrip_summary_line,
            }
        )
    commercial_benchmark_breadth_summary_line = str(
        committee_summary.get("commercial_benchmark_breadth_summary_line", ci_summary.get("commercial_benchmark_breadth_summary_line", ""))
        or ""
    ).strip()
    solver_breadth_summary_line = str(
        committee_summary.get("solver_breadth_summary_line", ci_summary.get("solver_breadth_summary_line", ""))
        or ""
    ).strip()
    element_material_breadth_summary_line = str(
        committee_summary.get(
            "element_material_breadth_summary_line",
            ci_summary.get("element_material_breadth_summary_line", ""),
        )
        or ""
    ).strip()
    material_constitutive_summary_line = str(
        committee_summary.get("material_constitutive_summary_line", ci_summary.get("material_constitutive_summary_line", ""))
        or ""
    ).strip()
    midas_kds_row_provenance_export_summary_line = str(
        committee_summary.get(
            "midas_kds_row_provenance_export_summary_line",
            ci_summary.get("midas_kds_row_provenance_export_summary_line", ""),
        )
        or ""
    ).strip()
    contact_readiness_summary_line = str(
        committee_summary.get("contact_readiness_summary_line", ci_summary.get("contact_readiness_summary_line", ""))
        or ""
    ).strip()
    foundation_soil_link_summary_line = str(
        committee_summary.get("foundation_soil_link_summary_line", ci_summary.get("foundation_soil_link_summary_line", ""))
        or ""
    ).strip()
    structural_contact_summary_line = str(
        committee_summary.get("structural_contact_summary_line", ci_summary.get("structural_contact_summary_line", ""))
        or ""
    ).strip()
    general_fe_contact_matrix_summary_line = str(
        committee_summary.get("general_fe_contact_matrix_summary_line", ci_summary.get("general_fe_contact_matrix_summary_line", ""))
        or ""
    ).strip()
    surface_interaction_benchmark_summary_line = str(
        committee_summary.get(
            "surface_interaction_benchmark_summary_line",
            ci_summary.get("surface_interaction_benchmark_summary_line", ""),
        )
        or ""
    ).strip()
    midas_interoperability_summary_line = str(
        committee_summary.get("midas_interoperability_summary_line", ci_summary.get("midas_interoperability_summary_line", ""))
        or ""
    ).strip()
    nonlinear_generalization_summary_line = str(
        committee_summary.get(
            "nonlinear_generalization_summary_line",
            ci_summary.get("nonlinear_generalization_summary_line", ""),
        )
        or ""
    ).strip()
    workflow_productization_summary_line = str(
        committee_summary.get(
            "workflow_productization_summary_line",
            ci_summary.get("workflow_productization_summary_line", ""),
        )
        or ""
    ).strip()
    commercial_readiness_summary_line = str(
        committee_summary.get("commercial_readiness_summary_line", ci_summary.get("commercial_readiness_summary_line", ""))
        or ""
    ).strip()
    if commercial_benchmark_breadth_summary_line:
        cards.append(
            {
                "label": "Benchmark Breadth",
                "value": "tracked",
                "status": "INFO",
                "note": commercial_benchmark_breadth_summary_line,
            }
        )
    if solver_breadth_summary_line:
        cards.append(
            {
                "label": "Solver Breadth",
                "value": "PASS" if "Solver breadth: PASS" in solver_breadth_summary_line else "CHECK",
                "status": "PASS" if "Solver breadth: PASS" in solver_breadth_summary_line else "WARN",
                "note": solver_breadth_summary_line,
            }
        )
    if element_material_breadth_summary_line:
        cards.append(
            {
                "label": "Element/Material Breadth",
                "value": "PASS"
                if "Element/material breadth: PASS" in element_material_breadth_summary_line
                else "CHECK",
                "status": "PASS"
                if "Element/material breadth: PASS" in element_material_breadth_summary_line
                else "WARN",
                "note": element_material_breadth_summary_line,
            }
        )
    if material_constitutive_summary_line:
        cards.append(
            {
                "label": "Material Constitutive",
                "value": "PASS" if "Material constitutive gate: PASS" in material_constitutive_summary_line else "CHECK",
                "status": "PASS" if "Material constitutive gate: PASS" in material_constitutive_summary_line else "WARN",
                "note": material_constitutive_summary_line,
            }
        )
    if midas_kds_row_provenance_export_summary_line:
        cards.append(
            {
                "label": "KDS Row Provenance Export",
                "value": "PASS"
                if "MIDAS KDS row provenance export: PASS" in midas_kds_row_provenance_export_summary_line
                else "CHECK",
                "status": "PASS"
                if "MIDAS KDS row provenance export: PASS" in midas_kds_row_provenance_export_summary_line
                else "WARN",
                "note": midas_kds_row_provenance_export_summary_line,
            }
        )
    if contact_readiness_summary_line:
        cards.append(
            {
                "label": "Contact Readiness",
                "value": "PASS" if "Contact readiness: PASS" in contact_readiness_summary_line else "CHECK",
                "status": "PASS" if "Contact readiness: PASS" in contact_readiness_summary_line else "WARN",
                "note": contact_readiness_summary_line,
            }
        )
    if foundation_soil_link_summary_line:
        cards.append(
            {
                "label": "Foundation/Soil Link",
                "value": "PASS" if "Foundation/soil link: PASS" in foundation_soil_link_summary_line else "CHECK",
                "status": "PASS" if "Foundation/soil link: PASS" in foundation_soil_link_summary_line else "WARN",
                "note": foundation_soil_link_summary_line,
            }
        )
    if structural_contact_summary_line:
        cards.append(
            {
                "label": "Structural Contact",
                "value": "PASS" if "Structural contact readiness: PASS" in structural_contact_summary_line else "GAP",
                "status": "PASS" if "Structural contact readiness: PASS" in structural_contact_summary_line else "WARN",
                "note": structural_contact_summary_line,
            }
        )
    if general_fe_contact_matrix_summary_line:
        cards.append(
            {
                "label": "General FE Contact Matrix",
                "value": "PASS" if "General FE contact matrix: PASS" in general_fe_contact_matrix_summary_line else "CHECK",
                "status": "PASS" if "General FE contact matrix: PASS" in general_fe_contact_matrix_summary_line else "WARN",
                "note": general_fe_contact_matrix_summary_line,
            }
        )
    if surface_interaction_benchmark_summary_line:
        cards.append(
            {
                "label": "Surface Interaction Benchmark",
                "value": "PASS"
                if "Surface interaction benchmark: PASS" in surface_interaction_benchmark_summary_line
                else "CHECK",
                "status": "PASS"
                if "Surface interaction benchmark: PASS" in surface_interaction_benchmark_summary_line
                else "WARN",
                "note": surface_interaction_benchmark_summary_line,
            }
        )
    if midas_interoperability_summary_line:
        cards.append(
            {
                "label": "MIDAS Interoperability",
                "value": "PASS"
                if "MIDAS interoperability/export readiness: PASS" in midas_interoperability_summary_line
                else "CHECK",
                "status": "PASS"
                if "MIDAS interoperability/export readiness: PASS" in midas_interoperability_summary_line
                else "WARN",
                "note": midas_interoperability_summary_line,
            }
        )
    performance_profiling_summary_line = str(
        committee_summary.get(
            "performance_profiling_summary_line",
            ci_summary.get("performance_profiling_summary_line", ""),
        )
        or ""
    ).strip()
    if performance_profiling_summary_line:
        performance_profiling_pass = "Performance profiling: PASS" in performance_profiling_summary_line
        cards.append(
            {
                "label": "Performance Profiling",
                "value": "PASS" if performance_profiling_pass else "CHECK",
                "status": "PASS" if performance_profiling_pass else "WARN",
                "note": performance_profiling_summary_line,
            }
        )
    solver_truthfulness_summary_line = str(
        committee_summary.get("solver_truthfulness_summary_line", ci_summary.get("solver_truthfulness_summary_line", ""))
        or ""
    ).strip()
    if solver_truthfulness_summary_line:
        solver_truthfulness_pass = (
            "Solver truthfulness gate: PASS" in solver_truthfulness_summary_line
            or "Solver truthfulness: PASS" in solver_truthfulness_summary_line
        )
        cards.append(
            {
                "label": "Solver Truthfulness",
                "value": "PASS" if solver_truthfulness_pass else "CHECK",
                "status": "PASS" if solver_truthfulness_pass else "WARN",
                "note": solver_truthfulness_summary_line,
            }
        )
    hardest_external_10case_kickoff_summary_line = str(
        committee_summary.get(
            "hardest_external_10case_kickoff_summary_line",
            ci_summary.get("hardest_external_10case_kickoff_summary_line", ""),
        )
        or ""
    ).strip()
    if hardest_external_10case_kickoff_summary_line:
        kickoff_pass = "Hardest external 10-case kickoff: PASS" in hardest_external_10case_kickoff_summary_line
        cards.append(
            {
                "label": "Hardest External 10-Case Kickoff",
                "value": "PASS" if kickoff_pass else "CHECK",
                "status": "PASS" if kickoff_pass else "WARN",
                "note": hardest_external_10case_kickoff_summary_line,
            }
        )
    if nonlinear_generalization_summary_line:
        cards.append(
            {
                "label": "Nonlinear Generalization",
                "value": "PASS"
                if "Nonlinear generalization: PASS" in nonlinear_generalization_summary_line
                else "CHECK",
                "status": "PASS"
                if "Nonlinear generalization: PASS" in nonlinear_generalization_summary_line
                else "WARN",
                "note": nonlinear_generalization_summary_line,
            }
        )
    if workflow_productization_summary_line:
        cards.append(
            {
                "label": "Workflow Productization",
                "value": "PASS"
                if "Workflow/interoperability productization: PASS" in workflow_productization_summary_line
                else "CHECK",
                "status": "PASS"
                if "Workflow/interoperability productization: PASS" in workflow_productization_summary_line
                else "WARN",
                "note": workflow_productization_summary_line,
            }
        )
    if commercial_readiness_summary_line:
        cards.append(
            {
                "label": "Commercial Readiness",
                "value": "PASS" if "Commercial readiness: PASS" in commercial_readiness_summary_line else "CHECK",
                "status": "PASS" if "Commercial readiness: PASS" in commercial_readiness_summary_line else "WARN",
                "note": commercial_readiness_summary_line,
            }
        )
    runtime_total_seconds = float(runtime_summary.get("total_seconds", 0.0) or 0.0)
    runtime_reused_steps = int(runtime_summary.get("reused_step_count", 0) or 0)
    runtime_total_steps = int(runtime_summary.get("step_count", 0) or 0)
    runtime_slowest = runtime_summary.get("slowest_steps", [])
    slowest_label = "n/a"
    if isinstance(runtime_slowest, list) and runtime_slowest:
        top = runtime_slowest[0]
        if isinstance(top, dict):
            slowest_label = f"{str(top.get('step', 'n/a'))}:{float(top.get('seconds', 0.0) or 0.0):.1f}s"
    cards.append(
        {
            "label": "Nightly Runtime",
            "value": f"{runtime_total_seconds:.1f}s",
            "status": "PASS" if runtime_total_seconds > 0.0 else "INFO",
            "note": f"steps={runtime_total_steps}, reused={runtime_reused_steps}, slowest={slowest_label}",
        }
    )
    comparable_mode = str(committee_summary.get("measured_chain_rolling_selection_mode", ""))
    comparable_dep = str(committee_summary.get("measured_chain_comparable_reference_deployment_model", ""))
    comparable_strict = bool(committee_summary.get("measured_chain_comparable_reference_strict_design_opt_cost_smoke", False))
    if comparable_mode or comparable_dep:
        cards.append(
            {
                "label": "Comparable Chain Reference",
                "value": comparable_mode or "n/a",
                "status": "INFO",
                "note": f"deployment={comparable_dep or 'n/a'}, strict_smoke={comparable_strict}",
            }
        )
    authority_changes = int(committee_summary.get("authority_catalog_diff_change_count", 0) or 0)
    cards.append(
        {
            "label": "Authority Routing Diff",
            "value": f"{authority_changes} changes",
            "status": "WARN" if authority_changes > 0 else "PASS",
            "note": (
                f"added={int(committee_summary.get('authority_catalog_diff_added_count', 0) or 0)}, "
                f"removed={int(committee_summary.get('authority_catalog_diff_removed_count', 0) or 0)}"
            ),
        }
    )
    return cards


def _nightly_runtime_summary(steps: list[dict]) -> dict[str, object]:
    total_seconds = 0.0
    reused_step_count = 0
    slowest_steps: list[dict[str, object]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        seconds = float(step.get("seconds", 0.0) or 0.0)
        total_seconds += seconds
        if bool(step.get("reused_existing", False)):
            reused_step_count += 1
        slowest_steps.append(
            {
                "step": str(step.get("step", "")),
                "seconds": float(seconds),
                "reused_existing": bool(step.get("reused_existing", False)),
                "return_code": int(step.get("return_code", 0) or 0),
            }
        )
    slowest_steps = sorted(slowest_steps, key=lambda item: float(item.get("seconds", 0.0) or 0.0), reverse=True)[:8]
    return {
        "step_count": int(len(steps)),
        "reused_step_count": int(reused_step_count),
        "fresh_step_count": int(max(len(steps) - reused_step_count, 0)),
        "total_seconds": float(total_seconds),
        "slowest_steps": slowest_steps,
    }


def _build_payload(
    args: argparse.Namespace,
    *,
    reason_code: str,
    steps: list[dict],
    smoke_payload: dict,
    smoke_history_payload: dict,
    smoke_recommendation: dict,
    committee_summary: dict,
    archive_manifest: str = "",
) -> dict:
    ci_summary = load_json(args.ci_report)
    runtime_summary = _nightly_runtime_summary(steps)
    payload = {
        "schema_version": "1.0",
        "run_id": "phase3-nightly-release-gate",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "design_optimization_entrypoint_status_rows": entrypoint_status_rows(),
        "design_optimization_entrypoint_group_rows": entrypoint_group_rows(),
        "summary_cards": _nightly_summary_cards(
            reason_code=reason_code,
            smoke_payload=smoke_payload,
            smoke_history_payload=smoke_history_payload,
            committee_summary=committee_summary,
            ci_summary=ci_summary,
            runtime_summary=runtime_summary,
        ),
        "runtime_summary": runtime_summary,
        "design_optimization_cost_reduction_smoke": smoke_payload,
        "design_optimization_cost_reduction_smoke_history": smoke_history_payload,
        "design_optimization_cost_reduction_smoke_strict_recommendation": smoke_recommendation,
        "committee_summary_snapshot": {
            "measured_chain_rolling_selection_mode": str(committee_summary.get("measured_chain_rolling_selection_mode", "")),
            "measured_chain_comparable_reference_deployment_model": str(
                committee_summary.get("measured_chain_comparable_reference_deployment_model", "")
            ),
            "midas_section_library_summary_line": str(
                committee_summary.get("midas_section_library_summary_line", ci_summary.get("midas_section_library_summary_line", ""))
            ),
            "midas_kds_geometry_bridge_summary_line": _prefer_richer_summary_line(
                committee_summary.get("midas_kds_geometry_bridge_summary_line", ""),
                ci_summary.get("midas_kds_geometry_bridge_summary_line", ""),
                required_fragments=("registry=",),
            ),
            "midas_loadcomb_roundtrip_summary_line": str(
                committee_summary.get("midas_loadcomb_roundtrip_summary_line", ci_summary.get("midas_loadcomb_roundtrip_summary_line", ""))
            ),
            "solver_breadth_summary_line": str(
                committee_summary.get("solver_breadth_summary_line", ci_summary.get("solver_breadth_summary_line", ""))
            ),
            "element_material_breadth_summary_line": str(
                committee_summary.get(
                    "element_material_breadth_summary_line",
                    ci_summary.get("element_material_breadth_summary_line", ""),
                )
            ),
            "material_constitutive_summary_line": str(
                committee_summary.get("material_constitutive_summary_line", ci_summary.get("material_constitutive_summary_line", ""))
            ),
            "midas_kds_row_provenance_export_summary_line": str(
                committee_summary.get(
                    "midas_kds_row_provenance_export_summary_line",
                    ci_summary.get("midas_kds_row_provenance_export_summary_line", ""),
                )
            ),
            "contact_readiness_summary_line": str(
                committee_summary.get("contact_readiness_summary_line", ci_summary.get("contact_readiness_summary_line", ""))
            ),
            "foundation_soil_link_summary_line": str(
                committee_summary.get("foundation_soil_link_summary_line", ci_summary.get("foundation_soil_link_summary_line", ""))
            ),
            "structural_contact_summary_line": str(
                committee_summary.get("structural_contact_summary_line", ci_summary.get("structural_contact_summary_line", ""))
            ),
            "general_fe_contact_matrix_summary_line": str(
                committee_summary.get("general_fe_contact_matrix_summary_line", ci_summary.get("general_fe_contact_matrix_summary_line", ""))
            ),
            "surface_interaction_benchmark_summary_line": str(
                committee_summary.get(
                    "surface_interaction_benchmark_summary_line",
                    ci_summary.get("surface_interaction_benchmark_summary_line", ""),
                )
            ),
            "midas_interoperability_summary_line": str(
                committee_summary.get("midas_interoperability_summary_line", ci_summary.get("midas_interoperability_summary_line", ""))
            ),
            "korean_source_ingest_gate_summary_line": str(
                committee_summary.get(
                    "korean_source_ingest_gate_summary_line",
                    ci_summary.get("korean_source_ingest_gate_summary_line", ""),
                )
            ),
            "midas_native_roundtrip_summary_line": str(
                committee_summary.get("midas_native_roundtrip_summary_line", ci_summary.get("midas_native_roundtrip_summary_line", ""))
            ),
            "performance_profiling_summary_line": str(
                committee_summary.get(
                    "performance_profiling_summary_line",
                    ci_summary.get("performance_profiling_summary_line", ""),
                )
            ),
            "irregular_structure_collection_gate_summary_line": str(
                committee_summary.get(
                    "irregular_structure_collection_gate_summary_line",
                    ci_summary.get("irregular_structure_collection_gate_summary_line", ""),
                )
            ),
            "irregular_top5_execution_manifest_summary_line": str(
                committee_summary.get(
                    "irregular_top5_execution_manifest_summary_line",
                    ci_summary.get("irregular_top5_execution_manifest_summary_line", ""),
                )
            ),
            "solver_truthfulness_summary_line": str(
                committee_summary.get("solver_truthfulness_summary_line", ci_summary.get("solver_truthfulness_summary_line", ""))
            ),
            "hardest_external_10case_kickoff_summary_line": str(
                committee_summary.get(
                    "hardest_external_10case_kickoff_summary_line",
                    ci_summary.get("hardest_external_10case_kickoff_summary_line", ""),
                )
            ),
            "nonlinear_generalization_summary_line": str(
                committee_summary.get(
                    "nonlinear_generalization_summary_line",
                    ci_summary.get("nonlinear_generalization_summary_line", ""),
                )
            ),
            "workflow_productization_summary_line": str(
                committee_summary.get(
                    "workflow_productization_summary_line",
                    ci_summary.get("workflow_productization_summary_line", ""),
                )
            ),
            "commercial_benchmark_breadth_summary_line": str(
                committee_summary.get("commercial_benchmark_breadth_summary_line", ci_summary.get("commercial_benchmark_breadth_summary_line", ""))
            ),
            "commercial_readiness_summary_line": str(
                committee_summary.get("commercial_readiness_summary_line", ci_summary.get("commercial_readiness_summary_line", ""))
            ),
            "measured_chain_comparable_reference_strict_design_opt_cost_smoke": bool(
                committee_summary.get("measured_chain_comparable_reference_strict_design_opt_cost_smoke", False)
            ),
            "authority_catalog_diff_change_count": int(committee_summary.get("authority_catalog_diff_change_count", 0) or 0),
            "authority_catalog_diff_added_count": int(committee_summary.get("authority_catalog_diff_added_count", 0) or 0),
            "authority_catalog_diff_removed_count": int(committee_summary.get("authority_catalog_diff_removed_count", 0) or 0),
            "authority_catalog_routing_warning_active": bool(
                committee_summary.get("authority_catalog_routing_warning_active", False)
            ),
            "panel_zone_3d_clash_ready": bool(committee_summary.get("panel_zone_3d_clash_ready", False)),
            "panel_zone_constructability_mode": str(committee_summary.get("panel_zone_constructability_mode", "")),
            "panel_zone_source_contract_mode": str(committee_summary.get("panel_zone_source_contract_mode", "")),
            "panel_zone_proxy_candidate_count": int(committee_summary.get("panel_zone_proxy_candidate_count", 0) or 0),
            "panel_zone_solver_verified_inbox_status_mode": str(
                committee_summary.get("panel_zone_solver_verified_inbox_status_mode", "")
            ),
            "panel_zone_solver_verified_pending_input": bool(
                committee_summary.get("panel_zone_solver_verified_pending_input", False)
            ),
            "panel_zone_solver_verified_latest_consume_contract_pass": bool(
                committee_summary.get("panel_zone_solver_verified_latest_consume_contract_pass", False)
            ),
            "foundation_optimization_ready": bool(committee_summary.get("foundation_optimization_ready", False)),
            "foundation_optimization_mode": str(committee_summary.get("foundation_optimization_mode", "")),
            "foundation_scope_source": str(committee_summary.get("foundation_scope_source", "")),
            "upstream_foundation_label_count": int(committee_summary.get("upstream_foundation_label_count", 0) or 0),
        },
        "inputs": {
            "candidate_id": str(args.candidate_id),
            "input_path": str(args.input_path),
            "download_if_missing": bool(args.download_if_missing),
            "gpu_strict": bool(args.gpu_strict),
            "allow_cpu_required": bool(args.allow_cpu_required),
            "scale_levels_nightly": str(args.scale_levels_nightly),
            "scale_levels_io": str(args.scale_levels_io),
            "partition_max_projection_ratio": float(args.partition_max_projection_ratio),
            "enable_hip_kernel_smoke": bool(args.enable_hip_kernel_smoke),
            "hipcc": str(args.hipcc),
            "rocm_path": str(args.rocm_path),
            "rocm_device_lib_path": str(args.rocm_device_lib_path),
            "nightly_10m_repro_runs": int(args.nightly_10m_repro_runs),
            "enable_ndtha_long_profile": bool(args.enable_ndtha_long_profile),
            "ndtha_long_profile_runs": int(args.ndtha_long_profile_runs),
            "reuse_existing_if_present": bool(args.reuse_existing_if_present),
            "report_reuse_max_age_sec": float(args.report_reuse_max_age_sec),
            "commercial_readiness_model_cases": str(args.commercial_readiness_model_cases),
            "commercial_readiness_target_split": str(args.commercial_readiness_target_split),
            "commercial_readiness_strict_benchmark_breadth": bool(args.commercial_readiness_strict_benchmark_breadth),
            "solver_breadth_report": str(args.solver_breadth_report),
            "contact_readiness_report": str(args.contact_readiness_report),
            "surface_interaction_benchmark_report": str(args.surface_interaction_benchmark_report),
            "midas_interoperability_report": str(args.midas_interoperability_report),
            "public_native_corpus_catalog": str(args.public_native_corpus_catalog),
            "public_native_corpus_dir": str(args.public_native_corpus_dir),
            "public_native_corpus_report": str(args.public_native_corpus_report),
            "midas_native_corpus_manifest": str(args.midas_native_corpus_manifest),
            "irregular_structure_source_catalog": str(args.irregular_structure_source_catalog),
            "irregular_structure_triage_report": str(args.irregular_structure_triage_report),
            "irregular_structure_collection_report": str(args.irregular_structure_collection_report),
            "irregular_structure_collection_gate_report": str(args.irregular_structure_collection_gate_report),
            "irregular_top5_execution_manifest": str(args.irregular_top5_execution_manifest),
            "midas_native_writeback_diff_receipts_report": str(args.midas_native_writeback_diff_receipts_report),
            "midas_native_roundtrip_report": str(args.midas_native_roundtrip_report),
            "nonlinear_generalization_report": str(args.nonlinear_generalization_report),
            "workflow_productization_report": str(args.workflow_productization_report),
            "ndtha_cases": str(args.ndtha_cases),
            "ndtha_target_split": str(args.ndtha_target_split),
            "ndtha_ground_motion_csv": str(args.ndtha_ground_motion_csv),
            "opensees_model": str(args.opensees_model),
            "require_real_topology": bool(args.require_real_topology),
            "require_shell_beam_mix": bool(args.require_shell_beam_mix),
            "noise_seeds": str(args.noise_seeds),
            "noise_stiffness_levels_pct": str(args.noise_stiffness_levels_pct),
            "noise_min_seed_count": int(args.noise_min_seed_count),
            "mgt_input": str(args.mgt_input),
            "mgt_json_out": str(args.mgt_json_out),
            "mgt_npz_out": str(args.mgt_npz_out),
            "mgt_edge_list_out": str(args.mgt_edge_list_out),
            "prefer_mgt_for_partition": bool(args.prefer_mgt_for_partition),
            "mgt_require_shell_beam_mix": bool(args.mgt_require_shell_beam_mix),
            "global_authority_catalog": str(args.global_authority_catalog),
            "global_authority_workdir": str(args.global_authority_workdir),
            "wind_csv": str(args.wind_csv),
            "wind_source_manifest": str(args.wind_source_manifest),
            "damper_catalog": str(args.damper_catalog),
            "rc_benchmark_cases": str(args.rc_benchmark_cases),
            "version_lock_manifest": str(args.version_lock_manifest),
            "skip_promotion": bool(args.skip_promotion),
            "skip_archive": bool(args.skip_archive),
            "dry_run": bool(args.dry_run),
            "reuse_existing_if_present": bool(args.reuse_existing_if_present),
            "enable_design_opt_cost_smoke": bool(args.enable_design_opt_cost_smoke),
            "strict_design_opt_cost_smoke": bool(args.strict_design_opt_cost_smoke),
            "design_opt_cost_smoke_history": str(args.design_opt_cost_smoke_history),
            "design_opt_cost_smoke_history_limit": int(args.design_opt_cost_smoke_history_limit),
            "design_opt_cost_smoke_objective_profile": str(args.design_opt_cost_smoke_objective_profile),
            "design_opt_cost_smoke_ndtha_step_count": int(args.design_opt_cost_smoke_ndtha_step_count),
            "committee_summary_report": str(args.committee_summary_report),
            "committee_package_report": str(args.committee_package_report),
            "pbd_review_package_report": str(args.pbd_review_package_report),
            "code_check_report": str(args.code_check_report),
            "design_opt_dataset_report": str(args.design_opt_dataset_report),
            "design_opt_dataset_npz": str(args.design_opt_dataset_npz),
            "design_opt_cost_reduction_changes": str(args.design_opt_cost_reduction_changes),
            "design_opt_rebar_payload_projection_json": str(args.design_opt_rebar_payload_projection_json),
            "design_opt_connection_detailing_payload_projection_json": str(
                args.design_opt_connection_detailing_payload_projection_json
            ),
            "design_opt_detailing_payload_projection_json": str(args.design_opt_detailing_payload_projection_json),
            "mgt_export_output_mgt": str(args.mgt_export_output_mgt),
            "mgt_export_report": str(args.mgt_export_report),
            "mgt_export_patch_manifest": str(args.mgt_export_patch_manifest),
            "mgt_export_instruction_sidecar": str(args.mgt_export_instruction_sidecar),
            "mgt_export_audit_review_manifest": str(args.mgt_export_audit_review_manifest),
            "mgt_export_audit_review_packet_manifest": str(args.mgt_export_audit_review_packet_manifest),
            "mgt_export_audit_review_packet_directory": str(args.mgt_export_audit_review_packet_directory),
            "mgt_export_audit_review_queue_manifest": str(args.mgt_export_audit_review_queue_manifest),
            "mgt_export_audit_review_queue_status_directory": str(args.mgt_export_audit_review_queue_status_directory),
            "mgt_export_audit_review_followup_manifest": str(args.mgt_export_audit_review_followup_manifest),
            "panel_zone_clash_artifact": str(args.panel_zone_clash_artifact),
            "panel_zone_solver_export_bundle": str(args.panel_zone_solver_export_bundle),
            "panel_zone_solver_verified_drop_dir": str(args.panel_zone_solver_verified_drop_dir),
            "panel_zone_solver_verified_joint_geometry_source": str(args.panel_zone_solver_verified_joint_geometry_source),
            "panel_zone_solver_verified_rebar_anchorage_source": str(args.panel_zone_solver_verified_rebar_anchorage_source),
            "panel_zone_solver_verified_clash_verification_source": str(args.panel_zone_solver_verified_clash_verification_source),
            "panel_zone_solver_verified_source_origin_class": str(args.panel_zone_solver_verified_source_origin_class),
            "panel_zone_solver_verified_drop_dir_discovered_bundle": str(
                getattr(args, "panel_zone_solver_verified_drop_dir_discovered_bundle", "")
            ),
            "panel_zone_solver_verified_drop_dir_discovered_joint_geometry_source": str(
                getattr(args, "panel_zone_solver_verified_drop_dir_discovered_joint_geometry_source", "")
            ),
            "panel_zone_solver_verified_drop_dir_discovered_rebar_anchorage_source": str(
                getattr(args, "panel_zone_solver_verified_drop_dir_discovered_rebar_anchorage_source", "")
            ),
            "panel_zone_solver_verified_drop_dir_discovered_clash_verification_source": str(
                getattr(args, "panel_zone_solver_verified_drop_dir_discovered_clash_verification_source", "")
            ),
            "panel_zone_solver_verified_drop_dir_discovered_source_origin_class": str(
                getattr(args, "panel_zone_solver_verified_drop_dir_discovered_source_origin_class", "")
            ),
            "panel_zone_joint_geometry_artifact": str(args.panel_zone_joint_geometry_artifact),
            "panel_zone_rebar_anchorage_artifact": str(args.panel_zone_rebar_anchorage_artifact),
            "panel_zone_clash_verification_artifact": str(args.panel_zone_clash_verification_artifact),
            "panel_zone_joint_geometry_source_output": str(args.panel_zone_joint_geometry_source_output),
            "panel_zone_rebar_anchorage_source_output": str(args.panel_zone_rebar_anchorage_source_output),
            "panel_zone_clash_verification_source_output": str(args.panel_zone_clash_verification_source_output),
            "panel_zone_joint_geometry_contract": str(args.panel_zone_joint_geometry_contract),
            "panel_zone_rebar_anchorage_contract": str(args.panel_zone_rebar_anchorage_contract),
            "panel_zone_clash_verification_contract": str(args.panel_zone_clash_verification_contract),
            "panel_zone_solver_verified_inbox_status_report": str(args.panel_zone_solver_verified_inbox_status_report),
            "foundation_optimization_artifact": str(args.foundation_optimization_artifact),
            "wind_raw_input": str(args.wind_raw_input),
            "wind_raw_manifest": str(args.wind_raw_manifest),
            "wind_benchmark_asset_registry": str(args.wind_benchmark_asset_registry),
            "wind_raw_mapping_artifact": str(args.wind_raw_mapping_artifact),
            "tpu_hffb_benchmark_report": str(args.tpu_hffb_benchmark_report),
            "peer_spd_column_seed_manifest": str(args.peer_spd_column_seed_manifest),
            "peer_spd_column_materialize_report": str(args.peer_spd_column_materialize_report),
            "pbd_hinge_benchmark_asset_registry": str(args.pbd_hinge_benchmark_asset_registry),
            "peer_spd_hinge_benchmark_report": str(args.peer_spd_hinge_benchmark_report),
            "peer_spd_hinge_fixture_regression_report": str(args.peer_spd_hinge_fixture_regression_report),
            "peer_spd_hinge_alignment_report": str(args.peer_spd_hinge_alignment_report),
            "external_benchmark_submission_readiness_report": str(args.external_benchmark_submission_readiness_report),
            "external_benchmark_kickoff_dir": str(args.external_benchmark_kickoff_dir),
            "external_benchmark_kickoff_package_report": str(args.external_benchmark_kickoff_package_report),
            "external_benchmark_execution_manifest_report": str(args.external_benchmark_execution_manifest_report),
            "external_benchmark_execution_updates_json": str(args.external_benchmark_execution_updates_json),
            "external_benchmark_execution_status_manifest_report": str(
                args.external_benchmark_execution_status_manifest_report
            ),
            "audit_review_decision_batch_template_json": str(args.audit_review_decision_batch_template_json),
            "audit_review_decision_batch_preview_artifacts_report": str(
                args.audit_review_decision_batch_preview_artifacts_report
            ),
            "structural_optimization_viewer_dir": str(args.structural_optimization_viewer_dir),
            "optimized_drawing_review_html": str(
                Path(args.structural_optimization_viewer_dir) / "optimized_drawing_review.html"
            ),
            "optimized_drawing_review_summary_json": str(
                Path(args.structural_optimization_viewer_dir) / "optimized_drawing_review_summary.json"
            ),
            "pbd_hinge_refresh_source_input": str(args.pbd_hinge_refresh_source_input),
            "pbd_hinge_refresh_source_output": str(args.pbd_hinge_refresh_source_output),
            "pbd_hinge_refresh_artifact": str(args.pbd_hinge_refresh_artifact),
            "release_gap_history_root": str(args.release_gap_history_root),
            "release_gap_history_limit": int(args.release_gap_history_limit),
        },
        "reports": {
            "hip_kernel_smoke": str(args.hip_kernel_smoke_report),
            "commercial_csv_gate": str(args.commercial_csv_gate),
            "midas_mgt_conversion": str(args.mgt_conversion_report),
            "commercial_readiness": str(args.commercial_readiness_report),
            "solver_breadth": str(args.solver_breadth_report),
            "contact_readiness": str(args.contact_readiness_report),
            "surface_interaction_benchmark": str(args.surface_interaction_benchmark_report),
            "midas_interoperability": str(args.midas_interoperability_report),
            "public_native_corpus": str(args.public_native_corpus_report),
            "midas_native_corpus_manifest": str(args.midas_native_corpus_manifest),
            "irregular_structure_source_catalog": str(args.irregular_structure_source_catalog),
            "irregular_structure_triage_report": str(args.irregular_structure_triage_report),
            "irregular_structure_collection_report": str(args.irregular_structure_collection_report),
            "irregular_structure_collection_gate": str(args.irregular_structure_collection_gate_report),
            "irregular_top5_execution_manifest": str(args.irregular_top5_execution_manifest),
            "irregular_priority_families": str(args.irregular_priority_families),
            "midas_native_writeback_diff_receipts": str(args.midas_native_writeback_diff_receipts_report),
            "midas_native_roundtrip": str(args.midas_native_roundtrip_report),
            "nonlinear_generalization": str(args.nonlinear_generalization_report),
            "workflow_productization": str(args.workflow_productization_report),
            "real_source_multi": str(args.real_source_multi_report),
            "nonlinear_engine": str(args.nonlinear_engine_report),
            "pushover_stress": str(args.pushover_stress_report),
            "ndtha_stress": str(args.ndtha_stress_report),
            "ndtha_residual": str(args.ndtha_residual_report),
            "global_authority_gate": str(args.global_authority_report),
            "wind_benchmark": str(args.wind_benchmark_report),
            "ssi_boundary": str(args.ssi_boundary_report),
            "damper_validation": str(args.damper_validation_report),
            "kds_compliance": str(args.kds_compliance_summary),
            "construction_sequence": str(args.construction_sequence_report),
            "flexible_diaphragm": str(args.flexible_diaphragm_report),
            "repro_version_lock": str(args.repro_version_lock_report),
            "release_registry": str(args.release_registry_report),
            "solver_hip_e2e": str(args.solver_hip_e2e_report),
            "solver_truthfulness": str(args.solver_truthfulness_report),
            "hardest_external_10case_kickoff": str(args.hardest_external_10case_kickoff_report),
            "rc_benchmark_lock": str(args.rc_benchmark_lock_report),
            "version_lock_manifest": str(args.version_lock_manifest),
            "phase3_pipeline": str(args.phase3_report),
            "topology_gate": str(args.topology_gate),
            "partitioned_scaleout": str(args.partitioned_scaleout),
            "sync_stress": str(args.sync_stress),
            "noise_convergence": str(args.noise_convergence),
            "scaleout_io": str(args.scaleout_io),
            "nightly_10m_repro": str(args.nightly_10m_repro),
            "ndtha_long_profile": str(args.ndtha_long_profile),
            "ci_gate": str(args.ci_report),
            "design_opt_cost_reduction_smoke": str(args.design_opt_cost_smoke_report),
            "design_opt_cost_reduction_smoke_history": str(args.design_opt_cost_smoke_history),
            "design_opt_dataset": str(args.design_opt_dataset_report),
            "design_opt_rebar_payload_projection": str(args.design_opt_rebar_payload_projection_json),
            "design_opt_connection_detailing_payload_projection": str(
                args.design_opt_connection_detailing_payload_projection_json
            ),
            "design_opt_detailing_payload_projection": str(args.design_opt_detailing_payload_projection_json),
            "mgt_export_output_mgt": str(args.mgt_export_output_mgt),
            "mgt_export": str(args.mgt_export_report),
            "mgt_export_patch_manifest": str(args.mgt_export_patch_manifest),
            "mgt_export_instruction_sidecar": str(args.mgt_export_instruction_sidecar),
            "mgt_export_audit_review_manifest": str(args.mgt_export_audit_review_manifest),
            "mgt_export_audit_review_packet_manifest": str(args.mgt_export_audit_review_packet_manifest),
            "mgt_export_audit_review_packet_directory": str(args.mgt_export_audit_review_packet_directory),
            "mgt_export_audit_review_queue_manifest": str(args.mgt_export_audit_review_queue_manifest),
            "mgt_export_audit_review_queue_status_directory": str(args.mgt_export_audit_review_queue_status_directory),
            "mgt_export_audit_review_followup_manifest": str(args.mgt_export_audit_review_followup_manifest),
            "static_validation": str(args.static_validation),
            "freeze_release": str(args.freeze_report),
            "promotion": str(args.promotion_report),
            "pbd_hinge_refresh_source": str(args.pbd_hinge_refresh_source_output),
            "pbd_hinge_refresh_artifact": str(args.pbd_hinge_refresh_artifact),
            "pbd_hinge_refresh": str(args.pbd_hinge_refresh_report),
            "panel_zone_joint_geometry_source": str(args.panel_zone_joint_geometry_source_output),
            "panel_zone_rebar_anchorage_source": str(args.panel_zone_rebar_anchorage_source_output),
            "panel_zone_clash_verification_source": str(args.panel_zone_clash_verification_source_output),
            "panel_zone_solver_export_bundle": str(args.panel_zone_solver_export_bundle),
            "panel_zone_solver_verified_export_bundle": str(args.panel_zone_solver_export_bundle),
            "panel_zone_joint_geometry_contract": str(args.panel_zone_joint_geometry_contract),
            "panel_zone_rebar_anchorage_contract": str(args.panel_zone_rebar_anchorage_contract),
            "panel_zone_clash_verification_contract": str(args.panel_zone_clash_verification_contract),
            "panel_zone_clash": str(args.panel_zone_clash_report),
            "panel_zone_solver_verified_inbox_status": str(args.panel_zone_solver_verified_inbox_status_report),
            "foundation_optimization": str(args.foundation_optimization_report),
            "wind_tunnel_raw_mapping": str(args.wind_raw_mapping_report),
            "tpu_hffb_benchmark": str(args.tpu_hffb_benchmark_report),
            "pbd_hinge_benchmark_asset_registry": str(args.pbd_hinge_benchmark_asset_registry),
            "peer_spd_hinge_benchmark": str(args.peer_spd_hinge_benchmark_report),
            "peer_spd_hinge_fixture_regression": str(args.peer_spd_hinge_fixture_regression_report),
            "peer_spd_hinge_alignment": str(args.peer_spd_hinge_alignment_report),
            "release_gap_report": str(args.release_gap_report),
            "release_gap_markdown": str(args.release_gap_markdown),
            "release_gap_smoke_history_png": str(args.release_gap_smoke_history_png),
            "release_gap_measured_chain_category_png": str(args.release_gap_measured_chain_category_png),
            "external_benchmark_submission_readiness": str(args.external_benchmark_submission_readiness_report),
            "external_benchmark_kickoff_package": str(args.external_benchmark_kickoff_package_report),
            "external_benchmark_execution_manifest": str(args.external_benchmark_execution_manifest_report),
            "external_benchmark_execution_status_manifest": str(
                args.external_benchmark_execution_status_manifest_report
            ),
            "audit_review_decision_batch_template": str(args.audit_review_decision_batch_template_json),
            "audit_review_decision_batch_approve_all_attested_example": str(
                Path(args.external_benchmark_kickoff_dir)
                / "audit_review_decision_batch_approve_all.attested_example.json"
            ),
            "audit_review_decision_batch_mixed_attested_example": str(
                Path(args.external_benchmark_kickoff_dir)
                / "audit_review_decision_batch_mixed.attested_example.json"
            ),
            "audit_review_decision_batch_approve_all_preview_input": str(
                Path(args.external_benchmark_kickoff_dir) / "audit_review_decision_batch_approve_all.preview.json"
            ),
            "audit_review_decision_batch_reject_one_preview_input": str(
                Path(args.external_benchmark_kickoff_dir) / "audit_review_decision_batch_reject_one.preview.json"
            ),
            "external_benchmark_submission_preview_approve_all": str(
                Path(args.external_benchmark_kickoff_dir)
                / "external_benchmark_submission_readiness_preview.approve_all.json"
            ),
            "external_benchmark_submission_preview_reject_one": str(
                Path(args.external_benchmark_kickoff_dir)
                / "external_benchmark_submission_readiness_preview.reject_one.json"
            ),
            "audit_review_decision_batch_live_preview": str(
                Path(args.external_benchmark_kickoff_dir) / "audit_review_decision_batch.live_preview.json"
            ),
            "audit_review_decision_batch_run_report": str(
                Path(args.external_benchmark_kickoff_dir) / "audit_review_decision_batch_run_report.json"
            ),
            "audit_review_decision_batch_preview_artifacts_report": str(
                args.audit_review_decision_batch_preview_artifacts_report
            ),
            "structural_optimization_viewer_json": str(
                Path(args.structural_optimization_viewer_dir) / "structural_optimization_viewer.json"
            ),
            "structural_optimization_viewer_html": str(
                Path(args.structural_optimization_viewer_dir) / "structural_optimization_viewer.html"
            ),
            "optimized_drawing_review_html": str(
                Path(args.structural_optimization_viewer_dir) / "optimized_drawing_review.html"
            ),
            "optimized_drawing_review_summary_json": str(
                Path(args.structural_optimization_viewer_dir) / "optimized_drawing_review_summary.json"
            ),
        },
        "steps": steps,
        "contract_pass": bool(reason_code == "PASS"),
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }
    if archive_manifest:
        payload["artifact_archive_manifest"] = archive_manifest
    return payload


def main() -> None:
    global RUN_ENV_OVERRIDES, REUSE_EXISTING_IF_PRESENT
    p = argparse.ArgumentParser()
    p.add_argument("--candidate-id", default="opstool_606m_megatall_model")
    p.add_argument("--input-path", default="implementation/phase1/open_data/megastructure")
    p.add_argument("--download-if-missing", action="store_true")
    p.add_argument("--gpu-strict", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--allow-cpu-required", action="store_true")
    p.add_argument("--noise-seeds", default="11,23,47")
    p.add_argument("--noise-stiffness-levels-pct", default="5,10")
    p.add_argument("--noise-min-seed-count", type=int, default=3)
    p.add_argument("--scale-levels-nightly", default="1000000,3000000,10000000")
    p.add_argument("--scale-levels-io", default="1000000,3000000")
    p.add_argument("--partition-max-projection-ratio", type=float, default=25000.0)
    p.add_argument("--enable-hip-kernel-smoke", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--hipcc", default="/opt/rocm/bin/hipcc")
    p.add_argument("--rocm-path", default="/opt/rocm")
    p.add_argument("--rocm-device-lib-path", default="")
    p.add_argument("--nightly-10m-repro-runs", type=int, default=3)
    p.add_argument("--enable-ndtha-long-profile", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--ndtha-long-profile-runs", type=int, default=2)
    p.add_argument(
        "--commercial-readiness-model-cases",
        default=(
            "implementation/phase1/commercial_benchmark_cases.rwth_zenodo.json,"
            "implementation/phase1/commercial_benchmark_cases.from_csv.json"
        ),
    )
    p.add_argument("--commercial-readiness-target-split", choices=["all", "train", "val", "test"], default="all")
    p.add_argument("--commercial-readiness-strict-benchmark-breadth", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--opensees-model", default="implementation/phase1/open_data/megastructure/opensees/SCBF16B_shell_beam_mix.tcl")
    p.add_argument("--require-real-topology", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--require-shell-beam-mix", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--runtime-hook-cmd", default="python3 implementation/phase1/rust_hip_md3bead_hook.py")
    p.add_argument("--producer-cmd", default="python3 implementation/phase1/rust_hip_md3bead_hook.py")
    p.add_argument("--skip-promotion", action="store_true")
    p.add_argument("--skip-archive", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--reuse-existing-if-present", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--report-reuse-max-age-sec", type=float, default=172800.0)
    p.add_argument("--global-authority-catalog", default="implementation/phase1/open_data/global_authority/authority_source_catalog.json")
    p.add_argument("--global-authority-workdir", default="implementation/phase1/open_data/global_authority/run_artifacts")
    p.add_argument("--mgt-input", default="implementation/phase1/open_data/midas/midas_generator_33.mgt")
    p.add_argument("--mgt-json-out", default="implementation/phase1/open_data/midas/midas_generator_33.json")
    p.add_argument("--mgt-npz-out", default="implementation/phase1/open_data/midas/midas_generator_33.npz")
    p.add_argument("--mgt-edge-list-out", default="implementation/phase1/open_data/midas/midas_generator_33_edges.json")
    p.add_argument("--prefer-mgt-for-partition", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--mgt-require-shell-beam-mix", action=argparse.BooleanOptionalAction, default=True)

    p.add_argument("--commercial-csv-gate", default="implementation/phase1/commercial_csv_gate_report.json")
    p.add_argument("--mgt-conversion-report", default="implementation/phase1/midas_mgt_conversion_report.json")
    p.add_argument("--hip-kernel-smoke-report", default="implementation/phase1/hip_kernel_smoke_report.json")
    p.add_argument("--phase3-report", default="implementation/phase1/phase3_megastructure_pipeline_report.json")
    p.add_argument("--commercial-readiness-report", default="implementation/phase1/commercial_readiness_report.json")
    p.add_argument("--solver-breadth-report", default="implementation/phase1/solver_breadth_report.json")
    p.add_argument("--contact-readiness-report", default="implementation/phase1/contact_readiness_report.json")
    p.add_argument("--material-constitutive-report", default="implementation/phase1/material_constitutive_gate_report.json")
    p.add_argument("--surface-interaction-benchmark-report", default="implementation/phase1/surface_interaction_benchmark_gate_report.json")
    p.add_argument("--midas-interoperability-report", default="implementation/phase1/midas_interoperability_gate_report.json")
    p.add_argument(
        "--public-native-corpus-catalog",
        default="implementation/phase1/open_data/midas/public_native_mgt_source_catalog.json",
    )
    p.add_argument(
        "--public-native-corpus-dir",
        default="implementation/phase1/open_data/midas/public_native_corpus",
    )
    p.add_argument(
        "--public-native-corpus-report",
        default="implementation/phase1/open_data/midas/public_native_corpus_report.json",
    )
    p.add_argument("--korean-source-seed-json", default="implementation/phase1/open_data/korea/korean_source_seed.json")
    p.add_argument("--korean-source-catalog", default="implementation/phase1/open_data/korea/korean_source_catalog.json")
    p.add_argument(
        "--korean-public-structure-out-dir",
        default="implementation/phase1/open_data/korea/collected",
    )
    p.add_argument(
        "--korean-public-structure-collection-report",
        default="implementation/phase1/open_data/korea/korean_public_structure_collection_report.json",
    )
    p.add_argument(
        "--korean-source-ingest-report",
        default="implementation/phase1/open_data/korea/korean_source_ingest_report.json",
    )
    p.add_argument("--korean-source-ingest-gate-report", default="implementation/phase1/korean_source_ingest_gate_report.json")
    p.add_argument(
        "--korean-solver-ready-reconstruction-out-dir",
        default="implementation/phase1/release/midas_native_roundtrip/solver_ready_reconstruction",
    )
    p.add_argument(
        "--korean-solver-ready-reconstruction-report",
        default="implementation/phase1/release/midas_native_roundtrip/korean_solver_ready_reconstruction_report.json",
    )
    p.add_argument("--midas-native-corpus-manifest", default="implementation/phase1/open_data/midas/midas_native_corpus_manifest.json")
    p.add_argument(
        "--irregular-structure-source-catalog",
        default="implementation/phase1/open_data/irregular/irregular_structure_source_catalog.json",
    )
    p.add_argument(
        "--irregular-structure-triage-report",
        default="implementation/phase1/open_data/irregular/irregular_structure_triage_report.json",
    )
    p.add_argument(
        "--irregular-structure-collection-report",
        default="implementation/phase1/open_data/irregular/irregular_structure_collection_report.json",
    )
    p.add_argument(
        "--irregular-structure-collection-gate-report",
        default="implementation/phase1/irregular_structure_collection_gate_report.json",
    )
    p.add_argument(
        "--irregular-top5-execution-manifest",
        default="implementation/phase1/open_data/irregular/irregular_top5_execution_manifest.json",
    )
    p.add_argument(
        "--irregular-priority-families",
        default="implementation/phase1/open_data/irregular/priority_irregular_structure_families.json",
    )
    p.add_argument(
        "--midas-native-writeback-diff-receipts-report",
        default="implementation/phase1/release/midas_native_roundtrip/midas_native_writeback_diff_receipts_report.json",
    )
    p.add_argument("--midas-native-roundtrip-report", default="implementation/phase1/midas_native_roundtrip_gate_report.json")
    p.add_argument("--nonlinear-generalization-report", default="implementation/phase1/nonlinear_generalization_gate_report.json")
    p.add_argument("--workflow-productization-report", default="implementation/phase1/workflow_productization_gate_report.json")
    p.add_argument("--structural-contact-report", default="implementation/phase1/structural_contact_gate_report.json")
    p.add_argument("--general-fe-contact-benchmark-report", default="implementation/phase1/general_fe_contact_benchmark_gate_report.json")
    p.add_argument("--foundation-soil-link-report", default="implementation/phase1/foundation_soil_link_gate_report.json")
    p.add_argument("--substructuring-interface-report", default="implementation/phase1/substructuring_interface_report.json")
    p.add_argument("--soil-tunnel-ssi-report", default="implementation/phase1/soil_tunnel_ssi_report.json")
    p.add_argument("--real-source-multi-report", default="implementation/phase1/real_source_multi_gate_report.json")
    p.add_argument("--nonlinear-engine-report", default="implementation/phase1/nonlinear_frame_engine_report.json")
    p.add_argument("--nonlinear-cases", default="implementation/phase1/commercial_benchmark_cases.from_csv.json")
    p.add_argument("--nonlinear-target-split", choices=["all", "train", "val", "test"], default="test")
    p.add_argument("--pushover-stress-report", default="implementation/phase1/nonlinear_pushover_stress_report.json")
    p.add_argument("--pushover-cases", default="implementation/phase1/commercial_benchmark_cases.from_csv.json")
    p.add_argument("--pushover-target-split", choices=["all", "train", "val", "test"], default="test")
    p.add_argument("--ndtha-stress-report", default="implementation/phase1/nonlinear_ndtha_stress_report.json")
    p.add_argument("--ndtha-residual-report", default="implementation/phase1/ndtha_residual_gate_report.json")
    p.add_argument("--ndtha-cases", default="implementation/phase1/commercial_benchmark_cases.from_csv.json")
    p.add_argument("--ndtha-target-split", choices=["all", "train", "val", "test"], default="test")
    p.add_argument("--ndtha-ground-motion-csv", default="implementation/phase1/open_data/seismic/el_centro_like_60s_dt0p01.csv")
    p.add_argument("--wind-csv", default="implementation/phase1/open_data/wind/across_wind_10h_dt1s.csv")
    p.add_argument("--wind-source-manifest", default="implementation/phase1/open_data/wind/across_wind_10h_dt1s.manifest.json")
    p.add_argument("--damper-catalog", default="implementation/phase1/open_data/global_authority/nheri/damped_frame_catalog.json")
    p.add_argument("--topology-gate", default="implementation/phase1/opensees_topology_report.json")
    p.add_argument("--partitioned-scaleout", default="implementation/phase1/partitioned_scaleout_report.json")
    p.add_argument("--sync-stress", default="implementation/phase1/sync_stress_gate_report.json")
    p.add_argument("--noise-convergence", default="implementation/phase1/noise_convergence_gate_report.json")
    p.add_argument("--wind-benchmark-report", default="implementation/phase1/wind_time_history_gate_report.json")
    p.add_argument("--ssi-boundary-report", default="implementation/phase1/ssi_boundary_gate_report.json")
    p.add_argument("--damper-validation-report", default="implementation/phase1/damper_validation_gate_report.json")
    p.add_argument("--kds-compliance-summary", default="implementation/phase1/release/kds_compliance/kds_compliance_summary.json")
    p.add_argument("--construction-sequence-report", default="implementation/phase1/construction_sequence_gate_report.json")
    p.add_argument("--flexible-diaphragm-report", default="implementation/phase1/flexible_diaphragm_gate_report.json")
    p.add_argument("--repro-version-lock-report", default="implementation/phase1/reproducibility_version_lock_report.json")
    p.add_argument("--release-registry-report", default="implementation/phase1/release/release_registry.json")
    p.add_argument("--release-registry-public-key", default="implementation/phase1/release/signing/release_registry_ed25519.pub.pem")
    p.add_argument("--release-registry-signature", default="implementation/phase1/release/signing/release_registry.signature.b64")
    p.add_argument("--performance-profiling-report", default="implementation/phase1/performance_profiling_gate_report.json")
    p.add_argument("--solver-hip-e2e-report", default="implementation/phase1/solver_hip_e2e_contract_report.json")
    p.add_argument("--solver-truthfulness-report", default="implementation/phase1/solver_truthfulness_gate_report.json")
    p.add_argument(
        "--hardest-external-10case-kickoff-report",
        default="implementation/phase1/hardest_external_10case_kickoff_gate_report.json",
    )
    p.add_argument("--rc-benchmark-lock-report", default="implementation/phase1/rc_benchmark_lock_report.json")
    p.add_argument("--rc-benchmark-cases", default="implementation/phase1/open_data/rc/rc_benchmark_lock_cases.json")
    p.add_argument("--rc-authority-catalog", default="implementation/phase1/open_data/global_authority/authority_source_catalog.json")
    p.add_argument("--version-lock-manifest", default="implementation/phase1/release/version_lock_manifest.json")
    p.add_argument("--scaleout-io", default="implementation/phase1/scaleout_io_profile_report.json")
    p.add_argument("--nightly-10m-repro", default="implementation/phase1/nightly_10m_repro_report.json")
    p.add_argument("--ndtha-long-profile", default="implementation/phase1/ndtha_long_profile_report.json")
    p.add_argument("--global-authority-report", default="implementation/phase1/global_authority_gate_report.json")
    p.add_argument("--ci-report", default="implementation/phase1/ci_gate_report.json")
    p.add_argument("--enable-design-opt-cost-smoke", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--strict-design-opt-cost-smoke", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument(
        "--design-opt-cost-smoke-report",
        default="implementation/phase1/release/design_optimization/design_optimization_cost_reduction_smoke_report.json",
    )
    p.add_argument(
        "--design-opt-cost-smoke-history",
        default="implementation/phase1/release/design_optimization/design_optimization_cost_reduction_smoke_history.json",
    )
    p.add_argument("--design-opt-cost-smoke-history-limit", type=int, default=10)
    p.add_argument("--design-opt-cost-smoke-objective-profile", default="balanced_practice")
    p.add_argument("--design-opt-cost-smoke-ndtha-step-count", type=int, default=24)
    p.add_argument("--static-validation", default="implementation/phase1/static_artifact_validation_report.json")
    p.add_argument("--freeze-report", default="implementation/phase1/release/freeze_release_report.json")
    p.add_argument("--promotion-report", default="implementation/phase1/release/release_candidate_promotion_report.json")
    p.add_argument(
        "--committee-package-report",
        default="implementation/phase1/release/committee_review/committee_review_package_report.json",
    )
    p.add_argument("--committee-summary-report", default="implementation/phase1/release/committee_review/committee_summary.json")
    p.add_argument(
        "--pbd-review-package-report",
        default="implementation/phase1/release/pbd_review/pbd_review_package_report.json",
    )
    p.add_argument(
        "--structural-optimization-viewer-dir",
        default="implementation/phase1/release/visualization",
    )
    p.add_argument(
        "--code-check-report",
        default="implementation/phase1/release/kds_compliance/code_check_report.json",
    )
    p.add_argument(
        "--design-opt-dataset-npz",
        default="implementation/phase1/release/design_optimization/design_optimization_dataset.npz",
    )
    p.add_argument(
        "--design-opt-dataset-report",
        default="implementation/phase1/release/design_optimization/design_optimization_dataset_report.json",
    )
    p.add_argument(
        "--design-opt-cost-reduction-changes",
        default="implementation/phase1/release/design_optimization/design_optimization_cost_reduction_changes.json",
    )
    p.add_argument(
        "--design-opt-rebar-payload-projection-json",
        default="implementation/phase1/open_data/midas/midas_generator_33.rebar_payload_projection.json",
    )
    p.add_argument(
        "--design-opt-connection-detailing-payload-projection-json",
        default="implementation/phase1/open_data/midas/midas_generator_33.connection_detailing_payload_projection.json",
    )
    p.add_argument(
        "--design-opt-detailing-payload-projection-json",
        default="implementation/phase1/open_data/midas/midas_generator_33.detailing_payload_projection.json",
    )
    p.add_argument(
        "--mgt-export-output-mgt",
        default="implementation/phase1/open_data/midas/midas_generator_33.optimized.mgt",
    )
    p.add_argument(
        "--mgt-export-report",
        default="implementation/phase1/open_data/midas/midas_generator_33.optimized.export_report.json",
    )
    p.add_argument(
        "--mgt-export-patch-manifest",
        default="implementation/phase1/open_data/midas/midas_generator_33.optimized.patch_manifest.json",
    )
    p.add_argument(
        "--mgt-export-instruction-sidecar",
        default="implementation/phase1/open_data/midas/midas_generator_33.optimized.instruction_sidecar.json",
    )
    p.add_argument(
        "--mgt-export-audit-review-manifest",
        default="implementation/phase1/open_data/midas/midas_generator_33.optimized.audit_review_manifest.json",
    )
    p.add_argument(
        "--mgt-export-audit-review-packet-manifest",
        default="implementation/phase1/open_data/midas/midas_generator_33.optimized.audit_review_packets.json",
    )
    p.add_argument(
        "--mgt-export-audit-review-packet-directory",
        default="implementation/phase1/open_data/midas/midas_generator_33.optimized.audit_review_packet_files",
    )
    p.add_argument(
        "--mgt-export-audit-review-queue-manifest",
        default="implementation/phase1/open_data/midas/midas_generator_33.optimized.audit_review_queue.json",
    )
    p.add_argument(
        "--mgt-export-audit-review-queue-status-directory",
        default="implementation/phase1/open_data/midas/midas_generator_33.optimized.audit_review_queue_status_files",
    )
    p.add_argument(
        "--mgt-export-audit-review-followup-manifest",
        default="implementation/phase1/open_data/midas/midas_generator_33.optimized.audit_review_followup_manifest.json",
    )
    p.add_argument("--panel-zone-clash-artifact", default="")
    p.add_argument("--panel-zone-solver-verified-export-bundle", default="")
    p.add_argument("--panel-zone-solver-export-bundle", default="")
    p.add_argument("--panel-zone-solver-verified-drop-dir", default=str(DEFAULT_PANEL_ZONE_INBOX))
    p.add_argument("--panel-zone-solver-verified-source-origin-class", default="")
    p.add_argument("--panel-zone-solver-verified-joint-geometry-source", default="")
    p.add_argument("--panel-zone-solver-verified-rebar-anchorage-source", default="")
    p.add_argument("--panel-zone-solver-verified-clash-verification-source", default="")
    p.add_argument("--panel-zone-joint-geometry-artifact", default="")
    p.add_argument("--panel-zone-rebar-anchorage-artifact", default="")
    p.add_argument("--panel-zone-clash-verification-artifact", default="")
    p.add_argument("--panel-zone-joint-geometry-source-output", default="implementation/phase1/panel_zone_joint_geometry_3d.json")
    p.add_argument("--panel-zone-rebar-anchorage-source-output", default="implementation/phase1/panel_zone_rebar_anchorage_3d.json")
    p.add_argument("--panel-zone-clash-verification-source-output", default="implementation/phase1/panel_zone_clash_verification_3d.json")
    p.add_argument(
        "--panel-zone-joint-geometry-contract",
        default="implementation/phase1/panel_zone_joint_geometry_3d_contract.json",
    )
    p.add_argument(
        "--panel-zone-rebar-anchorage-contract",
        default="implementation/phase1/panel_zone_rebar_anchorage_3d_contract.json",
    )
    p.add_argument(
        "--panel-zone-clash-verification-contract",
        default="implementation/phase1/panel_zone_clash_verification_3d_contract.json",
    )
    p.add_argument("--foundation-optimization-artifact", default="")
    p.add_argument("--wind-raw-input", default="implementation/phase1/open_data/wind/across_wind_10h_dt1s.csv")
    p.add_argument("--wind-raw-manifest", default="implementation/phase1/open_data/wind/across_wind_10h_dt1s.manifest.json")
    p.add_argument("--wind-benchmark-asset-registry", default="implementation/phase1/open_data/wind/wind_benchmark_asset_registry.json")
    p.add_argument("--wind-gate-report", default="implementation/phase1/wind_time_history_gate_report.json")
    p.add_argument("--wind-raw-mapping-artifact", default="")
    p.add_argument("--tpu-hffb-benchmark-report", default="implementation/phase1/open_data/wind/tpu_hffb_benchmark_gate_report.json")
    p.add_argument("--peer-spd-column-seed-manifest", default="implementation/phase1/open_data/pbd_hinge/peer_spd_column_seed_manifest.json")
    p.add_argument("--peer-spd-column-materialize-report", default="implementation/phase1/open_data/pbd_hinge/peer_spd_column_materialize_report.json")
    p.add_argument("--pbd-hinge-benchmark-asset-registry", default="implementation/phase1/open_data/pbd_hinge/pbd_hinge_benchmark_asset_registry.json")
    p.add_argument("--peer-spd-hinge-benchmark-report", default="implementation/phase1/open_data/pbd_hinge/peer_spd_hinge_benchmark_gate_report.json")
    p.add_argument(
        "--peer-spd-hinge-fixture-regression-report",
        default="implementation/phase1/open_data/pbd_hinge/peer_spd_hinge_fixture_regression_report.json",
    )
    p.add_argument(
        "--peer-spd-hinge-alignment-report",
        default="implementation/phase1/open_data/pbd_hinge/peer_spd_hinge_refresh_alignment_report.json",
    )
    p.add_argument(
        "--external-benchmark-submission-readiness-report",
        default="implementation/phase1/release/external_benchmark_submission_readiness.json",
    )
    p.add_argument(
        "--external-benchmark-kickoff-dir",
        default="implementation/phase1/release/external_benchmark_kickoff",
    )
    p.add_argument(
        "--external-benchmark-kickoff-package-report",
        default="implementation/phase1/release/external_benchmark_kickoff/external_benchmark_kickoff_package.json",
    )
    p.add_argument(
        "--external-benchmark-execution-manifest-report",
        default="implementation/phase1/release/external_benchmark_kickoff/external_benchmark_execution_manifest.json",
    )
    p.add_argument(
        "--external-benchmark-execution-updates-json",
        default="implementation/phase1/release/external_benchmark_kickoff/external_benchmark_execution_updates.json",
    )
    p.add_argument(
        "--external-benchmark-execution-status-manifest-report",
        default="implementation/phase1/release/external_benchmark_kickoff/external_benchmark_execution_status_manifest.json",
    )
    p.add_argument(
        "--audit-review-decision-batch-template-json",
        default="implementation/phase1/release/external_benchmark_kickoff/audit_review_decision_batch_template.json",
    )
    p.add_argument(
        "--audit-review-decision-batch-preview-artifacts-report",
        default="implementation/phase1/release/external_benchmark_kickoff/audit_review_decision_batch_preview_artifacts_report.json",
    )
    p.add_argument("--quality-mgt-corpus-report", default="implementation/phase1/open_data/midas/quality_corpus_report.json")
    p.add_argument("--pbd-hinge-refresh-source-input", default="")
    p.add_argument("--pbd-hinge-refresh-source-output", default="implementation/phase1/pbd_hinge_refresh_source.json")
    p.add_argument("--pbd-hinge-refresh-artifact", default="")
    p.add_argument("--pbd-hinge-refresh-report", default="implementation/phase1/pbd_hinge_refresh_report.json")
    p.add_argument("--panel-zone-clash-report", default="implementation/phase1/panel_zone_clash_report.json")
    p.add_argument(
        "--panel-zone-solver-verified-inbox-status-report",
        default="implementation/phase1/panel_zone_solver_verified_inbox_status.json",
    )
    p.add_argument(
        "--foundation-optimization-report",
        default="implementation/phase1/release/design_optimization/foundation_optimization_report.json",
    )
    p.add_argument("--wind-raw-mapping-report", default="implementation/phase1/wind_tunnel_raw_mapping_report.json")
    p.add_argument("--release-gap-report", default="implementation/phase1/release/release_gap_report.json")
    p.add_argument("--release-gap-markdown", default="implementation/phase1/release/release_gap_report.md")
    p.add_argument("--release-gap-smoke-history-png", default="implementation/phase1/release/release_gap_smoke_history.png")
    p.add_argument(
        "--release-gap-measured-chain-category-png",
        default="implementation/phase1/release/release_gap_measured_chain_categories.png",
    )
    p.add_argument("--release-gap-history-root", default="implementation/phase1/experiments/by_test/nightly_release_gate")
    p.add_argument("--release-gap-history-limit", type=int, default=14)
    p.add_argument("--out", default="implementation/phase1/release/nightly_release_gate_report.json")
    args = p.parse_args()
    if not str(args.panel_zone_clash_artifact).strip():
        args.panel_zone_clash_artifact = "implementation/phase1/panel_zone_clash_artifact.json"
    discovered_panel_zone_inputs: dict[str, str] = {}
    if str(args.panel_zone_solver_verified_export_bundle).strip() and not str(args.panel_zone_solver_export_bundle).strip():
        args.panel_zone_solver_export_bundle = str(args.panel_zone_solver_verified_export_bundle).strip()
    explicit_panel_zone_solver_export_bundle = str(args.panel_zone_solver_export_bundle).strip()
    explicit_solver_verified_joint_geometry_source = str(args.panel_zone_solver_verified_joint_geometry_source).strip()
    explicit_solver_verified_rebar_anchorage_source = str(args.panel_zone_solver_verified_rebar_anchorage_source).strip()
    explicit_solver_verified_clash_verification_source = str(args.panel_zone_solver_verified_clash_verification_source).strip()
    if str(args.panel_zone_solver_verified_drop_dir).strip():
        panel_zone_solver_verified_drop_dir = Path(str(args.panel_zone_solver_verified_drop_dir).strip())
        discovered_panel_zone_inputs = _discover_from_drop_dir(panel_zone_solver_verified_drop_dir)
        if not str(args.panel_zone_solver_verified_source_origin_class).strip():
            args.panel_zone_solver_verified_source_origin_class = _drop_dir_source_origin_class(
                panel_zone_solver_verified_drop_dir
            )
        discovered_bundle = str(discovered_panel_zone_inputs.get("bundle", "") or "").strip()
        discovered_joint = str(discovered_panel_zone_inputs.get("joint", "") or "").strip()
        discovered_anchorage = str(discovered_panel_zone_inputs.get("anchorage", "") or "").strip()
        discovered_clash = str(discovered_panel_zone_inputs.get("clash", "") or "").strip()
        if (
            not explicit_panel_zone_solver_export_bundle
            and not explicit_solver_verified_joint_geometry_source
            and not explicit_solver_verified_rebar_anchorage_source
            and not explicit_solver_verified_clash_verification_source
            and discovered_bundle
        ):
            args.panel_zone_solver_export_bundle = discovered_bundle
        else:
            if not explicit_solver_verified_joint_geometry_source and discovered_joint:
                args.panel_zone_solver_verified_joint_geometry_source = discovered_joint
            if not explicit_solver_verified_rebar_anchorage_source and discovered_anchorage:
                args.panel_zone_solver_verified_rebar_anchorage_source = discovered_anchorage
            if not explicit_solver_verified_clash_verification_source and discovered_clash:
                args.panel_zone_solver_verified_clash_verification_source = discovered_clash
    args.panel_zone_solver_verified_drop_dir_discovered_bundle = str(discovered_panel_zone_inputs.get("bundle", "") or "")
    args.panel_zone_solver_verified_drop_dir_discovered_joint_geometry_source = str(discovered_panel_zone_inputs.get("joint", "") or "")
    args.panel_zone_solver_verified_drop_dir_discovered_rebar_anchorage_source = str(discovered_panel_zone_inputs.get("anchorage", "") or "")
    args.panel_zone_solver_verified_drop_dir_discovered_clash_verification_source = str(discovered_panel_zone_inputs.get("clash", "") or "")
    args.panel_zone_solver_verified_drop_dir_discovered_source_origin_class = str(
        args.panel_zone_solver_verified_source_origin_class or ""
    )
    explicit_panel_zone_solver_export_bundle = str(args.panel_zone_solver_export_bundle).strip()
    explicit_solver_verified_joint_geometry_source = str(args.panel_zone_solver_verified_joint_geometry_source).strip()
    explicit_solver_verified_rebar_anchorage_source = str(args.panel_zone_solver_verified_rebar_anchorage_source).strip()
    explicit_solver_verified_clash_verification_source = str(args.panel_zone_solver_verified_clash_verification_source).strip()
    need_autogen_panel_zone_solver_verified_export_bundle = bool(
        True
        and not str(args.panel_zone_joint_geometry_artifact).strip()
        and not str(args.panel_zone_rebar_anchorage_artifact).strip()
        and not str(args.panel_zone_clash_verification_artifact).strip()
        and explicit_solver_verified_joint_geometry_source
        and explicit_solver_verified_rebar_anchorage_source
        and explicit_solver_verified_clash_verification_source
    )
    if need_autogen_panel_zone_solver_verified_export_bundle:
        if not str(args.panel_zone_solver_export_bundle).strip():
            args.panel_zone_solver_export_bundle = "implementation/phase1/panel_zone_solver_verified_export_bundle.json"
    need_autogen_panel_zone_solver_export_bundle = (
        not explicit_panel_zone_solver_export_bundle
        and (
            not str(args.panel_zone_joint_geometry_artifact).strip()
            or not str(args.panel_zone_rebar_anchorage_artifact).strip()
            or not str(args.panel_zone_clash_verification_artifact).strip()
        )
    )
    if need_autogen_panel_zone_solver_verified_export_bundle:
        need_autogen_panel_zone_solver_export_bundle = False
    if need_autogen_panel_zone_solver_export_bundle:
        args.panel_zone_solver_export_bundle = "implementation/phase1/panel_zone_solver_export_bundle.json"
    panel_zone_solver_export_bundle = str(args.panel_zone_solver_export_bundle).strip()
    if panel_zone_solver_export_bundle:
        if not str(args.panel_zone_joint_geometry_artifact).strip():
            args.panel_zone_joint_geometry_artifact = panel_zone_solver_export_bundle
        if not str(args.panel_zone_rebar_anchorage_artifact).strip():
            args.panel_zone_rebar_anchorage_artifact = panel_zone_solver_export_bundle
        if not str(args.panel_zone_clash_verification_artifact).strip():
            args.panel_zone_clash_verification_artifact = panel_zone_solver_export_bundle
    if not str(args.panel_zone_joint_geometry_contract).strip():
        args.panel_zone_joint_geometry_contract = "implementation/phase1/panel_zone_joint_geometry_3d_contract.json"
    if not str(args.panel_zone_rebar_anchorage_contract).strip():
        args.panel_zone_rebar_anchorage_contract = "implementation/phase1/panel_zone_rebar_anchorage_3d_contract.json"
    if not str(args.panel_zone_clash_verification_contract).strip():
        args.panel_zone_clash_verification_contract = "implementation/phase1/panel_zone_clash_verification_3d_contract.json"
    if not str(args.panel_zone_joint_geometry_artifact).strip():
        args.panel_zone_joint_geometry_artifact = str(args.panel_zone_joint_geometry_contract)
    if not str(args.panel_zone_rebar_anchorage_artifact).strip():
        args.panel_zone_rebar_anchorage_artifact = str(args.panel_zone_rebar_anchorage_contract)
    if not str(args.panel_zone_clash_verification_artifact).strip():
        args.panel_zone_clash_verification_artifact = str(args.panel_zone_clash_verification_contract)
    if not str(args.foundation_optimization_artifact).strip():
        args.foundation_optimization_artifact = "implementation/phase1/release/design_optimization/foundation_optimization_artifact.json"
    if not str(args.wind_raw_mapping_artifact).strip():
        args.wind_raw_mapping_artifact = "implementation/phase1/wind_tunnel_raw_mapping.json"
    if not str(args.pbd_hinge_refresh_source_output).strip():
        args.pbd_hinge_refresh_source_output = "implementation/phase1/pbd_hinge_refresh_source.json"
    explicit_pbd_hinge_refresh_source_input = str(args.pbd_hinge_refresh_source_input).strip()
    need_autogen_pbd_hinge_refresh_source = not explicit_pbd_hinge_refresh_source_input
    if need_autogen_pbd_hinge_refresh_source:
        args.pbd_hinge_refresh_source_input = str(args.pbd_hinge_refresh_source_output)
    if not str(args.pbd_hinge_refresh_artifact).strip():
        args.pbd_hinge_refresh_artifact = "implementation/phase1/pbd_hinge_refresh_artifact.json"
    RUN_ENV_OVERRIDES = {}
    REUSE_EXISTING_IF_PRESENT = bool(args.reuse_existing_if_present)
    if bool(args.gpu_strict) and not bool(args.allow_cpu_required):
        RUN_ENV_OVERRIDES["PHASE1_DISABLE_CPU_FALLBACK"] = "1"
        RUN_ENV_OVERRIDES["PHASE1_GPU_PREPROCESS"] = "1"
        RUN_ENV_OVERRIDES["PHASE1_GPU_PREPROCESS_STRICT"] = "1"
    global DRY_RUN
    DRY_RUN = bool(args.dry_run)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    steps: list[dict] = []
    reason_code = "PASS"

    cmd_hip_smoke = [
        sys.executable,
        "implementation/phase1/run_hip_kernel_smoke.py",
        "--hipcc",
        str(args.hipcc),
        "--rocm-path",
        str(args.rocm_path),
        "--strict",
        "--out",
        str(args.hip_kernel_smoke_report),
    ]
    if str(args.rocm_device_lib_path).strip():
        cmd_hip_smoke.extend(["--rocm-device-lib-path", str(args.rocm_device_lib_path)])
    if bool(args.enable_hip_kernel_smoke):
        if reason_code == "PASS" and not _run_reusable("hip_kernel_smoke_gate", cmd_hip_smoke, args.hip_kernel_smoke_report, steps):
            reason_code = "ERR_HIP_KERNEL_SMOKE"

    cmd_csv = [
        sys.executable,
        "implementation/phase1/run_commercial_csv_gate.py",
        "--out",
        str(args.commercial_csv_gate),
    ]
    if reason_code == "PASS" and not _run_reusable("commercial_csv_gate", cmd_csv, args.commercial_csv_gate, steps):
        reason_code = "ERR_COMMERCIAL_CSV_GATE"

    cmd_mgt = [
        sys.executable,
        "implementation/phase1/parse_midas_mgt_to_json_npz.py",
        "--mgt",
        str(args.mgt_input),
        "--json-out",
        str(args.mgt_json_out),
        "--npz-out",
        str(args.mgt_npz_out),
        "--edge-list-out",
        str(args.mgt_edge_list_out),
        "--report-out",
        str(args.mgt_conversion_report),
        "--forbid-synthetic-source",
    ]
    if bool(args.mgt_require_shell_beam_mix):
        cmd_mgt.append("--require-shell-beam-mix")
    else:
        cmd_mgt.append("--no-require-shell-beam-mix")
    if reason_code == "PASS" and not _run_reusable("midas_mgt_conversion_gate", cmd_mgt, args.mgt_conversion_report, steps):
        reason_code = "ERR_MIDAS_MGT_CONVERSION"

    cmd_midas_kds_bridge_backfill = [
        sys.executable,
        "implementation/phase1/backfill_midas_kds_geometry_bridge_metadata.py",
        "--write",
        str(args.mgt_json_out),
        str(Path("implementation/phase1/open_data/midas/midas_generator_33.pr_recheck.json")),
        str(Path("implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json")),
    ]
    if reason_code == "PASS" and not _run("midas_kds_geometry_bridge_backfill", cmd_midas_kds_bridge_backfill, steps):
        reason_code = "ERR_MIDAS_KDS_GEOMETRY_BRIDGE_BACKFILL"

    cmd_real_source_multi = [
        sys.executable,
        "implementation/phase1/run_real_source_multi_gate.py",
        "--cases",
        str(args.commercial_readiness_model_cases),
        "--out",
        str(args.real_source_multi_report),
        "--forbid-toy-markers",
    ]
    if reason_code == "PASS" and not _run_reusable("real_source_multi_gate", cmd_real_source_multi, args.real_source_multi_report, steps):
        reason_code = "ERR_REAL_SOURCE_MULTI_GATE"

    cmd_nonlinear = [
        sys.executable,
        "implementation/phase1/run_nonlinear_frame_engine_validation.py",
        "--cases",
        str(args.nonlinear_cases),
        "--target-split",
        str(args.nonlinear_target_split),
        "--min-case-count",
        "3",
        "--max-case-count",
        "6",
        "--require-top-disp-hf",
        "--out",
        str(args.nonlinear_engine_report),
    ]
    if reason_code == "PASS" and not _run_reusable("nonlinear_engine_gate", cmd_nonlinear, args.nonlinear_engine_report, steps):
        reason_code = "ERR_NONLINEAR_ENGINE_GATE"

    cmd_pushover = [
        sys.executable,
        "implementation/phase1/run_nonlinear_pushover_stress.py",
        "--cases",
        str(args.pushover_cases),
        "--target-split",
        str(args.pushover_target_split),
        "--min-case-count",
        "3",
        "--max-case-count",
        "6",
        "--load-factors",
        "1.0,1.2,1.4,1.6,1.8,2.0",
        "--yield-drift-scale",
        "0.45",
        "--hardening-ratio",
        "0.2",
        "--pdelta-factor",
        "0.6",
        "--max-iter",
        "300",
        "--tolerance",
        "1e-6",
        "--min-plastic-story-count",
        "1",
        "--min-drift-amplification",
        "1.8",
        "--out",
        str(args.pushover_stress_report),
    ]
    if reason_code == "PASS" and not _run_reusable("pushover_stress_gate", cmd_pushover, args.pushover_stress_report, steps):
        reason_code = "ERR_PUSHOVER_STRESS_GATE"

    cmd_ndtha = [
        sys.executable,
        "implementation/phase1/run_nonlinear_ndtha_stress.py",
        "--cases",
        str(args.ndtha_cases),
        "--target-split",
        str(args.ndtha_target_split),
        "--ground-motion-csv",
        str(args.ndtha_ground_motion_csv),
        "--min-case-count",
        "3",
        "--max-case-count",
        "6",
        "--ag-scale",
        "2.0",
        "--yield-drift-scale",
        "0.45",
        "--hardening-ratio",
        "0.2",
        "--pdelta-factor",
        "1.0",
        "--max-step-iterations",
        "16",
        "--step-tol",
        "1e-4",
        "--adaptive-load-decay",
        "0.82",
        "--damping-force-cap-ratio",
        "0.6",
        "--max-steps",
        "2400",
        "--min-load-reversals",
        "20",
        "--min-plastic-story-count",
        "1",
        "--collapse-drift-threshold-pct",
        "10.0",
        "--rayleigh-alpha",
        "0.03",
        "--rayleigh-beta",
        "1e-6",
        "--out",
        str(args.ndtha_stress_report),
    ]
    if reason_code == "PASS" and not _run_reusable("ndtha_stress_gate", cmd_ndtha, args.ndtha_stress_report, steps):
        reason_code = "ERR_NDTHA_STRESS_GATE"

    cmd_ndtha_residual = [
        sys.executable,
        "implementation/phase1/run_ndtha_residual_gate.py",
        "--ndtha-stress",
        str(args.ndtha_stress_report),
        "--max-residual-top-displacement-m",
        "5.0",
        "--max-residual-drift-ratio-pct",
        "10.0",
        "--recommended-residual-top-displacement-m",
        "1.0",
        "--recommended-residual-drift-ratio-pct",
        "2.0",
        "--max-fallback-rate",
        "1.0",
        "--out",
        str(args.ndtha_residual_report),
    ]
    if reason_code == "PASS" and not _run_reusable("ndtha_residual_gate", cmd_ndtha_residual, args.ndtha_residual_report, steps):
        reason_code = "ERR_NDTHA_RESIDUAL_GATE"

    cmd_wind = [
        sys.executable,
        "implementation/phase1/run_wind_time_history_gate.py",
        "--cases",
        str(args.ndtha_cases),
        "--target-split",
        "all",
        "--wind-csv",
        str(args.wind_csv),
        "--source-manifest",
        str(args.wind_source_manifest),
        "--min-duration-hours",
        "10",
        "--analysis-stride",
        "1",
        "--max-chunk-steps",
        "2048",
        "--max-case-count",
        "4",
        "--out",
        str(args.wind_benchmark_report),
    ]
    if reason_code == "PASS" and not _run_reusable(
        "wind_benchmark_gate",
        cmd_wind,
        args.wind_benchmark_report,
        steps,
        check_dependency_mtime=False,
        reuse_note="reused heavy wind benchmark artifact with matching command inputs",
    ):
        reason_code = "ERR_WIND_BENCHMARK_GATE"

    cmd_ssi = [
        sys.executable,
        "implementation/phase1/run_ssi_boundary_gate.py",
        "--cases",
        str(args.ndtha_cases),
        "--target-split",
        "all",
        "--ground-motion-csv",
        str(args.ndtha_ground_motion_csv),
        "--max-case-count",
        "4",
        "--out",
        str(args.ssi_boundary_report),
    ]
    if reason_code == "PASS" and not _run_reusable(
        "ssi_boundary_gate",
        cmd_ssi,
        args.ssi_boundary_report,
        steps,
        check_dependency_mtime=False,
        reuse_note="reused heavy SSI boundary artifact with matching command inputs",
    ):
        reason_code = "ERR_SSI_BOUNDARY_GATE"

    cmd_damper = [
        sys.executable,
        "implementation/phase1/run_damper_validation_gate.py",
        "--catalog",
        str(args.damper_catalog),
        "--out",
        str(args.damper_validation_report),
    ]
    if reason_code == "PASS" and not _run_reusable("damper_validation_gate", cmd_damper, args.damper_validation_report, steps):
        reason_code = "ERR_DAMPER_VALIDATION_GATE"

    cmd_kds = [
        sys.executable,
        "implementation/phase1/generate_kds_compliance_report.py",
        "--pbd-review-package",
        "implementation/phase1/release/pbd_review/pbd_review_package_report.json",
        "--pbd-compliance-slice-report",
        "implementation/phase1/release/pbd_review/pbd_review_compliance_slice_report.json",
        "--commercial-csv-gate",
        str(args.commercial_csv_gate),
        "--member-force-gate",
        "implementation/phase1/member_force_soft_accept_report.json",
        "--out-dir",
        str(Path(args.kds_compliance_summary).parent),
    ]
    if reason_code == "PASS" and not _run_reusable("kds_compliance_gate", cmd_kds, args.kds_compliance_summary, steps):
        reason_code = "ERR_KDS_COMPLIANCE_GATE"

    cmd_construction = [
        sys.executable,
        "implementation/phase1/run_construction_sequence_gate.py",
        "--cases",
        str(args.ndtha_cases),
        "--target-split",
        "all",
        "--min-case-count",
        "2",
        "--max-case-count",
        "4",
        "--stage-count",
        "24",
        "--construction-years",
        "4.0",
        "--out",
        str(args.construction_sequence_report),
    ]
    if reason_code == "PASS" and not _run_reusable(
        "construction_sequence_gate", cmd_construction, args.construction_sequence_report, steps
    ):
        reason_code = "ERR_CONSTRUCTION_SEQUENCE_GATE"

    cmd_diaphragm = [
        sys.executable,
        "implementation/phase1/run_flexible_diaphragm_gate.py",
        "--cases",
        str(args.ndtha_cases),
        "--opensees-model",
        str(args.opensees_model),
        "--target-split",
        "all",
        "--min-case-count",
        "2",
        "--max-case-count",
        "4",
        "--out",
        str(args.flexible_diaphragm_report),
    ]
    if bool(args.require_shell_beam_mix):
        cmd_diaphragm.append("--require-shell-beam-mix")
    else:
        cmd_diaphragm.append("--no-require-shell-beam-mix")
    if reason_code == "PASS" and not _run_reusable(
        "flexible_diaphragm_gate", cmd_diaphragm, args.flexible_diaphragm_report, steps
    ):
        reason_code = "ERR_FLEXIBLE_DIAPHRAGM_GATE"

    cmd_repro_lock = [
        sys.executable,
        "implementation/phase1/run_reproducibility_version_lock_gate.py",
        "--cases",
        str(args.ndtha_cases),
        "--target-split",
        "all",
        "--min-case-count",
        "2",
        "--max-case-count",
        "4",
        "--seed",
        "23",
        "--replay-runs",
        "3",
        "--model-artifacts",
        "implementation/phase1/winning_ticket_backprop_report.json,implementation/phase1/nonlinear_frame_engine_report.json",
        "--lock-manifest-out",
        str(args.version_lock_manifest),
        "--out",
        str(args.repro_version_lock_report),
    ]
    if reason_code == "PASS" and not _run_reusable(
        "reproducibility_version_lock_gate", cmd_repro_lock, args.repro_version_lock_report, steps
    ):
        reason_code = "ERR_REPRO_VERSION_LOCK_GATE"

    cmd_solver_hip = [
        sys.executable,
        "implementation/phase1/run_solver_hip_e2e_contract.py",
        "--strict-probe",
        "implementation/phase1/zero_copy_real_probe_report_strict.json",
        "--out",
        str(args.solver_hip_e2e_report),
    ]
    _run_reusable("solver_hip_e2e_contract", cmd_solver_hip, args.solver_hip_e2e_report, steps)

    cmd_solver_truthfulness = [
        sys.executable,
        "implementation/phase1/run_solver_truthfulness_gate.py",
        "--winning-ticket-backprop-report",
        "implementation/phase1/winning_ticket_backprop_report.json",
        "--physics-branching-report",
        "implementation/phase1/physics_branching_report.json",
        "--track-dynamics-dataset-report",
        "implementation/phase1/track_dynamics_dataset_report.json",
        "--tunnel-dynamics-dataset-report",
        "implementation/phase1/tunnel_dynamics_dataset_report.json",
        "--solver-hip-report",
        str(args.solver_hip_e2e_report),
        "--out",
        str(args.solver_truthfulness_report),
    ]
    _run_reusable("solver_truthfulness_gate", cmd_solver_truthfulness, args.solver_truthfulness_report, steps)

    cmd_performance_profiling = [
        sys.executable,
        "implementation/phase1/run_performance_profiling_gate.py",
        "--p0-engine-perf-report",
        "implementation/phase1/p0_engine_perf_report.json",
        "--gpu-bottleneck-audit-report",
        "implementation/phase1/gpu_bottleneck_audit_report.json",
        "--ndtha-long-profile-report",
        str(args.ndtha_long_profile),
        "--track-lf-solver-report",
        "implementation/phase1/track_lf_solver_report.json",
        "--moving-load-integrator-report",
        "implementation/phase1/moving_load_integrator_report.json",
        "--vti-coupled-solver-report",
        "implementation/phase1/vti_coupled_solver_report.json",
        "--ssi-boundary-report",
        str(args.ssi_boundary_report),
        "--contact-readiness-report",
        str(args.contact_readiness_report),
        "--foundation-soil-link-report",
        "implementation/phase1/foundation_soil_link_gate_report.json",
        "--solver-hip-e2e-report",
        str(args.solver_hip_e2e_report),
        "--bottleneck-map-md",
        "implementation/phase1/performance_bottleneck_map.md",
        "--sprint-targets-json",
        "implementation/phase1/performance_optimization_sprint_targets.json",
        "--sprint-targets-md",
        "implementation/phase1/performance_optimization_sprint_targets.md",
        "--out",
        str(args.performance_profiling_report),
    ]
    if reason_code == "PASS" and not _run_reusable(
        "performance_profiling_gate",
        cmd_performance_profiling,
        args.performance_profiling_report,
        steps,
    ):
        reason_code = "ERR_PERFORMANCE_PROFILING_GATE"

    def _release_registry_cmd() -> list[str]:
        return [
            sys.executable,
            "implementation/phase1/generate_signed_release_registry.py",
            "--repro-report",
            str(args.repro_version_lock_report),
            "--lock-manifest",
            str(args.version_lock_manifest),
            "--kds-summary",
            str(args.kds_compliance_summary),
            "--midas-conversion",
            str(args.mgt_conversion_report),
            "--solver-hip-e2e",
            str(args.solver_hip_e2e_report),
            "--committee-package",
            str(args.committee_package_report),
            "--committee-summary",
            str(args.committee_summary_report),
            "--gap-report",
            str(args.release_gap_report),
            "--public-key-out",
            str(args.release_registry_public_key),
            "--signature-out",
            str(args.release_registry_signature),
            "--out",
            str(args.release_registry_report),
        ]

    if reason_code == "PASS" and not _run_reusable(
        "release_registry_gate_pre_gap", _release_registry_cmd(), args.release_registry_report, steps
    ):
        reason_code = "ERR_RELEASE_REGISTRY_GATE"

    cmd_rc_lock = [
        sys.executable,
        "implementation/phase1/run_rc_benchmark_lock_gate.py",
        "--cases",
        str(args.rc_benchmark_cases),
        "--authority-catalog",
        str(args.rc_authority_catalog),
        "--require-authority",
        "--out",
        str(args.rc_benchmark_lock_report),
    ]
    if reason_code == "PASS" and not _run_reusable("rc_benchmark_lock_gate", cmd_rc_lock, args.rc_benchmark_lock_report, steps):
        reason_code = "ERR_RC_BENCHMARK_LOCK_GATE"

    cmd_commercial_readiness = [
        sys.executable,
        "implementation/phase1/run_megastructure_commercial_readiness.py",
        "--model-cases",
        str(args.commercial_readiness_model_cases),
        "--target-split",
        str(args.commercial_readiness_target_split),
        "--ci-mode",
        "nightly",
        "--noise-seeds",
        "11,23,47",
        "--convergence-seeds",
        "11,23,47",
        "--noise-stiffness-levels-pct",
        str(args.noise_stiffness_levels_pct),
        "--convergence-stiffness-levels-pct",
        "10",
        "--forbid-toy-cases",
        "--min-source-families",
        "2",
        "--out",
        str(args.commercial_readiness_report),
    ]
    if bool(args.commercial_readiness_strict_benchmark_breadth):
        cmd_commercial_readiness[3] = (
            f"{args.commercial_readiness_model_cases},"
            "implementation/phase1/commercial_benchmark_cases.atwood_open.json"
        )
        cmd_commercial_readiness.extend(
            [
                "--min-source-families",
                "3",
                "--require-measured-dynamic-targets",
                "--min-measured-source-families",
                "2",
                "--min-measured-case-count",
                "6",
            ]
        )
    if bool(args.require_shell_beam_mix):
        cmd_commercial_readiness.append("--require-shell-beam-mix-cases")
    else:
        cmd_commercial_readiness.append("--no-require-shell-beam-mix-cases")
    if bool(args.gpu_strict):
        cmd_commercial_readiness.append("--require-gpu-strict")
    else:
        cmd_commercial_readiness.append("--no-require-gpu-strict")
    if reason_code == "PASS" and not _run_reusable(
        "commercial_readiness_gate", cmd_commercial_readiness, args.commercial_readiness_report, steps
    ):
        reason_code = "ERR_COMMERCIAL_READINESS"

    cmd_surface_interaction = [
        sys.executable,
        "implementation/phase1/run_surface_interaction_benchmark_gate.py",
        "--flexible-diaphragm-report",
        str(args.flexible_diaphragm_report),
        "--substructuring-interface-report",
        str(args.substructuring_interface_report),
        "--sync-stress-report",
        str(args.sync_stress),
        "--foundation-soil-link-gate-report",
        str(args.foundation_soil_link_report),
        "--ssi-boundary-report",
        str(args.ssi_boundary_report),
        "--soil-tunnel-ssi-report",
        str(args.soil_tunnel_ssi_report),
        "--structural-contact-gate-report",
        str(args.structural_contact_report),
        "--out",
        str(args.surface_interaction_benchmark_report),
    ]
    if reason_code == "PASS" and not _run_reusable(
        "surface_interaction_benchmark_gate",
        cmd_surface_interaction,
        args.surface_interaction_benchmark_report,
        steps,
    ):
        reason_code = "ERR_SURFACE_INTERACTION_BENCHMARK"

    solver_breadth_case_files = str(args.commercial_readiness_model_cases)
    if bool(args.commercial_readiness_strict_benchmark_breadth):
        solver_breadth_case_files = (
            f"{solver_breadth_case_files},"
            "implementation/phase1/commercial_benchmark_cases.atwood_open.json"
        )
    cmd_solver_breadth = [
        sys.executable,
        "implementation/phase1/run_solver_breadth_gate.py",
        "--topology-report",
        str(args.topology_gate),
        "--pushover-stress-report",
        str(args.pushover_stress_report),
        "--flexible-diaphragm-report",
        str(args.flexible_diaphragm_report),
        "--ssi-boundary-report",
        str(args.ssi_boundary_report),
        "--substructuring-interface-report",
        str(args.substructuring_interface_report),
        "--ndtha-stress-report",
        str(args.ndtha_stress_report),
        "--structural-contact-gate-report",
        str(args.structural_contact_report),
        "--general-fe-contact-benchmark-report",
        str(args.general_fe_contact_benchmark_report),
        "--surface-interaction-benchmark-report",
        str(args.surface_interaction_benchmark_report),
        "--benchmark-cases",
        solver_breadth_case_files,
        "--out",
        str(args.solver_breadth_report),
    ]
    if reason_code == "PASS" and not _run_reusable("solver_breadth_gate", cmd_solver_breadth, args.solver_breadth_report, steps):
        reason_code = "ERR_SOLVER_BREADTH_GATE"

    cmd_contact_readiness = [
        sys.executable,
        "implementation/phase1/run_contact_readiness_gate.py",
        "--out",
        str(args.contact_readiness_report),
    ]
    if reason_code == "PASS" and not _run_reusable(
        "contact_readiness_gate", cmd_contact_readiness, args.contact_readiness_report, steps
    ):
        reason_code = "ERR_CONTACT_READINESS"

    cmd_midas_interoperability = [
        sys.executable,
        "implementation/phase1/run_midas_interoperability_gate.py",
        "--out",
        str(args.midas_interoperability_report),
    ]
    if reason_code == "PASS" and not _run_reusable(
        "midas_interoperability_gate", cmd_midas_interoperability, args.midas_interoperability_report, steps
    ):
        reason_code = "ERR_MIDAS_INTEROPERABILITY"

    cmd_public_native_corpus = [
        sys.executable,
        "implementation/phase1/open_data/midas/collect_public_native_mgt_corpus.py",
        "--catalog",
        str(args.public_native_corpus_catalog),
        "--out-dir",
        str(args.public_native_corpus_dir),
        "--report-out",
        str(args.public_native_corpus_report),
    ]
    if reason_code == "PASS" and not _run_reusable(
        "public_native_corpus",
        cmd_public_native_corpus,
        args.public_native_corpus_report,
        steps,
    ):
        reason_code = "ERR_MIDAS_NATIVE_ROUNDTRIP"

    cmd_korean_source_catalog = [
        sys.executable,
        "implementation/phase1/open_data/korea/generate_korean_source_catalog.py",
        "--seed-json",
        str(args.korean_source_seed_json),
        "--out",
        str(args.korean_source_catalog),
    ]
    if reason_code == "PASS" and not _run_reusable(
        "korean_source_catalog",
        cmd_korean_source_catalog,
        args.korean_source_catalog,
        steps,
    ):
        reason_code = "ERR_KOREAN_SOURCE_INGEST"

    cmd_korean_public_structure_collection = [
        sys.executable,
        "implementation/phase1/open_data/korea/collect_korean_public_structures.py",
        "--catalog",
        str(args.korean_source_catalog),
        "--out-dir",
        str(args.korean_public_structure_out_dir),
        "--report-out",
        str(args.korean_public_structure_collection_report),
    ]
    if reason_code == "PASS" and not _run_reusable(
        "korean_public_structure_collection",
        cmd_korean_public_structure_collection,
        args.korean_public_structure_collection_report,
        steps,
    ):
        reason_code = "ERR_KOREAN_SOURCE_INGEST"

    cmd_korean_source_ingest_report = [
        sys.executable,
        "implementation/phase1/open_data/korea/generate_korean_source_ingest_report.py",
        "--catalog",
        str(args.korean_source_catalog),
        "--collection-report",
        str(args.korean_public_structure_collection_report),
        "--out",
        str(args.korean_source_ingest_report),
    ]
    if reason_code == "PASS" and not _run_reusable(
        "korean_source_ingest_report",
        cmd_korean_source_ingest_report,
        args.korean_source_ingest_report,
        steps,
    ):
        reason_code = "ERR_KOREAN_SOURCE_INGEST"

    cmd_korean_source_ingest_gate = [
        sys.executable,
        "implementation/phase1/run_korean_source_ingest_gate.py",
        "--catalog",
        str(args.korean_source_catalog),
        "--collection-report",
        str(args.korean_public_structure_collection_report),
        "--ingest-report",
        str(args.korean_source_ingest_report),
        "--out",
        str(args.korean_source_ingest_gate_report),
    ]
    if reason_code == "PASS" and not _run_reusable(
        "korean_source_ingest_gate",
        cmd_korean_source_ingest_gate,
        args.korean_source_ingest_gate_report,
        steps,
    ):
        reason_code = "ERR_KOREAN_SOURCE_INGEST"

    cmd_korean_solver_ready_reconstruction = [
        sys.executable,
        "implementation/phase1/authoring/prepare_korean_ifc_solver_ready_reconstruction.py",
        "--korean-source-catalog",
        str(args.korean_source_catalog),
        "--korean-collection-report",
        str(args.korean_public_structure_collection_report),
        "--out-dir",
        str(args.korean_solver_ready_reconstruction_out_dir),
        "--out",
        str(args.korean_solver_ready_reconstruction_report),
    ]
    if reason_code == "PASS" and not _run_reusable(
        "korean_solver_ready_reconstruction",
        cmd_korean_solver_ready_reconstruction,
        args.korean_solver_ready_reconstruction_report,
        steps,
    ):
        reason_code = "ERR_KOREAN_SOURCE_INGEST"

    cmd_midas_native_corpus_manifest = [
        sys.executable,
        "implementation/phase1/generate_midas_native_corpus_manifest.py",
        "--public-native-catalog",
        str(args.public_native_corpus_catalog),
        "--public-native-corpus-report",
        str(args.public_native_corpus_report),
        "--korean-source-catalog",
        str(args.korean_source_catalog),
        "--korean-solver-ready-reconstruction-report",
        str(args.korean_solver_ready_reconstruction_report),
        "--out",
        str(args.midas_native_corpus_manifest),
    ]
    if reason_code == "PASS" and not _run_reusable(
        "midas_native_corpus_manifest",
        cmd_midas_native_corpus_manifest,
        args.midas_native_corpus_manifest,
        steps,
    ):
        reason_code = "ERR_MIDAS_NATIVE_ROUNDTRIP"

    cmd_midas_native_writeback_diff_receipts = [
        sys.executable,
        "implementation/phase1/generate_midas_native_writeback_diff_receipts.py",
        "--corpus-manifest",
        str(args.midas_native_corpus_manifest),
        "--out",
        str(args.midas_native_writeback_diff_receipts_report),
    ]
    if reason_code == "PASS" and not _run_reusable(
        "midas_native_writeback_diff_receipts",
        cmd_midas_native_writeback_diff_receipts,
        args.midas_native_writeback_diff_receipts_report,
        steps,
    ):
        reason_code = "ERR_MIDAS_NATIVE_ROUNDTRIP"

    cmd_midas_native_roundtrip = [
        sys.executable,
        "implementation/phase1/run_midas_native_roundtrip_gate.py",
        "--corpus-manifest",
        str(args.midas_native_corpus_manifest),
        "--diff-receipts-report",
        str(args.midas_native_writeback_diff_receipts_report),
        "--out",
        str(args.midas_native_roundtrip_report),
    ]
    if reason_code == "PASS" and not _run_reusable(
        "midas_native_roundtrip_gate",
        cmd_midas_native_roundtrip,
        args.midas_native_roundtrip_report,
        steps,
    ):
        reason_code = "ERR_MIDAS_NATIVE_ROUNDTRIP"

    cmd_irregular_top5_execution_manifest = [
        sys.executable,
        "implementation/phase1/generate_irregular_top5_execution_manifest.py",
        "--catalog",
        str(args.irregular_structure_source_catalog),
        "--triage-report",
        str(args.irregular_structure_triage_report),
        "--priority-families",
        str(args.irregular_priority_families),
        "--collection-report",
        str(args.irregular_structure_collection_report),
        "--out",
        str(args.irregular_top5_execution_manifest),
    ]
    irregular_top5_execution_manifest_payload = _build_irregular_top5_execution_manifest_payload(
        catalog_path=args.irregular_structure_source_catalog,
        triage_report_path=args.irregular_structure_triage_report,
        priority_families_path=args.irregular_priority_families,
        collection_report_path=args.irregular_structure_collection_report,
        out_path=args.irregular_top5_execution_manifest,
    )
    if reason_code == "PASS" and not _append_generated_report_step(
        "irregular_top5_execution_manifest",
        cmd_irregular_top5_execution_manifest,
        args.irregular_top5_execution_manifest,
        irregular_top5_execution_manifest_payload,
        steps,
    ):
        reason_code = "ERR_IRREGULAR_TOP5_EXECUTION_MANIFEST"

    cmd_irregular_structure_collection_gate = [
        sys.executable,
        "implementation/phase1/run_irregular_structure_collection_gate.py",
        "--source-catalog",
        str(args.irregular_structure_source_catalog),
        "--triage-report",
        str(args.irregular_structure_triage_report),
        "--collection-report",
        str(args.irregular_structure_collection_report),
        "--top5-manifest",
        str(args.irregular_top5_execution_manifest),
        "--out",
        str(args.irregular_structure_collection_gate_report),
    ]
    irregular_structure_collection_gate_payload = _build_irregular_structure_collection_gate_payload(
        catalog_path=args.irregular_structure_source_catalog,
        triage_report_path=args.irregular_structure_triage_report,
        collection_report_path=args.irregular_structure_collection_report,
        top5_manifest_path=args.irregular_top5_execution_manifest,
    )
    if reason_code == "PASS" and not _append_generated_report_step(
        "irregular_structure_collection_gate",
        cmd_irregular_structure_collection_gate,
        args.irregular_structure_collection_gate_report,
        irregular_structure_collection_gate_payload,
        steps,
    ):
        reason_code = "ERR_IRREGULAR_STRUCTURE_COLLECTION_GATE"

    cmd_nonlinear_generalization = [
        sys.executable,
        "implementation/phase1/run_nonlinear_generalization_gate.py",
        "--nonlinear-engine-report",
        str(args.nonlinear_engine_report),
        "--pushover-stress-report",
        str(args.pushover_stress_report),
        "--ndtha-stress-report",
        str(args.ndtha_stress_report),
        "--foundation-soil-link-gate-report",
        str(args.foundation_soil_link_report),
        "--out",
        str(args.nonlinear_generalization_report),
    ]
    if reason_code == "PASS" and not _run_reusable(
        "nonlinear_generalization_gate",
        cmd_nonlinear_generalization,
        args.nonlinear_generalization_report,
        steps,
    ):
        reason_code = "ERR_NONLINEAR_GENERALIZATION_GATE"

    cmd_workflow_productization = [
        sys.executable,
        "implementation/phase1/run_workflow_productization_gate.py",
        "--release-registry-report",
        str(args.release_registry_report),
        "--midas-interoperability-report",
        str(args.midas_interoperability_report),
        "--midas-native-roundtrip-report",
        str(args.midas_native_roundtrip_report),
        "--row-provenance-export-report",
        "implementation/phase1/release/kds_compliance/midas_kds_row_provenance_table_report.json",
        "--viewer-json",
        str(Path(args.structural_optimization_viewer_dir) / "structural_optimization_viewer.json"),
        "--viewer-html",
        str(Path(args.structural_optimization_viewer_dir) / "structural_optimization_viewer.html"),
        "--irregular-structure-source-catalog",
        str(args.irregular_structure_source_catalog),
        "--irregular-structure-priority-families",
        str(args.irregular_priority_families),
        "--irregular-structure-triage-report",
        str(args.irregular_structure_triage_report),
        "--irregular-structure-collection-report",
        str(args.irregular_structure_collection_report),
        "--irregular-structure-gate-report",
        str(args.irregular_structure_collection_gate_report),
        "--irregular-top5-execution-manifest",
        str(args.irregular_top5_execution_manifest),
        "--out",
        str(args.workflow_productization_report),
    ]
    if reason_code == "PASS" and not _run_reusable(
        "workflow_productization_gate",
        cmd_workflow_productization,
        args.workflow_productization_report,
        steps,
    ):
        reason_code = "ERR_WORKFLOW_PRODUCTIZATION_GATE"

    cmd_phase3 = [
        sys.executable,
        "implementation/phase1/run_phase3_megastructure_pipeline.py",
        "--candidate-id",
        str(args.candidate_id),
        "--input-path",
        str(args.input_path),
        "--opensees-model",
        str(args.opensees_model),
        "--mgt-model",
        str(args.mgt_input),
        "--mgt-report-out",
        str(args.mgt_conversion_report),
        "--mgt-json-out",
        str(args.mgt_json_out),
        "--mgt-npz-out",
        str(args.mgt_npz_out),
        "--mgt-edge-list-out",
        str(args.mgt_edge_list_out),
        "--ci-mode",
        "nightly",
        "--scale-levels-nightly",
        str(args.scale_levels_nightly),
        "--partition-max-projection-ratio",
        str(float(args.partition_max_projection_ratio)),
        "--noise-seeds",
        str(args.noise_seeds),
        "--noise-stiffness-levels-pct",
        str(args.noise_stiffness_levels_pct),
        "--noise-min-seed-count",
        str(int(args.noise_min_seed_count)),
        "--summary-out",
        str(args.phase3_report),
        "--partitioned-scaleout-out",
        str(args.partitioned_scaleout),
        "--topology-report-out",
        str(args.topology_gate),
        "--sync-stress-out",
        str(args.sync_stress),
        "--noise-convergence-out",
        str(args.noise_convergence),
        "--require-real-source",
    ]
    if bool(args.download_if_missing):
        cmd_phase3.append("--download-if-missing")
    if bool(args.gpu_strict):
        cmd_phase3.append("--gpu-strict")
    else:
        cmd_phase3.append("--no-gpu-strict")
    if bool(args.allow_cpu_required):
        cmd_phase3.append("--allow-cpu-required")
    if bool(args.require_real_topology):
        cmd_phase3.append("--require-real-topology")
    else:
        cmd_phase3.append("--no-require-real-topology")
    if bool(args.require_shell_beam_mix):
        cmd_phase3.append("--require-shell-beam-mix")
    else:
        cmd_phase3.append("--no-require-shell-beam-mix")
    if bool(args.prefer_mgt_for_partition):
        cmd_phase3.append("--prefer-mgt-for-partition")
    else:
        cmd_phase3.append("--no-prefer-mgt-for-partition")
    if reason_code == "PASS" and not _run_reusable(
        "phase3_pipeline_nightly",
        cmd_phase3,
        args.phase3_report,
        steps,
        check_dependency_mtime=False,
        reuse_note="reused heavy phase3 pipeline artifact with matching command inputs",
    ):
        reason_code = "ERR_PHASE3_PIPELINE"

    cmd_scaleout = [
        sys.executable,
        "implementation/phase1/run_scaleout_io_profile.py",
        "--runtime-hook-cmd",
        str(args.runtime_hook_cmd),
        "--producer-cmd",
        str(args.producer_cmd),
        "--dof-levels",
        str(args.scale_levels_io),
        "--out",
        str(args.scaleout_io),
    ]
    if bool(args.gpu_strict):
        cmd_scaleout.append("--gpu-strict")
    if bool(args.allow_cpu_required):
        cmd_scaleout.append("--allow-cpu-required")
    if reason_code == "PASS" and not _run_reusable("scaleout_io_profile", cmd_scaleout, args.scaleout_io, steps):
        reason_code = "ERR_SCALEOUT_IO"

    cmd_repro = [
        sys.executable,
        "implementation/phase1/run_nightly_10m_repro_gate.py",
        "--runs",
        str(int(args.nightly_10m_repro_runs)),
        "--dof-levels",
        str(args.scale_levels_nightly),
        "--edge-list-json",
        "implementation/phase1/open_data/megastructure/opensees_edges.json",
        "--partition-max-projection-ratio",
        str(float(args.partition_max_projection_ratio)),
        "--out",
        str(args.nightly_10m_repro),
    ]
    if bool(args.gpu_strict):
        cmd_repro.append("--gpu-strict")
    else:
        cmd_repro.append("--no-gpu-strict")
    if bool(args.allow_cpu_required):
        cmd_repro.append("--allow-cpu-required")
    if reason_code == "PASS" and not _run_reusable(
        "nightly_10m_repro_gate",
        cmd_repro,
        args.nightly_10m_repro,
        steps,
        check_dependency_mtime=False,
        reuse_note="reused heavy nightly 10m repro artifact with matching command inputs",
    ):
        reason_code = "ERR_NIGHTLY_10M_REPRO"

    if bool(args.enable_ndtha_long_profile):
        cmd_ndtha_long = [
            sys.executable,
            "implementation/phase1/run_10m_ndtha_long_profile.py",
            "--runs",
            str(int(args.ndtha_long_profile_runs)),
            "--partitioned-scaleout",
            str(args.partitioned_scaleout),
            "--topology-report",
            str(args.topology_gate),
            "--ground-motion-csv",
            str(args.ndtha_ground_motion_csv),
            "--target-dof",
            "10000000",
            "--partitions",
            "16",
            "--halo-coupling-gain",
            "1.0",
            "--out",
            str(args.ndtha_long_profile),
        ]
        if reason_code == "PASS" and not _run_reusable(
            "ndtha_long_profile_gate",
            cmd_ndtha_long,
            args.ndtha_long_profile,
            steps,
            check_dependency_mtime=False,
            reuse_note="reused heavy NDTHA long-profile artifact with matching command inputs",
        ):
            reason_code = "ERR_NDTHA_LONG_PROFILE"

    cmd_global_authority = [
        sys.executable,
        "implementation/phase1/run_global_authority_gate.py",
        "--catalog",
        str(args.global_authority_catalog),
        "--workdir-out",
        str(args.global_authority_workdir),
        "--require-sac",
        "--require-nheri",
        "--min-sac-cases",
        "3",
        "--min-nheri-cases",
        "3",
        "--out",
        str(args.global_authority_report),
    ]
    if reason_code == "PASS" and not _run_reusable("global_authority_gate", cmd_global_authority, args.global_authority_report, steps):
        reason_code = "ERR_GLOBAL_AUTHORITY_GATE"

    cmd_hardest_external_10case_kickoff = [
        sys.executable,
        "implementation/phase1/run_hardest_external_10case_kickoff_gate.py",
        "--solver-truthfulness-report",
        str(args.solver_truthfulness_report),
        "--solver-hip-e2e-report",
        str(args.solver_hip_e2e_report),
        "--nonlinear-generalization-report",
        str(args.nonlinear_generalization_report),
        "--workflow-productization-report",
        str(args.workflow_productization_report),
        "--commercial-readiness-report",
        str(args.commercial_readiness_report),
        "--real-source-multi-report",
        str(args.real_source_multi_report),
        "--material-constitutive-report",
        str(args.material_constitutive_report),
        "--surface-interaction-benchmark-report",
        str(args.surface_interaction_benchmark_report),
        "--wind-benchmark-report",
        str(args.wind_benchmark_report),
        "--ssi-boundary-report",
        str(args.ssi_boundary_report),
        "--damper-validation-report",
        str(args.damper_validation_report),
        "--construction-sequence-report",
        str(args.construction_sequence_report),
        "--pushover-stress-report",
        str(args.pushover_stress_report),
        "--ndtha-stress-report",
        str(args.ndtha_stress_report),
        "--buckling-contract-report",
        "implementation/phase1/buckling_contract_report.json",
        "--track-lf-solver-report",
        "implementation/phase1/track_lf_solver_report.json",
        "--moving-load-integrator-report",
        "implementation/phase1/moving_load_integrator_report.json",
        "--vti-coupled-solver-report",
        "implementation/phase1/vti_coupled_solver_report.json",
        "--tunnel-dynamics-dataset-report",
        "implementation/phase1/tunnel_dynamics_dataset_report.json",
        "--foundation-soil-link-gate-report",
        "implementation/phase1/foundation_soil_link_gate_report.json",
        "--out",
        str(args.hardest_external_10case_kickoff_report),
    ]
    if reason_code == "PASS" and not _run_reusable(
        "hardest_external_10case_kickoff_gate",
        cmd_hardest_external_10case_kickoff,
        args.hardest_external_10case_kickoff_report,
        steps,
    ):
        reason_code = "ERR_HARDEST_EXTERNAL_10CASE_KICKOFF_GATE"

    cmd_ci = [
        sys.executable,
        "implementation/phase1/phase1_ci_gate.py",
        "--ci-mode",
        "nightly",
        "--strict-probe",
        "implementation/phase1/zero_copy_real_probe_report_strict.json",
        "--hip-kernel-smoke",
        str(args.hip_kernel_smoke_report),
        "--rca",
        "implementation/phase1/step_outputs/step5_rca_summary.json",
        "--phase3-pipeline",
        str(args.phase3_report),
        "--topology-gate",
        str(args.topology_gate),
        "--partitioned-scaleout",
        str(args.partitioned_scaleout),
        "--sync-stress",
        str(args.sync_stress),
        "--noise-convergence",
        str(args.noise_convergence),
        "--commercial-csv-gate",
        str(args.commercial_csv_gate),
        "--midas-mgt-conversion",
        str(args.mgt_conversion_report),
        "--scaleout-io",
        str(args.scaleout_io),
        "--nightly-10m-repro",
        str(args.nightly_10m_repro),
        "--ndtha-long-profile",
        str(args.ndtha_long_profile),
        "--commercial-readiness",
        str(args.commercial_readiness_report),
        "--solver-breadth-report",
        str(args.solver_breadth_report),
        "--contact-readiness-report",
        str(args.contact_readiness_report),
        "--general-fe-contact-benchmark-report",
        str(args.general_fe_contact_benchmark_report),
        "--surface-interaction-benchmark-report",
        str(args.surface_interaction_benchmark_report),
        "--midas-interoperability-report",
        str(args.midas_interoperability_report),
        "--korean-source-ingest-gate-report",
        str(args.korean_source_ingest_gate_report),
        "--midas-native-roundtrip-report",
        str(args.midas_native_roundtrip_report),
        "--performance-profiling-report",
        str(args.performance_profiling_report),
        "--irregular-structure-collection-gate-report",
        str(args.irregular_structure_collection_gate_report),
        "--irregular-top5-execution-manifest",
        str(args.irregular_top5_execution_manifest),
        "--nonlinear-generalization-report",
        str(args.nonlinear_generalization_report),
        "--workflow-productization-report",
        str(args.workflow_productization_report),
        "--real-source-multi",
        str(args.real_source_multi_report),
        "--nonlinear-engine-report",
        str(args.nonlinear_engine_report),
        "--pushover-stress-report",
        str(args.pushover_stress_report),
        "--ndtha-stress-report",
        str(args.ndtha_stress_report),
        "--ndtha-residual-gate-report",
        str(args.ndtha_residual_report),
        "--global-authority-gate",
        str(args.global_authority_report),
        "--wind-benchmark-report",
        str(args.wind_benchmark_report),
        "--ssi-boundary-report",
        str(args.ssi_boundary_report),
        "--damper-validation-report",
        str(args.damper_validation_report),
        "--kds-compliance-summary",
        str(args.kds_compliance_summary),
        "--construction-sequence-report",
        str(args.construction_sequence_report),
        "--flexible-diaphragm-report",
        str(args.flexible_diaphragm_report),
        "--repro-version-lock-report",
        str(args.repro_version_lock_report),
        "--release-registry-report",
        str(args.release_registry_report),
        "--solver-hip-e2e",
        str(args.solver_hip_e2e_report),
        "--solver-truthfulness",
        str(args.solver_truthfulness_report),
        "--hardest-external-10case-kickoff-report",
        str(args.hardest_external_10case_kickoff_report),
        "--rc-benchmark-lock",
        str(args.rc_benchmark_lock_report),
        "--out",
        str(args.ci_report),
        "--manifest",
        "implementation/phase1/ci_artifact_manifest.json",
        *[
            item
            for artifact_path in MIDAS_SECTION_LIBRARY_ARTIFACTS
            for item in ("--midas-section-library-artifact", artifact_path)
        ],
        *[
            item
            for artifact_path in MIDAS_SECTION_LIBRARY_ARTIFACTS
            for item in ("--midas-kds-geometry-bridge-artifact", artifact_path)
        ],
        *[
            item
            for artifact_path in MIDAS_SECTION_LIBRARY_ARTIFACTS
            for item in ("--midas-loadcomb-roundtrip-artifact", artifact_path)
        ],
    ]
    if bool(args.enable_ndtha_long_profile):
        cmd_ci.append("--require-ndtha-long-profile")
    if bool(args.enable_hip_kernel_smoke):
        cmd_ci.append("--require-hip-kernel-smoke")
    if bool(args.gpu_strict):
        cmd_ci.append("--require-gpu-strict")
    if reason_code == "PASS" and not _run_reusable("phase1_ci_gate_nightly", cmd_ci, args.ci_report, steps):
        reason_code = "ERR_CI_GATE"

    cmd_design_opt_smoke = [
        sys.executable,
        "implementation/phase1/run_design_optimization_cost_reduction_smoke.py",
        "--objective-profile",
        str(args.design_opt_cost_smoke_objective_profile),
        "--ndtha-step-count",
        str(int(args.design_opt_cost_smoke_ndtha_step_count)),
        "--out",
        str(args.design_opt_cost_smoke_report),
    ]
    if reason_code == "PASS" and bool(args.enable_design_opt_cost_smoke):
        smoke_ok = _run_reusable(
            "design_optimization_cost_reduction_smoke",
            cmd_design_opt_smoke,
            args.design_opt_cost_smoke_report,
            steps,
        )
        if (not smoke_ok) and bool(args.strict_design_opt_cost_smoke):
            reason_code = "ERR_DESIGN_OPT_COST_REDUCTION_SMOKE"

    smoke_history_payload: dict = {}
    if bool(args.enable_design_opt_cost_smoke):
        if DRY_RUN:
            smoke_history_payload = load_json(args.design_opt_cost_smoke_history)
        else:
            smoke_history_payload = _update_smoke_history(
                args.design_opt_cost_smoke_history,
                args.design_opt_cost_smoke_report,
                limit=int(args.design_opt_cost_smoke_history_limit),
            )

    smoke_payload = (
        _smoke_report_payload(args.design_opt_cost_smoke_report)
        if bool(args.enable_design_opt_cost_smoke)
        else {}
    )
    smoke_recommendation = _smoke_strict_recommendation(smoke_history_payload) if bool(args.enable_design_opt_cost_smoke) else {}
    committee_summary = load_json(args.committee_summary_report)

    cmd_design_opt_dataset_refresh = [
        sys.executable,
        "implementation/phase1/generate_design_optimization_dataset.py",
        "--midas-model",
        str(args.mgt_json_out),
        "--code-check",
        str(args.code_check_report),
        "--pbd-review",
        str(args.pbd_review_package_report),
        "--ndtha-residual",
        str(args.ndtha_residual_report),
        "--dataset-npz-out",
        str(args.design_opt_dataset_npz),
        "--summary-out",
        str(args.design_opt_dataset_report),
    ]
    cmd_design_opt_rebar_payload_projection = [
        sys.executable,
        "implementation/phase1/generate_group_local_rebar_payloads.py",
        "--parsed-model-json",
        str(args.mgt_json_out),
        "--dataset-npz",
        str(args.design_opt_dataset_npz),
        "--changes-json",
        str(args.design_opt_cost_reduction_changes),
        "--projection-json-out",
        str(args.design_opt_rebar_payload_projection_json),
    ]
    cmd_design_opt_connection_detailing_payload_projection = [
        sys.executable,
        "implementation/phase1/generate_group_local_connection_detailing_payloads.py",
        "--parsed-model-json",
        str(args.mgt_json_out),
        "--dataset-npz",
        str(args.design_opt_dataset_npz),
        "--changes-json",
        str(args.design_opt_cost_reduction_changes),
        "--projection-json-out",
        str(args.design_opt_connection_detailing_payload_projection_json),
    ]
    cmd_design_opt_detailing_payload_projection = [
        sys.executable,
        "implementation/phase1/generate_group_local_detailing_payloads.py",
        "--parsed-model-json",
        str(args.mgt_json_out),
        "--dataset-npz",
        str(args.design_opt_dataset_npz),
        "--changes-json",
        str(args.design_opt_cost_reduction_changes),
        "--projection-json-out",
        str(args.design_opt_detailing_payload_projection_json),
    ]
    cmd_mgt_export_direct_patch = [
        sys.executable,
        "implementation/phase1/export_design_optimization_to_mgt.py",
        "--source-mgt",
        str(args.mgt_input),
        "--parsed-model-json",
        str(args.mgt_json_out),
        "--dataset-npz",
        str(args.design_opt_dataset_npz),
        "--changes-json",
        str(args.design_opt_cost_reduction_changes),
        "--rebar-payload-projection-json",
        str(args.design_opt_rebar_payload_projection_json),
        "--connection-detailing-payload-projection-json",
        str(args.design_opt_connection_detailing_payload_projection_json),
        "--detailing-payload-projection-json",
        str(args.design_opt_detailing_payload_projection_json),
        "--output-mgt",
        str(args.mgt_export_output_mgt),
        "--report-out",
        str(args.mgt_export_report),
        "--patch-manifest-out",
        str(args.mgt_export_patch_manifest),
        "--instruction-sidecar-out",
        str(args.mgt_export_instruction_sidecar),
        "--audit-review-manifest-out",
        str(args.mgt_export_audit_review_manifest),
        "--audit-review-packet-manifest-out",
        str(args.mgt_export_audit_review_packet_manifest),
        "--audit-review-packet-dir-out",
        str(args.mgt_export_audit_review_packet_directory),
        "--audit-review-queue-manifest-out",
        str(args.mgt_export_audit_review_queue_manifest),
        "--audit-review-queue-status-dir-out",
        str(args.mgt_export_audit_review_queue_status_directory),
        "--audit-review-followup-manifest-out",
        str(args.mgt_export_audit_review_followup_manifest),
    ]
    cmd_pbd_hinge_refresh = [
        sys.executable,
        "implementation/phase1/generate_pbd_hinge_refresh_artifact.py",
        "--design-optimization-dataset",
        str(args.design_opt_dataset_report),
        "--design-optimization-npz",
        str(args.design_opt_dataset_npz),
        "--cost-reduction-changes",
        str(args.design_opt_cost_reduction_changes),
        "--out",
        str(args.pbd_hinge_refresh_artifact),
    ]
    if str(args.pbd_hinge_refresh_source_input).strip():
        cmd_pbd_hinge_refresh.extend(["--source-input", str(args.pbd_hinge_refresh_source_input)])
    cmd_pbd_hinge_refresh_source = [
        sys.executable,
        "implementation/phase1/generate_pbd_hinge_refresh_source.py",
        "--design-optimization-dataset",
        str(args.design_opt_dataset_report),
        "--design-optimization-npz",
        str(args.design_opt_dataset_npz),
        "--cost-reduction-changes",
        str(args.design_opt_cost_reduction_changes),
        "--out",
        str(args.pbd_hinge_refresh_source_output),
    ]
    cmd_pbd_hinge_refresh_report = [
        sys.executable,
        "implementation/phase1/generate_pbd_hinge_refresh_report.py",
        "--design-optimization-dataset",
        str(args.design_opt_dataset_report),
        "--pbd-review-package",
        str(args.pbd_review_package_report),
        "--midas-conversion",
        str(args.mgt_conversion_report),
        "--ndtha-stress-report",
        str(args.ndtha_stress_report),
        "--benchmark-asset-registry",
        str(args.pbd_hinge_benchmark_asset_registry),
        "--benchmark-gate-report",
        str(args.peer_spd_hinge_benchmark_report),
        "--benchmark-fixture-regression-report",
        str(args.peer_spd_hinge_fixture_regression_report),
        "--benchmark-alignment-report",
        str(args.peer_spd_hinge_alignment_report),
        "--hinge-refresh-artifact",
        str(args.pbd_hinge_refresh_artifact),
        "--out",
        str(args.pbd_hinge_refresh_report),
    ]
    cmd_panel_zone_solver_verified_export_bundle = [
        sys.executable,
        "implementation/phase1/generate_panel_zone_solver_verified_export_bundle.py",
        "--joint-geometry-source",
        str(args.panel_zone_solver_verified_joint_geometry_source),
        "--rebar-anchorage-source",
        str(args.panel_zone_solver_verified_rebar_anchorage_source),
        "--clash-verification-source",
        str(args.panel_zone_solver_verified_clash_verification_source),
        "--source-origin-class",
        str(args.panel_zone_solver_verified_source_origin_class or "unclassified_external_source"),
        "--out",
        str(args.panel_zone_solver_export_bundle),
    ]
    cmd_panel_zone_solver_export_bundle = [
        sys.executable,
        "implementation/phase1/generate_panel_zone_solver_export_bundle.py",
        "--design-optimization-dataset",
        str(args.design_opt_dataset_report),
        "--design-optimization-npz",
        str(args.design_opt_dataset_npz),
        "--midas-json",
        str(args.mgt_json_out),
        "--out",
        str(args.panel_zone_solver_export_bundle),
    ]
    cmd_panel_zone_joint_geometry_source = [
        sys.executable,
        "implementation/phase1/generate_panel_zone_joint_geometry_3d_source.py",
        "--design-optimization-dataset",
        str(args.design_opt_dataset_report),
        "--design-optimization-npz",
        str(args.design_opt_dataset_npz),
        "--out",
        str(args.panel_zone_joint_geometry_source_output),
    ]
    if (
        str(args.panel_zone_joint_geometry_artifact).strip()
        and str(args.panel_zone_joint_geometry_artifact) not in {
            str(args.panel_zone_joint_geometry_source_output),
            str(args.panel_zone_joint_geometry_contract),
        }
    ):
        cmd_panel_zone_joint_geometry_source.extend(["--source-input", str(args.panel_zone_joint_geometry_artifact)])
    cmd_panel_zone_rebar_anchorage_source = [
        sys.executable,
        "implementation/phase1/generate_panel_zone_rebar_anchorage_3d_source.py",
        "--design-optimization-dataset",
        str(args.design_opt_dataset_report),
        "--design-optimization-npz",
        str(args.design_opt_dataset_npz),
        "--out",
        str(args.panel_zone_rebar_anchorage_source_output),
    ]
    if (
        str(args.panel_zone_rebar_anchorage_artifact).strip()
        and str(args.panel_zone_rebar_anchorage_artifact) not in {
            str(args.panel_zone_rebar_anchorage_source_output),
            str(args.panel_zone_rebar_anchorage_contract),
        }
    ):
        cmd_panel_zone_rebar_anchorage_source.extend(["--source-input", str(args.panel_zone_rebar_anchorage_artifact)])
    cmd_panel_zone_clash_verification_source = [
        sys.executable,
        "implementation/phase1/generate_panel_zone_clash_verification_3d_source.py",
        "--design-optimization-dataset",
        str(args.design_opt_dataset_report),
        "--design-optimization-npz",
        str(args.design_opt_dataset_npz),
        "--out",
        str(args.panel_zone_clash_verification_source_output),
    ]
    if (
        str(args.panel_zone_clash_verification_artifact).strip()
        and str(args.panel_zone_clash_verification_artifact) not in {
            str(args.panel_zone_clash_verification_source_output),
            str(args.panel_zone_clash_verification_contract),
        }
    ):
        cmd_panel_zone_clash_verification_source.extend(
            ["--source-input", str(args.panel_zone_clash_verification_artifact)]
        )
    cmd_panel_zone_joint_geometry_contract = [
        sys.executable,
        "implementation/phase1/generate_panel_zone_joint_geometry_3d_contract.py",
        "--source-artifact",
        str(args.panel_zone_joint_geometry_source_output),
        "--out",
        str(args.panel_zone_joint_geometry_contract),
    ]
    cmd_panel_zone_rebar_anchorage_contract = [
        sys.executable,
        "implementation/phase1/generate_panel_zone_rebar_anchorage_3d_contract.py",
        "--source-artifact",
        str(args.panel_zone_rebar_anchorage_source_output),
        "--out",
        str(args.panel_zone_rebar_anchorage_contract),
    ]
    cmd_panel_zone_clash_verification_contract = [
        sys.executable,
        "implementation/phase1/generate_panel_zone_clash_verification_3d_contract.py",
        "--source-artifact",
        str(args.panel_zone_clash_verification_source_output),
        "--out",
        str(args.panel_zone_clash_verification_contract),
    ]
    cmd_panel_zone_clash_artifact = [
        sys.executable,
        "implementation/phase1/generate_panel_zone_clash_artifact.py",
        "--design-optimization-dataset",
        str(args.design_opt_dataset_report),
        "--out",
        str(args.panel_zone_clash_artifact),
        "--panel-zone-joint-geometry-artifact",
        str(args.panel_zone_joint_geometry_contract),
        "--panel-zone-rebar-anchorage-artifact",
        str(args.panel_zone_rebar_anchorage_contract),
        "--panel-zone-clash-verification-artifact",
        str(args.panel_zone_clash_verification_contract),
    ]
    cmd_foundation_optimization_artifact = [
        sys.executable,
        "implementation/phase1/generate_foundation_optimization_artifact.py",
        "--design-optimization-dataset",
        str(args.design_opt_dataset_report),
        "--design-optimization-npz",
        str(args.design_opt_dataset_npz),
        "--midas-model",
        str(args.mgt_json_out),
        "--out",
        str(args.foundation_optimization_artifact),
    ]
    cmd_wind_raw_mapping_artifact = [
        sys.executable,
        "implementation/phase1/build_wind_raw_mapping_artifact.py",
        "--raw-wind",
        str(args.wind_raw_input),
        "--raw-wind-manifest",
        str(args.wind_raw_manifest),
        "--midas-json",
        str(args.mgt_json_out),
        "--midas-conversion",
        str(args.mgt_conversion_report),
        "--wind-gate-report",
        str(args.wind_gate_report),
        "--out",
        str(args.wind_raw_mapping_artifact),
    ]
    cmd_panel_zone_clash = [
        sys.executable,
        "implementation/phase1/generate_panel_zone_clash_report.py",
        "--design-optimization-dataset",
        str(args.design_opt_dataset_report),
        "--pbd-review-package",
        str(args.pbd_review_package_report),
        "--panel-zone-clash-artifact",
        str(args.panel_zone_clash_artifact),
        "--out",
        str(args.panel_zone_clash_report),
    ]
    cmd_panel_zone_solver_verified_inbox_status = [
        sys.executable,
        "implementation/phase1/generate_panel_zone_solver_verified_inbox_status.py",
        "--inbox-dir",
        str(args.panel_zone_solver_verified_drop_dir),
        "--out",
        str(args.panel_zone_solver_verified_inbox_status_report),
    ]
    cmd_foundation_optimization = [
        sys.executable,
        "implementation/phase1/generate_foundation_optimization_report.py",
        "--design-optimization-dataset",
        str(args.design_opt_dataset_report),
        "--foundation-optimization-artifact",
        str(args.foundation_optimization_artifact),
        "--out",
        str(args.foundation_optimization_report),
    ]
    cmd_wind_raw_mapping = [
        sys.executable,
        "implementation/phase1/generate_wind_tunnel_raw_mapping_report.py",
        "--raw-wind",
        str(args.wind_raw_input),
        "--raw-wind-manifest",
        str(args.wind_raw_manifest),
        "--wind-raw-mapping",
        str(args.wind_raw_mapping_artifact),
        "--midas-conversion",
        str(args.mgt_conversion_report),
        "--out",
        str(args.wind_raw_mapping_report),
    ]
    cmd_tpu_hffb_benchmark = [
        sys.executable,
        "implementation/phase1/run_tpu_hffb_benchmark_gate.py",
        "--asset-registry",
        str(args.wind_benchmark_asset_registry),
        "--out",
        str(args.tpu_hffb_benchmark_report),
    ]
    cmd_pbd_hinge_benchmark_asset_registry = [
        sys.executable,
        "implementation/phase1/build_pbd_hinge_benchmark_asset_registry.py",
        "--seed-manifest",
        str(args.peer_spd_column_seed_manifest),
        "--materialize-report",
        str(args.peer_spd_column_materialize_report),
        "--out",
        str(args.pbd_hinge_benchmark_asset_registry),
    ]
    cmd_peer_spd_hinge_benchmark = [
        sys.executable,
        "implementation/phase1/run_peer_spd_hinge_benchmark_gate.py",
        "--asset-registry",
        str(args.pbd_hinge_benchmark_asset_registry),
        "--out",
        str(args.peer_spd_hinge_benchmark_report),
    ]
    cmd_peer_spd_hinge_fixture_regression = [
        sys.executable,
        "implementation/phase1/run_peer_spd_hinge_fixture_regression.py",
        "--asset-registry",
        str(args.pbd_hinge_benchmark_asset_registry),
        "--out",
        str(args.peer_spd_hinge_fixture_regression_report),
    ]
    cmd_peer_spd_hinge_alignment = [
        sys.executable,
        "implementation/phase1/run_peer_spd_hinge_refresh_alignment.py",
        "--asset-registry",
        str(args.pbd_hinge_benchmark_asset_registry),
        "--hinge-refresh-source",
        str(args.pbd_hinge_refresh_source_output),
        "--out",
        str(args.peer_spd_hinge_alignment_report),
    ]
    if reason_code == "PASS":
        if not _run_reusable(
            "design_optimization_dataset_refresh",
            cmd_design_opt_dataset_refresh,
            args.design_opt_dataset_report,
            steps,
        ):
            reason_code = "ERR_DESIGN_OPT_DATASET_REFRESH"
        if reason_code == "PASS" and not _run_reusable(
            "design_optimization_rebar_payload_projection",
            cmd_design_opt_rebar_payload_projection,
            args.design_opt_rebar_payload_projection_json,
            steps,
        ):
            reason_code = "ERR_DESIGN_OPT_REBAR_PAYLOAD_PROJECTION"
        if reason_code == "PASS" and not _run_reusable(
            "design_optimization_connection_detailing_payload_projection",
            cmd_design_opt_connection_detailing_payload_projection,
            args.design_opt_connection_detailing_payload_projection_json,
            steps,
        ):
            reason_code = "ERR_DESIGN_OPT_CONNECTION_DETAILING_PAYLOAD_PROJECTION"
        if reason_code == "PASS" and not _run_reusable(
            "design_optimization_detailing_payload_projection",
            cmd_design_opt_detailing_payload_projection,
            args.design_opt_detailing_payload_projection_json,
            steps,
        ):
            reason_code = "ERR_DESIGN_OPT_DETAILING_PAYLOAD_PROJECTION"
        if reason_code == "PASS" and not _run_reusable(
            "mgt_export_direct_patch",
            cmd_mgt_export_direct_patch,
            args.mgt_export_report,
            steps,
        ):
            reason_code = "ERR_MGT_EXPORT_DIRECT_PATCH"
        if reason_code == "PASS" and need_autogen_pbd_hinge_refresh_source and not _run_reusable(
            "pbd_hinge_refresh_source",
            cmd_pbd_hinge_refresh_source,
            args.pbd_hinge_refresh_source_output,
            steps,
        ):
            reason_code = "ERR_PBD_HINGE_REFRESH_SOURCE"
        if reason_code == "PASS" and not _run_reusable(
            "pbd_hinge_refresh_artifact",
            cmd_pbd_hinge_refresh,
            args.pbd_hinge_refresh_artifact,
            steps,
        ):
            reason_code = "ERR_PBD_HINGE_REFRESH_ARTIFACT"
        if reason_code == "PASS" and not _run_reusable(
            "pbd_hinge_refresh_report",
            cmd_pbd_hinge_refresh_report,
            args.pbd_hinge_refresh_report,
            steps,
        ):
            reason_code = "ERR_PBD_HINGE_REFRESH_REPORT"
        if need_autogen_panel_zone_solver_verified_export_bundle and reason_code == "PASS" and not _run_reusable(
            "panel_zone_solver_verified_export_bundle",
            cmd_panel_zone_solver_verified_export_bundle,
            args.panel_zone_solver_export_bundle,
            steps,
        ):
            reason_code = "ERR_PANEL_ZONE_SOLVER_VERIFIED_EXPORT_BUNDLE"
        if need_autogen_panel_zone_solver_export_bundle and reason_code == "PASS" and not _run_reusable(
            "panel_zone_solver_export_bundle",
            cmd_panel_zone_solver_export_bundle,
            args.panel_zone_solver_export_bundle,
            steps,
        ):
            reason_code = "ERR_PANEL_ZONE_SOLVER_EXPORT_BUNDLE"
        if reason_code == "PASS" and not _run_reusable(
            "panel_zone_joint_geometry_source",
            cmd_panel_zone_joint_geometry_source,
            args.panel_zone_joint_geometry_source_output,
            steps,
        ):
            reason_code = "ERR_PANEL_ZONE_JOINT_GEOMETRY_SOURCE"
        if reason_code == "PASS" and not _run_reusable(
            "panel_zone_rebar_anchorage_source",
            cmd_panel_zone_rebar_anchorage_source,
            args.panel_zone_rebar_anchorage_source_output,
            steps,
        ):
            reason_code = "ERR_PANEL_ZONE_REBAR_ANCHORAGE_SOURCE"
        if reason_code == "PASS" and not _run_reusable(
            "panel_zone_clash_verification_source",
            cmd_panel_zone_clash_verification_source,
            args.panel_zone_clash_verification_source_output,
            steps,
        ):
            reason_code = "ERR_PANEL_ZONE_CLASH_VERIFICATION_SOURCE"
        if reason_code == "PASS" and not _run_reusable(
            "panel_zone_joint_geometry_contract",
            cmd_panel_zone_joint_geometry_contract,
            args.panel_zone_joint_geometry_contract,
            steps,
        ):
            reason_code = "ERR_PANEL_ZONE_JOINT_GEOMETRY_CONTRACT"
        if reason_code == "PASS" and not _run_reusable(
            "panel_zone_rebar_anchorage_contract",
            cmd_panel_zone_rebar_anchorage_contract,
            args.panel_zone_rebar_anchorage_contract,
            steps,
        ):
            reason_code = "ERR_PANEL_ZONE_REBAR_ANCHORAGE_CONTRACT"
        if reason_code == "PASS" and not _run_reusable(
            "panel_zone_clash_verification_contract",
            cmd_panel_zone_clash_verification_contract,
            args.panel_zone_clash_verification_contract,
            steps,
        ):
            reason_code = "ERR_PANEL_ZONE_CLASH_VERIFICATION_CONTRACT"
        if reason_code == "PASS" and not _run_reusable(
            "panel_zone_clash_artifact",
            cmd_panel_zone_clash_artifact,
            args.panel_zone_clash_artifact,
            steps,
        ):
            reason_code = "ERR_PANEL_ZONE_CLASH_ARTIFACT"
        if reason_code == "PASS" and not _run_reusable(
            "panel_zone_solver_verified_inbox_status",
            cmd_panel_zone_solver_verified_inbox_status,
            args.panel_zone_solver_verified_inbox_status_report,
            steps,
        ):
            reason_code = "ERR_PANEL_ZONE_SOLVER_VERIFIED_INBOX_STATUS"
        if reason_code == "PASS" and not _run_reusable(
            "foundation_optimization_artifact",
            cmd_foundation_optimization_artifact,
            args.foundation_optimization_artifact,
            steps,
        ):
            reason_code = "ERR_FOUNDATION_OPTIMIZATION_ARTIFACT"
        if reason_code == "PASS" and not _run_reusable(
            "wind_raw_mapping_artifact",
            cmd_wind_raw_mapping_artifact,
            args.wind_raw_mapping_artifact,
            steps,
        ):
            reason_code = "ERR_WIND_RAW_MAPPING_ARTIFACT"
        if reason_code == "PASS":
            _run_reusable("panel_zone_clash_report", cmd_panel_zone_clash, args.panel_zone_clash_report, steps)
            _run_reusable("foundation_optimization_report", cmd_foundation_optimization, args.foundation_optimization_report, steps)
            _run_reusable("wind_tunnel_raw_mapping_report", cmd_wind_raw_mapping, args.wind_raw_mapping_report, steps)
            _run_reusable("tpu_hffb_benchmark_gate", cmd_tpu_hffb_benchmark, args.tpu_hffb_benchmark_report, steps)
            _run_reusable(
                "pbd_hinge_benchmark_asset_registry",
                cmd_pbd_hinge_benchmark_asset_registry,
                args.pbd_hinge_benchmark_asset_registry,
                steps,
            )
            _run_reusable("peer_spd_hinge_benchmark_gate", cmd_peer_spd_hinge_benchmark, args.peer_spd_hinge_benchmark_report, steps)
            _run_reusable(
                "peer_spd_hinge_fixture_regression",
                cmd_peer_spd_hinge_fixture_regression,
                args.peer_spd_hinge_fixture_regression_report,
                steps,
            )
            _run_reusable("peer_spd_hinge_alignment", cmd_peer_spd_hinge_alignment, args.peer_spd_hinge_alignment_report, steps)

    cmd_val = [
        sys.executable,
        "implementation/phase1/validate_phase1_artifacts.py",
        "--ci",
        str(args.ci_report),
        "--hip-kernel-smoke",
        str(args.hip_kernel_smoke_report),
        "--phase3-pipeline",
        str(args.phase3_report),
        "--topology-gate",
        str(args.topology_gate),
        "--partitioned-scaleout",
        str(args.partitioned_scaleout),
        "--sync-stress",
        str(args.sync_stress),
        "--noise-convergence",
        str(args.noise_convergence),
        "--commercial-csv-gate",
        str(args.commercial_csv_gate),
        "--midas-mgt-conversion",
        str(args.mgt_conversion_report),
        "--scaleout-io",
        str(args.scaleout_io),
        "--nightly-10m-repro",
        str(args.nightly_10m_repro),
        "--commercial-readiness",
        str(args.commercial_readiness_report),
        "--real-source-multi",
        str(args.real_source_multi_report),
        "--nonlinear-engine",
        str(args.nonlinear_engine_report),
        "--pushover-stress",
        str(args.pushover_stress_report),
        "--ndtha-stress",
        str(args.ndtha_stress_report),
        "--ndtha-residual-gate",
        str(args.ndtha_residual_report),
        "--global-authority-gate",
        str(args.global_authority_report),
        "--wind-benchmark",
        str(args.wind_benchmark_report),
        "--ssi-boundary",
        str(args.ssi_boundary_report),
        "--damper-validation",
        str(args.damper_validation_report),
        "--kds-compliance",
        str(args.kds_compliance_summary),
        "--construction-sequence",
        str(args.construction_sequence_report),
        "--flexible-diaphragm",
        str(args.flexible_diaphragm_report),
        "--repro-version-lock",
        str(args.repro_version_lock_report),
        "--release-registry",
        str(args.release_registry_report),
        "--solver-hip-e2e",
        str(args.solver_hip_e2e_report),
        "--rc-benchmark-lock",
        str(args.rc_benchmark_lock_report),
        "--out",
        str(args.static_validation),
    ]

    cmd_freeze = [
        sys.executable,
        "implementation/phase1/freeze_release_snapshot.py",
        "--out",
        str(args.freeze_report),
    ]
    cmd_promote = [
        sys.executable,
        "implementation/phase1/promote_release_candidate.py",
        "--pr-ci",
        str(args.ci_report),
        "--out",
        str(args.promotion_report),
    ]

    if reason_code == "PASS":
        _run_reusable("static_artifact_validation_pre_gap", cmd_val, args.static_validation, steps)
        _run_reusable("freeze_release_snapshot_pre_gap", cmd_freeze, args.freeze_report, steps)
        if not bool(args.skip_promotion):
            _run_reusable("promote_release_candidate_pre_gap", cmd_promote, args.promotion_report, steps)

    provisional_payload = _build_payload(
        args,
        reason_code=reason_code,
        steps=steps,
        smoke_payload=smoke_payload,
        smoke_history_payload=smoke_history_payload,
        smoke_recommendation=smoke_recommendation,
        committee_summary=committee_summary,
    )
    out.write_text(json.dumps(provisional_payload, indent=2), encoding="utf-8")

    cmd_release_gap = [
        sys.executable,
        "implementation/phase1/generate_release_gap_report.py",
        "--nightly-release",
        str(args.out),
        "--ci-gate",
        str(args.ci_report),
        "--static-validation",
        str(args.static_validation),
        "--freeze-report",
        str(args.freeze_report),
        "--promotion-report",
        str(args.promotion_report),
        "--commercial-readiness",
        str(args.commercial_readiness_report),
        "--global-authority",
        str(args.global_authority_report),
        "--hip-kernel-smoke",
        str(args.hip_kernel_smoke_report),
        "--midas-conversion",
        str(args.mgt_conversion_report),
        "--mgt-export-output-mgt",
        str(args.mgt_export_output_mgt),
        "--mgt-export-report",
        str(args.mgt_export_report),
        "--mgt-export-audit-review-queue-manifest",
        str(args.mgt_export_audit_review_queue_manifest),
        "--mgt-export-audit-review-followup-manifest",
        str(args.mgt_export_audit_review_followup_manifest),
        "--construction-sequence",
        str(args.construction_sequence_report),
        "--flexible-diaphragm",
        str(args.flexible_diaphragm_report),
        "--repro-version-lock",
        str(args.repro_version_lock_report),
        "--release-registry",
        str(args.release_registry_report),
        "--kds-compliance",
        str(args.kds_compliance_summary),
        "--solver-hip-e2e",
        str(args.solver_hip_e2e_report),
        "--solver-truthfulness-report",
        str(args.solver_truthfulness_report),
        "--hardest-external-10case-kickoff-report",
        str(args.hardest_external_10case_kickoff_report),
        "--rc-benchmark-lock",
        str(args.rc_benchmark_lock_report),
        "--quality-mgt-corpus",
        str(args.quality_mgt_corpus_report),
        "--pbd-package",
        str(args.pbd_review_package_report),
        "--design-opt-dataset-report",
        str(args.design_opt_dataset_report),
        "--pbd-hinge-refresh-report",
        str(args.pbd_hinge_refresh_report),
        "--panel-zone-clash-report",
        str(args.panel_zone_clash_report),
        "--panel-zone-solver-verified-inbox-status-report",
        str(args.panel_zone_solver_verified_inbox_status_report),
        "--foundation-optimization-report",
        str(args.foundation_optimization_report),
        "--wind-raw-mapping-report",
        str(args.wind_raw_mapping_report),
        "--committee-summary",
        str(args.committee_summary_report),
        "--nightly-history-root",
        str(args.release_gap_history_root),
        "--nightly-history-limit",
        str(int(args.release_gap_history_limit)),
        "--out-json",
        str(args.release_gap_report),
        "--out-md",
        str(args.release_gap_markdown),
        "--out-smoke-history-png",
        str(args.release_gap_smoke_history_png),
        "--out-measured-chain-category-png",
        str(args.release_gap_measured_chain_category_png),
    ]
    cmd_external_benchmark_submission_readiness = [
        sys.executable,
        "implementation/phase1/generate_external_benchmark_submission_readiness.py",
        "--release-gap-report",
        str(args.release_gap_report),
        "--commercial-readiness-report",
        str(args.commercial_readiness_report),
        "--tpu-hffb-benchmark-report",
        str(args.tpu_hffb_benchmark_report),
        "--peer-spd-hinge-benchmark-report",
        str(args.peer_spd_hinge_benchmark_report),
        "--peer-spd-hinge-fixture-regression-report",
        str(args.peer_spd_hinge_fixture_regression_report),
        "--peer-spd-hinge-alignment-report",
        str(args.peer_spd_hinge_alignment_report),
        "--out",
        str(args.external_benchmark_submission_readiness_report),
    ]
    cmd_external_benchmark_kickoff_package = [
        sys.executable,
        "implementation/phase1/generate_external_benchmark_kickoff_package.py",
        "--readiness-report",
        str(args.external_benchmark_submission_readiness_report),
        "--out-dir",
        str(args.external_benchmark_kickoff_dir),
    ]
    cmd_external_benchmark_execution_manifest = [
        sys.executable,
        "implementation/phase1/generate_external_benchmark_execution_manifest.py",
        "--kickoff-package",
        str(args.external_benchmark_kickoff_package_report),
        "--out-dir",
        str(args.external_benchmark_kickoff_dir),
    ]
    cmd_external_benchmark_execution_status_manifest = [
        sys.executable,
        "implementation/phase1/generate_external_benchmark_execution_status_manifest.py",
        "--execution-manifest",
        str(args.external_benchmark_execution_manifest_report),
        "--updates-json",
        str(args.external_benchmark_execution_updates_json),
        "--out",
        str(args.external_benchmark_execution_status_manifest_report),
    ]
    cmd_audit_review_decision_batch_template = [
        sys.executable,
        "implementation/phase1/generate_audit_review_decision_batch_template.py",
        "--queue-manifest",
        str(args.mgt_export_audit_review_queue_manifest),
        "--out",
        str(args.audit_review_decision_batch_template_json),
    ]
    cmd_audit_review_decision_batch_examples = [
        sys.executable,
        "implementation/phase1/generate_audit_review_decision_batch_examples.py",
        "--template-json",
        str(args.audit_review_decision_batch_template_json),
        "--out-dir",
        str(args.external_benchmark_kickoff_dir),
    ]
    cmd_audit_review_decision_batch_previews = [
        sys.executable,
        "implementation/phase1/generate_audit_review_decision_batch_previews.py",
        "--queue-manifest",
        str(args.mgt_export_audit_review_queue_manifest),
        "--template-json",
        str(args.audit_review_decision_batch_template_json),
        "--release-gap-report",
        str(args.release_gap_report),
        "--commercial-readiness-report",
        str(args.commercial_readiness_report),
        "--tpu-hffb-benchmark-report",
        str(args.tpu_hffb_benchmark_report),
        "--peer-spd-hinge-benchmark-report",
        str(args.peer_spd_hinge_benchmark_report),
        "--peer-spd-hinge-fixture-regression-report",
        str(args.peer_spd_hinge_fixture_regression_report),
        "--peer-spd-hinge-alignment-report",
        str(args.peer_spd_hinge_alignment_report),
        "--out-dir",
        str(args.external_benchmark_kickoff_dir),
        "--out",
        str(args.audit_review_decision_batch_preview_artifacts_report),
    ]
    cmd_structural_optimization_viewer = [
        sys.executable,
        "implementation/phase1/generate_structural_optimization_visualization_viewer.py",
        "--release-gap-report",
        str(args.release_gap_report),
        "--export-report",
        str(args.mgt_export_report),
        "--change-summary-report",
        "implementation/phase1/release/design_optimization/design_optimization_cost_reduction_changes_summary.json",
        "--changes-report",
        str(args.design_opt_cost_reduction_changes),
        "--design-optimization-npz",
        str(args.design_opt_dataset_npz),
        "--model-json",
        str(args.mgt_json_out),
        "--execution-manifest",
        str(args.external_benchmark_execution_manifest_report),
        "--execution-status-manifest",
        str(args.external_benchmark_execution_status_manifest_report),
        "--committee-package-report",
        str(args.committee_package_report),
        "--out-dir",
        str(args.structural_optimization_viewer_dir),
    ]
    cmd_optimized_drawing_review = [
        sys.executable,
        "implementation/phase1/generate_optimized_drawing_review_ui.py",
        "--viewer-json",
        str(Path(args.structural_optimization_viewer_dir) / "structural_optimization_viewer.json"),
        "--out-html",
        str(Path(args.structural_optimization_viewer_dir) / "optimized_drawing_review.html"),
        "--out-summary",
        str(Path(args.structural_optimization_viewer_dir) / "optimized_drawing_review_summary.json"),
    ]
    if reason_code == "PASS" and not _run_reusable("release_gap_report", cmd_release_gap, args.release_gap_report, steps):
        reason_code = "ERR_RELEASE_GAP_REPORT"

    if reason_code == "PASS" and not _run_reusable(
        "external_benchmark_submission_readiness",
        cmd_external_benchmark_submission_readiness,
        args.external_benchmark_submission_readiness_report,
        steps,
    ):
        reason_code = "ERR_EXTERNAL_BENCHMARK_SUBMISSION_READINESS"

    if reason_code == "PASS" and not _run_reusable(
        "external_benchmark_kickoff_package",
        cmd_external_benchmark_kickoff_package,
        args.external_benchmark_kickoff_package_report,
        steps,
    ):
        reason_code = "ERR_EXTERNAL_BENCHMARK_KICKOFF_PACKAGE"

    if reason_code == "PASS" and not _run_reusable(
        "external_benchmark_execution_manifest",
        cmd_external_benchmark_execution_manifest,
        args.external_benchmark_execution_manifest_report,
        steps,
    ):
        reason_code = "ERR_EXTERNAL_BENCHMARK_EXECUTION_MANIFEST"

    if reason_code == "PASS" and not _run_reusable(
        "external_benchmark_execution_status_manifest",
        cmd_external_benchmark_execution_status_manifest,
        args.external_benchmark_execution_status_manifest_report,
        steps,
    ):
        reason_code = "ERR_EXTERNAL_BENCHMARK_EXECUTION_STATUS_MANIFEST"

    if reason_code == "PASS" and not _run_reusable(
        "audit_review_decision_batch_template",
        cmd_audit_review_decision_batch_template,
        args.audit_review_decision_batch_template_json,
        steps,
    ):
        reason_code = "ERR_AUDIT_REVIEW_DECISION_BATCH_TEMPLATE"

    if reason_code == "PASS" and not _run_reusable(
        "audit_review_decision_batch_examples",
        cmd_audit_review_decision_batch_examples,
        Path(args.external_benchmark_kickoff_dir) / "audit_review_decision_batch_approve_all.attested_example.json",
        steps,
    ):
        reason_code = "ERR_AUDIT_REVIEW_DECISION_BATCH_EXAMPLES"

    if reason_code == "PASS" and not _run_reusable(
        "audit_review_decision_batch_previews",
        cmd_audit_review_decision_batch_previews,
        args.audit_review_decision_batch_preview_artifacts_report,
        steps,
    ):
        reason_code = "ERR_AUDIT_REVIEW_DECISION_BATCH_PREVIEWS"

    if reason_code == "PASS" and not _run_reusable(
        "structural_optimization_viewer",
        cmd_structural_optimization_viewer,
        Path(args.structural_optimization_viewer_dir) / "structural_optimization_viewer.html",
        steps,
    ):
        reason_code = "ERR_STRUCTURAL_OPTIMIZATION_VIEWER"

    if reason_code == "PASS" and not _run_reusable(
        "optimized_drawing_review",
        cmd_optimized_drawing_review,
        Path(args.structural_optimization_viewer_dir) / "optimized_drawing_review.html",
        steps,
    ):
        reason_code = "ERR_OPTIMIZED_DRAWING_REVIEW"

    if reason_code == "PASS" and not _run_reusable(
        "release_registry_gate", _release_registry_cmd(), args.release_registry_report, steps
    ):
        reason_code = "ERR_RELEASE_REGISTRY_GATE"

    if reason_code == "PASS" and not _run_reusable("static_artifact_validation", cmd_val, args.static_validation, steps):
        reason_code = "ERR_STATIC_VALIDATION"

    if reason_code == "PASS" and not _run_reusable("freeze_release_snapshot", cmd_freeze, args.freeze_report, steps):
        reason_code = "ERR_FREEZE_SNAPSHOT"

    if reason_code == "PASS" and (not bool(args.skip_promotion)):
        if not _run_reusable("promote_release_candidate", cmd_promote, args.promotion_report, steps):
            promotion_payload = load_json(args.promotion_report)
            if str(promotion_payload.get("reason_code", "")) == "HOLD_FOR_REVIEW":
                reason_code = "ERR_PROMOTION_HOLD_FOR_REVIEW"
            else:
                reason_code = "ERR_PROMOTION"

    archive_manifest = ""
    if not bool(args.skip_archive):
        archive_manifest = _archive_outputs(
            test_name="nightly_release_gate",
            paths=[
                str(args.out),
                str(args.hip_kernel_smoke_report),
                str(args.commercial_csv_gate),
                str(args.mgt_conversion_report),
                str(args.mgt_json_out),
                str(args.mgt_npz_out),
                str(args.commercial_readiness_report),
                str(args.real_source_multi_report),
                str(args.nonlinear_engine_report),
                str(args.pushover_stress_report),
                str(args.ndtha_stress_report),
                str(args.ndtha_residual_report),
                str(args.global_authority_report),
                str(args.wind_benchmark_report),
                str(args.ssi_boundary_report),
                str(args.damper_validation_report),
                str(args.kds_compliance_summary),
                str(args.construction_sequence_report),
                str(args.flexible_diaphragm_report),
                str(args.repro_version_lock_report),
                str(args.release_registry_report),
                str(args.release_registry_public_key),
                str(args.release_registry_signature),
                str(args.solver_hip_e2e_report),
                str(args.hardest_external_10case_kickoff_report),
                str(args.rc_benchmark_lock_report),
                str(args.version_lock_manifest),
                str(args.phase3_report),
                str(args.topology_gate),
                str(args.partitioned_scaleout),
                str(args.sync_stress),
                str(args.noise_convergence),
                str(args.scaleout_io),
                str(args.nightly_10m_repro),
                str(args.ndtha_long_profile),
                str(args.ci_report),
                str(args.design_opt_cost_smoke_report),
                str(args.design_opt_cost_smoke_history),
                str(args.design_opt_dataset_report),
                str(args.design_opt_dataset_npz),
                str(args.design_opt_rebar_payload_projection_json),
                str(args.design_opt_connection_detailing_payload_projection_json),
                str(args.design_opt_detailing_payload_projection_json),
                str(args.mgt_export_output_mgt),
                str(args.mgt_export_report),
                str(args.mgt_export_patch_manifest),
                str(args.mgt_export_instruction_sidecar),
                str(args.mgt_export_audit_review_manifest),
                str(args.mgt_export_audit_review_packet_manifest),
                str(args.mgt_export_audit_review_packet_directory),
                str(args.mgt_export_audit_review_queue_manifest),
                str(args.mgt_export_audit_review_queue_status_directory),
                str(args.mgt_export_audit_review_followup_manifest),
                str(args.pbd_hinge_refresh_report),
                str(args.panel_zone_joint_geometry_contract),
                str(args.panel_zone_rebar_anchorage_contract),
                str(args.panel_zone_clash_verification_contract),
                str(args.panel_zone_clash_report),
                str(args.panel_zone_solver_verified_inbox_status_report),
                str(args.foundation_optimization_report),
                str(args.wind_raw_mapping_report),
                str(args.external_benchmark_submission_readiness_report),
                str(args.external_benchmark_kickoff_package_report),
                str(Path(args.external_benchmark_kickoff_dir) / "external_benchmark_kickoff_package.md"),
                str(args.external_benchmark_execution_manifest_report),
                str(Path(args.external_benchmark_kickoff_dir) / "external_benchmark_execution_manifest.md"),
                str(args.external_benchmark_execution_status_manifest_report),
                str(Path(args.external_benchmark_kickoff_dir) / "external_benchmark_execution_status_manifest.md"),
                str(args.audit_review_decision_batch_template_json),
                str(Path(args.audit_review_decision_batch_template_json).with_suffix(".md")),
                str(
                    Path(args.external_benchmark_kickoff_dir)
                    / "audit_review_decision_batch_approve_all.attested_example.json"
                ),
                str(
                    Path(args.external_benchmark_kickoff_dir)
                    / "audit_review_decision_batch_approve_all.attested_example.md"
                ),
                str(
                    Path(args.external_benchmark_kickoff_dir)
                    / "audit_review_decision_batch_mixed.attested_example.json"
                ),
                str(
                    Path(args.external_benchmark_kickoff_dir)
                    / "audit_review_decision_batch_mixed.attested_example.md"
                ),
                str(Path(args.external_benchmark_kickoff_dir) / "audit_review_decision_batch_approve_all.preview.json"),
                str(Path(args.external_benchmark_kickoff_dir) / "audit_review_decision_batch_reject_one.preview.json"),
                str(
                    Path(args.external_benchmark_kickoff_dir)
                    / "external_benchmark_submission_readiness_preview.approve_all.json"
                ),
                str(
                    Path(args.external_benchmark_kickoff_dir)
                    / "external_benchmark_submission_readiness_preview.approve_all.md"
                ),
                str(
                    Path(args.external_benchmark_kickoff_dir)
                    / "external_benchmark_submission_readiness_preview.reject_one.json"
                ),
                str(
                    Path(args.external_benchmark_kickoff_dir)
                    / "external_benchmark_submission_readiness_preview.reject_one.md"
                ),
                str(Path(args.external_benchmark_kickoff_dir) / "audit_review_decision_batch.live_preview.json"),
                str(Path(args.external_benchmark_kickoff_dir) / "audit_review_decision_batch.live_preview.md"),
                str(Path(args.external_benchmark_kickoff_dir) / "audit_review_decision_batch_run_report.json"),
                str(args.audit_review_decision_batch_preview_artifacts_report),
                str(args.release_gap_report),
                str(args.release_gap_markdown),
                str(args.release_gap_smoke_history_png),
                str(args.release_gap_measured_chain_category_png),
                str(args.static_validation),
                str(args.freeze_report),
                str(args.promotion_report),
            ],
        )

    payload = _build_payload(
        args,
        reason_code=reason_code,
        steps=steps,
        smoke_payload=smoke_payload,
        smoke_history_payload=smoke_history_payload,
        smoke_recommendation=smoke_recommendation,
        committee_summary=committee_summary,
        archive_manifest=archive_manifest,
    )
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote nightly release gate report: {out}")
    if reason_code != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
