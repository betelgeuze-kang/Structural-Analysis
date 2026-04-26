# White-box Validation Report

| Domain | Case | Metric | LF rel err | GNN rel err | Improved |
|---|---|---:|---:|---:|---:|
| building | cantilever_2d | disp_max_mm | 0.0403 | 0.0040 | true |
| building | cantilever_2d | stress_max_mpa | 0.0546 | 0.0067 | true |
| building | cantilever_2d | reaction_kN | 0.0120 | 0.0009 | true |
| building | cantilever_2d | equilibrium_residual | 0.0180 | 0.0040 | true |
| building | one_story_rahmen | disp_max_mm | 0.0465 | 0.0058 | true |
| building | one_story_rahmen | stress_max_mpa | 0.0628 | 0.0094 | true |
| building | one_story_rahmen | reaction_kN | 0.0152 | 0.0013 | true |
| building | one_story_rahmen | equilibrium_residual | 0.0220 | 0.0050 | true |
| track | track_moving_load_span | disp_max_mm | 0.0677 | 0.0129 | true |
| track | track_moving_load_span | acc_peak_mps2 | 0.0857 | 0.0163 | true |
| track | track_moving_load_span | contact_force_kN | 0.0324 | 0.0048 | true |
| track | track_moving_load_span | equilibrium_residual | 0.0150 | 0.0040 | true |
| tunnel | tunnel_longitudinal_seismic | disp_max_mm | 0.0495 | 0.0104 | true |
| tunnel | tunnel_longitudinal_seismic | lining_moment_kNm | 0.0510 | 0.0097 | true |
| tunnel | tunnel_longitudinal_seismic | strain_peak | 0.0833 | 0.0167 | true |
| tunnel | tunnel_longitudinal_seismic | equilibrium_residual | 0.0170 | 0.0050 | true |
| integrated | rail_tunnel_building_coupled | building_vib_mm_s | 0.1463 | 0.0244 | true |
| integrated | rail_tunnel_building_coupled | tunnel_disp_mm | 0.0616 | 0.0145 | true |
| integrated | rail_tunnel_building_coupled | track_disp_mm | 0.0569 | 0.0100 | true |
| integrated | rail_tunnel_building_coupled | equilibrium_residual | 0.0190 | 0.0060 | true |

- max_lf_rel_err: `0.1463`
- max_gnn_rel_err: `0.0244`
- max_gnn_non_residual_err: `0.0244`
- max_gnn_residual_abs: `0.0060`
- improved_ratio: `100.00%`
- acceptance_rel_err: `0.0500`
- acceptance_abs_residual: `0.0100`
- pass: `true`
