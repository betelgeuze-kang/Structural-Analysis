# Production Ops Security Runbook

- 기준일: 2026-05-18
- 상태: reference gate ready, deployment hardening still required
- 목적: `project_ops_api_service.py` reference control-plane surface를 독립 상용제품 운영 API로 승격하기 위한 보안/운영 닫힘 기준을 고정한다.

## Current Boundary

`implementation/phase1/project_ops_api_service.py`는 bearer token, tenant/actor/request headers, tenant filtering, RBAC-like role checks, audit JSONL, audit digest, rate/request limits, ops policy manifest, license status, telemetry off default, version/update-channel endpoint를 가진 reference API다.

현재 readiness gate에서 닫힌 항목:

- bearer token, tenant/actor/request headers, tenant filtering, admin audit role 계약
- production path의 default HMAC secret 제거
- 인증 활성화 서버는 명시 secret 또는 `PROJECT_OPS_JWT_HMAC_SECRET` 없이는 시작 불가
- tenant/actor rate limit과 request metadata byte limit
- audit JSONL SHA-256 batch digest와 `/audit/digest` admin endpoint
- `/ops/policy` manifest: retention, export, backup, restore, tenant delete policy 표면화
- support bundle과 audit digest evidence 연결

아직 deployment hardening으로 남은 항목:

- production secret rotation 운영 절차
- TLS/reverse proxy/deployment boundary가 문서화 단계
- gateway/WAF와 API rate limit의 실제 배포 파라미터 확정
- audit digest의 외부 WORM 저장소 또는 서명 키 연동
- backup/restore, tenant data deletion, incident response drill 실행 evidence 없음

## Required Production Controls

| Control | Closure evidence |
| --- | --- |
| Secret management | no production default secret, env/secret-store injection, rotation runbook, negative tests |
| Authn/Authz | bearer/JWT verification, tenant/actor/request header checks, admin/operator/viewer negative tests |
| Tenant isolation | cross-tenant read denial tests for `/projects`, `/families`, `/submissions`, `/audit/events` |
| Audit | append-only event format, SHA-256 batch digest, retention/export policy, optional signed/WORM storage |
| Rate limit | per tenant/actor/request-window throttle and tests |
| Transport | TLS/reverse proxy deployment contract or on-prem gateway requirement |
| Storage lifecycle | project evidence retention, deletion, backup, restore, export |
| Incident response | support bundle, audit trace, rollback/disable token steps |

## Implementation Order

1. Keep local test token helpers isolated from production server config.
2. Require `--jwt-hmac-secret` or `PROJECT_OPS_JWT_HMAC_SECRET` whenever auth is enabled.
3. Maintain rate-limit middleware for GET endpoints.
4. Maintain audit batch digest writer and `/audit/digest` endpoint.
5. Maintain tenant isolation and role negative tests.
6. Add production deployment sample with secret/env contract.
7. Run backup/restore, tenant delete, and incident response drills with signed evidence.

## Current Gate Status

The independent product readiness gate now passes the reference API security/ops check including rate limit, request metadata limit, audit tamper-evidence digest, and policy manifest. Release promotion still stays blocked by strict EB/RH evidence, and deployment hardening work above remains required before exposing this service outside a controlled gateway.
