# Accepted material histories in design and process review

## Implemented scope

Source `ef52f67d47e34ed333ddaca80426df05d9284a26` connects explicit material-memory
limits to the existing RC design comparison, candidate search, process suite,
later exhaustive oracle, portable review and Workbench comparison. The caller
supplies limits for steel accumulated plastic strain and concrete tensile and
compressive damage. Every positive accepted epoch contributes to each maximum.
The original companion still preserves genesis and native parent-change counts.
Its plastic memory is not a count of current Newton yielding events.

The option requires the existing response-history scope. A failed screen blocks
selection; unavailable material verification preserves already verified terminal
and response-history results and quantities but blocks combined verification.
Recovery and validation costs remain in the inclusive reference/quantity and
online intervals, with no additional public analysis request. These are caller
research screens, not design-code acceptance criteria. Existing requests retain
their original versions when material limits are absent. See
`rc-fiber-design-experiments.md` for exact fields and version selection.

Process request bytes are preserved, including integer zero/one limits. Typed
numeric normalization is used only for semantic plan comparison. Material cases
use v2 worker/arm/oracle reports and M2 v3 comparisons; mixed suites can still
contain unchanged nonmaterial v1 workers. Suite/review roots are v2 when any case
requests material limits. Stored validators check source bindings, native field
coverage, statistics, extrema, requested limits, selection, costs and oracle
scope. The browser checks stored contracts and raw transport identities; it
does not execute the constitutive laws or authenticate external provenance.

## Correctness and prior-result preservation

The actual integration made two public analysis requests for the 150 kN L-frame:
the original 0.4 m section and a candidate changing only `RC1.width_m` to 0.5 m.
Both completed four load steps with original reference, response-history and
material-history verification. Terminal/history translation and strain limits
were 1.0, while material limits were steel accumulation 0, tensile damage .95
and compressive damage 0. Both steel accumulation and compressive damage were
observed zeros. These deliberately chosen test limits are not engineering limits.

| Result | Baseline | Wider |
| --- | ---: | ---: |
| Accepted tensile-damage maximum | .9699183857765405 | .924735138718369 |
| Material screen | fail | pass |
| Accepted translation maximum (m) | .004708535167124795 | .0033200104986236788 |
| Accepted absolute fiber-strain maximum | .000646046570443547 | .0004562733417283255 |
| Synthetic scoped material estimate | 169.0626 | 190.0626 |

The wider candidate is selected despite its higher estimate because the baseline
fails the declared damage screen. Prices are synthetic 100 per gross concrete
m³ and 1 per authored longitudinal rebar kg, labelled KRW; neither quotes nor
construction savings follow from them.

The four actual integration tests passed in 110.25 s. Original public results,
raw checkpoints and the exported bundle are preserved at
`/tmp/structural-material-design-integration-aaske5ds/`. This correctness run
overlapped development checks and is not performance evidence. The current TS
provider separately accepted its 1,066,413-byte bundle report, retaining original
file hashes and the same maxima, statuses and selection; receipt:
`/tmp/structural-material-m2-consumer-F72lvV/receipt.json`.

The saved-artifact comparison at
`/tmp/structural-material-baseline-parity-lgu1e2t4/receipt.json` finds no change to
the prior source-`d1f9ff9af` L150 public payload or complete constitutive companion.
The 2,316-byte input and 149,971-byte checkpoint are byte-exact. Public JSON differs
only in whitespace/key order, with no excluded payload fields. The prior response
history was not separately persisted, so only its two identities retained in the
companion can be compared; both match. All nine read originals stayed unchanged.

Other focused groups passed: CLI 61, material producer-stub 18, candidate-search
stub/math 35, new material plus process contracts 108, legacy suite/process/review
163, CI ownership/quality contracts 40, and Workbench contracts 170. These groups
overlap and are not summed. Nine existing candidate-search tests requiring their
separate actual-analysis fixture were excluded from the stub group. TypeScript,
Ruff/format, diff checks, production build and viewer-delivery verification passed.
The build retains its large-chunk advisory. Actual process and browser evidence
below are separate from these contract tests.

## Fixed-source process observation

The observation is retained under
`/tmp/structural-material-design-observation.5bge446k/`. All 397 package source
files were exported from the clean commit and checked against the worktree before
and after execution. Tests, source changes and other numerical workloads were
stopped during the interval; lightweight artifact inspection and preparation of
post-run scripts continued. Exclusive host access is not asserted. The host
reports Ryzen 9 5900X, 24 logical CPUs, Linux 6.5.0-26-generic, Python 3.10.12,
NumPy 1.26.4 and SciPy 1.12.0.

One case, two measured repetitions, zero warmups and budget two per online arm
retain the existing order rule: deterministic/learned/oracle, then
learned/deterministic/oracle. Each worker makes its own full baseline and candidate
requests. All six worker/report/resource contracts passed, with **12 current
public requests**, eight online and four oracle. Original training generation's
four requests are charged once, giving **16 accounted requests**. There are no
unknown requests, failed slots, unavailable resources or additional fits.

The unchanged 31,759-byte training artifact comes from
`/tmp/structural-candidate-process-observation.5TRGr2/training.json`, raw SHA-256
`7654095ce46654a6a59865131ec4199696bdc677f31f62a595374cbe78d8c605`.
Its original source and train/validation/holdout records remain intact. Both
learned workers report `analysis_context_out_of_distribution` for the two-member
L-frame; numerical predictions and predicted terminal safety remain unavailable.
Both online strategies inspect the sole candidate and choose `wider`. The later
oracle records zero missed feasible candidates. The learned false-safe count is
zero with no predicted-safe candidate, so it establishes no predictive safety.
History/material safety prediction authority remains false.

All 12 public payloads and companions match their corresponding correctness
result exactly. The six instances of each of two physical models also have exact
response-history equality, covering 48 positive accepted epochs in total. These
repetitions are not independent case families. The 1,823-check saved audit passed
without solves, physical recovery, training or workers. It independently aggregates
native statistics from the two retained correctness checkpoints and compares them
with every matching worker descriptor/companion. Worker checkpoint bytes were not
separately saved; this establishes digest/length binding to retained bytes, not
a direct byte comparison between two saved worker checkpoints. Engineering energy
and recovery identities remain bound assertions rather than independent replay.

The first preparation script passed dataclass tuples to a strict JSON decoder and
failed before any worker or analysis. Its already serialized request had the
correct arrays. `complete_preparation.py` read those unchanged bytes and completed
the plan check; no numerical retry occurred. The failed preparation clock receipt
is unavailable, not zero. The successful separate plan check took .020495 s wall
and .020494 s CPU, outside the measured CLI, which repeated its own charged
preflight. Both scripts and the original exception log remain preserved.

## Observed resource and cost scopes

Each table row contains two observations. Slot wall time includes parent request
persistence, worker launch and parent validation; its scope excludes shared
preflight/final aggregation and historical training.

| Strategy | Slot wall (s), repetition 1 / 2 | Worker CPU sum (s) | Peak RSS range (MiB) |
| --- | --- | ---: | --- |
| Deterministic | 106.684558 / 105.042524 | 210.989155 | 123.332031–123.582031 |
| Learned | 105.786411 / 105.603765 | 210.628893 | 123.058594–123.652344 |
| Oracle | 104.467197 / 105.924525 | 209.851181 | 115.625000–115.761719 |

The paired deterministic-minus-learned slot differences change sign:
**+.898147 s and −.561241 s**, median +.168453 s and population SD .729694 s.
No consistent acceleration or learned ranking benefit is established. The raw
report's 229-reuse projection assumes this small positive median persists within
the same slot scope. It is not an observed break-even, and the OOD single-candidate
experiment does not establish a useful predictive contribution. Oracle report
shape differs from online reports, so its lower RSS is not an equal-output
memory advantage. Separate-process peaks are not summed or subtracted.

| Strategy | Input bytes / read time (ms) | Search bytes / write-flush-fsync (ms) |
| --- | --- | --- |
| Deterministic | 72,474 / .378082 | 5,594,748 / 18.229360 |
| Learned | 72,462 / .369071 | 5,595,317 / 33.133230 |
| Oracle | 72,836 / .354042 | 2,133,887 / 14.168456 |

These are file-API observations, not physical disk traffic. Source imports,
sidecars/manifests and final parent-suite persistence are excluded from the
reported file-I/O counters, with no separate byte/time counters for those
operations. Relevant work appears only within the broader stated wall/CPU
intervals. Worker CPU ends after search persistence and excludes resource-sidecar
emission; parent CPU ends after aggregation and excludes final suite persistence.

- Parent wall through aggregation: 633.640879 s. CLI launch to exit: 636.041066 s,
  including imports and final suite serialization/persistence. These overlap.
- Worker CPU subtotal: 631.469229 s; parent CPU: 1.144953 s; disjoint subtotal:
  632.614182 s. Historical CPU is unavailable. Driver launch/wait CPU is separately
  .189230 s and does not represent either the CLI parent or its workers.
- Parent preflight: .131450 s wall / .123204 s CPU, already included above.
- Historical generation: 38.517924 s; fit: .001512 s, both charged once. Parent
  wall plus historical wall is 672.160315 s. Preparation, audits, exports and
  browser checks are outside this measured scope.

## Portable and browser review

The saved Python writer/validator produced 38 portable files totaling 32,896,556
bytes, including four M2 v3 comparisons and all six worker slots. A second copy to
`review-bundle/` matched every byte. `postrun/audit.json` records all outcomes and
resource/limit/source consistency checks.

The final actual HTTP Chromium audit passed at UI commit
`8126fc718c7691443ca6d9a00b67d5702ca0d5e7`, with numerical producer source still
`ef52f67d47e34ed333ddaca80426df05d9284a26`. The 397 Python package files remain
unchanged. This source map also matches the earlier correctness package identity
`sha256:2aa4ee77b78f1c965cc01a7a4bb54d0795e402a2c0d54a32260f8c532d100ab2`;
the two later commits change only table accessibility and overflow containment.
The existing production build served the actual portable bundle through a
loopback server, without fixture interception, extra solves or fabricated assets.
Receipt: `/tmp/structural-material-browser-actual.WVOu1T/receipt.json`.

Both desktop 1440×1000 and touch-enabled mobile 390×844 passed all four online
comparisons and two later oracle selections. Each viewport verified ten
original-byte downloads (eight comparison report/manifest files plus the whole
suite and review manifest) and four whole-Workbench JSON exports. The exports
preserve the selected report/run and complete suite. All 51 original review/build
files retained their byte lengths and SHA-256 values. Each viewport retains 24
screenshots, six layout observations and the full network/console diagnostics.

The UI shows accepted steel accumulation and compressive damage as observed
zeros, tensile damage .9699/.9247, caller limits 0/.95/0, failed/passed screens and
the wider selection. All 13 column headers have accessible column-header roles.
Selectors are at least 44 px high; tables retain internal horizontal scrolling
and keyboard focus without document overflow. On mobile, the import-diagnostics
table is 602 px wide inside a 328 px region: an arrow-key scroll moves its content
while the document stays 390 px wide. Actual data contains no unavailable material
companion row. The observed-zero versus unavailable check uses the oracle's
unavailable online budget; malformed/unavailable material contracts are covered
by the separate contract tests, not a fabricated browser specimen.

The preserved earlier browser attempts include two actual UI defects and harness
diagnoses. `dc14a916e` adds explicit column scopes after accessibility inspection
found the comparison headers exposed as cells. `8126fc718` reuses the existing
scroll-region style for import diagnostics after the unchanged table extended the
mobile document to 633 px. The harness also needed explicit repetition option
values, since a string could match the label of a different value, and a narrow
exception for the observed Google Fonts stylesheet/font requests. Review-data
fetches retain same-origin enforcement. Failed runs and DOM-only probes remain
separate from the final successful run; no source mutation or assertion relaxation
from a diagnostic probe is part of the successful observation.

This is a passing candidate-review audit, with retained diagnostics rather than a
zero-network-error claim. The final desktop records one candidate resource fetch
`net::ERR_ABORTED` event. Its HTTP 200, 2,446-byte complete-body timing,
server-response finish, original SHA-256 provider verification and bound
suite/manifest/whole exports are all recorded together; the browser event is not
attributed to cleanup. No candidate fetch failure occurs in the final mobile run,
and neither viewport has an uncaught page error. Existing viewer/evidence assets
still return 404s, and the legacy viewer logs `initLog is not defined` before demo
fallback. Each viewport retains nine unrelated HTTP failures and ten console
errors, plus iframe/WebGL warnings. The Workbench shell remains Demo while the
attached candidate review retains the actual producer identity. Hosted delivery,
the unrelated viewer data path and whole-application readiness are not verified
by this local audit.

## Retained artifact identity

`/tmp/structural-material-design-observation.5bge446k/artifact-inventory.json`
seals **831 files, 553,677,289 bytes**, excluding the inventory itself. The
174,534-byte inventory has SHA-256
`b4f442dc803f0789e195372c25750d5357fbb6745bb7756452e664c2559c30c0`.
Creation and a separate read-only verification both checked exact file coverage,
lengths and every hash. All failed preparation/browser attempts and diagnostic
probes are retained alongside the final successful observations. No contents
were changed after sealing.

The browser collection inventory covers 11 original roots, 224 files and
474,675,508 bytes. Exact copies are under `browser-evidence/`, including the
final `structural-material-browser-actual.WVOu1T/receipt.json`. The collection
receipt also binds the final 13 compiled assets and the tracked Workbench source
plus declared build configuration. That source subset is not a complete build
dependency archive. Copied reports retain their original absolute source paths.

| Retained file | Bytes | SHA-256 |
| --- | ---: | --- |
| `request.json` | 1,540 | `cc4ea29aa5263c2529de0365fc39806a689fb9759ba62802d5ad37a354b07759` |
| `suite/suite.json` | 15,214,330 | `41de7a6ccb4929b477a0f3de9ac909a5b39d78c1ffc0b819382cb6202a9cc2fc` |
| `postrun/audit.json` | 2,704,304 | `a76cf0e7434f7ec8f7ff59e0b9f4e5cd128a8f9a0e9726bfb9417ebafbe39f80` |
| `review-bundle/manifest.json` | 10,917 | `ae9dcb56e5c4882cf0aef58e80697222d1b1e277bf3909308951dbbaf3a4aa4d` |

## Remaining authority and scope

The nine separately preserved force-controlled steel-plastic probes all failed
before retaining positive steel accumulation; see
`rc-fiber-steel-plastic-path-probes-20260909.md`. This integration adds no yielded,
cyclic, dynamic, design-code or independent material validation. Broader case
families, external corpus/provenance/licensing, hardware/operator qualification,
hosted integration and owner/admin/release decisions remain open. The complete
M1–M5/P1–P3/R1/R2 objective remains active.
