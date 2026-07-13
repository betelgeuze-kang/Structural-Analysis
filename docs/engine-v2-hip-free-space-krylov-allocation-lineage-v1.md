# Engine v2 HIP FreeSpace/Krylov allocation lineage integration v1

- 기준일: 2026-07-12
- 상태: v0.2.18 구현된 통합 계약 + v0.2.19 RTC handoff 사후 강화, unsigned·non-promoting
- 마스터 로드맵: v0.2.19
- 범위: FreeSpace 12개 owned allocation, Krylov primitives 9개 owned allocation과 parent 5개 exclusive borrow
- lineage profile: `foundation_non_promoting`
- receipt: FreeSpace context v2, Krylov primitives context v2
- 승격 경계: process-local allocation/lifetime integration 증거이며 solver, 성능, O(N), 상용 준비 증거가 아니다.

## 1. 목적

기존 FreeSpace/Krylov context는 raw HIP pointer dict가 할당 소유권을 대신했다. 이 단계는 기존 kernel ABI용 raw handle view를 유지하면서, 실제 `malloc/free`를 owner-minted capability와 immutable free/orphan lease 상태기계에 연결한다.

```text
FreeSpace allocation owner
  ├─ 12 owner-minted capabilities
  └─ atomic exclusive borrow: parent 5
       └─ Krylov semantic child token
            └─ same-domain peer allocation owner
                 └─ 9 owner-minted capabilities
```

공개 receipt에는 pointer, owner ID, lease ID, runtime-domain object를 직렬화하지 않는다. Receipt는 non-promoting profile, 관리된 buffer 수/byte, parent borrow 수와 quarantine telemetry만 기록한다.

## 2. FreeSpace owned allocation 12개

| role | element type | exact byte extent |
| --- | --- | ---: |
| `free_dofs` | `i32` | `4F` |
| `global_to_free` | `i32` | `4G` |
| `reduced_csr_row_ptr` | `i32` | `4(F+1)` |
| `reduced_csr_column_indices` | `i32` | `4Z` |
| `reduced_csr_global_value_indices` | `i32` | `4Z` |
| `reduced_csr_values` | `f64` | `8Z` |
| `reduced_state` | `f64` | `8F` |
| `reduced_load` | `f64` | `8F` |
| `reduced_direction` | `f64` | `8F` |
| `reduced_residual` | `f64` | `8F` |
| `reduced_jvp` | `f64` | `8F` |
| `error_flag` | `i32` | `4` |

여기서 `G=global_dof_count`, `F=free_dof_count`, `Z=reduced_csr_nnz`다. Context open은 실제 runtime의 selected device를 재확인한 뒤 owner를 열고, 각 view를 `owner.allocate(role, nbytes, element_type)`로 할당한다. Kernel에 넘기는 `_pointers[role]`는 해당 capability의 exact `base`다.

## 3. Krylov parent borrow 5개와 owned allocation 9개

FreeSpace는 latest source apply를 parent queue lock에서 재확인하고 다음 5개 capability를 하나의 all-or-none group borrow로 잠근다.

1. `reduced_csr_row_ptr`
2. `reduced_csr_column_indices`
3. `reduced_csr_values`
4. `reduced_direction`
5. `reduced_jvp`

Semantic child token은 group borrow가 commit된 뒤에만 외부로 반환된다. Borrow 중에는 parent apply, 다른 child open, parent close와 해당 allocation의 begin-free가 모두 거부된다. Krylov owner는 FreeSpace owner의 exact runtime-domain/device provenance를 계승한 peer owner로 열린다.

| Krylov owned role | element type | exact byte extent |
| --- | --- | ---: |
| `jacobi_inverse` | `f64` | `8F` |
| `work_x` | `f64` | `8F` |
| `work_y` | `f64` | `8F` |
| `preconditioned` | `f64` | `8F` |
| `reduction_ping` | `f64` | `16P` |
| `reduction_pong` | `f64` | `16P` |
| `dot_result` | `f64` | `8` |
| `norm_result` | `f64` | `8` |
| `error_flag` | `i32` | `4` |

`P=ceil(F/512)`다. Parent 5개와 owned 9개는 모두 exact same runtime/device에 결속되고, context authority가 same stream identity를 별도로 재검사한다.

## 4. Free lifecycle

각 owned allocation은 다음 상태를 따른다.

```text
live
  -> free lease reserved
  -> external free attempted
       -> known-not-freed: same lease/snapshot retry
       -> success: acknowledgement only; external free never repeated
       -> outcome uncertain: quarantine; external free never repeated
  -> acknowledged | quarantined
```

- `begin_free()`는 allocation당 최대 한 번만 호출한다.
- 외부 free 대상은 mutable raw pointer가 아니라 free lease에 고정된 `pointer_snapshot`이다.
- injected runtime에서는 exact `HipFreeKnownNotFreedError`만 미해제로 신뢰하고 같은 lease로 재시도한다. 서브클래스, 임의 attribute, 분류되지 않은 예외는 모두 outcome-uncertain다.
- exact native `_BoundHipContextRuntime`의 free exception은 caller metadata로 하향 분류하지 않고 항상 outcome-uncertain로 quarantine한다.
- external free 성공 후 acknowledgement가 중단되면 다음 close는 acknowledgement만 재시도한다. Registry의 idempotent `resolve_*` API는 기록된 `succeeded`/​`quarantined`를 구분하고, 반대 outcome 재시도를 mismatch로 거부한다.
- post-malloc publication 실패는 pre-reserved orphan lease로 exact pointer를 회수·acknowledge하거나, exact target/결과가 불확실하면 quarantine한다.

Quarantine는 device memory가 회수됐다고 주장하지 않는다. Exact pointer range가 있는 경우만 `quarantined_device_bytes`에 계산하고, pointer가 없는 malloc 결과는 `unknown_malloc_outcome_count`/​`unknown_requested_bytes`로 분리한다. 둘 다 `deallocation_success_count`를 증가시키지 않으며 terminal receipt는 `cleanup_quarantined`다.

## 5. 중단 안전 handoff와 close

Resident/Krylov child token은 caller가 identity를 먼저 보유한 뒤 parent가 live slot을 발행한다. Allocation owner는 one-slot handoff에 먼저 게시되고, owner registry의 cleanup snapshot이 caller `STORE` 전에 중단된 capability, free lease, orphan lease를 다시 회수한다. Failed-open cleanup context는 ready context와 중복된 소유자를 만들지 않고 preallocated exact object를 재사용한다.

RTC compiler handoff는 `copy_context().run(...)`으로 격리해 caller의 `ContextVar` 상태를 바꾸지 않는다. Native module load 전에 preallocated module cleanup owner를 one-shot weak handoff에 먼저 게시하고, `load_module_into(code_object, module_box)`가 exact box에 handle을 기록한 뒤 symbol binding과 kernel construction이 끝나면 같은 owner를 exact kernel로 원자 승격한다. Call/return/`STORE`, native load, symbol bind, kernel construct 또는 cleanup 진입 중 중단돼도 handoff가 동일 owner를 회수하므로 module handle이 소유자 없이 남지 않는다.

Parent 5-buffer group borrow는 다음 local phase를 사용한다.

```text
idle -> semantic_reserved -> active
                       \-> rollback_pending -> idle
active -> release_pending -> idle
```

Borrow/release registry terminal marker가 먼저 발행된 후 중단되어도 exact token/lease/capability tuple가 context에 남아 다음 acquire 또는 close가 재실행 없이 local 상태를 수렴시킨다.

### Close 순서와 lock 규칙

FreeSpace close:

```text
FreeSpace queue lock
  -> same-stream fence
  -> orphan/12 owned lineage retirement
  -> allocation owner close
  -> kernel close
  -> resident child lease release
```

Krylov close:

```text
Krylov queue lock
  -> active FGMRES child rejection
  -> same-stream completion/fence
  -> orphan/9 owned lineage retirement
  -> peer allocation owner close
  -> kernel close
  -> parent group borrow release
  -> FreeSpace semantic token release
```

상위 owner가 하위 context lock을 장시간 취득하지 않는다. Runtime/device validation은 lineage registry lock 밖에서 수행하고, HIP operation 후 registry acknowledgement를 별도 transaction으로 완료한다.

Native HIPRTC module unload도 persistent disposition을 사용한다. `status=0`을 관찰한 후 local handle clear가 중단되면 unload를 다시 호출하지 않고 local finalization만 수행한다. Status를 관찰하지 못한 Exception/BaseException은 outcome-uncertain로 고정하여 동일 module handle의 재-unload를 금지하고 cleanup failure를 보존한다.

### v0.2.19 사후 handoff 강화

v0.2.18 완료 뒤 더 강한 동시성 감사에서 common RTC compile entry와 FreeSpace/Krylov/FGMRES의 same-empty handoff에 추가 경쟁 경계가 확인됐다. v0.2.19는 각 handoff에 전용 lock과 `empty -> reserved -> published`, 실패 시 `spent` 상태를 넣고 handoff→cell 순서로 lock order를 고정했다. Native load는 shared cell lock 안에서 preflight하고 module/kernel cleanup은 모든 terminal field를 먼저 완결한 뒤 owner slot을 마지막에 비운다. Common RTC fixed-source compile도 persistent program owner와 inner implementation으로 감싸 cleanup-call 진입의 `BaseException`에서 소유권을 잃지 않는다.

따라서 동일 empty handoff를 두 thread가 경쟁해도 정확히 한 load/한 unload만 성립하고, publish/promote/close 경쟁은 stale owner overwrite나 deadlock 없이 수렴한다. 이 보강은 v0.2.18 당시 증거를 소급해 완전하다고 주장하지 않으며, 후속 v0.2.19 검증으로 별도 기록한다.

## 6. Receipt v2

FreeSpace/Krylov context v2는 다음 non-serializing summary와 telemetry를 추가한다.

- owner role, lineage profile/evidence scope
- managed buffer count/byte
- Krylov parent borrowed capability count `5`
- owner open/close count
- allocation/deallocation attempt·success, current·peak managed byte
- H2D/D2H/kernel/sync operation attempt·success
- module owner와 parent/semantic lease acquire·release lifecycle
- capability mint count/byte
- free/orphan acknowledgement count
- free/orphan quarantine count
- quarantined byte
- pointerless unknown malloc outcome count/requested byte
- failed-open의 exact allocation/upload/kernel stage prefix 및 byte conservation
- `pointer_values_serialized=false`, `promotion_eligible=false`

Batch/apply/evaluation receipt의 수치 의미는 변경하지 않으며 해당 schema version은 v1을 유지한다.

## 7. Claim boundary

이 통합으로 지원되는 claim은 다음으로 한정한다.

- FreeSpace 12개와 Krylov 9개의 실제 allocation/free가 owner-minted lineage로 관리됨
- Krylov가 FreeSpace 5개 capability를 all-or-none exclusive group borrow로 소비함
- failed-open token/owner/capability handoff, retryable free, terminal acknowledgement interruption, outcome uncertainty가 double-free/double-unload 없이 수렴됨
- raw pointer·device drift가 사용/정리 경계에서 fail-closed로 처리됨

다음은 이 FreeSpace/Krylov 통합 계약만으로는 계속 false다. 첫 항목의 resource-only lifetime은 후속 v0.2.19 계약에서 완료됐지만 device predecessor와 solver claim은 여전히 false다.

- FGMRES live context의 parent 3 + solver-owned 8 atomic group borrow(후속 [live checkpoint context v1](engine-v2-hip-fgmres-live-checkpoint-context-v1.md)에서 resource-only로 완료)
- authoritative predecessor producer, device-side mask-domain validator
- invalid-source multi-block failure atomicity
- later Arnoldi columns/restarts, full CPU/HIP solver parity
- iteration host-copy zero, PCG/AMG/DD, end-to-end O(N), speedup
- signed promotion, 독립 V&V, 상용 준비

## 8. 검증 근거

- FreeSpace/Krylov allocation-lineage·context·RTC·lease 집중 회귀: `350 passed`
- 독립 적대적 감사 집중 회귀: `171 passed`; 최종 source 기준 `BLOCKER/HIGH/MEDIUM 0`
- Engine v2 전체 `1427 passed`, ModelIR/MIDAS v2 `83 passed`, 레거시 핵심 `29 passed`; 실패·오류·skip·fallback `0`
- 실제 RX 6900 XT `gfx1030` FreeSpace/Krylov hardware gate: `2 passed`; skip/fallback `0`
- 저장소의 Draft 2020-12 schema self-check: `40/40 valid`
- Ruff, focused format check와 `py_compile`: 통과
- source/test/schema aggregate SHA-256: `aaad406e726cac86a456b06ab7fa9bd214dcdb975eb50c2447b3355ddab28c4e` / `22c1bcf3f9f8893bd6ae92ac83632ccb1ba76b4ad6e620932a66f240e9ff0fd7` / `f83bd07ebad9bd1f616d36da2cac05629a82ece238bfdaaf2504336286a73179`
- wheel: `745523` bytes, SHA-256 `1b50a1a2fe80716c7f064edf5348e25bf7b36280b92a6b1d2e2735ac4bc0c484`; 격리 설치에서 public API, 두 context-v2 schema와 FreeSpace/Krylov HIP kernel resource import 확인

v0.2.19 사후 hardening은 common RTC compile-owner `23 passed`, FreeSpace/Krylov/FGMRES RTC 집중 `169 passed`, same-empty 60회 경쟁(총 120 threads), publish-prefix interruption 3종, promote-vs-close deadlock 재현을 통과했고 독립 감사는 `BLOCKER/HIGH/MEDIUM/LOW = 0/0/0/0`으로 판정했다. 이 수치는 위 v0.2.18 historical hash·wheel 증거를 대체하지 않고 후속 source 상태를 검증한다.

이 검증은 injected runtime 적대적 경로와 실제 native hardware gate를 분리한다. 위 실행에서는 두 hardware gate가 실제 PASS했지만, 다른 환경의 hardware 미노출은 성공으로 간주하지 않는다.
