use std::ffi::CStr;
use std::os::raw::{c_char, c_int, c_longlong, c_void};
use std::sync::OnceLock;

const RTLD_NOW: c_int = 2;
const RTLD_LOCAL: c_int = 0;

#[repr(C)]
#[derive(Clone, Copy, Debug, Default)]
pub struct MgtHipFullResidualFfiStatus {
    pub code: c_int,
    pub frame_element_count: c_longlong,
    pub n_dof: c_longlong,
    pub free_count: c_longlong,
    pub shell_nnz: c_longlong,
    pub spring_nnz: c_longlong,
    pub batch_size: c_longlong,
    pub reps: c_int,
    pub device_id: c_int,
    pub eval_buffers_reused: c_int,
    pub operator_buffers_device_resident: c_int,
    pub kernel_elapsed_ms_total: f64,
    pub kernel_elapsed_ms_mean: f64,
    pub output_abs_sum: f64,
    pub output_max_abs: f64,
}

type CreateFn = unsafe extern "C" fn(
    *mut *mut c_void,
    *const c_longlong,
    *const f64,
    *const c_longlong,
    *const c_longlong,
    *const f64,
    *const c_longlong,
    *const c_longlong,
    *const f64,
    *const f64,
    *const c_longlong,
    c_longlong,
    c_longlong,
    c_longlong,
    c_longlong,
    c_longlong,
    *mut MgtHipFullResidualFfiStatus,
) -> c_int;

type EvalFn = unsafe extern "C" fn(
    *mut c_void,
    *const f64,
    c_longlong,
    c_int,
    *mut f64,
    *mut MgtHipFullResidualFfiStatus,
) -> c_int;

type DestroyFn = unsafe extern "C" fn(*mut c_void) -> c_int;
type DeviceNameFn = unsafe extern "C" fn(*mut c_void, *mut c_char, usize) -> c_int;
type LastErrorFn = unsafe extern "C" fn() -> *const c_char;

struct Api {
    create: CreateFn,
    eval: EvalFn,
    destroy: DestroyFn,
    device_name: DeviceNameFn,
    last_error: LastErrorFn,
}

static API: OnceLock<Api> = OnceLock::new();

#[link(name = "dl")]
extern "C" {
    fn dlopen(filename: *const c_char, flag: c_int) -> *mut c_void;
    fn dlsym(handle: *mut c_void, symbol: *const c_char) -> *mut c_void;
    fn dlerror() -> *const c_char;
}

unsafe fn symbol<T>(handle: *mut c_void, name: &'static [u8]) -> Result<T, c_int>
where
    T: Copy,
{
    let ptr = dlsym(handle, name.as_ptr() as *const c_char);
    if ptr.is_null() {
        return Err(-3);
    }
    Ok(std::mem::transmute_copy::<*mut c_void, T>(&ptr))
}

fn api() -> Option<&'static Api> {
    API.get()
}

#[no_mangle]
pub extern "C" fn mgt_rust_hip_full_residual_ffi_version() -> u32 {
    1
}

#[no_mangle]
pub unsafe extern "C" fn mgt_rust_hip_full_residual_load_library(path: *const c_char) -> c_int {
    if API.get().is_some() {
        return 0;
    }
    if path.is_null() {
        return -1;
    }
    let handle = dlopen(path, RTLD_NOW | RTLD_LOCAL);
    if handle.is_null() {
        return -2;
    }
    let loaded = Api {
        create: match symbol(handle, b"mgt_hip_full_residual_create\0") {
            Ok(value) => value,
            Err(code) => return code,
        },
        eval: match symbol(handle, b"mgt_hip_full_residual_eval\0") {
            Ok(value) => value,
            Err(code) => return code,
        },
        destroy: match symbol(handle, b"mgt_hip_full_residual_destroy\0") {
            Ok(value) => value,
            Err(code) => return code,
        },
        device_name: match symbol(handle, b"mgt_hip_full_residual_device_name\0") {
            Ok(value) => value,
            Err(code) => return code,
        },
        last_error: match symbol(handle, b"mgt_hip_full_residual_last_error\0") {
            Ok(value) => value,
            Err(code) => return code,
        },
    };
    match API.set(loaded) {
        Ok(()) => 0,
        Err(_) => 0,
    }
}

#[no_mangle]
pub unsafe extern "C" fn mgt_rust_hip_full_residual_create(
    out_handle: *mut *mut c_void,
    frame_dofs: *const c_longlong,
    frame_stiffness: *const f64,
    shell_row_ptr: *const c_longlong,
    shell_col_idx: *const c_longlong,
    shell_values: *const f64,
    spring_row_ptr: *const c_longlong,
    spring_col_idx: *const c_longlong,
    spring_values: *const f64,
    f_ext: *const f64,
    free_dofs: *const c_longlong,
    frame_element_count: c_longlong,
    n_dof: c_longlong,
    shell_nnz: c_longlong,
    spring_nnz: c_longlong,
    free_count: c_longlong,
    status: *mut MgtHipFullResidualFfiStatus,
) -> c_int {
    match api() {
        Some(loaded) => (loaded.create)(
            out_handle,
            frame_dofs,
            frame_stiffness,
            shell_row_ptr,
            shell_col_idx,
            shell_values,
            spring_row_ptr,
            spring_col_idx,
            spring_values,
            f_ext,
            free_dofs,
            frame_element_count,
            n_dof,
            shell_nnz,
            spring_nnz,
            free_count,
            status,
        ),
        None => -10,
    }
}

#[no_mangle]
pub unsafe extern "C" fn mgt_rust_hip_full_residual_eval(
    handle: *mut c_void,
    states: *const f64,
    batch_size: c_longlong,
    reps: c_int,
    residual_out: *mut f64,
    status: *mut MgtHipFullResidualFfiStatus,
) -> c_int {
    match api() {
        Some(loaded) => (loaded.eval)(handle, states, batch_size, reps, residual_out, status),
        None => -10,
    }
}

#[no_mangle]
pub unsafe extern "C" fn mgt_rust_hip_full_residual_destroy(handle: *mut c_void) -> c_int {
    match api() {
        Some(loaded) => (loaded.destroy)(handle),
        None => -10,
    }
}

#[no_mangle]
pub unsafe extern "C" fn mgt_rust_hip_full_residual_device_name(
    handle: *mut c_void,
    buffer: *mut c_char,
    buffer_len: usize,
) -> c_int {
    match api() {
        Some(loaded) => (loaded.device_name)(handle, buffer, buffer_len),
        None => -10,
    }
}

#[no_mangle]
pub unsafe extern "C" fn mgt_rust_hip_full_residual_last_error() -> *const c_char {
    match api() {
        Some(loaded) => (loaded.last_error)(),
        None => {
            let ptr = dlerror();
            if ptr.is_null() {
                b"rust HIP residual library not loaded\0".as_ptr() as *const c_char
            } else {
                CStr::from_ptr(ptr).as_ptr()
            }
        }
    }
}
