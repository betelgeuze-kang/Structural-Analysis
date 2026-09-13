# Historical failure between two real checkpoints — 2026-09-14

Base source `52f9d193f7bd636c5dcde1e7fe3915b534c5d8b5` plus a fixture/test/CI
patch. Production HTTP, Workbench and solver code are unchanged in this follow-up.

The earlier positive case began without a checkpoint. This additional scenario
first executes a real step and saves checkpoint A. Attempt 2 starts from A and
encounters one controlled linear-backend outage during replay; its original
failure diagnostic binds A. The unpatched retry advances and saves checkpoint B.
Attempt 4 consumes B and succeeds with byte-identical request input. The fixture
asserts that the checkpoint bytes differ, and browser tests verify that the
historical header is a SHA-256 different from the current checkpoint's hash.
No status, checkpoint or accepted numerical result is fabricated.

A replay failure can return no observed load path. The initial test fixture
incorrectly assumed a path existed when preparing unrelated adversarial payloads
and stopped with a `NoneType` error before serving the browser. The fixture now
preserves the actual diagnostic and omits only path-counter mutations that cannot
apply to a missing path. No production validation or source data is relaxed.
The failure log is retained; the initial run has one failed case and one unrun case.

Desktop and 390-pixel browser checks confirm that the historical failure is
verified, its original diagnostic downloads unchanged, and the current result
remains verified and succeeded. They explicitly require unavailable work to be
shown as `unavailable`, with the missing-observed-path explanation, not as zero.
Clearing the history view does not change the current job projection.

The corrected initial two-case run passed. After adding the explicit unavailable
work checks, the combined final history suites pass **16 tests in 1.4 min**;
the enclosing runner interval is 81.833442396 seconds. Fixtures are shared across
views: these are not independent structural experiments or production incidents.
Pinned Node 24 TypeScript checking, Ruff and `git diff --check` pass. All 18
workflow contract tests pass in 0.32 s. The new two-case spec is registered in
actual HTTP CI; hosted execution is pending. The existing built frontend from
the preceding production fix is reused; no fresh build is claimed here.

The [receipt](existing-checkpoint-history-20260914.json) binds the base source
archive, exact fixture/test patch, runner, initial failure log, final test log,
build inventory, diagnostics and screenshots. The read-only packet is
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-existing-history-selgn9na`:
28 files, 52753182 bytes. Adjacent `.inventory.json` SHA-256:
`87ec91bf28698af138776b49e8f236382bc0586cc9deecdd3878a43426580595`.
Each file was reread against its length/hash before sealing.

This extends local M5 history coverage to a non-null historical checkpoint and
a later different non-null checkpoint, including unavailable observed work.
It does not establish independent physical validity, all operational restart
conditions, full lifecycle cost or broader roadmap completion. Prior failed
results remain diagnostic-only.
