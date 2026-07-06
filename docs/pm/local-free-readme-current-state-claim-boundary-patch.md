# Local-free README/current-state claim-boundary patch proposal

Purpose: propose safe README/current-state wording updates without mutating README, current-state docs, protected evidence, or readiness snapshots.

This proposal is **non-promoting**. It does not change release readiness, does not close Developer Preview, does not close G1, and does not authorize paid-pilot, limited-commercial, or independent-solver claims.

## Current safe summary

Recommended public-facing summary:

> Current status: workstation-based engineer-in-loop structural analysis/optimization delivery is strong, and release evidence governance is mature. Product readiness remains blocked because G1 full-load/full-mesh/material/HIP closure, customer shadow evidence, external benchmark receipts, human UX observation, license/legal approval, CI streak evidence, and structural-scope owner decisions remain open.

## Proposed README wording patch

### Replace or add near product readiness summary

```md
## Current readiness posture

The repository is currently best described as a workstation-based, engineer-in-loop structural analysis/optimization workbench. The release evidence system, viewer/report workflow, structural-scope quarantine, and PM/CTO handoff surfaces are mature enough to support internal review and bounded delivery preparation.

The repository is **not yet** release-ready, paid-pilot-ready, limited-commercial-ready, or an independent commercial structural solver. The canonical readiness snapshot remains blocked. The main open gates are:

- G1 full-load 1.0, full-mesh nonlinear equilibrium, material Newton breadth, and production ROCm/HIP residency;
- Developer Preview final gates for selected medium models, Linux/Windows reproducibility, and human new-user observation;
- PR/nightly CI 30-run streak evidence;
- product/legal license approval evidence;
- customer shadow evidence 3/3;
- external benchmark receipts 4/4;
- structural-scope owner decisions and release-surface cleanup.

Allowed current claim: engineer-in-loop review assist and workstation delivery preparation.
Forbidden current claim: independent commercial solver readiness, structural engineer replacement, permit automation, production HIP solver truth, paid-pilot readiness, limited-commercial readiness, or autonomous AI structural engineer.
```

## Proposed current-state wording patch

### Add to `docs/commercialization-gap-current-state.md`

```md
### Claim boundary update

Current commercialization posture remains bounded. Workstation delivery and engineer-in-loop review-assist surfaces are strong, but commercial release claims remain blocked until the canonical readiness snapshot clears its numerical, benchmark, software-product, and future-commercial blockers.

Do not promote release-surface PASS artifacts into product-level readiness. Material/contact/support capability surfaces may pass while G1 full-load/full-mesh/material/HIP closure remains open.

Current non-promoting readiness summary:

- Evidence governance: strong.
- Workstation delivery: ready for bounded internal/service preparation.
- Developer Preview: deliverables ready, final gates still open.
- G1: direct residual terminal slice ready, full-load/HIP/Newton lane not ready.
- Paid pilot: not ready.
- Limited commercial: not ready.
- Independent commercial solver: not ready.
```

## Claim wording table

| Topic | Use | Avoid until closed |
| --- | --- | --- |
| Developer Preview | `Developer Preview candidate`, `deliverables 10/10`, `final gates 6/9` | `Developer Preview ready` |
| G1 | `direct residual terminal slice ready`, `full-load lane open` | `G1 closed`, `full-load solved` |
| Commercial | `engineer-in-loop assist`, `workstation delivery preparation` | `independent commercial solver ready` |
| GPU/HIP | `remediation path identified` | `production HIP solver truth ready` |
| Customer | `customer shadow pending` | `customer validated` |
| Benchmark | `EB receipts pending` | `externally certified` |
| License | `license approval pending` | `license-approved paid pilot` |

## Review checklist

Before applying any wording patch, verify:

- blocker count matches `product_readiness_snapshot.json`;
- Developer Preview final-gate count matches `developer_preview_rc_status.json`;
- G1 wording matches `g1_full_load_hip_newton_lane_report.json`;
- paid-pilot wording matches `paid_pilot_scope_guard_report.json`;
- structural-scope wording distinguishes quarantine from owner-decision closure;
- no public-facing doc claims readiness while `release_ready=false`.

## Acceptance criteria

This wording patch should be applied only if:

- README/current-state remain synchronized with product readiness snapshot;
- no forbidden claim is introduced;
- current blocker counts are preserved;
- claim boundaries remain explicit;
- protected evidence is not regenerated as part of the wording-only patch.

## Non-promoting boundary

This proposal does not update README or current-state by itself. It is a review-ready wording patch proposal for a later documentation PR.
