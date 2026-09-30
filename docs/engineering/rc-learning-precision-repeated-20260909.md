# Three fresh retained-arithmetic learning repetitions

All three predeclared fresh generation/fit/evaluation processes and their separate
original-record audits have exited zero. Each completes the same 14 full paths
over four cases with 242 targets each at frozen numerical source
`bdfa9a0262cf6fb74d27a7914744487178c5f150`. All fixed full-history comparisons pass with zero
mismatches. The source, cases, conservative splits, ridge, OOD margin and
`retained-twofold-refinement.v1` recipe are unchanged from the sealed pilot.

The actual aggregate verifier checks **10,164 original step pairs and 42 complete
history/checkpoint pairs** against that pilot, by matching the corresponding arm
across repetitions. Every fresh train-sample and fitted-policy byte matches.
This is not byte equality between different seed arms: their comparisons use the
unchanged full physical-field tolerances and retain their distinct native states.
Original proposal/prefix/work records and report/path hashes are bound throughout.

## Measured evaluation results

Each validation repetition makes **241 learned proposals and one abstention**.
Each OOD holdout abstains at **all 242 targets**, so its policy path measures
reference fallback, not learned OOD generalization. Training is regenerated and
refitted separately in every process; the 482 samples per fit are repeated
observations of the same declared training cases, not additional unique cases.

Whole path elapsed times, in seconds:

| Case | Arm | Median | Sample standard deviation | Range |
| --- | --- | ---: | ---: | ---: |
| validation | reference | 93.507904 | 0.317637 | 93.168252–93.803006 |
| validation | secant | 68.656924 | 0.399438 | 68.652076–69.346335 |
| validation | proposal | 75.783287 | 0.250447 | 75.463309–75.957036 |
| validation | fresh-reference | 93.214995 | 0.225078 | 92.998824–93.448865 |
| holdout | reference | 72.962154 | 0.286291 | 72.718528–73.289086 |
| holdout | secant | 59.011000 | 0.118658 | 58.881979–59.118984 |
| holdout | proposal | 72.807288 | 0.179016 | 72.689124–73.040897 |
| holdout | fresh-reference | 72.905299 | 0.070521 | 72.882431–73.014395 |

Signed paired secant-minus-policy times retain losing runs:

- validation: secant minus policy seconds = -7.126363, -6.116974, -7.304960.
- holdout: secant minus policy seconds = -13.796288, -13.570140, -14.158918.

Validation uses 1,026 Newton iterations/linear solves in the learned path versus
912 for secant and 1,270 for reference in each repetition. Holdout uses 1,056 in
the policy/reference fallback versus 790 for secant. These results preserve the
negative comparison with the deterministic baseline. No net learned acceleration
over secant, amortized training benefit, external generalization or physical
qualification is claimed.

## Complete costs and distinct timing scopes

Generation costs **4,356 core calls / 20,637
Newton iterations and linear solves**. Evaluation costs **5,808
core calls / 25,308 Newton iterations and linear solves**.
Total: **10,164 core calls / 45,945
Newton iterations and linear solves**, with no unknown work. All three fits are
charged: 0.009048, 0.008641, 0.009048 s, total **0.026737 s**.

| Phase | All path wall seconds | Nested core | Nested proposal | Nested recovery |
| --- | ---: | ---: | ---: | ---: |
| generation | 1544.331720 | 1254.411014 | 5.141583 | 221.580287 |
| evaluation | 1827.321979 | 1443.455472 | 8.257714 | 291.350071 |

The core column includes every recorded numerical attempt, and proposal includes
feature/initial-value preparation. These scopes are inside path time; they must
not be added to path or worker time. Whole worker time also retains preflight,
generation, fitting, validation, verification, recovery and artifact I/O.

| Repetition | Numerical worker parent seconds | Separate audit parent seconds |
| --- | ---: | ---: |
| r1 | 1145.182608 | 144.819135 |
| r2 | 1147.502604 | 142.260383 |
| r3 | 1148.041193 | 141.981993 |

Numerical parents total **3440.726405 s**;
audit parents total **429.061511 s**; complete driver
elapsed time is **3869.790118 s**. The three per-run audits
include original arithmetic/material re-evaluations and native reopens, as recorded
in their own receipts; they are not additional Newton solves or fits. The final
aggregate verifier takes **34.708528 s** internally and
**34.775241 s** parent time, with zero
Newton/fit/material/compile/commit calls. Its nine focused tests pass in 0.26 s;
invalid elapsed values cannot disappear into a positive total, and rejected-attempt
costs remain included. Ruff and formatting checks pass.

The host also ran lightweight coordinator source fetches, PDF rendering and
intake/check/report work. These activities and their recorded scopes are retained
in the bundle. The measurements do not establish exclusive-host timing, deployed
latency or independent hardware performance.

## Sealed evidence and remaining roadmap

After all worker/audit/driver PIDs disappeared and the original aggregation passed,
the bundle was sealed and every file reread exactly:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-learning-precision.ekj7dcak-repeated`.
It contains **62,476 files / 3,447,848,173 bytes**, inventory
SHA-256 `24ec6f76eaa1241c53ee437856e49d67097a7a9887f7652e3624302353a55e8a`. Inventory and seal live beside the root.
[Machine results, signed samples and complete costs](rc-learning-precision-repeated-20260909.summary.json).

This completes the bounded repeated observation for these four cases. Broader
project/geometry/load-history families, an independently verified external corpus,
M2/M4/M5 broader integration, public/sparse/material/3D qualification and R1/R2
integration remain open. Dataset/software terms, licensed blind corpus,
independent hardware/cross-code execution and owner/administrator decisions remain
attributed dependencies. No merge, release approval or full-roadmap closure follows.
