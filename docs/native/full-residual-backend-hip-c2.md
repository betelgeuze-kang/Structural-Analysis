# Full-residual product backend HIP C2 candidate

ABI v1.12 adds one append-only `backend_get_api` slot to the only public product symbol,
`sa_get_api_v1`. The selected table owns a versioned full-residual operator descriptor and an
opaque execution context. CPU-only builds return a real CPU table and reject HIP with
`SA_ERR_BACKEND_UNAVAILABLE`; HIP builds select only explicit device 0 and never fall back.

The HIP context deep-copies frame, shell CSR, spring CSR, external-force, and free-DOF operator
buffers once. Evaluation transfers only the caller's batched state and returns only the final
residual. Its grid-stride kernel computes each residual entry in a fixed frame/local/CSR order;
there is no `atomicAdd`, host reduction, or per-repetition operator transfer. Receipt fields bind
the run to the device, ROCm runtime/driver, compiler, compiled architecture, kernel source SHA,
device-library SHA, H2D/D2H counts, synchronization count, resident bytes, VRAM, FP64 policy,
determinism, and `fallback_count=0`.

The Rust safe wrapper owns context destruction and requires `&mut self` for execution. The legacy
`mgt_hip_full_residual_ffi` cdylib keeps its seven exports but resolves exactly one product symbol,
`sa_get_api_v1`; it no longer resolves or owns standalone HIP kernel symbols.

This is a C2 candidate until the dedicated self-hosted workflow runs in the protected
`native-hip-approved` environment and its checker accepts the source-bound live receipt. A local
compile or local GPU run is not authoritative C2. The lane does not close broader solver parity,
checkpoint/restart, packaging, product E2E, legacy removal, or C6 Python/Node decommission.
