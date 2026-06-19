# Release Limitation Manual

This manual records the claim boundary, known issue register, and rollback
expectations for the PM release gate.

## Claim Boundary

- Paid pilot scope: reviewer assist only, restricted to the declared structure
  families, workflows, and evidence package.
- Limited commercial scope: allowed only after strict runtime, residual,
  benchmark breadth, security, support, and CI evidence remain green.
- GA/Enterprise scope: not approved until independent V&V, family validation
  manual signoff, customer audit/failure bundle acceptance, support SLA, and
  release-area blockers are closed.

## Commercial v1 Supported Scope

The commercial v1 product surface is intentionally bounded. The paid-pilot
scope guard (`scripts/build_paid_pilot_scope_guard_report.py`) blocks when any
of the following are missing from the scope source:

- Structure families: frame structures, wall-frame structures, outrigger
  systems, truss systems.
- Interop: MIDAS interop, OpenSees interop, KDS interop.
- Analysis: nonlinear static, bounded NDTHA.
- Audit: residual audit, reference comparison.
- Reviewer package: reviewer package (reviewer handoff package).

## Commercial v1 Separate-Validation Exclusions

The following are explicitly excluded from commercial v1 and require separate
validation. The paid-pilot scope guard blocks when any of the following are
missing from the scope source as explicit separate-validation exclusions:

- rail/tunnel (rail-tunnel / 철도/터널)
- special SSI (special soil-structure interaction / 특수 SSI)
- nonstandard contact (비표준 접촉)
- legal/authority approval automation (인허가 자동화)
- special construction stages (특수 시공 단계)

## Known Issues

- CI streak evidence: PR and nightly release credit requires tracked GitHub
  Actions consecutive-pass evidence for the configured 30-run window.
- License status: security remains blocked until approved product/legal license
  status evidence is populated and current.
- GA signoff: independent V&V, family validation manual signoff, and customer
  audit/failure bundle/SLA evidence remain external owner inputs.
- Commercial v1 supported scope and separate-validation exclusions are
  contract-only; missing items are blocker, not silent omission.

## Support Bundle And Failure Bundle

The support bundle must include the PM blocker register, CI streak intake packet,
license status intake packet, frontend dependency audit report, GA/Enterprise
readiness and signoff intake packets, paid pilot scope guard, this limitation
manual, and the release validation manual.

## Rollback

Rollback uses the runtime packaging rollback runbook and release registry
provenance. Any customer-facing release must preserve the support bundle,
failure bundle, action/source trace, and reproduction command set for the
affected release.
