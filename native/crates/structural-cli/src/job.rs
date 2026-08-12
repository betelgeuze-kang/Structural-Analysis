use std::fmt;
use std::path::Path;

use serde_json::{json, Value};
use structural_contracts::product_ir::sha256_identity;
use structural_runtime::{
    unix_time_millis, DurableJobCompletionV1, DurableJobError, DurableJobStatusV1,
    DurableJobStoreV1, DurableJobViewV1,
};

use crate::product::{
    artifact_entry, canonicalize_value, execute_native_analysis, publish_artifact_directory,
    NativeAnalysisProductError,
};

/// Stable error boundary for public durable-job composition.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum DurableJobCommandError {
    Store(DurableJobError),
    Product(NativeAnalysisProductError),
    Invariant { code: String, detail: String },
}

impl DurableJobCommandError {
    #[must_use]
    pub const fn is_contract_error(&self) -> bool {
        match self {
            Self::Store(_) | Self::Invariant { .. } => true,
            Self::Product(error) => error.is_contract_error(),
        }
    }
}

impl fmt::Display for DurableJobCommandError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Store(error) => write!(formatter, "{error}"),
            Self::Product(error) => write!(formatter, "{error}"),
            Self::Invariant { code, detail } => write!(formatter, "{code}: {detail}"),
        }
    }
}

impl std::error::Error for DurableJobCommandError {}

impl From<DurableJobError> for DurableJobCommandError {
    fn from(error: DurableJobError) -> Self {
        Self::Store(error)
    }
}

impl From<NativeAnalysisProductError> for DurableJobCommandError {
    fn from(error: NativeAnalysisProductError) -> Self {
        Self::Product(error)
    }
}

/// Claim and advance at most one durable job using the bounded native product path.
///
/// Active execution publishes a checkpoint and releases its lease. Terminal execution publishes
/// the checkpoint, `ResultIR`, `ReportIR`, and deterministic document source as one event.
///
/// # Errors
///
/// Returns a stable error for store, lease, native execution, or artifact publication failure.
pub fn execute_next_durable_job(
    store: &DurableJobStoreV1,
    worker_id: &str,
    lease_millis: u64,
    step_budget: u32,
) -> Result<Option<DurableJobViewV1>, DurableJobCommandError> {
    if step_budget == 0 {
        return Err(invariant_error(
            "durable_job_step_budget_invalid",
            "durable job worker step budget must be greater than zero",
        ));
    }
    let claim_time = unix_time_millis()?;
    let Some(claim) = store.claim_next(worker_id, lease_millis, claim_time)? else {
        return Ok(None);
    };
    let outcome = match execute_native_analysis(
        &claim.request_bytes,
        claim.checkpoint_bytes.as_deref(),
        step_budget,
    ) {
        Ok(outcome) => outcome,
        Err(error) => {
            let failure_code = if error.is_contract_error() {
                "native_job_contract_failure"
            } else {
                "native_job_execution_failure"
            };
            let transition_time = unix_time_millis()?;
            store.fail_job(
                &claim.job.job_id,
                worker_id,
                &claim.lease_token,
                failure_code,
                false,
                transition_time,
            )?;
            return Err(error.into());
        }
    };
    let transition_time = unix_time_millis()?;
    if !outcome.is_terminal() {
        return store
            .publish_checkpoint(
                &claim.job.job_id,
                worker_id,
                &claim.lease_token,
                outcome.checkpoint_bytes(),
                transition_time,
            )
            .map(Some)
            .map_err(Into::into);
    }
    let completion = DurableJobCompletionV1 {
        checkpoint_bytes: outcome.checkpoint_bytes(),
        result_ir_bytes: required_artifact(outcome.result_ir_json(), "result_ir")?,
        report_ir_bytes: required_artifact(outcome.report_ir_json(), "report_ir")?,
        report_document_bytes: required_artifact(outcome.report_document(), "report_document")?,
    };
    match store.complete_job(
        &claim.job.job_id,
        worker_id,
        &claim.lease_token,
        completion,
        transition_time,
    ) {
        Ok(view) => Ok(Some(view)),
        Err(error) if error.code == "job_cancel_pending" => store
            .publish_checkpoint(
                &claim.job.job_id,
                worker_id,
                &claim.lease_token,
                outcome.checkpoint_bytes(),
                transition_time,
            )
            .map(Some)
            .map_err(Into::into),
        Err(error) => Err(error.into()),
    }
}

/// Export an immutable succeeded-job artifact set into a new directory.
///
/// # Errors
///
/// Returns a stable error unless the job succeeded and every stored artifact and receipt binding
/// validates before atomic publication.
pub fn export_durable_job(
    store: &DurableJobStoreV1,
    job_id: &str,
    output_directory: &Path,
) -> Result<String, DurableJobCommandError> {
    let view = store.poll(job_id)?;
    if view.status != DurableJobStatusV1::Succeeded {
        return Err(invariant_error(
            "durable_job_not_succeeded",
            "only a succeeded durable job can be exported",
        ));
    }
    let checkpoint = store.read_checkpoint(job_id)?;
    let result_ir = store.read_result_ir(job_id)?;
    let report_ir = store.read_report_ir(job_id)?;
    let report_document = store.read_report_document(job_id)?;
    let receipt =
        build_export_receipt(&view, &checkpoint, &result_ir, &report_ir, &report_document)?;
    publish_artifact_directory(
        output_directory,
        &[
            ("checkpoint.ndcp", &checkpoint),
            ("result-ir.json", &result_ir),
            ("report-ir.json", &report_ir),
            ("report.md", &report_document),
            ("job-receipt.json", receipt.as_bytes()),
        ],
    )?;
    Ok(receipt)
}

fn required_artifact<'a>(
    value: Option<&'a str>,
    role: &str,
) -> Result<&'a [u8], DurableJobCommandError> {
    value.map(str::as_bytes).ok_or_else(|| {
        invariant_error(
            "durable_job_terminal_artifact_missing",
            &format!("terminal native product did not expose {role}"),
        )
    })
}

fn build_export_receipt(
    view: &DurableJobViewV1,
    checkpoint: &[u8],
    result_ir: &[u8],
    report_ir: &[u8],
    report_document: &[u8],
) -> Result<String, DurableJobCommandError> {
    let mut receipt = json!({
        "schema_version": "structural-native-durable-job-export-receipt.v1",
        "job_id": view.job_id,
        "status": view.status,
        "revision": view.revision,
        "attempt": view.attempt,
        "request_hash": view.request.content_hash,
        "terminal_event_hash": view.terminal_event_hash,
        "artifacts": [
            artifact_entry("checkpoint", "checkpoint.ndcp", "application/vnd.structural.ndtha-checkpoint", checkpoint)?,
            artifact_entry("result_ir", "result-ir.json", "application/json", result_ir)?,
            artifact_entry("report_ir", "report-ir.json", "application/json", report_ir)?,
            artifact_entry("report_document_source", "report.md", "text/markdown", report_document)?,
        ],
        "claim_boundary": "single_host_bounded_cpu_nonlinear_ndtha_durable_job_export_not_distributed_service_hip_or_release_authority",
        "receipt_hash": ""
    });
    receipt
        .as_object_mut()
        .and_then(|object| object.remove("receipt_hash"))
        .ok_or_else(|| {
            invariant_error("durable_job_receipt_invalid", "receipt is not an object")
        })?;
    let unsigned = canonicalize_value(&receipt, "durable_job_receipt_canonicalization_failed")?;
    receipt
        .as_object_mut()
        .expect("receipt object checked above")
        .insert(
            "receipt_hash".to_owned(),
            Value::String(sha256_identity(unsigned.as_bytes())),
        );
    canonicalize_value(&receipt, "durable_job_receipt_canonicalization_failed").map_err(Into::into)
}

fn invariant_error(code: &str, detail: &str) -> DurableJobCommandError {
    DurableJobCommandError::Invariant {
        code: code.to_owned(),
        detail: detail.to_owned(),
    }
}
