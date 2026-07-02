# P1 Benchmark Breadth Status

- Benchmark inputs ready: `True`
- P1 benchmark execution unblocked: `False`
- P0 release blocker: `True`
- P1 work slice: `quality/fallback/benchmark breadth`
- Next action: `close P0-1 release publication before running P1 benchmark breadth`

| Gate | Status | Evidence |
| --- | --- | --- |
| P1 execution prerequisite | `blocked` |  |
| Commercial readiness breadth | `ready` | commercial_readiness_report.json |
| External benchmark submission queue | `ready` | external_benchmark_submission_readiness.json |
| hf benchmark report | `ready` | hf_benchmark_report.json |
| hf benchmark report.rwth zenodo | `ready` | hf_benchmark_report.rwth_zenodo.json |
| hf benchmark report.from csv | `ready` | hf_benchmark_report.from_csv.json |
| hf benchmark report.atwood open | `ready` | hf_benchmark_report.atwood_open.json |
| hf benchmark report.opstool pr | `ready` | hf_benchmark_report.opstool_pr.json |
| hf benchmark report.opstool nightly | `ready` | hf_benchmark_report.opstool_nightly.json |
| tpu hffb benchmark gate report | `ready` | tpu_hffb_benchmark_gate_report.json |
| peer spd hinge benchmark gate report | `ready` | peer_spd_hinge_benchmark_gate_report.json |
| irregular top5 execution manifest | `ready` | Irregular top5 execution manifest: PASS | top5=5 | native_roundtrip_candidates=18 | solver_benchmark_candidates=13 | ai_learning_candidates=32 |
| korean public structure collection report | `ready` | Korean source collect: PASS | sources=22 | collected=10 | metadata_only=12 | rejected=0 | bytes=6628988 | seed_complete=22 | exact_topology=7 | native_writeback=7 | curated_local_ifc=5/7 | p0_focus=18 |
