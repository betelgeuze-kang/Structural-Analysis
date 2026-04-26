# Curated Direct Batch for opstool_606m_megatall_model

Selected 5 direct-model cases from local artifacts only. The batch covers all 4 available topology types and both available hazard types, while keeping 2 bridge-ready outrigger variants for immediate optimization follow-through.

## Batch

- Source cases: `implementation/phase1/commercial_benchmark_cases.opstool_nightly.json`
- Comparison report: `implementation/phase1/topk_comparison_experiment_report.opstool_nightly.json`
- Bridge-ready cases in batch: `2/5`
- Public benchmark mirrors in batch: `2/5`
- Topology coverage: `4/4`
- Hazard coverage: `2/2`

## Cases

- `opstool_606m_megatall_model-00020`: `outrigger` / `seismic` / `test`; readiness `benchmark_and_optimization_ready`; bridge `yes`; why: Only bridged test holdout. Keeps the batch anchored to a directly materializable outrigger-seismic case with downstream optimization evidence already present.
  fit: drift err `0.572%`, base shear err `0.179%`, buckling err `0.030%`, residual err `11.035%`.
- `opstool_606m_megatall_model-00009`: `rahmen` / `wind` / `test`; readiness `benchmark_ready_bridge_missing`; bridge `no`; why: Best rahmen-wind test holdout in the public benchmark mirror, giving wind coverage and a direct-model holdout without relying on synthetic-only variants.
  fit: drift err `0.075%`, base shear err `0.183%`, buckling err `0.409%`, residual err `1.930%`.
- `opstool_606m_megatall_model-00019`: `wall-frame` / `wind` / `test`; readiness `benchmark_ready_bridge_missing`; bridge `no`; why: Wall-frame wind test holdout with lower residual than 00010 and inclusion in public_benchmark_cases, making it the stronger wall-frame representative.
  fit: drift err `0.259%`, base shear err `0.005%`, buckling err `0.181%`, residual err `6.897%`.
- `opstool_606m_megatall_model-00027`: `truss` / `seismic` / `train`; readiness `benchmark_ready_bridge_missing`; bridge `no`; why: Only selected truss representative. It extends topology coverage to all four available classes and shows one of the cleanest top-k fits among truss cases.
  fit: drift err `0.014%`, base shear err `0.127%`, buckling err `0.344%`, residual err `1.063%`.
- `opstool_606m_megatall_model-00008`: `outrigger` / `seismic` / `val`; readiness `benchmark_ready_with_bridge_for_pre_holdout_optimization`; bridge `yes`; why: Bridge-ready validation variant. Complements 00020 by giving a non-test outrigger-seismic case for pre-holdout tuning and optimization dry runs.
  fit: drift err `0.523%`, base shear err `0.152%`, buckling err `0.003%`, residual err `10.285%`.

## Next Commands

- `materialize_batch_subset`: `jq --argfile batch implementation/phase1/release/benchmark_expansion/opstool_direct_batch.json '($batch.batch_cases | map(.case_id)) as $ids | .cases |= [ .cases[] | select(.case_id as $id | $ids | index($id)) ] | .public_benchmark_cases |= [ (.public_benchmark_cases // [])[] | select(.case_id as $id | $ids | index($id)) ] | .split_counts = (reduce .cases[] as $c ({}; .[$c.split] = ((.[ $c.split ] // 0) + 1)))' implementation/phase1/commercial_benchmark_cases.opstool_nightly.json > implementation/phase1/release/benchmark_expansion/opstool_direct_batch.materialized_cases.json`
- `rerun_batch_topk`: `python3 implementation/phase1/benchmark_kpi_contract.py --cases implementation/phase1/release/benchmark_expansion/opstool_direct_batch.materialized_cases.json --out implementation/phase1/release/benchmark_expansion/opstool_direct_batch.benchmark_report.json --comparison-out implementation/phase1/release/benchmark_expansion/opstool_direct_batch.topk_comparison.json --target-split all --epochs 250 --branches 64 --top-k 8 --seed 23 --max-drift-error-pct 6.0 --max-base-shear-error-pct 5.0 --min-mode-shape-mac 0.97 --max-buckling-factor-error-pct 5.0 --require-direct-metrics --accepted-metric-sources open_data_measurement`
- `run_batch_noise_convergence`: `python3 implementation/phase1/run_noise_convergence_gate.py --cases implementation/phase1/release/benchmark_expansion/opstool_direct_batch.materialized_cases.json --target-split all --limit-cases 5 --seeds 11,17,23 --stiffness-noise-levels 0,1,2,3,5 --out implementation/phase1/release/benchmark_expansion/opstool_direct_batch.noise_convergence.json`

Per-case follow-up commands are listed in `opstool_direct_batch.json` under `batch_cases[].next_commands`.
