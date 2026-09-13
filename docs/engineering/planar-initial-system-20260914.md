# Initial planar system and production increment reconstruction

Frozen source `5606dac91151fc193a8f5376d592ee799837d689` and all 461 source identities were
verified. The original 48-equation four-story model was assembled twice from
its initial checkpoint at load factor 0.25, once through each assembly backend.
Original first-step residual arrays match both reconstructed residuals exactly.

## Discriminating results

The initial matrices differ at four entries. The largest absolute difference is
4.656612873077393e-10 kN/m, at two approximately 4.022e6 diagonal entries (one
float64 spacing). Two small off-diagonal entries are 1.4551915228366852e-11 versus
1.2732925824820995e-11. Dense indexed accumulation and sparse COO duplicate
aggregation have different arithmetic paths; the present check establishes the
matrix differences, not a unique member-level summation cause.

Both saved first Newton increments reproduce **exactly** through the original
`_solve_vector_increment` functions using their corresponding assembled matrices.
The sparse backend label routes to the project's checked SuperLU factorization;
a preliminary direct SciPy `spsolve` call did not reproduce it and is retained
only as an exploratory probe, not the production-path conclusion.

Crossed calculations also differ: sparse solving the dense matrix differs from
the saved dense increment by 2.1033522146218786e-17, and dense solving the sparse
matrix differs from the saved sparse increment by 1.0299920638612292e-17 in the
stored coordinate infinity norm. Thus matrix assembly identity alone would not
force identical increments across these factorization paths.

An 80-digit solve of the reconstructed **dense float64 matrix** provides a
numerical reference for that matrix only. Saved dense and sparse increments
differ from its rounded solution by 1.691355389077387e-17 and
1.5395670849294163e-17, respectively. Against the dense system, computed normwise
backward errors are 3.3528962026518044e-17 and 1.3411584810607555e-16. These
float64 residual diagnostics have their own rounding; they do not rank physical
accuracy or provide a whole-path error bound. Sparse's native diagnostic passes
with backward error 6.720942987132467e-17 and no regularization or fallback.

The dense infinity-norm condition number is approximately 3243.9244. The check
uses two assemblies, four production-path linear solves and one high-precision
linear solve; no full nonlinear path was rerun. The original terminal stress
comparison remains failed, with no tolerance change or qualified paired speed
claim. A solver change is not justified solely by these small, reproduced
initial differences.

## Evidence

Production-path packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-planar-initial-system-production-edsjg60y`.
Inventory SHA-256: `3bc5d7f8bf6e17f0198c21914b39694969fb337179094c78d7ee0d27879d13c9`.
It retains both matrices, residual, saved increments and crossed solutions.
The earlier direct-SciPy probe is separately preserved at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-planar-initial-system-aqztivfn`.

Independent physical validation, total learned benefit and the full roadmap
remain open. This diagnosis does not promote either backend or resolve the
failed four-story history comparison.
