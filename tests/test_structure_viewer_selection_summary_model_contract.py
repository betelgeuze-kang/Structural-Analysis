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


def test_selection_summary_model_builds_keys_summary_and_clear_button_state() -> None:
    payload = _run_node_contract_script(
        """
import {
  buildClearSelectionButtonModel,
  buildElementSelectionKey,
  buildSelectionSetSummary,
} from './src/structure-viewer/viewer-selection-summary-model.js';

const records = [
  {id: 'E1', member_id: 'M1'},
  {id: 'E2', member_id: 'M2'},
  {id: 'E3', member_id: 'M2'},
  {id: 'E4'},
  {id: 'E5', case_id: 'CASE-5'},
];
const selectedKeys = new Set([
  buildElementSelectionKey(records[0]),
  buildElementSelectionKey(records[1]),
  buildElementSelectionKey(records[2]),
  buildElementSelectionKey(records[3]),
  buildElementSelectionKey(records[4]),
  'missing::key',
]);

console.log(JSON.stringify({
  key: buildElementSelectionKey({id: 'E10', member_id: 'M10'}),
  fallbackKey: buildElementSelectionKey({id: 'E11'}),
  summary2: buildSelectionSetSummary(records, selectedKeys, {limit: 2}),
  summary4: buildSelectionSetSummary(records, selectedKeys, {limit: 4}),
  emptySummary: buildSelectionSetSummary(records, new Set(), {limit: 2}),
  clear0: buildClearSelectionButtonModel(0),
  clear1: buildClearSelectionButtonModel(1),
  clear3: buildClearSelectionButtonModel(3),
}));
"""
    )

    assert payload == {
        "key": "M10::E10",
        "fallbackKey": "E11::E11",
        "summary2": "M1, M2 +2",
        "summary4": "M1, M2, #E4, #E5",
        "emptySummary": "--",
        "clear0": {"visible": False, "display": "none", "text": "Clear Selection"},
        "clear1": {"visible": True, "display": "inline-flex", "text": "Clear Selection"},
        "clear3": {"visible": True, "display": "inline-flex", "text": "Clear Selection (3)"},
    }
