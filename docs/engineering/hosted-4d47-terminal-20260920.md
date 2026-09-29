# Hosted checks for 4d47f89ee

Exact source: `4d47f89ee670c7a3153fa3129218cd237b6f365d`. These jobs are terminal. The subsequent evidence-reader repair requires its own hosted checks.

- Python run 35497081250: development job 106041933773 passes **1,800 tests in 1311.52 s**; collection 106041933805 succeeds.
- Full-shard jobs 106041933856, 106041933924, 106041933948 and 106041933956 fail during external evidence preparation before actual repository tests. Aggregate 106043043181 fails. Shard-0 log retains `external_code_to_code_product_replay_not_passed` and `external_code_to_code_technical_receipt_not_ready`.
- Frontend run 35497068960: job 106041898389 passes **814 tests (18.6 m)**; required aggregate 106044376493 succeeds. Type checking, build and browser contract steps succeed.
- Workflow Contract CI 35497068967 and P0 Canonical Verification Contract 35497068970 succeed. Ordinary CI 35497068961 fails; these receipts do not establish full-suite completion.

Fetched logs: `/tmp/structural-4d47-development.log`, `/tmp/structural-4d47-frontend.log`, `/tmp/structural-4d47-shard0.log`.

The active 1,024-layer numerical experiment is separate from these software checks. Its result is pending. No independent physical verification, learned speed benefit or release approval follows from these test counts. No external requirement or numerical tolerance was weakened.
