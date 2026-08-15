# ModelIR linear nodal displacement view v1

`structural-workbench nodal-displacement-view` is a bounded read-only C5 result surface for the
explicit `model_ir_linear_cpu_v1` Workbench profile:

```text
structural-workbench nodal-displacement-view --workspace <DIR> \
  [--locale <en-US|ko-KR>] [--start-node <N>] [--count <1..256>]
```

The command requires a terminal-or-later durable session. It re-verifies the terminal run receipt,
strictly parses the sparse ResultIR and typed ModelIR linear recovery IR, verifies their exact
source binding, and strictly reparses the immutable imported ModelIR before rendering. Content,
semantic, provenance, request, assembly, result, recovery, state, execution, and checkpoint
identities remain visible. An NDTHA workspace fails with `workbench_profile_unsupported`.

Each displayed row maps one contiguous ModelIR node index to its actual immutable node ID and the
six recovered global displacement components in fixed order: `UX`, `UY`, `UZ` in metres and `RX`,
`RY`, `RZ` in radians. The default window starts at node one and contains at most 64 nodes; callers
may request one through 256 rows. Missing, duplicate, non-contiguous, out-of-range, or dimensionally
inconsistent node mappings fail closed.

The deterministic ANSI-free `en-US` or `ko-KR` output preserves exact FP64 values, the CPU FP64 ABI
receipt, transfer/sync counters, fallback 0, coordinate frame, and all source identities. Locale
changes fixed labels only. A final SHA-256 covers every preceding output byte, and the command never
mutates or re-executes the workspace.

Clean-environment E2E binds byte-identical direct/restart output for strict ModelIR and normalized
MGT linear workflows, repeated locale output, exact rows and self-hashes, bounded-window rejection,
durable-session nonmutation, frozen pre-reaction compatibility, wrong-profile rejection, terminal-
receipt tamper rejection, and no Python or Node lookup. Installed static/shared distribution and
non-root read-only rootfs publication for this new command remain open until append-only successor
receipts are built.

This view is a numeric table over one verified linear-static recovery. It is not a deformed-shape,
stress, contour, modal, serviceability, support-design, design-code, engineering-acceptance,
approved HIP C2, public/customer distribution, or C6 authority.
