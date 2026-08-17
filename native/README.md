# Native runtime foundation

This directory defines the first bounded native product boundary for Structural Analysis.

## Current authority

The current slice provides only:

- ABI discovery and version negotiation;
- explicit engine-handle ownership;
- typed status and diagnostic transport;
- a CPU-reference lifecycle implementation;
- a dependency-free Rust raw binding and safe RAII wrapper.

It does **not** provide a production structural solver, Frame3D accuracy authority, HIP residency, external V&V credit, design authority, or release authority.

## Language ownership

```text
Rust product runtime
  project / job / worker / checkpoint registry / result persistence
                         |
                         | versioned C ABI
                         v
C++ numerical engine
  compiled model / elements / materials / assembly / solver / recovery
                         |
                CPU and ROCm/HIP backends
```

Python remains the reference oracle, benchmark generator, research surface, and differential-test harness until a native capability independently earns promotion.

## ABI rules

1. Every public input/output structure begins with `struct_size`.
2. ABI major versions must match; callers may request no newer minor version than the library exposes.
3. No STL, Rust layout, exception, or panic crosses the C boundary.
4. Handles are opaque and released by the library that created them.
5. Native errors are status codes plus copied diagnostic text.
6. Handles are not `Send` or `Sync` until backend thread-safety is proven.
7. Capability bits describe implemented surfaces; they do not grant numerical or release authority.

## Checks

```bash
cmake -S native -B build/native
cmake --build build/native
cargo test --manifest-path native/rust/Cargo.toml --workspace --all-targets
python -m pytest -q tests/test_native_runtime_foundation.py
```

The `native-link` Rust feature is intentionally off by default. Default workspace tests use a mock ABI and therefore do not require a prebuilt native library. Linking the real C++ archive is a later packaging step.

## Next vertical slice

```text
ModelIR
  -> C++ CompiledModel
  -> CPU elastic Frame3D
  -> displacement / reaction / member-force recovery
  -> ResultIR
  -> Python parity
  -> identical operator contract on HIP
```
