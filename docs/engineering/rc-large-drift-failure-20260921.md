# Large-drift failure: original reversal nonconvergence

The retained 40 mm failures originate in the original solve, not in a mismatch introduced by fresh verification. Every affected artifact passes its artifact contract and fresh-source replay with no verification errors, but the physical path remains incomplete. Twelve recorded rows represent three candidate models across two orders and full/pruned modes, not twelve independent failures.

All three accept -20 mm and -40 mm, then fail the +20 mm reversal with `line_search_failed_to_reduce_residual`:

| Model | Failed Newton iterations | Final relative residual |
| --- | ---: | ---: |
| width 0.32, cheap | 14 | 0.10949988558613598 |
| width 0.32, middle | 12 | 0.5720162149872313 |
| width 0.48, cheap | 10 | 0.14010521754163582 |

These residuals are far from the requested 1e-10 gate; this is not a near-zero rounding discrepancy. The parent remains unchanged and rollback is exact in all twelve records. Fresh replay repeats the incomplete path, so it correctly withholds full-path verification. The table does not establish the deeper cause of the line-search failure or prove that smaller steps would succeed.

The audit verifies each consumed file against the original sealed packet inventory `dc9cee74b0cefb318f6b6f846b925f091af116b994a8542ed4a2522cc4e748ca`, with no numerical reruns. [The summary](rc-large-drift-failure-20260921.summary.json) preserves all identities and repeated records. Original packet files and tolerances remain unchanged.

The design report now retains `failure.original_analysis_path` with the accepted target prefix, failed target, solver reason, relative residual, parent/rollback status and artifact-contract result. Its existing `verification_blocked` state remains; the candidate is still ineligible with null performance. Both attempted analysis and fresh verification costs remain recorded. This makes the original path failure visible without granting authority to the failed result.

The cost-pruned-design suite passes 16 tests in 8.21 seconds, including a new actual reproduction of the width-0.32 cheap candidate. Ruff and whitespace checks pass. This reporting correction does not resolve the numerical failure. A future bounded globalization comparison must keep the same authored targets, material history semantics and tolerances; any added target subdivision must be declared as a different history rather than a hidden successful retry.
