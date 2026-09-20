# One locally accepted reversal seed; five unsuccessful starts

The predeclared six trust-region attempts on frozen `ca07bb1ea` finished with 607 actual full residual/tangent assembly callbacks. Every generated vector was tested twice with the original Newton configuration: twelve native solves and 44 Newton iterations/linear solves. Optimizer time totaled 1.216304871 s and native confirmation time 0.562809281 s. These are single-run diagnostic clocks, not speedup measurements. Native Newton assembly counts were not instrumented; the 607 count covers optimizer callbacks only.

Only the width 0.48 m / cheap candidate, starting from its accepted parent coordinates, passed the native solver. It required 23 optimizer assemblies, reached normalized residual 9.473903143468002e-16, and passed original equilibrium, increment and control gates in each native confirmation. The two accepted checkpoints agree exactly. No optimizer callback changed the parent. The other five starts failed native acceptance, including the same model started from its recorded terminal failed iterate. Optimizer termination alone was not treated as acceptance.

| Case | Start | Optimizer assemblies | Native acceptance |
| --- | --- | ---: | --- |
| w32 cheap | parent | 76 | failed |
| w32 cheap | terminal failed iterate | 193 | failed |
| w32 middle | parent | 82 | failed |
| w32 middle | terminal failed iterate | 39 | failed |
| w48 cheap | parent | 23 | passed twice |
| w48 cheap | terminal failed iterate | 194 | failed |

This authenticates one local equilibrium candidate on a retained parent. It does not establish a complete freshly reconstructed path, an independently validated physical branch, a causal cheap predictor, or a faster policy. Failed-terminal starts use already observed failure information. All six starts and twelve native records remain available; no successful subset is substituted for the full roster.

All 38 packet files were inventoried and reread. Inventory SHA-256: `cce59b19ef2f63edfb3b313a424e095dcfd44eed5e3aabb02d778e68fe754854`. The [summary](rc-reversal-trust-results-20260921.summary.json) retains the complete roster, original-solver metrics, clocks, input inventories and audit. The next bounded check reconstructs every model's preload and prefix from its input model before attempting the same parent-start procedure; production behavior remains unchanged.
