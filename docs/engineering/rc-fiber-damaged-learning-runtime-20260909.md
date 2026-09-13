# RC L-frame learning and retained material histories

Observed from numerical source `24e34255649ced519991a60904efae6621f49e3c`.
The complete study is **blocked**: all 18 paths converge and pass their own J1–J5
recovery, but three in-range learned paths fail the fixed trial-response comparison
against reference. The 4,805-check saved-artifact audit passes with no new solves,
fits, physical recovery or worker calls. Those statuses have different scopes.
This is one synthetic family, with caller-declared project/geometry/load-history
groups. It is not an independent corpus, blind external validation, design-code
acceptance or a release receipt.

## Question and fixed protocol

The earlier single-member low-load policy abstained on all attempted damaged
L-frame steps because its topology/layout context differed. The current study
fits the existing model-conditioned secant-correction v3 policy on the same
two-member L-frame context instead. The context/OOD test, constitutive laws,
guard/damping and solver tolerances remain unchanged. No production source change
is required for this declared family.

Base geometry has nodes (0,0), (2,0), (2,1.5) m, one fixed root and two serial
members with three integration points. The .6 m section depth, .05 m cover,
12 concrete layers and two groups of four .000387 m² bars stay unchanged.
Only uniform geometry scale, width and N3 FY reference load vary.

| Case | Split | Geometry scale | Width (m) | FY (kN) |
| --- | --- | ---: | ---: | ---: |
| train-small-narrow-low | train | .9 | .4 | -100 |
| train-small-wide-high | train | .9 | .5 | -150 |
| train-large-narrow-high | train | 1 | .4 | -150 |
| train-large-wide-low | train | 1 | .5 | -100 |
| validation-static-interior | validation | .95 | .45 | -125 |
| holdout-load-ood | holdout | .975 | .475 | -180 |

The exact large/narrow/high physical model is known from previous development
observations; it is explicitly a training case. All six full input files,
group assignments and the protocol were fixed before new labels. Cases do not
share physical identities across splits. Artificial group names do not establish
independent projects. The OOD holdout's static load exceeds the training range
plus the unchanged .1 margin. The interior case may still abstain due to dynamic
parent/previous-history features; that is an outcome, not grounds to widen ranges.

All cases request four proportional load steps, residual tolerance `1e-10`,
increment tolerance `1e-12` and at most 40 iterations. Ridge is `1e-6`, OOD margin
`.1`, target `secant_correction`, with three repetitions and zero warmups. The
three strategies rotate order, covering each position once. Response comparison
tolerances remain absolute `1e-10` and relative `1e-8`.

The declared successful-path denominators are six collection public requests,
24 accepted samples (16 train), 18 evaluated strategy paths and six separate
reference-episode checks. Any incomplete collection case causes the stock study
to skip fitting/evaluation. All failures are retained; no automatic retry,
case replacement, label deletion or hyperparameter/tolerance tuning is allowed.

## Source and observation boundaries

Root: `/tmp/structural-damaged-learning-observation.1c2t_yy5/`.
The 397 Python package files are frozen and hashed. The observation driver wraps
the public analyzer only during collection: each call forwards unchanged inputs
once and returns the same typed result. Six original references remain alive.
The wrapper is removed immediately when collection exits. Existing study fitting,
guards, fallback, full-history/recovery checks and resource reporting run normally.

After the stock worker persists its reports, the observer serializes each
retained public result and checkpoint and invokes the existing constitutive
inspector once. Those inspections include source validation and physical recovery;
zero additional public analysis requests does not mean zero numerical work.
Their wall/CPU and export costs are separately recorded and included in the whole
observation cost. Original source bytes are checked before/after inspection.

The stock absolute process CPU already includes observer setup/import CPU, so
those intervals are not added together. The retained results contribute to its
peak RSS. Stock and final process peaks are overlapping lifetime maxima, not
per-phase/strategy memory, and are not subtracted or compared as equal-scope
memory savings against earlier uninstrumented studies. Parent launch-to-exit
wall includes imports, study, source export, inspection and child persistence.

Preparation initially used the wrong loader import path after source/input
persistence but before any public solve or labels. The original script/log and
pre-binding protocol versions are retained. `complete_preparation.py` reads the
unchanged inputs and completed pure compilation in 1.651043104 s; the failed
preparation clock is unavailable. Neither event is a numerical retry.

## Results

All six original collection cases completed and produced 24 accepted samples:
16 train, four validation and four holdout. Only the train rows determine weights,
scales, preprocessing and feature ranges. The stored audit checks original train
membership, feature minima/maxima and every accepted-coordinate/source binding;
it does not independently refit the weights. The fixed policy is
`sha256:73def809586df6331a3d8977a216887c0f60a6d9d8145132d39b062e924baeca`.
Actual native states in all six original results retain positive tensile damage:

| Case | Accepted tensile-damage maximum |
| --- | ---: |
| train-small-narrow-low | .6894038167530325 |
| train-small-wide-high | .8739928157708069 |
| train-large-narrow-high | .9699183857765405 |
| train-large-wide-low | .610189617682575 |
| validation-static-interior | .8440122564223866 |
| holdout-load-ood | .9910352749984459 |

Every original case has four positive accepted epochs. Steel accumulated plastic
strain and compressive damage remain observed zeros. The audit independently
aggregates all native material fields, extrema and parent-change counts from the
six retained checkpoint chains and checks their companion/source bindings.
Engineering recovery and energy identities are stored assertions, not independent
physics replay. Runtime learned checkpoint/trial bytes are not part of the stock
study; the separate diagnostic below retains the affected comparison pair.

The interior validation case is in range on every learned step. All 12 learned
proposals across three repetitions become seeded attempts, with no failed-seed
rollback or baseline recovery. Learned uses 13 Newton iterations per path,
deterministic secant 14 and reference 18. Each learned path passes its own full
J1–J5 recovery. Displacement and native material-state comparisons pass the
declared elementwise tolerances, but trial-assembly response comparison fails in
all three repetitions. The report's aggregate trial-response maximum absolute
difference is `5.5246055126190186e-06`; that aggregate contains different response
and matrix fields and cannot alone identify the failed quantity or its unit.
The total fully verified denominator is therefore **15/18**, with **6/6** separate
reference-episode checks passed, and the study stays blocked.

The load-OOD holdout abstains on all 12 learned steps and executes reference
parent starts, with no learned seed or physical guard assembly. Its three learned
checkpoint chains are reported byte-exact to reference. That is expected guarded
fallback, not successful learned prediction on the high-load model.

## Inclusive runtime and additional observation cost

The table records all attempted paths, including the three failed comparisons.
The raw field is called `verified_end_to_end_wall_ns`; its name does not override
the actual comparison failure. It includes execution, authority verification and
comparison, but excludes collection/training, separate reference-episode checks
and post-study source export. Seconds show all three repetitions.

| Case | Strategy | Repetitions (s) | Median (s) | Full comparison passes |
| --- | --- | --- | ---: | ---: |
| Interior | Reference | 29.794605 / 29.586593 / 29.569821 | 29.586593 | 3/3 |
| Interior | Secant | 28.264992 / 28.404245 / 28.231519 | 28.264992 | 3/3 |
| Interior | Learned | 27.862387 / 27.869025 / 27.998777 | 27.869025 | 0/3 |
| Load OOD | Reference | 32.798513 / 32.513380 / 32.781154 | 32.781154 | 3/3 |
| Load OOD | Secant | 31.512757 / 31.625055 / 32.007930 | 31.625055 | 3/3 |
| Load OOD | Learned fallback | 32.448849 / 32.473196 / 32.524080 | 32.473196 | 3/3 |

Interior learned-minus-secant paired differences are −.402606/−.535220/−.232742 s;
their median is −.402606 s. These are timings of paths that failed the required
comparison, so both interior amortization rows correctly remain unavailable.
Holdout learned-minus-secant differences are +.936092/+.848141/+.516150 s:
the learned fallback is slower than secant in every pair. The raw holdout/reference
median difference produces a conditional 584-reuse projection, but the learned
arm supplied no prediction in that case and follows reference starts. It is not
evidence of an AI contribution or observed break-even, and it excludes the later
source-export/diagnostic cost.

| Whole stock phase | Wall (s) | Process CPU (s) |
| --- | ---: | ---: |
| Data collection and report conversion | 179.686392 | 179.679401 |
| Full training attempt and freeze checks | .036100 | .036100 |
| Frozen evaluation and report checks | 570.201008 | 570.143214 |

The internal study fields record 179.684617496 s generation, .027821654 s internal
fitting, .036096954 s entire training attempt, 570.201000679 s evaluation and
749.923600488 s study. The original amortization numerator is 179.720714450 s
generation plus entire training attempt. Feature preflight/internal fitting are
nested intervals. Evaluation includes all failed comparisons and the six separate
reference-episode checks; failed or OOD paths are not removed from costs.

Stock process CPU through study persistence is 751.636941015 s, already including
observer setup/import CPU. Post-study source export and inspection take
68.912959797 s wall / 68.762513861 s CPU, of which the six inspector calls account
for 63.389520719 s wall / 63.329535554 s CPU. Final child process CPU through final
checks is 820.436441962 s, excluding final sidecar persistence and exit.
Parent launch-to-exit wall is **820.843728181 s** and launch/wait parent CPU is
.212704636 s; parent source/artifact checks lie outside that CPU interval.
None of these nested values is added twice.

Stock and final process peak RSS are both 137,539,584 bytes (131.167969 MiB),
including retained originals. Bounded worker input reads total 17,387 bytes;
the stock study report is 1,690,363 bytes. The 18 post-study public/checkpoint/
companion files total 1,415,346 bytes. These counters are file-API scopes, not
complete physical disk traffic. Source verification, sidecars and parent writes
have no complete separate I/O byte/time counter.

## Locating the failed response comparison

The original study and its blocked result remain unchanged. After inspecting the
failure, a separate diagnostic freezes the same validation input, policy and
tolerances, then executes reference and learned single-strategy workers once each.
It adds two selected paths and one reference-episode check, with zero collection
or training calls. Both own-path workers complete and retain full comparison
snapshots: raw canonical checkpoints and trial assemblies at every accepted step.
The two process API calls take 34.879644488 s and 29.658037887 s, including their
launch/wait and artifact validation. These are additional diagnostic costs and
do not replace the failed repeated study or establish a repeated timing advantage.

The saved-pair comparator completes with zero errors and no new solver, training
or recovery calls. Both strategies reproduce their path hash, terminal checkpoint
state hash, entire authority-verification payload, selected-step hashes/sources and iteration
count from all three original repetitions. Its entire comparison payload also
equals each original repetition. This binds the diagnostic to the original
failure; the original study bytes and status remain unchanged.

Across 11,893 numeric leaves, 3,291 differ and 27 violate the unchanged elementwise
rule. There are no structural differences. All violations occur in trial
assemblies: 14 at epoch 2 and 13 at epoch 4, with 20 force/resultant occurrences,
two reactions and five residual components. Several fields serialize the same
underlying quantity: 14 occurrences repeat an exact ordered numeric pair and its
tolerance, leaving 13 such groups. These are 27 serialized comparisons, not 27
independent physical events.

The largest violating difference is `1.909118415717266e-09` kN in epoch 4
`internal_loads_global[3]` (N2 UX), also present in `residual_kn[0]`. Reference is
`9.563062458375288e-11` kN and learned is `2.004749040301019e-09` kN; the permitted
difference is `1.000000200474904e-10` kN. The difference is 19.09118033 times that
limit. Other failing near-zero force/moment components retain their own source
units; no single kN label is applied to the aggregate response.

These results do not contradict each path's convergence. The existing Newton
adapter measures the infinity norm of the scaled residual relative to the full
reference-force scale, with a minimum scale of one. Here the force scale is
125 kN, so residual tolerance `1e-10` permits a scaled residual up to `1.25e-8`
kN. N2 UX has translation scale one and no external horizontal load, so the
learned value above is both its horizontal internal force and residual. Dividing
it by 125 gives approximately `1.60379923224e-11`, below the Newton gate.
The separate cross-path rule compares raw values, with an approximately `1e-10`
kN absolute allowance near zero. Passing one criterion therefore does not imply
passing the other. This explains the observed acceptance mismatch without
establishing a solver defect or new physical validation.

In contrast, the aggregate maximum `5.5246055126190186e-06` belongs to epoch 4,
M1 section 0 `consistent_tangent[0][0]` (axial dN/dε, kN). Its permitted difference is
`.04608269398247342`, so this entry passes. Neither the largest absolute value
nor a large relative difference near zero can substitute for the actual per-leaf
acceptance decision. Displacement and material-state comparisons still pass.

The diagnostic reference and learned workers consume 34.651085462 s and
29.473847717 s process CPU through strategy persistence, respectively. Their
post-exec peak RSS values are 119,943,168 and 120,279,040 bytes. The reference
worker additionally checks a reference episode, so these are different workload
scopes. Their bounded input reads are 3,070 and 32,962 bytes; strategy reports are
1,504,040 and 1,507,439 bytes. The two API wall intervals total 64.537682375 s;
parent API CPU intervals total .085748606 s. Imports/source checks in the parent
and later saved-audit/seal wall time have no complete separate measurement.
These additional costs are retained without adding nested intervals twice.

No tolerance, trained policy, baseline or solver behavior is changed to turn this
failed study into a pass. Follow-up engineering must distinguish the scaled
single-path equilibrium criterion from the cross-path absolute force comparison,
retain a diagnostic for the actual failing fields, and evaluate any future
behavior change under a separately declared protocol. This observation alone
does not establish that either criterion should be relaxed.

## Retained audit and raw identities

`saved-audit/audit.json` records 4,805 passed checks and zero errors;
`saved-audit/summary.json` has canonical-payload hash
`sha256:4987684c628d0a52e6925c92aa4f3f08d46f73afbc0cfe15905c65316ff180a3`.
The field diagnostic is `field-diagnostic/comparison.json`, 221,840 bytes,
raw-file SHA-256 `234c1305882b698626a2394ee4072c5ded24f063851927f6364035b2af0e8165`.
Both audits read saved evidence; the earlier two diagnostic workers and six
constitutive inspections are separately charged numerical work.

The original `worker/study.json` is 1,690,363 bytes with raw-file SHA-256
`efdef3ba82601dbc574940fe5cbcc228fd3ccd571bed22094189277141b56bcc`;
`worker/resources.json` is 5,106 bytes with raw-file SHA-256
`58b6113f4a2233740b70d2a1c440fdff4e530316cb24c72af01db30c58295b0e`.
The final pre-execution `protocol.json` has raw-file SHA-256
`6c364c8f080dfa58ea8e3b052498151e4af9d47c7143c78cc5d2aaf4abda0d19`.
`source-before.json`, `execution-before.json`, `execution.json` and the observer
sidecars retain the frozen inputs, preparation, child lifecycle, scoped measured
costs and unavailable intervals, and before/after source checks.
`retained-audit-provenance.json` checks exact
copies of the external audits and launch logs. The original preparation failure
is retained alongside its successful compile-only continuation.

The completed local artifact root is sealed by `artifact-inventory.json`:
476 files totaling 15,072,154 bytes, excluding the inventory itself. The inventory
is 94,592 bytes with raw-file SHA-256
`d5b55ccf4cfb225975052da10bfba4e965f9c86d0ff19ef6f62148a5afeb9023`.
An exact-file-set scan and every byte/hash check pass. The sealed artifact draft
precedes this inventory paragraph to avoid a self-referential hash. All 397 frozen
Python package files also match the current implementation checkout; this slice
changes observation documentation only. The local seal establishes file identity,
not an externally signed source or independent numerical receipt.

## Remaining scope

Positive native damage in retained training and evaluation originals is required
to count this as damaged-history coverage. An observed zero cannot satisfy that
condition. Full solver/history parity and local timings do not establish external
physical validation or useful learned acceleration. Steel-plastic/cyclic paths,
independent project/corpus evidence, licensing, hardware/operator qualification,
hosted integration and owner/release decisions remain open.
