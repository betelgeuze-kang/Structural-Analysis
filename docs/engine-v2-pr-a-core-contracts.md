# Engine v2 PR A — Core Contracts

## 목적

PR A는 동결된 source-quarry에서 Engine v2의 최소 코어 계약을 current `main`
기준으로 추출한다. 이 변경은 solver 기능이나 제품 readiness를 승격하지 않고,
후속 수치 구현이 공유할 불변 데이터 경계만 만든다.

## 포함 범위

- Architecture Decision Record 7개와 claim-boundary index
- deterministic canonical JSON과 `sha256:<hex>` 해시
- little-endian, C-contiguous, immutable bytes-backed NumPy array
- bool↔numeric kind 변경, float→integer, 범위 초과, 정밀도 손실 dtype cast 차단
- strict Draft 2020-12 `ModelIR v2` schema와 의미 검증
- backend-neutral `ExecutionPlan v1` topology/CSR/operator binding
- immutable `StateIR v1` trial/commit/rollback lifecycle
- legacy public input → v2 core → future result/diagnostic → legacy public output의
  단방향 outer-boundary adapter와 authority 비승격 원칙
- unknown-field, exact scalar type, stale hash, mutable-array fail-closed gate
- core source의 backend/solver/later-result import를 차단하는 AST dependency lint

JSON Schema 표준은 수학적으로 정수인 `0.0`도 `integer`로 인정한다. Python
validator 경계에서는 이를 그대로 허용하지 않고 `type(value) is int`와
`type(value) in (int, float)`를 분리해 bool·integral-float 혼입을 fail-closed한다.
language-neutral consumer도 JSON token type을 보존하는 동등한 검사를 적용해야 한다.

## 계약 흐름

```text
ModelIR v2
  canonical model content hash
        |
        v
ExecutionPlan v1
  entity order + six-DOF map + CSR pattern
  opaque compiler/operator hashes
  runtime-selected external backend binding
        |
        v
StateIR v1
  immutable accepted/trial snapshots
  explicit parent hash + epoch
  commit or exact rollback
```

`ExecutionPlan`은 compiler가 생성한 정수 topology와 opaque artifact hash를
동결하지만 assembler나 solver를 호출하지 않는다. CPU/HIP executor는 이 코어
패키지의 dependency가 아니며 후속 PR에서 코어 계약을 소비하는 방향으로만
연결한다.

## 명시적 제외

- equation scaling policy/vector/hash와 raw/scaled residual
- CPU FGMRES 또는 fixed-rank coarse solve
- ResultIR/DiagnosticIR 타입과 결과 권한
- HIP runtime, kernel, device allocation 또는 hardware provenance
- AI proposal/runtime과 상용 capability 승격
- legacy input migration 또는 v1 API/Viewer output adapter의 실제 구현

따라서 이 PR의 PASS는 schema와 lifecycle의 완결성만 의미한다. 수치 정확도,
solver convergence, CPU/HIP parity, O(N), speedup 또는 commercial readiness의
증거가 아니다.

## 검증

```bash
/home/betelgeuze/.local/bin/ruff check \
  src/structural_analysis/engine_v2 \
  src/structural_analysis/model_ir \
  scripts/validate_model_ir_v2.py \
  tests/test_engine_v2_* \
  tests/test_model_ir_v2_contract.py

python3 -m pytest -q \
  tests/test_engine_v2_canonical_contract.py \
  tests/test_model_ir_v2_contract.py \
  tests/test_engine_v2_execution_plan_v1.py \
  tests/test_engine_v2_state_ir_v1.py \
  tests/test_engine_v2_core_dependency_boundary.py
```

검증 결과:

- focused extraction gate: `64 passed`
- 기존 public CPU/API adjacent regression: `37 passed`
- wheel 격리 설치 후 세 packaged schema resource와 public core import: PASS

이 수치는 current-main 추출 commit의 contract regression이며 solver 성능 또는
hardware evidence로 재사용하지 않는다.
