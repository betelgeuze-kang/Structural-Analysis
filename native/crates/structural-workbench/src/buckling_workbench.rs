use std::collections::BTreeSet;
use std::fs;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use structural_cli::{
    execute_model_ir_linear_buckling_analysis_with_checkpoint,
    publish_model_ir_linear_buckling_analysis,
    validate_model_ir_linear_buckling_analysis_compatibility,
};
use structural_contracts::model_buckling_product::{
    parse_model_ir_linear_buckling_analysis_request_v1,
    ModelIrLinearBucklingAnalysisRequestDocumentV1,
};
use structural_contracts::model_ir::{parse_model_ir_v2, ModelIrV2Document};
use structural_contracts::product_ir::sha256_identity;

use crate::buckling_result_view::BUCKLING_PRODUCT_FILES;
use crate::{
    canonical_hashed_json, canonical_self_hashed, output_parent, publish_initial_workspace,
    publish_new_directory, read_bounded_regular_file,
    render_model_ir_linear_buckling_result_view_directory, sync_directory, temporary_path,
    verify_directory, verify_self_hashed_json, verify_slice_bound, write_atomic_file,
    WorkbenchError, WorkbenchReportLocaleV1, MAX_MODEL_BYTES, MAX_PRODUCT_ARTIFACT_BYTES,
    MAX_REQUEST_BYTES, SESSION_FILE,
};

const SESSION_SCHEMA_V1: &str = "structural-native-model-ir-linear-buckling-workbench-session.v1";
const IMPORT_RECEIPT_SCHEMA_V1: &str =
    "structural-native-model-ir-linear-buckling-workbench-import-receipt.v1";
const VALIDATION_RECEIPT_SCHEMA_V1: &str =
    "structural-native-model-ir-linear-buckling-workbench-validation-receipt.v1";
const REPORT_RECEIPT_SCHEMA_V1: &str =
    "structural-native-model-ir-linear-buckling-workbench-report-receipt.v1";
const VIEW_SCHEMA_V1: &str = "structural-native-model-ir-linear-buckling-workbench-view.v1";
const IMPORT_DIRECTORY: &str = "01-import";
const VALIDATION_DIRECTORY: &str = "02-validate";
const DIRECT_DIRECTORY: &str = "03-run";
const RESUME_DIRECTORY: &str = "04-resume";
const REPORT_DIRECTORY: &str = "06-report";
const CLAIM_BOUNDARY: &str = "bounded_durable_modelir_frame3d_nodal_reference_load_cpu_linear_buckling_import_full_preflight_direct_execution_dual_phase_model_bound_checkpoint_restart_and_read_only_localized_factor_report_not_mixed_tension_member_load_self_weight_nonzero_prescribed_support_shell_sparse_nonlinear_external_parity_engineering_acceptance_customer_publication_hip_or_c6";

/// Ordered stages for the linear-buckling-only durable Workbench profile.
#[derive(Clone, Copy, Debug, Deserialize, Eq, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ModelIrLinearBucklingWorkbenchStageV1 {
    Imported,
    Validated,
    Direct,
    Resumed,
    Reported,
}

impl ModelIrLinearBucklingWorkbenchStageV1 {
    #[must_use]
    pub const fn label(self) -> &'static str {
        match self {
            Self::Imported => "imported",
            Self::Validated => "validated",
            Self::Direct => "direct",
            Self::Resumed => "resumed",
            Self::Reported => "reported",
        }
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
struct ModelIrLinearBucklingWorkbenchSessionV1 {
    schema_version: String,
    session_id: String,
    analysis_profile: String,
    stage: ModelIrLinearBucklingWorkbenchStageV1,
    model_content_hash: String,
    model_semantic_hash: String,
    model_provenance_hash: String,
    analysis_request_hash: String,
    claim_boundary: String,
    session_hash: String,
}

/// Durable linear-buckling controller calling the Rust product libraries directly.
#[derive(Debug)]
pub struct ModelIrLinearBucklingWorkbench {
    root: PathBuf,
    session: ModelIrLinearBucklingWorkbenchSessionV1,
}

impl ModelIrLinearBucklingWorkbench {
    /// Initialize from bounded non-symlink input paths.
    ///
    /// # Errors
    ///
    /// Rejects unsafe paths, malformed identities, existing destinations, or publication failure.
    pub fn initialize_from_paths(
        root: &Path,
        model_path: &Path,
        request_path: &Path,
    ) -> Result<Self, WorkbenchError> {
        let model = read_bounded_regular_file(model_path, MAX_MODEL_BYTES)?;
        let request = read_bounded_regular_file(request_path, MAX_REQUEST_BYTES)?;
        Self::initialize(root, &model, &request)
    }

    /// Initialize from exact canonical model and request bytes.
    ///
    /// # Errors
    ///
    /// Rejects malformed or identity-mismatched inputs and unsafe/existing destinations.
    pub fn initialize(
        root: &Path,
        model_bytes: &[u8],
        request_bytes: &[u8],
    ) -> Result<Self, WorkbenchError> {
        if root.exists() {
            return Err(error(
                "workbench_buckling_destination_exists",
                "the buckling Workbench directory must not already exist",
            ));
        }
        verify_slice_bound(model_bytes, MAX_MODEL_BYTES, "buckling ModelIR")?;
        verify_slice_bound(
            request_bytes,
            MAX_REQUEST_BYTES,
            "buckling analysis request",
        )?;
        verify_directory(
            output_parent(root),
            "workbench_buckling_output_parent_invalid",
        )?;
        let model = parse_model_ir_v2(model_bytes)
            .map_err(|value| error("workbench_buckling_model_invalid", value.to_string()))?;
        let request = parse_model_ir_linear_buckling_analysis_request_v1(request_bytes)
            .map_err(|value| error("workbench_buckling_request_invalid", value.to_string()))?;
        verify_request_identity(&model, &request)?;
        let session_id = sha256_identity(
            format!(
                "model-ir-linear-buckling-workbench.v1|{}|{}",
                model.content_hash(),
                request.request_hash()
            )
            .as_bytes(),
        );
        let session = ModelIrLinearBucklingWorkbenchSessionV1 {
            schema_version: SESSION_SCHEMA_V1.to_owned(),
            session_id: session_id.clone(),
            analysis_profile: "model_ir_linear_buckling_cpu_v1".to_owned(),
            stage: ModelIrLinearBucklingWorkbenchStageV1::Imported,
            model_content_hash: model.content_hash().to_owned(),
            model_semantic_hash: model.semantic_hash().to_owned(),
            model_provenance_hash: model.provenance_hash().to_owned(),
            analysis_request_hash: request.request_hash().to_owned(),
            claim_boundary: CLAIM_BOUNDARY.to_owned(),
            session_hash: String::new(),
        };
        let session_json = canonical_session(&session)?;
        let import_receipt = canonical_self_hashed(json!({
            "schema_version": IMPORT_RECEIPT_SCHEMA_V1,
            "status": "imported",
            "session_id": session_id,
            "analysis_profile": "model_ir_linear_buckling_cpu_v1",
            "model_content_hash": model.content_hash(),
            "model_semantic_hash": model.semantic_hash(),
            "model_provenance_hash": model.provenance_hash(),
            "analysis_request_hash": request.request_hash(),
            "artifacts": [
                {
                    "file": "model-ir.json",
                    "content_hash": sha256_identity(model.canonical_bytes()),
                    "byte_length": model.canonical_bytes().len(),
                },
                {
                    "file": "model-buckling-request.json",
                    "content_hash": sha256_identity(request.canonical_bytes()),
                    "byte_length": request.canonical_bytes().len(),
                },
            ],
            "claim_boundary": CLAIM_BOUNDARY,
        }))?;
        publish_initial_workspace(
            root,
            &[
                ("model-ir.json", model.canonical_bytes()),
                ("model-buckling-request.json", request.canonical_bytes()),
            ],
            None,
            import_receipt.as_bytes(),
            session_json.as_bytes(),
        )?;
        Ok(Self {
            root: root.to_path_buf(),
            session,
        })
    }

    /// Open, verify and reconcile an atomically published buckling stage chain.
    ///
    /// # Errors
    ///
    /// Rejects session, input, preflight, product, restart, report, symlink, or stage-gap drift.
    pub fn open(root: &Path) -> Result<Self, WorkbenchError> {
        verify_directory(root, "workbench_buckling_directory_invalid")?;
        let session_bytes = read_bounded_regular_file(&root.join(SESSION_FILE), MAX_REQUEST_BYTES)?;
        let mut session = parse_session(&session_bytes)?;
        verify_import(root, &session)?;
        let discovered = discover_stage(root, &session)?;
        if session.stage > discovered {
            return Err(error(
                "workbench_buckling_session_ahead_of_artifacts",
                "the buckling session claims a stage whose atomic artifacts are absent",
            ));
        }
        session.stage = discovered;
        Ok(Self {
            root: root.to_path_buf(),
            session,
        })
    }

    #[must_use]
    pub const fn stage(&self) -> ModelIrLinearBucklingWorkbenchStageV1 {
        self.session.stage
    }

    #[must_use]
    pub fn session_id(&self) -> &str {
        &self.session.session_id
    }

    /// Return the reconciled canonical self-hashed session.
    ///
    /// # Errors
    ///
    /// Returns an invariant error if canonical serialization fails.
    pub fn session_json(&self) -> Result<String, WorkbenchError> {
        canonical_session(&self.session)
    }

    /// Return a canonical operator view without inferring engineering authority.
    ///
    /// # Errors
    ///
    /// Returns an invariant error if view serialization fails.
    pub fn inspect_json(&self) -> Result<String, WorkbenchError> {
        let stages = [
            (ModelIrLinearBucklingWorkbenchStageV1::Imported, "import"),
            (
                ModelIrLinearBucklingWorkbenchStageV1::Validated,
                "full_native_preflight",
            ),
            (ModelIrLinearBucklingWorkbenchStageV1::Direct, "direct_run"),
            (
                ModelIrLinearBucklingWorkbenchStageV1::Resumed,
                "dual_phase_checkpoint_resume",
            ),
            (
                ModelIrLinearBucklingWorkbenchStageV1::Reported,
                "localized_report",
            ),
        ];
        let workflow = stages
            .iter()
            .map(|(stage, label)| {
                json!({
                    "stage": label,
                    "state": if self.session.stage >= *stage { "complete" } else { "pending" },
                })
            })
            .collect::<Vec<_>>();
        let next_action = match self.session.stage {
            ModelIrLinearBucklingWorkbenchStageV1::Imported => "buckling-validate",
            ModelIrLinearBucklingWorkbenchStageV1::Validated => "buckling-run",
            ModelIrLinearBucklingWorkbenchStageV1::Direct => "buckling-resume",
            ModelIrLinearBucklingWorkbenchStageV1::Resumed => "buckling-report",
            ModelIrLinearBucklingWorkbenchStageV1::Reported => "complete",
        };
        canonical_hashed_json(
            json!({
                "schema_version": VIEW_SCHEMA_V1,
                "session_id": self.session.session_id,
                "analysis_profile": self.session.analysis_profile,
                "durable_stage": self.session.stage,
                "model_identity": {
                    "content_hash": self.session.model_content_hash,
                    "semantic_hash": self.session.model_semantic_hash,
                    "provenance_hash": self.session.model_provenance_hash,
                },
                "analysis_request_hash": self.session.analysis_request_hash,
                "workflow": workflow,
                "next_action": next_action,
                "external_comparison": Value::Null,
                "engineering_verdict": Value::Null,
                "claim_boundary": CLAIM_BOUNDARY,
            }),
            "view_hash",
            "workbench_buckling_view_serialization_failed",
        )
    }

    /// Execute and persist a full non-publishing reference/Kg/buckling compatibility preflight.
    ///
    /// # Errors
    ///
    /// Requires imported stage and rejects any unsupported or nonconvergent product boundary.
    pub fn validate(&mut self) -> Result<(), WorkbenchError> {
        self.require_stage(ModelIrLinearBucklingWorkbenchStageV1::Imported)?;
        let (model, request) = self.import_bytes()?;
        let compatibility = validate_model_ir_linear_buckling_analysis_compatibility(
            &model, &request,
        )
        .map_err(|value| error("workbench_buckling_validation_failed", value.to_string()))?;
        let receipt = canonical_self_hashed(json!({
            "schema_version": VALIDATION_RECEIPT_SCHEMA_V1,
            "status": "validated",
            "session_id": self.session.session_id,
            "analysis_profile": self.session.analysis_profile,
            "model_content_hash": self.session.model_content_hash,
            "model_semantic_hash": self.session.model_semantic_hash,
            "model_provenance_hash": self.session.model_provenance_hash,
            "analysis_request_hash": self.session.analysis_request_hash,
            "generated_reference_request_hash": compatibility.generated_reference_request_hash,
            "reference_assembly_hash": compatibility.reference_assembly_hash,
            "buckling_assembly_hash": compatibility.buckling_assembly_hash,
            "generated_dense_request_hash": compatibility.generated_dense_request_hash,
            "active_dof_count": compatibility.active_dof_count,
            "critical_load_factor": compatibility.critical_load_factor,
            "preflight_execution_completed": true,
            "product_publication_started": false,
            "claim_boundary": CLAIM_BOUNDARY,
        }))?;
        publish_new_directory(
            &self.root.join(VALIDATION_DIRECTORY),
            &[("validation-receipt.json", receipt.as_bytes())],
        )?;
        self.session.stage = ModelIrLinearBucklingWorkbenchStageV1::Validated;
        self.persist()
    }

    /// Execute and atomically publish the direct 18-artifact product.
    ///
    /// # Errors
    ///
    /// Requires validated stage and rejects solver, projection, view, or publication failures.
    pub fn run(&mut self) -> Result<(), WorkbenchError> {
        self.require_stage(ModelIrLinearBucklingWorkbenchStageV1::Validated)?;
        let (model, request) = self.import_bytes()?;
        let outcome =
            execute_model_ir_linear_buckling_analysis_with_checkpoint(&model, &request, None)
                .map_err(|value| error("workbench_buckling_run_failed", value.to_string()))?;
        publish_model_ir_linear_buckling_analysis(&self.root.join(DIRECT_DIRECTORY), &outcome)
            .map_err(|value| error("workbench_buckling_run_publish_failed", value.to_string()))?;
        verify_product_directory(&self.root.join(DIRECT_DIRECTORY))?;
        self.session.stage = ModelIrLinearBucklingWorkbenchStageV1::Direct;
        self.persist()
    }

    /// Resume both product phases and publish only after exact direct/resumed byte equivalence.
    ///
    /// # Errors
    ///
    /// Requires direct stage and rejects checkpoint binding, determinism, or I/O drift.
    pub fn resume(&mut self) -> Result<(), WorkbenchError> {
        self.require_stage(ModelIrLinearBucklingWorkbenchStageV1::Direct)?;
        let (model, request) = self.import_bytes()?;
        let checkpoint = read_bounded_regular_file(
            &self.root.join(DIRECT_DIRECTORY).join("checkpoint.mbcp"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let outcome = execute_model_ir_linear_buckling_analysis_with_checkpoint(
            &model,
            &request,
            Some(&checkpoint),
        )
        .map_err(|value| error("workbench_buckling_resume_failed", value.to_string()))?;
        let destination = self.root.join(RESUME_DIRECTORY);
        let temporary = temporary_path(&self.root, RESUME_DIRECTORY);
        let result = (|| {
            publish_model_ir_linear_buckling_analysis(&temporary, &outcome).map_err(|value| {
                error(
                    "workbench_buckling_resume_publish_failed",
                    value.to_string(),
                )
            })?;
            verify_product_directory(&temporary)?;
            verify_product_equivalence(&self.root.join(DIRECT_DIRECTORY), &temporary)?;
            if destination.exists() {
                return Err(error(
                    "workbench_buckling_stage_destination_exists",
                    "buckling resume stage already exists",
                ));
            }
            fs::rename(&temporary, &destination).map_err(|value| {
                error(
                    "workbench_buckling_io_error",
                    format!("publish buckling resume stage failed: {value}"),
                )
            })?;
            sync_directory(&self.root, "sync buckling Workbench root")
        })();
        if result.is_err() {
            let _ignored = fs::remove_dir_all(&temporary);
        }
        result?;
        self.session.stage = ModelIrLinearBucklingWorkbenchStageV1::Resumed;
        self.persist()
    }

    /// Publish deterministic English and Korean read-only factor views.
    ///
    /// # Errors
    ///
    /// Requires an exact resumed product and rejects view or publication drift.
    pub fn report(&mut self) -> Result<(), WorkbenchError> {
        self.require_stage(ModelIrLinearBucklingWorkbenchStageV1::Resumed)?;
        let result = self.root.join(RESUME_DIRECTORY);
        let english = render_model_ir_linear_buckling_result_view_directory(
            &result,
            WorkbenchReportLocaleV1::EnUs,
            1,
            128,
        )?;
        let korean = render_model_ir_linear_buckling_result_view_directory(
            &result,
            WorkbenchReportLocaleV1::KoKr,
            1,
            128,
        )?;
        let receipt = canonical_self_hashed(json!({
            "schema_version": REPORT_RECEIPT_SCHEMA_V1,
            "status": "reported",
            "session_id": self.session.session_id,
            "analysis_profile": self.session.analysis_profile,
            "source_result_hash": sha256_identity(&read_bounded_regular_file(
                &result.join("result-ir.json"), MAX_PRODUCT_ARTIFACT_BYTES)?),
            "source_checkpoint_hash": sha256_identity(&read_bounded_regular_file(
                &result.join("checkpoint.mbcp"), MAX_PRODUCT_ARTIFACT_BYTES)?),
            "english_view_hash": sha256_identity(english.as_bytes()),
            "korean_view_hash": sha256_identity(korean.as_bytes()),
            "external_comparison": Value::Null,
            "engineering_verdict": Value::Null,
            "claim_boundary": CLAIM_BOUNDARY,
        }))?;
        publish_new_directory(
            &self.root.join(REPORT_DIRECTORY),
            &[
                ("buckling-result-view.en-US.txt", english.as_bytes()),
                ("buckling-result-view.ko-KR.txt", korean.as_bytes()),
                ("report-receipt.json", receipt.as_bytes()),
            ],
        )?;
        self.session.stage = ModelIrLinearBucklingWorkbenchStageV1::Reported;
        self.persist()
    }

    fn import_bytes(&self) -> Result<(Vec<u8>, Vec<u8>), WorkbenchError> {
        Ok((
            read_bounded_regular_file(
                &self.root.join(IMPORT_DIRECTORY).join("model-ir.json"),
                MAX_MODEL_BYTES,
            )?,
            read_bounded_regular_file(
                &self
                    .root
                    .join(IMPORT_DIRECTORY)
                    .join("model-buckling-request.json"),
                MAX_REQUEST_BYTES,
            )?,
        ))
    }

    fn require_stage(
        &self,
        required: ModelIrLinearBucklingWorkbenchStageV1,
    ) -> Result<(), WorkbenchError> {
        if self.session.stage != required {
            return Err(error(
                "workbench_buckling_stage_invalid",
                format!(
                    "buckling command requires stage {} but session is {}",
                    required.label(),
                    self.session.stage.label()
                ),
            ));
        }
        Ok(())
    }

    fn persist(&self) -> Result<(), WorkbenchError> {
        let bytes = canonical_session(&self.session)?;
        write_atomic_file(&self.root.join(SESSION_FILE), bytes.as_bytes())
    }
}

fn canonical_session(
    session: &ModelIrLinearBucklingWorkbenchSessionV1,
) -> Result<String, WorkbenchError> {
    let value = serde_json::to_value(session).map_err(|value| {
        error(
            "workbench_buckling_session_serialization_failed",
            value.to_string(),
        )
    })?;
    canonical_hashed_json(
        value,
        "session_hash",
        "workbench_buckling_session_serialization_failed",
    )
}

fn parse_session(bytes: &[u8]) -> Result<ModelIrLinearBucklingWorkbenchSessionV1, WorkbenchError> {
    let value = verify_self_hashed_json(bytes, "session_hash")?;
    let session: ModelIrLinearBucklingWorkbenchSessionV1 = serde_json::from_value(value)
        .map_err(|value| error("workbench_buckling_session_invalid", value.to_string()))?;
    if session.schema_version != SESSION_SCHEMA_V1
        || session.analysis_profile != "model_ir_linear_buckling_cpu_v1"
        || session.claim_boundary != CLAIM_BOUNDARY
        || canonical_session(&session)?.as_bytes() != bytes
    {
        return Err(error(
            "workbench_buckling_session_invalid",
            "buckling session schema, profile, boundary, or canonical bytes are invalid",
        ));
    }
    Ok(session)
}

fn verify_import(
    root: &Path,
    session: &ModelIrLinearBucklingWorkbenchSessionV1,
) -> Result<(), WorkbenchError> {
    let directory = root.join(IMPORT_DIRECTORY);
    verify_inventory(
        &directory,
        &[
            "import-receipt.json",
            "model-buckling-request.json",
            "model-ir.json",
        ],
    )?;
    let model_bytes = read_bounded_regular_file(&directory.join("model-ir.json"), MAX_MODEL_BYTES)?;
    let request_bytes = read_bounded_regular_file(
        &directory.join("model-buckling-request.json"),
        MAX_REQUEST_BYTES,
    )?;
    let model = parse_model_ir_v2(&model_bytes)
        .map_err(|value| error("workbench_buckling_model_invalid", value.to_string()))?;
    let request = parse_model_ir_linear_buckling_analysis_request_v1(&request_bytes)
        .map_err(|value| error("workbench_buckling_request_invalid", value.to_string()))?;
    verify_request_identity(&model, &request)?;
    let receipt = verify_self_hashed_json(
        &read_bounded_regular_file(&directory.join("import-receipt.json"), MAX_REQUEST_BYTES)?,
        "receipt_hash",
    )?;
    let expected_session_id = sha256_identity(
        format!(
            "model-ir-linear-buckling-workbench.v1|{}|{}",
            model.content_hash(),
            request.request_hash()
        )
        .as_bytes(),
    );
    if string_field(&receipt, "schema_version")? != IMPORT_RECEIPT_SCHEMA_V1
        || string_field(&receipt, "status")? != "imported"
        || string_field(&receipt, "session_id")? != session.session_id
        || string_field(&receipt, "analysis_profile")? != "model_ir_linear_buckling_cpu_v1"
        || string_field(&receipt, "model_content_hash")? != model.content_hash()
        || string_field(&receipt, "model_semantic_hash")? != model.semantic_hash()
        || string_field(&receipt, "model_provenance_hash")? != model.provenance_hash()
        || string_field(&receipt, "analysis_request_hash")? != request.request_hash()
        || string_field(&receipt, "claim_boundary")? != CLAIM_BOUNDARY
        || session.session_id != expected_session_id
        || session.model_content_hash != model.content_hash()
        || session.model_semantic_hash != model.semantic_hash()
        || session.model_provenance_hash != model.provenance_hash()
        || session.analysis_request_hash != request.request_hash()
    {
        return Err(error(
            "workbench_buckling_import_binding_mismatch",
            "buckling session, import receipt, model, and request identities do not match",
        ));
    }
    verify_import_artifacts(&receipt, &model_bytes, &request_bytes)
}

fn verify_import_artifacts(
    receipt: &Value,
    model: &[u8],
    request: &[u8],
) -> Result<(), WorkbenchError> {
    let rows = receipt
        .get("artifacts")
        .and_then(Value::as_array)
        .ok_or_else(|| {
            error(
                "workbench_buckling_import_receipt_invalid",
                "artifact rows are missing",
            )
        })?;
    let expected = [
        ("model-ir.json", model),
        ("model-buckling-request.json", request),
    ];
    if rows.len() != expected.len() {
        return Err(error(
            "workbench_buckling_import_receipt_invalid",
            "import receipt must bind exactly two artifacts",
        ));
    }
    for (row, (file, bytes)) in rows.iter().zip(expected) {
        if string_field(row, "file")? != file
            || string_field(row, "content_hash")? != sha256_identity(bytes)
            || row.get("byte_length").and_then(Value::as_u64) != u64::try_from(bytes.len()).ok()
        {
            return Err(error(
                "workbench_buckling_import_binding_mismatch",
                "import receipt artifact identity does not match canonical bytes",
            ));
        }
    }
    Ok(())
}

fn discover_stage(
    root: &Path,
    session: &ModelIrLinearBucklingWorkbenchSessionV1,
) -> Result<ModelIrLinearBucklingWorkbenchStageV1, WorkbenchError> {
    match fs::symlink_metadata(root.join("05-compare")) {
        Ok(_) => {
            return Err(error(
                "workbench_buckling_external_comparison_unsupported",
                "the bounded buckling Workbench has no external comparison stage",
            ))
        }
        Err(value) if value.kind() == std::io::ErrorKind::NotFound => {}
        Err(value) => {
            return Err(error(
                "workbench_buckling_io_error",
                format!("inspect unsupported comparison stage failed: {value}"),
            ))
        }
    }
    let stages = [
        (
            ModelIrLinearBucklingWorkbenchStageV1::Validated,
            VALIDATION_DIRECTORY,
        ),
        (
            ModelIrLinearBucklingWorkbenchStageV1::Direct,
            DIRECT_DIRECTORY,
        ),
        (
            ModelIrLinearBucklingWorkbenchStageV1::Resumed,
            RESUME_DIRECTORY,
        ),
        (
            ModelIrLinearBucklingWorkbenchStageV1::Reported,
            REPORT_DIRECTORY,
        ),
    ];
    let mut discovered = ModelIrLinearBucklingWorkbenchStageV1::Imported;
    let mut gap = false;
    for (stage, name) in stages {
        let path = root.join(name);
        match fs::symlink_metadata(&path) {
            Ok(_) if gap => {
                return Err(error(
                    "workbench_buckling_stage_gap",
                    format!("buckling stage {name} exists after a missing predecessor"),
                ))
            }
            Ok(_) => {
                match stage {
                    ModelIrLinearBucklingWorkbenchStageV1::Validated => {
                        verify_validation(root, session)?;
                    }
                    ModelIrLinearBucklingWorkbenchStageV1::Direct => {
                        verify_product_directory(&path)?;
                    }
                    ModelIrLinearBucklingWorkbenchStageV1::Resumed => {
                        verify_product_directory(&path)?;
                        verify_product_equivalence(&root.join(DIRECT_DIRECTORY), &path)?;
                    }
                    ModelIrLinearBucklingWorkbenchStageV1::Reported => {
                        verify_report(root, session)?;
                    }
                    ModelIrLinearBucklingWorkbenchStageV1::Imported => unreachable!(),
                }
                discovered = stage;
            }
            Err(value) if value.kind() == std::io::ErrorKind::NotFound => gap = true,
            Err(value) => {
                return Err(error(
                    "workbench_buckling_io_error",
                    format!("inspect buckling stage failed: {value}"),
                ))
            }
        }
    }
    Ok(discovered)
}

fn verify_validation(
    root: &Path,
    session: &ModelIrLinearBucklingWorkbenchSessionV1,
) -> Result<(), WorkbenchError> {
    let directory = root.join(VALIDATION_DIRECTORY);
    verify_inventory(&directory, &["validation-receipt.json"])?;
    let receipt = verify_self_hashed_json(
        &read_bounded_regular_file(
            &directory.join("validation-receipt.json"),
            MAX_REQUEST_BYTES,
        )?,
        "receipt_hash",
    )?;
    let model = read_bounded_regular_file(
        &root.join(IMPORT_DIRECTORY).join("model-ir.json"),
        MAX_MODEL_BYTES,
    )?;
    let request = read_bounded_regular_file(
        &root
            .join(IMPORT_DIRECTORY)
            .join("model-buckling-request.json"),
        MAX_REQUEST_BYTES,
    )?;
    let compatibility = validate_model_ir_linear_buckling_analysis_compatibility(&model, &request)
        .map_err(|value| error("workbench_buckling_validation_failed", value.to_string()))?;
    if string_field(&receipt, "schema_version")? != VALIDATION_RECEIPT_SCHEMA_V1
        || string_field(&receipt, "status")? != "validated"
        || string_field(&receipt, "session_id")? != session.session_id
        || string_field(&receipt, "analysis_profile")? != "model_ir_linear_buckling_cpu_v1"
        || string_field(&receipt, "model_content_hash")? != session.model_content_hash
        || string_field(&receipt, "model_semantic_hash")? != session.model_semantic_hash
        || string_field(&receipt, "model_provenance_hash")? != session.model_provenance_hash
        || string_field(&receipt, "analysis_request_hash")? != session.analysis_request_hash
        || string_field(&receipt, "generated_reference_request_hash")?
            != compatibility.generated_reference_request_hash
        || string_field(&receipt, "reference_assembly_hash")?
            != compatibility.reference_assembly_hash
        || string_field(&receipt, "buckling_assembly_hash")? != compatibility.buckling_assembly_hash
        || string_field(&receipt, "generated_dense_request_hash")?
            != compatibility.generated_dense_request_hash
        || receipt.get("active_dof_count").and_then(Value::as_u64)
            != Some(u64::from(compatibility.active_dof_count))
        || receipt
            .get("critical_load_factor")
            .and_then(Value::as_f64)
            .map(f64::to_bits)
            != Some(compatibility.critical_load_factor.to_bits())
        || receipt
            .get("preflight_execution_completed")
            .and_then(Value::as_bool)
            != Some(true)
        || receipt
            .get("product_publication_started")
            .and_then(Value::as_bool)
            != Some(false)
        || string_field(&receipt, "claim_boundary")? != CLAIM_BOUNDARY
    {
        return Err(error(
            "workbench_buckling_validation_binding_mismatch",
            "buckling validation receipt does not match the reconstructed native preflight",
        ));
    }
    Ok(())
}

fn verify_product_directory(directory: &Path) -> Result<(), WorkbenchError> {
    render_model_ir_linear_buckling_result_view_directory(
        directory,
        WorkbenchReportLocaleV1::EnUs,
        1,
        1,
    )
    .map(|_| ())
}

fn verify_product_equivalence(left: &Path, right: &Path) -> Result<(), WorkbenchError> {
    for name in BUCKLING_PRODUCT_FILES {
        let left = read_bounded_regular_file(&left.join(name), MAX_PRODUCT_ARTIFACT_BYTES)?;
        let right = read_bounded_regular_file(&right.join(name), MAX_PRODUCT_ARTIFACT_BYTES)?;
        if left != right {
            return Err(error(
                "workbench_buckling_restart_determinism_mismatch",
                format!("direct and resumed buckling artifact bytes differ for {name}"),
            ));
        }
    }
    Ok(())
}

fn verify_report(
    root: &Path,
    session: &ModelIrLinearBucklingWorkbenchSessionV1,
) -> Result<(), WorkbenchError> {
    let directory = root.join(REPORT_DIRECTORY);
    verify_inventory(
        &directory,
        &[
            "buckling-result-view.en-US.txt",
            "buckling-result-view.ko-KR.txt",
            "report-receipt.json",
        ],
    )?;
    let result = root.join(RESUME_DIRECTORY);
    let expected_english = render_model_ir_linear_buckling_result_view_directory(
        &result,
        WorkbenchReportLocaleV1::EnUs,
        1,
        128,
    )?;
    let expected_korean = render_model_ir_linear_buckling_result_view_directory(
        &result,
        WorkbenchReportLocaleV1::KoKr,
        1,
        128,
    )?;
    let english = read_bounded_regular_file(
        &directory.join("buckling-result-view.en-US.txt"),
        MAX_REQUEST_BYTES,
    )?;
    let korean = read_bounded_regular_file(
        &directory.join("buckling-result-view.ko-KR.txt"),
        MAX_REQUEST_BYTES,
    )?;
    let receipt = verify_self_hashed_json(
        &read_bounded_regular_file(&directory.join("report-receipt.json"), MAX_REQUEST_BYTES)?,
        "receipt_hash",
    )?;
    if english != expected_english.as_bytes()
        || korean != expected_korean.as_bytes()
        || string_field(&receipt, "schema_version")? != REPORT_RECEIPT_SCHEMA_V1
        || string_field(&receipt, "status")? != "reported"
        || string_field(&receipt, "session_id")? != session.session_id
        || string_field(&receipt, "analysis_profile")? != "model_ir_linear_buckling_cpu_v1"
        || string_field(&receipt, "english_view_hash")? != sha256_identity(&english)
        || string_field(&receipt, "korean_view_hash")? != sha256_identity(&korean)
        || string_field(&receipt, "source_result_hash")?
            != sha256_identity(&read_bounded_regular_file(
                &result.join("result-ir.json"),
                MAX_PRODUCT_ARTIFACT_BYTES,
            )?)
        || string_field(&receipt, "source_checkpoint_hash")?
            != sha256_identity(&read_bounded_regular_file(
                &result.join("checkpoint.mbcp"),
                MAX_PRODUCT_ARTIFACT_BYTES,
            )?)
        || !receipt
            .get("external_comparison")
            .is_some_and(Value::is_null)
        || !receipt
            .get("engineering_verdict")
            .is_some_and(Value::is_null)
        || string_field(&receipt, "claim_boundary")? != CLAIM_BOUNDARY
    {
        return Err(error(
            "workbench_buckling_report_binding_mismatch",
            "buckling report views or receipt do not match the resumed product",
        ));
    }
    Ok(())
}

fn verify_request_identity(
    model: &ModelIrV2Document,
    request: &ModelIrLinearBucklingAnalysisRequestDocumentV1,
) -> Result<(), WorkbenchError> {
    let identity = &request.request().model_identity;
    if identity.content_hash != model.content_hash()
        || identity.semantic_hash != model.semantic_hash()
        || identity.provenance_hash != model.provenance_hash()
    {
        return Err(error(
            "workbench_buckling_model_identity_mismatch",
            "buckling request model identity does not match the canonical ModelIR",
        ));
    }
    Ok(())
}

fn verify_inventory(directory: &Path, expected: &[&str]) -> Result<(), WorkbenchError> {
    verify_directory(directory, "workbench_buckling_stage_directory_invalid")?;
    let mut actual = BTreeSet::new();
    for entry in fs::read_dir(directory).map_err(|value| {
        error(
            "workbench_buckling_io_error",
            format!("read buckling stage directory failed: {value}"),
        )
    })? {
        let entry = entry.map_err(|value| {
            error(
                "workbench_buckling_io_error",
                format!("read buckling stage entry failed: {value}"),
            )
        })?;
        let name = entry.file_name().into_string().map_err(|_| {
            error(
                "workbench_buckling_stage_inventory_invalid",
                "buckling stage artifact name is not valid UTF-8",
            )
        })?;
        actual.insert(name);
    }
    let expected = expected
        .iter()
        .map(|value| (*value).to_owned())
        .collect::<BTreeSet<_>>();
    if actual != expected {
        return Err(error(
            "workbench_buckling_stage_inventory_invalid",
            "buckling stage inventory is missing, extra, or duplicated",
        ));
    }
    Ok(())
}

fn string_field<'a>(value: &'a Value, name: &str) -> Result<&'a str, WorkbenchError> {
    value.get(name).and_then(Value::as_str).ok_or_else(|| {
        error(
            "workbench_buckling_receipt_invalid",
            format!("receipt field {name} is missing or invalid"),
        )
    })
}

fn error(code: &'static str, detail: impl Into<String>) -> WorkbenchError {
    WorkbenchError::new(code, detail)
}
