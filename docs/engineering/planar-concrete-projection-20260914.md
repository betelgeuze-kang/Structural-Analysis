# Concrete-history cell projection across 64/128 layers

The previously reported 400 passing nodal/steel comparisons do not cover concrete
history at different fiber locations. This read-only audit compares the retained
64-layer path against the 128-layer prefix plus verified resumed suffix, through
all forty displacement targets. It finds substantial local differences in a
piecewise-constant cell representation, particularly near damage onset. This is
not a measured physical-error estimate or a same-point history comparison.

## Comparison definition and bindings

Source revision remains `3e2cc1dba5c6dac1b12eb1badc9b6df09337b847`. The three full
path files are hash-verified. The 128-layer restart parent must equal the prefix
final checkpoint. Canonical source input is hash-verified, with width 0.4 m and
depth 0.6 m. Each uniform 64-layer cell has area 0.00375 m2 and contains two equal-
area 128-layer cells, each 0.001875 m2. The coarse midpoint value is treated as
constant within its cell and compared to the arithmetic mean of its two fine
children. This is a deliberately explicit cell projection, not interpolation at
the same physical point or exact integration of a continuous field.

Every observation is bound to accepted element, section and fiber states. Fiber
strain is checked against the actual section axial strain and curvature at its
reconstructed midpoint coordinate. Member and integration-point coordinates and
weights must agree across discretizations. There are 18 section locations and
64 projected cells per target: 46,080 coarse-cell comparisons per field over the
forty targets.

The group infinity difference is normalized by the finer projected infinity
norm, with floor 1e-12 for history/damage/energy and 1e-9 MPa for stress. The
existing exploratory 1% screen is retained only as a diagnostic comparator.
It is not a physical or design acceptance rule. No solves or fits are performed.

## Observations

| Field | Largest projected group difference | Target | Witness |
| --- | ---: | ---: | --- |
| Tensile history strain | 0.269504% | 8 mm | E3, Gauss 0, cell 35 |
| Compressive history strain | 0.219462% | 40 mm | E6, Gauss 2, cell 9 |
| Tensile damage | 12.330094% | 74 mm | E3, Gauss 0, cell 50 |
| Compressive damage | 1.937147% | 76 mm | E3, Gauss 2, cell 7 |
| Dissipated energy density | 1.108178% | 34 mm | E2, Gauss 0, cell 10 |
| Stress | 1.698073% | 76 mm | E3, Gauss 2, cell 7 |

Seventy of the 240 target/field group comparisons exceed 1%. Cells and Gauss
indices above are zero-based. These numbers do not overturn the separate passing
nodal/steel observations; they expose an additional unverified field.

At the tensile-damage witness, the coarse midpoint damage is zero and the fine
cell average is 0.1233009440. The two fine children have damage 0.2466018881 and
zero. Their y coordinates are 0.17109375 and 0.17578125 m, with strains
0.0001236433873 and 0.0000762012758; both responses are on their tensile branch.

At the compressive-damage witness, coarse damage is zero and the fine average
is 0.0169289430. The children have damage 0.0338578861 and zero, at y=-0.23203125
and -0.22734375 m with strains -0.0010248195292 and -0.0009652163073. Both responses
are on their compression branch. The corresponding projected stress difference
is 0.5053145623 MPa, normalized by the fine group maximum 29.7581206634 MPa.

These observations are consistent with different midpoint samples straddling a
local damage-onset boundary. They do not establish a unique error mechanism,
exact continuum accuracy or convergence of the damage field. Increasing model
capacity or fitting another parameter to erase this difference is not justified
by this audit. The 64/128 nodal and steel agreement must not be promoted into a
claim that all material histories agree.

## Retained evidence

The reproducible auditor and all forty target comparisons are retained at:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-concrete-cell-refinement-3b22wbxp`

Two payload files, 133,963 bytes; inventory SHA-256:
`21a6615c53628d165ce6b5c62880be38112f7dbe5c6fe4491c9c11498b9ffc05`.
The retained script binds the three source paths to fixed SHA-256 identities,
verifies accepted states and regenerates the group comparisons. The adjacent
summary retains normalizers, absolute differences and witness cells. The fine
child details above are extracted from the same hash-verified resumed suffix.
No pointwise concrete-history validation, physical qualification, training
admission or AI performance benefit is claimed.
