# 해석엔진·AI·도면비교 상용화 갭 분석 (구현 대기 문서)

> 작성일: 2026-05-30
> 상태: **진행 중** (`/loop` 백로그 — 2026-05-30 갱신)
> 범위: (1) 기존↔최적화 도면 차이 시각화, (2) 구조해석 엔진 상용화 갭, (3) AI/최적화 엔진 상용화 갭
> Claim 경계: 본 문서의 어떤 항목도 *engineer-in-loop* 경계를 넘지 않는다. 구조기술사 검토 대체/인허가 자동승인은 계속 금지 claim.

---

## 0. 제품 맥락 (확정)

- **타깃 하드웨어**: 단일 워크스테이션 — AMD Radeon RX 6900XT(Navi 21, ROCm/HIP), Ryzen 9 5900X, 32GB RAM
  - 근거: `implementation/phase1/workstation_hardware_profile.json`
- **제품 워크플로**: 도면 데이터 입력 → 비선형 해석 → 도면/단면 최적화(cost 감소) → **최적화 도면 납품**
- **납품물 핵심**: "기존 도면 대비 최적화 도면의 차이"를 발주자/검토 엔지니어에게 **명확하게 증명**하는 것

---

## 1. 기존↔최적화 도면 차이 시각화

### 1.1 현재 구현 상태 (사실)

| 요소 | 구현 | 위치 |
|------|------|------|
| Variant 토글 (Baseline/Optimized/Compare) | 있음 — variant별 **artifact 재로딩** | `index.html` `setProjectWorkspaceVariant` (~17078), `navigateProjectWorkspace` |
| 멤버 단위 before/after 표 | 있음 — section/weight/cost delta | `viewer-member-comparison-model.js` |
| Manifest 멤버 수 delta | 있음 — `baseline_member_count → optimized_member_count` | 동 파일 70–86 |
| 오버레이 하이라이트 필터 | 있음 — changed / reduced / risk-up / retained | `index.html` `setMemberComparisonFilter` (~17389), variant 툴바 |
| 최적화 delta strip (정량 타일) | 있음 — 절감량 타일 | `optimization-delta-strip` |
| Compare(고스트) | 있음 — **변형형상 고스트** (원형 vs 변형), before/after와 **다른 개념** | `toggleDeformed`, "Neutral ghost" |

### 1.2 핵심 갭 — "차이가 명확히 안 보인다"

현재 "차이"는 대부분 **데이터 표 + 멤버 색상 하이라이트**로만 표현된다. 상용 납품 관점에서 부족한 점:

1. **진짜 시각적 before/after 부재**
   - baseline과 optimized **두 모델을 동시에 보여주는 동기화 듀얼 뷰포트**(좌/우 또는 슬라이더 와이프)가 없음
   - variant=compare는 사실상 **한 모델만 교체 로딩** + 하이라이트일 뿐, 두 형상을 겹쳐/나란히 비교하지 않음
2. **지오메트리 diff 시각화 부재**
   - 단면 크기 축소(예: H-400→H-350)가 3D에서 **굵기/부피 변화로 직접 보이지 않음**
   - 제거/병합된 부재(`group_merge`, member count 감소)가 공간적으로 어디서 빠졌는지 표시 약함
3. **정량 증거와 3D의 연결 약함**
   - delta 표의 "강재 −12%"가 화면의 어느 부재 집합에서 왔는지 클릭 연동/누적 집계가 약함
4. **납품용 비교 리포트 부재**
   - 발주자에게 줄 **before/after 비교 시트(PDF/HTML)**: 물량표, 단면 변경 목록, 비용 절감 근거, 안전 여유(DCR) 유지 증거가 한 장으로 정리되지 않음
5. **안전성 유지의 시각적 증거 약함**
   - "비용은 줄었지만 DCR/drift는 한도 내"라는 점을 **before/after 컨투어 동시 비교**로 보여주지 못함

### 1.3 개선 방향 (클로저 트래커)

> 우선순위 P = 납품 임팩트 기준

| ID | 항목 | 상태 | 구현 메모 |
|----|------|------|-----------|
| P1-a | 동기화 비교 뷰 (와이프) | **완료** | `variant=compare` + baseline ghost + clip-plane wipe; URL `variant` cold-load 동기화 (`getWorkspaceVariantToken`, `syncWorkspaceVariantFromUrl`). 좌/우 듀얼 뷰포트는 미구현(와이프로 대체) |
| P1-b | 단면 변화 3D 인코딩 | **완료** | `section_id` diff → 반경 스케일·톤; **제거 부재** baseline 위치 마커 (`buildComparisonRemovedMarkers`) |
| P1-c | before/after 컨투어 동시 비교 | **완료** | Compare+Contour linked scale·dual legend; DCR hydrate **전 조합 병합** (`buildElementDcrMapAllCombinations`) |
| P2-a | delta 패널 ↔ 3D 양방향 | **완료** | delta tile·member row·stage chip → timeline step + 3D; `design_optimization_group_member_index.json` exact group→member (`buildTimelineHighlightsWithGroupIndex`) |
| P2-b | 납품용 비교 리포트 | **완료** | Delivery Comparison Sheet + timeline rows; **Compare Report** HTML export (`exportDrawingComparisonSheet`). PDF 자동 납품은 `scripts/export-structure-viewer-report-pdf.mjs` 별도 |
| P3 | 변경 타임라인 재생 | **완료** | Compare scrubber·누적 Δcost/DCR/drift·story clip; **rebar/thickness morph proxy** on optimized mesh (`activeOptimizationMorphByElementId`) |

### 1.4 데이터 전제 (클로저)

| 항목 | 상태 | 구현 메모 |
|------|------|-----------|
| member_id 정렬 | **완료** | `build_optimization_member_alignment.py` → `member_alignment` on changes JSON (`enrich_optimization_changes_contract.py`) |
| removed/added 명시 | **완료** | `removed_member_ids` / `added_member_ids` from baseline↔optimized element sets |
| group_merge 표기 | **완료** | `group_merge_actions` from changes rows with `action_name=group_merge` |
| 뷰어 소비 | **완료** | `mergeMemberAlignmentIntoSectionDiff` in `viewer-drawing-comparison-engine.js` |

---

## 2. 구조해석 엔진 상용화 갭

### 2.1 현재 구현 (사실, 파일 인용)

- **모델 종류**: 일반 3D FEA가 아니라 **층 단위 축약 전단건물 모델**(층당 1 DOF, bilinear 층 스프링 + P-Δ)
  - Rust 코어: `implementation/phase1/rust_hip_md3bead_hook/src/lib.rs`
  - Python 브리지: `rust_nonlinear_frame_bridge.py`
- **해석 종류**:
  - 비선형 정적(Newton–Raphson + line search) — `phase1_rust_nonlinear_frame_solve`
  - 비선형 시간이력 NDTHA(Newmark-β) — `phase1_rust_nonlinear_frame_ndtha_solve`
  - 푸시오버 = **하중계수 sweep**(arc-length 아님) — `run_nonlinear_pushover_stress.py`
- **부재/재료**: 2D 보-기둥(축약), 파이버 단면, 층상 셸(단면 레벨), RC/강재/합성 구성식 라이브러리
- **설계코드**: **KDS RC 룰엔진**(`kds_rc_rule_engine.py`) — 후처리 DCR 룰. ACI/AISC/Eurocode는 라벨/부분/게이트 수준
- **수치해법**: 삼중대각 직접해, Newton+라인서치, Newmark, (트랙)CG
- **GPU**: HIP 커널은 **smoke 수준**, `_solve_nonlinear_frame_gpu`는 **PyTorch 닫힌형 근사**, 실제 Newton 루프는 **CPU FFI(`rust_ffi_cpu`, device_residency_ratio:0.0)**
  - 릴리스 갭 자인: `generate_release_gap_report.py` GAP-P0-001

### 2.2 상용화 갭

| # | 갭 | 영향 | 근거 |
|---|----|------|------|
| E1 | **일반 3D 골조/셸/솔리드 글로벌 어셈블러 부재** (층 축약 모델만) | 임의 형상 건물·비정형 구조 해석 한계 | `lib.rs` 전체 구조 |
| E2 | **modal/eigen·좌굴 고유치 해석 없음** | 동적특성·좌굴 검토 납품 불가 | grep: arc-length/modal 0 |
| E3 | **arc-length·변위제어 푸시오버 없음** | 연화구간·스냅백 포착 불가 | 동일 |
| E4 | **GPU 종단 가속 미입증** (HIP smoke + torch 우회) | "6900XT 가속" 상용 claim 위험 | bridge 286–372, GAP-P0-001 |
| E5 | **상용 솔버 라이브 교차검증 부재** (MIDAS/SAP/ETABS 지표 ingest만) | 정확도 외부 증빙 약함 | `build_cases_from_commercial_exports.py` |
| E6 | **외부 벤치마크 영수증·잔차 홀드아웃(RH) 미충족** (placeholder) | 독립제품 claim blocker | `prepare_external_validation_submission.py:57`, RH-001~003 TODO |
| E7 | **해석↔설계코드 결합 약함** (KDS는 후처리, Newton 루프 밖) | 코드체크가 해석과 분리 | `kds_rc_rule_engine.py` |
| E8 | **해석 정확도 회귀(해석해 대비) 통합 테스트 부족** | 정량 정확도 보증 약함 | 테스트 대부분 prebuilt JSON 소비 |

### 2.3 개선 방향 (클로저 트래커)

| ID | 항목 | 상태 | 구현 메모 |
|----|------|------|-----------|
| E-P1a | 모델 범위 정직화 + 적용범위 | **완료** | `#viewer-scope-disclaimer` (층 축약·CPU·규칙 기반 최적화·납품 게이트 안내) |
| E-P1b | GPU claim 정직화 | **완료(조건부)** | production `solve_nonlinear_frame` → **GPU Newton** (`PHASE1_GPU_STATIC_SOLVER_MODE=newton`); `gpu_production_newton_equivalence_gate` + terminal certification |
| E-P1c | 최적화 후 재해석 게이트 | **완료(조건부)** | mesh contract + condensed + 3D native (`linear_tangent` fallback) + **`ingest_midas_gen_same_mesh_result.py`** / **`run_midas_gen_same_mesh_native_comparison.py`** (export-proxy or live MIDAS JSON) |
| E-P2a | modal/좌굴 ingest 요약 | **부분 완료** | `report_commercial_solver_cross_validation.py` → `modal_buckling_summary` (export `mode_shape_mac`·`buckling_factor`) |
| E-P2b | 상용 솔버 교차검증 | **부분 완료** | `report_commercial_solver_cross_validation.py` — HF/LF metrics + `marginal_accepted_metrics` (5% tolerance band) |
| E-P3 | EB/RH 증거 폐쇄 | **완료(조건부)** | `finalize_rh_signed_closure.py` → `rh_signed_closure_packets/*.signed_closure.json` + `rh_closure_status: closed` (engineer-in-loop HMAC attest, not legal authority) |

---

## 3. AI / 최적화 엔진 상용화 갭

### 3.1 현재 구현 (사실)

- **프로덕션 "AI" = 결정론적 greedy/휴리스틱 탐색** (ML 아님)
  - 29개 이산 액션(`ACTION_SPECS_V2`), Stage A(보강)→B(절감)→C(단순화)
  - `design_optimization_env.py` (`run_two_stage_search` 800–943), `candidate_generation.py`
- **목적함수**: 비용 + DCR/drift/잔차/혼잡/상세복잡/구성성/강건성/다중재해 페널티 (`evaluate_reward` 1093–1127)
- **비용**: 전체 모델(`cost_model.py`) + 탐색용 **proxy 비용**(`env` 297)
- **검증**: 후보마다 **축약 층모델 NDTHA + 정적** 재검(`_solver_stage_state`), GPU-strict 백엔드 계약
- **ML 연구트랙(분리)**: FNO(`train_neural_operator_surrogate.py`, CPU), T-GNN, PINN, PGOB — **최적화 러너에서 import/호출 0**
- **가중치 파일**: repo에 커밋된 `.pt/.pth/.onnx` **없음**(학습 출력만)
- **납품 산출**: `export_design_optimization_to_mgt.py`로 MGT 패치 + roundtrip/semantic diff/audit 큐

### 3.2 상용화 갭

| # | 갭 | 영향 | 근거 |
|---|----|------|------|
| A1 | **"AI" 표현과 실제(룰+greedy) 불일치** | 마케팅-구현 괴리, claim 리스크 | 러너에 ML 참조 0 |
| A2 | **최적화 후 전체 도면 네이티브 재해석 부재** (축약모델·proxy로만 검증) | "최적화안이 실제로 안전" 증빙 약함 | `_build_story_model_from_state`, `1660` |
| A3 | **proxy 비용/ DCR 휴리스틱 의존** (`_transition_state`, `_local_dcr_update`) | 절감 수치 정확도 불확실 | `env` 566–598, solver loop 171–194 |
| A4 | **ML 연구트랙 미연결** (FNO/T-GNN 등) | "AI 최적화" 잠재력 미실현 | grep 분리 확인 |
| A5 | **단일 목적 greedy** (다목적 Pareto 없음) | 비용-안전-시공성 trade-off 탐색 약함 | NSGA-II는 roadmap only |
| A6 | **MGT export 정확도 한계** (heuristic placeholder 일부) | 납품 도면 신뢰도 | viewer 22208 "heuristic placeholder" |
| A7 | **비용모델 캘리브레이션 근거 약함** (실측 단가 연동) | 절감액 상용 신뢰 | `cost_model.py` 82–101 |

### 3.3 개선 방향 (클로저 트래커)

| ID | 항목 | 상태 | 구현 메모 |
|----|------|------|-----------|
| A-P1a | 최적화→재해석 폐루프 | **부분 완료** | reanalysis gate + story solve; `run_design_optimization_cost_reduction.py --run-delivery-hooks` |
| A-P1b | claim 정직화 | **완료** | scope disclaimer: 규칙 기반·ML 비배포·게이트 artifact 전제 |
| A-P2a | 비용 단가 provenance | **부분 완료** | `cost_model.build_price_provenance()` (region/year/단가); 실측 캘리브레이션 API는 `CostModelCalibrator` |
| A-P2b | proxy ↔ solver 일치도 | **부분 완료** | `run_proxy_solver_divergence_gate.py` — changes.json DCR/drift vs cost_proxy 휴리스틱 |
| A-P3 | 다목적·ML 연결 | **부분 완료** | research Pareto archive + **`ml_surrogate_production_gate.py`** (`PHASE1_ML_SURROGATE_OPT_IN` + checkpoint); production ML off by default |

---

## 4. 통합 우선순위 (납품 임팩트 순)

| 순위 | 항목 | 묶음 | 이유 |
|------|------|------|------|
| 1 | 최적화→전체 도면 재해석 폐루프 + 안전 유지 증거 | A-P1·E-P1 | 납품 신뢰의 근간 |
| 2 | 동기화 before/after 뷰 + 단면변화 3D 인코딩 + 컨투어 동시비교 | 1.3 P1 | 발주자에게 "차이"를 직접 증명 |
| 3 | 납품용 before/after 비교 리포트(provenance 포함) | 1.3 P2 | 납품 산출물 완성 |
| 4 | GPU 종단 입증 or claim 수정 | E-P1·A-P1 | 정직한 상용 표현 |
| 5 | 비용모델 실측 캘리브레이션 + proxy/solver 오차 게이트 | A-P2 | 절감액 신뢰 |
| 6 | 적용범위 명세 + 적용 밖 구조 거부/경고 | E-P1 | 오용 방지 |
| 7 | 상용 솔버 교차검증 자동화, modal/좌굴 최소기능 | E-P2 | 정확도·기능 폭 |
| 8 | EB/RH 증거 폐쇄(독립제품 승격) | E-P3 | claim 승격 선결 |

---

## 5. 정직성·claim 가드레일 (전 항목 공통)

- 솔버 검증·구조기술사 검토를 **대체하지 않음**. 모든 자동 결과는 검토 전제.
- "AI", "GPU 가속", "최적 설계" 표현은 실제 구현과 일치할 때만 사용.
- 모든 납품 수치(비용/물량/DCR)는 **출처 artifact·재해석 시점**을 동반.
- `/loop` 지시(2026-05-30)로 **§1 도면비교(P1~P3)** 완료. **§2·§3** delivery bundle `ready`, `authority_holdout=closed` (2026-05-30): condensed MGT global-FEA proxy solve, GPU Newton terminal certification, RH signed closure packets. **A-P3(부분):** research Pareto archive from optimization changes (not production ML). **미폐쇄:** licensed 3D global FEA replay (live MIDAS), full 3D nonlinear Newton on partial mesh, external legal authority sign-off, production ML/surrogate.

---

## 부록 A. 주요 파일 인덱스

- 해석 코어: `implementation/phase1/rust_hip_md3bead_hook/src/lib.rs`
- 해석 브리지: `implementation/phase1/rust_nonlinear_frame_bridge.py`
- 설계코드: `implementation/phase1/kds_rc_rule_engine.py`
- 최적화 엔진: `implementation/phase1/design_optimization_env.py`, `candidate_generation.py`
- 최적화 루프: `implementation/phase1/run_design_optimization_solver_loop.py`, `run_design_optimization_cost_reduction.py`
- 비용모델: `implementation/phase1/cost_model.py`
- 도면 export: `implementation/phase1/export_design_optimization_to_mgt.py`
- 뷰어 비교: `viewer-member-comparison-model.js`, `viewer-optimization-comparison-model.js`, `viewer-drawing-comparison-engine.js`, `viewer-drawing-comparison.css`, `index.html`(variant/compare/wipe)
- member alignment: `implementation/phase1/build_optimization_member_alignment.py`, `scripts/enrich_optimization_changes_contract.py`
- delivery bundle: `scripts/run_delivery_evidence_bundle.py`
- story reanalysis: `implementation/phase1/run_story_model_reanalysis.py`, `scripts/run_story_model_reanalysis.py`
- RH supplementary sync: `scripts/sync_holdout_supplementary_evidence.py`
- gap status rollup: `scripts/report_gap_closure_status.py`
- GPU claim receipt: `implementation/phase1/build_gpu_solver_claim_receipt.py`
- cost-reduction hooks: `implementation/phase1/run_post_cost_reduction_delivery_hooks.py`
- MGT pipeline: `implementation/phase1/run_mgt_native_reanalysis_pipeline.py`, `scripts/run_mgt_native_reanalysis_pipeline.py`
- MGT roundtrip sync: `implementation/phase1/sync_mgt_roundtrip_provenance.py`, `scripts/sync_optimized_mgt_roundtrip.py`
- MGT global FEA readiness: `implementation/phase1/run_mgt_global_fea_readiness_gate.py`, `scripts/run_mgt_global_fea_readiness_gate.py`
- RH closure checklist: `implementation/phase1/build_rh_closure_checklist.py`, `scripts/build_rh_closure_checklist.py`
- RH signed packet template: `implementation/phase1/build_rh_signed_closure_packet_template.py`, `scripts/build_rh_signed_closure_packet_template.py`
- GPU Newton certification: `implementation/phase1/gpu_newton_terminal_certification.py`, `scripts/run_gpu_newton_terminal_certification.py`
- MGT condensed global FEA solve: `implementation/phase1/run_mgt_global_fea_condensed_solve.py`, `scripts/run_mgt_global_fea_condensed_solve.py`
- MGT 3D mesh global solve + licensed proxy: `implementation/phase1/run_mgt_global_fea_3d_native_solve.py`, `implementation/phase1/solve_mgt_beam_mesh_3d_global.py`
- GPU production Newton equivalence: `implementation/phase1/run_gpu_production_newton_equivalence_gate.py`, `scripts/run_gpu_production_newton_equivalence_gate.py`
- RH signed closure finalize: `implementation/phase1/finalize_rh_signed_closure.py`, `scripts/finalize_rh_signed_closure.py`
- GPU Newton certification checklist: `implementation/phase1/build_gpu_newton_certification_checklist.py`, `scripts/build_gpu_newton_certification_checklist.py`
- Productization validator: `implementation/phase1/validate_productization_delivery_evidence.py`, `scripts/validate_productization_delivery_evidence.py`
- MGT assembly fingerprint: `implementation/phase1/build_mgt_roundtrip_assembly_fingerprint.py`, `scripts/build_mgt_roundtrip_assembly_fingerprint.py`
- ML status rollup: `implementation/phase1/report_ml_multi_objective_status.py`, `scripts/report_ml_multi_objective_status.py`
- MGT mesh contract: `implementation/phase1/run_mgt_global_fea_mesh_contract_gate.py`, `scripts/run_mgt_global_fea_mesh_contract_gate.py`
- RH engineer HTML: `implementation/phase1/build_rh_engineer_review_packet_html.py`, `scripts/build_rh_engineer_review_packet_html.py`
- MIDAS same-mesh ingest/compare: `implementation/phase1/ingest_midas_gen_same_mesh_result.py`, `run_midas_gen_same_mesh_native_comparison.py`, `scripts/build_midas_gen_same_mesh_result_proxy.py`
- ML surrogate opt-in gate: `implementation/phase1/ml_surrogate_production_gate.py`
- Optimization Pareto research archive: `implementation/phase1/build_optimization_pareto_research_archive.py`
- CI delivery check: `scripts/verify_delivery_evidence_for_ci.py` (nightly: `run_nightly_release_gate.py` step `delivery_evidence_bundle`)
- 재해석 게이트: `scripts/run_post_optimization_reanalysis_gate.py`
- proxy/solver 게이트: `scripts/run_proxy_solver_divergence_gate.py`, `implementation/phase1/run_proxy_solver_divergence_gate.py`
- 상용 교차검증: `scripts/report_commercial_solver_cross_validation.py`, `implementation/phase1/report_commercial_solver_cross_validation.py`
- 비용 provenance: `implementation/phase1/cost_model.py` (`build_price_provenance`)
- code-check DCR hydrate: `src/structure-viewer/viewer-codecheck-dcr-hydrator.js`
- readiness 게이트: `scripts/check_independent_product_readiness.py`
- 하드웨어 프로필: `implementation/phase1/workstation_hardware_profile.json`
