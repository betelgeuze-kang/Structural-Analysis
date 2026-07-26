# Corotational Fiber-Frame Native Sparse Assembly

The bounded corotational portal path supports a native CPU sparse backend identified as
`scipy_sparse_spsolve_cpu`. Each member integrates its stateful consistent tangent once,
then scatters only free/free entries into COO triplets. Duplicate entries are summed,
explicit zeros are removed, and column indices are sorted to form canonical CSR.

The assembly receipt binds the problem and parent-checkpoint hashes, target load factor,
raw COO entries, canonical CSR row pointers/columns/values, deterministic pattern and
numeric hashes, residual, reactions, and trial element-state hashes. Returned NumPy
arrays are immutable; callers receive a copy of the CSR matrix.

`compare_corotational_fiber_frame_dense_sparse_assembly` independently runs the dense
and sparse assemblers at the same trial coordinate and requires scaled L-infinity errors
no greater than `1e-13` for residual, tangent, internal load, and reaction, plus exact
trial-state-hash equality. The public load path additionally records
`native_sparse_assembly_used`, `sparse_backend_used`, fallback, and regularization state.

The sparse Newton path feeds this CSR directly to the fail-closed factorization and
conditioning contract described in
[Sparse Factorization and Conditioning Diagnostics](sparse-factorization-conditioning-diagnostics.md).

This is bounded numerical candidate evidence. External Level 2 validation and
release/design authority remain later roadmap gates.
