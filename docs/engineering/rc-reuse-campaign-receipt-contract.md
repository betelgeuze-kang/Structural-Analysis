# RC reuse campaign saved-receipt gate

`scripts/run_rc_reuse_campaign.py` records a case as completed only after it
checks the saved experiment output. The check binds the summary to the frozen
model and request bytes, current source and experiment script, declared
arithmetic and timing scope, and the exact number and alternating order of
repetitions. Each off/on benchmark must have a unique expected directory,
finite positive wall time, closed dispatch accounting, a matching time ratio,
and original native step files whose bytes match across the pair.
For each enumerated native step, the gate also reads its paired saved outcome,
checks the complete ordered assembly-dispatch record, and recomputes actual
dispatches and line-search reuse hits. The summary counts must match those
saved records; balanced but inflated summary counts, missing outcomes, and
malformed dispatch records fail the case.

The referenced comparison reports must retain valid canonical hashes, the
same supplied request and source revision, complete reference and strategy
paths, reported numerical work, and passing full-history comparisons. A
missing, malformed, or inconsistent saved receipt marks that case failed.
The campaign keeps the original receipt byte hash and case wall time, runs
later declared cases, and leaves the aggregate speed ratio `null`.

This is a post-run integrity and completion check. It does not repeat the
nonlinear solve, independently validate physical response, or prove a speedup.
Earlier campaign records are not retroactively reclassified by this change.
