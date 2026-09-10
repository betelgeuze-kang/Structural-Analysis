# RC alternatives from the same accepted parent

The [original step-work observation](rc-step-work-observation-20260910.md)
found that every lower-iteration learned step had a different origin from
the corresponding secant step. Those observations cannot directly label which
action would have been cheaper from one executable state.

`benchmark_rc_control_seed_paths` now accepts paired `parent_checkpoint_bytes`
and `accepted_context` arguments. Both are required for this experimental mode.
It restores a canonical native checkpoint and uses the complete accepted
coordinate prefix to run **one original target** through reference, secant and
the supplied proposal, followed by a fresh reference. The default complete-path
mode is unchanged. No policy is fitted by this benchmark.

## Origin and execution contract

Before creating output, the runner checks the native checkpoint integrity,
problem identity, control DOF, original target index, prefix dimensions and
finite values, source-request reversal budget, native step index, latest free
coordinates and any supplied material snapshot. Retained coordinates preserve
their native high/low representation. For binary64 checkpoints, the supplied
solver coordinates are forward-scaled to physical rotations for exact identity
checking; an inverse approximation or a new tolerance is not introduced.

The supplied parent already includes any constant-load preload. The compiled
constant load remains active, and the preload is not executed a second time.
The existing proposal validation, material capture, seeded solve, exact rollback,
fallback and result recovery remain in use. A proposal may abstain to secant.
An unknown numerical outcome or mutation of the native origin stops scheduling
before the next arm, leaving the failed arm and a scheduling-stop record.

Each arm records its numerical attempts, work, capture/inference/recovery and
I/O time. Four arms have a conservative six-call numerical bound: two unseeded
references plus a possible seeded attempt and fallback for each other arm.
Compilation, origin validation and input I/O are part of the parent comparison
cost. This does **not** include the historical cost of reaching the supplied
parent, generating old labels, or fitting the supplied policy.

## Evidence boundary

The output uses separate parent-step path and comparison schemas. It preserves
the full original request, selected source index, exact supplied parent/context
artifacts and parent hash. Comparisons report `step_response_pass`, never
`full_history_pass`; the full-path runtime selector explicitly rejects this
schema. One successful target cannot establish complete-path speedup.

Prefix reachability and original source-file authentication remain unverified
by this API. Earlier supplied coordinates are checked structurally, but are not
reexecuted. A source-bound experiment must authenticate the entire prefix and
native parent against original records. The benchmark grants no causal training
dataset admission, independent validation, performance improvement or design
approval. A later whole-path evaluation is still necessary before adopting a
strategy selected from local step comparisons.

## Focused verification

The new tests first execute original three-target nonlinear paths, then restore
their actual third-step parent and complete prefix. They cover binary64 and
retained twofold arithmetic with constant preload and direction reversals.
All four replay arms receive identical parent bytes and prefixes. Their secant
accepted checkpoint and trial assembly reproduce the original secant result.
These are small authored regression examples, not the 242-target research cases
or external physical validation.

Additional cases reject mismatched or missing origins before output, stop on
unknown numerical work, retain fallback behavior for invalid proposals, and
reproduce secant exactly when the proposal abstains. The test module is included
in the independent development-contract CI job. Full repository/external gates
remain unchanged.

Local verification completed with **118 passing tests in 120.27 seconds**:
the 22 new parent-step cases plus the existing warm-start, runtime-selection
and repository-workflow contract modules. Ruff, scoped mypy on the two changed
runtime modules, and whitespace checks passed. The initial test attempt exposed
an incorrect binary64 coordinate comparison and an insufficient reversal budget
in the constant-preload fixture; both were corrected without changing numerical
tolerances or original solver results.

The preceding source `a65db4a56fce6e1550ea4c14c3c20149be7e2d73` has a successful
hosted development-contract job in
[run 34445399532](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34445399532).
Its four full-test shards failed at current-source evidence materialization and
skipped actual suite execution. That run does not test this new parent-step code.

The separate [48-path counterbalanced study](rc-counterbalanced-runtime-20260910.md)
uses its previously frozen source. This change does not alter its in-flight
code, inputs or audit process. Its completion and audit must be checked separately.
