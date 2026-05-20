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
  DELIVERY_INDEX.md
  REVISION_HISTORY.md
  drawings/
  data/
    revision_policy.json
  evidence/
  manifest.json
  checksums.sha256
  README_DELIVERY.md
```

## Section Contract

| Section | Role |
| --- | --- |
| `viewer.html` | Interactive review surface for model/result inspection. |
| `DELIVERY_INDEX.md` | First-open guide and customer acceptance checklist. |
| `REVISION_HISTORY.md` | Current delivery revision row and redelivery rule. |
| `report.pdf` | Printable review summary. If the canonical report is missing, the builder creates a clearly bounded fallback PDF. |
| `drawings/` | SVG drawing sheets and callout references for v1 delivery. |
| `data/` | Source model, client validation report, hardware profile, and service budget. |
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
- restored `viewer.html` has a viewer shell marker
- `DELIVERY_INDEX.md` contains the open-order and acceptance checklist markers
- `data/revision_policy.json` is present and enforces new package/manifest/checksum/job record on redelivery
- job reproducibility folder contains `input_manifest.json`, `run_log.jsonl`, `output_manifest.json`, and `checksums.sha256`

The same restore result is stored in `restore_smoke` and `checksum_self_test`.

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
- viewer shell marker check passes
- job record and job folder checksum self-test pass
- job retention policy disables automatic deletion and requires explicit confirmation plus cleanup dry-run
- claim boundary remains engineer-review bounded

This readiness gate is independent from strict EB/RH evidence. A green workstation delivery package does not make `check_independent_product_readiness.py` green unless EB/RH also closes.
