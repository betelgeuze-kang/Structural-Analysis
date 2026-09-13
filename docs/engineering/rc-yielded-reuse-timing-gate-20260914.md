# Yielded-prefix timing experiment stops before a reuse comparison

Frozen source: `22977c86fde3422666a9c38da06ca036f9e29352`.
The existing reuse experiment was invoked with `--case yielded-prefix
--arithmetic binary64 --implementation native --repetitions 2
--record-assembly-timing`. Source and the authored model were extracted from
that exact commit. No model, targets, tolerances or arithmetic were altered.

The first baseline benchmark executed four 16-target paths and wrote 64
numerical step records. Its fresh reference was exact and all execution work
was reported. However, both secant and the identical secant proposal failed
their full-history comparisons to the reference. Each comparison records
46 member-end-force, 16 section-result and five support-reaction mismatches.
The wrapper therefore exited 1 after 12.160164263 seconds. No reuse-enabled
benchmark or second repetition ran; paired cost ratio is null.

One recorded witness is response-history index 2, member-end-force entry 1,
local end i FY: arm 0 N versus reference 1.1743437167116977e-10 N, above the
declared allowed difference 1.0000000117434372e-10 N. Other fields also fail.
The mixed-field maximum absolute difference is 6.810296326875687e-9; it has
no single physical unit and must not be presented as a structural error bound.
The relative maximum of 2.0 likewise does not establish physical inaccuracy
near zero. These observations justify retaining the failed comparison, not
relaxing its tolerance or claiming an independent solver ranking.

The intended successful-study auditor was not run against an incomplete
study. A separate failure audit retains the actual comparison status,
64-step count, missing reuse execution and null paired ratio. Original files,
frozen source, execution receipt and failure audit are read-only at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-yielded-reuse-timing-6q8qmjin`.
The packet has 1,262 files totaling 72,597,452 bytes. External inventory SHA-256:
`f91d32c2ae44e0338a09da1e47aebc98e90ea4d83f43d57bc41b48272fdf0c67`.

This does not attribute the mismatch to timing, prove reuse failure, or
establish learned benefit. Before comparing reuse costs on this path, the
baseline/reference numerical mismatch needs diagnosis under the existing
acceptance contract. No repeated run, tolerance change or successful-study
promotion was used to bypass the failure.

Separately, published source `9453bc210325305569442cbf7ac2fc075f8d1be0`
passes Workflow Contract CI job `103802687720`: 166 tests in 17.76 seconds.
This software check does not validate the later split repair or resolve the
numerical observation above.
