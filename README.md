# Structural Optimization Workbench

> Workstation-based, engineer-in-loop structural analysis and optimization workbench with evidence/report packaging, deterministic validation surfaces, and bounded commercial-readiness gates.

## Current readiness posture

This repository is currently best described as a **workstation-based, engineer-in-loop structural analysis/optimization workbench**. The release evidence system, viewer/report workflow, structural-scope quarantine, and PM/CTO handoff surfaces are mature enough to support internal review and bounded delivery preparation.

The repository is **not yet** release-ready, paid-pilot-ready, limited-commercial-ready, or an independent commercial structural solver. The canonical readiness snapshot remains blocked. The main open gates are:

- G1 full-load 1.0, full-mesh nonlinear equilibrium, material Newton breadth, and production ROCm/HIP residency;
- Developer Preview final gates for selected medium models, Linux/Windows reproducibility, and human new-user observation;
- PR/nightly CI 30-run streak evidence;
- product/legal license approval evidence;
- customer shadow evidence 3/3;
- external benchmark receipts 4/4;
- structural-scope owner decisions and release-surface cleanup.

Allowed current claim: **engineer-in-loop review assist and workstation delivery preparation**.
Forbidden current claim: **independent commercial solver readiness, structural engineer replacement, permit automation, production HIP solver truth, paid-pilot readiness, limited-commercial readiness, or autonomous AI structural engineer**.

## Canonical readiness source

The canonical product readiness source is:

```bash
python3 scripts/build_product_readiness_snapshot.py --json --no-write
```

Release-facing documentation must stay synchronized with:

- `implementation/phase1/release_evidence/productization/product_readiness_snapshot.json`
- `implementation/phase1/release_evidence/productization/structural_product_development_roadmap.json`
- `implementation/phase1/release_evidence/productization/developer_preview_rc_status.json`
- `implementation/phase1/release_evidence/productization/g1_full_load_hip_newton_lane_report.json`

## Canonical status summary

Canonical product readiness snapshot: status `blocked`, blocker_count `45`, paid_pilot_ready=`false`, release_ready=`false`. Canonical blocker categories: numerical `4`, benchmark `10`, software product `15`, future commercial `16`. Inspect it without writing evidence with `python3 scripts/build_product_readiness_snapshot.py --json --no-write`.

Open Benchmark Developer Preview readiness: `developer_preview_readiness.json` and `developer_preview_readiness.md` report developer_preview_ready=`false`, blocker_count `10`, future_commercial_blocker_count `35`; the Developer Preview blocker split is numerical `4`, benchmark `2`, software product `4`. The boundary keeps customer shadow, license approval, commercial SLA, the 30-run CI streak, and each external approval receipt in the future Commercial Release context. It excludes autonomous AI/GNN/surrogate truth claims until the deterministic reference solver, residual/Jacobian/Newton closure, and benchmark truth are fixed. The freeze policy is new feature freeze `frozen_until_developer_preview_baseline_is_clean`, AI training freeze `frozen_until_deterministic_reference_solver_and_benchmark_truth_are_fixed`, and GPU/HIP track `performance_track_after_cpu_reference_parity`.

Developer Preview RC status: `developer_preview_rc_status.json` and `developer_preview_rc_status.md` report status `blocked`, deliverables `10/10`, final gates `6/9`. The remaining gates are selected medium models, Linux/Windows reproducibility, and human new-user workflow observation. The clean-clone checks do not close full Phase 3, G1 full nonlinear full-mesh/material Newton, or Linux/Windows parity.

Independent commercial product status: `python3 scripts/check_independent_product_readiness.py --json`. Current status is blocked at `80.0/100`.

PM release areas are `4/16` green with `64` open blockers, `42` release-area blockers, `11` external-input-required blockers, and `53` local-remediation-ready blockers. `python3 scripts/report_release_evidence_freshness.py` currently reports `3/14` artifacts passing; `developer_preview_rc_status.json` remains visible because evidence freshness does not close Developer Preview RC final gates.

Release mode runs `python3 scripts/check_github_actions_self_hosted_runner_status.py --check --fail-blocked` and `python3 scripts/build_product_readiness_snapshot.py --check --fail-blocked` without rewriting tracked evidence. A runner query failure remains a blocker; only an explicitly requested `--write-query-error-evidence` operation may write query-error evidence.

Commercial scope remains bounded: `engineer_in_loop_accelerated_coverage_ready=true`, `full_commercial_replacement_ready=false`; this is not full autonomous replacement. EB receipts stay `0/4` in `external_benchmark_submission_updates.json`. RH closure evidence is now signed/attached in `residual_holdout_closure_updates.json`. Inspect the bounded level with `python3 scripts/report_commercialization_level.py`.

## Developer Preview boundary

Developer Preview deliverables are packaged, but final gates remain open. Use:

- `Developer Preview candidate`
- `deliverables 10/10`
- `final gates 6/9`

Do not claim `Developer Preview ready` until selected medium models, Linux/Windows reproducibility, and human new-user workflow observation all pass.

## G1 solver boundary

G1 currently has a ready direct-residual terminal slice and strong cause narrowing, but full G1 closure remains open. Use:

- `direct residual terminal slice ready`
- `full-load lane open`
- `consistent residual/Jacobian Newton + ROCm worker is the recommended next lane`

Do not claim:

- `G1 closed`
- `full-load 1.0 solved`
- `full-mesh nonlinear equilibrium ready`
- `production HIP solver truth ready`
- `material Newton breadth closed`

until the corresponding G1 terminal evidence passes and the product readiness snapshot clears the numerical blockers.

## Engine v2 development track

The independent solver architecture and implementation sequence are maintained in the
[Structural Solver Engine v2 master roadmap](docs/structural-solver-engine-v2-master-roadmap.md).
Engine v2 milestone receipts are development evidence only; they do not change the
commercial-readiness boundary stated above.

Capability implementation and authority are tracked separately in
[`validation/capabilities/structural_capability_registry.v2.json`](validation/capabilities/structural_capability_registry.v2.json).
In that registry, `implemented` and `executable` do not mean `public`, external V&V,
or `release_eligible`. In particular, bounded Frame2D rigid offsets, RZ releases,
uniform member loads, direct displacement control, Frame3D candidates, material
candidates, and nonlinear transient SDOF execution are recorded as implemented
candidates without promoting them to release support.

Repository-level package boundaries, the P0-P3 product stages, and the ordered PR 1-18
program are maintained in the
[Repository Architecture and Product Development Roadmap](docs/repository-architecture-and-product-roadmap.md).
These are target-state gates, not statements of current support. The corresponding
dependency invariants are accepted in
[ADR-008](docs/adr/008-repository-package-boundaries.md).

## Workstation delivery posture

The strongest current product posture is workstation-based delivery preparation:

- engineer-in-loop review assist;
- local viewer/report/evidence package;
- structural-scope quarantine and claim-boundary governance;
- deterministic validation surfaces and readiness evidence tracking;
- bounded delivery package preparation.

This posture does not imply independent commercial solver readiness, paid-pilot readiness, or GA/enterprise readiness.

## Local-free closure packets

Local-free closure support documents live under `docs/pm/` and `docs/engineering/`:

- `docs/pm/local-free-closure-index.md`
- `docs/pm/local-free-structural-scope-release-surface-decision-pack.md`
- `docs/pm/local-free-release-surface-owner-decisions.draft.json`
- `docs/pm/local-free-release-surface-owner-decisions.candidate.json`
- `docs/pm/local-free-pm-release-blocker-closure-pack.md`
- `docs/pm/local-free-developer-preview-final-gate-pack.md`
- `docs/pm/local-free-evidence-intake-template-pack.md`
- `docs/pm/local-free-claim-boundary-audit-pack.md`
- `docs/pm/local-free-readme-current-state-claim-boundary-patch.md`
- `docs/pm/local-free-readme-current-state-applied-safe-wording.md`
- `docs/engineering/local-free-g1-closure-contract-runbook.md`
- `docs/engineering/local-free-static-risk-pr-split-plan.md`

These packets are non-promoting. They prepare evidence closure but do not close release gates by themselves.
