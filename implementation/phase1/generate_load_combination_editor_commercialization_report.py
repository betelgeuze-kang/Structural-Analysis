#!/usr/bin/env python3
"""Materialize a commercialization-oriented receipt for the load/combination editor."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from implementation.phase1.generate_native_authoring_solver_session import (
        DEFAULT_OUT as DEFAULT_SOLVER_SESSION_REPORT,
        build_native_authoring_solver_session_payload,
    )
    from implementation.phase1.load_combination_engine import (
        KDS_CONCRETE_FAMILY,
        build_load_combination_diff_receipt,
        canonicalize_kds_family,
        load_combinations_from_midas_model,
        match_runtime_to_required_editor_targets,
        summarize_runtime_combination_model,
    )
except Exception:  # pragma: no cover - local execution fallback
    from generate_native_authoring_solver_session import (  # type: ignore
        DEFAULT_OUT as DEFAULT_SOLVER_SESSION_REPORT,
        build_native_authoring_solver_session_payload,
    )
    from load_combination_engine import (  # type: ignore
        KDS_CONCRETE_FAMILY,
        build_load_combination_diff_receipt,
        canonicalize_kds_family,
        load_combinations_from_midas_model,
        match_runtime_to_required_editor_targets,
        summarize_runtime_combination_model,
    )


DEFAULT_OUT = Path(
    "implementation/phase1/release/authoring/load_combination_editor_commercialization_report.json"
)
_SIGNATURE_MODE = "sha256_stable_json_v1"
_DEFAULT_EDITOR_CONTRACT_PROFILE = "commercialization_target"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_payload(payload: Any) -> str:
    return _sha256_text(_stable_json_text(payload))


def _payload_signature_input(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    determinism = normalized.get("determinism")
    if isinstance(determinism, dict):
        trimmed = dict(determinism)
        trimmed.pop("payload_sha256", None)
        normalized["determinism"] = trimmed
    return normalized


def _runtime_payload_from_editor_seed(editor_seed: dict[str, Any]) -> dict[str, Any]:
    combination_rows = [
        {
            "name": str(row.get("name", "") or ""),
            "combination_type": str(row.get("combination_type", "") or "GEN"),
            "limit_state": str(row.get("limit_state", "") or ""),
            "entry_rows": list(row.get("entry_rows") or []),
            "factor_map": dict(row.get("factor_map") or {}),
            "expanded_factor_map": dict(row.get("expanded_factor_map") or {}),
            "referenced_combinations": list(row.get("referenced_combinations") or []),
        }
        for row in (editor_seed.get("combination_nodes") or [])
        if isinstance(row, dict) and str(row.get("name", "")).strip()
    ]
    return {
        "model": {
            "loads": {
                "load_combinations": combination_rows,
            }
        }
    }


def _resolve_runtime_summary(
    *,
    load_combination_session: dict[str, Any],
    editor_seed: dict[str, Any],
) -> dict[str, Any]:
    if isinstance(editor_seed.get("combination_nodes"), list) and editor_seed.get("combination_nodes"):
        return summarize_runtime_combination_model(_runtime_payload_from_editor_seed(editor_seed))
    runtime_summary = load_combination_session.get("runtime_summary")
    if isinstance(runtime_summary, dict):
        return dict(runtime_summary)
    return summarize_runtime_combination_model({"model": {"loads": {"load_combinations": []}}})


def _locked_authoring_controls(authoring_controls: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = {
        "familyId",
        "family_id",
        "storyCount",
        "story_count",
        "bayCount",
        "bay_count",
        "floorHeightM",
        "floor_height_m",
        "loadPatternCount",
        "load_pattern_count",
        "sectionId",
        "section_id",
    }
    return {
        str(key): value
        for key, value in authoring_controls.items()
        if str(key) in allowed_keys
    }


def _resolve_editor_contract_profile(solver_session_report: dict[str, Any]) -> str:
    load_combination_session = (
        solver_session_report.get("load_combination_session")
        if isinstance(solver_session_report.get("load_combination_session"), dict)
        else {}
    )
    editor_seed = (
        load_combination_session.get("editor_seed")
        if isinstance(load_combination_session.get("editor_seed"), dict)
        else {}
    )
    source_provenance = (
        solver_session_report.get("source_provenance")
        if isinstance(solver_session_report.get("source_provenance"), dict)
        else {}
    )
    return (
        str(load_combination_session.get("editor_contract_profile", "") or "").strip()
        or str(editor_seed.get("editor_contract_profile", "") or "").strip()
        or str(source_provenance.get("editor_contract_profile", "") or "").strip()
        or _DEFAULT_EDITOR_CONTRACT_PROFILE
    )


def _flatten_solver_load_cards(solver_session_report: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    counts = {
        "selfweight_card_count": 0,
        "nodal_card_count": 0,
        "surface_card_count": 0,
        "pressure_card_count": 0,
        "line_card_count": 0,
        "displacement_card_count": 0,
    }
    model_preview = (
        solver_session_report.get("model_preview")
        if isinstance(solver_session_report.get("model_preview"), dict)
        else {}
    )
    load_patterns = model_preview.get("load_patterns") if isinstance(model_preview.get("load_patterns"), list) else []
    for pattern in load_patterns:
        if not isinstance(pattern, dict):
            continue
        pattern_id = str(pattern.get("pattern_id", "") or "")
        pattern_label = str(pattern.get("label", "") or "")
        design_situation = str(pattern.get("design_situation", "") or "")
        for primitive in (pattern.get("primitives") or []):
            if not isinstance(primitive, dict):
                continue
            primitive_kind = str(primitive.get("kind", "") or "")
            card_type = ""
            coverage_card_types: list[str] = []
            if primitive_kind == "self_weight":
                card_type = "selfweight"
                coverage_card_types = ["selfweight"]
                counts["selfweight_card_count"] += 1
            elif primitive_kind == "point_load":
                card_type = "nodal"
                coverage_card_types = ["nodal"]
                counts["nodal_card_count"] += 1
            elif primitive_kind == "surface_pressure":
                card_type = "surface"
                coverage_card_types = ["surface", "pressure"]
                counts["surface_card_count"] += 1
                counts["pressure_card_count"] += 1
            elif primitive_kind == "line_load":
                card_type = "line"
                coverage_card_types = ["line"]
                counts["line_card_count"] += 1
            elif primitive_kind == "displacement":
                card_type = "displacement"
                coverage_card_types = ["displacement"]
                counts["displacement_card_count"] += 1
            else:
                coverage_card_types = [primitive_kind] if primitive_kind else []
            rows.append(
                {
                    "pattern_id": pattern_id,
                    "pattern_label": pattern_label,
                    "design_situation": design_situation,
                    "card_type": card_type or primitive_kind,
                    "coverage_card_types": coverage_card_types,
                    "primitive_kind": primitive_kind,
                    "case_name": str(primitive.get("case_name", "") or ""),
                    "target_scope": str(primitive.get("target_scope", "") or ""),
                    "magnitude": float(primitive.get("magnitude", 0.0) or 0.0),
                    "direction": str(primitive.get("direction", "") or ""),
                }
            )
    counts["card_count"] = len(rows)
    counts["exact_solver_load_cards_ready"] = bool(
        counts["selfweight_card_count"] > 0
        and counts["nodal_card_count"] > 0
        and counts["surface_card_count"] > 0
        and counts["pressure_card_count"] > 0
    )
    return rows, counts


def _build_required_target_match(
    *,
    required_targets: dict[str, Any],
    runtime_summary: dict[str, Any],
    design_family: str,
) -> dict[str, Any]:
    ready_count = int(required_targets.get("ready_count", 0) or 0)
    target_count = int(required_targets.get("target_count", 0) or 0)
    runtime_case_names = [
        str(case_name)
        for case_name in (runtime_summary.get("runtime_case_names") or [])
        if str(case_name).strip()
    ]
    rc_target_match_label = "n/a"
    if canonicalize_kds_family(design_family) == KDS_CONCRETE_FAMILY:
        rc_target_match_label = f"{ready_count}/{target_count}"
    return {
        "family": canonicalize_kds_family(design_family),
        "ready_count": ready_count,
        "target_count": target_count,
        "ready_ratio_label": f"{ready_count}/{target_count}",
        "rc_target_match_label": rc_target_match_label,
        "runtime_case_count": int(runtime_summary.get("runtime_case_count", 0) or 0),
        "runtime_case_names": runtime_case_names,
        "runtime_case_breadth_label": str(runtime_summary.get("runtime_case_breadth_label", "") or ""),
        "contract_pass": bool(required_targets.get("contract_pass", False)),
        "rows": list(required_targets.get("rows") or []),
        "summary_line": str(required_targets.get("summary_line", "") or ""),
    }


def _build_nested_expansion_summary(runtime_summary: dict[str, Any]) -> dict[str, Any]:
    nested_combo_count = int(runtime_summary.get("nested_combo_count", 0) or 0)
    max_nested_depth = int(runtime_summary.get("max_nested_depth", 0) or 0)
    unresolved_reference_count = int(runtime_summary.get("unresolved_reference_count", 0) or 0)
    ready = bool(
        nested_combo_count > 0
        and max_nested_depth > 1
        and unresolved_reference_count == 0
    )
    combo_depth_rows = [
        row
        for row in (runtime_summary.get("combo_depth_rows") or [])
        if isinstance(row, dict)
    ]
    return {
        "ready": ready,
        "nested_combo_count": nested_combo_count,
        "linear_combo_count": int(runtime_summary.get("linear_combo_count", 0) or 0),
        "max_nested_depth": max_nested_depth,
        "unresolved_reference_count": unresolved_reference_count,
        "unresolved_reference_names": list(runtime_summary.get("unresolved_reference_names") or []),
        "combo_depth_rows": combo_depth_rows,
        "summary_line": (
            "Nested expansion: "
            f"{'PASS' if ready else 'CHECK'} | "
            f"nested={nested_combo_count} | "
            f"max_depth={max_nested_depth} | "
            f"unresolved={unresolved_reference_count}"
        ),
    }


def _build_solver_load_card_coverage(
    *,
    solver_load_card_rows: list[dict[str, Any]],
    solver_load_card_summary: dict[str, Any],
) -> dict[str, Any]:
    required_card_types = ["selfweight", "nodal", "surface", "pressure"]
    covered_card_types = [
        card_type
        for card_type, count in (
            ("selfweight", int(solver_load_card_summary.get("selfweight_card_count", 0) or 0)),
            ("nodal", int(solver_load_card_summary.get("nodal_card_count", 0) or 0)),
            ("surface", int(solver_load_card_summary.get("surface_card_count", 0) or 0)),
            ("pressure", int(solver_load_card_summary.get("pressure_card_count", 0) or 0)),
            ("line", int(solver_load_card_summary.get("line_card_count", 0) or 0)),
            ("displacement", int(solver_load_card_summary.get("displacement_card_count", 0) or 0)),
        )
        if count > 0
    ]
    missing_card_types = [
        card_type
        for card_type in required_card_types
        if card_type not in covered_card_types
    ]
    ready = bool(solver_load_card_summary.get("exact_solver_load_cards_ready", False))
    return {
        "ready": ready,
        "required_card_types": required_card_types,
        "covered_card_types": covered_card_types,
        "missing_card_types": missing_card_types,
        "card_count": int(solver_load_card_summary.get("card_count", 0) or 0),
        "selfweight_card_count": int(solver_load_card_summary.get("selfweight_card_count", 0) or 0),
        "nodal_card_count": int(solver_load_card_summary.get("nodal_card_count", 0) or 0),
        "surface_card_count": int(solver_load_card_summary.get("surface_card_count", 0) or 0),
        "pressure_card_count": int(solver_load_card_summary.get("pressure_card_count", 0) or 0),
        "line_card_count": int(solver_load_card_summary.get("line_card_count", 0) or 0),
        "displacement_card_count": int(solver_load_card_summary.get("displacement_card_count", 0) or 0),
        "rows": solver_load_card_rows,
        "summary_line": (
            "Solver load-card coverage: "
            f"{'PASS' if ready else 'CHECK'} | "
            f"selfweight={int(solver_load_card_summary.get('selfweight_card_count', 0) or 0)} | "
            f"nodal={int(solver_load_card_summary.get('nodal_card_count', 0) or 0)} | "
            f"surface={int(solver_load_card_summary.get('surface_card_count', 0) or 0)} | "
            f"pressure={int(solver_load_card_summary.get('pressure_card_count', 0) or 0)} | "
            f"line={int(solver_load_card_summary.get('line_card_count', 0) or 0)} | "
            f"displacement={int(solver_load_card_summary.get('displacement_card_count', 0) or 0)}"
        ),
    }


def _build_code_check_assembly(runtime_summary: dict[str, Any]) -> dict[str, Any]:
    limit_state_counts = dict(runtime_summary.get("limit_state_counts") or {})
    combo_family_counts = dict(runtime_summary.get("combo_family_counts") or {})
    combo_count = int(runtime_summary.get("combo_count", 0) or 0)
    runtime_case_count = int(runtime_summary.get("runtime_case_count", 0) or 0)
    unresolved_reference_count = int(runtime_summary.get("unresolved_reference_count", 0) or 0)
    ready = bool(
        runtime_summary.get("authoring_ready", False)
        and combo_count > 0
        and runtime_case_count > 0
        and bool(limit_state_counts)
        and bool(combo_family_counts)
        and unresolved_reference_count == 0
    )
    return {
        "ready": ready,
        "authoring_ready": bool(runtime_summary.get("authoring_ready", False)),
        "combo_count": combo_count,
        "runtime_case_count": runtime_case_count,
        "runtime_case_names": list(runtime_summary.get("runtime_case_names") or []),
        "runtime_case_breadth_count": int(runtime_summary.get("runtime_case_breadth_count", 0) or 0),
        "runtime_case_breadth_label": str(runtime_summary.get("runtime_case_breadth_label", "") or ""),
        "limit_state_count": len(limit_state_counts),
        "limit_state_counts": limit_state_counts,
        "combo_family_count": len(combo_family_counts),
        "combo_family_counts": combo_family_counts,
        "unresolved_reference_count": unresolved_reference_count,
        "unresolved_reference_names": list(runtime_summary.get("unresolved_reference_names") or []),
        "summary_line": (
            "Code-check assembly: "
            f"{'PASS' if ready else 'CHECK'} | "
            f"combos={combo_count} | "
            f"limit_states={len(limit_state_counts)} | "
            f"combo_families={len(combo_family_counts)} | "
            f"breadth={str(runtime_summary.get('runtime_case_breadth_label', '') or 'n/a')} | "
            f"unresolved={unresolved_reference_count}"
        ),
    }


def _extract_commercialization_target_context(
    *,
    solver_session_report: dict[str, Any],
    load_combination_session: dict[str, Any],
    authoring_controls: dict[str, Any],
    selected_family: dict[str, Any],
) -> Any:
    candidates: list[Any] = [
        solver_session_report.get("commercialization_target"),
        load_combination_session.get("commercialization_target"),
        authoring_controls.get("commercialization_target"),
        selected_family.get("commercialization_target"),
    ]
    for container in (
        solver_session_report.get("commercialization"),
        load_combination_session.get("commercialization"),
        authoring_controls.get("commercialization"),
    ):
        if isinstance(container, dict):
            candidates.append(container)
            candidates.append(container.get("target"))
            candidates.append(container.get("mode"))
    for candidate in candidates:
        if isinstance(candidate, dict):
            if any(
                str(candidate.get(key, "") or "").strip()
                for key in (
                    "mode",
                    "target",
                    "value",
                    "kind",
                    "name",
                    "policy",
                    "status",
                    "label",
                    "reason",
                    "acceptance_reason",
                    "expansion_reason",
                )
            ):
                return dict(candidate)
            continue
        if str(candidate or "").strip():
            return str(candidate)
    return None


def _build_diff_traceability(
    *,
    solver_session_report: dict[str, Any],
    baseline_solver_session: dict[str, Any],
    family_id: str,
    design_family: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    def _control_int(controls: dict[str, Any], *keys: str) -> int:
        for key in keys:
            if key in controls:
                return int(controls.get(key, 0) or 0)
        return 0

    current_artifacts = (
        solver_session_report.get("artifacts")
        if isinstance(solver_session_report.get("artifacts"), dict)
        else {}
    )
    current_determinism = (
        solver_session_report.get("determinism")
        if isinstance(solver_session_report.get("determinism"), dict)
        else {}
    )
    baseline_artifacts = (
        baseline_solver_session.get("artifacts")
        if isinstance(baseline_solver_session.get("artifacts"), dict)
        else {}
    )
    baseline_determinism = (
        baseline_solver_session.get("determinism")
        if isinstance(baseline_solver_session.get("determinism"), dict)
        else {}
    )
    baseline_authoring_controls = (
        baseline_solver_session.get("authoring_controls")
        if isinstance(baseline_solver_session.get("authoring_controls"), dict)
        else {}
    )
    baseline_trace = {
        "family_id": family_id,
        "design_family": design_family,
        "artifact_path": str(baseline_artifacts.get("session_summary_json", "") or ""),
        "payload_sha256": str(baseline_determinism.get("payload_sha256", "") or ""),
        "load_pattern_count": _control_int(
            baseline_authoring_controls,
            "loadPatternCount",
            "load_pattern_count",
        ),
        "source": "generated_family_baseline",
    }
    receipt_trace = {
        "artifact_path": str(
            current_artifacts.get("session_summary_json")
            or current_artifacts.get("solver_session_json")
            or ""
        ),
        "payload_sha256": str(current_determinism.get("payload_sha256", "") or ""),
        "generated_at": str(solver_session_report.get("generated_at", "") or ""),
        "source": "current_solver_session",
    }
    return baseline_trace, receipt_trace


def _build_diff_expansion_reason(
    *,
    authoring_controls: dict[str, Any],
    baseline_solver_session: dict[str, Any],
) -> str:
    def _control_int(controls: dict[str, Any], *keys: str) -> int:
        for key in keys:
            if key in controls:
                return int(controls.get(key, 0) or 0)
        return 0

    baseline_authoring_controls = (
        baseline_solver_session.get("authoring_controls")
        if isinstance(baseline_solver_session.get("authoring_controls"), dict)
        else {}
    )
    current_load_pattern_count = _control_int(authoring_controls, "loadPatternCount", "load_pattern_count")
    baseline_load_pattern_count = _control_int(
        baseline_authoring_controls,
        "loadPatternCount",
        "load_pattern_count",
    )
    if current_load_pattern_count > baseline_load_pattern_count > 0:
        return (
            "Commercialization target intentionally expands family-baseline load coverage "
            f"from loadPatternCount={baseline_load_pattern_count} to {current_load_pattern_count}."
        )
    return ""


def _resolve_solver_session_report(
    *,
    solver_session_path: Path,
    generated_at: str | None,
    family: str,
    family_id: str | None = None,
    story_count: int | float | None = None,
    bay_count: int | float | None = None,
    floor_height_m: int | float | None = None,
    load_pattern_count: int | float | None = None,
    section_id: str | None = None,
    editor_contract_profile: str = _DEFAULT_EDITOR_CONTRACT_PROFILE,
) -> tuple[dict[str, Any], str]:
    solver_session_report = _load_json(solver_session_path)
    if solver_session_report:
        return solver_session_report, "file"
    return (
        build_native_authoring_solver_session_payload(
            generated_at=generated_at,
            family=family,
            out_path=solver_session_path,
            family_id=family_id,
            story_count=story_count,
            bay_count=bay_count,
            floor_height_m=floor_height_m,
            load_pattern_count=load_pattern_count,
            section_id=section_id,
            editor_contract_profile=editor_contract_profile,
        ),
        "local_builder",
    )


def build_load_combination_editor_commercialization_report(
    solver_session_report: dict[str, Any],
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    timestamp = (
        str(generated_at or "").strip()
        or str(solver_session_report.get("generated_at", "") or "").strip()
        or _now_utc_iso()
    )
    selected_family = (
        solver_session_report.get("selected_family")
        if isinstance(solver_session_report.get("selected_family"), dict)
        else {}
    )
    authoring_controls = (
        solver_session_report.get("authoring_controls")
        if isinstance(solver_session_report.get("authoring_controls"), dict)
        else {}
    )
    load_combination_session = (
        solver_session_report.get("load_combination_session")
        if isinstance(solver_session_report.get("load_combination_session"), dict)
        else {}
    )
    editor_seed = (
        load_combination_session.get("editor_seed")
        if isinstance(load_combination_session.get("editor_seed"), dict)
        else {}
    )
    runtime_summary = _resolve_runtime_summary(
        load_combination_session=load_combination_session,
        editor_seed=editor_seed,
    )
    family_id = str(
        authoring_controls.get("family_id")
        or selected_family.get("family_id")
        or "sample_tower"
    ).strip() or "sample_tower"
    design_family = canonicalize_kds_family(
        str(load_combination_session.get("family", "") or KDS_CONCRETE_FAMILY)
    )
    editor_contract_profile = _resolve_editor_contract_profile(solver_session_report)
    runtime_combinations = load_combinations_from_midas_model(_runtime_payload_from_editor_seed(editor_seed))
    required_targets = match_runtime_to_required_editor_targets(
        runtime_combinations=runtime_combinations,
        family=design_family,
    )
    family_baseline_solver_session = build_native_authoring_solver_session_payload(
        generated_at=timestamp,
        family=design_family,
        family_id=family_id,
    )
    family_baseline_load_combination_session = (
        family_baseline_solver_session.get("load_combination_session")
        if isinstance(family_baseline_solver_session.get("load_combination_session"), dict)
        else {}
    )
    family_baseline_editor_seed = (
        family_baseline_load_combination_session.get("editor_seed")
        if isinstance(family_baseline_load_combination_session.get("editor_seed"), dict)
        else {}
    )
    commercialization_target = _extract_commercialization_target_context(
        solver_session_report=solver_session_report,
        load_combination_session=load_combination_session,
        authoring_controls=authoring_controls,
        selected_family=selected_family,
    )
    family_template_baseline_trace, receipt_trace = _build_diff_traceability(
        solver_session_report=solver_session_report,
        baseline_solver_session=family_baseline_solver_session,
        family_id=family_id,
        design_family=design_family,
    )
    family_template_diff_receipt = build_load_combination_diff_receipt(
        current_editor_seed=editor_seed,
        baseline_editor_seed=family_baseline_editor_seed,
        commercialization_target=commercialization_target,
        baseline_trace=family_template_baseline_trace,
        receipt_trace=receipt_trace,
        expansion_reason=_build_diff_expansion_reason(
            authoring_controls=authoring_controls,
            baseline_solver_session=family_baseline_solver_session,
        ),
        allow_additive_inference=True,
    )
    control_locked_baseline_solver_session = build_native_authoring_solver_session_payload(
        generated_at=timestamp,
        family=design_family,
        authoring_controls=_locked_authoring_controls(authoring_controls),
        family_id=family_id,
        editor_contract_profile=editor_contract_profile,
    )
    control_locked_baseline_load_combination_session = (
        control_locked_baseline_solver_session.get("load_combination_session")
        if isinstance(control_locked_baseline_solver_session.get("load_combination_session"), dict)
        else {}
    )
    control_locked_baseline_editor_seed = (
        control_locked_baseline_load_combination_session.get("editor_seed")
        if isinstance(control_locked_baseline_load_combination_session.get("editor_seed"), dict)
        else {}
    )
    control_locked_baseline_trace, _ = _build_diff_traceability(
        solver_session_report=solver_session_report,
        baseline_solver_session=control_locked_baseline_solver_session,
        family_id=family_id,
        design_family=design_family,
    )
    diff_receipt = build_load_combination_diff_receipt(
        current_editor_seed=editor_seed,
        baseline_editor_seed=control_locked_baseline_editor_seed,
        baseline_trace=control_locked_baseline_trace,
        receipt_trace=receipt_trace,
    )
    solver_load_card_rows, solver_load_card_summary = _flatten_solver_load_cards(solver_session_report)
    required_target_match = _build_required_target_match(
        required_targets=required_targets,
        runtime_summary=runtime_summary,
        design_family=design_family,
    )
    nested_expansion = _build_nested_expansion_summary(runtime_summary)
    solver_load_card_coverage = _build_solver_load_card_coverage(
        solver_load_card_rows=solver_load_card_rows,
        solver_load_card_summary=solver_load_card_summary,
    )
    code_check_assembly = _build_code_check_assembly(runtime_summary)
    checks = {
        "required_kds_targets_pass": bool(required_target_match.get("contract_pass", False)),
        "nested_envelope_native_expansion_pass": bool(nested_expansion.get("ready", False)),
        "exact_solver_load_cards_pass": bool(solver_load_card_coverage.get("ready", False)),
        "load_diff_receipt_materialized_pass": bool(diff_receipt.get("contract_pass", False)),
        "code_check_assembly_connected_pass": bool(code_check_assembly.get("ready", False)),
    }
    contract_pass = bool(all(checks.values()))
    summary_line = (
        "Load-combination editor commercialization: "
        f"{'PASS' if contract_pass else 'CHECK'} | "
        f"kds_match={required_target_match['ready_ratio_label']} | "
        f"nested={nested_expansion['nested_combo_count']} depth={nested_expansion['max_nested_depth']} | "
        f"cards=selfweight={solver_load_card_coverage['selfweight_card_count']},"
        f"nodal={solver_load_card_coverage['nodal_card_count']},"
        f"surface={solver_load_card_coverage['surface_card_count']},"
        f"pressure={solver_load_card_coverage['pressure_card_count']} | "
        f"diff={int(diff_receipt.get('difference_count', 0) or 0)} | "
        f"codecheck={'yes' if code_check_assembly.get('ready', False) else 'check'}"
    )
    payload = {
        "schema_version": "1.0",
        "report_family": "load_combination_editor_commercialization",
        "generated_at": timestamp,
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "CHECK",
        "reason": "load combination editor commercialization report generated",
        "summary_line": summary_line,
        "summary": {
            "family_id": family_id,
            "design_family": design_family,
            "required_target_count": int(required_target_match.get("target_count", 0) or 0),
            "required_target_ready_count": int(required_target_match.get("ready_count", 0) or 0),
            "required_target_match_label": str(required_target_match.get("ready_ratio_label", "") or ""),
            "required_rc_target_match_label": str(required_target_match.get("rc_target_match_label", "") or ""),
            "nested_combo_count": int(nested_expansion.get("nested_combo_count", 0) or 0),
            "max_nested_depth": int(nested_expansion.get("max_nested_depth", 0) or 0),
            "runtime_case_count": int(runtime_summary.get("runtime_case_count", 0) or 0),
            "load_editor_combo_count": int(runtime_summary.get("combo_count", 0) or 0),
            "selfweight_card_count": int(solver_load_card_coverage.get("selfweight_card_count", 0) or 0),
            "nodal_card_count": int(solver_load_card_coverage.get("nodal_card_count", 0) or 0),
            "surface_card_count": int(solver_load_card_coverage.get("surface_card_count", 0) or 0),
            "pressure_card_count": int(solver_load_card_coverage.get("pressure_card_count", 0) or 0),
            "line_card_count": int(solver_load_card_coverage.get("line_card_count", 0) or 0),
            "displacement_card_count": int(solver_load_card_coverage.get("displacement_card_count", 0) or 0),
            "exact_solver_load_cards_ready": bool(solver_load_card_coverage.get("ready", False)),
            "load_diff_difference_count": int(diff_receipt.get("difference_count", 0) or 0),
            "load_diff_closure_status": str(diff_receipt.get("closure_status", "") or ""),
            "family_template_diff_difference_count": int(
                family_template_diff_receipt.get("difference_count", 0) or 0
            ),
            "family_template_diff_closure_status": str(
                family_template_diff_receipt.get("closure_status", "") or ""
            ),
            "baseline_diff_policy": "authoring_controls_locked_baseline",
            "code_check_assembly_ready": bool(code_check_assembly.get("ready", False)),
        },
        "checks": checks,
        "commercialization_target": dict(family_template_diff_receipt.get("commercialization_target") or {}),
        "required_target_match": required_target_match,
        "required_target_rows": list(required_target_match.get("rows") or []),
        "nested_expansion": nested_expansion,
        "solver_load_card_coverage": solver_load_card_coverage,
        "solver_load_card_rows": solver_load_card_rows,
        "family_baseline_diff": {
            "ready": bool(family_template_diff_receipt.get("contract_pass", False)),
            "baseline_family_id": family_id,
            "baseline_design_family": design_family,
            "baseline_kind": "family_template",
            "difference_count": int(family_template_diff_receipt.get("difference_count", 0) or 0),
            "closure_status": str(family_template_diff_receipt.get("closure_status", "") or ""),
            "acceptance_reason": str(family_template_diff_receipt.get("acceptance_reason", "") or ""),
            "expansion_reason": str(family_template_diff_receipt.get("expansion_reason", "") or ""),
            "traceability": dict(family_template_diff_receipt.get("traceability") or {}),
            "summary_line": str(family_template_diff_receipt.get("summary_line", "") or ""),
            "receipt": family_template_diff_receipt,
        },
        "control_locked_baseline_diff": {
            "ready": bool(diff_receipt.get("contract_pass", False)),
            "baseline_family_id": family_id,
            "baseline_design_family": design_family,
            "baseline_kind": "authoring_controls_locked_baseline",
            "editor_contract_profile": str(editor_contract_profile),
            "difference_count": int(diff_receipt.get("difference_count", 0) or 0),
            "closure_status": str(diff_receipt.get("closure_status", "") or ""),
            "acceptance_reason": str(diff_receipt.get("acceptance_reason", "") or ""),
            "expansion_reason": str(diff_receipt.get("expansion_reason", "") or ""),
            "traceability": dict(diff_receipt.get("traceability") or {}),
            "summary_line": str(diff_receipt.get("summary_line", "") or ""),
            "receipt": diff_receipt,
        },
        "diff_receipt": diff_receipt,
        "code_check_assembly": code_check_assembly,
        "artifacts": {
            "solver_session_json": str(DEFAULT_SOLVER_SESSION_REPORT),
        },
    }
    payload["determinism"] = {
        "signature_mode": _SIGNATURE_MODE,
        "generated_at_locked": bool(str(generated_at or "").strip()),
        "payload_sha256": _sha256_payload(_payload_signature_input(payload)),
    }
    return payload


def materialize_load_combination_editor_commercialization_report(
    *,
    solver_session_path: Path = DEFAULT_SOLVER_SESSION_REPORT,
    out: Path = DEFAULT_OUT,
    generated_at: str | None = None,
    family: str = KDS_CONCRETE_FAMILY,
    family_id: str | None = None,
    story_count: int | float | None = None,
    bay_count: int | float | None = None,
    floor_height_m: int | float | None = None,
    load_pattern_count: int | float | None = None,
    section_id: str | None = None,
    editor_contract_profile: str = _DEFAULT_EDITOR_CONTRACT_PROFILE,
) -> dict[str, Any]:
    solver_session_report, solver_session_source = _resolve_solver_session_report(
        solver_session_path=solver_session_path,
        generated_at=generated_at,
        family=family,
        family_id=family_id,
        story_count=story_count,
        bay_count=bay_count,
        floor_height_m=floor_height_m,
        load_pattern_count=load_pattern_count,
        section_id=section_id,
        editor_contract_profile=editor_contract_profile,
    )
    payload = build_load_combination_editor_commercialization_report(
        solver_session_report,
        generated_at=generated_at,
    )
    payload.setdefault("artifacts", {})
    payload["artifacts"]["solver_session_json"] = str(solver_session_path)
    payload["artifacts"]["solver_session_source"] = solver_session_source
    payload["artifacts"]["load_combination_editor_commercialization_report_json"] = str(out)
    payload["determinism"]["payload_sha256"] = _sha256_payload(_payload_signature_input(payload))
    _write_json(out, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solver-session", default=str(DEFAULT_SOLVER_SESSION_REPORT))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--generated-at", default="")
    parser.add_argument("--family", default=KDS_CONCRETE_FAMILY)
    parser.add_argument("--family-id", default=None)
    parser.add_argument("--story-count", type=float, default=None)
    parser.add_argument("--bay-count", type=float, default=None)
    parser.add_argument("--floor-height-m", type=float, default=None)
    parser.add_argument("--load-pattern-count", type=float, default=None)
    parser.add_argument("--section-id", default=None)
    parser.add_argument("--editor-contract-profile", default=_DEFAULT_EDITOR_CONTRACT_PROFILE)
    args = parser.parse_args()
    payload = materialize_load_combination_editor_commercialization_report(
        solver_session_path=Path(args.solver_session),
        out=Path(args.out),
        generated_at=str(args.generated_at).strip() or None,
        family=str(args.family).strip() or KDS_CONCRETE_FAMILY,
        family_id=str(args.family_id).strip() if isinstance(args.family_id, str) and args.family_id.strip() else None,
        story_count=args.story_count,
        bay_count=args.bay_count,
        floor_height_m=args.floor_height_m,
        load_pattern_count=args.load_pattern_count,
        section_id=str(args.section_id).strip() if isinstance(args.section_id, str) and args.section_id.strip() else None,
        editor_contract_profile=str(args.editor_contract_profile).strip() or _DEFAULT_EDITOR_CONTRACT_PROFILE,
    )
    print(payload["summary_line"])


if __name__ == "__main__":
    main()
