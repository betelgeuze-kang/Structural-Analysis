#!/usr/bin/env python3
"""CI gate checker: validates strict probe + RCA + static contract artifacts.

Mobile-web friendly behavior:
- strict JSON shape/range checks (no runtime engine calls)
- deterministic reason_code output for CI debugging
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
import math
from pathlib import Path
import re
import subprocess
import sys
import tempfile


REASON_CODES = {
    "PASS": "all gates satisfied",
    "ERR_MISSING_STRICT_KEY": "strict report missing required key",
    "ERR_MISSING_RCA_KEY": "rca report missing required key",
    "ERR_INVALID_RCA_VALUE": "rca value is non-numeric or out-of-range",
    "ERR_STRICT_FAIL": "strict rust/hip pass flag is false",
    "ERR_HOST_COPY_SHARE": "host copy share exceeds configured threshold",
    "ERR_MISSING_CONTRACT_ARTIFACT": "one or more required static contract artifacts are missing or invalid",
    "ERR_PRIORITY3_FAIL": "priority3 summary indicates failure or invalid reason code",
    "ERR_BUCKLING_EIGEN_INVALID": "buckling eigen contract report failed validation",
    "ERR_ENERGY_MONOTONICITY": "physics residual energy monotonicity check failed",
    "ERR_META_OOD_FAIL": "meta-learning report does not satisfy OOD generalization minimum",
    "ERR_BENCHMARK_KPI_FAIL": "high-fidelity benchmark KPI contract failed",
    "ERR_BRANCHING_CONTRACT_FAIL": "derivative-free physical branching contract failed",
    "ERR_BIFURCATION_CONTRACT_FAIL": "bifurcation detector contract missing trigger readiness",
    "ERR_RUST_ONNX_CONTRACT_FAIL": "rust/hip/onnx native contract failed",
    "ERR_WINNING_TICKET_FAIL": "winning-ticket backprop contract failed",
    "ERR_RUST_MD3BEAD_PARITY_FAIL": "rust 3-bead hook is not parity-equivalent to python reference",
    "ERR_LJ_MAPPING_FAIL": "nonlinear Lennard-Jones mapping contract failed",
    "ERR_DYNAMIC_TIME_HISTORY_FAIL": "dynamic time-history contract failed",
    "ERR_CACHE_PROFILE_FAIL": "branch64 microbatch cache profile contract failed",
    "ERR_P0_ENGINE_PROFILE_FAIL": "p0 engine performance profile contract failed",
    "ERR_P0_CORE_GAP_FAIL": "p0 core-gap pipeline contract failed",
    "ERR_HIP_KERNEL_SMOKE_FAIL": "hip kernel smoke contract failed",
    "ERR_NOISE_STRESS_FAIL": "noise sensitivity stress contract failed",
    "ERR_SCALEOUT_IO_FAIL": "scale-out IO profile contract failed",
    "ERR_REAL_SOURCE_FAIL": "phase3 real-source integrity gate failed",
    "ERR_TOPOLOGY_GATE_FAIL": "opensees topology gate failed",
    "ERR_SYNC_STRESS_FAIL": "virtual sync stress gate failed",
    "ERR_GPU_STRICT_FAIL": "gpu strict gate failed (cpu backend/required/fallback detected)",
    "ERR_PARTITION_SCALE_FAIL": "partitioned scale-out contract failed",
    "ERR_NOISE_CONVERGENCE_FAIL": "adaptive-newton noise convergence contract failed",
    "ERR_NIGHTLY_10M_FAIL": "nightly 10M scale-out gate failed",
    "ERR_NIGHTLY_10M_REPRO_FAIL": "nightly 10M reproducibility gate failed",
    "ERR_NDTHA_LONG_PROFILE_FAIL": "10M NDTHA long-profile gate failed",
    "ERR_COMMERCIAL_CSV_GATE_FAIL": "commercial csv direct-compare gate failed",
    "ERR_MIDAS_MGT_CONVERSION_FAIL": "midas .mgt conversion contract failed",
    "ERR_MIDAS_SECTION_LIBRARY_ARTIFACT_FAIL": "midas section-library embedded-metadata validator failed",
    "ERR_MIDAS_KDS_GEOMETRY_BRIDGE_FAIL": "midas kds-geometry-bridge embedded-metadata validator failed",
    "ERR_MIDAS_LOADCOMB_ROUNDTRIP_FAIL": "midas loadcomb round-trip fidelity gate failed",
    "ERR_SOLVER_BREADTH_FAIL": "solver breadth evidence gate failed",
    "ERR_ELEMENT_MATERIAL_BREADTH_FAIL": "element/material direct breadth gate failed",
    "ERR_MATERIAL_CONSTITUTIVE_FAIL": "material constitutive evidence gate failed",
    "ERR_MIDAS_KDS_ROW_PROVENANCE_EXPORT_FAIL": "midas kds row provenance export failed",
    "ERR_CONTACT_READINESS_FAIL": "contact-readiness bounded evidence gate failed",
    "ERR_STRUCTURAL_CONTACT_FAIL": "full structural contact readiness gate failed",
    "ERR_GENERAL_FE_CONTACT_MATRIX_FAIL": "general FE contact benchmark matrix gate failed",
    "ERR_SURFACE_INTERACTION_BENCHMARK_FAIL": "surface-style FE interaction benchmark gate failed",
    "ERR_MIDAS_INTEROPERABILITY_FAIL": "midas interoperability/export readiness gate failed",
    "ERR_KOREAN_SOURCE_INGEST_FAIL": "korean public-source ingest gate failed",
    "ERR_MIDAS_NATIVE_ROUNDTRIP_FAIL": "native midas roundtrip/write-back gate failed",
    "ERR_NONLINEAR_GENERALIZATION_FAIL": "nonlinear member-model generalization gate failed",
    "ERR_WORKFLOW_PRODUCTIZATION_FAIL": "workflow/interoperability productization gate failed",
    "ERR_PHASEA_CONTRACT_FAIL": "phase-a contract pack (railway/tunnel schema+tables) failed",
    "ERR_PHASEB_TRACK_FAIL": "phase-b track dynamics contract pack failed",
    "ERR_PHASED_ML_FAIL": "phase-d multidomain residual-learning contract pack failed",
    "ERR_PHASEE_INTEGRATED_FAIL": "phase-e integrated coupling/compliance contract pack failed",
    "ERR_PHASEF_RESILIENCE_FAIL": "phase-f resilience contract pack failed",
    "ERR_COMMERCIAL_READINESS_FAIL": "commercial-readiness gate failed",
    "ERR_REAL_SOURCE_MULTI_FAIL": "multi real-source gate failed",
    "ERR_NONLINEAR_ENGINE_FAIL": "rust nonlinear frame engine gate failed",
    "ERR_PUSHOVER_STRESS_FAIL": "nonlinear pushover stress gate failed",
    "ERR_NDTHA_STRESS_FAIL": "nonlinear ndtha stress gate failed",
    "ERR_NDTHA_RESIDUAL_FAIL": "ndtha residual hard-threshold gate failed",
    "ERR_PBD_REVIEW_FAIL": "pbd review package gate failed",
    "ERR_GLOBAL_AUTHORITY_FAIL": "global authority gate failed",
    "ERR_WIND_BENCHMARK_FAIL": "wind long-duration benchmark gate failed",
    "ERR_SSI_BOUNDARY_FAIL": "ssi nonlinear boundary gate failed",
    "ERR_DAMPER_VALIDATION_FAIL": "damper validation gate failed",
    "ERR_KDS_FRONTEND_FAIL": "kds frontend/code-check package gate failed",
    "ERR_CONSTRUCTION_SEQUENCE_FAIL": "construction-sequence gate failed",
    "ERR_FLEXIBLE_DIAPHRAGM_FAIL": "flexible-diaphragm gate failed",
    "ERR_REPRO_VERSION_LOCK_FAIL": "reproducibility/version-lock gate failed",
    "ERR_RELEASE_REGISTRY_FAIL": "signed release registry gate failed",
    "ERR_PERFORMANCE_PROFILING_FAIL": "performance profiling gate failed",
    "ERR_SOLVER_HIP_E2E_FAIL": "solver-wide hip e2e contract failed",
    "ERR_SOLVER_TRUTHFULNESS_FAIL": "top-level solver truthfulness gate failed",
    "ERR_HARDEST_EXTERNAL_10CASE_KICKOFF_FAIL": "hardest external 10-case kickoff gate failed",
    "ERR_RC_BENCHMARK_LOCK_FAIL": "rc benchmark-lock gate failed",
}

DEFAULT_MIDAS_SECTION_LIBRARY_ARTIFACTS = [
    "implementation/phase1/open_data/midas/midas_generator_33.json",
    "implementation/phase1/open_data/midas/midas_generator_33.pr_recheck.json",
    "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json",
]

DEFAULT_MIDAS_KDS_GEOMETRY_BRIDGE_ARTIFACTS = list(DEFAULT_MIDAS_SECTION_LIBRARY_ARTIFACTS)
DEFAULT_MIDAS_LOADCOMB_ROUNDTRIP_ARTIFACTS = list(DEFAULT_MIDAS_SECTION_LIBRARY_ARTIFACTS)


def _is_finite_non_negative(x: object) -> bool:
    try:
        v = float(x)
    except Exception:
        return False
    return math.isfinite(v) and v >= 0.0


def _geometry_full_crosswalk_depth(
    load_crosswalk_surface: dict[str, Any],
    semantic_crosswalk_surface: dict[str, Any],
) -> int:
    counts: list[int] = []
    for surface in (load_crosswalk_surface, semantic_crosswalk_surface):
        if not isinstance(surface, dict):
            continue
        for key in ("count", "expected"):
            value = surface.get(key)
            if value is None:
                continue
            try:
                counts.append(int(value))
            except Exception:
                continue
    return min(counts) if counts else 0


def _ndtha_step_series_depth(ndtha_stress: dict) -> int:
    rows = ndtha_stress.get("rows") if isinstance(ndtha_stress.get("rows"), list) else []
    depths: list[int] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        summary = row.get("summary") if isinstance(row.get("summary"), dict) else {}
        value = summary.get("step_count_completed")
        if value is None:
            continue
        try:
            depths.append(int(value))
        except Exception:
            continue
    if depths:
        return max(depths)
    summary = ndtha_stress.get("summary") if isinstance(ndtha_stress.get("summary"), dict) else {}
    for key in ("step_series_depth", "step_count_completed", "full_step_count_max", "inline_step_count_max"):
        value = summary.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except Exception:
            continue
    return 0


def _support_search_surface(foundation_soil_link: dict) -> dict[str, Any]:
    summary = foundation_soil_link.get("summary") if isinstance(foundation_soil_link.get("summary"), dict) else {}
    support_search_model_types = sorted(
        {
            str(item).strip()
            for item in (summary.get("support_search_model_types") or [])
            if str(item).strip()
        }
    )
    node_to_surface_proxy_model_types = sorted(
        {
            str(item).strip()
            for item in (summary.get("node_to_surface_proxy_model_types") or [])
            if str(item).strip()
        }
    )
    support_search_family_types = sorted(
        {
            str(item).strip()
            for item in (summary.get("support_search_family_types") or [])
            if str(item).strip()
        }
    )
    node_to_surface_proxy_family_types = sorted(
        {
            str(item).strip()
            for item in (summary.get("node_to_surface_proxy_family_types") or [])
            if str(item).strip()
        }
    )
    support_search_pass = bool(summary.get("support_search_surface_pass", bool(support_search_model_types)))
    node_to_surface_proxy_pass = bool(summary.get("node_to_surface_proxy_pass", bool(node_to_surface_proxy_model_types)))
    support_depth_score = int(summary.get("support_depth_score", 0) or 0)
    summary_line = (
        f"Support search: {'PASS' if support_search_pass and node_to_surface_proxy_pass else 'CHECK'} | "
        f"support_search={len(support_search_model_types)} | "
        f"node_surface_proxy={len(node_to_surface_proxy_model_types)} | "
        f"support_depth={support_depth_score}"
        f"{' | support_families=' + str(len(support_search_family_types)) if support_search_family_types else ''}"
        f"{' | proxy_families=' + str(len(node_to_surface_proxy_family_types)) if node_to_surface_proxy_family_types else ''}"
    )
    return {
        "summary_line": summary_line,
        "support_search_count": len(support_search_model_types),
        "node_surface_proxy_count": len(node_to_surface_proxy_model_types),
        "support_depth_score": support_depth_score,
        "support_families_count": len(support_search_family_types),
        "proxy_families_count": len(node_to_surface_proxy_family_types),
        "support_search_pass": support_search_pass,
        "node_surface_proxy_pass": node_to_surface_proxy_pass,
    }


def _general_fe_contact_surface(general_fe_contact_matrix: dict) -> dict[str, Any]:
    summary = (
        general_fe_contact_matrix.get("summary")
        if isinstance(general_fe_contact_matrix.get("summary"), dict)
        else {}
    )
    surface = (
        general_fe_contact_matrix.get("general_fe_contact_matrix_surface")
        if isinstance(general_fe_contact_matrix.get("general_fe_contact_matrix_surface"), dict)
        else summary.get("general_fe_contact_matrix_surface")
        if isinstance(summary.get("general_fe_contact_matrix_surface"), dict)
        else {}
    )
    summary_line = str(general_fe_contact_matrix.get("summary_line", "") or "").strip()
    checks = (
        general_fe_contact_matrix.get("checks")
        if isinstance(general_fe_contact_matrix.get("checks"), dict)
        else {}
    )

    def _surface_or_summary_int(surface_key: str, summary_key: str, pattern: str) -> int:
        value = surface.get(surface_key)
        if value in (None, ""):
            value = summary.get(summary_key)
        if value not in (None, ""):
            try:
                return int(value)
            except Exception:
                pass
        match = re.search(pattern, summary_line)
        return int(match.group(1)) if match else 0

    support_search_count = _surface_or_summary_int(
        "support_search_model_count",
        "support_search_model_count",
        r"support_search=(\d+)",
    )
    if not support_search_count and isinstance(summary.get("support_search_model_types"), list):
        support_search_count = len([item for item in summary.get("support_search_model_types", []) if str(item).strip()])
    node_surface_proxy_count = _surface_or_summary_int(
        "node_to_surface_proxy_model_count",
        "node_to_surface_proxy_model_count",
        r"node_surface_proxy=(\d+)",
    )
    if not node_surface_proxy_count and isinstance(summary.get("node_to_surface_proxy_model_types"), list):
        node_surface_proxy_count = len(
            [item for item in summary.get("node_to_surface_proxy_model_types", []) if str(item).strip()]
        )
    support_depth_score = _surface_or_summary_int(
        "support_depth_score",
        "support_depth_score",
        r"support_depth=(\d+)",
    )
    coupling_depth_score = _surface_or_summary_int(
        "coupling_depth_score",
        "coupling_depth_score",
        r"coupling_depth=(\d+)",
    )
    support_family_count = _surface_or_summary_int(
        "support_search_family_count",
        "support_search_family_count",
        r"support_families=(\d+)(?:/\d+)?",
    )
    if not support_family_count and isinstance(summary.get("support_search_family_types"), list):
        support_family_count = len([item for item in summary.get("support_search_family_types", []) if str(item).strip()])
    proxy_family_count = _surface_or_summary_int(
        "node_to_surface_proxy_family_count",
        "node_to_surface_proxy_family_count",
        r"proxy_families=(\d+)(?:/\d+)?",
    )
    if not proxy_family_count and isinstance(summary.get("node_to_surface_proxy_family_types"), list):
        proxy_family_count = len(
            [item for item in summary.get("node_to_surface_proxy_family_types", []) if str(item).strip()]
        )
    support_family_required_count = _surface_or_summary_int(
        "support_search_family_requirement_count",
        "support_search_family_requirement_count",
        r"support_families=\d+/(\d+)",
    )
    if not support_family_required_count and isinstance(summary.get("support_search_family_requirements"), list):
        support_family_required_count = len(
            [item for item in summary.get("support_search_family_requirements", []) if str(item).strip()]
        )
    proxy_family_required_count = _surface_or_summary_int(
        "node_to_surface_proxy_family_requirement_count",
        "node_to_surface_proxy_family_requirement_count",
        r"proxy_families=\d+/(\d+)",
    )
    if not proxy_family_required_count and isinstance(summary.get("support_search_family_requirements"), list):
        proxy_family_required_count = len(
            [item for item in summary.get("support_search_family_requirements", []) if str(item).strip()]
        )
    surface_status = str(surface.get("status", "") or "").strip() or (
        "PASS" if bool(general_fe_contact_matrix.get("contract_pass", False)) else "CHECK"
    )
    compact_summary_line = (
        f"General FE compact: {surface_status} | "
        f"support_search={support_search_count} | "
        f"node_surface_proxy={node_surface_proxy_count} | "
        f"support_depth={support_depth_score} | "
        f"coupling_depth={coupling_depth_score} | "
        f"support_families={support_family_count}"
        f"{'/' + str(support_family_required_count) if support_family_required_count else ''} | "
        f"proxy_families={proxy_family_count}"
        f"{'/' + str(proxy_family_required_count) if proxy_family_required_count else ''}"
    )
    return {
        "summary_line": compact_summary_line,
        "status": surface_status,
        "support_search_count": support_search_count,
        "node_surface_proxy_count": node_surface_proxy_count,
        "support_depth_score": support_depth_score,
        "coupling_depth_score": coupling_depth_score,
        "support_family_count": support_family_count,
        "proxy_family_count": proxy_family_count,
        "support_family_required_count": support_family_required_count,
        "proxy_family_required_count": proxy_family_required_count,
        "support_search_pass": bool(
            checks.get("support_search_surface_pass", surface.get("support_search_surface_pass", support_search_count > 0))
        ),
        "node_surface_proxy_pass": bool(
            checks.get(
                "node_to_surface_proxy_surface_pass",
                surface.get("node_to_surface_proxy_surface_pass", node_surface_proxy_count > 0),
            )
        ),
        "support_family_pass": bool(
            checks.get(
                "support_search_family_surface_pass",
                surface.get("support_search_family_surface_pass", support_family_count > 0),
            )
        ),
        "proxy_family_pass": bool(
            checks.get(
                "node_to_surface_proxy_family_surface_pass",
                surface.get("node_to_surface_proxy_family_surface_pass", proxy_family_count > 0),
            )
        ),
    }


def _ndtha_material_surface(ndtha_stress: dict) -> dict[str, Any]:
    material_rows = [
        row
        for row in (ndtha_stress.get("material_effect_rows") if isinstance(ndtha_stress.get("material_effect_rows"), list) else [])
        if isinstance(row, dict)
    ]
    summary = ndtha_stress.get("summary") if isinstance(ndtha_stress.get("summary"), dict) else {}
    checks = ndtha_stress.get("checks") if isinstance(ndtha_stress.get("checks"), dict) else {}
    material_model = str(summary.get("material_model", "") or "").strip()
    material_pass_count = sum(1 for row in material_rows if bool(row.get("material_model_pass", False)))
    material_pass = bool(checks.get("material_model_pass", bool(material_rows) and material_pass_count == len(material_rows)))
    summary_line = (
        f"NDTHA material: {'PASS' if material_pass else 'CHECK'} | "
        f"material_model={material_model or 'unknown'} | "
        f"material_effect_rows={len(material_rows)} | "
        f"material_model_pass={material_pass_count}/{len(material_rows)}"
    )
    return {
        "summary_line": summary_line,
        "material_depth": len(material_rows),
        "material_model": material_model,
        "material_pass": material_pass,
        "material_model_pass_count": material_pass_count,
    }


def _validate_inputs(strict: dict, rca: dict) -> tuple[bool, str]:
    if "strict_rust_hip_pass" not in strict:
        return False, "ERR_MISSING_STRICT_KEY"

    if "timing_breakdown_seconds" not in rca:
        return False, "ERR_MISSING_RCA_KEY"

    timing = rca.get("timing_breakdown_seconds")
    if not isinstance(timing, dict):
        return False, "ERR_MISSING_RCA_KEY"

    for key in ("compute", "host_copy", "serialization"):
        if key not in timing:
            return False, "ERR_MISSING_RCA_KEY"
        if not _is_finite_non_negative(timing[key]):
            return False, "ERR_INVALID_RCA_VALUE"

    return True, "PASS"


def _validate_contract_artifacts(paths: list[str]) -> tuple[bool, list[str]]:
    missing: list[str] = []
    for p in paths:
        fp = Path(p)
        if not fp.exists():
            missing.append(p)
            continue
        try:
            payload = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            missing.append(p)
            continue
        # contract report must explicitly contain pass boolean
        if not bool(payload.get("contract_pass", payload.get("layout_pass", False))):
            missing.append(p)
    return len(missing) == 0, missing




def _validate_priority3(path: str | None) -> tuple[bool, str | None, dict | None]:
    if not path:
        return True, None, None
    p = Path(path)
    if not p.exists():
        return False, "ERR_PRIORITY3_FAIL", None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return False, "ERR_PRIORITY3_FAIL", None
    allowed = {"PASS", "ERR_MODULE_FAIL", "ERR_METADATA_VERSION_MISMATCH"}
    if data.get("reason_code") not in allowed:
        return False, "ERR_PRIORITY3_FAIL", data
    if not bool(data.get("all_pass", False)):
        return False, "ERR_PRIORITY3_FAIL", data
    return True, None, data



def _load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_json_from_disk(path: str) -> dict:
    report_path = Path(path)
    if not report_path.is_absolute():
        candidate = Path(__file__).resolve().parents[2] / report_path
        if candidate.exists():
            report_path = candidate
    if not report_path.exists():
        return {}
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_optional_json(path: str) -> dict:
    report_path = Path(path)
    if not report_path.exists():
        return {}
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _pass(report: dict) -> bool:
    return bool(report.get("contract_pass", report.get("layout_pass", False)))


def _panel_zone_external_validation_surface(summary: dict[str, Any]) -> dict[str, Any]:
    advisory_only = bool(
        summary.get("panel_zone_external_validation_advisory_only", False)
        or (
            bool(summary.get("panel_zone_3d_clash_ready", False))
            and bool(summary.get("panel_zone_external_validation_pending", False))
            and str(summary.get("panel_zone_validation_boundary", "") or "") == "external_validation_only"
        )
    )
    release_blocking = bool(
        summary.get("panel_zone_external_validation_release_blocking", False)
        or (
            bool(summary.get("panel_zone_external_validation_pending", False))
            and not advisory_only
        )
    )
    status_label = str(summary.get("panel_zone_external_validation_status_label", "") or "").strip()
    if not status_label:
        if advisory_only:
            status_label = "advisory_only"
        elif release_blocking:
            status_label = "release_blocking"
        elif str(summary.get("panel_zone_validation_boundary", "") or "") == "solver_verified":
            status_label = "solver_verified"
        elif bool(summary.get("panel_zone_external_validation_pending", False)):
            status_label = "pending_external_validation"
        else:
            status_label = "not_applicable"
    return {
        "advisory_only": advisory_only,
        "release_blocking": release_blocking,
        "status_label": status_label,
    }


def _build_core_engine_surface_summary(
    *,
    nonlinear_engine_report: dict,
    nonlinear_engine_pass: bool,
    solver_breadth_report: dict,
    solver_breadth_pass: bool,
    element_material_breadth_report: dict,
    element_material_breadth_pass: bool,
    material_constitutive_report: dict,
    material_constitutive_pass: bool,
    steel_composite_constitutive_report: dict,
    steel_composite_constitutive_pass: bool,
    contact_readiness_pass: bool,
    structural_contact_pass: bool,
    general_fe_contact_matrix_report: dict,
    general_fe_contact_matrix_pass: bool,
    surface_interaction_benchmark_report: dict,
    surface_interaction_benchmark_pass: bool,
) -> tuple[dict[str, object], str]:
    nonlinear_summary = (
        nonlinear_engine_report.get("summary")
        if isinstance(nonlinear_engine_report.get("summary"), dict)
        else {}
    )
    nonlinear_runtime_truthfulness = (
        nonlinear_engine_report.get("runtime_truthfulness")
        if isinstance(nonlinear_engine_report.get("runtime_truthfulness"), dict)
        else {}
    )
    solver_summary = (
        solver_breadth_report.get("summary")
        if isinstance(solver_breadth_report.get("summary"), dict)
        else {}
    )
    element_summary = (
        element_material_breadth_report.get("summary")
        if isinstance(element_material_breadth_report.get("summary"), dict)
        else {}
    )
    material_summary = (
        material_constitutive_report.get("summary")
        if isinstance(material_constitutive_report.get("summary"), dict)
        else {}
    )
    steel_composite_summary = (
        steel_composite_constitutive_report.get("summary")
        if isinstance(steel_composite_constitutive_report.get("summary"), dict)
        else {}
    )
    steel_summary = (
        steel_composite_summary.get("steel")
        if isinstance(steel_composite_summary.get("steel"), dict)
        else {}
    )
    composite_summary = (
        steel_composite_summary.get("composite")
        if isinstance(steel_composite_summary.get("composite"), dict)
        else {}
    )
    general_fe_contact_summary = (
        general_fe_contact_matrix_report.get("summary")
        if isinstance(general_fe_contact_matrix_report.get("summary"), dict)
        else {}
    )
    surface_interaction_summary = (
        surface_interaction_benchmark_report.get("summary")
        if isinstance(surface_interaction_benchmark_report.get("summary"), dict)
        else {}
    )

    def _int_or_none(value: object) -> int | None:
        try:
            normalized = int(value)  # type: ignore[arg-type]
        except Exception:
            return None
        return normalized if normalized >= 0 else None

    def _float_or_none(value: object) -> float | None:
        try:
            normalized = float(value)
        except Exception:
            return None
        return normalized if math.isfinite(normalized) else None

    def _ratio_label(numerator: int | None, denominator: int | None) -> str:
        if numerator is None or denominator is None or denominator <= 0:
            return "n/a"
        return f"{numerator}/{denominator}"

    runtime_backends = [
        str(item).strip()
        for item in (nonlinear_summary.get("runtime_backends") or [])
        if str(item).strip()
    ]
    if not runtime_backends:
        runtime_backend = str(nonlinear_runtime_truthfulness.get("runtime_backend", "") or "").strip()
        if runtime_backend:
            runtime_backends = [runtime_backend]

    beam_case_count = _int_or_none(nonlinear_summary.get("case_count"))
    beam_drift_p95 = _float_or_none(nonlinear_summary.get("drift_error_pct_p95"))
    beam_top_disp_p95 = _float_or_none(nonlinear_summary.get("top_disp_error_pct_p95"))
    shell_element_count = _int_or_none(solver_summary.get("shell_element_count"))
    wall_case_count = _int_or_none(
        solver_summary.get("wall_frame_case_count", element_summary.get("wall_frame_case_count"))
    )
    wall_material_model = str(
        solver_summary.get("wall_material_model", element_summary.get("wall_material_model", "")) or "n/a"
    ).strip()
    rc_matrix_pass = _int_or_none(material_summary.get("calibration_matrix_pass_row_count"))
    rc_matrix_total = _int_or_none(material_summary.get("calibration_matrix_row_count"))
    steel_pass = _int_or_none(steel_summary.get("pass_count"))
    steel_total = _int_or_none(steel_summary.get("row_count"))
    composite_pass = _int_or_none(composite_summary.get("pass_count"))
    composite_total = _int_or_none(composite_summary.get("row_count"))
    direct_contact_ready = _int_or_none(general_fe_contact_summary.get("direct_structural_contact_ready_count"))
    direct_contact_total = _int_or_none(general_fe_contact_summary.get("direct_structural_contact_total_count"))
    general_fe_ready = _int_or_none(general_fe_contact_summary.get("ready_row_count"))
    general_fe_total = _int_or_none(general_fe_contact_summary.get("total_row_count"))
    surface_ready = _int_or_none(surface_interaction_summary.get("ready_row_count"))
    surface_total = _int_or_none(surface_interaction_summary.get("total_row_count"))

    beam_status_label = "yes" if nonlinear_engine_pass else "check"
    shell_wall_status_label = "yes" if solver_breadth_pass and element_material_breadth_pass else "check"
    constitutive_status_label = (
        "yes" if material_constitutive_pass and steel_composite_constitutive_pass else "check"
    )
    contact_axis_pass = bool(
        contact_readiness_pass
        and structural_contact_pass
        and general_fe_contact_matrix_pass
        and surface_interaction_benchmark_pass
    )
    contact_status_label = "yes" if contact_axis_pass else "check"
    core_engine_surface_pass = bool(
        nonlinear_engine_pass
        and solver_breadth_pass
        and element_material_breadth_pass
        and material_constitutive_pass
        and steel_composite_constitutive_pass
        and contact_axis_pass
    )
    summary = {
        "contract_pass": core_engine_surface_pass,
        "scope_label": "bounded_release_ci_surface",
        "beam_column_status_label": beam_status_label,
        "beam_column_case_count": beam_case_count,
        "beam_column_runtime_backend_label": ",".join(runtime_backends) if runtime_backends else "n/a",
        "beam_column_drift_error_pct_p95": beam_drift_p95,
        "beam_column_top_disp_error_pct_p95": beam_top_disp_p95,
        "shell_wall_status_label": shell_wall_status_label,
        "shell_element_count": shell_element_count,
        "wall_case_count": wall_case_count,
        "wall_material_model": wall_material_model or "n/a",
        "constitutive_status_label": constitutive_status_label,
        "rc_matrix_label": _ratio_label(rc_matrix_pass, rc_matrix_total),
        "steel_matrix_label": _ratio_label(steel_pass, steel_total),
        "composite_matrix_label": _ratio_label(composite_pass, composite_total),
        "contact_status_label": contact_status_label,
        "direct_contact_label": _ratio_label(direct_contact_ready, direct_contact_total),
        "general_fe_contact_label": _ratio_label(general_fe_ready, general_fe_total),
        "surface_interaction_label": _ratio_label(surface_ready, surface_total),
    }

    beam_segments = []
    if beam_case_count is not None:
        beam_segments.append(f"cases={beam_case_count}")
    if runtime_backends:
        beam_segments.append(f"backend={','.join(runtime_backends)}")
    if beam_drift_p95 is not None:
        beam_segments.append(f"drift_p95={beam_drift_p95:.2f}%")
    if beam_top_disp_p95 is not None:
        beam_segments.append(f"top_disp_p95={beam_top_disp_p95:.2f}%")

    shell_segments = []
    if shell_element_count is not None:
        shell_segments.append(f"shell={shell_element_count}")
    if wall_case_count is not None:
        shell_segments.append(f"wall_cases={wall_case_count}")
    if wall_material_model and wall_material_model != "n/a":
        shell_segments.append(f"material={wall_material_model}")

    constitutive_segments = [
        f"rc={_ratio_label(rc_matrix_pass, rc_matrix_total)}",
        f"steel={_ratio_label(steel_pass, steel_total)}",
        f"composite={_ratio_label(composite_pass, composite_total)}",
    ]
    contact_segments = [
        f"direct={_ratio_label(direct_contact_ready, direct_contact_total)}",
        f"general={_ratio_label(general_fe_ready, general_fe_total)}",
        f"surface={_ratio_label(surface_ready, surface_total)}",
    ]

    summary_line = (
        f"Core engine surface: {'PASS' if core_engine_surface_pass else 'CHECK'}"
        f" | beam_column={beam_status_label}({','.join(beam_segments) or 'n/a'})"
        f" | shell_wall={shell_wall_status_label}({','.join(shell_segments) or 'n/a'})"
        f" | constitutive={constitutive_status_label}({','.join(constitutive_segments)})"
        f" | contact={contact_status_label}({','.join(contact_segments)})"
        f" | scope=bounded_release_ci_surface"
    )
    return summary, summary_line


def _extract_midas_exact_roundtrip_closure_scope(report: dict) -> dict[str, object]:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    if not summary:
        return {}

    def _first_present(*keys: str) -> object | None:
        for key in keys:
            if key in summary:
                return summary.get(key)
        return None

    def _normalize_non_negative_int(value: object) -> int | None:
        try:
            normalized = int(value)  # type: ignore[arg-type]
        except Exception:
            return None
        return normalized if normalized >= 0 else None

    def _normalize_labels(value: object) -> list[str] | None:
        if not isinstance(value, list):
            return None
        labels: list[str] = []
        for item in value:
            label = str(item).strip()
            if label and label not in labels:
                labels.append(label)
        return labels or None

    def _normalize_label_counts(value: object) -> dict[str, int] | None:
        if not isinstance(value, dict):
            return None
        normalized: dict[str, int] = {}
        for raw_key, raw_value in value.items():
            label = str(raw_key).strip()
            count = _normalize_non_negative_int(raw_value)
            if label and count is not None:
                normalized[label] = count
        return dict(sorted(normalized.items())) or None

    scope_summary: dict[str, object] = {}

    eligible_exact_candidate_count = _normalize_non_negative_int(
        _first_present("eligible_exact_candidate_count", "eligible_exact_scope_case_count", "eligible_case_count")
    )
    if eligible_exact_candidate_count is not None:
        scope_summary["eligible_exact_candidate_count"] = eligible_exact_candidate_count

    eligible_exact_case_count = _normalize_non_negative_int(_first_present("eligible_exact_case_count"))
    if eligible_exact_case_count is not None:
        scope_summary["eligible_exact_case_count"] = eligible_exact_case_count

    eligible_exact_exclusion_case_count = _normalize_non_negative_int(
        _first_present(
            "eligible_exact_exclusion_case_count",
            "eligible_exact_excluded_case_count",
            "excluded_case_count",
            "exclusion_case_count",
        )
    )
    if eligible_exact_exclusion_case_count is not None:
        scope_summary["eligible_exact_exclusion_case_count"] = eligible_exact_exclusion_case_count

    eligible_exact_exclusion_labels = _normalize_labels(
        _first_present(
            "eligible_exact_exclusion_labels",
            "eligible_exact_excluded_labels",
            "excluded_case_labels",
            "exclusion_labels",
        )
    )
    if eligible_exact_exclusion_labels is not None:
        scope_summary["eligible_exact_exclusion_labels"] = eligible_exact_exclusion_labels

    eligible_exact_exclusion_label_counts = _normalize_label_counts(
        _first_present(
            "eligible_exact_exclusion_label_counts",
            "eligible_exact_excluded_label_counts",
            "excluded_label_counts",
            "exclusion_label_counts",
        )
    )
    if eligible_exact_exclusion_label_counts is not None:
        scope_summary["eligible_exact_exclusion_label_counts"] = eligible_exact_exclusion_label_counts

    return scope_summary


def _extract_load_combination_engine_summary(report: dict) -> dict[str, object]:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    if not report and not summary:
        return {}

    def _first_present(*keys: str) -> object | None:
        for key in keys:
            if key in summary:
                return summary.get(key)
        return None

    def _normalize_non_negative_int(value: object) -> int | None:
        try:
            normalized = int(value)  # type: ignore[arg-type]
        except Exception:
            return None
        return normalized if normalized >= 0 else None

    def _normalize_labels(value: object) -> list[str] | None:
        if not isinstance(value, list):
            return None
        labels: list[str] = []
        for item in value:
            label = str(item).strip()
            if label and label not in labels:
                labels.append(label)
        return labels or None

    summary_block: dict[str, object] = {}
    if "contract_pass" in report:
        summary_block["contract_pass"] = bool(report.get("contract_pass", False))
    reason_code = str(report.get("reason_code", "") or "").strip()
    if reason_code:
        summary_block["reason_code"] = reason_code

    for output_key, candidate_keys in (
        ("combination_count", ("combination_count", "load_combination_count", "combo_count", "total_combination_count")),
        ("case_count", ("case_count", "load_case_count", "pattern_count", "load_pattern_count")),
        ("exact_combination_count", ("exact_combination_count", "exact_combo_count", "exact_case_count")),
        ("pending_case_count", ("pending_case_count", "pending_review_total", "pending_candidate_count")),
        ("unsupported_case_count", ("unsupported_case_count", "unsupported_combination_count", "unsupported_combo_count")),
    ):
        normalized = _normalize_non_negative_int(_first_present(*candidate_keys))
        if normalized is not None:
            summary_block[output_key] = normalized

    remaining_limits = _normalize_labels(
        _first_present("remaining_limits", "blockers", "pending_limits", "remaining_blockers")
    )
    if remaining_limits is not None:
        summary_block["remaining_limits"] = remaining_limits

    return summary_block


def _format_load_combination_engine_summary_line(report: dict, summary_block: dict[str, object]) -> str:
    explicit_summary_line = str(report.get("summary_line", "") or "").strip()
    if explicit_summary_line:
        return explicit_summary_line
    if not report:
        return "Load combination engine gate: unavailable"

    status = "PASS" if bool(report.get("contract_pass", False)) else "CHECK"
    fragments: list[str] = []
    combination_count = summary_block.get("combination_count")
    case_count = summary_block.get("case_count")
    exact_combination_count = summary_block.get("exact_combination_count")
    pending_case_count = summary_block.get("pending_case_count")
    remaining_limits = summary_block.get("remaining_limits")

    if combination_count is not None:
        fragments.append(f"combos={int(combination_count)}")
    if case_count is not None:
        fragments.append(f"cases={int(case_count)}")
    if exact_combination_count is not None and combination_count is not None:
        fragments.append(f"exact={int(exact_combination_count)}/{int(combination_count)}")
    elif exact_combination_count is not None:
        fragments.append(f"exact={int(exact_combination_count)}")
    if pending_case_count is not None:
        fragments.append(f"pending={int(pending_case_count)}")
    if isinstance(remaining_limits, list):
        fragments.append(f"limits={'none' if not remaining_limits else ','.join(str(item) for item in remaining_limits)}")
    reason_code = str(summary_block.get("reason_code", "") or "").strip()
    if reason_code and reason_code not in {"PASS", "CHECK"}:
        fragments.append(f"reason={reason_code}")
    if not fragments:
        return f"Load combination engine gate: {status}"
    return f"Load combination engine gate: {status} | " + " | ".join(fragments)


def _run_midas_section_library_validator(validator_path: str, artifact_paths: list[str]) -> tuple[bool, dict]:
    normalized_artifacts = [str(Path(path)) for path in artifact_paths]
    cmd = [sys.executable, validator_path, "--require"]
    for artifact_path in normalized_artifacts:
        cmd.extend(["--path", artifact_path])
    details = {
        "command": cmd,
        "validator_path": validator_path,
        "checked": True,
        "artifact_paths": normalized_artifacts,
        "checked_artifact_count": len(normalized_artifacts),
        "missing_input_paths": [path for path in normalized_artifacts if not Path(path).exists()],
    }
    validator = Path(validator_path)
    if not validator.exists():
        details.update({
            "exit_code": None,
            "stdout": "",
            "stderr": f"validator missing: {validator_path}",
        })
        return False, details
    completed = subprocess.run(cmd, capture_output=True, text=True)
    stdout_lines = [line for line in completed.stdout.splitlines() if line.strip()]
    first_stdout_line = stdout_lines[0] if stdout_lines else ""
    if first_stdout_line.startswith("MIDAS section-library:"):
        summary_line = first_stdout_line
    elif first_stdout_line.startswith("ok |") or first_stdout_line.startswith("missing |"):
        summary_line = f"MIDAS section-library: {first_stdout_line}"
    else:
        summary_line = "MIDAS section-library: unavailable"
    details.update({
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "stdout_lines": stdout_lines,
        "stderr_lines": [line for line in completed.stderr.splitlines() if line.strip()],
        "summary_line": summary_line,
    })
    return completed.returncode == 0, details


def _run_midas_kds_geometry_bridge_validator(
    validator_path: str,
    artifact_paths: list[str],
    *,
    min_mapped_review_ids: int = 0,
) -> tuple[bool, dict]:
    normalized_artifacts = [str(Path(path)) for path in artifact_paths]
    base_cmd = [sys.executable, validator_path, "--require", "--min-mapped-review-ids", str(int(min_mapped_review_ids))]
    for artifact_path in normalized_artifacts:
        base_cmd.extend(["--path", artifact_path])
    details = {
        "command": list(base_cmd),
        "validator_path": validator_path,
        "checked": True,
        "artifact_paths": normalized_artifacts,
        "checked_artifact_count": len(normalized_artifacts),
        "missing_input_paths": [path for path in normalized_artifacts if not Path(path).exists()],
        "min_mapped_review_ids": int(min_mapped_review_ids),
    }
    validator = Path(validator_path)
    if not validator.exists():
        details.update({
            "exit_code": None,
            "stdout": "",
            "stderr": f"validator missing: {validator_path}",
        })
        return False, details
    structured_report: dict[str, object] = {}
    fallback_command: list[str] | None = None
    with tempfile.TemporaryDirectory(prefix="midas_kds_geometry_bridge_") as tmp_dir:
        out_path = Path(tmp_dir) / "midas_kds_geometry_bridge_validation_report.json"
        cmd = [*base_cmd, "--out", str(out_path)]
        completed = subprocess.run(cmd, capture_output=True, text=True)
        if out_path.exists():
            try:
                payload = json.loads(out_path.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
            if isinstance(payload, dict):
                structured_report = payload
        if (
            completed.returncode != 0
            and not structured_report
            and "--out" in str(completed.stderr or "")
        ):
            fallback_command = list(base_cmd)
            completed = subprocess.run(fallback_command, capture_output=True, text=True)

    stdout_lines = [line for line in completed.stdout.splitlines() if line.strip()]
    first_stdout_line = stdout_lines[0] if stdout_lines else ""
    if first_stdout_line.startswith("MIDAS kds-geometry-bridge:"):
        summary_line = first_stdout_line
    elif first_stdout_line.startswith("ok |") or first_stdout_line.startswith("missing |"):
        summary_line = f"MIDAS kds-geometry-bridge: {first_stdout_line}"
    else:
        summary_line = str(structured_report.get("summary_line", "") or "").strip()
    if not summary_line:
        summary_line = "MIDAS kds-geometry-bridge: unavailable"
    if structured_report:
        details.update(structured_report)
    details.update({
        "command": cmd if fallback_command is None else fallback_command,
        "command_with_out": cmd,
        "fallback_command": fallback_command,
        "structured_report_available": bool(structured_report),
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "stdout_lines": stdout_lines,
        "stderr_lines": [line for line in completed.stderr.splitlines() if line.strip()],
        "summary_line": summary_line,
    })
    return completed.returncode == 0, details


def _extract_ratio_status_surface(summary_line: str, label: str) -> dict[str, object]:
    text = str(summary_line or "").strip()
    match = re.search(rf"({re.escape(label)}=(\d+)/(\d+)\s+(PASS|CHECK))", text)
    if not match:
        return {
            "summary_line": "",
            "count": 0,
            "expected": 0,
            "status": "",
            "pass": None,
        }
    status = str(match.group(4))
    return {
        "summary_line": str(match.group(1)),
        "count": int(match.group(2)),
        "expected": int(match.group(3)),
        "status": status,
        "pass": status == "PASS",
    }


def _extract_midas_kds_geometry_ratio_surface(
    validation: dict[str, object],
    *,
    label: str,
    summary_count_key: str,
    summary_expected_key: str,
    check_key: str,
) -> dict[str, object]:
    summary = validation.get("summary") if isinstance(validation.get("summary"), dict) else {}
    checks = validation.get("checks") if isinstance(validation.get("checks"), dict) else {}
    raw_count = summary.get(summary_count_key)
    raw_expected = summary.get(summary_expected_key)
    if raw_count is not None and raw_expected is not None:
        try:
            count = int(raw_count)
            expected = int(raw_expected)
        except Exception:
            count = expected = None
        if count is not None and expected is not None:
            check_value = checks.get(check_key)
            if isinstance(check_value, bool):
                status = "PASS" if check_value else "CHECK"
                pass_value: bool | None = check_value
            else:
                status = "PASS" if expected == 0 or count >= expected else "CHECK"
                pass_value = status == "PASS"
            return {
                "summary_line": f"{label}={count}/{expected} {status}",
                "count": count,
                "expected": expected,
                "status": status,
                "pass": pass_value,
            }
    return _extract_ratio_status_surface(str(validation.get("summary_line", "") or ""), label)


def _run_midas_loadcomb_roundtrip_validator(validator_path: str, artifact_paths: list[str]) -> tuple[bool, dict]:
    normalized_artifacts = [str(Path(path)) for path in artifact_paths]
    details = {
        "validator_path": validator_path,
        "checked": True,
        "artifact_paths": normalized_artifacts,
        "checked_artifact_count": len(normalized_artifacts),
        "missing_input_paths": [path for path in normalized_artifacts if not Path(path).exists()],
        "results": [],
    }
    validator = Path(validator_path)
    if not validator.exists():
        details.update({
            "stdout": "",
            "stderr": f"validator missing: {validator_path}",
            "summary_line": "MIDAS loadcomb-roundtrip: unavailable",
        })
        return False, details

    all_ok = True
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    with tempfile.TemporaryDirectory(prefix="midas_loadcomb_roundtrip_") as tmp_dir:
        tmp_root = Path(tmp_dir)
        for index, artifact_path in enumerate(normalized_artifacts):
            out_path = tmp_root / f"roundtrip_{index}.json"
            cmd = [
                sys.executable,
                validator_path,
                "--model-json",
                artifact_path,
                "--out",
                str(out_path),
            ]
            completed = subprocess.run(cmd, capture_output=True, text=True)
            stdout_lines.extend([line for line in completed.stdout.splitlines() if line.strip()])
            stderr_lines.extend([line for line in completed.stderr.splitlines() if line.strip()])
            report = {}
            if out_path.exists():
                try:
                    report = json.loads(out_path.read_text(encoding="utf-8"))
                except Exception:
                    report = {}
            result_row = {
                "artifact_path": artifact_path,
                "command": cmd,
                "exit_code": completed.returncode,
                "report": report,
                "pass": bool(completed.returncode == 0 and report.get("pass", False)),
                "exact_entry_row_coverage": float((report or {}).get("exact_entry_row_coverage", 0.0) or 0.0),
                "exact_header_coverage": float((report or {}).get("exact_header_coverage", 0.0) or 0.0),
                "recovery_mode": str((report or {}).get("recovery_mode", "") or ""),
                "missing_combo_count": int(len((report or {}).get("missing_combo_names", []) or [])),
                "extra_combo_count": int(len((report or {}).get("extra_combo_names", []) or [])),
            }
            details["results"].append(result_row)
            all_ok = bool(all_ok and result_row["pass"])
    coverage_preview = ", ".join(
        f"{Path(str(row.get('artifact_path', ''))).name}={float(row.get('exact_entry_row_coverage', 0.0) or 0.0):.2f}"
        for row in details["results"][:3]
    ) or "n/a"
    summary_line = (
        f"MIDAS loadcomb-roundtrip: {'ok' if all_ok else 'check'} | entry_row_coverage={coverage_preview} | "
        f"artifacts={len(details['results'])}"
    )
    details.update({
        "stdout_lines": stdout_lines,
        "stderr_lines": stderr_lines,
        "stdout": "\n".join(stdout_lines),
        "stderr": "\n".join(stderr_lines),
        "summary_line": summary_line,
    })
    return all_ok, details


def _validate_extended_contracts(
    physics_path: str,
    meta_path: str,
    buckling_path: str,
    benchmark_path: str,
    branching_path: str,
    bifurcation_path: str,
    rust_onnx_path: str,
    winning_ticket_path: str,
    rust_md3bead_parity_path: str,
    lj_mapping_path: str,
    dynamic_time_history_path: str,
    cache_profile_path: str,
    p0_engine_perf_path: str,
    p0_core_gap_path: str,
    noise_stress_path: str,
    scaleout_io_path: str,
    phasea_contract_path: str,
    phaseb_track_lf_path: str,
    phaseb_moving_load_path: str,
    phaseb_vti_path: str,
    phaseb_irregularity_path: str,
    phaseb_summary_path: str,
    phased_track_dataset_path: str,
    phased_tunnel_dataset_path: str,
    phased_attention_path: str,
    phased_tgnn_path: str,
    phased_summary_path: str,
    phasee_substructuring_path: str,
    phasee_attenuation_path: str,
    phasee_compliance_path: str,
    phasee_whitebox_path: str,
    phasee_summary_path: str,
    phasef_l3_path: str,
    phasef_phase_correction_path: str,
    phasef_soil_ood_path: str,
    phasef_summary_path: str,
) -> tuple[bool, bool, bool, bool, bool, bool, bool, bool, bool, bool, bool, bool, bool, bool, bool, bool, bool, bool, bool, bool, bool]:
    physics = _load_json(physics_path)
    meta = _load_json(meta_path)
    buckling = _load_json(buckling_path)
    benchmark = _load_json(benchmark_path)
    branching = _load_json(branching_path)
    bifurcation = _load_json(bifurcation_path)
    rust_onnx = _load_json(rust_onnx_path)
    winning_ticket = _load_json(winning_ticket_path)
    rust_parity = _load_json(rust_md3bead_parity_path)
    lj_mapping = _load_json(lj_mapping_path)
    dynamic_time_history = _load_json(dynamic_time_history_path)
    cache_profile = _load_json(cache_profile_path)
    p0_engine_perf = _load_json(p0_engine_perf_path)
    p0_core_gap = _load_json(p0_core_gap_path)
    noise_stress = _load_json(noise_stress_path)
    scaleout_io = _load_json(scaleout_io_path)
    phasea_contract = _load_json(phasea_contract_path)
    phaseb_track_lf = _load_json(phaseb_track_lf_path)
    phaseb_moving_load = _load_json(phaseb_moving_load_path)
    phaseb_vti = _load_json(phaseb_vti_path)
    phaseb_irregularity = _load_json(phaseb_irregularity_path)
    phaseb_summary = _load_json(phaseb_summary_path)
    phased_track_dataset = _load_json(phased_track_dataset_path)
    phased_tunnel_dataset = _load_json(phased_tunnel_dataset_path)
    phased_attention = _load_json(phased_attention_path)
    phased_tgnn = _load_json(phased_tgnn_path)
    phased_summary = _load_json(phased_summary_path)
    phasee_substructuring = _load_json(phasee_substructuring_path)
    phasee_attenuation = _load_json(phasee_attenuation_path)
    phasee_compliance = _load_json(phasee_compliance_path)
    phasee_whitebox = _load_json(phasee_whitebox_path)
    phasee_summary = _load_json(phasee_summary_path)
    phasef_l3 = _load_json(phasef_l3_path)
    phasef_phase = _load_json(phasef_phase_correction_path)
    phasef_soil_ood = _load_json(phasef_soil_ood_path)
    phasef_summary = _load_json(phasef_summary_path)

    energy_ok = bool(physics.get("checks", {}).get("energy_monotonicity_pass", False))
    meta_ood_ok = bool(meta.get("meta_ood_generalization_pass", False))
    buckling_ok = bool(buckling.get("contract_pass", False)) and float(buckling.get("critical_load_factor", 0.0)) > 0.0
    benchmark_ok = bool(benchmark.get("contract_pass", False)) and bool(benchmark.get("kpi_pass", False))
    branching_ok = bool(branching.get("contract_pass", False)) and not bool(branching.get("uses_backprop", True))
    bifurcation_ok = bool(bifurcation.get("contract_pass", False)) and isinstance(bifurcation.get("trigger", {}).get("triggered"), bool)
    rust_onnx_ok = bool(rust_onnx.get("contract_pass", False))
    sel = winning_ticket.get("selection", {})
    tb = winning_ticket.get("targeted_backprop", {})
    top_k = int(sel.get("top_k", 0))
    winning_ticket_ok = (
        bool(winning_ticket.get("contract_pass", False))
        and bool(winning_ticket.get("uses_backprop", False))
        and str(sel.get("strategy", "")) == "topk_weighted_backprop"
        and top_k >= 2
        and bool(tb.get("weighted_aggregation", False))
        and int(tb.get("graph_count", 0)) == top_k
    )
    rust_md3bead_parity_ok = bool(rust_parity.get("contract_pass", False))
    lj_mapping_ok = bool(lj_mapping.get("contract_pass", False))
    dynamic_time_history_ok = bool(dynamic_time_history.get("contract_pass", False)) and bool(dynamic_time_history.get("checks", {}).get("newmark_stability_pass", False))
    cache_profile_ok = bool(cache_profile.get("contract_pass", False)) and bool(cache_profile.get("checks", {}).get("microbatch_available", False))
    p0_engine_perf_ok = bool(p0_engine_perf.get("contract_pass", False)) and all(
        bool((p0_engine_perf.get("checks") or {}).get(key, False))
        for key in (
            "probe_pass",
            "track_rust_pass",
            "track_python_pass",
            "has_performance_fields",
            "speedup_pass",
        )
    )
    p0_core_gap_ok = bool(p0_core_gap.get("contract_pass", False)) and all(
        bool((p0_core_gap.get("checks") or {}).get(key, False))
        for key in (
            "p0_1_rust_engine_pass",
            "p0_1_engine_profile_pass",
            "p0_2_public_benchmark_pass",
        )
    )
    noise_stress_ok = bool(noise_stress.get("contract_pass", False)) and all(
        bool((noise_stress.get("checks") or {}).get(key, False))
        for key in ("has_required_case_count", "noise_sweep_complete", "finite_metrics")
    )
    scaleout_io_ok = bool(scaleout_io.get("contract_pass", False)) and all(
        bool((scaleout_io.get("checks") or {}).get(key, False))
        for key in ("probe_pass", "rust_hip_cmd_policy_pass", "profile_scenarios_present", "has_1m_plus", "scaleout_1m_microbatch_pass")
    )
    phasea_contract_ok = bool(phasea_contract.get("contract_pass", False))

    b1_ok = bool(phaseb_track_lf.get("contract_pass", False)) and bool(phaseb_track_lf.get("checks", {}).get("accuracy_pass", False))
    b2_ok = bool(phaseb_moving_load.get("contract_pass", False)) and bool(phaseb_moving_load.get("checks", {}).get("equilibrium_residual_pass", False))
    b3_ok = (
        bool(phaseb_vti.get("contract_pass", False))
        and bool(phaseb_vti.get("checks", {}).get("coupling_converged_ratio_pass", False))
        and bool(phaseb_vti.get("checks", {}).get("dynamic_disp_pass", False))
        and bool(phaseb_vti.get("checks", {}).get("adaptive_newton_converged_pass", False))
    )
    b4_ok = bool(phaseb_irregularity.get("contract_pass", False))
    bsum_ok = bool(phaseb_summary.get("contract_pass", False))
    phaseb_track_ok = bool(b1_ok and b2_ok and b3_ok and b4_ok and bsum_ok)

    d1_ok = bool(phased_track_dataset.get("contract_pass", False)) and bool(phased_track_dataset.get("checks", {}).get("equilibrium_residual_pass", False))
    d2_ok = bool(phased_tunnel_dataset.get("contract_pass", False)) and bool(phased_tunnel_dataset.get("checks", {}).get("equilibrium_residual_pass", False))
    d4_ok = bool(phased_attention.get("contract_pass", False)) and bool(phased_attention.get("checks", {}).get("speed_scaling_monotonic", False))
    d3_ok = (
        bool(phased_tgnn.get("contract_pass", False))
        and bool(phased_tgnn.get("domain_checks", {}).get("overall_val_gate_pass", False))
        and bool(phased_tgnn.get("domain_checks", {}).get("track_val_gate_pass", True))
        and bool(phased_tgnn.get("domain_checks", {}).get("tunnel_val_gate_pass", True))
        and bool(phased_tgnn.get("domain_checks", {}).get("rollout_val_gate_pass", True))
        and float((phased_tgnn.get("inputs") or {}).get("max_val_mae_pct", 999.0)) <= 5.0
        and float((phased_tgnn.get("inputs") or {}).get("max_val_mae_pct_track", 999.0)) <= 5.0
        and float((phased_tgnn.get("inputs") or {}).get("max_val_mae_pct_tunnel", 999.0)) <= 5.0
        and float((phased_tgnn.get("validation_metrics") or {}).get("mae_pct", 999.0)) <= 5.0
        and not bool((phased_tgnn.get("runtime") or {}).get("cpu_fallback_used", False))
        and (
            float((phased_tgnn.get("validation_track_metrics") or {}).get("mae_pct", 0.0)) <= 5.0
            if int((phased_tgnn.get("validation_track_metrics") or {}).get("case_count", 0)) > 0
            else True
        )
        and (
            float((phased_tgnn.get("validation_tunnel_metrics") or {}).get("mae_pct", 0.0)) <= 5.0
            if int((phased_tgnn.get("validation_tunnel_metrics") or {}).get("case_count", 0)) > 0
            else True
        )
    )
    dsum_ok = bool(phased_summary.get("contract_pass", False))
    phased_multidomain_ok = bool(d1_ok and d2_ok and d3_ok and d4_ok and dsum_ok)

    e1_ok = bool(phasee_substructuring.get("contract_pass", False)) and bool(phasee_substructuring.get("checks", {}).get("interface_dof_match", False))
    e2_ok = bool(phasee_attenuation.get("contract_pass", False)) and bool(phasee_attenuation.get("checks", {}).get("monotonic_distance_decay", False))
    e3_ok = bool(phasee_compliance.get("contract_pass", False)) and bool(phasee_compliance.get("checks", {}).get("compliance_ratio_pass", False))
    e5_ok = bool(phasee_whitebox.get("contract_pass", phasee_whitebox.get("summary", {}).get("pass", False)))
    esum_ok = bool(phasee_summary.get("contract_pass", False))
    phasee_integrated_ok = bool(e1_ok and e2_ok and e3_ok and e5_ok and esum_ok)

    f1_ok = bool(phasef_l3.get("contract_pass", False)) and bool(phasef_l3.get("checks", {}).get("has_cache_safe_chunk", False))
    f2_ok = bool(phasef_phase.get("contract_pass", False)) and bool(phasef_phase.get("checks", {}).get("phase_error_below_threshold", False))
    f3_ok = bool(phasef_soil_ood.get("contract_pass", False)) and bool(phasef_soil_ood.get("checks", {}).get("false_negative_gate_pass", False))
    fsum_ok = bool(phasef_summary.get("contract_pass", False))
    phasef_resilience_ok = bool(f1_ok and f2_ok and f3_ok and fsum_ok)

    return energy_ok, meta_ood_ok, buckling_ok, benchmark_ok, branching_ok, bifurcation_ok, rust_onnx_ok, winning_ticket_ok, rust_md3bead_parity_ok, lj_mapping_ok, dynamic_time_history_ok, cache_profile_ok, p0_engine_perf_ok, p0_core_gap_ok, noise_stress_ok, scaleout_io_ok, phasea_contract_ok, phaseb_track_ok, phased_multidomain_ok, phasee_integrated_ok, phasef_resilience_ok


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--strict-probe", default="implementation/phase1/zero_copy_real_probe_report_strict.json")
    p.add_argument("--rca", default="implementation/phase1/step_outputs/step5_rca_summary.json")
    p.add_argument("--max-host-copy-share", type=float, default=0.2)
    p.add_argument("--out", default="implementation/phase1/ci_gate_report.json")
    p.add_argument("--manifest", default="implementation/phase1/ci_artifact_manifest.json")
    p.add_argument("--priority3", default=None, help="optional priority3 summary path")
    p.add_argument("--physics-residual", default="implementation/phase1/physics_residual_contract_report.json")
    p.add_argument("--meta-learning", default="implementation/phase1/meta_learning_task_report.json")
    p.add_argument("--buckling", default="implementation/phase1/buckling_contract_report.json")
    p.add_argument("--benchmark", default="implementation/phase1/hf_benchmark_report.json")
    p.add_argument("--branching", default="implementation/phase1/physics_branching_report.json")
    p.add_argument("--bifurcation", default="implementation/phase1/bifurcation_detector_report.json")
    p.add_argument("--rust-onnx", default="implementation/phase1/rust_onnx_native_contract_report.json")
    p.add_argument("--winning-ticket", default="implementation/phase1/winning_ticket_backprop_report.json")
    p.add_argument("--rust-md3bead-parity", default="implementation/phase1/rust_md3bead_parity_report.json")
    p.add_argument("--lj-mapping", default="implementation/phase1/nonlinear_lj_mapping_report.json")
    p.add_argument("--dynamic-time-history", default="implementation/phase1/dynamic_time_history_report.json")
    p.add_argument("--cache-profile", default="implementation/phase1/branch64_microbatch_profile_report.json")
    p.add_argument("--p0-engine-perf", default="implementation/phase1/p0_engine_perf_report.json")
    p.add_argument("--p0-core-gap", default="implementation/phase1/p0_core_gap_report.json")
    p.add_argument("--hip-kernel-smoke", default="implementation/phase1/hip_kernel_smoke_report.json")
    p.add_argument("--require-hip-kernel-smoke", action="store_true")
    p.add_argument("--noise-stress", default="implementation/phase1/noise_sensitivity_stress_report.json")
    p.add_argument("--scaleout-io", default="implementation/phase1/scaleout_io_profile_report.json")
    p.add_argument("--nightly-10m-repro", default="implementation/phase1/nightly_10m_repro_report.json")
    p.add_argument("--ndtha-long-profile", default="implementation/phase1/ndtha_long_profile_report.json")
    p.add_argument("--require-ndtha-long-profile", action="store_true")
    p.add_argument("--phase3-pipeline", default="implementation/phase1/phase3_megastructure_pipeline_report.json")
    p.add_argument("--topology-gate", default="implementation/phase1/opensees_topology_report.json")
    p.add_argument("--partitioned-scaleout", default="implementation/phase1/partitioned_scaleout_report.json")
    p.add_argument("--sync-stress", default="implementation/phase1/sync_stress_gate_report.json")
    p.add_argument("--noise-convergence", default="implementation/phase1/noise_convergence_gate_report.json")
    p.add_argument("--commercial-csv-gate", default="implementation/phase1/commercial_csv_gate_report.json")
    p.add_argument("--commercial-readiness", default="implementation/phase1/commercial_readiness_report.json")
    p.add_argument("--solver-breadth-report", default="implementation/phase1/solver_breadth_report.json")
    p.add_argument("--element-material-breadth-report", default="implementation/phase1/element_material_breadth_gate_report.json")
    p.add_argument("--material-constitutive-report", default="implementation/phase1/material_constitutive_gate_report.json")
    p.add_argument(
        "--steel-composite-constitutive-gate-report",
        default="implementation/phase1/steel_composite_constitutive_gate_report.json",
    )
    p.add_argument(
        "--midas-kds-row-provenance-export-report",
        default="implementation/phase1/release/kds_compliance/midas_kds_row_provenance_table_report.json",
    )
    p.add_argument("--contact-readiness-report", default="implementation/phase1/contact_readiness_report.json")
    p.add_argument("--structural-contact-report", default="implementation/phase1/structural_contact_gate_report.json")
    p.add_argument("--general-fe-contact-benchmark-report", default="implementation/phase1/general_fe_contact_benchmark_gate_report.json")
    p.add_argument("--surface-interaction-benchmark-report", default="implementation/phase1/surface_interaction_benchmark_gate_report.json")
    p.add_argument("--foundation-soil-link-report", default="implementation/phase1/foundation_soil_link_gate_report.json")
    p.add_argument("--panel-zone-clash-report", default="implementation/phase1/panel_zone_clash_report.json")
    p.add_argument("--require-structural-contact", action="store_true")
    p.add_argument("--midas-interoperability-report", default="implementation/phase1/midas_interoperability_gate_report.json")
    p.add_argument("--korean-source-ingest-gate-report", default="implementation/phase1/korean_source_ingest_gate_report.json")
    p.add_argument("--midas-native-roundtrip-report", default="implementation/phase1/midas_native_roundtrip_gate_report.json")
    p.add_argument(
        "--midas-exact-roundtrip-closure-report",
        default="implementation/phase1/midas_exact_roundtrip_closure_gate_report.json",
    )
    p.add_argument(
        "--load-combination-engine-gate-report",
        default="implementation/phase1/load_combination_engine_gate_report.json",
    )
    p.add_argument(
        "--irregular-structure-collection-gate-report",
        default="implementation/phase1/irregular_structure_collection_gate_report.json",
    )
    p.add_argument(
        "--irregular-top5-execution-manifest",
        default="implementation/phase1/open_data/irregular/irregular_top5_execution_manifest.json",
    )
    p.add_argument("--nonlinear-generalization-report", default="implementation/phase1/nonlinear_generalization_gate_report.json")
    p.add_argument("--workflow-productization-report", default="implementation/phase1/workflow_productization_gate_report.json")
    p.add_argument("--real-source-multi", default="implementation/phase1/real_source_multi_gate_report.json")
    p.add_argument("--nonlinear-engine-report", default="implementation/phase1/nonlinear_frame_engine_report.json")
    p.add_argument("--pushover-stress-report", default="implementation/phase1/nonlinear_pushover_stress_report.json")
    p.add_argument("--ndtha-stress-report", default="implementation/phase1/nonlinear_ndtha_stress_report.json")
    p.add_argument("--ndtha-residual-gate-report", default="implementation/phase1/ndtha_residual_gate_report.json")
    p.add_argument("--pbd-review-package", default="implementation/phase1/release/pbd_review/pbd_review_package_report.json")
    p.add_argument("--global-authority-gate", default="implementation/phase1/global_authority_gate_report.json")
    p.add_argument("--wind-benchmark-report", default="implementation/phase1/wind_time_history_gate_report.json")
    p.add_argument("--ssi-boundary-report", default="implementation/phase1/ssi_boundary_gate_report.json")
    p.add_argument("--damper-validation-report", default="implementation/phase1/damper_validation_gate_report.json")
    p.add_argument("--kds-compliance-summary", default="implementation/phase1/release/kds_compliance/kds_compliance_summary.json")
    p.add_argument("--construction-sequence-report", default="implementation/phase1/construction_sequence_gate_report.json")
    p.add_argument("--flexible-diaphragm-report", default="implementation/phase1/flexible_diaphragm_gate_report.json")
    p.add_argument("--repro-version-lock-report", default="implementation/phase1/reproducibility_version_lock_report.json")
    p.add_argument("--release-registry-report", default="implementation/phase1/release/release_registry.json")
    p.add_argument("--performance-profiling-report", default="implementation/phase1/performance_profiling_gate_report.json")
    p.add_argument("--solver-hip-e2e", default="implementation/phase1/solver_hip_e2e_contract_report.json")
    p.add_argument("--require-solver-hip-e2e", action="store_true")
    p.add_argument("--solver-truthfulness", default="implementation/phase1/solver_truthfulness_gate_report.json")
    p.add_argument(
        "--hardest-external-10case-kickoff-report",
        default="implementation/phase1/hardest_external_10case_kickoff_gate_report.json",
    )
    p.add_argument("--rc-benchmark-lock", default="implementation/phase1/rc_benchmark_lock_report.json")
    p.add_argument("--midas-mgt-conversion", default="implementation/phase1/midas_mgt_conversion_report.json")
    p.add_argument("--midas-section-library-validator", default="implementation/phase1/validate_midas_section_library_artifacts.py")
    p.add_argument(
        "--midas-section-library-artifact",
        dest="midas_section_library_artifacts",
        action="append",
        default=None,
        help="canonical MIDAS model JSON to validate for embedded section_library metadata; can be passed multiple times",
    )
    p.add_argument("--midas-kds-geometry-bridge-validator", default="implementation/phase1/validate_midas_kds_geometry_bridge_artifacts.py")
    p.add_argument(
        "--midas-kds-geometry-bridge-artifact",
        dest="midas_kds_geometry_bridge_artifacts",
        action="append",
        default=None,
        help="canonical MIDAS model JSON to validate for embedded kds_geometry_bridge metadata; can be passed multiple times",
    )
    p.add_argument(
        "--midas-kds-geometry-bridge-min-mapped-review-ids",
        type=int,
        default=0,
        help="minimum mapped review-id count required by the MIDAS kds_geometry_bridge validator; defaults to 0 to track coverage without forcing non-zero mapping yet",
    )
    p.add_argument("--midas-loadcomb-roundtrip-validator", default="implementation/phase1/compare_midas_loadcomb_roundtrip.py")
    p.add_argument(
        "--midas-loadcomb-roundtrip-artifact",
        dest="midas_loadcomb_roundtrip_artifacts",
        action="append",
        default=None,
        help="canonical MIDAS model JSON to validate for LOADCOMB round-trip fidelity; can be passed multiple times",
    )
    p.add_argument("--ci-mode", choices=["pr", "nightly"], default="pr")
    p.add_argument("--require-gpu-strict", action="store_true")
    p.add_argument("--phasea-contract", default="implementation/phase1/phasea_contract_report.json")
    p.add_argument("--phaseb-track-lf", default="implementation/phase1/track_lf_solver_report.json")
    p.add_argument("--phaseb-moving-load", default="implementation/phase1/moving_load_integrator_report.json")
    p.add_argument("--phaseb-vti", default="implementation/phase1/vti_coupled_solver_report.json")
    p.add_argument("--phaseb-irregularity", default="implementation/phase1/track_irregularity_report.json")
    p.add_argument("--phaseb-summary", default="implementation/phase1/phaseb_track_summary_report.json")
    p.add_argument("--phased-track-dataset", default="implementation/phase1/track_dynamics_dataset_report.json")
    p.add_argument("--phased-tunnel-dataset", default="implementation/phase1/tunnel_dynamics_dataset_report.json")
    p.add_argument("--phased-attention", default="implementation/phase1/moving_load_attention_report.json")
    p.add_argument("--phased-tgnn", default="implementation/phase1/tgnn_multidomain_report.json")
    p.add_argument("--phased-summary", default="implementation/phase1/phased_multidomain_summary_report.json")
    p.add_argument("--phasee-substructuring", default="implementation/phase1/substructuring_interface_report.json")
    p.add_argument("--phasee-attenuation", default="implementation/phase1/vibration_attenuation_report.json")
    p.add_argument("--phasee-compliance", default="implementation/phase1/vibration_compliance_report.json")
    p.add_argument("--phasee-whitebox", default="implementation/phase1/whitebox_validation_report.json")
    p.add_argument("--phasee-summary", default="implementation/phase1/phasee_integrated_summary_report.json")
    p.add_argument("--phasef-l3", default="implementation/phase1/multiscale_l3_streaming_report.json")
    p.add_argument("--phasef-phase-correction", default="implementation/phase1/phase_correction_assimilation_report.json")
    p.add_argument("--phasef-soil-ood", default="implementation/phase1/heterogeneous_soil_ood_report.json")
    p.add_argument("--phasef-summary", default="implementation/phase1/phasef_resilience_summary_report.json")
    p.add_argument(
        "--required-contracts",
        nargs="*",
        default=[
            "implementation/phase1/dynamics_boundary_report.json",
            "implementation/phase1/pg_gat_contract_report.json",
            "implementation/phase1/subgraph_projection_report.json",
            "implementation/phase1/soa_dlpack_contract_report.json",
            "implementation/phase1/physics_residual_contract_report.json",
            "implementation/phase1/meta_learning_task_report.json",
            "implementation/phase1/buckling_contract_report.json",
            "implementation/phase1/hf_benchmark_report.json",
            "implementation/phase1/physics_branching_report.json",
            "implementation/phase1/bifurcation_detector_report.json",
            "implementation/phase1/rust_onnx_native_contract_report.json",
            "implementation/phase1/winning_ticket_backprop_report.json",
            "implementation/phase1/rust_md3bead_parity_report.json",
            "implementation/phase1/nonlinear_lj_mapping_report.json",
            "implementation/phase1/dynamic_time_history_report.json",
            "implementation/phase1/branch64_microbatch_profile_report.json",
            "implementation/phase1/p0_engine_perf_report.json",
            "implementation/phase1/p0_core_gap_report.json",
            "implementation/phase1/noise_sensitivity_stress_report.json",
            "implementation/phase1/scaleout_io_profile_report.json",
            "implementation/phase1/nightly_10m_repro_report.json",
            "implementation/phase1/phase3_megastructure_pipeline_report.json",
            "implementation/phase1/opensees_topology_report.json",
            "implementation/phase1/partitioned_scaleout_report.json",
            "implementation/phase1/sync_stress_gate_report.json",
            "implementation/phase1/noise_convergence_gate_report.json",
            "implementation/phase1/commercial_csv_gate_report.json",
            "implementation/phase1/commercial_readiness_report.json",
            "implementation/phase1/nonlinear_generalization_gate_report.json",
            "implementation/phase1/workflow_productization_gate_report.json",
            "implementation/phase1/real_source_multi_gate_report.json",
            "implementation/phase1/nonlinear_frame_engine_report.json",
            "implementation/phase1/nonlinear_pushover_stress_report.json",
            "implementation/phase1/nonlinear_ndtha_stress_report.json",
            "implementation/phase1/ndtha_residual_gate_report.json",
            "implementation/phase1/release/pbd_review/pbd_review_package_report.json",
            "implementation/phase1/global_authority_gate_report.json",
            "implementation/phase1/wind_time_history_gate_report.json",
            "implementation/phase1/ssi_boundary_gate_report.json",
            "implementation/phase1/damper_validation_gate_report.json",
            "implementation/phase1/release/kds_compliance/kds_compliance_summary.json",
            "implementation/phase1/construction_sequence_gate_report.json",
            "implementation/phase1/flexible_diaphragm_gate_report.json",
            "implementation/phase1/reproducibility_version_lock_report.json",
            "implementation/phase1/release/release_registry.json",
            "implementation/phase1/solver_truthfulness_gate_report.json",
            "implementation/phase1/hardest_external_10case_kickoff_gate_report.json",
            "implementation/phase1/midas_mgt_conversion_report.json",
            "implementation/phase1/phasea_contract_report.json",
            "implementation/phase1/track_lf_solver_report.json",
            "implementation/phase1/moving_load_integrator_report.json",
            "implementation/phase1/vti_coupled_solver_report.json",
            "implementation/phase1/track_irregularity_report.json",
            "implementation/phase1/phaseb_track_summary_report.json",
            "implementation/phase1/track_dynamics_dataset_report.json",
            "implementation/phase1/tunnel_dynamics_dataset_report.json",
            "implementation/phase1/moving_load_attention_report.json",
            "implementation/phase1/tgnn_multidomain_report.json",
            "implementation/phase1/phased_multidomain_summary_report.json",
            "implementation/phase1/substructuring_interface_report.json",
            "implementation/phase1/vibration_attenuation_report.json",
            "implementation/phase1/vibration_compliance_report.json",
            "implementation/phase1/whitebox_validation_report.json",
            "implementation/phase1/phasee_integrated_summary_report.json",
            "implementation/phase1/multiscale_l3_streaming_report.json",
            "implementation/phase1/phase_correction_assimilation_report.json",
            "implementation/phase1/heterogeneous_soil_ood_report.json",
            "implementation/phase1/phasef_resilience_summary_report.json",
        ],
        help="additional static contract artifacts required by gate",
    )
    args = p.parse_args(argv)

    strict = json.loads(Path(args.strict_probe).read_text(encoding="utf-8"))
    rca = json.loads(Path(args.rca).read_text(encoding="utf-8"))

    midas_section_library_targets = list(args.midas_section_library_artifacts or DEFAULT_MIDAS_SECTION_LIBRARY_ARTIFACTS)
    midas_section_library_ok, midas_section_library_validation = _run_midas_section_library_validator(
        args.midas_section_library_validator,
        midas_section_library_targets,
    )
    midas_kds_geometry_bridge_targets = list(
        args.midas_kds_geometry_bridge_artifacts or DEFAULT_MIDAS_KDS_GEOMETRY_BRIDGE_ARTIFACTS
    )
    midas_kds_geometry_bridge_ok, midas_kds_geometry_bridge_validation = _run_midas_kds_geometry_bridge_validator(
        args.midas_kds_geometry_bridge_validator,
        midas_kds_geometry_bridge_targets,
        min_mapped_review_ids=args.midas_kds_geometry_bridge_min_mapped_review_ids,
    )
    midas_kds_geometry_bridge_load_crosswalk_surface = _extract_midas_kds_geometry_ratio_surface(
        midas_kds_geometry_bridge_validation,
        label="load_crosswalk",
        summary_count_key="exact_review_load_crosswalk_count_total",
        summary_expected_key="exact_review_load_crosswalk_expected_total",
        check_key="exact_load_crosswalk_pass",
    )
    midas_kds_geometry_bridge_semantic_crosswalk_surface = _extract_midas_kds_geometry_ratio_surface(
        midas_kds_geometry_bridge_validation,
        label="semantic_crosswalk",
        summary_count_key="exact_review_semantic_crosswalk_count_total",
        summary_expected_key="exact_review_semantic_crosswalk_expected_total",
        check_key="exact_semantic_crosswalk_pass",
    )
    midas_kds_geometry_bridge_full_member_crosswalk_surface = _extract_midas_kds_geometry_ratio_surface(
        midas_kds_geometry_bridge_validation,
        label="full_member_crosswalk",
        summary_count_key="full_member_crosswalk_count_total",
        summary_expected_key="full_member_crosswalk_expected_total",
        check_key="full_member_crosswalk_pass",
    )
    midas_kds_geometry_bridge_full_section_crosswalk_surface = _extract_midas_kds_geometry_ratio_surface(
        midas_kds_geometry_bridge_validation,
        label="full_section_crosswalk",
        summary_count_key="full_section_crosswalk_count_total",
        summary_expected_key="full_section_crosswalk_expected_total",
        check_key="full_section_crosswalk_pass",
    )
    midas_kds_geometry_bridge_full_load_crosswalk_surface = _extract_midas_kds_geometry_ratio_surface(
        midas_kds_geometry_bridge_validation,
        label="full_load_crosswalk",
        summary_count_key="full_load_crosswalk_count_total",
        summary_expected_key="full_load_crosswalk_expected_total",
        check_key="full_load_crosswalk_pass",
    )
    midas_kds_geometry_bridge_validation.update(
        {
            "load_crosswalk_summary_line": str(
                midas_kds_geometry_bridge_load_crosswalk_surface.get("summary_line", "") or ""
            ),
            "load_crosswalk_count": int(
                midas_kds_geometry_bridge_load_crosswalk_surface.get("count", 0) or 0
            ),
            "load_crosswalk_expected": int(
                midas_kds_geometry_bridge_load_crosswalk_surface.get("expected", 0) or 0
            ),
            "load_crosswalk_status": str(
                midas_kds_geometry_bridge_load_crosswalk_surface.get("status", "") or ""
            ),
            "load_crosswalk_pass": midas_kds_geometry_bridge_load_crosswalk_surface.get("pass"),
            "semantic_crosswalk_summary_line": str(
                midas_kds_geometry_bridge_semantic_crosswalk_surface.get("summary_line", "") or ""
            ),
            "semantic_crosswalk_count": int(
                midas_kds_geometry_bridge_semantic_crosswalk_surface.get("count", 0) or 0
            ),
            "semantic_crosswalk_expected": int(
                midas_kds_geometry_bridge_semantic_crosswalk_surface.get("expected", 0) or 0
            ),
            "semantic_crosswalk_status": str(
                midas_kds_geometry_bridge_semantic_crosswalk_surface.get("status", "") or ""
            ),
            "semantic_crosswalk_pass": midas_kds_geometry_bridge_semantic_crosswalk_surface.get("pass"),
            "full_member_crosswalk_summary_line": str(
                midas_kds_geometry_bridge_full_member_crosswalk_surface.get("summary_line", "") or ""
            ),
            "full_member_crosswalk_count": int(
                midas_kds_geometry_bridge_full_member_crosswalk_surface.get("count", 0) or 0
            ),
            "full_member_crosswalk_expected": int(
                midas_kds_geometry_bridge_full_member_crosswalk_surface.get("expected", 0) or 0
            ),
            "full_member_crosswalk_status": str(
                midas_kds_geometry_bridge_full_member_crosswalk_surface.get("status", "") or ""
            ),
            "full_member_crosswalk_pass": midas_kds_geometry_bridge_full_member_crosswalk_surface.get("pass"),
            "full_section_crosswalk_summary_line": str(
                midas_kds_geometry_bridge_full_section_crosswalk_surface.get("summary_line", "") or ""
            ),
            "full_section_crosswalk_count": int(
                midas_kds_geometry_bridge_full_section_crosswalk_surface.get("count", 0) or 0
            ),
            "full_section_crosswalk_expected": int(
                midas_kds_geometry_bridge_full_section_crosswalk_surface.get("expected", 0) or 0
            ),
            "full_section_crosswalk_status": str(
                midas_kds_geometry_bridge_full_section_crosswalk_surface.get("status", "") or ""
            ),
            "full_section_crosswalk_pass": midas_kds_geometry_bridge_full_section_crosswalk_surface.get("pass"),
            "full_load_crosswalk_summary_line": str(
                midas_kds_geometry_bridge_full_load_crosswalk_surface.get("summary_line", "") or ""
            ),
            "full_load_crosswalk_count": int(
                midas_kds_geometry_bridge_full_load_crosswalk_surface.get("count", 0) or 0
            ),
            "full_load_crosswalk_expected": int(
                midas_kds_geometry_bridge_full_load_crosswalk_surface.get("expected", 0) or 0
            ),
            "full_load_crosswalk_status": str(
                midas_kds_geometry_bridge_full_load_crosswalk_surface.get("status", "") or ""
            ),
            "full_load_crosswalk_pass": midas_kds_geometry_bridge_full_load_crosswalk_surface.get("pass"),
            "full_crosswalk_depth": _geometry_full_crosswalk_depth(
                midas_kds_geometry_bridge_load_crosswalk_surface,
                midas_kds_geometry_bridge_semantic_crosswalk_surface,
            ),
        }
    )
    midas_loadcomb_roundtrip_targets = list(args.midas_loadcomb_roundtrip_artifacts or DEFAULT_MIDAS_LOADCOMB_ROUNDTRIP_ARTIFACTS)
    midas_loadcomb_roundtrip_ok, midas_loadcomb_roundtrip_validation = _run_midas_loadcomb_roundtrip_validator(
        args.midas_loadcomb_roundtrip_validator,
        midas_loadcomb_roundtrip_targets,
    )

    inputs_ok, input_reason = _validate_inputs(strict, rca)
    contracts_ok, missing_contracts = _validate_contract_artifacts(args.required_contracts)
    priority_ok, priority_reason, priority_data = _validate_priority3(args.priority3)
    energy_ok, meta_ood_ok, buckling_ok, benchmark_ok, branching_ok, bifurcation_ok, rust_onnx_ok, winning_ticket_ok, rust_md3bead_parity_ok, lj_mapping_ok, dynamic_time_history_ok, cache_profile_ok, p0_engine_perf_ok, p0_core_gap_ok, noise_stress_ok, scaleout_io_ok, phasea_contract_ok, phaseb_track_ok, phased_multidomain_ok, phasee_integrated_ok, phasef_resilience_ok = _validate_extended_contracts(
        args.physics_residual, args.meta_learning, args.buckling, args.benchmark,
        args.branching, args.bifurcation, args.rust_onnx, args.winning_ticket, args.rust_md3bead_parity, args.lj_mapping, args.dynamic_time_history, args.cache_profile, args.p0_engine_perf, args.p0_core_gap, args.noise_stress, args.scaleout_io, args.phasea_contract, args.phaseb_track_lf, args.phaseb_moving_load, args.phaseb_vti, args.phaseb_irregularity, args.phaseb_summary, args.phased_track_dataset, args.phased_tunnel_dataset, args.phased_attention, args.phased_tgnn, args.phased_summary, args.phasee_substructuring, args.phasee_attenuation, args.phasee_compliance, args.phasee_whitebox, args.phasee_summary, args.phasef_l3, args.phasef_phase_correction, args.phasef_soil_ood, args.phasef_summary
    )
    phase3_pipeline = _load_json(args.phase3_pipeline)
    topology_gate = _load_json(args.topology_gate)
    partitioned_scaleout = _load_json(args.partitioned_scaleout)
    sync_stress = _load_json(args.sync_stress)
    noise_convergence = _load_json(args.noise_convergence)
    commercial_csv_gate = _load_json(args.commercial_csv_gate)
    commercial_readiness = _load_json(args.commercial_readiness)
    solver_breadth = _load_json(args.solver_breadth_report)
    element_material_breadth = _load_json(args.element_material_breadth_report)
    material_constitutive = _load_json(args.material_constitutive_report)
    steel_composite_constitutive_gate = _load_optional_json(args.steel_composite_constitutive_gate_report)
    midas_kds_row_provenance_export = _load_json(args.midas_kds_row_provenance_export_report)
    contact_readiness = _load_json(args.contact_readiness_report)
    structural_contact = _load_json(args.structural_contact_report)
    general_fe_contact_matrix = _load_json(args.general_fe_contact_benchmark_report)
    surface_interaction_benchmark = _load_json(args.surface_interaction_benchmark_report)
    foundation_soil_link = _load_json(args.foundation_soil_link_report)
    midas_interoperability = _load_json(args.midas_interoperability_report)
    korean_source_ingest_gate = _load_json(args.korean_source_ingest_gate_report)
    midas_native_roundtrip = _load_json(args.midas_native_roundtrip_report)
    midas_exact_roundtrip_closure = _load_json(args.midas_exact_roundtrip_closure_report)
    load_combination_engine_gate = _load_optional_json(args.load_combination_engine_gate_report)
    panel_zone_clash = _load_optional_json(args.panel_zone_clash_report)
    irregular_structure_collection_gate = _load_json(args.irregular_structure_collection_gate_report)
    irregular_top5_execution_manifest = _load_json(args.irregular_top5_execution_manifest)
    nonlinear_generalization = _load_json(args.nonlinear_generalization_report)
    workflow_productization = _load_json(args.workflow_productization_report)
    real_source_multi = _load_json(args.real_source_multi)
    nonlinear_engine = _load_json(args.nonlinear_engine_report)
    pushover_stress = _load_json(args.pushover_stress_report)
    ndtha_stress = _load_json_from_disk(args.ndtha_stress_report)
    ndtha_step_series_depth = _ndtha_step_series_depth(ndtha_stress)
    ndtha_material_surface = _ndtha_material_surface(ndtha_stress)
    ndtha_material_depth = int(ndtha_material_surface.get("material_depth", 0) or 0)
    ndtha_material_summary_line = str(ndtha_material_surface.get("summary_line", "") or "").strip()
    ndtha_residual_gate = _load_json(args.ndtha_residual_gate_report)
    pbd_review = _load_json(args.pbd_review_package)
    global_authority = _load_json(args.global_authority_gate)
    opensees_canonical_breadth_path = Path(
        "implementation/phase1/release/benchmark_expansion/opensees_canonical_breadth_report.json"
    )
    opensees_canonical_breadth = (
        _load_json(str(opensees_canonical_breadth_path)) if opensees_canonical_breadth_path.exists() else {}
    )
    measured_benchmark_breadth_path = Path(
        "implementation/phase1/release/benchmark_expansion/measured_benchmark_breadth_report.json"
    )
    measured_benchmark_breadth = (
        _load_json(str(measured_benchmark_breadth_path)) if measured_benchmark_breadth_path.exists() else {}
    )
    wind_benchmark = _load_json(args.wind_benchmark_report)
    ssi_boundary = _load_json(args.ssi_boundary_report)
    damper_validation = _load_json(args.damper_validation_report)
    kds_compliance = _load_json(args.kds_compliance_summary)
    construction_sequence = _load_json(args.construction_sequence_report)
    flexible_diaphragm = _load_json(args.flexible_diaphragm_report)
    repro_version_lock = _load_json(args.repro_version_lock_report)
    release_registry = _load_json(args.release_registry_report)
    performance_profiling_path = Path(args.performance_profiling_report)
    performance_profiling = _load_json(args.performance_profiling_report) if performance_profiling_path.exists() else {}
    solver_hip_e2e = _load_json(args.solver_hip_e2e) if Path(args.solver_hip_e2e).exists() else {}
    solver_truthfulness = _load_json(args.solver_truthfulness) if Path(args.solver_truthfulness).exists() else {}
    hardest_external_10case_kickoff = _load_json(args.hardest_external_10case_kickoff_report)
    rc_benchmark_lock = _load_json(args.rc_benchmark_lock) if Path(args.rc_benchmark_lock).exists() else {}
    midas_mgt_conversion = _load_json(args.midas_mgt_conversion)
    scaleout_io_report = _load_json(args.scaleout_io)
    nightly_10m_repro = _load_json(args.nightly_10m_repro)
    hip_kernel_smoke = _load_json(args.hip_kernel_smoke) if Path(args.hip_kernel_smoke).exists() else {}
    ndtha_long_profile = _load_json(args.ndtha_long_profile) if Path(args.ndtha_long_profile).exists() else {}

    panel_zone_clash_available = bool(panel_zone_clash)
    panel_zone_clash_summary = (
        panel_zone_clash.get("summary") if isinstance(panel_zone_clash.get("summary"), dict) else {}
    )
    panel_zone_3d_clash_ready = bool(_pass(panel_zone_clash)) if panel_zone_clash_available else False
    panel_zone_report_mode = str(panel_zone_clash_summary.get("constructability_mode", "") or "")
    panel_zone_report_reason = str(panel_zone_clash.get("reason") or panel_zone_clash_summary.get("reason") or "")
    panel_zone_proxy_candidate_count = int(panel_zone_clash_summary.get("panel_zone_proxy_candidate_count", 0) or 0)
    panel_zone_source_artifact_kind = str(panel_zone_clash_summary.get("panel_zone_source_artifact_kind", "") or "")
    panel_zone_source_artifact_path = str(panel_zone_clash_summary.get("panel_zone_source_artifact_path", "") or "")
    panel_zone_source_contract_mode = str(panel_zone_clash_summary.get("panel_zone_source_contract_mode", "") or "")
    panel_zone_internal_engine_complete = bool(panel_zone_clash_summary.get("panel_zone_internal_engine_complete", False))
    panel_zone_external_validation_pending = bool(
        panel_zone_clash_summary.get("panel_zone_external_validation_pending", False)
    )
    panel_zone_validation_boundary = str(panel_zone_clash_summary.get("panel_zone_validation_boundary", "") or "")
    panel_zone_external_validation_surface = (
        _panel_zone_external_validation_surface(
            {**panel_zone_clash_summary, "panel_zone_3d_clash_ready": panel_zone_3d_clash_ready}
        )
        if panel_zone_clash_available
        else {
            "advisory_only": False,
            "release_blocking": False,
            "status_label": "unavailable",
        }
    )
    panel_zone_external_validation_advisory_only = bool(panel_zone_external_validation_surface["advisory_only"])
    panel_zone_external_validation_release_blocking = bool(
        panel_zone_external_validation_surface["release_blocking"]
    )
    panel_zone_external_validation_status_label = str(panel_zone_external_validation_surface["status_label"])
    panel_zone_advisory_only = bool(
        panel_zone_clash_available
        and panel_zone_3d_clash_ready
        and panel_zone_external_validation_pending
        and panel_zone_validation_boundary == "external_validation_only"
    )
    panel_zone_release_blocking = bool(panel_zone_clash_available and not panel_zone_3d_clash_ready)
    if panel_zone_advisory_only:
        panel_zone_status_label = "advisory_external_validation_only_boundary"
    elif panel_zone_release_blocking:
        panel_zone_status_label = "release_blocking"
    elif panel_zone_clash_available and panel_zone_3d_clash_ready:
        panel_zone_status_label = "release_ready"
    else:
        panel_zone_status_label = "unavailable"

    phase3_real_source_ok = bool(phase3_pipeline.get("contract_pass", False)) and bool(
        (phase3_pipeline.get("checks") or {}).get("real_source_verified", False)
    ) and bool((phase3_pipeline.get("checks") or {}).get("sample_source_blocked", False)) and bool(
        (phase3_pipeline.get("checks") or {}).get("shell_beam_mix_pass", False)
    )
    topology_gate_ok = bool(topology_gate.get("contract_pass", False)) and bool(
        (topology_gate.get("checks") or {}).get("real_topology_pass", False)
    ) and bool(
        (topology_gate.get("checks") or {}).get("shell_beam_mix_pass", False)
    )
    shell_beam_mix_ok = bool(
        (phase3_pipeline.get("checks") or {}).get("shell_beam_mix_pass", False)
        and bool((topology_gate.get("checks") or {}).get("shell_beam_mix_pass", False))
    )
    partitioned_scaleout_ok = bool(partitioned_scaleout.get("contract_pass", False)) and bool(
        (partitioned_scaleout.get("checks") or {}).get("pr_scale_pass" if str(args.ci_mode) == "pr" else "nightly_scale_pass", False)
    ) and bool((partitioned_scaleout.get("checks") or {}).get("on_scaling_regression_pass", True)) and bool(
        (partitioned_scaleout.get("checks") or {}).get("real_graph_used", True)
    ) and bool(
        (partitioned_scaleout.get("checks") or {}).get("graph_source_is_real", True)
    ) and bool(
        (partitioned_scaleout.get("checks") or {}).get("projection_ratio_pass", True)
    ) and bool(
        (partitioned_scaleout.get("checks") or {}).get("partition_quality_threshold_pass", True)
    )
    if str(args.ci_mode) == "nightly":
        partitioned_scaleout_ok = bool(
            partitioned_scaleout_ok
            and bool((partitioned_scaleout.get("checks") or {}).get("nightly_scale_pass", False))
        )
    noise_summary = noise_convergence.get("summary") if isinstance(noise_convergence.get("summary"), dict) else {}
    sync_stress_ok = bool(sync_stress.get("contract_pass", False)) and all(
        bool((sync_stress.get("checks") or {}).get(key, False))
        for key in (
            "topology_gate_pass",
            "required_levels_present",
            "required_levels_sync_pass",
            "sync_stall_budget_pass",
            "backend_policy_pass",
            "virtual_sync_blocked_pass",
            "feti_profile_pass",
            "inline_native_smoke_pass",
        )
    )
    noise_convergence_checks = noise_convergence.get("checks") if isinstance(noise_convergence.get("checks"), dict) else {}
    noise_convergence_ok = bool(noise_convergence.get("contract_pass", False)) and all(
        bool(noise_convergence_checks.get(key, False))
        for key in (
            "has_required_seeds",
            "has_seed_diversity",
            "includes_plus_minus_10",
            "includes_plus_minus_5",
            "case_diversity_pass",
            "stagewise_execution_pass",
            "all_converged",
            "scenario_count_nonzero",
        )
    )
    noise_convergence_ok = bool(noise_convergence_ok and int(noise_summary.get("fail_count", 1)) == 0)
    commercial_csv_gate_ok = bool(commercial_csv_gate.get("contract_pass", False)) and all(
        bool((commercial_csv_gate.get("checks") or {}).get(key, False))
        for key in (
            "build_cases_pass",
            "benchmark_pass",
            "metric_source_pass",
            "drift_within_5pct",
            "base_shear_within_5pct",
            "buckling_within_5pct",
            "mac_above_095",
            "member_force_metric_present",
            "member_force_hard_pass",
            "member_force_soft_accept_pass",
            "member_force_components_5d_pass",
        )
    )
    cr_inputs = commercial_readiness.get("inputs") if isinstance(commercial_readiness.get("inputs"), dict) else {}
    cr_checks = commercial_readiness.get("checks") if isinstance(commercial_readiness.get("checks"), dict) else {}
    cr_metrics = commercial_readiness.get("global_metrics") if isinstance(commercial_readiness.get("global_metrics"), dict) else {}
    cr_noise_seeds = {tok.strip() for tok in str(cr_inputs.get("noise_seeds", "")).split(",") if tok.strip()}
    cr_conv_seeds = {tok.strip() for tok in str(cr_inputs.get("convergence_seeds", "")).split(",") if tok.strip()}
    cr_noise_levels = {tok.strip() for tok in str(cr_inputs.get("noise_stiffness_levels_pct", "")).split(",") if tok.strip()}
    cr_conv_levels = {tok.strip() for tok in str(cr_inputs.get("convergence_stiffness_levels_pct", "")).split(",") if tok.strip()}
    required_seed_core = {"11", "23", "47"}
    measured_benchmark_breadth_summary = (
        measured_benchmark_breadth.get("summary")
        if isinstance(measured_benchmark_breadth.get("summary"), dict)
        else {}
    )
    measured_benchmark_breadth_summary_line = str(
        measured_benchmark_breadth.get("summary_line", "") or ""
    ).strip()
    measured_family_count = int(
        measured_benchmark_breadth_summary.get(
            "measured_family_count",
            cr_metrics.get("measured_source_family_count", 0),
        )
        or 0
    )
    measured_case_count = int(
        measured_benchmark_breadth_summary.get(
            "measured_case_count",
            cr_metrics.get("measured_case_count", 0),
        )
        or 0
    )
    commercial_benchmark_breadth_summary_line = (
        "Commercial benchmark breadth: "
        f"families={int(cr_metrics.get('source_family_count', 0) or 0)}, "
        f"measured_families={measured_family_count}, "
        f"measured_cases={measured_case_count}, "
        f"shell_beam_mix={int(cr_metrics.get('shell_beam_mix_case_count', 0) or 0)}"
    )
    commercial_readiness_summary_line = (
        "Commercial readiness: "
        f"{str(commercial_readiness.get('reason_code', 'UNKNOWN'))} | "
        f"grade={str((commercial_readiness.get('grade') or {}).get('label', 'unknown'))} | "
        f"strict_measured={bool(cr_inputs.get('require_measured_dynamic_targets', False))} | "
        f"families={int(cr_metrics.get('source_family_count', 0) or 0)} | "
        f"measured_families={measured_family_count} | "
        f"measured_cases={measured_case_count} | "
        f"shell_beam_mix={int(cr_metrics.get('shell_beam_mix_case_count', 0) or 0)}"
    )
    commercial_readiness_ok = bool(
        commercial_readiness.get("contract_pass", False)
        and bool(cr_checks.get("real_source_pass", False))
        and bool(cr_checks.get("benchmark_breadth_pass", True))
        and bool(cr_checks.get("measured_dynamic_targets_pass", True))
        and bool(cr_checks.get("measured_source_family_pass", True))
        and bool(cr_checks.get("measured_case_count_pass", True))
        and bool(cr_checks.get("gpu_strict_pass", False))
        and bool(cr_inputs.get("forbid_toy_cases", False))
        and required_seed_core.issubset(cr_noise_seeds)
        and required_seed_core.issubset(cr_conv_seeds)
        and "10" in cr_noise_levels
        and "10" in cr_conv_levels
    )
    solver_breadth_checks = solver_breadth.get("checks") if isinstance(solver_breadth.get("checks"), dict) else {}
    solver_breadth_summary_line = str(solver_breadth.get("summary_line", "") or "Solver breadth: unavailable").strip()
    solver_breadth_ok = bool(
        solver_breadth.get("contract_pass", False)
        and bool(solver_breadth_checks.get("shell_evidence_pass", False))
        and bool(solver_breadth_checks.get("wall_evidence_pass", False))
        and bool(solver_breadth_checks.get("interface_boundary_pass", False))
        and bool(solver_breadth_checks.get("benchmark_coverage_pass", False))
        and bool(solver_breadth_checks.get("contact_surface_declared", False))
    )
    element_material_breadth_checks = (
        element_material_breadth.get("checks") if isinstance(element_material_breadth.get("checks"), dict) else {}
    )
    element_material_breadth_summary_line = str(
        element_material_breadth.get("summary_line", "") or "Element/material breadth: unavailable"
    ).strip()
    element_material_breadth_ok = bool(
        element_material_breadth.get("contract_pass", False)
        and bool(element_material_breadth_checks.get("shell_direct_contract_pass", False))
        and bool(element_material_breadth_checks.get("wall_direct_contract_pass", False))
        and bool(element_material_breadth_checks.get("contact_interface_compression_surrogate_pass", False))
        and bool(element_material_breadth_checks.get("structural_contact_direct_contract_pass", False))
        and bool(element_material_breadth_checks.get("foundation_soil_link_direct_contract_pass", False))
        and bool(element_material_breadth_checks.get("material_model_breadth_pass", False))
        and bool(element_material_breadth_checks.get("link_model_breadth_pass", False))
        and bool(element_material_breadth_checks.get("material_capability_breadth_pass", False))
    )
    material_constitutive_checks = (
        material_constitutive.get("checks") if isinstance(material_constitutive.get("checks"), dict) else {}
    )
    material_constitutive_summary_line = str(
        material_constitutive.get("summary_line", "") or "Material constitutive gate: unavailable"
    ).strip()
    material_constitutive_ok = bool(
        material_constitutive.get("contract_pass", False)
        and bool(material_constitutive_checks.get("concrete_damage_pass", False))
        and bool(material_constitutive_checks.get("cyclic_degradation_pass", False))
        and bool(material_constitutive_checks.get("bond_interface_pass", False))
        and bool(material_constitutive_checks.get("calibration_matrix_pass", True))
    )
    steel_composite_constitutive_gate_available = bool(steel_composite_constitutive_gate)
    steel_composite_constitutive_gate_summary_line = str(
        steel_composite_constitutive_gate.get("summary_line", "") or "Steel/composite constitutive gate: unavailable"
    ).strip()
    steel_composite_constitutive_gate_ok = bool(steel_composite_constitutive_gate.get("contract_pass", False))
    midas_kds_row_provenance_export_summary_line = str(
        midas_kds_row_provenance_export.get("summary_line", "") or "MIDAS KDS row provenance export: unavailable"
    ).strip()
    midas_kds_row_provenance_export_ok = bool(midas_kds_row_provenance_export.get("contract_pass", False))
    contact_readiness_checks = contact_readiness.get("checks") if isinstance(contact_readiness.get("checks"), dict) else {}
    contact_readiness_summary_line = str(
        contact_readiness.get("summary_line", "") or "Contact readiness: unavailable"
    ).strip()
    contact_readiness_ok = bool(
        contact_readiness.get("contract_pass", False)
        and bool(contact_readiness_checks.get("contact_schema_pass", False))
        and bool(contact_readiness_checks.get("contact_solver_evidence_pass", False))
        and bool(contact_readiness_checks.get("contact_whitebox_evidence_pass", False))
    )
    structural_contact_checks = (
        structural_contact.get("checks") if isinstance(structural_contact.get("checks"), dict) else {}
    )
    structural_contact_summary_line = str(
        structural_contact.get("summary_line", "") or "Structural contact readiness: unavailable"
    ).strip()
    structural_contact_ok = bool(
        structural_contact.get("contract_pass", False)
        and bool(structural_contact_checks.get("bounded_contact_evidence_pass", False))
        and bool(structural_contact_checks.get("special_link_categories_present", False))
        and bool(structural_contact_checks.get("structural_contact_validation_present", False))
        and bool(structural_contact_checks.get("structural_contact_event_sequence_zero_pass", False))
        and bool(structural_contact_checks.get("all_structural_contact_categories_ready", False))
    )
    general_fe_contact_matrix_checks = (
        general_fe_contact_matrix.get("checks") if isinstance(general_fe_contact_matrix.get("checks"), dict) else {}
    )
    general_fe_contact_matrix_summary_line = str(
        general_fe_contact_matrix.get("summary_line", "") or "General FE contact matrix: unavailable"
    ).strip()
    general_fe_contact_matrix_ok = bool(
        general_fe_contact_matrix.get("contract_pass", False)
        and bool(general_fe_contact_matrix_checks.get("direct_structural_contact_pass", False))
        and bool(general_fe_contact_matrix_checks.get("foundation_soil_link_pass", False))
        and bool(general_fe_contact_matrix_checks.get("interface_transfer_pass", False))
        and bool(general_fe_contact_matrix_checks.get("ssi_boundary_pass", False))
        and bool(general_fe_contact_matrix_checks.get("soil_tunnel_dynamic_pass", False))
        and bool(general_fe_contact_matrix_checks.get("all_matrix_rows_ready", False))
    )
    general_fe_contact_surface = _general_fe_contact_surface(general_fe_contact_matrix)
    general_fe_contact_surface_summary_line = str(
        general_fe_contact_surface.get("summary_line", "") or ""
    ).strip()
    surface_interaction_benchmark_checks = (
        surface_interaction_benchmark.get("checks") if isinstance(surface_interaction_benchmark.get("checks"), dict) else {}
    )
    surface_interaction_benchmark_summary_line = str(
        surface_interaction_benchmark.get("summary_line", "") or "Surface interaction benchmark: unavailable"
    ).strip()
    surface_interaction_benchmark_ok = bool(
        surface_interaction_benchmark.get("contract_pass", False)
        and bool(surface_interaction_benchmark_checks.get("shell_surface_coupling_pass", False))
        and bool(surface_interaction_benchmark_checks.get("interface_transfer_pass", False))
        and bool(surface_interaction_benchmark_checks.get("interface_gap_continuity_pass", False))
        and bool(surface_interaction_benchmark_checks.get("foundation_soil_impedance_pass", False))
        and bool(surface_interaction_benchmark_checks.get("ssi_boundary_interaction_pass", False))
        and bool(surface_interaction_benchmark_checks.get("soil_tunnel_dynamic_interaction_pass", False))
        and bool(surface_interaction_benchmark_checks.get("direct_structural_contact_family_pass", False))
        and bool(surface_interaction_benchmark_checks.get("all_matrix_rows_ready", False))
    )
    nonlinear_engine_checks = nonlinear_engine.get("checks") if isinstance(nonlinear_engine.get("checks"), dict) else {}
    nonlinear_engine_ok = bool(
        nonlinear_engine.get("contract_pass", False)
        and bool(nonlinear_engine_checks.get("metric_source_pass", False))
        and bool(nonlinear_engine_checks.get("rust_backend_used_pass", False))
        and bool(nonlinear_engine_checks.get("all_cases_converged", False))
        and bool(nonlinear_engine_checks.get("drift_p95_pass", False))
        and bool(nonlinear_engine_checks.get("base_shear_p95_pass", False))
        and bool(nonlinear_engine_checks.get("top_disp_metric_source_required_pass", False))
        and bool(nonlinear_engine_checks.get("top_disp_p95_pass", False))
    )
    core_engine_surface_summary, core_engine_surface_summary_line = _build_core_engine_surface_summary(
        nonlinear_engine_report=nonlinear_engine,
        nonlinear_engine_pass=nonlinear_engine_ok,
        solver_breadth_report=solver_breadth,
        solver_breadth_pass=solver_breadth_ok,
        element_material_breadth_report=element_material_breadth,
        element_material_breadth_pass=element_material_breadth_ok,
        material_constitutive_report=material_constitutive,
        material_constitutive_pass=material_constitutive_ok,
        steel_composite_constitutive_report=steel_composite_constitutive_gate,
        steel_composite_constitutive_pass=steel_composite_constitutive_gate_ok,
        contact_readiness_pass=contact_readiness_ok,
        structural_contact_pass=structural_contact_ok,
        general_fe_contact_matrix_report=general_fe_contact_matrix,
        general_fe_contact_matrix_pass=general_fe_contact_matrix_ok,
        surface_interaction_benchmark_report=surface_interaction_benchmark,
        surface_interaction_benchmark_pass=surface_interaction_benchmark_ok,
    )
    core_engine_surface_ok = bool(core_engine_surface_summary.get("contract_pass", False))
    foundation_soil_link_checks = (
        foundation_soil_link.get("checks") if isinstance(foundation_soil_link.get("checks"), dict) else {}
    )
    foundation_soil_link_summary_line = str(
        foundation_soil_link.get("summary_line", "") or "Foundation/soil link: unavailable"
    ).strip()
    foundation_soil_link_ok = bool(
        foundation_soil_link.get("contract_pass", False)
        and bool(foundation_soil_link_checks.get("foundation_scope_ready", False))
        and bool(foundation_soil_link_checks.get("foundation_artifact_ready", False))
        and bool(foundation_soil_link_checks.get("foundation_link_models_ready", False))
    )
    support_search_surface = _support_search_surface(foundation_soil_link)
    support_search_summary_line = str(support_search_surface.get("summary_line", "") or "").strip()
    support_search_count = int(support_search_surface.get("support_search_count", 0) or 0)
    node_surface_proxy_count = int(support_search_surface.get("node_surface_proxy_count", 0) or 0)
    support_depth_score = int(support_search_surface.get("support_depth_score", 0) or 0)
    support_search_pass = bool(support_search_surface.get("support_search_pass", False))
    node_surface_proxy_pass = bool(support_search_surface.get("node_surface_proxy_pass", False))
    midas_interoperability_checks = (
        midas_interoperability.get("checks") if isinstance(midas_interoperability.get("checks"), dict) else {}
    )
    midas_interoperability_summary_line = str(
        midas_interoperability.get("summary_line", "") or "MIDAS interoperability/export readiness: unavailable"
    ).strip()
    midas_interoperability_ok = bool(
        midas_interoperability.get("contract_pass", False)
        and bool(midas_interoperability_checks.get("model_artifacts_present_pass", False))
        and bool(midas_interoperability_checks.get("editor_seed_present_pass", False))
        and bool(midas_interoperability_checks.get("load_pattern_library_present_pass", False))
        and bool(midas_interoperability_checks.get("export_report_pass", False))
        and bool(midas_interoperability_checks.get("loadcomb_preview_files_pass", False))
        and bool(midas_interoperability_checks.get("loadcomb_roundtrip_reports_pass", False))
    )
    korean_source_ingest_gate_summary_line = str(
        korean_source_ingest_gate.get("summary_line", "") or "Korean source ingest gate: unavailable"
    ).strip()
    korean_source_ingest_gate_ok = bool(korean_source_ingest_gate.get("contract_pass", False))
    midas_native_roundtrip_checks = (
        midas_native_roundtrip.get("checks") if isinstance(midas_native_roundtrip.get("checks"), dict) else {}
    )
    midas_native_roundtrip_summary_line = str(
        midas_native_roundtrip.get("summary_line", "") or "MIDAS native roundtrip: unavailable"
    ).strip()
    midas_native_roundtrip_ok = bool(
        midas_native_roundtrip.get("contract_pass", False)
        and bool(midas_native_roundtrip_checks.get("corpus_manifest_present_pass", False))
        and bool(midas_native_roundtrip_checks.get("native_text_case_present_pass", False))
        and bool(midas_native_roundtrip_checks.get("native_writeback_ready_pass", False))
        and bool(midas_native_roundtrip_checks.get("diff_receipt_coverage_pass", False))
        and bool(midas_native_roundtrip_checks.get("per_case_writeback_pass", False))
        and bool(midas_native_roundtrip_checks.get("topology_stability_pass", False))
        and bool(midas_native_roundtrip_checks.get("load_contract_stability_pass", False))
        and bool(midas_native_roundtrip_checks.get("loadcomb_exact_roundtrip_pass", False))
        and bool(midas_native_roundtrip_checks.get("unknown_rows_zero_pass", False))
    )
    midas_exact_roundtrip_closure_summary_line = str(
        midas_exact_roundtrip_closure.get("summary_line", "") or "MIDAS exact roundtrip closure: unavailable"
    ).strip()
    midas_exact_roundtrip_closure_ok = bool(midas_exact_roundtrip_closure.get("contract_pass", False))
    midas_exact_roundtrip_closure_scope_summary = _extract_midas_exact_roundtrip_closure_scope(
        midas_exact_roundtrip_closure
    )
    midas_exact_roundtrip_closure_scope_available = bool(midas_exact_roundtrip_closure_scope_summary)
    load_combination_engine_gate_summary = _extract_load_combination_engine_summary(load_combination_engine_gate)
    load_combination_engine_gate_available = bool(load_combination_engine_gate)
    load_combination_engine_gate_summary_line = _format_load_combination_engine_summary_line(
        load_combination_engine_gate,
        load_combination_engine_gate_summary,
    )
    load_combination_engine_gate_ok = bool(load_combination_engine_gate.get("contract_pass", False))
    nonlinear_generalization_checks = (
        nonlinear_generalization.get("checks") if isinstance(nonlinear_generalization.get("checks"), dict) else {}
    )
    nonlinear_generalization_summary_line = str(
        nonlinear_generalization.get("summary_line", "") or "Nonlinear generalization: unavailable"
    ).strip()
    nonlinear_generalization_ok = bool(
        nonlinear_generalization.get("contract_pass", False)
        and bool(nonlinear_generalization_checks.get("beam_column_generalization_pass", False))
        and bool(nonlinear_generalization_checks.get("fiber_section_family_pass", False))
        and bool(nonlinear_generalization_checks.get("layered_shell_wall_pass", False))
        and bool(nonlinear_generalization_checks.get("joint_panel_family_pass", False))
        and bool(nonlinear_generalization_checks.get("foundation_section_family_pass", False))
        and bool(nonlinear_generalization_checks.get("connection_section_family_pass", False))
        and bool(nonlinear_generalization_checks.get("substructure_section_family_pass", False))
        and bool(nonlinear_generalization_checks.get("device_section_family_pass", False))
        and bool(nonlinear_generalization_checks.get("isolation_section_family_pass", False))
        and bool(nonlinear_generalization_checks.get("soil_interface_section_family_pass", False))
        and bool(nonlinear_generalization_checks.get("bearing_section_family_pass", False))
        and bool(nonlinear_generalization_checks.get("retrofit_section_family_pass", False))
        and bool(nonlinear_generalization_checks.get("ground_improvement_section_family_pass", False))
        and bool(nonlinear_generalization_checks.get("foundation_soil_link_pass", False))
        and bool(nonlinear_generalization_checks.get("production_engine_evidence_pass", False))
    )
    workflow_productization_checks = (
        workflow_productization.get("checks") if isinstance(workflow_productization.get("checks"), dict) else {}
    )
    workflow_productization_summary = (
        workflow_productization.get("summary") if isinstance(workflow_productization.get("summary"), dict) else {}
    )
    workflow_productization_summary_line = str(
        workflow_productization.get("summary_line", "") or "Workflow/interoperability productization: unavailable"
    ).strip()
    workflow_results_explorer_traceability_pass = bool(
        workflow_productization_checks.get("results_explorer_traceability_pass", False)
    )
    workflow_productization_ok = bool(
        workflow_productization.get("contract_pass", False)
        and bool(workflow_productization_checks.get("signed_release_registry_pass", False))
        and bool(workflow_productization_checks.get("authoring_action_automation_pass", False))
        and bool(workflow_productization_checks.get("audit_approval_flow_pass", False))
        and bool(workflow_productization_checks.get("audit_action_automation_pass", False))
        and bool(workflow_productization_checks.get("auto_approved_subset_pass", False))
        and bool(workflow_productization_checks.get("signed_submission_bundle_pass", False))
        and bool(workflow_productization_checks.get("viewer_results_surface_pass", False))
        and workflow_results_explorer_traceability_pass
        and bool(workflow_productization_checks.get("provenance_export_pass", False))
        and bool(workflow_productization_checks.get("bounded_roundtrip_pass", False))
    )
    irregular_structure_collection_gate_checks = (
        irregular_structure_collection_gate.get("checks")
        if isinstance(irregular_structure_collection_gate.get("checks"), dict)
        else {}
    )
    irregular_structure_collection_gate_summary_line = str(
        irregular_structure_collection_gate.get("summary_line", "") or "Irregular structure collection gate: unavailable"
    ).strip()
    irregular_structure_collection_gate_ok = bool(
        irregular_structure_collection_gate.get("contract_pass", False)
        and bool(irregular_structure_collection_gate_checks.get("catalog_present_pass", True))
        and bool(irregular_structure_collection_gate_checks.get("collection_report_present_pass", True))
        and bool(irregular_structure_collection_gate_checks.get("top5_manifest_present_pass", True))
    )
    irregular_top5_execution_manifest_summary_line = str(
        irregular_top5_execution_manifest.get("summary_line", "") or "Irregular top5 execution manifest: unavailable"
    ).strip()
    real_source_multi_ok = bool(real_source_multi.get("contract_pass", False))
    pushover_checks = pushover_stress.get("checks") if isinstance(pushover_stress.get("checks"), dict) else {}
    pushover_stress_ok = bool(
        pushover_stress.get("contract_pass", False)
        and bool(pushover_checks.get("metric_source_pass", False))
        and bool(pushover_checks.get("all_cases_converged", False))
        and bool(pushover_checks.get("plasticity_triggered_all_cases", False))
        and bool(pushover_checks.get("collapse_path_pass", False))
        and bool(pushover_checks.get("min_plastic_story_count_pass", False))
    )
    ndtha_checks = ndtha_stress.get("checks") if isinstance(ndtha_stress.get("checks"), dict) else {}
    ndtha_stress_ok = bool(
        ndtha_stress.get("contract_pass", False)
        and bool(ndtha_checks.get("metric_source_pass", False))
        and bool(ndtha_checks.get("pdelta_enabled_pass", False))
        and bool(ndtha_checks.get("dynamic_reversal_pass", False))
        and bool(ndtha_checks.get("rayleigh_damping_pass", False))
        and bool(ndtha_checks.get("collapse_cutoff_guard_pass", False))
        and bool(ndtha_checks.get("no_collapse_detected", False))
        and bool(ndtha_checks.get("all_cases_converged", False))
        and bool(ndtha_checks.get("rust_backend_used_pass", False))
        and bool(ndtha_checks.get("plasticity_triggered_all_cases", False))
        and bool(ndtha_checks.get("min_plastic_story_count_pass", False))
    )
    ndtha_residual_checks = ndtha_residual_gate.get("checks") if isinstance(ndtha_residual_gate.get("checks"), dict) else {}
    ndtha_residual_summary = ndtha_residual_gate.get("summary") if isinstance(ndtha_residual_gate.get("summary"), dict) else {}
    ndtha_residual_ok = bool(
        ndtha_residual_gate.get("contract_pass", False)
        and str(ndtha_residual_gate.get("reason_code", "")) == "PASS"
        and bool(ndtha_residual_checks.get("case_count_pass", False))
        and bool(ndtha_residual_checks.get("ndtha_contract_pass", False))
        and bool(ndtha_residual_checks.get("ndtha_no_collapse_pass", False))
        and bool(ndtha_residual_checks.get("summary_residual_finite_pass", False))
        and bool(ndtha_residual_checks.get("residual_metric_trace_pass", False))
        and bool(ndtha_residual_checks.get("residual_top_hard_pass", False))
        and bool(ndtha_residual_checks.get("residual_drift_hard_pass", False))
        and bool(ndtha_residual_checks.get("fallback_rate_pass", False))
        and int(ndtha_residual_summary.get("case_count", 0)) >= 1
    )
    pbd_artifacts = pbd_review.get("artifacts") if isinstance(pbd_review.get("artifacts"), dict) else {}
    pbd_metrics = pbd_review.get("metrics") if isinstance(pbd_review.get("metrics"), dict) else {}
    pbd_artifact_paths_ok = all(
        isinstance(pbd_artifacts.get(key), str) and Path(str(pbd_artifacts.get(key))).exists()
        for key in (
            "drift_envelope_png",
            "core_hysteresis_png",
            "killshot_metrics_json",
            "killshot_metrics_csv",
            "review_markdown",
            "review_pdf",
        )
    )
    try:
        pbd_eq_case_count = int(pbd_metrics.get("earthquake_case_count", 0))
    except Exception:
        pbd_eq_case_count = 0
    try:
        pbd_step_ratio_min = float(pbd_metrics.get("converged_step_ratio_min", 0.0))
    except Exception:
        pbd_step_ratio_min = 0.0
    try:
        pbd_energy_err = abs(float(pbd_metrics.get("energy_balance_relative_error_ref", 1.0)))
    except Exception:
        pbd_energy_err = 1.0
    pbd_review_ok = bool(
        pbd_review.get("contract_pass", False)
        and str(pbd_review.get("reason_code", "")) == "PASS"
        and pbd_eq_case_count >= 7
        and bool(pbd_metrics.get("all_cases_converged", False))
        and pbd_step_ratio_min >= 1.0
        and pbd_energy_err <= 1e-2
        and pbd_artifact_paths_ok
    )
    global_authority_checks = global_authority.get("checks") if isinstance(global_authority.get("checks"), dict) else {}
    global_authority_summary = global_authority.get("summary") if isinstance(global_authority.get("summary"), dict) else {}
    opensees_canonical_breadth_summary_line = str(
        opensees_canonical_breadth.get("summary_line", "") or ""
    ).strip()
    global_authority_ok = bool(
        global_authority.get("contract_pass", False)
        and str(global_authority.get("reason_code", "")) == "PASS"
        and bool(global_authority_checks.get("opensees_pass", False))
        and bool(global_authority_checks.get("sac_pass", False))
        and bool(global_authority_checks.get("nheri_pass", False))
        and bool(global_authority_checks.get("holdout_manifest_pass", False))
        and bool(global_authority_checks.get("sac_min_case_count_pass", False))
        and bool(global_authority_checks.get("nheri_min_case_count_pass", False))
        and int(global_authority_summary.get("sac_case_count", 0)) >= 3
        and int(global_authority_summary.get("nheri_case_count", 0)) >= 3
    )
    wind_checks = wind_benchmark.get("checks") if isinstance(wind_benchmark.get("checks"), dict) else {}
    wind_summary = wind_benchmark.get("summary") if isinstance(wind_benchmark.get("summary"), dict) else {}
    wind_benchmark_ok = bool(
        wind_benchmark.get("contract_pass", False)
        and str(wind_benchmark.get("reason_code", "")) == "PASS"
        and bool(wind_checks.get("source_manifest_pass", False))
        and bool(wind_checks.get("wind_duration_pass", False))
        and bool(wind_checks.get("wind_reversal_pass", False))
        and bool(wind_checks.get("long_series_chunked_pass", False))
        and bool(wind_checks.get("all_cases_converged", False))
        and bool(wind_checks.get("rust_backend_used_pass", False))
        and bool(wind_checks.get("no_collapse_detected", False))
        and bool(wind_checks.get("section_family_pass", False))
        and bool(wind_checks.get("material_model_pass", False))
        and float(wind_summary.get("duration_hours", 0.0)) >= 10.0
    )
    ssi_checks = ssi_boundary.get("checks") if isinstance(ssi_boundary.get("checks"), dict) else {}
    ssi_summary = ssi_boundary.get("summary") if isinstance(ssi_boundary.get("summary"), dict) else {}
    ssi_boundary_ok = bool(
        ssi_boundary.get("contract_pass", False)
        and str(ssi_boundary.get("reason_code", "")) == "PASS"
        and bool(ssi_checks.get("case_count_pass", False))
        and bool(ssi_checks.get("ssi_nonlinear_boundary_active", False))
        and bool(ssi_checks.get("all_cases_converged", False))
        and bool(ssi_checks.get("rust_backend_used_pass", False))
        and bool(ssi_checks.get("no_collapse_detected", False))
        and bool(ssi_checks.get("shear_delta_pass", False))
        and float(ssi_summary.get("nonlinear_ratio_span", 0.0)) > 0.0
    )
    damper_checks = damper_validation.get("checks") if isinstance(damper_validation.get("checks"), dict) else {}
    damper_summary = damper_validation.get("summary") if isinstance(damper_validation.get("summary"), dict) else {}
    damper_validation_ok = bool(
        damper_validation.get("contract_pass", False)
        and str(damper_validation.get("reason_code", "")) == "PASS"
        and bool(damper_checks.get("case_count_pass", False))
        and bool(damper_checks.get("source_integrity_pass", False))
        and bool(damper_checks.get("damper_type_diversity_pass", False))
        and bool(damper_checks.get("waveform_corr_pass", False))
        and bool(damper_checks.get("phase_error_pass", False))
        and bool(damper_checks.get("residual_drift_pass", False))
        and bool(damper_checks.get("section_family_pass", False))
        and bool(damper_checks.get("material_model_pass", False))
        and int(damper_summary.get("case_count", 0)) >= 3
    )
    kds_artifacts = kds_compliance.get("artifacts") if isinstance(kds_compliance.get("artifacts"), dict) else {}
    kds_frontend_payload = kds_compliance.get("frontend_payload") if isinstance(kds_compliance.get("frontend_payload"), dict) else {}
    kds_frontend_path = str(kds_artifacts.get("kds_frontend_payload_json", ""))
    kds_frontend_ok = bool(
        kds_compliance.get("contract_pass", False)
        and str(kds_compliance.get("reason_code", "")) == "PASS"
        and bool(kds_frontend_path)
        and Path(kds_frontend_path).exists()
        and isinstance(kds_frontend_payload.get("summary_cards"), list)
        and len(kds_frontend_payload.get("summary_cards", [])) >= 3
    )
    construction_checks = construction_sequence.get("checks") if isinstance(construction_sequence.get("checks"), dict) else {}
    construction_summary = construction_sequence.get("summary") if isinstance(construction_sequence.get("summary"), dict) else {}
    construction_sequence_ok = bool(
        construction_sequence.get("contract_pass", False)
        and str(construction_sequence.get("reason_code", "")) == "PASS"
        and bool(construction_checks.get("case_count_pass", False))
        and bool(construction_checks.get("all_stages_converged", False))
        and bool(construction_checks.get("rust_backend_used_pass", False))
        and bool(construction_checks.get("stagewise_monotonic_load_pass", False))
        and bool(construction_checks.get("creep_shrinkage_applied", False))
        and bool(construction_checks.get("differential_shortening_detected", False))
        and bool(construction_checks.get("initial_stress_nonzero", False))
        and bool(construction_checks.get("initial_stress_upper_bound_pass", False))
        and bool(construction_checks.get("drift_guard_pass", False))
        and int(construction_summary.get("stage_count", 0)) >= 8
    )
    diaphragm_checks = flexible_diaphragm.get("checks") if isinstance(flexible_diaphragm.get("checks"), dict) else {}
    diaphragm_summary = flexible_diaphragm.get("summary") if isinstance(flexible_diaphragm.get("summary"), dict) else {}
    flexible_diaphragm_ok = bool(
        flexible_diaphragm.get("contract_pass", False)
        and str(flexible_diaphragm.get("reason_code", "")) == "PASS"
        and bool(diaphragm_checks.get("case_count_pass", False))
        and bool(diaphragm_checks.get("shell_beam_mix_topology_pass", False))
        and bool(diaphragm_checks.get("flexible_diaphragm_modeled", False))
        and bool(diaphragm_checks.get("all_cases_converged", False))
        and bool(diaphragm_checks.get("rust_backend_used_pass", False))
        and bool(diaphragm_checks.get("flex_amplification_band_pass", False))
        and bool(diaphragm_checks.get("slab_shear_stress_pass", False))
        and bool(diaphragm_checks.get("max_flexible_drift_pass", False))
        and int(diaphragm_summary.get("case_count", 0)) >= 2
    )
    repro_checks = repro_version_lock.get("checks") if isinstance(repro_version_lock.get("checks"), dict) else {}
    repro_manifest_path = str(repro_version_lock.get("lock_manifest", ""))
    repro_version_lock_ok = bool(
        repro_version_lock.get("contract_pass", False)
        and str(repro_version_lock.get("reason_code", "")) == "PASS"
        and bool(repro_checks.get("case_count_pass", False))
        and bool(repro_checks.get("seed_locked", False))
        and bool(repro_checks.get("input_hashes_frozen", False))
        and bool(repro_checks.get("model_hashes_frozen", False))
        and bool(repro_checks.get("no_missing_model_artifacts", False))
        and bool(repro_checks.get("rust_backend_used_pass", False))
        and bool(repro_checks.get("replay_exact_match", False))
        and bool(repro_checks.get("lock_manifest_written", False))
        and bool(repro_manifest_path)
        and Path(repro_manifest_path).exists()
    )
    registry_checks = release_registry.get("checks") if isinstance(release_registry.get("checks"), dict) else {}
    registry_sig = release_registry.get("signature") if isinstance(release_registry.get("signature"), dict) else {}
    registry_pubkey = str(registry_sig.get("public_key_path", ""))
    release_registry_ok = bool(
        release_registry.get("contract_pass", False)
        and str(release_registry.get("reason_code", "")) == "PASS"
        and bool(registry_checks.get("green_reports_pass", False))
        and bool(registry_checks.get("lock_manifest_hash_match", False))
        and bool(registry_checks.get("artifact_hashes_present_pass", False))
        and bool(registry_checks.get("public_key_written_pass", False))
        and bool(registry_checks.get("signature_generated_pass", False))
        and bool(registry_checks.get("signature_verified_pass", False))
        and bool(registry_pubkey)
        and Path(registry_pubkey).exists()
    )
    performance_profiling_summary_line = str(performance_profiling.get("summary_line", "") or "")
    performance_profiling_ok = True if not performance_profiling_path.exists() else bool(performance_profiling.get("contract_pass", False))
    solver_hip_checks = solver_hip_e2e.get("checks") if isinstance(solver_hip_e2e.get("checks"), dict) else {}
    solver_hip_e2e_ok = bool(
        solver_hip_e2e.get("contract_pass", False)
        and bool(solver_hip_checks.get("strict_probe_pass", False))
        and bool(solver_hip_checks.get("nonlinear_frame_gpu_pass", False))
        and bool(solver_hip_checks.get("ndtha_gpu_pass", False))
        and bool(solver_hip_checks.get("track_gpu_pass", False))
        and bool(solver_hip_checks.get("all_main_loops_gpu_pass", False))
        and bool(solver_hip_checks.get("no_cpu_backend_pass", False))
        and bool(solver_hip_checks.get("no_cpu_required_pass", False))
        and bool(solver_hip_checks.get("no_cpu_fallback_pass", False))
    )
    solver_truthfulness_checks = (
        solver_truthfulness.get("checks") if isinstance(solver_truthfulness.get("checks"), dict) else {}
    )
    solver_truthfulness_summary_line = str(solver_truthfulness.get("summary_line", "") or "")
    solver_truthfulness_ok = bool(
        solver_truthfulness.get("contract_pass", False)
        and bool(solver_truthfulness_checks.get("runtime_truthfulness_pass", False))
        and bool(solver_truthfulness_checks.get("no_surrogate_runtime_markers_pass", False))
        and bool(solver_truthfulness_checks.get("no_cpu_fallback_pass", False))
        and bool(solver_truthfulness_checks.get("solver_hip_production_proof_pass", True))
    )
    hardest_external_10case_kickoff_summary = (
        hardest_external_10case_kickoff.get("summary")
        if isinstance(hardest_external_10case_kickoff.get("summary"), dict)
        else {}
    )
    hardest_external_10case_kickoff_summary_line = str(
        hardest_external_10case_kickoff.get("summary_line", "") or "Hardest external 10-case kickoff: unavailable"
    ).strip()
    hardest_external_10case_kickoff_ok = bool(
        hardest_external_10case_kickoff.get("contract_pass", False)
        and bool(
            hardest_external_10case_kickoff_summary.get(
                "ready_to_start_now",
                hardest_external_10case_kickoff.get("contract_pass", False),
            )
        )
        and int(hardest_external_10case_kickoff_summary.get("ready_case_count", 10) or 0) >= 10
    )
    rc_lock_checks = rc_benchmark_lock.get("checks") if isinstance(rc_benchmark_lock.get("checks"), dict) else {}
    rc_benchmark_lock_ok = bool(
        rc_benchmark_lock.get("contract_pass", False)
        and bool(rc_lock_checks.get("case_count_pass", False))
        and bool(rc_lock_checks.get("finite_pass", False))
        and bool(rc_lock_checks.get("all_ranges_pass", False))
        and bool(rc_lock_checks.get("cracking_case_pass", False))
        and bool(rc_lock_checks.get("bond_slip_case_pass", False))
        and bool(rc_lock_checks.get("creep_case_pass", False))
        and bool(rc_lock_checks.get("slab_wall_case_pass", False))
    )
    mgt_checks = midas_mgt_conversion.get("checks") if isinstance(midas_mgt_conversion.get("checks"), dict) else {}
    mgt_source = midas_mgt_conversion.get("source_provenance") if isinstance(midas_mgt_conversion.get("source_provenance"), dict) else {}
    mgt_metrics = midas_mgt_conversion.get("metrics") if isinstance(midas_mgt_conversion.get("metrics"), dict) else {}
    mgt_artifacts = midas_mgt_conversion.get("artifacts") if isinstance(midas_mgt_conversion.get("artifacts"), dict) else {}
    mgt_json_path = str(mgt_artifacts.get("json_out", ""))
    mgt_npz_path = str(mgt_artifacts.get("npz_out", ""))
    midas_mgt_conversion_ok = bool(
        midas_mgt_conversion.get("contract_pass", False)
        and str(midas_mgt_conversion.get("reason_code", "")) == "PASS"
        and bool(mgt_checks.get("has_nodes", False))
        and bool(mgt_checks.get("has_elements", False))
        and bool(mgt_checks.get("synthetic_source_blocked", False))
        and bool(mgt_checks.get("unknown_section_policy_pass", False))
        and bool(mgt_checks.get("element_skip_budget_pass", False))
        and int(mgt_metrics.get("node_count", 0)) >= 100
        and int(mgt_metrics.get("element_count", 0)) >= 100
        and int(mgt_metrics.get("element_rows_skipped", 1)) == 0
        and str(mgt_source.get("source_family", "")) == "midas_mgt"
        and bool(mgt_json_path) and Path(mgt_json_path).exists()
        and bool(mgt_npz_path) and Path(mgt_npz_path).exists()
    )

    gpu_strict_ok = True
    if bool(args.require_gpu_strict):
        gpu_strict_ok = bool(
            scaleout_io_ok
            and bool((scaleout_io_report.get("checks") or {}).get("gpu_strict_pass", False))
            and bool((phase3_pipeline.get("checks") or {}).get("gpu_strict_pass", False))
            and bool((partitioned_scaleout.get("checks") or {}).get("gpu_strict_pass", False))
        )
    if bool(args.require_gpu_strict):
        partitioned_scaleout_ok = bool(
            partitioned_scaleout_ok and bool((partitioned_scaleout.get("checks") or {}).get("gpu_strict_pass", False))
        )

    if str(args.ci_mode) == "nightly":
        nightly_10m_ok = bool((partitioned_scaleout.get("checks") or {}).get("nightly_scale_pass", False))
    else:
        nightly_10m_ok = True
    nightly_10m_repro_ok = True
    if str(args.ci_mode) == "nightly":
        repro_checks = nightly_10m_repro.get("checks") if isinstance(nightly_10m_repro.get("checks"), dict) else {}
        nightly_10m_repro_ok = bool(
            nightly_10m_repro.get("contract_pass", False)
            and bool(repro_checks.get("run_count_sufficient", False))
            and bool(repro_checks.get("all_runs_pass", False))
            and bool(repro_checks.get("has_10m_rows", False))
            and bool(repro_checks.get("latency_cov_pass", False))
            and bool(repro_checks.get("working_set_cov_pass", False))
        )
    hip_kernel_checks = hip_kernel_smoke.get("checks") if isinstance(hip_kernel_smoke.get("checks"), dict) else {}
    hip_kernel_smoke_ok = bool(
        hip_kernel_smoke.get("contract_pass", False)
        and bool(hip_kernel_checks.get("hip_compiler_present", False))
        and bool(hip_kernel_checks.get("build_pass", False))
        and bool(hip_kernel_checks.get("run_pass", False))
        and bool(hip_kernel_checks.get("kernel_backend_pass", False))
    )
    if not bool(args.require_hip_kernel_smoke):
        hip_kernel_smoke_ok = True

    ndtha_long_checks = ndtha_long_profile.get("checks") if isinstance(ndtha_long_profile.get("checks"), dict) else {}
    ndtha_long_profile_ok = bool(
        ndtha_long_profile.get("contract_pass", False)
        and bool(ndtha_long_checks.get("all_runs_pass", False))
        and bool(ndtha_long_checks.get("rust_backend_all_runs_pass", False))
        and bool(ndtha_long_checks.get("elapsed_cov_pass", False))
        and bool(ndtha_long_checks.get("peak_vram_cov_pass", False))
    )
    if not bool(args.require_ndtha_long_profile):
        ndtha_long_profile_ok = True

    phase3_real_source_ok = bool(
        phase3_real_source_ok
        and topology_gate_ok
        and bool((phase3_pipeline.get("checks") or {}).get("benchmark_pass", False))
        and bool((phase3_pipeline.get("checks") or {}).get("noise_convergence_pass", False))
        and bool((phase3_pipeline.get("checks") or {}).get("case_diversity_pass", True))
        and bool((phase3_pipeline.get("checks") or {}).get("noise_seed_diversity_pass", True))
        and bool((phase3_pipeline.get("checks") or {}).get("noise_case_diversity_pass", True))
        and bool((phase3_pipeline.get("checks") or {}).get("noise_stagewise_pass", True))
        and bool((phase3_pipeline.get("checks") or {}).get("topology_gate_pass", False))
        and bool((phase3_pipeline.get("checks") or {}).get("shell_beam_mix_pass", False))
        and bool((phase3_pipeline.get("checks") or {}).get("sync_stress_pass", False))
        and bool((phase3_pipeline.get("checks") or {}).get("sync_backend_policy_pass", False))
    )

    if not inputs_ok:
        report = {
            "strict_rust_hip_pass": bool(strict.get("strict_rust_hip_pass", False)),
            "host_copy_share": None,
            "host_copy_share_limit": args.max_host_copy_share,
            "host_copy_share_pass": False,
            "contract_artifacts_pass": contracts_ok,
            "missing_contract_artifacts": missing_contracts,
            "priority3_checked": bool(args.priority3),
            "priority3_pass": priority_ok,
            "midas_section_library_artifacts_pass": midas_section_library_ok,
            "midas_section_library_validator": midas_section_library_validation,
            "all_pass": False,
            "reason_code": input_reason,
            "reason": REASON_CODES[input_reason],
        }
        Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
        return 1

    strict_ok = bool(strict["strict_rust_hip_pass"])
    timing = rca["timing_breakdown_seconds"]
    total = float(timing["compute"]) + float(timing["host_copy"]) + float(timing["serialization"])
    host_share = 0.0 if total <= 1e-12 else float(timing.get("host_copy", 0.0)) / total
    host_copy_ok = host_share <= args.max_host_copy_share

    if not contracts_ok:
        reason_code = "ERR_MISSING_CONTRACT_ARTIFACT"
    elif not buckling_ok:
        reason_code = "ERR_BUCKLING_EIGEN_INVALID"
    elif not energy_ok:
        reason_code = "ERR_ENERGY_MONOTONICITY"
    elif not meta_ood_ok:
        reason_code = "ERR_META_OOD_FAIL"
    elif not benchmark_ok:
        reason_code = "ERR_BENCHMARK_KPI_FAIL"
    elif not branching_ok:
        reason_code = "ERR_BRANCHING_CONTRACT_FAIL"
    elif not bifurcation_ok:
        reason_code = "ERR_BIFURCATION_CONTRACT_FAIL"
    elif not rust_onnx_ok:
        reason_code = "ERR_RUST_ONNX_CONTRACT_FAIL"
    elif not winning_ticket_ok:
        reason_code = "ERR_WINNING_TICKET_FAIL"
    elif not rust_md3bead_parity_ok:
        reason_code = "ERR_RUST_MD3BEAD_PARITY_FAIL"
    elif not lj_mapping_ok:
        reason_code = "ERR_LJ_MAPPING_FAIL"
    elif not dynamic_time_history_ok:
        reason_code = "ERR_DYNAMIC_TIME_HISTORY_FAIL"
    elif not cache_profile_ok:
        reason_code = "ERR_CACHE_PROFILE_FAIL"
    elif not p0_engine_perf_ok:
        reason_code = "ERR_P0_ENGINE_PROFILE_FAIL"
    elif not p0_core_gap_ok:
        reason_code = "ERR_P0_CORE_GAP_FAIL"
    elif not hip_kernel_smoke_ok:
        reason_code = "ERR_HIP_KERNEL_SMOKE_FAIL"
    elif not noise_stress_ok:
        reason_code = "ERR_NOISE_STRESS_FAIL"
    elif not scaleout_io_ok:
        reason_code = "ERR_SCALEOUT_IO_FAIL"
    elif not phase3_real_source_ok:
        reason_code = "ERR_REAL_SOURCE_FAIL"
    elif not topology_gate_ok:
        reason_code = "ERR_TOPOLOGY_GATE_FAIL"
    elif str(args.ci_mode) == "nightly" and not nightly_10m_ok:
        reason_code = "ERR_NIGHTLY_10M_FAIL"
    elif str(args.ci_mode) == "nightly" and not nightly_10m_repro_ok:
        reason_code = "ERR_NIGHTLY_10M_REPRO_FAIL"
    elif str(args.ci_mode) == "nightly" and not ndtha_long_profile_ok:
        reason_code = "ERR_NDTHA_LONG_PROFILE_FAIL"
    elif not partitioned_scaleout_ok:
        reason_code = "ERR_PARTITION_SCALE_FAIL"
    elif not sync_stress_ok:
        reason_code = "ERR_SYNC_STRESS_FAIL"
    elif not noise_convergence_ok:
        reason_code = "ERR_NOISE_CONVERGENCE_FAIL"
    elif not commercial_csv_gate_ok:
        reason_code = "ERR_COMMERCIAL_CSV_GATE_FAIL"
    elif not midas_mgt_conversion_ok:
        reason_code = "ERR_MIDAS_MGT_CONVERSION_FAIL"
    elif not midas_section_library_ok:
        reason_code = "ERR_MIDAS_SECTION_LIBRARY_ARTIFACT_FAIL"
    elif not midas_kds_geometry_bridge_ok:
        reason_code = "ERR_MIDAS_KDS_GEOMETRY_BRIDGE_FAIL"
    elif not midas_loadcomb_roundtrip_ok:
        reason_code = "ERR_MIDAS_LOADCOMB_ROUNDTRIP_FAIL"
    elif not solver_breadth_ok:
        reason_code = "ERR_SOLVER_BREADTH_FAIL"
    elif not element_material_breadth_ok:
        reason_code = "ERR_ELEMENT_MATERIAL_BREADTH_FAIL"
    elif not material_constitutive_ok:
        reason_code = "ERR_MATERIAL_CONSTITUTIVE_FAIL"
    elif not midas_kds_row_provenance_export_ok:
        reason_code = "ERR_MIDAS_KDS_ROW_PROVENANCE_EXPORT_FAIL"
    elif not contact_readiness_ok:
        reason_code = "ERR_CONTACT_READINESS_FAIL"
    elif bool(args.require_structural_contact) and not structural_contact_ok:
        reason_code = "ERR_STRUCTURAL_CONTACT_FAIL"
    elif not general_fe_contact_matrix_ok:
        reason_code = "ERR_GENERAL_FE_CONTACT_MATRIX_FAIL"
    elif not surface_interaction_benchmark_ok:
        reason_code = "ERR_SURFACE_INTERACTION_BENCHMARK_FAIL"
    elif not midas_interoperability_ok:
        reason_code = "ERR_MIDAS_INTEROPERABILITY_FAIL"
    elif not korean_source_ingest_gate_ok:
        reason_code = "ERR_KOREAN_SOURCE_INGEST_FAIL"
    elif not midas_native_roundtrip_ok:
        reason_code = "ERR_MIDAS_NATIVE_ROUNDTRIP_FAIL"
    elif not nonlinear_generalization_ok:
        reason_code = "ERR_NONLINEAR_GENERALIZATION_FAIL"
    elif not workflow_productization_ok:
        reason_code = "ERR_WORKFLOW_PRODUCTIZATION_FAIL"
    elif not commercial_readiness_ok:
        reason_code = "ERR_COMMERCIAL_READINESS_FAIL"
    elif not real_source_multi_ok:
        reason_code = "ERR_REAL_SOURCE_MULTI_FAIL"
    elif not nonlinear_engine_ok:
        reason_code = "ERR_NONLINEAR_ENGINE_FAIL"
    elif not pushover_stress_ok:
        reason_code = "ERR_PUSHOVER_STRESS_FAIL"
    elif not ndtha_stress_ok:
        reason_code = "ERR_NDTHA_STRESS_FAIL"
    elif not ndtha_residual_ok:
        reason_code = "ERR_NDTHA_RESIDUAL_FAIL"
    elif not pbd_review_ok:
        reason_code = "ERR_PBD_REVIEW_FAIL"
    elif not global_authority_ok:
        reason_code = "ERR_GLOBAL_AUTHORITY_FAIL"
    elif not wind_benchmark_ok:
        reason_code = "ERR_WIND_BENCHMARK_FAIL"
    elif not ssi_boundary_ok:
        reason_code = "ERR_SSI_BOUNDARY_FAIL"
    elif not damper_validation_ok:
        reason_code = "ERR_DAMPER_VALIDATION_FAIL"
    elif not kds_frontend_ok:
        reason_code = "ERR_KDS_FRONTEND_FAIL"
    elif not construction_sequence_ok:
        reason_code = "ERR_CONSTRUCTION_SEQUENCE_FAIL"
    elif not flexible_diaphragm_ok:
        reason_code = "ERR_FLEXIBLE_DIAPHRAGM_FAIL"
    elif not repro_version_lock_ok:
        reason_code = "ERR_REPRO_VERSION_LOCK_FAIL"
    elif not release_registry_ok:
        reason_code = "ERR_RELEASE_REGISTRY_FAIL"
    elif not performance_profiling_ok:
        reason_code = "ERR_PERFORMANCE_PROFILING_FAIL"
    elif not solver_truthfulness_ok:
        reason_code = "ERR_SOLVER_TRUTHFULNESS_FAIL"
    elif not hardest_external_10case_kickoff_ok:
        reason_code = "ERR_HARDEST_EXTERNAL_10CASE_KICKOFF_FAIL"
    elif bool(args.require_solver_hip_e2e) and not solver_hip_e2e_ok:
        reason_code = "ERR_SOLVER_HIP_E2E_FAIL"
    elif not rc_benchmark_lock_ok:
        reason_code = "ERR_RC_BENCHMARK_LOCK_FAIL"
    elif not gpu_strict_ok:
        reason_code = "ERR_GPU_STRICT_FAIL"
    elif not phasea_contract_ok:
        reason_code = "ERR_PHASEA_CONTRACT_FAIL"
    elif not phaseb_track_ok:
        reason_code = "ERR_PHASEB_TRACK_FAIL"
    elif not phased_multidomain_ok:
        reason_code = "ERR_PHASED_ML_FAIL"
    elif not phasee_integrated_ok:
        reason_code = "ERR_PHASEE_INTEGRATED_FAIL"
    elif not phasef_resilience_ok:
        reason_code = "ERR_PHASEF_RESILIENCE_FAIL"
    elif not priority_ok:
        reason_code = "ERR_PRIORITY3_FAIL"
    elif not strict_ok:
        reason_code = "ERR_STRICT_FAIL"
    elif not host_copy_ok:
        reason_code = "ERR_HOST_COPY_SHARE"
    else:
        reason_code = "PASS"

    report = {
        "schema_version": "2.0",
        "run_id": "phase1-ci-gate",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "strict_rust_hip_pass": strict_ok,
        "host_copy_share": host_share,
        "host_copy_share_limit": args.max_host_copy_share,
        "host_copy_share_pass": host_copy_ok,
        "contract_artifacts_pass": contracts_ok,
        "missing_contract_artifacts": missing_contracts,
        "priority3_checked": bool(args.priority3),
        "priority3_pass": priority_ok,
        "priority3_reason_code": None if priority_ok else priority_reason,
        "physics_energy_monotonic_pass": energy_ok,
        "meta_ood_generalization_pass": meta_ood_ok,
        "buckling_contract_pass": buckling_ok,
        "benchmark_kpi_pass": benchmark_ok,
        "branching_contract_pass": branching_ok,
        "bifurcation_contract_pass": bifurcation_ok,
        "rust_onnx_contract_pass": rust_onnx_ok,
        "winning_ticket_contract_pass": winning_ticket_ok,
        "rust_md3bead_parity_pass": rust_md3bead_parity_ok,
        "lj_mapping_contract_pass": lj_mapping_ok,
        "dynamic_time_history_pass": dynamic_time_history_ok,
        "cache_profile_pass": cache_profile_ok,
        "p0_engine_perf_pass": p0_engine_perf_ok,
        "p0_core_gap_pass": p0_core_gap_ok,
        "hip_kernel_smoke_pass": hip_kernel_smoke_ok,
        "noise_stress_pass": noise_stress_ok,
        "scaleout_io_pass": scaleout_io_ok,
        "phase3_real_source_pass": phase3_real_source_ok,
        "topology_gate_pass": topology_gate_ok,
        "shell_beam_mix_pass": shell_beam_mix_ok,
        "partitioned_scaleout_pass": partitioned_scaleout_ok,
        "sync_stress_pass": sync_stress_ok,
        "noise_convergence_pass": noise_convergence_ok,
        "commercial_csv_gate_pass": commercial_csv_gate_ok,
        "midas_mgt_conversion_pass": midas_mgt_conversion_ok,
        "midas_section_library_artifacts_pass": midas_section_library_ok,
        "midas_section_library_summary_line": str(midas_section_library_validation.get("summary_line", "MIDAS section-library: unavailable")),
        "midas_section_library_validator": midas_section_library_validation,
        "midas_kds_geometry_bridge_pass": midas_kds_geometry_bridge_ok,
        "midas_kds_geometry_bridge_summary_line": str(
            midas_kds_geometry_bridge_validation.get("summary_line", "MIDAS kds-geometry-bridge: unavailable")
        ),
        "midas_kds_geometry_bridge_load_crosswalk_summary_line": str(
            midas_kds_geometry_bridge_load_crosswalk_surface.get("summary_line", "") or ""
        ),
        "midas_kds_geometry_bridge_load_crosswalk_count": int(
            midas_kds_geometry_bridge_load_crosswalk_surface.get("count", 0) or 0
        ),
        "midas_kds_geometry_bridge_load_crosswalk_expected": int(
            midas_kds_geometry_bridge_load_crosswalk_surface.get("expected", 0) or 0
        ),
        "midas_kds_geometry_bridge_load_crosswalk_status": str(
            midas_kds_geometry_bridge_load_crosswalk_surface.get("status", "") or ""
        ),
        "midas_kds_geometry_bridge_load_crosswalk_pass": midas_kds_geometry_bridge_load_crosswalk_surface.get(
            "pass"
        ),
        "midas_kds_geometry_bridge_semantic_crosswalk_summary_line": str(
            midas_kds_geometry_bridge_semantic_crosswalk_surface.get("summary_line", "") or ""
        ),
        "midas_kds_geometry_bridge_semantic_crosswalk_count": int(
            midas_kds_geometry_bridge_semantic_crosswalk_surface.get("count", 0) or 0
        ),
        "midas_kds_geometry_bridge_semantic_crosswalk_expected": int(
            midas_kds_geometry_bridge_semantic_crosswalk_surface.get("expected", 0) or 0
        ),
        "midas_kds_geometry_bridge_semantic_crosswalk_status": str(
            midas_kds_geometry_bridge_semantic_crosswalk_surface.get("status", "") or ""
        ),
        "midas_kds_geometry_bridge_semantic_crosswalk_pass": midas_kds_geometry_bridge_semantic_crosswalk_surface.get(
            "pass"
        ),
        "midas_kds_geometry_bridge_full_member_crosswalk_summary_line": str(
            midas_kds_geometry_bridge_full_member_crosswalk_surface.get("summary_line", "") or ""
        ),
        "midas_kds_geometry_bridge_full_member_crosswalk_count": int(
            midas_kds_geometry_bridge_full_member_crosswalk_surface.get("count", 0) or 0
        ),
        "midas_kds_geometry_bridge_full_member_crosswalk_expected": int(
            midas_kds_geometry_bridge_full_member_crosswalk_surface.get("expected", 0) or 0
        ),
        "midas_kds_geometry_bridge_full_member_crosswalk_status": str(
            midas_kds_geometry_bridge_full_member_crosswalk_surface.get("status", "") or ""
        ),
        "midas_kds_geometry_bridge_full_member_crosswalk_pass": midas_kds_geometry_bridge_full_member_crosswalk_surface.get(
            "pass"
        ),
        "midas_kds_geometry_bridge_full_section_crosswalk_summary_line": str(
            midas_kds_geometry_bridge_full_section_crosswalk_surface.get("summary_line", "") or ""
        ),
        "midas_kds_geometry_bridge_full_section_crosswalk_count": int(
            midas_kds_geometry_bridge_full_section_crosswalk_surface.get("count", 0) or 0
        ),
        "midas_kds_geometry_bridge_full_section_crosswalk_expected": int(
            midas_kds_geometry_bridge_full_section_crosswalk_surface.get("expected", 0) or 0
        ),
        "midas_kds_geometry_bridge_full_section_crosswalk_status": str(
            midas_kds_geometry_bridge_full_section_crosswalk_surface.get("status", "") or ""
        ),
        "midas_kds_geometry_bridge_full_section_crosswalk_pass": midas_kds_geometry_bridge_full_section_crosswalk_surface.get(
            "pass"
        ),
        "midas_kds_geometry_bridge_full_load_crosswalk_summary_line": str(
            midas_kds_geometry_bridge_full_load_crosswalk_surface.get("summary_line", "") or ""
        ),
        "midas_kds_geometry_bridge_full_load_crosswalk_count": int(
            midas_kds_geometry_bridge_full_load_crosswalk_surface.get("count", 0) or 0
        ),
        "midas_kds_geometry_bridge_full_load_crosswalk_expected": int(
            midas_kds_geometry_bridge_full_load_crosswalk_surface.get("expected", 0) or 0
        ),
        "midas_kds_geometry_bridge_full_load_crosswalk_status": str(
            midas_kds_geometry_bridge_full_load_crosswalk_surface.get("status", "") or ""
        ),
        "midas_kds_geometry_bridge_full_load_crosswalk_pass": midas_kds_geometry_bridge_full_load_crosswalk_surface.get(
            "pass"
        ),
        "midas_kds_geometry_bridge_full_crosswalk_depth": int(
            midas_kds_geometry_bridge_validation.get("full_crosswalk_depth", 0) or 0
        ),
        "midas_kds_geometry_bridge_validator": midas_kds_geometry_bridge_validation,
        "midas_loadcomb_roundtrip_pass": midas_loadcomb_roundtrip_ok,
        "midas_loadcomb_roundtrip_summary_line": str(midas_loadcomb_roundtrip_validation.get("summary_line", "MIDAS loadcomb-roundtrip: unavailable")),
        "midas_loadcomb_roundtrip_validator": midas_loadcomb_roundtrip_validation,
        "solver_breadth_pass": solver_breadth_ok,
        "solver_breadth_summary_line": solver_breadth_summary_line,
        "solver_breadth_report": solver_breadth,
        "element_material_breadth_pass": element_material_breadth_ok,
        "element_material_breadth_summary_line": element_material_breadth_summary_line,
        "element_material_breadth_report": element_material_breadth,
        "material_constitutive_pass": material_constitutive_ok,
        "material_constitutive_summary_line": material_constitutive_summary_line,
        "material_constitutive_report": material_constitutive,
        "steel_composite_constitutive_gate_available": steel_composite_constitutive_gate_available,
        "steel_composite_constitutive_gate_pass": steel_composite_constitutive_gate_ok,
        "steel_composite_constitutive_gate_summary_line": steel_composite_constitutive_gate_summary_line,
        "steel_composite_constitutive_gate_report": steel_composite_constitutive_gate,
        "midas_kds_row_provenance_export_pass": midas_kds_row_provenance_export_ok,
        "midas_kds_row_provenance_export_summary_line": midas_kds_row_provenance_export_summary_line,
        "midas_kds_row_provenance_export_report": midas_kds_row_provenance_export,
        "contact_readiness_pass": contact_readiness_ok,
        "contact_readiness_summary_line": contact_readiness_summary_line,
        "contact_readiness_report": contact_readiness,
        "foundation_soil_link_pass": foundation_soil_link_ok,
        "foundation_soil_link_summary_line": foundation_soil_link_summary_line,
        "foundation_soil_link_report": foundation_soil_link,
        "support_search_pass": bool(support_search_pass and node_surface_proxy_pass),
        "support_search_summary_line": support_search_summary_line,
        "support_search_count": int(support_search_count),
        "node_surface_proxy_count": int(node_surface_proxy_count),
        "support_depth_score": int(support_depth_score),
        "support_families_count": int(support_search_surface.get("support_families_count", 0)),
        "proxy_families_count": int(support_search_surface.get("proxy_families_count", 0)),
        "structural_contact_pass": structural_contact_ok,
        "structural_contact_summary_line": structural_contact_summary_line,
        "structural_contact_report": structural_contact,
        "structural_contact_required": bool(args.require_structural_contact),
        "general_fe_contact_matrix_pass": general_fe_contact_matrix_ok,
        "general_fe_contact_matrix_summary_line": general_fe_contact_matrix_summary_line,
        "general_fe_contact_surface_summary_line": general_fe_contact_surface_summary_line,
        "general_fe_contact_surface_status": str(general_fe_contact_surface.get("status", "") or ""),
        "general_fe_contact_support_search_count": int(general_fe_contact_surface.get("support_search_count", 0) or 0),
        "general_fe_contact_node_surface_proxy_count": int(
            general_fe_contact_surface.get("node_surface_proxy_count", 0) or 0
        ),
        "general_fe_contact_support_depth_score": int(general_fe_contact_surface.get("support_depth_score", 0) or 0),
        "general_fe_contact_coupling_depth_score": int(general_fe_contact_surface.get("coupling_depth_score", 0) or 0),
        "general_fe_contact_support_family_count": int(general_fe_contact_surface.get("support_family_count", 0) or 0),
        "general_fe_contact_support_family_required_count": int(
            general_fe_contact_surface.get("support_family_required_count", 0) or 0
        ),
        "general_fe_contact_proxy_family_count": int(general_fe_contact_surface.get("proxy_family_count", 0) or 0),
        "general_fe_contact_proxy_family_required_count": int(
            general_fe_contact_surface.get("proxy_family_required_count", 0) or 0
        ),
        "general_fe_contact_surface_pass": bool(
            general_fe_contact_surface.get("support_search_pass", False)
            and general_fe_contact_surface.get("node_surface_proxy_pass", False)
            and general_fe_contact_surface.get("support_family_pass", False)
            and general_fe_contact_surface.get("proxy_family_pass", False)
        ),
        "general_fe_contact_matrix_report": general_fe_contact_matrix,
        "surface_interaction_benchmark_pass": surface_interaction_benchmark_ok,
        "surface_interaction_benchmark_summary_line": surface_interaction_benchmark_summary_line,
        "surface_interaction_benchmark_report": surface_interaction_benchmark,
        "midas_interoperability_pass": midas_interoperability_ok,
        "midas_interoperability_summary_line": midas_interoperability_summary_line,
        "midas_interoperability_report": midas_interoperability,
        "korean_source_ingest_gate_pass": korean_source_ingest_gate_ok,
        "korean_source_ingest_gate_summary_line": korean_source_ingest_gate_summary_line,
        "korean_source_ingest_gate_report": korean_source_ingest_gate,
        "midas_native_roundtrip_pass": midas_native_roundtrip_ok,
        "midas_native_roundtrip_summary_line": midas_native_roundtrip_summary_line,
        "midas_native_roundtrip_report": midas_native_roundtrip,
        "midas_exact_roundtrip_closure_pass": midas_exact_roundtrip_closure_ok,
        "midas_exact_roundtrip_closure_summary_line": midas_exact_roundtrip_closure_summary_line,
        "midas_exact_roundtrip_closure_scope_available": midas_exact_roundtrip_closure_scope_available,
        "midas_exact_roundtrip_closure_scope_summary": midas_exact_roundtrip_closure_scope_summary,
        "midas_exact_roundtrip_closure_report": midas_exact_roundtrip_closure,
        "load_combination_engine_gate_available": load_combination_engine_gate_available,
        "load_combination_engine_gate_pass": load_combination_engine_gate_ok,
        "load_combination_engine_gate_summary_line": load_combination_engine_gate_summary_line,
        "load_combination_engine_gate_summary": load_combination_engine_gate_summary,
        "load_combination_engine_gate_report": load_combination_engine_gate,
        "panel_zone_clash_report_available": panel_zone_clash_available,
        "panel_zone_3d_clash_ready": panel_zone_3d_clash_ready,
        "panel_zone_constructability_mode": panel_zone_report_mode or ("panel_zone_3d_clash_verified" if panel_zone_3d_clash_ready else "scalar_proxy_hard_gate_only"),
        "panel_zone_constructability_reason": panel_zone_report_reason
        or (
            "Panel-zone 3D clash artifact is attached."
            if panel_zone_3d_clash_ready
            else "Constructability currently relies on scalar detailing/congestion/anchorage hard gates; no 3D panel-zone clash and anchorage recomputation artifact is attached."
        ),
        "panel_zone_proxy_candidate_count": panel_zone_proxy_candidate_count,
        "panel_zone_source_artifact_kind": panel_zone_source_artifact_kind,
        "panel_zone_source_artifact_path": panel_zone_source_artifact_path,
        "panel_zone_source_contract_mode": panel_zone_source_contract_mode,
        "panel_zone_internal_engine_complete": panel_zone_internal_engine_complete,
        "panel_zone_external_validation_pending": panel_zone_external_validation_pending,
        "panel_zone_validation_boundary": panel_zone_validation_boundary,
        "panel_zone_status_label": panel_zone_status_label,
        "panel_zone_advisory_only": panel_zone_advisory_only,
        "panel_zone_release_blocking": panel_zone_release_blocking,
        "panel_zone_external_validation_status_label": panel_zone_external_validation_status_label,
        "panel_zone_external_validation_advisory_only": panel_zone_external_validation_advisory_only,
        "panel_zone_external_validation_release_blocking": panel_zone_external_validation_release_blocking,
        "panel_zone_clash_report": panel_zone_clash,
        "irregular_structure_collection_gate_pass": irregular_structure_collection_gate_ok,
        "irregular_structure_collection_gate_summary_line": irregular_structure_collection_gate_summary_line,
        "irregular_structure_collection_gate_report": irregular_structure_collection_gate,
        "irregular_top5_execution_manifest_summary_line": irregular_top5_execution_manifest_summary_line,
        "irregular_top5_execution_manifest_report": irregular_top5_execution_manifest,
        "nonlinear_generalization_pass": nonlinear_generalization_ok,
        "nonlinear_generalization_summary_line": nonlinear_generalization_summary_line,
        "nonlinear_generalization_report": nonlinear_generalization,
        "workflow_productization_pass": workflow_productization_ok,
        "workflow_productization_summary_line": workflow_productization_summary_line,
        "workflow_results_explorer_traceability_pass": workflow_results_explorer_traceability_pass,
        "workflow_results_explorer_traceability_available": bool(
            workflow_productization_summary.get("results_explorer_traceability_available", False)
        ),
        "workflow_results_explorer_traceability_source_report_count": int(
            workflow_productization_summary.get("results_explorer_traceability_source_report_count", 0) or 0
        ),
        "workflow_results_explorer_traceability_audit_report_count": int(
            workflow_productization_summary.get("results_explorer_traceability_audit_report_count", 0) or 0
        ),
        "workflow_results_explorer_traceability_output_report_count": int(
            workflow_productization_summary.get("results_explorer_traceability_output_report_count", 0) or 0
        ),
        "workflow_productization_report": workflow_productization,
        "commercial_benchmark_breadth_summary_line": commercial_benchmark_breadth_summary_line,
        "commercial_readiness_summary_line": commercial_readiness_summary_line,
        "commercial_readiness_pass": commercial_readiness_ok,
        "real_source_multi_pass": real_source_multi_ok,
        "nonlinear_engine_pass": nonlinear_engine_ok,
        "pushover_stress_pass": pushover_stress_ok,
        "ndtha_stress_pass": ndtha_stress_ok,
        "ndtha_step_series_depth": int(ndtha_step_series_depth),
        "ndtha_material_pass": bool(ndtha_material_surface.get("material_pass", False)),
        "ndtha_material_summary_line": ndtha_material_summary_line,
        "ndtha_material_depth": int(ndtha_material_depth),
        "ndtha_residual_gate_pass": ndtha_residual_ok,
        "pbd_review_pass": pbd_review_ok,
        "global_authority_gate_pass": global_authority_ok,
        "wind_benchmark_pass": wind_benchmark_ok,
        "ssi_boundary_pass": ssi_boundary_ok,
        "damper_validation_pass": damper_validation_ok,
        "kds_frontend_pass": kds_frontend_ok,
        "construction_sequence_pass": construction_sequence_ok,
        "flexible_diaphragm_pass": flexible_diaphragm_ok,
        "repro_version_lock_pass": repro_version_lock_ok,
        "release_registry_pass": release_registry_ok,
        "performance_profiling_pass": performance_profiling_ok,
        "performance_profiling_summary_line": performance_profiling_summary_line,
        "performance_profiling_report": performance_profiling,
        "solver_truthfulness_pass": solver_truthfulness_ok,
        "solver_truthfulness_summary_line": solver_truthfulness_summary_line,
        "solver_truthfulness_report": solver_truthfulness,
        "hardest_external_10case_kickoff_pass": hardest_external_10case_kickoff_ok,
        "hardest_external_10case_kickoff_summary_line": hardest_external_10case_kickoff_summary_line,
        "hardest_external_10case_kickoff_report": hardest_external_10case_kickoff,
        "measured_benchmark_breadth_summary_line": measured_benchmark_breadth_summary_line,
        "measured_benchmark_breadth_report": measured_benchmark_breadth,
        "opensees_canonical_breadth_summary_line": opensees_canonical_breadth_summary_line,
        "opensees_canonical_breadth_report": opensees_canonical_breadth,
        "solver_hip_e2e_pass": solver_hip_e2e_ok,
        "rc_benchmark_lock_pass": rc_benchmark_lock_ok,
        "gpu_strict_pass": gpu_strict_ok,
        "nightly_10m_pass": nightly_10m_ok,
        "nightly_10m_repro_pass": nightly_10m_repro_ok,
        "ndtha_long_profile_pass": ndtha_long_profile_ok,
        "phasea_contract_pass": phasea_contract_ok,
        "phaseb_track_contract_pass": phaseb_track_ok,
        "phased_multidomain_contract_pass": phased_multidomain_ok,
        "phasee_integrated_contract_pass": phasee_integrated_ok,
        "phasef_resilience_contract_pass": phasef_resilience_ok,
        "committee_summary_snapshot": {
            "performance_profiling_summary_line": performance_profiling_summary_line,
            "solver_truthfulness_summary_line": solver_truthfulness_summary_line,
            "hardest_external_10case_kickoff_summary_line": hardest_external_10case_kickoff_summary_line,
            "measured_benchmark_breadth_summary_line": measured_benchmark_breadth_summary_line,
            "opensees_canonical_breadth_summary_line": opensees_canonical_breadth_summary_line,
            "korean_source_ingest_gate_summary_line": korean_source_ingest_gate_summary_line,
            "midas_native_roundtrip_summary_line": midas_native_roundtrip_summary_line,
            "midas_exact_roundtrip_closure_summary_line": midas_exact_roundtrip_closure_summary_line,
            "midas_exact_roundtrip_closure_scope_available": midas_exact_roundtrip_closure_scope_available,
            "midas_exact_roundtrip_closure_scope_summary": midas_exact_roundtrip_closure_scope_summary,
        "load_combination_engine_gate_available": load_combination_engine_gate_available,
        "load_combination_engine_gate_summary_line": load_combination_engine_gate_summary_line,
        "load_combination_engine_gate_summary": load_combination_engine_gate_summary,
        "panel_zone_clash_report_available": panel_zone_clash_available,
        "panel_zone_3d_clash_ready": panel_zone_3d_clash_ready,
        "panel_zone_constructability_mode": panel_zone_report_mode or ("panel_zone_3d_clash_verified" if panel_zone_3d_clash_ready else "scalar_proxy_hard_gate_only"),
        "panel_zone_constructability_reason": panel_zone_report_reason
        or (
            "Panel-zone 3D clash artifact is attached."
            if panel_zone_3d_clash_ready
            else "Constructability currently relies on scalar detailing/congestion/anchorage hard gates; no 3D panel-zone clash and anchorage recomputation artifact is attached."
        ),
        "panel_zone_proxy_candidate_count": panel_zone_proxy_candidate_count,
        "panel_zone_source_artifact_kind": panel_zone_source_artifact_kind,
        "panel_zone_source_artifact_path": panel_zone_source_artifact_path,
        "panel_zone_source_contract_mode": panel_zone_source_contract_mode,
        "panel_zone_internal_engine_complete": panel_zone_internal_engine_complete,
        "panel_zone_external_validation_pending": panel_zone_external_validation_pending,
        "panel_zone_validation_boundary": panel_zone_validation_boundary,
        "panel_zone_status_label": panel_zone_status_label,
        "panel_zone_advisory_only": panel_zone_advisory_only,
        "panel_zone_release_blocking": panel_zone_release_blocking,
        "panel_zone_external_validation_pending": panel_zone_external_validation_pending,
        "panel_zone_external_validation_status_label": panel_zone_external_validation_status_label,
        "steel_composite_constitutive_gate_available": steel_composite_constitutive_gate_available,
        "steel_composite_constitutive_gate_summary_line": steel_composite_constitutive_gate_summary_line,
        "steel_composite_constitutive_gate_pass": steel_composite_constitutive_gate_ok,
        "irregular_structure_collection_gate_summary_line": irregular_structure_collection_gate_summary_line,
        "irregular_top5_execution_manifest_summary_line": irregular_top5_execution_manifest_summary_line,
        },
        "reports": {
            "performance_profiling": args.performance_profiling_report,
            "solver_truthfulness": args.solver_truthfulness,
            "hardest_external_10case_kickoff": args.hardest_external_10case_kickoff_report,
            "measured_benchmark_breadth": str(measured_benchmark_breadth_path),
            "opensees_canonical_breadth": str(opensees_canonical_breadth_path),
            "korean_source_ingest_gate": args.korean_source_ingest_gate_report,
            "midas_native_roundtrip": args.midas_native_roundtrip_report,
            "midas_exact_roundtrip_closure": args.midas_exact_roundtrip_closure_report,
            "load_combination_engine_gate": args.load_combination_engine_gate_report,
            "panel_zone_clash_report": args.panel_zone_clash_report,
            "steel_composite_constitutive_gate": args.steel_composite_constitutive_gate_report,
            "irregular_structure_collection_gate": args.irregular_structure_collection_gate_report,
            "irregular_top5_execution_manifest": args.irregular_top5_execution_manifest,
        },
        "all_pass": strict_ok and host_copy_ok and contracts_ok and energy_ok and meta_ood_ok and buckling_ok and benchmark_ok and branching_ok and bifurcation_ok and rust_onnx_ok and winning_ticket_ok and rust_md3bead_parity_ok and lj_mapping_ok and dynamic_time_history_ok and cache_profile_ok and p0_engine_perf_ok and p0_core_gap_ok and hip_kernel_smoke_ok and noise_stress_ok and scaleout_io_ok and phase3_real_source_ok and topology_gate_ok and partitioned_scaleout_ok and sync_stress_ok and nightly_10m_ok and nightly_10m_repro_ok and ndtha_long_profile_ok and noise_convergence_ok and commercial_csv_gate_ok and midas_mgt_conversion_ok and midas_section_library_ok and midas_kds_geometry_bridge_ok and midas_loadcomb_roundtrip_ok and solver_breadth_ok and element_material_breadth_ok and material_constitutive_ok and midas_kds_row_provenance_export_ok and contact_readiness_ok and (structural_contact_ok if bool(args.require_structural_contact) else True) and general_fe_contact_matrix_ok and surface_interaction_benchmark_ok and midas_interoperability_ok and korean_source_ingest_gate_ok and midas_native_roundtrip_ok and irregular_structure_collection_gate_ok and nonlinear_generalization_ok and workflow_productization_ok and commercial_readiness_ok and real_source_multi_ok and nonlinear_engine_ok and pushover_stress_ok and ndtha_stress_ok and ndtha_residual_ok and pbd_review_ok and global_authority_ok and wind_benchmark_ok and ssi_boundary_ok and damper_validation_ok and kds_frontend_ok and construction_sequence_ok and flexible_diaphragm_ok and repro_version_lock_ok and release_registry_ok and performance_profiling_ok and solver_truthfulness_ok and hardest_external_10case_kickoff_ok and rc_benchmark_lock_ok and (solver_hip_e2e_ok if bool(args.require_solver_hip_e2e) else True) and gpu_strict_ok and phasea_contract_ok and phaseb_track_ok and phased_multidomain_ok and phasee_integrated_ok and phasef_resilience_ok and priority_ok,
        "reason_code": reason_code,
        "reason": REASON_CODES[reason_code],
    }
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")

    manifest = {
        "schema_version": "2.0",
        "run_id": "phase1-ci-gate",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "artifacts": [
            args.strict_probe,
            args.rca,
            args.out,
            *args.required_contracts,
            *( [args.priority3] if args.priority3 else [] ),
            args.solver_hip_e2e,
            args.performance_profiling_report,
            args.solver_truthfulness,
            args.hardest_external_10case_kickoff_report,
            str(measured_benchmark_breadth_path),
            str(opensees_canonical_breadth_path),
            args.midas_native_roundtrip_report,
            args.midas_exact_roundtrip_closure_report,
            args.load_combination_engine_gate_report,
            args.panel_zone_clash_report,
            args.steel_composite_constitutive_gate_report,
            args.irregular_structure_collection_gate_report,
            args.irregular_top5_execution_manifest,
            args.rc_benchmark_lock,
            args.ndtha_residual_gate_report,
            args.midas_section_library_validator,
            *midas_section_library_targets,
            args.midas_kds_geometry_bridge_validator,
            *midas_kds_geometry_bridge_targets,
            args.midas_loadcomb_roundtrip_validator,
            *midas_loadcomb_roundtrip_targets,
            args.solver_breadth_report,
            args.element_material_breadth_report,
            args.contact_readiness_report,
            args.structural_contact_report,
            args.midas_interoperability_report,
            args.korean_source_ingest_gate_report,
            args.nonlinear_generalization_report,
            args.workflow_productization_report,
        ],
    }
    Path(args.manifest).write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"Wrote CI gate report: {args.out}")
    print(f"Wrote artifact manifest: {args.manifest}")
    if not report["all_pass"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
