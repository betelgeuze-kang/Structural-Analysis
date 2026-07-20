# Corotational frame 2D element kernel

This PR extracts the bounded two-node planar corotational Euler–Bernoulli
response used by the Lee/portal benchmark family.

The kernel owns only:

- current-chord kinematics;
- axial extension and end rotations relative to the chord;
- strain energy;
- exact global internal-force gradient;
- exact consistent tangent Hessian.

It does not own global assembly, constraints, continuation, material-state
commit, nonlinear result authority, design checks, release readiness, or
commercial claims.

The branch is validated against main containing the merged corotational truss
kernel, J1–J4 fiber-frame execution-state contracts, and deterministic concrete
damage evidence. Those systems remain independent of this element extraction.

Focused tests cover benchmark parity, energy-gradient and tangent finite
differences, rigid-body objectivity, tangent symmetry, immutable response arrays,
and fail-closed invalid inputs.
