# Steel history exceeds the exploratory refinement screen

This read-only audit extends the [local section comparison](planar-local-refinement-20260914.md)
using the same original 8/16/32-layer paths. Original path hashes and input hashes
are checked. The source input section geometry, steel arrangement and material
arrays agree across grids; only concrete layer count differs. The two outer
steel layers therefore have corresponding physical positions and areas.

Each element trial state is matched exactly to its accepted checkpoint state,
each section trial state to the accepted integration-point state, and each fiber
response trial state to the accepted fiber state. Steel comparison keys are
member ID, integration index and bottom/top layer. All 36 steel positions per
target are retained. Concrete fibers occupy different coordinates and are not
matched by index across grids.

At factors 0.25 and 0.5, all three models have zero accumulated steel plastic
strain. At factor 0.75, each has **five yielded members and nine yielded steel
positions**. Recounting the original responses agrees with the recorded member
counts. Maximum accumulated plastic strains are 0.00150047, 0.00145212 and
0.00143249 for 8/16/32 layers. This confirms yielded-steel execution coverage
in this generated prefix, not independent experimental validation.

Using the same exploratory 1% group-infinity refinement rule:

| At load factor 0.75 | 8 → 16 difference % | 16 → 32 difference % |
| --- | ---: | ---: |
| Plastic strain | 3.640713 | 1.591822 |
| Accumulated plastic strain | 3.640713 | 1.591822 |
| Backstress | 3.640713 | 1.591822 |
| Dissipated energy density | 3.640713 | 1.591822 |
| Steel stress | 2.084281 | 0.852468 |

The normalizers, absolute differences and worst-location witnesses are retained.
These are group norms, not bounds on every small pointwise relative error. The
16-to-32 stress difference meets the exploratory screen while its internal steel
history variables do not. Thus the earlier sub-1% nodal/generalized-section
observations cannot be extended to material-history convergence.

Concrete tensile and compressive damage are also nonzero at factor 0.75. The
32-layer model has recorded maxima about 0.999995 and 0.555710 respectively.
Those are model state variables, not physical safety/capacity factors. Because
concrete sample positions differ, the audit reports populations without treating
differences between maxima as pointwise refinement error.

No new solve, assembly or fit is performed. The
[machine summary](planar-steel-refinement-20260914.summary.json) links full matched
steel histories and the reproducible audit at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-planar-steel-refinement-isvp9gez`.
Inventory: two files / 108,783 bytes, SHA-256
`d2b4f593459859427696f32aaa09c716bbb8b101592af9012702e38020207b98`.
Complete-path, concrete history, member/integration refinement and independent
validation remain open. This finding does not justify loosening the screen or
promoting a coarse model for learned-performance claims.
