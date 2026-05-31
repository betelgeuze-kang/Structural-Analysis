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
| `kind` | yes | `midas_gen_live_export` (live Gen run), `midas_gen_export_proxy` (HF benchmark proxy), or `model_derived_estimate` (in-repo extraction from MGT mass/geometry) |
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

## Install live result (canonical path)

```bash
python3 scripts/install_midas_live_same_mesh_result.py \
  --live-result-json path/to/your_live_export.json
```

This validates `midas_gen_live_export` + SHA256 match, then copies to  
`implementation/phase1/open_data/midas/midas_generator_33.optimized.midas_gen_same_mesh_result.json`.

CI/demo without a real Gen run:

```bash
export PHASE1_USE_MIDAS_LIVE_RESULT=1
python3 scripts/run_delivery_evidence_bundle.py
```

Uses the illustrative live fixture (`*.live.example.json`) via resolver — not a substitute for real Gen metrics in production sign-off.

## CSV → JSON (one-row)

```bash
python3 scripts/convert_midas_gen_table_export_to_result.py \
  --csv path/to/gen_summary.csv \
  --roundtrip-json implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json \
  --kind midas_gen_live_export \
  --output-json implementation/phase1/open_data/midas/midas_generator_33.optimized.midas_gen_same_mesh_result.json
```

CSV header must include: `drift_ratio_pct`, `base_shear_kN`, `top_displacement_m`.

## Model-derived estimate (no Gen license)

When MIDAS Gen is unavailable, extract real same-mesh quantities directly from the MGT:

```bash
python3 scripts/extract_midas_gen_same_mesh_result.py \
  --output-json implementation/phase1/open_data/midas/midas_generator_33.optimized.midas_gen_same_mesh_result.model_derived.json
```

- `seismic_weight_kN` = Σ(nodal mass) × g — **rigorous** (from `*NODALMASS`)
- `base_shear_kN` = `Cs` × W — `Cs` from `implementation/phase1/open_data/kds/seismic_design_params.json` (`Cs = SDS/(R·Ie)`) or `--seismic-cs` / `PHASE1_MIDAS_SEISMIC_CS`
- `drift_ratio_pct` — from condensed story NDTHA when `--condensed-solve-json` is passed (**medium** confidence); else code-target placeholder

For `midas_generator_33.optimized` this extraction reports a **low-rise (H≈9.35 m), gravity-dominant** structure with W≈94,150 kN — confirming the earlier proxy KPIs (drift 1.95%, shear 1657 kN) were placeholders not matched to this model.
