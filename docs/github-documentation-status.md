# GitHub Documentation Status

- 기준일: 2026-05-19
- 목적: GitHub에서 바로 보이는 README/docs 문서가 현재 productization gate 상태와 같은 claim boundary를 말하는지 고정한다.

## Current Published Claim

현재 GitHub 문서에서 허용되는 claim은 **engineer-in-loop commercial assist**다.

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
| Production ops/security | ready: no production default secret, rate/request limits, audit digest, `/ops/policy` |
| Support bundle | ready |
| Viewer workflow packaging | ready: evidence ingest, solver receipt, commercial-tool crosswalk, lineage drilldown, SVG sheet/revision/callout deep-link package |
| Strict EB/RH evidence | blocked: EB `0/4`, RH `0/3` |
| Independent product readiness | blocked, `80/100` |

## Documentation Source Of Truth

- README: top-level GitHub status, command list, and allowed claim boundary
- `docs/independent-commercial-product-gap-reassessment.md`: readiness gate snapshot and remaining blocker summary
- `docs/production-ops-security.md`: production ops hardening boundary
- `docs/runtime-production-packaging.md`: runtime packaging/support bundle boundary
- `docs/structure-viewer-product-workspace.md`: viewer workflow/report package boundary
- `docs/commercialization-improvement-priority-assessment.md`: prioritized productization backlog

## Verification

Keep these checks aligned with documentation updates:

```bash
python3 scripts/check_independent_product_readiness.py --json
python3 scripts/verify_structure_viewer_contracts.py --dry-run
python3 scripts/verify_quality_gate.py --mode full --dry-run
git diff --check
```

If strict EB/RH evidence changes, update README, gap reassessment, commercialization priority assessment, and this status file in the same documentation commit.
