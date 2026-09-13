# Attempt-bound nonlinear failure diagnostic transport

`execution/nonlinear_failure_diagnostic.py` adds an isolated transport contract
for blocked corotational results. It preserves original result bytes in base64,
their byte length and SHA-256, the core canonical result hash, and an exact
job/request/attempt/source-revision/input/configuration binding. The validator
requires that expected binding as a separate argument. A future service caller
must derive it from its authorized claim and validated request, not copy it from
the submitted diagnostic. This module does not yet derive or authenticate a claim.

Both outer and embedded JSON use the existing bounded strict decoder, including
duplicate-key rejection. The core detached result validator checks the embedded
source before the diagnostic-specific rules apply. Only blocked corotational
results with empty accepted numerical rows, no checkpoint, no engineering
ResultIR and exact blocked authority axes are allowed. The wrapper grants only
diagnostic authority, not numerical, design, release or external-validation credit.

Observed-path validation checks exact nonnegative integer counts, configured
target order, attempted count versus step records, committed and history totals,
replayed plus new attempts, and commit/rollback dispositions. Unknown observed
work remains null. A recorded false rollback result remains false; it is useful
failure information and must not disappear merely because it is unfavorable.
All-committed paths can still be blocked by later recovery/validation gates.

The tests use an actual fresh public planar Newton failure with retained history
rows and an actual successful public solve that cannot be packaged as a failure.
They check original-byte roundtrip, cross-job/request/attempt/source rejection,
Boolean-integer confusion, rehashed contradictory counts and targets, altered
identity/authority, and ambiguous embedded JSON. The focused diagnostic module
and existing public sparse integration module passed 54 tests in 28.01 seconds;
Ruff and formatting checks passed. These are software-contract checks, not
independent physical validation or proof of durable publication.

The subsequent [durable diagnostic integration](durable-failure-diagnostics-20260913.md)
connects the local nonlinear worker, atomic failed transition and tenant-authorized
original-byte retrieval. That integration found no source-revision field in job
request v1, so the binding now permits null for that explicitly unavailable value.
Detailed Workbench projection remains open. Job view v1's prohibition on failed
result/evidence publication remains unchanged. The transport and storage checks
do not complete the failure-cost workflow or the broader roadmap.
