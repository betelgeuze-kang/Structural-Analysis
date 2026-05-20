# Workstation Delivery Service Productization Roadmap

- Date: 2026-05-20
- Scope: local workstation delivery service, not independent SaaS structural analysis product
- Gate: `scripts/check_workstation_delivery_readiness.py --json`

## Product Position

The active local product track is:

```text
Workstation-based structural analysis/optimization deliverable preparation service
with structural engineer review.
```

Allowed claim:

- Workstation-generated structural analysis, optimization, drawings, data, reports, and viewer package for engineer review.
- Local processing budget based on the current workstation hardware profile.
- HTML/PDF/SVG/JSON/CSV delivery package with manifest and checksums.

Forbidden claim:

- Independent commercial structural analysis product.
- Structural engineer replacement.
- Full autonomous replacement.
- Multi-tenant SaaS throughput claim.
- Customer-device FPS claim.

The existing independent commercial product readiness gate remains EB/RH-gated. Workstation readiness can become green locally, but it does not close strict external benchmark receipts or residual holdout closure evidence.

## Plan-First Operating Rule

Every workstation delivery-service task follows this order:

1. Check current state.
2. Define target artifact.
3. Add or update gate/test.
4. Implement.
5. Generate artifact.
6. Verify.
7. Update docs.
8. Reassess next gap.

Push, release, credential use, public upload, external submission, and deployment remain explicit-confirmation actions.

## Readiness Axes

| Axis | Gate | Local target | External blocker |
| --- | --- | --- | --- |
| Independent Commercial Product Readiness | `scripts/check_independent_product_readiness.py --json` | 80/100 currently | EB receipt `4/4`, RH closure `3/3` |
| Workstation Delivery Service Readiness | `scripts/check_workstation_delivery_readiness.py --json` | 100/100 locally achievable | none, except local artifact quality |

## Batch 1. Foundation

Artifacts:

- `implementation/phase1/workstation_hardware_profile.json`
- `implementation/phase1/workstation_service_budget.json`
- `implementation/phase1/workstation_delivery_readiness.json`

Commands:

```bash
python3 scripts/build_workstation_hardware_profile.py --json
python3 scripts/build_workstation_service_budget.py --json
python3 scripts/build_workstation_job_retention_policy.py --json
python3 scripts/check_workstation_delivery_readiness.py --json
```

Completion criteria:

- Hardware profile records CPU, RAM, GPU, storage, OS, local viewer probe, unsupported conditions, and recommended project-size tiers.
- Service budget records small/medium/large/oversize handling classes.
- Workstation readiness is visible as a separate non-EB/RH gate.

## Batch 2. Delivery Package

Artifact:

- `implementation/phase1/workstation_delivery_package_manifest.json`
- `implementation/phase1/release/workstation_delivery/project_package.zip`

Command:

```bash
python3 scripts/build_workstation_delivery_package.py --out implementation/phase1/release/workstation_delivery/project_package.zip --json
```

Package structure:

```text
project_package.zip
  report.pdf
  viewer.html
  ACCEPTANCE_PACKET.md
  DELIVERY_INDEX.md
  REVISION_HISTORY.md
  drawings/
  data/
    revision_policy.json
    redelivery_comparison_manifest.json
  evidence/
  manifest.json
  checksums.sha256
  README_DELIVERY.md
```

Completion criteria:

- Zip restore smoke passes.
- Checksums match.
- Manifest records input refs, output rows, file bytes, SHA-256 values, claim boundary, and proxy/fallback labeling.
- `DELIVERY_INDEX.md` tells the customer what to open first and what to verify.
- `ACCEPTANCE_PACKET.md` gives the customer an acceptance/rejection checklist and keeps engineer review explicit.
- `REVISION_HISTORY.md` and `data/revision_policy.json` lock redelivery/revision expectations.
- `data/redelivery_comparison_manifest.json` links the current job/package to previous delivery history without overwriting prior packages.

## Batch 3. Client Input Validation

Artifact:

- `implementation/phase1/client_input_validation_report.json`

Command:

```bash
python3 scripts/validate_client_input_package.py --input <dir-or-zip> --json
```

Statuses:

- `ready`: required geometry, coordinates, IDs, units, load cases, revision, and proxy/fallback labeling are present.
- `needs_review`: geometry is usable, but customer-facing missing-data report must be reviewed.
- `blocked`: input is missing, malformed, or lacks usable geometry.

## Batch 4. Delivery Readiness Gate

Command:

```bash
python3 scripts/check_workstation_delivery_readiness.py --json
```

Pass conditions:

- Hardware profile exists and `contract_pass=true`.
- Service budget exists and `contract_pass=true`.
- Delivery package manifest exists and `contract_pass=true`.
- Package checksum, restore smoke, PDF magic/header, manifest report/viewer/acceptance references, redelivery comparison, and manifest claim-boundary checks pass.
- Viewer browser probe and visual regression baseline pass.
- Client input validation report exists and is not `blocked`.
- Job record/folder contract exists and checksums pass.
- Job retention policy exists, disables automatic deletion, requires explicit confirmation plus dry-run before cleanup, and emits a non-destructive cleanup preview.
- Proxy/fallback values are explicitly labeled.

The full quality gate includes this check before independent product readiness:

```bash
python3 scripts/verify_quality_gate.py --mode full
```

## Batch 5. Customer-Facing Delivery UX

V1 formats:

- HTML viewer
- PDF report
- SVG drawings
- JSON/CSV data
- Evidence JSON
- Manifest/checksum files

V2 extensions:

- DXF/DWG round-trip.
- Customer-device performance evidence.
- Signed package/update flow.

## Batch 6. Job Reproducibility

Current v1 job record:

- `implementation/phase1/workstation_job_record.json`
- `implementation/phase1/workstation_jobs/<job_id>/`
- `implementation/phase1/workstation_job_retention_policy.json`
- embedded `job_record` inside `workstation_delivery_package_manifest.json`

Contract:

```text
jobs/<job_id>/
  input_manifest.json
  run_log.jsonl
  output_manifest.json
  checksums.sha256
```

The package builder emits a timestamp plus input-hash job id, records command, artifact path, input refs, output rows, and writes the folderized job contract with its own `checksums.sha256`. The workstation delivery readiness gate checks the flat job record and the folder contract before reporting PASS.

Retention policy:

```bash
python3 scripts/build_workstation_job_retention_policy.py --json
```

The policy is intentionally non-destructive: automatic deletion is disabled, cleanup requires a dry-run plus explicit confirmation, and the latest job remains pinned. The generated `cleanup_preview` only lists `would_delete_if_explicitly_confirmed` candidates by retention age or max completed job count; it never deletes folders.
