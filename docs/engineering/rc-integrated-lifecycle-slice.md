# RC pin/roller, explicit-layer and backup integration

This integration candidate combines the source from PRs #573, #575, #577 and
#579 and adds a combined lifecycle test. Those independent PRs retain their
own hosted and review gates. This candidate must not merge ahead of them; after
their main merges its remaining diff and exact-head gates must be rechecked.

The new synthetic browser profile uses an explicit pin/roller beam with three
steel layers, including two distinct steel laws. The browser submits the actual
request. A child worker performs calculation and verification, then is killed
at the interrupted reservation boundary. The private test driver stops the
original HTTP process, seals and verifies a supported backup, and restores it
into a new runtime directory. A new HTTP process and fresh worker resume the
saved checkpoint. Two declared-price report revisions and another cold
HTTP/browser reopen must preserve the numerical state and downloaded bytes.
The original store must remain unchanged after activation of the recovered
store. The expected longitudinal steel quantity is 17.898 kg for this authored
input, not a measurement from a public specimen.

The first combined browser run failed after backup/restore because the fixture
allowed only a direct temporary-root runtime. The fixture now permits the
specific recovered-runtime child for HTTP and worker modes, while keeping the
driver at the original root and rejecting arbitrary/nondisposable paths. This
is a test-harness repair; it does not relax production store activation checks.
Initial failed-run evidence is retained separately from the corrected run.

The backend counterpart covers backup during a checkpoint, original-worker
termination, recovery into a new store, resumed numerical work, terminal-result
backup, report reopen, immutable original request and the same steel quantity.
The interrupted invocation remains unknown and consumes its reserved budget:
five reservations, with ordinal 3 not reported as completed or refunded.

This does not provide automatic fencing of independent original/copied stores.
Stopping original writers is an explicit operator responsibility, and the
backup receipt continues to report original_writers_fenced=false. Descendant
resource containment, public-source specimen input admission, physical
validation, overall performance gains and release readiness remain separate
open conditions. Authored UI and solver evidence does not close those gates.
