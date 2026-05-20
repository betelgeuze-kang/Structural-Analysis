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
- Current workstation delivery readiness is `PASS | gates=7/7`.
- Support bundle includes 21/21 required artifacts, including workstation job retention policy.
- Full Python test suite passes: `1463 passed`.

## Next Recursive Candidates

1. Add a read-only retention cleanup preview that lists stale job folders without deleting.
2. Add stronger package restore checks for PDF magic/header and manifest-to-report cross-reference.
3. Add customer-facing sample acceptance packet for a realistic project handoff.
