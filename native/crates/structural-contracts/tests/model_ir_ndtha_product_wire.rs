use std::path::{Path, PathBuf};

use structural_contracts::product_ir::parse_model_ir_ndtha_analysis_request_v1;

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

fn fixture() -> Vec<u8> {
    std::fs::read(
        repository_root()
            .join("native/tests/fixtures/model_ir_adapter/fixed_guided_ndtha_request.json"),
    )
    .expect("adapter request fixture")
}

#[test]
fn bounded_model_ir_request_is_strict_canonical_and_hash_bound() {
    let document = parse_model_ir_ndtha_analysis_request_v1(&fixture()).expect("strict request");
    assert_eq!(
        document.request().model_identity.content_hash,
        "sha256:d0fa14472103a367cf33668f599f7ada56a5296e704d5e44ae5523484315ca2f"
    );
    assert_eq!(document.request().config.story_count, 1);
    assert_eq!(
        document.request().config.pdelta_factor.to_bits(),
        0.0_f64.to_bits()
    );
    assert_eq!(document.request().acceleration_g.len(), 5);
    assert!(document.request_hash().starts_with("sha256:"));
    assert_eq!(document.request_hash().len(), 71);
    let reparsed = parse_model_ir_ndtha_analysis_request_v1(document.canonical_bytes())
        .expect("canonical request reparses");
    assert_eq!(reparsed.request_hash(), document.request_hash());
}

#[test]
fn duplicate_unknown_hash_and_profile_domain_fail_closed() {
    let duplicate = br#"{
      "schema_version":"structural-model-ir-ndtha-analysis-request.v1",
      "schema_version":"structural-model-ir-ndtha-analysis-request.v1"
    }"#;
    assert!(parse_model_ir_ndtha_analysis_request_v1(duplicate)
        .expect_err("duplicate rejected")
        .code
        .contains("duplicate"));

    let mut value: serde_json::Value = serde_json::from_slice(&fixture()).expect("fixture JSON");
    value["unknown"] = serde_json::json!(true);
    assert!(parse_model_ir_ndtha_analysis_request_v1(
        &serde_json::to_vec(&value).expect("unknown JSON")
    )
    .is_err());
    value.as_object_mut().expect("object").remove("unknown");

    value["model_identity"]["content_hash"] = serde_json::json!("sha256:ABC");
    assert!(parse_model_ir_ndtha_analysis_request_v1(
        &serde_json::to_vec(&value).expect("bad hash JSON")
    )
    .is_err());
    value["model_identity"]["content_hash"] = serde_json::json!(
        "sha256:d0fa14472103a367cf33668f599f7ada56a5296e704d5e44ae5523484315ca2f"
    );

    value["config"]["pdelta_factor"] = serde_json::json!(1.0);
    assert!(parse_model_ir_ndtha_analysis_request_v1(
        &serde_json::to_vec(&value).expect("P-delta JSON")
    )
    .is_err());
}
