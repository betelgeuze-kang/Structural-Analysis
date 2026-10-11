# Fixed-guided axial input integration (in progress)

The public RC workflow cannot yet accept the two-end boundary needed for the
TC11 input investigation. This branch connects the compiler, public request and durable workflow. It
does not establish a calibrated TC11 comparison.

Base: `39c75e45d60aec2496034ee6228ec2471248c70a` (PR620).

The explicit internal `experimental_fixed_guided_axial` option accepts one
straight X- or Y-aligned serial chain, one endpoint fixed in UX/UY/RZ, and the
other endpoint fixed in transverse translation and RZ. The guided endpoint is
free axially. The two experimental support profiles are mutually exclusive.
Loads on restrained components are rejected. Existing default and pin-roller
profiles retain their previous admission rules.

Focused tests cover both axes, either fixed endpoint, single and three-member
chains, independent elastic EA/L and reaction equilibrium, reversed target
paths, byte-identical split restart, changed-boundary restart rejection,
nonlinear steel plasticity and concrete damage, exact post-yield failed-step
rollback, and invalid geometry/support/load admission.

The explicit request is `bounded-rc-fiber-direct-control-request.v5` inside
`structural-analysis-job-request.v5`. Its true opt-in is required and mutually
exclusive with the pin/roller profile. Legacy requests omit the new flag and
retain their hashes. The profile is carried through compilation, source replay,
worker receipts, quantity reports and Workbench validation.

Local verification includes actual worker process death, cold service/browser
reopens, preserved abandoned execution reservation, immutable report download,
price-only revisions with zero solver calls, and damaged artifact rejection.
The browser test uses an authored synthetic vertical specimen, not TC11.

Hosted exact-source checks and integration into the final main are still
required. The local lifecycle result does not complete the user's real-project
or independently validated physical comparison conditions.

Physical conditions remain independent: TC11 fixture kinematics/compliance,
initial stress and damage, source-specific cyclic material laws, and optical
side/frame correspondence. This ideal small-displacement profile supplies none
of those missing facts. Synthetic tests do not establish TC11 or release
qualification. Do not fit these unknowns silently to measured response.
