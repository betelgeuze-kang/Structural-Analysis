//! Durable runtime ownership boundary.

#![forbid(unsafe_code)]

mod checkpoint;

use std::path::Path;

pub use checkpoint::{NonlinearNdthaCheckpoint, NonlinearNdthaCheckpointReceipt};
use structural_contracts::legacy_runtime::{NdthaStoryInputsV3, NonlinearNdthaConfigV3};
use structural_contracts::model_ir::ModelIrV2Document;
use structural_ffi::{Api, Error, NonlinearNdthaRestartState};

pub use structural_ffi::{ModelIrValidation, ModelIrValidationReport};

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
