# Exact measured row subsequences cannot cross learning splits

Source `e281ebb1f488cc295a9bada3d6d32b7d8ea6dff1` closes an exact row-deletion
alias in the measured-source split screen. A shorter copy of a response could
previously pass after campaign names changed: original-file, whole-content and
whole-channel hashes differed. The new check rejects a complete shorter paired
force/displacement sequence found in the longer sequence in the same order,
before compilation, structural execution, fitting or study output.

Both channels must vary. Matching advances only when displacement and force
match together at one row. Each repeated observation consumes a distinct source
row. Separate channel matches, shared loading, constant preload, reordered rows
and nearby but unequal numbers do not establish this witness. Unit conversion
and decimal comparison remain exact, including under a short ambient decimal
precision. No physical tolerance, interpolation or rounding equivalence is added.

Whole-content identities remain unchanged. The split report is now v3 and
explicitly separates exact row-subsequence screening from unverified rounded or
interpolated equivalence. A rejection retains both case/source identities,
channel IDs, point counts, first/last matched source indices and a SHA-256 of the
complete ordered zero-based index sequence. This is a conservative overlap
witness, not authentication of the specimen, sensor pair or campaign.

The screen retains nonconstant response-channel values per source, deduplicating
identical channels. It checks different-length records across different splits;
same-length exact matches continue through the existing channel hashes. Cost
scales with compared response-channel pairs and history lengths, and is charged
in `screen_wall_ns`. This observation is not a large-corpus scaling benchmark.
Same-partition reuse is allowed without additional independence credit; later
cross-partition records still compare against the earlier sources.

## Focused checks and actual-source observation

The old source at `efb3d189f1ab9fe91a66102eeb8214eff81c8772` accepts an authored
6-row/3-row split alias. The new measured split/workbook selection passes **45
tests in 1.82 s**, including actual learning-entry rejection before compile,
solve, fit or output; both encounter orders; changed units/columns; ambiguous
individual channel matches; duplicate multiplicity; reordered and rounded
values; constant channels; and subsequent overlap after same-partition reuse.
Ruff, format and diff checks pass. Scoped mypy passes after adding annotations
for two new retained-channel collections.

A separate observation uses the sealed [Soesianawati source intake](soesianawati-source-correspondence-20260910.md).
The original PEER No. 1 history has 744 pairs. Local audit XLSX conversions
retain every original numeric token and explicitly declared units. An exact
548-row derivative selects indices `0`, then `42..588`, with exact mm-to-m
conversion. These workbooks are locally generated audit derivatives, not new
publications or admitted training samples.

All source tokens and every selected SI pair are checked using independent
rational arithmetic. Whole-content identities agree between old and new code.
The old screen accepts the cross-split full/derivative pair; the new screen
rejects both orders. An independent paired sequence reconstruction checks the
complete index witness. Duplicate values may admit an earlier equivalent match,
so a greedy content witness is not automatically the source's historical
selection provenance. Same-training-partition reuse passes.

The actual SimCenter CSV spellings are also retained in a separate local
workbook conversion. **With falsely different campaign labels, that rounded
548-row input is not detected by the exact row screen.** With the known common
campaign retained, the existing campaign check rejects it. The reviewed source
relationship must therefore remain in the data registry; this implementation
does not replace source review or solve general transformed-data identification.
No rounded values were silently changed to make this boundary test pass.

The successful audit takes **0.424760339 s** internally; the two new rejection
screens take **6.155043 ms** and **6.237045 ms** on the shared local host. There
are zero structural calls and zero training fits. These are input-screen costs,
not nonlinear-analysis acceleration. An initial attempt failed before source
reading because it used the wrong sibling inventory suffix; its source and log
are retained. The corrected attempt verifies the existing inventory hash before
copying any original input.

## Retained evidence and scope

[Machine summary](measured-row-subsequence-20260910.summary.json) binds the code,
source inventory, outcomes and limitations. The sealed local packet is
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-measured-row-subsequence-wmm8qizn`:
21 files, 157,344 bytes; sibling inventory SHA-256
`67eff605fd63c023755a6559b2aece9ccc67856c81b8a31095e1226678929983`.
All files were reread and hash-checked. Current split/test/decoder copies match
Git source e281ebb1f; the prior implementation, original inputs, derivatives,
full matched-index witnesses, audit code and terminal logs are retained.

No experiment is calibrated or admitted to learning by these checks. Physical
model compatibility, independent campaign provenance, transformed-data lineage,
full repository verification and actual learned net benefit remain open. The
running 32-path secant-abstention experiment uses its earlier frozen source and
is unaffected by this input-screen change.
