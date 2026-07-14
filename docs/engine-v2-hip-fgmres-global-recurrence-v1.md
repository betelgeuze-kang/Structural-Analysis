# Engine v2 HIP FGMRES sealed-continuation global recurrence owner v1

- 상태: v0.2.26 Phase 0 owner implemented, v0.2.27 completion export 및 v0.2.28 terminal observer compatible, `contract_only`/non-promoting
- schema version: `structural-analysis-hip-fgmres-global-recurrence-context.v1`
- capability profile: `phase0_sealed_continuation_consuming_fixed_global_recurrence`
- evidence scope: `fixed_suffix_fenced_device_outcome_unobserved_non_promoting`
- 상위 transaction: [sealed checkpoint transaction v1](engine-v2-hip-fgmres-sealed-checkpoint-transaction-v1.md)
- 전체 ABI: [HIP FGMRES full recurrence ABI v2](engine-v2-hip-fgmres-recurrence-abi-v2.md)
- 하위 consumer: [completion-only export v1](engine-v2-hip-fgmres-completion-export-v1.md)
- 별도 host observer: [terminal-outcome observation v1](engine-v2-hip-fgmres-terminal-outcome-observation-v1.md)

## 문서 범위

`HipFgmresGlobalRecurrenceExecutionContextV1`은 still-open sealed checkpoint context의 단일 non-owning child다. Sealed transaction이 발행한 process-local conditional continuation capability를 reserve한 뒤 enqueue 시작에서 정확히 한 번 소비하고, 이미 실행된 initial/restart-1/column-0 prefix를 재실행하지 않은 채 canonical global-program suffix만 같은 kernel·runtime·device·stream·checkpoint token에 제출한다.

이 owner가 완료됐다는 것은 immutable suffix 전체가 accepted되고 exact owning runtime으로 fence된 뒤 checkpoint pending map에서 제거됐다는 뜻이다. Product receipt는 live device state를 읽거나 numerical outcome에 따라 host 분기하지 않는다. 따라서 `fixed_suffix_fenced=true`와 completion capability는 terminal solver result, authoritative status, solution, numerical parity 또는 상용 준비 증거가 아니다.

권위 구현은 [global recurrence context source](../src/structural_analysis/engine_v2/assembly_backend/fgmres_global_recurrence_context_v1.py), fixed-program compiler는 [global schedule plan source](../src/structural_analysis/engine_v2/assembly_backend/fgmres_global_schedule_plan_v1.py), 직렬화 계약은 [JSON Schema](../src/structural_analysis/schemas/hip_fgmres_global_recurrence_context_v1.schema.json)에 있다.

## Public API와 사용 순서

```python
sealed_pending = sealed_context.enqueue_sealed_checkpoint_transaction()
continuation = sealed_context.synchronize_sealed_checkpoint_transaction(
    sealed_pending
)

opened = open_hip_fgmres_global_recurrence_context_v1(
    sealed_context,
    continuation,
)
context = opened.context

pending = context.enqueue_remaining_global_recurrence()
completion = context.synchronize_global_recurrence(pending)

validate_hip_fgmres_global_recurrence_receipt_v1(
    context.receipt(),
    expected_context=context,
)
validate_hip_fgmres_global_recurrence_completion_capability_v1(
    completion,
    expected_context=context,
)

context.close()
sealed_context.close()
```

- Open은 still-live sealed context와 아직 소비되지 않은 exact continuation capability를 검증하고 child 하나를 reserve한다.
- Enqueue는 frozen physical16 authority와 exact empty pending map을 재검증한 뒤 capability를 single-use consume하고 suffix row를 모두 제출한다.
- Synchronize는 global owner의 final fence 한 번을 관찰하고 exact pending count를 consume한 뒤 outcome-free completion capability를 발행한다.
- Pending과 completion capability는 context만 발행하며 외부 생성, mutation, issuer/context/nonce/snapshot drift는 fail-closed다.
- v0.2.27 completion-export child는 still-open `recurrence_fenced` context와 이 exact capability를 받아 별도 single-use reserve/consume한다. Export child가 살아 있는 동안 global close는 fail-closed다.
- Enqueue하지 않은 child는 close 후 같은 unused continuation으로 다시 열 수 있다. Consume 뒤 capability는 terminal이며 복원되지 않는다.
- Global child가 살아 있는 동안 sealed parent close는 거부된다. Child close는 live allocation, module, checkpoint token 또는 stream을 소유 해제하지 않는다.

## Fixed global program과 sealed partition

`F`는 free DOF 수, `M`은 restart dimension, `I`는 maximum iteration, `R=0 if I=0 else ceil(I/M)`, `S`는 deterministic reduction stage 수다.

```text
B = 7 + 4S
L_j = 20 + 4j + (10 + 2j)S
D = 2 + 2M^2 + 18M + (M^2 + 9M)S
H = (M^2 + 9M)S
B_r = B + (r - 1)D
Q_r = 4S + (r - 1)H
C_rj = B_r + 2 + 2j^2 + 18j + (j^2 + 9j)S
q_rj = Q_r + (j^2 + 9j)S
```

Host program은 `initial prefix + R * (restart preamble + M columns) + FINAL_GUARD`다. `I>0`이면 모든 `R*M` column slot과 final guard를 제출한다. `j>=cycle_width`, terminal 이후, 또는 device predicate가 false인 row도 host schedule에서는 제거하지 않고 device-side claim-only/no-op 계약을 따른다.

각 column은 row `0..j`의 first MGS와 conditional second MGS를 모두 고정 제출하고, prior Givens `0..j-1`, new Givens `j`, candidate replay, non-advancing predecessor validation, decide/preflight/commit/finalize를 순서대로 유지한다. Inactive padding은 모든 device byte와 실제 schedule/reduction epoch을 보존한다. Host의 fixed endpoint는 조기 terminal device epoch을 뜻하지 않는다.

`compile_hip_fgmres_global_sealed_continuation_v1(F, M, I)`는 다음 세 canonical segment를 만든다.

1. `full`: initial부터 final guard까지 전체 immutable program
2. `sealed_prefix`: canonical initial/restart-1/column-0 producer와 sealed four-row transaction이 이미 소유한 exact prefix
3. `continuation`: restart-1/column-1 이후와 나머지 restart, final guard만 포함한 gap-free/non-overlap suffix

`I=0`에는 sealed first-column checkpoint가 없으므로 continuation compiler가 fail-closed한다. Prefix를 다시 제출하면 이미 소비된 epoch과 capability를 replay하므로 허용하지 않는다.

## 수명·권위 계층

```text
live checkpoint context
  direct11 + kernel/module + checkpoint token + stream
    -> canonical predecessor child
       delegated CSR3 + reduction scratch2 = physical16
       initial + restart-1/column-0 predecessor, fence 1
         -> sealed checkpoint transaction child
            fixed four rows, fence 1, conditional continuation
              -> global recurrence child
                 exact suffix only, fence 1, outcome-free completion
                   -> completion export child
                      solution_x -> true_residual -> opaque solve_record
                      exact three blocking D2H, outcome uninterpreted
```

Global authority는 다음을 immutable snapshot으로 결속한다.

- exact live/canonical/sealed context와 receipt lineage
- same kernel object, loaded runtime, device ordinal, architecture와 stream identity
- same checkpoint owner token과 pending-map authority
- `F`, reduced CSR `nnz`, `M`, `I`, `R` 및 tolerance/policy
- direct11 role 순서와 pointer snapshot
- delegated CSR3/reduction scratch2 및 physical16 projection hash
- full/prefix/continuation segment hash와 모든 launch field
- recurrence ABI, combined ABI, fixed source와 kernel identity

Enqueue 전 drift는 zero-work로 거부되고 continuation은 미소비 상태를 유지한다. Consume 후 rejection, partial enqueue 또는 ambiguous acceptance는 capability를 복원하지 않고 exact accepted interval을 보존한 cleanup owner로 수렴한다. Fence 성공 후 acknowledgement가 끊기면 fence를 반복하지 않고 pending consume만 재개한다.

## v0.2.24 host submission control과 lifecycle hardening

Suffix 제출 경로는 다음의 두 단계 witness로 나뉘다.

- RTC compiler가 binding 공개 전 `identity.to_dict()`를 단 한 번 canonical hash하고, 각 identity field의 exact Python type과 값을 flat fixed-field snapshot으로 보존한다. 반복 launch는 semantic serialization/hash를 재실행하지 않고 이 snapshot을 대조하며, `True == 1`과 같은 type alias도 허용하지 않는다.
- Control/vector/indexed-SpMV/reduction 네 launch API는 private `_checkpoint_expected_prior_pending_count`를 RTC owner에 전달한다. RTC는 owner lock 안에서 exact leased-stream pending map이 기대 count와 일치하는지 검사한 뒤 reservation을 1 증가시킨다.
- Global owner는 deep lineage/current-binding 재캡처를 suffix 제출 직전과 전체 row 제출 직후의 phase boundary에서만 수행한다. 각 row에서는 exact child lease, frozen resource snapshot, current schedule row 및 `expected_prior_pending_count=index`를 검사한다.

Linear audit 중 validation 후 live row/pointer를 다시 읽어 실제 launch argument를 만들던 transient TOCTOU HIGH를 발견했다. 수정된 binding registry는 tuple-backed immutable dispatch snapshot과 canonical row-value tuple을 sealed witness로 보존한다. Per-row `_capture_submission` 재검증이 통과하면 `_dispatch`는 live object을 재조회하지 않고 이 sealed snapshot/tuple로만 실제 kernel argument를 구성한다. 최초 regression `test_dispatch_uses_validated_immutable_row_and_resource_snapshot`은 `1 passed in 26.62s`를 통과했다.

Final independent linear re-audit는 요청 범위 내 남는 defect가 없다고 결론냈다. Transient row/pointer drift와 two-thread race, bool/int equality alias, value-equal replacement launches tuple, forged registry dispatch slot은 launch 전 fail-closed되거나 canonical-only argument만 제출했다. `+0.0/-0.0`은 `float.hex()` exact snapshot으로 봉인되어 drift 시 `binding_invalid`/launch 0으로 종료했다. Direct `_require_current_binding` instrumentation은 `L=1/35` 모두 2회이고, 별도 aggregate deep-validator audit count는 두 L 모두 enqueue 3/fence 4로 고정이었다. Focused audit `4 passed in 120.65s`, immutable regression re-run `1 passed in 26.74s`, Ruff/format/py_compile이 모두 통과했다. 이 결론은 요청된 linear host-control 범위의 defect closure이며 numerical outcome, speedup, 일반 O(N) 또는 commercial readiness 승격이 아니다.

Deterministic instrumentation은 suffix launch count `L=1`과 `L=35` 모두에서 deep `_require_current_binding` call 2회, RTC identity `to_dict` call 0회, expected prior pending count `0..L-1`을 확인했다. 따라서 **fixed suffix host-submission control**은 phase-count deep check가 상수이고 row당 고정 작업인 구조적 gate에서 `O(L)`이다. 이는 kernel 실행 복잡도, solver end-to-end 복잡도, 일반 `N`-DOF `O(N)` 또는 속도 증거가 아니다.

Sealed parent는 weak child lease가 사라졌고 continuation이 아직 미소비이며 exact pending map이 빈 경우에만 abandoned unconsumed factory result를 lazy reap할 수 있다. Continuation을 이미 consume했거나 work가 pending인 상태에서 downstream cleanup owner 자체가 유실되면 자동 reap하지 않는다. 이 경우 parent close는 fail-closed로 거부되므로 운영 계층은 `cleanup_owner`를 유지하고 명시적 fence/ack/close retry를 완료해야 한다. 이는 현재의 명시적 operational limitation이다.

## v0.2.25 abandoned consumed/pending recovery

v0.2.24에서 명시한 consumed/pending cleanup-owner 유실 제한은 v0.2.25에서 process-local lifecycle 범위로 닫혔다. Exact loaded runtime의 `hipStreamQuery` callable을 checkpoint lease witness와 immutable binding snapshot에 봉인한다. Query status `0`만 COMPLETE, `600`만 NOT_READY이며, 그 밖의 status와 예외는 fail-closed다. Snapshot에서 나온 exact callable과 exact token/device/sole pending stream을 사용하고, query wrapper의 결과도 exact `bool`만 허용한다. Stale pending map, partial-close state, non-bool 결과 또는 frozen authority drift는 recovery를 진행하지 않는다.

Sealed parent에는 child나 lease에 대한 strong reference가 없는 weak-liveness recovery cell만 남는다. Finalization callback은 abandonment를 기록할 뿐 HIP API를 호출하지 않는다. 이후 parent-owned close/retry가 lock 아래에서 exact authority를 다시 검증하고 다음 순서로만 회수한다.

```text
exact hipStreamQuery
  -> NOT_READY이면 successful hipStreamSynchronize 정확히 1회
  -> exact hipStreamQuery 재확인
  -> exact pending interval pop
  -> terminal lease release
```

첫 query가 COMPLETE이면 sync를 호출하지 않는다. NOT_READY 뒤 sync가 성공한 경우에만 두 번째 query로 진행하며, query 자체는 pending acknowledgement를 소비하지 않는다. Query, optional sync, pop 또는 release 사이에서 interruption이 발생해도 이미 확인·기록된 단계를 되돌리지 않는 monotonic retry로 수렴한다. Recovery cell의 callback과 parent close 사이에는 child/lease strong-reference cycle이 없고 callback은 HIP-free다.

Independent audit 결과는 `BLOCKER/HIGH/MEDIUM/LOW 0/0/0/0`이며 focused lifecycle 검증은 `33 passed`, RTC full은 `111 passed in 34.77s`, checkpoint context v2 full은 `261 passed in 248.58s`다. 이는 owner/sealed full-suite 결과를 뜻하지 않는다. Actual RX 6900 XT `gfx1030`의 F12/M2/I2 abandoned suffix required gate는 pending `39 -> 0`, query `(False, True)`, sync 1, product-path malloc/H2D/D2H/runtime sync 0과 `1 passed, 2 deselected in 37.42s`를 확인했다. 이 recovery는 process-local lifecycle closure이며 terminal completion/status, numerical result/parity, product outcome, O(N), speedup 또는 commercial readiness 증거가 아니다.

## Operation·fence·resource 계약

정상 global suffix의 product-path 계측은 다음과 같다.

```text
continuation capability reservation 1
continuation capability consumption 1
kernel launch attempts/accepts continuation.launch_count
successful global final fence 1
pending consume continuation.launch_count
additional allocation/device bytes/borrow/checkpoint owner/module 0
H2D/D2H/intermediate synchronization/fallback 0
live device-state host read/branch 0
```

Canonical producer, sealed transaction과 global owner가 각각 final fence 하나를 소유하므로 전체 live chain의 정상 contract accounting은 3회다. 이것은 recurrence 전체가 one-fence라는 주장이 아니다. 또한 global suffix의 `no_h2d_or_d2h_copy=true`는 이 owner 범위의 계측이다. v0.2.27 downstream export의 exact three blocking D2H는 별도 export receipt에만 계산되며, 두 receipt를 합쳐 iteration host-copy-zero 또는 ResultIR 통합 증거로 확대하지 않는다.

## Actual `gfx1030` integrated owner evidence

[Actual integrated owner gate](../tests/test_engine_v2_hip_fgmres_global_recurrence_context_hardware_v1.py)는 RX 6900 XT `gfx1030`에서 later-column required case `1 passed in 38.29s`를 확인했다. 직전 동일 test의 `165.02s`대비 test wall-clock이 약 `4.31x` 짧아졌다.

- 3-node serial cantilever, `F=12`, reduced CSR `nnz=144`, `M=2`, `I=2`, `R=1`
- full/sealed-prefix/continuation launch count `84/45/39`
- suffix 첫 row `APPLY_JACOBI_RESTART1_COLUMN1`, 마지막 row `FINAL_GUARD`
- sealed continuation capability reserve/consume `1/1`, suffix attempt/accept/pending consume `39/39/39`
- global product path allocation/borrow/module/H2D/D2H/intermediate sync/fallback/live-read/host-branch 모두 0
- global fence 1, canonical+sealed+global chain fence 합계 3
- 실제 later column 1에서 수치적으로 수렴하고 inactive final guard 제출 뒤 terminal device epoch `E=79,Q=26` 보존
- product receipt를 먼저 고정한 뒤 verification-only D2H에서 CPU reference solution/residual과 FP64 array exact parity, status/counter/metric exact parity 확인
- verification D2H 뒤에도 product receipt hash와 `d2h_operation_count=0`, `numerical_parity_verified=false` 유지

이 gate는 하나의 active later column과 fixed final-guard submission을 실제 integrated owner chain에서 증명한다. `R=1`이므로 active later restart를 실행하지 않았고, column 1에서 이미 terminal이어서 active final-guard fallthrough도 실행하지 않았다. Verification-only oracle은 product receipt가 terminal outcome이나 parity를 관찰했다는 뜻이 아니다.

같은 hardware file의 `test_native_gfx1030_global_owner_executes_active_later_restarts`는 `1 passed, 1 deselected in 59.39s`로 integrated active later restart를 별도 확인했다.

- 5-node serial cantilever, `F=24`, reduced CSR `nnz=360`, `M=2`, `I=5`, `R=3`
- full/sealed-prefix/continuation launch count `228/45/183`
- actual device restart `1 -> 2 -> 3`, terminal location restart 3 column 0
- CPU oracle status/code `max_iterations`/`max_iterations_exhausted`, iteration/restart `5/3`, operator/preconditioner count `9/5`
- device terminal epoch `E=179,Q=58` 및 CPU solution/residual allclose
- global product path allocation/H2D/D2H/intermediate sync/fallback/live-read/host-branch 0, global fence 1
- `FINAL_GUARD`의 fixed expected endpoint `E=215,Q=70`은 제출되었지만 checkpoint finalizer가 이미 terminalize한 뒤여서 inactive였음

별도 v0.2.26 parameter는 같은 5-node cantilever의 exact full final cycle을 실행해 integrated active `FINAL_GUARD`를 닫았다.

- `F=24`, reduced CSR `nnz=360`, `M=2`, `I=4`, `R=2`
- full/sealed-prefix/continuation launch count `156/45/111`
- final checkpoint commit `E/Q=147/48`; active guard가 schedule epoch 하나를 단독 claim해 terminal `E/Q=148/48`
- CPU oracle iteration/restart `4/2`, operator/preconditioner `7/4`, device solution/residual allclose
- global product path allocation/H2D/D2H/intermediate sync/fallback/live-read/host-branch 0, global fence 1
- product receipt는 verification D2H 전에 고정되며 outcome/status/parity/solution 관찰 claim은 false 유지

Exact full-cycle max decision과 last restart/column이면 checkpoint finalizer는 row/metric을 commit한 뒤 active/not-terminal을 유지하고 `FINAL_GUARD`에 넘긴다. `I=5` partial final cycle은 기존 checkpoint-owned terminal `E/Q=179/58`과 inactive guard를 보존한다. Mandatory handoff eligibility와 exact prestate validity는 별도 predicate다. Required handoff에서 `next_expected_restart` 등이 오염되면 restart row/header publish 전 error/status/code `1/6/47`로 fail-closed하며 checkpoint-owned max termination으로 fallback하지 않는 actual `gfx1030` 음성 회귀를 통과했다.

따라서 integrated active later restart와 active final-guard fallthrough은 native evidence가 있다. 다만 이 evidence는 product receipt의 terminal outcome, solution 또는 parity 관찰을 승격하지 않는다.

Immutable dispatch snapshot TOCTOU 수정 후 위 F12 later-column과 F24 active-restart required hardware 두 case를 같이 재실행해 `2 passed in 96.11s`로 최종 재통과했다.

`38.29s` 결과는 flat RTC witness와 phase-boundary deep check로 줄인 **host-control test wall-clock**이다. HIP kernel speedup, solver end-to-end speedup, 일반 model-family latency, 또는 `N`-DOF `O(N)`으로 재분류하지 않는다.

Focused verification은 RTC `103 passed`, global owner `11 passed in 268.76s`, sealed/global lifecycle `6 passed in 123.64s`를 통과했고 independent lifecycle audit에서 추가 defect를 찾지 않았다.

v0.2.25 최종 전수 회귀는 RTC `111 passed in 34.77s`, checkpoint context v2 `261 passed in 248.58s`, global owner `54 passed in 1387.12s`, sealed transaction `30 passed in 507.23s`를 통과했다. Sealed 회귀에는 recovery cell 등록 없이 continuation을 consume하려면 HIP/query/sync/pending 변화 없이 fail-closed하고 unused reservation은 다시 열리는 음성 경계 검증이 포함된다.

별도 [raw global recurrence hardware gate](../tests/test_engine_v2_hip_fgmres_global_recurrence_hardware_v1.py)는 `F=513,M=2,I=5`의 lower-bidiagonal 3-restart exhaustion과 identity early-terminal padding을 CPU oracle과 비교한다. [Raw final-guard hardware gate](../tests/test_engine_v2_hip_fgmres_final_guard_hardware_v1.py)는 active valid fallthrough와 malformed fail-closed를 검사한다. Raw evidence와 v0.2.26 integrated owner evidence는 각각의 소유·schedule 계약으로 별도 유지한다.

## Current identity

| Current recurrence payload (v0.2.26 identity, unchanged by v0.2.27 export) | SHA-256 |
| --- | --- |
| checkpoint transaction semantic contract | `sha256:0583f66e5faa848da734ff8fbcc430d8bb71ef9fc854fab49121be3f61691e5d` |
| global schedule semantic contract | `sha256:7c18ba9190fef663fec8e1f87e0f56ec393e23f04d4753ffbc3c707bff1a10ea` |
| combined recurrence/kernel ABI | `sha256:6a361ccfd0dbbe544e93b6c9ea788cc3702f6f924a969a3aa3deebf3292f315b` |
| fixed HIP source | `sha256:a5b39fb976aa330eaffae74feb8561f241df662a21dc32354b8010af2bb1c93d` |

Integrated `F=12,M=2,I=2` fixture의 dimension-specific full/prefix/suffix hash는 각각 `sha256:ff7c027b7a2d9d40b2371bbc9b369f2c9413a36f83d969b4c03c1f6582f0d8ac`, `sha256:33c8f74230ac5489f7e28e060a973917e434a7b0d169c8d32bae3c32500c001b`, `sha256:7c710e878195e1b6567f6732f389b89c3d725d99e712ef8c3e98d1ef7a52abdc`다. 이 값은 dimension과 모든 launch field에 결속된 instance hash이며 전역 ABI 상수가 아니다.

v0.2.22 sealed checkpoint evidence의 combined/source `sha256:bb5b94457fbf3be4c5f2b38dda3f50c8a757094e0b97fb4d7288e7bdbf4db39f`/`sha256:a1d2da3f0d9a6c4a574fb1cb9d5be24c30c1e6e5e1c6de3ff1a4b50eeefad113`와 v0.2.23-v0.2.25 identities는 historical identity다. Current v0.2.26 native evidence로 소급 재해석하지 않는다. v0.2.26은 recurrence semantic payload/schema와 HIP source를 변경했지만 public global receipt/completion schema는 변경하지 않았다. v0.2.27 completion export와 v0.2.28 observer는 별도 source/schema/receipt를 추가하며 이 recurrence identity와 global receipt/hash를 변경하지 않는다.

Historical v0.2.25 package 검증은 당시 `src/`로 wheel `875235` bytes (`sha256:e6522f810af2a4a0f6d62c770f510bcab57278e64cec4e0070b8fbec2eb2b8e2`) 및 sdist `823734` bytes (`sha256:8094a8bcaf30d3aaf954d5c5f0183baaf03881ff96ae62b33b6832276b2b3d3c`)를 구성했다. Wheel을 `--no-deps` 격리 target에 설치해 Engine v2 global public export, global schedule/sealed-continuation API, Draft 2020-12 global schema (`15196` bytes, `sha256:72c1aa47547970e90376c20831698e80aef4c57e9fc6d600e6949d17288bad48`) 및 당시 packaged HIP source (`207780` bytes, `sha256:2ecbbe21f8f95686117e2a12cf8cf0984f7e51b11fa331e7d5c81e15f8ed7967`)를 확인했다. 이는 historical 패키지 완전성 검증이며 current v0.2.26 package, solver outcome이나 release promotion 증거가 아니다.

## Receipt 진본성과 claim boundary

Receipt canonical hash와 standalone validator는 current schema, ABI/source/schedule identity 및 내부 semantic consistency를 검증한다. Canonical hash는 서명이 아니므로 standalone validation만으로 coordinated provenance 진본성을 증명하지 않는다. Process-local provenance에는 `expected_context` 검증이 필요하고, 장기 보관·외부 전달에는 향후 signed chain이 필요하다.

`recurrence_fenced`에서 true인 범위는 다음과 같다.

- conditional sealed continuation capability가 single-use consume됨
- direct11/physical16과 same kernel/runtime/device/stream/checkpoint continuity가 bound됨
- canonical suffix 전체가 고정 순서로 accepted되고 global final fence와 pending acknowledgement가 완료됨
- global owner의 추가 resource/copy/intermediate-sync/fallback/live-read/host-branch가 0임
- outcome-free completion capability가 발행됨
- fixed suffix host-submission control이 phase-boundary deep check 2회와 row당 fixed work로 `O(L)` 구조 gate를 유지함
- per-row validation 후 실제 launch argument가 registry-sealed immutable dispatch snapshot과 canonical row-value tuple에서만 생성됨
- final independent linear re-audit이 요청 범위 내 remaining defect 0을 확인함
- actual integrated owner가 restart `1 -> 2 -> 3`의 active later restart를 실행함
- actual integrated owner가 exact full final cycle에서 checkpoint `E=147`의 mandatory handoff 후 active `FINAL_GUARD` `E=148`을 실행함
- malformed mandatory handoff prestate가 checkpoint-owned max termination으로 위장되지 않고 code 47로 fail-closed함
- consumed/pending owner abandonment가 exact query → optional successful sync 1회 → query → pending pop → terminal release의 parent-owned monotonic retry로 process-locally 회수됨

다음은 계속 false다.

- product receipt의 actual terminal outcome/status/solution/parity 관찰
- authoritative predecessor, numerical checkpoint transaction 또는 terminal solver receipt
- model-family·multi-architecture full CPU/HIP parity
- global receipt 자체의 payload export, ResultIR 연결과 iteration host-copy-zero; v0.2.27 completion export는 별도 non-promoting receipt이다
- kernel speedup, solver end-to-end speedup, 일반 `N`-DOF O(N) 또는 model-family latency
- SPD/PCG, AMG/DD, signed promotion과 commercial readiness

v0.2.27 downstream completion export는 `solution_x` → `true_residual` → opaque `solve_record`를 exact three blocking D2H로 materialize하고, v0.2.28 별도 observer가 exact process-local final publication에서 terminal record를 해석한다. 두 receipt는 분리되며 global/export receipt의 outcome-free claim은 변하지 않는다. 현재 next action은 model-family·multi-architecture CPU/HIP full parity이며, 그 뒤 iteration host-copy-zero와 ResultIR을 별도로 닫는다.
