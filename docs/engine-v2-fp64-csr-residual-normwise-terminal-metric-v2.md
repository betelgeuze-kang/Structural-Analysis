# Engine v2 FP64 CSR normwise / FGMRES terminal metric parity v2

상태: v0.2.49 unpublished candidate, backend-neutral norm projection + detached
FGMRES terminal record contract + actual local `gfx1030` high-load observation,
non-promoting

## 목적

v0.2.48은 reduced CSR 각 행의 두 잔차 계산 차이를 caller tolerance 없이
`|delta_r_i| <= B_i`로 감쌌다. 그러나 FGMRES v1 terminal record는 CPU stable-L2와
HIP 256-thread/512-value LASSQ tree라는 서로 다른 축약 경로를 사용한다. 따라서
`||B||`만 terminal scalar에 더하면 각 norm 계산 자체의 FP64 오차가 빠진다.

v0.2.49는 두 단계를 별도 additive contract로 고정한다.

1. componentwise receipt를 `L2`, `Linf`, solver `scaled-Linf` 예산으로 사영한다.
2. CPU/HIP record가 각 represented residual의 exact-real norm interval에서 벗어날 수
   있는 계산 경로 오차를 더해 terminal record 차이를 검증한다.

기존 `hip_fgmres_model_case_parity.v1` schema, receipt, solution/residual fixed gate와
terminal/history gate는 변경하거나 완화하지 않는다.

## Normwise 사영

v0.2.48의 `|delta_r_i| <= B_i`와 reverse triangle inequality에서 다음을 얻는다.

```text
| ||r_c||_2   - ||r_r||_2   | <= ||B||_2
| ||r_c||_inf - ||r_r||_inf | <= ||B||_inf

L              = max(1, ||b||_inf)
| scaled_inf(r_c) - scaled_inf(r_r) | <= ||B||_inf / L
scaled_inf(r)  = ||r||_inf / L
```

`fp64_csr_residual_normwise_v1`은 retained v0.2.48 result를 먼저 전부 재생한다.
각 residual의 exact-real L2는 nonnegative square/sum/sqrt의 lower/upper 연산을
`nextafter(-inf/+inf)`로 감싼 interval로 표현한다. Linf는 represented binary64 값의
exact absolute maximum이고, scaled-Linf division도 outward interval이다. CSR이나 dense
operator를 다시 만들지 않으며 추가 work/storage는 residual 길이에 대해 `O(n)`이다.

## Terminal record 예산

각 metric `m`에 대해 exact-real vector metric을 포함하는 interval을 `I_r`, `I_c`,
검증된 CPU/HIP record를 `m_r`, `m_c`라 둔다.

```text
e_r = max(|m_r - lower(I_r)|, |m_r - upper(I_r)|)
e_c = max(|m_c - lower(I_c)|, |m_c - upper(I_c)|)

T_m = e_r + norm_bound_m + e_c
gate = |m_c - m_r| <= T_m
```

`e_r/e_c`는 caller tolerance가 아니다. CPU result validator가 stable-L2/maximum/division
경로를 residual에서 재생하고, v2 adapter가 exported HIP residual에서 GPU-tree
LASSQ-L2, max-Linf와 scaled division을 직접 다시 계산해 terminal outcome record와 exact
equality를 요구한다. Record relabel은 norm budget에 도달하기 전에 fail-closed한다.

## 구현과 wire 경계

- Backend-neutral public API:
  `attest_fp64_csr_residual_normwise_v1`
- Detached FGMRES public API:
  `replay_hip_fgmres_detached_terminal_metric_parity_v2`
- Strict Draft 2020-12 schemas:
  `fp64_csr_residual_normwise_v1.schema.json`,
  `hip_fgmres_terminal_metric_parity_v2.schema.json`
- 두 result validator는 retained componentwise result, plan, CPU result, raw solution/residual
  bytes와 terminal outcome에서 전체 receipt를 재생한다.
- Core v2 adapter는 device identity나 live context를 받지 않으므로
  `actual_backend_verified=false`, `hardware_provenance_verified=false`다.
- `migration_action`은 각각
  `preserve_v1_and_issue_additive_normwise_v1`,
  `preserve_v1_and_issue_additive_terminal_metric_v2`로 고정한다.
- Restart history metric v2와 ResultIR authority는 발행하지 않는다.

## Subnormal 보수성 보강

검증 중 nonzero binary64 곱셈 또는 나눗셈의 exact-real 결과가 최소 subnormal보다 작아
represented 결과가 `0.0`이 될 때, 기존 `_mul_up/_div_up`도 `0.0`을 반환할 수 있음을
찾았다. v0.2.49는 upper-bound operand가 모두 nonzero이면 결과를
`2^-1074`로 올린다. Exact `Fraction` 회귀에 `2^-1074 * 0.5`를 추가했다.

이는 subnormal hardware acceptance나 formal kernel proof가 아니다. 단지 software
outward primitive가 underflow에서 상한을 잃지 않게 고친 것이다.

## 회귀 검증

- Normwise + terminal metric focused: `14 passed in 9.53s`
- v0.2.48 componentwise + v0.2.49 focused: `34 passed in 14.57s`
- Normwise + componentwise + legacy model-case + capability cross-check:
  `71 passed in 15.06s`
- Terminal observer + all-converged registry/family/ResultIR/public API adjacent cross-check:
  `140 passed in 395.82s (0:06:35)`
- Hardware harness static collection: `1 test collected`
- Ruff check/format, py_compile, 두 strict schema validation 통과

회귀 범위:

- exact `Fraction` sum-of-squares가 L2 interval 제곱 사이에 포함됨
- unit 이상 power-of-two load에서 raw L2/Linf 예산 선형 scaling과 scaled-Linf 불변
- `rhs_linf < 1`에서 solver 정의의 명시적 load-scale floor
- legacy `1e-12` absolute floor보다 큰 terminal metric 차이의 derived-budget 성공
- candidate GPU-tree record relabel, coherent receipt rehash, source splice, forged legacy
  solution child 거부
- v1 schema
  `sha256:4da38578a99ba1c479f32b66f62ef8c1771b4e734f947c1a0b24e1648066f050`
  및 `1e-12/1e-8` fixed gate 보존
- actual wheel에 두 module과 두 schema의 source byte-identical 포함
- public Engine/Contracts/Assembly identity와 sparse AST fence

Current-source single dirty non-release wheel은 `1,427,672` bytes/`270` members,
`sha256:da8eeef8160cdd4dfdd0f83250162b603ae3a4e37453ecd5c65dadcd28b355ae`였다.
소스 경로를 제거한 격리 설치에서 Engine/Assembly/Contracts/Elements public symbols
`932/746/93/10`, 새 두 API의 identity 및 두 module/두 schema source byte를 확인했다.
이는 단일 dirty smoke이며 reproducible 또는 authoritative release artifact 증거가 아니다.

## Actual local gfx1030 고하중 관찰

RX 6900 XT `gfx1030`에서 v0.2.48과 같은 원래 크기의 파생 세 모델을 actual HIP로
실행했다. 기존 strict solution gate, recurrence D2H 0, completion-export blocking D2H
exact 3회, failure 0, fallback 0을 유지했다.

| case | metric | record difference upper | total derived bound | ratio |
| --- | --- | ---: | ---: | ---: |
| rotated-axis `-10,000 N` | L2 | `2.503234925724582e-10` | `1.0851073735052529e-7` | `0.0023069006688603657` |
| rotated-axis `-10,000 N` | Linf | `1.0209078027401121e-10` | `8.671547888513862e-8` | `0.0011773074609809672` |
| rotated-axis `-10,000 N` | scaled-Linf | `1.020907802740112e-14` | `8.671547888513865e-12` | `0.0011773074609809668` |
| four-span `100,000 N` | L2 | `1.5299151462488066e-11` | `1.2847002708427478e-8` | `0.001190873218424093` |
| four-span `100,000 N` | Linf | `2.910383045673371e-11` | `9.858780458671471e-9` | `0.002952072072072049` |
| four-span `100,000 N` | scaled-Linf | `2.9103830456733706e-16` | `9.858780458671472e-14` | `0.002952072072072048` |
| five-span `100,000 N` | L2 | `3.953601733634087e-12` | `1.8679692924393254e-8` | `0.00021165239437481313` |
| five-span `100,000 N` | Linf | `0.0` | `1.3145040611561958e-8` | `0.0` |
| five-span `100,000 N` | scaled-Linf | `0.0` | `1.3145040611561962e-13` | `0.0` |

- required final-source hardware gate: `1 passed in 226.25s (0:03:46)`
- process peak RSS: `429,808 KiB`
- 실행 전후 source aggregate:
  `sha256:f88ab16874385d6a48dde6a17b26effda7fc93a25756f76b81b1ba7ad9366dc3`

이 actual observation은 harness가 live HIP observation/device identity를 별도로 검증한
unsigned·비영속 작업 세션 증거다. Core detached receipt의 false provenance claim을
바꾸지 않는다.

## 근거

IEEE-754 연산 순서에 따른 serial/FMA/parallel dot-product 차이는
[NVIDIA Floating Point and IEEE 754](https://docs.nvidia.com/cuda/archive/13.0.1/floating-point/index.html),
classic `gamma_n` dot-product bound는
[Numerical Validation of Compensated Algorithms](https://hal.science/hal-01367769v1/document)
Proposition 5.1을 따른다. Normwise 단계는 componentwise bound에 reverse triangle
inequality를 적용한다.

## 아직 증명하지 않는 것

- restart history row의 L2/Linf/scaled-Linf v2 계약
- 기존 v1 receipt의 교체 또는 persisted v1→v2 migration
- 고하중 세 모델의 ResultIR/aggregate authority
- v0.2.47 unit-load registry의 원래 load compatibility migration
- formal/machine-checked IEEE 및 reverse-triangle proof
- actual subnormal/overflow hardware acceptance
- external `gfx1100`, same signed artifact multiarchitecture parity
- persistent/signed provenance, broad host-copy-zero, end-to-end O(N), speedup
- nonlinear/dynamic/shell/solid/contact 또는 commercial readiness

## 다음 순서

1. restart history의 `true_residual_l2/linf/scaled` 각 row에 같은 record-path budget을
   결속하고 estimated residual·solution-update metric은 별도 오차 모델로 분리한다.
2. 고하중 세 case를 별도 v2 model-case authority와 ResultIR bridge에 결속한다.
3. v0.2.47 unit-load registry를 변경하지 않는 고하중 compatibility registry/aggregate를
   정의한다.
4. external `gfx1100`과 동일 final artifact local `gfx1030` 재실행으로 확장한다.
