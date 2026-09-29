# Fixed retained-continuation cost comparison

Freeze the committed source before execution. Compare the short L-frame (2 m,
1.5 m; 2 mm amplitude) and long L-frame (3 m, 2.5 m; 40 mm amplitude), with N3
UY targets `(-A/2, -A, A/2)` and constant N3 FY = -25 kN. Both arithmetic modes
explicitly enable terminal polishing: binary64 and the complete existing
`retained-twofold-refinement.v1` profile. Native and history tolerances are fixed.

Each case runs two repetitions, reversing arithmetic-mode order and arm order:
reference/secant/proposal then proposal/secant/reference. Each comparison includes
a fresh reference. Eight comparisons / 32 paths are planned. Upfront sixteen-stage
frozen-parent continuation remains the numerical proposal in all comparisons;
this experiment does not select or train an AI policy.

Retain canonical models/requests, the source archive, plan, driver, all original
native and trial artifacts, failures, work counts, wall/CPU measurements and
unknown-work flags. Timing includes the benchmark's proposal and artifact costs,
not import/compilation or the complete Workbench user flow. Check repeated complete
histories/checkpoints and fixed fresh-reference comparisons. Report per-arm summed
time across both orders. A proposal/secant timing ratio is eligible only if both
complete and pass fresh-reference gates in both repetitions, work is known and
the repeated complete histories match. Binary64-versus-retained speed claims are
not allowed when either arithmetic mode fails these gates. Passing retained tests
does not establish acceptable total cost, independent physics or broad robustness.
