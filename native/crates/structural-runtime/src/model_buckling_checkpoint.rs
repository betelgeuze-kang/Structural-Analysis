use std::fmt::Write as _;

use serde::Serialize;
use sha2::{Digest, Sha256};

use crate::{DenseSpectralCheckpointV1, ModelIrLinearCheckpointV1, RuntimeError};

const MAGIC: &[u8; 8] = b"SAMBKP01";
const FORMAT_VERSION: u32 = 1;
const HEADER_SIZE: usize = 448;
const MAX_ARTIFACT_BYTES: usize = 140 * 1024 * 1024;
const CHECKPOINT_MISMATCH: u32 = 1301;
const DOMAIN: &[u8] = b"structural-model-ir-linear-buckling-checkpoint.v1\0";

type DigestBytes = [u8; 32];

/// Immutable derivation bindings carried by one model-bound buckling checkpoint.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelIrLinearBucklingCheckpointBindingsV1 {
    pub model_content_hash: String,
    pub model_semantic_hash: String,
    pub model_provenance_hash: String,
    pub analysis_request_hash: String,
    pub generated_reference_request_hash: String,
    pub reference_assembly_hash: String,
    pub buckling_assembly_hash: String,
    pub generated_spectral_request_hash: String,
    pub reference_result_hash: String,
    pub reference_recovery_hash: String,
}

/// Deterministic receipt for a dual-phase model-bound buckling checkpoint.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct ModelIrLinearBucklingCheckpointReceiptV1 {
    pub schema_version: &'static str,
    pub model_content_hash: String,
    pub model_semantic_hash: String,
    pub model_provenance_hash: String,
    pub analysis_request_hash: String,
    pub generated_reference_request_hash: String,
    pub reference_assembly_hash: String,
    pub buckling_assembly_hash: String,
    pub generated_spectral_request_hash: String,
    pub reference_result_hash: String,
    pub reference_recovery_hash: String,
    pub reference_checkpoint_hash: String,
    pub spectral_checkpoint_hash: String,
    pub checkpoint_hash: String,
    pub artifact_bytes: u64,
}

/// Pointer-free aggregate checkpoint containing exact PCG and dense-spectral boundaries.
#[derive(Clone, Debug)]
pub struct ModelIrLinearBucklingCheckpointV1 {
    bindings: [DigestBytes; 10],
    reference: ModelIrLinearCheckpointV1,
    spectral: DenseSpectralCheckpointV1,
    reference_checkpoint_hash: DigestBytes,
    spectral_checkpoint_hash: DigestBytes,
    checkpoint_hash: DigestBytes,
    bytes: Vec<u8>,
}

impl ModelIrLinearBucklingCheckpointV1 {
    /// Create one aggregate checkpoint from exact inner phase boundaries and bindings.
    ///
    /// # Errors
    ///
    /// Returns a stable runtime error for malformed identities, length overflow, or allocation.
    pub fn create(
        reference: ModelIrLinearCheckpointV1,
        spectral: DenseSpectralCheckpointV1,
        bindings: &ModelIrLinearBucklingCheckpointBindingsV1,
    ) -> Result<Self, RuntimeError> {
        let parsed = parse_bindings(bindings)?;
        let reference_checkpoint_hash: DigestBytes = Sha256::digest(reference.as_bytes()).into();
        let spectral_checkpoint_hash: DigestBytes = Sha256::digest(spectral.as_bytes()).into();
        let checkpoint_hash = artifact_hash(
            &parsed,
            &reference_checkpoint_hash,
            reference.as_bytes().len(),
            &spectral_checkpoint_hash,
            spectral.as_bytes().len(),
        )?;
        let total = HEADER_SIZE
            .checked_add(reference.as_bytes().len())
            .and_then(|value| value.checked_add(spectral.as_bytes().len()))
            .filter(|value| *value <= MAX_ARTIFACT_BYTES)
            .ok_or_else(|| checkpoint_error("ModelIR buckling checkpoint length is invalid"))?;
        let mut bytes = Vec::new();
        bytes
            .try_reserve_exact(total)
            .map_err(|_| internal_error("ModelIR buckling checkpoint allocation failed"))?;
        bytes.extend_from_slice(MAGIC);
        bytes.extend_from_slice(&FORMAT_VERSION.to_le_bytes());
        bytes.extend_from_slice(
            &u32::try_from(HEADER_SIZE)
                .map_err(|_| internal_error("ModelIR buckling checkpoint header exceeds u32"))?
                .to_le_bytes(),
        );
        for digest in &parsed {
            bytes.extend_from_slice(digest);
        }
        bytes.extend_from_slice(
            &u64::try_from(reference.as_bytes().len())
                .map_err(|_| checkpoint_error("reference checkpoint length exceeds u64"))?
                .to_le_bytes(),
        );
        bytes.extend_from_slice(
            &u64::try_from(spectral.as_bytes().len())
                .map_err(|_| checkpoint_error("spectral checkpoint length exceeds u64"))?
                .to_le_bytes(),
        );
        bytes.extend_from_slice(&reference_checkpoint_hash);
        bytes.extend_from_slice(&spectral_checkpoint_hash);
        bytes.extend_from_slice(&checkpoint_hash);
        if bytes.len() != HEADER_SIZE {
            return Err(internal_error(
                "ModelIR buckling checkpoint header size drifted",
            ));
        }
        bytes.extend_from_slice(reference.as_bytes());
        bytes.extend_from_slice(spectral.as_bytes());
        Ok(Self {
            bindings: parsed,
            reference,
            spectral,
            reference_checkpoint_hash,
            spectral_checkpoint_hash,
            checkpoint_hash,
            bytes,
        })
    }

    /// Strictly restore one aggregate checkpoint and both inner checkpoints.
    ///
    /// # Errors
    ///
    /// Rejects truncation, trailing bytes, header/version drift, hash mismatch, oversized payload,
    /// or either malformed inner checkpoint before returning a value.
    pub fn from_bytes(bytes: &[u8]) -> Result<Self, RuntimeError> {
        if bytes.len() < HEADER_SIZE || bytes.len() > MAX_ARTIFACT_BYTES {
            return Err(checkpoint_error(
                "ModelIR buckling checkpoint size is invalid",
            ));
        }
        let mut reader = Reader::new(bytes);
        if reader.take(8)? != MAGIC
            || reader.u32()? != FORMAT_VERSION
            || usize::try_from(reader.u32()?).ok() != Some(HEADER_SIZE)
        {
            return Err(checkpoint_error(
                "ModelIR buckling checkpoint header is unsupported",
            ));
        }
        let mut bindings = [[0_u8; 32]; 10];
        for binding in &mut bindings {
            *binding = reader.digest()?;
        }
        let reference_length = reader.length()?;
        let spectral_length = reader.length()?;
        let reference_checkpoint_hash = reader.digest()?;
        let spectral_checkpoint_hash = reader.digest()?;
        let checkpoint_hash = reader.digest()?;
        if reader.position != HEADER_SIZE
            || reference_length == 0
            || spectral_length == 0
            || HEADER_SIZE
                .checked_add(reference_length)
                .and_then(|value| value.checked_add(spectral_length))
                != Some(bytes.len())
        {
            return Err(checkpoint_error(
                "ModelIR buckling checkpoint payload shape is invalid",
            ));
        }
        let reference_bytes = reader.take(reference_length)?;
        let spectral_bytes = reader.take(spectral_length)?;
        let actual_reference_hash: DigestBytes = Sha256::digest(reference_bytes).into();
        let actual_spectral_hash: DigestBytes = Sha256::digest(spectral_bytes).into();
        if reader.remaining() != 0
            || actual_reference_hash != reference_checkpoint_hash
            || actual_spectral_hash != spectral_checkpoint_hash
            || artifact_hash(
                &bindings,
                &reference_checkpoint_hash,
                reference_length,
                &spectral_checkpoint_hash,
                spectral_length,
            )? != checkpoint_hash
        {
            return Err(checkpoint_error(
                "ModelIR buckling checkpoint integrity check failed",
            ));
        }
        let reference = ModelIrLinearCheckpointV1::from_bytes(reference_bytes)?;
        let spectral = DenseSpectralCheckpointV1::from_bytes(spectral_bytes)?;
        Ok(Self {
            bindings,
            reference,
            spectral,
            reference_checkpoint_hash,
            spectral_checkpoint_hash,
            checkpoint_hash,
            bytes: bytes.to_vec(),
        })
    }

    /// Require all immutable outer and generated identities to match before either resume.
    ///
    /// # Errors
    ///
    /// Returns checkpoint-mismatch semantics when any binding differs.
    pub fn verify_bindings(
        &self,
        bindings: &ModelIrLinearBucklingCheckpointBindingsV1,
    ) -> Result<(), RuntimeError> {
        if self.bindings == parse_bindings(bindings)? {
            Ok(())
        } else {
            Err(checkpoint_error(
                "ModelIR buckling checkpoint binding does not match model or derivation",
            ))
        }
    }

    #[must_use]
    pub fn as_bytes(&self) -> &[u8] {
        &self.bytes
    }

    #[must_use]
    pub const fn reference(&self) -> &ModelIrLinearCheckpointV1 {
        &self.reference
    }

    #[must_use]
    pub const fn spectral(&self) -> &DenseSpectralCheckpointV1 {
        &self.spectral
    }

    #[must_use]
    pub fn receipt(&self) -> ModelIrLinearBucklingCheckpointReceiptV1 {
        ModelIrLinearBucklingCheckpointReceiptV1 {
            schema_version: "structural-model-ir-linear-buckling-checkpoint-receipt.v1",
            model_content_hash: format_digest(&self.bindings[0]),
            model_semantic_hash: format_digest(&self.bindings[1]),
            model_provenance_hash: format_digest(&self.bindings[2]),
            analysis_request_hash: format_digest(&self.bindings[3]),
            generated_reference_request_hash: format_digest(&self.bindings[4]),
            reference_assembly_hash: format_digest(&self.bindings[5]),
            buckling_assembly_hash: format_digest(&self.bindings[6]),
            generated_spectral_request_hash: format_digest(&self.bindings[7]),
            reference_result_hash: format_digest(&self.bindings[8]),
            reference_recovery_hash: format_digest(&self.bindings[9]),
            reference_checkpoint_hash: format_digest(&self.reference_checkpoint_hash),
            spectral_checkpoint_hash: format_digest(&self.spectral_checkpoint_hash),
            checkpoint_hash: format_digest(&self.checkpoint_hash),
            artifact_bytes: u64::try_from(self.bytes.len()).unwrap_or(u64::MAX),
        }
    }
}

fn parse_bindings(
    bindings: &ModelIrLinearBucklingCheckpointBindingsV1,
) -> Result<[DigestBytes; 10], RuntimeError> {
    Ok([
        parse_digest(&bindings.model_content_hash)?,
        parse_digest(&bindings.model_semantic_hash)?,
        parse_digest(&bindings.model_provenance_hash)?,
        parse_digest(&bindings.analysis_request_hash)?,
        parse_digest(&bindings.generated_reference_request_hash)?,
        parse_digest(&bindings.reference_assembly_hash)?,
        parse_digest(&bindings.buckling_assembly_hash)?,
        parse_digest(&bindings.generated_spectral_request_hash)?,
        parse_digest(&bindings.reference_result_hash)?,
        parse_digest(&bindings.reference_recovery_hash)?,
    ])
}

fn artifact_hash(
    bindings: &[DigestBytes; 10],
    reference_hash: &DigestBytes,
    reference_length: usize,
    spectral_hash: &DigestBytes,
    spectral_length: usize,
) -> Result<DigestBytes, RuntimeError> {
    let mut hasher = Sha256::new();
    hasher.update(DOMAIN);
    for digest in bindings {
        hasher.update(digest);
    }
    hasher.update(reference_hash);
    hasher.update(
        u64::try_from(reference_length)
            .map_err(|_| checkpoint_error("reference checkpoint length exceeds u64"))?
            .to_le_bytes(),
    );
    hasher.update(spectral_hash);
    hasher.update(
        u64::try_from(spectral_length)
            .map_err(|_| checkpoint_error("spectral checkpoint length exceeds u64"))?
            .to_le_bytes(),
    );
    Ok(hasher.finalize().into())
}

fn parse_digest(value: &str) -> Result<DigestBytes, RuntimeError> {
    let hex = value
        .strip_prefix("sha256:")
        .filter(|hex| hex.len() == 64)
        .ok_or_else(|| checkpoint_error("ModelIR buckling checkpoint identity is invalid"))?;
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
            "ModelIR buckling checkpoint identity is invalid",
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

    fn remaining(&self) -> usize {
        self.bytes.len().saturating_sub(self.position)
    }

    fn take(&mut self, count: usize) -> Result<&'a [u8], RuntimeError> {
        let end = self
            .position
            .checked_add(count)
            .ok_or_else(|| checkpoint_error("ModelIR buckling checkpoint offset overflows"))?;
        let value = self
            .bytes
            .get(self.position..end)
            .ok_or_else(|| checkpoint_error("ModelIR buckling checkpoint is truncated"))?;
        self.position = end;
        Ok(value)
    }

    fn u32(&mut self) -> Result<u32, RuntimeError> {
        let mut bytes = [0_u8; 4];
        bytes.copy_from_slice(self.take(4)?);
        Ok(u32::from_le_bytes(bytes))
    }

    fn length(&mut self) -> Result<usize, RuntimeError> {
        let mut bytes = [0_u8; 8];
        bytes.copy_from_slice(self.take(8)?);
        usize::try_from(u64::from_le_bytes(bytes)).map_err(|_| {
            checkpoint_error("ModelIR buckling checkpoint length exceeds address space")
        })
    }

    fn digest(&mut self) -> Result<DigestBytes, RuntimeError> {
        let mut digest = [0_u8; 32];
        digest.copy_from_slice(self.take(32)?);
        Ok(digest)
    }
}
