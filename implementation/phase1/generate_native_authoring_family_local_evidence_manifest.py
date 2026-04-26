#!/usr/bin/env python3
"""Generate concrete local evidence manifest for native authoring families."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from implementation.phase1.generate_native_authoring_family_corpus_manifest import (
    DEFAULT_AUTHORITY_SOURCE_CATALOG,
    DEFAULT_BENCHMARK_DIVERSIFICATION_CATALOG,
    DEFAULT_KOREAN_SOURCE_CATALOG,
    DEFAULT_PORTFOLIO_JSON,
    DEFAULT_RELEASE_ROOT,
    REFERENCE_SPECS,
    build_native_authoring_family_corpus_manifest,
    _compact_label,
    _first_text,
    _load_dict,
    _now_utc_iso,
    _unique_sorted_tokens,
    _write_json,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FAMILY_CORPUS_MANIFEST = DEFAULT_RELEASE_ROOT / "native_authoring_family_corpus_manifest.json"
DEFAULT_OUT = DEFAULT_RELEASE_ROOT / "native_authoring_family_local_evidence_manifest.json"
DEFAULT_KOREAN_SOURCE_INGEST_REPORT = Path("implementation/phase1/open_data/korea/korean_source_ingest_report.json")
DEFAULT_KOREAN_COLLECTION_REPORT = Path(
    "implementation/phase1/open_data/korea/korean_public_structure_collection_report.json"
)
DEFAULT_BENCHMARK_CATALOG = Path("implementation/phase1/open_data/megastructure/mega_structure_catalog.json")
DEFAULT_MIDAS_NATIVE_CORPUS_MANIFEST = Path("implementation/phase1/open_data/midas/midas_native_corpus_manifest.json")
DEFAULT_VISUALIZATION_ROOT = Path("implementation/phase1/release/visualization/entries")

REASONS = {
    "PASS": "native authoring family local evidence manifest generated",
    "CHECK": "native authoring family local evidence manifest generated with linked-only gaps",
    "ERR_INPUT": "no native authoring family rows available for local evidence generation",
}

BENCHMARK_REFERENCE_EXTRA_GLOBS: dict[str, tuple[str, ...]] = {
    "usgs_nsmp_structural_arrays": (
        "implementation/phase1/release/benchmark_expansion/authority_measured_catalog_cards.json",
        "implementation/phase1/release/benchmark_expansion/authority_measured_lane.json",
    ),
    "peer_spd_rc_columns": (
        "implementation/phase1/open_data/pbd_hinge/peer_spd_column_seed_manifest.json",
        "implementation/phase1/open_data/pbd_hinge/peer_spd_column_materialize_report.json",
        "implementation/phase1/open_data/pbd_hinge/peer_spd_hinge_benchmark_gate_report.json",
        "implementation/phase1/open_data/pbd_hinge/peer_spd_hinge_fixture_regression_report.json",
        "implementation/phase1/open_data/pbd_hinge/peer_spd_rc_column_*.source_manifest.json",
        "implementation/phase1/open_data/pbd_hinge/peer_spd_rc_column_*.hinge_fixture.json",
        "implementation/phase1/open_data/pbd_hinge/peer_spd_rc_column_*.hinge_fixture.normalize_report.json",
        "implementation/phase1/release/external_benchmark_kickoff/runs/hinge_peer_spd_*/benchmark_task_result.json",
    ),
    "tpu_highrise_wind_pressure_and_force": (
        "implementation/phase1/open_data/wind/tpu_hffb_seed_manifest.json",
        "implementation/phase1/open_data/wind/tpu_hffb_benchmark_gate_report.json",
        "implementation/phase1/open_data/wind/tpu/case_*_materialized/*.source_manifest.json",
        "implementation/phase1/open_data/wind/tpu/case_*_materialized/*.csv",
        "implementation/phase1/open_data/wind/tpu/case_*_materialized/*.prepare_report.json",
        "implementation/phase1/open_data/wind/tpu/case_*_materialized/*.convert_report.json",
        "implementation/phase1/release/external_benchmark_kickoff/runs/wind_tpu_hffb_*/benchmark_task_result.json",
    ),
    "canton_tower_megastructure": (
        "implementation/phase1/open_data/megastructure/canton_tower_conversion_report.json",
        "implementation/phase1/open_data/megastructure/canton_tower_conversion_report.source_manifest.json",
        "implementation/phase1/open_data/megastructure/canton_tower_reduced_shm.source_manifest.json",
        "implementation/phase1/open_data/megastructure/canton_tower_reduced_shm_fetch_report.json",
        "implementation/phase1/open_data/megastructure/canton_tower_reduced_shm/**/*",
        "implementation/phase1/release/benchmark_expansion/canton_tower_reduced_order_compare_report.json",
    ),
    "edefense_peer_blind_prediction": (
        "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_manifest.json",
        "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.source_manifest.json",
        "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_landing_manifest.json",
        "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_landing_status.json",
        "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_normalized.json",
        "implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_public_input_bundle_report.json",
        "implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_case_build_report.json",
        "implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_sample_case_build_report.json",
        "implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_sample_measured_response_report.json",
        "implementation/phase1/release/benchmark_expansion/peer_blind_prediction_compare_report.json",
        "implementation/phase1/release/benchmark_expansion/peer_blind_prediction_sample_compare_report.json",
    ),
}

FAMILY_TEST_FIXTURE_SPECS: dict[str, tuple[dict[str, Any], ...]] = {
    "sample_tower": (
        {
            "path": "tests/test_compare_midas_loadcomb_roundtrip.py",
            "linkage_tags": ("roundtrip",),
            "note": "Roundtrip contract fixture for deterministic LOADCOMB parity.",
        },
        {
            "path": "tests/test_generate_native_authoring_family_corpus_manifest.py",
            "linkage_tags": ("review",),
            "note": "Family corpus manifest regression for native authoring portfolio breadth.",
        },
    ),
    "steel_braced_frame": (
        {
            "path": "tests/test_prepare_opensees_family_compare_report.py",
            "linkage_tags": ("benchmark", "review"),
            "note": "OpenSees family compare regression for steel authority bundle coverage.",
        },
        {
            "path": "tests/test_prepare_opensees_shell_beam_mix_baseline_bridge.py",
            "linkage_tags": ("benchmark",),
            "note": "Shell-beam mix bridge fixture tied to SCBF authority models.",
        },
    ),
    "rc_wall_core": (
        {
            "path": "tests/test_run_peer_spd_hinge_fixture_regression.py",
            "linkage_tags": ("benchmark",),
            "note": "PEER SPD hinge fixture regression for RC response families.",
        },
        {
            "path": "tests/test_prepare_edefense_peer_blind_prediction_source_manifest.py",
            "linkage_tags": ("benchmark", "review"),
            "note": "Blind-prediction source manifest fixture for RC authority benchmark ingestion.",
        },
    ),
    "composite_podium": (
        {
            "path": "tests/test_panel_zone_3d_source_contract.py",
            "linkage_tags": ("benchmark", "review"),
            "note": "Joint-source contract fixture for podium transfer detailing review.",
        },
        {
            "path": "tests/test_panel_zone_clash_artifact.py",
            "linkage_tags": ("review",),
            "note": "Panel-zone clash artifact fixture for podium review evidence.",
        },
    ),
    "outrigger_transfer_tower": (
        {
            "path": "tests/test_prepare_tpu_hffb_seed.py",
            "linkage_tags": ("benchmark",),
            "note": "TPU HFFB seed preparation fixture for wind benchmark linkage.",
        },
        {
            "path": "tests/test_probe_canton_tower_reduced_shm_sources.py",
            "linkage_tags": ("benchmark", "review"),
            "note": "Canton Tower source probe fixture for measured megatall evidence.",
        },
    ),
    "dual_system_hospital": (
        {
            "path": "tests/test_prepare_edefense_peer_measured_response_landing_manifest.py",
            "linkage_tags": ("benchmark", "review"),
            "note": "Measured-response landing fixture for occupancy-critical review lanes.",
        },
        {
            "path": "tests/test_generate_korean_source_catalog.py",
            "linkage_tags": ("roundtrip",),
            "note": "Korean source catalog regression for local public-source readiness.",
        },
    ),
    "belt_truss_mega_frame": (
        {
            "path": "tests/test_canton_tower_reduced_order_compare.py",
            "linkage_tags": ("benchmark", "review"),
            "note": "Reduced-order compare fixture for megatall measured benchmark linkage.",
        },
        {
            "path": "tests/test_prepare_opstool_606m_outrigger_synthetic_bridge.py",
            "linkage_tags": ("benchmark",),
            "note": "Synthetic outrigger bridge fixture backing premium megatall storytelling.",
        },
    ),
    "deep_transfer_basement": (
        {
            "path": "tests/test_stage1_foundations.py",
            "linkage_tags": ("benchmark",),
            "note": "Foundation stage fixture for below-grade load-path evidence.",
        },
        {
            "path": "tests/test_run_foundation_soil_link_gate.py",
            "linkage_tags": ("benchmark", "review"),
            "note": "Foundation-soil link gate regression for basement / SSI evidence.",
        },
    ),
}


def _repo_path(path_like: str | Path) -> Path:
    path = Path(path_like)
    return path if path.is_absolute() else REPO_ROOT / path


def _repo_rel(path_like: str | Path) -> str:
    path = _repo_path(path_like).resolve()
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _load_json(path: Path) -> dict[str, Any] | list[Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_repo_string_paths(value: Any) -> list[str]:
    paths: list[str] = []
    if isinstance(value, str):
        normalized = value.strip()
        if normalized.startswith("implementation/") or normalized.startswith("tests/") or normalized.startswith(
            str(REPO_ROOT)
        ):
            paths.append(_repo_rel(normalized))
        return paths
    if isinstance(value, dict):
        for child in value.values():
            paths.extend(_extract_repo_string_paths(child))
    elif isinstance(value, list):
        for child in value:
            paths.extend(_extract_repo_string_paths(child))
    return _unique_sorted_tokens(paths)


def _source_kind_for_path(rel_path: str) -> str:
    normalized = rel_path.replace("\\", "/")
    if normalized.startswith("tests/"):
        return "test_fixture"
    if normalized.startswith("implementation/phase1/release/authoring/portfolio/"):
        return "release_authoring_portfolio"
    if normalized.startswith("implementation/phase1/release/signing/native_authoring_portfolio/"):
        return "release_authoring_signature"
    if normalized.startswith("implementation/phase1/release/midas_native_roundtrip/"):
        return "release_midas_roundtrip"
    if normalized.startswith("implementation/phase1/release/external_benchmark_kickoff/"):
        return "release_external_benchmark_run"
    if normalized.startswith("implementation/phase1/release/benchmark_expansion/"):
        return "release_benchmark_expansion"
    if normalized.startswith("implementation/phase1/release/committee_review/"):
        return "release_committee_review"
    if normalized.startswith("implementation/phase1/release/pbd_review/"):
        return "release_pbd_review"
    if normalized.startswith("implementation/phase1/release/visualization/entries/"):
        return "release_registered_dataset_entry"
    if normalized == "implementation/phase1/open_data/korea/korean_source_catalog.json":
        return "open_data_korean_catalog"
    if normalized == "implementation/phase1/open_data/korea/korean_source_ingest_report.json":
        return "open_data_korean_ingest_report"
    if normalized == "implementation/phase1/open_data/korea/korean_public_structure_collection_report.json":
        return "open_data_korean_collection_report"
    if normalized == "implementation/phase1/open_data/benchmark_diversification_catalog.json":
        return "open_data_benchmark_catalog"
    if normalized == "implementation/phase1/open_data/global_authority/authority_source_catalog.json":
        return "open_data_authority_catalog"
    if normalized == "implementation/phase1/open_data/midas/midas_native_corpus_manifest.json":
        return "open_data_midas_corpus_manifest"
    if normalized.startswith("implementation/phase1/open_data/korea/curated/"):
        return "open_data_korean_curated"
    if normalized.startswith("implementation/phase1/open_data/global_authority/"):
        return "open_data_authority_bundle"
    if normalized.startswith("implementation/phase1/open_data/pbd_hinge/"):
        return "open_data_pbd_hinge"
    if normalized.startswith("implementation/phase1/open_data/wind/"):
        return "open_data_wind"
    if normalized.startswith("implementation/phase1/open_data/megastructure/"):
        return "open_data_megastructure"
    if normalized.startswith("implementation/phase1/open_data/irregular/"):
        return "open_data_irregular"
    return "repo_local_artifact"


def _inferred_linkage_tags(rel_path: str, source_kind: str) -> list[str]:
    normalized = rel_path.replace("\\", "/")
    name = Path(normalized).name.lower()
    tags = {"corpus"}
    if source_kind in {
        "release_authoring_portfolio",
        "release_authoring_signature",
        "release_committee_review",
        "release_pbd_review",
    }:
        tags.add("review")
    if source_kind in {
        "release_midas_roundtrip",
        "open_data_korean_curated",
        "open_data_midas_corpus_manifest",
    }:
        tags.add("roundtrip")
    if source_kind in {
        "release_external_benchmark_run",
        "release_benchmark_expansion",
        "release_registered_dataset_entry",
        "open_data_authority_bundle",
        "open_data_benchmark_catalog",
        "open_data_pbd_hinge",
        "open_data_wind",
        "open_data_megastructure",
        "open_data_irregular",
    }:
        tags.add("benchmark")
    if "loadcomb" in name or "roundtrip" in name or "diff_receipt" in name:
        tags.add("roundtrip")
    if "benchmark" in name or "compare_report" in name or "reference_metrics" in name or "waveform_metrics" in name:
        tags.add("benchmark")
    if "review" in name or "landing_manifest" in name or "landing_status" in name or "signature" in name:
        tags.add("review")
    return _unique_sorted_tokens(list(tags))


def _is_concrete_local_artifact(source_kind: str) -> bool:
    return source_kind not in {
        "open_data_korean_catalog",
        "open_data_korean_ingest_report",
        "open_data_korean_collection_report",
        "open_data_benchmark_catalog",
        "open_data_authority_catalog",
        "open_data_midas_corpus_manifest",
        "release_registered_dataset_entry",
        "test_fixture",
    }


def _collect_globbed_paths(patterns: list[str] | tuple[str, ...]) -> list[str]:
    paths: list[str] = []
    for pattern in patterns:
        for match in sorted(REPO_ROOT.glob(pattern)):
            if match.is_file():
                paths.append(_repo_rel(match))
    return _unique_sorted_tokens(paths)


def _merge_row(store: dict[str, dict[str, Any]], row: dict[str, Any]) -> None:
    key = str(row["path"])
    if key not in store:
        store[key] = row
        return
    existing = store[key]
    existing["linkage_tags"] = _unique_sorted_tokens(
        [*existing.get("linkage_tags", []), *row.get("linkage_tags", [])]
    )
    existing["notes"] = _unique_sorted_tokens([*existing.get("notes", []), *row.get("notes", [])])
    artifact_labels = [*existing.get("artifact_labels", []), *row.get("artifact_labels", [])]
    existing["artifact_labels"] = _unique_sorted_tokens(artifact_labels)
    existing["concrete_local_artifact"] = bool(
        existing.get("concrete_local_artifact", False) or row.get("concrete_local_artifact", False)
    )


def _build_path_row(
    *,
    family_id: str,
    family_label: str,
    owner_type: str,
    path_str: str,
    artifact_label: str,
    note: str,
    reference_id: str = "",
    reference_title: str = "",
    reference_category: str = "",
    linkage_tags: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    rel_path = _repo_rel(path_str)
    source_kind = _source_kind_for_path(rel_path)
    tags = _unique_sorted_tokens([*(linkage_tags or []), *_inferred_linkage_tags(rel_path, source_kind)])
    return {
        "family_id": family_id,
        "family_label": family_label,
        "owner_type": owner_type,
        "reference_id": reference_id,
        "reference_title": reference_title,
        "reference_category": reference_category,
        "path": rel_path,
        "exists": _repo_path(rel_path).exists(),
        "source_kind": source_kind,
        "concrete_local_artifact": _is_concrete_local_artifact(source_kind),
        "linkage_tags": tags,
        "artifact_labels": [artifact_label] if artifact_label else [],
        "notes": [note] if note else [],
    }


def _load_portfolio_payload(
    *,
    portfolio_payload: dict[str, Any] | None,
    portfolio_json_path: Path,
) -> dict[str, Any]:
    if portfolio_payload is not None:
        return portfolio_payload
    return _load_dict(portfolio_json_path)


def _load_family_corpus_payload(
    *,
    family_corpus_payload: dict[str, Any] | None,
    family_corpus_manifest_path: Path,
    portfolio_json_path: Path,
    release_root: Path,
    korean_source_catalog_path: Path,
    benchmark_diversification_catalog_path: Path,
    authority_source_catalog_path: Path,
    timestamp: str,
) -> dict[str, Any]:
    if family_corpus_payload is not None:
        return family_corpus_payload
    existing = _load_dict(family_corpus_manifest_path)
    if existing:
        return existing
    return build_native_authoring_family_corpus_manifest(
        portfolio_json_path=portfolio_json_path,
        release_root=release_root,
        korean_source_catalog_path=korean_source_catalog_path,
        benchmark_diversification_catalog_path=benchmark_diversification_catalog_path,
        authority_source_catalog_path=authority_source_catalog_path,
        out=family_corpus_manifest_path,
        generated_at=timestamp,
    )


def _portfolio_index(portfolio_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = portfolio_payload.get("family_rows") if isinstance(portfolio_payload.get("family_rows"), list) else []
    return {
        _first_text(row.get("family_id")): row
        for row in rows
        if isinstance(row, dict) and _first_text(row.get("family_id"))
    }


def _family_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("family_rows") if isinstance(payload.get("family_rows"), list) else []
    return [row for row in rows if isinstance(row, dict)]


def _korean_source_index(korean_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = korean_payload.get("source_records") if isinstance(korean_payload.get("source_records"), list) else []
    return {
        _first_text(row.get("source_id")): row
        for row in rows
        if isinstance(row, dict) and _first_text(row.get("source_id"))
    }


def _benchmark_index(benchmark_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = benchmark_payload.get("candidates") if isinstance(benchmark_payload.get("candidates"), list) else []
    return {
        _first_text(row.get("id")): row
        for row in rows
        if isinstance(row, dict) and _first_text(row.get("id"))
    }


def _megastructure_index(megastructure_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = megastructure_payload.get("candidates") if isinstance(megastructure_payload.get("candidates"), list) else []
    return {
        _first_text(row.get("id")): row
        for row in rows
        if isinstance(row, dict) and _first_text(row.get("id"))
    }


def _midas_cases_by_source(midas_payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    rows = midas_payload.get("cases") if isinstance(midas_payload.get("cases"), list) else []
    by_source: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        source_id = _first_text(row.get("source_id"))
        if source_id:
            by_source.setdefault(source_id, []).append(row)
    return by_source


def _collect_internal_release_rows(
    *,
    family_id: str,
    family_label: str,
    family_row: dict[str, Any],
    portfolio_row: dict[str, Any],
) -> list[dict[str, Any]]:
    by_path: dict[str, dict[str, Any]] = {}
    artifacts = portfolio_row.get("artifacts") if isinstance(portfolio_row.get("artifacts"), dict) else {}
    if artifacts:
        for artifact_key, artifact_path in artifacts.items():
            artifact_path_text = _first_text(artifact_path)
            if not artifact_path_text:
                continue
            _merge_row(
                by_path,
                _build_path_row(
                    family_id=family_id,
                    family_label=family_label,
                    owner_type="internal_release",
                    path_str=artifact_path_text,
                    artifact_label=str(artifact_key),
                    note=f"Native authoring release artifact `{artifact_key}`.",
                ),
            )
    else:
        for entry in family_row.get("internal_corpus_entries", []):
            if not isinstance(entry, dict):
                continue
            artifact_path_text = _first_text(entry.get("path"))
            if not artifact_path_text:
                continue
            _merge_row(
                by_path,
                _build_path_row(
                    family_id=family_id,
                    family_label=family_label,
                    owner_type="internal_release",
                    path_str=artifact_path_text,
                    artifact_label=_first_text(entry.get("entry_id")),
                    note=_first_text(entry.get("title"), "Native authoring internal corpus artifact."),
                ),
            )
    return list(by_path.values())


def _collect_korean_reference_paths(
    *,
    source_id: str,
    midas_rows: list[dict[str, Any]],
) -> list[str]:
    paths: list[str] = []
    for row in midas_rows:
        artifacts = row.get("artifacts")
        paths.extend(_extract_repo_string_paths(artifacts))
    paths.extend(
        _collect_globbed_paths(
            (
                f"implementation/phase1/release/midas_native_roundtrip/*{source_id}*.diff_receipt.json",
                f"implementation/phase1/release/midas_native_roundtrip/*{source_id}*.diff_receipt.md",
                f"implementation/phase1/release/midas_native_roundtrip/solver_ready_reconstruction/{source_id}.solver_ready_reconstruction.json",
                f"implementation/phase1/release/midas_native_roundtrip/solver_ready_reconstruction/{source_id}.solver_ready_reconstruction.md",
            )
        )
    )
    return _unique_sorted_tokens(paths)


def _collect_authority_paths(
    *,
    reference_id: str,
    spec: dict[str, Any],
    authority_payload: dict[str, Any],
) -> list[str]:
    paths: list[str] = []
    tracks = authority_payload.get("tracks") if isinstance(authority_payload.get("tracks"), dict) else {}
    track_name = _first_text(spec.get("track"))
    track_payload = tracks.get(track_name) if isinstance(tracks, dict) else {}
    if not isinstance(track_payload, dict):
        return []
    if _first_text(spec.get("resolver")) == "authority_track_bundle":
        case_rows = track_payload.get("cases") if isinstance(track_payload.get("cases"), list) else []
        for row in case_rows:
            if isinstance(row, dict):
                paths.extend(_extract_repo_string_paths(row))
    if _first_text(spec.get("resolver")) == "authority_model_bundle":
        model_ids = {str(item).strip() for item in spec.get("model_ids", []) if str(item).strip()}
        model_rows = track_payload.get("models") if isinstance(track_payload.get("models"), list) else []
        for row in model_rows:
            if not isinstance(row, dict) or _first_text(row.get("id")) not in model_ids:
                continue
            paths.extend(_extract_repo_string_paths(row))
            model_id = _first_text(row.get("id"))
            if model_id:
                paths.extend(
                    _collect_globbed_paths(
                        (
                            f"implementation/phase1/open_data/global_authority/run_artifacts/opensees/{model_id}_topology_report.json",
                            f"implementation/phase1/open_data/global_authority/run_artifacts/opensees/{model_id}_csr.npz",
                            f"implementation/phase1/open_data/global_authority/run_artifacts/opensees/{model_id}_edges.json",
                        )
                    )
                )
        if reference_id == "opensees_scbf_bundle":
            paths.extend(
                _collect_globbed_paths(
                    (
                        "implementation/phase1/release/benchmark_expansion/opensees_scbf_family_compare.json",
                        "implementation/phase1/scbf16b_shell_beam_mix_execution_manifest.md",
                    )
                )
            )
    return _unique_sorted_tokens(paths)


def _visualization_reference_paths(reference_id: str) -> list[str]:
    entry_path = DEFAULT_VISUALIZATION_ROOT / f"megastructure_{reference_id}.json"
    if not entry_path.exists():
        return []
    paths = [_repo_rel(entry_path)]
    payload = _load_dict(entry_path)
    entry = payload.get("entry") if isinstance(payload.get("entry"), dict) else {}
    paths.extend(_extract_repo_string_paths(entry.get("artifact_paths")))
    return _unique_sorted_tokens(paths)


def _collect_benchmark_reference_paths(
    *,
    reference_id: str,
    candidate_row: dict[str, Any],
    megastructure_row: dict[str, Any],
) -> list[str]:
    paths: list[str] = []
    paths.extend(_extract_repo_string_paths(candidate_row))
    paths.extend(_extract_repo_string_paths(megastructure_row))
    paths.extend(_visualization_reference_paths(reference_id))
    paths.extend(_collect_globbed_paths(BENCHMARK_REFERENCE_EXTRA_GLOBS.get(reference_id, ())))
    return _unique_sorted_tokens(paths)


def _status_for_rows(rows: list[dict[str, Any]], *, tag: str) -> str:
    tagged = [row for row in rows if tag in row.get("linkage_tags", [])]
    if not tagged:
        return "missing"
    if any(bool(row.get("concrete_local_artifact")) for row in tagged):
        return "concrete"
    return "linked"


def _availability_for_rows(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "missing"
    if any(bool(row.get("concrete_local_artifact")) for row in rows):
        return "concrete"
    return "registered_only"


def build_native_authoring_family_local_evidence_manifest(
    *,
    family_corpus_payload: dict[str, Any] | None = None,
    family_corpus_manifest_path: Path = DEFAULT_FAMILY_CORPUS_MANIFEST,
    portfolio_payload: dict[str, Any] | None = None,
    portfolio_json_path: Path = DEFAULT_PORTFOLIO_JSON,
    release_root: Path = DEFAULT_RELEASE_ROOT,
    korean_source_catalog_path: Path = DEFAULT_KOREAN_SOURCE_CATALOG,
    korean_source_ingest_report_path: Path = DEFAULT_KOREAN_SOURCE_INGEST_REPORT,
    korean_collection_report_path: Path = DEFAULT_KOREAN_COLLECTION_REPORT,
    benchmark_diversification_catalog_path: Path = DEFAULT_BENCHMARK_DIVERSIFICATION_CATALOG,
    benchmark_catalog_path: Path = DEFAULT_BENCHMARK_CATALOG,
    authority_source_catalog_path: Path = DEFAULT_AUTHORITY_SOURCE_CATALOG,
    midas_native_corpus_manifest_path: Path = DEFAULT_MIDAS_NATIVE_CORPUS_MANIFEST,
    out: Path = DEFAULT_OUT,
    generated_at: str | None = None,
) -> dict[str, Any]:
    timestamp = str(generated_at or "").strip() or _now_utc_iso()
    family_corpus = _load_family_corpus_payload(
        family_corpus_payload=family_corpus_payload,
        family_corpus_manifest_path=family_corpus_manifest_path,
        portfolio_json_path=portfolio_json_path,
        release_root=release_root,
        korean_source_catalog_path=korean_source_catalog_path,
        benchmark_diversification_catalog_path=benchmark_diversification_catalog_path,
        authority_source_catalog_path=authority_source_catalog_path,
        timestamp=timestamp,
    )
    portfolio = _load_portfolio_payload(
        portfolio_payload=portfolio_payload,
        portfolio_json_path=portfolio_json_path,
    )

    family_rows = _family_rows(family_corpus)
    portfolio_index = _portfolio_index(portfolio)
    korean_index = _korean_source_index(_load_dict(korean_source_catalog_path))
    benchmark_index = _benchmark_index(_load_dict(benchmark_diversification_catalog_path))
    megastructure_index = _megastructure_index(_load_dict(benchmark_catalog_path))
    authority_payload = _load_dict(authority_source_catalog_path)
    midas_rows_by_source = _midas_cases_by_source(_load_dict(midas_native_corpus_manifest_path))

    emitted_family_rows: list[dict[str, Any]] = []
    all_evidence_rows: list[dict[str, Any]] = []
    source_kind_counts: dict[str, int] = {}

    for family_row in family_rows:
        family_id = _first_text(family_row.get("family_id"))
        family_label = _first_text(family_row.get("family_label"), family_id.replace("_", " ").title())
        if not family_id:
            continue

        internal_rows = _collect_internal_release_rows(
            family_id=family_id,
            family_label=family_label,
            family_row=family_row,
            portfolio_row=portfolio_index.get(family_id, {}),
        )

        reference_rows: list[dict[str, Any]] = []
        for reference_entry in family_row.get("reference_source_entries", []):
            if not isinstance(reference_entry, dict):
                continue
            reference_id = _first_text(reference_entry.get("reference_id"))
            if not reference_id:
                continue
            spec = REFERENCE_SPECS.get(reference_id, {})
            resolver = _first_text(spec.get("resolver"))
            evidence_paths: list[str] = []
            repo_catalog_path = _first_text(reference_entry.get("repo_catalog_path"))
            if repo_catalog_path:
                evidence_paths.append(repo_catalog_path)
            if resolver == "korean_source_record":
                source_id = _first_text(spec.get("source_id"))
                source_row = korean_index.get(source_id, {})
                evidence_paths.extend(
                    _extract_repo_string_paths(
                        {
                            "local_path": source_row.get("local_path"),
                            "curated_local_ifc_reference": source_row.get("curated_local_ifc_reference"),
                        }
                    )
                )
                if source_id:
                    evidence_paths.extend(_collect_korean_reference_paths(source_id=source_id, midas_rows=midas_rows_by_source.get(source_id, [])))
                if korean_source_ingest_report_path.exists():
                    evidence_paths.append(str(korean_source_ingest_report_path))
                if korean_collection_report_path.exists():
                    evidence_paths.append(str(korean_collection_report_path))
            elif resolver in {"authority_track_bundle", "authority_model_bundle"}:
                evidence_paths.extend(
                    _collect_authority_paths(
                        reference_id=reference_id,
                        spec=spec,
                        authority_payload=authority_payload,
                    )
                )
            elif resolver == "benchmark_candidate":
                candidate_id = _first_text(spec.get("candidate_id"))
                evidence_paths.extend(
                    _collect_benchmark_reference_paths(
                        reference_id=reference_id,
                        candidate_row=benchmark_index.get(candidate_id, {}),
                        megastructure_row=megastructure_index.get(candidate_id, {}),
                    )
                )

            by_path: dict[str, dict[str, Any]] = {}
            for evidence_path in _unique_sorted_tokens(evidence_paths):
                _merge_row(
                    by_path,
                    _build_path_row(
                        family_id=family_id,
                        family_label=family_label,
                        owner_type="reference_artifact",
                        path_str=evidence_path,
                        artifact_label=reference_id,
                        note=f"Local evidence for `{reference_id}`.",
                        reference_id=reference_id,
                        reference_title=_first_text(reference_entry.get("title")),
                        reference_category=_first_text(reference_entry.get("reference_category")),
                    ),
                )

            reference_artifact_rows = list(by_path.values())
            reference_summary = {
                "reference_id": reference_id,
                "reference_title": _first_text(reference_entry.get("title")),
                "reference_category": _first_text(reference_entry.get("reference_category")),
                "availability_status": _availability_for_rows(reference_artifact_rows),
                "local_artifact_count": len(reference_artifact_rows),
                "concrete_local_artifact_count": sum(
                    1 for row in reference_artifact_rows if bool(row.get("concrete_local_artifact"))
                ),
                "source_kind_label": _compact_label([row["source_kind"] for row in reference_artifact_rows]),
                "roundtrip_linkage_status": _status_for_rows(reference_artifact_rows, tag="roundtrip"),
                "benchmark_linkage_status": _status_for_rows(reference_artifact_rows, tag="benchmark"),
                "review_linkage_status": _status_for_rows(reference_artifact_rows, tag="review"),
                "evidence_rows": reference_artifact_rows,
                "summary_line": (
                    f"{reference_id}: {_availability_for_rows(reference_artifact_rows).upper()} | "
                    f"local={len(reference_artifact_rows)} | "
                    f"roundtrip={_status_for_rows(reference_artifact_rows, tag='roundtrip')} | "
                    f"benchmark={_status_for_rows(reference_artifact_rows, tag='benchmark')} | "
                    f"review={_status_for_rows(reference_artifact_rows, tag='review')}"
                ),
            }
            reference_rows.append(reference_summary)

        test_rows: list[dict[str, Any]] = []
        for spec in FAMILY_TEST_FIXTURE_SPECS.get(family_id, ()):
            test_rows.append(
                _build_path_row(
                    family_id=family_id,
                    family_label=family_label,
                    owner_type="test_fixture",
                    path_str=str(spec["path"]),
                    artifact_label=Path(str(spec["path"])).name,
                    note=str(spec["note"]),
                    linkage_tags=list(spec.get("linkage_tags", ())),
                )
            )

        family_evidence_rows = [
            *internal_rows,
            *[row for ref in reference_rows for row in ref.get("evidence_rows", [])],
            *test_rows,
        ]
        external_reference_rows = [row for ref in reference_rows for row in ref.get("evidence_rows", [])]

        roundtrip_status = _status_for_rows([*internal_rows, *external_reference_rows, *test_rows], tag="roundtrip")
        benchmark_status = _status_for_rows([*external_reference_rows, *test_rows], tag="benchmark")
        review_status = _status_for_rows([*internal_rows, *external_reference_rows, *test_rows], tag="review")
        local_corpus_status = _availability_for_rows([*internal_rows, *external_reference_rows])
        reference_availability_values = [str(ref["availability_status"]) for ref in reference_rows]
        source_kind_label = _compact_label([row["source_kind"] for row in family_evidence_rows])

        emitted_family_row = {
            "family_id": family_id,
            "family_label": family_label,
            "portfolio_name": _first_text(family_row.get("portfolio_name"), family_corpus.get("summary", {}).get("portfolio_name")),
            "commercialization_lane": _first_text(family_row.get("commercialization_lane")),
            "commercialization_status": _first_text(family_row.get("commercialization_status")),
            "concrete_local_corpus_status": local_corpus_status,
            "roundtrip_linkage_status": roundtrip_status,
            "benchmark_linkage_status": benchmark_status,
            "review_linkage_status": review_status,
            "reference_availability_label": _compact_label(reference_availability_values),
            "source_kind_label": source_kind_label,
            "internal_release_artifact_count": len(internal_rows),
            "reference_local_evidence_count": len(external_reference_rows),
            "test_fixture_count": len(test_rows),
            "concrete_reference_local_evidence_count": sum(
                1 for row in external_reference_rows if bool(row.get("concrete_local_artifact"))
            ),
            "registered_only_reference_count": sum(
                1 for ref in reference_rows if str(ref.get("availability_status")) == "registered_only"
            ),
            "missing_reference_count": sum(1 for ref in reference_rows if str(ref.get("availability_status")) == "missing"),
            "internal_release_rows": internal_rows,
            "reference_evidence_rows": reference_rows,
            "test_fixture_rows": test_rows,
            "summary_line": (
                f"{family_label}: corpus={local_corpus_status.upper()} | "
                f"roundtrip={roundtrip_status} | benchmark={benchmark_status} | review={review_status} | "
                f"release={len(internal_rows)} | refs={len(external_reference_rows)} | tests={len(test_rows)}"
            ),
        }
        emitted_family_rows.append(emitted_family_row)

        for row in family_evidence_rows:
            source_kind_counts[row["source_kind"]] = source_kind_counts.get(row["source_kind"], 0) + 1
            all_evidence_rows.append(row)

    concrete_family_count = sum(
        1 for row in emitted_family_rows if str(row.get("concrete_local_corpus_status")) == "concrete"
    )
    roundtrip_concrete_family_count = sum(
        1 for row in emitted_family_rows if str(row.get("roundtrip_linkage_status")) == "concrete"
    )
    benchmark_linked_family_count = sum(
        1 for row in emitted_family_rows if str(row.get("benchmark_linkage_status")) in {"concrete", "linked"}
    )
    benchmark_concrete_family_count = sum(
        1 for row in emitted_family_rows if str(row.get("benchmark_linkage_status")) == "concrete"
    )
    review_concrete_family_count = sum(
        1 for row in emitted_family_rows if str(row.get("review_linkage_status")) == "concrete"
    )

    checks = {
        "all_families_have_concrete_local_corpus": bool(emitted_family_rows)
        and all(str(row.get("concrete_local_corpus_status")) == "concrete" for row in emitted_family_rows),
        "all_families_have_roundtrip_linkage": bool(emitted_family_rows)
        and all(str(row.get("roundtrip_linkage_status")) in {"concrete", "linked"} for row in emitted_family_rows),
        "all_families_have_benchmark_linkage": bool(emitted_family_rows)
        and all(str(row.get("benchmark_linkage_status")) in {"concrete", "linked"} for row in emitted_family_rows),
        "all_families_have_review_linkage": bool(emitted_family_rows)
        and all(str(row.get("review_linkage_status")) in {"concrete", "linked"} for row in emitted_family_rows),
        "all_families_have_test_fixture_rows": bool(emitted_family_rows)
        and all(int(row.get("test_fixture_count", 0)) > 0 for row in emitted_family_rows),
    }
    contract_pass = bool(emitted_family_rows) and all(checks.values())
    reason_code = "PASS" if contract_pass else ("CHECK" if emitted_family_rows else "ERR_INPUT")
    summary_line = (
        "Native authoring family local evidence manifest: "
        f"{reason_code} | families={len(emitted_family_rows)} | concrete={concrete_family_count} | "
        f"roundtrip_concrete={roundtrip_concrete_family_count} | "
        f"benchmark={benchmark_linked_family_count}/{benchmark_concrete_family_count} | "
        f"review_concrete={review_concrete_family_count} | "
        f"source_kinds={len(source_kind_counts)}"
    )

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-native-authoring-family-local-evidence-manifest",
        "generated_at": timestamp,
        "inputs": {
            "family_corpus_manifest_path": str(family_corpus_manifest_path),
            "portfolio_json_path": str(portfolio_json_path),
            "release_root": str(release_root),
            "korean_source_catalog_path": str(korean_source_catalog_path),
            "korean_source_ingest_report_path": str(korean_source_ingest_report_path),
            "benchmark_diversification_catalog_path": str(benchmark_diversification_catalog_path),
            "benchmark_catalog_path": str(benchmark_catalog_path),
            "authority_source_catalog_path": str(authority_source_catalog_path),
            "midas_native_corpus_manifest_path": str(midas_native_corpus_manifest_path),
        },
        "summary": {
            "family_count": len(emitted_family_rows),
            "concrete_local_corpus_family_count": concrete_family_count,
            "roundtrip_concrete_family_count": roundtrip_concrete_family_count,
            "benchmark_linked_family_count": benchmark_linked_family_count,
            "benchmark_concrete_family_count": benchmark_concrete_family_count,
            "review_concrete_family_count": review_concrete_family_count,
            "source_kind_count": len(source_kind_counts),
            "source_kind_label": _compact_label(list(source_kind_counts.keys()), max_items=8),
            "evidence_row_count": len(all_evidence_rows),
            "reference_registered_only_family_count": sum(
                1 for row in emitted_family_rows if int(row.get("registered_only_reference_count", 0)) > 0
            ),
        },
        "source_kind_counts": source_kind_counts,
        "family_rows": emitted_family_rows,
        "evidence_rows": all_evidence_rows,
        "checks": checks,
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
        "summary_line": summary_line,
        "artifacts": {
            "native_authoring_family_local_evidence_manifest_json": str(out),
        },
    }
    _write_json(out, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family-corpus-manifest", type=Path, default=DEFAULT_FAMILY_CORPUS_MANIFEST)
    parser.add_argument("--portfolio-json", type=Path, default=DEFAULT_PORTFOLIO_JSON)
    parser.add_argument("--release-root", type=Path, default=DEFAULT_RELEASE_ROOT)
    parser.add_argument("--korean-source-catalog", type=Path, default=DEFAULT_KOREAN_SOURCE_CATALOG)
    parser.add_argument("--korean-source-ingest-report", type=Path, default=DEFAULT_KOREAN_SOURCE_INGEST_REPORT)
    parser.add_argument("--korean-collection-report", type=Path, default=DEFAULT_KOREAN_COLLECTION_REPORT)
    parser.add_argument(
        "--benchmark-diversification-catalog",
        type=Path,
        default=DEFAULT_BENCHMARK_DIVERSIFICATION_CATALOG,
    )
    parser.add_argument("--benchmark-catalog", type=Path, default=DEFAULT_BENCHMARK_CATALOG)
    parser.add_argument("--authority-source-catalog", type=Path, default=DEFAULT_AUTHORITY_SOURCE_CATALOG)
    parser.add_argument("--midas-native-corpus-manifest", type=Path, default=DEFAULT_MIDAS_NATIVE_CORPUS_MANIFEST)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--generated-at", default="")
    args = parser.parse_args()

    payload = build_native_authoring_family_local_evidence_manifest(
        family_corpus_manifest_path=args.family_corpus_manifest,
        portfolio_json_path=args.portfolio_json,
        release_root=args.release_root,
        korean_source_catalog_path=args.korean_source_catalog,
        korean_source_ingest_report_path=args.korean_source_ingest_report,
        korean_collection_report_path=args.korean_collection_report,
        benchmark_diversification_catalog_path=args.benchmark_diversification_catalog,
        benchmark_catalog_path=args.benchmark_catalog,
        authority_source_catalog_path=args.authority_source_catalog,
        midas_native_corpus_manifest_path=args.midas_native_corpus_manifest,
        out=args.out,
        generated_at=args.generated_at or None,
    )
    print(payload["summary_line"])
    return 0 if payload["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
