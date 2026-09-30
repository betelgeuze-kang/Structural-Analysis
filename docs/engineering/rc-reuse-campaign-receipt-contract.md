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

## Clean-source hosted packet

The optional `.github/workflows/rc-reuse-campaign-evidence.yml` runs the
committed three-topology synthetic plan from the event's exact head commit in a
clean checkout. It accepts only tracked files under `examples/` as plan and
model/request inputs and uses four pinned direct
Python dependencies. The campaign's `--require-clean-source` mode rejects a
dirty checkout, output inside the checkout, or imported repository modules from
another location. It records pre-run and post-run repository and imported
dependency module byte hashes, Python and installed dependency versions,
distribution `RECORD` hashes, and thread settings in
`execution-source.json`. The imported-module byte checks cover repository
modules and the four direct dependencies; transitive dependency versions and
distribution `RECORD` hashes are recorded, but their loaded file bytes are not
individually verified. The workflow retains the complete original packet as
a downloadable Actions artifact, including all comparison and native step
files. No protected or private source data belong in this workflow.

After the run, `scripts/audit_rc_reuse_campaign_packet.py` checks the packet in
a separate Python process against the committed plan and its original input
bytes. It rechecks case completion, saved receipt hashes, ordered dispatch
counts, baseline/reuse native step equality, reported full-history gates,
per-case ratios and a byte inventory of every packet file. The auditor does
not rerun a nonlinear solve or independently derive the physical response.
Failed or interrupted cases remain in the original packet; the audit exits
nonzero instead of turning a partial campaign into a success. Different cases
retain separate ratios and the cross-case ratio remains `null`.

This contract adds no hosted measurement until the workflow completes on an
exact source commit. A hosted packet gives inspectably bound software
execution evidence for these synthetic cases. Transitive dependencies are
neither locked nor byte-verified, so a later installation may differ. The
packet does not establish independent physical validation, hardware-general
speedup, learned-policy benefit, or complete preparation/transport/review cost.

## Interruption accounting in campaign receipt v2

The campaign now atomically writes a `running` row before calling each
numerical case. Its `case_wall_ns` is `null` and
`unknown_native_work=true`; the declared case remains in
`planned_case_count`. Successful saved-receipt verification changes the row
to `completed` with known case wall time and
`unknown_native_work=false`. An ordinary case error changes it to
`failed`, keeps the known elapsed wall time and any available receipt byte
bindings, and leaves native work unknown while later cases continue.

A caught `KeyboardInterrupt` changes the active row to `interrupted`,
records its elapsed wall time and available receipt byte bindings, then
re-raises. If the process stops without Python cleanup, the last atomic
`running` row remains with unknown elapsed time and native work. A
`campaign_complete` claim requires every declared case to have a terminal
`completed` or `failed` row, including when the interrupted case was last.
The aggregate speed ratio stays `null` in every state. Existing output
directories are refused on a subsequent invocation; a new execution cannot
silently overwrite or finalize the interrupted originals.

The v2 receipt measures its enclosing interval through the current receipt,
excluding that receipt's write. Its per-case wall interval begins after the
pre-case receipt and ends before hashing the final receipt files. These scopes
overlap and are not summed. No elapsed or native work is inferred for a
termination that did not reach the finalizer.
