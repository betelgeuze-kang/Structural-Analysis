#!/usr/bin/env python3
"""Generate a commercialization-facing corpus/source manifest for native authoring families."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


DEFAULT_RELEASE_ROOT = Path("implementation/phase1/release/authoring/portfolio")
DEFAULT_PORTFOLIO_JSON = DEFAULT_RELEASE_ROOT / "native_authoring_ops_portfolio.json"
DEFAULT_OUT = DEFAULT_RELEASE_ROOT / "native_authoring_family_corpus_manifest.json"
DEFAULT_KOREAN_SOURCE_CATALOG = Path("implementation/phase1/open_data/korea/korean_source_catalog.json")
DEFAULT_BENCHMARK_DIVERSIFICATION_CATALOG = Path("implementation/phase1/open_data/benchmark_diversification_catalog.json")
DEFAULT_AUTHORITY_SOURCE_CATALOG = Path("implementation/phase1/open_data/global_authority/authority_source_catalog.json")

REASONS = {
    "PASS": "native authoring family corpus/source manifest generated",
    "CHECK": "native authoring family corpus/source manifest generated with unresolved linkage gaps",
    "ERR_INPUT": "no native authoring family rows supplied",
}

SURFACE_LIBRARY = {
    "catalog_card": {
        "label": "Catalog Card",
        "description": "High-level commercialization tile with family metrics, readiness, and source badges.",
    },
    "guided_demo": {
        "label": "Guided Demo",
        "description": "Demo-ready surface that pairs the native family artifact set with a concise walkthrough story.",
    },
    "technical_review": {
        "label": "Technical Review",
        "description": "Review or diligence surface that needs traceable internal artifacts and reference provenance.",
    },
    "benchmark_story": {
        "label": "Benchmark Story",
        "description": "Commercial narrative surface that ties a family to authority-grade or public benchmark evidence.",
    },
    "regional_design_seed": {
        "label": "Regional Design Seed",
        "description": "Localization surface for Korean public/native design seeds and reference procurement examples.",
    },
}

REFERENCE_CATEGORY_SURFACE_IDS = {
    "public_design_reference": ("regional_design_seed",),
    "benchmark_candidate": ("benchmark_story",),
    "authority_holdout_bundle": ("benchmark_story",),
    "authority_model_bundle": ("benchmark_story",),
}

DESIGN_AUTHORITY_KIND_BY_CATEGORY = {
    "public_design_reference": "design_reference",
    "benchmark_candidate": "benchmark_reference",
    "authority_holdout_bundle": "authority_reference",
    "authority_model_bundle": "authority_reference",
}

INTERNAL_CORPUS_SPECS = (
    {
        "entry_id": "ops_bundle",
        "title": "Native authoring ops bundle",
        "filename": "native_authoring_ops_bundle.json",
        "corpus_role": "release_bundle",
    },
    {
        "entry_id": "project_registry",
        "title": "Native authoring project registry",
        "filename": "native_authoring_project_registry.json",
        "corpus_role": "registry_provenance",
    },
    {
        "entry_id": "workspace_summary",
        "title": "Native authoring workspace summary",
        "filename": "native_authoring_workspace_summary.json",
        "corpus_role": "workspace_contract",
    },
    {
        "entry_id": "solver_session",
        "title": "Native authoring solver session",
        "filename": "native_authoring_solver_session.json",
        "corpus_role": "solver_contract",
    },
)

REQUIRED_INTERNAL_ENTRY_IDS = {"ops_bundle", "project_registry", "workspace_summary"}

REFERENCE_SPECS: dict[str, dict[str, Any]] = {
    "koneps_hangang_park_gwangnaru2_native_baseline": {
        "resolver": "korean_source_record",
        "source_id": "koneps_hangang_park_gwangnaru2_native_baseline",
        "reference_category": "public_design_reference",
        "domain": "baseline_building",
        "fit_role": "public MIDAS-flavored starter baseline for straightforward onboarding surfaces",
    },
    "kci_concrete_building_design_examples_2e_native_baseline": {
        "resolver": "korean_source_record",
        "source_id": "kci_concrete_building_design_examples_2e_native_baseline",
        "reference_category": "public_design_reference",
        "domain": "design_example",
        "fit_role": "published RC building example anchor for baseline design-seed surfaces",
    },
    "ifc_public_award_structure": {
        "resolver": "korean_source_record",
        "source_id": "ifc_public_award_structure",
        "reference_category": "public_design_reference",
        "domain": "ifc_reference",
        "fit_role": "public IFC structural frame reference for import-ready steel storytelling",
    },
    "lh_happy_city_5_1_native_baseline": {
        "resolver": "korean_source_record",
        "source_id": "lh_happy_city_5_1_native_baseline",
        "reference_category": "public_design_reference",
        "domain": "mixed_use_core_wall",
        "fit_role": "local RC core and wall-frame baseline for mixed-use / core-wall commercialization surfaces",
    },
    "koneps_goyang_changneung_powerplant_design_service": {
        "resolver": "korean_source_record",
        "source_id": "koneps_goyang_changneung_powerplant_design_service",
        "reference_category": "public_design_reference",
        "domain": "steel_rc_hybrid",
        "fit_role": "steel-RC hybrid public design source for mixed-material podium and below-grade families",
    },
    "ifc_public_award_reference_2024": {
        "resolver": "korean_source_record",
        "source_id": "ifc_public_award_reference_2024",
        "reference_category": "public_design_reference",
        "domain": "mixed_structure_ifc",
        "fit_role": "mixed-structure IFC award reference for import and geometry-led commercialization surfaces",
    },
    "lh_bucheon_yeokgok_a1_housing_native_baseline": {
        "resolver": "korean_source_record",
        "source_id": "lh_bucheon_yeokgok_a1_housing_native_baseline",
        "reference_category": "public_design_reference",
        "domain": "housing_wall_frame",
        "fit_role": "wall-frame housing baseline for occupancy-critical RC/CFT dual-system stories",
    },
    "kci_strut_tie_model_design_examples": {
        "resolver": "korean_source_record",
        "source_id": "kci_strut_tie_model_design_examples",
        "reference_category": "public_design_reference",
        "domain": "deep_member",
        "fit_role": "deep-member design example for transfer girder and basement load-path narratives",
    },
    "usgs_nsmp_structural_arrays": {
        "resolver": "benchmark_candidate",
        "candidate_id": "usgs_nsmp_structural_arrays",
        "reference_category": "benchmark_candidate",
        "domain": "measured_dynamic_holdout",
        "fit_role": "measured building-response reference for commercialization surfaces that need real instrumentation context",
    },
    "peer_spd_rc_columns": {
        "resolver": "benchmark_candidate",
        "candidate_id": "peer_spd_rc_columns",
        "reference_category": "benchmark_candidate",
        "domain": "pbd_hinge",
        "fit_role": "component-level RC hysteresis reference for wall/core and nonlinear calibration surfaces",
    },
    "peer_rc_beam_column_joint_2003_10": {
        "resolver": "benchmark_candidate",
        "candidate_id": "peer_rc_beam_column_joint_2003_10",
        "reference_category": "benchmark_candidate",
        "domain": "panel_zone_joint",
        "fit_role": "joint/core shear and anchorage reference for transfer podium storytelling",
    },
    "tpu_highrise_wind_pressure_and_force": {
        "resolver": "benchmark_candidate",
        "candidate_id": "tpu_highrise_wind_pressure_and_force",
        "reference_category": "benchmark_candidate",
        "domain": "wind",
        "fit_role": "public high-rise wind authority reference for premium tower commercialization surfaces",
    },
    "designsafe_liquefaction_pile_foundations": {
        "resolver": "benchmark_candidate",
        "candidate_id": "designsafe_liquefaction_pile_foundations",
        "reference_category": "benchmark_candidate",
        "domain": "foundation_ssi",
        "fit_role": "foundation and pile-soil interaction reference for below-grade or basement family commercialization",
    },
    "canton_tower_megastructure": {
        "resolver": "benchmark_candidate",
        "candidate_id": "canton_tower_megastructure",
        "reference_category": "benchmark_candidate",
        "domain": "megastructure_shm",
        "fit_role": "measured megatall benchmark for outrigger and belt-truss commercialization narratives",
    },
    "edefense_peer_blind_prediction": {
        "resolver": "benchmark_candidate",
        "candidate_id": "edefense_peer_blind_prediction",
        "reference_category": "benchmark_candidate",
        "domain": "blind_prediction_dynamic_holdout",
        "fit_role": "blind-prediction nonlinear authority reference for RC and critical-facility diligence surfaces",
    },
    "sac_holdout_bundle": {
        "resolver": "authority_track_bundle",
        "track": "sac",
        "reference_category": "authority_holdout_bundle",
        "domain": "steel_authority_holdout",
        "title": "SAC steel authority holdout bundle",
        "fit_role": "authority steel holdout coverage for lateral-system commercialization and review surfaces",
    },
    "nheri_holdout_bundle": {
        "resolver": "authority_track_bundle",
        "track": "nheri",
        "reference_category": "authority_holdout_bundle",
        "domain": "measured_response_holdout",
        "title": "NHERI measured-response holdout bundle",
        "fit_role": "measured-response authority bundle for resilience-oriented commercialization surfaces",
    },
    "opensees_scbf_bundle": {
        "resolver": "authority_model_bundle",
        "track": "opensees",
        "model_ids": ("SCBF16B", "SCBF16B_shell_beam_mix"),
        "reference_category": "authority_model_bundle",
        "domain": "steel_benchmark_model",
        "title": "Public OpenSees SCBF model bundle",
        "fit_role": "public benchmark model bundle for steel braced-frame importer and solver surfaces",
    },
    "opensees_luxinzheng_megatall_model": {
        "resolver": "authority_model_bundle",
        "track": "opensees",
        "model_ids": ("Luxinzheng_Megatall_Model1",),
        "reference_category": "authority_model_bundle",
        "domain": "megatall_model",
        "title": "OpenSees 606 m megatall model",
        "fit_role": "public megatall model reference for outrigger and belt-truss premium tower surfaces",
    },
}

FAMILY_LINKAGE_SPECS: dict[str, dict[str, Any]] = {
    "sample_tower": {
        "commercialization_lane": "entry",
        "commercialization_focus": "Baseline onboarding family for first-contact demos, native roundtrip walkthroughs, and low-friction catalog surfaces.",
        "reference_ids": [
            "koneps_hangang_park_gwangnaru2_native_baseline",
            "kci_concrete_building_design_examples_2e_native_baseline",
            "usgs_nsmp_structural_arrays",
        ],
    },
    "steel_braced_frame": {
        "commercialization_lane": "core",
        "commercialization_focus": "Steel lateral-system showcase for authority-backed solver breadth, import, and shell-beam mixed storytelling.",
        "reference_ids": [
            "sac_holdout_bundle",
            "opensees_scbf_bundle",
            "ifc_public_award_structure",
        ],
    },
    "rc_wall_core": {
        "commercialization_lane": "core",
        "commercialization_focus": "RC core-wall family for mixed-use/residential authoring, nonlinear response narratives, and diligence-ready review surfaces.",
        "reference_ids": [
            "lh_happy_city_5_1_native_baseline",
            "peer_spd_rc_columns",
            "edefense_peer_blind_prediction",
        ],
    },
    "composite_podium": {
        "commercialization_lane": "advanced",
        "commercialization_focus": "Mixed-material podium family for transfer-demand storytelling, import surfaces, and composite framing differentiation.",
        "reference_ids": [
            "koneps_goyang_changneung_powerplant_design_service",
            "ifc_public_award_reference_2024",
            "peer_rc_beam_column_joint_2003_10",
        ],
    },
    "outrigger_transfer_tower": {
        "commercialization_lane": "premium",
        "commercialization_focus": "Premium megatall/outrigger family for wind, transfer, and measured-response commercialization surfaces.",
        "reference_ids": [
            "canton_tower_megastructure",
            "tpu_highrise_wind_pressure_and_force",
            "opensees_luxinzheng_megatall_model",
        ],
    },
    "dual_system_hospital": {
        "commercialization_lane": "premium",
        "commercialization_focus": "Resilience-oriented dual-system family for occupancy-critical review, measured-response storytelling, and owner diligence surfaces.",
        "reference_ids": [
            "lh_bucheon_yeokgok_a1_housing_native_baseline",
            "nheri_holdout_bundle",
            "usgs_nsmp_structural_arrays",
        ],
    },
    "belt_truss_mega_frame": {
        "commercialization_lane": "premium",
        "commercialization_focus": "Flagship megatall family for premium wind-response, perimeter mega-frame, and benchmark-story commercialization surfaces.",
        "reference_ids": [
            "canton_tower_megastructure",
            "tpu_highrise_wind_pressure_and_force",
            "opensees_luxinzheng_megatall_model",
        ],
    },
    "deep_transfer_basement": {
        "commercialization_lane": "advanced",
        "commercialization_focus": "Below-grade transfer and foundation scope family for basement load-path, SSI, and foundation optimization stories.",
        "reference_ids": [
            "designsafe_liquefaction_pile_foundations",
            "kci_strut_tie_model_design_examples",
            "koneps_goyang_changneung_powerplant_design_service",
        ],
    },
}


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any] | list[Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = _load_json(path)
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any] | list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _first_int(*values: Any) -> int:
    for value in values:
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str) and value.strip():
            try:
                return int(float(value))
            except ValueError:
                continue
    return 0


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _unique_sorted_tokens(values: list[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _unique_tokens_in_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        token = str(value).strip()
        if not token or token in seen:
            continue
        seen.add(token)
        ordered.append(token)
    return ordered


def _compact_label(values: list[str], max_items: int = 5) -> str:
    normalized = _unique_sorted_tokens(values)
    if not normalized:
        return ""
    if len(normalized) <= max_items:
        return ", ".join(normalized)
    return f"{', '.join(normalized[:max_items])} +{len(normalized) - max_items}"


def _normalize_status(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"ready", "narrowing", "check"}:
        return normalized
    return "check"


def _bool_count(rows: list[dict[str, Any]], key: str) -> int:
    return sum(1 for row in rows if bool(row.get(key, False)))


def _count_existing_paths(paths: list[str]) -> int:
    return sum(1 for path in paths if path and Path(path).exists())


def _catalog_rows(payload: dict[str, Any], *candidate_keys: str) -> list[dict[str, Any]]:
    for key in candidate_keys:
        rows = payload.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _collect_row_paths(rows: list[dict[str, Any]], *keys: str) -> list[str]:
    paths: list[str] = []
    for row in rows:
        for key in keys:
            value = row.get(key)
            if isinstance(value, list):
                paths.extend(str(item).strip() for item in value if str(item).strip())
            else:
                text = _first_text(value)
                if text:
                    paths.append(text)
    return _unique_sorted_tokens(paths)


def _descriptor_design_authority_kind(reference_category: Any) -> str:
    return DESIGN_AUTHORITY_KIND_BY_CATEGORY.get(_first_text(reference_category), "reference_source")


def _finalize_reference_descriptor(descriptor: dict[str, Any]) -> dict[str, Any]:
    source_urls = _unique_sorted_tokens([str(item) for item in descriptor.get("source_urls", []) if str(item).strip()])
    repo_backed_paths = _unique_sorted_tokens(
        [str(item) for item in descriptor.get("repo_backed_paths", []) if str(item).strip()]
    )
    existing_repo_backed_path_count = _count_existing_paths(repo_backed_paths)
    design_authority_kind = _descriptor_design_authority_kind(descriptor.get("reference_category"))
    coverage_axes = _unique_tokens_in_order(
        [
            "local" if existing_repo_backed_path_count else "",
            "public" if source_urls else "",
            "reference",
            "design_authority" if design_authority_kind != "reference_source" else "",
        ]
    )
    descriptor["source_urls"] = source_urls
    descriptor["public_url_count"] = len(source_urls)
    descriptor["repo_backed_paths"] = repo_backed_paths
    descriptor["repo_backed_path_count"] = len(repo_backed_paths)
    descriptor["existing_repo_backed_path_count"] = existing_repo_backed_path_count
    descriptor["design_authority_kind"] = design_authority_kind
    descriptor["coverage_axes"] = coverage_axes
    return descriptor


def _load_korean_source_index(path: Path) -> dict[str, dict[str, Any]]:
    payload = _load_dict(path)
    rows = _catalog_rows(payload, "source_records", "sources")
    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        source_id = _first_text(row.get("source_id"))
        if source_id:
            index[source_id] = row
    return index


def _load_benchmark_candidate_index(path: Path) -> dict[str, dict[str, Any]]:
    payload = _load_dict(path)
    rows = _catalog_rows(payload, "candidates")
    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        candidate_id = _first_text(row.get("id"))
        if candidate_id:
            index[candidate_id] = row
    return index


def _authority_track_bundle_descriptor(
    *,
    spec_id: str,
    spec: dict[str, Any],
    authority_payload: dict[str, Any],
    authority_catalog_path: Path,
) -> dict[str, Any]:
    tracks = authority_payload.get("tracks") if isinstance(authority_payload.get("tracks"), dict) else {}
    track_name = _first_text(spec.get("track"))
    track_payload = tracks.get(track_name) if isinstance(tracks, dict) else {}
    rows = _catalog_rows(track_payload if isinstance(track_payload, dict) else {}, "cases")
    source_urls = _unique_sorted_tokens(
        [_first_text(row.get("source_url"), row.get("download_url")) for row in rows]
    )
    source_paths = _unique_sorted_tokens([_first_text(row.get("source_file_path")) for row in rows])
    case_ids = _unique_sorted_tokens([_first_text(row.get("case_id")) for row in rows])
    repo_backed_paths = _collect_row_paths(
        rows,
        "source_file_path",
        "hf_csv_path",
        "lf_csv_path",
        "reference_metrics_path",
        "sensor_csv_path",
        "baseline_csv_path",
        "waveform_metrics_path",
    )
    return _finalize_reference_descriptor(
        {
        "reference_id": spec_id,
        "resolved": bool(rows),
        "reference_category": _first_text(spec.get("reference_category")),
        "title": _first_text(spec.get("title"), f"{track_name.upper()} authority bundle"),
        "domain": _first_text(spec.get("domain")),
        "fit_role": _first_text(spec.get("fit_role")),
        "repo_catalog_path": str(authority_catalog_path),
        "repo_record_id": track_name,
        "publisher": "",
        "public_access": "public_reference" if source_urls else "repo_curated_reference",
        "source_urls": source_urls,
        "case_count": len(case_ids),
        "case_ids": case_ids,
        "source_paths": source_paths,
        "repo_backed_paths": repo_backed_paths,
        "track": track_name,
        "real_source_case_count": _bool_count(rows, "real_source"),
        "holdout_case_count": sum(1 for row in rows if _first_text(row.get("holdout_split")) == "holdout"),
        "notes": (
            f"{track_name.upper()} authority bundle with {len(case_ids)} tracked case(s) from the checked-in authority catalog."
            if rows
            else f"{track_name.upper()} authority bundle definition is missing from the checked-in authority catalog."
        ),
        }
    )


def _authority_model_bundle_descriptor(
    *,
    spec_id: str,
    spec: dict[str, Any],
    authority_payload: dict[str, Any],
    authority_catalog_path: Path,
) -> dict[str, Any]:
    tracks = authority_payload.get("tracks") if isinstance(authority_payload.get("tracks"), dict) else {}
    track_name = _first_text(spec.get("track"))
    track_payload = tracks.get(track_name) if isinstance(tracks, dict) else {}
    rows = _catalog_rows(track_payload if isinstance(track_payload, dict) else {}, "models")
    model_ids = {str(item).strip() for item in spec.get("model_ids", []) if str(item).strip()}
    selected_rows = [
        row
        for row in rows
        if _first_text(row.get("id")) in model_ids
    ]
    model_paths = _unique_sorted_tokens([_first_text(row.get("model_path")) for row in selected_rows])
    source_classes = _unique_sorted_tokens([_first_text(row.get("source_class")) for row in selected_rows])
    selected_model_ids = _unique_sorted_tokens([_first_text(row.get("id")) for row in selected_rows])
    return _finalize_reference_descriptor(
        {
        "reference_id": spec_id,
        "resolved": bool(selected_rows),
        "reference_category": _first_text(spec.get("reference_category")),
        "title": _first_text(spec.get("title"), "Authority model bundle"),
        "domain": _first_text(spec.get("domain")),
        "fit_role": _first_text(spec.get("fit_role")),
        "repo_catalog_path": str(authority_catalog_path),
        "repo_record_id": _compact_label(sorted(model_ids)),
        "publisher": "",
        "public_access": "repo_curated_public_model",
        "source_urls": [],
        "case_count": len(selected_model_ids),
        "case_ids": selected_model_ids,
        "source_paths": model_paths,
        "repo_backed_paths": model_paths,
        "source_classes": source_classes,
        "track": track_name,
        "real_source_model_count": _bool_count(selected_rows, "real_source"),
        "shell_beam_mix_required_count": _bool_count(selected_rows, "require_shell_beam_mix"),
        "notes": (
            f"Authority model bundle with {len(selected_model_ids)} public model(s) from the checked-in catalog."
            if selected_rows
            else "Requested authority model bundle was not found in the checked-in authority catalog."
        ),
        }
    )


def _benchmark_candidate_descriptor(
    *,
    spec_id: str,
    spec: dict[str, Any],
    benchmark_index: dict[str, dict[str, Any]],
    benchmark_catalog_path: Path,
) -> dict[str, Any]:
    candidate_id = _first_text(spec.get("candidate_id"))
    row = benchmark_index.get(candidate_id, {})
    source_manifest_stub = _first_text(row.get("source_manifest_stub"))
    return _finalize_reference_descriptor(
        {
        "reference_id": spec_id,
        "resolved": bool(row),
        "reference_category": _first_text(spec.get("reference_category")),
        "title": _first_text(row.get("source_name"), spec_id.replace("_", " ")),
        "domain": _first_text(spec.get("domain"), row.get("benchmark_domain")),
        "fit_role": _first_text(spec.get("fit_role")),
        "repo_catalog_path": str(benchmark_catalog_path),
        "repo_record_id": candidate_id,
        "publisher": _first_text(row.get("source_name")),
        "public_access": "public_reference",
        "source_urls": _unique_sorted_tokens([str(item) for item in row.get("source_urls", [])]),
        "gap_targets": [str(item) for item in row.get("gap_targets", []) if str(item).strip()],
        "integration_fit": [str(item) for item in row.get("integration_fit", []) if str(item).strip()],
        "priority": _first_int(row.get("priority")),
        "stage": _first_text(row.get("stage")),
        "data_shape": [str(item) for item in row.get("data_shape", []) if str(item).strip()],
        "recommended_ingestion_mode": _first_text(row.get("recommended_ingestion_mode")),
        "source_manifest_stub": source_manifest_stub,
        "repo_backed_paths": [source_manifest_stub] if source_manifest_stub else [],
        "notes": _first_text(row.get("notes")),
        }
    )


def _korean_source_descriptor(
    *,
    spec_id: str,
    spec: dict[str, Any],
    korean_index: dict[str, dict[str, Any]],
    korean_catalog_path: Path,
) -> dict[str, Any]:
    source_id = _first_text(spec.get("source_id"))
    row = korean_index.get(source_id, {})
    provenance_url = _first_text(row.get("provenance_url"), row.get("download_url"))
    local_path = _first_text(row.get("local_path"), row.get("curated_local_ifc_reference"))
    return _finalize_reference_descriptor(
        {
        "reference_id": spec_id,
        "resolved": bool(row),
        "reference_category": _first_text(spec.get("reference_category")),
        "title": _first_text(row.get("title"), spec_id.replace("_", " ")),
        "domain": _first_text(spec.get("domain"), row.get("structure_type"), row.get("structural_system")),
        "fit_role": _first_text(spec.get("fit_role")),
        "repo_catalog_path": str(korean_catalog_path),
        "repo_record_id": source_id,
        "publisher": _first_text(row.get("origin_org")),
        "public_access": "public_reference" if provenance_url else "repo_curated_reference",
        "source_urls": [provenance_url] if provenance_url else [],
        "structure_type": _first_text(row.get("structure_type")),
        "structural_system": _first_text(row.get("structural_system")),
        "source_class": _first_text(row.get("source_class")),
        "origin_type": _first_text(row.get("origin_type")),
        "format": _first_text(row.get("format")),
        "content_kind": _first_text(row.get("content_kind")),
        "storey_band": _first_text(row.get("storey_band")),
        "seed_priority": _first_text(row.get("seed_priority")),
        "promotion_hint": _first_text(row.get("promotion_hint")),
        "collection_policy": _first_text(row.get("collection_policy")),
        "local_path": local_path,
        "repo_backed_paths": [local_path] if local_path else [],
        "notes": _first_text(row.get("title")),
        }
    )


def _resolve_reference_descriptor(
    *,
    spec_id: str,
    spec: dict[str, Any],
    korean_index: dict[str, dict[str, Any]],
    korean_catalog_path: Path,
    benchmark_index: dict[str, dict[str, Any]],
    benchmark_catalog_path: Path,
    authority_payload: dict[str, Any],
    authority_catalog_path: Path,
) -> dict[str, Any]:
    resolver = _first_text(spec.get("resolver"))
    if resolver == "korean_source_record":
        return _korean_source_descriptor(
            spec_id=spec_id,
            spec=spec,
            korean_index=korean_index,
            korean_catalog_path=korean_catalog_path,
        )
    if resolver == "benchmark_candidate":
        return _benchmark_candidate_descriptor(
            spec_id=spec_id,
            spec=spec,
            benchmark_index=benchmark_index,
            benchmark_catalog_path=benchmark_catalog_path,
        )
    if resolver == "authority_track_bundle":
        return _authority_track_bundle_descriptor(
            spec_id=spec_id,
            spec=spec,
            authority_payload=authority_payload,
            authority_catalog_path=authority_catalog_path,
        )
    if resolver == "authority_model_bundle":
        return _authority_model_bundle_descriptor(
            spec_id=spec_id,
            spec=spec,
            authority_payload=authority_payload,
            authority_catalog_path=authority_catalog_path,
        )
    return _finalize_reference_descriptor(
        {
            "reference_id": spec_id,
            "resolved": False,
            "reference_category": _first_text(spec.get("reference_category")),
            "title": spec_id.replace("_", " "),
            "domain": _first_text(spec.get("domain")),
            "fit_role": _first_text(spec.get("fit_role")),
            "repo_catalog_path": "",
            "repo_record_id": "",
            "publisher": "",
            "public_access": "unknown",
            "source_urls": [],
            "repo_backed_paths": [],
            "notes": "Unknown reference resolver.",
        }
    )


def _normalize_portfolio_rows(portfolio_payload: dict[str, Any] | list[Any]) -> tuple[str, list[dict[str, Any]]]:
    portfolio_name = "phase1-native-authoring-ops-portfolio"
    if isinstance(portfolio_payload, dict):
        portfolio_name = _first_text(portfolio_payload.get("portfolio_name"), portfolio_name)
        rows = portfolio_payload.get("family_rows")
        if not isinstance(rows, list):
            rows = portfolio_payload.get("families")
    elif isinstance(portfolio_payload, list):
        rows = portfolio_payload
    else:
        rows = []

    normalized_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows if isinstance(rows, list) else [], start=1):
        if not isinstance(row, dict):
            continue
        family_id = _first_text(row.get("family_id"), row.get("authoring_family_id"), f"family-{index}")
        if not family_id:
            continue
        normalized_rows.append(
            {
                "family_id": family_id,
                "authoring_family_id": _first_text(row.get("authoring_family_id"), family_id),
                "family_label": _first_text(row.get("family_label"), family_id.replace("_", " ").title()),
                "project_id": _first_text(row.get("project_id")),
                "project_name": _first_text(row.get("project_name")),
                "draft_label": _first_text(row.get("draft_label")),
                "commercialization_status": _normalize_status(row.get("commercialization_status")),
                "commercialization_score": _first_int(row.get("commercialization_score")),
                "preferred_design_family": _first_text(row.get("preferred_design_family")),
                "member_type_label": _first_text(row.get("member_type_label")),
                "story_count": _first_int(row.get("story_count")),
                "member_count": _first_int(row.get("member_count")),
                "solver_combo_count": _first_int(row.get("solver_combo_count")),
                "summary_line": _first_text(row.get("summary_line")),
                "commercialization_summary_line": _first_text(row.get("commercialization_summary_line")),
                "artifacts": dict(row.get("artifacts")) if isinstance(row.get("artifacts"), dict) else {},
            }
        )
    return portfolio_name, normalized_rows


def _workspace_family_metadata(family_root: Path) -> dict[str, Any]:
    payload = _load_dict(family_root / "native_authoring_workspace_summary.json")
    selected_family = payload.get("selected_family") if isinstance(payload.get("selected_family"), dict) else {}
    editor_controls = payload.get("editor_controls") if isinstance(payload.get("editor_controls"), dict) else {}
    return {
        "family_description": _first_text(selected_family.get("description")),
        "preferred_design_family": _first_text(
            selected_family.get("preferred_design_family"),
            editor_controls.get("preferred_design_family"),
        ),
        "representative_member_types": [
            str(item) for item in selected_family.get("representative_member_types", []) if str(item).strip()
        ],
    }


def _internal_corpus_entries(*, family_id: str, family_root: Path, portfolio_row: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    artifact_map = portfolio_row.get("artifacts") if isinstance(portfolio_row.get("artifacts"), dict) else {}
    for spec in INTERNAL_CORPUS_SPECS:
        candidate_path = family_root / str(spec["filename"])
        if spec["entry_id"] == "ops_bundle":
            artifact_path = _first_text(artifact_map.get("native_authoring_ops_bundle_json"))
            if artifact_path:
                candidate_path = Path(artifact_path)
        entries.append(
            {
                "entry_id": str(spec["entry_id"]),
                "title": str(spec["title"]),
                "entry_type": "internal_corpus",
                "corpus_role": str(spec["corpus_role"]),
                "family_id": family_id,
                "path": str(candidate_path),
                "exists": bool(candidate_path.exists()),
            }
        )
    return entries


def _family_surface_ids(reference_entries: list[dict[str, Any]]) -> list[str]:
    surface_ids = ["catalog_card", "guided_demo", "technical_review"]
    for entry in reference_entries:
        surface_ids.extend(REFERENCE_CATEGORY_SURFACE_IDS.get(_first_text(entry.get("reference_category")), ()))
    return _unique_sorted_tokens(surface_ids)


def _portfolio_artifact_paths(portfolio_row: dict[str, Any]) -> tuple[list[str], list[str]]:
    artifact_map = portfolio_row.get("artifacts") if isinstance(portfolio_row.get("artifacts"), dict) else {}
    artifact_keys = _unique_sorted_tokens([str(key) for key in artifact_map.keys() if str(key).strip()])
    artifact_paths = _unique_sorted_tokens([str(value) for value in artifact_map.values() if str(value).strip()])
    return artifact_keys, artifact_paths


def _family_coverage(
    *,
    internal_entries: list[dict[str, Any]],
    reference_entries: list[dict[str, Any]],
    portfolio_row: dict[str, Any],
) -> dict[str, Any]:
    artifact_keys, release_artifact_paths = _portfolio_artifact_paths(portfolio_row)
    internal_paths = _unique_sorted_tokens([_first_text(entry.get("path")) for entry in internal_entries])
    reference_repo_paths = _unique_sorted_tokens(
        [
            str(path)
            for entry in reference_entries
            for path in entry.get("repo_backed_paths", [])
            if str(path).strip()
        ]
    )
    all_repo_paths = _unique_sorted_tokens(internal_paths + release_artifact_paths + reference_repo_paths)

    public_reference_entries = [entry for entry in reference_entries if int(entry.get("public_url_count", 0)) > 0]
    public_reference_ids = [_first_text(entry.get("reference_id")) for entry in public_reference_entries]
    public_source_urls = _unique_sorted_tokens(
        [
            str(url)
            for entry in public_reference_entries
            for url in entry.get("source_urls", [])
            if str(url).strip()
        ]
    )
    public_publishers = _unique_sorted_tokens(
        [_first_text(entry.get("publisher")) for entry in public_reference_entries]
    )

    resolved_reference_count = sum(1 for entry in reference_entries if bool(entry.get("resolved", False)))
    reference_ids = [_first_text(entry.get("reference_id")) for entry in reference_entries]
    repo_catalog_paths = _unique_sorted_tokens(
        [_first_text(entry.get("repo_catalog_path")) for entry in reference_entries]
    )
    domains = _unique_sorted_tokens([_first_text(entry.get("domain")) for entry in reference_entries])
    fit_roles = _unique_sorted_tokens([_first_text(entry.get("fit_role")) for entry in reference_entries])

    design_reference_ids = [
        _first_text(entry.get("reference_id"))
        for entry in reference_entries
        if _first_text(entry.get("design_authority_kind")) == "design_reference"
    ]
    benchmark_reference_ids = [
        _first_text(entry.get("reference_id"))
        for entry in reference_entries
        if _first_text(entry.get("design_authority_kind")) == "benchmark_reference"
    ]
    authority_reference_ids = [
        _first_text(entry.get("reference_id"))
        for entry in reference_entries
        if _first_text(entry.get("design_authority_kind")) == "authority_reference"
    ]
    design_authority_labels = _unique_tokens_in_order(
        [
            "design" if design_reference_ids else "",
            "benchmark" if benchmark_reference_ids else "",
            "authority" if authority_reference_ids else "",
        ]
    )

    coverage = {
        "local": {
            "present": bool(_count_existing_paths(all_repo_paths)),
            "required_internal_entries_present": REQUIRED_INTERNAL_ENTRY_IDS
            == {
                entry["entry_id"]
                for entry in internal_entries
                if entry["entry_id"] in REQUIRED_INTERNAL_ENTRY_IDS and bool(entry.get("exists", False))
            },
            "internal_corpus_entry_count": len(internal_entries),
            "existing_internal_corpus_entry_count": sum(1 for entry in internal_entries if bool(entry.get("exists", False))),
            "release_artifact_count": len(release_artifact_paths),
            "existing_release_artifact_count": _count_existing_paths(release_artifact_paths),
            "reference_repo_path_count": len(reference_repo_paths),
            "existing_reference_repo_path_count": _count_existing_paths(reference_repo_paths),
            "artifact_keys": artifact_keys,
            "internal_paths": internal_paths,
            "release_artifact_paths": release_artifact_paths,
            "reference_repo_paths": reference_repo_paths,
            "repo_path_count": len(all_repo_paths),
            "existing_repo_path_count": _count_existing_paths(all_repo_paths),
            "repo_paths": all_repo_paths,
            "summary_line": (
                f"local coverage: internal={len(internal_entries)} | release_artifacts={len(release_artifact_paths)} | "
                f"reference_repo_paths={len(reference_repo_paths)} | repo_paths={len(all_repo_paths)}"
            ),
        },
        "public": {
            "present": bool(public_source_urls),
            "reference_count": len(public_reference_entries),
            "reference_ids": public_reference_ids,
            "source_url_count": len(public_source_urls),
            "publisher_count": len(public_publishers),
            "publishers": public_publishers,
            "source_urls": public_source_urls,
            "summary_line": (
                f"public coverage: references={len(public_reference_entries)} | urls={len(public_source_urls)} | "
                f"publishers={len(public_publishers)}"
            ),
        },
        "reference": {
            "present": bool(reference_entries),
            "reference_count": len(reference_entries),
            "resolved_reference_count": resolved_reference_count,
            "unresolved_reference_count": len(reference_entries) - resolved_reference_count,
            "reference_ids": reference_ids,
            "repo_catalog_path_count": len(repo_catalog_paths),
            "repo_catalog_paths": repo_catalog_paths,
            "domains": domains,
            "fit_roles": fit_roles,
            "summary_line": (
                f"reference coverage: resolved={resolved_reference_count}/{len(reference_entries)} | "
                f"domains={len(domains)} | catalogs={len(repo_catalog_paths)}"
            ),
        },
        "design_authority": {
            "present": bool(reference_entries),
            "design_reference_count": len(design_reference_ids),
            "benchmark_reference_count": len(benchmark_reference_ids),
            "authority_reference_count": len(authority_reference_ids),
            "design_reference_ids": design_reference_ids,
            "benchmark_reference_ids": benchmark_reference_ids,
            "authority_reference_ids": authority_reference_ids,
            "span_count": len(design_authority_labels),
            "coverage_label": ", ".join(design_authority_labels),
            "summary_line": (
                f"design authority coverage: design={len(design_reference_ids)} | "
                f"benchmark={len(benchmark_reference_ids)} | authority={len(authority_reference_ids)}"
            ),
        },
    }
    coverage["coverage_axes_present"] = [
        axis for axis in ("local", "public", "reference", "design_authority") if coverage[axis]["present"]
    ]
    coverage["summary_line"] = (
        f"coverage axes={','.join(coverage['coverage_axes_present'])} | "
        f"local_repo_paths={coverage['local']['repo_path_count']} | "
        f"public_urls={coverage['public']['source_url_count']} | "
        f"references={coverage['reference']['resolved_reference_count']}/{coverage['reference']['reference_count']} | "
        f"design_authority={coverage['design_authority']['coverage_label'] or 'none'}"
    )
    return coverage


def build_native_authoring_family_corpus_manifest(
    *,
    portfolio_payload: dict[str, Any] | list[Any] | None = None,
    portfolio_json_path: Path | None = DEFAULT_PORTFOLIO_JSON,
    release_root: Path = DEFAULT_RELEASE_ROOT,
    korean_source_catalog_path: Path = DEFAULT_KOREAN_SOURCE_CATALOG,
    benchmark_diversification_catalog_path: Path = DEFAULT_BENCHMARK_DIVERSIFICATION_CATALOG,
    authority_source_catalog_path: Path = DEFAULT_AUTHORITY_SOURCE_CATALOG,
    out: Path = DEFAULT_OUT,
    generated_at: str | None = None,
) -> dict[str, Any]:
    timestamp = str(generated_at or "").strip() or _now_utc_iso()
    if portfolio_payload is None and portfolio_json_path is not None:
        portfolio_payload = _load_json(portfolio_json_path)
    portfolio_payload = portfolio_payload if portfolio_payload is not None else {}
    portfolio_name, portfolio_rows = _normalize_portfolio_rows(portfolio_payload)

    korean_index = _load_korean_source_index(korean_source_catalog_path)
    benchmark_index = _load_benchmark_candidate_index(benchmark_diversification_catalog_path)
    authority_payload = _load_dict(authority_source_catalog_path)

    family_rows: list[dict[str, Any]] = []
    linkage_rows: list[dict[str, Any]] = []
    unresolved_family_ids: list[str] = []
    unresolved_reference_ids: list[str] = []
    total_internal_entries = 0
    total_reference_entries = 0
    total_design_reference_entries = 0
    total_benchmark_reference_entries = 0
    total_authority_reference_entries = 0

    for portfolio_row in portfolio_rows:
        family_id = str(portfolio_row["family_id"])
        linkage_spec = FAMILY_LINKAGE_SPECS.get(family_id)
        family_root = release_root / family_id
        workspace_metadata = _workspace_family_metadata(family_root)
        internal_entries = _internal_corpus_entries(
            family_id=family_id,
            family_root=family_root,
            portfolio_row=portfolio_row,
        )
        reference_entries: list[dict[str, Any]] = []
        if linkage_spec is None:
            unresolved_family_ids.append(family_id)
        else:
            for reference_id in linkage_spec.get("reference_ids", []):
                reference_spec = REFERENCE_SPECS.get(reference_id, {})
                descriptor = _resolve_reference_descriptor(
                    spec_id=reference_id,
                    spec=reference_spec,
                    korean_index=korean_index,
                    korean_catalog_path=korean_source_catalog_path,
                    benchmark_index=benchmark_index,
                    benchmark_catalog_path=benchmark_diversification_catalog_path,
                    authority_payload=authority_payload,
                    authority_catalog_path=authority_source_catalog_path,
                )
                if not bool(descriptor.get("resolved", False)):
                    unresolved_reference_ids.append(f"{family_id}:{reference_id}")
                reference_entries.append(descriptor)

        surface_ids = _family_surface_ids(reference_entries)
        required_internal_ready = {
            entry["entry_id"]
            for entry in internal_entries
            if entry["entry_id"] in REQUIRED_INTERNAL_ENTRY_IDS and bool(entry["exists"])
        }
        public_reference_count = len(reference_entries)
        design_reference_count = sum(
            1 for entry in reference_entries if _first_text(entry.get("reference_category")) == "public_design_reference"
        )
        benchmark_reference_count = sum(
            1 for entry in reference_entries if _first_text(entry.get("reference_category")) == "benchmark_candidate"
        )
        authority_reference_count = sum(
            1
            for entry in reference_entries
            if _first_text(entry.get("reference_category")) in {"authority_holdout_bundle", "authority_model_bundle"}
        )
        coverage = _family_coverage(
            internal_entries=internal_entries,
            reference_entries=reference_entries,
            portfolio_row=portfolio_row,
        )
        family_contract_pass = bool(
            linkage_spec
            and required_internal_ready == REQUIRED_INTERNAL_ENTRY_IDS
            and reference_entries
            and all(bool(entry.get("resolved", False)) for entry in reference_entries)
        )
        family_row = {
            "family_id": family_id,
            "family_label": portfolio_row["family_label"],
            "family_description": _first_text(workspace_metadata.get("family_description")),
            "portfolio_name": portfolio_name,
            "project_id": portfolio_row.get("project_id", ""),
            "project_name": portfolio_row.get("project_name", ""),
            "draft_label": portfolio_row.get("draft_label", ""),
            "commercialization_status": portfolio_row["commercialization_status"],
            "commercialization_score": portfolio_row["commercialization_score"],
            "commercialization_lane": _first_text(linkage_spec.get("commercialization_lane") if linkage_spec else ""),
            "commercialization_focus": _first_text(linkage_spec.get("commercialization_focus") if linkage_spec else ""),
            "preferred_design_family": _first_text(
                portfolio_row.get("preferred_design_family"),
                workspace_metadata.get("preferred_design_family"),
            ),
            "member_type_label": _first_text(portfolio_row.get("member_type_label")),
            "representative_member_types": [
                str(item) for item in workspace_metadata.get("representative_member_types", []) if str(item).strip()
            ],
            "story_count": portfolio_row["story_count"],
            "member_count": portfolio_row["member_count"],
            "solver_combo_count": portfolio_row["solver_combo_count"],
            "surface_ids": surface_ids,
            "surface_label": _compact_label([SURFACE_LIBRARY[surface_id]["label"] for surface_id in surface_ids]),
            "coverage_axes": list(coverage["coverage_axes_present"]),
            "local_repo_path_count": int(coverage["local"]["repo_path_count"]),
            "public_source_url_count": int(coverage["public"]["source_url_count"]),
            "resolved_reference_count": int(coverage["reference"]["resolved_reference_count"]),
            "design_authority_span_count": int(coverage["design_authority"]["span_count"]),
            "internal_corpus_entry_count": len(internal_entries),
            "public_reference_count": public_reference_count,
            "design_reference_count": design_reference_count,
            "benchmark_reference_count": benchmark_reference_count,
            "authority_reference_count": authority_reference_count,
            "contract_pass": family_contract_pass,
            "internal_corpus_entries": internal_entries,
            "reference_source_entries": reference_entries,
            "coverage": coverage,
            "commercialization_evidence_summary_line": coverage["summary_line"],
            "summary_line": (
                f"{portfolio_row['family_label']}: {portfolio_row['commercialization_status'].upper()} | "
                f"lane={_first_text(linkage_spec.get('commercialization_lane') if linkage_spec else 'check')} | "
                f"internal={len(internal_entries)} | public_refs={public_reference_count} | "
                f"authority={authority_reference_count} | benchmark={benchmark_reference_count} | "
                f"surfaces={', '.join(surface_ids)}"
            ),
        }
        family_rows.append(family_row)

        total_internal_entries += len(internal_entries)
        total_reference_entries += public_reference_count
        total_design_reference_entries += design_reference_count
        total_benchmark_reference_entries += benchmark_reference_count
        total_authority_reference_entries += authority_reference_count

        for entry in internal_entries:
            linkage_rows.append(
                {
                    "link_id": f"{family_id}::internal::{entry['entry_id']}",
                    "family_id": family_id,
                    "family_label": portfolio_row["family_label"],
                    "link_type": "internal_corpus",
                    "reference_id": str(entry["entry_id"]),
                    "title": str(entry["title"]),
                    "category": "internal_corpus",
                    "path": str(entry["path"]),
                    "exists": bool(entry["exists"]),
                    "coverage_axes": ["local"],
                    "design_authority_kind": "",
                    "repo_backed_paths": [str(entry["path"])] if _first_text(entry.get("path")) else [],
                    "repo_backed_path_count": 1 if _first_text(entry.get("path")) else 0,
                    "existing_repo_backed_path_count": 1 if bool(entry["exists"]) else 0,
                    "public_url_count": 0,
                    "surface_ids": surface_ids,
                }
            )
        for entry in reference_entries:
            linkage_rows.append(
                {
                    "link_id": f"{family_id}::reference::{entry['reference_id']}",
                    "family_id": family_id,
                    "family_label": portfolio_row["family_label"],
                    "link_type": "reference_source",
                    "reference_id": str(entry["reference_id"]),
                    "title": str(entry["title"]),
                    "category": _first_text(entry.get("reference_category")),
                    "resolved": bool(entry.get("resolved", False)),
                    "domain": _first_text(entry.get("domain")),
                    "fit_role": _first_text(entry.get("fit_role")),
                    "publisher": _first_text(entry.get("publisher")),
                    "repo_catalog_path": _first_text(entry.get("repo_catalog_path")),
                    "repo_record_id": _first_text(entry.get("repo_record_id")),
                    "source_urls": list(entry.get("source_urls", [])),
                    "coverage_axes": list(entry.get("coverage_axes", [])),
                    "design_authority_kind": _first_text(entry.get("design_authority_kind")),
                    "repo_backed_paths": list(entry.get("repo_backed_paths", [])),
                    "repo_backed_path_count": _first_int(entry.get("repo_backed_path_count")),
                    "existing_repo_backed_path_count": _first_int(entry.get("existing_repo_backed_path_count")),
                    "public_url_count": _first_int(entry.get("public_url_count")),
                    "surface_ids": surface_ids,
                }
            )

    ready_family_count = sum(
        1 for row in family_rows if _first_text(row.get("commercialization_status")) == "ready"
    )
    surface_family_counts = {
        surface_id: sum(1 for row in family_rows if surface_id in row.get("surface_ids", []))
        for surface_id in SURFACE_LIBRARY
    }
    coverage_axis_family_counts = {
        axis: sum(1 for row in family_rows if axis in row.get("coverage_axes", []))
        for axis in ("local", "public", "reference", "design_authority")
    }
    families_with_design_reference_count = sum(1 for row in family_rows if int(row.get("design_reference_count", 0)) > 0)
    families_with_benchmark_reference_count = sum(
        1 for row in family_rows if int(row.get("benchmark_reference_count", 0)) > 0
    )
    families_with_authority_reference_count = sum(
        1 for row in family_rows if int(row.get("authority_reference_count", 0)) > 0
    )
    family_scoped_repo_path_count = sum(int(row.get("local_repo_path_count", 0)) for row in family_rows)
    unique_repo_paths = _unique_sorted_tokens(
        [
            str(path)
            for row in family_rows
            for path in row.get("coverage", {}).get("local", {}).get("repo_paths", [])
            if str(path).strip()
        ]
    )
    family_scoped_public_source_url_count = sum(int(row.get("public_source_url_count", 0)) for row in family_rows)
    unique_public_source_urls = _unique_sorted_tokens(
        [
            str(url)
            for row in family_rows
            for url in row.get("coverage", {}).get("public", {}).get("source_urls", [])
            if str(url).strip()
        ]
    )
    coverage_summary = {
        "axis_family_counts": coverage_axis_family_counts,
        "family_scoped_repo_path_count": family_scoped_repo_path_count,
        "unique_repo_path_count": len(unique_repo_paths),
        "existing_unique_repo_path_count": _count_existing_paths(unique_repo_paths),
        "family_scoped_public_source_url_count": family_scoped_public_source_url_count,
        "unique_public_source_url_count": len(unique_public_source_urls),
        "families_with_design_reference_count": families_with_design_reference_count,
        "families_with_benchmark_reference_count": families_with_benchmark_reference_count,
        "families_with_authority_reference_count": families_with_authority_reference_count,
        "summary_line": (
            "coverage summary: "
            f"axes={', '.join(f'{axis}={count}' for axis, count in coverage_axis_family_counts.items())} | "
            f"repo_paths={family_scoped_repo_path_count} family-scoped / {len(unique_repo_paths)} unique | "
            f"public_urls={family_scoped_public_source_url_count} family-scoped / {len(unique_public_source_urls)} unique"
        ),
    }
    contract_pass = bool(
        family_rows
        and not unresolved_family_ids
        and not unresolved_reference_ids
        and all(bool(row.get("contract_pass", False)) for row in family_rows)
    )
    reason_code = "PASS" if contract_pass else ("CHECK" if family_rows else "ERR_INPUT")
    summary_line = (
        "Native authoring family corpus manifest: "
        f"{reason_code} | families={len(family_rows)} | ready={ready_family_count} | "
        f"internal={total_internal_entries} | public_refs={total_reference_entries} | "
        f"authority={total_authority_reference_entries} | benchmark={total_benchmark_reference_entries} | "
        f"design={total_design_reference_entries} | "
        f"surfaces={', '.join(f'{surface_id}={count}' for surface_id, count in surface_family_counts.items() if count)}"
    )

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-native-authoring-family-corpus-manifest",
        "generated_at": timestamp,
        "inputs": {
            "portfolio_json_path": str(portfolio_json_path) if portfolio_json_path is not None else "",
            "release_root": str(release_root),
            "korean_source_catalog_path": str(korean_source_catalog_path),
            "benchmark_diversification_catalog_path": str(benchmark_diversification_catalog_path),
            "authority_source_catalog_path": str(authority_source_catalog_path),
        },
        "summary": {
            "portfolio_name": portfolio_name,
            "family_count": len(family_rows),
            "ready_family_count": ready_family_count,
            "internal_corpus_entry_count": total_internal_entries,
            "public_reference_count": total_reference_entries,
            "design_reference_count": total_design_reference_entries,
            "benchmark_reference_count": total_benchmark_reference_entries,
            "authority_reference_count": total_authority_reference_entries,
            "coverage_axis_count": len([count for count in coverage_axis_family_counts.values() if count]),
            "family_scoped_repo_path_count": family_scoped_repo_path_count,
            "unique_repo_path_count": len(unique_repo_paths),
            "family_scoped_public_source_url_count": family_scoped_public_source_url_count,
            "unique_public_source_url_count": len(unique_public_source_urls),
            "families_with_design_reference_count": families_with_design_reference_count,
            "families_with_benchmark_reference_count": families_with_benchmark_reference_count,
            "families_with_authority_reference_count": families_with_authority_reference_count,
            "surface_count": len([count for count in surface_family_counts.values() if count]),
            "surface_label": _compact_label(
                [SURFACE_LIBRARY[surface_id]["label"] for surface_id, count in surface_family_counts.items() if count]
            ),
            "unresolved_family_count": len(unresolved_family_ids),
            "unresolved_reference_count": len(unresolved_reference_ids),
        },
        "coverage_summary": coverage_summary,
        "surfaces": [
            {
                "surface_id": surface_id,
                "label": surface_payload["label"],
                "description": surface_payload["description"],
                "family_count": int(surface_family_counts.get(surface_id, 0)),
            }
            for surface_id, surface_payload in SURFACE_LIBRARY.items()
        ],
        "family_rows": family_rows,
        "linkage_rows": linkage_rows,
        "checks": {
            "all_families_mapped": not unresolved_family_ids,
            "all_references_resolved": not unresolved_reference_ids,
            "all_required_internal_entries_present": all(
                REQUIRED_INTERNAL_ENTRY_IDS
                == {
                    entry["entry_id"]
                    for entry in row.get("internal_corpus_entries", [])
                    if entry["entry_id"] in REQUIRED_INTERNAL_ENTRY_IDS and bool(entry.get("exists", False))
                }
                for row in family_rows
            )
            if family_rows
            else False,
        },
        "unresolved_family_ids": unresolved_family_ids,
        "unresolved_reference_ids": unresolved_reference_ids,
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
        "summary_line": summary_line,
        "artifacts": {
            "native_authoring_family_corpus_manifest_json": str(out),
        },
    }
    _write_json(out, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portfolio-json", type=Path, default=DEFAULT_PORTFOLIO_JSON)
    parser.add_argument("--release-root", type=Path, default=DEFAULT_RELEASE_ROOT)
    parser.add_argument("--korean-source-catalog", type=Path, default=DEFAULT_KOREAN_SOURCE_CATALOG)
    parser.add_argument(
        "--benchmark-diversification-catalog",
        type=Path,
        default=DEFAULT_BENCHMARK_DIVERSIFICATION_CATALOG,
    )
    parser.add_argument("--authority-source-catalog", type=Path, default=DEFAULT_AUTHORITY_SOURCE_CATALOG)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--generated-at", default="")
    args = parser.parse_args()

    payload = build_native_authoring_family_corpus_manifest(
        portfolio_json_path=args.portfolio_json,
        release_root=args.release_root,
        korean_source_catalog_path=args.korean_source_catalog,
        benchmark_diversification_catalog_path=args.benchmark_diversification_catalog,
        authority_source_catalog_path=args.authority_source_catalog,
        out=args.out,
        generated_at=args.generated_at or None,
    )
    print(payload["summary_line"])
    return 0 if payload["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
