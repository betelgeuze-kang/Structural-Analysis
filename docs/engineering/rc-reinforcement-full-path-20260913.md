# Full cyclic-path reinforcement comparison

Frozen numerical source `94302f49a974546efd050e0eb8564e87ef670f86` now
extends the three-target reinforcement regression to the existing 242-target
L-frame history, including two reversals and material memory. The original
model, solver tolerances, target sequence and synthetic price table are retained.
All 653 tracked source files were copied before execution and rehashed afterward.
The saved runner invokes the existing comparison CLI from that isolated source.

**The comparison is incomplete: two of three designs pass full verification.**
The failed candidate stays in the denominator and retains its quantities and work.

| Design | Full-path verification | Straight rebar, kg | Synthetic estimate | Maximum absolute fiber strain |
| --- | --- | ---: | ---: | ---: |
| Baseline: 4 + 4 bars, 0.000387 m² each | Pass, 242 targets | 85.06260 | 169.06260 | 0.0067335994 |
| Fewer bars: 3 + 3, same area | Pass, 242 targets | 63.79695 | 147.79695 | 0.0069487631 |
| Smaller bars: 4 + 4, 0.000300 m² each | Blocked at eighth attempt | 65.94000 | 149.94000 | Unavailable for the full path |

Gross concrete remains 0.84 m³ for each design. Member quantities independently
match the authored 2 m and 1.5 m lengths, total longitudinal steel area and
7,850 kg/m³ density. All estimates use the same declared concrete price of 100
per m³ and rebar price of one per kg. Prices are synthetic, with the existing
scoped exclusions; these are not real quotes or confirmed savings.

The baseline and fewer-bars design each start at epoch zero and complete a new
full-path reference verification. Their peak steel accumulated plastic strains
are 0.0097565363 and 0.0096823429; both exhibit concrete tensile damage close to
one. Thus the full observation exercises material nonlinearity, unlike the
earlier small-amplitude regression. Permissive fixture limits do not constitute
design-code or physical acceptance. The fewer-bars design is selected only under
those declared screens; its lower estimate does not establish feasible rebar
reduction or an optimum over a fully verified candidate pool.

The smaller-bars design accepts seven targets, then blocks at -0.0032 m with
`line_search_failed_to_reduce_residual`. Its separate verification also records
eight attempted steps. The last failed transition is uncommitted, retains the
exact parent checkpoint and reports immutable-parent/exact-rollback success.
This is numerical nonconvergence under this request, not proof of physical
collapse. The reported full-path performance remains unavailable. The CLI
returns exit code 2 and publishes `status=incomplete`, rather than discarding
the failed row or treating the selected candidate as full-study success.

Six numerical API entries account for **984 attempted steps and 3,924 known
Newton iterations/linear solves**, including both failed attempts and all fresh
verification work; unknown solver work is zero. This is one serial observation,
not a repeated timing benchmark or an AI comparison. No fitting occurred.

The separate saved-data auditor checks source and artifact bytes/hashes,
report identity, original targets, fresh verification result bindings, member
quantity arithmetic, common prices and accepted-history strain/plasticity peaks.
It also rereads the sealed inventory: 691 files, 184,980,037 bytes, inventory
SHA-256 `4a5b3ebdeb2fe6a5dc695ee3ce0f6303d6bcb848716e70380b7097e924422b0f`.
The raw directory is
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-reinforcement-full-f8hsry7m`.
The [summary](rc-reinforcement-full-path-20260913.json) retains per-phase costs
and the failed transition facts. Original numerical artifacts are local.

This adds an actual cyclic reinforcement pair and a retained failed alternative
to M2. It does not close independent physical validation, public-data admission,
learned net benefit, broader families, R1/R2, hosted acceptance or release gates.
Further solver-strategy experiments must keep this original failure and its
costs, and must identify any changed intermediate steps or numerical protocol.
