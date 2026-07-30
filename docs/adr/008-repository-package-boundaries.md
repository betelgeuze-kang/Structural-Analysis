# ADR-008: Repository Package Boundaries

- Status: accepted
- Date: 2026-07-22
- Deciders: repository architecture baseline

## Context

현재 저장소에는 제품 코드, 검증 코드, AI 연구 경로, Workbench 및 과거 최적화
자산이 함께 있다. 이를 즉시 여러 저장소로 분리하면 이력과 검증 경로가 끊길 수
있지만, 패키지 경계가 계속 불명확하면 UI, AI 또는 importer가 solver 결과의
권한을 우회해 정의할 위험이 있다.

## Decision

당장은 monorepo를 유지하고 다음 최상위 경계를 목표 구조로 채택한다.

- `python/structural_analysis_contracts`: model, execution, result, evidence 계약
- `python/structural_analysis_core`: element, material, section, assembly, solver,
  analysis의 수치적 진실
- `python/structural_analysis_io`: neutral, MIDAS 및 IFC adapter
- `python/structural_analysis_vv`: analytic, code-to-code, published 및 experimental
  검증
- `python/structural_analysis_ai_control`: episode, shadow, policy 및 evaluation
- `apps`: CLI, worker 및 web Workbench의 composition/entry surface
- `artifacts`: versioned manifest와 schema
- `benchmarks`: benchmark manifest와 재배포 가능한 소형 공개 데이터
- `legacy/optimization-workbench`: 신규 제품 경로에서 격리한 기존 Workbench 자산

의존성 화살표는 import 가능한 대상 쪽을 가리킨다.

```text
contracts
   ^
core <--- io
   ^
  vv
   ^
 apps
   ^
ai-control
```

모든 화살표가 직접 import를 강제하는 것은 아니지만 역방향 의존은 허용하지
않는다. 특히 다음 규칙은 필수다.

1. `contracts`는 다른 저장소 내부 패키지를 import하지 않는다.
2. `core`는 `contracts`만 소비하며 `io`, `vv`, `apps`, `ai-control`을 import하지
   않는다.
3. `io`는 입력을 계약 또는 core 입력으로 변환할 수 있지만 별도의 solver truth를
   만들지 않는다.
4. `vv`는 core 결과를 검증하고 승격 증거를 만들 수 있지만 core 동작의 runtime
   선행조건이 되지 않는다.
5. `ai-control`은 core와 공개 계약을 import할 수 있지만 core는 AI를 import하지
   않는다. AI 출력은 proposal, policy decision 또는 shadow evaluation이며 solver
   state를 직접 확정하지 않는다.
6. Workbench를 포함한 `apps`는 typed result/evidence 계약을 소비한다. UI 계산,
   표시용 재가공 또는 AI 점수로 convergence, reaction, member/section/fiber 결과의
   권한을 새로 만들지 않는다.
7. dependency cycle과 경계 위반은 CI에서 정적 검사한다.

전체 목표 트리, 단계별 완료 조건 및 PR 순서는
[Repository Architecture and Product Development Roadmap](../repository-architecture-and-product-roadmap.md)에서
관리한다.

## Consequences

- 저장소 분리는 패키지 경계와 독립 release 필요성이 입증된 뒤의 선택 사항이다.
- 기존 `src/structural_analysis`는 한 번에 이동하지 않고 compatibility adapter와
  focused parity test를 둔 단계적 migration으로 교체한다.
- contracts와 capability metadata가 제품 문서, API, CLI 및 Workbench의 지원 범위
  표시에 대한 공통 source가 된다.
- legacy와 research 경로는 보존할 수 있지만 공개 제품 capability로 자동 승격되지
  않는다.

## Verification

- 패키지 import-boundary/cycle 검사
- core typecheck와 focused unit test
- legacy-to-target adapter parity 및 deprecation test
- capability registry에서 생성된 README/API/CLI/Workbench 지원표 drift 검사
- ResultIR/evidence authority와 Workbench 표시값의 end-to-end contract test

## Rollback / supersession

패키지 이름 또는 물리적 디렉터리 migration은 compatibility shim을 통해 되돌릴 수
있다. 수치적 진실의 방향, core-to-AI 금지 또는 result/evidence 권한을 변경하려면
별도의 superseding ADR과 독립 V&V 검토가 필요하다.
