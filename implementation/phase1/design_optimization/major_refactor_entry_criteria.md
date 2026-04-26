# Major Refactor Entry Criteria

대규모 리팩토링은 아래 조건이 만족될 때만 시작합니다.

## Required Conditions

1. `medium/high` ablation artifact가 연속 2회 이상 안정적으로 생성
2. `nightly_release_gate_report.json`이 최근 3회 연속 `PASS`
3. `design_optimization_dataset_report.json`의 schema v2 필드가 더 이상 크게 변하지 않음
4. `run_design_optimization_cost_reduction.py`의 stage B 선택 정책이 한 주기 이상 안정
5. `committee_review_package_report.json`, `external_validation_latest.json` 동기화가 반복적으로 green
6. GPU audit에 새로운 `remaining_optimizable_host_ops`가 추가되지 않음

## Hard No-Go Signals

- stage B action family가 자주 바뀌는 상태
- budget semantics(`low/medium/high`)가 계속 흔들리는 상태
- committee/external artifact naming이 아직 정리되지 않은 상태
- explain schema가 field/detail 불일치를 다시 만들고 있는 상태
- solver-backed ablation이 proxy fallback으로 자주 되돌아가는 상태

## Why

이 조건이 없으면 대규모 리팩토링은 개선이 아니라 회귀 추적 비용만 키웁니다.

지금 필요한 건 `big bang rewrite`가 아니라:

1. 공통 path 기준점 고정
2. entrypoint/primary report 대응 고정
3. 설계 최적화 로직 경계 고정

그 다음에만 파일 이동이나 패키지 재배치를 시작합니다.
