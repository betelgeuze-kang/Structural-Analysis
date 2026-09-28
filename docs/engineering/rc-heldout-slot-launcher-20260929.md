# RC held-out slot subprocess launcher

`launch_heldout_slot(plan, cases, selection, slot_index=..., packet_root=...)`
in `structural_analysis.benchmark.rc_control_heldout_launcher` executes exactly
one explicitly supplied, predeclared slot. It uses the current Python executable
and a fixed module entrypoint, with the checkout's `src` as `PYTHONPATH`. It does
not discover cases, choose a policy, train, retry, or execute a whole campaign.
The existing runtime requires a source-bound learned development selection;
current development results that retain secant remain ineligible.

Both parent and child require the exact clean committed source. Inputs are
serialized as JSON, byte-bound in the attempt receipt, and checked again by the
child before case reconstruction. The child reads the input once, checks its
hash, and parses that exact byte string with duplicate-key and nonfinite-number
rejection (64 MiB maximum). Replacing the input path after the read cannot
change the executed document. Model checksums, typed requests, the case
roster and selected policy are checked by the existing slot runtime. Measured
workbook sources are rejected by this initial transport rather than silently
omitted. Frozen source and rights references still need independent review.

The packet lives outside the checkout. Exclusive attempt directories prohibit
replacement even when the child never started a slot. An exclusive packet lock
serializes writers. No existing output is deleted. A killed parent can leave a
lock or pending manifest; inspect these manually before recovery. There is no
automatic retry or stale-lock removal. The empty source-bound lifecycle manifest
is persisted before the first launch, so a missing parent receipt remains
visible in the declared denominator.

The parent takes exactly one `perf_counter_ns()` interval around `Popen`, stdout
and stderr capture to files, exit/wait, timeout termination and stream close.
The fixed child calls `run_heldout_slot`; a raised terminal slot exits with code
1, a completed slot with code 0. A timeout kills the child process group and
waits for exit. If the child exits between timeout and the kill signal, it is
still reaped; the timeout remains recorded without a false launch error. A keyboard interruption during the wait also kills/waits and
records the interruption. An abrupt parent termination can leave its measured
cost unknown. Child CPU is unavailable and stays null.

The interval includes interpreter/module startup, all child work, final outcome
writing and captured stdout/stderr. It excludes parent input preparation,
post-exit hashing/receipt writes, and the separate audits. Files are closed but
not fsynced; this is not a power-loss durability or external-clock attestation.

Every attempt preserves `input.json`, `stdout.bin`, `stderr.bin` and
`attempt.json` below `launch-attempts/slot-NNNN/`. The attempt binds source, plan,
slot, actual child PID, return code, timeout/launch error, exact file lengths and
SHA-256 hashes. Original `started.json` and `outcome.json` are read after exit
without reserializing them. When an original start exists, the producer also
writes the v1 launcher observation accepted by the
[existing lifecycle auditor](rc-heldout-lifecycle-cost-audit-20260929.md).

A pre-start failure has real measured cost but cannot satisfy the v1 auditor's
required original start binding. Its launcher entry is absent, its cost remains
in the attempt receipt, and its slot remains missing/unknown in the original
slot audit. `audit_heldout_launch_attempts` rechecks all original attempt bytes,
reconciles each declaration with the v1 launcher, and reports
`observed_wall_ns_absent_from_v1_launcher_sum`. The all-declared attempt sum is
null whenever a parent receipt is missing. Even if every attempt has a receipt,
failed attempts stay in the denominator and do not imply completed evaluation.

Attempt intervals replace v1 launcher intervals and nested slot intervals;
these sums must never be added together. They are sums of observations, not
elapsed campaign time. Lifecycle cost, independent provenance, physical
accuracy, break-even and net benefit remain unproved. Both audits retain secant,
unknown total evaluation cost and false lifecycle/net-benefit flags.

Validation uses synthetic development fixtures only, including a real full-path
subprocess, source rejection before start, process creation failure, raised
outcomes, interrupted slots, timeouts before/after start, changed original bytes,
repeated-attempt rejection and resealed receipt disagreement. The full-path unit
fixture explicitly bypasses the clean-source guard in its synthetic child;
the production entrypoint has no bypass option. No reserved evaluation packet is
loaded or executed by these tests.

```bash
PYTHONPATH=src python3 -m pytest -q tests/test_rc_control_heldout_launcher.py tests/test_rc_control_heldout_lifecycle_costs.py tests/test_rc_control_heldout_runtime.py
python3 -m ruff check src/structural_analysis/benchmark/rc_control_heldout_launcher.py tests/test_rc_control_heldout_launcher.py
```
