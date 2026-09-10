# Development tests independent of external receipt preparation

The Repository Python Tests workflow now has an additional
`pytest-development-contracts` job. It runs on every existing workflow event,
from the committed checkout, without depending on external receipt materialization
or another job. This provides hosted regression information while an external
comparison or its preparation is blocked. It does not establish qualification
and does not replace the complete repository suite.

The job runs 17 whole test modules covering RC control initialization and rollback,
learning/splits/history/SVD/model selection/runtime selection, measured inputs,
design/candidate search/cost, actual HTTP artifact delivery, original-record audit,
pinned official runtime identity and the separate local source-reference report.
There is no test-name filter or deselection. The local selection collects
**336 tests in 3.39 s**; this is collection evidence, not 336 passing executions.
These modules construct their own bounded numerical inputs or use committed
fixtures; the new job does not rebuild external qualification receipts or invoke
the local source-build comparison CLI.

The job uses the existing pinned Python/numerical dependencies and immutable
checkout/setup/upload action revisions. It has read-only contents permission,
no persisted checkout credentials and a 30-minute timeout. JUnit results upload
on failure as well as success, under a commit-specific artifact name. Missing
results warn when setup prevents pytest from running; they do not fabricate
passing test results. A failing pytest invocation still fails the job.

The existing collection job, all four full-suite shards, preparation commands,
pristine-ledger check, existing explicit deselections and required `pytest-full`
aggregate are unchanged. The aggregate continues to require `full_shards.result`
to equal `success`; success in the new diagnostic cannot override failed,
cancelled or skipped full shards. No branch-protection decision or readiness
threshold is changed.

## Local verification

The focused workflow/YAML/action-pin/source-boundary selection passes **23 tests
in 1.28 s**. The new contract checks job independence, the unfiltered module
selection, read-only permissions, result retention, and preservation of the
full-shard aggregate. Ruff, `git diff --check` and the hosted/self-hosted runner
policy check pass.

Two initial runs each had 22 passes and one failure in an existing action-pin
count assertion: the test expected two checkout/setup steps and no artifact
upload in this workflow. Those expectations now account for the additional job
and its pinned upload action; the action revisions were not relaxed.

Raw local logs are `/tmp/rc-independent-ci-contract-tests.log`,
`/tmp/rc-independent-ci-contract-tests-final.log`,
`/tmp/rc-independent-ci-contract-tests-final2.log` and
`/tmp/rc-independent-ci-collection.log`. Hosted execution of the new job is still
pending at this documentation revision. Full-suite completion remains unproved.

The ongoing [secant-abstention experiment](rc-secant-abstention-20260910.md)
continues from its frozen 3d4ecef4b source, unaffected by these workflow edits.
Its first completed fold has 242 abstentions and identical secant/proposal
response histories, final checkpoint and all 242 original step-file pairs.
Its single proposal/secant path-time ratio is 1.0219789045931427. That partial,
fixed-order observation is not a repeated performance conclusion; the remaining
folds and complete original-state audit remain pending. The pairwise byte check
is retained under the active packet's `development-diagnostics/` directory.
