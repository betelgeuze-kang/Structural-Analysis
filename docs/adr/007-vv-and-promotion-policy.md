# ADR-007: V&V and Promotion Policy

- Status: accepted
- Date: 2026-07-10
- Deciders: Engine v2 architecture baseline

## Context

prototype, benchmark bridge, UI receipt, solver verification, 외부 validation이 같은 PASS로 표시되면 상용 readiness가 과장된다.

## Decision

검증 계층을 다음 순서로 분리한다.

1. element: closed-form, patch, rigid-body, energy
2. operator: residual/tangent/JVP consistency
3. algorithm: Newton/Krylov/eigen/dynamics convergence
4. backend: CPU/HIP parity와 deterministic mode
5. cross-solver: 허용 범위의 MIDAS/ETABS/OpenSees 비교
6. real-project: operator-attached 실제 모델 shadow run
7. independent review: 외부 구조전문가와 수치해석 검토
8. regression: versioned input/output/checksum/tolerance

promotion은 `research -> shadow -> CPU parity -> HIP parity/residency -> cross-solver -> independent review -> limited commercial` 순서만 허용한다.

## Normative invariants

- 하위 계층 PASS가 상위 계층을 자동 폐쇄하지 않는다.
- proxy, fallback, benchmark bridge, external blocker를 receipt에 보존한다.
- capability는 implementation state와 promotion state를 분리한다.
- 상용 claim은 supported scope와 known limitations를 machine-readable하게 공개한다.

## Alternatives considered

- 단일 종합 점수로 promotion: 미폐쇄 안전 항목 은닉 위험 때문에 기각.
- 내부 test만으로 상용 승격: 외부/실프로젝트 validation 부재 때문에 기각.

## Verification

- capability matrix schema test
- evidence path 존재/권한 검사
- claim/readiness consistency audit
- 100-case v1 및 300-500-case breadth 목표 추적

## Rollback / supersession

승격 후 regression 또는 evidence invalidation이 발생하면 이전 promotion state로 즉시 내려가며 결과와 사유를 보존한다.
