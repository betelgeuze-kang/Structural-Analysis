# Local-free README/current-state applied safe wording

Purpose: provide ready-to-apply wording for README and `docs/commercialization-gap-current-state.md` without mutating protected evidence or promoting readiness claims.

This companion is **non-promoting**. It does not replace the canonical product readiness snapshot and does not make the repository release-ready, paid-pilot-ready, limited-commercial-ready, Developer-Preview-ready, or independent-solver-ready.

## Applied wording block for README

Use this block near the current product readiness summary or as a replacement for any wording that could imply release readiness.

```md
## Current readiness posture

This repository is best described as a workstation-based, engineer-in-loop structural analysis/optimization workbench. The release evidence system, viewer/report workflow, structural-scope quarantine, and PM/CTO handoff surfaces are mature enough to support internal review and bounded delivery preparation.

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

## Applied wording block for current-state documentation

Use this block in `docs/commercialization-gap-current-state.md` under the commercialization status or claim boundary section.

```md
### Current claim boundary

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

## Applying this wording safely

Recommended process:

1. Confirm `product_readiness_snapshot.json` still reports release readiness as blocked.
2. Confirm Developer Preview final gates are still `6/9` before using the current block.
3. Confirm G1 full-load/HIP/Newton lane is still open before using the G1 wording.
4. Insert the README block into `README.md` or replace equivalent readiness text.
5. Insert the current-state block into `docs/commercialization-gap-current-state.md`.
6. Run doc/snapshot sync checks locally or in CI.
7. Do not regenerate protected evidence unless running the approved producer commands.

## Non-promoting boundary

This file is the applied wording source-of-truth for a later documentation patch. It intentionally does not edit README/current-state directly because those edits should be reviewed with current snapshot counts immediately before merge.
