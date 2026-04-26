# Design Optimization Bounded Refactor

이 디렉터리는 기존 flat runner를 유지한 채, `design optimization` 계층의 공통 path, entrypoint 메타데이터, 그리고 bounded helper 모듈을 모아두는 얇은 namespace입니다.

## 목표

- 파일 이동 없이 import 기준점 하나 만들기
- 반복되는 release artifact 경로 상수 제거
- entrypoint/primary report 관계를 한 곳에 모으기
- candidate generation / selection / reporting 책임을 runner에서 분리하기
- 이후 대규모 리팩토링 전에 경계를 먼저 고정하기

## 현재 구조

```text
design_optimization/
  __init__.py
  artifacts.py
  artifact_writers.py
  entrypoint_appendix.py
  entrypoints.py
  io.py
  report_builder.py
  candidate_generation.py
  candidate_selection.py
  reporting.py
  README.md
  bounded_refactor_plan.md
  major_refactor_entry_criteria.md
```

## 사용 원칙

- 기존 CLI 스크립트는 그대로 유지
- 새 코드에서 공통 artifact path가 필요하면 `design_optimization.artifacts` 사용
- 제출본/위원회/runner wiring에서 hardcoded design-opt path를 우선 제거
- solver/budgeted/ablation payload 조립은 가능하면 `report_builder.py`로 공통화
- cost-reduction의 JSON/CSV support artifact는 가능하면 `artifact_writers.py`에서 공유
- stage report의 `build + write`는 가능하면 `artifact_writers.py`의 helper로 통일
- main report도 가능하면 `artifact_writers.py`의 `build + write` helper를 사용
- cost-reduction support artifact는 가능하면 `design change / blocked / candidate explain` writer로 더 잘게 분리
- candidate generation / selection / explain/reporting 로직은 가능하면 이 package 하위 helper에서 공유
- solver/bridge/parser 계층은 아직 이 namespace로 이동하지 않음

## 대상 entrypoints

- `generate_design_optimization_dataset.py`
- `run_design_optimization_solver_loop.py`
- `run_design_optimization_solver_loop_long.py`
- `run_design_optimization_budgeted.py`
- `run_design_optimization_cost_reduction.py`
- `run_design_optimization_ablation.py`
- `generate_design_objective_calibration.py`
