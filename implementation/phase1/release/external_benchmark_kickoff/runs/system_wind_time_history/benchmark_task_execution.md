{
  "schema_version": "1.0",
  "generated_at": "2026-03-21T16:52:54.228646+00:00",
  "task_id": "system::wind_time_history",
  "phase": "system_anchor",
  "benchmark_family": "wind_time_history",
  "contract_pass": true,
  "reason_code": "PASS",
  "note": "completed benchmark task system::wind_time_history",
  "artifact_path": "implementation/phase1/release/external_benchmark_kickoff/runs/system_wind_time_history/benchmark_task_result.json",
  "execution_payload": {
    "executor": "system_anchor_report_validation",
    "report_path": "implementation/phase1/wind_time_history_gate_report.json",
    "artifact": {
      "schema_version": "1.0",
      "generated_at": "2026-03-21T16:52:54.228451+00:00",
      "contract_pass": true,
      "reason_code": "PASS",
      "summary": {
        "benchmark_family": "wind_time_history",
        "source_report_path": "implementation/phase1/wind_time_history_gate_report.json",
        "case_count": 4,
        "summary_head": {
          "selected_case_count": 4,
          "duration_hours": 10.0,
          "time_step_s": 1.0,
          "analysis_stride": 1,
          "effective_time_step_s": 1.0,
          "load_reversal_count": 7560,
          "dominant_frequency_hz": 0.105,
          "preprocess_backend": "rocm_torch_full"
        }
      }
    },
    "summary": {
      "benchmark_family": "wind_time_history",
      "source_report_path": "implementation/phase1/wind_time_history_gate_report.json",
      "case_count": 4,
      "summary_head": {
        "selected_case_count": 4,
        "duration_hours": 10.0,
        "time_step_s": 1.0,
        "analysis_stride": 1,
        "effective_time_step_s": 1.0,
        "load_reversal_count": 7560,
        "dominant_frequency_hz": 0.105,
        "preprocess_backend": "rocm_torch_full"
      }
    },
    "contract_pass": true,
    "reason_code": "PASS"
  }
}