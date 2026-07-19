# Local-free closure index

Purpose: index the local-free closure packets that can be advanced without local workstation, GPU/HIP runtime, Windows runner, self-hosted CI runner, legal signoff, customer evidence, or external benchmark receipts.

This index is **non-promoting**. It does not close readiness gates, mutate protected evidence, or authorize release, paid-pilot, limited-commercial, independent-solver, or GA claims.

## Current readiness posture

Current safe summary:

> Workstation-based engineer-in-loop structural analysis/optimization delivery is strong, and release evidence governance is mature. Product readiness remains blocked because G1 full-load/full-mesh/material/HIP closure, customer shadow evidence, external benchmark receipts, human UX observation, license/legal approval, CI streak evidence, and structural-scope owner decisions remain open.

Key current values:

| Area | Current value |
| --- | --- |
| Product roadmap | blocked |
| Evidence progress | 28.8% |
| Stage average | 26.1% |
| Ready stages | 0/8 |
| Product snapshot blockers | 118 |
| PM milestones | 2/5 |
| PM release areas | 4/16 |
| Developer Preview final gates | 5/9 |
| G1 direct residual terminal gate | ready |
| G1 full-load/HIP/Newton lane | not ready |
| Paid pilot ready | false |
| Limited commercial ready | false |
| Release ready | false |

## Packet map

| # | Packet | File | Purpose | Needed to close |
| ---: | --- | --- | --- | --- |
| 1 | Structural scope release-surface decision pack | `docs/pm/local-free-structural-scope-release-surface-decision-pack.md` | Prepare release-surface owner decisions for quarantined non-structural artifacts. | Owner approval and cleanup execution |
| 2 | PM release blocker closure pack | `docs/pm/local-free-pm-release-blocker-closure-pack.md` | Prepare CI/UX/license release-area blocker closure. | CI runner, UX observer, legal/product approval |
| 3 | Developer Preview final-gate pack | `docs/pm/local-free-developer-preview-final-gate-pack.md` | Prepare DP `5/9 -> 9/9` closure path. | Medium model execution, IFC acquisition/checksum/import execution, Windows replay, UX observation |
| 4 | Evidence intake template pack | `docs/pm/local-free-evidence-intake-template-pack.md` | Define license, UX, customer shadow, and EB evidence intake requirements. | Legal, UX, customer, external benchmark owners |
| 5 | G1 closure contract/runbook | `docs/engineering/local-free-g1-closure-contract-runbook.md` | Define G1 residual/Jacobian/full-load/HIP/material acceptance contract. | Solver execution and HIP runtime |
| 6 | Claim-boundary audit pack | `docs/pm/local-free-claim-boundary-audit-pack.md` | Prevent over-promotion in README/current-state/roadmap wording. | Documentation review |
| 7 | Static risk + PR split plan | `docs/engineering/local-free-static-risk-pr-split-plan.md` | Split docs/source/evidence work safely and identify static risks. | CI/local execution for verification |

## Recommended execution order

### Phase 1 — Owner-decision closure preparation

1. Use `local-free-structural-scope-release-surface-decision-pack.md`.
2. Review `local-free-release-surface-owner-decisions.draft.json`.
3. Owner fills identity, role, timestamp, and evidence reference.
4. Validate and merge decisions into the actual release-surface-first decision artifact.
5. Apply owner-approved delete/extract cleanup.
6. Rerun structural scope audit and product snapshot.

Target outcome:

- Release-surface owner decisions: `0/3 -> 3/3`
- Structural scope cleanup stage moves materially forward

### Phase 2 — Developer Preview closure preparation

1. Use `local-free-developer-preview-final-gate-pack.md`.
2. Select five medium models and attach PASS/approved REVIEW receipts.
3. Acquire/checksum the selected IFC files and attach import-health/negative silent-loss execution receipts.
4. Attach Linux and Windows replay receipts.
5. Attach human new-user workflow observation.
6. Regenerate Developer Preview RC status and readiness.

Target outcome:

- Developer Preview final gates: `5/9 -> 9/9`

### Phase 3 — PM release-area evidence closure

1. Use `local-free-pm-release-blocker-closure-pack.md`.
2. Attach product/legal license approval.
3. Attach human UX observation.
4. Bring self-hosted runner online.
5. Record PR/nightly 30-run CI streaks.
6. Regenerate PM release gate and product readiness snapshot.

Target outcome:

- PM release areas: `4/16 -> 16/16`

### Phase 4 — G1 solver closure execution

1. Use `local-free-g1-closure-contract-runbook.md`.
2. Generate full-load 1.0 checkpoint.
3. Close consistent residual/Jacobian Newton gate.
4. Close full-mesh nonlinear equilibrium.
5. Close material Newton breadth.
6. Prove production ROCm/HIP residual/JVP path.

Target outcome:

- G1 terminal requirements: `0/4 -> 4/4`

### Phase 5 — Commercial evidence closure

1. Use `local-free-evidence-intake-template-pack.md`.
2. Attach customer shadow `3/3`.
3. Attach external benchmark receipts `4/4`.
4. Refresh paid-pilot scope guard.
5. Refresh product readiness snapshot.

Target outcome:

- `paid_pilot_ready` can be evaluated for promotion.

## Non-promoting guardrails

Do not claim:

- release ready;
- paid-pilot ready;
- limited-commercial ready;
- Developer Preview ready;
- G1 closed;
- full-load 1.0 solved;
- production HIP solver proof ready;
- customer validated;
- external benchmark certified.

Until the corresponding leaf evidence passes and the product readiness snapshot reflects it.

## PR split recommendation

1. PR A: index + local-free packet docs.
2. PR B: release-surface owner decision draft and review.
3. PR C: README/current-state claim-boundary patch.
4. PR D: owner-filled structural-scope decision artifact.
5. PR E: protected evidence refresh after local/CI execution.
6. PR F: Developer Preview final-gate evidence.
7. PR G: G1 full-load/HIP/material evidence.

Keep docs-only, source-code, owner-input, and generated-evidence changes separate.
