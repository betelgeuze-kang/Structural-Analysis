# Developer Preview Blocker Split

This page separates Developer Preview RC blockers from Commercial Release blockers. It does not close any gate, create evidence, or promote a commercial claim.

## Source Receipts

| Track | Source | Current status |
|---|---|---|
| Canonical Commercial Release snapshot | `product_readiness_snapshot.json` | `blocked`, `blocker_count=36` |
| Developer Preview readiness bar | `developer_preview_readiness.json` | `blocked`, `blocker_count=5`, `future_commercial_blocker_count=31` |
| Developer Preview RC final gates | `developer_preview_rc_status.json` | `blocked`, deliverables `10/10`, final gates `6/9`, active RC blockers `3` |

The historical `42` release blocker count is no longer the stored canonical count after the current snapshot regeneration; the canonical Commercial Release blocker total is now `36`. Use `product_readiness_snapshot.json` for release blocker totals, and use the RC final-gate rows below for the three active Developer Preview RC blockers.

## Developer Preview RC Blockers

| Candidate item | DP RC blocker? | Current evidence boundary |
|---|---:|---|
| Selected medium models | Yes | Needs selected medium OpenSees/reference model PASS or approved REVIEW evidence. Parser/topology evidence alone does not count; medium normalization now has a receipt schema, but per-case normalization receipts are still missing. |
| Large crash/OOM-free execution | No | Current RC evidence is pass for this final gate; it still does not close full benchmark parity or commercial claim scope. |
| Silent import loss zero | No | Current RC evidence is pass for this final gate; it still does not close all import/benchmark/license commercial gates. |
| Linux/Windows reproducibility | Yes | Needs direct Windows replay receipt. Clean-clone spillover stays in the clean-checkout gate. |
| Human new-user workflow observation | Yes | Needs a real human new-user observation record. Automated browser/task evidence is rehearsal evidence only. |
| Git clean-clone benchmark regeneration | No | Current RC evidence is pass for this final gate; it remains non-promoting and does not close Phase 3 or commercial release. |

## Future Commercial Release Blockers

These remain visible for Commercial Release and do not count as Developer Preview RC final gates:

- Customer shadow evidence, including completed-project customer-retained metadata.
- Product/legal license approval, license-server operation, commercial SLA, and security/license release evidence.
- Self-hosted runner online evidence and PR/nightly 30-run consecutive green streak receipts.
- External benchmark receipts and independent V&V/signoff evidence.
- Release-publication remote mutation handoff.
- Full G1 commercial solver closure beyond the bounded Developer Preview evidence bar.

## Core API Boundary

The Developer Preview package API is narrower than the viewer/workbench product surface. The supported preview analysis types are `model_health`, `linear_static_axial_truss`, and `nonlinear_static_material_mesh_axial_chain`. General frame/shell linear analysis, modal, buckling, broad nonlinear analysis, design-code automation, and commercial solver replacement remain blocked or unsupported until explicit receipts close them.
