# Missing optimization timeline in the production viewer

Parent: `adbb7dea2cd0242783ced412056076308362d827`.

The normal non-comparison path in `refreshDrawingComparisonPresentation()`
sets `optimizationTimelineModel=null` and calls `setOptimizationTimelineStep(-1)`.
The step resolver dereferenced `model.steps`; its default argument only handled
undefined, not explicit null. This interrupted drawing comparison presentation
before the missing-state publication completed.

Both step and stage resolvers now accept the absent model and return no step or
stage. The panel explicitly displays "Optimization history unavailable" and
"No optimization change history loaded". No change, cost saving, or comparison
result is manufactured. Existing ready-history tests remain in place.

## Verification

- New missing-model test failed before the implementation change (Node subprocess
  exit 1), then passed for null, undefined and an empty model; delivery rows remain
  empty and the stage index remains -1.
- Timeline and drawing-comparison contract suites: 13 passed in 0.68 seconds.
- Ruff and git diff whitespace checks passed.
- Trusted Node v24.20.0 runner: TypeScript check, production Vite build, delivery
  verifier, and the registered preset browser test passed (1 test, 23.7 seconds).
  The test fetched seven original runtime files byte-for-byte, loaded the MIDAS
  preset, observed no drawing-comparison presentation exception, and checked the
  disabled timeline and missing-history labels in the actual DOM.

Commands:

```text
python3 -m pytest tests/test_structure_viewer_optimization_timeline_model_contract.py tests/test_structure_viewer_drawing_comparison_engine_contract.py -q
node scripts/verify-workbench-v2-e2e.mjs --with-job-api --grep 'viewer runtime assets preserve originals and load configured preset' --workers=1
```

Node commands used the pinned trusted runtime. The earlier sealed WSGI observation
is unchanged; this turn used the formal browser runner and did not repeat that
separate observation or the RC numerical experiments. This is neither a complete
frontend-suite result nor current-head hosted CI approval. Missing code-check
companion data, independent physical validation, learned net benefit, and the
broader roadmap remain open.
