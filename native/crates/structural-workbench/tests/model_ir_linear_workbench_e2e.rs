use std::ffi::OsStr;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::time::{SystemTime, UNIX_EPOCH};

use serde_json::{json, Value};
use structural_cli::{execute_model_ir_linear_analysis, execute_native_mgt_import};
use structural_contracts::model_ir::{canonicalize_model_ir_v2, parse_model_ir_v2};
use structural_contracts::product_ir::sha256_identity;
use structural_report::{validate_deterministic_localized_pdf_v2, validate_deterministic_pdf_v1};

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

fn temporary_root(name: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("clock")
        .as_nanos();
    std::env::temp_dir().join(format!(
        "structural-linear-workbench-{name}-{}-{nanos}",
        std::process::id()
    ))
}

fn text(value: &str) -> &OsStr {
    OsStr::new(value)
}

fn run_workbench(arguments: &[&OsStr]) -> Output {
    let mut command = Command::new(env!("CARGO_BIN_EXE_structural-workbench"));
    command.env_clear();
    command.env("PATH", "/nonexistent");
    for argument in arguments {
        command.arg(argument);
    }
    command.output().expect("run Workbench")
}

fn assert_success(output: &Output) {
    assert!(
        output.status.success(),
        "stdout={} stderr={}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
}

fn verify_self_hash(bytes: &[u8], field: &str) -> Value {
    let mut value: Value = serde_json::from_slice(bytes).expect("hashed JSON");
    let expected = value
        .as_object_mut()
        .expect("hashed object")
        .remove(field)
        .and_then(|value| value.as_str().map(ToOwned::to_owned))
        .expect("self hash");
    let unsigned = canonicalize_model_ir_v2(&value).expect("canonical unsigned JSON");
    assert_eq!(expected, sha256_identity(unsigned.as_bytes()));
    value
        .as_object_mut()
        .expect("hashed object")
        .insert(field.to_owned(), json!(expected));
    value
}

fn write_self_hashed_json(path: &Path, mut value: Value, field: &str) {
    value
        .as_object_mut()
        .expect("hashed object")
        .remove(field)
        .expect("existing self hash");
    let unsigned = canonicalize_model_ir_v2(&value).expect("canonical unsigned JSON");
    value.as_object_mut().expect("hashed object").insert(
        field.to_owned(),
        json!(sha256_identity(unsigned.as_bytes())),
    );
    let canonical = canonicalize_model_ir_v2(&value).expect("canonical hashed JSON");
    fs::write(path, canonical).expect("rewrite self-hashed JSON");
}

fn strip_reaction_from_frozen_receipt(path: &Path, claim_boundary: &str) {
    let mut receipt = verify_self_hash(&fs::read(path).expect("receipt"), "receipt_hash");
    receipt["artifacts"]
        .as_array_mut()
        .expect("artifact inventory")
        .retain(|artifact| artifact["file"] != "reaction-result-ir.json");
    receipt
        .as_object_mut()
        .expect("receipt object")
        .remove("source_reaction_hash");
    receipt["claim_boundary"] = json!(claim_boundary);
    write_self_hashed_json(path, receipt, "receipt_hash");
}

struct Inputs {
    model: PathBuf,
    request: PathBuf,
    external: PathBuf,
    source: PathBuf,
}

struct MgtInputs {
    source_mgt: PathBuf,
    model_id: String,
    request: PathBuf,
    external: PathBuf,
    source: PathBuf,
}

fn write_release_oracle(root: &Path, recovery: &Value) -> (PathBuf, PathBuf) {
    let displacement = recovery["global_displacement"][7]
        .as_f64()
        .expect("released model node 2 UY displacement");
    let source_bytes = b"language-neutral Frame3D end-release Workbench oracle v1\n";
    let source = root.join("release-linear-oracle.txt");
    fs::write(&source, source_bytes).expect("release source artifact");
    let external = root.join("release-linear-external.json");
    fs::write(
        &external,
        serde_json::to_vec(&json!({
            "schema_version": "structural-model-ir-linear-external-result.v1",
            "comparison_id": "workbench-model-linear-end-release-c5",
            "source": {
                "solver_family": "reference_oracle",
                "solver_version": "language-neutral-end-release-v1",
                "run_id": "workbench-model-linear-end-release-run",
                "evidence_kind": "language_neutral_golden",
                "source_artifact_hash": sha256_identity(source_bytes),
                "executable_hash": null
            },
            "binding": {
                "analysis_kind": "model_ir_linear_static",
                "case_id": recovery["case_id"],
                "model_identity": recovery["model_identity"],
                "analysis_request_hash": recovery["analysis_request_hash"],
                "load_pattern_id": recovery["load_pattern_id"],
                "coordinate_frame": "model_global"
            },
            "observations": [{
                "observation_id": "released-cantilever-tip-uy",
                "external_location_id": "node/N2/UY",
                "global_dof_index": 7,
                "dof": "UY",
                "native_result_path": "/global_displacement/7",
                "unit": "m",
                "value": displacement,
                "tolerance": {"absolute": 0.0, "relative": 0.0}
            }]
        }))
        .expect("release external result JSON"),
    )
    .expect("release external result");
    (source, external)
}

fn prepare_inputs(root: &Path) -> Inputs {
    let repository = repository_root();
    let model = repository.join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let request =
        repository.join("native/tests/fixtures/model_ir_linear/frame_cantilever_weak_request.json");
    let model_bytes = fs::read(&model).expect("ModelIR fixture");
    let request_bytes = fs::read(&request).expect("linear request fixture");
    let direct = execute_model_ir_linear_analysis(&model_bytes, &request_bytes, None, u32::MAX)
        .expect("direct terminal result");
    assert!(direct.is_complete(), "{}", direct.run_receipt_json());
    let recovery: Value = serde_json::from_str(
        direct
            .result_recovery_ir_json()
            .expect("direct recovery IR"),
    )
    .expect("recovery JSON");
    let displacement = recovery["global_displacement"][6]
        .as_f64()
        .expect("node 1 UX displacement");
    let source_bytes = b"language-neutral ModelIR linear Workbench oracle v1\n";
    let source = root.join("linear-oracle.txt");
    fs::write(&source, source_bytes).expect("source artifact");
    let external = root.join("linear-external.json");
    fs::write(
        &external,
        serde_json::to_vec(&json!({
            "schema_version": "structural-model-ir-linear-external-result.v1",
            "comparison_id": "workbench-model-linear-c5",
            "source": {
                "solver_family": "reference_oracle",
                "solver_version": "language-neutral-v1",
                "run_id": "workbench-model-linear-run",
                "evidence_kind": "language_neutral_golden",
                "source_artifact_hash": sha256_identity(source_bytes),
                "executable_hash": null
            },
            "binding": {
                "analysis_kind": "model_ir_linear_static",
                "case_id": recovery["case_id"],
                "model_identity": recovery["model_identity"],
                "analysis_request_hash": recovery["analysis_request_hash"],
                "load_pattern_id": recovery["load_pattern_id"],
                "coordinate_frame": "model_global"
            },
            "observations": [{
                "observation_id": "cantilever-tip-ux",
                "external_location_id": "node/N2/UX",
                "global_dof_index": 6,
                "dof": "UX",
                "native_result_path": "/global_displacement/6",
                "unit": "m",
                "value": displacement,
                "tolerance": {"absolute": 0.0, "relative": 0.0}
            }]
        }))
        .expect("external result JSON"),
    )
    .expect("external result");
    Inputs {
        model,
        request,
        external,
        source,
    }
}

fn prepare_offset_inputs(root: &Path) -> Inputs {
    let repository = repository_root();
    let baseline = repository.join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let baseline_request =
        repository.join("native/tests/fixtures/model_ir_linear/frame_cantilever_weak_request.json");
    let mut model_value: Value =
        serde_json::from_slice(&fs::read(baseline).expect("baseline ModelIR fixture"))
            .expect("baseline ModelIR JSON");
    model_value["model_id"] = json!("engine-v2-frame-cantilever-rigid-offset");
    model_value["elements"][0]["offsets"]["i_global_m"] = json!([0.1, 0.0, 0.0]);
    model_value["elements"][0]["offsets"]["j_global_m"] = json!([-0.1, 0.0, 0.0]);
    let model = root.join("frame-rigid-offset-model-ir.json");
    fs::write(
        &model,
        canonicalize_model_ir_v2(&model_value).expect("canonical offset ModelIR"),
    )
    .expect("offset ModelIR fixture");

    let model_bytes = fs::read(&model).expect("offset ModelIR bytes");
    let parsed_model = parse_model_ir_v2(&model_bytes).expect("strict offset ModelIR");
    let mut request_value: Value = serde_json::from_slice(
        &fs::read(&baseline_request).expect("baseline linear request fixture"),
    )
    .expect("baseline linear request JSON");
    request_value["model_identity"] = json!({
        "content_hash": parsed_model.content_hash(),
        "semantic_hash": parsed_model.semantic_hash(),
        "provenance_hash": parsed_model.provenance_hash()
    });
    let request = root.join("frame-rigid-offset-request.json");
    fs::write(
        &request,
        canonicalize_model_ir_v2(&request_value).expect("canonical offset request"),
    )
    .expect("offset request fixture");
    let request_bytes = fs::read(&request).expect("linear request fixture");
    let direct = execute_model_ir_linear_analysis(&model_bytes, &request_bytes, None, u32::MAX)
        .expect("direct offset terminal result");
    assert!(direct.is_complete(), "{}", direct.run_receipt_json());
    let recovery: Value = serde_json::from_str(
        direct
            .result_recovery_ir_json()
            .expect("direct offset recovery IR"),
    )
    .expect("offset recovery JSON");
    let displacement = recovery["global_displacement"][7]
        .as_f64()
        .expect("offset node 2 UY displacement");
    let source_bytes = b"language-neutral Frame3D rigid-offset Workbench oracle v1\n";
    let source = root.join("offset-linear-oracle.txt");
    fs::write(&source, source_bytes).expect("offset source artifact");
    let external = root.join("offset-linear-external.json");
    fs::write(
        &external,
        serde_json::to_vec(&json!({
            "schema_version": "structural-model-ir-linear-external-result.v1",
            "comparison_id": "workbench-model-linear-rigid-offset-c5",
            "source": {
                "solver_family": "reference_oracle",
                "solver_version": "language-neutral-rigid-offset-v1",
                "run_id": "workbench-model-linear-rigid-offset-run",
                "evidence_kind": "language_neutral_golden",
                "source_artifact_hash": sha256_identity(source_bytes),
                "executable_hash": null
            },
            "binding": {
                "analysis_kind": "model_ir_linear_static",
                "case_id": recovery["case_id"],
                "model_identity": recovery["model_identity"],
                "analysis_request_hash": recovery["analysis_request_hash"],
                "load_pattern_id": recovery["load_pattern_id"],
                "coordinate_frame": "model_global"
            },
            "observations": [{
                "observation_id": "offset-cantilever-tip-uy",
                "external_location_id": "node/N2/UY",
                "global_dof_index": 7,
                "dof": "UY",
                "native_result_path": "/global_displacement/7",
                "unit": "m",
                "value": displacement,
                "tolerance": {"absolute": 0.0, "relative": 0.0}
            }]
        }))
        .expect("offset external result JSON"),
    )
    .expect("offset external result");
    Inputs {
        model,
        request,
        external,
        source,
    }
}

fn prepare_release_inputs(root: &Path) -> Inputs {
    let repository = repository_root();
    let baseline = repository.join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let baseline_request =
        repository.join("native/tests/fixtures/model_ir_linear/frame_cantilever_weak_request.json");
    let mut model_value: Value =
        serde_json::from_slice(&fs::read(baseline).expect("baseline ModelIR fixture"))
            .expect("baseline ModelIR JSON");
    model_value["model_id"] = json!("engine-v2-frame-cantilever-end-release");
    model_value["elements"][0]["offsets"]["i_global_m"] = json!([0.1, 0.0, 0.0]);
    model_value["elements"][0]["offsets"]["j_global_m"] = json!([-0.1, 0.0, 0.0]);
    model_value["elements"][0]["releases"]["i"] = json!(["RY"]);
    model_value["constraints"]
        .as_array_mut()
        .expect("constraint array")
        .push(json!({
            "id": "BC2",
            "index": 1,
            "type": "fixed_dofs",
            "node_id": "N2",
            "dofs": ["UZ"],
            "prescribed_values_si": {"UZ": 0.0},
            "source_id": "generated:BC2",
            "extensions": {}
        }));
    let model = root.join("frame-end-release-model-ir.json");
    fs::write(
        &model,
        canonicalize_model_ir_v2(&model_value).expect("canonical release ModelIR"),
    )
    .expect("release ModelIR fixture");

    let model_bytes = fs::read(&model).expect("release ModelIR bytes");
    let parsed_model = parse_model_ir_v2(&model_bytes).expect("strict release ModelIR");
    let mut request_value: Value = serde_json::from_slice(
        &fs::read(&baseline_request).expect("baseline linear request fixture"),
    )
    .expect("baseline linear request JSON");
    request_value["model_identity"] = json!({
        "content_hash": parsed_model.content_hash(),
        "semantic_hash": parsed_model.semantic_hash(),
        "provenance_hash": parsed_model.provenance_hash()
    });
    let request = root.join("frame-end-release-request.json");
    fs::write(
        &request,
        canonicalize_model_ir_v2(&request_value).expect("canonical release request"),
    )
    .expect("release request fixture");
    let request_bytes = fs::read(&request).expect("release request fixture");
    let direct = execute_model_ir_linear_analysis(&model_bytes, &request_bytes, None, u32::MAX)
        .expect("direct release terminal result");
    assert!(direct.is_complete(), "{}", direct.run_receipt_json());
    let recovery: Value = serde_json::from_str(
        direct
            .result_recovery_ir_json()
            .expect("direct release recovery IR"),
    )
    .expect("release recovery JSON");
    assert_eq!(
        recovery["recovery_values"][4]
            .as_f64()
            .expect("released i-MY recovery")
            .to_bits(),
        0.0_f64.to_bits()
    );
    let (source, external) = write_release_oracle(root, &recovery);
    Inputs {
        model,
        request,
        external,
        source,
    }
}

fn prepare_self_weight_inputs(root: &Path) -> Inputs {
    let repository = repository_root();
    let baseline = repository.join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let baseline_request =
        repository.join("native/tests/fixtures/model_ir_linear/frame_cantilever_weak_request.json");
    let mut model_value: Value =
        serde_json::from_slice(&fs::read(baseline).expect("baseline ModelIR fixture"))
            .expect("baseline ModelIR JSON");
    model_value["model_id"] = json!("engine-v2-frame-cantilever-self-weight-workbench");
    model_value["load_patterns"][1]["self_weight"] = json!([0.0, 0.0, -1.0]);
    model_value["load_patterns"][1]["nodal_loads"] = json!([]);
    let model = root.join("frame-self-weight-model-ir.json");
    fs::write(
        &model,
        canonicalize_model_ir_v2(&model_value).expect("canonical self-weight ModelIR"),
    )
    .expect("self-weight ModelIR fixture");

    let model_bytes = fs::read(&model).expect("self-weight ModelIR bytes");
    let parsed_model = parse_model_ir_v2(&model_bytes).expect("strict self-weight ModelIR");
    let mut request_value: Value = serde_json::from_slice(
        &fs::read(&baseline_request).expect("baseline linear request fixture"),
    )
    .expect("baseline linear request JSON");
    request_value["model_identity"] = json!({
        "content_hash": parsed_model.content_hash(),
        "semantic_hash": parsed_model.semantic_hash(),
        "provenance_hash": parsed_model.provenance_hash()
    });
    let request = root.join("frame-self-weight-request.json");
    fs::write(
        &request,
        canonicalize_model_ir_v2(&request_value).expect("canonical self-weight request"),
    )
    .expect("self-weight request fixture");
    let request_bytes = fs::read(&request).expect("self-weight request fixture");
    let direct = execute_model_ir_linear_analysis(&model_bytes, &request_bytes, None, u32::MAX)
        .expect("direct self-weight terminal result");
    assert!(direct.is_complete(), "{}", direct.run_receipt_json());
    let recovery: Value = serde_json::from_str(
        direct
            .result_recovery_ir_json()
            .expect("direct self-weight recovery IR"),
    )
    .expect("self-weight recovery JSON");
    let expected_tip_uz = -0.000_192_455_506_25_f64;
    assert!(
        (recovery["global_displacement"][8]
            .as_f64()
            .expect("self-weight node 2 UZ displacement")
            - expected_tip_uz)
            .abs()
            <= 1.0e-15
    );
    let source_bytes =
        b"Euler-Bernoulli cantilever self-weight oracle: wL^4/(8EI), g=9.80665 m/s^2\n";
    let source = root.join("self-weight-linear-oracle.txt");
    fs::write(&source, source_bytes).expect("self-weight source artifact");
    let external = root.join("self-weight-linear-external.json");
    fs::write(
        &external,
        serde_json::to_vec(&json!({
            "schema_version": "structural-model-ir-linear-external-result.v1",
            "comparison_id": "workbench-model-linear-self-weight-c5",
            "source": {
                "solver_family": "reference_oracle",
                "solver_version": "euler-bernoulli-self-weight-v1",
                "run_id": "workbench-model-linear-self-weight-run",
                "evidence_kind": "language_neutral_golden",
                "source_artifact_hash": sha256_identity(source_bytes),
                "executable_hash": null
            },
            "binding": {
                "analysis_kind": "model_ir_linear_static",
                "case_id": recovery["case_id"],
                "model_identity": recovery["model_identity"],
                "analysis_request_hash": recovery["analysis_request_hash"],
                "load_pattern_id": recovery["load_pattern_id"],
                "coordinate_frame": "model_global"
            },
            "observations": [{
                "observation_id": "self-weight-cantilever-tip-uz",
                "external_location_id": "node/N2/UZ",
                "global_dof_index": 8,
                "dof": "UZ",
                "native_result_path": "/global_displacement/8",
                "unit": "m",
                "value": expected_tip_uz,
                "tolerance": {"absolute": 1.0e-15, "relative": 1.0e-12}
            }]
        }))
        .expect("self-weight external result JSON"),
    )
    .expect("self-weight external result");
    Inputs {
        model,
        request,
        external,
        source,
    }
}

#[allow(clippy::too_many_lines)]
fn prepare_member_distributed_load_inputs(root: &Path) -> Inputs {
    let repository = repository_root();
    let baseline = repository.join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let baseline_request =
        repository.join("native/tests/fixtures/model_ir_linear/frame_cantilever_weak_request.json");
    let mut model_value: Value =
        serde_json::from_slice(&fs::read(baseline).expect("baseline ModelIR fixture"))
            .expect("baseline ModelIR JSON");
    model_value["model_id"] = json!("engine-v2-frame-cantilever-member-load-workbench");
    model_value["load_patterns"][1]["nodal_loads"] = json!([]);
    model_value["load_patterns"][1]["member_distributed_loads"] = json!([{
        "id": "ML_WEAK_E1",
        "index": 0,
        "element_id": "E1",
        "basis": "initial_member_local",
        "distribution": "uniform_full_span",
        "components_si": {
            "qx_n_per_m": 0.0,
            "qy_n_per_m": -1000.0,
            "qz_n_per_m": 0.0
        },
        "source_id": "generated:ML_WEAK_E1",
        "extensions": {}
    }]);
    let model = root.join("frame-member-load-model-ir.json");
    fs::write(
        &model,
        canonicalize_model_ir_v2(&model_value).expect("canonical member-load ModelIR"),
    )
    .expect("member-load ModelIR fixture");

    let model_bytes = fs::read(&model).expect("member-load ModelIR bytes");
    let parsed_model = parse_model_ir_v2(&model_bytes).expect("strict member-load ModelIR");
    let mut request_value: Value = serde_json::from_slice(
        &fs::read(&baseline_request).expect("baseline linear request fixture"),
    )
    .expect("baseline linear request JSON");
    request_value["model_identity"] = json!({
        "content_hash": parsed_model.content_hash(),
        "semantic_hash": parsed_model.semantic_hash(),
        "provenance_hash": parsed_model.provenance_hash()
    });
    let request = root.join("frame-member-load-request.json");
    fs::write(
        &request,
        canonicalize_model_ir_v2(&request_value).expect("canonical member-load request"),
    )
    .expect("member-load request fixture");
    let request_bytes = fs::read(&request).expect("member-load request fixture");
    let direct = execute_model_ir_linear_analysis(&model_bytes, &request_bytes, None, u32::MAX)
        .expect("direct member-load terminal result");
    assert!(direct.is_complete(), "{}", direct.run_receipt_json());
    let recovery: Value = serde_json::from_str(
        direct
            .result_recovery_ir_json()
            .expect("direct member-load recovery IR"),
    )
    .expect("member-load recovery JSON");
    let expected_tip_uy = -0.000_2_f64;
    assert!(
        (recovery["global_displacement"][7]
            .as_f64()
            .expect("member-load node 2 UY displacement")
            - expected_tip_uy)
            .abs()
            <= 1.0e-15
    );
    let source_bytes = b"Euler-Bernoulli cantilever uniform member load oracle: qL^4/(8EI)\n";
    let source = root.join("member-load-linear-oracle.txt");
    fs::write(&source, source_bytes).expect("member-load source artifact");
    let external = root.join("member-load-linear-external.json");
    fs::write(
        &external,
        serde_json::to_vec(&json!({
            "schema_version": "structural-model-ir-linear-external-result.v1",
            "comparison_id": "workbench-model-linear-member-load-c5",
            "source": {
                "solver_family": "reference_oracle",
                "solver_version": "euler-bernoulli-uniform-load-v1",
                "run_id": "workbench-model-linear-member-load-run",
                "evidence_kind": "language_neutral_golden",
                "source_artifact_hash": sha256_identity(source_bytes),
                "executable_hash": null
            },
            "binding": {
                "analysis_kind": "model_ir_linear_static",
                "case_id": recovery["case_id"],
                "model_identity": recovery["model_identity"],
                "analysis_request_hash": recovery["analysis_request_hash"],
                "load_pattern_id": recovery["load_pattern_id"],
                "coordinate_frame": "model_global"
            },
            "observations": [{
                "observation_id": "member-load-cantilever-tip-uy",
                "external_location_id": "node/N2/UY",
                "global_dof_index": 7,
                "dof": "UY",
                "native_result_path": "/global_displacement/7",
                "unit": "m",
                "value": expected_tip_uy,
                "tolerance": {"absolute": 1.0e-15, "relative": 1.0e-12}
            }]
        }))
        .expect("member-load external result JSON"),
    )
    .expect("member-load external result");
    Inputs {
        model,
        request,
        external,
        source,
    }
}

fn author_prescribed_support_model(root: &Path, repository: &Path) -> PathBuf {
    let baseline = repository.join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let edited = root.join("prescribed-support-edit");
    assert_success(&run_workbench(&[
        text("model-edit-constraint-value"),
        baseline.as_os_str(),
        text("--constraint"),
        text("BC1"),
        text("--dof"),
        text("UX"),
        text("--value"),
        text("0.001"),
        text("--output-dir"),
        edited.as_os_str(),
    ]));
    let edit_receipt = verify_self_hash(
        &fs::read(edited.join("edit-receipt.json")).expect("prescribed edit receipt"),
        "receipt_hash",
    );
    assert_eq!(edit_receipt["analysis_ready"], true);
    assert_eq!(edit_receipt["cpp_semantic_snapshot_verified"], true);
    let composed = root.join("prescribed-support-combination");
    assert_success(&run_workbench(&[
        text("model-add-linear-load-combination"),
        edited.join("model-ir.json").as_os_str(),
        text("--load-combination"),
        text("COMBO_PRESCRIBED"),
        text("--term"),
        text("LC_AXIAL"),
        text("1.0"),
        text("--term"),
        text("LC_WEAK"),
        text("1.0"),
        text("--output-dir"),
        composed.as_os_str(),
    ]));
    let combination_receipt = verify_self_hash(
        &fs::read(composed.join("edit-receipt.json")).expect("combination edit receipt"),
        "receipt_hash",
    );
    assert_eq!(combination_receipt["analysis_ready"], true);
    assert_eq!(combination_receipt["cpp_semantic_snapshot_verified"], true);
    composed.join("model-ir.json")
}

fn prepare_prescribed_support_inputs(root: &Path) -> Inputs {
    let repository = repository_root();
    let model = author_prescribed_support_model(root, &repository);
    let model_bytes = fs::read(&model).expect("prescribed ModelIR bytes");
    let parsed_model = parse_model_ir_v2(&model_bytes).expect("strict prescribed ModelIR");
    let baseline_request =
        repository.join("native/tests/fixtures/model_ir_linear/frame_cantilever_weak_request.json");
    let mut request_value: Value = serde_json::from_slice(
        &fs::read(baseline_request).expect("baseline linear request fixture"),
    )
    .expect("baseline linear request JSON");
    request_value["case_id"] = json!("model-frame-prescribed-support-c5");
    request_value["load_pattern_id"] = json!("COMBO_PRESCRIBED");
    request_value["model_identity"] = json!({
        "content_hash": parsed_model.content_hash(),
        "semantic_hash": parsed_model.semantic_hash(),
        "provenance_hash": parsed_model.provenance_hash()
    });
    let request = root.join("prescribed-support-request.json");
    fs::write(
        &request,
        canonicalize_model_ir_v2(&request_value).expect("canonical prescribed request"),
    )
    .expect("prescribed request fixture");
    let request_bytes = fs::read(&request).expect("prescribed request bytes");
    let direct = execute_model_ir_linear_analysis(&model_bytes, &request_bytes, None, u32::MAX)
        .expect("direct prescribed terminal result");
    assert!(direct.is_complete(), "{}", direct.run_receipt_json());
    let recovery: Value = serde_json::from_str(
        direct
            .result_recovery_ir_json()
            .expect("direct prescribed recovery IR"),
    )
    .expect("prescribed recovery JSON");
    let expected_tip_ux = 0.001_05_f64;
    assert!(
        (recovery["global_displacement"][6]
            .as_f64()
            .expect("prescribed node 2 UX displacement")
            - expected_tip_ux)
            .abs()
            <= 1.0e-15
    );
    let source_bytes = b"Axial bar prescribed-support oracle: u_tip=u_support+FL/EA\n";
    let source = root.join("prescribed-support-oracle.txt");
    fs::write(&source, source_bytes).expect("prescribed source artifact");
    let external = root.join("prescribed-support-external.json");
    fs::write(
        &external,
        serde_json::to_vec(&json!({
            "schema_version": "structural-model-ir-linear-external-result.v1",
            "comparison_id": "workbench-model-linear-prescribed-support-c5",
            "source": {
                "solver_family": "reference_oracle",
                "solver_version": "axial-prescribed-support-v1",
                "run_id": "workbench-model-linear-prescribed-support-run",
                "evidence_kind": "language_neutral_golden",
                "source_artifact_hash": sha256_identity(source_bytes),
                "executable_hash": null
            },
            "binding": {
                "analysis_kind": "model_ir_linear_static",
                "case_id": recovery["case_id"],
                "model_identity": recovery["model_identity"],
                "analysis_request_hash": recovery["analysis_request_hash"],
                "load_pattern_id": recovery["load_pattern_id"],
                "coordinate_frame": "model_global"
            },
            "observations": [{
                "observation_id": "prescribed-support-cantilever-tip-ux",
                "external_location_id": "node/N2/UX",
                "global_dof_index": 6,
                "dof": "UX",
                "native_result_path": "/global_displacement/6",
                "unit": "m",
                "value": expected_tip_ux,
                "tolerance": {"absolute": 1.0e-15, "relative": 1.0e-12}
            }]
        }))
        .expect("prescribed external result JSON"),
    )
    .expect("prescribed external result");
    Inputs {
        model,
        request,
        external,
        source,
    }
}

fn prepare_mgt_inputs() -> MgtInputs {
    let repository = repository_root();
    let source_mgt =
        repository.join("native/tests/fixtures/mgt_import/workbench_cantilever_frame3d_x.mgt");
    let model_id = "workbench-mgt-linear-cantilever-v1";
    let mgt_bytes = fs::read(&source_mgt).expect("MGT fixture");
    let imported = execute_native_mgt_import(&mgt_bytes, model_id).expect("normalized MGT import");
    assert!(imported.is_normalized());
    let model_bytes = imported
        .model_ir_json()
        .expect("normalized ModelIR")
        .as_bytes();
    let request =
        repository.join("native/tests/fixtures/model_ir_linear/mgt_cantilever_request.json");
    let external =
        repository.join("native/tests/fixtures/model_ir_linear/mgt_cantilever_external_v1.json");
    let source = repository.join(
        "native/tests/fixtures/model_ir_linear/mgt_cantilever_language_neutral_oracle_v1.txt",
    );
    let request_bytes = fs::read(&request).expect("MGT linear request bytes");
    let direct = execute_model_ir_linear_analysis(model_bytes, &request_bytes, None, u32::MAX)
        .expect("MGT linear direct terminal result");
    assert!(direct.is_complete());
    let recovery: Value = serde_json::from_str(
        direct
            .result_recovery_ir_json()
            .expect("MGT linear recovery IR"),
    )
    .expect("MGT linear recovery JSON");
    let displacement = recovery["global_displacement"][6]
        .as_f64()
        .expect("cantilever floor UX displacement");
    assert!((displacement - 0.016).abs() <= 1e-14);

    MgtInputs {
        source_mgt,
        model_id: model_id.to_owned(),
        request,
        external,
        source,
    }
}

fn import_arguments<'a>(inputs: &'a Inputs, workspace: &'a Path) -> Vec<&'a OsStr> {
    vec![
        text("import-model-linear"),
        inputs.model.as_os_str(),
        inputs.request.as_os_str(),
        text("--external-result"),
        inputs.external.as_os_str(),
        text("--source-artifact"),
        inputs.source.as_os_str(),
        text("--workspace"),
        workspace.as_os_str(),
    ]
}

fn mgt_import_arguments<'a>(
    command: &'a str,
    inputs: &'a MgtInputs,
    workspace: &'a Path,
    workflow: bool,
) -> Vec<&'a OsStr> {
    let mut arguments = vec![
        text(command),
        inputs.source_mgt.as_os_str(),
        inputs.request.as_os_str(),
        text("--model-id"),
        OsStr::new(&inputs.model_id),
        text("--external-result"),
        inputs.external.as_os_str(),
        text("--source-artifact"),
        inputs.source.as_os_str(),
        text("--workspace"),
        workspace.as_os_str(),
    ];
    if workflow {
        arguments.extend([text("--step-budget"), text("1")]);
    }
    arguments
}

fn stage_arguments<'a>(command: &'a str, workspace: &'a Path) -> [&'a OsStr; 3] {
    [text(command), text("--workspace"), workspace.as_os_str()]
}

fn collect_files(root: &Path) -> Vec<PathBuf> {
    fn visit(root: &Path, directory: &Path, output: &mut Vec<PathBuf>) {
        let mut entries = fs::read_dir(directory)
            .expect("read Workbench directory")
            .map(|entry| entry.expect("read Workbench entry"))
            .collect::<Vec<_>>();
        entries.sort_by_key(fs::DirEntry::file_name);
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

#[test]
fn one_iteration_linear_run_is_a_direct_terminal_workbench_transition() {
    let root = temporary_root("direct-terminal");
    fs::create_dir(&root).expect("temporary root");
    let example = repository_root().join("native/examples/frame3d-linear-cantilever");
    let model = example.join("model-calculix-axial.json");
    let request = example.join("analysis-request-axial.json");
    let external = example.join("external-result-calculix-proxy.json");
    let source = example.join("calculix-technical-proxy.txt");
    let workspace = root.join("workspace");

    assert_success(&run_workbench(&[
        text("import-model-linear"),
        model.as_os_str(),
        request.as_os_str(),
        text("--external-result"),
        external.as_os_str(),
        text("--source-artifact"),
        source.as_os_str(),
        text("--workspace"),
        workspace.as_os_str(),
    ]));
    assert_success(&run_workbench(&stage_arguments("validate", &workspace)));
    let validated_session =
        fs::read(workspace.join("workbench-session.json")).expect("validated session");
    assert_success(&run_workbench(&[
        text("run"),
        text("--workspace"),
        workspace.as_os_str(),
        text("--step-budget"),
        text("1"),
    ]));

    assert!(workspace.join("03-run/result-ir.json").is_file());
    assert!(workspace.join("03-run/result-recovery-ir.json").is_file());
    let run_receipt = verify_self_hash(
        &fs::read(workspace.join("03-run/run-receipt.json")).expect("direct run receipt"),
        "receipt_hash",
    );
    assert_eq!(run_receipt["status"], "completed");
    assert!(!workspace.join("04-resume").exists());

    fs::write(workspace.join("workbench-session.json"), validated_session)
        .expect("simulate crash before direct-terminal session persistence");
    let inspected = run_workbench(&stage_arguments("inspect", &workspace));
    assert_success(&inspected);
    let inspected = verify_self_hash(&inspected.stdout, "view_hash");
    assert_eq!(inspected["durable_stage"], "terminal");
    assert_eq!(inspected["terminal_status"], "completed");
    assert_eq!(inspected["workflow"][3]["stage"], "resume");
    assert_eq!(inspected["workflow"][3]["state"], "not_required");
    assert_eq!(inspected["next_action"], "compare");

    assert_success(&run_workbench(&[
        text("compare"),
        text("--workspace"),
        workspace.as_os_str(),
        text("--require-pass"),
    ]));
    assert_success(&run_workbench(&stage_arguments("report", &workspace)));
    assert!(workspace.join("06-report/report.pdf").is_file());
    assert!(!workspace.join("04-resume").exists());

    let workflow = root.join("workflow");
    assert_success(&run_workbench(&[
        text("workflow-model-linear"),
        model.as_os_str(),
        request.as_os_str(),
        text("--external-result"),
        external.as_os_str(),
        text("--source-artifact"),
        source.as_os_str(),
        text("--workspace"),
        workflow.as_os_str(),
        text("--step-budget"),
        text("1"),
    ]));
    let session = verify_self_hash(
        &fs::read(workflow.join("workbench-session.json")).expect("workflow session"),
        "session_hash",
    );
    assert_eq!(session["stage"], "reported");
    assert_eq!(session["terminal_status"], "completed");
    assert!(workflow.join("03-run/result-ir.json").is_file());
    assert!(!workflow.join("04-resume").exists());
}

#[test]
#[allow(clippy::too_many_lines)]
fn reported_linear_workbench_exports_bound_standalone_html_in_both_locales() {
    let root = temporary_root("html-report");
    fs::create_dir(&root).expect("temporary root");
    let example = repository_root().join("native/examples/frame3d-linear-cantilever");
    let workspace = root.join("workspace");
    assert_success(&run_workbench(&[
        text("workflow-model-linear"),
        example.join("model-calculix-axial.json").as_os_str(),
        example.join("analysis-request-axial.json").as_os_str(),
        text("--external-result"),
        example
            .join("external-result-calculix-proxy.json")
            .as_os_str(),
        text("--source-artifact"),
        example.join("calculix-technical-proxy.txt").as_os_str(),
        text("--workspace"),
        workspace.as_os_str(),
        text("--step-budget"),
        text("1"),
    ]));
    let session_before =
        fs::read(workspace.join("workbench-session.json")).expect("reported session");
    let english = root.join("html-en");
    let english_repeat = root.join("html-en-repeat");
    let korean = root.join("html-ko");
    for (output, locale) in [
        (&english, "en-US"),
        (&english_repeat, "en-US"),
        (&korean, "ko-KR"),
    ] {
        assert_success(&run_workbench(&[
            text("report-export-html"),
            text("--workspace"),
            workspace.as_os_str(),
            text("--output-dir"),
            output.as_os_str(),
            text("--locale"),
            text(locale),
        ]));
    }

    assert_eq!(
        fs::read(english.join("report.html")).expect("English HTML"),
        fs::read(english_repeat.join("report.html")).expect("repeated English HTML")
    );
    assert_eq!(
        fs::read(english.join("html-receipt.json")).expect("English receipt"),
        fs::read(english_repeat.join("html-receipt.json")).expect("repeated English receipt")
    );
    let html_bytes = fs::read(english.join("report.html")).expect("English HTML");
    let html = std::str::from_utf8(&html_bytes).expect("UTF-8 HTML");
    for expected in [
        "<!doctype html>",
        "Analysis summary and identities",
        "Nodal displacements",
        "Constrained reactions",
        "Member forces and element recovery",
        "External comparison",
        "calculix",
        "proxy",
        "Within tolerance",
    ] {
        assert!(html.contains(expected), "missing HTML content: {expected}");
    }
    assert!(!html.contains("<script"));
    assert!(!html.contains("http://"));
    assert!(!html.contains("https://"));
    let receipt = verify_self_hash(
        &fs::read(english.join("html-receipt.json")).expect("HTML receipt"),
        "receipt_hash",
    );
    assert_eq!(
        receipt["schema_version"],
        "structural-native-workbench-model-ir-linear-html-report-receipt.v1"
    );
    assert_eq!(receipt["status"], "exported");
    assert_eq!(receipt["locale"], "en-US");
    assert_eq!(receipt["html_hash"], sha256_identity(&html_bytes));
    let comparison: Value = serde_json::from_slice(
        &fs::read(workspace.join("05-compare/external-comparison-ir.json")).expect("comparison IR"),
    )
    .expect("comparison JSON");
    assert_eq!(
        receipt["source_comparison_hash"],
        comparison["comparison_hash"]
    );
    let korean_html = fs::read_to_string(korean.join("report.html")).expect("Korean HTML");
    assert!(korean_html.contains("절점 변위"));
    assert!(korean_html.contains("부재력 및 요소 복원"));
    assert_ne!(html_bytes, korean_html.as_bytes());
    assert_eq!(
        fs::read(workspace.join("workbench-session.json")).expect("session after export"),
        session_before
    );

    let overwrite = run_workbench(&[
        text("report-export-html"),
        text("--workspace"),
        workspace.as_os_str(),
        text("--output-dir"),
        english.as_os_str(),
    ]);
    assert_eq!(overwrite.status.code(), Some(1));
    assert!(
        String::from_utf8_lossy(&overwrite.stdout).contains("workbench_stage_destination_exists")
    );

    let comparison_path = workspace.join("05-compare/external-comparison-ir.json");
    let mut tampered_comparison =
        fs::read(&comparison_path).expect("comparison bytes before tamper");
    let solver_offset = tampered_comparison
        .windows(b"calculix".len())
        .position(|window| window == b"calculix")
        .expect("CalculiX identity");
    tampered_comparison[solver_offset] = b'C';
    fs::write(&comparison_path, tampered_comparison).expect("tamper comparison identity");
    let tampered_output = root.join("html-tampered");
    let rejected = run_workbench(&[
        text("report-export-html"),
        text("--workspace"),
        workspace.as_os_str(),
        text("--output-dir"),
        tampered_output.as_os_str(),
    ]);
    assert_eq!(rejected.status.code(), Some(1));
    let rejected_stdout = String::from_utf8_lossy(&rejected.stdout);
    assert!(
        rejected_stdout.contains("workbench_artifact_inventory_mismatch"),
        "unexpected tamper rejection: {rejected_stdout}"
    );
    assert!(!tampered_output.exists());
}

#[test]
#[allow(clippy::too_many_lines)]
fn clean_environment_linear_workflow_restarts_and_reprojects_exactly() {
    let root = temporary_root("restart");
    fs::create_dir(&root).expect("temporary root");
    let inputs = prepare_inputs(&root);
    let restarted = root.join("restarted");
    let direct = root.join("direct");

    assert_success(&run_workbench(&import_arguments(&inputs, &restarted)));
    assert_success(&run_workbench(&stage_arguments("validate", &restarted)));
    let validated_session =
        fs::read(restarted.join("workbench-session.json")).expect("validated session");
    let premature_deformed_view = run_workbench(&[
        text("result-deformed-view"),
        text("--workspace"),
        restarted.as_os_str(),
    ]);
    assert_eq!(premature_deformed_view.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&premature_deformed_view.stdout)
        .contains("workbench_transition_invalid"));
    let premature_element_recovery_view = run_workbench(&[
        text("element-recovery-view"),
        text("--workspace"),
        restarted.as_os_str(),
    ]);
    assert_eq!(premature_element_recovery_view.status.code(), Some(2));
    assert!(
        String::from_utf8_lossy(&premature_element_recovery_view.stdout)
            .contains("workbench_transition_invalid")
    );
    assert_success(&run_workbench(&[
        text("run"),
        text("--workspace"),
        restarted.as_os_str(),
        text("--step-budget"),
        text("1"),
    ]));
    assert!(restarted.join("03-run/checkpoint.mlpcp").is_file());
    assert!(!restarted.join("03-run/result-ir.json").exists());

    fs::write(restarted.join("workbench-session.json"), validated_session)
        .expect("simulate crash before session persistence");
    assert_success(&run_workbench(&stage_arguments("resume", &restarted)));
    assert_success(&run_workbench(&[
        text("compare"),
        text("--workspace"),
        restarted.as_os_str(),
        text("--require-pass"),
    ]));
    assert_success(&run_workbench(&stage_arguments("report", &restarted)));

    assert_success(&run_workbench(&[
        text("workflow-model-linear"),
        inputs.model.as_os_str(),
        inputs.request.as_os_str(),
        text("--external-result"),
        inputs.external.as_os_str(),
        text("--source-artifact"),
        inputs.source.as_os_str(),
        text("--workspace"),
        direct.as_os_str(),
        text("--step-budget"),
        text("1"),
    ]));

    for relative in [
        "workbench-session.json",
        "04-resume/result-ir.json",
        "04-resume/result-recovery-ir.json",
        "04-resume/reaction-result-ir.json",
        "04-resume/report-ir.json",
        "04-resume/report.md",
        "04-resume/run-receipt.json",
        "05-compare/external-comparison-ir.json",
        "05-compare/comparison-receipt.json",
        "06-report/result-ir.json",
        "06-report/result-recovery-ir.json",
        "06-report/reaction-result-ir.json",
        "06-report/report-ir.json",
        "06-report/report.md",
        "06-report/report.pdf",
        "06-report/pdf-receipt.json",
        "06-report/report-receipt.json",
    ] {
        assert_eq!(
            fs::read(restarted.join(relative)).expect("restarted artifact"),
            fs::read(direct.join(relative)).expect("direct artifact"),
            "restart drift: {relative}"
        );
    }

    let session = verify_self_hash(
        &fs::read(restarted.join("workbench-session.json")).expect("session"),
        "session_hash",
    );
    assert_eq!(session["stage"], "reported");
    assert_eq!(session["analysis_profile"], "model_ir_linear_cpu_v1");
    assert_eq!(session["terminal_status"], "completed");
    assert_eq!(session["comparison_passed"], true);
    let report_receipt = verify_self_hash(
        &fs::read(restarted.join("06-report/report-receipt.json")).expect("report receipt"),
        "receipt_hash",
    );
    assert_eq!(report_receipt["status"], "reported");
    assert_eq!(
        report_receipt["schema_version"],
        "structural-native-model-ir-linear-pdf-report-receipt.v1"
    );
    let pdf = fs::read(restarted.join("06-report/report.pdf")).expect("linear PDF");
    validate_deterministic_pdf_v1(&pdf).expect("linear PDF structure");
    assert_eq!(report_receipt["pdf_hash"], sha256_identity(&pdf));
    let reaction_bytes =
        fs::read(restarted.join("04-resume/reaction-result-ir.json")).expect("reaction ResultIR");
    let reaction = verify_self_hash(&reaction_bytes, "result_hash");
    assert_eq!(
        reaction["constrained_dof_indices"],
        json!([0, 1, 2, 3, 4, 5])
    );
    assert_eq!(
        reaction["summary"]["maximum_absolute_reaction_component"],
        20_000
    );
    assert_eq!(reaction["backend_receipt"]["fallback_count"], 0);
    assert_eq!(
        report_receipt["source_reaction_hash"],
        reaction["result_hash"]
    );

    let inspected = run_workbench(&stage_arguments("inspect", &restarted));
    assert_success(&inspected);
    let inspected = verify_self_hash(&inspected.stdout, "view_hash");
    assert_eq!(inspected["analysis_profile"], "model_ir_linear_cpu_v1");
    assert_eq!(
        inspected["report"]["source_recovery_hash"],
        report_receipt["source_recovery_hash"]
    );
    assert_eq!(
        inspected["constrained_reactions"]["result_hash"],
        reaction["result_hash"]
    );
    let report_view = run_workbench(&[
        text("report-view"),
        text("--workspace"),
        restarted.as_os_str(),
        text("--locale"),
        text("ko-KR"),
    ]);
    assert_success(&report_view);
    let report_text = String::from_utf8_lossy(&report_view.stdout);
    assert!(report_text.contains("구조 ModelIR 선형 Workbench 보고서"));
    assert!(report_text.contains("최대 절대 구속 반력"));
    assert!(report_text.contains("structural-native-workbench-model-ir-linear-report-view.v1"));
    assert!(report_text.contains("# Sparse Linear Analysis Report"));

    let session_before_result_surfaces =
        fs::read(restarted.join("workbench-session.json")).expect("session before result surfaces");
    let result_bytes =
        fs::read(restarted.join("04-resume/result-ir.json")).expect("sparse ResultIR");
    let result = verify_self_hash(&result_bytes, "result_hash");
    let recovery_bytes = fs::read(restarted.join("04-resume/result-recovery-ir.json"))
        .expect("linear recovery ResultIR");
    let recovery = verify_self_hash(&recovery_bytes, "recovery_hash");
    let displacement_view_arguments = [
        text("nodal-displacement-view"),
        text("--workspace"),
        restarted.as_os_str(),
    ];
    let displacement_view_first = run_workbench(&displacement_view_arguments);
    let displacement_view_second = run_workbench(&displacement_view_arguments);
    assert_success(&displacement_view_first);
    assert_eq!(
        displacement_view_first.stdout,
        displacement_view_second.stdout
    );
    assert!(!displacement_view_first.stdout.contains(&0x1b));
    let direct_displacement_view = run_workbench(&[
        text("nodal-displacement-view"),
        text("--workspace"),
        direct.as_os_str(),
    ]);
    assert_success(&direct_displacement_view);
    assert_eq!(
        displacement_view_first.stdout,
        direct_displacement_view.stdout
    );
    let displacement_view =
        String::from_utf8(displacement_view_first.stdout).expect("ASCII displacement view");
    assert!(displacement_view
        .starts_with("Structural ModelIR Linear Workbench - Nodal Displacements\n"));
    assert!(displacement_view.contains(
        "Schema: structural-native-workbench-model-ir-linear-nodal-displacement-view.v1\n"
    ));
    assert!(displacement_view.contains("Displayed nodes: 1-2 of 2\n"));
    assert!(displacement_view.contains(&format!(
        "Backend: cpu / fp64 / ABI {} / fallback 0\n",
        result["backend_receipt"]["abi_version"]
            .as_str()
            .expect("sparse ABI version")
    )));
    for hash in [
        recovery["source_result_hash"]
            .as_str()
            .expect("source result hash"),
        recovery["recovery_hash"].as_str().expect("recovery hash"),
        recovery["analysis_request_hash"]
            .as_str()
            .expect("analysis request hash"),
        recovery["assembly_hash"].as_str().expect("assembly hash"),
        recovery["model_identity"]["content_hash"]
            .as_str()
            .expect("model content hash"),
        recovery["model_identity"]["semantic_hash"]
            .as_str()
            .expect("model semantic hash"),
        recovery["model_identity"]["provenance_hash"]
            .as_str()
            .expect("model provenance hash"),
        result["identity"]["request_hash"]
            .as_str()
            .expect("sparse request hash"),
        result["identity"]["model_hash"]
            .as_str()
            .expect("sparse model hash"),
        result["identity"]["state_hash"]
            .as_str()
            .expect("state hash"),
        result["identity"]["execution_hash"]
            .as_str()
            .expect("execution hash"),
        result["identity"]["checkpoint_hash"]
            .as_str()
            .expect("checkpoint hash"),
    ] {
        assert!(displacement_view.contains(hash));
    }
    for (node_index, node_id) in ["N1", "N2"].iter().enumerate() {
        let offset = node_index * 6;
        let expected_row = format!(
            "{:06}\t{}\t{:010}\t{:+.17e}\t{:+.17e}\t{:+.17e}\t{:+.17e}\t{:+.17e}\t{:+.17e}",
            node_index + 1,
            node_id,
            node_index,
            recovery["global_displacement"][offset]
                .as_f64()
                .expect("UX displacement"),
            recovery["global_displacement"][offset + 1]
                .as_f64()
                .expect("UY displacement"),
            recovery["global_displacement"][offset + 2]
                .as_f64()
                .expect("UZ displacement"),
            recovery["global_displacement"][offset + 3]
                .as_f64()
                .expect("RX displacement"),
            recovery["global_displacement"][offset + 4]
                .as_f64()
                .expect("RY displacement"),
            recovery["global_displacement"][offset + 5]
                .as_f64()
                .expect("RZ displacement"),
        );
        assert!(displacement_view.lines().any(|line| line == expected_row));
    }
    let (unsigned, hash_line) = displacement_view
        .rsplit_once("View hash: ")
        .expect("displacement view hash line");
    assert_eq!(hash_line.trim_end(), sha256_identity(unsigned.as_bytes()));

    let korean_displacement_arguments = [
        text("nodal-displacement-view"),
        text("--workspace"),
        restarted.as_os_str(),
        text("--locale"),
        text("ko-KR"),
        text("--start-node"),
        text("2"),
        text("--count"),
        text("1"),
    ];
    let korean_displacement_first = run_workbench(&korean_displacement_arguments);
    let korean_displacement_second = run_workbench(&korean_displacement_arguments);
    assert_success(&korean_displacement_first);
    assert_eq!(
        korean_displacement_first.stdout,
        korean_displacement_second.stdout
    );
    assert!(!korean_displacement_first.stdout.contains(&0x1b));
    let korean_displacement = String::from_utf8(korean_displacement_first.stdout)
        .expect("Korean displacement view UTF-8");
    assert!(korean_displacement.starts_with("Structural ModelIR 선형 Workbench - 노드 변위\n"));
    assert!(korean_displacement.contains("로케일: ko-KR\n"));
    assert!(korean_displacement.contains("표시 노드: 2-2 / 2\n"));
    assert!(!korean_displacement
        .lines()
        .any(|line| line.starts_with("000001\t")));
    assert!(korean_displacement
        .lines()
        .any(|line| line.starts_with("000002\tN2\t")));
    let (unsigned, hash_line) = korean_displacement
        .rsplit_once("보기 해시: ")
        .expect("Korean displacement view hash line");
    assert_eq!(hash_line.trim_end(), sha256_identity(unsigned.as_bytes()));
    for arguments in [
        vec![
            text("nodal-displacement-view"),
            text("--workspace"),
            restarted.as_os_str(),
            text("--count"),
            text("257"),
        ],
        vec![
            text("nodal-displacement-view"),
            text("--workspace"),
            restarted.as_os_str(),
            text("--start-node"),
            text("3"),
        ],
    ] {
        let rejected = run_workbench(&arguments);
        assert_eq!(rejected.status.code(), Some(2));
    }

    let element_view_arguments = [
        text("element-recovery-view"),
        text("--workspace"),
        restarted.as_os_str(),
    ];
    let element_view_first = run_workbench(&element_view_arguments);
    let element_view_second = run_workbench(&element_view_arguments);
    assert_success(&element_view_first);
    assert_eq!(element_view_first.stdout, element_view_second.stdout);
    assert!(!element_view_first.stdout.contains(&0x1b));
    let direct_element_view = run_workbench(&[
        text("element-recovery-view"),
        text("--workspace"),
        direct.as_os_str(),
    ]);
    assert_success(&direct_element_view);
    assert_eq!(element_view_first.stdout, direct_element_view.stdout);
    let element_view =
        String::from_utf8(element_view_first.stdout).expect("ASCII element recovery view");
    assert!(element_view.starts_with("Structural ModelIR Linear Workbench - Element Recovery\n"));
    assert!(element_view.contains(
        "Schema: structural-native-workbench-model-ir-linear-element-recovery-view.v1\n"
    ));
    assert!(element_view.contains("Locale: en-US\n"));
    assert!(element_view.contains("Selected state: 1 of 1 (terminal linear static)\n"));
    assert!(element_view.contains("Elements: 1\n"));
    assert!(element_view.contains("Displayed elements: 1-1 of 1\n"));
    assert!(
        element_view.contains("Coordinate frames: frame3d=element_local; truss3d=element_axis\n")
    );
    assert!(element_view.contains(&format!(
        "Backend: cpu / fp64 / ABI {} / fallback 0\n",
        result["backend_receipt"]["abi_version"]
            .as_str()
            .expect("sparse ABI version")
    )));
    for hash in [
        recovery["source_result_hash"]
            .as_str()
            .expect("source result hash"),
        recovery["recovery_hash"].as_str().expect("recovery hash"),
        recovery["analysis_request_hash"]
            .as_str()
            .expect("analysis request hash"),
        recovery["assembly_hash"].as_str().expect("assembly hash"),
        recovery["model_identity"]["content_hash"]
            .as_str()
            .expect("model content hash"),
        recovery["model_identity"]["semantic_hash"]
            .as_str()
            .expect("model semantic hash"),
        recovery["model_identity"]["provenance_hash"]
            .as_str()
            .expect("model provenance hash"),
        result["identity"]["request_hash"]
            .as_str()
            .expect("sparse request hash"),
        result["identity"]["model_hash"]
            .as_str()
            .expect("sparse model hash"),
        result["identity"]["state_hash"]
            .as_str()
            .expect("state hash"),
        result["identity"]["execution_hash"]
            .as_str()
            .expect("execution hash"),
        result["identity"]["checkpoint_hash"]
            .as_str()
            .expect("checkpoint hash"),
    ] {
        assert!(element_view.contains(hash));
    }
    assert_eq!(recovery["recovery_stable_indices"], json!([0]));
    assert_eq!(recovery["recovery_element_types"], json!([1]));
    assert_eq!(recovery["recovery_offsets"], json!([0, 12]));
    let frame_components = [
        "i_FX_N", "i_FY_N", "i_FZ_N", "i_MX_N_m", "i_MY_N_m", "i_MZ_N_m", "j_FX_N", "j_FY_N",
        "j_FZ_N", "j_MX_N_m", "j_MY_N_m", "j_MZ_N_m",
    ]
    .iter()
    .zip(
        recovery["recovery_values"]
            .as_array()
            .expect("frame recovery values"),
    )
    .map(|(name, value)| {
        format!(
            "{name}={:+.17e}",
            value.as_f64().expect("frame recovery FP64 value")
        )
    })
    .collect::<Vec<_>>()
    .join(";");
    let expected_element_row =
        format!("000001\tE1\t0000000000\tframe_3d\tN1->N2\telement_local\t{frame_components}");
    assert!(element_view
        .lines()
        .any(|line| line == expected_element_row));
    let (unsigned, hash_line) = element_view
        .rsplit_once("View hash: ")
        .expect("element recovery view hash line");
    assert_eq!(hash_line.trim_end(), sha256_identity(unsigned.as_bytes()));

    let korean_element_view = run_workbench(&[
        text("element-recovery-view"),
        text("--workspace"),
        restarted.as_os_str(),
        text("--locale"),
        text("ko-KR"),
        text("--start-element"),
        text("1"),
        text("--count"),
        text("1"),
    ]);
    assert_success(&korean_element_view);
    assert!(!korean_element_view.stdout.contains(&0x1b));
    let korean_element_view =
        String::from_utf8(korean_element_view.stdout).expect("Korean element recovery view UTF-8");
    assert!(korean_element_view.starts_with("Structural ModelIR 선형 Workbench - 요소 복원\n"));
    assert!(korean_element_view.contains("로케일: ko-KR\n"));
    assert!(korean_element_view.contains("표시 요소: 1-1 of 1\n"));
    assert!(korean_element_view
        .lines()
        .any(|line| line == expected_element_row));
    let (unsigned, hash_line) = korean_element_view
        .rsplit_once("보기 해시: ")
        .expect("Korean element recovery view hash line");
    assert_eq!(hash_line.trim_end(), sha256_identity(unsigned.as_bytes()));
    for arguments in [
        vec![
            text("element-recovery-view"),
            text("--workspace"),
            restarted.as_os_str(),
            text("--count"),
            text("257"),
        ],
        vec![
            text("element-recovery-view"),
            text("--workspace"),
            restarted.as_os_str(),
            text("--start-element"),
            text("2"),
        ],
    ] {
        let rejected = run_workbench(&arguments);
        assert_eq!(rejected.status.code(), Some(2));
    }

    let deformed_view_arguments = [
        text("result-deformed-view"),
        text("--workspace"),
        restarted.as_os_str(),
        text("--projection"),
        text("xy"),
        text("--scale"),
        text("1000"),
    ];
    let deformed_view_first = run_workbench(&deformed_view_arguments);
    let deformed_view_second = run_workbench(&deformed_view_arguments);
    assert_success(&deformed_view_first);
    assert_eq!(deformed_view_first.stdout, deformed_view_second.stdout);
    assert!(!deformed_view_first.stdout.contains(&0x1b));
    let direct_deformed_view = run_workbench(&[
        text("result-deformed-view"),
        text("--workspace"),
        direct.as_os_str(),
        text("--projection"),
        text("xy"),
        text("--scale"),
        text("1000"),
    ]);
    assert_success(&direct_deformed_view);
    assert_eq!(deformed_view_first.stdout, direct_deformed_view.stdout);
    let explicit_state = run_workbench(&[
        text("result-deformed-view"),
        text("--workspace"),
        restarted.as_os_str(),
        text("--projection"),
        text("xy"),
        text("--step"),
        text("1"),
        text("--scale"),
        text("1000"),
    ]);
    assert_success(&explicit_state);
    assert_eq!(deformed_view_first.stdout, explicit_state.stdout);
    let deformed_view =
        String::from_utf8(deformed_view_first.stdout).expect("ASCII linear deformed view");
    assert!(deformed_view.starts_with("Structural ModelIR Linear Workbench - Deformed Shape\n"));
    assert!(deformed_view
        .contains("Schema: structural-native-workbench-model-ir-linear-deformed-view.v1\n"));
    assert!(deformed_view.contains("Locale: en-US\n"));
    assert!(deformed_view.contains("Projection: xy\n"));
    assert!(deformed_view.contains("Selected state: 1 of 1 (terminal linear static)\n"));
    assert!(deformed_view.contains("Visual magnification: 1.00000000000000000e3\n"));
    assert!(deformed_view.contains("Inventory: nodes=2 elements=1\n"));
    assert!(deformed_view.contains(&format!(
        "Backend: cpu / fp64 / ABI {} / fallback 0\n",
        result["backend_receipt"]["abi_version"]
            .as_str()
            .expect("sparse ABI version")
    )));
    assert!(deformed_view.contains(
        "Rotation treatment: RX/RY/RZ are reported in rad but are not applied to centerline coordinates\n"
    ));
    for hash in [
        recovery["source_result_hash"]
            .as_str()
            .expect("source result hash"),
        recovery["recovery_hash"].as_str().expect("recovery hash"),
        recovery["analysis_request_hash"]
            .as_str()
            .expect("analysis request hash"),
        recovery["assembly_hash"].as_str().expect("assembly hash"),
        recovery["model_identity"]["content_hash"]
            .as_str()
            .expect("model content hash"),
        recovery["model_identity"]["semantic_hash"]
            .as_str()
            .expect("model semantic hash"),
        recovery["model_identity"]["provenance_hash"]
            .as_str()
            .expect("model provenance hash"),
        result["identity"]["request_hash"]
            .as_str()
            .expect("sparse request hash"),
        result["identity"]["model_hash"]
            .as_str()
            .expect("sparse model hash"),
        result["identity"]["state_hash"]
            .as_str()
            .expect("state hash"),
        result["identity"]["execution_hash"]
            .as_str()
            .expect("execution hash"),
        result["identity"]["checkpoint_hash"]
            .as_str()
            .expect("checkpoint hash"),
    ] {
        assert!(deformed_view.contains(hash));
    }
    let tip_displacement = (0..6)
        .map(|offset| {
            recovery["global_displacement"][6 + offset]
                .as_f64()
                .expect("tip displacement component")
        })
        .collect::<Vec<_>>();
    let expected_tip_prefix = format!(
        "  000002 N2 original_xyz_m=[{:+.17e},{:+.17e},{:+.17e}] translation_m=[{:+.17e},{:+.17e},{:+.17e}] rotation_rad=[{:+.17e},{:+.17e},{:+.17e}] magnified_xyz_m=[{:+.17e},{:+.17e},{:+.17e}]",
        2.0,
        0.0,
        0.0,
        tip_displacement[0],
        tip_displacement[1],
        tip_displacement[2],
        tip_displacement[3],
        tip_displacement[4],
        tip_displacement[5],
        2.0 + tip_displacement[0] * 1_000.0,
        tip_displacement[1] * 1_000.0,
        tip_displacement[2] * 1_000.0,
    );
    assert!(deformed_view
        .lines()
        .any(|line| line.starts_with(&expected_tip_prefix)));
    assert!(deformed_view.contains("  000001 E1 element_index=0000000000 frame_3d N1 -> N2\n"));
    let (unsigned, hash_line) = deformed_view
        .rsplit_once("View hash: ")
        .expect("linear deformed view hash line");
    assert_eq!(hash_line.trim_end(), sha256_identity(unsigned.as_bytes()));

    let korean_deformed_first = run_workbench(&[
        text("result-deformed-view"),
        text("--workspace"),
        restarted.as_os_str(),
        text("--locale"),
        text("ko-KR"),
        text("--projection"),
        text("xy"),
        text("--scale"),
        text("1000"),
    ]);
    let korean_deformed_second = run_workbench(&[
        text("result-deformed-view"),
        text("--workspace"),
        restarted.as_os_str(),
        text("--locale"),
        text("ko-KR"),
        text("--projection"),
        text("xy"),
        text("--scale"),
        text("1000"),
    ]);
    assert_success(&korean_deformed_first);
    assert_eq!(korean_deformed_first.stdout, korean_deformed_second.stdout);
    assert_ne!(korean_deformed_first.stdout, deformed_view.as_bytes());
    assert!(!korean_deformed_first.stdout.contains(&0x1b));
    let korean_deformed =
        String::from_utf8(korean_deformed_first.stdout).expect("Korean linear deformed view UTF-8");
    assert!(korean_deformed.starts_with("Structural ModelIR 선형 Workbench - 변형 형상\n"));
    assert!(korean_deformed.contains("로케일: ko-KR\n"));
    assert!(korean_deformed.contains("선택 상태: 1 of 1 (terminal linear static)\n"));
    let (unsigned, hash_line) = korean_deformed
        .rsplit_once("보기 해시: ")
        .expect("Korean linear deformed view hash line");
    assert_eq!(hash_line.trim_end(), sha256_identity(unsigned.as_bytes()));

    let invalid_linear_step = run_workbench(&[
        text("result-deformed-view"),
        text("--workspace"),
        restarted.as_os_str(),
        text("--step"),
        text("2"),
    ]);
    assert_eq!(invalid_linear_step.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&invalid_linear_step.stdout)
        .contains("workbench_deformed_view_step_invalid"));

    let reaction_view_arguments = [
        text("reaction-view"),
        text("--workspace"),
        restarted.as_os_str(),
    ];
    let reaction_view_first = run_workbench(&reaction_view_arguments);
    let reaction_view_second = run_workbench(&reaction_view_arguments);
    assert_success(&reaction_view_first);
    assert_eq!(reaction_view_first.stdout, reaction_view_second.stdout);
    assert!(!reaction_view_first.stdout.contains(&0x1b));
    let direct_reaction_view = run_workbench(&[
        text("reaction-view"),
        text("--workspace"),
        direct.as_os_str(),
    ]);
    assert_success(&direct_reaction_view);
    assert_eq!(reaction_view_first.stdout, direct_reaction_view.stdout);
    let reaction_view = String::from_utf8(reaction_view_first.stdout).expect("ASCII reaction view");
    assert!(
        reaction_view.starts_with("Structural ModelIR Linear Workbench - Constrained Reactions\n")
    );
    assert!(reaction_view
        .contains("Schema: structural-native-workbench-model-ir-linear-reaction-view.v1\n"));
    assert!(reaction_view.contains("Displayed rows: 1-6 of 6\n"));
    assert!(reaction_view.contains("Backend: cpu / fp64 / ABI 0x0001000e / fallback 0\n"));
    for hash in [
        reaction["source_result_hash"]
            .as_str()
            .expect("source result hash"),
        reaction["source_recovery_hash"]
            .as_str()
            .expect("source recovery hash"),
        reaction["result_hash"].as_str().expect("reaction hash"),
        reaction["analysis_request_hash"]
            .as_str()
            .expect("analysis request hash"),
        reaction["assembly_hash"].as_str().expect("assembly hash"),
        reaction["model_identity"]["content_hash"]
            .as_str()
            .expect("model content hash"),
        reaction["model_identity"]["semantic_hash"]
            .as_str()
            .expect("model semantic hash"),
        reaction["model_identity"]["provenance_hash"]
            .as_str()
            .expect("model provenance hash"),
        reaction["identity"]["request_hash"]
            .as_str()
            .expect("sparse request hash"),
        reaction["identity"]["model_hash"]
            .as_str()
            .expect("sparse model hash"),
        reaction["identity"]["state_hash"]
            .as_str()
            .expect("state hash"),
        reaction["identity"]["execution_hash"]
            .as_str()
            .expect("execution hash"),
        reaction["identity"]["checkpoint_hash"]
            .as_str()
            .expect("checkpoint hash"),
    ] {
        assert!(reaction_view.contains(hash));
    }
    let dofs = ["UX", "UY", "UZ", "RX", "RY", "RZ"];
    for position in 0..6 {
        let global_dof = reaction["constrained_dof_indices"][position]
            .as_u64()
            .expect("constrained global DOF");
        let component = usize::try_from(global_dof % 6).expect("component index");
        let unit = if component < 3 { "N" } else { "N*m" };
        let expected_row = format!(
            "{:06}\tN1\t{}\t{:010}\t{:+.17e}\t{:+.17e}\t{:+.17e}\t{}",
            position + 1,
            dofs[component],
            global_dof,
            reaction["constrained_internal_force"][position]
                .as_f64()
                .expect("constrained internal force"),
            reaction["constrained_external_load"][position]
                .as_f64()
                .expect("constrained external load"),
            reaction["reactions"][position]
                .as_f64()
                .expect("constrained reaction"),
            unit,
        );
        assert!(reaction_view.lines().any(|line| line == expected_row));
    }
    let (unsigned, hash_line) = reaction_view
        .rsplit_once("View hash: ")
        .expect("reaction view hash line");
    assert_eq!(hash_line.trim_end(), sha256_identity(unsigned.as_bytes()));

    let korean_window_arguments = [
        text("reaction-view"),
        text("--workspace"),
        restarted.as_os_str(),
        text("--locale"),
        text("ko-KR"),
        text("--start-row"),
        text("2"),
        text("--count"),
        text("2"),
    ];
    let korean_window_first = run_workbench(&korean_window_arguments);
    let korean_window_second = run_workbench(&korean_window_arguments);
    assert_success(&korean_window_first);
    assert_eq!(korean_window_first.stdout, korean_window_second.stdout);
    assert!(!korean_window_first.stdout.contains(&0x1b));
    let korean_window =
        String::from_utf8(korean_window_first.stdout).expect("Korean reaction view UTF-8");
    assert!(korean_window.starts_with("Structural ModelIR 선형 Workbench - 구속 반력\n"));
    assert!(korean_window.contains("로케일: ko-KR\n"));
    assert!(korean_window.contains("표시 행: 2-3 / 6\n"));
    assert!(!korean_window
        .lines()
        .any(|line| line.starts_with("000001\t")));
    assert!(korean_window
        .lines()
        .any(|line| line.starts_with("000002\t")));
    assert!(korean_window
        .lines()
        .any(|line| line.starts_with("000003\t")));
    assert!(!korean_window
        .lines()
        .any(|line| line.starts_with("000004\t")));
    let (unsigned, hash_line) = korean_window
        .rsplit_once("보기 해시: ")
        .expect("Korean reaction view hash line");
    assert_eq!(hash_line.trim_end(), sha256_identity(unsigned.as_bytes()));
    for arguments in [
        vec![
            text("reaction-view"),
            text("--workspace"),
            restarted.as_os_str(),
            text("--count"),
            text("257"),
        ],
        vec![
            text("reaction-view"),
            text("--workspace"),
            restarted.as_os_str(),
            text("--start-row"),
            text("7"),
        ],
    ] {
        let rejected = run_workbench(&arguments);
        assert_eq!(rejected.status.code(), Some(2));
    }

    let reaction_audit_arguments = [
        text("reaction-audit"),
        text("--workspace"),
        restarted.as_os_str(),
    ];
    let reaction_audit_first = run_workbench(&reaction_audit_arguments);
    let reaction_audit_second = run_workbench(&reaction_audit_arguments);
    assert_success(&reaction_audit_first);
    assert_eq!(reaction_audit_first.stdout, reaction_audit_second.stdout);
    assert!(!reaction_audit_first.stdout.contains(&0x1b));
    let direct_reaction_audit = run_workbench(&[
        text("reaction-audit"),
        text("--workspace"),
        direct.as_os_str(),
    ]);
    assert_success(&direct_reaction_audit);
    assert_eq!(reaction_audit_first.stdout, direct_reaction_audit.stdout);
    let reaction_audit =
        String::from_utf8(reaction_audit_first.stdout).expect("ASCII reaction audit");
    assert!(reaction_audit
        .starts_with("Structural ModelIR Linear Workbench - Algebraic Global Equilibrium Audit\n"));
    assert!(reaction_audit
        .contains("Schema: structural-native-workbench-model-ir-linear-reaction-audit.v1\n"));
    assert!(reaction_audit.contains(
        "Tolerance policy: 256*IEEE754_BINARY64_EPSILON*max(1,absolute_contribution_scale)\n"
    ));
    assert!(reaction_audit.contains(
        "Applied force resultant: X=+0.00000000000000000e0; Y=-1.00000000000000000e4; Z=+0.00000000000000000e0 N\n"
    ));
    assert!(reaction_audit.contains(
        "Support reaction force resultant: X=+0.00000000000000000e0; Y=+1.00000000000000000e4; Z=+0.00000000000000000e0 N\n"
    ));
    assert!(reaction_audit.contains(
        "Applied moment resultant: X=+0.00000000000000000e0; Y=+0.00000000000000000e0; Z=-2.00000000000000000e4 N*m\n"
    ));
    assert!(reaction_audit.contains(
        "Support reaction moment resultant: X=+0.00000000000000000e0; Y=+0.00000000000000000e0; Z=+2.00000000000000000e4 N*m\n"
    ));
    for status in [
        "Force status: within_numeric_tolerance\n",
        "Moment status: within_numeric_tolerance\n",
        "Active equation status: within_numeric_tolerance\n",
        "Overall numeric status: within_numeric_tolerance\n",
    ] {
        assert!(reaction_audit.contains(status));
    }
    for hash in [
        reaction["source_result_hash"]
            .as_str()
            .expect("source result hash"),
        reaction["source_recovery_hash"]
            .as_str()
            .expect("source recovery hash"),
        reaction["result_hash"].as_str().expect("reaction hash"),
        reaction["analysis_request_hash"]
            .as_str()
            .expect("analysis request hash"),
        reaction["assembly_hash"].as_str().expect("assembly hash"),
        reaction["model_identity"]["content_hash"]
            .as_str()
            .expect("model content hash"),
        reaction["model_identity"]["semantic_hash"]
            .as_str()
            .expect("model semantic hash"),
        reaction["model_identity"]["provenance_hash"]
            .as_str()
            .expect("model provenance hash"),
        reaction["identity"]["request_hash"]
            .as_str()
            .expect("sparse request hash"),
        reaction["identity"]["model_hash"]
            .as_str()
            .expect("sparse model hash"),
        reaction["identity"]["state_hash"]
            .as_str()
            .expect("state hash"),
        reaction["identity"]["execution_hash"]
            .as_str()
            .expect("execution hash"),
        reaction["identity"]["checkpoint_hash"]
            .as_str()
            .expect("checkpoint hash"),
    ] {
        assert!(reaction_audit.contains(hash));
    }
    let (unsigned, hash_line) = reaction_audit
        .rsplit_once("Audit hash: ")
        .expect("reaction audit hash line");
    assert_eq!(hash_line.trim_end(), sha256_identity(unsigned.as_bytes()));

    let korean_reaction_audit_arguments = [
        text("reaction-audit"),
        text("--workspace"),
        restarted.as_os_str(),
        text("--locale"),
        text("ko-KR"),
    ];
    let korean_reaction_audit_first = run_workbench(&korean_reaction_audit_arguments);
    let korean_reaction_audit_second = run_workbench(&korean_reaction_audit_arguments);
    assert_success(&korean_reaction_audit_first);
    assert_eq!(
        korean_reaction_audit_first.stdout,
        korean_reaction_audit_second.stdout
    );
    assert!(!korean_reaction_audit_first.stdout.contains(&0x1b));
    let korean_reaction_audit =
        String::from_utf8(korean_reaction_audit_first.stdout).expect("Korean reaction audit UTF-8");
    assert!(korean_reaction_audit
        .starts_with("Structural ModelIR 선형 Workbench - 대수적 전역 평형 감사\n"));
    assert!(korean_reaction_audit.contains("로케일: ko-KR\n"));
    assert!(korean_reaction_audit.contains("종합 수치 상태: within_numeric_tolerance\n"));
    let (unsigned, hash_line) = korean_reaction_audit
        .rsplit_once("감사 해시: ")
        .expect("Korean reaction audit hash line");
    assert_eq!(hash_line.trim_end(), sha256_identity(unsigned.as_bytes()));

    assert_eq!(
        fs::read(restarted.join("workbench-session.json")).expect("session after reaction views"),
        session_before_result_surfaces,
        "displacement/element/deformed/reaction view or audit mutated the durable session"
    );

    let session_before_localized_export =
        fs::read(restarted.join("workbench-session.json")).expect("session before PDF export");
    let mut localized_hashes = Vec::new();
    for locale in ["en-US", "ko-KR"] {
        let first = root.join(format!("localized-linear-{locale}-first"));
        let second = root.join(format!("localized-linear-{locale}-second"));
        for output_directory in [&first, &second] {
            let output = run_workbench(&[
                text("report-export-pdf"),
                text("--workspace"),
                restarted.as_os_str(),
                text("--output-dir"),
                output_directory.as_os_str(),
                text("--locale"),
                text(locale),
            ]);
            assert_success(&output);
            let receipt = verify_self_hash(&output.stdout, "receipt_hash");
            assert_eq!(
                receipt["schema_version"],
                "structural-native-model-ir-linear-engineering-localized-pdf-report-receipt.v3"
            );
            assert_eq!(
                receipt["profile"],
                "model_ir_linear_cpu_engineering_summary_v1"
            );
            assert_eq!(receipt["locale"], locale);
            let report_directory = restarted.join("06-report");
            let result: Value = serde_json::from_slice(
                &fs::read(report_directory.join("result-ir.json")).expect("reported ResultIR"),
            )
            .expect("reported ResultIR JSON");
            let recovery: Value = serde_json::from_slice(
                &fs::read(report_directory.join("result-recovery-ir.json"))
                    .expect("reported recovery IR"),
            )
            .expect("reported recovery JSON");
            let reaction: Value = serde_json::from_slice(
                &fs::read(report_directory.join("reaction-result-ir.json"))
                    .expect("reported reaction IR"),
            )
            .expect("reported reaction JSON");
            let report: Value = serde_json::from_slice(
                &fs::read(report_directory.join("report-ir.json")).expect("reported ReportIR"),
            )
            .expect("reported ReportIR JSON");
            assert_eq!(receipt["source_result_hash"], result["result_hash"]);
            assert_eq!(receipt["source_recovery_hash"], recovery["recovery_hash"]);
            assert_eq!(receipt["source_reaction_hash"], reaction["result_hash"]);
            assert_eq!(receipt["source_report_hash"], report["report_hash"]);
            let localized_pdf =
                fs::read(output_directory.join("report.pdf")).expect("localized linear PDF");
            validate_deterministic_localized_pdf_v2(&localized_pdf)
                .expect("localized linear PDF structure");
        }
        for file in ["report.pdf", "pdf-receipt.json"] {
            assert_eq!(
                fs::read(first.join(file)).expect("first localized linear artifact"),
                fs::read(second.join(file)).expect("second localized linear artifact"),
                "localized linear export drift: {locale}/{file}"
            );
        }
        localized_hashes.push(sha256_identity(
            &fs::read(first.join("report.pdf")).expect("localized linear PDF"),
        ));
    }
    assert_ne!(localized_hashes[0], localized_hashes[1]);
    assert_eq!(
        fs::read(restarted.join("workbench-session.json")).expect("session after PDF export"),
        session_before_localized_export,
        "localized linear export mutated the durable session"
    );

    let unsupported = run_workbench(&[
        text("result-view"),
        text("--workspace"),
        restarted.as_os_str(),
    ]);
    assert!(!unsupported.status.success());
    assert!(String::from_utf8_lossy(&unsupported.stdout).contains("workbench_profile_unsupported"));

    for workspace in [&restarted, &direct] {
        assert_success(&run_workbench(&[
            text("review"),
            text("--workspace"),
            workspace.as_os_str(),
            text("--decision"),
            text("review"),
            text("--reviewer"),
            text("Engineer A"),
            text("--comment"),
            text("Verify bounded linear assumptions."),
        ]));
    }
    assert_eq!(
        fs::read(restarted.join("07-review/review.json")).expect("restarted review"),
        fs::read(direct.join("07-review/review.json")).expect("direct review")
    );
    let review = verify_self_hash(
        &fs::read(restarted.join("07-review/review.json")).expect("review"),
        "review_hash",
    );
    assert_eq!(
        review["reaction_result_artifact_hash"],
        sha256_identity(&reaction_bytes)
    );
    assert_eq!(
        review["claim_boundary"],
        "explicit_human_review_bound_to_verified_model_ir_linear_result_recovery_constrained_reaction_result_comparison_report_ir_document_source_and_pdf_not_an_automated_engineering_verdict_or_signature"
    );
    let exported = run_workbench(&stage_arguments("export", &restarted));
    assert_success(&exported);
    let exported = verify_self_hash(&exported.stdout, "export_hash");
    assert_eq!(exported["analysis_profile"], "model_ir_linear_cpu_v1");
    let roles = exported["artifacts"]
        .as_array()
        .expect("export artifacts")
        .iter()
        .map(|artifact| artifact["role"].as_str().expect("artifact role"))
        .collect::<Vec<_>>();
    assert!(roles.contains(&"result_recovery_ir"));
    assert!(roles.contains(&"reaction_result_ir"));
    assert!(roles.contains(&"sparse_linear_pdf_report"));
    assert!(roles.contains(&"pdf_ready_document_source"));
    assert!(!roles.contains(&"pdf_report"));

    let reaction_path = restarted.join("04-resume/reaction-result-ir.json");
    let recovery_path = restarted.join("04-resume/result-recovery-ir.json");
    let mut tampered_recovery = recovery_bytes.clone();
    tampered_recovery[32] ^= 1;
    fs::write(&recovery_path, tampered_recovery).expect("tamper recovery");
    for rejected in [
        run_workbench(&[
            text("nodal-displacement-view"),
            text("--workspace"),
            restarted.as_os_str(),
        ]),
        run_workbench(&[
            text("element-recovery-view"),
            text("--workspace"),
            restarted.as_os_str(),
        ]),
        run_workbench(&[
            text("result-deformed-view"),
            text("--workspace"),
            restarted.as_os_str(),
        ]),
    ] {
        assert!(!rejected.status.success());
        assert!(String::from_utf8_lossy(&rejected.stdout)
            .contains("workbench_artifact_inventory_mismatch"));
    }
    fs::write(&recovery_path, &recovery_bytes).expect("restore recovery");

    let mut tampered_reaction = reaction_bytes.clone();
    tampered_reaction[32] ^= 1;
    fs::write(&reaction_path, tampered_reaction).expect("tamper reactions");
    for rejected in [
        run_workbench(&stage_arguments("inspect", &restarted)),
        run_workbench(&[
            text("reaction-view"),
            text("--workspace"),
            restarted.as_os_str(),
        ]),
        run_workbench(&[
            text("reaction-audit"),
            text("--workspace"),
            restarted.as_os_str(),
        ]),
    ] {
        assert!(!rejected.status.success());
        assert!(String::from_utf8_lossy(&rejected.stdout)
            .contains("workbench_artifact_inventory_mismatch"));
    }
    fs::write(&reaction_path, &reaction_bytes).expect("restore reactions");

    let mut tampered_pdf = pdf;
    tampered_pdf[32] ^= 1;
    fs::write(restarted.join("06-report/report.pdf"), tampered_pdf).expect("tamper PDF");
    let rejected = run_workbench(&stage_arguments("inspect", &restarted));
    assert!(!rejected.status.success());
    assert!(
        String::from_utf8_lossy(&rejected.stdout).contains("workbench_artifact_inventory_mismatch")
    );

    fs::remove_dir_all(root).expect("cleanup");
}

#[test]
fn frozen_linear_workspace_without_reactions_retains_legacy_review_contract() {
    let root = temporary_root("legacy-review");
    fs::create_dir(&root).expect("temporary root");
    let inputs = prepare_inputs(&root);
    let workspace = root.join("legacy");

    assert_success(&run_workbench(&[
        text("workflow-model-linear"),
        inputs.model.as_os_str(),
        inputs.request.as_os_str(),
        text("--external-result"),
        inputs.external.as_os_str(),
        text("--source-artifact"),
        inputs.source.as_os_str(),
        text("--workspace"),
        workspace.as_os_str(),
        text("--step-budget"),
        text("1"),
    ]));

    fs::remove_file(workspace.join("04-resume/reaction-result-ir.json"))
        .expect("remove post-legacy terminal reaction");
    strip_reaction_from_frozen_receipt(
        &workspace.join("04-resume/run-receipt.json"),
        "bounded_typed_modelir_frame3d_truss3d_cpu_assembly_pcg_restart_and_active_dof_recovery_not_sequential_c2_hip_reactions_shell_nonlinear_or_engineering_acceptance",
    );
    fs::remove_file(workspace.join("06-report/reaction-result-ir.json"))
        .expect("remove post-legacy report reaction");
    strip_reaction_from_frozen_receipt(
        &workspace.join("06-report/report-receipt.json"),
        "verified_deterministic_sparse_report_ir_markdown_and_single_page_pdf_not_pdf_a_accessibility_engineering_acceptance_or_design_code_compliance",
    );

    let unavailable = run_workbench(&[
        text("reaction-view"),
        text("--workspace"),
        workspace.as_os_str(),
    ]);
    assert!(!unavailable.status.success());
    assert!(
        String::from_utf8_lossy(&unavailable.stdout).contains("workbench_reaction_view_missing")
    );
    let audit_unavailable = run_workbench(&[
        text("reaction-audit"),
        text("--workspace"),
        workspace.as_os_str(),
    ]);
    assert!(!audit_unavailable.status.success());
    assert!(String::from_utf8_lossy(&audit_unavailable.stdout)
        .contains("workbench_reaction_audit_missing"));

    let displacement_available = run_workbench(&[
        text("nodal-displacement-view"),
        text("--workspace"),
        workspace.as_os_str(),
    ]);
    assert_success(&displacement_available);
    assert!(
        String::from_utf8_lossy(&displacement_available.stdout).contains(
            "Schema: structural-native-workbench-model-ir-linear-nodal-displacement-view.v1"
        )
    );
    let deformed_available = run_workbench(&[
        text("result-deformed-view"),
        text("--workspace"),
        workspace.as_os_str(),
    ]);
    assert_success(&deformed_available);
    assert!(String::from_utf8_lossy(&deformed_available.stdout)
        .contains("Schema: structural-native-workbench-model-ir-linear-deformed-view.v1"));

    assert_success(&run_workbench(&stage_arguments("status", &workspace)));
    assert_success(&run_workbench(&[
        text("review"),
        text("--workspace"),
        workspace.as_os_str(),
        text("--decision"),
        text("review"),
        text("--reviewer"),
        text("Engineer A"),
        text("--comment"),
        text("Review frozen pre-reaction evidence."),
    ]));
    let review = verify_self_hash(
        &fs::read(workspace.join("07-review/review.json")).expect("legacy review"),
        "review_hash",
    );
    assert!(review["reaction_result_artifact_hash"].is_null());
    assert_eq!(
        review["claim_boundary"],
        "explicit_human_review_bound_to_verified_model_ir_linear_result_recovery_comparison_report_ir_document_source_and_pdf_not_an_automated_engineering_verdict_or_signature"
    );

    let export = run_workbench(&stage_arguments("export", &workspace));
    assert_success(&export);
    let export = verify_self_hash(&export.stdout, "export_hash");
    assert_eq!(
        export["claim_boundary"],
        "deterministic_model_ir_linear_legacy_native_handoff_manifest_without_constrained_reactions_with_pdf_and_document_source_not_an_archive_signature_or_engineering_acceptance"
    );
    assert!(!export["artifacts"]
        .as_array()
        .expect("export artifacts")
        .iter()
        .any(|artifact| artifact["role"] == "reaction_result_ir"));

    fs::remove_dir_all(root).expect("cleanup");
}

#[test]
#[allow(clippy::too_many_lines)]
fn clean_environment_mgt_linear_workflow_preserves_import_health_and_restart_identity() {
    let root = temporary_root("mgt-restart");
    fs::create_dir(&root).expect("temporary root");
    let inputs = prepare_mgt_inputs();
    let restarted = root.join("restarted");
    let direct = root.join("direct");

    assert_success(&run_workbench(&mgt_import_arguments(
        "import-mgt-model-linear",
        &inputs,
        &restarted,
        false,
    )));
    assert_success(&run_workbench(&stage_arguments("validate", &restarted)));
    let validated_session =
        fs::read(restarted.join("workbench-session.json")).expect("validated MGT linear session");
    assert_success(&run_workbench(&[
        text("run"),
        text("--workspace"),
        restarted.as_os_str(),
        text("--step-budget"),
        text("1"),
    ]));
    assert!(restarted.join("03-run/checkpoint.mlpcp").is_file());
    fs::write(restarted.join("workbench-session.json"), validated_session)
        .expect("simulate MGT linear process death before session persistence");
    assert_success(&run_workbench(&stage_arguments("resume", &restarted)));
    assert_success(&run_workbench(&[
        text("compare"),
        text("--workspace"),
        restarted.as_os_str(),
        text("--require-pass"),
    ]));
    assert_success(&run_workbench(&stage_arguments("report", &restarted)));

    assert_success(&run_workbench(&mgt_import_arguments(
        "workflow-mgt-model-linear",
        &inputs,
        &direct,
        true,
    )));
    let restarted_files = collect_files(&restarted);
    assert_eq!(restarted_files, collect_files(&direct));
    for relative in restarted_files {
        assert_eq!(
            fs::read(restarted.join(&relative)).expect("restarted MGT linear artifact"),
            fs::read(direct.join(&relative)).expect("direct MGT linear artifact"),
            "MGT linear restart drift: {}",
            relative.display()
        );
    }

    let session = verify_self_hash(
        &fs::read(restarted.join("workbench-session.json")).expect("MGT linear session"),
        "session_hash",
    );
    assert_eq!(session["stage"], "reported");
    assert_eq!(session["analysis_profile"], "model_ir_linear_cpu_v1");
    assert_eq!(session["terminal_status"], "completed");
    assert_eq!(session["comparison_passed"], true);
    assert_eq!(
        session["mgt_source_hash"],
        sha256_identity(&fs::read(&inputs.source_mgt).expect("original MGT source"))
    );
    let import_receipt = verify_self_hash(
        &fs::read(restarted.join("01-import/import-receipt.json")).expect("MGT import receipt"),
        "receipt_hash",
    );
    assert_eq!(import_receipt["analysis_profile"], "model_ir_linear_cpu_v1");
    assert_eq!(
        import_receipt["claim_boundary"],
        "bounded_original_mgt_import_health_normalized_modelir_cpp_snapshot_and_linear_input_ingestion_only_not_solver_execution_or_external_acceptance"
    );
    let health: Value = serde_json::from_slice(
        &fs::read(restarted.join("01-import/import-health.json")).expect("MGT import health"),
    )
    .expect("MGT import health JSON");
    assert_eq!(health["status"], "normalized");
    assert_eq!(
        fs::read(restarted.join("01-import/source.mgt")).expect("preserved MGT source"),
        fs::read(&inputs.source_mgt).expect("original MGT source")
    );
    assert_eq!(
        fs::read(restarted.join("01-import/model-ir.json")).expect("normalized ModelIR"),
        fs::read(restarted.join("01-import/mgt-native-snapshot.json")).expect("C++ snapshot")
    );
    let recovery: Value = serde_json::from_slice(
        &fs::read(restarted.join("04-resume/result-recovery-ir.json"))
            .expect("MGT linear recovery"),
    )
    .expect("MGT linear recovery JSON");
    assert_eq!(recovery["load_pattern_id"], "LP_PUSH");
    assert!(
        (recovery["global_displacement"][6]
            .as_f64()
            .expect("MGT floor UX")
            - 0.016)
            .abs()
            <= 1e-14
    );
    let reaction: Value = serde_json::from_slice(
        &fs::read(restarted.join("04-resume/reaction-result-ir.json"))
            .expect("MGT linear reactions"),
    )
    .expect("MGT linear reaction JSON");
    assert_eq!(reaction["load_pattern_id"], "LP_PUSH");
    assert_eq!(
        reaction["constrained_dof_indices"],
        json!([0, 1, 2, 3, 4, 5])
    );
    assert_eq!(reaction["backend_receipt"]["fallback_count"], 0);
    validate_deterministic_pdf_v1(
        &fs::read(restarted.join("06-report/report.pdf")).expect("MGT linear PDF"),
    )
    .expect("MGT linear deterministic PDF");

    let session_before_result_surfaces = fs::read(restarted.join("workbench-session.json"))
        .expect("session before MGT result surfaces");
    let displacement_arguments = [
        text("nodal-displacement-view"),
        text("--workspace"),
        restarted.as_os_str(),
    ];
    let displacement_first = run_workbench(&displacement_arguments);
    let displacement_second = run_workbench(&displacement_arguments);
    assert_success(&displacement_first);
    assert_eq!(displacement_first.stdout, displacement_second.stdout);
    assert!(!displacement_first.stdout.contains(&0x1b));
    let direct_displacement = run_workbench(&[
        text("nodal-displacement-view"),
        text("--workspace"),
        direct.as_os_str(),
    ]);
    assert_success(&direct_displacement);
    assert_eq!(displacement_first.stdout, direct_displacement.stdout);
    let displacement =
        String::from_utf8(displacement_first.stdout).expect("MGT displacement view UTF-8");
    assert!(displacement.contains(
        "Schema: structural-native-workbench-model-ir-linear-nodal-displacement-view.v1\n"
    ));
    assert!(displacement.contains("Load pattern: LP_PUSH\n"));
    assert!(displacement.contains("Displayed nodes: 1-2 of 2\n"));
    assert!(displacement.contains(&format!(
        "{:+.17e}",
        recovery["global_displacement"][6]
            .as_f64()
            .expect("MGT floor UX")
    )));
    let (unsigned, hash_line) = displacement
        .rsplit_once("View hash: ")
        .expect("MGT displacement view hash line");
    assert_eq!(hash_line.trim_end(), sha256_identity(unsigned.as_bytes()));

    let korean_displacement = run_workbench(&[
        text("nodal-displacement-view"),
        text("--workspace"),
        restarted.as_os_str(),
        text("--locale"),
        text("ko-KR"),
        text("--start-node"),
        text("2"),
        text("--count"),
        text("1"),
    ]);
    assert_success(&korean_displacement);
    let korean_displacement =
        String::from_utf8(korean_displacement.stdout).expect("Korean MGT displacement UTF-8");
    assert!(korean_displacement.contains("표시 노드: 2-2 / 2\n"));
    assert!(korean_displacement
        .lines()
        .any(|line| line.starts_with("000002\tN_2\t")));
    let (unsigned, hash_line) = korean_displacement
        .rsplit_once("보기 해시: ")
        .expect("Korean MGT displacement view hash line");
    assert_eq!(hash_line.trim_end(), sha256_identity(unsigned.as_bytes()));

    let element_arguments = [
        text("element-recovery-view"),
        text("--workspace"),
        restarted.as_os_str(),
    ];
    let element_first = run_workbench(&element_arguments);
    let element_second = run_workbench(&element_arguments);
    assert_success(&element_first);
    assert_eq!(element_first.stdout, element_second.stdout);
    assert!(!element_first.stdout.contains(&0x1b));
    let direct_element = run_workbench(&[
        text("element-recovery-view"),
        text("--workspace"),
        direct.as_os_str(),
    ]);
    assert_success(&direct_element);
    assert_eq!(element_first.stdout, direct_element.stdout);
    let element = String::from_utf8(element_first.stdout).expect("MGT element recovery UTF-8");
    assert!(element.contains(
        "Schema: structural-native-workbench-model-ir-linear-element-recovery-view.v1\n"
    ));
    assert!(element.contains("Load pattern: LP_PUSH\n"));
    assert!(element.contains("Displayed elements: 1-1 of 1\n"));
    assert!(element.contains("\tframe_3d\tN_1->N_2\telement_local\t"));
    assert!(element.contains(&format!(
        "i_FX_N={:+.17e}",
        recovery["recovery_values"][0]
            .as_f64()
            .expect("MGT frame recovery")
    )));
    let (unsigned, hash_line) = element
        .rsplit_once("View hash: ")
        .expect("MGT element recovery view hash line");
    assert_eq!(hash_line.trim_end(), sha256_identity(unsigned.as_bytes()));

    let deformed_arguments = [
        text("result-deformed-view"),
        text("--workspace"),
        restarted.as_os_str(),
        text("--projection"),
        text("xz"),
        text("--scale"),
        text("1000"),
    ];
    let deformed_first = run_workbench(&deformed_arguments);
    let deformed_second = run_workbench(&deformed_arguments);
    assert_success(&deformed_first);
    assert_eq!(deformed_first.stdout, deformed_second.stdout);
    assert!(!deformed_first.stdout.contains(&0x1b));
    let direct_deformed = run_workbench(&[
        text("result-deformed-view"),
        text("--workspace"),
        direct.as_os_str(),
        text("--projection"),
        text("xz"),
        text("--scale"),
        text("1000"),
    ]);
    assert_success(&direct_deformed);
    assert_eq!(deformed_first.stdout, direct_deformed.stdout);
    let deformed =
        String::from_utf8(deformed_first.stdout).expect("MGT linear deformed view UTF-8");
    assert!(
        deformed.contains("Schema: structural-native-workbench-model-ir-linear-deformed-view.v1\n")
    );
    assert!(deformed.contains("Load pattern: LP_PUSH\n"));
    assert!(deformed.contains("Projection: xz\n"));
    assert!(deformed.contains("Inventory: nodes=2 elements=1\n"));
    assert!(deformed.contains(&format!(
        "translation_m=[{:+.17e}",
        recovery["global_displacement"][6]
            .as_f64()
            .expect("MGT floor UX")
    )));
    let (unsigned, hash_line) = deformed
        .rsplit_once("View hash: ")
        .expect("MGT linear deformed view hash line");
    assert_eq!(hash_line.trim_end(), sha256_identity(unsigned.as_bytes()));

    let korean_deformed = run_workbench(&[
        text("result-deformed-view"),
        text("--workspace"),
        restarted.as_os_str(),
        text("--locale"),
        text("ko-KR"),
        text("--projection"),
        text("xz"),
        text("--scale"),
        text("1000"),
    ]);
    assert_success(&korean_deformed);
    let korean_deformed =
        String::from_utf8(korean_deformed.stdout).expect("Korean MGT deformed UTF-8");
    assert!(korean_deformed.starts_with("Structural ModelIR 선형 Workbench - 변형 형상\n"));
    assert!(korean_deformed.contains("로케일: ko-KR\n"));
    assert!(korean_deformed.contains("요소 (2절점 중심선):\n"));
    let (unsigned, hash_line) = korean_deformed
        .rsplit_once("보기 해시: ")
        .expect("Korean MGT deformed view hash line");
    assert_eq!(hash_line.trim_end(), sha256_identity(unsigned.as_bytes()));

    let audit_arguments = [
        text("reaction-audit"),
        text("--workspace"),
        restarted.as_os_str(),
    ];
    let audit_first = run_workbench(&audit_arguments);
    let audit_second = run_workbench(&audit_arguments);
    assert_success(&audit_first);
    assert_eq!(audit_first.stdout, audit_second.stdout);
    assert!(!audit_first.stdout.contains(&0x1b));
    let direct_audit = run_workbench(&[
        text("reaction-audit"),
        text("--workspace"),
        direct.as_os_str(),
    ]);
    assert_success(&direct_audit);
    assert_eq!(audit_first.stdout, direct_audit.stdout);
    let audit = String::from_utf8(audit_first.stdout).expect("MGT reaction audit UTF-8");
    assert!(audit.contains("Load pattern: LP_PUSH\n"));
    assert!(audit.contains(
        "Applied force resultant: X=+2.00000000000000000e5; Y=+0.00000000000000000e0; Z=+0.00000000000000000e0 N\n"
    ));
    assert!(audit.contains(
        "Support reaction force resultant: X=-2.00000000000000116e5; Y=+0.00000000000000000e0; Z=+0.00000000000000000e0 N\n"
    ));
    assert!(audit.contains(
        "Force closure residual: X=-1.16415321826934814e-10; Y=+0.00000000000000000e0; Z=+0.00000000000000000e0 N\n"
    ));
    assert!(audit.contains("Overall numeric status: within_numeric_tolerance\n"));
    let (unsigned, hash_line) = audit
        .rsplit_once("Audit hash: ")
        .expect("MGT reaction audit hash line");
    assert_eq!(hash_line.trim_end(), sha256_identity(unsigned.as_bytes()));

    let korean_audit = run_workbench(&[
        text("reaction-audit"),
        text("--workspace"),
        restarted.as_os_str(),
        text("--locale"),
        text("ko-KR"),
    ]);
    assert_success(&korean_audit);
    let korean_audit = String::from_utf8(korean_audit.stdout).expect("Korean MGT audit UTF-8");
    assert!(korean_audit.contains("종합 수치 상태: within_numeric_tolerance\n"));
    let (unsigned, hash_line) = korean_audit
        .rsplit_once("감사 해시: ")
        .expect("Korean MGT reaction audit hash line");
    assert_eq!(hash_line.trim_end(), sha256_identity(unsigned.as_bytes()));
    assert_eq!(
        fs::read(restarted.join("workbench-session.json")).expect("session after MGT audits"),
        session_before_result_surfaces,
        "MGT displacement/element/deformed/reaction surfaces mutated the durable session"
    );

    let mut tampered =
        fs::read(restarted.join("01-import/source.mgt")).expect("preserved MGT source");
    tampered[0] ^= 1;
    fs::write(restarted.join("01-import/source.mgt"), tampered).expect("tamper MGT source");
    let rejected = run_workbench(&stage_arguments("status", &restarted));
    assert!(!rejected.status.success());
    assert!(
        String::from_utf8_lossy(&rejected.stdout).contains("workbench_mgt_import_binding_mismatch")
    );
    for rejected_surface in [
        run_workbench(&[
            text("nodal-displacement-view"),
            text("--workspace"),
            restarted.as_os_str(),
        ]),
        run_workbench(&[
            text("element-recovery-view"),
            text("--workspace"),
            restarted.as_os_str(),
        ]),
        run_workbench(&[
            text("result-deformed-view"),
            text("--workspace"),
            restarted.as_os_str(),
        ]),
    ] {
        assert!(!rejected_surface.status.success());
        assert!(String::from_utf8_lossy(&rejected_surface.stdout)
            .contains("workbench_mgt_import_binding_mismatch"));
    }

    fs::remove_dir_all(root).expect("cleanup");
}

#[test]
fn linear_profile_rejects_wrong_external_mapping_before_workspace_publication() {
    let root = temporary_root("negative");
    fs::create_dir(&root).expect("temporary root");
    let inputs = prepare_inputs(&root);
    let mut external: Value =
        serde_json::from_slice(&fs::read(&inputs.external).expect("external bytes"))
            .expect("external JSON");
    external["observations"][0]["dof"] = json!("UY");
    fs::write(
        &inputs.external,
        serde_json::to_vec(&external).expect("tampered external JSON"),
    )
    .expect("tampered external");
    let workspace = root.join("rejected");
    let output = run_workbench(&import_arguments(&inputs, &workspace));
    assert!(!output.status.success());
    assert!(String::from_utf8_lossy(&output.stdout)
        .contains("model_ir_linear_external_dof_mapping_invalid"));
    assert!(!workspace.exists());
    fs::remove_dir_all(root).expect("cleanup");
}

#[test]
fn frame3d_rigid_offsets_survive_workbench_restart_and_result_surfaces() {
    let root = temporary_root("rigid-offset");
    fs::create_dir(&root).expect("temporary root");
    let inputs = prepare_offset_inputs(&root);
    let restarted = root.join("restarted");
    let direct = root.join("direct");

    assert_success(&run_workbench(&import_arguments(&inputs, &restarted)));
    assert_success(&run_workbench(&stage_arguments("validate", &restarted)));
    assert_success(&run_workbench(&[
        text("run"),
        text("--workspace"),
        restarted.as_os_str(),
        text("--step-budget"),
        text("1"),
    ]));
    assert_success(&run_workbench(&stage_arguments("resume", &restarted)));
    assert_success(&run_workbench(&[
        text("compare"),
        text("--workspace"),
        restarted.as_os_str(),
        text("--require-pass"),
    ]));
    assert_success(&run_workbench(&stage_arguments("report", &restarted)));

    assert_success(&run_workbench(&[
        text("workflow-model-linear"),
        inputs.model.as_os_str(),
        inputs.request.as_os_str(),
        text("--external-result"),
        inputs.external.as_os_str(),
        text("--source-artifact"),
        inputs.source.as_os_str(),
        text("--workspace"),
        direct.as_os_str(),
        text("--step-budget"),
        text("1"),
    ]));

    let restarted_files = collect_files(&restarted);
    assert_eq!(restarted_files, collect_files(&direct));
    for relative in restarted_files {
        assert_eq!(
            fs::read(restarted.join(&relative)).expect("restarted offset artifact"),
            fs::read(direct.join(&relative)).expect("direct offset artifact"),
            "rigid-offset restart drift: {}",
            relative.display()
        );
    }

    let imported_model: Value = serde_json::from_slice(
        &fs::read(restarted.join("01-import/model-ir.json")).expect("imported offset ModelIR"),
    )
    .expect("imported offset ModelIR JSON");
    assert_eq!(
        imported_model["elements"][0]["offsets"],
        json!({"i_global_m": [0.1, 0, 0], "j_global_m": [-0.1, 0, 0]})
    );
    let recovery = verify_self_hash(
        &fs::read(restarted.join("04-resume/result-recovery-ir.json"))
            .expect("offset recovery ResultIR"),
        "recovery_hash",
    );
    assert_eq!(recovery["recovery_element_types"], json!([1]));
    assert_eq!(recovery["recovery_offsets"], json!([0, 12]));
    let result = verify_self_hash(
        &fs::read(restarted.join("04-resume/result-ir.json")).expect("offset sparse ResultIR"),
        "result_hash",
    );
    assert_eq!(result["backend_receipt"]["fallback_count"], 0);

    let element = run_workbench(&[
        text("element-recovery-view"),
        text("--workspace"),
        restarted.as_os_str(),
    ]);
    assert_success(&element);
    let element = String::from_utf8(element.stdout).expect("offset element view UTF-8");
    assert!(element.contains("\tframe_3d\tN1->N2\telement_local\t"));
    assert!(element.contains("i_FX_N="));

    fs::remove_dir_all(root).expect("cleanup");
}

#[test]
fn frame3d_end_releases_survive_workbench_restart_and_result_surfaces() {
    let root = temporary_root("end-release");
    fs::create_dir(&root).expect("temporary root");
    let inputs = prepare_release_inputs(&root);
    let restarted = root.join("restarted");
    let direct = root.join("direct");

    assert_success(&run_workbench(&import_arguments(&inputs, &restarted)));
    assert_success(&run_workbench(&stage_arguments("validate", &restarted)));
    assert_success(&run_workbench(&[
        text("run"),
        text("--workspace"),
        restarted.as_os_str(),
        text("--step-budget"),
        text("1"),
    ]));
    assert_success(&run_workbench(&stage_arguments("resume", &restarted)));
    assert_success(&run_workbench(&[
        text("compare"),
        text("--workspace"),
        restarted.as_os_str(),
        text("--require-pass"),
    ]));
    assert_success(&run_workbench(&stage_arguments("report", &restarted)));

    assert_success(&run_workbench(&[
        text("workflow-model-linear"),
        inputs.model.as_os_str(),
        inputs.request.as_os_str(),
        text("--external-result"),
        inputs.external.as_os_str(),
        text("--source-artifact"),
        inputs.source.as_os_str(),
        text("--workspace"),
        direct.as_os_str(),
        text("--step-budget"),
        text("1"),
    ]));

    let restarted_files = collect_files(&restarted);
    assert_eq!(restarted_files, collect_files(&direct));
    for relative in restarted_files {
        assert_eq!(
            fs::read(restarted.join(&relative)).expect("restarted release artifact"),
            fs::read(direct.join(&relative)).expect("direct release artifact"),
            "end-release restart drift: {}",
            relative.display()
        );
    }

    let imported_model: Value = serde_json::from_slice(
        &fs::read(restarted.join("01-import/model-ir.json")).expect("imported release ModelIR"),
    )
    .expect("imported release ModelIR JSON");
    assert_eq!(
        imported_model["elements"][0]["releases"],
        json!({"i": ["RY"], "j": []})
    );
    let recovery = verify_self_hash(
        &fs::read(restarted.join("04-resume/result-recovery-ir.json"))
            .expect("release recovery ResultIR"),
        "recovery_hash",
    );
    assert_eq!(recovery["recovery_element_types"], json!([1]));
    assert_eq!(recovery["recovery_offsets"], json!([0, 12]));
    assert_eq!(
        recovery["recovery_values"][4]
            .as_f64()
            .expect("released i-MY recovery")
            .to_bits(),
        0.0_f64.to_bits()
    );
    let result = verify_self_hash(
        &fs::read(restarted.join("04-resume/result-ir.json")).expect("release sparse ResultIR"),
        "result_hash",
    );
    assert_eq!(result["backend_receipt"]["fallback_count"], 0);

    let element = run_workbench(&[
        text("element-recovery-view"),
        text("--workspace"),
        restarted.as_os_str(),
    ]);
    assert_success(&element);
    let element = String::from_utf8(element.stdout).expect("release element view UTF-8");
    assert!(element.contains("\tframe_3d\tN1->N2\telement_local\t"));
    assert!(
        element.contains("i_MY_N_m=+0.00000000000000000e0"),
        "{element}"
    );

    fs::remove_dir_all(root).expect("cleanup");
}

#[test]
#[allow(clippy::too_many_lines)]
fn frame3d_self_weight_survives_workbench_restart_and_result_surfaces() {
    let root = temporary_root("self-weight");
    fs::create_dir(&root).expect("temporary root");
    let inputs = prepare_self_weight_inputs(&root);
    let restarted = root.join("restarted");
    let direct = root.join("direct");

    assert_success(&run_workbench(&import_arguments(&inputs, &restarted)));
    assert_success(&run_workbench(&stage_arguments("validate", &restarted)));
    assert_success(&run_workbench(&[
        text("run"),
        text("--workspace"),
        restarted.as_os_str(),
        text("--step-budget"),
        text("1"),
    ]));
    assert_success(&run_workbench(&stage_arguments("resume", &restarted)));
    assert_success(&run_workbench(&[
        text("compare"),
        text("--workspace"),
        restarted.as_os_str(),
        text("--require-pass"),
    ]));
    assert_success(&run_workbench(&stage_arguments("report", &restarted)));

    assert_success(&run_workbench(&[
        text("workflow-model-linear"),
        inputs.model.as_os_str(),
        inputs.request.as_os_str(),
        text("--external-result"),
        inputs.external.as_os_str(),
        text("--source-artifact"),
        inputs.source.as_os_str(),
        text("--workspace"),
        direct.as_os_str(),
        text("--step-budget"),
        text("1"),
    ]));

    let restarted_files = collect_files(&restarted);
    assert_eq!(restarted_files, collect_files(&direct));
    for relative in restarted_files {
        assert_eq!(
            fs::read(restarted.join(&relative)).expect("restarted self-weight artifact"),
            fs::read(direct.join(&relative)).expect("direct self-weight artifact"),
            "self-weight restart drift: {}",
            relative.display()
        );
    }

    let imported_model: Value = serde_json::from_slice(
        &fs::read(restarted.join("01-import/model-ir.json")).expect("imported self-weight ModelIR"),
    )
    .expect("imported self-weight ModelIR JSON");
    assert_eq!(
        imported_model["load_patterns"][1]["self_weight"],
        json!([0, 0, -1])
    );
    assert_eq!(imported_model["load_patterns"][1]["nodal_loads"], json!([]));
    let recovery = verify_self_hash(
        &fs::read(restarted.join("04-resume/result-recovery-ir.json"))
            .expect("self-weight recovery ResultIR"),
        "recovery_hash",
    );
    let external = recovery["active_external_load"]
        .as_array()
        .expect("self-weight active external load");
    assert!((external[2].as_f64().expect("self-weight FZ") - -1_539.644_05).abs() <= 1.0e-10);
    assert!(
        (external[4].as_f64().expect("self-weight MY") - -513.214_683_333_333_3).abs() <= 1.0e-10
    );
    assert!(
        (recovery["global_displacement"][8]
            .as_f64()
            .expect("self-weight tip UZ")
            - -0.000_192_455_506_25)
            .abs()
            <= 1.0e-15
    );
    let reaction = verify_self_hash(
        &fs::read(restarted.join("04-resume/reaction-result-ir.json"))
            .expect("self-weight reaction ResultIR"),
        "result_hash",
    );
    assert!(
        (reaction["reactions"][2]
            .as_f64()
            .expect("self-weight support FZ")
            - 3_079.288_1)
            .abs()
            <= 1.0e-8
    );
    assert!(
        (reaction["reactions"][4]
            .as_f64()
            .expect("self-weight support MY")
            - -3_079.288_1)
            .abs()
            <= 1.0e-8
    );
    let result = verify_self_hash(
        &fs::read(restarted.join("04-resume/result-ir.json")).expect("self-weight sparse ResultIR"),
        "result_hash",
    );
    assert_eq!(result["backend_receipt"]["fallback_count"], 0);

    let element = run_workbench(&[
        text("element-recovery-view"),
        text("--workspace"),
        restarted.as_os_str(),
    ]);
    assert_success(&element);
    let element = String::from_utf8(element.stdout).expect("self-weight element view UTF-8");
    assert!(element.contains("\tframe_3d\tN1->N2\telement_local\t"));
    assert!(element.contains("i_MY_N_m="));

    fs::remove_dir_all(root).expect("cleanup");
}

#[test]
#[allow(clippy::too_many_lines)]
fn frame3d_member_distributed_load_survives_workbench_restart_and_result_surfaces() {
    let root = temporary_root("member-load");
    fs::create_dir(&root).expect("temporary root");
    let inputs = prepare_member_distributed_load_inputs(&root);
    let restarted = root.join("restarted");
    let direct = root.join("direct");

    let model_view = run_workbench(&[text("model-view"), inputs.model.as_os_str()]);
    assert_success(&model_view);
    let model_view = String::from_utf8(model_view.stdout).expect("member-load model view UTF-8");
    assert!(model_view
        .lines()
        .any(|line| line.contains("N1 ") && line.contains("flags=support,load")));
    assert!(model_view
        .lines()
        .any(|line| line.contains("N2 ") && line.contains("flags=load")));

    assert_success(&run_workbench(&import_arguments(&inputs, &restarted)));
    assert_success(&run_workbench(&stage_arguments("validate", &restarted)));
    assert_success(&run_workbench(&[
        text("run"),
        text("--workspace"),
        restarted.as_os_str(),
        text("--step-budget"),
        text("1"),
    ]));
    assert_success(&run_workbench(&stage_arguments("resume", &restarted)));
    assert_success(&run_workbench(&[
        text("compare"),
        text("--workspace"),
        restarted.as_os_str(),
        text("--require-pass"),
    ]));
    assert_success(&run_workbench(&stage_arguments("report", &restarted)));

    assert_success(&run_workbench(&[
        text("workflow-model-linear"),
        inputs.model.as_os_str(),
        inputs.request.as_os_str(),
        text("--external-result"),
        inputs.external.as_os_str(),
        text("--source-artifact"),
        inputs.source.as_os_str(),
        text("--workspace"),
        direct.as_os_str(),
        text("--step-budget"),
        text("1"),
    ]));

    let restarted_files = collect_files(&restarted);
    assert_eq!(restarted_files, collect_files(&direct));
    for relative in restarted_files {
        assert_eq!(
            fs::read(restarted.join(&relative)).expect("restarted member-load artifact"),
            fs::read(direct.join(&relative)).expect("direct member-load artifact"),
            "member-load restart drift: {}",
            relative.display()
        );
    }

    let imported_model: Value = serde_json::from_slice(
        &fs::read(restarted.join("01-import/model-ir.json")).expect("imported member-load ModelIR"),
    )
    .expect("imported member-load ModelIR JSON");
    assert_eq!(
        imported_model["load_patterns"][1]["member_distributed_loads"][0]["element_id"],
        "E1"
    );
    assert_eq!(
        imported_model["load_patterns"][1]["member_distributed_loads"][0]["components_si"]
            ["qy_n_per_m"],
        -1000
    );
    let recovery = verify_self_hash(
        &fs::read(restarted.join("04-resume/result-recovery-ir.json"))
            .expect("member-load recovery ResultIR"),
        "recovery_hash",
    );
    assert!(
        (recovery["active_external_load"][1]
            .as_f64()
            .expect("member-load active FY")
            - -1000.0)
            .abs()
            <= 1.0e-12
    );
    assert!(
        (recovery["active_external_load"][5]
            .as_f64()
            .expect("member-load active MZ")
            - (1000.0 / 3.0))
            .abs()
            <= 1.0e-12
    );
    assert!(
        (recovery["global_displacement"][7]
            .as_f64()
            .expect("member-load tip UY")
            - -0.000_2)
            .abs()
            <= 1.0e-15
    );
    let reaction = verify_self_hash(
        &fs::read(restarted.join("04-resume/reaction-result-ir.json"))
            .expect("member-load reaction ResultIR"),
        "result_hash",
    );
    assert!(
        (reaction["reactions"][1]
            .as_f64()
            .expect("member-load support FY")
            - 2000.0)
            .abs()
            <= 1.0e-7
    );
    assert!(
        (reaction["reactions"][5]
            .as_f64()
            .expect("member-load support MZ")
            - 2000.0)
            .abs()
            <= 1.0e-7
    );
    let result = verify_self_hash(
        &fs::read(restarted.join("04-resume/result-ir.json")).expect("member-load sparse ResultIR"),
        "result_hash",
    );
    assert_eq!(result["backend_receipt"]["fallback_count"], 0);

    let element = run_workbench(&[
        text("element-recovery-view"),
        text("--workspace"),
        restarted.as_os_str(),
    ]);
    assert_success(&element);
    let element = String::from_utf8(element.stdout).expect("member-load element view UTF-8");
    assert!(element.contains("\tframe_3d\tN1->N2\telement_local\t"));
    assert!(element.contains("i_FY_N="), "{element}");
    assert!(element.contains("i_MZ_N_m="), "{element}");

    fs::remove_dir_all(root).expect("cleanup");
}

#[test]
fn authored_frame3d_prescribed_support_runs_compares_reports_and_restarts_exactly() {
    let root = temporary_root("prescribed-support");
    fs::create_dir(&root).expect("temporary root");
    let inputs = prepare_prescribed_support_inputs(&root);
    let restarted = root.join("restarted");
    let direct = root.join("direct");

    assert_success(&run_workbench(&import_arguments(&inputs, &restarted)));
    assert_success(&run_workbench(&stage_arguments("validate", &restarted)));
    assert_success(&run_workbench(&[
        text("run"),
        text("--workspace"),
        restarted.as_os_str(),
        text("--step-budget"),
        text("1"),
    ]));
    assert_success(&run_workbench(&stage_arguments("resume", &restarted)));
    assert_success(&run_workbench(&[
        text("compare"),
        text("--workspace"),
        restarted.as_os_str(),
        text("--require-pass"),
    ]));
    assert_success(&run_workbench(&stage_arguments("report", &restarted)));

    assert_success(&run_workbench(&[
        text("workflow-model-linear"),
        inputs.model.as_os_str(),
        inputs.request.as_os_str(),
        text("--external-result"),
        inputs.external.as_os_str(),
        text("--source-artifact"),
        inputs.source.as_os_str(),
        text("--workspace"),
        direct.as_os_str(),
        text("--step-budget"),
        text("1"),
    ]));

    let restarted_files = collect_files(&restarted);
    assert_eq!(restarted_files, collect_files(&direct));
    for relative in restarted_files {
        assert_eq!(
            fs::read(restarted.join(&relative)).expect("restarted prescribed artifact"),
            fs::read(direct.join(&relative)).expect("direct prescribed artifact"),
            "prescribed-support restart drift: {}",
            relative.display()
        );
    }

    let imported_model: Value = serde_json::from_slice(
        &fs::read(restarted.join("01-import/model-ir.json")).expect("imported prescribed ModelIR"),
    )
    .expect("imported prescribed ModelIR JSON");
    assert_eq!(
        imported_model["constraints"][0]["prescribed_values_si"]["UX"],
        0.001
    );
    let recovery = verify_self_hash(
        &fs::read(restarted.join("04-resume/result-recovery-ir.json"))
            .expect("prescribed recovery ResultIR"),
        "recovery_hash",
    );
    assert_eq!(
        recovery["constrained_dof_indices"],
        json!([0, 1, 2, 3, 4, 5])
    );
    assert_eq!(
        recovery["prescribed_displacement_values"][0]
            .as_f64()
            .expect("prescribed support UX")
            .to_bits(),
        0.001_f64.to_bits()
    );
    assert!(
        (recovery["global_displacement"][6]
            .as_f64()
            .expect("prescribed tip UX")
            - 0.001_05)
            .abs()
            <= 1.0e-15
    );
    let reaction = verify_self_hash(
        &fs::read(restarted.join("04-resume/reaction-result-ir.json"))
            .expect("prescribed reaction ResultIR"),
        "result_hash",
    );
    assert!(
        (reaction["reactions"][0]
            .as_f64()
            .expect("prescribed support reaction UX")
            - -100_000.0)
            .abs()
            <= 1.0e-7
    );
    let result = verify_self_hash(
        &fs::read(restarted.join("04-resume/result-ir.json")).expect("prescribed sparse ResultIR"),
        "result_hash",
    );
    assert_eq!(result["backend_receipt"]["fallback_count"], 0);

    fs::remove_dir_all(root).expect("cleanup");
}
