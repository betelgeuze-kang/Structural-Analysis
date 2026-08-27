# MGT Import Health Current-Source Evidence

`MGT Import Health Current Source` is the exact-`main`, GitHub-hosted lane for
the MGT parser/import-health corpus. It runs the existing
`parse_midas_mgt_to_json_npz.py` parser against every credited source, binds
the result to the current commit, verifies source-record and entity accounting,
and executes a live deleted-node silent-loss mutation through the parser for
every case. The mutated raw input is removed immediately; its parser report and
stable semantic digest remain in the JSON-only evidence bundle.

The current tracked repository contains **9**, not 10, independent source/model
lineages under the conservative credit policy. Duplicate bytes, optimized or
load-combination variants of `midas_generator_33`, Korean benchmark-bridge
copies, collection/probe copies of the GTC inputs, and semantic mutations of
the `foundation_small` fixture do not receive extra case credit.

The nine-case technical result is:

- 2 clean parser passes;
- 5 dirty parser passes with every unsupported/unclassified row visible;
- 2 dirty fail-closed parser rejections with every skipped element row visible;
- 9/9 source hashes, record/entity accounting checks, and negative mutations;
- 0/9 reviewed redistribution or commercial-use rights; and
- 9/10 independent-case target, so the ten-case gate remains blocked.

The manifest is
`benchmarks/import_health/mgt_current_source.v1.json`. Both it and the runtime
receipt use strict Draft 2020-12 schemas. Runtime parser reports and the
attestation bundle are uploaded from `.ci/mgt-import-health-current-source`;
raw MGT files are not copied into the workflow artifact.

## Local replay

Run from a clean exact checkout:

```bash
source_sha="$(git rev-parse HEAD)"
python scripts/build_mgt_import_health_current_source_receipt.py \
  --source-commit-sha "$source_sha" \
  --fail-available-blocked
python scripts/build_mgt_import_health_current_source_receipt.py \
  --source-commit-sha "$source_sha" \
  --check
```

To require the still-open ten-case target as well, add
`--fail-target-blocked`. That command currently exits nonzero by design.

## Exact tenth-case blocker

The blocker ID is `mgt_import_health_independent_source_10_missing`. Technical
target closure
requires one additional tracked source-native `.mgt` whose bytes and
source/model lineage differ from all nine credited rows. Its manifest row must
identify the source owner or licensor, immutable provenance, expected SHA-256
and byte length, and a recorded rights basis. The target gap must also clear its
blocker ID and set artifact, owner, and rights-basis conditions true. These
conditions do not themselves grant redistribution or commercial authority.
After attaching that row, rerun:

```bash
python scripts/build_mgt_import_health_current_source_receipt.py \
  --source-commit-sha "$(git rev-parse HEAD)" \
  --fail-available-blocked \
  --fail-target-blocked
```

Until the artifact and owner/rights record both exist, the receipt keeps
`artifact_attached`, `source_owner_identified`, and `rights_basis_recorded`
false.

Independent credit is checked at four layers: declared lineage, exact source
SHA-256, comment-insensitive source-record fingerprint, and a normalized
node/element model-identity fingerprint that ignores source row ordering and
material/section property changes. Consequently, a copied model with a renamed
lineage, changed comment, row reorder, or property-only rewrite cannot become
the tenth independent case. Receipt
checking recomputes these identities, source classification, row/entity
accounting, negative mutations, rights/owner fields, and parser-report hashes
from the current tracked artifacts.

## Claim boundary

A passing nine-case receipt proves same-operator technical execution and that
unsupported, skipped, or rejected records remain visible. It does not prove
that dirty cases were losslessly imported. It grants no solver-ready import,
design, independent V&V, legal, redistribution, commercial-use, or release
authority. The GitHub attestation establishes workflow provenance only; it
does not change those authority fields.
