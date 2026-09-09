# Bounded retained-coordinate terminal refinement

The previous full observation passes one of two fixed comparisons, with three
base-case axial/reaction differences remaining. An original-parent local trial
supports one additional retained-coordinate correction. This implementation adds
explicit benchmark-only `terminal_refinement_limit=2`; the validated problem can
select one through four attempts, with one preserving the previous default wire
contract. Additional attempts require enabled twofold terminal polishing and the
existing rational/native twofold frame profile. The problem contract and benchmark
identity bind any nondefault limit.

Each attempt adds the selected high coordinate, its retained low component and the
original Newton correction in rational arithmetic, then rounds to a canonical
pair of binary64 values. This three-term sum can require more than two components;
the twofold projection is explicit, not an arbitrary-precision coordinate claim.
Every candidate uses the same original native material parent and the original
strict residual improvement and residual/increment gates. A rejected later attempt
preserves the earlier accepted pair. The original Newton iteration budget also
bounds refinement. Ordinary iterations and line search are unchanged.

The optional refinement record retains every attempted/skipped candidate, its
original and proposed pair, residuals, increment and numerical errors. Selected
summary fields identify the last accepted candidate; separate stop reason and
summed assembly/linear/exception counts include subsequent rejected work. Each
accepted candidate enters convergence history, and final assembly, commit and
original transition recovery consume the selected pair. No material state is
committed between attempts.

Validation covers two sub-ulp corrections with the same high coordinate, later
residual/increment/assembly failure after an accepted correction, complete work
counts, original iteration limit, invalid options, profile-bound native restart
in a fresh interpreter, failure rollback, cyclic original transition recovery and
compensation tamper rejection. Two complete 242-target geometries must still pass
the unchanged absolute `1e-10` / relative `1e-8` comparisons before repeat admission.
All full costs and negative results will remain visible. This implementation alone
does not establish full comparison acceptance, speedup or roadmap closure.

Focused refinement tests pass 21 in 13.01 s. The related original/sparse Newton,
polishing, native control/recovery, rational assembly and quality-contract
neighborhood passes 208 in 52.46 s. Ruff and diff checks pass.

## Complete development observations

Frozen numerical source `93e589f1ba121f41afa0879f96f4c1c72f5190c7` contains 431 Git-verified
source/script/test files. Eight preceding modes reproduce 72
step pairs and 24 history/checkpoint pairs
byte-exactly in 16 fresh workers. Their separate work is
144 core calls and
356 Newton iterations/linear solves.

Both full 242-target geometries pass the unchanged fixed comparison. All six
paths complete, with 1,452 core calls, 7,240
accepted-history Newton iterations and 7,240 actual linear solves.
Included polishing work is 2,898 attempted corrections,
2,325 accepted corrections,
2,898 trial assemblies and 2,325
linear solves. Rejected work remains charged. Whole observation parent time,
including worker startup/output, is 548.422144 s.

| Geometry | Reference / secant / fresh-reference seconds | Full fixed comparison |
| --- | --- | --- |
| base | 101.330693 / 72.548357 / 100.730442 | pass; zero mismatches |
| long | 96.095010 / 70.349865 / 95.823964 | pass; zero mismatches |

Full comparison passes increase from 1/2 to 2/2, and the remaining three base
axial/reaction mismatches disappear. Every original equilibrium/control and
residual/increment gate, native parent chain, work record and step/history binding
passes. Both fresh references reproduce histories and native bytes exactly, and
all six terminal native checkpoints reopen exactly.

The audit checks 2,898 candidate pairs
against canonical twofold projection of their three-term rational coordinate sum,
and 2,325 accepted attempts against selected
convergence history. Every attempt starts from its recorded original history row;
subsequent rejected attempts cannot replace the last accepted pair. There are
20,286 projected coordinate components,
2,234 with nonzero
projection error; maximum absolute error is
3.009265538105056e-36 in the adapter's augmented coordinate
units. This two-component rounding is retained explicitly, not claimed exact.

Independent arithmetic reconstruction checks 1,452 assemblies, 2,904 members and
8,712 sections without material integrations or Newton solves. Its elapsed time
is 30.216095 s. The separate material
check verifies 121,968 exact fiber inputs and 100-digit stresses, and replays
121,968 original base-law integrations. All original state updates and branch
choices match. Complete audit parent time is 58.549593 s,
including arithmetic reconstruction; two model compilations, no Newton solves
or commits. These audit costs are separate from the six full paths.

The complete development bundle is sealed at `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-terminal-refinement.ufizghqu`:
**10,168 files / 534,888,502 bytes**, all reread/hash-checked;
inventory SHA-256 `b3a7a20e71ee4332bd0391923404199b8490999be8d1f92e265436f675d8ad05`. All development and audit processes
were terminal before sealing. Prior observations are unchanged.

These passes admit the declared three fresh repetitions per geometry. Repetitions
run serially in a separate output root using the same frozen source, original
inputs, full costs and fixed comparisons, with the declared alternating arm order.
Their measurements and per-repeat audits must finish before repeated performance
acceptance. The [machine summary](rc-terminal-refinement-20260909.summary.json)
records this development observation only. No independent physical validation,
learned-model generalization, hosted/full-suite acceptance or roadmap closure is
implied. Public admission, independent corpus, licensing/hardware/owner and R1/R2
requirements remain open.
