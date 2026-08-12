//! Durable runtime ownership boundary.

#![forbid(unsafe_code)]

mod checkpoint;

use std::path::Path;

pub use checkpoint::{NonlinearNdthaCheckpoint, NonlinearNdthaCheckpointReceipt};
use structural_contracts::legacy_runtime::{
    NdthaResponseV3, NdthaStoryInputsV3, NonlinearNdthaConfigV3,
};
use structural_contracts::model_ir::ModelIrV2Document;
use structural_contracts::product_ir::{
    average_step_iterations, build_nonlinear_ndtha_result_ir_v1, NativeAnalysisRequestDocumentV1,
    NonlinearNdthaResultIrDocumentV1, NonlinearNdthaResultSummaryV1,
    NonlinearNdthaTerminalStatusV1, ProductIrContractError, ResultIdentityV1,
};
use structural_ffi::{Api, Error};

pub use structural_ffi::{
    ModelIrValidation, ModelIrValidationReport, NonlinearNdthaExecutionStatus,
    NonlinearNdthaRestartState,
};

/// Runtime-layer projection of an error returned by the native ABI.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RuntimeError {
    pub code: u32,
    pub message: String,
}

impl std::fmt::Display for RuntimeError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(formatter, "runtime error {}: {}", self.code, self.message)
    }
}

impl std::error::Error for RuntimeError {}

impl From<Error> for RuntimeError {
    fn from(error: Error) -> Self {
        Self {
            code: error.code,
            message: error.message,
        }
    }
}

impl From<ProductIrContractError> for RuntimeError {
    fn from(error: ProductIrContractError) -> Self {
        Self {
            code: 1100,
            message: format!("{} at {}: {}", error.code, error.path, error.detail),
        }
    }
}

/// Terminal checkpoint plus deterministic `ResultIR` bound to the same state.
#[derive(Clone, Debug)]
pub struct NonlinearNdthaProductResultV1 {
    pub checkpoint: NonlinearNdthaCheckpoint,
    pub result_ir: NonlinearNdthaResultIrDocumentV1,
}

/// CPU-only runtime foundation connected to the native ABI table.
pub struct Runtime {
    api: Api,
}

impl Runtime {
    /// Connect to the process-local native core.
    ///
    /// # Errors
    ///
    /// Returns a stable runtime error when the ABI table cannot be loaded.
    pub fn new() -> Result<Self, RuntimeError> {
        Ok(Self {
            api: Api::load_nonlinear_ndtha_restart().map_err(RuntimeError::from)?,
        })
    }

    #[must_use]
    pub const fn native_capabilities(&self) -> u64 {
        self.api.capabilities()
    }

    /// Validate and identity-check one `ModelIR` document through the native C++ owner.
    ///
    /// # Errors
    ///
    /// Returns a runtime error for descriptor, ABI, report, snapshot, or hash failures.
    pub fn validate_model_ir(
        &self,
        document: &ModelIrV2Document,
    ) -> Result<ModelIrValidation, RuntimeError> {
        self.api
            .validate_model_ir(document)
            .map_err(RuntimeError::from)
    }

    /// Create a validated zero state for a bounded nonlinear NDTHA execution.
    ///
    /// # Errors
    ///
    /// Returns a runtime error for invalid configuration/input lengths or allocation failure.
    pub fn begin_nonlinear_ndtha(
        &self,
        config: &NonlinearNdthaConfigV3,
        inputs: &NdthaStoryInputsV3,
    ) -> Result<NonlinearNdthaRestartState, RuntimeError> {
        self.api
            .initial_nonlinear_ndtha_state(config, inputs)
            .map_err(RuntimeError::from)
    }

    /// Advance an in-memory NDTHA state by at most `step_budget` deterministic boundaries.
    ///
    /// # Errors
    ///
    /// Returns a runtime error without mutating `state` on invalid input, checkpoint mismatch,
    /// allocation failure or numerical nonconvergence.
    pub fn advance_nonlinear_ndtha(
        &self,
        config: &NonlinearNdthaConfigV3,
        inputs: &NdthaStoryInputsV3,
        step_budget: u32,
        state: &mut NonlinearNdthaRestartState,
    ) -> Result<(), RuntimeError> {
        self.api
            .advance_nonlinear_ndtha(config, inputs, step_budget, state)
            .map_err(RuntimeError::from)
    }

    /// Validate and bind an execution state into canonical checkpoint bytes.
    ///
    /// # Errors
    ///
    /// Returns a runtime error if native state validation, hashing or allocation fails.
    pub fn checkpoint_nonlinear_ndtha(
        &self,
        config: &NonlinearNdthaConfigV3,
        inputs: &NdthaStoryInputsV3,
        state: &NonlinearNdthaRestartState,
    ) -> Result<NonlinearNdthaCheckpoint, RuntimeError> {
        let mut validated = state.clone();
        self.advance_nonlinear_ndtha(config, inputs, 0, &mut validated)?;
        NonlinearNdthaCheckpoint::create(config, inputs, validated)
    }

    /// Restore canonical checkpoint bytes after integrity, model and execution binding checks.
    ///
    /// # Errors
    ///
    /// Returns `SA_ERR_CHECKPOINT_MISMATCH` semantics for corruption, incompatible model/input,
    /// impossible state or trailing data.
    pub fn restore_nonlinear_ndtha(
        &self,
        config: &NonlinearNdthaConfigV3,
        inputs: &NdthaStoryInputsV3,
        bytes: &[u8],
    ) -> Result<NonlinearNdthaRestartState, RuntimeError> {
        let checkpoint = NonlinearNdthaCheckpoint::from_bytes(bytes)?;
        checkpoint.verify_bindings(config, inputs)?;
        let mut state = checkpoint.state().clone();
        self.advance_nonlinear_ndtha(config, inputs, 0, &mut state)?;
        Ok(state)
    }

    /// Restore a checkpoint and advance it in one failure-atomic runtime operation.
    ///
    /// # Errors
    ///
    /// Returns a runtime error for any decode, binding, native validation or solve failure.
    pub fn resume_nonlinear_ndtha(
        &self,
        config: &NonlinearNdthaConfigV3,
        inputs: &NdthaStoryInputsV3,
        bytes: &[u8],
        step_budget: u32,
    ) -> Result<NonlinearNdthaRestartState, RuntimeError> {
        let mut state = self.restore_nonlinear_ndtha(config, inputs, bytes)?;
        self.advance_nonlinear_ndtha(config, inputs, step_budget, &mut state)?;
        Ok(state)
    }

    /// Atomically persist one validated checkpoint in its destination directory.
    ///
    /// The write sequence is create-new temporary file, write, file sync, rename and directory
    /// sync. Temporary files are removed on pre-publication failure.
    ///
    /// # Errors
    ///
    /// Returns a runtime error for validation, allocation or filesystem durability failure.
    pub fn save_nonlinear_ndtha_checkpoint(
        &self,
        path: &Path,
        config: &NonlinearNdthaConfigV3,
        inputs: &NdthaStoryInputsV3,
        state: &NonlinearNdthaRestartState,
    ) -> Result<NonlinearNdthaCheckpointReceipt, RuntimeError> {
        let checkpoint = self.checkpoint_nonlinear_ndtha(config, inputs, state)?;
        checkpoint::write_atomic(path, &checkpoint)?;
        Ok(checkpoint.receipt())
    }

    /// Read, verify and bind one durable checkpoint without advancing it.
    ///
    /// # Errors
    ///
    /// Returns a runtime error for I/O, integrity, binding or native state validation failure.
    pub fn load_nonlinear_ndtha_checkpoint(
        &self,
        path: &Path,
        config: &NonlinearNdthaConfigV3,
        inputs: &NdthaStoryInputsV3,
    ) -> Result<NonlinearNdthaRestartState, RuntimeError> {
        let checkpoint = checkpoint::read_file(path)?;
        checkpoint.verify_bindings(config, inputs)?;
        let mut state = checkpoint.state().clone();
        self.advance_nonlinear_ndtha(config, inputs, 0, &mut state)?;
        Ok(state)
    }

    /// Bind one terminal native NDTHA state to its checkpoint identities and `ResultIR`.
    ///
    /// Physical response channels are copied from the state already produced and validated by
    /// C++; Rust owns only deterministic lifecycle, identity and wire projection.
    ///
    /// # Errors
    ///
    /// Returns a runtime error for a non-terminal or impossible state, checkpoint failure, or
    /// `ResultIR` invariant/canonicalization failure.
    pub fn finish_nonlinear_ndtha_product(
        &self,
        request: &NativeAnalysisRequestDocumentV1,
        state: &NonlinearNdthaRestartState,
    ) -> Result<NonlinearNdthaProductResultV1, RuntimeError> {
        let request_value = request.request();
        let mut validated = state.clone();
        self.advance_nonlinear_ndtha(
            &request_value.config,
            &request_value.inputs,
            0,
            &mut validated,
        )?;
        let terminal_status = match validated.status {
            NonlinearNdthaExecutionStatus::Completed => NonlinearNdthaTerminalStatusV1::Completed,
            NonlinearNdthaExecutionStatus::Collapsed => NonlinearNdthaTerminalStatusV1::Collapsed,
            NonlinearNdthaExecutionStatus::Active | NonlinearNdthaExecutionStatus::Nonconverged => {
                return Err(RuntimeError {
                    code: 1300,
                    message:
                        "nonlinear NDTHA product projection requires a terminal successful state"
                            .to_owned(),
                });
            }
        };
        let checkpoint = self.checkpoint_nonlinear_ndtha(
            &request_value.config,
            &request_value.inputs,
            &validated,
        )?;
        let receipt = checkpoint.receipt();
        let completed = usize::try_from(validated.next_step).map_err(|_| RuntimeError {
            code: 1900,
            message: "completed step count exceeds address space".to_owned(),
        })?;
        let last = completed.checked_sub(1).ok_or_else(|| RuntimeError {
            code: 1301,
            message: "terminal NDTHA state has no completed response step".to_owned(),
        })?;
        let residual_top_displacement_m = validated.response.top_displacement_m[last];
        let residual_drift_ratio_pct = validated
            .response
            .final_story_drift_pct
            .iter()
            .map(|value| value.abs())
            .fold(0.0_f64, f64::max);
        let summary = NonlinearNdthaResultSummaryV1 {
            terminal_status,
            step_count_completed: validated.next_step,
            max_plastic_story_count: validated.max_plastic_story_count,
            max_drift_ratio_pct: validated.max_drift_ratio_pct,
            adaptive_iteration_sum: validated.adaptive_iteration_sum,
            avg_step_iterations: average_step_iterations(
                validated.adaptive_iteration_sum,
                validated.next_step,
            )?,
            total_line_search_backtracks: validated.total_line_search_backtracks,
            collapse_step: validated.collapse_step,
            collapse_time_s: validated.collapse_time_s,
            collapse_drift_ratio_pct: validated.collapse_drift_ratio_pct,
            collapse_top_displacement_m: validated.collapse_top_displacement_m,
            residual_top_displacement_m,
            residual_drift_ratio_pct,
        };
        let response = NdthaResponseV3 {
            top_displacement_m: validated.response.top_displacement_m,
            drift_ratio_pct: validated.response.drift_ratio_pct,
            base_shear_kn: validated.response.base_shear_kn,
            core_drift_pct: validated.response.core_drift_pct,
            core_shear_kn: validated.response.core_shear_kn,
            step_converged: validated.response.step_converged,
            step_iterations: validated.response.step_iterations,
            step_plastic_story_count: validated.response.step_plastic_story_count,
            step_residual_inf: validated.response.step_residual_inf,
            story_drift_envelope_pct: validated.response.story_drift_envelope_pct,
            final_story_drift_pct: validated.response.final_story_drift_pct,
        };
        let result_ir = build_nonlinear_ndtha_result_ir_v1(
            request,
            ResultIdentityV1 {
                request_hash: request.request_hash().to_owned(),
                model_hash: receipt.model_hash,
                state_hash: receipt.state_hash,
                execution_hash: receipt.execution_hash,
                checkpoint_hash: receipt.checkpoint_hash,
            },
            summary,
            response,
        )?;
        Ok(NonlinearNdthaProductResultV1 {
            checkpoint,
            result_ir,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::Runtime;

    #[test]
    fn runtime_uses_the_safe_ffi_owner() {
        let runtime = Runtime::new().expect("runtime loads native core");
        assert_eq!(runtime.native_capabilities(), 127);
    }
}
