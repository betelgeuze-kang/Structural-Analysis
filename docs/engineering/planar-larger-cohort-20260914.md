# Larger connected planar backend cohort

This cohort extends the earlier six-member/small-equation observations with two
larger generated models admitted by the existing public planar load-control
path. It does not extend public limits or introduce independent project data.

| Authored case | Nodes | Members | Free equations |
| --- | ---: | ---: | ---: |
| Three stories, two bays | 12 | 15 | 27 |
| Four stories, three bays | 20 | 28 | 48 |

The original portal example supplies material laws, section geometry, loads and
input conventions. Bays are 4 m and stories 3 m; bases are fixed and the original
nominal load vector is placed at the roof-right node. Each section uses twelve
concrete layers, the low-level builder's default count, rather than the earlier
two-layer research input. This is not proof of quadrature convergence for these
new geometries. Model IDs and authored provenance distinguish the generated
cases; they are not separate measured buildings or licensed external experiments.

The pre-run protocol fixes four proportional load steps, residual tolerance
1e-10, increment tolerance 1e-12 and maximum 40 iterations. Dense NumPy solve and
SciPy sparse spsolve each run twice per case in rotated order, using fresh worker
processes and no warmups: eight scheduled observations. Each worker has the same
180 s timeout. Failures are retained without outcome-based retries, changed
loads or relaxed acceptance gates. No learned policy or training admission is
part of this cohort.

The benchmark preserves source snapshots, input identities, all original result,
validation and history artifacts, worker resource records and parent validation
costs. Same-input backend comparisons require terminal and full-history agreement
at the declared absolute/relative 1e-9 tolerances, including material states.
Exact repeat identities are evaluated within each case/backend. Numerical
agreement is distinct from independent physical validation or a speed benefit.

## Executed results

Source revision: `99c362c29dc608064428c6169330e9552cb45d84`.
All eight workers enter the API, complete the path and pass their retained
artifact/resource contracts. All four cross-backend terminal/full-history
comparisons pass, and all four within-case/backend repetition pairs have exact
retained artifact identity. The audit checks 461 source-file identities and 80
worker artifact identities, then recomputes the internal comparisons.

No steel accumulated plastic strain or concrete tensile/compressive damage is
observed in any of the eight paths; material dissipation is zero. These exercise
the nonlinear geometric/material solver in an undamaged response range. They
must not be presented as inelastic damage/yield performance evidence.

| Case | Backend | Median API workload | Median launch/exit plus parent validation |
| --- | --- | ---: | ---: |
| 3 stories / 2 bays | Dense | 16.948520 s | 23.089946 s |
| 3 stories / 2 bays | spsolve | 16.946365 s | 23.007236 s |
| 4 stories / 3 bays | Dense | 30.964792 s | 40.424168 s |
| 4 stories / 3 bays | spsolve | 31.180861 s | 40.580015 s |

Sparse/dense workload ratios are 0.999872841 and 1.006977878 respectively. The
first is a negligible observed difference; the second is about 0.70% slower for
sparse. Only two observations per case/backend are available, so neither a
statistically established performance difference nor general sparse benefit is
claimed. The comparison does not train or evaluate an AI policy.

Parent detached-bundle validation medians are approximately 4.15–4.20 s for the
smaller case and 7.45–7.49 s for the larger case. These are separate from the
worker launch-to-exit interval, and include history reassembly. The combined
column above is the median of each observation's summed intervals, not an
addition of unrelated medians. Other experiment setup/comparison work is not
included in that column. The reported complete experiment interval is
256.909725 s; this turn's separate audit is outside it. Worker CPU and peak RSS
measurements are retained in the summary.

These results broaden the exercised connectivity/equation range while leaving
independent physics, quadrature convergence, inelastic performance and larger
sparse regimes open. Passing same-model numerical comparisons do not establish
that the authored structural model is physically correct.

## Reproduction and retained packet

The runner, pre-run protocol, both canonical-source input models, adapter/compiler
preflight observations, frozen source package, all eight worker artifacts,
comparison report and recomputing auditor are retained at:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-planar-larger-cohort-cgh0zfaw`

753 payload files, 61,783,669 bytes; inventory SHA-256:
`024018ef65e376b501fbaa45bff3b117ba0644a87190cb1726cb8d5006dc2086`.
The runner creates a fresh packet and writes its location to
`/tmp/structural-planar-larger-cohort-root.txt`; the auditor verifies retained
source/input/artifact identities and recomputes comparisons without admitting
external data or training. The adjacent summary retains failed-outcome handling,
full comparison records, material observations and cost scope.
