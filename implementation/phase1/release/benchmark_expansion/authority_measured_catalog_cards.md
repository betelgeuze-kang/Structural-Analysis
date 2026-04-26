# Authority/Measured Catalog Cards

Source evidence used only from local repo:
- `implementation/phase1/release/benchmark_expansion/authority_measured_batch.json`
- `implementation/phase1/release/benchmark_expansion/authority_measured_lane.json`
- `implementation/phase1/release/visualization/structural_optimization_viewer.json`

## Green Now

### Atwood
- Badge: `GREEN NOW`
- Readiness: `benchmarked_measured_holdout`
- Strongest evidence: `implementation/phase1/phase3_megastructure_pipeline_report.mgt_smoke2.json`
- Summary: 계측 기반 고층 holdout이 이미 KPI와 noise convergence evidence를 갖춘 상태입니다. A measured high-rise holdout with local KPI and convergence evidence already in place.
- Viewer: `entries/megastructure_zenodo_atwood_highrise_shm_2025.html`

### TPU Wind
- Badge: `GREEN NOW`
- Readiness: `materialized_and_execution_complete_for_mapping`
- Strongest evidence: `implementation/phase1/experiments/by_test/nightly_release_gate/20260322T155138Z/artifacts/external_benchmark_execution_status_manifest.json`
- Summary: 풍동 raw mapping이 isolated와 interference 두 케이스로 이미 실행 완료된 상태입니다. Raw wind mapping is already executed locally for both isolated and interference cases.
- Viewer: `entries/megastructure_tpu_highrise_wind_pressure_and_force.html`

## Yellow Next-Ingest

### KW51
- Badge: `YELLOW NEXT-INGEST`
- Readiness: `materialized_but_benchmark_failing`
- Strongest evidence: `implementation/phase1/hf_benchmark_report.kw51_railway_bridge.json`
- Summary: 브리지 계측 케이스는 이미 로컬에 있으나 KPI benchmark가 아직 실패 중입니다. The bridge-response cases are locally materialized, but the current KPI benchmark still fails.
- Viewer: `entries/megastructure_zenodo_kw51_railway_bridge_monitoring_2025.html`

### USGS NSMP
- Badge: `YELLOW NEXT-INGEST`
- Readiness: `registered_only_adapter_pending`
- Strongest evidence: `implementation/phase1/release/visualization/entries/megastructure_usgs_nsmp_structural_arrays.json`
- Summary: 현재는 catalog와 viewer placeholder만 있는 등록 단계입니다. Today it is still a registered-only structural-array track with no local ingest package yet.
- Viewer: `entries/megastructure_usgs_nsmp_structural_arrays.html`

## Compact Card Schema
- `track_id`: stable track key
- `title`: compact viewer title
- `lane_bucket`: `green_now` or `yellow_next_ingest`
- `lane_badge`: lane chip text for viewer surfacing
- `status_badge`: short state badge per card
- `readiness_label`: exact local readiness label from batch/lane evidence
- `summary_ko_en`: short Korean+English friendly summary
- `strongest_local_evidence_file`: strongest local anchor file
- `why_now`: short prioritization reason
- `next_step`: short next action
- `has_local_materialization`: local materialization exists or not
- `has_local_benchmark_or_execution_evidence`: benchmark or execution proof exists or not
- `direct_model_available`: direct model availability flag
- `optimization_ready`: current optimization-ready flag
- `suggested_viewer_entry_href`: existing viewer entry href if present
