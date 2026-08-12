use std::path::{Path, PathBuf};

use structural_contracts::product_ir::{
    average_step_iterations, build_nonlinear_ndtha_report_ir_v1,
    build_nonlinear_ndtha_result_ir_v1, parse_native_analysis_request_v1,
    parse_nonlinear_ndtha_report_ir_v1, parse_nonlinear_ndtha_result_ir_v1,
    NonlinearNdthaResultSummaryV1, NonlinearNdthaTerminalStatusV1, ResultIdentityV1,
};
use structural_contracts::solver_cpu::parse_nonlinear_ndtha_cpu_case_v1;

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

fn request_bytes() -> Vec<u8> {
    std::fs::read(
        repository_root().join("native/tests/fixtures/product_e2e/nonlinear_ndtha_request.json"),
    )
    .expect("tracked product request")
}

fn result_document() -> structural_contracts::product_ir::NonlinearNdthaResultIrDocumentV1 {
    let request = parse_native_analysis_request_v1(&request_bytes()).expect("strict request");
    let golden = parse_nonlinear_ndtha_cpu_case_v1(
        &std::fs::read(repository_root().join(
            "native/tests/fixtures/solver_cpu/nonlinear_ndtha_one_story_elastic_python_c1.json",
        ))
        .expect("tracked CPU golden"),
    )
    .expect("strict CPU golden");
    let result = golden.result;
    let iteration_sum = result.step_iterations_sum();
    build_nonlinear_ndtha_result_ir_v1(
        &request,
        ResultIdentityV1 {
            request_hash: request.request_hash().to_owned(),
            model_hash: format!("sha256:{}", "1".repeat(64)),
            state_hash: format!("sha256:{}", "2".repeat(64)),
            execution_hash: format!("sha256:{}", "3".repeat(64)),
            checkpoint_hash: format!("sha256:{}", "4".repeat(64)),
        },
        NonlinearNdthaResultSummaryV1 {
            terminal_status: NonlinearNdthaTerminalStatusV1::Completed,
            step_count_completed: result.step_count_completed,
            max_plastic_story_count: result.max_plastic_story_count,
            max_drift_ratio_pct: result.max_drift_ratio_pct,
            adaptive_iteration_sum: iteration_sum,
            avg_step_iterations: average_step_iterations(
                iteration_sum,
                result.step_count_completed,
            )
            .expect("bounded iteration average"),
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
    .expect("canonical ResultIR")
}

trait IterationSum {
    fn step_iterations_sum(&self) -> u64;
}

impl IterationSum for structural_contracts::solver_cpu::NonlinearNdthaCpuResultV1 {
    fn step_iterations_sum(&self) -> u64 {
        self.response
            .step_iterations
            .iter()
            .map(|value| u64::from(*value))
            .sum()
    }
}

#[test]
fn request_is_strict_canonical_and_hash_bound() {
    let bytes = request_bytes();
    let request = parse_native_analysis_request_v1(&bytes).expect("strict request");
    let repeated = parse_native_analysis_request_v1(request.canonical_bytes())
        .expect("canonical request reparses");
    assert_eq!(request.request_hash(), repeated.request_hash());
    assert_eq!(request.canonical_bytes(), repeated.canonical_bytes());
    assert_eq!(request.request().case_id, "ndtha-one-story-elastic");

    let duplicate = String::from_utf8(bytes).expect("UTF-8 fixture").replacen(
        "\"operation\": \"nonlinear_ndtha\",",
        "\"operation\": \"nonlinear_ndtha\", \"operation\": \"nonlinear_ndtha\",",
        1,
    );
    assert_eq!(
        parse_native_analysis_request_v1(duplicate.as_bytes())
            .expect_err("duplicate key")
            .code,
        "request_duplicate_json_key"
    );
    let unknown = String::from_utf8(request_bytes())
        .expect("UTF-8 fixture")
        .replacen(
            "\"backend\": \"cpu\",",
            "\"backend\": \"cpu\", \"extra\": 1,",
            1,
        );
    assert_eq!(
        parse_native_analysis_request_v1(unknown.as_bytes())
            .expect_err("unknown field")
            .code,
        "native_analysis_request_schema_invalid"
    );
}

#[test]
fn result_and_report_self_hashes_are_canonical_and_tamper_evident() {
    let result = result_document();
    let parsed =
        parse_nonlinear_ndtha_result_ir_v1(result.canonical_bytes()).expect("ResultIR round trip");
    assert_eq!(parsed.result_hash(), result.result_hash());
    assert_eq!(parsed.canonical_bytes(), result.canonical_bytes());

    let document_source = b"# deterministic report\n";
    let report =
        build_nonlinear_ndtha_report_ir_v1(&result, document_source).expect("canonical ReportIR");
    let parsed_report =
        parse_nonlinear_ndtha_report_ir_v1(report.canonical_bytes()).expect("ReportIR round trip");
    assert_eq!(parsed_report.report_hash(), report.report_hash());
    assert_eq!(parsed_report.canonical_bytes(), report.canonical_bytes());

    let tampered =
        result
            .canonical_json()
            .replacen("\"fallback_count\":0", "\"fallback_count\":1", 1);
    assert_eq!(
        parse_nonlinear_ndtha_result_ir_v1(tampered.as_bytes())
            .expect_err("backend receipt tamper")
            .code,
        "result_ir_backend_receipt_invalid"
    );
}
