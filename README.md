# Structural Optimization Workbench

## Documents

- [Frontend build reproducibility](docs/frontend-build-reproducibility.md)
- [Viewer source/export contract](docs/viewer-contract.md)
- [Real Project Corpus closeout guide](docs/real-project-corpus.md)
- [차세대 하이브리드 건축구조 분석 AI 아키텍처 명세서 (ADD)](docs/architecture-definition-document.md)
- [Phase 1 실행 산출물: LF 출력 스키마/검증](implementation/phase1/README.md)
- [Phase 1 다음 구현 계획](implementation/phase1/next-implementation-plan.md)
- [Phase 1 상용화 갭 분석/실행 플레이북 (Red Team)](implementation/phase1/commercialization-gap-redteam-playbook.md)
- [Phase 1 직교사영 잔차 보정 리포트](implementation/phase1/projection_update_report.json)
- [Phase 1 Zero-copy bridge report](implementation/phase1/zero_copy_bridge_report.json)
- [Phase 1 Krylov projection report](implementation/phase1/krylov_projection_report.json)
- [Phase 1 material mapping report](implementation/phase1/material_map_report.json)
- [Phase 1 priority 1/2/3 summary](implementation/phase1/priority3_summary.json)

## Clean Clone Quickstart

From a source checkout, run:

```bash
npm ci
python3 -m pip install -e .[dev]
npm run build
python3 -m pytest -q tests/test_generate_optimized_drawing_review_ui.py
python3 -m pytest -q tests/test_real_project_corpus_manifest.py
python3 scripts/check_repo_hygiene.py --show-ok
python3 scripts/verify_release_artifacts_manifest.py --manifest implementation/phase1/release_artifacts_manifest.json
python3 implementation/phase1/validate_real_project_corpus_manifest.py --schema implementation/phase1/real_project_corpus_manifest.schema.json --manifest implementation/phase1/real_project_corpus_seed_manifest.json --show-summary
python3 implementation/phase1/generate_real_project_parser_coverage_matrix.py --manifest implementation/phase1/real_project_corpus_seed_manifest.json --out implementation/phase1/real_project_parser_coverage_matrix.json
python3 implementation/phase1/build_peer_tbi_benchmark_metric_records.py --manifest implementation/phase1/real_project_corpus_seed_manifest.json --coverage-matrix implementation/phase1/real_project_parser_coverage_matrix.json --out implementation/phase1/peer_tbi_benchmark_metric_records.json
python3 implementation/phase1/build_real_project_row_provenance_report.py --manifest implementation/phase1/real_project_corpus_seed_manifest.json --coverage-matrix implementation/phase1/real_project_parser_coverage_matrix.json --peer-metric-records implementation/phase1/peer_tbi_benchmark_metric_records.json --out implementation/phase1/real_project_row_provenance_report.json
```

If you want the clean-clone smoke path instead of the manual build step, run `npm run verify:frontend-smoke`; it already performs the frontend contract check, a clean `npm ci`, and `npm run build`.

## Snapshot Hygiene

- A full `python3 -m pytest -q` run may regenerate `generated/open_data/panel_zone/stress` JSON outputs. Keep those refreshes separate from feature changes and expectation patches.
- When cleaning up snapshot drift, align the expected values to the current deterministic product state, keep asserts in place, and add explicit enum/status checks instead of removing coverage.

## Source vs Release Viewers

- Source viewers live in `src/structure-viewer/` and are for local development, QA, and deterministic rebuilds from the source repo.
- They may depend on repo-local vendor files and committed sidecars during development.
- Generated single-file delivery viewers are release artifacts listed in `implementation/phase1/release_artifacts_manifest.json`.
- Download the GitHub Release whose tag matches the manifest `release_tag`, unpack the assets into a local directory, and validate them with `python3 scripts/verify_release_artifacts_manifest.py --manifest implementation/phase1/release_artifacts_manifest.json --artifact-root <downloaded-release-root>`. When you validate the repo-local `implementation/phase1/release/` tree without `--artifact-root`, the check compares actual SHA/bytes and stale files can fail; use a clean clone/CI workspace or a freshly downloaded GitHub Release asset root.
- If you restore the release bundle locally, regenerate the release registries with `implementation/phase1/generate_release_project_registry_bootstrap.py` instead of hand-editing the packaged outputs.

## Repository Hygiene

- The source repo intentionally excludes private signing keys, large raw datasets, generated release folders, repeated experiment archives, and temporary QA scratch space.
- `python3 scripts/check_repo_hygiene.py --show-ok` enforces that `implementation/phase1/release/`, `implementation/phase1/experiments/`, `tmp/`, `node_modules/`, `dist/`, private `.pem` keys, and oversized raw artifacts stay out of Git.

## Real Project Corpus P0/P1/P2

- Quick check: `python3 implementation/phase1/validate_real_project_corpus_manifest.py --schema implementation/phase1/real_project_corpus_manifest.schema.json --manifest implementation/phase1/real_project_corpus_seed_manifest.json --show-summary`
- P0 starts with [real_project_corpus_seed_manifest.json](implementation/phase1/real_project_corpus_seed_manifest.json): KONEPS and PEER TBI are registered as source families, but KONEPS public metadata/announcement/attachment access stays separate from redistributable artifacts, and PEER TBI starts from citation plus benchmark metric records while raw model/input deck redistribution stays blocked until document-level review is complete.
- P1 begins with [real_project_parser_coverage_matrix.json](implementation/phase1/real_project_parser_coverage_matrix.json): KONEPS coverage targets `.mgt/.ifc/.dwg/.dxf/.pdf/.xlsx/.zip`, PEER TBI benchmark metric groups are `citation`, `period`, `base_shear`, `story_drift`, and `nonlinear_response`, and raw redistribution remains disabled after P0 unless document-level review explicitly allows it.
- P1-3 is the row provenance gate: each promoted parser/benchmark row must keep source family, access policy, checksum-or-withheld reason, file inventory status, parser contract, row pointer, and release-surface eligibility before it can move to P2. Generate it with `implementation/phase1/build_real_project_row_provenance_report.py`; `implementation/phase1/real_project_row_provenance_report.json` is a generated local/CI report and remains outside Git by default.
- PEER TBI metric records are generated by `python3 implementation/phase1/build_peer_tbi_benchmark_metric_records.py --manifest implementation/phase1/real_project_corpus_seed_manifest.json --coverage-matrix implementation/phase1/real_project_parser_coverage_matrix.json --out implementation/phase1/peer_tbi_benchmark_metric_records.json`; the output is citation-first and keeps raw model/input deck redistribution blocked by default.
- P2 automates refresh, redaction, release packaging, and viewer/report surfacing only after P0/P1 gates are green.

## Railway/Tunnel Structural Dynamics Extension

- [차량 모델 입력 스키마 (VTI)](implementation/phase1/vehicle_model_schema.json)
- [터널 라이닝/세그먼트 입력 스키마](implementation/phase1/tunnel_lining_schema.json)
- [지반 임피던스 파라미터 테이블](implementation/phase1/soil_impedance_table.json)
- [동역학 계약 - 건축물](implementation/phase1/dynamics_boundary_report.building.json)
- [동역학 계약 - 궤도](implementation/phase1/dynamics_boundary_report.track.json)
- [동역학 계약 - 터널](implementation/phase1/dynamics_boundary_report.tunnel.json)
