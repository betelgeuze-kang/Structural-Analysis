//! Durable runtime ownership boundary.
//!
//! Job persistence and checkpoint state intentionally arrive after the ABI foundation.

#![forbid(unsafe_code)]

mod frame3d;
mod native_job_store;

use structural_contracts::model_ir::ModelIrV2Document;
use structural_ffi::{Api, Error, LinearFrame3dInput, LinearFrame3dLoadCase as FfiLoadCase};

pub use frame3d::{
    LinearFrame3dAnalysisResult, LinearFrame3dGateMetrics, LinearFrame3dLoadSelection,
    LinearFrame3dMemberResult, LinearFrame3dNodeResult,
};
pub use native_job_store::{
    NativeFrame3dJobStore, NativeFrame3dJobStoreError, NativeFrame3dJobViewRecord,
};
pub use structural_contracts::native_job::{
    NativeFrame3dJobCancellationV2, NativeFrame3dJobLoadSourceV1, NativeFrame3dJobStatusV1,
    NativeFrame3dJobStatusV2, NativeFrame3dJobViewV1, NativeFrame3dJobViewV2,
};
pub use structural_contracts::result_ir::LinearFrame3dResultIrV1;
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
            api: Api::load_frame3d_offsets().map_err(RuntimeError::from)?,
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

    /// Validate, adapt, compile and solve one bounded linear Timoshenko `Frame3D` load pattern.
    ///
    /// # Errors
    ///
    /// Returns a stable error when semantic readiness, the exact Frame Alpha profile, unit/axis
    /// assumptions, topology, supports, selected loads, native compilation, or solve fails.
    pub fn analyze_linear_frame3d(
        &self,
        document: &ModelIrV2Document,
        load_pattern_id: &str,
    ) -> Result<LinearFrame3dAnalysisResult, RuntimeError> {
        self.analyze_linear_frame3d_load_case(
            document,
            LinearFrame3dLoadSelection::Pattern(load_pattern_id),
        )
    }

    /// Solve one explicitly selected linear load combination.
    ///
    /// # Errors
    ///
    /// Returns the same checked runtime failures as [`Self::analyze_linear_frame3d_load_case`].
    pub fn analyze_linear_frame3d_combination(
        &self,
        document: &ModelIrV2Document,
        load_combination_id: &str,
    ) -> Result<LinearFrame3dAnalysisResult, RuntimeError> {
        self.analyze_linear_frame3d_load_case(
            document,
            LinearFrame3dLoadSelection::Combination(load_combination_id),
        )
    }

    /// Validate, adapt, compile and solve one bounded linear Timoshenko `Frame3D` load source.
    ///
    /// # Errors
    ///
    /// Returns a stable error for an invalid pattern or combination selection, unsupported nested
    /// combination scope, non-finite superposition, native compilation, or solve failure.
    pub fn analyze_linear_frame3d_load_case(
        &self,
        document: &ModelIrV2Document,
        load_selection: LinearFrame3dLoadSelection<'_>,
    ) -> Result<LinearFrame3dAnalysisResult, RuntimeError> {
        let validation = self.validate_model_ir(document)?;
        if !validation.report.contract_valid {
            return Err(frame3d::semantic_invalid());
        }
        if !validation.report.analysis_ready {
            return Err(frame3d::analysis_not_ready());
        }
        let prepared = frame3d::prepare(document, load_selection)?;
        let model = self
            .api
            .compile_linear_frame3d(&LinearFrame3dInput {
                nodes: &prepared.nodes,
                sections: &prepared.sections,
                members: &prepared.members,
                restrained_dofs: &prepared.restrained_dofs,
                member_offsets: &prepared.member_offsets,
            })
            .map_err(RuntimeError::from)?;
        let result = model
            .solve_load_case(&FfiLoadCase {
                nodal_load_vector_kn: &prepared.nodal_loads_kn_knm,
                uniform_member_loads: &prepared.uniform_member_loads,
            })
            .map_err(RuntimeError::from)?;
        frame3d::project_result(
            document,
            load_selection,
            self.api.abi_version(),
            &prepared,
            &result,
        )
    }

    /// Produce the strict hash-bound bounded `ResultIR` after all native and replay gates pass.
    ///
    /// # Errors
    ///
    /// Returns a runtime error for any analysis failure, equilibrium mismatch, invalid result ID,
    /// non-finite value, hash instability or attempted authority promotion.
    pub fn analyze_linear_frame3d_result_ir(
        &self,
        document: &ModelIrV2Document,
        load_pattern_id: &str,
        result_id: &str,
    ) -> Result<LinearFrame3dResultIrV1, RuntimeError> {
        let raw = self.analyze_linear_frame3d(document, load_pattern_id)?;
        frame3d::promote_result_ir(&raw, result_id)
    }

    /// Produce a strict bounded `ResultIR` for one linear load combination.
    ///
    /// # Errors
    ///
    /// Returns the same checked failures as [`Self::analyze_linear_frame3d_load_case_result_ir`].
    pub fn analyze_linear_frame3d_combination_result_ir(
        &self,
        document: &ModelIrV2Document,
        load_combination_id: &str,
        result_id: &str,
    ) -> Result<LinearFrame3dResultIrV1, RuntimeError> {
        self.analyze_linear_frame3d_load_case_result_ir(
            document,
            LinearFrame3dLoadSelection::Combination(load_combination_id),
            result_id,
        )
    }

    /// Produce a strict bounded `ResultIR` for one explicitly selected pattern or combination.
    ///
    /// # Errors
    ///
    /// Returns a runtime error for selection, analysis, equilibrium, recovery, identity, or
    /// authority-boundary failure.
    pub fn analyze_linear_frame3d_load_case_result_ir(
        &self,
        document: &ModelIrV2Document,
        load_selection: LinearFrame3dLoadSelection<'_>,
        result_id: &str,
    ) -> Result<LinearFrame3dResultIrV1, RuntimeError> {
        let raw = self.analyze_linear_frame3d_load_case(document, load_selection)?;
        frame3d::promote_result_ir(&raw, result_id)
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
