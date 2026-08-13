# Fixed-guided deformed-shape view v1

`structural-workbench result-deformed-view` is a read-only terminal projection for the exact
`fixed_guided_frame3d_x` NDTHA adapter profile. It is available only after a durable Workbench
session reaches `terminal` or later.

```text
structural-workbench result-deformed-view --workspace SESSION \
  --projection xz --step 2 --scale 250
```

`--projection` is one of `isometric`, `xy`, `xz`, or `yz`. Without `--step`, the last completed
step is selected. The one-based step must belong to the completed ResultIR prefix. `--scale` is a
finite presentation-only magnification in `(0, 1000000]`; its default is `1000`. Neither option
changes the durable workspace or re-executes the solver.

Before rendering, the Workbench reopens and verifies every durable stage receipt and artifact
inventory. The view then:

1. strictly parses the immutable ModelIR adapter request and terminal ResultIR;
2. crosses Rust -> C ABI -> C++ again to obtain a semantically verified canonical ModelIR
   snapshot;
3. requires the exact model three-hash identity, two-node/one-frame inventory, selected element,
   vertical global-Z geometry, and `engine_v2_phase0_linear_3d` capability profile;
4. relies on the verified terminal run receipt as evidence that the C++ fixed-guided adapter
   accepted the request's base, floor, element, constraint, material, section, and load profile;
5. applies only `response.top_displacement_m[step - 1]` to the floor node in global X, while the
   fixed base remains unchanged;
6. prints the exact displacement, magnification, original and magnified coordinates, ModelIR,
   request, ResultIR, state, execution, and checkpoint identities; and
7. emits a fixed 73x25 ANSI-free original/deformed overlay followed by a SHA-256 view hash.

The YZ projection intentionally reports `Projected motion visible: false`, because global-X motion
is orthogonal to that plane. It does not invent another displacement component to make the picture
look different.

## Claim boundary

This surface is a bounded C5 inspection aid for one executed one-story profile. ResultIR v1 does
not contain a general per-node displacement field, so the view does not interpolate arbitrary
nodes, reconstruct element curvature, or claim general 3D, modal, contour, stress, animation,
engineering-acceptance, or design-code authority. The broader
`general_visual_model_editing_and_3d_result_exploration` transition blocker therefore remains open.
