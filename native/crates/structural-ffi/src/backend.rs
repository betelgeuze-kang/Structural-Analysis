use super::{
    abi_size, error_buffer, error_from_buffer, invalid_table, usize_to_u64, Api, Error,
    ERROR_CAPACITY,
};
use crate::sys;
use core::ffi::{c_char, c_void};
use core::mem::size_of;
use core::ptr::{self, NonNull};
use std::marker::PhantomData;
use std::rc::Rc;

/// Product execution backend requested through the single ABI v1.12 entry table.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ExecutionBackend {
    Cpu,
    Hip { device_id: i32 },
}

impl ExecutionBackend {
    fn raw(self) -> Result<(u32, i32), Error> {
        match self {
            Self::Cpu => Ok((sys::SA_EXECUTION_BACKEND_CPU, -1)),
            Self::Hip { device_id } if device_id >= 0 => {
                Ok((sys::SA_EXECUTION_BACKEND_HIP, device_id))
            }
            Self::Hip { .. } => Err(Error {
                code: sys::SA_ERR_DEVICE_MISMATCH,
                message: "HIP backend requires a nonnegative device id".to_owned(),
            }),
        }
    }
}

/// Borrowed, caller-owned full-residual operator. Native creation validates and deep-copies it.
#[derive(Clone, Copy, Debug)]
pub struct FullResidualOperator<'a> {
    pub frame_element_count: usize,
    pub order: usize,
    pub shell_nonzeros: usize,
    pub spring_nonzeros: usize,
    pub free_dof_count: usize,
    pub frame_dofs: &'a [u64],
    pub frame_stiffness: &'a [f64],
    pub shell_row_offsets: &'a [u64],
    pub shell_column_indices: &'a [u64],
    pub shell_values: &'a [f64],
    pub spring_row_offsets: &'a [u64],
    pub spring_column_indices: &'a [u64],
    pub spring_values: &'a [f64],
    pub external_force: &'a [f64],
    pub free_dofs: &'a [u64],
}

/// Stable full-residual execution receipt returned by CPU and HIP implementations.
#[derive(Clone, Debug, PartialEq)]
pub struct FullResidualStatus {
    pub execution_backend: u32,
    pub fallback_count: u32,
    pub device_id: i32,
    pub evaluation_buffers_reused: bool,
    pub operator_device_resident: bool,
    pub frame_element_count: u64,
    pub order: u64,
    pub free_dof_count: u64,
    pub shell_nonzeros: u64,
    pub spring_nonzeros: u64,
    pub batch_size: u64,
    pub repetitions: u32,
    pub h2d_bytes: u64,
    pub d2h_bytes: u64,
    pub h2d_transfer_count: u64,
    pub d2h_transfer_count: u64,
    pub synchronization_count: u64,
    pub kernel_launch_count: u64,
    pub device_buffer_bytes: u64,
    pub vram_total_bytes: u64,
    pub vram_free_before_bytes: u64,
    pub vram_free_after_bytes: u64,
    pub kernel_elapsed_ms_total: f64,
    pub kernel_elapsed_ms_mean: f64,
    pub output_abs_sum: f64,
    pub output_max_abs: f64,
}

impl TryFrom<sys::SaFullResidualStatusV1> for FullResidualStatus {
    type Error = Error;

    fn try_from(raw: sys::SaFullResidualStatusV1) -> Result<Self, Self::Error> {
        let flags_known = sys::SA_FULL_RESIDUAL_EVAL_BUFFERS_REUSED
            | sys::SA_FULL_RESIDUAL_OPERATOR_DEVICE_RESIDENT
            | sys::SA_FULL_RESIDUAL_FP64
            | sys::SA_FULL_RESIDUAL_DETERMINISTIC;
        let backend_valid = match raw.execution_backend {
            sys::SA_EXECUTION_BACKEND_CPU => {
                raw.device_id == -1
                    && raw.flags & sys::SA_FULL_RESIDUAL_OPERATOR_DEVICE_RESIDENT == 0
                    && raw.h2d_bytes == 0
                    && raw.d2h_bytes == 0
                    && raw.h2d_transfer_count == 0
                    && raw.d2h_transfer_count == 0
                    && raw.synchronization_count == 0
                    && raw.kernel_launch_count == 0
                    && raw.device_buffer_bytes == 0
                    && raw.vram_total_bytes == 0
                    && raw.vram_free_before_bytes == 0
                    && raw.vram_free_after_bytes == 0
            }
            sys::SA_EXECUTION_BACKEND_HIP => {
                raw.device_id >= 0
                    && raw.flags & sys::SA_FULL_RESIDUAL_OPERATOR_DEVICE_RESIDENT != 0
                    && raw.h2d_bytes > 0
                    && raw.h2d_transfer_count > 0
                    && raw.synchronization_count > 0
                    && raw.device_buffer_bytes > 0
                    && raw.vram_total_bytes > 0
                    && raw.vram_free_before_bytes <= raw.vram_total_bytes
                    && raw.vram_free_after_bytes <= raw.vram_total_bytes
                    && raw.device_buffer_bytes < raw.vram_total_bytes
            }
            _ => false,
        };
        let valid = backend_valid
            && raw.abi_version == sys::SA_ABI_V1_12
            && raw.struct_size as usize >= size_of::<sys::SaFullResidualStatusV1>()
            && raw.solver_status == sys::SA_SOLVER_CONVERGED
            && raw.fallback_count == 0
            && raw.flags & !flags_known == 0
            && raw.flags & sys::SA_FULL_RESIDUAL_FP64 != 0
            && raw.flags & sys::SA_FULL_RESIDUAL_DETERMINISTIC != 0
            && raw.reserved_u32 == 0
            && raw.reserved_repetitions == 0
            && raw.reserved == [0; 2]
            && raw.kernel_elapsed_ms_total.is_finite()
            && raw.kernel_elapsed_ms_total >= 0.0
            && raw.kernel_elapsed_ms_mean.is_finite()
            && raw.kernel_elapsed_ms_mean >= 0.0
            && raw.output_abs_sum.is_finite()
            && raw.output_abs_sum >= 0.0
            && raw.output_max_abs.is_finite()
            && raw.output_max_abs >= 0.0;
        if !valid {
            return Err(Error {
                code: sys::SA_ERR_INTERNAL,
                message: "native full-residual status violates the v1.12 contract".to_owned(),
            });
        }
        Ok(Self {
            execution_backend: raw.execution_backend,
            fallback_count: raw.fallback_count,
            device_id: raw.device_id,
            evaluation_buffers_reused: raw.flags & sys::SA_FULL_RESIDUAL_EVAL_BUFFERS_REUSED != 0,
            operator_device_resident: raw.flags & sys::SA_FULL_RESIDUAL_OPERATOR_DEVICE_RESIDENT
                != 0,
            frame_element_count: raw.frame_element_count,
            order: raw.order,
            free_dof_count: raw.free_dof_count,
            shell_nonzeros: raw.shell_nonzeros,
            spring_nonzeros: raw.spring_nonzeros,
            batch_size: raw.batch_size,
            repetitions: raw.repetitions,
            h2d_bytes: raw.h2d_bytes,
            d2h_bytes: raw.d2h_bytes,
            h2d_transfer_count: raw.h2d_transfer_count,
            d2h_transfer_count: raw.d2h_transfer_count,
            synchronization_count: raw.synchronization_count,
            kernel_launch_count: raw.kernel_launch_count,
            device_buffer_bytes: raw.device_buffer_bytes,
            vram_total_bytes: raw.vram_total_bytes,
            vram_free_before_bytes: raw.vram_free_before_bytes,
            vram_free_after_bytes: raw.vram_free_after_bytes,
            kernel_elapsed_ms_total: raw.kernel_elapsed_ms_total,
            kernel_elapsed_ms_mean: raw.kernel_elapsed_ms_mean,
            output_abs_sum: raw.output_abs_sum,
            output_max_abs: raw.output_max_abs,
        })
    }
}

/// Successful full-residual evaluation and its no-fallback execution receipt.
#[derive(Clone, Debug, PartialEq)]
pub struct FullResidualEvaluation {
    pub residual: Vec<f64>,
    pub status: FullResidualStatus,
}

/// Immutable selected backend table. Context creation deep-copies every operator buffer.
#[derive(Clone, Copy)]
pub struct BackendApi {
    table: sys::SaBackendApiV1,
}

/// Non-transferable context with concurrent immutable queries and exclusive mutable execution.
pub struct FullResidualContext {
    backend: sys::SaBackendApiV1,
    raw: Option<NonNull<sys::SaFullResidualContextV1>>,
    frame_element_count: usize,
    order: usize,
    shell_nonzeros: usize,
    spring_nonzeros: usize,
    free_dof_count: usize,
    _not_send_or_sync: PhantomData<Rc<()>>,
}

// SAFETY: immutable methods only call the C++ registry's synchronized read operations. Mutable
// execution and destruction still require Rust-exclusive access, and `Rc` keeps ownership !Send.
unsafe impl Sync for FullResidualContext {}

impl Api {
    /// Load ABI v1.12 with the product-backend selector.
    ///
    /// # Errors
    ///
    /// Returns a stable ABI error if the v1.12 capability or slot is unavailable.
    pub fn load_backend_selector() -> Result<Self, Error> {
        Self::load_version(sys::SA_ABI_V1_12)
    }

    /// Select one no-fallback product backend.
    ///
    /// # Errors
    ///
    /// CPU accepts only device `-1`; HIP accepts nonnegative ids and fails closed when absent.
    pub fn select_backend(self, backend: ExecutionBackend) -> Result<BackendApi, Error> {
        let get = self.table.backend_get_api.ok_or_else(invalid_table)?;
        let (execution_backend, device_id) = backend.raw()?;
        let request = sys::SaBackendRequestV1 {
            abi_version: sys::SA_ABI_V1_12,
            struct_size: abi_size::<sys::SaBackendRequestV1>(),
            execution_backend,
            device_id,
            flags: 0,
            reserved: [0; 2],
        };
        let mut table = sys::SaBackendApiV1 {
            abi_version: sys::SA_ABI_V1_12,
            ..sys::SaBackendApiV1::default()
        };
        let mut storage = [0_i8; ERROR_CAPACITY];
        let mut error = error_buffer(sys::SA_ABI_V1_12, &mut storage);
        // SAFETY: request, output table and bounded error storage are live C-layout values.
        let status = unsafe { get(&request, &mut table, &mut error) };
        if status != sys::SA_OK {
            return Err(error_from_buffer(status, &storage));
        }
        let valid = table.abi_version == sys::SA_ABI_V1_12
            && table.struct_size as usize >= size_of::<sys::SaBackendApiV1>()
            && table.execution_backend == execution_backend
            && table.device_id == device_id
            && table.capabilities & sys::SA_BACKEND_CAPABILITY_FULL_RESIDUAL != 0
            && table.full_residual_create.is_some()
            && table.full_residual_evaluate.is_some()
            && table.full_residual_destroy.is_some()
            && table.full_residual_device_name_size.is_some()
            && table.full_residual_device_name_write.is_some()
            && table.reserved == [0; 2];
        if !valid {
            return Err(invalid_table());
        }
        Ok(BackendApi { table })
    }
}

impl BackendApi {
    /// Deep-copy a validated operator into a backend-owned context.
    ///
    /// # Errors
    ///
    /// Returns stable descriptor, allocation, backend, or device errors.
    pub fn create_full_residual(
        self,
        operator: FullResidualOperator<'_>,
    ) -> Result<(FullResidualContext, FullResidualStatus), Error> {
        let descriptor = sys::SaFullResidualOperatorV1 {
            abi_version: sys::SA_ABI_V1_12,
            struct_size: abi_size::<sys::SaFullResidualOperatorV1>(),
            frame_dofs: input_view(operator.frame_dofs, sys::SA_ELEMENT_TYPE_U64)?,
            frame_stiffness: input_view(operator.frame_stiffness, sys::SA_ELEMENT_TYPE_F64)?,
            shell_row_offsets: input_view(operator.shell_row_offsets, sys::SA_ELEMENT_TYPE_U64)?,
            shell_column_indices: input_view(
                operator.shell_column_indices,
                sys::SA_ELEMENT_TYPE_U64,
            )?,
            shell_values: input_view(operator.shell_values, sys::SA_ELEMENT_TYPE_F64)?,
            spring_row_offsets: input_view(operator.spring_row_offsets, sys::SA_ELEMENT_TYPE_U64)?,
            spring_column_indices: input_view(
                operator.spring_column_indices,
                sys::SA_ELEMENT_TYPE_U64,
            )?,
            spring_values: input_view(operator.spring_values, sys::SA_ELEMENT_TYPE_F64)?,
            external_force: input_view(operator.external_force, sys::SA_ELEMENT_TYPE_F64)?,
            free_dofs: input_view(operator.free_dofs, sys::SA_ELEMENT_TYPE_U64)?,
            frame_element_count: usize_to_u64(operator.frame_element_count)?,
            order: usize_to_u64(operator.order)?,
            shell_nonzeros: usize_to_u64(operator.shell_nonzeros)?,
            spring_nonzeros: usize_to_u64(operator.spring_nonzeros)?,
            free_dof_count: usize_to_u64(operator.free_dof_count)?,
            reserved: [0; 2],
        };
        let create = self.table.full_residual_create.ok_or_else(invalid_table)?;
        let mut raw = ptr::null_mut();
        let mut status = raw_status();
        let mut storage = [0_i8; ERROR_CAPACITY];
        let mut error = error_buffer(sys::SA_ABI_V1_12, &mut storage);
        // SAFETY: all borrowed slices outlive this synchronous deep-copy call; outputs are live.
        let code = unsafe { create(&descriptor, &mut raw, &mut status, &mut error) };
        if code != sys::SA_OK {
            return Err(error_from_buffer(code, &storage));
        }
        let raw = NonNull::new(raw).ok_or_else(invalid_table)?;
        let destroy = self.table.full_residual_destroy.ok_or_else(invalid_table)?;
        let safe_status = match FullResidualStatus::try_from(status) {
            Ok(status) => status,
            Err(error) => {
                // SAFETY: native creation succeeded, so this call consumes the live context.
                unsafe {
                    let _ = destroy(raw.as_ptr(), ptr::null_mut());
                }
                return Err(error);
            }
        };
        if safe_status.execution_backend != self.table.execution_backend
            || safe_status.device_id != self.table.device_id
            || safe_status.frame_element_count != descriptor.frame_element_count
            || safe_status.order != usize_to_u64(operator.order)?
            || safe_status.free_dof_count != usize_to_u64(operator.free_dof_count)?
            || safe_status.shell_nonzeros != descriptor.shell_nonzeros
            || safe_status.spring_nonzeros != descriptor.spring_nonzeros
            || safe_status.batch_size != 0
            || safe_status.repetitions != 0
            || safe_status.evaluation_buffers_reused
            || safe_status.operator_device_resident
                != (self.table.execution_backend == sys::SA_EXECUTION_BACKEND_HIP)
        {
            // SAFETY: the native call returned a live context; destruction does not retain data.
            unsafe {
                let _ = destroy(raw.as_ptr(), ptr::null_mut());
            }
            return Err(invalid_table());
        }
        Ok((
            FullResidualContext {
                backend: self.table,
                raw: Some(raw),
                frame_element_count: operator.frame_element_count,
                order: operator.order,
                shell_nonzeros: operator.shell_nonzeros,
                spring_nonzeros: operator.spring_nonzeros,
                free_dof_count: operator.free_dof_count,
                _not_send_or_sync: PhantomData,
            },
            safe_status,
        ))
    }
}

impl FullResidualContext {
    /// Evaluate a batch with deterministic repetitions and no fallback.
    ///
    /// # Errors
    ///
    /// Rejects overflow, shape mismatch, non-finite data, backend failures, or receipt drift.
    pub fn evaluate(
        &mut self,
        states: &[f64],
        batch_size: usize,
        repetitions: u32,
    ) -> Result<FullResidualEvaluation, Error> {
        let state_count = batch_size.checked_mul(self.order).ok_or_else(|| Error {
            code: sys::SA_ERR_INVALID_ARGUMENT,
            message: "full-residual state count overflows usize".to_owned(),
        })?;
        let output_count = batch_size
            .checked_mul(self.free_dof_count)
            .ok_or_else(|| Error {
                code: sys::SA_ERR_INVALID_ARGUMENT,
                message: "full-residual output count overflows usize".to_owned(),
            })?;
        if states.len() != state_count {
            return Err(Error {
                code: sys::SA_ERR_INVALID_ARGUMENT,
                message: "full-residual state length does not match batch and order".to_owned(),
            });
        }
        let mut residual = Vec::new();
        residual
            .try_reserve_exact(output_count)
            .map_err(|_| Error {
                code: sys::SA_ERR_INTERNAL,
                message: "full-residual output allocation failed".to_owned(),
            })?;
        residual.resize(output_count, 0.0);
        let config = sys::SaFullResidualEvalConfigV1 {
            abi_version: sys::SA_ABI_V1_12,
            struct_size: abi_size::<sys::SaFullResidualEvalConfigV1>(),
            batch_size: usize_to_u64(batch_size)?,
            repetitions,
            flags: 0,
            reserved: [0; 2],
        };
        let state_view = input_view(states, sys::SA_ELEMENT_TYPE_F64)?;
        let output_view = output_view(&mut residual)?;
        let mut raw_receipt = raw_status();
        let mut storage = [0_i8; ERROR_CAPACITY];
        let mut error = error_buffer(sys::SA_ABI_V1_12, &mut storage);
        let evaluate = self
            .backend
            .full_residual_evaluate
            .ok_or_else(invalid_table)?;
        // SAFETY: context is live and uniquely borrowed; all descriptors and buffers are live.
        let code = unsafe {
            evaluate(
                self.raw.ok_or_else(invalid_table)?.as_ptr(),
                &config,
                &state_view,
                &output_view,
                &mut raw_receipt,
                &mut error,
            )
        };
        if code != sys::SA_OK {
            return Err(error_from_buffer(code, &storage));
        }
        let safe_status = FullResidualStatus::try_from(raw_receipt)?;
        if safe_status.execution_backend != self.backend.execution_backend
            || safe_status.device_id != self.backend.device_id
            || safe_status.batch_size != usize_to_u64(batch_size)?
            || safe_status.repetitions != repetitions
            || safe_status.frame_element_count != usize_to_u64(self.frame_element_count)?
            || safe_status.order != usize_to_u64(self.order)?
            || safe_status.free_dof_count != usize_to_u64(self.free_dof_count)?
            || safe_status.shell_nonzeros != usize_to_u64(self.shell_nonzeros)?
            || safe_status.spring_nonzeros != usize_to_u64(self.spring_nonzeros)?
            || safe_status.fallback_count != 0
            || safe_status.operator_device_resident
                != (self.backend.execution_backend == sys::SA_EXECUTION_BACKEND_HIP)
        {
            return Err(invalid_table());
        }
        Ok(FullResidualEvaluation {
            residual,
            status: safe_status,
        })
    }

    /// Return the immutable backend device name.
    ///
    /// # Errors
    ///
    /// Rejects native size/write inconsistencies or non-UTF-8 names.
    pub fn device_name(&self) -> Result<String, Error> {
        let context = self.raw.ok_or_else(invalid_table)?.as_ptr();
        let size_fn = self
            .backend
            .full_residual_device_name_size
            .ok_or_else(invalid_table)?;
        let write_fn = self
            .backend
            .full_residual_device_name_write
            .ok_or_else(invalid_table)?;
        let mut required = 0_u64;
        let mut storage = [0_i8; ERROR_CAPACITY];
        let mut error = error_buffer(sys::SA_ABI_V1_12, &mut storage);
        // SAFETY: context is live, immutable, and the size output is live.
        let code = unsafe { size_fn(context, &mut required, &mut error) };
        if code != sys::SA_OK {
            return Err(error_from_buffer(code, &storage));
        }
        let required = usize::try_from(required).map_err(|_| invalid_table())?;
        if required == 0 {
            return Err(invalid_table());
        }
        let mut bytes = vec![0_u8; required];
        let mut storage = [0_i8; ERROR_CAPACITY];
        let mut error = error_buffer(sys::SA_ABI_V1_12, &mut storage);
        // SAFETY: context is live and `bytes` provides exactly the queried caller-owned capacity.
        let code = unsafe {
            write_fn(
                context,
                bytes.as_mut_ptr().cast::<c_char>(),
                usize_to_u64(bytes.len())?,
                &mut error,
            )
        };
        if code != sys::SA_OK {
            return Err(error_from_buffer(code, &storage));
        }
        if bytes.last() != Some(&0) || bytes[..bytes.len() - 1].contains(&0) {
            return Err(invalid_table());
        }
        bytes.pop();
        String::from_utf8(bytes).map_err(|_| Error {
            code: sys::SA_ERR_INTERNAL,
            message: "native device name is not UTF-8".to_owned(),
        })
    }
}

impl Drop for FullResidualContext {
    fn drop(&mut self) {
        let Some(raw) = self.raw.take() else {
            return;
        };
        if let Some(destroy) = self.backend.full_residual_destroy {
            // SAFETY: `raw` is owned exactly once by this RAII wrapper and is never used again.
            unsafe {
                let _ = destroy(raw.as_ptr(), ptr::null_mut());
            }
        }
    }
}

fn input_view<T>(values: &[T], element_type: u32) -> Result<sys::SaBufferViewV1, Error> {
    Ok(sys::SaBufferViewV1 {
        abi_version: sys::SA_ABI_V1_12,
        struct_size: abi_size::<sys::SaBufferViewV1>(),
        data: if values.is_empty() {
            ptr::null()
        } else {
            values.as_ptr().cast::<c_void>()
        },
        length: usize_to_u64(values.len())?,
        stride_bytes: usize_to_u64(size_of::<T>())?,
        element_type,
        memory_space: sys::SA_MEMORY_SPACE_HOST,
        device_id: -1,
        flags: 0,
    })
}

fn output_view(values: &mut [f64]) -> Result<sys::SaMutBufferViewV1, Error> {
    Ok(sys::SaMutBufferViewV1 {
        abi_version: sys::SA_ABI_V1_12,
        struct_size: abi_size::<sys::SaMutBufferViewV1>(),
        data: if values.is_empty() {
            ptr::null_mut()
        } else {
            values.as_mut_ptr().cast::<c_void>()
        },
        length: usize_to_u64(values.len())?,
        stride_bytes: usize_to_u64(size_of::<f64>())?,
        element_type: sys::SA_ELEMENT_TYPE_F64,
        memory_space: sys::SA_MEMORY_SPACE_HOST,
        device_id: -1,
        flags: 0,
    })
}

fn raw_status() -> sys::SaFullResidualStatusV1 {
    sys::SaFullResidualStatusV1 {
        abi_version: sys::SA_ABI_V1_12,
        struct_size: abi_size::<sys::SaFullResidualStatusV1>(),
        ..sys::SaFullResidualStatusV1::default()
    }
}
