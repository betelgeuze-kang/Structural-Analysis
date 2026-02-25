# 모바일 정적 리뷰 체크리스트 (Phase1)

## 공통
- [ ] 리포트 JSON에 `reason_code`/`reason` 존재
- [ ] `interface_version`/`model_api_version` 존재
- [ ] 샘플 아티팩트가 문서 명령과 일치

## Step1 동역학/경계조건
- [ ] `dynamics_boundary_report.json`의 `contract_pass=true`
- [ ] support_type enum 위반 없음

## Step2 PG-GAT
- [ ] `pg_gat_contract_report.json`의 `attention_policy` 존재
- [ ] dense/sparse 분리 정책 값 검토

## Step3 분할 사영
- [ ] `subgraph_projection_report.json`의 `projection_mode=subgraph_divide_and_conquer`
- [ ] subgraph_count >= 1

## Step4 SoA/DLPack
- [ ] `soa_dlpack_contract_report.json`의 `layout=SoA`, `layout_pass=true`

## Step5 정적 게이트
- [ ] `phase1_ci_gate.py` 실행 시 `contract_artifacts_pass` 필드 확인
- [ ] `validate_phase1_artifacts.py` 통과
