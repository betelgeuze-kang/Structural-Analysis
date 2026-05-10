from pathlib import Path


def test_index_html_uses_instanced_mesh_pipeline_for_large_line_models() -> None:
    text = Path("src/structure-viewer/index.html").read_text(encoding="utf-8")
    mesh_builder_text = Path("src/structure-viewer/viewer-render-mesh-builders.js").read_text(encoding="utf-8")

    assert "const INSTANCED_LINE_ELEMENT_THRESHOLD=" in text
    assert "const INSTANCED_SURFACE_ELEMENT_THRESHOLD=" in text
    assert "const LARGE_MODEL_ELEMENT_THRESHOLD=100000;" in text
    assert "const LARGE_MODEL_PICK_SPATIAL_INDEX_TARGET_BUCKET_SIZE=24;" in text
    assert "const LARGE_MODEL_PICK_SPATIAL_INDEX_DENSE_BUCKET_SIZE=72;" in text
    assert "const LARGE_MODEL_PICK_SPATIAL_INDEX_OVERFLOW_BVH_LEAF_SIZE=12;" in text
    assert "const LARGE_MODEL_PICK_SPATIAL_INDEX_FULL_BVH_THRESHOLD=4096;" in text
    assert "const LARGE_MODEL_PICK_SPATIAL_INDEX_MESH_TRIANGLE_BVH_THRESHOLD=2048;" in text
    assert "const LARGE_MODEL_PICK_SPATIAL_INDEX_SURFACE_FACET_BVH_THRESHOLD=1024;" in text
    assert "function buildInstancedLineElements(" in text
    assert "function buildInstancedSurfaceElements(" in text
    assert "from './viewer-render-mesh-builders.js';" in text
    assert "const renderMeshBuilderToolkit=createViewerRenderMeshBuilderToolkit(THREE,{colors:COLORS});" in text
    assert "function createInstancedSurfaceWireframe(" in mesh_builder_text
    assert "function createInstancedLineGroupObjects(" in mesh_builder_text
    assert "function createInstancedSurfaceGroupObjects(" in mesh_builder_text
    assert "new T.InstancedMesh(" in mesh_builder_text
    assert "mesh.setMatrixAt(" in text
    assert "mesh.setColorAt(" in text
    assert "registerPickAnalyticRecord(record);" in text
    assert "geometryKind: 'surface'" in mesh_builder_text
    assert "_surfaceDirectFallback: isInstancedSurface" in mesh_builder_text
    assert "mesh.isInstancedMesh&&Number.isInteger(hit.instanceId)" in text


def test_index_html_keeps_instanced_wireframe_and_selection_refresh_hooks() -> None:
    text = Path("src/structure-viewer/index.html").read_text(encoding="utf-8")
    mesh_builder_text = Path("src/structure-viewer/viewer-render-mesh-builders.js").read_text(encoding="utf-8")

    assert "function refreshInstancedVisuals()" in text
    assert "function createInstancedWireframe(" in mesh_builder_text
    assert "instancedElementRecordsByMemberId" in text
    assert "resolveDisplayColorHex(record.data,record.baseColorHex)" in text
    assert "let selectedElementKeys=new Set(),selectedElementRecords=new Map();" in text
    assert "function updateSelectionFromData(" in text
    assert "function clearSelection(" in text
    assert "function normalizeSelectionValues(values)" in text
    assert "getSelectedElementCount()" in text
    assert "Selection Set" in text
    assert "member_set" in text
    assert "event.ctrlKey||event.metaKey" in text or "e.ctrlKey||e.metaKey" in text
    assert 'id="clear-selection-button"' in text
    assert "window.clearSelection=clearSelection;" in text
    assert "window.addEventListener('keydown',event=>{" in text


def test_index_html_exposes_bounded_loadcomb_authoring_draft_contract() -> None:
    text = Path("src/structure-viewer/index.html").read_text(encoding="utf-8")

    assert "Loadcomb Draft" in text
    assert 'id="loadcomb-edit-base-select"' in text
    assert 'id="loadcomb-edit-name-input"' in text
    assert 'id="loadcomb-edit-scale-input"' in text
    assert "function createEmptyLoadcombEditState()" in text
    assert "function getLoadCombinationCatalog()" in text
    assert "function stageLoadcombEditPreview()" in text
    assert "function exportLoadcombEditPreview()" in text
    assert "working_loadcomb_override_patch" in text
    assert "--loadcomb-override-patch-json <loadcomb-override-patch.json>" in text
    assert "window.stageLoadcombEditPreview=stageLoadcombEditPreview;" in text
    assert "window.exportLoadcombEditPreview=exportLoadcombEditPreview;" in text


def test_index_html_adds_surface_lod_and_pick_target_optimization_for_large_models() -> None:
    text = Path("src/structure-viewer/index.html").read_text(encoding="utf-8")
    geometry_text = Path("src/structure-viewer/viewer-render-picking-geometry.js").read_text(encoding="utf-8")
    deformed_text = Path("src/structure-viewer/viewer-deformed-rendering.js").read_text(encoding="utf-8")
    picking_text = Path("src/structure-viewer/viewer-large-model-picking.js").read_text(encoding="utf-8")
    compact_deformed_text = "".join(deformed_text.split())
    compact_geometry_text = "".join(geometry_text.split())
    compact_picking_text = "".join(picking_text.split())

    assert "let surfaceRenderLodProfile=null,pickTargetMeshes=[],pickAccelerationRecords=[],pickAnalyticRecords=[],pickAnalyticSpatialIndex=null,largeModelBuildProfile=null;" in text
    assert "const SURFACE_LOD_MEDIUM_ELEMENT_THRESHOLD=" in text
    assert "const SURFACE_LOD_COARSE_ELEMENT_THRESHOLD=" in text
    assert "from './viewer-render-picking-geometry.js';" in text
    assert "from './viewer-large-model-picking.js';" in text
    assert "const renderPickingGeometryToolkit=createViewerRenderPickingGeometryToolkit(THREE,{" in text
    assert "const largeModelPickingToolkit=createViewerLargeModelPickingToolkit(THREE,{" in text
    assert "export function createViewerRenderPickingGeometryToolkit(" in geometry_text
    assert "function buildSurfaceLodProfile(" in geometry_text
    assert "function computeSurfaceLodSubdivisions(" in geometry_text
    assert "function buildLodSurfaceContourGeometry(" in geometry_text
    assert "function buildSurfaceLodProfile(" not in text
    assert "surfaceRenderLodProfile=buildSurfaceLodProfile(surfaceElements.length,instancableSurfaceElements.length);" in text
    assert "surfaceLodLabel:surfaceRenderLodProfile?.label||'full'" in text
    assert "surfaceContourSubdivisions:computeSurfaceLodSubdivisions(verts,surfaceRenderLodProfile,{isInstancedSurface})" in text
    assert "function shouldPreferInstancedSurfacePicking(" in text
    assert "function rebuildPickTargetMeshes(" in text
    assert "function getPickableMeshes(" in text
    assert "function buildPickSpatialIndex(" in text
    assert "function buildPickBoundsBvh(" in geometry_text
    assert "function buildPickSpatialIndexOverflowBvh(" in geometry_text
    assert "async function buildPickMeshTriangleEntries(" in text
    assert "function buildPickMeshTriangleBvh(" in geometry_text
    assert "function buildLocalGeometryTriangleEntries(" in geometry_text
    assert "async function buildPickMeshLocalTriangleCatalogs(" in text
    assert "from './viewer-deformed-rendering.js';" in text
    assert "function resolvePickRecordWorldMatrix(" in geometry_text
    assert "function createLocalRayFromWorldRay(" in geometry_text
    assert "function intersectPickTriangleBvhClosest(" in geometry_text
    assert "function intersectLargeModelMeshLocalCatalog(" in geometry_text
    assert "function appendPickMeshTrianglesFromGeometry(" in geometry_text
    assert "mesh?.isInstancedMesh&&Number.isInteger(record?.instanceId)" in compact_geometry_text
    assert "mesh.getMatrixAt(record.instanceId,instanceMatrix);" in compact_geometry_text
    assert "function buildPickSurfaceFacetEntries(" in geometry_text
    assert "function buildPickSurfaceFacetBvh(" in geometry_text
    assert "function queryPickTriangleEntriesBvh(" in geometry_text
    assert "function queryPickMeshTriangleBvh(" in geometry_text
    assert "function refreshDeformedPickMeshTriangleBvh()" in text
    assert "function shouldIncludePickSpatialIndexOverflowRecord(" in geometry_text
    assert "function estimatePickRecordEntryDistance(" in geometry_text
    assert "function queryPickSpatialIndexOverflowBvh(" in geometry_text
    assert "function queryPickSurfaceFacetBvh(" in geometry_text
    assert "function queryPickSpatialIndexCandidates(" in picking_text
    assert "function intersectRayBoxDistances(" in geometry_text
    assert "function getPickSpatialIndexCellCoords(" in geometry_text
    assert "function pickLargeModelRecord(" in picking_text
    assert "function intersectLargeModelLineRecord(" in picking_text
    assert "function intersectLargeModelSurfaceRecord(" in picking_text
    assert "pickTargetMeshes=[...modelGroup.children].filter(child=>" in text
    assert "child.userData?._surfaceDirectFallback" in text
    assert "denseBucketRecordIndices:[]" in text
    assert "fullRecordIndices:[]" in text
    assert "nonSurfaceRecordIndices:[]" in text
    assert "meshTriangleEntries:[]" in text
    assert "deformedMeshTriangleEntries:[]" in text
    assert "meshLocalTriangleCatalogs:[]" in text
    assert "deformedMeshLocalTriangleCatalogs:[]" in text
    assert "surfaceFacetEntries:[]" in text
    assert "denseBucketBvh:null," in text
    assert "fullRecordBvh:null," in text
    assert "nonSurfaceRecordBvh:null," in text
    assert "meshTriangleBvh:null," in text
    assert "deformedMeshTriangleBvh:null," in text
    assert "surfaceFacetBvh:null," in text
    assert "recordIndexByElementId:new Map()," in text
    assert "recordIndexByMemberId:new Map()," in text
    assert "bucket.length<LARGE_MODEL_PICK_SPATIAL_INDEX_DENSE_BUCKET_SIZE" in text
    assert "index.denseBucketRecordIndices=[...denseBucketRecordSet].sort((left,right)=>left-right);" in text
    assert "index.fullRecordIndices=items.map((_,recordIndex)=>recordIndex);" in text
    assert "index.nonSurfaceRecordIndices=items" in text
    assert "index.meshTriangleEntries=await buildPickMeshTriangleEntries(index.records,{forceChunking});" in text
    assert "index.meshLocalTriangleCatalogs=await buildPickMeshLocalTriangleCatalogs(index.records,{forceChunking});" in text
    assert "index.surfaceFacetEntries=buildPickSurfaceFacetEntries(index.records);" in text
    assert "index.recordIndexByElementId.set(elementId,recordIndex);" in text
    assert "index.recordIndexByMemberId.set(memberId,recordIndex);" in text
    assert "index.denseBucketBvh=buildPickSpatialIndexOverflowBvh(index.denseBucketRecordIndices,index.records);" in text
    assert "index.fullRecordBvh=buildPickSpatialIndexOverflowBvh(index.fullRecordIndices,index.records);" in text
    assert "index.nonSurfaceRecordBvh=buildPickSpatialIndexOverflowBvh(index.nonSurfaceRecordIndices,index.records);" in text
    assert "index.meshTriangleBvh=buildPickMeshTriangleBvh(index.meshTriangleEntries);" in text
    assert "index.surfaceFacetBvh=buildPickSurfaceFacetBvh(index.surfaceFacetEntries);" in text
    assert "constcandidateEntries=queryPickSpatialIndexCandidates(pickAnalyticSpatialIndex,ray);" in compact_picking_text
    assert "if(index.meshTriangleBvh){" in compact_picking_text
    assert "queryPickMeshTriangleBvh(index.meshTriangleBvh,index.meshTriangleEntries,ray,pushCandidateEntry);" in compact_picking_text
    assert "if(getShowDeformed()&&index.deformedMeshTriangleBvh){" in compact_picking_text
    assert "queryPickMeshTriangleBvh(index.deformedMeshTriangleBvh,index.deformedMeshTriangleEntries,ray,pushCandidateEntry" in compact_picking_text
    assert "if(index.surfaceFacetBvh){" in compact_picking_text
    assert "queryPickSurfaceFacetBvh(index.surfaceFacetBvh,index.surfaceFacetEntries,ray,pushCandidateEntry);" in compact_picking_text
    assert "if(index.nonSurfaceRecordBvh){" in compact_picking_text
    assert "queryPickSpatialIndexOverflowBvh(index.nonSurfaceRecordBvh,ray,pushCandidateEntry);" in compact_picking_text
    assert "if(index.fullRecordBvh&&!index.meshTriangleBvh&&!index.surfaceFacetBvh&&!index.nonSurfaceRecordBvh){" in compact_picking_text
    assert "queryPickSpatialIndexOverflowBvh(index.fullRecordBvh,ray,pushCandidateEntry);" in compact_picking_text
    assert "if(index.denseBucketBvh){" in compact_picking_text
    assert "candidateEntries.sort((left,right)=>left.entryDistance-right.entryDistance)" in compact_picking_text
    assert "const acceleratedHit=pickLargeModelRecord(raycaster.ray);" in text
    assert "Pick Mesh Triangles" in text
    assert "Pick Mesh Local" in text
    assert "Pick Deformed Triangles" in text
    assert "Pick Deformed Local" in text
    assert "Pick Surface Facets" in text
    assert "Pick Non-Surface BVH" in text
    assert " + mesh triangle BVH" in text
    assert " + mesh-local BVH" in text
    assert " + deformed-local BVH" in text
    assert " + surface facet BVH" in text
    assert "const meshes=getPickableMeshes(raycaster.ray);" in text
    assert "rebuildPickTargetMeshes();" in text
    assert "Pick Full BVH" in text
    assert " + full BVH" in text
    assert "dense-bucket BVH" in text
    assert "pickSpatialIndex.deformedMeshTriangleEntries=triangleEntries;" in compact_deformed_text
    assert "pickSpatialIndex.deformedMeshLocalTriangleCatalogs=localCatalogs;" in compact_deformed_text
    assert "pickSpatialIndex.deformedMeshTriangleBvh=acceleration.triangleBvh||null;" in compact_deformed_text
    assert "record.deformedPickMeshLocalCatalog=localCatalogByRecordIndex.get(recordIndex)||null;" in compact_deformed_text
    assert "largeModelBuildProfile.pickSpatialDeformedMeshTriangleCount=triangleEntries.length;" in compact_deformed_text
    assert "largeModelBuildProfile.pickSpatialDeformedMeshTriangleBvhEnabled=Boolean(pickSpatialIndex.deformedMeshTriangleBvh);" in compact_deformed_text
    assert "largeModelBuildProfile.pickSpatialDeformedMeshLocalCatalogCount=localCatalogs.length;" in compact_deformed_text


def test_index_html_uses_anisotropic_pick_spatial_index_cell_sizes_end_to_end() -> None:
    text = Path("src/structure-viewer/index.html").read_text(encoding="utf-8")
    geometry_text = Path("src/structure-viewer/viewer-render-picking-geometry.js").read_text(encoding="utf-8")
    deformed_text = Path("src/structure-viewer/viewer-deformed-rendering.js").read_text(encoding="utf-8")
    picking_text = Path("src/structure-viewer/viewer-large-model-picking.js").read_text(encoding="utf-8")
    compact_geometry_text = "".join(geometry_text.split())
    compact_deformed_text = "".join(deformed_text.split())
    compact_picking_text = "".join(picking_text.split())

    assert "function getPickSpatialIndexAxisCellSize(index, axis) {" in geometry_text
    assert "safeNumber(index?.[`cellSize${axis.toUpperCase()}`],0)," in compact_geometry_text
    assert "safeNumber(index?.cellSize,0)," in compact_geometry_text
    assert "ix:clampPickSpatialIndexCoord((point.x-index.boundsMin.x)/getPickSpatialIndexAxisCellSize(index,'x'),index.dimX)," in compact_geometry_text
    assert "iy:clampPickSpatialIndexCoord((point.y-index.boundsMin.y)/getPickSpatialIndexAxisCellSize(index,'y'),index.dimY)," in compact_geometry_text
    assert "iz:clampPickSpatialIndexCoord((point.z-index.boundsMin.z)/getPickSpatialIndexAxisCellSize(index,'z'),index.dimZ)," in compact_geometry_text
    assert "const cellSizeX=axisExtentToCellSize(extent.x);" in text
    assert "const cellSizeY=axisExtentToCellSize(extent.y);" in text
    assert "const cellSizeZ=axisExtentToCellSize(extent.z);" in text
    assert "cellSize:Math.max(cellSizeX,cellSizeY,cellSizeZ)," in text
    assert "cellSizeX," in text
    assert "cellSizeY," in text
    assert "cellSizeZ," in text
    assert "constcellSizeX=getPickSpatialIndexAxisCellSize(index,'x');" in compact_picking_text
    assert "constcellSizeY=getPickSpatialIndexAxisCellSize(index,'y');" in compact_picking_text
    assert "constcellSizeZ=getPickSpatialIndexAxisCellSize(index,'z');" in compact_picking_text
    assert "?index.boundsMin.x+(ix+1)*cellSizeX" in compact_picking_text
    assert "?index.boundsMin.y+(iy+1)*cellSizeY" in compact_picking_text
    assert "?index.boundsMin.z+(iz+1)*cellSizeZ" in compact_picking_text
    assert "consttDeltaX=stepX!==0?Math.abs(cellSizeX/ray.direction.x):Infinity;" in compact_picking_text
    assert "consttDeltaY=stepY!==0?Math.abs(cellSizeY/ray.direction.y):Infinity;" in compact_picking_text
    assert "consttDeltaZ=stepZ!==0?Math.abs(cellSizeZ/ray.direction.z):Infinity;" in compact_picking_text
    assert "constpushCandidateEntry=(recordIndex,cellEntryDistance=0)=>{" in compact_picking_text
    assert "constentryDistance=Math.max(" in compact_picking_text
    assert "estimatePickRecordEntryDistance(ray,record,tolerance)" in compact_picking_text
    assert "pushBucketRecords(ix,iy,iz,traveled);" in compact_picking_text
    assert "overflowBvh:null," in text
    assert "denseBucketBvh:null," in text
    assert "fullRecordBvh:null," in text
    assert "nonSurfaceRecordBvh:null," in text
    assert "meshTriangleBvh:null," in text
    assert "deformedMeshTriangleBvh:null," in text
    assert "surfaceFacetBvh:null," in text
    assert "index.overflowBvh=buildPickSpatialIndexOverflowBvh(index.overflowIndices,index.records);" in text
    assert "queryPickMeshTriangleBvh(index.meshTriangleBvh,index.meshTriangleEntries,ray,pushCandidateEntry);" in compact_picking_text
    assert "queryPickMeshTriangleBvh(index.deformedMeshTriangleBvh,index.deformedMeshTriangleEntries,ray,pushCandidateEntry" in compact_picking_text
    assert "queryPickSurfaceFacetBvh(index.surfaceFacetBvh,index.surfaceFacetEntries,ray,pushCandidateEntry);" in compact_picking_text
    assert "queryPickSpatialIndexOverflowBvh(index.nonSurfaceRecordBvh,ray,pushCandidateEntry);" in compact_picking_text
    assert "queryPickSpatialIndexOverflowBvh(index.fullRecordBvh,ray,pushCandidateEntry);" in compact_picking_text
    assert "queryPickSpatialIndexOverflowBvh(index.overflowBvh,ray,pushCandidateEntry);" in compact_picking_text
    assert "queryPickSpatialIndexOverflowBvh(index.denseBucketBvh,ray,pushCandidateEntry);" in compact_picking_text
    assert "if(bestHit&&candidate.entryDistance>bestHit.distance)break;" in compact_picking_text
    assert "record.pickMeshLocalCatalog=catalog;" in text
    assert "record.deformedPickMeshLocalCatalog=localCatalogByRecordIndex.get(recordIndex)||null;" in compact_deformed_text
    assert "largeModelBuildProfile.pickSpatialMeshLocalCatalogCount=pickAnalyticSpatialIndex.meshLocalTriangleCatalogs.length;" in text
    assert "largeModelBuildProfile.pickSpatialDeformedMeshLocalCatalogCount=localCatalogs.length;" in compact_deformed_text


def test_index_html_chunk_normalizes_large_payloads_off_main_slice() -> None:
    text = Path("src/structure-viewer/index.html").read_text(encoding="utf-8")
    normalizer_text = Path("src/structure-viewer/viewer-model-normalizer.js").read_text(encoding="utf-8")
    direct_normalizer_text = Path("src/structure-viewer/viewer-direct-model-normalizer.js").read_text(encoding="utf-8")
    compact_text = "".join(text.split())

    assert "const NORMALIZATION_CHUNK_SIZE=" in text
    assert "async function yieldToMainThread(" in text
    assert "async function processInChunks(" in text
    assert "const mapRows = async" in direct_normalizer_text
    assert "requestIdleCallback" in text
    assert "requestAnimationFrame" in text
    assert "export async function sanitizeModelPayloadAsync(" in direct_normalizer_text
    assert "returnsanitizeModelPayloadAsync(payload,sourceMeta,{processInChunks,chunkSize:NORMALIZATION_CHUNK_SIZE});" in compact_text
    assert ":buildModelFromInteractivePayload(payload,sourceMeta);" in compact_text
    assert "constinteractiveModelAsync=awaitbuildModelFromInteractivePayloadAsync(payload,sourceMeta,{" in compact_text
    assert "viewer-model-normalizer.js" in text
    assert "viewer-direct-model-normalizer.js" in text
    assert "const VIEWER_OPTIMIZATION_WORKER_MODULE_URLS = {" in text
    assert "export async function buildModelFromInteractivePayloadAsync(" in normalizer_text
    assert "function createViewerOptimizationWorkerSource(" in text
    assert "function runViewerOptimizationWorker(" in text
    assert "async function sanitizeModelPayloadWithWorker(" in text
    assert "async function buildModelFromInteractivePayloadWithWorker(" in text
    assert "import {buildModelFromInteractivePayload} from ${JSON.stringify(modelNormalizerModuleUrl)};" in text
    assert "import {sanitizeModelPayload} from ${JSON.stringify(directModelNormalizerModuleUrl)};" in text
    assert "new Worker(url,{name:'structure-viewer-optimizer',type:'module'});" in text
    assert "viewerOptimizationWorkerMain" not in text
    assert "const safeNumber=(value,fallback=0)=>" not in text
    assert "const buildDirectModelMeta=(rootPayload" not in text
    assert "Normalizing payload in worker..." in text
    assert "processInChunks," in text
    assert "chunkSize:NORMALIZATION_CHUNK_SIZE" in text
    assert "forceChunking: totalSegments > chunkSize" in normalizer_text
    assert "await chunker(baselineSegments" in normalizer_text
    assert "await chunker(afterSegments" in normalizer_text
    assert "await yieldToMainThread({message:'Building render geometry...',ensurePaint:true});" in text
    assert "await normalizeLoadedPayload(" in text
    assert "await buildModel(initial.data,initial.sourceMeta);" in text


def test_index_html_streams_large_model_geometry_builds() -> None:
    text = Path("src/structure-viewer/index.html").read_text(encoding="utf-8")

    assert "const LARGE_MODEL_BUILD_CHUNK_SIZE=320;" in text
    assert "async function buildDirectRenderableElements(" in text
    assert "async function buildModel(data,sourceMeta=null){" in text
    assert "progressLabel:'Preparing render batches'" in text
    assert "progressLabel:'Building instanced line geometry'" in text
    assert "progressLabel:'Building instanced surface geometry'" in text
    assert "progressLabel:'Building direct render geometry'" in text
    assert "progressLabel:'Building pick spatial index'" in text
    assert "progressLabel:'Populating pick spatial index'" in text
    assert "pickAnalyticSpatialIndex=await buildPickSpatialIndex(" in text
    assert "largeModelBuildProfile.pickingMode='spatial-index';" in text
    assert "largeModelBuildProfile.pickRecordCount=pickAnalyticRecords.length;" in text


def test_index_html_supports_midas33_preset_and_nested_model_payloads() -> None:
    text = Path("src/structure-viewer/index.html").read_text(encoding="utf-8")
    loader_text = Path("src/structure-viewer/viewer-data-loader.js").read_text(encoding="utf-8")
    normalizer_text = Path("src/structure-viewer/viewer-model-normalizer.js").read_text(encoding="utf-8")
    direct_normalizer_text = Path("src/structure-viewer/viewer-direct-model-normalizer.js").read_text(encoding="utf-8")

    assert "viewer-data-loader.js" in text
    assert "buildArtifactCandidates" in text
    assert "loadPresetSidecarIfNeeded" in text
    assert "readEmbeddedPayload" in text
    assert "getPresetSidecarPath" in loader_text
    assert "normalizePresetToken" in loader_text
    assert "export async function loadPresetSidecarIfNeeded" in loader_text
    assert "ARTIFACT_PRESET_CANDIDATES" in loader_text
    assert "midas_generator_33.json" in loader_text
    assert "midas_generator_33.pr_recheck.json" in loader_text
    assert "midas_generator_33.optimized.roundtrip.json" in loader_text
    assert "PRESET_SIDECAR_FILES" in loader_text
    assert "./index.midas33.data.js" in loader_text
    assert "./index.real_drawing_private.data.js" in loader_text
    assert "real_drawing_private_3d: './index.real_drawing_private.data.js'" in loader_text
    assert "./index.html?preset=real_drawing_private_3d" in text
    assert "function updateSuiteRouteTabs()" in text
    assert "from './viewer-model-normalizer.js';" in text
    assert "from './viewer-direct-model-normalizer.js';" in text
    assert "export function extractModelPayload(" in normalizer_text
    assert "Array.isArray(payload.model.nodes)" in normalizer_text
    assert "export function buildDirectModelMeta(" in direct_normalizer_text
    assert "load_case_inventory" in direct_normalizer_text
    assert "geometry_bridge_review_count" in direct_normalizer_text


def test_index_html_surfaces_drawing_review_metadata() -> None:
    text = Path("src/structure-viewer/index.html").read_text(encoding="utf-8")

    assert "section_family_summary" in text
    assert "group_summary" in text
    assert "review_row_summary" in text
    assert "Section Families" in text
    assert "Review Rows" in text
    assert "focusFirstElementByPredicate(" in text
    assert "Section Family" in text
    assert "Review Row" in text
    assert "review_summary_label" in text


def test_index_html_adds_isolate_controls_and_svg_review_links() -> None:
    text = Path("src/structure-viewer/index.html").read_text(encoding="utf-8")

    assert 'id="clear-isolate-button"' in text
    assert "let activeIsolation={kind:'',value:'',label:''};" in text
    assert "function setActiveIsolation(" in text
    assert "function clearIsolation()" in text
    assert "isolateKind:'section_family'" in text
    assert "isolateKind:'group'" in text
    assert "isolateKind:'review_row'" in text
    assert "buildSvgReviewLinks(" in text
    assert "Drawings" in text
    assert "elevation_xz" in text
    assert "isometric" in text


def test_index_html_adds_story_clip_search_and_png_export() -> None:
    text = Path("src/structure-viewer/index.html").read_text(encoding="utf-8")

    assert 'id="member-search-input"' in text
    assert 'id="search-results"' in text
    assert "function matchesSearchQuery(" in text
    assert "function resolveSearchMatches(" in text
    assert "function runSearchIsolate()" in text
    assert "setActiveIsolation('member'" in text
    assert 'id="story-clip-select"' in text
    assert 'id="story-clip-padding"' in text
    assert "function readStoryClipStateFromQuery()" in text
    assert "function deriveStoryClipBands(" in text
    assert "function applyStoryClipPlanes()" in text
    assert "new THREE.Plane(new THREE.Vector3(0,1,0)" in text
    assert "renderer.localClippingEnabled=true;" in text
    assert 'id="export-png-button"' in text
    assert "function exportViewportPng()" in text
    assert "preserveDrawingBuffer:true" in text


def test_index_html_adds_non_destructive_section_edit_preview_export() -> None:
    text = Path("src/structure-viewer/index.html").read_text(encoding="utf-8")
    direct_normalizer_text = Path("src/structure-viewer/viewer-direct-model-normalizer.js").read_text(encoding="utf-8")

    assert 'id="edit-preview-section-input"' in text
    assert 'id="edit-preview-note-input"' in text
    assert 'id="edit-preview-stage-button"' in text
    assert 'id="edit-preview-apply-button"' in text
    assert 'id="edit-preview-export-button"' in text
    assert 'id="edit-preview-revert-button"' in text
    assert 'id="edit-preview-list"' in text
    assert "function resolveSectionEditPreviewSelectionScope()" in text
    assert "shared member_set" in text
    assert "function buildSectionEditPreviewEntries(" in text
    assert "function stageSectionEditPreview()" in text
    assert "function applySectionEditPreview()" in text
    assert "function exportSectionEditPreview()" in text
    assert "function revertAppliedSectionOverrides()" in text
    assert "patch_mode:'working_section_override_patch'" in text
    assert "mutates_model:false" in text
    assert "mutates_source_artifact:false" in text
    assert "source_artifact_sha256:normalizeSelectionValue(modelData?.meta?.source_artifact_sha256)" in text
    assert "source_artifact_format:normalizeSelectionValue(modelData?.meta?.source_artifact_format)" in text
    assert "target_section_resolution_mode:targetSectionCatalogMatch.resolution_mode||'unresolved_free_text'" in text
    assert "current_section_summary:entry.current_section_summary||entry.source_section_summary||'--'" in text
    assert "current_section_ids:entry.current_section_ids||[]" in text
    assert "element_section_pairs:entry.element_section_pairs||[]" in text
    assert "applied_at:entry.applied_at||sectionEditApplyState.appliedAt||''" in text
    assert "function resolveSectionEditTargetSectionCatalogMatch(" in text
    assert "export function buildSectionCatalogSummary(" in direct_normalizer_text
    assert "Applied Section" in text
    assert "Edit Apply" in text
    assert "No draft staged. Preview entries will summarize current and target sections for the active member scope." in text


def test_index_html_uses_vertex_color_contour_interpolation() -> None:
    text = Path("src/structure-viewer/index.html").read_text(encoding="utf-8")
    geometry_text = Path("src/structure-viewer/viewer-render-picking-geometry.js").read_text(encoding="utf-8")
    mesh_builder_text = Path("src/structure-viewer/viewer-render-mesh-builders.js").read_text(encoding="utf-8")
    contour_text = Path("src/structure-viewer/viewer-contour-materials.js").read_text(encoding="utf-8")

    assert "const NODE_CONTOUR_FIELDS=new Set(['disp_mag','stress_vm']);" in text
    assert "const CONTOUR_LUT_SIZE=256;" in text
    assert "from './viewer-contour-materials.js';" in text
    assert "const contourMaterialToolkit=createViewerContourMaterialToolkit(THREE,{" in text
    assert "const CONTOUR_SURFACE_TESSELLATION_MIN=10;" in text
    assert "const CONTOUR_SURFACE_TESSELLATION_MAX=20;" in text
    assert "function computeAdaptiveContourSubdivisions(" in geometry_text
    assert "function buildHighResolutionContourSurfaceGeometry(" in geometry_text
    assert "function buildContourLutTexture(" in contour_text
    assert "function applySurfaceContourScalars(" in contour_text
    assert "function createSurfaceContourShaderMaterial(" in contour_text
    assert "function applySurfaceContourShaderMaterial(" in text
    assert "function buildContourSurfaceGeometry(" in geometry_text
    assert "function sampleBilinearColor(" in geometry_text
    assert "function sampleBilinearScalar(" in contour_text
    assert "function applyLineTubeContourColors(" in contour_text
    assert "function applySurfaceContourColors(" in contour_text
    assert "function updateDirectMeshContourGeometry(" in contour_text
    assert "new T.DataTexture(" in contour_text
    assert "new T.ShaderMaterial(" in contour_text
    assert "contourScalar" in contour_text
    assert "geometry?.getAttribute?.('uv')" in contour_text
    assert "buildLodSurfaceContourGeometry(verts,surfaceRenderLodProfile,{isInstancedSurface})" in text
    assert "vertexColors: true" in mesh_builder_text
    assert "renderMode==='wireframe'||renderMode==='contour'" in text
    assert "resolveNodeContourColor(" in text
