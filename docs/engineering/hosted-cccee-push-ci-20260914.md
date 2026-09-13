# cccee push CI failure — 2026-09-14

Exact source: `cccee909a8f4eb11c63724888db19617412fb859`.
The push-event [CI run 34772635703](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34772635703)
finished with a failure in job `103764900216` (`verify`). The failed step is
`Materialize exact current-source test evidence`. Its original log reports:

- `external_code_to_code_product_replay_not_passed`
- `external_code_to_code_technical_receipt_not_ready`

This is the observed result of this one terminal push-event run. It is not an
aggregate result for all workflows or evidence that repository tests ran and
failed. At capture, the separate Repository Python Tests run `34772638006`
had completed collection and was still running all four full shards and the
development-contract selection. The PR-event CI run `34772638019`, runtime
run `34772637958` and topology run `34772638050` were also still active.
These handles must be checked separately; neither success nor failure is inferred
from the push run.

The raw run metadata, job metadata and job log are preserved read-only at:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-cccee-push-ci-cy6opkc_`.
The packet contains 3 files, 143740 bytes. Its adjacent `-inventory.json` SHA-256
is `56b3519ad541a80afc7f1fcc9d8fe161ca937d34d600fdbb96455e79c0a1c11c`.
The run head and terminal job status were checked before sealing. No tolerance,
external-validation authority or protected evidence artifact was changed.
