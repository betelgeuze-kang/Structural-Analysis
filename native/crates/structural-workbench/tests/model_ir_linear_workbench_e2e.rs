use std::ffi::OsStr;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::time::{SystemTime, UNIX_EPOCH};

use serde_json::{json, Value};
use structural_cli::{execute_model_ir_linear_analysis, execute_native_mgt_import};
use structural_contracts::model_ir::canonicalize_model_ir_v2;
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
        "displacement/deformed/reaction view or audit mutated the durable session"
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
                "structural-native-sparse-linear-localized-pdf-report-receipt.v2"
            );
            assert_eq!(receipt["profile"], "sparse_linear_cpu_v1");
            assert_eq!(receipt["locale"], locale);
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
        "MGT displacement/deformed/reaction surfaces mutated the durable session"
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
