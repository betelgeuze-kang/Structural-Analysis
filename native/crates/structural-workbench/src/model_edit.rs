use std::path::Path;

use serde_json::{json, Value};
use structural_cli::validate_model_bytes;
use structural_contracts::model_ir::{canonicalize_model_ir_v2, parse_model_ir_v2};
use structural_contracts::product_ir::sha256_identity;

use super::{
    artifact_entry, canonical_self_hashed, input_error, publish_new_directory,
    read_bounded_regular_file, WorkbenchError, MAX_MODEL_BYTES,
};

const EDIT_SCHEMA_V1: &str = "structural-native-model-edit-receipt.v1";
const EDIT_EXTENSION_KEY: &str = "structural-native:model-edit-node.v1";
const UPSTREAM_PROVENANCE_KEY: &str = "structural-native:upstream-provenance";
const CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_modelir_node_coordinate_edit_not_visual_dragging_property_constraint_load_or_solver_editing_engineering_acceptance_or_c6";

/// Complete deterministic artifact pair produced by one bounded node-coordinate edit.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelNodeEditOutcomeV1 {
    pub model_ir_json: String,
    pub receipt_json: String,
}

/// Edit one node in a bounded regular `ModelIR` file and atomically publish a new artifact set.
///
/// # Errors
///
/// Rejects unsafe input/output paths, non-finite coordinates, invalid source or edited semantics,
/// missing node identities, no-op edits, or any create-new publication failure.
pub fn publish_model_node_coordinate_edit(
    source_path: &Path,
    node_id: &str,
    coordinates_m: [f64; 3],
    output_directory: &Path,
) -> Result<ModelNodeEditOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome = edit_model_node_coordinates(&source, node_id, coordinates_m)?;
    publish_new_directory(
        output_directory,
        &[
            ("model-ir.json", outcome.model_ir_json.as_bytes()),
            ("edit-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Produce one provenance-bound, C++-revalidated node-coordinate edit in memory.
///
/// # Errors
///
/// Rejects non-finite coordinates, an invalid source model, a missing node, a no-op edit, schema
/// drift introduced by provenance projection, or edited geometry rejected by C++ semantics.
pub fn edit_model_node_coordinates(
    source_bytes: &[u8],
    node_id: &str,
    coordinates_m: [f64; 3],
) -> Result<ModelNodeEditOutcomeV1, WorkbenchError> {
    validate_edit_request(source_bytes.len(), node_id, coordinates_m)?;

    let source_validation = validate_model_bytes(source_bytes)
        .map_err(|error| input_error("workbench_model_edit_source_validation_failed", &error))?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    let source_document = &source_validation.snapshot;
    let source_content_hash = source_document.content_hash().to_owned();
    let source_semantic_hash = source_document.semantic_hash().to_owned();
    let source_provenance_hash = source_document.provenance_hash().to_owned();
    let source_input_sha256 = sha256_identity(source_bytes);
    let mut edited = source_document.value().clone();
    let previous_coordinates_m = replace_node_coordinates(&mut edited, node_id, coordinates_m)?;
    if previous_coordinates_m
        .iter()
        .zip(coordinates_m)
        .all(|(previous, edited)| {
            normalized_number_bits(*previous) == normalized_number_bits(edited)
        })
    {
        return Err(WorkbenchError::new(
            "workbench_model_edit_no_change",
            "edited coordinates are canonically identical to the source node",
        ));
    }
    bind_edit_provenance(
        &mut edited,
        node_id,
        previous_coordinates_m,
        coordinates_m,
        &source_content_hash,
        &source_semantic_hash,
        &source_provenance_hash,
    )?;
    mark_roundtrip_node_approximated(&mut edited, node_id)?;

    let edited_wire = canonicalize_model_ir_v2(&edited)
        .map_err(|error| input_error("workbench_model_edit_serialization_failed", &error))?;
    parse_model_ir_v2(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_contract_invalid", &error))?;
    let edited_validation = validate_model_bytes(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_validation_failed", &error))?;
    if !edited_validation.report.contract_valid || !edited_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_semantics_invalid",
            "native C++ validation rejected the edited ModelIR semantics",
        ));
    }
    let model_ir_json = edited_validation.snapshot.canonical_json().to_owned();
    let model_artifact = artifact_entry(
        "edited_model_ir",
        "model-ir.json",
        "application/json",
        model_ir_json.as_bytes(),
    )?;
    let receipt_json = canonical_self_hashed(json!({
        "schema_version": EDIT_SCHEMA_V1,
        "operation": "node_coordinates",
        "model_id": edited_validation.report.model_id,
        "node_id": node_id,
        "previous_coordinates_m": previous_coordinates_m,
        "edited_coordinates_m": coordinates_m,
        "source_input_sha256": source_input_sha256,
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "edited_content_hash": edited_validation.report.content_hash,
        "edited_semantic_hash": edited_validation.report.semantic_hash,
        "edited_provenance_hash": edited_validation.report.provenance_hash,
        "cpp_semantic_snapshot_verified": true,
        "analysis_ready": edited_validation.report.analysis_ready,
        "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
        "artifacts": [model_artifact],
        "claim_boundary": CLAIM_BOUNDARY,
    }))?;
    Ok(ModelNodeEditOutcomeV1 {
        model_ir_json,
        receipt_json,
    })
}

fn validate_edit_request(
    source_length: usize,
    node_id: &str,
    coordinates_m: [f64; 3],
) -> Result<(), WorkbenchError> {
    if source_length > usize::try_from(MAX_MODEL_BYTES).unwrap_or(usize::MAX) {
        return Err(WorkbenchError::new(
            "workbench_model_edit_input_too_large",
            "ModelIR exceeds the bounded editor input limit",
        ));
    }
    if coordinates_m
        .iter()
        .any(|coordinate| !coordinate.is_finite())
    {
        return Err(WorkbenchError::new(
            "workbench_model_edit_coordinate_invalid",
            "edited node coordinates must be finite SI values",
        ));
    }
    if node_id.is_empty() || node_id.len() > 128 {
        return Err(WorkbenchError::new(
            "workbench_model_edit_node_id_invalid",
            "edited node identity must contain 1 through 128 bytes",
        ));
    }
    Ok(())
}

fn replace_node_coordinates(
    model: &mut Value,
    node_id: &str,
    coordinates_m: [f64; 3],
) -> Result<[f64; 3], WorkbenchError> {
    let nodes = model
        .get_mut("nodes")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("nodes"))?;
    let node = nodes
        .iter_mut()
        .find(|node| node.get("id").and_then(Value::as_str) == Some(node_id))
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_edit_node_missing",
                format!("ModelIR has no node with identity {node_id}"),
            )
        })?;
    let previous = node
        .get("coordinates_m")
        .and_then(Value::as_array)
        .filter(|values| values.len() == 3)
        .ok_or_else(|| snapshot_error("node coordinates_m"))?;
    let previous_coordinates_m = [
        finite_number(&previous[0])?,
        finite_number(&previous[1])?,
        finite_number(&previous[2])?,
    ];
    node.as_object_mut()
        .ok_or_else(|| snapshot_error("node"))?
        .insert("coordinates_m".to_owned(), json!(coordinates_m));
    Ok(previous_coordinates_m)
}

#[allow(clippy::too_many_arguments)]
fn bind_edit_provenance(
    model: &mut Value,
    node_id: &str,
    previous_coordinates_m: [f64; 3],
    edited_coordinates_m: [f64; 3],
    source_content_hash: &str,
    source_semantic_hash: &str,
    source_provenance_hash: &str,
) -> Result<(), WorkbenchError> {
    let model_id = model
        .get("model_id")
        .and_then(Value::as_str)
        .ok_or_else(|| snapshot_error("model_id"))?
        .to_owned();
    let object = model
        .as_object_mut()
        .ok_or_else(|| snapshot_error("root object"))?;
    let upstream_provenance = object
        .get("provenance")
        .cloned()
        .ok_or_else(|| snapshot_error("provenance"))?;
    object.insert(
        "provenance".to_owned(),
        json!({
            "source_format": "neutral_json",
            "source_ref": format!("modelir-edit:{model_id}"),
            "source_sha256": source_content_hash,
            "normalizer_id": "structural-native-model-editor",
            "normalizer_version": "1",
            "source_units": {
                "length": "m",
                "force": "N",
                "mass": "kg",
                "time": "s",
                "rotation": "rad"
            },
            "unit_scales_to_si": {
                "length_to_m": 1.0,
                "force_to_n": 1.0,
                "mass_to_kg": 1.0,
                "time_to_s": 1.0,
                "rotation_to_rad": 1.0
            },
            "extensions": {
                UPSTREAM_PROVENANCE_KEY: upstream_provenance
            }
        }),
    );
    let extensions = object
        .get_mut("extensions")
        .and_then(Value::as_object_mut)
        .ok_or_else(|| snapshot_error("root extensions"))?;
    extensions.insert(
        EDIT_EXTENSION_KEY.to_owned(),
        json!({
            "operation": "node_coordinates",
            "node_id": node_id,
            "previous_coordinates_m": previous_coordinates_m,
            "edited_coordinates_m": edited_coordinates_m,
            "source_content_hash": source_content_hash,
            "source_semantic_hash": source_semantic_hash,
            "source_provenance_hash": source_provenance_hash,
            "claim_boundary": CLAIM_BOUNDARY
        }),
    );
    Ok(())
}

fn mark_roundtrip_node_approximated(
    model: &mut Value,
    node_id: &str,
) -> Result<(), WorkbenchError> {
    let rows = model
        .get_mut("roundtrip_map")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("roundtrip_map"))?;
    for row in rows {
        if row.get("entity_kind").and_then(Value::as_str) == Some("node")
            && row.get("model_ir_entity_id").and_then(Value::as_str) == Some(node_id)
            && matches!(
                row.get("mapping_status").and_then(Value::as_str),
                Some("exact" | "canonicalized")
            )
        {
            row.as_object_mut()
                .ok_or_else(|| snapshot_error("roundtrip_map node row"))?
                .insert(
                    "mapping_status".to_owned(),
                    Value::String("approximated".to_owned()),
                );
        }
    }
    Ok(())
}

fn normalized_number_bits(value: f64) -> u64 {
    let bits = value.to_bits();
    if bits.trailing_zeros() >= 63 {
        0
    } else {
        bits
    }
}

fn finite_number(value: &Value) -> Result<f64, WorkbenchError> {
    value
        .as_f64()
        .filter(|number| number.is_finite())
        .ok_or_else(|| snapshot_error("finite coordinate"))
}

fn snapshot_error(field: &str) -> WorkbenchError {
    WorkbenchError::new(
        "workbench_model_edit_snapshot_invalid",
        format!("verified ModelIR snapshot has an invalid {field} field"),
    )
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::{
        mark_roundtrip_node_approximated, normalized_number_bits, validate_edit_request,
        MAX_MODEL_BYTES,
    };

    #[test]
    fn signed_zero_is_the_same_canonical_coordinate() {
        assert_eq!(normalized_number_bits(0.0), normalized_number_bits(-0.0));
        assert_ne!(normalized_number_bits(1.0), normalized_number_bits(-1.0));
    }

    #[test]
    fn edit_request_bounds_have_stable_error_taxonomy() {
        let too_large = usize::try_from(MAX_MODEL_BYTES).expect("model size fits usize") + 1;
        assert_eq!(
            validate_edit_request(too_large, "N1", [0.0; 3])
                .expect_err("oversized edit request")
                .code,
            "workbench_model_edit_input_too_large"
        );
        assert_eq!(
            validate_edit_request(0, "", [0.0; 3])
                .expect_err("empty edit node identity")
                .code,
            "workbench_model_edit_node_id_invalid"
        );
        assert_eq!(
            validate_edit_request(0, "N1", [f64::NAN, 0.0, 0.0])
                .expect_err("non-finite edit coordinate")
                .code,
            "workbench_model_edit_coordinate_invalid"
        );
    }

    #[test]
    fn roundtrip_mapping_only_degrades_direct_source_claims() {
        let mut model = json!({
            "roundtrip_map": [
                {"entity_kind": "node", "model_ir_entity_id": "N2", "mapping_status": "exact"},
                {"entity_kind": "node", "model_ir_entity_id": "N2", "mapping_status": "canonicalized"},
                {"entity_kind": "node", "model_ir_entity_id": "N2", "mapping_status": "approximated"},
                {"entity_kind": "node", "model_ir_entity_id": "N2", "mapping_status": "unsupported"},
                {"entity_kind": "node", "model_ir_entity_id": "N1", "mapping_status": "exact"}
            ]
        });
        mark_roundtrip_node_approximated(&mut model, "N2").expect("mapping update");
        let statuses = model["roundtrip_map"]
            .as_array()
            .expect("mapping rows")
            .iter()
            .map(|row| row["mapping_status"].as_str().expect("mapping status"))
            .collect::<Vec<_>>();
        assert_eq!(
            statuses,
            [
                "approximated",
                "approximated",
                "approximated",
                "unsupported",
                "exact"
            ]
        );
    }
}
