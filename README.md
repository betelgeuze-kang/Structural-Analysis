# Structural Optimization Workbench

## Documents

- [Frontend build reproducibility](docs/frontend-build-reproducibility.md)
- [Viewer source/export contract](docs/viewer-contract.md)
- [상용화 갭 현재상태 보고서](docs/commercialization-gap-current-state.md)
- [Real Project Corpus closeout guide](docs/real-project-corpus.md)
- [차세대 하이브리드 건축구조 분석 AI 아키텍처 명세서 (ADD)](docs/architecture-definition-document.md)
- [Phase 1 실행 산출물: LF 출력 스키마/검증](implementation/phase1/README.md)
- [Phase 1 다음 구현 계획](implementation/phase1/next-implementation-plan.md)
- [Phase 1 상용화 갭 분석/실행 플레이북 (Red Team)](implementation/phase1/commercialization-gap-redteam-playbook.md)
- [Phase 1 상용화 실행 로드맵](implementation/phase1/commercialization-execution-roadmap.md)
- [Phase 1 직교사영 잔차 보정 리포트](implementation/phase1/projection_update_report.json)
- [Phase 1 Zero-copy bridge report](implementation/phase1/zero_copy_bridge_report.json)
- [Phase 1 Krylov projection report](implementation/phase1/krylov_projection_report.json)
- [Phase 1 material mapping report](implementation/phase1/material_map_report.json)
- [Phase 1 priority 1/2/3 summary](implementation/phase1/priority3_summary.json)

## Commercial Priority Snapshot

- Current state: source tree is clean; source-boundary cleanup is closed; release artifact integrity is still open because P0-1 publication is incomplete.
- P0 source-boundary item: tracked stress/workspace/output/rust target artifacts are removed from Git tracking; 25MiB+ open-data artifacts are externalized in `implementation/phase1/open_data_external_artifacts_manifest.json`.
- Next order: P0-1 release closure -> P0-2 MIDAS exact roundtrip -> P0-3 KDS load combination -> P0-4 MIDAS-KDS geometry identity -> P0-5 constitutive libraries -> P0-6 element/solver -> P1 quality/fallback/benchmark breadth -> P2 viewer shared selection/provenance and report polish.
- P0-1 is not closed until a fresh artifact root is regenerated, the manifest is updated if needed, the tag/release is published, metadata preflight passes, exactly 12 manifest assets are uploaded, and SHA/bytes verification passes.
- Viewer provenance/performance/report polish stays in P2, including shared selection/provenance, wall/slab batching/LOD, solver-verified panel-zone, and SVG sheet/revision/callout.

## Clean Clone Quickstart

From a source checkout, run:

```bash
npm ci
python3 -m pip install -e .[dev]
npm run build
python3 -m pytest -q tests/test_generate_optimized_drawing_review_ui.py
python3 -m pytest -q tests/test_real_project_corpus_manifest.py
python3 scripts/check_repo_hygiene.py --show-ok
python3 scripts/check_git_remote_safety.py --show-ok
python3 scripts/verify_release_artifacts_manifest.py --manifest implementation/phase1/release_artifacts_manifest.json --structure-only
python3 scripts/verify_open_data_external_artifacts_manifest.py --manifest implementation/phase1/open_data_external_artifacts_manifest.json --structure-only
python3 implementation/phase1/validate_real_project_corpus_manifest.py --schema implementation/phase1/real_project_corpus_manifest.schema.json --manifest implementation/phase1/real_project_corpus_seed_manifest.json --show-summary
python3 implementation/phase1/generate_real_project_parser_coverage_matrix.py --manifest implementation/phase1/real_project_corpus_seed_manifest.json --out implementation/phase1/real_project_parser_coverage_matrix.json
python3 implementation/phase1/build_peer_tbi_benchmark_metric_records.py --manifest implementation/phase1/real_project_corpus_seed_manifest.json --coverage-matrix implementation/phase1/real_project_parser_coverage_matrix.json --out implementation/phase1/peer_tbi_benchmark_metric_records.json
python3 implementation/phase1/build_real_project_row_provenance_report.py --manifest implementation/phase1/real_project_corpus_seed_manifest.json --coverage-matrix implementation/phase1/real_project_parser_coverage_matrix.json --peer-metric-records implementation/phase1/peer_tbi_benchmark_metric_records.json --out implementation/phase1/real_project_row_provenance_report.json
```

If you want the clean-clone smoke path instead of the manual build step, run `npm run verify:frontend-smoke`; it already performs the frontend contract check, a clean `npm ci`, and `npm run build`.

## Snapshot Hygiene

- After a full `python3 -m pytest -q`, run `python3 scripts/check_generated_worktree_clean.py --show-ok` as the `generated worktree clean` check before you commit. If it fails, run `python3 scripts/report_worktree_drift.py` to confirm the generated/asset/source split and wait until `source_changes` is `0` before deciding what belongs in cleanup. This guard only reports tracked generated paths that are dirty relative to `HEAD`; it should pass in clean clone/CI, and it does not decide whether source edits or intentional user deletions outside those paths are valid.
- Before cleanup, run `python3 scripts/report_worktree_drift.py --json --fail-on-source --fail-on-other` as a no-write gate. After approval, use `python3 scripts/report_worktree_drift.py --write-pathspec-dir <dir>` to write category pathspec files, then run `python3 scripts/verify_worktree_cleanup_plan.py --pathspec-dir <dir>` to confirm the pathspec still matches the current worktree. Keep generated cleanup and user-owned asset deletion in separate approvals and separate commits. If the diff includes a user-owned asset deletion or any intentional deletion outside the tracked generated paths, confirm that separately before restoring or removing anything.
- A full `python3 -m pytest -q` run may regenerate tracked outputs under `implementation/phase1/open_data/`, `implementation/phase1/stress/`, and `implementation/phase1/panel_zone_solver_verified_*.json`. Keep those refreshes separate from feature changes and expectation patches.
- Legitimate artifact refreshes belong in a separate commit with the verification result that justified them.
- Test side-effect bugs should be fixed with test isolation, not by blindly committing the generated diff.
- `stale local state` means the local release bundle or workspace state is out of date; handle it only after approval, in a separate release-artifact-refresh or workspace-cleanup task, not folded into feature or test work.
- When cleaning up snapshot drift, align the expected values to the current deterministic product state, keep asserts in place, and add explicit enum/status checks instead of removing coverage.

## Source vs Release Viewers

- Source viewers live in `src/structure-viewer/` and are for local development, QA, and deterministic rebuilds from the source repo.
- They may depend on repo-local vendor files and committed sidecars during development.
- Generated single-file delivery viewers are release artifacts listed in `implementation/phase1/release_artifacts_manifest.json`.
- Release verification runbook:
  1. Source CI: run `python3 scripts/verify_release_artifacts_manifest.py --manifest implementation/phase1/release_artifacts_manifest.json --structure-only` so source CI only checks manifest structure.
  2. Metadata preflight: run `python3 scripts/fetch_github_release_assets.py --repo <owner/name> --tag <release-tag> --out <release-assets.json>` to export release asset metadata, then run `python3 scripts/check_release_asset_listing.py --manifest implementation/phase1/release_artifacts_manifest.json --assets-json <release-assets.json> --require-all`.
  3. Flat asset root: after regenerating local release outputs, run `python3 scripts/materialize_release_asset_root.py --manifest implementation/phase1/release_artifacts_manifest.json --artifact-root <fresh-release-asset-root> --write` to copy the 12 manifest-listed assets into a flat upload root.
  4. Full integrity: run `python3 scripts/verify_release_artifacts_manifest.py --manifest implementation/phase1/release_artifacts_manifest.json --artifact-root <fresh-release-asset-root> --require-artifacts`.
  5. Upload plan: run `python3 scripts/prepare_release_upload_plan.py --manifest implementation/phase1/release_artifacts_manifest.json --artifact-root <fresh-release-asset-root> --out <release-upload-plan.json>` and upload only the `upload_assets` entries.
  6. Closure gate: run `python3 scripts/check_release_p0_closure.py --manifest implementation/phase1/release_artifacts_manifest.json --assets-json <release-assets.json> --artifact-root <fresh-release-asset-root> --tag-ref-present true --require-all --fail-unclosed`.
  7. Current blocker: `structural-analysis-artifacts-2026-04-26` is not visible through the GitHub API or `git ls-remote`, repo-local `implementation/phase1/release/` is stale, and upload-plan validation fails on mismatched/missing assets. This is a release-publication gap, not a source-boundary gap.
- Do not wildcard-upload `implementation/phase1/release/`; publish only the 12 manifest-listed assets from a freshly regenerated asset root.
- If you restore the release bundle locally, regenerate the release registries with `implementation/phase1/generate_release_project_registry_bootstrap.py` instead of hand-editing the packaged outputs.

## Repository Hygiene

- The source repo intentionally excludes private signing keys, large raw datasets, generated release folders, repeated experiment archives, and temporary QA scratch space.
- `python3 scripts/check_repo_hygiene.py --show-ok` enforces that `implementation/phase1/release/`, `implementation/phase1/experiments/`, `tmp/`, `node_modules/`, `dist/`, private `.pem` keys, and oversized raw artifacts stay out of Git.
- `python3 scripts/check_git_remote_safety.py --show-ok` prevents accidental publish to the old Monet-wedding remote; both `origin` and `structural` should resolve to `betelgeuze-kang/Structural-Analysis`.
- `python3 scripts/plan_source_boundary_cleanup.py --write-pathspec <path>` creates a non-mutating cleanup plan for tracked stress/workspace/output/rust target artifacts and 25MiB+ files before any `git rm --cached` operation.
- `implementation/phase1/open_data_external_artifacts_manifest.json` records SHA-256 and byte counts for externalized open-data assets that should be restored from GitHub Releases or the source-family artifact cache when running heavy validation.

## Real Project Corpus P0/P1/P2

- Quick check: `python3 implementation/phase1/validate_real_project_corpus_manifest.py --schema implementation/phase1/real_project_corpus_manifest.schema.json --manifest implementation/phase1/real_project_corpus_seed_manifest.json --show-summary`
- P0 starts with [real_project_corpus_seed_manifest.json](implementation/phase1/real_project_corpus_seed_manifest.json): KONEPS and PEER TBI are registered as source families, but KONEPS public metadata/announcement/attachment access stays separate from redistributable artifacts, and PEER TBI starts from citation plus benchmark metric records while raw model/input deck redistribution stays blocked until document-level review is complete.
- P1 begins with [real_project_parser_coverage_matrix.json](implementation/phase1/real_project_parser_coverage_matrix.json): KONEPS coverage targets `.mgt/.ifc/.dwg/.dxf/.pdf/.xlsx/.zip`, PEER TBI benchmark metric groups are `citation`, `period`, `base_shear`, `story_drift`, and `nonlinear_response`, and raw redistribution remains disabled after P0 unless document-level review explicitly allows it.
- P1-3 is the row provenance gate: each promoted parser/benchmark row must keep source family, access policy, checksum-or-withheld reason, file inventory status, parser contract, row pointer, and release-surface eligibility before it can move to P2. Generate it with `implementation/phase1/build_real_project_row_provenance_report.py`; `implementation/phase1/real_project_row_provenance_report.json` is a generated local/CI report and remains outside Git by default.
- PEER TBI metric records are generated by `python3 implementation/phase1/build_peer_tbi_benchmark_metric_records.py --manifest implementation/phase1/real_project_corpus_seed_manifest.json --coverage-matrix implementation/phase1/real_project_parser_coverage_matrix.json --out implementation/phase1/peer_tbi_benchmark_metric_records.json`; the output is citation-first and keeps raw model/input deck redistribution blocked by default.
- P2 automates refresh, redaction, release packaging, and viewer/report surfacing only after P0/P1 gates are green; shared selection/provenance, wall/slab batching/LOD, solver-verified panel-zone, and SVG sheet/revision/callout remain the main viewer gaps.

## Railway/Tunnel Structural Dynamics Extension

- [차량 모델 입력 스키마 (VTI)](implementation/phase1/vehicle_model_schema.json)
- [터널 라이닝/세그먼트 입력 스키마](implementation/phase1/tunnel_lining_schema.json)
- [지반 임피던스 파라미터 테이블](implementation/phase1/soil_impedance_table.json)
- [동역학 계약 - 건축물](implementation/phase1/dynamics_boundary_report.building.json)
- [동역학 계약 - 궤도](implementation/phase1/dynamics_boundary_report.track.json)
- [동역학 계약 - 터널](implementation/phase1/dynamics_boundary_report.tunnel.json)
