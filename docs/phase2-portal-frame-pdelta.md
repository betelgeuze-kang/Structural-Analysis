# Phase 2 portal-frame P-Delta tangent benchmark

This Level 1 analytic slice verifies a gravity-prestressed, three-member portal
frame. It closes the gap between the repository's existing single-column modal
amplification identity and an assembled frame with two columns, a flexible
beam, six free joint degrees of freedom, axial shortening, and a coupled sway
mode. It remains deliberately narrower than a production second-order frame
analysis.

The terminology follows the distinction used by the official
[OpenSees P-Delta transformation documentation](https://opensees.github.io/OpenSeesDocumentation/user/manual/model/geomTransf/PDelta.html),
which describes a geometric transformation that includes second-order P-Delta
effects. That page is context only; all numerical truth in this receipt comes
from the closed-form reduction below.

## Frame definition

The one-bay, one-story elastic frame has:

- fixed bases and rigid beam-column joints;
- story height `L = 3 m` and bay width `B = 5 m`;
- `E = 200,000 MPa`;
- column `A_c = 0.2 m^2` and `I_c = 8e-5 m^4`;
- beam `A_b = 0.2 m^2` and `I_b = 1.6e-4 m^4`; and
- equal downward gravity loads `P/2` applied at the two top joints before a
  symmetric unit lateral-load tangent probe.

The large column area keeps axial shortening small so the benchmark isolates
the elastic stability calculation. It is a mathematical elastic verification
case and makes no material-strength or design-capacity claim.

Both columns and the beam use the same energy-consistent corotational
Euler--Bernoulli element introduced for the Lee-frame benchmark. The six free
physical degrees of freedom are both top joints' `ux`, `uy`, and rotation.

## Independent closed-form reduction

Under gravity alone, each column shortens uniformly and the current story
height is

```text
h = L (1 - P / (2 E A_c)).
```

The symmetric sway perturbation is represented by three generalized
coordinates:

```text
z = [Delta, eta, theta]
```

`Delta` is the common top-joint sway, `eta` is upward at the left joint and
downward at the right joint, and `theta` is the common joint rotation. Direct
differentiation of member energies gives

```text
        [ a  0  b ]
K_sym = [ 0  e  d ]
        [ b  d  c ]

a = 24 E I_c / (L h^2) - P / h
b = 12 E I_c / (L h)
c = 8 E I_c / L + 12 E I_b / B
d = 24 E I_b / B^2
e = 2 E A_c / L + 48 E I_b / B^3.
```

The `-P/h` term is the destabilizing story P-Delta contribution. Static
condensation of `eta` and `theta` yields the independent effective story
stiffness

```text
k_story(P) = a - b^2 / (c - d^2/e).
```

The analytic critical gravity load is the first positive root of
`k_story(P) = 0`, and the infinitesimal lateral amplification is
`k_story(0) / k_story(P)`.

Independently, the implementation assembles all three elements in the global
six-DOF basis, evaluates the exact total-potential Hessian at the gravity
equilibrium, transforms that Hessian into the symmetric coordinates, and
performs the same condensation. The analytic matrix never seeds or replaces
an assembled term.

## Fixed receipt result

The analytic and assembled critical total gravity loads are respectively
`31,246.914946939 kN` and `31,246.914946935 kN`, a relative difference of
`1.17e-13`.

| Critical-load ratio | Assembled lateral amplification |
| ---: | ---: |
| `0.00` | `1.0000000000` |
| `0.25` | `1.3332031887` |
| `0.50` | `1.9996095662` |
| `0.75` | `3.9988286985` |
| `0.90` | `9.9964860956` |
| `0.95` | `19.9925817574` |

The slight difference from exactly `1/(1-P/Pcr)` is expected because the
closed form retains the gravity-induced change from `L` to `h` instead of
freezing the original height.

The fixed verification gates are:

| Check | Result | Contract |
| --- | ---: | ---: |
| Critical-load relative error | `1.169e-13` | at most `1e-10` |
| Maximum analytic/assembled tangent error | `6.143e-17` | at most `1e-11` |
| Maximum effective-stiffness error | `3.151e-12` | at most `1e-10` |
| Maximum amplification error | `3.151e-12` | at most `1e-10` |
| Maximum gravity equilibrium residual | `2.423e-9 kN` | at most `1e-7 kN` |
| Energy-gradient finite-difference error | `1.491e-9` | at most `1e-7` |
| Tangent-Hessian finite-difference error | `2.027e-9` | at most `1e-7` |
| Tangent symmetry error | `0` | at most `1e-12` |

No regularization or fallback is present.

Run the focused verification with:

```bash
PYTHONPATH=src python3 -W error -m pytest -q \
  tests/test_portal_frame_pdelta_benchmark.py \
  tests/test_lee_frame_snapthrough_benchmark.py \
  tests/test_geometric_nonlinear_benchmarks.py
python3 -m ruff check \
  src/structural_analysis/benchmark/portal_frame_pdelta.py \
  tests/test_portal_frame_pdelta_benchmark.py
```

## Claim boundary

Passing this receipt supports one bounded claim: the gravity-prestressed
symmetric sway tangent, critical load, and lateral amplification of this
elastic three-member planar portal agree with the independent closed-form
reduction.

It does **not** validate a finite-displacement portal load path, member
`P-small-delta` stability functions, the legacy corotational proxy, a general
2D/3D production frame or shell, material--geometric coupling, sparse or
ROCm/HIP execution, full-building equilibrium, or G1 closure. Those remain
explicit blockers in the machine-readable receipt.
