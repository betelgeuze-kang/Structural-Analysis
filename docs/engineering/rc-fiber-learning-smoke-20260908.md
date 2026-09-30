# Local RC fiber learning integration observation

This is one local synthetic serial-cantilever family, not independent-project,
geometry-family, load-history, blind, or external validation. Artificial split
declarations exercise the data/learning/runtime integration only. No production
policy or construction saving is approved by this observation.

## Source and protocol

- Evaluated source: `48c9a897e315b69fef796903fd18ef66aaa889aa`, exported from the
  committed tree before execution; concurrent development used a separate tree.
- Model: `examples/public_rc_fiber_frame_cantilever.json`, changing section width
  only. Train widths: 0.400 and 0.390 m; validation width: 0.401 m; holdout width:
  0.402 m. All remain the same synthetic structural family and load history.
- Four load steps, three measured repetitions per arm per evaluation case and
  one unmeasured warmup repetition. Reference Newton, deterministic secant and
  opt-in learned displacement proposals share each case's model/configuration.
- Ridge `1e-6`, OOD margin `0.1`, declared before collection; 8 train samples,
  4 validation samples and 4 holdout samples. Training excludes evaluation targets.
- Policy: `sha256:5f12a3a1efdd26285fd4853e6ea6359b299b2321d626ca1c7abcecbf3a12e892`.
- Study report: `sha256:56d036690a78875b6a16189525f91401a5a90c8ce454a5ff3d582e8f07e176b8`.
  This is the report's logical hash, not a signature or external receipt.

The local raw report and protocol are retained at
`/tmp/structural-learning-source.FmdTmf/local-study/study.json` and its adjacent
`protocol.json`; the driver is
`/tmp/structural-design-source.cB2t6U/run_learning_study.py`.
These local files are not a published or independently retained evidence bundle.

## Observed result

All 18 measured runs passed full configured history comparison and J1-J5 recovery;
all 6 reference episode checks passed. All 24 measured AI step proposals were
accepted in-range; this observation does **not** exercise actual OOD recovery.
OOD and rollback contracts have focused tests, not independent operating evidence.

Verified end-to-end median seconds, including comparison/recovery verification:

| Local evaluation case | Reference Newton | Deterministic secant | Learned displacement |
| --- | ---: | ---: | ---: |
| validation-width | 16.074983 | 15.709762 | 16.100689 |
| holdout-width | 16.172362 | 15.527044 | 16.120239 |

The learned arm is slower than the deterministic arm in both cases. A small
positive learned/reference median difference in one case is not a general speedup
or a reason to promote the policy. The reference/learned iteration count is 8 per
run, versus 5 for secant. Selected solver time is roughly 0.04-0.055 seconds;
verification dominates the reported total. Timing is a volatile single-host
observation, not a stable numerical result identity.

Full data generation cost: 64.648713 seconds. Entire training call: 0.001146
seconds (learner-internal fit: 0.001137 seconds). Offline evaluation: 293.044402
seconds. Total study: 357.700556 seconds. These are separate scopes, not additive
speedup claims. No positive learned/secant saving exists, so amortization against
secant is unavailable. The single positive learned/reference median difference
projects 1,241 identical-case reuses to amortize generation plus training; this
excludes offline evaluation and was not an observed break-even execution.

## Decision

Keep learned warm starts opt-in and non-authoritative. Continue candidate-pool
selection experiments. Do not retune on these holdout
outcomes or describe artificial split isolation as independent generalization.
Independent corpus/provenance, operational validation and price/takeoff evidence
remain outside this observation.

## Frozen-policy OOD follow-up

A separate actual 4 m member case changed the physical-coordinate scaling profile
from that used in training. The saved policy was reloaded without retraining and
its artifact hash was unchanged before and after execution. At all four load steps
the policy reported OOD and the runner selected reference Newton without a seeded
attempt. Full history, material state and checkpoint bytes matched the reference
exactly. All three strategy runs and the reference episode check passed.

This was a one-repetition functional OOD probe, run concurrently with unrelated
focused verification; its elapsed values are not a comparative speed result. It
exercises pre-solve OOD rejection, not rollback after a failed seeded solve.
The report is `/tmp/structural-learning-source.FmdTmf/ood-smoke.json`, with logical
hash `sha256:5fa4b60bab3d09d502db4ad2553b0adfc083a1c8799c61c85efccc811310715c`.
The source revision and frozen policy are the same as the in-range study.
