# Shared terminal polishing on the complete RC control path

This follow-up retains the failed unpolished observation at `707702f8825def701cf4a36cbdea57b747353770`.
It does not change the `1e-10` absolute / `1e-8` relative physical comparison rule.
At source `3f6c952d50a5a2a54ae4ce54968a3757db30e5c8`, the existing
`terminal_polishing=true` option is enabled for reference, secant and fresh
reference alike. The original two model files and all 242 requested targets are
unchanged. Six serial fresh processes, three for each geometry, alternate the
reference/secant order. Source files and inputs are copied and hash-bound before
any worker starts; worker imports resolve to the isolated source copy.

The option attempts one correction after ordinary residual and increment
convergence. It replaces the converged state only if the original residual and
increment gates still pass and the residual norm strictly improves. It retains
rejected attempts and exceptions in the original polishing record. The RC step
still rechecks control, equilibrium, immutable parent and solver/assembly binding
before commit. This is an existing Newton option, not a new material law or
recovery correction. Public defaults remain unchanged.

The reporter additionally records all mismatch counts grouped by physical
response field and the first 20 deterministic path/value/tolerance examples.
Only diagnostic storage is bounded; full-history comparison and mismatch counting
retain every value. Missing histories and structural differences remain failures.
The whole-study elapsed interval includes comparison and diagnostic traversal.

The original focused group passes 22 cases, including actual shared finishing
through every arm and retained extra linear-solve counts. The subsequent related
Newton/material/control/API/request/CI-registration selection passes 307 cases in
53.86 seconds. These overlap; they are not a full-repository Python suite. Ruff
and diff checks pass. No additional frontend application change is included.

## Preceding hosted frontend acceptance

At exact preceding head `2cdaf3c8c49a62072c65e15c48f5cec33d24536a`, the
[PR frontend job](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34313277654/job/102344149986),
[push frontend job](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34313275148/job/102344142699)
and [frontend-contracts job](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34313277668/job/102344150349)
all pass. The inspected PR log records 475 tests passed in 6.9 minutes, including
the delayed-original valid/tampered regressions. This confirms the earlier browser
loading follow-up on that head; it is not hosted acceptance of a later head.

The inspected full-pytest shard stops during preparation at internal license due
diligence with `legal_approval=False`, before repository test execution. That
external approval remains open. Current-main R1, separate R2, independent physical
validation, learned cyclic training and broader roadmap acceptance also remain
open. No merge, release or deployment is performed.


## Completed observation and remaining force mismatch

All six workers exit successfully and all 18 paths complete 242 targets. All
reference/fresh-reference histories are byte-exact, and each geometry/strategy's
three histories are identical. The source audit rechecks all 408 frozen files.
The original-record audit checks all 4,356 started/outcome/step records, report/path
hashes, own accepted-prefix contexts, parent chains and original commit gates.
There is no unknown execution work and no failed numerical attempt.

Total observed work is 4,356 core entries and 17,718 Newton/linear counts. Terminal
polishing is attempted 4,356 times, accepted 2,973 times, and performs 4,341 extra
assemblies and 2,973 extra linear solves, with no assembly/linear exceptions.
Those linear solves and all finishing time are already included in total work and
elapsed time; they must not be added again. The parent elapsed interval is 713.608
seconds and includes process startup and all six workers, excluding source staging.

| Geometry (m) | Reference median ± sample SD (s) | Secant median ± sample SD (s) | Reference / secant Newton-linear counts per path | Secant full-history pass |
| --- | --- | --- | --- | --- |
| 2.0 / 1.5 | 42.229 ± 0.210 | 30.815 ± 0.095 | 1,135 / 742 | 0 / 3 |
| 2.5 / 2.0 | 40.630 ± 0.406 | 30.184 ± 0.250 | 1,086 / 722 | 0 / 3 |

All six secant comparisons remain failed at unchanged tolerances. Their maximum
mixed-SI absolute differences are `2.718297764658928e-08` and
`1.0244548320770264e-08`, respectively. The base case retains 1,616 failing values
per repeat (1,076 member-force, 116 reaction and 424 section values); the longer
case retains 1,464 (949 member-force, 92 reaction and 423 section values). These
counts and the deterministic diagnostic examples reproduce exactly. Smaller
errors and shorter elapsed times do not establish accepted acceleration.

## Stored-data diagnostics, without changing accepted results

The section diagnostic recomputes each original force/moment from the retained
fiber stresses, areas and offsets using both `math.fsum` of the existing rounded
fiber forces and 80-digit decimal products/sums of the original binary64 inputs.
For the first reference/secant pair of each geometry, all 424 and 423 failing
section-moment comparisons remain under both alternatives. Maximum differences
from the original summed section values are below `3.5e-10` in the mixed force /
moment fields. This only diagnoses summation of fixed retained stresses; it does
not test a changed assembler or new material trajectory.

A separate diagnostic evaluates M2 curvature at all 726 integration points in
those four retained paths directly from the original binary64 nodal coordinates,
using the equivalent Hermite slope/rotation expression and 80-digit arithmetic.
The largest difference from the stored curvature is `1.3209545361124896e-17` per
metre. Many finite-coordinate states themselves have nonzero exact curvature:
576/579 base reference/secant points and 549/525 longer-geometry points. Replacing
only a dot product or summation cannot be assumed to restore an exactly rigid
state. These evaluations call neither Newton nor the material routines and do
not replace any accepted physical history or prove a solver repair.

The next work is to resolve numerical acceptance across displacement/curvature,
material response and recovered forces, with an explicit error budget and full
reference verification. The failed strict-tolerance observations remain the
baseline; no tolerance, force value or state is rounded/clamped to obtain a pass.
Cyclic learned training and independent project/geometry/history provenance remain
open. [Source-bound summary and raw inventory](rc-control-shared-polishing-20260909.summary.json).
