# Structural Optimization Workbench

## Documents

- [Frontend build reproducibility](docs/frontend-build-reproducibility.md)
- [Viewer source/export contract](docs/viewer-contract.md)
- [Release publication runbook](docs/release-publication-runbook.md)
- [Open-data artifact restore runbook](docs/open-data-artifact-restore-runbook.md)
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

- Current state: source-boundary cleanup is closed, P0 is closed, P1 is now unblocked, and P0-1 release publication for `structural-analysis-artifacts-2026-04-26` is verified against the GitHub Release asset listing, metadata preflight, and published-byte SHA/bytes evidence.
- P0 closure status is scriptable: `python3 scripts/check_p0_closure_status.py --json` without release evidence still reports the publication gate as open by design, while the same command with release assets, upload plan, metadata preflight, hydrated artifact root, and `--tag-ref-present` reports overall P0 closed.
- Commercial scope is release-facing and intentionally bounded: grade is `Commercial`, `engineer_in_loop_accelerated_coverage_ready=true` for 95-99% accelerated coverage, `full_commercial_replacement_ready=false`, and the residual holdout queue stays explicit as `licensed_engineer_review_required` (`owner=기술사`, `status=pending_review`, `work_item=RH-001`, `SLA=72h`, `due=assignment_plus_3_business_days`, `closure_evidence=signed_engineer_review_packet`), `legacy_tool_cross_validation_required` (`owner=기존툴+기술사`, `status=pending_cross_validation`, `work_item=RH-002`, `SLA=120h`, `due=assignment_plus_5_business_days`, `closure_evidence=legacy_tool_cross_validation_packet`), and `legal_authority_signoff_required` (`owner=기술사/기존 승인 workflow`, `status=pending_signoff`, `work_item=RH-003`, `SLA=168h`, `due=assignment_plus_7_business_days`, `closure_evidence=authority_signoff_packet`). Until the EB/RH evidence sidecars are materialized, EB receipt stays `0/4` and RH closure evidence stays pending.
- External benchmark handoff is tracked separately through the one-page attestation queue (`hardest_external_10case`, `tpu_hffb`, `peer_spd_hinge`, `korean_public_structures`), with work item, submission id, lifecycle, receipt status, owner action, and dry-run evidence visible in the release-gap and committee package surfaces.
- Before a live queue changes, preview batch review updates with `implementation/phase1/preview_external_benchmark_submission_after_review_updates.py --queue-manifest <queue-manifest.json> --batch-updates-json <batch-updates.json> --out <external_benchmark_submission_readiness_preview.json>` so the next `submission_receipt` / `receipt_status` and owner action stay explicit; when a receipt/update sidecar exists, merge it with `implementation/phase1/generate_external_benchmark_submission_readiness.py --submission-updates <external_benchmark_submission_updates.json>` so `receipt_url`, `submitted_at_utc`, `last_checked_at_utc`, and `closure_evidence_status` stay machine-readable. The same closure pattern applies to RH through the planned `residual_holdout_closure_updates.json` sidecar.
- P0 source-boundary item: tracked stress/workspace/output/rust target artifacts are removed from Git tracking; 25MiB+ open-data artifacts are externalized in `implementation/phase1/open_data_external_artifacts_manifest.json`.
- Next order: P1 quality/fallback/benchmark breadth (now unblocked) -> real-project row provenance/parser breadth -> residual holdout queue ownership/status -> P2 viewer shared selection/provenance and report polish.
- P0-1 remains closed only while the release has exactly the current 22 manifest assets, metadata preflight passes, upload-plan SHA/bytes match the promoted manifest, and hydrated published bytes plus post-publish round-trip evidence verify cleanly.
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
python3 scripts/check_p0_closure_status.py --json
python3 scripts/verify_open_data_external_artifacts_manifest.py --manifest implementation/phase1/open_data_external_artifacts_manifest.json --structure-only
python3 scripts/plan_open_data_artifact_restore.py --json --out /tmp/open-data-restore-plan.json
python3 implementation/phase1/validate_real_project_corpus_manifest.py --schema implementation/phase1/real_project_corpus_manifest.schema.json --manifest implementation/phase1/real_project_corpus_seed_manifest.json --show-summary
```

After publication, pass the captured P0 closure evidence into the same clean-checkout materializer: `python3 scripts/materialize_clean_checkout_evidence_chain.py --p0-status <p0-status.json> --p1-readiness-out <p1-readiness-status.json> --p1-benchmark-out <p1-benchmark-breadth-status.json> --p1-operational-queues-out <p1-operational-queues.json> --p1-operational-queues-out-md <p1-operational-queues.md> --json --out <clean-checkout-evidence-chain.json>`. The materializer now keeps `contract_pass=false` unless P0 closure evidence is consumed and P1 execution/breadth gates are unblocked; `inputs_contract_pass` remains available for the softer pre-P0 materialization check.

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
- If P0-1 is still open, use [Release publication runbook](docs/release-publication-runbook.md) before trying to publish from the release tree.
- Generated single-file delivery viewers are release artifacts listed in `implementation/phase1/release_artifacts_manifest.json`.
- Release verification runbook:
  1. Source CI: run `python3 scripts/verify_release_artifacts_manifest.py --manifest implementation/phase1/release_artifacts_manifest.json --structure-only` so source CI only checks manifest structure.
  2. Metadata preflight: run `python3 scripts/fetch_github_release_assets.py --repo <owner/name> --tag <release-tag> --out <release-assets.json>` to export release asset metadata, then run `python3 scripts/check_release_asset_listing.py --manifest implementation/phase1/release_artifacts_manifest.json --assets-json <release-assets.json> --require-all --require-exact`.
  3. Fresh candidate root: run `python3 scripts/build_release_publication_candidate.py --manifest implementation/phase1/release_artifacts_manifest.json --artifact-root <fresh-release-asset-root> --work-dir <private-release-work-dir> --manifest-out <candidate-manifest.json> --write`. The work dir holds private signing keys; the artifact root holds only uploadable manifest assets.
  4. Full integrity: run `python3 scripts/verify_release_artifacts_manifest.py --manifest <candidate-manifest.json> --artifact-root <fresh-release-asset-root> --require-artifacts`, then write metadata evidence with `python3 scripts/verify_release_artifacts_manifest.py --manifest <candidate-manifest.json> --artifact-root <fresh-release-asset-root> --hydrate-preflight --out <metadata-preflight.json>`.
  5. Upload plan: run `python3 scripts/prepare_release_upload_plan.py --manifest <candidate-manifest.json> --artifact-root <fresh-release-asset-root> --out <release-upload-plan.json>` and upload only the `upload_assets` entries. With `GITHUB_TOKEN` or `GH_TOKEN` set, run `python3 scripts/publish_github_release_assets.py --repo betelgeuze-kang/Structural-Analysis --manifest <candidate-manifest.json> --artifact-root <fresh-release-asset-root> --assets-out <release-assets.json>` to create/update the GitHub Release and upload those manifest-listed files. Without an env token, run the `Publish Release Assets` GitHub Actions workflow from the UI or dispatch it with `python3 scripts/dispatch_release_publish_workflow.py --allow-gh-auth-token --dry-run --json` followed by the same command without `--dry-run`; the workflow uses the Actions `GITHUB_TOKEN` to regenerate the candidate, publish the release assets, verify release closure, and optionally promote the source manifest.
  6. Published-byte roundtrip: run `python3 scripts/hydrate_github_release_assets.py --repo betelgeuze-kang/Structural-Analysis --manifest <candidate-manifest.json> --artifact-root <hydrated-release-root> --write --out <post-publish-roundtrip.json>`, then `python3 scripts/verify_release_artifacts_manifest.py --manifest <candidate-manifest.json> --artifact-root <hydrated-release-root>`.
  7. Closure gate: run `python3 scripts/check_release_p0_closure.py --manifest <candidate-manifest.json> --assets-json <release-assets.json> --artifact-root <fresh-release-asset-root> --upload-plan-json <release-upload-plan.json> --metadata-preflight-json <metadata-preflight.json> --post-publish-roundtrip-json <post-publish-roundtrip.json> --tag-ref-present true --require-all --require-exact --fail-unclosed`.
  8. Overall P0 status: run `python3 scripts/check_p0_closure_status.py --manifest <candidate-manifest.json> --release-assets-json <release-assets.json> --artifact-root <fresh-release-asset-root> --upload-plan-json <release-upload-plan.json> --metadata-preflight-json <metadata-preflight.json> --post-publish-roundtrip-json <post-publish-roundtrip.json> --tag-ref-present --fail-open` to combine P0-1 publication evidence with P0-2..P0-6 core evidence against the candidate manifest.
  9. Promote manifest: after the GitHub Release asset listing and SHA/bytes checks pass, promote `<candidate-manifest.json>` into `implementation/phase1/release_artifacts_manifest.json` in a separate source commit.
  10. Published status: `structural-analysis-artifacts-2026-04-26` must match the current 22 manifest-listed assets. Repo-local `implementation/phase1/release/` is still not an upload source; verify the release through asset listing, upload plan, metadata preflight, post-publish round-trip JSON, and hydrated published-byte SHA/bytes checks.

- Failure triage: if the `Regenerate release viewer artifacts` step fails, read the `Nightly release gate summary:` block in the job log, then download the `release-publication-evidence` artifact and inspect `implementation/phase1/release/nightly_release_gate_report.json`. A `Node20` warning by itself is only a runtime warning; use the step exit code and artifact contents to decide whether to rerun.
- After success: run `python3 scripts/check_p0_closure_status.py --manifest <candidate-manifest.json> --release-assets-json <release-assets.json> --artifact-root <fresh-release-asset-root> --upload-plan-json <release-upload-plan.json> --metadata-preflight-json <metadata-preflight.json> --post-publish-roundtrip-json <post-publish-roundtrip.json> --tag-ref-present --json --out <p0-status.json> --out-md <p0-status.md> --fail-open` first, then `python3 scripts/check_p1_readiness_status.py --p0-status <p0-status.json> --json --out <p1-readiness-status.json> --out-md <p1-readiness-status.md> --fail-blocked`, and only then `python3 scripts/check_p1_benchmark_breadth_status.py --p1-readiness-status <p1-readiness-status.json> --json --out <p1-benchmark-breadth-status.json> --out-md <p1-benchmark-breadth-status.md> --fail-blocked`.
- Do not wildcard-upload `implementation/phase1/release/`; publish only the manifest-listed assets from a freshly regenerated asset root.
- If you restore the release bundle locally, regenerate the release registries with `implementation/phase1/generate_release_project_registry_bootstrap.py` instead of hand-editing the packaged outputs.

## Repository Hygiene

- The source repo intentionally excludes private signing keys, large raw datasets, generated release folders, repeated experiment archives, and temporary QA scratch space.
- `python3 scripts/check_repo_hygiene.py --show-ok` enforces that `implementation/phase1/release/`, `implementation/phase1/experiments/`, `tmp/`, `node_modules/`, `dist/`, private `.pem` keys, and oversized raw artifacts stay out of Git.
- `python3 scripts/check_git_remote_safety.py --show-ok` prevents accidental publish to the old Monet-wedding remote; both `origin` and `structural` should resolve to `betelgeuze-kang/Structural-Analysis`.
- `python3 scripts/plan_source_boundary_cleanup.py --write-pathspec <path>` creates a non-mutating cleanup plan for tracked stress/workspace/output/rust target artifacts and 25MiB+ files before any `git rm --cached` operation.
- `implementation/phase1/open_data_external_artifacts_manifest.json` records SHA-256 and byte counts for externalized open-data assets that should be restored from GitHub Releases or the source-family artifact cache when running heavy validation.
- Use [Open-data artifact restore runbook](docs/open-data-artifact-restore-runbook.md) and `python3 scripts/plan_open_data_artifact_restore.py --cache-root <cache-root> --fail-unready` before P1 heavy validation.
- `python3 scripts/check_p1_readiness_status.py --json` separates P1 input readiness from the P0-1 release-publication blocker, so P1 work does not accidentally start before release closure.
- `python3 scripts/check_p1_benchmark_breadth_status.py --json` summarizes the tracked P1 commercial/benchmark breadth evidence, including the external benchmark submission queue lifecycle, and keeps execution blocked until `check_p1_readiness_status.py` reports P0-1 closed.
- `python3 scripts/materialize_p1_operational_queues.py --p1-benchmark-breadth-status <p1-benchmark-breadth-status.json> --artifact-root <artifact-root> --json --out <p1-operational-queues.json> --out-md <p1-operational-queues.md> --fail-open` writes the combined P1 operational backlog: external benchmark submission work items plus residual holdout closure packet templates for RH-001/RH-002/RH-003. The EB receipt/update sidecar is `external_benchmark_submission_updates.json`; the RH closure-update sidecar is `residual_holdout_closure_updates.json`. Publication candidates include both sidecars in `project_package.zip` when present, and the clean-checkout chain can hydrate them back from that package so release reviewers can see pending versus attached receipt/closure evidence without a source checkout. Missing or incomplete sidecars do not auto-close EB/RH rows; they keep the clean-checkout contract blocked or pending until the expected EB/RH update rows are present.
- `python3 scripts/report_commercialization_level.py --external-benchmark-submission-updates <external_benchmark_submission_updates.json> --json` reports the release-facing commercialization level from commercial readiness, EB receipt/update sidecar status, RH closure sidecar status, and P1 breadth readiness. Current intended claim remains engineer-in-loop commercial acceleration, not full autonomous replacement.

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
