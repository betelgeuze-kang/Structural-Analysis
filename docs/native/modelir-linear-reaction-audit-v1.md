# ModelIR linear algebraic reaction audit v1

`structural-workbench reaction-audit` is a read-only C5 numeric audit for the explicit
`model_ir_linear_cpu_v1` Workbench profile:

```text
structural-workbench reaction-audit --workspace <DIR> [--locale <en-US|ko-KR>]
```

The command requires a terminal-or-later durable session. It re-verifies the terminal receipt,
sparse ResultIR, typed global/element recovery ResultIR, constrained-reaction ResultIR, exact source
bindings, and immutable ModelIR content/semantic/provenance identities before computing anything.
A frozen pre-reaction workspace fails with `workbench_reaction_audit_missing`; an NDTHA workspace
fails with `workbench_profile_unsupported`.

The audit reconstructs one complete global generalized external-load vector from the verified
active and constrained partitions. It separately places every constrained reaction at its global
DOF. For each six-DOF node it then computes:

- applied and reaction force resultants;
- applied and reaction moment resultants about the ModelIR global origin, including both `r x F`
  and nodal generalized moments;
- force and moment closure residual vectors; and
- the independently recomputed active-equation residual infinity norm from internal minus external
  generalized force.

No source load is reinterpreted. The audit consumes the exact generalized external-load vectors
already accepted by the bounded C++ assembly/result contract, so it does not silently create a new
distributed-load or self-weight interpretation.

Each observation uses the fixed, visible numeric policy
`256 * IEEE754_BINARY64_EPSILON * max(1, absolute_contribution_scale)`. Force, moment, active
equation, and overall states use only `within_numeric_tolerance` or
`outside_numeric_tolerance`. These strings describe floating-point algebraic closure; they are not
engineering pass/fail decisions.

The deterministic ANSI-free `en-US` or `ko-KR` output preserves exact FP64 resultants, residuals,
scales, tolerances, CPU FP64 ABI/fallback/transfer counters, and model/request/assembly/result/
recovery/reaction/state/execution/checkpoint identities. A final SHA-256 covers every preceding
output byte, and the command never mutates or re-executes the workspace.

Clean-environment E2E binds byte-identical direct/restart output for strict ModelIR and normalized
MGT linear workflows, repeated locale output, exact self-hashes, visible nonzero roundoff closure,
durable-session nonmutation, frozen pre-reaction rejection, and terminal-receipt tamper rejection
with no Python or Node. Installed static/shared distribution and non-root read-only rootfs
publication for this new command remain open until their append-only successor receipts are built.

This audit is limited to algebraic global resultants and the active equation residual for the
bounded frame3d/truss3d linear CPU candidate. It is not support design, stability or singularity
assessment, design-code compliance, engineering acceptance, approved HIP C2 evidence, public or
customer distribution publication, or C6 authority.
