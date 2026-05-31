# MIDAS Gen same-mesh result JSON (`midas-gen-same-mesh-result.v1`)

Engineer-in-loop delivery uses this file to compare **licensed MIDAS Gen** (or export-proxy) metrics against in-repo native MGT solves on the **same optimized MGT SHA256**.

## Required top-level fields

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | string | Must be `midas-gen-same-mesh-result.v1` |
| `generated_at` | ISO-8601 UTC | When the export was produced |
| `source` | object | Provenance (see below) |
| `metrics` | object | Global response KPIs (see below) |

## `source` object

| Field | Required | Description |
|-------|----------|-------------|
| `kind` | yes | `midas_gen_live_export` (live Gen run) or `midas_gen_export_proxy` (HF benchmark proxy) |
| `mgt_sha256` | yes | SHA256 of optimized `.mgt` — must match `roundtrip.json` → `source.sha256` |
| `roundtrip_json` | recommended | Path or repo-relative path to paired roundtrip JSON |
| `midas_model_name` | optional | Gen model title |
| `load_case` | optional | e.g. `COMB1`, `EQX` |
| `run_id` | optional | Operator/run trace id |
| `note` | optional | Free text |

Live exports must set `kind: midas_gen_live_export`. Proxy files (CI default) use `midas_gen_export_proxy`.

## `metrics` object (all required)

| Metric | Unit | Typical Gen source |
|--------|------|-------------------|
| `drift_ratio_pct` | % | Story drift / height × 100 |
| `base_shear_kN` | kN | Sum of base reactions (horizontal) |
| `top_displacement_m` | m | Top node displacement magnitude |

Optional extensions (ignored by ingest v1 unless noted):

- `max_story_drift_ratio_pct` — alias accepted by converter only
- `equilibrium_residual` — documentation only

## Example — live MIDAS Gen export

```json
{
  "schema_version": "midas-gen-same-mesh-result.v1",
  "generated_at": "2026-05-31T12:00:00+00:00",
  "source": {
    "kind": "midas_gen_live_export",
    "mgt_sha256": "1538a3cc663e530d52955a4211ca2b37554dca6c76f59a0056a313213beb4eb4",
    "roundtrip_json": "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json",
    "midas_model_name": "midas_generator_33.optimized",
    "load_case": "COMB1",
    "run_id": "gen-run-20260531-001",
    "note": "Exported from MIDAS Gen post-processing; same mesh as optimized MGT."
  },
  "metrics": {
    "drift_ratio_pct": 1.92,
    "base_shear_kN": 1640.0,
    "top_displacement_m": 0.55
  }
}
```

Repo fixture (illustrative, not a real Gen run):  
`implementation/phase1/open_data/midas/midas_generator_33.optimized.midas_gen_same_mesh_result.live.example.json`

## Workflow

1. Run MIDAS Gen on `midas_generator_33.optimized.mgt` (same file as roundtrip SHA).
2. Export KPIs to JSON (manual) or one-row CSV + converter CLI.
3. Validate:

```bash
python3 scripts/validate_midas_gen_same_mesh_result.py \
  --result-json implementation/phase1/open_data/midas/midas_generator_33.optimized.midas_gen_same_mesh_result.json \
  --roundtrip-json implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json
```

4. Re-run delivery comparison:

```bash
python3 scripts/run_midas_gen_same_mesh_native_comparison.py \
  --result-json …/midas_generator_33.optimized.midas_gen_same_mesh_result.json \
  --roundtrip-json …/midas_generator_33.optimized.roundtrip.json \
  --output-json implementation/phase1/release_evidence/productization/midas_gen_same_mesh_native_comparison.json
```

When ingest reports `live_midas_gen_export: true` and comparison `comparison_status` starts with `pass_live`, native pipeline status can upgrade from proxy-bridge to live-aligned receipt.

## CSV → JSON (one-row)

```bash
python3 scripts/convert_midas_gen_table_export_to_result.py \
  --csv path/to/gen_summary.csv \
  --roundtrip-json implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json \
  --kind midas_gen_live_export \
  --output-json implementation/phase1/open_data/midas/midas_generator_33.optimized.midas_gen_same_mesh_result.json
```

CSV header must include: `drift_ratio_pct`, `base_shear_kN`, `top_displacement_m`.
