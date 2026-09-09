# Supplemental producer and production consumer on current main

The separate R2 integration is now based on main
`4de4e3f55aae1d267cf704cec7d7533f3a627498`, verified against GitHub on
2026-09-09. Integration commit `7e18876131bacc176182773ca8cf5b8763fcc795`
applies the original candidate's complete 13-file patch without conflicts.
Formatting commit `8c64a1fcd0d7d69086d219980cbe6d38a9be579c` is the final
executable source covered by the local checks below. This is a review candidate;
these local results do not establish a successful hosted Product State execution.

The branch is `codex/r2-current-main-20260909`, isolated at
`/home/betelgeuze/.codex/worktrees/r2-final-base-20260909/건축구조분석`.
The original R2 checkout remains at `6088df6aaf2160f132029601c0fc45588d88a53f`;
PR #432 and draft PR #434 retain their original heads. The AI roadmap branch and
the user's original checkout were not used to integrate this patch.

## Reviewed source boundaries

Before formatting, all 13 changed files match the original R2 candidate byte for
byte. Their paths have no overlap with the six intervening main commits, and all
paths changed by those main commits retain their current-main bytes.

The literal production block from `technical_receipt` through the final receipt
check is byte-identical to main, including all five family rows, signature
verification, runtime seals, unavailable handling, and receipt construction and
checking. Its comparison digest is
`d4502c5ddc4b0108ea086af25c2aa2ecaf54b7fe85460a0527120f1b7d259185`.
The existing lookup retries remain. Direct artifact-ID transport, bounded archive
validation and fresh-directory extraction replace the name-based download.
Separate diagnostics remain outside signed inputs.

The initial full changed-file format check found four inherited producer/consumer
files needing formatting. Ruff formatted those four files; their Python ASTs,
excluding source locations, remain identical. The initial failing check and
before/after file hashes are retained. Ruff checks and formatting now pass for all
seven changed Python files. No numerical tolerance, signature rule, unavailable
condition or acceptance threshold was adjusted.

## Executed local verification

| Check | Result | Measured test time |
| --- | --- | ---: |
| Producer identity, after formatting | 19 unittest methods passed | 0.267 s |
| Consumer, after formatting | 28 unittest methods passed | 0.043 s |
| Literal production shell, after formatting | 10 unittest methods passed | 14.402 s |
| Repository workflow contracts, integration commit | 13 pytest tests passed | 0.36 s |
| Source-quarry inventory, integration commit | 9 pytest tests passed | 20.38 s |
| Runner, ownership, workflow/YAML and action-pin contracts, formatted commit | 66 pytest tests passed | 1.42 s |

These are 145 distinct test cases/methods across the listed suites; the 57
producer/consumer/production methods were also executed before formatting and are
not counted twice. The tests contain further parameterized failure scenarios.
The machine report retains each command's parent elapsed time separately from
pytest/unittest's measured time; these are nested timing scopes.

The offline inventory check passes at both integration and formatted commits:
480 historical rows, 71 present and 409 superseded, with no blockers. The canonical
inventory does not require another rebuild on current main. Its stored historical
GitHub metadata was not refreshed by these offline checks.

The runner-policy check passes across all 49 workflows / 89 runner declarations.
The four changed workflow files parse with duplicate-key rejection and required
trigger/job mappings. Ruff, formatting and patch whitespace checks pass.
Actionlint and ShellCheck are unavailable locally and were not executed.

The production test runs the actual workflow shell and the actual consumer and
identity verifier. GitHub transport, attestation replies, sleep and the downstream
receipt builder use controlled shims. Thus the tests establish local orchestration
and rejection behavior, not real signature verification, hosted artifact upload,
independent engineering validation or release readiness.

## Retained record and outstanding acceptance

The [machine-readable validation record](supplemental-current-main-20260909.summary.json)
binds source revisions, commands, log hashes, source comparisons and the formatting
reconciliation. The local record contains 76 files / 1,298,833 bytes, reread exactly,
at `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-r2-current-base.u9ovgsuy`.
Its adjacent inventory SHA-256 is
`77b447fe562a62bb5d427e813c70a96d0772a3b97262a31e3eea20c1b941b12d`.
The earlier [integration report](supplemental-production-consumer-20260908.md)
remains a historical record of the original candidate.

Exact-head hosted PR checks, a real Product State consumer run, actual retained
diagnostics and the historical duplicate-registration cause remain open. Issues
#433 and #435 cover producer verification and the preparatory consumer;
the production wiring is additional R2 work tracked by #438. No original PR is
merged or closed by preparing this candidate, and no independent, licensing,
operator, hardware or release dependency is completed by these tests.
