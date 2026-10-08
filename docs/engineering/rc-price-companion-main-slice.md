# Immutable price companions for completed bounded RC jobs

This slice follows the control, API and durable-worker slices. It does not
modify any numerical source or recompute structural results when prices change.
Reports refer to authenticated completed-job originals and remain separate from
the job's request, result, checkpoint, events and execution budget.

## Narrow extraction

The original report/custody implementation comes from
`7b6e077f7b99eb9d91d4636dd9196029097ff050`. The generic design-search module is
not imported. Its geometry, declared-price validation and estimate functions
are extracted into `execution/rc_fiber_quantities.py`, preserving the formulas
for gross concrete volume and straight authored longitudinal reinforcement.
Only models accepted by the existing main compiler can be measured. Later
pin-roller, two-fixed-endpoint and preload flags are not exposed.

The service follows main's existing bounded content-addressed blob behavior;
it does not import the donor's later global payload-quota subsystem. Each
companion is bounded to 4 MiB. This is not an account-wide storage quota or a
production storage-capacity claim. Blob-write and report-index failures are
tested without publishing a report index entry.

## Pricing and custody

- Prices are finite nonnegative caller declarations with explicit currency,
  date and source. No market lookup, verified quote or purchasing commitment
  is inferred
- Exact normalized source/price combinations reuse the same immutable report
  revision, including signed-zero normalization
- Price changes append a new revision; original numerical artifacts, job
  revisions, event history and invocation ledger remain unchanged
- Reads rederive quantities and report bindings from the completed originals;
  coherent rehashing of altered quantities cannot grant authority
- Tenant B and invalid credentials cannot access tenant A's report; changed
  expected source hashes are rejected
- HTTP download preserves attachment semantics and reports the content hash

Gross concrete is not reduced by rebar displacement. Straight longitudinal
bars exclude transverse reinforcement, laps/hooks/anchorage, waste, formwork,
labor, fabrication, transport and tax. These reports are neither detailing
takeoffs nor engineering design approvals.

## Evidence and remaining gate

The complete process test begins with an absent store and a newly authored
two-target cantilever request. It performs real analysis/replay, records a
checkpoint, kills the first worker, restores from a fresh worker after lease
expiry, then creates price revisions one and two. During report creation,
numerical entrypoints are patched to raise; numerical database rows remain
unchanged. The resulting HTTP attachment bytes match the revision hash.

```sh
python -m pytest -q tests/test_rc_fiber_quantity_report.py tests/test_rc_fiber_quantity_report_service.py tests/test_rc_real_process_lifecycle.py
```

Separate synthetic report-seam tests are labelled as such and do not replace
the genuine process test. Hosted workflow selection is not modified here.
The actual browser/Workbench gate remains separate: neither HTTP success nor
a test download link proves a fresh Workbench session can reopen the job. No
independent physical validation, release approval or design authority follows.
