# Smaller fixed-parent increments pass the short/40 mm first target

The [predeclared diagnostic](rc-l-frame-adaptive-parent-protocol-20260921.md)
ran from frozen source `8e9cb4a75`, retaining the original parent, -20 mm target,
constant preload and native tolerances. Binary64 and retained arithmetic each ran
twice in reversed mode order. All four runs reached the target and committed the
additional native confirmation. Every run used eighteen trials (one failed) plus
one confirmation and one fresh preload: **80 native calls / 444 Newton iterations
and linear solves**, including all four failed trials.

At the previously failing trial eight, the increment is halved without advancing
the accepted fraction or seed. The smaller trial commits, and the following
trials reach the original target. Intermediate material checkpoints are never
adopted. The result demonstrates that a bounded step-size change can cross this
specific native convergence obstacle; higher arithmetic precision was not required
to achieve that crossing.

Within each precision, final confirmation checkpoints repeat exactly across the
two runs. Binary64 also has exact equality between the last internal trial and
its confirmation. Retained arithmetic does **not**: its confirmation changes 77
numeric checkpoint fields, with maximum absolute difference 7.105427357601002e-15
in a backstress value (MPa). Both native confirmations commit, but this is not
reported as exact equality between those two retained states. The confirmed
checkpoint is the final authority; no cross-arithmetic state equality is claimed.

The separate readback audit verifies artifact hashes/lengths, original parent
equality, absolute seed handoff, the success/failure-driven schedule, call bounds,
all work and repeated confirmed checkpoints. Its initial checker assumed binary64
parents stored `free_coordinates_m` and assumed trial/confirmation exact equality;
it was corrected to reconstruct binary64 initial coordinates through the native
adapter and explicitly retain the observed retained-state inequality. Original
numerical artifacts were not changed.

Packet:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-adaptive-parent-37z5un86`.
All 1,087 audited inventory entries were reread and hash/length checked.
`audited-inventory.json` SHA-256:
`2cf79a5ac62a6c9ffc6f89bde395331de077794865932df4e3f0112d7ceb8d59`.
[Machine-readable audit](rc-l-frame-adaptive-parent-results-20260921.summary.json).

This diagnostic covers one parent-to-target solve, not the full requested history,
physical accuracy, a learned policy or product acceleration. Full-path integration
and independent verification are separate requirements.
