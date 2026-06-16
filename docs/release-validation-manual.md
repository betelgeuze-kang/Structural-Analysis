# Release Validation Manual

This manual defines the validation evidence required for the PM release gate.
It is an evidence index, not an independent V&V attestation and not a
substitute for licensed engineering review.

## Scope

- Product scope: reviewer-assisted structural analysis for the declared
  families and workflows in the PM release evidence package.
- Validation family coverage: RC, steel, composite, contact/material coupling,
  SSI/foundation links, benchmark breadth families, and interop roundtrips.
- Release tiers: paid pilot, limited commercial, and GA/Enterprise are evaluated
  separately. GA/Enterprise still requires independent V&V and owner signoff.

## Evidence Thresholds

- Core engine p95 error: each active family must stay within the PM p95 error
  threshold, with GA targeting the tighter p95 range documented by the release
  gate report.
- Residual: hard and recommended residual checks must pass in strict mode, with
  solver_raw source ratio, normalized residual, fallback rate, and corrected
  state recompute evidence attached.
- Benchmark breadth: measured/open-data validation cases must satisfy the
  paid-pilot, limited-commercial, and GA thresholds separately.
- Runtime and device: require_ndtha and require_hip evidence must pass for GPU
  product scope, with device residency and host-copy share reported.
- Interop: MIDAS, KDS, and OpenSees trace evidence must be reproducible from the
  release evidence package.

## Reproduction Commands

- `python3 scripts/report_pm_release_gate.py --out implementation/phase1/release_evidence/productization/pm_release_gate_report.json --out-md implementation/phase1/release_evidence/productization/pm_release_gate_report.md`
- `python3 scripts/build_support_bundle.py`
- `python3 scripts/verify_quality_gate.py --mode pr`

## Acceptance Boundary

A pass in this manual means the local release evidence is complete for the
declared product scope. It does not create independent V&V, customer acceptance,
license approval, or GA/Enterprise support commitments.
