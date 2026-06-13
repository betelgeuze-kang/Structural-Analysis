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

## Operator attachment manifest

Use `operator_attachment_manifest.template.json` as the starting point for source-native real artifacts that should replace metadata-only rows or repo benchmark bridges. Rows are accepted only when `source_id` exists in the catalog, `local_path` exists, `rights_confirmed` is true, and `source_native_artifact` is true.

```bash
python3 scripts/validate_korean_operator_attachment_manifest.py --show-summary
python3 scripts/run_korean_medium_large_ingest_pipeline.py --skip-regenerate --skip-collect
```

The validator writes `operator_attachment_manifest_validation_report.json`. The ingest receipt counts accepted rows only after replaying artifact/header checks.

## Collection

```bash
python3 implementation/phase1/open_data/korea/collect_korean_public_structures.py
```
