use std::ffi::OsStr;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::time::{SystemTime, UNIX_EPOCH};

use serde_json::{json, Value};
use structural_cli::execute_model_ir_linear_analysis;
use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_contracts::product_ir::sha256_identity;

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

struct Inputs {
    model: PathBuf,
    request: PathBuf,
    external: PathBuf,
    source: PathBuf,
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
    assert!(direct.is_complete());
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

fn stage_arguments<'a>(command: &'a str, workspace: &'a Path) -> [&'a OsStr; 3] {
    [text(command), text("--workspace"), workspace.as_os_str()]
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
        "04-resume/report-ir.json",
        "04-resume/report.md",
        "04-resume/run-receipt.json",
        "05-compare/external-comparison-ir.json",
        "05-compare/comparison-receipt.json",
        "06-report/result-ir.json",
        "06-report/result-recovery-ir.json",
        "06-report/report-ir.json",
        "06-report/report.md",
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
    assert!(!restarted.join("06-report/report.pdf").exists());

    let inspected = run_workbench(&stage_arguments("inspect", &restarted));
    assert_success(&inspected);
    let inspected = verify_self_hash(&inspected.stdout, "view_hash");
    assert_eq!(inspected["analysis_profile"], "model_ir_linear_cpu_v1");
    assert_eq!(
        inspected["report"]["source_recovery_hash"],
        report_receipt["source_recovery_hash"]
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
    assert!(report_text.contains("structural-native-workbench-model-ir-linear-report-view.v1"));
    assert!(report_text.contains("# Sparse Linear Analysis Report"));

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
    assert!(roles.contains(&"pdf_ready_document_source"));
    assert!(!roles.contains(&"pdf_report"));

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
