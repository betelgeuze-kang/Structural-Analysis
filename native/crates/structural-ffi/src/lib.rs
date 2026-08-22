//! Safe entry-table and immutable `ModelIR` ownership for C ABI v1.

mod descriptor;

use core::ffi::{c_char, c_void};
use core::fmt;
use core::mem::size_of;
use core::ptr::{self, NonNull};

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

    /// Load the current ABI v1.1 table with typed `ModelIR` and snapshot support.
    ///
    /// # Errors
    ///
    /// Returns a stable ABI error if any required v1.1 capability or operation is absent.
    pub fn load_model_ir() -> Result<Self, Error> {
        Self::load_version(sys::SA_ABI_V1_1)
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
    let version_valid = if requested == sys::SA_ABI_V1_0 {
        model_slots.iter().all(|present| !present)
            && table.capabilities == sys::SA_CAPABILITY_BUFFER_VALIDATION
    } else if requested == sys::SA_ABI_V1_1 {
        model_slots.iter().all(|present| *present)
            && table.capabilities & sys::SA_CAPABILITY_MODEL_IR_V2_TYPED != 0
            && table.capabilities & sys::SA_CAPABILITY_MODEL_IR_V2_SNAPSHOT != 0
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
        SA_ABI_V1_1, SA_CAPABILITY_BUFFER_VALIDATION, SA_CAPABILITY_MODEL_IR_V2_SNAPSHOT,
        SA_CAPABILITY_MODEL_IR_V2_TYPED, SA_ERR_INVALID_ARGUMENT, SA_ERR_UNSUPPORTED, SA_OK,
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
}
