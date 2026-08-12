//! Durable runtime ownership boundary.
//!
//! Job persistence and checkpoint state intentionally arrive after the ABI foundation.

#![forbid(unsafe_code)]

use structural_ffi::{Api, Error};

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
            api: Api::load().map_err(RuntimeError::from)?,
        })
    }

    #[must_use]
    pub const fn native_capabilities(&self) -> u64 {
        self.api.capabilities()
    }
}

#[cfg(test)]
mod tests {
    use super::Runtime;

    #[test]
    fn runtime_uses_the_safe_ffi_owner() {
        let runtime = Runtime::new().expect("runtime loads native core");
        assert_eq!(runtime.native_capabilities(), 1);
    }
}
