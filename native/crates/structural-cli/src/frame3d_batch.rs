//! One read-only manifest in, one complete ordered artifact out; no per-case file publication.

use std::collections::{BTreeMap, BTreeSet};
use std::fs::File;
use std::io::{Read, Write};
use std::path::Path;
use std::process::ExitCode;

use serde_json::{json, Map, Value};
use structural_contracts::model_ir::{decode_json_strict, parse_model_ir_v2};
use structural_contracts::report_ir::sha256_bytes_identity;
use structural_runtime::{
    Frame3dBatchCpuBudget, LinearFrame3dBatchLoadSource, LinearFrame3dBatchRequest,
    MAX_FRAME3D_BATCH_REQUESTS, MAX_FRAME3D_BATCH_WORKERS,
};

const REQUEST_SCHEMA: &str = "structural-native-frame3d-batch-request.v1";
const RESOURCE_PROFILE: &str = "bounded_frame3d_single_thread_workers.v1";
const MAX_MANIFEST_BYTES: u64 = 64 * 1024 * 1024;
const THREAD_ENVIRONMENT: [&str; 7] = [
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "OMP_MAX_ACTIVE_LEVELS",
];

struct BatchManifest {
    batch_id: String,
    workers: usize,
    cpu_budget: Frame3dBatchCpuBudget,
    cases: Vec<ManifestCase>,
}

struct ManifestCase {
    case_id: String,
    result_id: String,
    load_source: LinearFrame3dBatchLoadSource,
    model: Value,
}

struct Failure {
    code: &'static str,
    detail: String,
    exit_code: u8,
}

fn invalid(detail: impl Into<String>) -> Failure {
    Failure {
        code: "batch_manifest_invalid",
        detail: detail.into(),
        exit_code: 2,
    }
}

fn object_with_keys<'a>(
    value: &'a Value,
    allowed: &[&str],
) -> Result<&'a Map<String, Value>, Failure> {
    let object = value
        .as_object()
        .ok_or_else(|| invalid("expected a JSON object"))?;
    if object.keys().any(|key| !allowed.contains(&key.as_str())) {
        return Err(invalid(
            "unknown manifest field; per-case output paths are not supported",
        ));
    }
    Ok(object)
}

fn text(object: &Map<String, Value>, key: &str) -> Result<String, Failure> {
    object
        .get(key)
        .and_then(Value::as_str)
        .map(str::to_owned)
        .ok_or_else(|| invalid(format!("{key} must be a string")))
}

fn identity(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || b"_.:-".contains(&byte))
}

fn positive_integer(object: &Map<String, Value>, key: &str) -> Result<usize, Failure> {
    let count = object
        .get(key)
        .and_then(Value::as_u64)
        .and_then(|value| usize::try_from(value).ok())
        .filter(|value| *value > 0)
        .ok_or_else(|| invalid(format!("{key} must be a positive JSON integer")))?;
    Ok(count)
}

fn parse_manifest(bytes: &[u8]) -> Result<BatchManifest, Failure> {
    let value = decode_json_strict(bytes)
        .map_err(|error| invalid(format!("{}: {}", error.code, error.detail)))?;
    let root = object_with_keys(
        &value,
        &["schema_version", "batch_id", "resource_policy", "requests"],
    )?;
    if text(root, "schema_version")? != REQUEST_SCHEMA {
        return Err(invalid("unsupported batch request schema"));
    }
    let batch_id = text(root, "batch_id")?;
    if !identity(&batch_id) {
        return Err(invalid("batch_id must be a bounded ASCII identifier"));
    }
    let policy = object_with_keys(
        root.get("resource_policy")
            .ok_or_else(|| invalid("resource_policy is required"))?,
        &["profile", "workers", "cpu_budget"],
    )?;
    if text(policy, "profile")? != RESOURCE_PROFILE {
        return Err(invalid("unsupported resource profile"));
    }
    let workers = positive_integer(policy, "workers")?;
    if workers > MAX_FRAME3D_BATCH_WORKERS {
        return Err(invalid("workers must be in 1..=12"));
    }
    let total_workers = positive_integer(policy, "cpu_budget")?;
    let cpu_budget = Frame3dBatchCpuBudget::for_current_process(total_workers)
        .map_err(|error| invalid(error.to_string()))?;
    if workers > cpu_budget.total_workers() {
        return Err(invalid("requested workers exceed the explicit CPU budget"));
    }
    let requests = root
        .get("requests")
        .and_then(Value::as_array)
        .filter(|requests| (1..=MAX_FRAME3D_BATCH_REQUESTS).contains(&requests.len()))
        .ok_or_else(|| invalid("requests must contain 1..=1024 cases"))?;
    let mut case_ids = BTreeSet::new();
    let mut result_ids = BTreeSet::new();
    let mut cases = Vec::with_capacity(requests.len());
    for request in requests {
        let row = object_with_keys(
            request,
            &[
                "case_id",
                "model",
                "load_pattern_id",
                "load_combination_id",
                "result_id",
            ],
        )?;
        let case_id = text(row, "case_id")?;
        let result_id = text(row, "result_id")?;
        if !identity(&case_id) || !case_ids.insert(case_id.clone()) {
            return Err(invalid("case_id must be a unique bounded ASCII identifier"));
        }
        if !result_ids.insert(result_id.clone()) {
            return Err(invalid("duplicate result_id is not allowed"));
        }
        let load_source = match (row.get("load_pattern_id"), row.get("load_combination_id")) {
            (Some(Value::String(id)), None) => LinearFrame3dBatchLoadSource::Pattern(id.clone()),
            (None, Some(Value::String(id))) => {
                LinearFrame3dBatchLoadSource::Combination(id.clone())
            }
            _ => {
                return Err(invalid(
                    "each case requires exactly one string load selection",
                ))
            }
        };
        cases.push(ManifestCase {
            case_id,
            result_id,
            load_source,
            model: row
                .get("model")
                .cloned()
                .ok_or_else(|| invalid("case model is required"))?,
        });
    }
    Ok(BatchManifest {
        batch_id,
        workers,
        cpu_budget,
        cases,
    })
}

fn external_thread_declarations() -> Result<BTreeMap<&'static str, Option<&'static str>>, Failure> {
    let mut observed = BTreeMap::new();
    for name in THREAD_ENVIRONMENT {
        let value = std::env::var_os(name);
        if value.as_deref().is_some_and(|value| value != "1") {
            return Err(invalid(format!(
                "{name} must be unset or exactly 1 for this resource profile"
            )));
        }
        observed.insert(name, value.map(|_| "1"));
    }
    // A true nested OpenMP declaration conflicts even if its default team count is one.
    let nested = std::env::var_os("OMP_NESTED");
    if nested
        .as_deref()
        .is_some_and(|value| value != "FALSE" && value != "false" && value != "0")
    {
        return Err(invalid("OMP_NESTED must be unset, FALSE, false or 0"));
    }
    observed.insert("OMP_NESTED", nested.map(|_| "false"));
    Ok(observed)
}

fn case_error(case: &ManifestCase, index: usize, issue: &Value) -> Value {
    json!({
        "index": index, "case_id": case.case_id, "result_id": case.result_id,
        "success": false, "result_ir": null, "issues": [issue],
    })
}

fn execute(bytes: &[u8]) -> Result<(Value, u8), Failure> {
    let manifest = parse_manifest(bytes)?;
    let thread_declarations = external_thread_declarations()?;
    let mut outcomes = vec![Value::Null; manifest.cases.len()];
    let mut valid_requests = Vec::with_capacity(manifest.cases.len());
    let mut valid_indices = Vec::with_capacity(manifest.cases.len());
    for (index, case) in manifest.cases.iter().enumerate() {
        let model_bytes = case.model.to_string().into_bytes();
        match parse_model_ir_v2(&model_bytes) {
            Ok(document) => {
                valid_requests.push(LinearFrame3dBatchRequest {
                    document,
                    load_source: case.load_source.clone(),
                    result_id: case.result_id.clone(),
                });
                valid_indices.push(index);
            }
            Err(error) => {
                outcomes[index] = case_error(
                    case,
                    index,
                    &json!({
                        "code": error.code, "path": error.path, "detail": error.detail,
                        "status_code": null, "layer": "model_wire_contract",
                    }),
                );
            }
        }
    }
    let workers_used = manifest.workers.min(valid_requests.len());
    if !valid_requests.is_empty() {
        let batch = manifest
            .cpu_budget
            .analyze(&valid_requests, manifest.workers)
            .map_err(|error| Failure {
                code: "batch_runtime_failed",
                detail: error.to_string(),
                exit_code: 1,
            })?;
        for (index, outcome) in valid_indices.into_iter().zip(batch.outcomes) {
            let case = &manifest.cases[index];
            outcomes[index] = match outcome {
                Ok(result) => {
                    let canonical = result.canonical_json().map_err(|error| Failure {
                        code: "batch_result_serialization_failed",
                        detail: error.to_string(),
                        exit_code: 1,
                    })?;
                    let value: Value =
                        serde_json::from_str(&canonical).map_err(|error| Failure {
                            code: "batch_result_serialization_failed",
                            detail: error.to_string(),
                            exit_code: 1,
                        })?;
                    json!({"index": index, "case_id": case.case_id, "result_id": case.result_id,
                           "success": true, "result_ir": value, "issues": []})
                }
                Err(error) => case_error(
                    case,
                    index,
                    &json!({
                        "code": "native_runtime_error", "path": "/analysis", "detail": error.message,
                        "status_code": error.code, "layer": "native_runtime",
                    }),
                ),
            };
        }
    }
    let succeeded = outcomes
        .iter()
        .filter(|outcome| outcome["success"] == true)
        .count();
    let failed = outcomes.len() - succeeded;
    let result = json!({
        "schema_version": "structural-native-linear-frame3d-batch-result.v1",
        "batch_id": manifest.batch_id, "manifest_sha256": sha256_bytes_identity(bytes),
        "completed": true, "success": failed == 0,
        "resource_policy": {
            "profile": RESOURCE_PROFILE,
            "cpu_budget": manifest.cpu_budget.total_workers(),
            "observed_available_parallelism": manifest.cpu_budget.observed_available_parallelism(),
            "requested_workers": manifest.workers, "workers_used": workers_used,
            "native_threads_per_worker": 1,
            "external_thread_declarations": thread_declarations,
            "external_thread_policy": "strict launch declarations; the current bounded Frame3D kernel itself calls no BLAS or OpenMP operations",
            "scope": "this invocation's workers; observed CPU admission, not cross-process quota or process isolation",
            "process_environment_modified": false,
        },
        "summary": {"requested_cases": outcomes.len(), "succeeded_cases": succeeded, "failed_cases": failed},
        "outcomes": outcomes,
        "claim_boundary": "independent bounded Frame3D cases retain their original ResultIR authority; batch completion grants no physical, design, commercial or release qualification",
    });
    Ok((result, u8::from(failed != 0)))
}

fn read_and_execute(path: &Path) -> Result<(Value, u8), Failure> {
    let file = File::open(path).map_err(|_| Failure {
        code: "batch_manifest_read_failed",
        detail: "batch manifest could not be opened".to_owned(),
        exit_code: 1,
    })?;
    let mut bytes = Vec::new();
    file.take(MAX_MANIFEST_BYTES + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| Failure {
            code: "batch_manifest_read_failed",
            detail: "batch manifest could not be read".to_owned(),
            exit_code: 1,
        })?;
    if u64::try_from(bytes.len()).unwrap_or(u64::MAX) > MAX_MANIFEST_BYTES {
        return Err(invalid("batch manifest exceeds 64 MiB"));
    }
    execute(&bytes)
}

pub fn run(path: &Path) -> ExitCode {
    let (artifact, exit_code) = match read_and_execute(path) {
        Ok(result) => result,
        Err(error) => (
            json!({
                "schema_version": "structural-native-linear-frame3d-batch-failure.v1",
                "success": false, "completed": false,
                "issues": [{"code": error.code, "detail": error.detail}],
                "claim_boundary": "batch failed without publishing a completed batch artifact",
            }),
            error.exit_code,
        ),
    };
    // Build the entire artifact before its only stdout write. No input/output files are mutated.
    let mut bytes = artifact.to_string().into_bytes();
    bytes.push(b'\n');
    if std::io::stdout().lock().write_all(&bytes).is_err() {
        return ExitCode::from(1);
    }
    ExitCode::from(exit_code)
}
