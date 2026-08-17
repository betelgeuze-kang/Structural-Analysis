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
3. ABI-facing status and execution-mode scalars use fixed-width integer typedefs; C enum layout is never assumed by Rust.
4. Reserved input fields must be zero so a current library never silently accepts unknown future semantics.
5. No STL, Rust layout, exception, or panic crosses the C boundary.
6. Handles are opaque and released by the library that created them.
7. Native errors are status codes plus copied diagnostic text; callers first query the required buffer size.
8. Fallible output scalars are reset to a fail-closed value before validation, and successful calls clear stale thread-local diagnostics.
9. Handles are not `Send` or `Sync` until backend thread-safety is proven.
10. Capability bits describe implemented surfaces; they do not grant numerical or release authority.

## Checks

```bash
cmake -S native -B build/native
cmake --build build/native
cargo test --manifest-path native/rust/Cargo.toml --workspace --all-targets
python -m pytest -q tests/test_native_runtime_foundation.py
```

The `native-link` Rust feature is intentionally off by default. Default workspace tests use a mock ABI and therefore do not require a prebuilt native library. Linking the real C++ archive is a later packaging step.

The focused Python contract compiles the header as C11, compiles the implementation with strict C++20 warnings, links and executes a native lifecycle binary, and runs the Rust workspace offline. These checks prove only the lifecycle boundary described above.

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
