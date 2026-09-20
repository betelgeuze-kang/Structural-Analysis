# Fixed gate variants: complete excluded-group evaluation, no promotion

Frozen source `42815feb1adc26694e7e4d51181fbbac09ab75f3`; [prepared evaluation](rc-inner-gate-evaluation-preparation-20260920.md). The driver completed all twenty directed outer/validation folds for both predeclared variants: **40 actual fits**, each using 99 triple-excluded training rows and a separate 33-row validation table. Ridge 1 and threshold 0.01 were unchanged. The 27 accepted-material statistics are included only in the material variant.

Training labels come from the [new complete 990-pair campaign](rc-inner-label-results-20260920.md). Validation labels reuse the original authenticated 660-pair campaign, whose producing seeds exclude both outer and validation groups. No normalization uses validation rows. This is additional development validation, not untouched project/geometry evaluation.

| Variant | True positive | False positive | True negative | False negative | Unverified |
| --- | ---: | ---: | ---: | ---: | ---: |
| Prefix cost | 0 | 0 | 628 | 32 | 0 |
| Material cost | 0 | 2 | 626 | 32 | 0 |

Each variant has 660 overlapping validation decisions involving 165 original source samples; these are not 660 independent experiments or projects. Prefix cost declines every row. Material cost proposes two rows in `train-e-amp150`, from different outer folds. Their predicted relative margins are 2.4485% and 1.2805%, while their measured worst-repeat margins are **−2.3058% and −1.3168%**. Neither variant identifies a verified beneficial proposal. No winner is selected, no online adapter is promoted, and no new full-path campaign is justified by this result. Deterministic secant remains the supported baseline.

## Independent retained-output check

A separate audit verified all 989 evaluation payloads (34,372,864 bytes), reconstructed every training/validation table from pinned sources, checked all policy hashes and exclusions, reproduced exact training-only normalization, and checked the fitted ridge normal-equation residual without refitting. The maximum residual was **5.4539706084710815e−14**. Independently recomputed bounded decisions, three-repeat labels/targets, per-row source identities, report hashes, counts, precision and recall match all forty saved evaluations.

The audit performs zero new fits and zero structural solves. The original evaluation performs zero structural solves and leaves reserved cases untouched. Full-path runtime benefit remains unmeasured for these fitted gates; false positives are classified against retained single-target cost observations.

## Costs and immutable receipts

Forty fit calls total 0.273096463 seconds, contained within the 2.253005970-second driver and its 4.018155270-second enclosing process. Full new-label inventory verification before fitting took 9.466660970 seconds. The separate evaluation audit took 2.172438040 seconds. These do not erase historical sample/seed/label generation costs; material extraction and online guard cost would also need charging in a future runtime campaign.

Evaluation packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-inner-gate-evaluation-kar_fiaa`.
Inventory: `69dd07e07063ba88f8227bddc57ffcd02bc1de100e0adc335a35caea8faf0afb`.
Audit packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-inner-gate-evaluation-audit-7y38z_zc`.
Audit inventory: `6b7b44b140f622dfceb8bb1ccd188b58404716f335682872310ca933434d3c20`.

This negative result rules out promoting these fixed linear gates on the available development evidence. It does not prove all learned warm starts impossible or remove the roadmap requirement for useful independently evaluated learning.
