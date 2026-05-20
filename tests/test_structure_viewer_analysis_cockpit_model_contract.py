from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run_node_contract_script(script: str) -> dict:
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_analysis_cockpit_model_builds_command_center_kpis_and_charts() -> None:
    payload = _run_node_contract_script(
        """
import {
  ANALYSIS_COCKPIT_KPI_KEYS,
  buildAnalysisCockpitModel,
} from './src/structure-viewer/viewer-analysis-cockpit-model.js';

const data = {
  nodes: [
    {id: 'N1', x: 0, y: 0, z: 0, dx: 0, dy: 0, dz: 0},
    {id: 'N2', x: 6, y: 0, z: 0, dx: 0.002, dy: 0, dz: 0},
    {id: 'N3', x: 0, y: 0, z: 3.6, dx: 0.020, dy: 0.004, dz: 0.001},
    {id: 'N4', x: 6, y: 0, z: 3.6, dx: 0.026, dy: 0.006, dz: 0.001},
    {id: 'N5', x: 0, y: 0, z: 7.2, dx: 0.062, dy: 0.010, dz: 0.002},
    {id: 'N6', x: 6, y: 0, z: 7.2, dx: 0.078, dy: 0.014, dz: 0.002},
    {id: 'N7', x: 0, y: 5, z: 7.2, dx: 0.070, dy: 0.020, dz: 0.002},
  ],
  elements: [
    {id: 'E1', member_id: 'C-21', type: 'column', story: '21', node_ids: ['N3', 'N5'], dcr: 0.96, shear_force_x_kN: 260},
    {id: 'E2', member_id: 'B-15A', type: 'beam', story: '15', node_ids: ['N5', 'N6'], dcr: 0.88, shear_force_y_kN: 190},
    {id: 'E3', member_id: 'W-02', type: 'wall', story: 'B2', node_ids: ['N1', 'N2', 'N4', 'N3'], dcr: 0.61, shear_force_z_kN: 310},
    {id: 'E4', member_id: 'S-07', type: 'slab', story: '7', node_ids: ['N3', 'N4', 'N6', 'N5'], dcr: 0.42},
  ],
  meta: {
    active_step: 14,
    total_steps: 20,
    governing_load_case: 'Pushover X+',
    active_level: '15',
    deformation_scale: 1,
    solver_label: 'Nonlinear (Displacement Control)',
    convergence_status: 'Converged',
    run_time: '00:11:08',
    cost_reduction_pct: 9.7,
    drift_limit_pct: 2,
  },
};
const model = buildAnalysisCockpitModel(data, {summary: {maxDcrValue: 0.96}});
console.log(JSON.stringify({
  kpiKeys: ANALYSIS_COCKPIT_KPI_KEYS,
  cardKeys: model.kpiCards.map((card) => card.key),
  firstCard: model.kpiCards[0],
  baseShearCard: model.kpiCards.find((card) => card.key === 'baseShear'),
  concreteVolumeCard: model.kpiCards.find((card) => card.key === 'concreteVolume'),
  optimizationLabels: model.optimizationRows.map((row) => row.label),
  criticalMembers: model.criticalMembers.map((row) => ({
    id: row.id,
    status: row.status,
    recommendedChange: row.recommendedChange,
    driftContributionPct: row.driftContributionPct,
  })),
  chartShape: {
    storyRows: model.charts.storyDrift.rows.length,
    loadStepPoints: model.charts.displacementLoadStep.points.length,
    materialRows: model.charts.materialQuantity.rows.length,
    heatmapCells: model.charts.utilizationHeatmap.cells.length,
  },
  timeline: model.timeline,
}));
"""
    )

    assert payload["kpiKeys"] == [
        "maxDisplacement",
        "maxInterstoryDrift",
        "baseShear",
        "utilizationRatio",
        "steelWeight",
        "concreteVolume",
        "materialCost",
        "costReduction",
    ]
    assert payload["cardKeys"] == payload["kpiKeys"]
    assert payload["firstCard"]["label"] == "Max Displacement"
    assert payload["firstCard"]["value"].endswith(" mm")
    assert payload["firstCard"]["value"] != "0.0 mm"
    assert payload["baseShearCard"]["value"] != "0 kN"
    assert payload["concreteVolumeCard"]["value"] != "0 m3"
    assert payload["optimizationLabels"] == [
        "Steel Weight",
        "Concrete Volume",
        "Material Cost",
        "CO2 Emissions",
    ]
    assert payload["criticalMembers"][0]["id"] == "C-21"
    assert payload["criticalMembers"][0]["status"] == "High"
    assert payload["criticalMembers"][0]["recommendedChange"] == "Increase section"
    assert payload["criticalMembers"][0]["driftContributionPct"] > 0
    assert payload["criticalMembers"][1]["id"] == "B-15A"
    assert payload["criticalMembers"][1]["status"] == "Watch"
    assert payload["criticalMembers"][1]["recommendedChange"] == "Increase size"
    assert payload["chartShape"] == {
        "storyRows": 2,
        "loadStepPoints": 20,
        "materialRows": 3,
        "heatmapCells": 72,
    }
    assert payload["timeline"] == {
        "loadCase": "Pushover X+",
        "activeStep": 14,
        "totalSteps": 20,
        "scale": 1,
        "solver": "Nonlinear (Displacement Control)",
        "convergence": "Converged",
        "runTime": "00:11:08",
    }


def test_analysis_cockpit_model_derives_nonzero_proxy_metrics_when_result_fields_are_missing() -> None:
    payload = _run_node_contract_script(
        """
import {buildAnalysisCockpitModel} from './src/structure-viewer/viewer-analysis-cockpit-model.js';

const data = {
  nodes: [
    {id: 'N1', x: 0, y: 0, z: 0},
    {id: 'N2', x: 8, y: 0, z: 0},
    {id: 'N3', x: 0, y: 8, z: 0},
    {id: 'N4', x: 8, y: 8, z: 0},
    {id: 'N5', x: 0, y: 0, z: 4},
    {id: 'N6', x: 8, y: 0, z: 4},
    {id: 'N7', x: 0, y: 8, z: 4},
    {id: 'N8', x: 8, y: 8, z: 4},
  ],
  elements: [
    {id: 'C1', member_id: 'C-01', type: 'column', story: '1', node_ids: ['N1', 'N5'], dcr: 0.87},
    {id: 'C2', member_id: 'C-02', type: 'column', story: '1', node_ids: ['N2', 'N6'], dcr: 0.73},
    {id: 'B1', member_id: 'B-01', type: 'beam', story: '1', node_ids: ['N5', 'N6'], dcr: 0.64},
    {id: 'S1', member_id: 'S-01', type: 'slab', story: '1', node_ids: ['N5', 'N6', 'N8', 'N7'], dcr: 0.48},
  ],
  meta: {
    governing_load_case: 'Pushover X+',
    concrete_volume_m3: 0,
    base_shear_kN: 0,
    max_displacement_mm: 0,
  },
};
const model = buildAnalysisCockpitModel(data, {summary: {maxDcrValue: 0.87}});
const cards = Object.fromEntries(model.kpiCards.map((card) => [card.key, card.value]));
console.log(JSON.stringify({
  cards,
  criticalDrift: model.criticalMembers[0].driftContributionPct,
  storyDriftPeak: Math.max(...model.charts.storyDrift.rows.map((row) => row.driftPct)),
}));
"""
    )

    assert payload["cards"]["maxDisplacement"] != "0.0 mm"
    assert payload["cards"]["baseShear"] != "0 kN"
    assert payload["cards"]["concreteVolume"] != "0 m3"
    assert payload["criticalDrift"] > 0
    assert payload["storyDriftPeak"] > 0
