# Engine v2 HIP FGMRES sealed checkpoint transaction v1

- 상태: v0.2.22 Phase 0 historical checkpoint implemented, current v0.2.26 downstream-compatible, `contract_only`/non-promoting
- schema version: `structural-analysis-hip-fgmres-sealed-checkpoint-transaction.v1`
- capability profile: `phase0_canonical_capability_consuming_sealed_checkpoint_transaction`
- evidence scope: `canonical_capability_consumed_device_outcome_unobserved_non_promoting`
- 상위 producer: [canonical predecessor v1](engine-v2-hip-fgmres-canonical-predecessor-v1.md)
- 수치·atomicity 계약: [checkpoint invalid-source atomicity v1](engine-v2-hip-fgmres-checkpoint-atomicity-v1.md)
- 전체 설계: [HIP FGMRES full recurrence ABI v2](engine-v2-hip-fgmres-recurrence-abi-v2.md)
- 하위 consumer: [global recurrence owner v1](engine-v2-hip-fgmres-global-recurrence-v1.md)

## 문서 범위

`HipFgmresSealedCheckpointTransactionExecutionContextV1`은 아직 열려 있는 canonical predecessor context의 단일 non-owning child다. Canonical producer가 발행한 process-local conditional predecessor capability를 reserve한 뒤 enqueue 시작에서 정확히 한 번 소비하고, 같은 live kernel·checkpoint owner token·stream·direct11 allocation에 `CHECKPOINT_DECIDE -> PREFLIGHT_COMMIT_SOURCE -> COMMIT_CHECKPOINT -> CHECKPOINT_FINALIZE` 네 row를 제출한다. Transaction 자체의 마지막 exact-runtime fence 한 번과 pending acknowledgement가 끝나면 outcome-unobserved conditional continuation capability를 발행한다.

이 연결은 v0.2.16 caller-attested raw predecessor를 product live chain의 canonical capability로 대체한다. 다만 product path는 actual mask, validator verdict, commit gate, commit 여부 또는 device numerical outcome을 D2H하지 않는다. 따라서 발행 capability와 receipt는 고정 프로그램의 연속 실행만 조건부로 증명하며 authoritative predecessor, numerical transaction, solver 또는 solution을 증명하지 않는다.

v0.2.24 global recurrence child는 이 conditional continuation을 single-use consume해 canonical global-program suffix만 제출한다. 이 downstream 소비는 sealed receipt를 authoritative numerical transaction으로 소급 승격하지 않는다. Standalone sealed/global receipt validation은 structural/semantic consistency만 검증하며 process-local provenance에는 `expected_context`, 외부 전달 provenance에는 signed chain이 필요하다.

권위 구현은 [sealed transaction source](../src/structural_analysis/engine_v2/assembly_backend/fgmres_sealed_checkpoint_transaction_v1.py), 직렬화 계약은 [JSON Schema](../src/structural_analysis/schemas/hip_fgmres_sealed_checkpoint_transaction_v1.schema.json)에 있다.

## Public API와 사용 순서

```python
canonical_pending = canonical_context.enqueue_canonical_predecessor()
predecessor = canonical_context.synchronize_canonical_predecessor(
    canonical_pending
)

opened = open_hip_fgmres_sealed_checkpoint_transaction_context_v1(
    canonical_context,
    predecessor,
)
context = opened.context

pending = context.enqueue_sealed_checkpoint_transaction()
continuation = context.synchronize_sealed_checkpoint_transaction(pending)

validate_hip_fgmres_sealed_checkpoint_transaction_receipt_v1(
    context.receipt(),
    expected_context=context,
)
validate_hip_fgmres_sealed_checkpoint_continuation_capability_v1(
    continuation,
    expected_context=context,
)

context.close()
canonical_context.close()
```

- `open_hip_fgmres_sealed_checkpoint_transaction_context_v1(...)`은 fenced canonical context와 exact predecessor capability를 검증하고 단 하나의 sealed child를 reserve한다.
- `enqueue_sealed_checkpoint_transaction()`은 reserved authority와 pending map이 비어 있음을 재검증하고 predecessor capability를 single-use consume한 뒤 exact four-row program을 제출한다.
- `synchronize_sealed_checkpoint_transaction(pending)`은 transaction-owned final fence를 관찰하고 exact pending reservations를 원자적으로 consume한 뒤 conditional continuation capability를 발행한다.
- pending과 continuation은 context만 발행할 수 있고 외부에서 직접 생성할 수 없다. Issuer/context/nonce/snapshot 또는 receipt hash가 바뀌면 fail-closed다.
- 작업을 제출하지 않은 child의 `close()`는 reservation만 반환하므로 같은 아직 유효한 predecessor capability로 다시 열 수 있다. Enqueue가 capability를 소비하면 그 canonical capability는 terminal이며 새 transaction을 열 수 없다.
- Sealed child가 살아 있는 동안 canonical context의 close는 거부된다. Child close는 live allocation, borrow, module 또는 checkpoint owner를 해제하지 않고 non-owning child reservation만 반환한다.

## 수명·권위 계층

```text
live checkpoint context
  exact11 + kernel/module + checkpoint token + stream
    -> canonical predecessor child
       delegated CSR3 + reduction scratch2 = physical16
       canonical prefix fence + conditional predecessor capability
         -> sealed checkpoint transaction child
            same direct11/physical16 + same token/stream/kernel
            capability single-use consume + fixed four rows + final fence
              -> global recurrence child
                 same authority + exact suffix only + final fence
                 outcome-free completion capability
```

Lock 순서는 child transaction에서 canonical, live, kernel owner 방향으로만 진행한다. Open은 canonical capability와 idle owner를 같은 reservation 경계에서 묶고, enqueue 전과 각 row 직전에 다음 immutable binding을 재검증한다.

- exact canonical/live context와 receipt lineage
- kernel object, loaded runtime, checkpoint owner token, device와 stream identity
- `F`, `M`, iteration/restart policy와 tolerance 값
- direct11 role 순서와 exact pointer snapshot
- canonical exact16 physical projection hash와 generation binding hash
- fixed four-row launch tuple과 각 row의 모든 field
- checkpoint owner의 exact `(stream, pending reservation count)` snapshot

Enqueue 전 drift는 zero-work로 거부되고 capability는 미소비 상태를 유지한다. Capability가 소비된 뒤의 rejection, ambiguity 또는 partial enqueue는 capability를 복원하지 않고 owner를 poison한다. Cleanup은 처음 고정한 binding으로 이미 받아들여졌을 수 있는 work만 fence/ack한다.

## Fixed four-row program

`S = len(reduction_stage_output_counts_v2(F))`, `E0=26+14S`, `Q=14S`에서 exact launch tuple은 다음 네 row다.

| 순서 | schedule epoch | device 계약 |
| --- | --- | --- |
| `CHECKPOINT_DECIDE` | `E0 -> E0+1` | armed snapshot과 live mask/epoch을 대조하고 `armed(1) -> consumed(2)`로 전이한 뒤 pending outcome을 계산한다. |
| `PREFLIGHT_COMMIT_SOURCE(mode=9)` | `E0+1`, non-advancing | commit gate가 true일 때 source만 전역 검사하고 정상 admission에서는 `consumed(2) -> commit-preflighted(3)` ticket을 발행한다. |
| `COMMIT_CHECKPOINT` | `E0+1 -> E0+2` | state 3, active/error와 exact sealed snapshot admission 뒤 pure copy만 수행한다. |
| `CHECKPOINT_FINALIZE` | `E0+2 -> E0+3` | pending outcome을 대조·발행하고 transient/snapshot을 먼저 정리한 뒤 validation state를 마지막에 clear한다. |

성공 schedule endpoint는 `E=29+14S`, `Q=14S`이고 checkpoint schedule hash는 `sha256:2423da989b6cd419b7c4bef46d6c76f2120825a0c840cb516803bb2643ca11e5`다. 이 host context는 네 row를 모두 제출할 뿐 actual device gate를 읽어 분기하지 않는다.

정상 sealed lifecycle만 `2 -> 3 -> 0`이다. Multi-block preflight의 block>0 invalid lane이 block 0 state CAS보다 먼저 `active=0`을 publish할 수 있으므로 invalid failure의 validation state는 scheduling에 따라 `consumed(2)` 또는 `commit-preflighted(3)`일 수 있다. 두 경우 모두 mask와 reduction-epoch snapshot은 유지되고 뒤의 COMMIT은 `active=0` admission에서 destination을 쓰지 않는다. 이 state 차이는 destination atomicity를 바꾸지 않으며, host receipt가 어느 device state였는지를 관찰했다는 뜻도 아니다.

Invalid-source destination atomicity는 [v0.2.21 계약](engine-v2-hip-fgmres-checkpoint-atomicity-v1.md)의 전제, 즉 exact registered nonoverlap allocation, same stream, exclusive source ownership과 fixed owner sequence에서만 bound된다. Receipt의 `invalid_source_destination_atomicity_contract_bound=true`는 이 실행이 그 고정 계약에 결속됐다는 의미이지, host가 이번 device outcome이나 commit 여부를 관찰했다는 의미가 아니다.

## Operation·fence·resource 계약

정상 sealed transaction 자체의 product-path 수치는 다음과 같다.

```text
canonical predecessor capability reservation 1
canonical predecessor capability consumption 1
kernel launches 4
successful final fence 1
pending reservation consume 4
additional allocation/borrow/checkpoint-owner/module 0
additional H2D/D2H/intermediate sync/fallback 0
```

Canonical predecessor producer는 이 child가 열리기 전에 자신의 prefix를 이미 final fence 한 번으로 닫았다. 따라서 end-to-end canonical producer + sealed transaction 체인의 successful fence는 총 2회이며, transaction receipt의 `fence_success_count=1`을 전체 체인의 one-fence claim으로 확대하면 안 된다.

본 child는 새 allocation, device byte, allocation-registry borrow, checkpoint owner acquisition 또는 module load/unload를 수행하지 않는다. Persistent direct11과 canonical delegated5를 그대로 사용하므로 `persistent_capability_count=11`, `physical_capability_count=16`, `transaction_launch_count=4`다. Pointer, stream, token, module/function handle은 receipt에 직렬화하지 않는다.

## Lifecycle, poison, retry

정상 lifecycle은 다음과 같다.

```text
context_ready
  -> transaction_pending
  -> fence_observed_ack_pending
  -> transaction_fenced
  -> context_closed
```

- Open과 enqueue 경쟁에서는 child 하나와 enqueue 하나만 성공한다.
- Capability는 enqueue 시작에서 소비되므로 첫 row rejection을 포함해 enqueue attempt 이후에는 재사용되지 않는다.
- 각 kernel call은 attempted count와 accepted lower/upper bound를 기록한다. 명시적 rejection은 `0..0`, 성공은 `1..1`, outcome이 불명확한 예외는 `0..1`을 더한다.
- Accepted work가 없으면 `poisoned_no_work`, 하나라도 pending일 수 있으면 `poisoned_pending_fence`로 수렴한다. Poisoned path는 continuation capability를 발행하지 않는다.
- Fence 실패는 row를 다시 enqueue하지 않고 같은 pending authority로 fence만 재시도한다.
- Fence 성공 후 acknowledgement의 before-pop/after-pop 경계가 끊기면 `fence_observed_ack_pending` 계열에서 fence를 반복하지 않고 pending consume만 재개한다.
- Exact pending map이 비어 있지 않거나 consume count가 accepted interval과 맞지 않으면 fail-closed다. Ambiguous accepted interval은 재시도에서 임의의 lower bound를 authoritative consumed count로 만들지 않는다.
- Open rollback이나 close cleanup이 실패하면 error가 `cleanup_owner`를 보존하므로 같은 owner로 정리를 재시도할 수 있다.
- Global child reservation은 parent에 weak lease로 보존된다. Factory가 context를 성공적으로 연 뒤 결과 assignment 전에 취소되어 child가 소멸하고, continuation이 아직 unconsumed이며 exact pending map이 빈 경우 parent close는 dead lease를 lazy reap한다.
- Continuation이 이미 consumed이거나 work가 pending인 downstream cleanup owner 자체가 유실된 경우는 자동 reap하지 않는다. Parent close는 fail-closed로 거부되며 운영 계층은 cleanup owner를 유지하고 명시적 fence/ack/close retry를 완료해야 한다.

## Receipt와 conditional continuation

Receipt는 canonical/live/Krylov/source-apply lineage, recurrence plan/kernel ABI, current source hash, canonical/validator/checkpoint schedule, direct11 generation과 physical16 projection, lease epoch, dimensions, exact-zero resource telemetry와 claim boundary를 canonical hash로 결속한다. Standalone validator는 current source/ABI/schedule identity와 closed-schema semantic consistency를 재생하지만, canonical hash는 서명이 아니므로 coordinated provenance 진본성까지 증명하지 않는다. Process-local `expected_context` 검증은 live context의 현재 receipt와 exact hash를 대조해 `actual_backend`를 포함한 provenance relabel을 거부한다. 장기 보관·외부 전달 receipt의 독립 진본성은 향후 서명 gate다.

`transaction_fenced`에서 다음 실행 사실은 true다.

- live Krylov parent와 canonical predecessor capability가 bound됨
- predecessor capability가 single-use consume됨
- direct11/physical16과 same runtime/device/stream continuity가 bound됨
- exact fixed four-row program이 transaction-owned final fence로 완료됨
- sealed state-transition program과 scoped invalid-source atomicity 계약이 bound됨
- outcome-unobserved conditional continuation capability가 발행됨

하지만 product path는 device numerical state를 복사하지 않는다. 따라서 continuation은 후속 고정 device program에 전달할 수 있는 process-local conditional authority일 뿐 성공한 numerical checkpoint, continuation decision 또는 solution의 증거가 아니다. 다음 claim은 receipt와 semantic validator에서 항상 false다.

- actual mask, validator verdict, commit gate, checkpoint commit의 host 관찰
- authoritative predecessor와 authoritative numerical transaction
- live solver, solution, later recurrence readiness
- iteration host-copy zero, O(N), speedup
- promotion eligibility와 commercial readiness

## Current와 historical identity

| Current v0.2.26 executable payload | SHA-256 |
| --- | --- |
| predecessor validator schedule | `sha256:b083896de86a808b1398d0fde4abe73726cb91f50399651274ef82dc09a5ef58` |
| checkpoint transaction schedule | `sha256:0583f66e5faa848da734ff8fbcc430d8bb71ef9fc854fab49121be3f61691e5d` |
| global schedule semantic contract | `sha256:7c18ba9190fef663fec8e1f87e0f56ec393e23f04d4753ffbc3c707bff1a10ea` |
| combined recurrence/kernel ABI | `sha256:6a361ccfd0dbbe544e93b6c9ea788cc3702f6f924a969a3aa3deebf3292f315b` |
| fixed HIP source | `sha256:a5b39fb976aa330eaffae74feb8561f241df662a21dc32354b8010af2bb1c93d` |

| Historical v0.2.22 sealed evidence payload | SHA-256 |
| --- | --- |
| predecessor validator schedule | `sha256:b083896de86a808b1398d0fde4abe73726cb91f50399651274ef82dc09a5ef58` |
| checkpoint transaction schedule | `sha256:2423da989b6cd419b7c4bef46d6c76f2120825a0c840cb516803bb2643ca11e5` |
| combined recurrence/kernel ABI | `sha256:bb5b94457fbf3be4c5f2b38dda3f50c8a757094e0b97fb4d7288e7bdbf4db39f` |
| fixed HIP source | `sha256:a1d2da3f0d9a6c4a574fb1cb9d5be24c30c1e6e5e1c6de3ff1a4b50eeefad113` |

v0.2.26 current identity는 exact full-final-cycle checkpoint-to-guard handoff와 malformed mandatory-prestate prepublication fail-closed를 recurrence semantic payload/schema와 HIP source에 결박한다. Public sealed/global receipt·completion schema는 변경되지 않았다. Historical v0.2.22 native evidence를 current identity의 native evidence로 소급 재해석하지 않는다. Future action gate `commit_required=continuation_required=0`만으로 과거 COMMIT 미실행이나 rollback을 증명하지 않으며, late-invalid no-commit과 destination 보존은 source-only preflight ordering과 full-byte sentinel로 별도 검증한다. v0.2.21 atomicity source `sha256:ce4353f61fc3e8cd1311ad52ce50f21a677c7bfa865a2656aa5447b6ec104a83`도 historical identity다.

## 검증 현황과 남은 gate

[적대적 focused unit](../tests/test_engine_v2_hip_fgmres_sealed_checkpoint_transaction_v1.py)은 `23 passed`를 확인했다. 범위는 exact four-row/pending map, no-additional-resource telemetry, unused-close/reopen와 consumed-terminal, open/enqueue race, consume-return interruption reconciliation, binding drift, partial/ambiguous enqueue poison, fence·ack retry, callback reentrancy, closed receipt의 current-binding claim release, fixed identity forgery와 context-bound provenance relabel rejection, nonconstructible capability다. 인접 live+canonical legacy 회귀는 `56 passed`를 확인했고, Engine v2 + MIDAS v2 + ModelIR v2 광범위 회귀는 `1778 passed in 2682.66s (0:44:42)`를 통과했다.

[Actual `gfx1030` hardware gate](../tests/test_engine_v2_hip_fgmres_sealed_checkpoint_transaction_hardware_v1.py)는 latest v0.2.22 source에서 valid canonical -> sealed chain `1 passed in 41.30s`와 `F=513` late NaN/Inf multi-block sealed invalid-source `1 passed in 432.80s`, 합계 2 scoped cases를 확인했다. Valid case는 canonical fence 1 + transaction fence 1 = total 2, exact four-row pending consume와 additional allocation/borrow/module/copy/fallback 0을 관찰했다. Invalid case는 state `{2,3}` 허용, pending status/code 6/47, future action gate clear, mask/snapshot provenance 보존과 두 destination full-byte 불변을 verification-only D2H로 대조했다.

저장소 밖에서 만든 historical v0.2.22 `826616`-byte wheel(`sha256:9c0eaaa4e27f2cbb9b2ac827a91b1f3785c8ca01c3e494077d01aae763420ffb`)을 격리 target에 설치해 public sealed API, Draft 2020-12 sealed schema, HIP kernel resource import와 당시 source hash를 확인했다.

이 D2H는 테스트 oracle이며 product receipt telemetry가 아니다. 따라서 scoped native byte-preservation 결과를 actual mask/verdict/commit host observation, authoritative numerical transaction 또는 solution claim으로 승격하지 않는다.

v0.2.24 sealed/global lifecycle focused `6 passed in 123.64s`는 abandoned unconsumed factory result의 weak-lease reap, consumed/pending fail-closed 경계와 parent/child close 순서를 확인했고 independent lifecycle audit은 추가 defect를 찾지 않았다. v0.2.25는 process-local consumed/pending owner-loss recovery를 구현했다. Global owner의 actual integrated `gfx1030` gate는 이 continuation을 소비해 active later column, restart `1 -> 2 -> 3`, v0.2.26 exact full-cycle active `FINAL_GUARD`를 실행했지만 sealed receipt의 numerical outcome claim을 바꾸지 않는다. 다음 순서는 completion-only solution/record/residual export와 명시적 terminal-outcome observation contract이며, 그 뒤 CPU/HIP full recurrence parity와 iteration host-copy-zero를 각각 별도 gate로 닫는다.
