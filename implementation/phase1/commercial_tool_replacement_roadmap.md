# 상용툴 대체 로드맵

생성일: `2026-03-10`

## 목적

이 문서는 현재 `Phase 1` 아키텍처가 내부 게이트 기준으로는 녹색 상태에 도달했더라도, MIDAS/ETABS/SAP2000/OpenSees 계열 상용 구조해석 툴의 기능 범위를 실제로 대체하려면 어떤 작업이 더 필요한지를 정리한 실행 로드맵이다.

중요한 전제는 다음과 같다.

- [release_gap_report.json](release/release_gap_report.json)의 `P0/P1/P2=0`은 현재 정의된 내부 검증 게이트가 닫혔다는 뜻이다.
- 이것은 곧바로 "상용툴 기능 범위 전체 대체 완료"를 의미하지 않는다.
- 상용 대체의 기준은 `고속 솔버` 하나가 아니라 `재료모델 + 요소기술 + 설계후처리 + 입력/출력 워크플로우` 전체다.

## 실행 규칙

- 이 문서는 달력 기반 일정이 아니라 `닫힘 기준` 기반 실행 문서다.
- 각 축의 `검증 기준`이 닫히면 다음 축으로 이동한다.
- 12개 세부 백로그는 축 1~5로 묶어 운영한다.

## 현재 기준선

현재 구현에서 이미 확보된 축은 다음과 같다.

- `GPU main-loop contract`: [run_solver_hip_e2e_contract.py](run_solver_hip_e2e_contract.py)
- `RC benchmark lock`: [run_rc_benchmark_lock_gate.py](run_rc_benchmark_lock_gate.py)
- `MIDAS parser / corpus`: [parse_midas_mgt_to_json_npz.py](parse_midas_mgt_to_json_npz.py), [collect_mgt_quality_corpus.py](collect_mgt_quality_corpus.py)
- `MIDAS exact roundtrip closure`: `PASS`
  `run_midas_native_roundtrip_gate` 기준 `ready=35/35`, `receipts=35/35`, `topology=35/35`, `load=35/35`, `loadcomb=35/35 exact`, `exact_queue=0/8`
  `run_midas_exact_roundtrip_closure_gate` 기준 `exact=33/33`, `canonical=0`, `lossy=0`, `unsupported=0`, `pending_review=0`, `scope_excluded=2`, `limits=none`
- `load-combination engine`: `PASS`
  `family=KDS-2022-steel-gravity`, `exact_roundtrip=3/3`, `pattern_coverage=3/3 min=1.00`, `kds_strength_avg=1.000`, `kds_service_avg=1.000`, `gaps=none`
- `KDS compliance package`: [code_check_engine.py](code_check_engine.py), [generate_kds_compliance_report.py](generate_kds_compliance_report.py)
- `비선형 프레임/NDTHA`: [run_nonlinear_frame_engine_validation.py](run_nonlinear_frame_engine_validation.py), [run_nonlinear_ndtha_stress.py](run_nonlinear_ndtha_stress.py)
- `풍하중/SSI/댐퍼/시공단계/유연다이아프램`: [dynamics-boundary-contract.md](dynamics-boundary-contract.md)와 관련 gate 러너들
- `MIDAS-KDS exact geometry bridge`: [validate_midas_kds_geometry_bridge_artifacts.py](validate_midas_kds_geometry_bridge_artifacts.py), [build_kds_geometry_bridge_registry.py](build_kds_geometry_bridge_registry.py)
- `Structural contact / foundation-device / element-material breadth`: [run_structural_contact_gate.py](run_structural_contact_gate.py), [run_foundation_soil_link_gate.py](run_foundation_soil_link_gate.py), [run_element_material_breadth_gate.py](run_element_material_breadth_gate.py)
- `Workflow/interoperability productization`: [run_workflow_productization_gate.py](run_workflow_productization_gate.py), [generate_structural_optimization_visualization_viewer.py](generate_structural_optimization_visualization_viewer.py)

현재 checked-in core gate 체인은 `MIDAS-KDS exact geometry bridge`, `structural contact / foundation-device / element-material breadth`, `workflow/interoperability productization`, `steel/composite constitutive library`까지 `PASS`다. `MIDAS-KDS exact geometry bridge`는 validator/workflow/CI/release/committee surface에서 full-crosswalk PASS로 닫혔고, release/committee summary propagation이 고정되어 `compact structured contact/coupling surfacing`이 solver breadth/workflow/release/committee rollup에 반영된다. 다음 active target은 core engine depth의 `compact structured contact/coupling surfacing`이다.

- `MIDAS-KDS exact geometry bridge`는 live JSON/committee/release surface에서 `load_crosswalk=36/36`, `semantic_crosswalk=36/36`, `full_member_crosswalk=242/242 PASS`, `full_section_crosswalk=200/200 PASS`, `full_load_crosswalk=51/51 PASS`, `full_crosswalk_depth=36`, `geometry_diff=36/36 PASS`로 읽는다.
- `structural contact / foundation-device / element-material breadth`는 live surface에서 `support_search=9 | node_surface_proxy=5 | support_depth=21`, `support=15(contact=6,foundation=4,device=5)`, `materials=2(rc_composite,steel_elastic_plastic)`까지 함께 본다.
- `비선형 프레임/NDTHA`는 live surface에서 `ndtha_step_series_depth=2400`과 `ndtha_material_depth=3`를 함께 본다.

- Next active gate: `compact structured contact/coupling surfacing` within solver breadth/workflow/release/committee. summary propagation이 고정된 뒤에 여는 실무 핵심 축이다.

현재 live reports에서는 1~5번 축과 geometry/contact/workflow 관련 surface가 이미 PASS다. 아래 10개 목록은 open work queue가 아니라 closure order를 기록한 것이다.

## 다음 10개 구현 타겟

현재 live 상태를 기준으로, 다음 구현 타겟은 아래 10개로 고정한다.

1. `beam-column / fiber engine`를 force-based/displacement-based/corotational member response 기준으로 assembled FE 요소 수준에 맞춘다.
2. `shell / wall / slab engine`를 local demand, mesh sensitivity, diaphragm coupling 기준으로 assembled FE 요소 수준에 맞춘다.
3. `contact / material integration`을 foundation, device, cyclic material state와 함께 묶어 core engine depth를 닫는다.
4. `RC cyclic backbone`과 `bond-slip interface`를 실체화해 concrete crushing, pinching, degradation을 history state로 다룬다.
5. `steel / composite constitutive`를 현재 reduced-order 계열과 분리해 전용 library 단위로 정리한다.
6. `foundation / contact / device / staged-construction / results-explorer`를 한 묶음으로 연결해 실무 파일럿 운영 흐름을 닫는다.
7. `load-combination engine`을 KDS steel gravity slice 밖으로 확장해 RC, wind, seismic, nested combo까지 family-aware로 일반화한다.
8. `benchmark / validation breadth`를 release/committee 산출물에 정식 반영해 authority vs external coverage 차이를 숫자로 고정한다.
9. `design report / results explorer`를 model -> solve -> report -> review로 traceable하게 묶는다.
10. `batch ops / rerun / audit trail`을 signed package, queued rerun, reproducible audit trail 기준으로 닫는다.

## 축 1. 재료모델 실체화

### 현재 상태

- [rc_composite_material_model.py](rc_composite_material_model.py)는 `cracking`, `bond-slip`, `creep`, `confinement`를 스토리 수준 보정 인자로 반영한다.
- [nonlinear_lj_hinge_kernel.py](nonlinear_lj_hinge_kernel.py)는 surrogate hinge 계열이다.
- [kbc_md_material_parser.py](kbc_md_material_parser.py)와 [material_rule_table.json](material_rule_table.json)은 입력 물성 매핑 레이어다.

### 부족한 점

- RC 응력-변형률 이력모델이 없다.
- 콘크리트 압괴, 인장균열, pinching, cyclic stiffness degradation이 없다.
- 철근 Bauschinger, bar buckling, 저주기 피로가 없다.
- bond-slip이 인터페이스 요소가 아니라 보정치 중심이다.
- creep/shrinkage가 history state가 아니라 축약 계수 중심이다.
- SRC/CFT/합성보/전단연결재 모델이 없다.

### 구현 작업

1. `rc_constitutive_library.py`
   - confined / unconfined concrete
   - tension softening
   - compression softening / crushing
   - cyclic unloading / reloading
   - pinching / strength deterioration
2. `steel_constitutive_library.py`
   - bilinear / multilinear hardening
   - isotropic + kinematic hardening
   - local buckling / fracture proxy
3. `bond_slip_interface.py`
   - 철근-콘크리트 부착 슬립 전용 link / spring
4. `composite_constitutive_library.py`
   - SRC, CFT, composite beam, shear connector slip

### 검증 기준

- authority cyclic test set 기준 `hysteresis correlation >= 0.95`
- residual drift / residual slip error `<= 5%`
- creep / shrinkage long-term deflection error `<= 5%`
- crack onset / crushing onset step mismatch `<= 1 step`

### 우선순위

- `P0`
- 닫히면 다음 축: 축 2

## 축 2. 범용 비선형 요소기술 확대

### 현재 상태

- [run_nonlinear_frame_engine_validation.py](run_nonlinear_frame_engine_validation.py)는 story-level reduced model 성격이 강하다.
- [rust_nonlinear_frame_bridge.py](rust_nonlinear_frame_bridge.py)는 GPU main-loop contract는 확보했지만, 범용 FE 요소 라이브러리 수준의 폭은 아직 아니다.

### 부족한 점

- force-based / displacement-based nonlinear beam-column 일반화 부족
- fiber section 기반 일반 부재 해석 부족
- layered shell / wall / slab 요소 부족
- general structural-contact benchmark breadth and FE coupling depth still need expansion beyond the implemented special-link baseline
- pile / foundation / soil spring 계열 부족

### 구현 작업

1. `beam_column_nonlinear.py`
   - force-based beam-column
   - displacement-based beam-column
   - corotational geometry
2. `fiber_section.py`
   - RC / steel / composite section fiber integration
3. `layered_shell_wall.py`
   - slab / wall / core wall layered section
   - membrane + bending coupling
4. `special_link_library.py`
   - implemented baseline nonlinear links for gap
   - implemented baseline nonlinear links for uplift
   - implemented baseline nonlinear links for compression-only
   - implemented baseline nonlinear links for bearing
   - implemented baseline nonlinear links for friction
   - implemented baseline nonlinear links for pounding
5. `foundation_link_library.py`
   - p-y, t-z, q-z, pile head spring

### 검증 기준

- OpenSees holdout 대비 global drift / base shear / modal metrics `<= 5%`
- member force field error `<= 5%`
- shell / wall local demand metric error `<= 7%`
- contact-uplift chronology mismatch count `0`

### 우선순위

- `P0`
- 닫히면 다음 축: 축 3

## 축 3. 설계 코드 체크 엔진 확대

### 현재 상태

- [code_check_engine.py](code_check_engine.py)는 strength / interaction / serviceability / stability를 포함한다.
- [generate_kds_compliance_report.py](generate_kds_compliance_report.py)는 제출용 패키지를 생성한다.

### 부족한 점

- 현재 범위는 `focused compliance slice`에 가깝다.
- RC 부재 상세 설계가 부족하다.
- slab / wall / foundation / connection check가 얕다.
- 하중 조합 생성기가 상용툴 수준으로 넓지 않다.
- section redesign / reinforcement suggestion loop가 없다.

### 구현 작업

1. `kds_steel_rule_engine.py`
   - beam / column / brace / panel-zone / connection
2. `kds_rc_rule_engine.py`
   - beam / column / wall / slab / foundation
   - punching / shear friction / boundary element
3. `load_combination_engine.py`
   - KDS / ACI / AISC edition별 자동 조합
4. `design_report_book.py`
   - governing clause
   - DCR table
   - NG grouping
   - report export
5. `section_optimizer.py`
   - 단면 증분 / 배근량 제안

### 검증 기준

- compliance row count `>= 5,000`
- member check count `>= 1,000`
- member family `>= 8`
- governing clause traceability `100%`
- external design sheet diff `<= 5%`

### 우선순위

- `P0`
- 닫히면 다음 축: 축 4

## 축 4. 현실 하중/특수장치/인프라 확장

### 현재 상태

- 풍하중, SSI, damper, construction sequence, flexible diaphragm gate는 이미 있다.
- 철도/터널 축도 [track_lf_solver.py](track_lf_solver.py), [soil_tunnel_ssi.py](soil_tunnel_ssi.py), [vti_coupled_solver.py](vti_coupled_solver.py), [tunnel_graph_converter.py](tunnel_graph_converter.py) 등으로 연결되어 있다.

### 부족한 점

- TMD / base isolation / friction pendulum / viscoelastic damper 계열 일반화 부족
- 풍동실험 데이터 매핑 및 거주성 평가 체계 부족
- layered soil / pile group / frequency-dependent SSI 강화 필요
- prestress / tendon / cable / staged activation 확장 필요
- 철도/터널 분야도 상용 수준 후처리와 설계 검토는 아직 약하다

### 구현 작업

1. `device_library.py`
   - viscous, viscoelastic, friction pendulum, lead-rubber, TMD
2. `wind_workflow.py`
   - code wind + tunnel mapping + occupant comfort
3. `advanced_ssi.py`
   - layered soil impedance
   - pile group interaction
4. `construction_stage_engine.py`
   - tendon / prestress / cable / staged activation
5. `rail_tunnel_postprocess.py`
   - vibration compliance
   - serviceability / maintenance indicators

### 검증 기준

- wind acceleration / drift / base moment error `<= 5%`
- SSI impedance curve fit `R^2 >= 0.95`
- device hysteresis correlation `>= 0.95`
- staged construction camber / shortening error `<= 5%`

### 우선순위

- `P1`
- 닫히면 다음 축: 축 5

## 축 5. 상용툴 워크플로우와 제품화

### 현재 상태

- MIDAS 파서, release registry, committee package, external submission 패키지는 이미 존재한다.

### 부족한 점

- 모델 작성기와 단면 라이브러리 UI가 부족하다.
- 결과 탐색기가 상용툴 수준으로 넓지 않다.
- IFC/BIM/ETABS/OpenSees/MIDAS round-trip interoperability가 부족하다.
- 프로젝트 승인 / 감사 로그 / 재현성 운영 흐름이 로컬 중심이다.

### 구현 작업

1. `interoperability_gateway.py`
   - MIDAS / ETABS / OpenSees / IFC import-export
2. `section_library_and_mesher.py`
   - section DB
   - meshing
   - load pattern editor
   - embedded metadata validator
   - representative-member focus flow
3. `results_explorer`
   - contour, mode shape, time-history viewer, envelope explorer
4. `project_registry_service.py`
   - signed project package
   - audit log
   - approval workflow
5. `batch_job_runner.py`
   - multi-case job queue
   - rerun / snapshot management

### 검증 기준

- import/export round-trip geometry diff `0`
- analysis result diff after round-trip `<= 2%`
- signed package reproducibility `100%`
- project audit trail completeness `100%`

### 우선순위

- `P1`~`P2`
- 닫히면 다음 단계: release / committee / batch 운영 안정화

## 구현 순서

실행 순서는 다음으로 고정한다. 각 축이 닫히면 다음 축으로 이동한다.

현재 위치는 이 순서 안에서 core CI gate 체인을 `steel/composite constitutive library`까지 닫은 상태다. 다음 실무 경계는 core engine depth이며, 첫 활성 게이트는 `compact structured contact/coupling surfacing through solver breadth/workflow/release/committee`이다.

1. `재료모델 실체화`
2. `범용 비선형 요소기술 확대`
3. `설계 코드 체크 엔진 확대`
4. `현실 하중/특수장치/인프라 확장`
5. `워크플로우/제품화`

이 순서가 맞는 이유는 간단하다.

- 재료모델이 없으면 정확도가 무너진다.
- 요소기술이 부족하면 범용 모델을 못 푼다.
- 코드체크가 약하면 현업 도장을 못 받는다.
- 이후 특수장치/인프라/워크플로우는 범위 확장과 제품성 문제다.

## 단계별 완료 정의

### Stage 1

- RC / steel / composite constitutive library 추가
- cyclic benchmark gate 추가
- authority dataset lock

### Stage 2

- fiber beam-column + layered shell/wall 추가
- shell / wall / slab local metric gate 추가

### Stage 3

- KDS steel / RC rule engine 확대
- load combination engine 일반화
- design report book 생성

### Stage 4

- device / wind / advanced SSI / staged construction 확장
- railway / tunnel postprocess 확장

### Stage 5

- import/export round-trip
- results explorer
- signed project registry service

## 권장 산출물

각 축이 구현될 때마다 아래 산출물을 같이 고정한다.

- `*_report.json`
- `*_contract_report.json`
- `*_gate_report.json`
- `authority benchmark manifest`
- `committee / external submission package`

## 다음 액션

지금 바로 착수할 작업은 다음 3개다.

1. `run_steel_composite_constitutive_gate.py` 기준선(`steel=12/12`, `composite=8/8`)을 고정한다.
2. core engine depth의 `compact structured contact/coupling surfacing`을 다음 활성 게이트로 연다.
3. 별도 release intake가 없다면 최신 `ci_gate_report.json` / `release_gap_report.json`에서 core engine depth의 `compact structured contact/coupling surfacing` 기준의 첫 non-green 항목을 다시 연다.
