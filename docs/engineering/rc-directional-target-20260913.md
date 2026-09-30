# Training-only directional correction and residual diagnostic

Source: `340d26c53ac6ee7412a740a02e9064ba3cf06b3b`. The completed same-parent study already showed that the existing learned proposal never reduced primary convergence rows in its 241 actual proposals. This follow-up examines a different, smaller representation before fitting another policy: change only the magnitude of the secant advance on free coordinates, preserving the prescribed control coordinate.

The coordinate diagnostic reads 964 original training rows, 241 for each of train-a/b/c/d, from the sealed training-expansion packet. Sample hashes, ordering, original secant coordinates and correction labels were checked. The historical 92-feature policy is used only to bind sample order and its training-derived target scales; its predictions and the later 500-feature policies are not evaluated here. No validation/holdout observations or public measured data are used.

Let `d = secant - previous accepted coordinates`, with the prescribed-control component set to zero. For each original accepted answer, the oracle chooses the scalar coefficient minimizing the correction's squared error along `d`, then clips it to [-1, 1]. The proposed seed is `secant + alpha*d`. Every coefficient already lies in that interval. Each coefficient uses its own accepted answer: these are oracle expressivity values, not an executable learned predictor or held-out performance.

| Training case | Remaining squared error, native augmented coordinates | Remaining squared error, historical target-scale metric |
| --- | ---: | ---: |
| train-a | 0.273689 | 0.903298 |
| train-b | 0.168609 | 0.899861 |
| train-c | 0.173887 | 0.751705 |
| train-d | 0.200677 | 0.974123 |

The fixed control component is excluded from both metrics. Native augmented-coordinate error is not physical equilibrium error: translations, rotations and scaled load-factor coordinates have different mechanical effects. The large difference between these two coordinate metrics therefore does not select a training loss or establish a computational benefit.

A second protocol freezes five uniformly spaced indices (1, 61, 121, 181, 241) per training case. From each identical original reference parent, it assembles the secant seed and the two oracle seeds once: 20 parents and 60 explicit residual/tangent dispatches. It does not execute Newton, solve a linear system or commit an accepted step. Compiled problem identities and original parent/step bindings must match; native before/after parent bytes remain unchanged. The archived source, inputs and stored residual ratios were rechecked.

| Seed | Lower / equal / higher residual than secant | Original residual gate passed | New gate passes |
| --- | --- | ---: | ---: |
| Secant | reference | 5 / 20 | — |
| Native-coordinate oracle | 2 / 3 / 15 | 5 / 20 | 0 |
| Target-scale oracle | 7 / 3 / 10 | 5 / 20 | 0 |

On all 15 parents where secant fails the residual gate, the native-coordinate oracle increases the residual. The target-scale oracle lowers it in five and raises it in ten, but creates no new gate pass. Passing this residual gate alone would not establish increment convergence or fewer iterations; those were not tested. Tiny changes on already-small residuals are retained rather than interpreted as material improvements.

The result argues against proceeding directly to a scalar **coordinate-loss** policy in this direction. It does not prove that every scalar policy is useless: a residual-directed coefficient, a different correction subspace or harder supported cases could behave differently. Any next candidate still needs train-only fitting, independent split controls, measured full-path cost and unchanged accepted-history verification. Secant remains the baseline and no policy is promoted.

The initial residual observer failed after one explicit assembly because it compared native checkpoint bytes with transport JSON instead of a native before/after snapshot. That failed packet and log remain preserved. A separate corrected run compares like representations and completes all 60 dispatches, with coefficients independently recomputed from the original labels and policy scales. The initial failed trial produced no retained numerical row; it is not silently counted as a successful probe.

The coordinate diagnostic records 0.717067405 seconds including its input processing after imports. The corrected residual loop records 2.425804414 seconds including case compilation, original-record reads, assembly and row writes, but excluding earlier source staging/imports. Initial failed-run and complete research-lifecycle costs are unknown. These are diagnostic intervals, not solver speed measurements. All three packets are sealed; exact paths, inventory hashes, per-row values, input bindings and scripts are retained in the accompanying summary. No learned policy was fitted, no complete path or independent physical experiment was verified, and no net saving is claimed.
