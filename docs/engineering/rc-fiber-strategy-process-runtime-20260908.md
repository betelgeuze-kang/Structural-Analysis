# Local isolated-strategy resource observation

The additional `fiber_frame_strategy_process_suite` experiment gives each strategy
its own fresh Python worker for every declared case, warmup and repetition. It
reuses the existing solver, guarded proposal and full selected-path verification
logic. A learned worker decodes one frozen policy and reuses that instance; it
does not collect training data, fit a policy or reset it between runs.

## Implementation and verification

Each worker persists its complete canonical checkpoints and trial assemblies.
The parent validates the input byte bindings, compiled problem/coordinate/config/
load-history bindings, ordered execution coverage and raw report/resource hashes.
It then compares every measured history with the reference using the existing
numerical comparison rules. Checkpoint ancestry must match the immediately prior
state. Local self-validation alone does not grant cross-worker comparison credit.

CPU/wall intervals distinguish compilation, warmup execution, measured execution
and full verification, reference-only baseline episode checks, and parent
comparison. Inclusive verified runs also include snapshot preparation. Nested
phase and material intervals must fit their enclosing intervals; unavailable
material metadata remains unavailable. Parent comparison is a subset of parent
orchestration CPU. Missing workers retain their expected rows and null complete
totals; valid resource observations of physically blocked workers retain attempted
costs. Independent worker peaks cannot be added or subtracted.

The reference worker's RSS includes its extra baseline episode checks. This
prevents a claim of equal-scope peak-memory advantage. RSS includes imports,
input processing and strategy-report persistence, using post-exec Linux `VmHWM`;
it is unavailable on platforms without a validated process-local measurement.
Input/report file I/O is the explicit bounded read/write scope, excluding
resource-sidecar, parent-manifest and combined-report persistence. Reads may use
cache and are not measurements of physical disk traffic. No GPU work is measured.

The legacy in-process comparator now passes detached canonical snapshots through
the same comparison implementation. Its comparison interval therefore includes
serialization and snapshot validation at this source version; old timing records
retain their original scopes. Numerical algorithms and tolerances are unchanged.

Focused verification before the fixed-source observation:

- Existing process/learning regressions: **59 passed in 123.61 seconds**.
- Existing actual two-step runtime cases: **2 passed in 69.35 seconds**.
- Final strategy contracts and CI ownership contracts: **107 passed in 2.20
  seconds**, including 73 strategy cases and 34 CI cases.
- The new process integration collected three physical label cases (six samples),
  fitted once, and ran one validation case with one warmup and one measured run
  in each of three fresh workers. All workers and the parent comparison passed.
  Its first test invocation had 42 passes and one test-only tuple/list equality
  failure. Normalizing that assertion and rereading the preserved artifacts
  produced 50 passing tests without additional fitting or numerical solves.
- Final transport, cost-subset, unavailable-metadata and typed ancestry negative
  tests: **60 passed in 2.41 seconds**, reusing those same artifacts with no new
  solver paths or training calls. Ruff and whitespace checks passed.

These are separate correctness runs with overlapping coverage, not performance
observations or a repository-wide test result. The process fixture artifacts are
retained under `/tmp/structural-strategy-process-nwxb6ywv/`. Later cost/ancestry
negative tests reuse those completed reports and rebind all outer hashes so they
exercise the inner contract rather than merely detecting changed bytes.

## Evidence limits

Source revisions and hashes establish explicit identities, not attestations.
This implementation does not supply independently grouped licensed training
data, independent solver/hardware validation, generalized acceleration, confirmed
construction savings, hosted full-suite acceptance or release approval. The
broader roadmap and the original dirty checkout remain separate.
