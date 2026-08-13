use std::path::Path;

use serde_json::json;
use structural_cli::{validate_model_bytes, validate_model_ir_linear_analysis_compatibility};
use structural_contracts::model_linear_product::{
    build_model_ir_linear_analysis_request_v1, ModelIrLinearAnalysisRequestV1,
    ModelIrLinearBackendV1, MODEL_IR_LINEAR_ANALYSIS_REQUEST_V1,
};
use structural_contracts::product_ir::{sha256_identity, ModelIrIdentityV1};
use structural_contracts::sparse_product::SparseLinearConfigV1;

use super::{
    artifact_entry, canonical_self_hashed, input_error, publish_new_directory,
    read_bounded_regular_file, WorkbenchError, MAX_MODEL_BYTES,
};

const REQUEST_RECEIPT_SCHEMA_V1: &str = "structural-native-model-linear-request-create-receipt.v1";
const CLAIM_BOUNDARY: &str = "bounded_cpp_assembly_preflighted_modelir_linear_cpu_request_creation_not_arbitrary_solver_backend_model_editing_execution_convergence_engineering_acceptance_or_c6";

/// Complete deterministic artifact pair for one CPU `ModelIR` linear analysis request.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelLinearAnalysisRequestCreateOutcomeV1 {
    pub analysis_request_json: String,
    pub receipt_json: String,
}

/// Construct and atomically publish one model-bound CPU linear analysis request.
///
/// # Errors
///
/// Rejects unsafe paths, invalid or blocked `ModelIR`, an incompatible load-pattern/element graph,
/// invalid bounded PCG controls, invalid identifiers, or create-new publication failures.
pub fn publish_model_linear_analysis_request(
    source_path: &Path,
    case_id: &str,
    load_pattern_id: &str,
    config: SparseLinearConfigV1,
    output_directory: &Path,
) -> Result<ModelLinearAnalysisRequestCreateOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome = create_model_linear_analysis_request(&source, case_id, load_pattern_id, config)?;
    publish_new_directory(
        output_directory,
        &[
            (
                "analysis-request.json",
                outcome.analysis_request_json.as_bytes(),
            ),
            ("request-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Construct one canonical CPU linear request after C++ snapshot and assembly preflight.
///
/// # Errors
///
/// Returns a stable Workbench error for invalid source semantics/readiness, missing or non-linear
/// load patterns, invalid request fields, or a C++ assembly/generated-PCG-request incompatibility.
pub fn create_model_linear_analysis_request(
    source_bytes: &[u8],
    case_id: &str,
    load_pattern_id: &str,
    config: SparseLinearConfigV1,
) -> Result<ModelLinearAnalysisRequestCreateOutcomeV1, WorkbenchError> {
    let source_validation = validate_model_bytes(source_bytes).map_err(|error| {
        input_error(
            "workbench_model_linear_request_source_validation_failed",
            &error,
        )
    })?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_linear_request_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    if !source_validation.report.analysis_ready {
        return Err(WorkbenchError::new(
            "workbench_model_linear_request_source_not_ready",
            "source ModelIR retains explicit analysis blockers",
        ));
    }
    require_linear_load_pattern(source_validation.snapshot.value(), load_pattern_id)?;

    let request = build_model_ir_linear_analysis_request_v1(ModelIrLinearAnalysisRequestV1 {
        schema_version: MODEL_IR_LINEAR_ANALYSIS_REQUEST_V1.to_owned(),
        operation: "solve_model_ir_linear_static".to_owned(),
        case_id: case_id.to_owned(),
        backend: ModelIrLinearBackendV1::Cpu,
        model_identity: ModelIrIdentityV1 {
            content_hash: source_validation.report.content_hash.clone(),
            semantic_hash: source_validation.report.semantic_hash.clone(),
            provenance_hash: source_validation.report.provenance_hash.clone(),
        },
        load_pattern_id: load_pattern_id.to_owned(),
        config,
    })
    .map_err(|error| input_error("workbench_model_linear_request_contract_invalid", &error))?;
    let compatibility =
        validate_model_ir_linear_analysis_compatibility(source_bytes, request.canonical_bytes())
            .map_err(|error| {
                input_error("workbench_model_linear_request_preflight_failed", &error)
            })?;

    let analysis_request_json = request.canonical_json().to_owned();
    let request_artifact = artifact_entry(
        "model_linear_analysis_request",
        "analysis-request.json",
        "application/json",
        analysis_request_json.as_bytes(),
    )?;
    let receipt_json = canonical_self_hashed(json!({
        "schema_version": REQUEST_RECEIPT_SCHEMA_V1,
        "operation": "create_model_ir_linear_analysis_request",
        "model_id": source_validation.report.model_id,
        "model_identity": request.request().model_identity,
        "source_input_sha256": sha256_identity(source_bytes),
        "case_id": request.request().case_id,
        "backend": "cpu",
        "load_pattern_id": request.request().load_pattern_id,
        "config": request.request().config,
        "analysis_request_hash": request.request_hash(),
        "cpp_semantic_snapshot_verified": true,
        "cpp_linear_assembly_preflight_verified": true,
        "assembly_hash": compatibility.assembly_hash,
        "generated_sparse_request_hash": compatibility.generated_request_hash,
        "execution_started": false,
        "artifacts": [request_artifact],
        "claim_boundary": CLAIM_BOUNDARY,
    }))?;
    Ok(ModelLinearAnalysisRequestCreateOutcomeV1 {
        analysis_request_json,
        receipt_json,
    })
}

fn require_linear_load_pattern(
    model: &serde_json::Value,
    load_pattern_id: &str,
) -> Result<(), WorkbenchError> {
    let patterns = model
        .get("load_patterns")
        .and_then(serde_json::Value::as_array)
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_linear_request_snapshot_invalid",
                "verified ModelIR snapshot has no load-pattern array",
            )
        })?;
    let pattern = patterns
        .iter()
        .find(|pattern| {
            pattern.get("id").and_then(serde_json::Value::as_str) == Some(load_pattern_id)
        })
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_linear_request_load_pattern_missing",
                format!("ModelIR has no load pattern with identity {load_pattern_id}"),
            )
        })?;
    if pattern
        .get("analysis_type")
        .and_then(serde_json::Value::as_str)
        != Some("linear_static")
    {
        return Err(WorkbenchError::new(
            "workbench_model_linear_request_load_pattern_unsupported",
            format!("load pattern {load_pattern_id} is not linear_static"),
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::create_model_linear_analysis_request;
    use structural_contracts::sparse_product::SparseLinearConfigV1;

    #[test]
    fn invalid_typed_controls_fail_with_contract_taxonomy_before_preflight() {
        let source = include_bytes!(
            "../../../../tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
        );
        let error = create_model_linear_analysis_request(
            source,
            "case",
            "LC_WEAK",
            SparseLinearConfigV1 {
                max_iterations: 0,
                absolute_residual_tolerance: 0.0,
                relative_residual_tolerance: 0.0,
                maximum_increment: 0.0,
            },
        )
        .expect_err("invalid controls fail closed");
        assert_eq!(
            error.code,
            "workbench_model_linear_request_contract_invalid"
        );
    }
}
