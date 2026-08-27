use serde_json::{json, Value};
use structural_contracts::comparison_ir::{
    create_linear_frame3d_comparison_ir_v1, parse_external_linear_frame3d_reference_v1,
    parse_linear_frame3d_comparison_ir_v1, validate_linear_frame3d_comparison_ir_v1,
    validate_linear_frame3d_comparison_sources,
};
use structural_contracts::result_ir::{
    create_linear_frame3d_result_ir_v1, Frame3dResultBindingsV1, Frame3dResultGatesV1,
    Frame3dResultMemberV1, Frame3dResultNodeV1, LinearFrame3dResultIrInput,
    LinearFrame3dResultIrV1,
};

fn hash(character: char) -> String {
    format!("sha256:{}", character.to_string().repeat(64))
}

fn result() -> LinearFrame3dResultIrV1 {
    create_linear_frame3d_result_ir_v1(LinearFrame3dResultIrInput {
        result_id: "frame-alpha.LC1".to_owned(),
        bindings: Frame3dResultBindingsV1 {
            model_id: "frame-alpha".to_owned(),
            model_content_hash: hash('a'),
            model_semantic_hash: hash('b'),
            model_provenance_hash: hash('c'),
            load_pattern_id: Some("LC1".to_owned()),
            load_combination_id: None,
            native_abi_version: 0x0001_0005,
        },
        gates: Frame3dResultGatesV1 {
            native_residual_gate_passed: true,
            free_residual_scaled_linf: 2.0e-15,
            free_residual_scaled_linf_tolerance: 1.0e-9,
            global_force_balance_scaled_linf: 3.0e-16,
            global_force_balance_scaled_linf_tolerance: 1.0e-9,
            global_moment_balance_scaled_linf: 4.0e-16,
            global_moment_balance_scaled_linf_tolerance: 1.0e-9,
            global_resultant_gate_passed: true,
            independent_recovery_replay_passed: true,
            member_force_replay_scaled_linf: 5.0e-16,
            member_force_replay_scaled_linf_tolerance: 1.0e-9,
            zero_prescribed_displacement_gate_passed: true,
            fallback_count: 0,
            regularization_count: 0,
        },
        nodes: vec![
            Frame3dResultNodeV1 {
                node_id: "N1".to_owned(),
                displacement_m_rad: [0.0; 6],
                reaction_n_nm: [-100_000.0, 0.0, 0.0, 0.0, 0.0, 10_000.0],
            },
            Frame3dResultNodeV1 {
                node_id: "N2".to_owned(),
                displacement_m_rad: [5.0e-5, -2.0e-4, 0.0, 0.0, 0.0, 1.0e-3],
                reaction_n_nm: [0.0; 6],
            },
        ],
        members: vec![Frame3dResultMemberV1 {
            member_id: "E1".to_owned(),
            end_i_force_n_nm: [-100_000.0, 0.0, 0.0, 0.0, 0.0, 10_000.0],
            end_j_force_n_nm: [100_000.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        }],
    })
    .expect("bounded ResultIR")
}

fn reference_value(result: &LinearFrame3dResultIrV1) -> Value {
    json!({
        "schema_version": "structural-external-linear-frame3d-reference.v1",
        "reference_id": "reference.synthetic.LC1",
        "source": {
            "tool": "synthetic_fixture",
            "version": "contract-test-v1",
            "origin": "synthetic_contract_fixture",
            "export_sha256": hash('d')
        },
        "bindings": {
            "model_content_hash": result.bindings.model_content_hash,
            "load_pattern_id": "LC1",
            "load_combination_id": null
        },
        "axes": {
            "node_displacement": "global_ux_uy_uz_rx_ry_rz",
            "node_reaction": "global_fx_fy_fz_mx_my_mz",
            "member_end_force": "member_local_fx_fy_fz_mx_my_mz_i_then_j",
            "sign_convention": "native_result_ir_compatible"
        },
        "units": {"translation": "mm", "rotation": "rad", "force": "kN", "moment": "kN*m"},
        "nodes": result.nodes.iter().map(|node| json!({
            "node_id": node.node_id,
            "displacement": [
                node.displacement_m_rad[0] * 1000.0,
                node.displacement_m_rad[1] * 1000.0,
                node.displacement_m_rad[2] * 1000.0,
                node.displacement_m_rad[3], node.displacement_m_rad[4], node.displacement_m_rad[5]
            ],
            "reaction": [
                node.reaction_n_nm[0] / 1000.0,
                node.reaction_n_nm[1] / 1000.0,
                node.reaction_n_nm[2] / 1000.0,
                node.reaction_n_nm[3] / 1000.0,
                node.reaction_n_nm[4] / 1000.0,
                node.reaction_n_nm[5] / 1000.0
            ]
        })).collect::<Vec<_>>(),
        "members": result.members.iter().map(|member| json!({
            "member_id": member.member_id,
            "end_i_force": member.end_i_force_n_nm.map(|value| value / 1000.0),
            "end_j_force": member.end_j_force_n_nm.map(|value| value / 1000.0)
        })).collect::<Vec<_>>(),
        "claim_boundary": "operator_declared_mapping_and_units_not_independent_validation_or_release_authority"
    })
}

#[test]
fn comparison_normalizes_units_and_is_deterministic_and_hash_bound() {
    let result = result();
    let bytes = serde_json::to_vec(&reference_value(&result)).expect("reference bytes");
    let first = create_linear_frame3d_comparison_ir_v1(&result, &bytes, "comparison.LC1")
        .expect("comparison");
    let second = create_linear_frame3d_comparison_ir_v1(&result, &bytes, "comparison.LC1")
        .expect("deterministic comparison");

    assert_eq!(first, second);
    assert!(first.summary.passed);
    assert_eq!(first.summary.row_count, 36);
    assert_eq!(first.summary.failing_row_count, 0);
    assert!(first.summary.families[0].max_scaled_difference.abs() <= f64::EPSILON);
    assert_eq!(first.authority.external_validation, "not_established");
    let canonical = first.canonical_json().expect("canonical ComparisonIR");
    let parsed = parse_linear_frame3d_comparison_ir_v1(canonical.as_bytes())
        .expect("strict comparison round-trip");
    assert_eq!(parsed, first);
    validate_linear_frame3d_comparison_sources(&parsed, &result, &bytes)
        .expect("exact source replay");

    let mut operator_reference = reference_value(&result);
    operator_reference["source"]["tool"] = json!("sap2000");
    operator_reference["source"]["version"] = json!("v-test");
    operator_reference["source"]["origin"] = json!("operator_attached_external");
    let operator_comparison = create_linear_frame3d_comparison_ir_v1(
        &result,
        &serde_json::to_vec(&operator_reference).expect("operator reference bytes"),
        "comparison.operator",
    )
    .expect("operator-attached contract input");
    assert_eq!(operator_comparison.source_reference.tool, "sap2000");
    assert_eq!(
        operator_comparison.source_reference.origin,
        "operator_attached_external"
    );
}

#[test]
fn tolerance_failure_is_recorded_without_authority_promotion() {
    let result = result();
    let mut reference = reference_value(&result);
    reference["nodes"][1]["displacement"][1] = json!(-0.204);
    let comparison = create_linear_frame3d_comparison_ir_v1(
        &result,
        &serde_json::to_vec(&reference).expect("reference bytes"),
        "comparison.failed",
    )
    .expect("evaluated failing comparison");

    assert!(!comparison.summary.passed);
    assert_eq!(comparison.summary.failing_row_count, 1);
    assert!(!comparison.summary.families[0].passed);
    assert_eq!(comparison.summary.families[0].worst_entity_id, "N2");
    assert_eq!(comparison.summary.families[0].worst_component, "UY");
    assert_eq!(
        comparison.authority.comparison,
        "bounded_cross_code_evaluation"
    );
    assert_eq!(comparison.authority.release_readiness, "not_authoritative");
}

#[test]
fn stale_bindings_incomplete_coverage_and_invalid_origin_fail_closed() {
    let result = result();
    let mut stale = reference_value(&result);
    stale["bindings"]["model_content_hash"] = json!(hash('e'));
    let error = create_linear_frame3d_comparison_ir_v1(
        &result,
        &serde_json::to_vec(&stale).expect("stale bytes"),
        "comparison.stale",
    )
    .expect_err("stale model binding must fail");
    assert_eq!(error.code, "frame3d_external_reference_binding_mismatch");

    let mut incomplete = reference_value(&result);
    incomplete["nodes"].as_array_mut().expect("nodes").pop();
    let error = create_linear_frame3d_comparison_ir_v1(
        &result,
        &serde_json::to_vec(&incomplete).expect("incomplete bytes"),
        "comparison.incomplete",
    )
    .expect_err("partial reference coverage must fail");
    assert!(matches!(
        error.code.as_str(),
        "frame3d_external_reference_schema_invalid"
            | "frame3d_external_reference_coverage_mismatch"
    ));

    let mut origin = reference_value(&result);
    origin["source"]["tool"] = json!("sap2000");
    let error = parse_external_linear_frame3d_reference_v1(
        &serde_json::to_vec(&origin).expect("origin bytes"),
    )
    .expect_err("synthetic origin cannot claim an external tool");
    assert_eq!(error.code, "frame3d_external_reference_origin_invalid");
}

#[test]
fn duplicate_reference_keys_and_tampered_comparison_hash_fail_closed() {
    let result = result();
    let reference = reference_value(&result);
    let duplicate = serde_json::to_string(&reference)
        .expect("reference JSON")
        .replacen('{', "{\"schema_version\":\"duplicate\",", 1);
    let error = parse_external_linear_frame3d_reference_v1(duplicate.as_bytes())
        .expect_err("duplicate reference key must fail");
    assert_eq!(error.code, "frame3d_external_reference_json_invalid");

    let bytes = serde_json::to_vec(&reference).expect("reference bytes");
    let comparison = create_linear_frame3d_comparison_ir_v1(&result, &bytes, "comparison.tamper")
        .expect("comparison");
    let mut wrong_identity = comparison.clone();
    wrong_identity.rows[0].component = "FX".to_owned();
    let error = validate_linear_frame3d_comparison_ir_v1(&wrong_identity)
        .expect_err("cross-family component transplantation must fail");
    assert_eq!(error.code, "frame3d_comparison_row_identity_invalid");

    let mut promoted = comparison.clone();
    promoted.authority.external_validation = "established".to_owned();
    let error = validate_linear_frame3d_comparison_ir_v1(&promoted)
        .expect_err("comparison must not promote validation authority");
    assert!(matches!(
        error.code.as_str(),
        "frame3d_comparison_ir_schema_invalid" | "frame3d_comparison_policy_promotion_forbidden"
    ));

    let mut value: Value = serde_json::from_str(&comparison.canonical_json().expect("canonical"))
        .expect("ComparisonIR JSON");
    value["rows"][0]["reference_value"] = json!(1.0);
    let error = parse_linear_frame3d_comparison_ir_v1(
        &serde_json::to_vec(&value).expect("tampered comparison bytes"),
    )
    .expect_err("tampered row must fail closed");
    assert!(matches!(
        error.code.as_str(),
        "frame3d_comparison_row_inconsistent" | "frame3d_comparison_ir_hash_mismatch"
    ));
}
