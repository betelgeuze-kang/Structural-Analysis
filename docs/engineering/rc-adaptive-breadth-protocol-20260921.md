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
