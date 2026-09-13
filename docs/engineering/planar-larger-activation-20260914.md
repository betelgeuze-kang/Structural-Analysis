# Larger planar frame material activation screen

Source: `3c759fc430f4a90e51bec2bdf42305a0d466032e`.

Before execution, two generated connectivities (3 stories/2 bays and 4 stories/3
bays, 27 and 48 free equations) were fixed with 12 concrete layers and ten times
the original roof-right load. All four proportional load targets, existing
solver tolerances and public model limits were retained. This is one dense
worker per case to identify material-active paths before a repeated backend
comparison. It is not a speed benchmark or independent physical validation.

Both paths completed and passed their artifact contracts. Observed accepted
histories:

- three_story_two_bay: maximum tensile damage 0.416992466905, compressive damage 0, accumulated steel plastic strain 0.
- four_story_three_bay: maximum tensile damage 0.0890741559648, compressive damage 0, accumulated steel plastic strain 0.

The audit checked all 461 frozen source files, 20 worker artifact identities,
input identities and the report manifest. Material activity comes from verified
accepted histories; these values are model state observations, not experimental
damage estimates. No learned policy or training admission was involved.

The experiment took 66.579217017 seconds, including parent
work. Individual worker times are retained in the summary, with comparison
ratios null: no repeated or cross-backend speed conclusion is available.

The next performance comparison can retain these exact two inputs and evaluate
dense and sparse backends with repeated fresh workers, full history comparison,
and all failures/costs retained. Section refinement and external physical
validation remain separate unmet requirements.

Evidence packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-planar-larger-activation-10vh3m3p`.
Inventory SHA-256: `6fc5a3430c46a8f5015cd6720ccd7b9f1699fb37449d4324ec6eae0a6c9dd44e`.
