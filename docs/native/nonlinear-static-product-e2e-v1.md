# Nonlinear Static Newton Product E2E v1

## Scope and gate boundary

This slice connects the existing bounded 1/3-story FP64 C++ reference family to ABI v1.11,
an exact CPU C4 checkpoint, and a public Rust C5 product flow. It does not promote the
nonlinear-static numerical family beyond C1: an approved HIP C2 receipt is still required before
sequential C3/C4/C5 cutover authority can advance. General ModelIR topology, shell/frame assembly,
engineering acceptance, HIP execution and C6 decommission remain open.

The implemented profile is the existing serial story-frame law: positive story stiffness and
height, finite axial load/yield drift/floor load, bilinear hardening, optional P-delta tangent,
fixed-order tridiagonal Newton updates and deterministic backtracking. CPU execution is FP64 with
fallback count zero.

## ABI v1.11 real Newton iteration state

ABI v1.11 appends `nonlinear_static_begin` and `nonlinear_static_advance` at table offsets 160 and
168. The 152-byte caller-owned state includes status, iteration and backtrack counters, recovered
residual/displacement/base-shear/plastic metrics, and the complete displacement vector. C++ first
deep-copies and deterministically revalidates the supplied boundary, advances a private state, and
publishes only after success. A zero budget and terminal state are idempotent. A numerical
nonconvergence is a durable terminal state rather than discarded partial output.

The safe Rust owner serializes values only; no process pointer crosses a restart boundary. Tests
split a six-iteration solve across real Newton iteration boundaries, JSON round-trip the state,
and require exact equality with direct completion. One-bit metric corruption and changed problem
bindings fail atomically with checkpoint-mismatch taxonomy.

## C4 SASTAC01 checkpoint

`SASTAC01` is a bounded canonical little-endian artifact containing canonical request bytes and
the complete pointer-free Newton state. Its 192-byte header carries five independent SHA-256
bindings:

- exact request identity;
- story model, material law, forcing and unit identity;
- complete Newton state identity;
- backend, controls, ABI v1.11 and algorithm identity;
- aggregate checkpoint identity over all preceding identities and both payloads.

Restore re-parses the request with strict duplicate-key/unknown-field/non-finite rejection,
requires canonical bytes, re-encodes the state, independently repeats constitutive recovery, and
checks every identity. The focused C4 test flips every single byte of a real checkpoint and
requires every mutation to fail closed. Request, input and configuration drift also fail.

## ResultIR, ReportIR and C5 CLI

The strict request schema is `structural-nonlinear-static-request.v1` with operation
`solve_nonlinear_static_newton`, one portable case ID, CPU backend, bounded solver configuration
and five exactly sized story vectors. A converged state projects to self-hashed
`structural-nonlinear-static-result-ir.v1`; Rust independently recovers residual, displacement,
base shear and plastic-story metrics from the exact request and displacement values before
publication. Deterministic Markdown and self-hashed ReportIR remain `bounded_candidate` evidence.

Public commands are:

~~~text
structural-cli analysis static-run request.json --output-dir direct
structural-cli analysis static-run request.json --output-dir partial --iteration-budget 1
structural-cli analysis static-resume request.json partial/checkpoint.stacp \
  --output-dir resumed
~~~

An active boundary publishes only checkpoint, checkpoint receipt and run receipt. A converged
boundary additionally publishes ResultIR, ReportIR and Markdown. A nonconverged terminal boundary
publishes its durable checkpoint and typed failure receipt, then returns a failing process status.
Output publication is create-new and atomic; symlink inputs, corrupt checkpoints and existing
destinations fail without partial publication.

The C5 test clears the environment, gives the process no usable `PATH`, and proves that direct and
real-iteration resumed artifact directories are byte-identical without Python/Node lookup.

## Honest open gates

- HIP C2 has no approved protected-runner receipt for this nonlinear-static family.
- This story model is not arbitrary ModelIR assembly or general frame/shell nonlinear authority.
- Durable queued-job/service integration and the broader Workbench are not claimed by this slice.
- PDF rendering is not promoted for this result profile.
- C6 needs protected C2, sequential closure, rollback packaging and removal evidence; none is
  inferred from bounded CPU C4/C5 implementation.
