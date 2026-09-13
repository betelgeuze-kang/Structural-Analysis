# Planar reference discrepancy and CI diagnostics, 2026-09-10

The two failed horizontal-reaction comparisons identified in the
[previous replay](ci-replay-diagnosis-20260909.md) arise from the small-chord
kinematic arithmetic change in `e2f6967ec84893aa83f3e56616ede3ff7f9b4f10`.
The current implementation retains its precision correction. External reference
values and original acceptance tolerances remain unchanged, so the comparisons
remain failed.

## Attribution using unchanged model inputs

Separate fresh processes run the member-feature and prescribed-settlement public
helpers at current source `7bdfb6e190d0ffcc67d1f55ba9571f30bbd32868` and the
main-based R2 source `f788a3c55964ef963f8145835e188d4a3f3792da`.
A third, explicitly diagnostic process uses current code with only the
`corotational_frame2d_basic_kinematics` function body from main
`4de4e3f55aae1d267cf704cec7d7533f3a627498`, bound to the current module globals
before importing the receipt runner. This process receives no product acceptance
credit; its override is recorded in its payload and preserved worker.

| Case | Current horizontal reaction (N) | Main and single-function diagnostic (N) |
| --- | ---: | ---: |
| Member feature | -1.3753172320614404e-12 | 4.964244685421869e-7 |
| Prescribed settlement | -1000.0000000000011 | -999.9999996368759 |

The diagnostic reproduces both entire helper result payloads exactly, including
displacements, member forces, support reactions and recovery metadata. The
source model and runner input hashes are recorded for each process. This isolates
the arithmetic change from the other AI-branch changes for these two cases; it
does not establish the accuracy of all solver behavior or verify an external
engine. Existing independent 90-digit kinematic checks, including retained alpha
terminal coordinates, continue to pass without changes.

There are six public analysis helper requests, each reporting four committed
load steps. Helpers also validate and recover their results; no separate total
Newton/material-work count is asserted. Parent times are retained for the two
unmodified-source processes; the diagnostic retains helper elapsed time only.
These timings are diagnostic costs, not performance or speedup evidence.

## Actual blocker output

Source `9899de5455d62713496eb1e778191613c70c59f8` changes the human-readable
license inventory CLI to print each actual blocker. The build, validate, check
and write function ASTs are unchanged. Formatting does not change those functions.
The JSON output mode and exit-code policy remain unchanged.

Running the committed CLI on the copied failed current-product receipts exits
**1** and prints:

```text
Internal license due diligence: blocked | inventory=7 | legal_approval=False
Internal license due diligence blocker: external_code_to_code_product_replay_not_passed
Internal license due diligence blocker: external_code_to_code_technical_receipt_not_ready
```

Four new CLI tests cover complete and blocked payloads in text and JSON modes.
They verify that legal approval staying false allows a complete inventory to
exit zero, blocked replay still exits one, and JSON remains one parseable
document. Together with the inventory and stable-kinematics suites,
**43 tests pass in 1.82 s**. Ruff, formatting and diff checks pass. This improves
failure diagnosis; it does not turn the failing numerical comparisons into passes.

The [machine summary](planar-reference-attribution-20260910.summary.json) binds
the preserved local packet at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-planar-attribution.ikbz9yv_`.
Protected receipts, external numbers, existing learning studies and original
worktrees are preserved. Current external-runtime verification and full hosted
acceptance remain open, along with the full M1-M5/P1-P3/R1/R2 roadmap.
