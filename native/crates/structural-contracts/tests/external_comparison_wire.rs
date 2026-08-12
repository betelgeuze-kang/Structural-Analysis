use std::path::{Path, PathBuf};

use serde_json::{json, Value};
use structural_contracts::external_comparison::{
    build_external_comparison_ir_v1, parse_external_comparison_ir_v1, parse_external_result_v1,
    ExternalComparisonStatusV1,
};
use structural_contracts::product_ir::{
    average_step_iterations, build_nonlinear_ndtha_result_ir_v1, parse_native_analysis_request_v1,
    NonlinearNdthaResultIrDocumentV1, NonlinearNdthaResultSummaryV1,
    NonlinearNdthaTerminalStatusV1, ResultIdentityV1,
};
use structural_contracts::solver_cpu::parse_nonlinear_ndtha_cpu_case_v1;

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

fn fixture_bytes() -> Vec<u8> {
    std::fs::read(
        repository_root()
            .join("native/tests/fixtures/external_comparison/reference_oracle_ndtha_v1.json"),
    )
    .expect("tracked external result")
}

fn oracle_bytes() -> Vec<u8> {
    std::fs::read(
        repository_root().join(
            "native/tests/fixtures/solver_cpu/nonlinear_ndtha_one_story_elastic_python_c1.json",
        ),
    )
    .expect("tracked Python C1 oracle")
}

fn result_document() -> NonlinearNdthaResultIrDocumentV1 {
    let request = parse_native_analysis_request_v1(
        &std::fs::read(
            repository_root()
                .join("native/tests/fixtures/product_e2e/nonlinear_ndtha_request.json"),
        )
        .expect("tracked request"),
    )
    .expect("strict request");
    let golden = parse_nonlinear_ndtha_cpu_case_v1(&oracle_bytes()).expect("strict CPU golden");
    let result = golden.result;
    let adaptive_iteration_sum = result
        .response
        .step_iterations
        .iter()
        .take(usize::try_from(result.step_count_completed).expect("step count"))
        .map(|value| u64::from(*value))
        .sum();
    build_nonlinear_ndtha_result_ir_v1(
        &request,
        ResultIdentityV1 {
            request_hash: request.request_hash().to_owned(),
            model_hash:
                "sha256:ec014742cc1079fe02be7379b49b969f219e89fd8cf715dcee3c4590f2929fc0"
                    .to_owned(),
            state_hash:
                "sha256:1111111111111111111111111111111111111111111111111111111111111111"
                    .to_owned(),
            execution_hash:
                "sha256:2222222222222222222222222222222222222222222222222222222222222222"
                    .to_owned(),
            checkpoint_hash:
                "sha256:3333333333333333333333333333333333333333333333333333333333333333"
                    .to_owned(),
        },
        NonlinearNdthaResultSummaryV1 {
            terminal_status: NonlinearNdthaTerminalStatusV1::Completed,
            step_count_completed: result.step_count_completed,
            max_plastic_story_count: result.max_plastic_story_count,
            max_drift_ratio_pct: result.max_drift_ratio_pct,
            adaptive_iteration_sum,
            avg_step_iterations: average_step_iterations(
                adaptive_iteration_sum,
                result.step_count_completed,
            )
            .expect("exact iteration average"),
            total_line_search_backtracks: result.total_line_search_backtracks,
            collapse_step: result.collapse_step,
            collapse_time_s: result.collapse_time_s,
            collapse_drift_ratio_pct: result.collapse_drift_ratio_pct,
            collapse_top_displacement_m: result.collapse_top_displacement_m,
            residual_top_displacement_m: result.residual_top_displacement_m,
            residual_drift_ratio_pct: result.residual_drift_ratio_pct,
        },
        result.response,
    )
    .expect("bounded ResultIR")
}

fn encoded(value: &Value) -> Vec<u8> {
    serde_json::to_vec(value).expect("encode test input")
}

#[test]
fn python_c1_golden_is_hash_bound_and_all_rows_pass() {
    let external = parse_external_result_v1(&fixture_bytes()).expect("strict external result");
    let repeated = parse_external_result_v1(external.canonical_bytes()).expect("canonical reparse");
    assert_eq!(repeated.canonical_bytes(), external.canonical_bytes());
    assert_eq!(
        repeated.external_result_hash(),
        external.external_result_hash()
    );

    let comparison =
        build_external_comparison_ir_v1(&result_document(), &external, &oracle_bytes(), None)
            .expect("C1 comparison");
    assert_eq!(
        comparison.comparison().status,
        ExternalComparisonStatusV1::Passed
    );
    assert_eq!(comparison.comparison().rows.len(), 3);
    assert!(comparison
        .comparison()
        .rows
        .iter()
        .all(|row| row.within_tolerance));
    let parsed = parse_external_comparison_ir_v1(comparison.canonical_bytes())
        .expect("self-validating comparison");
    assert_eq!(parsed.canonical_bytes(), comparison.canonical_bytes());
}

#[test]
fn duplicate_and_unknown_input_fields_fail_closed() {
    let text = String::from_utf8(fixture_bytes()).expect("fixture UTF-8");
    let duplicate = text.replacen(
        "\"schema_version\":",
        "\"schema_version\": \"structural-native-external-result.v1\", \"schema_version\":",
        1,
    );
    assert_eq!(
        parse_external_result_v1(duplicate.as_bytes())
            .expect_err("duplicate key")
            .code,
        "external_result_duplicate_json_key"
    );

    let mut unknown: Value = serde_json::from_str(&text).expect("fixture JSON");
    unknown["unexpected"] = json!(true);
    assert_eq!(
        parse_external_result_v1(&encoded(&unknown))
            .expect_err("unknown field")
            .code,
        "external_result_schema_invalid"
    );
}

#[test]
fn quantity_mapping_unit_and_duplicates_are_rejected() {
    for (field, value, expected) in [
        (
            "native_result_path",
            json!("/summary/residual_top_displacement_m"),
            "external_native_result_path_mismatch",
        ),
        (
            "native_location_id",
            json!("terminal_global_response"),
            "external_native_location_mismatch",
        ),
        ("unit", json!("m"), "external_quantity_unit_mismatch"),
    ] {
        let mut input: Value = serde_json::from_slice(&fixture_bytes()).expect("fixture JSON");
        input["observations"][0][field] = value;
        assert_eq!(
            parse_external_result_v1(&encoded(&input))
                .expect_err("mapping mismatch")
                .code,
            expected
        );
    }

    let mut duplicate: Value = serde_json::from_slice(&fixture_bytes()).expect("fixture JSON");
    duplicate["observations"][1]["quantity"] = json!("max_drift_ratio_pct");
    duplicate["observations"][1]["native_location_id"] = json!("global_response_envelope");
    duplicate["observations"][1]["native_result_path"] = json!("/summary/max_drift_ratio_pct");
    assert_eq!(
        parse_external_result_v1(&encoded(&duplicate))
            .expect_err("duplicate quantity")
            .code,
        "external_quantity_duplicate"
    );
}

#[test]
fn source_model_and_case_hashes_are_checked_before_comparison() {
    let result = result_document();
    let external = parse_external_result_v1(&fixture_bytes()).expect("strict external result");
    assert_eq!(
        build_external_comparison_ir_v1(&result, &external, b"wrong", None)
            .expect_err("source mismatch")
            .code,
        "external_source_artifact_hash_mismatch"
    );

    for (field, expected) in [
        ("model_hash", "external_model_hash_mismatch"),
        ("case_id", "external_case_id_mismatch"),
    ] {
        let mut input: Value = serde_json::from_slice(&fixture_bytes()).expect("fixture JSON");
        input["binding"][field] = if field == "model_hash" {
            json!("sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        } else {
            json!("another-case")
        };
        let external = parse_external_result_v1(&encoded(&input)).expect("strict mismatch input");
        assert_eq!(
            build_external_comparison_ir_v1(&result, &external, &oracle_bytes(), None)
                .expect_err("binding mismatch")
                .code,
            expected
        );
    }
}

#[test]
fn live_evidence_requires_verified_executable_bytes() {
    let executable = b"pinned external solver executable";
    let executable_hash = structural_contracts::product_ir::sha256_identity(executable);
    let mut input: Value = serde_json::from_slice(&fixture_bytes()).expect("fixture JSON");
    input["source"]["solver_family"] = json!("opensees");
    input["source"]["evidence_kind"] = json!("live_external_execution");
    input["source"]["executable_hash"] = json!(executable_hash);
    let external = parse_external_result_v1(&encoded(&input)).expect("strict live input");
    assert_eq!(
        build_external_comparison_ir_v1(&result_document(), &external, &oracle_bytes(), None,)
            .expect_err("missing executable")
            .code,
        "external_executable_artifact_missing"
    );
    assert_eq!(
        build_external_comparison_ir_v1(
            &result_document(),
            &external,
            &oracle_bytes(),
            Some(b"wrong executable"),
        )
        .expect_err("wrong executable")
        .code,
        "external_executable_hash_mismatch"
    );
    build_external_comparison_ir_v1(
        &result_document(),
        &external,
        &oracle_bytes(),
        Some(executable),
    )
    .expect("verified live executable");
}

#[test]
fn divergence_is_data_and_derived_rows_are_tamper_evident() {
    let mut input: Value = serde_json::from_slice(&fixture_bytes()).expect("fixture JSON");
    input["observations"][0]["value"] = json!(1.0);
    let external = parse_external_result_v1(&encoded(&input)).expect("strict divergent input");
    let comparison =
        build_external_comparison_ir_v1(&result_document(), &external, &oracle_bytes(), None)
            .expect("comparison artifact");
    assert_eq!(
        comparison.comparison().status,
        ExternalComparisonStatusV1::Diverged
    );

    let mut tampered: Value =
        serde_json::from_slice(comparison.canonical_bytes()).expect("comparison JSON");
    tampered["rows"][0]["within_tolerance"] = json!(true);
    assert_eq!(
        parse_external_comparison_ir_v1(&encoded(&tampered))
            .expect_err("derived-row tamper")
            .code,
        "external_comparison_row_derivation_invalid"
    );
}
