# Preserve model and load-combination scope during companion hydration

Parent: `6d0800876349bab576ed0e3e695f37effb791608`.

`applyFullCodecheckHydration()` accepted a model-specific `rootPayload` and
`allCombinations` flag. Its companion helper instead used the global optimized
root and always built a single-combination map. With matching element IDs, this
could replace a baseline model's DCR with an unrelated optimized-model value.
It could also replace an all-combination governing value with the active
combination when a companion response arrived.

The helper now receives both options explicitly. It builds local and companion
maps for the same requested scope, without falling back to the global root.
The public helper's omitted root defaults to null. The existing caller explicitly
passes its selected root; baseline calls that specify null remain isolated.

## Reproduction and verification

A test extracts the actual two browser functions from the HTML and imports the
real mapping/hydration module. Only fetching and browser globals are substituted.
Synthetic models deliberately share an element ID. Before the fix, both selected
and all-combination calls returned optimized-root DCR 9 instead of 0.5 and 1.4.
These values are input-contract fixtures, not calculated structural results.

The final test covers selected combination, local governing combination,
companion governing combination, explicitly absent local root, and failed
companion fetch. All-combination outputs retain the governing combination name.
Together with existing hydrator and drawing-comparison tests: 9 passed in 0.70s.
Ruff and git diff whitespace checks passed. Trusted Node TypeScript, production
build and delivery checks passed, followed by one registered browser test
(23.5 seconds).

Commands:

```text
python3 -m pytest tests/test_structure_viewer_codecheck_dcr_hydrator_contract.py tests/test_structure_viewer_drawing_comparison_engine_contract.py -q
node scripts/verify-workbench-v2-e2e.mjs --with-job-api --grep 'viewer runtime assets preserve originals and load configured preset' --workers=1
```

Node commands use the pinned v24.20.0 runtime. The browser check exercises preset
loading and missing-timeline handling; the controlled function test specifically
exercises differing model roots and combination scopes. Neither is independent
physical verification. No numerical solve or training fit was added.

## Hosted state and remaining limits

At inspection, parent-head Repository Python Tests run 34721158553 still had all
six jobs queued, including four full shards. No new full-suite result or failure
cause was inferred. Issue State Current run 34721158657 succeeded for that parent.
These statuses do not qualify subsequent commits. The absent code-check companion
file in the production host remains unresolved: this change fixes isolation and
scope when data is available, and preserves local data when fetching fails.
Full CI, learned net benefit, independent validation and broader roadmap remain
open. Existing sealed observation packets are unchanged.
