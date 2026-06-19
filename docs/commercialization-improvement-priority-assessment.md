# 상용화 개선 우선순위 및 단계 평가

- 기준일: 2026-06-19
- 대상: 전체 repo, `implementation/phase1`, `src/structure-viewer`, 릴리즈/검증 문서와 게이트 스크립트
- 평가 방식: 현재 로컬 게이트 결과, 기존 상용화 gap 문서, 프론트엔드/viewer 계약 문서, 빌드/품질 체크 결과를 함께 반영한다.

## 결론

현재 단계는 **strict evidence-aware 상용 운영 L4, 8.0/10**으로 본다.

- 게이트 기반 공식 점수: **8.0/10** (`scripts/report_commercialization_level.py --closure-mode strict`)
- PM release milestone gate: **M1-M5 5/5 pass**, release areas는 CI streak, release evidence freshness/provenance metadata, human UX observation, license status 때문에 blocked (`11/15` green)
- 실무자 검토 전제 상용 보조툴 readiness: **상용 운영 가능**
- 독립 상용 구조해석제품 readiness: **blocked, 80/100** (`scripts/check_independent_product_readiness.py`)
- 완전자율 상용 구조툴 대체 readiness: **55-60%**

즉, 지금 상태는 "구조 엔지니어가 검토하면서 반복 업무를 크게 줄이는 상용 보조툴"에는 충분히 가까워졌지만, "검증/배포/운영/외부 벤치마크까지 닫힌 독립 상용 구조해석 제품"으로는 아직 부족하다.

## 현재 확인값

| 항목 | 현재 상태 | 의미 |
| --- | --- | --- |
| P0 core evidence | closed | MIDAS roundtrip, KDS load combination, geometry identity, constitutive, solver/element 핵심 증거는 닫힘 |
| P0 overall | closed with publication evidence | `publication_evidence/current` 묶음을 명시하면 P0-1까지 closed |
| P1 inputs | ready | P1 입력 재료는 준비됨 |
| P1 execution | ready | publication evidence 기반 P1 readiness와 benchmark breadth가 unblocked |
| P1 evidence sidecar structure | pass | `preflight_p1_evidence_sidecar_intake.py --structure-only --fail-open` 통과. EB/RH row 구조는 준비됨 |
| source boundary inventory | pass | CI에서 `plan_source_boundary_cleanup.py --large-file-threshold-mib 25 --fail-on-candidates` 실행, 현재 후보 0건 |
| 상용화 레벨 | L4 strict evidence-aware | `commercial_operations_ready_with_evidence_closure`, strict evidence는 EB receipt 때문에 pending |
| 상용화 점수 | 8.0/10 | strict evidence 기준. 독립 제품 승격은 별도 readiness gate로 blocked |
| 외부 benchmark receipt | 0/4 attached | strict evidence gate는 아직 pending. 외부 검증은 아직 claim 승격 근거로 쓰면 안 됨 |
| residual holdout closure | 3/3 signed_attached | RH-001/RH-002/RH-003 signed closure evidence는 attached로 계산됨 |
| runtime production packaging | pass | strict Rust/HIP probe, SBOM, native artifact manifest, compatibility matrix가 `production_runtime_packaging_manifest.json`으로 연결됨 |
| production ops/security gate | pass | auth/tenant/audit 계약, no-default-secret production path, tenant/actor rate limit, request metadata limit, audit digest, `/ops/policy` manifest가 readiness gate를 통과함 |
| support bundle | pass | redaction, audit digest, roundtrip 가능한 support bundle manifest가 생성됨 |
| viewer sheet package | pass | SVG sheet/revision/callout/deep-link가 `structure-viewer-drawing-sheet-package.v1`로 report/panel에 연결됨 |
| viewer performance budget | pass | wall/slab instancing, surface LOD, BVH picking, pick-candidate cap이 `structure_viewer_performance_budget_manifest.json` static contract로 고정됨 |
| viewer browser performance probe | pass | `npm run verify:viewer-performance-probe`가 local browser ready/FPS smoke를 수행하며 고객 하드웨어 FPS claim은 하지 않음 |
| viewer visual regression | pass | `npm run verify:viewer-visual-regression`이 render mode와 plan/review/compare/evidence-ingest workflow-state local canvas signature baseline을 비교하며 pixel-perfect 고객 장비 claim은 하지 않음 |
| frontend build | pass | `npm run build`, frontend build contract 통과 |
| repo hygiene | pass | repo hygiene, generated artifact drift 통과 |
| critical static lint | pass | `ruff --select F821,F601,F401,F841` 통과 |
| full static lint | pass | 전체 `ruff check .` 통과, CI gate를 full ruff로 승격 |
| full pytest | pass | `1387 passed`, 테스트 후 tracked generated artifact drift 없음 |

## 2026-05-13~2026-05-14 실행 결과

문서 작성 후 실제로 아래 항목을 진행했다.

- `publication_evidence/current` bundle을 `check_p0_closure_status.py`에 명시해 P0 전체를 closed로 재판정했다.
- P1 readiness와 P1 benchmark breadth를 같은 P0 evidence 기준으로 재실행해 둘 다 `ready` 상태로 만들었다.
- P1 operational queues와 evidence intake template를 materialize했다.
- `F821`, `F601`, `F401` lint를 0건으로 정리하고 CI에 `python -m ruff check . --select F821,F601,F401` gate를 추가했다.
- 이어서 `F841`을 작은 source/report/test 파일과 대형 HTML generator에서 제거했고, 임시 per-file ignore도 제거했다.
- `python -m ruff check . --select F821,F601,F401,F841`는 0건이며, 전체 ruff 잔여는 **147건에서 30건**으로 줄었다.
- 이어서 `E402/E741/E731/E701/F811` 잔여 30건을 정리해 전체 `python -m ruff check .` 통과 상태로 만들고 CI static check를 full ruff로 승격했다.
- 풀 테스트 후 `panel_zone_solver_verified_export_bundle.json`이 fixture 샘플로 덮이는 테스트 격리 누락을 수정했고, 재실행 후 `check_generated_worktree_clean.py --show-ok` 통과를 확인했다.
- `python -m pytest -q`는 **1387 passed**로 통과했다.
- P1 EB/RH evidence sidecar preflight에 `--structure-only` 모드를 추가해, 내부 준비 구조와 strict evidence 상태를 분리했다.
- `python3 scripts/preflight_p1_evidence_sidecar_intake.py --structure-only --fail-open --json`은 통과하며, 같은 preflight의 기본 strict evidence 모드는 EB receipt 4건 pending을 blocker로 보고한다. RH closure evidence 3건은 `signed_attached`로 attached 처리된다.
- clean-checkout evidence chain도 `p1_evidence_sidecar_structure_preflight`와 strict `p1_evidence_sidecar_preflight`를 함께 기록하므로, release reviewer가 내부 준비도와 실제 승격 evidence를 한 payload에서 구분할 수 있다.
- 구조 웹뷰어의 real drawing browser state를 `viewer-real-drawing-browser-state.js` 모듈로 분리했고, single-file viewer generator가 이 모듈을 data URL로 inline하도록 연결했다.
- source-boundary cleanup plan에 JSON/Markdown 산출물, NUL-safe tracked file fixture, `--fail-on-candidates` 게이트를 추가했고 현재 repo 기준 후보 0건 통과를 확인했다.
- CI에 source-boundary inventory gate를 추가해 새 대형 산출물/경계 후보가 들어오면 pre-merge에서 차단되도록 했다.
- 구조 웹뷰어의 shared selection 정규화/query/storage payload를 `viewer-shared-selection-state.js`로 분리했고, single-file viewer generator inline 계약까지 검증했다.
- 구조 웹뷰어의 real drawing 품질 tier/search/sort/review queue 계산을 `viewer-real-drawing-quality.js`로 분리했고, 도면 검색이 zero-load/load evidence 상태까지 잡도록 계약 테스트를 추가했다.
- CI에 `Structure viewer contracts` 단계를 추가해 3D viewer 모듈/도면 품질/공유 선택/single-file inline 계약을 frontend smoke 전에 강제 검증하도록 했다.
- `scripts/verify_structure_viewer_contracts.py`를 추가해 CI와 로컬이 같은 structure viewer 계약 suite를 실행하도록 했다.
- 구조 웹뷰어의 KPI/stat summary 계산을 `viewer-stats-summary.js`로 분리했고, real drawing quality module을 재사용하는 독립 계약 테스트를 추가했다.
- 구조 웹뷰어의 real drawing switcher/browser/review/promotion HTML 렌더링을 `viewer-real-drawing-panel-renderer.js`로 분리했고, single-file inline 계약에 포함했다.
- 구조 웹뷰어의 real drawing 선택/최근 선택/필터 결과 이동 계산을 `viewer-real-drawing-selection.js`로 분리했고, 선택 stale fallback과 single-file inline 계약을 테스트로 고정했다.
- 구조 웹뷰어의 real drawing 패널 view-model 계산을 `viewer-real-drawing-panel-model.js`로 분리했고, review/promotion queue 우선순위와 active asset fallback을 독립 계약 테스트로 고정했다.
- 구조 웹뷰어의 real drawing 패널 interaction binding을 `viewer-real-drawing-panel-events.js`로 분리했고, fake DOM 계약 테스트로 select/change/click/input/Enter 흐름을 고정했다.
- 구조 웹뷰어의 real drawing model tree badge/tooltip/empty-state 계산을 `viewer-real-drawing-tree-model.js`로 분리했고, 도면 트리 표시 계약을 테스트로 고정했다.
- 구조 웹뷰어의 side panel load-case inventory/layer toggle 계산을 `viewer-side-panel-model.js`로 분리했고, load-case fallback/active insertion 계약을 테스트로 고정했다.
- 구조 웹뷰어의 member search result 중복 제거/selected/isolate 표시 계산을 `viewer-search-results-model.js`로 분리했고, applied section 검색 계약을 테스트로 고정했다.
- 구조 웹뷰어의 selection key/summary/clear button state 계산을 `viewer-selection-summary-model.js`로 분리했고, multi-selection summary 계약을 테스트로 고정했다.
- 상용화 레포트는 strict evidence 기준 **`8.0/10`**과 L4를 보고한다.

남은 strict blocker는 외부 benchmark receipt 4건과 full commercial replacement false 상태다. RH closure 3건은 signed evidence로 닫혔지만, full autonomous replacement claim을 열지는 않는다.

## 2026-05-18~2026-05-19 실행 결과

- `project_ops_api_service.py`에서 production default secret을 제거하고, auth-enabled server는 명시 secret 또는 `PROJECT_OPS_JWT_HMAC_SECRET` 없이는 시작하지 않도록 닫았다.
- Project ops API에 tenant/actor rate limit, request metadata byte limit, audit SHA-256 batch digest, `/audit/digest`, `/ops/policy`, retention/export/backup/delete policy surface를 추가했다.
- `scripts/check_independent_product_readiness.py`가 auth/audit뿐 아니라 rate limit, request limit, audit digest, policy manifest, lifecycle policy를 production ops gate로 확인하도록 강화했다.
- `scripts/build_project_ops_deployment_drill_manifest.py`를 추가해 secret rotation negative-start, gateway/rate policy, backup/restore, tenant delete, audit digest, incident response dry-run contract를 `project_ops_deployment_drill_manifest.json`으로 남기고 readiness/support bundle에 연결했다.
- Runtime packaging manifest, runtime SBOM, native runtime artifact manifest, compatibility matrix, support bundle manifest를 생성하고 독립 제품 gate에 연결했다.
- `deployment/onprem` packaging skeleton과 `scripts/build_onprem_deployment_packaging_manifest.py`를 추가해 Containerfile, compose example, offline license example, signed update package example을 on-prem/air-gapped skeleton contract로 검증한다.
- `scripts/build_structure_viewer_performance_budget_manifest.py`를 추가해 wall/slab instancing, surface LOD, BVH picking, pick-candidate cap을 `static_contract` evidence로 남긴다.
- `scripts/measure-structure-viewer-performance.mjs`와 `npm run verify:viewer-performance-probe`를 추가해 local browser canvas ready/FPS smoke를 full quality gate에 연결했다. 이 증거는 `live_performance_claim=false`이며 고객 하드웨어 FPS claim으로 쓰지 않는다.
- `scripts/measure-structure-viewer-visual-regression.mjs`와 `npm run verify:viewer-visual-regression`을 추가해 render mode 및 plan/review/compare/evidence-ingest workflow-state local canvas signature baseline을 full quality gate에 연결했다. 이 증거는 `live_visual_claim=false`이며 pixel-perfect 고객 장비 렌더링 claim으로 쓰지 않는다.
- Viewer evidence hub에 review task, solver receipt, commercial-tool crosswalk, evidence ingest, renderable ingest, lineage drilldown, local ops bundle 흐름을 확장했다.
- 선택 부재의 SVG sheet/revision/callout/viewer deep-link를 `structure-viewer-drawing-sheet-package.v1`로 정규화하고 HTML report/report panel에 노출했다.
- 현재 `python3 scripts/check_independent_product_readiness.py --json`은 production ops/runtime/support/viewer packaging과 RH signed closure가 ready인 상태에서도 strict EB receipt 때문에 **80/100 blocked**를 유지한다.

## 우선순위 0. P0 릴리즈 증거 게이트 닫기

가장 먼저 해야 한다. 핵심 엔진 증거가 닫혀 있어도, release asset listing과 published-byte verification이 없으면 문서상 P0 전체는 open이다.

완료된 부분:

- release asset listing, upload plan, metadata preflight, post-publish roundtrip, hydrated SHA-bytes verification evidence bundle 확인
- 22/22 release asset listing 일치
- evidence bundle 기반 `p0_closed=true` 확인

주의할 부분:

- release tree는 `.gitignore` 대상이므로, 기본 실행이 아니라 publication evidence bundle을 명시해야 같은 판정이 재현됨
- README/상용화 문서/릴리즈 문서가 같은 evidence path를 가리키도록 계속 동기화해야 함

완료 기준:

- `scripts/check_p0_closure_status.py`가 release publication까지 포함해 `p0_closed=true`를 보고
- 해당 결과가 md/json evidence로 남고
- README, 상용화 gap 문서, 릴리즈 문서가 같은 상태를 가리킴

다음 작업:

1. P0 status md/json을 release evidence bundle 기준으로 유지
2. README와 상용화 문서의 P0/P1 상태 표현 동기화
3. release evidence가 바뀔 때마다 같은 명령으로 재판정

## 우선순위 1. 정적 품질 게이트 정리

상용툴 수준에서는 "빌드는 된다"보다 "정적 품질 게이트가 깨끗하다"가 중요하다. 현재 ruff 기준 잔여 오류는 0개다.

완료된 부분:

- source/test 영역의 `F821`, `F601` 0건
- source/test 영역의 `F401` 0건
- source/test/generator 영역의 `F841` 0건, generator-scoped ignore 제거 완료
- source/test 영역의 `E402`, `E741`, `E731`, `E701`, `F811` 0건
- vendored `implementation/phase1/_vendor/**` ruff 제외
- generated open-data demo path를 ruff 제외해 generated artifact drift와 lint 대상 경계를 분리
- CI에 full ruff static check 추가
- 풀 테스트가 tracked generated artifact를 오염시키던 handoff 테스트 격리 누락 수정

남은 부분:

- 정적 lint blocker는 없음
- 대형 HTML generator는 lint 때문이 아니라 유지보수성 때문에 별도 모듈 분리 필요

완료 기준:

- vendored/generated 제외 정책을 명확히 한 `ruff` 설정 추가
- source 영역의 `F821`, `F601` 0건
- `F841`와 style/safety rule 정리
- CI에 full `ruff check` 추가

다음 작업:

1. ruff full pass를 CI 필수 게이트로 유지
2. 새 generator/test 추가 시 generated/source 경계와 import bootstrap 예외를 문서화
3. 대형 HTML generator를 renderer/decision/data transform/CLI로 분리

## 우선순위 2. P1 evidence intake와 운영 queue 완성

외부 검증은 지금 당장 실제로 모으기 어렵더라도, 상용 claim을 올리려면 evidence intake와 queue는 제품처럼 닫혀 있어야 한다.

완료된 부분:

- P1 readiness unblocked
- P1 benchmark breadth ready
- P1 operational queues materialized
- EB/RH evidence intake template generated
- EB/RH sidecar row 구조 preflight 통과 모드 추가
- `--structure-only --fail-open`은 준비 구조를 통과시키고, strict EB receipt pending은 `pending_evidence_blockers`로 분리 보고
- clean-checkout materializer가 structure preflight와 strict preflight를 모두 payload에 기록

남은 부분:

- external benchmark submission receipt `0/4`
- residual holdout closure evidence `3/3 signed_attached`

완료 기준:

- P1 operational queues materialized
- EB 4개 lane에 receipt/status/update sidecar 구조 존재
- RH 3건에 owner/status/SLA/closure packet template와 signed closure evidence 존재
- 외부 증거가 없는 상태와 내부 준비 완료 상태가 명확히 분리됨

다음 작업:

1. 제품 개발 중에는 `preflight_p1_evidence_sidecar_intake.py --structure-only --fail-open`을 내부 준비도 gate로 사용
2. EB receipt 4개에 실제 receipt URL/path 또는 formal hold evidence 연결
3. RH 3개의 signed closure evidence path 유지 및 회귀 검증
4. `build_p1_evidence_sidecar_updates.py --require-complete` 실행
5. `preflight_p1_evidence_sidecar_intake.py --fail-open` strict evidence gate 통과

## 우선순위 3. 소스와 대형 산출물 경계 재정리

현재 `implementation/phase1`은 로컬 기준 매우 크고, open-data/generator/report 산출물이 source와 강하게 섞여 있다. 상용 배포와 협업에는 큰 리스크다.

현재 부족한 부분:

- 대형 JSON/open-data artifact가 repo 운용 비용을 키움
- generated artifact와 source artifact의 경계가 일부 흐림
- clone, CI, review, storage 비용 증가
- 파일명/경로에 공백과 non-ASCII가 있어 일부 도구는 NUL-safe 처리가 필요함

진행된 부분:

- `plan_source_boundary_cleanup.py`가 JSON/Markdown inventory를 산출하고 `--fail-on-candidates`로 게이트화 가능
- tracked file fixture가 NUL 구분자를 지원해 공백/non-ASCII 경로가 섞여도 안전하게 검증 가능
- `.github/workflows/ci.yml`에서 source-boundary inventory를 필수 gate로 실행
- 현재 repo 기준 `--large-file-threshold-mib 25 --fail-on-candidates` 통과, cleanup candidate 0건

완료 기준:

- source repo에는 작은 manifest와 deterministic generator만 유지
- 대형 data/artifact는 release asset, cache, external artifact manifest로 이동
- restore runbook으로 clean checkout 재현 가능
- path-safe/NUL-safe 검증 스크립트 확보

다음 작업:

1. source로 남길 파일과 release/cache로 보낼 파일 분류 기준을 CI 문서에 더 강하게 연결
2. open-data artifact restore runbook과 manifest 업데이트
3. CI가 대형 artifact 없이도 핵심 계약을 재현하도록 유지
4. 새 대형 산출물 추가 시 `--fail-on-candidates`를 pre-merge gate로 사용

## 우선순위 4. 구조 3D 웹뷰어 제품화

웹뷰어는 기능이 많이 붙었지만, 아직 상용 프론트엔드처럼 모듈 경계와 회귀 검증이 충분히 깔끔하지 않다.

현재 부족한 부분:

- `src/structure-viewer/index.html`가 여전히 큼
- `design-theme.css`도 장기 유지보수에는 큰 편
- source viewer와 generated single-file viewer의 차이를 사용자가 체감하기 어려울 수 있음
- 최적화 도면 선택/전환, provenance, cross-view selection이 더 제품형이어야 함
- 3D wall/slab batching, LOD, hit-test 비용 제어는 static contract, local browser probe, 11-case render-mode/core/advanced workflow visual baseline으로 고정됐지만 고객 하드웨어 FPS/latency matrix는 더 필요함

진행된 부분:

- real drawing browser state/query/storage 정규화를 `viewer-real-drawing-browser-state.js`로 분리
- shared selection state/query/storage payload 정규화를 `viewer-shared-selection-state.js`로 분리
- real drawing 품질 tier/search/sort/review queue 계산을 `viewer-real-drawing-quality.js`로 분리
- source viewer와 generated single-file viewer 모두 새 browser-state 모듈을 계약 테스트로 검증
- single-file viewer generator가 browser/selection/quality 모듈을 외부 sidecar 없이 data URL로 inline하도록 연결
- CI에서 structure viewer contract suite를 frontend smoke 전 필수 단계로 실행
- `scripts/verify_structure_viewer_contracts.py --dry-run`으로 CI와 로컬 viewer gate 범위를 한 곳에서 확인 가능
- KPI/stat summary 계산을 `viewer-stats-summary.js`로 분리하고 single-file inline 계약에 포함
- real drawing 패널 HTML 렌더링을 `viewer-real-drawing-panel-renderer.js`로 분리하고 독립 계약 테스트 추가
- real drawing 선택/최근 선택/브라우저 결과 이동 계산을 `viewer-real-drawing-selection.js`로 분리하고 stale selection fallback을 독립 계약 테스트로 고정
- real drawing 패널 view-model 계산을 `viewer-real-drawing-panel-model.js`로 분리하고 review/promotion queue 우선순위를 독립 계약 테스트로 고정
- real drawing 패널 interaction binding을 `viewer-real-drawing-panel-events.js`로 분리하고 select/change/click/input/Enter 흐름을 fake DOM 계약 테스트로 고정
- real drawing model tree badge/tooltip/empty-state 계산을 `viewer-real-drawing-tree-model.js`로 분리하고 도면 트리 표시 계약 테스트 추가
- side panel load-case inventory/layer toggle 계산을 `viewer-side-panel-model.js`로 분리하고 load-case fallback/active insertion 계약 테스트 추가
- member search result 중복 제거/selected/isolate 표시 계산을 `viewer-search-results-model.js`로 분리하고 applied section 검색 계약 테스트 추가
- selection key/summary/clear button state 계산을 `viewer-selection-summary-model.js`로 분리하고 multi-selection summary 계약 테스트 추가
- wall/slab surface instancing, surface LOD, BVH picking, pick-candidate cap을 `structure_viewer_performance_budget_manifest.json` static contract와 전용 테스트로 고정
- local browser performance probe를 full quality gate에 연결하고 `structure_viewer_browser_performance_probe.json` artifact 생성 경로를 추가
- render-mode/core workflow-state와 renderable JSON/section-edit/load-combination draft visual regression baseline을 full quality gate에 연결하고 `structure_viewer_visual_regression_baseline.json` artifact 생성 경로를 추가

완료 기준:

- viewer shell, data loading, selection, camera, render layer, drawing selector가 모듈화됨
- 도면 선택/전환 UX가 현재 등록 도면 수가 늘어나도 빠르고 명확함
- 3D/charts/panel-zone/optimization-history 간 shared selection 계약 통일
- Playwright 또는 동등한 smoke/visual regression으로 blank canvas, layout overlap, 주요 interaction 검증
- wall/slab/LOD/hit-test static budget manifest, local browser probe, local visual baseline, 고객 하드웨어 FPS/latency regression budget 분리
- single-file export와 repo-local source viewer의 의존성이 문서와 테스트에서 분리됨

다음 작업:

1. `index.html`에서 viewer state, drawing registry, selection controller를 추가 분리
2. 도면 목록 검색/필터/최근 선택/품질 상태 badge 강화
3. panel-zone proxy/verified 상태를 UI에서 명확히 표시
4. static performance budget manifest, local browser probe, 11-case render-mode/core/advanced workflow visual baseline을 유지하면서 customer hardware large model FPS/latency 측정 추가
5. `structure-viewer-drawing-sheet-package.v1` 계약을 유지하면서 solver-verified panel-zone surfacing으로 이동

## 우선순위 5. 하드 런타임 productization

문서와 contract는 많지만, 일부 hard implementation은 아직 stub/contract/probe 성격이 남아 있다.

현재 부족한 부분:

- zero-copy bridge가 실제 device producer 경로보다 fallback/contract 성격이 강함
- Rust/HIP/ONNX native runtime이 상용 통합 런타임 수준으로 완전히 제품화됐다고 보기 어려움
- 성능, 장애 복구, fallback 정책은 더 필요하지만 runtime packaging manifest/SBOM/native artifact/compatibility evidence는 readiness gate에서 ready 상태임

완료 기준:

- 실제 producer -> runtime -> verifier 경로가 end-to-end로 고정
- CPU fallback, GPU path, failure mode가 명시적이고 테스트됨
- 성능 budget과 regression threshold가 release gate에 포함됨
- native runtime artifact packaging과 version compatibility가 문서화됨

다음 작업:

1. zero-copy/Rust/HIP path에서 stub 명칭과 실제 구현 범위 분리
2. end-to-end smoke를 CPU/GPU lane으로 분리
3. fallback 발생 시 viewer/report에 provenance로 남기기
4. runtime packaging manifest 유지 및 installer/container packaging evidence 확장

## 우선순위 6. 운영 API와 보안/권한 모델

현재 project ops API는 reference control-plane API로 올라왔지만, 상용 배포 전에는 gateway/WAF, secret rotation, tenant deletion/restore drill, WORM 또는 서명된 audit storage가 더 필요하다.

현재 부족한 부분:

- local `http.server` 기반 API
- production gateway/WAF와 API rate limit 파라미터가 아직 실제 배포값으로 검증되지 않음
- multi-user 저장소/tenant deletion execution evidence는 아직 drill 수준
- audit digest는 구현됐지만 외부 WORM 저장소 또는 서명 키 연동은 남음

완료 기준:

- 상용 배포 대상 API와 local helper API 분리
- authn/authz, audit log, request validation, rate limit 정책 유지 및 배포 파라미터 검증
- 프로젝트/도면/검토 evidence의 저장소 수명주기 정의
- 최소 보안 smoke와 threat model 문서화

다음 작업:

1. production gateway/WAF와 project ops rate limit 파라미터 확정
2. secret rotation, backup/restore, tenant deletion, incident drill evidence 추가
3. audit digest를 WORM 저장소 또는 서명 키와 연동
4. 보안 체크를 release checklist와 support bundle roundtrip에 계속 포함

## 우선순위 7. 대형 generator 리팩터링

상용툴은 기능 추가보다 장기 유지보수가 중요하다. 현재 일부 generator/report script는 너무 커져서 회귀 위험이 크다.

현재 부족한 부분:

- 수천~수만 라인 단일 script 존재
- report 생성, evidence 판정, HTML 렌더링, 데이터 변환이 한 파일에 섞임
- 테스트 단위가 커지고 변경 영향 파악이 어려움

완료 기준:

- domain별 module 분리
- pure data transform, gate decision, renderer, CLI entrypoint 분리
- shared schema와 writer helper 재사용
- 기존 산출물 byte/contract regression 유지

다음 작업:

1. 가장 큰 viewer/report generator부터 module boundary 설계
2. public CLI는 유지하고 내부만 분리
3. golden output 또는 contract test로 기존 산출물 호환성 고정
4. 신규 기능은 분리된 module에만 추가

## 독립 상용제품 승격 산정

상용 보조툴 점수와 독립 상용제품 readiness는 분리한다.

- strict evidence-aware 상용 운영 점수: **8.0/10**
- 독립 상용 구조해석제품 readiness: `scripts/check_independent_product_readiness.py` 기준 blocked
- 완전자율 상용 구조툴 대체 readiness: **55-60%**

독립 상용제품 readiness는 아래 가중치로 본다.

| 평가 축 | 가중치 | 현재 상태 | 가중 기여 |
| --- | ---: | ---: | ---: |
| P0 release/core evidence | 15 | closed | 15 |
| P1 validation/benchmark breadth | 15 | ready | 15 |
| strict EB/RH evidence | 20 | EB 0/4, RH 3/3 signed_attached | 0 |
| runtime production path | 15 | strict runtime + packaging manifest pass | 15 |
| ops/security productization | 15 | no production default secret, auth/tenant/audit/rate/request-limit/audit-digest/policy/deployment-drill contract pass | 15 |
| packaging/support | 10 | support bundle redaction/digest/roundtrip pass, on-prem/air-gapped skeleton pass | 10 |
| claim governance | 5 | synchronized | 5 |
| source boundary | 5 | pass | 5 |
| 합계 | 100 | - | **80** |

따라서 현재 판정은 다음처럼 구분한다.

- **8.0/10**: strict evidence-aware 상용 운영 readiness
- **blocked / 80%**: 독립 상용 구조해석제품 readiness
- **55-60%**: 완전자율 상용 구조툴 대체 readiness

## 단계 목표

| 단계 | 목표 퍼센트 | 승격 조건 |
| --- | ---: | --- |
| 현재 | blocked / 80% | L4, P0/P1/runtime/ops/support ready, RH signed closure ready, EB receipt pending |
| 다음 목표 | 100% | EB strict evidence receipt sidecar closed 4/4, claim docs synchronized |
| 독립 제품 후보 | 80%+ | runtime production path, ops/security, packaging/support gate closed |
| 독립 제품 release | 100% | `check_independent_product_readiness.py --fail-blocked` 통과 |

## 바로 실행할 작업 순서

1. EB receipt 4개에 실제 receipt URL/path 또는 formal hold evidence 연결
2. RH 3개 signed closure packet 경로와 status 회귀 검증
3. `validate_p1_evidence_intake_manifest.py --json --fail-open`으로 no-write promotion lint 통과
4. `build_p1_evidence_sidecar_updates.py --require-complete`로 sidecar 생성
5. `preflight_p1_evidence_sidecar_intake.py --json --fail-open` strict evidence gate 통과
6. `check_independent_product_readiness.py --fail-blocked`를 release promotion gate로 승격
7. 대형 generator를 renderer/decision/data transform/CLI로 계속 분리

## claim 가이드

현재 쓸 수 있는 표현:

- "Engineer-in-loop commercial assist ready"
- "반복 구조 검토/최적화 업무의 95-99% 가속을 목표로 하는 상용 보조툴"
- "핵심 P0 엔진 증거는 닫혔고, release/P1/evidence gate가 남아 있음"

아직 쓰면 안 되는 표현:

- "완전 자율 상용 구조설계툴"
- "구조기술사 검토 대체"
- "외부 benchmark로 검증 완료"
- "모든 실도면/인허가 상황에서 production ready"
