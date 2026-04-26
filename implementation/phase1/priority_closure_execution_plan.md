# 우선순위 기반 폐쇄 실행 계획 (Priority Closure Execution Plan)

작성일: `2026-04-11`

이 문서는 구조툴 교체 프로그램의 실행 순서를 정의한다. 달력 기반 주차, 스프린트, 분기 표기는 사용하지 않는다.
운영 규칙은 하나다. 가장 높은 우선순위 게이트를 닫고, 닫히는 즉시 다음 게이트를 연다.
병렬 작업은 현재 열려 있는 게이트 내부에서만 허용되며, 다음 게이트는 이전 게이트의 `Exit Gate`가 닫힌 뒤에만 시작한다.
현재 checked-in core gate 체인은 `steel/composite constitutive library`까지 `PASS`다.
MIDAS-KDS exact geometry bridge는 validator/workflow/CI/release/committee surface에서 full crosswalk closure가 완료되었고, release/committee summary propagation도 고정되어 compact structured contact/coupling surfacing이 solver breadth/workflow/release/committee로 올라가고 있다. 다음 active target은 core engine depth의 `compact structured contact/coupling surfacing`이다.
현재 release 경계의 `panel_zone external validation`은 `external_validation_only` advisory external audit boundary이며 submission blocker는 아니다. summary propagation이 고정된 뒤의 다음 active target도 core engine depth의 `compact structured contact/coupling surfacing`이다.

## 0) 운영 규칙

- 단일 오픈 게이트 원칙을 따른다.
- 게이트 실패 시 같은 항목을 수정하고 재검증한다.
- 증빙은 `implementation/phase1/*_report.*`, `release/*`, `docs/*`에 남긴다.
- 새 기능은 실무 폐쇄에 직접 연결되지 않으면 후순위로 미룬다.
- `MIDAS exact roundtrip` 폐쇄 범위에서는 intentional optimized writeback과 parser-drop fixture를 예외로 둔다.
- 이 계획은 "문서상의 일정"이 아니라 "닫힘 기준"만 가진 실행 기록이다.

## 1) 10개 실무 백로그

각 항목은 위에서 아래로 순서대로 닫는다. 위 항목이 닫히면 즉시 다음 항목을 연다.

| 순번 | 우선순위 | 백로그 | Exit Gate | 다음 |
| --- | --- | --- | --- | --- |
| 1 | P0 | MIDAS-KDS exact geometry bridge | review snapshot, member, section, and load mapping이 validator/workflow/CI/release/committee full-crosswalk PASS로 닫혔다. | 2 |
| 2 | P0 | RC constitutive library | hysteresis correlation `>= 0.95`, residual drift `<= 5%`, crack/crushing onset mismatch `<= 1 step`이다. | 3 |
| 3 | P0 | steel/composite constitutive library | cyclic response, stiffness degradation, connector slip이 reference test 허용오차 안에 들어오고 bond-slip interface가 분리된다. | 4 |
| 4 | P0 | beam-column/fiber engine | force-based/displacement-based/corotational member response가 holdout 기준 drift/base shear/member force error `<= 5%`로 맞는다. | 5 |
| 5 | P0 | shell/wall/slab engine | local demand error가 `<= 7%`이고 mesh sensitivity가 안정적이며 diaphragm coupling이 유지된다. | 6 |
| 6 | P1 | foundation/contact/device library | chronology mismatch가 `0`이고 hysteresis correlation `>= 0.95`, impedance fit `R^2 >= 0.95`이다. | 7 |
| 7 | P1 | nonlinear solver control | cutback/line search/arc-length/event handling이 severe-softening 및 contact 사례를 수동 튜닝 없이 통과한다. | 8 |
| 8 | P1 | benchmark/validation breadth | cross-tool holdout MAPE `<= 5%`, provenance complete, coverage counts met이다. | 9 |
| 9 | P2 | design report/results explorer | model -> solve -> report -> review 루프가 traceable하고 deep-linkable하다. | 10 |
| 10 | P2 | batch ops / rerun / audit trail | signed package, queued rerun, and reproducible audit trail이 batch-safe하게 이어진다. | 완료 |

P0 항목이 닫히기 전에는 P1/P2를 시작하지 않는다. P1 항목이 닫히기 전에는 P2를 시작하지 않는다. 현재 release/roundtrip/load-combination은 baseline으로 유지하고, exact geometry / contact / workflow slice는 live reports에서 closed 상태다. geometry bridge의 validator/workflow/CI/release/committee surface는 `full_member_crosswalk=242/242 PASS`, `full_section_crosswalk=200/200 PASS`, `full_load_crosswalk=51/51 PASS`로 정규화되었다. 다음 active target은 core engine depth의 `compact structured contact/coupling surfacing`이다.

- Closed slices: `MIDAS-KDS exact geometry bridge`, `structural contact / foundation-device`, `workflow/interoperability productization`
- Next active gate: `compact structured contact/coupling surfacing` within core engine depth

## 1-1) 현재 증빙 출처

- 원천 입력: `implementation/phase1/open_data/midas/midas_native_corpus_manifest.json`, `implementation/phase1/release/midas_native_roundtrip/midas_native_writeback_diff_receipts_report.json`
- gate 산출물: `implementation/phase1/midas_native_roundtrip_gate_report.json`, `implementation/phase1/midas_interoperability_gate_report.json`, `implementation/phase1/midas_exact_roundtrip_closure_gate_report.json`
- 보조 release 산출물: `implementation/phase1/release/midas_native_roundtrip/exact_topology_structural_preview_promotion_queue.json`, `implementation/phase1/release/midas_native_roundtrip/unsupported_lossy_card_family_appendix.md`
- 롤업/공유 본문: `implementation/phase1/ci_gate_report.json`, `implementation/phase1/release/release_gap_report.json`

## 1-2) 현재 MIDAS exact roundtrip 상태

- `run_midas_native_roundtrip_gate`: `PASS`
  `ready=35/35`, `receipts=35/35`, `topology=35/35`, `load=35/35`, `loadcomb=35/35`, `exact_queue=0/8`
- `run_midas_interoperability_gate`: `PASS`
  `bounded_subset=full_exact_roundtrip`, `remaining_limits=[]`, `exact_closure=closed`
- `run_midas_exact_roundtrip_closure_gate`: `PASS`
  `exact=33/33`, `canonical=0`, `lossy=0`, `unsupported=0`, `pending_review=0`, `scope_excluded=2`, `limits=[]`
- `MIDAS-KDS geometry bridge`: `PASS`
  `load_crosswalk=36/36`, `semantic_crosswalk=36/36`, `full_member_crosswalk=242/242 PASS`, `full_section_crosswalk=200/200 PASS`, `full_load_crosswalk=51/51 PASS`, `full_crosswalk_depth=36`, `geometry_diff=36/36 PASS`
  이 집계는 validator/workflow/CI/release/committee surface에서 같은 full-crosswalk 기준으로 정규화되었다.
- 현재 해석:
  closure scope 안의 canonical 대상은 모두 exact fidelity로 닫혔다. scope 밖 예외는 intentional optimized writeback 1건과 parser-drop fixture 1건뿐이다.
- `Support search`: `PASS`
  `support_search=9`, `node_surface_proxy=5`, `support_depth=21`
- `Element/material breadth`: `PASS`
  `contact=full_structural_contact`, `support=15(contact=6,foundation=4,device=5)`, `materials=2(rc_composite,steel_elastic_plastic)`, `links=6(bearing_bilinear,compression_only_penalty,coulomb_friction,kelvin_voigt_pounding,normal_gap_unilateral,uplift_seat_unilateral)`
- `NDTHA material depth`: `3`
  `material_model=rc_composite`, `material_model_pass=3/3`
- `run_load_combination_engine_gate`: `PASS`
  `family=KDS-2022-steel-gravity`, `exact_roundtrip=3/3`, `pattern_coverage=3/3 min=1.00`, `kds_strength_avg=1.000`, `kds_service_avg=1.000`, `gaps=none`
- `NDTHA step-series depth`: `2400`
- 최근 폐쇄 게이트:
  `run_steel_composite_constitutive_gate.py` 기준 `steel=12/12`, `composite=8/8`, `steel_cases=4`, `composite_cases=4`, `source=constitutive_library_benchmarks`
- 현재 release 경계:
  `panel_zone_external_validation_pending=True`, `panel_zone_internal_engine_complete=True`, `panel_zone_validation_boundary=external_validation_only`
- 즉시 확인해야 할 항목:
  core engine depth의 `compact structured contact/coupling surfacing`을 다음 활성 게이트로 연다.

## 2) MIDAS replacement sequence

MIDAS 대체는 아래 순서로 닫는다. 이 순서 역시 주차형이 아니라 게이트형이다.

| 단계 | 내용 | Exit Gate |
| --- | --- | --- |
| 1 | `Reader + canonical corpus` | `.mgt` / native export를 canonical JSON/NPZ로 받아들이고, 표준 샘플셋을 안정적으로 읽는다. |
| 2 | `Exact geometry bridge` | geometry, member, section, load mapping이 exact하게 연결된다. |
| 3 | `Load-combination + code-check companion` | 조합식과 governing clause가 원본 입력으로 trace되고, orphan combo가 없다. |
| 4 | `Native writeback + raw recovery cleanup` | bounded subset 안에서 heuristic raw recovery가 제거되고 normalized factor map / primitive load card / summary grade가 exact closure 기준을 만족한다. |
| 5 | `Review workspace + batch ops` | review package, change log, rerun, audit trail이 한 흐름으로 이어진다. |
| 6 | `Full replacement` | 한 프로젝트가 sidecar repair 없이 open -> edit -> analyze -> report -> export로 닫힌다. |

핵심 규칙은 같다. 1번이 닫히면 2번을 열고, 2번이 닫히면 3번을 연다. 중간 단계를 건너뛰지 않는다.

## 3) Abaqus/OpenSees core-engine gap map

아래 표는 현재 코어 엔진이 상용툴과 비교해 어디가 비어 있는지를 정리한 것이다.
OpenSees와는 "범용 비선형 부재/요소/재료의 폭"에서, Abaqus와는 "contact, continuum, solver robustness, element zoo"에서 더 큰 격차가 남아 있다.

| 축 | OpenSees gap | Abaqus gap | Exit Gate |
| --- | --- | --- | --- |
| Material models | reduced-order RC/fiber helpers는 있지만, 일반 RC/steel/composite constitutive breadth가 부족하다. | continuum-grade cyclic damage, connector slip, path-dependent material law가 부족하다. | hysteresis correlation `>= 0.95`, residual drift/slip `<= 5%`, crack/crushing onset mismatch `<= 1 step` |
| Beam-column elements | story-level reduced element는 있으나 force-based / displacement-based / corotational family가 필요하다. | member type별 element zoo와 nonlinear response breadth가 부족하다. | global drift/base shear/member force error `<= 5%` |
| Shell/wall/slab | layered shell / wall / slab support가 섹션 보조 수준에 머문다. | continuum/shell breadth와 안정적 coupling이 부족하다. | local demand error `<= 7%`, mesh sensitivity stable, diaphragm coupling preserved |
| Contact/foundation/device | scalar gap/uplift/friction baseline은 있으나 surface contact, p-y/t-z/q-z, device family가 부족하다. | general contact search, penalty/augmented Lagrange, surface interaction robustness가 부족하다. | chronology mismatch `= 0`, hysteresis correlation `>= 0.95`, impedance fit `R^2 >= 0.95` |
| Solver control | adaptive Newton/LM 유틸은 있으나 cutback, arc-length, event handling이 부족하다. | severe-softening, contact, staged activation을 견디는 convergence stack이 부족하다. | canonical nonlinear cases converge without manual damping tuning |
| Validation breadth | 내부 gate와 선택 holdout은 있으나 cross-tool benchmark breadth가 더 필요하다. | cross-tool traceability와 benchmark archive depth가 더 필요하다. | cross-tool holdout MAPE `<= 5%`, provenance complete, coverage counts met |

## 4) 게이트 전환 규칙

- 현재 열려 있는 게이트만 작업한다.
- `Exit Gate`가 닫히면 그 항목만 merge하고 즉시 다음 항목을 연다.
- 다음 항목을 미리 설계할 수는 있지만, 구현 착수는 현재 게이트가 닫힌 뒤에만 한다.
- 하드 구현과 소프트 구현은 같은 게이트 안에서 병렬화할 수 있다.
- 게이트를 닫는 기준은 "좋아 보임"이 아니라 수치/산출물/재현성 증빙이다.

## 5) 현재 프로그램의 해석

이 프로그램은 상용툴을 한 번에 대체하는 문서가 아니다.  
먼저 release/committee 체인을 안정화하고, 그다음 MIDAS exact roundtrip을 닫고, 이어서 재료/요소/solver gap을 닫아간다.  
마지막에야 report, review, batch ops가 결합되어 실무 대체 루프가 완성된다.

## 6) 다음 명령

```bash
python implementation/phase1/run_midas_interoperability_gate.py \
  --out implementation/phase1/midas_interoperability_gate_report.json

python implementation/phase1/run_midas_exact_roundtrip_closure_gate.py \
  --native-roundtrip-report implementation/phase1/midas_native_roundtrip_gate_report.json \
  --interoperability-report implementation/phase1/midas_interoperability_gate_report.json \
  --out implementation/phase1/midas_exact_roundtrip_closure_gate_report.json
```

실행 순서는 아래처럼 유지한다.

1. exact roundtrip, load-combination, geometry bridge, RC, steel/composite constitutive 산출물을 기준선으로 고정한다.
2. release 경계의 `panel_zone external validation` advisory external audit boundary는 더 이상 다음 활성 게이트가 아니며, core engine depth의 `compact structured contact/coupling surfacing`을 solver breadth/workflow/release/committee로 올린다.
3. 별도 외부 intake가 없으면 최신 `ci_gate_report.json` / `release_gap_report.json`의 첫 non-green 항목을 core engine depth의 `compact structured contact/coupling surfacing` 기준으로 다시 연다.
