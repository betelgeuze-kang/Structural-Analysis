# Read canonical companion code-check metadata

Parent: `00aad16abd90df6b538ebce4a8786c70b776a2f3`.

The companion loader previously passed an empty metadata object to the DCR map
builder. The tracked canonical baseline `midas_generator_33.json` contains its
`kds_geometry_bridge` under `model.metadata` and has no root `case_context`.
Even a successful file response therefore yielded an empty companion map.

The loader now supplies the fetched canonical model metadata alongside its root
payload, preserving the model-root and combination-scope isolation added earlier.
Reports with root case-context tables continue to work through the existing path.
Absent metadata remains empty; no result is inferred from geometry. Inspection of
the optimized roundtrip original found no `kds_geometry_bridge` and no root
case-context table. Serving that file alone would not supply missing check data.

## Evidence

A new regression executes the actual companion browser function with the tracked
canonical baseline as the fetched response and the real DCR mapping module.
The destination is a controlled set of matching element IDs. Before the fix,
0 members were hydrated versus 242 expected. After the fix, all 242 values and
combination identities match the original-derived map for both KDS_ULS_1 and
all-combination requests. These are the same members, not 484 independent cases.
This establishes loader fidelity, not physical correctness of the stored DCRs.

The complete hydrator and drawing-comparison focused tests passed: 10 tests,
0.77 seconds. Existing coverage includes case-context companions, isolated model
roots, governing combination scope, and failed fetching. Ruff and whitespace
checks passed. Trusted Node type checking, production build and delivery
verification passed, followed by the registered preset browser test (1 passed,
23.5 seconds).

Reproduction commands (Node uses the pinned v24.20.0 runtime):

```text
python3 -m pytest tests/test_structure_viewer_codecheck_dcr_hydrator_contract.py tests/test_structure_viewer_drawing_comparison_engine_contract.py -q
node scripts/verify-workbench-v2-e2e.mjs --with-job-api --grep 'viewer runtime assets preserve originals and load configured preset' --workers=1
```

## Limits

The controlled fetch substitutes transport; it is not evidence that the canonical
file is available in the production host. No source artifact was copied into the
build or redistributed. The production preset regression checks the existing
build/loading path, not physical DCR qualification or baseline companion delivery.
No solver replay or training ran. Parent-head Python workflow 34721328476 remained
pending at inspection, while Issue State Current 34721328546 succeeded. Neither
is subsequent-head full acceptance. Broader roadmap gates remain open.
