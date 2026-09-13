# Training-only work gate coupled to learned vector correction

Numerical source `36a13b45d87183b4bba2fe89de763675d31f4e3d`.
The [work classifier](rc-work-gate-training-20260914.md) could identify some
multi-iteration steps but did not establish that correcting them saves work.
This experiment connects it to an actual learned displacement/load-factor seed
and measures the missing numerical outcome.

## Frozen fitting and execution

Retain the prior four gate models and their threshold 0.5. Use the same 17
pre-solve features and four original training cases. For each excluded case,
fit a seven-component correction to accepted high coordinates minus secant,
using only the other three cases (723 rows), training-only scaling, ridge=1,
augmented least-squares SVD and an unpenalized intercept. Freeze all four
correction models before any new numerical call. The prescribed control
correction is forced to zero. At inference the current answer is not used.

Evaluate the fixed indices 1, 61, 121, 181, 241 from each original secant arm,
using its native parent and accepted context. These differ conceptually from
the reference-arm parents in earlier answer-oracle diagnostics; comparisons
here are between strategies at each same original secant parent. The gate
returns a learned seed at score >=0.5 and abstains to secant otherwise. Numerical
rejection retains the existing fallback and accounting rules. No model or
threshold is tuned from these outcomes.

Alternate reference/secant/proposal and proposal/secant/reference order, followed
by a fresh reference at each parent. Preserve original request, arithmetic
profile and all tolerances. Existing prefixes are reused, not newly executed.
Case exclusion within this related and repeatedly inspected training family is
not independent project/geometry/history validation. The models remain research
artifacts; no public policy or solver default changes.

## Actual numerical result

| Across twenty parents | Secant | Gated learned correction |
| --- | ---: | ---: |
| Core calls | 20 | 20 |
| Inclusive linear solves | 78 | 84 |
| Newton assembly dispatches | 132 | 140 |
| Recorded arm interval sum, seconds | 5.512631344 | 5.697374446 |

The gate selects nine parents and abstains to secant on eleven. No parent has
fewer inclusive linear solves or Newton assemblies: five have more linear
solves and four have more assemblies. Seventeen proposal arm intervals are
higher and three lower in this single observation. There are no extra fallback
core calls. A classifier with some predictive skill does not make this vector
correction effective.

All 60 response comparisons pass unchanged absolute 1e-10 / relative 1e-8
tolerances, and all twenty reference/fresh-reference terminal checkpoints match
exactly. Across all four arms there are 80 core calls, 386 inclusive linear
solves and 684 Newton assembly dispatches. Assembly dispatch counts do not
include every material integration or recovery assembly; those totals remain
unknown. This is a same-parent one-step study, not full-path equivalence or
independent physical validation.

## Costs and reproducibility

Correction data preparation takes 1.586015815 seconds; the four new fits total
0.004027841 seconds. The numerical campaign loop takes 27.434801790 seconds,
including model/request loads and paired execution, excluding prior data
preparation/fitting, staging/imports and later audit. The previously trained gate
also has earlier preparation and fitting costs. Arm intervals charge current
feature generation, prediction, event serialization, solves and step recovery/I/O.
Do not sum nested intervals or interpret batch/prior fit costs as free. No
full-path amortization or net speedup is established.

The [receipt](rc-gated-vector-steps-20260914.json) binds the immutable packet,
source archive, frozen protocol/models, original input bindings, runnable
experiment/auditor, callback records and actual execution log. The audit verifies
source archive extraction, bound input bytes, every gate score and proposed seed,
step/path/report hashes, all numerical invocation counters, response comparisons
and exact reference repeats. All 1,323 sealed file entries are reread for length
and SHA256. No extra fit or numerical solve is used for this audit.

## Decision

Do not adopt this gated correction or schedule a large held-out runtime campaign
for it. The missing link has been executed and is negative on the fixed training
parents. Future proposal work must first show actual work reduction on training
parents without using current answers, then freeze its policy before independent
geometry/history evaluation and charge the full end-to-end cost. Neither the
classifier's accuracy nor oracle headroom can substitute for this requirement.
The broader roadmap, external verification and issue integration remain open.
