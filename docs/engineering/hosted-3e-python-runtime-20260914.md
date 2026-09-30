# Hosted Python and runtime observations for 3e2cc1dba

All observations below belong to published source
`3e2cc1dba5c6dac1b12eb1badc9b6df09337b847`, not later local evidence commits.
Eight terminal job metadata records and their logs were downloaded and matched
to that full source SHA. This is software execution evidence, not independent
physical validation, release approval or main integration.

| Executed scope | Result |
| --- | --- |
| Development contracts, job 103780489879 | 1,217 passed, 1,167.94 s |
| Runtime Python, job 103780489133 | 96 passed, 13.46 s |
| Guarded frontend, job 103780489001 | 706 passed, 10.3 min |
| Actual HTTP Playwright, same frontend job | 36 passed, 3.5 min |

Repository workflow:
https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34778316962

Runtime workflow:
https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34778316768

All four full-test shards (jobs 103780490002, 103780490007, 103780490051 and
103780490075) failed `Materialize exact current-source test evidence` and skipped
`Run materialized repository test suite shard`. Their logs each retain both
`external_code_to_code_product_replay_not_passed` and
`external_code_to_code_technical_receipt_not_ready`. Aggregate job 103782268115
failed. Preparation includes a passing individual check, but that is not a
completed repository shard. Neither the successful development contracts nor
the successful runtime checks substitutes for the unexecuted full suite.

The topology job was still live when checked separately; this document makes no
terminal topology claim. No running job was canceled or restarted.

Retained packet:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-3e-terminal-python-1h8nq47c`

16 payload files, 689,176 bytes; inventory SHA-256:
`a98fcbbff58c3a2942b750b5599bf0acb8f5a2c82669d4fa84ce8b97a64a63d9`.
The adjacent summary lists job IDs, exact revisions and authoritative job links.
