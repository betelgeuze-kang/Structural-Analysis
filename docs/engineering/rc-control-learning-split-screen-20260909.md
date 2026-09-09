# Conservative geometry and control-history split screens

The cyclic learning preflight now blocks additional ways to reuse a development
case across train/validation/holdout splits. This changes data admission before
output creation and label production, not the solver or physical tolerances.

Geometry groups compare sorted node-pair distances normalized by their largest
distance, together with node/member counts, sorted connectivity degrees and the
restraint count. Moving, rotating, reflecting, uniformly scaling or renaming the
same shape cannot manufacture a new held-out geometry in the tested cases.
The normalized comparison uses `rtol=1e-10`, `atol=1e-12` for this conservative
split screen only. Homometric shapes or different graphs with the same coarse
signature may be rejected together. The screen is deliberately conservative and
is neither a complete geometric classification nor physical equivalence proof.

Control-history groups retain ordered turning points and the final target while
ignoring monotone resampling. Normalization by the first turning point groups
amplitude/sign aliases. Complete-prefix reuse also remains in one split, so a
truncated or more finely divided copy cannot manufacture held-out loading history.
Original full-sample, declared project/family/history and entity-invariant model
checks remain in place. No group label authenticates independent project or
family provenance; a genuinely independent corpus still requires external evidence.

The new screen is called inside `run_rc_control_learning_study` preflight, before
creating the output directory or calling its numerical collection. Its per-case
geometry/history record is retained in the plan. The original frozen experiment
at `889e78c2b22e1d6f8d6633993834fac83fc8ac44` continues from its isolated source
copy; this preflight follow-up does not alter its source, policy, trajectories or
results. All four original model/request inputs also pass the stronger current
screen in a separate no-solve check.

Validation: 16 initial shape tests pass. After integration, 32 split, case, failure-
roster and CI-registration checks pass with two numerical learning tests explicitly
deselected while the long numerical observation runs. The tested outer study
boundary rejects transformed/resampled duplicates before creating output. A
previous OOD test fixture at 6.0/5.0 m was a proportional copy of its 3.0/2.5 m
training geometry; it is now 6.0/4.7 m, matching the already predeclared experiment
holdout. This was a test fixture correction, not a changed running experiment.
Ruff and diff checks pass. No complete new-head numeric or hosted pass is inferred
from these no-solve checks; the earlier 198-test result remains bound to its source.
