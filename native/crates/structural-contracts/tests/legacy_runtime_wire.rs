use std::path::{Path, PathBuf};

use serde_json::Value;
use structural_contracts::legacy_runtime::{
    parse_legacy_runtime_case_v3, LegacyRuntimeCaseV3, LEGACY_RUNTIME_SCHEMA_V3,
};

const FIXTURES: [&str; 4] = [
    "native/tests/fixtures/legacy_runtime_v3/track_point_load.json",
    "native/tests/fixtures/legacy_runtime_v3/inplace_scale_f32.json",
    "native/tests/fixtures/legacy_runtime_v3/nonlinear_static.json",
    "native/tests/fixtures/legacy_runtime_v3/nonlinear_ndtha.json",
];

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

fn fixture_bytes(index: usize) -> Vec<u8> {
    std::fs::read(repository_root().join(FIXTURES[index])).expect("tracked fixture")
}

#[test]
fn all_four_runtime_families_are_strict_typed_golden_data() {
    let parsed = FIXTURES
        .iter()
        .enumerate()
        .map(|(index, _)| parse_legacy_runtime_case_v3(&fixture_bytes(index)).expect("valid case"))
        .collect::<Vec<_>>();

    assert!(matches!(parsed[0], LegacyRuntimeCaseV3::Track(_)));
    assert!(matches!(parsed[1], LegacyRuntimeCaseV3::InplaceScale(_)));
    assert!(matches!(parsed[2], LegacyRuntimeCaseV3::NonlinearStatic(_)));
    assert!(matches!(parsed[3], LegacyRuntimeCaseV3::NonlinearNdtha(_)));
    for case in parsed {
        let encoded = serde_json::to_vec(&case).expect("serialize typed case");
        let reparsed = parse_legacy_runtime_case_v3(&encoded).expect("reparse typed case");
        assert_eq!(reparsed, case);
    }
}

#[test]
fn wire_contract_rejects_duplicate_unknown_nonfinite_and_unknown_status() {
    let duplicate = br#"{
        "schema_version":"structural-runtime-compat.v3",
        "schema_version":"structural-runtime-compat.v3"
    }"#;
    let error = parse_legacy_runtime_case_v3(duplicate).expect_err("duplicate key");
    assert_eq!(error.code, "legacy_runtime_duplicate_json_key");

    let mut unknown: Value = serde_json::from_slice(&fixture_bytes(0)).expect("fixture JSON");
    unknown["config"]["implicit_default"] = Value::Bool(true);
    let error = parse_legacy_runtime_case_v3(&serde_json::to_vec(&unknown).expect("JSON"))
        .expect_err("unknown field");
    assert_eq!(error.code, "legacy_runtime_schema_invalid");

    let error = parse_legacy_runtime_case_v3(
        br#"{"schema_version":"structural-runtime-compat.v3","operation":"track_point_load","config":{"length_m":NaN}}"#,
    )
    .expect_err("non-finite JSON token");
    assert_eq!(error.code, "legacy_runtime_invalid_json");

    let mut unknown_status: Value =
        serde_json::from_slice(&fixture_bytes(2)).expect("fixture JSON");
    unknown_status["result"]["status_code"] = Value::from(-999);
    let error = parse_legacy_runtime_case_v3(&serde_json::to_vec(&unknown_status).expect("JSON"))
        .expect_err("unknown status");
    assert_eq!(error.code, "legacy_runtime_schema_invalid");
}

#[test]
fn declared_story_and_step_counts_fail_closed_on_vector_mismatch() {
    let mut static_case: Value = serde_json::from_slice(&fixture_bytes(2)).expect("fixture JSON");
    static_case["inputs"]["floor_load_n"] = serde_json::json!([10_000.0, 8_000.0]);
    let error = parse_legacy_runtime_case_v3(&serde_json::to_vec(&static_case).expect("JSON"))
        .expect_err("static vector mismatch");
    assert_eq!(error.code, "legacy_runtime_vector_length_mismatch");

    let mut ndtha_case: Value = serde_json::from_slice(&fixture_bytes(3)).expect("fixture JSON");
    ndtha_case["result"]["response"]["step_iterations"] = serde_json::json!([1, 1]);
    let error = parse_legacy_runtime_case_v3(&serde_json::to_vec(&ndtha_case).expect("JSON"))
        .expect_err("NDTHA vector mismatch");
    assert_eq!(error.code, "legacy_runtime_vector_length_mismatch");
}

#[test]
fn schema_is_packaged_and_keeps_pointer_addresses_out_of_the_wire() {
    let schema_path =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("schemas/legacy_runtime_v3.schema.json");
    let schema = std::fs::read_to_string(schema_path).expect("packaged schema");

    assert!(schema.contains(LEGACY_RUNTIME_SCHEMA_V3));
    assert!(schema.contains("shared_storage"));
    assert!(!schema.contains("ptr_before"));
    assert!(!schema.contains("ptr_after"));
    assert!(!schema.contains("pointer"));
}
