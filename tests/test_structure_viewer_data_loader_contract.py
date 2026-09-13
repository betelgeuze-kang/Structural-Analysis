from __future__ import annotations

import json
import subprocess
from pathlib import Path


def test_workspace_preset_failure_continues_to_declared_artifact() -> None:
    script = r"""
import {readFileSync} from 'node:fs';
const html=readFileSync('src/structure-viewer/index.html','utf8');
const start=html.indexOf('async function loadWorkspaceResolvedModelData(){');
const end=html.indexOf('async function loadInitialModelData(){',start);
if(start<0||end<start)throw Error('workspace loader not found');
const source=html.slice(start,end);
const run=new Function('workspaceState','window','normalizePresetToken','normalizeSelectionValue',
  'setLoadingMessage','resolvePresetModelPayload','getPresetSidecarPath','normalizeLoadedPayload',
  'tryFetchArtifact','console',source+';return loadWorkspaceResolvedModelData();');
const results=[];
for(const mode of ['preset','artifact','missing']){
 const warnings=[],calls=[];
 const result=await run({viewerPreset:'configured',projectId:'project',drawingId:'drawing'},
  {__STRUCTURE_VIEWER_WORKSPACE_RESOLVED_ARTIFACT__:'declared.json'},x=>x,x=>x,()=>{},
  async()=>{calls.push('preset');if(mode!=='preset')throw Error('sidecar unavailable');return {payload:{marker:'preset'},sourcePath:'preset.js'};},
  ()=> 'preset.js',async payload=>payload,
  async path=>{calls.push(path);if(mode==='missing')throw Error('artifact unavailable');return {payload:{marker:'artifact'},resolvedPath:path,label:'declared model',loadedAt:'fixture-time'};},
  {warn:(...args)=>warnings.push(String(args[0]))});
 results.push({mode,result,calls,warnings});
}
console.log(JSON.stringify(results));
"""
    process = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )
    assert process.returncode == 0, process.stderr
    preset, artifact, missing = json.loads(process.stdout)
    assert preset["result"]["data"] == {"marker": "preset"}
    assert preset["result"]["sourceMeta"]["mode"] == "inline_preset"
    assert preset["calls"] == ["preset"]
    assert preset["warnings"] == []
    assert artifact["result"]["data"] == {"marker": "artifact"}
    assert artifact["result"]["sourceMeta"]["resolvedPath"] == "declared.json"
    assert artifact["result"]["sourceMeta"]["mode"] == "artifact"
    assert artifact["calls"] == ["preset", "declared.json"]
    assert len(artifact["warnings"]) == 1
    assert missing["result"] is None
    assert missing["calls"] == ["preset", "declared.json"]
    assert len(missing["warnings"]) == 2


def test_viewer_data_loader_resolves_preset_aliases_and_candidate_order() -> None:
    script = """
import {
  buildArtifactCandidates,
  getPresetSidecarPath,
  getRequestedPreset,
  readEmbeddedPayload,
  normalizePresetToken,
  readEmbeddedPresetPayload,
} from './src/structure-viewer/viewer-data-loader.js';

const root = {
  __STRUCTURE_VIEWER_WORKSPACE_RESOLVED_PRESET__: 'midas33_optimized',
  __STRUCTURE_VIEWER_WORKSPACE_RESOLVED_ARTIFACT__: 'workspace-artifact.json',
  __STRUCTURE_VIEWER_PAYLOAD__: {inline: true},
  __STRUCTURE_VIEWER_PRESET_PAYLOADS__: {
    real_drawing_private_3d: {
      label: 'fixture real drawings',
      report_name: 'fixture-report',
      path: 'fixture-sidecar',
      payload: {model: {nodes: [], elements: []}},
    },
  },
};
globalThis.window = root;
console.log(JSON.stringify({
  alias: normalizePresetToken('real drawings'),
  query: getRequestedPreset('?model_preset=real_drawing_3d'),
  sidecar: getPresetSidecarPath('real_drawings'),
  workspacePreset: getRequestedPreset(''),
  candidates: buildArtifactCandidates('?preset=midas33_pr&artifact=custom.json').slice(0, 3),
  workspaceCandidates: buildArtifactCandidates('').slice(0, 2),
  inlineLabel: readEmbeddedPayload({root})?.label || '',
  embedded: readEmbeddedPresetPayload('real_drawings', root)?.reportName || '',
}));
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["alias"] == "real_drawing_private_3d"
    assert payload["query"] == "real_drawing_private_3d"
    assert payload["sidecar"] == "./index.real_drawing_private.data.js"
    assert payload["workspacePreset"] == "midas33_optimized"
    assert payload["candidates"][0] == "custom.json"
    assert payload["candidates"][1] == "workspace-artifact.json"
    assert any(candidate.endswith("midas_generator_33.pr_recheck.json") for candidate in payload["candidates"])
    assert payload["workspaceCandidates"][0] == "workspace-artifact.json"
    assert payload["inlineLabel"] == "window.__STRUCTURE_VIEWER_PAYLOAD__"
    assert payload["embedded"] == "fixture-report"
