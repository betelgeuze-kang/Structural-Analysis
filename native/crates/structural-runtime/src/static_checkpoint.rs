use std::mem::size_of;

use sha2::{Digest, Sha256};
use structural_contracts::static_product::{
    nonlinear_static_execution_hash_v1, nonlinear_static_model_hash_v1,
    parse_nonlinear_static_request_v1, NonlinearStaticAnalysisRequestDocumentV1,
    NONLINEAR_STATIC_MAXIMUM_REQUEST_BYTES, NONLINEAR_STATIC_MAXIMUM_STORIES,
};
use structural_ffi::{NonlinearStaticExecutionStatus, NonlinearStaticRestartState};

use crate::RuntimeError;

const MAGIC: &[u8; 8] = b"SASTAC01";
const FORMAT_VERSION: u32 = 1;
const HEADER_SIZE: usize = 192;
const STATE_FORMAT_VERSION: u32 = 1;
const STATE_HEADER_SIZE: usize = 80;
const MAXIMUM_STATE_BYTES: usize =
    STATE_HEADER_SIZE + size_of::<f64>() * NONLINEAR_STATIC_MAXIMUM_STORIES as usize;
const STATE_DOMAIN: &[u8] = b"structural-nonlinear-static-newton-state.v1\0";
const CHECKPOINT_DOMAIN: &[u8] = b"structural-nonlinear-static-checkpoint.v1\0";
const CHECKPOINT_MISMATCH: u32 = 1301;

type DigestBytes = [u8; 32];

/// Complete identity receipt for a real nonlinear-static Newton boundary.
#[derive(Clone, Debug, Eq, PartialEq, serde::Serialize)]
pub struct NonlinearStaticCheckpointReceiptV1 {
    pub schema_version: &'static str,
    pub phase: &'static str,
    pub execution_status: &'static str,
    pub iterations: u32,
    pub line_search_backtracks: u32,
    pub request_hash: String,
    pub model_hash: String,
    pub state_hash: String,
    pub execution_hash: String,
    pub checkpoint_hash: String,
    pub artifact_bytes: u64,
}

/// Canonical binary checkpoint containing the exact request and complete Newton state.
#[derive(Clone, Debug, PartialEq)]
pub struct NonlinearStaticCheckpointV1 {
    bytes: Vec<u8>,
    state: NonlinearStaticRestartState,
    request_hash: DigestBytes,
    model_hash: DigestBytes,
    state_hash: DigestBytes,
    execution_hash: DigestBytes,
    checkpoint_hash: DigestBytes,
}

impl NonlinearStaticCheckpointV1 {
    pub(crate) fn create(
        request: &NonlinearStaticAnalysisRequestDocumentV1,
        state: &NonlinearStaticRestartState,
    ) -> Result<Self, RuntimeError> {
        validate_state_binding(request, state)?;
        let request_payload = request.canonical_bytes();
        if request_payload.is_empty()
            || request_payload.len() > NONLINEAR_STATIC_MAXIMUM_REQUEST_BYTES
        {
            return Err(checkpoint_error(
                "nonlinear-static checkpoint request payload is outside the bounded size",
            ));
        }
        let state_payload = encode_state(state)?;
        let request_hash = parse_identity(request.request_hash())?;
        let model_hash = parse_identity(&nonlinear_static_model_hash_v1(request)?)?;
        let execution_hash = parse_identity(&nonlinear_static_execution_hash_v1(request)?)?;
        let state_hash = domain_hash(STATE_DOMAIN, &[&state_payload]);
        let checkpoint_hash = checkpoint_hash(
            &request_hash,
            &model_hash,
            &state_hash,
            &execution_hash,
            request_payload,
            &state_payload,
        )?;
        let total = HEADER_SIZE
            .checked_add(request_payload.len())
            .and_then(|value| value.checked_add(state_payload.len()))
            .ok_or_else(|| checkpoint_error("nonlinear-static checkpoint length overflows"))?;
        let mut bytes = Vec::new();
        bytes
            .try_reserve_exact(total)
            .map_err(|_| internal_error("nonlinear-static checkpoint allocation failed"))?;
        bytes.extend_from_slice(MAGIC);
        bytes.extend_from_slice(&FORMAT_VERSION.to_le_bytes());
        bytes.extend_from_slice(
            &u32::try_from(HEADER_SIZE)
                .map_err(|_| internal_error("nonlinear-static header exceeds u32"))?
                .to_le_bytes(),
        );
        bytes.extend_from_slice(
            &u64::try_from(request_payload.len())
                .map_err(|_| checkpoint_error("nonlinear-static request exceeds u64"))?
                .to_le_bytes(),
        );
        bytes.extend_from_slice(
            &u64::try_from(state_payload.len())
                .map_err(|_| checkpoint_error("nonlinear-static state exceeds u64"))?
                .to_le_bytes(),
        );
        bytes.extend_from_slice(&request_hash);
        bytes.extend_from_slice(&model_hash);
        bytes.extend_from_slice(&state_hash);
        bytes.extend_from_slice(&execution_hash);
        bytes.extend_from_slice(&checkpoint_hash);
        bytes.extend_from_slice(request_payload);
        bytes.extend_from_slice(&state_payload);
        if bytes.len() != total {
            return Err(internal_error(
                "nonlinear-static checkpoint length invariant failed",
            ));
        }
        Ok(Self {
            bytes,
            state: state.clone(),
            request_hash,
            model_hash,
            state_hash,
            execution_hash,
            checkpoint_hash,
        })
    }

    /// Decode and verify every header, payload, canonical encoding, state binding, and hash.
    ///
    /// # Errors
    ///
    /// Returns checkpoint-mismatch semantics for malformed, truncated, oversized, noncanonical,
    /// corrupted, or internally inconsistent artifact bytes.
    #[allow(clippy::too_many_lines)]
    pub fn from_bytes(bytes: &[u8]) -> Result<Self, RuntimeError> {
        let maximum = HEADER_SIZE
            .checked_add(NONLINEAR_STATIC_MAXIMUM_REQUEST_BYTES)
            .and_then(|value| value.checked_add(MAXIMUM_STATE_BYTES))
            .ok_or_else(|| internal_error("nonlinear-static checkpoint maximum overflows"))?;
        if bytes.len() < HEADER_SIZE || bytes.len() > maximum {
            return Err(checkpoint_error(
                "nonlinear-static checkpoint size is outside the bounded range",
            ));
        }
        let mut reader = Reader::new(bytes);
        if reader.take(MAGIC.len())? != MAGIC {
            return Err(checkpoint_error(
                "nonlinear-static checkpoint magic does not match",
            ));
        }
        if reader.u32()? != FORMAT_VERSION {
            return Err(checkpoint_error(
                "nonlinear-static checkpoint format version is unsupported",
            ));
        }
        if usize::try_from(reader.u32()?).ok() != Some(HEADER_SIZE) {
            return Err(checkpoint_error(
                "nonlinear-static checkpoint header size does not match",
            ));
        }
        let request_length = usize::try_from(reader.u64()?).map_err(|_| {
            checkpoint_error("nonlinear-static request length exceeds address space")
        })?;
        let state_length = usize::try_from(reader.u64()?)
            .map_err(|_| checkpoint_error("nonlinear-static state length exceeds address space"))?;
        if request_length == 0
            || request_length > NONLINEAR_STATIC_MAXIMUM_REQUEST_BYTES
            || !(STATE_HEADER_SIZE..=MAXIMUM_STATE_BYTES).contains(&state_length)
        {
            return Err(checkpoint_error(
                "nonlinear-static checkpoint payload lengths are outside the bounded range",
            ));
        }
        let request_hash = reader.digest()?;
        let model_hash = reader.digest()?;
        let state_hash = reader.digest()?;
        let execution_hash = reader.digest()?;
        let checkpoint_hash_value = reader.digest()?;
        let payload_length = request_length.checked_add(state_length).ok_or_else(|| {
            checkpoint_error("nonlinear-static checkpoint payload length overflows")
        })?;
        if reader.position() != HEADER_SIZE || reader.remaining() != payload_length {
            return Err(checkpoint_error(
                "nonlinear-static checkpoint payload length does not match artifact",
            ));
        }
        let request_payload = reader.take(request_length)?;
        let state_payload = reader.take(state_length)?;
        reader.finish()?;
        let request = parse_nonlinear_static_request_v1(request_payload).map_err(|_| {
            checkpoint_error("nonlinear-static checkpoint request violates its strict contract")
        })?;
        if request.canonical_bytes() != request_payload {
            return Err(checkpoint_error(
                "nonlinear-static checkpoint request payload is not canonical",
            ));
        }
        let state = decode_state(state_payload)?;
        if encode_state(&state)? != state_payload {
            return Err(checkpoint_error(
                "nonlinear-static checkpoint state payload is not canonical",
            ));
        }
        validate_state_binding(&request, &state)?;
        let derived_request_hash = parse_identity(request.request_hash())?;
        let derived_model_hash = parse_identity(&nonlinear_static_model_hash_v1(&request)?)?;
        let derived_execution_hash =
            parse_identity(&nonlinear_static_execution_hash_v1(&request)?)?;
        let derived_state_hash = domain_hash(STATE_DOMAIN, &[state_payload]);
        if request_hash != derived_request_hash
            || model_hash != derived_model_hash
            || state_hash != derived_state_hash
            || execution_hash != derived_execution_hash
        {
            return Err(checkpoint_error(
                "nonlinear-static checkpoint derived identity does not match payload",
            ));
        }
        let expected = checkpoint_hash(
            &request_hash,
            &model_hash,
            &state_hash,
            &execution_hash,
            request_payload,
            state_payload,
        )?;
        if checkpoint_hash_value != expected {
            return Err(checkpoint_error(
                "nonlinear-static checkpoint aggregate hash does not match",
            ));
        }
        Ok(Self {
            bytes: bytes.to_vec(),
            state,
            request_hash,
            model_hash,
            state_hash,
            execution_hash,
            checkpoint_hash: checkpoint_hash_value,
        })
    }

    #[must_use]
    pub fn as_bytes(&self) -> &[u8] {
        &self.bytes
    }

    #[must_use]
    pub const fn state(&self) -> &NonlinearStaticRestartState {
        &self.state
    }

    #[must_use]
    pub fn receipt(&self) -> NonlinearStaticCheckpointReceiptV1 {
        NonlinearStaticCheckpointReceiptV1 {
            schema_version: "structural-nonlinear-static-checkpoint-receipt.v1",
            phase: match self.state.status {
                NonlinearStaticExecutionStatus::Active => "newton_iteration_boundary",
                NonlinearStaticExecutionStatus::Converged
                | NonlinearStaticExecutionStatus::Nonconverged => "newton_terminal_boundary",
            },
            execution_status: status_name(self.state.status),
            iterations: self.state.iterations,
            line_search_backtracks: self.state.line_search_backtracks,
            request_hash: format_identity(&self.request_hash),
            model_hash: format_identity(&self.model_hash),
            state_hash: format_identity(&self.state_hash),
            execution_hash: format_identity(&self.execution_hash),
            checkpoint_hash: format_identity(&self.checkpoint_hash),
            artifact_bytes: u64::try_from(self.bytes.len()).unwrap_or(u64::MAX),
        }
    }

    pub(crate) fn verify_request(
        &self,
        request: &NonlinearStaticAnalysisRequestDocumentV1,
    ) -> Result<(), RuntimeError> {
        if self.request_hash != parse_identity(request.request_hash())?
            || self.model_hash != parse_identity(&nonlinear_static_model_hash_v1(request)?)?
            || self.execution_hash != parse_identity(&nonlinear_static_execution_hash_v1(request)?)?
        {
            return Err(checkpoint_error(
                "nonlinear-static checkpoint bindings do not match request",
            ));
        }
        validate_state_binding(request, &self.state)
    }
}

fn encode_state(state: &NonlinearStaticRestartState) -> Result<Vec<u8>, RuntimeError> {
    let vector_length = state.displacement_m.len();
    if vector_length == 0 || vector_length > NONLINEAR_STATIC_MAXIMUM_STORIES as usize {
        return Err(checkpoint_error(
            "nonlinear-static state vector length is outside the bounded range",
        ));
    }
    let total = STATE_HEADER_SIZE
        .checked_add(
            vector_length
                .checked_mul(size_of::<f64>())
                .ok_or_else(|| checkpoint_error("nonlinear-static state bytes overflow"))?,
        )
        .ok_or_else(|| checkpoint_error("nonlinear-static state length overflows"))?;
    let mut bytes = Vec::new();
    bytes
        .try_reserve_exact(total)
        .map_err(|_| internal_error("nonlinear-static state allocation failed"))?;
    for value in [
        STATE_FORMAT_VERSION,
        status_raw(state.status),
        state.iterations,
        state.line_search_backtracks,
        state.plastic_story_count,
        state.execution_backend,
        state.fallback_count,
        0,
    ] {
        bytes.extend_from_slice(&value.to_le_bytes());
    }
    for value in [
        state.residual_inf,
        state.residual_l2,
        state.max_abs_displacement_m,
        state.top_displacement_m,
        state.base_shear_kn,
    ] {
        bytes.extend_from_slice(&value.to_bits().to_le_bytes());
    }
    bytes.extend_from_slice(
        &u64::try_from(vector_length)
            .map_err(|_| checkpoint_error("nonlinear-static vector length exceeds u64"))?
            .to_le_bytes(),
    );
    for value in &state.displacement_m {
        bytes.extend_from_slice(&value.to_bits().to_le_bytes());
    }
    if bytes.len() != total {
        return Err(internal_error(
            "nonlinear-static state encoding length invariant failed",
        ));
    }
    Ok(bytes)
}

fn decode_state(bytes: &[u8]) -> Result<NonlinearStaticRestartState, RuntimeError> {
    if bytes.len() < STATE_HEADER_SIZE || bytes.len() > MAXIMUM_STATE_BYTES {
        return Err(checkpoint_error(
            "nonlinear-static state payload size is outside the bounded range",
        ));
    }
    let mut reader = Reader::new(bytes);
    if reader.u32()? != STATE_FORMAT_VERSION {
        return Err(checkpoint_error(
            "nonlinear-static state format version is unsupported",
        ));
    }
    let status = status_from_raw(reader.u32()?)?;
    let iterations = reader.u32()?;
    let line_search_backtracks = reader.u32()?;
    let plastic_story_count = reader.u32()?;
    let execution_backend = reader.u32()?;
    let fallback_count = reader.u32()?;
    if reader.u32()? != 0 {
        return Err(checkpoint_error(
            "nonlinear-static state reserved field is not zero",
        ));
    }
    let residual_inf = reader.f64()?;
    let residual_l2 = reader.f64()?;
    let max_abs_displacement_m = reader.f64()?;
    let top_displacement_m = reader.f64()?;
    let base_shear_kn = reader.f64()?;
    let vector_length = usize::try_from(reader.u64()?).map_err(|_| {
        checkpoint_error("nonlinear-static state vector length exceeds address space")
    })?;
    if vector_length == 0 || vector_length > NONLINEAR_STATIC_MAXIMUM_STORIES as usize {
        return Err(checkpoint_error(
            "nonlinear-static state vector length is outside the bounded range",
        ));
    }
    let expected = STATE_HEADER_SIZE
        .checked_add(
            vector_length
                .checked_mul(size_of::<f64>())
                .ok_or_else(|| checkpoint_error("nonlinear-static vector bytes overflow"))?,
        )
        .ok_or_else(|| checkpoint_error("nonlinear-static state length overflows"))?;
    if bytes.len() != expected {
        return Err(checkpoint_error(
            "nonlinear-static state vector length does not match payload",
        ));
    }
    let mut displacement_m = Vec::new();
    displacement_m
        .try_reserve_exact(vector_length)
        .map_err(|_| internal_error("nonlinear-static vector allocation failed"))?;
    for _ in 0..vector_length {
        displacement_m.push(reader.f64()?);
    }
    reader.finish()?;
    Ok(NonlinearStaticRestartState {
        status,
        iterations,
        line_search_backtracks,
        plastic_story_count,
        residual_inf,
        residual_l2,
        max_abs_displacement_m,
        top_displacement_m,
        base_shear_kn,
        displacement_m,
        execution_backend,
        fallback_count,
    })
}

fn validate_state_binding(
    request: &NonlinearStaticAnalysisRequestDocumentV1,
    state: &NonlinearStaticRestartState,
) -> Result<(), RuntimeError> {
    let value = request.request();
    let count = usize::try_from(value.config.story_count)
        .map_err(|_| checkpoint_error("nonlinear-static story_count exceeds address space"))?;
    let metrics = [
        state.residual_inf,
        state.residual_l2,
        state.max_abs_displacement_m,
        state.top_displacement_m,
        state.base_shear_kn,
    ];
    let basic_valid = state.displacement_m.len() == count
        && state.displacement_m.iter().all(|item| item.is_finite())
        && metrics.into_iter().all(f64::is_finite)
        && state.iterations <= value.config.max_iter
        && state.execution_backend == 1
        && state.fallback_count == 0;
    if !basic_valid {
        return Err(checkpoint_error(
            "nonlinear-static checkpoint state does not match the exact request",
        ));
    }
    let expected = derived_response(value, &state.displacement_m)?;
    let recovered = state.residual_inf.to_bits() == expected.residual_inf.to_bits()
        && state.residual_l2.to_bits() == expected.residual_l2.to_bits()
        && state.max_abs_displacement_m.to_bits() == expected.max_abs_displacement_m.to_bits()
        && state.top_displacement_m.to_bits() == expected.top_displacement_m.to_bits()
        && state.base_shear_kn.to_bits() == expected.base_shear_kn.to_bits()
        && state.plastic_story_count == expected.plastic_story_count;
    let status_valid = match state.status {
        NonlinearStaticExecutionStatus::Active => state.iterations < value.config.max_iter,
        NonlinearStaticExecutionStatus::Converged => {
            state.iterations > 0 && state.residual_inf <= value.config.tolerance
        }
        NonlinearStaticExecutionStatus::Nonconverged => state.iterations > 0,
    };
    if recovered && status_valid {
        Ok(())
    } else {
        Err(checkpoint_error(
            "nonlinear-static checkpoint state fails deterministic recovery",
        ))
    }
}

struct DerivedResponse {
    residual_inf: f64,
    residual_l2: f64,
    max_abs_displacement_m: f64,
    top_displacement_m: f64,
    base_shear_kn: f64,
    plastic_story_count: u32,
}

fn derived_response(
    request: &structural_contracts::static_product::NonlinearStaticAnalysisRequestV1,
    displacement_m: &[f64],
) -> Result<DerivedResponse, RuntimeError> {
    let count = displacement_m.len();
    let mut spring_force = Vec::new();
    spring_force
        .try_reserve_exact(count)
        .map_err(|_| internal_error("nonlinear-static recovery allocation failed"))?;
    spring_force.resize(count, 0.0);
    let mut plastic_story_count = 0_u32;
    for index in 0..count {
        let previous = if index == 0 {
            0.0
        } else {
            displacement_m[index - 1]
        };
        let drift = displacement_m[index] - previous;
        let initial = request.inputs.story_k_n_per_m[index].max(1.0e-12);
        let yield_drift = request.inputs.story_yield_drift_m[index].abs().max(1.0e-9);
        spring_force[index] = if drift.abs() <= yield_drift {
            initial * drift
        } else {
            plastic_story_count = plastic_story_count
                .checked_add(1)
                .ok_or_else(|| checkpoint_error("plastic-story count overflowed"))?;
            let sign = if drift >= 0.0 { 1.0 } else { -1.0 };
            sign * (initial * yield_drift
                + request.config.hardening_ratio * initial * (drift.abs() - yield_drift))
        };
    }
    let mut residual_inf = 0.0_f64;
    let mut residual_square_sum = 0.0_f64;
    for index in 0..count {
        let internal = if index < count - 1 {
            spring_force[index] - spring_force[index + 1]
        } else {
            spring_force[index]
        };
        let residual = request.inputs.floor_load_n[index] - internal;
        residual_inf = residual_inf.max(residual.abs());
        residual_square_sum += residual * residual;
    }
    Ok(DerivedResponse {
        residual_inf,
        residual_l2: residual_square_sum.sqrt(),
        max_abs_displacement_m: displacement_m
            .iter()
            .fold(0.0_f64, |maximum, value| maximum.max(value.abs())),
        top_displacement_m: displacement_m[count - 1],
        base_shear_kn: spring_force[0].abs() / 1000.0,
        plastic_story_count,
    })
}

fn checkpoint_hash(
    request_hash: &DigestBytes,
    model_hash: &DigestBytes,
    state_hash: &DigestBytes,
    execution_hash: &DigestBytes,
    request_payload: &[u8],
    state_payload: &[u8],
) -> Result<DigestBytes, RuntimeError> {
    let request_length = u64::try_from(request_payload.len())
        .map_err(|_| checkpoint_error("nonlinear-static request exceeds u64"))?;
    let state_length = u64::try_from(state_payload.len())
        .map_err(|_| checkpoint_error("nonlinear-static state exceeds u64"))?;
    Ok(domain_hash(
        CHECKPOINT_DOMAIN,
        &[
            request_hash,
            model_hash,
            state_hash,
            execution_hash,
            &request_length.to_le_bytes(),
            &state_length.to_le_bytes(),
            &Sha256::digest(request_payload),
            &Sha256::digest(state_payload),
        ],
    ))
}

fn domain_hash(domain: &[u8], parts: &[&[u8]]) -> DigestBytes {
    let mut hasher = Sha256::new();
    hasher.update(domain);
    for part in parts {
        hasher.update(part);
    }
    hasher.finalize().into()
}

fn parse_identity(value: &str) -> Result<DigestBytes, RuntimeError> {
    let hex = value.strip_prefix("sha256:").unwrap_or_default();
    if hex.len() != 64 {
        return Err(checkpoint_error(
            "nonlinear-static checkpoint hash identity is invalid",
        ));
    }
    let mut digest = [0_u8; 32];
    for (index, pair) in hex.as_bytes().chunks_exact(2).enumerate() {
        digest[index] = (hex_digit(pair[0])? << 4) | hex_digit(pair[1])?;
    }
    Ok(digest)
}

fn hex_digit(value: u8) -> Result<u8, RuntimeError> {
    match value {
        b'0'..=b'9' => Ok(value - b'0'),
        b'a'..=b'f' => Ok(value - b'a' + 10),
        _ => Err(checkpoint_error(
            "nonlinear-static checkpoint hash identity is invalid",
        )),
    }
}

fn format_identity(value: &DigestBytes) -> String {
    let mut output = String::with_capacity(71);
    output.push_str("sha256:");
    for byte in value {
        use std::fmt::Write as _;
        write!(&mut output, "{byte:02x}").expect("String writes cannot fail");
    }
    output
}

const fn status_raw(value: NonlinearStaticExecutionStatus) -> u32 {
    match value {
        NonlinearStaticExecutionStatus::Active => 0,
        NonlinearStaticExecutionStatus::Converged => 1,
        NonlinearStaticExecutionStatus::Nonconverged => 2,
    }
}

fn status_from_raw(value: u32) -> Result<NonlinearStaticExecutionStatus, RuntimeError> {
    match value {
        0 => Ok(NonlinearStaticExecutionStatus::Active),
        1 => Ok(NonlinearStaticExecutionStatus::Converged),
        2 => Ok(NonlinearStaticExecutionStatus::Nonconverged),
        _ => Err(checkpoint_error(
            "nonlinear-static checkpoint execution status is invalid",
        )),
    }
}

const fn status_name(value: NonlinearStaticExecutionStatus) -> &'static str {
    match value {
        NonlinearStaticExecutionStatus::Active => "active",
        NonlinearStaticExecutionStatus::Converged => "converged",
        NonlinearStaticExecutionStatus::Nonconverged => "nonconverged",
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
        code: 1900,
        message: message.to_owned(),
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

    fn remaining(&self) -> usize {
        self.bytes.len().saturating_sub(self.position)
    }

    fn take(&mut self, count: usize) -> Result<&'a [u8], RuntimeError> {
        let end = self
            .position
            .checked_add(count)
            .ok_or_else(|| checkpoint_error("nonlinear-static checkpoint offset overflows"))?;
        let value = self
            .bytes
            .get(self.position..end)
            .ok_or_else(|| checkpoint_error("nonlinear-static checkpoint is truncated"))?;
        self.position = end;
        Ok(value)
    }

    fn u32(&mut self) -> Result<u32, RuntimeError> {
        let mut bytes = [0_u8; 4];
        bytes.copy_from_slice(self.take(4)?);
        Ok(u32::from_le_bytes(bytes))
    }

    fn u64(&mut self) -> Result<u64, RuntimeError> {
        let mut bytes = [0_u8; 8];
        bytes.copy_from_slice(self.take(8)?);
        Ok(u64::from_le_bytes(bytes))
    }

    fn f64(&mut self) -> Result<f64, RuntimeError> {
        Ok(f64::from_bits(self.u64()?))
    }

    fn digest(&mut self) -> Result<DigestBytes, RuntimeError> {
        let mut bytes = [0_u8; 32];
        bytes.copy_from_slice(self.take(32)?);
        Ok(bytes)
    }

    fn finish(&self) -> Result<(), RuntimeError> {
        if self.position == self.bytes.len() {
            Ok(())
        } else {
            Err(checkpoint_error(
                "nonlinear-static checkpoint contains trailing bytes",
            ))
        }
    }
}
