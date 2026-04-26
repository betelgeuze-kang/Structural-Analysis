# 동역학/경계조건 계약 (Phase1 static contract)

모바일/정적 개발환경에서 Rust/HIP 실커널 없이도 인터페이스를 고정하기 위한 계약 문서.

## 목표
- 경계조건(고정단/힌지/롤러)과 동역학 항(M, C, K, 외력)의 필수 필드를 선고정
- LF 출력/PG-GAT/분할사영 단계에서 동일 키를 참조하도록 통일
- **철도 궤도(track) 및 터널(tunnel) 도메인 동역학 계약 확장**

## 도메인 타입 (`domain_type`)
- `building`: 건축 구조물 (기존)
- `track`: 철도 궤도 (궤도-차량 상호작용 VTI)
- `tunnel`: 터널 구조체 (지반-터널 SSI)
- `coupled`: 복합 연성계 (건축물+궤도+터널)

## 경계조건 타입 (`support_type`)
- `fixed`: Cα/SC 모두 위치 업데이트 금지
- `hinge`: Cα 고정, SC 회전 자유
- `roller`: 축 하나만 구속(예: z)
- `elastic_foundation`: Winkler/Pasternak 탄성기초 (궤도/터널 노드)
- `segment_joint`: 터널 세그먼트 조인트 (비선형 회전 스프링)
- `rail_fastener`: 레일 체결장치 (궤도 노드 ↔ 침목 연결)

## 노드 필수 필드
- `node_id` (string)
- `mass` (number, >= 0)
- `is_fixed_mask` (bool)
- `support_type` (`fixed|hinge|roller|free|elastic_foundation|segment_joint|rail_fastener`)
- `dof_lock` (object: `ux,uy,uz,rx,ry,rz` bool)
- `foundation_stiffness` (optional, 궤도/터널: `k_vertical`, `k_shear`, `c_vertical`)

## 동역학 필수 필드
- `damping_model` (`rayleigh|modal|none|track_vti|tunnel_ssi`)
- `alpha_m`, `beta_k` (number, >= 0)
- `time_step_dt` (number, > 0)
- `external_force_profile` (`dead|wind|seismic|combined|train_passage|track_irregularity|tunnel_pressure_wave`)

## 차량 모델 참조 (domain_type=track|coupled)
- `vehicle.vehicle_schema_ref`: `vehicle_model_schema.json` 경로

## 터널 모델 참조 (domain_type=tunnel|coupled)
- `tunnel.tunnel_schema_ref`: `tunnel_lining_schema.json` 경로

## 출력 계약(예시)
- `dynamics_boundary_report.json`
  - `interface_version`
  - `domain_type`
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
- `ERR_DOMAIN_TYPE_MISSING`
- `ERR_VEHICLE_REF_MISSING` — domain=track/coupled인데 vehicle 참조 없음
- `ERR_TUNNEL_REF_MISSING` — domain=tunnel/coupled인데 tunnel 참조 없음
- `ERR_FOUNDATION_STIFFNESS_INVALID` — elastic_foundation 노드에 강성 누락/음수
- `ERR_IMPEDANCE_RANGE_INVALID` — 주파수 의존 임피던스 범위 오류

