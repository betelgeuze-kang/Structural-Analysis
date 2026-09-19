# Connected training groups for warm-start runtime selection

`run_rc_control_runtime_selection(...,
withholding_strategy="connected_training_groups")` adds an explicit group
exclusion mode to the existing full-path runtime selector. The default remains
`case`, preserving earlier experiments as leave-case-out internal tuning.

Training cases are connected when they share a declared project, geometry-family
or load-history ID, or when the existing conservative geometry/history screens
find overlap. Geometry checks retain scale/rotation/reflection and collinear
subdivision handling; history checks retain amplitude/sign normalization,
monotone resampling and truncated prefixes. Connected components include indirect
links, so A sharing a project with B and B sharing a geometry with C excludes all
three together. Validation/holdout cases do not enter the grouping or fitting;
the original cross-split preflight still runs first.

The original plan records the exact groups and pairwise connection reasons before
any fit. Every fold's fit receipt records the whole excluded group; no sample from
that group enters its normalization or regression. If all training cases connect
into one group, the request fails before output creation or fitting. Renaming
cases therefore cannot manufacture a usable geometry/history holdout.

Execution still evaluates each training case's entire path with reference, secant,
proposal and fresh reference. Existing error thresholds, known-work requirements,
full clocks and conservative secant selection are unchanged. Scores remain
**equal-case weighted**, not equal-group weighted. Fits are performed once per
withheld case/ridge and reused across that case's repetitions, rather than cached
across distinct cases sharing a group; all performed fits remain charged.

This is stronger internal tuning separation. Caller-declared project identifiers
are not authenticated provenance, conservative grouping is not physical
equivalence, and the resulting timing cannot establish independent generalization
or learned benefit. Previous measurements are not retrospectively relabeled.

## Focused evidence

Five new group/withholding tests passed in 44.13 s. They cover transitive project
and geometry connections, history aliases under new IDs, deterministic ordering,
ignoring evaluation cases in training groups, and pre-fit refusal when no fitting
group remains. A real three-training-case run generated fresh labels, then fitted
and executed all three withheld-case paths under two connected groups. Persisted
policy sample hashes exactly equal the complementary group's samples, and every
full-path comparison passed. These deliberately tiny internal paths establish
implementation behavior; they are not a new nonlinear speedup benchmark.

An additional 25 existing split, default full-path, excluded-label and budget
regressions passed in 33.37 s. Ruff and diff checks passed. Original solver
acceptance thresholds and default case-exclusion semantics are unchanged.
