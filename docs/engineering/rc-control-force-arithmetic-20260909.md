# Original RC force arithmetic attribution

The native twofold observation completes all original paths but still fails the
fixed physical comparisons: 339 / 262 differences per geometry repeat. Only one
section moment fails in each first pair, whereas member-end forces and reactions
retain many failures. The next diagnostic follows these forces from the original
stored fiber stresses through section, element and global assembly.

`scripts/diagnose_rc_control_force_error.py` first verifies original path hashes,
step hashes using their signed-zero-normalizing contract, step-to-history binding,
model/arithmetic identities, quadrature, fiber stress projections, sequential
binary64 section resultants, member local/global forces, global force assembly,
external loads, reactions and SI force projections. Every original file is hashed
before and after reading. Changed arithmetic is rejected even when step and path
hashes have been recomputed. This is selected force replay; material state history
and equilibrium are not independently solved by this tool.

The ordered counterfactual stages retain the original finite inputs:

1. Original binary64 forces and SI projections.
2. Exact products, sums, global transformations and SI conversion using stored
   binary64 section resultants and the original rounded B coefficients and
   quadrature factors.
3. Exact rational Hermite coefficients and quadrature factors of the original
   finite member length, integration points and weights, retaining stored section
   resultants.
4. Exact section sums of original finite fiber stresses, areas and ordinates,
   followed by the preceding exact element/global operations. Original finite
   load factors remain in reaction calculations.

The candidate-minus-reference difference is decomposed into three adjacent-stage
changes and the remaining stored-stress/load difference. The sum closes exactly
as rational numbers before serialization; individual reported components are
rounded to binary64. The stage order is explicit and does not prove unique causal
attribution. Each stage reports force mismatch counts across every selected force
component using the same fixed absolute/relative tolerances; new counterfactual
failures are retained as well as original failures.

Counterfactual forces are not replacement outputs or equilibrium solutions.
They do not predict the result of a future solver that incorporates a different
arithmetic profile during all trials and recovery. There is no force snapping,
material integration, Newton solve, accepted state commit, tolerance change,
public API/Workbench change or release approval in this diagnostic.

The initial ten tests include independent 100-digit geometry coefficients,
exact telescoping attribution with opposing contributions, real cyclic force
replay with material/Newton entry points forbidden, six rehashed tampering
cases, and rejecting output inside the original study before work. The related
neighborhood passes 97 tests in 10.89 seconds; Ruff and diff checks pass. Complete
saved 242-target observations and source-bound results are recorded separately.
