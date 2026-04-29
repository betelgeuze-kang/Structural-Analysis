# Commercialization Execution Roadmap

이 문서는 이후 작업의 기준 순서표다.  
상세 갭 정의는 `commercialization-gap-redteam-playbook.md`를 따르고, 본 문서는 실제 진행 순서와 개선 내용을 고정한다.

## Current Commercialization Level

현재 단계는 `상용 데모 / 파일럿 직전`이다.

- Source repo hygiene: `Green`
- Generated drift gate: `Green`
- Frontend contract: `Green`
- Targeted pytest smoke: `Green`
- Release artifact integrity: `Yellow`
- Structural analysis commercial trust: `Red`
- Viewer product polish: `Yellow`

상용화 레벨은 대략 `0.6`으로 본다.  
PoC, 기술제안 데모, 내부 파일럿은 가능하지만, 책임 해석 결과를 정식 납품하는 상용 해석기 단계는 아니다.

## Operating Rules

- 실행 순서는 `P0 -> P1 -> P2`로 고정한다.
- `P0`가 닫히기 전에는 `P1/P2`를 상용 게이트로 승격하지 않는다.
- generated artifact, release bundle, user asset 변경은 feature/source 커밋과 섞지 않는다.
- 모든 게이트는 재현 가능한 명령과 report/json 증빙을 남긴다.
- source repo는 실행 소스, 테스트, 문서, 작은 fixture만 유지한다.

## Immediate Cleanup State

현재 남은 worktree 변경은 사용자가 의도 삭제한 PNG asset 4개뿐이다.

```text
generated_drift: 0
asset_deletions: 4
source_changes: 0
other_changes: 0
```

다음 조치는 별도 asset cleanup 커밋이다.

```bash
python3 scripts/report_worktree_drift.py --json --fail-on-source --fail-on-other
python3 scripts/check_generated_worktree_clean.py --show-ok
python3 scripts/check_repo_hygiene.py --show-ok
```

## Work Order

### 0. Source Repo Closeout

목표: GitHub source repo가 납품/협업 가능한 상태를 유지하게 한다.

개선 내용:

- 불필요 PNG asset 삭제를 별도 커밋으로 닫는다.
- generated drift와 source changes가 동시에 생기지 않도록 현재 guard를 유지한다.
- stale local release bundle 검증 실패를 release artifact refresh 작업으로 분리한다.

Exit gate:

```bash
python3 scripts/report_worktree_drift.py --json --fail-on-source --fail-on-other
python3 scripts/check_generated_worktree_clean.py --show-ok
python3 scripts/check_repo_hygiene.py --show-ok
```

### 1. P0-1 Release / Review Chain Stabilization

목표: 납품 산출물의 SHA, registry, signature, manifest가 서로 맞게 한다.

개선 내용:

- GitHub Release asset root 기준으로 `release_artifacts_manifest.json` 검증을 닫는다.
- stale local `implementation/phase1/release/` 검증 실패를 fresh release asset 검증으로 대체한다.
- `project_package.zip`, `project_registry.json`, `release_registry.json`, signature 재생성 절차를 문서화하고 CI/수동 검증 기준을 고정한다.

Exit gate:

```bash
python3 scripts/verify_release_artifacts_manifest.py \
  --manifest implementation/phase1/release_artifacts_manifest.json \
  --artifact-root <fresh-release-asset-root>
```

### 2. P0-2 MIDAS Exact Roundtrip

목표: MIDAS 입력/출력 왕복에서 geometry, material, section, load, group mapping을 정확히 보존한다.

개선 내용:

- `.mgt` parser/exporter의 row-level provenance를 강화한다.
- 변경 전/후 diff가 구조적으로 설명 가능하도록 report를 추가한다.
- instruction sidecar, audit manifest, review packet을 deterministic output으로 고정한다.

Exit gate:

```bash
python3 -m pytest -q tests/test_export_design_optimization_to_mgt.py
python3 -m pytest -q tests/test_generate_optimized_drawing_review_ui.py
```

### 3. P0-3 KDS Load Combination Engine

목표: 국내 설계 기준 기반 load combination을 상용툴 수준으로 재현한다.

개선 내용:

- KDS load case taxonomy를 schema로 고정한다.
- dead/live/wind/seismic/load factor 조합을 deterministic engine으로 만든다.
- UI의 load combination 선택과 solver/report provenance를 연결한다.

Exit gate:

```bash
python3 -m pytest -q tests/test_load_combination*
```

### 4. P0-4 MIDAS-KDS Exact Geometry Bridge

목표: MIDAS model geometry와 KDS design check가 같은 member/load/combination identity를 공유하게 한다.

개선 내용:

- `member`, `load_case`, `combination`, `focus_member` 키를 parser, solver, viewer에 공통 적용한다.
- 3D viewer, charts, panel-zone, optimization-history deep-link 계약을 강화한다.
- row provenance report에서 release-surface eligibility를 판정한다.

Exit gate:

```bash
npm run verify:frontend-contract
python3 -m pytest -q tests/test_real_project_parser_coverage_matrix.py
python3 -m pytest -q tests/test_build_real_project_row_provenance_report.py
```

### 5. P0-5 Structural Constitutive Libraries

목표: RC, steel, composite 재료 모델을 실무 검토 가능한 library로 올린다.

개선 내용:

- RC cracking, rebar, confinement, concrete nonlinear envelope를 분리 구현한다.
- steel/composite yielding, buckling, section interaction을 schema와 report로 노출한다.
- proxy result와 solver-verified result를 UI에서 명확히 구분한다.

Exit gate:

```bash
python3 -m pytest -q tests/test_*constitutive*
python3 implementation/phase1/validate_phase1_artifacts.py \
  --out implementation/phase1/static_artifact_validation_report.json
```

### 6. P0-6 Element / Solver Engine

목표: beam-column, fiber, shell, wall, slab 해석 엔진을 상용 검토 수준으로 만든다.

개선 내용:

- beam-column / fiber element의 tangent, residual, convergence report를 고정한다.
- wall/slab batching, LOD, hit-test, contour/deformed mode 비용을 통제한다.
- Rust/HIP 또는 strict native backend가 필요한 구간은 별도 성능 게이트로 분리한다.

Exit gate:

```bash
python3 implementation/phase1/zero_copy_real_probe.py \
  --producer-cmd "<rust_hip_producer_cmd>" \
  --require-rust-hip \
  --out implementation/phase1/zero_copy_real_probe_report_strict.json
```

### 7. P1 Quality / Fallback / Benchmark Breadth

목표: 기능 존재가 아니라 운영 안정성을 증명한다.

개선 내용:

- full pytest, schema validation, structured error code를 CI 기준으로 올린다.
- 물리 위반 시 fallback HF 재해석 루프를 E2E로 검증한다.
- KONEPS/PEER TBI/open benchmark row provenance를 넓힌다.

Exit gate:

```bash
python3 -m pytest -q
python3 implementation/phase1/run_productization_gate.py \
  --out implementation/phase1/spatiotemporal_data/productization_gate_report.json
```

### 8. P2 Viewer / Report / Batch Operations

목표: 고품질 웹뷰어와 납품 보고서를 상용 워크플로로 완성한다.

개선 내용:

- 3D viewer를 상용 구조해석 UI 수준으로 정리한다.
- panel-zone, optimization-history, charts, drawings를 같은 provenance key로 연결한다.
- report export, revision lifecycle, sheet set, annotation/callout collision을 정리한다.
- source viewer와 generated single-file delivery viewer의 역할을 계속 분리한다.

Exit gate:

```bash
npm run verify:frontend-contract
npm run verify:frontend-smoke
python3 -m pytest -q tests/test_generate_optimized_drawing_review_ui.py
```

## Next Action Queue

1. 불필요 PNG asset 삭제를 별도 커밋으로 닫는다.
2. fresh GitHub Release asset root를 확보해 release manifest 검증을 닫는다.
3. `P0-1 Release / Review Chain Stabilization`부터 증빙 report를 갱신한다.
4. `P0-2 MIDAS Exact Roundtrip` 테스트와 report를 확장한다.
5. 이후 Red Team 실행 맵의 P0 항목을 순서대로 닫는다.

## Reference Commands

```bash
python3 scripts/report_worktree_drift.py --json --fail-on-source --fail-on-other
python3 scripts/check_generated_worktree_clean.py --show-ok
python3 scripts/check_repo_hygiene.py --show-ok
npm run verify:frontend-contract
python3 -m pytest -q tests/test_verify_worktree_cleanup_plan.py tests/test_report_worktree_drift.py tests/test_check_generated_worktree_clean.py
```
