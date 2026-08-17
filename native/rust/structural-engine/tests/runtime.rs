use std::ffi::c_char;
use std::sync::atomic::{AtomicUsize, Ordering};

use structural_engine::{sys, Engine, EngineApi, EngineConfig, Error};

static DESTROY_COUNT: AtomicUsize = AtomicUsize::new(0);
static IMPLEMENTATION_NAME: &[u8] = b"mock-structural-engine\0";

#[derive(Clone)]
struct MockApi {
    create_status: sys::Status,
    api_major: u32,
    error_message: String,
}

impl MockApi {
    fn success() -> Self {
        Self {
            create_status: sys::Status::Ok,
            api_major: sys::ABI_VERSION_MAJOR,
            error_message: "mock native failure".to_owned(),
        }
    }
}

impl EngineApi for MockApi {
    unsafe fn get_api_info(&self, out_info: *mut sys::ApiInfo) -> i32 {
        if out_info.is_null() {
            return sys::Status::InvalidArgument as i32;
        }
        unsafe {
            (*out_info).abi_version_major = self.api_major;
            (*out_info).abi_version_minor = sys::ABI_VERSION_MINOR;
            (*out_info).capability_bits = sys::CAPABILITY_CPU_REFERENCE;
            (*out_info).implementation_name = IMPLEMENTATION_NAME.as_ptr().cast::<c_char>();
        }
        sys::Status::Ok as i32
    }

    unsafe fn create_engine(
        &self,
        _config: *const sys::EngineConfig,
        out_engine: *mut *mut sys::Engine,
    ) -> i32 {
        if self.create_status != sys::Status::Ok {
            return self.create_status as i32;
        }
        unsafe { *out_engine = std::ptr::NonNull::<sys::Engine>::dangling().as_ptr() };
        sys::Status::Ok as i32
    }

    unsafe fn destroy_engine(&self, engine: *mut sys::Engine) {
        if !engine.is_null() {
            DESTROY_COUNT.fetch_add(1, Ordering::SeqCst);
        }
    }

    unsafe fn engine_capabilities(
        &self,
        _engine: *const sys::Engine,
        out_capabilities: *mut u64,
    ) -> i32 {
        unsafe { *out_capabilities = sys::CAPABILITY_CPU_REFERENCE };
        sys::Status::Ok as i32
    }

    unsafe fn engine_last_error(
        &self,
        _engine: *const sys::Engine,
        buffer: *mut c_char,
        buffer_capacity: usize,
        out_required_size: *mut usize,
    ) -> i32 {
        let message = self.error_message.as_bytes();
        let required = message.len() + 1;
        unsafe { *out_required_size = required };
        if buffer.is_null() || buffer_capacity < required {
            return sys::Status::BufferTooSmall as i32;
        }
        unsafe {
            std::ptr::copy_nonoverlapping(
                message.as_ptr().cast::<c_char>(),
                buffer,
                message.len(),
            );
            *buffer.add(message.len()) = 0;
        }
        sys::Status::Ok as i32
    }
}

#[test]
fn engine_handle_is_released_exactly_once() {
    DESTROY_COUNT.store(0, Ordering::SeqCst);
    {
        let engine = Engine::create(MockApi::success(), EngineConfig::default())
            .expect("engine should be created");
        assert_eq!(
            engine.capabilities().expect("capabilities should succeed"),
            sys::CAPABILITY_CPU_REFERENCE
        );
    }
    assert_eq!(DESTROY_COUNT.load(Ordering::SeqCst), 1);
}

#[test]
fn create_error_preserves_native_status_and_message() {
    let error = Engine::create(
        MockApi {
            create_status: sys::Status::Unsupported,
            api_major: sys::ABI_VERSION_MAJOR,
            error_message: "mock native failure".to_owned(),
        },
        EngineConfig::default(),
    )
    .err()
    .expect("unsupported configuration should fail");
    assert_eq!(
        error,
        Error::Native {
            status: sys::Status::Unsupported,
            message: "mock native failure".to_owned(),
        }
    );
}

#[test]
fn long_native_diagnostic_is_not_truncated() {
    let message = "diagnostic:".to_owned() + &"x".repeat(2_048);
    let error = Engine::create(
        MockApi {
            create_status: sys::Status::InternalError,
            api_major: sys::ABI_VERSION_MAJOR,
            error_message: message.clone(),
        },
        EngineConfig::default(),
    )
    .err()
    .expect("native error should fail engine creation");
    assert_eq!(
        error,
        Error::Native {
            status: sys::Status::InternalError,
            message,
        }
    );
}

#[test]
fn incompatible_abi_is_rejected_before_create() {
    let error = Engine::create(
        MockApi {
            create_status: sys::Status::Ok,
            api_major: sys::ABI_VERSION_MAJOR + 1,
            error_message: "unused".to_owned(),
        },
        EngineConfig::default(),
    )
    .err()
    .expect("ABI mismatch should fail");
    assert!(matches!(error, Error::AbiMismatch { .. }));
}
