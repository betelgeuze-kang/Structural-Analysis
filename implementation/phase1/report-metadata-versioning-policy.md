# Report Metadata Versioning Policy (Phase1)

대상 리포트:
- `lf_to_gnn_e2e_smoke_report.json`
- `ci_gate_report.json`
- `static_artifact_validation_report.json`
- `dynamics_boundary_report.json`
- `pg_gat_contract_report.json`
- `subgraph_projection_report.json`
- `soa_dlpack_contract_report.json`

## Required metadata
- `schema_version`
- `run_id`
- `generated_at` (ISO-8601 UTC)

## Version bump rules
- **major**: required key 삭제/이름 변경/타입 변경 (하위호환 깨짐)
- **minor**: optional key 추가, 새 하위 객체 추가 (하위호환 유지)
- **patch**: 설명/문구/내부 계산식 변경으로 schema 불변

## Validation rule
`validate_phase1_artifacts.py`는 위 메타 필드 누락 시 FAIL 처리한다.
