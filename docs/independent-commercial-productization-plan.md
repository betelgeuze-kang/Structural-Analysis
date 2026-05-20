# Independent Commercial Productization Plan

- 기준일: 2026-05-19
- 목적: 현재 engineer-in-loop 상용 보조툴 상태를 독립 상용 구조해석제품 claim으로 승격하기 위한 닫힘 기준을 고정한다.

## Current Boundary

현재 제품 claim은 `engineer-in-loop commercial assist only`다. P0/P1, runtime packaging, production ops/security hardening, project ops dry-run deployment drill, on-prem/air-gapped packaging skeleton, support bundle, source-boundary, viewer evidence/report workflow, static viewer performance budget, local browser performance probe, 11-case render-mode/core/advanced workflow visual regression baseline은 ready지만, 독립 상용제품 claim은 strict EB/RH evidence 미완료 때문에 아직 blocked로 본다.

금지 claim:

- 구조기술사 검토 대체
- 인허가 자동 승인
- 외부 benchmark 검증 완료
- 완전 자율 상용 구조설계툴

허용 claim:

- 구조 엔지니어 검토를 전제로 한 상용 구조해석/최적화 보조 플랫폼
- P0/P1 release evidence 기반 engineer-in-loop review workflow
- strict EB/RH evidence가 닫히기 전까지 claim-limited commercial assist

## Product Gate

독립 상용제품 승격 상태는 아래 명령으로 본다.

```bash
python3 scripts/check_independent_product_readiness.py --json
python3 scripts/check_independent_product_readiness.py --out implementation/phase1/release/independent_product_readiness.json --out-md implementation/phase1/release/independent_product_readiness.md
```

릴리스 후보에서 차단 조건으로 쓰려면:

```bash
python3 scripts/check_independent_product_readiness.py --fail-blocked
```

현재 이 명령은 fail-fast promotion gate가 아니라 blocked work queue를 드러내는 상위 집계 게이트다. production runtime, ops/security, packaging/support gate는 로컬 증거 기준 ready이며, 실제 release promotion에 묶는 시점은 EB/RH strict evidence가 닫힌 뒤로 둔다.

## Closure Criteria

| Gate | Independent product 기준 |
| --- | --- |
| P0 release/core | P0 release publication과 P0-2..P0-6 core evidence가 closed |
| P1 validation/breadth | P1 inputs, execution, benchmark breadth가 ready |
| Strict EB/RH evidence | EB receipt 4/4, EB closure evidence 4/4, RH closure 3/3 |
| Runtime production path | real producer -> runtime -> verifier 경로가 strict Rust/HIP 또는 승인된 production backend로 pass |
| API/security/ops | production auth secret injection, tenant isolation, audit, rate limit, request limit, audit digest, policy manifest, dry-run deployment drill, retention/backup/runbook |
| Packaging/support | runtime package manifest, version compatibility, on-prem/air-gapped skeleton manifest, support bundle manifest, SBOM/license evidence |
| Viewer/workflow | evidence ingest, solver receipt, commercial-tool crosswalk, lineage drilldown, SVG sheet/revision/callout deep-link package, static wall/slab/LOD/hit-test performance budget manifest, local browser performance probe without customer-hardware FPS claim, 11-case render-mode/core/advanced workflow visual regression baseline without pixel-perfect customer-device claim |
| Claim governance | README/docs/report/committee package가 같은 recommended claim과 blocker vocabulary 사용 |
| Source boundary | source repo에 unknown large/generated/private artifact가 없음 |

## Evidence To Attach

### EB external benchmark receipts

- `hardest_external_10case`
- `tpu_hffb`
- `peer_spd_hinge`
- `korean_public_structures`

각 row는 receipt URL 또는 evidence path, submitted timestamp, last checked timestamp, attached closure evidence status를 가져야 한다.

### RH residual holdout closure

- `RH-001`: signed engineer review packet
- `RH-002`: legacy tool cross-validation packet
- `RH-003`: authority signoff receipt or formal hold packet

각 row는 `status=closed`, `closure_evidence_status=attached`, 존재하는 local path 또는 explicit URL을 가져야 한다.

## Implementation Order

1. `scripts/generate_p1_evidence_intake_template.py`로 EB/RH intake를 생성한다.
2. 실제 receipt/review/signoff evidence를 intake에 채운다.
3. `scripts/validate_p1_evidence_intake_manifest.py --json --fail-open`으로 no-write promotion lint를 통과시킨다.
4. `scripts/build_p1_evidence_sidecar_updates.py --require-complete`로 sidecar를 생성한다.
5. `scripts/preflight_p1_evidence_sidecar_intake.py --json --fail-open` strict mode를 통과시킨다.
6. `zero_copy_real_probe_report_strict.json` 또는 승인된 production backend strict report를 유지한다.
7. `scripts/build_runtime_packaging_manifest.py --json`으로 runtime packaging/SBOM/native artifact/compatibility evidence를 갱신한다.
8. `scripts/build_project_ops_deployment_drill_manifest.py --json`으로 project ops deployment dry-run evidence를 갱신한다.
9. `scripts/build_structure_viewer_performance_budget_manifest.py --json`으로 viewer static performance budget evidence를 갱신한다.
10. `npm run verify:viewer-performance-probe`로 local browser performance smoke를 갱신한다.
11. `npm run verify:viewer-visual-regression`으로 11-case render-mode/core/advanced workflow visual baseline을 검증한다.
12. `scripts/build_support_bundle.py --json`으로 support bundle redaction/digest/roundtrip evidence를 갱신한다.
13. `scripts/build_onprem_deployment_packaging_manifest.py --json`으로 on-prem/air-gapped skeleton packaging evidence를 갱신한다.
14. `scripts/verify_structure_viewer_contracts.py`로 viewer evidence/report workflow contract를 유지한다.
15. `scripts/check_independent_product_readiness.py --fail-blocked`를 release promotion 전 gate로 승격한다.

## Claim Promotion Ladder

| State | Allowed wording |
| --- | --- |
| Current | engineer-in-loop commercial assist only; independent readiness 80/100 blocked by EB/RH evidence |
| Runtime/ops/packaging/viewer workflow closed | production-packaged engineer-in-loop commercial assist platform with on-prem/air-gapped skeleton |
| Strict EB/RH closed | independent commercial structural analysis product with engineer sign-off boundary |
| Full autonomous replacement | 금지. 별도 법적/전문가 책임 검토와 authority acceptance evidence 없이는 사용하지 않는다. |
