# 동역학/경계조건 계약 (Phase1 static contract)

모바일/정적 개발환경에서 Rust/HIP 실커널 없이도 인터페이스를 고정하기 위한 계약 문서.

## 목표
- 경계조건(고정단/힌지/롤러)과 동역학 항(M, C, K, 외력)의 필수 필드를 선고정
- LF 출력/PG-GAT/분할사영 단계에서 동일 키를 참조하도록 통일

## 경계조건 타입
- `fixed`: Cα/SC 모두 위치 업데이트 금지
- `hinge`: Cα 고정, SC 회전 자유
- `roller`: 축 하나만 구속(예: z)

## 노드 필수 필드
- `node_id` (string)
- `mass` (number, >= 0)
- `is_fixed_mask` (bool)
- `support_type` (`fixed|hinge|roller|free`)
- `dof_lock` (object: `ux,uy,uz,rx,ry,rz` bool)

## 동역학 필수 필드
- `damping_model` (`rayleigh|modal|none`)
- `alpha_m`, `beta_k` (number, >= 0)
- `time_step_dt` (number, > 0)
- `external_force_profile` (`dead|wind|seismic|combined`)

## 출력 계약(예시)
- `dynamics_boundary_report.json`
  - `interface_version`
  - `supports_summary`
  - `damping_summary`
  - `contract_pass`
  - `reason_code`

## reason_code
- `PASS`
- `ERR_NODE_FIELD_MISSING`
- `ERR_SUPPORT_TYPE_INVALID`
- `ERR_DAMPING_INVALID`
- `ERR_DT_INVALID`
