# Envelope campaign: reused policy identity and historical costs

The frozen envelope campaign reuses **two different policies**. Its validation
and holdout policy is the original all-training SVD fit at ridge `1e-6`; it is
not the later nested-selection refit at ridge `10000`. Filenames alone do not
establish which fit was used. The original policy payloads and fit receipts were
compared against their pinned packet inventories before assigning costs.

| Use | Actual policy hash | Original fit wall time |
| --- | --- | ---: |
| `train-b`, with that case withheld | `sha256:2a924b90d6347379185a1ef1f4cbe689e794213ec73f0510abaa5e2cdedc9778` | 0.078683420 s |
| validation / holdout, integrated ridge `1e-6` | `sha256:50c4aa07f672ef2183dfc7b280c6b667de24e99bbfc7ff3b92ff4474ba8f943c` | 0.106241841 s |

The unused later selected refit has policy hash
`sha256:e847a2f46c57c77e78d06269ab6352cc3aecdc0f616597f54fa51440c04e40a9`.
The nested-selection packet preserved its root `integrated-policy.json` unchanged
and wrote selected fits under `study/`. Its 11.340960791 s parent interval belongs
to historical selection research; it is not the fit interval for the integrated
policy being used here. The frozen numerical campaign is unchanged by this
provenance clarification.

## Cost scopes and overlap

The original shared training-generation record contains 12 complete paths:
reference, secant and fresh-reference for each of four training cases. It records
1,045.632468841 s of path time, 2,904 core calls and 13,815 Newton iterations /
linear solves. This includes generation verification paths. It is not the full
generation parent interval and must not be presented as the entire historical
research cost. Shared data generation is charged once across reused policies,
not once per policy or repetition.

The integrated SVD worker's five fits include one full-training fit and four
withheld fits. The full fit took 0.106241841 s, the worker through report generation
took 1.491425737 s, and the enclosing parent took 3.335099386 s. These clocks are
nested; adding them would double-count work. The withheld `train-b` fit is likewise
already contained in the earlier native-runtime experiment's parent interval.

The current envelope experiment performs zero new fits and generates zero new
training labels. That does not make training free. Report its online path costs,
both numerical parent intervals including the preserved orchestration failure,
post-run audit cost, and historical costs separately. The first completed slot
is carried into the continuation and must not be charged twice. A complete
research-lifecycle total remains **unknown**, including incompletely metered
historical preparation and failed audits; no net-savings claim follows from this
partial cost reconstruction.

## Evidence and verification scope

The [machine-readable receipt](rc-envelope-historical-costs-20260913.summary.json)
retains 17 input bindings, inventory checks and policy identities. Receipt SHA-256:
`c895cadfef31f157a1e5337131cd80bc64a06788a5f446d81f8458f7a06b5b66`.
The local read-only reproduction driver is
`/tmp/trace-rc-envelope-historical-costs.py`, SHA-256
`8143f1d5daeca440963feae50b005666ff429628bc025179e778bacbd205d9e0`.
It performed no Newton solves, fits or original packet edits. Only the listed
files were checked against pinned inventories; this is not a new full audit of
all historical records or independent physical validation.

The prepared post-terminal campaign verifier copies this receipt, rechecks its
input hashes, and distinguishes envelope permission from actual policy
consultation after the static model gate. Preparation and syntax compilation do
not count as an executed numerical audit. The ongoing campaign must reach a
terminal state before that heavier verification starts.

See the [preserved failure and continuation](rc-envelope-continuation-20260913.md)
for the frozen numerical source and original nine-slot protocol. Independent
project provenance, physical validation and learned net benefit remain unproved.
