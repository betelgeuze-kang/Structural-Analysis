# Engine v2 ResultIR / DiagnosticIR 권위 계약

## 목적

Engine v2의 solver recurrence, 진단 관찰, 수치 결과, 엔지니어링 결과를 같은
`PASS`로 취급하지 않도록 권위 경계를 타입과 스키마로 고정한다.

- `DiagnosticIR`: 안정적인 code/path 관찰만 보존하는 비권위 진단
- `NumericalResultIR`: 독립 검증을 통과한 committed global displacement 상태

이 v1 계약은 반력, 부재력, 설계검토 또는 Viewer 결과를 생성하지 않는다.

## NumericalResultIR 생성 조건

`create_numerical_result_ir`는 다음을 하나의 canonical hash로 묶는다.

1. equation scaling이 결합된 정확한 `ExecutionPlan`
2. 동일 plan에서 파생된 reduced CSR identity
3. positive epoch의 committed `StateIR`
4. committed state의 free DOF bytes와 동일한 source solution hash
5. 수렴 terminal receipt
6. 독립 full-residual receipt
7. boundary-condition receipt
8. backend receipt
9. canonical little-endian FP64 global displacement artifact

source recurrence의 권위는 계속
`non_authoritative_solver_recurrence`다. ResultIR 승격은 source terminal 하나가
아니라 committed state와 독립 residual/BC 영수증을 함께 결합했을 때만 허용된다.
`max_iterations`나 `arnoldi_breakdown`, initial StateIR, F=0
`no_solve_reaction_only`, stale plan/state, 다른 free-solution bytes는 fail-closed다.

이 타입은 receipt hash의 결합과 의미 경계를 검증하지만 서명자 또는 외부 증거의
진위를 스스로 인증하지 않는다. ResultIR를 만드는 상위 executor/adapter는 각
receipt의 원래 schema와 signature/실행 정책을 먼저 검증해야 하며, 임의 hash를
넣어 만든 manifest는 제품 권위 증거가 아니다.

## 권위 축

NumericalResultIR v1이 부여하는 권위는 세 축뿐이다.

- converged numerical state
- global displacement
- 이 결과 envelope에 결합된 convergence 판정

다음 축은 고정적으로 비권위 또는 미평가다.

- reaction: `not_evaluated`
- member force: `not_evaluated`
- engineering design / code compliance: `not_authoritative`
- release readiness / commercial use: `not_authoritative`

따라서 manifest hash를 함께 다시 계산하더라도 reaction 또는 engineering 권위를
`authoritative`로 바꾸면 strict schema가 거부한다.

## DiagnosticIR 비승격 규칙

DiagnosticIR entry는 다음 공개 필드만 가진다.

- 안정적인 lowercase code
- sanitized absolute JSON pointer path
- `info | warning | error`
- `observed | partial | unsupported | fallback | failed`
- occurrence count
- 선택적인 evidence hash

raw exception, payload, 자유형 메시지 필드는 스키마에 없으며 unknown field로
거부된다. v1의 `extensions`는 빈 객체로 고정되어 namespaced key를 통한 우회도
허용하지 않는다. fallback·unsupported·partial은 그대로 `partial`, failed는
`blocked`로 집계된다. DiagnosticIR의 numerical, convergence, displacement, reaction,
member-force, engineering, readiness, commercial 권위는 모두
`not_authoritative`로 고정된다.

## Artifact 경계

NumericalResultIR는 StateIR의 global displacement를 flat node-major six-DOF
little-endian FP64 artifact로 보존한다. descriptor는 dtype, shape, byte length,
unit profile, data/content hash와 canonical artifact URI를 가진다. write helper는
배타 생성(`xb`)으로 동시 작성 경합에서도 기존 target overwrite를 거부하고,
write/readback hash 검증에 실패하면 이번 호출이 만든 파일만 제거한다.

이 state projection은 engineering-result recovery가 아니다. reaction과 local-axis
member force는 residual과 동일한 element/material law, operator hash, state epoch를
사용하는 별도 recovery PR에서 구현하고 CPU/HIP parity를 검증해야 한다.

## 검증

```bash
PYTHONPATH=src python3 -m pytest -q \
  tests/test_engine_v2_result_ir_v1.py \
  tests/test_engine_v2_core_dependency_boundary.py \
  tests/test_engine_v2_cpu_fgmres_v1.py

python3 -m ruff check \
  src/structural_analysis/engine_v2 \
  tests/test_engine_v2*.py
```

이 검증은 ResultIR/DiagnosticIR의 로컬 계약만 증명한다. 실제 제품 solve의
독립 residual/BC receipt, reaction/member-force recovery, legacy API/Viewer output
adapter, Windows/Linux 결과 artifact parity, 외부 V&V 또는 상용 readiness를
생성하지 않는다.
