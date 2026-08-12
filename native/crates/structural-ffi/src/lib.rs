//! Safe entry-table access for the C ABI v1.

use core::ffi::{c_char, c_void};
use core::fmt;
use core::mem::size_of;
use core::ptr;

use structural_ffi_sys as sys;

const ERROR_CAPACITY: usize = 256;

/// Stable error returned by the native core.
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

/// Immutable, process-lifetime C ABI v1 function table.
#[derive(Clone, Copy)]
pub struct Api {
    table: sys::SaApiV1,
}

// SAFETY: `Api::load` rejects non-null reserved pointers and copies a table of
// immutable process-lifetime function pointers. No caller-owned pointer is retained.
unsafe impl Send for Api {}
// SAFETY: every exposed base function uses only caller-owned arguments and error buffers.
unsafe impl Sync for Api {}

impl Api {
    /// Load the supported ABI v1.0 function table.
    ///
    /// # Errors
    ///
    /// Returns a stable ABI error if the library rejects the request or returns an invalid
    /// function table.
    pub fn load() -> Result<Self, Error> {
        Self::load_version(sys::SA_ABI_V1_0)
    }

    fn load_version(abi_version: u32) -> Result<Self, Error> {
        let request = sys::SaApiRequestV1 {
            abi_version,
            struct_size: u32::try_from(size_of::<sys::SaApiRequestV1>()).unwrap_or(u32::MAX),
            flags: 0,
            reserved: [0; 3],
        };
        let mut table = sys::SaApiV1 {
            abi_version,
            ..sys::SaApiV1::default()
        };
        let mut storage = [0_i8; ERROR_CAPACITY];
        let mut error = error_buffer(&mut storage);
        // SAFETY: request, table and error point to live, correctly sized C-layout values.
        let status = unsafe { sys::sa_get_api_v1(&request, &mut table, &mut error) };
        if status != sys::SA_OK {
            return Err(error_from_buffer(status, &storage));
        }
        if table.abi_version != sys::SA_ABI_V1_0
            || table.validate_buffer_view.is_none()
            || table.reserved.iter().any(|value| !value.is_null())
        {
            return Err(Error {
                code: sys::SA_ERR_INTERNAL,
                message: "invalid API table returned by native library".to_owned(),
            });
        }
        Ok(Self { table })
    }

    /// Return the capability bits declared by the v1 function table.
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
            abi_version: sys::SA_ABI_V1_0,
            struct_size: u32::try_from(size_of::<sys::SaBufferViewV1>()).unwrap_or(u32::MAX),
            data,
            length: u64::try_from(values.len()).unwrap_or(u64::MAX),
            stride_bytes: u64::try_from(size_of::<f64>()).unwrap_or(u64::MAX),
            element_type: sys::SA_ELEMENT_TYPE_F64,
            memory_space: sys::SA_MEMORY_SPACE_HOST,
            device_id: -1,
            flags: 0,
        };
        let mut storage = [0_i8; ERROR_CAPACITY];
        let mut error = error_buffer(&mut storage);
        let validate = self.table.validate_buffer_view.ok_or_else(|| Error {
            code: sys::SA_ERR_INTERNAL,
            message: "buffer validator missing from API table".to_owned(),
        })?;
        // SAFETY: the view borrows `values` for this call only and the error storage is live.
        let status = unsafe { validate(&view, &mut error) };
        if status == sys::SA_OK {
            Ok(())
        } else {
            Err(error_from_buffer(status, &storage))
        }
    }
}

fn error_buffer(storage: &mut [c_char; ERROR_CAPACITY]) -> sys::SaErrorBufferV1 {
    sys::SaErrorBufferV1 {
        abi_version: sys::SA_ABI_V1_0,
        struct_size: u32::try_from(size_of::<sys::SaErrorBufferV1>()).unwrap_or(u32::MAX),
        data: storage.as_mut_ptr(),
        capacity: u64::try_from(storage.len()).unwrap_or(u64::MAX),
        required: 0,
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
    use std::sync::Arc;
    use std::thread;
    use structural_ffi_sys::{SA_CAPABILITY_BUFFER_VALIDATION, SA_OK};

    #[test]
    fn loads_v1_and_validates_caller_owned_f64() {
        let api = Api::load().expect("v1 API loads");
        assert_eq!(api.capabilities(), SA_CAPABILITY_BUFFER_VALIDATION);
        assert_eq!(api.validate_f64_slice(&[1.0, 2.0, 3.0]), Ok(()));
        assert_eq!(api.validate_f64_slice(&[]), Ok(()));
        assert_eq!(SA_OK, 0);
    }

    #[test]
    fn immutable_api_table_is_safe_for_concurrent_reads() {
        let api = Arc::new(Api::load().expect("v1 API loads"));
        let threads: Vec<_> = (0..8)
            .map(|index| {
                let api = Arc::clone(&api);
                thread::spawn(move || {
                    for iteration in 0..256 {
                        api.validate_f64_slice(&[f64::from(index), f64::from(iteration)])
                            .expect("independent caller-owned view validates");
                    }
                })
            })
            .collect();
        for worker in threads {
            worker.join().expect("worker does not panic");
        }
    }
}
