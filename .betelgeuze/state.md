# Betelgeuze Harness State

- Status: done
- Mode: Deep
- Risk: R3, local artifact/productization work
- Goal: keep recursively improving the workstation-based structural delivery service until locally closable gaps are eliminated.
- Current boundary: EB/RH strict independent-product evidence remains external and is not claimed as locally closable.

## Completed In This Track

- Added workstation hardware profile, service budget, delivery package, client input validation, and workstation delivery readiness gates.
- Generated local workstation artifacts and package zip.
- Verified workstation delivery readiness passes locally.
- Kept independent commercial product readiness blocked by EB/RH only.

## Current Recursive Gap

Resolved local productization gaps:

- `build_workstation_delivery_package.py` now writes `implementation/phase1/workstation_jobs/<job_id>/`.
- The job folder contains `input_manifest.json`, `run_log.jsonl`, `output_manifest.json`, and `checksums.sha256`.
- `check_workstation_delivery_readiness.py` now includes `Job reproducibility contract`.
- Delivery package builder now verifies `manifest.json` output rows against the zip's actual bytes/SHA-256 rows.
- Restore smoke now verifies the restored `viewer.html` has a viewer shell marker.
- Delivery package now includes `DELIVERY_INDEX.md`, `REVISION_HISTORY.md`, and `data/revision_policy.json`.
- Restore smoke now verifies the delivery index marker and revision policy.
- Added `workstation-job-retention-policy.v1` with explicit-confirmation cleanup policy.
- `check_workstation_delivery_readiness.py` now includes `Job retention and cleanup policy`.
- Added a read-only `cleanup_preview` that lists stale job folders without deleting.
- Restore smoke now checks PDF header, manifest report/viewer references, and manifest claim boundary.
- Added `ACCEPTANCE_PACKET.md` with customer acceptance/rejection and engineer-review acknowledgement markers.
- Added `data/redelivery_comparison_manifest.json` to link current package/job to previous delivery history.
- Restore smoke now verifies acceptance packet markers, manifest acceptance references, and redelivery comparison policy.
- Current workstation delivery readiness is `PASS | gates=7/7`.
- Support bundle includes 21/21 required artifacts, including workstation job retention policy.
- Full Python test suite passes: `1465 passed`.

## Next Recursive Candidates

1. Add report metadata/manifest revision cross-reference beyond PDF header.
2. Add a customer-facing delivery QA summary page that mirrors readiness PASS/BLOCKED without exposing internal-only paths.
3. Add optional signed delivery manifest skeleton for offline handoff, still placeholder-only until keys exist.
