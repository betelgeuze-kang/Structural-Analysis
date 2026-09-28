# RC held-out lifecycle cost receipt audit

This optional audit extends the guarded held-out contract in
[`rc-heldout-runtime-contract-20260928.md`](rc-heldout-runtime-contract-20260928.md).
It does not launch a campaign, select a policy, run the two reserved cases, or
establish net AI benefit. Current development selection retains secant.

`audit_heldout_lifecycle_costs(plan, packet_root)` first runs the existing
original-path audit. It then reads `packet_root/lifecycle-manifest.json` and
the packet-local original files that manifest names. Every referenced file has
an exact relative path, byte length and SHA-256; duplicate paths, aliases,
symlinks and duplicate JSON keys are rejected. The manifest binds the frozen
plan, source revision and selection-result hash. Its `manifest_hash` is the
canonical JSON SHA-256 computed without that field. These integrity checks do
not authenticate a producer or external source rights.

Each `launchers` entry identifies one declared slot and an original
`rc-heldout-launcher-observation.v1` JSON file. The launcher file binds the
plan and source, slot index, original `started.json` and `outcome.json` byte
hashes, process identity, return code, and measured `wall_ns`. Its `scope` is
`subprocess_launch_through_exit_including_startup_and_stdout`, the same
enclosing-process scope used by `rc_control_process_costs.py`. A future
producer must take a **single parent** `perf_counter_ns()` interval around
subprocess launch, output capture and exit, including Python startup and the
slot's final outcome write. The auditor checks that this interval is at least
the original slot interval and that all observed process identities are
distinct. In v1, `cpu_ns` must be null: a parent
`process_time_ns()` interval does not include child process CPU, and this
contract has no audited child-resource observation. The original slot CPU
measurement remains in the slot audit.

The sum of complete launcher intervals replaces the nested slot intervals;
they are never added together. It is a **sum of process observations**, not
elapsed campaign wall time. No cross-process timestamp ordering or same-host
clock epoch is assumed. A missing launcher leaves the all-slot sum null. A
nonzero exit keeps its measured interval but fails the successful-exit flag.
Missing, raised, interrupted, unknown-work and fallback-only slots remain in
the original declared denominator.

Optional `selection_receipt` and `label_receipts` contain byte-preserved
original selection-result and learning-study JSON. The auditor recomputes
their embedded result/report hashes, checks the selected policy against the
plan, binds the label source revision, and requires each declared training
case exactly once across deferred-evaluation label receipts. It reports the
known historical label intervals plus the enclosing development selection
interval. Fits nested inside selection are **not** added again. These source
revisions and file hashes still need a separate provenance and rights review;
the code does not establish that the records came from independent projects.

The manifest's `training_cost_reuse_count` must equal the value frozen in the
plan. The current plan fixes that value to null, so break-even is unknown.
Historical launcher overhead, final writes, preparation and some report I/O
also remain unmeasured. The result therefore keeps
`actual_total_evaluation_wall_ns`, projected operational break-even and
`net_benefit_proved` unavailable, sets `unknown_evaluation_cost=true`, and
retains secant. A later source-authenticated, predeclared experiment must fill
those gaps before a lifecycle decision; neither same-engine synthetic paths
nor a favorable path ratio can promote the learned policy.

Focused checks:

```bash
PYTHONPATH=src python3 -m pytest -q tests/test_rc_control_heldout_lifecycle_costs.py tests/test_rc_control_heldout_runtime.py
python3 -m ruff check src/structural_analysis/benchmark/rc_control_heldout_lifecycle_costs.py tests/test_rc_control_heldout_lifecycle_costs.py
```
