//! Safe entry-table and immutable `ModelIR` ownership for C ABI v1.

mod descriptor;

use core::ffi::{c_char, c_void};
use core::fmt;
use core::mem::size_of;
use core::ptr::{self, NonNull};

use serde::{Deserialize, Serialize};
use structural_contracts::legacy_runtime::{
    NdthaStoryInputsV3, NonlinearNdthaConfigV3, NonlinearStaticConfigV3, StaticStoryInputsV3,
    TrackConfigV3, TrackSupportType, TrackTheory,
};
use structural_contracts::model_ir::{parse_model_ir_v2, ModelIrV2Document};
use structural_ffi_sys as sys;

use descriptor::DescriptorArena;

const ERROR_CAPACITY: usize = 256;

/// Stable error returned by the native core or by a fail-closed safe-wrapper invariant.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Error {
    pub code: sys::SaStatusCodeV1,
    pub message: String,
}

impl fmt::Display for Error {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "native ABI error {}: {}",
            self.code, self.message
        )
    }
}

impl std::error::Error for Error {}

/// One deterministic semantic issue emitted by the C++ `ModelIR` owner.
#[derive(Clone, Debug, Deserialize, Eq, Ord, PartialEq, PartialOrd, Serialize)]
pub struct ModelIrValidationIssue {
    pub code: String,
    pub path: String,
    pub detail: String,
}

/// Entity-family counts carried in the stable `ModelIR` validation report.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct ModelIrEntityCounts {
    pub nodes: u64,
    pub materials: u64,
    pub sections: u64,
    pub elements: u64,
    pub constraints: u64,
    pub load_patterns: u64,
    pub load_combinations: u64,
    pub time_functions: u64,
    pub construction_stages: u64,
    pub roundtrip_map: u64,
    pub unsupported_features: u64,
}

/// Parsed form of `structural-model-ir-cpp-validation.v1`.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
// These independent booleans intentionally mirror the stable C++ wire report. In particular,
// contract validity and analysis readiness must not collapse into one enum state.
#[allow(clippy::struct_excessive_bools)]
pub struct ModelIrValidationReport {
    pub schema_version: String,
    pub model_ir_schema_version: String,
    pub model_id: String,
    pub schema_valid: bool,
    pub semantics_valid: bool,
    pub contract_valid: bool,
    pub analysis_ready: bool,
    pub issues: Vec<ModelIrValidationIssue>,
    pub blocking_feature_ids: Vec<String>,
    pub declared_blocking_feature_ids: Vec<String>,
    pub derived_blocking_feature_ids: Vec<String>,
    pub content_hash: String,
    pub semantic_hash: String,
    pub provenance_hash: String,
    pub entity_counts: ModelIrEntityCounts,
    pub abi_version: u32,
    pub library_build_identity: String,
    pub claim_boundary: String,
}

/// Verified Rust -> C ABI -> C++ -> snapshot -> Rust result.
#[derive(Clone, Debug)]
pub struct ModelIrValidation {
    pub report: ModelIrValidationReport,
    pub report_json: String,
    pub snapshot: ModelIrV2Document,
}

/// Caller-owned deterministic result from the bounded C++ track point-load CPU kernel.
#[derive(Clone, Debug, PartialEq)]
pub struct TrackPointLoadSolution {
    pub iterations: u32,
    pub residual_inf: f64,
    pub max_abs_displacement_m: f64,
    pub mid_displacement_m: f64,
    pub displacement_m: Vec<f64>,
    pub rotation_rad: Vec<f64>,
    pub execution_backend: u32,
    pub fallback_count: u32,
}

/// Caller-owned deterministic result from the bounded C++ nonlinear static CPU kernel.
#[derive(Clone, Debug, PartialEq)]
pub struct NonlinearStaticSolution {
    pub iterations: u32,
    pub residual_inf: f64,
    pub residual_l2: f64,
    pub max_abs_displacement_m: f64,
    pub top_displacement_m: f64,
    pub base_shear_kn: f64,
    pub plastic_story_count: u32,
    pub line_search_backtracks: u32,
    pub displacement_m: Vec<f64>,
    pub execution_backend: u32,
    pub fallback_count: u32,
}

/// Caller-owned deterministic response channels from the C++ nonlinear NDTHA CPU kernel.
#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct NonlinearNdthaResponse {
    pub top_displacement_m: Vec<f64>,
    pub drift_ratio_pct: Vec<f64>,
    pub base_shear_kn: Vec<f64>,
    pub core_drift_pct: Vec<f64>,
    pub core_shear_kn: Vec<f64>,
    pub step_converged: Vec<bool>,
    pub step_iterations: Vec<u32>,
    pub step_plastic_story_count: Vec<u32>,
    pub step_residual_inf: Vec<f64>,
    pub story_drift_envelope_pct: Vec<f64>,
    pub final_story_drift_pct: Vec<f64>,
}

/// Stable inter-step execution state used by the v1.5 caller-owned restart operation.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum NonlinearNdthaExecutionStatus {
    Active,
    Completed,
    Collapsed,
    Nonconverged,
}

/// Pointer-free Rust owner of every value needed to resume a nonlinear NDTHA execution.
#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct NonlinearNdthaRestartState {
    pub next_step: u32,
    pub status: NonlinearNdthaExecutionStatus,
    pub collapse_step: i32,
    pub collapse_time_s: f64,
    pub collapse_drift_ratio_pct: f64,
    pub collapse_top_displacement_m: f64,
    pub max_plastic_story_count: u32,
    pub max_drift_ratio_pct: f64,
    pub adaptive_iteration_sum: u64,
    pub total_line_search_backtracks: u32,
    pub displacement_m: Vec<f64>,
    pub velocity_m_per_s: Vec<f64>,
    pub acceleration_m_per_s2: Vec<f64>,
    pub response: NonlinearNdthaResponse,
    pub execution_backend: u32,
    pub fallback_count: u32,
}

/// Caller-owned deterministic result from the bounded C++ nonlinear NDTHA CPU kernel.
#[derive(Clone, Debug, PartialEq)]
pub struct NonlinearNdthaSolution {
    pub converged_all_steps: bool,
    pub collapsed: bool,
    pub collapse_step: i32,
    pub collapse_time_s: f64,
    pub collapse_drift_ratio_pct: f64,
    pub collapse_top_displacement_m: f64,
    pub step_count_completed: u32,
    pub max_plastic_story_count: u32,
    pub max_drift_ratio_pct: f64,
    pub avg_step_iterations: f64,
    pub residual_top_displacement_m: f64,
    pub residual_drift_ratio_pct: f64,
    pub total_line_search_backtracks: u32,
    pub response: NonlinearNdthaResponse,
    pub execution_backend: u32,
    pub fallback_count: u32,
}

struct NdthaOutputArena {
    top_displacement_m: Vec<f64>,
    drift_ratio_pct: Vec<f64>,
    base_shear_kn: Vec<f64>,
    core_drift_pct: Vec<f64>,
    core_shear_kn: Vec<f64>,
    step_converged: Vec<u8>,
    step_iterations: Vec<u32>,
    step_plastic_story_count: Vec<u32>,
    step_residual_inf: Vec<f64>,
    story_drift_envelope_pct: Vec<f64>,
    final_story_drift_pct: Vec<f64>,
}

impl NdthaOutputArena {
    fn allocate(story_count: usize, step_count: usize) -> Result<Self, Error> {
        Ok(Self {
            top_displacement_m: allocate_f64_output(step_count)?,
            drift_ratio_pct: allocate_f64_output(step_count)?,
            base_shear_kn: allocate_f64_output(step_count)?,
            core_drift_pct: allocate_f64_output(step_count)?,
            core_shear_kn: allocate_f64_output(step_count)?,
            step_converged: allocate_u8_output(step_count)?,
            step_iterations: allocate_u32_output(step_count)?,
            step_plastic_story_count: allocate_u32_output(step_count)?,
            step_residual_inf: allocate_f64_output(step_count)?,
            story_drift_envelope_pct: allocate_f64_output(story_count)?,
            final_story_drift_pct: allocate_f64_output(story_count)?,
        })
    }

    fn descriptor(&mut self, abi_version: u32) -> Result<sys::SaNonlinearNdthaOutputsV1, Error> {
        Ok(sys::SaNonlinearNdthaOutputsV1 {
            abi_version,
            struct_size: abi_size::<sys::SaNonlinearNdthaOutputsV1>(),
            top_displacement_m: mutable_f64_view(&mut self.top_displacement_m, abi_version)?,
            drift_ratio_pct: mutable_f64_view(&mut self.drift_ratio_pct, abi_version)?,
            base_shear_kn: mutable_f64_view(&mut self.base_shear_kn, abi_version)?,
            core_drift_pct: mutable_f64_view(&mut self.core_drift_pct, abi_version)?,
            core_shear_kn: mutable_f64_view(&mut self.core_shear_kn, abi_version)?,
            step_converged: mutable_u8_view(&mut self.step_converged, abi_version)?,
            step_iterations: mutable_u32_view(&mut self.step_iterations, abi_version)?,
            step_plastic_story_count: mutable_u32_view(
                &mut self.step_plastic_story_count,
                abi_version,
            )?,
            step_residual_inf: mutable_f64_view(&mut self.step_residual_inf, abi_version)?,
            story_drift_envelope_pct: mutable_f64_view(
                &mut self.story_drift_envelope_pct,
                abi_version,
            )?,
            final_story_drift_pct: mutable_f64_view(&mut self.final_story_drift_pct, abi_version)?,
            reserved: [0; 2],
        })
    }

    fn from_response(
        response: &NonlinearNdthaResponse,
        story_count: usize,
        step_count: usize,
    ) -> Result<Self, Error> {
        validate_response_lengths(response, story_count, step_count)?;
        let mut step_converged = Vec::new();
        step_converged
            .try_reserve_exact(step_count)
            .map_err(|_| allocation_error("restart convergence"))?;
        step_converged.extend(response.step_converged.iter().map(|value| u8::from(*value)));
        Ok(Self {
            top_displacement_m: try_clone_slice(
                &response.top_displacement_m,
                "restart top displacement",
            )?,
            drift_ratio_pct: try_clone_slice(&response.drift_ratio_pct, "restart drift ratio")?,
            base_shear_kn: try_clone_slice(&response.base_shear_kn, "restart base shear")?,
            core_drift_pct: try_clone_slice(&response.core_drift_pct, "restart core drift")?,
            core_shear_kn: try_clone_slice(&response.core_shear_kn, "restart core shear")?,
            step_converged,
            step_iterations: try_clone_slice(&response.step_iterations, "restart iterations")?,
            step_plastic_story_count: try_clone_slice(
                &response.step_plastic_story_count,
                "restart plastic counts",
            )?,
            step_residual_inf: try_clone_slice(&response.step_residual_inf, "restart residuals")?,
            story_drift_envelope_pct: try_clone_slice(
                &response.story_drift_envelope_pct,
                "restart drift envelope",
            )?,
            final_story_drift_pct: try_clone_slice(
                &response.final_story_drift_pct,
                "restart final drift",
            )?,
        })
    }

    fn into_response(self) -> NonlinearNdthaResponse {
        NonlinearNdthaResponse {
            top_displacement_m: self.top_displacement_m,
            drift_ratio_pct: self.drift_ratio_pct,
            base_shear_kn: self.base_shear_kn,
            core_drift_pct: self.core_drift_pct,
            core_shear_kn: self.core_shear_kn,
            step_converged: self
                .step_converged
                .into_iter()
                .map(|value| value == 1)
                .collect(),
            step_iterations: self.step_iterations,
            step_plastic_story_count: self.step_plastic_story_count,
            step_residual_inf: self.step_residual_inf,
            story_drift_envelope_pct: self.story_drift_envelope_pct,
            final_story_drift_pct: self.final_story_drift_pct,
        }
    }

    fn finish(
        self,
        raw: sys::SaNonlinearNdthaResultV1,
        config: &NonlinearNdthaConfigV3,
    ) -> Result<NonlinearNdthaSolution, Error> {
        validate_ndtha_result(&raw, config, &self.step_converged)?;
        Ok(NonlinearNdthaSolution {
            converged_all_steps: raw.converged_all_steps == 1,
            collapsed: raw.collapsed == 1,
            collapse_step: raw.collapse_step,
            collapse_time_s: raw.collapse_time_s,
            collapse_drift_ratio_pct: raw.collapse_drift_ratio_pct,
            collapse_top_displacement_m: raw.collapse_top_displacement_m,
            step_count_completed: raw.step_count_completed,
            max_plastic_story_count: raw.max_plastic_story_count,
            max_drift_ratio_pct: raw.max_drift_ratio_pct,
            avg_step_iterations: raw.avg_step_iterations,
            residual_top_displacement_m: raw.residual_top_displacement_m,
            residual_drift_ratio_pct: raw.residual_drift_ratio_pct,
            total_line_search_backtracks: raw.total_line_search_backtracks,
            response: self.into_response(),
            execution_backend: raw.execution_backend,
            fallback_count: raw.fallback_count,
        })
    }
}

struct NdthaRestartArena {
    displacement_m: Vec<f64>,
    velocity_m_per_s: Vec<f64>,
    acceleration_m_per_s2: Vec<f64>,
    response: NdthaOutputArena,
}

impl NdthaRestartArena {
    fn from_state(
        state: &NonlinearNdthaRestartState,
        story_count: usize,
        step_count: usize,
    ) -> Result<Self, Error> {
        validate_restart_state(state, story_count, step_count)?;
        Ok(Self {
            displacement_m: try_clone_slice(&state.displacement_m, "restart displacement")?,
            velocity_m_per_s: try_clone_slice(&state.velocity_m_per_s, "restart velocity")?,
            acceleration_m_per_s2: try_clone_slice(
                &state.acceleration_m_per_s2,
                "restart acceleration",
            )?,
            response: NdthaOutputArena::from_response(&state.response, story_count, step_count)?,
        })
    }

    fn descriptor(
        &mut self,
        state: &NonlinearNdthaRestartState,
    ) -> Result<sys::SaNonlinearNdthaStateV1, Error> {
        Ok(sys::SaNonlinearNdthaStateV1 {
            abi_version: sys::SA_ABI_V1_5,
            struct_size: abi_size::<sys::SaNonlinearNdthaStateV1>(),
            next_step: state.next_step,
            status: execution_status_to_raw(state.status),
            collapse_step: state.collapse_step,
            max_plastic_story_count: state.max_plastic_story_count,
            total_line_search_backtracks: state.total_line_search_backtracks,
            execution_backend: state.execution_backend,
            fallback_count: state.fallback_count,
            reserved_u32: 0,
            adaptive_iteration_sum: state.adaptive_iteration_sum,
            collapse_time_s: state.collapse_time_s,
            collapse_drift_ratio_pct: state.collapse_drift_ratio_pct,
            collapse_top_displacement_m: state.collapse_top_displacement_m,
            max_drift_ratio_pct: state.max_drift_ratio_pct,
            displacement_m: mutable_f64_view(&mut self.displacement_m, sys::SA_ABI_V1_5)?,
            velocity_m_per_s: mutable_f64_view(&mut self.velocity_m_per_s, sys::SA_ABI_V1_5)?,
            acceleration_m_per_s2: mutable_f64_view(
                &mut self.acceleration_m_per_s2,
                sys::SA_ABI_V1_5,
            )?,
            response: self.response.descriptor(sys::SA_ABI_V1_5)?,
            reserved: [0; 2],
        })
    }

    fn finish(
        self,
        raw: &sys::SaNonlinearNdthaStateV1,
        story_count: usize,
        step_count: usize,
    ) -> Result<NonlinearNdthaRestartState, Error> {
        if raw.abi_version != sys::SA_ABI_V1_5
            || raw.struct_size != abi_size::<sys::SaNonlinearNdthaStateV1>()
            || raw.execution_backend != sys::SA_EXECUTION_BACKEND_CPU
            || raw.fallback_count != 0
            || raw.reserved_u32 != 0
            || raw.reserved != [0; 2]
        {
            return Err(Error {
                code: sys::SA_ERR_INTERNAL,
                message: "native nonlinear NDTHA restart metadata violated ABI v1.5".to_owned(),
            });
        }
        let state = NonlinearNdthaRestartState {
            next_step: raw.next_step,
            status: execution_status_from_raw(raw.status)?,
            collapse_step: raw.collapse_step,
            collapse_time_s: raw.collapse_time_s,
            collapse_drift_ratio_pct: raw.collapse_drift_ratio_pct,
            collapse_top_displacement_m: raw.collapse_top_displacement_m,
            max_plastic_story_count: raw.max_plastic_story_count,
            max_drift_ratio_pct: raw.max_drift_ratio_pct,
            adaptive_iteration_sum: raw.adaptive_iteration_sum,
            total_line_search_backtracks: raw.total_line_search_backtracks,
            displacement_m: self.displacement_m,
            velocity_m_per_s: self.velocity_m_per_s,
            acceleration_m_per_s2: self.acceleration_m_per_s2,
            response: self.response.into_response(),
            execution_backend: raw.execution_backend,
            fallback_count: raw.fallback_count,
        };
        validate_restart_state(&state, story_count, step_count)?;
        Ok(state)
    }
}

/// Immutable, process-lifetime C ABI v1 function table.
#[derive(Clone, Copy)]
pub struct Api {
    table: sys::SaApiV1,
}

// SAFETY: table loading validates every negotiated slot and copies only immutable,
// process-lifetime function pointers. The native library retains no caller-owned pointer.
unsafe impl Send for Api {}
// SAFETY: all table operations use caller-owned arguments; the ModelIR operations enforce
// immutable concurrent access in the native handle registry.
unsafe impl Sync for Api {}

impl Api {
    /// Load the ABI v1.0 compatibility table.
    ///
    /// # Errors
    ///
    /// Returns a stable ABI error if the library rejects the request or returns an invalid
    /// compatibility table.
    pub fn load() -> Result<Self, Error> {
        Self::load_version(sys::SA_ABI_V1_0)
    }

    /// Load the ABI v1.1 table with typed `ModelIR` and snapshot support.
    ///
    /// # Errors
    ///
    /// Returns a stable ABI error if any required v1.1 capability or operation is absent.
    pub fn load_model_ir() -> Result<Self, Error> {
        Self::load_version(sys::SA_ABI_V1_1)
    }

    /// Load the ABI v1.2 table with the deterministic track point-load CPU operation.
    ///
    /// # Errors
    ///
    /// Returns a stable ABI error if the v1.2 capability or operation is absent.
    pub fn load_track_point_load() -> Result<Self, Error> {
        Self::load_version(sys::SA_ABI_V1_2)
    }

    /// Load the ABI v1.3 table with the deterministic nonlinear static CPU operation.
    ///
    /// # Errors
    ///
    /// Returns a stable ABI error if the v1.3 capability or operation is absent.
    pub fn load_nonlinear_static() -> Result<Self, Error> {
        Self::load_version(sys::SA_ABI_V1_3)
    }

    /// Load the ABI v1.4 table with the deterministic nonlinear NDTHA CPU operation.
    ///
    /// # Errors
    ///
    /// Returns a stable ABI error if the v1.4 capability or operation is absent.
    pub fn load_nonlinear_ndtha() -> Result<Self, Error> {
        Self::load_version(sys::SA_ABI_V1_4)
    }

    /// Load the ABI v1.5 table with caller-owned nonlinear NDTHA restart state.
    ///
    /// # Errors
    ///
    /// Returns a stable ABI error if the restart capability or operation is absent.
    pub fn load_nonlinear_ndtha_restart() -> Result<Self, Error> {
        Self::load_version(sys::SA_ABI_V1_5)
    }

    fn load_version(abi_version: u32) -> Result<Self, Error> {
        let request = sys::SaApiRequestV1 {
            abi_version,
            struct_size: abi_size::<sys::SaApiRequestV1>(),
            flags: 0,
            reserved: [0; 3],
        };
        let mut table = sys::SaApiV1 {
            abi_version,
            ..sys::SaApiV1::default()
        };
        let mut storage = [0_i8; ERROR_CAPACITY];
        let mut error = error_buffer(abi_version, &mut storage);
        // SAFETY: request, table and error point to live, correctly sized C-layout values.
        let status = unsafe { sys::sa_get_api_v1(&request, &mut table, &mut error) };
        if status != sys::SA_OK {
            return Err(error_from_buffer(status, &storage));
        }
        validate_table(&table, abi_version)?;
        Ok(Self { table })
    }

    /// Return the negotiated ABI version.
    #[must_use]
    pub const fn abi_version(self) -> u32 {
        self.table.abi_version
    }

    /// Return the capability bits declared by the negotiated function table.
    #[must_use]
    pub const fn capabilities(self) -> u64 {
        self.table.capabilities
    }

    /// Validate one caller-owned packed FP64 host slice without retaining it.
    ///
    /// # Errors
    ///
    /// Returns the native validation status and bounded diagnostic on invalid metadata.
    pub fn validate_f64_slice(self, values: &[f64]) -> Result<(), Error> {
        let data = if values.is_empty() {
            ptr::null()
        } else {
            values.as_ptr().cast::<c_void>()
        };
        let view = sys::SaBufferViewV1 {
            abi_version: self.abi_version(),
            struct_size: abi_size::<sys::SaBufferViewV1>(),
            data,
            length: usize_to_u64(values.len())?,
            stride_bytes: usize_to_u64(size_of::<f64>())?,
            element_type: sys::SA_ELEMENT_TYPE_F64,
            memory_space: sys::SA_MEMORY_SPACE_HOST,
            device_id: -1,
            flags: 0,
        };
        let validate = self.table.validate_buffer_view.ok_or_else(invalid_table)?;
        let mut storage = [0_i8; ERROR_CAPACITY];
        let mut error = error_buffer(self.abi_version(), &mut storage);
        // SAFETY: the view borrows `values` for this call only and the error storage is live.
        let status = unsafe { validate(&view, &mut error) };
        status_result(status, &storage)
    }

    /// Deep-copy one schema-valid Rust `ModelIR` document into an immutable native handle.
    ///
    /// # Errors
    ///
    /// Returns an ABI or descriptor-invariant error. Semantic invalidity remains a successful
    /// handle and is represented by its validation report.
    pub fn create_model_ir(self, document: &ModelIrV2Document) -> Result<ModelIr, Error> {
        if self.abi_version() < sys::SA_ABI_V1_1 {
            return Err(Error {
                code: sys::SA_ERR_UNSUPPORTED,
                message: "typed ModelIR requires ABI v1.1".to_owned(),
            });
        }
        let arena = DescriptorArena::build(document)?;
        let create = self.table.model_ir_create.ok_or_else(invalid_table)?;
        let mut output = ptr::null_mut();
        let mut storage = [0_i8; ERROR_CAPACITY];
        let mut error = error_buffer(self.abi_version(), &mut storage);
        // SAFETY: the arena owns every borrowed string and slice for the complete call. The
        // negotiated contract deep-copies the descriptor before returning.
        let status = unsafe { create(arena.root(), &mut output, &mut error) };
        if status != sys::SA_OK {
            return Err(error_from_buffer(status, &storage));
        }
        let handle = NonNull::new(output).ok_or_else(|| Error {
            code: sys::SA_ERR_INTERNAL,
            message: "native ModelIR create returned a null success handle".to_owned(),
        })?;
        Ok(ModelIr { api: self, handle })
    }

    /// Execute and verify the complete Rust -> C ABI -> C++ -> snapshot -> Rust round-trip.
    ///
    /// # Errors
    ///
    /// Returns an error for ABI failure, malformed native output, or any byte/hash identity
    /// mismatch. Semantic invalidity and explicit blockers remain fields in the returned report.
    pub fn validate_model_ir(
        self,
        document: &ModelIrV2Document,
    ) -> Result<ModelIrValidation, Error> {
        let model = self.create_model_ir(document)?;
        let report_json = model.validation_report_json()?;
        let report: ModelIrValidationReport =
            serde_json::from_str(&report_json).map_err(|_| Error {
                code: sys::SA_ERR_INTERNAL,
                message: "native ModelIR validation report is not the required JSON contract"
                    .to_owned(),
            })?;
        let snapshot_bytes = model.snapshot_bytes()?;
        let snapshot = parse_model_ir_v2(&snapshot_bytes).map_err(|_| Error {
            code: sys::SA_ERR_INTERNAL,
            message: "native ModelIR snapshot failed strict Rust reconstruction".to_owned(),
        })?;
        verify_round_trip(document, &snapshot, &snapshot_bytes, &report)?;
        Ok(ModelIrValidation {
            report,
            report_json,
            snapshot,
        })
    }

    /// Solve one bounded point-load track case in the C++ serial FP64 CPU backend.
    ///
    /// The operation owns no input or output memory after it returns and rejects any backend
    /// fallback. Numerical nonconvergence is returned as `SA_ERR_NONCONVERGENCE` without partial
    /// output mutation.
    ///
    /// # Errors
    ///
    /// Returns a stable ABI error for invalid inputs, allocation failure, output invariants or
    /// numerical nonconvergence.
    pub fn solve_track_point_load(
        self,
        config: &TrackConfigV3,
    ) -> Result<TrackPointLoadSolution, Error> {
        if self.abi_version() < sys::SA_ABI_V1_2 {
            return Err(Error {
                code: sys::SA_ERR_UNSUPPORTED,
                message: "track point-load CPU solve requires ABI v1.2".to_owned(),
            });
        }
        let count = usize::try_from(config.node_count).map_err(|_| Error {
            code: sys::SA_ERR_INVALID_ARGUMENT,
            message: "track node_count exceeds the Rust address space".to_owned(),
        })?;
        if count < 7 || config.node_count > sys::SA_TRACK_POINT_LOAD_MAX_NODE_COUNT {
            return Err(Error {
                code: sys::SA_ERR_INVALID_ARGUMENT,
                message: "track node_count is outside the bounded product range".to_owned(),
            });
        }
        let mut displacement_m = allocate_f64_output(count)?;
        let mut rotation_rad = allocate_f64_output(count)?;
        let raw_config = sys::SaTrackPointLoadConfigV1 {
            abi_version: sys::SA_ABI_V1_2,
            struct_size: abi_size::<sys::SaTrackPointLoadConfigV1>(),
            length_m: config.length_m,
            node_count: config.node_count,
            support_type: match config.support_type {
                TrackSupportType::Pinned => sys::SA_TRACK_SUPPORT_PINNED,
                TrackSupportType::Fixed => sys::SA_TRACK_SUPPORT_FIXED,
            },
            theory: match config.theory {
                TrackTheory::Euler => sys::SA_TRACK_THEORY_EULER,
                TrackTheory::Timoshenko => sys::SA_TRACK_THEORY_TIMOSHENKO_REDUCED,
            },
            flags: 0,
            bending_stiffness_n_m2: config.bending_stiffness_n_m2,
            shear_stiffness_n: config.shear_stiffness_n,
            winkler_k_n_per_m2: config.winkler_k_n_per_m2,
            pasternak_g_n: config.pasternak_g_n,
            tolerance: config.tolerance,
            cg_max_iter: config.cg_max_iter,
            reserved_u32: 0,
            point_force_n: config.point_force_n,
            point_position_m: config.point_position_m,
            reserved: [0; 2],
        };
        let displacement_view = mutable_f64_view(&mut displacement_m, sys::SA_ABI_V1_2)?;
        let rotation_view = mutable_f64_view(&mut rotation_rad, sys::SA_ABI_V1_2)?;
        let mut raw_result = sys::SaTrackPointLoadResultV1 {
            abi_version: sys::SA_ABI_V1_2,
            struct_size: abi_size::<sys::SaTrackPointLoadResultV1>(),
            converged: 0,
            iterations: 0,
            residual_inf: 0.0,
            max_abs_displacement_m: 0.0,
            mid_displacement_m: 0.0,
            output_length: 0,
            execution_backend: 0,
            fallback_count: u32::MAX,
            reserved: u64::MAX,
        };
        let solve = self
            .table
            .track_point_load_solve
            .ok_or_else(invalid_table)?;
        let mut storage = [0_i8; ERROR_CAPACITY];
        let mut error = error_buffer(self.abi_version(), &mut storage);
        // SAFETY: all descriptors and caller-owned vectors are live, correctly aligned and
        // non-overlapping for the complete synchronous call. The C++ operation retains none.
        let status = unsafe {
            solve(
                &raw_config,
                &displacement_view,
                &rotation_view,
                &mut raw_result,
                &mut error,
            )
        };
        if status != sys::SA_OK {
            return Err(error_from_buffer(status, &storage));
        }
        let expected_length = usize_to_u64(count)?;
        if raw_result.abi_version != sys::SA_ABI_V1_2
            || raw_result.struct_size != abi_size::<sys::SaTrackPointLoadResultV1>()
            || raw_result.converged != 1
            || raw_result.output_length != expected_length
            || raw_result.execution_backend != sys::SA_EXECUTION_BACKEND_CPU
            || raw_result.fallback_count != 0
            || raw_result.reserved != 0
        {
            return Err(Error {
                code: sys::SA_ERR_INTERNAL,
                message: "native track result violated the v1.2 output contract".to_owned(),
            });
        }
        Ok(TrackPointLoadSolution {
            iterations: raw_result.iterations,
            residual_inf: raw_result.residual_inf,
            max_abs_displacement_m: raw_result.max_abs_displacement_m,
            mid_displacement_m: raw_result.mid_displacement_m,
            displacement_m,
            rotation_rad,
            execution_backend: raw_result.execution_backend,
            fallback_count: raw_result.fallback_count,
        })
    }

    /// Solve one bounded nonlinear static story-frame case in the C++ serial FP64 CPU backend.
    ///
    /// The operation borrows five packed input slices and writes one caller-owned displacement
    /// vector only after convergence. It retains no pointer and permits no backend fallback.
    ///
    /// # Errors
    ///
    /// Returns a stable ABI error for invalid inputs, allocation failure, output invariants or
    /// numerical nonconvergence.
    pub fn solve_nonlinear_static(
        self,
        config: &NonlinearStaticConfigV3,
        inputs: &StaticStoryInputsV3,
    ) -> Result<NonlinearStaticSolution, Error> {
        if self.abi_version() < sys::SA_ABI_V1_3 {
            return Err(Error {
                code: sys::SA_ERR_UNSUPPORTED,
                message: "nonlinear static CPU solve requires ABI v1.3".to_owned(),
            });
        }
        let count = nonlinear_static_count(config, inputs)?;

        let mut displacement_m = allocate_f64_output(count)?;
        let raw_config = sys::SaNonlinearStaticConfigV1 {
            abi_version: sys::SA_ABI_V1_3,
            struct_size: abi_size::<sys::SaNonlinearStaticConfigV1>(),
            story_count: config.story_count,
            max_iter: config.max_iter,
            tolerance: config.tolerance,
            hardening_ratio: config.hardening_ratio,
            line_search_decay: config.line_search_decay,
            line_search_min: config.line_search_min,
            pdelta_factor: config.pdelta_factor,
            flags: 0,
            reserved_u32: 0,
            reserved: [0; 2],
        };
        let stiffness_view = input_f64_view(&inputs.story_k_n_per_m, sys::SA_ABI_V1_3)?;
        let height_view = input_f64_view(&inputs.story_h_m, sys::SA_ABI_V1_3)?;
        let axial_view = input_f64_view(&inputs.story_axial_n, sys::SA_ABI_V1_3)?;
        let yield_drift_view = input_f64_view(&inputs.story_yield_drift_m, sys::SA_ABI_V1_3)?;
        let load_view = input_f64_view(&inputs.floor_load_n, sys::SA_ABI_V1_3)?;
        let displacement_view = mutable_f64_view(&mut displacement_m, sys::SA_ABI_V1_3)?;
        let mut raw_result = sys::SaNonlinearStaticResultV1 {
            abi_version: sys::SA_ABI_V1_3,
            struct_size: abi_size::<sys::SaNonlinearStaticResultV1>(),
            converged: 0,
            iterations: 0,
            residual_inf: 0.0,
            residual_l2: 0.0,
            max_abs_displacement_m: 0.0,
            top_displacement_m: 0.0,
            base_shear_kn: 0.0,
            plastic_story_count: 0,
            line_search_backtracks: 0,
            output_length: 0,
            execution_backend: 0,
            fallback_count: u32::MAX,
            reserved: u64::MAX,
        };
        let solve = self
            .table
            .nonlinear_static_solve
            .ok_or_else(invalid_table)?;
        let mut storage = [0_i8; ERROR_CAPACITY];
        let mut error = error_buffer(self.abi_version(), &mut storage);
        // SAFETY: every descriptor and borrowed slice is live, packed, aligned and disjoint from
        // the caller-owned output for the complete synchronous call. C++ retains none.
        let status = unsafe {
            solve(
                &raw_config,
                &stiffness_view,
                &height_view,
                &axial_view,
                &yield_drift_view,
                &load_view,
                &displacement_view,
                &mut raw_result,
                &mut error,
            )
        };
        if status != sys::SA_OK {
            return Err(error_from_buffer(status, &storage));
        }
        let expected_length = usize_to_u64(count)?;
        if raw_result.abi_version != sys::SA_ABI_V1_3
            || raw_result.struct_size != abi_size::<sys::SaNonlinearStaticResultV1>()
            || raw_result.converged != 1
            || raw_result.output_length != expected_length
            || raw_result.execution_backend != sys::SA_EXECUTION_BACKEND_CPU
            || raw_result.fallback_count != 0
            || raw_result.reserved != 0
        {
            return Err(Error {
                code: sys::SA_ERR_INTERNAL,
                message: "native nonlinear static result violated the v1.3 output contract"
                    .to_owned(),
            });
        }
        Ok(NonlinearStaticSolution {
            iterations: raw_result.iterations,
            residual_inf: raw_result.residual_inf,
            residual_l2: raw_result.residual_l2,
            max_abs_displacement_m: raw_result.max_abs_displacement_m,
            top_displacement_m: raw_result.top_displacement_m,
            base_shear_kn: raw_result.base_shear_kn,
            plastic_story_count: raw_result.plastic_story_count,
            line_search_backtracks: raw_result.line_search_backtracks,
            displacement_m,
            execution_backend: raw_result.execution_backend,
            fallback_count: raw_result.fallback_count,
        })
    }

    /// Solve one bounded nonlinear Newmark time-history story-frame case on the serial FP64 CPU.
    ///
    /// Eight packed inputs and eleven caller-owned output vectors remain borrowed only for the
    /// synchronous call. Numerical nonconvergence returns an error without exposing partial
    /// vectors. A deterministic physical collapse is a successful terminal result with
    /// `collapsed == true` and all response channels available through the collapse step.
    ///
    /// # Errors
    ///
    /// Returns a stable ABI error for invalid inputs, allocation failure, output invariants or
    /// numerical nonconvergence.
    pub fn solve_nonlinear_ndtha(
        self,
        config: &NonlinearNdthaConfigV3,
        inputs: &NdthaStoryInputsV3,
    ) -> Result<NonlinearNdthaSolution, Error> {
        if self.abi_version() < sys::SA_ABI_V1_4 {
            return Err(Error {
                code: sys::SA_ERR_UNSUPPORTED,
                message: "nonlinear NDTHA CPU solve requires ABI v1.4".to_owned(),
            });
        }
        let (story_count, step_count) = nonlinear_ndtha_counts(config, inputs)?;
        let raw_config = ndtha_config_descriptor(config, sys::SA_ABI_V1_4);
        let raw_inputs = ndtha_input_descriptor(inputs, sys::SA_ABI_V1_4)?;
        let mut arena = NdthaOutputArena::allocate(story_count, step_count)?;
        let raw_outputs = arena.descriptor(sys::SA_ABI_V1_4)?;
        let mut raw_result = ndtha_result_descriptor();
        let solve = self.table.nonlinear_ndtha_solve.ok_or_else(invalid_table)?;
        let mut storage = [0_i8; ERROR_CAPACITY];
        let mut error = error_buffer(self.abi_version(), &mut storage);
        // SAFETY: all descriptors, immutable inputs and disjoint caller-owned outputs remain live
        // for this synchronous call. The C++ operation retains no pointer.
        let status = unsafe {
            solve(
                &raw_config,
                &raw_inputs,
                &raw_outputs,
                &mut raw_result,
                &mut error,
            )
        };
        if status != sys::SA_OK {
            return Err(error_from_buffer(status, &storage));
        }
        arena.finish(raw_result, config)
    }

    /// Create the deterministic zero restart boundary for a bounded NDTHA problem.
    ///
    /// # Errors
    ///
    /// Returns a stable error for count/length mismatch or allocation failure.
    pub fn initial_nonlinear_ndtha_state(
        self,
        config: &NonlinearNdthaConfigV3,
        inputs: &NdthaStoryInputsV3,
    ) -> Result<NonlinearNdthaRestartState, Error> {
        if self.abi_version() < sys::SA_ABI_V1_5 {
            return Err(Error {
                code: sys::SA_ERR_UNSUPPORTED,
                message: "nonlinear NDTHA restart requires ABI v1.5".to_owned(),
            });
        }
        let (story_count, step_count) = nonlinear_ndtha_counts(config, inputs)?;
        Ok(NonlinearNdthaRestartState {
            next_step: 0,
            status: NonlinearNdthaExecutionStatus::Active,
            collapse_step: -1,
            collapse_time_s: 0.0,
            collapse_drift_ratio_pct: 0.0,
            collapse_top_displacement_m: 0.0,
            max_plastic_story_count: 0,
            max_drift_ratio_pct: 0.0,
            adaptive_iteration_sum: 0,
            total_line_search_backtracks: 0,
            displacement_m: allocate_f64_output(story_count)?,
            velocity_m_per_s: allocate_f64_output(story_count)?,
            acceleration_m_per_s2: allocate_f64_output(story_count)?,
            response: NdthaOutputArena::allocate(story_count, step_count)?.into_response(),
            execution_backend: sys::SA_EXECUTION_BACKEND_CPU,
            fallback_count: 0,
        })
    }

    /// Advance a caller-owned restart state by at most `step_budget` inter-step boundaries.
    ///
    /// This method deep-copies the supplied state before crossing the ABI, so any ABI rejection,
    /// allocation failure, or numerical nonconvergence leaves the Rust owner byte-for-byte
    /// unchanged.
    ///
    /// # Errors
    ///
    /// Returns stable validation, checkpoint-mismatch, nonconvergence, or internal errors.
    pub fn advance_nonlinear_ndtha(
        self,
        config: &NonlinearNdthaConfigV3,
        inputs: &NdthaStoryInputsV3,
        step_budget: u32,
        state: &mut NonlinearNdthaRestartState,
    ) -> Result<(), Error> {
        if self.abi_version() < sys::SA_ABI_V1_5 {
            return Err(Error {
                code: sys::SA_ERR_UNSUPPORTED,
                message: "nonlinear NDTHA restart requires ABI v1.5".to_owned(),
            });
        }
        let (story_count, step_count) = nonlinear_ndtha_counts(config, inputs)?;
        validate_restart_state(state, story_count, step_count)?;
        let raw_config = ndtha_config_descriptor(config, sys::SA_ABI_V1_5);
        let raw_inputs = ndtha_input_descriptor(inputs, sys::SA_ABI_V1_5)?;
        let mut arena = NdthaRestartArena::from_state(state, story_count, step_count)?;
        let mut raw_state = arena.descriptor(state)?;
        let advance = self
            .table
            .nonlinear_ndtha_advance
            .ok_or_else(invalid_table)?;
        let mut storage = [0_i8; ERROR_CAPACITY];
        let mut error = error_buffer(self.abi_version(), &mut storage);
        // SAFETY: all pointers refer to live, disjoint arena-owned buffers for this synchronous
        // call. The C++ boundary deep-copies before mutation and retains no pointer.
        let status = unsafe {
            advance(
                &raw_config,
                &raw_inputs,
                step_budget,
                &mut raw_state,
                &mut error,
            )
        };
        if status != sys::SA_OK {
            return Err(error_from_buffer(status, &storage));
        }
        let advanced = arena.finish(&raw_state, story_count, step_count)?;
        *state = advanced;
        Ok(())
    }
}

/// RAII owner of one deep-copied immutable C++ `ModelIR` handle.
pub struct ModelIr {
    api: Api,
    handle: NonNull<sys::SaModelIrHandleV1>,
}

// SAFETY: the C ABI contract declares immutable ModelIR handles movable across threads and the
// registry serializes lifetime operations. Safe methods expose immutable queries only.
unsafe impl Send for ModelIr {}
// SAFETY: immutable report/snapshot queries may execute concurrently and never mutate the model.
unsafe impl Sync for ModelIr {}

impl ModelIr {
    /// Read the exact deterministic C++ semantic validation report.
    ///
    /// # Errors
    ///
    /// Returns a stable ABI error if size or caller-owned output transfer fails.
    pub fn validation_report_json(&self) -> Result<String, Error> {
        let bytes = self.read_bytes(
            self.api
                .table
                .model_ir_validation_report_size
                .ok_or_else(invalid_table)?,
            self.api
                .table
                .model_ir_validation_report_write
                .ok_or_else(invalid_table)?,
        )?;
        String::from_utf8(bytes).map_err(|_| Error {
            code: sys::SA_ERR_INTERNAL,
            message: "native ModelIR validation report is not UTF-8".to_owned(),
        })
    }

    /// Read the exact caller-owned canonical `ModelIR` snapshot bytes.
    ///
    /// # Errors
    ///
    /// Returns a stable ABI error if size or output transfer fails.
    pub fn snapshot_bytes(&self) -> Result<Vec<u8>, Error> {
        self.read_bytes(
            self.api
                .table
                .model_ir_snapshot_size
                .ok_or_else(invalid_table)?,
            self.api
                .table
                .model_ir_snapshot_write
                .ok_or_else(invalid_table)?,
        )
    }

    fn read_bytes(
        &self,
        size_operation: unsafe extern "C" fn(
            *const sys::SaModelIrHandleV1,
            *mut u64,
            *mut sys::SaErrorBufferV1,
        ) -> sys::SaStatusCodeV1,
        write_operation: unsafe extern "C" fn(
            *const sys::SaModelIrHandleV1,
            *mut u8,
            u64,
            *mut u64,
            *mut sys::SaErrorBufferV1,
        ) -> sys::SaStatusCodeV1,
    ) -> Result<Vec<u8>, Error> {
        let mut required = 0_u64;
        let mut storage = [0_i8; ERROR_CAPACITY];
        let mut error = error_buffer(self.api.abi_version(), &mut storage);
        // SAFETY: the live RAII handle and caller-owned output scalar remain valid for the call.
        let status = unsafe { size_operation(self.handle.as_ptr(), &mut required, &mut error) };
        if status != sys::SA_OK {
            return Err(error_from_buffer(status, &storage));
        }
        let capacity = usize::try_from(required).map_err(|_| Error {
            code: sys::SA_ERR_INTERNAL,
            message: "native ModelIR output exceeds the Rust address space".to_owned(),
        })?;
        let mut output = vec![0_u8; capacity];
        let output_pointer = if output.is_empty() {
            ptr::null_mut()
        } else {
            output.as_mut_ptr()
        };
        let mut written = 0_u64;
        let mut storage = [0_i8; ERROR_CAPACITY];
        let mut error = error_buffer(self.api.abi_version(), &mut storage);
        // SAFETY: output owns `capacity` writable bytes and neither it nor the live handle moves
        // during the call. The operation writes only on complete success.
        let status = unsafe {
            write_operation(
                self.handle.as_ptr(),
                output_pointer,
                required,
                &mut written,
                &mut error,
            )
        };
        if status != sys::SA_OK {
            return Err(error_from_buffer(status, &storage));
        }
        if written != required {
            return Err(Error {
                code: sys::SA_ERR_INTERNAL,
                message: "native ModelIR output size changed during immutable transfer".to_owned(),
            });
        }
        Ok(output)
    }
}

impl Drop for ModelIr {
    fn drop(&mut self) {
        if let Some(destroy) = self.api.table.model_ir_destroy {
            // SAFETY: this is the unique RAII destruction point for the live opaque handle. Arc
            // ownership prevents Drop while any safe immutable query still borrows the value.
            let _status = unsafe { destroy(self.handle.as_ptr(), ptr::null_mut()) };
        }
    }
}

fn ndtha_config_descriptor(
    config: &NonlinearNdthaConfigV3,
    abi_version: u32,
) -> sys::SaNonlinearNdthaConfigV1 {
    sys::SaNonlinearNdthaConfigV1 {
        abi_version,
        struct_size: abi_size::<sys::SaNonlinearNdthaConfigV1>(),
        story_count: config.story_count,
        step_count: config.step_count,
        dt_s: config.dt_s,
        newmark_beta: config.newmark_beta,
        newmark_gamma: config.newmark_gamma,
        tolerance: config.tolerance,
        max_step_iterations: config.max_step_iterations,
        reserved_iteration_u32: 0,
        adaptive_load_decay: config.adaptive_load_decay,
        damping_force_cap_ratio: config.damping_force_cap_ratio,
        newton_max_iter: config.newton_max_iter,
        reserved_newton_u32: 0,
        line_search_decay: config.line_search_decay,
        line_search_min: config.line_search_min,
        hardening_ratio: config.hardening_ratio,
        pdelta_factor: config.pdelta_factor,
        collapse_drift_threshold_pct: config.collapse_drift_threshold_pct,
        flags: 0,
        reserved_u32: 0,
        reserved: [0; 2],
    }
}

fn ndtha_input_descriptor(
    inputs: &NdthaStoryInputsV3,
    abi_version: u32,
) -> Result<sys::SaNonlinearNdthaInputsV1, Error> {
    Ok(sys::SaNonlinearNdthaInputsV1 {
        abi_version,
        struct_size: abi_size::<sys::SaNonlinearNdthaInputsV1>(),
        story_stiffness_n_per_m: input_f64_view(&inputs.story_k_n_per_m, abi_version)?,
        story_height_m: input_f64_view(&inputs.story_h_m, abi_version)?,
        story_axial_n: input_f64_view(&inputs.story_axial_n, abi_version)?,
        story_yield_drift_m: input_f64_view(&inputs.story_yield_drift_m, abi_version)?,
        story_mass_kg: input_f64_view(&inputs.story_mass_kg, abi_version)?,
        story_damping_n_s_per_m: input_f64_view(&inputs.story_damping_n_s_per_m, abi_version)?,
        floor_load_base_n: input_f64_view(&inputs.floor_load_base_n, abi_version)?,
        acceleration_g: input_f64_view(&inputs.ag_g, abi_version)?,
        reserved: [0; 2],
    })
}

fn ndtha_result_descriptor() -> sys::SaNonlinearNdthaResultV1 {
    sys::SaNonlinearNdthaResultV1 {
        abi_version: sys::SA_ABI_V1_4,
        struct_size: abi_size::<sys::SaNonlinearNdthaResultV1>(),
        converged_all_steps: 0,
        collapsed: 0,
        collapse_step: i32::MIN,
        step_count_completed: 0,
        collapse_time_s: f64::NAN,
        collapse_drift_ratio_pct: f64::NAN,
        collapse_top_displacement_m: f64::NAN,
        max_drift_ratio_pct: f64::NAN,
        avg_step_iterations: f64::NAN,
        residual_top_displacement_m: f64::NAN,
        residual_drift_ratio_pct: f64::NAN,
        max_plastic_story_count: u32::MAX,
        total_line_search_backtracks: u32::MAX,
        output_story_count: 0,
        output_step_count: 0,
        execution_backend: 0,
        fallback_count: u32::MAX,
        reserved: [u64::MAX; 2],
    }
}

fn validate_ndtha_result(
    raw: &sys::SaNonlinearNdthaResultV1,
    config: &NonlinearNdthaConfigV3,
    step_converged: &[u8],
) -> Result<(), Error> {
    let terminal_flags_valid = raw.converged_all_steps <= 1
        && raw.collapsed <= 1
        && raw.converged_all_steps + raw.collapsed == 1;
    let completion_valid = if raw.collapsed == 1 {
        raw.collapse_step >= 0
            && u32::try_from(raw.collapse_step).is_ok_and(|step| {
                step < raw.step_count_completed && raw.step_count_completed <= config.step_count
            })
    } else {
        raw.collapse_step == -1 && raw.step_count_completed == config.step_count
    };
    let result_valid = raw.abi_version == sys::SA_ABI_V1_4
        && raw.struct_size == abi_size::<sys::SaNonlinearNdthaResultV1>()
        && terminal_flags_valid
        && completion_valid
        && raw.output_story_count == u64::from(config.story_count)
        && raw.output_step_count == u64::from(config.step_count)
        && raw.execution_backend == sys::SA_EXECUTION_BACKEND_CPU
        && raw.fallback_count == 0
        && raw.reserved == [0; 2]
        && step_converged.iter().all(|value| *value <= 1);
    if result_valid {
        Ok(())
    } else {
        Err(Error {
            code: sys::SA_ERR_INTERNAL,
            message: "native nonlinear NDTHA result violated the v1.4 output contract".to_owned(),
        })
    }
}

fn allocation_error(label: &str) -> Error {
    Error {
        code: sys::SA_ERR_INTERNAL,
        message: format!("native {label} allocation failed"),
    }
}

fn try_clone_slice<T: Clone>(values: &[T], label: &str) -> Result<Vec<T>, Error> {
    let mut output = Vec::new();
    output
        .try_reserve_exact(values.len())
        .map_err(|_| allocation_error(label))?;
    output.extend_from_slice(values);
    Ok(output)
}

fn validate_response_lengths(
    response: &NonlinearNdthaResponse,
    story_count: usize,
    step_count: usize,
) -> Result<(), Error> {
    let valid = response.top_displacement_m.len() == step_count
        && response.drift_ratio_pct.len() == step_count
        && response.base_shear_kn.len() == step_count
        && response.core_drift_pct.len() == step_count
        && response.core_shear_kn.len() == step_count
        && response.step_converged.len() == step_count
        && response.step_iterations.len() == step_count
        && response.step_plastic_story_count.len() == step_count
        && response.step_residual_inf.len() == step_count
        && response.story_drift_envelope_pct.len() == story_count
        && response.final_story_drift_pct.len() == story_count;
    if valid {
        Ok(())
    } else {
        Err(Error {
            code: sys::SA_ERR_CHECKPOINT_MISMATCH,
            message: "nonlinear NDTHA restart response lengths do not match config".to_owned(),
        })
    }
}

fn validate_restart_state(
    state: &NonlinearNdthaRestartState,
    story_count: usize,
    step_count: usize,
) -> Result<(), Error> {
    validate_response_lengths(&state.response, story_count, step_count)?;
    let lengths_valid = state.displacement_m.len() == story_count
        && state.velocity_m_per_s.len() == story_count
        && state.acceleration_m_per_s2.len() == story_count;
    let metadata_valid = state.execution_backend == sys::SA_EXECUTION_BACKEND_CPU
        && state.fallback_count == 0
        && usize::try_from(state.next_step).is_ok_and(|step| step <= step_count);
    if lengths_valid && metadata_valid {
        Ok(())
    } else {
        Err(Error {
            code: sys::SA_ERR_CHECKPOINT_MISMATCH,
            message: "nonlinear NDTHA restart state does not match config or backend".to_owned(),
        })
    }
}

const fn execution_status_to_raw(status: NonlinearNdthaExecutionStatus) -> u32 {
    match status {
        NonlinearNdthaExecutionStatus::Active => sys::SA_NONLINEAR_NDTHA_EXECUTION_ACTIVE,
        NonlinearNdthaExecutionStatus::Completed => sys::SA_NONLINEAR_NDTHA_EXECUTION_COMPLETED,
        NonlinearNdthaExecutionStatus::Collapsed => sys::SA_NONLINEAR_NDTHA_EXECUTION_COLLAPSED,
        NonlinearNdthaExecutionStatus::Nonconverged => {
            sys::SA_NONLINEAR_NDTHA_EXECUTION_NONCONVERGED
        }
    }
}

fn execution_status_from_raw(raw: u32) -> Result<NonlinearNdthaExecutionStatus, Error> {
    match raw {
        sys::SA_NONLINEAR_NDTHA_EXECUTION_ACTIVE => Ok(NonlinearNdthaExecutionStatus::Active),
        sys::SA_NONLINEAR_NDTHA_EXECUTION_COMPLETED => Ok(NonlinearNdthaExecutionStatus::Completed),
        sys::SA_NONLINEAR_NDTHA_EXECUTION_COLLAPSED => Ok(NonlinearNdthaExecutionStatus::Collapsed),
        sys::SA_NONLINEAR_NDTHA_EXECUTION_NONCONVERGED => {
            Ok(NonlinearNdthaExecutionStatus::Nonconverged)
        }
        _ => Err(Error {
            code: sys::SA_ERR_INTERNAL,
            message: "native nonlinear NDTHA restart returned an invalid status".to_owned(),
        }),
    }
}

fn validate_table(table: &sys::SaApiV1, requested: u32) -> Result<(), Error> {
    let base_valid = table.abi_version == requested
        && table.struct_size as usize >= size_of::<sys::SaApiV1>()
        && table.validate_buffer_view.is_some()
        && table.capabilities & sys::SA_CAPABILITY_BUFFER_VALIDATION != 0
        && table.reserved.iter().all(|value| value.is_null());
    let model_slots = [
        table.model_ir_create.is_some(),
        table.model_ir_destroy.is_some(),
        table.model_ir_validation_report_size.is_some(),
        table.model_ir_validation_report_write.is_some(),
        table.model_ir_snapshot_size.is_some(),
        table.model_ir_snapshot_write.is_some(),
    ];
    let track_slot = table.track_point_load_solve.is_some();
    let nonlinear_static_slot = table.nonlinear_static_solve.is_some();
    let nonlinear_ndtha_slot = table.nonlinear_ndtha_solve.is_some();
    let nonlinear_ndtha_restart_slot = table.nonlinear_ndtha_advance.is_some();
    let version_valid = if requested == sys::SA_ABI_V1_0 {
        model_slots.iter().all(|present| !present)
            && !track_slot
            && !nonlinear_static_slot
            && !nonlinear_ndtha_slot
            && !nonlinear_ndtha_restart_slot
            && table.capabilities == sys::SA_CAPABILITY_BUFFER_VALIDATION
    } else if requested == sys::SA_ABI_V1_1 {
        model_slots.iter().all(|present| *present)
            && !track_slot
            && !nonlinear_static_slot
            && !nonlinear_ndtha_slot
            && !nonlinear_ndtha_restart_slot
            && table.capabilities & sys::SA_CAPABILITY_MODEL_IR_V2_TYPED != 0
            && table.capabilities & sys::SA_CAPABILITY_MODEL_IR_V2_SNAPSHOT != 0
            && table.capabilities & sys::SA_CAPABILITY_TRACK_POINT_LOAD_CPU == 0
            && table.capabilities & sys::SA_CAPABILITY_NONLINEAR_STATIC_CPU == 0
            && table.capabilities & sys::SA_CAPABILITY_NONLINEAR_NDTHA_CPU == 0
    } else if requested == sys::SA_ABI_V1_2 {
        model_slots.iter().all(|present| *present)
            && track_slot
            && !nonlinear_static_slot
            && !nonlinear_ndtha_slot
            && !nonlinear_ndtha_restart_slot
            && table.capabilities & sys::SA_CAPABILITY_MODEL_IR_V2_TYPED != 0
            && table.capabilities & sys::SA_CAPABILITY_MODEL_IR_V2_SNAPSHOT != 0
            && table.capabilities & sys::SA_CAPABILITY_TRACK_POINT_LOAD_CPU != 0
            && table.capabilities & sys::SA_CAPABILITY_NONLINEAR_STATIC_CPU == 0
            && table.capabilities & sys::SA_CAPABILITY_NONLINEAR_NDTHA_CPU == 0
    } else if requested == sys::SA_ABI_V1_3 {
        model_slots.iter().all(|present| *present)
            && track_slot
            && nonlinear_static_slot
            && !nonlinear_ndtha_slot
            && !nonlinear_ndtha_restart_slot
            && table.capabilities & sys::SA_CAPABILITY_MODEL_IR_V2_TYPED != 0
            && table.capabilities & sys::SA_CAPABILITY_MODEL_IR_V2_SNAPSHOT != 0
            && table.capabilities & sys::SA_CAPABILITY_TRACK_POINT_LOAD_CPU != 0
            && table.capabilities & sys::SA_CAPABILITY_NONLINEAR_STATIC_CPU != 0
            && table.capabilities & sys::SA_CAPABILITY_NONLINEAR_NDTHA_CPU == 0
    } else if requested == sys::SA_ABI_V1_4 {
        model_slots.iter().all(|present| *present)
            && track_slot
            && nonlinear_static_slot
            && nonlinear_ndtha_slot
            && !nonlinear_ndtha_restart_slot
            && table.capabilities & sys::SA_CAPABILITY_MODEL_IR_V2_TYPED != 0
            && table.capabilities & sys::SA_CAPABILITY_MODEL_IR_V2_SNAPSHOT != 0
            && table.capabilities & sys::SA_CAPABILITY_TRACK_POINT_LOAD_CPU != 0
            && table.capabilities & sys::SA_CAPABILITY_NONLINEAR_STATIC_CPU != 0
            && table.capabilities & sys::SA_CAPABILITY_NONLINEAR_NDTHA_CPU != 0
            && table.capabilities & sys::SA_CAPABILITY_NONLINEAR_NDTHA_RESTART_CPU == 0
    } else if requested == sys::SA_ABI_V1_5 {
        model_slots.iter().all(|present| *present)
            && track_slot
            && nonlinear_static_slot
            && nonlinear_ndtha_slot
            && nonlinear_ndtha_restart_slot
            && table.capabilities & sys::SA_CAPABILITY_MODEL_IR_V2_TYPED != 0
            && table.capabilities & sys::SA_CAPABILITY_MODEL_IR_V2_SNAPSHOT != 0
            && table.capabilities & sys::SA_CAPABILITY_TRACK_POINT_LOAD_CPU != 0
            && table.capabilities & sys::SA_CAPABILITY_NONLINEAR_STATIC_CPU != 0
            && table.capabilities & sys::SA_CAPABILITY_NONLINEAR_NDTHA_CPU != 0
            && table.capabilities & sys::SA_CAPABILITY_NONLINEAR_NDTHA_RESTART_CPU != 0
    } else {
        false
    };
    if base_valid && version_valid {
        Ok(())
    } else {
        Err(invalid_table())
    }
}

fn allocate_f64_output(length: usize) -> Result<Vec<f64>, Error> {
    let mut output = Vec::new();
    output.try_reserve_exact(length).map_err(|_| Error {
        code: sys::SA_ERR_INTERNAL,
        message: "native FP64 output allocation failed".to_owned(),
    })?;
    output.resize(length, 0.0);
    Ok(output)
}

fn allocate_u8_output(length: usize) -> Result<Vec<u8>, Error> {
    let mut output = Vec::new();
    output.try_reserve_exact(length).map_err(|_| Error {
        code: sys::SA_ERR_INTERNAL,
        message: "native U8 output allocation failed".to_owned(),
    })?;
    output.resize(length, 0);
    Ok(output)
}

fn allocate_u32_output(length: usize) -> Result<Vec<u32>, Error> {
    let mut output = Vec::new();
    output.try_reserve_exact(length).map_err(|_| Error {
        code: sys::SA_ERR_INTERNAL,
        message: "native U32 output allocation failed".to_owned(),
    })?;
    output.resize(length, 0);
    Ok(output)
}

fn nonlinear_static_count(
    config: &NonlinearStaticConfigV3,
    inputs: &StaticStoryInputsV3,
) -> Result<usize, Error> {
    let count = usize::try_from(config.story_count).map_err(|_| Error {
        code: sys::SA_ERR_INVALID_ARGUMENT,
        message: "nonlinear static story_count exceeds the Rust address space".to_owned(),
    })?;
    if count == 0 || config.story_count > sys::SA_NONLINEAR_STATIC_MAX_STORY_COUNT {
        return Err(Error {
            code: sys::SA_ERR_INVALID_ARGUMENT,
            message: "nonlinear static story_count is outside the bounded product range".to_owned(),
        });
    }
    let input_lengths = [
        inputs.story_k_n_per_m.len(),
        inputs.story_h_m.len(),
        inputs.story_axial_n.len(),
        inputs.story_yield_drift_m.len(),
        inputs.floor_load_n.len(),
    ];
    if input_lengths.iter().any(|length| *length != count) {
        return Err(Error {
            code: sys::SA_ERR_INVALID_ARGUMENT,
            message: "nonlinear static input lengths do not match story_count".to_owned(),
        });
    }
    Ok(count)
}

fn nonlinear_ndtha_counts(
    config: &NonlinearNdthaConfigV3,
    inputs: &NdthaStoryInputsV3,
) -> Result<(usize, usize), Error> {
    let story_count = usize::try_from(config.story_count).map_err(|_| Error {
        code: sys::SA_ERR_INVALID_ARGUMENT,
        message: "nonlinear NDTHA story_count exceeds the Rust address space".to_owned(),
    })?;
    let step_count = usize::try_from(config.step_count).map_err(|_| Error {
        code: sys::SA_ERR_INVALID_ARGUMENT,
        message: "nonlinear NDTHA step_count exceeds the Rust address space".to_owned(),
    })?;
    if story_count == 0 || config.story_count > sys::SA_NONLINEAR_NDTHA_MAX_STORY_COUNT {
        return Err(Error {
            code: sys::SA_ERR_INVALID_ARGUMENT,
            message: "nonlinear NDTHA story_count is outside the bounded product range".to_owned(),
        });
    }
    if step_count == 0 || config.step_count > sys::SA_NONLINEAR_NDTHA_MAX_STEP_COUNT {
        return Err(Error {
            code: sys::SA_ERR_INVALID_ARGUMENT,
            message: "nonlinear NDTHA step_count is outside the bounded product range".to_owned(),
        });
    }
    let story_lengths = [
        inputs.story_k_n_per_m.len(),
        inputs.story_h_m.len(),
        inputs.story_axial_n.len(),
        inputs.story_yield_drift_m.len(),
        inputs.story_mass_kg.len(),
        inputs.story_damping_n_s_per_m.len(),
        inputs.floor_load_base_n.len(),
    ];
    if story_lengths.iter().any(|length| *length != story_count) || inputs.ag_g.len() != step_count
    {
        return Err(Error {
            code: sys::SA_ERR_INVALID_ARGUMENT,
            message: "nonlinear NDTHA input lengths do not match config counts".to_owned(),
        });
    }
    Ok((story_count, step_count))
}

fn input_f64_view(values: &[f64], abi_version: u32) -> Result<sys::SaBufferViewV1, Error> {
    Ok(sys::SaBufferViewV1 {
        abi_version,
        struct_size: abi_size::<sys::SaBufferViewV1>(),
        data: values.as_ptr().cast::<c_void>(),
        length: usize_to_u64(values.len())?,
        stride_bytes: usize_to_u64(size_of::<f64>())?,
        element_type: sys::SA_ELEMENT_TYPE_F64,
        memory_space: sys::SA_MEMORY_SPACE_HOST,
        device_id: -1,
        flags: 0,
    })
}

fn mutable_f64_view(values: &mut [f64], abi_version: u32) -> Result<sys::SaMutBufferViewV1, Error> {
    Ok(sys::SaMutBufferViewV1 {
        abi_version,
        struct_size: abi_size::<sys::SaMutBufferViewV1>(),
        data: values.as_mut_ptr().cast::<c_void>(),
        length: usize_to_u64(values.len())?,
        stride_bytes: usize_to_u64(size_of::<f64>())?,
        element_type: sys::SA_ELEMENT_TYPE_F64,
        memory_space: sys::SA_MEMORY_SPACE_HOST,
        device_id: -1,
        flags: 0,
    })
}

fn mutable_u8_view(values: &mut [u8], abi_version: u32) -> Result<sys::SaMutBufferViewV1, Error> {
    Ok(sys::SaMutBufferViewV1 {
        abi_version,
        struct_size: abi_size::<sys::SaMutBufferViewV1>(),
        data: values.as_mut_ptr().cast::<c_void>(),
        length: usize_to_u64(values.len())?,
        stride_bytes: usize_to_u64(size_of::<u8>())?,
        element_type: sys::SA_ELEMENT_TYPE_U8,
        memory_space: sys::SA_MEMORY_SPACE_HOST,
        device_id: -1,
        flags: 0,
    })
}

fn mutable_u32_view(values: &mut [u32], abi_version: u32) -> Result<sys::SaMutBufferViewV1, Error> {
    Ok(sys::SaMutBufferViewV1 {
        abi_version,
        struct_size: abi_size::<sys::SaMutBufferViewV1>(),
        data: values.as_mut_ptr().cast::<c_void>(),
        length: usize_to_u64(values.len())?,
        stride_bytes: usize_to_u64(size_of::<u32>())?,
        element_type: sys::SA_ELEMENT_TYPE_U32,
        memory_space: sys::SA_MEMORY_SPACE_HOST,
        device_id: -1,
        flags: 0,
    })
}

fn verify_round_trip(
    original: &ModelIrV2Document,
    snapshot: &ModelIrV2Document,
    snapshot_bytes: &[u8],
    report: &ModelIrValidationReport,
) -> Result<(), Error> {
    let identity_matches = snapshot_bytes == original.canonical_bytes()
        && snapshot.canonical_bytes() == original.canonical_bytes()
        && snapshot.content_hash() == original.content_hash()
        && snapshot.semantic_hash() == original.semantic_hash()
        && snapshot.provenance_hash() == original.provenance_hash()
        && report.model_id == original.model_id()
        && report.content_hash == original.content_hash()
        && report.semantic_hash == original.semantic_hash()
        && report.provenance_hash == original.provenance_hash()
        && report.abi_version == sys::SA_ABI_V1_1
        && report.schema_version == "structural-model-ir-cpp-validation.v1";
    if identity_matches {
        Ok(())
    } else {
        Err(Error {
            code: sys::SA_ERR_INTERNAL,
            message: "native ModelIR round-trip byte or hash identity mismatch".to_owned(),
        })
    }
}

fn abi_size<T>() -> u32 {
    u32::try_from(size_of::<T>()).unwrap_or(u32::MAX)
}

fn usize_to_u64(value: usize) -> Result<u64, Error> {
    u64::try_from(value).map_err(|_| Error {
        code: sys::SA_ERR_INVALID_ARGUMENT,
        message: "Rust slice length exceeds the C ABI range".to_owned(),
    })
}

fn invalid_table() -> Error {
    Error {
        code: sys::SA_ERR_INTERNAL,
        message: "invalid API table returned by native library".to_owned(),
    }
}

fn error_buffer(abi_version: u32, storage: &mut [c_char; ERROR_CAPACITY]) -> sys::SaErrorBufferV1 {
    sys::SaErrorBufferV1 {
        abi_version,
        struct_size: abi_size::<sys::SaErrorBufferV1>(),
        data: storage.as_mut_ptr(),
        capacity: u64::try_from(storage.len()).unwrap_or(u64::MAX),
        required: 0,
    }
}

fn status_result(code: sys::SaStatusCodeV1, storage: &[c_char]) -> Result<(), Error> {
    if code == sys::SA_OK {
        Ok(())
    } else {
        Err(error_from_buffer(code, storage))
    }
}

fn error_from_buffer(code: sys::SaStatusCodeV1, storage: &[c_char]) -> Error {
    let length = storage
        .iter()
        .position(|byte| *byte == 0)
        .unwrap_or(storage.len());
    let bytes: Vec<u8> = storage[..length]
        .iter()
        .map(|byte| byte.to_ne_bytes()[0])
        .collect();
    Error {
        code,
        message: String::from_utf8_lossy(&bytes).into_owned(),
    }
}

#[cfg(test)]
mod tests {
    use super::Api;
    use std::path::{Path, PathBuf};
    use std::sync::Arc;
    use std::thread;
    use structural_contracts::model_ir::parse_model_ir_v2;
    use structural_ffi_sys::{
        SA_ABI_V1_1, SA_ABI_V1_2, SA_ABI_V1_3, SA_ABI_V1_4, SA_ABI_V1_5,
        SA_CAPABILITY_BUFFER_VALIDATION, SA_CAPABILITY_MODEL_IR_V2_SNAPSHOT,
        SA_CAPABILITY_MODEL_IR_V2_TYPED, SA_CAPABILITY_NONLINEAR_NDTHA_CPU,
        SA_CAPABILITY_NONLINEAR_NDTHA_RESTART_CPU, SA_CAPABILITY_NONLINEAR_STATIC_CPU,
        SA_CAPABILITY_TRACK_POINT_LOAD_CPU, SA_ERR_INVALID_ARGUMENT, SA_ERR_UNSUPPORTED, SA_OK,
    };

    fn repository_root() -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../..")
            .canonicalize()
            .expect("repository root")
    }

    fn fixture() -> structural_contracts::model_ir::ModelIrV2Document {
        let bytes = std::fs::read(
            repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"),
        )
        .expect("fixture bytes");
        parse_model_ir_v2(&bytes).expect("schema-valid fixture")
    }

    #[test]
    fn v1_0_compatibility_table_stays_prefix_only() {
        let api = Api::load().expect("v1.0 API loads");
        assert_eq!(api.capabilities(), SA_CAPABILITY_BUFFER_VALIDATION);
        assert_eq!(api.validate_f64_slice(&[1.0, 2.0, 3.0]), Ok(()));
        assert_eq!(api.validate_f64_slice(&[]), Ok(()));
        assert_eq!(SA_OK, 0);
    }

    #[test]
    fn v1_1_round_trip_is_byte_and_hash_identical() {
        let api = Api::load_model_ir().expect("v1.1 API loads");
        assert_eq!(api.abi_version(), SA_ABI_V1_1);
        assert_eq!(
            api.capabilities(),
            SA_CAPABILITY_BUFFER_VALIDATION
                | SA_CAPABILITY_MODEL_IR_V2_TYPED
                | SA_CAPABILITY_MODEL_IR_V2_SNAPSHOT
        );
        let document = fixture();
        let validated = api
            .validate_model_ir(&document)
            .expect("complete native round-trip");
        assert!(validated.report.contract_valid);
        assert!(validated.report.analysis_ready);
        assert_eq!(
            validated.snapshot.canonical_bytes(),
            document.canonical_bytes()
        );
    }

    #[test]
    fn v1_2_table_adds_only_the_bounded_track_cpu_capability() {
        let api = Api::load_track_point_load().expect("v1.2 API loads");
        assert_eq!(api.abi_version(), SA_ABI_V1_2);
        assert_eq!(
            api.capabilities(),
            SA_CAPABILITY_BUFFER_VALIDATION
                | SA_CAPABILITY_MODEL_IR_V2_TYPED
                | SA_CAPABILITY_MODEL_IR_V2_SNAPSHOT
                | SA_CAPABILITY_TRACK_POINT_LOAD_CPU
        );
    }

    #[test]
    fn v1_3_table_adds_only_the_bounded_nonlinear_static_cpu_capability() {
        let api = Api::load_nonlinear_static().expect("v1.3 API loads");
        assert_eq!(api.abi_version(), SA_ABI_V1_3);
        assert_eq!(
            api.capabilities(),
            SA_CAPABILITY_BUFFER_VALIDATION
                | SA_CAPABILITY_MODEL_IR_V2_TYPED
                | SA_CAPABILITY_MODEL_IR_V2_SNAPSHOT
                | SA_CAPABILITY_TRACK_POINT_LOAD_CPU
                | SA_CAPABILITY_NONLINEAR_STATIC_CPU
        );
    }

    #[test]
    fn v1_4_table_adds_only_the_bounded_nonlinear_ndtha_cpu_capability() {
        let api = Api::load_nonlinear_ndtha().expect("v1.4 API loads");
        assert_eq!(api.abi_version(), SA_ABI_V1_4);
        assert_eq!(
            api.capabilities(),
            SA_CAPABILITY_BUFFER_VALIDATION
                | SA_CAPABILITY_MODEL_IR_V2_TYPED
                | SA_CAPABILITY_MODEL_IR_V2_SNAPSHOT
                | SA_CAPABILITY_TRACK_POINT_LOAD_CPU
                | SA_CAPABILITY_NONLINEAR_STATIC_CPU
                | SA_CAPABILITY_NONLINEAR_NDTHA_CPU
        );
    }

    #[test]
    fn v1_5_table_adds_only_the_nonlinear_ndtha_restart_capability() {
        let api = Api::load_nonlinear_ndtha_restart().expect("v1.5 API loads");
        assert_eq!(api.abi_version(), SA_ABI_V1_5);
        assert_eq!(
            api.capabilities(),
            SA_CAPABILITY_BUFFER_VALIDATION
                | SA_CAPABILITY_MODEL_IR_V2_TYPED
                | SA_CAPABILITY_MODEL_IR_V2_SNAPSHOT
                | SA_CAPABILITY_TRACK_POINT_LOAD_CPU
                | SA_CAPABILITY_NONLINEAR_STATIC_CPU
                | SA_CAPABILITY_NONLINEAR_NDTHA_CPU
                | SA_CAPABILITY_NONLINEAR_NDTHA_RESTART_CPU
        );
    }

    #[test]
    fn v1_0_rejects_typed_use_and_raii_drop_destroys_exactly_once() {
        let document = fixture();
        let compatibility = Api::load().expect("v1.0 API");
        let unsupported = compatibility
            .create_model_ir(&document)
            .err()
            .expect("typed use requires v1.1");
        assert_eq!(unsupported.code, SA_ERR_UNSUPPORTED);

        let api = Api::load_model_ir().expect("v1.1 API");
        let model = api.create_model_ir(&document).expect("native model");
        let raw = model.handle.as_ptr();
        drop(model);
        let destroy = api.table.model_ir_destroy.expect("destroy operation");
        // SAFETY: this test intentionally probes the stale raw value after the safe RAII owner
        // has destroyed it; the native registry validates the address without dereferencing it.
        let status = unsafe { destroy(raw, core::ptr::null_mut()) };
        assert_eq!(status, SA_ERR_INVALID_ARGUMENT);
    }

    #[test]
    fn immutable_model_queries_are_safe_for_concurrent_reads() {
        let api = Api::load_model_ir().expect("v1.1 API loads");
        let document = fixture();
        let model = Arc::new(api.create_model_ir(&document).expect("native model"));
        let threads: Vec<_> = (0..8)
            .map(|_| {
                let model = Arc::clone(&model);
                let expected = document.canonical_bytes().to_vec();
                thread::spawn(move || {
                    for _ in 0..128 {
                        assert_eq!(model.snapshot_bytes().expect("snapshot"), expected);
                        assert!(model
                            .validation_report_json()
                            .expect("report")
                            .contains("\"contract_valid\":true"));
                    }
                })
            })
            .collect();
        for worker in threads {
            worker.join().expect("worker does not panic");
        }
    }
}
