# Engine v2 HIP Krylov primitives v1

- 상태: 구현된 primitive 계약, unsigned·non-promoting
- capability profile: `phase0_hip_krylov_vector_reduction_positive_jacobi_primitives`
- 범위: free-space device vector를 사용하는 same-stream affine, positive Jacobi, deterministic dot, stable L2 primitive 수직 슬라이스
- 기준 문서: [Structural Solver Engine v2 마스터 로드맵](structural-solver-engine-v2-master-roadmap.md)

이 v1은 Krylov **해법기**가 아니다. 장치 상주 벡터 연산과 reduction에 필요한 가장 작은 고정 프로그램을 구현하고, 그 프로그램의 소유권·전송·fence·오류·영수증 경계를 검증한다. CG/FGMRES/PCG recurrence, SPD 증명, 통합 preconditioner, solver iteration은 아직 없다.

## 소유권 계층과 open 전제

Primitive context는 free-space context의 exclusive grandchild다.

```text
assembly context
  └─ resident CSR context
       └─ free-space context
            └─ Krylov primitives context
```

`open_hip_krylov_primitives_execution_context()`는 다음 입력만 받는다.

1. exact `HipFreeSpaceExecutionContext`
2. 그 context가 가장 최근에 성공적으로 enqueue한 exact `HipFreeSpaceApplyReceipt`

Source apply는 `status=enqueued`여야 하며 receipt object, hash, sequence, device-direction generation과 parent 내부 witness가 모두 일치해야 한다. Stale receipt, 재해시한 복제 receipt, 다른 context의 receipt는 거부한다.

Open은 free-space의 `_acquire_krylov_consumer_for_apply()`로 source apply가 exact latest object·generation·witness인지 다시 확인하는 것과 grandchild lease 획득을 하나의 parent queue-lock 원자구간에서 수행한다. 따라서 preflight 뒤 다른 apply가 끼어들어 오래된 generation과 새 device buffer 상태가 분리될 수 없다. Lease가 살아 있는 동안 free-space의 새 operator apply, verification, 다른 primitive child 획득과 close는 work 제출 전에 차단된다. 그 결과 resident와 assembly의 상위 lease도 유지된다. Primitive context는 새 stream을 만들지 않고 parent의 exact runtime과 stream을 그대로 사용한다.

## 장치 버퍼

기호는 다음과 같다.

```text
F = free_dof_count
P = max(1, ceil(F / 512))
```

### Borrowed 5

Primitive context는 free-space가 소유한 다음 pointer를 빌리며 해제하지 않는다.

| 버퍼 | 형태 | 역할 |
|---|---:|---|
| `reduced_csr_row_ptr` | `<i4>[F+1]` | `K_ff` CSR row |
| `reduced_csr_column_indices` | `<i4>[nnz_ff]` | `K_ff` CSR column |
| `reduced_csr_values` | `<f8>[nnz_ff]` | device-materialized `K_ff` 값 |
| `reduced_direction` | `<f8>[F]` | source apply가 만든 `r = F_f-K_ffu_f` |
| `reduced_jvp` | `<f8>[F]` | source apply가 만든 `K_ff r` |

### Owned 9

| 버퍼 | 형태 | 역할 |
|---|---:|---|
| `jacobi_inverse` | `<f8>[F]` | positive diagonal의 역수 |
| `work_x` | `<f8>[F]` | 첫 affine 결과 |
| `work_y` | `<f8>[F]` | fill 및 alias-safe affine 결과 |
| `preconditioned` | `<f8>[F]` | `D⁻¹r` 진단 벡터 |
| `reduction_ping` | `<f8>[2P]` | dot partial 또는 LASSQ pair ping |
| `reduction_pong` | `<f8>[2P]` | 다단계 LASSQ/dot reduction pong |
| `dot_result` | `<f8>[1]` | `rᵀD⁻¹r` 진단 scalar |
| `norm_result` | `<f8>[1]` | stable L2 진단 scalar |
| `error_flag` | `<i4>[1]` | device error bit 집계 |

`2P` reduction buffer는 dot에서 앞쪽 scalar partial 영역으로, LASSQ에서 `(scale, ssq)` pair 영역으로 재사용된다. Open 중 host에서 올리는 것은 zeroed `error_flag` 4 byte 한 번뿐이다. Vector, CSR numeric, reduction partial은 host에서 업로드하지 않는다.

## Positive unshifted Jacobi

Open의 package-owned `prepare_positive_jacobi` kernel은 각 reduced CSR row에서 diagonal entry가 정확히 하나인지 확인하고 다음 조건을 모두 만족할 때만 역수를 쓴다.

- row/column 구조가 유효하다.
- diagonal이 finite다.
- diagonal이 엄격히 `> 0.0`이다.
- reciprocal도 finite이고 엄격히 양수다.

다음 보정은 존재하지 않는다.

- diagonal clamp
- diagonal shift
- absolute-value 치환
- epsilon 대체
- 누락 diagonal 삽입

Device가 `JACOBI_DIAGONAL` bit만 보고한 경우에도 즉시 정상 unsupported로 간주하지 않는다. Immutable CPU `ExecutionPlanV2`에서 diagonal을 다시 도출한다.

- CPU plan에도 diagonal 누락 또는 nonpositive diagonal이 있으면 `positive_jacobi_unsupported`로 clean cleanup하며 parent를 poison하지 않는다.
- CPU plan은 positive인데 device만 거부하면 device numeric mismatch/corruption으로 보고 전체 owner chain을 poison한다.
- nonfinite, CSR corruption, arithmetic overflow 또는 복합 error bit는 fail-closed하고 공유 poison한다.

Positive diagonal은 이 고정 Jacobi primitive가 계산 가능하다는 뜻뿐이다. 행렬의 대칭성이나 양의 정부호성을 증명하지 않으며 PCG admissibility 증거가 아니다.

## 고정 raw batch

`enqueue_primitive_batch()`는 caller가 임의 프로그램을 구성하는 API가 아니다. 항상 같은 stream에서 다음 프로그램을 같은 순서로 enqueue한다.

```text
r   = borrowed reduced_direction
jvp = borrowed reduced_jvp

work_y = 0.25
work_x = -0.5*r + 0.0*r
work_y = 0.25*jvp + 1.0*work_y
z      = jacobi_inverse * r
dot    = deterministic_tree(r * z)
norm   = lassq_finalize(deterministic_tree(lassq(r)))
```

두 번째 affine은 `output == y == work_y`인 exact per-index alias를 의도적으로 사용한다. Kernel은 입력 값을 먼저 읽은 뒤 같은 index에 출력하므로 이 exact alias는 지원된다.

Reduction은 512개 값당 하나의 partial을 만드는 고정 segment와 block size 256을 사용한다. `P=1`이어도 dot `sum_stage`와 LASSQ `combine_stage`를 각각 최소 한 번 실행한다. `P>1`이면 `reduction_output_count()`가 1이 될 때까지 ping/pong tree를 반복하며 receipt는 계획된 stage 수와 각 attempt/success prefix를 정확히 결박한다.

Reduction input과 output의 임의 overlap은 지원하지 않는다. 특히 byte-offset이 다른 **shifted partial alias**는 금지하며 correctness claim이 없다. Context 프로그램은 distinct ping/pong/result buffer를 선택해 이 경계를 지킨다. Affine의 exact same-index alias 지원을 reduction alias 지원으로 일반화하면 안 된다.

### Dot의 수치 경계

Dot은 fixed tree이고 numerical `atomicAdd`를 사용하지 않는다. 각 product와 중간 sum이 finite인지 확인하며 overflow가 발생하면 `ARITHMETIC_OVERFLOW` bit를 기록하고 결과를 성공으로 승격하지 않는다.

이 동작은 fail-closed overflow **검출**이다. 다음 주장은 하지 않는다.

- compensated summation
- scaled dot product
- arbitrary-magnitude overflow-resistant summation
- exact 또는 correctly rounded dot

즉 중간 tree overflow를 숨기지는 않지만, overflow를 피하도록 합산법을 바꾸는 primitive도 아니다.

### LASSQ의 수치 경계

L2 norm은 `(scale, ssq)`를 결합하는 scale-first LASSQ를 사용한다. Pair는 finite `scale`, `ssq >= 1`, zero-pair canonical form을 검사하며 invalid pair와 arithmetic overflow를 error bit로 남긴다. 이것은 dot의 합산 성질을 바꾸지 않는 별도의 stable norm primitive다.

## 전송과 fence 경계

### Open

성공한 open은 다음 순서를 따른다.

1. exact parent/source-apply preflight
2. exclusive free-space grandchild lease 획득
3. package-owned HIPRTC module compile/load 또는 caller test kernel 결박
4. owned 9개 allocation
5. `error_flag=0`만 H2D 1회, 4 byte
6. positive Jacobi preparation enqueue
7. `error_flag` D2H 1회, 4 byte
8. same-stream fence 1회
9. RTC module에 그 exact stream의 completion을 acknowledge
10. device error와 trusted CPU diagonal을 검사한 뒤 `context_ready`

### Raw batch

성공한 raw batch의 호출 구간은 다음과 같이 고정된다.

| 항목 | 값 |
|---|---:|
| H2D | 0 |
| D2H | 0 |
| device allocation | 0 |
| sync/fence | 0 |
| fallback | 0 |

Raw receipt의 `status=enqueued`는 queue 제출만 뜻한다. `completion_fence_observed=false`, `solver_iteration=false`, `pcg_iteration=false`다. Error flag 결과도 이후 실제 fence 전에는 완료로 주장하지 않는다.

### Explicit verification

`evaluate_for_verification()`은 매번 새 raw batch를 먼저 enqueue하고 다음 7개 D2H operation을 수행한다.

1. `jacobi_inverse`
2. `work_x`
3. `work_y`
4. `preconditioned`
5. `dot_result`
6. `norm_result`
7. `error_flag`

총 D2H byte 식은 `32F + 20`이고, 마지막에 같은 stream fence를 정확히 한 번 수행한 뒤 RTC completion을 acknowledge한다. Evaluation 구간의 H2D, allocation, fallback은 0이다.

CPU oracle은 fence와 error-flag 검사가 성공한 뒤에만 실행한다. Source `ExecutionPlanV2`에서 `K_ff` diagonal, full residual로부터의 `r`, reduced `K_ff r`, fixed affine 식, `D⁻¹r`, dot과 scale-first norm을 독립적으로 다시 계산한다. 다음 6개 metric을 absolute/relative tolerance `1e-8`로 비교한다.

- `jacobi_inverse`
- `work_x`
- `work_y`
- `preconditioned`
- `dot_result`
- `norm_result`

CPU 계산은 검증 oracle이며 GPU 계산의 fallback이나 대체 실행 경로가 아니다. 성공/parity-failed evaluation의 strong validator는 exact live context를 필수로 받고 CPU expected와 parity를 다시 계산하므로, array descriptor·receipt·parity 숫자를 함께 재해시한 forgery도 거부한다. Live context가 없는 경우 receipt의 schema/hash 구조 검사는 가능하지만 successful evaluation의 수치적 진실 검증은 명시적으로 거부한다.

## RTC completion-fence acknowledgement

`HipRtcKrylovPrimitivesKernel`은 성공했거나 결과가 모호한 launch의 stream을 pending으로 기록한다. 외부 context가 실제 `synchronize(stream)` 또는 동등한 completion event를 관찰한 뒤에만 `acknowledge_stream_completion(stream)`을 호출할 수 있다.

- 다른 stream의 fence로 pending stream을 지울 수 없다.
- pending 기록이 없는 stream acknowledgement는 contract error다.
- pending stream이 남은 상태에서 module close는 `completion_fence_required`로 거부된다.
- raw batch receipt 자체는 acknowledgement가 아니다.

Context는 open fence, verification fence, close fence와 open-failure cleanup fence 직후에만 acknowledgement를 수행한다. Synchronize 성공과 acknowledgement 성공은 별도 상태로 계측한다. Fence 뒤 acknowledgement가 실패하면 raw 예외로 owner를 잃지 않고 `cleanup_failed` context가 buffer·module·lease를 보존해 재시도한다. 이 규칙은 code object를 참조하는 device work가 끝나기 전에 HIPRTC module이 unload되는 것을 방지한다.

## Receipt와 authority 경계

Context v2와 batch/evaluation v1의 세 Draft 2020-12 receipt는 canonical hash, exact Python container/scalar type, semantic validator를 함께 사용한다.

### Context receipt

다음을 결박한다.

- parent context ID와 opening receipt hash
- source apply ID/hash/sequence/device generation
- execution plan, operator, numeric snapshot, partition hash
- state hash와 epoch
- grandchild lease epoch와 parent 5-capability all-or-none group borrow
- internally-compiled/caller-supplied kernel origin
- architecture, 9 fixed symbols, launch geometry, source/code-object/library hash
- 9 owner-minted buffer descriptor, lineage count/byte와 allocation/deallocation·quarantine·unknown-outcome·module lifecycle telemetry

### Batch receipt

Fixed stage별 attempt/success, planned dot sum stage 수, planned LASSQ combine stage 수와 실패 prefix를 결박한다. 실패한 stage 이후 downstream stage가 enqueue된 것처럼 재해시하면 거부한다. Live-context validation에서는 sequence witness가 반드시 존재하고 receipt hash와 일치해야 하며, 단순히 미등록 sequence를 재해시한 receipt는 거부한다. 성공 receipt는 fill, affine 2회, Jacobi, dot tree, LASSQ tree/finalize가 모두 정확히 완료 제출된 경우에만 `enqueued`다.

### Evaluation receipt

Nested batch, 6개 FP64 export descriptor/hash, `7 D2H + 1 fence` telemetry, metric count와 parity를 결박한다. `execution_id`는 context/opening/batch receipt hash에서 재도출하며 임의 hash로 바꿀 수 없다. Receipt에는 pointer, stream, module, function 또는 device address를 직렬화하지 않는다. 모든 receipt는 `promotion_eligible=false`다.

세 schema는 telemetry/delta/claims를 임의 `patternProperties`가 아닌 exact property 집합으로 정의한다. Evaluation schema는 nested batch, six-array descriptor, six parity metric을 local `$defs`로 완전히 정의하고 `verified`/`parity_failed`/`unavailable`별 reason·array·parity 조건을 강제한다. 따라서 Python semantic validator를 호출하지 않는 schema-only 소비자도 빈 batch/parity/arrays, extra snake-case field, 완료 claim과 status의 모순을 수용하지 않는다.

## Poison과 retryable cleanup

다음 오류는 primitive context에서 시작해 free-space→resident→assembly owner chain에 공유 poison된다.

- runtime/stream/parent/source receipt authority 변경
- owned 또는 borrowed pointer identity 변경
- kernel identity/owner 변경
- raw stage launch 실패 또는 결과가 모호한 queue 실패
- verification copy/fence 실패
- device nonfinite, CSR corruption, invalid LASSQ pair, arithmetic overflow
- trusted CPU plan과 device Jacobi 결과 불일치
- device export와 trusted CPU oracle의 수치 parity 불일치

반면 queue를 건드리기 전 compile, binding, memory-budget, allocation 실패는 parent를 poison하지 않는다. Trusted plan에도 존재하는 missing/nonpositive diagonal은 clean unsupported다. 수치 parity mismatch는 진단 가능한 `parity_failed` receipt를 먼저 완성한 뒤 전체 owner chain을 poison해 같은 primitive context의 후속 batch 재사용을 금지한다.

Close 순서는 다음과 같다.

```text
same-stream fence
  -> exact stream completion acknowledgement
  -> orphan/owned 9 allocation lineage retirement
  -> peer allocation owner close
  -> HIPRTC module close with persistent disposition
  -> parent 5-capability group-borrow release
  -> free-space grandchild semantic lease release
```

Free, module close 또는 lease release가 실패하면 `cleanup_failed` context가 남은 resource ownership을 유지한다. `close()` 재시도는 이미 회수한 resource를 다시 해제하지 않고 남은 단계부터 계속한다. Internal RTC compile 중 symbol/load cleanup이 module unload에 실패해도 module-only cleanup owner를 잃지 않고 context cleanup 경로로 넘긴다.

## Native evidence와 hardware gate

`evidence_scope=native_hiprtc_krylov_primitives_composite`는 다음 조건이 모두 참일 때만 생성된다.

1. Primitive kernel을 context가 package-owned source에서 내부 compile했다.
2. Parent free-space context가 `native_hiprtc_free_space_composite`다.
3. Loaded HIP runtime과 primitive kernel이 exact native 구현 type이다.
4. Primitive와 parent architecture가 같다.
5. Runtime library SHA-256이 parent와 같다.
6. Runtime/HIPRTC discovery source가 `injected`가 아니다.

Caller-supplied kernel은 identity 값을 동일하게 흉내 내도 항상 `injected_test_double`이다.

`tests/test_engine_v2_hip_krylov_primitives_hardware_v1.py`는 gfx agent와 native HIP capability가 있을 때 다음 실제 device chain을 실행한다.

```text
assembly
  -> resident CSR
  -> free-space device apply
  -> internally compiled Krylov primitives open
  -> raw fixed batch
  -> 7-D2H verification + CPU parity
  -> primitive/free-space/resident/assembly reverse cleanup
```

일반 실행에서 gfx agent나 native capability가 없으면 명시적으로 skip하고 CPU fallback을 사용하지 않는다. `ENGINE_V2_REQUIRE_HIP_HARDWARE=1` 또는 `ENGINE_V2_REQUIRE_HIP_KRYLOV_PRIMITIVES_HARDWARE=1`이면 같은 미지원·실패 조건은 skip이 아니라 failure다. Cleanup 실패는 어떤 모드에서도 skip으로 바뀌지 않는다.

현재 native hardware smoke fixture는 `P <= 512` 범위다. `P > 512`, 즉 512-value first-stage partial이 513개 이상 필요한 `F > 262,144` free DOF의 다단계 reduction은 contract/unit adversarial test로 stage 수와 receipt를 검증했지만 실제 native device 실행은 아직 없다.

## 명시적 claim 경계

| 항목 | v1 상태 | 의미 |
|---|---|---|
| positive unshifted Jacobi 준비 | 구현 | exactly-one finite positive diagonal만 역수화, shift/clamp 없음 |
| affine primitive | 구현 | fixed FP64 affine와 exact same-index input/output alias |
| deterministic dot tree | 구현 | 512-value segment, fixed tree, intermediate overflow fail-closed |
| stable L2 | 구현 | scale-first LASSQ pair tree |
| raw batch transfer/allocation/sync/fallback 0 | 구현된 호출 경계 | 한 fixed batch의 telemetry delta에 한정 |
| CG recurrence | **false** | `alpha`, `beta`, residual update, convergence state machine 없음 |
| FGMRES recurrence | **false** | Arnoldi basis, orthogonalization, restart 없음 |
| PCG recurrence/readiness | **false** | SPD gate와 preconditioned recurrence 없음 |
| SPD proof | **false** | positive diagonal은 SPD 증거가 아님 |
| integrated preconditioner | **false** | Jacobi 결과를 solver recurrence에 연결하지 않음 |
| solver iteration | **false** | primitive diagnostic batch만 존재 |
| iteration host-copy-zero | **false** | iteration이 없고 verification은 D2H 7회 |
| end-to-end `O(N)` | **false** | primitive kernel 구조로 전체 solver complexity를 증명하지 않음 |
| speedup | **false** | 모델 크기 family, CPU baseline, timing 통계 없음 |
| commercial readiness | **false** | solver/V&V/release/promotion 증거 없음 |

`host_copy_zero_proven`, `spd_proven`, `pcg_ready`, `krylov_solver_ready`, `preconditioner_integrated`, `solver_iteration_ready`, `asymptotic_o_n_proven`, `speedup_proven`, `commercial_ready`는 context claim에서 모두 exact `false`다.

## 구현·검증 파일

2026-07-12 v0.2.18의 allocation-lineage 통합 수치와 해시는 [통합 계약](engine-v2-hip-free-space-krylov-allocation-lineage-v1.md) 및 [마스터 로드맵 변경 기록](structural-solver-engine-v2-master-roadmap.md)에 고정한다. 조건부 hardware gate는 장치 미노출 시 명시적으로 skip하며 CPU fallback을 사용하지 않는다.

- context/receipt/verification: `src/structural_analysis/engine_v2/assembly_backend/krylov_primitives.py`
- fixed HIPRTC owner/ABI: `src/structural_analysis/engine_v2/assembly_backend/krylov_primitives_rtc.py`
- package-owned HIP source: `src/structural_analysis/engine_v2/assembly_backend/kernels/engine_v2_krylov_primitives_v1.hip.cpp`
- context schema: `src/structural_analysis/schemas/hip_krylov_primitives_context_v2.schema.json`
- batch schema: `src/structural_analysis/schemas/hip_krylov_primitives_batch_v1.schema.json`
- evaluation schema: `src/structural_analysis/schemas/hip_krylov_primitives_evaluation_v1.schema.json`
- RTC ABI/source/lifetime test: `tests/test_engine_v2_hip_krylov_primitives_rtc_v1.py`
- context/lifetime/receipt/parity test: `tests/test_engine_v2_hip_krylov_primitives_context_v1.py`
- allocation-lineage 통합·receipt 보존 test: `tests/test_engine_v2_hip_krylov_allocation_lineage_integration_v1.py`
- schema-only nested/status/extra-field forgery test: `tests/test_engine_v2_hip_krylov_primitives_schema_v1.py`
- package re-export test: `tests/test_engine_v2_hip_krylov_primitives_public_api_v1.py`
- conditional native gate: `tests/test_engine_v2_hip_krylov_primitives_hardware_v1.py`

Fixed ABI는 FP64 value, int32 CSR/error, block size 256, reduction segment 512를 사용하며 module symbol은 다음 9개다.

- `prepare_positive_jacobi`
- `fill`
- `affine`
- `apply_jacobi`
- `dot_stage`
- `sum_stage`
- `lassq_stage`
- `lassq_combine_stage`
- `lassq_finalize`
