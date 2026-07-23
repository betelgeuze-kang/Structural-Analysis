# Unified Nonlinear Frame API

`analyze_nonlinear_frame` and `structural-analysis-nonlinear-frame` select one
explicit analysis profile while returning the same typed envelope and normalized
SI field names.

| Profile | Current boundary |
| --- | --- |
| `fixed_chord_serial_cantilever.v1` | Existing bounded serial-cantilever Developer Preview |
| `corotational_one_bay_portal.v1` | Four-node, three-member rectangular portal candidate |

The corotational compiler requires exactly two fully fixed bases, proportional
nodal loads, explicit rectangular RC fiber sections, and the supported
steel/concrete laws. Unsupported keys, topology, support, load, material,
section, unit, coordinate, release, offset, distributed-load, or prescribed
displacement semantics fail before solve.

For a ready corotational result, the API binds:

1. the canonical model checksum and portal compiler hash;
2. J1-J5 topology, scaling, state ancestry, solver-state, and convergence receipts;
3. exact terminal-parent engineering replay and immutable SI artifacts;
4. a complete epoch-zero-rooted checkpoint-chain hash and canonical artifact bytes;
5. normalized displacement, reaction, member, section, and fiber rows;
6. an explicit dense or native COO/CSR backend choice with no fallback.

The corotational profile accepts `numpy_linalg_solve_dense` or
`scipy_sparse_spsolve_cpu`. The sparse choice scatters member tangents directly
to COO and canonical sorted CSR; see
[Corotational Fiber-Frame Native Sparse Assembly](corotational-fiber-frame-native-sparse.md).
The fixed-chord profile remains dense-only.

When a restart artifact is supplied, every prefix step is solved again from
genesis and its checkpoint bytes must match before any remaining step runs. A
valid terminal chain therefore replays to identical engineering output. Altered
bytes, model identity, load prefix, parent link, state hash, or non-canonical JSON
fail closed.

The command line writes result, report, and optional checkpoint files atomically:

```bash
structural-analysis-nonlinear-frame \
  examples/public_corotational_rc_portal.json \
  --profile corotational_one_bay_portal.v1 \
  --matrix-backend scipy_sparse_spsolve_cpu \
  --out result.json \
  --report-out report.json \
  --checkpoint-out checkpoint-chain.json
```

The same envelope preserves the existing fixed-chord authority while converting
fiber stress output from MPa to Pa. The corotational endpoint remains a bounded
Developer Preview candidate. General topology, sparse factorization and conditioning
diagnostics, member features, direct displacement control, both
independent Level 2 comparisons, design-code authority, and release promotion
remain separate gates.
