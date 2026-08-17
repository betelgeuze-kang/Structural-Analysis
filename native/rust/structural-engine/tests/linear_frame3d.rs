use std::ffi::c_char;
use std::sync::atomic::{AtomicUsize, Ordering};

use structural_engine::{
    sys, Engine, EngineApi, EngineConfig, Error, LinearFrame3DInput,
};

static ENGINE_DESTROY_COUNT: AtomicUsize = AtomicUsize::new(0);
static MODEL_DESTROY_COUNT: AtomicUsize = AtomicUsize::new(0);
static SOLVE_COUNT: AtomicUsize = AtomicUsize::new(0);
static IMPLEMENTATION_NAME: &[u8] = b"mock-linear-frame3d\0";

#[derive(Clone)]
struct MockApi {
    solve_status: sys::Status,
    error_message: String,
}

impl MockApi {
    fn success() -> Self {
        Self {
            solve_status: sys::Status::Ok,
            error_message: String::new(),
        }
    }
}

impl EngineApi for MockApi {
    unsafe fn get_api_info(&self, out_info: *mut sys::ApiInfo) -> i32 {
        if out_info.is_null() {
            return sys::Status::InvalidArgument as i32;
        }
        unsafe {
            (*out_info).abi_version_major = sys::ABI_VERSION_MAJOR;
            (*out_info).abi_version_minor = sys::ABI_VERSION_MINOR;
            (*out_info).capability_bits =
                sys::CAPABILITY_CPU_REFERENCE | sys::CAPABILITY_LINEAR_FRAME3D;
            (*out_info).implementation_name = IMPLEMENTATION_NAME.as_ptr().cast::<c_char>();
        }
        sys::Status::Ok as i32
    }

    unsafe fn create_engine(
        &self,
        _config: *const sys::EngineConfig,
        out_engine: *mut *mut sys::Engine,
    ) -> i32 {
        unsafe { *out_engine = std::ptr::NonNull::<sys::Engine>::dangling().as_ptr() };
        sys::Status::Ok as i32
    }

    unsafe fn destroy_engine(&self, engine: *mut sys::Engine) {
        if !engine.is_null() {
            ENGINE_DESTROY_COUNT.fetch_add(1, Ordering::SeqCst);
        }
    }

    unsafe fn engine_capabilities(
        &self,
        _engine: *const sys::Engine,
        out_capabilities: *mut u64,
    ) -> i32 {
        unsafe {
            *out_capabilities =
                sys::CAPABILITY_CPU_REFERENCE | sys::CAPABILITY_LINEAR_FRAME3D;
        }
        sys::Status::Ok as i32
    }

    unsafe fn engine_last_error(
        &self,
        _engine: *const sys::Engine,
        buffer: *mut c_char,
        buffer_capacity: usize,
        out_required_size: *mut usize,
    ) -> i32 {
        let bytes = self.error_message.as_bytes();
        let required = bytes.len() + 1;
        unsafe { *out_required_size = required };
        if buffer.is_null() || buffer_capacity < required {
            return sys::Status::BufferTooSmall as i32;
        }
        unsafe {
            std::ptr::copy_nonoverlapping(bytes.as_ptr().cast::<c_char>(), buffer, bytes.len());
            *buffer.add(bytes.len()) = 0;
        }
        sys::Status::Ok as i32
    }

    unsafe fn compile_linear_frame3d(
        &self,
        _engine: *const sys::Engine,
        input: *const sys::LinearFrame3DModelInput,
        out_model: *mut *mut sys::LinearFrame3DModel,
    ) -> i32 {
        if input.is_null() || out_model.is_null() {
            return sys::Status::InvalidArgument as i32;
        }
        unsafe {
            if (*input).node_count != 2
                || (*input).section_count != 1
                || (*input).member_count != 1
                || (*input).restrained_dof_count != 6
            {
                return sys::Status::InvalidArgument as i32;
            }
            *out_model = std::ptr::NonNull::<sys::LinearFrame3DModel>::dangling().as_ptr();
        }
        sys::Status::Ok as i32
    }

    unsafe fn destroy_linear_frame3d(&self, model: *mut sys::LinearFrame3DModel) {
        if !model.is_null() {
            MODEL_DESTROY_COUNT.fetch_add(1, Ordering::SeqCst);
        }
    }

    unsafe fn linear_frame3d_sizes(
        &self,
        _model: *const sys::LinearFrame3DModel,
        out_dof_count: *mut usize,
        out_member_end_force_count: *mut usize,
    ) -> i32 {
        unsafe {
            *out_dof_count = 12;
            *out_member_end_force_count = 12;
        }
        sys::Status::Ok as i32
    }

    unsafe fn solve_linear_frame3d(
        &self,
        _model: *const sys::LinearFrame3DModel,
        _load_vector_kn: *const f64,
        load_count: usize,
        out_result: *mut sys::LinearFrame3DResultBuffers,
    ) -> i32 {
        SOLVE_COUNT.fetch_add(1, Ordering::SeqCst);
        if self.solve_status != sys::Status::Ok {
            return self.solve_status as i32;
        }
        if load_count != 12 || out_result.is_null() {
            return sys::Status::InvalidArgument as i32;
        }
        unsafe {
            let result = &mut *out_result;
            let displacements =
                std::slice::from_raw_parts_mut(result.displacements, result.displacement_count);
            let reactions =
                std::slice::from_raw_parts_mut(result.reactions, result.reaction_count);
            let member_forces = std::slice::from_raw_parts_mut(
                result.member_end_forces,
                result.member_end_force_count,
            );
            for (index, value) in displacements.iter_mut().enumerate() {
                *value = index as f64;
            }
            reactions.fill(-2.0);
            member_forces.fill(3.0);
        }
        sys::Status::Ok as i32
    }
}

fn input_rows() -> (
    [sys::LinearFrame3DNode; 2],
    [sys::LinearFrame3DSection; 1],
    [sys::LinearFrame3DMember; 1],
    [u32; 6],
) {
    (
        [
            sys::LinearFrame3DNode::new(0.0, 0.0, 0.0),
            sys::LinearFrame3DNode::new(2.0, 0.0, 0.0),
        ],
        [sys::LinearFrame3DSection::new(
            0.02,
            200_000_000.0,
            76_923_076.0,
            8.0e-5,
            5.0e-5,
            1.0e-5,
            0.015,
            0.014,
        )],
        [sys::LinearFrame3DMember::new(0, 1, 0)],
        [0, 1, 2, 3, 4, 5],
    )
}

#[test]
fn safe_model_owns_native_handle_and_result_buffers() {
    ENGINE_DESTROY_COUNT.store(0, Ordering::SeqCst);
    MODEL_DESTROY_COUNT.store(0, Ordering::SeqCst);
    SOLVE_COUNT.store(0, Ordering::SeqCst);
    {
        let engine = Engine::create(MockApi::success(), EngineConfig::default())
            .expect("engine should be created");
        let (nodes, sections, members, restrained_dofs) = input_rows();
        let input = LinearFrame3DInput {
            nodes: &nodes,
            sections: &sections,
            members: &members,
            restrained_dofs: &restrained_dofs,
        };
        let model = engine
            .compile_linear_frame3d(&input)
            .expect("model should compile");
        assert_eq!(model.dof_count(), 12);
        assert_eq!(model.member_count(), 1);
        let result = model.solve(&[0.0; 12]).expect("solve should succeed");
        assert_eq!(result.displacements, (0..12).map(f64::from).collect::<Vec<_>>());
        assert_eq!(result.reactions, vec![-2.0; 12]);
        assert_eq!(result.member_end_forces, vec![3.0; 12]);
        assert_eq!(SOLVE_COUNT.load(Ordering::SeqCst), 1);
    }
    assert_eq!(MODEL_DESTROY_COUNT.load(Ordering::SeqCst), 1);
    assert_eq!(ENGINE_DESTROY_COUNT.load(Ordering::SeqCst), 1);
}

#[test]
fn load_length_is_rejected_before_native_call() {
    SOLVE_COUNT.store(0, Ordering::SeqCst);
    let engine = Engine::create(MockApi::success(), EngineConfig::default())
        .expect("engine should be created");
    let (nodes, sections, members, restrained_dofs) = input_rows();
    let input = LinearFrame3DInput {
        nodes: &nodes,
        sections: &sections,
        members: &members,
        restrained_dofs: &restrained_dofs,
    };
    let model = engine
        .compile_linear_frame3d(&input)
        .expect("model should compile");
    assert_eq!(
        model.solve(&[0.0; 11]),
        Err(Error::LoadLength {
            expected: 12,
            actual: 11,
        })
    );
    assert_eq!(SOLVE_COUNT.load(Ordering::SeqCst), 0);
}

#[test]
fn singular_native_status_and_diagnostic_are_preserved() {
    let api = MockApi {
        solve_status: sys::Status::SingularSystem,
        error_message: "bounded frame is singular".to_owned(),
    };
    let engine = Engine::create(api, EngineConfig::default()).expect("engine should be created");
    let (nodes, sections, members, restrained_dofs) = input_rows();
    let input = LinearFrame3DInput {
        nodes: &nodes,
        sections: &sections,
        members: &members,
        restrained_dofs: &restrained_dofs,
    };
    let model = engine
        .compile_linear_frame3d(&input)
        .expect("model should compile");
    assert_eq!(
        model.solve(&[0.0; 12]),
        Err(Error::Native {
            status: sys::Status::SingularSystem,
            message: "bounded frame is singular".to_owned(),
        })
    );
}
