# Engine v2 HIP canonical sparse-LU apply

This slice adds a backend adapter for the canonical sparse-LU factor contract.
It fixes the factor arrays, row/column permutations, dependency-level
schedules, one right-hand side, and the CPU comparison rules before invoking
HIP. It does not change the canonical CPU factor format or promote a production
GPU solver.

## Execution contract

The nontrivial eight-equation fixture contains 19 lower and 19 upper
nonzeros. The lower and upper triangular dependencies produce six levels each.
The HIP executable validates the complete fixture, then enqueues this sequence
on one stream:

1. inverse row-permutation RHS gather;
2. one forward-substitution kernel per lower dependency level;
3. one backward-substitution kernel per upper dependency level;
4. forward column-permutation solution gather.

That gives 14 expected kernel invocations. There is no device-to-host transfer
or blocking synchronization between levels; one final synchronization precedes
the output receipt. Compilation disables FP contraction, and each row follows
ascending-column sequential FP64 accumulation. The receipt comparison checks
both the canonical Python-`fsum` result and a CPU reference that reproduces the
device accumulation order, using absolute and relative tolerances of `1e-11 m`.

The fixture identities are:

- fixture:
  `sha256:101104d49783906875453f094cec2a74e2650edfedf773169063ae80c030c5e1`;
- factor contract:
  `sha256:7e0d74b3cbc4e0de978474da946a2e821bbfaa389b6ae7a7c2734d194f78f3b6`;
- dependency schedule:
  `sha256:41e15f32bc0772cd44e76b512a00672ab78becc14a0da99d7e55361511b8ff36`;
- preconditioner contract:
  `sha256:2d88fe848dbf8e21b27551ed302407a70050e552baf00464b0ef597bdf6bb1bd`.

## Current evidence

ROCm/HIP compiler `6.0.32831-204d35d16` compiles the source with `-Werror` for
both declared targets. A second build reproduced the same binary hashes:

- `gfx1030`: 57,936 bytes,
  `sha256:be3b38976dcecec4d4be06fb5a21e60158fbea7b486dc8f3d378dafe71605751`;
- `gfx1100`: 58,192 bytes,
  `sha256:9c23f463c1a124a64702d2c3b270e872c5e64f9a7e5cdf388190c104806824aa`.

Each binary also runs `--validate-fixture-only` successfully against the same
1,232-byte fixture. This path parses and validates every CSR, permutation,
schedule, and RHS field before returning a bounded JSON record with
`actual_hardware=false` and `hip_runtime_api_call_count=0`.

The environment did not expose `/dev/kfd` or `/dev/dri`, so neither binary was
executed. The committed receipt is deliberately
`contract_scope=target_compile_and_host_fixture_parser_only`; actual hardware
execution, numerical parity, actual 70,560-equation MGT factor execution,
production-size schedule execution, device-resident current-tangent FGMRES,
independent cross-device receipts, and performance all remain false.

The actual-MGT G1 audit now prepares the production-size dependency schedule
without promoting an execution claim. For the 70,560-equation, 12,554,899-nnz
canonical factor it records:

- lower schedule: 4,405 levels, maximum width 14,101;
- upper schedule: 4,254 levels, maximum width 6,637;
- four schedule arrays: 1,198,248 bytes;
- schedule contract:
  `sha256:25ebdf8fdb6ab2ff8ae2801dad604a51df809353f57d3d0e144a739a284af5df`;
- declared full fixture size: 204,899,096 bytes;
- expected current implementation launch count: 8,661 kernels.

The audit additionally materializes the complete 204,899,096-byte fixture in a
temporary directory, validates the exact streaming readback hash
`sha256:80dc13ad269f787dd328be5ccd5018377d5d830057e75a9740e89898d401db89`,
and deletes it.
This is an ephemeral executable-input roundtrip, not a retained release
artifact. The 8,661 launch count is an execution-plan fact, not performance
evidence; it makes
actual device timing and, potentially, a persistent-kernel or grouped-level
strategy necessary before production promotion.

## Artifacts and checks

- adapter contract:
  `src/structural_analysis/engine_v2_backends/hip_sparse_lu_apply.py`;
- HIP source:
  `implementation/phase1/hip_kernels/engine_v2_sparse_lu_apply.hip.cpp`;
- runner:
  `scripts/run_engine_v2_hip_sparse_lu_apply.py`;
- runtime schema:
  `src/structural_analysis/schemas/hip_sparse_lu_apply_parity_v1.schema.json`;
- compile/host-parser schema:
  `src/structural_analysis/schemas/hip_sparse_lu_apply_compile_receipt_v1.schema.json`;
- compile/host-parser receipt:
  `implementation/phase1/release_evidence/productization/engine_v2_hip_sparse_lu_apply_compile_receipt.json`.

```bash
python3 scripts/run_engine_v2_hip_sparse_lu_apply.py --compile-only --check
python3 -m pytest -q \
  tests/test_engine_v2_hip_sparse_lu_apply.py \
  tests/test_engine_v2_hip_sparse_lu_apply_runner.py
```

On an authorized AMD ROCm host with a visible device, omit `--compile-only` to
produce the separate hardware/parity receipt. That receipt remains a small
fixture proof; actual-scale integration and independent `gfx1100` evidence are
separate gates.
