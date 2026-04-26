# Priority Irregular Structure Families

Priority 1 is the highest-value first-capture target. `likely_formats` are the first corpus payloads we should expect.

| priority | id | why_it_matters | irregularity_tags | likely_formats | authority_fit | ai_learning_fit | recommended_kpi_or_validation_angle |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | transfer_podium_tower | Transfer podiums expose sharp load-path jumps. | transfer_story, podium, load_transfer, vertical_irregularity | mgt, json, tcl | high | very-high | transfer-story demand ratio; load-path continuity |
| 2 | soft_story_podium_tower | Canonical soft-story drift concentration case. | soft_story, vertical_irregularity, stiffness_drop, drift_concentration | mgt, json, tcl | high | very-high | story stiffness ratio; P-Delta amplification |
| 3 | torsionally_eccentric_core_tower | Offset core and mass eccentricity drive torsion. | torsion, core_offset, plan_asymmetry, mass_eccentricity | mgt, json, npz | high | very-high | torsional irregularity index; corner drift spread |
| 4 | setback_tower | Setbacks break stiffness and mass continuity. | setback, vertical_irregularity, massing, load_path_step | mgt, json, tcl | high | high | setback-level demand jump; mode-shape discontinuity |
| 5 | reentrant_corner_tower | Re-entrant corners concentrate diaphragm shear. | reentrant_corner, plan_irregularity, diaphragm_torsion, corner_hotspot | mgt, json, npz | high | very-high | corner drift amplification; torsion/drift ratio |
| 6 | outrigger_megatall_offset_core | Megatall outriggers make coupled load sharing visible. | outrigger, megatall, offset_core, tall_building | mgt, json, npz | high | high | core drift reduction; outrigger force share |
| 7 | discontinuous_braced_frame_tower | Brace discontinuities expose weak-story behavior. | braced_frame, brace_discontinuity, vertical_irregularity, load_path_break | mgt, json, tcl | high | high | brace force redistribution; drift concentration |
| 8 | hanging_column_podium_tower | Hanging columns test reverse load flow. | hanging_column, suspended_floor, transfer, vertical_discontinuity | mgt, json, tcl | medium-high | very-high | force path completeness; transfer deflection |
| 9 | diagrid_exoskeleton_asymmetric_tower | Diagrids stress perimeter stiffness reasoning. | diagrid, exoskeleton, asymmetry, perimeter_stiffness | mgt, json, npz | high | high | perimeter-to-core stiffness share; node stress concentration |
| 10 | split_core_linked_towers | Linked towers form a coupled-system benchmark. | split_core, linked_towers, coupled_system, skybridge | mgt, json, npz | medium-high | very-high | inter-tower drift differential; link force demand |
| 11 | cantilevered_upper_volume_tower | Overhangs make support demand obvious. | cantilever, overhang, load_reversal, mass_offset | mgt, json, tcl | medium-high | high | tip deflection; support moment ratio |
| 12 | vertical_mass_jump_tower | Mass jumps shift modes and acceleration demand. | mass_irregularity, vertical_jump, dynamic_shift, stiffness_mismatch | mgt, json, csv | high | very-high | mode-shape jump; acceleration ratio |
| 13 | atrium_void_ring_tower | Internal voids create tricky diaphragm flow. | atrium_void, diaphragm_discontinuity, plan_void, torsion | mgt, json, npz | medium-high | very-high | shear flow around void; torsion amplification |
| 14 | twisted_tapered_tower | Twist plus taper tests shape-aware reasoning. | twist, taper, geometry_irregularity, mode_coupling | mgt, json, npz | medium-high | high | twist angle vs drift; coupled-mode ratio |
| 15 | sloped_site_stepped_podium_tower | Grade changes hide practical irregularity. | sloping_site, stepped_foundation, podium_step, level_change | mgt, json, csv | medium | medium-high | base reaction imbalance; foundation demand skew |
| 16 | skewed_column_frame | Nonorthogonal grids test geometry-aware transfer. | skew, nonorthogonal_grid, frame_irregularity, lateral_offset | mgt, json, tcl | high | high | skew-induced secondary forces; plan response coupling |
| 17 | bridge_skewed_support_span | Bridge skew expands the track beyond towers. | bridge, skew_support, support_irregularity, global_torsion | mgt, json, npz | medium-high | high | support reaction spread; torsional twist |
| 18 | curved_plan_bridge_torsion | Curved bridges are a clean torsion edge case. | bridge, curved_plan, torsion, alignment_irregularity | mgt, json, npz | medium | high | curvature-induced torsion; lane-load asymmetry |
| 19 | long_span_irregular_roof_truss | Irregular roof trusses help with big-span learning. | roof_truss, long_span, support_irregularity, gravity_lateral_coupling | mgt, json, tcl | medium | high | partial-load deflection; support reaction imbalance |
| 20 | free_form_shell_core_hybrid | Shell-plus-core hybrids are the hardest geometry bucket. | free_form, shell, hybrid_system, geometry_irregularity | mgt, json, npz | medium | high | geometry-to-response consistency; local instability sensitivity |
