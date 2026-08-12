# Bounded ModelIR to NDTHA Adapter v1

Status: implemented through C3 for one exact CPU profile

ABI v1.6 adds `model_ir_ndtha_adapt` at byte offset 104 of the unchanged 128-byte
`sa_api_v1` table. ABI v1.0-v1.5 tables return a null pointer in that slot and retain their
original minimum prefix sizes and capability masks. The only public library symbol remains
`sa_get_api_v1`.

## Accepted profile

`fixed_guided_frame3d_x_v1` accepts only a semantically valid, analysis-ready ModelIR with:

- exactly two nodes and one vertical global-Z Euler-Bernoulli frame3d element, ordered base to
  floor;
- one linear-elastic material and one frame3d section, with zero rotation, offsets and releases;
- one all-DOF fixed base constraint and one floor constraint fixing every DOF except global UX;
- one linear-static load pattern containing one finite nonzero floor FX load and no self-weight;
- no combinations, time functions, construction stages, roundtrip rows or unsupported features.

Selectors are bounded ASCII stable IDs. A structural, selector or readiness mismatch fails closed;
the adapter never chooses a nearby element or invents a property.

## Derivation and explicit analysis data

The C++ ModelIR owner computes:

~~~text
L = floor_z - base_z
k = 12 E Iy / L^3
m = rho A L / 2
c = 2 damping_ratio sqrt(k m)
floor_load = selected floor FX
story_axial = 0
~~~

The caller must explicitly provide damping ratio, elastic-guard yield drift, the complete NDTHA
configuration and the acceleration record. The bounded profile requires `story_count = 1` and
`pdelta_factor = 0`; it does not infer damping, yield behavior, gravity or P-delta demand from
ModelIR.

## Ownership and evidence

The request and seven packed FP64 outputs are caller-owned. Descriptors, inputs, outputs and the
result must be disjoint. Native validation and derivation run against private values and publish
outputs only after all checks succeed. The immutable handle may be adapted concurrently; destroy
returns a state conflict while an immutable call is in flight. C++ exceptions and Rust failures do
not cross the ABI.

Evidence consists of C/C++ layout checks, version negotiation, invalid/alias failure atomicity,
concurrent immutable calls, an independent Python closed-form oracle, Rust raw-layout tests, a safe
RAII wrapper and a native-fed solve compared with the existing language-neutral product input.
The tracked elastic case converges with zero plastic stories and fallback count zero.

This adapter evidence closes only C0, C1 and C3 for the exact transformation. A separate public
product slice now closes C4/C5 for the same profile by binding all three ModelIR identities, the
explicit adapter request, the generated native request and the inner native state in one canonical
checkpoint envelope. Its public `analysis model-run` and `analysis model-resume` paths are
documented in [ModelIR NDTHA Product E2E v1](modelir-ndtha-product-e2e-v1.md).

Neither promotion expands the accepted topology. Arbitrary topology, nonlinear material
reduction and P-delta derivation are unsupported. HIP CPU/device parity is C2 work and C6
decommission remains open.
