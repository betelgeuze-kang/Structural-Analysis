# Direct Model Green Lane

- lane: `Direct Model Green Lane`
- status: `green`
- case_count: `5`
- topology_coverage: `4/4`
- hazard_coverage: `2/2`
- recommended_first_case: `opstool_606m_megatall_model-00020`

## Exact Next Commands

- `jq --argfile batch implementation/phase1/release/benchmark_expansion/opstool_direct_batch.json '($batch.batch_cases | map(.case_id)) as $ids | .cases |= [ .cases[] | select(.case_id as $id | $ids | index($id)) ] | .public_benchmark_cases |= [ (.public_benchmark_cases // [])[] | select(.case_id as $id | $ids | index($id)) ] | .split_counts = (reduce .cases[] as $c ({}; .[$c.split] = ((.[ $c.split ] // 0) + 1)))' implementation/phase1/commercial_benchmark_cases.opstool_nightly.json > implementation/phase1/release/benchmark_expansion/opstool_direct_batch.materialized_cases.json`
- `python3 implementation/phase1/benchmark_kpi_contract.py --cases implementation/phase1/release/benchmark_expansion/opstool_direct_batch.materialized_cases.json --out implementation/phase1/release/benchmark_expansion/opstool_direct_batch.benchmark_report.json --comparison-out implementation/phase1/release/benchmark_expansion/opstool_direct_batch.topk_comparison.json --target-split all --epochs 250 --branches 64 --top-k 8 --seed 23 --max-drift-error-pct 6.0 --max-base-shear-error-pct 5.0 --min-mode-shape-mac 0.97 --max-buckling-factor-error-pct 5.0 --require-direct-metrics --accepted-metric-sources open_data_measurement`
- `python3 implementation/phase1/run_noise_convergence_gate.py --cases implementation/phase1/release/benchmark_expansion/opstool_direct_batch.materialized_cases.json --target-split all --limit-cases 5 --seeds 11,17,23 --stiffness-noise-levels 0,1,2,3,5 --out implementation/phase1/release/benchmark_expansion/opstool_direct_batch.noise_convergence.json`
