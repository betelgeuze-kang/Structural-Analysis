# OpenCode Worker Review: strict P1 evidence readiness

Goal: Give a concise independent review of strict P1 evidence readiness consistency.

Scope:
- Inspect commit `54b46729` and current branch status.
- Focus on P1 EB/RH evidence status handling and claim-boundary docs.
- Candidate files:
  - `scripts/preflight_p1_evidence_sidecar_intake.py`
  - `scripts/check_p1_benchmark_breadth_status.py`
  - `scripts/materialize_p1_operational_queues.py`
  - `implementation/phase1/commercial_gap_ledger_status.py`
  - `implementation/phase1/release_evidence/productization/*`
  - `README.md`
  - `docs/commercialization-gap-current-state.md`
  - `docs/commercialization-improvement-priority-assessment.md`
  - `docs/github-documentation-status.md`
  - `docs/independent-commercial-product-gap-reassessment.md`

Verification criteria:
- `signed_attached` is accepted for RH closure evidence, but EB receipt remains `0/4`.
- G6 remains `external_blocked` and does not claim full strict EB/RH closure.
- PM gate remains limited milestone ready, not full release ready.
- Docs do not say RH closure is `0/3` or pending.
- `trace.jsonl` and `.betelgeuze/worker_outputs/` are not staged or tracked.

Run only these checks and do not paste their full output:
- `git status -sb`
- `python3 -m pytest -q tests/test_preflight_p1_evidence_sidecar_intake.py tests/test_check_p1_benchmark_breadth_status.py tests/test_materialize_p1_operational_queues.py tests/test_commercial_gap_ledger_status.py::test_commercial_gap_ledger_status_is_honest_about_current_blockers`
- `git diff --check HEAD`
- `rg -n 'RH.*0/3|0/3.*RH|receipt/closure evidence 7|9\.0/10|strict EB/RH pending' README.md docs/commercialization-gap-current-state.md docs/commercialization-improvement-priority-assessment.md docs/github-documentation-status.md docs/independent-commercial-product-gap-reassessment.md`

Do not edit files.

Your entire response must start with `Changed files` on the first line. No greeting, no intro, no markdown fence, no preamble.

Use exactly this response skeleton:

Changed files
- one short line

Test results
- one short line

Failed tests
- none

Core diff summary
- one short line

Blockers
- one short line or none

Keep the full answer under 1200 characters.
