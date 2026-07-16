# Engine v2 FP64 CSR residual roundoff/backward-error v1

상태: v0.2.48 unpublished candidate, backend-neutral contract + actual local
`gfx1030` high-load observation, non-promoting

## 목적

v0.2.47의 첫 actual all-converged 실행은 해 벡터와 scaled convergence gate가 맞아도
near-zero residual의 CPU/HIP 합산 순서 차이가 고정
`1e-12 + 1e-8*abs(r_cpu)` 비교를 넘어서 fail-closed했다. 세 fixture를 unit load로
정규화해 10/10 ResultIR gate를 먼저 닫았지만, 이는 일반 load scale의 수치 계약이
아니었다.

이 v1은 caller가 정하는 absolute tolerance 없이 `ExecutionPlanV2`의 reduced CSR과 두
해·잔차 벡터로부터 행별 허용 가능한 FP64 계산 차이를 유도한다. 기존
`HipFgmresModelCaseParityV1`의 solution/terminal/history strict 계약은 변경하지 않는다.
따라서 이 계약의 성공만으로 기존 ResultIR authority가 발행되지는 않는다.

## 행별 오차 모델

행 `i`의 nonzero 수를 `n_i`, binary64 unit roundoff를 `u=2^-53`, 최소 subnormal을
`eta=2^-1074`라 둔다.

```text
k_i        = 2*n_i + 1
gamma_i    = (k_i*u) / (1-k_i*u)
s_i(x)     = |b_i| + sum_j |a_ij| |x_j|
q_i(x)     = gamma_i*s_i(x) + k_i*eta
t_i        = sum_j |a_ij| |x_candidate_j-x_reference_j|
B_i        = t_i + q_i(x_reference) + q_i(x_candidate)
gate_i     = |r_candidate_i-r_reference_i| <= B_i
```

`t_i`는 서로 다른 해에서 발생하는 exact operator transport를 분리하고, `q_i`는 두
residual 계산 경로의 곱셈·합산·최종 뺄셈 roundoff를 보수적으로 감싼다. FMA나 tree
reduction처럼 더 적은 경로 연산은 이 상한 안에 남는다. 모든 nonnegative bound
연산은 `nextafter(value,+inf)`로 outward rounding하며 overflow/nonfinite, 잘못된 dtype,
extent, signed zero는 fail-closed한다. Subnormal 구간은 `k_i*eta` absolute guard를
명시하고, 그 위의 bound 식은 load/solution/residual 동시 스케일에 대해 1차
homogeneous하다.

각 residual에 대해 다음 componentwise backward error도 기록한다.

```text
beta(x,r) = max_i |r_i| / (|b_i| + sum_j |a_ij| |x_j|)
```

분모가 0인 행은 residual도 exact `+0.0`이어야 한다. 이 값은 진단 metric이며 solver
convergence 정책을 대신하지 않는다.

## 구현 경계

- Public backend-neutral API:
  `attest_fp64_csr_residual_roundoff_v1`
- Strict receipt/result validators와
  `fp64_csr_residual_roundoff_v1.schema.json`
- Retained source vector는 immutable byte snapshot이며 result validator가 plan과 네
  vector에서 receipt를 전부 재생한다.
- Detached FGMRES adapter
  `replay_hip_fgmres_detached_residual_roundoff_v1`는 solution에 기존 fixed
  componentwise gate를 유지하고 다음 두 계약을 함께 발행한다.
  1. CPU reference residual vs candidate exported residual
  2. candidate exported residual vs independent `math.fsum` sparse replay
- Adapter는 terminal observation/device/live context를 받지 않으므로 그 자체의
  `actual_backend_verified`는 false다.
- 구현은 CSR row와 nonzero를 한 번 순회하고 row-sized bound array만 보유한다.
  이 좁은 함수의 work/storage는 `O(nnz+n)`이며 global dense matrix, SciPy, solve,
  device operation 또는 D2H를 수행하지 않는다. End-to-end solver O(N) 주장은 아니다.

## 회귀 검증

Focused contract + detached adapter:

- `20 passed in 6.85s`
- 기존 model-case parity v1: `24 passed in 1.83s`
- Current contract + legacy + capability 3-file cross-check: `56 passed in 7.06s`
- Registry/family/ResultIR/public API를 포함한 7-file adjacent cross-check:
  `116 passed in 264.39s (0:04:24)`
- schema Draft 2020-12 valid
- Ruff check/format 통과

회귀는 다음을 포함한다.

- `2^-20`, `1`, `2^20` power-of-two load scaling에서 bound와 error/bound,
  backward-error ratio 보존
- `10 kN` near-zero cancellation에서 fixed `1e-12`보다 큰 물리 유도 bound
- `|A||delta_x|` solution transport
- 계산 bound의 바로 안쪽 성공과 초과값 거부
- exact `Fraction` 기준 add/multiply/distance/gamma outward primitive 검증
- endian/dtype/extent/nonfinite/signed-zero 거부
- stale/coherently-rehashed tolerance·backend claim·ratio 거부
- public Engine/Contracts/Assembly identity export와 sparse AST fence
- 기존 fixed v1 replay가 동일 고하중 residual을 계속 거부함을 확인해 silent relaxation을
  방지

Current-source single dirty non-release PEP 517 wheel은 `1,411,419` bytes,
`266` members, `sha256:1e61eac1fddf52329d1daa3b789e1f59b838054aff87b908d7adfed19ce56e28`였다.
Actual-wheel test는 새 contract module과 strict schema가 source와 byte-identical하게
포함됨을 확인했고, 소스 경로를 제거한 격리 설치의 public symbol 수는
Engine/Assembly/Contracts/Elements `903/732/78/10`이었다. 이는 단일 dirty smoke이며
reproducible 또는 authoritative release artifact 증거가 아니다.

## Actual local gfx1030 고하중 관찰

RX 6900 XT `gfx1030`에서 v0.2.47 unit-load registry를 변경하지 않고 원래 크기의 세
파생 모델을 즉석 컴파일했다. Actual HIP/device identity, 기존 strict solution gate,
completion-export blocking D2H exact 3회, fallback 0을 유지했다.

| case | load | CPU-HIP max difference | CPU-HIP bound | max ratio | HIP-replay difference | HIP-replay bound | max ratio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| rotated-axis bending | `-10,000 N` | `1.2821601558243858e-9` | `8.67154788851386e-8` | `0.021012885183208055` | `6.002665031701328e-11` | `2.105839482489273e-8` | `0.03547771831820348` |
| four-span axial | `100,000 N` | `2.910383045673371e-11` | `9.858780458671468e-9` | `0.0029520720720720497` | `2.910383045673371e-11` | `9.858780458671468e-9` | `0.0029520720720720497` |
| five-span axial | `100,000 N` | `2.910383045673371e-11` | `1.3145040611561954e-8` | `0.0029520720720720497` | `2.910383045673371e-11` | `1.3145040611561954e-8` | `0.0029520720720720497` |

- required hardware gate: `1 passed in 218.17s (0:03:38)`
- process peak RSS: `428,820 KiB`
- 세 HIP backward error 최대값은 `1.2238707852511078e-15`
- 실행 전후 core/schema/adapter/harness aggregate:
  `sha256:d30dd5e67d1b7cc994bb2a050689eda79d02a6b93d2af7418a51f51671c176f6`

이 관찰은 unsigned·비영속 local hardware observation이다. Core receipt의 backend claim을
true로 바꾸지 않으며 v0.2.47 registry raw/canonical hash나 10/10 ResultIR evidence도
수정하지 않는다.

## 근거와 보수성

NVIDIA의 IEEE-754 dot-product 설명은 serial, FMA, parallel reduction이 모두 표준
연산을 사용하면서도 합산 순서에 따라 다른 결과를 낼 수 있음을 보여 준다.
[NVIDIA Floating Point and IEEE 754](https://docs.nvidia.com/cuda/archive/13.0.1/floating-point/index.html)

classic dot product의 deterministic error bound
`|fl(x^T y)-x^T y| <= gamma_n |x|^T|y|`와 `gamma_n=nu/(1-nu)`는 다음 1차 자료의
Proposition 5.1에 정리되어 있다. 이 구현은 residual subtraction과 서로 다른 두 경로를
포함하기 위해 더 보수적인 `k_i=2*n_i+1`을 사용한다.
[Numerical Validation of Compensated Algorithms](https://hal.science/hal-01367769v1/document)

## 아직 증명하지 않는 것

- v1 terminal/history scalar metric의 새 normwise bound 또는 기존 receipt migration
- 고하중 파생 모델의 ResultIR/aggregate authority
- v0.2.47 unit-load fixture를 원래 load로 되돌리는 compatibility migration
- kernel instruction sequence의 formal/machine-checked IEEE proof
- actual subnormal/overflow hardware acceptance; overflow는 현재 fail-closed
- external `gfx1100`, multiarchitecture 및 동일 signed artifact parity
- persistent/signed hardware provenance, promotion 또는 commercial readiness
- broad iteration host-copy-zero, end-to-end O(N), speedup

## 다음 순서

1. componentwise `B_i`에서 `L2/Linf/scaled Linf` normwise budget을 유도해
   model-case parity v2 terminal metric에 결속한다.
2. 기존 v1 wire receipt를 소급 변경하지 않고 v1→v2 compatibility/migration 결정을
   고정한다.
3. 세 고하중 case의 ResultIR bridge와 post-close validator를 v2로 발행한다.
4. actual `gfx1100`과 동일 final artifact의 local `gfx1030` 재실행으로 확장한다.
