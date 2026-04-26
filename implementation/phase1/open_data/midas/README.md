# MIDAS `.mgt` Open Data

This directory stores publicly downloadable MIDAS text-model samples used for
parser validation and architecture stress tests.

## Current sample

- File: `midas_generator_33.mgt`
- Upstream repository: `https://github.com/chen39137112/MidasMgtGenerator`
- Upstream file: `https://raw.githubusercontent.com/chen39137112/MidasMgtGenerator/f704e6300795f35d7d7d2c05bce2b9b6a15ccbb1/33.mgt`
- Commit: `f704e6300795f35d7d7d2c05bce2b9b6a15ccbb1`
- SHA256 (local): `269419de4b0ae9aacbfd2aeed05766d2c8bb065f7b64e81fee8c295129bbf2cc`

## Generated artifacts

- `midas_generator_33.json`: parsed model graph + metadata
- `midas_generator_33.npz`: compact tensor graph arrays
- `midas_generator_33_edges.json`: undirected edge list for partition/scale-out

## Rebuild command

```bash
python implementation/phase1/parse_midas_mgt_to_json_npz.py \
  --mgt implementation/phase1/open_data/midas/midas_generator_33.mgt \
  --json-out implementation/phase1/open_data/midas/midas_generator_33.json \
  --npz-out implementation/phase1/open_data/midas/midas_generator_33.npz \
  --report-out implementation/phase1/midas_mgt_conversion_report.json \
  --forbid-synthetic-source \
  --require-shell-beam-mix
```

## Quality Corpus Gate

Use the strict collector to allow only real-source, quality-passed `.mgt` files:

```bash
python implementation/phase1/collect_mgt_quality_corpus.py \
  --catalog implementation/phase1/open_data/midas/quality_mgt_source_catalog.json \
  --out-dir implementation/phase1/open_data/midas/quality_corpus \
  --report-out implementation/phase1/open_data/midas/quality_corpus_report.json \
  --min-node-count 100 \
  --min-element-count 100 \
  --require-shell-beam-mix
```

The collector runs parser validation per source and accepts only entries that
pass all of:
- `contract_pass = true`
- `synthetic_source_blocked = true`
- `shell_beam_mix_pass = true` (when enabled)
- `node_count >= min_node_count`
- `element_count >= min_element_count`
