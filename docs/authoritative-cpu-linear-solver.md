# Authoritative CPU Linear Solver v1

This path is the single public linear-static implementation used by the Python API,
the `structural-analysis` CLI, and the embedded viewer payload.

## Solver path

`CanonicalModel -> analyses.linear_static -> assembly.linear_static -> solvers.linear.static -> AnalysisResult`

- Solver ID: `authoritative_cpu_linear_fea_3d_v1`
- Degrees of freedom: `UX, UY, UZ, RX, RY, RZ`
- Elements: 3D axial/truss and 3D Euler-Bernoulli frame/beam/column
- Backends: dense NumPy and sparse SciPy CPU
- Residual: `R(u) = K u - F`
- Viewer source: `result.metrics.viewer_payload`

The legacy MGT full-frame runner imports the shared frame local stiffness,
orientation, transformation, and rigid-offset kernels from
`structural_analysis.elements.frame3d`; it no longer owns duplicate copies.

## Fail-closed production policy

The public solver does not create engineering properties or boundary conditions.
Frame elements require explicit:

- material `elastic_modulus` and `poisson_ratio`;
- section `area`, `iy`, `iz`, and `torsional_constant`;
- nodal supports and nodal loads;
- canonical `m` and `kN` units.

Missing data, unsupported elements, inactive loaded DOFs, singular mechanisms, and
unknown load cases produce a blocked result. No stiffness regularization, synthetic
section, automatic base restraint, implicit density, or CPU/GPU fallback is used.

## Claim boundary

This is a deterministic CPU reference path for linear frame/truss analysis. It does
not claim Timoshenko shear deformation, warping torsion, shell coupling, geometric
nonlinearity, material nonlinearity, construction stages, dynamics, or design-code
closure. Those capabilities must remain unsupported until connected to the same
canonical model and result path with focused verification.
