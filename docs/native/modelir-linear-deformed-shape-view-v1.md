# ModelIR linear deformed-shape view v1

`structural-workbench result-deformed-view` is a bounded read-only C5 projection for a verified
`model_ir_linear_cpu_v1` durable workspace at terminal or later:

```text
structural-workbench result-deformed-view --workspace <DIR> \
  [--locale <en-US|ko-KR>] [--projection <isometric|xy|xz|yz>] \
  [--step 1] [--scale <F64>]
```

The same command remains byte-compatible with the legacy fixed-guided NDTHA selected-step view.
For a linear-static workspace there is exactly one terminal state, so an omitted step or `--step 1`
is accepted and every other step fails with `workbench_deformed_view_step_invalid`.

The linear surface:

1. re-verifies the terminal receipt, sparse ResultIR and typed global/element recovery ResultIR;
2. strictly reparses the immutable ModelIR and independently revalidates it through the native C++
   semantic boundary;
3. requires exact model content, semantic and provenance identities plus case/result/recovery,
   request, assembly, state, execution and checkpoint bindings;
4. maps each contiguous six-DOF recovery block to the actual ModelIR node index and identifier;
5. applies only UX/UY/UZ translational displacement in metres to the original global node
   coordinates, multiplied by a finite visual scale in `(0, 1000000]`;
6. reports RX/RY/RZ in radians exactly but never applies them to centerline coordinates;
7. draws original and magnified deformed two-node element centerlines in a fixed 73x25 ANSI-free
   `isometric`, `xy`, `xz` or `yz` terminal viewport;
8. reports exact original/deformed coordinates, recovered components, projected cells, element
   connectivity, CPU FP64 ABI/transfer/sync/fallback receipt and every source identity; and
9. emits deterministic en-US or ko-KR UTF-8 output followed by a SHA-256 self-hash.

The bounded v1 inventory is at most 512 nodes and 1,024 two-node elements. Missing, duplicate,
non-contiguous or unsafe identifiers/indices, dangling or non-two-node connectivity, non-finite
coordinates/results, dimension drift, oversized inventory, unsafe magnification, preterminal
access and artifact/source tampering fail closed.

Clean-environment E2E clears the process environment, leaves `PATH` unusable, and proves
byte-identical direct/restart output for strict ModelIR and normalized MGT linear workflows. It also proves repeated en-US/ko-KR
determinism, explicit-state equivalence, self-hashes, session nonmutation, frozen pre-reaction
compatibility, preterminal rejection, invalid-step rejection, and terminal/source tamper rejection.
No Python, Node, browser or external renderer participates. Installed static/shared distribution
v88 now binds five distinct strict-ModelIR/normalized-MGT locale and projection identities with
direct/restart parity, repeated locale output, invalid-step rejection, Python/Node lookup 0 and
fallback 0. Local rootfs diagnostic v11 independently re-verifies the same identities as UID/GID
65532 with an empty PATH, read-only root and payload, writable workspace and loopback-only
networking. Frozen distribution v1-v87 and rootfs v1-v10 receipts retain their narrower authority.

The source-bound evidence was built from commit `e1d8034dc2552dce00c9fed990053a83f2ce6890`
with source identity
`sha256:39f58bf00f6213e8b7db3929b9b720b0aa2fe787cd2bb1b96e5a799a8324176b`.
The static v88 receipt file is
`sha256:63b49e860c861117a4d6b197140a5a492b94f281ae537a8c306b9882ade00abb`,
the shared v88 receipt file is
`sha256:185b53d6819b51ee6f7f63f73039ba6d3d9b27266ef56415046265b7a7aa434e`,
and the rootfs v11 receipt file is
`sha256:e043d3fda09b3d43daf0f0df495457ee8853db9ce0dc879b48808836f56fa5eb`.

This is a centerline projection of nodal translations. It does not reconstruct element curvature,
apply rigid offsets or nodal rotations, calculate stress/strain or contours, render shell surfaces,
provide perspective interaction, assess serviceability, design supports, apply design codes, or
constitute engineering acceptance. Arbitrary topology, general interactive 3D exploration,
approved HIP C2, public/customer distribution authority and C6 remain open.
