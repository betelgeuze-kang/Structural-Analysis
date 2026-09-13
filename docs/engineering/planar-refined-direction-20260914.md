# Refined planar Newton direction and one-extra-alpha probe

This diagnostic follows the 32/64-layer full-path failures. It uses frozen source
`3e2cc1dba5c6dac1b12eb1badc9b6df09337b847`, verifies the preserved source/input
hashes, and executes the original 32-layer four-target path with an observational
line-search wrapper. The wrapper returns the original answer unchanged. The
complete returned path exactly reproduces the prior preserved 32-layer path.

At the failed factor-1 Newton iterate, reassembled residuals exactly equal those
observed by the original line search. The relative infinity-norm linear equation
error `||K d + r|| / ||r||` is 9.6761523e-14. Central directional finite difference
errors relative to `K d` are 6.1119753e-7 at h=1e-4 and 2.5940013e-7 at h=1e-5.
At smaller h the errors increase (1.6740441e-6 and 1.1661203e-5), consistent with
finite-difference sensitivity. These are directional checks at one failed state,
not independent verification of every tangent entry or material branch.

All eleven post-run trial alphas from 1/64 through 1/65536 reduce the original
residual infinity norm. At 1/64 it changes from 165.957141811 to 164.122737787,
a ratio of 0.988946520. None of these diagnostic trials was admitted as a solution.
Twenty-one diagnostic assemblies took 3.970471 s, separate from the captured
full-path execution's 13.571836 s. Reassembling the original coordinates afterward
reproduces both residual and tangent exactly; all retained checkpoint bytes are
unchanged.

The findings provide no evidence that an inaccurate linear solve causes this
particular rejection. They motivate testing whether the first smaller step helps
complete the path, rather than assuming local residual reduction is sufficient.

## Prespecified seven-alpha full path

A separate fresh run added only alpha=1/64 to the existing six factors. It kept
32 layers, targets 0.25/0.5/0.75/1.0, dense solution, residual tolerance 1e-10,
increment tolerance 1e-12 and maximum 40 iterations. No public default changed.
This is one diagnostic alternative, not a parameter sweep or a selected policy.

The first three accepted steps exactly reproduce the baseline. At factor 1,
accepted Newton alphas are 1 and 1/64, followed by rejection of all seven alphas.
The final relative residual is 0.109415159, versus the baseline 0.110638095.
Both remain `line_search_failed_to_reduce_residual`, with three committed targets
and exact rollback to factor 0.75. The extended run has 28 convergence-history
rows and 45 line-search attempts versus baseline 27 and 37. Its single observed
path time is 14.987752 s. Failed speed ratios remain null.

Thus one smaller step produces local progress but does not complete the refined
path. This does not prove that no continuation strategy can succeed or establish
physical capacity. It does not justify changing defaults, relaxing tolerances or
training on failed trial states as accepted solutions. A subsequent investigation
must evaluate complete paths and preserve material history, including any costs
and path changes introduced by a different continuation strategy.

## Reproduction and artifacts

Both packets retain the runnable scripts, pre-run protocols, full paths and
numeric observations. The first includes the full tangent/direction and every
perturbation response; the second includes an auditor verifying baseline prefix
identity and exact rollback. Runners create fresh directories and verify/import
the retained frozen source. No structural solver source was edited.

Direction packet (5 payload files, 20,676,290 bytes):
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-planar-refined-direction-ldrresjl`

Inventory SHA-256:
`eb93bacd94f5670baa6720a62327a014778d75e71ca1abe2cad7b3a30078e299`.

Seven-alpha packet (6 payload files, 20,658,358 bytes):
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-planar-refined-seven-alpha-mf8lniht`

Inventory SHA-256:
`061a061245a591a6435d2af2c18afe55be05f8d51ba29082ef45e71f89cff1eb`.

Adjacent machine-readable summaries retain exact observations. No training,
physical qualification, full-path completion or AI speedup is claimed.
