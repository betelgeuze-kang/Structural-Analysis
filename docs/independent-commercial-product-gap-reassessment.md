# Independent Commercial Product Gap Reassessment

- 기준일: 2026-06-19
- 목적: 조건부 상용 보조툴 상태에서 독립 상용 구조해석제품 claim으로 넘어가기 위해 남은 gap을 재산정한다.
- 판정 기준: `scripts/check_independent_product_readiness.py --json`

## 결론

현재 독립 상용제품 readiness는 **80/100, blocked**다.

상용 보조툴 관점에서는 strict evidence-aware L4, `8.0/10`으로 운영 가능한 상태에 가깝다. 그러나 독립 상용 구조해석제품 claim은 아직 사용할 수 없다. 이유는 runtime, ops, packaging이 아니라 **strict external benchmark receipt evidence**가 비어 있기 때문이다. RH closure는 signed evidence `3/3`으로 닫혔지만, EB receipt `0/4`가 strict package 전체를 blocked로 유지한다.

별도 로컬 트랙으로 **Workstation Delivery Service Readiness**를 추가했다. 이 트랙은 내 워크스테이션에서 구조해석/최적화 산출물, 리포트, 뷰어, 도면, 데이터, evidence, manifest/checksum zip을 생성해 납품하는 서비스 gate이며, EB/RH를 닫지 않아도 로컬에서 green이 될 수 있다. 다만 이 green은 독립 상용 구조해석제품 claim을 의미하지 않는다.

현재 허용 claim:

- Commercial engineer-in-loop acceleration
- 구조 엔지니어 검토 전제 구조해석/최적화 보조 플랫폼
- 구조 엔지니어 검토 전제의 워크스테이션 기반 구조해석/최적화 산출물 제작 서비스
- P0/P1 evidence 기반 반복 업무 가속

현재 금지 claim:

- 독립 상용 구조해석제품 release complete
- 구조기술사 검토 대체
- 인허가 자동 승인
- full autonomous commercial replacement

## Gate Snapshot

| Gate | Weight | Status | Evidence |
| --- | ---: | --- | --- |
| P0 release/core evidence | 15 | ready | `p0_closed=true`, release publication closed, core evidence closed |
| P1 validation/benchmark breadth | 15 | ready | P1 inputs/execution ready, benchmark breadth unblocked |
| Strict EB/RH evidence | 20 | blocked | EB receipt `0/4`, RH signed closure `3/3` |
| Runtime production path | 15 | ready | strict Rust/HIP probe pass, runtime packaging manifest pass |
| Production API/security/ops | 15 | ready | bearer/tenant/audit contract present, production default secret removed, rate/request limits, audit digest, ops policy manifest, dry-run deployment drill |
| Deployment packaging/support | 10 | ready | support bundle redaction/digest/roundtrip pass, on-prem/air-gapped skeleton packaging pass, static viewer performance budget pass |
| Claim governance | 5 | ready | recommended claim remains engineer-in-loop bounded |
| Source boundary/artifact footprint | 5 | ready | cleanup candidate count `0` |
| Total | 100 | blocked | **80/100** |

## Separate Workstation Delivery Service Gate

| Gate | Status | Evidence |
| --- | --- | --- |
| Hardware profile | local gate | `implementation/phase1/workstation_hardware_profile.json` |
| Service budget | local gate | `implementation/phase1/workstation_service_budget.json` |
| Delivery package | local gate | `implementation/phase1/workstation_delivery_package_manifest.json` and `project_package.zip` |
| Client input validation | local gate | `implementation/phase1/client_input_validation_report.json` |
| Delivery readiness | local gate | `implementation/phase1/workstation_delivery_readiness.json` |

Command sequence:

```bash
python3 scripts/build_workstation_hardware_profile.py --json
python3 scripts/build_workstation_service_budget.py --json
python3 scripts/validate_client_input_package.py --input implementation/phase1/open_data/midas/midas_model.json --json
python3 scripts/build_workstation_delivery_package.py --json
python3 scripts/check_workstation_delivery_readiness.py --json
```

This track is documented in `docs/workstation-service-productization-roadmap.md` and `docs/workstation-delivery-package.md`.

## Remaining Commercialization Gaps

### Gap 1. External Benchmark Receipts

Impact: **independent product claim blocker**

Current evidence:

- `hardest_external_10case`: receipt pending
- `tpu_hffb`: receipt pending
- `peer_spd_hinge`: receipt pending
- `korean_public_structures`: receipt pending

Missing requirements:

- `receipt_status=attached`
- receipt URL or local evidence path
- `closure_evidence_status=attached`
- submitted/last-checked timestamps

Closure path:

```bash
python3 scripts/generate_p1_evidence_intake_template.py --p1-operational-queues <p1-operational-queues.json> --out <p1-evidence-intake.json>
python3 scripts/validate_p1_evidence_intake_manifest.py --intake-manifest <p1-evidence-intake.json> --json --fail-open
python3 scripts/build_p1_evidence_sidecar_updates.py --intake-manifest <p1-evidence-intake.json> --require-complete --json --fail-open
python3 scripts/preflight_p1_evidence_sidecar_intake.py --json --fail-open
```

### Gap 2. Residual Holdout Closure

Impact: **closed locally, still audited with strict package**

Current evidence:

- `RH-001`: signed engineer review packet attached
- `RH-002`: legacy tool cross-validation packet attached
- `RH-003`: authority signoff receipt or formal hold packet attached

Maintained requirements:

- `status=closed`
- `closure_evidence_status=signed_attached`
- local evidence path exists or explicit evidence URL
- closed/last-checked timestamps

RH closure no longer contributes a current blocker by itself. Keep it in the strict preflight so EB/RH package regressions are visible before any independent product claim.

### Gap 3. External-State Release Promotion

Impact: **release process blocker, not local readiness blocker**

Local gates can now say whether the product is ready, but actual release promotion remains an external-state action. It requires explicit confirmation before any public release, push, deployment, publication, or credential-backed action.

Closure criteria:

- `check_independent_product_readiness.py --fail-blocked` passes
- release publication evidence remains closed
- external-state target/action/rollback/verification is confirmed before execution

## No Longer Primary Gaps

The following items were previous independent-product blockers, but are now ready in the local gate:

- Runtime packaging: `production_runtime_packaging_manifest.json` has `contract_pass=true`
- Runtime SBOM: `runtime_sbom.json` generated
- Native runtime artifact manifest: `native_runtime_artifact_manifest.json` has `contract_pass=true`
- Runtime compatibility matrix: `runtime_version_compatibility_matrix.json` has `contract_pass=true`
- On-prem/air-gapped packaging skeleton: `onprem_deployment_packaging_manifest.json` has `contract_pass=true`
- Support bundle: `support_bundle_manifest.json` has `contract_pass=true`
- Production ops hardening: auth-enabled production path has no default secret, tenant/actor rate limit is present, request metadata limit is present, audit digest is generated, `/ops/policy` exposes retention/export/backup/delete policy, and dry-run deployment drill evidence is attached
- Viewer workflow packaging: evidence ingest, solver receipt, commercial-tool crosswalk, lineage drilldown, and SVG sheet/revision/callout deep-link package are covered by source viewer contracts
- Viewer static performance budget: `structure_viewer_performance_budget_manifest.json` has `contract_pass=true` for wall/slab instancing, surface LOD, BVH picking, and pick-candidate cap; live FPS/latency evidence remains future work and is not used as an independent-product claim
- Viewer local browser performance probe: `structure_viewer_browser_performance_probe.json` records local canvas ready/FPS smoke with `live_performance_claim=false`; customer-hardware FPS/latency remains future evidence
- Viewer visual regression baseline: `structure_viewer_visual_regression_baseline.json` records 11 desktop/mobile render-mode and workflow signatures, including plan view, review member selection, compare overlay, CSV evidence ingest, renderable JSON ingest, section edit apply, and load-combination draft markers with `live_visual_claim=false`; customer-device visual evidence remains future work
- Source boundary: readiness gate reports candidate files `0`

## Promotion Decision

Do not promote to independent commercial structural analysis product yet.

Next valid milestone is **strict EB receipt evidence closed 4/4**. Once that happens, rerun:

```bash
python3 scripts/check_independent_product_readiness.py --fail-blocked
python3 scripts/report_commercialization_level.py --closure-mode strict --json
```

Until both pass, public wording should remain bounded to engineer-in-loop commercial acceleration.
