# 상용화 갭 현재상태 보고서

- 기준일: 2026-04-30
- 목적: P0 hygiene inventory 이후, 상용 구조해석 툴(MIDAS/ETABS/SAP2000/OpenSees) 대비 현재 상태와 다음 작업 순서를 고정한다.

## 한 줄 요약

뷰어와 일부 브리지/리포트는 이미 있으나, release 체인, source boundary, 핵심 해석 fidelity, 그리고 P2 viewer/report polish가 아직 완전히 닫히지 않았다.

## 현재 상태

- P0는 아직 열려 있다. 상용 납품 가능 상태로 보기에는 release 검증과 source 경계 정리가 먼저다.
- P1은 MIDAS/KDS/geometry/constitutive/element 수준의 core fidelity를 순차적으로 닫아야 한다.
- P2는 viewer/report 제품화 단계로, shared selection과 provenance를 전 surface에 통일해야 한다.

## P0 blockers

- release는 fresh artifact root, 12 manifest assets, metadata preflight, SHA/bytes verification pass가 모두 끝나기 전에는 close할 수 없다.
- source repo boundary는 `implementation/phase1/stress/`, `implementation/phase1/workspace/`, `implementation/phase1/output/`, `implementation/phase1/rust_hip_md3bead_hook/target/` cleanup pending 상태다.
- 25 MiB를 넘는 tracked files는 externalization vs allowlist 결정을 먼저 내려야 한다.
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

1. 이 보고서를 커밋하고 `README.md`의 문서 목록에 현재상태 링크를 추가한다.
2. fresh artifact root를 다시 받아 12 manifest assets, metadata preflight, SHA/bytes verification으로 release P0-1을 닫는다.
3. `stress/`, `workspace/`, `output/`, `rust target/` 경계를 별도 source-boundary 커밋으로 정리한다.
4. 25 MiB 초과 tracked 파일은 externalization vs allowlist 결정을 기록하고, 결정에 따라 별도 커밋으로 처리한다.
5. `scripts/check_git_remote_safety.py --show-ok`를 CI/local gate로 유지한 뒤 MIDAS exact roundtrip -> KDS load combinations -> geometry identity 작업 묶음을 시작한다.

## 참고 문서

- [Viewer contract](viewer-contract.md)
- [Frontend visualization next steps](frontend-visualization-next-steps.md)
- [Frontend visualization improvement plan](frontend-visualization-improvement-plan.md)
- [Commercialization execution roadmap](../implementation/phase1/commercialization-execution-roadmap.md)
- [Red team playbook](../implementation/phase1/commercialization-gap-redteam-playbook.md)
- [README](../README.md)
