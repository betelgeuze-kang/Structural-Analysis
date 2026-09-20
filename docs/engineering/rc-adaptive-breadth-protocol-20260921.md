# Reusable adaptive recovery breadth campaign

The repository runner `scripts/run_rc_adaptive_continuation_campaign.py` fixes
8 synthetic L-frame conditions: geometries (2 m, 1.5 m) and (3 m, 2.5 m), each
with amplitudes 20, 40, 60 and 80 mm. There are two canonical models, not eight
independent projects. Requests use N3 UY targets `(-A/2, -A, A/2)` with constant
N3 FY = -25 kN. All runs use binary64 and explicit terminal polishing. These are
numerical-model probes, not independently validated engineering operating limits.

Both strategies trigger only after a known rollback-safe failure at any requested
target. Compare fixed sixteen-stage recovery with bounded adaptive recovery;
no upfront-versus-failure trigger difference is mixed into this comparison.
Two repetitions reverse mode and arm order: 32 comparisons / 128 paths, with
fresh reference in every comparison. Native and history tolerances are unchanged.
The conservative whole-campaign bound is 4,736 native calls, including preload,
ordinary retries and all internal trials. The underlying strategy retains its
64-trial and minimum-increment limits.

Run `--preflight-only` to print the plan hash, case/path counts and call bound
without creating outputs or invoking the solver. A real run requires a new output
directory and writes the complete canonical plan before solving. Each attempted
comparison has a started record and immutable outcome record. Exceptions remain
unknown-work rows; known incomplete paths are distinct from orchestration errors.
`observations_complete=true` and process exit zero never mean all paths passed or
independent physics/speedup was qualified. All failed original attempts remain.

After freezing committed source, archive the runner, engine and examples and run
from that snapshot. Preserve the source archive, plan, all raw comparison/trial
artifacts, outcome and execution metadata. Separately audit report/path/native
hashes, model/request/profile binding, parent state preservation, all work, repeated
complete histories/checkpoints and fixed/adaptive complete-history agreement.
Only compute a qualified adaptive/fixed timing ratio when both modes complete,
match histories and pass fresh-reference comparisons in both repetitions, with
known work and matching repeated complete histories. Otherwise retain null.

Five orchestration tests exercise the fixed roster/budget, balanced ordering,
known incomplete paths, unknown-work retention, revision validation and preflight.
They use explicitly synthetic reports for orchestration and are not numerical
validation. Those tests and repository workflow/strict-YAML checks pass 27 tests.
The development-contract CI list includes this runner's test module; the required
full-suite gate is unchanged. No policy promotion, independent project provenance,
physical qualification or learned gain is claimed by this campaign.

## Comparison-level measured cost

New runner outcomes include `comparison_cost` on every returned or raised row.
Wall and process CPU clocks span the benchmark call and classification of its
return/exception. Benchmark-internal result writing is included; the outer started
marker, row outcome write and final campaign write are outside each row's clock.
The existing parent clock includes row writes but excludes case preparation,
plan writing and the final campaign write. These clocks are nested, not additive.

Caught exceptions retain elapsed cost and `unknown_work=true`; a known elapsed
time does not reconstruct missing native work or qualify an incomplete path.
Process termination before a row returns still leaves only its started marker,
so complete cost is not inferred for killed processes. The independent auditor
rejects partially present timing, invalid types/values, unknown scopes, or summed
comparison wall time exceeding its enclosing sequential campaign time. Earlier
packets without row timing remain readable and are not assigned invented costs.
No original execution clock is independently authenticated, and startup, transport
and browser review remain outside these measurements.

Verification: 29 audit/runner tests passed, including a real short/40 mm campaign,
injected exceptions with retained elapsed cost, partial timing rejection and
separate audit timing. Ruff and whitespace checks passed. These checks establish
the accounting contract, not a fresh eight-condition runtime performance result.
