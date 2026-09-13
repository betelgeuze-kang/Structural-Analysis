# Accepted-history material activity reporting

The planar backend v2 experiment report now records material activity from
hash-bound, contract-verified accepted histories. This distinguishes running a
nonlinear solver without observed material activation from paths with observed
steel plastic strain or concrete damage. It is not a geometric nonlinearity
classification or independent physical validation.

Each row includes maxima across all accepted steps, observed step/material row
counts, and nullable activity flags. Failed or unverified paths, changed history
bytes, unsupported material schemas, and malformed activity values remain
unavailable; partially collected maxima are discarded. An absent material kind
remains unknown rather than undamaged. Positive means strictly greater than zero
in the recorded model state, not an engineering significance threshold.

The scan is included in parent CPU and experiment wall time, but excluded from
worker and per-slot validation costs. V1 reports are unchanged. No selection
threshold, convergence tolerance, or external verification gate is relaxed.

## Read-only replay

The accompanying `planar-material-activity-20260914.summary.json` records replay
against existing immutable packets and their original source revisions:

- Larger 27/48-free-equation cohort: 8 verified paths, no observed steel plasticity
  or concrete damage.
- Earlier high-load topology cohort: 9 verified paths with concrete damage and
  no observed steel plasticity; the 9 failed paths remain unknown.

History bytes were checked against each retained row's SHA-256 and length before
parsing. This replay executes no new solves and does not requalify the old source
or convert failed paths into zero-damage observations.

## Verification

Focused synthetic tests cover zero, nonterminal activity, failed verification
gates, changed bytes, invalid values, absent material kinds and unknown schemas.
The real-worker history test checks report integration and cost scope against
new worker outputs. Synthetic fixtures are software integrity evidence only.
The focused activity suite is also registered in the development-contract CI
lane; hosted execution of this change is still pending.

AI net benefit, external physical validation, main integration and signed owner
acceptance remain open roadmap requirements.

## Late comparison invalidation

A regression reuses real worker outputs, then changes a checkpoint after the
parent retention check but immediately before paired comparison. The existing
comparison correctly rejects the artifacts and invalidates both rows, but the
previous ordering had already generated an available material summary. The
regression failed with `available=True` on the invalidated row.

Material activity is now computed after paired comparison, using its final
validation flags. The same case must retain unknown material flags rather than
zero or positive evidence. Numerical mismatches alone remain distinct from
artifact corruption. The test launches only its two fixture workers and reuses
their saved bytes for the fault injection; it does not simulate physical damage
or claim additional physical validation.

After the ordering fix, the backend/history/material-activity selection passes
177 tests in 42.36 seconds, including the reproduced regression. Ruff and diff
checks pass. This local change is not yet verified by hosted CI.
