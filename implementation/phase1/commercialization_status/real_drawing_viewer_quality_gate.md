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
| Review queue assets | 10 |
| Review items | 18 |
| Hard blockers | 0 |

- Quality flags: not_solver_exact=7, proxy_layout_not_true_geometry=7, proxy_node_glyph_fallback=1, sampled_dense_model=1, sparse_preview=2

## Review Queue

| Asset | Tier | Flags | Action |
| --- | --- | --- | --- |
| RD-001 | proxy_preview_review | proxy_layout_not_true_geometry, not_solver_exact | replace proxy or preview topology with solver-exact structural geometry |
| RD-002 | proxy_preview_review | proxy_layout_not_true_geometry, not_solver_exact | replace proxy or preview topology with solver-exact structural geometry |
| RD-003 | proxy_preview_review | proxy_layout_not_true_geometry, not_solver_exact | replace proxy or preview topology with solver-exact structural geometry |
| RD-004 | proxy_preview_review | proxy_layout_not_true_geometry, not_solver_exact | replace proxy or preview topology with solver-exact structural geometry |
| RD-005 | proxy_preview_review | proxy_layout_not_true_geometry, not_solver_exact | replace proxy or preview topology with solver-exact structural geometry |
| RD-006 | proxy_preview_review | proxy_layout_not_true_geometry, not_solver_exact | replace proxy or preview topology with solver-exact structural geometry |
| RD-007 | proxy_preview_review | proxy_layout_not_true_geometry, proxy_node_glyph_fallback, not_solver_exact | replace node glyph fallback with edge-backed topology |
| RD-008 | solver_exact_sampled_review | sampled_dense_model | inspect sampled dense model before using it as a full-detail design claim |
| RD-012 | sparse_preview_review | sparse_preview | expand sparse preview into a complete solver-exact model |
| RD-017 | sparse_preview_review | sparse_preview | expand sparse preview into a complete solver-exact model |
