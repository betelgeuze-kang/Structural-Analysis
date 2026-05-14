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


def test_real_drawing_panel_events_bind_core_interactions_without_browser_globals() -> None:
    payload = _run_node_contract_script(
        """
import {bindRealDrawingQualityPanelEvents} from './src/structure-viewer/viewer-real-drawing-panel-events.js';

class FakeNode {
  constructor({value = '', attrs = {}} = {}) {
    this.value = value;
    this.attrs = attrs;
    this.listeners = {};
    this.focusCalls = [];
    this.selectionRanges = [];
  }
  getAttribute(name) {
    return this.attrs[name] ?? null;
  }
  addEventListener(type, callback) {
    if (!this.listeners[type]) this.listeners[type] = [];
    this.listeners[type].push(callback);
  }
  emit(type, event = {}) {
    for (const callback of this.listeners[type] || []) callback(event);
  }
  focus(options) {
    this.focusCalls.push(options);
  }
  setSelectionRange(start, end) {
    this.selectionRanges.push([start, end]);
  }
}

class FakePanel {
  constructor(nodesBySelector) {
    this.nodesBySelector = nodesBySelector;
  }
  querySelector(selector) {
    return (this.nodesBySelector[selector] || [])[0] || null;
  }
  querySelectorAll(selector) {
    return this.nodesBySelector[selector] || [];
  }
}

const assetSelect = new FakeNode({value: 'RD-002'});
const stepPrev = new FakeNode({attrs: {'data-real-drawing-step': '-1'}});
const focusButton = new FakeNode();
const isolateButton = new FakeNode();
const copyButton = new FakeNode({attrs: {'data-real-drawing-copy-link': ''}});
const filterButton = new FakeNode({attrs: {'data-real-drawing-quality-filter': 'proxy'}});
const browserQuery = new FakeNode({value: 'ifc proxy'});
const browserClear = new FakeNode();
const browserSort = new FakeNode({value: 'asset'});
const nextReview = new FakeNode({attrs: {'data-real-drawing-next-review': 'RD-003'}});
const browserAsset = new FakeNode({attrs: {'data-real-drawing-browser-asset': 'RD-010'}});
const recentAsset = new FakeNode({attrs: {'data-real-drawing-recent-asset': 'RD-002'}});
const reviewAsset = new FakeNode({attrs: {'data-real-drawing-review-asset': 'RD-003'}});
const promotionAsset = new FakeNode({attrs: {'data-real-drawing-promotion-asset': 'RD-004'}});

const panel = new FakePanel({
  '[data-real-drawing-asset-select]': [assetSelect],
  '[data-real-drawing-step]': [stepPrev],
  '[data-real-drawing-focus]': [focusButton],
  '[data-real-drawing-isolate]': [isolateButton],
  '[data-real-drawing-copy-link]': [copyButton],
  '[data-real-drawing-quality-filter]': [filterButton],
  '[data-real-drawing-browser-query]': [browserQuery],
  '[data-real-drawing-browser-clear]': [browserClear],
  '[data-real-drawing-browser-sort]': [browserSort],
  '[data-real-drawing-next-review]': [nextReview],
  '[data-real-drawing-browser-asset]': [browserAsset],
  '[data-real-drawing-recent-asset]': [recentAsset],
  '[data-real-drawing-review-asset]': [reviewAsset],
  '[data-real-drawing-promotion-asset]': [promotionAsset],
});

const calls = [];
const bindings = bindRealDrawingQualityPanelEvents(panel, {
  focusQuery: true,
  getActiveAssetRef: () => 'RD-ACTIVE',
  focusAsset: (assetRef, options = {}) => calls.push(['focus', assetRef, options]),
  stepAsset: (direction) => calls.push(['step', direction]),
  copyDeepLink: (assetRef, node) => calls.push(['copy', assetRef, node === copyButton]),
  setQualityFilter: (filter) => calls.push(['filter', filter]),
  setAssetQuery: (query, options = {}) => calls.push(['query', query, options]),
  setBrowserSort: (sort) => calls.push(['sort', sort]),
});

assetSelect.emit('change');
stepPrev.emit('click');
focusButton.emit('click');
isolateButton.emit('click');
copyButton.emit('click');
filterButton.emit('click');
browserQuery.emit('input');
browserQuery.emit('keydown', {key: 'Escape'});
browserQuery.emit('keydown', {key: 'Enter'});
browserClear.emit('click');
browserSort.emit('change');
nextReview.emit('click');
browserAsset.emit('click');
recentAsset.emit('click');
reviewAsset.emit('click');
promotionAsset.emit('click');

console.log(JSON.stringify({
  bindings,
  calls,
  focusCalls: browserQuery.focusCalls,
  selectionRanges: browserQuery.selectionRanges,
}));
"""
    )

    assert payload["bindings"] == {
        "assetSelect": True,
        "stepButtons": 1,
        "focusButtons": 1,
        "isolateButtons": 1,
        "copyButtons": 1,
        "qualityFilterButtons": 1,
        "browserQuery": True,
        "browserClear": True,
        "browserSort": True,
        "nextReview": True,
        "browserAssetButtons": 1,
        "recentAssetButtons": 1,
        "reviewAssetButtons": 1,
        "promotionAssetButtons": 1,
    }
    assert payload["calls"] == [
        ["focus", "RD-002", {}],
        ["step", -1],
        ["focus", "RD-ACTIVE", {}],
        ["focus", "RD-ACTIVE", {"isolate": True}],
        ["copy", "RD-ACTIVE", True],
        ["filter", "proxy"],
        ["query", "ifc proxy", {"preserveFocus": True}],
        ["focus", "RD-010", {}],
        ["query", "", {"preserveFocus": True}],
        ["sort", "asset"],
        ["focus", "RD-003", {}],
        ["focus", "RD-010", {}],
        ["focus", "RD-002", {}],
        ["focus", "RD-003", {}],
        ["focus", "RD-004", {}],
    ]
    assert payload["focusCalls"] == [{"preventScroll": True}]
    assert payload["selectionRanges"] == [[9, 9]]
