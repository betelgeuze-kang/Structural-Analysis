//! CLI composition boundary shared by the binary and future API adapter.

#![forbid(unsafe_code)]

use structural_runtime::Runtime;

/// Load the CPU-only native runtime and return its declared base capabilities.
/// # Errors
///
/// Returns a runtime-layer error when the native ABI cannot be loaded.
pub fn probe_native_runtime() -> Result<u64, structural_runtime::RuntimeError> {
    Runtime::new().map(|runtime| runtime.native_capabilities())
}

#[cfg(test)]
mod tests {
    use super::probe_native_runtime;

    #[test]
    fn cli_composition_reaches_the_native_api_table() {
        assert_eq!(probe_native_runtime(), Ok(1));
    }
}
