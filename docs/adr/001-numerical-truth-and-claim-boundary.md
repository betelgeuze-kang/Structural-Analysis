# ADR-001: Numerical Truth and Claim Boundary

- Status: accepted
- Date: 2026-07-10
- Deciders: Engine v2 architecture baseline

## Context

기존 저장소에는 실제 물리 residual 경로와 함께 proxy, 축약모델, residual polishing, AI prototype이 공존한다. 이 결과들을 같은 권한으로 취급하면 보조 계산이 최종 평형 또는 상용 closure로 오인될 수 있다.

## Decision

- element/material law에서 생성된 `R(u, state)`, `K_t(u, state)`, `J(u, state)v`, energy가 수치적 진실이다.
- CPU FP64 reference는 독립 검증 기준이고 HIP backend는 동일 의미론의 production 실행이다.
- AI, projection, surrogate, reduced model은 proposal 또는 preconditioner/coarse-space 생성 권한만 갖는다.
- 최종 상태는 full residual, increment, BC, energy, constitutive 및 적용 code gate를 통과한 solver state만 될 수 있다.
- v1과 v2는 parity 기간 동안 병행하고 v2가 gate를 통과한 경로만 순차 승격한다.

## Normative invariants

- AI-off 실행이 모든 지원 workflow에서 가능해야 한다.
- proxy나 fallback을 authoritative 결과로 재분류하지 않는다.
- unsupported/partial/fallback 상태를 receipt와 API에서 보존한다.
- 문서 또는 UI만으로 solver capability를 승격하지 않는다.

## Alternatives considered

- AI가 LF 결과를 직접 최종 보정: 평형과 안전 판정 권한이 불명확해 기각.
- 기존 연구 runner를 그대로 production API로 노출: 상태/ABI/검증 경계가 분산되어 기각.

## Consequences

초기 구현 속도는 느려질 수 있지만 CPU/HIP/AI 결과의 책임과 검증 경계가 명확해진다.

## Verification

- AI-off end-to-end test
- CPU/HIP operator parity
- proposal rejection 후 accepted-state rollback
- gap/readiness claim-boundary audit

## Rollback / supersession

수치적 진실의 권한을 변경하려면 독립 V&V와 안전 검토를 포함하는 새 ADR이 필요하다.
