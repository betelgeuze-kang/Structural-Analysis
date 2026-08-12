use std::path::{Path, PathBuf};

use serde_json::Value;
use structural_contracts::solver_cpu::{
    parse_nonlinear_ndtha_cpu_case_v1, ExecutionBackendV1, NONLINEAR_NDTHA_CPU_SCHEMA_V1,
};

const FIXTURES: [&str; 5] = [
    "nonlinear_ndtha_one_story_elastic_python_c1.json",
    "nonlinear_ndtha_elastic_pdelta_python_c1.json",
    "nonlinear_ndtha_plastic_backtrack_python_c1.json",
    "nonlinear_ndtha_adaptive_retry_python_c1.json",
    "nonlinear_ndtha_collapse_python_c1.json",
];

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

fn fixture_bytes(index: usize) -> Vec<u8> {
    std::fs::read(
        repository_root()
            .join("native/tests/fixtures/solver_cpu")
            .join(FIXTURES[index]),
    )
    .expect("tracked solver CPU fixture")
}

#[test]
fn all_nonlinear_ndtha_product_goldens_are_strict_typed_round_trips() {
    for (index, fixture) in FIXTURES.iter().enumerate() {
        let case = parse_nonlinear_ndtha_cpu_case_v1(&fixture_bytes(index))
            .unwrap_or_else(|error| panic!("{fixture}: {error}"));
        assert_eq!(case.schema_version, NONLINEAR_NDTHA_CPU_SCHEMA_V1);
        assert_eq!(case.operation, "nonlinear_ndtha");
        assert_eq!(case.result.execution_backend, ExecutionBackendV1::Cpu);
        assert_eq!(case.result.fallback_count, 0);
        let encoded = serde_json::to_vec(&case).expect("serialize typed product golden");
        assert_eq!(
            parse_nonlinear_ndtha_cpu_case_v1(&encoded).expect("reparse typed product golden"),
            case
        );
    }
}

#[test]
fn product_wire_rejects_duplicate_unknown_and_nonfinite_values() {
    let duplicate = br#"{
        "schema_version":"structural-solver-cpu-nonlinear-ndtha.v1",
        "schema_version":"structural-solver-cpu-nonlinear-ndtha.v1"
    }"#;
    let error = parse_nonlinear_ndtha_cpu_case_v1(duplicate).expect_err("duplicate key");
    assert_eq!(error.code, "solver_cpu_duplicate_json_key");

    let mut unknown: Value = serde_json::from_slice(&fixture_bytes(0)).expect("fixture JSON");
    unknown["config"]["implicit_default"] = Value::Bool(true);
    let error = parse_nonlinear_ndtha_cpu_case_v1(&serde_json::to_vec(&unknown).expect("JSON"))
        .expect_err("unknown field");
    assert_eq!(error.code, "solver_cpu_schema_invalid");

    let error = parse_nonlinear_ndtha_cpu_case_v1(
        br#"{"schema_version":"structural-solver-cpu-nonlinear-ndtha.v1","operation":"nonlinear_ndtha","config":{"dt_s":NaN}}"#,
    )
    .expect_err("non-finite JSON token");
    assert_eq!(error.code, "solver_cpu_invalid_json");
}

#[test]
fn product_wire_rejects_vector_and_terminal_state_mismatches() {
    let mut mismatch: Value = serde_json::from_slice(&fixture_bytes(1)).expect("fixture JSON");
    mismatch["inputs"]["ag_g"] = serde_json::json!([0.0, 0.01]);
    let error = parse_nonlinear_ndtha_cpu_case_v1(&serde_json::to_vec(&mismatch).expect("JSON"))
        .expect_err("step vector mismatch");
    assert_eq!(error.code, "solver_cpu_vector_length_mismatch");

    let mut terminal: Value = serde_json::from_slice(&fixture_bytes(4)).expect("fixture JSON");
    terminal["result"]["collapse_step"] = Value::from(-1);
    let error = parse_nonlinear_ndtha_cpu_case_v1(&serde_json::to_vec(&terminal).expect("JSON"))
        .expect_err("impossible collapse state");
    assert_eq!(error.code, "solver_cpu_terminal_state_invalid");
}

#[test]
fn product_schema_is_packaged_and_names_the_bounded_cpu_contract() {
    let schema = std::fs::read_to_string(
        Path::new(env!("CARGO_MANIFEST_DIR")).join("schemas/nonlinear_ndtha_cpu_v1.schema.json"),
    )
    .expect("packaged product schema");
    assert!(schema.contains(NONLINEAR_NDTHA_CPU_SCHEMA_V1));
    assert!(schema.contains("total_line_search_backtracks"));
    assert!(schema.contains("fallback_count"));
}
