# Hosted checks for 6a9093b6e and diagnostic selection repair

Exact source: `6a9093b6e542309e7757c99ddd4de9696040418f`. Python run 35499446673, development job 106048463572, passes **1,807 tests in 1013.64 s**; collection 106048463522 succeeds. Frontend run 35499425010, job 106048405971, passes **814 tests (13.7 m)** plus seven setup tests; aggregate 106050230656 succeeds. Workflow Contract CI 35499425017 and P0 Canonical Verification Contract 35499425031 also succeed.

The four full shards fail before repository tests in external evidence preparation. Shard-0 106048463526 retains `external_code_to_code_product_replay_not_passed` and `external_code_to_code_technical_receipt_not_ready`. Ordinary CI 35499425022 fails. These scoped successes do not establish complete repository testing, physical verification or release approval.

The unchanged development count exposed an explicit-selection omission: the new witness-probe test file was not among the 64 diagnostic files. The following local repair adds that file and both new artifact writer/reader files, making 67 selected files. The workflow contract now requires all three. The workflow/new diagnostic focused checks pass **47 tests in 2.21 s**, with Ruff/diff checks passing. This local result is not attributed to the older hosted SHA. New-source hosted execution remains pending; the external full-suite requirement is unchanged.

Fetched logs: `/tmp/structural-6a9-development.log`, `/tmp/structural-6a9-frontend.log`, `/tmp/structural-6a9-shard0.log`. The earlier witness tests did pass locally; their omission from this hosted selection is retained explicitly.
