//! Safe entry-table and immutable `ModelIR` ownership for C ABI v1.

mod descriptor;

use core::ffi::{c_char, c_void};
use core::fmt;
use core::mem::size_of;
use core::ptr::{self, NonNull};

use serde::{Deserialize, Serialize};
use structural_contracts::legacy_runtime::{
    NonlinearStaticConfigV3, StaticStoryInputsV3, TrackConfigV3, TrackSupportType, TrackTheory,
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
    let version_valid = if requested == sys::SA_ABI_V1_0 {
        model_slots.iter().all(|present| !present)
            && !track_slot
            && !nonlinear_static_slot
            && table.capabilities == sys::SA_CAPABILITY_BUFFER_VALIDATION
    } else if requested == sys::SA_ABI_V1_1 {
        model_slots.iter().all(|present| *present)
            && !track_slot
            && !nonlinear_static_slot
            && table.capabilities & sys::SA_CAPABILITY_MODEL_IR_V2_TYPED != 0
            && table.capabilities & sys::SA_CAPABILITY_MODEL_IR_V2_SNAPSHOT != 0
            && table.capabilities & sys::SA_CAPABILITY_TRACK_POINT_LOAD_CPU == 0
            && table.capabilities & sys::SA_CAPABILITY_NONLINEAR_STATIC_CPU == 0
    } else if requested == sys::SA_ABI_V1_2 {
        model_slots.iter().all(|present| *present)
            && track_slot
            && !nonlinear_static_slot
            && table.capabilities & sys::SA_CAPABILITY_MODEL_IR_V2_TYPED != 0
            && table.capabilities & sys::SA_CAPABILITY_MODEL_IR_V2_SNAPSHOT != 0
            && table.capabilities & sys::SA_CAPABILITY_TRACK_POINT_LOAD_CPU != 0
            && table.capabilities & sys::SA_CAPABILITY_NONLINEAR_STATIC_CPU == 0
    } else if requested == sys::SA_ABI_V1_3 {
        model_slots.iter().all(|present| *present)
            && track_slot
            && nonlinear_static_slot
            && table.capabilities & sys::SA_CAPABILITY_MODEL_IR_V2_TYPED != 0
            && table.capabilities & sys::SA_CAPABILITY_MODEL_IR_V2_SNAPSHOT != 0
            && table.capabilities & sys::SA_CAPABILITY_TRACK_POINT_LOAD_CPU != 0
            && table.capabilities & sys::SA_CAPABILITY_NONLINEAR_STATIC_CPU != 0
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
        SA_ABI_V1_1, SA_ABI_V1_2, SA_ABI_V1_3, SA_CAPABILITY_BUFFER_VALIDATION,
        SA_CAPABILITY_MODEL_IR_V2_SNAPSHOT, SA_CAPABILITY_MODEL_IR_V2_TYPED,
        SA_CAPABILITY_NONLINEAR_STATIC_CPU, SA_CAPABILITY_TRACK_POINT_LOAD_CPU,
        SA_ERR_INVALID_ARGUMENT, SA_ERR_UNSUPPORTED, SA_OK,
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
