# White-box Validation Report

| Case | Metric | LF rel err | GNN rel err | Improved |
|---|---:|---:|---:|---:|
| cantilever_2d | disp_max_mm | 0.0403 | 0.0040 | true |
| cantilever_2d | stress_max_mpa | 0.0546 | 0.0067 | true |
| cantilever_2d | reaction_kN | 0.0120 | 0.0009 | true |
| cantilever_2d | equilibrium_residual | 0.0180 | 0.0040 | true |
| one_story_rahmen | disp_max_mm | 0.0465 | 0.0058 | true |
| one_story_rahmen | stress_max_mpa | 0.0628 | 0.0094 | true |
| one_story_rahmen | reaction_kN | 0.0152 | 0.0013 | true |
| one_story_rahmen | equilibrium_residual | 0.0220 | 0.0050 | true |
| truss_3d | disp_max_mm | 0.0577 | 0.0038 | true |
| truss_3d | stress_max_mpa | 0.0493 | 0.0077 | true |
| truss_3d | reaction_kN | 0.0142 | 0.0007 | true |
| truss_3d | equilibrium_residual | 0.0150 | 0.0030 | true |

- max_lf_rel_err: `0.0628`
- max_gnn_rel_err: `0.0094`
- improved_ratio: `100.00%`
- acceptance_rel_err: `0.0300`
- pass: `true`
