# Fallback Policy Spec (Phase1)

모바일/정적 개발환경에서도 Gate 입력 계약을 고정하기 위한 정책 스펙입니다.

## Required keys
- `policy_version` (string)
- `enable_hf_fallback` (bool)
- `equilibrium_residual_threshold` (number, >= 0)
- `subgraph_selector` (string)
- `max_subgraphs_per_iteration` (int, >= 1)

## Gate report linkage
`run_phase1_steps.py`의 `step6_gate_report.json`에 아래 필드가 포함됩니다.
- `fallback_policy_loaded`
- `fallback_policy_version`
- `fallback_policy_fingerprint`

`fallback_policy_fingerprint`는 정책 파일 원문에 대한 sha256 해시 앞 16자입니다.

## Reason
- 정책 드리프트를 코드리뷰에서 추적 가능하게 만들기 위함
- CI/HPC 환경에서 동일 정책이 사용되었는지 비교하기 위함


## 정책-게이트 매핑표

| fallback_policy key | step6_gate_report field | 설명 |
|---|---|---|
| `policy_version` | `fallback_policy_version` | 정책 버전 추적 |
| raw file content | `fallback_policy_fingerprint` | 정책 드리프트 검출 |
| file exists/parsed | `fallback_policy_loaded` | 정책 로드 성공 여부 |
