//! Safe entry-table and immutable `ModelIR` ownership for C ABI v1.

mod descriptor;

use core::ffi::{c_char, c_void};
use core::fmt;
use core::marker::PhantomData;
use core::mem::size_of;
use core::ptr::{self, NonNull};
use std::rc::Rc;

use serde::{Deserialize, Serialize};
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

pub type LinearFrame3dNode = sys::SaLinearFrame3dNodeV1;
pub type LinearFrame3dSection = sys::SaLinearFrame3dSectionV1;
pub type LinearFrame3dMember = sys::SaLinearFrame3dMemberV1;
pub type LinearFrame3dUniformMemberLoad = sys::SaLinearFrame3dUniformMemberLoadV1;

/// Borrowed Rust input for the bounded linear-elastic `Frame3D` native profile.
pub struct LinearFrame3dInput<'a> {
    pub nodes: &'a [LinearFrame3dNode],
    pub sections: &'a [LinearFrame3dSection],
    pub members: &'a [LinearFrame3dMember],
    pub restrained_dofs: &'a [u32],
}

/// Borrowed load case for ABI v1.3 bounded nodal and uniform initial-local member forces.
pub struct LinearFrame3dLoadCase<'a> {
    pub nodal_load_vector_kn: &'a [f64],
    pub uniform_member_loads: &'a [LinearFrame3dUniformMemberLoad],
}

/// Caller-owned result vectors produced by one successful native `Frame3D` solve.
#[derive(Clone, Debug, PartialEq)]
pub struct LinearFrame3dResult {
    pub displacements: Vec<f64>,
    pub reactions: Vec<f64>,
    pub member_end_forces: Vec<f64>,
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

    /// Load ABI v1.1 with typed `ModelIR` and snapshot support.
    ///
    /// # Errors
    ///
    /// Returns a stable ABI error if any required v1.1 capability or operation is absent.
    pub fn load_model_ir() -> Result<Self, Error> {
        Self::load_version(sys::SA_ABI_V1_1)
    }

    /// Load ABI v1.2 with `ModelIR` and bounded CPU `Frame3D` support.
    ///
    /// # Errors
    ///
    /// Returns a stable ABI error if any required v1.2 capability or operation is absent.
    pub fn load_frame3d() -> Result<Self, Error> {
        Self::load_version(sys::SA_ABI_V1_2)
    }

    /// Load ABI v1.3 with the bounded uniform initial-member-local load-case solve.
    ///
    /// # Errors
    ///
    /// Returns a stable ABI error if the v1.3 capability or operation is absent.
    pub fn load_frame3d_member_loads() -> Result<Self, Error> {
        Self::load_version(sys::SA_ABI_V1_3)
    }

    /// Load ABI v1.4 with bounded RX/RY/RZ member-end releases.
    ///
    /// # Errors
    ///
    /// Returns a stable ABI error if the v1.4 capability is absent.
    pub fn load_frame3d_releases() -> Result<Self, Error> {
        Self::load_version(sys::SA_ABI_V1_4)
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

    /// Deep-copy and compile a bounded linear-elastic `Frame3D` model in the native core.
    ///
    /// # Errors
    ///
    /// Returns a stable ABI error for invalid topology, unsupported profile bounds, or native
    /// allocation failure. Input slices are borrowed only for the duration of this call.
    pub fn compile_linear_frame3d(
        self,
        input: &LinearFrame3dInput<'_>,
    ) -> Result<LinearFrame3dModel, Error> {
        if self.abi_version() < sys::SA_ABI_V1_2 {
            return Err(Error {
                code: sys::SA_ERR_UNSUPPORTED,
                message: "bounded linear Frame3D requires ABI v1.2".to_owned(),
            });
        }
        let raw_input = sys::SaLinearFrame3dModelInputV1 {
            abi_version_major: self.abi_version() >> 16,
            abi_version_minor: self.abi_version() & 0xffff,
            nodes: input.nodes.as_ptr(),
            node_count: usize_to_u64(input.nodes.len())?,
            sections: input.sections.as_ptr(),
            section_count: usize_to_u64(input.sections.len())?,
            members: input.members.as_ptr(),
            member_count: usize_to_u64(input.members.len())?,
            restrained_dofs: input.restrained_dofs.as_ptr(),
            restrained_dof_count: usize_to_u64(input.restrained_dofs.len())?,
            ..sys::SaLinearFrame3dModelInputV1::default()
        };
        let compile = self
            .table
            .linear_frame3d_model_compile
            .ok_or_else(invalid_table)?;
        let mut output = ptr::null_mut();
        let mut storage = [0_i8; ERROR_CAPACITY];
        let mut error = error_buffer(self.abi_version(), &mut storage);
        // SAFETY: every descriptor slice remains live for the call; the native contract
        // validates and deep-copies all model data before returning.
        let status = unsafe { compile(&raw_input, &mut output, &mut error) };
        if status != sys::SA_OK {
            return Err(error_from_buffer(status, &storage));
        }
        let handle = NonNull::new(output).ok_or_else(|| Error {
            code: sys::SA_ERR_INTERNAL,
            message: "native Frame3D compile returned a null success handle".to_owned(),
        })?;
        let mut model = LinearFrame3dModel {
            api: self,
            handle,
            dof_count: 0,
            member_end_force_count: 0,
            _not_send_or_sync: PhantomData,
        };
        model.read_shape()?;
        Ok(model)
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

/// Unique RAII owner of one compiled bounded native `Frame3D` model.
pub struct LinearFrame3dModel {
    api: Api,
    handle: NonNull<sys::SaLinearFrame3dModelV1>,
    dof_count: usize,
    member_end_force_count: usize,
    _not_send_or_sync: PhantomData<Rc<()>>,
}

impl LinearFrame3dModel {
    #[must_use]
    pub const fn dof_count(&self) -> usize {
        self.dof_count
    }

    #[must_use]
    pub const fn member_count(&self) -> usize {
        self.member_end_force_count / 12
    }

    /// Solve one load vector with deterministic caller-owned output buffers.
    ///
    /// # Errors
    ///
    /// Returns a stable ABI error if the load shape/value is invalid or the system is singular.
    pub fn solve(&self, load_vector_kn: &[f64]) -> Result<LinearFrame3dResult, Error> {
        if load_vector_kn.len() != self.dof_count {
            return Err(Error {
                code: sys::SA_ERR_INVALID_ARGUMENT,
                message: format!(
                    "Frame3D load length must be {}; received {}",
                    self.dof_count,
                    load_vector_kn.len()
                ),
            });
        }
        let mut result = LinearFrame3dResult {
            displacements: vec![0.0; self.dof_count],
            reactions: vec![0.0; self.dof_count],
            member_end_forces: vec![0.0; self.member_end_force_count],
        };
        let mut raw_result = sys::SaLinearFrame3dResultBuffersV1 {
            displacements: result.displacements.as_mut_ptr(),
            displacement_count: usize_to_u64(result.displacements.len())?,
            reactions: result.reactions.as_mut_ptr(),
            reaction_count: usize_to_u64(result.reactions.len())?,
            member_end_forces: result.member_end_forces.as_mut_ptr(),
            member_end_force_count: usize_to_u64(result.member_end_forces.len())?,
            ..sys::SaLinearFrame3dResultBuffersV1::default()
        };
        let solve = self.table_solve()?;
        let mut storage = [0_i8; ERROR_CAPACITY];
        let mut error = error_buffer(self.api.abi_version(), &mut storage);
        // SAFETY: the unique model handle is live, the load slice remains borrowed, and all
        // output vectors own their advertised writable extents for the complete call.
        let status = unsafe {
            solve(
                self.handle.as_ptr(),
                load_vector_kn.as_ptr(),
                usize_to_u64(load_vector_kn.len())?,
                &mut raw_result,
                &mut error,
            )
        };
        status_result(status, &storage)?;
        Ok(result)
    }

    /// Solve one ABI v1.3 load case with nodal and uniform initial-local member forces.
    ///
    /// # Errors
    ///
    /// Returns a stable ABI error for an invalid load row, shape, non-finite value, or singular
    /// system. The native core owns equivalent-load assembly and fixed-end-force recovery.
    pub fn solve_load_case(
        &self,
        load_case: &LinearFrame3dLoadCase<'_>,
    ) -> Result<LinearFrame3dResult, Error> {
        if self.api.abi_version() < sys::SA_ABI_V1_3 {
            return Err(Error {
                code: sys::SA_ERR_UNSUPPORTED,
                message: "uniform member loads require ABI v1.3".to_owned(),
            });
        }
        if load_case.nodal_load_vector_kn.len() != self.dof_count {
            return Err(Error {
                code: sys::SA_ERR_INVALID_ARGUMENT,
                message: format!(
                    "Frame3D nodal load length must be {}; received {}",
                    self.dof_count,
                    load_case.nodal_load_vector_kn.len()
                ),
            });
        }
        let mut result = LinearFrame3dResult {
            displacements: vec![0.0; self.dof_count],
            reactions: vec![0.0; self.dof_count],
            member_end_forces: vec![0.0; self.member_end_force_count],
        };
        let mut raw_result = sys::SaLinearFrame3dResultBuffersV1 {
            displacements: result.displacements.as_mut_ptr(),
            displacement_count: usize_to_u64(result.displacements.len())?,
            reactions: result.reactions.as_mut_ptr(),
            reaction_count: usize_to_u64(result.reactions.len())?,
            member_end_forces: result.member_end_forces.as_mut_ptr(),
            member_end_force_count: usize_to_u64(result.member_end_forces.len())?,
            ..sys::SaLinearFrame3dResultBuffersV1::default()
        };
        let raw_load_case = sys::SaLinearFrame3dLoadCaseV1 {
            nodal_load_vector_kn: load_case.nodal_load_vector_kn.as_ptr(),
            nodal_load_count: usize_to_u64(load_case.nodal_load_vector_kn.len())?,
            uniform_member_loads: if load_case.uniform_member_loads.is_empty() {
                ptr::null()
            } else {
                load_case.uniform_member_loads.as_ptr()
            },
            uniform_member_load_count: usize_to_u64(load_case.uniform_member_loads.len())?,
            ..sys::SaLinearFrame3dLoadCaseV1::default()
        };
        let solve = self
            .api
            .table
            .linear_frame3d_solve_load_case
            .ok_or_else(invalid_table)?;
        let mut storage = [0_i8; ERROR_CAPACITY];
        let mut error = error_buffer(self.api.abi_version(), &mut storage);
        // SAFETY: the unique compiled model is live; every load and output slice owns its exact
        // advertised extent for the complete immutable native call.
        let status = unsafe {
            solve(
                self.handle.as_ptr(),
                &raw_load_case,
                &mut raw_result,
                &mut error,
            )
        };
        status_result(status, &storage)?;
        Ok(result)
    }

    fn read_shape(&mut self) -> Result<(), Error> {
        let sizes = self
            .api
            .table
            .linear_frame3d_model_sizes
            .ok_or_else(invalid_table)?;
        let mut dof_count = 0_u64;
        let mut force_count = 0_u64;
        let mut storage = [0_i8; ERROR_CAPACITY];
        let mut error = error_buffer(self.api.abi_version(), &mut storage);
        // SAFETY: the newly compiled unique handle and output scalars are live for the call.
        let status = unsafe {
            sizes(
                self.handle.as_ptr(),
                &mut dof_count,
                &mut force_count,
                &mut error,
            )
        };
        status_result(status, &storage)?;
        self.dof_count = usize::try_from(dof_count).map_err(|_| invalid_frame_shape())?;
        self.member_end_force_count =
            usize::try_from(force_count).map_err(|_| invalid_frame_shape())?;
        if self.dof_count == 0
            || self.member_end_force_count == 0
            || self.member_end_force_count % 12 != 0
        {
            return Err(invalid_frame_shape());
        }
        Ok(())
    }

    fn table_solve(&self) -> Result<sys::SaLinearFrame3dSolveFnV1, Error> {
        self.api
            .table
            .linear_frame3d_solve
            .ok_or_else(invalid_table)
    }
}

impl Drop for LinearFrame3dModel {
    fn drop(&mut self) {
        if let Some(destroy) = self.api.table.linear_frame3d_model_destroy {
            // SAFETY: safe Rust exposes no duplicate owner and this is the unique destruction
            // point for the native model handle.
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
    let frame_slots = [
        table.linear_frame3d_model_compile.is_some(),
        table.linear_frame3d_model_destroy.is_some(),
        table.linear_frame3d_model_sizes.is_some(),
        table.linear_frame3d_solve.is_some(),
    ];
    let member_load_slot = table.linear_frame3d_solve_load_case.is_some();
    let version_valid = if requested == sys::SA_ABI_V1_0 {
        model_slots.iter().all(|present| !present)
            && frame_slots.iter().all(|present| !present)
            && !member_load_slot
            && table.capabilities == sys::SA_CAPABILITY_BUFFER_VALIDATION
    } else if requested == sys::SA_ABI_V1_1 {
        model_slots.iter().all(|present| *present)
            && frame_slots.iter().all(|present| !present)
            && !member_load_slot
            && table.capabilities
                == (sys::SA_CAPABILITY_BUFFER_VALIDATION
                    | sys::SA_CAPABILITY_MODEL_IR_V2_TYPED
                    | sys::SA_CAPABILITY_MODEL_IR_V2_SNAPSHOT)
    } else if requested == sys::SA_ABI_V1_2 {
        model_slots.iter().all(|present| *present)
            && frame_slots.iter().all(|present| *present)
            && !member_load_slot
            && table.capabilities
                == (sys::SA_CAPABILITY_BUFFER_VALIDATION
                    | sys::SA_CAPABILITY_MODEL_IR_V2_TYPED
                    | sys::SA_CAPABILITY_MODEL_IR_V2_SNAPSHOT
                    | sys::SA_CAPABILITY_LINEAR_FRAME3D_CPU)
    } else if requested == sys::SA_ABI_V1_3 {
        model_slots.iter().all(|present| *present)
            && frame_slots.iter().all(|present| *present)
            && member_load_slot
            && table.capabilities
                == (sys::SA_CAPABILITY_BUFFER_VALIDATION
                    | sys::SA_CAPABILITY_MODEL_IR_V2_TYPED
                    | sys::SA_CAPABILITY_MODEL_IR_V2_SNAPSHOT
                    | sys::SA_CAPABILITY_LINEAR_FRAME3D_CPU
                    | sys::SA_CAPABILITY_LINEAR_FRAME3D_UNIFORM_MEMBER_LOAD)
    } else if requested == sys::SA_ABI_V1_4 {
        model_slots.iter().all(|present| *present)
            && frame_slots.iter().all(|present| *present)
            && member_load_slot
            && table.capabilities
                == (sys::SA_CAPABILITY_BUFFER_VALIDATION
                    | sys::SA_CAPABILITY_MODEL_IR_V2_TYPED
                    | sys::SA_CAPABILITY_MODEL_IR_V2_SNAPSHOT
                    | sys::SA_CAPABILITY_LINEAR_FRAME3D_CPU
                    | sys::SA_CAPABILITY_LINEAR_FRAME3D_UNIFORM_MEMBER_LOAD
                    | sys::SA_CAPABILITY_LINEAR_FRAME3D_ROTATIONAL_END_RELEASE)
    } else {
        false
    };
    if base_valid && version_valid {
        Ok(())
    } else {
        Err(invalid_table())
    }
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

fn invalid_frame_shape() -> Error {
    Error {
        code: sys::SA_ERR_INTERNAL,
        message: "native Frame3D model returned an invalid result shape".to_owned(),
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
    use super::{
        Api, LinearFrame3dInput, LinearFrame3dLoadCase, LinearFrame3dMember, LinearFrame3dNode,
        LinearFrame3dSection, LinearFrame3dUniformMemberLoad,
    };
    use std::path::{Path, PathBuf};
    use std::sync::Arc;
    use std::thread;
    use structural_contracts::model_ir::parse_model_ir_v2;
    use structural_ffi_sys::{
        SA_ABI_V1_1, SA_ABI_V1_2, SA_ABI_V1_3, SA_ABI_V1_4, SA_CAPABILITY_BUFFER_VALIDATION,
        SA_CAPABILITY_LINEAR_FRAME3D_CPU, SA_CAPABILITY_LINEAR_FRAME3D_ROTATIONAL_END_RELEASE,
        SA_CAPABILITY_LINEAR_FRAME3D_UNIFORM_MEMBER_LOAD, SA_CAPABILITY_MODEL_IR_V2_SNAPSHOT,
        SA_CAPABILITY_MODEL_IR_V2_TYPED, SA_ERR_ANALYSIS_NOT_READY, SA_ERR_INVALID_ARGUMENT,
        SA_ERR_UNSUPPORTED, SA_FRAME3D_DOF_MASK_RX, SA_FRAME3D_DOF_MASK_RZ, SA_OK,
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

    fn frame_section() -> LinearFrame3dSection {
        LinearFrame3dSection::new(
            0.02,
            200_000_000.0,
            76_923_076.923_076_93,
            8.0e-5,
            5.0e-5,
            1.0e-5,
            0.015,
            0.014,
        )
    }

    #[test]
    fn v1_2_compiles_and_solves_the_bounded_native_cantilever() {
        let api = Api::load_frame3d().expect("v1.2 API loads");
        assert_eq!(api.abi_version(), SA_ABI_V1_2);
        assert_ne!(api.capabilities() & SA_CAPABILITY_LINEAR_FRAME3D_CPU, 0);

        let nodes = [
            LinearFrame3dNode::new(0.0, 0.0, 0.0),
            LinearFrame3dNode::new(2.0, 0.0, 0.0),
        ];
        let sections = [frame_section()];
        let members = [LinearFrame3dMember::new(0, 1, 0)];
        let restrained_dofs = [0, 1, 2, 3, 4, 5];
        let model = api
            .compile_linear_frame3d(&LinearFrame3dInput {
                nodes: &nodes,
                sections: &sections,
                members: &members,
                restrained_dofs: &restrained_dofs,
            })
            .expect("bounded cantilever compiles");
        assert_eq!(model.dof_count(), 12);
        assert_eq!(model.member_count(), 1);

        let mut loads = [0.0; 12];
        loads[7] = -10.0;
        let result = model.solve(&loads).expect("bounded cantilever solves");
        assert!(result.displacements[7] < 0.0);
        assert!((result.reactions[1] - 10.0).abs() < 1.0e-10);
        assert!((result.reactions[5] - 20.0).abs() < 1.0e-10);
        assert!(result.displacements.iter().all(|value| value.is_finite()));

        let length_error = model.solve(&loads[..11]).expect_err("wrong load shape");
        assert_eq!(length_error.code, SA_ERR_INVALID_ARGUMENT);
    }

    #[test]
    fn frame3d_version_and_singular_boundaries_fail_closed() {
        let compatibility = Api::load_model_ir().expect("v1.1 API loads");
        let nodes = [
            LinearFrame3dNode::new(0.0, 0.0, 0.0),
            LinearFrame3dNode::new(2.0, 0.0, 0.0),
        ];
        let sections = [frame_section()];
        let members = [LinearFrame3dMember::new(0, 1, 0)];
        let restrained_dofs = [0, 1, 2];
        let input = LinearFrame3dInput {
            nodes: &nodes,
            sections: &sections,
            members: &members,
            restrained_dofs: &restrained_dofs,
        };
        let unsupported = compatibility
            .compile_linear_frame3d(&input)
            .err()
            .expect("v1.1 table has no Frame3D slots");
        assert_eq!(unsupported.code, SA_ERR_UNSUPPORTED);

        let model = Api::load_frame3d()
            .expect("v1.2 API")
            .compile_linear_frame3d(&input)
            .expect("under-restrained topology compiles for solve-time diagnosis");
        let mut loads = [0.0; 12];
        loads[7] = -10.0;
        let singular = model
            .solve(&loads)
            .expect_err("singular system fails closed");
        assert_eq!(singular.code, SA_ERR_ANALYSIS_NOT_READY);
    }

    #[test]
    fn v1_3_uniform_local_member_load_recovers_fixed_end_forces() {
        let api = Api::load_frame3d_member_loads().expect("v1.3 API loads");
        assert_eq!(api.abi_version(), SA_ABI_V1_3);
        assert_ne!(
            api.capabilities() & SA_CAPABILITY_LINEAR_FRAME3D_UNIFORM_MEMBER_LOAD,
            0
        );
        let nodes = [
            LinearFrame3dNode::new(0.0, 0.0, 0.0),
            LinearFrame3dNode::new(2.0, 0.0, 0.0),
        ];
        let sections = [frame_section()];
        let members = [LinearFrame3dMember::new(0, 1, 0)];
        let restrained_dofs = [0, 1, 2, 3, 4, 5];
        let model = api
            .compile_linear_frame3d(&LinearFrame3dInput {
                nodes: &nodes,
                sections: &sections,
                members: &members,
                restrained_dofs: &restrained_dofs,
            })
            .expect("bounded cantilever compiles");
        let nodal = [0.0; 12];
        let member_loads = [LinearFrame3dUniformMemberLoad::new(0, [0.0, -10.0, 0.0])];
        let result = model
            .solve_load_case(&LinearFrame3dLoadCase {
                nodal_load_vector_kn: &nodal,
                uniform_member_loads: &member_loads,
            })
            .expect("uniform member load solves");
        assert!((result.reactions[1] - 20.0).abs() < 1.0e-9);
        assert!((result.reactions[5] - 20.0).abs() < 1.0e-9);
        assert!((result.member_end_forces[1] - 20.0).abs() < 1.0e-9);
        assert!((result.member_end_forces[5] - 20.0).abs() < 1.0e-9);
        assert!(result.member_end_forces[7].abs() < 1.0e-9);
        assert!(result.member_end_forces[11].abs() < 1.0e-9);

        let legacy = Api::load_frame3d()
            .expect("v1.2 API")
            .compile_linear_frame3d(&LinearFrame3dInput {
                nodes: &nodes,
                sections: &sections,
                members: &members,
                restrained_dofs: &restrained_dofs,
            })
            .expect("legacy compile");
        let unsupported = legacy
            .solve_load_case(&LinearFrame3dLoadCase {
                nodal_load_vector_kn: &nodal,
                uniform_member_loads: &member_loads,
            })
            .expect_err("v1.2 has no member-load solve slot");
        assert_eq!(unsupported.code, SA_ERR_UNSUPPORTED);

        let zero_loads = [LinearFrame3dUniformMemberLoad::new(0, [0.0; 3])];
        let invalid = model
            .solve_load_case(&LinearFrame3dLoadCase {
                nodal_load_vector_kn: &nodal,
                uniform_member_loads: &zero_loads,
            })
            .expect_err("zero member-load row fails closed");
        assert_eq!(invalid.code, SA_ERR_INVALID_ARGUMENT);
    }

    #[test]
    fn v1_4_rotational_release_condenses_member_load_and_legacy_rejects_it() {
        let api = Api::load_frame3d_releases().expect("v1.4 API loads");
        assert_eq!(api.abi_version(), SA_ABI_V1_4);
        assert_ne!(
            api.capabilities() & SA_CAPABILITY_LINEAR_FRAME3D_ROTATIONAL_END_RELEASE,
            0
        );
        let nodes = [
            LinearFrame3dNode::new(0.0, 0.0, 0.0),
            LinearFrame3dNode::new(2.0, 0.0, 0.0),
        ];
        let sections = [frame_section()];
        let mut member = LinearFrame3dMember::new(0, 1, 0);
        member.released_dof_mask_j = SA_FRAME3D_DOF_MASK_RZ;
        let members = [member];
        let restrained_dofs = [0, 1, 2, 3, 4, 5, 7, 11];
        let model = api
            .compile_linear_frame3d(&LinearFrame3dInput {
                nodes: &nodes,
                sections: &sections,
                members: &members,
                restrained_dofs: &restrained_dofs,
            })
            .expect("released propped member compiles");
        let result = model
            .solve_load_case(&LinearFrame3dLoadCase {
                nodal_load_vector_kn: &[0.0; 12],
                uniform_member_loads: &[LinearFrame3dUniformMemberLoad::new(0, [0.0, -10.0, 0.0])],
            })
            .expect("released member load solves");
        assert!(result.member_end_forces[11].abs() < 1.0e-10);
        assert!(result.reactions[11].abs() < 1.0e-10);
        assert!((result.reactions[1] + result.reactions[7] - 20.0).abs() < 1.0e-9);

        let legacy_error = Api::load_frame3d_member_loads()
            .expect("v1.3 API")
            .compile_linear_frame3d(&LinearFrame3dInput {
                nodes: &nodes,
                sections: &sections,
                members: &members,
                restrained_dofs: &restrained_dofs,
            })
            .err()
            .expect("v1.3 keeps former reserved slots zero");
        assert_eq!(legacy_error.code, SA_ERR_INVALID_ARGUMENT);

        let mut singular_member = LinearFrame3dMember::new(0, 1, 0);
        singular_member.released_dof_mask_i = SA_FRAME3D_DOF_MASK_RX;
        singular_member.released_dof_mask_j = SA_FRAME3D_DOF_MASK_RX;
        let singular_members = [singular_member];
        let singular_release = api
            .compile_linear_frame3d(&LinearFrame3dInput {
                nodes: &nodes,
                sections: &sections,
                members: &singular_members,
                restrained_dofs: &restrained_dofs,
            })
            .err()
            .expect("two-end torsion release has a singular condensation partition");
        assert_eq!(singular_release.code, SA_ERR_INVALID_ARGUMENT);
    }
}
