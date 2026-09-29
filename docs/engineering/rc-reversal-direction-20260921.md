# Retained reversal states have descent outside the configured alpha grid

A noncommitting diagnostic reconstructs six failed states: the original and extended-grid states for each of the three failed candidate models. Original result inputs and frozen `ca07bb1ea` source are checked against their sealed inventories. Reassembled residual vectors and newly solved Newton directions match the recorded arrays exactly. The original accepted parent remains byte-identical after all observations.

The diagnostic samples fixed binary alphas from 1 through 2^-40. It performs 252 residual/tangent assemblies, zero nonlinear solves, zero checkpoint commits and no policy changes.

| Candidate | First decreasing alpha at original failure | First decreasing alpha at extended-grid failure |
| --- | ---: | ---: |
| width 0.32, cheap | 2^-8 | 2^-17 |
| width 0.32, middle | 2^-6 | 2^-19 |
| width 0.48, cheap | 2^-6 | 2^-20 |

All first decreasing alphas lie outside the configuration that failed: original search stops at 2^-5 and the extended search at 2^-16. This shows local descent exists at these retained states. It does not show that repeatedly extending the grid will complete the path. The later states require substantially smaller steps and obtain little residual reduction, while remaining far from equilibrium.

For example, width-0.48 cheap at the extended-grid failure decreases residual infinity norm from 83.4473572635 to 83.4473566231 at 2^-20. That is a tiny local improvement, not convergence. The width-0.32 cheap extended state has a Newton direction with about 3.99 m in one scaled free coordinate against a roughly 0.04 m current coordinate magnitude; a unit Newton step is not locally small.

Linear equation residual norms `||J d + F||_inf` range from about 1.78e-15 to 4.95e-11. Raw augmented Jacobian 2-norm condition numbers range from about 777 to 340,046. Those condition numbers depend on coordinate and equation scaling; they do not prove physical instability or singularity. Small linear equation error also does not prove that all constitutive tangents are globally correct. The packet retains the full directional finite-difference curve, including subtraction-sensitive very small alphas.

The result narrows the next investigation: insufficient configured search range explains the immediate reported failure, but simple grid extension previously only moved the path to another such state. A bounded comparison of a different causal initial guess or a step-limited nonlinear direction is more informative than declaring a larger grid successful based on these local reductions. Any proposal still needs complete authored-target execution, fresh verification, unchanged tolerances and full cost accounting.

All six packet files were inventoried and reread. Inventory SHA-256: `257eb324dd798410ba1bb172bd86510ac4ef933c4af28d9e62d560b049203a8f`. The [summary](rc-reversal-direction-20260921.summary.json) retains each curve, source/input identities, work and parent-isolation checks. This is internal numerical diagnosis, not independent physical validation or a resolved solver failure.
