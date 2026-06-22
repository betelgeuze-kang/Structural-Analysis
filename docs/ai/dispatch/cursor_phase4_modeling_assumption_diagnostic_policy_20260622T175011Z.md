# Cursor Worker Slice: Phase 4 Modeling-Assumption Diagnostic Policy Audit

Goal:
Audit the Phase 4 commercial comparison import template and operator reference contract for the goal requirement that commercial/reference differences are diagnosed as modeling-assumption differences first, not as solver-correctness claims.

Scope:
- Read only these files unless a direct import requires one more local file:
  - `scripts/build_phase4_commercial_comparison_import_template.py`
  - `scripts/build_phase4_commercial_operator_reference_contract.py`
  - `tests/test_build_phase4_commercial_comparison_import_template.py`
  - `tests/test_build_phase4_commercial_operator_reference_contract.py`
- Do not edit protected evidence receipts or ledgers.
- Do not claim Phase 4 closure.

Report:
- Missing fields or validation rules needed for a modeling-assumption-first diagnostic policy.
- Suggested exact test assertions.
- Any claim-boundary risk.

Verification criteria:
- The policy must prioritize units, local axes, rigid offsets, end releases, diaphragm, mass source, self-weight, material modulus convention, shell formulation, mesh density, damping, P-Delta, eigen solver, load combinations, and convergence tolerance before solver-correctness language.
- Commercial outputs remain comparison references, not absolute truth.
- Operator output absence and two-reference-solver blockers remain visible.
