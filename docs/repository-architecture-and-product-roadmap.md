# Repository Architecture and Product Development Roadmap

- Status: accepted target architecture and ordered implementation plan
- Effective date: 2026-07-22
- Implementation state: planned; this document does not assert current capability or readiness
- Architecture decision: [ADR-008: Repository Package Boundaries](adr/008-repository-package-boundaries.md)

## 1. Purpose and authority

이 문서는 저장소 수준의 목표 패키지 구조, 제품 성숙도 P0-P3 및 제품 PR 1-18의
순서를 정한다. 지금 지원되는 기능의 source of truth가 아니며, 문서에 적힌 목표나
완료 조건만으로 capability, release status 또는 상용 readiness가 승격되지 않는다.

문서 간 역할은 다음과 같다.

- 본 문서: repository/package 경계와 제품 수준의 단계·PR 순서
- [Engine v2 master roadmap](structural-solver-engine-v2-master-roadmap.md): 솔버,
  CPU/HIP 및 수치 계약의 세부 구현 계획
- capability registry와 현재 HEAD에서 생성한 readiness snapshot: 현재 구현·지원·승격
  상태
- [ADR-001](adr/001-numerical-truth-and-claim-boundary.md) 및
  [ADR-007](adr/007-vv-and-promotion-policy.md): 수치적 진실과 V&V 승격 불변식

Engine v2의 문자형 작업 묶음 등 세부 계획은 아래 제품 PR 안에서 더 작게 나눌 수
있다. 그러나 세부 계획이 본 문서의 선행 gate를 우회하거나 proxy, fallback,
benchmark bridge를 authoritative capability로 승격할 수는 없다.

## 2. Target repository structure

현재 저장소를 즉시 여러 repository로 나누지 않는다. 먼저 monorepo 안에서 다음
패키지 경계를 만든 뒤, 독립 배포·소유권·변경 주기가 실제로 필요할 때만 별도
repository 분리를 검토한다.

```text
Structural-Analysis/
├─ python/
│  ├─ structural_analysis_contracts/
│  │  ├─ model/
│  │  ├─ execution/
│  │  ├─ result/
│  │  └─ evidence/
│  │
│  ├─ structural_analysis_core/
│  │  ├─ elements/
│  │  ├─ materials/
│  │  ├─ sections/
│  │  ├─ assembly/
│  │  ├─ solvers/
│  │  └─ analyses/
│  │
│  ├─ structural_analysis_io/
│  │  ├─ neutral/
│  │  ├─ midas/
│  │  └─ ifc/
│  │
│  ├─ structural_analysis_vv/
│  │  ├─ analytic/
│  │  ├─ code_to_code/
│  │  ├─ published/
│  │  └─ experimental/
│  │
│  └─ structural_analysis_ai_control/
│     ├─ episodes/
│     ├─ shadow/
│     ├─ policies/
│     └─ evaluation/
│
├─ apps/
│  ├─ cli/
│  ├─ worker/
│  └─ workbench-web/
│
├─ artifacts/
│  ├─ manifests/
│  └─ schemas/
│
├─ benchmarks/
│  ├─ manifests/
│  └─ small-open-data/
│
├─ legacy/
│  └─ optimization-workbench/
│
└─ docs/
```

이 트리는 목표 상태다. 디렉터리가 아직 없다는 사실은 결함 은닉 사유가 아니며,
기존 경로를 대량 이동하는 것만으로 해당 단계가 완료되지는 않는다.

이 구조는 Python만 허용한다는 뜻이 아니다. Rust/HIP 또는 web source도 아래 표의
책임 package나 app이 소유하며 동일한 dependency/authority 규칙을 따른다. 기존
Engine v2 문서의 논리 경로는 migration 동안 다음과 같이 대응한다.

| Existing logical boundary | Target owner |
| --- | --- |
| `schema/sair`, public model/result/evidence schema | `structural_analysis_contracts`와 `artifacts/schemas` |
| `engine/core`, elements, materials, operators, solvers, CPU/HIP backend | `structural_analysis_core` |
| `interop` | `structural_analysis_io` |
| `validation` | `structural_analysis_vv`와 `benchmarks` |
| AI feature, policy, shadow 및 evaluation runtime | `structural_analysis_ai_control` |
| runtime API, CLI, worker, Workbench 및 viewer | `apps` |
| 기존 optimization Workbench 중 새 계약으로 이관되지 않은 경로 | `legacy/optimization-workbench` |

## 3. Dependency and authority rules

핵심 의존성은 다음과 같이 단방향으로 유지한다. 화살표는 dependency/import 대상
쪽을 가리킨다.

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

적용 규칙:

- `contracts`는 가장 안쪽의 안정된 경계이며 model, execution, result, evidence의
  versioned schema와 typed API를 소유한다.
- `core`는 element/material/section 의미론, assembly, solver 및 analysis 결과의
  유일한 수치적 진실이다.
- `io`는 변환과 provenance를 소유한다. 누락, 근사 또는 unsupported entity를
  silent-ignore하지 않는다.
- `vv`는 analytic, code-to-code, published, experimental 증거를 서로 다른 등급으로
  유지하며 하위 등급 PASS를 상위 등급으로 자동 승격하지 않는다.
- `ai-control`은 core를 import할 수 있지만 core는 AI를 import하지 않는다. AI-off
  경로는 모든 공개 지원 workflow에서 유지한다.
- Workbench는 result/evidence 계약을 표시하고 탐색한다. Workbench 자체 계산은
  diagnostic일 수는 있어도 solver truth, convergence 또는 engineering authority가
  될 수 없다.
- CPU sparse reference와 외부 V&V가 먼저다. GPU/HIP는 그 이후의 parity 및 성능
  track이며, GPU 실행 자체가 결과 권한을 높이지 않는다.

## 4. Migration policy

1. PR마다 target package와 기존 source 사이의 owner를 한 명시적 manifest에 기록한다.
2. 기존 public import/API가 필요하면 얇은 compatibility shim을 두고 제거 버전과
   경고를 테스트한다.
3. 파일 이동과 동작 변경을 가능한 한 분리한다. 각 동작 변경에는 focused test와
   이전 경로 parity를 둔다.
4. `legacy/optimization-workbench` 이동은 현재 소비자가 새 result/evidence 계약으로
   전환된 뒤 수행한다.
5. 대형 artifact는 외부화하되 checksum, origin, license 및 restore 절차를 manifest에
   남긴다.
6. 각 P 단계의 상태는 현재 HEAD에서 새로 생성한 snapshot으로만 판정한다. 과거
   branch, 재사용 receipt 또는 문서 체크박스는 완료 증거가 아니다.

## 5. P0 — Foundation and product truth

### Goal

현재 무엇이 제품이고 무엇이 research, legacy, proxy 또는 quarantine인지 명확히
고정한다.

### Work

- 배포 패키지를 `Structural Analysis` 계열 identity로 통일하고 공개 안정성에 맞게
  `0.x` version으로 전환한다.
- canonical `artifacts/manifests/capabilities.yaml`을 도입한다.
- README, API, CLI 및 Workbench의 지원표와 공개 capability claim을 registry에서
  생성하고 drift를 CI에서 거부한다.
- corotational, fixed-chord 및 legacy 경계를 문서와 registry에 명시한다.
- `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`, `CODEOWNERS`를 추가한다.
- PR #137을 포함한 장기 branch/PR을 inventory하고 retain, supersede 또는 close
  결정을 기록한다.
- issue-PR 자동 close metadata를 검사하는 validator를 도입한다.
- 25 MiB를 넘는 Git artifact를 inventory하고 승인되지 않은 blob을 외부화한다.
- 초기 inventory의 quarantine 86개 파일에 owner와 disposition을 부여한다. 이후
  재계수 결과는 versioned manifest를 기준으로 한다.
- pyright 또는 mypy, coverage threshold와 Python/OS compatibility matrix를 CI에
  도입한다.
- 현재 commit에서 single readiness snapshot을 생성하고 stale snapshot을 거부한다.

### Completion criteria

- package identity가 build metadata, import, CLI, 문서 및 artifact에서 일치한다.
- 모든 공개 지원표와 capability claim이 registry에서 생성된다.
- stale open PR metadata가 없다.
- release surface의 quarantined 파일 중 owner가 없는 항목이 없다.
- 승인되지 않은 25 MiB 초과 Git blob이 없다.
- core typecheck가 통과하고 coverage threshold가 강제된다.
- release status가 현재 HEAD에서 생성된다.

## 6. P1 — Public corotational 2D frame product path

### Goal

Corotational 2D frame을 연구 또는 내부 경로가 아닌 typed public product path로
승격한다.

### Work

- corotational J1-J5 adapter와 corotational ResultIR
- exact engineering recovery
- public compiler profile과 unified nonlinear API
- native sparse assembly와 sparse factorization/conditioning diagnostics
- general branching topology
- multiple support와 prescribed displacement
- release, offset 및 distributed load
- displacement control
- checkpoint-chain replay
- OpenSees 및 두 번째 독립 solver와의 Level 2 검증

### Completion criteria

- public portal-frame profile
- dense/sparse parity
- restart exactness
- authoritative reaction/member/section/fiber result
- fallback-authority promotion 없음
- Level 2 OpenSees slot PASS
- Level 2 second-solver slot PASS

## 7. P2 — Material science and 3D frame

### Work

- fracture-energy concrete와 mesh-objectivity 검증
- confinement, bond-slip 및 partial composite interaction
- cyclic degradation
- 3D corotational frame와 shear-deformable beam
- torsion/warping과 initial imperfection
- nonlinear transient dynamics
- sparse modal/buckling
- published Level 3 benchmark
- job-service 기반 Workbench

### Completion criteria

- mesh-objective RC benchmark PASS
- published material cyclic benchmark PASS
- published snap-through benchmark PASS
- 3D frame external comparison PASS
- checkpoint/resume job service
- signed engineering review package

## 8. P3 — Extended product

다음 기능은 P0-P2의 수치적 진실, 외부 V&V 및 job 경계가 닫힌 뒤 본격적으로
진행한다.

- shell과 plate
- contact
- cable
- soil-structure interaction
- staged construction
- mixed frame-shell nonlinear solve
- distributed execution
- ROCm/HIP production path
- 고객 shadow 3개 이상
- 설계기준 모듈
- guarded AI execution

ROCm/HIP는 CPU sparse reference와 외부 V&V 이후의 성능 track이다. parity,
residency, fallback 및 hardware provenance가 각각 검증되기 전에는 production solver
truth로 표시하지 않는다.

## 9. Ordered product PR sequence

아래 번호는 merge dependency를 뜻한다. 선행 PR의 완료 조건을 충족하지 못한 채
후속 PR의 capability를 public으로 승격하지 않는다. review 가능한 크기를 위해 한
번호를 여러 mechanical sub-PR로 나눌 수 있지만 번호의 gate와 산출물은 하나로
판정한다.

| PR | Phase | Primary deliverable |
| --- | --- | --- |
| 1 | P0 | package rename, 0.x version 및 metadata 단일화 |
| 2 | P0 | `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`, `CODEOWNERS` |
| 3 | P0 | `capabilities.yaml` 및 README/API/CLI/Workbench 지원표 생성 |
| 4 | P0 | 장기 PR/issue/branch 정리, 대형 artifact/quarantine owner 결정 및 PR metadata validator |
| 5 | P0 | pyright/mypy, coverage, Python/OS CI matrix 및 current-HEAD readiness snapshot |
| 6 | P1 | typed ResultIR와 quantity별 unit/tolerance schema |
| 7 | P1 | public compiler profile과 corotational J1-J5 adapter |
| 8 | P1 | corotational exact engineering recovery |
| 9 | P1 | displacement control과 checkpoint-chain replay를 포함한 unified public nonlinear API/CLI |
| 10 | P1 | native COO/CSR nonlinear assembly |
| 11 | P1 | sparse factorization 및 conditioning diagnostics |
| 12 | P1 | branching topology, multiple support 및 prescribed displacement |
| 13 | P1 | release, offset 및 distributed load |
| 14 | P1 | OpenSees clean-runner Level 2 package |
| 15 | P1 | 두 번째 독립 solver Level 2 package |
| 16 | P2 | fracture-energy concrete와 mesh-objectivity benchmark |
| 17 | P2 | Workbench job API와 checkpoint resume |
| 18 | P2 | AI offline counterfactual dataset과 shadow policy scorecard |

이 순서는 기능 breadth보다 제품 권한과 외부 신뢰를 먼저 닫기 위한 것이다. 각 PR은
capability registry, focused verification, known limitation 및 현재 HEAD snapshot을
함께 갱신해야 한다. P3 기능은 별도 승인된 후속 roadmap 없이는 이 순서에 끼워 넣지
않는다.

PR 16-18은 P2 진입 tranche이며 P2 전체 완료를 뜻하지 않는다. 3D frame, cyclic
material, transient, sparse modal/buckling 및 published Level 3 항목은 P1 종료 시점의
현재 HEAD 결과를 기준으로 후속 번호와 review 단위가 확정되어야 한다.

## 10. Change control

- package boundary 변경은 ADR-008을 supersede하는 ADR이 필요하다.
- P 단계의 완료 조건 또는 PR merge dependency 변경은 본 문서의 명시적 revision과
  변경 사유가 필요하다.
- 문서, UI 또는 generated support table은 capability를 구현하거나 승격한 증거가
  아니다.
- externally blocked, partial, proxy, fallback 및 benchmark-bridge 상태를 삭제하거나
  PASS로 합치지 않는다.
- release claim은 반드시 current HEAD snapshot과 일치해야 한다.
