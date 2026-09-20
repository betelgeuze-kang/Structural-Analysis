# Retained arithmetic with failed-target recovery: fixed comparison

Freeze source before numerical execution. Use the complete retained-twofold
refinement profile with explicit terminal polishing in every arm; preserve all
native and history tolerances. Four L-frame cases are fixed: short (2 m, 1.5 m)
with amplitudes 2, 20 and 40 mm, and long (3 m, 2.5 m) with amplitude 40 mm.
Every request uses N3 UY targets `(-A/2, -A, A/2)` and constant N3 FY = -25 kN.

Compare upfront reversal continuation with recovery only after a known,
rollback-safe failure at any requested target. The latter permits recovery at a
first target; the former does not. This scope difference is intentional and must
remain visible when completion differs. Neither mode repairs a failed preload or
adopts intermediate material-history checkpoints. The native sixteen-stage
search budget is unchanged for each recovery attempt.

Two repetitions reverse mode and arm order, for sixteen comparisons / 64 paths.
Every comparison includes reference, secant, proposal and fresh reference. Retain
source, inputs, driver, original native/trial artifacts, failed attempts and all
known/unknown work. Compare complete repeated histories/checkpoints; count all
ordinary and additional native calls and Newton iterations. Incomplete prefixes
must not qualify as repeated complete histories.

Only compute failed-target/upfront time ratios when both proposal paths complete,
match within the fixed full-history tolerance and pass their fresh-reference
gates in both repetitions. A failed reference or unknown work leaves the ratio
null. Also report same-profile proposal/secant ratios with the same qualification.
Timings include proposal and artifact costs but exclude import/compilation and the
full Workbench flow. This is not AI training, external physics validation or a
policy-promotion experiment. The earlier binary64 and upfront retained failures
and costs remain part of the evidence.
