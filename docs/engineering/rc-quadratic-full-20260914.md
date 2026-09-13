# Full-path causal quadratic baseline screening

The frozen runner executed archived source
`259697d6ee946057bec3e8bfbe35ac155929e205` for the four original training cases,
using the same causal divided-difference proposal as the
[parent diagnostic](rc-quadratic-seed-steps-20260914.md). It predates the reusable
`quadratic_seed` helper. No current answer label, policy fit, external row or
independent evaluation case entered this run.

Each case runs reference, secant, proposal and fresh reference independently
through all 242 requested targets, with two reversals. Alternate the first
three arms' order by case; fresh reference is last. Each arm builds its own
accepted history. The original request tolerances and retained arithmetic
profile remain unchanged. Each proposal path uses 236 quadratic proposals and
six abstentions, with secant fallback explicitly requested.

These original requests contain no separate constant-load preload. Earlier
progress text saying this run included axial preloading was incorrect. The
audit includes preload invocations when present, but there are none here.
This screening does not validate constant-axial-load quadratic behavior.

## Actual work and timing

| Case | Secant / proposal linear solves | Secant / proposal Newton assemblies | Secant / proposal seconds |
| --- | ---: | ---: | ---: |
| train-a | 969 / 957 | 1640 / 1625 | 67.7291 / 66.8088 |
| train-b | 870 / 863 | 1436 / 1458 | 61.8329 / 62.3920 |
| train-c | 990 / 971 | 1711 / 1670 | 69.8884 / 69.0469 |
| train-d | 852 / 844 | 1424 / 1436 | 61.4770 / 62.4450 |
| Sum | 3681 / 3635 | 6211 / 6189 | 260.9274 / 260.6928 |

All four cases use fewer linear solves, but two use more Newton assemblies
and take longer. The approximately 0.23-second aggregate wall-time difference
does not demonstrate a runtime gain. Each case has only one observation,
related training geometries/histories have already been inspected, and brief
development/unit checks and GitHub tooling overlapped the numerical run.
These observations are neither isolated repeats nor independent generalization.

All 16 paths complete: 3,872 core calls / 17,450 inclusive linear solves /
32,216 Newton assembly calls across all four arms. All 12 full-history
comparisons pass; four reference/fresh-reference histories and terminal
checkpoints match exactly. Proposal checkpoints need not be byte-identical to
reference checkpoints; physical responses must pass the unchanged comparisons.
There is no unknown execution work in these records.

The numerical campaign takes 1,255.087976403 s, including all arms and reports.
Proposal construction/adapter validation and event recording are included in
proposal-arm timing (3.070678119 s aggregate proposal intervals, versus
3.015891068 s for secant). These are nested intervals, not extra costs to add
to arm time. The separate audit takes 43.199151731 s through source, input,
step, proposal and response validation; 45.887974290 s through inventory
creation and complete readback. The latter includes the former and excludes
final receipt writing and permission sealing.

## Audit and next decision

The [receipt](rc-quadratic-full-20260914.json) binds the source archive, frozen
protocol, numerical runner, original inputs, per-step records, events and
auditor. It reconstructs proposals with Lagrange weights, checks canonical
step/path/report hashes, recomputes response comparisons and aggregates actual
invocations. All 23,924 files / 1,415,485,590 bytes are reread and sealed.
The original and revised planned auditors remain in the packet. Numerical
and audit processes have both exited successfully; neither needs restarting.

This makes the optional quadratic baseline a useful comparison candidate, not
an adopted policy or a learned gain. Before training a selector on its modest
work reduction, investigate why assembly work increases in train-b/d despite
fewer linear solves. Any subsequent timing claim requires frozen independent
cases and repeated measurements including all proposal/verification costs.
Constant-load coverage, learned net benefit, independent physics and the full
roadmap remain open.
