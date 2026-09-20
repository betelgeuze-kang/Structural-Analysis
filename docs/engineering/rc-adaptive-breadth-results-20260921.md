# Recovery breadth: one resolved obstacle and a retained larger-history limit

Frozen source `84714992a`. The
[reusable runner and fixed protocol](rc-adaptive-breadth-protocol-20260921.md)
executed all 32 comparisons / 128 paths with known work. **70 paths complete;
58 remain incomplete.** These are eight conditions on two canonical L-frame
geometries, not eight independent buildings. All requests use binary64, explicit
terminal polishing, fixed tolerances and the original three-target histories.

Both modes trigger after native failure at any requested target. Only the internal
increment schedule and bound differ: fixed sixteen versus adaptive up to 64.

| Case | Fixed proposal, both repeats | Adaptive proposal, both repeats | Additional calls across repeats, fixed → adaptive | Qualified adaptive/fixed time ratio |
| --- | --- | --- | ---: | ---: |
| Short / 20 mm | Complete | Complete | 32 → 32 | null |
| Short / 40 mm | Incomplete | Complete | 16 → 36 | null |
| Short / 60 mm | Complete | Complete | 32 → 32 | null |
| Short / 80 mm | Incomplete | Incomplete | 18 → 78 | null |
| Long / 20 mm | Complete | Complete | 32 → 32 | null |
| Long / 40 mm | Complete | Complete | 0 → 0 | 0.997516674 |
| Long / 60 mm | Complete | Complete | 0 → 0 | 0.995901541 |
| Long / 80 mm | Complete | Complete | 0 → 0 | 0.999936229 |

Every completed proposal history/checkpoint repeats exactly within its mode.
Where both modes complete, their full histories also match under the original
limits. The first five rows do not pass fresh-reference comparisons in both
modes and repetitions, so their qualified ratios remain null. The last three rows
never invoke either recovery strategy: their near-one ratios describe ordinary
native paths and small timing variation, not adaptive or learned acceleration.
Two repeats do not establish a latency distribution or a statistically reliable
small performance difference.

The adaptive option resolves the short/40 mm obstacle already observed in its
focused study, without regressing completion on the other completed cases in this
roster. Short/60 mm succeeding while short/40 mm fixed recovery fails also shows
that amplitude alone is not a monotonic difficulty indicator.

## Short/80 mm still stops before completing the requested history

Both modes accept the first -40 mm requested target and fail to reach the second
-80 mm target. Fixed recovery stops at internal trial nine, -62.5 mm, with relative
residual 0.018480313658097464. Adaptive recovery uses 39 internal trials per run,
including 24 failed trials, and stops at the declared minimum fraction increment.
Its last successful internal target is -0.061943588256835935 m; the final failed
trial is -0.0619436264038086 m with relative residual 1.348344651559413e-7 and
`line_search_failed_to_reduce_residual`.

The smaller residual does not make the original target complete. No internal
checkpoint is adopted as a material-history parent, no near-target prefix is
reported as a finished history, and no tolerance or budget is relaxed after
observing this result. This is a bounded numerical failure; it does not prove
nonexistence of an equilibrium or identify a physical limit state.

## Work and verification

All ordinary retries, preload and recovery trials are counted:
**462 ordinary + 340 additional = 802 native calls** and
**2,946 + 1,756 = 4,702 Newton iterations**. The observed work is below the
predeclared conservative bound of 4,736 native calls. Import/compilation and the
complete Workbench user flow are outside the per-path timing comparisons.

The separate audit validates the frozen plan against the archived runner,
canonical model/request and strategy identities, original outcome/report/path/
native hashes, phase/path bindings, stage artifact references, failed-first
rollback, full fixed-parent equality, absolute seed handoff and the adaptive
fraction schedule. It recomputes complete-history comparison gates from original
responses and separately checks repeated complete histories before allowing a
ratio. Incomplete prefixes are never credited as complete repeats.

Packet:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-adaptive-breadth-r0_ukbrk`.
All 4,211 audited inventory entries were reread and hash/length checked.
`audited-inventory.json` SHA-256:
`03dc65610ed106d45f088643fc61666be819229c8ed68b4d4624abda2fd52c70`.
[Machine-readable summary](rc-adaptive-breadth-results-20260921.summary.json).
The packet retains source, execution metadata, plan, original files and audit.

The runner is reusable and its orchestration tests are part of development CI.
Observations completing is not full structural validation: independent physics,
qualified engineering range, learned net benefit, product promotion and full
user-time savings remain unproved. The short/80 mm convergence question remains
open and must not be hidden by the successful short/40 mm result.
