# Explicit intermediate longitudinal steel layers

Implementation/source execution: `7a55b7f306dd1a1d4f838550cbbc0f08609a48af`.
The public planar ModelIR and canonical RC analysis paths now preserve additional
steel layers between the existing bottom and top layers. This addresses the
[previous input representation gap](rc-perimeter-source-boundary-20260913.md).
It does not reconstruct or validate the Soesianawati specimen.

## Input contract

Add this optional field to a canonical rectangular RC section, or to the
`parameters` of a ModelIR `rectangular_rc_fiber_2d` section:

```json
"intermediate_steel_layers": [
  {"y_m": -0.08, "bar_count": 2},
  {"y_m": 0.08, "bar_count": 2}
]
```

Coordinates use the same section-centroid y axis as existing section fibers.
Each layer uses the existing `bar_area_m2` and steel material; bar counts are
additional to the existing top/bottom counts. Rows must be strictly increasing,
unique and strictly inside the outer layer centroids, with 1–32 rows and 1–64
bars per row. Explicit null/empty lists, booleans, unknown row fields and invalid
positions are rejected before analysis. The JSON schema and semantic ModelIR
validator, both public compilers and the material factory enforce their respective
boundaries. Existing inputs omit the field and retain their section identities.

This is a one-axis fiber projection, not arbitrary 3D bar coordinates. Within-row
transverse placement, individual bar areas, confinement, bond slip, bar buckling,
transverse reinforcement and detailing rules are not added. `cover_m` retains its
existing outer steel-centroid interpretation.

## Analysis, quantities and learning

The adapter/compiler passes every row to the section factory. Layer coordinates,
areas and IDs enter the section contract and checkpoint state. Additional steel
area enters member quantities, cost estimates and candidate volume features.
Both Workbench quantity reconstruction paths validate and count these layers.
Canonical physical identity includes the rows, so equal area at different heights
does not alias to the same physical model.

The current learning feature profile keeps intermediate positions/counts in its
fixed analysis context. A changed intermediate arrangement therefore requires a
matching context and policy; this change does not claim trained generalization
across arbitrary layer layouts. Legacy scalar section-change commands remain
scalar commands. Full-model inputs carry the added layer list; width/count edits
preserve it, and depth/cover edits that put it outside the section fail validation.
No dedicated layer-editing UI or new training corpus is introduced.

## Verification and actual comparison

Python selections: 40 section/design/new-layer tests, then 79 ModelIR, identity,
candidate-learning and public-API regressions. The final new-layer selection
also checks ModelIR rejection and passes 10 tests. There are **119 distinct passing
Python tests**, not 129. Actual integration tests execute the canonical RC path
and public planar dense/extended sparse paths.

TypeScript/build/delivery checks passed. The first frontend selection discovered
only an existing test because the runner uses an explicit file list. Registering
the new file then executed eight layer checks. A separately generated actual
comparison adds one passing frontend case, for **10 distinct frontend tests**
including the existing compatibility case. These are contract tests, not a new
rendered-browser usability or full frontend-suite qualification.

The eight-module mypy command reports 24 errors. A frozen pre-change source run
has the same 24 error messages after excluding file roots and shifted line
numbers. Ruff and formatting pass; mypy is not reported green. Initial new Python
checks used an incorrect result property, and the first actual frontend check
looked for source revision at the wrong report level; both harness errors were
corrected without changing numerical output.

The retained actual comparison starts from the authored cantilever with the two
additional layers above, then changes width from 0.40 to 0.35 m. Both rows execute
the two-step reference analysis and pass internal full-reference verification.
The report records two known solver executions and two reference requests.
Elapsed comparison time was 8.324703329 seconds, a single observation without a
speedup claim.

| Quantity | Baseline | Narrower candidate |
| --- | ---: | ---: |
| Gross concrete volume, m3 | 0.72 | 0.63 |
| Longitudinal steel volume, m3 | 0.013932 | 0.013932 |
| Longitudinal steel mass, kg | 109.3662 | 109.3662 |
| Synthetic material estimate, USD | 290.7324 | 281.7324 |

Synthetic prices are 100 USD/m3 concrete and 2 USD/kg longitudinal steel.
Transverse steel, anchorage, waste, labor and other existing exclusions remain.
These are not quotes or confirmed currency savings. The unmodified generated
report passes the Workbench comparison validator, preserving equal steel mass,
changed concrete cost and the same additional layer list in both models.

The committed 7,087-byte gzip fixture SHA-256 is
`66354a292673dc2c182e5d0a350017591b85c74300c14305fb3fe376fb9a4652`;
the original report SHA-256 is
`163efa5b8f6fcce980b60a25f1c932803c8c439f75a04cfa1775fb08272aef7a`.
The adjacent summary binds the original driver/model/report/protocol and mypy
observations in the local packet. Inventory SHA-256:
`6e728b1bccbbc2e3c7813054fdd2ca4adf0c69249cc8af83963cad4d5abd3d4a`.

Full hosted CI, experimental input reconstruction, independent physical
validation, release acceptance and learned net benefit remain open.
