# Engine v2 HIP FGMRES completion-only export v1

- 상태: Phase 0 implemented, `contract_only`/non-promoting
- schema version: `structural-analysis-hip-fgmres-completion-export.v1`
- capability profile: `phase0_fenced_completion_three_buffer_blocking_d2h_export`
- evidence scope: `fenced_completion_bytes_exported_outcome_uninterpreted_non_promoting`
- 상위 owner: [sealed-continuation global recurrence owner v1](engine-v2-hip-fgmres-global-recurrence-v1.md)
- solve-record ABI: [HIP FGMRES full recurrence ABI v2](engine-v2-hip-fgmres-recurrence-abi-v2.md)

## 문서 범위

`HipFgmresCompletionExportExecutionContextV1`은 still-open global recurrence owner의 단일 non-owning child다. Global owner가 fixed suffix를 fence하고 checkpoint pending acknowledgement를 마친 뒤 발행한 exact process-local completion capability를 reserve하고, 첫 host read 직전에 정확히 한 번 consume한다.

Export는 다음 세 device buffer만 고정 순서로 blocking D2H한다.

1. `solution_x`
2. `true_residual`
3. `solve_record`

`solve_record`는 v2 ABI로 크기와 lineage만 bound된 opaque bytes다. 이 contract는 record를 parse하지 않고, 수치 content를 읽어 host에서 분기하지 않으며, terminal outcome/status를 해석하지 않는다. `solution_x`와 `true_residual`의 bytes를 내보내는 것도 그 자체로 numerical success나 solution-ready를 뜻하지 않는다.

권위 구현은 [completion export source](../src/structural_analysis/engine_v2/assembly_backend/fgmres_completion_export_v1.py), runtime의 blocking copy binding은 [HIP context runtime](../src/structural_analysis/engine_v2/backends/hip/context.py), 직렬화 계약은 [Draft 2020-12 JSON Schema](../src/structural_analysis/schemas/hip_fgmres_completion_export_v1.schema.json)에 있다.

## Public API와 사용 순서

```python
pending = global_context.enqueue_remaining_global_recurrence()
completion = global_context.synchronize_global_recurrence(pending)

opened = open_hip_fgmres_completion_export_context_v1(
    global_context,
    completion,
)
export_context = opened.context

result = export_context.export_completion_buffers()

validate_hip_fgmres_completion_export_receipt_v1(
    result.receipt,
    expected_context=export_context,
)
validate_hip_fgmres_completion_export_result_v1(
    result,
    expected_context=export_context,
)

export_context.close()
global_context.close()
```

- Open은 exact `recurrence_fenced` global context와 그 context가 발행한 completion capability를 검증하고 sole downstream child를 reserve한다. 이 단계에서 capability는 아직 consume되지 않고 D2H도 발생하지 않는다.
- `export_completion_buffers()`와 `export()`는 같은 operation이다. 첫 호출은 세 host staging array를 먼저 할당한 뒤, 첫 D2H 직전에 capability를 consume하고 세 copy와 immutable publication을 수행한다.
- 성공 후 같은 context에 대한 반복·동시 호출은 추가 copy 없이 같은 published result identity로 수렴한다. 이 idempotent result retrieval은 capability가 여러 번 consume된다는 뜻이 아니다.
- 성공한 `result` object을 caller가 보유하면 export/global/sealed/canonical/live context를 닫은 뒤에도 detached bytes는 유효하다.

## Fixed payload·copy 계약

`F`는 free DOF 수, `R`은 global recurrence plan에 bound된 maximum restart count다. 이 export slice는 `F>0`, `R>0`인 exact authority만 받는다.

| 순서 | role | host dtype/shape | exact bytes | 의미 |
| ---: | --- | --- | ---: | --- |
| 1 | `solution_x` | `<f8`, `(F,)` | `8F` | committed solution raw bytes; 미해석 |
| 2 | `true_residual` | `<f8`, `(F,)` | `8F` | committed true-residual raw bytes; 미해석 |
| 3 | `solve_record` | `|u1`, `(192+72R,)` | `192+72R` | opaque v2 solve-record bytes |

전체 export byte 수는 정확히 `16F + 192 + 72R`이며 `exported_buffer_count=3`이다. `fgmres_control_state_v2`, basis, preconditioned basis, dense state, CSR 및 reduction scratch는 export하지 않는다.

Native runtime은 loader-issued `hipMemcpy` function을 `hipMemcpyDeviceToHost` kind에 고정한 immutable `_BoundBlockingD2HCopy`로 보존한다. Native `hip` receipt는 factory result·runtime `_blocking_d2h_copy`·exact class·그 내부 `_memcpy`/loaded-runtime의 identity 관계가 모두 일치해야 한다. Export owner는 callable type의 `__call__`, ctypes `argtypes`/`restype`/`errcheck`까지 runtime/loaded-runtime/source authority와 함께 snapshot한다. 각 copy 직전에 authority와 binding drift를 다시 검증하고, 세 copy 후 publication 전에 authority를 한 번 더 검증한다.

Global suffix는 completion capability 발행 전에 이미 exact owning runtime으로 fence되었다. 따라서 export는 별도 `hipStreamSynchronize`를 호출하지 않고, 각 blocking `hipMemcpy` 호출이 돌아오기 전에 해당 host staging copy가 종료된다. 이는 `explicit_stream_sync_count=0`을 뜻하며 blocking copy 자체가 없다거나 D2H가 0이라는 뜻이 아니다.

## Single-use·parent lifetime·fail-closed

수명 계층은 다음과 같다.

```text
live -> canonical -> sealed -> global recurrence_fenced
                                    -> completion export child
                                       three blocking D2H
                                       immutable detached result
```

- Global owner는 export child를 정확히 하나만 reserve한다. Foreign, forged, mutated, stale capability, 다른 context의 capability, 두 번째 active child와 terminally consumed child는 copy 전 fail-closed다.
- Export child가 active인 동안 global `close()`는 거부된다. 먼저 export child를 닫아 lease를 반환한 뒤 global owner를 닫아야 한다.
- Host staging은 irreversible consume 전에 할당한다. 할당 실패는 allocation accounting을 rollback하고 capability를 unused로 남겨, 같은 context에서 copy 없이 재시도할 수 있다.
- Completion capability는 첫 host read 전에 irreversibly consume된다. Consume 후 copy/binding/authority 실패나 complete publication object 생성 전 interruption/return loss가 발생하면 context는 `poisoned`로 수렴하고 D2H를 재시도하지 않는다. 세 payload·hash가 검증된 publication object가 이미 만들어졌다면 final publication만 monotonic하게 재개하여 같은 result를 반환한다.
- 부분 copy가 성공했더라도 세 payload와 hash 검증이 모두 완료되기 전에는 `HipFgmresCompletionExportResultV1`을 publish하지 않는다. 실패 receipt의 payload hash는 zero sentinel을 유지하고 `result is None`이다.
- 실패는 exact attempted/succeeded prefix telemetry와 `cleanup_owner` affine exception을 남긴다. Caller는 cleanup owner를 보존하고 `close()`를 retry해 parent lease를 반환해야 한다.
- Export 중 parent/global validator가 발생시킨 regular exception도 export 경계에서 exporter 자체를 `cleanup_owner`로 갖는 stable error로 재결속한다. 상위 owner를 닫아 활성 export child를 남기는 오류 경로를 허용하지 않는다.
- Consumed child release는 active weak reference를 먼저 제거한 뒤 terminal bit을 고정한다. 두 authoritative store 사이 중단되어도 consumed bit이 reopen을 차단하고 exporter `close()` retry는 parent를 영구 wedged 상태로 남기지 않는다.
- Consume 전 unused child가 유실되면 global parent는 weak lease를 reap해 다시 reserve할 수 있다. Consume 후 child가 유실되면 capability는 terminal로 남으며 재export하지 않는다.

Blocking copy를 사용하므로 Python control이 copy call에서 돌아온 뒤 pending DMA가 private staging buffer나 upstream device allocation의 수명을 넘어 남지 않는다. 이 특성은 async D2H recovery, host-buffer pinning ledger 및 별도 stream pending acknowledgement를 이 v1 contract에 추가하지 않고도 parent close를 fail-closed로 유지하는 근거다.

## Authority·immutable result·hash

Export authority는 다음을 process-local immutable snapshot으로 결속한다.

- exact global context ID, global fenced receipt hash와 completion receipt hash
- continuation schedule, recurrence plan, recurrence kernel ABI, combined ABI, kernel identity와 fixed source hash
- architecture, device ordinal, exact runtime/loaded-runtime/stream identity
- direct allocation generation binding, physical projection과 three-source binding hash
- `solution_x`, `true_residual`, `solve_record`의 exact role, element type, byte extent, allocation generation, runtime owner, device ordinal과 base pointer snapshot
- solve-record ABI hash와 exact `F`, `R`

Completion capability identity와 device pointer 값은 receipt에 직렬화하지 않으며 두 필드는 각각 `completion_capability_identity_serialized=false`, `device_pointer_values_serialized=false`로 고정된다.

세 host staging array가 모두 채워지면 각 payload를 Python `bytes`로 detach한다. Publication 검증 후에는 final result를 공개하기 전 staging reference를 즉시 해제하여 대형 `F`에서 동일 host payload를 context `close()`까지 이중 보유하지 않는다. Telemetry의 `host_staging_allocation_count=3`은 성공 경로의 이력 accounting이지 현재 보유 개수가 아니다. Result의 `solution_x_array`, `true_residual_array`, `solve_record_array`는 detached bytes를 base로 하는 C-contiguous, read-only NumPy view다. Result와 receipt dataclass는 frozen이며, caller가 payload를 변조한 result는 validator에서 거부된다.

각 buffer descriptor는 `source_lineage_hash` 및 개별 `payload_sha256`를 갖는다. Bundle `payload_hash`는 contract domain, role, role-name length, payload length·bytes를 고정 순서로 hash하여 role swap과 concatenation ambiguity를 차단한다. Receipt `receipt_hash`는 payload bytes 자체 대신 descriptor/hash/telemetry/claims를 포함한 canonical receipt payload에 결속된다.

Receipt status는 다음 다섯 개만 허용한다.

```text
context_ready, exported, poisoned, context_closed, cleanup_failed
```

Standalone validator는 exact Python type, Draft 2020-12 schema, receipt/payload hash와 내부 semantic consistency를 검증한다. Canonical hash는 서명이 아니므로 process-local provenance에는 `expected_context` 검증이 필요하고, 장기 보관·외부 전달의 진본성은 향후 signed chain의 범위다.

Downstream [terminal-outcome observer v1](engine-v2-hip-fgmres-terminal-outcome-observation-v1.md)을 위해 exporter는 public raw receipt와 그 hash를 바꾸지 않는 private final-publication seal을 유지한다. Seal은 exact final result/receipt/세 payload identity와 hash, parent에서 publication 직전에 다시 검증한 recurrence policy를 단일 state로 결속한다. Intermediate publication이나 local policy mutation은 observer authority가 아니며, seal publication interruption은 동일 result로 monotonic retry된다. 이 private seal은 exporter가 solve record를 해석했다는 claim을 추가하지 않는다.

## Operation·telemetry 계약

정상 `exported` receipt의 exact accounting은 다음과 같다.

```text
completion capability reservation              1
completion capability consumption              1
host staging allocations                       3
blocking D2H attempts / successes              3 / 3
blocking copy completions                       3
D2H bytes attempted / succeeded                B / B
  B = 16F + 192 + 72R
device allocation / allocation borrow          0 / 0
H2D / kernel launch                            0 / 0
explicit stream synchronization / fallback     0 / 0
numerical-content host branch                  0
```

각 D2H attempt와 attempted bytes는 runtime call 전에, success/completion과 succeeded bytes는 blocking call이 정상 반환한 뒤에만 증가한다. Copy `k`에서 실패하면 attempted prefix는 `1..k`, success/completion prefix는 `1..k-1`을 보존하고 부분 payload는 publish하지 않는다.

Global recurrence receipt는 export 전에 이미 고정되었으며 export 후에도 변하지 않는다. Global owner의 `d2h_operation_count=0`/`no_h2d_or_d2h_copy=true`는 suffix-owner 범위에 남고, completion export의 D2H 3회는 신규 export receipt에만 계산된다. 두 receipt를 합쳐 global iteration host-copy-zero 증거로 재분류하지 않는다.

Actual AMD HIP gate는 gfx1030에서 `F=6`, `R=1`, `I=1`로 실행했다. Required hardware test는 `1 passed in 35.37s`를 기록했고, 고정 순서의 blocking D2H `3`회·정확히 `360` bytes, export owner 범위의 추가 device allocation/H2D/async D2H/runtime sync/checkpoint fence `0`을 확인했다. 동일 테스트의 CPU 비교는 test-only oracle이며 model-family parity나 promotion 증거가 아니다.

## Claim boundary

`exported`에서 true인 범위는 다음으로 한정된다.

- exact fenced global completion과 single-use completion consumption이 bound됨
- exact three source lineage의 raw bytes가 고정 순서로 host materialize됨
- 세 D2H가 blocking call으로 완료되고 async pending work가 남지 않음
- detached bytes, individual payload hash, bundle hash와 canonical receipt hash가 일치함
- export owner 범위의 device allocation/borrow, H2D, kernel launch, explicit stream synchronization, fallback과 numerical-content branch가 0임

다음 claim은 payload가 성공적으로 export되어도 계속 false다.

- `solve_record_semantics_interpreted`
- `actual_terminal_outcome_host_observed`
- `authoritative_terminal_status_proven`
- `numerical_parity_verified`
- `solution_ready`
- `result_ir_ready`
- `iteration_host_copy_zero_proven`
- `performance_or_speedup_proven`; 일반 `N`-DOF O(N), kernel/solver end-to-end speedup 및 기타 performance claim
- `commercial_ready`
- `promotion_eligible`

특히 opaque `solve_record` bytes가 존재한다는 사실은 status/code/active/error/counter/metric이 해석·검증되었다는 뜻이 아니다. `solution_x`와 `true_residual`도 terminal status, finite/invariant 및 CPU/HIP oracle parity와 결합되기 전에는 authoritative numerical result가 아니다. 이 contract은 completion bytes export만 닫으며 ResultIR, 상용 solver 완성도 또는 release promotion으로 승격하지 않는다.

## 다음 단계


Explicit terminal-outcome observation은 [별도 v1 contract](engine-v2-hip-fgmres-terminal-outcome-observation-v1.md)로 구현되었다. Observer는 본 raw-export receipt의 outcome-free claim을 소급 변경하지 않고 별도 receipt에서 terminal record 의미를 고정한다.

다음 우선순위는 model-family·multi-architecture CPU/HIP full parity이다. ResultIR integration과 iteration host-copy-zero는 그 후에도 각각 독립 gate로 검증해야 한다.
