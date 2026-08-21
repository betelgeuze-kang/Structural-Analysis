use std::fmt;
use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::path::Path;
use std::sync::atomic::{AtomicU64, Ordering};

use serde_json::{json, Value};
use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_contracts::product_ir::{
    parse_native_analysis_request_v1, sha256_identity, ProductIrContractError,
};
use structural_report::build_nonlinear_ndtha_report_v1;
use structural_runtime::{
    NonlinearNdthaCheckpoint, NonlinearNdthaCheckpointReceipt, NonlinearNdthaExecutionStatus,
    Runtime, RuntimeError,
};

const INTERNAL_ERROR: u32 = 1900;
static OUTPUT_SEQUENCE: AtomicU64 = AtomicU64::new(0);

/// Stable error boundary for the bounded native product command.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum NativeAnalysisProductError {
    Contract(ProductIrContractError),
    Runtime(RuntimeError),
    Io { code: u32, message: String },
}

impl NativeAnalysisProductError {
    #[must_use]
    pub const fn is_contract_error(&self) -> bool {
        matches!(self, Self::Contract(_))
    }
}

impl fmt::Display for NativeAnalysisProductError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Contract(error) => write!(formatter, "{error}"),
            Self::Runtime(error) => write!(formatter, "{error}"),
            Self::Io { code, message } => write!(formatter, "product I/O error {code}: {message}"),
        }
    }
}

impl std::error::Error for NativeAnalysisProductError {}

impl From<ProductIrContractError> for NativeAnalysisProductError {
    fn from(error: ProductIrContractError) -> Self {
        Self::Contract(error)
    }
}

impl From<RuntimeError> for NativeAnalysisProductError {
    fn from(error: RuntimeError) -> Self {
        Self::Runtime(error)
    }
}

/// Complete artifact set from one bounded native analysis advancement.
#[derive(Clone, Debug)]
pub struct NativeAnalysisRunOutcomeV1 {
    checkpoint: NonlinearNdthaCheckpoint,
    checkpoint_receipt: NonlinearNdthaCheckpointReceipt,
    result_ir_json: Option<String>,
    report_ir_json: Option<String>,
    report_document: Option<String>,
    run_receipt_json: String,
}

impl NativeAnalysisRunOutcomeV1 {
    pub(crate) const fn checkpoint(&self) -> &NonlinearNdthaCheckpoint {
        &self.checkpoint
    }

    #[must_use]
    pub fn is_terminal(&self) -> bool {
        self.result_ir_json.is_some()
    }

    #[must_use]
    pub fn checkpoint_bytes(&self) -> &[u8] {
        self.checkpoint.as_bytes()
    }

    #[must_use]
    pub const fn checkpoint_receipt(&self) -> &NonlinearNdthaCheckpointReceipt {
        &self.checkpoint_receipt
    }

    #[must_use]
    pub fn result_ir_json(&self) -> Option<&str> {
        self.result_ir_json.as_deref()
    }

    #[must_use]
    pub fn report_ir_json(&self) -> Option<&str> {
        self.report_ir_json.as_deref()
    }

    #[must_use]
    pub fn report_document(&self) -> Option<&str> {
        self.report_document.as_deref()
    }

    #[must_use]
    pub fn run_receipt_json(&self) -> &str {
        &self.run_receipt_json
    }
}

/// Parse and advance one bounded request, optionally restoring exact checkpoint bytes first.
///
/// `step_budget` controls the maximum new inter-step boundaries. An active state returns only a
/// durable checkpoint; completion or physical collapse additionally returns `ResultIR`,
/// `ReportIR` and deterministic Markdown source.
///
/// # Errors
///
/// Returns a product contract error before FFI for invalid request bytes, or a runtime error for
/// checkpoint mismatch, native validation, nonconvergence or artifact construction failure.
pub fn execute_native_analysis(
    request_bytes: &[u8],
    checkpoint_bytes: Option<&[u8]>,
    step_budget: u32,
) -> Result<NativeAnalysisRunOutcomeV1, NativeAnalysisProductError> {
    let request = parse_native_analysis_request_v1(request_bytes)?;
    let runtime = Runtime::new()?;
    let value = request.request();
    let mut state = if let Some(bytes) = checkpoint_bytes {
        runtime.restore_nonlinear_ndtha(&value.config, &value.inputs, bytes)?
    } else {
        runtime.begin_nonlinear_ndtha(&value.config, &value.inputs)?
    };
    runtime.advance_nonlinear_ndtha(&value.config, &value.inputs, step_budget, &mut state)?;

    if state.status == NonlinearNdthaExecutionStatus::Active {
        let checkpoint =
            runtime.checkpoint_nonlinear_ndtha(&value.config, &value.inputs, &state)?;
        let checkpoint_receipt = checkpoint.receipt();
        let run_receipt_json = build_run_receipt(
            value.case_id.as_str(),
            request.request_hash(),
            "checkpointed",
            &checkpoint,
            &checkpoint_receipt,
            None,
            None,
            None,
        )?;
        return Ok(NativeAnalysisRunOutcomeV1 {
            checkpoint,
            checkpoint_receipt,
            result_ir_json: None,
            report_ir_json: None,
            report_document: None,
            run_receipt_json,
        });
    }

    let product = runtime.finish_nonlinear_ndtha_product(&request, &state)?;
    let checkpoint_receipt = product.checkpoint.receipt();
    let report = build_nonlinear_ndtha_report_v1(&product.result_ir)?;
    let result_ir_json = product.result_ir.canonical_json().to_owned();
    let report_ir_json = report.report_ir.canonical_json().to_owned();
    let report_document = report.document_source;
    let status = match state.status {
        NonlinearNdthaExecutionStatus::Completed => "completed",
        NonlinearNdthaExecutionStatus::Collapsed => "collapsed",
        NonlinearNdthaExecutionStatus::Active | NonlinearNdthaExecutionStatus::Nonconverged => {
            return Err(NativeAnalysisProductError::Runtime(RuntimeError {
                code: 1300,
                message: "native product terminal status changed during projection".to_owned(),
            }));
        }
    };
    let run_receipt_json = build_run_receipt(
        value.case_id.as_str(),
        request.request_hash(),
        status,
        &product.checkpoint,
        &checkpoint_receipt,
        Some(&result_ir_json),
        Some(&report_ir_json),
        Some(&report_document),
    )?;
    Ok(NativeAnalysisRunOutcomeV1 {
        checkpoint: product.checkpoint,
        checkpoint_receipt,
        result_ir_json: Some(result_ir_json),
        report_ir_json: Some(report_ir_json),
        report_document: Some(report_document),
        run_receipt_json,
    })
}

/// Atomically publish one complete product advancement into a new output directory.
///
/// # Errors
///
/// Returns a stable I/O error if the destination exists, its parent is invalid, or any
/// write/sync/rename operation fails. No existing destination is overwritten.
pub fn publish_native_analysis(
    output_directory: &Path,
    outcome: &NativeAnalysisRunOutcomeV1,
) -> Result<(), NativeAnalysisProductError> {
    let mut artifacts = vec![
        ("checkpoint.ndcp", outcome.checkpoint_bytes()),
        ("run-receipt.json", outcome.run_receipt_json().as_bytes()),
    ];
    if let (Some(result), Some(report), Some(document)) = (
        outcome.result_ir_json(),
        outcome.report_ir_json(),
        outcome.report_document(),
    ) {
        artifacts.push(("result-ir.json", result.as_bytes()));
        artifacts.push(("report-ir.json", report.as_bytes()));
        artifacts.push(("report.md", document.as_bytes()));
    }
    publish_artifact_directory(output_directory, &artifacts)
}

pub(crate) fn publish_artifact_directory(
    output_directory: &Path,
    artifacts: &[(&str, &[u8])],
) -> Result<(), NativeAnalysisProductError> {
    if output_directory.exists() {
        return Err(io_contract_error(
            "native analysis output directory already exists",
        ));
    }
    let parent = output_directory
        .parent()
        .filter(|path| !path.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."));
    let output_name = output_directory
        .file_name()
        .and_then(|name| name.to_str())
        .filter(|name| !name.is_empty())
        .ok_or_else(|| io_contract_error("native analysis output has no valid directory name"))?;
    if !parent.is_dir() {
        return Err(io_contract_error(
            "native analysis output parent does not exist",
        ));
    }
    let sequence = OUTPUT_SEQUENCE.fetch_add(1, Ordering::Relaxed);
    let temporary = parent.join(format!(
        ".{output_name}.tmp.{}.{}",
        std::process::id(),
        sequence
    ));
    fs::create_dir(&temporary)
        .map_err(|error| io_error("create native analysis temporary directory", &error))?;
    let publish_result = (|| -> Result<(), NativeAnalysisProductError> {
        for (name, bytes) in artifacts {
            if name.is_empty()
                || name.contains('/')
                || name.contains('\\')
                || *name == "."
                || *name == ".."
            {
                return Err(io_contract_error(
                    "native analysis artifact has an invalid flat file name",
                ));
            }
            write_synced_file(&temporary.join(name), bytes)?;
        }
        sync_directory(&temporary, "sync native analysis temporary directory")?;
        fs::rename(&temporary, output_directory)
            .map_err(|error| io_error("publish native analysis output directory", &error))?;
        sync_directory(parent, "sync native analysis output parent")?;
        Ok(())
    })();
    if publish_result.is_err() {
        let _ignored = fs::remove_dir_all(&temporary);
    }
    publish_result
}

#[allow(clippy::too_many_arguments)]
fn build_run_receipt(
    case_id: &str,
    request_hash: &str,
    status: &str,
    checkpoint: &NonlinearNdthaCheckpoint,
    checkpoint_receipt: &NonlinearNdthaCheckpointReceipt,
    result_ir: Option<&str>,
    report_ir: Option<&str>,
    report_document: Option<&str>,
) -> Result<String, NativeAnalysisProductError> {
    let mut artifacts = vec![artifact_entry(
        "checkpoint",
        "checkpoint.ndcp",
        "application/vnd.structural.ndtha-checkpoint",
        checkpoint.as_bytes(),
    )?];
    if let (Some(result), Some(report), Some(document)) = (result_ir, report_ir, report_document) {
        artifacts.push(artifact_entry(
            "result_ir",
            "result-ir.json",
            "application/json",
            result.as_bytes(),
        )?);
        artifacts.push(artifact_entry(
            "report_ir",
            "report-ir.json",
            "application/json",
            report.as_bytes(),
        )?);
        artifacts.push(artifact_entry(
            "report_document_source",
            "report.md",
            "text/markdown",
            document.as_bytes(),
        )?);
    }
    let mut receipt = json!({
        "schema_version": "structural-native-analysis-run-receipt.v1",
        "case_id": case_id,
        "status": status,
        "request_hash": request_hash,
        "checkpoint": checkpoint_receipt,
        "artifacts": artifacts,
        "claim_boundary": "bounded_cpu_nonlinear_ndtha_product_flow_not_broader_solver_hip_or_engineering_acceptance",
        "receipt_hash": ""
    });
    receipt
        .as_object_mut()
        .and_then(|object| object.remove("receipt_hash"))
        .ok_or_else(|| {
            NativeAnalysisProductError::Contract(ProductIrContractError {
                code: "run_receipt_invariant_failed".to_owned(),
                path: "/".to_owned(),
                detail: "run receipt is not an object".to_owned(),
            })
        })?;
    let unsigned = canonicalize_value(&receipt, "run_receipt_canonicalization_failed")?;
    receipt
        .as_object_mut()
        .expect("receipt object was checked above")
        .insert(
            "receipt_hash".to_owned(),
            Value::String(sha256_identity(unsigned.as_bytes())),
        );
    canonicalize_value(&receipt, "run_receipt_canonicalization_failed")
}

pub(crate) fn artifact_entry(
    role: &str,
    file: &str,
    media_type: &str,
    bytes: &[u8],
) -> Result<Value, NativeAnalysisProductError> {
    Ok(json!({
        "role": role,
        "file": file,
        "media_type": media_type,
        "byte_length": u64::try_from(bytes.len()).map_err(|_| io_contract_error("artifact length exceeds u64"))?,
        "content_hash": sha256_identity(bytes)
    }))
}

pub(crate) fn canonicalize_value(
    value: &Value,
    code: &str,
) -> Result<String, NativeAnalysisProductError> {
    canonicalize_model_ir_v2(value).map_err(|_| {
        NativeAnalysisProductError::Contract(ProductIrContractError {
            code: code.to_owned(),
            path: "/".to_owned(),
            detail: "run receipt could not be represented as canonical JSON".to_owned(),
        })
    })
}

fn write_synced_file(path: &Path, bytes: &[u8]) -> Result<(), NativeAnalysisProductError> {
    let mut file = OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(path)
        .map_err(|error| io_error("create native analysis artifact", &error))?;
    file.write_all(bytes)
        .map_err(|error| io_error("write native analysis artifact", &error))?;
    file.sync_all()
        .map_err(|error| io_error("sync native analysis artifact", &error))
}

fn sync_directory(path: &Path, action: &'static str) -> Result<(), NativeAnalysisProductError> {
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::fs::OpenOptionsExt;

        const GENERIC_WRITE: u32 = 0x4000_0000;
        const FILE_FLAG_BACKUP_SEMANTICS: u32 = 0x0200_0000;

        OpenOptions::new()
            .access_mode(GENERIC_WRITE)
            .custom_flags(FILE_FLAG_BACKUP_SEMANTICS)
            .open(path)
            .and_then(|directory| directory.sync_all())
            .map_err(|error| io_error(action, &error))
    }

    #[cfg(not(target_os = "windows"))]
    {
        File::open(path)
            .and_then(|directory| directory.sync_all())
            .map_err(|error| io_error(action, &error))
    }
}

fn io_contract_error(message: &str) -> NativeAnalysisProductError {
    NativeAnalysisProductError::Io {
        code: INTERNAL_ERROR,
        message: message.to_owned(),
    }
}

fn io_error(action: &str, error: &std::io::Error) -> NativeAnalysisProductError {
    io_contract_error(&format!("{action} failed: {error}"))
}
