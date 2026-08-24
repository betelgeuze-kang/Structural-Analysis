//! Wire-contract ownership for the native product.
//!
//! Slice B owns strict `ModelIR` JSON decoding, schema validation, canonical
//! bytes and identity hashes. C++ remains the future owner of semantic model
//! validation, so this crate deliberately makes no solver-readiness claim.

#![forbid(unsafe_code)]

pub mod comparison_ir;
pub mod model_ir;
pub mod native_job;
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

/// Strict external linear `Frame3D` reference input schema family.
pub const FRAME3D_EXTERNAL_REFERENCE_SCHEMA_V1: &str =
    "structural-external-linear-frame3d-reference.v1";

/// Bounded native-to-external linear `Frame3D` `ComparisonIR` schema family.
pub const FRAME3D_COMPARISON_IR_SCHEMA_V1: &str =
    "structural-native-linear-frame3d-comparison-ir.v1";

/// Completed no-overwrite CLI artifact bundle consumed by Workbench v2.
pub const FRAME3D_WORKBENCH_BUNDLE_SCHEMA_V1: &str =
    "structural-native-linear-frame3d-workbench-bundle.v1";

/// Submitted bounded native linear `Frame3D` job request schema family.
pub const FRAME3D_JOB_REQUEST_SCHEMA_V1: &str = "structural-native-linear-frame3d-job-request.v1";

/// Browser-to-loopback-host submission envelope for one bounded native job.
pub const FRAME3D_JOB_SUBMISSION_SCHEMA_V1: &str =
    "structural-native-linear-frame3d-job-submission.v1";

/// Append-only bounded native linear `Frame3D` job event schema family.
pub const FRAME3D_JOB_EVENT_SCHEMA_V1: &str = "structural-native-linear-frame3d-job-event.v1";

/// Cancellation-capable append-only bounded native linear `Frame3D` job event schema family.
pub const FRAME3D_JOB_EVENT_SCHEMA_V2: &str = "structural-native-linear-frame3d-job-event.v2";

/// Materialized bounded native linear `Frame3D` job view schema family.
pub const FRAME3D_JOB_VIEW_SCHEMA_V1: &str = "structural-native-linear-frame3d-job-view.v1";

/// Cancellation-capable materialized bounded native linear `Frame3D` job view schema family.
pub const FRAME3D_JOB_VIEW_SCHEMA_V2: &str = "structural-native-linear-frame3d-job-view.v2";

#[cfg(test)]
mod tests {
    use super::{ABI_V1_0, FRAME3D_WORKBENCH_BUNDLE_SCHEMA_V1, MODEL_IR_SCHEMA_V2};
    use jsonschema::{Draft, JSONSchema};
    use serde_json::Value;

    #[test]
    fn foundation_constants_name_the_implemented_wire_contract() {
        assert_eq!(ABI_V1_0, 0x0001_0000);
        assert_eq!(MODEL_IR_SCHEMA_V2, "structural-analysis-model-ir.v2");
        assert_eq!(
            FRAME3D_WORKBENCH_BUNDLE_SCHEMA_V1,
            "structural-native-linear-frame3d-workbench-bundle.v1"
        );
        let schema: Value = serde_json::from_str(include_str!(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/schemas/linear_frame3d_workbench_bundle_v1.schema.json"
        )))
        .expect("Workbench bundle schema JSON");
        JSONSchema::options()
            .with_draft(Draft::Draft202012)
            .compile(&schema)
            .expect("Workbench bundle schema compiles");
    }
}
