# Exact d53 hosted terminal results

Source: `d53d6e54a9ce28fe1a2e65aeebac2a995896c047`.

- Python development job 106079093003 / run 35511119446: **1,940 passed in
  921.53 seconds**; collection job 106079092950 also passes.
- Frontend job 106079085897 / run 35511117589: **814 passed in 13.2 minutes**.
  This includes the scoped desktop/mobile RC search capture budget correction.
  The prior 4f232 failure remains retained; no assertion or capture was removed.
- Workflow contract run 35511117582 and P0 run 35511117606 succeed.
- Full-shard jobs 106079093050/061/066/088 and aggregate 106080157046 fail.
  Shard 0 fails in current-source evidence materialization, skipping actual tests;
  its raw log retains `external_code_to_code_product_replay_not_passed` and
  `external_code_to_code_technical_receipt_not_ready`.
- Ordinary CI run 35511117616 fails. Full-suite execution is not complete.

Raw completed development/frontend/shard-0 logs were inspected. These receipts
apply only to d53. The eight newly separated output-capture tests were not yet
selected by d53's development lane; later CI registration needs its own hosted
receipt. No physics, rights, signed acceptance, merge or release claim follows.
