# Reaction-only provenance and fracture-energy source refresh

Update: the protected reaction-only receipt was subsequently restored to the PR
base; the corrected checker and fresh local validation remain. CI regenerates
the receipt in its ephemeral runner. See [the CI boundary correction](package-preparation-ci-boundary-20260913.md).

The remaining reaction-only baseline failure combined stale Newton input hashes
with a commit self-reference: its checker compared the generation commit directly
with the current HEAD. Committing an otherwise unchanged generated receipt would
therefore make its check fail again.

The checker now resolves the receipt's explicit 40-character source commit and
uses `commit_bound_input_metadata` to verify the builder's fixed input set against
that commit and the current workspace. It requires the recorded input hashes to
match those committed inputs. Only after that check does result comparison allow
the generation commit to differ from current HEAD. No receipt-supplied file paths
are used for provenance reads. The provenance helper is now included in the
receipt's hashed input set.

A temporary real Git repository regression preserves a valid receipt across an
unrelated commit and rejects an alias, unresolved commit, boolean commit, changed
input hashes, changed result and modified workspace input. The normal current
receipt is freshly generated from code commit
`d44cda596a5e9de259413a9468f929f46abb0b9b`. Its reaction/material results and
all authority claims match the old record. This still describes six committed
fully constrained steps with zero Newton iterations and zero linear solves;
it is not a nonlinear solver-convergence claim.

The fracture-energy concrete benchmark was also recomputed. Only the Newton and
capability-manifest source checksums, source-set hash and artifact hash changed.
All numerical results and bounded mesh-objectivity claims remain unchanged.
The old source-staleness checks and reproduction requirement remain enabled.

All **15 tests** across the reaction-only artifact and fracture-energy modules
passed in 3.51 seconds after final code/source binding. Ruff and format checks
passed. This addresses two baseline failure mechanisms; it does not establish a
new full-suite pass, independent physical validation, general material breadth,
hardware parity or learned net benefit.

Diagnostics: `/tmp/structural-reaction-fracture-refresh-_c1d4zej/changes.json`.
Final JUnit: `/tmp/structural-reaction-fracture-final-tests.xml`.
