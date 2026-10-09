# Nonlinear layered pin/roller control-path matrix

This test slice uses the authored three-layer mixed-steel section and pin/roller
beam from the pending RC integration stack. It exercises actual concrete damage,
unloading, sign reversal, material history, exact restart replay, and real Newton
failure. It does not validate a measured specimen or change a solver default.

Two explicitly distinct material cases are retained:

- The unchanged authored example steel laws (250 and 404 MPa yield stresses).
  The tested history develops concrete damage but no steel plastic strain.
- A deliberately synthetic early-yield variant (4 and 8 MPa), used to exercise
  both steel return-mapping laws, cumulative plastic strain and dissipation at
  these small displacements. These strengths are not plausible specimen inputs,
  experimentally inferred properties, or a calibration to a measured curve.

The history advances in 10 micrometre increments to -110 micrometres, unloads
to -50, reverses to +50 and returns to zero. A separate 5 micrometre schedule
covers increment subdivision. Irreversible material histories cannot decrease.
Splits after targets 1, 11 and 13 cover restart before yielding, after damage,
and after the positive excursion; replay must reproduce exact terminal native
state and restart bytes and count all prefix replay work.

The default policy fails on the complete authored histories. Its failure remains
an explicit regression: no failed state is committed, unattempted targets remain
visible, and a same-policy restart repeats the failed attempt after verifying
its accepted prefix. This is observed numerical nonconvergence, not a physical
capacity prediction. Earlier coarse schedules and both finer forward schedules
also failed in exploratory probes; none is presented as completed loading.

The successful arm explicitly declares up to 100 Newton iterations and 16
backtracking factors (powers of one half), rather than the default 25 iterations
and six factors. Equilibrium, increment and displacement tolerances stay equal.
The larger work budget is part of the immutable request and restart scope; it
cannot be changed silently on resume. This is neither a speedup nor a cost
reduction claim, and does not authorize relaxed convergence or hidden cutbacks.

This PR depends on #581's pending source stack. Keep it Draft until its ancestors
merge into main, then retarget main and verify the remaining exact source and
hosted/review gates. This does not close the full P2 matrix, public-source physical
mapping, resource containment, performance or release qualification requirements.
