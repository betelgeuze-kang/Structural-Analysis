# Engine v2 Architecture Decision Records

이 디렉터리는 [Structural Solver Engine v2 마스터 로드맵](../structural-solver-engine-v2-master-roadmap.md)의 규범적 구현 결정을 기록한다.

## 상태 의미

- `accepted`: 후속 구현이 따라야 하는 현재 기준
- `proposed`: 검토 중이며 구현 기준으로 아직 확정하지 않음
- `superseded`: 더 새로운 ADR로 교체됨
- `rejected`: 채택하지 않은 대안

ADR은 현재 G1-G10 또는 AI-G1-AI-G10 폐쇄 증거가 아니다. 구현과 focused verification이 별도로 통과해야 한다.

## 구현 경계

ADR은 전체 Engine v2의 장기 결정을 기록하지만, 코드 타입과 runtime은 추출 PR
순서에 맞춰 단계적으로 도입한다. PR #104까지 canonical array/hash, `ModelIR`,
`StateIR`, backend-neutral `ExecutionPlan`, equation scaling, reduced CSR, CPU
FGMRES와 제한된 HIP contract가 도입됐다. 후속 Result authority slice는
displacement-only `NumericalResultIR`와 비권위 `DiagnosticIR` 타입을 추가한다.
reaction/member-force recovery, output adapter, AI runtime과 미검증 hardware
evidence는 각각의 후속 PR gate를 통과하기 전까지 구현 완료로 간주하지 않는다.

## Index

1. [ADR-001: Numerical Truth and Claim Boundary](001-numerical-truth-and-claim-boundary.md)
2. [ADR-002: ModelIR, StateIR, ExecutionPlan, and ResultIR](002-modelir-stateir-resultir-schema.md)
3. [ADR-003: Operator ABI and Constitutive Source Policy](003-operator-abi-and-constitutive-source-policy.md)
4. [ADR-004: Backend, Fallback, Precision, and Residency](004-backend-fallback-precision-and-residency.md)
5. [ADR-005: AI Proposal and Rollback Contract](005-ai-proposal-and-rollback-contract.md)
6. [ADR-006: Complexity and Benchmark Contract](006-complexity-and-benchmark-contract.md)
7. [ADR-007: V&V and Promotion Policy](007-vv-and-promotion-policy.md)
8. [ADR-008: Repository Package Boundaries](008-repository-package-boundaries.md)

## 변경 규칙

- accepted ADR의 의미를 바꿀 때는 기존 파일을 조용히 수정하지 않고 superseding ADR을 추가한다.
- 허용 claim 또는 readiness 의미가 바뀌면 gap ledger/readiness 문서를 별도로 교차검토한다.
- backend, AI 또는 최적화가 authoritative solver gate를 우회하게 만드는 변경은 허용하지 않는다.
