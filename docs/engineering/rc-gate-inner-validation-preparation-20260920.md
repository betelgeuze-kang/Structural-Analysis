# Ten 66-row seeds prepared for additional gate validation

The [three-group exclusion protocol](rc-gate-inner-validation-protocol-20260920.md)
has completed its seed-preparation stage at source
`e471feef529b14611d2d305a4792cab023a25ee3`. Ten actual seed fits use exactly
66 original rows each, excluding the outer, added validation and label groups.
All 20 directed gate-validation folds pass the provenance checks.

The plan audit uses the actual original 165 samples and existing nested seed
declarations. All 60 logical training-task usages in a naive added validation
split would retain 33 validation-group rows in their producing seed. This
would contaminate the proposed extra validation stage. The original outer-only
experiment is not invalidated, because its actual outer group is excluded.

A separate read-only audit verifies all 1,210 preparation-packet files /
123,284,927 bytes, regenerates the complete plan, checks each strict policy
hash and exact 66-row sample list, and reproduces feature means, minima,
maxima, scales and target scales. Maximum ridge normal-equation residual is
`2.9885338614357306e-13`. No second fit is performed for this audit.

Ten seed fits take a combined 0.189272 s, inside a 0.948870 s preparation
driver and a 2.702712 s outer process. These are nested intervals. The separate
audit takes 0.310107 s before report output. Original label-generation costs
remain separately preserved; concurrent numerical work prevents interpreting
these observations as isolated runtime benchmarks.

The [machine summary](rc-gate-inner-validation-preparation-20260920.summary.json)
records exact sources, packet/inventory pins and each policy hash. The initial
plan's zero executed-fit count describes its pre-execution state; completed
result and outer receipt both count **ten seed fits**. There are **zero new
gate fits, label comparisons or structural solves** in this preparation stage.
Reserved cases remain untouched and no policy is promoted.

The future 990 unique parent/policy label pairs, 2,970 repeated comparisons
and 11,880 single-target paths have **not run**. Source-bound generation,
counterbalanced cost recording and subsequent gate validation remain required.
Do not start timing generation while the 2,048-layer solve is live. Inner
development validation will still not prove independent project or full-path
runtime benefit.

Four focused planner tests pass, including hidden seed-training contamination
and incomplete complements; Ruff and whitespace checks pass. Published
`01948913f` CI predates this preparation code.
