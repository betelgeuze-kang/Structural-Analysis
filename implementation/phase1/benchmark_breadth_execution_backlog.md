# Benchmark Breadth Execution Backlog

목표: MIDAS 스타일 production coverage를 넘어가기 위한 `fixed real-source benchmark families`를 추가한다.

우선순위는 다음 네 축이다.

1. `megastructure / open` breadth 확대
2. `shell-beam-mix` coverage 확대
3. `measured dynamic targets` 확보
4. `topology / hazard` 다양성 확보

## Candidate Families

### 1) Measured megatall outrigger family
- 대표: `606m outrigger` 계열
- 목적: 초고층 오구리거/벨트트러스 load path, lateral stiffness, drift envelope 검증
- 필요 데이터: measured dynamic target, story drift envelope, outrigger/belt geometry, baseline vs optimized compare

### 2) Shell-beam-mix megastructure family
- 대표: `SCBF16B shell-beam mix`
- 목적: slab/shell가 frame과 섞인 경우의 상세 해석 및 viewer/readout 검증
- 필요 데이터: shell-only panel map, shared frame map, group/family cluster, baseline handoff

### 3) MIDAS 33-like control family
- 대표: `midas33` 계열
- 목적: parser/round-trip/visualization/control benchmark 기준선 유지
- 필요 데이터: full topology, member families, design code slice, comparison surface

### 4) Torsion-dominant asymmetric high-rise family
- 대표: 편심 코어 / 비대칭 평면 / transfer level 포함 초고층
- 목적: plan irregularity, torsion, coupled drift, story-by-story load redistribution 검증
- 필요 데이터: torsional response target, mode shape MAC, irregularity summary

### 5) Soft-story / transfer / podium family
- 대표: podium + tower, soft-story 또는 transfer slab가 있는 megastructure
- 목적: collapse-prone / nonlinear concentration / transfer-path robustness 검증
- 필요 데이터: measured or authoritative dynamic target, hinge concentration, residual drift, local demand peaks

## Acceptance Criteria

각 family는 아래 기준을 만족해야 등록한다.

1. `real-source provenance`가 명확해야 한다.
2. `fixed seed / fixed split`가 있어야 한다.
3. `measured dynamic target` 또는 공신력 있는 response target이 최소 1개 이상 있어야 한다.
4. `shell-beam-mix` 또는 equivalent topology complexity를 설명할 수 있어야 한다.
5. `baseline vs optimized` compare가 가능해야 한다.
6. `viewer-ready` static + interactive payload가 둘 다 생성되어야 한다.
7. `holdout` split이 있어 training leakage가 없어야 한다.

## Required Artifacts

각 family마다 최소 아래 파일이 필요하다.

1. `source_manifest.json`
2. `family_summary.md`
3. `benchmark_case.json`
4. `response_target.json`
5. `baseline_geometry.json`
6. `optimized_geometry.json`
7. `compare_report.json`
8. `viewer_entry.html`

권장 추가 파일:

1. `drift_envelope.npz`
2. `mode_shape_mac.json`
3. `load_path_trace.json`
4. `failure_mode_labels.json`

## Execution Order

1. `SCBF16B shell-beam mix` family를 먼저 고정한다.
2. `606m outrigger` family를 measured dynamic target과 함께 고정한다.
3. `MIDAS 33` control family를 baseline compatibility 용도로 유지한다.
4. `torsion-dominant asymmetric` family를 추가해 topology 다양성을 확보한다.
5. `soft-story / transfer / podium` family를 추가해 nonlinear collapse diversity를 확보한다.

## Delivery Rule

새 family는 반드시 아래 순서로 릴리즈한다.

1. source manifest
2. benchmark case
3. response target
4. compare report
5. viewer entry

이 순서를 못 지키면 family를 benchmark로 올리지 않는다.

