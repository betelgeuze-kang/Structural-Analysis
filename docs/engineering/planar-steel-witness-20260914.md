# Accepted steel witness at the 24 mm refinement discrepancy

A read-only audit of the retained 32/64-layer full displacement paths locates the
largest absolute plastic-strain difference at 24 mm in `E1:gauss-0:top`, integration
coordinate -0.7745966692414834. Path hashes and element/section/fiber bindings to
accepted checkpoints are checked before extracting observations. No solve or fit
is performed. The source files and the numerical 1% screen are unchanged.

Both models first record nonzero plastic strain at this steel point at the
sampled 24 mm target. At 22 mm both points remain elastic (about 229.1 MPa); at
24 mm both yield. Both paths have three yielded steel points at 24 mm, four at
26 mm and five at 28 mm. Thus the witness is not an elastic-versus-plastic label
mismatch at these sampled targets. The actual onset between sampled targets is
not resolved by this audit.

At 24 mm the witness plastic strains are 3.3769139705e-6 (32 layers) and
4.6690716599e-6 (64 layers), differing by 1.2921576894e-6. Total strains are
0.0012535119905 and 0.0012548558345; stresses are 250.0270153 and 250.0373526 MPa.
The full group's finer plastic-strain maximum is 8.5445592590e-5, which produced
the earlier 1.512258% group discrepancy. That percentage is a group-normalized
error, not the witness's own relative error.

This places the retained screen failure near the sampled onset of plasticity.
It does not prove a unique cause, establish exact quadrature error, or justify
loosening the screen. A subsequent reference calculation should preserve this
point and its full preceding history. Endpoint agreement must not erase it.

The audit records the same witness through all forty accepted targets. Packet:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-refinement-steel-witness-51u_bxxg`

Two payload files, 44,193 bytes; inventory SHA-256:
`e2e4f48a83d616ee6bdeb5991eaabda73a3da7818d4adff663e154a23c45768c`.
The retained `audit.py` checks source path identities and regenerates the audit.
No independent physical validation or training-reference qualification follows.
