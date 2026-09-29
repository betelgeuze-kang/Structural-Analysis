# Frozen-parent continuation finds accepted final candidates for all three models

All three predeclared sixteen-stage searches reach the original +20 mm reversal and pass an additional native confirmation from the same original -40 mm parent. The repeat final checkpoints agree exactly. Unlike subdividing the committed loading history, every stage uses the identical original material checkpoint; intermediate native checkpoint objects are discarded. Only coordinates initialize the next trial.

| Model | Native calls including final repeat | Newton iterations | Final relative residual |
| --- | ---: | ---: | ---: |
| w32 cheap | 17 | 52 | 9.379164112033322e-13 |
| w32 middle | 17 | 51 | 5.305385760342082e-15 |
| w48 cheap | 17 | 55 | 3.157967714489334e-17 |

All 51 original native solves pass equilibrium/control/increment gates with unchanged tolerances. The aggregate work is 158 Newton iterations/linear solves and 324 recorded Newton assembly dispatches; summed native time is 0.746295039 s. Outside-Newton recovery/material work is not an additional counted dispatch. These are retained-parent diagnostic clocks, not full-path speed gains.

The audit checks every stage's actual parent checkpoint against the original failed result, including complete native artifacts rather than only reported parent hashes. All 116 files were inventoried and reread; inventory SHA-256 `54351ec7325076f2b971808daaf7dc5b756921e9b6df8f233d4a4776bce484a0`. The [summary](rc-frozen-parent-continuation-results-20260921.summary.json) retains model-level costs and source packet identity. No unique physical branch, independent experimental agreement or production readiness is inferred.

The next implementation exposes this as an opt-in complete-path proposal, records every intermediate artifact and adds its native calls/iterations as separate proposal work. It must not hide those 16 solves inside one apparent inference or adopt intermediate checkpoint states as requested-history steps.
