use serde_json::{json, Value};
use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_contracts::model_linear_comparison::{
    build_model_ir_linear_external_comparison_ir_v1,
    parse_model_ir_linear_external_comparison_ir_v1, parse_model_ir_linear_external_result_v1,
};
use structural_contracts::model_linear_recovery::{
    parse_model_ir_linear_result_recovery_ir_v1, verify_model_ir_linear_result_recovery_v1,
};
use structural_contracts::product_ir::{sha256_identity, ResultIdentityV1};
use structural_contracts::sparse_product::{
    build_sparse_linear_request_v1, build_sparse_linear_result_ir_v1,
    sparse_linear_execution_hash_v1, sparse_linear_model_hash_v1, SparseLinearAnalysisRequestV1,
    SparseLinearBackendV1, SparseLinearConfigV1, SparseLinearResultSummaryV1,
    SPARSE_LINEAR_REQUEST_V1,
};

fn hash() -> String {
    format!("sha256:{}", "1".repeat(64))
}

fn canonical_self_hashed(mut value: Value, field: &str) -> Vec<u8> {
    value
        .as_object_mut()
        .expect("object")
        .remove(field)
        .expect("placeholder");
    let unsigned = canonicalize_model_ir_v2(&value).expect("canonical unsigned JSON");
    value.as_object_mut().expect("object").insert(
        field.to_owned(),
        json!(sha256_identity(unsigned.as_bytes())),
    );
    canonicalize_model_ir_v2(&value)
        .expect("canonical hashed JSON")
        .into_bytes()
}

fn sparse_result_with_reported_residual(
    final_residual_inf: f64,
) -> structural_contracts::sparse_product::SparseLinearResultIrDocumentV1 {
    let request = build_sparse_linear_request_v1(SparseLinearAnalysisRequestV1 {
        schema_version: SPARSE_LINEAR_REQUEST_V1.to_owned(),
        operation: "solve_sparse_spd_pcg".to_owned(),
        case_id: "linear-compare-c5".to_owned(),
        backend: SparseLinearBackendV1::Cpu,
        order: 5,
        row_offsets: vec![0, 2, 5, 8, 11, 13],
        column_indices: vec![0, 1, 0, 1, 2, 1, 2, 3, 2, 3, 4, 3, 4],
        values: vec![
            4.0, -1.0, -1.0, 4.0, -1.0, -1.0, 4.0, -1.0, -1.0, 3.0, -1.0, -1.0, 2.0,
        ],
        right_hand_side: vec![6.0, -12.0, 18.0, -20.0, 14.0],
        initial_guess: Vec::new(),
        config: SparseLinearConfigV1 {
            max_iterations: 100,
            absolute_residual_tolerance: 1.0e-13,
            relative_residual_tolerance: 1.0e-13,
            maximum_increment: 0.0,
        },
    })
    .expect("request");
    let identity = ResultIdentityV1 {
        request_hash: request.request_hash().to_owned(),
        model_hash: sparse_linear_model_hash_v1(&request).expect("model hash"),
        state_hash: hash(),
        execution_hash: sparse_linear_execution_hash_v1(&request).expect("execution hash"),
        checkpoint_hash: format!("sha256:{}", "2".repeat(64)),
    };
    build_sparse_linear_result_ir_v1(
        &request,
        identity,
        SparseLinearResultSummaryV1 {
            order: 5,
            nonzero_count: 13,
            iterations: 5,
            initial_residual_inf: 20.0,
            final_residual_inf,
            final_residual_l2: 0.0,
            last_increment_inf: 0.25,
        },
        vec![1.0, -2.0, 3.0, -4.0, 5.0],
    )
    .expect("result")
}

fn sparse_result() -> structural_contracts::sparse_product::SparseLinearResultIrDocumentV1 {
    sparse_result_with_reported_residual(0.0)
}

fn recovery_bytes_with_first_residual(result_hash: &str, first_residual: f64) -> Vec<u8> {
    let first_internal_force = 6.0 + first_residual;
    let first_residual = first_internal_force - 6.0;
    canonical_self_hashed(
        json!({
            "schema_version": "structural-model-ir-linear-result-recovery-ir.v1",
            "case_id": "linear-compare-c5",
            "model_id": "frame-linear",
            "model_identity": {
                "content_hash": hash(),
                "semantic_hash": hash(),
                "provenance_hash": hash()
            },
            "analysis_request_hash": hash(),
            "assembly_hash": hash(),
            "source_result_hash": result_hash,
            "load_pattern_id": "LC1",
            "load_pattern_index": 0,
            "global_dof_count": 6,
            "dof_order_per_node": ["UX", "UY", "UZ", "RX", "RY", "RZ"],
            "active_dof_indices": [0, 1, 2, 3, 4],
            "global_displacement": [1.0, -2.0, 3.0, -4.0, 5.0, 0.0],
            "active_internal_force": [first_internal_force, -12.0, 18.0, -20.0, 14.0],
            "active_external_load": [6.0, -12.0, 18.0, -20.0, 14.0],
            "active_equilibrium_residual": [first_residual, 0.0, 0.0, 0.0, 0.0],
            "same_state_jvp": [first_internal_force, -12.0, 18.0, -20.0, 14.0],
            "recovery_stable_indices": [0],
            "recovery_element_types": [1],
            "recovery_offsets": [0, 12],
            "recovery_values": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "summary": {
                "maximum_absolute_displacement": 5.0,
                "active_residual_inf": first_residual.abs()
            },
            "units": {
                "global_displacement": "translations_m_rotations_rad",
                "active_force": "forces_n_moments_n_m",
                "frame3d_recovery": "local_end_forces_n_and_moments_n_m",
                "truss3d_recovery": ["axial_strain_1", "axial_stress_pa", "axial_force_n"]
            },
            "coordinate_frame": {
                "global_displacement_and_active_force": "model_global",
                "frame3d_recovery": "element_local",
                "truss3d_recovery": "element_axis"
            },
            "backend": "cpu",
            "precision": "fp64",
            "fallback_count": 0,
            "claim_boundary": "bounded_active_dof_and_element_recovery_not_constrained_reactions_shell_nonlinear_hip_or_engineering_acceptance",
            "recovery_hash": ""
        }),
        "recovery_hash",
    )
}

fn recovery_bytes(result_hash: &str) -> Vec<u8> {
    recovery_bytes_with_first_residual(result_hash, 0.0)
}

fn external_bytes(source_hash: &str, observed: f64) -> Vec<u8> {
    serde_json::to_vec(&json!({
        "schema_version": "structural-model-ir-linear-external-result.v1",
        "comparison_id": "linear-reference-c5",
        "source": {
            "solver_family": "reference_oracle",
            "solver_version": "language-neutral-v1",
            "run_id": "linear-reference-run",
            "evidence_kind": "language_neutral_golden",
            "source_artifact_hash": source_hash,
            "executable_hash": null
        },
        "binding": {
            "analysis_kind": "model_ir_linear_static",
            "case_id": "linear-compare-c5",
            "model_identity": {
                "content_hash": hash(),
                "semantic_hash": hash(),
                "provenance_hash": hash()
            },
            "analysis_request_hash": hash(),
            "load_pattern_id": "LC1",
            "coordinate_frame": "model_global"
        },
        "observations": [{
            "observation_id": "node0-ux",
            "external_location_id": "node/N0/UX",
            "global_dof_index": 0,
            "dof": "UX",
            "native_result_path": "/global_displacement/0",
            "unit": "m",
            "value": observed,
            "tolerance": {"absolute": 1.0e-12, "relative": 1.0e-12}
        }]
    }))
    .expect("external JSON")
}

#[test]
fn recovered_result_and_external_dof_comparison_are_strict_and_self_hashed() {
    let result = sparse_result();
    let recovery_bytes = recovery_bytes(result.result_hash());
    let recovery =
        parse_model_ir_linear_result_recovery_ir_v1(&recovery_bytes).expect("strict recovery");
    assert_eq!(recovery.canonical_bytes(), recovery_bytes);

    let source = b"language-neutral linear reference\n";
    let external =
        parse_model_ir_linear_external_result_v1(&external_bytes(&sha256_identity(source), 1.0))
            .expect("external result");
    let comparison = build_model_ir_linear_external_comparison_ir_v1(
        &result, &recovery, &external, source, None,
    )
    .expect("comparison");
    assert_eq!(
        comparison.comparison().status,
        structural_contracts::external_comparison::ExternalComparisonStatusV1::Passed
    );
    let reparsed =
        parse_model_ir_linear_external_comparison_ir_v1(comparison.canonical_json().as_bytes())
            .expect("strict comparison");
    assert_eq!(reparsed.comparison_hash(), comparison.comparison_hash());

    let diverged =
        parse_model_ir_linear_external_result_v1(&external_bytes(&sha256_identity(source), 2.0))
            .expect("diverged external result");
    assert_eq!(
        build_model_ir_linear_external_comparison_ir_v1(
            &result, &recovery, &diverged, source, None,
        )
        .expect("valid divergence")
        .comparison()
        .status,
        structural_contracts::external_comparison::ExternalComparisonStatusV1::Diverged
    );
}

#[test]
fn recovery_result_binding_uses_bounded_fp64_residual_parity() {
    let rounded_result = sparse_result_with_reported_residual(5.0e-13);
    let exact_recovery_bytes = recovery_bytes(rounded_result.result_hash());
    let exact_recovery =
        parse_model_ir_linear_result_recovery_ir_v1(&exact_recovery_bytes).expect("recovery");
    verify_model_ir_linear_result_recovery_v1(&rounded_result, &exact_recovery)
        .expect("roundoff-sized residual parity");

    let result = sparse_result();
    let divergent_recovery_bytes =
        recovery_bytes_with_first_residual(result.result_hash(), 2.0e-12);
    let divergent_recovery = parse_model_ir_linear_result_recovery_ir_v1(&divergent_recovery_bytes)
        .expect("standalone exact recovery");
    let error = verify_model_ir_linear_result_recovery_v1(&result, &divergent_recovery)
        .expect_err("material residual divergence must fail closed");
    assert_eq!(error.code, "model_ir_linear_recovery_residual_mismatch");
}

#[test]
fn duplicate_mapping_and_recovery_tamper_fail_closed() {
    let result = sparse_result();
    let recovery_bytes = recovery_bytes(result.result_hash());
    let recovery =
        parse_model_ir_linear_result_recovery_ir_v1(&recovery_bytes).expect("strict recovery");
    let source = b"language-neutral linear reference\n";
    let mut external: Value =
        serde_json::from_slice(&external_bytes(&sha256_identity(source), 1.0))
            .expect("external JSON");
    let duplicate = external["observations"][0].clone();
    external["observations"]
        .as_array_mut()
        .expect("observations")
        .push(duplicate);
    assert!(parse_model_ir_linear_external_result_v1(
        &serde_json::to_vec(&external).expect("duplicate JSON")
    )
    .is_err());

    let mut tampered: Value = serde_json::from_slice(&recovery_bytes).expect("recovery JSON");
    tampered["global_displacement"][0] = json!(2.0);
    assert!(parse_model_ir_linear_result_recovery_ir_v1(
        &serde_json::to_vec(&tampered).expect("tampered JSON")
    )
    .is_err());

    let forged_recovery_bytes = canonical_self_hashed(tampered, "recovery_hash");
    let forged_recovery = parse_model_ir_linear_result_recovery_ir_v1(&forged_recovery_bytes)
        .expect("standalone self-consistent but result-inconsistent recovery");

    let external =
        parse_model_ir_linear_external_result_v1(&external_bytes(&sha256_identity(source), 1.0))
            .expect("external result");
    let wrong_source = b"different source\n";
    assert!(build_model_ir_linear_external_comparison_ir_v1(
        &result,
        &recovery,
        &external,
        wrong_source,
        None,
    )
    .is_err());
    assert!(build_model_ir_linear_external_comparison_ir_v1(
        &result,
        &forged_recovery,
        &external,
        source,
        None,
    )
    .is_err());

    let mut oversized_dof: Value =
        serde_json::from_slice(&external_bytes(&sha256_identity(source), 1.0))
            .expect("external JSON");
    oversized_dof["observations"][0]["global_dof_index"] = json!(1_000_000);
    oversized_dof["observations"][0]["dof"] = json!("RY");
    oversized_dof["observations"][0]["native_result_path"] = json!("/global_displacement/1000000");
    assert!(parse_model_ir_linear_external_result_v1(
        &serde_json::to_vec(&oversized_dof).expect("oversized DOF JSON")
    )
    .is_err());
}
