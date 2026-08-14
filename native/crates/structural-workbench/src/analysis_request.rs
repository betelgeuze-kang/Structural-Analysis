use std::path::Path;

use serde_json::json;
use structural_cli::{validate_model_bytes, validate_model_ir_linear_analysis_compatibility};
use structural_contracts::model_linear_product::{
    build_model_ir_linear_analysis_request_v1, ModelIrLinearAnalysisRequestV1,
    ModelIrLinearBackendV1, MODEL_IR_LINEAR_ANALYSIS_REQUEST_V1,
};
use structural_contracts::product_ir::{sha256_identity, ModelIrIdentityV1};
use structural_contracts::sparse_product::SparseLinearConfigV1;

use super::model_edit::{
    MODEL_LINEAR_LOAD_COMBINATION_MAX_DIRECT_TERMS_V1,
    MODEL_LINEAR_LOAD_COMBINATION_MIN_DIRECT_TERMS_V1,
};
use super::{
    artifact_entry, canonical_self_hashed, input_error, publish_new_directory,
    read_bounded_regular_file, WorkbenchError, MAX_MODEL_BYTES,
};

const REQUEST_RECEIPT_SCHEMA_V1: &str = "structural-native-model-linear-request-create-receipt.v1";
const COMBINATION_REQUEST_RECEIPT_SCHEMA_V1: &str =
    "structural-native-model-linear-combination-request-create-receipt.v1";
const DIRECT_COMBINATION_REQUEST_RECEIPT_SCHEMA_V2: &str =
    "structural-native-model-linear-direct-combination-request-create-receipt.v2";
const CLAIM_BOUNDARY: &str = "bounded_cpp_assembly_preflighted_modelir_linear_cpu_request_creation_not_arbitrary_solver_backend_model_editing_execution_convergence_engineering_acceptance_or_c6";
const COMBINATION_CLAIM_BOUNDARY: &str = "bounded_exact_two_pattern_linear_combination_cpp_assembly_preflighted_cpu_request_using_frozen_v1_load_pattern_id_wire_alias_not_nested_combination_arbitrary_solver_backend_hip_engineering_acceptance_or_c6";
const DIRECT_COMBINATION_CLAIM_BOUNDARY: &str = "bounded_two_to_64_unique_direct_pattern_linear_combination_cpp_assembly_preflighted_cpu_request_using_frozen_v1_load_pattern_id_wire_alias_not_nested_combination_arbitrary_solver_backend_hip_engineering_acceptance_or_c6";

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum LoadSelectorKindV1 {
    Pattern,
    Combination,
}

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
    publish_model_linear_analysis_request_for_selector(
        source_path,
        case_id,
        load_pattern_id,
        LoadSelectorKindV1::Pattern,
        config,
        output_directory,
    )
}

/// Construct and atomically publish one bounded two-to-64-pattern direct linear-combination CPU request.
///
/// The frozen request v1 field remains named `load_pattern_id`; the combination receipt records
/// that this field is intentionally carrying a load-combination selector.
///
/// # Errors
///
/// Rejects unsafe paths, invalid or blocked `ModelIR`, an ambiguous or unsupported combination,
/// invalid bounded PCG controls, invalid identifiers, or create-new publication failures.
pub fn publish_model_linear_combination_analysis_request(
    source_path: &Path,
    case_id: &str,
    load_combination_id: &str,
    config: SparseLinearConfigV1,
    output_directory: &Path,
) -> Result<ModelLinearAnalysisRequestCreateOutcomeV1, WorkbenchError> {
    publish_model_linear_analysis_request_for_selector(
        source_path,
        case_id,
        load_combination_id,
        LoadSelectorKindV1::Combination,
        config,
        output_directory,
    )
}

fn publish_model_linear_analysis_request_for_selector(
    source_path: &Path,
    case_id: &str,
    selector_id: &str,
    selector_kind: LoadSelectorKindV1,
    config: SparseLinearConfigV1,
    output_directory: &Path,
) -> Result<ModelLinearAnalysisRequestCreateOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome = create_model_linear_analysis_request_for_selector(
        &source,
        case_id,
        selector_id,
        selector_kind,
        config,
    )?;
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
    create_model_linear_analysis_request_for_selector(
        source_bytes,
        case_id,
        load_pattern_id,
        LoadSelectorKindV1::Pattern,
        config,
    )
}

/// Construct one canonical CPU request for a bounded two-to-64-pattern direct linear combination.
///
/// # Errors
///
/// Returns stable Workbench errors for the same source and request failures as
/// [`create_model_linear_analysis_request`], plus ambiguous, nested, malformed, duplicate-pattern,
/// zero-factor, or non-linear combination selectors.
pub fn create_model_linear_combination_analysis_request(
    source_bytes: &[u8],
    case_id: &str,
    load_combination_id: &str,
    config: SparseLinearConfigV1,
) -> Result<ModelLinearAnalysisRequestCreateOutcomeV1, WorkbenchError> {
    create_model_linear_analysis_request_for_selector(
        source_bytes,
        case_id,
        load_combination_id,
        LoadSelectorKindV1::Combination,
        config,
    )
}

fn create_model_linear_analysis_request_for_selector(
    source_bytes: &[u8],
    case_id: &str,
    selector_id: &str,
    selector_kind: LoadSelectorKindV1,
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
    let combination_terms = require_load_selector(
        source_validation.snapshot.value(),
        selector_id,
        selector_kind,
    )?;

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
        load_pattern_id: selector_id.to_owned(),
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
    let receipt_json = build_model_linear_request_receipt(
        json!({
            "model_id": source_validation.report.model_id,
            "model_identity": request.request().model_identity,
            "source_input_sha256": sha256_identity(source_bytes),
            "case_id": request.request().case_id,
            "backend": "cpu",
            "config": request.request().config,
            "analysis_request_hash": request.request_hash(),
            "cpp_semantic_snapshot_verified": true,
            "cpp_linear_assembly_preflight_verified": true,
            "assembly_hash": compatibility.assembly_hash,
            "generated_sparse_request_hash": compatibility.generated_request_hash,
            "execution_started": false,
            "artifacts": [request_artifact],
        }),
        selector_kind,
        &request.request().load_pattern_id,
        combination_terms.as_ref(),
    )?;
    Ok(ModelLinearAnalysisRequestCreateOutcomeV1 {
        analysis_request_json,
        receipt_json,
    })
}

fn build_model_linear_request_receipt(
    mut receipt: serde_json::Value,
    selector_kind: LoadSelectorKindV1,
    selector_id: &str,
    combination_terms: Option<&serde_json::Value>,
) -> Result<String, WorkbenchError> {
    if selector_kind == LoadSelectorKindV1::Pattern {
        receipt["schema_version"] = json!(REQUEST_RECEIPT_SCHEMA_V1);
        receipt["operation"] = json!("create_model_ir_linear_analysis_request");
        receipt["load_pattern_id"] = json!(selector_id);
        receipt["claim_boundary"] = json!(CLAIM_BOUNDARY);
        return canonical_self_hashed(receipt);
    }

    let terms = combination_terms.ok_or_else(|| {
        WorkbenchError::new(
            "workbench_model_linear_combination_request_terms_invalid",
            "validated load-combination terms became unavailable",
        )
    })?;
    let term_count = terms.as_array().map_or(0, Vec::len);
    if term_count == 2 {
        receipt["schema_version"] = json!(COMBINATION_REQUEST_RECEIPT_SCHEMA_V1);
        receipt["operation"] = json!("create_model_ir_linear_combination_analysis_request");
        receipt["claim_boundary"] = json!(COMBINATION_CLAIM_BOUNDARY);
    } else {
        receipt["schema_version"] = json!(DIRECT_COMBINATION_REQUEST_RECEIPT_SCHEMA_V2);
        receipt["operation"] = json!("create_model_ir_linear_direct_combination_analysis_request");
        receipt["request_profile"] = json!("unique_direct_linear_static_patterns_2_to_64");
        receipt["combination_term_count"] = json!(term_count);
        receipt["claim_boundary"] = json!(DIRECT_COMBINATION_CLAIM_BOUNDARY);
    }
    receipt["load_selector_kind"] = json!("load_combination");
    receipt["load_combination_id"] = json!(selector_id);
    receipt["combination_terms"] = terms.clone();
    receipt["frozen_request_selector_field"] = json!("load_pattern_id");
    canonical_self_hashed(receipt)
}

fn require_load_selector(
    model: &serde_json::Value,
    selector_id: &str,
    selector_kind: LoadSelectorKindV1,
) -> Result<Option<serde_json::Value>, WorkbenchError> {
    match selector_kind {
        LoadSelectorKindV1::Pattern => {
            require_linear_load_pattern(model, selector_id)?;
            Ok(None)
        }
        LoadSelectorKindV1::Combination => {
            require_bounded_linear_load_combination(model, selector_id).map(Some)
        }
    }
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
    if model
        .get("load_combinations")
        .and_then(serde_json::Value::as_array)
        .is_some_and(|combinations| {
            combinations.iter().any(|combination| {
                combination.get("id").and_then(serde_json::Value::as_str) == Some(load_pattern_id)
            })
        })
    {
        return Err(WorkbenchError::new(
            "workbench_model_linear_request_selector_ambiguous",
            format!("identity {load_pattern_id} names both a load pattern and combination"),
        ));
    }
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

fn require_bounded_linear_load_combination(
    model: &serde_json::Value,
    load_combination_id: &str,
) -> Result<serde_json::Value, WorkbenchError> {
    let patterns = model
        .get("load_patterns")
        .and_then(serde_json::Value::as_array)
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_linear_combination_request_snapshot_invalid",
                "verified ModelIR snapshot has no load-pattern array",
            )
        })?;
    if patterns.iter().any(|pattern| {
        pattern.get("id").and_then(serde_json::Value::as_str) == Some(load_combination_id)
    }) {
        return Err(WorkbenchError::new(
            "workbench_model_linear_request_selector_ambiguous",
            format!("identity {load_combination_id} names both a load pattern and combination"),
        ));
    }
    let combinations = model
        .get("load_combinations")
        .and_then(serde_json::Value::as_array)
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_linear_combination_request_snapshot_invalid",
                "verified ModelIR snapshot has no load-combination array",
            )
        })?;
    let combination = combinations
        .iter()
        .find(|combination| {
            combination.get("id").and_then(serde_json::Value::as_str) == Some(load_combination_id)
        })
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_linear_combination_request_missing",
                format!("ModelIR has no load combination with identity {load_combination_id}"),
            )
        })?;
    if combination
        .get("combination_type")
        .and_then(serde_json::Value::as_str)
        != Some("linear")
    {
        return Err(WorkbenchError::new(
            "workbench_model_linear_combination_request_type_unsupported",
            format!("load combination {load_combination_id} is not linear"),
        ));
    }
    let terms = combination
        .get("terms")
        .and_then(serde_json::Value::as_array)
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_linear_combination_request_terms_invalid",
                "selected load combination has no term array",
            )
        })?;
    if !(MODEL_LINEAR_LOAD_COMBINATION_MIN_DIRECT_TERMS_V1
        ..=MODEL_LINEAR_LOAD_COMBINATION_MAX_DIRECT_TERMS_V1)
        .contains(&terms.len())
    {
        return Err(WorkbenchError::new(
            "workbench_model_linear_combination_request_term_count_unsupported",
            "selected direct load combination must contain between two and 64 terms",
        ));
    }
    let referenced_ids = terms
        .iter()
        .map(|term| require_bounded_linear_load_combination_term(term, patterns))
        .collect::<Result<Vec<_>, _>>()?;
    if referenced_ids
        .iter()
        .enumerate()
        .any(|(index, id)| referenced_ids[..index].iter().any(|prior| prior == id))
    {
        return Err(WorkbenchError::new(
            "workbench_model_linear_combination_request_duplicate_pattern",
            "selected direct load combination must reference unique load patterns",
        ));
    }
    Ok(serde_json::Value::Array(terms.clone()))
}

fn require_bounded_linear_load_combination_term<'a>(
    term: &'a serde_json::Value,
    patterns: &[serde_json::Value],
) -> Result<&'a str, WorkbenchError> {
    if term.get("ref_kind").and_then(serde_json::Value::as_str) != Some("load_pattern") {
        return Err(WorkbenchError::new(
            "workbench_model_linear_combination_request_nested_unsupported",
            "selected load combination may reference load patterns only",
        ));
    }
    let referenced_id = term
        .get("ref_id")
        .and_then(serde_json::Value::as_str)
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_linear_combination_request_terms_invalid",
                "selected load-combination term has no reference identity",
            )
        })?;
    let factor = term
        .get("factor")
        .and_then(serde_json::Value::as_f64)
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_linear_combination_request_terms_invalid",
                "selected load-combination factor is not numeric",
            )
        })?;
    if !factor.is_finite() || factor == 0.0 {
        return Err(WorkbenchError::new(
            "workbench_model_linear_combination_request_factor_unsupported",
            "selected load-combination factors must be finite and nonzero",
        ));
    }
    let referenced_pattern = patterns
        .iter()
        .find(|pattern| {
            pattern.get("id").and_then(serde_json::Value::as_str) == Some(referenced_id)
        })
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_linear_combination_request_pattern_missing",
                format!("ModelIR has no referenced load pattern {referenced_id}"),
            )
        })?;
    if referenced_pattern
        .get("analysis_type")
        .and_then(serde_json::Value::as_str)
        != Some("linear_static")
    {
        return Err(WorkbenchError::new(
            "workbench_model_linear_combination_request_pattern_unsupported",
            format!("referenced load pattern {referenced_id} is not linear_static"),
        ));
    }
    Ok(referenced_id)
}

#[cfg(test)]
mod tests {
    use super::{
        create_model_linear_analysis_request, create_model_linear_combination_analysis_request,
    };
    use serde_json::{json, Value};
    use structural_contracts::model_ir::canonicalize_model_ir_v2;
    use structural_contracts::sparse_product::SparseLinearConfigV1;

    fn config() -> SparseLinearConfigV1 {
        SparseLinearConfigV1 {
            max_iterations: 100,
            absolute_residual_tolerance: 1.0e-11,
            relative_residual_tolerance: 1.0e-13,
            maximum_increment: 0.0,
        }
    }

    fn model_with_combinations(combinations: Value) -> Vec<u8> {
        let mut value: Value = serde_json::from_slice(include_bytes!(
            "../../../../tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
        ))
        .expect("ModelIR fixture JSON");
        value["load_combinations"] = combinations;
        canonicalize_model_ir_v2(&value)
            .expect("canonical combination fixture")
            .into_bytes()
    }

    fn combination(id: &str, terms: &Value) -> Value {
        json!({
            "id": id,
            "index": 0,
            "combination_type": "linear",
            "terms": terms,
            "source_id": null,
            "extensions": {}
        })
    }

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

    #[test]
    fn exact_two_pattern_combination_is_preflighted_with_an_explicit_alias_receipt() {
        let terms = json!([
            {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": 1.2},
            {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": -0.5}
        ]);
        let source = model_with_combinations(json!([combination("COMBO_SERVICE", &terms)]));
        let outcome = create_model_linear_combination_analysis_request(
            &source,
            "combo-case",
            "COMBO_SERVICE",
            config(),
        )
        .expect("bounded combination request");
        let request: Value =
            serde_json::from_str(&outcome.analysis_request_json).expect("request JSON");
        assert_eq!(request["load_pattern_id"], "COMBO_SERVICE");
        let receipt: Value = serde_json::from_str(&outcome.receipt_json).expect("receipt JSON");
        assert_eq!(
            receipt["schema_version"],
            "structural-native-model-linear-combination-request-create-receipt.v1"
        );
        assert_eq!(receipt["load_selector_kind"], "load_combination");
        assert_eq!(receipt["load_combination_id"], "COMBO_SERVICE");
        assert_eq!(receipt["combination_terms"], terms);
        assert_eq!(receipt["frozen_request_selector_field"], "load_pattern_id");
        assert_eq!(receipt["cpp_linear_assembly_preflight_verified"], true);
    }

    #[test]
    fn three_pattern_direct_combination_uses_the_versioned_bounded_receipt() {
        let terms = json!([
            {"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 0.25},
            {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": 1.2},
            {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": -0.5}
        ]);
        let source = model_with_combinations(json!([combination("COMBO_DIRECT", &terms)]));
        let outcome = create_model_linear_combination_analysis_request(
            &source,
            "direct-combination-case",
            "COMBO_DIRECT",
            config(),
        )
        .expect("bounded direct combination request");
        let receipt: Value = serde_json::from_str(&outcome.receipt_json).expect("receipt JSON");
        assert_eq!(
            receipt["schema_version"],
            "structural-native-model-linear-direct-combination-request-create-receipt.v2"
        );
        assert_eq!(
            receipt["request_profile"],
            "unique_direct_linear_static_patterns_2_to_64"
        );
        assert_eq!(receipt["combination_term_count"], 3);
        assert_eq!(receipt["combination_terms"], terms);
        assert_eq!(receipt["cpp_linear_assembly_preflight_verified"], true);
    }

    #[test]
    fn malformed_or_ambiguous_combination_selectors_fail_closed_before_publication() {
        let one_term = model_with_combinations(json!([combination(
            "COMBO_ONE",
            &json!([{"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": 1.0}])
        )]));
        assert_eq!(
            create_model_linear_combination_analysis_request(
                &one_term,
                "case",
                "COMBO_ONE",
                config()
            )
            .expect_err("one-term combination fails")
            .code,
            "workbench_model_linear_combination_request_term_count_unsupported"
        );

        let duplicate = model_with_combinations(json!([combination(
            "COMBO_DUPLICATE",
            &json!([
                {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": 1.0},
                {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": 0.5}
            ])
        )]));
        assert_eq!(
            create_model_linear_combination_analysis_request(
                &duplicate,
                "case",
                "COMBO_DUPLICATE",
                config()
            )
            .expect_err("duplicate-pattern combination fails")
            .code,
            "workbench_model_linear_combination_request_duplicate_pattern"
        );

        let zero = model_with_combinations(json!([combination(
            "COMBO_ZERO",
            &json!([
                {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": 1.0},
                {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": 0.0}
            ])
        )]));
        assert_eq!(
            create_model_linear_combination_analysis_request(&zero, "case", "COMBO_ZERO", config())
                .expect_err("zero-factor combination fails")
                .code,
            "workbench_model_linear_combination_request_factor_unsupported"
        );

        let nested = model_with_combinations(json!([
            combination(
                "COMBO_BASE",
                &json!([
                    {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": 1.0},
                    {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": 1.0}
                ])
            ),
            {
                "id": "COMBO_NESTED",
                "index": 1,
                "combination_type": "linear",
                "terms": [
                    {"ref_id": "COMBO_BASE", "ref_kind": "load_combination", "factor": 1.0},
                    {"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 1.0}
                ],
                "source_id": null,
                "extensions": {}
            }
        ]));
        assert_eq!(
            create_model_linear_combination_analysis_request(
                &nested,
                "case",
                "COMBO_NESTED",
                config()
            )
            .expect_err("nested combination fails")
            .code,
            "workbench_model_linear_combination_request_nested_unsupported"
        );

        let ambiguous = model_with_combinations(json!([combination(
            "LC_WEAK",
            &json!([
                {"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 1.0},
                {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": 1.0}
            ])
        )]));
        assert_eq!(
            create_model_linear_combination_analysis_request(
                &ambiguous,
                "case",
                "LC_WEAK",
                config()
            )
            .expect_err("ambiguous selector fails")
            .code,
            "workbench_model_linear_request_selector_ambiguous"
        );
    }
}
