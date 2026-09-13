# Workbench actual HTTP CI integration

The 704-test hermetic frontend suite does not include the five actual HTTP
specifications gated by `--with-job-api`. The completed c8e4fbc2a frontend jobs
therefore prove their declared 704 tests, not execution of those extra HTTP tests.
Local HTTP evidence remains separately valid.

Runtime Input and Viewer CI now installs Python 3.10 and the application in its
frontend job, and executes the five real HTTP specifications in a separate step
after guarded E2E. The separate command retains the setup-python interpreter in
PATH; it does not change the sanitized environment of the hermetic runner.
The job retains test-results artifacts and fails on integration test failure.
Both push and PR path filters include components, execution code, transport
servers and fixtures so changes to the integration reach this lane.

The exact five-specification command passes 24 local tests in 1.2 minutes:
job API, failure diagnostics, failure history, RC candidate search and strategy
cohort HTTP. The workflow contract suite passes 18 tests; Ruff and diff checks
pass. No solver or frontend production code changes in this patch. Local fixture
and loopback results are not production identity, deployment or independent
physical validation. Hosted execution of this new step is still required.

Logs and the implementation patch are retained at `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-http-ci-integration-y6o49_g2` with an adjacent
SHA-256 inventory. The change is prepared locally while c8e4fbc2a topology CI
finishes; its prior results must not be relabeled as validation of this change.

## First hosted attempt and independent step scheduling

At 7734ad540 / merge 24e6b1b, frontend job 103733485138 installs Python
and the application successfully. The preceding guarded suite has 703 passes
and one failure: the ModelIR submit/run/replay test did not see the succeeded
panel within its existing five-second assertion. The captured UI remained
running; the cause is not established. Consequently the new HTTP step skipped.
The complete log and failure snapshot archive remain retained at `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-http-ci-failure-xtrgb56d`.
The unchanged failing test passes three local repetitions (24.7 seconds) on the
built application; this does not invalidate the hosted failure or prove a fix.

The HTTP step now runs when the build succeeded and the job was not cancelled,
even if the separate guarded E2E step failed. The failed E2E step still fails the
job; no continue-on-error or relaxed assertion is introduced. Workflow contracts
(18) and Ruff pass. Hosted HTTP execution and the ModelIR failure remain open.
