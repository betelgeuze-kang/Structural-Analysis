# Engine v2 HIP FGMRES canonical predecessor v1

- 상태: v0.2.20 Phase 0 canonical first-column producer 구현, `contract_only`/non-promoting
- schema version: `structural-analysis-hip-fgmres-canonical-predecessor.v1`
- capability profile: `phase0_live_first_column_device_sealed_predecessor`
- evidence scope: `device_sealed_predecessor_outcome_unobserved_non_promoting`
- 상위 기준: [Structural Solver Engine v2 마스터 로드맵](structural-solver-engine-v2-master-roadmap.md)

## 문서 범위

`HipFgmresCanonicalPredecessorExecutionContextV1`은 준비된 [live checkpoint context v1](engine-v2-hip-fgmres-live-checkpoint-context-v1.md)의 단일 child로 열린다. 이 child는 기존 exact11 allocation과 Krylov parent가 위임한 CSR3+reduction2를 바인딩하고, owned8을 0으로 초기화한 뒤 `INIT`부터 first-column candidate scale prefix와 장치 검증기까지 고정 schedule을 제출한다. 마지막에 exact-runtime stream fence 하나를 관찰하고, process-local conditional predecessor capability를 발행한다.

이 slice는 실제 mask 값과 device validation verdict를 host에 공개하지 않는다. 따라서 고정 prefix가 완료되고 mask-domain gate가 장치에 바인딩되었다는 사실만 증명하며, authoritative predecessor, checkpoint transaction 준비, solution 완료를 증명하지 않는다.

권위 구현은 [canonical predecessor source](../src/structural_analysis/engine_v2/assembly_backend/fgmres_canonical_predecessor_v1.py), 직렬화 receipt 계약은 [JSON Schema](../src/structural_analysis/schemas/hip_fgmres_canonical_predecessor_v1.schema.json), 고정 launch planner와 sealed runtime 계약은 [FGMRES RTC v2](../src/structural_analysis/engine_v2/assembly_backend/fgmres_rtc_v2.py)에 있다.

## Public API와 사용 순서

외부에 공개되는 핵심 API는 다음과 같다.

```python
opened = open_hip_fgmres_canonical_predecessor_context_v1(live_context)
context = opened.context

pending = context.enqueue_canonical_predecessor()
capability = context.synchronize_canonical_predecessor(pending)

validate_hip_fgmres_canonical_predecessor_receipt_v1(
    context.receipt(), expected_context=context
)
validate_hip_fgmres_canonical_predecessor_capability_v1(
    capability, expected_context=context
)

context.close()
```

- `open_hip_fgmres_canonical_predecessor_context_v1(...)`은 ready live context에 단 하나의 canonical child를 reserve하고 `HipFgmresCanonicalPredecessorOpenResultV1`을 반환한다.
- `enqueue_canonical_predecessor()`는 단 한 번만 성공하며, 직접 생성할 수 없고 변경할 수 없는 `HipFgmresCanonicalPredecessorPendingV1`을 반환한다.
- `synchronize_canonical_predecessor(pending)`은 exact issuer/context/nonce/snapshot을 검증하고 fence와 pending acknowledgement를 완료한 뒤 `HipFgmresCanonicalPredecessorCapabilityV1`을 반환한다. 같은 valid pending으로의 재호출은 이미 발행된 capability를 반환한다.
- capability는 `context_id`, 해당 fenced receipt hash, mask domain `(0, 1792, 7936)`에 결속된 process-local 권위이다. context가 close되면 더 이상 live capability로 검증되지 않는다.
- `close()`는 idempotent하다. canonical child가 살아 있는 동안 parent live context의 close는 거부된다.

## 자원 topology: exact11 + delegated5 = physical16

본 slice는 추가 device allocation이나 allocation-registry borrow를 만들지 않는다. 기존 live exact11과 이미 활성화된 parent/solver lease에서 생성한 비직렬 delegated projection 다섯 개를 결합한다.

| 그룹 | 권위 출처 | 순서가 고정된 role | 수 |
| --- | --- | --- | ---: |
| persistent parent3 | live exact11의 부모 borrow | `reduced_state`, `reduced_load`, `jacobi_inverse` | 3 |
| persistent owned8 | live checkpoint peer owner | `solution_x`, `true_residual`, `work_w`, `basis_v`, `preconditioned_basis_z`, `packed_dense_state`, `fgmres_control_state_v2`, `solve_record` | 8 |
| delegated operator3 | FreeSpace→Krylov parent borrow | `reduced_csr_row_ptr`, `reduced_csr_column_indices`, `reduced_csr_values` | 3 |
| delegated workspace2 | Krylov primitive owner | `reduction_ping`, `reduction_pong` | 2 |
| 합계 | 동일 live child authority | persistent11 + delegated5 | 16 |

delegated projection은 직렬화되지 않으며 raw pointer를 receipt에 넣지 않는다. device 사용 직전에 다음을 다시 검증한다.

- exact context/source apply과 active parent/solver lease identity·epoch
- role 순서, capability/owner/base 객체 identity, allocation id·generation
- element type/extent/byte length과 pointer snapshot
- loaded runtime, runtime domain/id, device ordinal, exact stream
- persistent11과 delegated5의 서로 다른 capability 및 physical range

변경, 교체, foreign/stale projection은 parent Krylov child를 poison하고 fail-closed로 종료된다. receipt의 `additional_allocation_count=0`, `additional_device_bytes=0`, `pointer_values_serialized=false`는 schema에 고정된다.

## 제출 계약: `INIT` → scale prefix → validator

`F`를 free DOF count, `M`을 restart dimension, `S = len(reduction_stage_output_counts_v2(F))`로 둔다. planner `canonical_first_column_predecessor_launches_v2(F, M)`는 host에서 중간 gate 값을 읽지 않고 다음을 하나의 deterministic tuple로 생성한다.

1. `CONTROL_INIT`과 initial `x`, RHS L2/L∞, initial SpMV/residual, initial gate
2. restart 1/column 0 Jacobi, Arnoldi SpMV, MGS/DGKS, normalization, Givens completion
3. candidate preparation, candidate SpMV/residual L2/L∞
4. trial/committed `x` scale metrics prefix
5. non-advancing `PREDECESSOR_VALIDATE_COLUMN0`

전체 kernel row 수는 정확히 `27 + 14S`이며 첫 row는 `CONTROL_INIT`, 마지막 row는 `PREDECESSOR_VALIDATE_COLUMN0`이다. 축약은 tree별 `reduction_tree_id`에 따라 `reduction_ping`/`reduction_pong`을 교대하며, conditional numerical work는 고정 row를 생략하지 않고 device gate에서 no-op한다.

validator는 control mode `PREDECESSOR_VALIDATE=14`를 사용한다. 요구 prestate는 schedule epoch `E=26+14S`, reduction epoch `Q=14S`, restart 1, column 0이며 validator 자체는 두 epoch을 증가시키지 않는다. 이 v1 producer는 후속 `CHECKPOINT_DECIDE → COMMIT_CHECKPOINT → CHECKPOINT_FINALIZE`를 제출하지 않는다.

## sealed owned8 초기화와 fence

kernel row 제출 전에 persistent11 중 owned8 전체 byte span을 각각 0으로 만든다. 초기화는 일반 runtime wrapper가 아니라 checkpoint lease가 고정한 exact loaded runtime의 sealed `hipMemsetAsync` callable, exact stream, exact token을 사용한다. callable identity는 kernel launch·module·device·stream fence identity와 함께 immutable binding snapshot에 포함된다.

정상 경로의 작업 수는 다음과 같다.

```text
8 sealed async memsets
+ (27 + 14S) fixed kernel launches
= 35 + 14S accepted asynchronous operations
```

모든 작업은 같은 stream에 제출되고 중간 synchronize는 0회이다. happy path는 마지막에 `hipStreamSynchronize` 1회만 성공한 뒤 exact pending count를 consume한다. fence가 일시적으로 실패하면 enqueue를 반복하지 않고 같은 pending authority로 fence만 재시도하므로 `fence_attempt_count`는 1보다 커질 수 있지만 성공 fence는 하나이다.

제품 경로 telemetry는 `h2d_operation_count=0`, `d2h_operation_count=0`, `intermediate_sync_count=0`, `fallback_count=0`을 고정한다. `source_apply_completion_bound`/`positive_jacobi_completion_bound`는 ready Krylov/live parent가 이미 성립시킨 완료 권위를 번들한다는 뜻이며, canonical child가 source apply를 다시 실행하거나 host에서 수치 결과를 재검증한다는 뜻은 아니다.

## device seal과 mask-domain 계약

validator는 `fgmres_control_state_v2` 내 다음 세 field를 사용한다.

| Offset | Field | 정상 validator 후 |
| ---: | --- | --- |
| 116 | `predecessor_validation_state` | `armed=1` |
| 120 | `predecessor_mask_snapshot` | 실제 `reduction_valid_mask`의 exact snapshot |
| 124 | `predecessor_reduction_epoch_snapshot` | `14S` |

state code는 `empty=0`, `armed=1`, `consumed=2`이다. validator는 actual device state가 정확한 predecessor 좌표와 mask domain을 만족할 때만 mask/reduction-epoch snapshot을 먼저 기록하고 `armed`를 마지막에 publish한다. 허용 mask는 다음 세 개다.

- `0`: inactive/no active candidate path
- `1792`: active candidate, scale metrics는 필요하지 않은 path
- `7936`: trial/committed scale metrics까지 유효한 path

후속 canonical checkpoint transaction이 연결되면 `CHECKPOINT_DECIDE`가 armed snapshot을 exact-match 검증하고 `consumed`로 바꾸며, commit은 consumed snapshot을 재검증하고 finalize가 seal field를 지우는 계약이다. 현 v1 producer receipt의 `checkpoint_transaction_ready`는 그러나 항상 `false`이다. producer가 transaction을 제출하지 않으며, actual mask/verdict를 host에서 관찰하지 않기 때문이다.

## Lifecycle, poison, retry

정상 lifecycle은 다음 순서다.

```text
context_ready
  -> predecessor_pending
  -> fence_observed_ack_pending
  -> predecessor_fenced
  -> context_closed
```

- enqueue는 context lock 아래 single-use로 보호된다. 두 thread가 동시에 호출해도 하나만 성공한다.
- foreign, 변조된, 다른 context에서 발행된 pending/capability는 fail-closed로 거부된다.
- 각 async call은 attempted count와 accepted lower/upper bound를 별도로 기록한다. 명시적 거부는 `0..0`, 성공은 `1..1`, call outcome이 불명확한 예외는 `0..1`로 기록한다.
- 아무 작업도 받아들여지지 않은 enqueue 실패는 `poisoned_no_work`, 하나라도 pending 가능성이 있는 실패는 `poisoned_pending_fence`로 수렴한다.
- partial/ambiguous enqueue는 checkpoint owner를 poison하여 새 launch를 막지만, 기존 work를 fence/ack하고 정리할 권위는 보존한다. `close()`도 pending이 있으면 먼저 fence/consume한다.
- fence 성공 후 pending acknowledgement의 return/STORE 경계가 끊겨도 `fence_observed_ack_pending` 또는 `poisoned_fence_observed_ack_pending`에서 fence를 다시 제출하지 않고 consume를 재개한다.
- poison 후 fence/ack가 완료되면 `poisoned_fenced`이며 conditional predecessor capability를 발행하지 않는다. cleanup이 실패하면 `cleanup_failed`와 retryable cleanup owner를 보존한다.

## Receipt, telemetry, backend provenance

receipt는 schema와 canonical receipt hash 외에 다음을 바인딩한다.

- live/Krylov/source-apply/recurrence plan의 context·receipt·state hash
- recurrence ABI, kernel identity/source, kernel origin, runtime/HIPRTC discovery provenance
- instance-specific canonical schedule hash와 고정 validator schedule hash
- persistent11 generation binding hash, physical16 projection hash
- primitive parent lease epoch, solver child lease epoch
- `F`, reduced CSR NNZ, `M`, `S`, capability count 11/3/2/16
- admitted mask domain, async acceptance interval, fence/consume counts, claim boundary

raw pointer, stream/module/function handle, owner/lease token은 직렬화하지 않는다. `extensions`는 빈 객체여야 하고 `promotion_eligible=false`는 schema에 고정된다.

`actual_backend` label은 receipt 작성자가 선택하지 않고 provenance에서 파생한다.

- `hip`: parent primitive가 `native_hiprtc_krylov_primitives_composite`/`hip`이고, FGMRES kernel이 internally compiled이며, runtime·HIPRTC library discovery가 `explicit`, `opt_rocm`, `system_loader` 중 하나인 경우
- `test_double`: 위 native provenance를 완전히 만족하지 않는 경우

schema를 만족하더라도 backend relabel, forbidden claim 승격, 변조된 receipt hash, expected live context와의 불일치는 semantic validator가 거부한다.

## Claim boundary

`predecessor_fenced`에서 참으로 승격되는 핵심 claim은 다음이다.

- inherited source apply completion과 positive Jacobi completion authority가 바인딩됨
- persistent parent3+owned8과 delegated CSR3+workspace2가 동일 runtime/device/stream에 바인딩됨
- owned8의 전체 byte span이 0으로 초기화되고 canonical prefix 제출이 fence됨
- device mask-domain validator가 실제 device state에 바인딩되고 seal을 arm함

`owned_content_initialized=true`는 owned8 zeroing 후 고정 prefix가 fence되었다는 수명·실행 사실이다. `device_mask_domain_gate_bound=true`는 validator launch와 후속 seal 검사 계약이 같은 device stream에 결속되어 fence되었다는 뜻이다. Product path는 control state를 D2H하지 않으므로 일반 receipt는 validator가 `armed`를 발행했는지를 승격하지 않고, 후속 transaction이 exact `armed` snapshot을 소비해야만 연속 실행이 가능한 conditional capability만 발행한다. 해의 정확성, validator verdict, mask의 특정 값, numerical predecessor의 권위를 뜻하지 않는다.

다음은 `predecessor_fenced`에서도 항상 `false`이며 schema와 semantic validator가 `true`로의 변조를 거부한다.

- `device_validation_outcome_host_observed`
- `actual_mask_host_observed`
- `authoritative_predecessor_proven`
- `checkpoint_transaction_ready`
- `invalid_source_destination_atomicity_proven`
- `live_solver_ready`
- `solution_ready`
- `iteration_host_copy_zero_proven`
- `asymptotic_o_n_proven`
- `speedup_proven`
- `commercial_ready`
- `promotion_eligible`

즉 이 slice는 full solver, later columns/restarts, invalid-source multi-block destination atomicity, O(N), 초고속 성능, 상용 준비를 증명하지 않는다.

## Current hash contract

아래 값은 문서 작성 시점의 current v0.2.20 source payload에서 재계산·확인한 값이다. 이전 v0.2.15/v0.2.19 문서와 receipt에 남은 ABI/source hash는 historical evidence이며, 이 문서의 current runtime admission에 사용하지 않는다.

| Current payload | SHA-256 |
| --- | --- |
| control-state ABI v2 | `sha256:5d6c72227aece05e89572c6283694f6e0012029409292a0d5c3ac930f928db7e` |
| solve-record ABI v2 | `sha256:cd6f5204b16a3aef0a274baeb57f162060dd9e18c051f9cde1c2c3a4dccbcfb1` |
| combined recurrence/kernel interface ABI v2 | `sha256:d719aebffadafa0c076bb4ff395df35e7b4bd888bdb613b8be9ff7ef0f20335d` |
| fixed HIPRTC source | `sha256:cdb8917b8553ceceed047b0c9b3e091afe9d80bccfece8242a778b5d56e00b18` |
| predecessor validator schedule | `sha256:b083896de86a808b1398d0fde4abe73726cb91f50399651274ef82dc09a5ef58` |
| downstream checkpoint transaction schedule, 현 producer에서는 미제출 | `sha256:d9b9115287e3b5839096e3f4417c04899ffc7592864483d918be55deaf4b4442` |

`canonical_schedule_hash`는 전역 상수가 아니라 `F`, `M`, 이들에서 파생된 `S`를 포함한 exact launch tuple의 instance hash이다. 각 receipt가 자신의 `bindings.canonical_schedule_hash`를 보존한다. current planner의 재계산 예시는 다음과 같으며, 이 세 값은 규범 상수가 아니다.

| `(F, M, S)` | Rows | Instance schedule hash |
| --- | ---: | --- |
| `(1, 1, 1)` | 41 | `sha256:780014584756387cb6043853e56cc8bc75b7629fb1d763fc92604994dc1aadcd` |
| `(513, 16, 2)` | 55 | `sha256:39dadd1514f8258ae85bf2c0a3b62b8ffce4ef8a0ec84a171bb415a9c153bcec` |
| `(262145, 16, 3)` | 69 | `sha256:211f008ac80062e0b7543d003cc9bf01a60a2bcb8a90d8644cecd2a7b263d8a3` |

## Focused/native verification

[focused canonical predecessor tests](../tests/test_engine_v2_hip_fgmres_canonical_predecessor_v1.py)는 다음을 대상으로 한다.

- exact `8 + (27+14S)` operation count, product H2D/D2H/intermediate-sync 0, final fence 1
- single-use concurrent enqueue, foreign/mutated pending 거부
- capability mutation·close 후 stale, enqueue 전 projection drift의 zero-work 거부
- first-memset exact rejection, partial rejected/ambiguous launch accepted interval·suffix 차단
- fence 실패 후 re-enqueue 없는 retry와 fence-observed consume before/after-pop 재시도
- receipt schema/hash, backend relabel, forbidden claim, schedule hash·telemetry 불일치 변조 거부
- pending/capability의 public construction 금지

현재 해당 focused 파일은 `14 passed`를 통과했다. 이 수치는 broad Engine v2 또는 상용 준비 증거가 아니다.

[native hardware test](../tests/test_engine_v2_hip_fgmres_canonical_predecessor_hardware_v1.py)는 실제 RX 6900 XT `gfx1030`에서 assembly → resident CSR → FreeSpace source apply → Krylov primitives → live exact11 → canonical producer 체인을 required gate로 실행했고 `1 passed`를 확인했다. 제품 telemetry에서는 다음이 확인되었다.

- `actual_backend="hip"`, internally compiled HIPRTC kernel, fallback 0
- sealed memset 8회, kernel row `27+14S`회, consumed operation `35+14S`회
- H2D 0, D2H 0, intermediate sync 0, final successful fence 1
- `canonical_producer_prefix_fenced=true`, `device_mask_domain_gate_bound=true`
- actual mask/verdict host-observed claim과 authoritative predecessor claim은 false

검증 코드는 제품 telemetry 밖의 verification-only D2H를 한 번 수행해 control state의 실제 값도 대조했다. `reduction_valid_mask ∈ {0,1792,7936}`, `reduction_epoch=14S`, `schedule_epoch=26+14S`, state `armed=1`, exact mask snapshot, exact reduction-epoch snapshot을 확인했다. 이 D2H는 테스트 oracle일 뿐 product path/receipt telemetry에 포함되지 않는다.

이 native 1 pass는 현 슬라이스의 실제 device submission·seal·fence·cleanup 증거이다. authoritative checkpoint transaction, invalid-source atomicity, later recurrence, CPU/GPU numerical parity, O(N), speedup, full solver, commercial readiness를 증명하지 않는다.

## Selected aggregate와 wheel 검증

v0.2.20에서 변경·소비하는 핵심 source 9개, focused test 9개, 전체 42개 schema의 순서 고정 aggregate는 다음과 같다. 이 값은 표시된 파일 집합의 재현 편의용 해시이며 전체 repository, release signature 또는 promotion receipt가 아니다.

- selected source aggregate: `sha256:110ab18c3d6e5cbd4ec1d21750cd9e9aca064bc1b6ef401ee46856d97d58d534`
- selected focused-test aggregate: `sha256:edbd15e1757800fa9173b7380f34b9e8216de6e4c3da11b6d2644f877c66b9d9`
- 42-schema aggregate: `sha256:515ad55eabdbb810dad52e66747c6f5ba31eeaca01ca712bf7543be297020969`
- wheel: `802664` bytes, `sha256:a58afc56f4d5bd37d18758718b85dd67e4859caa36b8c3e0bd01729794e47dd6`

전체 Engine v2 회귀는 `1650 passed in 1420.51s`로 실패·오류·skip 없이 완료됐다. 첫 실행에서 발견한 과거 `reserved_zero_fields` test key 1건은 현재 ABI의 `transient_zero_fields`로 수정하고 해당 native test를 단독 재검증한 뒤 전체 suite를 처음부터 재실행한 결과다.

선택 aggregate는 각 `sha256sum` 출력의 상대 경로와 순서를 포함해 다시 SHA-256한 값이다.

```bash
sha256sum \
  src/structural_analysis/engine_v2/__init__.py \
  src/structural_analysis/engine_v2/assembly_backend/__init__.py \
  src/structural_analysis/engine_v2/assembly_backend/fgmres_canonical_predecessor_v1.py \
  src/structural_analysis/engine_v2/assembly_backend/fgmres_context_v2.py \
  src/structural_analysis/engine_v2/assembly_backend/fgmres_live_checkpoint_context_v1.py \
  src/structural_analysis/engine_v2/assembly_backend/fgmres_recurrence_plan_v2.py \
  src/structural_analysis/engine_v2/assembly_backend/fgmres_rtc_v2.py \
  src/structural_analysis/engine_v2/assembly_backend/kernels/engine_v2_fgmres_v2.hip.cpp \
  src/structural_analysis/engine_v2/assembly_backend/krylov_primitives.py \
  | sha256sum

sha256sum \
  tests/test_engine_v2_capability_matrix.py \
  tests/test_engine_v2_hip_fgmres_canonical_predecessor_v1.py \
  tests/test_engine_v2_hip_fgmres_canonical_predecessor_hardware_v1.py \
  tests/test_engine_v2_hip_fgmres_context_v2.py \
  tests/test_engine_v2_hip_fgmres_initial_hardware_v2.py \
  tests/test_engine_v2_hip_fgmres_live_checkpoint_context_v1.py \
  tests/test_engine_v2_hip_fgmres_recurrence_plan_v2.py \
  tests/test_engine_v2_hip_fgmres_rtc_v2.py \
  tests/test_engine_v2_hip_krylov_fgmres_producer_projection_v1.py \
  | sha256sum

rg --files src/structural_analysis/schemas -g '*.schema.json' \
  | sort | xargs sha256sum | sha256sum
```

Wheel을 빈 target에 `--no-deps`로 설치한 뒤 그 target의 top-level canonical API, packaged canonical schema, fixed HIP kernel resource와 current ABI marker를 import/read해 확인했다. 이는 패키지 완결성 검증이며 솔버 수치 정확성이나 상용 승격 증거가 아니다.

## 다음 권위 단계

1. invalid CSR/non-finite source가 multi-block destination을 부분 오염시키지 않는 destination atomicity를 구현·native 검증한다.
2. sealed capability를 후속 checkpoint transaction context와 소유권 단절 없이 연결하고 decide·commit·finalize의 seal consume/clear를 receipt에 결속한다.
3. v0.2.23 global suffix owner가 later column과 fixed guard submission을 연결했다. 남은 active later-restart/final-guard integrated coverage, completion/export와 product outcome observation을 닫은 뒤 model-family CPU/HIP parity를 검증한다.
4. 그 후에만 iteration host-copy-zero, O(N) 복잡도, 속도 향상, 상용 승격을 별도 evidence gate로 평가한다.
