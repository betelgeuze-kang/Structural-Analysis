# Cursor Composer 2.5 Worker Slice: Quality Gate Audit

Goal: Audit the current worktree for Developer Preview readiness gate risk.

Scope:
- Inspect current files only. Do not edit files.
- Focus on remaining quality-gate risks after Phase3 clean checkout refresh:
  - socket PermissionError failures in the Codex sandbox
  - TPU/HFFB external fetch or DNS/network-dependent checks
  - MGT condensed solve determinism
  - Phase3 clean checkout and git-clean-clone evidence freshness

Candidate files:
- scripts/ai-worker-cursor.sh
- scripts/ai-worker-opencode.sh
- scripts/build_developer_preview_readiness.py
- scripts/build_developer_preview_rc_status.py
- scripts/build_product_readiness_snapshot.py
- scripts/run_mgt_global_fea_condensed_solve.py
- scripts/run_phase3_benchmark_factory_clean_checkout_reproduction.py
- scripts/run_phase3_benchmark_factory_git_clean_clone_reproduction.py
- implementation/phase1/release_evidence/productization/developer_preview_readiness.json
- implementation/phase1/release_evidence/productization/product_readiness_snapshot.json
- implementation/phase1/release_evidence/productization/phase6_clean_checkout_status.json

Verification criteria:
- Report whether each risk is environment/external-state, stale artifact, or code regression.
- Report exact commands run and pass/fail status.
- Return only:
  - Changed files
  - Test results
  - Failed tests
  - Core diff summary
  - Blockers
