# Korean public-structure open data

Local-first catalog for g2b, LH/SH, KCI, and buildingSMART Korea sources. **No automatic HTTP downloads** — operators attach files under `collected/artifacts/<source_id>/`.

## Catalog generation

Default seed: `korean_source_seed.json` (15 records).

When present, `korean_medium_large_source_seed.json` is merged afterward (deduped by `source_id`) for medium/large building diversity (backlog I5).

```bash
python3 scripts/generate_korean_source_catalog.py
# or
python3 implementation/phase1/open_data/korea/generate_korean_source_catalog.py
```

Flags: `--no-medium-large-seed`, `--medium-large-seed-json`, `--seed-json`, `--out`.

## Medium/large reporting and ingest

```bash
python3 scripts/report_medium_large_korean_sources.py
python3 scripts/run_korean_medium_large_ingest_pipeline.py
```

Operator guide: [docs/korean-medium-large-drawing-data-guide.md](../../../../docs/korean-medium-large-drawing-data-guide.md)

## Collection

```bash
python3 implementation/phase1/open_data/korea/collect_korean_public_structures.py
```
