# Native reuse across design search, replay and Workbench validation

The existing opt-in optimization now reaches durable control paths, the bounded
control API, design comparison, candidate search and their design/search CLIs.
`reuse_line_search_assembly=True` remains optional and defaults to false.
Both CLIs expose `--reuse-line-search-assembly` for evaluation. Candidate-policy
training remains unchanged; this is an execution option, not a new learned model.

## Consistent execution and artifact binding

When enabled, the API request, durable restart scope, design request/report and
candidate-search plan declare
`line_search_assembly_reuse=rc-control-immediate-line-search-reuse.v1`.
Their existing hashes include the declaration. Default artifacts omit it.
Analysis, fresh verification, restart-prefix replay, suffix execution, baseline,
every shortlisted candidate and the exhaustive oracle receive the same option.
Constant preload remains on its original fresh assembly path.

A result verified with a different setting is rejected before a fresh source
solve. A restart requires the same scope setting and still replays its entire
accepted prefix. Successful native/default API comparisons retain identical
physical response histories and Newton-work totals; the request and restart
metadata intentionally differ. No convergence tolerance, constitutive law,
checkpoint commit/rollback rule or verification requirement changes.

Workbench design validation recognizes only the named profile, includes it in
the request hash and binds it to both API request and native restart scope.
Search validation binds every constituent design comparison to the plan's
profile. Rehashed unknown profiles and plans claiming reuse over ordinary
comparison artifacts are rejected.

## Executed validation

- 228 Python API/path/design/search tests passed, then three added malformed-flag
  checks passed before compilation. The API test includes a successful native
  replay and rejection of mismatched verification/restart settings.
- 59 Workbench contract tests passed, including unknown/mismatched profile cases.
- TypeScript `--noEmit`, Ruff, diff checks and scoped mypy on six source files
  passed.
- The current Workbench search validator was bundled and run directly against
  actual native search artifacts, then against a separately executed native CLI
  search. Both validate all three arms. This is validator execution, not a new
  browser-rendering or deployment test.

The retained search uses the existing authored cantilever, 600 kN constant axial
load and targets `[-1e-5, -2e-5, 1e-5]` m. Training widths are 0.32, 0.40 and
0.54 m; evaluation baseline is 0.43 m with alternatives 0.36, 0.46 and 0.50 m.
Prices and performance limits are development inputs, not market quotes or
approved design constraints.

For each of the direct and CLI searches, price-order and learned-order arms
verify two rows each, and the later oracle verifies four rows. Analysis plus
fresh verification use 16 + 16 + 32 = **64 step executions per search**. Both
searches are retained, totaling 128 such executions. The separate original
three-model training fixture has 24 label-generation step executions. Other
test-suite work is excluded from these packet counts.

All three search strategies select `cheap`. There is **no new learned advantage,
candidate optimality generalization or speedup measurement** in this integration
run. The [earlier native runtime study](rc-native-assembly-reuse-20260912.md)
contains the separate timing experiment and its limitations.

## Evidence and remaining scope

Base revision `f9cfed9bdd182834b17abd80571fd4dd5a356cf0` plus the captured source
changes. The direct fixture's `a`-repeated revision is an artificial test label;
the CLI's revision names the base, not an attestation of the uncommitted changes.
Source snapshots and raw artifacts establish this run's provenance separately.

Packet: **224 files / 4,734,778 bytes**. Adjacent inventory was reread and verified,
SHA256 `1a57c1f388976680a7f2a3d96c29be476d940b62ccc6e2aec5e1441d0447497c`.
[The summary](rc-design-native-reuse-20260912.summary.json) records paths, hashes,
test scopes, choices and work totals. No ignored runtime data is added to Git.

Hosted CI, the earlier binary64 yield-case baseline mismatch, learned net benefit,
independent physical validation and release/owner acceptance remain open. The
job-service request transport and UI submission controls have not been extended
to expose this option; these changes validate CLI-generated study artifacts in
the existing Workbench review path.

[Durable job integration](rc-job-native-reuse-20260912.md) subsequently adds the
execution option to stored job requests and verifies worker, replay and browser
display bindings. The RC review panel remains a review view, without a new form.
