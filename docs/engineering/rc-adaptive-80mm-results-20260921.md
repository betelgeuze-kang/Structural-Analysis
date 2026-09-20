# Short L-frame 80 mm arithmetic isolation

Four frozen-source comparisons at `a94d82d1ed60317d36bce7f5af67730576f9ff61` repeat the short L-frame with binary64 and the complete retained-arithmetic profile, reversing mode and arm order on the second repeat. The canonical geometry is 2 m by 1.5 m, constant N3 FY is -25 kN, and original N3 UY targets are -40, -80, +40 mm. Terminal polishing is enabled in both profiles. Original Newton/history tolerances, adaptive maximum 64 calls, and minimum fraction increment 2^-20 remain unchanged. The plan was written before numerical execution.

All 16 paths (reference, secant, proposal and fresh reference for each comparison) remain incomplete. Each adaptive proposal accepts only the original -40 mm target and fails at the next -80 mm target. Both profiles and both repetitions stop after 39 recovery trials at the same last attempted -0.0619436264038086 m coordinate, with last successful internal target -0.061943588256835935 m. Each recovery keeps the original outer material parent; no intermediate material checkpoint is adopted. Repeated proposal prefixes and terminal checkpoints are exact within each arithmetic profile.

Binary64 terminal relative residual is 1.348344651559413e-7; retained arithmetic is 1.3483442044547537e-7. Both retain `line_search_failed_to_reduce_residual` and `minimum_fraction_increment`. The small numerical difference does not turn either into an accepted original target. This observation rules out simply switching to the tested retained profile as a remedy for this case; it does not prove nonexistence of equilibrium, global instability, or validity of the physical model.

All unsuccessful work is retained: 52 ordinary plus 156 additional native calls (208 total), and 368 ordinary plus 1,012 additional Newton iterations (1,380 total). Summed proposal wall times across two repetitions are 16.440205331 s for binary64 and 56.600090475 s for retained arithmetic. These are raw incomplete-path costs; every qualified proposal/secant speed ratio remains null. No learned policy or production default changes.

The next numerical investigation must distinguish local residual/tangent behavior from path-following limitations at the failed parent. Increasing precision alone did not resolve the witness, and reducing the original tolerance would not establish correctness. Independent experimental validation remains open.

## Evidence and checks

Packet `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-adaptive-80mm-k70o7es7` preserves the source archive, pre-execution plan, driver, all returned reports and trial artifacts, plus the readback audit. The audit verifies all original inventory hashes, all four comparison identities, native work accounting, trial hashes and unchanged original material parents. All 1447 audited-inventory files were reread. Inventory SHA-256: `d8c52bb79583fac4cb7d6505194914226569419ebe7c97103e0234adb90db28a`.

[Machine-readable results](rc-adaptive-80mm-results-20260921.summary.json) include failure coordinates, repeated prefixes, raw clocks, complete-path gates and null ratios. This is a new actual numerical diagnostic, not independent physics verification or a new repository test run.
