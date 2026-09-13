# Upstream reconstruction of the planar stress witness

Using the repeated experiment's frozen source `5606dac91151fc193a8f5376d592ee799837d689`,
all 461 source-file identities and the original model identity were verified.
Two original result/history pairs (one per backend) were checked against their
retained SHA-256 and lengths. No new nonlinear or linear solve was run.

The original E13 node displacements reconstruct basic corotational deformations,
local beam displacements and midpoint axial strain/curvature exactly at all four
accepted steps for both backends (eight section states). This excludes a separate
history-export transformation as the source of this witness mismatch.

The two saved Newton traces contain 13 rows each. Load step, iteration,
line-search alpha, attempt count, accepted/committed labels and both gate flags
match row by row. Their first initial displacement and residual arrays are
byte-value equal, but their first Newton increments already differ by
3.209238430557093e-17 in the stored free-coordinate infinity norm. Subsequent
states and residuals diverge slightly while following the same observed branch
and iteration schedule. Stored free coordinates include translations and scaled
rotations; this norm is not a physical displacement error bound.

This narrows the first observable divergence to the initial linear-increment
calculation or its inputs not retained in the public trace. It does not prove
identical tangent matrices, identify either backend as more accurate, or establish
a backward-error bound. The next discriminating check is to reconstruct the same
initial system for both backends, compare matrix/residual identities, and assess
the original increments against that system before proposing a solver change.

The prior terminal stress comparison remains failed. Its paired timing metrics
remain unavailable. No comparison tolerance, solver default, training admission,
independent physical acceptance or roadmap gate is changed.

Packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-planar-newton-origin-mnop74bf`.
Inventory SHA-256: `740632214df2ffe43f475131790e6ed9019234ec6876aa3380c5776198fe514b`.
