# First-verified-feasible candidate process observation

At frozen source `f0acd24f130db4fe909a0faf9685d4db7e33437f`, the optional
`first_verified_feasible` mode completed 12 fresh workers over the existing
damaged L-frame pool. All four deterministic/learned pairs selected the same
fully verified feasible candidate. Learned ordering used eight online public
analysis requests versus 14 for price ordering. The four exhaustive oracle
workers added 16 requests: **38 current requests**, plus six historical label
requests charged once, give **44 accounted requests**. No labels were generated
and no policy was fitted again.

The retained root is
`/tmp/structural-candidate-stop-observation.5rnmmzev/`. This is a local development
and repeatability observation on previously known cases and oracle labels.
It is not a blind evaluation, independent family/corpus validation, global
optimization result or general performance claim. The implementation contract
and focused verification are described in `rc-fiber-candidate-stop-mode.md`.

## Frozen protocol and reuse

The two cases apply tensile-damage screens .95 and .94 to the same synthetic
L150 geometry and three candidate widths. The baseline width is .42 m;
`width-0425`, `width-0455` and `width-0490` change the section width to .425,
.455 and .49 m. Both strategies receive all three candidates and the same maximum
budget of four requests, including one fresh baseline. Two measured repetitions
per screen alternate online order, with zero warmups and a separate exhaustive
oracle after both online arms. The maximum budget differs from the earlier
baseline-plus-one-candidate experiment; these are not identical before/after
protocols.

All public requests use four load steps, 40 maximum iterations, residual
tolerance `1e-10` and solver-coordinate increment tolerance `1e-12 m`.
Terminal and accepted-history translation/strain limits are both 1.0 in their
respective units. Steel accumulated plastic strain and concrete compressive
damage limits are zero. These permissive response limits and selected damage
screens are caller research constraints, not structural design acceptance limits.

The process request is v3, with `stop_mode` bound through each input declaration,
frozen plan, arm/oracle report and suite. The preflight freezes price-order plans
as `.425 → .455 → .49`. Learned order is `.455 → .49 → .425` for .95 and
`.49 → .425 → .455` for .94. Predictions use the existing seven-target
`terminal_and_committed_material_history.v1` profile. All three candidates are
reported in the train feature range, with uncalibrated uncertainty and no
physical-result authority. No new prediction-error evaluation is claimed here.

The original six-label training artifact has four train rows and one validation
and holdout row each, from source
`0183c600dcdc2073ed1e890492ef166803ec0dbe`. Its 76,379 bytes are copied unchanged;
raw SHA-256 is
`f16efd105b167e7863741ad680033ec0ed992551482fb79f11cf92850d8d1ad9`.
`historical_reuse.json` binds the old sealed inventory, original/copied bytes,
training report and policy artifact. The policy hash remains
`sha256:dadb7cfa519e7833a42c98c46687e1db4daf1c046fe28726c651911481f2b879`.
The earlier oracle results were known before this protocol was declared, so
using the same frozen policy avoids refitting but does not make this observation
blind or independent.

The source snapshot contains 397 package files. The before/after receipts record
the same revision, a clean worktree, and unchanged frozen/worktree bytes for all
397 files; the driver also records all declared input and script bytes unchanged.
The capture hook is bound separately from the package source manifest and copied
into the frozen interpreter search path. It wraps each original public call once,
returns the original typed result and exports its public JSON and raw checkpoint.
Its import, serialization, persistence and memory overhead stay inside the
enclosing observed process costs. It neither changes the physical call nor
adds another public analysis to create a comparison bundle.

## Actual requests and selection

The CLI exited zero, and the suite is `ready` with report/resource contracts
passing for all 12 workers. All 38 requested rows retain ready public results
and full reference, response-history and material-history verification. All
terminal and response-history screens pass; material screening records 24 failures
and 14 passes. A screen failure is a verified feasibility outcome, not a failed
solver or missing result. There are zero unknown solver executions, invalid
worker reports/resources or unlaunched slots in this run.

Each table row describes both repetitions; request counts include the baseline.

| Screen | Selected width, both strategies (m) | Deterministic requests / unused budget | Learned requests / unused budget | Oracle requests |
| --- | ---: | ---: | ---: | ---: |
| Tensile damage ≤ .95 | .455 | 3 / 1 | 2 / 2 | 4 |
| Tensile damage ≤ .94 | .49 | 4 / 0 | 2 / 2 | 4 |

Every online arm stops at its first fully verified feasible result. The .42 m
baseline fails both damage screens. Price ordering must also inspect .425 m
before reaching the .95 winner, and both .425 and .455 m before reaching the
.94 winner. Learned ordering reaches each winner with its first candidate.
All planned IDs remain visible: unattempted suffixes have no result, execution
credit or feasibility claim. Genuine M2 bundles contain the original baseline
and actual attempted prefix in evaluation order, without repeating those calls.

The original oracle rows record these accepted-epoch maxima and scoped estimates:

| Width (m) | Maximum tensile damage | Synthetic material estimate, labelled KRW |
| --- | ---: | ---: |
| .42 baseline | .9606663726943693 | 173.2626 |
| .425 | .9588649919330566 | 174.3126 |
| .455 | .9471940743451447 | 180.6126 |
| .49 | .9304904804455402 | 187.9626 |

Steel accumulated plastic strain and compressive damage remain zero. These
native maxima describe retained material memory over positive accepted epochs,
not current yielding events or a calibrated damage acceptance standard. Prices
are explicitly synthetic: 100 per gross concrete m³ and 1 per authored straight
longitudinal rebar kg, dated 2026-09-09. Excluded construction items, unverified
quotes and unavailable confirmed currency savings remain in the original reports.

The full planned shortlist contains every candidate, so planned
`missed_feasible_count` is zero for both strategies in every pair. At .95,
both arms leave the also-feasible .49 m candidate unrequested and separately
record `unrequested_feasible_count=1`. At .94 there is no feasible candidate
left unrequested, so that count is zero. Learned terminal/combined false-safe
and predicted-safe-unverifiable counts are zero in this small pool; deterministic
prediction counters are unavailable. These counts do not establish calibrated
predictive safety. Oracle labels remain unavailable to online execution.

## Timing and resource scopes

The following are paired parent-slot wall intervals in seconds, rounded to six
decimals. Each slot includes its request persistence, worker launch/imports,
input preparation/ranking, all attempted reanalysis/recovery/stop/M2 work, report
persistence and parent validation. Shared parent preflight, final aggregation
and historical training are outside this paired slot scope.

| Screen | Repetition | Deterministic slot | Learned slot | Deterministic minus learned |
| --- | ---: | ---: | ---: | ---: |
| .95 | 0 | 157.582189 | 106.794680 | 50.787509 |
| .95 | 1 | 158.629350 | 106.487933 | 52.141417 |
| .94 | 0 | 210.589067 | 106.393707 | 104.195360 |
| .94 | 1 | 209.410299 | 105.637477 | 103.772822 |

The two-observation paired medians are **51.464463 s** at .95 and
**103.984091 s** at .94; population standard deviations are .676954 s and
.211269 s. Both pairs per screen have the same sign and the same selected candidate
under the requested quality gate. This establishes fewer observed requests and
lower paired elapsed cost in this declared run. Two repetitions on a known pool
do not establish a general speedup or isolate host contention from elapsed time.

Each strategy resource row below contains four separate fresh workers. CPU is a
sum of disjoint process lifetimes; peak RSS is a range of individual high-water
marks and is not summed or subtracted.

| Strategy | Worker CPU sum (s) | Peak RSS range (MiB) | Input bytes read | Search-report bytes written |
| --- | ---: | ---: | ---: | ---: |
| Deterministic | 733.959527 | 128.710938–136.347656 | 326,300 | 18,060,659 |
| Learned | 423.709135 | 121.144531–123.312500 | 326,276 | 11,227,108 |
| Oracle | 838.617384 | 119.015625–119.984375 | 327,024 | 8,550,610 |

Input-read counters cover bounded worker input files, while output counters cover
search-report persistence. They exclude capture exports, sidecars, manifests,
parent suite persistence and later portable export/audit; they are not complete
filesystem I/O counts. Capture export work remains included in enclosing wall,
CPU and RSS observations even though those bytes are outside these I/O counters.
Oracle CPU and elapsed costs remain charged separately from the online pairs.

The complete comparison CLI launch-to-exit interval is **2005.519108563 s**.
The process-suite parent interval through aggregation is **2001.932713515 s**,
including child waits and parent preparation/validation. Its own CPU is
3.182700021 s; workers contribute 1996.286046138 s, giving disjoint current
parent-plus-worker CPU 1999.468746159 s. Parent preflight is a subset
(.189658426 s wall / .179194332 s CPU), not another additive cost. Parent peak
RSS and historical CPU are unavailable.

Historical generation 310.587635558 s and fit .002199284 s are charged once.
Adding those to the parent-through-aggregation interval gives
**2312.522548357 s** accounted wall. This aggregate excludes the final suite
encoding/persistence tail, separate preparation and later audit/export/browser
work; it is not the complete CLI interval plus those same nested costs. The
separate no-analysis preparation preflight took .094898382 s outside the CLI.
The outer driver interval through comparison is 2005.557661204 s and is another
enclosing interval, not added to the CLI or parent wall values.

The existing per-case formula reports conditional reuse counts of seven at .95
and three at .94 to amortize that historical generation/fit cost using the
respective positive paired median. These are hypotheses under unchanged future
cost/quality assumptions. They are not observed break-even executions and exclude
shared preflight/final aggregation and later review costs from the paired saving.
The shared historical cost is not charged once per case or again per repetition.

The host reports Linux 6.5.0-26-generic, x86-64, 24 logical CPUs, Python 3.10.12,
NumPy 1.26.4 and SciPy 1.12.0. Agent tests, builds, source writes and other agent
numerical tasks were stopped during this run. Immediately before launch,
`prelaunch-process-observation.json` records another project's synthetic
measurement process, so other work may overlap. No processes were stopped;
neither exclusive host access nor timing causality is asserted. Bounded read-only
checks and preparation of post-run scripts also continued outside the worktree.

## Original artifacts and completed retained-data review

The 38 capture metadata records report complete exports, ready public results
and zero export errors. They cover four physical input identities, with a fresh
baseline once per worker. The subsequent saved-data audit checked the original
public JSON/checkpoint bytes, all requested material/history rows, the actual
prefix and budget, source Git blobs, historical reuse and portable M2 bindings.
The current suite identity is
`sha256:b18be7886935b3c232a205cf0b3dfa602c621f098daa70d59711c3961e661f9e`;
its report hash is
`sha256:8ecf3832093f39a671b5160f3f6f534ee8e45eae3da220b5b88e7a2d34283feb`.

The stdlib-only audit passes **15,244 checks**, with no failures. It forbids
project/numerical imports, arbitrary process/network calls and writes other than
its new receipt. Four same-input groups contain 12 baseline, eight .425, ten .455
and eight .49 calls. Every group's original public and checkpoint SHA-256/length
matches exactly. All 38 current calls also match the corresponding historical
original identities: the old capture metadata and its public/checkpoint identities
were checked against the previously sealed inventory, without rereading all old
large artifacts. Hash agreement is retained-byte consistency, not independent
physical replay or source authenticity.

The actual Python portable review export and full saved-bundle validation pass.
An execution guard records zero new numerical, training or worker calls. Including
guard instrumentation and child startup, export/validation takes 271.507230299 s;
the separate audit takes 4.420129242 s. These post-run intervals are additional
review work outside the measured comparison and accounted generation/fit sum.
Receipts are `postrun/review-export.json`, `postrun/audit.json` and
`postrun/checks-execution.json`.

The actual TypeScript HTTP provider accepts the exported v3 bundle. Desktop
1440×1000 and mobile 390×844 each verify all 12 original slots, planned/attempted
orders, stop reasons and budgets, selected M2 rows and native quantity/price/
response/material values. Each viewport downloads 18 files byte-exact to source:
the suite and review manifest plus both files for eight genuine M2 attachments.
The receipt records **480 counted comparisons** in addition to the UI assertions,
26 screenshots, no page errors, and no whole-document horizontal overflow.
Original inputs and build files remain unchanged, with no review refetch on slot
selection. Both browser contexts, browser and loopback server are closed.

The successful receipt is
`postrun/browser-artifacts/browser-fourth/receipt.json`; source/build provenance is
bound by `postrun/ui-build-receipt.json`. Three earlier harness failures remain:
a missing closing brace before any execution, an unavailable esbuild path, and
an overly narrow dependency assumption. Success uses the installed Vite library
builder with config/env/public-file loading disabled, Git-bound project source,
recorded Ajv dependency bytes and the generated Rolldown helper. No production
source, validation threshold or numerical input was changed to repair the harness.
All versions, diagnostics and original failure logs are retained.

Unrelated existing viewer diagnostics remain visible: missing preset/catalog
sidecars, the `initLog` demo-fallback error, drawing presentation warnings and
software WebGL/iframe warnings. The verified candidate-review panel passes; this
does not claim the whole viewer or application is free of errors.
The same receipt retains `net::ERR_ABORTED` on three desktop requests and four
mobile requests. Two desktop and three mobile aborts concern candidate-review
artifacts; the remaining request in each viewport is the missing static viewer
sidecar. Their cause is unclassified and remains a transport follow-up despite
the completed provider, displayed-value and original-download checks.

After all writers stopped, the root was sealed and a separate read-only invocation
verified the same inventory: **790 files / 385,977,598 bytes**, excluding only
the 154,341-byte inventory itself. `artifact-inventory.json` SHA-256 is
`5fb1000c2b8c2e07907e1bf4401aacba046e05bcf9fc57c057516aae0e783685`.
The inventory includes original numerical records, helper scripts, copied browser
artifacts and all failed harness attempts. Historical originals remain in their
separately sealed root. External UI source/dependency/dist inputs are receipt-bound
and are not copied wholesale into this inventory. This is local integrity
verification, not an independent operator receipt or an atomic filesystem snapshot.

This observation advances local implementation and measured first-feasible
candidate selection under the same requested quality constraints. It does not
supersede the earlier incomplete full-shortlist experiment, prove independent
physical accuracy or generalization, establish construction savings, or close
hosted acceptance, hardware, licensing or release requirements.
