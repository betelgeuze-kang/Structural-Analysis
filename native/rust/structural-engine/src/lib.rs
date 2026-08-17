#![deny(unsafe_op_in_unsafe_fn)]

use std::ffi::CStr;
use std::marker::PhantomData;
use std::ptr::NonNull;
use std::rc::Rc;

pub use structural_engine_sys as sys;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ExecutionMode {
    Audited,
    Performance,
}

impl ExecutionMode {
    const fn as_raw(self) -> u32 {
        match self {
            Self::Audited => sys::EXECUTION_MODE_AUDITED,
            Self::Performance => sys::EXECUTION_MODE_PERFORMANCE,
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct EngineConfig {
    pub execution_mode: ExecutionMode,
    pub requested_device_index: i32,
}

impl Default for EngineConfig {
    fn default() -> Self {
        Self {
            execution_mode: ExecutionMode::Audited,
            requested_device_index: -1,
        }
    }
}

impl EngineConfig {
    fn as_raw(self) -> sys::EngineConfig {
        sys::EngineConfig {
            execution_mode: self.execution_mode.as_raw(),
            requested_device_index: self.requested_device_index,
            ..sys::EngineConfig::default()
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ApiInfo {
    pub abi_version_major: u32,
    pub abi_version_minor: u32,
    pub capability_bits: u64,
    pub implementation_name: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Error {
    AbiMismatch {
        expected_major: u32,
        expected_minor_at_most: u32,
        actual_major: u32,
        actual_minor: u32,
    },
    Native {
        status: sys::Status,
        message: String,
    },
    NullHandle,
    UnknownStatus(i32),
    InvalidImplementationName,
    InvalidNativeShape {
        dof_count: usize,
        member_end_force_count: usize,
    },
    LoadLength {
        expected: usize,
        actual: usize,
    },
}

pub trait EngineApi: Clone {
    unsafe fn get_api_info(&self, out_info: *mut sys::ApiInfo) -> i32;
    unsafe fn create_engine(
        &self,
        config: *const sys::EngineConfig,
        out_engine: *mut *mut sys::Engine,
    ) -> i32;
    unsafe fn destroy_engine(&self, engine: *mut sys::Engine);
    unsafe fn engine_capabilities(
        &self,
        engine: *const sys::Engine,
        out_capabilities: *mut u64,
    ) -> i32;
    unsafe fn engine_last_error(
        &self,
        engine: *const sys::Engine,
        buffer: *mut std::ffi::c_char,
        buffer_capacity: usize,
        out_required_size: *mut usize,
    ) -> i32;

    unsafe fn compile_linear_frame3d(
        &self,
        _engine: *const sys::Engine,
        _input: *const sys::LinearFrame3DModelInput,
        _out_model: *mut *mut sys::LinearFrame3DModel,
    ) -> i32 {
        sys::Status::Unsupported as i32
    }

    unsafe fn destroy_linear_frame3d(&self, _model: *mut sys::LinearFrame3DModel) {}

    unsafe fn linear_frame3d_sizes(
        &self,
        _model: *const sys::LinearFrame3DModel,
        _out_dof_count: *mut usize,
        _out_member_end_force_count: *mut usize,
    ) -> i32 {
        sys::Status::Unsupported as i32
    }

    unsafe fn solve_linear_frame3d(
        &self,
        _model: *const sys::LinearFrame3DModel,
        _load_vector_kn: *const f64,
        _load_count: usize,
        _out_result: *mut sys::LinearFrame3DResultBuffers,
    ) -> i32 {
        sys::Status::Unsupported as i32
    }
}

#[cfg(feature = "native-link")]
#[derive(Clone, Copy, Debug, Default)]
pub struct NativeApi;

#[cfg(feature = "native-link")]
impl EngineApi for NativeApi {
    unsafe fn get_api_info(&self, out_info: *mut sys::ApiInfo) -> i32 {
        unsafe { sys::sa_get_api_info(out_info) }
    }

    unsafe fn create_engine(
        &self,
        config: *const sys::EngineConfig,
        out_engine: *mut *mut sys::Engine,
    ) -> i32 {
        unsafe { sys::sa_engine_create(config, out_engine) }
    }

    unsafe fn destroy_engine(&self, engine: *mut sys::Engine) {
        unsafe { sys::sa_engine_destroy(engine) }
    }

    unsafe fn engine_capabilities(
        &self,
        engine: *const sys::Engine,
        out_capabilities: *mut u64,
    ) -> i32 {
        unsafe { sys::sa_engine_capabilities(engine, out_capabilities) }
    }

    unsafe fn engine_last_error(
        &self,
        engine: *const sys::Engine,
        buffer: *mut std::ffi::c_char,
        buffer_capacity: usize,
        out_required_size: *mut usize,
    ) -> i32 {
        unsafe {
            sys::sa_engine_last_error(engine, buffer, buffer_capacity, out_required_size)
        }
    }

    unsafe fn compile_linear_frame3d(
        &self,
        engine: *const sys::Engine,
        input: *const sys::LinearFrame3DModelInput,
        out_model: *mut *mut sys::LinearFrame3DModel,
    ) -> i32 {
        unsafe { sys::sa_linear_frame3d_model_compile(engine, input, out_model) }
    }

    unsafe fn destroy_linear_frame3d(&self, model: *mut sys::LinearFrame3DModel) {
        unsafe { sys::sa_linear_frame3d_model_destroy(model) }
    }

    unsafe fn linear_frame3d_sizes(
        &self,
        model: *const sys::LinearFrame3DModel,
        out_dof_count: *mut usize,
        out_member_end_force_count: *mut usize,
    ) -> i32 {
        unsafe {
            sys::sa_linear_frame3d_model_sizes(
                model,
                out_dof_count,
                out_member_end_force_count,
            )
        }
    }

    unsafe fn solve_linear_frame3d(
        &self,
        model: *const sys::LinearFrame3DModel,
        load_vector_kn: *const f64,
        load_count: usize,
        out_result: *mut sys::LinearFrame3DResultBuffers,
    ) -> i32 {
        unsafe {
            sys::sa_linear_frame3d_solve(
                model,
                load_vector_kn,
                load_count,
                out_result,
            )
        }
    }
}

pub fn query_api_info<A: EngineApi>(api: &A) -> Result<ApiInfo, Error> {
    let mut raw = sys::ApiInfo::default();
    let status = unsafe { api.get_api_info(&mut raw) };
    ensure_ok(api, std::ptr::null(), status)?;
    if raw.abi_version_major != sys::ABI_VERSION_MAJOR
        || raw.abi_version_minor < sys::ABI_VERSION_MINOR
    {
        return Err(Error::AbiMismatch {
            expected_major: sys::ABI_VERSION_MAJOR,
            expected_minor_at_most: sys::ABI_VERSION_MINOR,
            actual_major: raw.abi_version_major,
            actual_minor: raw.abi_version_minor,
        });
    }
    if raw.implementation_name.is_null() {
        return Err(Error::InvalidImplementationName);
    }
    let implementation_name = unsafe { CStr::from_ptr(raw.implementation_name) }
        .to_str()
        .map_err(|_| Error::InvalidImplementationName)?
        .to_owned();
    Ok(ApiInfo {
        abi_version_major: raw.abi_version_major,
        abi_version_minor: raw.abi_version_minor,
        capability_bits: raw.capability_bits,
        implementation_name,
    })
}

pub struct LinearFrame3DInput<'a> {
    pub nodes: &'a [sys::LinearFrame3DNode],
    pub sections: &'a [sys::LinearFrame3DSection],
    pub members: &'a [sys::LinearFrame3DMember],
    pub restrained_dofs: &'a [u32],
}

impl LinearFrame3DInput<'_> {
    fn as_raw(&self) -> sys::LinearFrame3DModelInput {
        sys::LinearFrame3DModelInput {
            nodes: self.nodes.as_ptr(),
            node_count: self.nodes.len(),
            sections: self.sections.as_ptr(),
            section_count: self.sections.len(),
            members: self.members.as_ptr(),
            member_count: self.members.len(),
            restrained_dofs: self.restrained_dofs.as_ptr(),
            restrained_dof_count: self.restrained_dofs.len(),
            ..sys::LinearFrame3DModelInput::default()
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct LinearFrame3DResult {
    pub displacements: Vec<f64>,
    pub reactions: Vec<f64>,
    pub member_end_forces: Vec<f64>,
}

pub struct Engine<A: EngineApi> {
    api: A,
    handle: NonNull<sys::Engine>,
    _not_send_or_sync: PhantomData<Rc<()>>,
}

impl<A: EngineApi> Engine<A> {
    pub fn create(api: A, config: EngineConfig) -> Result<Self, Error> {
        let _ = query_api_info(&api)?;
        let raw_config = config.as_raw();
        let mut raw_handle = std::ptr::null_mut();
        let status = unsafe { api.create_engine(&raw_config, &mut raw_handle) };
        ensure_ok(&api, raw_handle, status)?;
        let handle = NonNull::new(raw_handle).ok_or(Error::NullHandle)?;
        Ok(Self {
            api,
            handle,
            _not_send_or_sync: PhantomData,
        })
    }

    pub fn capabilities(&self) -> Result<u64, Error> {
        let mut capability_bits = 0;
        let status = unsafe {
            self.api
                .engine_capabilities(self.handle.as_ptr(), &mut capability_bits)
        };
        ensure_ok(&self.api, self.handle.as_ptr(), status)?;
        Ok(capability_bits)
    }

    pub fn compile_linear_frame3d<'engine>(
        &'engine self,
        input: &LinearFrame3DInput<'_>,
    ) -> Result<LinearFrame3DModel<'engine, A>, Error> {
        let raw_input = input.as_raw();
        let mut raw_model = std::ptr::null_mut();
        let status = unsafe {
            self.api.compile_linear_frame3d(
                self.handle.as_ptr(),
                &raw_input,
                &mut raw_model,
            )
        };
        ensure_ok(&self.api, self.handle.as_ptr(), status)?;
        let handle = NonNull::new(raw_model).ok_or(Error::NullHandle)?;
        let mut compiled = LinearFrame3DModel {
            api: self.api.clone(),
            engine: self.handle,
            handle,
            dof_count: 0,
            member_end_force_count: 0,
            _engine_lifetime: PhantomData,
            _not_send_or_sync: PhantomData,
        };
        let status = unsafe {
            compiled.api.linear_frame3d_sizes(
                compiled.handle.as_ptr(),
                &mut compiled.dof_count,
                &mut compiled.member_end_force_count,
            )
        };
        ensure_ok(&compiled.api, compiled.engine.as_ptr(), status)?;
        if compiled.dof_count == 0
            || compiled.member_end_force_count == 0
            || compiled.member_end_force_count % 12 != 0
        {
            return Err(Error::InvalidNativeShape {
                dof_count: compiled.dof_count,
                member_end_force_count: compiled.member_end_force_count,
            });
        }
        Ok(compiled)
    }

    pub fn as_raw(&self) -> *mut sys::Engine {
        self.handle.as_ptr()
    }
}

impl<A: EngineApi> Drop for Engine<A> {
    fn drop(&mut self) {
        unsafe { self.api.destroy_engine(self.handle.as_ptr()) }
    }
}

pub struct LinearFrame3DModel<'engine, A: EngineApi> {
    api: A,
    engine: NonNull<sys::Engine>,
    handle: NonNull<sys::LinearFrame3DModel>,
    dof_count: usize,
    member_end_force_count: usize,
    _engine_lifetime: PhantomData<&'engine Engine<A>>,
    _not_send_or_sync: PhantomData<Rc<()>>,
}

impl<A: EngineApi> LinearFrame3DModel<'_, A> {
    pub fn dof_count(&self) -> usize {
        self.dof_count
    }

    pub fn member_count(&self) -> usize {
        self.member_end_force_count / 12
    }

    pub fn solve(&self, load_vector_kn: &[f64]) -> Result<LinearFrame3DResult, Error> {
        if load_vector_kn.len() != self.dof_count {
            return Err(Error::LoadLength {
                expected: self.dof_count,
                actual: load_vector_kn.len(),
            });
        }
        let mut result = LinearFrame3DResult {
            displacements: vec![0.0; self.dof_count],
            reactions: vec![0.0; self.dof_count],
            member_end_forces: vec![0.0; self.member_end_force_count],
        };
        let mut raw_result = sys::LinearFrame3DResultBuffers {
            displacements: result.displacements.as_mut_ptr(),
            displacement_count: result.displacements.len(),
            reactions: result.reactions.as_mut_ptr(),
            reaction_count: result.reactions.len(),
            member_end_forces: result.member_end_forces.as_mut_ptr(),
            member_end_force_count: result.member_end_forces.len(),
            ..sys::LinearFrame3DResultBuffers::default()
        };
        let status = unsafe {
            self.api.solve_linear_frame3d(
                self.handle.as_ptr(),
                load_vector_kn.as_ptr(),
                load_vector_kn.len(),
                &mut raw_result,
            )
        };
        ensure_ok(&self.api, self.engine.as_ptr(), status)?;
        Ok(result)
    }

    pub fn as_raw(&self) -> *mut sys::LinearFrame3DModel {
        self.handle.as_ptr()
    }
}

impl<A: EngineApi> Drop for LinearFrame3DModel<'_, A> {
    fn drop(&mut self) {
        unsafe { self.api.destroy_linear_frame3d(self.handle.as_ptr()) }
    }
}

fn ensure_ok<A: EngineApi>(
    api: &A,
    engine: *const sys::Engine,
    raw_status: i32,
) -> Result<(), Error> {
    let status = sys::Status::from_raw(raw_status).ok_or(Error::UnknownStatus(raw_status))?;
    if status == sys::Status::Ok {
        return Ok(());
    }
    Err(Error::Native {
        status,
        message: read_last_error(api, engine),
    })
}

fn read_last_error<A: EngineApi>(api: &A, engine: *const sys::Engine) -> String {
    let mut required = 0_usize;
    let probe_status = unsafe {
        api.engine_last_error(
            engine,
            std::ptr::null_mut(),
            0,
            &mut required,
        )
    };
    match sys::Status::from_raw(probe_status) {
        Some(sys::Status::Ok | sys::Status::BufferTooSmall) => {}
        Some(status) => {
            return format!(
                "failed to query native error size: status {status:?}; required buffer size {required}"
            )
        }
        None => {
            return format!(
                "failed to query native error size: unknown status {probe_status}; required buffer size {required}"
            )
        }
    }

    if required == 0 {
        return String::new();
    }

    for _ in 0..3 {
        let mut buffer = vec![0_u8; required];
        let mut next_required = 0_usize;
        let read_status = unsafe {
            api.engine_last_error(
                engine,
                buffer.as_mut_ptr().cast(),
                buffer.len(),
                &mut next_required,
            )
        };
        match sys::Status::from_raw(read_status) {
            Some(sys::Status::Ok) => {
                let Some(nul_index) = buffer.iter().position(|byte| *byte == 0) else {
                    return "native error message was not NUL terminated".to_owned();
                };
                return String::from_utf8_lossy(&buffer[..nul_index]).into_owned();
            }
            Some(sys::Status::BufferTooSmall) if next_required > buffer.len() => {
                required = next_required;
            }
            Some(status) => {
                return format!(
                    "failed to read native error: status {status:?}; required buffer size {next_required}"
                )
            }
            None => {
                return format!(
                    "failed to read native error: unknown status {read_status}; required buffer size {next_required}"
                )
            }
        }
    }

    format!(
        "native error message size changed repeatedly; last required buffer size {required}"
    )
}
