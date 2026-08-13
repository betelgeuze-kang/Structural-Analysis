# Native ModelIR terminal topology view v1

## Closed profile

`structural-workbench model-view` renders the geometry of any semantically valid ModelIR v2
document accepted by the current schema and C++ owner. It is independent of the fixed-guided
analysis session and supports the eight tracked positive ModelIR profiles.

```text
structural-workbench model-view MODEL.json
structural-workbench model-view MODEL.json --projection xz
```

The projection vocabulary is closed and case-sensitive: `isometric`, `xy`, `xz`, or `yz`.
`isometric` uses a rational oblique projection rather than a platform trigonometry routine. The
fixed 73-by-25-cell canvas uses ASCII only, emits no ANSI escape or color sequence, and is followed
by complete node coordinates, projected cells, support/load flags, element connectivity, analysis
types, inventory counts, and the exact content/semantic/provenance hashes.

## Authority and failure boundary

Rust strictly parses the input and calls the existing Rust -> C ABI -> C++ validator. Rendering
uses the verified canonical C++ snapshot, not unverified source fields. Contract or semantic
invalidity fails closed. A semantically valid model with an explicit unsupported-feature blocker
remains viewable and displays `Analysis ready: false`; visualization does not erase or promote the
blocker. The bounded view accepts at most 512 nodes and 1,024 elements from a regular non-symlink
ModelIR file of at most 64 MiB.

The output is deterministic UTF-8 text. A final SHA-256 binds every preceding byte. Repetition is
byte-identical in an empty process environment, and the installed distribution E2E exercises all
four projections without Python, Node, a browser, network access, or an external renderer.

## Open boundary

This is a native topology inspection slice, not general visual editing, picking, snapping,
section/property mutation, perspective rendering, hidden-line removal, deformed-shape or modal
animation, scalar contouring, result exploration, accessibility certification, or engineering
acceptance. It does not select or execute a solver. Those broader Workbench and C6 gates remain
open.
