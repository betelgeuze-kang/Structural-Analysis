# Fresh reconstruction reproduces one successful model and two failures

Each of the three models was run twice from its input model, with the original 600 kN preload and -20/-40 mm prefix rebuilt through the frozen `ca07bb1ea` public API. Every rebuilt parent exactly matches its authenticated retained counterpart; the retained bytes were not used as the solve input. A trust-region candidate from the rebuilt parent's coordinates was then checked by the original Newton solver at +20 mm.

The width 0.48 m / cheap candidate completed the terminal step in both repetitions, with exactly equal accepted checkpoints and normalized residual 9.473903143468002e-16. The width 0.32 m cheap and middle candidates failed in both repetitions. All six attempts remain in the record. Every original equilibrium, control and increment tolerance is unchanged, and optimizer observations left their parent immutable.

| Work scope | Observed work |
| --- | ---: |
| Six prefix analyses, including preload | 18 core calls / 84 Newton iterations |
| Six trust-region proposals | 362 full residual/tangent callbacks |
| Six terminal native solves | 38 Newton iterations / 228 recorded Newton assembly dispatches |
| Prefix time, summed | 1.008373595 s |
| Optimizer time, summed | 0.675447382 s |
| Terminal native time, summed | 0.424789141 s |

Assembly scopes differ: prefix API recovery and native outside-Newton observations are not represented by the 228 sidecar count. The counts must not be presented as a single exhaustive assembly total. All invocation iteration counts are known; these single-run clocks are not a speed ratio.

This extends the retained-parent observation to a custom freshly reconstructed prefix plus terminal solve. It is not the public complete-path artifact validator, an independent reference comparison, a production policy, design approval or physical validation. The original ordinary-Newton and secant paths still fail. A subsequent implementation would need explicit proposal provenance and costs in a complete path contract and fresh validation that does not erase the original failures.

All 44 packet files were inventoried and reread; inventory SHA-256 `368bca15680f194447ece1d835caa6d3aeea9980363dfbf489c42d9f78d24c9b`. The [compact summary](rc-reversal-fresh-prefix-results-20260921.summary.json) contains the roster, clocks, scoped counts, gates and checkpoint hashes. Full native/prefix artifacts, callback evidence and audit driver remain in the sealed packet.
