# 상용화 갭 현재상태 보고서

- 기준일: 2026-04-30
- 목적: P0 hygiene inventory 이후, 상용 구조해석 툴(MIDAS/ETABS/SAP2000/OpenSees) 대비 현재 상태와 다음 작업 순서를 고정한다.

## 한 줄 요약

source boundary는 닫혔고, release P0-1만 아직 열려 있다. 이 갭은 source boundary 갭이 아니라 release publication 갭이며, 닫힘 기준은 fresh artifact root, 12개 manifest asset, metadata preflight, SHA/bytes verification이다.

## 현재 상태

- `scripts/check_repo_hygiene.py --strict-source-boundary`는 통과했고, tracked stress/workspace/output/rust target 정리는 끝났다.
- `scripts/plan_source_boundary_cleanup.py --large-file-threshold-mib 25`는 0 candidates를 보고했다.
- `implementation/phase1/open_data_external_artifacts_manifest.json`는 SHA/bytes가 붙은 8개 externalized open-data assets를 기록한다.
- 자동 검증으로 닫힌 범위는 source boundary, repo hygiene, open-data externalization manifest다.
- 아직 수작업/외부 자산 의존으로 열린 범위는 release P0-1 publication이다.
- P0는 source boundary 관점에서는 닫혔지만, release P0-1은 아직 열려 있다.
- P1은 MIDAS/KDS/geometry/constitutive/element 수준의 core fidelity와 quality/fallback/benchmark breadth를 순차적으로 닫아야 한다.
- P2는 viewer/report 제품화 단계로, shared selection과 provenance를 전 surface에 통일하고 wall/slab batching/LOD, solver-verified panel-zone, SVG sheet/revision/callout을 정리해야 한다.

## P0-1 Release closure

- 미완 이유: `structural-analysis-artifacts-2026-04-26` Git tag는 푸시됐지만, GitHub Release object와 12개 manifest asset 업로드가 아직 완료되지 않았다. 로컬 `implementation/phase1/release/`는 stale 상태이므로 업로드 소스로 쓰지 않는다.
- `scripts/prepare_release_upload_plan.py`는 fresh candidate root에서는 통과하지만, stale local release에 대해서는 mismatched/missing assets를 정확히 실패시킨다.
- 닫힘 기준: `scripts/build_release_publication_candidate.py`로 private work dir과 flat artifact root 생성 -> candidate manifest 검증 -> GitHub Release 생성 -> `scripts/publish_github_release_assets.py`로 manifest asset 정확히 12개 업로드 -> metadata preflight -> SHA/bytes verification 통과 순서로 고정한다.
- 자동 검증 가능한 단계는 manifest structure, flat root materialization preflight, asset listing, SHA/bytes verification이다.
- 수작업/외부 의존 단계는 fresh release output 재생성, GitHub tag/release publication, 그리고 실제 자산 업로드 과정이다.
- remote safety는 `origin`과 `structural`을 모두 `betelgeuze-kang/Structural-Analysis`로 맞추고, `scripts/check_git_remote_safety.py`로 예전 Monet-wedding target 재유입을 막는다.

## P1/P2 작업 순서

P0-1이 닫힌 뒤의 다음 순서다.

1. MIDAS exact roundtrip
2. KDS load combinations
3. MIDAS-KDS geometry identity
4. constitutive libraries
5. element/solver engine
6. P1 quality/fallback/benchmark breadth
7. viewer shared selection/provenance, wall/slab batching/LOD, solver-verified panel-zone, SVG sheet/revision/callout

- 1~5는 P1 core fidelity slice다.
- 6은 P1 reliability/validation slice다.
- 7은 P2 productization slice다.

## Do Not Do

- KONEPS/PEER assets는 provenance/license/manual-review gate 없이 재배포하지 않는다.
- private `.pem`과 heavy raw artifacts는 커밋하지 않는다.

## 다음 5개 작업

1. fresh artifact root를 다시 생성하고, 필요하면 manifest를 갱신한 뒤 GitHub Release object를 만든다.
2. `scripts/publish_github_release_assets.py`로 manifest asset 정확히 12개를 업로드하고 metadata preflight와 SHA/bytes verification을 통과시켜 release P0-1을 닫는다.
3. `scripts/check_repo_hygiene.py --strict-source-boundary`와 `scripts/plan_source_boundary_cleanup.py --large-file-threshold-mib 25`를 반복 가능한 gate로 유지한다.
4. externalized open-data artifacts를 GitHub Releases 또는 source-family artifact cache에서 복원하는 heavy-validation runbook을 추가한다.
5. `scripts/check_git_remote_safety.py --show-ok`를 CI/local gate로 유지한 뒤 MIDAS exact roundtrip -> KDS load combinations -> geometry identity 작업 묶음을 시작한다.

## 참고 문서

- [Viewer contract](viewer-contract.md)
- [Frontend visualization next steps](frontend-visualization-next-steps.md)
- [Frontend visualization improvement plan](frontend-visualization-improvement-plan.md)
- [Commercialization execution roadmap](../implementation/phase1/commercialization-execution-roadmap.md)
- [Red team playbook](../implementation/phase1/commercialization-gap-redteam-playbook.md)
- [README](../README.md)
