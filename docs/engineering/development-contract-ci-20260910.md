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
`/tmp/rc-independent-ci-collection.log`. The first hosted result is recorded below.

## Hosted execution and remaining full-suite failure

[Run 34434309082](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34434309082)
completed for PR head `bb88bbe8d7d4769001b13bb5861141edeacff888`.
The actual checkout was GitHub's proposed merge
`78c3c6800d654fcdd60c9b84ffcda5b27e921dfa`, combining that head with
base `4de4e3f55aae1d267cf704cec7d7533f3a627498`. This is a tested merge
checkout, not an actual repository merge or a direct head-only execution.

The [development job](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34434309082/job/102736578729)
passed **336 tests in 373.31 s**, with zero failures, errors or skips. The downloaded
JUnit artifact agrees with the log and its ZIP SHA-256 agrees with the GitHub
artifact digest. The collection job also succeeded.

All four full shards failed `Materialize exact current-source test evidence`;
all four actual repository pytest steps were skipped. The full aggregate failed.
The inspected raw shard-1 log reports `external_code_to_code_product_replay_not_passed`
and `external_code_to_code_technical_receipt_not_ready` from the due-diligence
builder. The bounded matrix reports 2/25 technical cases and zero fresh technical,
external-engine, preflight and eligible cases. This identifies the current
preparation blockers; it does not establish every numerical cause from this log
or turn the separate modified-source comparison into official reference approval.

The independent diagnostic now provides executed regression information despite
that preparation failure. Complete repository execution and external qualification
remain open. No requirement was bypassed to obtain the 336 passing results.

The [machine summary](development-contract-ci-20260910.summary.json) binds the
run, head, tested merge, jobs, artifact and blockers. Eight original metadata,
log, JUnit and summary files (271,167 bytes) are preserved in
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-development-ci-1t4__7r7`.
The sibling inventory SHA-256 is
`41298ce7272698059a4abcaec4f9e2576efb7576265ef11e142334982bb72ba5`;
every inventoried file was reread and hash-checked. No new local numerical solve
was needed to inspect these hosted results.

The ongoing [secant-abstention experiment](rc-secant-abstention-20260910.md)
continues from its frozen 3d4ecef4b source, unaffected by these workflow edits.
Its first completed fold has 242 abstentions and identical secant/proposal
response histories, final checkpoint and all 242 original step-file pairs.
Its single proposal/secant path-time ratio is 1.0219789045931427. That partial,
fixed-order observation is not a repeated performance conclusion; the remaining
folds and complete original-state audit remain pending. The pairwise byte check
is retained under the active packet's `development-diagnostics/` directory.
