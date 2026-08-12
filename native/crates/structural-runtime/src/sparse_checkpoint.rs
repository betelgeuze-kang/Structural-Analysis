use std::mem::size_of;

use sha2::{Digest, Sha256};
use structural_contracts::sparse_product::{
    parse_sparse_linear_request_v1, sparse_linear_execution_hash_v1, sparse_linear_model_hash_v1,
    SparseLinearAnalysisRequestDocumentV1, SPARSE_LINEAR_MAXIMUM_ORDER,
    SPARSE_LINEAR_MAXIMUM_REQUEST_BYTES,
};
use structural_ffi::{
    SparseLinearExecutionStatus, SparseLinearRestartState, SparseLinearSolverStatus,
};

use crate::RuntimeError;

const MAGIC: &[u8; 8] = b"SAPCGC01";
const FORMAT_VERSION: u32 = 1;
const HEADER_SIZE: usize = 192;
const STATE_FORMAT_VERSION: u32 = 1;
const STATE_HEADER_SIZE: usize = 72;
const MAXIMUM_STATE_BYTES: usize = STATE_HEADER_SIZE + 4 * 8 * SPARSE_LINEAR_MAXIMUM_ORDER as usize;
const STATE_DOMAIN: &[u8] = b"structural-sparse-linear-pcg-state.v1\0";
const CHECKPOINT_DOMAIN: &[u8] = b"structural-sparse-linear-checkpoint.v1\0";
const CHECKPOINT_MISMATCH: u32 = 1301;

type DigestBytes = [u8; 32];

/// Complete identity receipt for a real PCG iteration boundary.
#[derive(Clone, Debug, Eq, PartialEq, serde::Serialize)]
pub struct SparseLinearCheckpointReceiptV1 {
    pub schema_version: &'static str,
    pub phase: &'static str,
    pub execution_status: &'static str,
    pub solver_status: &'static str,
    pub iterations: u32,
    pub request_hash: String,
    pub model_hash: String,
    pub state_hash: String,
    pub execution_hash: String,
    pub checkpoint_hash: String,
    pub artifact_bytes: u64,
}

/// Canonical binary checkpoint containing the exact request and all resumable PCG vectors.
#[derive(Clone, Debug, PartialEq)]
pub struct SparseLinearCheckpointV1 {
    bytes: Vec<u8>,
    state: SparseLinearRestartState,
    request_hash: DigestBytes,
    model_hash: DigestBytes,
    state_hash: DigestBytes,
    execution_hash: DigestBytes,
    checkpoint_hash: DigestBytes,
}

impl SparseLinearCheckpointV1 {
    pub(crate) fn create(
        request: &SparseLinearAnalysisRequestDocumentV1,
        state: &SparseLinearRestartState,
    ) -> Result<Self, RuntimeError> {
        validate_state_binding(request, state)?;
        let request_payload = request.canonical_bytes();
        if request_payload.is_empty() || request_payload.len() > SPARSE_LINEAR_MAXIMUM_REQUEST_BYTES
        {
            return Err(checkpoint_error(
                "sparse checkpoint request payload is outside the bounded size",
            ));
        }
        let state_payload = encode_state(state)?;
        let request_hash = parse_identity(request.request_hash())?;
        let model_hash = parse_identity(&sparse_linear_model_hash_v1(request)?)?;
        let execution_hash = parse_identity(&sparse_linear_execution_hash_v1(request)?)?;
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
            .ok_or_else(|| checkpoint_error("sparse checkpoint artifact length overflows"))?;
        let mut bytes = Vec::new();
        bytes
            .try_reserve_exact(total)
            .map_err(|_| internal_error("sparse checkpoint allocation failed"))?;
        bytes.extend_from_slice(MAGIC);
        bytes.extend_from_slice(&FORMAT_VERSION.to_le_bytes());
        bytes.extend_from_slice(
            &u32::try_from(HEADER_SIZE)
                .map_err(|_| internal_error("sparse checkpoint header size exceeds u32"))?
                .to_le_bytes(),
        );
        bytes.extend_from_slice(
            &u64::try_from(request_payload.len())
                .map_err(|_| checkpoint_error("sparse request payload exceeds u64"))?
                .to_le_bytes(),
        );
        bytes.extend_from_slice(
            &u64::try_from(state_payload.len())
                .map_err(|_| checkpoint_error("sparse state payload exceeds u64"))?
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
            return Err(internal_error("sparse checkpoint length invariant failed"));
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

    /// Decode and verify every header, payload, canonical encoding, and derived identity.
    ///
    /// # Errors
    ///
    /// Returns checkpoint-mismatch semantics for malformed, truncated, oversized, noncanonical,
    /// corrupted, or internally inconsistent artifact bytes.
    #[allow(clippy::too_many_lines)] // Keeping the ordered binary audit in one fail-closed parser is clearer.
    pub fn from_bytes(bytes: &[u8]) -> Result<Self, RuntimeError> {
        let maximum = HEADER_SIZE
            .checked_add(SPARSE_LINEAR_MAXIMUM_REQUEST_BYTES)
            .and_then(|value| value.checked_add(MAXIMUM_STATE_BYTES))
            .ok_or_else(|| internal_error("sparse checkpoint maximum length overflows"))?;
        if bytes.len() < HEADER_SIZE || bytes.len() > maximum {
            return Err(checkpoint_error(
                "sparse checkpoint artifact size is outside the bounded range",
            ));
        }
        let mut reader = Reader::new(bytes);
        if reader.take(MAGIC.len())? != MAGIC {
            return Err(checkpoint_error("sparse checkpoint magic does not match"));
        }
        if reader.u32()? != FORMAT_VERSION {
            return Err(checkpoint_error(
                "sparse checkpoint format version is unsupported",
            ));
        }
        if usize::try_from(reader.u32()?).ok() != Some(HEADER_SIZE) {
            return Err(checkpoint_error(
                "sparse checkpoint header size does not match",
            ));
        }
        let request_length = usize::try_from(reader.u64()?).map_err(|_| {
            checkpoint_error("sparse checkpoint request length exceeds address space")
        })?;
        let state_length = usize::try_from(reader.u64()?).map_err(|_| {
            checkpoint_error("sparse checkpoint state length exceeds address space")
        })?;
        if request_length == 0
            || request_length > SPARSE_LINEAR_MAXIMUM_REQUEST_BYTES
            || !(STATE_HEADER_SIZE..=MAXIMUM_STATE_BYTES).contains(&state_length)
        {
            return Err(checkpoint_error(
                "sparse checkpoint payload lengths are outside the bounded range",
            ));
        }
        let request_hash = reader.digest()?;
        let model_hash = reader.digest()?;
        let state_hash = reader.digest()?;
        let execution_hash = reader.digest()?;
        let checkpoint_hash_value = reader.digest()?;
        let payload_length = request_length
            .checked_add(state_length)
            .ok_or_else(|| checkpoint_error("sparse checkpoint payload length overflows"))?;
        if reader.position() != HEADER_SIZE || reader.remaining() != payload_length {
            return Err(checkpoint_error(
                "sparse checkpoint payload length does not match artifact",
            ));
        }
        let request_payload = reader.take(request_length)?;
        let state_payload = reader.take(state_length)?;
        reader.finish()?;
        let request = parse_sparse_linear_request_v1(request_payload).map_err(|_| {
            checkpoint_error("sparse checkpoint request violates its strict contract")
        })?;
        if request.canonical_bytes() != request_payload {
            return Err(checkpoint_error(
                "sparse checkpoint request payload is not canonical",
            ));
        }
        let state = decode_state(state_payload)?;
        if encode_state(&state)? != state_payload {
            return Err(checkpoint_error(
                "sparse checkpoint state payload is not canonical",
            ));
        }
        validate_state_binding(&request, &state)?;
        let derived_request_hash = parse_identity(request.request_hash())?;
        let derived_model_hash = parse_identity(&sparse_linear_model_hash_v1(&request)?)?;
        let derived_execution_hash = parse_identity(&sparse_linear_execution_hash_v1(&request)?)?;
        let derived_state_hash = domain_hash(STATE_DOMAIN, &[state_payload]);
        if request_hash != derived_request_hash
            || model_hash != derived_model_hash
            || state_hash != derived_state_hash
            || execution_hash != derived_execution_hash
        {
            return Err(checkpoint_error(
                "sparse checkpoint derived identity does not match payload",
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
                "sparse checkpoint aggregate hash does not match",
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
    pub const fn state(&self) -> &SparseLinearRestartState {
        &self.state
    }

    #[must_use]
    pub fn receipt(&self) -> SparseLinearCheckpointReceiptV1 {
        SparseLinearCheckpointReceiptV1 {
            schema_version: "structural-sparse-linear-checkpoint-receipt.v1",
            phase: match self.state.execution_status {
                SparseLinearExecutionStatus::Active => "pcg_iteration_boundary",
                SparseLinearExecutionStatus::Terminal => "pcg_terminal_boundary",
            },
            execution_status: execution_status_name(self.state.execution_status),
            solver_status: solver_status_name(self.state.solver_status),
            iterations: self.state.iterations,
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
        request: &SparseLinearAnalysisRequestDocumentV1,
    ) -> Result<(), RuntimeError> {
        if self.request_hash != parse_identity(request.request_hash())?
            || self.model_hash != parse_identity(&sparse_linear_model_hash_v1(request)?)?
            || self.execution_hash != parse_identity(&sparse_linear_execution_hash_v1(request)?)?
        {
            return Err(checkpoint_error(
                "sparse checkpoint bindings do not match request",
            ));
        }
        validate_state_binding(request, &self.state)
    }
}

fn encode_state(state: &SparseLinearRestartState) -> Result<Vec<u8>, RuntimeError> {
    let vector_length = state.solution.len();
    if vector_length == 0 || vector_length > SPARSE_LINEAR_MAXIMUM_ORDER as usize {
        return Err(checkpoint_error(
            "sparse checkpoint state vector length is outside the bounded range",
        ));
    }
    let total = STATE_HEADER_SIZE
        .checked_add(
            vector_length
                .checked_mul(4 * size_of::<f64>())
                .ok_or_else(|| checkpoint_error("sparse state vector bytes overflow"))?,
        )
        .ok_or_else(|| checkpoint_error("sparse state payload length overflows"))?;
    let mut bytes = Vec::new();
    bytes
        .try_reserve_exact(total)
        .map_err(|_| internal_error("sparse state allocation failed"))?;
    for value in [
        STATE_FORMAT_VERSION,
        execution_status_raw(state.execution_status),
        solver_status_raw(state.solver_status),
        state.iterations,
        state.execution_backend,
        state.fallback_count,
        0,
        0,
    ] {
        bytes.extend_from_slice(&value.to_le_bytes());
    }
    for value in [
        state.initial_residual_inf,
        state.convergence_limit,
        state.rho,
        state.last_increment_inf,
    ] {
        bytes.extend_from_slice(&value.to_bits().to_le_bytes());
    }
    bytes.extend_from_slice(
        &u64::try_from(vector_length)
            .map_err(|_| checkpoint_error("sparse state vector length exceeds u64"))?
            .to_le_bytes(),
    );
    for vector in [
        &state.solution,
        &state.residual,
        &state.direction,
        &state.diagonal_inverse,
    ] {
        for value in vector {
            bytes.extend_from_slice(&value.to_bits().to_le_bytes());
        }
    }
    if bytes.len() != total {
        return Err(internal_error(
            "sparse state encoding length invariant failed",
        ));
    }
    Ok(bytes)
}

fn decode_state(bytes: &[u8]) -> Result<SparseLinearRestartState, RuntimeError> {
    if bytes.len() < STATE_HEADER_SIZE || bytes.len() > MAXIMUM_STATE_BYTES {
        return Err(checkpoint_error(
            "sparse state payload size is outside the bounded range",
        ));
    }
    let mut reader = Reader::new(bytes);
    if reader.u32()? != STATE_FORMAT_VERSION {
        return Err(checkpoint_error(
            "sparse state format version is unsupported",
        ));
    }
    let execution_status = execution_status_from_raw(reader.u32()?)?;
    let solver_status = solver_status_from_raw(reader.u32()?)?;
    let iterations = reader.u32()?;
    let execution_backend = reader.u32()?;
    let fallback_count = reader.u32()?;
    if reader.u32()? != 0 || reader.u32()? != 0 {
        return Err(checkpoint_error(
            "sparse state reserved fields are not zero",
        ));
    }
    let initial_residual_inf = reader.f64()?;
    let convergence_limit = reader.f64()?;
    let rho = reader.f64()?;
    let last_increment_inf = reader.f64()?;
    let vector_length = usize::try_from(reader.u64()?)
        .map_err(|_| checkpoint_error("sparse state vector length exceeds address space"))?;
    if vector_length == 0 || vector_length > SPARSE_LINEAR_MAXIMUM_ORDER as usize {
        return Err(checkpoint_error(
            "sparse state vector length is outside the bounded range",
        ));
    }
    let expected = STATE_HEADER_SIZE
        .checked_add(
            vector_length
                .checked_mul(4 * size_of::<f64>())
                .ok_or_else(|| checkpoint_error("sparse state vector bytes overflow"))?,
        )
        .ok_or_else(|| checkpoint_error("sparse state length overflows"))?;
    if bytes.len() != expected {
        return Err(checkpoint_error(
            "sparse state vector length does not match payload",
        ));
    }
    let mut decode_vector = || -> Result<Vec<f64>, RuntimeError> {
        let mut values = Vec::new();
        values
            .try_reserve_exact(vector_length)
            .map_err(|_| internal_error("sparse state vector allocation failed"))?;
        for _ in 0..vector_length {
            values.push(reader.f64()?);
        }
        Ok(values)
    };
    let state = SparseLinearRestartState {
        execution_status,
        solver_status,
        iterations,
        initial_residual_inf,
        convergence_limit,
        rho,
        last_increment_inf,
        solution: decode_vector()?,
        residual: decode_vector()?,
        direction: decode_vector()?,
        diagonal_inverse: decode_vector()?,
        execution_backend,
        fallback_count,
    };
    reader.finish()?;
    Ok(state)
}

fn validate_state_binding(
    request: &SparseLinearAnalysisRequestDocumentV1,
    state: &SparseLinearRestartState,
) -> Result<(), RuntimeError> {
    let value = request.request();
    let order = usize::try_from(value.order)
        .map_err(|_| checkpoint_error("sparse request order exceeds address space"))?;
    let lengths_valid = state.solution.len() == order
        && state.residual.len() == order
        && state.direction.len() == order
        && state.diagonal_inverse.len() == order;
    let vectors_finite = state.solution.iter().all(|item| item.is_finite())
        && state.residual.iter().all(|item| item.is_finite())
        && state.direction.iter().all(|item| item.is_finite())
        && state.diagonal_inverse.iter().all(|item| item.is_finite());
    let expected_limit = value.config.absolute_residual_tolerance
        + value.config.relative_residual_tolerance * norm_inf(&value.right_hand_side);
    let scalars_valid = state.initial_residual_inf.is_finite()
        && state.initial_residual_inf >= 0.0
        && state.convergence_limit.to_bits() == expected_limit.to_bits()
        && state.rho.is_finite()
        && state.last_increment_inf.is_finite()
        && state.last_increment_inf >= 0.0;
    let status_valid = match state.execution_status {
        SparseLinearExecutionStatus::Active => {
            state.solver_status == SparseLinearSolverStatus::Nonconvergence
                && state.iterations < value.config.max_iterations
                && state.rho > 0.0
                && state.diagonal_inverse.iter().all(|item| *item > 0.0)
                && norm_inf(&state.residual) > state.convergence_limit
        }
        SparseLinearExecutionStatus::Terminal => match state.solver_status {
            SparseLinearSolverStatus::Converged => {
                norm_inf(&state.residual) <= state.convergence_limit
            }
            SparseLinearSolverStatus::Nonconvergence => {
                state.iterations == value.config.max_iterations
            }
            SparseLinearSolverStatus::Singularity
            | SparseLinearSolverStatus::IndefiniteOperator
            | SparseLinearSolverStatus::IncrementLimit
            | SparseLinearSolverStatus::ResidualLimit => true,
        },
    };
    if lengths_valid
        && vectors_finite
        && scalars_valid
        && status_valid
        && state.iterations <= value.config.max_iterations
        && state.execution_backend == 1
        && state.fallback_count == 0
    {
        Ok(())
    } else {
        Err(checkpoint_error(
            "sparse checkpoint state does not match the exact request",
        ))
    }
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
        .map_err(|_| checkpoint_error("sparse request payload exceeds u64"))?;
    let state_length = u64::try_from(state_payload.len())
        .map_err(|_| checkpoint_error("sparse state payload exceeds u64"))?;
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
            "sparse checkpoint hash identity is invalid",
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
            "sparse checkpoint hash identity is invalid",
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

const fn execution_status_raw(value: SparseLinearExecutionStatus) -> u32 {
    match value {
        SparseLinearExecutionStatus::Active => 0,
        SparseLinearExecutionStatus::Terminal => 1,
    }
}

fn execution_status_from_raw(value: u32) -> Result<SparseLinearExecutionStatus, RuntimeError> {
    match value {
        0 => Ok(SparseLinearExecutionStatus::Active),
        1 => Ok(SparseLinearExecutionStatus::Terminal),
        _ => Err(checkpoint_error(
            "sparse checkpoint execution status is invalid",
        )),
    }
}

const fn solver_status_raw(value: SparseLinearSolverStatus) -> u32 {
    match value {
        SparseLinearSolverStatus::Converged => 0,
        SparseLinearSolverStatus::Singularity => 2,
        SparseLinearSolverStatus::IndefiniteOperator => 3,
        SparseLinearSolverStatus::Nonconvergence => 4,
        SparseLinearSolverStatus::IncrementLimit => 5,
        SparseLinearSolverStatus::ResidualLimit => 6,
    }
}

fn solver_status_from_raw(value: u32) -> Result<SparseLinearSolverStatus, RuntimeError> {
    match value {
        0 => Ok(SparseLinearSolverStatus::Converged),
        2 => Ok(SparseLinearSolverStatus::Singularity),
        3 => Ok(SparseLinearSolverStatus::IndefiniteOperator),
        4 => Ok(SparseLinearSolverStatus::Nonconvergence),
        5 => Ok(SparseLinearSolverStatus::IncrementLimit),
        6 => Ok(SparseLinearSolverStatus::ResidualLimit),
        _ => Err(checkpoint_error(
            "sparse checkpoint solver status is invalid",
        )),
    }
}

const fn execution_status_name(value: SparseLinearExecutionStatus) -> &'static str {
    match value {
        SparseLinearExecutionStatus::Active => "active",
        SparseLinearExecutionStatus::Terminal => "terminal",
    }
}

const fn solver_status_name(value: SparseLinearSolverStatus) -> &'static str {
    match value {
        SparseLinearSolverStatus::Converged => "converged",
        SparseLinearSolverStatus::Singularity => "singularity",
        SparseLinearSolverStatus::IndefiniteOperator => "indefinite_operator",
        SparseLinearSolverStatus::Nonconvergence => "nonconvergence",
        SparseLinearSolverStatus::IncrementLimit => "increment_limit",
        SparseLinearSolverStatus::ResidualLimit => "residual_limit",
    }
}

fn norm_inf(values: &[f64]) -> f64 {
    values
        .iter()
        .fold(0.0_f64, |maximum, value| maximum.max(value.abs()))
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
            .ok_or_else(|| checkpoint_error("sparse checkpoint offset overflows"))?;
        let value = self
            .bytes
            .get(self.position..end)
            .ok_or_else(|| checkpoint_error("sparse checkpoint is truncated"))?;
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
                "sparse checkpoint contains trailing bytes",
            ))
        }
    }
}
