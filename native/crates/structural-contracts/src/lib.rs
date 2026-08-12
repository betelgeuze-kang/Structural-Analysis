//! Wire-contract ownership for the native product.
//!
//! This crate owns strict `ModelIR` decoding/canonical identity and strict,
//! pointer-free bounded CPU product goldens. Numerical execution remains in
//! C++; a golden wire records a verified parity slice without promoting broader
//! solver readiness.

#![forbid(unsafe_code)]

pub mod legacy_runtime;
pub mod model_ir;
pub mod product_ir;
pub mod solver_cpu;

/// ABI family consumed by the wire-contract crates.
pub const ABI_V1_0: u32 = 0x0001_0000;

/// `ModelIR` schema family accepted by the Slice B wire contract.
pub const MODEL_IR_SCHEMA_V2: &str = "structural-analysis-model-ir.v2";

#[cfg(test)]
mod tests {
    use super::{ABI_V1_0, MODEL_IR_SCHEMA_V2};

    #[test]
    fn foundation_constants_name_the_implemented_wire_contract() {
        assert_eq!(ABI_V1_0, 0x0001_0000);
        assert_eq!(MODEL_IR_SCHEMA_V2, "structural-analysis-model-ir.v2");
    }
}
