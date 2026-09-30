# Enclosing process costs for original RC strategy pairs — 2026-09-13

Source `e7afc97176e431cb5a4f7058af1bd65341ffb7e8` adds `compare_rc_control_process_costs(pairs, processes)` in
`structural_analysis.benchmark.rc_control_process_costs`. It reuses the existing
standalone strategy accounting checks and replaces each nested CLI interval with
its enclosing process interval. The two intervals are never added together.

## Contract

Exactly one process observation is required for each verified report/runtime
identity. Its fields are `report_hash`, `runtime_digest`, `wall_ns`, `return_code`
and `scope`. The scope must be
`subprocess_launch_through_exit_including_startup_and_stdout`; completion requires
an integer zero exit code and a nonnegative safe-integer wall time at least as large
as the bound CLI interval. Duplicate/foreign identities, different runtime digests,
missing or extra observations, invalid fields, failures and overflowing totals
reject the comparison. Hash binding is not clock attestation.

Historical training remains deduplicated by report identity. Pairs without
comparable verified selections retain their costs and denominator but receive no
ratio. The outside-CLI difference is reported separately; it includes more than
startup and must not be labeled startup alone. Transport/review, separate audits
and campaign preparation remain excluded. The output is a sum of intervals, not
campaign elapsed time or independent physical verification.

## Verification and original records

13 new controlled-clock tests plus 17 existing strategy-cost and 16 workflow tests
passed: **46 total**. Ruff, focused mypy and diff checks passed. The independent
development CI list now contains 30 modules, including this test. An initial
workflow test correctly caught the stale expected count of 29; both the explicit
module requirement and count were updated. Full-suite gates were not changed.

The observation driver verified the original standalone packet inventory SHA-256
`9d99cdce0f6115905c729696b742af59b004412fce7a29de750cc7b0920b95aa`, then checked
26 input files (protocol, outcomes, and eight report/plan/runtime triplets).
Recorded slot order, strategy and budget were checked before constructing process
observations. No new numerical solve, fit, physical replay or timing experiment was
performed. This uses the earlier eight executions; it is not another independent
sample. Reconstructed process observations retain their source byte references.

| Scope | Price processes (s) | Learned processes (s) | Historical training once (s) | Learned + training / price |
| --- | ---: | ---: | ---: | ---: |
| All four pairs | 30.506515408 | 30.199308686 | 2.761753795 | Unavailable |
| Budget 11, both recorded orders | 22.010361421 | 22.026184226 | 2.761753795 | 1.126194047742893 |

The second row is a predeclared budget stratum of the first; do not sum them.
Two all-pair selections are incomparable. In the comparable stratum, learned
processes plus historical training cost about 12.6% more than price processes.
The earlier CLI-only inclusive ratio was about 1.14495; the changed denominator
and enclosing intervals explain the different ratio, not a new acceleration result.

The separately observed HTTP cohort review included both strategies and was run
later. Charging it solely to one strategy, or adding overlapping server/browser
intervals, would not reconstruct a defensible full campaign. Those costs remain
explicitly unassigned until matched end-to-end measurements exist.

## Records and remaining scope

Packet `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-process-costs-ujthvfwa` contains 7 files / 30,359 bytes, with sibling
inventory SHA-256 `04fedf2caaf4ea494e4aef479dc955a278cf2464af4d6074f5efb6eaad4cde39`. It preserves the exact source delta,
observation driver, original-input bindings, computed costs and test logs, including
the stale-count failure. Existing packets remain unchanged.

The new API is accounting infrastructure and a measured negative result on the
same known family. Portable cohort/Workbench process-cost display is not yet wired
to this additional report. Full campaign measurement, unseen geometry/history
cases, hosted CI and independent physics remain open, with existing licensing,
owner/administrator and hardware dependencies retained.
