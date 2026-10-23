# One-storey, one-bay RC portal workflow

The experimental corotational durable request now has an explicit
`config.experimental_portal_frame: true` profile. It reuses the existing native
portal compiler, with two fixed bases, two columns and a beam in the XY plane.
The fixed-chord cantilever and beam profiles retain their original admission.

## Author and run

Open **Submit a new RC input**, then **Start from the RC portal example**. Supply
a caller-declared source revision, load the example locally, inspect the model,
and apply it to the draft. Loading or editing does not submit a job. The shared
request is [`public_rc_portal_frame_corotational_request.json`](../examples/public_rc_portal_frame_corotational_request.json).

The bounded profile requires four rectangular corner nodes, exactly two fixed
bottom supports (UX, UY, RZ), and three native corotational RC fiber members.
Reference loads are horizontal roof FX loads. Exactly one negative fixed FY
load at each roof node supplies gravity preload; these remain present through
all lateral targets. A roof UX displacement controls the proportional reference
load factor. Weighted observations, legacy support flags, other geometries and
other load patterns are outside this profile.

The preview distinguishes fixed preload from proportional reference loads.
Coordinates, sections, reinforcement, loads and control targets remain editable
within admission bounds. To change span or height, update both corresponding
corner coordinates. Admission rejects an invalid rectangle or moved support.

Save the project to retain the complete request and job reference. Reopening a
project does not submit another job. A successful authenticated job provides the
saved corotational nodal report, deformed member chords, accepted-state history,
applied loads and support reactions. Member end forces, section and fiber
histories are not available in that report. Shape amplification changes display
only. Gravity preload and signed lateral targets retain their stored order.

## Numerical and recovery checks

The example is a 4 m span by 3 m height portal, with 1 kN downward gravity at
each roof node, a 1 kN horizontal reference at the right roof node, and UX
targets `[1e-5, -1e-5, 2e-5]` m. Its concrete section uses two midpoint layers;
the discrete elastic bending stiffness differs from a gross-section integral.

The example explicitly sets both residual tolerances to `1e-8` and the control
load-factor increment tolerance to `1e-10`; runtime defaults are unchanged.
With the stricter defaults, the preload residual stalls near `2.8e-10` while the
computed displacement correction is near `1.1e-16` m. At the first lateral
target the load-factor correction also exceeds the default `1e-12` threshold
despite a displacement correction near coordinate resolution. The example's
settings are retained in its request and continuation identity; the solver does
not silently relax tolerances, regularize the matrix or replace failed targets.

The independent test assembles an Euler–Bernoulli frame stiffness matrix from
the authored dimensions, material moduli and discrete fiber geometry, without
using production element or assembly routines. It compares the elastic-range
nodal solution, reactions and load factors, and checks force/moment equilibrium.
The reference uses the standard [Euler–Bernoulli beam formulation](https://teachbooks.tudelft.nl/computational-modelling/structural_linear/euler_bernouilli.html).
This is an independently implemented elastic-limit software comparison; it is
not independent-operator validation, nonlinear specimen validation or design
qualification.

Backend tests compare uninterrupted and serialized continuation, and cover the
v6 request plus the isolated v7 request. The separate actual HTTP/browser test
authors and submits the shared request, commits a checkpoint, kills the waiting
worker, restarts HTTP and the browser, restores the project, and completes the
same job with a fresh worker. The interruption is after a committed chunk, not
inside a solver iteration. Report and visualization reads must leave numerical
state unchanged and execute zero numerical calls.

These checks cover this bounded development workflow. They do not establish
nonlinear cyclic accuracy, arbitrary portal sizing convergence, a complete
commercial frame product, or physical/release qualification.
