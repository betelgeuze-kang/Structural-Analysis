# Real Drawing Viewer Quality Gate

- Contract: PASS_WITH_REVIEW_QUEUE
- Commercial viewer ready: True
- Full solver-exact ready: False
- Viewer: `src/structure-viewer/index.html?preset=real_drawing_private_3d`
- Recommended claim: Integrated real-drawing viewer is ready for engineer-in-loop review; proxy/preview assets are labeled and are not full solver-exact replacements.

## Summary

| Metric | Value |
| --- | ---: |
| Asset count | 18 |
| Renderable assets | 18 |
| Solver-exact assets | 11 |
| Proxy or preview assets | 7 |
| Review queue assets | 7 |
| Review items | 13 |
| Hard blockers | 0 |

- Quality flags: ifc_solver_graph_draft_not_member_extents=5, not_solver_exact=7, sampled_dense_model=1

## Review Queue

| Asset | Tier | Flags | Action |
| --- | --- | --- | --- |
| RD-001 | proxy_preview_review | ifc_solver_graph_draft_not_member_extents, not_solver_exact | recover member extents and close IFC load/zero-load evidence |
| RD-002 | proxy_preview_review | not_solver_exact | close IFC load/zero-load evidence and promote draft to solver-exact topology |
| RD-003 | proxy_preview_review | ifc_solver_graph_draft_not_member_extents, not_solver_exact | recover member extents and close IFC load/zero-load evidence |
| RD-004 | proxy_preview_review | not_solver_exact | close IFC load/zero-load evidence and promote draft to solver-exact topology |
| RD-005 | proxy_preview_review | ifc_solver_graph_draft_not_member_extents, sampled_dense_model, not_solver_exact | recover member extents and close IFC load/zero-load evidence |
| RD-006 | proxy_preview_review | ifc_solver_graph_draft_not_member_extents, not_solver_exact | recover member extents and close IFC load/zero-load evidence |
| RD-007 | proxy_preview_review | ifc_solver_graph_draft_not_member_extents, not_solver_exact | recover member extents and close IFC load/zero-load evidence |
