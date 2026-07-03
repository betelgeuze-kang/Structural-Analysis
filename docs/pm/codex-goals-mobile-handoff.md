# Codex `/goal` Mobile Handoff

> Status: **mobile-safe Codex routing packet**  
> Scope: executable goals for later local PC / CI / ROCm/HIP contexts  
> This file is a planning handoff only. It does not run Codex, dispatch CI, execute Python/npm/Playwright, regenerate protected evidence, or promote any readiness claim.

## 1. Current mobile boundary

Current coordination is mobile/static. Therefore these goals are written so that Codex or a local/GPU operator can later execute them in the right environment.

Mobile-safe output:

```text
PM/CTO scope definition
acceptance criteria
command skeletons
non-promoting guardrails
owner-decision templates
```

Deferred execution:

```text
pytest / Python / npm / Playwright
structural scope cleanup apply/delete/extract
product readiness snapshot regeneration
ROCm/HIP runtime proof
G1 checkpoint continuation
external benchmark receipt attachment
customer shadow evidence collection
```

## 2. Goal 1 — Structural scope owner decisions

```text
/goal
Close the structural release-surface owner-decision blocker without promoting solver readiness.

Context:
- structural_scope_contamination_audit.json detects 86 tracked non-structural paths.
- The paths are quarantined outside the structural release surface.
- The near-term release-surface cleanup batch has 3 priority paths.
- Mobile work has prepared docs/pm/structural-scope-owner-decision-matrix.md.
- structural_scope_owner_decisions.template.json is a template only, not owner approval.

Tasks:
1. Fill owner decisions for the priority-1 release-surface batch:
   - implementation/phase1/release_evidence/surface/gpcr_hard_decoy_evidence_surface.json
   - implementation/phase1/release_evidence/surface/h_bond_backmap_evidence_surface.json
   - implementation/phase1/release_evidence/surface/pocketmd_lite_science_product_surface.json
2. For each row, choose one:
   - delete_from_structural_repository
   - extract_to_molecular_or_science_repository
   - keep_quarantined_outside_structural_release with signed exception
3. Do not delete or extract without explicit owner approval.
4. After approved decisions, run structural scope checks and readiness checks in local/CI.
5. Keep all science/GPCR/PocketMD/MD rows excluded from structural release evidence.

Acceptance criteria:
- release_surface_owner_decision_pending_count can be reduced after real owner decisions.
- first_unquarantined_non_structural_path remains empty.
- structural release surface does not count non-structural science rows.
- No G1, release, paid pilot, limited commercial, or GA promotion.
```

## 3. Goal 2 — G1 consistent residual/Jacobian Newton ROCm worker

```text
/goal
Repair and execute the G1 consistent residual/Jacobian Newton ROCm worker lane.

Context:
- g1_f2g_f2h_cause_narrowing_status routes the next G1 lane to consistent_residual_jacobian_newton_rocm_worker.
- Row-only support/elastic-link correction is deprioritized.
- Current G1 full-load lane is blocked by full-load 1.0 absence, consistent Newton proof, material Newton breadth, and production ROCm/HIP worker proof.
- Current ROCm/HIP blockers include /dev/kfd missing, /dev/dri missing, runtime unavailable, direct probe not executed, JVP rows not retained, and global Krylov HIP solver not proven.

Tasks:
1. Run ROCm/HIP runtime preflight on a GPU host.
2. Clear /dev/kfd and /dev/dri blockers if hardware is available.
3. Execute mgt_residual_jacobian_consistency_hip_required_probe.
4. Prove production ROCm/HIP residual/JVP path with no CPU fallback.
5. Retain JVP rows and prove global Krylov HIP solver.
6. Refresh g1_full_load_hip_newton_lane_report.
7. Keep full-load 1.0, direct residual, relative increment, material Newton, and CPU/GPU parity gates separate.

Acceptance criteria:
- mgt_residual_jacobian_consistency_hip_required_probe.status == ready.
- production_rocm_hip_residual_jvp_worker.ready == true.
- consistent_residual_jacobian_newton_gate_passed == true.
- No G1 closure claim unless full-load 1.0, direct residual, relative increment, material Newton breadth, and parity gates all pass.
```

## 4. Goal 3 — Developer Preview remaining gates

```text
/goal
Close the remaining Open Benchmark Developer Preview final gates without promoting commercial solver readiness.

Context:
- Developer Preview deliverables are 10/10.
- Current final gates are 6/9.
- Silent import loss zero and large crash/OOM-free are now passing in the current README/DP surface.
- Remaining gates are selected medium models, Linux/Windows reproducibility, and human new-user workflow observation.

Tasks:
1. Close selected medium models PASS or approved REVIEW:
   - identify five selected medium structural models
   - run or review model scorecards
   - record PASS or approved REVIEW
2. Close Linux/Windows reproducibility:
   - attach Linux replay receipt
   - attach Windows replay receipt
   - compare outputs and document acceptable deltas
3. Close human new-user workflow observation:
   - run install/load/analyze/view/export workflow with a real observer
   - record PASS/REVIEW/FAIL
   - update known limitations if REVIEW
4. Rebuild Developer Preview RC/readiness surfaces.

Acceptance criteria:
- Developer Preview final gates 9/9.
- developer_preview_ready == true for Open Benchmark Workstation Preview only.
- No commercial solver beta, G1, paid pilot, or autonomous AI claim.
```

## 5. Goal 4 — Readiness surface sync

```text
/goal
Synchronize readiness surfaces after owner decisions and Developer Preview/G1 receipt updates.

Context:
- README, structural roadmap, and raw product_readiness_snapshot can expose different blocker counts while development is active.
- product_readiness_snapshot.json is the machine-readable authoritative rollup.
- roadmap is the PM stage view.
- README is the human-facing mirror.

Tasks:
1. Run product readiness snapshot in no-write mode first.
2. Confirm whether README uses a compact structural-only count or the raw rollup count.
3. Regenerate roadmap only after upstream receipts are intentionally current.
4. Update README/current-state docs in the same PR as any snapshot/roadmap refresh.
5. Keep blocked status if blockers remain.

Acceptance criteria:
- README, roadmap, and snapshot status semantics agree.
- Count differences are either eliminated or explicitly labeled by scope.
- release_ready remains false unless all release gates actually pass.
- No protected evidence is rewritten from mobile/static context.
```

## 6. Goal 5 — Full-load 1.0 candidate, after worker lane

```text
/goal
Generate a non-promoting G1 full-load 1.0 checkpoint candidate after the consistent residual/Jacobian Newton worker path is coherent.

Context:
- highest observed load_scale is currently 0.656.
- required load_scale is 1.0.
- gap is 0.344.
- full_load_candidate_count is 0.

Tasks:
1. Start from the retained 0.656 checkpoint.
2. Attempt staged continuation 0.7 -> 0.8 -> 0.9 -> 1.0.
3. Use consistent residual/Jacobian Newton path, not row-only support/link correction.
4. Record direct residual, relative increment, fallback-zero/traced-degraded-state, and material Newton status.
5. Keep output non-promoting until all gates pass.

Acceptance criteria:
- load_scale 1.0 checkpoint candidate exists.
- direct residual gate status is machine-readable.
- relative increment gate status is machine-readable.
- material Newton breadth status remains explicit.
- No G1 closure unless all root gates pass.
```

## 7. Mobile-safe next action

From mobile, the correct next action is not to execute any goal. The correct next action is to hand this file to Codex/local/GPU operators and keep PR #63 documentation-only.

## 8. Claim boundary

This Codex handoff does not execute the goals. It only defines them. It does not close Developer Preview, G1, release readiness, paid pilot, limited commercial, production ROCm/HIP residency, external benchmark, customer shadow, or license/legal readiness.
