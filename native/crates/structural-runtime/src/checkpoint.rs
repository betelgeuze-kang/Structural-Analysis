use std::fmt::Write as _;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::Path;
use std::sync::atomic::{AtomicU64, Ordering};

use serde::Serialize;
use sha2::{Digest, Sha256};
use structural_contracts::legacy_runtime::{NdthaStoryInputsV3, NonlinearNdthaConfigV3};
use structural_ffi::{
    NonlinearNdthaExecutionStatus, NonlinearNdthaResponse, NonlinearNdthaRestartState,
};

use crate::RuntimeError;

const MAGIC: &[u8; 8] = b"SANDCP01";
const FORMAT_VERSION: u32 = 1;
const HEADER_SIZE: usize = 152;
const STATE_PAYLOAD_FIXED_SIZE: usize = 184;
const MAX_VECTOR_VALUES: usize = 1_000_000;
const MAX_ARTIFACT_BYTES: usize = 256 * 1024 * 1024;
const CHECKPOINT_MISMATCH: u32 = 1301;
const INTERNAL_ERROR: u32 = 1900;
const MODEL_DOMAIN: &[u8] = b"structural-ndtha-model.v1\0";
const EXECUTION_DOMAIN: &[u8] = b"structural-ndtha-execution.v1\0";
const STATE_DOMAIN: &[u8] = b"structural-ndtha-state.v1\0";
const ARTIFACT_DOMAIN: &[u8] = b"structural-ndtha-checkpoint.v1\0";
const ALGORITHM_ID: &[u8] = b"cpp-fp64-newmark-newton-story-frame.v1";
const ABI_VERSION: u32 = 0x0001_0005;
static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);

type DigestBytes = [u8; 32];

/// Verifiable identity and progress metadata for one persisted NDTHA checkpoint.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct NonlinearNdthaCheckpointReceipt {
    pub schema_version: &'static str,
    pub model_hash: String,
    pub state_hash: String,
    pub execution_hash: String,
    pub checkpoint_hash: String,
    pub next_step: u32,
    pub status: NonlinearNdthaExecutionStatus,
    pub artifact_bytes: u64,
}

/// Complete, pointer-free, integrity-checked checkpoint artifact.
#[derive(Clone, Debug, PartialEq)]
pub struct NonlinearNdthaCheckpoint {
    bytes: Vec<u8>,
    state: NonlinearNdthaRestartState,
    model_hash: DigestBytes,
    state_hash: DigestBytes,
    execution_hash: DigestBytes,
    checkpoint_hash: DigestBytes,
}

impl NonlinearNdthaCheckpoint {
    pub(crate) fn create(
        config: &NonlinearNdthaConfigV3,
        inputs: &NdthaStoryInputsV3,
        state: NonlinearNdthaRestartState,
    ) -> Result<Self, RuntimeError> {
        let payload = encode_state(&state)?;
        let model_hash = model_hash(config, inputs);
        let execution_hash = execution_hash(config, inputs);
        let state_hash = domain_hash(STATE_DOMAIN, &payload);
        let checkpoint_hash =
            artifact_hash(&model_hash, &state_hash, &execution_hash, payload.len())?;
        let total = HEADER_SIZE
            .checked_add(payload.len())
            .ok_or_else(|| checkpoint_error("checkpoint artifact length overflow"))?;
        if total > MAX_ARTIFACT_BYTES {
            return Err(checkpoint_error(
                "checkpoint artifact exceeds the bounded size",
            ));
        }
        let mut bytes = Vec::new();
        bytes
            .try_reserve_exact(total)
            .map_err(|_| internal_error("checkpoint artifact allocation failed"))?;
        bytes.extend_from_slice(MAGIC);
        push_u32(&mut bytes, FORMAT_VERSION);
        push_u32(
            &mut bytes,
            u32::try_from(HEADER_SIZE)
                .map_err(|_| internal_error("checkpoint header size conversion failed"))?,
        );
        push_u64(
            &mut bytes,
            u64::try_from(payload.len())
                .map_err(|_| checkpoint_error("checkpoint payload length exceeds u64"))?,
        );
        bytes.extend_from_slice(&model_hash);
        bytes.extend_from_slice(&state_hash);
        bytes.extend_from_slice(&execution_hash);
        bytes.extend_from_slice(&checkpoint_hash);
        bytes.extend_from_slice(&payload);
        Ok(Self {
            bytes,
            state,
            model_hash,
            state_hash,
            execution_hash,
            checkpoint_hash,
        })
    }

    /// Decode and verify the complete binary artifact without accepting external bindings yet.
    ///
    /// # Errors
    ///
    /// Returns `SA_ERR_CHECKPOINT_MISMATCH` semantics for malformed, truncated, oversized,
    /// non-finite or hash-inconsistent bytes.
    pub fn from_bytes(bytes: &[u8]) -> Result<Self, RuntimeError> {
        if bytes.len() < HEADER_SIZE || bytes.len() > MAX_ARTIFACT_BYTES {
            return Err(checkpoint_error(
                "checkpoint artifact size is outside the bounded range",
            ));
        }
        let mut reader = Reader::new(bytes);
        if reader.take(MAGIC.len())? != MAGIC {
            return Err(checkpoint_error("checkpoint magic does not match"));
        }
        if reader.u32()? != FORMAT_VERSION {
            return Err(checkpoint_error("checkpoint format version is unsupported"));
        }
        if usize::try_from(reader.u32()?).ok() != Some(HEADER_SIZE) {
            return Err(checkpoint_error("checkpoint header size does not match"));
        }
        let payload_len = reader.artifact_length()?;
        let model_hash = reader.digest()?;
        let state_hash = reader.digest()?;
        let execution_hash = reader.digest()?;
        let checkpoint_hash = reader.digest()?;
        if reader.position() != HEADER_SIZE || reader.remaining() != payload_len {
            return Err(checkpoint_error(
                "checkpoint payload length does not match artifact",
            ));
        }
        let payload = reader.take(payload_len)?;
        reader.finish()?;
        if domain_hash(STATE_DOMAIN, payload) != state_hash {
            return Err(checkpoint_error(
                "checkpoint state hash does not match payload",
            ));
        }
        let expected_artifact_hash =
            artifact_hash(&model_hash, &state_hash, &execution_hash, payload_len)?;
        if expected_artifact_hash != checkpoint_hash {
            return Err(checkpoint_error("checkpoint aggregate hash does not match"));
        }
        let state = decode_state(payload)?;
        Ok(Self {
            bytes: clone_bytes(bytes)?,
            state,
            model_hash,
            state_hash,
            execution_hash,
            checkpoint_hash,
        })
    }

    /// Exact canonical artifact bytes suitable for durable storage or transport.
    #[must_use]
    pub fn as_bytes(&self) -> &[u8] {
        &self.bytes
    }

    /// Pointer-free decoded execution state.
    #[must_use]
    pub fn state(&self) -> &NonlinearNdthaRestartState {
        &self.state
    }

    /// Stable receipt containing all three binding hashes and the aggregate artifact hash.
    #[must_use]
    pub fn receipt(&self) -> NonlinearNdthaCheckpointReceipt {
        NonlinearNdthaCheckpointReceipt {
            schema_version: "structural-ndtha-checkpoint-receipt.v1",
            model_hash: format_digest(&self.model_hash),
            state_hash: format_digest(&self.state_hash),
            execution_hash: format_digest(&self.execution_hash),
            checkpoint_hash: format_digest(&self.checkpoint_hash),
            next_step: self.state.next_step,
            status: self.state.status,
            artifact_bytes: u64::try_from(self.bytes.len()).unwrap_or(u64::MAX),
        }
    }

    pub(crate) fn verify_bindings(
        &self,
        config: &NonlinearNdthaConfigV3,
        inputs: &NdthaStoryInputsV3,
    ) -> Result<(), RuntimeError> {
        if self.model_hash != model_hash(config, inputs) {
            return Err(checkpoint_error(
                "checkpoint model hash does not match request",
            ));
        }
        if self.execution_hash != execution_hash(config, inputs) {
            return Err(checkpoint_error(
                "checkpoint execution hash does not match request",
            ));
        }
        Ok(())
    }
}

pub(crate) fn write_atomic(
    path: &Path,
    checkpoint: &NonlinearNdthaCheckpoint,
) -> Result<(), RuntimeError> {
    let parent = path
        .parent()
        .filter(|parent| !parent.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."));
    let file_name = path
        .file_name()
        .and_then(|name| name.to_str())
        .filter(|name| !name.is_empty())
        .ok_or_else(|| internal_error("checkpoint destination has no valid file name"))?;
    if !parent.is_dir() {
        return Err(internal_error(
            "checkpoint destination directory does not exist",
        ));
    }

    let sequence = TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed);
    let temporary = parent.join(format!(
        ".{file_name}.tmp.{}.{}",
        std::process::id(),
        sequence
    ));
    let write_result = (|| -> Result<(), RuntimeError> {
        let mut file = OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(&temporary)
            .map_err(|error| io_error("create checkpoint temporary file", &error))?;
        file.write_all(checkpoint.as_bytes())
            .map_err(|error| io_error("write checkpoint temporary file", &error))?;
        file.sync_all()
            .map_err(|error| io_error("sync checkpoint temporary file", &error))?;
        drop(file);
        fs::rename(&temporary, path)
            .map_err(|error| io_error("atomically publish checkpoint", &error))?;
        File::open(parent)
            .and_then(|directory| directory.sync_all())
            .map_err(|error| io_error("sync checkpoint directory", &error))?;
        Ok(())
    })();
    if write_result.is_err() {
        let _ignored = fs::remove_file(&temporary);
    }
    write_result
}

pub(crate) fn read_file(path: &Path) -> Result<NonlinearNdthaCheckpoint, RuntimeError> {
    let mut file = File::open(path).map_err(|error| io_error("open checkpoint", &error))?;
    let byte_count = usize::try_from(
        file.metadata()
            .map_err(|error| io_error("read checkpoint metadata", &error))?
            .len(),
    )
    .map_err(|_| checkpoint_error("checkpoint file length exceeds address space"))?;
    if !(HEADER_SIZE..=MAX_ARTIFACT_BYTES).contains(&byte_count) {
        return Err(checkpoint_error(
            "checkpoint file size is outside the bounded range",
        ));
    }
    let mut bytes = Vec::new();
    bytes
        .try_reserve_exact(byte_count)
        .map_err(|_| internal_error("checkpoint file allocation failed"))?;
    file.read_to_end(&mut bytes)
        .map_err(|error| io_error("read checkpoint", &error))?;
    if bytes.len() != byte_count {
        return Err(checkpoint_error("checkpoint file size changed during read"));
    }
    NonlinearNdthaCheckpoint::from_bytes(&bytes)
}

fn encode_state(state: &NonlinearNdthaRestartState) -> Result<Vec<u8>, RuntimeError> {
    validate_finite_state(state)?;
    let length = encoded_state_length(state)?;
    if length > MAX_ARTIFACT_BYTES - HEADER_SIZE {
        return Err(checkpoint_error(
            "checkpoint state payload exceeds the bounded size",
        ));
    }
    let mut output = Vec::new();
    output
        .try_reserve_exact(length)
        .map_err(|_| internal_error("checkpoint state allocation failed"))?;
    push_u32(&mut output, FORMAT_VERSION);
    push_u32(&mut output, state.next_step);
    push_u32(&mut output, status_to_u32(state.status));
    push_i32(&mut output, state.collapse_step);
    push_u32(&mut output, state.max_plastic_story_count);
    push_u32(&mut output, state.total_line_search_backtracks);
    push_u32(&mut output, state.execution_backend);
    push_u32(&mut output, state.fallback_count);
    push_u64(&mut output, state.adaptive_iteration_sum);
    push_f64(&mut output, state.collapse_time_s);
    push_f64(&mut output, state.collapse_drift_ratio_pct);
    push_f64(&mut output, state.collapse_top_displacement_m);
    push_f64(&mut output, state.max_drift_ratio_pct);
    push_f64_vector(&mut output, &state.displacement_m)?;
    push_f64_vector(&mut output, &state.velocity_m_per_s)?;
    push_f64_vector(&mut output, &state.acceleration_m_per_s2)?;
    push_f64_vector(&mut output, &state.response.top_displacement_m)?;
    push_f64_vector(&mut output, &state.response.drift_ratio_pct)?;
    push_f64_vector(&mut output, &state.response.base_shear_kn)?;
    push_f64_vector(&mut output, &state.response.core_drift_pct)?;
    push_f64_vector(&mut output, &state.response.core_shear_kn)?;
    push_bool_vector(&mut output, &state.response.step_converged)?;
    push_u32_vector(&mut output, &state.response.step_iterations)?;
    push_u32_vector(&mut output, &state.response.step_plastic_story_count)?;
    push_f64_vector(&mut output, &state.response.step_residual_inf)?;
    push_f64_vector(&mut output, &state.response.story_drift_envelope_pct)?;
    push_f64_vector(&mut output, &state.response.final_story_drift_pct)?;
    if output.len() != length {
        return Err(internal_error("checkpoint state length invariant failed"));
    }
    Ok(output)
}

fn decode_state(bytes: &[u8]) -> Result<NonlinearNdthaRestartState, RuntimeError> {
    let mut reader = Reader::new(bytes);
    if reader.u32()? != FORMAT_VERSION {
        return Err(checkpoint_error("checkpoint state version is unsupported"));
    }
    let next_step = reader.u32()?;
    let status = status_from_u32(reader.u32()?)?;
    let collapse_step = reader.i32()?;
    let max_plastic_story_count = reader.u32()?;
    let total_line_search_backtracks = reader.u32()?;
    let execution_backend = reader.u32()?;
    let fallback_count = reader.u32()?;
    let adaptive_iteration_sum = reader.u64()?;
    let collapse_time_s = reader.f64()?;
    let collapse_drift_ratio_pct = reader.f64()?;
    let collapse_top_displacement_m = reader.f64()?;
    let max_drift_ratio_pct = reader.f64()?;
    let displacement_m = reader.f64_vector()?;
    let velocity_m_per_s = reader.f64_vector()?;
    let acceleration_m_per_s2 = reader.f64_vector()?;
    let response = NonlinearNdthaResponse {
        top_displacement_m: reader.f64_vector()?,
        drift_ratio_pct: reader.f64_vector()?,
        base_shear_kn: reader.f64_vector()?,
        core_drift_pct: reader.f64_vector()?,
        core_shear_kn: reader.f64_vector()?,
        step_converged: reader.bool_vector()?,
        step_iterations: reader.u32_vector()?,
        step_plastic_story_count: reader.u32_vector()?,
        step_residual_inf: reader.f64_vector()?,
        story_drift_envelope_pct: reader.f64_vector()?,
        final_story_drift_pct: reader.f64_vector()?,
    };
    reader.finish()?;
    Ok(NonlinearNdthaRestartState {
        next_step,
        status,
        collapse_step,
        collapse_time_s,
        collapse_drift_ratio_pct,
        collapse_top_displacement_m,
        max_plastic_story_count,
        max_drift_ratio_pct,
        adaptive_iteration_sum,
        total_line_search_backtracks,
        displacement_m,
        velocity_m_per_s,
        acceleration_m_per_s2,
        response,
        execution_backend,
        fallback_count,
    })
}

fn encoded_state_length(state: &NonlinearNdthaRestartState) -> Result<usize, RuntimeError> {
    let mut length = STATE_PAYLOAD_FIXED_SIZE;
    for values in [
        &state.displacement_m,
        &state.velocity_m_per_s,
        &state.acceleration_m_per_s2,
        &state.response.top_displacement_m,
        &state.response.drift_ratio_pct,
        &state.response.base_shear_kn,
        &state.response.core_drift_pct,
        &state.response.core_shear_kn,
        &state.response.step_residual_inf,
        &state.response.story_drift_envelope_pct,
        &state.response.final_story_drift_pct,
    ] {
        validate_vector_length(values.len())?;
        length = add_vector_bytes(length, values.len(), std::mem::size_of::<f64>())?;
    }
    validate_vector_length(state.response.step_converged.len())?;
    length = add_vector_bytes(length, state.response.step_converged.len(), 1)?;
    for values in [
        &state.response.step_iterations,
        &state.response.step_plastic_story_count,
    ] {
        validate_vector_length(values.len())?;
        length = add_vector_bytes(length, values.len(), std::mem::size_of::<u32>())?;
    }
    Ok(length)
}

fn add_vector_bytes(
    current: usize,
    length: usize,
    element_size: usize,
) -> Result<usize, RuntimeError> {
    let data = length
        .checked_mul(element_size)
        .ok_or_else(|| checkpoint_error("checkpoint vector extent overflow"))?;
    current
        .checked_add(data)
        .ok_or_else(|| checkpoint_error("checkpoint state length overflow"))
}

fn validate_vector_length(length: usize) -> Result<(), RuntimeError> {
    if length <= MAX_VECTOR_VALUES {
        Ok(())
    } else {
        Err(checkpoint_error(
            "checkpoint vector exceeds the bounded length",
        ))
    }
}

fn validate_finite_state(state: &NonlinearNdthaRestartState) -> Result<(), RuntimeError> {
    let finite_scalars = [
        state.collapse_time_s,
        state.collapse_drift_ratio_pct,
        state.collapse_top_displacement_m,
        state.max_drift_ratio_pct,
    ]
    .iter()
    .all(|value| value.is_finite());
    let finite_vectors = [
        &state.displacement_m,
        &state.velocity_m_per_s,
        &state.acceleration_m_per_s2,
        &state.response.top_displacement_m,
        &state.response.drift_ratio_pct,
        &state.response.base_shear_kn,
        &state.response.core_drift_pct,
        &state.response.core_shear_kn,
        &state.response.step_residual_inf,
        &state.response.story_drift_envelope_pct,
        &state.response.final_story_drift_pct,
    ]
    .iter()
    .all(|values| values.iter().all(|value| value.is_finite()));
    if finite_scalars && finite_vectors {
        Ok(())
    } else {
        Err(checkpoint_error(
            "checkpoint state contains a non-finite value",
        ))
    }
}

fn model_hash(config: &NonlinearNdthaConfigV3, inputs: &NdthaStoryInputsV3) -> DigestBytes {
    let mut digest = Sha256::new();
    digest.update(MODEL_DOMAIN);
    hash_u32(&mut digest, config.story_count);
    for values in [
        &inputs.story_k_n_per_m,
        &inputs.story_h_m,
        &inputs.story_axial_n,
        &inputs.story_yield_drift_m,
        &inputs.story_mass_kg,
        &inputs.story_damping_n_s_per_m,
    ] {
        hash_f64_vector(&mut digest, values);
    }
    digest.finalize().into()
}

fn execution_hash(config: &NonlinearNdthaConfigV3, inputs: &NdthaStoryInputsV3) -> DigestBytes {
    let mut digest = Sha256::new();
    digest.update(EXECUTION_DOMAIN);
    hash_bytes(&mut digest, ALGORITHM_ID);
    hash_bytes(&mut digest, b"cpu");
    hash_u32(&mut digest, ABI_VERSION);
    hash_u32(&mut digest, config.story_count);
    hash_u32(&mut digest, config.step_count);
    for value in [
        config.dt_s,
        config.newmark_beta,
        config.newmark_gamma,
        config.tolerance,
    ] {
        hash_f64(&mut digest, value);
    }
    hash_u32(&mut digest, config.max_step_iterations);
    for value in [config.adaptive_load_decay, config.damping_force_cap_ratio] {
        hash_f64(&mut digest, value);
    }
    hash_u32(&mut digest, config.newton_max_iter);
    for value in [
        config.line_search_decay,
        config.line_search_min,
        config.hardening_ratio,
        config.pdelta_factor,
        config.collapse_drift_threshold_pct,
    ] {
        hash_f64(&mut digest, value);
    }
    hash_f64_vector(&mut digest, &inputs.floor_load_base_n);
    hash_f64_vector(&mut digest, &inputs.ag_g);
    digest.finalize().into()
}

fn artifact_hash(
    model_hash: &DigestBytes,
    state_hash: &DigestBytes,
    execution_hash: &DigestBytes,
    payload_len: usize,
) -> Result<DigestBytes, RuntimeError> {
    let mut digest = Sha256::new();
    digest.update(ARTIFACT_DOMAIN);
    digest.update(model_hash);
    digest.update(state_hash);
    digest.update(execution_hash);
    digest.update(
        u64::try_from(payload_len)
            .map_err(|_| checkpoint_error("checkpoint payload length exceeds u64"))?
            .to_le_bytes(),
    );
    Ok(digest.finalize().into())
}

fn domain_hash(domain: &[u8], bytes: &[u8]) -> DigestBytes {
    let mut digest = Sha256::new();
    digest.update(domain);
    digest.update(bytes);
    digest.finalize().into()
}

fn hash_bytes(digest: &mut Sha256, bytes: &[u8]) {
    digest.update(u64::try_from(bytes.len()).unwrap_or(u64::MAX).to_le_bytes());
    digest.update(bytes);
}

fn hash_u32(digest: &mut Sha256, value: u32) {
    digest.update(value.to_le_bytes());
}

fn hash_f64(digest: &mut Sha256, value: f64) {
    digest.update(value.to_bits().to_le_bytes());
}

fn hash_f64_vector(digest: &mut Sha256, values: &[f64]) {
    digest.update(
        u64::try_from(values.len())
            .unwrap_or(u64::MAX)
            .to_le_bytes(),
    );
    for value in values {
        hash_f64(digest, *value);
    }
}

fn format_digest(digest: &DigestBytes) -> String {
    let mut output = String::with_capacity(71);
    output.push_str("sha256:");
    for byte in digest {
        let _ignored = write!(&mut output, "{byte:02x}");
    }
    output
}

fn clone_bytes(bytes: &[u8]) -> Result<Vec<u8>, RuntimeError> {
    let mut output = Vec::new();
    output
        .try_reserve_exact(bytes.len())
        .map_err(|_| internal_error("checkpoint artifact allocation failed"))?;
    output.extend_from_slice(bytes);
    Ok(output)
}

fn push_u32(output: &mut Vec<u8>, value: u32) {
    output.extend_from_slice(&value.to_le_bytes());
}

fn push_i32(output: &mut Vec<u8>, value: i32) {
    output.extend_from_slice(&value.to_le_bytes());
}

fn push_u64(output: &mut Vec<u8>, value: u64) {
    output.extend_from_slice(&value.to_le_bytes());
}

fn push_f64(output: &mut Vec<u8>, value: f64) {
    output.extend_from_slice(&value.to_bits().to_le_bytes());
}

fn push_vector_length(output: &mut Vec<u8>, length: usize) -> Result<(), RuntimeError> {
    push_u64(
        output,
        u64::try_from(length)
            .map_err(|_| checkpoint_error("checkpoint vector length exceeds u64"))?,
    );
    Ok(())
}

fn push_f64_vector(output: &mut Vec<u8>, values: &[f64]) -> Result<(), RuntimeError> {
    push_vector_length(output, values.len())?;
    for value in values {
        push_f64(output, *value);
    }
    Ok(())
}

fn push_u32_vector(output: &mut Vec<u8>, values: &[u32]) -> Result<(), RuntimeError> {
    push_vector_length(output, values.len())?;
    for value in values {
        push_u32(output, *value);
    }
    Ok(())
}

fn push_bool_vector(output: &mut Vec<u8>, values: &[bool]) -> Result<(), RuntimeError> {
    push_vector_length(output, values.len())?;
    output.extend(values.iter().map(|value| u8::from(*value)));
    Ok(())
}

const fn status_to_u32(status: NonlinearNdthaExecutionStatus) -> u32 {
    match status {
        NonlinearNdthaExecutionStatus::Active => 0,
        NonlinearNdthaExecutionStatus::Completed => 1,
        NonlinearNdthaExecutionStatus::Collapsed => 2,
        NonlinearNdthaExecutionStatus::Nonconverged => 3,
    }
}

fn status_from_u32(value: u32) -> Result<NonlinearNdthaExecutionStatus, RuntimeError> {
    match value {
        0 => Ok(NonlinearNdthaExecutionStatus::Active),
        1 => Ok(NonlinearNdthaExecutionStatus::Completed),
        2 => Ok(NonlinearNdthaExecutionStatus::Collapsed),
        3 => Ok(NonlinearNdthaExecutionStatus::Nonconverged),
        _ => Err(checkpoint_error("checkpoint execution status is invalid")),
    }
}

struct Reader<'a> {
    bytes: &'a [u8],
    position: usize,
}

impl<'a> Reader<'a> {
    const fn new(bytes: &'a [u8]) -> Self {
        Self { bytes, position: 0 }
    }

    const fn position(&self) -> usize {
        self.position
    }

    const fn remaining(&self) -> usize {
        self.bytes.len() - self.position
    }

    fn take(&mut self, count: usize) -> Result<&'a [u8], RuntimeError> {
        let end = self
            .position
            .checked_add(count)
            .filter(|end| *end <= self.bytes.len())
            .ok_or_else(|| checkpoint_error("checkpoint artifact is truncated"))?;
        let output = &self.bytes[self.position..end];
        self.position = end;
        Ok(output)
    }

    fn u32(&mut self) -> Result<u32, RuntimeError> {
        let mut bytes = [0_u8; 4];
        bytes.copy_from_slice(self.take(4)?);
        Ok(u32::from_le_bytes(bytes))
    }

    fn i32(&mut self) -> Result<i32, RuntimeError> {
        let mut bytes = [0_u8; 4];
        bytes.copy_from_slice(self.take(4)?);
        Ok(i32::from_le_bytes(bytes))
    }

    fn u64(&mut self) -> Result<u64, RuntimeError> {
        let mut bytes = [0_u8; 8];
        bytes.copy_from_slice(self.take(8)?);
        Ok(u64::from_le_bytes(bytes))
    }

    fn f64(&mut self) -> Result<f64, RuntimeError> {
        let value = f64::from_bits(self.u64()?);
        if value.is_finite() {
            Ok(value)
        } else {
            Err(checkpoint_error(
                "checkpoint state contains a non-finite value",
            ))
        }
    }

    fn length(&mut self) -> Result<usize, RuntimeError> {
        let length = usize::try_from(self.u64()?)
            .map_err(|_| checkpoint_error("checkpoint length exceeds address space"))?;
        validate_vector_length(length)?;
        Ok(length)
    }

    fn artifact_length(&mut self) -> Result<usize, RuntimeError> {
        let length = usize::try_from(self.u64()?)
            .map_err(|_| checkpoint_error("checkpoint payload length exceeds address space"))?;
        if length <= MAX_ARTIFACT_BYTES - HEADER_SIZE {
            Ok(length)
        } else {
            Err(checkpoint_error(
                "checkpoint payload exceeds the bounded size",
            ))
        }
    }

    fn digest(&mut self) -> Result<DigestBytes, RuntimeError> {
        let mut digest = [0_u8; 32];
        digest.copy_from_slice(self.take(32)?);
        Ok(digest)
    }

    fn f64_vector(&mut self) -> Result<Vec<f64>, RuntimeError> {
        let length = self.length()?;
        let extent = length
            .checked_mul(std::mem::size_of::<f64>())
            .ok_or_else(|| checkpoint_error("checkpoint FP64 vector extent overflow"))?;
        if extent > self.remaining() {
            return Err(checkpoint_error("checkpoint FP64 vector is truncated"));
        }
        let mut output = Vec::new();
        output
            .try_reserve_exact(length)
            .map_err(|_| internal_error("checkpoint FP64 vector allocation failed"))?;
        for _ in 0..length {
            output.push(self.f64()?);
        }
        Ok(output)
    }

    fn u32_vector(&mut self) -> Result<Vec<u32>, RuntimeError> {
        let length = self.length()?;
        let extent = length
            .checked_mul(std::mem::size_of::<u32>())
            .ok_or_else(|| checkpoint_error("checkpoint U32 vector extent overflow"))?;
        if extent > self.remaining() {
            return Err(checkpoint_error("checkpoint U32 vector is truncated"));
        }
        let mut output = Vec::new();
        output
            .try_reserve_exact(length)
            .map_err(|_| internal_error("checkpoint U32 vector allocation failed"))?;
        for _ in 0..length {
            output.push(self.u32()?);
        }
        Ok(output)
    }

    fn bool_vector(&mut self) -> Result<Vec<bool>, RuntimeError> {
        let length = self.length()?;
        let values = self.take(length)?;
        let mut output = Vec::new();
        output
            .try_reserve_exact(length)
            .map_err(|_| internal_error("checkpoint bool vector allocation failed"))?;
        for value in values {
            match value {
                0 => output.push(false),
                1 => output.push(true),
                _ => return Err(checkpoint_error("checkpoint bool vector is not canonical")),
            }
        }
        Ok(output)
    }

    fn finish(&self) -> Result<(), RuntimeError> {
        if self.position == self.bytes.len() {
            Ok(())
        } else {
            Err(checkpoint_error("checkpoint artifact has trailing bytes"))
        }
    }
}

fn checkpoint_error(message: &str) -> RuntimeError {
    RuntimeError {
        code: CHECKPOINT_MISMATCH,
        message: message.to_owned(),
    }
}

fn internal_error(message: &str) -> RuntimeError {
    RuntimeError {
        code: INTERNAL_ERROR,
        message: message.to_owned(),
    }
}

fn io_error(action: &str, error: &std::io::Error) -> RuntimeError {
    RuntimeError {
        code: INTERNAL_ERROR,
        message: format!("{action} failed: {error}"),
    }
}

#[cfg(test)]
mod tests {
    use structural_ffi::{
        NonlinearNdthaExecutionStatus, NonlinearNdthaResponse, NonlinearNdthaRestartState,
    };

    use super::{decode_state, encode_state, format_digest, Reader, MAX_VECTOR_VALUES};

    fn state() -> NonlinearNdthaRestartState {
        NonlinearNdthaRestartState {
            next_step: 0,
            status: NonlinearNdthaExecutionStatus::Active,
            collapse_step: -1,
            collapse_time_s: 0.0,
            collapse_drift_ratio_pct: 0.0,
            collapse_top_displacement_m: 0.0,
            max_plastic_story_count: 0,
            max_drift_ratio_pct: 0.0,
            adaptive_iteration_sum: 0,
            total_line_search_backtracks: 0,
            displacement_m: vec![0.0],
            velocity_m_per_s: vec![0.0],
            acceleration_m_per_s2: vec![0.0],
            response: NonlinearNdthaResponse {
                top_displacement_m: vec![0.0],
                drift_ratio_pct: vec![0.0],
                base_shear_kn: vec![0.0],
                core_drift_pct: vec![0.0],
                core_shear_kn: vec![0.0],
                step_converged: vec![false],
                step_iterations: vec![0],
                step_plastic_story_count: vec![0],
                step_residual_inf: vec![0.0],
                story_drift_envelope_pct: vec![0.0],
                final_story_drift_pct: vec![0.0],
            },
            execution_backend: 1,
            fallback_count: 0,
        }
    }

    #[test]
    fn digest_format_is_fixed_width() {
        let formatted = format_digest(&[0xab; 32]);
        assert_eq!(formatted.len(), 71);
        assert!(formatted.starts_with("sha256:"));
        assert!(formatted.ends_with("abab"));
    }

    #[test]
    fn reader_rejects_truncation_without_panicking() {
        let error = Reader::new(&[1, 2, 3]).u32().expect_err("truncated u32");
        assert_eq!(error.code, 1301);
    }

    #[test]
    fn state_codec_rejects_noncanonical_values_even_with_an_independent_hash() {
        let encoded = encode_state(&state()).expect("canonical state");

        let mut nonfinite = encoded.clone();
        nonfinite[40..48].copy_from_slice(&f64::NAN.to_bits().to_le_bytes());
        assert_eq!(
            decode_state(&nonfinite)
                .expect_err("non-finite scalar")
                .code,
            1301
        );

        let mut excessive = encoded.clone();
        excessive[72..80].copy_from_slice(
            &u64::try_from(MAX_VECTOR_VALUES + 1)
                .expect("bounded length")
                .to_le_bytes(),
        );
        assert_eq!(
            decode_state(&excessive)
                .expect_err("excessive vector length")
                .code,
            1301
        );

        let mut noncanonical_bool = encoded;
        noncanonical_bool[208] = 2;
        assert_eq!(
            decode_state(&noncanonical_bool)
                .expect_err("noncanonical bool")
                .code,
            1301
        );
    }
}
