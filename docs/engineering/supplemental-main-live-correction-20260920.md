# Live correction: supplemental integration has merged

The earlier supplemental observation and local `origin/main` reference were
stale. Fresh GitHub API reads on 2026-09-20 confirm PR #440 is closed and merged,
not Draft. User `betelgeuze-kang` merged it at 2026-09-14T05:06:57Z. Its merge
commit `234c3122c78dea064411aa16b06b18ab16157576` is the current protected main
head. A read-only fetch updates the local remote-tracking reference from
4de4e3f55 to that head; the active development branch was not merged or rebased.

This establishes main integration of PR #440's exact-ID supplemental producer
and consumer changes. It does not establish main integration of PR #439,
independent physical qualification, owner-signed acceptance or release approval.
The prior historical document remains a dated observation; this record supersedes
its open/Draft status for PR #440.

Current-main Product State run 35403885473 has failed build-current-state job
105789490226; its subsequent attest/verify/replay jobs are skipped. The original
job log ends with `receipt_product_comparisons_stale`, wrapped as
`matrix_code_receipt_validation_failed`. This is an unresolved current-source
comparison validation failure, not evidence that the now-merged supplemental
transport is absent. No receipt flags, tolerances or authorization gates changed.
The commit check listing contains many historical/nightly checks; it was not
interpreted as a complete audit or a signed acceptance record.

Development head `467d2a05600304e76b2f55abec246a97940c69c4` has only four automatic
push workflows. Repository Python Tests was explicitly dispatched as run
35466030205 at exactly that head. The development-contract job 105958415497,
collection job and four full shards were confirmed running. This dispatch adds
the missing hosted execution, not a passing result. Original full-suite gates
remain in force. PR #439 and issue #438 bodies were updated with the corrected
main state and this pending exact-source validation.
