# Workbench test registration and restored coverage

The hosted Workbench driver uses explicit file lists. Comparing those lists with the committed `workbench-v2-*.spec.ts` files found five existing files that were absent from both execution modes. This meant their earlier local results could not be presented as hosted coverage.

Restored default frontend-only files:

- `workbench-v2-centroid-distance-contract.spec.ts`: original centroid-change results on desktop and mobile.
- `workbench-v2-material-history-contract.spec.ts`: material memory limits, unavailable histories, provenance, state summaries and rejection of false safe selections.

Restored Python-enabled files (only under the existing `--with-job-api` option):

- `workbench-v2-checkpoint-retry-history-browser.spec.ts`.
- `workbench-v2-existing-checkpoint-history-browser.spec.ts`.
- `workbench-v2-successful-retry-history-browser.spec.ts`.

Those three start the real local Python job service and verify that injected historical failures do not hide later successful results, including checkpoint identity changes. They must not be added to the frontend-only lane, which has no solver installation.

## Prevention and verification

`scripts/workbench-test-registration.mjs` checks that every Workbench v2 spec is registered in exactly one lane and that every registered path exists within the expected test namespace. New unregistered files, duplicate registrations and invalid/missing paths fail before the build/browser run. This does not automatically execute new files in a potentially incompatible environment: the author must choose the correct lane.

Current registration is 40 default files and 8 Python integration files, including the separately added L-frame fixture test. A Node regression injects an unregistered test, a duplicate, a missing path and an outside path; it runs before the hosted build/browser checks as well as locally.

All five restored files were directly executed locally: **64 tests passed in 56.2 seconds** (54 frontend-only and 10 Python-integrated tests). The registration regression passed; frontend build/reproducibility contracts passed **9 tests in 0.48 seconds**. Vite and the test-owned job services were stopped normally. The prior numerical campaigns were not rerun. Source changes are retained at `d27962bb6`.

This restores recurring software coverage for result selection, material-history integrity and restart history. It does not close independent physical verification, observed learned benefit, external execution or release requirements. New-head hosted execution remains necessary.

The offline source inventory rebuild changes exactly one `current_blob_sha` and its `inventory_digest`; all historical identities, owner dispositions and other fields remain identical. The rebuilt inventory passes, and its nine regressions pass in 20.54 seconds. No fresh GitHub metadata verification is claimed.
