//! Durable runtime ownership boundary.
//!
//! Job persistence and checkpoint state intentionally arrive after the ABI foundation.

#![forbid(unsafe_code)]

use structural_contracts::model_ir::ModelIrV2Document;
use structural_ffi::{Api, Error};

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
            api: Api::load_model_ir().map_err(RuntimeError::from)?,
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
}

#[cfg(test)]
mod tests {
    use super::Runtime;

    #[test]
    fn runtime_uses_the_safe_ffi_owner() {
        let runtime = Runtime::new().expect("runtime loads native core");
        assert_eq!(runtime.native_capabilities(), 7);
    }
}
