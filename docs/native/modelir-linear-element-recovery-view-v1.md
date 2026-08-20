# ModelIR linear element recovery view v1

`structural-workbench element-recovery-view` is a bounded read-only C5 result surface for the
explicit `model_ir_linear_cpu_v1` Workbench profile:

```text
structural-workbench element-recovery-view --workspace <DIR> \
  [--locale <en-US|ko-KR>] [--start-element <N>] [--count <1..256>]
```

The command requires a terminal-or-later durable session. It re-verifies the terminal run receipt,
strictly parses the sparse ResultIR and typed ModelIR linear recovery IR, verifies their exact
source binding, strictly reparses the immutable imported ModelIR, and independently revalidates
that model through the native C++ semantic boundary before rendering. Content, semantic,
provenance, request, assembly, result, recovery, state, execution, and checkpoint identities remain
visible. A preterminal workspace fails closed, and a non-ModelIR-linear workspace fails with
`workbench_profile_unsupported`.

Each row maps one stable recovery index to the immutable element ID, zero-based element index,
element family, and ordered two-node connectivity. A frame row reports all 12 frame3d local end forces
in fixed `i` then `j` order: forces in N and moments in N*m. A truss row reports the three
truss3d axial strain, stress, and force components in dimensionless strain, Pa, and N. The fixed
coordinate frames are `element_local` for frame3d and `element_axis` for truss3d.

The default window starts at element one and contains at most 64 elements; callers may request one through 256 elements.
Missing or duplicate identifiers, duplicate or absent stable indices,
non-two-node connectivity, family/type mismatch, invalid recovery offsets, non-finite FP64 values,
dimension drift, or an out-of-range window fail closed.

The deterministic ANSI-free `en-US` or `ko-KR` output preserves exact FP64 components, CPU FP64 ABI
receipt, transfer/sync counters, fallback count, coordinate frames, units, and every source
identity. Locale changes fixed labels only. A final SHA-256 covers every preceding output byte, and
the command never mutates or re-executes the workspace.

Clean-environment E2E binds byte-identical strict ModelIR and normalized MGT linear workflows across
direct and real-checkpoint restart execution. It also checks repeated output, exact rows and
self-hashes, bounded-window policy, durable-session nonmutation, preterminal and wrong-profile
rejection, terminal recovery tamper rejection, and original MGT source-binding rejection. Unit
coverage fixes frame3d/truss3d component labels and scientific-notation formatting.

Installed CPU static/shared distribution v89 now binds repeated en-US/ko-KR strict-ModelIR and
normalized-MGT Frame3D end-force views, direct/restart parity, four distinct identities and
invalid-window rejection. Local rootfs diagnostic v12 independently re-verifies those same
installed bytes as UID/GID 65532 with a read-only root and payload. Truss3D formatting remains
source-tested rather than independently executed by these installed receipts. Neither receipt is
customer publication or release authority.

This view exposes element recovery already carried by one verified linear-static result. It is not
a shell or general stress contour, member diagram interpolation, design utilization, serviceability
assessment, support design, design-code check, engineering acceptance, approved HIP C2,
public/customer distribution, or C6 authority.
