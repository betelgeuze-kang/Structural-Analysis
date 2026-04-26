# 프론트엔드 시각화 개선 계획

> 업데이트: 2026-04-12  
> 상태: **구현 기반은 갖춰졌고, 실무형 마감 작업이 남아 있음**

## 현재 상태 요약

프론트 시각화는 더 이상 "뷰어 부재" 단계가 아닙니다. 현재 저장소에는 artifact-driven 3D 뷰어, 차트, 최적화 이력, panel-zone 뷰어, SVG 도면 생성기, 그리고 generated single-file export 경로가 모두 존재합니다.

다만 현재 강점은 `viewer 존재 + artifact 연결 + 오프라인 실행 기반`이고, 남은 핵심 갭은 `대형 모델 성능`, `row-level provenance`, `shared selection 일관성`, `source viewer와 generated single-file viewer의 계약 정리`입니다.

## 구현 완료로 봐야 하는 항목

| 영역 | 현재 구현 상태 | 남은 핵심 갭 |
|---|---|---|
| 3D 구조 뷰어 | `src/structure-viewer/index.html`에 artifact/local payload/repo fallback, shared selection, deep-link, provenance, line-dominant 모델용 `InstancedMesh` 경로가 있음 | wall/slab까지 포함한 더 넓은 batching, LOD, decimation, hit-test 최적화 |
| 인터랙티브 차트 | `charts.html`은 artifact-driven 로더와 generated single-file 경로가 있음 | crosshair, zoom/pan, synced cursor, governing combo drill-down |
| 최적화 이력 차트 | `optimization_history.html`은 inline JSON -> local payload -> repo artifact -> demo fallback을 지원하고 실제 최적화 artifact를 읽음 | iteration-level tooltip/probe, constraint/source drill-down 강화 |
| Panel Zone 3D 뷰어 | `panel_zone.html`은 `panel_zone_*` artifact를 읽고 `artifact_vector_coords` / `artifact_world_coords` / `heuristic_proxy` 렌더링 경로를 모두 가짐. verified/topology-projected/proxy 상태 badge와 clearance/clash provenance도 UI에서 직접 표기함 | solver-verified 3D coverage 확대, richer row-level drill-down, section-cut UX |
| SVG 자동 도면 | `structural_svg_generator.py`는 plan/elevation/isometric, title block, dimension label lane 기반 충돌 회피를 이미 가짐 | sheet set/revision 관리, dimension 외 annotation collision 회피, callout, CAD round-trip |
| Self-contained export | generated single-file viewer 경로가 3D/charts/optimization-history/panel-zone에 존재 | source HTML 자체는 일부 여전히 repo-local vendor/sidecar를 기대하므로, source/export 계약을 더 명확히 문서화할 필요가 있음 |

## 정확히 정정해야 하는 부분

아래 표현은 현재 코드 기준으로 더 이상 맞지 않습니다.

- 3D WebGL 뷰어가 없다
- panel-zone 뷰어가 없다
- SVG가 placeholder 수준이다
- self-contained 경로가 없다
- instancing path가 아직 없다
- panel-zone이 vector-ready rendering path를 전혀 못 읽는다
- title block / collision avoidance가 미구현이다

대신 정확한 표현은 아래에 가깝습니다.

- 3D 뷰어는 이미 있고, line-heavy 모델 기준 instancing path가 들어가 있다.
- panel-zone 뷰어는 artifact-driven이며, 벡터 좌표를 직접 읽는 경로가 있다.
- SVG는 title block과 dimension label collision avoidance까지는 올라와 있다.
- generated artifact 기준 single-file viewer 경로는 존재한다.
- source viewer는 여전히 local vendor / sidecar 기반 오프라인 실행 경로를 유지하는 경우가 있다.

## single-file 상태

이 항목은 source viewer와 generated artifact를 분리해서 봐야 합니다.

- `index.html`, `panel_zone.html` 같은 source viewer는 repo-local `vendor`와 `.data.js` sidecar를 기대하는 경로가 남아 있습니다.
- 대신 generator가 만든 산출물은 vendor import와 payload를 inline해서 single-file HTML을 생성할 수 있습니다.
- 즉 현재 상태는 `source = repo-local offline`, `generated export = true single-file`로 구분하는 것이 정확합니다.

문서와 검증도 이 구분을 유지해야 합니다.

## panel-zone 관련 실제 수준

panel-zone은 "완전한 hardcoded demo"라고 보기 어렵고, 반대로 "항상 solver-verified 3D"라고 쓰는 것도 과장입니다.

- viewer는 `panel_zone_joint_geometry_3d`, `panel_zone_rebar_anchorage_3d`, `panel_zone_clash_verification_3d`, `panel_zone_clash_artifact`, `panel_zone_clash_report`를 읽습니다.
- geometry row에 `beam_axis_segment_m`, `column_axis_segment_m`, `*_rebar_segments_m`, `clash_points_m`가 있으면 1:1 vector layout을 그립니다.
- 그런 좌표가 부족하면 world coords 또는 proxy layout으로 내려갑니다.
- source contract 테스트는 missing source일 때 open skeleton도 허용하고, topology-projected bridge도 유효한 upstream source로 취급합니다.

따라서 남은 핵심은 "vector-ready path 추가"가 아니라, `solver-verified source coverage 확대`와 `clearance/clash provenance의 더 깊은 row-level drill-down`입니다.

## SVG 관련 실제 수준

SVG는 이미 CAD-like 방향으로 꽤 올라와 있습니다.

- title block field 추출과 렌더링이 있습니다.
- dimension text는 horizontal/vertical lane 할당으로 겹침을 줄입니다.
- plan/elevation/isometric가 실제 구조 데이터를 기반으로 생성됩니다.

하지만 아래는 여전히 다음 단계입니다.

- 도면 묶음(sheet set)과 revision lifecycle
- dimension 외 annotation/callout 충돌 회피
- section/detail callout
- DXF/DWG 왕복
- viewer와 SVG 간 deep-link

## 남은 우선순위

### P0

- source viewer와 generated single-file viewer의 계약을 문서와 테스트에서 일관되게 정리
- 3D / charts / panel-zone / optimization-history 간 shared selection과 provenance 표현을 같은 방식으로 맞춤
- row/member/load-case/combination 수준 provenance를 더 직접 표기

### P1

- 3D 뷰어의 instancing을 wall/slab 포함 wider batching으로 확대
- chart 탐색 UX 강화
- panel-zone solver-verified 3D source coverage 확대
- SVG의 revision/sheet/callout 계층 마감

## 다음 작업 묶음

### Batch A

- source/export single-file 계약을 각 viewer별로 표로 고정
- release artifact 기준 deep-link / provenance 라벨 명칭 통일

### Batch B

- `index.html`의 instancing path를 line-heavy 모델 밖으로 확장
- selection contract를 charts / panel-zone / optimization-history까지 동일 키로 정리

### Batch C

- `panel_zone.html`의 vector-ready path를 solver-verified source coverage와 직접 연결
- clash / anchorage / clearance row provenance를 UI에 노출
- verified / topology-projected / proxy fallback 상태를 source contract와 함께 명시

### Batch D

- `structural_svg_generator.py`의 title block / collision avoidance를 sheet-set/revision 단계로 확장
- SVG와 viewer 간 deep-link 계약 추가

## 한 줄 결론

프론트 시각화는 이미 "없는 기능을 새로 만드는 단계"를 지났습니다. 지금 남은 일은 `실제 artifact 기반 검토 도구로 마감하는 것`이며, 특히 `instancing 확장`, `panel-zone source fidelity`, `SVG 문서 마감`, `source vs generated single-file 계약 정리`가 핵심입니다.
