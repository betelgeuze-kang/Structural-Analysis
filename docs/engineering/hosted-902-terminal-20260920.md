# Hosted checks at 90222c9ff

Source `90222c9ff9e926609d06d6b1b83b790ffb5d28bb` completed its hosted workflows. These results qualify the executed checks at that source only, not the subsequent clean-runner capture transport implementation.

| Check | Result | Evidence |
| --- | --- | --- |
| Development contracts | 1,948 passed in 1,313.39 s | [job 106081312229](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/35511965626/job/106081312229) |
| Frontend | 814 passed in 18.8 min; required aggregate passed | [job 106081308015](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/35511965001/job/106081308015) |
| Python collection | Success | [run 35511965626](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/35511965626) |
| Four full Python shards | Failed during evidence preparation; repository tests not executed | Same Python run |
| Workflow contracts / P0 canonical | Success | Runs 35511964986 / 35511964996 |
| Ordinary CI | Failure | Run 35511964991 |

The development count now includes the eight standalone original-output capture checks registered at this source. It does not include the three later container-transport cases added at `2b41f71e7`.

Shard-zero raw logs identify `external_code_to_code_product_replay_not_passed` and `external_code_to_code_technical_receipt_not_ready`. This is not evidence that the full repository tests passed or that they all failed assertions: they were skipped after preparation failed. The separate fresh container diagnostic at `2b41f71e7` also retained the two reaction mismatches without changing tolerances; see [the observation](container-reference-capture-20260920.md).

No full-suite, independent-operator, legal or release closure follows from the successful focused checks. PR 439 remains a draft; no merge is performed.
