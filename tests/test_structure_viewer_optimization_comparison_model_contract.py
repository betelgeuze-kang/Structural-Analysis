from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run_node(script: str) -> dict:
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_optimization_comparison_model_formats_exact_counts_and_proxy_delta() -> None:
    payload = _run_node(
        """
import {buildOptimizationComparisonModel} from './src/structure-viewer/viewer-optimization-comparison-model.js';

const ready = buildOptimizationComparisonModel({
  workspace: {
    drawing: {
      source_family: 'midas_mgt',
      optimization_summary: {
        baseline_member_count: 11334,
        optimized_member_count: 2242,
        evidence_level: 'repo exact roundtrip release counts',
        risk_delta_label: 'D/C movement requires engineer-in-loop review',
        source: 'midas33_optimized_roundtrip.json',
        artifact_count_source: 'midas33_optimized_roundtrip.json',
      },
    },
  },
  data: {elements: [{id: 1}]},
});
const manifestOnly = buildOptimizationComparisonModel({
  workspace: {
    drawing: {
      optimization_summary: {
        baseline_member_count: 100,
        optimized_member_count: 80,
        evidence_level: 'manifest optimization_summary',
        source: 'manifest-row.json',
      },
    },
  },
  data: {},
});
const missing = buildOptimizationComparisonModel({
  workspace: {drawing: {source_family: 'ifc_midas_mixed'}},
  data: {},
});
console.log(JSON.stringify({
  readyStatus: ready.status,
  headline: ready.headline,
  memberRow: ready.rows.find((row) => row.label === 'Members'),
  proxyRow: ready.rows.find((row) => row.label === 'Weight / cost proxy'),
  riskRow: ready.rows.find((row) => row.label === 'Risk movement'),
  verification: ready.verification,
  verificationRow: ready.rows.find((row) => row.label === 'Count verification'),
  manifestOnlyVerification: manifestOnly.verification,
  missingStatus: missing.status,
  missingHeadline: missing.headline,
  missingMemberEvidence: missing.rows.find((row) => row.label === 'Members').evidence,
  missingVerification: missing.verification,
}));
"""
    )

    assert payload["readyStatus"] == "ready"
    assert payload["headline"] == "Members 11,334 -> 2,242 (-80.2%)"
    assert payload["memberRow"]["delta"] == "-9,092 (-80.2%)"
    assert payload["memberRow"]["evidence"] == "repo exact roundtrip release counts"
    assert payload["proxyRow"]["value"] == "-80.2%"
    assert payload["proxyRow"]["evidence"] == "derived proxy"
    assert payload["riskRow"]["value"] == "D/C movement requires engineer-in-loop review"
    assert payload["verification"]["status"] == "verified"
    assert payload["verification"]["label"] == "Artifact count verified"
    assert payload["verification"]["source"] == "midas33_optimized_roundtrip.json"
    assert payload["verificationRow"]["value"] == "Artifact count verified"
    assert payload["verificationRow"]["evidence"] == "artifact_count_source"
    assert payload["manifestOnlyVerification"]["status"] == "manifest_only"
    assert payload["manifestOnlyVerification"]["label"] == "Manifest comparison only"
    assert payload["missingStatus"] == "needs_review"
    assert payload["missingHeadline"] == "Before/optimized comparison evidence pending"
    assert payload["missingMemberEvidence"] == "missing evidence"
    assert payload["missingVerification"]["status"] == "missing"
