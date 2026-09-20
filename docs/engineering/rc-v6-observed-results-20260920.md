# v6 full-path residual observations: completed, secant retained

Frozen source `49924c039af03df28ad208331e2812efe553ad04` completed all 90 comparisons and 360 full paths. The frozen campaign auditor verified the original history tolerances, complete roster, five-group exclusions, policy/source/model/request identities, costs and observation coverage. Both candidates remain slower than secant; no policy is promoted and no reserved case is executed.

| Ridge | Instrumented learned/secant path-time score | Smaller initial residual | Larger initial residual |
| --- | ---: | ---: | ---: |
| 10,000 | 1.126772112 | 96 | 201 |
| 1,000,000 | 1.118387498 | 84 | 213 |

Scores are equal-case means of within-case equal-repeat measured ratios, including the static gate and observation costs. They measure the instrumented policy. Comparison with the older uninstrumented campaign is not a causal estimate of instrumentation overhead or a cross-revision speedup claim.

## What the observations add

All 594 actual proposals were paired with secant on that proposal arm's own accepted parent. The observations cover target indices 1–11, nine development cases and 99 unique case/target pairs (198 case/target/ridge pairs). Three repetitions produce 594 rows; these are not independent structures or independent experiments. There were also 486 abstentions, with no fictitious proposal observation assigned to them.

Learned initial residuals are smaller in 180 rows and larger in 414, with no equal rows. Secant passes the initial residual gate while the proposal fails in 72 rows; the reverse occurs in zero rows. This replaces the narrower earlier observation that all 60 early common-parent rows were worse: later proposal histories contain some residual improvements. It does not invalidate that earlier subset or establish that residual improvement saves Newton work.

The two seeds share a parent within each observation. Independent secant and learned full paths may subsequently have different accepted parents, so their iteration differences cannot be attributed solely to this local residual comparison. The observation does not execute a residual-selected policy, and no online gate has been validated.

## Full costs and checks

- 4,680 nonlinear core calls, 24,147 Newton iterations and 24,147 linear solves.
- 1,188 additional full residual/tangent assemblies, counted separately from nonlinear core calls and Newton dispatches.
- Observation invocation time totals 30.236794912 seconds, included in path wall time. Persistence and other path overhead remain in full path time.
- Thirty selection fits total 0.704467379 seconds; the separate metadata fit takes 0.026045556 seconds. Historical label generation remains separately reported in the summary.
- Whole process wall time is 1,560.615787640 seconds. Selection and driver timing scopes are recorded separately.
- All observation parent/target/seed bindings, observation coverage and added work reconcile with the complete campaign auditor. No observation failure or incomplete path received speed credit.

The later reporting helper from `cda872e37` ran without fits or solves against the frozen campaign dependencies. Its exact source hash and result hash are preserved. Inventory creation and reread verified 36,204 files totaling 1,988,252,219 bytes, including 6,071 frozen source files. Packet inventory SHA-256: `29a6673c8624042cbcec7fe2cba3c2a5660e5361f033d202c44109de213b3b45`.

The first inventory-builder attempt rejected a tracked nested file named `inventory.json`; the corrected guard only reserves the packet-root inventory filenames. The failed script is retained and hashed. Numerical output and solver tolerances were not changed or rerun.

The practical next question is whether any prespecified, cheaper decision rule can preserve good secant starts and improve full-path cost. This dataset supplies development evidence for that question; it does not authorize a residual-based gate or prove a net learning benefit. Independent physical verification, public-data admission, licensing, broader capability and release requirements remain open.

Exact packet paths, source identities, costs, artifact hashes and per-ridge counts are in [the summary](rc-v6-observed-results-20260920.summary.json). The separate hosted checks are described in [the source receipt](hosted-49924-terminal-20260920.md).
