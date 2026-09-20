# Same-parent benefit changes across nested seed policies

The completed nested campaign evaluates each of 165 original training parents
under four distinct seed policies, giving 660 sample/policy pairs. A read-only
diagnostic verifies the complete declared task roster, seed-fit index, case,
parent identity, repeated time labels and exact guard-feature equality before
comparing those four observations.

- **13 of 165 parents** change time-benefit label across policies.
- **48 of 165 parents** change solver-work category across policies.
- Every parent's four guard-feature vectors are identical, while its four
  seed-policy hashes are distinct.

The time label uses the unchanged three-repeat benefit rule. Work categories
retain the full core-call/Newton/linear-solve comparison in each repeat. No fit,
new numerical solve, reserved evaluation, threshold change or policy promotion
occurs. Every source sample, parent, policy and original report hash is retained
in the detailed diagnostic.

This shows a policy-dependent component in outcomes for the same accepted
state. It is **not** contradictory training labels within one gate: the four
observations belong to different excluded-outer-group experiments and are not
pooled by the existing fitter. It is also not a lower bound on a gate's error,
a causal attribution of wall time, or evidence that adding a categorical policy
ID would generalize. The 48 work-category changes support looking at the actual
proposer as well as the structural state in subsequent experiments, but do not
specify a useful low-cost representation by themselves.

Any such proposal-aware experiment must respect deployment timing. Features
obtained only after generating a candidate cannot silently appear in a
pre-capture guard, and candidate generation cost is due even if a later gate
declines it. Outer-group exclusions must cover the seed policies producing
training labels, not only the final gate table. This matters before performing
an additional inner validation split over the existing nested-label rows.

Observer source is `efb00a50d767b5b2d796944a585957224e559663`. It reuses the
verified immutable dependency snapshot from the prior work-counter diagnostic
instead of copying another complete source archive. Dependency verification
takes 0.110264 s; the subsequent read/diagnostic takes 0.166524 s. These are
separate intervals, not runtime benefit measurements. The
[machine summary](rc-policy-sensitive-labels-20260920.summary.json) records the
observer and dependency pins plus the final packet inventory.

The wrapper initially exits 1 while attempting to read its generated
`__pycache__` directory as a file during inventory creation, after the original
diagnostic is complete. A separate completion record preserves that failure
and enumerates files recursively. The observer and diagnostic are unchanged;
neither fitting nor numerical work is repeated. The completed packet's four
files / 475,921 bytes verify against its final inventory.

Six focused tests pass for order invariance, changed labels/work, foreign
parents/inputs, duplicate policy identities, omitted observations and wrong
seed bindings. Ruff and whitespace checks pass. This remains local evidence;
the current published `01948913f` CI predates this diagnostic.
