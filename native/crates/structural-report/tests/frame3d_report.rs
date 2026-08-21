use structural_contracts::report_ir::parse_linear_frame3d_report_ir_v1;
use structural_contracts::result_ir::{
    create_linear_frame3d_result_ir_v1, Frame3dResultBindingsV1, Frame3dResultGatesV1,
    Frame3dResultMemberV1, Frame3dResultNodeV1, LinearFrame3dResultIrInput,
};
use structural_report::{build_linear_frame3d_report, validate_linear_frame3d_report_source};

fn hash(character: char) -> String {
    format!("sha256:{}", character.to_string().repeat(64))
}

fn result(model_hash_character: char) -> structural_contracts::result_ir::LinearFrame3dResultIrV1 {
    create_linear_frame3d_result_ir_v1(LinearFrame3dResultIrInput {
        result_id: "frame-alpha.LC1".to_owned(),
        bindings: Frame3dResultBindingsV1 {
            model_id: "frame-alpha".to_owned(),
            model_content_hash: hash(model_hash_character),
            model_semantic_hash: hash('b'),
            model_provenance_hash: hash('c'),
            load_pattern_id: "LC1".to_owned(),
            native_abi_version: 0x0001_0003,
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
    })
    .expect("bounded ResultIR")
}

#[test]
fn report_ir_and_html_are_byte_deterministic_and_authority_limited() {
    let source = result('a');
    let first = build_linear_frame3d_report(&source, "frame-alpha.LC1.report")
        .expect("deterministic report");
    let second = build_linear_frame3d_report(&source, "frame-alpha.LC1.report")
        .expect("deterministic replay");

    assert_eq!(first, second);
    assert_eq!(first.report_ir.extrema[0].entity_id, "N2");
    assert_eq!(first.report_ir.extrema[0].component, "UX");
    assert_eq!(
        first.report_ir.extrema[1].signed_value.to_bits(),
        (-100_000.0_f64).to_bits()
    );
    assert_eq!(first.report_ir.extrema[2].component, "FX_I");
    assert_eq!(first.report_ir.authority.comparison, "not_evaluated");
    assert!(first
        .report_ir
        .limitations
        .iter()
        .any(|value| value == "load_scope_nodal_and_uniform_initial_local_force"));
    assert!(first
        .report_ir
        .limitations
        .iter()
        .any(|value| value == "no_nonuniform_or_member_point_load"));
    assert_eq!(
        first.report_ir.authority.engineering_design,
        "not_authoritative"
    );
    assert!(first.html.starts_with("<!doctype html>\n"));
    assert!(first.html.contains("2.00000000000000016e-15"));
    assert!(first
        .html
        .contains("Independent member-force recovery replay"));
    assert!(first
        .html
        .contains("load_scope_nodal_and_uniform_initial_local_force"));
    assert!(first.html_hash.starts_with("sha256:"));

    let canonical = first
        .report_ir
        .canonical_json()
        .expect("canonical ReportIR");
    let parsed = parse_linear_frame3d_report_ir_v1(canonical.as_bytes())
        .expect("strict ReportIR round-trip");
    validate_linear_frame3d_report_source(&parsed, &source).expect("exact source binding");
}

#[test]
fn result_transplant_and_stale_report_hash_fail_closed() {
    let source = result('a');
    let bundle = build_linear_frame3d_report(&source, "frame-alpha.LC1.report")
        .expect("deterministic report");
    let other_source = result('d');
    let transplant = validate_linear_frame3d_report_source(&bundle.report_ir, &other_source)
        .expect_err("another valid ResultIR must not inherit this report");
    assert_eq!(transplant.code, "frame3d_report_source_binding_mismatch");

    let stale = bundle
        .report_ir
        .canonical_json()
        .expect("canonical ReportIR")
        .replace("100000", "200000");
    let stale_error = parse_linear_frame3d_report_ir_v1(stale.as_bytes())
        .expect_err("mutated report bytes must fail closed");
    assert_eq!(stale_error.code, "frame3d_report_ir_hash_mismatch");

    let duplicate = bundle
        .report_ir
        .canonical_json()
        .expect("canonical ReportIR")
        .replacen('{', "{\"report_id\":\"duplicate\",", 1);
    let duplicate_error = parse_linear_frame3d_report_ir_v1(duplicate.as_bytes())
        .expect_err("duplicate report key must fail before typed decode");
    assert_eq!(duplicate_error.code, "frame3d_report_ir_json_invalid");
}
