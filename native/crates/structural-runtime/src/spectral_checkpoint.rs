use sha2::{Digest, Sha256};
use structural_contracts::spectral_product::{
    dense_spectral_execution_hash_v1, dense_spectral_model_hash_v1,
    parse_dense_spectral_request_v1, DenseSpectralAnalysisRequestDocumentV1,
};

use crate::RuntimeError;

const MAGIC: &[u8; 8] = b"SAEIGC01";
const FORMAT_VERSION: u32 = 1;
const HEADER_SIZE: usize = 184;
const MAXIMUM_PAYLOAD_BYTES: usize = 4 * 1024 * 1024;
const STATE_DOMAIN: &[u8] = b"structural-dense-spectral-ready-state.v1\0";
const CHECKPOINT_DOMAIN: &[u8] = b"structural-dense-spectral-checkpoint.v1\0";
const CHECKPOINT_MISMATCH: u32 = 1301;

type DigestBytes = [u8; 32];

/// Binding receipt for the phase-boundary spectral checkpoint.
#[derive(Clone, Debug, Eq, PartialEq, serde::Serialize)]
pub struct DenseSpectralCheckpointReceiptV1 {
    pub schema_version: &'static str,
    pub phase: &'static str,
    pub request_hash: String,
    pub model_hash: String,
    pub state_hash: String,
    pub execution_hash: String,
    pub checkpoint_hash: String,
    pub artifact_bytes: u64,
}

/// Canonical checkpoint between strict request validation and atomic native eigensolve dispatch.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct DenseSpectralCheckpointV1 {
    bytes: Vec<u8>,
    request_hash: DigestBytes,
    model_hash: DigestBytes,
    state_hash: DigestBytes,
    execution_hash: DigestBytes,
    checkpoint_hash: DigestBytes,
}

impl DenseSpectralCheckpointV1 {
    pub(crate) fn create(
        request: &DenseSpectralAnalysisRequestDocumentV1,
    ) -> Result<Self, RuntimeError> {
        let payload = request.canonical_bytes();
        if payload.is_empty() || payload.len() > MAXIMUM_PAYLOAD_BYTES {
            return Err(checkpoint_error(
                "spectral checkpoint request payload is outside the bounded size",
            ));
        }
        let request_hash = parse_identity(request.request_hash())?;
        let model_hash = parse_identity(&dense_spectral_model_hash_v1(request)?)?;
        let execution_hash = parse_identity(&dense_spectral_execution_hash_v1(request)?)?;
        let state_hash = domain_hash(STATE_DOMAIN, &[&request_hash, b"ready"]);
        let checkpoint_hash = checkpoint_hash(
            &request_hash,
            &model_hash,
            &state_hash,
            &execution_hash,
            payload,
        )?;
        let total = HEADER_SIZE
            .checked_add(payload.len())
            .ok_or_else(|| checkpoint_error("spectral checkpoint artifact length overflows"))?;
        let mut bytes = Vec::new();
        bytes
            .try_reserve_exact(total)
            .map_err(|_| internal_error("spectral checkpoint allocation failed"))?;
        bytes.extend_from_slice(MAGIC);
        bytes.extend_from_slice(&FORMAT_VERSION.to_le_bytes());
        bytes.extend_from_slice(
            &u32::try_from(HEADER_SIZE)
                .map_err(|_| internal_error("spectral checkpoint header size exceeds u32"))?
                .to_le_bytes(),
        );
        bytes.extend_from_slice(
            &u64::try_from(payload.len())
                .map_err(|_| checkpoint_error("spectral checkpoint payload exceeds u64"))?
                .to_le_bytes(),
        );
        bytes.extend_from_slice(&request_hash);
        bytes.extend_from_slice(&model_hash);
        bytes.extend_from_slice(&state_hash);
        bytes.extend_from_slice(&execution_hash);
        bytes.extend_from_slice(&checkpoint_hash);
        bytes.extend_from_slice(payload);
        if bytes.len() != total {
            return Err(internal_error(
                "spectral checkpoint length invariant failed",
            ));
        }
        Ok(Self {
            bytes,
            request_hash,
            model_hash,
            state_hash,
            execution_hash,
            checkpoint_hash,
        })
    }

    /// Decode and verify all hashes plus the embedded strict canonical request.
    ///
    /// # Errors
    ///
    /// Returns checkpoint-mismatch semantics for truncation, mutation, noncanonical payload,
    /// unsupported version, or derived identity drift.
    pub fn from_bytes(bytes: &[u8]) -> Result<Self, RuntimeError> {
        if bytes.len() < HEADER_SIZE || bytes.len() > HEADER_SIZE + MAXIMUM_PAYLOAD_BYTES {
            return Err(checkpoint_error(
                "spectral checkpoint artifact size is outside the bounded range",
            ));
        }
        let mut reader = Reader::new(bytes);
        if reader.take(MAGIC.len())? != MAGIC {
            return Err(checkpoint_error("spectral checkpoint magic does not match"));
        }
        if reader.u32()? != FORMAT_VERSION {
            return Err(checkpoint_error(
                "spectral checkpoint format version is unsupported",
            ));
        }
        if usize::try_from(reader.u32()?).ok() != Some(HEADER_SIZE) {
            return Err(checkpoint_error(
                "spectral checkpoint header size does not match",
            ));
        }
        let payload_length = usize::try_from(reader.u64()?).map_err(|_| {
            checkpoint_error("spectral checkpoint payload length exceeds address space")
        })?;
        if payload_length == 0 || payload_length > MAXIMUM_PAYLOAD_BYTES {
            return Err(checkpoint_error(
                "spectral checkpoint payload length is outside the bounded range",
            ));
        }
        let request_hash = reader.digest()?;
        let model_hash = reader.digest()?;
        let state_hash = reader.digest()?;
        let execution_hash = reader.digest()?;
        let checkpoint_hash_value = reader.digest()?;
        if reader.position() != HEADER_SIZE || reader.remaining() != payload_length {
            return Err(checkpoint_error(
                "spectral checkpoint payload length does not match artifact",
            ));
        }
        let payload = reader.take(payload_length)?;
        reader.finish()?;
        let request = parse_dense_spectral_request_v1(payload).map_err(|_| {
            checkpoint_error("spectral checkpoint request payload violates its strict contract")
        })?;
        if request.canonical_bytes() != payload {
            return Err(checkpoint_error(
                "spectral checkpoint request payload is not canonical",
            ));
        }
        let derived_request_hash = parse_identity(request.request_hash()).map_err(|_| {
            checkpoint_error("spectral checkpoint request identity cannot be decoded")
        })?;
        let derived_model_hash = dense_spectral_model_hash_v1(&request)
            .map_err(|_| checkpoint_error("spectral checkpoint model identity cannot be derived"))
            .and_then(|value| parse_identity(&value))?;
        let derived_execution_hash = dense_spectral_execution_hash_v1(&request)
            .map_err(|_| {
                checkpoint_error("spectral checkpoint execution identity cannot be derived")
            })
            .and_then(|value| parse_identity(&value))?;
        if derived_request_hash != request_hash
            || derived_model_hash != model_hash
            || derived_execution_hash != execution_hash
            || domain_hash(STATE_DOMAIN, &[&request_hash, b"ready"]) != state_hash
        {
            return Err(checkpoint_error(
                "spectral checkpoint derived identity does not match payload",
            ));
        }
        let expected = checkpoint_hash(
            &request_hash,
            &model_hash,
            &state_hash,
            &execution_hash,
            payload,
        )?;
        if expected != checkpoint_hash_value {
            return Err(checkpoint_error(
                "spectral checkpoint aggregate hash does not match",
            ));
        }
        Ok(Self {
            bytes: bytes.to_vec(),
            request_hash,
            model_hash,
            state_hash,
            execution_hash,
            checkpoint_hash: checkpoint_hash_value,
        })
    }

    /// Exact pointer-free checkpoint artifact bytes.
    #[must_use]
    pub fn as_bytes(&self) -> &[u8] {
        &self.bytes
    }

    /// All request/model/state/execution/checkpoint bindings.
    #[must_use]
    pub fn receipt(&self) -> DenseSpectralCheckpointReceiptV1 {
        DenseSpectralCheckpointReceiptV1 {
            schema_version: "structural-dense-spectral-checkpoint-receipt.v1",
            phase: "validated_ready_for_atomic_native_solve",
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
        request: &DenseSpectralAnalysisRequestDocumentV1,
    ) -> Result<(), RuntimeError> {
        if self.request_hash != parse_identity(request.request_hash())?
            || self.model_hash != parse_identity(&dense_spectral_model_hash_v1(request)?)?
            || self.execution_hash != parse_identity(&dense_spectral_execution_hash_v1(request)?)?
        {
            return Err(checkpoint_error(
                "spectral checkpoint bindings do not match request",
            ));
        }
        Ok(())
    }
}

fn checkpoint_hash(
    request_hash: &DigestBytes,
    model_hash: &DigestBytes,
    state_hash: &DigestBytes,
    execution_hash: &DigestBytes,
    payload: &[u8],
) -> Result<DigestBytes, RuntimeError> {
    let payload_length = u64::try_from(payload.len())
        .map_err(|_| checkpoint_error("spectral checkpoint payload exceeds u64"))?;
    Ok(domain_hash(
        CHECKPOINT_DOMAIN,
        &[
            request_hash,
            model_hash,
            state_hash,
            execution_hash,
            &payload_length.to_le_bytes(),
            &Sha256::digest(payload),
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
            "spectral checkpoint hash identity is invalid",
        ));
    }
    let mut digest = [0_u8; 32];
    for (index, pair) in hex.as_bytes().chunks_exact(2).enumerate() {
        let high = hex_digit(pair[0])?;
        let low = hex_digit(pair[1])?;
        digest[index] = (high << 4) | low;
    }
    Ok(digest)
}

fn hex_digit(value: u8) -> Result<u8, RuntimeError> {
    match value {
        b'0'..=b'9' => Ok(value - b'0'),
        b'a'..=b'f' => Ok(value - b'a' + 10),
        _ => Err(checkpoint_error(
            "spectral checkpoint hash identity is invalid",
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
            .ok_or_else(|| checkpoint_error("spectral checkpoint offset overflows"))?;
        let value = self
            .bytes
            .get(self.position..end)
            .ok_or_else(|| checkpoint_error("spectral checkpoint is truncated"))?;
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
                "spectral checkpoint contains trailing bytes",
            ))
        }
    }
}
