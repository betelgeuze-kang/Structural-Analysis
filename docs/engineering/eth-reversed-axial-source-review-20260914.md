# ETH reversed-axial campaign: separate material tests from member labels

Review source is `e97f9e971`; no raw samples or models enter training.
The [publisher paper](https://doi.org/10.1002/suco.70408), Sections 2, 4 and 6,
reports five RC axial specimens and fourteen separate cyclic reinforcing-bar
tests. CW specimens s-1–6 and s-11–14 are a material-comparison lead. QST
specimens s-7–10 were excluded from the paper's subsequent evaluation because
of suspected clamping influence. They must not silently join the initial fit.

The member response involves crack closure, tension stiffening and bond.
Steel stresses inferred from member strain through a calibrated material model,
and bond stresses derived from those stresses, are not directly measured stress
labels. Material and member tests share reinforcement batches and form one
campaign, not nineteen independent calibration/validation groups.

The primary [dataset metadata](https://www.research-collection.ethz.ch/handle/20.500.11850/731659)
identifies CC BY 4.0 and links supplement DOI `10.3929/ethz-c-000789665`.
The dataset landing request timed out; the supplement received a non-retryable
browsing-tool rejection and was not retried. Metadata was available through the
primary repository's search record. No raw files or file-specific terms were
verified. The [structured review](eth-reversed-axial-source-review-20260914.json)
retains these access and admission states.

## Next admissible work

This separates two engineering questions. The current public fiber profile
explicitly excludes bond slip (`materials/stateful_fiber_section.py`); the
repository's separate connector modules do not establish this campaign's
member-level validation. RC member curves therefore remain held for mechanism
and boundary reconstruction.

For a future uniaxial material comparison, first obtain the original CW test
files, sensor units, area convention, gauge length, sign and complete cyclic
history. Compare the current `BilinearCombinedHardeningSteel` against the
recorded stress–strain paths before changing or fitting a material model.
Do not use nominal paper strengths as fabricated sample histories.

Freeze specimen assignments before calibration and keep all campaign-derived
material/member observations linked. Within-campaign holdouts can diagnose
history transfer but cannot establish independent-project generalization.
Retain QST exclusions and the original measured-versus-inferred distinction
through any later importer. A broader material model should be justified by
actual residuals on admissible data, not by replacing the current model solely
to match a published model's name.

Current result: a newly classified material-data lead, zero raw acquisition,
zero admitted rows, zero fits and zero new solver calls. No independent
physical acceptance, learned benefit or roadmap closure is claimed.
