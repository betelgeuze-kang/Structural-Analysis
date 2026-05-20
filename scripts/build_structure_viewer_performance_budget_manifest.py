#!/usr/bin/env python3
"""Build static performance-budget evidence for the structure viewer."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any


SCHEMA_VERSION = "structure-viewer-performance-budget-manifest.v1"
DEFAULT_MANIFEST_OUT = Path("implementation/phase1/structure_viewer_performance_budget_manifest.json")
DEFAULT_INDEX_HTML = Path("src/structure-viewer/index.html")
DEFAULT_RENDER_MESH_BUILDERS = Path("src/structure-viewer/viewer-render-mesh-builders.js")
DEFAULT_RENDER_PICKING_GEOMETRY = Path("src/structure-viewer/viewer-render-picking-geometry.js")
DEFAULT_LARGE_MODEL_PICKING = Path("src/structure-viewer/viewer-large-model-picking.js")
DEFAULT_PICK_BROADPHASE = Path("src/structure-viewer/viewer-pick-broadphase.js")
DEFAULT_DEFORMED_RENDERING = Path("src/structure-viewer/viewer-deformed-rendering.js")
DEFAULT_SMOKE_SPEC = Path("tests/frontend/structure-viewer-smoke.spec.ts")
DEFAULT_VIEWER_CONTRACT_SCRIPT = Path("scripts/verify_structure_viewer_contracts.py")
DEFAULT_BROWSER_PERFORMANCE_PROBE = Path("scripts/measure-structure-viewer-performance.mjs")
DEFAULT_VISUAL_REGRESSION_PROBE = Path("scripts/measure-structure-viewer-visual-regression.mjs")


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def _sha256_path(path: Path) -> str:
    if not path.exists():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_row(path: Path, *, label: str) -> dict[str, Any]:
    return {
        "label": label,
        "path": str(path),
        "available": path.exists(),
        "bytes": path.stat().st_size if path.exists() else 0,
        "sha256": _sha256_path(path),
    }


def _has_all(text: str, tokens: tuple[str, ...]) -> bool:
    return all(token in text for token in tokens)


def _constant_int(text: str, name: str) -> int | None:
    match = re.search(rf"\bconst\s+{re.escape(name)}\s*=\s*([0-9]+)\s*;", text)
    return int(match.group(1)) if match else None


def _fallback_int(text: str, key: str) -> int | None:
    match = re.search(rf"{re.escape(key)}\s*,\s*([0-9]+)\)", text)
    return int(match.group(1)) if match else None


def _check_row(check_id: str, *, title: str, checks: dict[str, bool], evidence: list[str]) -> dict[str, Any]:
    blockers = [key for key, ok in checks.items() if not ok]
    return {
        "check_id": check_id,
        "title": title,
        "status": "pass" if not blockers else "blocked",
        "checks": checks,
        "evidence": evidence,
        "blockers": blockers,
    }


def _budget_row(
    budget_id: str,
    *,
    title: str,
    actual: int | None,
    comparator: str,
    limit: int,
    unit: str,
) -> dict[str, Any]:
    if actual is None:
        pass_budget = False
    elif comparator == "eq":
        pass_budget = actual == limit
    elif comparator == "lte":
        pass_budget = actual <= limit
    elif comparator == "gte":
        pass_budget = actual >= limit
    else:
        raise ValueError(f"unsupported comparator: {comparator}")
    return {
        "budget_id": budget_id,
        "title": title,
        "actual": actual,
        "comparator": comparator,
        "limit": limit,
        "unit": unit,
        "status": "pass" if pass_budget else "blocked",
    }


def _extract_budget_values(index_text: str, broadphase_text: str) -> dict[str, int | None]:
    return {
        "instanced_line_element_threshold": _constant_int(index_text, "INSTANCED_LINE_ELEMENT_THRESHOLD"),
        "instanced_surface_element_threshold": _constant_int(index_text, "INSTANCED_SURFACE_ELEMENT_THRESHOLD"),
        "surface_lod_medium_element_threshold": _constant_int(index_text, "SURFACE_LOD_MEDIUM_ELEMENT_THRESHOLD"),
        "surface_lod_coarse_element_threshold": _constant_int(index_text, "SURFACE_LOD_COARSE_ELEMENT_THRESHOLD"),
        "large_model_element_threshold": _constant_int(index_text, "LARGE_MODEL_ELEMENT_THRESHOLD"),
        "large_model_pick_line_screen_tolerance_px": _constant_int(
            index_text,
            "LARGE_MODEL_PICK_LINE_SCREEN_TOLERANCE_PX",
        ),
        "large_model_pick_acceleration_threshold": _constant_int(
            index_text,
            "LARGE_MODEL_PICK_ACCELERATION_THRESHOLD",
        ),
        "large_model_pick_spatial_index_target_bucket_size": _constant_int(
            index_text,
            "LARGE_MODEL_PICK_SPATIAL_INDEX_TARGET_BUCKET_SIZE",
        ),
        "large_model_pick_spatial_index_max_overlap_cells": _constant_int(
            index_text,
            "LARGE_MODEL_PICK_SPATIAL_INDEX_MAX_OVERLAP_CELLS",
        ),
        "large_model_pick_spatial_index_full_bvh_threshold": _constant_int(
            index_text,
            "LARGE_MODEL_PICK_SPATIAL_INDEX_FULL_BVH_THRESHOLD",
        ),
        "large_model_pick_mesh_triangle_bvh_threshold": _constant_int(
            index_text,
            "LARGE_MODEL_PICK_SPATIAL_INDEX_MESH_TRIANGLE_BVH_THRESHOLD",
        ),
        "large_model_pick_surface_facet_bvh_threshold": _constant_int(
            index_text,
            "LARGE_MODEL_PICK_SPATIAL_INDEX_SURFACE_FACET_BVH_THRESHOLD",
        ),
        "broadphase_acceleration_fallback": _fallback_int(broadphase_text, "config.accelerationThreshold"),
        "broadphase_line_tolerance_fallback_px": _fallback_int(broadphase_text, "config.lineScreenTolerancePx"),
        "max_pick_candidate_meshes": 1600 if ".slice(0, 1600)" in broadphase_text else None,
    }


def _build_budget_rows(values: dict[str, int | None]) -> list[dict[str, Any]]:
    return [
        _budget_row(
            "surface_instancing_threshold",
            title="Wall/slab surfaces switch to instancing early enough for drawing-scale models",
            actual=values["instanced_surface_element_threshold"],
            comparator="lte",
            limit=120,
            unit="elements",
        ),
        _budget_row(
            "surface_lod_medium_threshold",
            title="Medium surface LOD engages before high-density surface batches dominate the frame",
            actual=values["surface_lod_medium_element_threshold"],
            comparator="lte",
            limit=480,
            unit="elements",
        ),
        _budget_row(
            "surface_lod_coarse_threshold",
            title="Coarse surface LOD engages for large surface batches",
            actual=values["surface_lod_coarse_element_threshold"],
            comparator="lte",
            limit=1200,
            unit="elements",
        ),
        _budget_row(
            "large_model_gate",
            title="Large-model acceleration gate is explicit and stable",
            actual=values["large_model_element_threshold"],
            comparator="eq",
            limit=100000,
            unit="elements",
        ),
        _budget_row(
            "pick_acceleration_threshold",
            title="Picking broadphase acceleration starts before linear mesh scans dominate interaction",
            actual=values["large_model_pick_acceleration_threshold"],
            comparator="lte",
            limit=900,
            unit="records",
        ),
        _budget_row(
            "pick_candidate_mesh_cap",
            title="Ray pick candidates are capped after near-ray filtering",
            actual=values["max_pick_candidate_meshes"],
            comparator="lte",
            limit=1600,
            unit="meshes",
        ),
        _budget_row(
            "line_screen_tolerance",
            title="Line hit-test screen tolerance remains bounded",
            actual=values["large_model_pick_line_screen_tolerance_px"],
            comparator="eq",
            limit=10,
            unit="px",
        ),
        _budget_row(
            "mesh_triangle_bvh_threshold",
            title="Mesh triangle BVH is required for high-density picking catalogs",
            actual=values["large_model_pick_mesh_triangle_bvh_threshold"],
            comparator="lte",
            limit=2048,
            unit="triangles",
        ),
        _budget_row(
            "surface_facet_bvh_threshold",
            title="Surface facet BVH is required for high-density surface picking",
            actual=values["large_model_pick_surface_facet_bvh_threshold"],
            comparator="lte",
            limit=1024,
            unit="facets",
        ),
    ]


def build_structure_viewer_performance_budget_manifest(
    *,
    index_html: Path = DEFAULT_INDEX_HTML,
    render_mesh_builders: Path = DEFAULT_RENDER_MESH_BUILDERS,
    render_picking_geometry: Path = DEFAULT_RENDER_PICKING_GEOMETRY,
    large_model_picking: Path = DEFAULT_LARGE_MODEL_PICKING,
    pick_broadphase: Path = DEFAULT_PICK_BROADPHASE,
    deformed_rendering: Path = DEFAULT_DEFORMED_RENDERING,
    smoke_spec: Path = DEFAULT_SMOKE_SPEC,
    viewer_contract_script: Path = DEFAULT_VIEWER_CONTRACT_SCRIPT,
    browser_performance_probe: Path = DEFAULT_BROWSER_PERFORMANCE_PROBE,
    visual_regression_probe: Path = DEFAULT_VISUAL_REGRESSION_PROBE,
) -> dict[str, Any]:
    index_text = _read_text(index_html)
    render_text = _read_text(render_mesh_builders)
    geometry_text = _read_text(render_picking_geometry)
    large_picking_text = _read_text(large_model_picking)
    broadphase_text = _read_text(pick_broadphase)
    deformed_text = _read_text(deformed_rendering)
    smoke_text = _read_text(smoke_spec)
    contract_text = _read_text(viewer_contract_script)
    probe_text = _read_text(browser_performance_probe)
    visual_probe_text = _read_text(visual_regression_probe)
    compact_index_text = "".join(index_text.split())

    sources = [
        _source_row(index_html, label="viewer_index"),
        _source_row(render_mesh_builders, label="render_mesh_builders"),
        _source_row(render_picking_geometry, label="render_picking_geometry"),
        _source_row(large_model_picking, label="large_model_picking"),
        _source_row(pick_broadphase, label="pick_broadphase"),
        _source_row(deformed_rendering, label="deformed_rendering"),
        _source_row(smoke_spec, label="frontend_smoke_spec"),
        _source_row(viewer_contract_script, label="viewer_contract_script"),
        _source_row(browser_performance_probe, label="browser_performance_probe"),
        _source_row(visual_regression_probe, label="visual_regression_probe"),
    ]
    source_missing = [row["label"] for row in sources if not row["available"]]

    budget_values = _extract_budget_values(index_text, broadphase_text)
    budget_rows = _build_budget_rows(budget_values)
    budget_blockers = [row["budget_id"] for row in budget_rows if row["status"] != "pass"]

    check_rows = [
        _check_row(
            "surface_instancing_contract",
            title="Wall/slab surface batching is backed by instanced render objects",
            checks={
                "builder_exports_surface_instancing": "function createInstancedSurfaceGroupObjects(" in render_text,
                "surface_groups_marked_instanced": "_instancedSurfaceGroup" in render_text,
                "surface_geometry_kind_tagged": "geometryKind: 'surface'" in render_text,
                "wall_slab_opacity_split_present": "type === 'slab'" in render_text,
                "viewer_invokes_surface_instancing": "function buildInstancedSurfaceElements(" in index_text
                and "createInstancedSurfaceGroupObjects(records,type)" in compact_index_text,
            },
            evidence=[str(render_mesh_builders), str(index_html)],
        ),
        _check_row(
            "surface_lod_contract",
            title="Surface LOD records the active profile and keeps direct fallback pick geometry",
            checks={
                "lod_profile_builder_present": "function buildSurfaceLodProfile(" in geometry_text,
                "lod_subdivision_builder_present": "function computeSurfaceLodSubdivisions(" in geometry_text,
                "lod_label_recorded": "surfaceLodLabel" in render_text and "surfaceLodLabel" in index_text,
                "lod_subdivisions_recorded": "surfaceContourSubdivisions" in render_text
                and "surfaceContourSubdivisions" in index_text,
                "direct_surface_fallback_marked": "_surfaceDirectFallback: isInstancedSurface" in render_text,
                "instanced_surface_pick_preference_present": "function shouldPreferInstancedSurfacePicking("
                in broadphase_text,
            },
            evidence=[str(render_picking_geometry), str(render_mesh_builders), str(index_html), str(pick_broadphase)],
        ),
        _check_row(
            "large_model_pick_bvh_contract",
            title="Large model hit-testing uses spatial index, mesh BVH, surface BVH, and deformed mesh refresh",
            checks={
                "large_model_picker_uses_spatial_index": "function queryPickSpatialIndexCandidates("
                in large_picking_text,
                "mesh_triangle_bvh_query_present": "queryPickMeshTriangleBvh" in large_picking_text
                and "meshTriangleBvh" in large_picking_text,
                "surface_facet_bvh_query_present": "queryPickSurfaceFacetBvh" in large_picking_text
                and "surfaceFacetBvh" in large_picking_text,
                "cell_visit_cap_present": "visitedCellCap" in large_picking_text,
                "deformed_bvh_refresh_present": "function refreshDeformedPickMeshTriangleBvh()" in index_text
                and "deformedMeshTriangleBvh" in deformed_text,
            },
            evidence=[str(large_model_picking), str(render_picking_geometry), str(deformed_rendering), str(index_html)],
        ),
        _check_row(
            "pick_broadphase_budget_contract",
            title="Fallback mesh picking is bounded by thresholded acceleration records and candidate caps",
            checks={
                "acceleration_threshold_declared": "accelerationThreshold" in broadphase_text,
                "line_screen_tolerance_declared": "lineScreenTolerancePx" in broadphase_text,
                "acceleration_records_built": "pickAccelerationRecords" in broadphase_text,
                "candidate_mesh_cap_present": ".slice(0, 1600)" in broadphase_text,
                "fallback_cache_present": "return candidates.length ? candidates : pickTargetMeshes" in broadphase_text,
                "surface_fallback_filtered": "child.userData?._surfaceDirectFallback" in broadphase_text,
            },
            evidence=[str(pick_broadphase)],
        ),
        _check_row(
            "browser_smoke_visual_contract",
            title="Browser smoke tests keep desktop/mobile canvas rendering and workflow coverage visible",
            checks={
                "playwright_spec_present": smoke_spec.exists(),
                "canvas_nonblank_probe_present": "waitForCanvasNonBlank" in smoke_text,
                "canvas_frame_probe_present": "assertCanvasWellFramed" in smoke_text,
                "desktop_viewport_present": "{ width: 1440, height: 1000 }" in smoke_text,
                "mobile_viewport_present": "{ width: 390, height: 844 }" in smoke_text,
                "midas33_project_route_present": "project=midas33_release&drawing=midas33_optimized" in smoke_text,
            },
            evidence=[str(smoke_spec)],
        ),
        _check_row(
            "contract_suite_regression_surface",
            title="Structure viewer contract suite includes the large-model and pick broadphase tests",
            checks={
                "instancing_contract_listed": "tests/test_structure_viewer_instancing_contract.py" in contract_text,
                "render_mesh_contract_listed": "tests/test_structure_viewer_render_mesh_builders_contract.py"
                in contract_text,
                "large_model_picking_contract_listed": "tests/test_structure_viewer_large_model_picking_contract.py"
                in contract_text,
                "pick_broadphase_contract_listed": "tests/test_structure_viewer_pick_broadphase_contract.py"
                in contract_text,
                "performance_budget_contract_listed": "tests/test_build_structure_viewer_performance_budget_manifest.py"
                in contract_text,
            },
            evidence=[str(viewer_contract_script)],
        ),
        _check_row(
            "browser_performance_probe_contract",
            title="Local browser performance probe is present and keeps the FPS claim boundary explicit",
            checks={
                "probe_script_present": browser_performance_probe.exists(),
                "probe_schema_declared": "structure-viewer-browser-performance-probe.v1" in probe_text,
                "local_probe_mode_declared": "local_browser_probe" in probe_text,
                "live_performance_claim_disabled": "live_performance_claim: false" in probe_text,
                "independent_product_claim_disabled": "independent_product_claim: false" in probe_text,
                "canvas_probe_reused": "waitForCanvasNonBlank" in probe_text and "assertCanvasWellFramed" in probe_text,
                "raf_sampling_present": "sampleRaf" in probe_text and "requestAnimationFrame" in probe_text,
            },
            evidence=[str(browser_performance_probe)],
        ),
        _check_row(
            "visual_regression_probe_contract",
            title="Local visual regression baseline probe is present and keeps the visual claim boundary explicit",
            checks={
                "probe_script_present": visual_regression_probe.exists(),
                "visual_schema_declared": "structure-viewer-visual-regression-baseline.v1" in visual_probe_text,
                "local_signature_mode_declared": "local_canvas_signature_baseline" in visual_probe_text,
                "live_visual_claim_disabled": "live_visual_claim: false" in visual_probe_text,
                "independent_product_claim_disabled": "independent_product_claim: false" in visual_probe_text,
                "signature_comparison_present": "compareSignatures" in visual_probe_text,
                "viewport_hash_recorded": "viewport_screenshot_sha256" in visual_probe_text,
                "mode_specific_cases_declared": "desktop_midas33_solid" in visual_probe_text
                and "desktop_midas33_contour" in visual_probe_text,
                "render_mode_marker_recorded": "expected_render_mode" in visual_probe_text
                and "render_mode_mismatch" in visual_probe_text,
                "workflow_state_cases_declared": "desktop_midas33_plan_wireframe" in visual_probe_text
                and "desktop_midas33_review_member" in visual_probe_text
                and "desktop_midas33_compare_risk_overlay" in visual_probe_text
                and "desktop_midas33_evidence_ingest_csv" in visual_probe_text,
                "workflow_state_markers_recorded": "expected_workflow_state" in visual_probe_text
                and "view_preset_mismatch" in visual_probe_text
                and "comparison_filter_mismatch" in visual_probe_text
                and "evidence_ingest_missing" in visual_probe_text,
                "advanced_workflow_cases_declared": "desktop_midas33_renderable_json_ingest" in visual_probe_text
                and "desktop_midas33_section_edit_apply" in visual_probe_text
                and "desktop_midas33_loadcomb_draft" in visual_probe_text,
                "advanced_workflow_markers_recorded": "renderable_payload_missing" in visual_probe_text
                and "section_edit_missing" in visual_probe_text
                and "loadcomb_draft_missing" in visual_probe_text,
            },
            evidence=[str(visual_regression_probe)],
        ),
    ]
    check_blockers = [
        f"{row['check_id']}:{blocker}"
        for row in check_rows
        for blocker in row["blockers"]
    ]
    blockers = [
        *(f"source_missing:{label}" for label in source_missing),
        *(f"budget_blocked:{budget_id}" for budget_id in budget_blockers),
        *check_blockers,
    ]
    contract_pass = not blockers
    pass_count = sum(1 for row in check_rows if row["status"] == "pass")
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_STRUCTURE_VIEWER_PERFORMANCE_BUDGET_PENDING",
        "summary_line": (
            f"Structure viewer performance budget: {'PASS' if contract_pass else 'BLOCKED'} | "
            f"checks={pass_count}/{len(check_rows)} | budgets={len(budget_rows) - len(budget_blockers)}/{len(budget_rows)} | "
            "mode=static_contract"
        ),
        "budget_mode": "static_contract",
        "live_performance_claim": False,
        "budget_values": budget_values,
        "budget_rows": budget_rows,
        "check_rows": check_rows,
        "source_rows": sources,
        "checks": {
            "all_sources_available": not source_missing,
            "all_static_contracts_pass": not check_blockers,
            "all_budget_rows_pass": not budget_blockers,
            "live_performance_claim": False,
        },
        "residual_live_work": [
            "Promote the local browser probe to repeatable customer-hardware FPS and interaction latency budgets.",
            "Capture real wall/slab large-payload traces for MIDAS33 and OPSTOOL-class drawings across the device matrix.",
            "Record browser/device matrix results for GPU, CPU fallback, and low-memory profiles.",
            "Expand visual baselines beyond core workflow states to customer browser/device matrix runs.",
        ],
        "blockers": blockers,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-out", type=Path, default=DEFAULT_MANIFEST_OUT)
    parser.add_argument("--index-html", type=Path, default=DEFAULT_INDEX_HTML)
    parser.add_argument("--render-mesh-builders", type=Path, default=DEFAULT_RENDER_MESH_BUILDERS)
    parser.add_argument("--render-picking-geometry", type=Path, default=DEFAULT_RENDER_PICKING_GEOMETRY)
    parser.add_argument("--large-model-picking", type=Path, default=DEFAULT_LARGE_MODEL_PICKING)
    parser.add_argument("--pick-broadphase", type=Path, default=DEFAULT_PICK_BROADPHASE)
    parser.add_argument("--deformed-rendering", type=Path, default=DEFAULT_DEFORMED_RENDERING)
    parser.add_argument("--smoke-spec", type=Path, default=DEFAULT_SMOKE_SPEC)
    parser.add_argument("--viewer-contract-script", type=Path, default=DEFAULT_VIEWER_CONTRACT_SCRIPT)
    parser.add_argument("--browser-performance-probe", type=Path, default=DEFAULT_BROWSER_PERFORMANCE_PROBE)
    parser.add_argument("--visual-regression-probe", type=Path, default=DEFAULT_VISUAL_REGRESSION_PROBE)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_structure_viewer_performance_budget_manifest(
        index_html=args.index_html,
        render_mesh_builders=args.render_mesh_builders,
        render_picking_geometry=args.render_picking_geometry,
        large_model_picking=args.large_model_picking,
        pick_broadphase=args.pick_broadphase,
        deformed_rendering=args.deformed_rendering,
        smoke_spec=args.smoke_spec,
        viewer_contract_script=args.viewer_contract_script,
        browser_performance_probe=args.browser_performance_probe,
        visual_regression_probe=args.visual_regression_probe,
    )
    args.manifest_out.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else payload["summary_line"])
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
