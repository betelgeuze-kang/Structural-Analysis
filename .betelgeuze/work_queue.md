# Work Queue

## Completed

- Promote workstation job reproducibility from flat JSON only to folderized job contract and readiness gate.
- Add delivery package manifest self-consistency checks that verify manifest rows against zip file rows.
- Add restored viewer shell marker check.
- Add customer-facing `DELIVERY_INDEX.md` and `REVISION_HISTORY.md` to the delivery package.
- Add `data/revision_policy.json` and restore/readiness checks for it.
- Add `workstation-job-retention-policy.v1` and include it in readiness/support bundle.
- Keep full Python suite green after viewer preset contract update.
- Add read-only stale job cleanup preview for `workstation_jobs/`.
- Add package restore checks for PDF magic/header and report/package manifest cross-reference.
- Add customer-facing `ACCEPTANCE_PACKET.md` for acceptance/rejection and engineer-review acknowledgement.
- Add `data/redelivery_comparison_manifest.json` linking current package/job to previous delivery history.

## Next

- Add report metadata/manifest revision cross-reference checks.
- Add a customer-facing delivery QA summary page that mirrors readiness PASS/BLOCKED.
- Add optional signed delivery manifest skeleton for offline handoff.

## External / Not Locally Closable

- EB receipt `4/4`.
- RH closure `3/3`.
