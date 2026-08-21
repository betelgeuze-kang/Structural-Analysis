use std::path::{Path, PathBuf};

use serde_json::{json, Value};
use structural_contracts::model_ir::{parse_model_ir_v2, ModelIrV2Document};
use structural_contracts::result_ir::parse_linear_frame3d_result_ir_v1;
use structural_runtime::Runtime;

const ABI_V1_2: u32 = 0x0001_0002;
const UNSUPPORTED: u32 = 1200;

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

fn fixture_value() -> Value {
    serde_json::from_slice(
        &std::fs::read(
            repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"),
        )
        .expect("tracked ModelIR fixture"),
    )
    .expect("fixture JSON")
}

fn document(value: &Value) -> ModelIrV2Document {
    parse_model_ir_v2(&serde_json::to_vec(value).expect("JSON bytes"))
        .expect("schema-valid ModelIR")
}

fn frame_alpha_value() -> Value {
    let mut value = fixture_value();
    value["elements"][0]["formulation"] = json!("linear_timoshenko_frame3d");
    value
}

fn assert_near(actual: f64, expected: f64, tolerance: f64) {
    assert!(
        (actual - expected).abs() <= tolerance,
        "expected {expected} +/- {tolerance}, got {actual}"
    );
}

#[test]
fn tracked_cantilever_fixture_solves_four_modes_with_si_results_and_bound_identity() {
    let source = document(&frame_alpha_value());
    let runtime = Runtime::new().expect("native Frame3D runtime");

    let axial = runtime
        .analyze_linear_frame3d(&source, "LC_AXIAL")
        .expect("axial solve");
    assert_eq!(
        axial.schema_version,
        "structural-native-linear-frame3d-result.v1"
    );
    assert_eq!(axial.native_abi_version, ABI_V1_2);
    assert_eq!(axial.model_id, source.model_id());
    assert_eq!(axial.model_content_hash, source.content_hash());
    assert_eq!(axial.model_semantic_hash, source.semantic_hash());
    assert_eq!(axial.model_provenance_hash, source.provenance_hash());
    assert_eq!(axial.load_pattern_id, "LC_AXIAL");
    assert_eq!(axial.nodes.len(), 2);
    assert_eq!(axial.members.len(), 1);
    assert_eq!(axial.nodes[1].node_id, "N2");
    assert_eq!(axial.members[0].member_id, "E1");
    assert_near(axial.nodes[1].displacement_m_rad[0], 5.0e-5, 1.0e-14);
    assert_near(axial.nodes[0].reaction_n_nm[0], -100_000.0, 1.0e-7);
    assert_eq!(
        axial.claim_boundary,
        "bounded_cpu_linear_timoshenko_frame3d_not_resultir_or_release_authority"
    );
    assert!(axial.gates.free_residual_scaled_linf <= 1.0e-9);
    assert!(axial.gates.global_force_balance_scaled_linf <= 1.0e-9);
    assert!(axial.gates.global_moment_balance_scaled_linf <= 1.0e-9);

    let result_ir = runtime
        .analyze_linear_frame3d_result_ir(&source, "LC_AXIAL", "frame-alpha.LC_AXIAL")
        .expect("bounded ResultIR promotion");
    assert_eq!(result_ir.bindings.model_content_hash, source.content_hash());
    assert_eq!(result_ir.bindings.load_pattern_id, "LC_AXIAL");
    assert_eq!(result_ir.authority.member_force, "bounded_candidate");
    assert!(!result_ir.claim_boundary.independent_recovery_replay);
    assert!(!result_ir.claim_boundary.workbench_e2e);
    assert!(!result_ir.claim_boundary.release_readiness);
    let canonical = result_ir.canonical_json().expect("canonical ResultIR");
    assert_eq!(
        parse_linear_frame3d_result_ir_v1(canonical.as_bytes()).expect("strict ResultIR replay"),
        result_ir
    );

    let weak = runtime
        .analyze_linear_frame3d(&source, "LC_WEAK")
        .expect("weak-axis solve");
    assert!(weak.nodes[1].displacement_m_rad[1] < 0.0);
    assert_near(weak.nodes[0].reaction_n_nm[1], 10_000.0, 1.0e-7);
    assert_near(weak.nodes[0].reaction_n_nm[5], 20_000.0, 1.0e-7);

    let strong = runtime
        .analyze_linear_frame3d(&source, "LC_STRONG")
        .expect("strong-axis solve");
    assert!(strong.nodes[1].displacement_m_rad[2] < 0.0);
    assert_near(strong.nodes[0].reaction_n_nm[2], 10_000.0, 1.0e-7);
    assert_near(strong.nodes[0].reaction_n_nm[4], -20_000.0, 1.0e-7);

    let torsion = runtime
        .analyze_linear_frame3d(&source, "LC_TORSION")
        .expect("torsion solve");
    assert!(torsion.nodes[1].displacement_m_rad[3] > 0.0);
    assert_near(torsion.nodes[0].reaction_n_nm[3], -5_000.0, 1.0e-7);
    assert!(torsion
        .members
        .iter()
        .flat_map(|member| member
            .end_i_force_n_nm
            .iter()
            .chain(&member.end_j_force_n_nm))
        .all(|value| value.is_finite()));
}

#[test]
fn euler_fixture_is_not_silently_substituted_with_timoshenko() {
    let runtime = Runtime::new().expect("native Frame3D runtime");
    let error = runtime
        .analyze_linear_frame3d(&document(&fixture_value()), "LC_AXIAL")
        .expect_err("Euler formulation is a distinct contract");

    assert_eq!(error.code, UNSUPPORTED);
    assert!(error.message.contains("/elements/0/formulation"));
}

#[test]
fn unsupported_frame_features_fail_closed_before_native_compilation() {
    let runtime = Runtime::new().expect("native Frame3D runtime");
    let cases: Vec<(&str, Value, &str)> = vec![
        (
            "offset",
            {
                let mut value = frame_alpha_value();
                value["elements"][0]["offsets"]["j_global_m"] = json!([0.01, 0.0, 0.0]);
                value
            },
            "/elements/0/offsets/j_global_m",
        ),
        (
            "release",
            {
                let mut value = frame_alpha_value();
                value["elements"][0]["releases"]["i"] = json!(["RZ"]);
                value
            },
            "/elements/0/releases/i",
        ),
        (
            "settlement",
            {
                let mut value = frame_alpha_value();
                value["constraints"][0]["prescribed_values_si"]["UX"] = json!(0.001);
                value
            },
            "/constraints/0/prescribed_values_si/UX",
        ),
        (
            "self weight",
            {
                let mut value = frame_alpha_value();
                value["load_patterns"][0]["self_weight"] = json!([0.0, 0.0, -1.0]);
                value
            },
            "/load_patterns/0/self_weight",
        ),
        (
            "physics extension",
            {
                let mut value = frame_alpha_value();
                value["elements"][0]["extensions"] = json!({"vendor.test:feature": true});
                value
            },
            "/elements/0/extensions",
        ),
    ];

    for (name, value, expected_path) in cases {
        let error = runtime
            .analyze_linear_frame3d(&document(&value), "LC_AXIAL")
            .expect_err(name);
        assert_eq!(error.code, UNSUPPORTED, "{name}");
        assert!(error.message.contains(expected_path), "{name}: {error}");
    }
}

#[test]
fn unknown_load_pattern_is_rejected_without_defaulting() {
    let runtime = Runtime::new().expect("native Frame3D runtime");
    let error = runtime
        .analyze_linear_frame3d(&document(&frame_alpha_value()), "LC_MISSING")
        .expect_err("unknown load pattern must not default");

    assert_eq!(error.code, 1000);
    assert!(error.message.contains("/load_patterns"));
}

#[test]
fn invalid_result_id_fails_at_the_runtime_input_boundary() {
    let runtime = Runtime::new().expect("native Frame3D runtime");
    let error = runtime
        .analyze_linear_frame3d_result_ir(
            &document(&frame_alpha_value()),
            "LC_AXIAL",
            "invalid result id",
        )
        .expect_err("ResultIR IDs are stable identifiers");

    assert_eq!(error.code, 1000);
    assert!(error.message.contains("/result_id"));
}
