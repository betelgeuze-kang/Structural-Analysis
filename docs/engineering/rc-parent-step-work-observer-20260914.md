# Supplied-parent work observation — 2026-09-14

A reusable diagnostic now extracts cost differences from the existing
`experimental-rc-control-parent-step-comparison.v1` reports. It does not fit,
select or admit a policy. The existing separate-full-path observer remains
unchanged in behavior and continues to reject causal-label interpretations.

`analyze_rc_control_parent_step_work(report, context)` checks the comparison
hash, canonical accepted-context byte count/hash, source target and control,
common native parent, complete one-target paths for all four executions,
response comparisons, exact fresh-reference repeat and known invocation work.
It includes every recorded attempt, including unsuccessful attempts before a
successful recovery. A failed comparison, missing/unknown work, mismatched
parent/prefix or invalid time cannot become a zero-cost sample.

The result retains all four work totals and whole-arm wall times, with
proposal-minus-secant differences. Whole-arm timings already include proposal,
recovery and step IO; this function does not add those nested intervals again.
These are local consistency checks against supplied records, not independent
source authentication, parent reachability, permission to train, or evidence
that choosing steps retrospectively accelerates a complete path. Those claims
remain explicitly false. The context argument is a decoded canonical object;
this function is not a raw JSON transport parser.

## Verification

- `PYTHONPATH=src python3 -m pytest -q tests/test_rc_control_step_work.py`:
  **37 passed, 1.57 s** (21 existing full-path tests and 16 new diagnostic tests).
- Ruff format/check and `git diff --check` passed.
- Read-only replay of the 20 original reports and canonical contexts in
  `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-quadratic-seed-twwg82hn`
  reproduced total proposal-minus-secant work: **0 core calls, -5 recorded
  Newton iterations, -5 linear solves**, and **-25,082,799 ns** whole-arm time.
  These are the same observations described in
  [the original screening](rc-quadratic-seed-steps-20260914.md), not new samples.
  No new solver calls or fits; the sealed source packet was not modified.
- The 20 parents come from four already inspected related training cases.
  Re-extracting these records adds no independent generalization evidence.
  The small single-observation timing difference is not a demonstrated speedup.

Next learning experiments still require an explicit campaign split and source
admission decision, and a full-path evaluation of any proposed strategy. The
observer deliberately does not turn a validated local difference into a
training label automatically.

## Integration boundary

At this change's preparation, the published `cccee909a8f4eb11c63724888db19617412fb859`
CI remained active: repository Python run `34772638006`, runtime run `34772637958`,
and execution-topology run `34772638050`. Their outcomes are not evidence for
this subsequent local change. No push was issued to interrupt these runs.

## Current solver integration follow-up

The initial archived replay covered retained-arithmetic reports only. Adding
observer assertions to existing real solver tests exposed an unsupported
assumption: the default binary64 report does not carry a top-level
`compiled_problem_contract_hash`. Its canonical accepted context and all four
paths still bind that same problem. The observer now uses the hash-bound context
identity, checks every path against it, and requires the optional top-level
identity to match when present. A conflicting or null supplied identity rejects.
No solver, source report schema or original numerical artifact was changed.

The integration assertions exercise binary64 and retained arithmetic with a
constant preload, valid proposals, invalid-proposal fallback and abstention to
secant. They compare actual original arm wall times, work totals and source
indices. They keep training and full-path performance claims false.

The first combined run exposed **3 failures and 56 passes in 11.18 s**. The three
failures were the newly asserted binary64 cases, not numerical solver failures.
The corrected final result is recorded below.

Final verification:
`PYTHONPATH=src python3 -m pytest -q tests/test_rc_control_parent_step.py tests/test_rc_control_step_work.py`
— **61 passed in 11.05 s**. Ruff and `git diff --check` also passed.
This includes fresh numerical executions through both supported arithmetic
profiles; it does not establish independent physical validity or speedup.
