# Repeated full campaign with measured comparison costs

Frozen source `0f713400a0b493b4d9ce117acc0839929e4364f7` reruns the declared eight conditions, two mode orders and two arm orders: 32 comparisons / 128 paths from two canonical L-frame models. This exercises the committed comparison timing and audit tools on real native calculations. No tolerance, model, policy or request was changed to obtain completion.

All 128 original path statuses, accepted-target counts, preload responses, response histories and terminal checkpoints match the earlier source-847 campaign exactly, including incomplete paths. Totals remain 70 complete / 58 incomplete, 802 native calls and 4,702 Newton iterations and linear solves. All original and newly written inventory entries were reread. The original 80 mm limitation and the failed fresh-reference gates remain visible.

## Measured boundaries

| Boundary | Wall seconds | Process CPU seconds |
| --- | ---: | ---: |
| All 32 benchmark calls and return/exception classification, summed | 114.501715752 | 114.146825168 |
| Runner loop through before final outcome write | 114.573735169 | Not measured separately |
| Enclosing runner process including startup and final output | 116.338499118 | Not measured separately |
| Audit call through audit output close | 10.229858235 | 10.229276678 |
| Enclosing audit process including startup and timing output | 12.116026914 | Not measured separately |

The first three rows are nested; the final two are nested. They must not be summed as independent costs. The separate runner and audit process observations do not include source archiving, preflight, inventory verification between phases, transport or browser review, so their sum is not a measured full user flow. Cache state and host contention are uncontrolled; these timings do not establish a speedup relative to the earlier campaign.

Fixed-mode comparison calls total 49.196171749 seconds across 16 comparisons; adaptive-mode calls total 65.305544003 seconds across 16 comparisons. These enclosing costs include all four arms and differ in completion outcomes and attempted recovery work. Their quotient is not an equal-accuracy or equal-completion performance ratio. Qualified performance remains false; no learned acceleration is inferred from either result.

## Retained evidence

Packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-measured-adaptive-breadth-cafwehuh`. Audited-inventory SHA-256: `24e1bd652a828c559ad694652f5174440090a6e644cea61b2b41b0f9310741be`; 4216 entries reread. It includes the frozen source, driver, all 128 path records, per-comparison timings, runner process observation, separate audit result/timing, comparison to the original path payloads and both inventories.

[Machine-readable observations](rc-measured-adaptive-campaign-20260921.summary.json). Earlier 29 focused tests validate contracts; this study adds actual all-condition execution evidence but does not substitute for independent physical validation, experimental provenance, full CI, hardware or release approval.
