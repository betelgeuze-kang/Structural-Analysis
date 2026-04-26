from pathlib import Path


def test_index_html_uses_instanced_mesh_pipeline_for_large_line_models() -> None:
    text = Path("src/structure-viewer/index.html").read_text(encoding="utf-8")

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
    assert "function createInstancedSurfaceWireframe(" in text
    assert "new THREE.InstancedMesh(" in text
    assert "mesh.setMatrixAt(" in text
    assert "mesh.setColorAt(" in text
    assert "registerPickAnalyticRecord(record);" in text
    assert "geometryKind:'surface'" in text
    assert "_surfaceDirectFallback:isInstancedSurface" in text
    assert "mesh.isInstancedMesh&&Number.isInteger(hit.instanceId)" in text


def test_index_html_keeps_instanced_wireframe_and_selection_refresh_hooks() -> None:
    text = Path("src/structure-viewer/index.html").read_text(encoding="utf-8")

    assert "function refreshInstancedVisuals()" in text
    assert "createInstancedWireframe(" in text
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

    assert "let surfaceRenderLodProfile=null,pickTargetMeshes=[],pickAccelerationRecords=[],pickAnalyticRecords=[],pickAnalyticSpatialIndex=null,largeModelBuildProfile=null;" in text
    assert "const SURFACE_LOD_MEDIUM_ELEMENT_THRESHOLD=" in text
    assert "const SURFACE_LOD_COARSE_ELEMENT_THRESHOLD=" in text
    assert "function buildSurfaceLodProfile(" in text
    assert "function computeSurfaceLodSubdivisions(" in text
    assert "function buildLodSurfaceContourGeometry(" in text
    assert "surfaceRenderLodProfile=buildSurfaceLodProfile(surfaceElements.length,instancableSurfaceElements.length);" in text
    assert "surfaceLodLabel:surfaceRenderLodProfile?.label||'full'" in text
    assert "surfaceContourSubdivisions:computeSurfaceLodSubdivisions(verts,surfaceRenderLodProfile,{isInstancedSurface})" in text
    assert "function shouldPreferInstancedSurfacePicking(" in text
    assert "function rebuildPickTargetMeshes(" in text
    assert "function getPickableMeshes(" in text
    assert "function buildPickSpatialIndex(" in text
    assert "function buildPickBoundsBvh(" in text
    assert "function buildPickSpatialIndexOverflowBvh(" in text
    assert "async function buildPickMeshTriangleEntries(" in text
    assert "function buildPickMeshTriangleBvh(" in text
    assert "function buildLocalGeometryTriangleEntries(" in text
    assert "async function buildPickMeshLocalTriangleCatalogs(" in text
    assert "function resolvePickRecordWorldMatrix(" in text
    assert "function createLocalRayFromWorldRay(" in text
    assert "function intersectPickTriangleBvhClosest(" in text
    assert "function intersectLargeModelMeshLocalCatalog(" in text
    assert "function appendPickMeshTrianglesFromGeometry(" in text
    assert "mesh?.isInstancedMesh&&Number.isInteger(record?.instanceId)" in text
    assert "mesh.getMatrixAt(record.instanceId,instanceMatrix);" in text
    assert "function buildPickSurfaceFacetEntries(" in text
    assert "function buildPickSurfaceFacetBvh(" in text
    assert "function queryPickTriangleEntriesBvh(" in text
    assert "function queryPickMeshTriangleBvh(" in text
    assert "function refreshDeformedPickMeshTriangleBvh()" in text
    assert "function shouldIncludePickSpatialIndexOverflowRecord(" in text
    assert "function estimatePickRecordEntryDistance(" in text
    assert "function queryPickSpatialIndexOverflowBvh(" in text
    assert "function queryPickSurfaceFacetBvh(" in text
    assert "function queryPickSpatialIndexCandidates(" in text
    assert "function intersectRayBoxDistances(" in text
    assert "function getPickSpatialIndexCellCoords(" in text
    assert "function pickLargeModelRecord(" in text
    assert "function intersectLargeModelLineRecord(" in text
    assert "function intersectLargeModelSurfaceRecord(" in text
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
    assert "const candidateEntries=queryPickSpatialIndexCandidates(pickAnalyticSpatialIndex,ray);" in text
    assert "if(index.meshTriangleBvh){" in text
    assert "queryPickMeshTriangleBvh(index.meshTriangleBvh,index.meshTriangleEntries,ray,pushCandidateEntry);" in text
    assert "if(showDeformed&&index.deformedMeshTriangleBvh){" in text
    assert "queryPickMeshTriangleBvh(index.deformedMeshTriangleBvh,index.deformedMeshTriangleEntries,ray,pushCandidateEntry);" in text
    assert "if(index.surfaceFacetBvh){" in text
    assert "queryPickSurfaceFacetBvh(index.surfaceFacetBvh,index.surfaceFacetEntries,ray,pushCandidateEntry);" in text
    assert "if(index.nonSurfaceRecordBvh){" in text
    assert "queryPickSpatialIndexOverflowBvh(index.nonSurfaceRecordBvh,ray,pushCandidateEntry);" in text
    assert "if(index.fullRecordBvh&&!index.meshTriangleBvh&&!index.surfaceFacetBvh&&!index.nonSurfaceRecordBvh){" in text
    assert "queryPickSpatialIndexOverflowBvh(index.fullRecordBvh,ray,pushCandidateEntry);" in text
    assert "if(index.denseBucketBvh){" in text
    assert "candidateEntries.sort((left,right)=>left.entryDistance-right.entryDistance)" in text
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


def test_index_html_uses_anisotropic_pick_spatial_index_cell_sizes_end_to_end() -> None:
    text = Path("src/structure-viewer/index.html").read_text(encoding="utf-8")

    assert "function getPickSpatialIndexAxisCellSize(index,axis){" in text
    assert "safeNumber(index?.[`cellSize${axis.toUpperCase()}`],0)," in text
    assert "safeNumber(index?.cellSize,0)," in text
    assert "ix:clampPickSpatialIndexCoord((point.x-index.boundsMin.x)/getPickSpatialIndexAxisCellSize(index,'x'),index.dimX)," in text
    assert "iy:clampPickSpatialIndexCoord((point.y-index.boundsMin.y)/getPickSpatialIndexAxisCellSize(index,'y'),index.dimY)," in text
    assert "iz:clampPickSpatialIndexCoord((point.z-index.boundsMin.z)/getPickSpatialIndexAxisCellSize(index,'z'),index.dimZ)," in text
    assert "const cellSizeX=axisExtentToCellSize(extent.x);" in text
    assert "const cellSizeY=axisExtentToCellSize(extent.y);" in text
    assert "const cellSizeZ=axisExtentToCellSize(extent.z);" in text
    assert "cellSize:Math.max(cellSizeX,cellSizeY,cellSizeZ)," in text
    assert "cellSizeX," in text
    assert "cellSizeY," in text
    assert "cellSizeZ," in text
    assert "const cellSizeX=getPickSpatialIndexAxisCellSize(index,'x');" in text
    assert "const cellSizeY=getPickSpatialIndexAxisCellSize(index,'y');" in text
    assert "const cellSizeZ=getPickSpatialIndexAxisCellSize(index,'z');" in text
    assert "?index.boundsMin.x+(ix+1)*cellSizeX" in text
    assert "?index.boundsMin.y+(iy+1)*cellSizeY" in text
    assert "?index.boundsMin.z+(iz+1)*cellSizeZ" in text
    assert "let tDeltaX=stepX!==0?Math.abs(cellSizeX/ray.direction.x):Infinity;" in text
    assert "let tDeltaY=stepY!==0?Math.abs(cellSizeY/ray.direction.y):Infinity;" in text
    assert "let tDeltaZ=stepZ!==0?Math.abs(cellSizeZ/ray.direction.z):Infinity;" in text
    assert "const pushCandidateEntry=(recordIndex,cellEntryDistance=0)=>{" in text
    assert "const entryDistance=Math.max(" in text
    assert "estimatePickRecordEntryDistance(ray,record,tolerance)" in text
    assert "pushBucketRecords(ix,iy,iz,traveled);" in text
    assert "overflowBvh:null," in text
    assert "denseBucketBvh:null," in text
    assert "fullRecordBvh:null," in text
    assert "nonSurfaceRecordBvh:null," in text
    assert "meshTriangleBvh:null," in text
    assert "deformedMeshTriangleBvh:null," in text
    assert "surfaceFacetBvh:null," in text
    assert "index.overflowBvh=buildPickSpatialIndexOverflowBvh(index.overflowIndices,index.records);" in text
    assert "queryPickMeshTriangleBvh(index.meshTriangleBvh,index.meshTriangleEntries,ray,pushCandidateEntry);" in text
    assert "queryPickMeshTriangleBvh(index.deformedMeshTriangleBvh,index.deformedMeshTriangleEntries,ray,pushCandidateEntry);" in text
    assert "queryPickSurfaceFacetBvh(index.surfaceFacetBvh,index.surfaceFacetEntries,ray,pushCandidateEntry);" in text
    assert "queryPickSpatialIndexOverflowBvh(index.nonSurfaceRecordBvh,ray,pushCandidateEntry);" in text
    assert "queryPickSpatialIndexOverflowBvh(index.fullRecordBvh,ray,pushCandidateEntry);" in text
    assert "queryPickSpatialIndexOverflowBvh(index.overflowBvh,ray,pushCandidateEntry);" in text
    assert "queryPickSpatialIndexOverflowBvh(index.denseBucketBvh,ray,pushCandidateEntry);" in text
    assert "if(bestHit&&candidate.entryDistance>bestHit.distance)break;" in text
    assert "record.pickMeshLocalCatalog=catalog;" in text
    assert "record.deformedPickMeshLocalCatalog=localCatalogByRecordIndex.get(recordIndex)||null;" in text
    assert "largeModelBuildProfile.pickSpatialMeshLocalCatalogCount=pickAnalyticSpatialIndex.meshLocalTriangleCatalogs.length;" in text
    assert "largeModelBuildProfile.pickSpatialDeformedMeshLocalCatalogCount=localCatalogs.length;" in text


def test_index_html_chunk_normalizes_large_payloads_off_main_slice() -> None:
    text = Path("src/structure-viewer/index.html").read_text(encoding="utf-8")

    assert "const NORMALIZATION_CHUNK_SIZE=" in text
    assert "async function yieldToMainThread(" in text
    assert "async function processInChunks(" in text
    assert "async function chunkMap(" in text
    assert "requestIdleCallback" in text
    assert "requestAnimationFrame" in text
    assert "async function sanitizeModelPayloadAsync(" in text
    assert "async function buildModelFromInteractivePayloadAsync(" in text
    assert "function createViewerOptimizationWorkerSource(" in text
    assert "function runViewerOptimizationWorker(" in text
    assert "async function sanitizeModelPayloadWithWorker(" in text
    assert "async function buildModelFromInteractivePayloadWithWorker(" in text
    assert "Normalizing payload in worker..." in text
    assert "forceChunking:totalSegments>NORMALIZATION_CHUNK_SIZE" in text
    assert "await processInChunks(baselineSegments" in text
    assert "await processInChunks(afterSegments" in text
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

    assert "ARTIFACT_PRESET_CANDIDATES" in text
    assert "midas_generator_33.json" in text
    assert "midas_generator_33.pr_recheck.json" in text
    assert "midas_generator_33.optimized.roundtrip.json" in text
    assert "PRESET_SIDECAR_FILES" in text
    assert "./index.midas33.data.js" in text
    assert "function extractModelPayload(" in text
    assert "payload.model&&typeof payload.model==='object'" in text
    assert "buildDirectModelMeta(" in text
    assert "load_case_inventory" in text
    assert "geometry_bridge_review_count" in text


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
    assert "function buildSectionCatalogSummary(" in text
    assert "Applied Section" in text
    assert "Edit Apply" in text
    assert "No draft staged. Preview entries will summarize current and target sections for the active member scope." in text


def test_index_html_uses_vertex_color_contour_interpolation() -> None:
    text = Path("src/structure-viewer/index.html").read_text(encoding="utf-8")

    assert "const NODE_CONTOUR_FIELDS=new Set(['disp_mag','stress_vm']);" in text
    assert "const CONTOUR_LUT_SIZE=256;" in text
    assert "const CONTOUR_SURFACE_TESSELLATION_MIN=10;" in text
    assert "const CONTOUR_SURFACE_TESSELLATION_MAX=20;" in text
    assert "function computeAdaptiveContourSubdivisions(" in text
    assert "function buildHighResolutionContourSurfaceGeometry(" in text
    assert "function buildContourLutTexture(" in text
    assert "function applySurfaceContourScalars(" in text
    assert "function createSurfaceContourShaderMaterial(" in text
    assert "function applySurfaceContourShaderMaterial(" in text
    assert "function buildContourSurfaceGeometry(" in text
    assert "function sampleBilinearColor(" in text
    assert "function sampleBilinearScalar(" in text
    assert "function applyLineTubeContourColors(" in text
    assert "function applySurfaceContourColors(" in text
    assert "function updateDirectMeshContourGeometry(" in text
    assert "new THREE.DataTexture(" in text
    assert "new THREE.ShaderMaterial(" in text
    assert "contourScalar" in text
    assert "geometry?.getAttribute?.('uv')" in text
    assert "buildLodSurfaceContourGeometry(verts,surfaceRenderLodProfile,{isInstancedSurface})" in text
    assert "vertexColors:true" in text
    assert "renderMode==='wireframe'||renderMode==='contour'" in text
    assert "resolveNodeContourColor(" in text
