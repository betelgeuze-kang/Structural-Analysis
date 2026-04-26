# Authority/Measured Benchmark Batch

Local-only curated batch for `Atwood`, `KW51`, `USGS NSMP`, and `TPU wind`.

| Track | Why it matters | Readiness | Direct model | Optimization | Strongest local evidence |
| --- | --- | --- | --- | --- | --- |
| Atwood | Best local measured high-rise counterweight to the recurring MIDAS building file. | High: measured cases, KPI pass, and noise convergence already exist. | No local direct model; measured-case path only. | Proxy benchmark available, not track-native direct optimization. | `implementation/phase1/phase3_megastructure_pipeline_report.mgt_smoke2.json` |
| KW51 | Expands authority/measured coverage into railway bridge dynamics. | Medium: source/materialization pass exists, but KPI benchmark currently fails. | No local direct model. | Not available today because the current KPI run fails. | `implementation/phase1/hf_benchmark_report.kw51_railway_bridge.json` |
| USGS NSMP | Best cataloged route to widen measured building-response holdouts beyond Atwood. | Low: registered only, adapter pending, no local materialization. | No local direct model. | Not available. | `implementation/phase1/release/visualization/entries/megastructure_usgs_nsmp_structural_arrays.json` |
| TPU wind | Only local authority wind track with isolated + interference high-rise raw HFFB cases. | High: local gate passes and both benchmark executions are completed. | No local direct model; raw mapping only. | Mapping-ready, but not track-native optimization-ready. | `implementation/phase1/experiments/by_test/nightly_release_gate/20260322T155138Z/artifacts/external_benchmark_execution_status_manifest.json` |

## Recommended Batch Read

- Include `Atwood` now as the measured building anchor.
- Include `TPU wind` now as the authority wind anchor.
- Include `KW51` as a tracked-but-yellow infrastructure holdout.
- Keep `USGS NSMP` in the same batch as the explicit next materialization target, not as a green benchmark.

## Next Commands

### Atwood
```bash
/usr/bin/python3 implementation/phase1/build_cases_from_megastructure_open.py --input-path implementation/phase1/open_data/megastructure --candidate-id zenodo_atwood_highrise_shm_2025 --catalog implementation/phase1/open_data/megastructure/mega_structure_catalog.json --dynamic-out implementation/phase1/spatiotemporal_data/atwood_dynamic_cases.jsonl --benchmark-out implementation/phase1/commercial_benchmark_cases.atwood_open.mgt_smoke2.json --report-out implementation/phase1/open_data/megastructure/atwood_conversion_report.json --source-manifest-out implementation/phase1/open_data/megastructure/atwood_conversion_report.source_manifest.json --case-id-prefix zenodo_atwood_highrise_shm_2025 --require-source-manifest --min-topology-types 3 --min-hazard-types 2 --min-material-types 2 --forbid-local-sanity-wave
/usr/bin/python3 implementation/phase1/benchmark_kpi_contract_stub.py --cases implementation/phase1/commercial_benchmark_cases.atwood_open.mgt_smoke2.json --out implementation/phase1/hf_benchmark_report.mgt_smoke2.json --comparison-out implementation/phase1/topk_comparison_experiment_report.mgt_smoke2.json --target-split test --epochs 20 --branches 10 --top-k 3 --lr 0.055 --epsilon 0.11 --temperature 0.32 --seed 23 --max-drift-error-pct 5.0 --max-base-shear-error-pct 5.0 --min-mode-shape-mac 0.85 --max-buckling-factor-error-pct 5.0 --require-direct-metrics --accepted-metric-sources engine_export_direct,commercial_solver_export,open_data_measurement
```

### KW51
```bash
/usr/bin/python3 implementation/phase1/build_cases_from_megastructure_open.py --input-path implementation/phase1/open_data/tunnel --candidate-id zenodo_kw51_railway_bridge_monitoring_2025 --catalog implementation/phase1/open_data/megastructure/mega_structure_catalog.json --dynamic-out implementation/phase1/spatiotemporal_data/kw51_dynamic_cases.jsonl --benchmark-out implementation/phase1/commercial_benchmark_cases.kw51_railway_bridge.json --report-out implementation/phase1/open_data/megastructure/kw51_conversion_report.json --source-manifest-out implementation/phase1/open_data/megastructure/kw51_conversion_report.source_manifest.json --case-id-prefix zenodo_kw51_railway_bridge_monitoring_2025 --require-source-manifest --forbid-local-sanity-wave
/usr/bin/python3 implementation/phase1/benchmark_kpi_contract.py --cases implementation/phase1/commercial_benchmark_cases.kw51_railway_bridge.json --out implementation/phase1/hf_benchmark_report.kw51_railway_bridge.json --comparison-out implementation/phase1/topk_comparison_experiment_report.kw51_railway_bridge.json --target-split test --epochs 120 --branches 10 --top-k 3 --lr 0.06 --epsilon 0.12 --temperature 0.35 --seed 23 --max-drift-error-pct 5.0 --max-base-shear-error-pct 5.0 --min-mode-shape-mac 0.85 --max-buckling-factor-error-pct 5.0 --require-direct-metrics --accepted-metric-sources engine_export_direct,commercial_solver_export,open_data_measurement
```

### USGS NSMP
```bash
/usr/bin/python3 implementation/phase1/build_cases_from_megastructure_open.py --input-path implementation/phase1/open_data/usgs_nsmp --candidate-id usgs_nsmp_structural_arrays --catalog implementation/phase1/open_data/megastructure/mega_structure_catalog.json --dynamic-out implementation/phase1/spatiotemporal_data/usgs_nsmp_dynamic_cases.jsonl --benchmark-out implementation/phase1/commercial_benchmark_cases.usgs_nsmp_structural_arrays.json --report-out implementation/phase1/open_data/megastructure/usgs_nsmp_conversion_report.json --source-manifest-out implementation/phase1/open_data/megastructure/usgs_nsmp_conversion_report.source_manifest.json --case-id-prefix usgs_nsmp_structural_arrays --require-source-manifest --forbid-local-sanity-wave
/usr/bin/python3 implementation/phase1/benchmark_kpi_contract.py --cases implementation/phase1/commercial_benchmark_cases.usgs_nsmp_structural_arrays.json --out implementation/phase1/hf_benchmark_report.usgs_nsmp_structural_arrays.json --comparison-out implementation/phase1/topk_comparison_experiment_report.usgs_nsmp_structural_arrays.json --target-split test --epochs 120 --branches 10 --top-k 3 --lr 0.06 --epsilon 0.12 --temperature 0.35 --seed 23 --max-drift-error-pct 5.0 --max-base-shear-error-pct 5.0 --min-mode-shape-mac 0.85 --max-buckling-factor-error-pct 5.0 --require-direct-metrics --accepted-metric-sources engine_export_direct,commercial_solver_export,open_data_measurement
```

### TPU Wind
```bash
/usr/bin/python3 implementation/phase1/build_wind_raw_mapping_artifact.py --raw-wind implementation/phase1/open_data/wind/tpu/case_616_materialized/tpu_hffb_isolated_highrise_seed_01.csv --raw-wind-manifest implementation/phase1/open_data/wind/tpu/case_616_materialized/tpu_hffb_isolated_highrise_seed_01.source_manifest.json --midas-json implementation/phase1/open_data/midas/midas_model.json --midas-conversion implementation/phase1/midas_mgt_conversion_report.json --wind-gate-report implementation/phase1/wind_time_history_gate_report.json --out implementation/phase1/release/external_benchmark_kickoff/runs/wind_tpu_hffb_isolated_highrise_seed_01/benchmark_task_result.json
/usr/bin/python3 implementation/phase1/build_wind_raw_mapping_artifact.py --raw-wind implementation/phase1/open_data/wind/tpu/case_917_materialized/tpu_hffb_interference_highrise_seed_01.csv --raw-wind-manifest implementation/phase1/open_data/wind/tpu/case_917_materialized/tpu_hffb_interference_highrise_seed_01.source_manifest.json --midas-json implementation/phase1/open_data/midas/midas_model.json --midas-conversion implementation/phase1/midas_mgt_conversion_report.json --wind-gate-report implementation/phase1/wind_time_history_gate_report.json --out implementation/phase1/release/external_benchmark_kickoff/runs/wind_tpu_hffb_interference_highrise_seed_01/benchmark_task_result.json
```

## Bottom Line

- Ship `Atwood` and `TPU wind` as the green anchors in this batch.
- Keep `KW51` in the same manifest as a yellow measured holdout that needs rematerialization and rerun.
- Keep `USGS NSMP` in the batch as the explicit next authority/measured ingest target.
