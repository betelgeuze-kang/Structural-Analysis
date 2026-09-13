# Candidate learning with committed response and material history

The previous candidate policy learns terminal translation and fiber strain.
Full design selection can already require accepted-history response and material
memory limits, but those limits do not affect the old policy's ranking. A
candidate that looks promising at the terminal step can therefore consume the
limited analysis budget while failing a requested history or damage screen.

The explicit `terminal_and_committed_material_history.v1` target profile adds
five history targets to the original two terminal targets. It ranks candidates
against the requested scopes and retains the original full-reference analysis
as the only authority for final selection. Existing terminal policies keep
their original v2 serialization and behavior.

## Labels and fitting

Call `train_fiber_frame_candidate_policy(...,
target_profile="terminal_and_committed_material_history.v1")` to request new
labels. An existing two-target artifact cannot be relabeled into this profile.
The policy and learning report use explicit v3 schemas. The seven targets are:

| Scope | Targets |
| --- | --- |
| Terminal | Maximum translation in m; maximum absolute fiber strain |
| Committed response history | Maximum translation in m; maximum absolute fiber strain across accepted epochs |
| Committed material history | Maximum steel accumulated plastic strain; concrete tensile damage; concrete compressive damage across positive accepted epochs |

Collection uses the existing public analysis, full result validation, original
response-history recovery and source-validated constitutive companion. It stores
compact native per-epoch labels and their result/checkpoint/recovery bindings.
A missing or failed requested source blocks label collection and retains its
request, failure and cost. Label maxima are independent of the subsequent
candidate search limits.

Preprocessing, target scales, feature ranges and ridge weights use train rows
only. Validation and holdout targets do not enter fitting. The feature context
remains fixed in geometry, connectivity, load history, material laws and analysis
configuration; authored section/rebar inputs vary. This profile adds history
targets, not new geometry/load generalization. The earlier L-frame OOD result
still requires a separately collected compatible-context dataset.

Saved artifact validation checks the compact labels' internal source/epoch/hash
relations and their maxima. It does not rerun physics or authenticate externally
supplied provenance. Existing exact physical training-overlap checks remain;
caller-declared group names and hashes do not establish independent projects,
licenses or a blind external corpus. Binding original dataset sources to a
separate search-case group declaration remains a broader roadmap requirement.

## Ranking and final selection

Only the new profile carries the explicit history prediction and requested-scope
decisions. Candidate ranking and near-limit exploration use terminal and every
requested history/material limit. Unrequested scopes do not constrain the rank.
Missing, invalid or OOD predictions remain unknown. A zero material limit admits
an exactly zero prediction and rejects a positive prediction without dividing
by zero or introducing nonfinite JSON.

The deterministic strategy keeps its quantity/price ordering and makes no learned
safety prediction. Both strategies retain the same full-analysis budget,
including the baseline. The original reference result, complete requested
histories, quantities and declared common prices govern the selected candidate.
An estimate never waives a failed structural screen or authorizes a design.

The separate oracle runs after frozen online plans. Existing terminal false-safe
counts remain identifiable; new combined counts compare predicted acceptance of
all requested scopes with their complete reference outcomes. Unverified outcomes
remain separate from known failures. Deterministic prediction counts remain
unavailable because that strategy makes no prediction claim.

The policy hash and explicit target profile bind the frozen search declaration,
worker plans and reports. The process reader retains old default bytes, while
rejecting profile removal or downgrade. Workbench verifies those source bindings
and audit arithmetic before showing the prediction scope and measured final
comparison. Changing a viewed slot or downloading a report performs no analysis.

## Actual local correctness integration

The final implementation commit is
`33431e300335b71b9a2c228acf0b419350b2ffcf`.
The generation source is the retained 397-file Python package tree
`sha256:71d969a27e6897042ea6273a6b783237c36e228efc5798f57891af1f50863397`.
The test checks this identity before and after its numerical calls; the subsequent
source copy matches every file. This is a content identity and post-execution
copy, not an attestation or a predeclared performance experiment. A later review
adds a no-solve suite ranking check, described below; the original generation
snapshot and outputs are preserved separately from that final source change.

Four actual public requests collect labels for widths .34/.46 m (train), .37 m
(validation) and .43 m (holdout) in the original cantilever context. All use the
same low load, two accepted epochs and caller-declared group identifiers. Only
the two train rows fit the policy. All three material-memory targets are zero;
this tests collection and binding, not damage/plasticity prediction accuracy or
independent project generalization.

The saved artifact is restored into one fresh learned worker. It evaluates the
.4 m baseline and .395 m candidate with an identical budget of two public
requests. Both pass full original reference, response-history and material-history
verification, and the candidate is selected under the declared synthetic common
prices. The broad terminal/history/material limits are correctness fixtures,
not design acceptance criteria. The declaration permits two repetitions, but
this integration launches only one learned worker and no deterministic/oracle
workers. It is not a completed repeated comparison suite.

There are **six public analysis requests** in total: four historical label
requests and two online requests. Generation costs 27.246638003 s and fitting
0.002006916 s; worker workload is 13.629025979 s within its 15.131597873 s
launch-to-exit interval. These scopes overlap and include their existing
validation/recovery costs; internal source replays are not extra public-request
counts. The timings belong to a correctness run and establish no comparative
speed or net benefit.

The retained root is
`/tmp/structural-candidate-history-integration-p29nk1z_/`. It contains all four
original public results and checkpoint bytes, models, training report, frozen
declaration, worker request/report/resources/manifest and the matching generation
source snapshot. The checked-in compressed frontend fixture retains the original
training and declaration bytes only, with their exact byte lengths/hashes and
explicit limitations in `provenance.json`. The full worker report remains in
the retained root.

The completed root is sealed at **465 files / 9,738,754 bytes**, excluding its
95,569-byte inventory. Inventory SHA-256:
`f5db5a2133ac67dd29d1467d211e82078c29c6e4c497d7e6a411fc37399a0767`.
Creation and a separate read-only verification both confirm exact file coverage
and all raw hashes. `audit.json` records 464 saved-source/label/worker/fixture
binding checks with zero new analysis or fitting calls. `completion.json`
distinguishes the generation snapshot from the final implementation, and
`implementation-manifest.json` retains the 18 exact committed implementation/test
blobs. The only Python difference from the generation snapshot is the later
single-process suite validation correction. Initial failure logs, passing
follow-ups and the focused browser runner are included. These local checksums
are consistency records and do not authenticate origin or establish independent
physical verification. The sealed root must not be rewritten.

## Focused verification

The separate test groups overlap and must not be added into a claimed whole-suite
total. The current checks cover:

| Group | Result and scope |
| --- | --- |
| Learner | 83 passed; new profile/source/label guards, train-only fit and original v2 serialization |
| Search, suite and material contracts | 135 passed in 3.93 s after cross-review correction; includes five new coherently rehashed ranking/shortlist rejection cases |
| Existing process contracts | 65 passed; saved inputs, policy decoding and process identity |
| Actual integration | 4 passed in 44.08 s; the six public requests above, saved-policy restoration and profile-removal rejection |
| CI ownership and registration | 44 passed; all three new Python modules and both frontend specs are registered |
| Frontend contracts | New profile group 48 passed, then 3 actual-producer byte tests passed; 47 existing contracts passed in the earlier combined run |
| Browser delivery and review | TypeScript, Vite build and delivery checks passed; 10 Chromium tests passed, including new desktop/mobile scope, audit, exact-download and overflow checks |

The new browser rendering tests use explicitly synthetic profile metadata on
retained transport fixtures. Separate actual-producer tests accept the original
Python training/declaration bytes and reject profile stripping and material
targets detached from their stored epoch labels. Neither is independent physics
replay. No new numerical requests are made while producing the frontend fixture
or auditing the stored artifacts.

Read-only cross-review found that the single-process suite verified reported
shortlist hashes without recomputing ranking and shortlist against the new
combined prediction scope. A coherently rewritten custom-runner report could
therefore retain a stale terminal-only order. The final correction recomputes
both strategies' ranking and shortlist for the new profile before accepting the
report; the separate fresh-process path already compares the complete frozen
plan. Existing terminal-only contracts remain unchanged.

Initial failures remain in the retained logs: a tuple/list equality assertion
was corrected to compare serialized v2 bytes; a test-helper import and incomplete
price fixture were corrected; a frontend text assertion was aligned with the
actual approval-boundary copy. Passing follow-up tests do not erase those runs.

A separate observation at frozen `0183c600d` subsequently finds useful learned
ranking on one damaged three-candidate pool under two repeated research screens.
Its 38 original public requests and actual desktop/mobile review are documented
in `rc-fiber-damaged-candidate-history-runtime-20260909.md`. Four deterministic
arms find no feasible winner, so that suite remains incomplete and cannot support
equal-quality speedup or amortization. Repeated compatible families, independent
corpus/provenance, net performance and hosted integration remain open. The
original failed studies and bounded terminal-polishing observation retain their
existing identities and conclusions.
