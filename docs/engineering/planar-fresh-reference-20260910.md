# Fresh OpenSees reference execution and horizontal equilibrium

The original OpenSees driver at product source `8dea62f1efb4dd3f5f45f51abf313b323af88b35`
now executes in a fresh local process. Official PyPI wheels for OpenSeesPy and
OpenSeesPyLinux **3.7.1.2** match the repository's exact pinned SHA-256 values;
the runtime reports **3.7.1**. Packages are extracted into a separate temporary
location and remain outside the repository. The current
[package declaration](https://pypi.org/project/openseespy/3.7.1.2/) allows internal
use and distinguishes commercial redistribution; no redistribution or legal
approval is inferred here.

All **17 stored external values** for the member-feature and prescribed-settlement
cases match this new execution exactly. Fresh current-product helper execution
again passes 15 comparisons and fails the same two `support_N1_UX_N` metrics.
All 595 recorded product source files retain their hashes throughout the check.
The original driver, raw stdout/stderr, wheel metadata/hashes, commands, current
product results and comparison audit are retained. Other outputs of the full
OpenSees driver are stored, but this observation audits only these two cases;
CalculiX and the complete external technical receipt are not refreshed.

## What the reaction difference represents

Both source models have horizontal initial chords, zero horizontal distributed
load and self-weight, and only N1 constrained in UX. N2 is horizontally free.
The global horizontal force equation therefore independently requires
`R_N1_X + F_N2_X = 0`. The external `nodeReaction` at the free N2 UX DOF is an
unbalanced nodal residual; it is not another physical support.

| Case | Applied FX (N) | External support-only balance error (N) | Product balance error (N) |
| --- | ---: | ---: | ---: |
| Member feature | 0 | 4.96422719988357e-7 | -1.3753172320614404e-12 |
| Settlement | 1000 | 3.63124513569346e-7 | -1.1368683772161603e-12 |

An 80-digit Decimal sum of the original binary64 values shows that adding the
external free-DOF residual cancels these external support-only errors: exactly
zero for member feature and about -1.69e-14 N for settlement. Thus the current
product's two horizontal reactions satisfy this independent global statics check
more closely. This conclusion concerns those forces and supported input models;
it does not validate all displacements, constitutive laws or solver families.

The original external convergence threshold is `NormUnbalance = 1e-9 kN`, or
`1e-6 N`. The unchanged comparison uses absolute and relative tolerances of
`1e-10` with a minimum scale of one, giving about `2e-10 N` for the zero-force
case and `1.001e-7 N` for the 1000 N case. The original reference's convergence
criterion admits residuals larger than either comparison budget. Agreement with
those rounded reference reactions is therefore not a sufficient accuracy oracle
at the comparison's precision. This observation does not change that comparison
or relabel its failed result as passed.

## Bounded stricter-convergence diagnostic

Three separately declared fresh executions extract exactly the two original
model blocks, preserve the four analyze calls per case and iteration limit 80,
and record each call's code, load factor, test norms and free horizontal residual.
The instrumented `1e-9 kN` baseline reproduces both complete original case
payloads exactly.

At both tighter diagnostic thresholds, **1e-12 and 1e-14 kN**, all analyze calls
return **-3** after reaching the convergence limit. The scripts themselves exit
zero, but the load factor remains zero after failed/reverted attempts. Their
zero final reactions are therefore excluded from physical comparisons. The
original four-call loop is retained: after failure, later calls attempt the same
first target again; they are not four completed load steps.

There are 24 diagnostic analyze calls: eight baseline successes and 16 failed
calls. The failed test reports a counter of 81 while its warning says 80
iterations; that counter is retained without pretending it is an independently
verified total Newton/linear-work count. For example, the member-feature failed
first step reports a residual norm about `3.3065e-10 kN`, above the stricter
threshold. Tightening this setting alone did not produce a more accurate accepted
reference. All failed output and stderr remain in the packet.

## Added physical regressions and limits

[Five public-path statics regressions](../../tests/test_bounded_planar_horizontal_equilibrium.py)
exercise the original member-feature zero-horizontal-load case, positive and
negative 1000 N loads with offsets/releases, and positive/negative 1000 N loads
with prescribed settlement. They verify the known constraint/load assumptions,
source-bound canonical execution, all four committed steps, exact engineering
recovery and checkpoint replay, then compare support force against global
statics using the unchanged comparison tolerance. They do not copy external
rounded reference values into an expected answer.

These five cases plus the 31 existing independent Decimal kinematics cases pass
**36 tests in 7.05 s**. Ruff, formatting and diff checks pass. The first test
invocation fails during collection because Python resolves the original checkout
instead of this worktree. Explicit `PYTHONPATH=src` fixes the test environment;
no numerical test ran in that first attempt. This error remains recorded.

The packet contains **62 files / 242,356,950 bytes** at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-opensees-reference._42rebm3`. Every file is inventoried and reread after the execution PIDs disappear.
Inventory SHA-256: `eef59d4444dadb040879684ca7c30d5a109f84a0cd78ae2e8b63969ac60df764`.
The [machine summary](planar-fresh-reference-20260910.summary.json) binds the
fresh runtime, original comparisons, exact stored-reference match, statics audit,
failed diagnostic calls, focused tests and seal.

The two existing external comparisons remain failed. This slice supplies fresh
local external execution and a statics regression, not independent operator or
hardware validation, a full new receipt, Verification Level 2, CI acceptance or
release approval. A reference capable of supporting the requested comparison
precision still needs authoritative verification. Protected receipts and fixed
tolerances remain unchanged; the complete roadmap continues.
