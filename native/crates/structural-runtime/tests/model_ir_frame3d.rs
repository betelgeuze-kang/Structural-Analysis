use std::path::{Path, PathBuf};

use serde_json::{json, Value};
use structural_contracts::model_ir::{parse_model_ir_v2, ModelIrV2Document};
use structural_contracts::result_ir::parse_linear_frame3d_result_ir_v1;
use structural_runtime::Runtime;

const ABI_V1_5: u32 = 0x0001_0005;
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
    assert_eq!(axial.native_abi_version, ABI_V1_5);
    assert_eq!(axial.model_id, source.model_id());
    assert_eq!(axial.model_content_hash, source.content_hash());
    assert_eq!(axial.model_semantic_hash, source.semantic_hash());
    assert_eq!(axial.model_provenance_hash, source.provenance_hash());
    assert_eq!(axial.load_pattern_id.as_deref(), Some("LC_AXIAL"));
    assert_eq!(axial.load_combination_id, None);
    assert_eq!(axial.nodes.len(), 2);
    assert_eq!(axial.members.len(), 1);
    assert_eq!(axial.nodes[1].node_id, "N2");
    assert_eq!(axial.members[0].member_id, "E1");
    assert_near(axial.nodes[1].displacement_m_rad[0], 5.0e-5, 1.0e-14);
    assert_near(axial.nodes[0].reaction_n_nm[0], -100_000.0, 1.0e-7);
    assert_eq!(
        axial.claim_boundary,
        "bounded_cpu_linear_timoshenko_frame3d_nested_linear_combination_not_resultir_or_release_authority"
    );
    assert!(axial.gates.free_residual_scaled_linf <= 1.0e-9);
    assert!(axial.gates.global_force_balance_scaled_linf <= 1.0e-9);
    assert!(axial.gates.global_moment_balance_scaled_linf <= 1.0e-9);
    assert!(axial.gates.member_force_replay_scaled_linf <= 1.0e-9);

    let result_ir = runtime
        .analyze_linear_frame3d_result_ir(&source, "LC_AXIAL", "frame-alpha.LC_AXIAL")
        .expect("bounded ResultIR promotion");
    assert_eq!(result_ir.bindings.model_content_hash, source.content_hash());
    assert_eq!(
        result_ir.bindings.load_pattern_id.as_deref(),
        Some("LC_AXIAL")
    );
    assert_eq!(result_ir.bindings.load_combination_id, None);
    assert_eq!(result_ir.authority.member_force, "bounded_candidate");
    assert!(result_ir.claim_boundary.independent_recovery_replay);
    assert!(result_ir.claim_boundary.member_end_rotational_release);
    assert!(result_ir.claim_boundary.rigid_member_end_offset);
    assert!(result_ir.claim_boundary.self_weight_standard_gravity);
    assert!(
        result_ir
            .claim_boundary
            .linear_load_combination_superposition
    );
    assert!(result_ir.gates.independent_recovery_replay_passed);
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
fn independent_rust_recovery_replays_a_rotated_rolled_member() {
    let mut value = frame_alpha_value();
    value["nodes"][1]["coordinates_m"] = json!([1.3, -0.8, 2.1]);
    value["elements"][0]["local_axis_rotation_rad"] = json!(0.37);
    let source = document(&value);
    let runtime = Runtime::new().expect("native Frame3D runtime");

    let raw = runtime
        .analyze_linear_frame3d(&source, "LC_WEAK")
        .expect("rotated and rolled member solve with independent recovery replay");
    assert!(raw.gates.member_force_replay_scaled_linf <= 1.0e-9);

    let result = runtime
        .analyze_linear_frame3d_result_ir(&source, "LC_WEAK", "frame-alpha.rotated.LC_WEAK")
        .expect("replay-gated bounded ResultIR");
    assert!(result.gates.independent_recovery_replay_passed);
    assert!(result.claim_boundary.independent_recovery_replay);
    assert!(!result.claim_boundary.nodal_load_only);
    assert!(result.claim_boundary.uniform_member_load_initial_local);
}

#[test]
fn invalid_uniform_member_load_rows_fail_closed_before_native_solve() {
    let runtime = Runtime::new().expect("native Frame3D runtime");
    for (name, member_id, components, expected_code, expected_path) in [
        (
            "unknown member",
            "E404",
            json!({"QX": 0.0, "QY": -10000.0, "QZ": 0.0}),
            1101,
            "not contract-valid",
        ),
        (
            "zero row",
            "E1",
            json!({"QX": 0.0, "QY": 0.0, "QZ": 0.0}),
            1000,
            "/load_patterns/1/uniform_member_loads/0/components_si",
        ),
    ] {
        let mut value = frame_alpha_value();
        value["load_patterns"][1]["uniform_member_loads"] = json!([{
            "id": format!("INVALID_{}", name.replace(' ', "_")),
            "index": 0,
            "member_id": member_id,
            "basis": "initial_member_local",
            "behavior": "dead",
            "components_si": components,
            "source_id": null,
            "extensions": {}
        }]);
        let error = runtime
            .analyze_linear_frame3d(&document(&value), "LC_WEAK")
            .expect_err(name);
        assert_eq!(error.code, expected_code, "{name}");
        assert!(error.message.contains(expected_path), "{name}: {error}");
    }
}

#[test]
fn uniform_initial_local_member_load_reaches_result_ir_with_fixed_end_replay() {
    let mut value = frame_alpha_value();
    let pattern = value["load_patterns"]
        .as_array_mut()
        .expect("load patterns")
        .iter_mut()
        .find(|row| row["id"] == "LC_WEAK")
        .expect("weak-axis pattern");
    pattern["nodal_loads"] = json!([]);
    pattern["uniform_member_loads"] = json!([{
        "id": "UDL_E1_QY",
        "index": 0,
        "member_id": "E1",
        "basis": "initial_member_local",
        "behavior": "dead",
        "components_si": {"QX": 0.0, "QY": -10000.0, "QZ": 0.0},
        "source_id": null,
        "extensions": {}
    }]);
    let source = document(&value);
    let runtime = Runtime::new().expect("native Frame3D runtime");
    let raw = runtime
        .analyze_linear_frame3d(&source, "LC_WEAK")
        .expect("uniform member-load solve");
    assert_eq!(raw.native_abi_version, ABI_V1_5);
    assert!(raw.nodes[1].displacement_m_rad[1] < 0.0);
    assert_near(raw.nodes[0].reaction_n_nm[1], 20_000.0, 1.0e-6);
    assert_near(raw.nodes[0].reaction_n_nm[5], 20_000.0, 1.0e-6);
    assert_near(raw.members[0].end_i_force_n_nm[1], 20_000.0, 1.0e-6);
    assert_near(raw.members[0].end_i_force_n_nm[5], 20_000.0, 1.0e-6);
    assert_near(raw.members[0].end_j_force_n_nm[1], 0.0, 1.0e-6);
    assert_near(raw.members[0].end_j_force_n_nm[5], 0.0, 1.0e-6);
    assert!(raw.gates.free_residual_scaled_linf <= 1.0e-9);
    assert!(raw.gates.global_force_balance_scaled_linf <= 1.0e-9);
    assert!(raw.gates.global_moment_balance_scaled_linf <= 1.0e-9);
    assert!(raw.gates.member_force_replay_scaled_linf <= 1.0e-9);

    let result = runtime
        .analyze_linear_frame3d_result_ir(&source, "LC_WEAK", "frame-alpha.udl.LC_WEAK")
        .expect("member-load ResultIR promotion");
    assert!(result.gates.independent_recovery_replay_passed);
    assert!(result.claim_boundary.independent_recovery_replay);
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
fn rotational_end_release_condenses_stiffness_load_and_recovery() {
    let mut value = frame_alpha_value();
    value["elements"][0]["releases"]["i"] = json!(["RY"]);
    value["elements"][0]["releases"]["j"] = json!(["RZ"]);
    value["constraints"]
        .as_array_mut()
        .expect("constraints")
        .push(json!({
            "id": "BC2",
            "index": 1,
            "type": "fixed_dofs",
            "node_id": "N2",
            "dofs": ["UY", "UZ", "RY", "RZ"],
            "prescribed_values_si": {"UY": 0.0, "UZ": 0.0, "RY": 0.0, "RZ": 0.0},
            "source_id": "generated:BC2",
            "extensions": {}
        }));
    let pattern = value["load_patterns"]
        .as_array_mut()
        .expect("load patterns")
        .iter_mut()
        .find(|row| row["id"] == "LC_WEAK")
        .expect("weak-axis pattern");
    pattern["nodal_loads"] = json!([]);
    pattern["uniform_member_loads"] = json!([{
        "id": "UDL_E1_QY",
        "index": 0,
        "member_id": "E1",
        "basis": "initial_member_local",
        "behavior": "dead",
        "components_si": {"QX": 0.0, "QY": -10000.0, "QZ": 7000.0},
        "source_id": null,
        "extensions": {}
    }]);
    let source = document(&value);
    let result = Runtime::new()
        .expect("native Frame3D runtime")
        .analyze_linear_frame3d_result_ir(&source, "LC_WEAK", "frame-alpha.release.LC_WEAK")
        .expect("released member solve and ResultIR");

    assert_eq!(result.bindings.native_abi_version, ABI_V1_5);
    assert_near(result.members[0].end_i_force_n_nm[4], 0.0, 1.0e-7);
    assert_near(result.members[0].end_j_force_n_nm[5], 0.0, 1.0e-7);
    assert_near(result.nodes[0].reaction_n_nm[4], 0.0, 1.0e-7);
    assert_near(result.nodes[1].reaction_n_nm[5], 0.0, 1.0e-7);
    assert_near(
        result.nodes[0].reaction_n_nm[1] + result.nodes[1].reaction_n_nm[1],
        20_000.0,
        1.0e-6,
    );
    assert_near(
        result.nodes[0].reaction_n_nm[2] + result.nodes[1].reaction_n_nm[2],
        -14_000.0,
        1.0e-6,
    );
    assert!(result.claim_boundary.member_end_rotational_release);
    assert!(result.claim_boundary.rigid_member_end_offset);
    assert!(result.gates.independent_recovery_replay_passed);
}

#[test]
fn rigid_end_offsets_reach_native_geometry_and_independent_recovery() {
    let mut value = frame_alpha_value();
    value["elements"][0]["offsets"]["i_global_m"] = json!([0.25, 0.0, 0.0]);
    value["elements"][0]["offsets"]["j_global_m"] = json!([-0.25, 0.0, 0.0]);
    let source = document(&value);
    let result = Runtime::new()
        .expect("native Frame3D runtime")
        .analyze_linear_frame3d_result_ir(&source, "LC_AXIAL", "frame-alpha.offset.LC_AXIAL")
        .expect("offset member solve and ResultIR");

    assert_eq!(result.bindings.native_abi_version, ABI_V1_5);
    assert_near(result.nodes[1].displacement_m_rad[0], 3.75e-5, 1.0e-14);
    assert_near(result.nodes[0].reaction_n_nm[0], -100_000.0, 1.0e-7);
    assert!(result.claim_boundary.rigid_member_end_offset);
    assert!(result.gates.independent_recovery_replay_passed);
    assert!(result.gates.member_force_replay_scaled_linf <= 1.0e-9);
}

#[test]
fn rigid_offsets_transform_uniform_member_loads_through_resultant_gates() {
    let mut value = frame_alpha_value();
    value["elements"][0]["offsets"]["i_global_m"] = json!([0.10, 0.20, 0.05]);
    value["elements"][0]["offsets"]["j_global_m"] = json!([-0.05, 0.08, -0.02]);
    let pattern = value["load_patterns"]
        .as_array_mut()
        .expect("load patterns")
        .iter_mut()
        .find(|row| row["id"] == "LC_WEAK")
        .expect("weak-axis pattern");
    pattern["nodal_loads"] = json!([]);
    pattern["uniform_member_loads"] = json!([{
        "id": "UDL_E1_OFFSET",
        "index": 0,
        "member_id": "E1",
        "basis": "initial_member_local",
        "behavior": "dead",
        "components_si": {"QX": 3000.0, "QY": -10000.0, "QZ": 7000.0},
        "source_id": null,
        "extensions": {}
    }]);
    let source = document(&value);
    let result = Runtime::new()
        .expect("native Frame3D runtime")
        .analyze_linear_frame3d_result_ir(&source, "LC_WEAK", "frame-alpha.offset.LC_WEAK")
        .expect("offset member-load solve and ResultIR");

    assert!(result.claim_boundary.rigid_member_end_offset);
    assert!(result.gates.global_resultant_gate_passed);
    assert!(result.gates.independent_recovery_replay_passed);
    assert!(result.gates.global_force_balance_scaled_linf <= 1.0e-9);
    assert!(result.gates.global_moment_balance_scaled_linf <= 1.0e-9);
    assert!(result.gates.member_force_replay_scaled_linf <= 1.0e-9);
}

#[test]
fn standard_gravity_self_weight_matches_closed_form_axial_cantilever() {
    let mut value = frame_alpha_value();
    value["load_patterns"][0]["self_weight"] = json!([-1.0, 0.0, 0.0]);
    value["load_patterns"][0]["nodal_loads"] = json!([]);
    let source = document(&value);
    let result = Runtime::new()
        .expect("native Frame3D runtime")
        .analyze_linear_frame3d_result_ir(&source, "LC_AXIAL", "frame-alpha.self-weight.axial")
        .expect("self-weight-only ResultIR");

    let length_m = 2.0;
    let area_m2 = 0.02;
    let density_kg_m3 = 7_850.0;
    let elastic_modulus_pa = 200.0e9;
    let weight_n_m = density_kg_m3 * area_m2 * 9.806_65;
    let expected_tip_m = -weight_n_m * length_m * length_m / (2.0 * elastic_modulus_pa * area_m2);
    assert_near(
        result.nodes[1].displacement_m_rad[0],
        expected_tip_m,
        1.0e-15,
    );
    assert_near(
        result.nodes[0].reaction_n_nm[0],
        weight_n_m * length_m,
        1.0e-8,
    );
    assert!(result.claim_boundary.self_weight_standard_gravity);
    assert!(result.gates.global_resultant_gate_passed);
    assert!(result.gates.independent_recovery_replay_passed);
}

#[test]
fn rotated_offset_self_weight_passes_independent_resultant_and_recovery_gates() {
    let mut value = frame_alpha_value();
    value["nodes"][1]["coordinates_m"] = json!([1.2, -0.7, 2.3]);
    value["elements"][0]["local_axis_rotation_rad"] = json!(0.41);
    value["elements"][0]["offsets"]["i_global_m"] = json!([0.10, -0.04, 0.06]);
    value["elements"][0]["offsets"]["j_global_m"] = json!([-0.08, 0.05, -0.03]);
    value["load_patterns"][0]["self_weight"] = json!([0.25, -0.4, -1.0]);
    value["load_patterns"][0]["nodal_loads"] = json!([]);
    let source = document(&value);
    let result = Runtime::new()
        .expect("native Frame3D runtime")
        .analyze_linear_frame3d_result_ir(
            &source,
            "LC_AXIAL",
            "frame-alpha.self-weight.rotated-offset",
        )
        .expect("rotated offset self-weight ResultIR");

    assert!(result.claim_boundary.self_weight_standard_gravity);
    assert!(result.claim_boundary.rigid_member_end_offset);
    assert!(result.gates.global_resultant_gate_passed);
    assert!(result.gates.independent_recovery_replay_passed);
    assert!(result.gates.global_force_balance_scaled_linf <= 1.0e-9);
    assert!(result.gates.global_moment_balance_scaled_linf <= 1.0e-9);
    assert!(result.gates.member_force_replay_scaled_linf <= 1.0e-9);
}

#[test]
#[allow(clippy::too_many_lines)]
fn nested_linear_load_combination_matches_independent_pattern_superposition() {
    let mut value = frame_alpha_value();
    value["load_patterns"][0]["self_weight"] = json!([-0.2, 0.1, -0.3]);
    value["load_patterns"][1]["uniform_member_loads"] = json!([{
        "id": "UDL_COMB_WEAK",
        "index": 0,
        "member_id": "E1",
        "basis": "initial_member_local",
        "behavior": "dead",
        "components_si": {"QX": 2500.0, "QY": -4000.0, "QZ": 1500.0},
        "source_id": null,
        "extensions": {}
    }]);
    value["load_combinations"] = json!([
        {
            "id": "COMB_BASE",
            "index": 0,
            "combination_type": "linear",
            "terms": [
                {"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 1.25},
                {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": -0.4}
            ],
            "source_id": null,
            "extensions": {}
        },
        {
            "id": "COMB_NESTED",
            "index": 1,
            "combination_type": "linear",
            "terms": [
                {"ref_id": "COMB_BASE", "ref_kind": "load_combination", "factor": 0.8},
                {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": 1.1}
            ],
            "source_id": null,
            "extensions": {}
        }
    ]);
    let source = document(&value);
    let runtime = Runtime::new().expect("native Frame3D runtime");
    let axial = runtime
        .analyze_linear_frame3d(&source, "LC_AXIAL")
        .expect("axial pattern");
    let weak = runtime
        .analyze_linear_frame3d(&source, "LC_WEAK")
        .expect("weak pattern");
    let strong = runtime
        .analyze_linear_frame3d(&source, "LC_STRONG")
        .expect("strong pattern");
    let combined = runtime
        .analyze_linear_frame3d_combination(&source, "COMB_NESTED")
        .expect("nested linear combination");

    assert_eq!(combined.load_pattern_id, None);
    assert_eq!(combined.load_combination_id.as_deref(), Some("COMB_NESTED"));
    for node_index in 0..combined.nodes.len() {
        for component in 0..6 {
            let expected_displacement = axial.nodes[node_index].displacement_m_rad[component]
                - 0.32 * weak.nodes[node_index].displacement_m_rad[component]
                + 1.1 * strong.nodes[node_index].displacement_m_rad[component];
            let expected_reaction = axial.nodes[node_index].reaction_n_nm[component]
                - 0.32 * weak.nodes[node_index].reaction_n_nm[component]
                + 1.1 * strong.nodes[node_index].reaction_n_nm[component];
            assert_near(
                combined.nodes[node_index].displacement_m_rad[component],
                expected_displacement,
                1.0e-12 * expected_displacement.abs().max(1.0),
            );
            assert_near(
                combined.nodes[node_index].reaction_n_nm[component],
                expected_reaction,
                1.0e-10 * expected_reaction.abs().max(1.0),
            );
        }
    }
    for member_index in 0..combined.members.len() {
        for component in 0..6 {
            for (actual, axial_value, weak_value, strong_value) in [
                (
                    combined.members[member_index].end_i_force_n_nm[component],
                    axial.members[member_index].end_i_force_n_nm[component],
                    weak.members[member_index].end_i_force_n_nm[component],
                    strong.members[member_index].end_i_force_n_nm[component],
                ),
                (
                    combined.members[member_index].end_j_force_n_nm[component],
                    axial.members[member_index].end_j_force_n_nm[component],
                    weak.members[member_index].end_j_force_n_nm[component],
                    strong.members[member_index].end_j_force_n_nm[component],
                ),
            ] {
                let expected = axial_value - 0.32 * weak_value + 1.1 * strong_value;
                assert_near(actual, expected, 1.0e-10 * expected.abs().max(1.0));
            }
        }
    }
    assert!(combined.gates.global_force_balance_scaled_linf <= 1.0e-9);
    assert!(combined.gates.global_moment_balance_scaled_linf <= 1.0e-9);
    assert!(combined.gates.member_force_replay_scaled_linf <= 1.0e-9);

    let result = runtime
        .analyze_linear_frame3d_combination_result_ir(
            &source,
            "COMB_NESTED",
            "frame-alpha.COMB_NESTED",
        )
        .expect("combination ResultIR");
    assert_eq!(result.bindings.load_pattern_id, None);
    assert_eq!(
        result.bindings.load_combination_id.as_deref(),
        Some("COMB_NESTED")
    );
    assert!(result.claim_boundary.linear_load_combination_superposition);
}

#[test]
fn load_combination_selection_and_factor_overflow_fail_closed() {
    let runtime = Runtime::new().expect("native Frame3D runtime");
    let mut value = frame_alpha_value();
    value["load_combinations"] = json!([{
        "id": "COMB_HUGE",
        "index": 0,
        "combination_type": "linear",
        "terms": [{"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 1.0e308}],
        "source_id": null,
        "extensions": {}
    }, {
        "id": "COMB_OVERFLOW",
        "index": 1,
        "combination_type": "linear",
        "terms": [{"ref_id": "COMB_HUGE", "ref_kind": "load_combination", "factor": 1.0e308}],
        "source_id": null,
        "extensions": {}
    }]);
    let source = document(&value);

    let missing = runtime
        .analyze_linear_frame3d_combination(&source, "COMB_MISSING")
        .expect_err("unknown combination must not default");
    assert_eq!(missing.code, 1000);
    assert!(missing.message.contains("/load_combinations"));

    let overflow = runtime
        .analyze_linear_frame3d_combination(&source, "COMB_OVERFLOW")
        .expect_err("factor product overflow must fail closed");
    assert_eq!(overflow.code, 1000);
    assert!(overflow.message.contains("/load_combinations/0/terms/0"));
}

#[test]
fn load_combination_count_and_expansion_bounds_fail_closed() {
    let runtime = Runtime::new().expect("native Frame3D runtime");
    let mut count_value = frame_alpha_value();
    count_value["load_combinations"] = Value::Array(
        (0..257)
            .map(|index| {
                json!({
                    "id": format!("COMB{index}"),
                    "index": index,
                    "combination_type": "linear",
                    "terms": [{
                        "ref_id": "LC_AXIAL",
                        "ref_kind": "load_pattern",
                        "factor": 1.0
                    }],
                    "source_id": null,
                    "extensions": {}
                })
            })
            .collect(),
    );
    let count_error = runtime
        .analyze_linear_frame3d_combination(&document(&count_value), "COMB256")
        .expect_err("combination count bound must fail closed");
    assert_eq!(count_error.code, UNSUPPORTED);
    assert!(count_error.message.contains("/load_combinations"));

    let mut expansion_value = frame_alpha_value();
    expansion_value["load_combinations"] = json!([{
        "id": "COMB_EXPANDED",
        "index": 0,
        "combination_type": "linear",
        "terms": (0..4097).map(|_| json!({
            "ref_id": "LC_AXIAL",
            "ref_kind": "load_pattern",
            "factor": 1.0
        })).collect::<Vec<_>>(),
        "source_id": null,
        "extensions": {}
    }]);
    let expansion_error = runtime
        .analyze_linear_frame3d_combination(&document(&expansion_value), "COMB_EXPANDED")
        .expect_err("expanded term bound must fail closed");
    assert_eq!(expansion_error.code, UNSUPPORTED);
    assert!(expansion_error
        .message
        .contains("expanded load-combination term count"));
}

#[test]
fn unsupported_frame_features_fail_closed_before_native_compilation() {
    let runtime = Runtime::new().expect("native Frame3D runtime");
    let cases: Vec<(&str, Value, &str)> = vec![
        (
            "translational release",
            {
                let mut value = frame_alpha_value();
                value["elements"][0]["releases"]["i"] = json!(["UY"]);
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
