# ModelIR linear-static load-pattern addition v1

This C5 slice creates one valid `linear_static` load pattern and its first nodal load as one atomic
operation. It never publishes an empty intermediate pattern. The installed command is:

```text
structural-workbench model-add-linear-load-pattern MODEL.json \
  --load-pattern NEW-PATTERN-ID --load NEW-LOAD-ID \
  --node EXISTING-NODE-ID --components FX FY FZ MX MY MZ \
  --output-dir ADDED-PATTERN-MODEL
```

## Contract

Rust strictly reads the bounded source ModelIR. Pattern, load, and node identities must be UTF-8
with 1-128 bytes. The pattern identity must be new, the nested load identity must be globally
unique across all patterns, and the target node must exist. All six force/moment components are
finite SI values and at least one is nonzero.

The operation appends exactly one top-level pattern with the next contiguous index,
`analysis_type: linear_static`, zero self-weight, null `source_id`, empty extensions, and exactly
one index-zero nodal load. That load targets the selected existing node and also has neutral source
ownership and empty extensions. Self-weight authoring, combinations, time functions, other load
families, empty patterns, editing, deletion, and retargeting are outside this command.

Both source and edited models cross Rust -> C ABI -> C++ semantic validation. The edited canonical
model carries `structural-native:model-add-linear-load-pattern.v1`, complete upstream provenance,
and the exact source content/semantic/provenance identities. Existing round-trip rows and explicit
blockers remain unchanged; a successful edit never promotes analysis readiness.

Publication is create-new and atomic. It emits `model-ir.json` plus a self-hashed
`structural-native-model-edit-receipt.v1` binding the pattern ID/index/type/self-weight, first load
ID/index/node/components, source input hash, source and edited hashes, C++ snapshot status,
analysis readiness, blockers, artifact hash, and claim boundary.

## Product evidence

Focused Rust E2E composes the connected frame3d-member, N3-UY nodal-load, and homogeneous N3
fixed-constraint additions before repeating this operation byte-for-byte. It proves source
nonmutation and rejects duplicate pattern IDs, globally duplicate nested-load IDs, missing target
nodes, all-zero/non-finite components, invalid destinations, and invalid source semantics without
publishing partial output.

The test then creates a model-bound request for the new pattern and completes native CPU linear
execution. Typed recovery proves the active DOFs remain exactly N2 indices 6 through 11, the active
`active_external_load` vector is `[2500, 0, 0, 0, 0, 0]`, displacement differs from the supported
`LC_WEAK` baseline, and fallback 0 is preserved.

Static and shared installed-package E2E v26 repeats that composition with an empty `PATH`, validates
the edited model through the installed C++ boundary, compares repeated model, receipt, request,
ResultIR, and recovery trees, and binds all five artifact identities into the authoritative CPU
distribution receipt.

This is not general load authoring, arbitrary solver selection, engineering acceptance, approved
HIP C2, React/TypeScript removal, or C6 decommission.
