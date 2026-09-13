# Concrete layer sensitivity of the generated two-story model

Source `3e2cc1dba5c6dac1b12eb1badc9b6df09337b847`. The earlier generated portal
fixture uses **two concrete layers**; this is not the section helper's default
of twelve. `make_rectangular_stateful_rc_fiber_section` places one concrete fiber
at each layer midpoint, with its full layer area. For a rectangle divided into
N equal layers this reproduces area, while the discrete concrete second moment
is `(1 - 1/N**2)` times `width * depth**3 / 12`.

Direct calculation from the generated fibers, with the same lumped steel layers
and declared elastic moduli, gives:

| Concrete layers | Concrete second-moment ratio | Gross concrete plus lumped steel initial EI ratio |
| ---: | ---: | ---: |
| 2 | 0.750000 | 0.787986 |
| 4 | 0.937500 | 0.946996 |
| 8 | 0.984375 | 0.986749 |
| 16 | 0.996094 | 0.996687 |
| 32 | 0.999023 | 0.999172 |

The denominator uses the analytic gross rectangle for concrete and exactly the
same lumped steel convention as the existing model. It is not a cracked-section,
effective-stiffness or independent physical reference. No displaced-concrete
correction or constitutive change is introduced. All concrete areas remain
0.24 m²; the second-moment formula agrees within 1e-12 in the direct calculation.

Four new public API runs were frozen before execution: 4, 8, 16 and 32 layers,
dense backend, one fresh worker per case. The original two-story topology,
material laws, steel arrangement, 30x proportional loads, four load targets,
residual/increment tolerances and iteration limits remain unchanged. There are
no retries, timing repetitions or outcome-based exclusions.

| Layers | Last committed factor | Failed factor | Attempted steps | History rows | API workload s |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 4 | 0.5 | 0.75 | 3 | 19 | 4.558237 |
| 8 | 0.75 | 1.0 | 4 | 24 | 6.145115 |
| 16 | 0.75 | 1.0 | 4 | 24 | 9.512874 |
| 32 | 0.75 | 1.0 | 4 | 27 | 16.478146 |

The original two-layer observation failed at factor 0.5. Changing discretization
therefore changes the attained range under the same control and tolerances.
This is sensitivity evidence, not nonlinear mesh convergence: none of the four
new paths completes, and matching last attained load factors does not establish
matching displacements, forces or material histories. The next comparison needs
those responses at the same predeclared accepted targets and explicit refinement
criteria. The coarse fixture remains useful for software tests but cannot alone
support physical calibration or capacity conclusions.

Every new run retains contract-valid failure diagnostics and exact rollback;
none exposes an accepted engineering result or resumable public checkpoint.
History rows are not complete assembly/solve counts, and speed ratios remain
null. The enclosing experiment takes 45.563946 s; no learned model is involved.

The separate audit checks 461 frozen/current source files, 32 artifact identities,
the original input hash and every model difference: only layer count plus model
identity/provenance fields changed. The [machine receipt](planar-section-refinement-20260914.summary.json)
contains geometry and all failed-path observations. The immutable packet at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-planar-section-refinement-w_v5cyvl`
contains the protocol, generator, sources, workers and audit. Inventory covers
514 files / 9,612,224 bytes, SHA-256
`e4ba94fdf25aafd20597f712953dd990045623c7cd239b4cab9eab0ac6cbd631`.
An initial import probe without repository PYTHONPATH failed before any model or
solver execution; the recorded campaign uses explicit `PYTHONPATH=src`.
