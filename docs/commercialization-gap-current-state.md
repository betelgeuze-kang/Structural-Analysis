# 상용화 갭 현재상태 보고서

- 기준일: 2026-04-30
- 목적: P0 hygiene inventory 이후, 상용 구조해석 툴(MIDAS/ETABS/SAP2000/OpenSees) 대비 현재 상태와 다음 작업 순서를 고정한다.

## 한 줄 요약

source boundary는 닫혔고, release P0-1만 아직 열려 있다. 상용 납품 기준은 fresh release root와 12개 manifest asset의 검증까지다.

## 현재 상태

- `scripts/check_repo_hygiene.py --strict-source-boundary`는 통과했고, tracked stress/workspace/output/rust target 정리는 끝났다.
- `scripts/plan_source_boundary_cleanup.py --large-file-threshold-mib 25`는 0 candidates를 보고했다.
- `implementation/phase1/open_data_external_artifacts_manifest.json`는 SHA/bytes가 붙은 8개 externalized open-data assets를 기록한다.
- P0는 source boundary 관점에서는 닫혔지만, release P0-1은 아직 열려 있다.
- P1은 MIDAS/KDS/geometry/constitutive/element 수준의 core fidelity를 순차적으로 닫아야 한다.
- P2는 viewer/report 제품화 단계로, shared selection과 provenance를 전 surface에 통일해야 한다.

## P0 blockers

- release P0-1은 아직 열려 있다. GitHub API fetch와 `git ls-remote` 모두 `structural-analysis-artifacts-2026-04-26` tag/release를 찾지 못했고, 로컬 `implementation/phase1/release/`는 stale 상태다.
- `scripts/prepare_release_upload_plan.py`는 stale local release와 mismatched/missing assets 때문에 실패한다. close path는 fresh artifact root 재생성 -> manifest update(필요 시) -> tag/release 생성 -> manifest asset 정확히 12개 업로드 -> metadata preflight -> SHA/bytes verification 순서로 고정한다.
- remote safety는 `origin`과 `structural`을 모두 `betelgeuze-kang/Structural-Analysis`로 맞추고, `scripts/check_git_remote_safety.py`로 예전 Monet-wedding target 재유입을 막는다.

## P1/P2 작업 순서

1. MIDAS exact roundtrip
2. KDS load combinations
3. MIDAS-KDS geometry identity
4. constitutive libraries
5. element/solver engine
6. viewer shared selection/provenance, wall/slab batching/LOD, solver-verified panel-zone, SVG sheet/revision/callout

- 1~5는 P1 core fidelity slice다.
- 6은 P2 productization slice다.

## Do Not Do

- KONEPS/PEER assets는 provenance/license/manual-review gate 없이 재배포하지 않는다.
- private `.pem`과 heavy raw artifacts는 커밋하지 않는다.

## 다음 5개 작업

1. fresh artifact root를 다시 생성하고, 필요하면 manifest를 갱신한 뒤 tag/release를 만든다.
2. manifest asset 정확히 12개를 업로드하고 metadata preflight와 SHA/bytes verification을 통과시켜 release P0-1을 닫는다.
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
