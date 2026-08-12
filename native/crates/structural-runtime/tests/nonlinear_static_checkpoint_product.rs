use std::path::{Path, PathBuf};

use structural_contracts::legacy_runtime::{
    parse_legacy_runtime_case_v3, LegacyRuntimeCaseV3, NonlinearStaticCaseV3,
};
use structural_contracts::static_product::{
    build_nonlinear_static_request_v1, NonlinearStaticAnalysisRequestDocumentV1,
    NonlinearStaticAnalysisRequestV1, NonlinearStaticBackendV1,
};
use structural_runtime::{NonlinearStaticCheckpointV1, NonlinearStaticExecutionStatus, Runtime};

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

fn fixture() -> NonlinearStaticCaseV3 {
    let bytes = std::fs::read(
        repository_root().join("native/tests/fixtures/legacy_runtime_v3/nonlinear_static.json"),
    )
    .expect("tracked fixture");
    match parse_legacy_runtime_case_v3(&bytes).expect("strict fixture") {
        LegacyRuntimeCaseV3::NonlinearStatic(value) => value,
        _ => panic!("fixture decoded as another family"),
    }
}

fn request() -> NonlinearStaticAnalysisRequestDocumentV1 {
    let fixture = fixture();
    build_nonlinear_static_request_v1(NonlinearStaticAnalysisRequestV1 {
        schema_version: "structural-nonlinear-static-request.v1".to_owned(),
        operation: "solve_nonlinear_static_newton".to_owned(),
        case_id: "static-runtime-c4".to_owned(),
        backend: NonlinearStaticBackendV1::Cpu,
        config: fixture.config,
        inputs: fixture.inputs,
    })
    .expect("canonical request")
}

#[test]
fn real_iteration_checkpoint_resume_is_byte_identical_to_direct_completion() {
    let runtime = Runtime::new().expect("runtime");
    let request = request();
    let direct = runtime
        .advance_nonlinear_static_product(&request, None, u32::MAX)
        .expect("direct completion");
    assert_eq!(
        direct.checkpoint.state().status,
        NonlinearStaticExecutionStatus::Converged
    );
    let direct_result = direct.result_ir.as_ref().expect("direct ResultIR");

    let partial = runtime
        .advance_nonlinear_static_product(&request, None, 1)
        .expect("one Newton iteration");
    assert_eq!(
        partial.checkpoint.state().status,
        NonlinearStaticExecutionStatus::Active
    );
    assert_eq!(partial.checkpoint.state().iterations, 1);
    assert!(partial.result_ir.is_none());
    let restored = Runtime::restore_nonlinear_static(&request, partial.checkpoint.as_bytes())
        .expect("verified restore");
    assert_eq!(restored.state(), partial.checkpoint.state());
    let resumed = runtime
        .advance_nonlinear_static_product(&request, Some(partial.checkpoint.as_bytes()), u32::MAX)
        .expect("resumed completion");
    assert_eq!(resumed.checkpoint.as_bytes(), direct.checkpoint.as_bytes());
    assert_eq!(
        resumed
            .result_ir
            .as_ref()
            .expect("resumed ResultIR")
            .canonical_bytes(),
        direct_result.canonical_bytes()
    );
    assert_eq!(direct.checkpoint.receipt().execution_status, "converged");
}

#[test]
fn every_single_byte_mutation_and_request_drift_fail_closed() {
    let runtime = Runtime::new().expect("runtime");
    let request = request();
    let partial = runtime
        .advance_nonlinear_static_product(&request, None, 1)
        .expect("partial checkpoint");
    let original = partial.checkpoint.as_bytes();
    for index in 0..original.len() {
        let mut corrupt = original.to_vec();
        corrupt[index] ^= 1;
        let error = NonlinearStaticCheckpointV1::from_bytes(&corrupt)
            .expect_err("every one-byte mutation must fail");
        assert_eq!(error.code, 1301, "mutation index {index}");
    }

    let mut changed_value = request.request().clone();
    changed_value.inputs.floor_load_n[0] += 1.0;
    let changed = build_nonlinear_static_request_v1(changed_value).expect("changed request");
    let error =
        Runtime::restore_nonlinear_static(&changed, original).expect_err("changed request binding");
    assert_eq!(error.code, 1301);
}

#[test]
fn nonconvergence_is_terminal_and_checkpointable_without_result_ir() {
    let runtime = Runtime::new().expect("runtime");
    let mut value = request().request().clone();
    value.config.max_iter = 1;
    let request = build_nonlinear_static_request_v1(value).expect("bounded request");
    let failed = runtime
        .advance_nonlinear_static_product(&request, None, u32::MAX)
        .expect("numerical terminal transition");
    assert_eq!(
        failed.checkpoint.state().status,
        NonlinearStaticExecutionStatus::Nonconverged
    );
    assert!(failed.result_ir.is_none());
    assert_eq!(
        NonlinearStaticCheckpointV1::from_bytes(failed.checkpoint.as_bytes())
            .expect("failed state remains restorable")
            .state(),
        failed.checkpoint.state()
    );
}
