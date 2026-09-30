# Frozen selected material policy: runtime and original-record audit

The [training-only nested selection](rc-nested-selection-20260910.md) selects
SVD ridge 10,000 from the original four training cases. This observation executes
that frozen material-feature policy using source
`6ea17e2fe1d3c60c4270d8e3d4f541a3488dcb4b`. It performs **no fitting or new training-label
generation**. The original authored validation and holdout models and all 242
targets per case are copied with their sealed hashes. These are reused
development cases, not newly blind data or independent experimental campaigns.

The source snapshot, input records and protocol are retained before launch.
Each case runs reference, secant, proposal and a fresh reference in that order.
The existing retained-twofold/refinement arithmetic, terminal polishing and
fixed `1e-10` absolute / `1e-8` relative history comparisons are unchanged.
Material-state feature capture is charged only to the proposal path. The policy
retains its existing range guard and abstention-to-reference behavior; no secant
fallback is silently substituted for a learned proposal. Rejected numerical
seeds retain the existing recorded reference retry mechanism.

## Results

All **eight paths and 1,936 target calls complete**. All six comparisons against
fresh reference pass over the full physical response histories, with exact
reference/fresh-reference history and terminal-checkpoint bytes. The policy
proposes at 241 validation targets after its initial-prefix abstention. All
242 holdout targets abstain to reference. The stored policy bytes are unchanged.

| Development case | Path | Whole-path seconds | Newton iterations / linear solves |
| --- | --- | ---: | ---: |
| validation | reference | 92.810516 | 1270 |
| validation | secant | 68.647688 | 912 |
| validation | proposal | 77.643409 | 1025 |
| validation | fresh-reference | 93.220616 | 1270 |
| holdout | reference | 72.831802 | 1056 |
| holdout | secant | 58.571642 | 790 |
| holdout | proposal | 74.316764 | 1056 |
| holdout | fresh-reference | 72.554436 | 1056 |

Validation proposal time is **13.10% greater than secant**, with 1,025
versus 912 Newton iterations. Holdout proposal time is **26.88% greater
than secant**: it executes the reference iteration count and incurs the material
input and policy-check overhead even though it abstains. These are single
fixed-order, shared-host observations; they do not measure timing dispersion or
an exclusive-hardware effect. They supply no learned net-saving claim and the
candidate is not promoted.

In the validation proposal path, material-state capture takes
1.287785 s,
proposal construction/checks take
1.419553 s,
numerical calls take
59.198867 s,
and original-transition recovery takes
12.172377 s.
All are already included in whole-path time. Remaining path time includes
context preparation, bookkeeping and artifact writes. Final path-file writes,
comparisons and study setup are charged in their broader enclosing intervals.

The audit also compares each stored proposed seed and a reconstructed secant
seed against the accepted solution from that proposal path's same parent.
Using the frozen training target scales and omitting the controlled coordinate,
the summed learned/secant MSE ratio is **0.928619469** over 241 proposed
rows. This diagnostic uses no fitted evaluation preprocessing. It is not a
physical-error metric or the nested-selection score. Direct runtime results
remain authoritative for the optimization objective.

## Costs and original-record verification

The original 964 labels required **2,904 generation core calls and 13,815
Newton/linear counts**, with 1045.632469 s
across the original generation paths. That path sum excludes outer collection
overhead. The original whole-study interval was
1682.662862 s and also contains its old fit and
old evaluation; it must not be added again as if entirely new training work.
Material-feature derivation took 33.715374 s.
The new selection's 114 fits ran within an 11.131849 s worker interval and
11.340961 s parent interval. Earlier feature/model investigations remain in
their original sealed packets. No training cost is waived or amortized here,
and no positive break-even count follows from a slower online path.

The current runtime worker takes 623.810168 s,
CPU 623.600406 s and peak RSS
265436 KiB. Parent elapsed time is
623.985510 s; source/input preparation precedes
that interval. Nested timing fields are not additive across scopes.

The separate audit verifies the frozen source and original input bytes,
reconstructs all 484 policy decisions and all 484 committed material input
snapshots, checks every step reservation/outcome and parent chain, reconstructs
Newton and polishing counters, and reopens all eight terminal native states.
It reassembles all 1,936 original accepted coordinate states and reproduces
every stored response exactly. This same-solver response replay adds
162624 material integrations and
no Newton solve or fit. A separate rational-assembly and 100-digit stress audit
checks the original retained coordinates and native material branches; its
counts and costs are retained separately in the machine summary. These are
algebraic and original-record checks, not independent physical experiments.

The first audit stopped before its first assembly replay because its generic
hash checker applied report-byte hashing to a canonically normalized step.
The corrected checker uses the step contract's canonical hash. That failed
auditor and log are retained; its duration is unavailable. No numerical record
was changed or numerical path rerun. The completed second audit takes
280.180377 s internally, CPU 278.885351 s and peak RSS
466088 KiB; its enclosing parent interval is retained separately.
Total investigative wall time including the failed audit is therefore not
claimed as fully known. The runtime cost records themselves remain complete.

The cost-scope source change passed 33 focused tests in 83.90 s, Ruff,
two-source mypy and diff checks. The test log is retained in this packet.
The earlier nested selection passed 40 tests as described in its own record;
these overlapping selections are not added as distinct test counts.

After original and audit processes terminate, the packet at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-selected-runtime-d2pyuff9`
is sealed with **12126 files / 665923163 bytes** and
inventory SHA-256 `ba2e66da49ccd2001a7673cbdb467caa76333d2c128fb46486b0fd4a9b22a126`. Every file is reread exactly.
The [machine summary](rc-selected-runtime-20260910.summary.json) retains all
case-level work, cost components, comparisons, audit counts and source identities.

## Hosted status and next work

The preceding published head `5f3ef972eb27344c37c77fdcc467621482a48e91` has
failed [CI](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34411111944),
[Repository Python Tests](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34411111644)
and [Legacy Evidence CI](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34411111674)
materialization jobs. Original representative logs from all three name
`external_code_to_code_product_replay_not_passed` and
`external_code_to_code_technical_receipt_not_ready`. Issue-state offline checking
passes, while live-exact-main is skipped. These are preceding-head observations,
not hosted closure for the new source or owner acceptance.

Regularization selection and honest material-feature costs are implemented,
but the M3 measured-net-savings requirement remains unmet. The next useful
learning work needs independently diverse cases and an objective connected to
actual iteration/recovery cost; repeating this unsuccessful fixed candidate
does not establish benefit. Public experiment/model correspondence, licensing,
broader independent solver verification, M4 integration and the complete
roadmap remain open. No release, design approval or promotion follows.
