# 프론트엔드 시각화 다음 단계

> 업데이트: 2026-05-20
> 기준: 현재 repo 구현, project workspace/evidence hub, payload generator, viewer contract 테스트 기준

## 현재 기준선

이미 닫힌 항목은 다시 P0로 잡지 않습니다.

- 3D 구조 뷰어 존재
- charts / optimization history / panel-zone viewer 존재
- artifact-driven loader 존재
- generated single-file export 경로 존재
- 3D viewer의 instancing path 존재
- wall/slab surface instancing, surface LOD, BVH picking, pick-candidate cap은 `structure_viewer_performance_budget_manifest.json`의 static contract로 고정됨
- local browser performance smoke는 `structure_viewer_browser_performance_probe.json`으로 canvas ready 시간과 RAF cadence를 남김
- 11-case render mode/core/advanced workflow visual regression baseline은 `structure_viewer_visual_regression_baseline.json`으로 local canvas signature와 active workflow marker를 남김
- Structural Insight Viewer cockpit layer는 8개 analysis KPI, before/after optimization summary, drift contribution이 있는 critical member ranking, story-drift/load-step/material/heatmap chart strip, footer solver timeline, compact desktop chrome, stage-native lateral-load/support-marker overlay를 source viewer contract로 노출함
- panel-zone vector-ready rendering path 존재
- SVG title block / dimension collision avoidance 존재
- project workspace, review task, solver receipt, evidence ingest, commercial-tool crosswalk, lineage drilldown 존재
- SVG sheet/revision/callout/viewer deep-link가 `structure-viewer-drawing-sheet-package.v1`로 report/panel에 연결됨

지금부터의 일은 "뷰어를 만들기"가 아니라 "실무형 review surface로 닫기"입니다.

## 다음 우선순위

### 1. source viewer와 generated single-file viewer 계약 유지

기본 계약은 닫혔고, 이제 새 viewer 모듈을 추가할 때마다 source viewer와 generated single-file viewer의 의존성 차이가 다시 섞이지 않게 유지해야 합니다.

- source viewer는 대체로 repo-local `vendor`와 `.data.js` sidecar를 유지합니다.
- generated export는 payload와 vendor import를 inline한 single-file HTML 경로가 있습니다.
- 문서, 테스트, 배포 설명이 이 둘을 혼동하지 않도록 정리해야 합니다.

핵심 대상:

- `src/structure-viewer/index.html`
- `src/structure-viewer/panel_zone.html`
- `src/structure-viewer/charts.html`
- `src/structure-viewer/optimization_history.html`
- `implementation/phase1/generate_selfcontained_viewer.py`
- `implementation/phase1/generate_structure_viewer_payloads.py`

### 2. 3D viewer 성능 경로 확장

`index.html`에는 line-dominant 모델용 instancing path뿐 아니라 wall/slab surface instancing, surface LOD, BVH picking, pick-candidate cap까지 static contract가 있습니다. 또한 analysis cockpit layer가 KPI/optimization/critical-member/chart/timeline과 stage-native load/support overlay를 한 화면에 묶고, local browser probe가 canvas ready 시간과 RAF cadence를 남기며, 11-case render-mode/core/advanced workflow visual baseline이 local canvas signature와 active workflow marker를 비교합니다. 다음은 이 경로를 고객 하드웨어 매트릭스로 넓히는 일입니다.

- wall/slab batching static contract 유지
- 큰 모델용 LOD static contract 유지
- contour/deformed 모드에서의 비용 제어
- selection/hit-test 비용 축소의 고객 하드웨어 실측 budget 추가

핵심 메시지는 `instancing 도입`이 아니라 `local browser smoke에서 repeatable customer-hardware regression gate로 이동`입니다.

### 3. panel-zone을 vector-ready에서 solver-verified review surface로 승격

현재 panel-zone viewer는 실제 artifact를 읽고, vector segment / point array가 있으면 1:1로 렌더링합니다. 다만 source contract 기준으로는 topology-projected validated source와 open skeleton도 함께 존재할 수 있습니다.

남은 일:

- solver-verified source coverage 확대
- clearance / clash / anchorage provenance를 row-level deep-link까지 확장
- section-cut / detail drill-down
- proxy fallback이 활성화된 경우 그 사실을 더 명확히 표기

### 4. shared selection / provenance 계약 확장

3D source viewer는 shared selection, provenance, lineage drilldown, report deep-link 계약이 생겼습니다. 다음은 charts / panel-zone / optimization-history까지 같은 vocabulary를 더 넓히는 일입니다.

남은 일:

- `member`, `load_case`, `combination`, `focus_member` 키 정리
- 3D -> charts -> panel-zone -> optimization-history handoff 일치
- URL 공유와 row provenance 링크 규칙 통일

### 5. SVG sheet package 유지와 CAD 연계 검토

`structural_svg_generator.py`는 title block과 dimension label lane을 갖고 있고, source viewer는 선택 부재의 SVG sheet/revision/callout/deep-link를 report package로 남깁니다. 다음 단계는 이 계약을 CAD/export 흐름까지 확장하는 것입니다.

- multi-sheet metadata 유지
- revision lifecycle evidence 확장
- callout / annotation collision handling 확대
- SVG와 viewer 간 deep-link 회귀 테스트 유지
- DXF/DWG 연계 검토

## 문서상 주의할 표현

아래처럼 쓰는 것은 피합니다.

- "single-file viewer가 완전히 끝났다"
- "panel-zone이 완전한 verified 3D solver 결과만 렌더링한다"
- "SVG는 아직 placeholder다"
- "instancing은 아직 미구현이다"

대신 아래처럼 씁니다.

- "generated export 기준 single-file 경로가 있다"
- "panel-zone은 validated artifact vector path와 proxy fallback을 함께 가진다"
- "SVG는 title block / dimension collision avoidance까지는 구현돼 있다"
- "3D viewer에는 line-heavy 모델용 instancing path가 이미 있다"

## 바로 이어갈 실행 묶음

### Batch A

- source/export 계약 표 작성
- viewer별 single-file / offline / sidecar 의존 여부 명시

### Batch B

- `scripts/build_structure_viewer_performance_budget_manifest.py --json`으로 wall/slab/LOD/hit-test static budget을 유지
- `npm run verify:viewer-performance-probe`로 local browser probe를 유지
- `npm run verify:viewer-visual-regression`으로 11-case render-mode/core/advanced workflow visual baseline을 유지
- 큰 모델 기준 고객 하드웨어 FPS/interaction latency 측정 항목 추가

### Batch C

- panel-zone source provenance와 verified/proxy 상태를 UI에서 직접 표기
- source contract / source artifact / viewer 표시 문구를 맞춤
- row-level provenance를 results explorer deep-link와 더 직접 연결

### Batch D

- SVG sheet/revision/callout report package는 완료
- 다음은 review deep-link를 chart/panel-zone/optimization-history까지 같은 계약으로 확장

## 한 줄 결론

다음 단계의 본질은 `새 프론트 화면 추가`가 아니라, `이미 있는 viewer/export 경로를 실무형 계약으로 닫는 것`입니다.
