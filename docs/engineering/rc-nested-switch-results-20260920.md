# Nested development labels and fixed pre-capture gates

The declared nested label campaign completed on frozen source `2b356511f178b68238a0cd0a5037f2d1f8535a04`. All **1,980** same-parent comparisons pass. The 660 policy/parent pairs yield **32 positive, 628 negative and zero unverified labels** under the original requirement: three actual proposals, three passing comparisons and at least 1% arm-time benefit in every repetition. There are 921 actual proposal decisions across repetitions; remaining calls abstain. Eighty-five pairs have a mean time ratio below one, which is a different, weaker criterion than the declared label rule.

The campaign performs 7,920 core calls and 43,023 Newton iterations/linear solves. Driver time before outcome write is 2760.435718147 s; outer execution is 2761.841455506 s. Read-only report audit is 7.904595480 s. These are separate scopes; the outer interval contains the driver interval. Historical label generation and ten seed fits remain separately recorded. No reserved evaluation, new seed fit or complete-path speedup claim is introduced.

All 68,516 packet files (2,970,935,459 bytes) passed hash/length verification. Packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-nested-labels-xqm1porr`; inventory SHA-256 `35fd7ed0e4552eb1a093bf1394e8bdcf5fbe694464761085c194a8f8ee88b4fb`.

## Five fitted development gates

The [fixed gate specification](rc-switch-gate-protocol-20260920.md) uses ridge 1.0 and threshold 0.75, without threshold search. Each gate uses 132 verified labels excluding its outer group. Positive/negative counts by outer group are 5/127, 6/126, 7/125, 6/126 and 8/124. Unverified rows are excluded from fitting but retained in the assembly accounting. Material state, step identity and outcomes are excluded from inference features.

The first fit attempt at `1700701130bb9dfc847292ba8699a913bb18f74a` failed during policy construction: a repeated decimal constant acquired a rounding-induced mean outside its identical min/max bounds. No gate file was completed. Preserve this failed fit attempt and its **2.009715670 s** outer cost. Its packet is `structural-switch-gate-fits-jjamghkf`, inventory `c05110243a7a4907c876605294cc516ad4beb63d633aaf2fe47766901070452e`. Completed numerical labels were not rerun.

Source `7bdf126366fbda24ad7f3455e583275641561134` detects exactly constant columns from equal bounds, retaining the original constant mean and unit scale. Focused tests pass **61 in 5.68 s**, including the decimal-constant regression, known two-row ridge solution, excluded-group checks, unknown-label handling, report-order invariance, strict JSON and immutable policy payloads. Ruff and whitespace checks pass.

Five corrected fits complete, with combined measured fit time **0.028244864 s**, driver time **0.184041752 s** and outer process time **2.054198339 s**. These times are nested, not additive. All 1,200 packet files (22,806,554 bytes) verify. Packet: `structural-switch-gate-fits-fixed-ae1_qfvj`; inventory `05164ea961023ccaf19e1f6ec0bd7f6d1a9a6f3ed8d948e21d6ec420cca192e2`.

A separate read-only audit reconstructs every training assembly from the pinned label audit and nested plan, verifies normalization and original sample hashes, and checks ridge normal-equation residuals without refitting. All five assemblies match; each has 77 exactly constant columns. Maximum residual is 1.2376905056399323e-13. Audit time is 0.189247519 s, with zero fits/solves. Audit packet: `structural-switch-gate-fit-audit-xrrz1ri3`; inventory `608822f2d0e9d14e174966b0a6b72a6823fe244560308a324c16e579c49fee8a`. All packet names in this section are under the same mounted root as the label packet.

## What remains unproven

These are development labels and fitted gates, not full-path acceleration or independent physical evidence. Full nonlinear gate execution must use its own evolving accepted history, charge guard/capture/inference/solver/recovery costs and retain fresh reference verification. The seed policy changes from the two-group-excluded label fit to a one-group-excluded outer execution fit; this distribution shift remains explicit. Do not tune the fixed gate after seeing its outer results and call that independent evaluation.

All five roadmap objectives remain open. The [hosted checks](hosted-2b356-terminal-20260920.md) qualify their exact source only; later gate source still requires its own hosted checks. External comparison readiness, independent physics, licensing, operator/hardware and signature dependencies remain unchanged.
