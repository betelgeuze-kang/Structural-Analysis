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

## Known Issues

- CI streak evidence: PR and nightly release credit requires tracked GitHub
  Actions consecutive-pass evidence for the configured 30-run window.
- License status: security remains blocked until approved product/legal license
  status evidence is populated and current.
- GA signoff: independent V&V, family validation manual signoff, and customer
  audit/failure bundle/SLA evidence remain external owner inputs.

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
