from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_local_model_object_limits_cover_depth_counts_and_all_payload_routes() -> None:
    script = """
import {
  AUTHORITATIVE_VIEWER_MAX_ELEMENT_COUNT,
  AUTHORITATIVE_VIEWER_MAX_NODE_COUNT,
} from './src/structure-viewer/viewer-authoritative-payload-contract.js';
import {
  STRUCTURE_VIEWER_INGEST_MAX_SEGMENT_COUNT,
} from './src/structure-viewer/viewer-evidence-ingest-resource-policy.js';
import {
  VIEWER_LOCAL_MODEL_MAX_ELEMENT_COUNT,
  VIEWER_LOCAL_MODEL_MAX_JSON_CONTAINERS,
  VIEWER_LOCAL_MODEL_MAX_JSON_DEPTH,
  VIEWER_LOCAL_MODEL_MAX_NODE_COUNT,
  VIEWER_LOCAL_MODEL_MAX_SEGMENT_COUNT,
  VIEWER_LOCAL_MODEL_OBJECT_POLICY,
  ViewerLocalModelPayloadError,
  inspectViewerLocalModelJsonStructure,
  validateViewerLocalModelPayloadResources,
  viewerLocalModelObjectLimits,
} from './src/structure-viewer/viewer-local-model-payload-policy.js';
import {
  ViewerLocalModelFileError,
  readViewerLocalModelFile,
  viewerLocalModelFileMetadata,
} from './src/structure-viewer/viewer-local-model-file-reader.js';

function captureSync(fn) {
  try {
    return {value: fn(), error: null};
  } catch (error) {
    return {
      value: null,
      error: {
        expectedType: error instanceof ViewerLocalModelPayloadError,
        code: error.code || '',
        path: error.path || '',
      },
    };
  }
}

async function captureAsync(fn) {
  try {
    return {value: await fn(), error: null};
  } catch (error) {
    return {
      value: null,
      error: {
        expectedType: error instanceof ViewerLocalModelFileError,
        code: error.code || '',
        path: error.path || '',
        hasCause: Boolean(error.cause),
      },
    };
  }
}

const quotedText = JSON.stringify({
  text: 'literal { [ ] } and escaped quote " still text',
  rows: [{}, []],
});
const quoted = captureSync(() => inspectViewerLocalModelJsonStructure(
  quotedText,
  {maxDepth: 3, maxContainers: 4},
));
const depthOver = captureSync(() => inspectViewerLocalModelJsonStructure(
  '{"a":{"b":[{}]}}',
  {maxDepth: 3, maxContainers: 10},
));
const containerAt = captureSync(() => inspectViewerLocalModelJsonStructure(
  '{"a":[],"b":{}}',
  {maxDepth: 3, maxContainers: 3},
));
const containerOver = captureSync(() => inspectViewerLocalModelJsonStructure(
  '{"a":[],"b":{},"c":[]}',
  {maxDepth: 3, maxContainers: 3},
));
const invalidLimit = captureSync(() => inspectViewerLocalModelJsonStructure(
  '{}',
  {maxDepth: 1.5, maxContainers: 3},
));

const exact = captureSync(() => validateViewerLocalModelPayloadResources({
  nodes: new Array(VIEWER_LOCAL_MODEL_MAX_NODE_COUNT).fill(null),
  elements: new Array(VIEWER_LOCAL_MODEL_MAX_ELEMENT_COUNT).fill(null),
  interactive_3d: {
    baseline_segments: new Array(VIEWER_LOCAL_MODEL_MAX_SEGMENT_COUNT).fill(null),
    after_segments: [],
  },
}));
const rootNodeOver = captureSync(() => validateViewerLocalModelPayloadResources({
  nodes: new Array(VIEWER_LOCAL_MODEL_MAX_NODE_COUNT + 1).fill(null),
  elements: [],
}));
const modelElementOver = captureSync(() => validateViewerLocalModelPayloadResources({
  model: {
    nodes: [],
    elements: new Array(VIEWER_LOCAL_MODEL_MAX_ELEMENT_COUNT + 1).fill(null),
  },
}));
const nativeNodeOver = captureSync(() => validateViewerLocalModelPayloadResources({
  native_model: {
    nodes: new Array(VIEWER_LOCAL_MODEL_MAX_NODE_COUNT + 1).fill(null),
    elements: [],
  },
}));
const geometryElementOver = captureSync(() => validateViewerLocalModelPayloadResources({
  geometry: {
    nodes: [],
    elements: new Array(VIEWER_LOCAL_MODEL_MAX_ELEMENT_COUNT + 1).fill(null),
  },
}));
const interactiveOver = captureSync(() => validateViewerLocalModelPayloadResources({
  interactive_3d: {
    baseline_segments: new Array(VIEWER_LOCAL_MODEL_MAX_SEGMENT_COUNT).fill(null),
    after_segments: [{}],
  },
}));
const aggregateNodes = captureSync(() => validateViewerLocalModelPayloadResources({
  nodes: new Array(120000).fill(null),
  elements: [],
  model: {
    nodes: new Array(80001).fill(null),
    elements: [],
  },
}));
const aggregateElements = captureSync(() => validateViewerLocalModelPayloadResources({
  nodes: [],
  elements: new Array(60000).fill(null),
  native_model: {
    nodes: [],
    elements: new Array(40001).fill(null),
  },
}));
const aggregateSegments = captureSync(() => validateViewerLocalModelPayloadResources({
  baseline_segments: new Array(100000).fill(null),
  after_segments: [],
  interactive_3d_payload: {
    baseline_segments: new Array(100001).fill(null),
    after_segments: [],
  },
}));

let deep = {leaf: true};
for (let index = 0; index < VIEWER_LOCAL_MODEL_MAX_JSON_DEPTH; index += 1) {
  deep = {nested: deep};
}
const deepText = JSON.stringify(deep);
const deepReader = await captureAsync(() => readViewerLocalModelFile({
  name: 'deep.json',
  size: deepText.length,
  async text() { return deepText; },
}));

const nodeOverText = JSON.stringify({
  model: {
    nodes: new Array(VIEWER_LOCAL_MODEL_MAX_NODE_COUNT + 1).fill(null),
    elements: [],
  },
});
const nodeOverReader = await captureAsync(() => readViewerLocalModelFile({
  name: 'node-over.json',
  size: nodeOverText.length,
  async text() { return nodeOverText; },
}));

const validText = JSON.stringify({
  model: {
    nodes: [{}, {}],
    elements: [{}],
  },
  interactive_3d: {
    baseline_segments: [{}],
    after_segments: [{}, {}],
  },
});
const validReader = await captureAsync(() => readViewerLocalModelFile({
  name: 'valid-model.json',
  size: validText.length,
  async text() { return validText; },
}));
const validMetadata = viewerLocalModelFileMetadata(validReader.value);

console.log(JSON.stringify({
  constants: {
    policy: VIEWER_LOCAL_MODEL_OBJECT_POLICY,
    maxNodes: VIEWER_LOCAL_MODEL_MAX_NODE_COUNT,
    maxElements: VIEWER_LOCAL_MODEL_MAX_ELEMENT_COUNT,
    maxSegments: VIEWER_LOCAL_MODEL_MAX_SEGMENT_COUNT,
    maxDepth: VIEWER_LOCAL_MODEL_MAX_JSON_DEPTH,
    maxContainers: VIEWER_LOCAL_MODEL_MAX_JSON_CONTAINERS,
    authoritativeNodes: AUTHORITATIVE_VIEWER_MAX_NODE_COUNT,
    authoritativeElements: AUTHORITATIVE_VIEWER_MAX_ELEMENT_COUNT,
    ingestSegments: STRUCTURE_VIEWER_INGEST_MAX_SEGMENT_COUNT,
    limits: viewerLocalModelObjectLimits(),
  },
  quoted,
  depthOver,
  containerAt,
  containerOver,
  invalidLimit,
  exact,
  rootNodeOver,
  modelElementOver,
  nativeNodeOver,
  geometryElementOver,
  interactiveOver,
  aggregateNodes,
  aggregateElements,
  aggregateSegments,
  deepReader,
  nodeOverReader,
  validReader: validReader.value,
  validMetadata,
}));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    payload = json.loads(completed.stdout)

    constants = payload["constants"]
    assert constants == {
        "policy": "structure_viewer_local_model_object_budget_v1",
        "maxNodes": 200_000,
        "maxElements": 100_000,
        "maxSegments": 200_000,
        "maxDepth": 64,
        "maxContainers": 1_000_000,
        "authoritativeNodes": 200_000,
        "authoritativeElements": 100_000,
        "ingestSegments": 200_000,
        "limits": {
            "policy": "structure_viewer_local_model_object_budget_v1",
            "max_nodes": 200_000,
            "max_elements": 100_000,
            "max_segments": 200_000,
            "max_json_depth": 64,
            "max_json_containers": 1_000_000,
        },
    }
    budget = json.loads(
        (
            ROOT
            / "implementation/phase1/structure_viewer_performance_budget_manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert constants["maxElements"] == budget["budget_values"][
        "large_model_element_threshold"
    ]

    assert payload["quoted"] == {
        "value": {
            "policy": constants["policy"],
            "maximumDepth": 3,
            "containerCount": 4,
        },
        "error": None,
    }
    assert payload["containerAt"]["error"] is None
    assert payload["containerAt"]["value"]["containerCount"] == 3
    assert payload["depthOver"]["error"] == {
        "expectedType": True,
        "code": "local_model_nesting_depth_limit_exceeded",
        "path": "/",
    }
    assert payload["containerOver"]["error"] == {
        "expectedType": True,
        "code": "local_model_container_count_limit_exceeded",
        "path": "/",
    }
    assert payload["invalidLimit"]["error"] == {
        "expectedType": True,
        "code": "local_model_resource_limit_invalid",
        "path": "/limits/max_json_depth",
    }

    exact = payload["exact"]["value"]
    assert payload["exact"]["error"] is None
    assert exact == {
        "policy": constants["policy"],
        "maximumNodeCount": 200_000,
        "maximumElementCount": 100_000,
        "maximumSegmentCount": 200_000,
        "totalNodeCount": 200_000,
        "totalElementCount": 100_000,
        "totalSegmentCount": 200_000,
        "modelContainerCount": 1,
        "interactiveContainerCount": 1,
    }

    expected_errors = {
        "rootNodeOver": (
            "local_model_node_count_limit_exceeded",
            "/nodes",
        ),
        "modelElementOver": (
            "local_model_element_count_limit_exceeded",
            "/model/elements",
        ),
        "nativeNodeOver": (
            "local_model_node_count_limit_exceeded",
            "/native_model/nodes",
        ),
        "geometryElementOver": (
            "local_model_element_count_limit_exceeded",
            "/geometry/elements",
        ),
        "interactiveOver": (
            "local_model_segment_count_limit_exceeded",
            "/interactive_3d/segments",
        ),
        "aggregateNodes": (
            "local_model_total_node_count_limit_exceeded",
            "/model_containers/nodes",
        ),
        "aggregateElements": (
            "local_model_total_element_count_limit_exceeded",
            "/model_containers/elements",
        ),
        "aggregateSegments": (
            "local_model_total_segment_count_limit_exceeded",
            "/interactive_containers/segments",
        ),
    }
    for name, (code, path) in expected_errors.items():
        assert payload[name]["error"] == {
            "expectedType": True,
            "code": code,
            "path": path,
        }

    assert payload["deepReader"]["error"] == {
        "expectedType": True,
        "code": "local_model_nesting_depth_limit_exceeded",
        "path": "/",
        "hasCause": True,
    }
    assert payload["nodeOverReader"]["error"] == {
        "expectedType": True,
        "code": "local_model_node_count_limit_exceeded",
        "path": "/model/nodes",
        "hasCause": True,
    }

    valid_reader = payload["validReader"]
    assert valid_reader["objectPolicy"] == constants["policy"]
    assert valid_reader["maximumJsonDepth"] == 4
    assert valid_reader["jsonContainerCount"] == 13
    assert valid_reader["maximumNodeCount"] == 2
    assert valid_reader["maximumElementCount"] == 1
    assert valid_reader["maximumSegmentCount"] == 3
    assert valid_reader["payload"]["model"]["nodes"] == [{}, {}]
    assert payload["validMetadata"]["object_policy"] == constants["policy"]
    assert payload["validMetadata"]["maximum_json_depth"] == 4
    assert payload["validMetadata"]["json_container_count"] == 13
    assert payload["validMetadata"]["maximum_node_count"] == 2
    assert payload["validMetadata"]["maximum_element_count"] == 1
    assert payload["validMetadata"]["maximum_segment_count"] == 3
    assert "payload" not in payload["validMetadata"]
