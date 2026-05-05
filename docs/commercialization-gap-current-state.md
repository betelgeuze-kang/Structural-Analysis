# 상용화 갭 현재상태 보고서

- 기준일: 2026-05-05
- 목적: P0 hygiene inventory 이후, 상용 구조해석 툴(MIDAS/ETABS/SAP2000/OpenSees) 대비 현재 상태와 다음 작업 순서를 고정한다.

## 한 줄 요약

source boundary, P0-2~P0-6 core evidence, release P0-1 publication이 닫혔다. 그래서 P0 closed, P1 now unblocked이다. P0-1 닫힘 기준은 GitHub Release의 current manifest asset set(현재 source manifest 기준 22개), upload plan, metadata preflight, post-publish round-trip JSON, hydrated published-byte SHA/bytes verification이며, P1 quality/fallback/benchmark breadth 실행은 P0 status evidence를 넘길 때 unblocked 상태다.

## 현재 상태

- `scripts/check_repo_hygiene.py --strict-source-boundary`는 통과했고, tracked stress/workspace/output/rust target 정리는 끝났다.
- `scripts/plan_source_boundary_cleanup.py --large-file-threshold-mib 25`는 0 candidates를 보고했다.
- `implementation/phase1/open_data_external_artifacts_manifest.json`는 SHA/bytes가 붙은 8개 externalized open-data assets를 기록한다.
- 자동 검증으로 닫힌 범위는 source boundary, repo hygiene, open-data externalization manifest다.
- 수작업/외부 자산 의존 범위였던 release P0-1 publication은 published release evidence로 닫혔다.
- `python3 scripts/check_p0_closure_status.py --json`는 P0-2 MIDAS exact roundtrip, P0-3 KDS load combination, P0-4 MIDAS-KDS geometry identity, P0-5 constitutive libraries, P0-6 element/solver evidence를 closed로 묶어 보고한다.
- release evidence 없이 `python3 scripts/check_p0_closure_status.py --json`를 실행하면 P0-1 open을 보고하는 것이 정상이다. release asset listing, upload plan, metadata preflight, hydrated artifact root, `--tag-ref-present`를 함께 넘기면 overall P0는 closed다.
- P1은 quality/fallback/benchmark breadth를 순차적으로 닫아야 하며, heavy validation 전에 [open-data artifact restore runbook](open-data-artifact-restore-runbook.md)과 `scripts/check_p1_readiness_status.py`로 externalized artifact와 real-project seed 준비 상태를 확인한다.
- `scripts/check_p1_benchmark_breadth_status.py`는 tracked commercial readiness, external benchmark submission lifecycle queue, HF benchmark, TPU wind, PEER hinge, irregular top5, Korean public structure collection evidence를 하나로 묶어 P1 benchmark breadth inputs ready와 P0 release blocker를 분리해서 보고한다.
- 상용화 표기는 release-facing 문서 기준으로 `Commercial` grade이지만 과장하지 않는다. `full_commercial_replacement_ready=false`, `engineer_in_loop_accelerated_coverage_ready=true`, accelerated coverage target은 95-99%, residual holdout은 1-5%이며 holdout은 owner/status/work item/SLA/due policy/closure evidence가 보이는 licensed engineer review, legacy tool cross-validation, legal/authority sign-off queue로 운영한다.
- 외부 benchmark submission queue는 residual holdout과 별개로 `hardest_external_10case`, `tpu_hffb`, `peer_spd_hinge`, `korean_public_structures` 4개 one-page lane을 노출하고, evidence가 아직 투입되기 전에는 `receipt_attached=0/4`(EB receipt 0/4) 상태를 유지한다. RH 쪽은 `residual_holdout_closure_updates.json` 같은 closure-update sidecar가 materialize되기 전까지 `closure_evidence_status=pending`이다. work item, submission id, lifecycle status, receipt status/url, owner action, dry-run evidence와 queue-wide `onepage_attestation_status`를 release-gap/committee package에서 함께 본다. 실제 승격 전에는 `scripts/generate_p1_evidence_intake_template.py`로 7개 evidence slot을 만들고, `scripts/build_p1_evidence_sidecar_updates.py --intake-manifest <p1-evidence-intake.json>`로 실제 evidence를 sidecar로 변환한 뒤, `scripts/preflight_p1_evidence_sidecar_intake.py --json --fail-open`로 EB receipt `4/4`와 RH closure evidence `3/3`가 attached/closed인지 다시 확인한다.
- intake가 불완전하거나 로컬 evidence path가 없으면 sidecar builder는 `ERR_P1_EVIDENCE_SIDECAR_BUILD_FAILED`와 machine-readable blockers를 summary JSON에 남긴다. clean checkout chain은 이 실패를 `p1_evidence_sidecar_build` payload로 노출하고 기존 pending sidecar를 자동 승격하지 않는다.
- wind/SSI gate outputs는 `response_artifacts_consumed`를 canonical contract name으로 쓴다. 현재 machine-readable evidence는 rename transition 동안 `_pass` suffix가 붙은 필드를 계속 노출할 수 있다.
- P2는 viewer/report 제품화 단계로, shared selection과 provenance를 전 surface에 통일하고 wall/slab batching/LOD, solver-verified panel-zone, SVG sheet/revision/callout을 정리해야 한다.

## P0-1 Release closure

- 완료 상태: `structural-analysis-artifacts-2026-04-26` GitHub Release object는 current manifest asset set(현재 source manifest 기준 22개)과 metadata preflight, post-publish round-trip JSON, hydrated published-byte SHA/bytes verification이 일치할 때 P0-1을 닫는다. 로컬 `implementation/phase1/release/`는 여전히 upload source로 쓰지 않는다.
- `scripts/prepare_release_upload_plan.py`는 fresh candidate root에서는 통과하지만, stale local release에 대해서는 mismatched/missing assets를 정확히 실패시킨다.
- 닫힘 기준: `scripts/build_release_publication_candidate.py`로 private work dir과 flat artifact root 생성 -> candidate manifest 검증 -> GitHub Release 생성 -> `scripts/publish_github_release_assets.py`로 current manifest asset set만 업로드 -> metadata preflight -> `scripts/hydrate_github_release_assets.py --out <post-publish-roundtrip.json>`로 published asset 재다운로드 -> SHA/bytes verification 통과 순서로 고정한다.
- 자동 검증 가능한 단계는 manifest structure, flat root materialization preflight, asset listing, SHA/bytes verification이다.
- 전체 P0 판정은 `scripts/check_p0_closure_status.py`로 고정한다. release asset listing 없이 실행하면 P0-1 open, P0-2~P0-6 closed 상태를 명시적으로 보고한다.
- 수작업/외부 의존 단계는 fresh release output 재생성과 GitHub Release publication이다. 로컬 토큰이 없을 때는 `Publish Release Assets` GitHub Actions workflow가 Actions `GITHUB_TOKEN`으로 release 생성, current manifest asset set 업로드, release-side hydration/SHA 검증, release closure 검증, 선택적 manifest promotion을 수행한다.
- `Regenerate release viewer artifacts`는 clean checkout 기준으로 동작해야 하므로 KDS/frontend compliance 이전에 PBD review package와 PBD compliance slice를 다시 materialize한다. 이때 release tree를 소스로 쓰지 않고 tracked NDTHA evidence와 `implementation/phase1/release_evidence/kds/`의 작은 source evidence만 사용한다.
- MIDAS KDS row-provenance export는 compact PASS report만 `implementation/phase1/release_evidence/kds/midas_kds_row_provenance_table_report.json`로 hydrate한다. 대형 row table/CSV 전체를 source repo로 되돌리지 않고도 workflow productization과 phase1 CI가 clean checkout에서 같은 provenance 계약을 검증할 수 있게 한다.
- clean checkout에서는 `python3 scripts/materialize_clean_checkout_evidence_chain.py --p0-status <p0-status.json> --p1-operational-queues-out <p1-operational-queues.json> --p1-evidence-intake-template-out <p1-evidence-intake.template.json> --json --out <clean-checkout-evidence-chain.json>` 한 번으로 MIDAS/KDS validation evidence, commercial readiness evidence, parser coverage, PEER metric records, row provenance, P1 readiness/breadth status, P1 operational queue, EB/RH evidence intake template를 같은 순서로 materialize한다. 완성된 `p1-evidence-intake.json`가 있을 때는 같은 chain에 `--p1-evidence-intake <p1-evidence-intake.json> --p1-evidence-sidecar-build-summary-out <p1-evidence-sidecar-build-summary.json>`를 추가해서 EB/RH sidecar build와 preflight까지 이어간다. 이 chain의 `contract_pass`는 P0 closure evidence가 실제로 소비되고 P1 execution/breadth가 unblocked일 때만 true다. `external_benchmark_submission_updates.json`는 EB receipt/update sidecar, `residual_holdout_closure_updates.json`는 RH closure-update sidecar로 취급하고, 둘 다 들어오기 전에는 `receipt_pending=4`와 `closure_evidence_status=pending`이 그대로 남는다. 실제 evidence 승격 상태는 같은 payload의 `p1_evidence_intake_ready`와 `p1_evidence_sidecar_preflight`에서 별도로 본다.
- `commercial_csv_gate`는 clean checkout에서 필수 sidecar인 `member_force_soft_accept_report.json`가 없으면 재사용이 막히므로, CPU-required release runner에서는 `implementation/phase1/release_evidence/commercial/`의 checked-in commercial evidence와 member-force sidecar를 먼저 materialize한다.
- `commercial_readiness_gate`는 RWTH/Atwood benchmark breadth를 유지하지만 GitHub-hosted CPU runner에서 torch-dependent training을 재수행하지 않는다. CPU-required release runner는 `implementation/phase1/release_evidence/commercial/commercial_readiness_report.json`을 materialize하고, full refresh는 torch-capable validation lane에서 수행한다.
- CPU-required GitHub runner에서는 GPU-only solver HIP e2e proof를 재생성하지 않는다. 대신 `implementation/phase1/release_evidence/gpu/solver_hip_e2e_contract_report.json`를 materialize하고, GPU evidence refresh는 별도 GPU-capable validation으로 분리한다.
- `performance_profiling_gate`는 clean checkout에서 `gpu_bottleneck_audit`, `ssi_boundary`, `contact_readiness`, `foundation_soil_link` 입력이 비면 false negative가 난다. CPU-required release runner는 `implementation/phase1/release_evidence/performance/`의 checked-in performance evidence를 먼저 materialize한 뒤 performance profiling과 downstream surface/solver gates를 실행한다.
- `surface_interaction_benchmark_gate`, `solver_breadth_gate`, solver-truthfulness, `element_material_breadth_gate`, material constitutive gates, structural contact gate는 clean checkout에서 joint-panel/direct-contact matrix가 부분 재생성되거나 core breadth/material/contact sidecar가 빠지면 false negative가 난다. CPU-required release runner는 `implementation/phase1/release_evidence/surface/`의 checked-in general-FE, surface-interaction, solver-breadth, solver-truthfulness, element/material breadth, material/steel-composite constitutive, structural contact evidence를 materialize하고, full refresh는 heavy validation lane으로 분리한다.
- `midas_interoperability_gate`는 clean checkout에서 preview/LOADCOMB round-trip 산출물을 release tree에서 다시 찾으면 false negative가 난다. CPU-required release runner는 `implementation/phase1/release_evidence/midas/midas_interoperability_gate_report.json`을 materialize하고, exact roundtrip refresh는 MIDAS validation lane에서 수행한다.
- `midas_native_writeback_diff_receipts`와 `midas_native_roundtrip_gate`도 clean checkout에서 release-sidecar diff receipt를 재생성하지 않는다. CPU-required release runner는 `implementation/phase1/release_evidence/midas/`의 write-back receipts와 native roundtrip evidence를 materialize하고, native write-back refresh는 MIDAS validation lane으로 분리한다.
- MIDAS exact-roundtrip closure, load-combination engine gate, MIDAS-KDS exact geometry bridge evidence도 `implementation/phase1/release_evidence/midas/`에서 materialize한다. 이로써 phase1 CI와 P0 closure가 ignored top-level generated report 없이도 clean checkout에서 같은 MIDAS closure 계약을 읽는다.
- `workflow_productization_gate`는 clean checkout에서 viewer/authoring sidecar가 아직 재생성되기 전에 실행되므로 false negative가 날 수 있다. CPU-required release runner는 `implementation/phase1/release_evidence/productization/workflow_productization_gate_report.json`을 materialize하고, authoring automation refresh는 productization validation lane에서 수행한다.
- `phase3_pipeline_nightly`는 top-k benchmark 학습에 torch가 필요하고 10M scale repro/NDTHA long profile은 CPU runner에서 publication 중 재실행하기에 너무 무겁다. CPU-required release runner는 `implementation/phase1/release_evidence/productization/`의 phase3, nightly 10M, NDTHA long-profile PASS evidence를 materialize하고 heavy refresh는 validation lane에 둔다.
- `hardest_external_10case_kickoff_gate`는 publication-hydrated heavy reports만 보고 재판정하면 start-readiness false negative가 날 수 있다. CPU-required release runner는 `implementation/phase1/release_evidence/productization/hardest_external_10case_kickoff_gate_report.json`을 materialize하고, external kickoff refresh는 benchmark/productization validation lane에서 수행한다.
- `design_optimization_cost_reduction_smoke`는 clean checkout에서 release-side solver-loop NPZ를 다시 찾으면 false negative가 난다. CPU-required release runner는 `implementation/phase1/release_evidence/productization/design_optimization_cost_reduction_smoke_report.json`을 materialize하고, solver-loop smoke refresh는 design optimization validation lane에서 수행한다.
- `design_optimization_cost_reduction_changes.json`과 `design_optimization_cost_reduction_blocked_actions.json`은 PASS report가 아니라 projection/MGT export/foundation review 입력 payload다. CPU-required release runner는 두 payload를 generic file materializer로 복원한다.
- Committee review package, committee summary, authority-catalog routing diff는 final snapshot과 viewer/registry provenance가 공유하는 governance evidence다. CPU-required release runner는 `implementation/phase1/release_evidence/productization/`에서 이 세 파일을 hydrate하고, PDF/HTML 같은 대형 납품 산출물은 release asset 경계에 둔다.
- `--skip-promotion` publication lane은 실제 promotion을 하지 않는다. 대신 `release_candidate_promotion_report.json`에 deterministic skipped-promotion marker를 써서 release-gap report가 promotion evidence contract를 읽을 수 있게 한다.
- remote safety는 `origin`과 `structural`을 모두 `betelgeuze-kang/Structural-Analysis`로 맞추고, `scripts/check_git_remote_safety.py`로 예전 Monet-wedding target 재유입을 막는다.
- 운영 절차는 [release publication runbook](release-publication-runbook.md)에서 그대로 따른다.

## 재실행 및 확인 순서

1. `Publish Release Assets` workflow를 GitHub Actions UI에서 다시 실행하거나, `python3 scripts/dispatch_release_publish_workflow.py --allow-gh-auth-token --dry-run --json` 후 같은 명령에서 `--dry-run`만 빼고 다시 dispatch한다. env token을 쓰는 runner라면 `GITHUB_TOKEN=<token> python3 scripts/dispatch_release_publish_workflow.py --json`를 사용한다.
2. 로그에 `Node20` warning이 보여도 그것만으로 실패로 판단하지 말고, 실제 step exit code와 증빙 artifact를 확인한다.
3. `Regenerate release viewer artifacts` 단계가 실패하면 로그의 `Nightly release gate summary:` 블록을 열고, `release-publication-evidence` artifact 안의 `implementation/phase1/release/nightly_release_gate_report.json`을 확인한다.
4. publication이 성공하면 `python3 scripts/hydrate_github_release_assets.py --repo <owner/name> --manifest <candidate-manifest.json> --artifact-root <hydrated-root> --write`와 `python3 scripts/verify_release_artifacts_manifest.py --manifest <candidate-manifest.json> --artifact-root <hydrated-root>`로 GitHub Release에 올라간 실제 bytes를 먼저 확인한다.
5. 그 다음 `python3 scripts/check_p0_closure_status.py --manifest <candidate-manifest.json> --release-assets-json <release-assets.json> --artifact-root <fresh-root> --upload-plan-json <release-upload-plan.json> --metadata-preflight-json <metadata-preflight.json> --post-publish-roundtrip-json <post-publish-roundtrip.json> --tag-ref-present --json --out <p0-status.json> --out-md <p0-status.md> --fail-open`으로 overall P0를 확인한다.
6. P0가 closed일 때만 `python3 scripts/check_p1_readiness_status.py --p0-status <p0-status.json> --json --out <p1-readiness-status.json> --out-md <p1-readiness-status.md> --fail-blocked`를 먼저 실행한다.
7. 그 다음 `python3 scripts/check_p1_benchmark_breadth_status.py --p1-readiness-status <p1-readiness-status.json> --json --out <p1-benchmark-breadth-status.json> --out-md <p1-benchmark-breadth-status.md> --fail-blocked`로 P1 quality/fallback/benchmark breadth 상태를 확인한다.
8. `python3 scripts/materialize_p1_operational_queues.py --p1-benchmark-breadth-status <p1-benchmark-breadth-status.json> --json --out <p1-operational-queues.json> --out-md <p1-operational-queues.md> --fail-open`로 external submission lane과 residual holdout work item을 같은 운영 backlog로 materialize한다.

## P1/P2 작업 순서

P0-1이 닫힌 뒤에는 core fidelity를 재작업하지 말고, 이미 닫힌 evidence를 유지하면서 P1/P2 breadth로 넘어간다.

P1 상용화 코어 순서는 `MIDAS exact roundtrip -> KDS load combination -> geometry identity -> row provenance`로 고정한다.

1. P1 quality/fallback/benchmark breadth
2. real-project row provenance and parser breadth hardening
3. viewer shared selection/provenance, wall/slab batching/LOD, solver-verified panel-zone, SVG sheet/revision/callout

- MIDAS exact roundtrip, KDS load combinations, MIDAS-KDS geometry identity, constitutive libraries, element/solver engine은 P0-2~P0-6 evidence로 닫힌 상태를 유지한다.
- 1~2는 P1 reliability/validation slice다.
- 3은 P2 productization slice다.

## Do Not Do

- KONEPS/PEER assets는 provenance/license/manual-review gate 없이 재배포하지 않는다.
- private `.pem`과 heavy raw artifacts는 커밋하지 않는다.

## 다음 5개 작업

1. 현재 feature branch를 promoted manifest commit 위로 정리하거나, `--promoted-manifest-json`로 published manifest evidence를 명시해서 stale local manifest가 P0를 다시 열지 않게 한다.
2. `scripts/materialize_clean_checkout_evidence_chain.py --p0-status <p0-status.json> --p1-readiness-out <p1-readiness-status.json> --p1-benchmark-out <p1-benchmark-breadth-status.json> --p1-operational-queues-out <p1-operational-queues.json> --p1-operational-queues-out-md <p1-operational-queues.md> --p1-evidence-intake-template-out <p1-evidence-intake.template.json> --p1-evidence-intake-template-out-md <p1-evidence-intake.template.md> --json --out <clean-checkout-evidence-chain.json>`로 clean checkout P1 handoff와 evidence intake template 생성을 한 커맨드로 재현한다. 실제 evidence를 채운 뒤에는 `--p1-evidence-intake <p1-evidence-intake.json> --p1-evidence-sidecar-build-summary-out <p1-evidence-sidecar-build-summary.json>`를 추가해 EB/RH sidecar build와 preflight를 같은 chain에서 재실행한다.
3. P1 quality/fallback/benchmark breadth 실행을 refresh하고 `preview_external_benchmark_submission_after_review_updates.py`로 external benchmark review updates/receipts의 preview를 확인한 뒤 hardest 10-case, PEER/SPD, TPU/HFFB, Korean public structures submission queue의 submission id/receipt/lifecycle과 one-page attestation을 최신 evidence로 갱신한다.
4. `materialize_p1_operational_queues.py`로 `external_benchmark_submission_queue/*.receipt_template.json`와 `residual_holdout_queue/*.closure_packet_template.json` sidecar를 생성하고, `licensed_engineer_review_required`, `legacy_tool_cross_validation_required`, `legal_authority_signoff_required`를 owner/status/work item/SLA/due policy/closure evidence packet template가 있는 residual holdout work queue로 운영한다. 하드 구현이 붙일 RH closure-update sidecar 이름은 `residual_holdout_closure_updates.json`으로 맞춘다.
5. `scripts/generate_p1_evidence_intake_template.py --p1-operational-queues <p1-operational-queues.json> --out <p1-evidence-intake.template.json> --out-md <p1-evidence-intake.template.md>`로 EB/RH evidence intake template를 만들고, 실제 evidence를 채운 뒤 `scripts/build_p1_evidence_sidecar_updates.py --intake-manifest <p1-evidence-intake.json> --require-complete --fail-open --json`로 EB receipt URL/path와 RH closure evidence path를 sidecar로 변환한다. `scripts/preflight_p1_evidence_sidecar_intake.py --external-benchmark-submission-updates <external_benchmark_submission_updates.json> --residual-holdout-closure-updates <residual_holdout_closure_updates.json> --json --fail-open`가 통과한 뒤에만 상용화 claim을 L4/L5 쪽으로 올린다. release package, committee package, README가 `Commercial` grade와 `full_commercial_replacement_ready=false`를 계속 같이 노출하는지도 회귀 테스트로 고정한다.

## 참고 문서

- [Viewer contract](viewer-contract.md)
- [Open-data artifact restore runbook](open-data-artifact-restore-runbook.md)
- [Frontend visualization next steps](frontend-visualization-next-steps.md)
- [Frontend visualization improvement plan](frontend-visualization-improvement-plan.md)
- [Commercialization execution roadmap](../implementation/phase1/commercialization-execution-roadmap.md)
- [Red team playbook](../implementation/phase1/commercialization-gap-redteam-playbook.md)
- [README](../README.md)
