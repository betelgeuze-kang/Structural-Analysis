# Real Drawing IFC Solver-Exact Reconstruction Plan

- Contract: PASS_IFC_RECONSTRUCTION_PLAN_OPEN
- IFC assets: 7
- Blocked assets: 7
- Node-glyph fallback: 1
- Relationship coverage gaps: 1

## Reconstruction Queue

| Asset | Blocker | Edges / Structural | Edge Coverage | Required Evidence |
| --- | --- | ---: | ---: | --- |
| RD-001 | ERR_IFC_PROXY_RELATIONSHIP_COVERAGE_GAP | 534/661 | 0.8079 | ifc_relationship_edge_extraction_receipt, ifc_local_placement_coordinate_extraction_receipt, ifc_representation_shape_axis_receipt |
| RD-002 | ERR_IFC_PROXY_LAYOUT_NOT_TRUE_GEOMETRY | 77/77 | 1.0 | ifc_local_placement_coordinate_extraction_receipt, ifc_representation_shape_axis_receipt, ifc_material_section_binding_receipt |
| RD-003 | ERR_IFC_PROXY_LAYOUT_NOT_TRUE_GEOMETRY | 1170/1170 | 1.0 | ifc_local_placement_coordinate_extraction_receipt, ifc_representation_shape_axis_receipt, ifc_material_section_binding_receipt |
| RD-004 | ERR_IFC_PROXY_LAYOUT_NOT_TRUE_GEOMETRY | 238/238 | 1.0 | ifc_local_placement_coordinate_extraction_receipt, ifc_representation_shape_axis_receipt, ifc_material_section_binding_receipt |
| RD-005 | ERR_IFC_PROXY_LAYOUT_NOT_TRUE_GEOMETRY | 6772/6772 | 1.0 | ifc_local_placement_coordinate_extraction_receipt, ifc_representation_shape_axis_receipt, ifc_material_section_binding_receipt |
| RD-006 | ERR_IFC_PROXY_LAYOUT_NOT_TRUE_GEOMETRY | 843/843 | 1.0 | ifc_local_placement_coordinate_extraction_receipt, ifc_representation_shape_axis_receipt, ifc_material_section_binding_receipt |
| RD-007 | ERR_IFC_PROXY_NODE_GLYPH_FALLBACK | 0/829 | 0.0 | ifc_relationship_edge_extraction_receipt, ifc_local_placement_coordinate_extraction_receipt, ifc_representation_shape_axis_receipt |
