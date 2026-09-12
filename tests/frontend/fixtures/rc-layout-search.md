# Original layout-search test graph

`rc-layout-search.json.gz` is a gzip-compressed JSON map of original artifact bytes
encoded as base64. `layoutSearchFixture.ts` decodes the map without rewriting JSON
numbers or hashes. It contains 85 files from the portable export recorded in
`docs/engineering/rc-layout-http-20260913.md`.

The result identity is
`sha256:6804c5f19ae7d6526fbabe28c545457ea23b73c86faeada8845b45bf7e7d2b0f`.
The numerical producer source was `218a4c052c350de4f274cb0e387975349b7bfad6`;
the HTTP export added only the original price-table supplement verified against
the existing plan hash. All earlier graph bytes remain unchanged.

This is repository-generated exploratory data derived from the public L-frame
example, not measured external data or proof of independent generalization. Its
budget-two price arm found no feasible selection, while learned order chose
`large` and the later complete-pool comparison chose cheaper `middle`. Browser
verification must preserve this distinction and the original download bytes.
