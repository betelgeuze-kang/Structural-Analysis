# Experimental parent-increment RC control with native coordinate compensation

The exact-strain observation at `d81cd8e9033024afcd4f800e63217ecc9abbe091`
removed intermediate strain evaluation error but still failed all six fixed
reference/secant comparisons. The saved original-parent diagnostic located the
remaining section-moment differences in finite accepted coordinates. This next
experiment changes the representation used during an original solve and restart.
It does not modify saved forces or relax comparison tolerances.

The explicit `coordinate_precision="twofold-increment"` profile requires
`strain_evaluation="exact-rational"`. Original vector Newton solves an increment
from the native committed parent in generalized coordinate space. Each trial
forms parent high + parent low + Newton increment using rational intermediates,
then rounds high and residual low separately to binary64. FastTwoSum normalizes
the represented sum at rounding ties, and underflowed zeros are canonical positive
zeros. Physical scaling,
member transforms and exact Hermite strain evaluation carry both components.
Zero matrix coefficients are omitted from rational products. This is a bounded,
portable coordinate experiment; Newton vectors, Jacobians, linear solves,
constitutive values, final strains, forces and load factors remain binary64.
Increment rounding, two-component rounding and material/force rounding remain.
There is no general high-precision solver or independent physical validation.

Reference initialization is the zero increment from the native parent. Secant
and other caller proposals remain binary64 absolute initial estimates and are
converted into increments relative to that parent. No proposal owns the committed
state. The original Newton implementation and configured residual/increment,
equilibrium, control, parent-binding and rollback gates remain in use. The solver's
coordinate metric records its actual increment; separate response fields record
the reconstructed absolute high and low coordinates and parent origin. Recovery
replays the original increment against the original parent, repeats native
assembly and requires identical response/checkpoint bytes. Control errors use
both coordinate components. Load-factor origin is derived from the accepted
binary64 load factor; load-factor compensation is not persistent state.

The native checkpoint uses a distinct strict schema,
`stateful-fiber-frame2d-twofold-checkpoint.v1`, with free high/low arrays and
`stateful-fiber-beam2d-twofold-state.v1` local low arrays. Canonical coordinate
expansions, both components, material states and arithmetic profile identities
are hash-bound. Native restoration validates the rounded global projection,
exact local component transforms and exact coordinate-to-section strain binding.
Missing low data, noncanonical expansions (including negative-zero components),
malformed JSON, duplicate keys and mismatched profiles fail closed. A rehashed
free low-part change still fails its binding to saved element coordinates.
There is no mutable hidden coordinate cache required for continuation.

Default `coordinate_precision="binary64"` retains its prior contract/schema and
response shape for both matrix and exact-rational strain modes. The experiment
is selected by `benchmark_rc_control_seed_paths`; public API/CLI/Workbench and
learning admission do not select it. The ordinary load-step path has no twofold
adapter and cannot execute this experimental problem profile.

The focused checks exercise sub-ULP increments, cancellation under a coordinate
transform, independent 100-digit strain evaluation with a nonzero low component,
canonical pair rejection, native hash/schema rejection, forged original solver
metrics and exact rollback, and cyclic reference/secant/fresh-reference recovery.
A fresh interpreter restores a nonzero-low checkpoint and reproduces all remaining
step results and the final native checkpoint byte-for-byte. These checks establish
bounded implementation behavior, not successful 242-target error reduction.

The full observation will retain the preceding two geometries, 242 target values,
shared terminal polishing, fixed absolute `1e-10` / relative `1e-8` comparisons,
three serial fresh processes per geometry, and all solver/proposal/recovery costs.
Source, inputs and complete original records must be frozen and audited before
reporting performance or physical comparison outcomes. Independent corpus,
physical validation, release and broader roadmap requirements remain open.
