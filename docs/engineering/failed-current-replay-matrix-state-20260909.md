# Preserve failed current-product replay in the verification matrix

At source `0113110186d6cd22c9ce3995e8a031556f02b50f`, the matrix producer can
find a historical passing technical comparison while its current-product replay
fails. It previously labelled that combination `current_product_replay_only`,
then its unchanged validator correctly rejected the false replay flag. This
stopped current-source artifact preparation before downstream tests could run.

The producer now reports `current_product_replay_failed`. It preserves the
historical reference, receipt ID, path, artifact hash and case IDs, with explicit
failure diagnostics. Replay, current-source freshness and promotion flags remain
false. A valid blocked report describes the failure; it does not turn the failed
numerical replay into a pass.

## Observed CI failure and implementation boundary

Read-only API/log inspection confirms the same first exception,
`matrix_status_replay_only_row_invalid`, in three completed jobs at that head:

- [Full-pytest shard 0](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34291482375/job/102278770521):
  artifact preparation fails; the actual repository shard is skipped. Only its
  separate prerequisite ledger test ran and passed in 5.00 seconds.
- [Legacy contract-core](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34291482329/job/102279093601):
  preparation fails and the deterministic evidence-contract shard is skipped.
- [Verify](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34291482320/job/102278770367):
  preparation fails; structural-core, PR quality and subsequent readiness steps
  are skipped.

Earlier head `91f75dde9` also had all four full-pytest shards stop at the same
preparation error. These are not observed failures from tests that never ran.
The retained logs do not name the affected requirement/receipt, so the new row
diagnostic includes its receipt ID for the next actual materialization.

The change is limited to the matrix producer, its schema, two direct consumers
and three focused test modules. It adds a positive failed-row count only when
failed rows exist; existing no-failure summary shapes and count meanings remain.
Historical technical-reference counts still measure reference presence. They
cannot establish fresh current-source verification or promotion.

The existing source/replay/evidence bindings and operator signature validation
remain in place. The operator-bundle composer uses the same summary definition:
unreplaced failed rows retain their count/blocker, and replacing all of them with
valid rows removes that count. The nonpromotion policy recognizes the diagnostic
count only at the two existing summary/stored-summary pointers. It does not allow
similar authority keys or that field at other authority-bearing paths.

## Schema and status consistency

Both Python and schema contracts require failed rows to retain technical evidence
and explicit false replay/freshness/promotion fields. Missing failure diagnostics,
empty evidence and integer/float substitutes for booleans are rejected. A forged
failure count, including a count without failed rows, is rejected by the shared
summary validator.

Independent review also found a pre-existing one-way promotion implication:
relabeling a failed row `promotion_eligible` while leaving eligibility false could
inflate the summary. Promotion status now requires eligibility and the existing
authority conditions; no new approval authority is introduced. Failed external
execution rows also prohibit an external-matrix freshness claim in schema-only
consumers. A preflight-only failure does not automatically negate freshness of
all external-execution rows; the method distinction is preserved.

The schema extension accepts prior valid no-failure payloads. Consumers pinned to
an older strict schema may reject the new failure status until they update. This
local integration is not production compatibility or release approval.

## Focused validation and retained failures

The final selected group passes **77 tests, with 141 deselected, in 2.12 seconds**.
It covers both verification methods, failure/reference preservation, false
promotion/freshness, strict booleans, summary counts, exact nonpromotion pointers
and operator row composition. Ruff, format and diff checks pass. Independent
read-only review reports no remaining defect in the requested source changes.

The exact focused command is:

```bash
python3 -B -m pytest -q \
  tests/test_build_bounded_planar_external_vv_matrix.py \
  tests/test_build_bounded_planar_external_vv_matrix_from_operator_bundle.py \
  tests/test_nonpromotion_authority_policy.py \
  -k 'failed_replay or matrix_schema_is_valid or current_matrix_defaults_do_not_fall_back_to_tracked_snapshots or bounded_summary_rejects_transplanted_known_keys or bounded_planar_nested_metadata_rejects_unknown_truthy_descendants or production_policy_contains_current_authority_boundary'
```

The initial two failing pure regressions preserve the original misclassification.
An intermediate 45-case group passes. The first consumer group has 75 passes and
two test-only import failures; loading its synthetic helper through the existing
exact-file loader fixes those two cases, which pass separately before the final
77-case run. These groups overlap. Original logs are retained.

The operator tests explicitly substitute signature/source boundaries and the
full validator. They test the actual row, count, hash and blocker composition;
they do not revalidate signatures or accept real evidence. The focused command
does not run the protected original-evidence tests, the full matrix builder or
the skipped hosted suites. No local solver/public analyses or protected evidence
regeneration is performed. The failed replay itself, full hosted materialization,
downstream suites and independent verification remain to be resolved.

## Retention

The focused development bundle is retained at
`/tmp/structural-matrix-failed-replay.UgRtkg`. Its inventory covers **nine files /
55,266 bytes**, excluding the inventory. Inventory SHA-256 is
`e15c9e499497cd6814bb762553507eab256e8189349a0a45898f593b8deea783`.
A separate process verifies the complete file set and hashes, and all seven
current changed files match the source hashes in the report. Its receipt is
outside the root at the same path plus `-verification.json`.

The three current-head CI logs and API records are sealed at
`/tmp/structural-ci011-failure-classification.OyLasvnq`: **10 files /
326,293 bytes**, inventory SHA-256
`1fac6cf1b5efdf0113f569158ebb868b4ac5ef9c1e65600852d0b5c34961c9fd`.
The complete bytes were rechecked in a separate process. These are unsigned local
consistency records; raw bundles remain local. The
[machine summary](failed-current-replay-matrix-state-20260909.summary.json)
publishes source identities, results and limits. New exact-head hosted results,
the broader roadmap and all independent/owner/licensing/hardware dependencies
remain open.

## Follow-up at e56a005

At exact head `e56a00502aa1d5d2cc35bbc0ad700e4eb1d0f810`, both frontend
jobs complete successfully with 407 browser cases each. Engine-v2 and both
canonical-contract jobs also pass. The four full-pytest shards still stop during
materialization, now at `matrix_status_evidence_authority_invalid`; their actual
repository test bodies do not run. The same exception is retained for the
legacy contract-core and PR verify jobs. The hosted logs name this validator
branch but do not identify the affected row.

Source inspection identifies another supported combination: the whole receipt's
technical flag can fail with current replay while its binding still contains
passing historical comparison IDs. `_receipt_binding` explicitly derives
`case_ids` from comparisons whose `contract_pass` is true. A failed row may retain
those source-revalidated references without requiring the whole current receipt
to pass. The focused correction preserves exact path/hash/case coverage, current
replay and freshness comparisons, and all strict failed-row nonpromotion flags.
Passing replay rows still require the original whole-receipt technical pass.

The extracted pure evidence validator is exercised with the real binding
projection over synthetic receipt bytes, including a deliberately failed
historical case excluded from its inventory. Eleven additional cases cover both
verification methods, whole-receipt true/false, missing or transplanted evidence,
uncovered cases, replay disagreement and preservation of passing-row authority.
The final combined selection passes **88 tests / 141 deselected in 2.10 s**.
There is no local protected-evidence read, full materialization, solver execution
or numerical replay repair in this follow-up. Hosted success for this correction
still requires a new exact-head run.

Follow-up logs and focused results are retained separately at
`/tmp/structural-cie56-final.rjtWCrYy`. Earlier sealed bundles remain unchanged.

## Engineering recovery coverage selection

The same e56 topology job passes all **412 focused tests in 1,050.78 s** and
the J1–J5 coverage gate (22 tests, 92%). Its next engineering-recovery group has
19 passing tests but only 85% coverage against the existing 90% threshold.
The workflow omitted the already-existing dedicated checkpoint-transition
recovery tests from that coverage command.

The workflow now includes `test_corotational_checkpoint_transition_recovery.py`
in the original coverage command and its path trigger. No solver or numerical
test changes are needed, and the threshold remains 90%. Local baseline
reproduction passes 19 tests in 57.19 s at 85.0095%; the three-file selection
passes **86 tests in 64.69 s at 94.3074%**, and the original coverage gate passes.
An argument-preserving observer counts 56 returned Newton calls in the existing
two suites and **zero** in the added checkpoint-transition suite. The baseline
was not count-instrumented, so its call count is unavailable.

The first local command could not import `coverage` and ran zero tests. The
test tool was installed only under a fresh temporary tooling directory; an
initial download retry is retained. Logs, coverage JSON and invocation counts
are in `/tmp/structural-engineering-recovery-coverage.lMYbvBth/summary.json`.
This focused correction does not prove the later skipped topology steps or
new-head hosted materialization pass. Combined CI registration checks pass
49 tests in 0.55 s.

The [combined follow-up machine summary](rc-fiber-durable-jobs-20260909.summary.json)
retains the exact e56 check snapshot (59 success / 13 failure / five skipped,
including aggregate failures), focused results and coverage observation.
The follow-up bundle is sealed at 26 files / 1,908,066 bytes with inventory
SHA-256 `b77f398b6de42eb82e61a3afcc9f809fec660520b034486159e1e2a63fa283d1`;
a separate process verifies the exact file set and bytes. Its source copies
were taken after validation. It does not replace the earlier sealed records.
