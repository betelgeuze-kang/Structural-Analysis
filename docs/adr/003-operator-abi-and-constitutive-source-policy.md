# ADR-003: Operator ABI and Constitutive Source Policy

- Status: accepted
- Date: 2026-07-10
- Deciders: Engine v2 architecture baseline

## Context

서로 다른 residual, tangent, JVP 구현이 존재하면 Newton/Krylov parity와 재료 state update를 검증할 수 없다. 현재 HIP FFI의 긴 위치 인자 ABI는 formulation 확장에 취약하다.

## Decision

- operator 종류는 최소 `residual`, `tangent`, `jvp`, `mass`, `damping`, `constraint_projection`, `preconditioner`, `result_recovery`를 구분한다.
- `R`, `K_t`, `Jv`는 같은 element/material constitutive source와 state epoch에서 생성한다.
- residual sign convention은 `internal_minus_external`로 고정한다.
- state protocol은 immutable accepted state, trial state, commit, rollback을 명시한다.
- FFI v2는 versioned descriptor/table ABI를 사용하고 모든 struct에 ABI version과 struct size를 둔다.
- runtime buffer pointer/stride/device 정보는 `BufferView`에만 존재하며 serialized ModelIR에 넣지 않는다.

## Normative invariants

- JVP는 기준 residual operator ID와 state epoch를 기록한다.
- CPU/HIP operator는 동일 fixture와 DOF ordering을 소비한다.
- constitutive update 실패는 silent clamp하지 않고 typed failure로 반환한다.
- result recovery는 solver residual과 다른 material law를 사용할 수 없다.

## Alternatives considered

- backend별 독립 constitutive 구현: drift 위험 때문에 기각.
- 고정 배열 위치 인자 ABI 확장: shell/solid/contact 추가 때 호환성 문제가 커져 기각.

## Verification

- finite-difference JVP parity
- element patch/energy/reaction suite
- CPU/HIP residual/tangent/result-recovery parity
- trial/commit/rollback history test

## Rollback / supersession

기존 FFI는 validation harness로 유지하고 v2 descriptor ABI가 parity를 통과할 때만 production dependency를 교체한다.
