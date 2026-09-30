# Previous-failure consumer boundaries and current CI preparation

Source head `28209c76643e00b4648a25dc9cfffe416768087a` plus the retained test-only
patch. Production code, failure authority and checkpoint checks are unchanged.

Two new tests use actual diagnostic/request bytes from the existing authenticated
service fixture, which executes failed nonlinear paths and preserves attempt 1
through a second failed attempt. The tests then construct local job-view metadata:

- A synthetic succeeded view with paired artifact references and completed
  progress permits explicit review of earlier attempt 1. Original diagnostic
  bytes are returned unchanged. Treating the same diagnostic as the current
  successful attempt is rejected. The input view is unchanged after validation.
- A synthetic changed-checkpoint view is schema-valid but the historical
  diagnostic is rejected because its restart binding differs. The input view
  is unchanged after rejection.

The succeeded view's result/evidence references are schema-only placeholders;
those bytes are neither fetched nor validated as an accepted engineering result.
No service job is changed to succeeded and no new checkpoint is generated.
These tests qualify consumer branching and rejection only. Actual successful
retry, changed-checkpoint end-to-end history and whole-user-flow timing remain
unqualified. They do not close M5, physical validation or release acceptance.

Pinned Node 24 TypeScript checking passes. The existing current-diagnostic and
history browser suites, including the two new contract tests, pass all 14 tests
in 52.1 seconds. Existing desktop/mobile actual-failure and original-download
checks remain included. These tests reuse three authored failed paths across
the fixture groups, not fourteen independent physical experiments. No fresh
production build is claimed for this test-only change.

The [receipt](failure-history-boundaries-20260914.json) binds a separate durable
output directory containing the source patch/files, runner, test log, outcome and
screenshots. All 15 files / 386,100 bytes are reread for SHA256 and length before
sealing. The outputs are outside the default Playwright test-results directory.

## Existing hosted head: full Python tests still not executed

At source head `58f6f2eb75dfa25ba98e4f8072b52c6a8319a029`, original logs for jobs
103748509303, 103748509319, 103748509328 and 103748509329 in
[Repository Python Tests run 34766580190](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34766580190)
identify merge checkout `ef56314eb` of that head into main `4de4e3f55…`.
All four fail `Materialize exact current-source test evidence`, and all four
skip `Run materialized repository test suite shard`. Each original log records
`external_code_to_code_product_replay_not_passed` and
`external_code_to_code_technical_receipt_not_ready`.

This verifies the current failure stage; it does not mean all repository tests
failed or passed. The separate development-contract and topology jobs were still
running when inspected. Their outcomes are not inferred from the shard failures.
The four job metadata/log pairs and summary are separately inventoried and bound
by the receipt. No external receipt or acceptance tolerance was changed.
