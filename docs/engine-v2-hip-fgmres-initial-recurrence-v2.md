# Engine v2 HIP FGMRES initial + first-column checkpoint transaction recurrence v2

- 상태: v0.2.21, Phase 0 valid-predecessor raw checkpoint slice와 scoped invalid-source atomicity implemented, `contract_only`
- Transaction owner: [first-column checkpoint transaction context v2](engine-v2-hip-fgmres-checkpoint-context-v2.md)
- Canonical producer: [device-sealed canonical first-column predecessor v1](engine-v2-hip-fgmres-canonical-predecessor-v1.md)
- 전체 설계: [HIP FGMRES full recurrence ABI v2](engine-v2-hip-fgmres-recurrence-abi-v2.md)
- CPU 수치 oracle: [CPU fixed-restart FGMRES reference v1](engine-v2-cpu-fgmres-reference-v1.md)
- 상위 기준: [Structural Solver Engine v2 마스터 로드맵](structural-solver-engine-v2-master-roadmap.md)

이 단계는 v2 전체 FGMRES 중 initial gate, restart 1/column 0 Arnoldi/DGKS/Givens, candidate preparation, SpMV, in-place residual, raw candidate L2/L∞와 trial/committed scale metrics를 거쳐 `CHECKPOINT_DECIDE -> PREFLIGHT_COMMIT_SOURCE -> gated COMMIT_CHECKPOINT -> CHECKPOINT_FINALIZE`까지 실행한다. v0.2.21 source preflight는 destination을 전혀 쓰지 않은 채 commit source의 유한성을 모든 block에서 먼저 검사해 late invalid lane에서도 두 destination 전체 bytes를 보존한다. 이 atomicity는 exact registered nonoverlap allocation, same stream, exclusive source ownership과 fixed four-row owner sequence에만 적용한다.

v0.2.20 canonical producer는 live exact11과 delegated CSR3/scratch2를 결속하고 owned8 zero initialization 뒤 `INIT`부터 device seal까지 exact `27+14S` kernel row를 제출한다. 그러나 product receipt는 actual mask와 validator verdict를 D2H하지 않으며, 발행 capability는 아직 checkpoint transaction이 소비하지 않는 conditional device capability다. Companion transaction context의 predecessor도 계속 caller attestation이므로 raw atomicity 구현이 authoritative predecessor, transaction 또는 solution receipt를 만들지는 않는다.

## 1. 구현 구성

| 계층 | 구현 |
| --- | --- |
| allocation/control plan | exact `HipFgmresPlanV1`을 replay하고 7 borrowed + 10 owned buffer를 고정한다. v1 대비 추가 allocation은 `u8[256]` control state 하나다. |
| public record | v1과 동일한 `192+72R` field extent를 유지하되 producer recurrence ABI는 2로 분리한다. |
| HIPRTC module | `control`, `vector`, `csr_spmv_indexed`, `reduce` 네 C symbol을 하나의 code object로 compile/load한다. |
| reduction | 256 thread/512 value fixed tree, scale-first LASSQ L2, abs-max L∞와 signed FP64 dot, ping/pong multistage combine를 사용한다. |
| CPU oracle | HIP과 동일한 tree 병합 순서를 BLAS/SciPy 없이 재생하고 candidate residual, trial/committed scale metrics와 checkpoint transaction을 독립 계산한다. |

권위 소스:

- `src/structural_analysis/engine_v2/assembly_backend/fgmres_recurrence_plan_v2.py`
- `src/structural_analysis/schemas/hip_fgmres_recurrence_plan_v2.schema.json`
- `src/structural_analysis/engine_v2/assembly_backend/fgmres_rtc_v2.py`
- `src/structural_analysis/engine_v2/assembly_backend/fgmres_context_v2.py`
- `src/structural_analysis/engine_v2/assembly_backend/kernels/engine_v2_fgmres_v2.hip.cpp`
- `src/structural_analysis/engine_v2/solvers/gpu_tree_reference_v2.py`

## 2. Control과 schedule ABI

Control state는 little-endian `32*i32 + 16*f64 = 256 bytes`다. Offset 112의 `schedule_epoch`와 offset 96의 `reduction_epoch`이 독립적으로 duplicate, skip, reorder를 검사한다. `INIT` 전에는 256 byte 전체가 정확한 0이어야 하며, 성공 후 `phase=rhs_metrics`, `schedule_epoch=1`이다. Offset 116/120/124는 각각 `predecessor_validation_state`, `predecessor_mask_snapshot`, `predecessor_reduction_epoch_snapshot`이다. State code는 empty `0`, armed `1`, consumed `2`, commit-preflighted `3`이다. State 3은 성공 verdict가 아니라 fixed transaction ticket이며 finalizer가 snapshot을 먼저 clear한 뒤 state 0을 마지막에 publish한다.

`S` = `F`를 512단위로 1개 scalar까지 축약하는 stage 수라고 하면 initial schedule은 다음을 hash에 고정한다.

| 순서 | 예상 schedule |
| --- | ---: |
| `CONTROL INIT` | `0 -> 1` |
| `VECTOR COPY_INITIAL_X` | `1` |
| RHS L2 / L∞ | `2..1+2S` |
| `CONTROL BIND_RHS` | `2+2S` |
| initial SpMV / `OPERATOR_ACCEPT` | `3+2S`, `4+2S` |
| `FORM_INITIAL_RESIDUAL` | `5+2S` |
| initial L2 / L∞ | `6+2S..5+4S` |
| `CONTROL INITIAL_GATE` | `6+4S` |

비종단 initial gate 뒤의 canonical first-column schedule은 `B=7+4S`로 두고 다음을 partial/completion schedule hash에 고정한다. `B`를 소유하는 mode는 `RESTART_BEGIN` 하나뿐이다.

| 순서 | 예상 schedule / reduction epoch |
| --- | --- |
| `RESTART_BEGIN(r=1,c=-1)` | `B` |
| `NORMALIZE_V0`, `APPLY_JACOBI_INDEXED` | `B+1`, `B+2` |
| `PRECONDITION_ACCEPT`, Arnoldi SpMV, `OPERATOR_ACCEPT` | `B+3`, `B+4`, `B+5` |
| `WORK_BEFORE` LASSQ | `schedule=13+q`, `q=4S..5S-1` |
| first-pass row-0 signed dot | `schedule=13+q`, `q=5S..6S-1` |
| `DOT_ACCEPT(row=0,pass=0)` | `13+6S` |
| `MGS_SUBTRACT_INDEXED(row=0)` | `14+6S` |
| `AFTER_FIRST` LASSQ | `schedule=15+q`, `q=6S..7S-1` |
| `DGKS_DECIDE(pass=0)` | `15+7S`, post-state `schedule=16+7S` |

그 뒤 completion schedule은 분기 여부와 무관하게 고정 launch envelope를 유지한다.

| 순서 | 예상 schedule / reduction epoch |
| --- | --- |
| second-pass row-0 signed dot | `schedule=16+q`, `q=7S..8S-1` |
| `DOT_ACCEPT(row=0,pass=1)` | `16+8S` |
| gated `MGS_SUBTRACT_INDEXED(row=0)` | `17+8S` |
| `H_NEXT` LASSQ | `schedule=18+q`, `q=8S..9S-1` |
| `NORMALIZE_V_NEXT(logical_index=1)` | `18+9S` |
| `ARNOLDI_GIVENS(row=-1,pass=-1)` | `19+9S`, post-state `schedule=20+9S` |

`DOT_ACCEPT`는 signed dot을 packed dense의 임시 `y[0]`에 복사하고 `H[0,0]+=y[0]` 후 DOT slot/bit만 소비한다. MGS는 누적 H가 아니라 그 pass의 `y[0]`를 읽는다. DGKS는 `after_first < 0.717*work_before`를 strict 비교한다. Flag가 true이면 second DOT+MGS를 수치 실행한다. False이면 second DOT reduction과 gated MGS는 같은 schedule/reduction epoch만 claim하고 수치 입출력을 읽거나 쓰지 않으며, 사이의 `DOT_ACCEPT`는 schedule을 claim하고 `y[0]=+0.0`만 canonicalize하며 H를 누적하지 않는다.

`H_NEXT` LASSQ 후 먼저 `V1`을 정규화한 뒤 Givens를 적용한다. Arnoldi breakdown threshold는 `tau=64*eps=2^-46` 및 `tau*work_before`이다. `h_next` 가 threshold 이하이면 invariant flag를 설정하고 `V1` 전체를 canonical `+0.0`으로 쓰며, 그 외에는 `V1=w/h_next`를 계산한다. Givens breakdown은 `hypot(upper,lower) <= tau*max(abs(upper),abs(lower))`로 검사한다. Candidate reason bit 0/1/2는 각각 `estimated<=solver_tolerance`, invariant/Givens breakdown, `column+1>=cycle_width`를 뜻한다. Bits가 0이 아니면 `candidate_required=1`, phase=candidate이고, 그 외에는 phase=arnoldi다. 이 slice에서 stored column은 계속 0이다. 성공 후 effective restart/iteration/Arnoldi step은 1/1/1, operator/preconditioner count는 2/1이며 reorthogonalization count는 DGKS true일 때만 1이다.

Through-Givens의 정확한 종료 상태 `E=20+9S`, `Q=9S`, valid mask 0에서 candidate-preparation prefix는 다음으로 고정된다.

| 순서 | 예상 schedule / reduction epoch |
| --- | --- |
| `BACKSUBSTITUTE(r=1,c=0)` | `E=20+9S` |
| gated `BUILD_TRIAL_X(logical_index=0)` | `E=21+9S` |
| `UPDATE_L2` LASSQ | `E=22+q`, `q=9S..10S-1` |
| `VECTOR_ACCEPT(r=1,c=0)` | `E=22+10S`, 종료 `E=23+10S`, `Q=10S` |

Active candidate의 backsolve는 `abs(pivot) <= 2^-46*max_abs_upper`를 사용하며 unit floor를 두지 않는다. 성공하면 `work_w=x+y[0]Z[0]`를 multiply-then-add/no-FMA 순서로 계산하고 `work_w-x`의 scale-first LASSQ를 `UPDATE_L2` bit 10에 publish한다. `VECTOR_ACCEPT`는 유한·음이 아닌 update norm을 검사한 뒤 향후 `CHECKPOINT_DECIDE`를 위해 valid mask `1024`만 보존한다. `candidate_required=false`와 backsolve에서의 triangular breakdown은 나머지 schedule/reduction epoch을 전부 claim하지만, 그 이후 launch들은 candidate numeric/scratch를 읽거나 쓰지 않고 target을 publish하지 않아 종료 mask가 0이다. Triangular breakdown은 `invariant_breakdown=1`로 OR-promote한다.

Candidate-preparation 종료 `E=23+10S`, `Q=10S`에서 candidate-residual metrics prefix는 다음으로 고정된다.

| 순서 | 예상 schedule / reduction epoch |
| --- | --- |
| candidate SpMV `work_w -> V[M]` | `E=23+10S` |
| `OPERATOR_ACCEPT` | `E=24+10S` |
| in-place `V[M]=reduced_load-V[M]` | `E=25+10S` |
| candidate L2 LASSQ | `E=26+q`, `q=10S..11S-1` |
| candidate raw L∞ max | `E=26+q`, `q=11S..12S-1`; 종료 `E=26+12S`, `Q=12S` |

유효한 candidate는 operator count를 3으로 올리고 `UPDATE_L2`, `CANDIDATE_L2`, `CANDIDATE_LINF` bit을 합친 mask `1792`를 보존한다. Candidate=false 또는 triangular breakdown은 모든 epoch을 claim하지만 operator count 2, mask 0을 유지하고 CSR/load/`work_w`/`V[M]`/reduction scratch/target을 읽거나 쓰지 않는다. Native gate는 inactive `V[M]`에 주입한 NaN poison의 bit pattern까지 보존했다. Active replay 후에도 `solution_x`/`true_residual`은 committed state로 남고, trial은 `work_w`, candidate residual은 `V[M]`에 만 있다.

L∞는 raw `max(abs(V[M]))`만 저장한다. Scaled authoritative 비교값 자체는 transient이며 persist하지 않고, 뒤의 checkpoint decide가 그 비교 결과를 pending outcome으로 기록한다. Scale-first LASSQ의 최종 represented FP64 L2가 overflow하면 GPU는 의도적으로 terminal fail-closed한다. CPU early-candidate inf-gate가 계속할 수 있는 이 edge에 대해 exact CPU/GPU parity를 주장하지 않는다.

Candidate-residual 종료 `E=26+12S`, `Q=12S`에서 scale-metrics prefix는 고정된 2S reduction을 제출한다.

| 순서 | 예상 schedule / reduction epoch |
| --- | --- |
| `TRIAL_X_L2` (`work_w`) | `E=26+q`, `q=12S..13S-1` |
| `COMMITTED_X_L2` (`solution_x`) | `E=26+q`, `q=13S..14S-1`; 종료 `E=26+14S`, `Q=14S` |

Device-only `scale_metrics_required`는 active candidate → planned cycle-end bit 2 → dual gate → invariant breakdown → strict divergence 순서를 유지한다. False이면 2S epoch만 claim하고 source/scratch/target을 읽거나 쓰지 않는다. Inactive candidate는 mask 0, active이지만 scale불필요인 경로는 1792, scale=true는 trial L2 후 committed L2까지 publish해 7936을 보존한다. `COMMITTED_X_L2`의 기존 future-consumer metadata는 바꾸지 않았다.

Scale-metrics 종료 `E=26+14S`, `Q=14S`에서 canonical producer는 다음 non-advancing device seal을 제출한다.

| 순서 | 예상 schedule / reduction epoch | seal 계약 |
| --- | --- | --- |
| `PREDECESSOR_VALIDATE(mode=14)` | `E=26+14S`, `Q=14S`; 종료 epoch 동일 | actual device state와 mask domain 0/1792/7936을 검사하고 mask/reduction epoch snapshot을 먼저 쓴 뒤 state를 `empty(0) -> armed(1)`로 publish한다. Duplicate validation과 이후 snapshot drift는 fail-closed다. |

Validator schedule hash는 `sha256:b083896de86a808b1398d0fde4abe73726cb91f50399651274ef82dc09a5ef58`다. 이 launch의 fence는 queue completion만 관찰하며 actual mask나 validation verdict를 host 성공 판정으로 승격하지 않는다.

같은 `E=26+14S`, `Q=14S`의 valid predecessor에서 checkpoint transaction은 항상 네 launch를 같은 stream에 고정 순서로 제출한다. Sealed 경로와 기존 caller-attested legacy 경로를 함께 지원한다.

| 순서 | 예상 schedule / reduction epoch | 수치·publish 계약 |
| --- | --- | --- |
| `CHECKPOINT_DECIDE` | `E=26+14S`, `Q=14S` | Sealed 경로는 armed snapshot과 live mask/epoch을 대조하고 `armed(1) -> consumed(2)`로 전이한다. Legacy raw 경로는 state/snapshot 모두 0이어야 한다. 그 뒤 `x_scale_l2=trial_x_l2+committed_x_l2`, unit floor 없음으로 dual gate → invariant → strict divergence → stagnation → max iterations 우선순위를 계산하고 pending outcome을 기록한다. |
| `PREFLIGHT_COMMIT_SOURCE(mode=9)` | `E=27+14S`, `Q=14S`; non-advancing | Legacy `0 -> 3`, sealed `2 -> 3` ticket을 발행한다. `commit_required=true`이면 `work_w`와 `V[M]`만 읽어 전체 source finite를 검사하며 destination과 snapshot은 쓰지 않는다. False이면 source/destination을 읽지 않는다. Invalid source는 error bit 4, origin 2, code 47, `active=0`으로 fail-closed한다. |
| gated `COMMIT_CHECKPOINT` | `E=27+14S`, `Q=14S` | 모든 lane이 state 3, active 1, error bits 0과 exact legacy/sealed snapshot shape를 확인한 뒤 pure copy만 수행한다. Late finite 검사나 rollback branch는 없다. False이면 source와 destination을 읽거나 쓰지 않는다. |
| `CHECKPOINT_FINALIZE` | `E=28+14S`, `Q=14S`; 성공 종료 `E=29+14S`, `Q=14S` | Sealed 경로는 state 3과 preserved snapshot을 다시 대조한다. Pending decision을 재계산·대조한 뒤 restart row와 result-metric header를 쓰는 유일한 publisher이며, 성공 시 mask와 snapshot을 먼저 지우고 validation state를 마지막에 0으로 clear해 terminal/continuation phase를 확정한다. |

Mask 0/1792/7936은 decide, preflight와 commit 동안 그대로 유지되고 finalizer만 0으로 지운다. 정상 transaction에서 solve record의 `active`도 finalizer 전까지 1이다. 단 terminal numerical failure는 finalizer 전에도 `active=0`과 terminal status/code/error header를 기록하며 result metrics/restart row는 publish하지 않는다. Restart row는 나머지 field를 먼저 쓴 뒤 `restart_index` sentinel을 마지막에 쓴다. Finalizer는 snapshot과 transient를 먼저 지우고 state `3 -> 0`을 마지막에 수행한다.

계약 해시는 다음이다.

- candidate-preparation schedule: `sha256:8df0561cf0988539ed8718dc7348a1e2a85c86f474056ca156c8b8c6d5bb1aec`
- candidate-residual schedule: `sha256:c2c74ad20a4b881ad209a632d021cbf368d8ae042bca5f161e82cb0bae9c4ad3`
- candidate scale-metrics schedule: `sha256:1bc8a32247ad2255cc5953f525f67b1991a62ffb9f6ca6bf299a898c11468ba8`
- predecessor validator schedule: `sha256:b083896de86a808b1398d0fde4abe73726cb91f50399651274ef82dc09a5ef58`
- checkpoint transaction schedule: `sha256:2423da989b6cd419b7c4bef46d6c76f2120825a0c840cb516803bb2643ca11e5`
- current combined v2 kernel ABI: `sha256:bb5b94457fbf3be4c5f2b38dda3f50c8a757094e0b97fb4d7288e7bdbf4db39f`
- current fixed HIP source: `sha256:ce4353f61fc3e8cd1311ad52ce50f21a677c7bfa865a2656aa5447b6ec104a83`

v0.2.20 canonical producer 당시 combined ABI `sha256:d719aebffadafa0c076bb4ff395df35e7b4bd888bdb613b8be9ff7ef0f20335d`, fixed HIP source `sha256:cdb8917b8553ceceed047b0c9b3e091afe9d80bccfece8242a778b5d56e00b18`와 three-row checkpoint schedule `sha256:d9b9115287e3b5839096e3f4417c04899ffc7592864483d918be55deaf4b4442`는 historical identity다. v0.2.15 raw checkpoint 검증 당시 combined ABI `sha256:31fbff2fa25c221a99f28e170818990a8ed71211169d239e05d28628941941c9`와 fixed HIP source `sha256:34049a08119b19382c26fbe310f957d7af9c41db037dfcbab521828732025e9b`도 historical snapshot이다. 현재 identity로 재사용하지 않는다.

모든 pending operation은 최초에 결속된 하나의 stream에만 제출할 수 있다. 다른 stream은 completion fence가 관찰되고 pending reservation이 소비되기 전에 host에서 거부된다. v0.2.21 checkpoint owner는 exact four-row sequence와 같은 stream을 결속하고, preflight/commit에는 동일한 exact 11-pointer snapshot을 전달한다. Binding witness는 exact loaded runtime의 `hipStreamSynchronize`와 sealed `hipMemsetAsync` callable을 함께 고정하고 kernel/memset acceptance interval을 같은 pending accounting에 포함한다. Canonical producer는 8개 owned memset과 exact `27+14S` kernel row를 한 fence로 소비하지만 event/sequence receipt를 발행하지 않는다. Reduction의 pre-barrier admission은 block-shared flag로 통일해 lane 일부만 return한 뒤 `__syncthreads()`에 진입하는 경우를 금지한다.

`schedule_epoch`는 launch admission 순서의 증거이지 전역 수치 성공의 증거가 아니다. Multi-block의 늦은 lane에서 비유한/CSR 오류가 발견되면 `device_error_bits`, `active=0`, terminal failure로 격리한다.

## 3. Reduction publish 규칙

- output partial이 2개 이상인 stage는 `target=NONE`이며 scalar/valid bit를 publish하지 않는다.
- output이 1개인 마지막 stage만 mode과 호환되는 named target을 publish한다.
- RHS L2/L∞는 control의 candidate norm slot을 임시 사용하고 `BIND_RHS`가 valid bit와 slot을 지운 뒤 initial L2/L∞가 재사용한다.
- 이미 valid한 target의 중복 publish, output과 active source/control/record의 exact allocation-base alias, combine input/output base alias, invalid LASSQ pair는 fail-closed다. Raw launch API는 exact-base만 검사한다. v0.2.16 companion context는 11개 allocation의 exact extent·alignment·uintptr overflow와 모든 local/process-global shifted range overlap을 별도로 검증한다.
- numerical `atomicAdd`, shifted pointer, host scalar publish, fast-math, dense `lstsq`/pseudoinverse, solver fallback은 없다.

## 4. 검증 현황

계약 및 독립 oracle은 candidate residual 후 device priority predicate, trial/committed L2 tree, checkpoint decision/commit/finalize, predicate-false poison preservation, masks 0/1792/7936, `x_scale_l2` overflow precommit fail-closed와 terminal/continuation priority를 다룬다. Raw numerical checkpoint v0.2.15 검증은 plan `58 passed`, RTC `57 passed`, oracle `95 passed`, integrated focused `222 passed`, hardware `12 passed`(기존 full path 7 + synthetic boundary 5), 전체 FGMRES `289 passed`, broad `1019 passed`와 actual HIPRTC compile/load를 통과했다. v0.2.16 transaction owner는 context `246 passed`, raw RTC `60 passed`, 기존 HIP context와의 결합 `258 passed`, plan `58 passed`, oracle `95 passed`, 실제 hardware `12 passed`, 전체 FGMRES `538 passed`, broad `1268 passed`를 skip/fallback 0으로 통과했다.

v0.2.20 validator/producer historical focused 기록은 recurrence plan `61 passed`, RTC `99 passed`, delegated physical projection `14 passed`, canonical producer `8 passed`다. 당시 actual `gfx1030` required gate는 raw checkpoint의 validator arm→consume→clear `5 passed`와 canonical full-prefix producer `1 passed`를 확인했다. 후자의 control D2H는 테스트 oracle 전용이며 product telemetry의 D2H 0 claim을 바꾸지 않는다.

v0.2.21 atomicity focused 기록은 recurrence plan/schema `63 passed`, RTC owner/source `100 passed`, checkpoint context 신규·인접 `77 passed`, actual `gfx1030` recurrence `13 passed`와 native repeated race stress `5/5`다. 별도 full checkpoint context 전수 회귀는 `261 passed in 523.33s (0:08:43)`를 통과했다. Source preflight의 destination access count가 0이고, 늦은 lane에 비유한 source를 주입해도 `solution_x`와 `true_residual` 전체 raw byte sentinel이 변하지 않음을 확인했다. Valid legacy/sealed lifecycle `0 -> 3 -> 0`/`2 -> 3 -> 0`, gate-false source/destination no-read, error bit 4/origin 2/code 47 fail-closed도 검증했다. 독립 감사에서 diagnostic first-error CAS, state-code ABI binding, complete row/pointer frozen binding과 u8 role alignment를 보강한 뒤 남은 High/Medium 결함은 없었다. Ruff format/check, py_compile, canonical hashes와 actual HIP source hash assertion도 통과했다. 이 결과는 scoped raw fixed-four-row atomicity 증거이며 canonical capability 소비나 authoritative transaction 증거가 아니다. Sealed lifecycle과 common invalid-source branch는 각각 native 검증됐지만 sealed+invalid-source 조합 전용 native case는 아직 없다.

실제 RX 6900 XT `gfx1030` gate에서는 `F=513` diagonal CSR과 nonzero `x0`를 사용해 두 block/two-stage 초기 schedule을 실행했다. Completion에서만 `x`, `Ax`, residual, control, record를 D2H하고 stream fence 1회를 관찰했다. GPU-tree oracle과 vector/네 norm/gate가 일치했고 `schedule_epoch=15`, `reduction_epoch=8`, operator count 1, `device_error_bits=0`, fallback 0을 확인했다. 이는 initial slice의 조건부 native test이며 signed promotion receipt나 전체 recurrence parity가 아니다.

동일한 `F=513` nonfinal LASSQ stage를 같은 schedule/reduction epoch로 중복 제출한 native 회귀에서도 stream이 hang 없이 완료되고, invalid-control error bit·`active=0`·failed phase·보존된 epoch으로 종료됨을 확인했다.

같은 실제 GPU에서 candidate residual, scale metrics와 checkpoint transaction을 completion 전 D2H 없이 실행했다. Valid-predecessor full path와 five synthetic boundary에서 device priority, `x_scale_l2=trial+committed`, gated commit, finalizer-only restart-row/result-metric publish, masks 0/1792/7936과 poison 보존이 독립 GPU-tree oracle와 일치했다. Hardware `12 passed`는 unsigned non-promoting raw-slice evidence이며 live transaction ownership이나 완전 recurrence parity가 아니다.

독립 안전 감사와 v0.2.21 source-preflight 구현 후 다음 경계로 분리했다.

- exact registered nonoverlap allocation, 같은 stream, exclusive source ownership과 fixed four-row owner sequence에서는 active commit source의 late NaN/Inf에도 destination all-or-nothing을 보존한다. Arbitrary raw duplicate COMMIT, 외부 writer/DMA/device fault는 이 증거 범위 밖이다.
- raw API 자체는 exact pointer equality만 거부하지만 v0.2.16 context가 exact extent·alignment·uintptr와 shifted/range overlap을 검증한다. 별도 live resource/canonical producer 경로는 actual allocator lineage exact11과 delegated CSR3/scratch2 physical projection을 결속한다.
- 현재 context가 decide/preflight/commit/finalize를 same-buffer host transaction으로 묶고 중간 rejection/ambiguity poison, exact-runtime fence와 acknowledgement retry를 소유한다. 이는 caller-attested predecessor에 한정된다.
- v0.2.20 canonical producer는 owned8 initialization과 validator arm까지 fence하지만, 그 conditional capability를 위 caller-attested checkpoint context가 소비하지 않으므로 authoritative checkpoint transaction은 여전히 성립하지 않는다.
- context 경로는 predecessor single-use로 duplicate transaction을 거부한다. Context 밖 raw API의 native duplicate checkpoint 정책은 별도 hardware 회귀로 고정되지 않았다.

## 5. Claim boundary

현재 허용되는 claim은 다음까지다.

- v2 allocation/control ABI plan과 strict schema가 구현되었다.
- fixed-source 4-symbol module이 `gfx1030`으로 compile/load되고 valid-predecessor first-column checkpoint transaction raw path가 조건부 native gate에서 독립 GPU-tree oracle와 일치했다.
- Python raw launch owner와 plan·schema hash binding이 fixed four-row checkpoint transaction schedule까지 있다.
- Caller-attested companion context에 exact typed range registry, exclusive raw lease, same-stream four-launch transaction, ambiguity poison과 exact-runtime fence/cleanup이 있다.
- Live canonical child는 exact16 physical projection, sealed owned8 zero initialization, exact `27+14S` prefix와 non-advancing device validator를 one-fence conditional capability로 묶는다.

다음은 true다: valid predecessor에 대한 raw `x_scale_l2`, `CHECKPOINT_DECIDE`, source-only `PREFLIGHT_COMMIT_SOURCE`, gated pure-copy `COMMIT_CHECKPOINT`, `CHECKPOINT_FINALIZE` 수치 slice와 actual HIPRTC 실행. Exact registered nonoverlap allocation, same stream, exclusive source ownership과 fixed four-row owner sequence에 한해 invalid-source destination failure atomicity도 true다.

다음은 아직 false다: authoritative predecessor와 checkpoint transaction, canonical sealed-capability consumption, host-observed actual device mask/validator verdict, arbitrary writer/duplicate/device-fault 범위의 전역 atomicity, live solver context, later columns/restarts, full recurrence/full parity, owned event sequence receipt, authoritative solver/solution receipt, 전체 iteration host-copy-zero, SPD/PCG, AMG/DD, Newton, ResultIR, end-to-end O(N), speedup, signed promotion, commercial readiness.

다음 구현 우선순위는 conditional sealed capability를 still-open canonical context 아래의 live checkpoint transaction이 소비하게 한 뒤 later columns/restarts로 확장하는 것이다. D2H가 없는 receipt는 계속 `actual_mask_host_observed=false`, `device_validation_outcome_host_observed=false`를 유지한다.
