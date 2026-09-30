# Trace the yielded-prefix M2 force witness through stored operands

This audit reads the sealed failed study from source
`22977c86fde3422666a9c38da06ca036f9e29352`. All imported frozen Python sources
and consumed original step files were length/hash checked against the packet's
inventory. No solver, training or additional full path was executed.

For all 16 reference and 16 secant steps, the frozen element's strain matrix
times the stored M2 local coordinates exactly reproduces the stored generalized
strains. Accumulating the stored section resultants through that same matrix
and the original quadrature weights exactly reproduces all six local member
forces. This replays kinematics and force assembly, not constitutive response
integration or the Newton solve that produced the coordinates.

At step `002-1`, the M2 end rotations are both
`-0.0008562435647451532` radians in the reference and
`-0.0008562435647451533` in secant. The reference's three curvatures are
`[-2.168404344971009e-19, 0, 3.2526065174565133e-19]` per metre; secant stores
three zeros. Both have the same stored generalized axial strain. Section
moments in the reference are approximately `[-5.507e-14, 0, 8.138e-14]` kN m;
secant stores zeros. Their assembled end-i shear is respectively
`1.1743437167116976e-13` kN and zero. The ordinary kN-to-N conversion therefore
reproduces the previously reported comparison witness.

An 80-digit Decimal dot product using the exact binary64 matrix coefficients
and coordinates produces nonzero end curvatures in both strategies:
reference approximately `[-2.012e-19, 0, 2.012e-19]`, secant
`[1.207e-19, 0, -1.207e-19]`. Thus the stored operands already differ and
binary64 dot-product rounding affects the near-zero observation. This is not
an exact-real beam solution: matrix coefficients and coordinates are still
the original rounded operands. In particular, a displayed zero does not prove
that a strategy is more physically accurate.

M2 has zero yielded and damaged integration points at this witness. This
does not classify every member or every later step as elastic. It also does
not explain all 67 mismatch locations or establish why Newton accepted the
slightly different coordinates. No clipping, tolerance change, material patch,
or successful comparison promotion follows from this audit. Paired reuse
cost remains unavailable.

The audit script and JSON are read-only at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-yielded-force-origin-ddpy6k43`.
External inventory SHA-256:
`e5db50901b7972a34c833873b50489b606cf2d2c851583b9a0f0041403a2793b`.
The next diagnostic boundary is the accepted-coordinate/Newton history,
before proposing any numerical implementation change.
