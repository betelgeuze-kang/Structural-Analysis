use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};

use structural_contracts::mgt_import::{import_mgt_v1, MgtImportStatusV1, MgtRowDispositionKindV1};
use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_contracts::product_ir::sha256_identity;

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

fn fixture(relative: &str) -> Vec<u8> {
    std::fs::read(repository_root().join(relative)).expect("MGT fixture")
}

fn verify_health_self_hash(document: &structural_contracts::mgt_import::MgtImportDocumentV1) {
    let mut value: serde_json::Value =
        serde_json::from_str(document.health_json()).expect("health JSON");
    let health_hash = value["health_hash"]
        .as_str()
        .expect("health hash")
        .to_owned();
    value
        .as_object_mut()
        .expect("health object")
        .remove("health_hash");
    let unsigned = canonicalize_model_ir_v2(&value).expect("canonical health");
    assert_eq!(health_hash, sha256_identity(unsigned.as_bytes()));
}

#[test]
fn exact_numeric_mgt_is_canonical_model_ir_with_complete_dispositions() {
    let bytes = fixture("native/tests/fixtures/mgt_import/fixed_guided_frame3d_x.mgt");
    let document = import_mgt_v1(&bytes, "mgt-fixed-guided-v1").expect("bounded import");
    assert!(document.is_normalized());
    assert_eq!(document.source_bytes(), bytes);
    assert_eq!(document.health().status, MgtImportStatusV1::Normalized);
    assert_eq!(document.health().blocker_count, 0);
    assert_eq!(document.health().dropped_row_count, 0);
    assert_eq!(document.health().unsupported_row_count, 0);
    assert!(document
        .health()
        .dispositions
        .iter()
        .any(|row| row.disposition == MgtRowDispositionKindV1::PreservedOnly));
    assert!(document
        .health()
        .dispositions
        .iter()
        .all(|row| row.source_row_hash.starts_with("sha256:")));
    verify_health_self_hash(&document);

    let model = document.model().expect("normalized ModelIR");
    assert_eq!(model.model_id(), "mgt-fixed-guided-v1");
    assert_eq!(model.value()["provenance"]["source_format"], "midas_mgt");
    assert_eq!(
        model.value()["provenance"]["source_sha256"],
        document.health().source.source_hash
    );
    assert_eq!(model.value()["nodes"].as_array().expect("nodes").len(), 2);
    assert_eq!(
        model.value()["roundtrip_map"]
            .as_array()
            .expect("roundtrip rows")
            .len(),
        8
    );
    assert_eq!(model.value()["unsupported_features"], serde_json::json!([]));
}

#[test]
fn existing_foundation_fixture_preserves_loss_and_never_invents_properties() {
    let bytes = fixture("tests/fixtures/foundation_realish/foundation_small.mgt");
    let document = import_mgt_v1(&bytes, "foundation-small-health-v1").expect("health import");
    assert!(!document.is_normalized());
    assert!(document.model().is_none());
    assert_eq!(document.health().status, MgtImportStatusV1::Blocked);
    assert!(document.health().mapped_row_count >= 8);
    assert!(document.health().preserved_only_row_count >= 2);
    assert!(document.health().dropped_row_count >= 1);
    assert!(document.health().unsupported_row_count >= 1);
    assert!(document.health().blocker_count >= 1);
    assert!(document
        .health()
        .diagnostics
        .iter()
        .any(|row| { row.code == "mgt_material_properties_unsupported" }));
    assert!(document
        .health()
        .diagnostics
        .iter()
        .any(|row| { row.code == "mgt_element_family_dropped" }));
    verify_health_self_hash(&document);
}

#[test]
fn encoding_duplicate_and_dangling_fail_closed_as_import_health() {
    let invalid_encoding = import_mgt_v1(&[0xff, 0xfe, 0x00], "bad-encoding-v1")
        .expect("invalid encoding is health data");
    assert!(!invalid_encoding.is_normalized());
    assert_eq!(invalid_encoding.health().source.encoding, "unsupported");
    assert_eq!(invalid_encoding.health().source.byte_length, 3);
    assert_eq!(invalid_encoding.health().blocker_count, 1);

    let exact_bytes = fixture("native/tests/fixtures/mgt_import/fixed_guided_frame3d_x.mgt");
    let mut with_bom = vec![0xef, 0xbb, 0xbf];
    with_bom.extend_from_slice(&exact_bytes);
    let bom = import_mgt_v1(&with_bom, "utf8-bom-v1").expect("UTF-8 BOM import");
    assert!(bom.is_normalized());
    assert_eq!(bom.source_bytes(), with_bom);
    assert_eq!(bom.health().source.encoding, "utf-8-bom");
    assert_ne!(
        bom.health().source.source_hash,
        sha256_identity(&exact_bytes)
    );

    let invalid = br"*UNIT
N,M,C
*NODE
1,0,0,0
1,0,0,1
2,0,0,3
*MATERIAL
1,STEEL,2.0E11,0.3,7850
*SECTION
1,FRAME,0.1,0.01,0.01,0.01,0.08,0.08
*ELEMENT
1,BEAM,1,1,2,99,0
*CONSTRAINT
1,111111
*STLDCASE
DEAD,D
*CONLOAD
2,1,0,0,0,0,0
";
    let document = import_mgt_v1(invalid, "invalid-graph-v1").expect("blocked health");
    assert!(!document.is_normalized());
    assert!(document
        .health()
        .diagnostics
        .iter()
        .any(|row| row.code == "mgt_duplicate_node_id"));
    assert!(document
        .health()
        .diagnostics
        .iter()
        .any(|row| row.code == "mgt_element_dangling_node"));
    assert!(document.health().dispositions.iter().any(|row| {
        row.reason_code == "mgt_element_dangling_node"
            && row.disposition == MgtRowDispositionKindV1::Unsupported
            && row.target_ids.is_empty()
    }));

    let exact = String::from_utf8(fixture(
        "native/tests/fixtures/mgt_import/fixed_guided_frame3d_x.mgt",
    ))
    .expect("UTF-8 exact fixture");
    let extra_field = exact.replace(
        "1, STEEL, 2.0E+11, 0.3, 8000.0",
        "1, STEEL, 2.0E+11, 0.3, 8000.0, SILENT",
    );
    let document =
        import_mgt_v1(extra_field.as_bytes(), "extra-field-v1").expect("blocked extra field");
    assert!(!document.is_normalized());
    assert!(document
        .health()
        .diagnostics
        .iter()
        .any(|row| row.code == "mgt_material_properties_unsupported"));

    let overflow = exact
        .replace("N, M, C", "MN, MM, C")
        .replace("2.0E+11", "1.0E+308");
    let document = import_mgt_v1(overflow.as_bytes(), "overflow-v1").expect("blocked overflow");
    assert!(!document.is_normalized());
    assert!(document
        .health()
        .diagnostics
        .iter()
        .any(|row| row.code == "mgt_si_conversion_overflow"));
}

#[test]
fn source_mutation_changes_every_bound_identity() {
    let bytes = fixture("native/tests/fixtures/mgt_import/fixed_guided_frame3d_x.mgt");
    let first = import_mgt_v1(&bytes, "mgt-fixed-guided-v1").expect("first import");
    let mut changed = bytes;
    let position = changed
        .windows(b"200000.0".len())
        .position(|window| window == b"200000.0")
        .expect("load token");
    changed[position] = b'3';
    let second = import_mgt_v1(&changed, "mgt-fixed-guided-v1").expect("second import");
    assert_ne!(
        first.health().source.source_hash,
        second.health().source.source_hash
    );
    assert_ne!(first.health().health_hash, second.health().health_hash);
    assert_ne!(
        first.model().expect("first model").content_hash(),
        second.model().expect("second model").content_hash()
    );
    assert_ne!(
        first.model().expect("first model").provenance_hash(),
        second.model().expect("second model").provenance_hash()
    );
}

#[test]
fn all_tracked_mgt_fixtures_match_the_language_neutral_python_oracle() {
    let root = repository_root();
    let golden: serde_json::Value = serde_json::from_slice(
        &std::fs::read(root.join("native/tests/golden/mgt_import_health_v1.json"))
            .expect("MGT oracle golden"),
    )
    .expect("MGT oracle JSON");
    assert_eq!(
        golden["schema_version"],
        "structural-native-mgt-python-oracle.v1"
    );
    for case in golden["cases"].as_array().expect("oracle cases") {
        let source_path = case["source_path"].as_str().expect("source path");
        let model_id = case["model_id"].as_str().expect("model ID");
        let bytes = std::fs::read(root.join(source_path)).expect("tracked MGT fixture");
        let document = import_mgt_v1(&bytes, model_id).expect("native MGT import");
        assert_eq!(document.health().source.source_hash, case["source_hash"]);
        assert_eq!(document.health().source.line_count, case["line_count"]);
        let section_counts = case["section_counts"]
            .as_object()
            .expect("section counts")
            .iter()
            .map(|(name, count)| (name.clone(), count.as_u64().expect("section count integer")))
            .collect::<BTreeMap<_, _>>();
        assert_eq!(document.health().section_counts, section_counts);
        let expected = &case["native_expected"];
        assert_eq!(
            serde_json::to_value(document.health().status).expect("status JSON"),
            expected["status"]
        );
        assert_eq!(
            document.health().mapped_row_count,
            expected["mapped_row_count"]
        );
        assert_eq!(
            document.health().preserved_only_row_count,
            expected["preserved_only_row_count"]
        );
        assert_eq!(
            document.health().dropped_row_count,
            expected["dropped_row_count"]
        );
        assert_eq!(
            document.health().unsupported_row_count,
            expected["unsupported_row_count"]
        );
        assert_eq!(document.health().blocker_count, expected["blocker_count"]);
        let codes = document
            .health()
            .diagnostics
            .iter()
            .map(|row| row.code.as_str())
            .collect::<BTreeSet<_>>();
        let expected_codes = expected["diagnostic_codes"]
            .as_array()
            .expect("diagnostic codes")
            .iter()
            .map(|code| code.as_str().expect("diagnostic code"))
            .collect::<BTreeSet<_>>();
        assert_eq!(codes, expected_codes, "diagnostic drift: {source_path}");
        verify_health_self_hash(&document);
    }
}
