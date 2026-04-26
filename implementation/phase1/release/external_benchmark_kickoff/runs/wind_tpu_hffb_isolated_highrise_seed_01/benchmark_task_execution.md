{
  "schema_version": "1.0",
  "generated_at": "2026-03-21T16:47:27.620575+00:00",
  "task_id": "wind::tpu_hffb_isolated_highrise_seed_01",
  "phase": "component_wind",
  "benchmark_family": "tpu_raw_hffb_mapping",
  "contract_pass": true,
  "reason_code": "PASS",
  "note": "completed official TPU isolated raw HFFB mapping benchmark",
  "artifact_path": "implementation/phase1/release/external_benchmark_kickoff/runs/wind_tpu_hffb_isolated_highrise_seed_01/benchmark_task_result.json",
  "execution_payload": {
    "executor": "build_wind_raw_mapping_artifact",
    "command": [
      "/usr/bin/python3",
      "implementation/phase1/build_wind_raw_mapping_artifact.py",
      "--raw-wind",
      "implementation/phase1/open_data/wind/tpu/case_616_materialized/tpu_hffb_isolated_highrise_seed_01.csv",
      "--raw-wind-manifest",
      "implementation/phase1/open_data/wind/tpu/case_616_materialized/tpu_hffb_isolated_highrise_seed_01.source_manifest.json",
      "--midas-json",
      "implementation/phase1/midas_model.json",
      "--midas-conversion",
      "implementation/phase1/midas_mgt_conversion_report.json",
      "--out",
      "implementation/phase1/release/external_benchmark_kickoff/runs/wind_tpu_hffb_isolated_highrise_seed_01/benchmark_task_result.json",
      "--wind-gate-report",
      "implementation/phase1/wind_time_history_gate_report.json"
    ],
    "source_manifest_path": "implementation/phase1/open_data/wind/tpu/case_616_materialized/tpu_hffb_isolated_highrise_seed_01.source_manifest.json",
    "raw_wind_path": "implementation/phase1/open_data/wind/tpu/case_616_materialized/tpu_hffb_isolated_highrise_seed_01.csv",
    "stdout": "Wrote wind raw mapping artifact: implementation/phase1/release/external_benchmark_kickoff/runs/wind_tpu_hffb_isolated_highrise_seed_01/benchmark_task_result.json",
    "stderr": "",
    "artifact": {
      "schema_version": "1.0",
      "run_id": "phase3-wind-raw-mapping-artifact",
      "generated_at": "2026-03-21T16:47:27.594553+00:00",
      "inputs": {
        "raw_wind": "implementation/phase1/open_data/wind/tpu/case_616_materialized/tpu_hffb_isolated_highrise_seed_01.csv",
        "raw_wind_manifest": "implementation/phase1/open_data/wind/tpu/case_616_materialized/tpu_hffb_isolated_highrise_seed_01.source_manifest.json",
        "wind_gate_report": "implementation/phase1/wind_time_history_gate_report.json",
        "midas_roundtrip_json": "implementation/phase1/open_data/midas/midas_model.json",
        "midas_conversion_report": "implementation/phase1/midas_mgt_conversion_report.json"
      },
      "summary": {
        "mapping_mode": "raw_hffb_node_pressure_mapping",
        "mapping_row_count": 7278,
        "mapped_node_row_count": 3942,
        "mapped_floor_row_count": 2,
        "pressure_loaded_element_count": 3644,
        "raw_row_count": 32768,
        "raw_pressure_row_count": 32768,
        "pressure_case_counts": {
          "DEAD": 3634,
          "LIVE": 3644
        },
        "wind_gate_contract_pass": true,
        "conversion_pressure_row_count": 7278
      },
      "checks": {
        "raw_manifest_verified": true,
        "pressure_rows_present": true,
        "element_to_node_backreference_present": true,
        "floor_proxy_present": true,
        "pressure_count_matches_conversion_report": true
      },
      "artifacts": {
        "mapping_rows_head": [
          {
            "pressure_row_index": 0,
            "load_case": "DEAD",
            "element_id": 18108,
            "target_node_id": 2146,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 1,
            "load_case": "DEAD",
            "element_id": 18117,
            "target_node_id": 2147,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 2,
            "load_case": "DEAD",
            "element_id": 18128,
            "target_node_id": 2148,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 3,
            "load_case": "DEAD",
            "element_id": 18186,
            "target_node_id": 2156,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 4,
            "load_case": "DEAD",
            "element_id": 18461,
            "target_node_id": 2253,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 5,
            "load_case": "DEAD",
            "element_id": 18525,
            "target_node_id": 2289,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 6,
            "load_case": "DEAD",
            "element_id": 18526,
            "target_node_id": 9,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 7,
            "load_case": "DEAD",
            "element_id": 18531,
            "target_node_id": 14,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 8,
            "load_case": "DEAD",
            "element_id": 18532,
            "target_node_id": 2292,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 9,
            "load_case": "DEAD",
            "element_id": 18534,
            "target_node_id": 2295,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 10,
            "load_case": "DEAD",
            "element_id": 18585,
            "target_node_id": 2412,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 11,
            "load_case": "DEAD",
            "element_id": 18693,
            "target_node_id": 2421,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 12,
            "load_case": "DEAD",
            "element_id": 18706,
            "target_node_id": 2422,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 13,
            "load_case": "DEAD",
            "element_id": 18723,
            "target_node_id": 2421,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 14,
            "load_case": "DEAD",
            "element_id": 18742,
            "target_node_id": 2419,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 15,
            "load_case": "DEAD",
            "element_id": 18773,
            "target_node_id": 2419,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 16,
            "load_case": "DEAD",
            "element_id": 18902,
            "target_node_id": 24,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 17,
            "load_case": "DEAD",
            "element_id": 18925,
            "target_node_id": 2394,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 18,
            "load_case": "DEAD",
            "element_id": 18955,
            "target_node_id": 33,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 19,
            "load_case": "DEAD",
            "element_id": 18979,
            "target_node_id": 2393,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 20,
            "load_case": "DEAD",
            "element_id": 19011,
            "target_node_id": 2318,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 21,
            "load_case": "DEAD",
            "element_id": 19012,
            "target_node_id": 2319,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 22,
            "load_case": "DEAD",
            "element_id": 19029,
            "target_node_id": 2392,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 23,
            "load_case": "DEAD",
            "element_id": 19043,
            "target_node_id": 2328,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 24,
            "load_case": "DEAD",
            "element_id": 19054,
            "target_node_id": 2323,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 25,
            "load_case": "DEAD",
            "element_id": 19063,
            "target_node_id": 2328,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 26,
            "load_case": "DEAD",
            "element_id": 19068,
            "target_node_id": 2332,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 27,
            "load_case": "DEAD",
            "element_id": 19098,
            "target_node_id": 2336,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 28,
            "load_case": "DEAD",
            "element_id": 19100,
            "target_node_id": 2338,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 29,
            "load_case": "DEAD",
            "element_id": 19196,
            "target_node_id": 2318,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 30,
            "load_case": "DEAD",
            "element_id": 19199,
            "target_node_id": 2320,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 31,
            "load_case": "DEAD",
            "element_id": 19200,
            "target_node_id": 2304,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 32,
            "load_case": "DEAD",
            "element_id": 19201,
            "target_node_id": 2309,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 33,
            "load_case": "DEAD",
            "element_id": 19207,
            "target_node_id": 2359,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 34,
            "load_case": "DEAD",
            "element_id": 19494,
            "target_node_id": 15,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 35,
            "load_case": "DEAD",
            "element_id": 20378,
            "target_node_id": 67,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 36,
            "load_case": "DEAD",
            "element_id": 20379,
            "target_node_id": 87,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 37,
            "load_case": "DEAD",
            "element_id": 20380,
            "target_node_id": 70,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 38,
            "load_case": "DEAD",
            "element_id": 20381,
            "target_node_id": 80,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 39,
            "load_case": "DEAD",
            "element_id": 20382,
            "target_node_id": 83,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 40,
            "load_case": "DEAD",
            "element_id": 20383,
            "target_node_id": 104,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 41,
            "load_case": "DEAD",
            "element_id": 20384,
            "target_node_id": 68,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 42,
            "load_case": "DEAD",
            "element_id": 20385,
            "target_node_id": 17,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 43,
            "load_case": "DEAD",
            "element_id": 20386,
            "target_node_id": 92,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 44,
            "load_case": "DEAD",
            "element_id": 20387,
            "target_node_id": 82,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 45,
            "load_case": "DEAD",
            "element_id": 20388,
            "target_node_id": 65,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 46,
            "load_case": "DEAD",
            "element_id": 20389,
            "target_node_id": 71,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 47,
            "load_case": "DEAD",
            "element_id": 20390,
            "target_node_id": 64,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 48,
            "load_case": "DEAD",
            "element_id": 20391,
            "target_node_id": 16,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 49,
            "load_case": "DEAD",
            "element_id": 20392,
            "target_node_id": 74,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 50,
            "load_case": "DEAD",
            "element_id": 20393,
            "target_node_id": 19,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 51,
            "load_case": "DEAD",
            "element_id": 20394,
            "target_node_id": 75,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 52,
            "load_case": "DEAD",
            "element_id": 20395,
            "target_node_id": 77,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 53,
            "load_case": "DEAD",
            "element_id": 20396,
            "target_node_id": 108,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 54,
            "load_case": "DEAD",
            "element_id": 20397,
            "target_node_id": 78,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 55,
            "load_case": "DEAD",
            "element_id": 20398,
            "target_node_id": 88,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 56,
            "load_case": "DEAD",
            "element_id": 20399,
            "target_node_id": 69,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 57,
            "load_case": "DEAD",
            "element_id": 20400,
            "target_node_id": 85,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 58,
            "load_case": "DEAD",
            "element_id": 20401,
            "target_node_id": 106,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 59,
            "load_case": "DEAD",
            "element_id": 20402,
            "target_node_id": 18,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 60,
            "load_case": "DEAD",
            "element_id": 20403,
            "target_node_id": 96,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 61,
            "load_case": "DEAD",
            "element_id": 20404,
            "target_node_id": 90,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 62,
            "load_case": "DEAD",
            "element_id": 20405,
            "target_node_id": 95,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          },
          {
            "pressure_row_index": 63,
            "load_case": "DEAD",
            "element_id": 20406,
            "target_node_id": 72,
            "floor_id": 1,
            "average_z": 0.0,
            "element_type": "PLATE",
            "load_type": "FACE"
          }
        ]
      },
      "contract_pass": true,
      "reason_code": "PASS",
      "reason": "Raw wind series is traceably bridged to MIDAS pressure-loaded elements, nodes, and floor proxies."
    },
    "contract_pass": true,
    "reason_code": "PASS",
    "summary": {
      "mapping_mode": "raw_hffb_node_pressure_mapping",
      "mapping_row_count": 7278,
      "mapped_node_row_count": 3942,
      "mapped_floor_row_count": 2,
      "pressure_loaded_element_count": 3644,
      "raw_row_count": 32768,
      "raw_pressure_row_count": 32768,
      "pressure_case_counts": {
        "DEAD": 3634,
        "LIVE": 3644
      },
      "wind_gate_contract_pass": true,
      "conversion_pressure_row_count": 7278
    }
  }
}