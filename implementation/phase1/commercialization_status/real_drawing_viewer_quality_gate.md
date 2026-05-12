# Real Drawing Viewer Quality Gate

- Contract: PASS_WITH_REVIEW_QUEUE
- Commercial viewer ready: True
- Full solver-exact ready: False
- Viewer: `src/structure-viewer/index.html?preset=real_drawing_private_3d`
- Recommended claim: Integrated real-drawing viewer is ready for engineer-in-loop review; IFC geometry-ready drafts are separated from load-model/analysis claim gaps.

## Summary

| Metric | Value |
| --- | ---: |
| Asset count | 18 |
| Renderable assets | 18 |
| Solver-exact assets | 11 |
| Geometry-exact assets | 18 |
| IFC geometry-exact assets | 7 |
| Load-model missing assets | 7 |
| Analysis-claim ready assets | 11 |
| Proxy or preview assets | 7 |
| Review queue assets | 7 |
| Review items | 7 |
| Hard blockers | 0 |

- Quality flags: not_solver_exact=7
- Source quality flags: ifc_source_shape_missing_partial=1
- Claim quality flags: ifc_load_model_missing=7

## Review Queue

| Asset | Tier | Flags | Action |
| --- | --- | --- | --- |
| RD-001 | ifc_geometry_ready_load_review | not_solver_exact, claim:ifc_load_model_missing | attach IFC load-model evidence before analysis claim |
| RD-002 | ifc_geometry_ready_load_review | not_solver_exact, claim:ifc_load_model_missing | attach IFC load-model evidence before analysis claim |
| RD-003 | ifc_geometry_ready_load_review | not_solver_exact, claim:ifc_load_model_missing | attach IFC load-model evidence before analysis claim |
| RD-004 | ifc_geometry_ready_load_review | not_solver_exact, claim:ifc_load_model_missing | attach IFC load-model evidence before analysis claim |
| RD-005 | ifc_geometry_ready_load_review | not_solver_exact, claim:ifc_load_model_missing | attach IFC load-model evidence before analysis claim |
| RD-006 | ifc_geometry_ready_load_review | not_solver_exact, claim:ifc_load_model_missing | attach IFC load-model evidence before analysis claim |
| RD-007 | ifc_geometry_ready_load_review | not_solver_exact, claim:ifc_load_model_missing | attach IFC load-model evidence before analysis claim |
