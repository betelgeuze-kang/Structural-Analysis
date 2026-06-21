Goal: Tighten G1 alternating closure aggregation so nested closure evidence is authoritative only when read from the actual nested child receipt file.

Scope: Inspect and, if needed, update `implementation/phase1/run_mgt_g1_alternating_newton_controller.py` and `tests/test_mgt_g1_alternating_newton_controller.py`. Keep the change narrow. Do not edit PM reports, ledgers, release receipts, environment files, or unrelated solver code. Do not claim G1 closure in docs or receipts.

Candidate files:
- `implementation/phase1/run_mgt_g1_alternating_newton_controller.py`
- `tests/test_mgt_g1_alternating_newton_controller.py`

Verification criteria:
- Nested closure evidence must read `gate_assessment` and `residual_contract` from `child_receipt_path`; embedded row copies alone must not close G1.
- Missing or unreadable nested receipt paths must leave `g1_closure_claimed=false`.
- Existing top-level child receipts with direct `gate_assessment` and `residual_contract` still work.
- Run focused tests for nested/closure behavior in `tests/test_mgt_g1_alternating_newton_controller.py`.
- Worker summary only: changed files, test results, failed test names, core diff summary, blockers.
