use std::fmt::Write as _;

use serde::Serialize;
use sha2::{Digest, Sha256};

use crate::{RuntimeError, SparseLinearCheckpointV1};

const MAGIC: &[u8; 8] = b"SAMLPC01";
const FORMAT_VERSION: u32 = 1;
const HEADER_SIZE: usize = 280;
const MAX_ARTIFACT_BYTES: usize = 128 * 1024 * 1024;
const CHECKPOINT_MISMATCH: u32 = 1301;
const DOMAIN: &[u8] = b"structural-model-ir-linear-checkpoint.v1\0";

type DigestBytes = [u8; 32];

/// Exact immutable and generated identities required to reuse a `ModelIR` linear checkpoint.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelIrLinearCheckpointBindingsV1 {
    pub model_content_hash: String,
    pub model_semantic_hash: String,
    pub model_provenance_hash: String,
    pub analysis_request_hash: String,
    pub assembly_hash: String,
    pub generated_request_hash: String,
}

/// Auditable identity receipt for one `ModelIR`-bound PCG iteration boundary.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct ModelIrLinearCheckpointReceiptV1 {
    pub schema_version: &'static str,
    pub model_content_hash: String,
    pub model_semantic_hash: String,
    pub model_provenance_hash: String,
    pub analysis_request_hash: String,
    pub assembly_hash: String,
    pub generated_request_hash: String,
    pub inner_checkpoint_hash: String,
    pub checkpoint_hash: String,
    pub artifact_bytes: u64,
}

/// Pointer-free envelope binding complete PCG state to exact typed-`ModelIR` assembly provenance.
#[derive(Clone, Debug, PartialEq)]
pub struct ModelIrLinearCheckpointV1 {
    bytes: Vec<u8>,
    inner: SparseLinearCheckpointV1,
    model_content_hash: DigestBytes,
    model_semantic_hash: DigestBytes,
    model_provenance_hash: DigestBytes,
    analysis_request_hash: DigestBytes,
    assembly_hash: DigestBytes,
    generated_request_hash: DigestBytes,
    inner_checkpoint_hash: DigestBytes,
    checkpoint_hash: DigestBytes,
}

impl ModelIrLinearCheckpointV1 {
    /// Wrap one validated sparse checkpoint with all `ModelIR` and derivation identities.
    ///
    /// # Errors
    ///
    /// Returns checkpoint-mismatch semantics for malformed identities or an oversized artifact.
    pub fn create(
        inner: SparseLinearCheckpointV1,
        bindings: &ModelIrLinearCheckpointBindingsV1,
    ) -> Result<Self, RuntimeError> {
        let model_content_hash = parse_digest(&bindings.model_content_hash)?;
        let model_semantic_hash = parse_digest(&bindings.model_semantic_hash)?;
        let model_provenance_hash = parse_digest(&bindings.model_provenance_hash)?;
        let analysis_request_hash = parse_digest(&bindings.analysis_request_hash)?;
        let assembly_hash = parse_digest(&bindings.assembly_hash)?;
        let generated_request_hash = parse_digest(&bindings.generated_request_hash)?;
        let inner_checkpoint_hash = parse_digest(&inner.receipt().checkpoint_hash)?;
        let inner_length = inner.as_bytes().len();
        let checkpoint_hash = artifact_hash(
            &model_content_hash,
            &model_semantic_hash,
            &model_provenance_hash,
            &analysis_request_hash,
            &assembly_hash,
            &generated_request_hash,
            &inner_checkpoint_hash,
            inner_length,
        )?;
        let total = HEADER_SIZE
            .checked_add(inner_length)
            .ok_or_else(|| checkpoint_error("ModelIR linear checkpoint length overflows"))?;
        if total > MAX_ARTIFACT_BYTES {
            return Err(checkpoint_error(
                "ModelIR linear checkpoint exceeds the bounded size",
            ));
        }
        let mut bytes = Vec::new();
        bytes
            .try_reserve_exact(total)
            .map_err(|_| internal_error("ModelIR linear checkpoint allocation failed"))?;
        bytes.extend_from_slice(MAGIC);
        bytes.extend_from_slice(&FORMAT_VERSION.to_le_bytes());
        bytes.extend_from_slice(
            &u32::try_from(HEADER_SIZE)
                .map_err(|_| internal_error("ModelIR linear header conversion failed"))?
                .to_le_bytes(),
        );
        bytes.extend_from_slice(
            &u64::try_from(inner_length)
                .map_err(|_| checkpoint_error("inner checkpoint length exceeds u64"))?
                .to_le_bytes(),
        );
        bytes.extend_from_slice(&model_content_hash);
        bytes.extend_from_slice(&model_semantic_hash);
        bytes.extend_from_slice(&model_provenance_hash);
        bytes.extend_from_slice(&analysis_request_hash);
        bytes.extend_from_slice(&assembly_hash);
        bytes.extend_from_slice(&generated_request_hash);
        bytes.extend_from_slice(&inner_checkpoint_hash);
        bytes.extend_from_slice(&checkpoint_hash);
        bytes.extend_from_slice(inner.as_bytes());
        if bytes.len() != total {
            return Err(internal_error(
                "ModelIR linear checkpoint length invariant failed",
            ));
        }
        Ok(Self {
            bytes,
            inner,
            model_content_hash,
            model_semantic_hash,
            model_provenance_hash,
            analysis_request_hash,
            assembly_hash,
            generated_request_hash,
            inner_checkpoint_hash,
            checkpoint_hash,
        })
    }

    /// Decode and verify the complete envelope and embedded sparse checkpoint.
    ///
    /// # Errors
    ///
    /// Returns checkpoint-mismatch semantics for corruption, truncation, trailing bytes, invalid
    /// hashes, or a malformed embedded PCG boundary.
    pub fn from_bytes(bytes: &[u8]) -> Result<Self, RuntimeError> {
        if bytes.len() < HEADER_SIZE || bytes.len() > MAX_ARTIFACT_BYTES {
            return Err(checkpoint_error(
                "ModelIR linear checkpoint size is outside the bounded range",
            ));
        }
        let mut reader = Reader::new(bytes);
        if reader.take(MAGIC.len())? != MAGIC {
            return Err(checkpoint_error(
                "ModelIR linear checkpoint magic does not match",
            ));
        }
        if reader.u32()? != FORMAT_VERSION {
            return Err(checkpoint_error(
                "ModelIR linear checkpoint format version is unsupported",
            ));
        }
        if usize::try_from(reader.u32()?).ok() != Some(HEADER_SIZE) {
            return Err(checkpoint_error(
                "ModelIR linear checkpoint header size does not match",
            ));
        }
        let inner_length = reader.length()?;
        let model_content_hash = reader.digest()?;
        let model_semantic_hash = reader.digest()?;
        let model_provenance_hash = reader.digest()?;
        let analysis_request_hash = reader.digest()?;
        let assembly_hash = reader.digest()?;
        let generated_request_hash = reader.digest()?;
        let inner_checkpoint_hash = reader.digest()?;
        let checkpoint_hash = reader.digest()?;
        if reader.position != HEADER_SIZE || reader.remaining() != inner_length {
            return Err(checkpoint_error(
                "ModelIR linear checkpoint inner length does not match artifact",
            ));
        }
        let inner = SparseLinearCheckpointV1::from_bytes(reader.take(inner_length)?)?;
        if parse_digest(&inner.receipt().checkpoint_hash)? != inner_checkpoint_hash {
            return Err(checkpoint_error(
                "ModelIR linear embedded identity does not match inner checkpoint",
            ));
        }
        let expected = artifact_hash(
            &model_content_hash,
            &model_semantic_hash,
            &model_provenance_hash,
            &analysis_request_hash,
            &assembly_hash,
            &generated_request_hash,
            &inner_checkpoint_hash,
            inner_length,
        )?;
        if expected != checkpoint_hash {
            return Err(checkpoint_error(
                "ModelIR linear checkpoint aggregate hash does not match",
            ));
        }
        let mut owned_bytes = Vec::new();
        owned_bytes
            .try_reserve_exact(bytes.len())
            .map_err(|_| internal_error("ModelIR linear checkpoint allocation failed"))?;
        owned_bytes.extend_from_slice(bytes);
        Ok(Self {
            bytes: owned_bytes,
            inner,
            model_content_hash,
            model_semantic_hash,
            model_provenance_hash,
            analysis_request_hash,
            assembly_hash,
            generated_request_hash,
            inner_checkpoint_hash,
            checkpoint_hash,
        })
    }

    /// Require every immutable and generated binding to match before native resume.
    ///
    /// # Errors
    ///
    /// Returns checkpoint-mismatch semantics when any supplied identity differs.
    pub fn verify_bindings(
        &self,
        bindings: &ModelIrLinearCheckpointBindingsV1,
    ) -> Result<(), RuntimeError> {
        let matches = self.model_content_hash == parse_digest(&bindings.model_content_hash)?
            && self.model_semantic_hash == parse_digest(&bindings.model_semantic_hash)?
            && self.model_provenance_hash == parse_digest(&bindings.model_provenance_hash)?
            && self.analysis_request_hash == parse_digest(&bindings.analysis_request_hash)?
            && self.assembly_hash == parse_digest(&bindings.assembly_hash)?
            && self.generated_request_hash == parse_digest(&bindings.generated_request_hash)?;
        if matches {
            Ok(())
        } else {
            Err(checkpoint_error(
                "ModelIR linear checkpoint binding does not match model or derivation",
            ))
        }
    }

    #[must_use]
    pub fn as_bytes(&self) -> &[u8] {
        &self.bytes
    }

    #[must_use]
    pub const fn inner(&self) -> &SparseLinearCheckpointV1 {
        &self.inner
    }

    #[must_use]
    pub fn receipt(&self) -> ModelIrLinearCheckpointReceiptV1 {
        ModelIrLinearCheckpointReceiptV1 {
            schema_version: "structural-model-ir-linear-checkpoint-receipt.v1",
            model_content_hash: format_digest(&self.model_content_hash),
            model_semantic_hash: format_digest(&self.model_semantic_hash),
            model_provenance_hash: format_digest(&self.model_provenance_hash),
            analysis_request_hash: format_digest(&self.analysis_request_hash),
            assembly_hash: format_digest(&self.assembly_hash),
            generated_request_hash: format_digest(&self.generated_request_hash),
            inner_checkpoint_hash: format_digest(&self.inner_checkpoint_hash),
            checkpoint_hash: format_digest(&self.checkpoint_hash),
            artifact_bytes: u64::try_from(self.bytes.len()).unwrap_or(u64::MAX),
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn artifact_hash(
    model_content_hash: &DigestBytes,
    model_semantic_hash: &DigestBytes,
    model_provenance_hash: &DigestBytes,
    analysis_request_hash: &DigestBytes,
    assembly_hash: &DigestBytes,
    generated_request_hash: &DigestBytes,
    inner_checkpoint_hash: &DigestBytes,
    inner_length: usize,
) -> Result<DigestBytes, RuntimeError> {
    let mut hasher = Sha256::new();
    hasher.update(DOMAIN);
    hasher.update(model_content_hash);
    hasher.update(model_semantic_hash);
    hasher.update(model_provenance_hash);
    hasher.update(analysis_request_hash);
    hasher.update(assembly_hash);
    hasher.update(generated_request_hash);
    hasher.update(inner_checkpoint_hash);
    hasher.update(
        u64::try_from(inner_length)
            .map_err(|_| checkpoint_error("inner checkpoint length exceeds u64"))?
            .to_le_bytes(),
    );
    Ok(hasher.finalize().into())
}

fn parse_digest(value: &str) -> Result<DigestBytes, RuntimeError> {
    let hex = value
        .strip_prefix("sha256:")
        .filter(|hex| hex.len() == 64)
        .ok_or_else(|| checkpoint_error("ModelIR linear checkpoint identity is invalid"))?;
    let mut digest = [0_u8; 32];
    for (index, pair) in hex.as_bytes().chunks_exact(2).enumerate() {
        digest[index] = (hex_nibble(pair[0])? << 4) | hex_nibble(pair[1])?;
    }
    Ok(digest)
}

fn hex_nibble(value: u8) -> Result<u8, RuntimeError> {
    match value {
        b'0'..=b'9' => Ok(value - b'0'),
        b'a'..=b'f' => Ok(value - b'a' + 10),
        _ => Err(checkpoint_error(
            "ModelIR linear checkpoint identity is invalid",
        )),
    }
}

fn format_digest(digest: &DigestBytes) -> String {
    let mut output = String::with_capacity(71);
    output.push_str("sha256:");
    for byte in digest {
        write!(&mut output, "{byte:02x}").expect("writing to String cannot fail");
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

    fn take(&mut self, length: usize) -> Result<&'a [u8], RuntimeError> {
        let end = self
            .position
            .checked_add(length)
            .filter(|end| *end <= self.bytes.len())
            .ok_or_else(|| checkpoint_error("ModelIR linear checkpoint is truncated"))?;
        let value = &self.bytes[self.position..end];
        self.position = end;
        Ok(value)
    }

    fn u32(&mut self) -> Result<u32, RuntimeError> {
        let bytes: [u8; 4] = self
            .take(4)?
            .try_into()
            .map_err(|_| checkpoint_error("ModelIR linear checkpoint u32 is truncated"))?;
        Ok(u32::from_le_bytes(bytes))
    }

    fn length(&mut self) -> Result<usize, RuntimeError> {
        let bytes: [u8; 8] = self
            .take(8)?
            .try_into()
            .map_err(|_| checkpoint_error("ModelIR linear checkpoint length is truncated"))?;
        usize::try_from(u64::from_le_bytes(bytes))
            .map_err(|_| checkpoint_error("ModelIR linear checkpoint length exceeds address space"))
    }

    fn digest(&mut self) -> Result<DigestBytes, RuntimeError> {
        self.take(32)?
            .try_into()
            .map_err(|_| checkpoint_error("ModelIR linear checkpoint digest is truncated"))
    }

    fn remaining(&self) -> usize {
        self.bytes.len().saturating_sub(self.position)
    }
}
