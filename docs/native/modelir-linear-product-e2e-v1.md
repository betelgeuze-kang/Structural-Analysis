# Typed ModelIR Linear Product C4/C5 v1

Status: bounded CPU C4/C5 implementation capabilities. The assembly and sparse numerical families
remain sequentially at C1 until an approved protected-runner HIP C2 receipt exists. This document
does not promote C2, authoritative C3, engineering acceptance, or C6.

## Product path

`structural-model-ir-linear-analysis-request.v1` keeps analysis control outside immutable
`ModelIR`. Rust rejects duplicate keys, unknown fields, invalid portable identifiers, noncanonical
SHA-256 identities, non-CPU selection, and invalid bounded PCG configuration before FFI. The
request binds the exact content, semantic, and provenance hashes plus one direct nodal load-pattern
identifier.

The execution path is:

1. strictly parse and canonicalize `ModelIR` plus the analysis request;
2. require the request's three model identities to match the exact model bytes;
3. create an immutable C++ `ModelIR` handle and call ABI v1.13's exact-size and 16-buffer linear
   assembly operations at an all-zero state;
4. bind the active-DOF map, canonical CSR structure, tangent, mass, load, residual, JVP, recovery
   layout, model identities, selected stable load-pattern index, CPU backend, FP64 policy, and
   fallback zero in a self-hashed assembly receipt;
5. derive one strict `structural-sparse-linear-request.v1` and advance the existing ABI v1.10
   Jacobi-PCG begin/advance path;
6. on convergence, scatter the active solution into the exact global DOF map and call ABI v1.13
   again with displacement and direction equal to that global solution;
7. require immutable CSR/tangent/mass/load/mapping identity, bitwise equality of linear internal
   force and same-state JVP, finite active residuals, canonical element recovery, CPU execution,
   and fallback zero before publishing recovery.

Rust does not reconstruct stiffness, mass, load, internal force, or element recovery formulas.
C++ reference elements and deterministic assembly remain the sole numerical source.
Before allocating the general ABI output arena, Rust queries exact immutable extents and applies
the smaller product caps of 100,000 active DOFs, 5,000,000 structural entries, and 100,000 recovery
records. Oversized graphs fail with no large numerical output allocation.
Recovery declares the canonical per-node `UX, UY, UZ, RX, RY, RZ` ordering, translation/rotation
and force/moment SI units, global active-vector frame, frame local-end-force frame, and truss
axial strain/stress/force channel order.

## C4 checkpoint

`SAMLPC01` is a pointer-free little-endian envelope with a fixed 280-byte header. It contains the
complete existing `SAPCGC01` PCG checkpoint and independently binds:

- ModelIR content, semantic, and provenance identities;
- canonical model-analysis request identity;
- unsigned canonical ABI v1.13 assembly-receipt identity;
- generated canonical-CSR request identity;
- inner complete PCG checkpoint identity;
- outer aggregate checkpoint identity and exact inner byte length.

Resume reconstructs and verifies the exact assembly and generated request before it accepts the
outer envelope. Every single-byte mutation and configuration drift returns checkpoint-mismatch
code 1301. A real one-iteration boundary resumes to the same terminal checkpoint and artifact
bytes as uninterrupted execution.

## C5 CLI and artifacts

The public CPU commands are:

```text
structural-cli analysis model-linear-run MODEL.json REQUEST.json \
  --output-dir direct [--iteration-budget N]

structural-cli analysis model-linear-resume MODEL.json REQUEST.json CHECKPOINT.mlpcp \
  --output-dir resumed [--iteration-budget N]
```

Every boundary atomically publishes a create-new directory containing canonical ModelIR and
analysis request, assembly receipt, generated sparse request, outer and inner checkpoints, both
checkpoint receipts, the inner sparse run receipt, and the outer self-hashed run receipt. A
converged boundary additionally publishes sparse `ResultIR`, sparse `ReportIR`, deterministic
Markdown, and `structural-model-ir-linear-result-recovery-ir.v1`. The complete terminal set has 14
files. Active and numerically failed boundaries never expose terminal result or recovery files.

The clean-environment E2E test clears the child environment, points `PATH` at a nonexistent
directory, executes a direct solve and a real-iteration resume as separate processes, and requires
all 14 terminal files to be byte-identical. No Python/Node lookup, CLI subprocess composition, or
fallback is used. Its request and exact ModelIR three-hash binding are frozen as language-neutral
JSON under `native/tests/fixtures/model_ir_linear/`; fixture drift is not regenerated implicitly.
Symlink inputs and existing destinations fail without partial publication.

## Honest boundary

This slice covers bounded linear-elastic frame3d/truss3d graphs, homogeneous constraints, direct
nodal loads, one signed direct linear combination of two through 64 unique patterns, or one
depth-eight/64-leaf acyclic nested linear combination, active-DOF
solution and residual, and element recovery. The exact-two receipt path remains frozen while the
three-through-64 Workbench path uses the additive v2 provenance/request contract.
It does not expose constrained reactions; ABI v1.13 intentionally returns the reduced active system
only. It also excludes
nonzero prescribed constraints, releases/offsets, self-weight, member loads, nested graphs outside
the bounded depth/expansion/resolved-pattern contract, more-than-64-term combinations or stages,
shells, nonlinear constitutive epochs, reordering/preconditioning authority, native Workbench
integration, PDF specialization, HIP execution, design-code compliance, and C6 decommission.
The separately bounded durable job and loopback-service C5 path is documented in
`docs/native/modelir-linear-durable-job-v1.md`; it does not broaden this numerical claim.
