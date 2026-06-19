# GitHub Documentation Status

- 기준일: 2026-06-19
- 목적: GitHub에서 바로 보이는 README/docs 문서가 현재 productization gate 상태와 같은 claim boundary를 말하는지 고정한다.

## Current Published Claim

현재 GitHub 문서에서 허용되는 claim은 **engineer-in-loop commercial assist**다.

별도 허용 claim으로 **workstation delivery service**가 추가됐다: 내 워크스테이션에서 HTML/PDF/SVG/JSON/CSV 납품 패키지를 생성하고 구조 엔지니어 검토 전제로 전달하는 서비스다. 이 claim은 독립 SaaS/독립 구조해석제품 claim이 아니다.

Commercial v1 supported scope (machine-checked by `scripts/build_paid_pilot_scope_guard_report.py`):

- Structure families: frame, wall-frame, outrigger, truss
- Interop: MIDAS interop, OpenSees interop, KDS interop
- Analysis: nonlinear static, bounded NDTHA
- Audit: residual audit, reference comparison
- Reviewer package

Commercial v1 separate-validation exclusions (must stay visible):

- rail/tunnel
- special SSI
- nonstandard contact
- legal/authority approval automation
- special construction stages

금지 claim:

- full autonomous commercial replacement
- 구조기술사 검토 대체
- 인허가 자동 승인
- full strict external benchmark / residual holdout evidence package closed

## Current Gate Snapshot

| Area | Current status |
| --- | --- |
| P0 release/core | ready |
| P1 validation/breadth | ready |
| Runtime packaging | ready |
| Production ops/security | ready: no production default secret, rate/request limits, audit digest, `/ops/policy`, dry-run deployment drill |
| On-prem/air-gapped packaging | ready: skeleton contract, no live deployment claim |
| Support bundle | ready |
| Viewer workflow packaging | ready: evidence ingest, solver receipt, commercial-tool crosswalk, lineage drilldown, SVG sheet/revision/callout deep-link package, static performance budget manifest, local browser performance probe, 11-case render-mode/core/advanced workflow-state visual regression baseline |
| Workstation delivery service | local gate: hardware profile, service budget, delivery package manifest, client input validation, package restore/checksum smoke |
| PM release-area gate | blocked: `12/15` green; CI streak, human UX observation, license status remain open |
| Release evidence freshness | pass: `10/10` artifacts include generated_at/source commit/engine version/input checksum/reuse marker and producer mtime recency; customer shadow intake/status/full-validation/residual/G1 freshness does not close the `0/3` shadow-case, `0/8` fresh-receipt, G1 full-mesh nonlinear-equilibrium, or GA breadth blockers |
| Fresh full-validation lanes | blocked: lane contracts `8/8`, fresh receipts `0/8`; hydrated CPU-required release evidence does not replace Level 3 fresh validation receipts |
| Real-project corpus measured status | pass for initial metadata/value gate: KR measured rows `10/10`, formats `2/2`, PEER metric-bearing values `5/5`; official PEER reference-truth groups `1`, measured-run bridge groups `3` |
| Customer shadow evidence | schema/validator/intake packet ready; five owner-input slots fixed; status gate blocked at `0/3` completed-project shadow cases until real customer-retained evidence files are attached |
| Residual Level 3 status | ready for attached NDTHA residual slice: hard `3/3`, recommended rate `1.0`, fallback `0.0`, solver_raw `1.0`, corrected-state recompute `3/3`; does not close independent V&V or GA breadth |
| Evidence Console scope | scope fixed: features `7/7`, deferred full-GUI surfaces `5/5`; launch blocked because customer shadow evidence remains `0/3` |
| Strict EB/RH evidence | blocked: EB `0/4`, RH signed closure `3/3` |
| Independent product readiness | blocked, `80/100` |

## Documentation Source Of Truth

- README: top-level GitHub status, command list, and allowed claim boundary
- `docs/independent-commercial-product-gap-reassessment.md`: readiness gate snapshot and remaining blocker summary
- `docs/workstation-service-productization-roadmap.md`: local workstation delivery-service roadmap and claim boundary
- `docs/workstation-delivery-package.md`: package layout, checksum, restore, and delivery manifest contract
- `docs/production-ops-security.md`: production ops hardening boundary
- `docs/runtime-production-packaging.md`: runtime packaging/support bundle boundary
- `docs/structure-viewer-product-workspace.md`: viewer workflow/report package boundary
- `docs/commercialization-improvement-priority-assessment.md`: prioritized productization backlog

## Verification

Keep these checks aligned with documentation updates:

```bash
python3 scripts/build_project_ops_deployment_drill_manifest.py --json
python3 scripts/build_structure_viewer_performance_budget_manifest.py --json
python3 scripts/build_workstation_hardware_profile.py --json
python3 scripts/build_workstation_service_budget.py --json
python3 scripts/validate_client_input_package.py --input implementation/phase1/open_data/midas/midas_model.json --json
python3 scripts/build_workstation_delivery_package.py --json
python3 scripts/build_workstation_job_retention_policy.py --json
python3 scripts/check_workstation_delivery_readiness.py --json
npm run verify:viewer-performance-probe
npm run verify:viewer-visual-regression
python3 scripts/build_support_bundle.py --json
python3 scripts/build_onprem_deployment_packaging_manifest.py --json
python3 scripts/report_release_evidence_freshness.py
python3 implementation/phase1/check_real_project_corpus_measured_status.py
python3 scripts/check_independent_product_readiness.py --json
python3 scripts/verify_structure_viewer_contracts.py --dry-run
python3 scripts/verify_quality_gate.py --mode full --dry-run
git diff --check
```

If strict EB/RH evidence changes, update README, gap reassessment, commercialization priority assessment, and this status file in the same documentation commit.
