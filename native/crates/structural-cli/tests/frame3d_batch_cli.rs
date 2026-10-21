use std::ffi::OsString;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicU64, Ordering};

use serde_json::{json, Value};
use structural_contracts::result_ir::parse_linear_frame3d_result_ir_v1;

static NEXT_TEMP: AtomicU64 = AtomicU64::new(0);
const THREAD_ENVIRONMENT: [&str; 7] = [
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "OMP_MAX_ACTIVE_LEVELS",
];

struct TempDirectory(PathBuf);

impl TempDirectory {
    fn new() -> Self {
        loop {
            let sequence = NEXT_TEMP.fetch_add(1, Ordering::Relaxed);
            let path = std::env::temp_dir().join(format!(
                "structural-cli-frame3d-batch-{}-{sequence}",
                std::process::id()
            ));
            match std::fs::create_dir(&path) {
                Ok(()) => return Self(path),
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
                Err(error) => panic!("create temporary batch directory: {error}"),
            }
        }
    }

    fn write_bytes(&self, name: &str, bytes: &[u8]) -> PathBuf {
        let path = self.0.join(name);
        std::fs::write(&path, bytes).expect("temporary test input");
        path
    }

    fn write_json(&self, name: &str, value: &Value) -> PathBuf {
        self.write_bytes(
            name,
            &serde_json::to_vec(value).expect("fixture JSON bytes"),
        )
    }

    fn entries(&self) -> Vec<OsString> {
        let mut entries: Vec<_> = std::fs::read_dir(&self.0)
            .expect("temporary directory entries")
            .map(|entry| entry.expect("temporary entry").file_name())
            .collect();
        entries.sort();
        entries
    }
}

impl Drop for TempDirectory {
    fn drop(&mut self) {
        let _removed = std::fs::remove_dir_all(&self.0);
    }
}

fn command(temporary: &TempDirectory) -> Command {
    let mut command = Command::new(env!("CARGO_BIN_EXE_structural-cli"));
    command.current_dir(&temporary.0);
    for name in THREAD_ENVIRONMENT {
        command.env(name, "1");
    }
    command.env("OMP_NESTED", "FALSE");
    command
}

fn fixture_model() -> Value {
    let path = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let mut value: Value =
        serde_json::from_slice(&std::fs::read(path).expect("tracked synthetic Frame3D fixture"))
            .expect("fixture JSON");
    value["elements"][0]["formulation"] = json!("linear_timoshenko_frame3d");
    value["load_combinations"] = json!([{
        "id": "COMB_BATCH_CLI",
        "index": 0,
        "combination_type": "linear",
        "terms": [
            {"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 1.2},
            {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": -0.4}
        ],
        "source_id": null,
        "extensions": {}
    }]);
    value
}

fn pattern_case(model: &Value, case_id: &str, load_id: &str) -> Value {
    json!({
        "case_id": case_id,
        "model": model,
        "load_pattern_id": load_id,
        "result_id": format!("batch-cli-result.{case_id}"),
    })
}

fn manifest() -> Value {
    let model = fixture_model();
    let mut combination = pattern_case(&model, "case-a", "LC_AXIAL");
    combination
        .as_object_mut()
        .expect("case object")
        .remove("load_pattern_id");
    combination["load_combination_id"] = json!("COMB_BATCH_CLI");
    json!({
        "schema_version": "structural-native-frame3d-batch-request.v1",
        "batch_id": "synthetic-batch-cli",
        "resource_policy": {
            "profile": "bounded_frame3d_single_thread_workers.v1",
            "workers": 1,
            "cpu_budget": 1,
        },
        "requests": [
            pattern_case(&model, "case-z", "LC_WEAK"),
            combination,
            pattern_case(&model, "case-m", "LC_TORSION"),
        ],
    })
}

fn artifact(output: &Output) -> Value {
    assert!(
        output.stderr.is_empty(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    serde_json::from_slice(&output.stdout).expect("exactly one complete JSON artifact on stdout")
}

fn run_batch(temporary: &TempDirectory, path: &Path) -> Output {
    command(temporary)
        .args(["model", "analyze-frame3d-batch"])
        .arg(path)
        .output()
        .expect("batch CLI runs")
}

fn serial_result(temporary: &TempDirectory, case: &Value) -> Value {
    let path = temporary.write_json(
        &format!("{}.model.json", case["case_id"].as_str().expect("case ID")),
        &case["model"],
    );
    let mut command = command(temporary);
    command.args(["model", "analyze-frame3d"]).arg(path);
    if let Some(id) = case.get("load_pattern_id").and_then(Value::as_str) {
        command.args(["--load-pattern", id]);
    } else {
        command.args([
            "--load-combination",
            case["load_combination_id"]
                .as_str()
                .expect("combination ID"),
        ]);
    }
    command.args([
        "--result-id",
        case["result_id"].as_str().expect("result ID"),
    ]);
    let output = command.output().expect("existing serial CLI runs");
    assert_eq!(output.status.code(), Some(0));
    artifact(&output)
}

fn assert_matches_serial(temporary: &TempDirectory, case: &Value, outcome: &Value) {
    let nested = &outcome["result_ir"];
    parse_linear_frame3d_result_ir_v1(
        &serde_json::to_vec(nested).expect("nested ResultIR JSON bytes"),
    )
    .expect("nested ResultIR retains its strict hash and replay contract");
    assert_eq!(nested, &serial_result(temporary, case));
}

fn assert_admission_rejection(output: &Output) -> Value {
    assert_eq!(output.status.code(), Some(2));
    let value = artifact(output);
    assert_eq!(
        value["schema_version"],
        "structural-native-linear-frame3d-batch-failure.v1"
    );
    assert_eq!(value["success"], false);
    assert_eq!(value["completed"], false);
    assert_eq!(value["issues"][0]["code"], "batch_manifest_invalid");
    assert!(value.get("outcomes").is_none());
    assert!(value.get("summary").is_none());
    value
}

fn reject_bytes(temporary: &TempDirectory, bytes: &[u8]) -> Value {
    let path = temporary.write_bytes("manifest.json", bytes);
    let before = temporary.entries();
    let output = run_batch(temporary, &path);
    let value = assert_admission_rejection(&output);
    assert_eq!(std::fs::read(path).expect("unchanged manifest"), bytes);
    assert_eq!(temporary.entries(), before);
    value
}

fn reject_manifest(temporary: &TempDirectory, value: &Value) -> Value {
    reject_bytes(
        temporary,
        &serde_json::to_vec(value).expect("manifest JSON"),
    )
}

#[test]
fn mixed_pattern_and_combination_results_match_the_existing_serial_cli_in_input_order() {
    let temporary = TempDirectory::new();
    let workers = std::thread::available_parallelism()
        .map_or(1, std::num::NonZeroUsize::get)
        .min(2);
    let mut manifest = manifest();
    manifest["resource_policy"]["workers"] = json!(workers);
    manifest["resource_policy"]["cpu_budget"] = json!(workers);
    let bytes = serde_json::to_vec(&manifest).expect("manifest JSON");
    let path = temporary.write_bytes("manifest.json", &bytes);
    let before = temporary.entries();
    let output = run_batch(&temporary, &path);
    assert_eq!(output.status.code(), Some(0));
    let value = artifact(&output);
    assert_eq!(std::fs::read(path).expect("unchanged manifest"), bytes);
    assert_eq!(temporary.entries(), before);
    assert_eq!(
        value["schema_version"],
        "structural-native-linear-frame3d-batch-result.v1"
    );
    assert_eq!(value["batch_id"], manifest["batch_id"]);
    assert_eq!(value["completed"], true);
    assert_eq!(value["success"], true);
    assert_eq!(
        value["summary"],
        json!({
            "requested_cases": 3, "succeeded_cases": 3, "failed_cases": 0,
        })
    );
    assert_eq!(value["resource_policy"]["requested_workers"], workers);
    assert_eq!(value["resource_policy"]["workers_used"], workers);
    assert_eq!(value["resource_policy"]["native_threads_per_worker"], 1);
    assert_eq!(
        value["resource_policy"]["process_environment_modified"],
        false
    );
    let outcomes = value["outcomes"].as_array().expect("ordered outcomes");
    let requests = manifest["requests"].as_array().expect("requests");
    assert_eq!(outcomes.len(), requests.len());
    for (index, (case, outcome)) in requests.iter().zip(outcomes).enumerate() {
        assert_eq!(outcome["index"], index);
        assert_eq!(outcome["case_id"], case["case_id"]);
        assert_eq!(outcome["result_id"], case["result_id"]);
        assert_eq!(outcome["success"], true);
        assert_eq!(outcome["issues"], json!([]));
        assert_matches_serial(&temporary, case, outcome);
    }
}

#[test]
fn invalid_models_and_runtime_cases_keep_their_positions_and_later_successes() {
    let temporary = TempDirectory::new();
    let model = fixture_model();
    let mut manifest = manifest();
    let last = manifest["requests"][1].clone();
    manifest["requests"] = json!([
        pattern_case(&model, "ok-first", "LC_AXIAL"),
        pattern_case(
            &json!({"schema_version": "invalid"}),
            "bad-wire",
            "LC_AXIAL"
        ),
        pattern_case(&model, "bad-load", "LC_MISSING"),
        last,
    ]);
    let path = temporary.write_json("manifest.json", &manifest);
    let before = temporary.entries();
    let output = run_batch(&temporary, &path);
    assert_eq!(output.status.code(), Some(1));
    let value = artifact(&output);
    assert_eq!(temporary.entries(), before);
    assert_eq!(value["completed"], true);
    assert_eq!(value["success"], false);
    assert_eq!(
        value["summary"],
        json!({
            "requested_cases": 4, "succeeded_cases": 2, "failed_cases": 2,
        })
    );
    let outcomes = value["outcomes"].as_array().expect("all case outcomes");
    assert_eq!(outcomes.len(), 4);
    for (index, outcome) in outcomes.iter().enumerate() {
        assert_eq!(outcome["index"], index);
        assert_eq!(outcome["case_id"], manifest["requests"][index]["case_id"]);
    }
    for index in [0, 3] {
        assert_eq!(outcomes[index]["success"], true);
        assert_matches_serial(&temporary, &manifest["requests"][index], &outcomes[index]);
    }
    for index in [1, 2] {
        assert_eq!(outcomes[index]["success"], false);
        assert_eq!(outcomes[index]["result_ir"], Value::Null);
        assert_eq!(
            outcomes[index]["issues"]
                .as_array()
                .expect("case issues")
                .len(),
            1
        );
    }
    assert_eq!(outcomes[1]["issues"][0]["layer"], "model_wire_contract");
    assert_eq!(outcomes[2]["issues"][0]["layer"], "native_runtime");
    assert_eq!(outcomes[2]["issues"][0]["code"], "native_runtime_error");
    assert_eq!(outcomes[2]["issues"][0]["status_code"], 1000);
}

#[test]
fn duplicate_json_keys_at_the_root_and_inside_models_fail_manifest_admission() {
    let temporary = TempDirectory::new();
    let encoded = serde_json::to_string(&manifest()).expect("manifest JSON");
    let root_duplicate = encoded.replacen('{', "{\"batch_id\":\"shadow\",", 1);
    let model_duplicate = encoded.replacen(
        "\"model_id\":",
        "\"model_id\":\"shadow-model\",\"model_id\":",
        1,
    );
    for bytes in [root_duplicate, model_duplicate] {
        let value = reject_bytes(&temporary, bytes.as_bytes());
        assert!(value["issues"][0]["detail"]
            .as_str()
            .expect("error detail")
            .contains("duplicate"));
    }
}

#[test]
fn unknown_root_policy_and_case_fields_are_rejected() {
    let temporary = TempDirectory::new();
    for location in ["root", "policy", "case"] {
        let mut value = manifest();
        let target = match location {
            "root" => &mut value,
            "policy" => &mut value["resource_policy"],
            _ => &mut value["requests"][0],
        };
        target["allow_fallback"] = json!(true);
        reject_manifest(&temporary, &value);
    }
}

#[test]
fn duplicate_case_and_result_identifiers_reject_the_whole_manifest() {
    let temporary = TempDirectory::new();
    for field in ["case_id", "result_id"] {
        let mut value = manifest();
        value["requests"][1][field] = value["requests"][0][field].clone();
        reject_manifest(&temporary, &value);
    }
}

#[test]
fn each_case_requires_exactly_one_string_load_selection() {
    let temporary = TempDirectory::new();
    for invalid in ["missing", "both", "boolean"] {
        let mut value = manifest();
        let row = value["requests"][0].as_object_mut().expect("case object");
        match invalid {
            "missing" => {
                row.remove("load_pattern_id");
            }
            "both" => {
                row.insert("load_combination_id".to_owned(), json!("COMB_BATCH_CLI"));
            }
            _ => {
                row.insert("load_pattern_id".to_owned(), json!(true));
            }
        }
        reject_manifest(&temporary, &value);
    }
}

#[test]
fn zero_fractional_boolean_and_string_cpu_counts_are_rejected_without_coercion() {
    let temporary = TempDirectory::new();
    for field in ["workers", "cpu_budget"] {
        for count in [json!(0), json!(1.5), json!(true), json!("1")] {
            let mut value = manifest();
            value["resource_policy"][field] = count;
            reject_manifest(&temporary, &value);
        }
    }
}

#[test]
fn workers_above_the_explicit_budget_or_worker_limit_are_rejected() {
    let temporary = TempDirectory::new();
    for workers in [2, 13] {
        let mut value = manifest();
        value["resource_policy"]["workers"] = json!(workers);
        reject_manifest(&temporary, &value);
    }
}

#[test]
fn cpu_budget_above_observed_available_parallelism_is_rejected() {
    let temporary = TempDirectory::new();
    let available = std::thread::available_parallelism().map_or(1, std::num::NonZeroUsize::get);
    let mut value = manifest();
    value["resource_policy"]["cpu_budget"] = json!(available.checked_add(1).expect("CPU count"));
    reject_manifest(&temporary, &value);
}

#[test]
fn per_case_output_paths_are_rejected_without_creating_any_output_files() {
    let temporary = TempDirectory::new();
    let target = temporary.0.join("unexpected-result.json");
    let mut value = manifest();
    value["requests"][0]["output_path"] = json!(target.to_string_lossy());
    reject_manifest(&temporary, &value);
    assert!(!target.exists());
}

#[test]
fn invalid_thread_declarations_are_rejected_without_mutating_the_test_environment() {
    let temporary = TempDirectory::new();
    let path = temporary.write_json("manifest.json", &manifest());
    let parent_before: Vec<_> = THREAD_ENVIRONMENT
        .into_iter()
        .chain(["OMP_NESTED"])
        .map(|name| (name, std::env::var_os(name)))
        .collect();
    let before = temporary.entries();
    for name in THREAD_ENVIRONMENT.into_iter().chain(["OMP_NESTED"]) {
        let mut command = command(&temporary);
        command.env(name, if name == "OMP_NESTED" { "TRUE" } else { "2" });
        let output = command
            .args(["model", "analyze-frame3d-batch"])
            .arg(&path)
            .output()
            .expect("CLI with conflicting thread declaration");
        let value = assert_admission_rejection(&output);
        assert!(value["issues"][0]["detail"]
            .as_str()
            .expect("thread declaration detail")
            .contains(name));
    }
    for (name, value) in parent_before {
        assert_eq!(std::env::var_os(name), value, "parent environment: {name}");
    }
    assert_eq!(temporary.entries(), before);
}
