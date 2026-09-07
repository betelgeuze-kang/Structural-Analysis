# Corotational Fiber-Frame Native Sparse Assembly

The bounded one-bay corotational portal and connected planar load-control path
support a CPU sparse selector identified as `scipy_sparse_spsolve_cpu`. The public
`analyze_planar_frame` wrapper accepts a source-bound
`planar_frame_verified_alpha.v1` ModelIR document and passes the selector through
`PlanarFrameConfig(matrix_backend="scipy_sparse_spsolve_cpu")` to the existing
connected-frame solver. Its Newton solve uses unregularized SuperLU `splu`
with `COLAMD` and fail-closed factorization diagnostics. Each member integrates its
stateful consistent tangent once per trial and scatters only free/free entries into COO triplets. Duplicate
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
records backend, storage, sparse-assembly use, factorization receipt hashes, fallback,
and regularization state. See
[Sparse Factorization and Conditioning Diagnostics](sparse-factorization-conditioning-diagnostics.md).

## Public wrapper integration boundary

`examples/planar_frame_rc_portal.json` is a generated four-node, three-member RC
portal with two fully fixed planar supports, explicit rectangular RC sections,
and one proportional nodal load. The other two nodes constrain only the inactive
out-of-plane DOFs. There are no releases, rigid offsets, distributed loads, or
self-weight in this integration fixture. Its generated-source hash covers the
canonical normalized model excluding the `provenance` object; it is not an
external observation or an independent reference result.

`tests/test_planar_frame_public_sparse_integration.py` exercises the public
verified-alpha wrapper, checks full normalized SI dense/sparse result parity and
source ModelIR bindings, and checks exact prefix and terminal checkpoint replay
within each backend. A changed physical section must reject the previous
candidate's checkpoint before solving. Dense/sparse physical parity does not
require checkpoint bytes to match across backends, and an internally valid
diagnostic failure does not carry numerical or engineering-result authority.
The wrapper validator checks the complete nested unified manifest and its source
and engineering-result bindings, not only the outer hash. Its authority object
must exactly match the six fields emitted by the public builder; rehashing the
outer envelope cannot promote external V&V, design, or release authority, omit an
axis, or add an unrecognized axis. These validation checks leave valid result
manifests, hashes, and checkpoint bytes unchanged.

The exact public conditioning diagnostic remains capped at **256 free
equations**, independently of the connected profile's 128-node/256-member input
bounds. The tests separately check the factorization policy at 256/257 equations
and send an 88-node subdivided portal (258 free equations) through the public
wrapper: it must fail closed before SuperLU factorization, without dense fallback,
regularization, checkpoint export, or authoritative engineering results. These
tests are code contracts, not a claim that the medium/large corpus has executed.

Connected topology and member-feature integration already have separate focused
coverage in `tests/test_unified_nonlinear_frame_api.py`; they are not newly
introduced by this portal fixture. The public verified-alpha API remains
nonlinear load-control only. Direct displacement-control and arc-length remain
experimental and are not promoted by sparse availability.

This slice does not establish production-scale conditioning policy, performance
or memory improvement, independent external Level 2 validation, design authority,
or release authority. Those remain separate roadmap gates.
