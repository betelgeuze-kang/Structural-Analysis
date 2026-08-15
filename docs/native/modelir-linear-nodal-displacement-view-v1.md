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
receipt tamper rejection, and no Python or Node lookup. Installed static/shared distribution v87
now binds the same five distinct strict-ModelIR/normalized-MGT locale and window identities with
direct/restart parity, Python/Node lookup 0 and fallback 0. Local rootfs diagnostic v10 independently
re-verifies those five identities as UID/GID 65532 with an empty PATH, read-only root and payload,
writable workspace and loopback-only networking. Frozen distribution v1-v86 and rootfs v1-v9
receipts retain their narrower authority.

The source-bound evidence was built from commit `038a2b868ac89ebb6790222071071f933a542ef6`
with source identity
`sha256:e57f5733e787c932999896de64a08bb9b35179c4aa2cad046a92bb60c6e6a885`.
The static v87 receipt file is
`sha256:943f021c218615e5e41178691085382343440cbe887a0a0c0d96f0ad05cdd159`,
the shared v87 receipt file is
`sha256:6ead38b73e3a89682178d272df9f230c5d1c5054feaf3de0f75e6f18ddcef675`,
and the rootfs v10 receipt file is
`sha256:1f6329b1ec86b487d4f3cb65aeda7cce02b4a2bde4932ac9192be6c7e672f0c9`.

This view is a numeric table over one verified linear-static recovery. It is not a deformed-shape,
stress, contour, modal, serviceability, support-design, design-code, engineering-acceptance,
approved HIP C2, public/customer distribution, or C6 authority.
