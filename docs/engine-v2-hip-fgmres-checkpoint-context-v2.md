# Engine v2 HIP FGMRES first-column checkpoint transaction context v2

- 상태: Checkpoint owner v0.2.16 implemented; current v0.2.26 recurrence ABI compatibility confirmed, `contract_only`
- 증거 범위: `caller_attested_valid_predecessor_non_promoting`
- 수치 커널: [initial + first-column checkpoint recurrence v2](engine-v2-hip-fgmres-initial-recurrence-v2.md)
- 후속 live owner: [canonical-capability-consuming sealed checkpoint transaction v1](engine-v2-hip-fgmres-sealed-checkpoint-transaction-v1.md)
- 후속 global consumer: [sealed-continuation global recurrence owner v1](engine-v2-hip-fgmres-global-recurrence-v1.md)
- 전체 설계: [HIP FGMRES full recurrence ABI v2](engine-v2-hip-fgmres-recurrence-abi-v2.md)
- 상위 기준: [Structural Solver Engine v2 마스터 로드맵](structural-solver-engine-v2-master-roadmap.md)

이 단계는 column-0 `CHECKPOINT_DECIDE -> PREFLIGHT_COMMIT_SOURCE -> COMMIT_CHECKPOINT -> CHECKPOINT_FINALIZE` 네 launch에 process-local 단독 실행권, 정확한 HIP allocation 범위 등록, single-use predecessor capability, 부분 enqueue poison, 실제 HIP stream fence와 재시도 가능한 cleanup을 추가한다. 네 launch의 host-side lifetime은 한 context가 소유한다. v0.2.16의 three-row 검증 수치는 historical snapshot으로 유지하며 current owner는 fixed four-row schedule을 사용한다.

이 context가 발행하는 predecessor는 상위 Krylov producer가 장치 메모리의 실제 값과 mask를 검증해 넘긴 영수증이 아니라 caller attestation이다. 따라서 이 context 자체의 `authoritative_predecessor_proven`, `live_krylov_parent_integrated`, `promotion_eligible`은 모두 false다. 후속 [live checkpoint resource context v1](engine-v2-hip-fgmres-live-checkpoint-context-v1.md)과 [canonical first-column predecessor producer v1](engine-v2-hip-fgmres-canonical-predecessor-v1.md)은 actual allocator lineage, owned8 initialization과 device validator seal을 별도로 구현했고, v0.2.22의 별도 sealed transaction child가 그 conditional capability를 소비한다. 이 caller-attested API의 receipt가 소급 승격되는 것은 아니며, 이 문서는 authoritative solver, solution receipt 또는 상용 준비를 주장하지 않는다.

## 1. 소유 경계

```text
caller-attested valid predecessor
        |
        v
exact allocation registry + raw-kernel lease
        |
        v
DECIDE -> PREFLIGHT -> COMMIT -> FINALIZE  (one queue lock, one stream)
        |
        v
exact loaded-runtime hipStreamSynchronize
        |
        v
atomic pending-reservation consume -> fenced receipt -> unload/registry cleanup
```

공개 진입점은 다음으로 한정한다.

- `HipFgmresDeviceAllocationV2`
- `HipFgmresCheckpointBuffersV2`
- `HipFgmresRecurrenceExecutionContextV2`
- `HipFgmresCheckpointPredecessorReceiptV2`
- `HipFgmresCheckpointTransactionReceiptV2`
- `HipFgmresRecurrenceContextV2Error`

Receipt 두 종류는 일반 constructor로 만들 수 없고 context-private mint, issuer, nonce와 발행 시 snapshot을 함께 검사한다. 같은 객체를 `object.__setattr__`로 바꾼 경우도 다음 사용에서 거부한다. 이는 process-local capability 계약이며 악성 코드에 대한 보안 sandbox는 아니다.

## 2. 정확한 allocation 계약

`F=free_dof_count`, `M=restart_dimension`, `R=maximum_restart_count`일 때 11개 descriptor의 역할, type, byte extent와 base가 정확히 일치해야 한다.

| 역할 | element type | exact byte extent |
| --- | --- | ---: |
| `reduced_state` | `f64` | `8F` |
| `reduced_load` | `f64` | `8F` |
| `inverse_diagonal` | `f64` | `8F` |
| `solution_x` | `f64` | `8F` |
| `true_residual` | `f64` | `8F` |
| `work_w` | `f64` | `8F` |
| `basis_v` | `f64` | `8(M+1)F` |
| `basis_z` | `f64` | `8MF` |
| `dense` | `f64` | `8(M^2+5M+1)` |
| `control_state` | `u8` | `256` |
| `solve_record` | `u8` | `192+72R` |

각 descriptor는 exact base pointer snapshot, byte extent, element type, 공통 owner token, 양의 generation, exact `_BoundHipContextRuntime`, device ordinal을 가진다. `f64`뿐 아니라 kernel에서 i32/f64 header로 접근하는 `control_state`와 `solve_record`의 u8 allocation base도 8-byte aligned여야 한다. `base+nbytes`의 `uintptr_t` overflow와 context 내부 55개 모든 range pair의 overlap을 거부한다.

등록 후 launch는 공개 descriptor를 다시 역참조하지 않고 private immutable pointer snapshot만 사용한다. 공개 descriptor의 base, pointer, extent, type, owner, generation, runtime 또는 device가 바뀌면 authority 검증이 실패한다. Cleanup은 공개 descriptor가 변조되어도 등록 당시 private candidate로 exact range를 해제할 수 있다.

Process-global registry는 다음을 보장한다.

- 같은 live process/device pointer range의 exact-base 재등록과 shifted overlap 거부
- allocation base별 generation high-water와 constructor 실패 시 원자적 rollback
- 정상 close에서 11개 range의 all-or-none bulk unregister
- module unload 성공 뒤 registry cleanup만 실패하면 `CLEANUP_FAILED`에서 unload를 반복하지 않고 cleanup만 재시도

현재 Engine v2는 explicit HIP context handle을 소유하지 않는다. 서로 다른 `LoadedHipRuntime`/DSO handle도 같은 process와 device ordinal이면 primary-context GPU VA domain을 공유할 수 있으므로 모든 exact native runtime wrapper를 하나의 보수적인 process-native domain으로 합친다. Test-double runtime은 객체 identity로 분리한다. 향후 explicit context를 지원할 때만 `hipCtxGetCurrent` 같은 실제 context witness로 세분화한다.

## 3. Raw module과 device 권한

`HipRtcFgmresV2Kernel`은 fixed-source compiler만 private mint로 만들 수 있다. Compile/load 시 다음 값을 immutable process-local binding witness로 보관한다.

- exact runtime API와 loaded runtime 객체
- module handle과 네 function handle
- raw launch, unload, `hipGetDevice`, `hipStreamSynchronize`, `hipStreamQuery`, `hipMemsetAsync` callable
- module을 load한 실제 device ordinal
- recurrence identity payload와 source/ABI hash

`LoadedHipRuntime`도 `load_hip_native_runtime()`만 private mint로 만들 수 있고 library identity는 read-only다. Public `cdll`은 호환 view일 뿐 binding authority가 아니다. Native `bind()`는 private handle resolver로 symbol address를 다시 찾고 매 호출마다 고정 prototype의 새 `CFUNCTYPE` instance를 만든다. 따라서 public `ctypes` function의 `argtypes`, `restype`, `errcheck`나 cached symbol attribute를 compile 전후 또는 다른 thread에서 바꿔도 module load/get-function, device query, stream query, launch, sync와 unload callable은 변하지 않는다.

Context lease는 raw owner token과 binding snapshot을 한 lock 안에서 원자적으로 획득한다. Lease acquisition 시 exact loaded runtime에서 `hipStreamSynchronize`, `hipStreamQuery`, `hipMemsetAsync`를 함께 결속한다. 이 caller-attested four-launch context는 memset이나 stream query를 제출하지 않지만, 같은 exclusive checkpoint lease를 사용하는 v0.2.20 canonical producer는 sealed memset callable을 kernel pending accounting과 동일한 acceptance interval로 추적하고 v0.2.25 downstream parent recovery는 sealed query callable만 사용한다. Public module/function/runtime field drift는 launch 전에 거부되며 실제 launch, memset, query, sync와 unload는 witness의 private handle/callable만 사용한다.

`hipGetDevice`는 metadata가 아니라 실제 runtime query다. Module binding, lease, 각 launch, pending observation, fence, pending consume, authority 확인과 close에서 module device, lease expected device, current device가 같아야 한다. Device drift는 장치 mutation 전에 실패하며 원래 device를 복원한 뒤 fence 또는 cleanup을 재시도할 수 있다.

Sealed `hipStreamQuery` wrapper는 raw status `0`만 exact `True`(COMPLETE), `600`만 exact `False`(NOT_READY)로 변환한다. 그 밖의 status와 예외는 fail-closed이며 호출자는 `bool`의 exact type만 받아들여 `0/1` 같은 int alias를 허용하지 않는다. Query authority는 exact runtime callable, checkpoint token, device와 sole pending stream snapshot에 결속된다.

현재 sealed native binding의 지원 전제는 CPython/Linux ROCm과 신뢰된 process·설치 filesystem·명시적 runtime-library 설정이다. Package가 hash한 path와 loader mapping 사이를 적대적으로 교체하는 보안 공격, 임의 `dlclose`, private underscore/registry 변조를 방어하는 sandbox나 AMD 서명 검증은 아니다.

## 4. Predecessor와 transaction

Context는 `READY` 상태에서 predecessor를 정확히 한 번만 발행한다. Receipt는 다음을 결속한다.

- kernel identity, combined ABI와 checkpoint schedule hash
- runtime, stream pointer, device와 `F/M/R`
- exact schedule/reduction epoch
- mask의 허용 domain `(0, 1792, 7936)`
- `work_w`, `basis_v` source generation과 전체 allocation generation

중요하게도 receipt는 device memory를 D2H해서 실제 mask나 content를 관찰하지 않는다. Caller가 세 허용 mask 중 실제 하나와 canonical valid-predecessor 내용을 만들었다고 증언할 뿐이다. v0.2.20 control ABI에서 이 legacy 경로는 offset 116/120/124의 validation state/mask snapshot/reduction-epoch snapshot도 모두 0이라고 attestation한다. 따라서 fixed domain 확인은 actual-mask proof가 아니다.

별도 canonical producer 경로에서는 `PREDECESSOR_VALIDATE=14`가 같은 `E=26+14S`, `Q=14S`에서 actual mask를 장치 안에서 검사하고 `empty(0) -> armed(1)` seal을 만든다. `CHECKPOINT_DECIDE`는 sealed 경로에서 `armed(1) -> consumed(2)`, 정상 source preflight는 snapshot을 보존하며 `consumed(2) -> commit-preflighted(3)`, 정상 finalizer는 snapshot clear 뒤 state `3 -> empty(0)`를 수행한다. Multi-block invalid preflight의 종료 state는 scheduling에 따라 `2` 또는 `3`이고 mask/reduction snapshot을 보존한다. Legacy 경로는 exact-zero snapshot의 정상 `0 -> 3 -> 0`이다. 이 caller-attested context API는 canonical producer capability를 입력받지 않으며 legacy 경로만 소유하므로, 별도 sealed owner 구현이 이 receipt를 승격하지 않는다.

정상 enqueue는 context queue lock 아래에서 raw pending count가 0임을 확인하고 네 launch를 항상 같은 stream에 순서대로 호출한다. Plan의 row kind는 control/vector/vector/control, epoch은 `E0`, `E0+1`, `E0+1`, `E0+2`여야 하며 preflight와 commit은 같은 exact 11-pointer tuple을 사용한다. Receipt에는 attempted count와 accepted lower/upper bound를 기록한다.

- launch 전 거부 또는 명시적 runtime rejection은 `not_attempted`/`rejected`로 분류한다.
- raw launch callable이 예외를 던져 수락 여부를 알 수 없으면 `ambiguous`로 분류하고 그 launch를 upper bound에 포함한다.
- 일부 launch가 제출되었거나 제출 여부가 모호하면 raw lease와 context를 poison하고 fence 전 unload를 금지한다.
- 제출된 work가 없음을 증명한 실패는 `POISONED_NO_WORK`로 닫을 수 있다.

Predecessor receipt는 enqueue 시 즉시 소비되며 성공, 거부, ambiguity 어느 경우에도 재사용할 수 없다.

## 5. Fence, acknowledgement와 lifetime

상태 전이는 다음 집합으로 제한된다.

```text
READY -> ENQUEUEING -> PENDING_FENCE -> FENCED -> CLOSED
                    \-> POISONED_PENDING_FENCE -> POISONED_FENCED -> CLOSED
READY/ENQUEUEING    \-> POISONED_NO_WORK -> CLOSED
fence observed, consume uncertain -> FENCE_OBSERVED_ACK_PENDING -> POISONED_FENCED
kernel unloaded, registry cleanup failed -> CLEANUP_FAILED -> CLOSED
```

Fence는 facade의 주장이나 host callback이 아니라 module을 소유한 exact loaded runtime의 `hipStreamSynchronize` 호출로 관찰한다. 그 뒤 raw pending map에서 해당 stream의 launch reservation 수를 lock 안에서 원자적으로 pop한다.

- fence 실패: pending ownership을 유지하고 `POISONED_PENDING_FENCE`에서 재시도
- fence 성공 후 consume 전 실패: 두 번째 sync 없이 `FENCE_OBSERVED_ACK_PENDING`에서 consume 재시도
- consume callback이 pop 뒤 실패했을 가능성: 다음 consume의 0을 already-consumed로 인정하되 transaction은 poison 유지
- consumed count가 accepted interval 밖: `POISONED_FENCED`

Context는 reentrant enqueue, fence와 close를 pre-mutation에서 거부하고 raw kernel은 reentrant close를 별도 차단한다. Raw launch/sync 자체에 일반 operation guard가 있다는 주장은 하지 않는다. Raw unload callback이 close를 재진입해도 `hipModuleUnload`는 한 번만 실행한다. Kernel unload 실패는 range registry와 lease를 유지하며, device를 복원하거나 runtime 오류를 해소한 뒤 재시도할 수 있다.

v0.2.25 downstream consumed/pending abandonment recovery는 이 shared lease의 query witness를 사용한다. Sealed parent가 보유하는 recovery cell은 child나 lease를 strong-reference하지 않으며 finalization callback은 abandonment만 기록하고 HIP을 호출하지 않는다. Parent-owned close/retry만 exact token/device/sole pending stream과 frozen binding을 다시 검사한 뒤 `query -> 필요 시 successful sync 1회 -> query -> pending pop -> terminal release` 순서로 진행한다. 첫 query가 COMPLETE이면 sync는 0회이고, NOT_READY일 때만 sync 성공 뒤 두 번째 query를 요구한다. Query만으로 pending을 pop하지 않으며 interruption 뒤에는 이미 완료된 단계를 되돌리지 않는 monotonic retry를 수행한다. Stale pending, partial-close, non-bool query result 또는 frozen authority drift는 모두 fail-closed다.

## 6. 검증과 고정값

v0.2.16 집중 검증은 다음을 통과했다.

- checkpoint context `246 passed`
- raw recurrence-v2 RTC `60 passed`
- context와 기존 HIP context 결합 `258 passed`
- recurrence plan v2 `58 passed`, 독립 GPU-tree oracle `95 passed`
- 실제 RX 6900 XT `gfx1030` raw numerical hardware `12 passed`, skip/fallback 0
- 전체 FGMRES `538 passed`, 광범위 Phase 0 `1268 passed`, capability matrix `7 passed`
- Ruff format/check와 Python bytecode compile

다음은 v0.2.16 검증 당시의 historical source snapshot hash다. 현재 파일 hash나 v0.2.19 source aggregate로 재해석하지 않는다.

- `fgmres_context_v2.py`: `sha256:52d95b7a57a9c851c52fa8012047e2399e84e8da65cb686346f1ab2694cc2f23`
- `fgmres_rtc_v2.py`: `sha256:d6e312fba83d60c87dedc10aa5b8c0525cb1715b4beb5980df9b0f9dc40e7f59`
- `backends/hip/native.py`: `sha256:35dad9d9a303d71ffef975e99247dc1ca08f1bfa7a871bf67746a75f3225a59e`
- `backends/hip/context.py`: `sha256:de916fe1a41a7aedec49fe1170fe8153fa75babc4d644ac0c27a974dd03f554e`
- fixed HIP source: `sha256:34049a08119b19382c26fbe310f957d7af9c41db037dfcbab521828732025e9b`
- combined recurrence ABI: `sha256:31fbff2fa25c221a99f28e170818990a8ed71211169d239e05d28628941941c9`
- checkpoint schedule: `sha256:d9b9115287e3b5839096e3f4417c04899ffc7592864483d918be55deaf4b4442`

현재 v0.2.26 recurrence identity는 다음과 같다. Exact full-final-cycle checkpoint-to-guard handoff로 recurrence semantic payload/schema와 HIP source가 변경됐으며 위 historical ABI/source와 구분한다.

- predecessor validator schedule: `sha256:b083896de86a808b1398d0fde4abe73726cb91f50399651274ef82dc09a5ef58`
- global schedule semantic contract: `sha256:7c18ba9190fef663fec8e1f87e0f56ec393e23f04d4753ffbc3c707bff1a10ea`
- combined recurrence ABI: `sha256:6a361ccfd0dbbe544e93b6c9ea788cc3702f6f924a969a3aa3deebf3292f315b`
- fixed HIP source: `sha256:a5b39fb976aa330eaffae74feb8561f241df662a21dc32354b8010af2bb1c93d`
- checkpoint schedule: `sha256:0583f66e5faa848da734ff8fbcc430d8bb71ef9fc854fab49121be3f61691e5d`

v0.2.22 combined/source `sha256:bb5b94457fbf3be4c5f2b38dda3f50c8a757094e0b97fb4d7288e7bdbf4db39f`/`sha256:a1d2da3f0d9a6c4a574fb1cb9d5be24c30c1e6e5e1c6de3ff1a4b50eeefad113`, v0.2.21 fixed source와 v0.2.20 combined/source는 historical identity다. Gate clear만으로 과거 COMMIT 미실행이나 rollback을 증명하지 않는다.

v0.2.21 context 신규·인접 focused `77 passed`는 complete row fields, canonical tuple identity, kernel/token/stream/policy/exact 11-pointer tuple의 frozen binding과 dispatch 전 drift 거부를 검증했다. 전체 context 전수 회귀도 `261 passed in 523.33s (0:08:43)`를 통과했다. `control_state`와 `solve_record`를 포함한 모든 11 allocation은 role type·extent뿐 아니라 이 context가 요구하는 exact alignment도 통과해야 한다. 독립 감사에서 발견한 same-kind row mutation, preflight/commit pointer TOCTOU, predecessor state-code source-ABI binding 누락과 u8 role alignment 누락을 수정했고 최종 source에서 남은 High/Medium 결함은 없었다. Ruff format/check, py_compile, canonical hashes와 actual HIP source hash assertion도 통과했다.

v0.2.25 lifecycle 검증은 focused `33 passed`, RTC full `111 passed in 34.77s`, checkpoint context v2 full `261 passed in 248.58s`, global owner full `54 passed in 1387.12s`, sealed transaction full `30 passed in 507.23s`를 통과했고 independent audit은 `BLOCKER/HIGH/MEDIUM/LOW 0/0/0/0`으로 종료했다. Actual RX 6900 XT `gfx1030` F12/M2/I2 abandoned suffix required gate는 pending `39 -> 0`, query `(False, True)`, sync 1, product-path malloc/H2D/D2H/runtime sync 0과 `1 passed, 2 deselected in 37.42s`를 확인했다. 이 증거는 process-local lifecycle recovery에 한정되며 completion, 수치 결과/parity, product outcome, O(N), speedup 또는 commercial readiness를 승격하지 않는다.

기존 native `gfx1030` hardware `12 passed`는 raw valid-predecessor numerical slice의 증거다. 새 context의 allocator/parent 통합 또는 end-to-end native solver 증거로 승격하지 않는다.

699314-byte wheel `sha256:3a75dd97faac20c1ac0c4ab2cc093689fdc23a9ca8e6c365c551a9df0f867b72`를 만들고 격리 설치 환경에서 새 public API 6개, recurrence schema와 fixed HIP kernel resource import를 확인했다. Package import는 구현의 배포 가능성만 확인하며 solver readiness를 승격하지 않는다.

## 7. Claim boundary와 다음 단계

현재 true인 범위는 caller-attested valid predecessor에 대한 exact typed range registry, exclusive raw lease, same-stream fixed-four-launch host transaction, partial-enqueue poison, exact-runtime/device fence, atomic pending consume와 retryable cleanup이다. `completion_fence_authoritative`는 이 exact raw stream fence에만 true다. Exact registered nonoverlap allocation, same stream, exclusive source ownership과 fixed four-row owner sequence에서는 invalid commit source가 두 destination 전체 bytes를 보존한다. Sealed `hipMemsetAsync`와 `hipStreamQuery` binding은 shared RTC lease의 현재 사실이지만 이 context의 transaction receipt에는 memset 실행, downstream recovery 또는 terminal outcome claim이 없다.

다음은 아직 false다.

- 실제 scale-metrics producer가 발행한 authoritative predecessor와 actual mask/content proof
- free-space/Krylov parent의 live lease와 queue/buffer lifetime 통합(후속 resource/canonical producer에서 완료, 이 transaction과의 결합은 미완료)
- allocator가 발행한 pointer provenance와 실제 free ownership(후속 resource/canonical producer에서 완료, 이 transaction의 predecessor provenance는 미완료)
- 이 caller-attested API 자체의 canonical conditional capability 소비; 별도 v0.2.22 sealed child에서 single-use consume와 정상 `1→2→3→0` fixed-program continuity를 구현했지만 본 receipt에는 소급되지 않음
- arbitrary raw duplicate COMMIT, 외부 writer/DMA/device fault까지 포함한 전역 destination atomicity
- host 측 네 launch enqueue 자체의 불가분 원자성
- 본 caller-attested receipt가 actual sealed invalid outcome을 host 관찰했다는 claim; 별도 v0.2.22 actual `gfx1030` valid/late-invalid scoped cases `2 passed`도 conditional receipt 경계를 유지함
- global later columns/restarts와 final guard의 raw/current 구현이 이 historical caller-attested receipt를 소급 승격한다는 claim
- full CPU/HIP recurrence parity와 iteration host-copy zero
- multi-GPU/explicit HIP context, HIP graph/capture와 속도 증거
- SPD/PCG, AMG/DD, Newton, ResultIR, O(N), signed promotion, commercial readiness

Global owner 위 completion-only solution/residual/opaque-record export는 v0.2.27의 별도 non-promoting receipt로 구현됐고, 그 raw bytes와 lineage를 해석하는 명시적 terminal-outcome observation contract는 v0.2.28에 별도로 구현됐다. 다음 권위 gate는 model-family·multi-architecture CPU/HIP full parity와 iteration host-copy-zero다. Active final-guard integrated native coverage는 v0.2.26 downstream owner에서 검증됐지만 본 historical caller-attested receipt를 소급 승격하지 않는다. D2H가 없는 receipt는 exact mask scalar나 validator verdict를 host가 안다고 주장하지 않고 `actual_mask_host_observed=false`, `device_validation_outcome_host_observed=false`를 유지해야 한다.
