# ModelIR linear constrained-reaction view v1

`structural-workbench reaction-view` is a read-only C5 terminal projection for the explicit
`model_ir_linear_cpu_v1` Workbench profile:

```text
structural-workbench reaction-view --workspace <DIR> \
  [--locale <en-US|ko-KR>] [--start-row <N>] [--count <1..256>]
```

The command requires the durable session to be terminal or later. Before presenting a value it
re-verifies the terminal run receipt, sparse ResultIR, typed global/element recovery ResultIR,
constrained-reaction ResultIR, their exact source bindings, and the immutable ModelIR identities.
It then maps each constrained global DOF through the ModelIR node `index` to the actual node ID and
the fixed `UX, UY, UZ, RX, RY, RZ` order. Every row preserves the exact FP64 internal force,
external load, internal-minus-external reaction, and its `N` or `N*m` unit.

The output also carries component sums, maximum absolute reaction, model/request/assembly/state/
execution/checkpoint identities, source result and recovery hashes, the CPU FP64 ABI receipt,
transfer/synchronization counters, and fallback count. English and Korean change labels only. The
view contains no ANSI escape byte and appends a SHA-256 identity over every preceding output byte.
Windows are one-based, deterministic, and limited to 256 rows; the command never mutates or
re-executes the durable workspace.

Clean-environment E2E proves byte-identical output from a one-real-iteration restart and a direct
workflow, repeated Korean output, bounded-window behavior, durable-session nonmutation, exact
node/DOF/value/unit rows, source-hash visibility, and receipt-tamper rejection. A frozen
pre-reaction workspace fails with `workbench_reaction_view_missing`. The NDTHA profile fails with
`workbench_profile_unsupported`; compatibility artifacts are not silently synthesized.

This is not an equilibrium audit, support-design verdict, general nodal-field/stress/contour/modal
viewer, engineering acceptance, design-code compliance, installed distribution publication,
approved HIP C2 evidence, or C6 authority.
