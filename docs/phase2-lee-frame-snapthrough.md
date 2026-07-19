# Phase 2 Lee-frame snap-through and snap-back benchmark

This bounded verification slice connects an energy-consistent planar
corotational frame assembly to the existing dense vector spherical arc-length
solver. It reproduces the elastic Lee-frame limit-point path, including the
descending, negative-load, snap-back, and rehardening branches. It does not
promote the repository's legacy geometric proxy or establish a general
production frame or shell capability.

## Published reference problem

The primary comparison is Table 11 and Figure 11 of Leahu-Aluas and
Abed-Meraim, [“A proposed set of popular limit-point buckling benchmark
problems” (2011)](https://doi.org/10.12989/sem.2011.38.6.767). That paper reports
the Lee, Manuel, and Rossow (1968) elastic frame and states that its results
match the original solution. NAFEMS also catalogues the problem as
[NLGB8](https://www.nafems.org/publications/pubguide/benchmarks/Page6/).

The implemented SI-unit definition is:

- two perpendicular members, each `1.2 m` long;
- both outer ends restrained in translation and free in rotation;
- a downward `1 kN` reference load on the horizontal member, `0.24 m` from
  the rigid corner;
- `E = 72,000 MPa`, `A = 6.0e-4 m^2`, and `I = 2.0e-8 m^4`; and
- the 23 published `(horizontal displacement, downward displacement, load
  proportionality factor)` points from Table 11.

The frame uses 10 elements on each member. The mesh therefore contains 21
nodes and 59 free equations. The published samples are used only after the
solve: no reference displacement or load value seeds an iteration.

## Energy-consistent element and assembly

For each two-node planar Euler--Bernoulli element, the basic deformation vector
is

```text
v = [l - L, theta_i - (phi - phi_0), theta_j - (phi - phi_0)]
```

where `L` and `l` are the initial and current chord lengths, and `phi_0` and
`phi` are the initial and current chord angles. The total strain energy is

```text
U_e = 0.5 v^T k_b v

      [ EA/L       0       0 ]
k_b = [    0    4EI/L  2EI/L ]
      [    0    2EI/L  4EI/L ]
```

The internal force is the exact energy gradient `B^T k_b v`. The consistent
tangent is the exact Hessian,

```text
K_e = B^T k_b B + N Hessian(l) - (M_i + M_j) Hessian(phi).
```

Central differences at a deformed path checkpoint independently check both
derivative identities and tangent symmetry. Rotational solver coordinates are
scaled by the element length so every arc-length state component has metre
units; the matching congruence transformation preserves energy conjugacy and
expresses every generalized residual component in kN.

## Path-following contract and result

The dense solver uses a `0.02 m` spherical arc length, a `0.0001 m` load-factor
metric scale, a `1e-7 kN` residual tolerance, and the vertical load-point
displacement as its continuation monitor. It stops after passing `0.94 m`
downward displacement. The run accepts 335 increments with no rejected step,
tangent regularization, or fallback. Restarting from the midpoint checkpoint
reproduces the final checkpoint hash exactly.

Published points are compared to the computed displacement path by an ordered
closest projection onto successive computed segments, with the load factor
interpolated on the same segment. The current fixed-mesh receipt reports:

| Check | Result | Contract |
| --- | ---: | ---: |
| First limit load factor | `18.6586298167` | within `0.25` of `18.59` |
| Maximum displacement-path distance | `0.001852243 m` | at most `0.004 m` |
| Maximum absolute load-factor error | `0.131252987` | at most `0.35` |
| RMS load-factor error | `0.064216287` | at most `0.20` |
| Maximum equilibrium residual | `9.920843e-8 kN` | at most `1e-7 kN` |
| Maximum arc-length constraint residual | `1.273819e-11 m^2` | at most `1e-10 m^2` |
| Energy-gradient relative error | `2.637117e-9` | at most `1e-7` |
| Tangent-Hessian relative error | `5.781103e-11` | at most `2e-7` |
| Tangent-symmetry relative error | `6.734143e-17` | at most `1e-12` |

The receipt also requires explicit observation of a descending load branch, a
negative load factor, snap-back in the displacement plane, and subsequent
rehardening.

Run the focused verification with:

```bash
PYTHONPATH=src python3 -W error -m pytest -q \
  tests/test_lee_frame_snapthrough_benchmark.py \
  tests/test_cantilever_elastica_benchmark.py \
  tests/test_geometric_nonlinear_benchmarks.py \
  tests/test_nonlinear_vector_arc_length.py
python3 -m ruff check \
  src/structural_analysis/benchmark/lee_frame.py \
  tests/test_lee_frame_snapthrough_benchmark.py
```

## Claim boundary

Passing this receipt supports one bounded claim: this elastic planar
two-member Lee frame follows the published Table 11 path using an
energy-consistent corotational element and the dense CPU arc-length kernel.

It does **not** validate the legacy corotational proxy, a general 2D/3D
production frame or shell, material--geometric coupling, sparse or ROCm/HIP
execution, full-building equilibrium, or G1 closure. Those remain explicit
open gaps in both the machine-readable receipt and this document.
