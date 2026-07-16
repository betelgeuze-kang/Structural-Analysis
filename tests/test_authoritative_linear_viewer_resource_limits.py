from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from structural_analysis.results import (
    VIEWER_MAX_ELEMENT_COUNT,
    VIEWER_MAX_NODE_COUNT,
    VIEWER_RESOURCE_LIMIT_POLICY,
    ViewerPayloadValidationError,
    validate_linear_static_viewer_payload,
)
from structural_analysis.results import __all__ as result_exports


ROOT = Path(__file__).resolve().parents[1]
_HASH_A = "sha256:" + "a" * 64
_HASH_B = "sha256:" + "b" * 64


def _minimal_payload() -> dict[str, object]:
    zero_displacement = {
        "UX": 0.0,
        "UY": 0.0,
        "UZ": 0.0,
        "RX": 0.0,
        "RY": 0.0,
        "RZ": 0.0,
    }
    zero_force = {
        "FX": 0.0,
        "FY": 0.0,
        "FZ": 0.0,
        "MX": 0.0,
        "MY": 0.0,
        "MZ": 0.0,
    }
    return {
        "schema_version": "structural-analysis-viewer-payload.v2",
        "source": "authoritative_solver_result",
        "solver_path_id": "authoritative_cpu_linear_fea_3d_v1",
        "analysis_fidelity": "cpu_reference_linear_fea",
        "reaction_definition": "constrained_dof_internal_minus_external_force",
        "equilibrium_residual_definition": (
            "free_dof_internal_minus_external_force; constrained entries are zero"
        ),
        "model_identity": {
            "identity_policy": "source_bytes_and_detached_canonical_model_v1",
            "source_input_checksum": _HASH_A,
            "canonical_model_checksum": _HASH_B,
            "analysis_input_snapshot": "detached_canonical_model_v1",
        },
        "nodes": [
            {
                "id": "1",
                "coordinates": [0.0, 0.0, 0.0],
                "displacement": dict(zero_displacement),
                "reaction": dict(zero_force),
                "equilibrium_residual": dict(zero_force),
            },
            {
                "id": "2",
                "coordinates": [1.0, 0.0, 0.0],
                "displacement": dict(zero_displacement),
                "reaction": dict(zero_force),
                "equilibrium_residual": dict(zero_force),
            },
        ],
        "elements": [
            {
                "id": "1",
                "type": "truss",
                "nodes": ["1", "2"],
                "axial_force": 0.0,
                "elongation": 0.0,
                "local_end_forces": {"FX_I": 0.0, "FX_J": 0.0},
            }
        ],
    }


def test_python_schema_and_public_exports_share_large_model_gate() -> None:
    schema = json.loads(
        (
            ROOT
            / "src/structural_analysis/schemas/viewer_payload.schema.json"
        ).read_text(encoding="utf-8")
    )

    assert VIEWER_RESOURCE_LIMIT_POLICY == "authoritative_viewer_large_model_gate_v1"
    assert VIEWER_MAX_NODE_COUNT == 200_000
    assert VIEWER_MAX_ELEMENT_COUNT == 100_000
    assert schema["properties"]["nodes"]["maxItems"] == VIEWER_MAX_NODE_COUNT
    assert schema["properties"]["elements"]["maxItems"] == (
        VIEWER_MAX_ELEMENT_COUNT
    )
    assert {
        "VIEWER_MAX_NODE_COUNT",
        "VIEWER_MAX_ELEMENT_COUNT",
        "VIEWER_RESOURCE_LIMIT_POLICY",
    } <= set(result_exports)


def test_python_validator_rejects_oversized_arrays_before_item_walk() -> None:
    node_payload = _minimal_payload()
    node_payload["nodes"] = [None] * (VIEWER_MAX_NODE_COUNT + 1)
    with pytest.raises(ViewerPayloadValidationError) as node_error:
        validate_linear_static_viewer_payload(node_payload)
    assert node_error.value.code == "viewer_node_count_limit_exceeded"
    assert node_error.value.path == "/nodes"

    element_payload = _minimal_payload()
    element_payload["elements"] = [None] * (VIEWER_MAX_ELEMENT_COUNT + 1)
    with pytest.raises(ViewerPayloadValidationError) as element_error:
        validate_linear_static_viewer_payload(element_payload)
    assert element_error.value.code == "viewer_element_count_limit_exceeded"
    assert element_error.value.path == "/elements"


def test_browser_and_python_resource_limits_are_identical() -> None:
    script = f"""
import {{
  AUTHORITATIVE_VIEWER_MAX_ELEMENT_COUNT,
  AUTHORITATIVE_VIEWER_MAX_NODE_COUNT,
  AUTHORITATIVE_VIEWER_RESOURCE_LIMIT_POLICY,
  AuthoritativeViewerPayloadValidationError,
  validateAuthoritativeViewerResourceCounts,
}} from './src/structure-viewer/viewer-authoritative-payload-contract.js';

function capture(values) {{
  try {{
    return {{value: validateAuthoritativeViewerResourceCounts(values), error: null}};
  }} catch (error) {{
    return {{
      value: null,
      error: {{
        expectedType: error instanceof AuthoritativeViewerPayloadValidationError,
        code: error.code || '',
        path: error.path || '',
      }},
    }};
  }}
}}

console.log(JSON.stringify({{
  policy: AUTHORITATIVE_VIEWER_RESOURCE_LIMIT_POLICY,
  maxNodes: AUTHORITATIVE_VIEWER_MAX_NODE_COUNT,
  maxElements: AUTHORITATIVE_VIEWER_MAX_ELEMENT_COUNT,
  atLimit: capture({{
    nodeCount: AUTHORITATIVE_VIEWER_MAX_NODE_COUNT,
    elementCount: AUTHORITATIVE_VIEWER_MAX_ELEMENT_COUNT,
  }}),
  nodeOver: capture({{
    nodeCount: AUTHORITATIVE_VIEWER_MAX_NODE_COUNT + 1,
    elementCount: 1,
  }}),
  elementOver: capture({{
    nodeCount: 2,
    elementCount: AUTHORITATIVE_VIEWER_MAX_ELEMENT_COUNT + 1,
  }}),
  invalid: capture({{nodeCount: 1.5, elementCount: 1}}),
}}));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)

    assert payload["policy"] == VIEWER_RESOURCE_LIMIT_POLICY
    assert payload["maxNodes"] == VIEWER_MAX_NODE_COUNT
    assert payload["maxElements"] == VIEWER_MAX_ELEMENT_COUNT
    assert payload["atLimit"] == {
        "value": {
            "nodeCount": VIEWER_MAX_NODE_COUNT,
            "elementCount": VIEWER_MAX_ELEMENT_COUNT,
        },
        "error": None,
    }
    assert payload["nodeOver"]["error"] == {
        "expectedType": True,
        "code": "viewer_node_count_limit_exceeded",
        "path": "/nodes",
    }
    assert payload["elementOver"]["error"] == {
        "expectedType": True,
        "code": "viewer_element_count_limit_exceeded",
        "path": "/elements",
    }
    assert payload["invalid"]["error"] == {
        "expectedType": True,
        "code": "viewer_resource_count_invalid",
        "path": "/nodes",
    }
