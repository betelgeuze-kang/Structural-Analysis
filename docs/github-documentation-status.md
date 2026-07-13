# GitHub Documentation Status

- 기준일: 2026-07-12
- 목적: GitHub에서 바로 보이는 README/docs 문서가 현재 productization gate 상태와 같은 claim boundary를 말하는지 고정한다.

## Current Published Claim

현재 GitHub 문서에서 허용되는 claim은 **engineer-in-loop commercial assist**다.

별도 허용 claim으로 **workstation delivery service**가 추가됐다: 내 워크스테이션에서 HTML/PDF/SVG/JSON/CSV 납품 패키지를 생성하고 구조 엔지니어 검토 전제로 전달하는 서비스다. 이 claim은 독립 SaaS/독립 구조해석제품 claim이 아니다.

Commercial v1 supported scope (machine-checked by `scripts/build_paid_pilot_scope_guard_report.py`):

- Structure families: frame, wall-frame, outrigger, truss
- Interop: MIDAS interop, OpenSees interop, KDS interop
- Analysis: nonlinear static, bounded NDTHA
- Audit: residual audit, reference comparison
- Reviewer package

Commercial v1 separate-validation exclusions (must stay visible):

- rail/tunnel
- special SSI
- nonstandard contact
- legal/authority approval automation
- special construction stages

금지 claim:

- full autonomous commercial replacement
- 구조기술사 검토 대체
- 인허가 자동 승인
- full strict external benchmark / residual holdout evidence package closed

## Current Gate Snapshot

| Area | Current status |
| --- | --- |
| P0 release/core | ready |
| P1 validation/breadth | ready |
| Runtime packaging | ready |
| Production ops/security | ready: no production default secret, rate/request limits, audit digest, `/ops/policy`, dry-run deployment drill |
| On-prem/air-gapped packaging | ready: skeleton contract, no live deployment claim |
| Support bundle | ready |
| Viewer workflow packaging | ready: evidence ingest, solver receipt, commercial-tool crosswalk, lineage drilldown, SVG sheet/revision/callout deep-link package, static performance budget manifest, local browser performance probe, 11-case render-mode/core/advanced workflow-state visual regression baseline |
| Workstation delivery service | local gate: hardware profile, service budget, delivery package manifest, client input validation, package restore/checksum smoke |
| PM release-area gate | blocked: `12/16` green; CI streak, human UX observation, license status, and GitHub sync local-head mismatch remain open |
| Release evidence freshness | pass: `15/15` artifacts include generated_at/source commit/engine version/input checksum/reuse marker, producer mtime recency, and declared dependency mtime recency; metadata freshness does not close the `0/3` shadow-case, G1 full-mesh nonlinear-equilibrium, Evidence Console launch, Developer Preview RC final gates, public benchmark source material, or GA breadth blockers |
| Fresh full-validation lanes | ready: lane contracts `8/8`, fresh receipts `8/8`; hydrated CPU-required release evidence and Level 3 fresh validation receipts remain separate evidence lanes |
| Real-project corpus measured status | pass for initial metadata/value gate: KR measured rows `10/10`, formats `2/2`, PEER metric-bearing values `5/5`; official PEER reference-truth groups `1`, measured-run bridge groups `3` |
| Customer shadow evidence | schema/validator/intake packet ready; five owner-input slots fixed; status gate blocked at `0/3` completed-project shadow cases until real customer-retained evidence files are attached |
| Residual Level 3 status | ready for attached NDTHA residual slice: hard `3/3`, recommended rate `1.0`, fallback `0.0`, solver_raw `1.0`, corrected-state recompute `3/3`; does not close independent V&V or GA breadth |
| Evidence Console scope | scope fixed: features `7/7`, deferred full-GUI surfaces `5/5`; launch blocked because customer shadow evidence remains `0/3` |
| Strict EB/RH evidence | blocked: EB `0/4`, RH signed closure `3/3` |
| Independent product readiness | blocked, `80/100` |
| Engine v2 FGMRES checkpoint raw slice v0.2.15 | `contract_only`: valid-predecessor first-column raw numerical slice와 actual HIPRTC hardware 12 cases 관찰. Authoritative solver/solution/full recurrence/host-copy-zero/O(N)/speedup/commercial은 false |
| Engine v2 FGMRES checkpoint context v0.2.16 | `contract_only`: typed range, loader-sealed runtime, historical 3-launch/current fixed-4-launch poison/fence owner는 구현됐다. 후속 resource context에 live Krylov parent가 생겼지만 이 caller-attested transaction과의 결합, authoritative predecessor/transaction·later recurrence·commercial은 false |
| Engine v2 HIP allocation-lineage foundation v0.2.17 | `contract_only`: process-local owner-minted typed allocation/range/borrow/free authority이며 solver/device-content/signed promotion/commercial은 false |
| Engine v2 FreeSpace/Krylov allocation-lineage integration v0.2.18 | `contract_only`: FreeSpace 12·Krylov 9 owned 실제 allocation/free와 parent 5-capability borrow, context-v2 conservation 및 RTC ownership을 구현; FGMRES predecessor·host-copy-zero·O(N)·speedup·commercial은 false |
| Engine v2 FGMRES live checkpoint resource context v0.2.19 | `contract_only`: actual Krylov parent3+allocator-owned8 exact11 lease, fresh/exclusive owner control, internal RTC/checkpoint-token과 semantic-last cleanup을 구현하고 실제 `gfx1030` resource chain을 관찰; owned content·authoritative predecessor/mask·transaction·solver/solution·host-copy-zero·O(N)·speedup·commercial은 false |
| Engine v2 FGMRES canonical predecessor producer v0.2.20 | `contract_only`: live exact11+delegated CSR3/scratch2의 allocation-free exact16 projection, sealed owned8 memset 8회, exact `27+14S` kernel prefix와 non-advancing device mask-domain validator를 one-fence conditional capability로 구현하고 actual `gfx1030` chain을 관찰; actual mask/verdict host 관찰·authoritative predecessor·checkpoint transaction·invalid-source atomicity·solver/solution·host-copy-zero·O(N)·speedup·commercial/promotion은 false |
| Engine v2 FGMRES checkpoint invalid-source atomicity v0.2.21 | `contract_only`: destination access 0인 non-advancing source preflight와 pure-copy COMMIT의 fixed four-row transaction을 구현해 late invalid source에서도 두 destination 전체 bytes를 보존한다. Plan/RTC/context-focused/native `63/100/77/13`, full context `261 passed in 523.33s`, race stress `5/5`와 final High/Medium 0을 확인했다. True 범위는 exact registered nonoverlap allocation, same stream, exclusive source ownership과 fixed owner sequence뿐이며 canonical capability 소비·authoritative predecessor/transaction/solver, arbitrary duplicate/external writer, later recurrence·host-copy-zero·O(N)·speedup·commercial은 false |

## Documentation Source Of Truth

- README: top-level GitHub status, command list, and allowed claim boundary
- `docs/structural-solver-engine-v2-master-roadmap.md`: Engine v2 target architecture, dependency rules, implementation sequencing, and phase exit criteria; this future-state plan does not close current readiness gaps
- `docs/engine-v2-execution-state-result-contracts-v1.md`: narrow Phase 0 CPU-reference ExecutionPlan/StateIR/ResultIR and receipt-chain contract; explicitly not HIP parity or commercial-readiness evidence
- `docs/engine-v2-sparse-execution-plan-v2.md`: bounded zero-offset/release frame/truss sparse-only plan and CPU direct-CSR execution with no global dense K; exact same-runtime result replay and retained-array slope guard do not establish peak-memory, iterative-solver, HIP, end-to-end O(N), or commercial claims
- `docs/engine-v2-cpu-fgmres-reference-v1.md`: deterministic fixed-restart right-preconditioned FGMRES CPU oracle with actual `r0=b-Ax0`, DGKS MGS, incremental Givens, true-residual restart/convergence gates, scale-relative breakdown, strict immutable result receipt and mandatory full recurrence replay; this is the HIP recurrence oracle, not device execution, host-copy-zero, O(N), speedup, ResultIR integration, or commercial evidence
- `docs/engine-v2-hip-context-v1.md`: native HIP availability and persistent ModelBuffer context with exact transfer telemetry; operator/state/solver/parity claims remain false
- `docs/engine-v2-hip-allocation-lineage-v1.md`: process-local owner-minted allocation identity, typed range/generation, exclusive borrow와 immutable free/orphan authority foundation; 후속 소비자 통합·solver·promotion 증거는 별도다
- `docs/engine-v2-hip-free-space-krylov-allocation-lineage-v1.md`: FreeSpace 12/Krylov 9 owned allocation과 parent 5-capability group borrow를 실제 lifetime 경로에 연결하고 context-v2 telemetry·중단 안전 module handoff를 검증; live FGMRES predecessor나 성능/상용 증거는 아니다
- `docs/engine-v2-hip-fgmres-live-checkpoint-context-v1.md`: exact Krylov parent3와 fresh/exclusive allocator-owned8을 exact11 group lease, internal RTC v2 module/checkpoint token, same runtime/device/stream, semantic-last cleanup과 strict non-promoting receipt에 결속한다. v0.2.20 single canonical-child reserve/close blocking/terminal release coordination이 추가됐지만 base v1 receipt는 resource-only이고, downstream producer claim은 별도 문서와 receipt가 소유한다
- `docs/engine-v2-hip-fgmres-canonical-predecessor-v1.md`: live exact11과 Krylov-delegated CSR3/scratch2를 allocation-free exact16 projection으로 결속하고, sealed `hipMemsetAsync` owned8 initialization 뒤 `INIT`부터 `PREDECESSOR_VALIDATE`까지 exact `27+14S` row를 한 exact-runtime fence로 닫는다. Device mask domain gate와 `empty -> armed` snapshot은 bound되지만 actual mask/verdict는 host가 관찰하지 않으며 authoritative predecessor, checkpoint transaction, invalid-source destination atomicity, solver/solution, host-copy-zero, O(N), speedup, commercial/promotion은 false다
- `docs/engine-v2-hip-fgmres-checkpoint-atomicity-v1.md`: `DECIDE -> non-advancing PREFLIGHT -> pure-copy COMMIT -> FINALIZE` fixed row, mode 9/state 3 ticket, legacy/sealed lifecycle와 invalid-source terminal contract를 고정한다. Actual `gfx1030` late-lane sentinel은 scoped raw destination byte-preservation만 증명하며 sealed transaction integration이나 authoritative solver claim은 아니다
- `docs/engine-v2-hip-device-assembly-v1.md`: symbolic-only H2D plus HIPRTC frame/truss element contributions and deterministic CSR gather with exact telemetry and no CPU fallback; `gfx1030` compile/symbol inspection is available, while fresh native launch/parity, resident solver consumption, Krylov, O(N), speedup, and commercial claims remain unavailable
- `docs/engine-v2-hip-resident-csr-consumer-v1.md`: exclusive live-parent lease borrows assembly CSR and foundation load on the same runtime/device/stream with zero CSR/load reupload; test-double full/free/constrained residual/JVP parity is available, while native combined hardware parity and any Krylov/vector-loop claim remain unavailable in this resident-only contract; the downstream device producer is tracked separately below
- `docs/engine-v2-hip-free-space-operator-v1.md`: detached five-array symbolic overlay materializes `K_ff`/free state/load on the resident stream, produces `F_f-K_ffu_f` as an opaque single-use device generation, reuses resident full residual/JVP, and gathers reduced JVP with exact-zero prescribed and cross-residual parity guards; test-double parity and HIPRTC three-symbol compilation are available, while the native hardware gate may skip and reduction, preconditioning, Krylov iteration, iteration host-copy zero, O(N), speedup, signed evidence, and commercial claims remain unavailable
- `docs/engine-v2-hip-krylov-primitives-v1.md`: exact latest free-space apply 재검사와 lease 획득을 원자화한 same-stream child가 five borrowed/nine owned device buffers로 positive unshifted Jacobi, fixed affine/Jacobi, deterministic dot과 scale-first LASSQ diagnostic batch를 제공한다; raw batch transfer/allocation/sync/fallback 0, strict schema/live witness, parity-failure shared poison, acknowledgement-failure retry ownership, test-double FP64 parity, HIPRTC nine-symbol compile 및 conditional native gate는 검증했지만 recurrence, CG/FGMRES/PCG, SPD proof, integrated preconditioner, iteration host-copy zero, O(N), speedup, signed evidence와 commercial claim은 unavailable이다
- `docs/engine-v2-hip-fgmres-plan-v1.md`: exact sparse/free-space source, finite-positive Jacobi inverse와 CPU FGMRES policy에 결박된 seven-borrowed/nine-owned HIP memory 및 fixed recurrence ABI 계획; `M<=16`, global `I<=4096`, `P=ceil(F/512)`, dense `M²+5M+1`, little-endian field/code/flag가 고정된 solve-record `192+72R` 계약은 검증했지만 allocation, live lineage, HIPRTC recurrence, host-copy-zero, parity, O(N), speedup, ResultIR 및 commercial claim은 unavailable이다
- `docs/engine-v2-hip-fgmres-rtc-substrate-v1.md`: plan과 공유하는 canonical solve-record layout/code/flag hash, active-mask CSR SpMV/residual/copy-scale/Jacobi/control/record 7-symbol fixed source, gfx/code-object identity, pending-stream unload fence와 실제 `gfx1030` HIPRTC compile/symbol inspection을 검증한다. 후속 live resource context는 별도 구현됐지만 이 substrate 자체의 reduction producer, MGS/DGKS, Givens, backsolve, solution update, live solver receipt, iteration host-copy zero, native numerical parity와 commercial claim은 unavailable이다
- `docs/engine-v2-hip-fgmres-recurrence-abi-v2.md`: valid predecessor에서 `x_scale_l2=trial+committed`, fixed four-row raw checkpoint와 parent3+owned8 live resource context를 유지하면서, mode `PREDECESSOR_VALIDATE=14`, source preflight mode 9, offset 116/120/124의 state 3 ticket과 canonical exact `27+14S` producer를 고정했다. Validator/checkpoint/current combined/source는 `sha256:b083896de86a808b1398d0fde4abe73726cb91f50399651274ef82dc09a5ef58`/`sha256:2423da989b6cd419b7c4bef46d6c76f2120825a0c840cb516803bb2643ca11e5`/`sha256:bb5b94457fbf3be4c5f2b38dda3f50c8a757094e0b97fb4d7288e7bdbf4db39f`/`sha256:ce4353f61fc3e8cd1311ad52ce50f21a677c7bfa865a2656aa5447b6ec104a83`다. Scoped raw invalid-source atomicity만 true이고 actual mask/verdict host 관찰, authoritative transaction, sealed capability 소비, later recurrence, O(N), speedup과 commercial claim은 unavailable이다
- `docs/engine-v2-hip-fgmres-initial-recurrence-v2.md`: Checkpoint schedule `sha256:2423da989b6cd419b7c4bef46d6c76f2120825a0c840cb516803bb2643ca11e5`와 legacy `0 -> 3 -> 0`, sealed `1 -> 2 -> 3 -> 0`을 계약에 고정했다. Current combined ABI/source는 `sha256:bb5b94457fbf3be4c5f2b38dda3f50c8a757094e0b97fb4d7288e7bdbf4db39f`/`sha256:ce4353f61fc3e8cd1311ad52ce50f21a677c7bfa865a2656aa5447b6ec104a83`다. v0.2.20과 v0.2.15 identity는 historical snapshot이며 authoritative solver/solution claim은 false다
- `docs/engine-v2-hip-fgmres-checkpoint-context-v2.md`: Checkpoint context v0.2.16은 exact 11-role extent/range registry, loader-minted read-only runtime와 fresh fixed native callable, actual device query, atomic raw lease, single-use predecessor, ambiguity poison, exact-runtime fence/atomic consume와 retry cleanup을 구현했다. v0.2.21 binding은 same-stream four-launch row와 preflight/commit exact pointer tuple을 사용하지만 이 API는 caller-attested legacy transaction만 소유한다. Canonical producer capability와의 결합, authoritative predecessor/transaction, later recurrence와 commercial claim은 unavailable이다
- `docs/engine-v2-hip-residual-jvp-v1.md`: AOT canonical-CSR ABI/artifact contract and plan/committed-state replay context with exact evaluation telemetry; current native execution/parity/speed claims remain unavailable
- `docs/engine-v2-rtc-backend-residual-jvp-v1.md`: isolated fixed-source HIPRTC canonical-CSR replay with an actual `gfx1030` residual/JVP parity observation, exact no-fallback telemetry, and forced unsigned-v1 non-promotion; not HIP assembly, a solver, O(N), speedup, or commercial evidence
- `docs/engine-v2-rtc-kernel-scaling-v1.md`: predeclared RX 6900 XT/gfx1030 off-cache five-size HIP-event scaling gate and unsigned raw observation; accepted only for the fixed degree-3 fused CSR kernel and explicitly not solver/end-to-end O(N), speedup, or commercial evidence
- `docs/engine-v2-fixed-rank-projection-v1.md`: bounded plan-bound implicit projection primitive and operation-count contract; not an AI proposal, learning, or solver-speed claim
- `docs/engine-v2-ai-proposal-gate-qr-v1.md`: immutable correction proposal, CPU full-physics replay, exact rollback, shadow isolation, and solver-approved bounded QR memory; OOD remains rejected and the direct solver does not consume the proposal
- `docs/independent-commercial-product-gap-reassessment.md`: readiness gate snapshot and remaining blocker summary
- `docs/workstation-service-productization-roadmap.md`: local workstation delivery-service roadmap and claim boundary
- `docs/workstation-delivery-package.md`: package layout, checksum, restore, and delivery manifest contract
- `docs/production-ops-security.md`: production ops hardening boundary
- `docs/runtime-production-packaging.md`: runtime packaging/support bundle boundary
- `docs/structure-viewer-product-workspace.md`: viewer workflow/report package boundary
- `docs/commercialization-improvement-priority-assessment.md`: prioritized productization backlog

## Verification

Keep these checks aligned with documentation updates:

```bash
python3 scripts/build_project_ops_deployment_drill_manifest.py --json
python3 scripts/build_structure_viewer_performance_budget_manifest.py --json
python3 scripts/build_workstation_hardware_profile.py --json
python3 scripts/build_workstation_service_budget.py --json
python3 scripts/validate_client_input_package.py --input implementation/phase1/open_data/midas/midas_model.json --json
python3 scripts/build_workstation_delivery_package.py --json
python3 scripts/build_workstation_job_retention_policy.py --json
python3 scripts/check_workstation_delivery_readiness.py --json
npm run verify:viewer-performance-probe
npm run verify:viewer-visual-regression
python3 scripts/build_support_bundle.py --json
python3 scripts/build_onprem_deployment_packaging_manifest.py --json
python3 scripts/report_release_evidence_freshness.py
python3 scripts/check_github_development_sync_preflight.py --fetch --json
# The GitHub sync preflight is read-only and reports only unsynced refs in pending_remote_updates.
# report_pm_release_gate.py also evaluates the read-only github_sync release area; use --github-sync-preflight to pin this JSON.
python3 implementation/phase1/check_real_project_corpus_measured_status.py --no-write
python3 scripts/check_independent_product_readiness.py --json
python3 scripts/verify_structure_viewer_contracts.py --dry-run
python3 scripts/verify_quality_gate.py --mode full --dry-run
git diff --check
```

If strict EB/RH evidence changes, update README, gap reassessment, commercialization priority assessment, and this status file in the same documentation commit.
