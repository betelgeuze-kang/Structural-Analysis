# G1 Physical-Consistent Line-Search Preview (F1, non-promoting)

Step F1 of the D→E→F plan. Drives the opt-in physical-consistent global Newton
operator (E) into a Newton **direction solve + physical-residual backtracking
line-search** on the deterministic representative physical system, and checks
whether it beats the D-audit tiny-alpha stall. It does not change the default
solver path, does not promote G1, and does not regenerate tracked evidence.

- Line-search helper: `implementation/phase1/g1_physical_residual_line_search.py`
- Preview driver: `implementation/phase1/run_g1_physical_consistent_line_search_preview.py`
- Tests: `tests/test_g1_physical_residual_line_search.py` (hermetic, synthetic)
- Output: `release_evidence/productization/g1_physical_consistent_line_search_preview.local.json`
  (untracked `*.local.json`; never promoted, never committed)

## What F1 proves (representative system)

1. the physical-consistent operator builds a direction with **no** lambda damping;
2. a matrix-free GMRES solve (and an equivalent dense representative solve) works
   on `J_phys(u) p = -R(u)`, with `J_phys . v` the matrix-free JVP from E;
3. an accepted alpha is found on the **physical** residual
   `R(u, lambda) = F_int(u) - lambda * F_ext`;
4. accepted alpha is larger than the D tiny-alpha threshold (~1.25e-4);
5. residual reduction per pass beats the D baseline (~1.9%);
6. the predicted/actual mismatch ratio collapses from the D audit's ~8.3e5x;
7. the report stays non-promoting (no G1 closure field).

## Mandatory F1 success criteria (locked by tests)

- default solver path unchanged;
- physical operator opt-in only; lambda damping excluded; JVP parity still passes;
- `line_search_preview.status != "deferred_to_F"`;
- `accepted_alpha > 1.25e-4`; `residual_reduction_ratio > 0.019`;
- predicted/actual mismatch ratio `<< 8.3e5`;
- `promotes_g1_closure = false`; tracked protected evidence not modified.

Fail-closed behaviour is also tested: no descent -> `no_descent_found`, GMRES
nonconvergence -> explicit `reason_code`, NaN residual -> `fail_closed_nan`.

## Observed on the representative system (non-promoting)

`accepted_alpha = 0.03125` (≈250x the D threshold), `residual_reduction_ratio ≈ 0.26`
(≈14x the D baseline), accepted predicted/actual mismatch ratio ≈ 0.083 (vs the D
audit's ~8.3e5). These are positive F-stage signals on a representative system, not
a G1 claim. The non-unit accepted alpha reflects a genuine nonlinear backtracking:
the full Newton step overshoots into the geometric term.

## Deferred to F2

Real MGT model / 0.656 continuation checkpoint regeneration and application is F2
and is intentionally not performed here.
