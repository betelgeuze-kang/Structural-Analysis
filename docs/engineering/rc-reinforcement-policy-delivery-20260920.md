# Reinforcement-policy CLI and Workbench delivery

Both candidate-search CLIs now load only explicitly supported policy schemas via
`load_rc_control_candidate_policy`. Dispatch uses bounded strict JSON decoding;
unknown/non-string schemas and duplicate keys reject before policy execution.
The selected policy class still verifies all dimensions, finite values, hashes
and targets. Training opts in with `--reinforcement-features`; omission preserves
the original learner. Standalone learned-order execution recognizes the same
new schema and retains its complete process/runtime accounting.

Workbench search review now requires a matching policy/training schema pair for
either the original candidate learner or the new reinforcement learner. An
unknown or crossed pair is not treated as compatible. Existing original-byte,
full-reference, quantity, cost, training-overlap and artifact checks remain.

`scripts/build_reinforcement_search_workbench_fixture.py` executes actual train,
search (both arms plus later exhaustive oracle) and standalone learned CLI paths.
Three training models and two unseen evaluation models use a small three-target
reversing path with 600 kN constant axial load. Both arms select `cheaper` with
full-reference verification. The generated authenticated HTTP artifact handler
returns all **57 registered original artifacts** byte-exactly. This is in-process
HTTP-handler coverage, not an external network deployment test.

The compressed frontend fixture retains those original bytes as base64 strings.
Its reported numerical source is `f0849316472fdf2a27f820cc2ef0d95e7803171c`;
generation also used the local CLI/loader changes described here. It is an internal
software fixture, not an exact-commit external qualification receipt. The declared
prices are synthetic and the same-candidate result is not a learning benefit.

Validation:

- 108 Python learning/search/HTTP tests passed in 23.91 s.
- 57 frontend search tests passed in 11.4 s, including original and new policy
  reports, exact-byte tampering rejection, and 1440/390 px browser review.
- Both browser sizes review learned selection, show separate top/bottom areas,
  and download a result byte-identical to the original artifact. Mobile screenshot
  was inspected. The first browser assertions used the wrong detail region;
  corrected assertions target the selected-model panel.
- TypeScript no-emit, Ruff and diff checks passed.

This closes the new policy's opt-in CLI and existing Workbench search-review
connection. It does not establish independent project/geometry/history
performance, repeated net learning benefit, specimen admission, physical
qualification or release approval. Interactive experiment authoring and those
roadmap acceptance requirements remain separate work.
