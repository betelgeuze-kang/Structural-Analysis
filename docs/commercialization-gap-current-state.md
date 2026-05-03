# 상용화 갭 현재상태 보고서

- 기준일: 2026-04-30
- 목적: P0 hygiene inventory 이후, 상용 구조해석 툴(MIDAS/ETABS/SAP2000/OpenSees) 대비 현재 상태와 다음 작업 순서를 고정한다.

## 한 줄 요약

source boundary와 P0-2~P0-6 core evidence는 닫혔고, release P0-1만 아직 열려 있다. 이 갭은 source boundary 갭이 아니라 release publication 갭이며, 닫힘 기준은 fresh artifact root, 12개 manifest asset, metadata preflight, SHA/bytes verification이다.

## 현재 상태

- `scripts/check_repo_hygiene.py --strict-source-boundary`는 통과했고, tracked stress/workspace/output/rust target 정리는 끝났다.
- `scripts/plan_source_boundary_cleanup.py --large-file-threshold-mib 25`는 0 candidates를 보고했다.
- `implementation/phase1/open_data_external_artifacts_manifest.json`는 SHA/bytes가 붙은 8개 externalized open-data assets를 기록한다.
- 자동 검증으로 닫힌 범위는 source boundary, repo hygiene, open-data externalization manifest다.
- 아직 수작업/외부 자산 의존으로 열린 범위는 release P0-1 publication이다.
- `python3 scripts/check_p0_closure_status.py --json`는 P0-2 MIDAS exact roundtrip, P0-3 KDS load combination, P0-4 MIDAS-KDS geometry identity, P0-5 constitutive libraries, P0-6 element/solver evidence를 closed로 묶어 보고한다.
- P0는 core evidence 관점에서는 닫혔지만, release P0-1 publication이 open이므로 overall P0는 아직 open이다.
- P1은 quality/fallback/benchmark breadth를 순차적으로 닫아야 하며, heavy validation 전에 [open-data artifact restore runbook](open-data-artifact-restore-runbook.md)과 `scripts/check_p1_readiness_status.py`로 externalized artifact와 real-project seed 준비 상태를 확인한다.
- `scripts/check_p1_benchmark_breadth_status.py`는 tracked commercial readiness, HF benchmark, TPU wind, PEER hinge, irregular top5, Korean public structure collection evidence를 하나로 묶어 P1 benchmark breadth inputs ready와 P0 release blocker를 분리해서 보고한다.
- wind/SSI gate outputs는 `response_artifacts_consumed`를 canonical contract name으로 쓴다. 현재 machine-readable evidence는 rename transition 동안 `_pass` suffix가 붙은 필드를 계속 노출할 수 있다.
- P2는 viewer/report 제품화 단계로, shared selection과 provenance를 전 surface에 통일하고 wall/slab batching/LOD, solver-verified panel-zone, SVG sheet/revision/callout을 정리해야 한다.

## P0-1 Release closure

- 미완 이유: `structural-analysis-artifacts-2026-04-26` Git tag는 푸시됐지만, GitHub Release object와 12개 manifest asset 업로드가 아직 완료되지 않았다. 로컬 `implementation/phase1/release/`는 stale 상태이므로 업로드 소스로 쓰지 않는다.
- `scripts/prepare_release_upload_plan.py`는 fresh candidate root에서는 통과하지만, stale local release에 대해서는 mismatched/missing assets를 정확히 실패시킨다.
- 닫힘 기준: `scripts/build_release_publication_candidate.py`로 private work dir과 flat artifact root 생성 -> candidate manifest 검증 -> GitHub Release 생성 -> `scripts/publish_github_release_assets.py`로 manifest asset 정확히 12개 업로드 -> metadata preflight -> `scripts/hydrate_github_release_assets.py`로 published asset 재다운로드 -> SHA/bytes verification 통과 순서로 고정한다.
- 자동 검증 가능한 단계는 manifest structure, flat root materialization preflight, asset listing, SHA/bytes verification이다.
- 전체 P0 판정은 `scripts/check_p0_closure_status.py`로 고정한다. release asset listing 없이 실행하면 P0-1 open, P0-2~P0-6 closed 상태를 명시적으로 보고한다.
- 수작업/외부 의존 단계는 fresh release output 재생성과 GitHub Release publication이다. 로컬 토큰이 없을 때는 `Publish Release Assets` GitHub Actions workflow가 Actions `GITHUB_TOKEN`으로 release 생성, 12개 asset 업로드, release-side hydration/SHA 검증, release closure 검증, 선택적 manifest promotion을 수행한다.
- `Regenerate release viewer artifacts`는 clean checkout 기준으로 동작해야 하므로 KDS/frontend compliance 이전에 PBD review package와 PBD compliance slice를 다시 materialize한다. 이때 release tree를 소스로 쓰지 않고 tracked NDTHA evidence와 `implementation/phase1/release_evidence/kds/`의 작은 source evidence만 사용한다.
- `commercial_csv_gate`는 clean checkout에서 필수 sidecar인 `member_force_soft_accept_report.json`가 없으면 재사용이 막히므로, CPU-required release runner에서는 `implementation/phase1/release_evidence/commercial/`의 checked-in commercial evidence와 member-force sidecar를 먼저 materialize한다.
- `commercial_readiness_gate`는 RWTH/Atwood benchmark breadth를 유지하지만 GitHub-hosted CPU runner에서 torch-dependent training을 재수행하지 않는다. CPU-required release runner는 `implementation/phase1/release_evidence/commercial/commercial_readiness_report.json`을 materialize하고, full refresh는 torch-capable validation lane에서 수행한다.
- CPU-required GitHub runner에서는 GPU-only solver HIP e2e proof를 재생성하지 않는다. 대신 `implementation/phase1/release_evidence/gpu/solver_hip_e2e_contract_report.json`를 materialize하고, GPU evidence refresh는 별도 GPU-capable validation으로 분리한다.
- `performance_profiling_gate`는 clean checkout에서 `gpu_bottleneck_audit`, `ssi_boundary`, `contact_readiness`, `foundation_soil_link` 입력이 비면 false negative가 난다. CPU-required release runner는 `implementation/phase1/release_evidence/performance/`의 checked-in performance evidence를 먼저 materialize한 뒤 performance profiling과 downstream surface/solver gates를 실행한다.
- remote safety는 `origin`과 `structural`을 모두 `betelgeuze-kang/Structural-Analysis`로 맞추고, `scripts/check_git_remote_safety.py`로 예전 Monet-wedding target 재유입을 막는다.
- 운영 절차는 [release publication runbook](release-publication-runbook.md)에서 그대로 따른다.

## 재실행 및 확인 순서

1. `Publish Release Assets` workflow를 GitHub Actions UI에서 다시 실행하거나, `python3 scripts/dispatch_release_publish_workflow.py --dry-run --json` 후 `GITHUB_TOKEN=<token> python3 scripts/dispatch_release_publish_workflow.py --json`로 다시 dispatch한다.
2. 로그에 `Node20` warning이 보여도 그것만으로 실패로 판단하지 말고, 실제 step exit code와 증빙 artifact를 확인한다.
3. `Regenerate release viewer artifacts` 단계가 실패하면 로그의 `Nightly release gate summary:` 블록을 열고, `release-publication-evidence` artifact 안의 `implementation/phase1/release/nightly_release_gate_report.json`을 확인한다.
4. publication이 성공하면 `python3 scripts/hydrate_github_release_assets.py --repo <owner/name> --manifest <candidate-manifest.json> --artifact-root <hydrated-root> --write`와 `python3 scripts/verify_release_artifacts_manifest.py --manifest <candidate-manifest.json> --artifact-root <hydrated-root>`로 GitHub Release에 올라간 실제 bytes를 먼저 확인한다.
5. 그 다음 `python3 scripts/check_p0_closure_status.py --manifest <candidate-manifest.json> --release-assets-json <release-assets.json> --artifact-root <fresh-root> --tag-ref-present --json --out <p0-status.json> --out-md <p0-status.md> --fail-open`으로 overall P0를 확인한다.
6. P0가 closed일 때만 `python3 scripts/check_p1_readiness_status.py --p0-status <p0-status.json> --json --out <p1-readiness-status.json> --out-md <p1-readiness-status.md> --fail-blocked`를 먼저 실행한다.
7. 그 다음 `python3 scripts/check_p1_benchmark_breadth_status.py --p1-readiness-status <p1-readiness-status.json> --json --out <p1-benchmark-breadth-status.json> --out-md <p1-benchmark-breadth-status.md> --fail-blocked`로 P1 breadth 상태를 확인한다.

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

1. fresh artifact root를 다시 생성하고, 필요하면 manifest를 갱신한 뒤 GitHub Release object를 만든다.
2. `scripts/publish_github_release_assets.py`로 manifest asset 정확히 12개를 업로드하고, `scripts/hydrate_github_release_assets.py`로 published asset을 재다운로드해 metadata preflight와 SHA/bytes verification을 통과시켜 release P0-1을 닫는다.
3. `scripts/check_p0_closure_status.py --manifest <candidate-manifest.json> --release-assets-json <release-assets.json> --artifact-root <fresh-root> --tag-ref-present --json --out <p0-status.json> --out-md <p0-status.md> --fail-open`로 candidate manifest 기준 overall P0 closure를 판정한다.
4. `scripts/check_repo_hygiene.py --strict-source-boundary`와 `scripts/plan_source_boundary_cleanup.py --large-file-threshold-mib 25`를 반복 가능한 gate로 유지한다.
5. `scripts/check_p1_readiness_status.py --p0-status <p0-status.json> --json --out <p1-readiness-status.json> --out-md <p1-readiness-status.md> --fail-blocked`를 먼저 실행하고, 그다음 `scripts/check_p1_benchmark_breadth_status.py --p1-readiness-status <p1-readiness-status.json> --json --out <p1-benchmark-breadth-status.json> --out-md <p1-benchmark-breadth-status.md> --fail-blocked`로 P1 inputs/benchmark breadth ready와 P0 release blocker를 분리해서 확인한 뒤 P1 breadth로 넘어간다.

## 참고 문서

- [Viewer contract](viewer-contract.md)
- [Open-data artifact restore runbook](open-data-artifact-restore-runbook.md)
- [Frontend visualization next steps](frontend-visualization-next-steps.md)
- [Frontend visualization improvement plan](frontend-visualization-improvement-plan.md)
- [Commercialization execution roadmap](../implementation/phase1/commercialization-execution-roadmap.md)
- [Red team playbook](../implementation/phase1/commercialization-gap-redteam-playbook.md)
- [README](../README.md)
