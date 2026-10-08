# Common current-layout pool admission preserves physical control and preload

The first price-order correction left a concrete route gap: the combined
comparison and standalone learned-order execution still bypassed its physical
control/preload comparator. Their unchanged legacy descriptor contexts could
admit declaration permutations or preload-name remapping together with a
distinct geometry/section alternative. This followup extends that same
comparator to every current model pool entering `_run_layout_search()`.

Before the extension, 16 new no-solve counterexamples were observed on the
first-turn local source, SHA-256
`ac1fa9ede1b3111c183cd4023e308a0425468fd8086da650c5b1fc2199f37bfb`.
Four actual authored changes were supplied to each of the combined comparison,
full learned-order, cost-pruned learned-order and prefix-staged learned-order
wrappers: v1 control declaration permutation with section change, v1 control
permutation with geometry change, v2 preload-name remapping with section change,
and v3 control permutation with section change. Existing descriptor/compiler
admission succeeded, contexts remained equal, and physical model identities
differed. Every call reached one actual policy prediction and the first output
directory boundary. That boundary was intercepted before creation; solver,
fit, label-generation and artifact-writing calls were forbidden and observed
zero calls. These observations establish an input-admission gap only.

The production change removes the policy-dependent bypass in the common pool
loop. After actual descriptor compilation, distinct-identity checks and the
existing fixed-context checks, every baseline/candidate binding is compared
before preparing its quantity row, predicting, creating output or executing a
reference path. The binding retains the same canonical XY node rank, control
component and exact constant-load values. Equal fixed context supplies the
topology correspondence; canonical rank permits the admitted geometry changes
and translations. Declaration changes and node renaming pass when they preserve
the controlled and preloaded canonical slots. The existing helper and error
strings are retained. No descriptor, request, policy, output schema, context
hash rule, quantity/price calculation, budget or solver tolerance changes.

The common guard now covers standalone price order, standalone learned order
through its full/pruned/staged wrappers, and the combined two-arm comparison's
current pool before either arm can execute. It checks the complete pool even
when the pool contains more alternatives than the shortlist budget. The existing
v4 pin-roller learned-policy rejection remains in place. No new v4 learned
policy support is introduced.

`tests/test_rc_layout_current_pool_preflight.py` passed **40 checks in
11.69 seconds** on Python 3.10.12 / pytest 9.0.2. Rejection tests prove zero
prediction/output/solver/fit/artifact calls. Positive cases cover retained v1
geometry/declaration changes, v2 geometry/translation/declaration changes and
v3 geometry/translation changes; they run real pure prediction, then stop at
the first output boundary before creating files. Model/request/descriptor,
policy and report bytes remain unchanged. The actual policy constructor and
`_training_cost()` validation are enabled in every test. V1 tests load the
retained fixture policy bytes unchanged and validate their retained report;
this does not replay the fixture or its numerical paths. V2/v3 tests construct
explicitly synthetic, correctly hashed policy/report admission inputs, with
complete array dimensions, zero weights and zero declared test work. These
synthetic contracts are not historical learning or label receipts, and no fit
is performed. Ruff 0.12.4 lint/format and `git diff --check` passed. The completed
29/41/30 checks and existing numerical fixtures/campaigns were not rerun.

The first-turn documents and receipts remain unchanged as prior evidence.
The new before/after receipt, pre-extension source snapshot and final changed
file hashes are under
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/pr-backlog-20260929/rc-readiness-goal-20261002/current-layout-pool/`.

Historical training compatibility remains unqualified. This check binds the
current baseline/candidate pool to itself; it does not bind that pool to the
historical training models behind an old policy. Dataset preparation, label
generation, fitting, and direct `RCControlLayoutPolicy.predict()` calls retain
their prior context contracts. They still need separate canonical-binding
compatibility evidence. The correction does not establish historical policy
fitness, independent physical accuracy, functional equivalence, commercial
savings, exact-final-commit hosted CI or release readiness.
