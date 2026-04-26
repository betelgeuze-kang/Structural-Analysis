#!/usr/bin/env python3
"""Gate the active load-combination engine step against canonical MIDAS artifacts."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from runtime_contracts import InputContractError, validate_input_contract

try:
    from implementation.phase1.load_combination_engine import (
        LoadCombination,
        generate_kds_service_combinations,
        generate_kds_steel_service_combinations,
        generate_kds_steel_strength_combinations,
        generate_kds_strength_combinations,
        load_combinations_from_midas_model,
        match_runtime_to_kds,
        normalize_runtime_case_name,
        summarize_runtime_combination_model,
    )
except Exception:  # pragma: no cover - local execution fallback
    from load_combination_engine import (  # type: ignore
        LoadCombination,
        generate_kds_service_combinations,
        generate_kds_steel_service_combinations,
        generate_kds_steel_strength_combinations,
        generate_kds_strength_combinations,
        load_combinations_from_midas_model,
        match_runtime_to_kds,
        normalize_runtime_case_name,
        summarize_runtime_combination_model,
    )


REASONS = {
    "PASS": "load-combination engine evidence satisfies the current exact-roundtrip and KDS alignment gate",
    "ERR_INVALID_INPUT": "invalid load-combination engine gate input",
    "ERR_EVIDENCE_MISSING": "one or more required load-combination artifacts are missing",
    "ERR_RUNTIME_INVENTORY_GAP": "runtime combination inventory is incomplete or inconsistent with roundtrip receipts",
    "ERR_LOAD_PATTERN_COVERAGE_GAP": "required runtime load-pattern coverage is incomplete",
    "ERR_KDS_RUNTIME_ALIGNMENT_GAP": "runtime combinations do not yet align closely enough with the canonical KDS library",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["model_jsons", "loadcomb_roundtrip_reports", "out"],
    "properties": {
        "model_jsons": {"type": "string", "minLength": 1},
        "loadcomb_roundtrip_reports": {"type": "string", "minLength": 1},
        "out": {"type": "string", "minLength": 1},
    },
}

DEFAULT_MODEL_JSONS = (
    "implementation/phase1/open_data/midas/midas_generator_33.json,"
    "implementation/phase1/open_data/midas/midas_generator_33.pr_recheck.json,"
    "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json"
)

DEFAULT_LOADCOMB_ROUNDTRIP_REPORTS = (
    "implementation/phase1/release/midas_generator_33_loadcomb_roundtrip_report.json,"
    "implementation/phase1/release/midas_generator_33_pr_recheck_loadcomb_roundtrip_report.json,"
    "implementation/phase1/release/midas_generator_33_optimized_roundtrip_loadcomb_roundtrip_report.json"
)

DEFAULT_OUT = "implementation/phase1/load_combination_engine_gate_report.json"

MIN_KDS_STRENGTH_AVG_MATCH = 0.90
MIN_KDS_STRENGTH_MIN_MATCH = 0.75
MIN_KDS_SERVICE_AVG_MATCH = 0.90
MIN_KDS_SERVICE_MIN_MATCH = 0.75

KDS_FAMILY_GENERIC = "KDS-2022-generic"
KDS_FAMILY_RC_WIND = "KDS-2022-rc-wind"
KDS_FAMILY_RC_SEISMIC = "KDS-2022-rc-seismic"
KDS_FAMILY_RC_NESTED = "KDS-2022-rc-nested"
KDS_FAMILY_STEEL = "KDS-2022-steel-gravity"

_CANONICAL_CASE_ALIASES = {
    "WX": "Wx",
    "WY": "Wy",
    "EX": "Ex",
    "EY": "Ey",
    "LR": "Lr",
}
_STEEL_SELECTION_NAME_TOKENS = ("STL", "ENV_STR", "ENV_SER", "SLCB")
_STEEL_FAMILY_CASE_KEYS = frozenset({"D", "L"})
_RUNTIME_BREADTH_ORDER = ("rc", "wind", "seismic")


def _parse_csv(text: str) -> list[str]:
    return [item.strip() for item in str(text).split(",") if item.strip()]


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _path_aliases(path: Path) -> set[str]:
    aliases = {str(path), path.as_posix(), path.name}
    try:
        aliases.add(str(path.resolve()))
        aliases.add(path.resolve().as_posix())
    except Exception:
        pass
    return {item for item in aliases if item}


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(sum(values) / len(values))


def _normalize_case_label(value: str) -> str:
    normalized = str(normalize_runtime_case_name(str(value or "")) or "").strip()
    if not normalized:
        return ""
    return _CANONICAL_CASE_ALIASES.get(normalized.upper(), normalized)


def _extract_pattern_case_names(model_payload: dict[str, Any]) -> set[str]:
    model = model_payload.get("model") if isinstance(model_payload.get("model"), dict) else {}
    metadata = model.get("metadata") if isinstance(model.get("metadata"), dict) else {}
    pattern_library = (
        metadata.get("load_pattern_library")
        if isinstance(metadata.get("load_pattern_library"), dict)
        else {}
    )
    pattern_summary = (
        pattern_library.get("pattern_summary")
        if isinstance(pattern_library.get("pattern_summary"), dict)
        else {}
    )
    pattern_rows = (
        pattern_summary.get("patterns")
        if isinstance(pattern_summary.get("patterns"), list)
        else []
    )
    case_counts = (
        pattern_summary.get("case_counts")
        if isinstance(pattern_summary.get("case_counts"), dict)
        else {}
    )
    names: set[str] = set()
    for row in pattern_rows:
        if not isinstance(row, dict):
            continue
        label = _normalize_case_label(str(row.get("label", "") or ""))
        if label:
            names.add(label)
    for key in case_counts:
        label = _normalize_case_label(str(key))
        if label:
            names.add(label)
    return names


def _extract_semantic_case_names(model_payload: dict[str, Any]) -> set[str]:
    model = model_payload.get("model") if isinstance(model_payload.get("model"), dict) else {}
    loads = model.get("loads") if isinstance(model.get("loads"), dict) else {}
    semantic_summary = (
        loads.get("semantic_load_summary")
        if isinstance(loads.get("semantic_load_summary"), dict)
        else {}
    )
    case_rows = (
        semantic_summary.get("case_force_summaries")
        if isinstance(semantic_summary.get("case_force_summaries"), list)
        else []
    )
    names: set[str] = set()
    for row in case_rows:
        if not isinstance(row, dict):
            continue
        label = _normalize_case_label(str(row.get("load_case", "") or ""))
        if label:
            names.add(label)
    return names


def _roundtrip_report_map(report_paths: list[Path]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    by_source: dict[str, dict[str, Any]] = {}
    for path in report_paths:
        payload = _load_json(path)
        source_model_json = str(payload.get("source_model_json", "") or "")
        row = {
            "path": str(path),
            "exists": bool(path.exists()),
            "payload": payload,
            "source_model_json": source_model_json,
        }
        rows.append(row)
        for alias in _path_aliases(Path(source_model_json)) if source_model_json else {str(path)}:
            if alias and alias not in by_source:
                by_source[alias] = row
    return rows, by_source


def _find_roundtrip_row(
    *,
    model_path: Path,
    report_rows: list[dict[str, Any]],
    report_by_source: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    for alias in _path_aliases(model_path):
        matched = report_by_source.get(alias)
        if matched:
            return matched
    if len(report_rows) == 1:
        return report_rows[0]
    return {}


def _coverage_pass(value: Any) -> bool:
    try:
        return float(value or 0.0) >= 1.0
    except (TypeError, ValueError):
        return False


def _kds_match_metrics(match_rows: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [float(row.get("match_score", 0.0) or 0.0) for row in match_rows if isinstance(row, dict)]
    return {
        "target_count": int(len(match_rows)),
        "avg_match_score": float(_mean(scores)),
        "min_match_score": float(min(scores) if scores else 0.0),
        "exact_match_count": int(sum(1 for score in scores if score >= 1.0)),
        "strong_match_count": int(sum(1 for score in scores if score >= 0.90)),
        "weak_match_count": int(sum(1 for score in scores if score < 0.75)),
        "worst_cases": [
            {
                "kds_name": str(row.get("kds_name", "") or ""),
                "matched_runtime_name": str(row.get("matched_runtime_name", "") or ""),
                "match_score": float(row.get("match_score", 0.0) or 0.0),
            }
            for row in sorted(match_rows, key=lambda item: float(item.get("match_score", 0.0) or 0.0))[:3]
            if isinstance(row, dict)
        ],
    }


def _build_supported_kds_families() -> dict[str, dict[str, Any]]:
    rc_strength = generate_kds_strength_combinations()
    rc_service = generate_kds_service_combinations()
    return {
        KDS_FAMILY_GENERIC: {
            "family": KDS_FAMILY_GENERIC,
            "label": "KDS generic",
            "strength": rc_strength,
            "service": rc_service,
        },
        KDS_FAMILY_RC_WIND: {
            "family": KDS_FAMILY_RC_WIND,
            "label": "KDS RC wind",
            "strength": rc_strength,
            "service": rc_service,
        },
        KDS_FAMILY_RC_SEISMIC: {
            "family": KDS_FAMILY_RC_SEISMIC,
            "label": "KDS RC seismic",
            "strength": rc_strength,
            "service": rc_service,
        },
        KDS_FAMILY_RC_NESTED: {
            "family": KDS_FAMILY_RC_NESTED,
            "label": "KDS RC nested",
            "strength": rc_strength,
            "service": rc_service,
        },
        KDS_FAMILY_STEEL: {
            "family": KDS_FAMILY_STEEL,
            "label": "KDS steel gravity",
            "strength": generate_kds_steel_strength_combinations(),
            "service": generate_kds_steel_service_combinations(),
        },
    }


def _factor_signature(factors: dict[str, float]) -> tuple[tuple[str, float], ...]:
    return tuple(
        sorted(
            (
                str(key),
                round(float(value), 6),
            )
            for key, value in factors.items()
            if str(key).strip()
        )
    )


def _select_kds_family(
    *,
    runtime_combos: list[LoadCombination],
    family_profiles: dict[str, dict[str, Any]],
    family_metrics: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    runtime_names = [str(combo.name or "").strip().upper() for combo in runtime_combos if str(combo.name or "").strip()]
    runtime_name_token_hits = sorted(
        {
            token
            for token in _STEEL_SELECTION_NAME_TOKENS
            if any(token in combo_name for combo_name in runtime_names)
        }
    )
    non_empty_runtime_combos = [combo for combo in runtime_combos if combo.factors]
    gravity_only = bool(non_empty_runtime_combos) and all(
        set(str(key) for key in combo.factors.keys()).issubset(_STEEL_FAMILY_CASE_KEYS)
        for combo in non_empty_runtime_combos
    )
    steel_strength = family_profiles.get(KDS_FAMILY_STEEL, {}).get("strength") or []
    steel_service = family_profiles.get(KDS_FAMILY_STEEL, {}).get("service") or []
    steel_signature_reference = {
        _factor_signature(combo.factors)
        for combo in [*steel_strength, *steel_service]
        if isinstance(combo, LoadCombination)
    }
    runtime_signature_matches = sorted(
        {
            "|".join(f"{key}={value:.3f}" for key, value in signature)
            for signature in (
                _factor_signature(combo.factors)
                for combo in non_empty_runtime_combos
            )
            if signature in steel_signature_reference
        }
    )
    steel_family_clear_signal = bool(
        gravity_only
        and bool(runtime_name_token_hits)
        and len(runtime_signature_matches) >= 2
    )

    family_scores = {
        family_name: float(
            (
                float(metrics.get("strength", {}).get("avg_match_score", 0.0) or 0.0)
                + float(metrics.get("service", {}).get("avg_match_score", 0.0) or 0.0)
            )
            / 2.0
        )
        for family_name, metrics in family_metrics.items()
    }
    selected_family = KDS_FAMILY_STEEL if steel_family_clear_signal else KDS_FAMILY_GENERIC
    if selected_family not in family_profiles:
        selected_family = max(
            family_scores,
            key=family_scores.get,
            default=KDS_FAMILY_GENERIC,
        )
    selected_reason = (
        "steel_named_gravity_signature_match"
        if selected_family == KDS_FAMILY_STEEL and steel_family_clear_signal
        else "generic_default"
    )
    return {
        "selected_family": selected_family,
        "recommended_family": selected_family,
        "selection_reason": selected_reason,
        "steel_family_clear_signal": steel_family_clear_signal,
        "steel_name_token_hits": runtime_name_token_hits,
        "steel_signature_match_count": int(len(runtime_signature_matches)),
        "steel_signature_matches": runtime_signature_matches,
        "gravity_only_runtime": gravity_only,
        "family_scores": {str(key): float(value) for key, value in sorted(family_scores.items())},
    }


def build_report(
    *,
    model_json_paths: list[Path],
    roundtrip_report_paths: list[Path],
    source_args: dict[str, Any],
) -> dict[str, Any]:
    family_profiles = _build_supported_kds_families()
    report_rows, report_by_source = _roundtrip_report_map(roundtrip_report_paths)

    artifact_rows: list[dict[str, Any]] = []
    artifact_gap_counts: Counter[str] = Counter()
    selected_family_counts: Counter[str] = Counter()

    for model_path in model_json_paths:
        model_payload = _load_json(model_path)
        model = model_payload.get("model") if isinstance(model_payload.get("model"), dict) else {}
        runtime_combos = load_combinations_from_midas_model(model_payload) if model else []
        runtime_model_summary = summarize_runtime_combination_model(model_payload) if model else {}
        runtime_combo_names = [str(combo.name) for combo in runtime_combos if str(combo.name).strip()]
        runtime_case_names = sorted(
            {
                _normalize_case_label(case_name)
                for combo in runtime_combos
                for case_name in combo.factors.keys()
                if _normalize_case_label(case_name)
            }
        )
        pattern_case_names = sorted(_extract_pattern_case_names(model_payload))
        semantic_case_names = sorted(_extract_semantic_case_names(model_payload))
        covered_pattern_names = sorted(set(pattern_case_names) | set(semantic_case_names))
        missing_required_pattern_cases = sorted(
            case_name for case_name in runtime_case_names if case_name not in covered_pattern_names
        )

        roundtrip_row = _find_roundtrip_row(
            model_path=model_path,
            report_rows=report_rows,
            report_by_source=report_by_source,
        )
        roundtrip_payload = (
            roundtrip_row.get("payload")
            if isinstance(roundtrip_row.get("payload"), dict)
            else {}
        )
        roundtrip_report_present = bool(roundtrip_row)
        roundtrip_pass = bool(roundtrip_payload.get("pass", False))
        roundtrip_supported = bool(roundtrip_payload.get("supported", False))
        exact_name_coverage = float(roundtrip_payload.get("exact_name_coverage", 0.0) or 0.0)
        exact_entry_row_coverage = float(roundtrip_payload.get("exact_entry_row_coverage", 0.0) or 0.0)
        exact_header_coverage = float(roundtrip_payload.get("exact_header_coverage", 0.0) or 0.0)
        exact_factor_map_coverage = float(roundtrip_payload.get("exact_factor_map_coverage", 0.0) or 0.0)
        exact_expression_coverage = float(roundtrip_payload.get("exact_expression_coverage", 0.0) or 0.0)
        roundtrip_raw_combo_count = int(roundtrip_payload.get("raw_combo_count", 0) or 0)
        roundtrip_export_combo_count = int(roundtrip_payload.get("export_combo_count", 0) or 0)

        exact_roundtrip_fidelity_pass = bool(
            roundtrip_report_present
            and roundtrip_pass
            and roundtrip_supported
            and _coverage_pass(exact_name_coverage)
            and _coverage_pass(exact_entry_row_coverage)
            and _coverage_pass(exact_header_coverage)
            and _coverage_pass(exact_factor_map_coverage)
            and _coverage_pass(exact_expression_coverage)
        )

        family_metrics: dict[str, dict[str, Any]] = {}
        for family_name, family_profile in family_profiles.items():
            strength_match_rows = match_runtime_to_kds(
                runtime_combinations=runtime_combos,
                kds_combinations=list(family_profile.get("strength") or []),
            )
            service_match_rows = match_runtime_to_kds(
                runtime_combinations=runtime_combos,
                kds_combinations=list(family_profile.get("service") or []),
            )
            family_metrics[family_name] = {
                "strength": _kds_match_metrics(strength_match_rows),
                "service": _kds_match_metrics(service_match_rows),
            }
        family_selection = _select_kds_family(
            runtime_combos=runtime_combos,
            family_profiles=family_profiles,
            family_metrics=family_metrics,
        )
        selected_family = str(family_selection.get("selected_family", KDS_FAMILY_GENERIC) or KDS_FAMILY_GENERIC)
        selected_family_profile = family_profiles.get(selected_family, family_profiles[KDS_FAMILY_GENERIC])
        selected_family_metrics = family_metrics.get(selected_family, {})
        strength_metrics = (
            selected_family_metrics.get("strength")
            if isinstance(selected_family_metrics.get("strength"), dict)
            else _kds_match_metrics([])
        )
        service_metrics = (
            selected_family_metrics.get("service")
            if isinstance(selected_family_metrics.get("service"), dict)
            else _kds_match_metrics([])
        )
        selected_family_counts.update([selected_family])

        gap_labels: list[str] = []
        if not model_path.exists():
            gap_labels.append("model_artifact_missing")
        if not roundtrip_report_present:
            gap_labels.append("roundtrip_report_missing")
        if not runtime_combo_names:
            gap_labels.append("runtime_combo_inventory_missing")
        if roundtrip_report_present and roundtrip_raw_combo_count != len(runtime_combo_names):
            gap_labels.append("runtime_combo_count_mismatch")
        if roundtrip_report_present and roundtrip_export_combo_count != len(runtime_combo_names):
            gap_labels.append("export_combo_count_mismatch")
        if roundtrip_report_present and not exact_roundtrip_fidelity_pass:
            if not _coverage_pass(exact_name_coverage):
                gap_labels.append("exact_name_coverage_gap")
            if not _coverage_pass(exact_entry_row_coverage):
                gap_labels.append("exact_entry_row_coverage_gap")
            if not _coverage_pass(exact_header_coverage):
                gap_labels.append("exact_header_coverage_gap")
            if not _coverage_pass(exact_factor_map_coverage):
                gap_labels.append("exact_factor_map_coverage_gap")
            if not _coverage_pass(exact_expression_coverage):
                gap_labels.append("exact_expression_coverage_gap")
        if missing_required_pattern_cases:
            gap_labels.append("load_pattern_coverage_gap")
        if not (
            strength_metrics["avg_match_score"] >= MIN_KDS_STRENGTH_AVG_MATCH
            and strength_metrics["min_match_score"] >= MIN_KDS_STRENGTH_MIN_MATCH
        ):
            gap_labels.append("kds_strength_alignment_gap")
        if not (
            service_metrics["avg_match_score"] >= MIN_KDS_SERVICE_AVG_MATCH
            and service_metrics["min_match_score"] >= MIN_KDS_SERVICE_MIN_MATCH
        ):
            gap_labels.append("kds_service_alignment_gap")

        artifact_gap_counts.update(gap_labels)
        artifact_rows.append(
            {
                "model_json": str(model_path),
                "model_exists": bool(model_path.exists()),
                "roundtrip_report": str(roundtrip_row.get("path", "") or ""),
                "roundtrip_report_present": roundtrip_report_present,
                "runtime_combo_count": int(len(runtime_combo_names)),
                "runtime_combo_names": runtime_combo_names,
                "runtime_linear_combo_count": int(runtime_model_summary.get("linear_combo_count", 0) or 0),
                "runtime_nested_combo_count": int(runtime_model_summary.get("nested_combo_count", 0) or 0),
                "runtime_max_nested_depth": int(runtime_model_summary.get("max_nested_depth", 0) or 0),
                "runtime_unresolved_reference_count": int(
                    runtime_model_summary.get("unresolved_reference_count", 0) or 0
                ),
                "runtime_unresolved_reference_names": list(
                    runtime_model_summary.get("unresolved_reference_names") or []
                ),
                "runtime_combo_depth_rows": list(runtime_model_summary.get("combo_depth_rows") or []),
                "runtime_authoring_summary_line": str(runtime_model_summary.get("summary_line", "") or ""),
                "runtime_authoring_ready": bool(runtime_model_summary.get("authoring_ready", False)),
                "runtime_required_case_count": int(len(runtime_case_names)),
                "runtime_required_cases": runtime_case_names,
                "runtime_case_family_counts": dict(runtime_model_summary.get("runtime_case_family_counts") or {}),
                "runtime_case_breadth_count": int(runtime_model_summary.get("runtime_case_breadth_count", 0) or 0),
                "runtime_case_breadth_label": str(
                    runtime_model_summary.get("runtime_case_breadth_label", "") or ""
                ),
                "runtime_combo_family_counts": dict(runtime_model_summary.get("combo_family_counts") or {}),
                "runtime_family_tag_counts": dict(runtime_model_summary.get("family_tag_counts") or {}),
                "runtime_limit_state_counts": dict(runtime_model_summary.get("limit_state_counts") or {}),
                "runtime_rc_combo_count": int(runtime_model_summary.get("rc_combo_count", 0) or 0),
                "runtime_wind_combo_count": int(runtime_model_summary.get("wind_combo_count", 0) or 0),
                "runtime_seismic_combo_count": int(runtime_model_summary.get("seismic_combo_count", 0) or 0),
                "runtime_rc_max_nested_depth": int(runtime_model_summary.get("rc_max_nested_depth", 0) or 0),
                "runtime_wind_max_nested_depth": int(runtime_model_summary.get("wind_max_nested_depth", 0) or 0),
                "runtime_seismic_max_nested_depth": int(
                    runtime_model_summary.get("seismic_max_nested_depth", 0) or 0
                ),
                "load_pattern_case_count": int(len(pattern_case_names)),
                "load_pattern_cases": pattern_case_names,
                "semantic_case_count": int(len(semantic_case_names)),
                "semantic_cases": semantic_case_names,
                "covered_required_pattern_case_count": int(
                    len([case_name for case_name in runtime_case_names if case_name in covered_pattern_names])
                ),
                "required_load_pattern_coverage_ratio": float(
                    1.0
                    if not runtime_case_names
                    else len([case_name for case_name in runtime_case_names if case_name in covered_pattern_names])
                    / len(runtime_case_names)
                ),
                "missing_required_load_pattern_cases": missing_required_pattern_cases,
                "roundtrip_raw_combo_count": roundtrip_raw_combo_count,
                "roundtrip_export_combo_count": roundtrip_export_combo_count,
                "roundtrip_pass": roundtrip_pass,
                "roundtrip_supported": roundtrip_supported,
                "exact_name_coverage": exact_name_coverage,
                "exact_entry_row_coverage": exact_entry_row_coverage,
                "exact_header_coverage": exact_header_coverage,
                "exact_factor_map_coverage": exact_factor_map_coverage,
                "exact_expression_coverage": exact_expression_coverage,
                "exact_roundtrip_fidelity_pass": exact_roundtrip_fidelity_pass,
                "selected_kds_family": selected_family,
                "recommended_kds_family": str(family_selection.get("recommended_family", selected_family) or selected_family),
                "kds_family_selection_reason": str(family_selection.get("selection_reason", "") or ""),
                "kds_family_selection_signals": {
                    "steel_family_clear_signal": bool(family_selection.get("steel_family_clear_signal", False)),
                    "gravity_only_runtime": bool(family_selection.get("gravity_only_runtime", False)),
                    "steel_name_token_hits": list(family_selection.get("steel_name_token_hits") or []),
                    "steel_signature_match_count": int(family_selection.get("steel_signature_match_count", 0) or 0),
                    "steel_signature_matches": list(family_selection.get("steel_signature_matches") or []),
                    "family_scores": dict(family_selection.get("family_scores") or {}),
                },
                "kds_family_candidates": {
                    family_name: {
                        "label": str((family_profiles.get(family_name) or {}).get("label", family_name)),
                        "strength": dict(candidate_metrics.get("strength") or {}),
                        "service": dict(candidate_metrics.get("service") or {}),
                    }
                    for family_name, candidate_metrics in sorted(family_metrics.items())
                },
                "kds_strength_target_count": int(len(selected_family_profile.get("strength") or [])),
                "kds_service_target_count": int(len(selected_family_profile.get("service") or [])),
                "kds_strength_match": strength_metrics,
                "kds_service_match": service_metrics,
                "gap_labels": gap_labels,
            }
        )

    checks = {
        "model_artifacts_present_pass": bool(artifact_rows) and all(row["model_exists"] for row in artifact_rows),
        "roundtrip_reports_present_pass": bool(artifact_rows) and all(
            row["roundtrip_report_present"] for row in artifact_rows
        ),
        "runtime_combo_inventory_pass": bool(artifact_rows)
        and all(
            row["runtime_combo_count"] >= 1
            and "runtime_combo_inventory_missing" not in row["gap_labels"]
            and "runtime_combo_count_mismatch" not in row["gap_labels"]
            and "export_combo_count_mismatch" not in row["gap_labels"]
            for row in artifact_rows
        ),
        "exact_roundtrip_fidelity_pass": bool(artifact_rows) and all(
            row["exact_roundtrip_fidelity_pass"] for row in artifact_rows
        ),
        "required_load_pattern_coverage_pass": bool(artifact_rows) and all(
            not row["missing_required_load_pattern_cases"] and row["runtime_required_case_count"] >= 1
            for row in artifact_rows
        ),
        "runtime_nested_depth_surface_pass": bool(artifact_rows) and all(
            row["runtime_authoring_ready"]
            and row["runtime_unresolved_reference_count"] == 0
            and row["runtime_max_nested_depth"] >= 1
            for row in artifact_rows
        ),
        "runtime_case_breadth_surface_pass": bool(artifact_rows) and all(
            row["runtime_case_breadth_count"] >= 1 for row in artifact_rows
        ),
        "kds_strength_alignment_pass": bool(artifact_rows) and all(
            row["kds_strength_match"]["avg_match_score"] >= MIN_KDS_STRENGTH_AVG_MATCH
            and row["kds_strength_match"]["min_match_score"] >= MIN_KDS_STRENGTH_MIN_MATCH
            for row in artifact_rows
        ),
        "kds_service_alignment_pass": bool(artifact_rows) and all(
            row["kds_service_match"]["avg_match_score"] >= MIN_KDS_SERVICE_AVG_MATCH
            and row["kds_service_match"]["min_match_score"] >= MIN_KDS_SERVICE_MIN_MATCH
            for row in artifact_rows
        ),
    }

    contract_pass = bool(all(checks.values()))
    if not checks["model_artifacts_present_pass"] or not checks["roundtrip_reports_present_pass"]:
        reason_code = "ERR_EVIDENCE_MISSING"
    elif not checks["runtime_combo_inventory_pass"] or not checks["exact_roundtrip_fidelity_pass"]:
        reason_code = "ERR_RUNTIME_INVENTORY_GAP"
    elif not checks["required_load_pattern_coverage_pass"]:
        reason_code = "ERR_LOAD_PATTERN_COVERAGE_GAP"
    elif not checks["kds_strength_alignment_pass"] or not checks["kds_service_alignment_pass"]:
        reason_code = "ERR_KDS_RUNTIME_ALIGNMENT_GAP"
    else:
        reason_code = "PASS"

    runtime_combo_counts = [int(row["runtime_combo_count"]) for row in artifact_rows]
    runtime_linear_combo_counts = [int(row["runtime_linear_combo_count"]) for row in artifact_rows]
    runtime_nested_combo_counts = [int(row["runtime_nested_combo_count"]) for row in artifact_rows]
    runtime_nested_depths = [int(row["runtime_max_nested_depth"]) for row in artifact_rows]
    runtime_case_breadth_counts = [int(row["runtime_case_breadth_count"]) for row in artifact_rows]
    runtime_rc_combo_counts = [int(row["runtime_rc_combo_count"]) for row in artifact_rows]
    runtime_wind_combo_counts = [int(row["runtime_wind_combo_count"]) for row in artifact_rows]
    runtime_seismic_combo_counts = [int(row["runtime_seismic_combo_count"]) for row in artifact_rows]
    runtime_rc_nested_depths = [int(row["runtime_rc_max_nested_depth"]) for row in artifact_rows]
    runtime_wind_nested_depths = [int(row["runtime_wind_max_nested_depth"]) for row in artifact_rows]
    runtime_seismic_nested_depths = [int(row["runtime_seismic_max_nested_depth"]) for row in artifact_rows]
    runtime_case_family_counts_total: Counter[str] = Counter()
    runtime_combo_family_counts_total: Counter[str] = Counter()
    runtime_limit_state_counts_total: Counter[str] = Counter()
    runtime_case_breadth_labels: set[str] = set()
    for row in artifact_rows:
        runtime_case_family_counts_total.update(
            {
                str(key): int(value)
                for key, value in (row.get("runtime_case_family_counts") or {}).items()
            }
        )
        runtime_combo_family_counts_total.update(
            {
                str(key): int(value)
                for key, value in (row.get("runtime_combo_family_counts") or {}).items()
            }
        )
        runtime_limit_state_counts_total.update(
            {
                str(key): int(value)
                for key, value in (row.get("runtime_limit_state_counts") or {}).items()
            }
        )
        breadth_label = str(row.get("runtime_case_breadth_label", "") or "").strip()
        if breadth_label:
            runtime_case_breadth_labels.update(part.strip() for part in breadth_label.split(",") if part.strip())
    runtime_case_breadth_label = ", ".join(
        [tag for tag in _RUNTIME_BREADTH_ORDER if tag in runtime_case_breadth_labels]
        + [tag for tag in sorted(runtime_case_breadth_labels) if tag not in _RUNTIME_BREADTH_ORDER]
    )
    strength_avg_scores = [float(row["kds_strength_match"]["avg_match_score"]) for row in artifact_rows]
    strength_min_scores = [float(row["kds_strength_match"]["min_match_score"]) for row in artifact_rows]
    service_avg_scores = [float(row["kds_service_match"]["avg_match_score"]) for row in artifact_rows]
    service_min_scores = [float(row["kds_service_match"]["min_match_score"]) for row in artifact_rows]

    summary = {
        "model_count": int(len(artifact_rows)),
        "runtime_combo_count_total": int(sum(runtime_combo_counts)),
        "runtime_combo_count_min": int(min(runtime_combo_counts) if runtime_combo_counts else 0),
        "runtime_combo_count_max": int(max(runtime_combo_counts) if runtime_combo_counts else 0),
        "runtime_linear_combo_count_total": int(sum(runtime_linear_combo_counts)),
        "runtime_nested_combo_count_total": int(sum(runtime_nested_combo_counts)),
        "runtime_max_nested_depth_global": int(max(runtime_nested_depths) if runtime_nested_depths else 0),
        "runtime_case_breadth_count_min": int(min(runtime_case_breadth_counts) if runtime_case_breadth_counts else 0),
        "runtime_case_breadth_count_max": int(max(runtime_case_breadth_counts) if runtime_case_breadth_counts else 0),
        "runtime_case_breadth_label": runtime_case_breadth_label,
        "runtime_case_family_counts_total": {
            str(key): int(value) for key, value in sorted(runtime_case_family_counts_total.items())
        },
        "runtime_combo_family_counts_total": {
            str(key): int(value) for key, value in sorted(runtime_combo_family_counts_total.items())
        },
        "runtime_limit_state_counts_total": {
            str(key): int(value) for key, value in sorted(runtime_limit_state_counts_total.items())
        },
        "runtime_rc_combo_count_total": int(sum(runtime_rc_combo_counts)),
        "runtime_wind_combo_count_total": int(sum(runtime_wind_combo_counts)),
        "runtime_seismic_combo_count_total": int(sum(runtime_seismic_combo_counts)),
        "runtime_rc_max_nested_depth_global": int(max(runtime_rc_nested_depths) if runtime_rc_nested_depths else 0),
        "runtime_wind_max_nested_depth_global": int(
            max(runtime_wind_nested_depths) if runtime_wind_nested_depths else 0
        ),
        "runtime_seismic_max_nested_depth_global": int(
            max(runtime_seismic_nested_depths) if runtime_seismic_nested_depths else 0
        ),
        "exact_roundtrip_ready_artifact_count": int(
            sum(1 for row in artifact_rows if row["exact_roundtrip_fidelity_pass"])
        ),
        "required_load_pattern_covered_artifact_count": int(
            sum(1 for row in artifact_rows if not row["missing_required_load_pattern_cases"])
        ),
        "required_load_pattern_case_total": int(
            sum(int(row["runtime_required_case_count"]) for row in artifact_rows)
        ),
        "covered_required_pattern_case_total": int(
            sum(int(row["covered_required_pattern_case_count"]) for row in artifact_rows)
        ),
        "required_load_pattern_coverage_ratio_min": float(
            min((float(row["required_load_pattern_coverage_ratio"]) for row in artifact_rows), default=0.0)
        ),
        "selected_kds_family": (
            artifact_rows[0]["selected_kds_family"]
            if artifact_rows and len(selected_family_counts) == 1
            else "mixed"
        ),
        "recommended_kds_family": (
            artifact_rows[0]["recommended_kds_family"]
            if artifact_rows and len({str(row["recommended_kds_family"]) for row in artifact_rows}) == 1
            else "mixed"
        ),
        "supported_kds_family_labels": list(sorted(family_profiles)),
        "selected_kds_family_counts": {
            str(key): int(value) for key, value in sorted(selected_family_counts.items())
        },
        "kds_strength_target_count": int(
            min((int(row["kds_strength_target_count"]) for row in artifact_rows), default=0)
        ),
        "kds_service_target_count": int(
            min((int(row["kds_service_target_count"]) for row in artifact_rows), default=0)
        ),
        "kds_strength_avg_match_score_mean": float(_mean(strength_avg_scores)),
        "kds_strength_min_match_score_global": float(min(strength_min_scores) if strength_min_scores else 0.0),
        "kds_service_avg_match_score_mean": float(_mean(service_avg_scores)),
        "kds_service_min_match_score_global": float(min(service_min_scores) if service_min_scores else 0.0),
        "kds_strength_avg_match_threshold": float(MIN_KDS_STRENGTH_AVG_MATCH),
        "kds_strength_min_match_threshold": float(MIN_KDS_STRENGTH_MIN_MATCH),
        "kds_service_avg_match_threshold": float(MIN_KDS_SERVICE_AVG_MATCH),
        "kds_service_min_match_threshold": float(MIN_KDS_SERVICE_MIN_MATCH),
        "artifact_gap_counts": {str(key): int(value) for key, value in sorted(artifact_gap_counts.items())},
        "artifact_rows": artifact_rows,
        "evidence_notes": [
            "Exact roundtrip fidelity is evaluated from canonical MIDAS LOADCOMB roundtrip reports and must stay exact.",
            "Required load-pattern coverage is computed only over runtime leaf cases actually referenced by runtime combinations.",
            "Runtime authoring summaries surface deterministic RC/wind/seismic breadth plus nested depth before KDS alignment is checked.",
            "KDS/runtime alignment uses best-match similarity against the canonical KDS strength/service libraries and is intentionally conservative.",
            "Supported KDS family selection is heuristic; a steel family is selected only when the runtime inventory presents clear steel/gravity signatures.",
        ],
    }

    gap_label = ", ".join(
        f"{key}:{value}" for key, value in sorted(summary["artifact_gap_counts"].items())
    ) or "none"
    summary_line = (
        "Load-combination engine gate: "
        f"{'PASS' if contract_pass else 'CHECK'} | "
        f"models={summary['model_count']} | "
        f"family={summary['selected_kds_family']} | "
        f"runtime_combo_range={summary['runtime_combo_count_min']}-{summary['runtime_combo_count_max']} | "
        f"nested={summary['runtime_nested_combo_count_total']} max_depth={summary['runtime_max_nested_depth_global']} | "
        f"breadth={summary['runtime_case_breadth_label'] or 'none'} | "
        f"rc/wind/seismic={summary['runtime_rc_combo_count_total']}/"
        f"{summary['runtime_wind_combo_count_total']}/{summary['runtime_seismic_combo_count_total']} | "
        f"exact_roundtrip={summary['exact_roundtrip_ready_artifact_count']}/{summary['model_count']} | "
        f"pattern_coverage={summary['required_load_pattern_covered_artifact_count']}/{summary['model_count']} "
        f"min={summary['required_load_pattern_coverage_ratio_min']:.2f} | "
        f"kds_strength_avg={summary['kds_strength_avg_match_score_mean']:.3f} "
        f"min={summary['kds_strength_min_match_score_global']:.3f} | "
        f"kds_service_avg={summary['kds_service_avg_match_score_mean']:.3f} "
        f"min={summary['kds_service_min_match_score_global']:.3f} | "
        f"gaps={gap_label}"
    )

    return {
        "schema_version": "1.0",
        "run_id": "phase1-load-combination-engine-gate",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": source_args,
        "checks": checks,
        "summary": summary,
        "summary_line": summary_line,
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
        "artifacts": {
            "model_jsons": [str(path) for path in model_json_paths],
            "loadcomb_roundtrip_reports": [str(path) for path in roundtrip_report_paths],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-jsons", default=DEFAULT_MODEL_JSONS)
    parser.add_argument("--loadcomb-roundtrip-reports", default=DEFAULT_LOADCOMB_ROUNDTRIP_REPORTS)
    parser.add_argument("--out", default=DEFAULT_OUT)
    args = parser.parse_args()

    input_payload = {
        "model_jsons": str(args.model_jsons),
        "loadcomb_roundtrip_reports": str(args.loadcomb_roundtrip_reports),
        "out": str(args.out),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase1.run_load_combination_engine_gate")
        model_json_paths = [Path(item) for item in _parse_csv(args.model_jsons)]
        roundtrip_report_paths = [Path(item) for item in _parse_csv(args.loadcomb_roundtrip_reports)]
        if not model_json_paths or not roundtrip_report_paths:
            raise ValueError("one or more evidence lists are empty")
        payload = build_report(
            model_json_paths=model_json_paths,
            roundtrip_report_paths=roundtrip_report_paths,
            source_args=input_payload,
        )
    except (InputContractError, ValueError) as exc:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-load-combination-engine-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }

    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote load-combination engine gate report: {out}")
    if payload.get("summary_line"):
        print(payload["summary_line"])
    raise SystemExit(0 if bool(payload.get("contract_pass", False)) else 1)


if __name__ == "__main__":
    main()
