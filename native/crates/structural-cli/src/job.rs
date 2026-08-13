use std::fmt;
use std::path::Path;

use serde_json::{json, Value};
use structural_contracts::model_linear_job::parse_model_ir_linear_durable_job_request_v1;
use structural_contracts::product_ir::sha256_identity;
use structural_runtime::{
    unix_time_millis, DurableJobAnalysisProfileV1, DurableJobCompletionV1, DurableJobError,
    DurableJobStatusV1, DurableJobStoreV1, DurableJobViewV1, ModelIrLinearDurableJobCompletionV1,
};

use crate::model_linear_product::{execute_model_ir_linear_analysis, ModelIrLinearProductError};
use crate::product::{
    artifact_entry, canonicalize_value, execute_native_analysis, publish_artifact_directory,
    NativeAnalysisProductError,
};

/// Stable error boundary for public durable-job composition.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum DurableJobCommandError {
    Store(DurableJobError),
    Product(NativeAnalysisProductError),
    ModelLinearProduct(ModelIrLinearProductError),
    Invariant { code: String, detail: String },
}

impl DurableJobCommandError {
    #[must_use]
    pub const fn is_contract_error(&self) -> bool {
        match self {
            Self::Store(_) | Self::Invariant { .. } => true,
            Self::Product(error) => error.is_contract_error(),
            Self::ModelLinearProduct(error) => error.is_contract_error(),
        }
    }
}

impl fmt::Display for DurableJobCommandError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Store(error) => write!(formatter, "{error}"),
            Self::Product(error) => write!(formatter, "{error}"),
            Self::ModelLinearProduct(error) => write!(formatter, "{error}"),
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

impl From<ModelIrLinearProductError> for DurableJobCommandError {
    fn from(error: ModelIrLinearProductError) -> Self {
        Self::ModelLinearProduct(error)
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
    match claim.job.analysis_profile {
        DurableJobAnalysisProfileV1::NonlinearNdthaCpuV1 => {
            advance_ndtha_job(store, worker_id, step_budget, &claim)
        }
        DurableJobAnalysisProfileV1::ModelIrLinearCpuV1 => {
            advance_model_ir_linear_job(store, worker_id, step_budget, &claim)
        }
    }
    .map(Some)
}

fn advance_ndtha_job(
    store: &DurableJobStoreV1,
    worker_id: &str,
    step_budget: u32,
    claim: &structural_runtime::DurableJobClaimV1,
) -> Result<DurableJobViewV1, DurableJobCommandError> {
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
        Ok(view) => Ok(view),
        Err(error) if error.code == "job_cancel_pending" => store
            .publish_checkpoint(
                &claim.job.job_id,
                worker_id,
                &claim.lease_token,
                outcome.checkpoint_bytes(),
                transition_time,
            )
            .map_err(Into::into),
        Err(error) => Err(error.into()),
    }
}

fn advance_model_ir_linear_job(
    store: &DurableJobStoreV1,
    worker_id: &str,
    iteration_budget: u32,
    claim: &structural_runtime::DurableJobClaimV1,
) -> Result<DurableJobViewV1, DurableJobCommandError> {
    let request = match parse_model_ir_linear_durable_job_request_v1(&claim.request_bytes) {
        Ok(request) => request,
        Err(error) => {
            store.fail_job(
                &claim.job.job_id,
                worker_id,
                &claim.lease_token,
                "model_ir_linear_job_contract_failure",
                false,
                unix_time_millis()?,
            )?;
            return Err(invariant_error(
                "durable_model_ir_linear_request_invalid",
                &error.to_string(),
            ));
        }
    };
    let outcome = match execute_model_ir_linear_analysis(
        request.model_ir().canonical_bytes(),
        request.analysis_request().canonical_bytes(),
        claim.checkpoint_bytes.as_deref(),
        iteration_budget,
    ) {
        Ok(outcome) => outcome,
        Err(error) => {
            let failure_code = if error.is_contract_error() {
                "model_ir_linear_job_contract_failure"
            } else {
                "model_ir_linear_job_execution_failure"
            };
            store.fail_job(
                &claim.job.job_id,
                worker_id,
                &claim.lease_token,
                failure_code,
                false,
                unix_time_millis()?,
            )?;
            return Err(error.into());
        }
    };
    let transition_time = unix_time_millis()?;
    if outcome.is_terminal_failure() {
        return store
            .fail_model_ir_linear_job(
                &claim.job.job_id,
                worker_id,
                &claim.lease_token,
                outcome.checkpoint_bytes(),
                transition_time,
            )
            .map_err(Into::into);
    }
    if !outcome.is_complete() {
        return store
            .publish_model_ir_linear_checkpoint(
                &claim.job.job_id,
                worker_id,
                &claim.lease_token,
                outcome.checkpoint_bytes(),
                transition_time,
            )
            .map_err(Into::into);
    }
    let completion = ModelIrLinearDurableJobCompletionV1 {
        checkpoint_bytes: outcome.checkpoint_bytes(),
        result_ir_bytes: required_artifact(outcome.result_ir_json(), "result_ir")?,
        result_recovery_ir_bytes: required_artifact(
            outcome.result_recovery_ir_json(),
            "result_recovery_ir",
        )?,
        report_ir_bytes: required_artifact(outcome.report_ir_json(), "report_ir")?,
        report_document_bytes: required_artifact(outcome.report_document(), "report_document")?,
    };
    match store.complete_model_ir_linear_job(
        &claim.job.job_id,
        worker_id,
        &claim.lease_token,
        completion,
        transition_time,
    ) {
        Ok(view) => Ok(view),
        Err(error) if error.code == "job_cancel_pending" => store
            .publish_model_ir_linear_checkpoint(
                &claim.job.job_id,
                worker_id,
                &claim.lease_token,
                outcome.checkpoint_bytes(),
                transition_time,
            )
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
    let recovery = if view.analysis_profile == DurableJobAnalysisProfileV1::ModelIrLinearCpuV1 {
        Some(store.read_result_recovery_ir(job_id)?)
    } else {
        None
    };
    let receipt = build_export_receipt(
        &view,
        &checkpoint,
        &result_ir,
        recovery.as_deref(),
        &report_ir,
        &report_document,
    )?;
    let checkpoint_name =
        if view.analysis_profile == DurableJobAnalysisProfileV1::ModelIrLinearCpuV1 {
            "checkpoint.mlpcp"
        } else {
            "checkpoint.ndcp"
        };
    let mut artifacts = vec![
        (checkpoint_name, checkpoint.as_slice()),
        ("result-ir.json", result_ir.as_slice()),
        ("report-ir.json", report_ir.as_slice()),
        ("report.md", report_document.as_slice()),
        ("job-receipt.json", receipt.as_bytes()),
    ];
    if let Some(recovery) = recovery.as_deref() {
        artifacts.push(("result-recovery-ir.json", recovery));
    }
    publish_artifact_directory(output_directory, &artifacts)?;
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
    result_recovery_ir: Option<&[u8]>,
    report_ir: &[u8],
    report_document: &[u8],
) -> Result<String, DurableJobCommandError> {
    let mut receipt = match view.analysis_profile {
        DurableJobAnalysisProfileV1::NonlinearNdthaCpuV1 => json!({
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
        }),
        DurableJobAnalysisProfileV1::ModelIrLinearCpuV1 => {
            let recovery = result_recovery_ir.ok_or_else(|| {
                invariant_error(
                    "durable_job_terminal_artifact_missing",
                    "terminal ModelIR linear job did not expose result_recovery_ir",
                )
            })?;
            json!({
                "schema_version": "structural-native-durable-job-export-receipt.v1",
                "job_id": view.job_id,
                "analysis_profile": view.analysis_profile,
                "status": view.status,
                "revision": view.revision,
                "attempt": view.attempt,
                "request_hash": view.request.content_hash,
                "terminal_event_hash": view.terminal_event_hash,
                "artifacts": [
                    artifact_entry("checkpoint", "checkpoint.mlpcp", "application/vnd.structural.model-ir-linear-checkpoint", checkpoint)?,
                    artifact_entry("result_ir", "result-ir.json", "application/json", result_ir)?,
                    artifact_entry("report_ir", "report-ir.json", "application/json", report_ir)?,
                    artifact_entry("report_document_source", "report.md", "text/markdown", report_document)?,
                    artifact_entry("result_recovery_ir", "result-recovery-ir.json", "application/json", recovery)?,
                ],
                "claim_boundary": "single_host_bounded_cpu_model_ir_linear_durable_job_export_not_distributed_hip_or_release_authority",
                "receipt_hash": ""
            })
        }
    };
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
