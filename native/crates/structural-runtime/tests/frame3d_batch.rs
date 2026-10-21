use std::path::Path;

use serde_json::{json, Value};
use structural_contracts::model_ir::{parse_model_ir_v2, ModelIrV2Document};
use structural_contracts::result_ir::LinearFrame3dResultIrV1;
use structural_runtime::{
    analyze_linear_frame3d_batch, Frame3dBatchError, LinearFrame3dBatchLoadSource,
    LinearFrame3dBatchRequest, Runtime, RuntimeError, MAX_FRAME3D_BATCH_REQUESTS,
    MAX_FRAME3D_BATCH_WORKERS,
};

fn fixture_value() -> Value {
    let path = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    serde_json::from_slice(&std::fs::read(path).expect("tracked synthetic Frame3D fixture"))
        .expect("fixture JSON")
}

fn frame_alpha_value() -> Value {
    let mut value = fixture_value();
    value["elements"][0]["formulation"] = json!("linear_timoshenko_frame3d");
    value["load_combinations"] = json!([{
        "id": "COMB_BATCH",
        "index": 0,
        "combination_type": "linear",
        "terms": [
            {"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 1.25},
            {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": -0.4}
        ],
        "source_id": null,
        "extensions": {}
    }]);
    value
}

fn document(value: &Value) -> ModelIrV2Document {
    parse_model_ir_v2(&serde_json::to_vec(value).expect("fixture JSON bytes"))
        .expect("schema-valid synthetic ModelIR")
}

fn request(
    source: &ModelIrV2Document,
    load_source: LinearFrame3dBatchLoadSource,
    result_id: &str,
) -> LinearFrame3dBatchRequest {
    LinearFrame3dBatchRequest {
        document: source.clone(),
        load_source,
        result_id: result_id.to_owned(),
    }
}

fn serial_outcomes(requests: &[LinearFrame3dBatchRequest]) -> Vec<Result<String, RuntimeError>> {
    let runtime = Runtime::new().expect("native Frame3D runtime");
    requests
        .iter()
        .map(|request| {
            let result = match &request.load_source {
                LinearFrame3dBatchLoadSource::Pattern(id) => runtime
                    .analyze_linear_frame3d_result_ir(&request.document, id, &request.result_id),
                LinearFrame3dBatchLoadSource::Combination(id) => runtime
                    .analyze_linear_frame3d_combination_result_ir(
                        &request.document,
                        id,
                        &request.result_id,
                    ),
            };
            result.map(|value| value.canonical_json().expect("canonical serial ResultIR"))
        })
        .collect()
}

fn canonical_outcomes(
    outcomes: &[Result<LinearFrame3dResultIrV1, RuntimeError>],
) -> Vec<Result<String, RuntimeError>> {
    outcomes
        .iter()
        .map(|outcome| match outcome {
            Ok(value) => Ok(value.canonical_json().expect("canonical batch ResultIR")),
            Err(error) => Err(error.clone()),
        })
        .collect()
}

fn ordered_requests() -> Vec<LinearFrame3dBatchRequest> {
    let base = frame_alpha_value();
    let patterns = ["LC_TORSION", "LC_AXIAL", "LC_STRONG", "LC_WEAK"];
    (0..17)
        .map(|index| {
            let mut value = base.clone();
            value["model_id"] = json!(format!("batch-synthetic-model-{index:02}"));
            let load_source = if index % 5 == 4 {
                LinearFrame3dBatchLoadSource::Combination("COMB_BATCH".to_owned())
            } else {
                LinearFrame3dBatchLoadSource::Pattern(patterns[index % 5].to_owned())
            };
            request(
                &document(&value),
                load_source,
                &format!("batch-result-{index:02}"),
            )
        })
        .collect()
}

#[test]
fn worker_counts_preserve_exact_serial_results_and_input_order() {
    let requests = ordered_requests();
    let expected = serial_outcomes(&requests);
    assert!(expected.iter().all(Result::is_ok));

    for workers in [1, 2, 4, 8, 12] {
        let result = analyze_linear_frame3d_batch(&requests, workers).expect("valid batch");
        assert_eq!(result.requested_workers, workers);
        assert_eq!(result.workers_used, workers);
        assert_eq!(result.outcomes.len(), requests.len());
        assert_eq!(
            canonical_outcomes(&result.outcomes),
            expected,
            "{workers} workers"
        );

        for (index, outcome) in result.outcomes.iter().enumerate() {
            let output = outcome.as_ref().expect("successful synthetic case");
            assert_eq!(output.result_id, requests[index].result_id);
            assert_eq!(
                output.bindings.model_id,
                requests[index].document.model_id()
            );
        }
    }
}

#[test]
fn more_workers_than_requests_preserves_all_outcomes() {
    let source = document(&frame_alpha_value());
    let requests = [
        request(
            &source,
            LinearFrame3dBatchLoadSource::Combination("COMB_BATCH".to_owned()),
            "small-batch-combination",
        ),
        request(
            &source,
            LinearFrame3dBatchLoadSource::Pattern("LC_TORSION".to_owned()),
            "small-batch-pattern",
        ),
    ];
    let expected = serial_outcomes(&requests);
    let result = analyze_linear_frame3d_batch(&requests, MAX_FRAME3D_BATCH_WORKERS)
        .expect("workers are bounded by request count");

    assert_eq!(result.requested_workers, MAX_FRAME3D_BATCH_WORKERS);
    assert_eq!(result.workers_used, requests.len());
    assert_eq!(canonical_outcomes(&result.outcomes), expected);
}

#[test]
fn mixed_case_failures_keep_serial_errors_and_do_not_discard_successes() {
    let base = frame_alpha_value();
    let source = document(&base);
    let mut unsupported_support = base;
    unsupported_support["constraints"][0]["prescribed_values_si"]["UX"] = json!(0.001);
    let requests = [
        request(
            &source,
            LinearFrame3dBatchLoadSource::Pattern("LC_AXIAL".to_owned()),
            "mixed-first",
        ),
        request(
            &source,
            LinearFrame3dBatchLoadSource::Pattern("LC_MISSING".to_owned()),
            "mixed-missing-pattern",
        ),
        request(
            &source,
            LinearFrame3dBatchLoadSource::Combination("COMB_BATCH".to_owned()),
            "mixed-combination",
        ),
        request(
            &source,
            LinearFrame3dBatchLoadSource::Pattern("LC_STRONG".to_owned()),
            "invalid result id",
        ),
        request(
            &document(&unsupported_support),
            LinearFrame3dBatchLoadSource::Pattern("LC_AXIAL".to_owned()),
            "mixed-nonzero-prescribed-support",
        ),
        request(
            &source,
            LinearFrame3dBatchLoadSource::Pattern("LC_TORSION".to_owned()),
            "mixed-after-support-error",
        ),
        request(
            &source,
            LinearFrame3dBatchLoadSource::Combination("COMB_MISSING".to_owned()),
            "mixed-missing-combination",
        ),
        request(
            &document(&fixture_value()),
            LinearFrame3dBatchLoadSource::Pattern("LC_AXIAL".to_owned()),
            "mixed-unsupported-formulation",
        ),
        request(
            &source,
            LinearFrame3dBatchLoadSource::Pattern("LC_WEAK".to_owned()),
            "mixed-last",
        ),
    ];
    let expected = serial_outcomes(&requests);
    for index in [0, 2, 5, 8] {
        assert!(expected[index].is_ok(), "valid request at {index}");
    }
    for index in [1, 3, 4, 6, 7] {
        assert!(expected[index].is_err(), "invalid request at {index}");
    }
    for index in [1, 3, 6] {
        assert_eq!(
            expected[index].as_ref().expect_err("input error").code,
            1000
        );
    }
    assert_eq!(
        expected[7]
            .as_ref()
            .expect_err("unsupported formulation")
            .code,
        1200
    );

    for workers in [1, 4, MAX_FRAME3D_BATCH_WORKERS] {
        let result = analyze_linear_frame3d_batch(&requests, workers)
            .expect("case errors remain individual outcomes");
        assert_eq!(result.requested_workers, workers);
        assert_eq!(result.workers_used, workers.min(requests.len()));
        assert_eq!(result.outcomes.len(), requests.len());
        assert_eq!(
            canonical_outcomes(&result.outcomes),
            expected,
            "{workers} workers"
        );
    }
}

#[test]
fn invalid_worker_counts_are_rejected_at_the_batch_boundary() {
    assert_eq!(MAX_FRAME3D_BATCH_WORKERS, 12);
    let requests = [request(
        &document(&frame_alpha_value()),
        LinearFrame3dBatchLoadSource::Pattern("LC_AXIAL".to_owned()),
        "worker-boundary",
    )];

    for workers in [0, MAX_FRAME3D_BATCH_WORKERS + 1] {
        assert!(matches!(
            analyze_linear_frame3d_batch(&requests, workers),
            Err(Frame3dBatchError::InvalidWorkerCount { requested, maximum })
                if requested == workers && maximum == MAX_FRAME3D_BATCH_WORKERS
        ));
    }
}

#[test]
fn empty_request_batch_is_rejected() {
    assert!(matches!(
        analyze_linear_frame3d_batch(&[], 1),
        Err(Frame3dBatchError::InvalidRequestCount { requested: 0, maximum })
            if maximum == MAX_FRAME3D_BATCH_REQUESTS
    ));
}

#[test]
fn oversized_request_batch_is_rejected_at_the_batch_boundary() {
    assert_eq!(MAX_FRAME3D_BATCH_REQUESTS, 1024);
    let source = document(&frame_alpha_value());
    let requests: Vec<_> = (0..=MAX_FRAME3D_BATCH_REQUESTS)
        .map(|_| {
            request(
                &source,
                LinearFrame3dBatchLoadSource::Pattern("LC_AXIAL".to_owned()),
                "request-count-boundary",
            )
        })
        .collect();

    assert!(matches!(
        analyze_linear_frame3d_batch(&requests, 1),
        Err(Frame3dBatchError::InvalidRequestCount { requested, maximum })
            if requested == requests.len() && maximum == MAX_FRAME3D_BATCH_REQUESTS
    ));
}
