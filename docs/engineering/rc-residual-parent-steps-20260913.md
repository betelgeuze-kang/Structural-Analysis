# Residual-directed correction: actual same-parent step costs

Numerical source `d2c696a405b874354c0ab35b2c1ba6f7e35a9924`.
The [residual-only diagnostic](rc-residual-directed-20260913.md) could not answer
whether a smaller residual would save later Newton work without immediately
passing the residual gate. This follow-up executes that missing comparison.

## Frozen protocol

Use the same four original training cases and indices 1, 61, 121, 181, 241.
These parents and their earlier residual outcomes were already inspected. No
held-out claim is made. Freeze all twenty before new step-cost observations;
alternate reference/secant/proposal and proposal/secant/reference order, then
execute a fresh reference in each group. Retain original native parent/prefix,
request and arithmetic profile. No full prefix is re-executed or newly authenticated.

The callback recomputes the secant residual and Jacobian at the original parent,
then derives the bounded scalar from the current residual, Jacobian and secant
advance. It does not use the current accepted answer. All twenty coefficients
and seeds exactly match the preceding residual-only observation. Each callback
adds one assembly; callback time includes this work and diagnostic event writes.
The solver separately records actual Newton assembly dispatches. Full original
paths, model fitting and held-out evaluation are not performed.

## Actual work and response checks

| Metric across twenty parents | Secant | Proposal |
| --- | ---: | ---: |
| Primary convergence rows | 46 | 46 |
| Inclusive linear solves | 78 | 77 |
| Newton assembly dispatches | 132 | 132 |
| Additional proposal assemblies | 0 | 20 |
| Recorded arm interval sum, seconds | 5.420855570 | 6.066188018 |

Every parent has equal primary rows and equal Newton assembly counts in both
arms. Three proposal steps have fewer inclusive linear solves and two have more;
these differences are terminal refinement work, not saved primary iterations.
Every proposal arm is slower in this single observation. Arm intervals include
proposal generation, numerical attempts, recovery and step I/O, excluding the
final path write. Callback diagnostic event serialization is also charged. These
are instrumented one-step observations, not deployed or repeated path speedups.

The complete observation executes 80 numerical core calls, 375 inclusive linear
solves and 676 Newton assembly dispatches across all four arms, plus twenty
callback assemblies. Material integrations and recovery assemblies are not
included in the dispatch count; their total remains unknown. The campaign loop
is 27.894509887 seconds, excluding staging/imports and the later audit.

All 60 response comparisons to fresh reference pass the unchanged declared
absolute 1e-10 / relative 1e-8 tolerances. All twenty reference/fresh-reference
terminal checkpoints match exactly. Proposal/secant checkpoints need not be
byte-identical; this is step-response agreement, not whole-path equivalence or
independent physical verification.

## Audit and decision

The audit verifies source archive/extracted files and original input bindings,
report/path/step hashes, native parent identities, all actual invocation counters,
assembly event counts and every comparison against original stored responses.
Primary/terminal work is reconstructed from step records rather than inferred
from inclusive iterations. No extra numerical solves are used by the audit.
The immutable packet retains the protocol, source, runnable experiment/audit,
all original step/path records and logs. Its inventory is bound in the
[receipt](rc-residual-parent-steps-20260913.json).

Do not promote this single-direction correction or fit a surrogate merely from
its residual reduction. The missing actual-work question now has a negative
answer on these twenty training parents. This does not rule out other correction
representations, harder supported cases or other learning targets. Secant stays
the baseline; full-cost held-out benefit and the complete roadmap remain open.
