use serde_json::Value;
use structural_contracts::result_ir::{
    create_linear_frame3d_result_ir_v1, parse_linear_frame3d_result_ir_v1, Frame3dResultBindingsV1,
    Frame3dResultGatesV1, Frame3dResultMemberV1, Frame3dResultNodeV1, LinearFrame3dResultIrInput,
};

fn hash(character: char) -> String {
    format!("sha256:{}", character.to_string().repeat(64))
}

fn input() -> LinearFrame3dResultIrInput {
    LinearFrame3dResultIrInput {
        result_id: "frame-alpha.LC1".to_owned(),
        bindings: Frame3dResultBindingsV1 {
            model_id: "frame-alpha".to_owned(),
            model_content_hash: hash('a'),
            model_semantic_hash: hash('b'),
            model_provenance_hash: hash('c'),
            load_pattern_id: "LC1".to_owned(),
            native_abi_version: 0x0001_0002,
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
                reaction_n_nm: [-100_000.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            },
            Frame3dResultNodeV1 {
                node_id: "N2".to_owned(),
                displacement_m_rad: [5.0e-5, 0.0, 0.0, 0.0, 0.0, 0.0],
                reaction_n_nm: [0.0; 6],
            },
        ],
        members: vec![Frame3dResultMemberV1 {
            member_id: "E1".to_owned(),
            end_i_force_n_nm: [-100_000.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            end_j_force_n_nm: [100_000.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        }],
    }
}

#[test]
fn result_ir_is_canonical_hash_bound_and_strictly_round_trippable() {
    let result = create_linear_frame3d_result_ir_v1(input()).expect("bounded ResultIR");
    let canonical = result.canonical_json().expect("canonical JSON");
    let reparsed =
        parse_linear_frame3d_result_ir_v1(canonical.as_bytes()).expect("strict round-trip");

    assert_eq!(reparsed, result);
    assert_eq!(
        reparsed.canonical_json().expect("canonical replay"),
        canonical
    );
    assert!(result.result_hash.starts_with("sha256:"));
    assert_eq!(result.authority.reaction, "bounded_candidate");
    assert!(result.claim_boundary.independent_recovery_replay);
    assert!(!result.claim_boundary.release_readiness);
}

#[test]
fn stale_hash_and_duplicate_json_keys_fail_closed() {
    let result = create_linear_frame3d_result_ir_v1(input()).expect("bounded ResultIR");
    let mut value: Value = serde_json::from_str(&result.canonical_json().expect("canonical JSON"))
        .expect("JSON value");
    value["nodes"][1]["displacement_m_rad"][0] = serde_json::json!(0.001);
    let stale =
        parse_linear_frame3d_result_ir_v1(&serde_json::to_vec(&value).expect("mutated JSON bytes"))
            .expect_err("transplanted result hash must fail");
    assert_eq!(stale.code, "frame3d_result_ir_hash_mismatch");

    let duplicate = result.canonical_json().expect("canonical JSON").replacen(
        '{',
        "{\"schema_version\":\"duplicate\",",
        1,
    );
    let duplicate_error = parse_linear_frame3d_result_ir_v1(duplicate.as_bytes())
        .expect_err("duplicate key must fail before typed decode");
    assert_eq!(duplicate_error.code, "frame3d_result_ir_json_invalid");
}

#[test]
fn failed_equilibrium_or_fallback_cannot_create_result_authority() {
    let mut failed_gate = input();
    failed_gate.gates.global_force_balance_scaled_linf = 2.0e-9;
    let error = create_linear_frame3d_result_ir_v1(failed_gate)
        .expect_err("failed balance gate must block ResultIR");
    assert!(matches!(
        error.code.as_str(),
        "frame3d_result_ir_schema_invalid" | "frame3d_result_ir_gate_failed"
    ));

    let mut failed_recovery = input();
    failed_recovery.gates.member_force_replay_scaled_linf = 2.0e-9;
    let error = create_linear_frame3d_result_ir_v1(failed_recovery)
        .expect_err("failed independent recovery gate must block ResultIR");
    assert!(matches!(
        error.code.as_str(),
        "frame3d_result_ir_schema_invalid" | "frame3d_result_ir_gate_failed"
    ));

    let mut fallback = input();
    fallback.gates.fallback_count = 1;
    let error =
        create_linear_frame3d_result_ir_v1(fallback).expect_err("fallback must block ResultIR");
    assert!(matches!(
        error.code.as_str(),
        "frame3d_result_ir_schema_invalid" | "frame3d_result_ir_promotion_gate_failed"
    ));
}
