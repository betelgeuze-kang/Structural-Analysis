use std::ffi::OsStr;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicU64, Ordering};

use serde_json::Value;
use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_contracts::product_ir::sha256_identity;
use structural_report::validate_deterministic_pdf_v1;

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
        "sha256:58601994beeabc8dfec557a0ae12ea483c0390685af9257179abfdaad0d990da"
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
