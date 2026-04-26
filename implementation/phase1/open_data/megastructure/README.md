# Mega-Structure Open Data Alternatives

This folder contains open-source replacement candidates for phase3 mega-structure stress tests when proprietary Shanghai Tower-grade datasets are unavailable.

## Selected candidates

1. **Zenodo Atwood high-rise SHM (recommended real-data first pass)**
- Link: https://zenodo.org/records/16739185
- DOI: 10.5281/zenodo.16739185
- Why: real seismic response data for an instrumented high-rise.

2. **Canton Tower reduced-order SHM benchmark (recommended next-frontier measured megatall pass)**
- Links:
  - https://polyucee.hk/ceyxia/benchmark/benchmark.htm
  - https://polyucee.hk/ceyxia/benchmark/tvtower.htm
  - https://polyucee.hk/ceyxia/benchmark/task_i.htm
- Why: official public megatall benchmark with reduced-order FE/system matrices and measured wind/acceleration records.

3. **Opstool 606m megatall OpenSees model (recommended mega-scale synthetic pass)**
- Link: https://opstool.readthedocs.io/en/stable/src/posts/megatall-building/
- Why: directly useful for 1M+ DOF scale-out and cache stress tests.

4. **Zenodo KW51 full-scale railway bridge monitoring**
- Link: https://zenodo.org/records/16879917
- DOI: 10.5281/zenodo.16879917
- Why: real rail-infrastructure dynamics for railway/tunnel expansion.

5. **San Francisco Tall Building Inventory**
- Link: https://catalog.data.gov/dataset/san-francisco-tall-building-inventory
- Why: city-scale topology/material metadata for active-learning seed generation.

6. **USGS National Strong Motion Project (NSMP)**
- Link: https://www.usgs.gov/programs/earthquake-hazards/national-strong-motion-project
- Why: authoritative structural strong-motion records for dynamic/phase validation.

6. **Canton Tower reduced SHM onboarding stub**
- Link: [canton_tower_reduced_shm.source_manifest.json](canton_tower_reduced_shm.source_manifest.json)
- Why: lightweight manifest/catalog stub for the next megatall SHM intake packet.

## Execution recommendation

- Step 1: Run strict commercial checks with RWTH benchmark cases (`commercial_benchmark_cases.rwth_zenodo.json`).
- Step 2: Use OpenSees shell-beam mix topology for 1M/3M/10M partitioned scale-out.
- Step 3: Expand with Atwood/KW51 only as supplemental domain coverage.
- Constitutive/interaction families: expanded constitutive/interaction families are surfaced explicitly as shared summary lines across the release, committee, and external reports; the same lines are reused as-is.
- Row-provenance sync: the interactive `structural_optimization_viewer.html` Review surface and the row-provenance appendix stay bidirectionally aligned on the same `Hazard` and `Rule Family` slices; the appendix exposes explicit `viewer_row_url` / `viewer_slice_url` reverse-sync links back to the matching viewer row and slice.

Machine-readable catalog: `mega_structure_catalog.json`.

## Canton Tower intake stub

The repo now includes a concrete local intake stub for the public reduced-order Canton Tower benchmark:

- Source-manifest stub:
  [canton_tower_reduced_shm.source_manifest.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/megastructure/canton_tower_reduced_shm.source_manifest.json)
- Manifest helper:
  [prepare_canton_tower_reduced_shm_source_manifest.py](/home/betelgeuze/건축구조분석/implementation/phase1/prepare_canton_tower_reduced_shm_source_manifest.py)

Recommended local landing root:

- `implementation/phase1/open_data/megastructure/canton_tower_reduced_shm/`

Expected artifact groups:

1. `system_matrices.mat`
2. benchmark description PDFs
3. measured response bundles or extracted CSVs

Prepare a local source manifest after downloading the public package:

```bash
python3 implementation/phase1/prepare_canton_tower_reduced_shm_source_manifest.py \
  --input-root implementation/phase1/open_data/megastructure/canton_tower_reduced_shm \
  --out implementation/phase1/open_data/megastructure/canton_tower_reduced_shm.source_manifest.json
```

Then convert local CSV/ZIP measurement slices through the existing generic megastructure converter:

```bash
python3 implementation/phase1/build_cases_from_megastructure_open.py \
  --candidate-id canton_tower_reduced_shm_benchmark \
  --input-path implementation/phase1/open_data/megastructure/canton_tower_reduced_shm \
  --catalog implementation/phase1/open_data/megastructure/mega_structure_catalog.json \
  --require-source-manifest \
  --source-manifest-out implementation/phase1/open_data/megastructure/canton_tower_conversion_report.source_manifest.json \
  --dynamic-out implementation/phase1/spatiotemporal_data/canton_tower_dynamic_cases.jsonl \
  --benchmark-out implementation/phase1/commercial_benchmark_cases.canton_tower_open.json \
  --report-out implementation/phase1/open_data/megastructure/canton_tower_conversion_report.json \
  --case-id-prefix canton_tower_reduced_shm
```

Then derive the reduced-order compare surface from `system_matrices.mat` plus the converted benchmark windows:

```bash
python3 implementation/phase1/run_canton_tower_reduced_order_compare.py \
  --mat-path implementation/phase1/open_data/megastructure/canton_tower_reduced_shm/system_matrices.mat \
  --normalization-report implementation/phase1/open_data/megastructure/canton_tower_reduced_shm/canton_tower_normalization_report.json \
  --conversion-report implementation/phase1/open_data/megastructure/canton_tower_conversion_report.json \
  --benchmark-payload implementation/phase1/commercial_benchmark_cases.canton_tower_open.json \
  --out implementation/phase1/release/benchmark_expansion/canton_tower_reduced_order_compare_report.json
```

Current live artifacts:

- [canton_tower_reduced_shm.source_manifest.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/megastructure/canton_tower_reduced_shm.source_manifest.json)
- [canton_tower_conversion_report.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/megastructure/canton_tower_conversion_report.json)
- [canton_tower_reduced_order_compare_report.json](/home/betelgeuze/건축구조분석/implementation/phase1/release/benchmark_expansion/canton_tower_reduced_order_compare_report.json)

## Local pipeline commands

```bash
# Strict non-toy commercial readiness (RWTH + OpenSees scale-out path)
python implementation/phase1/run_megastructure_commercial_readiness.py \
  --model-cases implementation/phase1/commercial_benchmark_cases.rwth_zenodo.json,implementation/phase1/commercial_benchmark_cases.from_csv.json \
  --target-split all \
  --noise-seeds 11,23,47 \
  --convergence-seeds 11,23,47 \
  --noise-stiffness-levels-pct 0,10 \
  --convergence-stiffness-levels-pct 10 \
  --ci-mode nightly \
  --forbid-toy-cases \
  --require-gpu-strict \
  --out implementation/phase1/commercial_readiness_report.json

# Strict benchmark-breadth probe (adds Atwood measured family)
# Current expected state: breadth + measured-family accuracy + convergence + scaleout all pass,
# so this path is ready to be promoted into the default nightly gate.
python implementation/phase1/run_megastructure_commercial_readiness.py \
  --model-cases implementation/phase1/commercial_benchmark_cases.rwth_zenodo.json,implementation/phase1/commercial_benchmark_cases.from_csv.json,implementation/phase1/commercial_benchmark_cases.atwood_open.json \
  --target-split all \
  --noise-seeds 11,23,47 \
  --convergence-seeds 11,23,47 \
  --noise-stiffness-levels-pct 5,10 \
  --convergence-stiffness-levels-pct 10 \
  --ci-mode nightly \
  --forbid-toy-cases \
  --min-source-families 3 \
  --require-measured-dynamic-targets \
  --min-measured-source-families 2 \
  --min-measured-case-count 6 \
  --require-shell-beam-mix-cases \
  --require-gpu-strict \
  --out implementation/phase1/commercial_readiness_report.strict_breadth.json

# Solver breadth evidence gate (shell + wall + interface-boundary, with contact tracked as an explicit gap)
python implementation/phase1/run_solver_breadth_gate.py \
  --topology-report implementation/phase1/opensees_topology_report.json \
  --pushover-stress-report implementation/phase1/nonlinear_pushover_stress_report.json \
  --flexible-diaphragm-report implementation/phase1/flexible_diaphragm_gate_report.json \
  --ssi-boundary-report implementation/phase1/ssi_boundary_gate_report.json \
  --benchmark-cases implementation/phase1/commercial_benchmark_cases.rwth_zenodo.json,implementation/phase1/commercial_benchmark_cases.from_csv.json,implementation/phase1/commercial_benchmark_cases.atwood_open.json \
  --out implementation/phase1/solver_breadth_report.json

# Multi real-source gate (dual dataset)
python implementation/phase1/run_real_source_multi_gate.py \
  --cases implementation/phase1/commercial_benchmark_cases.rwth_zenodo.json,implementation/phase1/commercial_benchmark_cases.from_csv.json \
  --forbid-toy-markers \
  --out implementation/phase1/real_source_multi_gate_report.json

# Convert open source record into phase1 datasets
python implementation/phase1/build_cases_from_megastructure_open.py \
  --candidate-id zenodo_atwood_highrise_shm_2025 \
  --input-path implementation/phase1/open_data/megastructure \
  --download-if-missing \
  --require-source-manifest \
  --forbid-local-sanity-wave \
  --dynamic-out implementation/phase1/spatiotemporal_data/atwood_dynamic_cases.jsonl \
  --benchmark-out implementation/phase1/commercial_benchmark_cases.atwood_open.json \
  --report-out implementation/phase1/open_data/megastructure/atwood_conversion_report.json \
  --source-manifest-out implementation/phase1/open_data/megastructure/atwood_conversion_report.source_manifest.json

# Run integrated phase3 hardening pipeline (PR mode: 1M/3M + seeds 11/23/47)
python implementation/phase1/run_phase3_megastructure_pipeline.py \
  --candidate-id zenodo_atwood_highrise_shm_2025 \
  --input-path implementation/phase1/open_data/megastructure \
  --opensees-model implementation/phase1/open_data/megastructure/opensees/SCBF16B_shell_beam_mix.tcl \
  --download-if-missing \
  --require-real-source \
  --require-real-topology \
  --require-shell-beam-mix \
  --gpu-strict \
  --ci-mode pr \
  --scale-levels-pr 1000000,3000000 \
  --noise-seeds 11,23,47 \
  --noise-stiffness-levels-pct 5,10 \
  --noise-min-seed-count 3 \
  --summary-out implementation/phase1/phase3_megastructure_pipeline_report.json

# Nightly mode: add 10M DOF gate
python implementation/phase1/run_phase3_megastructure_pipeline.py \
  --candidate-id zenodo_atwood_highrise_shm_2025 \
  --input-path implementation/phase1/open_data/megastructure \
  --opensees-model implementation/phase1/open_data/megastructure/opensees/SCBF16B_shell_beam_mix.tcl \
  --download-if-missing \
  --require-real-source \
  --require-real-topology \
  --require-shell-beam-mix \
  --gpu-strict \
  --ci-mode nightly \
  --scale-levels-nightly 1000000,3000000,10000000 \
  --noise-seeds 11,23,47 \
  --noise-stiffness-levels-pct 5,10 \
  --noise-min-seed-count 3 \
  --summary-out implementation/phase1/phase3_megastructure_pipeline_report.json

# Nightly release runbook (gate + freeze + promotion)
python implementation/phase1/run_nightly_release_gate.py \
  --candidate-id zenodo_atwood_highrise_shm_2025 \
  --input-path implementation/phase1/open_data/megastructure \
  --opensees-model implementation/phase1/open_data/megastructure/opensees/SCBF16B_shell_beam_mix.tcl \
  --download-if-missing \
  --gpu-strict \
  --require-real-topology \
  --require-shell-beam-mix \
  --scale-levels-nightly 1000000,3000000,10000000 \
  --scale-levels-io 1000000,3000000 \
  --noise-seeds 11,23,47 \
  --noise-stiffness-levels-pct 5,10 \
  --noise-min-seed-count 3 \
  --out implementation/phase1/release/nightly_release_gate_report.json
```

If automatic download does not expose CSV/ZIP payloads, provide a local extracted
measurement path directly with `--input-path <dir_or_zip_or_csv>`.
