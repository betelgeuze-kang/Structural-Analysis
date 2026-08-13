use std::collections::{BTreeMap, BTreeSet};
use std::ffi::OsString;
use std::path::{Component, Path, PathBuf};

use serde::{Deserialize, Serialize};
use serde_json::Value;
use structural_contracts::model_ir::{canonicalize_model_ir_v2, decode_json_strict};
use structural_contracts::product_ir::sha256_identity;

use super::{
    canonical_struct, parse_source_map, read_bounded_regular_file, resolve_required_file,
    verify_real_directory, FrontendContractError, SOURCE_MAP_BYTES,
};

const MAX_VIEWER_MANIFEST_BYTES: u64 = 2 * 1024 * 1024;
const MAX_VIEWER_WORKSPACE_BYTES: u64 = 4 * 1024 * 1024;
const MAX_ARTIFACT_COUNT_SOURCE_BYTES: u64 = 128 * 1024 * 1024;
const MAX_PROJECTS: usize = 256;
const MAX_DRAWINGS: usize = 16_384;
const MAX_VARIANTS: usize = 65_536;
const MAX_TEXT_BYTES: usize = 16 * 1024;
const MAX_PATH_BYTES: usize = 512;
const JAVASCRIPT_PROJECTION_PREFIX: &str =
    "/* Generated from viewer-project-manifest.v1.json; checked by structural-frontend-contract. */\nexport const DEFAULT_STRUCTURE_VIEWER_PROJECT_MANIFEST = ";
const JAVASCRIPT_PROJECTION_SUFFIX: &str = ";\n";

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ViewerManifestMinimumsV1 {
    pub projects: usize,
    pub drawings: usize,
    pub variants: usize,
    pub release_triples: usize,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct ViewerManifestSourceV1 {
    pub(super) contract: String,
    pub(super) manifest_path: String,
    pub(super) javascript_projection_path: String,
    pub(super) workspace_module_path: String,
    pub(super) project_schema_version: String,
    pub(super) release_project_id: String,
    pub(super) status_order: Vec<String>,
    pub(super) default_minimums: ViewerManifestMinimumsV1,
    pub(super) workspace_required_markers: Vec<String>,
    pub(super) generated_release_path_fragment: String,
    pub(super) claim_boundary: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ProjectManifestV1 {
    schema_version: String,
    generated_at: String,
    projects: Vec<ProjectV1>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ProjectV1 {
    project_id: String,
    project_title: String,
    drawings: Vec<DrawingV1>,
}

#[derive(Clone, Debug, Default, Deserialize)]
#[serde(deny_unknown_fields)]
struct OptimizationSummaryV1 {
    #[serde(default)]
    baseline_member_count: Option<u64>,
    #[serde(default)]
    optimized_member_count: Option<u64>,
    #[serde(default)]
    evidence_level: String,
    #[serde(default)]
    risk_delta_label: String,
    #[serde(default)]
    source: String,
    #[serde(default)]
    artifact_count_source: String,
}

#[derive(Clone, Debug, Default, Deserialize)]
#[serde(deny_unknown_fields)]
struct ProvenanceV1 {
    #[serde(default)]
    source_path: String,
    #[serde(default)]
    report_path: String,
    #[serde(default)]
    evidence_level: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct VariantV1 {
    variant: String,
    label: String,
    #[serde(default)]
    viewer_preset: String,
    #[serde(default)]
    artifact_path: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct DrawingV1 {
    drawing_id: String,
    drawing_title: String,
    source_family: String,
    #[serde(default)]
    artifact_path: String,
    #[serde(default)]
    viewer_preset: String,
    #[serde(default)]
    baseline_ref: String,
    #[serde(default)]
    optimized_ref: String,
    #[serde(default)]
    optimization_summary: OptimizationSummaryV1,
    quality_flags: Vec<String>,
    commercial_review_status: String,
    #[serde(default)]
    release_family: String,
    #[serde(default)]
    provenance: ProvenanceV1,
    #[serde(default)]
    solver_receipts: Vec<Value>,
    #[serde(default)]
    lineage: Vec<Value>,
    #[serde(default)]
    ingest_summary: Value,
    variants: Vec<VariantV1>,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ViewerManifestSummaryV1 {
    pub project_count: usize,
    pub drawing_count: usize,
    pub variant_count: usize,
    pub status_counts: BTreeMap<String, usize>,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ViewerArtifactCountCheckV1 {
    pub label: String,
    pub source_path: String,
    pub exists: bool,
    pub baseline_manifest: Option<u64>,
    pub optimized_manifest: Option<u64>,
    pub baseline_artifact: Option<u64>,
    pub optimized_artifact: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub source_byte_length: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub source_sha256: Option<String>,
    pub ok: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub optional: Option<bool>,
}

/// Canonical, self-hashed verification of the language-neutral Viewer project manifest.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ViewerManifestReceiptV1 {
    #[serde(rename = "schema_version")]
    pub schema_version: String,
    pub action: String,
    #[serde(rename = "contract_pass")]
    pub contract_pass: bool,
    #[serde(rename = "reason_code")]
    pub reason_code: String,
    #[serde(rename = "manifest_schema_version")]
    pub manifest_schema_version: String,
    pub summary: ViewerManifestSummaryV1,
    pub release_triple_count: usize,
    pub path_check_count: usize,
    pub missing_path_count: usize,
    pub artifact_count_check_count: usize,
    pub artifact_count_mismatch_count: usize,
    pub artifact_count_checks: Vec<ViewerArtifactCountCheckV1>,
    pub minimums: ViewerManifestMinimumsV1,
    #[serde(rename = "source_map_sha256")]
    pub source_map_sha256: String,
    #[serde(rename = "manifest_sha256")]
    pub manifest_sha256: String,
    #[serde(rename = "javascript_projection_sha256")]
    pub javascript_projection_sha256: String,
    #[serde(rename = "workspace_module_sha256")]
    pub workspace_module_sha256: String,
    pub deterministic: bool,
    #[serde(rename = "commands_executed")]
    pub commands_executed: u64,
    #[serde(rename = "network_access_count")]
    pub network_access_count: u64,
    #[serde(rename = "claim_boundary")]
    pub claim_boundary: String,
    pub warnings: Vec<String>,
    pub errors: Vec<String>,
    #[serde(rename = "receipt_hash")]
    pub receipt_hash: String,
}

#[derive(Debug)]
struct ResolvedRepoPath {
    skipped: bool,
    path: Option<PathBuf>,
}

#[derive(Debug, Default)]
struct ManifestValidation {
    summary: Option<ViewerManifestSummaryV1>,
    release_triple_count: usize,
    path_check_count: usize,
    missing_path_count: usize,
    artifact_count_checks: Vec<ViewerArtifactCountCheckV1>,
    warnings: Vec<String>,
    errors: Vec<String>,
}

#[derive(Clone, Copy)]
struct DrawingContext<'a> {
    root: &'a Path,
    contract: &'a ViewerManifestSourceV1,
    project: &'a ProjectV1,
    drawing: &'a DrawingV1,
    label: &'a str,
}

/// Verify the frozen default Viewer project manifest without executing JavaScript.
///
/// # Errors
///
/// Rejects duplicate-key or schema-invalid JSON, JavaScript projection drift, repo path escape,
/// symlinks, inventory/status/variant drift, and mismatched locally present artifact counts.
pub fn check_viewer_manifest(
    root: &Path,
) -> Result<ViewerManifestReceiptV1, FrontendContractError> {
    verify_real_directory(root, "viewer manifest root")?;
    let source_map = parse_source_map()?;
    let contract = &source_map.viewer_manifest_contract;

    let manifest_path = resolve_required_file(root, &contract.manifest_path)?;
    let projection_path = resolve_required_file(root, &contract.javascript_projection_path)?;
    let workspace_path = resolve_required_file(root, &contract.workspace_module_path)?;
    let manifest_bytes = read_bounded_regular_file(
        &manifest_path,
        MAX_VIEWER_MANIFEST_BYTES,
        "Viewer project manifest",
    )?;
    let projection_bytes = read_bounded_regular_file(
        &projection_path,
        MAX_VIEWER_MANIFEST_BYTES,
        "Viewer project manifest JavaScript projection",
    )?;
    let workspace_bytes = read_bounded_regular_file(
        &workspace_path,
        MAX_VIEWER_WORKSPACE_BYTES,
        "Viewer project workspace module",
    )?;

    validate_exact_javascript_projection(&manifest_bytes, &projection_bytes)?;
    validate_workspace_projection_import(contract, &workspace_bytes)?;
    let value = decode_json_strict(&manifest_bytes).map_err(|error| {
        FrontendContractError::new(
            "viewer_manifest_json_invalid",
            format!("Viewer project manifest is invalid strict JSON: {error}"),
        )
    })?;
    let manifest: ProjectManifestV1 = serde_json::from_value(value).map_err(|error| {
        FrontendContractError::new(
            "viewer_manifest_schema_invalid",
            format!("Viewer project manifest fields are invalid: {error}"),
        )
    })?;
    let validation = validate_manifest(root, contract, &manifest);
    if !validation.errors.is_empty() {
        return Err(FrontendContractError::new(
            "viewer_manifest_contract_drift",
            validation.errors.join("; "),
        ));
    }
    let summary = validation.summary.ok_or_else(|| {
        FrontendContractError::new(
            "viewer_manifest_contract_drift",
            "Viewer project manifest summary was not produced",
        )
    })?;
    let mismatch_count = validation
        .artifact_count_checks
        .iter()
        .filter(|check| !check.ok)
        .count();
    let mut receipt = ViewerManifestReceiptV1 {
        schema_version: contract.contract.clone(),
        action: "viewer_manifest_check".to_owned(),
        contract_pass: true,
        reason_code: "PASS".to_owned(),
        manifest_schema_version: manifest.schema_version,
        summary,
        release_triple_count: validation.release_triple_count,
        path_check_count: validation.path_check_count,
        missing_path_count: validation.missing_path_count,
        artifact_count_check_count: validation.artifact_count_checks.len(),
        artifact_count_mismatch_count: mismatch_count,
        artifact_count_checks: validation.artifact_count_checks,
        minimums: contract.default_minimums,
        source_map_sha256: sha256_identity(SOURCE_MAP_BYTES),
        manifest_sha256: sha256_identity(&manifest_bytes),
        javascript_projection_sha256: sha256_identity(&projection_bytes),
        workspace_module_sha256: sha256_identity(&workspace_bytes),
        deterministic: true,
        commands_executed: 0,
        network_access_count: 0,
        claim_boundary: contract.claim_boundary.clone(),
        warnings: validation.warnings,
        errors: Vec::new(),
        receipt_hash: String::new(),
    };
    receipt.receipt_hash = hash_without_receipt_hash(&receipt)?;
    Ok(receipt)
}

/// Encode a Viewer project-manifest receipt as canonical JSON.
///
/// # Errors
///
/// Returns an error if the receipt cannot be projected into canonical JSON.
pub fn canonical_viewer_manifest_receipt_json(
    receipt: &ViewerManifestReceiptV1,
) -> Result<String, FrontendContractError> {
    canonical_struct(receipt, "viewer_manifest_receipt_encode_failed")
}

pub(super) fn validate_viewer_manifest_source(
    source: &ViewerManifestSourceV1,
) -> Result<(), FrontendContractError> {
    if source.contract != "structure-viewer-project-manifest-verification.v1"
        || source.project_schema_version != "structure-viewer-project-manifest.v1"
        || source.release_project_id != "release_visualization"
        || source.status_order != ["ready", "needs_review", "blocked"]
        || source.workspace_required_markers.is_empty()
        || source.workspace_required_markers.len() > 16
        || source.generated_release_path_fragment != "implementation/phase1/release/"
        || source.claim_boundary.trim().is_empty()
    {
        return Err(source_contract_error(
            "Viewer manifest source-map identity or boundary is invalid",
        ));
    }
    for path in [
        &source.manifest_path,
        &source.javascript_projection_path,
        &source.workspace_module_path,
    ] {
        super::validate_relative_path(path)?;
    }
    let minimums = source.default_minimums;
    if minimums.projects == 0
        || minimums.projects > MAX_PROJECTS
        || minimums.drawings == 0
        || minimums.drawings > MAX_DRAWINGS
        || minimums.variants == 0
        || minimums.variants > MAX_VARIANTS
        || minimums.release_triples > minimums.drawings
    {
        return Err(source_contract_error(
            "Viewer manifest source-map minimums are invalid",
        ));
    }
    if source
        .workspace_required_markers
        .iter()
        .chain(source.status_order.iter())
        .any(|value| !valid_text(value))
    {
        return Err(source_contract_error(
            "Viewer manifest source-map text is invalid",
        ));
    }
    Ok(())
}

fn validate_exact_javascript_projection(
    manifest_bytes: &[u8],
    projection_bytes: &[u8],
) -> Result<(), FrontendContractError> {
    let manifest = std::str::from_utf8(manifest_bytes).map_err(|_| {
        FrontendContractError::new(
            "viewer_manifest_json_invalid",
            "Viewer project manifest must be UTF-8",
        )
    })?;
    let body = manifest.strip_suffix('\n').ok_or_else(|| {
        FrontendContractError::new(
            "viewer_manifest_json_invalid",
            "Viewer project manifest must end with one LF",
        )
    })?;
    if body.ends_with(['\r', '\n']) {
        return Err(FrontendContractError::new(
            "viewer_manifest_json_invalid",
            "Viewer project manifest must use one trailing LF",
        ));
    }
    let mut expected = Vec::with_capacity(
        JAVASCRIPT_PROJECTION_PREFIX.len() + body.len() + JAVASCRIPT_PROJECTION_SUFFIX.len(),
    );
    expected.extend_from_slice(JAVASCRIPT_PROJECTION_PREFIX.as_bytes());
    expected.extend_from_slice(body.as_bytes());
    expected.extend_from_slice(JAVASCRIPT_PROJECTION_SUFFIX.as_bytes());
    if projection_bytes != expected {
        return Err(FrontendContractError::new(
            "viewer_manifest_javascript_projection_drift",
            "Viewer project manifest JavaScript projection differs from the language-neutral JSON",
        ));
    }
    Ok(())
}

fn validate_workspace_projection_import(
    contract: &ViewerManifestSourceV1,
    workspace_bytes: &[u8],
) -> Result<(), FrontendContractError> {
    let workspace = std::str::from_utf8(workspace_bytes).map_err(|_| {
        FrontendContractError::new(
            "viewer_manifest_workspace_invalid",
            "Viewer project workspace module must be UTF-8",
        )
    })?;
    for marker in &contract.workspace_required_markers {
        if !workspace.contains(marker) {
            return Err(FrontendContractError::new(
                "viewer_manifest_workspace_drift",
                format!(
                    "Viewer project workspace is missing its neutral-manifest marker: {marker}"
                ),
            ));
        }
    }
    Ok(())
}

fn validate_manifest(
    root: &Path,
    contract: &ViewerManifestSourceV1,
    manifest: &ProjectManifestV1,
) -> ManifestValidation {
    let mut output = ManifestValidation::default();
    if manifest.schema_version != contract.project_schema_version {
        output.errors.push(format!(
            "schema_version mismatch: {}",
            manifest.schema_version
        ));
    }
    if !valid_text(&manifest.generated_at) {
        output
            .errors
            .push("manifest generated_at is invalid".to_owned());
    }
    if manifest.projects.len() > MAX_PROJECTS {
        output
            .errors
            .push("project count exceeds the native bound".to_owned());
    }

    let mut project_ids = BTreeSet::new();
    let mut drawing_ids = BTreeSet::new();
    let mut drawing_count = 0_usize;
    let mut variant_count = 0_usize;
    let mut status_counts = contract
        .status_order
        .iter()
        .map(|status| (status.clone(), 0_usize))
        .collect::<BTreeMap<_, _>>();
    let mut release_project_present = false;

    for project in &manifest.projects {
        validate_project_identity(project, &mut project_ids, &mut output.errors);
        if project.drawings.is_empty() {
            output
                .errors
                .push(format!("{} has no drawings", project.project_id));
        }
        if project.project_id == contract.release_project_id {
            release_project_present = true;
        }
        for drawing in &project.drawings {
            drawing_count = drawing_count.saturating_add(1);
            variant_count = variant_count.saturating_add(drawing.variants.len());
            let label = format!("{}/{}", project.project_id, drawing.drawing_id);
            validate_drawing(
                DrawingContext {
                    root,
                    contract,
                    project,
                    drawing,
                    label: &label,
                },
                &mut drawing_ids,
                &mut status_counts,
                &mut output,
            );
        }
    }
    if drawing_count > MAX_DRAWINGS || variant_count > MAX_VARIANTS {
        output
            .errors
            .push("drawing or variant inventory exceeds the native bound".to_owned());
    }
    if manifest.projects.len() < contract.default_minimums.projects {
        output.errors.push(format!(
            "project count below minimum: {}",
            manifest.projects.len()
        ));
    }
    if drawing_count < contract.default_minimums.drawings {
        output
            .errors
            .push(format!("drawing count below minimum: {drawing_count}"));
    }
    if variant_count < contract.default_minimums.variants {
        output
            .errors
            .push(format!("variant count below minimum: {variant_count}"));
    }
    if !release_project_present {
        output
            .errors
            .push("release_visualization project missing".to_owned());
    }
    if output.release_triple_count < contract.default_minimums.release_triples {
        output.errors.push(format!(
            "release visualization triple count below minimum: {}",
            output.release_triple_count
        ));
    }
    output.summary = Some(ViewerManifestSummaryV1 {
        project_count: manifest.projects.len(),
        drawing_count,
        variant_count,
        status_counts,
    });
    output
}

fn validate_project_identity(
    project: &ProjectV1,
    seen: &mut BTreeSet<String>,
    errors: &mut Vec<String>,
) {
    if !valid_token(&project.project_id) {
        errors.push("project missing or invalid project_id".to_owned());
    } else if !seen.insert(project.project_id.clone()) {
        errors.push(format!("duplicate project_id: {}", project.project_id));
    }
    if !valid_text(&project.project_title) {
        errors.push(format!(
            "{} missing or invalid project_title",
            project.project_id
        ));
    }
}

fn validate_drawing(
    context: DrawingContext<'_>,
    drawing_ids: &mut BTreeSet<String>,
    status_counts: &mut BTreeMap<String, usize>,
    output: &mut ManifestValidation,
) {
    validate_drawing_metadata(context, drawing_ids, status_counts, output);
    validate_drawing_paths(context, output);
    let variants = validate_drawing_variants(context, output);
    validate_release_drawing(context, &variants, output);
}

fn validate_drawing_metadata(
    context: DrawingContext<'_>,
    drawing_ids: &mut BTreeSet<String>,
    status_counts: &mut BTreeMap<String, usize>,
    output: &mut ManifestValidation,
) {
    let DrawingContext {
        project,
        drawing,
        label,
        ..
    } = context;
    if !valid_token(&drawing.drawing_id) {
        output
            .errors
            .push(format!("{label} missing or invalid drawing_id"));
    } else if !drawing_ids.insert(format!("{}/{}", project.project_id, drawing.drawing_id)) {
        output.errors.push(format!("duplicate drawing_id: {label}"));
    }
    for (field, value) in [
        ("drawing_title", drawing.drawing_title.as_str()),
        ("source_family", drawing.source_family.as_str()),
        ("baseline_ref", drawing.baseline_ref.as_str()),
        ("optimized_ref", drawing.optimized_ref.as_str()),
        ("release_family", drawing.release_family.as_str()),
        (
            "optimization evidence_level",
            drawing.optimization_summary.evidence_level.as_str(),
        ),
        (
            "optimization risk_delta_label",
            drawing.optimization_summary.risk_delta_label.as_str(),
        ),
        (
            "optimization source",
            drawing.optimization_summary.source.as_str(),
        ),
        (
            "provenance evidence_level",
            drawing.provenance.evidence_level.as_str(),
        ),
    ] {
        if !value.is_empty() && !valid_text(value) {
            output.errors.push(format!("{label} has invalid {field}"));
        }
    }
    if drawing.drawing_title.trim().is_empty() {
        output.errors.push(format!("{label} missing drawing_title"));
    }
    match status_counts.get_mut(&drawing.commercial_review_status) {
        Some(count) => *count = count.saturating_add(1),
        None => output.errors.push(format!(
            "{label} has invalid commercial_review_status={}",
            drawing.commercial_review_status
        )),
    }
    validate_quality_flags(label, &drawing.quality_flags, &mut output.errors);
    if drawing.variants.is_empty() {
        output.errors.push(format!("{label} has no variants"));
    }
    if drawing.viewer_preset.is_empty()
        && drawing.artifact_path.is_empty()
        && !drawing
            .variants
            .iter()
            .any(|variant| !variant.viewer_preset.is_empty() || !variant.artifact_path.is_empty())
    {
        output
            .errors
            .push(format!("{label} has no viewer_preset or artifact path"));
    }
    let _ = (
        &drawing.solver_receipts,
        &drawing.lineage,
        &drawing.ingest_summary,
    );
}

fn validate_drawing_paths(context: DrawingContext<'_>, output: &mut ManifestValidation) {
    let DrawingContext {
        root,
        contract,
        drawing,
        label,
        ..
    } = context;
    let drawing_required = !drawing.artifact_path.is_empty() && drawing.viewer_preset.is_empty();
    add_path_check(
        root,
        contract,
        output,
        &format!("{label} drawing artifact"),
        &drawing.artifact_path,
        drawing_required,
    );
    if drawing.provenance.source_path.is_empty() {
        output
            .warnings
            .push(format!("{label} has no provenance source_path"));
    } else {
        add_path_check(
            root,
            contract,
            output,
            &format!("{label} provenance source"),
            &drawing.provenance.source_path,
            true,
        );
    }
    if !drawing.provenance.report_path.is_empty() {
        add_path_check(
            root,
            contract,
            output,
            &format!("{label} provenance report"),
            &drawing.provenance.report_path,
            true,
        );
    }
    add_artifact_count_check(root, contract, output, label, drawing);
}

fn validate_drawing_variants(
    context: DrawingContext<'_>,
    output: &mut ManifestValidation,
) -> BTreeSet<String> {
    let DrawingContext {
        root,
        contract,
        drawing,
        label,
        ..
    } = context;
    let mut variants = BTreeSet::new();
    for variant in &drawing.variants {
        if !valid_token(&variant.variant) {
            output
                .errors
                .push(format!("{label} variant missing or invalid name"));
        } else if !variants.insert(variant.variant.clone()) {
            output.errors.push(format!(
                "{label} has duplicate variant name: {}",
                variant.variant
            ));
        }
        if !valid_text(&variant.label) {
            output
                .errors
                .push(format!("{label}/{} has invalid label", variant.variant));
        }
        if variant.viewer_preset.is_empty() && variant.artifact_path.is_empty() {
            output.errors.push(format!(
                "{label}/{} has no preset or artifact",
                variant.variant
            ));
        }
        if !variant.artifact_path.is_empty() {
            add_path_check(
                root,
                contract,
                output,
                &format!("{label}/{} artifact", variant.variant),
                &variant.artifact_path,
                variant.viewer_preset.is_empty(),
            );
        }
    }
    variants
}

fn validate_release_drawing(
    context: DrawingContext<'_>,
    variants: &BTreeSet<String>,
    output: &mut ManifestValidation,
) {
    let DrawingContext {
        contract,
        project,
        drawing,
        label,
        ..
    } = context;
    if project.project_id == contract.release_project_id {
        if ["baseline", "optimized", "compare"]
            .iter()
            .all(|name| variants.contains(*name))
        {
            output.release_triple_count = output.release_triple_count.saturating_add(1);
        } else {
            output.errors.push(format!(
                "{label} does not expose baseline/optimized/compare variants"
            ));
        }
        if !drawing
            .quality_flags
            .iter()
            .any(|flag| flag == "external_receipt_pending")
        {
            output.warnings.push(format!(
                "{label} should remain claim-limited without external receipt"
            ));
        }
    }
}

fn validate_quality_flags(label: &str, flags: &[String], errors: &mut Vec<String>) {
    let mut unique = BTreeSet::new();
    for flag in flags {
        if !valid_token(flag) {
            errors.push(format!("{label} has invalid quality flag: {flag}"));
        } else if !unique.insert(flag) {
            errors.push(format!("{label} has duplicate quality flag: {flag}"));
        }
    }
}

fn add_path_check(
    root: &Path,
    contract: &ViewerManifestSourceV1,
    output: &mut ManifestValidation,
    label: &str,
    relative: &str,
    required: bool,
) {
    output.path_check_count = output.path_check_count.saturating_add(1);
    match resolve_repo_path(root, relative) {
        Ok(resolved) if resolved.skipped => {}
        Ok(resolved) if resolved.path.is_some() => {}
        Ok(_) => {
            output.missing_path_count = output.missing_path_count.saturating_add(1);
            if required {
                if is_generated_release_path(contract, relative) {
                    output.warnings.push(format!(
                        "{label} missing (generated release artifact): {relative}"
                    ));
                } else {
                    output.errors.push(format!("{label} missing: {relative}"));
                }
            }
        }
        Err(error) => output.errors.push(format!("{label} invalid: {error}")),
    }
}

fn add_artifact_count_check(
    root: &Path,
    contract: &ViewerManifestSourceV1,
    output: &mut ManifestValidation,
    label: &str,
    drawing: &DrawingV1,
) {
    let source_path = drawing.optimization_summary.artifact_count_source.trim();
    if source_path.is_empty() {
        return;
    }
    let mut check = ViewerArtifactCountCheckV1 {
        label: label.to_owned(),
        source_path: source_path.to_owned(),
        exists: false,
        baseline_manifest: drawing.optimization_summary.baseline_member_count,
        optimized_manifest: drawing.optimization_summary.optimized_member_count,
        baseline_artifact: None,
        optimized_artifact: None,
        source_byte_length: None,
        source_sha256: None,
        ok: false,
        optional: None,
    };
    match resolve_repo_path(root, source_path) {
        Ok(ResolvedRepoPath { path: None, .. }) => {
            if is_generated_release_path(contract, source_path) {
                check.optional = Some(true);
                output.warnings.push(format!(
                    "{label} artifact count source missing (generated release artifact): {source_path}"
                ));
            } else {
                output.errors.push(format!(
                    "{label} artifact count source missing: {source_path}"
                ));
            }
        }
        Ok(ResolvedRepoPath {
            path: Some(path), ..
        }) => {
            check.exists = true;
            match read_artifact_counts(&path) {
                Ok((baseline, optimized, byte_length, sha256)) => {
                    check.baseline_artifact = baseline;
                    check.optimized_artifact = optimized;
                    check.source_byte_length = Some(byte_length);
                    check.source_sha256 = Some(sha256);
                    check.ok = check.baseline_manifest == baseline
                        && check.optimized_manifest == optimized
                        && baseline.is_some()
                        && optimized.is_some();
                    if !check.ok {
                        output.errors.push(format!(
                            "{label} artifact count mismatch: manifest {:?}->{:?}, artifact {:?}->{:?}",
                            check.baseline_manifest,
                            check.optimized_manifest,
                            check.baseline_artifact,
                            check.optimized_artifact
                        ));
                    }
                }
                Err(error) => output
                    .errors
                    .push(format!("{label} artifact count source unreadable: {error}")),
            }
        }
        Err(error) => output
            .errors
            .push(format!("{label} artifact count source invalid: {error}")),
    }
    output.artifact_count_checks.push(check);
}

fn read_artifact_counts(
    path: &Path,
) -> Result<(Option<u64>, Option<u64>, u64, String), FrontendContractError> {
    let bytes = read_bounded_regular_file(
        path,
        MAX_ARTIFACT_COUNT_SOURCE_BYTES,
        "Viewer artifact count source",
    )?;
    let byte_length = u64::try_from(bytes.len()).map_err(|_| {
        FrontendContractError::new(
            "viewer_manifest_artifact_length_invalid",
            "Viewer artifact count source length is not addressable",
        )
    })?;
    let sha256 = sha256_identity(&bytes);
    let value = decode_json_strict(&bytes).map_err(|error| {
        FrontendContractError::new(
            "viewer_manifest_artifact_json_invalid",
            format!("Viewer artifact count source is invalid strict JSON: {error}"),
        )
    })?;
    let interactive = value.get("interactive_3d").and_then(Value::as_object);
    let baseline = interactive.and_then(|object| {
        exact_count(object.get("baseline_segment_count")).or_else(|| {
            object
                .get("baseline_segments")
                .and_then(Value::as_array)
                .and_then(|rows| u64::try_from(rows.len()).ok())
        })
    });
    let optimized = interactive.and_then(|object| {
        exact_count(object.get("after_segment_count")).or_else(|| {
            object
                .get("after_segments")
                .and_then(Value::as_array)
                .and_then(|rows| u64::try_from(rows.len()).ok())
        })
    });
    Ok((baseline, optimized, byte_length, sha256))
}

fn exact_count(value: Option<&Value>) -> Option<u64> {
    let value = value?;
    value.as_u64().or_else(|| {
        let number = value.as_f64()?;
        if number.is_finite()
            && (0.0..=9_007_199_254_740_991.0).contains(&number)
            && number.fract() == 0.0
        {
            #[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
            Some(number as u64)
        } else {
            None
        }
    })
}

fn resolve_repo_path(root: &Path, value: &str) -> Result<ResolvedRepoPath, FrontendContractError> {
    let text = value.trim();
    if text.is_empty() || is_external_or_private(text) {
        return Ok(ResolvedRepoPath {
            skipped: true,
            path: None,
        });
    }
    if text.len() > MAX_PATH_BYTES || text.contains('\\') || text.chars().any(char::is_control) {
        return Err(path_error(text));
    }
    let mut candidates = BTreeSet::new();
    for base in [&[][..], &["src", "structure-viewer"][..]] {
        if let Some(relative) = normalize_candidate(base, text) {
            candidates.insert(relative);
        }
    }
    if candidates.is_empty() {
        return Err(path_error(text));
    }
    for relative in candidates {
        match resolve_required_file(root, &relative) {
            Ok(path) => {
                return Ok(ResolvedRepoPath {
                    skipped: false,
                    path: Some(path),
                });
            }
            Err(error) if error.code == "frontend_required_file_missing" => {}
            Err(error) => {
                return Err(FrontendContractError::new(
                    "viewer_manifest_path_invalid",
                    format!(
                        "Viewer manifest path is unsafe or not a regular file: {text}: {error}"
                    ),
                ));
            }
        }
    }
    Ok(ResolvedRepoPath {
        skipped: false,
        path: None,
    })
}

fn normalize_candidate(base: &[&str], value: &str) -> Option<String> {
    if Path::new(value).is_absolute() {
        return None;
    }
    let mut segments = base.iter().map(OsString::from).collect::<Vec<_>>();
    for component in Path::new(value).components() {
        match component {
            Component::Normal(segment) => segments.push(segment.to_os_string()),
            Component::CurDir => {}
            Component::ParentDir => {
                segments.pop()?;
            }
            Component::RootDir | Component::Prefix(_) => return None,
        }
    }
    if segments.is_empty() {
        return None;
    }
    let mut values = Vec::with_capacity(segments.len());
    for segment in segments {
        values.push(segment.to_str()?.to_owned());
    }
    Some(values.join("/"))
}

fn is_external_or_private(value: &str) -> bool {
    let lower = value.to_ascii_lowercase();
    value.starts_with("private ")
        || lower.starts_with("http://")
        || lower.starts_with("https://")
        || lower.starts_with("data:")
}

fn is_generated_release_path(contract: &ViewerManifestSourceV1, value: &str) -> bool {
    value.contains(&contract.generated_release_path_fragment)
}

fn valid_token(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 256
        && value
            .bytes()
            .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'_')
}

fn valid_text(value: &str) -> bool {
    !value.trim().is_empty()
        && value.len() <= MAX_TEXT_BYTES
        && !value.chars().any(char::is_control)
}

fn source_contract_error(detail: &str) -> FrontendContractError {
    FrontendContractError::new("frontend_source_map_contract_invalid", detail)
}

fn path_error(path: &str) -> FrontendContractError {
    FrontendContractError::new(
        "viewer_manifest_path_invalid",
        format!("Viewer manifest path escapes or violates the repo boundary: {path}"),
    )
}

fn hash_without_receipt_hash(
    receipt: &ViewerManifestReceiptV1,
) -> Result<String, FrontendContractError> {
    let mut value = serde_json::to_value(receipt).map_err(|error| {
        FrontendContractError::new(
            "viewer_manifest_receipt_encode_failed",
            format!("project Viewer manifest receipt failed: {error}"),
        )
    })?;
    value
        .as_object_mut()
        .ok_or_else(|| {
            FrontendContractError::new(
                "viewer_manifest_receipt_encode_failed",
                "Viewer manifest receipt projection is not an object",
            )
        })?
        .remove("receipt_hash");
    let canonical = canonicalize_model_ir_v2(&value).map_err(|error| {
        FrontendContractError::new(
            "viewer_manifest_receipt_encode_failed",
            format!("canonicalize Viewer manifest receipt failed: {error}"),
        )
    })?;
    Ok(sha256_identity(canonical.as_bytes()))
}

#[cfg(test)]
mod tests {
    use std::sync::atomic::{AtomicU64, Ordering};

    use structural_contracts::product_ir::sha256_identity;

    use super::{normalize_candidate, read_artifact_counts, ViewerManifestMinimumsV1};

    static TEST_SEQUENCE: AtomicU64 = AtomicU64::new(0);

    #[test]
    fn candidate_normalization_never_escapes_the_repo_root() {
        assert_eq!(
            normalize_candidate(
                &["src", "structure-viewer"],
                "../../implementation/phase1/release/file.json"
            )
            .as_deref(),
            Some("implementation/phase1/release/file.json")
        );
        assert!(normalize_candidate(&[], "../../outside.json").is_none());
        assert!(normalize_candidate(&["src"], "../../outside.json").is_none());
        assert!(normalize_candidate(&[], "/absolute.json").is_none());
    }

    #[test]
    fn frozen_minimums_remain_explicit() {
        assert_eq!(
            ViewerManifestMinimumsV1 {
                projects: 3,
                drawings: 11,
                variants: 32,
                release_triples: 8,
            }
            .release_triples,
            8
        );
    }

    #[test]
    fn artifact_counts_are_strict_and_bind_the_exact_source_bytes() {
        let sequence = TEST_SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "structural-viewer-artifact-count-{}-{sequence}.json",
            std::process::id()
        ));
        let bytes =
            b"{\"interactive_3d\":{\"after_segments\":[{},{}],\"baseline_segment_count\":3}}\n";
        std::fs::write(&path, bytes).expect("write artifact-count fixture");
        let (baseline, optimized, byte_length, sha256) =
            read_artifact_counts(&path).expect("read artifact counts");
        let _removed = std::fs::remove_file(&path);
        assert_eq!(baseline, Some(3));
        assert_eq!(optimized, Some(2));
        assert_eq!(
            byte_length,
            u64::try_from(bytes.len()).expect("fixture length")
        );
        assert_eq!(sha256, sha256_identity(bytes));
    }
}
