//! Durable runtime ownership boundary.

#![forbid(unsafe_code)]

mod checkpoint;
mod job;
mod model_checkpoint;
mod model_linear_checkpoint;
mod model_linear_product;
mod sparse_checkpoint;
mod spectral_checkpoint;
mod static_checkpoint;

use std::path::Path;

pub use checkpoint::{NonlinearNdthaCheckpoint, NonlinearNdthaCheckpointReceipt};
pub use job::{
    unix_time_millis, DurableJobAnalysisProfileV1, DurableJobClaimV1, DurableJobCompletionV1,
    DurableJobError, DurableJobStatusV1, DurableJobStoreV1, DurableJobViewV1,
    JobArtifactReferenceV1, ModelIrLinearDurableJobCompletionV1,
};
pub use model_checkpoint::{
    ModelIrNdthaCheckpointBindingsV1, ModelIrNdthaCheckpointReceiptV1, ModelIrNdthaCheckpointV1,
};
pub use model_linear_checkpoint::{
    ModelIrLinearCheckpointBindingsV1, ModelIrLinearCheckpointReceiptV1, ModelIrLinearCheckpointV1,
};
pub use model_linear_product::PreparedModelIrLinearProductV1;
pub use sparse_checkpoint::{SparseLinearCheckpointReceiptV1, SparseLinearCheckpointV1};
pub use spectral_checkpoint::{DenseSpectralCheckpointReceiptV1, DenseSpectralCheckpointV1};
pub use static_checkpoint::{NonlinearStaticCheckpointReceiptV1, NonlinearStaticCheckpointV1};
use structural_contracts::legacy_runtime::{
    NdthaResponseV3, NdthaStoryInputsV3, NonlinearNdthaConfigV3,
};
use structural_contracts::model_ir::ModelIrV2Document;
use structural_contracts::model_linear_product::MODEL_IR_LINEAR_MAXIMUM_RECOVERY_RECORDS;
use structural_contracts::product_ir::{
    average_step_iterations, build_nonlinear_ndtha_result_ir_v1, NativeAnalysisRequestDocumentV1,
    NonlinearNdthaResultIrDocumentV1, NonlinearNdthaResultSummaryV1,
    NonlinearNdthaTerminalStatusV1, ProductIrContractError, ResultIdentityV1,
};
use structural_contracts::sparse_product::{
    build_sparse_linear_result_ir_v1, sparse_linear_execution_hash_v1, sparse_linear_model_hash_v1,
    SparseLinearAnalysisRequestDocumentV1, SparseLinearAnalysisRequestV1, SparseLinearConfigV1,
    SparseLinearResultIrDocumentV1, SparseLinearResultSummaryV1, SPARSE_LINEAR_MAXIMUM_NONZEROS,
    SPARSE_LINEAR_MAXIMUM_ORDER,
};
use structural_contracts::spectral_product::{
    build_dense_spectral_result_ir_v1, dense_spectral_execution_hash_v1,
    dense_spectral_model_hash_v1, DenseSpectralAnalysisRequestDocumentV1,
    DenseSpectralAnalysisRequestV1, DenseSpectralResultIrDocumentV1, SpectralAnalysisKindV1,
    SpectralGeneralizedEigenConfigV1, SpectralModeV1, SpectralResultSummaryV1,
};
use structural_contracts::static_product::{
    build_nonlinear_static_result_ir_v1, nonlinear_static_execution_hash_v1,
    nonlinear_static_model_hash_v1, NonlinearStaticAnalysisRequestDocumentV1,
    NonlinearStaticResultIrDocumentV1, NonlinearStaticResultSummaryV1,
};
use structural_ffi::{Api, Error};

pub use structural_ffi::{
    DenseSymmetricMatrix, GeneralizedEigenConfig, ModelIrLinearAssembly,
    ModelIrLinearAssemblyRequest, ModelIrLinearAssemblySizes, ModelIrNdthaAdaptedProblem,
    ModelIrNdthaAdapterReceipt, ModelIrNdthaAdapterRequest, ModelIrValidation,
    ModelIrValidationReport, NonlinearNdthaExecutionStatus, NonlinearNdthaRestartState,
    NonlinearStaticExecutionStatus, NonlinearStaticRestartState, SparseCsrMatrix,
    SparseLinearConfig, SparseLinearExecutionStatus, SparseLinearRestartState,
    SparseLinearSolverStatus,
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

/// Terminal dense spectral result bound to its exact phase-boundary checkpoint.
#[derive(Clone, Debug)]
pub struct DenseSpectralProductResultV1 {
    pub checkpoint: DenseSpectralCheckpointV1,
    pub result_ir: DenseSpectralResultIrDocumentV1,
}

/// One durable sparse PCG boundary, with `ResultIR` present only after convergence.
#[derive(Clone, Debug)]
pub struct SparseLinearProductProgressV1 {
    pub checkpoint: SparseLinearCheckpointV1,
    pub result_ir: Option<SparseLinearResultIrDocumentV1>,
}

/// One durable nonlinear-static Newton boundary, with `ResultIR` only after convergence.
#[derive(Clone, Debug)]
pub struct NonlinearStaticProductProgressV1 {
    pub checkpoint: NonlinearStaticCheckpointV1,
    pub result_ir: Option<NonlinearStaticResultIrDocumentV1>,
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
            api: Api::load_model_ir_ndtha_adapter().map_err(RuntimeError::from)?,
        })
    }

    /// Create the canonical restart boundary after strict request validation and before solve.
    ///
    /// # Errors
    ///
    /// Returns a runtime error for canonical identity, hash, or allocation failure.
    pub fn checkpoint_dense_spectral(
        request: &DenseSpectralAnalysisRequestDocumentV1,
    ) -> Result<DenseSpectralCheckpointV1, RuntimeError> {
        DenseSpectralCheckpointV1::create(request)
    }

    /// Verify a phase-boundary checkpoint against one exact spectral request.
    ///
    /// # Errors
    ///
    /// Returns checkpoint-mismatch semantics for corruption, noncanonical payload, or any
    /// request/model/execution identity drift.
    pub fn restore_dense_spectral(
        request: &DenseSpectralAnalysisRequestDocumentV1,
        bytes: &[u8],
    ) -> Result<DenseSpectralCheckpointV1, RuntimeError> {
        let checkpoint = DenseSpectralCheckpointV1::from_bytes(bytes)?;
        checkpoint.verify_request(request)?;
        Ok(checkpoint)
    }

    /// Execute one exact bounded modal/buckling request and construct deterministic `ResultIR`.
    ///
    /// The native dense eigensolve is atomic; the checkpoint is intentionally the restartable
    /// boundary immediately before dispatch, not an invented mid-Jacobi state.
    ///
    /// # Errors
    ///
    /// Returns a stable runtime/ABI error for checkpoint drift, matrix-contract failure,
    /// nonconvergence, residual failure, allocation, or result invariant failure.
    pub fn execute_dense_spectral_product(
        &self,
        request: &DenseSpectralAnalysisRequestDocumentV1,
        checkpoint_bytes: Option<&[u8]>,
    ) -> Result<DenseSpectralProductResultV1, RuntimeError> {
        let checkpoint = match checkpoint_bytes {
            Some(bytes) => Self::restore_dense_spectral(request, bytes)?,
            None => Self::checkpoint_dense_spectral(request)?,
        };
        let (summary, modes) = solve_dense_spectral(request.request())?;
        let receipt = checkpoint.receipt();
        let model_hash = dense_spectral_model_hash_v1(request)?;
        let execution_hash = dense_spectral_execution_hash_v1(request)?;
        if receipt.model_hash != model_hash || receipt.execution_hash != execution_hash {
            return Err(RuntimeError {
                code: 1301,
                message: "spectral checkpoint receipt identity drifted before result projection"
                    .to_owned(),
            });
        }
        let result_ir = build_dense_spectral_result_ir_v1(
            request,
            ResultIdentityV1 {
                request_hash: request.request_hash().to_owned(),
                model_hash,
                state_hash: receipt.state_hash,
                execution_hash,
                checkpoint_hash: receipt.checkpoint_hash,
            },
            summary,
            modes,
        )?;
        Ok(DenseSpectralProductResultV1 {
            checkpoint,
            result_ir,
        })
    }

    /// Canonically bind one complete PCG state to its exact request.
    ///
    /// # Errors
    ///
    /// Returns a runtime error if the state is not a complete valid boundary for the request or
    /// if an identity or bounded binary encoding cannot be constructed.
    pub fn checkpoint_sparse_linear(
        request: &SparseLinearAnalysisRequestDocumentV1,
        state: &SparseLinearRestartState,
    ) -> Result<SparseLinearCheckpointV1, RuntimeError> {
        SparseLinearCheckpointV1::create(request, state)
    }

    /// Decode and verify a sparse PCG checkpoint against one exact request.
    ///
    /// # Errors
    ///
    /// Returns checkpoint-mismatch semantics for corrupt/noncanonical bytes or any request,
    /// model, configuration, state, execution, or aggregate identity mismatch.
    pub fn restore_sparse_linear(
        request: &SparseLinearAnalysisRequestDocumentV1,
        bytes: &[u8],
    ) -> Result<SparseLinearCheckpointV1, RuntimeError> {
        let checkpoint = SparseLinearCheckpointV1::from_bytes(bytes)?;
        checkpoint.verify_request(request)?;
        Ok(checkpoint)
    }

    /// Begin or resume one sparse PCG execution and publish at most `iteration_budget` boundaries.
    ///
    /// Active and numerically failed terminal states remain successful checkpoint transitions;
    /// `ResultIR` is emitted only for a converged terminal state.
    ///
    /// # Errors
    ///
    /// Returns a runtime error for invalid checkpoint bindings, ABI/solver transport failure, an
    /// invalid restart state, or a failed deterministic checkpoint/ResultIR projection.
    pub fn advance_sparse_linear_product(
        &self,
        request: &SparseLinearAnalysisRequestDocumentV1,
        checkpoint_bytes: Option<&[u8]>,
        iteration_budget: u32,
    ) -> Result<SparseLinearProductProgressV1, RuntimeError> {
        let value = request.request();
        let (matrix, config) = sparse_linear_problem(value);
        let api = Api::load_sparse_linear_restart().map_err(RuntimeError::from)?;
        let mut state = match checkpoint_bytes {
            Some(bytes) => Self::restore_sparse_linear(request, bytes)?.state().clone(),
            None => api
                .begin_sparse_linear(
                    &matrix,
                    &value.right_hand_side,
                    (!value.initial_guess.is_empty()).then_some(value.initial_guess.as_slice()),
                    config,
                )
                .map_err(RuntimeError::from)?,
        };
        api.advance_sparse_linear(
            &matrix,
            &value.right_hand_side,
            config,
            iteration_budget,
            &mut state,
        )
        .map_err(RuntimeError::from)?;
        let checkpoint = Self::checkpoint_sparse_linear(request, &state)?;
        let result_ir = if state.execution_status == SparseLinearExecutionStatus::Terminal
            && state.solver_status == SparseLinearSolverStatus::Converged
        {
            Some(Self::finish_sparse_linear_product(request, &checkpoint)?)
        } else {
            None
        };
        Ok(SparseLinearProductProgressV1 {
            checkpoint,
            result_ir,
        })
    }

    /// Project one exact converged sparse checkpoint into deterministic `ResultIR`.
    ///
    /// # Errors
    ///
    /// Returns checkpoint-mismatch or state-conflict semantics unless the checkpoint is bound to
    /// the request and contains a converged terminal ABI state.
    pub fn finish_sparse_linear_product(
        request: &SparseLinearAnalysisRequestDocumentV1,
        checkpoint: &SparseLinearCheckpointV1,
    ) -> Result<SparseLinearResultIrDocumentV1, RuntimeError> {
        checkpoint.verify_request(request)?;
        let state = checkpoint.state();
        let solution = state.terminal_solution().map_err(RuntimeError::from)?;
        let receipt = checkpoint.receipt();
        let model_hash = sparse_linear_model_hash_v1(request)?;
        let execution_hash = sparse_linear_execution_hash_v1(request)?;
        if receipt.model_hash != model_hash || receipt.execution_hash != execution_hash {
            return Err(RuntimeError {
                code: 1301,
                message: "sparse checkpoint identity drifted before ResultIR projection".to_owned(),
            });
        }
        let value = request.request();
        build_sparse_linear_result_ir_v1(
            request,
            ResultIdentityV1 {
                request_hash: request.request_hash().to_owned(),
                model_hash,
                state_hash: receipt.state_hash,
                execution_hash,
                checkpoint_hash: receipt.checkpoint_hash,
            },
            SparseLinearResultSummaryV1 {
                order: value.order,
                nonzero_count: u64::try_from(value.values.len()).map_err(|_| RuntimeError {
                    code: 1900,
                    message: "sparse nonzero count exceeds u64".to_owned(),
                })?,
                iterations: solution.iterations,
                initial_residual_inf: solution.initial_residual_inf,
                final_residual_inf: solution.final_residual_inf,
                final_residual_l2: solution.final_residual_l2,
                last_increment_inf: solution.last_increment_inf,
            },
            solution.solution,
        )
        .map_err(Into::into)
    }

    /// Canonically bind one complete Newton state to its exact nonlinear-static request.
    ///
    /// # Errors
    ///
    /// Returns a runtime error if the state is invalid for the request or binary identity
    /// construction fails.
    pub fn checkpoint_nonlinear_static(
        request: &NonlinearStaticAnalysisRequestDocumentV1,
        state: &NonlinearStaticRestartState,
    ) -> Result<NonlinearStaticCheckpointV1, RuntimeError> {
        NonlinearStaticCheckpointV1::create(request, state)
    }

    /// Decode and verify a nonlinear-static Newton checkpoint against one exact request.
    ///
    /// # Errors
    ///
    /// Returns checkpoint-mismatch semantics for corrupt/noncanonical bytes or any request,
    /// model, configuration, state, execution, or aggregate identity drift.
    pub fn restore_nonlinear_static(
        request: &NonlinearStaticAnalysisRequestDocumentV1,
        bytes: &[u8],
    ) -> Result<NonlinearStaticCheckpointV1, RuntimeError> {
        let checkpoint = NonlinearStaticCheckpointV1::from_bytes(bytes)?;
        checkpoint.verify_request(request)?;
        Ok(checkpoint)
    }

    /// Begin or resume one nonlinear-static Newton execution for a bounded iteration budget.
    ///
    /// Active and nonconverged terminal states remain successful checkpoint transitions;
    /// `ResultIR` is emitted only for a converged terminal state.
    ///
    /// # Errors
    ///
    /// Returns a runtime error for invalid checkpoint bindings, ABI transport failure, invalid
    /// restart state, or deterministic checkpoint/ResultIR projection failure.
    pub fn advance_nonlinear_static_product(
        &self,
        request: &NonlinearStaticAnalysisRequestDocumentV1,
        checkpoint_bytes: Option<&[u8]>,
        iteration_budget: u32,
    ) -> Result<NonlinearStaticProductProgressV1, RuntimeError> {
        let value = request.request();
        let api = Api::load_nonlinear_static_restart().map_err(RuntimeError::from)?;
        let mut state = match checkpoint_bytes {
            Some(bytes) => Self::restore_nonlinear_static(request, bytes)?
                .state()
                .clone(),
            None => api
                .begin_nonlinear_static(&value.config, &value.inputs)
                .map_err(RuntimeError::from)?,
        };
        api.advance_nonlinear_static(&value.config, &value.inputs, iteration_budget, &mut state)
            .map_err(RuntimeError::from)?;
        let checkpoint = Self::checkpoint_nonlinear_static(request, &state)?;
        let result_ir = if state.status == NonlinearStaticExecutionStatus::Converged {
            let solution = state.terminal_solution().map_err(RuntimeError::from)?;
            let receipt = checkpoint.receipt();
            let model_hash = nonlinear_static_model_hash_v1(request)?;
            let execution_hash = nonlinear_static_execution_hash_v1(request)?;
            if receipt.model_hash != model_hash || receipt.execution_hash != execution_hash {
                return Err(RuntimeError {
                    code: 1301,
                    message:
                        "nonlinear-static checkpoint identity drifted before ResultIR projection"
                            .to_owned(),
                });
            }
            Some(build_nonlinear_static_result_ir_v1(
                request,
                ResultIdentityV1 {
                    request_hash: request.request_hash().to_owned(),
                    model_hash,
                    state_hash: receipt.state_hash,
                    execution_hash,
                    checkpoint_hash: receipt.checkpoint_hash,
                },
                NonlinearStaticResultSummaryV1 {
                    story_count: value.config.story_count,
                    iterations: solution.iterations,
                    residual_inf: solution.residual_inf,
                    residual_l2: solution.residual_l2,
                    max_abs_displacement_m: solution.max_abs_displacement_m,
                    top_displacement_m: solution.top_displacement_m,
                    base_shear_kn: solution.base_shear_kn,
                    plastic_story_count: solution.plastic_story_count,
                    line_search_backtracks: solution.line_search_backtracks,
                },
                solution.displacement_m,
            )?)
        } else {
            None
        };
        Ok(NonlinearStaticProductProgressV1 {
            checkpoint,
            result_ir,
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

    /// Adapt one immutable `ModelIR` into the exact bounded NDTHA story profile.
    ///
    /// # Errors
    ///
    /// Returns a runtime error for descriptor/hash transfer, model readiness, selector, analysis
    /// domain or native output invariant failures.
    pub fn adapt_model_ir_ndtha(
        &self,
        document: &ModelIrV2Document,
        request: &ModelIrNdthaAdapterRequest,
    ) -> Result<ModelIrNdthaAdaptedProblem, RuntimeError> {
        let model = self
            .api
            .create_model_ir(document)
            .map_err(RuntimeError::from)?;
        model
            .adapt_nonlinear_ndtha(request)
            .map_err(RuntimeError::from)
    }

    /// Assemble the exact initial typed-ModelIR linear graph through ABI v1.13.
    ///
    /// C++ remains the sole owner of graph sizing, constraint reduction, element kernels,
    /// deterministic scatter, loads, recovery layout, and model identities.
    ///
    /// # Errors
    ///
    /// Returns a stable runtime error for an unavailable v1.13 table, invalid model/profile,
    /// selector failure, allocation failure, or any native output-contract violation.
    pub fn assemble_model_ir_linear(
        &self,
        document: &ModelIrV2Document,
        load_pattern_id: &str,
    ) -> Result<ModelIrLinearAssembly, RuntimeError> {
        let model = Api::load_model_ir_linear_assembly()
            .map_err(RuntimeError::from)?
            .create_model_ir(document)
            .map_err(RuntimeError::from)?;
        validate_model_ir_linear_product_sizes(model.linear_assembly_sizes()?)?;
        model
            .assemble_linear_zero_state(load_pattern_id)
            .map_err(RuntimeError::from)
    }

    /// Assemble and recover one explicit typed-ModelIR linear state through ABI v1.13.
    ///
    /// # Errors
    ///
    /// Returns the same stable runtime boundary as [`Self::assemble_model_ir_linear`], including
    /// exact vector-size and constrained-DOF validation.
    pub fn assemble_model_ir_linear_state(
        &self,
        document: &ModelIrV2Document,
        request: &ModelIrLinearAssemblyRequest,
    ) -> Result<ModelIrLinearAssembly, RuntimeError> {
        let model = Api::load_model_ir_linear_assembly()
            .map_err(RuntimeError::from)?
            .create_model_ir(document)
            .map_err(RuntimeError::from)?;
        validate_model_ir_linear_product_sizes(model.linear_assembly_sizes()?)?;
        model
            .assemble_linear_reference(request)
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

fn validate_model_ir_linear_product_sizes(
    sizes: ModelIrLinearAssemblySizes,
) -> Result<(), RuntimeError> {
    let bounded = sizes.active_dof_count <= SPARSE_LINEAR_MAXIMUM_ORDER as usize
        && sizes.structural_entry_count <= SPARSE_LINEAR_MAXIMUM_NONZEROS
        && sizes.recovery_record_count <= MODEL_IR_LINEAR_MAXIMUM_RECOVERY_RECORDS;
    if bounded {
        Ok(())
    } else {
        Err(RuntimeError {
            code: 1100,
            message: "ModelIR linear graph exceeds the bounded sparse product allocation limits"
                .to_owned(),
        })
    }
}

fn sparse_linear_problem(
    value: &SparseLinearAnalysisRequestV1,
) -> (SparseCsrMatrix, SparseLinearConfig) {
    (
        SparseCsrMatrix {
            row_offsets: value.row_offsets.clone(),
            column_indices: value.column_indices.clone(),
            values: value.values.clone(),
        },
        sparse_linear_config(value.config),
    )
}

const fn sparse_linear_config(value: SparseLinearConfigV1) -> SparseLinearConfig {
    SparseLinearConfig {
        max_iterations: value.max_iterations,
        absolute_residual_tolerance: value.absolute_residual_tolerance,
        relative_residual_tolerance: value.relative_residual_tolerance,
        maximum_increment: value.maximum_increment,
    }
}

type SpectralNativeOutput = (SpectralResultSummaryV1, Vec<SpectralModeV1>);

fn solve_dense_spectral(
    value: &DenseSpectralAnalysisRequestV1,
) -> Result<SpectralNativeOutput, RuntimeError> {
    let order = usize::try_from(value.order).map_err(|_| RuntimeError {
        code: 1100,
        message: "spectral request order exceeds the address space".to_owned(),
    })?;
    let stiffness = DenseSymmetricMatrix {
        order,
        values: value.stiffness.clone(),
    };
    let secondary = DenseSymmetricMatrix {
        order,
        values: value.secondary_matrix.clone(),
    };
    let config = generalized_eigen_config(&value.config);
    let scale = if value.coordinate_recovery_scale.is_empty() {
        None
    } else {
        Some(value.coordinate_recovery_scale.as_slice())
    };
    let api = Api::load_generalized_eigen().map_err(RuntimeError::from)?;
    match value.analysis_kind {
        SpectralAnalysisKindV1::Modal => project_modal_solution(
            &api,
            &stiffness,
            &secondary,
            scale,
            config,
            value.config.mode_count,
        ),
        SpectralAnalysisKindV1::LinearBuckling => project_buckling_solution(
            &api,
            &stiffness,
            &secondary,
            scale,
            config,
            value.config.mode_count,
        ),
    }
}

fn generalized_eigen_config(value: &SpectralGeneralizedEigenConfigV1) -> GeneralizedEigenConfig {
    GeneralizedEigenConfig {
        mode_count: value.mode_count,
        maximum_sweeps: value.maximum_sweeps,
        symmetry_relative_tolerance: value.symmetry_relative_tolerance,
        positive_semidefinite_relative_tolerance: value.positive_semidefinite_relative_tolerance,
        mode_relative_tolerance: value.mode_relative_tolerance,
        cluster_relative_tolerance: value.cluster_relative_tolerance,
        residual_relative_tolerance: value.residual_relative_tolerance,
        orthogonality_tolerance: value.orthogonality_tolerance,
        eigensolver_relative_tolerance: value.eigensolver_relative_tolerance,
    }
}

fn project_modal_solution(
    api: &Api,
    stiffness: &DenseSymmetricMatrix,
    mass: &DenseSymmetricMatrix,
    scale: Option<&[f64]>,
    config: GeneralizedEigenConfig,
    mode_count: u32,
) -> Result<SpectralNativeOutput, RuntimeError> {
    let solution = api
        .solve_modal_modes(stiffness, mass, scale, config)
        .map_err(RuntimeError::from)?;
    let modes = solution
        .modes
        .into_iter()
        .map(|mode| {
            Ok(SpectralModeV1::Modal {
                eigenvalue_rad2_per_s2: mode.eigenvalue_rad2_per_s2,
                omega_rad_per_s: mode.omega_rad_per_s,
                frequency_hz: mode.frequency_hz,
                period_s: mode.period_s,
                max_component_normalized_shape: max_component_normalized(
                    &mode.mass_normalized_shape,
                )?,
                mass_normalized_shape: mode.mass_normalized_shape,
                generalized_mass: mode.generalized_mass,
                generalized_stiffness: mode.generalized_stiffness,
                residual_relative_inf: mode.residual_relative_inf,
            })
        })
        .collect::<Result<Vec<_>, RuntimeError>>()?;
    Ok((
        SpectralResultSummaryV1 {
            mode_count,
            rigid_mode_count: solution.rigid_mode_count,
            finite_positive_eigenvalue_count: 0,
            geometric_stiffness_positive_rank: 0,
            eigensolver_sweeps: solution.eigensolver_sweeps,
            critical_load_factor: None,
            metric_orthogonality_error_inf: solution.mass_orthogonality_error_inf,
            operator_diagonalization_error_inf: solution.stiffness_diagonalization_error_inf,
            stiffness_relative_symmetry_error: solution.stiffness_relative_symmetry_error,
            secondary_relative_symmetry_error: solution.mass_relative_symmetry_error,
            stiffness_minimum_eigenvalue: solution.stiffness_minimum_eigenvalue,
            secondary_minimum_eigenvalue: solution.mass_minimum_eigenvalue,
        },
        modes,
    ))
}

fn project_buckling_solution(
    api: &Api,
    stiffness: &DenseSymmetricMatrix,
    geometric_stiffness: &DenseSymmetricMatrix,
    scale: Option<&[f64]>,
    config: GeneralizedEigenConfig,
    mode_count: u32,
) -> Result<SpectralNativeOutput, RuntimeError> {
    let solution = api
        .solve_linear_buckling(stiffness, geometric_stiffness, scale, config)
        .map_err(RuntimeError::from)?;
    let modes = solution
        .modes
        .into_iter()
        .map(|mode| {
            Ok(SpectralModeV1::LinearBuckling {
                load_factor: mode.load_factor,
                max_component_normalized_shape: max_component_normalized(
                    &mode.stiffness_normalized_shape,
                )?,
                stiffness_normalized_shape: mode.stiffness_normalized_shape,
                generalized_elastic_stiffness: mode.generalized_elastic_stiffness,
                generalized_geometric_stiffness: mode.generalized_geometric_stiffness,
                residual_relative_inf: mode.residual_relative_inf,
            })
        })
        .collect::<Result<Vec<_>, RuntimeError>>()?;
    Ok((
        SpectralResultSummaryV1 {
            mode_count,
            rigid_mode_count: 0,
            finite_positive_eigenvalue_count: solution.finite_positive_eigenvalue_count,
            geometric_stiffness_positive_rank: solution.geometric_stiffness_positive_rank,
            eigensolver_sweeps: solution.eigensolver_sweeps,
            critical_load_factor: Some(solution.critical_load_factor),
            metric_orthogonality_error_inf: solution.stiffness_orthogonality_error_inf,
            operator_diagonalization_error_inf: solution.geometric_diagonalization_error_inf,
            stiffness_relative_symmetry_error: solution.stiffness_relative_symmetry_error,
            secondary_relative_symmetry_error: solution.geometric_stiffness_relative_symmetry_error,
            stiffness_minimum_eigenvalue: solution.stiffness_minimum_eigenvalue,
            secondary_minimum_eigenvalue: solution.geometric_stiffness_minimum_eigenvalue,
        },
        modes,
    ))
}

fn max_component_normalized(values: &[f64]) -> Result<Vec<f64>, RuntimeError> {
    let maximum = values
        .iter()
        .map(|value| value.abs())
        .fold(0.0_f64, f64::max);
    if !maximum.is_finite() || maximum <= 0.0 {
        return Err(RuntimeError {
            code: 1900,
            message: "native spectral mode cannot be max-component normalized".to_owned(),
        });
    }
    Ok(values.iter().map(|value| value / maximum).collect())
}

#[cfg(test)]
mod tests {
    use super::{
        validate_model_ir_linear_product_sizes, ModelIrLinearAssemblySizes, Runtime,
        MODEL_IR_LINEAR_MAXIMUM_RECOVERY_RECORDS, SPARSE_LINEAR_MAXIMUM_NONZEROS,
        SPARSE_LINEAR_MAXIMUM_ORDER,
    };

    #[test]
    fn runtime_uses_the_safe_ffi_owner() {
        let runtime = Runtime::new().expect("runtime loads native core");
        assert_eq!(runtime.native_capabilities(), 255);
    }

    #[test]
    fn model_ir_linear_product_limits_apply_before_output_allocation() {
        let maximum = ModelIrLinearAssemblySizes {
            global_dof_count: 1_000_000,
            active_dof_count: SPARSE_LINEAR_MAXIMUM_ORDER as usize,
            row_offset_count: SPARSE_LINEAR_MAXIMUM_ORDER as usize + 1,
            structural_entry_count: SPARSE_LINEAR_MAXIMUM_NONZEROS,
            recovery_record_count: MODEL_IR_LINEAR_MAXIMUM_RECOVERY_RECORDS,
            recovery_offset_count: MODEL_IR_LINEAR_MAXIMUM_RECOVERY_RECORDS + 1,
            recovery_value_count: MODEL_IR_LINEAR_MAXIMUM_RECOVERY_RECORDS * 12,
            model_identity_length: 71,
        };
        assert_eq!(validate_model_ir_linear_product_sizes(maximum), Ok(()));

        for oversized in [
            ModelIrLinearAssemblySizes {
                active_dof_count: maximum.active_dof_count + 1,
                ..maximum
            },
            ModelIrLinearAssemblySizes {
                structural_entry_count: maximum.structural_entry_count + 1,
                ..maximum
            },
            ModelIrLinearAssemblySizes {
                recovery_record_count: maximum.recovery_record_count + 1,
                ..maximum
            },
        ] {
            assert_eq!(
                validate_model_ir_linear_product_sizes(oversized)
                    .expect_err("oversized product graph fails")
                    .code,
                1100
            );
        }
    }
}
