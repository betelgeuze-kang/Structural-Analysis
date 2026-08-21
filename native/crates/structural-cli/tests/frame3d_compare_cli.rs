use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicU64, Ordering};

use serde_json::{json, Value};

static NEXT_TEMP_FILE: AtomicU64 = AtomicU64::new(0);

struct TempFile(PathBuf);

impl TempFile {
    fn write(label: &str, bytes: &[u8]) -> Self {
        let sequence = NEXT_TEMP_FILE.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "structural-cli-comparison-{label}-{}-{sequence}.json",
            std::process::id()
        ));
        std::fs::write(&path, bytes).expect("temporary comparison file");
        Self(path)
    }
}

impl Drop for TempFile {
    fn drop(&mut self) {
        let _removed = std::fs::remove_file(&self.0);
    }
}

fn hash(character: char) -> String {
    format!("sha256:{}", character.to_string().repeat(64))
}

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

fn native_result() -> (TempFile, Value) {
    let fixture =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let mut model: Value =
        serde_json::from_slice(&std::fs::read(fixture).expect("ModelIR fixture"))
            .expect("ModelIR JSON");
    model["elements"][0]["formulation"] = json!("linear_timoshenko_frame3d");
    let model_file = TempFile::write("model", &serde_json::to_vec(&model).expect("model bytes"));
    let output = Command::new(env!("CARGO_BIN_EXE_structural-cli"))
        .args(["model", "analyze-frame3d"])
        .arg(&model_file.0)
        .args([
            "--load-pattern",
            "LC_AXIAL",
            "--result-id",
            "frame-alpha.LC_AXIAL",
        ])
        .output()
        .expect("native analysis runs");
    assert_eq!(
        output.status.code(),
        Some(0),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    let value: Value = serde_json::from_slice(&output.stdout).expect("ResultIR JSON");
    let file = TempFile::write("result", &output.stdout);
    (file, value)
}

fn reference(result: &Value) -> Value {
    json!({
        "schema_version": "structural-external-linear-frame3d-reference.v1",
        "reference_id": "reference.synthetic.LC_AXIAL",
        "source": {
            "tool": "synthetic_fixture",
            "version": "cli-contract-test-v1",
            "origin": "synthetic_contract_fixture",
            "export_sha256": hash('d')
        },
        "bindings": {
            "model_content_hash": result["bindings"]["model_content_hash"],
            "load_pattern_id": "LC_AXIAL",
            "load_combination_id": null
        },
        "axes": {
            "node_displacement": "global_ux_uy_uz_rx_ry_rz",
            "node_reaction": "global_fx_fy_fz_mx_my_mz",
            "member_end_force": "member_local_fx_fy_fz_mx_my_mz_i_then_j",
            "sign_convention": "native_result_ir_compatible"
        },
        "units": {"translation": "m", "rotation": "rad", "force": "N", "moment": "N*m"},
        "nodes": result["nodes"].as_array().expect("nodes").iter().map(|node| json!({
            "node_id": node["node_id"],
            "displacement": node["displacement_m_rad"],
            "reaction": node["reaction_n_nm"]
        })).collect::<Vec<_>>(),
        "members": result["members"].as_array().expect("members").iter().map(|member| json!({
            "member_id": member["member_id"],
            "end_i_force": member["end_i_force_n_nm"],
            "end_j_force": member["end_j_force_n_nm"]
        })).collect::<Vec<_>>(),
        "claim_boundary": "operator_declared_mapping_and_units_not_independent_validation_or_release_authority"
    })
}

fn compare(result: &TempFile, reference: &TempFile, output: &str) -> Output {
    Command::new(env!("CARGO_BIN_EXE_structural-cli"))
        .args(["result", "compare-frame3d"])
        .arg(&result.0)
        .arg(&reference.0)
        .args(["--comparison-id", "comparison.LC_AXIAL", "--output", output])
        .output()
        .expect("comparison CLI runs")
}

#[test]
fn comparison_cli_emits_hash_bound_non_promoting_comparison_ir() {
    let (result_file, result) = native_result();
    let reference_file = TempFile::write(
        "reference",
        &serde_json::to_vec(&reference(&result)).expect("reference bytes"),
    );
    let output = compare(&result_file, &reference_file, "comparison-ir");

    assert_eq!(
        output.status.code(),
        Some(0),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    assert!(output.stderr.is_empty());
    let comparison: Value = serde_json::from_slice(&output.stdout).expect("ComparisonIR JSON");
    assert_eq!(
        comparison["schema_version"],
        "structural-native-linear-frame3d-comparison-ir.v1"
    );
    assert_eq!(comparison["summary"]["passed"], true);
    assert_eq!(comparison["summary"]["failing_row_count"], 0);
    assert_eq!(
        comparison["source_result"]["result_hash"],
        result["result_hash"]
    );
    assert_eq!(
        comparison["authority"]["external_validation"],
        "not_established"
    );
    assert_eq!(
        comparison["authority"]["release_readiness"],
        "not_authoritative"
    );
}

#[test]
fn comparison_cli_html_is_deterministic_and_keeps_authority_visible() {
    let (result_file, result) = native_result();
    let reference_file = TempFile::write(
        "reference-html",
        &serde_json::to_vec(&reference(&result)).expect("reference bytes"),
    );
    let first = compare(&result_file, &reference_file, "html");
    let second = compare(&result_file, &reference_file, "html");

    assert_eq!(first.status.code(), Some(0));
    assert_eq!(first.stdout, second.stdout);
    let html = String::from_utf8(first.stdout).expect("UTF-8 comparison HTML");
    assert!(html.starts_with("<!doctype html>\n"));
    assert!(html.contains("Bounded native-to-external Frame3D comparison"));
    assert!(html.contains("not_established"));
    assert!(html.contains("not_authoritative"));
}

#[test]
fn comparison_cli_returns_nonzero_with_an_auditable_failed_gate() {
    let (result_file, result) = native_result();
    let mut reference = reference(&result);
    let value = reference["nodes"][1]["displacement"][0]
        .as_f64()
        .expect("finite displacement");
    reference["nodes"][1]["displacement"][0] = json!(value * 1.02);
    let reference_file = TempFile::write(
        "reference-failed",
        &serde_json::to_vec(&reference).expect("reference bytes"),
    );
    let output = compare(&result_file, &reference_file, "comparison-ir");

    assert_eq!(output.status.code(), Some(2));
    let comparison: Value =
        serde_json::from_slice(&output.stdout).expect("failed ComparisonIR JSON");
    assert_eq!(comparison["summary"]["passed"], false);
    assert!(
        comparison["summary"]["failing_row_count"]
            .as_u64()
            .expect("failure count")
            > 0
    );
    assert_eq!(
        comparison["authority"]["external_validation"],
        "not_established"
    );
}

#[test]
fn comparison_cli_rejects_a_transplanted_reference_without_an_artifact() {
    let (result_file, result) = native_result();
    let mut reference = reference(&result);
    reference["bindings"]["model_content_hash"] = json!(hash('e'));
    let reference_file = TempFile::write(
        "reference-stale",
        &serde_json::to_vec(&reference).expect("reference bytes"),
    );
    let output = compare(&result_file, &reference_file, "comparison-ir");

    assert_eq!(output.status.code(), Some(2));
    let failure: Value = serde_json::from_slice(&output.stdout).expect("failure JSON");
    assert_eq!(
        failure["schema_version"],
        "structural-native-linear-frame3d-comparison-failure.v1"
    );
    assert_eq!(
        failure["issues"][0]["code"],
        "frame3d_external_reference_binding_mismatch"
    );
}
