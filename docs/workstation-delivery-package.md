# Workstation Delivery Package

- Builder: `scripts/build_workstation_delivery_package.py`
- Manifest: `implementation/phase1/workstation_delivery_package_manifest.json`
- Default package: `implementation/phase1/release/workstation_delivery/project_package.zip`

## Purpose

The workstation delivery package is the customer handoff unit for the local service track. It packages the interactive viewer, printable report, drawing sheets, data artifacts, evidence artifacts, manifest, checksums, and delivery README into one restorable zip.

It supports a service claim only:

```text
Workstation-generated structural analysis/optimization deliverable for structural engineer review.
```

It does not claim independent SaaS readiness, structural engineer replacement, autonomous approval, or customer-device FPS.

## Package Layout

```text
project_package.zip
  report.pdf
  viewer.html
  ACCEPTANCE_PACKET.md
  DELIVERY_QA_SUMMARY.md
  HANDOFF_DIFF_SUMMARY.md
  DELIVERY_INDEX.md
  REVISION_HISTORY.md
  drawings/
  data/
    handoff_diff_summary.json
    report_metadata.json
    revision_policy.json
    redelivery_comparison_manifest.json
    signing_manifest.json
  evidence/
  manifest.json
  checksums.sha256
  README_DELIVERY.md
```

## Section Contract

| Section | Role |
| --- | --- |
| `viewer.html` | Interactive review surface for model/result inspection. |
| `ACCEPTANCE_PACKET.md` | Customer acceptance/rejection checklist and engineer-review acknowledgement. |
| `DELIVERY_QA_SUMMARY.md` | Customer-safe QA status page that mirrors package restore/checksum readiness without exposing internal-only paths. |
| `HANDOFF_DIFF_SUMMARY.md` | Customer-facing redelivery diff summary with added/removed/changed/unchanged package-member counts. |
| `DELIVERY_INDEX.md` | First-open guide and customer acceptance checklist. |
| `REVISION_HISTORY.md` | Current delivery revision row and redelivery rule. |
| `report.pdf` | Printable review summary. If the canonical report is missing, the builder creates a clearly bounded fallback PDF. |
| `drawings/` | SVG drawing sheets and callout references for v1 delivery. |
| `data/` | Source model, client validation report, hardware profile, and service budget. |
| `data/handoff_diff_summary.json` | Machine-readable package-member diff summary for current vs previous job output manifest. |
| `data/report_metadata.json` | Report SHA-256, bytes, source/fallback flag, manifest path, revision path, QA summary path, and engineer-review boundary. |
| `data/signing_manifest.json` | Unsigned offline-signing skeleton: signable payload, no included key material, and explicit `unsigned_placeholder` status. |
| `evidence/` | Local viewer performance probe, visual regression baseline, and support/readiness evidence. |
| `manifest.json` | Schema version, claim boundary, input refs, output rows, and proxy/fallback labeling. |
| `checksums.sha256` | SHA-256 rows for package contents. |
| `README_DELIVERY.md` | Short customer-facing open/read instructions and claim boundary. |

## Build

```bash
python3 scripts/build_workstation_delivery_package.py \
  --out implementation/phase1/release/workstation_delivery/project_package.zip \
  --json
```

The builder writes:

- `implementation/phase1/workstation_delivery_package_manifest.json`
- `implementation/phase1/workstation_job_record.json`
- `implementation/phase1/workstation_jobs/<job_id>/`
- `implementation/phase1/workstation_job_retention_policy.json` through `scripts/build_workstation_job_retention_policy.py`
- `implementation/phase1/release/workstation_delivery/project_package.zip`

## Restore Smoke

The builder extracts the zip into a temporary directory and verifies:

- required files/directories exist
- `checksums.sha256` is present
- every checksum row matches extracted bytes
- manifest, report, viewer, drawings, data, evidence, and README are present
- `manifest.json` output rows match zip bytes/SHA-256 rows for packaged content
- `report.pdf` starts with a PDF header
- `manifest.json` references both `report.pdf` and `viewer.html`
- `manifest.json` references `ACCEPTANCE_PACKET.md`, `DELIVERY_QA_SUMMARY.md`, `HANDOFF_DIFF_SUMMARY.md`, `data/handoff_diff_summary.json`, `data/report_metadata.json`, `data/redelivery_comparison_manifest.json`, and `data/signing_manifest.json`
- manifest claim boundary still says structural engineer review is required
- restored `viewer.html` has a viewer shell marker
- `ACCEPTANCE_PACKET.md` contains acceptance decision, package integrity, and engineer-review markers
- `DELIVERY_QA_SUMMARY.md` contains customer-visible QA, included-checks, and hidden/internal-checks markers
- `HANDOFF_DIFF_SUMMARY.md` contains customer handoff, package-change, and review-guidance markers
- `DELIVERY_INDEX.md` contains the open-order and acceptance checklist markers
- `data/handoff_diff_summary.json` records added, removed, changed, and unchanged package-member counts against the previous job output manifest, or an explicit initial-delivery status when no previous package exists
- `data/report_metadata.json` links the current job id to `report.pdf`, `manifest.json`, `REVISION_HISTORY.md`, `data/revision_policy.json`, and `DELIVERY_QA_SUMMARY.md`
- `data/revision_policy.json` is present and enforces new package/manifest/checksum/job record on redelivery
- `data/redelivery_comparison_manifest.json` links the current job to previous delivery history without overwriting prior packages
- `data/signing_manifest.json` is present as an unsigned skeleton, references `manifest.json` plus `checksums.sha256`, and proves no key material/private key is embedded
- job reproducibility folder contains `input_manifest.json`, `run_log.jsonl`, `output_manifest.json`, and `checksums.sha256`

The same restore result is stored in `restore_smoke` and `checksum_self_test`.

## Customer-Open Viewer Smoke

Run:

```bash
node scripts/verify-workstation-delivery-viewer-smoke.mjs --json
```

This extracts `project_package.zip`, serves the restored package from a temporary local HTTP server, opens `viewer.html` in Chromium, verifies the viewport canvas is visible and nonblank, and writes `implementation/phase1/workstation_delivery_viewer_smoke.json`.

The smoke also records `commercial_cockpit_alignment`. A passing customer-open smoke now requires the delivered single-file viewer to expose the current commercial cockpit handoff markers from `src/structure-viewer/index.html`, including the cockpit polish stylesheet, workflow tabs, stage review controls, contour scale evidence, load-case evidence rows, utilization heatmap evidence, viewport tool rail, 3D overlay receipt, stage result callouts, stage result receipt, critical members, optimization summary, and drawing handoff panel. The expected alignment status is `current_cockpit_delivery`; stale or legacy single-file delivery viewers must be called out explicitly.

## Readiness Integration

Run:

```bash
python3 scripts/check_workstation_delivery_readiness.py --json
```

The delivery package gate passes only when:

- package manifest has `contract_pass=true`
- required sections are present
- checksum self-test passes
- manifest consistency self-test passes
- restore smoke passes
- customer-open delivery viewer smoke passes
- PDF header, report/viewer/acceptance/QA/report-metadata/signing manifest references, redelivery comparison, and manifest claim-boundary checks pass
- viewer shell marker check passes
- customer QA summary, handoff diff summary, report metadata, and unsigned signing manifest checks pass
- job record and job folder checksum self-test pass
- job retention policy disables automatic deletion, requires explicit confirmation plus cleanup dry-run, and exposes a read-only cleanup preview
- claim boundary remains engineer-review bounded

This readiness gate is independent from strict EB/RH evidence. A green workstation delivery package does not make `check_independent_product_readiness.py` green unless EB/RH also closes.
