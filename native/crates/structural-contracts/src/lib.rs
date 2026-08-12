//! Wire-contract ownership for the native product.
//!
//! Slice A intentionally contains no solver or `ModelIR` semantic implementation.

#![forbid(unsafe_code)]

/// ABI family consumed by the wire-contract crates.
pub const ABI_V1_0: u32 = 0x0001_0000;

/// Schema family that the next `ModelIR` slice will implement.
pub const MODEL_IR_SCHEMA_V2: &str = "model-ir.v2";

#[cfg(test)]
mod tests {
    use super::{ABI_V1_0, MODEL_IR_SCHEMA_V2};

    #[test]
    fn foundation_constants_do_not_claim_model_implementation() {
        assert_eq!(ABI_V1_0, 0x0001_0000);
        assert_eq!(MODEL_IR_SCHEMA_V2, "model-ir.v2");
    }
}
