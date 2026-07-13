# Engine v2 CPU fixed-restart FGMRES reference v1

- 상태: 구현된 결정론적 CPU 기준 오라클, unsigned·non-promoting
- capability profile: `phase0_cpu_fixed_restart_right_preconditioned_fgmres_reference`
- 범위: `ExecutionPlanV2`의 축약 선형계에 대한 fixed-restart right-preconditioned FGMRES
- 기준 문서: [Structural Solver Engine v2 마스터 로드맵](structural-solver-engine-v2-master-roadmap.md)

이 구현은 HIP 솔버가 아니라 향후 장치 상주 recurrence를 판정할 독립 CPU 기준선이다. SciPy iterative solver를 호출하지 않으며, sparse direct solve는 테스트 비교에만 사용한다. 런타임 fallback, HIP 실행, 속도, 전체 `O(N)`, 상용 준비도를 주장하지 않는다.

## 해석 문제와 초기 상태

오라클은 다음 절대 변위 문제를 푼다.

```text
A  = K_ff
b  = F_f
x0 = supplied free state, or zero
r0 = b - A x0
```

초기 수렴은 항상 실제 `A x0`를 다시 계산한 true residual로 판정한다. `b=0`, `x0=0`이면 operator apply 1회 후 iteration 0에서 수렴하며 preconditioner는 실행하지 않는다. 자유 DOF의 `-0.0` 입력은 `+0.0`으로 정규화하고, constrained DOF는 exact `+0.0`만 허용한다.

## 고정 수치 정책

- FP64 only
- restart dimension `1..16`, 기본 `16`
- global iteration budget `0..4096`; restart 경계를 넘어 하나의 cap으로 적용
- positive, unshifted Jacobi right preconditioner
- DGKS 조건에 따른 second-pass modified Gram-Schmidt
- incremental Givens QR와 scale-relative triangular pivot gate
- pseudo-inverse, least-squares rescue, diagonal shift/clamp, iterative-library fallback 금지

내부 L2 수렴 조건은 다음과 같다.

```text
tau_2 = max(atol, rtol * ||b||_2)
||b - A x||_2 <= tau_2
```

`max(||b||, 1)` 형태의 숨은 상대오차 floor는 없다. 이와 별개로 `ExecutionPlanV2`의 권위 경계를 유지하기 위해 다음 scaled true-residual gate도 동시에 통과해야 한다.

```text
||b - A x||_inf / max(1, ||b||_inf) <= plan.residual_tolerance
```

estimated GMRES residual만으로 수렴을 선언하지 않는다. estimated residual이 tolerance를 통과하거나 invariant-subspace breakdown이 감지되면 candidate solution을 만들고 `b-Ax`를 다시 계산한다. 매 restart 경계도 recurrence residual이 아닌 true residual에서 시작한다.

## Arnoldi, breakdown, restart

각 step은 `z_j=D^-1 v_j`, `w=A z_j` 순서의 right-preconditioned Arnoldi recurrence다. 첫 MGS pass 후 norm이 DGKS 기준 아래로 감소할 때만 두 번째 pass를 수행한다. subdiagonal breakdown 기준은 `64 eps ||A z_j||_2`로 스케일되며 절대 `1e-60` 상수를 사용하지 않는다.

Happy breakdown은 triangular solve와 두 true-residual gate를 모두 통과할 때만 수렴이다. 그렇지 않으면 `arnoldi_breakdown`으로 종료한다. Restart dimension `m=2`, global cap `5`이면 schedule은 정확히 `2+2+1`이고 iteration count가 cap을 초과하지 않는다.

Stagnation은 true-residual checkpoint에서만 연속 plateau와 작은 update를 함께 관찰하며, divergence는 초기 residual 대비 별도 factor로 판정한다. `max_iterations`, finite breakdown, stagnation, divergence는 정상 algorithmic terminal이고 arithmetic/operator nonfinite는 `numerical_failure` 또는 안정된 fail-closed contract error다.

## 결과 계약과 강한 검증

`CpuFgmresReferenceResultV1`은 다음을 hash로 결박한다.

- execution plan, operator, numeric snapshot, partition
- canonical initial reduced state와 RHS
- fixed FGMRES policy
- iteration/restart/operator/preconditioner count
- 초기·최종 residual metric과 restart history
- immutable-bytes-backed `reduced_solution`, `true_residual`

결과 스키마는 Draft 2020-12 strict object이며 모든 중첩 객체의 unknown field를 거부한다. 결과 배열은 little-endian contiguous FP64, immutable bytes backing, finite, canonical `+0.0`이어야 한다.

공개 validator에는 약한 검증 모드가 없다. source plan과 policy로 초기 residual, 최종 `b-Ax`, count/history/status 불변식, descriptor/hash를 다시 계산한 뒤 전체 recurrence를 결정론적으로 재실행한다. 따라서 metric/history/status/array를 함께 수정하고 receipt를 다시 hash한 경우도 거부한다.

## 검증된 fixture

- cantilever axial/weak/strong/torsion 네 하중모드의 sparse direct 비교
- zero reduced RHS와 arbitrary nonzero `x0`
- direct solution `x0`의 iteration-0 true-residual 판정
- tiny RHS의 relative-tolerance floor 부재
- tiny nonsingular operator의 scale-relative backsolve
- happy/unhappy Arnoldi breakdown
- restart `2+2+1` global cap
- final candidate true-residual 중복 SpMV 방지
- immutable backing, `-0.0`, strict schema와 non-promoting claim
- fully rehashed metric/count/history/status/iteration-0 state 위조 거부
- nonfinite policy/operator 및 residual replay overflow의 안정된 fail-closed 오류

## 명시적 미완료 경계

다음은 이 CPU 오라클로 완료되지 않는다.

- HIPRTC FGMRES kernel/context와 device scalar state
- raw iteration 구간 H2D/D2H/sync 0 증거
- native CPU↔HIP recurrence parity
- SPD certificate와 PCG fast path
- AMG/DD preconditioner와 mesh-independent iteration
- Newton tangent epoch, trial/commit, line search
- ResultIR reaction/recovery/energy 통합
- end-to-end `O(N)`, speedup, commercial readiness
