# Exact 4f232 hosted terminal results

These results qualify only `4f232fdfaaef47e59559fc92c14dbdcc5297b942`.
They do not qualify later output-capture or browser-budget changes.

| Check | Run / job | Result |
| --- | --- | --- |
| Python collection | 35509938156 / 106075972383 | Passed |
| Python development contracts | 35509938156 / 106075972484 | 1,940 passed in 1,310.10 s |
| Full Python shards | 35509938156 / 106075972485, 106075972492, 106075972511, 106075972517 | Failed |
| Full Python aggregate | 35509938156 / 106077054248 | Failed |
| Frontend | 35509925226 / 106075934685 | 813 passed, 1 failed in 18.7 min |
| Workflow contract | 35509925227 | Passed |
| P0 canonical contract | 35509925221 | Passed |
| Ordinary CI | 35509925222 | Failed |

The inspected full-shard steps fail in `Materialize exact current-source test
evidence` and skip `Run materialized repository test suite shard`. Shard 0 raw
logs retain `external_code_to_code_product_replay_not_passed` and
`external_code_to_code_technical_receipt_not_ready`. Full-suite execution and
independent technical acceptance are not complete.

The sole frontend failure is the mobile RC search review's test-wide 30-second
limit during final screenshot capture, after its assertions/download checks.
[The retained trace and scoped correction](rc-search-browser-capture-budget-20260920.md)
keep the original failed result visible. Both corrected local viewport cases
pass, but a new hosted head still needs verification.

Raw development/frontend/shard-0 logs were obtained from their completed jobs.
No failed numerical reference, browser assertion, original threshold or external
acceptance requirement was removed. No merge or release occurred.
