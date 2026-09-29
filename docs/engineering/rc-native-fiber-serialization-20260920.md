# Native scalar serialization in repeated contract validation

Retained pooled-path profiling identifies recursive fiber serialization inside
contract validation as avoidable work. The change reads the four native scalar
fields directly for exact `StatefulSectionFiber` instances. It does not cache
objects, contract hashes, checkpoints, or validation results. Every call still
observes current content. Subclasses and non-native field values retain the
existing recursive `asdict` path, including nested-data detachment.

All checkpoint validation, geometry checks, state/hash checks, native material
fields and snapshot decoding remain in place. No arithmetic, solver tolerance,
learning feature, or acceptance criterion changes.

A retained D-amp100 target-6 parent from fold 30 is checked against the sealed
90-fold packet inventory. The original checkpoint loader accepts it and all
1,231 snapshot comparisons match the original stored JSON bytes. Six alternating
legacy/direct measurement pairs each run 100 captures per arm. Direct/legacy
ratios range from **0.8667 to 0.8743**, approximately 12.6–13.3% less capture time.
The raw measurements, source patch and reproduction script are preserved in the
[summary's packet](rc-native-fiber-serialization-20260920.summary.json).

These measurements use one retained parent on the current workstation. They
measure capture, not complete paths or independent projects; the profiler's
instrumented times are not used as the performance comparison. No solver call
or fit occurs in that diagnostic. Secant remains the selected strategy.

Focused verification: 50 section/timing/binding tests and 115 frame/control-path/
constant-load tests pass. Actual learning and split regression checks pass 68
tests in 117.23 seconds (233 focused tests in total); lint and whitespace checks
pass. The new tests retain
fresh-content behavior after forced field replacement and recursive detachment
for extended fibers. Complete learned-path cost selection still needs its own
measurement on the new frozen source before claiming a full-path benefit.
