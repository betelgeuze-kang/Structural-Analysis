# Phase 2 cantilever elastica large-rotation benchmark

This bounded verification slice adds the previously missing continuum
cantilever large-rotation case. It does not validate the repository's
production beam/frame path and does not close the broader geometric-nonlinear
benchmark gate.

## Continuum reference

The problem is an initially horizontal, inextensible planar Euler--Bernoulli
cantilever of length `L` and flexural rigidity `EI`. The root is clamped and a
vertical conservative dead load `P` acts at the free tip. Arc length is
`t = s/L`, rotation `beta` and transverse coordinate are positive downward, and
the nondimensional load is `alpha = P L^2 / EI`.

The stationary potential gives

```text
beta''(t) + alpha cos(beta(t)) = 0,
beta(0) = 0,
beta'(1) = 0.
```

On the principal branch, the first integral is

```text
0.5 beta'(t)^2 + alpha sin(beta(t)) = alpha sin(beta_tip).
```

The implementation solves the resulting unit-length integral for `beta_tip`
with a bracketed scalar root and evaluates `x/L` and downward `y/L` by adaptive
quadrature. The substitution `beta = beta_tip - z^2` removes the square-root
endpoint singularity. This is independent of the discrete Newton solve.

The governing elastica and terminal-load solution family follow the classical
large-deflection cantilever treatment of
[Bisshopp and Drucker (1945)](https://doi.org/10.1090/qam/13360) and the exact
terminal-load formulation catalogued by
[Batista (2013)](https://arxiv.org/abs/1303.6490). A more recent independent
elliptic-integral treatment of clamped beams under concentrated terminal loads
is given by
[An, Xie, and Yang (2021)](https://doi.org/10.13700/j.bh.1001-5965.2020.0186).

At `alpha = 4`, the reference result is deliberately outside the small-rotation
regime:

```text
beta_tip = 1.1212393474875764 rad
x_tip/L  = 0.6710587577531542
y_tip/L  = 0.6699641812776667  (downward)
```

The linear small-rotation prediction would be `y_tip/L = alpha/3 = 4/3`, which
is physically incompatible with an inextensible unit-length centerline and is
about twice the nonlinear result.

## Independent discrete solve

The numerical side uses a piecewise-linear nodal rotation field, fixes only the
root rotation, and integrates the following nondimensional potential with two
Gauss points per element:

```text
Pi = 0.5 integral(beta'(t)^2 dt) - alpha integral(sin(beta(t)) dt).
```

The assembled residual is the exact gradient of this energy and the symmetric
Newton tangent is its exact Hessian. Central differences check both identities
at a non-equilibrium rotation field. The solver starts from zero rotation,
advances through 16 load increments, and uses the previous accepted state only;
the continuum reference never seeds the solve. No tangent regularization or
fallback path is present.

Meshes with 8, 16, 32, and 64 elements must converge monotonically to the
continuum tip rotation and both tip coordinates. All three measures must show
at least 1.9 observed order, and the finest absolute error must stay below
`5e-5`.

Run the focused verification with:

```bash
PYTHONPATH=src python3 -m pytest -q \
  tests/test_cantilever_elastica_benchmark.py \
  tests/test_geometric_nonlinear_benchmarks.py
python3 -m ruff check \
  src/structural_analysis/benchmark/cantilever_elastica.py \
  tests/test_cantilever_elastica_benchmark.py
```

## Claim boundary

Passing this receipt supports one claim only: the bounded continuum cantilever
large-rotation benchmark agrees with an independently discretized
energy-consistent rotation solve and exhibits the expected mesh convergence.

It does **not** validate a production corotational beam, general 2D/3D
frame/shell geometric stiffness, Lee-frame snap-through, material--geometric
coupling, sparse or ROCm/HIP execution, or G1 closure. Those remain explicit
open gaps.
