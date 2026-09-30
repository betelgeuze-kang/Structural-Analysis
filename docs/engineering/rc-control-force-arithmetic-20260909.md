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

## Completed source-bound saved-force observations

Frozen diagnostic `6e0dfeb65bebcf8b6e7380f6c3de760ac5810796` verifies four
complete original reference/secant pairs: both geometries under binary64
exact-strain and native twofold increments. There are 1,936 original step-force
replays and 14,520 selected force-component comparisons. All original inputs
match their earlier sealed inventories. All ordered decompositions close exactly
before serialization. Four model compilations are performed; instrumented
material/element/Newton entry points confirm zero calls, and no states commit.

The counts below cover six local force components per member and the fixed
support reactions. They exclude other history fields and are not full-analysis
acceptance verdicts. Each cell shows member-force / reaction mismatches.

| Source profile / geometry | Original | Exact stored coefficients | Exact geometry coefficients | Exact stored-stress section sums |
| --- | --- | --- | --- | --- |
| binary64 exact-strain / base | 964 / 102 | 975 / 107 | 975 / 107 | 961 / 103 |
| binary64 exact-strain / long | 965 / 108 | 973 / 112 | 973 / 112 | 966 / 109 |
| twofold increments / base | 233 / 105 | 236 / 107 | 236 / 107 | 226 / 101 |
| twofold increments / long | 179 / 82 | 181 / 84 | 181 / 84 | 204 / 96 |

None of these post-processing counterfactuals eliminates the force failures.
New failures are visible: exact stored-stress section sums increase the longer
twofold case from 261 to 300 selected force mismatches. This does not predict a
future integrated solver's behavior, since these inputs satisfy the original
arithmetic's equilibrium/commit gates, not a different solver's equations.

Among the latest twofold source's 599 originally failing selected force values,
the retained-stress/load term is uniquely largest in absolute magnitude at 590;
section-resultant rounding is largest at nine. For the preceding binary64
source the corresponding counts are 2,136 and three among 2,139 failures.
These are results of the explicit stage order, not unique physical causality.
In the latest twofold failed fields, maximum geometry-coefficient contributions
are below 3.5e-26 SI, whereas maximum retained-stress/load contributions reach
7.409120441393755e-10 (base) and 4.628063690383562e-10 (long). Isolating B-coefficient
or final force accumulation rounding is therefore insufficient to explain most
of these original differences.

A separate read-only review of the already completed original-parent section
diagnostics retains an important distinction. Zero material-parent contribution
was previously established for the isolated failing **M2 section moments**.
Across all stored M1 axial-force field/order pairs, parent-history contributions
are nonzero in 948 pairs (base) and 665 (long), with maxima 6.984919309616089e-10 N
and 4.656612873077393e-10 N. Finite-coordinate contributions are also nonzero in
1,062 / 979 such pairs. These counts include all section rows, not only failed
end forces; they are not an end-force decomposition. No new material integration
was required to inspect that existing evidence. The zero-parent M2 result must
not be generalized to M1 or the whole frame.

The next precision investigation must distinguish finite trial strain from
persistent material-history precision before changing original trial, commit or
recovery arithmetic. Neither a new equilibrium solve nor numerical repair,
accepted acceleration, learned-policy improvement, independent physical
validation or release closure is established here.

The new evidence root is
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-force-arithmetic.sx1c4yjz`.
Its 435 files / 26,217,515 bytes are inventoried and reread/hash-checked; inventory
SHA-256 `e85b4f3bfe02567f7813081a4960a8747a92aa8977050d308558979399418059`.
The [machine-readable results](rc-control-force-arithmetic-20260909.summary.json)
preserve complete stage counts, maxima, work, source/input bindings and limits.
Prior sealed evidence remains unchanged. The full roadmap and independent,
licensing, hardware, owner, hosted/full-suite and R1/R2 requirements remain open.
