# GitHub Documentation Status

- 기준일: 2026-07-14
- 목적: GitHub에서 바로 보이는 README/docs 문서가 현재 productization gate 상태와 같은 claim boundary를 말하는지 고정한다.
- Engine v2 working milestone: v0.2.34 external release identity v1; pushed audit HEAD `b2284e7a640932f9e21f5d78ed141097c721d4dd`, 신규 identity work는 local unpushed

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
| Engine v2 FGMRES sealed checkpoint transaction v0.2.22 | `contract_only`: still-open canonical context의 non-owning child가 conditional predecessor capability를 reserve 후 single-use consume하고 exact direct11/physical16, runtime/device/stream과 fixed four-row program을 transaction final fence 1회로 묶는다. Canonical parent를 포함한 체인은 fence 총 2회이며 추가 allocation/borrow/checkpoint-owner/module/H2D/D2H/intermediate sync/fallback은 0이다. Unit/legacy `23/56`와 actual `gfx1030` valid/late-invalid scoped cases `2 passed`를 확인했다. Consume-return interruption reconciliation과 closed current-binding claim release를 포함한다. Standalone receipt는 semantic consistency만 검증하며 provenance authenticity에는 `expected_context` 또는 서명이 필요하다. Invalid state `{2,3}`, snapshot 보존과 future action gate clear를 허용하며 gate zero 자체를 과거 no-commit/rollback 증거로 쓰지 않는다. Product receipt가 actual mask/verdict/commit/device outcome을 관찰하지 않으므로 conditional continuation만 발행하며 authoritative predecessor/numerical transaction/solver/solution·later recurrence·host-copy-zero·O(N)·speedup·commercial/promotion은 false |
| Engine v2 FGMRES global recurrence owner v0.2.23 | `contract_only`: sealed continuation을 single-use consume해 fixed later-column/restart/final-guard suffix를 one-fence completion으로 닫는다. Integrated actual HIP은 active later column/restart를 검증했지만 product receipt는 terminal outcome/status, parity, solution, O(N), speedup과 commercial을 관찰하지 않는다 |
| Engine v2 FGMRES fixed-suffix host-control v0.2.24 | `contract_only`: immutable dispatch·atomic pending·fixed-row-work `O(L)` host-control gate와 scoped lifecycle audit을 닫았다. 이는 일반 N-DOF O(N), kernel/solver speedup, terminal outcome 또는 commercial 증거가 아니다 |
| Engine v2 FGMRES owner-loss recovery v0.2.25 | `contract_only`: exact `hipStreamQuery`와 weak-liveness cell의 process-local consumed/pending suffix-owner recovery를 고정했다. Process crash/GPU reset/cross-process recovery와 numerical completion/parity/solution, promotion·commercial은 false |
| Engine v2 FGMRES active final guard v0.2.26 | `contract_only`: exact full final cycle을 checkpoint에서 fixed `FINAL_GUARD`로 handoff하고 actual `gfx1030` active/inactive·malformed prestate를 검증했다. Product receipt의 terminal outcome/status, parity, solution-ready, ResultIR, host-copy-zero, O(N), speedup·commercial은 false |
| Engine v2 FGMRES completion-only export v0.2.27 | `contract_only`: still-open `recurrence_fenced` global owner의 exact completion capability를 single-use consume하고 `solution_x` → `true_residual` → opaque `solve_record`를 exact three blocking D2H로 materialize한다. Exact `8F/8F/(192+72R)` extent, source lineage, immutable detached bytes/read-only view, payload hash와 copy-prefix telemetry를 별도 receipt에 결속하고 global receipt/hash·recurrence identity는 변경하지 않는다. Actual `gfx1030` `F=6,M=1,I=1,R=1`은 exact `3` copies/`360` bytes, host staging 3과 추가 HIP device allocation·H2D·async D2H·explicit stream sync·checkpoint fence·fallback 0을 확인했다. Exporter는 record를 parse하거나 payload content로 branch하지 않으므로 terminal outcome/status, parity, solution-ready, ResultIR, iteration host-copy-zero, O(N), speedup, promotion과 commercial은 false |
| Engine v2 FGMRES terminal-outcome observation v0.2.28 | `contract_only`: exact final completion-export result와 process-local context/policy seal을 요구하고 little-endian `192+72R` record의 terminal status/code/error/counter/metric/restart history를 별도 non-promoting receipt에서 해석한다. Numerical-failure stale header metrics와 solution/residual norm은 숨기고 committed row prefix만 보존하며, nonfailure residual bytes는 record deterministic tree metric과 일치해야 한다. Actual `gfx1030` later-column convergence와 active final-guard max-iteration 두 경로, raw export D2H 각 3회, observer device allocation/H2D/D2H/kernel/sync 0을 확인했다. Raw global/export receipt는 outcome-free로 유지되며 full parity, solution-ready, ResultIR, iteration host-copy-zero, O(N), speedup, promotion과 commercial은 false |
| Engine v2 FGMRES exact model-case parity v0.2.29 | `contract_only`: exact process-local terminal observation·CPU recurrence·compiler/runtime/device identity와 raw solution/exported residual/independent `b-Ax`를 고정 허용오차로 검증한다. Actual `gfx1030` 단일-model chain은 확인했지만 full model-family, multiarchitecture, signed promotion, ResultIR, iteration host-copy-zero, O(N), speedup과 commercial은 false |
| Engine v2 FGMRES fixed-suite local matrix v0.2.30 | `contract_only`: package-owned 10-slot × fixed `gfx1030/gfx1100` 20-cell 분류와 duplicate/device cross-base drift 거부를 구현했다. 이 historical v1 단계의 registered slot/coverage는 `0/10`, `0/20`으로 동결되며 downstream 증거를 소급하지 않는다 |
| Engine v2 FGMRES package fixture registry v0.2.31 | `contract_only`: exact ModelIR 10개를 package raw hash, canonical slot/registry hash, ExecutionPlan/FGMRES/CPU result와 독립 bounded direct oracle로 재생한다. Package registration은 `10/10`이지만 registry receipt 자체는 hardware·multiarchitecture·signed promotion·ResultIR·host-copy-zero·O(N)·speedup·commercial 증거가 아니다 |
| Engine v2 FGMRES registry-bound model-family parity v0.2.32 | `non_promoting`: package registry만 case authority로 소비하고 local actual RX 6900 XT `gfx1030` fixed suite `10/10`, 전체 matrix `10/20`을 확인했다. External actual `gfx1100`은 `0/10`이며 full family·multiarchitecture·signed promotion·ResultIR·iteration host-copy-zero·O(N)·speedup·commercial은 false |
| Engine v2 FGMRES external signed evidence verifier v0.2.33 | `non_promoting`: package-owned Ed25519 trust registry, canonical signed envelope, process-local single-use challenge, release/runtime/kernel/device 결속과 exact `gfx1100` 10-slot raw solution/residual/solve-record replay verifier를 구현했다. Caller-supplied expected wheel/source identity를 challenge·서명에 결속하고 current package schema/fixture registry는 직접 재생한다. 합성 집중 `10 passed`, quick suite `23 passed`; wheel `1034513` bytes/`sha256:4031426ee32b973e1e702f2947cc4dfebaaaf4be1f5d39043fabb11b5b7318e4`다. Package active key `0`이므로 public path는 `trust_anchor_not_found`로 fail-closed하고 actual external `gfx1100`은 `0/10`이다. Synthetic test는 hardware evidence가 아니며 wheel/source 자체 재해시·durable ledger·hardware-root·same-artifact multiarchitecture·release promotion·ResultIR·host-copy-zero·O(N)·speedup·commercial은 false |
| Engine v2 FGMRES external release identity v0.2.34 working | `contract_only`: candidate wheel same-FD/ZIP/full `RECORD`, installed distribution `RECORD`/declared scripts, clean Git manifest/exact archive/runner·build·lock hashes, exact declared-target-environment runtime dependency wheel closure와 fixed recipe policy를 독립 재생한다. 핵심 입력을 두 번 순차 replay하고 challenge·signed verify 직전 fresh replay해, 기존 release binding을 검증된 artifact에서 파생한 공개 constructor로 정상 발행할 수 없는 process-local mint-guarded capability로 signed verifier와 결합한다. Pushed audit HEAD `b2284e7a640932f9e21f5d78ed141097c721d4dd` 이후의 local unpushed milestone이다. Atomic multi-artifact snapshot, build 실행/재현성, remote commit authenticity, build-system dependency closure, dependency 설치 실행/current-interpreter wheel-tag 호환성, bounded total source-artifact memory, hostile same-process mint isolation, identity receipt hash의 serialized signed binding, durable ledger, runner honesty, hardware attestation/실행은 false다. Active key `0`, actual external `gfx1100` `0/10`, same-artifact two-architecture·promotion·ResultIR·host-copy-zero·O(N)·speedup·commercial도 false |

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
- `docs/engine-v2-hip-fgmres-checkpoint-atomicity-v1.md`: `DECIDE -> non-advancing PREFLIGHT -> pure-copy COMMIT -> FINALIZE` fixed row, mode 9/normal state 3 ticket, legacy/sealed lifecycle와 invalid-source state `{2,3}`·snapshot-preserving terminal contract를 고정한다. Historical raw `gfx1030` late-lane sentinel은 scoped destination byte-preservation만 증명하며 v0.2.22 sealed integration이나 authoritative solver claim으로 소급되지 않는다
- `docs/engine-v2-hip-fgmres-sealed-checkpoint-transaction-v1.md`: still-open canonical predecessor 아래에서 exact live kernel/checkpoint token/stream/direct11과 physical16 projection을 재사용하고 conditional predecessor capability를 single-use consume해 fixed four-row transaction과 transaction-owned final fence를 닫는다. 이 연결은 fixed program continuity와 conditional continuation만 증명하며 actual mask/verdict/commit/device outcome, authoritative predecessor/numerical transaction, solver/solution, later recurrence, iteration host-copy zero, O(N), speedup, promotion과 commercial claim은 false다
- `docs/engine-v2-hip-fgmres-global-recurrence-v1.md`: sealed continuation을 single-use consume해 exact global-program suffix를 same direct11/physical16·kernel/runtime/device/stream/checkpoint authority에 제출하고 final fence/pending acknowledgement 후 outcome-free completion capability를 발행한다. Integrated `gfx1030`은 active later column/restart와 exact full-cycle active final guard를 실행했지만 global receipt는 terminal outcome/status/parity/solution을 관찰하지 않는다
- `docs/engine-v2-hip-fgmres-completion-export-v1.md`: `recurrence_fenced` global owner의 completion capability를 single-use consume해 `solution_x`·`true_residual`·opaque `solve_record`를 fixed-order exact three blocking D2H로 materialize하고 immutable payload/hash·strict telemetry·parent-lifetime·fail-closed 경계를 별도 receipt에 고정한다. Solve record/outcome을 해석하지 않으므로 terminal status, parity, solution-ready, ResultIR, iteration host-copy-zero, O(N), speedup, promotion과 commercial claim은 false다
- `docs/engine-v2-hip-device-assembly-v1.md`: symbolic-only H2D plus HIPRTC frame/truss element contributions and deterministic CSR gather with exact telemetry and no CPU fallback; `gfx1030` compile/symbol inspection is available, while fresh native launch/parity, resident solver consumption, Krylov, O(N), speedup, and commercial claims remain unavailable
- `docs/engine-v2-hip-resident-csr-consumer-v1.md`: exclusive live-parent lease borrows assembly CSR and foundation load on the same runtime/device/stream with zero CSR/load reupload; test-double full/free/constrained residual/JVP parity is available, while native combined hardware parity and any Krylov/vector-loop claim remain unavailable in this resident-only contract; the downstream device producer is tracked separately below
- `docs/engine-v2-hip-free-space-operator-v1.md`: detached five-array symbolic overlay materializes `K_ff`/free state/load on the resident stream, produces `F_f-K_ffu_f` as an opaque single-use device generation, reuses resident full residual/JVP, and gathers reduced JVP with exact-zero prescribed and cross-residual parity guards; test-double parity and HIPRTC three-symbol compilation are available, while the native hardware gate may skip and reduction, preconditioning, Krylov iteration, iteration host-copy zero, O(N), speedup, signed evidence, and commercial claims remain unavailable
- `docs/engine-v2-hip-krylov-primitives-v1.md`: exact latest free-space apply 재검사와 lease 획득을 원자화한 same-stream child가 five borrowed/nine owned device buffers로 positive unshifted Jacobi, fixed affine/Jacobi, deterministic dot과 scale-first LASSQ diagnostic batch를 제공한다; raw batch transfer/allocation/sync/fallback 0, strict schema/live witness, parity-failure shared poison, acknowledgement-failure retry ownership, test-double FP64 parity, HIPRTC nine-symbol compile 및 conditional native gate는 검증했지만 recurrence, CG/FGMRES/PCG, SPD proof, integrated preconditioner, iteration host-copy zero, O(N), speedup, signed evidence와 commercial claim은 unavailable이다
- `docs/engine-v2-hip-fgmres-plan-v1.md`: exact sparse/free-space source, finite-positive Jacobi inverse와 CPU FGMRES policy에 결박된 seven-borrowed/nine-owned HIP memory 및 fixed recurrence ABI 계획; `M<=16`, global `I<=4096`, `P=ceil(F/512)`, dense `M²+5M+1`, little-endian field/code/flag가 고정된 solve-record `192+72R` 계약은 검증했지만 allocation, live lineage, HIPRTC recurrence, host-copy-zero, parity, O(N), speedup, ResultIR 및 commercial claim은 unavailable이다
- `docs/engine-v2-hip-fgmres-rtc-substrate-v1.md`: plan과 공유하는 canonical solve-record layout/code/flag hash, active-mask CSR SpMV/residual/copy-scale/Jacobi/control/record 7-symbol fixed source, gfx/code-object identity, pending-stream unload fence와 실제 `gfx1030` HIPRTC compile/symbol inspection을 검증한다. 후속 live resource context는 별도 구현됐지만 이 substrate 자체의 reduction producer, MGS/DGKS, Givens, backsolve, solution update, live solver receipt, iteration host-copy zero, native numerical parity와 commercial claim은 unavailable이다
- `docs/engine-v2-hip-fgmres-recurrence-abi-v2.md`: valid predecessor의 fixed four-row checkpoint, live/canonical/sealed owner에서 global later-column/restart/final-guard suffix, v0.2.27 completion export와 v0.2.28 context-bound terminal observer까지의 순서·lifetime·claim boundary를 고정한다. Current recurrence checkpoint/global/combined/source identity는 `sha256:0583f66e5faa848da734ff8fbcc430d8bb71ef9fc854fab49121be3f61691e5d`/`sha256:7c18ba9190fef663fec8e1f87e0f56ec393e23f04d4753ffbc3c707bff1a10ea`/`sha256:6a361ccfd0dbbe544e93b6c9ea788cc3702f6f924a969a3aa3deebf3292f315b`/`sha256:a5b39fb976aa330eaffae74feb8561f241df662a21dc32354b8010af2bb1c93d`로 유지된다. Exact terminal record observation은 observer receipt에서 true지만 full parity, solution-ready, ResultIR, iteration host-copy-zero, O(N), speedup과 commercial claim은 unavailable이다
- `docs/engine-v2-hip-fgmres-terminal-outcome-observation-v1.md`: exact final export result/context seal, 17 terminal code, policy/counter/gate/flag/stagnation 재생, failure stale-metric 숨김, residual payload metric 일치와 observer zero-device-operation 계약을 고정한다. Serialized receipt만으로 process-local provenance를 재인증하지 않으며 parity/solution/ResultIR/promotion 증거가 아니다
- `docs/engine-v2-hip-fgmres-model-case-parity-v1.md`: terminal observer 뒤 exact process-local CPU/HIP single-model numerical parity, compiler/runtime/device/kernel identity와 independent residual replay를 결속한다. 단일 local ISA 증거이며 family/multiarchitecture/promotion은 별도다
- `docs/engine-v2-hip-fgmres-fixture-registry-v1.md`: package-owned 10-slot ModelIR fixed suite와 strict replay authority를 고정한다. Registry 자체는 hardware 또는 external signed evidence가 아니다
- `docs/engine-v2-hip-fgmres-model-family-parity-v2.md`: registry-bound live local `gfx1030` `10/10`과 fixed 20-cell matrix를 소유한다. Serialized external evidence는 이 process-local receipt에 합산하지 않고 actual `gfx1100`은 `0/10`이다
- `docs/engine-v2-hip-fgmres-external-signed-evidence-v1.md`: package trust-anchor와 external `gfx1100` canonical Ed25519 envelope, release binding, single-use challenge, exact 10-slot raw numerical/record replay 경계를 소유한다. Current active key `0`의 public fail-closed와 synthetic-test-only 상태를 hardware/promotion evidence와 분리한다
- `docs/engine-v2-hip-fgmres-external-release-identity-v1.md`: candidate wheel/설치본, clean Git/exact archive/runner/build/lock, runtime dependency wheel closure와 declared recipe의 두 번 순차 replay, challenge·signed verify 앞 fresh replay와 process-local verified-release 결합을 소유한다. Atomic snapshot/build execution·reproducibility/durable ledger/hardware/promotion claim은 분리한다
- `docs/engine-v2-hip-fgmres-initial-recurrence-v2.md`: Checkpoint schedule `sha256:2423da989b6cd419b7c4bef46d6c76f2120825a0c840cb516803bb2643ca11e5`와 정상 legacy `0 -> 3 -> 0`, sealed `1 -> 2 -> 3 -> 0`, invalid sealed state `{2,3}`를 계약에 고정하고 v0.2.22 non-owning child가 canonical capability를 single-use consume하도록 연결했다. Historical v0.2.22 combined ABI/source는 `sha256:bb5b94457fbf3be4c5f2b38dda3f50c8a757094e0b97fb4d7288e7bdbf4db39f`/`sha256:a1d2da3f0d9a6c4a574fb1cb9d5be24c30c1e6e5e1c6de3ff1a4b50eeefad113`다. v0.2.21, v0.2.20과 v0.2.15 identity는 historical snapshot이며 authoritative solver/solution claim은 false다
- `docs/engine-v2-hip-fgmres-checkpoint-context-v2.md`: Checkpoint context v0.2.16은 exact 11-role extent/range registry, loader-minted read-only runtime와 fresh fixed native callable, actual device query, atomic raw lease, single-use predecessor, ambiguity poison, exact-runtime fence/atomic consume와 retry cleanup을 구현했다. Historical v0.2.22 binding은 same-stream four-launch row와 preflight/commit exact pointer tuple, fixed source `sha256:a1d2da3f0d9a6c4a574fb1cb9d5be24c30c1e6e5e1c6de3ff1a4b50eeefad113`을 사용하지만 이 API는 caller-attested legacy transaction만 소유한다. Canonical capability 소비는 별도 sealed child가 담당하며 본 receipt의 authoritative predecessor/transaction, later recurrence와 commercial claim은 unavailable이다
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
