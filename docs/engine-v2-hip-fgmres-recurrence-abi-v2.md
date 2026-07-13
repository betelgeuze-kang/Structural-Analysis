# Engine v2 HIP FGMRES full recurrence ABI v2 design

- 상태: v0.2.21 accepted ABI; plan/schema, valid-predecessor raw checkpoint slice, scoped invalid-source failure atomicity, caller-attested transaction context, live resource owner와 device-sealed canonical first-column predecessor producer는 구현, sealed checkpoint 결합과 full recurrence는 unavailable
- 목표: fixed-restart right-Jacobi FGMRES의 iteration D2H/sync 0 device schedule
- 수치 oracle: [CPU fixed-restart FGMRES reference v1](engine-v2-cpu-fgmres-reference-v1.md)
- 기반: [HIPRTC FGMRES 7-symbol recurrence substrate v1](engine-v2-hip-fgmres-rtc-substrate-v1.md)
- 상위 기준: [Structural Solver Engine v2 마스터 로드맵](structural-solver-engine-v2-master-roadmap.md)

이 문서는 v2 전체 구현 ABI를 고정한다. 현재 [initial + first-column checkpoint transaction recurrence v2](engine-v2-hip-fgmres-initial-recurrence-v2.md)의 candidate residual, device-only scale predicate, trial/committed L2와 `CHECKPOINT_DECIDE -> PREFLIGHT_COMMIT_SOURCE -> gated COMMIT_CHECKPOINT -> CHECKPOINT_FINALIZE`까지 구현·조건부 native 검증되었다. [Checkpoint transaction context v2](engine-v2-hip-fgmres-checkpoint-context-v2.md)는 exact allocation range, raw lease, fixed four-launch poison/fence lifetime을 구현한다. [Checkpoint invalid-source atomicity v1](engine-v2-hip-fgmres-checkpoint-atomicity-v1.md)은 exact registered nonoverlap allocation, same stream, exclusive source ownership과 fixed four-row owner sequence에 한정해 late invalid source에서도 destination 전체 bytes가 보존되는 범위를 고정한다. [Live checkpoint context v1](engine-v2-hip-fgmres-live-checkpoint-context-v1.md)은 실제 Krylov parent3와 allocator-owned8을 exact11 lease, fresh/exclusive owner control, RTC module/checkpoint token과 semantic-last cleanup에 결속한다.

v0.2.20의 [canonical first-column predecessor producer v1](engine-v2-hip-fgmres-canonical-predecessor-v1.md)은 이 exact11에 Krylov가 위임한 CSR3와 reduction scratch2를 더한 allocation-free exact16 physical projection을 검증하고, owned8을 sealed `hipMemsetAsync`로 zero-initialize한 뒤 `INIT`부터 `PREDECESSOR_VALIDATE`까지 exact `27+14S` kernel row를 같은 runtime/device/stream에 제출해 한 번의 exact-runtime fence로 닫는다. Validator는 허용 mask domain만 장치에서 검사하고 결과와 actual mask를 host에 복사하지 않는다. 따라서 이 producer도 authoritative predecessor, checkpoint transaction, live solver, later column/restart 또는 성능 증거로 승격되지 않는다.

## 1. Device control state

V1의 공개 solve record `192+72R`는 completion/export 영수증으로 유지한다. 반복 중 transient state는 새 owned buffer `fgmres_control_state_v2: u8[256]`에 격리한다. Allocation base는 native HIP alignment을 사용하고, 직렬화는 little-endian으로 고정한다.

| offset | type | field |
|---:|---|---|
| 0 | i32 | `control_abi_version=2` |
| 4 | i32 | `phase` |
| 8 | i32 | `free_dof_count` |
| 12 | i32 | `restart_dimension` |
| 16 | i32 | `max_iterations` |
| 20 | i32 | `maximum_restart_count` |
| 24 | i32 | `restart_index`, pre-start `0` |
| 28 | i32 | `cycle_start_iteration` |
| 32 | i32 | `cycle_width` |
| 36 | i32 | `column_index`, pre-column `-1` |
| 40 | i32 | `arnoldi_step_count` |
| 44 | i32 | `reorthogonalization_count` |
| 48 | i32 | `dgks_reorth_required` |
| 52 | i32 | `invariant_breakdown` |
| 56 | i32 | `candidate_required` |
| 60 | i32 | `candidate_reason_bits` |
| 64 | i32 | `triangular_breakdown` |
| 68 | i32 | `commit_required` |
| 72 | i32 | `continuation_required` |
| 76 | i32 | `pending_terminal_status` |
| 80 | i32 | `pending_termination_code` |
| 84 | i32 | `pending_restart_hint` |
| 88 | i32 | `pending_restart_flags` |
| 92 | i32 | `stagnation_checkpoint_limit` |
| 96 | i32 | `reduction_epoch` |
| 100 | i32 | `reduction_valid_mask` |
| 104 | i32 | `failure_origin` |
| 108 | i32 | `next_expected_restart` |
| 112 | i32 | `schedule_epoch`, zero prestate, post-`INIT` `1` |
| 116 | i32 | `predecessor_validation_state`: empty `0`, armed `1`, consumed `2`, commit-preflighted `3` |
| 120 | i32 | `predecessor_mask_snapshot` |
| 124 | i32 | `predecessor_reduction_epoch_snapshot` |
| 128 | f64 | `absolute_tolerance` |
| 136 | f64 | `relative_tolerance` |
| 144 | f64 | `authoritative_tolerance` |
| 152 | f64 | `stagnation_relative_tolerance` |
| 160 | f64 | `divergence_factor` |
| 168 | f64 | `cycle_beta` |
| 176 | f64 | `dot_coefficient` |
| 184 | f64 | `work_before_l2` |
| 192 | f64 | `after_first_l2` |
| 200 | f64 | `h_next_l2` |
| 208 | f64 | `candidate_l2` |
| 216 | f64 | `candidate_linf` |
| 224 | f64 | `solution_update_l2` |
| 232 | f64 | `committed_x_l2` |
| 240 | f64 | `trial_x_l2` |
| 248 | f64 | `x_scale_l2` |

`candidate_reason_bits` 0/1/2는 각각 estimated-L2 trigger, invariant/rotation breakdown, planned cycle end다. Phase는 `uninitialized`, `rhs_metrics`, `initial_state`, `restart_ready`, `arnoldi`, `dgks_second_pass`, `candidate`, `checkpoint_commit`, `between_restarts`, `terminal`, `failed`의 고정 code를 사용한다. 모든 심볼은 host가 제출한 `expected_schedule_epoch`를 검사한다. 일반 recurrence launch는 admission에 성공한 경우에만 block 0이 epoch을 한 번 증가시키지만 `PREDECESSOR_VALIDATE`와 `PREFLIGHT_COMMIT_SOURCE`는 동일 epoch의 명시적 non-advancing exception이다. State 3은 성공 verdict가 아니라 preflight ticket이며 sealed `2 -> 3`에서 snapshot은 보존된다. 축약은 별도 `expected_reduction_epoch`도 검사한다. Admission 불일치는 epoch을 변경하지 않지만, multi-block launch의 늦은 lane에서 발견된 CSR/비유한 데이터 오류는 `device_error_bits`+`active=0`으로 종단 격리되며 schedule epoch 자체는 전역 데이터 유효성의 증거가 아니다.

## 2. 단일 v2 module의 네 심볼

모든 vector/basis/dense argument는 allocation base pointer와 logical index를 따로 받는다. Host-shifted pointer는 금지한다.

### `engine_v2_fgmres_control_v2`

Single-block scalar state machine이며 mode는 다음을 고정한다.

```text
INIT, BIND_RHS, INITIAL_GATE, RESTART_BEGIN,
PRECONDITION_ACCEPT, OPERATOR_ACCEPT, DOT_ACCEPT, DGKS_DECIDE,
ARNOLDI_GIVENS, BACKSUBSTITUTE, VECTOR_ACCEPT,
CHECKPOINT_DECIDE, CHECKPOINT_FINALIZE, FINAL_GUARD,
PREDECESSOR_VALIDATE
```

- DGKS: `after_first < 0.717*work_before`
- Arnoldi: `h_next <= 64*eps*work_before`
- Givens: `hypot(u,l) <= 64*eps*max(abs(u),abs(l))`
- backsolve: `abs(pivot) <= 64*eps*max_abs_upper`, unit floor 없음
- checkpoint 우선순위: dual-gate convergence, invariant breakdown, strict divergence, stagnation, max iterations
- multi-block kernel count는 제출 전이 아니라 후속 `*_ACCEPT`에서만 증가

### `engine_v2_fgmres_vector_v2`

Mode:

```text
COPY_INITIAL_X, FORM_INITIAL_RESIDUAL,
APPLY_JACOBI_INDEXED, MGS_SUBTRACT_INDEXED,
NORMALIZE_V0, NORMALIZE_V_NEXT,
BUILD_TRIAL_X, FORM_CANDIDATE_RESIDUAL,
PREFLIGHT_COMMIT_SOURCE, COMMIT_CHECKPOINT
```

Gate:

```text
ACTIVE, DGKS_SECOND_PASS, CANDIDATE_REQUIRED, CYCLE_END, COMMIT_REQUIRED
```

### `engine_v2_fgmres_csr_spmv_indexed_v2`

Mode:

```text
INITIAL:   A*x             -> work_w
ARNOLDI:   A*Z[j]          -> work_w
CANDIDATE: A*trial(work_w) -> V[M]
```

### `engine_v2_fgmres_reduce_v2`

256-thread/512-value fixed tree 하나로 dot, scale-first LASSQ, abs-max와 각 combine stage를 처리한다. `P=ceil(F/512)`일 때 ping/pong은 각 `2P` doubles를 유지하며 LASSQ는 전체 `2P`, dot/L∞는 앞 `P`만 사용한다.

```text
DOT_W_VI
LASSQ_LOAD, LASSQ_TRUE_RESIDUAL, LASSQ_WORK_W, LASSQ_V_M
LASSQ_WORK_W_MINUS_X, LASSQ_SOLUTION_X
LINF_LOAD, LINF_TRUE_RESIDUAL, LINF_V_M
COMBINE_SUM, COMBINE_LASSQ, COMBINE_MAX
```

출력 partial이 둘 이상인 중간 stage는 반드시 `target=NONE`을 사용해 control scalar과 valid bit를 변경하지 않는다. 출력이 한 블록인 마지막 stage만 host scalar로 복사하지 않고 `DOT`, `RHS_L2/LINF`, `INITIAL_L2/LINF`, `WORK_BEFORE`, `AFTER_FIRST`, `H_NEXT`, `CANDIDATE_L2/LINF`, `UPDATE_L2`, `COMMITTED_X_L2`, `TRIAL_X_L2` 중 mode과 호환되는 named control slot에 publish한다.

## 3. V/Z/H memory ABI

```text
V[i,k] = basis_v_base[i*F+k], 0<=i<=M
Z[i,k] = basis_z_base[i*F+k], 0<=i<M
H[i,j] = dense_base[j*(M+1)+i]

H:   offset 0,                  length M*(M+1)
cos: offset M*(M+1),            length M
sin: offset M*(M+1)+M,          length M
g:   offset M*(M+1)+2*M,        length M+1
y:   offset M*(M+1)+3*M+1,      length M
total = M*M+5*M+1 doubles
```

새 O(F) buffer는 추가하지 않는다.

- `work_w`: Arnoldi work, candidate 구간에서 trial `x`
- `V[M]`: candidate SpMV 및 residual scratch
- `solution_x`, `true_residual`: checkpoint commit 전까지 이전 committed state 보존

조기 candidate `j<M-1`에서 `V[M]`은 미사용이고, `j=M-1`에서는 backsolve 후 더 이상 basis로 사용하지 않는다. 추가 physical allocation은 256-byte control state 하나다.

## 4. Fixed host launch schedule

초기 구간:

1. owned8 zero initialization; canonical producer는 8회의 sealed `hipMemsetAsync`, H2D 0
2. `CONTROL INIT`
3. `VECTOR COPY_INITIAL_X`
4. RHS L2/L∞ reductions
5. `CONTROL BIND_RHS`
6. initial SpMV, `OPERATOR_ACCEPT`
7. explicit `b-Ax0`, residual L2/L∞ reductions
8. `CONTROL INITIAL_GATE`

각 restart와 고정 column은 Jacobi, SpMV, work-before L2, first MGS, after-first L2, device DGKS decision, gated second MGS, h-next L2, V normalization, Givens, gated backsolve/trial, candidate SpMV/residual/norms, checkpoint decide/preflight/commit/finalize를 고정 순서로 제출한다. DGKS flag=false일 때도 second DOT/MGS launch는 고정 epoch을 claim하는 device no-op이며, normalization은 반드시 Givens보다 먼저다.

구현된 column-0 candidate-preparation 경계는 through-Givens 종료 `E=20+9S`, `Q=9S`에서 시작해 `E=23+10S`, `Q=10S`로 끝나며 schedule hash는 `sha256:8df0561cf0988539ed8718dc7348a1e2a85c86f474056ca156c8b8c6d5bb1aec`이다.

그 다음 candidate-residual prefix는 `SPMV(E=23+10S) -> OPERATOR_ACCEPT(E=24+10S) -> FORM_CANDIDATE_RESIDUAL(E=25+10S) -> L2(q=10S..11S-1) -> raw L∞(q=11S..12S-1)`로 `E=26+12S`, `Q=12S`에서 끝난다. Active path는 mask 1792/operator count 3, inactive/triangular path는 claim-only mask 0/operator count 2이며 `solution_x`/`true_residual`을 commit하지 않는다. Residual schedule hash는 `sha256:c2c74ad20a4b881ad209a632d021cbf368d8ae042bca5f161e82cb0bae9c4ad3`이다. Represented FP64 L2 overflow는 GPU terminal fail-closed이며 CPU early-candidate 계속 edge와 exact parity를 주장하지 않는다.

Scale-metrics prefix는 `E=26+12S`, `Q=12S`에서 trial L2 `q=12S..13S-1`, committed L2 `q=13S..14S-1`를 제출해 `E=26+14S`, `Q=14S`로 끝난다. Device predicate는 active → cycle-end → dual gate → invariant → strict divergence 우선순위를 따르며 mask는 0/1792/7936 중 하나다. Schedule hash는 `sha256:1bc8a32247ad2255cc5953f525f67b1991a62ffb9f6ca6bf299a898c11468ba8`이다.

Device predecessor validator는 같은 `E=26+14S`, `Q=14S`에서 mode `PREDECESSOR_VALIDATE=14`를 한 번 제출한다. 이 launch는 schedule/reduction epoch을 전진시키지 않는 pure gate다. 장치의 실제 predecessor state와 mask domain 0/1792/7936을 검사하고 성공 시 mask와 reduction epoch을 offset 120/124에 먼저 snapshot한 뒤 offset 116을 `empty(0) -> armed(1)`로 publish한다. Duplicate validation, snapshot 이후 mask 변경과 잘못된 epoch은 fail-closed다. Actual mask와 validator verdict는 D2H하지 않으며 fence 자체도 host-side 성공 verdict가 아니다. Validator schedule hash는 `sha256:b083896de86a808b1398d0fde4abe73726cb91f50399651274ef82dc09a5ef58`이다.

Checkpoint transaction은 `E=26+14S`, `Q=14S`의 valid predecessor에서 시작한다. Host는 live outcome을 읽어 분기하지 않고 네 launch를 항상 같은 stream에 제출한다. Sealed 경로에서 decide는 exact snapshot을 대조한 뒤 `armed(1) -> consumed(2)`로 전이하고 source preflight가 snapshot을 보존한 채 `consumed(2) -> commit-preflighted(3)` ticket을 발행한다. 기존 caller-attested raw context는 exact-zero snapshot의 `empty(0) -> commit-preflighted(3)` legacy 경로로 호환된다.

1. `CHECKPOINT_DECIDE(E=26+14S)`: `x_scale_l2=trial_x_l2+committed_x_l2`, unit floor 없음. dual gate → invariant → strict divergence → stagnation → max iterations 우선순위로 pending outcome을 만든다. 정상 decision은 result metric/header나 restart row를 쓰지 않지만 수치 실패는 terminal status/code/error header를 fail-closed로 기록한다.
2. `PREFLIGHT_COMMIT_SOURCE(E=27+14S, mode=9)`: non-advancing row다. Commit gate가 true이면 `work_w`와 `V[M]`만 읽어 모든 source가 finite인지 검사하고 destination/snapshot은 쓰지 않는다. False이면 source/destination을 읽지 않는다. Invalid source는 error bit 4, origin 2, termination code 47과 `active=0`으로 fail-closed한다.
3. gated `COMMIT_CHECKPOINT(E=27+14S)`: 모든 lane이 state 3, active 1, error bits 0과 exact legacy/sealed snapshot shape를 확인한 뒤 pure copy만 수행한다. Late finite 검사나 rollback branch가 없으며 false이면 네 vector를 읽거나 쓰지 않는다.
4. `CHECKPOINT_FINALIZE(E=28+14S)`: pending outcome을 재계산·대조한 뒤 restart row와 result-metric header를 쓰는 유일한 publisher다. Snapshot과 transient를 먼저 clear하고 state 0을 마지막에 publish한다. 성공 종료는 `E=29+14S`, `Q=14S`다.

Mask 0/1792/7936은 decide, preflight와 commit에서 보존되고 finalizer가 mask/snapshot을 먼저, validation state를 마지막에 0으로 지운다. 정상 transaction의 `active`도 finalizer 전까지 유지된다. 단 terminal numerical failure는 result metrics/restart row 없이 `active=0`과 terminal status/code/error header를 먼저 기록할 수 있다. Checkpoint schedule hash는 `sha256:2423da989b6cd419b7c4bef46d6c76f2120825a0c840cb516803bb2643ca11e5`다. 현재 combined v2 kernel ABI는 `sha256:bb5b94457fbf3be4c5f2b38dda3f50c8a757094e0b97fb4d7288e7bdbf4db39f`, fixed HIP source는 `sha256:ce4353f61fc3e8cd1311ad52ce50f21a677c7bfa865a2656aa5447b6ec104a83`다.

v0.2.20 canonical producer 당시의 combined ABI `sha256:d719aebffadafa0c076bb4ff395df35e7b4bd888bdb613b8be9ff7ef0f20335d`, fixed HIP source `sha256:cdb8917b8553ceceed047b0c9b3e091afe9d80bccfece8242a778b5d56e00b18`와 three-row checkpoint schedule `sha256:d9b9115287e3b5839096e3f4417c04899ffc7592864483d918be55deaf4b4442`는 historical identity다. v0.2.15 raw checkpoint 검증 당시의 combined ABI `sha256:31fbff2fa25c221a99f28e170818990a8ed71211169d239e05d28628941941c9`와 fixed HIP source `sha256:34049a08119b19382c26fbe310f957d7af9c41db037dfcbab521828732025e9b`도 historical snapshot이다. 현재 ABI/source identity로 재해석하지 않는다.

Host는 항상 `R*M` column schedule을 제출한다. `j>=cycle_width`, DGKS/candidate/commit 미필요, terminal 후의 work는 device gate가 no-op한다. Preflight는 유효 commit에서 두 source를 추가로 한 번 읽는 parallel O(F) row이며 새 F-sized workspace는 없다. Raw recurrence 구간의 H2D, D2H, allocation, sync, fallback은 모두 0이어야 한다. Completion에서만 solve record, solution, residual을 D2H하고 한 번 fence한다.

`M<=16`은 고정이지만 launch count와 실제 latency가 선형임을 자동으로 증명하지 않는다. Correctness 폐쇄 후 HIP graph/capture와 latency benchmark를 별도로 수행한다.

## 5. 구현 순서

현재 1~4번, 5번 중 valid-predecessor restart-1/column-0 checkpoint raw numerical slice와 scoped invalid-source atomicity, 6번 중 caller-attested transaction owner와 live parent3+owned8 resource owner, 그 위의 canonical first-column device producer·validator까지 구현되었다. Native raw 결과는 device priority predicate, `x_scale_l2`, source preflight, pure-copy commit, finalizer-only publish, masks 0/1792/7936과 poison 보존을 독립 GPU-tree oracle와 비교한 unsigned non-promoting evidence다. Canonical producer hardware gate는 actual HIP chain에서 owned8 zero initialization, exact `27+14S` prefix, validator의 armed snapshot과 one-fence completion을 verification-only D2H로 관찰했지만 product receipt는 actual mask/verdict를 host에 노출하지 않는다.

v0.2.20 focused 기록은 recurrence plan `61 passed`, RTC `99 passed`, delegated producer projection `14 passed`, canonical producer `8 passed`다. Actual `gfx1030` required gate는 raw validator arm→consume→clear checkpoint `5 passed`와 canonical producer chain `1 passed`를 관찰했다. 이 수치는 first-column contract evidence이며 broad solver parity나 승격 증거가 아니다.

v0.2.21 atomicity focused 기록은 recurrence plan/schema `63 passed`, RTC owner/source `100 passed`, checkpoint context 신규·인접 `77 passed`, actual `gfx1030` recurrence `13 passed`와 native race stress `5/5`다. 별도 full checkpoint context 전수 회귀는 `261 passed in 523.33s (0:08:43)`를 통과했다. Source preflight의 destination access 0, late invalid source의 두 destination 전체 byte 보존, valid legacy/sealed `0 -> 3 -> 0`/`2 -> 3 -> 0`와 gate-false no-read를 확인했다. 독립 감사에서 diagnostic first-error CAS, predecessor state-code ABI binding, complete row/pointer frozen binding과 u8 role alignment를 보강한 뒤 남은 High/Medium 결함은 없었다. Ruff format/check, py_compile, canonical hashes와 actual HIP source hash assertion도 통과했다. 이 결과의 atomicity scope는 exact registered nonoverlap allocation, same stream, exclusive source ownership과 fixed four-row owner sequence이며 arbitrary raw duplicate/external writer/device fault를 포함하지 않는다. Sealed lifecycle과 common invalid-source branch는 각각 native 검증됐지만 sealed+invalid-source 조합 전용 native case는 아직 없다.

1. v2 plan/schema에 256-byte control buffer와 identity/layout hash 추가
2. v2 control ABI, deterministic RHS/residual L2·L∞ reduction/publish, initial `x` copy·`b-Ax0`·dual gate·`I=0`
3. indexed Jacobi/SpMV, one Arnoldi column, first MGS와 device DGKS flag
4. full MGS/DGKS, h-next, V normalization, Givens, scale-relative backsolve, candidate replay
5. commit, false-convergence continuation, stagnation/divergence/breakdown/final guard; 현재 column-0 checkpoint 부분만 구현
6. live allocation/context, strict completion/export receipt, poison/retry cleanup; 현재 caller-attested checkpoint owner, resource-only live parent/allocator context와 single-use canonical predecessor child까지 partial 구현
7. CPU oracle·GPU-tree oracle·native hardware parity 및 iteration host-copy-zero gate

## 6. 필수 검증

- 256-byte field offset/type, offset 116/120/124의 legacy `0→3→0`와 sealed `1→2→3→0`, mode/gate/reason enum, interface/source hash drift 거부
- shifted pointer 0, base+logical-index만 사용
- reduction `F=1,255,256,511,512,513` 및 multi-stage ping/pong
- zero/signed-zero/subnormal/near-overflow/NaN/Inf fail-closed
- nonzero `x0`, zero RHS, 한 gate만 통과, dual gate 통과, `I=0`
- `M=2,I=5 -> 2+2+1`, DGKS second pass, happy/unhappy breakdown, false convergence
- failure operator/preconditioner count의 CPU oracle 일치
- raw recurrence D2H/sync/allocation/H2D/fallback 0
- ambiguous launch, fence/ack/free/module/token retry와 parent poison
- exact registered nonoverlap/same-stream/exclusive-owner fixed four-row invalid-source multi-block commit all-or-nothing, raw duplicate checkpoint 정책, 외부 writer exclusion
- decide/preflight/commit/finalize 사이의 enqueue 실패와 ambiguity poison
- typed allocation descriptor의 exact-base/range-overlap 검사와 네 launch의 same-buffer identity
- 실제 `gfx1030` compile/symbol, 조건부 native numerical gate

GPU fixed tree와 CPU `math.fsum`/순차 LASSQ는 각각 결정적이지만 bitwise 동일하지 않을 수 있다. 경계 fixture는 GPU-tree oracle 또는 명시적 수치 허용오차를 사용하고 bitwise recurrence parity를 주장하지 않는다.

## 7. Claim boundary

현재 `plan_schema_implemented`, `candidate_spmv_residual_l2_raw_linf_implemented`, `device_scale_metrics_priority_predicate_implemented`, `trial_committed_x_norms_implemented`, `raw_x_scale_l2_implemented`, `raw_checkpoint_decide_preflight_gated_commit_finalize_implemented`, `native_first_column_checkpoint_raw_slice_observed`, `caller_attested_checkpoint_range_lease_enqueue_fence_context_implemented`, `live_krylov_parent_integrated`, `allocator_provenance_bound`, `resource_owner_ready`는 true다. Exact registered nonoverlap allocation, same stream, exclusive source ownership과 fixed four-row owner sequence에 한해 `invalid_source_destination_atomicity_proven`도 true다. Canonical producer의 fenced receipt에 한해 `owned_content_initialized`, `canonical_producer_prefix_fenced`, `device_mask_domain_gate_bound`, exact16 projection과 same-runtime/device/stream binding도 true다.

Caller-attested context에서는 range/shift overlap, same-buffer four-launch enqueue/state tracking, ambiguity poison과 exact-runtime fence가 true다. Live resource context에서는 parent3+owned8 exact11, same runtime/device/stream, internal RTC owner와 allocator provenance가 true다. Canonical child는 CSR3+scratch2 delegated projection, sealed memset과 device validator gate를 더하지만 actual mask와 validator outcome을 host가 관찰하지 않으며 그 conditional capability를 checkpoint transaction이 아직 소비하지 않는다. 따라서 `actual_mask_host_observed`, `device_validation_outcome_host_observed`, `authoritative_predecessor_proven`, `checkpoint_transaction_ready`, `authoritative_checkpoint_transaction`, `sealed_predecessor_checkpoint_transaction_integration`, `later_columns_and_restarts_implemented`, `full_device_recurrence_implemented`, `live_solver_ready`, `solution_ready`, `iteration_host_copy_zero_proven`, `native_full_recurrence_parity`, O(N), speedup, ResultIR 통합, SPD/PCG, commercial readiness는 모두 false다. Arbitrary raw duplicate COMMIT, external writer/DMA/device fault 범위의 전역 atomicity도 false다. 다음 우선순위는 sealed capability를 live transaction과 결속하고 later columns/restarts로 확장하는 것이다.
