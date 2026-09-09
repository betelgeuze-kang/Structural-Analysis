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
