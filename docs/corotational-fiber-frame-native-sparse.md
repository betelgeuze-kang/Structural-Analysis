# Corotational Fiber-Frame Native Sparse Assembly

The bounded one-bay corotational portal supports a CPU sparse backend identified as
`scipy_sparse_spsolve_cpu`. Each member integrates its stateful consistent tangent
once per trial and scatters only free/free entries into COO triplets. Duplicate
entries are summed, explicit zeros are removed, and column indices are sorted to
form canonical CSR. The Newton solve receives that CSR directly; it is not created
by converting a previously assembled dense global tangent.

Each assembly receipt binds the problem and parent-checkpoint hashes, target load
factor, raw COO entries, canonical CSR row pointers/columns/values, deterministic
pattern and numeric hashes, residual, internal/external loads, reactions, and trial
element-state hashes. Returned NumPy receipt arrays are immutable, and callers get
an independently owned CSR matrix.

`compare_corotational_fiber_frame_dense_sparse_assembly` independently runs the
dense and sparse assemblers at the same trial coordinate. It requires scaled
L-infinity errors no greater than `1e-13` for generalized coordinates, physical
displacements, residual, tangent, internal/external load, and reaction, plus exact
trial-state-hash equality. API tests additionally compare every normalized SI node,
reaction, member, section, and fiber result and replay the sparse checkpoint chain
from epoch zero.

The final accepted-state record is rebuilt through the existing immutable assembly
record for checkpoint commit and exact engineering recovery. This is not a linear
solve fallback: every Newton tangent requested under the sparse backend is assembled
as native COO/CSR, and the contract blocks if that fact is not observed. The result
records backend, storage, sparse-assembly use, fallback, and regularization state.

This slice does not add factorization/conditioning diagnostics, production-scale
performance or memory evidence, general connected topology, member features, direct
displacement control, external Level 2 validation, design authority, or release
authority. Those remain separate roadmap gates.
