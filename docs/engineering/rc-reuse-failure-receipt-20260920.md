# Retain rejected benchmark cost in the reuse experiment

The yielded-prefix binary64 experiment previously left its complete benchmark
report and original steps but raised before creating a top-level study summary.
Its failure cost and unexecuted reuse comparison required a separate audit.

The reuse runner now writes `failure.json` when a returned benchmark fails
reference-repeat/work completeness or full-history validation. The receipt
records the failed benchmark's directory, comparison byte length and SHA-256,
arithmetic/preload/repetition/order, enabled reuse/timing flags, observed gates,
enclosing benchmark time, and elapsed study time from output setup through
validation. Model loading and failure-receipt serialization are excluded from
that study interval. Nested intervals must not be added.

Completed pairs and earlier completed benchmarks in the current pair remain
visible; the failed pair's time ratio is null. The runner still raises the
original validation error, does not execute subsequent planned benchmarks,
and does not create a successful `summary.json`. Existing output refusal and
solver tolerances are unchanged. This receipt covers these explicit validation
failures, not every possible process interruption, missing file or exception.

The experiment suite passed 31 tests in 32.17 seconds, including its existing
actual timed/untimed retained-arithmetic paths. After adding the original
comparison hash binding, the three targeted rejection tests were rerun.
They inject returned reports with failed repeat, incomplete work and failed
history gates; verify one invocation only, null ratio, retained original,
failure cost and no successful summary. Their timings are test observations,
not performance measurements. Ruff and diff checks pass.

No old packet was modified or retroactively given this receipt. The original
failed binary64 observation, its separate audit and the distinct successful
retained-arithmetic measurements remain separate evidence.
