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


def test_shared_selection_state_module_reads_query_storage_and_builds_payloads() -> None:
    payload = _run_node_contract_script(
        """
import {
  SHARED_SELECTION_KEY,
  applySharedSelectionQueryParams,
  buildSharedSelectionPayload,
  normalizeSelectionValues,
  readSharedSelectionState,
} from './src/structure-viewer/viewer-shared-selection-state.js';

const storage = new Map();
storage.set(SHARED_SELECTION_KEY, JSON.stringify({
  memberId: 'M-stored',
  memberIds: ['M-stored', 'M-002'],
  loadCase: 'LC-stored',
  updated_at: '2026-05-13T00:00:00Z',
}));

const fromQuery = readSharedSelectionState({
  search: '?member=M-001&member_set=M-001|M-003&load_case=LCB1',
  storageGet: (key) => storage.get(key) || null,
});
const fromStorage = readSharedSelectionState({
  storageGet: (key) => storage.get(key) || null,
});
const payload = buildSharedSelectionPayload({
  memberId: '',
  memberIds: ['M-003', 'M-004', 'M-003'],
  loadCase: ' LCB2 ',
}, {
  source: 'test_source',
  viewerFamily: 'test_viewer',
  updatedAt: 'fixed',
});
const url = new URL('https://viewer.test/index.html?member=old&member_set=old2&load_case=old3');
applySharedSelectionQueryParams(url, payload);
const cleanUrl = new URL('https://viewer.test/index.html?member=old&member_set=old2&load_case=old3');
applySharedSelectionQueryParams(cleanUrl, {memberId: '', memberIds: [], loadCase: ''});

console.log(JSON.stringify({
  fromQuery,
  fromStorage,
  payload,
  url: url.toString(),
  cleanUrl: cleanUrl.toString(),
  normalized: normalizeSelectionValues('M-1| |M-1|M-2'),
}));
"""
    )

    assert payload["fromQuery"]["memberId"] == "M-001"
    assert payload["fromQuery"]["memberIds"] == ["M-001", "M-003"]
    assert payload["fromQuery"]["loadCase"] == "LCB1"
    assert payload["fromStorage"]["memberId"] == "M-stored"
    assert payload["fromStorage"]["memberIds"] == ["M-stored", "M-002"]
    assert payload["fromStorage"]["loadCase"] == "LC-stored"
    assert payload["payload"]["memberId"] == "M-003"
    assert payload["payload"]["memberSet"] == ["M-003", "M-004"]
    assert payload["payload"]["selectionSetCount"] == 2
    assert payload["payload"]["source"] == "test_source"
    assert payload["payload"]["viewerFamily"] == "test_viewer"
    assert payload["payload"]["updated_at"] == "fixed"
    assert "member=M-003" in payload["url"]
    assert "member_set=M-003%7CM-004" in payload["url"]
    assert "load_case=LCB2" in payload["url"]
    assert payload["cleanUrl"] == "https://viewer.test/index.html"
    assert payload["normalized"] == ["M-1", "M-2"]
