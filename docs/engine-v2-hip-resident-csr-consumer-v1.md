# Engine v2 HIP assembly-resident CSR residual/JVP consumer v1

- Status: implemented contract, unsigned and non-promoting
- Scope: assembly-owned full-DOF frame/truss CSR의 same-runtime/device/stream residual/JVP 소비
- Authority: [Structural Solver Engine v2 마스터 로드맵](structural-solver-engine-v2-master-roadmap.md)
- Claim boundary: test-double에서 조립 CSR을 재할당·재업로드하지 않는 소비 계약과 full/free/constrained FP64 replay를 검증했다. 현재 환경에서는 native assembly→resident residual/JVP hardware launch가 실행되지 않았다. Device Krylov, iteration host-copy 0, solver, O(N), speedup 또는 상용 준비도 증거가 아니다.

## 결과

기존 `HipRtcCsrExecutionContext`는 CPU에서 조립한 CSR row/column/value를 별도 context와 stream에 다시 적재한다. 이 v1은 그 경로를 재사용하지 않는다. 대신 live `HipAssemblyExecutionContext`가 process-local 독점 lease를 발급하고 consumer가 다음 네 장치 버퍼를 빌린다.

- assembly child: `csr_row_ptr`, `csr_column_indices`, `csr_values`
- foundation ModelBuffer: `load_vector_si`

Consumer가 소유하는 장치 버퍼는 다음 네 개뿐이다.

- committed `state_displacement`
- `direction_workspace`
- `residual_workspace`
- `jvp_workspace`

Open 시 H2D는 committed state 한 번뿐이다. Consumer 단계의 CSR symbolic/numeric H2D와 load H2D는 모두 0이고 새 stream 생성도 0이다. `ExecutionPlanV2.global_load`와 foundation `load_vector_si`의 shape, dtype, 값과 hash가 acquire 전 일치해야 한다.

## 수명과 동시성

Parent assembly context는 monotonic lease epoch와 opaque token을 발급한다. Parent-level `RLock`이 acquire/release/poison/close를 하나의 임계구역으로 보호하므로 두 thread가 동시에 lease를 얻을 수 없다. Active consumer가 있으면 parent close는 sync/free 전에 원자적으로 거부된다.

Consumer도 process-local serial lock으로 enqueue, verification, close를 직렬화한다. acquire 시 다음 identity를 snapshot하고 각 enqueue에서 O(1)으로 재검사한다.

- parent runtime 객체
- device ordinal
- parent stream 객체
- foundation owner 객체
- borrowed CSR/load pointer 객체 네 개
- loaded residual kernel과 identity 객체

Native exact kernel의 hot path는 파일 또는 shared-library hash를 다시 읽지 않는다. Caller-supplied kernel은 exact native type처럼 보여도 항상 `injected_test_double`이고, native composite 표시는 parent와 residual kernel이 모두 내부에서 획득되고 architecture/runtime-library identity가 연결될 때만 생성된다.

Caller-supplied kernel은 parent lease를 얻기 전에 `launch_residual_jvp()`/`close()`가 호출 가능하고 아직 닫히지 않았는지 검사한다. 따라서 회수 불가능하거나 이미 닫힌 kernel이 parent lease를 영구 점유할 수 없다. Mutable telemetry를 읽는 `receipt()`도 같은 serial lock 안에서 snapshot하므로 concurrent close 도중의 부분 해제 상태를 ready receipt로 관찰하지 않는다.

## 두 실행 경로

### Device enqueue primitive

`enqueue_residual_jvp()`는 이미 생성된 device direction workspace를 소비해 `R=Ku-F`, `Jv=Kv`를 한 번 enqueue한다. 이 호출 자체의 계약은 다음과 같다.

- H2D/D2H: 0
- allocation: 0
- sync/fence: 0
- fallback: 0
- kernel launch attempt: 1
- completion claim: false, enqueue claim만 true

미초기화 device memory를 읽지 않도록 direction producer generation이 0이면 fail-closed한다. Resident 단독 public API의 producer는 아래 verification upload뿐이다. 별도 [free-space device-direction child](engine-v2-hip-free-space-operator-v1.md)가 same-stream producer와 single-use generation을 연결하지만 Krylov vector recurrence나 convergence loop는 아직 없으므로, zero-transfer enqueue를 device-resident Krylov 준비 완료로 해석하면 안 된다.

### Host verification wrapper

`evaluate_for_verification(direction)`은 검증 전용 경로다.

1. host direction H2D 1회
2. same-stream fused enqueue 1회
3. residual/JVP D2H 2회
4. same-stream fence 1회
5. 성공한 fence 뒤에만 CPU `ExecutionPlanV2` oracle replay

Residual/JVP는 full/free/constrained partition별 절대·상대·scaled error로 검증한다. Metric은 global scale로 정규화해 극대 finite 입력의 raw norm/subtraction overflow를 피한다. Verification 경로에는 full-vector host copy가 있으므로 iteration host-copy 0 증거가 아니다.

## 오류·cleanup 계약

- H2D, launch, D2H, fence, nonfinite, parity 또는 live-authority 실패는 consumer와 parent serial queue를 함께 poison 처리한다.
- CPU oracle은 device launch, 두 output export와 fence가 모두 성공한 뒤에만 호출하며 fallback으로 사용하지 않는다.
- Close 순서는 fence → owned four buffers reverse free → residual module close → parent lease release다.
- Borrowed CSR/load는 consumer가 free하지 않는다.
- Open 또는 close 중 fence/free/module/release 실패 시 남은 pointer, kernel과 parent owner를 cleanup-only context가 계속 소유한다. `close()` 재시도는 남은 resource만 회수한다.
- Runtime pointer, address, stream, handle, module 또는 function 값은 receipt, manifest, repr와 오류 detail에 직렬화하지 않는다.
- `context_ready`와 `poisoned`는 네 vector의 완전한 live ownership과 teardown 0회를, `cleanup_failed`는 실제 미회수 resource를, `context_closed`/`unavailable`은 완전한 deallocation·module close·lease release를 각각 강제한다.

## Receipt 체인

세 Draft 2020-12 schema를 사용한다.

- `hip_resident_csr_context_v1.schema.json`
- `hip_resident_csr_enqueue_v1.schema.json`
- `hip_resident_csr_evaluation_v1.schema.json`

Context receipt는 parent opening/evaluation/operator metadata, 두 kernel identity, plan/operator/numeric/partition hash, state epoch/hash, load source, lease epoch 및 kernel origin을 결박한다. Evaluation receipt는 전체 enqueue receipt를 중첩해 enqueue ID, sequence, kernel identity, telemetry와 execution ID를 standalone으로 재검산한다. 모든 receipt는 unsigned이며 `promotion_eligible=false`다.

Context와 evaluation telemetry는 operation count와 `8 × global_dof_count` vector byte 수를 정확히 결속한다. Verification 상태기계는 H2D 최대 1회, D2H 최대 2회, sync 최대 1회와 `H2D → enqueue → D2H×2 → fence` prefix 순서를 강제한다. Descriptor shape/bytes, full/free/constrained metric count, metric pass 기준, aggregate parity, live nested-enqueue sequence/kernel identity 및 status별 backend 값도 semantic validator가 재검산한다.

Standalone canonical rehash는 내부 모순과 변조를 탐지하지만 provenance를 인증하지 못한다. Native promotion은 live expected-context 재검증과 별도의 trusted-runner signature/attestation envelope가 모두 생기기 전까지 금지한다.

## 검증

2026-07-11 기준 resident/parent-lifetime/capability 집중 suite 결과는 `127 passed, 1 skipped`다. Free-space와 Krylov-primitives downstream을 포함한 전체 Engine v2·ModelIR v2·MGT v2 focused 회귀는 `708 passed, 7 skipped`, 기존 v1 core/MGT parser 호환 회귀는 `33 passed`다.

- borrowed CSR/load pointer와 모든 copy/launch/fence의 parent stream identity
- consumer CSR/load allocation·H2D 0, owned allocation 4, state H2D 1
- enqueue transfer/allocation/fence 0 및 monotonic sequence
- full/free/constrained residual/JVP FP64 parity
- direction H2D, launch, D2H #1/#2, fence 실패별 exact attempt/success delta
- 실패 시 CPU oracle 미호출, fallback 0, consumer/parent poison
- 네 allocation cut point, partial free, module close, cleanup fence의 retry ownership
- two-thread exclusive parent lease, stale epoch 및 parent-close-with-child 거부
- live kernel identity, borrowed pointer, runtime/stream authority mutation 거부
- rehashed nested receipt, bool/int confusion, broad claim, runtime-handle forgery 거부
- caller kernel pre-lease reclaimability, concurrent receipt/close snapshot, ready/poisoned/cleanup/closed ownership 상태기계
- operation↔byte exact식, evaluation stage prefix, descriptor/partition/parity aggregate 및 backend exactness 위조 거부
- native hardware gate: 현재 gfx device 미노출로 skip, CPU 대체 실행 없음

일반 로컬 실행은 gfx agent가 없을 때 명시적으로 skip한다. Authoritative hardware lane은 `ENGINE_V2_REQUIRE_HIP_HARDWARE=1`로 실행하며, 이때 device discovery, capability, assembly open, resident open, parity 또는 cleanup 실패는 skip이 아니라 test failure다.

## 다음 gate

Device-resident Krylov로 넘어가려면 다음이 추가로 필요하다.

별도 free-space v1이 device direction producer generation과 reduced CSR/gather 수직 슬라이스를 추가했고, 후속 [Krylov primitive v1](engine-v2-hip-krylov-primitives-v1.md)이 same-stream affine·Jacobi·dot·LASSQ와 raw-batch zero-transfer 계약을 추가했다. 남은 gate는 다음과 같다.

1. device convergence scalar 정책과 recurrence state lifecycle
2. solver에 실제 결합된 preconditioner/AMG 또는 DD hierarchy
3. fixed-restart FGMRES 및 SPD-gated PCG 상태기계
4. Krylov iteration당 state/residual full-vector host copy 0 계측
5. 실제 AMD GPU assembly→consumer→Krylov native parity와 다중 크기 scaling

따라서 이 v1의 정확한 결론은 **장치에서 조립된 full CSR을 host CSR 재업로드 없이 같은 HIP queue에서 residual/JVP 커널이 소비하는 수명·telemetry·receipt 계약이 구현됐다**는 것이다.
