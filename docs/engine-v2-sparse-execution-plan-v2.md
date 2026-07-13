# Engine v2 sparse-only ExecutionPlan v2

Status: bounded Phase 0 implementation

Scope: zero-offset, zero-release, zero-prescribed-displacement linear 3D frame/truss

Schema: `structural-analysis-execution-plan.v2`

## Outcome

`ExecutionPlanV2` compiles the existing `SolverModelBuffers v1` input directly
to sorted FP64 CSR without ever allocating a global `(G,G)` stiffness array.
The execution path uses the retained reduced CSR with SciPy sparse direct solve,
then performs sparse residual/reaction evaluation and element-local force/energy
recovery.

This is a sparse foundation slice, not a commercial solver breadth claim. It
does not add offsets, end releases, nonzero prescribed displacements,
shell/solid elements, geometric or material nonlinearity, dynamics, buckling,
staged construction, or a HIP sparse solver.

## Retained-array boundary

The immutable plan retains these descriptor-listed linear-memory array groups
in a fixed canonical tuple (not a mutable or externally aliased mapping):

- node/global/element DOF maps and strict free/constrained partitions;
- sorted full CSR row/column/diagonal indices;
- deterministic element-to-CSR scatter indices;
- sorted reduced CSR and exact reduced-to-full value positions;
- full and reduced FP64 CSR values, including retained structural-zero slots;
- global load vector;
- per-element 12-by-12 transform and local-stiffness recovery arrays.

There is no `global_stiffness_dense` payload and no densification helper in the
compiler, validator, residual/JVP, direct solve, reaction, or recovery path.
Per-element 12-by-12 work is fixed-size local work and is not a global matrix.

## Determinism and hashes

The numeric assembly order is fixed as:

1. ascending element index;
2. ascending local row;
3. ascending local column;
4. one addition into the precompiled CSR scatter position.

All floating payloads normalize signed zero before immutable byte hashing.

The plan deliberately separates three identities:

- `symbolic_reuse_hash` binds topology, DOF partition, sorted CSR patterns, and
  scatter maps; it can be reused across changed loads or element numerics when
  topology/supports are unchanged;
- `numeric_snapshot_hash` binds the full/reduced CSR values, global load, local
  transforms, local stiffness, formula-source version, solver buffer hash,
  recovery hash, and assembly order;
- `plan_hash` binds the exact input artifact, solver tolerance, all manifest
  content, and both identities above.

The validator does more than recheck user-provided hashes. It revalidates the
bound source buffers, requires exact descriptor and base `numpy.ndarray` types,
rederives the constrained/free/global-to-free partition from the exact
`support_mask` bytes, reconstructs the supported local transforms/stiffness,
recompiles the symbolic pattern, and independently reaccumulates an O(nnz) CSR
value vector. Thus a coherently changed partition, value, or local operator
remains detectable after the attacker refreshes all descriptors and aggregate
hashes. The fixed tuple also prevents an external mapping pointer swap from
changing subsequent public residual/JVP behavior.

## Numerical execution

`solve_sparse_execution_plan_v2` builds SciPy CSR directly from the retained
reduced arrays, uses `spsolve` with `NATURAL` permutation and no fallback, and
recovers:

- nodal displacements;
- full residual `K*u-F`;
- constrained reactions and zero free reaction slots;
- local element end forces;
- element and total strain energy.

The result receipt has its own strict Draft 2020-12 schema and binds the exact
plan/operator/numeric snapshot plus immutable array descriptors.

The in-memory result validator repeats the SciPy reduced direct solve and then
recomputes residual, reaction, recovery force, and energy in the same operation
order. It requires exact normalized FP64 array equality, exact nonnegative
element/total energy, and exact zero free-reaction slots. This is an
`exact_same_runtime_direct_solve_replay` claim only. Cross-platform serialized
receipt loading/replay, BLAS/SciPy version portability, and signed provenance
are not implemented in this slice.

## Complexity claim boundary

- complete symbolic and numeric compile:
  `O(E*12^3 + sum_r(z_r*log(z_r)) + nnz)`, including fixed-size transform
  multiplication and per-row column sorting;
- direct scatter accumulation after the symbolic map exists:
  `O(E*12^2 + nnz)`;
- only when both element rank and assembled row degree are bounded does the
  compile expression reduce to `O(E + nnz)`;
- residual/JVP: `O(nnz)`;
- descriptor-listed retained plan arrays: measured by
  `described_array_byte_length` and expected to be linear for a fixed-degree
  chain;
- SciPy sparse direct factorization/solve: explicitly **not O(N)**;
- end-to-end solve: no O(N) claim;
- no speedup, HIP parity, multi-architecture, or commercial-readiness claim.

The focused five-size chain test compiles 17, 33, 65, 129, and 257-node models,
fits log-log slopes for descriptor-listed retained plan-array bytes and CSR
`nnz`, and forbids invoking the v1 global dense assembler during that scaling
check. It excludes the strong `_source_buffers` reference, Python object
overhead, transient symbolic sets/dictionaries, SciPy state, and manifest
materialization. This is a deterministic unit-scale retained-array growth guard,
not a peak-memory or production performance benchmark.

## Verification

Focused coverage includes:

- strict Draft 2020-12 schemas and additional-property rejection;
- deterministic immutable artifacts and structural-zero retention;
- symbolic reuse across load/geometry changes with distinct numeric/plan hashes;
- fully rehashed partition, CSR, and local-operator tamper rejection;
- fail-closed nonzero prescribed displacement;
- sparse residual, JVP, reduced JVP, solve, reaction, force, and energy parity
  with the existing v1 oracle for cantilever load modes, a truss, a rotated
  frame, and a two-element frame;
- five-size retained plan-array byte/`nnz` slope guard;
- source guard against global densification helpers.

Run:

```bash
PYTHONPATH=src pytest -q tests/test_engine_v2_execution_plan_v2_sparse.py
ruff check src/structural_analysis/engine_v2/contracts/execution_plan_v2.py \
  src/structural_analysis/engine_v2/operators \
  tests/test_engine_v2_execution_plan_v2_sparse.py
```

## Follow-up debt

The v2 compiler currently imports the v1 CPU reference module's private element
validation, frame construction, and frame/truss stiffness helpers. This avoids
changing frozen v1 behavior while preserving exact numerical conventions. A
later isolated refactor should move these formulas into a versioned shared
element-kernel module and make both v1 and v2 consume it under unchanged parity
tests.

`ExecutionPlanV2` also keeps a strong `_source_buffers` reference so validation
can independently rederive source semantics. Compilation first applies the
public immutable-backing preflight, then constructs an alias-free canonical
snapshot of the source array/entity/code-table containers. Its referenced array
bytes are intentionally not included in `described_array_byte_length`. Calling
`to_dict()` materializes CSR, scatter, and DOF arrays through `.tolist()`,
creating transient O(N) Python objects with a high constant factor. Peak
resident memory and a streaming or descriptor-only manifest export need a
separate measured follow-up gate.
