# Accepted-answer seed: training-parent work headroom

Numerical source `c62d0b67fc0599ef027a16e9de6114c960d2a24a`.
The preceding [scalar correction experiment](rc-residual-parent-steps-20260913.md)
saved no primary iterations or Newton assemblies. This observation asks whether
another representation can save work through the existing seed interface before
spending on another fitted policy.

## Protocol and interpretation

Freeze the same four original training cases and indices 1, 61, 121, 181, 241.
At each original native parent, propose the stored accepted coordinate high
components, including the augmented load coordinate. This intentionally uses
the target answer: it is an oracle diagnostic, never a deployable learned policy.
The original twofold compensation is recorded but cannot be supplied through
this binary64 seed interface. Consequently this is observed headroom, not a
mathematical upper bound or an exact full-precision solution initialization.

Retain original request, parent, context, arithmetic profile and tolerances.
Alternate reference/secant/proposal and proposal/secant/reference orders, with
a fresh reference after each group. The callback adds no assembly, but its event
serialization is included in its interval. Original prefix histories are reused,
not freshly re-executed. No new model fit or held-out case is present.

## Actual observations

| Across twenty parents | Secant | Accepted-answer seed |
| --- | ---: | ---: |
| Primary convergence rows | 46 | 20 |
| Inclusive linear solves | 78 | 47 |
| Newton assembly dispatches | 132 | 80 |
| Recorded arm interval sum, seconds | 5.489816930 | 4.155957798 |

Fifteen parents reduce primary rows and assemblies; five tie. Sixteen reduce
inclusive linear solves and four tie. Fifteen arm intervals are lower and five
higher. These are single instrumented step observations, not repeated runtime
or full-path acceleration. Obtaining the oracle answer already required the
original solve; its generation cost is not part of these arm sums. Therefore
the time difference cannot establish a net achievable product speedup.

All 60 comparisons to fresh reference pass unchanged absolute 1e-10 / relative
1e-8 response tolerances. All twenty reference/fresh-reference terminal
checkpoints match exactly. Across four arms there are 80 core calls, 345 inclusive
linear solves and 624 Newton assembly dispatches. Total element integrations
remain unknown. Campaign loop time is 26.230190332 seconds, excluding staging,
imports and subsequent audit; no whole original path is newly run.

## Reproducibility and next decision

The [receipt](rc-answer-seed-parent-steps-20260914.json) binds the immutable packet,
source archive, runnable experiment and auditor, protocol, original input hashes,
step/path reports, callback records and original execution log. The audit checks
source archive extraction, input bindings, answer vectors and omitted compensation,
report/path hashes, native parent identities, actual per-step work and response
comparisons. All 1,322 inventory entries were independently reread for length and
SHA256 after sealing. No additional numerical calls occur in the audit.

Full-vector binary64 seeds have measurable work headroom on these already-known
training parents. This changes the next experiment from more scalar-direction
fitting to measuring how accurately a vector correction must be recovered before
its work savings survive. Such a tolerance study must remain training-only;
a subsequent learned policy must be frozen before independent geometry/history
assessment and charged for training, feature extraction, fallback and validation.
No learned benefit, independent physical validation, or roadmap closure is claimed.
