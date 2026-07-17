# ADR-002: ModelIR, StateIR, ExecutionPlan, and ResultIR

- Status: accepted
- Date: 2026-07-10
- Deciders: Engine v2 architecture baseline

## Context

canonical v1은 다수 entity를 `list[dict]`로 보존하고 model, solver option, runtime state 경계를 충분히 구분하지 않는다. HIP 장치 정보까지 ModelIR에 넣으면 backend 변경 때 모델 스키마가 다시 깨진다.

## Decision

- `ModelIR`: 불변 구조 의미, SI 정규화 값, 원본 provenance, stable entity ID를 보존한다.
- `StateIR`: trial/committed material 및 kinematic state를 보존한다.
- `ExecutionPlan`: DOF ordering, operator graph, solver/precision/placement/residency policy를 보존한다.
- `ResultIR`: 결과, 수렴, backend, checksum, recovery provenance를 보존한다.
- JSON Schema draft 2020-12를 Phase 0 language-neutral mirror로 사용한다.
- unknown field는 거부하고 확장은 namespaced `extensions` 안에서만 허용한다.
- solver tolerance, device pointer, HIP stream, 임시 파일경로는 ModelIR에 넣지 않는다.

## Normative invariants

- canonical units는 `m`, `N`, `kg`, `s`, `rad`다.
- 원본 단위와 변환계수를 provenance에 보존한다.
- ID uniqueness, reference integrity, finite number, local-frame handedness, load-combination acyclicity를 semantic validator가 검사한다.
- blocking unsupported feature가 있으면 schema-valid이어도 analysis-ready가 아니다.
- schema major version 변경은 명시적 migration report를 요구한다.

## Alternatives considered

- v1 schema 확장: untyped field 의미와 호환성 부채 때문에 기각.
- backend-native raw tensor를 모델 포맷으로 사용: 물리 의미와 메모리 배치가 결합되어 기각.

## Consequences

adapter와 solver 사이 경계가 명확해지지만 초기 migration/round-trip 구현이 추가된다.

## Verification

- JSON Schema self-validation
- golden fixture validation
- unknown field, dangling reference, duplicate ID, cycle, non-finite number rejection
- deterministic serialization/checksum

## Rollback / supersession

v2 migration은 v1 API를 즉시 제거하지 않는다. v2 adapter 실패 시 v1은 기존 claim boundary로만 유지한다.
