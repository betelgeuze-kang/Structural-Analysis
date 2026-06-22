# Cursor worker slice: Phase 4 analytic/physical fallback scorecard

Goal:
Add or audit a narrow Phase 4 evidence artifact proving that cases without operator-attached commercial solver outputs can still be evaluated by analytic/physical checks, without claiming Phase 4 or commercial closure.

Scope:
- `scripts/build_phase4_commercial_*`
- `scripts/build_phase3_benchmark_factory_artifacts.py`
- `tests/test_build_phase4_*`
- `tests/test_build_phase3_benchmark_factory_artifacts.py`
- `implementation/phase1/release_evidence/productization/phase4_*`

Candidate implementation:
- A new generated receipt such as `phase4_analytic_physical_fallback_scorecard.json`.
- It should consume the Phase 3 benchmark factory seed manifest/scorecard.
- It should report counts for cases without commercial references, analytic expected-output checks, physical residual/equilibrium checks, convergence-history presence, regularization/fallback absence, and explicit claim boundaries.
- It must keep `phase4_closure_claim: false`, `commercial_cross_solver_execution_missing`, and `two_reference_solver_comparison_not_available` visible.

Criteria:
- The artifact is ready only for the generated seed fallback lane, not commercial comparison.
- Phase 3 build summary/repro bundle references it if appropriate.
- Tests assert the fallback scorecard does not close Phase 4 and preserves commercial/operator blockers.

Verification:
- Focused pytest for new/changed Phase 4 and Phase 3 tests.
- Ruff on changed scripts/tests.
- Check mode for changed artifact builders.

Return only:
- Changed files
- Test results
- Claim-boundary risks or blockers
