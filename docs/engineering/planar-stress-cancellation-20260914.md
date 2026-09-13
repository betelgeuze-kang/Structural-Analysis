# Fixed witness diagnosis of planar backend stress mismatch

The original repeated experiment at source `5606dac91151fc193a8f5376d592ee799837d689
remains failed for the four-story cross-backend stress comparison. This audit
reads the six original history files, checks their retained SHA-256/length, and
reconstructs E13 / integration point 1 / concrete-08 at all four accepted steps.
There are 24 checked observations and no new nonlinear solves.

## What the witness establishes

The witness has zero tensile and compressive damage in every observation. Both
backends' fiber strains exactly equal the recorded section expression
`axial_strain - curvature_z_per_m * y_m`. Both stresses exactly reproduce the
material's `30000 MPa * strain`, followed by the original MPa-to-Pa conversion.
There is no missing damage factor or inconsistent stress conversion here.

At the terminal step, dense minus sparse strain is 9.158120225713495e-18.
The axial-strain contribution is 8.782037597132586e-18 and the curvature
contribution is 3.7608262858090935e-19. Axial and bending contributions nearly
cancel: the sum of their magnitudes divided by the resulting strain is about
156.864. Small upstream differences therefore have greater relative influence
on this near-zero fiber strain.

Using 80-digit Decimal arithmetic on the exact binary floating-point operands
shows zero rounding error in the terminal fiber-strain subtraction for both
backends. Replacing only that final subtraction with higher precision or
compensated summation would not remove the already different section inputs.
This observation does not isolate the upstream linear solve, geometry mapping,
or accumulated Newton path as the sole root cause.

The resulting stress difference is 2.7474359853840724e-7 Pa. The declared
comparison threshold is 2.359228606783097e-7 Pa, so the difference is
1.1645484365 times the threshold. All three repeats preserve each backend's
identical witness values. The original comparison stays failed and its paired
performance metrics stay unavailable. This is not a physical significance
assessment or authority to relax tolerances.

Next numerical investigation should compare the upstream section kinematics
and accepted Newton states; a material-law patch at this witness is not supported
by the evidence. No solver defaults, public profile, learning data or external
verification status changes in this audit.

Packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-planar-stress-cancellation-8c_ymesj`.
Inventory SHA-256: `b2b87e0e239a61a79661ee9136a40830a227040921019a90d73df214dfb89c18`.
