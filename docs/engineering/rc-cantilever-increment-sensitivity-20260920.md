# Plastic cantilever increment sensitivity: 8 mm versus 4 mm

Source `f8986dd16b0e14b10ef24ea992753324a96ffad7`. A separate predeclared
60-target request halves the preceding 8 mm increments to 4 mm, with the same
0 -> -48 -> +48 -> -48 mm extrema, model, 600 kN compression, retained arithmetic,
terminal polishing and tolerances. This study does not change production code.

## Full-history gate still matters

The initial baseline benchmark completed all 60 targets in reference, secant,
identical-secant proposal and fresh reference (244 steps including preloads).
Reference/fresh repetition was exact and all work was reported. Secant/proposal
each fail one full-history field at target index 57: M1 local end-j MZ is
1.0788912473228476e-10 N m versus reference 2.6221634460354374e-12 N m.
Difference 1.0526696128624933e-10 exceeds the existing allowed
1.0000000107889125e-10 N m. The criterion is unchanged. Reuse execution and
second repetition were not performed; paired speed ratio remains null.
The failure receipt records 18.032750081 s benchmark wall time and binds the
original comparison bytes with SHA-256
`7080ae47abcb590cfd60cc39f5eb5d4c824eb7f71a77673d0bd3dc6d7537ebab`.

## Reference-only sensitivity at common chronological targets

A separate audit compares completed reference paths, not the rejected seed
comparison. Each of the 30 coarse target occurrences matches fine index 2*i+1,
with exact requested-coordinate equality, committed-state checks and per-file
hashes. Repeated coordinates on different branches are not mixed. The reported
normalized difference divides the maximum absolute difference by the maximum
absolute fine-path value in that response group at the 30 common targets.
This is descriptive, with no newly chosen acceptance threshold.

| Response | Maximum absolute difference | Fine-peak-normalized difference |
|---|---:|---:|
| Base horizontal reaction | 1.13687e-13 kN | 1.89478e-16 |
| Base transverse reaction | 2.59842381 kN | 1.35790% |
| Base moment | 7.79527143 kN m | 1.35790% |
| Tip axial displacement | 8.60059e-5 m | 1.88732% |
| Tip rotation | 0.000331761 rad | 1.14658% |
| Concrete tensile damage | 0.05616099 | 5.61611% |
| Accumulated steel plastic strain | 8.88982e-5 | 0.95304% |

Compressive damage remains zero. The transverse reaction witness is coarse
index 25/fine 51: 129.1436253 versus 131.7420491 kN. The tensile-damage witness
is M1 integration point 1, fiber 0, coarse index 13/fine 27: 0.6904483443 versus
0.7466093342. These results show increment sensitivity; neither 4 mm nor 8 mm
is established as converged or physically accurate. A two-grid comparison does
not determine convergence order or a mesh-independent solution. The earlier
byte-exact reuse observation remains valid only within its fixed request.

Evidence packet:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-cantilever-halfstep-reuse-5tp77h3_`.
It contains the plan, inputs, log, failure receipt, original results and saved
sensitivity audit. All 1,484 inventory file hashes were re-read. External inventory
SHA-256: `1972b10e03ceb1dfbc300e1a23a52209209ff73be8d07d3968e404678fd78e1e`.
The coarse evidence source is the packet referenced by
`rc-cantilever-plastic-reversal-reuse-20260920.md`.
