# Expanded RC training observation: complete, no learned speedup

The [frozen four-training-case protocol](rc-training-coverage-expansion-20260910.md)
completes all **20 paths / 4,840 target solves** at numerical source
`bdfa9a0262cf6fb74d27a7914744487178c5f150`. Training now contains **964 paired samples** from four
authored cases, followed by two previously observed development evaluation cases.
All 14 recorded full-history comparisons, including reference comparisons, pass
at unchanged absolute `1e-10` and relative `1e-8` tolerances with zero mismatches.
No failed attempt, unknown work, numerical restart or automatic repetition occurs.

This is one observation. The new geometries and load transformations broaden an
authored training project; they do not establish an independent corpus or a new
blind evaluation. Public experimental intakes remain outside this training run.
The learner, preprocessing, ridge, OOD margin and retained arithmetic are unchanged.

## Actual evaluation

| Case | Arm | Whole path seconds | Newton iterations / linear solves |
| --- | --- | ---: | ---: |
| validation | reference | 92.950288 | 1,270 |
| validation | secant | 68.867855 | 912 |
| validation | proposal | 75.130137 | 1,034 |
| validation | fresh-reference | 92.873842 | 1,270 |
| holdout | reference | 72.381742 | 1,056 |
| holdout | secant | 58.694106 | 790 |
| holdout | proposal | 72.830513 | 1,056 |
| holdout | fresh-reference | 72.513975 | 1,056 |

Validation makes 241 learned proposals and one reference abstention. Its learned
path takes **9.09% longer than secant** in this observation, a signed
secant-minus-policy difference of **-6.262282 s**. It uses 1,034 Newton iterations
versus secant's 912. The preceding two-training-case repetitions used 1,026 in the
learned arm; the new fit therefore does not reduce that deterministic work count.
Cross-study wall times are not a controlled speedup comparison.

The OOD case still abstains on all 242 targets. Its policy path measures reference
fallback and associated policy overhead, taking **14.136407 s longer than secant**;
it provides no accepted learned OOD generalization evidence. Doubling training
samples has not made this OOD case eligible. No standard deviation or repeated
performance conclusion is available for this single expanded observation.

## Original-record verification

A separate process audits all **4,840 original steps**, **964 source-bound training
pairs** and **484 policy decisions**. It verifies accepted-parent chains, report
and path hashes, original label/high-low values, train-only preprocessing and
fit normal equations, fixed comparison results and all work counters. All **433
frozen source files** match retained hashes and their original Git blobs.
Reference/fresh-reference response histories and terminal checkpoints are byte
identical; all **20 native terminal reopens** are exact. Different seed arms retain
their own native states and are compared with the declared physical tolerances.

The independent arithmetic implementation performs 4,840 assembly replays,
29,040 section replays and 406,560 100-digit material stress checks against
original fiber inputs. Material states and branches match. This is local
arithmetic verification of the same model laws, not external experimental or
independent solver validation. The audit performs no Newton solve or fit; it
compiles six models and records all material/arithmetic replay costs.

## Complete measured costs

Generation: **2,904 core calls / 13,815 Newton iterations and linear solves**.
Evaluation: **1,936 core calls / 8,444 Newton iterations and linear solves**.
Total: **4,840 / 22,259**, with no unknown work. The one fit costs
**0.013931297 s** and is charged in addition to label generation.

| Phase | Path seconds | Nested core | Nested proposal | Nested recovery |
| --- | ---: | ---: | ---: | ---: |
| generation | 1045.632469 | 850.040394 | 3.445238 | 149.179041 |
| evaluation | 606.242457 | 479.395611 | 2.762375 | 96.270872 |

Core, proposal and recovery costs are inside path costs and must not be added
again. The numerical parent takes **1684.593196 s**;
the separate audit parent takes **200.374181 s**.
Their sequential sum is **1884.967377 s**.
That sum excludes preparation, coordinator work, final cost aggregation, sealing
and publication; it is not total project cost. Original-path cost aggregation
takes 5.075205 s internally and adds no
Newton, fit, material or model-compilation calls. Shared-host source intake,
inspection and publication activity is explicitly recorded, so exclusive-host
or deployed-latency claims are unsupported.

## Preserved evidence and next work

The terminal worker/driver/audit PIDs are absent before sealing. All
**29,565 files / 1,647,755,140 bytes** are inventoried and
reread exactly at `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-training-expansion.vdyyju94`.
Inventory SHA-256: `0526defa221f9106038fb35c87d3bc32daa9bcabefb6cd7269bd12a92217e6e4`.
The [machine summary](rc-training-expansion-completed-20260910.summary.json)
retains the original audit, per-path costs, negative paired differences and seal.
Historical studies and startup observations remain unchanged.

This result completes the declared expanded pilot and its audit. It does not
admit a faster learner or automatic repetitions. Further learner changes must
be selected using training-only evidence and tested against the strongest
deterministic baseline with complete generation/inference/recovery costs.
Independent campaign coverage and unseen evaluation remain required. The full
M1-M5/P1-P3/R1-R2 roadmap, public-data reconstruction, external verification,
licensing, hardware and owner/administrator dependencies remain open.
