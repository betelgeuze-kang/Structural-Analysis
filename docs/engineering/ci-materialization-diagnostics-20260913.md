# Basic CI materialization failure diagnostics

At source `d8b22b206c0edcf66efe45b1a7c07390d9f43a7b`,
[CI run 34749003150](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34749003150)
failed before its quality gate. Job 103701978068 refreshed internal product replay,
then the license due-diligence builder exited 1 with
`external_code_to_code_product_replay_not_passed` and
`external_code_to_code_technical_receipt_not_ready`. The log does not expose
individual numerical mismatches; this observation cannot establish their cause.
This is the basic CI job, not the independent development-contract pytest job.
At readback the latter was cancelled for this source, while collection succeeded;
no new development-contract pass is inferred.

The basic workflow now retains the same four explicitly named failure-context
and receipt files as the repository Python shard workflow. Upload runs only after
materialization failure, retains data seven days and does not bypass any failure
or readiness check. Context identifies the workflow SHA, run, attempt and job,
and states that receipts may be tracked or partially rewritten. Upload is not
proof of receipt generation, fresh external execution or qualification.

Both workflows share parameterized contract coverage: exactly the allowed files,
failure-only conditions, unchanged fail-blocked behavior and no continue-on-error.
The tests execute both embedded context producers and verify their JSON identities
and non-qualification fields. The two affected modules pass 21 tests; Ruff and
whitespace checks pass. Hosted upload remains unobserved until a new failure run.
See the [source-bound observation](ci-materialization-diagnostics-20260913.json).

This closes missing basic-CI diagnostic retention, not the external comparison
failure, complete test execution, independent validation, or roadmap integration.
Protected checked-in receipts were not changed.
