# Engine v2 HIP fixed-restart FGMRES plan v1

- 상태: 구현된 compile-time allocation/policy contract, unsigned·non-promoting
- capability profile: `phase0_hip_fixed_restart_fgmres_allocation_and_policy_plan`
- 범위: 향후 same-stream HIP FGMRES child의 source, policy, buffer extent와 runtime lineage 요구사항
- 수치 기준: [CPU fixed-restart FGMRES reference v1](engine-v2-cpu-fgmres-reference-v1.md)
- 기준 문서: [Structural Solver Engine v2 마스터 로드맵](structural-solver-engine-v2-master-roadmap.md)

이 계획은 solver context, device allocation, HIPRTC module, recurrence 실행 또는 수렴 receipt가 아니다. 실제 장치 work를 시작하기 전에 고정해야 할 source/policy/memory ABI를 별도 artifact로 만든다. 후속 recurrence v2와 [live checkpoint resource context v1](engine-v2-hip-fgmres-live-checkpoint-context-v1.md)이 일부 runtime 자원을 구현했지만 이 v1 plan artifact의 compile-time claim은 바꾸지 않는다.

## Source와 policy 결속

`compile_hip_fgmres_plan_v1()`은 exact `ExecutionPlanV2`, 그 plan에서 도출한 exact `HipFreeSpaceOperatorPlanV1`, 선택적인 `FgmresPolicyV1`을 받는다. artifact는 다음을 hash로 결박한다.

- execution plan schema/profile/id/hash
- operator, numeric snapshot, symbolic reuse, partition
- ModelIR content, solver artifact, load pattern
- authoritative scaled-L∞ residual tolerance
- free-space plan/view hash
- positive Jacobi diagonal과 finite positive inverse의 raw-byte hash
- fixed-restart FGMRES policy hash
- exact buffer order, extent와 memory-layout hash

Compile 중 source plan과 free-space overlay를 독립 재검증하고 detached witness를 보관한다. 같은 symbolic topology라도 load/numeric snapshot이 다르면 서로 다른 FGMRES plan이다.

`ExecutionPlanV2`의 기존 direct solver policy는 변경하지 않는다. 이 artifact는 source contract 위에 future FGMRES backend policy를 추가로 계획하며 direct result를 iterative result로 가장하지 않는다.

## 알고리즘 ABI

- recurrence ABI version `1`
- FP64 fixed-restart right-preconditioned FGMRES
- restart dimension `M=1..16`
- global max iterations `I=0..4096`
- `R=0 if I=0 else ceil(I/M)`
- positive unshifted Jacobi right preconditioner
- DGKS conditional second-pass MGS, `eta=0.717`
- Arnoldi breakdown multiplier `64 eps`
- incremental Givens QR
- scale-relative upper-triangular backsolve
- estimated L2 pass 또는 suspected Arnoldi breakdown에서 candidate true residual replay
- solver L2와 `||r||∞/max(1,||b||∞)` gate의 inclusive 동시 통과
- true-residual checkpoint 기반 plateau+tiny-update stagnation과 별도 divergence rule
- dense `lstsq`/pseudo-inverse, diagonal shift/clamp, silent solver fallback 금지

## Device memory plan

기호:

```text
F = free DOF count
Z = reduced CSR nnz
P = max(1, ceil(F/512))
M = restart dimension
R = maximum restart count
```

### Borrowed 7

| 이름 | 형태 | source |
| --- | ---: | --- |
| `reduced_csr_row_ptr` | `<i4>[F+1]` | free-space symbolic |
| `reduced_csr_column_indices` | `<i4>[Z]` | free-space symbolic |
| `reduced_csr_values` | `<f8>[Z]` | free-space numeric |
| `reduced_state` | `<f8>[F]` | free-space reduced state |
| `reduced_load` | `<f8>[F]` | free-space reduced load |
| `reduced_direction` | `<f8>[F]` | exact latest free-space apply |
| `jacobi_inverse` | `<f8>[F]` | Krylov primitive context |

### Owned 9

| 이름 | 형태 |
| --- | ---: |
| `solution_x` | `<f8>[F]` |
| `true_residual` | `<f8>[F]` |
| `work_w` | `<f8>[F]` |
| `basis_v` | `<f8>[(M+1),F]` |
| `preconditioned_basis_z` | `<f8>[M,F]` |
| `reduction_ping` | `<f8>[2P]` |
| `reduction_pong` | `<f8>[2P]` |
| `packed_dense_state` | `<f8>[M²+5M+1]` |
| `solve_record` | `u8[192+72R]` |

Owned byte 식은 다음과 같다.

```text
8 * ((2M+4)F + 4P + M² + 5M + 1) + 192 + 72R
```

`packed_dense_state`는 `(M+1)M` Hessenberg, cosine `M`, sine `M`, least-squares RHS `M+1`, triangular solution `M`을 담는다. `solve_record`는 little-endian으로 고정된 192-byte header와 restart당 72-byte record를 사용하며 모든 i32/f64 field offset, terminal/termination/hint code와 flag bit를 manifest에 열거한다. Header offset 60에는 fixed restart dimension `M`을 보관한다. `hip_fgmres_solve_record_abi_payload_v1()`이 plan과 HIPRTC identity의 canonical ABI source며 logical offsets, code map, record ABI와 recurrence ABI도 memory-layout hash에 포함된다. 이는 추가 peak device bytes의 계획값이며 실제 allocation 또는 peak VRAM 측정값은 아니다.

## Runtime lineage 경계

Apply receipt, primitive context ID, lease epoch, stream handle, device address, kernel identity는 compile-time에 존재하지 않으므로 plan에 가짜 값으로 넣지 않는다. 향후 context open은 반드시 다음을 수행해야 한다.

1. exact latest free-space apply receipt 재검증
2. exact live Krylov primitive parent 결속
3. exclusive solver-child lease 원자 획득
4. same runtime/device/stream 확인
5. policy와 buffer extent에 맞는 allocation 및 kernel ABI 확인

따라서 현재 `runtime_receipt_lineage_bound=false`, `fgmres_runtime_ready=false`다.

## 검증과 미완료 경계

Strict Draft 2020-12 schema는 16개 buffer의 prefix order뿐 아니라 각 buffer의 ownership/dtype/access/source/initialization/formula와 solve-record ABI를 고정한다. Dimension-dependent shape·element·byte 산술은 JSON Schema만으로 권위를 갖지 않으며 `schema_only_validation_authoritative=false`, `python_semantic_replay_required=true`다. Focused test는 source/policy determinism, `M=2,I=5 → R=3`, 최대 `M=16,I=4096`, byte 식, numeric/load binding, fully rehashed buffer/source forgery, wrong-type/policy failure, compile manifest의 runtime identity 부재, public export와 positive-but-nonfinite-reciprocal Jacobi 사전거부를 검증한다.

다음은 이 v1 plan artifact 자체에서는 계속 미완료다. 첫 두 resource-lifetime 항목은 후속 v0.2.19 context에서 별도 구현됐지만 owned content와 solver 실행은 미완료다.

- device allocation과 exclusive live context(후속 resource-only context에서 parent3+owned8으로 완료)
- FGMRES RTC v2 module을 소유하는 live allocation/context(후속 resource-only context에서 완료; 수치 launch 없음)
- deterministic L2/L∞ producer와 device-scalar/indexed Arnoldi/MGS/DGKS/Givens/backsolve/solution-update kernel
- full device control state와 stagnation/divergence/breakdown finalize
- raw fixed schedule의 H2D/D2H/allocation/sync/fallback 0 receipt
- final compact control record D2H와 full-vector export 경계
- native CPU↔HIP recurrence parity
- ResultIR, reaction/recovery/energy 통합
- SPD/PCG, AMG/DD, Newton, O(N), speedup, commercial readiness
