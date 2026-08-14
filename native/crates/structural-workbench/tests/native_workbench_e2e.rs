use std::ffi::{OsStr, OsString};
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicU64, Ordering};

use serde_json::Value;
use structural_cli::{
    execute_model_ir_linear_analysis, validate_model_bytes, ModelIrLinearAnalysisOutcomeV1,
};
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

fn run_node_add(
    source: &Path,
    destination: &Path,
    node_id: &str,
    coordinates: [&str; 3],
) -> Output {
    run_workbench(&[
        text("model-add-node"),
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

fn run_orphan_node_delete(source: &Path, destination: &Path, node_id: &str) -> Output {
    run_workbench(&[
        text("model-delete-orphan-node"),
        source.as_os_str(),
        text("--node"),
        text(node_id),
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

fn run_truss_section_edit(
    source: &Path,
    destination: &Path,
    section_id: &str,
    area_m2: &str,
) -> Output {
    run_workbench(&[
        text("model-edit-truss-section"),
        source.as_os_str(),
        text("--section"),
        text(section_id),
        text("--area-m2"),
        text(area_m2),
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

fn run_frame_element_properties_edit(
    source: &Path,
    destination: &Path,
    element_id: &str,
    material_id: &str,
    section_id: &str,
) -> Output {
    run_workbench(&[
        text("model-edit-frame-element-properties"),
        source.as_os_str(),
        text("--element"),
        text(element_id),
        text("--material"),
        text(material_id),
        text("--section"),
        text(section_id),
        text("--output-dir"),
        destination.as_os_str(),
    ])
}

fn run_truss_element_properties_edit(
    source: &Path,
    destination: &Path,
    element_id: &str,
    material_id: &str,
    section_id: &str,
) -> Output {
    run_workbench(&[
        text("model-edit-truss-element-properties"),
        source.as_os_str(),
        text("--element"),
        text(element_id),
        text("--material"),
        text(material_id),
        text("--section"),
        text(section_id),
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

#[allow(clippy::too_many_arguments)]
fn run_truss3d_member_add(
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
        text("model-add-truss3d-member"),
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

fn run_frame3d_leaf_member_delete(
    source: &Path,
    destination: &Path,
    element_id: &str,
    node_id: &str,
) -> Output {
    run_workbench(&[
        text("model-delete-frame3d-leaf-member"),
        source.as_os_str(),
        text("--element"),
        text(element_id),
        text("--node"),
        text(node_id),
        text("--output-dir"),
        destination.as_os_str(),
    ])
}

fn run_truss3d_leaf_member_delete(
    source: &Path,
    destination: &Path,
    element_id: &str,
    node_id: &str,
) -> Output {
    run_workbench(&[
        text("model-delete-truss3d-leaf-member"),
        source.as_os_str(),
        text("--element"),
        text(element_id),
        text("--node"),
        text(node_id),
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

fn run_nodal_load_delete(
    source: &Path,
    destination: &Path,
    load_pattern_id: &str,
    nodal_load_id: &str,
) -> Output {
    run_workbench(&[
        text("model-delete-nodal-load"),
        source.as_os_str(),
        text("--load-pattern"),
        text(load_pattern_id),
        text("--load"),
        text(nodal_load_id),
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

fn run_fixed_constraint_delete(source: &Path, destination: &Path, constraint_id: &str) -> Output {
    run_workbench(&[
        text("model-delete-fixed-constraint"),
        source.as_os_str(),
        text("--constraint"),
        text(constraint_id),
        text("--output-dir"),
        destination.as_os_str(),
    ])
}

fn run_linear_load_pattern_add(
    source: &Path,
    destination: &Path,
    load_pattern_id: &str,
    nodal_load_id: &str,
    node_id: &str,
    components: [&str; 6],
) -> Output {
    run_workbench(&[
        text("model-add-linear-load-pattern"),
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

fn run_linear_load_combination_add(
    source: &Path,
    destination: &Path,
    load_combination_id: &str,
    first_term: [&str; 2],
    second_term: [&str; 2],
) -> Output {
    run_direct_linear_load_combination_add(
        source,
        destination,
        load_combination_id,
        &[first_term, second_term],
    )
}

fn run_direct_linear_load_combination_add(
    source: &Path,
    destination: &Path,
    load_combination_id: &str,
    terms: &[[&str; 2]],
) -> Output {
    let mut arguments = vec![
        OsString::from("model-add-linear-load-combination"),
        source.as_os_str().to_owned(),
        OsString::from("--load-combination"),
        OsString::from(load_combination_id),
    ];
    for term in terms {
        arguments.push(OsString::from("--term"));
        arguments.push(OsString::from(term[0]));
        arguments.push(OsString::from(term[1]));
    }
    arguments.push(OsString::from("--output-dir"));
    arguments.push(destination.as_os_str().to_owned());
    let borrowed = arguments
        .iter()
        .map(OsString::as_os_str)
        .collect::<Vec<_>>();
    run_workbench(&borrowed)
}

fn run_direct_linear_load_combination_term_add(
    source: &Path,
    destination: &Path,
    load_combination_id: &str,
    load_pattern_id: &str,
    factor: &str,
) -> Output {
    run_workbench(&[
        text("model-add-linear-load-combination-term"),
        source.as_os_str(),
        text("--load-combination"),
        text(load_combination_id),
        text("--load-pattern"),
        text(load_pattern_id),
        text("--factor"),
        text(factor),
        text("--output-dir"),
        destination.as_os_str(),
    ])
}

fn run_direct_linear_load_combination_term_delete(
    source: &Path,
    destination: &Path,
    load_combination_id: &str,
    load_pattern_id: &str,
) -> Output {
    run_workbench(&[
        text("model-delete-linear-load-combination-term"),
        source.as_os_str(),
        text("--load-combination"),
        text(load_combination_id),
        text("--load-pattern"),
        text(load_pattern_id),
        text("--output-dir"),
        destination.as_os_str(),
    ])
}

fn run_nested_linear_load_combination_add(
    source: &Path,
    destination: &Path,
    load_combination_id: &str,
    terms: &[[&str; 3]],
) -> Output {
    let mut arguments = vec![
        OsString::from("model-add-nested-linear-load-combination"),
        source.as_os_str().to_owned(),
        OsString::from("--load-combination"),
        OsString::from(load_combination_id),
    ];
    for term in terms {
        arguments.push(OsString::from(term[0]));
        arguments.push(OsString::from(term[1]));
        arguments.push(OsString::from(term[2]));
    }
    arguments.push(OsString::from("--output-dir"));
    arguments.push(destination.as_os_str().to_owned());
    let borrowed = arguments
        .iter()
        .map(OsString::as_os_str)
        .collect::<Vec<_>>();
    run_workbench(&borrowed)
}

fn run_direct_linear_load_combination_factor_edit(
    source: &Path,
    destination: &Path,
    load_combination_id: &str,
    load_pattern_id: &str,
    factor: &str,
) -> Output {
    run_workbench(&[
        text("model-edit-linear-load-combination-factor"),
        source.as_os_str(),
        text("--load-combination"),
        text(load_combination_id),
        text("--load-pattern"),
        text(load_pattern_id),
        text("--factor"),
        text(factor),
        text("--output-dir"),
        destination.as_os_str(),
    ])
}

fn run_direct_linear_load_combination_reference_edit(
    source: &Path,
    destination: &Path,
    load_combination_id: &str,
    load_pattern_id: &str,
    replacement_load_pattern_id: &str,
) -> Output {
    run_workbench(&[
        text("model-edit-linear-load-combination-reference"),
        source.as_os_str(),
        text("--load-combination"),
        text(load_combination_id),
        text("--load-pattern"),
        text(load_pattern_id),
        text("--replacement-load-pattern"),
        text(replacement_load_pattern_id),
        text("--output-dir"),
        destination.as_os_str(),
    ])
}

fn run_nested_linear_load_combination_factor_edit(
    source: &Path,
    destination: &Path,
    load_combination_id: &str,
    reference_kind: &str,
    reference_id: &str,
    factor: &str,
) -> Output {
    run_workbench(&[
        text("model-edit-nested-linear-load-combination-factor"),
        source.as_os_str(),
        text("--load-combination"),
        text(load_combination_id),
        text("--ref-kind"),
        text(reference_kind),
        text("--ref-id"),
        text(reference_id),
        text("--factor"),
        text(factor),
        text("--output-dir"),
        destination.as_os_str(),
    ])
}

#[allow(clippy::too_many_arguments)]
fn run_nested_linear_load_combination_reference_edit(
    source: &Path,
    destination: &Path,
    load_combination_id: &str,
    reference_kind: &str,
    reference_id: &str,
    replacement_reference_kind: &str,
    replacement_reference_id: &str,
) -> Output {
    run_workbench(&[
        text("model-edit-nested-linear-load-combination-reference"),
        source.as_os_str(),
        text("--load-combination"),
        text(load_combination_id),
        text("--ref-kind"),
        text(reference_kind),
        text("--ref-id"),
        text(reference_id),
        text("--replacement-ref-kind"),
        text(replacement_reference_kind),
        text("--replacement-ref-id"),
        text(replacement_reference_id),
        text("--output-dir"),
        destination.as_os_str(),
    ])
}

fn run_linear_load_combination_delete(
    source: &Path,
    destination: &Path,
    load_combination_id: &str,
) -> Output {
    run_workbench(&[
        text("model-delete-linear-load-combination"),
        source.as_os_str(),
        text("--load-combination"),
        text(load_combination_id),
        text("--output-dir"),
        destination.as_os_str(),
    ])
}

fn run_linear_load_pattern_delete(
    source: &Path,
    destination: &Path,
    load_pattern_id: &str,
) -> Output {
    run_workbench(&[
        text("model-delete-linear-load-pattern"),
        source.as_os_str(),
        text("--load-pattern"),
        text(load_pattern_id),
        text("--output-dir"),
        destination.as_os_str(),
    ])
}

fn run_linear_material_add(
    source: &Path,
    destination: &Path,
    material_id: &str,
    parameters: [&str; 3],
) -> Output {
    run_workbench(&[
        text("model-add-linear-material"),
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

fn run_linear_material_delete(source: &Path, destination: &Path, material_id: &str) -> Output {
    run_workbench(&[
        text("model-delete-linear-material"),
        source.as_os_str(),
        text("--material"),
        text(material_id),
        text("--output-dir"),
        destination.as_os_str(),
    ])
}

fn run_frame_section_add(
    source: &Path,
    destination: &Path,
    section_id: &str,
    parameters: [&str; 6],
) -> Output {
    run_workbench(&[
        text("model-add-frame-section"),
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

fn run_frame_section_delete(source: &Path, destination: &Path, section_id: &str) -> Output {
    run_workbench(&[
        text("model-delete-frame-section"),
        source.as_os_str(),
        text("--section"),
        text(section_id),
        text("--output-dir"),
        destination.as_os_str(),
    ])
}

fn run_truss_section_add(
    source: &Path,
    destination: &Path,
    section_id: &str,
    area_m2: &str,
) -> Output {
    run_workbench(&[
        text("model-add-truss-section"),
        source.as_os_str(),
        text("--section"),
        text(section_id),
        text("--area-m2"),
        text(area_m2),
        text("--output-dir"),
        destination.as_os_str(),
    ])
}

fn run_truss_section_delete(source: &Path, destination: &Path, section_id: &str) -> Output {
    run_workbench(&[
        text("model-delete-truss-section"),
        source.as_os_str(),
        text("--section"),
        text(section_id),
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

fn run_model_linear_combination_request_create(
    source: &Path,
    destination: &Path,
    case_id: &str,
    load_combination_id: &str,
) -> Output {
    run_workbench(&[
        text("model-create-linear-analysis-request"),
        source.as_os_str(),
        text("--case"),
        text(case_id),
        text("--load-combination"),
        text(load_combination_id),
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

fn assert_published_frame_element_properties_edit(destination: &Path) {
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
    assert_eq!(element["material_id"], "M2");
    assert_eq!(element["section_id"], "S2");
    assert_eq!(element["node_ids"], serde_json::json!(["N1", "N2"]));
    assert_eq!(element["local_axis_rotation_rad"], 0.0);
    assert!(edited.value()["extensions"]
        .get("structural-native:model-edit-frame-element-properties.v1")
        .is_some());
    let mut receipt: Value = serde_json::from_slice(
        &std::fs::read(destination.join("edit-receipt.json"))
            .expect("frame-element property edit receipt"),
    )
    .expect("frame-element property edit receipt JSON");
    assert_eq!(receipt["operation"], "frame_element_properties");
    assert_eq!(receipt["element_id"], "E1");
    assert_eq!(receipt["element_type"], "frame_3d");
    assert_eq!(receipt["formulation"], "euler_bernoulli_3d");
    assert_eq!(receipt["previous_material_id"], "M1");
    assert_eq!(receipt["edited_material_id"], "M2");
    assert_eq!(receipt["previous_section_id"], "S1");
    assert_eq!(receipt["edited_section_id"], "S2");
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

fn assert_published_linear_load_pattern_add(destination: &Path) {
    let edited_bytes =
        std::fs::read(destination.join("model-ir.json")).expect("pattern-added ModelIR");
    let edited = parse_model_ir_v2(&edited_bytes).expect("strict pattern-added ModelIR");
    let patterns = edited.value()["load_patterns"]
        .as_array()
        .expect("load patterns");
    assert_eq!(patterns.len(), 5);
    let pattern = &patterns[4];
    assert_eq!(pattern["id"], "LC_CUSTOM");
    assert_eq!(pattern["index"], 4);
    assert_eq!(pattern["analysis_type"], "linear_static");
    assert_eq!(pattern["self_weight"], serde_json::json!([0, 0, 0]));
    assert_eq!(pattern["source_id"], Value::Null);
    let loads = pattern["nodal_loads"].as_array().expect("nodal loads");
    assert_eq!(loads.len(), 1);
    assert_eq!(loads[0]["id"], "L_CUSTOM_N2");
    assert_eq!(loads[0]["index"], 0);
    assert_eq!(loads[0]["node_id"], "N2");
    assert_eq!(loads[0]["components_si"]["FX"], 2_500.0);
    assert_eq!(loads[0]["source_id"], Value::Null);
    assert!(edited.value()["extensions"]
        .get("structural-native:model-add-linear-load-pattern.v1")
        .is_some());

    let mut receipt: Value = serde_json::from_slice(
        &std::fs::read(destination.join("edit-receipt.json"))
            .expect("linear-load-pattern add receipt"),
    )
    .expect("linear-load-pattern add receipt JSON");
    assert_eq!(receipt["operation"], "linear_load_pattern_add");
    assert_eq!(receipt["load_pattern_id"], "LC_CUSTOM");
    assert_eq!(receipt["load_pattern_index"], 4);
    assert_eq!(receipt["analysis_type"], "linear_static");
    assert_eq!(receipt["self_weight"], serde_json::json!([0, 0, 0]));
    assert_eq!(receipt["nodal_load_id"], "L_CUSTOM_N2");
    assert_eq!(receipt["nodal_load_index"], 0);
    assert_eq!(receipt["node_id"], "N2");
    assert_eq!(receipt["components_si"]["FX"], 2_500.0);
    assert_eq!(receipt["cpp_semantic_snapshot_verified"], true);
    assert_eq!(receipt["analysis_ready"], true);
    assert_eq!(receipt["edited_content_hash"], edited.content_hash());
    assert_self_hashed_edit_receipt(&mut receipt);
}

fn assert_published_linear_material_add(destination: &Path) {
    let edited_bytes =
        std::fs::read(destination.join("model-ir.json")).expect("material-added ModelIR");
    let edited = parse_model_ir_v2(&edited_bytes).expect("strict material-added ModelIR");
    let materials = edited.value()["materials"].as_array().expect("materials");
    assert_eq!(materials.len(), 2);
    let material = &materials[1];
    assert_eq!(material["id"], "M2");
    assert_eq!(material["index"], 1);
    assert_eq!(material["law_id"], "linear_elastic_isotropic");
    assert_eq!(material["parameter_set_version"], "1");
    assert_eq!(
        material["parameters"]["elastic_modulus_pa"],
        100_000_000_000.0
    );
    assert_eq!(material["parameters"]["poisson_ratio"], 0.3);
    assert_eq!(material["parameters"]["density_kg_m3"], 2_700.0);
    assert_eq!(material["state_schema"]["stateful"], false);
    assert_eq!(material["state_schema"]["state_update_epoch"], "none");
    assert_eq!(
        material["state_schema"]["supports_trial_commit_rollback"],
        true
    );
    assert_eq!(material["source_id"], Value::Null);
    assert!(edited.value()["extensions"]
        .get("structural-native:model-add-linear-material.v1")
        .is_some());

    let mut receipt: Value = serde_json::from_slice(
        &std::fs::read(destination.join("edit-receipt.json")).expect("linear-material add receipt"),
    )
    .expect("linear-material add receipt JSON");
    assert_eq!(receipt["operation"], "linear_material_add");
    assert_eq!(receipt["material_id"], "M2");
    assert_eq!(receipt["material_index"], 1);
    assert_eq!(receipt["law_id"], "linear_elastic_isotropic");
    assert_eq!(receipt["parameter_set_version"], "1");
    assert_eq!(receipt["parameters_si"], material["parameters"]);
    assert_eq!(receipt["state_schema"], material["state_schema"]);
    assert_eq!(receipt["cpp_semantic_snapshot_verified"], true);
    assert_eq!(receipt["analysis_ready"], true);
    assert_eq!(receipt["edited_content_hash"], edited.content_hash());
    assert_self_hashed_edit_receipt(&mut receipt);
}

fn assert_published_frame_section_add(destination: &Path) {
    let edited_bytes =
        std::fs::read(destination.join("model-ir.json")).expect("section-added ModelIR");
    let edited = parse_model_ir_v2(&edited_bytes).expect("strict section-added ModelIR");
    let sections = edited.value()["sections"].as_array().expect("sections");
    assert_eq!(sections.len(), 2);
    let section = &sections[1];
    assert_eq!(section["id"], "S2");
    assert_eq!(section["index"], 1);
    assert_eq!(section["family_id"], "frame_3d");
    assert_eq!(section["parameter_set_version"], "1");
    assert_eq!(section["parameters"]["area_m2"], 0.01);
    assert_eq!(section["parameters"]["iy_m4"], 0.000_04);
    assert_eq!(section["parameters"]["iz_m4"], 0.000_025);
    assert_eq!(section["parameters"]["torsional_constant_m4"], 0.000_005);
    assert_eq!(section["parameters"]["shear_area_y_m2"], 0.008);
    assert_eq!(section["parameters"]["shear_area_z_m2"], 0.008);
    assert_eq!(section["source_id"], Value::Null);
    assert_eq!(section["extensions"], serde_json::json!({}));
    assert!(edited.value()["extensions"]
        .get("structural-native:model-add-frame-section.v1")
        .is_some());

    let mut receipt: Value = serde_json::from_slice(
        &std::fs::read(destination.join("edit-receipt.json")).expect("frame-section add receipt"),
    )
    .expect("frame-section add receipt JSON");
    assert_eq!(receipt["operation"], "frame_section_add");
    assert_eq!(receipt["section_id"], "S2");
    assert_eq!(receipt["section_index"], 1);
    assert_eq!(receipt["family_id"], "frame_3d");
    assert_eq!(receipt["parameter_set_version"], "1");
    assert_eq!(receipt["parameters_si"], section["parameters"]);
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

fn assert_rejected_frame_element_properties_edit(
    source: &Path,
    temporary: &Path,
    name: &str,
    element_id: &str,
    material_id: &str,
    section_id: &str,
    expected_code: &str,
) {
    let destination = temporary.join(name);
    let rejected = run_frame_element_properties_edit(
        source,
        &destination,
        element_id,
        material_id,
        section_id,
    );
    assert_eq!(
        rejected.status.code(),
        Some(1),
        "unexpected property edit status for {name}: stdout={} stderr={}",
        String::from_utf8_lossy(&rejected.stdout),
        String::from_utf8_lossy(&rejected.stderr)
    );
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
#[allow(clippy::too_many_lines)]
fn node_add_is_deterministic_fail_closed_composable_and_cpu_executable() {
    let temporary = TestDirectory::create();
    let source =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let source_bytes = std::fs::read(&source).expect("source ModelIR bytes");
    let source_validation = validate_model_bytes(&source_bytes).expect("C++-validated source");
    let source_model = &source_validation.snapshot;
    let first = temporary.0.join("node-add-first");
    let second = temporary.0.join("node-add-second");
    for destination in [&first, &second] {
        let output = run_node_add(&source, destination, "N3", ["4", "1", "0"]);
        assert_success(&output);
        let receipt = std::fs::read(destination.join("edit-receipt.json"))
            .expect("published node-add receipt");
        assert_eq!(output.stdout, [receipt.as_slice(), b"\n"].concat());
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(artifact)).expect("first node-add artifact"),
            std::fs::read(second.join(artifact)).expect("second node-add artifact")
        );
    }
    assert_eq!(
        std::fs::read(&source).expect("unchanged node-add source"),
        source_bytes
    );

    let added_bytes = std::fs::read(first.join("model-ir.json")).expect("node-added ModelIR");
    let added = parse_model_ir_v2(&added_bytes).expect("strict node-added ModelIR");
    let source_nodes = source_model.value()["nodes"]
        .as_array()
        .expect("source nodes");
    let added_nodes = added.value()["nodes"].as_array().expect("added nodes");
    assert_eq!(added_nodes.len(), source_nodes.len() + 1);
    assert_eq!(&added_nodes[..source_nodes.len()], source_nodes);
    assert_eq!(added_nodes[2]["id"], "N3");
    assert_eq!(added_nodes[2]["index"], 2);
    assert_eq!(
        added_nodes[2]["coordinates_m"],
        serde_json::json!([4, 1, 0])
    );
    assert_eq!(added_nodes[2]["source_id"], Value::Null);
    assert_eq!(added_nodes[2]["extensions"], serde_json::json!({}));
    for family in [
        "materials",
        "sections",
        "elements",
        "constraints",
        "load_patterns",
        "load_combinations",
        "time_functions",
        "construction_stages",
        "unsupported_features",
        "roundtrip_map",
    ] {
        assert_eq!(added.value()[family], source_model.value()[family]);
    }
    let extension = added.value()["extensions"]
        .get("structural-native:model-add-node.v1")
        .expect("node-add provenance extension");
    assert_eq!(extension["operation"], "node_add");
    assert_eq!(extension["node_id"], "N3");
    assert_eq!(extension["node_index"], 2);
    assert_eq!(extension["coordinates_m"], serde_json::json!([4, 1, 0]));
    assert_eq!(extension["source_id"], Value::Null);
    assert_eq!(
        added.value()["provenance"]["normalizer_id"],
        "structural-native-model-editor"
    );
    assert!(added.value()["provenance"]["extensions"]
        .get("structural-native:upstream-provenance")
        .is_some());

    let mut receipt: Value = serde_json::from_slice(
        &std::fs::read(first.join("edit-receipt.json")).expect("node-add receipt"),
    )
    .expect("node-add receipt JSON");
    assert_eq!(receipt["operation"], "node_add");
    assert_eq!(receipt["node_id"], "N3");
    assert_eq!(receipt["node_index"], 2);
    assert_eq!(receipt["coordinates_m"], serde_json::json!([4, 1, 0]));
    assert_eq!(receipt["source_id"], Value::Null);
    assert_eq!(receipt["cpp_semantic_snapshot_verified"], true);
    assert_eq!(receipt["analysis_ready"], true);
    assert_eq!(receipt["blocking_feature_ids"], serde_json::json!([]));
    assert_eq!(receipt["edited_content_hash"], added.content_hash());
    assert_ne!(
        receipt["source_semantic_hash"],
        receipt["edited_semantic_hash"]
    );
    assert_ne!(
        receipt["source_provenance_hash"],
        receipt["edited_provenance_hash"]
    );
    assert_self_hashed_edit_receipt(&mut receipt);

    for (name, node_id, coordinates, expected_code) in [
        (
            "duplicate-id",
            "N2",
            ["4", "1", "0"],
            "workbench_model_add_node_exists",
        ),
        (
            "duplicate-coordinate",
            "N3",
            ["2", "-0", "0"],
            "workbench_model_add_node_coordinate_exists",
        ),
    ] {
        let destination = temporary.0.join(name);
        let rejected = run_node_add(&source, &destination, node_id, coordinates);
        assert_eq!(rejected.status.code(), Some(1));
        assert!(
            String::from_utf8_lossy(&rejected.stdout).contains(expected_code),
            "{name} rejection: {}",
            String::from_utf8_lossy(&rejected.stdout)
        );
        assert!(!destination.exists());
    }
    let existing = run_node_add(&source, &first, "N3", ["4", "1", "0"]);
    assert_eq!(existing.status.code(), Some(1));
    assert!(
        String::from_utf8_lossy(&existing.stdout).contains("workbench_stage_destination_exists")
    );

    let mut index_drift = source_model.value().clone();
    index_drift["nodes"][1]["index"] = serde_json::json!(7);
    let index_drift_path = temporary.0.join("node-add-index-drift-source.json");
    std::fs::write(
        &index_drift_path,
        canonicalize_model_ir_v2(&index_drift)
            .expect("canonical node-index-drift source")
            .as_bytes(),
    )
    .expect("write node-index-drift source");
    let index_drift_destination = temporary.0.join("node-add-index-drift-output");
    let index_drift_rejection = run_node_add(
        &index_drift_path,
        &index_drift_destination,
        "N3",
        ["4", "1", "0"],
    );
    assert_eq!(index_drift_rejection.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&index_drift_rejection.stdout)
        .contains("workbench_model_edit_source_semantics_invalid"));
    assert!(!index_drift_destination.exists());

    let mut blocked = source_model.value().clone();
    blocked["unsupported_features"] = serde_json::json!([{
        "feature_id": "feature.node-add-visible-not-runnable",
        "kind": "unsupported_solver_feature",
        "source_entity_id": null,
        "disposition": "blocked",
        "blocking": true,
        "detail": "Node addition must preserve unsupported solver blockers.",
        "extensions": {}
    }]);
    blocked["roundtrip_map"] = serde_json::json!([{
        "source_entity_id": "source:N2",
        "entity_kind": "node",
        "model_ir_entity_id": "N2",
        "mapping_status": "exact",
        "extensions": {}
    }]);
    let blocked_source = temporary.0.join("blocked-node-add-source.json");
    std::fs::write(
        &blocked_source,
        canonicalize_model_ir_v2(&blocked)
            .expect("canonical blocked node-add source")
            .as_bytes(),
    )
    .expect("write blocked node-add source");
    let blocked_destination = temporary.0.join("blocked-node-add-output");
    assert_success(&run_node_add(
        &blocked_source,
        &blocked_destination,
        "N3",
        ["4", "1", "0"],
    ));
    let blocked_receipt: Value = serde_json::from_slice(
        &std::fs::read(blocked_destination.join("edit-receipt.json"))
            .expect("blocked node-add receipt"),
    )
    .expect("blocked node-add receipt JSON");
    assert_eq!(blocked_receipt["analysis_ready"], false);
    assert_eq!(
        blocked_receipt["blocking_feature_ids"],
        serde_json::json!(["feature.node-add-visible-not-runnable"])
    );
    let blocked_added: Value = serde_json::from_slice(
        &std::fs::read(blocked_destination.join("model-ir.json"))
            .expect("blocked node-added ModelIR"),
    )
    .expect("blocked node-added JSON");
    assert_eq!(blocked_added["roundtrip_map"], blocked["roundtrip_map"]);

    let supported = temporary.0.join("node-add-supported");
    assert_success(&run_fixed_constraint_add(
        &first.join("model-ir.json"),
        &supported,
        "BC_N3",
        "N3",
    ));
    let supported_bytes =
        std::fs::read(supported.join("model-ir.json")).expect("fixed node-added ModelIR");
    let request_directory = temporary.0.join("node-add-request");
    assert_success(&run_model_linear_request_create(
        &supported.join("model-ir.json"),
        &request_directory,
        "node-add-c5",
        "LC_WEAK",
    ));
    let request_bytes =
        std::fs::read(request_directory.join("analysis-request.json")).expect("node-add request");
    let direct = execute_model_ir_linear_analysis(&supported_bytes, &request_bytes, None, u32::MAX)
        .expect("node-add direct execution");
    assert!(direct.is_complete());
    let recovery: Value = serde_json::from_str(
        direct
            .result_recovery_ir_json()
            .expect("node-add direct recovery"),
    )
    .expect("node-add recovery JSON");
    assert_eq!(
        recovery["active_dof_indices"],
        serde_json::json!([6, 7, 8, 9, 10, 11])
    );
    assert_eq!(
        recovery["active_external_load"],
        serde_json::json!([0, -10000, 0, 0, 0, 0])
    );
    assert_eq!(recovery["recovery_stable_indices"], serde_json::json!([0]));
    assert_eq!(recovery["recovery_element_types"], serde_json::json!([1]));
    assert_eq!(recovery["recovery_offsets"], serde_json::json!([0, 12]));
    assert_eq!(recovery["fallback_count"], 0);
    let partial = execute_model_ir_linear_analysis(&supported_bytes, &request_bytes, None, 0)
        .expect("node-add initialized checkpoint");
    assert!(!partial.is_complete());
    let resumed = execute_model_ir_linear_analysis(
        &supported_bytes,
        &request_bytes,
        Some(partial.checkpoint_bytes()),
        u32::MAX,
    )
    .expect("node-add resumed execution");
    assert!(resumed.is_complete());
    assert_eq!(resumed.result_ir_json(), direct.result_ir_json());
    assert_eq!(
        resumed.result_recovery_ir_json(),
        direct.result_recovery_ir_json()
    );
}

#[test]
#[allow(clippy::too_many_lines)]
fn orphan_node_deletion_is_deterministic_fail_closed_restartable_and_cpu_executable() {
    let temporary = TestDirectory::create();
    let source =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let source_bytes = std::fs::read(&source).expect("source ModelIR bytes");
    let source_validation = validate_model_bytes(&source_bytes).expect("C++-validated source");
    let source_model = &source_validation.snapshot;
    let added = temporary.0.join("orphan-node-added");
    assert_success(&run_node_add(&source, &added, "N3", ["4", "1", "0"]));
    let added_path = added.join("model-ir.json");
    let added_bytes = std::fs::read(&added_path).expect("node-added source bytes");
    let added_model = parse_model_ir_v2(&added_bytes).expect("strict node-added source");

    let first = temporary.0.join("orphan-node-delete-first");
    let second = temporary.0.join("orphan-node-delete-second");
    for destination in [&first, &second] {
        let output = run_orphan_node_delete(&added_path, destination, "N3");
        assert_success(&output);
        let receipt = std::fs::read(destination.join("edit-receipt.json"))
            .expect("published orphan-node-delete receipt");
        assert_eq!(output.stdout, [receipt.as_slice(), b"\n"].concat());
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(artifact)).expect("first deletion artifact"),
            std::fs::read(second.join(artifact)).expect("second deletion artifact")
        );
    }
    assert_eq!(
        std::fs::read(&added_path).expect("unchanged node-added source"),
        added_bytes
    );

    let deleted_bytes = std::fs::read(first.join("model-ir.json")).expect("node-deleted ModelIR");
    let deleted = parse_model_ir_v2(&deleted_bytes).expect("strict node-deleted ModelIR");
    assert_eq!(deleted.value()["nodes"], source_model.value()["nodes"]);
    for family in [
        "materials",
        "sections",
        "elements",
        "constraints",
        "load_patterns",
        "load_combinations",
        "time_functions",
        "construction_stages",
        "unsupported_features",
        "roundtrip_map",
    ] {
        assert_eq!(deleted.value()[family], added_model.value()[family]);
    }
    let extension = deleted.value()["extensions"]
        .get("structural-native:model-delete-orphan-node.v1")
        .expect("orphan-node-delete provenance extension");
    assert_eq!(extension["operation"], "orphan_node_delete");
    assert_eq!(extension["removed_node_id"], "N3");
    assert_eq!(extension["removed_node_index"], 2);
    assert_eq!(
        extension["removed_coordinates_m"],
        serde_json::json!([4, 1, 0])
    );
    assert_eq!(extension["removed_source_id"], Value::Null);
    assert_eq!(extension["removed_extensions"], serde_json::json!({}));
    assert!(deleted.value()["extensions"]
        .get("structural-native:model-add-node.v1")
        .is_some());
    assert_eq!(
        deleted.value()["provenance"]["normalizer_id"],
        "structural-native-model-editor"
    );

    let mut receipt: Value = serde_json::from_slice(
        &std::fs::read(first.join("edit-receipt.json")).expect("orphan-node-delete receipt"),
    )
    .expect("orphan-node-delete receipt JSON");
    assert_eq!(receipt["operation"], "orphan_node_delete");
    assert_eq!(receipt["removed_node_id"], "N3");
    assert_eq!(receipt["removed_node_index"], 2);
    assert_eq!(
        receipt["removed_coordinates_m"],
        serde_json::json!([4, 1, 0])
    );
    assert_eq!(receipt["removed_source_id"], Value::Null);
    assert_eq!(receipt["removed_extensions"], serde_json::json!({}));
    assert_eq!(receipt["cpp_semantic_snapshot_verified"], true);
    assert_eq!(receipt["analysis_ready"], true);
    assert_eq!(receipt["blocking_feature_ids"], serde_json::json!([]));
    assert_eq!(receipt["edited_content_hash"], deleted.content_hash());
    assert_ne!(
        receipt["source_semantic_hash"],
        receipt["edited_semantic_hash"]
    );
    assert_ne!(
        receipt["source_provenance_hash"],
        receipt["edited_provenance_hash"]
    );
    assert_self_hashed_edit_receipt(&mut receipt);

    for (name, node_id, expected_code) in [
        (
            "missing",
            "N404",
            "workbench_model_delete_orphan_node_missing",
        ),
        (
            "nonterminal",
            "N2",
            "workbench_model_delete_orphan_node_not_terminal",
        ),
    ] {
        let destination = temporary.0.join(format!("orphan-node-{name}-rejected"));
        let rejected = run_orphan_node_delete(&added_path, &destination, node_id);
        assert_eq!(rejected.status.code(), Some(1));
        assert!(String::from_utf8_lossy(&rejected.stdout).contains(expected_code));
        assert!(!destination.exists());
    }
    let minimum_destination = temporary.0.join("orphan-node-minimum-rejected");
    let minimum = run_orphan_node_delete(&source, &minimum_destination, "N2");
    assert_eq!(minimum.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&minimum.stdout)
        .contains("workbench_model_delete_orphan_node_minimum_topology"));
    assert!(!minimum_destination.exists());
    let existing = run_orphan_node_delete(&added_path, &first, "N3");
    assert_eq!(existing.status.code(), Some(1));
    assert!(
        String::from_utf8_lossy(&existing.stdout).contains("workbench_stage_destination_exists")
    );

    for (name, mutate, expected_code) in [
        (
            "source-owned",
            0_u8,
            "workbench_model_delete_orphan_node_source_owned",
        ),
        (
            "extended",
            1_u8,
            "workbench_model_delete_orphan_node_extensions_unsupported",
        ),
        (
            "unsupported-owned",
            2_u8,
            "workbench_model_delete_orphan_node_unsupported_feature_owned",
        ),
        (
            "roundtrip-owned",
            3_u8,
            "workbench_model_delete_orphan_node_roundtrip_owned",
        ),
    ] {
        let mut guarded = added_model.value().clone();
        match mutate {
            0 => guarded["nodes"][2]["source_id"] = serde_json::json!("source:N3"),
            1 => {
                guarded["nodes"][2]["extensions"] =
                    serde_json::json!({"external:owner": "external"});
            }
            2 => {
                guarded["unsupported_features"] = serde_json::json!([{
                    "feature_id": "feature.orphan-node-owned",
                    "kind": "unsupported_topology",
                    "source_entity_id": "N3",
                    "disposition": "blocked",
                    "blocking": true,
                    "detail": "Target node is owned by unsupported source topology.",
                    "extensions": {}
                }]);
            }
            3 => {
                guarded["roundtrip_map"] = serde_json::json!([{
                    "source_entity_id": "source:N3",
                    "entity_kind": "node",
                    "model_ir_entity_id": "N3",
                    "mapping_status": "exact",
                    "extensions": {}
                }]);
            }
            _ => unreachable!(),
        }
        let guarded_path = temporary.0.join(format!("orphan-node-{name}-source.json"));
        std::fs::write(
            &guarded_path,
            canonicalize_model_ir_v2(&guarded)
                .expect("canonical guarded orphan-node source")
                .as_bytes(),
        )
        .expect("write guarded orphan-node source");
        let destination = temporary.0.join(format!("orphan-node-{name}-output"));
        let rejected = run_orphan_node_delete(&guarded_path, &destination, "N3");
        assert_eq!(rejected.status.code(), Some(1));
        assert!(
            String::from_utf8_lossy(&rejected.stdout).contains(expected_code),
            "{name} rejection: {}",
            String::from_utf8_lossy(&rejected.stdout)
        );
        assert!(!destination.exists());
    }

    let element_source = temporary.0.join("orphan-node-element-source");
    assert_success(&run_element_connectivity_edit(
        &added_path,
        &element_source,
        "E1",
        ["N1", "N3"],
    ));
    let element_destination = temporary.0.join("orphan-node-element-rejected");
    let element_rejected = run_orphan_node_delete(
        &element_source.join("model-ir.json"),
        &element_destination,
        "N3",
    );
    assert_eq!(element_rejected.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&element_rejected.stdout)
        .contains("workbench_model_delete_orphan_node_referenced_by_element"));
    assert!(!element_destination.exists());

    let constraint_source = temporary.0.join("orphan-node-constraint-source");
    assert_success(&run_fixed_constraint_add(
        &added_path,
        &constraint_source,
        "BC_N3",
        "N3",
    ));
    let constraint_destination = temporary.0.join("orphan-node-constraint-rejected");
    let constraint_rejected = run_orphan_node_delete(
        &constraint_source.join("model-ir.json"),
        &constraint_destination,
        "N3",
    );
    assert_eq!(constraint_rejected.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&constraint_rejected.stdout)
        .contains("workbench_model_delete_orphan_node_referenced_by_constraint"));
    assert!(!constraint_destination.exists());

    let load_source = temporary.0.join("orphan-node-load-source");
    assert_success(&run_nodal_load_add(
        &added_path,
        &load_source,
        "LC_WEAK",
        "L_WEAK_N3",
        "N3",
        ["0", "-1", "0", "0", "0", "0"],
    ));
    let load_destination = temporary.0.join("orphan-node-load-rejected");
    let load_rejected =
        run_orphan_node_delete(&load_source.join("model-ir.json"), &load_destination, "N3");
    assert_eq!(load_rejected.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&load_rejected.stdout)
        .contains("workbench_model_delete_orphan_node_referenced_by_load"));
    assert!(!load_destination.exists());

    let mut blocked = added_model.value().clone();
    blocked["unsupported_features"] = serde_json::json!([{
        "feature_id": "feature.orphan-node-delete-visible-not-runnable",
        "kind": "unsupported_solver_feature",
        "source_entity_id": null,
        "disposition": "blocked",
        "blocking": true,
        "detail": "Orphan-node deletion must preserve unrelated blockers.",
        "extensions": {}
    }]);
    blocked["roundtrip_map"] = serde_json::json!([{
        "source_entity_id": "source:N2",
        "entity_kind": "node",
        "model_ir_entity_id": "N2",
        "mapping_status": "exact",
        "extensions": {}
    }]);
    let blocked_source = temporary.0.join("orphan-node-blocked-source.json");
    std::fs::write(
        &blocked_source,
        canonicalize_model_ir_v2(&blocked)
            .expect("canonical blocked orphan-node source")
            .as_bytes(),
    )
    .expect("write blocked orphan-node source");
    let blocked_destination = temporary.0.join("orphan-node-blocked-output");
    assert_success(&run_orphan_node_delete(
        &blocked_source,
        &blocked_destination,
        "N3",
    ));
    let blocked_receipt: Value = serde_json::from_slice(
        &std::fs::read(blocked_destination.join("edit-receipt.json"))
            .expect("blocked orphan-node-delete receipt"),
    )
    .expect("blocked orphan-node-delete receipt JSON");
    assert_eq!(blocked_receipt["analysis_ready"], false);
    assert_eq!(
        blocked_receipt["blocking_feature_ids"],
        serde_json::json!(["feature.orphan-node-delete-visible-not-runnable"])
    );
    let blocked_deleted: Value = serde_json::from_slice(
        &std::fs::read(blocked_destination.join("model-ir.json"))
            .expect("blocked node-deleted ModelIR"),
    )
    .expect("blocked node-deleted JSON");
    assert_eq!(blocked_deleted["roundtrip_map"], blocked["roundtrip_map"]);

    let request_directory = temporary.0.join("orphan-node-delete-request");
    assert_success(&run_model_linear_request_create(
        &first.join("model-ir.json"),
        &request_directory,
        "orphan-node-delete-c5",
        "LC_WEAK",
    ));
    let request_bytes = std::fs::read(request_directory.join("analysis-request.json"))
        .expect("orphan-node-delete request");
    let direct = execute_model_ir_linear_analysis(&deleted_bytes, &request_bytes, None, u32::MAX)
        .expect("orphan-node-delete direct execution");
    assert!(direct.is_complete());
    let recovery: Value = serde_json::from_str(
        direct
            .result_recovery_ir_json()
            .expect("orphan-node-delete recovery"),
    )
    .expect("orphan-node-delete recovery JSON");
    assert_eq!(
        recovery["active_dof_indices"],
        serde_json::json!([6, 7, 8, 9, 10, 11])
    );
    assert_eq!(
        recovery["active_external_load"],
        serde_json::json!([0, -10000, 0, 0, 0, 0])
    );
    assert_eq!(recovery["recovery_stable_indices"], serde_json::json!([0]));
    assert_eq!(recovery["recovery_element_types"], serde_json::json!([1]));
    assert_eq!(recovery["recovery_offsets"], serde_json::json!([0, 12]));
    assert_eq!(recovery["fallback_count"], 0);
    let partial = execute_model_ir_linear_analysis(&deleted_bytes, &request_bytes, None, 0)
        .expect("orphan-node-delete initialized checkpoint");
    assert!(!partial.is_complete());
    let resumed = execute_model_ir_linear_analysis(
        &deleted_bytes,
        &request_bytes,
        Some(partial.checkpoint_bytes()),
        u32::MAX,
    )
    .expect("orphan-node-delete resumed execution");
    assert!(resumed.is_complete());
    assert_eq!(resumed.result_ir_json(), direct.result_ir_json());
    assert_eq!(
        resumed.result_recovery_ir_json(),
        direct.result_recovery_ir_json()
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
fn frame_element_properties_edit_is_deterministic_executable_and_fail_closed() {
    let temporary = TestDirectory::create();
    let source =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let source_before = std::fs::read(&source).expect("source ModelIR bytes");

    let material_add = temporary.0.join("property-edit-material-add");
    assert_success(&run_linear_material_add(
        &source,
        &material_add,
        "M2",
        ["100000000000", "0.3", "2700"],
    ));
    let section_add = temporary.0.join("property-edit-section-add");
    assert_success(&run_frame_section_add(
        &material_add.join("model-ir.json"),
        &section_add,
        "S2",
        ["0.01", "0.00004", "0.000025", "0.000005", "0.008", "0.008"],
    ));
    let composed_source = section_add.join("model-ir.json");
    let composed_source_before =
        std::fs::read(&composed_source).expect("composed property-edit source bytes");

    let first = temporary.0.join("frame-element-properties-edit-first");
    let second = temporary.0.join("frame-element-properties-edit-second");
    for destination in [&first, &second] {
        let output =
            run_frame_element_properties_edit(&composed_source, destination, "E1", "M2", "S2");
        assert_success(&output);
        let receipt_bytes = std::fs::read(destination.join("edit-receipt.json"))
            .expect("frame-element property edit receipt");
        assert_eq!(output.stdout, [receipt_bytes.as_slice(), b"\n"].concat());
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(artifact)).expect("first property-edit artifact"),
            std::fs::read(second.join(artifact)).expect("second property-edit artifact")
        );
    }
    assert_eq!(
        std::fs::read(&source).expect("source after property edit"),
        source_before
    );
    assert_eq!(
        std::fs::read(&composed_source).expect("composed source after property edit"),
        composed_source_before
    );
    assert_published_frame_element_properties_edit(&first);

    let material_only = temporary.0.join("frame-element-material-only-edit");
    assert_success(&run_frame_element_properties_edit(
        &composed_source,
        &material_only,
        "E1",
        "M2",
        "S1",
    ));
    let material_only_receipt: Value = serde_json::from_slice(
        &std::fs::read(material_only.join("edit-receipt.json"))
            .expect("material-only assignment receipt"),
    )
    .expect("material-only assignment receipt JSON");
    assert_eq!(material_only_receipt["previous_material_id"], "M1");
    assert_eq!(material_only_receipt["edited_material_id"], "M2");
    assert_eq!(material_only_receipt["previous_section_id"], "S1");
    assert_eq!(material_only_receipt["edited_section_id"], "S1");

    let section_only = temporary.0.join("frame-element-section-only-edit");
    assert_success(&run_frame_element_properties_edit(
        &composed_source,
        &section_only,
        "E1",
        "M1",
        "S2",
    ));
    let section_only_model: Value = serde_json::from_slice(
        &std::fs::read(section_only.join("model-ir.json")).expect("section-only assigned model"),
    )
    .expect("section-only assigned model JSON");
    assert_eq!(section_only_model["elements"][0]["material_id"], "M1");
    assert_eq!(section_only_model["elements"][0]["section_id"], "S2");

    let baseline_request = temporary.0.join("property-edit-baseline-request");
    let edited_request = temporary.0.join("property-edit-request");
    assert_success(&run_model_linear_request_create(
        &source,
        &baseline_request,
        "frame-element-properties-c5",
        "LC_WEAK",
    ));
    assert_success(&run_model_linear_request_create(
        &first.join("model-ir.json"),
        &edited_request,
        "frame-element-properties-c5",
        "LC_WEAK",
    ));
    let baseline = execute_model_ir_linear_analysis(
        &source_before,
        &std::fs::read(baseline_request.join("analysis-request.json"))
            .expect("baseline property request"),
        None,
        u32::MAX,
    )
    .expect("baseline property execution");
    let edited = execute_model_ir_linear_analysis(
        &std::fs::read(first.join("model-ir.json")).expect("property-edited model"),
        &std::fs::read(edited_request.join("analysis-request.json"))
            .expect("property-edited request"),
        None,
        u32::MAX,
    )
    .expect("property-edited execution");
    assert!(baseline.is_complete());
    assert!(
        edited.is_complete(),
        "receipt={}",
        edited.run_receipt_json()
    );
    let baseline_recovery: Value = serde_json::from_str(
        baseline
            .result_recovery_ir_json()
            .expect("baseline property recovery"),
    )
    .expect("baseline property recovery JSON");
    let edited_recovery: Value = serde_json::from_str(
        edited
            .result_recovery_ir_json()
            .expect("edited property recovery"),
    )
    .expect("edited property recovery JSON");
    assert_eq!(
        edited_recovery["active_dof_indices"],
        serde_json::json!([6, 7, 8, 9, 10, 11])
    );
    assert_eq!(
        edited_recovery["active_external_load"],
        serde_json::json!([0, -10000, 0, 0, 0, 0])
    );
    assert_eq!(
        baseline_recovery["active_external_load"],
        edited_recovery["active_external_load"]
    );
    assert_ne!(
        baseline_recovery["global_displacement"],
        edited_recovery["global_displacement"]
    );
    assert_eq!(edited_recovery["fallback_count"], 0);

    let existing = run_frame_element_properties_edit(&composed_source, &first, "E1", "M2", "S2");
    assert_eq!(existing.status.code(), Some(1));
    assert!(
        String::from_utf8_lossy(&existing.stdout).contains("workbench_stage_destination_exists")
    );
    for (name, element, material, section, code) in [
        (
            "property-edit-element-missing",
            "MISSING",
            "M2",
            "S2",
            "workbench_model_edit_element_missing",
        ),
        (
            "property-edit-material-missing",
            "E1",
            "MISSING",
            "S2",
            "workbench_model_edit_frame_element_material_missing",
        ),
        (
            "property-edit-section-missing",
            "E1",
            "M2",
            "MISSING",
            "workbench_model_edit_frame_element_section_missing",
        ),
        (
            "property-edit-no-op",
            "E1",
            "M1",
            "S1",
            "workbench_model_edit_no_change",
        ),
    ] {
        assert_rejected_frame_element_properties_edit(
            &composed_source,
            &temporary.0,
            name,
            element,
            material,
            section,
            code,
        );
    }
    let wrong_type = repository_root().join("examples/bounded_planar_frame_alpha.model-ir.v2.json");
    assert_rejected_frame_element_properties_edit(
        &wrong_type,
        &temporary.0,
        "property-edit-wrong-element-type",
        "E1",
        "steel",
        "RC1",
        "workbench_model_edit_element_type_unsupported",
    );
    let nonlinear =
        repository_root().join("examples/bounded_frame3d_direct_control.model-ir.v2.json");
    assert_rejected_frame_element_properties_edit(
        &nonlinear,
        &temporary.0,
        "property-edit-incompatible-material",
        "E1",
        "S1",
        "SEC1",
        "workbench_model_edit_frame_element_material_unsupported",
    );

    let mut invalid_source: Value = serde_json::from_slice(&composed_source_before)
        .expect("property-edit source JSON for invalid source");
    invalid_source["elements"][0]["node_ids"][1] = Value::String("MISSING".to_owned());
    let invalid_source_path = temporary.0.join("invalid-property-edit-source.json");
    std::fs::write(
        &invalid_source_path,
        serde_json::to_vec(&invalid_source).expect("invalid property-edit source bytes"),
    )
    .expect("write invalid property-edit source");
    assert_rejected_frame_element_properties_edit(
        &invalid_source_path,
        &temporary.0,
        "property-edit-invalid-source",
        "E1",
        "M2",
        "S2",
        "workbench_model_edit_source_semantics_invalid",
    );

    let mut blocked: Value = serde_json::from_slice(&composed_source_before)
        .expect("property-edit source JSON for blocker preservation");
    blocked["unsupported_features"] = serde_json::json!([{
        "feature_id": "feature.element-property-edit-visible-not-runnable",
        "kind": "unsupported_solver_feature",
        "source_entity_id": null,
        "disposition": "blocked",
        "blocking": true,
        "detail": "Element property assignment must not promote unsupported solver authority.",
        "extensions": {}
    }]);
    blocked["roundtrip_map"] = serde_json::json!([
        {
            "source_entity_id": "source:E1",
            "entity_kind": "element",
            "model_ir_entity_id": "E1",
            "mapping_status": "exact",
            "extensions": {}
        },
        {
            "source_entity_id": "source:S2",
            "entity_kind": "section",
            "model_ir_entity_id": "S2",
            "mapping_status": "exact",
            "extensions": {}
        }
    ]);
    let blocked_source = temporary.0.join("blocked-property-edit-source.json");
    std::fs::write(
        &blocked_source,
        serde_json::to_vec(&blocked).expect("blocked property-edit source bytes"),
    )
    .expect("write blocked property-edit source");
    let blocked_destination = temporary.0.join("blocked-property-edit");
    assert_success(&run_frame_element_properties_edit(
        &blocked_source,
        &blocked_destination,
        "E1",
        "M2",
        "S2",
    ));
    let blocked_receipt: Value = serde_json::from_slice(
        &std::fs::read(blocked_destination.join("edit-receipt.json"))
            .expect("blocked property-edit receipt"),
    )
    .expect("blocked property-edit receipt JSON");
    assert_eq!(blocked_receipt["analysis_ready"], false);
    assert_eq!(
        blocked_receipt["blocking_feature_ids"],
        serde_json::json!(["feature.element-property-edit-visible-not-runnable"])
    );
    let blocked_edited: Value = serde_json::from_slice(
        &std::fs::read(blocked_destination.join("model-ir.json"))
            .expect("blocked property-edited model"),
    )
    .expect("blocked property-edited JSON");
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
fn nodal_load_deletion_is_deterministic_fail_closed_restartable_and_cpu_executable() {
    let temporary = TestDirectory::create();
    let source =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let member_directory = temporary.0.join("load-delete-member-source");
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
    let load_directory = temporary.0.join("load-delete-source");
    assert_success(&run_nodal_load_add(
        &member_directory.join("model-ir.json"),
        &load_directory,
        "LC_WEAK",
        "L_WEAK_N3",
        "N3",
        ["0", "-1000", "0", "0", "0", "0"],
    ));
    let load_path = load_directory.join("model-ir.json");
    let load_bytes = std::fs::read(&load_path).expect("nodal-load delete source bytes");
    let load_model = parse_model_ir_v2(&load_bytes).expect("strict nodal-load delete source");

    let first = temporary.0.join("nodal-load-delete-first");
    let second = temporary.0.join("nodal-load-delete-second");
    for destination in [&first, &second] {
        let output = run_nodal_load_delete(&load_path, destination, "LC_WEAK", "L_WEAK_N3");
        assert_success(&output);
        let receipt = std::fs::read(destination.join("edit-receipt.json"))
            .expect("nodal-load delete receipt");
        assert_eq!(output.stdout, [receipt.as_slice(), b"\n"].concat());
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(artifact)).expect("first nodal-load delete artifact"),
            std::fs::read(second.join(artifact)).expect("second nodal-load delete artifact")
        );
    }
    assert_eq!(
        std::fs::read(&load_path).expect("unchanged nodal-load delete source"),
        load_bytes
    );

    let deleted_bytes =
        std::fs::read(first.join("model-ir.json")).expect("nodal-load-deleted ModelIR");
    let deleted = parse_model_ir_v2(&deleted_bytes).expect("strict nodal-load-deleted ModelIR");
    for family in [
        "nodes",
        "materials",
        "sections",
        "elements",
        "constraints",
        "load_combinations",
        "time_functions",
        "construction_stages",
    ] {
        assert_eq!(deleted.value()[family], load_model.value()[family]);
    }
    let source_patterns = load_model.value()["load_patterns"]
        .as_array()
        .expect("source load patterns");
    let deleted_patterns = deleted.value()["load_patterns"]
        .as_array()
        .expect("deleted load patterns");
    assert_eq!(source_patterns.len(), deleted_patterns.len());
    for (source_pattern, deleted_pattern) in source_patterns.iter().zip(deleted_patterns) {
        if source_pattern["id"] == "LC_WEAK" {
            assert_eq!(deleted_pattern["analysis_type"], "linear_static");
            assert_eq!(
                deleted_pattern["nodal_loads"].as_array().map(Vec::len),
                Some(1)
            );
            assert_eq!(
                deleted_pattern["nodal_loads"][0],
                source_pattern["nodal_loads"][0]
            );
        } else {
            assert_eq!(deleted_pattern, source_pattern);
        }
    }
    let extension = deleted.value()["extensions"]
        .get("structural-native:model-delete-nodal-load.v1")
        .expect("nodal-load delete provenance extension");
    assert_eq!(extension["operation"], "nodal_load_delete");
    assert_eq!(extension["load_pattern_id"], "LC_WEAK");
    assert_eq!(extension["load_pattern_index"], 1);
    assert_eq!(extension["removed_nodal_load_id"], "L_WEAK_N3");
    assert_eq!(extension["removed_nodal_load_index"], 1);
    assert_eq!(extension["removed_node_id"], "N3");
    assert_eq!(
        extension["removed_components_si"],
        serde_json::json!({"FX": 0, "FY": -1000, "FZ": 0, "MX": 0, "MY": 0, "MZ": 0})
    );
    let mut receipt: Value = serde_json::from_slice(
        &std::fs::read(first.join("edit-receipt.json")).expect("nodal-load delete receipt"),
    )
    .expect("nodal-load delete receipt JSON");
    assert_eq!(receipt["operation"], "nodal_load_delete");
    assert_eq!(receipt["load_pattern_id"], "LC_WEAK");
    assert_eq!(receipt["removed_nodal_load_id"], "L_WEAK_N3");
    assert_eq!(receipt["cpp_semantic_snapshot_verified"], true);
    assert_eq!(receipt["analysis_ready"], true);
    assert_eq!(receipt["edited_content_hash"], deleted.content_hash());
    assert_self_hashed_edit_receipt(&mut receipt);

    let request_directory = temporary.0.join("nodal-load-delete-request");
    assert_success(&run_model_linear_request_create(
        &first.join("model-ir.json"),
        &request_directory,
        "nodal-load-delete-c5",
        "LC_WEAK",
    ));
    let request_bytes = std::fs::read(request_directory.join("analysis-request.json"))
        .expect("nodal-load delete request");
    let direct = execute_model_ir_linear_analysis(&deleted_bytes, &request_bytes, None, u32::MAX)
        .expect("nodal-load delete direct execution");
    assert!(direct.is_complete());
    let recovery: Value = serde_json::from_str(
        direct
            .result_recovery_ir_json()
            .expect("nodal-load delete direct recovery"),
    )
    .expect("nodal-load delete recovery JSON");
    assert_eq!(
        recovery["active_dof_indices"],
        serde_json::json!([6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17])
    );
    assert_eq!(
        recovery["active_external_load"],
        serde_json::json!([0, -10000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
    );
    assert_eq!(
        recovery["recovery_stable_indices"],
        serde_json::json!([0, 1])
    );
    assert_eq!(
        recovery["recovery_element_types"],
        serde_json::json!([1, 1])
    );
    assert_eq!(recovery["recovery_offsets"], serde_json::json!([0, 12, 24]));
    assert_eq!(recovery["fallback_count"], 0);
    let partial = execute_model_ir_linear_analysis(&deleted_bytes, &request_bytes, None, 1)
        .expect("nodal-load delete partial execution");
    assert!(!partial.is_complete());
    let resumed = execute_model_ir_linear_analysis(
        &deleted_bytes,
        &request_bytes,
        Some(partial.checkpoint_bytes()),
        u32::MAX,
    )
    .expect("nodal-load delete resumed execution");
    assert!(resumed.is_complete());
    assert_eq!(resumed.result_ir_json(), direct.result_ir_json());
    assert_eq!(
        resumed.result_recovery_ir_json(),
        direct.result_recovery_ir_json()
    );

    let nonterminal_destination = temporary.0.join("nodal-load-delete-nonterminal");
    let nonterminal =
        run_nodal_load_delete(&load_path, &nonterminal_destination, "LC_WEAK", "L_WEAK_N2");
    assert_eq!(nonterminal.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&nonterminal.stdout)
        .contains("workbench_model_delete_nodal_load_not_terminal"));
    assert!(!nonterminal_destination.exists());

    let mut source_owned = load_model.value().clone();
    source_owned["load_patterns"][1]["nodal_loads"][1]["source_id"] =
        serde_json::json!("native:test:L_WEAK_N3");
    let source_owned_path = temporary.0.join("nodal-load-delete-source-owned.json");
    std::fs::write(
        &source_owned_path,
        canonicalize_model_ir_v2(&source_owned)
            .expect("canonical source-owned nodal load")
            .as_bytes(),
    )
    .expect("write source-owned nodal load");
    let source_owned_destination = temporary.0.join("nodal-load-delete-source-owned");
    let source_owned_rejection = run_nodal_load_delete(
        &source_owned_path,
        &source_owned_destination,
        "LC_WEAK",
        "L_WEAK_N3",
    );
    assert_eq!(source_owned_rejection.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&source_owned_rejection.stdout)
        .contains("workbench_model_delete_nodal_load_source_owned"));
    assert!(!source_owned_destination.exists());

    let minimum_destination = temporary.0.join("nodal-load-delete-minimum");
    let minimum = run_nodal_load_delete(
        &member_directory.join("model-ir.json"),
        &minimum_destination,
        "LC_WEAK",
        "L_WEAK_N2",
    );
    assert_eq!(minimum.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&minimum.stdout)
        .contains("workbench_model_delete_nodal_load_minimum_pattern"));
    assert!(!minimum_destination.exists());

    let existing = run_nodal_load_delete(&load_path, &first, "LC_WEAK", "L_WEAK_N3");
    assert_eq!(existing.status.code(), Some(1));
    assert!(
        String::from_utf8_lossy(&existing.stdout).contains("workbench_stage_destination_exists")
    );

    let mut blocked = load_model.value().clone();
    blocked["unsupported_features"] = serde_json::json!([{
        "feature_id": "feature.nodal-load-delete-visible-not-runnable",
        "kind": "unsupported_solver_feature",
        "source_entity_id": null,
        "disposition": "blocked",
        "blocking": true,
        "detail": "Nodal-load deletion must preserve unsupported solver blockers.",
        "extensions": {}
    }]);
    blocked["roundtrip_map"] = serde_json::json!([{
        "source_entity_id": "source:LC_WEAK",
        "entity_kind": "load_pattern",
        "model_ir_entity_id": "LC_WEAK",
        "mapping_status": "exact",
        "extensions": {}
    }]);
    let blocked_source = temporary.0.join("blocked-nodal-load-delete-source.json");
    std::fs::write(
        &blocked_source,
        canonicalize_model_ir_v2(&blocked)
            .expect("canonical blocked nodal-load delete")
            .as_bytes(),
    )
    .expect("write blocked nodal-load delete source");
    let blocked_destination = temporary.0.join("blocked-nodal-load-delete-output");
    assert_success(&run_nodal_load_delete(
        &blocked_source,
        &blocked_destination,
        "LC_WEAK",
        "L_WEAK_N3",
    ));
    let blocked_receipt: Value = serde_json::from_slice(
        &std::fs::read(blocked_destination.join("edit-receipt.json"))
            .expect("blocked nodal-load delete receipt"),
    )
    .expect("blocked nodal-load delete receipt JSON");
    assert_eq!(blocked_receipt["analysis_ready"], false);
    assert_eq!(
        blocked_receipt["blocking_feature_ids"],
        serde_json::json!(["feature.nodal-load-delete-visible-not-runnable"])
    );
    let blocked_edited: Value = serde_json::from_slice(
        &std::fs::read(blocked_destination.join("model-ir.json"))
            .expect("blocked nodal-load-deleted ModelIR"),
    )
    .expect("blocked nodal-load-deleted JSON");
    assert_eq!(
        blocked_edited["roundtrip_map"][0]["mapping_status"],
        "approximated"
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
fn fixed_constraint_deletion_is_deterministic_fail_closed_restartable_and_cpu_executable() {
    let temporary = TestDirectory::create();
    let source =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let member_directory = temporary.0.join("constraint-delete-member-source");
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
    let load_directory = temporary.0.join("constraint-delete-load-source");
    assert_success(&run_nodal_load_add(
        &member_directory.join("model-ir.json"),
        &load_directory,
        "LC_WEAK",
        "L_WEAK_N3",
        "N3",
        ["0", "-1000", "0", "0", "0", "0"],
    ));
    let fixed_directory = temporary.0.join("constraint-delete-fixed-source");
    assert_success(&run_fixed_constraint_add(
        &load_directory.join("model-ir.json"),
        &fixed_directory,
        "BC_N3",
        "N3",
    ));
    let fixed_path = fixed_directory.join("model-ir.json");
    let fixed_bytes = std::fs::read(&fixed_path).expect("fixed constraint delete source bytes");
    let fixed_model = parse_model_ir_v2(&fixed_bytes).expect("strict fixed constraint source");

    let first = temporary.0.join("fixed-constraint-delete-first");
    let second = temporary.0.join("fixed-constraint-delete-second");
    for destination in [&first, &second] {
        let output = run_fixed_constraint_delete(&fixed_path, destination, "BC_N3");
        assert_success(&output);
        let receipt = std::fs::read(destination.join("edit-receipt.json"))
            .expect("fixed constraint delete receipt");
        assert_eq!(output.stdout, [receipt.as_slice(), b"\n"].concat());
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(artifact)).expect("first constraint delete artifact"),
            std::fs::read(second.join(artifact)).expect("second constraint delete artifact")
        );
    }
    assert_eq!(
        std::fs::read(&fixed_path).expect("unchanged fixed constraint delete source"),
        fixed_bytes
    );

    let deleted_bytes =
        std::fs::read(first.join("model-ir.json")).expect("deleted fixed constraint ModelIR");
    let deleted = parse_model_ir_v2(&deleted_bytes).expect("strict constraint-deleted ModelIR");
    assert_eq!(
        deleted.value()["constraints"]
            .as_array()
            .expect("constraints")
            .len(),
        1
    );
    assert_eq!(deleted.value()["constraints"][0]["id"], "BC1");
    for family in [
        "nodes",
        "materials",
        "sections",
        "elements",
        "load_patterns",
        "roundtrip_map",
    ] {
        assert_eq!(deleted.value()[family], fixed_model.value()[family]);
    }
    let extension = deleted.value()["extensions"]
        .get("structural-native:model-delete-fixed-constraint.v1")
        .expect("fixed constraint delete provenance extension");
    assert_eq!(extension["operation"], "fixed_constraint_delete");
    assert_eq!(extension["removed_constraint_id"], "BC_N3");
    assert_eq!(extension["removed_constraint_index"], 1);
    assert_eq!(extension["removed_constraint_type"], "fixed_dofs");
    assert_eq!(extension["removed_node_id"], "N3");
    assert_eq!(
        extension["removed_dofs"],
        serde_json::json!(["UX", "UY", "UZ", "RX", "RY", "RZ"])
    );
    assert_eq!(
        extension["removed_prescribed_values_si"],
        serde_json::json!({"UX": 0, "UY": 0, "UZ": 0, "RX": 0, "RY": 0, "RZ": 0})
    );
    let mut receipt: Value = serde_json::from_slice(
        &std::fs::read(first.join("edit-receipt.json")).expect("fixed constraint delete receipt"),
    )
    .expect("fixed constraint delete receipt JSON");
    assert_eq!(receipt["operation"], "fixed_constraint_delete");
    assert_eq!(receipt["removed_constraint_id"], "BC_N3");
    assert_eq!(receipt["cpp_semantic_snapshot_verified"], true);
    assert_eq!(receipt["analysis_ready"], true);
    assert_eq!(receipt["edited_content_hash"], deleted.content_hash());
    assert_self_hashed_edit_receipt(&mut receipt);

    let request_directory = temporary.0.join("fixed-constraint-delete-request");
    assert_success(&run_model_linear_request_create(
        &first.join("model-ir.json"),
        &request_directory,
        "fixed-constraint-delete-c5",
        "LC_WEAK",
    ));
    let request_bytes = std::fs::read(request_directory.join("analysis-request.json"))
        .expect("fixed constraint delete request");
    let direct = execute_model_ir_linear_analysis(&deleted_bytes, &request_bytes, None, u32::MAX)
        .expect("fixed constraint delete direct execution");
    assert!(direct.is_complete());
    let recovery: Value = serde_json::from_str(
        direct
            .result_recovery_ir_json()
            .expect("fixed constraint delete direct recovery"),
    )
    .expect("fixed constraint delete recovery JSON");
    assert_eq!(
        recovery["active_dof_indices"],
        serde_json::json!([6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17])
    );
    assert_eq!(
        recovery["active_external_load"],
        serde_json::json!([0, -10000, 0, 0, 0, 0, 0, -1000, 0, 0, 0, 0])
    );
    assert_eq!(
        recovery["recovery_stable_indices"],
        serde_json::json!([0, 1])
    );
    assert_eq!(
        recovery["recovery_element_types"],
        serde_json::json!([1, 1])
    );
    assert_eq!(recovery["recovery_offsets"], serde_json::json!([0, 12, 24]));
    assert_eq!(recovery["fallback_count"], 0);
    let partial = execute_model_ir_linear_analysis(&deleted_bytes, &request_bytes, None, 1)
        .expect("fixed constraint delete partial execution");
    assert!(!partial.is_complete());
    let resumed = execute_model_ir_linear_analysis(
        &deleted_bytes,
        &request_bytes,
        Some(partial.checkpoint_bytes()),
        u32::MAX,
    )
    .expect("fixed constraint delete resumed execution");
    assert!(resumed.is_complete());
    assert_eq!(resumed.result_ir_json(), direct.result_ir_json());
    assert_eq!(
        resumed.result_recovery_ir_json(),
        direct.result_recovery_ir_json()
    );

    let nonterminal_destination = temporary.0.join("fixed-constraint-delete-nonterminal");
    let nonterminal = run_fixed_constraint_delete(&fixed_path, &nonterminal_destination, "BC1");
    assert_eq!(nonterminal.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&nonterminal.stdout)
        .contains("workbench_model_delete_fixed_constraint_not_terminal"));
    assert!(!nonterminal_destination.exists());

    let mut source_owned = fixed_model.value().clone();
    source_owned["constraints"][1]["source_id"] = serde_json::json!("native:test:BC_N3");
    let source_owned_path = temporary
        .0
        .join("fixed-constraint-delete-source-owned.json");
    std::fs::write(
        &source_owned_path,
        canonicalize_model_ir_v2(&source_owned)
            .expect("canonical source-owned fixed constraint")
            .as_bytes(),
    )
    .expect("write source-owned fixed constraint");
    let source_owned_destination = temporary.0.join("fixed-constraint-delete-source-owned");
    let source_owned_rejection =
        run_fixed_constraint_delete(&source_owned_path, &source_owned_destination, "BC_N3");
    assert_eq!(source_owned_rejection.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&source_owned_rejection.stdout)
        .contains("workbench_model_delete_fixed_constraint_source_owned"));
    assert!(!source_owned_destination.exists());

    let existing = run_fixed_constraint_delete(&fixed_path, &first, "BC_N3");
    assert_eq!(existing.status.code(), Some(1));
    assert!(
        String::from_utf8_lossy(&existing.stdout).contains("workbench_stage_destination_exists")
    );

    let mut blocked = fixed_model.value().clone();
    blocked["unsupported_features"] = serde_json::json!([{
        "feature_id": "feature.fixed-constraint-delete-visible-not-runnable",
        "kind": "unsupported_solver_feature",
        "source_entity_id": null,
        "disposition": "blocked",
        "blocking": true,
        "detail": "Fixed constraint deletion must preserve unsupported solver blockers.",
        "extensions": {}
    }]);
    let blocked_source = temporary
        .0
        .join("blocked-fixed-constraint-delete-source.json");
    std::fs::write(
        &blocked_source,
        canonicalize_model_ir_v2(&blocked)
            .expect("canonical blocked fixed constraint delete")
            .as_bytes(),
    )
    .expect("write blocked fixed constraint delete source");
    let blocked_destination = temporary.0.join("blocked-fixed-constraint-delete-output");
    assert_success(&run_fixed_constraint_delete(
        &blocked_source,
        &blocked_destination,
        "BC_N3",
    ));
    let blocked_receipt: Value = serde_json::from_slice(
        &std::fs::read(blocked_destination.join("edit-receipt.json"))
            .expect("blocked fixed constraint delete receipt"),
    )
    .expect("blocked fixed constraint delete receipt JSON");
    assert_eq!(blocked_receipt["analysis_ready"], false);
    assert_eq!(
        blocked_receipt["blocking_feature_ids"],
        serde_json::json!(["feature.fixed-constraint-delete-visible-not-runnable"])
    );
}

#[test]
#[allow(clippy::too_many_lines)]
fn linear_load_pattern_add_is_atomic_deterministic_cpp_revalidated_and_executable() {
    let temporary = TestDirectory::create();
    let source =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let member_directory = temporary.0.join("pattern-add-member-source");
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
    let load_directory = temporary.0.join("pattern-add-load-source");
    assert_success(&run_nodal_load_add(
        &member_directory.join("model-ir.json"),
        &load_directory,
        "LC_WEAK",
        "L_WEAK_N3",
        "N3",
        ["0", "-1000", "0", "0", "0", "0"],
    ));
    let constraint_directory = temporary.0.join("pattern-add-constraint-source");
    assert_success(&run_fixed_constraint_add(
        &load_directory.join("model-ir.json"),
        &constraint_directory,
        "BC_N3",
        "N3",
    ));
    let constrained_source = constraint_directory.join("model-ir.json");
    let constrained_source_before =
        std::fs::read(&constrained_source).expect("constrained source bytes");

    let first = temporary.0.join("linear-load-pattern-add-first");
    let second = temporary.0.join("linear-load-pattern-add-second");
    for destination in [&first, &second] {
        let output = run_linear_load_pattern_add(
            &constrained_source,
            destination,
            "LC_CUSTOM",
            "L_CUSTOM_N2",
            "N2",
            ["2500", "0", "0", "0", "0", "0"],
        );
        assert_success(&output);
        let receipt_bytes = std::fs::read(destination.join("edit-receipt.json"))
            .expect("linear-load-pattern add receipt");
        assert_eq!(output.stdout, [receipt_bytes.as_slice(), b"\n"].concat());
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(artifact)).expect("first pattern-add artifact"),
            std::fs::read(second.join(artifact)).expect("second pattern-add artifact")
        );
    }
    assert_eq!(
        std::fs::read(&constrained_source).expect("source after pattern addition"),
        constrained_source_before
    );
    assert_published_linear_load_pattern_add(&first);

    let view = run_workbench(&[text("model-view"), first.join("model-ir.json").as_os_str()]);
    assert_success(&view);
    assert!(String::from_utf8_lossy(&view.stdout).contains("load_patterns=5"));

    let baseline_request_directory = temporary.0.join("pattern-add-baseline-request");
    let custom_request_directory = temporary.0.join("pattern-add-custom-request");
    assert_success(&run_model_linear_request_create(
        &constrained_source,
        &baseline_request_directory,
        "added-linear-load-pattern-c5",
        "LC_WEAK",
    ));
    assert_success(&run_model_linear_request_create(
        &first.join("model-ir.json"),
        &custom_request_directory,
        "added-linear-load-pattern-c5",
        "LC_CUSTOM",
    ));
    let baseline = execute_model_ir_linear_analysis(
        &constrained_source_before,
        &std::fs::read(baseline_request_directory.join("analysis-request.json"))
            .expect("baseline request"),
        None,
        u32::MAX,
    )
    .expect("baseline constrained-model execution");
    let custom_model = std::fs::read(first.join("model-ir.json")).expect("pattern-added model");
    let custom = execute_model_ir_linear_analysis(
        &custom_model,
        &std::fs::read(custom_request_directory.join("analysis-request.json"))
            .expect("custom-pattern request"),
        None,
        u32::MAX,
    )
    .expect("custom-pattern native linear execution");
    assert!(baseline.is_complete());
    assert!(custom.is_complete());
    let baseline_recovery: Value = serde_json::from_str(
        baseline
            .result_recovery_ir_json()
            .expect("baseline result recovery"),
    )
    .expect("baseline recovery JSON");
    let custom_recovery: Value = serde_json::from_str(
        custom
            .result_recovery_ir_json()
            .expect("custom-pattern result recovery"),
    )
    .expect("custom-pattern recovery JSON");
    assert_eq!(
        custom_recovery["active_dof_indices"],
        serde_json::json!([6, 7, 8, 9, 10, 11])
    );
    assert_eq!(
        custom_recovery["active_external_load"],
        serde_json::json!([2500, 0, 0, 0, 0, 0])
    );
    assert_ne!(
        baseline_recovery["global_displacement"],
        custom_recovery["global_displacement"]
    );
    assert_eq!(custom_recovery["fallback_count"], 0);

    let existing = run_linear_load_pattern_add(
        &constrained_source,
        &first,
        "LC_CUSTOM",
        "L_CUSTOM_N2",
        "N2",
        ["2500", "0", "0", "0", "0", "0"],
    );
    assert_eq!(existing.status.code(), Some(1));
    assert!(
        String::from_utf8_lossy(&existing.stdout).contains("workbench_stage_destination_exists")
    );

    for (name, pattern, load, node, components, code) in [
        (
            "pattern-add-duplicate-pattern",
            "LC_WEAK",
            "L_CUSTOM_N2",
            "N2",
            ["2500", "0", "0", "0", "0", "0"],
            "workbench_model_add_linear_load_pattern_identity_exists",
        ),
        (
            "pattern-add-duplicate-load",
            "LC_CUSTOM",
            "L_AXIAL_N2",
            "N2",
            ["2500", "0", "0", "0", "0", "0"],
            "workbench_model_add_linear_load_pattern_load_identity_exists",
        ),
        (
            "pattern-add-missing-node",
            "LC_CUSTOM",
            "L_CUSTOM_N2",
            "MISSING",
            ["2500", "0", "0", "0", "0", "0"],
            "workbench_model_add_linear_load_pattern_node_missing",
        ),
        (
            "pattern-add-zero",
            "LC_CUSTOM",
            "L_CUSTOM_N2",
            "N2",
            ["0", "0", "0", "0", "0", "0"],
            "workbench_usage_error",
        ),
    ] {
        let destination = temporary.0.join(name);
        let rejected = run_linear_load_pattern_add(
            &constrained_source,
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
        serde_json::from_slice(&constrained_source_before).expect("pattern source JSON");
    blocked["unsupported_features"] = serde_json::json!([{
        "feature_id": "feature.linear-load-pattern-add-visible-not-runnable",
        "kind": "unsupported_solver_feature",
        "source_entity_id": null,
        "disposition": "blocked",
        "blocking": true,
        "detail": "Load-pattern authoring must not promote unsupported solver authority.",
        "extensions": {}
    }]);
    let original_roundtrip_map = blocked["roundtrip_map"].clone();
    let blocked_source = temporary.0.join("blocked-pattern-add-source.json");
    std::fs::write(
        &blocked_source,
        serde_json::to_vec(&blocked).expect("blocked pattern-add source bytes"),
    )
    .expect("write blocked pattern-add source");
    let blocked_destination = temporary.0.join("blocked-pattern-add");
    assert_success(&run_linear_load_pattern_add(
        &blocked_source,
        &blocked_destination,
        "LC_CUSTOM",
        "L_CUSTOM_N2",
        "N2",
        ["2500", "0", "0", "0", "0", "0"],
    ));
    let blocked_receipt: Value = serde_json::from_slice(
        &std::fs::read(blocked_destination.join("edit-receipt.json"))
            .expect("blocked pattern-add receipt"),
    )
    .expect("blocked pattern-add receipt JSON");
    assert_eq!(blocked_receipt["analysis_ready"], false);
    assert_eq!(
        blocked_receipt["blocking_feature_ids"],
        serde_json::json!(["feature.linear-load-pattern-add-visible-not-runnable"])
    );
    let blocked_edited: Value = serde_json::from_slice(
        &std::fs::read(blocked_destination.join("model-ir.json"))
            .expect("blocked pattern-added model"),
    )
    .expect("blocked pattern-added JSON");
    assert_eq!(blocked_edited["roundtrip_map"], original_roundtrip_map);
}

#[test]
#[allow(clippy::too_many_lines)]
fn linear_load_combination_add_is_deterministic_cpp_revalidated_and_cpu_executable() {
    let temporary = TestDirectory::create();
    let source =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let source_bytes = std::fs::read(&source).expect("load-combination source bytes");
    let source_validation =
        validate_model_bytes(&source_bytes).expect("C++-validated load-combination source");
    let source_model = &source_validation.snapshot;

    let first = temporary.0.join("linear-load-combination-add-first");
    let second = temporary.0.join("linear-load-combination-add-second");
    for destination in [&first, &second] {
        let output = run_linear_load_combination_add(
            &source,
            destination,
            "COMBO_SERVICE",
            ["LC_WEAK", "1.2"],
            ["LC_STRONG", "-0.5"],
        );
        assert_success(&output);
        let receipt = std::fs::read(destination.join("edit-receipt.json"))
            .expect("linear-load-combination add receipt");
        assert_eq!(output.stdout, [receipt.as_slice(), b"\n"].concat());
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(artifact)).expect("first combination-add artifact"),
            std::fs::read(second.join(artifact)).expect("second combination-add artifact")
        );
    }
    assert_eq!(
        std::fs::read(&source).expect("unchanged combination-add source"),
        source_bytes
    );

    let edited_bytes =
        std::fs::read(first.join("model-ir.json")).expect("combination-added ModelIR");
    let edited = parse_model_ir_v2(&edited_bytes).expect("strict combination-added ModelIR");
    let validation = validate_model_bytes(&edited_bytes).expect("C++-validated combination model");
    assert!(validation.report.contract_valid);
    assert!(validation.report.semantics_valid);
    assert!(validation.report.analysis_ready);
    assert_eq!(validation.report.entity_counts.load_combinations, 1);
    for family in [
        "nodes",
        "materials",
        "sections",
        "elements",
        "constraints",
        "load_patterns",
        "time_functions",
        "construction_stages",
        "unsupported_features",
        "roundtrip_map",
    ] {
        assert_eq!(edited.value()[family], source_model.value()[family]);
    }
    assert_eq!(
        edited.value()["load_combinations"],
        serde_json::json!([{
            "id": "COMBO_SERVICE",
            "index": 0,
            "combination_type": "linear",
            "terms": [
                {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": 1.2},
                {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": -0.5}
            ],
            "source_id": null,
            "extensions": {}
        }])
    );
    let extension = edited.value()["extensions"]
        .get("structural-native:model-add-linear-load-combination.v1")
        .expect("load-combination provenance extension");
    assert_eq!(extension["operation"], "linear_load_combination_add");
    assert_eq!(extension["load_combination_id"], "COMBO_SERVICE");
    assert_eq!(extension["load_combination_index"], 0);
    assert_eq!(
        extension["terms"],
        edited.value()["load_combinations"][0]["terms"]
    );

    let mut receipt: Value = serde_json::from_slice(
        &std::fs::read(first.join("edit-receipt.json")).expect("linear-load-combination receipt"),
    )
    .expect("linear-load-combination receipt JSON");
    assert_eq!(receipt["operation"], "linear_load_combination_add");
    assert_eq!(receipt["load_combination_id"], "COMBO_SERVICE");
    assert_eq!(receipt["load_combination_index"], 0);
    assert_eq!(receipt["combination_type"], "linear");
    assert_eq!(
        receipt["terms"],
        edited.value()["load_combinations"][0]["terms"]
    );
    assert_eq!(receipt["cpp_semantic_snapshot_verified"], true);
    assert_eq!(receipt["analysis_ready"], true);
    assert_eq!(receipt["blocking_feature_ids"], serde_json::json!([]));
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

    let view = run_workbench(&[text("model-view"), first.join("model-ir.json").as_os_str()]);
    assert_success(&view);
    assert!(String::from_utf8_lossy(&view.stdout).contains("C++ semantic snapshot: verified"));

    let direct_pattern_request = temporary.0.join("combination-adjacent-pattern-request");
    assert_success(&run_model_linear_request_create(
        &first.join("model-ir.json"),
        &direct_pattern_request,
        "linear-pattern-beside-combination",
        "LC_WEAK",
    ));

    let combination_request = temporary.0.join("combination-solver-request");
    let preflight = run_model_linear_combination_request_create(
        &first.join("model-ir.json"),
        &combination_request,
        "linear-combination-c5",
        "COMBO_SERVICE",
    );
    assert_success(&preflight);
    let request_receipt_bytes = std::fs::read(combination_request.join("request-receipt.json"))
        .expect("combination request receipt");
    assert_eq!(
        preflight.stdout,
        [request_receipt_bytes.as_slice(), b"\n"].concat()
    );
    let mut request_receipt: Value =
        serde_json::from_slice(&request_receipt_bytes).expect("combination request receipt JSON");
    assert_eq!(
        request_receipt["schema_version"],
        "structural-native-model-linear-combination-request-create-receipt.v1"
    );
    assert_eq!(request_receipt["load_selector_kind"], "load_combination");
    assert_eq!(request_receipt["load_combination_id"], "COMBO_SERVICE");
    assert_eq!(
        request_receipt["frozen_request_selector_field"],
        "load_pattern_id"
    );
    assert_eq!(
        request_receipt["cpp_linear_assembly_preflight_verified"],
        true
    );
    assert_self_hashed_edit_receipt(&mut request_receipt);

    let combination_request_bytes =
        std::fs::read(combination_request.join("analysis-request.json"))
            .expect("combination analysis request");
    let direct =
        execute_model_ir_linear_analysis(&edited_bytes, &combination_request_bytes, None, u32::MAX)
            .expect("combination direct CPU execution");
    assert!(direct.is_complete());
    let recovery: Value = serde_json::from_str(
        direct
            .result_recovery_ir_json()
            .expect("combination direct recovery"),
    )
    .expect("combination recovery JSON");
    assert_eq!(recovery["load_pattern_id"], "COMBO_SERVICE");
    assert_eq!(recovery["load_pattern_index"], 0);
    assert_eq!(
        recovery["active_external_load"],
        serde_json::json!([0, -12000, 5000, 0, 0, 0])
    );
    assert_eq!(recovery["fallback_count"], 0);
    let partial =
        execute_model_ir_linear_analysis(&edited_bytes, &combination_request_bytes, None, 0)
            .expect("combination initial checkpoint");
    assert!(!partial.is_complete());
    let resumed = execute_model_ir_linear_analysis(
        &edited_bytes,
        &combination_request_bytes,
        Some(partial.checkpoint_bytes()),
        u32::MAX,
    )
    .expect("combination resumed CPU execution");
    assert!(resumed.is_complete());
    assert_eq!(resumed.result_ir_json(), direct.result_ir_json());
    assert_eq!(
        resumed.result_recovery_ir_json(),
        direct.result_recovery_ir_json()
    );

    let append_second = temporary.0.join("linear-load-combination-add-next-index");
    assert_success(&run_linear_load_combination_add(
        &first.join("model-ir.json"),
        &append_second,
        "COMBO_STRENGTH",
        ["LC_AXIAL", "1.4"],
        ["LC_TORSION", "0.7"],
    ));
    let appended: Value = serde_json::from_slice(
        &std::fs::read(append_second.join("model-ir.json")).expect("second combination model"),
    )
    .expect("second combination JSON");
    assert_eq!(appended["load_combinations"][1]["index"], 1);
    assert_eq!(appended["load_combinations"][1]["id"], "COMBO_STRENGTH");

    for (name, combination, first_term, second_term, expected_status, expected_code) in [
        (
            "duplicate-combination",
            "COMBO_SERVICE",
            ["LC_AXIAL", "1"],
            ["LC_TORSION", "1"],
            1,
            "workbench_model_add_linear_load_combination_identity_exists",
        ),
        (
            "missing-pattern",
            "COMBO_MISSING",
            ["LC_WEAK", "1"],
            ["LC_MISSING", "1"],
            1,
            "workbench_model_add_linear_load_combination_pattern_missing",
        ),
        (
            "duplicate-pattern",
            "COMBO_DUPLICATE",
            ["LC_WEAK", "1"],
            ["LC_WEAK", "2"],
            2,
            "workbench_usage_error",
        ),
        (
            "zero-factor",
            "COMBO_ZERO",
            ["LC_WEAK", "0"],
            ["LC_STRONG", "1"],
            2,
            "workbench_usage_error",
        ),
        (
            "nonfinite-factor",
            "COMBO_NONFINITE",
            ["LC_WEAK", "NaN"],
            ["LC_STRONG", "1"],
            2,
            "workbench_usage_error",
        ),
    ] {
        let destination = temporary.0.join(format!("combination-{name}-rejected"));
        let input = if name == "duplicate-combination" {
            first.join("model-ir.json")
        } else {
            source.clone()
        };
        let rejected = run_linear_load_combination_add(
            &input,
            &destination,
            combination,
            first_term,
            second_term,
        );
        assert_eq!(rejected.status.code(), Some(expected_status));
        assert!(
            String::from_utf8_lossy(&rejected.stdout).contains(expected_code),
            "{name} rejection: {}",
            String::from_utf8_lossy(&rejected.stdout)
        );
        assert!(!destination.exists());
    }

    let existing_destination = run_linear_load_combination_add(
        &source,
        &first,
        "COMBO_OTHER",
        ["LC_AXIAL", "1"],
        ["LC_TORSION", "1"],
    );
    assert_eq!(existing_destination.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&existing_destination.stdout)
        .contains("workbench_stage_destination_exists"));

    let mut blocked = source_model.value().clone();
    blocked["unsupported_features"] = serde_json::json!([{
        "feature_id": "feature.linear-load-combination-visible-not-runnable",
        "kind": "unsupported_solver_feature",
        "source_entity_id": null,
        "disposition": "blocked",
        "blocking": true,
        "detail": "Combination authoring must preserve unrelated analysis blockers.",
        "extensions": {}
    }]);
    let original_roundtrip_map = blocked["roundtrip_map"].clone();
    let blocked_source = temporary.0.join("blocked-combination-add-source.json");
    std::fs::write(
        &blocked_source,
        canonicalize_model_ir_v2(&blocked)
            .expect("canonical blocked combination source")
            .as_bytes(),
    )
    .expect("write blocked combination source");
    let blocked_destination = temporary.0.join("blocked-combination-add");
    assert_success(&run_linear_load_combination_add(
        &blocked_source,
        &blocked_destination,
        "COMBO_SERVICE",
        ["LC_WEAK", "1.2"],
        ["LC_STRONG", "-0.5"],
    ));
    let blocked_receipt: Value = serde_json::from_slice(
        &std::fs::read(blocked_destination.join("edit-receipt.json"))
            .expect("blocked combination-add receipt"),
    )
    .expect("blocked combination-add receipt JSON");
    assert_eq!(blocked_receipt["analysis_ready"], false);
    assert_eq!(
        blocked_receipt["blocking_feature_ids"],
        serde_json::json!(["feature.linear-load-combination-visible-not-runnable"])
    );
    let blocked_edited: Value = serde_json::from_slice(
        &std::fs::read(blocked_destination.join("model-ir.json"))
            .expect("blocked combination-added model"),
    )
    .expect("blocked combination-added JSON");
    assert_eq!(blocked_edited["roundtrip_map"], original_roundtrip_map);
}

#[test]
#[allow(clippy::too_many_lines)]
fn direct_three_pattern_linear_load_combination_executes_and_restarts_without_fallback() {
    let temporary = TestDirectory::create();
    let source =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let terms = [
        ["LC_AXIAL", "0.25"],
        ["LC_WEAK", "1.2"],
        ["LC_STRONG", "-0.5"],
    ];
    let first = temporary.0.join("direct-combination-add-first");
    let second = temporary.0.join("direct-combination-add-second");
    for destination in [&first, &second] {
        assert_success(&run_direct_linear_load_combination_add(
            &source,
            destination,
            "COMBO_DIRECT",
            &terms,
        ));
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(artifact)).expect("first direct-combination artifact"),
            std::fs::read(second.join(artifact)).expect("second direct-combination artifact")
        );
    }

    let edited_bytes =
        std::fs::read(first.join("model-ir.json")).expect("direct-combination ModelIR");
    let edited = parse_model_ir_v2(&edited_bytes).expect("strict direct-combination ModelIR");
    let validation =
        validate_model_bytes(&edited_bytes).expect("C++-validated direct-combination ModelIR");
    assert!(validation.report.analysis_ready);
    assert_eq!(
        edited.value()["load_combinations"][0]["terms"],
        serde_json::json!([
            {"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 0.25},
            {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": 1.2},
            {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": -0.5}
        ])
    );
    let extension = edited.value()["extensions"]
        .get("structural-native:model-add-direct-linear-load-combination.v2")
        .expect("direct-combination provenance extension");
    assert_eq!(extension["operation"], "direct_linear_load_combination_add");
    assert_eq!(
        extension["authoring_profile"],
        "unique_direct_linear_static_patterns_2_to_64"
    );
    assert_eq!(extension["term_count"], 3);

    let mut edit_receipt: Value = serde_json::from_slice(
        &std::fs::read(first.join("edit-receipt.json")).expect("direct-combination edit receipt"),
    )
    .expect("direct-combination edit receipt JSON");
    assert_eq!(
        edit_receipt["operation"],
        "direct_linear_load_combination_add"
    );
    assert_eq!(
        edit_receipt["authoring_profile"],
        "unique_direct_linear_static_patterns_2_to_64"
    );
    assert_eq!(edit_receipt["term_count"], 3);
    assert_self_hashed_edit_receipt(&mut edit_receipt);

    let request_directory = temporary.0.join("direct-combination-request");
    let preflight = run_model_linear_combination_request_create(
        &first.join("model-ir.json"),
        &request_directory,
        "direct-combination-c5",
        "COMBO_DIRECT",
    );
    assert_success(&preflight);
    let request_bytes = std::fs::read(request_directory.join("analysis-request.json"))
        .expect("direct-combination request");
    let mut request_receipt: Value = serde_json::from_slice(
        &std::fs::read(request_directory.join("request-receipt.json"))
            .expect("direct-combination request receipt"),
    )
    .expect("direct-combination request receipt JSON");
    assert_eq!(
        request_receipt["schema_version"],
        "structural-native-model-linear-direct-combination-request-create-receipt.v2"
    );
    assert_eq!(request_receipt["combination_term_count"], 3);
    assert_eq!(
        request_receipt["request_profile"],
        "unique_direct_linear_static_patterns_2_to_64"
    );
    assert_self_hashed_edit_receipt(&mut request_receipt);

    let direct = execute_model_ir_linear_analysis(&edited_bytes, &request_bytes, None, u32::MAX)
        .expect("three-pattern direct CPU execution");
    assert!(direct.is_complete());
    let recovery: Value = serde_json::from_str(
        direct
            .result_recovery_ir_json()
            .expect("three-pattern direct recovery"),
    )
    .expect("three-pattern recovery JSON");
    assert_eq!(recovery["load_pattern_id"], "COMBO_DIRECT");
    assert_eq!(
        recovery["active_external_load"],
        serde_json::json!([25000, -12000, 5000, 0, 0, 0])
    );
    assert_eq!(recovery["fallback_count"], 0);

    let partial = execute_model_ir_linear_analysis(&edited_bytes, &request_bytes, None, 0)
        .expect("three-pattern initial checkpoint");
    assert!(!partial.is_complete());
    let resumed = execute_model_ir_linear_analysis(
        &edited_bytes,
        &request_bytes,
        Some(partial.checkpoint_bytes()),
        u32::MAX,
    )
    .expect("three-pattern resumed CPU execution");
    assert!(resumed.is_complete());
    assert_eq!(resumed.result_ir_json(), direct.result_ir_json());
    assert_eq!(
        resumed.result_recovery_ir_json(),
        direct.result_recovery_ir_json()
    );

    let delete_first = temporary.0.join("direct-combination-delete-first");
    let delete_second = temporary.0.join("direct-combination-delete-second");
    for destination in [&delete_first, &delete_second] {
        assert_success(&run_linear_load_combination_delete(
            &first.join("model-ir.json"),
            destination,
            "COMBO_DIRECT",
        ));
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(delete_first.join(artifact)).expect("first direct-deletion artifact"),
            std::fs::read(delete_second.join(artifact)).expect("second direct-deletion artifact")
        );
    }
    let deleted_bytes =
        std::fs::read(delete_first.join("model-ir.json")).expect("direct-deleted ModelIR");
    let deleted = parse_model_ir_v2(&deleted_bytes).expect("strict direct-deleted ModelIR");
    assert_eq!(deleted.value()["load_combinations"], serde_json::json!([]));
    let delete_extension = deleted.value()["extensions"]
        .get("structural-native:model-delete-direct-linear-load-combination.v2")
        .expect("direct-combination delete provenance extension");
    assert_eq!(
        delete_extension["operation"],
        "direct_linear_load_combination_delete"
    );
    assert_eq!(
        delete_extension["deletion_profile"],
        "unique_direct_linear_static_patterns_2_to_64"
    );
    assert_eq!(delete_extension["term_count"], 3);
    assert_eq!(
        delete_extension["removed_terms"],
        edited.value()["load_combinations"][0]["terms"]
    );
    let mut delete_receipt: Value = serde_json::from_slice(
        &std::fs::read(delete_first.join("edit-receipt.json"))
            .expect("direct-combination delete receipt"),
    )
    .expect("direct-combination delete receipt JSON");
    assert_eq!(
        delete_receipt["operation"],
        "direct_linear_load_combination_delete"
    );
    assert_eq!(delete_receipt["term_count"], 3);
    assert_eq!(
        delete_receipt["deletion_profile"],
        "unique_direct_linear_static_patterns_2_to_64"
    );
    assert_self_hashed_edit_receipt(&mut delete_receipt);

    let deleted_request_directory = temporary.0.join("direct-combination-delete-request");
    assert_success(&run_model_linear_request_create(
        &delete_first.join("model-ir.json"),
        &deleted_request_directory,
        "direct-combination-delete-c5",
        "LC_WEAK",
    ));
    let deleted_request = std::fs::read(deleted_request_directory.join("analysis-request.json"))
        .expect("direct-combination delete request");
    let deleted_direct =
        execute_model_ir_linear_analysis(&deleted_bytes, &deleted_request, None, u32::MAX)
            .expect("direct-combination deletion CPU execution");
    assert!(deleted_direct.is_complete());
    let deleted_recovery: Value = serde_json::from_str(
        deleted_direct
            .result_recovery_ir_json()
            .expect("direct-combination deletion recovery"),
    )
    .expect("direct-combination deletion recovery JSON");
    assert_eq!(
        deleted_recovery["active_external_load"],
        serde_json::json!([0, -10000, 0, 0, 0, 0])
    );
    assert_eq!(deleted_recovery["fallback_count"], 0);
}

#[test]
#[allow(clippy::too_many_lines)]
fn direct_linear_load_combination_factor_edit_executes_and_restarts_without_fallback() {
    let temporary = TestDirectory::create();
    let source =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let authored = temporary.0.join("factor-edit-authored");
    assert_success(&run_direct_linear_load_combination_add(
        &source,
        &authored,
        "COMBO_DIRECT",
        &[
            ["LC_AXIAL", "0.25"],
            ["LC_WEAK", "1.2"],
            ["LC_STRONG", "-0.5"],
        ],
    ));
    let authored_path = authored.join("model-ir.json");
    let authored_bytes = std::fs::read(&authored_path).expect("authored direct ModelIR");
    let first = temporary.0.join("factor-edit-first");
    let second = temporary.0.join("factor-edit-second");
    for destination in [&first, &second] {
        assert_success(&run_direct_linear_load_combination_factor_edit(
            &authored_path,
            destination,
            "COMBO_DIRECT",
            "LC_WEAK",
            "1.35",
        ));
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(artifact)).expect("first factor-edit artifact"),
            std::fs::read(second.join(artifact)).expect("second factor-edit artifact")
        );
    }
    assert_eq!(
        std::fs::read(&authored_path).expect("unchanged factor-edit source"),
        authored_bytes
    );

    let edited_bytes = std::fs::read(first.join("model-ir.json")).expect("factor-edited ModelIR");
    let edited = parse_model_ir_v2(&edited_bytes).expect("strict factor-edited ModelIR");
    let validation = validate_model_bytes(&edited_bytes).expect("C++-validated factor edit");
    assert!(validation.report.analysis_ready);
    assert_eq!(
        edited.value()["load_combinations"][0]["terms"],
        serde_json::json!([
            {"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 0.25},
            {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": 1.35},
            {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": -0.5}
        ])
    );
    let extension = edited.value()["extensions"]
        .get("structural-native:model-edit-direct-linear-load-combination-factor.v1")
        .expect("direct factor-edit provenance extension");
    assert_eq!(
        extension["operation"],
        "direct_linear_load_combination_factor_edit"
    );
    assert_eq!(
        extension["editing_profile"],
        "unique_direct_linear_static_patterns_2_to_64"
    );
    assert_eq!(extension["load_combination_index"], 0);
    assert_eq!(extension["term_index"], 1);
    assert_eq!(extension["term_count"], 3);
    assert_eq!(extension["previous_factor"], 1.2);
    assert_eq!(extension["edited_factor"], 1.35);

    let mut edit_receipt: Value = serde_json::from_slice(
        &std::fs::read(first.join("edit-receipt.json")).expect("factor-edit receipt"),
    )
    .expect("factor-edit receipt JSON");
    assert_eq!(
        edit_receipt["operation"],
        "direct_linear_load_combination_factor_edit"
    );
    assert_eq!(edit_receipt["term_index"], 1);
    assert_eq!(edit_receipt["term_count"], 3);
    assert_eq!(edit_receipt["previous_factor"], 1.2);
    assert_eq!(edit_receipt["edited_factor"], 1.35);
    assert_eq!(edit_receipt["cpp_semantic_snapshot_verified"], true);
    assert_self_hashed_edit_receipt(&mut edit_receipt);

    let request_directory = temporary.0.join("factor-edit-request");
    assert_success(&run_model_linear_combination_request_create(
        &first.join("model-ir.json"),
        &request_directory,
        "factor-edit-c5",
        "COMBO_DIRECT",
    ));
    let request_bytes = std::fs::read(request_directory.join("analysis-request.json"))
        .expect("factor-edit request");
    let direct = execute_model_ir_linear_analysis(&edited_bytes, &request_bytes, None, u32::MAX)
        .expect("factor-edited direct CPU execution");
    assert!(direct.is_complete());
    let recovery: Value = serde_json::from_str(
        direct
            .result_recovery_ir_json()
            .expect("factor-edit recovery"),
    )
    .expect("factor-edit recovery JSON");
    assert_eq!(recovery["load_pattern_id"], "COMBO_DIRECT");
    assert_eq!(
        recovery["active_external_load"],
        serde_json::json!([25000, -13500, 5000, 0, 0, 0])
    );
    assert_eq!(recovery["fallback_count"], 0);

    let partial = execute_model_ir_linear_analysis(&edited_bytes, &request_bytes, None, 0)
        .expect("factor-edit initial checkpoint");
    assert!(!partial.is_complete());
    let resumed = execute_model_ir_linear_analysis(
        &edited_bytes,
        &request_bytes,
        Some(partial.checkpoint_bytes()),
        u32::MAX,
    )
    .expect("factor-edit resumed CPU execution");
    assert!(resumed.is_complete());
    assert_eq!(resumed.result_ir_json(), direct.result_ir_json());
    assert_eq!(
        resumed.result_recovery_ir_json(),
        direct.result_recovery_ir_json()
    );

    let no_change = temporary.0.join("factor-edit-no-change");
    let rejected = run_direct_linear_load_combination_factor_edit(
        &authored_path,
        &no_change,
        "COMBO_DIRECT",
        "LC_WEAK",
        "1.2",
    );
    assert!(!rejected.status.success());
    assert!(!no_change.exists());
}

#[test]
#[allow(clippy::too_many_lines)]
fn direct_linear_load_combination_term_add_executes_and_restarts_without_fallback() {
    let temporary = TestDirectory::create();
    let source =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let authored = temporary.0.join("term-add-authored");
    assert_success(&run_linear_load_combination_add(
        &source,
        &authored,
        "COMBO_SERVICE",
        ["LC_WEAK", "1.2"],
        ["LC_STRONG", "-0.5"],
    ));
    let authored_path = authored.join("model-ir.json");
    let authored_bytes = std::fs::read(&authored_path).expect("term-add source ModelIR");
    let first = temporary.0.join("term-add-first");
    let second = temporary.0.join("term-add-second");
    for destination in [&first, &second] {
        let output = run_direct_linear_load_combination_term_add(
            &authored_path,
            destination,
            "COMBO_SERVICE",
            "LC_AXIAL",
            "0.25",
        );
        assert_success(&output);
        let receipt =
            std::fs::read(destination.join("edit-receipt.json")).expect("term-add receipt");
        assert_eq!(output.stdout, [receipt.as_slice(), b"\n"].concat());
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(artifact)).expect("first term-add artifact"),
            std::fs::read(second.join(artifact)).expect("second term-add artifact")
        );
    }
    assert_eq!(
        std::fs::read(&authored_path).expect("unchanged term-add source"),
        authored_bytes
    );

    let edited_bytes = std::fs::read(first.join("model-ir.json")).expect("term-extended ModelIR");
    let edited = parse_model_ir_v2(&edited_bytes).expect("strict term-extended ModelIR");
    let validation = validate_model_bytes(&edited_bytes).expect("C++-validated term addition");
    assert!(validation.report.analysis_ready);
    assert_eq!(
        edited.value()["load_combinations"][0]["terms"],
        serde_json::json!([
            {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": 1.2},
            {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": -0.5},
            {"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 0.25}
        ])
    );
    let extension = edited.value()["extensions"]
        .get("structural-native:model-add-direct-linear-load-combination-term.v1")
        .expect("direct term-add provenance extension");
    assert_eq!(
        extension["operation"],
        "direct_linear_load_combination_term_add"
    );
    assert_eq!(
        extension["editing_profile"],
        "unique_direct_linear_static_patterns_3_to_64"
    );
    assert_eq!(extension["load_combination_index"], 0);
    assert_eq!(extension["load_pattern_id"], "LC_AXIAL");
    assert_eq!(extension["term_index"], 2);
    assert_eq!(extension["source_term_count"], 2);
    assert_eq!(extension["term_count"], 3);
    assert_eq!(extension["factor"], 0.25);
    assert_eq!(
        extension["source_terms"],
        serde_json::json!([
            {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": 1.2},
            {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": -0.5}
        ])
    );

    let mut edit_receipt: Value = serde_json::from_slice(
        &std::fs::read(first.join("edit-receipt.json")).expect("term-add receipt"),
    )
    .expect("term-add receipt JSON");
    assert_eq!(
        edit_receipt["operation"],
        "direct_linear_load_combination_term_add"
    );
    assert_eq!(edit_receipt["load_pattern_id"], "LC_AXIAL");
    assert_eq!(edit_receipt["term_index"], 2);
    assert_eq!(edit_receipt["source_term_count"], 2);
    assert_eq!(edit_receipt["term_count"], 3);
    assert_eq!(edit_receipt["factor"], 0.25);
    assert_eq!(edit_receipt["cpp_semantic_snapshot_verified"], true);
    assert_self_hashed_edit_receipt(&mut edit_receipt);

    let request_directory = temporary.0.join("term-add-request");
    assert_success(&run_model_linear_combination_request_create(
        &first.join("model-ir.json"),
        &request_directory,
        "term-add-c5",
        "COMBO_SERVICE",
    ));
    let request_bytes =
        std::fs::read(request_directory.join("analysis-request.json")).expect("term-add request");
    let direct = execute_model_ir_linear_analysis(&edited_bytes, &request_bytes, None, u32::MAX)
        .expect("term-extended direct CPU execution");
    assert!(direct.is_complete());
    let recovery: Value =
        serde_json::from_str(direct.result_recovery_ir_json().expect("term-add recovery"))
            .expect("term-add recovery JSON");
    assert_eq!(recovery["load_pattern_id"], "COMBO_SERVICE");
    assert_eq!(
        recovery["active_external_load"],
        serde_json::json!([25000, -12000, 5000, 0, 0, 0])
    );
    assert_eq!(recovery["fallback_count"], 0);

    let partial = execute_model_ir_linear_analysis(&edited_bytes, &request_bytes, None, 0)
        .expect("term-add initial checkpoint");
    assert!(!partial.is_complete());
    let resumed = execute_model_ir_linear_analysis(
        &edited_bytes,
        &request_bytes,
        Some(partial.checkpoint_bytes()),
        u32::MAX,
    )
    .expect("term-add resumed CPU execution");
    assert!(resumed.is_complete());
    assert_eq!(resumed.result_ir_json(), direct.result_ir_json());
    assert_eq!(
        resumed.result_recovery_ir_json(),
        direct.result_recovery_ir_json()
    );

    for (label, pattern, expected_code) in [
        (
            "duplicate",
            "LC_WEAK",
            "workbench_model_add_direct_linear_load_combination_term_pattern_duplicate",
        ),
        (
            "missing",
            "LC_MISSING",
            "workbench_model_add_direct_linear_load_combination_term_pattern_missing",
        ),
    ] {
        let destination = temporary.0.join(format!("term-add-{label}"));
        let rejected = run_direct_linear_load_combination_term_add(
            &authored_path,
            &destination,
            "COMBO_SERVICE",
            pattern,
            "0.25",
        );
        assert!(!rejected.status.success());
        assert!(String::from_utf8_lossy(&rejected.stdout).contains(expected_code));
        assert!(!destination.exists());
    }
}

#[test]
#[allow(clippy::too_many_lines)]
fn direct_linear_load_combination_term_delete_executes_and_restarts_without_fallback() {
    let temporary = TestDirectory::create();
    let source =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let authored = temporary.0.join("term-delete-authored");
    assert_success(&run_direct_linear_load_combination_add(
        &source,
        &authored,
        "COMBO_SERVICE",
        &[
            ["LC_WEAK", "1.2"],
            ["LC_STRONG", "-0.5"],
            ["LC_AXIAL", "0.25"],
        ],
    ));
    let authored_path = authored.join("model-ir.json");
    let authored_bytes = std::fs::read(&authored_path).expect("term-delete source ModelIR");
    let first = temporary.0.join("term-delete-first");
    let second = temporary.0.join("term-delete-second");
    for destination in [&first, &second] {
        let output = run_direct_linear_load_combination_term_delete(
            &authored_path,
            destination,
            "COMBO_SERVICE",
            "LC_STRONG",
        );
        assert_success(&output);
        let receipt =
            std::fs::read(destination.join("edit-receipt.json")).expect("term-delete receipt");
        assert_eq!(output.stdout, [receipt.as_slice(), b"\n"].concat());
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(artifact)).expect("first term-delete artifact"),
            std::fs::read(second.join(artifact)).expect("second term-delete artifact")
        );
    }
    assert_eq!(
        std::fs::read(&authored_path).expect("unchanged term-delete source"),
        authored_bytes
    );

    let edited_bytes = std::fs::read(first.join("model-ir.json")).expect("term-reduced ModelIR");
    let edited = parse_model_ir_v2(&edited_bytes).expect("strict term-reduced ModelIR");
    let validation = validate_model_bytes(&edited_bytes).expect("C++-validated term deletion");
    assert!(validation.report.analysis_ready);
    assert_eq!(
        edited.value()["load_combinations"][0]["terms"],
        serde_json::json!([
            {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": 1.2},
            {"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 0.25}
        ])
    );
    let extension = edited.value()["extensions"]
        .get("structural-native:model-delete-direct-linear-load-combination-term.v1")
        .expect("direct term-delete provenance extension");
    assert_eq!(
        extension["operation"],
        "direct_linear_load_combination_term_delete"
    );
    assert_eq!(
        extension["editing_profile"],
        "unique_direct_linear_static_patterns_2_to_63"
    );
    assert_eq!(extension["load_combination_index"], 0);
    assert_eq!(extension["load_pattern_id"], "LC_STRONG");
    assert_eq!(extension["term_index"], 1);
    assert_eq!(extension["source_term_count"], 3);
    assert_eq!(extension["term_count"], 2);
    assert_eq!(extension["removed_factor"], -0.5);
    assert_eq!(
        extension["source_terms"],
        serde_json::json!([
            {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": 1.2},
            {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": -0.5},
            {"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 0.25}
        ])
    );

    let mut edit_receipt: Value = serde_json::from_slice(
        &std::fs::read(first.join("edit-receipt.json")).expect("term-delete receipt"),
    )
    .expect("term-delete receipt JSON");
    assert_eq!(
        edit_receipt["operation"],
        "direct_linear_load_combination_term_delete"
    );
    assert_eq!(edit_receipt["load_pattern_id"], "LC_STRONG");
    assert_eq!(edit_receipt["term_index"], 1);
    assert_eq!(edit_receipt["source_term_count"], 3);
    assert_eq!(edit_receipt["term_count"], 2);
    assert_eq!(edit_receipt["removed_factor"], -0.5);
    assert_eq!(edit_receipt["cpp_semantic_snapshot_verified"], true);
    assert_self_hashed_edit_receipt(&mut edit_receipt);

    let request_directory = temporary.0.join("term-delete-request");
    assert_success(&run_model_linear_combination_request_create(
        &first.join("model-ir.json"),
        &request_directory,
        "term-delete-c5",
        "COMBO_SERVICE",
    ));
    let request_bytes = std::fs::read(request_directory.join("analysis-request.json"))
        .expect("term-delete request");
    let direct = execute_model_ir_linear_analysis(&edited_bytes, &request_bytes, None, u32::MAX)
        .expect("term-reduced direct CPU execution");
    assert!(direct.is_complete());
    let recovery: Value = serde_json::from_str(
        direct
            .result_recovery_ir_json()
            .expect("term-delete recovery"),
    )
    .expect("term-delete recovery JSON");
    assert_eq!(recovery["load_pattern_id"], "COMBO_SERVICE");
    assert_eq!(
        recovery["active_external_load"],
        serde_json::json!([25000, -12000, 0, 0, 0, 0])
    );
    assert_eq!(recovery["fallback_count"], 0);

    let partial = execute_model_ir_linear_analysis(&edited_bytes, &request_bytes, None, 0)
        .expect("term-delete initial checkpoint");
    assert!(!partial.is_complete());
    let resumed = execute_model_ir_linear_analysis(
        &edited_bytes,
        &request_bytes,
        Some(partial.checkpoint_bytes()),
        u32::MAX,
    )
    .expect("term-delete resumed CPU execution");
    assert!(resumed.is_complete());
    assert_eq!(resumed.result_ir_json(), direct.result_ir_json());
    assert_eq!(
        resumed.result_recovery_ir_json(),
        direct.result_recovery_ir_json()
    );

    let missing_destination = temporary.0.join("term-delete-missing");
    let missing = run_direct_linear_load_combination_term_delete(
        &authored_path,
        &missing_destination,
        "COMBO_SERVICE",
        "LC_MISSING",
    );
    assert!(!missing.status.success());
    assert!(String::from_utf8_lossy(&missing.stdout)
        .contains("workbench_model_delete_direct_linear_load_combination_term_pattern_missing"));
    assert!(!missing_destination.exists());

    let minimum = temporary.0.join("term-delete-minimum");
    let two_term = temporary.0.join("term-delete-two-term");
    assert_success(&run_linear_load_combination_add(
        &source,
        &two_term,
        "COMBO_MINIMUM",
        ["LC_WEAK", "1.2"],
        ["LC_STRONG", "-0.5"],
    ));
    let rejected = run_direct_linear_load_combination_term_delete(
        &two_term.join("model-ir.json"),
        &minimum,
        "COMBO_MINIMUM",
        "LC_STRONG",
    );
    assert!(!rejected.status.success());
    assert!(String::from_utf8_lossy(&rejected.stdout)
        .contains("workbench_model_delete_direct_linear_load_combination_term_count_invalid"));
    assert!(!minimum.exists());
}

#[test]
#[allow(clippy::too_many_lines)]
fn direct_linear_load_combination_reference_edit_executes_and_restarts_without_fallback() {
    let temporary = TestDirectory::create();
    let source =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let authored = temporary.0.join("reference-edit-authored");
    assert_success(&run_linear_load_combination_add(
        &source,
        &authored,
        "COMBO_SERVICE",
        ["LC_WEAK", "1.2"],
        ["LC_STRONG", "-0.5"],
    ));
    let authored_path = authored.join("model-ir.json");
    let authored_bytes = std::fs::read(&authored_path).expect("reference-edit source ModelIR");
    let first = temporary.0.join("reference-edit-first");
    let second = temporary.0.join("reference-edit-second");
    for destination in [&first, &second] {
        let output = run_direct_linear_load_combination_reference_edit(
            &authored_path,
            destination,
            "COMBO_SERVICE",
            "LC_WEAK",
            "LC_AXIAL",
        );
        assert_success(&output);
        let receipt =
            std::fs::read(destination.join("edit-receipt.json")).expect("reference-edit receipt");
        assert_eq!(output.stdout, [receipt.as_slice(), b"\n"].concat());
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(artifact)).expect("first reference-edit artifact"),
            std::fs::read(second.join(artifact)).expect("second reference-edit artifact")
        );
    }
    assert_eq!(
        std::fs::read(&authored_path).expect("unchanged reference-edit source"),
        authored_bytes
    );

    let edited_bytes =
        std::fs::read(first.join("model-ir.json")).expect("reference-edited ModelIR");
    let edited = parse_model_ir_v2(&edited_bytes).expect("strict reference-edited ModelIR");
    let validation = validate_model_bytes(&edited_bytes).expect("C++-validated reference edit");
    assert!(validation.report.analysis_ready);
    assert_eq!(
        edited.value()["load_combinations"][0]["terms"],
        serde_json::json!([
            {"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 1.2},
            {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": -0.5}
        ])
    );
    let extension = edited.value()["extensions"]
        .get("structural-native:model-edit-direct-linear-load-combination-reference.v1")
        .expect("direct reference-edit provenance extension");
    assert_eq!(
        extension["operation"],
        "direct_linear_load_combination_reference_edit"
    );
    assert_eq!(
        extension["editing_profile"],
        "unique_direct_linear_static_patterns_2_to_64"
    );
    assert_eq!(extension["load_combination_index"], 0);
    assert_eq!(extension["load_pattern_id"], "LC_WEAK");
    assert_eq!(extension["replacement_load_pattern_id"], "LC_AXIAL");
    assert_eq!(extension["term_index"], 0);
    assert_eq!(extension["term_count"], 2);
    assert_eq!(extension["preserved_factor"], 1.2);
    assert_eq!(
        extension["source_terms"],
        serde_json::json!([
            {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": 1.2},
            {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": -0.5}
        ])
    );

    let mut edit_receipt: Value = serde_json::from_slice(
        &std::fs::read(first.join("edit-receipt.json")).expect("reference-edit receipt"),
    )
    .expect("reference-edit receipt JSON");
    assert_eq!(
        edit_receipt["operation"],
        "direct_linear_load_combination_reference_edit"
    );
    assert_eq!(edit_receipt["load_pattern_id"], "LC_WEAK");
    assert_eq!(edit_receipt["replacement_load_pattern_id"], "LC_AXIAL");
    assert_eq!(edit_receipt["term_index"], 0);
    assert_eq!(edit_receipt["term_count"], 2);
    assert_eq!(edit_receipt["preserved_factor"], 1.2);
    assert_eq!(edit_receipt["cpp_semantic_snapshot_verified"], true);
    assert_self_hashed_edit_receipt(&mut edit_receipt);

    let request_directory = temporary.0.join("reference-edit-request");
    assert_success(&run_model_linear_combination_request_create(
        &first.join("model-ir.json"),
        &request_directory,
        "reference-edit-c5",
        "COMBO_SERVICE",
    ));
    let request_bytes = std::fs::read(request_directory.join("analysis-request.json"))
        .expect("reference-edit request");
    let direct = execute_model_ir_linear_analysis(&edited_bytes, &request_bytes, None, u32::MAX)
        .expect("reference-edited direct CPU execution");
    assert!(direct.is_complete());
    let recovery: Value = serde_json::from_str(
        direct
            .result_recovery_ir_json()
            .expect("reference-edit recovery"),
    )
    .expect("reference-edit recovery JSON");
    assert_eq!(recovery["load_pattern_id"], "COMBO_SERVICE");
    assert_eq!(
        recovery["active_external_load"],
        serde_json::json!([120_000, 0, 5000, 0, 0, 0])
    );
    assert_eq!(recovery["fallback_count"], 0);

    let partial = execute_model_ir_linear_analysis(&edited_bytes, &request_bytes, None, 0)
        .expect("reference-edit initial checkpoint");
    assert!(!partial.is_complete());
    let resumed = execute_model_ir_linear_analysis(
        &edited_bytes,
        &request_bytes,
        Some(partial.checkpoint_bytes()),
        u32::MAX,
    )
    .expect("reference-edit resumed CPU execution");
    assert!(resumed.is_complete());
    assert_eq!(resumed.result_ir_json(), direct.result_ir_json());
    assert_eq!(
        resumed.result_recovery_ir_json(),
        direct.result_recovery_ir_json()
    );

    for (label, replacement, expected_code) in [
        ("no-change", "LC_WEAK", "workbench_model_edit_no_change"),
        (
            "duplicate",
            "LC_STRONG",
            "workbench_model_edit_linear_load_combination_replacement_pattern_duplicate",
        ),
        (
            "missing",
            "LC_MISSING",
            "workbench_model_edit_linear_load_combination_replacement_pattern_missing",
        ),
    ] {
        let destination = temporary.0.join(format!("reference-edit-{label}"));
        let rejected = run_direct_linear_load_combination_reference_edit(
            &authored_path,
            &destination,
            "COMBO_SERVICE",
            "LC_WEAK",
            replacement,
        );
        assert!(!rejected.status.success());
        assert!(String::from_utf8_lossy(&rejected.stdout).contains(expected_code));
        assert!(!destination.exists());
    }
}

#[test]
#[allow(clippy::too_many_lines)]
fn nested_linear_load_combination_is_authored_executed_and_restarted_without_fallback() {
    let temporary = TestDirectory::create();
    let source =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let base = temporary.0.join("nested-combination-base");
    assert_success(&run_linear_load_combination_add(
        &source,
        &base,
        "COMBO_BASE",
        ["LC_WEAK", "1.2"],
        ["LC_STRONG", "-0.5"],
    ));
    let terms = [
        ["--combination-term", "COMBO_BASE", "0.5"],
        ["--pattern-term", "LC_AXIAL", "0.25"],
    ];
    let first = temporary.0.join("nested-combination-add-first");
    let second = temporary.0.join("nested-combination-add-second");
    for destination in [&first, &second] {
        assert_success(&run_nested_linear_load_combination_add(
            &base.join("model-ir.json"),
            destination,
            "COMBO_NESTED",
            &terms,
        ));
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(artifact)).expect("first nested-combination artifact"),
            std::fs::read(second.join(artifact)).expect("second nested-combination artifact")
        );
    }

    let edited_bytes =
        std::fs::read(first.join("model-ir.json")).expect("nested-combination ModelIR");
    let edited = parse_model_ir_v2(&edited_bytes).expect("strict nested-combination ModelIR");
    let validation =
        validate_model_bytes(&edited_bytes).expect("C++-validated nested-combination ModelIR");
    assert!(validation.report.analysis_ready);
    assert_eq!(
        edited.value()["load_combinations"][1]["terms"],
        serde_json::json!([
            {"ref_id": "COMBO_BASE", "ref_kind": "load_combination", "factor": 0.5},
            {"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 0.25}
        ])
    );
    let extension = edited.value()["extensions"]
        .get("structural-native:model-add-nested-linear-load-combination.v3")
        .expect("nested-combination provenance extension");
    assert_eq!(extension["operation"], "nested_linear_load_combination_add");
    assert_eq!(extension["combination_depth"], 2);
    assert_eq!(extension["expanded_term_count"], 3);
    assert_eq!(extension["expanded_pattern_count"], 3);
    assert_eq!(
        extension["expanded_pattern_terms"],
        serde_json::json!([
            {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": 0.6},
            {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": -0.25},
            {"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 0.25}
        ])
    );

    let mut edit_receipt: Value = serde_json::from_slice(
        &std::fs::read(first.join("edit-receipt.json")).expect("nested-combination edit receipt"),
    )
    .expect("nested-combination edit receipt JSON");
    assert_eq!(
        edit_receipt["operation"],
        "nested_linear_load_combination_add"
    );
    assert_eq!(edit_receipt["combination_depth"], 2);
    assert_eq!(edit_receipt["expanded_term_count"], 3);
    assert_self_hashed_edit_receipt(&mut edit_receipt);

    let request_directory = temporary.0.join("nested-combination-request");
    let preflight = run_model_linear_combination_request_create(
        &first.join("model-ir.json"),
        &request_directory,
        "nested-combination-c5",
        "COMBO_NESTED",
    );
    assert_success(&preflight);
    let request_bytes = std::fs::read(request_directory.join("analysis-request.json"))
        .expect("nested-combination request");
    let mut request_receipt: Value = serde_json::from_slice(
        &std::fs::read(request_directory.join("request-receipt.json"))
            .expect("nested-combination request receipt"),
    )
    .expect("nested-combination request receipt JSON");
    assert_eq!(
        request_receipt["schema_version"],
        "structural-native-model-linear-nested-combination-request-create-receipt.v3"
    );
    assert_eq!(request_receipt["combination_depth"], 2);
    assert_eq!(request_receipt["expanded_term_count"], 3);
    assert_eq!(request_receipt["expanded_pattern_count"], 3);
    assert_self_hashed_edit_receipt(&mut request_receipt);

    let direct = execute_model_ir_linear_analysis(&edited_bytes, &request_bytes, None, u32::MAX)
        .expect("nested-combination direct CPU execution");
    assert!(direct.is_complete());
    let recovery: Value = serde_json::from_str(
        direct
            .result_recovery_ir_json()
            .expect("nested-combination recovery"),
    )
    .expect("nested-combination recovery JSON");
    assert_eq!(recovery["load_pattern_id"], "COMBO_NESTED");
    assert_eq!(recovery["load_pattern_index"], 1);
    assert_eq!(
        recovery["active_external_load"],
        serde_json::json!([25000, -6000, 2500, 0, 0, 0])
    );
    assert_eq!(recovery["fallback_count"], 0);

    let partial = execute_model_ir_linear_analysis(&edited_bytes, &request_bytes, None, 0)
        .expect("nested-combination initial checkpoint");
    assert!(!partial.is_complete());
    let resumed = execute_model_ir_linear_analysis(
        &edited_bytes,
        &request_bytes,
        Some(partial.checkpoint_bytes()),
        u32::MAX,
    )
    .expect("nested-combination resumed CPU execution");
    assert!(resumed.is_complete());
    assert_eq!(resumed.result_ir_json(), direct.result_ir_json());
    assert_eq!(
        resumed.result_recovery_ir_json(),
        direct.result_recovery_ir_json()
    );

    let delete_first = temporary.0.join("nested-combination-delete-first");
    let delete_second = temporary.0.join("nested-combination-delete-second");
    for destination in [&delete_first, &delete_second] {
        assert_success(&run_linear_load_combination_delete(
            &first.join("model-ir.json"),
            destination,
            "COMBO_NESTED",
        ));
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(delete_first.join(artifact)).expect("first nested-deletion artifact"),
            std::fs::read(delete_second.join(artifact)).expect("second nested-deletion artifact")
        );
    }
    assert_eq!(
        std::fs::read(first.join("model-ir.json")).expect("unchanged nested source"),
        edited_bytes
    );
    let deleted_bytes =
        std::fs::read(delete_first.join("model-ir.json")).expect("nested-deleted ModelIR");
    let deleted = parse_model_ir_v2(&deleted_bytes).expect("strict nested-deleted ModelIR");
    assert_eq!(
        deleted.value()["load_combinations"]
            .as_array()
            .map(Vec::len),
        Some(1)
    );
    assert_eq!(deleted.value()["load_combinations"][0]["id"], "COMBO_BASE");
    let delete_extension = deleted.value()["extensions"]
        .get("structural-native:model-delete-nested-linear-load-combination.v3")
        .expect("nested-combination delete provenance extension");
    assert_eq!(
        delete_extension["operation"],
        "nested_linear_load_combination_delete"
    );
    assert_eq!(
        delete_extension["deletion_profile"],
        "acyclic_nested_linear_static_depth_8_expanded_terms_64"
    );
    assert_eq!(delete_extension["term_count"], 2);
    assert_eq!(delete_extension["combination_depth"], 2);
    assert_eq!(delete_extension["expanded_term_count"], 3);
    assert_eq!(delete_extension["expanded_pattern_count"], 3);
    assert_eq!(
        delete_extension["removed_terms"],
        edited.value()["load_combinations"][1]["terms"]
    );
    assert_eq!(
        delete_extension["expanded_pattern_terms"],
        extension["expanded_pattern_terms"]
    );
    let mut delete_receipt: Value = serde_json::from_slice(
        &std::fs::read(delete_first.join("edit-receipt.json"))
            .expect("nested-combination delete receipt"),
    )
    .expect("nested-combination delete receipt JSON");
    assert_eq!(
        delete_receipt["operation"],
        "nested_linear_load_combination_delete"
    );
    assert_eq!(delete_receipt["combination_depth"], 2);
    assert_eq!(delete_receipt["expanded_term_count"], 3);
    assert_self_hashed_edit_receipt(&mut delete_receipt);

    let deleted_request_directory = temporary.0.join("nested-combination-delete-request");
    assert_success(&run_model_linear_combination_request_create(
        &delete_first.join("model-ir.json"),
        &deleted_request_directory,
        "nested-combination-delete-c5",
        "COMBO_BASE",
    ));
    let deleted_request = std::fs::read(deleted_request_directory.join("analysis-request.json"))
        .expect("nested-combination delete request");
    let deleted_direct =
        execute_model_ir_linear_analysis(&deleted_bytes, &deleted_request, None, u32::MAX)
            .expect("surviving child-combination CPU execution");
    assert!(deleted_direct.is_complete());
    let deleted_recovery: Value = serde_json::from_str(
        deleted_direct
            .result_recovery_ir_json()
            .expect("nested-combination deletion recovery"),
    )
    .expect("nested-combination deletion recovery JSON");
    assert_eq!(deleted_recovery["load_pattern_id"], "COMBO_BASE");
    assert_eq!(
        deleted_recovery["active_external_load"],
        serde_json::json!([0, -12000, 5000, 0, 0, 0])
    );
    assert_eq!(deleted_recovery["fallback_count"], 0);
    let deleted_partial =
        execute_model_ir_linear_analysis(&deleted_bytes, &deleted_request, None, 0)
            .expect("surviving child-combination checkpoint");
    assert!(!deleted_partial.is_complete());
    let deleted_resumed = execute_model_ir_linear_analysis(
        &deleted_bytes,
        &deleted_request,
        Some(deleted_partial.checkpoint_bytes()),
        u32::MAX,
    )
    .expect("surviving child-combination resumed execution");
    assert_eq!(
        deleted_resumed.result_ir_json(),
        deleted_direct.result_ir_json()
    );
    assert_eq!(
        deleted_resumed.result_recovery_ir_json(),
        deleted_direct.result_recovery_ir_json()
    );
}

#[test]
#[allow(clippy::too_many_lines)]
fn nested_linear_load_combination_factor_edit_executes_and_restarts_without_fallback() {
    let temporary = TestDirectory::create();
    let source =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let base = temporary.0.join("nested-factor-edit-base");
    assert_success(&run_linear_load_combination_add(
        &source,
        &base,
        "COMBO_BASE",
        ["LC_WEAK", "1.2"],
        ["LC_STRONG", "-0.5"],
    ));
    let nested = temporary.0.join("nested-factor-edit-authored");
    assert_success(&run_nested_linear_load_combination_add(
        &base.join("model-ir.json"),
        &nested,
        "COMBO_NESTED",
        &[
            ["--combination-term", "COMBO_BASE", "0.5"],
            ["--pattern-term", "LC_AXIAL", "0.25"],
        ],
    ));
    let nested_path = nested.join("model-ir.json");
    let nested_bytes = std::fs::read(&nested_path).expect("nested factor-edit source");
    let first = temporary.0.join("nested-factor-edit-first");
    let second = temporary.0.join("nested-factor-edit-second");
    for destination in [&first, &second] {
        let output = run_nested_linear_load_combination_factor_edit(
            &nested_path,
            destination,
            "COMBO_NESTED",
            "load_combination",
            "COMBO_BASE",
            "0.75",
        );
        assert_success(&output);
        let receipt = std::fs::read(destination.join("edit-receipt.json"))
            .expect("nested factor-edit receipt");
        assert_eq!(output.stdout, [receipt.as_slice(), b"\n"].concat());
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(artifact)).expect("first nested factor-edit artifact"),
            std::fs::read(second.join(artifact)).expect("second nested factor-edit artifact")
        );
    }
    assert_eq!(
        std::fs::read(&nested_path).expect("unchanged nested factor-edit source"),
        nested_bytes
    );

    let edited_bytes =
        std::fs::read(first.join("model-ir.json")).expect("nested factor-edited ModelIR");
    let edited = parse_model_ir_v2(&edited_bytes).expect("strict nested factor-edited ModelIR");
    let validation = validate_model_bytes(&edited_bytes).expect("C++-validated nested factor edit");
    assert!(validation.report.analysis_ready);
    assert_eq!(
        edited.value()["load_combinations"][1]["terms"],
        serde_json::json!([
            {"ref_id": "COMBO_BASE", "ref_kind": "load_combination", "factor": 0.75},
            {"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 0.25}
        ])
    );
    let extension = edited.value()["extensions"]
        .get("structural-native:model-edit-nested-linear-load-combination-factor.v1")
        .expect("nested factor-edit provenance extension");
    assert_eq!(
        extension["operation"],
        "nested_linear_load_combination_factor_edit"
    );
    assert_eq!(
        extension["editing_profile"],
        "acyclic_nested_linear_static_depth_8_expanded_terms_64"
    );
    assert_eq!(extension["load_combination_index"], 1);
    assert_eq!(extension["reference_kind"], "load_combination");
    assert_eq!(extension["reference_id"], "COMBO_BASE");
    assert_eq!(extension["term_index"], 0);
    assert_eq!(extension["term_count"], 2);
    assert_eq!(extension["previous_factor"], 0.5);
    assert_eq!(extension["edited_factor"], 0.75);
    assert_eq!(extension["source_combination_depth"], 2);
    assert_eq!(extension["edited_combination_depth"], 2);
    assert_eq!(extension["source_expanded_term_count"], 3);
    assert_eq!(extension["edited_expanded_term_count"], 3);
    assert_eq!(extension["source_expanded_pattern_count"], 3);
    assert_eq!(extension["edited_expanded_pattern_count"], 3);
    assert_eq!(
        extension["edited_expanded_pattern_terms"],
        serde_json::json!([
            {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": 0.899_999_999_999_999_9},
            {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": -0.375},
            {"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 0.25}
        ])
    );

    let mut edit_receipt: Value = serde_json::from_slice(
        &std::fs::read(first.join("edit-receipt.json")).expect("nested factor-edit receipt"),
    )
    .expect("nested factor-edit receipt JSON");
    assert_eq!(
        edit_receipt["operation"],
        "nested_linear_load_combination_factor_edit"
    );
    assert_eq!(edit_receipt["reference_kind"], "load_combination");
    assert_eq!(edit_receipt["reference_id"], "COMBO_BASE");
    assert_eq!(edit_receipt["term_index"], 0);
    assert_eq!(edit_receipt["term_count"], 2);
    assert_eq!(edit_receipt["previous_factor"], 0.5);
    assert_eq!(edit_receipt["edited_factor"], 0.75);
    assert_eq!(edit_receipt["cpp_semantic_snapshot_verified"], true);
    assert_self_hashed_edit_receipt(&mut edit_receipt);

    let request_directory = temporary.0.join("nested-factor-edit-request");
    assert_success(&run_model_linear_combination_request_create(
        &first.join("model-ir.json"),
        &request_directory,
        "nested-factor-edit-c5",
        "COMBO_NESTED",
    ));
    let request_bytes = std::fs::read(request_directory.join("analysis-request.json"))
        .expect("nested factor-edit request");
    let direct = execute_model_ir_linear_analysis(&edited_bytes, &request_bytes, None, u32::MAX)
        .expect("nested factor-edited direct CPU execution");
    assert!(direct.is_complete());
    let recovery: Value = serde_json::from_str(
        direct
            .result_recovery_ir_json()
            .expect("nested factor-edit recovery"),
    )
    .expect("nested factor-edit recovery JSON");
    assert_eq!(recovery["load_pattern_id"], "COMBO_NESTED");
    assert_eq!(
        recovery["active_external_load"],
        serde_json::json!([25000, -9000, 3750, 0, 0, 0])
    );
    assert_eq!(recovery["fallback_count"], 0);

    let partial = execute_model_ir_linear_analysis(&edited_bytes, &request_bytes, None, 0)
        .expect("nested factor-edit initial checkpoint");
    assert!(!partial.is_complete());
    let resumed = execute_model_ir_linear_analysis(
        &edited_bytes,
        &request_bytes,
        Some(partial.checkpoint_bytes()),
        u32::MAX,
    )
    .expect("nested factor-edit resumed CPU execution");
    assert!(resumed.is_complete());
    assert_eq!(resumed.result_ir_json(), direct.result_ir_json());
    assert_eq!(
        resumed.result_recovery_ir_json(),
        direct.result_recovery_ir_json()
    );

    let pattern_edit = temporary.0.join("nested-pattern-factor-edit");
    assert_success(&run_nested_linear_load_combination_factor_edit(
        &nested_path,
        &pattern_edit,
        "COMBO_NESTED",
        "load_pattern",
        "LC_AXIAL",
        "0.3",
    ));
    let pattern_edited = parse_model_ir_v2(
        &std::fs::read(pattern_edit.join("model-ir.json"))
            .expect("nested pattern factor-edited ModelIR"),
    )
    .expect("strict nested pattern factor edit");
    assert_eq!(
        pattern_edited.value()["load_combinations"][1]["terms"][1],
        serde_json::json!({
            "ref_id": "LC_AXIAL",
            "ref_kind": "load_pattern",
            "factor": 0.3
        })
    );

    let no_change = temporary.0.join("nested-factor-edit-no-change");
    let rejected = run_nested_linear_load_combination_factor_edit(
        &nested_path,
        &no_change,
        "COMBO_NESTED",
        "load_combination",
        "COMBO_BASE",
        "0.5",
    );
    assert!(!rejected.status.success());
    assert!(String::from_utf8_lossy(&rejected.stdout).contains("workbench_model_edit_no_change"));
    assert!(!no_change.exists());

    let typed_mismatch = temporary.0.join("nested-factor-edit-typed-mismatch");
    let rejected = run_nested_linear_load_combination_factor_edit(
        &nested_path,
        &typed_mismatch,
        "COMBO_NESTED",
        "load_pattern",
        "COMBO_BASE",
        "0.75",
    );
    assert!(!rejected.status.success());
    assert!(String::from_utf8_lossy(&rejected.stdout)
        .contains("workbench_model_edit_nested_linear_load_combination_term_missing"));
    assert!(!typed_mismatch.exists());
}

#[test]
#[allow(clippy::too_many_lines)]
fn nested_linear_load_combination_reference_edit_executes_and_restarts_without_fallback() {
    let temporary = TestDirectory::create();
    let source =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let base = temporary.0.join("nested-reference-edit-base");
    assert_success(&run_linear_load_combination_add(
        &source,
        &base,
        "COMBO_BASE",
        ["LC_WEAK", "1.2"],
        ["LC_STRONG", "-0.5"],
    ));
    let alternate = temporary.0.join("nested-reference-edit-alternate");
    assert_success(&run_linear_load_combination_add(
        &base.join("model-ir.json"),
        &alternate,
        "COMBO_ALTERNATE",
        ["LC_WEAK", "0.8"],
        ["LC_STRONG", "0.2"],
    ));
    let nested = temporary.0.join("nested-reference-edit-authored");
    assert_success(&run_nested_linear_load_combination_add(
        &alternate.join("model-ir.json"),
        &nested,
        "COMBO_NESTED",
        &[
            ["--combination-term", "COMBO_BASE", "0.5"],
            ["--pattern-term", "LC_AXIAL", "0.25"],
        ],
    ));
    let nested_path = nested.join("model-ir.json");
    let nested_bytes = std::fs::read(&nested_path).expect("nested reference-edit source");
    let nested_document = parse_model_ir_v2(&nested_bytes).expect("strict nested source");
    let first = temporary.0.join("nested-reference-edit-first");
    let second = temporary.0.join("nested-reference-edit-second");
    for destination in [&first, &second] {
        let output = run_nested_linear_load_combination_reference_edit(
            &nested_path,
            destination,
            "COMBO_NESTED",
            "load_pattern",
            "LC_AXIAL",
            "load_combination",
            "COMBO_ALTERNATE",
        );
        assert_success(&output);
        let receipt = std::fs::read(destination.join("edit-receipt.json"))
            .expect("nested reference-edit receipt");
        assert_eq!(output.stdout, [receipt.as_slice(), b"\n"].concat());
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(artifact)).expect("first nested reference-edit artifact"),
            std::fs::read(second.join(artifact)).expect("second nested reference-edit artifact")
        );
    }
    assert_eq!(
        std::fs::read(&nested_path).expect("unchanged nested reference-edit source"),
        nested_bytes
    );

    let edited_bytes =
        std::fs::read(first.join("model-ir.json")).expect("nested reference-edited ModelIR");
    let edited = parse_model_ir_v2(&edited_bytes).expect("strict nested reference-edited ModelIR");
    let validation =
        validate_model_bytes(&edited_bytes).expect("C++-validated nested reference edit");
    assert!(validation.report.analysis_ready);
    assert_eq!(
        edited.value()["load_combinations"][2]["terms"],
        serde_json::json!([
            {"ref_id": "COMBO_BASE", "ref_kind": "load_combination", "factor": 0.5},
            {"ref_id": "COMBO_ALTERNATE", "ref_kind": "load_combination", "factor": 0.25}
        ])
    );
    assert_eq!(
        edited.value()["load_combinations"][0],
        nested_document.value()["load_combinations"][0]
    );
    assert_eq!(
        edited.value()["load_combinations"][1],
        nested_document.value()["load_combinations"][1]
    );
    let extension = edited.value()["extensions"]
        .get("structural-native:model-edit-nested-linear-load-combination-reference.v1")
        .expect("nested reference-edit provenance extension");
    assert_eq!(
        extension["operation"],
        "nested_linear_load_combination_reference_edit"
    );
    assert_eq!(
        extension["editing_profile"],
        "acyclic_nested_linear_static_depth_8_expanded_terms_64"
    );
    assert_eq!(extension["load_combination_index"], 2);
    assert_eq!(extension["reference_kind"], "load_pattern");
    assert_eq!(extension["reference_id"], "LC_AXIAL");
    assert_eq!(extension["replacement_reference_kind"], "load_combination");
    assert_eq!(extension["replacement_reference_id"], "COMBO_ALTERNATE");
    assert_eq!(extension["term_index"], 1);
    assert_eq!(extension["term_count"], 2);
    assert_eq!(extension["preserved_factor"], 0.25);
    assert_eq!(extension["source_combination_depth"], 2);
    assert_eq!(extension["edited_combination_depth"], 2);
    assert_eq!(extension["source_expanded_term_count"], 3);
    assert_eq!(extension["edited_expanded_term_count"], 4);
    assert_eq!(extension["source_expanded_pattern_count"], 3);
    assert_eq!(extension["edited_expanded_pattern_count"], 2);
    assert_eq!(
        extension["edited_expanded_pattern_terms"],
        serde_json::json!([
            {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": 0.8},
            {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": -0.2}
        ])
    );

    let mut edit_receipt: Value = serde_json::from_slice(
        &std::fs::read(first.join("edit-receipt.json")).expect("nested reference-edit receipt"),
    )
    .expect("nested reference-edit receipt JSON");
    assert_eq!(
        edit_receipt["operation"],
        "nested_linear_load_combination_reference_edit"
    );
    assert_eq!(edit_receipt["reference_kind"], "load_pattern");
    assert_eq!(edit_receipt["reference_id"], "LC_AXIAL");
    assert_eq!(
        edit_receipt["replacement_reference_kind"],
        "load_combination"
    );
    assert_eq!(edit_receipt["replacement_reference_id"], "COMBO_ALTERNATE");
    assert_eq!(edit_receipt["preserved_factor"], 0.25);
    assert_eq!(edit_receipt["cpp_semantic_snapshot_verified"], true);
    assert_self_hashed_edit_receipt(&mut edit_receipt);

    let request_directory = temporary.0.join("nested-reference-edit-request");
    assert_success(&run_model_linear_combination_request_create(
        &first.join("model-ir.json"),
        &request_directory,
        "nested-reference-edit-c5",
        "COMBO_NESTED",
    ));
    let request_bytes = std::fs::read(request_directory.join("analysis-request.json"))
        .expect("nested reference-edit request");
    let direct = execute_model_ir_linear_analysis(&edited_bytes, &request_bytes, None, u32::MAX)
        .expect("nested reference-edited direct CPU execution");
    assert!(direct.is_complete());
    let recovery: Value = serde_json::from_str(
        direct
            .result_recovery_ir_json()
            .expect("nested reference-edit recovery"),
    )
    .expect("nested reference-edit recovery JSON");
    assert_eq!(recovery["load_pattern_id"], "COMBO_NESTED");
    assert_eq!(
        recovery["active_external_load"],
        serde_json::json!([0, -8000, 2000, 0, 0, 0])
    );
    assert_eq!(recovery["fallback_count"], 0);

    let partial = execute_model_ir_linear_analysis(&edited_bytes, &request_bytes, None, 0)
        .expect("nested reference-edit initial checkpoint");
    assert!(!partial.is_complete());
    let resumed = execute_model_ir_linear_analysis(
        &edited_bytes,
        &request_bytes,
        Some(partial.checkpoint_bytes()),
        u32::MAX,
    )
    .expect("nested reference-edit resumed CPU execution");
    assert!(resumed.is_complete());
    assert_eq!(resumed.result_ir_json(), direct.result_ir_json());
    assert_eq!(
        resumed.result_recovery_ir_json(),
        direct.result_recovery_ir_json()
    );

    let cases = [
        (
            "no-change",
            "load_pattern",
            "LC_AXIAL",
            "workbench_model_edit_no_change",
        ),
        (
            "duplicate",
            "load_combination",
            "COMBO_BASE",
            "workbench_model_edit_nested_linear_load_combination_replacement_reference_duplicate",
        ),
        (
            "missing",
            "load_combination",
            "COMBO_MISSING",
            "workbench_model_edit_nested_linear_load_combination_replacement_combination_missing",
        ),
        (
            "cycle",
            "load_combination",
            "COMBO_NESTED",
            "workbench_model_linear_nested_combination_cycle",
        ),
    ];
    for (label, replacement_kind, replacement_id, expected_code) in cases {
        let destination = temporary
            .0
            .join(format!("nested-reference-edit-{label}-rejected"));
        let rejected = run_nested_linear_load_combination_reference_edit(
            &nested_path,
            &destination,
            "COMBO_NESTED",
            "load_pattern",
            "LC_AXIAL",
            replacement_kind,
            replacement_id,
        );
        assert!(
            !rejected.status.success(),
            "accepted {label} reference edit"
        );
        assert!(
            String::from_utf8_lossy(&rejected.stdout).contains(expected_code),
            "unexpected {label} error: {}",
            String::from_utf8_lossy(&rejected.stdout)
        );
        assert!(!destination.exists());
    }

    let direct_degradation = temporary.0.join("nested-reference-edit-direct-rejected");
    let rejected = run_nested_linear_load_combination_reference_edit(
        &nested_path,
        &direct_degradation,
        "COMBO_NESTED",
        "load_combination",
        "COMBO_BASE",
        "load_pattern",
        "LC_WEAK",
    );
    assert!(!rejected.status.success());
    assert!(String::from_utf8_lossy(&rejected.stdout)
        .contains("workbench_model_edit_nested_linear_load_combination_direct_unsupported"));
    assert!(!direct_degradation.exists());
}

#[test]
#[allow(clippy::too_many_lines)]
fn linear_load_combination_deletion_is_deterministic_fail_closed_and_restores_cpu_execution() {
    let temporary = TestDirectory::create();
    let source =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let source_bytes = std::fs::read(&source).expect("load-combination delete base bytes");
    let source_validation =
        validate_model_bytes(&source_bytes).expect("C++-validated combination-delete base");
    let combination_source = temporary.0.join("combination-delete-source");
    assert_success(&run_linear_load_combination_add(
        &source,
        &combination_source,
        "COMBO_SERVICE",
        ["LC_WEAK", "1.2"],
        ["LC_STRONG", "-0.5"],
    ));
    let combination_path = combination_source.join("model-ir.json");
    let combination_bytes =
        std::fs::read(&combination_path).expect("load-combination delete source bytes");
    let combination_model =
        parse_model_ir_v2(&combination_bytes).expect("strict combination-delete source");

    let first = temporary.0.join("linear-load-combination-delete-first");
    let second = temporary.0.join("linear-load-combination-delete-second");
    for destination in [&first, &second] {
        let output =
            run_linear_load_combination_delete(&combination_path, destination, "COMBO_SERVICE");
        assert_success(&output);
        let receipt = std::fs::read(destination.join("edit-receipt.json"))
            .expect("linear-load-combination delete receipt");
        assert_eq!(output.stdout, [receipt.as_slice(), b"\n"].concat());
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(artifact)).expect("first combination-delete artifact"),
            std::fs::read(second.join(artifact)).expect("second combination-delete artifact")
        );
    }
    assert_eq!(
        std::fs::read(&combination_path).expect("unchanged combination-delete source"),
        combination_bytes
    );

    let deleted_bytes =
        std::fs::read(first.join("model-ir.json")).expect("combination-deleted ModelIR");
    let deleted = parse_model_ir_v2(&deleted_bytes).expect("strict combination-deleted ModelIR");
    let deleted_validation =
        validate_model_bytes(&deleted_bytes).expect("C++-validated combination-deleted ModelIR");
    assert!(deleted_validation.report.analysis_ready);
    assert_eq!(deleted_validation.report.entity_counts.load_combinations, 0);
    assert_eq!(deleted.value()["load_combinations"], serde_json::json!([]));
    for family in [
        "nodes",
        "materials",
        "sections",
        "elements",
        "constraints",
        "load_patterns",
        "time_functions",
        "construction_stages",
        "unsupported_features",
        "roundtrip_map",
    ] {
        assert_eq!(deleted.value()[family], combination_model.value()[family]);
    }
    assert!(deleted.value()["extensions"]
        .get("structural-native:model-add-linear-load-combination.v1")
        .is_some());
    let extension = deleted.value()["extensions"]
        .get("structural-native:model-delete-linear-load-combination.v1")
        .expect("linear-load-combination delete provenance extension");
    assert_eq!(extension["operation"], "linear_load_combination_delete");
    assert!(extension.get("deletion_profile").is_none());
    assert!(extension.get("term_count").is_none());
    assert_eq!(extension["removed_load_combination_id"], "COMBO_SERVICE");
    assert_eq!(extension["removed_load_combination_index"], 0);
    assert_eq!(extension["removed_combination_type"], "linear");
    assert_eq!(
        extension["removed_terms"],
        combination_model.value()["load_combinations"][0]["terms"]
    );
    assert_eq!(extension["removed_source_id"], Value::Null);
    assert_eq!(extension["removed_extensions"], serde_json::json!({}));

    let mut receipt: Value = serde_json::from_slice(
        &std::fs::read(first.join("edit-receipt.json"))
            .expect("linear-load-combination delete receipt"),
    )
    .expect("linear-load-combination delete receipt JSON");
    assert_eq!(receipt["operation"], "linear_load_combination_delete");
    assert!(receipt.get("deletion_profile").is_none());
    assert!(receipt.get("term_count").is_none());
    assert_eq!(receipt["removed_load_combination_id"], "COMBO_SERVICE");
    assert_eq!(receipt["removed_load_combination_index"], 0);
    assert_eq!(receipt["removed_combination_type"], "linear");
    assert_eq!(
        receipt["removed_terms"],
        combination_model.value()["load_combinations"][0]["terms"]
    );
    assert_eq!(receipt["cpp_semantic_snapshot_verified"], true);
    assert_eq!(receipt["analysis_ready"], true);
    assert_eq!(receipt["blocking_feature_ids"], serde_json::json!([]));
    assert_eq!(receipt["edited_content_hash"], deleted.content_hash());
    assert_eq!(
        receipt["edited_semantic_hash"],
        source_validation.report.semantic_hash
    );
    assert_self_hashed_edit_receipt(&mut receipt);

    let view = run_workbench(&[text("model-view"), first.join("model-ir.json").as_os_str()]);
    assert_success(&view);
    assert!(String::from_utf8_lossy(&view.stdout).contains("C++ semantic snapshot: verified"));

    let request_directory = temporary.0.join("linear-load-combination-delete-request");
    assert_success(&run_model_linear_request_create(
        &first.join("model-ir.json"),
        &request_directory,
        "linear-load-combination-delete-c5",
        "LC_WEAK",
    ));
    let request_bytes = std::fs::read(request_directory.join("analysis-request.json"))
        .expect("combination-delete request");
    let direct = execute_model_ir_linear_analysis(&deleted_bytes, &request_bytes, None, u32::MAX)
        .expect("combination-delete direct execution");
    assert!(direct.is_complete());
    let recovery: Value = serde_json::from_str(
        direct
            .result_recovery_ir_json()
            .expect("combination-delete direct recovery"),
    )
    .expect("combination-delete recovery JSON");
    assert_eq!(
        recovery["active_dof_indices"],
        serde_json::json!([6, 7, 8, 9, 10, 11])
    );
    assert_eq!(
        recovery["active_external_load"],
        serde_json::json!([0, -10000, 0, 0, 0, 0])
    );
    assert_eq!(recovery["recovery_element_types"], serde_json::json!([1]));
    assert_eq!(recovery["recovery_offsets"], serde_json::json!([0, 12]));
    assert_eq!(recovery["fallback_count"], 0);
    let partial = execute_model_ir_linear_analysis(&deleted_bytes, &request_bytes, None, 0)
        .expect("combination-delete partial execution");
    assert!(!partial.is_complete());
    let resumed = execute_model_ir_linear_analysis(
        &deleted_bytes,
        &request_bytes,
        Some(partial.checkpoint_bytes()),
        u32::MAX,
    )
    .expect("combination-delete resumed execution");
    assert!(resumed.is_complete());
    assert_eq!(resumed.result_ir_json(), direct.result_ir_json());
    assert_eq!(
        resumed.result_recovery_ir_json(),
        direct.result_recovery_ir_json()
    );

    let two_combinations = temporary.0.join("combination-delete-two-source");
    assert_success(&run_linear_load_combination_add(
        &combination_path,
        &two_combinations,
        "COMBO_STRENGTH",
        ["LC_AXIAL", "1.4"],
        ["LC_TORSION", "0.7"],
    ));
    let nonterminal_destination = temporary.0.join("combination-delete-nonterminal");
    let nonterminal = run_linear_load_combination_delete(
        &two_combinations.join("model-ir.json"),
        &nonterminal_destination,
        "COMBO_SERVICE",
    );
    assert_eq!(nonterminal.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&nonterminal.stdout)
        .contains("workbench_model_delete_linear_load_combination_not_terminal"));
    assert!(!nonterminal_destination.exists());

    for (name, guarded, expected_code) in [
        (
            "source-owned",
            {
                let mut value = combination_model.value().clone();
                value["load_combinations"][0]["source_id"] = serde_json::json!("mgt:COMBO_SERVICE");
                value
            },
            "workbench_model_delete_linear_load_combination_source_owned",
        ),
        (
            "extended",
            {
                let mut value = combination_model.value().clone();
                value["load_combinations"][0]["extensions"] =
                    serde_json::json!({"external:owner": "external"});
                value
            },
            "workbench_model_delete_linear_load_combination_extensions_unsupported",
        ),
        (
            "feature-owned",
            {
                let mut value = combination_model.value().clone();
                value["unsupported_features"] = serde_json::json!([{
                    "feature_id": "feature.combination-delete-owned",
                    "kind": "source_owned_load_combination",
                    "source_entity_id": "COMBO_SERVICE",
                    "disposition": "preserved_only",
                    "blocking": false,
                    "detail": "The source feature directly owns the candidate combination.",
                    "extensions": {}
                }]);
                value
            },
            "workbench_model_delete_linear_load_combination_unsupported_feature_owned",
        ),
        (
            "roundtrip-owned",
            {
                let mut value = combination_model.value().clone();
                value["roundtrip_map"] = serde_json::json!([{
                    "source_entity_id": "source:COMBO_SERVICE",
                    "entity_kind": "load_combination",
                    "model_ir_entity_id": "COMBO_SERVICE",
                    "mapping_status": "exact",
                    "extensions": {}
                }]);
                value
            },
            "workbench_model_delete_linear_load_combination_roundtrip_owned",
        ),
    ] {
        let guarded_path = temporary.0.join(format!("combination-delete-{name}.json"));
        std::fs::write(
            &guarded_path,
            canonicalize_model_ir_v2(&guarded)
                .expect("canonical guarded combination-delete source")
                .as_bytes(),
        )
        .expect("write guarded combination-delete source");
        let destination = temporary.0.join(format!("combination-delete-{name}"));
        let rejected =
            run_linear_load_combination_delete(&guarded_path, &destination, "COMBO_SERVICE");
        assert_eq!(rejected.status.code(), Some(1), "{name}");
        assert!(
            String::from_utf8_lossy(&rejected.stdout).contains(expected_code),
            "{name}: {}",
            String::from_utf8_lossy(&rejected.stdout)
        );
        assert!(!destination.exists());
    }

    let mut referenced = combination_model.value().clone();
    let candidate = referenced["load_combinations"][0].clone();
    referenced["load_combinations"] = serde_json::json!([
        {
            "id": "COMBO_PARENT",
            "index": 0,
            "combination_type": "linear",
            "terms": [
                {"ref_id": "COMBO_SERVICE", "ref_kind": "load_combination", "factor": 1},
                {"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 1}
            ],
            "source_id": null,
            "extensions": {}
        },
        candidate
    ]);
    referenced["load_combinations"][1]["index"] = serde_json::json!(1);
    let referenced_path = temporary.0.join("combination-delete-referenced.json");
    std::fs::write(
        &referenced_path,
        canonicalize_model_ir_v2(&referenced)
            .expect("canonical referenced combination-delete source")
            .as_bytes(),
    )
    .expect("write referenced combination-delete source");
    let referenced_destination = temporary.0.join("combination-delete-referenced");
    let referenced_rejection = run_linear_load_combination_delete(
        &referenced_path,
        &referenced_destination,
        "COMBO_SERVICE",
    );
    assert_eq!(referenced_rejection.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&referenced_rejection.stdout)
        .contains("workbench_model_delete_linear_load_combination_referenced_by_combination"));
    assert!(!referenced_destination.exists());

    let existing = run_linear_load_combination_delete(&combination_path, &first, "COMBO_SERVICE");
    assert_eq!(existing.status.code(), Some(1));
    assert!(
        String::from_utf8_lossy(&existing.stdout).contains("workbench_stage_destination_exists")
    );

    let mut blocked = combination_model.value().clone();
    blocked["unsupported_features"] = serde_json::json!([{
        "feature_id": "feature.combination-delete-visible-not-runnable",
        "kind": "unsupported_solver_feature",
        "source_entity_id": null,
        "disposition": "blocked",
        "blocking": true,
        "detail": "Combination deletion must preserve unrelated solver blockers.",
        "extensions": {}
    }]);
    let original_roundtrip_map = blocked["roundtrip_map"].clone();
    let blocked_source = temporary.0.join("blocked-combination-delete-source.json");
    std::fs::write(
        &blocked_source,
        canonicalize_model_ir_v2(&blocked)
            .expect("canonical blocked combination-delete source")
            .as_bytes(),
    )
    .expect("write blocked combination-delete source");
    let blocked_destination = temporary.0.join("blocked-combination-delete");
    assert_success(&run_linear_load_combination_delete(
        &blocked_source,
        &blocked_destination,
        "COMBO_SERVICE",
    ));
    let blocked_receipt: Value = serde_json::from_slice(
        &std::fs::read(blocked_destination.join("edit-receipt.json"))
            .expect("blocked combination-delete receipt"),
    )
    .expect("blocked combination-delete receipt JSON");
    assert_eq!(blocked_receipt["analysis_ready"], false);
    assert_eq!(
        blocked_receipt["blocking_feature_ids"],
        serde_json::json!(["feature.combination-delete-visible-not-runnable"])
    );
    let blocked_edited: Value = serde_json::from_slice(
        &std::fs::read(blocked_destination.join("model-ir.json"))
            .expect("blocked combination-deleted model"),
    )
    .expect("blocked combination-deleted JSON");
    assert_eq!(blocked_edited["roundtrip_map"], original_roundtrip_map);
}

#[test]
#[allow(clippy::too_many_lines)]
fn linear_load_pattern_deletion_is_atomic_fail_closed_restartable_and_cpu_executable() {
    let temporary = TestDirectory::create();
    let source =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let member_directory = temporary.0.join("pattern-delete-member-source");
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
    let load_directory = temporary.0.join("pattern-delete-load-source");
    assert_success(&run_nodal_load_add(
        &member_directory.join("model-ir.json"),
        &load_directory,
        "LC_WEAK",
        "L_WEAK_N3",
        "N3",
        ["0", "-1000", "0", "0", "0", "0"],
    ));
    let constraint_directory = temporary.0.join("pattern-delete-constraint-source");
    assert_success(&run_fixed_constraint_add(
        &load_directory.join("model-ir.json"),
        &constraint_directory,
        "BC_N3",
        "N3",
    ));
    let pattern_directory = temporary.0.join("pattern-delete-source");
    assert_success(&run_linear_load_pattern_add(
        &constraint_directory.join("model-ir.json"),
        &pattern_directory,
        "LC_CUSTOM",
        "L_CUSTOM_N2",
        "N2",
        ["2500", "0", "0", "0", "0", "0"],
    ));
    let pattern_path = pattern_directory.join("model-ir.json");
    let pattern_bytes = std::fs::read(&pattern_path).expect("load-pattern delete source bytes");
    let pattern_model = parse_model_ir_v2(&pattern_bytes).expect("strict pattern-delete source");

    let first = temporary.0.join("linear-load-pattern-delete-first");
    let second = temporary.0.join("linear-load-pattern-delete-second");
    for destination in [&first, &second] {
        let output = run_linear_load_pattern_delete(&pattern_path, destination, "LC_CUSTOM");
        assert_success(&output);
        let receipt = std::fs::read(destination.join("edit-receipt.json"))
            .expect("linear-load-pattern delete receipt");
        assert_eq!(output.stdout, [receipt.as_slice(), b"\n"].concat());
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(artifact)).expect("first pattern-delete artifact"),
            std::fs::read(second.join(artifact)).expect("second pattern-delete artifact")
        );
    }
    assert_eq!(
        std::fs::read(&pattern_path).expect("unchanged pattern-delete source"),
        pattern_bytes
    );

    let deleted_bytes =
        std::fs::read(first.join("model-ir.json")).expect("load-pattern-deleted ModelIR");
    let deleted = parse_model_ir_v2(&deleted_bytes).expect("strict load-pattern-deleted ModelIR");
    for family in [
        "nodes",
        "materials",
        "sections",
        "elements",
        "constraints",
        "load_combinations",
        "time_functions",
        "construction_stages",
        "roundtrip_map",
        "unsupported_features",
    ] {
        assert_eq!(deleted.value()[family], pattern_model.value()[family]);
    }
    let source_patterns = pattern_model.value()["load_patterns"]
        .as_array()
        .expect("source load patterns");
    let deleted_patterns = deleted.value()["load_patterns"]
        .as_array()
        .expect("deleted load patterns");
    assert_eq!(source_patterns.len(), deleted_patterns.len() + 1);
    assert_eq!(deleted_patterns, &source_patterns[..deleted_patterns.len()]);
    assert_eq!(
        source_patterns.last().expect("terminal pattern")["id"],
        "LC_CUSTOM"
    );
    let extension = deleted.value()["extensions"]
        .get("structural-native:model-delete-linear-load-pattern.v1")
        .expect("linear-load-pattern delete provenance extension");
    assert_eq!(extension["operation"], "linear_load_pattern_delete");
    assert_eq!(extension["removed_load_pattern_id"], "LC_CUSTOM");
    assert_eq!(extension["removed_load_pattern_index"], 4);
    assert_eq!(extension["removed_analysis_type"], "linear_static");
    assert_eq!(
        extension["removed_self_weight"],
        serde_json::json!([0, 0, 0])
    );
    assert_eq!(extension["removed_nodal_load_id"], "L_CUSTOM_N2");
    assert_eq!(extension["removed_nodal_load_index"], 0);
    assert_eq!(extension["removed_node_id"], "N2");
    assert_eq!(
        extension["removed_components_si"],
        serde_json::json!({"FX": 2500, "FY": 0, "FZ": 0, "MX": 0, "MY": 0, "MZ": 0})
    );
    let mut receipt: Value = serde_json::from_slice(
        &std::fs::read(first.join("edit-receipt.json"))
            .expect("linear-load-pattern delete receipt"),
    )
    .expect("linear-load-pattern delete receipt JSON");
    assert_eq!(receipt["operation"], "linear_load_pattern_delete");
    assert_eq!(receipt["removed_load_pattern_id"], "LC_CUSTOM");
    assert_eq!(receipt["removed_nodal_load_id"], "L_CUSTOM_N2");
    assert_eq!(receipt["cpp_semantic_snapshot_verified"], true);
    assert_eq!(receipt["analysis_ready"], true);
    assert_eq!(receipt["edited_content_hash"], deleted.content_hash());
    assert_self_hashed_edit_receipt(&mut receipt);

    let request_directory = temporary.0.join("linear-load-pattern-delete-request");
    assert_success(&run_model_linear_request_create(
        &first.join("model-ir.json"),
        &request_directory,
        "linear-load-pattern-delete-c5",
        "LC_WEAK",
    ));
    let request_bytes = std::fs::read(request_directory.join("analysis-request.json"))
        .expect("load-pattern delete request");
    let direct = execute_model_ir_linear_analysis(&deleted_bytes, &request_bytes, None, u32::MAX)
        .expect("load-pattern delete direct execution");
    assert!(direct.is_complete());
    let recovery: Value = serde_json::from_str(
        direct
            .result_recovery_ir_json()
            .expect("load-pattern delete direct recovery"),
    )
    .expect("load-pattern delete recovery JSON");
    assert_eq!(
        recovery["active_dof_indices"],
        serde_json::json!([6, 7, 8, 9, 10, 11])
    );
    assert_eq!(
        recovery["active_external_load"],
        serde_json::json!([0, -10000, 0, 0, 0, 0])
    );
    assert_eq!(
        recovery["recovery_stable_indices"],
        serde_json::json!([0, 1])
    );
    assert_eq!(
        recovery["recovery_element_types"],
        serde_json::json!([1, 1])
    );
    assert_eq!(recovery["recovery_offsets"], serde_json::json!([0, 12, 24]));
    assert_eq!(recovery["fallback_count"], 0);
    let partial = execute_model_ir_linear_analysis(&deleted_bytes, &request_bytes, None, 0)
        .expect("load-pattern delete partial execution");
    assert!(!partial.is_complete());
    let resumed = execute_model_ir_linear_analysis(
        &deleted_bytes,
        &request_bytes,
        Some(partial.checkpoint_bytes()),
        u32::MAX,
    )
    .expect("load-pattern delete resumed execution");
    assert!(resumed.is_complete());
    assert_eq!(resumed.result_ir_json(), direct.result_ir_json());
    assert_eq!(
        resumed.result_recovery_ir_json(),
        direct.result_recovery_ir_json()
    );

    let nonterminal_destination = temporary.0.join("pattern-delete-nonterminal");
    let nonterminal =
        run_linear_load_pattern_delete(&pattern_path, &nonterminal_destination, "LC_WEAK");
    assert_eq!(nonterminal.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&nonterminal.stdout)
        .contains("workbench_model_delete_linear_load_pattern_not_terminal"));
    assert!(!nonterminal_destination.exists());

    let mut source_owned = pattern_model.value().clone();
    source_owned["load_patterns"][4]["source_id"] = serde_json::json!("source:LC_CUSTOM");
    let source_owned_path = temporary.0.join("pattern-delete-source-owned.json");
    std::fs::write(
        &source_owned_path,
        canonicalize_model_ir_v2(&source_owned)
            .expect("canonical source-owned pattern")
            .as_bytes(),
    )
    .expect("write source-owned pattern");
    let source_owned_destination = temporary.0.join("pattern-delete-source-owned");
    let source_owned_rejection =
        run_linear_load_pattern_delete(&source_owned_path, &source_owned_destination, "LC_CUSTOM");
    assert_eq!(source_owned_rejection.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&source_owned_rejection.stdout)
        .contains("workbench_model_delete_linear_load_pattern_source_owned"));
    assert!(!source_owned_destination.exists());

    let extra_load_directory = temporary.0.join("pattern-delete-multiple-load-source");
    assert_success(&run_nodal_load_add(
        &pattern_path,
        &extra_load_directory,
        "LC_CUSTOM",
        "L_CUSTOM_N3",
        "N3",
        ["0", "-100", "0", "0", "0", "0"],
    ));
    let multiple_destination = temporary.0.join("pattern-delete-multiple-load");
    let multiple = run_linear_load_pattern_delete(
        &extra_load_directory.join("model-ir.json"),
        &multiple_destination,
        "LC_CUSTOM",
    );
    assert_eq!(multiple.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&multiple.stdout)
        .contains("workbench_model_delete_linear_load_pattern_single_load_required"));
    assert!(!multiple_destination.exists());

    for (name, field, value, code) in [
        (
            "combined",
            "load_combinations",
            serde_json::json!([{
                "id": "COMB_DELETE_GUARD",
                "index": 0,
                "combination_type": "linear",
                "terms": [{"ref_id": "LC_CUSTOM", "ref_kind": "load_pattern", "factor": 1}],
                "source_id": null,
                "extensions": {}
            }]),
            "workbench_model_delete_linear_load_pattern_referenced_by_combination",
        ),
        (
            "staged",
            "construction_stages",
            serde_json::json!([{
                "id": "STAGE_DELETE_GUARD",
                "index": 0,
                "active_element_ids": [],
                "active_constraint_ids": [],
                "load_pattern_ids": ["LC_CUSTOM"],
                "extensions": {}
            }]),
            "workbench_model_delete_linear_load_pattern_referenced_by_stage",
        ),
        (
            "feature-owned",
            "unsupported_features",
            serde_json::json!([{
                "feature_id": "feature.pattern-delete-owned",
                "kind": "source_owned_load_pattern",
                "source_entity_id": "LC_CUSTOM",
                "disposition": "preserved_only",
                "blocking": false,
                "detail": "The source feature directly owns the candidate load pattern.",
                "extensions": {}
            }]),
            "workbench_model_delete_linear_load_pattern_unsupported_feature_owned",
        ),
        (
            "roundtrip-owned",
            "roundtrip_map",
            serde_json::json!([{
                "source_entity_id": "source:LC_CUSTOM",
                "entity_kind": "load_pattern",
                "model_ir_entity_id": "LC_CUSTOM",
                "mapping_status": "exact",
                "extensions": {}
            }]),
            "workbench_model_delete_linear_load_pattern_roundtrip_owned",
        ),
    ] {
        let mut guarded = pattern_model.value().clone();
        guarded[field] = value;
        let guarded_path = temporary.0.join(format!("pattern-delete-{name}.json"));
        std::fs::write(
            &guarded_path,
            canonicalize_model_ir_v2(&guarded)
                .expect("canonical guarded pattern-delete source")
                .as_bytes(),
        )
        .expect("write guarded pattern-delete source");
        let destination = temporary.0.join(format!("pattern-delete-{name}"));
        let rejection = run_linear_load_pattern_delete(&guarded_path, &destination, "LC_CUSTOM");
        assert_eq!(rejection.status.code(), Some(1));
        assert!(String::from_utf8_lossy(&rejection.stdout).contains(code));
        assert!(!destination.exists());
    }

    let existing = run_linear_load_pattern_delete(&pattern_path, &first, "LC_CUSTOM");
    assert_eq!(existing.status.code(), Some(1));
    assert!(
        String::from_utf8_lossy(&existing.stdout).contains("workbench_stage_destination_exists")
    );

    let mut blocked = pattern_model.value().clone();
    blocked["unsupported_features"] = serde_json::json!([{
        "feature_id": "feature.pattern-delete-visible-not-runnable",
        "kind": "unsupported_solver_feature",
        "source_entity_id": null,
        "disposition": "blocked",
        "blocking": true,
        "detail": "Load-pattern deletion must preserve unsupported solver blockers.",
        "extensions": {}
    }]);
    let blocked_source = temporary.0.join("blocked-pattern-delete-source.json");
    std::fs::write(
        &blocked_source,
        canonicalize_model_ir_v2(&blocked)
            .expect("canonical blocked pattern-delete source")
            .as_bytes(),
    )
    .expect("write blocked pattern-delete source");
    let blocked_destination = temporary.0.join("blocked-pattern-delete-output");
    assert_success(&run_linear_load_pattern_delete(
        &blocked_source,
        &blocked_destination,
        "LC_CUSTOM",
    ));
    let blocked_receipt: Value = serde_json::from_slice(
        &std::fs::read(blocked_destination.join("edit-receipt.json"))
            .expect("blocked pattern-delete receipt"),
    )
    .expect("blocked pattern-delete receipt JSON");
    assert_eq!(blocked_receipt["analysis_ready"], false);
    assert_eq!(
        blocked_receipt["blocking_feature_ids"],
        serde_json::json!(["feature.pattern-delete-visible-not-runnable"])
    );
}

#[test]
#[allow(clippy::too_many_lines)]
fn linear_material_add_is_deterministic_cpp_revalidated_and_used_by_member_execution() {
    let temporary = TestDirectory::create();
    let source =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let source_before = std::fs::read(&source).expect("source ModelIR bytes");
    let first = temporary.0.join("linear-material-add-first");
    let second = temporary.0.join("linear-material-add-second");
    for destination in [&first, &second] {
        let output =
            run_linear_material_add(&source, destination, "M2", ["100000000000", "0.3", "2700"]);
        assert_success(&output);
        let receipt_bytes = std::fs::read(destination.join("edit-receipt.json"))
            .expect("linear-material add receipt");
        assert_eq!(output.stdout, [receipt_bytes.as_slice(), b"\n"].concat());
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(artifact)).expect("first material-add artifact"),
            std::fs::read(second.join(artifact)).expect("second material-add artifact")
        );
    }
    assert_eq!(
        std::fs::read(&source).expect("source after material addition"),
        source_before
    );
    assert_published_linear_material_add(&first);

    let baseline_member = temporary.0.join("material-add-baseline-member");
    let added_member = temporary.0.join("material-add-new-material-member");
    assert_success(&run_frame3d_member_add(
        &source,
        &baseline_member,
        "N3",
        ["4", "0", "0"],
        "E2",
        "N2",
        "M1",
        "S1",
    ));
    assert_success(&run_frame3d_member_add(
        &first.join("model-ir.json"),
        &added_member,
        "N3",
        ["4", "0", "0"],
        "E2",
        "N2",
        "M2",
        "S1",
    ));
    let baseline_supported = temporary.0.join("material-add-baseline-supported");
    let added_supported = temporary.0.join("material-add-new-material-supported");
    assert_success(&run_fixed_constraint_add(
        &baseline_member.join("model-ir.json"),
        &baseline_supported,
        "BC_N3",
        "N3",
    ));
    assert_success(&run_fixed_constraint_add(
        &added_member.join("model-ir.json"),
        &added_supported,
        "BC_N3",
        "N3",
    ));
    let added_supported_model: Value = serde_json::from_slice(
        &std::fs::read(added_supported.join("model-ir.json")).expect("composed material model"),
    )
    .expect("composed material model JSON");
    assert_eq!(added_supported_model["elements"][1]["material_id"], "M2");

    let baseline_request = temporary.0.join("material-add-baseline-request");
    let added_request = temporary.0.join("material-add-request");
    assert_success(&run_model_linear_request_create(
        &baseline_supported.join("model-ir.json"),
        &baseline_request,
        "added-linear-material-c5",
        "LC_WEAK",
    ));
    assert_success(&run_model_linear_request_create(
        &added_supported.join("model-ir.json"),
        &added_request,
        "added-linear-material-c5",
        "LC_WEAK",
    ));
    let baseline = execute_model_ir_linear_analysis(
        &std::fs::read(baseline_supported.join("model-ir.json")).expect("baseline composed model"),
        &std::fs::read(baseline_request.join("analysis-request.json")).expect("baseline request"),
        None,
        u32::MAX,
    )
    .expect("baseline material execution");
    let added = execute_model_ir_linear_analysis(
        &std::fs::read(added_supported.join("model-ir.json")).expect("new-material composed model"),
        &std::fs::read(added_request.join("analysis-request.json")).expect("new-material request"),
        None,
        u32::MAX,
    )
    .expect("new material execution");
    assert!(
        baseline.is_complete(),
        "baseline run receipt={}",
        baseline.run_receipt_json()
    );
    assert!(
        added.is_complete(),
        "new-material run receipt={}",
        added.run_receipt_json()
    );
    let baseline_recovery: Value = serde_json::from_str(
        baseline
            .result_recovery_ir_json()
            .expect("baseline material recovery"),
    )
    .expect("baseline material recovery JSON");
    let added_recovery: Value = serde_json::from_str(
        added
            .result_recovery_ir_json()
            .expect("new material recovery"),
    )
    .expect("new material recovery JSON");
    assert_eq!(
        added_recovery["active_dof_indices"],
        serde_json::json!([6, 7, 8, 9, 10, 11])
    );
    assert_eq!(
        added_recovery["active_external_load"],
        serde_json::json!([0, -10000, 0, 0, 0, 0])
    );
    assert_eq!(
        baseline_recovery["active_external_load"],
        added_recovery["active_external_load"]
    );
    assert_ne!(
        baseline_recovery["global_displacement"],
        added_recovery["global_displacement"]
    );
    assert_eq!(added_recovery["fallback_count"], 0);

    let existing = run_linear_material_add(&source, &first, "M2", ["100000000000", "0.3", "2700"]);
    assert_eq!(existing.status.code(), Some(1));
    assert!(
        String::from_utf8_lossy(&existing.stdout).contains("workbench_stage_destination_exists")
    );
    for (name, material_id, parameters, code) in [
        (
            "material-add-duplicate-id",
            "M1",
            ["100000000000", "0.3", "2700"],
            "workbench_model_add_linear_material_identity_exists",
        ),
        (
            "material-add-zero-modulus",
            "M2",
            ["0", "0.3", "2700"],
            "workbench_usage_error",
        ),
        (
            "material-add-invalid-ratio",
            "M2",
            ["100000000000", "0.5", "2700"],
            "workbench_usage_error",
        ),
        (
            "material-add-negative-density",
            "M2",
            ["100000000000", "0.3", "-1"],
            "workbench_usage_error",
        ),
        (
            "material-add-nonfinite-modulus",
            "M2",
            ["NaN", "0.3", "2700"],
            "workbench_usage_error",
        ),
    ] {
        let destination = temporary.0.join(name);
        let rejected = run_linear_material_add(&source, &destination, material_id, parameters);
        let expected_status = if code == "workbench_usage_error" {
            2
        } else {
            1
        };
        assert_eq!(rejected.status.code(), Some(expected_status));
        assert!(String::from_utf8_lossy(&rejected.stdout).contains(code));
        assert!(!destination.exists());
    }

    let mut blocked: Value = serde_json::from_slice(&source_before).expect("material source JSON");
    blocked["unsupported_features"] = serde_json::json!([{
        "feature_id": "feature.linear-material-add-visible-not-runnable",
        "kind": "unsupported_solver_feature",
        "source_entity_id": null,
        "disposition": "blocked",
        "blocking": true,
        "detail": "Material authoring must not promote unsupported solver authority.",
        "extensions": {}
    }]);
    let original_roundtrip_map = blocked["roundtrip_map"].clone();
    let blocked_source = temporary.0.join("blocked-material-add-source.json");
    std::fs::write(
        &blocked_source,
        serde_json::to_vec(&blocked).expect("blocked material-add source bytes"),
    )
    .expect("write blocked material-add source");
    let blocked_destination = temporary.0.join("blocked-material-add");
    assert_success(&run_linear_material_add(
        &blocked_source,
        &blocked_destination,
        "M2",
        ["100000000000", "0.3", "2700"],
    ));
    let blocked_receipt: Value = serde_json::from_slice(
        &std::fs::read(blocked_destination.join("edit-receipt.json"))
            .expect("blocked material-add receipt"),
    )
    .expect("blocked material-add receipt JSON");
    assert_eq!(blocked_receipt["analysis_ready"], false);
    assert_eq!(
        blocked_receipt["blocking_feature_ids"],
        serde_json::json!(["feature.linear-material-add-visible-not-runnable"])
    );
    let blocked_edited: Value = serde_json::from_slice(
        &std::fs::read(blocked_destination.join("model-ir.json"))
            .expect("blocked material-added model"),
    )
    .expect("blocked material-added JSON");
    assert_eq!(blocked_edited["roundtrip_map"], original_roundtrip_map);
}

#[test]
#[allow(clippy::too_many_lines)]
fn linear_material_deletion_is_deterministic_fail_closed_restartable_and_cpu_executable() {
    let temporary = TestDirectory::create();
    let source =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let added_directory = temporary.0.join("linear-material-delete-source");
    assert_success(&run_linear_material_add(
        &source,
        &added_directory,
        "M2",
        ["100000000000", "0.3", "2700"],
    ));
    let added_path = added_directory.join("model-ir.json");
    let added_bytes = std::fs::read(&added_path).expect("linear-material delete source bytes");
    let added = parse_model_ir_v2(&added_bytes).expect("strict material-delete source");

    let first = temporary.0.join("linear-material-delete-first");
    let second = temporary.0.join("linear-material-delete-second");
    for destination in [&first, &second] {
        let output = run_linear_material_delete(&added_path, destination, "M2");
        assert_success(&output);
        let receipt = std::fs::read(destination.join("edit-receipt.json"))
            .expect("linear-material delete receipt");
        assert_eq!(output.stdout, [receipt.as_slice(), b"\n"].concat());
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(artifact)).expect("first material-delete artifact"),
            std::fs::read(second.join(artifact)).expect("second material-delete artifact")
        );
    }
    assert_eq!(
        std::fs::read(&added_path).expect("unchanged material-delete source"),
        added_bytes
    );

    let deleted_bytes =
        std::fs::read(first.join("model-ir.json")).expect("material-deleted ModelIR");
    let deleted = parse_model_ir_v2(&deleted_bytes).expect("strict material-deleted ModelIR");
    for family in [
        "nodes",
        "sections",
        "elements",
        "constraints",
        "load_patterns",
        "load_combinations",
        "time_functions",
        "construction_stages",
        "roundtrip_map",
        "unsupported_features",
    ] {
        assert_eq!(deleted.value()[family], added.value()[family]);
    }
    let source_materials = added.value()["materials"]
        .as_array()
        .expect("source materials");
    let deleted_materials = deleted.value()["materials"]
        .as_array()
        .expect("deleted materials");
    assert_eq!(source_materials.len(), deleted_materials.len() + 1);
    assert_eq!(
        deleted_materials,
        &source_materials[..deleted_materials.len()]
    );
    assert_eq!(
        source_materials.last().expect("terminal material")["id"],
        "M2"
    );
    let extension = deleted.value()["extensions"]
        .get("structural-native:model-delete-linear-material.v1")
        .expect("linear-material delete provenance extension");
    assert_eq!(extension["operation"], "linear_material_delete");
    assert_eq!(extension["removed_material_id"], "M2");
    assert_eq!(extension["removed_material_index"], 1);
    assert_eq!(extension["removed_law_id"], "linear_elastic_isotropic");
    assert_eq!(extension["removed_parameter_set_version"], "1");
    assert_eq!(
        extension["removed_parameters_si"]["elastic_modulus_pa"]
            .as_f64()
            .expect("removed elastic modulus")
            .to_bits(),
        100_000_000_000.0_f64.to_bits()
    );
    assert_eq!(extension["removed_state_schema"]["stateful"], false);
    let mut receipt: Value = serde_json::from_slice(
        &std::fs::read(first.join("edit-receipt.json")).expect("linear-material delete receipt"),
    )
    .expect("linear-material delete receipt JSON");
    assert_eq!(receipt["operation"], "linear_material_delete");
    assert_eq!(receipt["removed_material_id"], "M2");
    assert_eq!(receipt["removed_material_index"], 1);
    assert_eq!(receipt["cpp_semantic_snapshot_verified"], true);
    assert_eq!(receipt["analysis_ready"], true);
    assert_eq!(receipt["edited_content_hash"], deleted.content_hash());
    assert_self_hashed_edit_receipt(&mut receipt);

    let request_directory = temporary.0.join("linear-material-delete-request");
    assert_success(&run_model_linear_request_create(
        &first.join("model-ir.json"),
        &request_directory,
        "linear-material-delete-c5",
        "LC_WEAK",
    ));
    let request_bytes = std::fs::read(request_directory.join("analysis-request.json"))
        .expect("material-delete request");
    let direct = execute_model_ir_linear_analysis(&deleted_bytes, &request_bytes, None, u32::MAX)
        .expect("material-delete direct execution");
    assert!(direct.is_complete());
    let recovery: Value = serde_json::from_str(
        direct
            .result_recovery_ir_json()
            .expect("material-delete direct recovery"),
    )
    .expect("material-delete recovery JSON");
    assert_eq!(
        recovery["active_dof_indices"],
        serde_json::json!([6, 7, 8, 9, 10, 11])
    );
    assert_eq!(
        recovery["active_external_load"],
        serde_json::json!([0, -10000, 0, 0, 0, 0])
    );
    assert_eq!(recovery["recovery_stable_indices"], serde_json::json!([0]));
    assert_eq!(recovery["recovery_element_types"], serde_json::json!([1]));
    assert_eq!(recovery["recovery_offsets"], serde_json::json!([0, 12]));
    assert_eq!(recovery["fallback_count"], 0);
    let partial = execute_model_ir_linear_analysis(&deleted_bytes, &request_bytes, None, 0)
        .expect("material-delete partial execution");
    assert!(!partial.is_complete());
    let resumed = execute_model_ir_linear_analysis(
        &deleted_bytes,
        &request_bytes,
        Some(partial.checkpoint_bytes()),
        u32::MAX,
    )
    .expect("material-delete resumed execution");
    assert!(resumed.is_complete());
    assert_eq!(resumed.result_ir_json(), direct.result_ir_json());
    assert_eq!(
        resumed.result_recovery_ir_json(),
        direct.result_recovery_ir_json()
    );

    let referenced_directory = temporary.0.join("linear-material-delete-referenced-source");
    assert_success(&run_frame3d_member_add(
        &added_path,
        &referenced_directory,
        "N3",
        ["4", "0", "0"],
        "E2",
        "N2",
        "M2",
        "S1",
    ));
    let referenced_destination = temporary.0.join("linear-material-delete-referenced");
    let referenced = run_linear_material_delete(
        &referenced_directory.join("model-ir.json"),
        &referenced_destination,
        "M2",
    );
    assert_eq!(referenced.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&referenced.stdout)
        .contains("workbench_model_delete_linear_material_referenced_by_element"));
    assert!(!referenced_destination.exists());

    let later_directory = temporary.0.join("linear-material-delete-later-source");
    assert_success(&run_linear_material_add(
        &added_path,
        &later_directory,
        "M3",
        ["70000000000", "0.33", "2700"],
    ));
    let nonterminal_destination = temporary.0.join("linear-material-delete-nonterminal");
    let nonterminal = run_linear_material_delete(
        &later_directory.join("model-ir.json"),
        &nonterminal_destination,
        "M2",
    );
    assert_eq!(nonterminal.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&nonterminal.stdout)
        .contains("workbench_model_delete_linear_material_not_terminal"));
    assert!(!nonterminal_destination.exists());

    let mut source_owned = added.value().clone();
    source_owned["materials"][1]["source_id"] = serde_json::json!("source:M2");
    let source_owned_path = temporary.0.join("linear-material-delete-source-owned.json");
    std::fs::write(
        &source_owned_path,
        canonicalize_model_ir_v2(&source_owned)
            .expect("canonical source-owned material")
            .as_bytes(),
    )
    .expect("write source-owned material");
    let source_owned_destination = temporary.0.join("linear-material-delete-source-owned");
    let source_owned_rejection =
        run_linear_material_delete(&source_owned_path, &source_owned_destination, "M2");
    assert_eq!(source_owned_rejection.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&source_owned_rejection.stdout)
        .contains("workbench_model_delete_linear_material_source_owned"));
    assert!(!source_owned_destination.exists());

    for (name, field, value, code) in [
        (
            "feature-owned",
            "unsupported_features",
            serde_json::json!([{
                "feature_id": "feature.material-delete-owned",
                "kind": "source_owned_material",
                "source_entity_id": "M2",
                "disposition": "preserved_only",
                "blocking": false,
                "detail": "The source feature directly owns the candidate material.",
                "extensions": {}
            }]),
            "workbench_model_delete_linear_material_unsupported_feature_owned",
        ),
        (
            "roundtrip-owned",
            "roundtrip_map",
            serde_json::json!([{
                "source_entity_id": "source:M2",
                "entity_kind": "material",
                "model_ir_entity_id": "M2",
                "mapping_status": "exact",
                "extensions": {}
            }]),
            "workbench_model_delete_linear_material_roundtrip_owned",
        ),
    ] {
        let mut guarded = added.value().clone();
        guarded[field] = value;
        let guarded_path = temporary
            .0
            .join(format!("linear-material-delete-{name}.json"));
        std::fs::write(
            &guarded_path,
            canonicalize_model_ir_v2(&guarded)
                .expect("canonical guarded material-delete source")
                .as_bytes(),
        )
        .expect("write guarded material-delete source");
        let destination = temporary.0.join(format!("linear-material-delete-{name}"));
        let rejection = run_linear_material_delete(&guarded_path, &destination, "M2");
        assert_eq!(rejection.status.code(), Some(1));
        assert!(String::from_utf8_lossy(&rejection.stdout).contains(code));
        assert!(!destination.exists());
    }

    let minimum_destination = temporary.0.join("linear-material-delete-minimum");
    let minimum = run_linear_material_delete(&source, &minimum_destination, "M1");
    assert_eq!(minimum.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&minimum.stdout)
        .contains("workbench_model_delete_linear_material_minimum_model"));
    assert!(!minimum_destination.exists());

    let existing = run_linear_material_delete(&added_path, &first, "M2");
    assert_eq!(existing.status.code(), Some(1));
    assert!(
        String::from_utf8_lossy(&existing.stdout).contains("workbench_stage_destination_exists")
    );

    let mut blocked = added.value().clone();
    blocked["unsupported_features"] = serde_json::json!([{
        "feature_id": "feature.material-delete-visible-not-runnable",
        "kind": "unsupported_solver_feature",
        "source_entity_id": null,
        "disposition": "blocked",
        "blocking": true,
        "detail": "Material deletion must preserve unsupported solver blockers.",
        "extensions": {}
    }]);
    let blocked_source = temporary.0.join("blocked-material-delete-source.json");
    std::fs::write(
        &blocked_source,
        canonicalize_model_ir_v2(&blocked)
            .expect("canonical blocked material-delete source")
            .as_bytes(),
    )
    .expect("write blocked material-delete source");
    let blocked_destination = temporary.0.join("blocked-material-delete-output");
    assert_success(&run_linear_material_delete(
        &blocked_source,
        &blocked_destination,
        "M2",
    ));
    let blocked_receipt: Value = serde_json::from_slice(
        &std::fs::read(blocked_destination.join("edit-receipt.json"))
            .expect("blocked material-delete receipt"),
    )
    .expect("blocked material-delete receipt JSON");
    assert_eq!(blocked_receipt["analysis_ready"], false);
    assert_eq!(
        blocked_receipt["blocking_feature_ids"],
        serde_json::json!(["feature.material-delete-visible-not-runnable"])
    );
}

#[test]
#[allow(clippy::too_many_lines)]
fn frame_section_add_is_deterministic_cpp_revalidated_and_used_by_member_execution() {
    let temporary = TestDirectory::create();
    let source =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let source_before = std::fs::read(&source).expect("source ModelIR bytes");
    let first = temporary.0.join("frame-section-add-first");
    let second = temporary.0.join("frame-section-add-second");
    let parameters = ["0.01", "0.00004", "0.000025", "0.000005", "0.008", "0.008"];
    for destination in [&first, &second] {
        let output = run_frame_section_add(&source, destination, "S2", parameters);
        assert_success(&output);
        let receipt_bytes = std::fs::read(destination.join("edit-receipt.json"))
            .expect("frame-section add receipt");
        assert_eq!(output.stdout, [receipt_bytes.as_slice(), b"\n"].concat());
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(artifact)).expect("first section-add artifact"),
            std::fs::read(second.join(artifact)).expect("second section-add artifact")
        );
    }
    assert_eq!(
        std::fs::read(&source).expect("source after section addition"),
        source_before
    );
    assert_published_frame_section_add(&first);

    let baseline_member = temporary.0.join("section-add-baseline-member");
    let added_member = temporary.0.join("section-add-new-section-member");
    assert_success(&run_frame3d_member_add(
        &source,
        &baseline_member,
        "N3",
        ["4", "0", "0"],
        "E2",
        "N2",
        "M1",
        "S1",
    ));
    assert_success(&run_frame3d_member_add(
        &first.join("model-ir.json"),
        &added_member,
        "N3",
        ["4", "0", "0"],
        "E2",
        "N2",
        "M1",
        "S2",
    ));
    let baseline_supported = temporary.0.join("section-add-baseline-supported");
    let added_supported = temporary.0.join("section-add-new-section-supported");
    assert_success(&run_fixed_constraint_add(
        &baseline_member.join("model-ir.json"),
        &baseline_supported,
        "BC_N3",
        "N3",
    ));
    assert_success(&run_fixed_constraint_add(
        &added_member.join("model-ir.json"),
        &added_supported,
        "BC_N3",
        "N3",
    ));
    let added_supported_model: Value = serde_json::from_slice(
        &std::fs::read(added_supported.join("model-ir.json")).expect("composed section model"),
    )
    .expect("composed section model JSON");
    assert_eq!(added_supported_model["elements"][1]["section_id"], "S2");

    let baseline_request = temporary.0.join("section-add-baseline-request");
    let added_request = temporary.0.join("section-add-request");
    assert_success(&run_model_linear_request_create(
        &baseline_supported.join("model-ir.json"),
        &baseline_request,
        "added-frame-section-c5",
        "LC_WEAK",
    ));
    assert_success(&run_model_linear_request_create(
        &added_supported.join("model-ir.json"),
        &added_request,
        "added-frame-section-c5",
        "LC_WEAK",
    ));
    let baseline = execute_model_ir_linear_analysis(
        &std::fs::read(baseline_supported.join("model-ir.json")).expect("baseline composed model"),
        &std::fs::read(baseline_request.join("analysis-request.json")).expect("baseline request"),
        None,
        u32::MAX,
    )
    .expect("baseline section execution");
    let added = execute_model_ir_linear_analysis(
        &std::fs::read(added_supported.join("model-ir.json")).expect("new-section composed model"),
        &std::fs::read(added_request.join("analysis-request.json")).expect("new-section request"),
        None,
        u32::MAX,
    )
    .expect("new section execution");
    assert!(
        baseline.is_complete(),
        "baseline run receipt={}",
        baseline.run_receipt_json()
    );
    assert!(
        added.is_complete(),
        "new-section run receipt={}",
        added.run_receipt_json()
    );
    let baseline_recovery: Value = serde_json::from_str(
        baseline
            .result_recovery_ir_json()
            .expect("baseline section recovery"),
    )
    .expect("baseline section recovery JSON");
    let added_recovery: Value = serde_json::from_str(
        added
            .result_recovery_ir_json()
            .expect("new section recovery"),
    )
    .expect("new section recovery JSON");
    assert_eq!(
        added_recovery["active_dof_indices"],
        serde_json::json!([6, 7, 8, 9, 10, 11])
    );
    assert_eq!(
        added_recovery["active_external_load"],
        serde_json::json!([0, -10000, 0, 0, 0, 0])
    );
    assert_eq!(
        baseline_recovery["active_external_load"],
        added_recovery["active_external_load"]
    );
    assert_ne!(
        baseline_recovery["global_displacement"],
        added_recovery["global_displacement"]
    );
    assert_eq!(added_recovery["fallback_count"], 0);

    let existing = run_frame_section_add(&source, &first, "S2", parameters);
    assert_eq!(existing.status.code(), Some(1));
    assert!(
        String::from_utf8_lossy(&existing.stdout).contains("workbench_stage_destination_exists")
    );
    for (name, section_id, rejected_parameters, code) in [
        (
            "frame-section-add-duplicate-id",
            "S1",
            parameters,
            "workbench_model_add_frame_section_identity_exists",
        ),
        (
            "frame-section-add-zero-area",
            "S2",
            ["0", "0.00004", "0.000025", "0.000005", "0.008", "0.008"],
            "workbench_usage_error",
        ),
        (
            "frame-section-add-nonfinite-inertia",
            "S2",
            ["0.01", "NaN", "0.000025", "0.000005", "0.008", "0.008"],
            "workbench_usage_error",
        ),
    ] {
        let destination = temporary.0.join(name);
        let rejected =
            run_frame_section_add(&source, &destination, section_id, rejected_parameters);
        let expected_status = if code == "workbench_usage_error" {
            2
        } else {
            1
        };
        assert_eq!(rejected.status.code(), Some(expected_status));
        assert!(String::from_utf8_lossy(&rejected.stdout).contains(code));
        assert!(!destination.exists());
    }

    let mut blocked: Value = serde_json::from_slice(&source_before).expect("section source JSON");
    blocked["unsupported_features"] = serde_json::json!([{
        "feature_id": "feature.frame-section-add-visible-not-runnable",
        "kind": "unsupported_solver_feature",
        "source_entity_id": null,
        "disposition": "blocked",
        "blocking": true,
        "detail": "Section authoring must not promote unsupported solver authority.",
        "extensions": {}
    }]);
    let original_roundtrip_map = blocked["roundtrip_map"].clone();
    let blocked_source = temporary.0.join("blocked-section-add-source.json");
    std::fs::write(
        &blocked_source,
        serde_json::to_vec(&blocked).expect("blocked section-add source bytes"),
    )
    .expect("write blocked section-add source");
    let blocked_destination = temporary.0.join("blocked-section-add");
    assert_success(&run_frame_section_add(
        &blocked_source,
        &blocked_destination,
        "S2",
        parameters,
    ));
    let blocked_receipt: Value = serde_json::from_slice(
        &std::fs::read(blocked_destination.join("edit-receipt.json"))
            .expect("blocked section-add receipt"),
    )
    .expect("blocked section-add receipt JSON");
    assert_eq!(blocked_receipt["analysis_ready"], false);
    assert_eq!(
        blocked_receipt["blocking_feature_ids"],
        serde_json::json!(["feature.frame-section-add-visible-not-runnable"])
    );
    let blocked_edited: Value = serde_json::from_slice(
        &std::fs::read(blocked_destination.join("model-ir.json"))
            .expect("blocked section-added model"),
    )
    .expect("blocked section-added JSON");
    assert_eq!(blocked_edited["roundtrip_map"], original_roundtrip_map);
}

#[test]
#[allow(clippy::too_many_lines)]
fn frame_section_deletion_is_deterministic_fail_closed_restartable_and_cpu_executable() {
    let temporary = TestDirectory::create();
    let source =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let parameters = ["0.01", "0.00004", "0.000025", "0.000005", "0.008", "0.008"];
    let added_directory = temporary.0.join("frame-section-delete-source");
    assert_success(&run_frame_section_add(
        &source,
        &added_directory,
        "S2",
        parameters,
    ));
    let added_path = added_directory.join("model-ir.json");
    let added_bytes = std::fs::read(&added_path).expect("frame-section delete source bytes");
    let added = parse_model_ir_v2(&added_bytes).expect("strict frame-section-delete source");

    let first = temporary.0.join("frame-section-delete-first");
    let second = temporary.0.join("frame-section-delete-second");
    for destination in [&first, &second] {
        let output = run_frame_section_delete(&added_path, destination, "S2");
        assert_success(&output);
        let receipt = std::fs::read(destination.join("edit-receipt.json"))
            .expect("frame-section delete receipt");
        assert_eq!(output.stdout, [receipt.as_slice(), b"\n"].concat());
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(artifact)).expect("first frame-section-delete artifact"),
            std::fs::read(second.join(artifact)).expect("second frame-section-delete artifact")
        );
    }
    assert_eq!(
        std::fs::read(&added_path).expect("unchanged frame-section-delete source"),
        added_bytes
    );

    let deleted_bytes =
        std::fs::read(first.join("model-ir.json")).expect("frame-section-deleted ModelIR");
    let deleted = parse_model_ir_v2(&deleted_bytes).expect("strict frame-section-deleted ModelIR");
    for family in [
        "nodes",
        "materials",
        "elements",
        "constraints",
        "load_patterns",
        "load_combinations",
        "time_functions",
        "construction_stages",
        "roundtrip_map",
        "unsupported_features",
    ] {
        assert_eq!(deleted.value()[family], added.value()[family]);
    }
    let source_sections = added.value()["sections"]
        .as_array()
        .expect("source sections");
    let deleted_sections = deleted.value()["sections"]
        .as_array()
        .expect("deleted sections");
    assert_eq!(source_sections.len(), deleted_sections.len() + 1);
    assert_eq!(deleted_sections, &source_sections[..deleted_sections.len()]);
    assert_eq!(
        source_sections.last().expect("terminal section")["id"],
        "S2"
    );
    let extension = deleted.value()["extensions"]
        .get("structural-native:model-delete-frame-section.v1")
        .expect("frame-section delete provenance extension");
    assert_eq!(extension["operation"], "frame_section_delete");
    assert_eq!(extension["removed_section_id"], "S2");
    assert_eq!(extension["removed_section_index"], 1);
    assert_eq!(extension["removed_family_id"], "frame_3d");
    assert_eq!(extension["removed_parameter_set_version"], "1");
    assert_eq!(extension["removed_parameters_si"]["area_m2"], 0.01);
    let mut receipt: Value = serde_json::from_slice(
        &std::fs::read(first.join("edit-receipt.json")).expect("frame-section delete receipt"),
    )
    .expect("frame-section delete receipt JSON");
    assert_eq!(receipt["operation"], "frame_section_delete");
    assert_eq!(receipt["removed_section_id"], "S2");
    assert_eq!(receipt["removed_section_index"], 1);
    assert_eq!(receipt["cpp_semantic_snapshot_verified"], true);
    assert_eq!(receipt["analysis_ready"], true);
    assert_eq!(receipt["edited_content_hash"], deleted.content_hash());
    assert_self_hashed_edit_receipt(&mut receipt);

    let request_directory = temporary.0.join("frame-section-delete-request");
    assert_success(&run_model_linear_request_create(
        &first.join("model-ir.json"),
        &request_directory,
        "frame-section-delete-c5",
        "LC_WEAK",
    ));
    let request_bytes = std::fs::read(request_directory.join("analysis-request.json"))
        .expect("frame-section-delete request");
    let direct = execute_model_ir_linear_analysis(&deleted_bytes, &request_bytes, None, u32::MAX)
        .expect("frame-section-delete direct execution");
    assert!(direct.is_complete());
    let recovery: Value = serde_json::from_str(
        direct
            .result_recovery_ir_json()
            .expect("frame-section-delete direct recovery"),
    )
    .expect("frame-section-delete recovery JSON");
    assert_eq!(
        recovery["active_dof_indices"],
        serde_json::json!([6, 7, 8, 9, 10, 11])
    );
    assert_eq!(
        recovery["active_external_load"],
        serde_json::json!([0, -10000, 0, 0, 0, 0])
    );
    assert_eq!(recovery["recovery_stable_indices"], serde_json::json!([0]));
    assert_eq!(recovery["recovery_element_types"], serde_json::json!([1]));
    assert_eq!(recovery["recovery_offsets"], serde_json::json!([0, 12]));
    assert_eq!(recovery["fallback_count"], 0);
    let partial = execute_model_ir_linear_analysis(&deleted_bytes, &request_bytes, None, 0)
        .expect("frame-section-delete partial execution");
    assert!(!partial.is_complete());
    let resumed = execute_model_ir_linear_analysis(
        &deleted_bytes,
        &request_bytes,
        Some(partial.checkpoint_bytes()),
        u32::MAX,
    )
    .expect("frame-section-delete resumed execution");
    assert!(resumed.is_complete());
    assert_eq!(resumed.result_ir_json(), direct.result_ir_json());
    assert_eq!(
        resumed.result_recovery_ir_json(),
        direct.result_recovery_ir_json()
    );

    let referenced_directory = temporary.0.join("frame-section-delete-referenced-source");
    assert_success(&run_frame3d_member_add(
        &added_path,
        &referenced_directory,
        "N3",
        ["4", "0", "0"],
        "E2",
        "N2",
        "M1",
        "S2",
    ));
    let referenced_destination = temporary.0.join("frame-section-delete-referenced");
    let referenced = run_frame_section_delete(
        &referenced_directory.join("model-ir.json"),
        &referenced_destination,
        "S2",
    );
    assert_eq!(referenced.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&referenced.stdout)
        .contains("workbench_model_delete_frame_section_referenced_by_element"));
    assert!(!referenced_destination.exists());

    let later_directory = temporary.0.join("frame-section-delete-later-source");
    assert_success(&run_frame_section_add(
        &added_path,
        &later_directory,
        "S3",
        parameters,
    ));
    let nonterminal_destination = temporary.0.join("frame-section-delete-nonterminal");
    let nonterminal = run_frame_section_delete(
        &later_directory.join("model-ir.json"),
        &nonterminal_destination,
        "S2",
    );
    assert_eq!(nonterminal.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&nonterminal.stdout)
        .contains("workbench_model_delete_frame_section_not_terminal"));
    assert!(!nonterminal_destination.exists());

    let mut source_owned = added.value().clone();
    source_owned["sections"][1]["source_id"] = serde_json::json!("source:S2");
    let source_owned_path = temporary.0.join("frame-section-delete-source-owned.json");
    std::fs::write(
        &source_owned_path,
        canonicalize_model_ir_v2(&source_owned)
            .expect("canonical source-owned frame section")
            .as_bytes(),
    )
    .expect("write source-owned frame section");
    let source_owned_destination = temporary.0.join("frame-section-delete-source-owned");
    let source_owned_rejection =
        run_frame_section_delete(&source_owned_path, &source_owned_destination, "S2");
    assert_eq!(source_owned_rejection.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&source_owned_rejection.stdout)
        .contains("workbench_model_delete_frame_section_source_owned"));
    assert!(!source_owned_destination.exists());

    for (name, field, value, code) in [
        (
            "feature-owned",
            "unsupported_features",
            serde_json::json!([{
                "feature_id": "feature.frame-section-delete-owned",
                "kind": "source_owned_section",
                "source_entity_id": "S2",
                "disposition": "preserved_only",
                "blocking": false,
                "detail": "The source feature directly owns the candidate frame section.",
                "extensions": {}
            }]),
            "workbench_model_delete_frame_section_unsupported_feature_owned",
        ),
        (
            "roundtrip-owned",
            "roundtrip_map",
            serde_json::json!([{
                "source_entity_id": "source:S2",
                "entity_kind": "section",
                "model_ir_entity_id": "S2",
                "mapping_status": "exact",
                "extensions": {}
            }]),
            "workbench_model_delete_frame_section_roundtrip_owned",
        ),
    ] {
        let mut guarded = added.value().clone();
        guarded[field] = value;
        let guarded_path = temporary
            .0
            .join(format!("frame-section-delete-{name}.json"));
        std::fs::write(
            &guarded_path,
            canonicalize_model_ir_v2(&guarded)
                .expect("canonical guarded frame-section-delete source")
                .as_bytes(),
        )
        .expect("write guarded frame-section-delete source");
        let destination = temporary.0.join(format!("frame-section-delete-{name}"));
        let rejection = run_frame_section_delete(&guarded_path, &destination, "S2");
        assert_eq!(rejection.status.code(), Some(1));
        assert!(String::from_utf8_lossy(&rejection.stdout).contains(code));
        assert!(!destination.exists());
    }

    let minimum_destination = temporary.0.join("frame-section-delete-minimum");
    let minimum = run_frame_section_delete(&source, &minimum_destination, "S1");
    assert_eq!(minimum.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&minimum.stdout)
        .contains("workbench_model_delete_frame_section_minimum_model"));
    assert!(!minimum_destination.exists());

    let existing = run_frame_section_delete(&added_path, &first, "S2");
    assert_eq!(existing.status.code(), Some(1));
    assert!(
        String::from_utf8_lossy(&existing.stdout).contains("workbench_stage_destination_exists")
    );

    let mut blocked = added.value().clone();
    blocked["unsupported_features"] = serde_json::json!([{
        "feature_id": "feature.frame-section-delete-visible-not-runnable",
        "kind": "unsupported_solver_feature",
        "source_entity_id": null,
        "disposition": "blocked",
        "blocking": true,
        "detail": "Frame-section deletion must preserve unsupported solver blockers.",
        "extensions": {}
    }]);
    let blocked_source = temporary.0.join("blocked-frame-section-delete-source.json");
    std::fs::write(
        &blocked_source,
        canonicalize_model_ir_v2(&blocked)
            .expect("canonical blocked frame-section-delete source")
            .as_bytes(),
    )
    .expect("write blocked frame-section-delete source");
    let blocked_destination = temporary.0.join("blocked-frame-section-delete-output");
    assert_success(&run_frame_section_delete(
        &blocked_source,
        &blocked_destination,
        "S2",
    ));
    let blocked_receipt: Value = serde_json::from_slice(
        &std::fs::read(blocked_destination.join("edit-receipt.json"))
            .expect("blocked frame-section-delete receipt"),
    )
    .expect("blocked frame-section-delete receipt JSON");
    assert_eq!(blocked_receipt["analysis_ready"], false);
    assert_eq!(
        blocked_receipt["blocking_feature_ids"],
        serde_json::json!(["feature.frame-section-delete-visible-not-runnable"])
    );
}

#[test]
#[allow(clippy::too_many_lines)]
fn truss_section_deletion_is_deterministic_fail_closed_restartable_and_cpu_executable() {
    let temporary = TestDirectory::create();
    let source =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let retained_directory = temporary.0.join("truss-section-delete-retained");
    assert_success(&run_truss_section_add(
        &source,
        &retained_directory,
        "T1",
        "0.005",
    ));
    let member_directory = temporary.0.join("truss-section-delete-member");
    assert_success(&run_truss3d_member_add(
        &retained_directory.join("model-ir.json"),
        &member_directory,
        "N3",
        ["2", "1", "0"],
        "E2",
        "N2",
        "M1",
        "T1",
    ));
    let supported_directory = temporary.0.join("truss-section-delete-supported");
    assert_success(&run_fixed_constraint_add(
        &member_directory.join("model-ir.json"),
        &supported_directory,
        "BC_N3",
        "N3",
    ));
    let added_directory = temporary.0.join("truss-section-delete-source");
    assert_success(&run_truss_section_add(
        &supported_directory.join("model-ir.json"),
        &added_directory,
        "T2",
        "0.0025",
    ));
    let added_path = added_directory.join("model-ir.json");
    let added_bytes = std::fs::read(&added_path).expect("truss-section delete source bytes");
    let added = parse_model_ir_v2(&added_bytes).expect("strict truss-section-delete source");

    let first = temporary.0.join("truss-section-delete-first");
    let second = temporary.0.join("truss-section-delete-second");
    for destination in [&first, &second] {
        let output = run_truss_section_delete(&added_path, destination, "T2");
        assert_success(&output);
        let receipt = std::fs::read(destination.join("edit-receipt.json"))
            .expect("truss-section delete receipt");
        assert_eq!(output.stdout, [receipt.as_slice(), b"\n"].concat());
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(artifact)).expect("first truss-section-delete artifact"),
            std::fs::read(second.join(artifact)).expect("second truss-section-delete artifact")
        );
    }
    assert_eq!(
        std::fs::read(&added_path).expect("unchanged truss-section-delete source"),
        added_bytes
    );

    let deleted_bytes =
        std::fs::read(first.join("model-ir.json")).expect("truss-section-deleted ModelIR");
    let deleted = parse_model_ir_v2(&deleted_bytes).expect("strict truss-section-deleted ModelIR");
    for family in [
        "nodes",
        "materials",
        "elements",
        "constraints",
        "load_patterns",
        "load_combinations",
        "time_functions",
        "construction_stages",
        "roundtrip_map",
        "unsupported_features",
    ] {
        assert_eq!(deleted.value()[family], added.value()[family]);
    }
    let source_sections = added.value()["sections"]
        .as_array()
        .expect("source sections");
    let deleted_sections = deleted.value()["sections"]
        .as_array()
        .expect("deleted sections");
    assert_eq!(source_sections.len(), deleted_sections.len() + 1);
    assert_eq!(deleted_sections, &source_sections[..deleted_sections.len()]);
    assert_eq!(deleted_sections[1]["id"], "T1");
    assert_eq!(
        source_sections.last().expect("terminal section")["id"],
        "T2"
    );
    let extension = deleted.value()["extensions"]
        .get("structural-native:model-delete-truss-section.v1")
        .expect("truss-section delete provenance extension");
    assert_eq!(extension["operation"], "truss_section_delete");
    assert_eq!(extension["removed_section_id"], "T2");
    assert_eq!(extension["removed_section_index"], 2);
    assert_eq!(extension["removed_family_id"], "truss_3d");
    assert_eq!(extension["removed_parameter_set_version"], "1");
    assert_eq!(extension["removed_parameters_si"]["area_m2"], 0.0025);
    let mut receipt: Value = serde_json::from_slice(
        &std::fs::read(first.join("edit-receipt.json")).expect("truss-section delete receipt"),
    )
    .expect("truss-section delete receipt JSON");
    assert_eq!(receipt["operation"], "truss_section_delete");
    assert_eq!(receipt["removed_section_id"], "T2");
    assert_eq!(receipt["removed_section_index"], 2);
    assert_eq!(
        receipt["removed_parameters_si"],
        serde_json::json!({"area_m2": 0.0025})
    );
    assert_eq!(receipt["cpp_semantic_snapshot_verified"], true);
    assert_eq!(receipt["analysis_ready"], true);
    assert_eq!(receipt["edited_content_hash"], deleted.content_hash());
    assert_self_hashed_edit_receipt(&mut receipt);

    let request_directory = temporary.0.join("truss-section-delete-request");
    assert_success(&run_model_linear_request_create(
        &first.join("model-ir.json"),
        &request_directory,
        "truss-section-delete-c5",
        "LC_WEAK",
    ));
    let request_bytes = std::fs::read(request_directory.join("analysis-request.json"))
        .expect("truss-section-delete request");
    let direct = execute_model_ir_linear_analysis(&deleted_bytes, &request_bytes, None, u32::MAX)
        .expect("truss-section-delete direct execution");
    assert!(direct.is_complete());
    let recovery: Value = serde_json::from_str(
        direct
            .result_recovery_ir_json()
            .expect("truss-section-delete direct recovery"),
    )
    .expect("truss-section-delete recovery JSON");
    assert_eq!(
        recovery["active_dof_indices"],
        serde_json::json!([6, 7, 8, 9, 10, 11])
    );
    assert_eq!(
        recovery["active_external_load"],
        serde_json::json!([0, -10000, 0, 0, 0, 0])
    );
    assert_eq!(
        recovery["recovery_stable_indices"],
        serde_json::json!([0, 1])
    );
    assert_eq!(
        recovery["recovery_element_types"],
        serde_json::json!([1, 2])
    );
    assert_eq!(recovery["recovery_offsets"], serde_json::json!([0, 12, 15]));
    assert_eq!(recovery["fallback_count"], 0);
    let partial = execute_model_ir_linear_analysis(&deleted_bytes, &request_bytes, None, 0)
        .expect("truss-section-delete partial execution");
    assert!(!partial.is_complete());
    let resumed = execute_model_ir_linear_analysis(
        &deleted_bytes,
        &request_bytes,
        Some(partial.checkpoint_bytes()),
        u32::MAX,
    )
    .expect("truss-section-delete resumed execution");
    assert!(resumed.is_complete());
    assert_eq!(resumed.result_ir_json(), direct.result_ir_json());
    assert_eq!(
        resumed.result_recovery_ir_json(),
        direct.result_recovery_ir_json()
    );

    let referenced_directory = temporary.0.join("truss-section-delete-referenced-source");
    assert_success(&run_truss_element_properties_edit(
        &added_path,
        &referenced_directory,
        "E2",
        "M1",
        "T2",
    ));
    let referenced_destination = temporary.0.join("truss-section-delete-referenced");
    let referenced = run_truss_section_delete(
        &referenced_directory.join("model-ir.json"),
        &referenced_destination,
        "T2",
    );
    assert_eq!(referenced.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&referenced.stdout)
        .contains("workbench_model_delete_truss_section_referenced_by_element"));
    assert!(!referenced_destination.exists());

    let later_directory = temporary.0.join("truss-section-delete-later-source");
    assert_success(&run_truss_section_add(
        &added_path,
        &later_directory,
        "T3",
        "0.001",
    ));
    let nonterminal_destination = temporary.0.join("truss-section-delete-nonterminal");
    let nonterminal = run_truss_section_delete(
        &later_directory.join("model-ir.json"),
        &nonterminal_destination,
        "T2",
    );
    assert_eq!(nonterminal.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&nonterminal.stdout)
        .contains("workbench_model_delete_truss_section_not_terminal"));
    assert!(!nonterminal_destination.exists());

    let mut source_owned = added.value().clone();
    source_owned["sections"][2]["source_id"] = serde_json::json!("source:T2");
    let source_owned_path = temporary.0.join("truss-section-delete-source-owned.json");
    std::fs::write(
        &source_owned_path,
        canonicalize_model_ir_v2(&source_owned)
            .expect("canonical source-owned truss section")
            .as_bytes(),
    )
    .expect("write source-owned truss section");
    let source_owned_destination = temporary.0.join("truss-section-delete-source-owned");
    let source_owned_rejection =
        run_truss_section_delete(&source_owned_path, &source_owned_destination, "T2");
    assert_eq!(source_owned_rejection.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&source_owned_rejection.stdout)
        .contains("workbench_model_delete_truss_section_source_owned"));
    assert!(!source_owned_destination.exists());

    for (name, field, value, code) in [
        (
            "feature-owned",
            "unsupported_features",
            serde_json::json!([{
                "feature_id": "feature.truss-section-delete-owned",
                "kind": "source_owned_section",
                "source_entity_id": "T2",
                "disposition": "preserved_only",
                "blocking": false,
                "detail": "The source feature directly owns the candidate truss section.",
                "extensions": {}
            }]),
            "workbench_model_delete_truss_section_unsupported_feature_owned",
        ),
        (
            "roundtrip-owned",
            "roundtrip_map",
            serde_json::json!([{
                "source_entity_id": "source:T2",
                "entity_kind": "section",
                "model_ir_entity_id": "T2",
                "mapping_status": "exact",
                "extensions": {}
            }]),
            "workbench_model_delete_truss_section_roundtrip_owned",
        ),
    ] {
        let mut guarded = added.value().clone();
        guarded[field] = value;
        let guarded_path = temporary
            .0
            .join(format!("truss-section-delete-{name}.json"));
        std::fs::write(
            &guarded_path,
            canonicalize_model_ir_v2(&guarded)
                .expect("canonical guarded truss-section-delete source")
                .as_bytes(),
        )
        .expect("write guarded truss-section-delete source");
        let destination = temporary.0.join(format!("truss-section-delete-{name}"));
        let rejection = run_truss_section_delete(&guarded_path, &destination, "T2");
        assert_eq!(rejection.status.code(), Some(1));
        assert!(String::from_utf8_lossy(&rejection.stdout).contains(code));
        assert!(!destination.exists());
    }

    let minimum_destination = temporary.0.join("truss-section-delete-minimum");
    let minimum = run_truss_section_delete(
        &supported_directory.join("model-ir.json"),
        &minimum_destination,
        "T1",
    );
    assert_eq!(minimum.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&minimum.stdout)
        .contains("workbench_model_delete_truss_section_minimum_family"));
    assert!(!minimum_destination.exists());

    let existing = run_truss_section_delete(&added_path, &first, "T2");
    assert_eq!(existing.status.code(), Some(1));
    assert!(
        String::from_utf8_lossy(&existing.stdout).contains("workbench_stage_destination_exists")
    );

    let mut blocked = added.value().clone();
    blocked["unsupported_features"] = serde_json::json!([{
        "feature_id": "feature.truss-section-delete-visible-not-runnable",
        "kind": "unsupported_solver_feature",
        "source_entity_id": null,
        "disposition": "blocked",
        "blocking": true,
        "detail": "Truss-section deletion must preserve unsupported solver blockers.",
        "extensions": {}
    }]);
    let blocked_source = temporary.0.join("blocked-truss-section-delete-source.json");
    std::fs::write(
        &blocked_source,
        canonicalize_model_ir_v2(&blocked)
            .expect("canonical blocked truss-section-delete source")
            .as_bytes(),
    )
    .expect("write blocked truss-section-delete source");
    let blocked_destination = temporary.0.join("blocked-truss-section-delete-output");
    assert_success(&run_truss_section_delete(
        &blocked_source,
        &blocked_destination,
        "T2",
    ));
    let blocked_receipt: Value = serde_json::from_slice(
        &std::fs::read(blocked_destination.join("edit-receipt.json"))
            .expect("blocked truss-section-delete receipt"),
    )
    .expect("blocked truss-section-delete receipt JSON");
    assert_eq!(blocked_receipt["analysis_ready"], false);
    assert_eq!(
        blocked_receipt["blocking_feature_ids"],
        serde_json::json!(["feature.truss-section-delete-visible-not-runnable"])
    );
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
fn truss3d_authoring_is_deterministic_fail_closed_restartable_and_cpu_executable() {
    let temporary = TestDirectory::create();
    let source =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let source_before = std::fs::read(&source).expect("truss authoring source bytes");
    let source_value: Value =
        serde_json::from_slice(&source_before).expect("truss authoring source JSON");

    let section_first = temporary.0.join("truss-section-first");
    let section_second = temporary.0.join("truss-section-second");
    for destination in [&section_first, &section_second] {
        let output = run_truss_section_add(&source, destination, "T1", "0.005");
        assert_success(&output);
        let receipt =
            std::fs::read(destination.join("edit-receipt.json")).expect("truss-section receipt");
        assert_eq!(output.stdout, [receipt.as_slice(), b"\n"].concat());
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(section_first.join(artifact)).expect("first section artifact"),
            std::fs::read(section_second.join(artifact)).expect("second section artifact")
        );
    }
    let section_bytes =
        std::fs::read(section_first.join("model-ir.json")).expect("truss-section model");
    let section_model = parse_model_ir_v2(&section_bytes).expect("strict truss-section model");
    let section = &section_model.value()["sections"][1];
    assert_eq!(section["id"], "T1");
    assert_eq!(section["index"], 1);
    assert_eq!(section["family_id"], "truss_3d");
    assert_eq!(section["parameter_set_version"], "1");
    assert_eq!(section["parameters"], serde_json::json!({"area_m2": 0.005}));
    assert_eq!(section["source_id"], Value::Null);
    assert!(section_model.value()["extensions"]
        .get("structural-native:model-add-truss-section.v1")
        .is_some());
    assert_eq!(
        section_model.value()["roundtrip_map"],
        source_value["roundtrip_map"]
    );
    let mut section_receipt: Value = serde_json::from_slice(
        &std::fs::read(section_first.join("edit-receipt.json")).expect("truss-section receipt"),
    )
    .expect("truss-section receipt JSON");
    assert_eq!(section_receipt["operation"], "truss_section_add");
    assert_eq!(section_receipt["parameters_si"], section["parameters"]);
    assert_eq!(section_receipt["cpp_semantic_snapshot_verified"], true);
    assert_eq!(section_receipt["analysis_ready"], true);
    assert_eq!(
        section_receipt["edited_content_hash"],
        section_model.content_hash()
    );
    assert_self_hashed_edit_receipt(&mut section_receipt);

    let member_first = temporary.0.join("truss-member-first");
    let member_second = temporary.0.join("truss-member-second");
    for (section_directory, destination) in [
        (&section_first, &member_first),
        (&section_second, &member_second),
    ] {
        let output = run_truss3d_member_add(
            &section_directory.join("model-ir.json"),
            destination,
            "N3",
            ["2", "1", "0"],
            "E2",
            "N2",
            "M1",
            "T1",
        );
        assert_success(&output);
        let receipt =
            std::fs::read(destination.join("edit-receipt.json")).expect("truss-member receipt");
        assert_eq!(output.stdout, [receipt.as_slice(), b"\n"].concat());
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(member_first.join(artifact)).expect("first member artifact"),
            std::fs::read(member_second.join(artifact)).expect("second member artifact")
        );
    }
    assert_eq!(
        std::fs::read(&source).expect("unchanged source"),
        source_before
    );
    let member_bytes =
        std::fs::read(member_first.join("model-ir.json")).expect("truss-member model");
    let member_model = parse_model_ir_v2(&member_bytes).expect("strict truss-member model");
    assert_eq!(member_model.value()["nodes"][2]["id"], "N3");
    assert_eq!(member_model.value()["nodes"][2]["index"], 2);
    assert_eq!(
        member_model.value()["nodes"][2]["coordinates_m"],
        serde_json::json!([2, 1, 0])
    );
    let element = &member_model.value()["elements"][1];
    assert_eq!(element["id"], "E2");
    assert_eq!(element["index"], 1);
    assert_eq!(element["type"], "truss_3d");
    assert_eq!(element["formulation"], "linear_truss_3d");
    assert_eq!(element["node_ids"], serde_json::json!(["N2", "N3"]));
    assert_eq!(element["material_id"], "M1");
    assert_eq!(element["section_id"], "T1");
    assert!(element.get("local_axis_rotation_rad").is_none());
    assert!(element.get("releases").is_none());
    assert!(member_model.value()["extensions"]
        .get("structural-native:model-add-truss3d-member.v1")
        .is_some());
    assert_eq!(
        member_model.value()["roundtrip_map"],
        source_value["roundtrip_map"]
    );
    let mut member_receipt: Value = serde_json::from_slice(
        &std::fs::read(member_first.join("edit-receipt.json")).expect("member receipt"),
    )
    .expect("member receipt JSON");
    assert_eq!(member_receipt["operation"], "truss3d_member_add");
    assert_eq!(member_receipt["cpp_semantic_snapshot_verified"], true);
    assert_eq!(member_receipt["analysis_ready"], true);
    assert_eq!(
        member_receipt["edited_content_hash"],
        member_model.content_hash()
    );
    assert_self_hashed_edit_receipt(&mut member_receipt);

    let fixed = temporary.0.join("truss-fixed");
    assert_success(&run_fixed_constraint_add(
        &member_first.join("model-ir.json"),
        &fixed,
        "BC_N3",
        "N3",
    ));
    let baseline_request = temporary.0.join("truss-baseline-request");
    let composed_request = temporary.0.join("truss-composed-request");
    assert_success(&run_model_linear_request_create(
        &source,
        &baseline_request,
        "truss-authoring-c5",
        "LC_WEAK",
    ));
    assert_success(&run_model_linear_request_create(
        &fixed.join("model-ir.json"),
        &composed_request,
        "truss-authoring-c5",
        "LC_WEAK",
    ));
    let baseline = execute_model_ir_linear_analysis(
        &source_before,
        &std::fs::read(baseline_request.join("analysis-request.json")).expect("baseline request"),
        None,
        u32::MAX,
    )
    .expect("baseline execution");
    let composed_model = std::fs::read(fixed.join("model-ir.json")).expect("composed truss model");
    let composed_request_bytes =
        std::fs::read(composed_request.join("analysis-request.json")).expect("composed request");
    let composed =
        execute_model_ir_linear_analysis(&composed_model, &composed_request_bytes, None, u32::MAX)
            .expect("truss execution");
    assert!(baseline.is_complete());
    assert!(composed.is_complete());
    let baseline_recovery: Value = serde_json::from_str(
        baseline
            .result_recovery_ir_json()
            .expect("baseline recovery"),
    )
    .expect("baseline recovery JSON");
    let recovery: Value =
        serde_json::from_str(composed.result_recovery_ir_json().expect("truss recovery"))
            .expect("truss recovery JSON");
    assert_eq!(
        recovery["active_dof_indices"],
        serde_json::json!([6, 7, 8, 9, 10, 11])
    );
    assert_eq!(
        recovery["active_external_load"],
        serde_json::json!([0, -10000, 0, 0, 0, 0])
    );
    assert_eq!(
        recovery["recovery_stable_indices"],
        serde_json::json!([0, 1])
    );
    assert_eq!(
        recovery["recovery_element_types"],
        serde_json::json!([1, 2])
    );
    assert_eq!(recovery["recovery_offsets"], serde_json::json!([0, 12, 15]));
    let values = recovery["recovery_values"]
        .as_array()
        .expect("recovery values");
    assert_eq!(values.len(), 15);
    assert!(values[12..]
        .iter()
        .all(|value| value.as_f64().is_some_and(f64::is_finite)));
    assert!(values[14].as_f64().expect("truss axial force").abs() > f64::EPSILON);
    assert_ne!(
        baseline_recovery["global_displacement"],
        recovery["global_displacement"]
    );
    assert_eq!(recovery["fallback_count"], 0);

    let partial =
        execute_model_ir_linear_analysis(&composed_model, &composed_request_bytes, None, 1)
            .expect("partial truss execution");
    assert!(!partial.is_complete());
    let resumed = execute_model_ir_linear_analysis(
        &composed_model,
        &composed_request_bytes,
        Some(partial.checkpoint_bytes()),
        u32::MAX,
    )
    .expect("resumed truss execution");
    assert!(resumed.is_complete());
    assert_eq!(resumed.result_ir_json(), composed.result_ir_json());
    assert_eq!(
        resumed.result_recovery_ir_json(),
        composed.result_recovery_ir_json()
    );

    for (name, section_id, area, status, code) in [
        (
            "duplicate-section",
            "S1",
            "0.005",
            1,
            "workbench_model_add_truss_section_identity_exists",
        ),
        ("zero-area", "T1", "0", 2, "workbench_usage_error"),
        ("nonfinite-area", "T1", "NaN", 2, "workbench_usage_error"),
    ] {
        let destination = temporary.0.join(name);
        let rejected = run_truss_section_add(&source, &destination, section_id, area);
        assert_eq!(rejected.status.code(), Some(status));
        assert!(String::from_utf8_lossy(&rejected.stdout).contains(code));
        assert!(!destination.exists());
    }
    for (name, node, coordinates, element_id, from_node, material, section, code) in [
        (
            "duplicate-node",
            "N2",
            ["2", "1", "0"],
            "E2",
            "N1",
            "M1",
            "T1",
            "workbench_model_add_truss3d_member_node_exists",
        ),
        (
            "duplicate-coordinate",
            "N3",
            ["2", "0", "0"],
            "E2",
            "N2",
            "M1",
            "T1",
            "workbench_model_add_truss3d_member_coordinate_exists",
        ),
        (
            "duplicate-element",
            "N3",
            ["2", "1", "0"],
            "E1",
            "N2",
            "M1",
            "T1",
            "workbench_model_add_truss3d_member_element_exists",
        ),
        (
            "missing-from-node",
            "N3",
            ["2", "1", "0"],
            "E2",
            "MISSING",
            "M1",
            "T1",
            "workbench_model_add_truss3d_member_from_node_missing",
        ),
        (
            "missing-reference",
            "N3",
            ["2", "1", "0"],
            "E2",
            "N2",
            "MISSING",
            "T1",
            "workbench_model_add_truss3d_member_material_missing",
        ),
        (
            "missing-section",
            "N3",
            ["2", "1", "0"],
            "E2",
            "N2",
            "M1",
            "MISSING",
            "workbench_model_add_truss3d_member_section_missing",
        ),
        (
            "wrong-family",
            "N3",
            ["2", "1", "0"],
            "E2",
            "N2",
            "M1",
            "S1",
            "workbench_model_add_truss3d_member_section_unsupported",
        ),
    ] {
        let destination = temporary.0.join(name);
        let rejected = run_truss3d_member_add(
            &section_first.join("model-ir.json"),
            &destination,
            node,
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

    let existing_destination = run_truss3d_member_add(
        &section_first.join("model-ir.json"),
        &member_first,
        "N3",
        ["2", "1", "0"],
        "E2",
        "N2",
        "M1",
        "T1",
    );
    assert_eq!(existing_destination.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&existing_destination.stdout)
        .contains("workbench_stage_destination_exists"));

    let invalid_source = temporary.0.join("invalid-truss-source.json");
    std::fs::write(&invalid_source, b"{}").expect("write invalid truss source");
    let invalid_destination = temporary.0.join("invalid-truss-destination");
    let invalid = run_truss_section_add(&invalid_source, &invalid_destination, "T1", "0.005");
    assert_eq!(invalid.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&invalid.stdout)
        .contains("workbench_model_edit_source_validation_failed"));
    assert!(!invalid_destination.exists());

    let mut blocked = source_value;
    blocked["unsupported_features"] = serde_json::json!([{
        "feature_id": "feature.truss-authoring-visible-not-runnable",
        "kind": "unsupported_solver_feature",
        "source_entity_id": null,
        "disposition": "blocked",
        "blocking": true,
        "detail": "Truss authoring must not promote unsupported solver authority.",
        "extensions": {}
    }]);
    let blocked_source = temporary.0.join("blocked-truss-source.json");
    std::fs::write(
        &blocked_source,
        serde_json::to_vec(&blocked).expect("blocked bytes"),
    )
    .expect("write blocked source");
    let blocked_section = temporary.0.join("blocked-truss-section");
    let blocked_member = temporary.0.join("blocked-truss-member");
    assert_success(&run_truss_section_add(
        &blocked_source,
        &blocked_section,
        "T1",
        "0.005",
    ));
    assert_success(&run_truss3d_member_add(
        &blocked_section.join("model-ir.json"),
        &blocked_member,
        "N3",
        ["2", "1", "0"],
        "E2",
        "N2",
        "M1",
        "T1",
    ));
    let blocked_receipt: Value = serde_json::from_slice(
        &std::fs::read(blocked_member.join("edit-receipt.json")).expect("blocked receipt"),
    )
    .expect("blocked receipt JSON");
    assert_eq!(blocked_receipt["analysis_ready"], false);
    assert_eq!(
        blocked_receipt["blocking_feature_ids"],
        serde_json::json!(["feature.truss-authoring-visible-not-runnable"])
    );
    let blocked_request_directory = temporary.0.join("blocked-truss-request");
    let blocked_request = run_model_linear_request_create(
        &blocked_member.join("model-ir.json"),
        &blocked_request_directory,
        "blocked-truss",
        "LC_WEAK",
    );
    assert_eq!(blocked_request.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&blocked_request.stdout)
        .contains("workbench_model_linear_request_source_not_ready"));
    assert!(!blocked_request_directory.exists());
}

#[test]
#[allow(clippy::too_many_lines)]
fn truss3d_edits_are_deterministic_fail_closed_restartable_and_cpu_executable() {
    let temporary = TestDirectory::create();
    let source =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let t1 = temporary.0.join("truss-edit-t1");
    let t2 = temporary.0.join("truss-edit-t2");
    let m2 = temporary.0.join("truss-edit-m2");
    let member = temporary.0.join("truss-edit-member");
    let fixed = temporary.0.join("truss-edit-fixed");
    assert_success(&run_truss_section_add(&source, &t1, "T1", "0.005"));
    assert_success(&run_truss_section_add(
        &t1.join("model-ir.json"),
        &t2,
        "T2",
        "0.0025",
    ));
    assert_success(&run_linear_material_add(
        &t2.join("model-ir.json"),
        &m2,
        "M2",
        ["105000000000", "0.3", "7850"],
    ));
    assert_success(&run_truss3d_member_add(
        &m2.join("model-ir.json"),
        &member,
        "N3",
        ["2", "1", "0"],
        "E2",
        "N2",
        "M1",
        "T1",
    ));
    assert_success(&run_fixed_constraint_add(
        &member.join("model-ir.json"),
        &fixed,
        "BC_N3",
        "N3",
    ));
    let fixed_path = fixed.join("model-ir.json");
    let fixed_bytes = std::fs::read(&fixed_path).expect("truss edit source");
    let fixed_model = parse_model_ir_v2(&fixed_bytes).expect("strict truss edit source");

    let section_first = temporary.0.join("truss-section-edit-first");
    let section_second = temporary.0.join("truss-section-edit-second");
    for destination in [&section_first, &section_second] {
        let output = run_truss_section_edit(&fixed_path, destination, "T1", "0.01");
        assert_success(&output);
        let receipt = std::fs::read(destination.join("edit-receipt.json"))
            .expect("truss section edit receipt");
        assert_eq!(output.stdout, [receipt.as_slice(), b"\n"].concat());
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(section_first.join(artifact)).expect("first truss section edit"),
            std::fs::read(section_second.join(artifact)).expect("second truss section edit")
        );
    }
    let section_bytes =
        std::fs::read(section_first.join("model-ir.json")).expect("edited truss section model");
    let section_model = parse_model_ir_v2(&section_bytes).expect("strict edited truss section");
    assert_eq!(section_model.value()["sections"][1]["id"], "T1");
    assert_eq!(
        section_model.value()["sections"][1]["parameters"],
        serde_json::json!({"area_m2": 0.01})
    );
    assert_eq!(
        section_model.value()["roundtrip_map"],
        fixed_model.value()["roundtrip_map"]
    );
    assert!(section_model.value()["extensions"]
        .get("structural-native:model-edit-truss-section.v1")
        .is_some());
    let mut section_receipt: Value = serde_json::from_slice(
        &std::fs::read(section_first.join("edit-receipt.json"))
            .expect("truss section edit receipt"),
    )
    .expect("truss section edit receipt JSON");
    assert_eq!(section_receipt["operation"], "truss_section_parameters");
    assert_eq!(section_receipt["section_id"], "T1");
    assert_eq!(section_receipt["family_id"], "truss_3d");
    assert_eq!(
        section_receipt["previous_parameters_si"],
        serde_json::json!({"area_m2": 0.005})
    );
    assert_eq!(
        section_receipt["edited_parameters_si"],
        serde_json::json!({"area_m2": 0.01})
    );
    assert_eq!(section_receipt["cpp_semantic_snapshot_verified"], true);
    assert_eq!(section_receipt["analysis_ready"], true);
    assert_eq!(
        section_receipt["edited_content_hash"],
        section_model.content_hash()
    );
    assert_self_hashed_edit_receipt(&mut section_receipt);

    let properties_first = temporary.0.join("truss-properties-edit-first");
    let properties_second = temporary.0.join("truss-properties-edit-second");
    for destination in [&properties_first, &properties_second] {
        let output = run_truss_element_properties_edit(
            &section_first.join("model-ir.json"),
            destination,
            "E2",
            "M2",
            "T2",
        );
        assert_success(&output);
        let receipt = std::fs::read(destination.join("edit-receipt.json"))
            .expect("truss property edit receipt");
        assert_eq!(output.stdout, [receipt.as_slice(), b"\n"].concat());
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(properties_first.join(artifact)).expect("first truss property edit"),
            std::fs::read(properties_second.join(artifact)).expect("second truss property edit")
        );
    }
    assert_eq!(
        std::fs::read(&fixed_path).expect("unchanged truss source"),
        fixed_bytes
    );
    let properties_bytes =
        std::fs::read(properties_first.join("model-ir.json")).expect("edited truss property model");
    let properties_model =
        parse_model_ir_v2(&properties_bytes).expect("strict edited truss property model");
    let edited_element = &properties_model.value()["elements"][1];
    let source_element = &section_model.value()["elements"][1];
    assert_eq!(edited_element["id"], source_element["id"]);
    assert_eq!(edited_element["index"], source_element["index"]);
    assert_eq!(edited_element["type"], "truss_3d");
    assert_eq!(edited_element["formulation"], "linear_truss_3d");
    assert_eq!(edited_element["node_ids"], source_element["node_ids"]);
    assert_eq!(edited_element["offsets"], source_element["offsets"]);
    assert_eq!(edited_element["material_id"], "M2");
    assert_eq!(edited_element["section_id"], "T2");
    assert_eq!(
        properties_model.value()["roundtrip_map"],
        section_model.value()["roundtrip_map"]
    );
    assert!(properties_model.value()["extensions"]
        .get("structural-native:model-edit-truss-element-properties.v1")
        .is_some());
    let mut properties_receipt: Value = serde_json::from_slice(
        &std::fs::read(properties_first.join("edit-receipt.json"))
            .expect("truss property edit receipt"),
    )
    .expect("truss property edit receipt JSON");
    assert_eq!(properties_receipt["operation"], "truss_element_properties");
    assert_eq!(properties_receipt["element_id"], "E2");
    assert_eq!(properties_receipt["element_type"], "truss_3d");
    assert_eq!(properties_receipt["formulation"], "linear_truss_3d");
    assert_eq!(properties_receipt["previous_material_id"], "M1");
    assert_eq!(properties_receipt["edited_material_id"], "M2");
    assert_eq!(properties_receipt["previous_section_id"], "T1");
    assert_eq!(properties_receipt["edited_section_id"], "T2");
    assert_eq!(properties_receipt["cpp_semantic_snapshot_verified"], true);
    assert_eq!(properties_receipt["analysis_ready"], true);
    assert_eq!(
        properties_receipt["edited_content_hash"],
        properties_model.content_hash()
    );
    assert_self_hashed_edit_receipt(&mut properties_receipt);

    let baseline_request = temporary.0.join("truss-edit-baseline-request");
    let section_request = temporary.0.join("truss-edit-section-request");
    let properties_request = temporary.0.join("truss-edit-properties-request");
    for (model, destination) in [
        (&fixed_path, &baseline_request),
        (&section_first.join("model-ir.json"), &section_request),
        (&properties_first.join("model-ir.json"), &properties_request),
    ] {
        assert_success(&run_model_linear_request_create(
            model,
            destination,
            "truss-editing-c5",
            "LC_WEAK",
        ));
    }
    let execute = |model: &[u8], request_directory: &Path| {
        execute_model_ir_linear_analysis(
            model,
            &std::fs::read(request_directory.join("analysis-request.json"))
                .expect("truss edit request"),
            None,
            u32::MAX,
        )
        .expect("truss edit execution")
    };
    let baseline = execute(&fixed_bytes, &baseline_request);
    let section_result = execute(&section_bytes, &section_request);
    let properties_result = execute(&properties_bytes, &properties_request);
    assert!(baseline.is_complete());
    assert!(section_result.is_complete());
    assert!(properties_result.is_complete());
    let recovery = |result: &ModelIrLinearAnalysisOutcomeV1| {
        serde_json::from_str::<Value>(
            result
                .result_recovery_ir_json()
                .expect("completed truss edit recovery"),
        )
        .expect("truss edit recovery JSON")
    };
    let baseline_recovery = recovery(&baseline);
    let section_recovery = recovery(&section_result);
    let properties_recovery = recovery(&properties_result);
    for value in [&baseline_recovery, &section_recovery, &properties_recovery] {
        assert_eq!(
            value["active_external_load"],
            serde_json::json!([0, -10000, 0, 0, 0, 0])
        );
        assert_eq!(value["recovery_element_types"], serde_json::json!([1, 2]));
        assert_eq!(value["recovery_offsets"], serde_json::json!([0, 12, 15]));
        assert_eq!(value["fallback_count"], 0);
    }
    assert_ne!(
        baseline_recovery["global_displacement"],
        section_recovery["global_displacement"]
    );
    assert_ne!(
        section_recovery["global_displacement"],
        properties_recovery["global_displacement"]
    );
    let properties_request_bytes =
        std::fs::read(properties_request.join("analysis-request.json")).expect("property request");
    let partial =
        execute_model_ir_linear_analysis(&properties_bytes, &properties_request_bytes, None, 1)
            .expect("partial truss edit execution");
    assert!(!partial.is_complete());
    let resumed = execute_model_ir_linear_analysis(
        &properties_bytes,
        &properties_request_bytes,
        Some(partial.checkpoint_bytes()),
        u32::MAX,
    )
    .expect("resumed truss edit execution");
    assert!(resumed.is_complete());
    assert_eq!(resumed.result_ir_json(), properties_result.result_ir_json());
    assert_eq!(
        resumed.result_recovery_ir_json(),
        properties_result.result_recovery_ir_json()
    );

    for (name, section_id, area, status, code) in [
        (
            "truss-section-edit-missing",
            "MISSING",
            "0.01",
            1,
            "workbench_model_edit_truss_section_missing",
        ),
        (
            "truss-section-edit-wrong-family",
            "S1",
            "0.01",
            1,
            "workbench_model_edit_truss_section_family_unsupported",
        ),
        (
            "truss-section-edit-noop",
            "T1",
            "0.005",
            1,
            "workbench_model_edit_no_change",
        ),
        (
            "truss-section-edit-zero",
            "T1",
            "0",
            2,
            "workbench_usage_error",
        ),
    ] {
        let destination = temporary.0.join(name);
        let rejected = run_truss_section_edit(&fixed_path, &destination, section_id, area);
        assert_eq!(rejected.status.code(), Some(status));
        assert!(String::from_utf8_lossy(&rejected.stdout).contains(code));
        assert!(!destination.exists());
    }
    for (name, element_id, material_id, section_id, code) in [
        (
            "truss-property-edit-missing-element",
            "MISSING",
            "M2",
            "T2",
            "workbench_model_edit_truss_element_missing",
        ),
        (
            "truss-property-edit-wrong-element",
            "E1",
            "M2",
            "T2",
            "workbench_model_edit_truss_element_type_unsupported",
        ),
        (
            "truss-property-edit-missing-material",
            "E2",
            "MISSING",
            "T2",
            "workbench_model_edit_truss_element_material_missing",
        ),
        (
            "truss-property-edit-missing-section",
            "E2",
            "M2",
            "MISSING",
            "workbench_model_edit_truss_element_section_missing",
        ),
        (
            "truss-property-edit-wrong-section",
            "E2",
            "M2",
            "S1",
            "workbench_model_edit_truss_element_section_unsupported",
        ),
        (
            "truss-property-edit-noop",
            "E2",
            "M1",
            "T1",
            "workbench_model_edit_no_change",
        ),
    ] {
        let destination = temporary.0.join(name);
        let rejected = run_truss_element_properties_edit(
            &section_first.join("model-ir.json"),
            &destination,
            element_id,
            material_id,
            section_id,
        );
        assert_eq!(rejected.status.code(), Some(1));
        assert!(String::from_utf8_lossy(&rejected.stdout).contains(code));
        assert!(!destination.exists());
    }
    let existing_destination = run_truss_element_properties_edit(
        &section_first.join("model-ir.json"),
        &properties_first,
        "E2",
        "M2",
        "T2",
    );
    assert_eq!(existing_destination.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&existing_destination.stdout)
        .contains("workbench_stage_destination_exists"));

    let mut blocked = fixed_model.value().clone();
    blocked["unsupported_features"] = serde_json::json!([{
        "feature_id": "feature.truss-edit-visible-not-runnable",
        "kind": "unsupported_solver_feature",
        "source_entity_id": null,
        "disposition": "blocked",
        "blocking": true,
        "detail": "Truss editing must not promote unsupported solver authority.",
        "extensions": {}
    }]);
    let blocked_source = temporary.0.join("blocked-truss-edit-source.json");
    std::fs::write(
        &blocked_source,
        serde_json::to_vec(&blocked).expect("blocked truss edit bytes"),
    )
    .expect("write blocked truss edit source");
    let blocked_section = temporary.0.join("blocked-truss-section-edit");
    let blocked_properties = temporary.0.join("blocked-truss-properties-edit");
    assert_success(&run_truss_section_edit(
        &blocked_source,
        &blocked_section,
        "T1",
        "0.01",
    ));
    assert_success(&run_truss_element_properties_edit(
        &blocked_section.join("model-ir.json"),
        &blocked_properties,
        "E2",
        "M2",
        "T2",
    ));
    let blocked_receipt: Value = serde_json::from_slice(
        &std::fs::read(blocked_properties.join("edit-receipt.json"))
            .expect("blocked truss edit receipt"),
    )
    .expect("blocked truss edit receipt JSON");
    assert_eq!(blocked_receipt["analysis_ready"], false);
    assert_eq!(
        blocked_receipt["blocking_feature_ids"],
        serde_json::json!(["feature.truss-edit-visible-not-runnable"])
    );
    let blocked_request_directory = temporary.0.join("blocked-truss-edit-request");
    let blocked_request = run_model_linear_request_create(
        &blocked_properties.join("model-ir.json"),
        &blocked_request_directory,
        "blocked-truss-edit",
        "LC_WEAK",
    );
    assert_eq!(blocked_request.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&blocked_request.stdout)
        .contains("workbench_model_linear_request_source_not_ready"));
    assert!(!blocked_request_directory.exists());
}

#[test]
#[allow(clippy::too_many_lines)]
fn frame3d_leaf_deletion_is_deterministic_fail_closed_restartable_and_cpu_executable() {
    let temporary = TestDirectory::create();
    let source =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let source_before = std::fs::read(&source).expect("frame leaf-delete source bytes");
    let member = temporary.0.join("frame-leaf-delete-member");
    assert_success(&run_frame3d_member_add(
        &source,
        &member,
        "N3",
        ["2", "1", "0"],
        "E2",
        "N2",
        "M1",
        "S1",
    ));
    let member_path = member.join("model-ir.json");
    let member_bytes = std::fs::read(&member_path).expect("frame leaf-delete composed source");
    let member_model = parse_model_ir_v2(&member_bytes).expect("strict frame composed source");

    let first = temporary.0.join("frame-leaf-delete-first");
    let second = temporary.0.join("frame-leaf-delete-second");
    for destination in [&first, &second] {
        let output = run_frame3d_leaf_member_delete(&member_path, destination, "E2", "N3");
        assert_success(&output);
        let receipt = std::fs::read(destination.join("edit-receipt.json"))
            .expect("frame leaf-delete receipt");
        assert_eq!(output.stdout, [receipt.as_slice(), b"\n"].concat());
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(artifact)).expect("first frame leaf-delete artifact"),
            std::fs::read(second.join(artifact)).expect("second frame leaf-delete artifact")
        );
    }
    assert_eq!(
        std::fs::read(&source).expect("unchanged frame leaf-delete base source"),
        source_before
    );
    assert_eq!(
        std::fs::read(&member_path).expect("unchanged frame leaf-delete composed source"),
        member_bytes
    );

    let deleted_bytes =
        std::fs::read(first.join("model-ir.json")).expect("deleted frame leaf ModelIR");
    let deleted = parse_model_ir_v2(&deleted_bytes).expect("strict deleted frame leaf ModelIR");
    assert_eq!(deleted.value()["nodes"].as_array().expect("nodes").len(), 2);
    assert_eq!(
        deleted.value()["elements"]
            .as_array()
            .expect("elements")
            .len(),
        1
    );
    assert_eq!(deleted.value()["nodes"][1]["id"], "N2");
    assert_eq!(deleted.value()["elements"][0]["id"], "E1");
    for family in [
        "materials",
        "sections",
        "constraints",
        "load_patterns",
        "roundtrip_map",
    ] {
        assert_eq!(deleted.value()[family], member_model.value()[family]);
    }
    let extension = deleted.value()["extensions"]
        .get("structural-native:model-delete-frame3d-leaf-member.v1")
        .expect("frame leaf-delete provenance extension");
    assert_eq!(extension["operation"], "frame3d_leaf_member_delete");
    assert_eq!(extension["removed_node_id"], "N3");
    assert_eq!(extension["removed_node_index"], 2);
    assert_eq!(
        extension["removed_coordinates_m"],
        serde_json::json!([2, 1, 0])
    );
    assert_eq!(extension["removed_element_id"], "E2");
    assert_eq!(extension["removed_element_index"], 1);
    assert_eq!(
        extension["removed_node_ids"],
        serde_json::json!(["N2", "N3"])
    );
    assert_eq!(extension["removed_material_id"], "M1");
    assert_eq!(extension["removed_section_id"], "S1");
    assert_eq!(extension["removed_local_axis_rotation_rad"], 0);
    assert_eq!(
        extension["removed_releases"],
        serde_json::json!({"i": [], "j": []})
    );
    let mut receipt: Value = serde_json::from_slice(
        &std::fs::read(first.join("edit-receipt.json")).expect("frame leaf-delete receipt"),
    )
    .expect("frame leaf-delete receipt JSON");
    assert_eq!(receipt["operation"], "frame3d_leaf_member_delete");
    assert_eq!(receipt["removed_element_type"], "frame_3d");
    assert_eq!(receipt["removed_formulation"], "euler_bernoulli_3d");
    assert_eq!(receipt["cpp_semantic_snapshot_verified"], true);
    assert_eq!(receipt["analysis_ready"], true);
    assert_eq!(receipt["edited_content_hash"], deleted.content_hash());
    assert_self_hashed_edit_receipt(&mut receipt);

    let request_directory = temporary.0.join("frame-leaf-delete-request");
    assert_success(&run_model_linear_request_create(
        &first.join("model-ir.json"),
        &request_directory,
        "frame-leaf-delete-c5",
        "LC_WEAK",
    ));
    let request_bytes = std::fs::read(request_directory.join("analysis-request.json"))
        .expect("frame leaf-delete request");
    let direct = execute_model_ir_linear_analysis(&deleted_bytes, &request_bytes, None, u32::MAX)
        .expect("frame leaf-delete direct execution");
    assert!(direct.is_complete());
    let recovery: Value = serde_json::from_str(
        direct
            .result_recovery_ir_json()
            .expect("frame leaf-delete direct recovery"),
    )
    .expect("frame leaf-delete recovery JSON");
    assert_eq!(recovery["recovery_stable_indices"], serde_json::json!([0]));
    assert_eq!(recovery["recovery_element_types"], serde_json::json!([1]));
    assert_eq!(recovery["recovery_offsets"], serde_json::json!([0, 12]));
    assert_eq!(
        recovery["active_external_load"],
        serde_json::json!([0, -10000, 0, 0, 0, 0])
    );
    assert_eq!(recovery["fallback_count"], 0);
    let partial = execute_model_ir_linear_analysis(&deleted_bytes, &request_bytes, None, 1)
        .expect("frame leaf-delete partial execution");
    assert!(!partial.is_complete());
    let resumed = execute_model_ir_linear_analysis(
        &deleted_bytes,
        &request_bytes,
        Some(partial.checkpoint_bytes()),
        u32::MAX,
    )
    .expect("frame leaf-delete resumed execution");
    assert!(resumed.is_complete());
    assert_eq!(resumed.result_ir_json(), direct.result_ir_json());
    assert_eq!(
        resumed.result_recovery_ir_json(),
        direct.result_recovery_ir_json()
    );

    let fixed = temporary.0.join("frame-leaf-delete-fixed");
    assert_success(&run_fixed_constraint_add(
        &member_path,
        &fixed,
        "BC_N3",
        "N3",
    ));
    let constrained_destination = temporary.0.join("frame-leaf-delete-constrained-rejected");
    let constrained = run_frame3d_leaf_member_delete(
        &fixed.join("model-ir.json"),
        &constrained_destination,
        "E2",
        "N3",
    );
    assert_eq!(constrained.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&constrained.stdout)
        .contains("workbench_model_delete_frame3d_leaf_node_referenced_by_constraint"));
    assert!(!constrained_destination.exists());

    let mut source_owned = member_model.value().clone();
    source_owned["elements"][1]["source_id"] = serde_json::json!("native:test:E2");
    let source_owned_path = temporary.0.join("frame-leaf-delete-source-owned.json");
    std::fs::write(
        &source_owned_path,
        canonicalize_model_ir_v2(&source_owned)
            .expect("canonical source-owned frame leaf")
            .as_bytes(),
    )
    .expect("write source-owned frame leaf");
    let source_owned_destination = temporary.0.join("frame-leaf-delete-source-owned-rejected");
    let source_owned_rejection =
        run_frame3d_leaf_member_delete(&source_owned_path, &source_owned_destination, "E2", "N3");
    assert_eq!(source_owned_rejection.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&source_owned_rejection.stdout)
        .contains("workbench_model_delete_frame3d_leaf_source_owned"));
    assert!(!source_owned_destination.exists());

    let existing = run_frame3d_leaf_member_delete(&member_path, &first, "E2", "N3");
    assert_eq!(existing.status.code(), Some(1));
    assert!(
        String::from_utf8_lossy(&existing.stdout).contains("workbench_stage_destination_exists")
    );

    let mut blocked = member_model.value().clone();
    blocked["unsupported_features"] = serde_json::json!([{
        "feature_id": "feature.frame-leaf-delete-visible-not-runnable",
        "kind": "unsupported_solver_feature",
        "source_entity_id": null,
        "disposition": "blocked",
        "blocking": true,
        "detail": "Frame leaf deletion must preserve unsupported solver blockers.",
        "extensions": {}
    }]);
    let blocked_source = temporary.0.join("blocked-frame-leaf-delete-source.json");
    std::fs::write(
        &blocked_source,
        canonicalize_model_ir_v2(&blocked)
            .expect("canonical blocked frame leaf")
            .as_bytes(),
    )
    .expect("write blocked frame leaf source");
    let blocked_destination = temporary.0.join("blocked-frame-leaf-delete-output");
    assert_success(&run_frame3d_leaf_member_delete(
        &blocked_source,
        &blocked_destination,
        "E2",
        "N3",
    ));
    let blocked_receipt: Value = serde_json::from_slice(
        &std::fs::read(blocked_destination.join("edit-receipt.json"))
            .expect("blocked frame leaf receipt"),
    )
    .expect("blocked frame leaf receipt JSON");
    assert_eq!(blocked_receipt["analysis_ready"], false);
    assert_eq!(
        blocked_receipt["blocking_feature_ids"],
        serde_json::json!(["feature.frame-leaf-delete-visible-not-runnable"])
    );
}

#[test]
#[allow(clippy::too_many_lines)]
fn truss3d_leaf_deletion_is_deterministic_fail_closed_restartable_and_cpu_executable() {
    let temporary = TestDirectory::create();
    let source =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let source_before = std::fs::read(&source).expect("leaf-delete source bytes");
    let section = temporary.0.join("leaf-delete-section");
    let member = temporary.0.join("leaf-delete-member");
    assert_success(&run_truss_section_add(&source, &section, "T1", "0.005"));
    assert_success(&run_truss3d_member_add(
        &section.join("model-ir.json"),
        &member,
        "N3",
        ["2", "1", "0"],
        "E2",
        "N2",
        "M1",
        "T1",
    ));
    let member_path = member.join("model-ir.json");
    let member_bytes = std::fs::read(&member_path).expect("leaf-delete composed source");
    let member_model = parse_model_ir_v2(&member_bytes).expect("strict composed source");

    let first = temporary.0.join("leaf-delete-first");
    let second = temporary.0.join("leaf-delete-second");
    for destination in [&first, &second] {
        let output = run_truss3d_leaf_member_delete(&member_path, destination, "E2", "N3");
        assert_success(&output);
        let receipt =
            std::fs::read(destination.join("edit-receipt.json")).expect("leaf-delete receipt");
        assert_eq!(output.stdout, [receipt.as_slice(), b"\n"].concat());
    }
    for artifact in ["model-ir.json", "edit-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(artifact)).expect("first leaf-delete artifact"),
            std::fs::read(second.join(artifact)).expect("second leaf-delete artifact")
        );
    }
    assert_eq!(
        std::fs::read(&source).expect("unchanged leaf-delete base source"),
        source_before
    );
    assert_eq!(
        std::fs::read(&member_path).expect("unchanged leaf-delete composed source"),
        member_bytes
    );

    let deleted_bytes = std::fs::read(first.join("model-ir.json")).expect("deleted leaf ModelIR");
    let deleted = parse_model_ir_v2(&deleted_bytes).expect("strict deleted leaf ModelIR");
    assert_eq!(deleted.value()["nodes"].as_array().expect("nodes").len(), 2);
    assert_eq!(
        deleted.value()["elements"]
            .as_array()
            .expect("elements")
            .len(),
        1
    );
    assert_eq!(deleted.value()["nodes"][1]["id"], "N2");
    assert_eq!(deleted.value()["elements"][0]["id"], "E1");
    assert_eq!(
        deleted.value()["materials"],
        member_model.value()["materials"]
    );
    assert_eq!(
        deleted.value()["sections"],
        member_model.value()["sections"]
    );
    assert_eq!(
        deleted.value()["constraints"],
        member_model.value()["constraints"]
    );
    assert_eq!(
        deleted.value()["load_patterns"],
        member_model.value()["load_patterns"]
    );
    assert_eq!(
        deleted.value()["roundtrip_map"],
        member_model.value()["roundtrip_map"]
    );
    let extension = deleted.value()["extensions"]
        .get("structural-native:model-delete-truss3d-leaf-member.v1")
        .expect("leaf-delete provenance extension");
    assert_eq!(extension["operation"], "truss3d_leaf_member_delete");
    assert_eq!(extension["removed_node_id"], "N3");
    assert_eq!(extension["removed_node_index"], 2);
    assert_eq!(
        extension["removed_coordinates_m"],
        serde_json::json!([2, 1, 0])
    );
    assert_eq!(extension["removed_element_id"], "E2");
    assert_eq!(extension["removed_element_index"], 1);
    assert_eq!(
        extension["removed_node_ids"],
        serde_json::json!(["N2", "N3"])
    );
    assert_eq!(extension["removed_material_id"], "M1");
    assert_eq!(extension["removed_section_id"], "T1");
    let mut receipt: Value = serde_json::from_slice(
        &std::fs::read(first.join("edit-receipt.json")).expect("leaf-delete receipt"),
    )
    .expect("leaf-delete receipt JSON");
    assert_eq!(receipt["operation"], "truss3d_leaf_member_delete");
    assert_eq!(receipt["removed_node_id"], "N3");
    assert_eq!(receipt["removed_element_id"], "E2");
    assert_eq!(receipt["cpp_semantic_snapshot_verified"], true);
    assert_eq!(receipt["analysis_ready"], true);
    assert_eq!(receipt["edited_content_hash"], deleted.content_hash());
    assert_self_hashed_edit_receipt(&mut receipt);

    let request_directory = temporary.0.join("leaf-delete-request");
    assert_success(&run_model_linear_request_create(
        &first.join("model-ir.json"),
        &request_directory,
        "truss-leaf-delete-c5",
        "LC_WEAK",
    ));
    let request_bytes = std::fs::read(request_directory.join("analysis-request.json"))
        .expect("leaf-delete request");
    let direct = execute_model_ir_linear_analysis(&deleted_bytes, &request_bytes, None, u32::MAX)
        .expect("leaf-delete direct execution");
    assert!(direct.is_complete());
    let recovery: Value = serde_json::from_str(
        direct
            .result_recovery_ir_json()
            .expect("leaf-delete direct recovery"),
    )
    .expect("leaf-delete recovery JSON");
    assert_eq!(recovery["recovery_stable_indices"], serde_json::json!([0]));
    assert_eq!(recovery["recovery_element_types"], serde_json::json!([1]));
    assert_eq!(recovery["recovery_offsets"], serde_json::json!([0, 12]));
    assert_eq!(
        recovery["active_external_load"],
        serde_json::json!([0, -10000, 0, 0, 0, 0])
    );
    assert_eq!(recovery["fallback_count"], 0);
    let partial = execute_model_ir_linear_analysis(&deleted_bytes, &request_bytes, None, 1)
        .expect("leaf-delete partial execution");
    assert!(!partial.is_complete());
    let resumed = execute_model_ir_linear_analysis(
        &deleted_bytes,
        &request_bytes,
        Some(partial.checkpoint_bytes()),
        u32::MAX,
    )
    .expect("leaf-delete resumed execution");
    assert!(resumed.is_complete());
    assert_eq!(resumed.result_ir_json(), direct.result_ir_json());
    assert_eq!(
        resumed.result_recovery_ir_json(),
        direct.result_recovery_ir_json()
    );

    for (name, element_id, node_id, code) in [
        (
            "leaf-delete-missing-node",
            "E2",
            "MISSING",
            "workbench_model_delete_truss3d_leaf_node_missing",
        ),
        (
            "leaf-delete-nonterminal-source-row",
            "E1",
            "N2",
            "workbench_model_delete_truss3d_leaf_not_terminal",
        ),
        (
            "leaf-delete-endpoint-mismatch",
            "E2",
            "N2",
            "workbench_model_delete_truss3d_leaf_not_terminal",
        ),
    ] {
        let destination = temporary.0.join(name);
        let rejected =
            run_truss3d_leaf_member_delete(&member_path, &destination, element_id, node_id);
        assert_eq!(rejected.status.code(), Some(1));
        assert!(String::from_utf8_lossy(&rejected.stdout).contains(code));
        assert!(!destination.exists());
    }

    let fixed = temporary.0.join("leaf-delete-fixed");
    assert_success(&run_fixed_constraint_add(
        &member_path,
        &fixed,
        "BC_N3",
        "N3",
    ));
    let constrained_destination = temporary.0.join("leaf-delete-constrained-rejected");
    let constrained = run_truss3d_leaf_member_delete(
        &fixed.join("model-ir.json"),
        &constrained_destination,
        "E2",
        "N3",
    );
    assert_eq!(constrained.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&constrained.stdout)
        .contains("workbench_model_delete_truss3d_leaf_node_referenced_by_constraint"));
    assert!(!constrained_destination.exists());

    let loaded = temporary.0.join("leaf-delete-loaded");
    assert_success(&run_nodal_load_add(
        &member_path,
        &loaded,
        "LC_WEAK",
        "L_N3",
        "N3",
        ["1", "0", "0", "0", "0", "0"],
    ));
    let loaded_destination = temporary.0.join("leaf-delete-loaded-rejected");
    let loaded_rejection = run_truss3d_leaf_member_delete(
        &loaded.join("model-ir.json"),
        &loaded_destination,
        "E2",
        "N3",
    );
    assert_eq!(loaded_rejection.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&loaded_rejection.stdout)
        .contains("workbench_model_delete_truss3d_leaf_node_referenced_by_load"));
    assert!(!loaded_destination.exists());

    let mut source_owned = member_model.value().clone();
    source_owned["nodes"][2]["source_id"] = serde_json::json!("native:test:N3");
    let source_owned_path = temporary.0.join("leaf-delete-source-owned.json");
    std::fs::write(
        &source_owned_path,
        canonicalize_model_ir_v2(&source_owned)
            .expect("canonical source-owned leaf")
            .as_bytes(),
    )
    .expect("write source-owned leaf");
    let source_owned_destination = temporary.0.join("leaf-delete-source-owned-rejected");
    let source_owned_rejection =
        run_truss3d_leaf_member_delete(&source_owned_path, &source_owned_destination, "E2", "N3");
    assert_eq!(source_owned_rejection.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&source_owned_rejection.stdout)
        .contains("workbench_model_delete_truss3d_leaf_source_owned"));
    assert!(!source_owned_destination.exists());

    let existing = run_truss3d_leaf_member_delete(&member_path, &first, "E2", "N3");
    assert_eq!(existing.status.code(), Some(1));
    assert!(
        String::from_utf8_lossy(&existing.stdout).contains("workbench_stage_destination_exists")
    );

    let mut blocked = member_model.value().clone();
    blocked["unsupported_features"] = serde_json::json!([{
        "feature_id": "feature.truss-leaf-delete-visible-not-runnable",
        "kind": "unsupported_solver_feature",
        "source_entity_id": null,
        "disposition": "blocked",
        "blocking": true,
        "detail": "Leaf deletion must preserve unsupported solver blockers.",
        "extensions": {}
    }]);
    let blocked_source = temporary.0.join("blocked-leaf-delete-source.json");
    std::fs::write(
        &blocked_source,
        canonicalize_model_ir_v2(&blocked)
            .expect("canonical blocked leaf")
            .as_bytes(),
    )
    .expect("write blocked leaf source");
    let blocked_destination = temporary.0.join("blocked-leaf-delete-output");
    assert_success(&run_truss3d_leaf_member_delete(
        &blocked_source,
        &blocked_destination,
        "E2",
        "N3",
    ));
    let blocked_receipt: Value = serde_json::from_slice(
        &std::fs::read(blocked_destination.join("edit-receipt.json"))
            .expect("blocked leaf receipt"),
    )
    .expect("blocked leaf receipt JSON");
    assert_eq!(blocked_receipt["analysis_ready"], false);
    assert_eq!(
        blocked_receipt["blocking_feature_ids"],
        serde_json::json!(["feature.truss-leaf-delete-visible-not-runnable"])
    );
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
