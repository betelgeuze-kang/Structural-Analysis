use std::cell::RefCell;
use std::ffi::{CStr, CString};
use std::mem::size_of;
use std::os::raw::{c_char, c_int, c_longlong, c_void};
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::ptr;
use std::sync::OnceLock;

use structural_ffi_sys as sys;

const RTLD_NOW: c_int = 2;
const RTLD_LOCAL: c_int = 0;
const ERROR_CAPACITY: usize = 512;
const LEGACY_LOAD_INVALID: c_int = -1;
const LEGACY_LOAD_OPEN_FAILED: c_int = -2;
const LEGACY_LOAD_API_FAILED: c_int = -3;
const LEGACY_NOT_LOADED: c_int = -10;
const LEGACY_PANIC: c_int = -90;

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

type GetApiFn = unsafe extern "C" fn(
    request: *const sys::SaApiRequestV1,
    out_api: *mut sys::SaApiV1,
    error: *mut sys::SaErrorBufferV1,
) -> sys::SaStatusCodeV1;

#[derive(Clone, Copy)]
struct Api {
    backend: sys::SaBackendApiV1,
}

struct LegacyHandle {
    native: *mut sys::SaFullResidualContextV1,
    order: u64,
    free_count: u64,
}

static API: OnceLock<Api> = OnceLock::new();

thread_local! {
    static LAST_ERROR: RefCell<CString> = RefCell::new(empty_c_string());
}

#[link(name = "dl")]
extern "C" {
    fn dlopen(filename: *const c_char, flag: c_int) -> *mut c_void;
    fn dlsym(handle: *mut c_void, symbol: *const c_char) -> *mut c_void;
    fn dlclose(handle: *mut c_void) -> c_int;
    fn dlerror() -> *const c_char;
}

fn empty_c_string() -> CString {
    CString::new(Vec::<u8>::new()).unwrap_or_default()
}

fn set_last_error(message: &str) {
    let sanitized = message.replace('\0', "?");
    let value = CString::new(sanitized).unwrap_or_else(|_| empty_c_string());
    LAST_ERROR.with(|slot| {
        *slot.borrow_mut() = value;
    });
}

fn clear_last_error() {
    set_last_error("");
}

fn abi_size<T>() -> u32 {
    u32::try_from(size_of::<T>()).unwrap_or(u32::MAX)
}

fn error_buffer(storage: &mut [c_char; ERROR_CAPACITY]) -> sys::SaErrorBufferV1 {
    sys::SaErrorBufferV1 {
        abi_version: sys::SA_ABI_V1_12,
        struct_size: abi_size::<sys::SaErrorBufferV1>(),
        data: storage.as_mut_ptr(),
        capacity: u64::try_from(storage.len()).unwrap_or(u64::MAX),
        required: 0,
    }
}

fn error_message(storage: &[c_char]) -> String {
    let length = storage
        .iter()
        .position(|value| *value == 0)
        .unwrap_or(storage.len());
    let bytes: Vec<u8> = storage[..length]
        .iter()
        .map(|value| value.to_ne_bytes()[0])
        .collect();
    String::from_utf8_lossy(&bytes).into_owned()
}

fn boundary(operation: impl FnOnce() -> c_int) -> c_int {
    if let Ok(code) = catch_unwind(AssertUnwindSafe(operation)) {
        code
    } else {
        set_last_error("Rust panic was contained at the compatibility ABI boundary");
        LEGACY_PANIC
    }
}

unsafe fn resolve_get_api(handle: *mut c_void) -> Option<GetApiFn> {
    // SAFETY: clearing the loader error state is required before the single symbol lookup.
    unsafe {
        let _ = dlerror();
    }
    // SAFETY: `handle` came from dlopen and the symbol name is a static NUL-terminated string.
    let pointer = unsafe { dlsym(handle, c"sa_get_api_v1".as_ptr()) };
    if pointer.is_null() {
        None
    } else {
        // SAFETY: the public product symbol has the frozen `GetApiFn` signature.
        Some(unsafe { std::mem::transmute::<*mut c_void, GetApiFn>(pointer) })
    }
}

#[allow(clippy::too_many_lines)]
unsafe fn load_library_impl(path: *const c_char) -> c_int {
    if API.get().is_some() {
        clear_last_error();
        return 0;
    }
    if path.is_null() {
        set_last_error("product library path is null");
        return LEGACY_LOAD_INVALID;
    }
    // SAFETY: the caller supplies a NUL-terminated path under the frozen legacy contract.
    let handle = unsafe { dlopen(path, RTLD_NOW | RTLD_LOCAL) };
    if handle.is_null() {
        // SAFETY: dlerror returns a loader-owned NUL-terminated message or null.
        let loader_error = unsafe { dlerror() };
        let message = if loader_error.is_null() {
            "dlopen failed without a loader diagnostic".to_owned()
        } else {
            // SAFETY: non-null dlerror values point to a valid loader-owned C string.
            unsafe { CStr::from_ptr(loader_error) }
                .to_string_lossy()
                .into_owned()
        };
        set_last_error(&message);
        return LEGACY_LOAD_OPEN_FAILED;
    }
    // SAFETY: `handle` is a live dynamic-library handle.
    let Some(get_api) = (unsafe { resolve_get_api(handle) }) else {
        set_last_error("product library does not export sa_get_api_v1");
        // SAFETY: the failed load has not published any function pointer.
        unsafe {
            let _ = dlclose(handle);
        }
        return LEGACY_LOAD_API_FAILED;
    };

    let request = sys::SaApiRequestV1 {
        abi_version: sys::SA_ABI_V1_12,
        struct_size: abi_size::<sys::SaApiRequestV1>(),
        flags: 0,
        reserved: [0; 3],
    };
    let mut main = sys::SaApiV1 {
        abi_version: sys::SA_ABI_V1_12,
        ..sys::SaApiV1::default()
    };
    let mut storage = [0_i8; ERROR_CAPACITY];
    let mut error = error_buffer(&mut storage);
    // SAFETY: all descriptors and error storage are live and correctly sized.
    let status = unsafe { get_api(&request, &mut main, &mut error) };
    if status != sys::SA_OK
        || main.abi_version != sys::SA_ABI_V1_12
        || main.struct_size as usize != size_of::<sys::SaApiV1>()
        || main.capabilities & sys::SA_CAPABILITY_BACKEND_SELECTOR == 0
    {
        let message = if status == sys::SA_OK {
            "product library returned an invalid ABI v1.12 table".to_owned()
        } else {
            error_message(&storage)
        };
        set_last_error(&message);
        // SAFETY: no table has been published, so the library can be closed.
        unsafe {
            let _ = dlclose(handle);
        }
        return LEGACY_LOAD_API_FAILED;
    }
    let Some(select_backend) = main.backend_get_api else {
        set_last_error("product library omitted the v1.12 backend selector");
        // SAFETY: no table has been published, so the library can be closed.
        unsafe {
            let _ = dlclose(handle);
        }
        return LEGACY_LOAD_API_FAILED;
    };
    let backend_request = sys::SaBackendRequestV1 {
        abi_version: sys::SA_ABI_V1_12,
        struct_size: abi_size::<sys::SaBackendRequestV1>(),
        execution_backend: sys::SA_EXECUTION_BACKEND_HIP,
        device_id: 0,
        flags: 0,
        reserved: [0; 2],
    };
    let mut backend = sys::SaBackendApiV1 {
        abi_version: sys::SA_ABI_V1_12,
        ..sys::SaBackendApiV1::default()
    };
    let mut storage = [0_i8; ERROR_CAPACITY];
    let mut error = error_buffer(&mut storage);
    // SAFETY: all descriptors and error storage are live and correctly sized.
    let status = unsafe { select_backend(&backend_request, &mut backend, &mut error) };
    let backend_valid = status == sys::SA_OK
        && backend.abi_version == sys::SA_ABI_V1_12
        && backend.struct_size as usize == size_of::<sys::SaBackendApiV1>()
        && backend.execution_backend == sys::SA_EXECUTION_BACKEND_HIP
        && backend.device_id == 0
        && backend.capabilities & sys::SA_BACKEND_CAPABILITY_FULL_RESIDUAL != 0
        && backend.full_residual_create.is_some()
        && backend.full_residual_evaluate.is_some()
        && backend.full_residual_destroy.is_some()
        && backend.full_residual_device_name_size.is_some()
        && backend.full_residual_device_name_write.is_some()
        && backend.reserved == [0; 2];
    if !backend_valid {
        let message = if status == sys::SA_OK {
            "product library returned an invalid HIP backend table".to_owned()
        } else {
            error_message(&storage)
        };
        set_last_error(&message);
        // SAFETY: no table has been published, so the library can be closed.
        unsafe {
            let _ = dlclose(handle);
        }
        return LEGACY_LOAD_API_FAILED;
    }
    if API.set(Api { backend }).is_ok() {
        clear_last_error();
        // The winning process-lifetime table deliberately keeps its library handle open.
        0
    } else {
        // SAFETY: another thread published the winning handle and table.
        unsafe {
            let _ = dlclose(handle);
        }
        clear_last_error();
        0
    }
}

fn input_view<T>(data: *const T, length: u64, element_type: u32) -> sys::SaBufferViewV1 {
    sys::SaBufferViewV1 {
        abi_version: sys::SA_ABI_V1_12,
        struct_size: abi_size::<sys::SaBufferViewV1>(),
        data: if length == 0 {
            ptr::null()
        } else {
            data.cast::<c_void>()
        },
        length,
        stride_bytes: u64::try_from(size_of::<T>()).unwrap_or(u64::MAX),
        element_type,
        memory_space: sys::SA_MEMORY_SPACE_HOST,
        device_id: -1,
        flags: 0,
    }
}

fn output_view(data: *mut f64, length: u64) -> sys::SaMutBufferViewV1 {
    sys::SaMutBufferViewV1 {
        abi_version: sys::SA_ABI_V1_12,
        struct_size: abi_size::<sys::SaMutBufferViewV1>(),
        data: data.cast::<c_void>(),
        length,
        stride_bytes: u64::try_from(size_of::<f64>()).unwrap_or(u64::MAX),
        element_type: sys::SA_ELEMENT_TYPE_F64,
        memory_space: sys::SA_MEMORY_SPACE_HOST,
        device_id: -1,
        flags: 0,
    }
}

fn raw_status() -> sys::SaFullResidualStatusV1 {
    sys::SaFullResidualStatusV1 {
        abi_version: sys::SA_ABI_V1_12,
        struct_size: abi_size::<sys::SaFullResidualStatusV1>(),
        ..sys::SaFullResidualStatusV1::default()
    }
}

fn legacy_status(raw: &sys::SaFullResidualStatusV1, code: c_int) -> MgtHipFullResidualFfiStatus {
    MgtHipFullResidualFfiStatus {
        code,
        frame_element_count: c_longlong::try_from(raw.frame_element_count)
            .unwrap_or(c_longlong::MAX),
        n_dof: c_longlong::try_from(raw.order).unwrap_or(c_longlong::MAX),
        free_count: c_longlong::try_from(raw.free_dof_count).unwrap_or(c_longlong::MAX),
        shell_nnz: c_longlong::try_from(raw.shell_nonzeros).unwrap_or(c_longlong::MAX),
        spring_nnz: c_longlong::try_from(raw.spring_nonzeros).unwrap_or(c_longlong::MAX),
        batch_size: c_longlong::try_from(raw.batch_size).unwrap_or(c_longlong::MAX),
        reps: c_int::try_from(raw.repetitions).unwrap_or(c_int::MAX),
        device_id: raw.device_id,
        eval_buffers_reused: i32::from(raw.flags & sys::SA_FULL_RESIDUAL_EVAL_BUFFERS_REUSED != 0),
        operator_buffers_device_resident: i32::from(
            raw.flags & sys::SA_FULL_RESIDUAL_OPERATOR_DEVICE_RESIDENT != 0,
        ),
        kernel_elapsed_ms_total: raw.kernel_elapsed_ms_total,
        kernel_elapsed_ms_mean: raw.kernel_elapsed_ms_mean,
        output_abs_sum: raw.output_abs_sum,
        output_max_abs: raw.output_max_abs,
    }
}

unsafe fn publish_status(
    destination: *mut MgtHipFullResidualFfiStatus,
    raw: &sys::SaFullResidualStatusV1,
    code: c_int,
) {
    if !destination.is_null() {
        // SAFETY: the legacy caller supplied writable status storage.
        unsafe {
            destination.write(legacy_status(raw, code));
        }
    }
}

fn checked_positive(value: c_longlong, label: &str) -> Option<u64> {
    match u64::try_from(value) {
        Ok(converted) if converted > 0 => Some(converted),
        _ => {
            set_last_error(label);
            None
        }
    }
}

fn checked_nonnegative(value: c_longlong, label: &str) -> Option<u64> {
    if let Ok(converted) = u64::try_from(value) {
        Some(converted)
    } else {
        set_last_error(label);
        None
    }
}

#[no_mangle]
pub extern "C" fn mgt_rust_hip_full_residual_ffi_version() -> u32 {
    1
}

#[no_mangle]
/// Load one product shared library and resolve only its `sa_get_api_v1` symbol.
///
/// # Safety
///
/// `path` must be null or point to a readable NUL-terminated path for this call.
pub unsafe extern "C" fn mgt_rust_hip_full_residual_load_library(path: *const c_char) -> c_int {
    boundary(|| {
        // SAFETY: all loader pointer validation is performed by `load_library_impl`.
        unsafe { load_library_impl(path) }
    })
}

#[allow(clippy::too_many_arguments)]
#[allow(clippy::too_many_lines)]
unsafe fn create_impl(
    out_handle: *mut *mut c_void,
    frame_dofs: *const c_longlong,
    frame_stiffness: *const f64,
    shell_row_ptr: *const c_longlong,
    shell_col_idx: *const c_longlong,
    shell_values: *const f64,
    spring_row_ptr: *const c_longlong,
    spring_col_idx: *const c_longlong,
    spring_values: *const f64,
    external_force: *const f64,
    free_dofs: *const c_longlong,
    frame_element_count: c_longlong,
    order: c_longlong,
    shell_nonzeros: c_longlong,
    spring_nonzeros: c_longlong,
    free_count: c_longlong,
    legacy_status_out: *mut MgtHipFullResidualFfiStatus,
) -> c_int {
    let Some(api) = API.get() else {
        set_last_error("product HIP backend table is not loaded");
        return LEGACY_NOT_LOADED;
    };
    if out_handle.is_null() {
        set_last_error("out_handle pointer is null");
        return LEGACY_LOAD_INVALID;
    }
    // SAFETY: `out_handle` was validated non-null and is caller-owned writable storage.
    unsafe {
        out_handle.write(ptr::null_mut());
    }
    let Some(frame_count) = checked_positive(frame_element_count, "frame count must be positive")
    else {
        return LEGACY_LOAD_INVALID;
    };
    let Some(order) = checked_positive(order, "order must be positive") else {
        return LEGACY_LOAD_INVALID;
    };
    let Some(shell_nonzeros) = checked_nonnegative(shell_nonzeros, "shell nnz must be nonnegative")
    else {
        return LEGACY_LOAD_INVALID;
    };
    let Some(spring_nonzeros) =
        checked_nonnegative(spring_nonzeros, "spring nnz must be nonnegative")
    else {
        return LEGACY_LOAD_INVALID;
    };
    let Some(free_count) = checked_positive(free_count, "free count must be positive") else {
        return LEGACY_LOAD_INVALID;
    };
    let Some(frame_dof_count) = frame_count.checked_mul(12) else {
        set_last_error("frame dof count overflows");
        return LEGACY_LOAD_INVALID;
    };
    let Some(frame_matrix_count) = frame_count.checked_mul(144) else {
        set_last_error("frame matrix count overflows");
        return LEGACY_LOAD_INVALID;
    };
    let Some(row_count) = order.checked_add(1) else {
        set_last_error("CSR row count overflows");
        return LEGACY_LOAD_INVALID;
    };
    let descriptor = sys::SaFullResidualOperatorV1 {
        abi_version: sys::SA_ABI_V1_12,
        struct_size: abi_size::<sys::SaFullResidualOperatorV1>(),
        frame_dofs: input_view(
            frame_dofs.cast::<u64>(),
            frame_dof_count,
            sys::SA_ELEMENT_TYPE_U64,
        ),
        frame_stiffness: input_view(
            frame_stiffness,
            frame_matrix_count,
            sys::SA_ELEMENT_TYPE_F64,
        ),
        shell_row_offsets: input_view(
            shell_row_ptr.cast::<u64>(),
            row_count,
            sys::SA_ELEMENT_TYPE_U64,
        ),
        shell_column_indices: input_view(
            shell_col_idx.cast::<u64>(),
            shell_nonzeros,
            sys::SA_ELEMENT_TYPE_U64,
        ),
        shell_values: input_view(shell_values, shell_nonzeros, sys::SA_ELEMENT_TYPE_F64),
        spring_row_offsets: input_view(
            spring_row_ptr.cast::<u64>(),
            row_count,
            sys::SA_ELEMENT_TYPE_U64,
        ),
        spring_column_indices: input_view(
            spring_col_idx.cast::<u64>(),
            spring_nonzeros,
            sys::SA_ELEMENT_TYPE_U64,
        ),
        spring_values: input_view(spring_values, spring_nonzeros, sys::SA_ELEMENT_TYPE_F64),
        external_force: input_view(external_force, order, sys::SA_ELEMENT_TYPE_F64),
        free_dofs: input_view(
            free_dofs.cast::<u64>(),
            free_count,
            sys::SA_ELEMENT_TYPE_U64,
        ),
        frame_element_count: frame_count,
        order,
        shell_nonzeros,
        spring_nonzeros,
        free_dof_count: free_count,
        reserved: [0; 2],
    };
    let mut native = ptr::null_mut();
    let mut raw_receipt = raw_status();
    let mut storage = [0_i8; ERROR_CAPACITY];
    let mut error = error_buffer(&mut storage);
    let Some(create) = api.backend.full_residual_create else {
        set_last_error("HIP backend table omitted full_residual_create");
        return LEGACY_LOAD_API_FAILED;
    };
    // SAFETY: the legacy pointers are described without dereference and the product ABI validates
    // every pointer, extent, index, and value before publishing a deep-copied context.
    let code = unsafe { create(&descriptor, &mut native, &mut raw_receipt, &mut error) };
    if code != sys::SA_OK || native.is_null() {
        let message = if code == sys::SA_OK {
            "product returned a null full-residual context".to_owned()
        } else {
            error_message(&storage)
        };
        set_last_error(&message);
        // SAFETY: status is optional caller-owned storage under the legacy contract.
        unsafe {
            publish_status(legacy_status_out, &raw_receipt, -2);
        }
        return -2;
    }
    let wrapper = Box::new(LegacyHandle {
        native,
        order,
        free_count,
    });
    // SAFETY: `out_handle` was validated and receives exclusive ownership of the boxed wrapper.
    unsafe {
        out_handle.write(Box::into_raw(wrapper).cast::<c_void>());
        publish_status(legacy_status_out, &raw_receipt, 0);
    }
    clear_last_error();
    0
}

#[no_mangle]
#[allow(clippy::too_many_arguments)]
/// Create a legacy opaque wrapper around a product-owned HIP full-residual context.
///
/// # Safety
///
/// Every pointer must satisfy the frozen legacy lengths derived from the scalar dimensions;
/// `out_handle` and optional status storage must be writable for this call.
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
    external_force: *const f64,
    free_dofs: *const c_longlong,
    frame_element_count: c_longlong,
    order: c_longlong,
    shell_nonzeros: c_longlong,
    spring_nonzeros: c_longlong,
    free_count: c_longlong,
    legacy_status_out: *mut MgtHipFullResidualFfiStatus,
) -> c_int {
    boundary(|| {
        // SAFETY: `create_impl` validates scalar metadata before forwarding raw descriptors.
        unsafe {
            create_impl(
                out_handle,
                frame_dofs,
                frame_stiffness,
                shell_row_ptr,
                shell_col_idx,
                shell_values,
                spring_row_ptr,
                spring_col_idx,
                spring_values,
                external_force,
                free_dofs,
                frame_element_count,
                order,
                shell_nonzeros,
                spring_nonzeros,
                free_count,
                legacy_status_out,
            )
        }
    })
}

unsafe fn evaluate_impl(
    handle: *mut c_void,
    states: *const f64,
    batch_size: c_longlong,
    repetitions: c_int,
    residual_out: *mut f64,
    legacy_status_out: *mut MgtHipFullResidualFfiStatus,
) -> c_int {
    let Some(api) = API.get() else {
        set_last_error("product HIP backend table is not loaded");
        return LEGACY_NOT_LOADED;
    };
    if handle.is_null() || states.is_null() || residual_out.is_null() {
        set_last_error("handle, state, or residual pointer is null");
        return -3;
    }
    let Some(batch_size) = checked_positive(batch_size, "batch size must be positive") else {
        return -3;
    };
    let repetitions = u32::try_from(repetitions.max(1)).unwrap_or(1);
    // SAFETY: a successful legacy create returned this exclusive boxed wrapper pointer.
    let wrapper = unsafe { &mut *handle.cast::<LegacyHandle>() };
    let Some(state_count) = batch_size.checked_mul(wrapper.order) else {
        set_last_error("state count overflows");
        return -3;
    };
    let Some(output_count) = batch_size.checked_mul(wrapper.free_count) else {
        set_last_error("residual count overflows");
        return -3;
    };
    let config = sys::SaFullResidualEvalConfigV1 {
        abi_version: sys::SA_ABI_V1_12,
        struct_size: abi_size::<sys::SaFullResidualEvalConfigV1>(),
        batch_size,
        repetitions,
        flags: 0,
        reserved: [0; 2],
    };
    let state_view = input_view(states, state_count, sys::SA_ELEMENT_TYPE_F64);
    let residual_view = output_view(residual_out, output_count);
    let mut raw_receipt = raw_status();
    let mut storage = [0_i8; ERROR_CAPACITY];
    let mut error = error_buffer(&mut storage);
    let Some(evaluate) = api.backend.full_residual_evaluate else {
        set_last_error("HIP backend table omitted full_residual_evaluate");
        return -3;
    };
    // SAFETY: product ABI validates the live context and every caller-owned buffer descriptor.
    let code = unsafe {
        evaluate(
            wrapper.native,
            &config,
            &state_view,
            &residual_view,
            &mut raw_receipt,
            &mut error,
        )
    };
    if code != sys::SA_OK {
        set_last_error(&error_message(&storage));
        // SAFETY: status is optional caller-owned storage under the legacy contract.
        unsafe {
            publish_status(legacy_status_out, &raw_receipt, -3);
        }
        return -3;
    }
    // SAFETY: status is optional caller-owned storage under the legacy contract.
    unsafe {
        publish_status(legacy_status_out, &raw_receipt, 0);
    }
    clear_last_error();
    0
}

#[no_mangle]
/// Evaluate one legacy batch through the selected product HIP backend.
///
/// # Safety
///
/// `handle` must be live and exclusively mutable. State, residual, and optional status pointers
/// must cover the frozen lengths derived from the context and `batch_size`.
pub unsafe extern "C" fn mgt_rust_hip_full_residual_eval(
    handle: *mut c_void,
    states: *const f64,
    batch_size: c_longlong,
    repetitions: c_int,
    residual_out: *mut f64,
    legacy_status_out: *mut MgtHipFullResidualFfiStatus,
) -> c_int {
    boundary(|| {
        // SAFETY: `evaluate_impl` validates scalar metadata before forwarding raw descriptors.
        unsafe {
            evaluate_impl(
                handle,
                states,
                batch_size,
                repetitions,
                residual_out,
                legacy_status_out,
            )
        }
    })
}

unsafe fn destroy_impl(handle: *mut c_void) -> c_int {
    if handle.is_null() {
        clear_last_error();
        return 0;
    }
    let Some(api) = API.get() else {
        set_last_error("product HIP backend table is not loaded");
        return LEGACY_NOT_LOADED;
    };
    let Some(destroy) = api.backend.full_residual_destroy else {
        set_last_error("HIP backend table omitted full_residual_destroy");
        return -3;
    };
    // SAFETY: a successful legacy create returned this exclusive boxed wrapper pointer.
    let wrapper = unsafe { &mut *handle.cast::<LegacyHandle>() };
    let mut storage = [0_i8; ERROR_CAPACITY];
    let mut error = error_buffer(&mut storage);
    // SAFETY: the wrapper owns this native context until successful destruction.
    let code = unsafe { destroy(wrapper.native, &mut error) };
    if code != sys::SA_OK {
        set_last_error(&error_message(&storage));
        return -3;
    }
    // SAFETY: native destruction succeeded and the wrapper pointer is consumed exactly once.
    unsafe {
        drop(Box::from_raw(handle.cast::<LegacyHandle>()));
    }
    clear_last_error();
    0
}

#[no_mangle]
/// Destroy a legacy wrapper and its product-owned context.
///
/// # Safety
///
/// A non-null handle must be live, exclusively owned, and passed exactly once.
pub unsafe extern "C" fn mgt_rust_hip_full_residual_destroy(handle: *mut c_void) -> c_int {
    boundary(|| {
        // SAFETY: `destroy_impl` validates null and consumes only a live legacy wrapper.
        unsafe { destroy_impl(handle) }
    })
}

unsafe fn device_name_impl(handle: *mut c_void, buffer: *mut c_char, buffer_len: usize) -> c_int {
    let Some(api) = API.get() else {
        set_last_error("product HIP backend table is not loaded");
        return LEGACY_NOT_LOADED;
    };
    if handle.is_null() || buffer.is_null() || buffer_len == 0 {
        set_last_error("handle or device-name buffer is invalid");
        return LEGACY_LOAD_INVALID;
    }
    // SAFETY: a successful legacy create returned this wrapper pointer.
    let wrapper = unsafe { &*handle.cast::<LegacyHandle>() };
    let Some(write) = api.backend.full_residual_device_name_write else {
        set_last_error("HIP backend table omitted full_residual_device_name_write");
        return -3;
    };
    let mut storage = [0_i8; ERROR_CAPACITY];
    let mut error = error_buffer(&mut storage);
    // SAFETY: product ABI validates the context and caller-owned output capacity.
    let code = unsafe {
        write(
            wrapper.native,
            buffer,
            u64::try_from(buffer_len).unwrap_or(u64::MAX),
            &mut error,
        )
    };
    if code != sys::SA_OK {
        set_last_error(&error_message(&storage));
        return -3;
    }
    clear_last_error();
    0
}

#[no_mangle]
/// Copy the immutable product device name into legacy caller-owned storage.
///
/// # Safety
///
/// `handle` must be live; `buffer` must be writable for `buffer_len` bytes.
pub unsafe extern "C" fn mgt_rust_hip_full_residual_device_name(
    handle: *mut c_void,
    buffer: *mut c_char,
    buffer_len: usize,
) -> c_int {
    boundary(|| {
        // SAFETY: `device_name_impl` validates the legacy pointers and capacity.
        unsafe { device_name_impl(handle, buffer, buffer_len) }
    })
}

#[no_mangle]
pub extern "C" fn mgt_rust_hip_full_residual_last_error() -> *const c_char {
    match catch_unwind(AssertUnwindSafe(|| {
        LAST_ERROR.with(|slot| slot.borrow().as_ptr())
    })) {
        Ok(pointer) => pointer,
        Err(_) => c"Rust panic while reading compatibility error".as_ptr(),
    }
}

#[cfg(test)]
mod tests {
    use super::{error_message, legacy_status, raw_status, MgtHipFullResidualFfiStatus};
    use structural_ffi_sys as sys;

    #[test]
    fn legacy_status_mapping_preserves_residency_and_no_fallback_metrics() {
        let mut raw = raw_status();
        raw.frame_element_count = 4;
        raw.order = 30;
        raw.free_dof_count = 7;
        raw.shell_nonzeros = 11;
        raw.spring_nonzeros = 13;
        raw.batch_size = 2;
        raw.repetitions = 5;
        raw.device_id = 0;
        raw.flags = sys::SA_FULL_RESIDUAL_EVAL_BUFFERS_REUSED
            | sys::SA_FULL_RESIDUAL_OPERATOR_DEVICE_RESIDENT;
        raw.kernel_elapsed_ms_total = 8.0;
        raw.kernel_elapsed_ms_mean = 1.6;
        raw.output_abs_sum = 17.0;
        raw.output_max_abs = 9.0;
        let legacy: MgtHipFullResidualFfiStatus = legacy_status(&raw, 0);
        assert_eq!(legacy.frame_element_count, 4);
        assert_eq!(legacy.n_dof, 30);
        assert_eq!(legacy.free_count, 7);
        assert_eq!(legacy.eval_buffers_reused, 1);
        assert_eq!(legacy.operator_buffers_device_resident, 1);
        assert_eq!(legacy.kernel_elapsed_ms_total.to_bits(), 8.0_f64.to_bits());
        assert_eq!(legacy.output_max_abs.to_bits(), 9.0_f64.to_bits());
    }

    #[test]
    fn bounded_error_storage_decodes_without_reading_past_nul() {
        let storage = [97_i8, 98_i8, 0_i8, 99_i8];
        assert_eq!(error_message(&storage), "ab");
    }
}
