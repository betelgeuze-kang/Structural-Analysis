//! Wire-contract ownership for the native product.
//!
//! Slice B owns strict `ModelIR` JSON decoding, schema validation, canonical
//! bytes and identity hashes. C++ remains the future owner of semantic model
//! validation, so this crate deliberately makes no solver-readiness claim.

#![forbid(unsafe_code)]

pub mod model_ir;
pub mod report_ir;
pub mod result_ir;

/// ABI family consumed by the wire-contract crates.
pub const ABI_V1_0: u32 = 0x0001_0000;

/// `ModelIR` schema family accepted by the Slice B wire contract.
pub const MODEL_IR_SCHEMA_V2: &str = "structural-analysis-model-ir.v2";

/// Bounded native linear `Frame3D` `ResultIR` schema family.
pub const FRAME3D_RESULT_IR_SCHEMA_V1: &str = "structural-native-linear-frame3d-result-ir.v1";

/// Deterministic bounded native linear `Frame3D` `ReportIR` schema family.
pub const FRAME3D_REPORT_IR_SCHEMA_V1: &str = "structural-native-linear-frame3d-report-ir.v1";

#[cfg(test)]
mod tests {
    use super::{ABI_V1_0, MODEL_IR_SCHEMA_V2};

    #[test]
    fn foundation_constants_name_the_implemented_wire_contract() {
        assert_eq!(ABI_V1_0, 0x0001_0000);
        assert_eq!(MODEL_IR_SCHEMA_V2, "structural-analysis-model-ir.v2");
    }
}
