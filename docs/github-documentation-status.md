# GitHub Documentation Status

- 기준일: 2026-05-20
- 목적: GitHub에서 바로 보이는 README/docs 문서가 현재 productization gate 상태와 같은 claim boundary를 말하는지 고정한다.

## Current Published Claim

현재 GitHub 문서에서 허용되는 claim은 **engineer-in-loop commercial assist**다.

별도 허용 claim으로 **workstation delivery service**가 추가됐다: 내 워크스테이션에서 HTML/PDF/SVG/JSON/CSV 납품 패키지를 생성하고 구조 엔지니어 검토 전제로 전달하는 서비스다. 이 claim은 독립 SaaS/독립 구조해석제품 claim이 아니다.

금지 claim:

- full autonomous commercial replacement
- 구조기술사 검토 대체
- 인허가 자동 승인
- strict external benchmark / residual holdout evidence closed

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
| Strict EB/RH evidence | blocked: EB `0/4`, RH `0/3` |
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
python3 scripts/check_independent_product_readiness.py --json
python3 scripts/verify_structure_viewer_contracts.py --dry-run
python3 scripts/verify_quality_gate.py --mode full --dry-run
git diff --check
```

If strict EB/RH evidence changes, update README, gap reassessment, commercialization priority assessment, and this status file in the same documentation commit.
