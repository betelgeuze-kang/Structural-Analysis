# Bounded Refactor Plan

## 범위

대규모 파일 이동 없이 아래 계층만 먼저 정리합니다.

1. 공통 artifact path
2. entrypoint 메타데이터
3. report wiring
4. committee/external bundle의 design-opt artifact 참조

## Target Tree

```text
implementation/phase1/
  design_optimization/
    artifacts.py
    entrypoints.py
    README.md
    bounded_refactor_plan.md
    major_refactor_entry_criteria.md
  design_optimization_env.py
  design_optimization_explain_schema.py
  design_objective_calibration.py
  generate_design_optimization_dataset.py
  run_design_optimization_solver_loop.py
  run_design_optimization_solver_loop_long.py
  run_design_optimization_budgeted.py
  run_design_optimization_cost_reduction.py
  run_design_optimization_ablation.py
```

## 이번 bounded refactor에서 하는 것

- `release/design_optimization` 하드코딩 경로를 공통 상수로 승격
- runner default path를 공통 상수로 교체
- external bundle의 design-opt artifact 리스트를 공통화
- entrypoint와 primary report 대응표를 코드로 유지

## 이번 bounded refactor에서 하지 않는 것

- flat runner 파일 이동
- solver loop / cost reduction / budgeted logic 분리 이동
- parser, code-check, committee 패키지 전면 재배치
- `phase1` 전체 import graph 재조정

## 다음 단계

1. `candidate_generation.py`
2. `candidate_selection.py`
3. `reporting/design_change_table.py`
4. `reporting/committee_export.py`

이 4개는 로직 분리가 안정화된 뒤에만 추가합니다.
