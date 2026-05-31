# Continued Improvement Backlog (상용화 후속 개선)

작성: 2026-05-31. 기준: delivery bundle `ready` 상태에서 **독립 제품 claim의 정직성·정확도**를 끌어올리기 위한 후속 개선 목록.
우선순위는 **자체 구현 가능 + claim blocker 해소 ROI** 순. 외부 의존(라이선스/법적 서명)은 별도 표기.

## 우선순위 요약

| ID | 항목 | 현재 | 목표 | 자체구현 | ROI |
|----|------|------|------|----------|-----|
| I1 | 실제 단면/재료 물성 파싱 | 대표값(`_beam_props`: E=210 GPa, 대표 I) | MGT `*SECTION`/`*MATERIAL`/`*THICKNESS`에서 실제 B·H·I·A·E 파싱 → 3D 솔버 + 풍 drift에 주입 | ✅ | ★★★ |
| I2 | 풍 트랙 다방향/비틀림/와류 | **done** — `wind_directional` + corner drift | 다방향(45° 포함)·우발편심 비틀림·와류진동 across-wind | ✅ | ★★☆ |
| I3 | 3D 비선형 Newton 부분메쉬 수렴 | **partial** — improved Newton infra; 0% geometric on benchmark; fallback @ 0.1 | geometric+material Newton without fallback | ✅(난이도 高) | ★★☆ |
| I4 | 풍↔native 직접 교차검증 | **done** — dual BC FE; lumped ≈ fixed-guided (**~5%** rel); cantilever ~3× softer | `pass_model_derived_wind_aligned` | ✅ | ★★☆ |
| I5 | 중·대형 건축물 도면 데이터 다변화 | korea 카탈로그 15건(다수 metadata-only) | 중·대형 native MGT/IFC 수동첨부 → ingest/roundtrip/검증 골격 | ✅(데이터 첨부 필요) | ★★☆ |
| I6 | Live MIDAS Gen 3D replay | export-proxy/model-derived | 라이선스 실행 JSON ingest | ❌(라이선스) | ★★★ |
| I7 | Production ML/surrogate | research Pareto + opt-in gate | 검증 체크포인트 운영 투입 | ✅(데이터/학습 필요) | ★☆☆ |
| I8 | 외부 법적 권위 서명 | RH 내부 signed packet | 외부 면허기술사/기관 서명 | ❌(외부) | ★★★ |

---

## I1 — 실제 단면/재료 물성 파싱 (최우선, composer-2.5 구현 대상)

**Status: done** — `parse_mgt_section_material_properties.py` (SB+P); wind same-mesh full-height column filter (H ≥ 0.5×building height, short secondary/mesh stubs excluded); K_lat ≈ **2.67M kN/m**, drift ≈ **0.0026%**, real-section coverage **~91%** on surviving lines, confidence **high** (`mechanics_real_section`).

### 문제
3D 보 솔버(`solve_mgt_beam_mesh_3d_global.py:_beam_props`)와 풍 drift(`extract_midas_wind_same_mesh_result.py`)는
`section_id % 19` 기반의 **대표 단면**과 고정 E=210 GPa를 사용. SRC/C40 합성·콘크리트 부재가 steel-representative로
처리되어 강성·관성모멘트가 근사값. 따라서 drift는 medium confidence에 머무름.

### 가용 데이터 (검증됨)
- `*SECTION`: `DBUSER` 직사각형(SB) 단면에 실제 치수 포함. 예: `SB800X300` → H=0.8 m, B=0.3 m (행 끝의 `0.8, 0.3`).
- `*MATERIAL`: 실제 탄성계수 — C40 `3.2500e+07` kN/m²(=32.5 GPa), Q235 `2.0600e+08`(=206 GPa), SRC `C40+Q235` 합성(2개 modulus), RigidBar 등.
- `*THICKNESS`: 플레이트 두께(0.2~0.8 m).
- NPZ `elem_section_id`, `elem_material_id`로 요소→단면/재료 매핑 가능.

### 목표
1. `parse_mgt_section_material_properties.py` 신설: MGT 텍스트에서 `{section_id → (B,H,A,Iy,Iz)}`, `{material_id → (E,ν,γ, type)}` 파싱.
   - 직사각형: A=B·H, Iy=B·H³/12, Iz=H·B³/12. SRC는 합성 변환단면(steel 기준 n=Es/Ec) 또는 보수적 콘크리트 단독.
2. `_beam_props`를 실제 물성 우선(없으면 대표값 fallback)으로 교체 — 시그니처에 `section_props`/`material_props` 주입.
3. 풍 drift의 `_mechanics_lateral_stiffness_kNpm`가 실제 I·E 사용 → drift confidence `medium`→`high` 승격(파싱 성공 시).
4. 회귀: 기존 3D 솔버 테스트·풍 테스트 통과 유지, 신규 파서 단위테스트 추가(알려진 단면 I 검증).

### 수용 기준
- `parse_mgt_section_material_properties(mgt_path)`가 SB 단면 ≥1개에 대해 손계산 I와 1% 이내 일치.
- 풍 추출 결과 `assumptions.lateral_stiffness_basis == "mechanics_real_section"`, drift confidence `high`.
- `pytest tests/test_parse_mgt_section_material_properties.py tests/test_extract_midas_wind_same_mesh_result.py tests/test_solve_mgt_beam_mesh_3d_global.py` 통과.
- delivery bundle `ready` 유지.

### I1c — 3D beam mesh solver real section/material (2026-05-31)
- `solve_mgt_beam_mesh_3d_global.py` now accepts `elem_material_id`, `section_props`, `material_props` from `load_mgt_section_material_properties(mgt_path)`; caller `run_mgt_global_fea_3d_native_solve.py` wires MGT path via `build_mgt_reanalysis_provenance`.
- Real props override A, E, weak-axis I (`min(Iy,Iz)`); yield/hardening remain representative (`_beam_props` fallback for missing IDs).
- Output adds `used_real_section_properties`, `real_section_property_coverage_pct`; solve modes `mgt_npz_beam_mesh_3d_real_section` / `…_real_section_linear_tangent` when tables are injected (Newton two-phase + `linear_tangent` fallback unchanged).
- Benchmark (`max_elements=420`, generator-33 roundtrip): **~91.3%** real-section coverage on 80-element submesh; **Newton does not converge** at load scales 1.0–0.25; **`linear_tangent` fallback at load_scale=0.1** → `solve_mode=mgt_npz_beam_mesh_3d_real_section_linear_tangent`, `converged=true`. vs representative-only at same mesh cap: rep also used `linear_tangent` but at a higher load step — real run **base_shear ≈500 kN** (vs rep **≈396 kN**), **max_drift_ratio_pct ≈2052%** (vs rep **≈3740%**); both are partial-submesh proxies, not full-building drift. Delivery bundle **`ready`** maintained.

---

## I2 — 풍 다방향/비틀림/와류

**Status: done** — `extract_midas_wind_same_mesh_result.py` surfaces `wind_directional` (X/Y base shear, `governing_direction`, crosswind bias, serviceability/comfort/accel from `wind_workflow`); simplified accidental torsion (`governing_amplification` ≈ **1.073** on ~84.8×68 m plan, **gov_dir=X**); `metrics.corner_drift_ratio_pct` ≈ **0.00275%** (translational ≈ **0.00256%**).

### 목표
- 8방위(0/45/90/...) 또는 최소 X/Y/대각 base shear envelope.
- 우발편심(±5% 평면치수) 비틀림 모멘트 → 모서리 drift 증폭.
- across-wind 와류진동(Strouhal) 가속도 체크는 `wind_workflow.py`에 이미 부분 존재 → same-mesh 결과로 surface.

### 수용 기준
- 풍 same-mesh 결과에 `governing_direction`, `torsional_amplification`, `vortex_check` 필드 추가, 테스트. ✅ (`wind_directional`, `accidental_torsion.governing_amplification`, comfort/accel surfaced)

## I3 — 3D 비선형 Newton 부분메쉬 수렴

**Status: partial (2026-05-31)** — `solve_mgt_beam_mesh_3d_global.py` gains `use_improved_newton=True` (default) with elastic incremental predictor per load step, 8-trial backtracking line search (best-trial + optional Armijo), Jacobi diagonal scaling on ill-conditioned tangents, optional `lateral_load_scale` (default 0) for top-story lateral shear exercising geometric stiffness, gravity-tributary axial forces when lateral load is active, finer load steps `(0.05…1.0)`, and reporting fields `newton_converged_at_load_step`, `newton_iterations_total`, `fell_back_to_linear_tangent`. `linear_tangent` fallback retained.

**Benchmark (generator-33 roundtrip, real sections, max_elements=420):**

| Solver | First Newton residual @ load_scale=0.1 | Geometric Newton converged | Final solve_mode |
|--------|----------------------------------------|----------------------------|------------------|
| Legacy (`use_improved_newton=False`) | ~4437 N | **0%** (stalls load_step 0.2) | `mgt_npz_beam_mesh_3d_real_section_linear_tangent` @ load_scale=0.1 |
| Improved (default) | ~391 N (~11× lower) | **0%** (stalls load_step 0.05) | `mgt_npz_beam_mesh_3d_real_section_linear_tangent` @ load_scale=0.1 |

- **`nonlinear_equilibrium=true` rate on benchmark: 0%** — force-based geometric tangent + partial vertical-chain submesh still does not drive free-DOF equilibrium residual below tolerance; Newton direction barely changes `f_int` on free DOFs (known model/BC limitation).
- **`linear_tangent` fallback still required** at load_scale ≤ 0.1 for converged status; delivery native solve uses bridge path when only fallback converges.
- CLI `scripts/run_mgt_global_fea_3d_native_solve.py`: `solve_mode=mgt_npz_beam_mesh_3d_real_section_linear_tangent`, `fell_back_to_linear_tangent=true`, `load_scale_applied=0.1`.
- Tests: `pytest tests/test_solve_mgt_beam_mesh_3d_global.py` — 3 passed; new test asserts improved first-iteration residual < legacy or geometric convergence at load_step ≥ 0.5.

**Still open:** deformed-state axial force iteration for P-Δ, full-mesh (non-chain) BC/diaphragm, consistent force-based internal force Jacobian — needed to raise geometric Newton convergence rate above 0%.

## I4 — 풍↔native 직접 교차검증

**Status: done (aligned)** — Native lateral solve runs **two Euler–Bernoulli beam FE boundary conditions** on the same aggregate `EI=Σ E·I` and wind forces (`wind_native_lateral_dual.v1` JSON): **`fixed_guided`** (base fixed + top rotation constrained → same BC family as lumped `K=Σ12EI/H³`) and **`cantilever`** (free top rotation → softer flexural bound).

**BC note:** Prior ~3× drift gap was a **BC mismatch** (cantilever ≈3EI/H³ vs lumped fixed-guided 12EI/H³), not a load disagreement.

**N-convergence (max story drift %, V≈638 kN):**

| N | fixed_guided | cantilever |
|---|--------------|------------|
| 12 | 0.002694% | 0.007639% |
| 24 | 0.002618% | 0.007228% |
| 48 | 0.002576% | 0.007024% |

| Metric | Lumped extractor | Native fixed_guided (N=12) | Native cantilever (N=12) |
|--------|------------------|----------------------------|--------------------------|
| Drift | **0.002561%** | **0.002694%** | **0.007639%** |
| vs lumped | — | rel **~5.2%** (tol 60% → **aligned**) | ~3× larger (soft bound) |

- `comparison_status`: **`pass_model_derived_wind_aligned`** (`wind_native_lateral` tier **pass**). Bracket path `pass_model_derived_wind_bracketed` available when lumped lies strictly between the two native drifts.
- CLI: `scripts/solve_mgt_real_section_lateral_pushover.py --boundary both`; bundle writes `mgt_real_section_lateral_pushover.json` with both modes.

## I5 — 중·대형 건축물 도면 데이터 — **partial done**
- **Done (scaffolding):** `korean_medium_large_source_seed.json` (+7 metadata/attach targets), `korean_building_scale.py`, catalog merge in `generate_korean_source_catalog.py`, `report_medium_large_korean_sources.py`, `run_korean_medium_large_ingest_pipeline.py`, `docs/korean-medium-large-drawing-data-guide.md`, `open_data/korea/README.md`.
- **Still operator:** 실제 중·대형 native MGT/IFC 바이너리는 g2b/LH/buildingSMART에서 **수동 다운로드** 후 `collected/artifacts/<id>/`에 첨부 → `collect_korean_public_structures.py` / ingest pipeline 재실행. placeholder MGT는 `mgt_header_ok=false`로 보고됨.
- 기존 시드(고양창릉, 행복도시 5-1, BIM Awards 등) + 확장 시드 병합 카탈로그: `python3 scripts/generate_korean_source_catalog.py`.
- 정책: 자동 HTTP 다운로드 금지. 첨부 후 MGT는 roundtrip, IFC는 `ifc_structural_subset`.
- 초고층 벤치마크는 별도 `open_data/megastructure/` (Canton Tower 등) — 운영 가이드 참조.

## I6/I8 — 외부 의존 (자체구현 불가)
- I6 Live MIDAS Gen: 라이선스 환경에서 export → `scripts/install_midas_live_same_mesh_result.py`로 설치(골격 준비 완료).
- I8 외부 법적 서명: 면허기술사/기관 검토·서명.

## I7 — Production ML/surrogate
- research Pareto archive(`build_optimization_pareto_research_archive.py`)는 존재. 운영 투입은 검증 체크포인트(`PHASE1_ML_SURROGATE_CHECKPOINT`) + opt-in(`PHASE1_ML_SURROGATE_OPT_IN`) 필요.
