use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

use serde_json::{json, Value};
use structural_contracts::model_ir::{
    canonicalize_model_ir_v2, parse_model_ir_v2, provenance_projection, semantic_projection,
    validate_model_ir_v2_wire,
};

const GOLDEN_FIXTURES: [(&str, usize, &str, &str, &str); 8] = [
    (
        "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json",
        3548,
        "sha256:43dfd7770d69075bc8f10ee6a7f903d6d66e39cf5d845eea78b976d04adb1610",
        "sha256:5a19491d252b3936135cc1da91338f23e6ca1db59e42b0cf2b4cbd0346e25cb2",
        "sha256:7af33051b9c4d241a5c8779006580e2de6b1727166f68a67385fff6412921c5c",
    ),
    (
        "examples/bounded_planar_frame_alpha.model-ir.v2.json",
        3449,
        "sha256:4703d9137223345322db05cc37e8e53eb453d9bc67f12e88864c390ba3de66b7",
        "sha256:fa0bfb2cf75d58ce406fe116dc4d463eac3568f3a8c32009afb51f5650daf08d",
        "sha256:04a669a3a6deb764e9ea63d0215a563753a5bd74d0a68631001176821003938e",
    ),
    (
        "examples/bounded_planar_settlement.model-ir.v2.json",
        3614,
        "sha256:a3745cf7a6e2023465bbcd232a620fa96e3bdf2a31976bb082a38f1e64176e06",
        "sha256:5547a8be9e4fbf5ea2176e41adc9db3ec12931d3e327c1516c8b0cf11ab03b48",
        "sha256:963127da36dd4de2004596ec523dec07099ad8bb652ead4686dd6a7f830fbc1c",
    ),
    (
        "examples/bounded_frame3d_direct_control.model-ir.v2.json",
        2859,
        "sha256:d81117630c67e09c4ad84d7593a8b00812ebb79e3745426e4a68eafcf65977e1",
        "sha256:63ec041ec9d64e0e7b5c1a15f08eb12f04de438c6ee7be251b012b10d4a215b7",
        "sha256:5ef30577480ea4a9f34d500214114382bcd81d37196606568a31d777c20885ae",
    ),
    (
        "examples/bounded_frame3d_direct_control_axial_yield.model-ir.v2.json",
        2862,
        "sha256:43da4a835ef8c3a966ad72526847ca10c3ff9223fbf28c3e55e7073e9d4648b6",
        "sha256:4bf418bc2d6256938b96e111e3de571a6ba728b9d17c881cbf1f2c89347147ec",
        "sha256:7f4be14b782cf3887d4a0eafa3399ae12057fd7adc15465e828452bc583a5cb6",
    ),
    (
        "examples/bounded_frame3d_direct_control_ry_bending.model-ir.v2.json",
        2860,
        "sha256:0e333921b0ecdbb68d57c0940f9f561eefee1c893ba95d16d31727c4cba9267e",
        "sha256:741d97ce371d18943030a09050cdec84cda18dd2cf256e6177e36843461c704f",
        "sha256:304f1eb14ee4b419ab79566b667ff9186638888a73ad0b1d5a84de21e01d85f7",
    ),
    (
        "examples/bounded_frame3d_direct_control_rz_bending.model-ir.v2.json",
        2860,
        "sha256:9b0a47f224ff454c502b36f29e449eacb97494b4b3582e6be397ef571d618ed3",
        "sha256:d5fd642406f6599ca6aa9e2bda25293d70846055cd560e26e5cf1b64f1dd1c64",
        "sha256:260247e6f7783097d6f62bedc9ae7c6bf365d93a077adf555c1380986764ab2d",
    ),
    (
        "examples/bounded_frame3d_direct_control_torsion.model-ir.v2.json",
        2854,
        "sha256:24bc0eca2c1480972f531ba0d70c5082584e75ee7973041b5e237dbe70252c92",
        "sha256:a7fb2742606cb12fb5bd4a54f9c52cc5179a8fdf5427bb67a64968091e4fc55e",
        "sha256:40092631a33818541ef39075d22174a7894630658186cffb0f99a6dfaafbd49e",
    ),
];

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

fn fixture_value() -> Value {
    let path = repository_root().join(GOLDEN_FIXTURES[0].0);
    serde_json::from_slice(&std::fs::read(path).expect("fixture bytes")).expect("fixture JSON")
}

#[test]
fn packaged_native_schema_is_byte_identical_to_the_python_oracle_schema() {
    let root = repository_root();
    let oracle =
        std::fs::read(root.join("src/structural_analysis/schemas/model_ir_v2.schema.json"))
            .expect("Python oracle schema");
    let native = std::fs::read(
        Path::new(env!("CARGO_MANIFEST_DIR")).join("schemas/model_ir_v2.schema.json"),
    )
    .expect("packaged native schema");

    assert_eq!(
        native, oracle,
        "schema copies require an explicit migration"
    );
}

#[test]
fn exact_integer_guard_covers_every_integer_property_in_the_schema() {
    fn collect(value: &Value, names: &mut BTreeSet<String>) {
        match value {
            Value::Object(object) => {
                if let Some(properties) = object.get("properties").and_then(Value::as_object) {
                    for (name, property) in properties {
                        let has_integer_type = property.get("type").is_some_and(|kind| {
                            kind == "integer"
                                || kind
                                    .as_array()
                                    .is_some_and(|kinds| kinds.iter().any(|item| item == "integer"))
                        });
                        let is_index_reference = property.get("$ref").and_then(Value::as_str)
                            == Some("#/$defs/nonNegativeIndex");
                        if has_integer_type || is_index_reference {
                            names.insert(name.clone());
                        }
                    }
                }
                for item in object.values() {
                    collect(item, names);
                }
            }
            Value::Array(items) => {
                for item in items {
                    collect(item, names);
                }
            }
            _ => {}
        }
    }

    let schema: Value = serde_json::from_slice(
        &std::fs::read(
            Path::new(env!("CARGO_MANIFEST_DIR")).join("schemas/model_ir_v2.schema.json"),
        )
        .expect("packaged schema"),
    )
    .expect("schema JSON");
    let mut integer_properties = BTreeSet::new();
    collect(&schema, &mut integer_properties);

    assert_eq!(
        integer_properties,
        [
            "bottom_bar_count",
            "concrete_layer_count",
            "index",
            "integration_order",
            "top_bar_count",
        ]
        .into_iter()
        .map(str::to_owned)
        .collect()
    );
}

fn parse_value(value: &Value) -> structural_contracts::model_ir::ModelIrV2Document {
    parse_model_ir_v2(&serde_json::to_vec(value).expect("JSON bytes"))
        .expect("valid ModelIR wire document")
}

#[test]
fn python_oracle_golden_bytes_and_three_hashes_are_native_constants() {
    let root = repository_root();
    for (relative, canonical_length, content, semantic, provenance) in GOLDEN_FIXTURES {
        let bytes = std::fs::read(root.join(relative)).expect("tracked fixture");
        let document = parse_model_ir_v2(&bytes).expect("schema-valid fixture");
        assert_eq!(
            document.canonical_bytes().len(),
            canonical_length,
            "{relative}"
        );
        assert_eq!(document.content_hash(), content, "{relative}");
        assert_eq!(document.semantic_hash(), semantic, "{relative}");
        assert_eq!(document.provenance_hash(), provenance, "{relative}");
        assert_eq!(
            canonicalize_model_ir_v2(document.value()).expect("repeat canonicalization"),
            document.canonical_json(),
            "{relative}"
        );
    }
}

#[test]
fn semantic_and_provenance_hashes_are_separate_axes() {
    let baseline_value = fixture_value();
    let baseline = parse_value(&baseline_value);

    let mut provenance_changed = baseline_value.clone();
    provenance_changed["provenance"]["source_ref"] = json!("another/source/model.mgt");
    provenance_changed["provenance"]["source_sha256"] = json!(format!("sha256:{}", "a".repeat(64)));
    provenance_changed["nodes"][0]["source_id"] = json!("source:N1001");
    let provenance_document = parse_value(&provenance_changed);

    let mut physical_changed = baseline_value;
    physical_changed["nodes"][1]["coordinates_m"][0] = json!(3.25);
    let physical_document = parse_value(&physical_changed);

    assert_eq!(
        baseline.semantic_hash(),
        provenance_document.semantic_hash()
    );
    assert_ne!(
        baseline.provenance_hash(),
        provenance_document.provenance_hash()
    );
    assert_ne!(baseline.content_hash(), provenance_document.content_hash());
    assert_ne!(baseline.semantic_hash(), physical_document.semantic_hash());
    assert_eq!(
        baseline.provenance_hash(),
        physical_document.provenance_hash()
    );
}

#[test]
fn projections_match_the_document_hash_inputs_without_semantic_validation() {
    let value = fixture_value();
    let semantic = semantic_projection(&value).expect("semantic projection");
    let provenance = provenance_projection(&value).expect("provenance projection");

    assert!(semantic.get("model_id").is_none());
    assert!(semantic["nodes"][0].get("source_id").is_none());
    assert!(semantic["nodes"][0].get("extensions").is_none());
    assert_eq!(
        provenance["entity_source_metadata"]["nodes"][0]["id"],
        value["nodes"][0]["id"]
    );
    assert!(provenance.get("units").is_none());
}

#[test]
fn strict_decode_and_schema_negative_matrix_fails_before_cpp() {
    for (bytes, expected_code) in [
        (&b"{\"id\":1,\"id\":2}"[..], "model_ir_duplicate_json_key"),
        (&b"{\"value\":NaN}"[..], "model_ir_invalid_json"),
        (&b"{\"value\":Infinity}"[..], "model_ir_invalid_json"),
        (&b"{\"value\":-Infinity}"[..], "model_ir_invalid_json"),
        (&b"{} trailing"[..], "model_ir_invalid_json"),
        (&[0xff, 0xfe][..], "model_ir_invalid_utf8"),
    ] {
        let error = parse_model_ir_v2(bytes).expect_err("invalid input must fail");
        assert_eq!(error.code, expected_code);
        assert!(error.issues.is_empty());
    }

    let root_error = parse_model_ir_v2(b"[]").expect_err("root array is schema-invalid");
    assert_eq!(root_error.code, "model_ir_schema_invalid");
    assert_eq!(root_error.issues[0].path, "/");

    let mut unknown = fixture_value();
    unknown["elements"][0]["end_release_i"] = json!(["RY"]);
    let unknown_error = parse_model_ir_v2(&serde_json::to_vec(&unknown).expect("JSON"))
        .expect_err("unknown field must fail schema validation");
    assert_eq!(unknown_error.code, "model_ir_schema_invalid");
}

#[test]
fn exact_json_integer_type_rejects_float_and_boolean_substitutes() {
    let mut float_index = fixture_value();
    float_index["nodes"][0]["index"] = json!(0.0);
    let value = structural_contracts::model_ir::decode_json_strict(
        &serde_json::to_vec(&float_index).expect("JSON"),
    )
    .expect("strict JSON");
    let report = validate_model_ir_v2_wire(&value).expect("schema report");
    assert!(!report.schema_valid);
    assert!(report.issues.iter().any(|issue| {
        issue.path == "/nodes/0/index"
            && issue.detail == "value must use the exact JSON integer type"
    }));

    let mut boolean_index = fixture_value();
    boolean_index["nodes"][0]["index"] = json!(true);
    let error = parse_model_ir_v2(&serde_json::to_vec(&boolean_index).expect("JSON"))
        .expect_err("boolean is not an integer");
    assert_eq!(error.code, "model_ir_schema_invalid");
}

#[test]
fn signed_zero_and_key_order_have_one_canonical_identity() {
    let baseline_value = fixture_value();
    let baseline = parse_value(&baseline_value);
    let mut changed = baseline_value;
    changed["coordinate_system"]["origin_m"][0] = json!(-0.0);
    let changed = parse_value(&changed);

    assert_eq!(baseline.canonical_json(), changed.canonical_json());
    assert_eq!(baseline.content_hash(), changed.content_hash());
}

#[test]
fn schema_report_is_explicitly_not_a_semantic_or_solver_claim() {
    let report = validate_model_ir_v2_wire(&fixture_value()).expect("schema report");
    assert!(report.schema_valid);
    assert!(report.issues.is_empty());
    assert_eq!(
        report.claim_boundary,
        "json_schema_and_canonical_identity_not_semantic_or_solver_readiness"
    );
    let serialized = serde_json::to_string(&report).expect("serialized report");
    assert!(!serialized.contains("analysis_ready"));
    assert!(!serialized.contains("semantics_valid"));
}
