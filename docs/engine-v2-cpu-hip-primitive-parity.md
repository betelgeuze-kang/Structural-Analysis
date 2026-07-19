# Engine v2 CPU/HIP primitive parity

This slice keeps the Engine v2 core backend-neutral and places the optional HIP
adapter under `structural_analysis.engine_v2_backends`. The fixture is bound to
the deterministic CPU FGMRES run's ExecutionPlan hash, EquationScaling hash,
reduced-CSR identity, and operator numeric-values hash. Its mixed numeric input
is serialized as canonical little-endian binary.

The actual HIP probe executes these FP64 operations on one explicit stream:

- reduced-CSR SpMV;
- dot product;
- L2 and Linf norms;
- operator-derived left-scaled Jacobi preconditioner apply;
- AXPY;
- solution update.

The local receipt was compiled with ROCm HIP and executed on an AMD Radeon RX
6900 XT (`gfx1030`). Every primitive matches the CPU reference within absolute
and relative tolerance `1e-12`; the maximum observed absolute difference is
`2.7755575615628914e-17`. The runtime output also records no CPU backend, six
kernel invocations, same-stream ordering, and one blocking D2H synchronization
after all result copies are enqueued.

The preconditioner profile is
`operator_derived_left_scaled_jacobi_right.v1`. Its canonical vector is the
exact positive diagonal inverse of `D_free^-1 A_free`, selected through the
authoritative reduced-CSR mapping. The fixture carries the scale divisors, and
both the Python validator and HIP executable recompute the diagonal relation
and fail closed on a missing, duplicate, non-positive, or mismatched entry. The
receipt binds preconditioner contract hash
`sha256:7a80362388b9ce461d6816e704fff162f9ccbba9e9de8f204884c61d1cf1c1bc`.

Artifacts:

- `implementation/phase1/release_evidence/productization/engine_v2_cpu_hip_primitive_parity_receipt.json`
- `src/structural_analysis/schemas/cpu_hip_primitive_parity_v1.schema.json`
- `implementation/phase1/hip_kernels/engine_v2_primitive_parity.hip.cpp`

Run actual local hardware and then check it offline:

```bash
PYTHONPATH=src python3 scripts/run_engine_v2_hip_primitive_parity.py
PYTHONPATH=src python3 scripts/run_engine_v2_hip_primitive_parity.py --check
PYTHONPATH=src python3 -m pytest -q \
  tests/test_engine_v2_hip_primitive_parity.py \
  tests/test_engine_v2_hip_primitive_parity_runner.py
```

The receipt deliberately remains `status=partial`. It was created from a dirty
development worktree and therefore sets `exact_source_commit_claim=false`.
Because this is a primitive-only receipt, its full-recurrence claim remains
false even when a separate recurrence receipt exists. Its checkpoint-artifact
claim also remains false because checkpoint resume is covered by the separate
recurrence receipt, not by this primitive probe. The operator-derived Jacobi
apply probe is true on this six-equation fixture, while production-scale
preconditioner effectiveness remains unverified. An independent `gfx1100` run,
a clean same-commit and wheel-hash pair, signature, and performance claims also
remain false.
