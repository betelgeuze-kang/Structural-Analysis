# Real Drawing Solver-Exact Promotion Queue

- Contract: PASS_PROMOTION_QUEUE_OPEN
- Viewer: `src/structure-viewer/index.html?preset=real_drawing_private_3d`
- Current solver-exact assets: 7
- Target solver-exact assets: 10
- Planned unlock batch: 3 assets
- Planned solver-exact after batch: 10

## Planned Unlock Batch

| ID | Asset | Family | Delta | Action |
| --- | --- | --- | ---: | --- |
| RP-001 | RD-013 | archive_preview_exactness_verification | 1 | verify decoded archive preview against native solver topology and flip solver_exact when topology is complete |
| RP-002 | RD-014 | archive_preview_exactness_verification | 1 | verify decoded archive preview against native solver topology and flip solver_exact when topology is complete |
| RP-003 | RD-012 | archive_sparse_preview_expansion | 1 | expand sparse decoded archive preview into complete solver topology before solver_exact promotion |

## Full Queue

| ID | Asset | Family | Effort | Delta | Flags |
| --- | --- | --- | --- | ---: | --- |
| RP-001 | RD-013 | archive_preview_exactness_verification | low | 1 | not_solver_exact |
| RP-002 | RD-014 | archive_preview_exactness_verification | low | 1 | not_solver_exact |
| RP-003 | RD-012 | archive_sparse_preview_expansion | medium | 1 | not_solver_exact, sparse_preview |
| RP-004 | RD-017 | archive_sparse_preview_expansion | medium | 1 | not_solver_exact, sparse_preview |
| RP-005 | RD-007 | ifc_node_glyph_topology_rebuild | medium_high | 1 | not_solver_exact, proxy_layout_not_true_geometry, proxy_node_glyph_fallback |
| RP-006 | RD-001 | ifc_coordinate_geometry_reconstruction | high | 1 | not_solver_exact, proxy_layout_not_true_geometry |
| RP-007 | RD-002 | ifc_coordinate_geometry_reconstruction | high | 1 | not_solver_exact, proxy_layout_not_true_geometry |
| RP-008 | RD-003 | ifc_coordinate_geometry_reconstruction | high | 1 | not_solver_exact, proxy_layout_not_true_geometry |
| RP-009 | RD-004 | ifc_coordinate_geometry_reconstruction | high | 1 | not_solver_exact, proxy_layout_not_true_geometry |
| RP-010 | RD-005 | ifc_coordinate_geometry_reconstruction | high | 1 | not_solver_exact, proxy_layout_not_true_geometry |
| RP-011 | RD-006 | ifc_coordinate_geometry_reconstruction | high | 1 | not_solver_exact, proxy_layout_not_true_geometry |
| RP-012 | RD-008 | solver_exact_lod_completion | medium | 0 | sampled_dense_model |
