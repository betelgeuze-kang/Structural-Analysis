from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_structure_viewer_performance_budget_manifest.py"
SPEC = importlib.util.spec_from_file_location("build_structure_viewer_performance_budget_manifest", SCRIPT_PATH)
assert SPEC is not None
build_structure_viewer_performance_budget_manifest = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_structure_viewer_performance_budget_manifest)


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _viewer_perf_fixture(tmp_path: Path) -> dict[str, Path]:
    return {
        "index_html": _write_text(
            tmp_path / "src" / "structure-viewer" / "index.html",
            "\n".join(
                [
                    "const INSTANCED_LINE_ELEMENT_THRESHOLD=400;",
                    "const INSTANCED_SURFACE_ELEMENT_THRESHOLD=120;",
                    "const SURFACE_LOD_MEDIUM_ELEMENT_THRESHOLD=480;",
                    "const SURFACE_LOD_COARSE_ELEMENT_THRESHOLD=1200;",
                    "const LARGE_MODEL_ELEMENT_THRESHOLD=100000;",
                    "const LARGE_MODEL_PICK_LINE_SCREEN_TOLERANCE_PX=10;",
                    "const LARGE_MODEL_PICK_ACCELERATION_THRESHOLD=900;",
                    "const LARGE_MODEL_PICK_SPATIAL_INDEX_TARGET_BUCKET_SIZE=24;",
                    "const LARGE_MODEL_PICK_SPATIAL_INDEX_MAX_OVERLAP_CELLS=96;",
                    "const LARGE_MODEL_PICK_SPATIAL_INDEX_FULL_BVH_THRESHOLD=4096;",
                    "const LARGE_MODEL_PICK_SPATIAL_INDEX_MESH_TRIANGLE_BVH_THRESHOLD=2048;",
                    "const LARGE_MODEL_PICK_SPATIAL_INDEX_SURFACE_FACET_BVH_THRESHOLD=1024;",
                    "function buildInstancedSurfaceElements(){",
                    "  createInstancedSurfaceGroupObjects(records,type);",
                    "}",
                    "const meshData={surfaceLodLabel:'medium',surfaceContourSubdivisions:6};",
                    "function refreshDeformedPickMeshTriangleBvh(){}",
                ]
            ),
        ),
        "render_mesh_builders": _write_text(
            tmp_path / "src" / "structure-viewer" / "viewer-render-mesh-builders.js",
            "\n".join(
                [
                    "function createInstancedSurfaceGroupObjects(records, type) {",
                    "  const defaultOpacity = type === 'slab' ? 0.25 : 0.45;",
                    "  mesh.userData = {_instancedSurfaceGroup: true, geometryKind: 'surface'};",
                    "  const data = {surfaceLodLabel, surfaceContourSubdivisions, _surfaceDirectFallback: isInstancedSurface};",
                    "}",
                ]
            ),
        ),
        "render_picking_geometry": _write_text(
            tmp_path / "src" / "structure-viewer" / "viewer-render-picking-geometry.js",
            "function buildSurfaceLodProfile(){}\nfunction computeSurfaceLodSubdivisions(){}\n",
        ),
        "large_model_picking": _write_text(
            tmp_path / "src" / "structure-viewer" / "viewer-large-model-picking.js",
            "\n".join(
                [
                    "function queryPickSpatialIndexCandidates(){",
                    "  queryPickMeshTriangleBvh(index.meshTriangleBvh, index.meshTriangleEntries, ray, push);",
                    "  queryPickSurfaceFacetBvh(index.surfaceFacetBvh, index.surfaceFacetEntries, ray, push);",
                    "  while (visitedCellCap) break;",
                    "}",
                ]
            ),
        ),
        "pick_broadphase": _write_text(
            tmp_path / "src" / "structure-viewer" / "viewer-pick-broadphase.js",
            "\n".join(
                [
                    "const accelerationThreshold = Math.max(1, Math.round(safeNumber(config.accelerationThreshold, 900)));",
                    "const lineScreenTolerancePx = Math.max(0, safeNumber(config.lineScreenTolerancePx, 10));",
                    "function shouldPreferInstancedSurfacePicking(){}",
                    "const pickAccelerationRecords = [];",
                    "if (child.userData?._surfaceDirectFallback) return false;",
                    "return candidates.length ? candidates : pickTargetMeshes;",
                    "candidates.slice(0, 1600);",
                ]
            ),
        ),
        "deformed_rendering": _write_text(
            tmp_path / "src" / "structure-viewer" / "viewer-deformed-rendering.js",
            "const deformedMeshTriangleBvh = true;\n",
        ),
        "smoke_spec": _write_text(
            tmp_path / "tests" / "frontend" / "structure-viewer-smoke.spec.ts",
            "\n".join(
                [
                    "waitForCanvasNonBlank(page)",
                    "assertCanvasWellFramed(page)",
                    "openMidas33OptimizedViewer(page, { width: 1440, height: 1000 })",
                    "openMidas33OptimizedViewer(page, { width: 390, height: 844 })",
                    "'project=midas33_release&drawing=midas33_optimized&variant=optimized'",
                ]
            ),
        ),
        "viewer_contract_script": _write_text(
            tmp_path / "scripts" / "verify_structure_viewer_contracts.py",
            "\n".join(
                [
                    "tests/test_structure_viewer_instancing_contract.py",
                    "tests/test_structure_viewer_render_mesh_builders_contract.py",
                    "tests/test_structure_viewer_large_model_picking_contract.py",
                    "tests/test_structure_viewer_pick_broadphase_contract.py",
                    "tests/test_build_structure_viewer_performance_budget_manifest.py",
                ]
            ),
        ),
        "browser_performance_probe": _write_text(
            tmp_path / "scripts" / "measure-structure-viewer-performance.mjs",
            "\n".join(
                [
                    "const schemaVersion = 'structure-viewer-browser-performance-probe.v1'",
                    "const probeMode = 'local_browser_probe'",
                    "const payload = {live_performance_claim: false, independent_product_claim: false}",
                    "async function run(){ await waitForCanvasNonBlank(page); await assertCanvasWellFramed(page); }",
                    "async function sampleRaf(){ requestAnimationFrame(() => sampleRaf()) }",
                ]
            ),
        ),
        "visual_regression_probe": _write_text(
            tmp_path / "scripts" / "measure-structure-viewer-visual-regression.mjs",
            "\n".join(
                [
                    "const schemaVersion = 'structure-viewer-visual-regression-baseline.v1'",
                    "const mode = 'local_canvas_signature_baseline'",
                    "const payload = {live_visual_claim: false, independent_product_claim: false}",
                    "const defaultCases = ['desktop_midas33_solid', 'desktop_midas33_contour']",
                    "const rowState = {expected_render_mode: 'solid'}",
                    "const blocker = 'render_mode_mismatch'",
                    "const workflowCases = ['desktop_midas33_plan_wireframe', 'desktop_midas33_review_member', 'desktop_midas33_compare_risk_overlay', 'desktop_midas33_evidence_ingest_csv']",
                    "const workflowState = {expected_workflow_state: 'evidence_ingest_csv'}",
                    "const workflowBlockers = ['view_preset_mismatch', 'comparison_filter_mismatch', 'evidence_ingest_missing']",
                    "const advancedCases = ['desktop_midas33_renderable_json_ingest', 'desktop_midas33_section_edit_apply', 'desktop_midas33_loadcomb_draft']",
                    "const advancedBlockers = ['renderable_payload_missing', 'section_edit_missing', 'loadcomb_draft_missing']",
                    "function compareSignatures(left, right){ return left === right }",
                    "const row = {viewport_screenshot_sha256: 'abc'}",
                ]
            ),
        ),
    }


def test_structure_viewer_performance_budget_manifest_passes_static_contract(tmp_path: Path) -> None:
    payload = build_structure_viewer_performance_budget_manifest.build_structure_viewer_performance_budget_manifest(
        **_viewer_perf_fixture(tmp_path)
    )

    assert payload["contract_pass"] is True
    assert payload["budget_mode"] == "static_contract"
    assert payload["live_performance_claim"] is False
    assert payload["budget_values"]["max_pick_candidate_meshes"] == 1600
    assert {row["status"] for row in payload["check_rows"]} == {"pass"}
    assert payload["blockers"] == []


def test_structure_viewer_performance_budget_manifest_blocks_missing_pick_cap(tmp_path: Path) -> None:
    fixture = _viewer_perf_fixture(tmp_path)
    fixture["pick_broadphase"].write_text(
        fixture["pick_broadphase"].read_text(encoding="utf-8").replace(".slice(0, 1600)", ".slice(0, 6400)"),
        encoding="utf-8",
    )

    payload = build_structure_viewer_performance_budget_manifest.build_structure_viewer_performance_budget_manifest(
        **fixture
    )

    assert payload["contract_pass"] is False
    assert "budget_blocked:pick_candidate_mesh_cap" in payload["blockers"]
    assert any("pick_broadphase_budget_contract:candidate_mesh_cap_present" == blocker for blocker in payload["blockers"])
