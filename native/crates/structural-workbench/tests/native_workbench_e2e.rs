use std::ffi::OsStr;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicU64, Ordering};

use serde_json::Value;
use structural_cli::execute_model_ir_linear_analysis;
use structural_contracts::model_ir::{canonicalize_model_ir_v2, parse_model_ir_v2};
use structural_contracts::model_linear_product::parse_model_ir_linear_analysis_request_v1;
use structural_contracts::product_ir::sha256_identity;
use structural_report::{validate_deterministic_localized_pdf_v2, validate_deterministic_pdf_v1};

static TEST_SEQUENCE: AtomicU64 = AtomicU64::new(0);

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

struct TestDirectory(PathBuf);

impl TestDirectory {
    fn create() -> Self {
        let sequence = TEST_SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "structural-native-workbench-test-{}-{sequence}",
            std::process::id()
        ));
        std::fs::create_dir(&path).expect("create isolated Workbench test directory");
        Self(path)
    }
}

impl Drop for TestDirectory {
    fn drop(&mut self) {
        std::fs::remove_dir_all(&self.0).expect("remove isolated Workbench test directory");
    }
}

fn text(value: &str) -> &OsStr {
    OsStr::new(value)
}

fn run_workbench(arguments: &[&OsStr]) -> Output {
    let mut command = Command::new(env!("CARGO_BIN_EXE_structural-workbench"));
    command.env_clear();
    command.args(arguments);
    command.output().expect("execute Rust-native Workbench")
}

fn assert_success(output: &Output) {
    assert!(
        output.status.success(),
        "stdout={}\nstderr={}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
}

fn inputs() -> (PathBuf, PathBuf, PathBuf, PathBuf) {
    let root = repository_root();
    (
        root.join("native/tests/fixtures/model_ir_adapter/fixed_guided_frame3d_x.json"),
        root.join("native/tests/fixtures/model_ir_adapter/fixed_guided_ndtha_request.json"),
        root.join("native/tests/fixtures/external_comparison/reference_oracle_ndtha_v1.json"),
        root.join(
            "native/tests/fixtures/solver_cpu/nonlinear_ndtha_one_story_elastic_python_c1.json",
        ),
    )
}

fn mgt_inputs() -> (PathBuf, PathBuf, PathBuf, PathBuf) {
    let root = repository_root();
    (
        root.join("native/tests/fixtures/mgt_import/workbench_fixed_guided_frame3d_x.mgt"),
        root.join("native/tests/fixtures/mgt_import/workbench_fixed_guided_ndtha_request.json"),
        root.join("native/tests/fixtures/external_comparison/reference_oracle_ndtha_v1.json"),
        root.join(
            "native/tests/fixtures/solver_cpu/nonlinear_ndtha_one_story_elastic_python_c1.json",
        ),
    )
}

fn evidence_fixture() -> PathBuf {
    repository_root().join("native/tests/fixtures/workbench_evidence")
}

fn copy_evidence_fixture(destination: &Path) {
    std::fs::create_dir_all(destination.join("readiness")).expect("create evidence fixture copy");
    std::fs::copy(
        evidence_fixture().join("manifest.json"),
        destination.join("manifest.json"),
    )
    .expect("copy evidence manifest");
    for name in ["ready.json", "blocked.json", "unavailable.json"] {
        std::fs::copy(
            evidence_fixture().join("readiness").join(name),
            destination.join("readiness").join(name),
        )
        .expect("copy evidence artifact");
    }
}

fn assert_blocked_model_remains_viewable(temporary: &Path, model: &Value) {
    let mut blocked = model.clone();
    blocked["unsupported_features"] = serde_json::json!([{
        "feature_id": "feature.blocked",
        "kind": "unsupported_solver_feature",
        "source_entity_id": null,
        "disposition": "blocked",
        "blocking": true,
        "detail": "Requires a solver capability outside this slice.",
        "extensions": {}
    }]);
    let blocked_path = temporary.join("blocked.model-ir.json");
    std::fs::write(
        &blocked_path,
        serde_json::to_vec(&blocked).expect("blocked ModelIR bytes"),
    )
    .expect("write blocked ModelIR");
    let visible_blocker = run_workbench(&[text("model-view"), blocked_path.as_os_str()]);
    assert_success(&visible_blocker);
    let view = String::from_utf8(visible_blocker.stdout).expect("blocked model view");
    assert!(view.contains("Analysis ready: false\n"));
    assert!(view.contains("Blocking features: feature.blocked\n"));
}

fn run_node_edit(
    source: &Path,
    destination: &Path,
    node_id: &str,
    coordinates: [&str; 3],
) -> Output {
    run_workbench(&[
        text("model-edit-node"),
        source.as_os_str(),
        text("--node"),
        text(node_id),
        text("--coordinates"),
        text(coordinates[0]),
        text(coordinates[1]),
        text(coordinates[2]),
        text("--output-dir"),
        destination.as_os_str(),
    ])
}

fn assert_published_node_edit(destination: &Path) {
    let edited_bytes = std::fs::read(destination.join("model-ir.json")).expect("edited ModelIR");
    let edited = parse_model_ir_v2(&edited_bytes).expect("strict edited ModelIR");
    let node = edited
        .value()
        .get("nodes")
        .and_then(Value::as_array)
        .and_then(|nodes| {
            nodes
                .iter()
                .find(|node| node.get("id").and_then(Value::as_str) == Some("N2"))
        })
        .expect("edited node");
    let coordinates = node["coordinates_m"]
        .as_array()
        .expect("edited node coordinates");
    for (actual, expected) in coordinates.iter().zip([2.0_f64, 1.0_f64, 1.0_f64]) {
        assert_eq!(
            actual.as_f64().expect("finite coordinate").to_bits(),
            expected.to_bits()
        );
    }
    assert_eq!(
        edited.value()["provenance"]["normalizer_id"],
        "structural-native-model-editor"
    );
    assert!(edited.value()["provenance"]["extensions"]
        .get("structural-native:upstream-provenance")
        .is_some());
    assert!(edited.value()["extensions"]
        .get("structural-native:model-edit-node.v1")
        .is_some());

    let receipt_bytes = std::fs::read(destination.join("edit-receipt.json")).expect("edit receipt");
    let mut receipt: Value = serde_json::from_slice(&receipt_bytes).expect("edit receipt JSON");
    assert_eq!(
        receipt["schema_version"],
        "structural-native-model-edit-receipt.v1"
    );
    assert_eq!(receipt["cpp_semantic_snapshot_verified"], true);
    assert_eq!(receipt["analysis_ready"], true);
    assert_eq!(receipt["edited_content_hash"], edited.content_hash());
    assert_ne!(
        receipt["source_semantic_hash"],
        receipt["edited_semantic_hash"]
    );
    assert_ne!(
        receipt["source_provenance_hash"],
        receipt["edited_provenance_hash"]
    );
    let expected_receipt_hash = receipt
        .as_object_mut()
        .and_then(|object| object.remove("receipt_hash"))
        .and_then(|value| value.as_str().map(ToOwned::to_owned))
        .expect("receipt self-hash");
    let unsigned = canonicalize_model_ir_v2(&receipt).expect("unsigned canonical receipt");
    assert_eq!(expected_receipt_hash, sha256_identity(unsigned.as_bytes()));

    let view = run_workbench(&[
        text("model-view"),
        destination.join("model-ir.json").as_os_str(),
    ]);
    assert_success(&view);
    assert!(String::from_utf8_lossy(&view.stdout).contains("C++ semantic snapshot: verified\n"));
}

fn assert_rejected_node_edit(
    source: &Path,
    temporary: &Path,
    name: &str,
    node_id: &str,
    coordinates: [&str; 3],
    expected_code: &str,
) {
    let destination = temporary.join(name);
    let rejected = run_node_edit(source, &destination, node_id, coordinates);
    assert_eq!(
        rejected.status.code(),
        Some(1),
        "unexpected node edit status for {name}: stdout={} stderr={}",
        String::from_utf8_lossy(&rejected.stdout),
        String::from_utf8_lossy(&rejected.stderr)
    );
    assert!(String::from_utf8_lossy(&rejected.stdout).contains(expected_code));
    assert!(!destination.exists());
}

fn run_nodal_load_edit(
    source: &Path,
    destination: &Path,
    load_pattern_id: &str,
    nodal_load_id: &str,
    components: [&str; 6],
) -> Output {
    run_workbench(&[
        text("model-edit-nodal-load"),
        source.as_os_str(),
        text("--load-pattern"),
        text(load_pattern_id),
        text("--load"),
        text(nodal_load_id),
        text("--components"),
        text(components[0]),
        text(components[1]),
        text(components[2]),
        text(components[3]),
        text(components[4]),
        text(components[5]),
        text("--output-dir"),
        destination.as_os_str(),
    ])
}

fn assert_published_nodal_load_edit(destination: &Path) {
    let edited_bytes = std::fs::read(destination.join("model-ir.json")).expect("edited ModelIR");
    let edited = parse_model_ir_v2(&edited_bytes).expect("strict edited ModelIR");
    let load = edited
        .value()
        .get("load_patterns")
        .and_then(Value::as_array)
        .and_then(|patterns| {
            patterns
                .iter()
                .find(|pattern| pattern.get("id").and_then(Value::as_str) == Some("LC_WEAK"))
        })
        .and_then(|pattern| pattern.get("nodal_loads"))
        .and_then(Value::as_array)
        .and_then(|loads| {
            loads
                .iter()
                .find(|load| load.get("id").and_then(Value::as_str) == Some("L_WEAK_N2"))
        })
        .expect("edited nodal load");
    for (key, expected) in [
        ("FX", 0.0_f64),
        ("FY", -20_000.0),
        ("FZ", 0.0),
        ("MX", 0.0),
        ("MY", 0.0),
        ("MZ", 0.0),
    ] {
        assert_eq!(
            load["components_si"][key]
                .as_f64()
                .expect("finite edited component")
                .to_bits(),
            expected.to_bits()
        );
    }
    assert_eq!(
        edited.value()["provenance"]["normalizer_id"],
        "structural-native-model-editor"
    );
    assert!(edited.value()["provenance"]["extensions"]
        .get("structural-native:upstream-provenance")
        .is_some());
    assert!(edited.value()["extensions"]
        .get("structural-native:model-edit-nodal-load.v1")
        .is_some());

    let receipt_bytes = std::fs::read(destination.join("edit-receipt.json")).expect("edit receipt");
    let mut receipt: Value = serde_json::from_slice(&receipt_bytes).expect("edit receipt JSON");
    assert_eq!(
        receipt["schema_version"],
        "structural-native-model-edit-receipt.v1"
    );
    assert_eq!(receipt["operation"], "nodal_load_components");
    assert_eq!(receipt["load_pattern_id"], "LC_WEAK");
    assert_eq!(receipt["nodal_load_id"], "L_WEAK_N2");
    assert_eq!(receipt["previous_components_si"]["FY"], -10_000.0);
    assert_eq!(receipt["edited_components_si"]["FY"], -20_000.0);
    assert_eq!(receipt["cpp_semantic_snapshot_verified"], true);
    assert_eq!(receipt["analysis_ready"], true);
    assert_eq!(receipt["edited_content_hash"], edited.content_hash());
    assert_ne!(
        receipt["source_semantic_hash"],
        receipt["edited_semantic_hash"]
    );
    assert_ne!(
        receipt["source_provenance_hash"],
        receipt["edited_provenance_hash"]
    );
    let expected_receipt_hash = receipt
        .as_object_mut()
        .and_then(|object| object.remove("receipt_hash"))
        .and_then(|value| value.as_str().map(ToOwned::to_owned))
        .expect("receipt self-hash");
    let unsigned = canonicalize_model_ir_v2(&receipt).expect("unsigned canonical receipt");
    assert_eq!(expected_receipt_hash, sha256_identity(unsigned.as_bytes()));
}

fn assert_rejected_nodal_load_edit(
    source: &Path,
    temporary: &Path,
    name: &str,
    load_pattern_id: &str,
    nodal_load_id: &str,
    components: [&str; 6],
    expected_code: &str,
) {
    let destination = temporary.join(name);
    let rejected = run_nodal_load_edit(
        source,
        &destination,
        load_pattern_id,
        nodal_load_id,
        components,
    );
    assert_eq!(rejected.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&rejected.stdout).contains(expected_code));
    assert!(!destination.exists());
}

fn run_constraint_value_edit(
    source: &Path,
    destination: &Path,
    constraint_id: &str,
    dof: &str,
    value_si: &str,
) -> Output {
    run_workbench(&[
        text("model-edit-constraint-value"),
        source.as_os_str(),
        text("--constraint"),
        text(constraint_id),
        text("--dof"),
        text(dof),
        text("--value"),
        text(value_si),
        text("--output-dir"),
        destination.as_os_str(),
    ])
}

fn assert_published_constraint_value_edit(destination: &Path) {
    let edited_bytes = std::fs::read(destination.join("model-ir.json")).expect("edited ModelIR");
    let edited = parse_model_ir_v2(&edited_bytes).expect("strict edited ModelIR");
    let constraint = edited
        .value()
        .get("constraints")
        .and_then(Value::as_array)
        .and_then(|constraints| {
            constraints
                .iter()
                .find(|constraint| constraint.get("id").and_then(Value::as_str) == Some("BC2"))
        })
        .expect("edited constraint");
    assert_eq!(
        constraint["prescribed_values_si"]["UY"]
            .as_f64()
            .expect("finite prescribed value")
            .to_bits(),
        (-0.0002_f64).to_bits()
    );
    assert_eq!(
        edited.value()["provenance"]["normalizer_id"],
        "structural-native-model-editor"
    );
    assert!(edited.value()["provenance"]["extensions"]
        .get("structural-native:upstream-provenance")
        .is_some());
    assert!(edited.value()["extensions"]
        .get("structural-native:model-edit-constraint-value.v1")
        .is_some());

    let receipt_bytes = std::fs::read(destination.join("edit-receipt.json")).expect("edit receipt");
    let mut receipt: Value = serde_json::from_slice(&receipt_bytes).expect("edit receipt JSON");
    assert_eq!(
        receipt["schema_version"],
        "structural-native-model-edit-receipt.v1"
    );
    assert_eq!(receipt["operation"], "constraint_prescribed_value");
    assert_eq!(receipt["constraint_id"], "BC2");
    assert_eq!(receipt["dof"], "UY");
    assert_eq!(receipt["unit"], "m");
    assert_eq!(receipt["previous_value_si"], -0.0001);
    assert_eq!(receipt["edited_value_si"], -0.0002);
    assert_eq!(receipt["cpp_semantic_snapshot_verified"], true);
    assert_eq!(receipt["analysis_ready"], true);
    assert_eq!(receipt["edited_content_hash"], edited.content_hash());
    assert_ne!(
        receipt["source_semantic_hash"],
        receipt["edited_semantic_hash"]
    );
    assert_ne!(
        receipt["source_provenance_hash"],
        receipt["edited_provenance_hash"]
    );
    let expected_receipt_hash = receipt
        .as_object_mut()
        .and_then(|object| object.remove("receipt_hash"))
        .and_then(|value| value.as_str().map(ToOwned::to_owned))
        .expect("receipt self-hash");
    let unsigned = canonicalize_model_ir_v2(&receipt).expect("unsigned canonical receipt");
    assert_eq!(expected_receipt_hash, sha256_identity(unsigned.as_bytes()));
}

fn assert_rejected_constraint_value_edit(
    source: &Path,
    temporary: &Path,
    name: &str,
    constraint_id: &str,
    dof: &str,
    value_si: &str,
    expected_code: &str,
) {
    let destination = temporary.join(name);
    let rejected = run_constraint_value_edit(source, &destination, constraint_id, dof, value_si);
    assert_eq!(rejected.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&rejected.stdout).contains(expected_code));
    assert!(!destination.exists());
}

fn run_linear_material_edit(
    source: &Path,
    destination: &Path,
    material_id: &str,
    parameters: [&str; 3],
) -> Output {
    run_workbench(&[
        text("model-edit-linear-material"),
        source.as_os_str(),
        text("--material"),
        text(material_id),
        text("--elastic-modulus-pa"),
        text(parameters[0]),
        text("--poisson-ratio"),
        text(parameters[1]),
        text("--density-kg-m3"),
        text(parameters[2]),
        text("--output-dir"),
        destination.as_os_str(),
    ])
}

fn run_frame_section_edit(
    source: &Path,
    destination: &Path,
    section_id: &str,
    parameters: [&str; 6],
) -> Output {
    run_workbench(&[
        text("model-edit-frame-section"),
        source.as_os_str(),
        text("--section"),
        text(section_id),
        text("--area-m2"),
        text(parameters[0]),
        text("--iy-m4"),
        text(parameters[1]),
        text("--iz-m4"),
        text(parameters[2]),
        text("--torsional-constant-m4"),
        text(parameters[3]),
        text("--shear-area-y-m2"),
        text(parameters[4]),
        text("--shear-area-z-m2"),
        text(parameters[5]),
        text("--output-dir"),
        destination.as_os_str(),
    ])
}

fn run_frame_element_orientation_edit(
    source: &Path,
    destination: &Path,
    element_id: &str,
    rotation_rad: &str,
) -> Output {
    run_workbench(&[
        text("model-edit-frame-element-orientation"),
        source.as_os_str(),
        text("--element"),
        text(element_id),
        text("--rotation-rad"),
        text(rotation_rad),
        text("--output-dir"),
        destination.as_os_str(),
    ])
}

fn run_element_connectivity_edit(
    source: &Path,
    destination: &Path,
    element_id: &str,
    node_ids: [&str; 2],
) -> Output {
    run_workbench(&[
        text("model-edit-element-connectivity"),
        source.as_os_str(),
        text("--element"),
        text(element_id),
        text("--nodes"),
        text(node_ids[0]),
        text(node_ids[1]),
        text("--output-dir"),
        destination.as_os_str(),
    ])
}

#[allow(clippy::too_many_arguments)]
fn run_frame3d_member_add(
    source: &Path,
    destination: &Path,
    node_id: &str,
    coordinates: [&str; 3],
    element_id: &str,
    from_node_id: &str,
    material_id: &str,
    section_id: &str,
) -> Output {
    run_workbench(&[
        text("model-add-frame3d-member"),
        source.as_os_str(),
        text("--node"),
        text(node_id),
        text("--coordinates"),
        text(coordinates[0]),
        text(coordinates[1]),
        text(coordinates[2]),
        text("--element"),
        text(element_id),
        text("--from-node"),
        text(from_node_id),
        text("--material"),
        text(material_id),
        text("--section"),
        text(section_id),
        text("--output-dir"),
        destination.as_os_str(),
    ])
}

fn run_nodal_load_add(
    source: &Path,
    destination: &Path,
    load_pattern_id: &str,
    nodal_load_id: &str,
    node_id: &str,
    components: [&str; 6],
) -> Output {
    run_workbench(&[
        text("model-add-nodal-load"),
        source.as_os_str(),
        text("--load-pattern"),
        text(load_pattern_id),
        text("--load"),
        text(nodal_load_id),
        text("--node"),
        text(node_id),
        text("--components"),
        text(components[0]),
        text(components[1]),
        text(components[2]),
        text(components[3]),
        text(components[4]),
        text(components[5]),
        text("--output-dir"),
        destination.as_os_str(),
    ])
}

fn run_fixed_constraint_add(
    source: &Path,
    destination: &Path,
    constraint_id: &str,
    node_id: &str,
) -> Output {
    run_workbench(&[
        text("model-add-fixed-constraint"),
        source.as_os_str(),
        text("--constraint"),
        text(constraint_id),
        text("--node"),
        text(node_id),
        text("--output-dir"),
        destination.as_os_str(),
    ])
}

fn run_model_linear_request_create(
    source: &Path,
    destination: &Path,
    case_id: &str,
    load_pattern_id: &str,
) -> Output {
    run_workbench(&[
        text("model-create-linear-analysis-request"),
        source.as_os_str(),
        text("--case"),
        text(case_id),
        text("--load-pattern"),
        text(load_pattern_id),
        text("--max-iterations"),
        text("100"),
        text("--absolute-residual-tolerance"),
        text("1e-11"),
        text("--relative-residual-tolerance"),
        text("1e-13"),
        text("--maximum-increment"),
        text("0"),
        text("--output-dir"),
        destination.as_os_str(),
    ])
}

fn assert_self_hashed_edit_receipt(receipt: &mut Value) {
    let expected_receipt_hash = receipt
        .as_object_mut()
        .and_then(|object| object.remove("receipt_hash"))
        .and_then(|value| value.as_str().map(ToOwned::to_owned))
        .expect("receipt self-hash");
    let unsigned = canonicalize_model_ir_v2(receipt).expect("unsigned canonical receipt");
    assert_eq!(expected_receipt_hash, sha256_identity(unsigned.as_bytes()));
}

fn assert_published_linear_material_edit(destination: &Path) {
    let edited_bytes = std::fs::read(destination.join("model-ir.json")).expect("edited ModelIR");
    let edited = parse_model_ir_v2(&edited_bytes).expect("strict edited ModelIR");
    let material = edited
        .value()
        .get("materials")
        .and_then(Value::as_array)
        .and_then(|materials| {
            materials
                .iter()
                .find(|material| material.get("id").and_then(Value::as_str) == Some("M1"))
        })
        .expect("edited material");
    for (key, expected) in [
        ("elastic_modulus_pa", 210_000_000_000.0_f64),
        ("poisson_ratio", 0.29),
        ("density_kg_m3", 7850.0),
    ] {
        assert_eq!(
            material["parameters"][key]
                .as_f64()
                .expect("finite material parameter")
                .to_bits(),
            expected.to_bits()
        );
    }
    assert!(edited.value()["extensions"]
        .get("structural-native:model-edit-linear-material.v1")
        .is_some());
    let mut receipt: Value = serde_json::from_slice(
        &std::fs::read(destination.join("edit-receipt.json")).expect("material edit receipt"),
    )
    .expect("material edit receipt JSON");
    assert_eq!(receipt["operation"], "linear_elastic_material_parameters");
    assert_eq!(receipt["material_id"], "M1");
    assert_eq!(receipt["law_id"], "linear_elastic_isotropic");
    assert_eq!(receipt["parameter_set_version"], "1");
    assert_eq!(receipt["previous_parameters_si"]["poisson_ratio"], 0.3);
    assert_eq!(receipt["edited_parameters_si"]["poisson_ratio"], 0.29);
    assert_eq!(receipt["cpp_semantic_snapshot_verified"], true);
    assert_eq!(receipt["analysis_ready"], true);
    assert_eq!(receipt["edited_content_hash"], edited.content_hash());
    assert_ne!(
        receipt["source_semantic_hash"],
        receipt["edited_semantic_hash"]
    );
    assert_ne!(
        receipt["source_provenance_hash"],
        receipt["edited_provenance_hash"]
    );
    assert_self_hashed_edit_receipt(&mut receipt);
}

fn assert_published_frame_section_edit(destination: &Path) {
    let edited_bytes = std::fs::read(destination.join("model-ir.json")).expect("edited ModelIR");
    let edited = parse_model_ir_v2(&edited_bytes).expect("strict edited ModelIR");
    let section = edited
        .value()
        .get("sections")
        .and_then(Value::as_array)
        .and_then(|sections| {
            sections
                .iter()
                .find(|section| section.get("id").and_then(Value::as_str) == Some("S1"))
        })
        .expect("edited section");
    for (key, expected) in [
        ("area_m2", 0.025_f64),
        ("iy_m4", 0.000_09),
        ("iz_m4", 0.000_06),
        ("torsional_constant_m4", 0.000_012),
        ("shear_area_y_m2", 0.02),
        ("shear_area_z_m2", 0.02),
    ] {
        assert_eq!(
            section["parameters"][key]
                .as_f64()
                .expect("finite section parameter")
                .to_bits(),
            expected.to_bits()
        );
    }
    assert!(edited.value()["extensions"]
        .get("structural-native:model-edit-frame-section.v1")
        .is_some());
    let mut receipt: Value = serde_json::from_slice(
        &std::fs::read(destination.join("edit-receipt.json")).expect("section edit receipt"),
    )
    .expect("section edit receipt JSON");
    assert_eq!(receipt["operation"], "frame_section_parameters");
    assert_eq!(receipt["section_id"], "S1");
    assert_eq!(receipt["family_id"], "frame_3d");
    assert_eq!(receipt["parameter_set_version"], "1");
    assert_eq!(receipt["previous_parameters_si"]["area_m2"], 0.02);
    assert_eq!(receipt["edited_parameters_si"]["area_m2"], 0.025);
    assert_eq!(receipt["cpp_semantic_snapshot_verified"], true);
    assert_eq!(receipt["analysis_ready"], true);
    assert_eq!(receipt["edited_content_hash"], edited.content_hash());
    assert_ne!(
        receipt["source_semantic_hash"],
        receipt["edited_semantic_hash"]
    );
    assert_ne!(
        receipt["source_provenance_hash"],
        receipt["edited_provenance_hash"]
    );
    assert_self_hashed_edit_receipt(&mut receipt);
}

fn assert_published_frame_element_orientation_edit(destination: &Path) {
    let edited_bytes = std::fs::read(destination.join("model-ir.json")).expect("edited ModelIR");
    let edited = parse_model_ir_v2(&edited_bytes).expect("strict edited ModelIR");
    let element = edited
        .value()
        .get("elements")
        .and_then(Value::as_array)
        .and_then(|elements| {
            elements
                .iter()
                .find(|element| element.get("id").and_then(Value::as_str) == Some("E1"))
        })
        .expect("edited element");
    assert_eq!(
        element["local_axis_rotation_rad"]
            .as_f64()
            .expect("finite frame-element orientation")
            .to_bits(),
        0.25_f64.to_bits()
    );
    assert!(edited.value()["extensions"]
        .get("structural-native:model-edit-frame-element-orientation.v1")
        .is_some());
    let mut receipt: Value = serde_json::from_slice(
        &std::fs::read(destination.join("edit-receipt.json"))
            .expect("frame-element orientation edit receipt"),
    )
    .expect("frame-element orientation edit receipt JSON");
    assert_eq!(receipt["operation"], "frame_element_local_axis_rotation");
    assert_eq!(receipt["element_id"], "E1");
    assert_eq!(receipt["element_type"], "frame_3d");
    assert_eq!(receipt["formulation"], "euler_bernoulli_3d");
    assert_eq!(receipt["previous_local_axis_rotation_rad"], 0.0);
    assert_eq!(receipt["edited_local_axis_rotation_rad"], 0.25);
    assert_eq!(receipt["cpp_semantic_snapshot_verified"], true);
    assert_eq!(receipt["analysis_ready"], true);
    assert_eq!(receipt["edited_content_hash"], edited.content_hash());
    assert_ne!(
        receipt["source_semantic_hash"],
        receipt["edited_semantic_hash"]
    );
    assert_ne!(
        receipt["source_provenance_hash"],
        receipt["edited_provenance_hash"]
    );
    assert_self_hashed_edit_receipt(&mut receipt);
}

fn assert_published_element_connectivity_edit(destination: &Path) {
    let edited_bytes = std::fs::read(destination.join("model-ir.json")).expect("edited ModelIR");
    let edited = parse_model_ir_v2(&edited_bytes).expect("strict edited ModelIR");
    let element = edited
        .value()
        .get("elements")
        .and_then(Value::as_array)
        .and_then(|elements| {
            elements
                .iter()
                .find(|element| element.get("id").and_then(Value::as_str) == Some("E1"))
        })
        .expect("edited element");
    assert_eq!(element["node_ids"], serde_json::json!(["N1", "N3"]));
    assert_eq!(element["type"], "frame_3d");
    assert_eq!(element["formulation"], "euler_bernoulli_3d");
    assert!(edited.value()["extensions"]
        .get("structural-native:model-edit-element-connectivity.v1")
        .is_some());
    let mut receipt: Value = serde_json::from_slice(
        &std::fs::read(destination.join("edit-receipt.json"))
            .expect("element connectivity edit receipt"),
    )
    .expect("element connectivity edit receipt JSON");
    assert_eq!(receipt["operation"], "element_connectivity");
    assert_eq!(receipt["element_id"], "E1");
    assert_eq!(receipt["element_type"], "frame_3d");
    assert_eq!(receipt["formulation"], "euler_bernoulli_3d");
    assert_eq!(
        receipt["previous_node_ids"],
        serde_json::json!(["N1", "N2"])
    );
    assert_eq!(receipt["edited_node_ids"], serde_json::json!(["N1", "N3"]));
    assert_eq!(receipt["cpp_semantic_snapshot_verified"], true);
    assert_eq!(receipt["analysis_ready"], true);
    assert_eq!(receipt["edited_content_hash"], edited.content_hash());
    assert_ne!(
        receipt["source_semantic_hash"],
        receipt["edited_semantic_hash"]
    );
    assert_ne!(
        receipt["source_provenance_hash"],
        receipt["edited_provenance_hash"]
    );
    assert_self_hashed_edit_receipt(&mut receipt);
}

fn assert_published_frame3d_member_add(destination: &Path) {
    let edited_bytes = std::fs::read(destination.join("model-ir.json")).expect("added ModelIR");
    let edited = parse_model_ir_v2(&edited_bytes).expect("strict added-member ModelIR");
    assert_eq!(edited.value()["nodes"].as_array().expect("nodes").len(), 3);
    assert_eq!(
        edited.value()["elements"]
            .as_array()
            .expect("elements")
            .len(),
        2
    );
    assert_eq!(edited.value()["nodes"][2]["id"], "N3");
    assert_eq!(edited.value()["nodes"][2]["index"], 2);
    for (actual, expected) in edited.value()["nodes"][2]["coordinates_m"]
        .as_array()
        .expect("new node coordinates")
        .iter()
        .zip([4.0_f64, 0.0, 0.0])
    {
        assert_eq!(
            actual
                .as_f64()
                .expect("finite new-node coordinate")
                .to_bits(),
            expected.to_bits()
        );
    }
    assert_eq!(edited.value()["nodes"][2]["source_id"], Value::Null);
    let element = &edited.value()["elements"][1];
    assert_eq!(element["id"], "E2");
    assert_eq!(element["index"], 1);
    assert_eq!(element["type"], "frame_3d");
    assert_eq!(element["formulation"], "euler_bernoulli_3d");
    assert_eq!(element["node_ids"], serde_json::json!(["N2", "N3"]));
    assert_eq!(element["material_id"], "M1");
    assert_eq!(element["section_id"], "S1");
    assert_eq!(element["source_id"], Value::Null);
    assert!(edited.value()["extensions"]
        .get("structural-native:model-add-frame3d-member.v1")
        .is_some());

    let mut receipt: Value = serde_json::from_slice(
        &std::fs::read(destination.join("edit-receipt.json")).expect("member-add receipt"),
    )
    .expect("member-add receipt JSON");
    assert_eq!(receipt["operation"], "frame3d_member_add");
    assert_eq!(receipt["node_id"], "N3");
    assert_eq!(receipt["node_index"], 2);
    assert_eq!(receipt["element_id"], "E2");
    assert_eq!(receipt["element_index"], 1);
    assert_eq!(receipt["node_ids"], serde_json::json!(["N2", "N3"]));
    assert_eq!(receipt["material_id"], "M1");
    assert_eq!(receipt["section_id"], "S1");
    assert_eq!(receipt["cpp_semantic_snapshot_verified"], true);
    assert_eq!(receipt["analysis_ready"], true);
    assert_eq!(receipt["edited_content_hash"], edited.content_hash());
    assert_self_hashed_edit_receipt(&mut receipt);
}

fn assert_published_nodal_load_add(destination: &Path) {
    let edited_bytes =
        std::fs::read(destination.join("model-ir.json")).expect("load-added ModelIR");
    let edited = parse_model_ir_v2(&edited_bytes).expect("strict load-added ModelIR");
    let pattern = edited.value()["load_patterns"]
        .as_array()
        .expect("load patterns")
        .iter()
        .find(|pattern| pattern["id"] == "LC_WEAK")
        .expect("LC_WEAK pattern");
    let loads = pattern["nodal_loads"].as_array().expect("nodal loads");
    assert_eq!(loads.len(), 2);
    assert_eq!(loads[1]["id"], "L_WEAK_N3");
    assert_eq!(loads[1]["index"], 1);
    assert_eq!(loads[1]["node_id"], "N3");
    assert_eq!(loads[1]["components_si"]["FY"], -1_000.0);
    assert_eq!(loads[1]["source_id"], Value::Null);
    assert!(edited.value()["extensions"]
        .get("structural-native:model-add-nodal-load.v1")
        .is_some());

    let mut receipt: Value = serde_json::from_slice(
        &std::fs::read(destination.join("edit-receipt.json")).expect("load-add receipt"),
    )
    .expect("load-add receipt JSON");
    assert_eq!(receipt["operation"], "nodal_load_add");
    assert_eq!(receipt["load_pattern_id"], "LC_WEAK");
    assert_eq!(receipt["load_pattern_index"], 1);
    assert_eq!(receipt["analysis_type"], "linear_static");
    assert_eq!(receipt["nodal_load_id"], "L_WEAK_N3");
    assert_eq!(receipt["nodal_load_index"], 1);
    assert_eq!(receipt["node_id"], "N3");
    assert_eq!(receipt["components_si"]["FY"], -1_000.0);
    assert_eq!(receipt["cpp_semantic_snapshot_verified"], true);
    assert_eq!(receipt["analysis_ready"], true);
    assert_eq!(receipt["edited_content_hash"], edited.content_hash());
    assert_self_hashed_edit_receipt(&mut receipt);
}

fn assert_published_fixed_constraint_add(destination: &Path) {
    let edited_bytes =
        std::fs::read(destination.join("model-ir.json")).expect("constraint-added ModelIR");
    let edited = parse_model_ir_v2(&edited_bytes).expect("strict constraint-added ModelIR");
    let constraints = edited.value()["constraints"]
        .as_array()
        .expect("constraints");
    assert_eq!(constraints.len(), 2);
    let constraint = &constraints[1];
    assert_eq!(constraint["id"], "BC_N3");
    assert_eq!(constraint["index"], 1);
    assert_eq!(constraint["type"], "fixed_dofs");
    assert_eq!(constraint["node_id"], "N3");
    assert_eq!(
        constraint["dofs"],
        serde_json::json!(["UX", "UY", "UZ", "RX", "RY", "RZ"])
    );
    assert_eq!(
        constraint["prescribed_values_si"],
        serde_json::json!({"UX": 0, "UY": 0, "UZ": 0, "RX": 0, "RY": 0, "RZ": 0})
    );
    assert_eq!(constraint["source_id"], Value::Null);
    assert!(edited.value()["extensions"]
        .get("structural-native:model-add-fixed-constraint.v1")
        .is_some());

    let mut receipt: Value = serde_json::from_slice(
        &std::fs::read(destination.join("edit-receipt.json")).expect("constraint-add receipt"),
    )
    .expect("constraint-add receipt JSON");
    assert_eq!(receipt["operation"], "fixed_constraint_add");
    assert_eq!(receipt["constraint_id"], "BC_N3");
    assert_eq!(receipt["constraint_index"], 1);
    assert_eq!(receipt["constraint_type"], "fixed_dofs");
    assert_eq!(receipt["node_id"], "N3");
    assert_eq!(receipt["dofs"], constraint["dofs"]);
    assert_eq!(
        receipt["prescribed_values_si"],
        constraint["prescribed_values_si"]
    );
    assert_eq!(receipt["cpp_semantic_snapshot_verified"], true);
    assert_eq!(receipt["analysis_ready"], true);
    assert_eq!(receipt["edited_content_hash"], edited.content_hash());
    assert_self_hashed_edit_receipt(&mut receipt);
}

fn assert_rejected_linear_material_edit(
    source: &Path,
    temporary: &Path,
    name: &str,
    material_id: &str,
    parameters: [&str; 3],
    expected_code: &str,
) {
    let destination = temporary.join(name);
    let rejected = run_linear_material_edit(source, &destination, material_id, parameters);
    assert_eq!(rejected.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&rejected.stdout).contains(expected_code));
    assert!(!destination.exists());
}

fn assert_rejected_frame_section_edit(
    source: &Path,
    temporary: &Path,
    name: &str,
    section_id: &str,
    parameters: [&str; 6],
    expected_code: &str,
) {
    let destination = temporary.join(name);
    let rejected = run_frame_section_edit(source, &destination, section_id, parameters);
    assert_eq!(rejected.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&rejected.stdout).contains(expected_code));
    assert!(!destination.exists());
}

fn assert_rejected_frame_element_orientation_edit(
    source: &Path,
    temporary: &Path,
    name: &str,
    element_id: &str,
    rotation_rad: &str,
    expected_code: &str,
) {
    let destination = temporary.join(name);
    let rejected =
        run_frame_element_orientation_edit(source, &destination, element_id, rotation_rad);
    assert_eq!(rejected.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&rejected.stdout).contains(expected_code));
    assert!(!destination.exists());
}

fn assert_rejected_element_connectivity_edit(
    source: &Path,
    temporary: &Path,
    name: &str,
    element_id: &str,
    node_ids: [&str; 2],
    expected_code: &str,
) {
    let destination = temporary.join(name);
    let rejected = run_element_connectivity_edit(source, &destination, element_id, node_ids);
    assert_eq!(
        rejected.status.code(),
        Some(1),
        "unexpected connectivity edit status for {name}: stdout={} stderr={}",
        String::from_utf8_lossy(&rejected.stdout),
        String::from_utf8_lossy(&rejected.stderr)
    );
    assert!(String::from_utf8_lossy(&rejected.stdout).contains(expected_code));
    assert!(!destination.exists());
}

#[test]
#[allow(clippy::too_many_lines)]
fn general_modelir_topology_view_is_cpp_verified_deterministic_and_fail_closed() {
    const FIXTURES: [&str; 8] = [
        "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json",
        "examples/bounded_planar_frame_alpha.model-ir.v2.json",
        "examples/bounded_planar_settlement.model-ir.v2.json",
        "examples/bounded_frame3d_direct_control.model-ir.v2.json",
        "examples/bounded_frame3d_direct_control_axial_yield.model-ir.v2.json",
        "examples/bounded_frame3d_direct_control_ry_bending.model-ir.v2.json",
        "examples/bounded_frame3d_direct_control_rz_bending.model-ir.v2.json",
        "examples/bounded_frame3d_direct_control_torsion.model-ir.v2.json",
    ];
    let root = repository_root();
    for relative in FIXTURES {
        let model = root.join(relative);
        let first = run_workbench(&[text("model-view"), model.as_os_str()]);
        let second = run_workbench(&[text("model-view"), model.as_os_str()]);
        assert_success(&first);
        assert_success(&second);
        assert_eq!(first.stdout, second.stdout, "model view drift: {relative}");
        let view = String::from_utf8(first.stdout).expect("UTF-8 model topology view");
        let document = parse_model_ir_v2(&std::fs::read(&model).expect("ModelIR fixture"))
            .expect("strict ModelIR fixture");
        assert!(view.starts_with("Structural Native Workbench - Model topology view\n"));
        assert!(view.contains("Schema: structural-native-model-topology-view.v1\n"));
        assert!(view.contains("Projection: isometric\n"));
        assert!(view.contains("C++ semantic snapshot: verified\n"));
        assert!(view.contains("Analysis ready: true\n"));
        assert!(view.contains(document.content_hash()));
        assert!(view.contains(document.semantic_hash()));
        assert!(view.contains(document.provenance_hash()));
        assert!(!view.contains('\u{1b}'));
        let (unsigned, hash_line) = view
            .rsplit_once("View hash: ")
            .expect("model topology view hash line");
        assert_eq!(hash_line.trim_end(), sha256_identity(unsigned.as_bytes()));
    }

    let temporary = TestDirectory::create();
    let source = root.join(FIXTURES[0]);
    let default_english = run_workbench(&[text("model-view"), source.as_os_str()]);
    let explicit_english = run_workbench(&[
        text("model-view"),
        source.as_os_str(),
        text("--locale"),
        text("en-US"),
    ]);
    assert_success(&default_english);
    assert_success(&explicit_english);
    assert_eq!(default_english.stdout, explicit_english.stdout);
    let korean_arguments = [
        text("model-view"),
        source.as_os_str(),
        text("--locale"),
        text("ko-KR"),
    ];
    let korean_first = run_workbench(&korean_arguments);
    let korean_second = run_workbench(&korean_arguments);
    assert_success(&korean_first);
    assert_eq!(korean_first.stdout, korean_second.stdout);
    assert!(!korean_first.stdout.contains(&0x1b));
    let english = String::from_utf8(default_english.stdout).expect("English model topology view");
    let korean = String::from_utf8(korean_first.stdout).expect("Korean model topology view");
    assert!(korean.starts_with("Structural Native Workbench - 모델 위상 뷰\n"));
    assert!(korean.contains("로케일: ko-KR\n"));
    assert!(korean.contains("투영: isometric\n"));
    assert!(korean.contains("C++ 의미 스냅샷: verified\n"));
    let document = parse_model_ir_v2(&std::fs::read(&source).expect("ModelIR fixture"))
        .expect("strict ModelIR fixture");
    for identity in [
        document.content_hash(),
        document.semantic_hash(),
        document.provenance_hash(),
    ] {
        assert!(korean.contains(identity));
    }
    let english_geometry = english
        .lines()
        .filter(|line| line.starts_with('|') || line.starts_with('+') || line.starts_with("  "))
        .collect::<Vec<_>>();
    let korean_geometry = korean
        .lines()
        .filter(|line| line.starts_with('|') || line.starts_with('+') || line.starts_with("  "))
        .collect::<Vec<_>>();
    assert_eq!(korean_geometry, english_geometry);
    let (unsigned, hash_line) = korean
        .rsplit_once("보기 해시: ")
        .expect("Korean model topology view hash line");
    assert_eq!(hash_line.trim_end(), sha256_identity(unsigned.as_bytes()));
    assert_ne!(korean, english);

    let mut three_dimensional: Value =
        serde_json::from_slice(&std::fs::read(&source).expect("source ModelIR fixture"))
            .expect("source ModelIR JSON");
    three_dimensional["nodes"][1]["coordinates_m"] = serde_json::json!([2.0, 1.0, 1.0]);
    let three_dimensional_path = temporary.0.join("three-dimensional.model-ir.json");
    std::fs::write(
        &three_dimensional_path,
        serde_json::to_vec(&three_dimensional).expect("3D ModelIR bytes"),
    )
    .expect("write 3D ModelIR");
    let mut projections = Vec::new();
    for projection in ["isometric", "xy", "xz", "yz"] {
        let output = run_workbench(&[
            text("model-view"),
            three_dimensional_path.as_os_str(),
            text("--projection"),
            text(projection),
        ]);
        assert_success(&output);
        assert!(String::from_utf8_lossy(&output.stdout)
            .contains(&format!("Projection: {projection}\n")));
        projections.push(output.stdout);
    }
    for left in 0..projections.len() {
        for right in (left + 1)..projections.len() {
            assert_ne!(projections[left], projections[right]);
        }
    }

    assert_blocked_model_remains_viewable(&temporary.0, &three_dimensional);

    let mut dangling = three_dimensional;
    dangling["elements"][0]["node_ids"][1] = Value::String("MISSING".to_owned());
    let dangling_path = temporary.0.join("dangling.model-ir.json");
    std::fs::write(
        &dangling_path,
        serde_json::to_vec(&dangling).expect("dangling ModelIR bytes"),
    )
    .expect("write dangling ModelIR");
    let rejected = run_workbench(&[text("model-view"), dangling_path.as_os_str()]);
    assert_eq!(rejected.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&rejected.stdout)
        .contains("workbench_model_view_semantics_invalid"));

    let invalid_projection = run_workbench(&[
        text("model-view"),
        source.as_os_str(),
        text("--projection"),
        text("perspective"),
    ]);
    assert_eq!(invalid_projection.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&invalid_projection.stdout).contains("workbench_usage_error"));
}

#[test]
fn node_coordinate_edit_is_provenance_bound_cpp_revalidated_and_create_new() {
    let temporary = TestDirectory::create();
    let source =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let source_before = std::fs::read(&source).expect("source ModelIR bytes");
    let first = temporary.0.join("edited-first");
    let second = temporary.0.join("edited-second");
    for destination in [&first, &second] {
        let output = run_node_edit(&source, destination, "N2", ["2", "1", "1"]);
        assert_success(&output);
        let receipt_bytes =
            std::fs::read(destination.join("edit-receipt.json")).expect("published edit receipt");
        assert_eq!(output.stdout, [receipt_bytes.as_slice(), b"\n"].concat());
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(artifact)).expect("first edit artifact"),
            std::fs::read(second.join(artifact)).expect("second edit artifact")
        );
    }
    assert_eq!(
        std::fs::read(&source).expect("source after edit"),
        source_before
    );
    assert_published_node_edit(&first);

    let repeated = run_node_edit(&source, &first, "N2", ["2", "1", "1"]);
    assert_eq!(repeated.status.code(), Some(1));
    assert!(
        String::from_utf8_lossy(&repeated.stdout).contains("workbench_stage_destination_exists")
    );

    for (name, node_id, coordinates, expected_code) in [
        (
            "missing",
            "MISSING",
            ["2", "1", "1"],
            "workbench_model_edit_node_missing",
        ),
        (
            "no-op",
            "N2",
            ["2", "0", "0"],
            "workbench_model_edit_no_change",
        ),
        (
            "signed-zero-no-op",
            "N2",
            ["2", "-0", "0"],
            "workbench_model_edit_no_change",
        ),
        (
            "zero-length",
            "N2",
            ["0", "0", "0"],
            "workbench_model_edit_semantics_invalid",
        ),
    ] {
        assert_rejected_node_edit(
            &source,
            &temporary.0,
            name,
            node_id,
            coordinates,
            expected_code,
        );
    }

    let mut invalid_source: Value =
        serde_json::from_slice(&source_before).expect("source ModelIR for invalid-source edit");
    invalid_source["elements"][0]["node_ids"][1] = Value::String("MISSING".to_owned());
    let invalid_source_path = temporary.0.join("invalid-source.model-ir.json");
    std::fs::write(
        &invalid_source_path,
        serde_json::to_vec(&invalid_source).expect("invalid source bytes"),
    )
    .expect("write invalid edit source");
    assert_rejected_node_edit(
        &invalid_source_path,
        &temporary.0,
        "invalid-source-edit",
        "N2",
        ["2", "1", "1"],
        "workbench_model_edit_source_semantics_invalid",
    );
}

#[test]
fn node_coordinate_edit_preserves_analysis_blockers_without_promotion() {
    let temporary = TestDirectory::create();
    let fixture =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let mut blocked: Value = serde_json::from_slice(
        &std::fs::read(fixture).expect("source ModelIR fixture for blocked edit"),
    )
    .expect("source ModelIR JSON for blocked edit");
    blocked["unsupported_features"] = serde_json::json!([{
        "feature_id": "feature.edit-visible-not-runnable",
        "kind": "unsupported_solver_feature",
        "source_entity_id": null,
        "disposition": "blocked",
        "blocking": true,
        "detail": "Editing must not promote unsupported solver authority.",
        "extensions": {}
    }]);
    blocked["roundtrip_map"] = serde_json::json!([{
        "source_entity_id": "source:N2",
        "entity_kind": "node",
        "model_ir_entity_id": "N2",
        "mapping_status": "exact",
        "extensions": {}
    }]);
    let source = temporary.0.join("blocked-source.model-ir.json");
    std::fs::write(
        &source,
        serde_json::to_vec(&blocked).expect("blocked edit source bytes"),
    )
    .expect("write blocked edit source");
    let destination = temporary.0.join("blocked-edit");
    let output = run_node_edit(&source, &destination, "N2", ["2", "1", "0"]);
    assert_success(&output);

    let receipt: Value = serde_json::from_slice(
        &std::fs::read(destination.join("edit-receipt.json")).expect("blocked edit receipt"),
    )
    .expect("blocked edit receipt JSON");
    assert_eq!(receipt["analysis_ready"], false);
    assert_eq!(
        receipt["blocking_feature_ids"],
        serde_json::json!(["feature.edit-visible-not-runnable"])
    );
    let edited: Value = serde_json::from_slice(
        &std::fs::read(destination.join("model-ir.json")).expect("blocked edited model"),
    )
    .expect("blocked edited ModelIR JSON");
    assert_eq!(
        edited["roundtrip_map"][0]["mapping_status"], "approximated",
        "edited round-trip map: {}",
        edited["roundtrip_map"]
    );
    let view = run_workbench(&[
        text("model-view"),
        destination.join("model-ir.json").as_os_str(),
    ]);
    assert_success(&view);
    let view = String::from_utf8(view.stdout).expect("blocked edited model view");
    assert!(view.contains("Analysis ready: false\n"));
    assert!(view.contains("Blocking features: feature.edit-visible-not-runnable\n"));
}

#[test]
#[allow(clippy::too_many_lines)]
fn nodal_load_edit_is_provenance_bound_cpp_revalidated_and_create_new() {
    let temporary = TestDirectory::create();
    let source =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let source_before = std::fs::read(&source).expect("source ModelIR bytes");
    let first = temporary.0.join("load-edit-first");
    let second = temporary.0.join("load-edit-second");
    for destination in [&first, &second] {
        let output = run_nodal_load_edit(
            &source,
            destination,
            "LC_WEAK",
            "L_WEAK_N2",
            ["0", "-20000", "0", "0", "0", "0"],
        );
        assert_success(&output);
        let receipt_bytes =
            std::fs::read(destination.join("edit-receipt.json")).expect("published edit receipt");
        assert_eq!(output.stdout, [receipt_bytes.as_slice(), b"\n"].concat());
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(artifact)).expect("first load edit artifact"),
            std::fs::read(second.join(artifact)).expect("second load edit artifact")
        );
    }
    assert_eq!(
        std::fs::read(&source).expect("source after load edit"),
        source_before
    );
    assert_published_nodal_load_edit(&first);

    let repeated = run_nodal_load_edit(
        &source,
        &first,
        "LC_WEAK",
        "L_WEAK_N2",
        ["0", "-20000", "0", "0", "0", "0"],
    );
    assert_eq!(repeated.status.code(), Some(1));
    assert!(
        String::from_utf8_lossy(&repeated.stdout).contains("workbench_stage_destination_exists")
    );

    for (name, pattern_id, load_id, components, expected_code) in [
        (
            "missing-pattern",
            "MISSING",
            "L_WEAK_N2",
            ["0", "-20000", "0", "0", "0", "0"],
            "workbench_model_edit_load_pattern_missing",
        ),
        (
            "missing-load",
            "LC_WEAK",
            "MISSING",
            ["0", "-20000", "0", "0", "0", "0"],
            "workbench_model_edit_nodal_load_missing",
        ),
        (
            "load-no-op",
            "LC_WEAK",
            "L_WEAK_N2",
            ["0", "-10000", "0", "0", "0", "0"],
            "workbench_model_edit_no_change",
        ),
        (
            "load-signed-zero-no-op",
            "LC_WEAK",
            "L_WEAK_N2",
            ["-0", "-10000", "0", "0", "0", "0"],
            "workbench_model_edit_no_change",
        ),
        (
            "zero-load-pattern",
            "LC_WEAK",
            "L_WEAK_N2",
            ["0", "0", "0", "0", "0", "0"],
            "workbench_model_edit_semantics_invalid",
        ),
    ] {
        assert_rejected_nodal_load_edit(
            &source,
            &temporary.0,
            name,
            pattern_id,
            load_id,
            components,
            expected_code,
        );
    }
}

#[test]
fn nodal_load_edit_preserves_analysis_blockers_without_promotion() {
    let temporary = TestDirectory::create();
    let fixture =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let mut blocked: Value = serde_json::from_slice(
        &std::fs::read(fixture).expect("source ModelIR fixture for blocked load edit"),
    )
    .expect("source ModelIR JSON for blocked load edit");
    blocked["unsupported_features"] = serde_json::json!([{
        "feature_id": "feature.load-edit-visible-not-runnable",
        "kind": "unsupported_solver_feature",
        "source_entity_id": null,
        "disposition": "blocked",
        "blocking": true,
        "detail": "Editing a load must not promote unsupported solver authority.",
        "extensions": {}
    }]);
    blocked["roundtrip_map"] = serde_json::json!([{
        "source_entity_id": "source:LC_WEAK",
        "entity_kind": "load_pattern",
        "model_ir_entity_id": "LC_WEAK",
        "mapping_status": "exact",
        "extensions": {}
    }]);
    let source = temporary.0.join("blocked-load-source.model-ir.json");
    std::fs::write(
        &source,
        serde_json::to_vec(&blocked).expect("blocked load edit source bytes"),
    )
    .expect("write blocked load edit source");
    let destination = temporary.0.join("blocked-load-edit");
    let output = run_nodal_load_edit(
        &source,
        &destination,
        "LC_WEAK",
        "L_WEAK_N2",
        ["0", "-20000", "0", "0", "0", "0"],
    );
    assert_success(&output);

    let receipt: Value = serde_json::from_slice(
        &std::fs::read(destination.join("edit-receipt.json")).expect("blocked load edit receipt"),
    )
    .expect("blocked load edit receipt JSON");
    assert_eq!(receipt["analysis_ready"], false);
    assert_eq!(
        receipt["blocking_feature_ids"],
        serde_json::json!(["feature.load-edit-visible-not-runnable"])
    );
    let edited: Value = serde_json::from_slice(
        &std::fs::read(destination.join("model-ir.json")).expect("blocked load edited model"),
    )
    .expect("blocked load edited ModelIR JSON");
    assert_eq!(
        edited["roundtrip_map"][0]["mapping_status"], "approximated",
        "edited round-trip map: {}",
        edited["roundtrip_map"]
    );
}

#[test]
fn constraint_value_edit_is_provenance_bound_cpp_revalidated_and_create_new() {
    let temporary = TestDirectory::create();
    let source = repository_root().join("examples/bounded_planar_settlement.model-ir.v2.json");
    let source_before = std::fs::read(&source).expect("source settlement ModelIR bytes");
    let first = temporary.0.join("constraint-edit-first");
    let second = temporary.0.join("constraint-edit-second");
    for destination in [&first, &second] {
        let output = run_constraint_value_edit(&source, destination, "BC2", "UY", "-0.0002");
        assert_success(&output);
        let receipt_bytes =
            std::fs::read(destination.join("edit-receipt.json")).expect("published edit receipt");
        assert_eq!(output.stdout, [receipt_bytes.as_slice(), b"\n"].concat());
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(artifact)).expect("first constraint edit artifact"),
            std::fs::read(second.join(artifact)).expect("second constraint edit artifact")
        );
    }
    assert_eq!(
        std::fs::read(&source).expect("source after constraint edit"),
        source_before
    );
    assert_published_constraint_value_edit(&first);

    let repeated = run_constraint_value_edit(&source, &first, "BC2", "UY", "-0.0002");
    assert_eq!(repeated.status.code(), Some(1));
    assert!(
        String::from_utf8_lossy(&repeated.stdout).contains("workbench_stage_destination_exists")
    );

    for (name, constraint_id, dof, value_si, expected_code) in [
        (
            "missing-constraint",
            "MISSING",
            "UY",
            "-0.0002",
            "workbench_model_edit_constraint_missing",
        ),
        (
            "unrestrained-dof",
            "BC2",
            "UX",
            "-0.0002",
            "workbench_model_edit_constraint_dof_not_restrained",
        ),
        (
            "constraint-no-op",
            "BC2",
            "UY",
            "-0.0001",
            "workbench_model_edit_no_change",
        ),
        (
            "constraint-signed-zero-no-op",
            "BC1",
            "UX",
            "-0",
            "workbench_model_edit_no_change",
        ),
    ] {
        assert_rejected_constraint_value_edit(
            &source,
            &temporary.0,
            name,
            constraint_id,
            dof,
            value_si,
            expected_code,
        );
    }

    let mut invalid_source: Value =
        serde_json::from_slice(&source_before).expect("source ModelIR for invalid constraint edit");
    invalid_source["constraints"][1]["node_id"] = Value::String("MISSING".to_owned());
    let invalid_source_path = temporary.0.join("invalid-constraint-source.model-ir.json");
    std::fs::write(
        &invalid_source_path,
        serde_json::to_vec(&invalid_source).expect("invalid constraint source bytes"),
    )
    .expect("write invalid constraint edit source");
    assert_rejected_constraint_value_edit(
        &invalid_source_path,
        &temporary.0,
        "invalid-constraint-source-edit",
        "BC2",
        "UY",
        "-0.0002",
        "workbench_model_edit_source_semantics_invalid",
    );
}

#[test]
fn constraint_value_edit_preserves_source_analysis_blockers_without_promotion() {
    let temporary = TestDirectory::create();
    let fixture =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let mut blocked: Value = serde_json::from_slice(
        &std::fs::read(fixture).expect("source ModelIR fixture for blocked constraint edit"),
    )
    .expect("source ModelIR JSON for blocked constraint edit");
    blocked["unsupported_features"] = serde_json::json!([{
        "feature_id": "feature.constraint-edit-visible-not-runnable",
        "kind": "unsupported_solver_feature",
        "source_entity_id": null,
        "disposition": "blocked",
        "blocking": true,
        "detail": "Editing a constraint must not promote unsupported solver authority.",
        "extensions": {}
    }]);
    blocked["roundtrip_map"] = serde_json::json!([{
        "source_entity_id": "source:BC1",
        "entity_kind": "constraint",
        "model_ir_entity_id": "BC1",
        "mapping_status": "canonicalized",
        "extensions": {}
    }]);
    let source = temporary.0.join("blocked-constraint-source.model-ir.json");
    std::fs::write(
        &source,
        serde_json::to_vec(&blocked).expect("blocked constraint edit source bytes"),
    )
    .expect("write blocked constraint edit source");
    let destination = temporary.0.join("blocked-constraint-edit");
    let output = run_constraint_value_edit(&source, &destination, "BC1", "UX", "0.001");
    assert_success(&output);

    let receipt: Value = serde_json::from_slice(
        &std::fs::read(destination.join("edit-receipt.json"))
            .expect("blocked constraint edit receipt"),
    )
    .expect("blocked constraint edit receipt JSON");
    assert_eq!(receipt["analysis_ready"], false);
    let blockers = receipt["blocking_feature_ids"]
        .as_array()
        .expect("constraint edit blockers");
    assert!(blockers
        .iter()
        .any(|value| { value.as_str() == Some("feature.constraint-edit-visible-not-runnable") }));
    let edited: Value = serde_json::from_slice(
        &std::fs::read(destination.join("model-ir.json")).expect("blocked constraint edited model"),
    )
    .expect("blocked constraint edited ModelIR JSON");
    assert_eq!(edited["roundtrip_map"][0]["mapping_status"], "approximated");
}

#[test]
fn linear_material_edit_is_provenance_bound_cpp_revalidated_and_create_new() {
    let temporary = TestDirectory::create();
    let source =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let source_before = std::fs::read(&source).expect("source ModelIR bytes");
    let first = temporary.0.join("material-edit-first");
    let second = temporary.0.join("material-edit-second");
    let edited_parameters = ["210000000000", "0.29", "7850"];
    for destination in [&first, &second] {
        let output = run_linear_material_edit(&source, destination, "M1", edited_parameters);
        assert_success(&output);
        let receipt_bytes =
            std::fs::read(destination.join("edit-receipt.json")).expect("material edit receipt");
        assert_eq!(output.stdout, [receipt_bytes.as_slice(), b"\n"].concat());
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(artifact)).expect("first material edit artifact"),
            std::fs::read(second.join(artifact)).expect("second material edit artifact")
        );
    }
    assert_eq!(
        std::fs::read(&source).expect("source after edit"),
        source_before
    );
    assert_published_linear_material_edit(&first);

    let repeated = run_linear_material_edit(&source, &first, "M1", edited_parameters);
    assert_eq!(repeated.status.code(), Some(1));
    assert!(
        String::from_utf8_lossy(&repeated.stdout).contains("workbench_stage_destination_exists")
    );
    for (name, material_id, parameters, expected_code) in [
        (
            "material-missing",
            "MISSING",
            edited_parameters,
            "workbench_model_edit_material_missing",
        ),
        (
            "material-no-op",
            "M1",
            ["200000000000", "0.3", "7850"],
            "workbench_model_edit_no_change",
        ),
    ] {
        assert_rejected_linear_material_edit(
            &source,
            &temporary.0,
            name,
            material_id,
            parameters,
            expected_code,
        );
    }

    let mut zero_density_source: Value =
        serde_json::from_slice(&source_before).expect("source ModelIR for signed-zero edit");
    zero_density_source["materials"][0]["parameters"]["density_kg_m3"] = serde_json::json!(0.0);
    let zero_density_path = temporary.0.join("zero-density-source.model-ir.json");
    std::fs::write(
        &zero_density_path,
        serde_json::to_vec(&zero_density_source).expect("zero-density source bytes"),
    )
    .expect("write zero-density source");
    assert_rejected_linear_material_edit(
        &zero_density_path,
        &temporary.0,
        "material-density-signed-zero-no-op",
        "M1",
        ["200000000000", "0.3", "-0"],
        "workbench_model_edit_no_change",
    );

    let other_law = repository_root().join("examples/bounded_planar_frame_alpha.model-ir.v2.json");
    assert_rejected_linear_material_edit(
        &other_law,
        &temporary.0,
        "material-wrong-law",
        "steel",
        edited_parameters,
        "workbench_model_edit_material_law_unsupported",
    );

    let mut invalid_source: Value =
        serde_json::from_slice(&source_before).expect("source ModelIR for invalid material edit");
    invalid_source["elements"][0]["material_id"] = Value::String("MISSING".to_owned());
    let invalid_source_path = temporary.0.join("invalid-material-source.model-ir.json");
    std::fs::write(
        &invalid_source_path,
        serde_json::to_vec(&invalid_source).expect("invalid material source bytes"),
    )
    .expect("write invalid material edit source");
    assert_rejected_linear_material_edit(
        &invalid_source_path,
        &temporary.0,
        "invalid-material-source-edit",
        "M1",
        edited_parameters,
        "workbench_model_edit_source_semantics_invalid",
    );
}

#[test]
fn frame_section_edit_is_provenance_bound_cpp_revalidated_and_create_new() {
    let temporary = TestDirectory::create();
    let source =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let source_before = std::fs::read(&source).expect("source ModelIR bytes");
    let first = temporary.0.join("section-edit-first");
    let second = temporary.0.join("section-edit-second");
    let edited_parameters = ["0.025", "0.00009", "0.00006", "0.000012", "0.02", "0.02"];
    for destination in [&first, &second] {
        let output = run_frame_section_edit(&source, destination, "S1", edited_parameters);
        assert_success(&output);
        let receipt_bytes =
            std::fs::read(destination.join("edit-receipt.json")).expect("section edit receipt");
        assert_eq!(output.stdout, [receipt_bytes.as_slice(), b"\n"].concat());
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(artifact)).expect("first section edit artifact"),
            std::fs::read(second.join(artifact)).expect("second section edit artifact")
        );
    }
    assert_eq!(
        std::fs::read(&source).expect("source after edit"),
        source_before
    );
    assert_published_frame_section_edit(&first);

    let repeated = run_frame_section_edit(&source, &first, "S1", edited_parameters);
    assert_eq!(repeated.status.code(), Some(1));
    assert!(
        String::from_utf8_lossy(&repeated.stdout).contains("workbench_stage_destination_exists")
    );
    for (name, section_id, parameters, expected_code) in [
        (
            "section-missing",
            "MISSING",
            edited_parameters,
            "workbench_model_edit_section_missing",
        ),
        (
            "section-no-op",
            "S1",
            ["0.02", "0.00008", "0.00005", "0.00001", "0.016", "0.016"],
            "workbench_model_edit_no_change",
        ),
    ] {
        assert_rejected_frame_section_edit(
            &source,
            &temporary.0,
            name,
            section_id,
            parameters,
            expected_code,
        );
    }

    let other_family =
        repository_root().join("examples/bounded_planar_frame_alpha.model-ir.v2.json");
    assert_rejected_frame_section_edit(
        &other_family,
        &temporary.0,
        "section-wrong-family",
        "RC1",
        edited_parameters,
        "workbench_model_edit_section_family_unsupported",
    );

    let mut invalid_source: Value =
        serde_json::from_slice(&source_before).expect("source ModelIR for invalid section edit");
    invalid_source["elements"][0]["section_id"] = Value::String("MISSING".to_owned());
    let invalid_source_path = temporary.0.join("invalid-section-source.model-ir.json");
    std::fs::write(
        &invalid_source_path,
        serde_json::to_vec(&invalid_source).expect("invalid section source bytes"),
    )
    .expect("write invalid section edit source");
    assert_rejected_frame_section_edit(
        &invalid_source_path,
        &temporary.0,
        "invalid-section-source-edit",
        "S1",
        edited_parameters,
        "workbench_model_edit_source_semantics_invalid",
    );
}

#[test]
#[allow(clippy::too_many_lines)]
fn frame_element_orientation_edit_is_deterministic_fail_closed_and_preserves_blockers() {
    let temporary = TestDirectory::create();
    let source =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let source_before = std::fs::read(&source).expect("source ModelIR bytes");
    let first = temporary.0.join("element-orientation-edit-first");
    let second = temporary.0.join("element-orientation-edit-second");
    for destination in [&first, &second] {
        let output = run_frame_element_orientation_edit(&source, destination, "E1", "0.25");
        assert_success(&output);
        let receipt_bytes = std::fs::read(destination.join("edit-receipt.json"))
            .expect("frame-element orientation edit receipt");
        assert_eq!(output.stdout, [receipt_bytes.as_slice(), b"\n"].concat());
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(artifact)).expect("first orientation edit artifact"),
            std::fs::read(second.join(artifact)).expect("second orientation edit artifact")
        );
    }
    assert_eq!(
        std::fs::read(&source).expect("source after orientation edit"),
        source_before
    );
    assert_published_frame_element_orientation_edit(&first);

    let repeated = run_frame_element_orientation_edit(&source, &first, "E1", "0.25");
    assert_eq!(repeated.status.code(), Some(1));
    assert!(
        String::from_utf8_lossy(&repeated.stdout).contains("workbench_stage_destination_exists")
    );
    for (name, element_id, rotation, expected_code) in [
        (
            "element-orientation-missing",
            "MISSING",
            "0.25",
            "workbench_model_edit_element_missing",
        ),
        (
            "element-orientation-no-op",
            "E1",
            "0",
            "workbench_model_edit_no_change",
        ),
        (
            "element-orientation-signed-zero-no-op",
            "E1",
            "-0",
            "workbench_model_edit_no_change",
        ),
    ] {
        assert_rejected_frame_element_orientation_edit(
            &source,
            &temporary.0,
            name,
            element_id,
            rotation,
            expected_code,
        );
    }

    let wrong_type = repository_root().join("examples/bounded_planar_frame_alpha.model-ir.v2.json");
    assert_rejected_frame_element_orientation_edit(
        &wrong_type,
        &temporary.0,
        "element-orientation-wrong-type",
        "E1",
        "0.25",
        "workbench_model_edit_element_type_unsupported",
    );

    let mut invalid_source: Value =
        serde_json::from_slice(&source_before).expect("source ModelIR for invalid element edit");
    invalid_source["elements"][0]["node_ids"][1] = Value::String("MISSING".to_owned());
    let invalid_source_path = temporary
        .0
        .join("invalid-element-orientation-source.model-ir.json");
    std::fs::write(
        &invalid_source_path,
        serde_json::to_vec(&invalid_source).expect("invalid element source bytes"),
    )
    .expect("write invalid element orientation source");
    assert_rejected_frame_element_orientation_edit(
        &invalid_source_path,
        &temporary.0,
        "invalid-element-orientation-source-edit",
        "E1",
        "0.25",
        "workbench_model_edit_source_semantics_invalid",
    );

    let mut blocked: Value =
        serde_json::from_slice(&source_before).expect("source ModelIR for blocked element edit");
    blocked["unsupported_features"] = serde_json::json!([{
        "feature_id": "feature.element-orientation-edit-visible-not-runnable",
        "kind": "unsupported_solver_feature",
        "source_entity_id": null,
        "disposition": "blocked",
        "blocking": true,
        "detail": "Element orientation editing must not promote unsupported solver authority.",
        "extensions": {}
    }]);
    blocked["roundtrip_map"] = serde_json::json!([
        {
            "source_entity_id": "source:E1",
            "entity_kind": "element",
            "model_ir_entity_id": "E1",
            "mapping_status": "canonicalized",
            "extensions": {}
        },
        {
            "source_entity_id": "source:S1",
            "entity_kind": "section",
            "model_ir_entity_id": "S1",
            "mapping_status": "exact",
            "extensions": {}
        }
    ]);
    let blocked_source = temporary
        .0
        .join("blocked-element-orientation-source.model-ir.json");
    std::fs::write(
        &blocked_source,
        serde_json::to_vec(&blocked).expect("blocked element edit source bytes"),
    )
    .expect("write blocked element orientation edit source");
    let blocked_destination = temporary.0.join("blocked-element-orientation-edit");
    let blocked_output =
        run_frame_element_orientation_edit(&blocked_source, &blocked_destination, "E1", "0.25");
    assert_success(&blocked_output);
    let blocked_receipt: Value = serde_json::from_slice(
        &std::fs::read(blocked_destination.join("edit-receipt.json"))
            .expect("blocked element orientation receipt"),
    )
    .expect("blocked element orientation receipt JSON");
    assert_eq!(blocked_receipt["analysis_ready"], false);
    assert_eq!(
        blocked_receipt["blocking_feature_ids"],
        serde_json::json!(["feature.element-orientation-edit-visible-not-runnable"])
    );
    let blocked_edited: Value = serde_json::from_slice(
        &std::fs::read(blocked_destination.join("model-ir.json"))
            .expect("blocked element orientation edited model"),
    )
    .expect("blocked element orientation edited JSON");
    assert_eq!(
        blocked_edited["roundtrip_map"][0]["mapping_status"],
        "approximated"
    );
    assert_eq!(
        blocked_edited["roundtrip_map"][1]["mapping_status"],
        "exact"
    );
}

#[test]
#[allow(clippy::too_many_lines)]
fn element_connectivity_edit_is_deterministic_cpp_revalidated_and_preserves_blockers() {
    let temporary = TestDirectory::create();
    let fixture =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let mut source_model: Value = serde_json::from_slice(
        &std::fs::read(&fixture).expect("element connectivity source fixture"),
    )
    .expect("element connectivity source JSON");
    source_model["nodes"]
        .as_array_mut()
        .expect("source nodes")
        .push(serde_json::json!({
            "id": "N3",
            "index": 2,
            "coordinates_m": [2.0, 1.0, 0.0],
            "source_id": "generated:N3",
            "extensions": {}
        }));
    let mut second_element = source_model["elements"][0].clone();
    second_element["id"] = Value::String("E2".to_owned());
    second_element["index"] = serde_json::json!(1);
    second_element["node_ids"] = serde_json::json!(["N2", "N3"]);
    second_element["source_id"] = Value::String("generated:E2".to_owned());
    source_model["elements"]
        .as_array_mut()
        .expect("source elements")
        .push(second_element);
    let source = temporary.0.join("three-node-frame.model-ir.json");
    let source_before = serde_json::to_vec(&source_model).expect("connectivity source bytes");
    std::fs::write(&source, &source_before).expect("write connectivity source");

    let first = temporary.0.join("element-connectivity-edit-first");
    let second = temporary.0.join("element-connectivity-edit-second");
    for destination in [&first, &second] {
        let output = run_element_connectivity_edit(&source, destination, "E1", ["N1", "N3"]);
        assert_success(&output);
        let receipt_bytes = std::fs::read(destination.join("edit-receipt.json"))
            .expect("element connectivity edit receipt");
        assert_eq!(output.stdout, [receipt_bytes.as_slice(), b"\n"].concat());
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(artifact)).expect("first connectivity edit artifact"),
            std::fs::read(second.join(artifact)).expect("second connectivity edit artifact")
        );
    }
    assert_eq!(
        std::fs::read(&source).expect("source after connectivity edit"),
        source_before
    );
    assert_published_element_connectivity_edit(&first);

    let repeated = run_element_connectivity_edit(&source, &first, "E1", ["N1", "N3"]);
    assert_eq!(repeated.status.code(), Some(1));
    assert!(
        String::from_utf8_lossy(&repeated.stdout).contains("workbench_stage_destination_exists")
    );
    for (name, element_id, node_ids, expected_code) in [
        (
            "element-connectivity-missing-element",
            "MISSING",
            ["N1", "N3"],
            "workbench_model_edit_element_missing",
        ),
        (
            "element-connectivity-missing-node",
            "E1",
            ["N1", "MISSING"],
            "workbench_model_edit_connectivity_node_missing",
        ),
        (
            "element-connectivity-no-op",
            "E1",
            ["N1", "N2"],
            "workbench_model_edit_no_change",
        ),
    ] {
        assert_rejected_element_connectivity_edit(
            &source,
            &temporary.0,
            name,
            element_id,
            node_ids,
            expected_code,
        );
    }

    let identical_destination = temporary.0.join("element-connectivity-identical-endpoints");
    let identical =
        run_element_connectivity_edit(&source, &identical_destination, "E1", ["N1", "N1"]);
    assert_eq!(identical.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&identical.stdout).contains("workbench_usage_error"));
    assert!(!identical_destination.exists());

    let reversed_destination = temporary.0.join("element-connectivity-reversed-endpoints");
    let reversed =
        run_element_connectivity_edit(&source, &reversed_destination, "E1", ["N3", "N2"]);
    assert_success(&reversed);
    let reversed_model: Value = serde_json::from_slice(
        &std::fs::read(reversed_destination.join("model-ir.json"))
            .expect("reversed connectivity edited model"),
    )
    .expect("reversed connectivity edited JSON");
    assert_eq!(
        reversed_model["elements"][0]["node_ids"],
        serde_json::json!(["N3", "N2"])
    );

    let mut zero_length = source_model.clone();
    zero_length["nodes"][2]["coordinates_m"] = serde_json::json!([0.0, 0.0, 0.0]);
    let zero_length_source = temporary.0.join("zero-length-target.model-ir.json");
    std::fs::write(
        &zero_length_source,
        serde_json::to_vec(&zero_length).expect("zero-length target source bytes"),
    )
    .expect("write zero-length target source");
    assert_rejected_element_connectivity_edit(
        &zero_length_source,
        &temporary.0,
        "element-connectivity-zero-length",
        "E1",
        ["N1", "N3"],
        "workbench_model_edit_semantics_invalid",
    );

    let mut invalid_source = source_model.clone();
    invalid_source["elements"][1]["node_ids"][1] = Value::String("MISSING".to_owned());
    let invalid_source_path = temporary
        .0
        .join("invalid-connectivity-source.model-ir.json");
    std::fs::write(
        &invalid_source_path,
        serde_json::to_vec(&invalid_source).expect("invalid connectivity source bytes"),
    )
    .expect("write invalid connectivity source");
    assert_rejected_element_connectivity_edit(
        &invalid_source_path,
        &temporary.0,
        "invalid-connectivity-source-edit",
        "E1",
        ["N1", "N3"],
        "workbench_model_edit_source_semantics_invalid",
    );

    let mut blocked = source_model;
    blocked["unsupported_features"] = serde_json::json!([{
        "feature_id": "feature.connectivity-edit-visible-not-runnable",
        "kind": "unsupported_solver_feature",
        "source_entity_id": null,
        "disposition": "blocked",
        "blocking": true,
        "detail": "Connectivity editing must not promote unsupported solver authority.",
        "extensions": {}
    }]);
    blocked["roundtrip_map"] = serde_json::json!([
        {
            "source_entity_id": "source:E1",
            "entity_kind": "element",
            "model_ir_entity_id": "E1",
            "mapping_status": "canonicalized",
            "extensions": {}
        },
        {
            "source_entity_id": "source:N1",
            "entity_kind": "node",
            "model_ir_entity_id": "N1",
            "mapping_status": "exact",
            "extensions": {}
        }
    ]);
    let blocked_source = temporary
        .0
        .join("blocked-connectivity-source.model-ir.json");
    std::fs::write(
        &blocked_source,
        serde_json::to_vec(&blocked).expect("blocked connectivity source bytes"),
    )
    .expect("write blocked connectivity source");
    let blocked_destination = temporary.0.join("blocked-connectivity-edit");
    let blocked_output =
        run_element_connectivity_edit(&blocked_source, &blocked_destination, "E1", ["N1", "N3"]);
    assert_success(&blocked_output);
    let blocked_receipt: Value = serde_json::from_slice(
        &std::fs::read(blocked_destination.join("edit-receipt.json"))
            .expect("blocked connectivity receipt"),
    )
    .expect("blocked connectivity receipt JSON");
    assert_eq!(blocked_receipt["analysis_ready"], false);
    assert_eq!(
        blocked_receipt["blocking_feature_ids"],
        serde_json::json!(["feature.connectivity-edit-visible-not-runnable"])
    );
    let blocked_edited: Value = serde_json::from_slice(
        &std::fs::read(blocked_destination.join("model-ir.json"))
            .expect("blocked connectivity edited model"),
    )
    .expect("blocked connectivity edited JSON");
    assert_eq!(
        blocked_edited["roundtrip_map"][0]["mapping_status"],
        "approximated"
    );
    assert_eq!(
        blocked_edited["roundtrip_map"][1]["mapping_status"],
        "exact"
    );
}

#[test]
#[allow(clippy::too_many_lines)]
fn frame3d_member_add_is_deterministic_cpp_revalidated_and_linear_executable() {
    let temporary = TestDirectory::create();
    let model =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let source_before = std::fs::read(&model).expect("frame3d member-add source");
    let first = temporary.0.join("frame3d-member-add-first");
    let second = temporary.0.join("frame3d-member-add-second");
    for destination in [&first, &second] {
        let output = run_frame3d_member_add(
            &model,
            destination,
            "N3",
            ["4", "0", "0"],
            "E2",
            "N2",
            "M1",
            "S1",
        );
        assert_success(&output);
        let receipt_bytes = std::fs::read(destination.join("edit-receipt.json"))
            .expect("frame3d member-add receipt");
        assert_eq!(output.stdout, [receipt_bytes.as_slice(), b"\n"].concat());
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(artifact)).expect("first member-add artifact"),
            std::fs::read(second.join(artifact)).expect("second member-add artifact")
        );
    }
    assert_eq!(
        std::fs::read(&model).expect("source after member addition"),
        source_before
    );
    assert_published_frame3d_member_add(&first);

    let view = run_workbench(&[text("model-view"), first.join("model-ir.json").as_os_str()]);
    assert_success(&view);
    let view_text = String::from_utf8_lossy(&view.stdout);
    assert!(view_text.contains("nodes=3 elements=2"));
    assert!(view_text.contains("C++ semantic snapshot: verified"));

    let request_directory = temporary.0.join("added-member-linear-request");
    let request_output = run_model_linear_request_create(
        &first.join("model-ir.json"),
        &request_directory,
        "added-frame3d-member-linear-c5",
        "LC_WEAK",
    );
    assert_success(&request_output);
    let added_model = std::fs::read(first.join("model-ir.json")).expect("added-member model");
    let added_request = std::fs::read(request_directory.join("analysis-request.json"))
        .expect("added-member analysis request");
    let outcome = execute_model_ir_linear_analysis(&added_model, &added_request, None, u32::MAX)
        .expect("added-member native linear execution");
    assert!(outcome.is_complete());
    assert!(!outcome.is_terminal_failure());
    assert!(outcome.result_ir_json().is_some());
    assert!(outcome.result_recovery_ir_json().is_some());

    let existing = run_frame3d_member_add(
        &model,
        &first,
        "N3",
        ["4", "0", "0"],
        "E2",
        "N2",
        "M1",
        "S1",
    );
    assert_eq!(existing.status.code(), Some(1));
    assert!(
        String::from_utf8_lossy(&existing.stdout).contains("workbench_stage_destination_exists")
    );

    for (name, node_id, coordinates, element_id, from_node, material, section, code) in [
        (
            "member-add-duplicate-node",
            "N2",
            ["4", "0", "0"],
            "E2",
            "N1",
            "M1",
            "S1",
            "workbench_model_add_frame3d_member_node_exists",
        ),
        (
            "member-add-duplicate-coordinate",
            "N3",
            ["2", "0", "0"],
            "E2",
            "N2",
            "M1",
            "S1",
            "workbench_model_add_frame3d_member_coordinate_exists",
        ),
        (
            "member-add-duplicate-element",
            "N3",
            ["4", "0", "0"],
            "E1",
            "N2",
            "M1",
            "S1",
            "workbench_model_add_frame3d_member_element_exists",
        ),
        (
            "member-add-missing-from-node",
            "N3",
            ["4", "0", "0"],
            "E2",
            "MISSING",
            "M1",
            "S1",
            "workbench_model_add_frame3d_member_from_node_missing",
        ),
        (
            "member-add-missing-material",
            "N3",
            ["4", "0", "0"],
            "E2",
            "N2",
            "MISSING",
            "S1",
            "workbench_model_add_frame3d_member_material_missing",
        ),
        (
            "member-add-missing-section",
            "N3",
            ["4", "0", "0"],
            "E2",
            "N2",
            "M1",
            "MISSING",
            "workbench_model_add_frame3d_member_section_missing",
        ),
    ] {
        let destination = temporary.0.join(name);
        let rejected = run_frame3d_member_add(
            &model,
            &destination,
            node_id,
            coordinates,
            element_id,
            from_node,
            material,
            section,
        );
        assert_eq!(rejected.status.code(), Some(1));
        assert!(String::from_utf8_lossy(&rejected.stdout).contains(code));
        assert!(!destination.exists());
    }

    let mut blocked: Value = serde_json::from_slice(&source_before).expect("source ModelIR JSON");
    blocked["unsupported_features"] = serde_json::json!([{
        "feature_id": "feature.frame3d-member-add-visible-not-runnable",
        "kind": "unsupported_solver_feature",
        "source_entity_id": null,
        "disposition": "blocked",
        "blocking": true,
        "detail": "Topology authoring must not promote unsupported solver authority.",
        "extensions": {}
    }]);
    let blocked_source = temporary.0.join("blocked-member-add-source.json");
    std::fs::write(
        &blocked_source,
        serde_json::to_vec(&blocked).expect("blocked member-add source bytes"),
    )
    .expect("write blocked member-add source");
    let blocked_destination = temporary.0.join("blocked-member-add");
    let blocked_output = run_frame3d_member_add(
        &blocked_source,
        &blocked_destination,
        "N3",
        ["4", "0", "0"],
        "E2",
        "N2",
        "M1",
        "S1",
    );
    assert_success(&blocked_output);
    let blocked_receipt: Value = serde_json::from_slice(
        &std::fs::read(blocked_destination.join("edit-receipt.json"))
            .expect("blocked member-add receipt"),
    )
    .expect("blocked member-add receipt JSON");
    assert_eq!(blocked_receipt["analysis_ready"], false);
    assert_eq!(
        blocked_receipt["blocking_feature_ids"],
        serde_json::json!(["feature.frame3d-member-add-visible-not-runnable"])
    );
    let blocked_request_destination = temporary.0.join("blocked-member-add-request");
    let blocked_request = run_model_linear_request_create(
        &blocked_destination.join("model-ir.json"),
        &blocked_request_destination,
        "blocked-member",
        "LC_WEAK",
    );
    assert_eq!(blocked_request.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&blocked_request.stdout)
        .contains("workbench_model_linear_request_source_not_ready"));
    assert!(!blocked_request_destination.exists());
}

#[test]
#[allow(clippy::too_many_lines)]
fn nodal_load_add_is_deterministic_cpp_revalidated_and_changes_linear_execution() {
    let temporary = TestDirectory::create();
    let source =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let member_directory = temporary.0.join("load-add-member-source");
    let member_output = run_frame3d_member_add(
        &source,
        &member_directory,
        "N3",
        ["4", "0", "0"],
        "E2",
        "N2",
        "M1",
        "S1",
    );
    assert_success(&member_output);
    let member_source = member_directory.join("model-ir.json");
    let member_source_before = std::fs::read(&member_source).expect("member source bytes");

    let first = temporary.0.join("nodal-load-add-first");
    let second = temporary.0.join("nodal-load-add-second");
    for destination in [&first, &second] {
        let output = run_nodal_load_add(
            &member_source,
            destination,
            "LC_WEAK",
            "L_WEAK_N3",
            "N3",
            ["0", "-1000", "0", "0", "0", "0"],
        );
        assert_success(&output);
        let receipt_bytes =
            std::fs::read(destination.join("edit-receipt.json")).expect("nodal-load add receipt");
        assert_eq!(output.stdout, [receipt_bytes.as_slice(), b"\n"].concat());
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(artifact)).expect("first load-add artifact"),
            std::fs::read(second.join(artifact)).expect("second load-add artifact")
        );
    }
    assert_eq!(
        std::fs::read(&member_source).expect("member source after load addition"),
        member_source_before
    );
    assert_published_nodal_load_add(&first);

    let baseline_request_directory = temporary.0.join("load-add-baseline-request");
    let loaded_request_directory = temporary.0.join("load-add-loaded-request");
    assert_success(&run_model_linear_request_create(
        &member_source,
        &baseline_request_directory,
        "added-nodal-load-linear-c5",
        "LC_WEAK",
    ));
    assert_success(&run_model_linear_request_create(
        &first.join("model-ir.json"),
        &loaded_request_directory,
        "added-nodal-load-linear-c5",
        "LC_WEAK",
    ));
    let baseline = execute_model_ir_linear_analysis(
        &member_source_before,
        &std::fs::read(baseline_request_directory.join("analysis-request.json"))
            .expect("baseline request"),
        None,
        u32::MAX,
    )
    .expect("baseline member-model execution");
    let loaded_model = std::fs::read(first.join("model-ir.json")).expect("load-added model");
    let loaded = execute_model_ir_linear_analysis(
        &loaded_model,
        &std::fs::read(loaded_request_directory.join("analysis-request.json"))
            .expect("load-added request"),
        None,
        u32::MAX,
    )
    .expect("load-added native linear execution");
    assert!(baseline.is_complete());
    assert!(loaded.is_complete());
    let baseline_recovery: Value = serde_json::from_str(
        baseline
            .result_recovery_ir_json()
            .expect("baseline result recovery"),
    )
    .expect("baseline recovery JSON");
    let loaded_recovery: Value = serde_json::from_str(
        loaded
            .result_recovery_ir_json()
            .expect("load-added result recovery"),
    )
    .expect("load-added recovery JSON");
    let n3_uy_position = loaded_recovery["active_dof_indices"]
        .as_array()
        .expect("active DOF indices")
        .iter()
        .position(|index| index.as_u64() == Some(13))
        .expect("N3 UY active DOF");
    assert_eq!(
        baseline_recovery["active_external_load"][n3_uy_position],
        0.0
    );
    assert_eq!(
        loaded_recovery["active_external_load"][n3_uy_position],
        -1_000.0
    );
    assert_ne!(
        baseline_recovery["global_displacement"],
        loaded_recovery["global_displacement"]
    );
    assert_eq!(loaded_recovery["fallback_count"], 0);

    let existing = run_nodal_load_add(
        &member_source,
        &first,
        "LC_WEAK",
        "L_WEAK_N3",
        "N3",
        ["0", "-1000", "0", "0", "0", "0"],
    );
    assert_eq!(existing.status.code(), Some(1));
    assert!(
        String::from_utf8_lossy(&existing.stdout).contains("workbench_stage_destination_exists")
    );

    for (name, pattern, load, node, components, code) in [
        (
            "load-add-duplicate-id",
            "LC_WEAK",
            "L_AXIAL_N2",
            "N3",
            ["0", "-1000", "0", "0", "0", "0"],
            "workbench_model_add_nodal_load_identity_exists",
        ),
        (
            "load-add-missing-pattern",
            "MISSING",
            "L_WEAK_N3",
            "N3",
            ["0", "-1000", "0", "0", "0", "0"],
            "workbench_model_add_nodal_load_pattern_missing",
        ),
        (
            "load-add-missing-node",
            "LC_WEAK",
            "L_WEAK_N3",
            "MISSING",
            ["0", "-1000", "0", "0", "0", "0"],
            "workbench_model_add_nodal_load_node_missing",
        ),
        (
            "load-add-zero",
            "LC_WEAK",
            "L_WEAK_N3",
            "N3",
            ["0", "0", "0", "0", "0", "0"],
            "workbench_usage_error",
        ),
    ] {
        let destination = temporary.0.join(name);
        let rejected = run_nodal_load_add(
            &member_source,
            &destination,
            pattern,
            load,
            node,
            components,
        );
        let expected_status = if code == "workbench_usage_error" {
            2
        } else {
            1
        };
        assert_eq!(rejected.status.code(), Some(expected_status));
        assert!(String::from_utf8_lossy(&rejected.stdout).contains(code));
        assert!(!destination.exists());
    }

    let mut blocked: Value =
        serde_json::from_slice(&member_source_before).expect("member source JSON");
    blocked["unsupported_features"] = serde_json::json!([{
        "feature_id": "feature.nodal-load-add-visible-not-runnable",
        "kind": "unsupported_solver_feature",
        "source_entity_id": null,
        "disposition": "blocked",
        "blocking": true,
        "detail": "Load authoring must not promote unsupported solver authority.",
        "extensions": {}
    }]);
    blocked["roundtrip_map"] = serde_json::json!([
        {
            "source_entity_id": "source:LC_WEAK",
            "entity_kind": "load_pattern",
            "model_ir_entity_id": "LC_WEAK",
            "mapping_status": "exact",
            "extensions": {}
        },
        {
            "source_entity_id": "source:N3",
            "entity_kind": "node",
            "model_ir_entity_id": "N3",
            "mapping_status": "exact",
            "extensions": {}
        }
    ]);
    let blocked_source = temporary.0.join("blocked-load-add-source.json");
    std::fs::write(
        &blocked_source,
        serde_json::to_vec(&blocked).expect("blocked load-add source bytes"),
    )
    .expect("write blocked load-add source");
    let blocked_destination = temporary.0.join("blocked-load-add");
    assert_success(&run_nodal_load_add(
        &blocked_source,
        &blocked_destination,
        "LC_WEAK",
        "L_WEAK_N3",
        "N3",
        ["0", "-1000", "0", "0", "0", "0"],
    ));
    let blocked_receipt: Value = serde_json::from_slice(
        &std::fs::read(blocked_destination.join("edit-receipt.json"))
            .expect("blocked load-add receipt"),
    )
    .expect("blocked load-add receipt JSON");
    assert_eq!(blocked_receipt["analysis_ready"], false);
    assert_eq!(
        blocked_receipt["blocking_feature_ids"],
        serde_json::json!(["feature.nodal-load-add-visible-not-runnable"])
    );
    let blocked_edited: Value = serde_json::from_slice(
        &std::fs::read(blocked_destination.join("model-ir.json"))
            .expect("blocked load-added model"),
    )
    .expect("blocked load-added JSON");
    assert_eq!(
        blocked_edited["roundtrip_map"][0]["mapping_status"],
        "approximated"
    );
    assert_eq!(
        blocked_edited["roundtrip_map"][1]["mapping_status"],
        "exact"
    );
}

#[test]
#[allow(clippy::too_many_lines)]
fn fixed_constraint_add_is_deterministic_cpp_revalidated_and_changes_linear_execution() {
    let temporary = TestDirectory::create();
    let source =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let member_directory = temporary.0.join("constraint-add-member-source");
    assert_success(&run_frame3d_member_add(
        &source,
        &member_directory,
        "N3",
        ["4", "0", "0"],
        "E2",
        "N2",
        "M1",
        "S1",
    ));
    let load_directory = temporary.0.join("constraint-add-load-source");
    assert_success(&run_nodal_load_add(
        &member_directory.join("model-ir.json"),
        &load_directory,
        "LC_WEAK",
        "L_WEAK_N3",
        "N3",
        ["0", "-1000", "0", "0", "0", "0"],
    ));
    let loaded_source = load_directory.join("model-ir.json");
    let loaded_source_before = std::fs::read(&loaded_source).expect("loaded source bytes");

    let first = temporary.0.join("fixed-constraint-add-first");
    let second = temporary.0.join("fixed-constraint-add-second");
    for destination in [&first, &second] {
        let output = run_fixed_constraint_add(&loaded_source, destination, "BC_N3", "N3");
        assert_success(&output);
        let receipt_bytes = std::fs::read(destination.join("edit-receipt.json"))
            .expect("fixed-constraint add receipt");
        assert_eq!(output.stdout, [receipt_bytes.as_slice(), b"\n"].concat());
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(artifact)).expect("first constraint-add artifact"),
            std::fs::read(second.join(artifact)).expect("second constraint-add artifact")
        );
    }
    assert_eq!(
        std::fs::read(&loaded_source).expect("source after fixed-constraint addition"),
        loaded_source_before
    );
    assert_published_fixed_constraint_add(&first);

    let view = run_workbench(&[text("model-view"), first.join("model-ir.json").as_os_str()]);
    assert_success(&view);
    assert!(String::from_utf8_lossy(&view.stdout).contains("constraints=2"));

    let baseline_request_directory = temporary.0.join("constraint-add-baseline-request");
    let supported_request_directory = temporary.0.join("constraint-add-supported-request");
    assert_success(&run_model_linear_request_create(
        &loaded_source,
        &baseline_request_directory,
        "added-fixed-constraint-linear-c5",
        "LC_WEAK",
    ));
    assert_success(&run_model_linear_request_create(
        &first.join("model-ir.json"),
        &supported_request_directory,
        "added-fixed-constraint-linear-c5",
        "LC_WEAK",
    ));
    let baseline = execute_model_ir_linear_analysis(
        &loaded_source_before,
        &std::fs::read(baseline_request_directory.join("analysis-request.json"))
            .expect("baseline request"),
        None,
        u32::MAX,
    )
    .expect("baseline loaded-model execution");
    let supported_model =
        std::fs::read(first.join("model-ir.json")).expect("fixed-constraint-added model");
    let supported = execute_model_ir_linear_analysis(
        &supported_model,
        &std::fs::read(supported_request_directory.join("analysis-request.json"))
            .expect("fixed-constraint request"),
        None,
        u32::MAX,
    )
    .expect("fixed-constraint native linear execution");
    assert!(baseline.is_complete());
    assert!(supported.is_complete());
    let baseline_recovery: Value = serde_json::from_str(
        baseline
            .result_recovery_ir_json()
            .expect("baseline result recovery"),
    )
    .expect("baseline recovery JSON");
    let supported_recovery: Value = serde_json::from_str(
        supported
            .result_recovery_ir_json()
            .expect("fixed-constraint result recovery"),
    )
    .expect("fixed-constraint recovery JSON");
    assert_eq!(
        supported_recovery["active_dof_indices"],
        serde_json::json!([6, 7, 8, 9, 10, 11])
    );
    assert_eq!(
        baseline_recovery["active_dof_indices"]
            .as_array()
            .expect("baseline active DOFs")
            .len(),
        12
    );
    assert!(supported_recovery["global_displacement"]
        .as_array()
        .expect("supported global displacement")[12..18]
        .iter()
        .all(|value| value.as_f64() == Some(0.0)));
    assert_ne!(
        baseline_recovery["global_displacement"],
        supported_recovery["global_displacement"]
    );
    assert_eq!(supported_recovery["fallback_count"], 0);

    let existing = run_fixed_constraint_add(&loaded_source, &first, "BC_N3", "N3");
    assert_eq!(existing.status.code(), Some(1));
    assert!(
        String::from_utf8_lossy(&existing.stdout).contains("workbench_stage_destination_exists")
    );

    for (name, constraint_id, node_id, code) in [
        (
            "constraint-add-duplicate-id",
            "BC1",
            "N3",
            "workbench_model_add_fixed_constraint_identity_exists",
        ),
        (
            "constraint-add-missing-node",
            "BC_MISSING",
            "MISSING",
            "workbench_model_add_fixed_constraint_node_missing",
        ),
        (
            "constraint-add-overlapping-node",
            "BC_N1_AGAIN",
            "N1",
            "workbench_model_add_fixed_constraint_node_already_constrained",
        ),
    ] {
        let destination = temporary.0.join(name);
        let rejected =
            run_fixed_constraint_add(&loaded_source, &destination, constraint_id, node_id);
        assert_eq!(rejected.status.code(), Some(1));
        assert!(String::from_utf8_lossy(&rejected.stdout).contains(code));
        assert!(!destination.exists());
    }

    let mut blocked: Value =
        serde_json::from_slice(&loaded_source_before).expect("constraint source JSON");
    blocked["unsupported_features"] = serde_json::json!([{
        "feature_id": "feature.fixed-constraint-add-visible-not-runnable",
        "kind": "unsupported_solver_feature",
        "source_entity_id": null,
        "disposition": "blocked",
        "blocking": true,
        "detail": "Constraint authoring must not promote unsupported solver authority.",
        "extensions": {}
    }]);
    blocked["roundtrip_map"] = serde_json::json!([
        {
            "source_entity_id": "source:BC1",
            "entity_kind": "constraint",
            "model_ir_entity_id": "BC1",
            "mapping_status": "exact",
            "extensions": {}
        },
        {
            "source_entity_id": "source:N3",
            "entity_kind": "node",
            "model_ir_entity_id": "N3",
            "mapping_status": "exact",
            "extensions": {}
        }
    ]);
    let blocked_source = temporary.0.join("blocked-constraint-add-source.json");
    std::fs::write(
        &blocked_source,
        serde_json::to_vec(&blocked).expect("blocked constraint-add source bytes"),
    )
    .expect("write blocked constraint-add source");
    let blocked_destination = temporary.0.join("blocked-constraint-add");
    assert_success(&run_fixed_constraint_add(
        &blocked_source,
        &blocked_destination,
        "BC_N3",
        "N3",
    ));
    let blocked_receipt: Value = serde_json::from_slice(
        &std::fs::read(blocked_destination.join("edit-receipt.json"))
            .expect("blocked constraint-add receipt"),
    )
    .expect("blocked constraint-add receipt JSON");
    assert_eq!(blocked_receipt["analysis_ready"], false);
    assert_eq!(
        blocked_receipt["blocking_feature_ids"],
        serde_json::json!(["feature.fixed-constraint-add-visible-not-runnable"])
    );
    let blocked_edited: Value = serde_json::from_slice(
        &std::fs::read(blocked_destination.join("model-ir.json"))
            .expect("blocked constraint-added model"),
    )
    .expect("blocked constraint-added JSON");
    assert_eq!(blocked_edited["roundtrip_map"], blocked["roundtrip_map"]);
}

#[test]
#[allow(clippy::too_many_lines)]
fn model_linear_request_creation_is_deterministic_cpp_preflighted_and_product_executable() {
    let temporary = TestDirectory::create();
    let root = repository_root();
    let model = root.join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let fixture_request =
        root.join("native/tests/fixtures/model_ir_linear/frame_cantilever_weak_request.json");
    let external =
        root.join("native/tests/fixtures/model_ir_linear/frame_cantilever_external_v1.json");
    let source_artifact = root.join(
        "native/tests/fixtures/model_ir_linear/frame_cantilever_language_neutral_oracle_v1.txt",
    );
    let source_before = std::fs::read(&model).expect("linear request source ModelIR");
    let first = temporary.0.join("linear-request-first");
    let second = temporary.0.join("linear-request-second");
    for destination in [&first, &second] {
        let output = run_model_linear_request_create(
            &model,
            destination,
            "model-frame-linear-c5",
            "LC_WEAK",
        );
        assert_success(&output);
        let receipt_bytes = std::fs::read(destination.join("request-receipt.json"))
            .expect("linear request creation receipt");
        assert_eq!(output.stdout, [receipt_bytes.as_slice(), b"\n"].concat());
    }
    for artifact in ["analysis-request.json", "request-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(artifact)).expect("first request artifact"),
            std::fs::read(second.join(artifact)).expect("second request artifact")
        );
    }
    assert_eq!(
        std::fs::read(&model).expect("source after request creation"),
        source_before
    );

    let generated = parse_model_ir_linear_analysis_request_v1(
        &std::fs::read(first.join("analysis-request.json")).expect("generated request"),
    )
    .expect("strict generated request");
    let fixture = parse_model_ir_linear_analysis_request_v1(
        &std::fs::read(&fixture_request).expect("fixture request"),
    )
    .expect("strict fixture request");
    assert_eq!(generated.canonical_json(), fixture.canonical_json());
    assert_eq!(generated.request_hash(), fixture.request_hash());

    let mut receipt: Value = serde_json::from_slice(
        &std::fs::read(first.join("request-receipt.json")).expect("request receipt"),
    )
    .expect("request receipt JSON");
    assert_eq!(
        receipt["schema_version"],
        "structural-native-model-linear-request-create-receipt.v1"
    );
    assert_eq!(
        receipt["operation"],
        "create_model_ir_linear_analysis_request"
    );
    assert_eq!(receipt["backend"], "cpu");
    assert_eq!(receipt["load_pattern_id"], "LC_WEAK");
    assert_eq!(receipt["analysis_request_hash"], generated.request_hash());
    assert_eq!(receipt["cpp_semantic_snapshot_verified"], true);
    assert_eq!(receipt["cpp_linear_assembly_preflight_verified"], true);
    assert_eq!(receipt["execution_started"], false);
    for field in ["assembly_hash", "generated_sparse_request_hash"] {
        assert!(receipt[field]
            .as_str()
            .is_some_and(|value| value.starts_with("sha256:")));
    }
    assert_self_hashed_edit_receipt(&mut receipt);

    let existing =
        run_model_linear_request_create(&model, &first, "model-frame-linear-c5", "LC_WEAK");
    assert_eq!(existing.status.code(), Some(1));
    assert!(
        String::from_utf8_lossy(&existing.stdout).contains("workbench_stage_destination_exists")
    );

    let missing_destination = temporary.0.join("linear-request-missing-load-pattern");
    let missing = run_model_linear_request_create(
        &model,
        &missing_destination,
        "model-frame-linear-c5",
        "MISSING",
    );
    assert_eq!(missing.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&missing.stdout)
        .contains("workbench_model_linear_request_load_pattern_missing"));
    assert!(!missing_destination.exists());

    let planar = root.join("examples/bounded_planar_frame_alpha.model-ir.v2.json");
    let unsupported_destination = temporary.0.join("linear-request-nonlinear-pattern");
    let unsupported =
        run_model_linear_request_create(&planar, &unsupported_destination, "case-1", "LP1");
    assert_eq!(unsupported.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&unsupported.stdout)
        .contains("workbench_model_linear_request_load_pattern_unsupported"));
    assert!(!unsupported_destination.exists());

    let mut blocked: Value = serde_json::from_slice(&source_before).expect("source ModelIR JSON");
    blocked["unsupported_features"] = serde_json::json!([{
        "feature_id": "feature.linear-request-blocked",
        "kind": "unsupported_solver_feature",
        "source_entity_id": null,
        "disposition": "blocked",
        "blocking": true,
        "detail": "Blocked models cannot receive an executable request receipt.",
        "extensions": {}
    }]);
    let blocked_source = temporary.0.join("blocked-linear-request-source.json");
    std::fs::write(
        &blocked_source,
        serde_json::to_vec(&blocked).expect("blocked source bytes"),
    )
    .expect("write blocked request source");
    let blocked_destination = temporary.0.join("blocked-linear-request");
    let blocked_output = run_model_linear_request_create(
        &blocked_source,
        &blocked_destination,
        "model-frame-linear-c5",
        "LC_WEAK",
    );
    assert_eq!(blocked_output.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&blocked_output.stdout)
        .contains("workbench_model_linear_request_source_not_ready"));
    assert!(!blocked_destination.exists());

    let workspace = temporary.0.join("generated-request-workflow");
    let generated_request_path = first.join("analysis-request.json");
    let workflow = run_workbench(&[
        text("workflow-model-linear"),
        model.as_os_str(),
        generated_request_path.as_os_str(),
        text("--external-result"),
        external.as_os_str(),
        text("--source-artifact"),
        source_artifact.as_os_str(),
        text("--workspace"),
        workspace.as_os_str(),
        text("--step-budget"),
        text("1"),
    ]);
    assert_success(&workflow);
    let session: Value = serde_json::from_slice(
        &std::fs::read(workspace.join("workbench-session.json"))
            .expect("generated-request Workbench session"),
    )
    .expect("generated-request session JSON");
    assert_eq!(session["stage"], "reported");
    assert_eq!(session["analysis_profile"], "model_ir_linear_cpu_v1");
    assert_eq!(session["analysis_request_hash"], generated.request_hash());
}

#[test]
fn material_and_section_edits_preserve_blockers_and_degrade_only_matching_roundtrip_rows() {
    let temporary = TestDirectory::create();
    let fixture =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let mut blocked: Value = serde_json::from_slice(
        &std::fs::read(fixture).expect("source ModelIR fixture for blocked parameter edits"),
    )
    .expect("source ModelIR JSON for blocked parameter edits");
    blocked["unsupported_features"] = serde_json::json!([{
        "feature_id": "feature.parameter-edit-visible-not-runnable",
        "kind": "unsupported_solver_feature",
        "source_entity_id": null,
        "disposition": "blocked",
        "blocking": true,
        "detail": "Parameter editing must not promote unsupported solver authority.",
        "extensions": {}
    }]);
    blocked["roundtrip_map"] = serde_json::json!([
        {
            "source_entity_id": "source:M1",
            "entity_kind": "material",
            "model_ir_entity_id": "M1",
            "mapping_status": "exact",
            "extensions": {}
        },
        {
            "source_entity_id": "source:S1",
            "entity_kind": "section",
            "model_ir_entity_id": "S1",
            "mapping_status": "canonicalized",
            "extensions": {}
        }
    ]);
    let source = temporary.0.join("blocked-parameter-source.model-ir.json");
    std::fs::write(
        &source,
        serde_json::to_vec(&blocked).expect("blocked parameter edit source bytes"),
    )
    .expect("write blocked parameter edit source");
    let material_destination = temporary.0.join("blocked-material-edit");
    let material_output = run_linear_material_edit(
        &source,
        &material_destination,
        "M1",
        ["210000000000", "0.29", "7850"],
    );
    assert_success(&material_output);
    let material_edited: Value = serde_json::from_slice(
        &std::fs::read(material_destination.join("model-ir.json"))
            .expect("blocked material edited model"),
    )
    .expect("blocked material edited JSON");
    assert_eq!(
        material_edited["roundtrip_map"][0]["mapping_status"],
        "approximated"
    );
    assert_eq!(
        material_edited["roundtrip_map"][1]["mapping_status"],
        "canonicalized"
    );

    let section_destination = temporary.0.join("blocked-section-edit");
    let section_output = run_frame_section_edit(
        &material_destination.join("model-ir.json"),
        &section_destination,
        "S1",
        ["0.025", "0.00009", "0.00006", "0.000012", "0.02", "0.02"],
    );
    assert_success(&section_output);
    let receipt: Value = serde_json::from_slice(
        &std::fs::read(section_destination.join("edit-receipt.json"))
            .expect("blocked section edit receipt"),
    )
    .expect("blocked section edit receipt JSON");
    assert_eq!(receipt["analysis_ready"], false);
    assert_eq!(
        receipt["blocking_feature_ids"],
        serde_json::json!(["feature.parameter-edit-visible-not-runnable"])
    );
    let section_edited: Value = serde_json::from_slice(
        &std::fs::read(section_destination.join("model-ir.json"))
            .expect("blocked section edited model"),
    )
    .expect("blocked section edited JSON");
    assert_eq!(
        section_edited["roundtrip_map"][0]["mapping_status"],
        "approximated"
    );
    assert_eq!(
        section_edited["roundtrip_map"][1]["mapping_status"],
        "approximated"
    );
}

fn import_arguments<'a>(
    command: &'a str,
    model: &'a Path,
    request: &'a Path,
    external: &'a Path,
    source: &'a Path,
    workspace: &'a Path,
) -> Vec<&'a OsStr> {
    vec![
        text(command),
        model.as_os_str(),
        request.as_os_str(),
        text("--external-result"),
        external.as_os_str(),
        text("--source-artifact"),
        source.as_os_str(),
        text("--workspace"),
        workspace.as_os_str(),
        text("--step-budget"),
        text("1"),
    ]
}

fn mgt_import_arguments<'a>(
    command: &'a str,
    source_mgt: &'a Path,
    request: &'a Path,
    external: &'a Path,
    source: &'a Path,
    workspace: &'a Path,
) -> Vec<&'a OsStr> {
    vec![
        text(command),
        source_mgt.as_os_str(),
        request.as_os_str(),
        text("--model-id"),
        text("workbench-mgt-fixed-guided-v1"),
        text("--external-result"),
        external.as_os_str(),
        text("--source-artifact"),
        source.as_os_str(),
        text("--workspace"),
        workspace.as_os_str(),
        text("--step-budget"),
        text("1"),
    ]
}

fn stage_arguments<'a>(command: &'a str, workspace: &'a Path) -> [&'a OsStr; 3] {
    [text(command), text("--workspace"), workspace.as_os_str()]
}

fn review_arguments(workspace: &Path) -> Vec<&OsStr> {
    vec![
        text("review"),
        text("--workspace"),
        workspace.as_os_str(),
        text("--decision"),
        text("review"),
        text("--reviewer"),
        text("Engineer A"),
        text("--comment"),
        text("Check connection assumptions before acceptance."),
    ]
}

fn collect_files(root: &Path) -> Vec<PathBuf> {
    fn visit(root: &Path, directory: &Path, output: &mut Vec<PathBuf>) {
        let mut entries = std::fs::read_dir(directory)
            .expect("read Workbench directory")
            .map(|entry| entry.expect("read Workbench entry"))
            .collect::<Vec<_>>();
        entries.sort_by_key(std::fs::DirEntry::file_name);
        for entry in entries {
            let path = entry.path();
            let metadata = entry.metadata().expect("Workbench artifact metadata");
            if metadata.is_dir() {
                visit(root, &path, output);
            } else if metadata.is_file() {
                output.push(
                    path.strip_prefix(root)
                        .expect("artifact below Workbench root")
                        .to_path_buf(),
                );
            } else {
                panic!("Workbench output must contain only regular files and directories");
            }
        }
    }
    let mut output = Vec::new();
    visit(root, root, &mut output);
    output
}

fn verify_session(workspace: &Path) -> Value {
    let bytes = std::fs::read(workspace.join("workbench-session.json")).expect("session bytes");
    let mut value: Value = serde_json::from_slice(&bytes).expect("session JSON");
    let session_hash = value["session_hash"]
        .as_str()
        .expect("session hash")
        .to_owned();
    value
        .as_object_mut()
        .expect("session object")
        .remove("session_hash");
    let unsigned = canonicalize_model_ir_v2(&value).expect("canonical unsigned session");
    assert_eq!(session_hash, sha256_identity(unsigned.as_bytes()));
    value
}

fn output_json(output: &Output) -> Value {
    assert_success(output);
    serde_json::from_slice(&output.stdout).expect("Workbench canonical JSON stdout")
}

fn verify_output_self_hash(value: &Value, hash_field: &str) {
    let mut unsigned = value.clone();
    let expected = unsigned
        .as_object_mut()
        .expect("self-hashed output object")
        .remove(hash_field)
        .and_then(|hash| hash.as_str().map(ToOwned::to_owned))
        .expect("self-hashed output field");
    let canonical = canonicalize_model_ir_v2(&unsigned).expect("canonical self-hashed output");
    assert_eq!(expected, sha256_identity(canonical.as_bytes()));
}

#[test]
fn native_catalog_browse_and_exact_case_view_are_deterministic_and_non_promoting() {
    let browse_arguments = [
        text("catalog"),
        text("--truth"),
        text("geometry_only"),
        text("--size"),
        text("large"),
    ];
    let first = run_workbench(&browse_arguments);
    let second = run_workbench(&browse_arguments);
    assert_success(&first);
    assert_eq!(first.stdout, second.stdout);
    let view = output_json(&first);
    assert_eq!(
        view["schema_version"],
        "structural-native-benchmark-catalog-view.v1"
    );
    assert_eq!(view["source_schema_version"], "benchmark-catalog.v2");
    assert_eq!(
        view["source_content_hash"],
        "sha256:235a463ccd9508440b8cba9e7e793396b8635b0a761cfdb645e120a756d60736"
    );
    assert_eq!(view["summary"]["total_case_count"], 26);
    assert_eq!(view["summary"]["matched_case_count"], 4);
    assert_eq!(view["summary"]["accuracy_comparable_count"], 5);
    assert_eq!(view["summary"]["runnable_count"], 0);
    assert!(view["cases"]
        .as_array()
        .expect("filtered cases")
        .iter()
        .all(|case| case["accuracyComparable"] == false
            && case["runCommand"].is_null()
            && case["runBlockedReason"] == "No benchmark runner registered"));
    verify_output_self_hash(&view, "catalog_view_hash");

    let show = run_workbench(&[
        text("catalog-show"),
        text("--case"),
        text("peer_spd_rc_column_rectangular_seed_01"),
    ]);
    let case_view = output_json(&show);
    assert_eq!(
        case_view["schema_version"],
        "structural-native-benchmark-case-view.v1"
    );
    assert_eq!(
        case_view["case"]["id"],
        "peer_spd_rc_column_rectangular_seed_01"
    );
    assert_eq!(case_view["case"]["lifecycle"], "REFERENCE_ATTACHED");
    assert_eq!(case_view["case"]["accuracyComparable"], true);
    assert_eq!(case_view["case"]["runCommand"], Value::Null);
    verify_output_self_hash(&case_view, "case_view_hash");

    let missing = run_workbench(&[
        text("catalog-show"),
        text("--case"),
        text("not-a-registered-case"),
    ]);
    assert_eq!(missing.status.code(), Some(2));
    let failure: Value = serde_json::from_slice(&missing.stdout).expect("failure JSON");
    assert_eq!(failure["code"], "workbench_catalog_case_not_found");
}

#[test]
fn native_evidence_bundle_view_is_deterministic_and_fails_closed_on_hash_drift() {
    let fixture = evidence_fixture();
    let browse_arguments = [
        text("evidence"),
        text("--bundle"),
        fixture.as_os_str(),
        text("--as-of-unix"),
        text("1786579200"),
    ];
    let first = run_workbench(&browse_arguments);
    let second = run_workbench(&browse_arguments);
    assert_success(&first);
    assert_eq!(first.stdout, second.stdout);
    let view = output_json(&first);
    assert_eq!(
        view["schema_version"],
        "structural-native-evidence-bundle-view.v1"
    );
    assert_eq!(view["commit_mismatch"], false);
    assert_eq!(view["bundle_consistent"], true);
    assert_eq!(view["summary"]["artifact_count"], 3);
    assert_eq!(view["summary"]["ready_count"], 1);
    assert_eq!(view["summary"]["blocked_count"], 1);
    assert_eq!(view["summary"]["unavailable_count"], 1);
    assert_eq!(view["summary"]["stale_count"], 1);
    assert_eq!(view["summary"]["product_release_ready"], true);
    assert_eq!(view["artifacts"][0]["facts"]["gate_state"], "ready");
    assert_eq!(view["artifacts"][1]["facts"]["gate_state"], "blocked");
    assert_eq!(view["artifacts"][2]["facts"]["gate_state"], "unavailable");
    verify_output_self_hash(&view, "evidence_view_hash");

    let show = run_workbench(&[
        text("evidence-show"),
        text("--bundle"),
        fixture.as_os_str(),
        text("--artifact"),
        text("approval_status"),
        text("--as-of-unix"),
        text("1786579200"),
    ]);
    let artifact = output_json(&show);
    assert_eq!(
        artifact["schema_version"],
        "structural-native-evidence-artifact-view.v1"
    );
    assert_eq!(artifact["artifact"]["id"], "approval_status");
    assert_eq!(artifact["artifact"]["facts"]["blocker_count"], 1);
    verify_output_self_hash(&artifact, "evidence_artifact_view_hash");

    let temporary = TestDirectory::create();
    let tampered = temporary.0.join("evidence");
    copy_evidence_fixture(&tampered);
    std::fs::write(
        tampered.join("readiness/ready.json"),
        b"{\"source_commit_sha\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\"}\n",
    )
    .expect("tamper copied evidence");
    let rejected = run_workbench(&[text("evidence"), text("--bundle"), tampered.as_os_str()]);
    assert_eq!(rejected.status.code(), Some(1));
    let failure: Value = serde_json::from_slice(&rejected.stdout).expect("failure JSON");
    assert_eq!(failure["code"], "workbench_evidence_checksum_mismatch");

    let uppercase = temporary.0.join("uppercase-evidence");
    copy_evidence_fixture(&uppercase);
    let manifest_path = uppercase.join("manifest.json");
    let mut manifest: Value = serde_json::from_slice(
        &std::fs::read(&manifest_path).expect("read copied evidence manifest"),
    )
    .expect("decode copied evidence manifest");
    let uppercase_hash = manifest["artifacts"][0]["sha256"]
        .as_str()
        .expect("fixture SHA-256")
        .to_ascii_uppercase();
    manifest["artifacts"][0]["sha256"] = Value::String(uppercase_hash);
    std::fs::write(
        &manifest_path,
        serde_json::to_vec(&manifest).expect("encode uppercase manifest"),
    )
    .expect("write uppercase evidence manifest");
    let rejected = run_workbench(&[text("evidence"), text("--bundle"), uppercase.as_os_str()]);
    assert_eq!(rejected.status.code(), Some(1));
    let failure: Value = serde_json::from_slice(&rejected.stdout).expect("failure JSON");
    assert_eq!(
        failure["code"],
        "workbench_evidence_manifest_contract_invalid"
    );

    #[cfg(unix)]
    {
        use std::os::unix::fs::symlink;

        let symlinked = temporary.0.join("symlinked-evidence");
        copy_evidence_fixture(&symlinked);
        std::fs::remove_file(symlinked.join("readiness/ready.json"))
            .expect("remove copied evidence artifact");
        symlink(
            evidence_fixture().join("readiness/ready.json"),
            symlinked.join("readiness/ready.json"),
        )
        .expect("create evidence artifact symlink");
        let rejected = run_workbench(&[text("evidence"), text("--bundle"), symlinked.as_os_str()]);
        assert_eq!(rejected.status.code(), Some(1));
        let failure: Value = serde_json::from_slice(&rejected.stdout).expect("failure JSON");
        assert_eq!(failure["code"], "workbench_evidence_io_error");
    }
}

#[test]
fn clean_process_restart_workflow_recovers_and_is_bitwise_deterministic() {
    let (model, request, external, source) = inputs();
    let temporary = TestDirectory::create();
    let restarted = temporary.0.join("restarted");
    let direct = temporary.0.join("direct");

    let mut import = import_arguments("import", &model, &request, &external, &source, &restarted);
    import.truncate(9);
    assert_success(&run_workbench(&import));
    assert_success(&run_workbench(&stage_arguments("validate", &restarted)));
    let validated_session =
        std::fs::read(restarted.join("workbench-session.json")).expect("validated session");
    let mut run = stage_arguments("run", &restarted).to_vec();
    run.extend([text("--step-budget"), text("1")]);
    assert_success(&run_workbench(&run));

    // Model a process death after the atomic stage directory rename but before the session swap.
    std::fs::write(restarted.join("workbench-session.json"), validated_session)
        .expect("restore pre-run durable session");
    assert_success(&run_workbench(&stage_arguments("resume", &restarted)));
    let mut compare = stage_arguments("compare", &restarted).to_vec();
    compare.push(text("--require-pass"));
    assert_success(&run_workbench(&compare));
    assert_success(&run_workbench(&stage_arguments("report", &restarted)));
    assert_success(&run_workbench(&stage_arguments("status", &restarted)));

    let direct_arguments =
        import_arguments("workflow", &model, &request, &external, &source, &direct);
    assert_success(&run_workbench(&direct_arguments));

    let restarted_session = verify_session(&restarted);
    let direct_session = verify_session(&direct);
    assert_eq!(restarted_session["stage"], "reported");
    assert_eq!(restarted_session["terminal_status"], "completed");
    assert_eq!(restarted_session["comparison_passed"], true);
    assert_eq!(restarted_session, direct_session);

    let files = collect_files(&restarted);
    assert_eq!(files, collect_files(&direct));
    assert_eq!(files.len(), 29);
    for relative in files {
        assert_eq!(
            std::fs::read(restarted.join(&relative)).expect("restarted artifact"),
            std::fs::read(direct.join(&relative)).expect("direct artifact"),
            "Workbench artifact drift: {}",
            relative.display()
        );
    }
    let pdf = std::fs::read(restarted.join("06-report/report.pdf")).expect("native PDF");
    validate_deterministic_pdf_v1(&pdf).expect("deterministic native PDF structure");
    assert_eq!(
        sha256_identity(&pdf),
        "sha256:35f2bebb41411b31cba9e0c395ba74f914097498e8da63e4b14d72704f06c197"
    );
    assert_eq!(
        sha256_identity(
            &std::fs::read(restarted.join("04-resume/result-ir.json")).expect("terminal ResultIR")
        ),
        "sha256:f59193c725e236e4d824b9f2422befce5205050677489e6fc13bb8a31d580ceb"
    );
}

#[test]
fn invalid_transition_and_import_tamper_fail_closed() {
    let (model, request, external, source) = inputs();
    let temporary = TestDirectory::create();
    let workspace = temporary.0.join("session");
    let mut import = import_arguments("import", &model, &request, &external, &source, &workspace);
    import.truncate(9);
    assert_success(&run_workbench(&import));

    let invalid = run_workbench(&stage_arguments("report", &workspace));
    assert_eq!(invalid.status.code(), Some(2));
    assert!(!workspace.join("06-report").exists());

    let imported_model = workspace.join("01-import/model-ir.json");
    let mut bytes = std::fs::read(&imported_model).expect("imported ModelIR");
    bytes[0] ^= 1;
    std::fs::write(&imported_model, bytes).expect("tamper imported ModelIR");
    let rejected = run_workbench(&stage_arguments("status", &workspace));
    assert_eq!(rejected.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&rejected.stdout).contains("workbench_imported_model_invalid"));
    assert!(!workspace.join("02-validate").exists());
}

#[test]
#[allow(clippy::too_many_lines)]
fn mgt_import_restart_workflow_preserves_health_and_is_bitwise_deterministic() {
    let (source_mgt, request, external, source) = mgt_inputs();
    let temporary = TestDirectory::create();
    let restarted = temporary.0.join("mgt-restarted");
    let direct = temporary.0.join("mgt-direct");

    let mut import = mgt_import_arguments(
        "import-mgt",
        &source_mgt,
        &request,
        &external,
        &source,
        &restarted,
    );
    import.truncate(11);
    assert_success(&run_workbench(&import));
    assert_success(&run_workbench(&stage_arguments("validate", &restarted)));
    let validated_session =
        std::fs::read(restarted.join("workbench-session.json")).expect("validated MGT session");
    let mut run = stage_arguments("run", &restarted).to_vec();
    run.extend([text("--step-budget"), text("1")]);
    assert_success(&run_workbench(&run));
    std::fs::write(restarted.join("workbench-session.json"), validated_session)
        .expect("restore MGT pre-run durable session");
    assert_success(&run_workbench(&stage_arguments("resume", &restarted)));
    let mut compare = stage_arguments("compare", &restarted).to_vec();
    compare.push(text("--require-pass"));
    assert_success(&run_workbench(&compare));
    assert_success(&run_workbench(&stage_arguments("report", &restarted)));

    let direct_arguments = mgt_import_arguments(
        "workflow-mgt",
        &source_mgt,
        &request,
        &external,
        &source,
        &direct,
    );
    assert_success(&run_workbench(&direct_arguments));

    let session = verify_session(&restarted);
    assert_eq!(session["stage"], "reported");
    assert_eq!(session["comparison_passed"], true);
    assert_eq!(
        session["mgt_source_hash"],
        "sha256:d541e384cc592a2a619475c6e7524b38b5668a1287ae26c03576fb35a2244861"
    );
    assert_eq!(session, verify_session(&direct));
    let files = collect_files(&restarted);
    assert_eq!(files, collect_files(&direct));
    assert_eq!(files.len(), 34);
    for relative in files {
        assert_eq!(
            std::fs::read(restarted.join(&relative)).expect("restarted MGT artifact"),
            std::fs::read(direct.join(&relative)).expect("direct MGT artifact"),
            "MGT Workbench artifact drift: {}",
            relative.display()
        );
    }
    assert_eq!(
        std::fs::read(restarted.join("01-import/source.mgt")).expect("preserved MGT bytes"),
        std::fs::read(&source_mgt).expect("source MGT bytes")
    );
    assert_eq!(
        std::fs::read(restarted.join("01-import/mgt-native-snapshot.json"))
            .expect("MGT C++ snapshot"),
        std::fs::read(restarted.join("01-import/model-ir.json")).expect("normalized ModelIR")
    );
    let restarted_deformed = run_workbench(&[
        text("result-deformed-view"),
        text("--workspace"),
        restarted.as_os_str(),
        text("--projection"),
        text("xz"),
        text("--step"),
        text("2"),
        text("--scale"),
        text("250"),
    ]);
    let direct_deformed = run_workbench(&[
        text("result-deformed-view"),
        text("--workspace"),
        direct.as_os_str(),
        text("--projection"),
        text("xz"),
        text("--step"),
        text("2"),
        text("--scale"),
        text("250"),
    ]);
    assert_success(&restarted_deformed);
    assert_success(&direct_deformed);
    assert_eq!(restarted_deformed.stdout, direct_deformed.stdout);
    assert!(String::from_utf8_lossy(&restarted_deformed.stdout)
        .contains("Profile: fixed_guided_frame3d_x\n"));

    let mut tampered =
        std::fs::read(restarted.join("01-import/source.mgt")).expect("preserved MGT bytes");
    tampered[0] ^= 1;
    std::fs::write(restarted.join("01-import/source.mgt"), tampered).expect("tamper MGT source");
    let rejected = run_workbench(&stage_arguments("status", &restarted));
    assert_eq!(rejected.status.code(), Some(1));
    assert!(
        String::from_utf8_lossy(&rejected.stdout).contains("workbench_mgt_import_binding_mismatch")
    );
}

#[test]
fn blocked_mgt_health_cannot_create_an_analysis_workspace() {
    let root = repository_root();
    let blocked = root.join("tests/fixtures/foundation_realish/foundation_small.mgt");
    let (_, request, external, source) = mgt_inputs();
    let temporary = TestDirectory::create();
    let workspace = temporary.0.join("blocked");
    let mut arguments = mgt_import_arguments(
        "import-mgt",
        &blocked,
        &request,
        &external,
        &source,
        &workspace,
    );
    arguments.truncate(11);
    let rejected = run_workbench(&arguments);
    assert_eq!(rejected.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&rejected.stdout).contains("workbench_mgt_import_blocked"));
    assert!(!workspace.exists());
}

#[test]
fn native_review_inspect_and_export_are_deterministic_and_tamper_evident() {
    let (model, request, external, source) = inputs();
    let temporary = TestDirectory::create();
    let first = temporary.0.join("review-first");
    let second = temporary.0.join("review-second");
    for workspace in [&first, &second] {
        assert_success(&run_workbench(&import_arguments(
            "workflow", &model, &request, &external, &source, workspace,
        )));
    }

    let before = output_json(&run_workbench(&stage_arguments("inspect", &first)));
    assert_eq!(before["durable_stage"], "reported");
    assert_eq!(before["next_action"], "review");
    assert!(before["human_review"].is_null());
    assert_eq!(before["comparison"]["status"], "passed");
    assert_eq!(before["backend_receipt"]["fallback_count"], 0);
    let unreviewed_report =
        run_workbench(&[text("report-view"), text("--workspace"), first.as_os_str()]);
    assert_success(&unreviewed_report);
    assert!(
        String::from_utf8_lossy(&unreviewed_report.stdout).contains("Human review: not recorded\n")
    );

    let first_review = run_workbench(&review_arguments(&first));
    let second_review = run_workbench(&review_arguments(&second));
    assert_success(&first_review);
    assert_success(&second_review);
    assert_eq!(first_review.stdout, second_review.stdout);

    let review = output_json(&run_workbench(&stage_arguments("review-show", &first)));
    assert_eq!(review["decision"], "review");
    assert_eq!(review["reviewer"], "Engineer A");
    assert_eq!(
        review["claim_boundary"],
        "explicit_human_review_bound_to_verified_native_result_comparison_and_pdf_not_an_automated_engineering_verdict_or_signature"
    );
    assert!(review["review_hash"]
        .as_str()
        .is_some_and(|value| value.starts_with("sha256:")));

    let first_view = run_workbench(&stage_arguments("inspect", &first));
    let second_view = run_workbench(&stage_arguments("inspect", &second));
    assert_success(&first_view);
    assert_success(&second_view);
    assert_eq!(first_view.stdout, second_view.stdout);
    let view: Value = serde_json::from_slice(&first_view.stdout).expect("native view JSON");
    assert_eq!(view["next_action"], "export");
    assert_eq!(view["human_review"]["decision"], "review");
    assert_eq!(view["human_review"]["automatically_inferred"], false);

    let first_export = run_workbench(&stage_arguments("export", &first));
    let second_export = run_workbench(&stage_arguments("export", &second));
    assert_success(&first_export);
    assert_success(&second_export);
    assert_eq!(first_export.stdout, second_export.stdout);
    let export: Value = serde_json::from_slice(&first_export.stdout).expect("native export JSON");
    assert_eq!(
        export["schema_version"],
        "structural-native-workbench-export.v1"
    );
    assert_eq!(export["decision"], "review");
    assert_eq!(
        export["artifacts"].as_array().expect("artifact list").len(),
        6
    );
    assert!(export["export_hash"]
        .as_str()
        .is_some_and(|value| value.starts_with("sha256:")));

    let duplicate = run_workbench(&review_arguments(&first));
    assert_eq!(duplicate.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&duplicate.stdout).contains("workbench_review_exists"));

    let review_path = first.join("07-review/review.json");
    let mut tampered = std::fs::read(&review_path).expect("review bytes");
    tampered[0] ^= 1;
    std::fs::write(review_path, tampered).expect("tamper review");
    let rejected = run_workbench(&stage_arguments("status", &first));
    assert_eq!(rejected.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&rejected.stdout).contains("workbench_hashed_json"));
}

fn verified_response_channel_views(workspace: &Path, result_hash: &str) -> Vec<String> {
    let mut outputs = Vec::new();
    for (channel, unit) in [
        ("top-displacement", "m"),
        ("drift-ratio", "percent"),
        ("base-shear", "kN"),
        ("residual-inf", "N"),
    ] {
        let arguments = [
            text("result-view"),
            text("--workspace"),
            workspace.as_os_str(),
            text("--channel"),
            text(channel),
        ];
        let first = run_workbench(&arguments);
        let second = run_workbench(&arguments);
        assert_success(&first);
        assert_eq!(first.stdout, second.stdout);
        assert!(!first.stdout.contains(&0x1b));
        let view = String::from_utf8(first.stdout).expect("ASCII response view");
        assert!(view.starts_with("Structural Native Workbench - NDTHA response history\n"));
        assert!(view.contains("Schema: structural-native-workbench-ndtha-response-view.v1\n"));
        assert!(view.contains(&format!("Channel: {channel}\n")));
        assert!(view.contains(&format!("Unit: {unit}\n")));
        assert!(view.contains("Completed steps: 5\n"));
        assert!(view.contains("Displayed steps: 1-5 of 5\n"));
        assert!(view.contains(result_hash));
        assert!(view.contains("ResultIR v1 does not carry dt_s"));
        assert!(view.contains("not a time reconstruction, 3D/deformed/modal/contour view"));
        let (unsigned, hash_line) = view
            .rsplit_once("View hash: ")
            .expect("response view hash line");
        assert_eq!(hash_line.trim_end(), sha256_identity(unsigned.as_bytes()));
        outputs.push(view);
    }
    for left in 0..outputs.len() {
        for right in (left + 1)..outputs.len() {
            assert_ne!(outputs[left], outputs[right]);
        }
    }
    outputs
}

#[test]
#[allow(clippy::too_many_lines)]
fn ndtha_response_view_is_windowed_deterministic_hash_bound_and_terminal_gated() {
    let (model, request, external, source) = inputs();
    let temporary = TestDirectory::create();
    let workspace = temporary.0.join("response-view");
    let mut import = import_arguments("import", &model, &request, &external, &source, &workspace);
    import.truncate(9);
    assert_success(&run_workbench(&import));

    let premature = run_workbench(&[
        text("result-view"),
        text("--workspace"),
        workspace.as_os_str(),
    ]);
    assert_eq!(premature.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&premature.stdout).contains("workbench_transition_invalid"));

    for command in ["validate", "run", "resume"] {
        assert_success(&run_workbench(&stage_arguments(command, &workspace)));
    }
    let result: Value = serde_json::from_slice(
        &std::fs::read(workspace.join("04-resume/result-ir.json")).expect("terminal ResultIR"),
    )
    .expect("terminal ResultIR JSON");
    let result_hash = result["result_hash"].as_str().expect("result hash");
    let channel_outputs = verified_response_channel_views(&workspace, result_hash);
    assert_eq!(channel_outputs.len(), 4);
    let explicit_english = run_workbench(&[
        text("result-view"),
        text("--workspace"),
        workspace.as_os_str(),
        text("--locale"),
        text("en-US"),
        text("--channel"),
        text("top-displacement"),
    ]);
    assert_success(&explicit_english);
    assert_eq!(explicit_english.stdout, channel_outputs[0].as_bytes());

    let localized_arguments = [
        text("result-view"),
        text("--workspace"),
        workspace.as_os_str(),
        text("--locale"),
        text("ko-KR"),
        text("--channel"),
        text("top-displacement"),
    ];
    let localized_first = run_workbench(&localized_arguments);
    let localized_second = run_workbench(&localized_arguments);
    assert_success(&localized_first);
    assert_eq!(localized_first.stdout, localized_second.stdout);
    assert!(!localized_first.stdout.contains(&0x1b));
    let localized = String::from_utf8(localized_first.stdout).expect("Korean UTF-8 response view");
    assert!(localized.starts_with("Structural Native Workbench - NDTHA 응답 이력\n"));
    assert!(localized.contains("로케일: ko-KR\n"));
    assert!(localized.contains("채널: 최상단 변위 [top-displacement]\n"));
    assert!(localized.contains("가로 좌표: 1부터 시작하는 단계 번호"));
    assert!(localized.contains("시간값을 추론하지 않습니다"));
    assert!(localized.contains(result_hash));
    for key in [
        "request_hash",
        "model_hash",
        "state_hash",
        "execution_hash",
        "checkpoint_hash",
    ] {
        assert!(localized.contains(
            result["identity"][key]
                .as_str()
                .expect("terminal ResultIR identity")
        ));
    }
    let english_rows = channel_outputs[0]
        .lines()
        .filter(|line| line.starts_with("000"))
        .collect::<Vec<_>>();
    let localized_rows = localized
        .lines()
        .filter(|line| line.starts_with("000"))
        .collect::<Vec<_>>();
    assert_eq!(localized_rows, english_rows);
    let (unsigned, hash_line) = localized
        .rsplit_once("보기 해시: ")
        .expect("Korean response view hash line");
    assert_eq!(hash_line.trim_end(), sha256_identity(unsigned.as_bytes()));
    assert_ne!(localized, channel_outputs[0]);

    let window = run_workbench(&[
        text("result-view"),
        text("--workspace"),
        workspace.as_os_str(),
        text("--channel"),
        text("drift-ratio"),
        text("--start-step"),
        text("2"),
        text("--count"),
        text("2"),
    ]);
    assert_success(&window);
    let window = String::from_utf8(window.stdout).expect("windowed response view");
    assert!(window.contains("Displayed steps: 2-3 of 5\n"));
    assert!(!window.lines().any(|line| line.starts_with("000001 ")));
    assert!(window.lines().any(|line| line.starts_with("000002 ")));
    assert!(window.lines().any(|line| line.starts_with("000003 ")));
    assert!(!window.lines().any(|line| line.starts_with("000004 ")));

    for arguments in [
        vec![
            text("result-view"),
            text("--workspace"),
            workspace.as_os_str(),
            text("--channel"),
            text("energy"),
        ],
        vec![
            text("result-view"),
            text("--workspace"),
            workspace.as_os_str(),
            text("--count"),
            text("257"),
        ],
        vec![
            text("result-view"),
            text("--workspace"),
            workspace.as_os_str(),
            text("--start-step"),
            text("6"),
        ],
    ] {
        let rejected = run_workbench(&arguments);
        assert_eq!(rejected.status.code(), Some(2));
    }

    let result_path = workspace.join("04-resume/result-ir.json");
    let mut tampered = std::fs::read(&result_path).expect("terminal ResultIR bytes");
    tampered[0] ^= 1;
    std::fs::write(result_path, tampered).expect("tamper terminal ResultIR");
    let rejected = run_workbench(&[
        text("result-view"),
        text("--workspace"),
        workspace.as_os_str(),
    ]);
    assert_eq!(rejected.status.code(), Some(1));
    assert!(
        String::from_utf8_lossy(&rejected.stdout).contains("workbench_artifact_inventory_mismatch")
    );
}

#[test]
#[allow(clippy::too_many_lines)]
fn fixed_guided_deformed_view_is_profile_bound_deterministic_and_terminal_gated() {
    let (model, request, external, source) = inputs();
    let temporary = TestDirectory::create();
    let workspace = temporary.0.join("deformed-view");
    let mut import = import_arguments("import", &model, &request, &external, &source, &workspace);
    import.truncate(9);
    assert_success(&run_workbench(&import));

    let premature = run_workbench(&[
        text("result-deformed-view"),
        text("--workspace"),
        workspace.as_os_str(),
    ]);
    assert_eq!(premature.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&premature.stdout).contains("workbench_transition_invalid"));

    for command in ["validate", "run", "resume"] {
        assert_success(&run_workbench(&stage_arguments(command, &workspace)));
    }
    let session_before = std::fs::read(workspace.join("workbench-session.json"))
        .expect("session before deformed views");
    let result: Value = serde_json::from_slice(
        &std::fs::read(workspace.join("04-resume/result-ir.json")).expect("terminal ResultIR"),
    )
    .expect("terminal ResultIR JSON");
    let result_hash = result["result_hash"].as_str().expect("result hash");
    let mut projection_outputs = Vec::new();
    for projection in ["isometric", "xy", "xz", "yz"] {
        let arguments = [
            text("result-deformed-view"),
            text("--workspace"),
            workspace.as_os_str(),
            text("--projection"),
            text(projection),
        ];
        let first = run_workbench(&arguments);
        let second = run_workbench(&arguments);
        assert_success(&first);
        assert_eq!(first.stdout, second.stdout);
        assert!(!first.stdout.contains(&0x1b));
        let view = String::from_utf8(first.stdout).expect("ASCII deformed view");
        assert!(
            view.starts_with("Structural Native Workbench - fixed-guided NDTHA deformed shape\n")
        );
        assert!(
            view.contains("Schema: structural-native-workbench-fixed-guided-deformed-view.v1\n")
        );
        assert!(view.contains("Profile: fixed_guided_frame3d_x\n"));
        assert!(view.contains(&format!("Projection: {projection}\n")));
        assert!(view.contains("Selected step: 5\n"));
        assert!(view.contains("Visual magnification: 1.00000000000000000e3\n"));
        assert!(view.contains("C++ semantic snapshot: verified\n"));
        assert!(view.contains(
            "C++ fixed-guided adapter execution: verified by durable terminal receipt\n"
        ));
        assert!(view.contains(result_hash));
        assert!(view.contains("not_general_nodal_displacement_3d_modal_contour"));
        let (unsigned, hash_line) = view
            .rsplit_once("View hash: ")
            .expect("deformed view hash line");
        assert_eq!(hash_line.trim_end(), sha256_identity(unsigned.as_bytes()));
        projection_outputs.push(view);
    }
    for left in 0..projection_outputs.len() {
        for right in (left + 1)..projection_outputs.len() {
            assert_ne!(projection_outputs[left], projection_outputs[right]);
        }
    }
    assert!(projection_outputs[3].contains("Projected motion visible: false\n"));
    let explicit_english = run_workbench(&[
        text("result-deformed-view"),
        text("--workspace"),
        workspace.as_os_str(),
        text("--locale"),
        text("en-US"),
        text("--projection"),
        text("isometric"),
    ]);
    assert_success(&explicit_english);
    assert_eq!(explicit_english.stdout, projection_outputs[0].as_bytes());

    let localized_arguments = [
        text("result-deformed-view"),
        text("--workspace"),
        workspace.as_os_str(),
        text("--locale"),
        text("ko-KR"),
        text("--projection"),
        text("isometric"),
    ];
    let localized_first = run_workbench(&localized_arguments);
    let localized_second = run_workbench(&localized_arguments);
    assert_success(&localized_first);
    assert_eq!(localized_first.stdout, localized_second.stdout);
    assert!(!localized_first.stdout.contains(&0x1b));
    let localized = String::from_utf8(localized_first.stdout).expect("Korean UTF-8 deformed view");
    assert!(localized.starts_with("Structural Native Workbench - 고정-가이드 NDTHA 변형 형상\n"));
    assert!(localized.contains("로케일: ko-KR\n"));
    assert!(localized.contains("프로파일: fixed_guided_frame3d_x\n"));
    assert!(localized.contains("투영: isometric\n"));
    assert!(localized.contains("C++ 의미 스냅샷: verified\n"));
    assert!(localized.contains("주장 경계: exact_executed_fixed_guided"));
    assert!(localized.contains(result_hash));
    for key in [
        "request_hash",
        "model_hash",
        "state_hash",
        "execution_hash",
        "checkpoint_hash",
    ] {
        assert!(localized.contains(
            result["identity"][key]
                .as_str()
                .expect("terminal ResultIR identity")
        ));
    }
    let displacement = result["response"]["top_displacement_m"][4]
        .as_f64()
        .expect("terminal top displacement");
    assert!(localized.contains(&format!("{displacement:+.17e}")));
    let english_canvas = projection_outputs[0]
        .lines()
        .filter(|line| line.starts_with('|') || line.starts_with('+'))
        .collect::<Vec<_>>();
    let localized_canvas = localized
        .lines()
        .filter(|line| line.starts_with('|') || line.starts_with('+'))
        .collect::<Vec<_>>();
    assert_eq!(localized_canvas, english_canvas);
    let (unsigned, hash_line) = localized
        .rsplit_once("보기 해시: ")
        .expect("Korean deformed view hash line");
    assert_eq!(hash_line.trim_end(), sha256_identity(unsigned.as_bytes()));
    assert_ne!(localized, projection_outputs[0]);

    let explicit = run_workbench(&[
        text("result-deformed-view"),
        text("--workspace"),
        workspace.as_os_str(),
        text("--projection"),
        text("xz"),
        text("--step"),
        text("2"),
        text("--scale"),
        text("250"),
    ]);
    assert_success(&explicit);
    let explicit = String::from_utf8(explicit.stdout).expect("explicit deformed view");
    assert!(explicit.contains("Selected step: 2\n"));
    assert!(explicit.contains("Visual magnification: 2.50000000000000000e2\n"));
    assert_ne!(explicit, projection_outputs[2]);

    for arguments in [
        vec![
            text("result-deformed-view"),
            text("--workspace"),
            workspace.as_os_str(),
            text("--step"),
            text("6"),
        ],
        vec![
            text("result-deformed-view"),
            text("--workspace"),
            workspace.as_os_str(),
            text("--scale"),
            text("1000001"),
        ],
    ] {
        let rejected = run_workbench(&arguments);
        assert_eq!(rejected.status.code(), Some(2));
    }
    assert_eq!(
        std::fs::read(workspace.join("workbench-session.json"))
            .expect("session after deformed views"),
        session_before
    );

    let result_path = workspace.join("04-resume/result-ir.json");
    let mut tampered = std::fs::read(&result_path).expect("terminal ResultIR bytes");
    tampered[0] ^= 1;
    std::fs::write(result_path, tampered).expect("tamper terminal ResultIR");
    let rejected = run_workbench(&[
        text("result-deformed-view"),
        text("--workspace"),
        workspace.as_os_str(),
    ]);
    assert_eq!(rejected.status.code(), Some(1));
    assert!(
        String::from_utf8_lossy(&rejected.stdout).contains("workbench_artifact_inventory_mismatch")
    );
}

#[test]
fn localized_linear_report_view_is_utf8_deterministic_and_hash_bound() {
    let (model, request, external, source) = inputs();
    let temporary = TestDirectory::create();
    let first = temporary.0.join("localized-first");
    let second = temporary.0.join("localized-second");
    for workspace in [&first, &second] {
        assert_success(&run_workbench(&import_arguments(
            "workflow", &model, &request, &external, &source, workspace,
        )));
        assert_success(&run_workbench(&[
            text("review"),
            text("--workspace"),
            workspace.as_os_str(),
            text("--decision"),
            text("review"),
            text("--reviewer"),
            text("김 구조"),
            text("--comment"),
            text("접합부 가정을 확인하세요.\n이 줄은 색상없이도 읽혀야 합니다."),
        ]));
    }

    let korean_arguments = [
        text("report-view"),
        text("--workspace"),
        first.as_os_str(),
        text("--locale"),
        text("ko-KR"),
    ];
    let first_korean = run_workbench(&korean_arguments);
    let second_korean = run_workbench(&[
        text("report-view"),
        text("--workspace"),
        second.as_os_str(),
        text("--locale"),
        text("ko-KR"),
    ]);
    assert_success(&first_korean);
    assert_success(&second_korean);
    assert_eq!(first_korean.stdout, second_korean.stdout);
    assert!(!first_korean.stdout.contains(&0x1b));
    let korean = String::from_utf8(first_korean.stdout).expect("Korean UTF-8 report view");
    assert!(korean.starts_with("구조 네이티브 워크벤치 - 선형 보고서\n"));
    assert!(korean.contains("언어: ko-KR\n"));
    assert!(korean.contains("표현: UTF-8 선형 텍스트;"));
    assert!(korean.contains("검토자: 김 구조\n"));
    assert!(korean.contains("비교 해시: sha256:"));
    assert!(korean.contains("검토 해시: sha256:"));
    assert!(korean.contains("  접합부 가정을 확인하세요.\n"));
    assert!(korean.contains("  이 줄은 색상없이도 읽혀야 합니다.\n"));
    assert!(korean.contains("WCAG, PDF/UA"));
    let (unsigned, hash_line) = korean
        .rsplit_once("보기 해시: ")
        .expect("localized report view hash line");
    assert_eq!(hash_line.trim_end(), sha256_identity(unsigned.as_bytes()));

    let english = run_workbench(&[text("report-view"), text("--workspace"), first.as_os_str()]);
    assert_success(&english);
    let english = String::from_utf8(english.stdout).expect("English UTF-8 report view");
    assert!(english.starts_with("Structural Native Workbench - linear report\n"));
    assert!(english.contains("Locale: en-US\n"));
    assert!(english.contains("Reviewer: 김 구조\n"));
    let result: Value = serde_json::from_slice(
        &std::fs::read(first.join("04-resume/result-ir.json")).expect("terminal ResultIR"),
    )
    .expect("terminal ResultIR JSON");
    let report: Value = serde_json::from_slice(
        &std::fs::read(first.join("04-resume/report-ir.json")).expect("terminal ReportIR"),
    )
    .expect("terminal ReportIR JSON");
    let comparison: Value = serde_json::from_slice(
        &std::fs::read(first.join("05-compare/comparison-receipt.json"))
            .expect("comparison receipt"),
    )
    .expect("comparison receipt JSON");
    let review: Value = serde_json::from_slice(
        &std::fs::read(first.join("07-review/review.json")).expect("review"),
    )
    .expect("review JSON");
    for value in [
        result["result_hash"].as_str().expect("result hash"),
        report["report_hash"].as_str().expect("report hash"),
        report["document_source_hash"]
            .as_str()
            .expect("document hash"),
        comparison["comparison_hash"]
            .as_str()
            .expect("comparison hash"),
        review["review_hash"].as_str().expect("review hash"),
    ] {
        assert!(english.contains(value));
        assert!(korean.contains(value));
    }

    let invalid_locale = run_workbench(&[
        text("report-view"),
        text("--workspace"),
        first.as_os_str(),
        text("--locale"),
        text("ko-kr"),
    ]);
    assert_eq!(invalid_locale.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&invalid_locale.stdout)
        .contains("report-view locale must be en-US or ko-KR"));
}

#[test]
#[allow(clippy::too_many_lines)]
fn localized_pdf_export_is_deterministic_hash_bound_and_non_mutating() {
    let (model, request, external, source) = inputs();
    let temporary = TestDirectory::create();
    let workspace = temporary.0.join("localized-pdf-session");
    assert_success(&run_workbench(&import_arguments(
        "workflow", &model, &request, &external, &source, &workspace,
    )));
    let workspace_files = collect_files(&workspace);
    let workspace_bytes = workspace_files
        .iter()
        .map(|relative| {
            (
                relative.clone(),
                std::fs::read(workspace.join(relative)).expect("workspace artifact"),
            )
        })
        .collect::<Vec<_>>();

    let mut locale_hashes = Vec::new();
    for locale in ["en-US", "ko-KR"] {
        let first = temporary.0.join(format!("localized-pdf-{locale}-first"));
        let second = temporary.0.join(format!("localized-pdf-{locale}-second"));
        for output_directory in [&first, &second] {
            let output = run_workbench(&[
                text("report-export-pdf"),
                text("--workspace"),
                workspace.as_os_str(),
                text("--output-dir"),
                output_directory.as_os_str(),
                text("--locale"),
                text(locale),
            ]);
            assert_success(&output);
            let receipt: Value =
                serde_json::from_slice(&output.stdout).expect("localized PDF receipt stdout");
            assert_eq!(
                receipt["schema_version"],
                "structural-native-localized-pdf-report-receipt.v2"
            );
            assert_eq!(receipt["locale"], locale);
            assert_eq!(receipt["embedded_font"]["license"]["id"], "OFL-1.1");
            let stored_receipt =
                std::fs::read(output_directory.join("pdf-receipt.json")).expect("stored receipt");
            assert_eq!(
                String::from_utf8_lossy(&output.stdout).trim_end(),
                String::from_utf8_lossy(&stored_receipt)
            );
            let pdf =
                std::fs::read(output_directory.join("report.pdf")).expect("localized PDF artifact");
            validate_deterministic_localized_pdf_v2(&pdf)
                .expect("localized PDF structure and embedded font");
            assert_eq!(receipt["pdf_hash"], sha256_identity(&pdf));

            let mut unsigned = receipt;
            let receipt_hash = unsigned
                .as_object_mut()
                .expect("receipt object")
                .remove("receipt_hash")
                .and_then(|value| value.as_str().map(str::to_owned))
                .expect("receipt hash");
            let canonical = canonicalize_model_ir_v2(&unsigned).expect("canonical receipt");
            assert_eq!(receipt_hash, sha256_identity(canonical.as_bytes()));
        }
        for file in ["report.pdf", "pdf-receipt.json"] {
            assert_eq!(
                std::fs::read(first.join(file)).expect("first localized artifact"),
                std::fs::read(second.join(file)).expect("second localized artifact"),
                "localized Workbench PDF drift: {locale}/{file}"
            );
        }
        locale_hashes.push(sha256_identity(
            &std::fs::read(first.join("report.pdf")).expect("localized PDF"),
        ));
    }
    assert_ne!(locale_hashes[0], locale_hashes[1]);
    assert_eq!(workspace_files, collect_files(&workspace));
    for (relative, before) in workspace_bytes {
        assert_eq!(
            before,
            std::fs::read(workspace.join(&relative)).expect("unchanged workspace artifact"),
            "localized export mutated workspace artifact: {}",
            relative.display()
        );
    }

    let invalid_destination = temporary.0.join("invalid-locale-pdf");
    let invalid = run_workbench(&[
        text("report-export-pdf"),
        text("--workspace"),
        workspace.as_os_str(),
        text("--output-dir"),
        invalid_destination.as_os_str(),
        text("--locale"),
        text("ko-kr"),
    ]);
    assert_eq!(invalid.status.code(), Some(2));
    assert!(!invalid_destination.exists());

    let existing = temporary.0.join("existing-localized-pdf");
    std::fs::create_dir(&existing).expect("existing output directory");
    std::fs::write(existing.join("sentinel"), b"preserve").expect("sentinel");
    let rejected = run_workbench(&[
        text("report-export-pdf"),
        text("--workspace"),
        workspace.as_os_str(),
        text("--output-dir"),
        existing.as_os_str(),
        text("--locale"),
        text("ko-KR"),
    ]);
    assert_eq!(rejected.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&rejected.stdout)
        .contains("workbench_localized_pdf_publish_failed"));
    assert_eq!(
        std::fs::read(existing.join("sentinel")).expect("preserved sentinel"),
        b"preserve"
    );
}
