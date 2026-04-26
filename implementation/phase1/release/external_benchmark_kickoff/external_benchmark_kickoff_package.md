# External Benchmark Kickoff Package

- `generated_at`: `2026-04-11T13:36:55.987292+00:00`
- `reason_code`: `PASS_START_NOW_FULL`
- `recommended_start_mode`: `start_now_full_external_submission`
- `recommended_submission_scope`: `full_external_submission_package`
- `ready_to_start_now`: `True`
- `ready_to_start_full_submission_now`: `True`
- `caution_label`: `panel_zone_external_validation_only_boundary`

## Component Benchmarks

- `wind_component_asset_count`: `2`
- `hinge_component_asset_count`: `5`

### Wind

- `tpu_hffb_isolated_highrise_seed_01` | role=`baseline_isolated_highrise` | split=`val` | signals=`200` | manifest=`implementation/phase1/open_data/wind/tpu/case_616_materialized/tpu_hffb_isolated_highrise_seed_01.source_manifest.json`
- `tpu_hffb_interference_highrise_seed_01` | role=`neighbor_interference_highrise` | split=`holdout` | signals=`252` | manifest=`implementation/phase1/open_data/wind/tpu/case_917_materialized/tpu_hffb_interference_highrise_seed_01.source_manifest.json`

### Hinge

- `peer_spd_rc_column_rectangular_seed_01` | split=`train` | specimen=`121` | points=`1169` | fixture=`implementation/phase1/open_data/pbd_hinge/peer_spd_rc_column_rectangular_seed_01.hinge_fixture.json`
- `peer_spd_rc_column_rectangular_seed_02` | split=`train` | specimen=`29` | points=`721` | fixture=`implementation/phase1/open_data/pbd_hinge/peer_spd_rc_column_rectangular_seed_02.hinge_fixture.json`
- `peer_spd_rc_column_spiral_seed_01` | split=`val` | specimen=`276` | points=`960` | fixture=`implementation/phase1/open_data/pbd_hinge/peer_spd_rc_column_spiral_seed_01.hinge_fixture.json`
- `peer_spd_rc_column_rebar_sensitive_seed_01` | split=`val` | specimen=`121` | points=`1169` | fixture=`implementation/phase1/open_data/pbd_hinge/peer_spd_rc_column_rebar_sensitive_seed_01.hinge_fixture.json`
- `peer_spd_rc_column_holdout_seed_01` | split=`holdout` | specimen=`299` | points=`449` | fixture=`implementation/phase1/open_data/pbd_hinge/peer_spd_rc_column_holdout_seed_01.hinge_fixture.json`

## System Anchors

- `nonlinear_frame` | pass=`True` | cases=`3` | report=`implementation/phase1/nonlinear_frame_engine_report.json`
- `wind_time_history` | pass=`True` | cases=`4` | report=`implementation/phase1/wind_time_history_gate_report.json`
- `ssi_boundary` | pass=`True` | cases=`4` | report=`implementation/phase1/ssi_boundary_gate_report.json`

## Review Boundary

- `pending_packet_count`: `0`
- `pending_packet_label`: `none`

## Next Actions

- start TPU raw HFFB benchmark execution on isolated/interference official cases
- start PEER hinge benchmark execution across train/val/holdout fixture set
