# Original warm-start training corpus has one connected project group

The read-only `audit_rc_runtime_training_groups.py` was run against the retained
original runtime-selection packet. Before constructing typed cases, it verifies
the protocol against the SHA-256 already preserved in the historical tracked
summary, then verifies all 13 referenced original plan/model/request files by
length and SHA-256. It executes no archived script, fit or numerical solve and
writes only a new audit file outside the original packet.

Protocol SHA-256:
`733d98281f3ac60958808db119845df6bc40bcd2eb432729f236d293ac3720ff`.
Original numerical source:
`664f128896dc08eeb3337264881fa2d869badc4e`.
Packet:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-runtime-selection-1blqipjy`.

All four training cases (`train-a`, `train-b`, `train-c`, `train-d`) share the
project ID `declared-development-train`, so they form **one connected group**.
Additionally, train-a/train-b share the declared load-history ID and overlap under
the conservative history/prefix screen. The other pairs are connected by project
identity; this audit does not claim all four have identical histories.
Validation and holdout inputs are checked as original bytes but do not enter the
training grouping or any fit/score. Their roles are not reassigned.

Consequently the explicit connected-group runtime mode cannot use this corpus:
excluding its one group leaves zero fitting cases. This is a data limitation,
not a reason to weaken the exclusion rule or rename projects. Prior leave-case-out
results remain honest internal tuning observations and still do not justify
promoting the learned initial guess over secant. No historical runtime or score
was recomputed or overwritten by this audit.

A next grouped cost experiment needs additional defensible training groups and a
separate untouched evaluation role. Newly authored synthetic scenarios can support
a clearly labeled synthetic development study; they do not manufacture independent
project provenance. An externally measured case needs its own license, dimensions,
materials, channels and compatible physics admission before use. Existing inspected
evaluation data cannot be relabeled as a new untouched holdout.

[Machine audit](rc-original-training-groups-20260920.summary.json) preserves exact
input references, pairwise connection reasons and the unusable-group conclusion.
The split/auditor suite passed 25 tests in 1.68 s, including rejection of a changed
protocol pin and a byte-modified original input. Ruff and diff checks passed.
The original numerical packet and its inventory remain unchanged; this audit did
not re-verify its entire multi-gigabyte execution record or independent physics.
