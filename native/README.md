# Native runtime foundation

This directory defines the first bounded native product boundary for Structural Analysis.

## Current authority

The current branch provides:

- ABI discovery and version negotiation;
- explicit engine-handle ownership;
- typed status and allocation-free diagnostic transport;
- a CPU-reference lifecycle implementation;
- a dependency-free Rust raw binding and safe RAII wrapper;
- one bounded linear CPU Frame3D compile/solve/recovery slice.

The linear Frame3D slice is limited to 2–16 nodes, 1–32 two-node prismatic Timoshenko members, at most 60 free equations, explicit effective shear areas, explicit restraints, optional local-axis roll, and one global nodal load vector. It returns the full displacement vector, equilibrium residual/reaction vector, and local member end forces.

It does **not** provide a production structural solver, geometric or material nonlinearity, releases, offsets, member loads, sparse production scalability, modal/buckling/transient analysis, shell/contact/cable support, HIP residency, ResultIR promotion, external V&V credit, design authority, public support, paid-pilot readiness, or release authority.

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

Python remains the reference oracle, benchmark generator, research surface, and differential-test harness until each native capability independently earns promotion.

## ABI rules

1. Every public input/output structure begins with `struct_size`.
2. ABI major versions must match; callers may request no newer minor version than the library exposes.
3. ABI-facing status and execution-mode scalars use fixed-width integer typedefs; C enum layout is never assumed by Rust.
4. Reserved input fields must be zero so a current library never silently accepts unknown future semantics.
5. No STL, Rust layout, exception, or panic crosses the C boundary.
6. Handles are opaque and released by the library that created them.
7. Native diagnostics use a bounded allocation-free thread-local store; callers first query the required copied-buffer size.
8. Fallible scalar outputs are reset before validation. Frame solve buffers are zeroed before numerical execution.
9. Rust compiled-model lifetimes are tied to the creating engine, and handles remain non-`Send`/non-`Sync` until backend thread-safety is proven.
10. Capability bits describe implemented bounded surfaces; they do not grant numerical or release authority.

## Checks

```bash
cmake -S native -B build/native
cmake --build build/native
cargo test --manifest-path native/rust/Cargo.toml --workspace --all-targets
python -m pytest -q \
  tests/test_native_runtime_foundation.py \
  tests/test_native_linear_frame3d.py
```

The `native-link` Rust feature is intentionally off by default. Default workspace tests use mock ABIs and therefore do not require a prebuilt native library. Linking the real C++ archive is a later packaging step.

The focused contracts:

- compile the public header as C11;
- compile both C++20 translation units with strict warnings;
- link and execute the native lifecycle boundary;
- build a shared library and compare a cantilever solve against the existing Python Timoshenko reference;
- verify reactions and local member forces;
- reject reserved fields, short buffers, and singular models;
- run Rust ownership, load-length, result-buffer, and diagnostic tests offline.

These checks prove only the bounded capability described above.

## Next slices

```text
bounded linear Frame3D
  -> canonical ModelIR compiler adapter
  -> versioned raw numerical result adapter
  -> installed Linux/Windows package parity
  -> identical operator contract on HIP
  -> nonlinear/stateful promotion only after separate verification
```
