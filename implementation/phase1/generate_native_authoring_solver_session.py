#!/usr/bin/env python3
"""Generate a deterministic native authoring solver session artifact."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from implementation.phase1.generate_native_authoring_workspace_summary import (
        build_sample_authoring_model,
        get_native_authoring_family_template,
        resolve_authoring_controls,
    )
    from implementation.phase1.load_combination_engine import (
        KDS_CONCRETE_FAMILY,
        KDS_STEEL_BASIC_FAMILY,
        canonicalize_kds_family,
        export_midas_loadcomb_from_editor_seed,
        generate_kds_service_combinations,
        generate_kds_steel_service_combinations,
        generate_kds_steel_strength_combinations,
        generate_kds_strength_combinations,
        summarize_runtime_combination_model,
    )
    from implementation.phase1.section_library_and_mesher import (
        AuthoringModelDraft,
        MeshRequest,
        build_authoring_bundle_summary,
        build_default_section_catalog,
        build_load_pattern_summary,
        validate_mesh_request,
    )
except ImportError:  # pragma: no cover
    from generate_native_authoring_workspace_summary import (  # type: ignore
        build_sample_authoring_model,
        get_native_authoring_family_template,
        resolve_authoring_controls,
    )
    from load_combination_engine import (  # type: ignore
        KDS_CONCRETE_FAMILY,
        KDS_STEEL_BASIC_FAMILY,
        canonicalize_kds_family,
        export_midas_loadcomb_from_editor_seed,
        generate_kds_service_combinations,
        generate_kds_steel_service_combinations,
        generate_kds_steel_strength_combinations,
        generate_kds_strength_combinations,
        summarize_runtime_combination_model,
    )
    from section_library_and_mesher import (  # type: ignore
        AuthoringModelDraft,
        MeshRequest,
        build_authoring_bundle_summary,
        build_default_section_catalog,
        build_load_pattern_summary,
        validate_mesh_request,
    )


DEFAULT_AUTHORING_DIR = Path("implementation/phase1/release/authoring")
DEFAULT_OUT = DEFAULT_AUTHORING_DIR / "native_authoring_solver_session.json"
DEFAULT_LOADCOMB_PREVIEW_OUT = DEFAULT_AUTHORING_DIR / "native_authoring_solver_session.loadcomb_preview.mgt"
DEFAULT_LOADCOMB_OUT = DEFAULT_LOADCOMB_PREVIEW_OUT
DEFAULT_EDITOR_CONTRACT_PROFILE = "default"
COMMERCIALIZATION_TARGET_EDITOR_CONTRACT_PROFILE = "commercialization_target"

_RUNTIME_CASE_NAMES = {
    "D": "DEAD",
    "L": "LIVE",
    "Lr": "ROOF_LIVE",
    "S": "SNOW",
    "Wx": "WIND+X",
    "Wy": "WIND+Y",
    "Ex": "EX",
    "Ey": "EY",
}
_VALID_ELEMENT_KINDS = {"frame", "fiber_section", "shell", "solid"}
_HELPER_CONTRACTS = {
    "authoring_model_builder": (
        "implementation.phase1.generate_native_authoring_workspace_summary.build_sample_authoring_model"
    ),
    "section_catalog_builder": "implementation.phase1.section_library_and_mesher.build_default_section_catalog",
    "authoring_bundle_summary": "implementation.phase1.section_library_and_mesher.build_authoring_bundle_summary",
    "load_pattern_summary": "implementation.phase1.section_library_and_mesher.build_load_pattern_summary",
    "mesh_validation": "implementation.phase1.section_library_and_mesher.validate_mesh_request",
    "family_normalizer": "implementation.phase1.load_combination_engine.canonicalize_kds_family",
    "loadcomb_export": "implementation.phase1.load_combination_engine.export_midas_loadcomb_from_editor_seed",
    "runtime_combination_summary": "implementation.phase1.load_combination_engine.summarize_runtime_combination_model",
}
_LOAD_COMBINATION_LIBRARY_SOURCES = {
    KDS_CONCRETE_FAMILY: [
        "implementation.phase1.load_combination_engine.generate_kds_strength_combinations",
        "implementation.phase1.load_combination_engine.generate_kds_service_combinations",
    ],
    KDS_STEEL_BASIC_FAMILY: [
        "implementation.phase1.load_combination_engine.generate_kds_steel_strength_combinations",
        "implementation.phase1.load_combination_engine.generate_kds_steel_service_combinations",
    ],
}


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _stable_json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_payload(payload: Any) -> str:
    return _sha256_text(_stable_json_text(payload))


def _runtime_case_name(case_name: str) -> str:
    normalized = str(case_name).strip()
    return _RUNTIME_CASE_NAMES.get(normalized, normalized.upper())


def _normalize_editor_contract_profile(profile: str | None) -> str:
    normalized = str(profile or "").strip().lower()
    if normalized in {
        "commercialization",
        "commercialization-target",
        "commercialization_target",
        "load_editor_commercialization",
        "target",
    }:
        return COMMERCIALIZATION_TARGET_EDITOR_CONTRACT_PROFILE
    return DEFAULT_EDITOR_CONTRACT_PROFILE


def _same_artifact_path(path: Path, expected: Path) -> bool:
    try:
        return path.resolve() == expected.resolve()
    except Exception:
        return str(path) == str(expected)


def _resolve_editor_contract_profile_for_artifacts(
    profile: str | None,
    *,
    out_path: Path,
    loadcomb_out_path: Path,
) -> str:
    normalized = _normalize_editor_contract_profile(profile)
    if normalized != DEFAULT_EDITOR_CONTRACT_PROFILE:
        return normalized
    if _same_artifact_path(out_path, DEFAULT_OUT) or _same_artifact_path(loadcomb_out_path, DEFAULT_LOADCOMB_OUT):
        return COMMERCIALIZATION_TARGET_EDITOR_CONTRACT_PROFILE
    return normalized


def _format_combo_expression(factors: dict[str, float]) -> str:
    terms: list[str] = []
    for index, (case_name, factor) in enumerate(factors.items()):
        runtime_case = _runtime_case_name(case_name)
        magnitude = abs(float(factor))
        token = f"{magnitude:g}({runtime_case})"
        if index == 0:
            terms.append(token if factor >= 0.0 else f"-{token}")
            continue
        prefix = "+ " if factor >= 0.0 else "- "
        terms.append(f"{prefix}{token}")
    return " ".join(terms) if terms else "0"


def _available_case_names(model: AuthoringModelDraft) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for pattern in model.load_patterns:
        for primitive in pattern.primitives:
            case_name = str(primitive.case_name).strip()
            if case_name and case_name not in seen:
                seen.add(case_name)
                ordered.append(case_name)
    return tuple(ordered)


def _element_kind_for_member(member: Any) -> str:
    analysis_kind = str(getattr(member, "analysis_kind", "") or "").strip()
    if analysis_kind in _VALID_ELEMENT_KINDS:
        return analysis_kind
    member_type = str(getattr(member, "member_type", "") or "").strip()
    if member_type in {"wall", "slab"}:
        return "shell"
    return "frame"


def _build_solver_mesh_requests(model: AuthoringModelDraft) -> list[MeshRequest]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for member in model.members:
        element_kind = _element_kind_for_member(member)
        key = (str(member.section_id), element_kind)
        bucket = grouped.setdefault(
            key,
            {
                "member_count": 0,
                "member_types": set(),
            },
        )
        bucket["member_count"] = int(bucket["member_count"]) + 1
        bucket["member_types"].add(str(member.member_type))

    requests: list[MeshRequest] = []
    for index, (section_id, element_kind) in enumerate(sorted(grouped)):
        bucket = grouped[(section_id, element_kind)]
        through_thickness_layers = 4 if element_kind in {"fiber_section", "solid"} else 1
        minimum_divisions = 6 if element_kind in {"fiber_section", "solid"} else 4
        requests.append(
            MeshRequest(
                request_id=f"native-authoring-mesh-{index + 1:02d}",
                section_id=section_id,
                element_kind=element_kind,
                minimum_divisions=minimum_divisions,
                through_thickness_layers=through_thickness_layers,
                metadata={
                    "member_count": int(bucket["member_count"]),
                    "member_types": list(sorted(bucket["member_types"])),
                },
            )
        )
    return requests


def _library_combinations_for_family(family: str) -> list[Any]:
    normalized = canonicalize_kds_family(family)
    if normalized.upper() == KDS_STEEL_BASIC_FAMILY.upper():
        return [*generate_kds_steel_strength_combinations(), *generate_kds_steel_service_combinations()]
    return [*generate_kds_strength_combinations(), *generate_kds_service_combinations()]


def _build_case_nodes(model: AuthoringModelDraft) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for pattern in model.load_patterns:
        case_name = str(pattern.primitives[0].case_name).strip()
        if not case_name or case_name in seen:
            continue
        seen.add(case_name)
        primitive_scopes = list(dict.fromkeys(str(row.target_scope).strip() for row in pattern.primitives if str(row.target_scope).strip()))
        primitive_counts = pattern.primitive_counts()
        nodes.append(
            {
                "id": f"CASE:{_runtime_case_name(case_name)}",
                "name": _runtime_case_name(case_name),
                "canonical_name": case_name,
                "kind": "case",
                "editor_stage": 0,
                "design_situation": str(pattern.design_situation),
                "source_pattern_id": str(pattern.pattern_id),
                "source_pattern_label": str(pattern.label),
                "primitive_count": len(pattern.primitives),
                "primitive_kind_counts": dict(sorted(primitive_counts.items())),
                "primitive_kind_labels": list(sorted(primitive_counts)),
                "primitive_scope_preview": " | ".join(primitive_scopes) if primitive_scopes else "global",
            }
        )
    return nodes


def _clean_factor_map(factor_map: dict[str, float]) -> dict[str, float]:
    return {
        str(key): float(value)
        for key, value in sorted(factor_map.items())
        if abs(float(value)) > 1.0e-12
    }


def _accumulate_factor_map(target: dict[str, float], source: dict[str, float], *, scale: float = 1.0) -> None:
    for case_name, value in source.items():
        target[str(case_name)] = float(target.get(str(case_name), 0.0)) + float(value) * float(scale)


def _combo_factor_map(combo_row: dict[str, Any]) -> dict[str, float]:
    expanded_factor_map = combo_row.get("expanded_factor_map") if isinstance(combo_row.get("expanded_factor_map"), dict) else {}
    if expanded_factor_map:
        return _clean_factor_map(
            {
                str(case_name): float(value)
                for case_name, value in expanded_factor_map.items()
            }
        )
    factor_map = combo_row.get("factor_map") if isinstance(combo_row.get("factor_map"), dict) else {}
    return _clean_factor_map(
        {
            str(case_name): float(value)
            for case_name, value in factor_map.items()
        }
    )


def _lookup_combo_row(
    combination_nodes: list[dict[str, Any]],
    combo_name: str,
) -> dict[str, Any] | None:
    normalized = str(combo_name).strip()
    if not normalized:
        return None
    for row in combination_nodes:
        if str(row.get("name", "") or "").strip() == normalized:
            return row
    return None


def _build_native_nested_combo_row(
    *,
    name: str,
    limit_state: str,
    stage: int,
    referenced_combinations: list[str],
    combination_nodes: list[dict[str, Any]],
    description_role: str,
) -> dict[str, Any] | None:
    references = [str(reference_name).strip() for reference_name in referenced_combinations if str(reference_name).strip()]
    if len(references) < 2:
        return None
    aggregated: dict[str, float] = {}
    for reference_name in references:
        reference_row = _lookup_combo_row(combination_nodes, reference_name)
        if reference_row is None:
            return None
        reference_factor_map = _combo_factor_map(reference_row)
        if not reference_factor_map:
            return None
        _accumulate_factor_map(aggregated, reference_factor_map)
    expanded_factor_map = _clean_factor_map(aggregated)
    if not expanded_factor_map:
        return None
    return {
        "id": f"COMBO:{name}",
        "name": str(name),
        "kind": "combo",
        "editor_stage": int(stage),
        "limit_state": str(limit_state),
        "combination_type": "GEN",
        "expression": " + ".join(f"1({reference_name})" for reference_name in references),
        "entry_count": len(references),
        "expansion_mode": "nested_envelope",
        "expansion_depth": int(stage),
        "referenced_combinations": references,
        "referenced_leaf_cases": list(expanded_factor_map),
        "factor_map": dict(expanded_factor_map),
        "expanded_factor_map": dict(expanded_factor_map),
        "entry_rows": [
            {
                "reference_kind": "CB",
                "reference_name": reference_name,
                "factor": 1.0,
            }
            for reference_name in references
        ],
        "node_role": str(description_role),
    }


def _extend_with_native_nested_envelopes(
    combination_nodes: list[dict[str, Any]],
    *,
    family: str,
    editor_contract_profile: str,
) -> list[dict[str, Any]]:
    normalized_profile = _normalize_editor_contract_profile(editor_contract_profile)
    if normalized_profile != COMMERCIALIZATION_TARGET_EDITOR_CONTRACT_PROFILE:
        return combination_nodes
    normalized_family = canonicalize_kds_family(family)
    if normalized_family != KDS_CONCRETE_FAMILY:
        return combination_nodes

    extended_rows = list(combination_nodes)
    planned_rows: list[dict[str, Any]] = []

    uls_lateral_refs = [
        combo_name
        for combo_name in ("KDS_ULS_3_WX+", "KDS_ULS_4_WY+", "KDS_ULS_5_EX+", "KDS_ULS_6_EY+")
        if _lookup_combo_row(extended_rows, combo_name) is not None
    ]
    sls_lateral_refs = [
        combo_name
        for combo_name in ("KDS_SLS_2_WX+", "KDS_SLS_3_WY+", "KDS_SLS_4_EX+", "KDS_SLS_5_EY+")
        if _lookup_combo_row(extended_rows, combo_name) is not None
    ]

    if _lookup_combo_row(extended_rows, "KDS_ENV_ULS_LATERAL") is None:
        nested_row = _build_native_nested_combo_row(
            name="KDS_ENV_ULS_LATERAL",
            limit_state="ULS",
            stage=2,
            referenced_combinations=uls_lateral_refs,
            combination_nodes=extended_rows,
            description_role="native_nested_envelope",
        )
        if nested_row is not None:
            planned_rows.append(nested_row)
            extended_rows.append(nested_row)

    if _lookup_combo_row(extended_rows, "KDS_ENV_SLS_DRIFT") is None:
        nested_row = _build_native_nested_combo_row(
            name="KDS_ENV_SLS_DRIFT",
            limit_state="SLS",
            stage=2,
            referenced_combinations=sls_lateral_refs,
            combination_nodes=extended_rows,
            description_role="native_nested_envelope",
        )
        if nested_row is not None:
            planned_rows.append(nested_row)
            extended_rows.append(nested_row)

    if _lookup_combo_row(extended_rows, "KDS_ENV_ULS_CRITICAL") is None:
        nested_row = _build_native_nested_combo_row(
            name="KDS_ENV_ULS_CRITICAL",
            limit_state="ULS",
            stage=3,
            referenced_combinations=["KDS_ULS_2", "KDS_ENV_ULS_LATERAL"],
            combination_nodes=extended_rows,
            description_role="native_nested_envelope_deep",
        )
        if nested_row is not None:
            planned_rows.append(nested_row)
            extended_rows.append(nested_row)

    return extended_rows


def _build_editor_seed(
    model: AuthoringModelDraft,
    *,
    family: str,
    editor_contract_profile: str = DEFAULT_EDITOR_CONTRACT_PROFILE,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    available_cases = set(_available_case_names(model))
    library_combinations = _library_combinations_for_family(family)
    omitted_combinations: list[dict[str, Any]] = []
    combination_nodes: list[dict[str, Any]] = []

    for combo in library_combinations:
        combo_case_names = list(combo.factors.keys())
        missing_case_names = sorted(case_name for case_name in combo_case_names if case_name not in available_cases)
        if missing_case_names:
            omitted_combinations.append(
                {
                    "name": str(combo.name),
                    "limit_state": str(combo.limit_state),
                    "missing_case_names": [_runtime_case_name(case_name) for case_name in missing_case_names],
                }
            )
            continue

        factor_map = {
            _runtime_case_name(case_name): float(factor)
            for case_name, factor in combo.factors.items()
        }
        entry_rows = [
            {
                "reference_kind": "ST",
                "reference_name": _runtime_case_name(case_name),
                "factor": float(factor),
            }
            for case_name, factor in combo.factors.items()
        ]
        combination_nodes.append(
            {
                "id": f"COMBO:{combo.name}",
                "name": str(combo.name),
                "kind": "combo",
                "editor_stage": 1,
                "limit_state": str(combo.limit_state),
                "combination_type": "GEN",
                "expression": _format_combo_expression(combo.factors),
                "entry_count": len(entry_rows),
                "expansion_mode": "linear_combination",
                "expansion_depth": 1,
                "referenced_combinations": [],
                "referenced_leaf_cases": list(factor_map),
                "factor_map": factor_map,
                "expanded_factor_map": dict(factor_map),
                "entry_rows": entry_rows,
                "node_role": "library_combo",
            }
        )

    combination_nodes = _extend_with_native_nested_envelopes(
        combination_nodes,
        family=family,
        editor_contract_profile=editor_contract_profile,
    )

    graph_edges = [
        {
            "src_id": str(combo_row["id"]),
            "src_name": str(combo_row["name"]),
            "src_kind": "combo",
            "dst_id": (
                f"COMBO:{str(entry_row['reference_name'])}"
                if str(entry_row.get("reference_kind", "")).strip().upper() == "CB"
                else f"CASE:{str(entry_row['reference_name'])}"
            ),
            "dst_name": str(entry_row["reference_name"]),
            "dst_kind": (
                "combo"
                if str(entry_row.get("reference_kind", "")).strip().upper() == "CB"
                else "case"
            ),
            "reference_kind": str(entry_row.get("reference_kind", "")).strip().upper() or "ST",
            "factor": float(entry_row["factor"]),
        }
        for combo_row in combination_nodes
        for entry_row in combo_row["entry_rows"]
    ]
    limit_state_counts: dict[str, int] = {}
    expansion_mode_counts: dict[str, int] = {}
    for combo_row in combination_nodes:
        limit_state = str(combo_row.get("limit_state", "") or "")
        expansion_mode = str(combo_row.get("expansion_mode", "") or "")
        if limit_state:
            limit_state_counts[limit_state] = int(limit_state_counts.get(limit_state, 0) + 1)
        if expansion_mode:
            expansion_mode_counts[expansion_mode] = int(expansion_mode_counts.get(expansion_mode, 0) + 1)

    case_nodes = _build_case_nodes(model)
    stages = {
        int(row.get("editor_stage", 0) or 0)
        for row in [*case_nodes, *combination_nodes]
    }
    editor_seed = {
        "contract_version": "0.1.0",
        "provenance": "native_authoring_solver_session_generator",
        "seed_kind": "midas_load_combination_editor_seed",
        "editor_contract_profile": _normalize_editor_contract_profile(editor_contract_profile),
        "limitations": [
            "Filtered to KDS library combinations whose referenced cases exist in the native authoring sample.",
        ],
        "summary": {
            "case_count": len(case_nodes),
            "combination_count": len(combination_nodes),
            "graph_edge_count": len(graph_edges),
            "stage_count": len(stages),
            "nested_combination_count": sum(
                1
                for row in combination_nodes
                if str(row.get("expansion_mode", "")).strip() == "nested_envelope"
            ),
            "max_expansion_depth": max((int(row.get("expansion_depth", 0) or 0) for row in combination_nodes), default=0),
            "limit_state_counts": dict(sorted(limit_state_counts.items())),
            "expansion_mode_counts": dict(sorted(expansion_mode_counts.items())),
        },
        "case_nodes": case_nodes,
        "combination_nodes": combination_nodes,
        "graph_edges": graph_edges,
    }
    return editor_seed, omitted_combinations


def _runtime_summary_payload(editor_seed: dict[str, Any]) -> dict[str, Any]:
    combination_rows = [
        {
            "name": str(row.get("name", "") or ""),
            "combination_type": str(row.get("combination_type", "") or "GEN"),
            "limit_state": str(row.get("limit_state", "") or ""),
            "entry_rows": [
                {
                    "reference_kind": str(entry.get("reference_kind", "") or "ST"),
                    "reference_name": str(entry.get("reference_name", "") or ""),
                    "factor": float(entry.get("factor", 0.0) or 0.0),
                }
                for entry in (row.get("entry_rows") or [])
                if isinstance(entry, dict)
            ],
            "factor_map": {
                str(key): float(value)
                for key, value in (row.get("factor_map") or {}).items()
            },
            "expanded_factor_map": {
                str(key): float(value)
                for key, value in (row.get("expanded_factor_map") or {}).items()
            },
            "referenced_combinations": [
                str(item)
                for item in (row.get("referenced_combinations") or [])
                if str(item).strip()
            ],
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


def _build_source_provenance(
    *,
    catalog: Any,
    model: AuthoringModelDraft,
    mesh_requests: list[MeshRequest],
    family: str,
    editor_contract_profile: str,
) -> dict[str, Any]:
    return {
        "helper_contracts": dict(sorted(_HELPER_CONTRACTS.items())),
        "load_combination_library_sources": list(
            _LOAD_COMBINATION_LIBRARY_SOURCES.get(
                canonicalize_kds_family(family),
                _LOAD_COMBINATION_LIBRARY_SOURCES[KDS_CONCRETE_FAMILY],
            )
        ),
        "catalog_version": str(getattr(catalog, "version", "") or ""),
        "catalog_source_label": str(getattr(catalog, "source_label", "") or ""),
        "model_id": str(model.model_id),
        "mesh_request_ids": [request.request_id for request in mesh_requests],
        "mesh_request_count": len(mesh_requests),
        "preview_export_mode": "midas_loadcomb_editor_seed",
        "editor_contract_profile": _normalize_editor_contract_profile(editor_contract_profile),
    }


def _build_payload_and_preview(
    *,
    generated_at: str | None,
    family: str,
    out_path: Path,
    loadcomb_out_path: Path,
    authoring_controls: Any = None,
    draft_payload: dict[str, Any] | None = None,
    draft_json_path: str | Path | None = None,
    editor_contract_profile: str = DEFAULT_EDITOR_CONTRACT_PROFILE,
    family_id: str | None = None,
    story_count: int | float | None = None,
    bay_count: int | float | None = None,
    floor_height_m: int | float | None = None,
    load_pattern_count: int | float | None = None,
    section_id: str | None = None,
) -> tuple[dict[str, Any], str]:
    timestamp = str(generated_at or "").strip() or _now_utc_iso()
    catalog = build_default_section_catalog()
    controls = resolve_authoring_controls(
        authoring_controls=authoring_controls,
        draft_payload=draft_payload,
        draft_json_path=draft_json_path,
        family_id=family_id,
        story_count=story_count,
        bay_count=bay_count,
        floor_height_m=floor_height_m,
        load_pattern_count=load_pattern_count,
        section_id=section_id,
    )
    model = build_sample_authoring_model(authoring_controls=controls)
    authoring_family = get_native_authoring_family_template(controls.family_id)
    authoring_summary = build_authoring_bundle_summary(catalog=catalog, model=model)
    load_pattern_summary = build_load_pattern_summary(model.load_patterns)

    mesh_requests = _build_solver_mesh_requests(model)
    mesh_plan_rows = [validate_mesh_request(catalog=catalog, request=request).to_payload() for request in mesh_requests]
    mesh_summary = {
        "request_count": len(mesh_requests),
        "total_estimated_cells": int(sum(int(row["estimated_cell_count"]) for row in mesh_plan_rows)),
        "max_estimated_cell_count": int(max((int(row["estimated_cell_count"]) for row in mesh_plan_rows), default=0)),
        "mesh_requests": [request.to_payload() for request in mesh_requests],
        "mesh_plan_summaries": mesh_plan_rows,
    }

    normalized_family = canonicalize_kds_family(family)
    normalized_editor_contract_profile = _resolve_editor_contract_profile_for_artifacts(
        editor_contract_profile,
        out_path=out_path,
        loadcomb_out_path=loadcomb_out_path,
    )
    editor_seed, omitted_combinations = _build_editor_seed(
        model,
        family=normalized_family,
        editor_contract_profile=normalized_editor_contract_profile,
    )
    loadcomb_preview = export_midas_loadcomb_from_editor_seed(editor_seed)
    runtime_summary = summarize_runtime_combination_model(_runtime_summary_payload(editor_seed))
    selected_combination_names = [
        str(row.get("name", "") or "")
        for row in (editor_seed.get("combination_nodes") or [])
        if isinstance(row, dict)
    ]
    source_provenance = _build_source_provenance(
        catalog=catalog,
        model=model,
        mesh_requests=mesh_requests,
        family=normalized_family,
        editor_contract_profile=normalized_editor_contract_profile,
    )
    contract_pass = bool(
        authoring_summary.native_authoring_ready
        and bool(mesh_plan_rows)
        and runtime_summary.get("authoring_ready", False)
        and bool(loadcomb_preview.strip())
    )
    reason_code = "PASS" if contract_pass else "CHECK"
    summary_line = (
        f"Native authoring solver session: {'PASS' if contract_pass else 'CHECK'} | "
        f"meshes={len(mesh_plan_rows)} | cells={mesh_summary['total_estimated_cells']} | "
        f"combos={runtime_summary['combo_count']} | family={normalized_family}"
    )
    payload = {
        "schema_version": "1.0",
        "report_family": "native_authoring_solver_session",
        "generated_at": timestamp,
        "authoring_controls": controls.to_draft_payload(section_palette=list(catalog.template_ids())),
        "selected_family": authoring_family.to_payload(),
        "session_id": f"{model.model_id}::solver-session",
        "summary_line": f"{summary_line} | authoring_family={controls.family_id}",
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "reason": "native authoring solver session generated",
        "summary": {
            "model_id": str(model.model_id),
            "authoring_family_id": str(controls.family_id),
            "story_count": len(model.story_levels),
            "member_count": len(model.members),
            "load_pattern_count": len(model.load_patterns),
            "mesh_request_count": len(mesh_requests),
            "mesh_plan_count": len(mesh_plan_rows),
            "combo_count": int(runtime_summary.get("combo_count", 0) or 0),
            "load_case_count": int(runtime_summary.get("runtime_case_count", 0) or 0),
            "loadcomb_line_count": len(loadcomb_preview.splitlines()),
            "family": normalized_family,
            "editor_contract_profile": normalized_editor_contract_profile,
            "session_ready": bool(contract_pass),
        },
        "authoring_summary": authoring_summary.to_payload(),
        "load_pattern_summary": load_pattern_summary,
        "mesh_session": mesh_summary,
        "load_combination_session": {
            "family": normalized_family,
            "editor_contract_profile": normalized_editor_contract_profile,
            "editor_seed": editor_seed,
            "runtime_summary": runtime_summary,
            "selected_combination_names": selected_combination_names,
            "omitted_library_combinations": omitted_combinations,
            "loadcomb_preview_line_count": len(loadcomb_preview.splitlines()),
        },
        "model_preview": {
            "story_levels": [row.to_payload() for row in model.story_levels],
            "member_preview_rows": [row.to_payload() for row in model.members[:8]],
            "load_patterns": [row.to_payload() for row in model.load_patterns],
        },
        "source_provenance": source_provenance,
        "artifacts": {
            "session_summary_json": str(out_path),
            "loadcomb_preview_mgt": str(loadcomb_out_path),
        },
    }
    payload["determinism"] = {
        "signature_mode": "sha256_stable_json_v1",
        "generated_at_locked": bool(str(generated_at or "").strip()),
        "payload_sha256": _sha256_payload(payload),
        "loadcomb_preview_sha256": _sha256_text(loadcomb_preview),
    }
    return payload, loadcomb_preview


def build_native_authoring_solver_session_payload(
    *,
    generated_at: str | None = None,
    family: str = KDS_CONCRETE_FAMILY,
    out_path: Path = DEFAULT_OUT,
    loadcomb_out_path: Path = DEFAULT_LOADCOMB_OUT,
    authoring_controls: Any = None,
    draft_payload: dict[str, Any] | None = None,
    draft_json_path: str | Path | None = None,
    editor_contract_profile: str = DEFAULT_EDITOR_CONTRACT_PROFILE,
    family_id: str | None = None,
    story_count: int | float | None = None,
    bay_count: int | float | None = None,
    floor_height_m: int | float | None = None,
    load_pattern_count: int | float | None = None,
    section_id: str | None = None,
) -> dict[str, Any]:
    payload, _ = _build_payload_and_preview(
        generated_at=generated_at,
        family=family,
        out_path=out_path,
        loadcomb_out_path=loadcomb_out_path,
        authoring_controls=authoring_controls,
        draft_payload=draft_payload,
        draft_json_path=draft_json_path,
        editor_contract_profile=editor_contract_profile,
        family_id=family_id,
        story_count=story_count,
        bay_count=bay_count,
        floor_height_m=floor_height_m,
        load_pattern_count=load_pattern_count,
        section_id=section_id,
    )
    return payload


def materialize_native_authoring_solver_session(
    *,
    out_path: Path = DEFAULT_OUT,
    loadcomb_out_path: Path = DEFAULT_LOADCOMB_OUT,
    generated_at: str | None = None,
    family: str = KDS_CONCRETE_FAMILY,
    authoring_controls: Any = None,
    draft_payload: dict[str, Any] | None = None,
    draft_json_path: str | Path | None = None,
    editor_contract_profile: str = DEFAULT_EDITOR_CONTRACT_PROFILE,
    family_id: str | None = None,
    story_count: int | float | None = None,
    bay_count: int | float | None = None,
    floor_height_m: int | float | None = None,
    load_pattern_count: int | float | None = None,
    section_id: str | None = None,
) -> dict[str, Any]:
    payload, loadcomb_preview = _build_payload_and_preview(
        generated_at=generated_at,
        family=family,
        out_path=out_path,
        loadcomb_out_path=loadcomb_out_path,
        authoring_controls=authoring_controls,
        draft_payload=draft_payload,
        draft_json_path=draft_json_path,
        editor_contract_profile=editor_contract_profile,
        family_id=family_id,
        story_count=story_count,
        bay_count=bay_count,
        floor_height_m=floor_height_m,
        load_pattern_count=load_pattern_count,
        section_id=section_id,
    )
    _write_json(out_path, payload)
    _write_text(loadcomb_out_path, loadcomb_preview)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--loadcomb-out", default=str(DEFAULT_LOADCOMB_OUT))
    parser.add_argument("--generated-at", default="")
    parser.add_argument("--family", default=KDS_CONCRETE_FAMILY)
    parser.add_argument("--draft-json", default="")
    parser.add_argument("--editor-contract-profile", default=DEFAULT_EDITOR_CONTRACT_PROFILE)
    parser.add_argument("--family-id", default=None)
    parser.add_argument("--story-count", type=float, default=None)
    parser.add_argument("--bay-count", type=float, default=None)
    parser.add_argument("--floor-height-m", type=float, default=None)
    parser.add_argument("--load-pattern-count", type=float, default=None)
    parser.add_argument("--section-id", default=None)
    args = parser.parse_args()

    payload = materialize_native_authoring_solver_session(
        out_path=Path(args.out),
        loadcomb_out_path=Path(args.loadcomb_out),
        generated_at=str(args.generated_at).strip() or None,
        family=str(args.family).strip() or KDS_CONCRETE_FAMILY,
        draft_json_path=str(args.draft_json).strip() or None,
        editor_contract_profile=str(args.editor_contract_profile).strip() or DEFAULT_EDITOR_CONTRACT_PROFILE,
        family_id=str(args.family_id).strip() if isinstance(args.family_id, str) and args.family_id.strip() else None,
        story_count=args.story_count,
        bay_count=args.bay_count,
        floor_height_m=args.floor_height_m,
        load_pattern_count=args.load_pattern_count,
        section_id=str(args.section_id).strip() if isinstance(args.section_id, str) and args.section_id.strip() else None,
    )
    print(payload["summary_line"])


if __name__ == "__main__":
    main()
