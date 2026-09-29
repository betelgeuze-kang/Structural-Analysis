# Bounded fixed-parent step-size diagnostic for the short 40 mm L-frame

Freeze source and authenticate the prior retained-failure packet before reading
its short/40 mm model/request. Use the original first requested target (-20 mm)
and constant 25 kN preload. Rebuild the preload natively for each run. Compare
binary64 and the complete retained arithmetic profile, both with terminal
polishing enabled, in two reversed mode orders. This is four parent-to-target
diagnostics, not a complete-path or performance campaign.

Every trial uses the same original preloaded material parent. Carry only absolute
seed coordinates from the last successful trial. Start at 1/16 of the remaining
original displacement span; after success double the fraction increment up to
1/16, after a known rollback-safe failure halve it. Never advance the accepted
fraction or coordinates after failure. Stop if the increment falls below 2^-20,
if work is unknown, or after 64 native trials. If the original target is reached,
run one additional native confirmation from the unchanged original parent.
The budget is at most 66 calls per run including preload and confirmation.

Preserve all attempts, native states, checkpoints, residuals, step fractions and
work; retain failed originals. Native convergence and history tolerances are
unchanged. An intermediate accepted checkpoint never becomes the material parent.
Failure with smaller increments is not proof that no equilibrium exists. Success
would justify a separate full-history integration/verification step, not immediate
production promotion, physical accuracy or learned acceleration.
