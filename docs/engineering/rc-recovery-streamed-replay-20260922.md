# RC recovery integration, bounded replay, and branch-sampled candidate

Base: `431b895f0be5bbf7da0c95a26ec72ed2d97b3d3f`. This change does not modify
material laws, element equations, native tolerances, recovery budgets, protected
evidence, original runtime entry points, or branch rules.

## Explicit entry point

`rc_control_recovery_execution.benchmark_rc_control_seed_paths` accepts one
`RCControlRecoveryStrategy` or valid historical Boolean selectors. It delegates
to the unchanged historical runtime. Six profiles retain existing identities and
numerical results. This supersedes the earlier local plan to edit the large
runtime itself; no monkeypatch/import indirection is used.

## Replay

`ReplayStudyFiles` keeps only file metadata and validates detached JSON one file
at a time. Initial bytes are read once for hashing and strict decode, followed
by a complete inventory recheck. Every later lookup checks the initial digest;
a final check detects changes during fresh execution. These are trusted local,
non-concurrently-written workspaces, not a multi-user filesystem sandbox.
Encoded byte limits are not RSS limits. Exceptions retain a failed audit and
known/unknown work where possible; the original exception remains primary.

## Diagnostic and experimental candidate

The noncommitting binary64 diagnostic validates finite derived results and is
tested on an actually accepted parent with nonzero compression history. That
fixture remains elastic; it does not qualify arbitrary plastic/damaged parents.
A fixed direction, sampled on a declared dyadic grid (18 samples by default,
65 maximum), may produce one strictly descending seed. Ties prefer fewer sampled
branch changes and then the smaller fraction. Only one unchanged native Newton
confirmation can accept. Partial diagnostics cannot select a seed. Direction
construction cost is outside the function and explicitly labelled. This is not
an adaptive line search, a default solver, or a demonstrated speed improvement.
The original 80mm failure checkpoint is not available here and is not resolved.

## Local use

```
python -m structural_analysis.benchmark.rc_recovery_cli run \
  --model model.json --request request.json --strategy adaptive-failed-target \
  --source-revision <40-lowercase-hex-commit> --output new-directory --replay
python -m structural_analysis.benchmark.rc_recovery_cli summary --study new-directory/study
```

`--replay` requires the existing constant-load v2 request profile. Unsupported
scope is rejected before calculation/output creation. Summaries distinguish
completion, declared full-history checks, fresh numerical reproduction, work,
and independent physics. No command grants design approval or changes GitHub.
Run exit codes: 0 complete declared comparisons (and replay when requested),
1 incomplete/unverified, 2 input/execution failure, 130 interrupted. Read-only
summary exit 0 means bounded artifact checks, not successful structural analysis.

## Verification and limitations

The final focused local selection passes 171 cases: 151 added test cases plus
20 retained review cases. It includes real small RC paths, synthetic interruption
and admission tests, and no original large-80mm replay. The legacy runtime stays
byte-identical. Existing full-suite and independent validation requirements remain.
Python 3.13.5 / NumPy 2.3.5 / SciPy 1.17.0, wheel-derived partial tree, not the
canonical hosted Python 3.10 checkout. Full remote tests and merge eligibility
must be checked on the final committed source. No release or physical promotion.
