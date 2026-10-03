# RC chunk execution integrated with the refinement branch

## Scope

Owner-authorized continuation of the merge plan, based on PR #450 commit
`1eee5f1fa012f7b1105e07df35a0b2f80f5d7271`. Port the distinct chunk-session,
CLI, bounded candidate threads, AMD command probe and tests from PR #444
`264cd592b295c5d72481c029e7390561643c0fed`. This is a source port, not a claim
that #444's Git history or all pending branches have been merged into main.

The chunk adapter uses #450's atomic no-replace first-owner mechanism. An
unowned legacy chunk directory is refused rather than silently claimed. Jobs
retain per-physics-key databases and the current RC chunk worker's lease,
invocation and checkpoint validation. Partial jobs are not injected into the
full-result/refinement cache. Cost search counts work on a paused model as new
work, not a cache hit; historical unknown work cannot establish an incumbent.
Cooperative stops preserve unrequested candidates as unknown. The 1..4-thread
batch is bounded scheduling, not a hard RSS limit or a performance certificate.
The AMD probe runs bounded discovery only and grants no GPU qualification.

All five files changed by the latest 1eee5f commit, including its twelve new
assembly-option cases, are preserved exactly. The ordinary local search CLI now
also exposes that existing option. Original scientific comparison, 114 numerical
core files, tolerances and material laws are unchanged. Existing collection,
development-contract, full-shard and required full-aggregate jobs, permissions,
triggers and concurrency remain structurally identical. The focused integration
job adds the ported regression modules and retains format/lint diagnostics.

## Verification before publication

A reconstructed, per-file-digest-verified tracked-source subset plus the port
passed 259 tests, zero failures/errors/skips. This includes 233 tests selected by
the expanded integration job, 23 current design tests and three action-pin tests.
The tests include real small RC solves, fresh replays, restart/repricing,
chunk-boundary pause/resume, wrong-owner refusal, immutable original checks and
explicit fault injection. Fault injection is not independent physical evidence.
Ruff 0.15.0 format and lint passed for fifteen current/changed Python files;
334 product Python files parsed with Python 3.10 grammar. Actual local execution
used Python 3.13.5, NumPy 2.3.5 and SciPy 1.17.0. This is not a full Git checkout,
whole-repository pytest, native build, hosted Python 3.10 result or AMD execution.

## Remaining integration and merge gates

The main-content reconciliation remains a separate pending change. Neither
main nor #439 is advanced by this port. #442/#448 are already in #450's ancestry;
old PRs and branches remain retained until validated integration is complete.

The prior head's four full-suite jobs failed evidence preparation, not their
pytest bodies. The inspected job 103905545187 reached the internal diligence
check with `external_code_to_code_product_replay_not_passed` and
`external_code_to_code_technical_receipt_not_ready`. The retained packet reports
two failed N1 horizontal-reaction comparisons in the bounded planar member-load
and prescribed-settlement cases. External bytes are historical, not newly
executed in that refresh. Their tolerances and reference values are not changed
by this port. The result does not justify a general legal-approval claim or an
assertion that the new chunk implementation caused those failures.

Final-head hosted integration and required full checks remain mandatory. Local
success cannot authorize a merge when those checks fail or have not run.
