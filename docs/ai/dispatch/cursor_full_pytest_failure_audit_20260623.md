Goal: Audit the non-socket full pytest failures after readiness artifact updates.

Scope:
- Do not edit files.
- Focus on these failures only:
  - tests/test_mgt_global_fea_condensed_solve.py::test_mgt_condensed_solve_wires_native_status
  - tests/test_probe_tpu_hffb_case_pool.py::test_probe_tpu_hffb_case_pool_aggregates_fetch_reports
  - tests/test_run_phase3_benchmark_factory_clean_checkout_reproduction.py::test_phase3_clean_checkout_reproduction_runs_isolated_seed_contract
- Ignore socket permission failures caused by local TCP server creation in the Codex sandbox.

Candidate files:
- scripts/run_mgt_global_fea_condensed_solve.py
- tests/test_mgt_global_fea_condensed_solve.py
- scripts/probe_tpu_hffb_case_pool.py
- tests/test_probe_tpu_hffb_case_pool.py
- scripts/run_phase3_benchmark_factory_clean_checkout_reproduction.py
- tests/test_run_phase3_benchmark_factory_clean_checkout_reproduction.py

Verification criteria:
- Report whether these failures are caused by current uncommitted readiness changes, missing local artifacts, environment restrictions, or pre-existing assumptions.
- Return concise output only: changed files: none; test results; core cause; recommended next action.
