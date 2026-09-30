# Perimeter reinforcement is not a two-row count substitution

Review source: `1c3c51e1e45602f515afb29b6a58d1c087752503`.
The earlier [Soesianawati correspondence](soesianawati-nist-correspondence-20260910.md)
remains incomplete. Fresh requests to the CiteSeerX report URL and its identified
Wayback snapshot both returned HTTP 404. Search indexing is not acquired text;
neither request supplies the original 1986 thesis or additional specimen geometry.

The official [1986 study-group report](https://bulletin.nzsee.org.nz/article/view/830/805)
was acquired separately (9,188,627 bytes, SHA-256
`b36d9e606da973e3598aab801e5bb254d20da581521374ad6e25f8f451e7e520`).
PDF pages 1 and 15 were rendered and visually reviewed. Printed p.285 lists Park,
Priestley and Soesianawati among the participants; p.299 distinguishes confinement,
compression-bar restraint and shear requirements in discussing limited ductility.
This is a related study-group publication, not the thesis or an additional
independent specimen campaign. It supplies no replacement No.1 reinforcement
coordinates. No redistribution license is inferred from access; the PDF remains
in the local research packet rather than Git.

## Verified implementation boundary

`bounded_planar_model_ir._canonical_section` passes `top_bar_count`,
`bottom_bar_count`, a common bar area and `cover_m`. The public nonlinear compiler
uses `make_rectangular_stateful_rc_fiber_section`, which builds two steel fibers:
all bottom bars at `-depth/2+cover` and all top bars at `depth/2-cover`.
Thus this cover is an extreme steel-layer centroid offset, not clear cover to
transverse reinforcement. The earlier NIST review's 13 mm transverse clear cover
must not be inserted without a documented conversion.

The lower-level `StatefulRCFiberSection` can hold additional steel fibers, but
that does not make arbitrary perimeter layouts available through the public
ModelIR/quantity/search interfaces. Representing twelve perimeter bars as six
upper and six lower bars preserves steel area while changing its distribution.

A new authored regression in `tests/test_stateful_fiber_section.py` demonstrates
the distinction without claiming specimen reconstruction. Both sections have
identical concrete and twelve equal-area bars. One places six bars at each of
`y=±s`; the other places four at each extreme and two at each of `y=±s/3`.
Their steel area and initial axial stiffness agree. Their steel bending terms are
`12*A*s^2` and `(8+4/9)*A*s^2`, giving a ratio `27/19`, approximately 1.42105.
The test checks the actual initial tangent, distinct section identities and
rejection of the other layout's parent state. This is a manufactured elastic
section check, not a 42% estimate of the error for Soesianawati No.1, total RC
stiffness, nonlinear strength, or measured response.

The complete section module selection passes **10 tests in 1.69 seconds**;
Ruff and formatting pass. No structural load-path solve, external calibration or
training fit was performed in this source review. Product behavior is unchanged.

## Next implementation and admission requirements

Intermediate steel layers need an explicit representation propagated through
canonical ModelIR validation, adapter/compiler construction, section identity,
quantity/cost reconstruction, design-change contracts and review/export. Preserve
legacy two-row identities when the additional representation is absent. Reject
ambiguous simultaneous count/layer descriptions, duplicate/out-of-bounds rows and
inconsistent areas before analysis. Test equal-area/different-layout cases and
actual full-path result bindings; a lower-level helper alone is not completion.

For the external case, separately retain the unresolved source coordinates,
confined/unconfined concrete mapping, measured material law, loading and geometric
force convention, unsupported buckling/fracture mechanisms and acquisition/license
provenance. These inputs are not replaced by fitting a curve or a synthetic layout.
No experimental rows are admitted, and independent validation remains open.

The adjacent summary identifies the local packet, both failed fetches, acquired
PDF/text and rendered pages. Inventory SHA-256:
`b9c7b406e4bc5789ff7e447e018db2cdf0b305abb8faa6263ae51cae9a856c5f`;
10 files / 11,288,419 bytes excluding the inventory. Only pages 1 and 15 were
visually reviewed; pages 21 and 28 were rendered by the heading search but are
not used as inspected evidence.
