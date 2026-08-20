use std::collections::BTreeSet;
use std::fs;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use structural_cli::{
    execute_model_ir_modal_analysis_with_checkpoint, publish_model_ir_modal_analysis,
    validate_model_ir_modal_analysis_compatibility,
};
use structural_contracts::model_ir::parse_model_ir_v2;
use structural_contracts::model_modal_product::parse_model_ir_modal_analysis_request_v1;
use structural_contracts::product_ir::sha256_identity;

use crate::{
    canonical_hashed_json, canonical_self_hashed, output_parent, publish_initial_workspace,
    publish_new_directory, read_bounded_regular_file, render_model_ir_modal_result_view_directory,
    sync_directory, temporary_path, verify_directory, verify_self_hashed_json, verify_slice_bound,
    write_atomic_file, WorkbenchError, WorkbenchReportLocaleV1, MAX_MODEL_BYTES,
    MAX_PRODUCT_ARTIFACT_BYTES, MAX_REQUEST_BYTES, SESSION_FILE,
};

const SESSION_SCHEMA_V1: &str = "structural-native-model-ir-modal-workbench-session.v1";
const IMPORT_RECEIPT_SCHEMA_V1: &str =
    "structural-native-model-ir-modal-workbench-import-receipt.v1";
const VALIDATION_RECEIPT_SCHEMA_V1: &str =
    "structural-native-model-ir-modal-workbench-validation-receipt.v1";
const REPORT_RECEIPT_SCHEMA_V1: &str =
    "structural-native-model-ir-modal-workbench-report-receipt.v1";
const VIEW_SCHEMA_V1: &str = "structural-native-model-ir-modal-workbench-view.v1";
const IMPORT_DIRECTORY: &str = "01-import";
const VALIDATION_DIRECTORY: &str = "02-validate";
const DIRECT_DIRECTORY: &str = "03-run";
const RESUME_DIRECTORY: &str = "04-resume";
const REPORT_DIRECTORY: &str = "06-report";
const CLAIM_BOUNDARY: &str = "bounded_durable_modelir_frame3d_truss3d_cpu_modal_import_validation_direct_execution_model_bound_checkpoint_restart_and_read_only_localized_mode_report_not_external_parity_engineering_acceptance_response_spectrum_buckling_shell_sparse_or_c6";
const PRODUCT_FILES: [&str; 11] = [
    "assembly-receipt.json",
    "checkpoint.eigcp",
    "checkpoint.mmcp",
    "dense-run-receipt.json",
    "generated-dense-request.json",
    "model-ir.json",
    "model-modal-request.json",
    "report-ir.json",
    "report.md",
    "result-ir.json",
    "run-receipt.json",
];

/// Ordered stages for the modal-only durable Workbench profile.
#[derive(Clone, Copy, Debug, Deserialize, Eq, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ModelIrModalWorkbenchStageV1 {
    Imported,
    Validated,
    Direct,
    Resumed,
    Reported,
}

impl ModelIrModalWorkbenchStageV1 {
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
struct ModelIrModalWorkbenchSessionV1 {
    schema_version: String,
    session_id: String,
    analysis_profile: String,
    stage: ModelIrModalWorkbenchStageV1,
    model_content_hash: String,
    model_semantic_hash: String,
    model_provenance_hash: String,
    analysis_request_hash: String,
    claim_boundary: String,
    session_hash: String,
}

/// Durable modal controller that calls the Rust product libraries directly.
#[derive(Debug)]
pub struct ModelIrModalWorkbench {
    root: PathBuf,
    session: ModelIrModalWorkbenchSessionV1,
}

impl ModelIrModalWorkbench {
    /// Initialize a new modal Workbench from bounded non-symlink input paths.
    ///
    /// # Errors
    ///
    /// Rejects unsafe paths, invalid identities, existing destinations, and publication failures.
    pub fn initialize_from_paths(
        root: &Path,
        model_path: &Path,
        request_path: &Path,
    ) -> Result<Self, WorkbenchError> {
        let model = read_bounded_regular_file(model_path, MAX_MODEL_BYTES)?;
        let request = read_bounded_regular_file(request_path, MAX_REQUEST_BYTES)?;
        Self::initialize(root, &model, &request)
    }

    /// Initialize a new modal Workbench from bounded in-memory inputs.
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
                "workbench_modal_destination_exists",
                "the modal Workbench directory must not already exist",
            ));
        }
        verify_slice_bound(model_bytes, MAX_MODEL_BYTES, "modal ModelIR")?;
        verify_slice_bound(request_bytes, MAX_REQUEST_BYTES, "modal analysis request")?;
        verify_directory(output_parent(root), "workbench_modal_output_parent_invalid")?;

        let model = parse_model_ir_v2(model_bytes)
            .map_err(|value| error("workbench_modal_model_invalid", value.to_string()))?;
        let request = parse_model_ir_modal_analysis_request_v1(request_bytes)
            .map_err(|value| error("workbench_modal_request_invalid", value.to_string()))?;
        verify_request_identity(&model, &request)?;
        let session_id = sha256_identity(
            format!(
                "model-ir-modal-workbench.v1|{}|{}",
                model.content_hash(),
                request.request_hash()
            )
            .as_bytes(),
        );
        let session = ModelIrModalWorkbenchSessionV1 {
            schema_version: SESSION_SCHEMA_V1.to_owned(),
            session_id: session_id.clone(),
            analysis_profile: "model_ir_modal_cpu_v1".to_owned(),
            stage: ModelIrModalWorkbenchStageV1::Imported,
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
            "analysis_profile": "model_ir_modal_cpu_v1",
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
                    "file": "model-modal-request.json",
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
                ("model-modal-request.json", request.canonical_bytes()),
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

    /// Open, verify, and reconcile an atomically published modal stage chain.
    ///
    /// # Errors
    ///
    /// Rejects session, input, receipt, product, restart, report, symlink, or stage-gap drift.
    pub fn open(root: &Path) -> Result<Self, WorkbenchError> {
        verify_directory(root, "workbench_modal_directory_invalid")?;
        let session_bytes = read_bounded_regular_file(&root.join(SESSION_FILE), MAX_REQUEST_BYTES)?;
        let mut session = parse_session(&session_bytes)?;
        verify_import(root, &session)?;
        let discovered = discover_stage(root, &session)?;
        if session.stage > discovered {
            return Err(error(
                "workbench_modal_session_ahead_of_artifacts",
                "the modal session claims a stage whose atomic artifacts are absent",
            ));
        }
        session.stage = discovered;
        Ok(Self {
            root: root.to_path_buf(),
            session,
        })
    }

    #[must_use]
    pub const fn stage(&self) -> ModelIrModalWorkbenchStageV1 {
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

    /// Return a canonical operator view without inferring an engineering verdict.
    ///
    /// # Errors
    ///
    /// Returns an invariant error if view serialization fails.
    pub fn inspect_json(&self) -> Result<String, WorkbenchError> {
        let stages = [
            (ModelIrModalWorkbenchStageV1::Imported, "import"),
            (ModelIrModalWorkbenchStageV1::Validated, "validate"),
            (ModelIrModalWorkbenchStageV1::Direct, "direct_run"),
            (ModelIrModalWorkbenchStageV1::Resumed, "checkpoint_resume"),
            (ModelIrModalWorkbenchStageV1::Reported, "localized_report"),
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
            ModelIrModalWorkbenchStageV1::Imported => "modal-validate",
            ModelIrModalWorkbenchStageV1::Validated => "modal-run",
            ModelIrModalWorkbenchStageV1::Direct => "modal-resume",
            ModelIrModalWorkbenchStageV1::Resumed => "modal-report",
            ModelIrModalWorkbenchStageV1::Reported => "complete",
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
            "workbench_modal_view_serialization_failed",
        )
    }

    /// Validate native modal assembly compatibility and publish its immutable receipt.
    ///
    /// # Errors
    ///
    /// Requires the imported stage and rejects unsupported model/request assembly surfaces.
    pub fn validate(&mut self) -> Result<(), WorkbenchError> {
        self.require_stage(ModelIrModalWorkbenchStageV1::Imported)?;
        let (model, request) = self.import_bytes()?;
        let compatibility = validate_model_ir_modal_analysis_compatibility(&model, &request)
            .map_err(|value| error("workbench_modal_validation_failed", value.to_string()))?;
        let receipt = canonical_self_hashed(json!({
            "schema_version": VALIDATION_RECEIPT_SCHEMA_V1,
            "status": "validated",
            "session_id": self.session.session_id,
            "analysis_profile": self.session.analysis_profile,
            "model_content_hash": self.session.model_content_hash,
            "model_semantic_hash": self.session.model_semantic_hash,
            "model_provenance_hash": self.session.model_provenance_hash,
            "analysis_request_hash": self.session.analysis_request_hash,
            "assembly_hash": compatibility.assembly_hash,
            "generated_dense_request_hash": compatibility.generated_dense_request_hash,
            "active_dof_count": compatibility.active_dof_count,
            "claim_boundary": CLAIM_BOUNDARY,
        }))?;
        publish_new_directory(
            &self.root.join(VALIDATION_DIRECTORY),
            &[("validation-receipt.json", receipt.as_bytes())],
        )?;
        self.session.stage = ModelIrModalWorkbenchStageV1::Validated;
        self.persist()
    }

    /// Execute and atomically publish the direct modal product and its model-bound checkpoint.
    ///
    /// # Errors
    ///
    /// Requires the validated stage and rejects solver, projection, or publication failures.
    pub fn run(&mut self) -> Result<(), WorkbenchError> {
        self.require_stage(ModelIrModalWorkbenchStageV1::Validated)?;
        let (model, request) = self.import_bytes()?;
        let outcome = execute_model_ir_modal_analysis_with_checkpoint(&model, &request, None)
            .map_err(|value| error("workbench_modal_run_failed", value.to_string()))?;
        publish_model_ir_modal_analysis(&self.root.join(DIRECT_DIRECTORY), &outcome)
            .map_err(|value| error("workbench_modal_run_publish_failed", value.to_string()))?;
        render_model_ir_modal_result_view_directory(
            &self.root.join(DIRECT_DIRECTORY),
            WorkbenchReportLocaleV1::EnUs,
            1,
            1,
        )?;
        self.session.stage = ModelIrModalWorkbenchStageV1::Direct;
        self.persist()
    }

    /// Resume from the direct product checkpoint and publish only after exact byte equivalence.
    ///
    /// # Errors
    ///
    /// Requires the direct stage and rejects checkpoint binding, artifact, determinism, or I/O drift.
    pub fn resume(&mut self) -> Result<(), WorkbenchError> {
        self.require_stage(ModelIrModalWorkbenchStageV1::Direct)?;
        let (model, request) = self.import_bytes()?;
        let checkpoint = read_bounded_regular_file(
            &self.root.join(DIRECT_DIRECTORY).join("checkpoint.mmcp"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let outcome =
            execute_model_ir_modal_analysis_with_checkpoint(&model, &request, Some(&checkpoint))
                .map_err(|value| error("workbench_modal_resume_failed", value.to_string()))?;
        let destination = self.root.join(RESUME_DIRECTORY);
        let temporary = temporary_path(&self.root, RESUME_DIRECTORY);
        let result = (|| {
            publish_model_ir_modal_analysis(&temporary, &outcome).map_err(|value| {
                error("workbench_modal_resume_publish_failed", value.to_string())
            })?;
            render_model_ir_modal_result_view_directory(
                &temporary,
                WorkbenchReportLocaleV1::EnUs,
                1,
                1,
            )?;
            verify_product_equivalence(&self.root.join(DIRECT_DIRECTORY), &temporary)?;
            if destination.exists() {
                return Err(error(
                    "workbench_modal_stage_destination_exists",
                    "modal resume stage already exists",
                ));
            }
            fs::rename(&temporary, &destination).map_err(|value| {
                error(
                    "workbench_modal_io_error",
                    format!("publish modal resume stage failed: {value}"),
                )
            })?;
            sync_directory(&self.root, "sync modal Workbench root")
        })();
        if result.is_err() {
            let _ignored = fs::remove_dir_all(&temporary);
        }
        result?;
        self.session.stage = ModelIrModalWorkbenchStageV1::Resumed;
        self.persist()
    }

    /// Publish deterministic English and Korean read-only result views.
    ///
    /// # Errors
    ///
    /// Requires an exact resumed product and rejects result or publication drift.
    pub fn report(&mut self) -> Result<(), WorkbenchError> {
        self.require_stage(ModelIrModalWorkbenchStageV1::Resumed)?;
        let result = self.root.join(RESUME_DIRECTORY);
        let english = render_model_ir_modal_result_view_directory(
            &result,
            WorkbenchReportLocaleV1::EnUs,
            1,
            128,
        )?;
        let korean = render_model_ir_modal_result_view_directory(
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
                &result.join("checkpoint.mmcp"), MAX_PRODUCT_ARTIFACT_BYTES)?),
            "english_view_hash": sha256_identity(english.as_bytes()),
            "korean_view_hash": sha256_identity(korean.as_bytes()),
            "external_comparison": Value::Null,
            "engineering_verdict": Value::Null,
            "claim_boundary": CLAIM_BOUNDARY,
        }))?;
        publish_new_directory(
            &self.root.join(REPORT_DIRECTORY),
            &[
                ("modal-result-view.en-US.txt", english.as_bytes()),
                ("modal-result-view.ko-KR.txt", korean.as_bytes()),
                ("report-receipt.json", receipt.as_bytes()),
            ],
        )?;
        self.session.stage = ModelIrModalWorkbenchStageV1::Reported;
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
                    .join("model-modal-request.json"),
                MAX_REQUEST_BYTES,
            )?,
        ))
    }

    fn require_stage(&self, required: ModelIrModalWorkbenchStageV1) -> Result<(), WorkbenchError> {
        if self.session.stage != required {
            return Err(error(
                "workbench_modal_stage_invalid",
                format!(
                    "modal command requires stage {} but session is {}",
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

fn canonical_session(session: &ModelIrModalWorkbenchSessionV1) -> Result<String, WorkbenchError> {
    let value = serde_json::to_value(session).map_err(|value| {
        error(
            "workbench_modal_session_serialization_failed",
            value.to_string(),
        )
    })?;
    canonical_hashed_json(
        value,
        "session_hash",
        "workbench_modal_session_serialization_failed",
    )
}

fn parse_session(bytes: &[u8]) -> Result<ModelIrModalWorkbenchSessionV1, WorkbenchError> {
    let value = verify_self_hashed_json(bytes, "session_hash")?;
    let session: ModelIrModalWorkbenchSessionV1 = serde_json::from_value(value)
        .map_err(|value| error("workbench_modal_session_invalid", value.to_string()))?;
    if session.schema_version != SESSION_SCHEMA_V1
        || session.analysis_profile != "model_ir_modal_cpu_v1"
        || session.claim_boundary != CLAIM_BOUNDARY
        || canonical_session(&session)?.as_bytes() != bytes
    {
        return Err(error(
            "workbench_modal_session_invalid",
            "modal Workbench session schema, profile, boundary, or canonical bytes are invalid",
        ));
    }
    Ok(session)
}

fn verify_import(
    root: &Path,
    session: &ModelIrModalWorkbenchSessionV1,
) -> Result<(), WorkbenchError> {
    let directory = root.join(IMPORT_DIRECTORY);
    verify_inventory(
        &directory,
        &[
            "import-receipt.json",
            "model-ir.json",
            "model-modal-request.json",
        ],
    )?;
    let model_bytes = read_bounded_regular_file(&directory.join("model-ir.json"), MAX_MODEL_BYTES)?;
    let request_bytes = read_bounded_regular_file(
        &directory.join("model-modal-request.json"),
        MAX_REQUEST_BYTES,
    )?;
    let model = parse_model_ir_v2(&model_bytes)
        .map_err(|value| error("workbench_modal_model_invalid", value.to_string()))?;
    let request = parse_model_ir_modal_analysis_request_v1(&request_bytes)
        .map_err(|value| error("workbench_modal_request_invalid", value.to_string()))?;
    verify_request_identity(&model, &request)?;
    let receipt_bytes =
        read_bounded_regular_file(&directory.join("import-receipt.json"), MAX_REQUEST_BYTES)?;
    let receipt = verify_self_hashed_json(&receipt_bytes, "receipt_hash")?;
    let expected_session_id = sha256_identity(
        format!(
            "model-ir-modal-workbench.v1|{}|{}",
            model.content_hash(),
            request.request_hash()
        )
        .as_bytes(),
    );
    if string_field(&receipt, "schema_version")? != IMPORT_RECEIPT_SCHEMA_V1
        || string_field(&receipt, "status")? != "imported"
        || string_field(&receipt, "session_id")? != session.session_id
        || string_field(&receipt, "analysis_profile")? != "model_ir_modal_cpu_v1"
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
            "workbench_modal_import_binding_mismatch",
            "modal session, import receipt, model, and request identities do not match",
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
                "workbench_modal_import_receipt_invalid",
                "artifact rows are missing",
            )
        })?;
    let expected = [
        ("model-ir.json", model),
        ("model-modal-request.json", request),
    ];
    if rows.len() != expected.len() {
        return Err(error(
            "workbench_modal_import_receipt_invalid",
            "import receipt must bind exactly two artifacts",
        ));
    }
    for (row, (file, bytes)) in rows.iter().zip(expected) {
        if string_field(row, "file")? != file
            || string_field(row, "content_hash")? != sha256_identity(bytes)
            || row.get("byte_length").and_then(Value::as_u64) != u64::try_from(bytes.len()).ok()
        {
            return Err(error(
                "workbench_modal_import_binding_mismatch",
                "import receipt artifact identity does not match canonical bytes",
            ));
        }
    }
    Ok(())
}

fn discover_stage(
    root: &Path,
    session: &ModelIrModalWorkbenchSessionV1,
) -> Result<ModelIrModalWorkbenchStageV1, WorkbenchError> {
    match fs::symlink_metadata(root.join("05-compare")) {
        Ok(_) => {
            return Err(error(
                "workbench_modal_external_comparison_unsupported",
                "the bounded modal Workbench has no external comparison stage",
            ));
        }
        Err(value) if value.kind() == std::io::ErrorKind::NotFound => {}
        Err(value) => {
            return Err(error(
                "workbench_modal_io_error",
                format!("inspect unsupported comparison stage failed: {value}"),
            ));
        }
    }
    let stages = [
        (
            ModelIrModalWorkbenchStageV1::Validated,
            VALIDATION_DIRECTORY,
        ),
        (ModelIrModalWorkbenchStageV1::Direct, DIRECT_DIRECTORY),
        (ModelIrModalWorkbenchStageV1::Resumed, RESUME_DIRECTORY),
        (ModelIrModalWorkbenchStageV1::Reported, REPORT_DIRECTORY),
    ];
    let mut discovered = ModelIrModalWorkbenchStageV1::Imported;
    let mut gap = false;
    for (stage, name) in stages {
        let path = root.join(name);
        match fs::symlink_metadata(&path) {
            Ok(_) if gap => {
                return Err(error(
                    "workbench_modal_stage_gap",
                    format!("modal stage {name} exists after a missing predecessor"),
                ));
            }
            Ok(_) => {
                match stage {
                    ModelIrModalWorkbenchStageV1::Validated => {
                        verify_validation(root, session)?;
                    }
                    ModelIrModalWorkbenchStageV1::Direct => {
                        verify_product_directory(&path)?;
                    }
                    ModelIrModalWorkbenchStageV1::Resumed => {
                        verify_product_directory(&path)?;
                        verify_product_equivalence(&root.join(DIRECT_DIRECTORY), &path)?;
                    }
                    ModelIrModalWorkbenchStageV1::Reported => verify_report(root, session)?,
                    ModelIrModalWorkbenchStageV1::Imported => unreachable!(),
                }
                discovered = stage;
            }
            Err(value) if value.kind() == std::io::ErrorKind::NotFound => gap = true,
            Err(value) => {
                return Err(error(
                    "workbench_modal_io_error",
                    format!("inspect modal stage failed: {value}"),
                ));
            }
        }
    }
    Ok(discovered)
}

fn verify_validation(
    root: &Path,
    session: &ModelIrModalWorkbenchSessionV1,
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
        &root.join(IMPORT_DIRECTORY).join("model-modal-request.json"),
        MAX_REQUEST_BYTES,
    )?;
    let compatibility = validate_model_ir_modal_analysis_compatibility(&model, &request)
        .map_err(|value| error("workbench_modal_validation_failed", value.to_string()))?;
    if string_field(&receipt, "schema_version")? != VALIDATION_RECEIPT_SCHEMA_V1
        || string_field(&receipt, "status")? != "validated"
        || string_field(&receipt, "session_id")? != session.session_id
        || string_field(&receipt, "analysis_profile")? != "model_ir_modal_cpu_v1"
        || string_field(&receipt, "model_content_hash")? != session.model_content_hash
        || string_field(&receipt, "model_semantic_hash")? != session.model_semantic_hash
        || string_field(&receipt, "model_provenance_hash")? != session.model_provenance_hash
        || string_field(&receipt, "analysis_request_hash")? != session.analysis_request_hash
        || string_field(&receipt, "assembly_hash")? != compatibility.assembly_hash
        || string_field(&receipt, "generated_dense_request_hash")?
            != compatibility.generated_dense_request_hash
        || receipt.get("active_dof_count").and_then(Value::as_u64)
            != Some(u64::from(compatibility.active_dof_count))
        || string_field(&receipt, "claim_boundary")? != CLAIM_BOUNDARY
    {
        return Err(error(
            "workbench_modal_validation_binding_mismatch",
            "modal validation receipt does not match the reconstructed native assembly",
        ));
    }
    Ok(())
}

fn verify_product_directory(directory: &Path) -> Result<(), WorkbenchError> {
    render_model_ir_modal_result_view_directory(directory, WorkbenchReportLocaleV1::EnUs, 1, 1)
        .map(|_| ())
}

fn verify_product_equivalence(left: &Path, right: &Path) -> Result<(), WorkbenchError> {
    for name in PRODUCT_FILES {
        let left = read_bounded_regular_file(&left.join(name), MAX_PRODUCT_ARTIFACT_BYTES)?;
        let right = read_bounded_regular_file(&right.join(name), MAX_PRODUCT_ARTIFACT_BYTES)?;
        if left != right {
            return Err(error(
                "workbench_modal_restart_determinism_mismatch",
                format!("direct and resumed modal artifact bytes differ for {name}"),
            ));
        }
    }
    Ok(())
}

fn verify_report(
    root: &Path,
    session: &ModelIrModalWorkbenchSessionV1,
) -> Result<(), WorkbenchError> {
    let directory = root.join(REPORT_DIRECTORY);
    verify_inventory(
        &directory,
        &[
            "modal-result-view.en-US.txt",
            "modal-result-view.ko-KR.txt",
            "report-receipt.json",
        ],
    )?;
    let result = root.join(RESUME_DIRECTORY);
    let expected_english = render_model_ir_modal_result_view_directory(
        &result,
        WorkbenchReportLocaleV1::EnUs,
        1,
        128,
    )?;
    let expected_korean = render_model_ir_modal_result_view_directory(
        &result,
        WorkbenchReportLocaleV1::KoKr,
        1,
        128,
    )?;
    let english = read_bounded_regular_file(
        &directory.join("modal-result-view.en-US.txt"),
        MAX_REQUEST_BYTES,
    )?;
    let korean = read_bounded_regular_file(
        &directory.join("modal-result-view.ko-KR.txt"),
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
        || string_field(&receipt, "analysis_profile")? != "model_ir_modal_cpu_v1"
        || string_field(&receipt, "english_view_hash")? != sha256_identity(&english)
        || string_field(&receipt, "korean_view_hash")? != sha256_identity(&korean)
        || string_field(&receipt, "source_result_hash")?
            != sha256_identity(&read_bounded_regular_file(
                &result.join("result-ir.json"),
                MAX_PRODUCT_ARTIFACT_BYTES,
            )?)
        || !receipt
            .get("external_comparison")
            .is_some_and(Value::is_null)
        || !receipt
            .get("engineering_verdict")
            .is_some_and(Value::is_null)
        || string_field(&receipt, "claim_boundary")? != CLAIM_BOUNDARY
        || string_field(&receipt, "source_checkpoint_hash")?
            != sha256_identity(&read_bounded_regular_file(
                &result.join("checkpoint.mmcp"),
                MAX_PRODUCT_ARTIFACT_BYTES,
            )?)
    {
        return Err(error(
            "workbench_modal_report_binding_mismatch",
            "modal report views or receipt do not match the resumed product",
        ));
    }
    Ok(())
}

fn verify_request_identity(
    model: &structural_contracts::model_ir::ModelIrV2Document,
    request: &structural_contracts::model_modal_product::ModelIrModalAnalysisRequestDocumentV1,
) -> Result<(), WorkbenchError> {
    let identity = &request.request().model_identity;
    if identity.content_hash != model.content_hash()
        || identity.semantic_hash != model.semantic_hash()
        || identity.provenance_hash != model.provenance_hash()
    {
        return Err(error(
            "workbench_modal_model_identity_mismatch",
            "modal request model identity does not match the canonical ModelIR",
        ));
    }
    Ok(())
}

fn verify_inventory(directory: &Path, expected: &[&str]) -> Result<(), WorkbenchError> {
    verify_directory(directory, "workbench_modal_stage_directory_invalid")?;
    let actual = fs::read_dir(directory)
        .map_err(|value| error("workbench_modal_io_error", value.to_string()))?
        .map(|entry| {
            entry
                .map_err(|value| error("workbench_modal_io_error", value.to_string()))?
                .file_name()
                .into_string()
                .map_err(|_| {
                    error(
                        "workbench_modal_inventory_invalid",
                        "modal artifact names must be valid UTF-8",
                    )
                })
        })
        .collect::<Result<BTreeSet<_>, _>>()?;
    let expected = expected
        .iter()
        .map(|value| (*value).to_owned())
        .collect::<BTreeSet<_>>();
    if actual != expected {
        return Err(error(
            "workbench_modal_inventory_mismatch",
            "modal stage contains missing or extra artifacts",
        ));
    }
    Ok(())
}

fn string_field<'a>(value: &'a Value, name: &str) -> Result<&'a str, WorkbenchError> {
    value.get(name).and_then(Value::as_str).ok_or_else(|| {
        error(
            "workbench_modal_receipt_invalid",
            format!("modal receipt field {name} is missing or invalid"),
        )
    })
}

fn error(code: &'static str, detail: impl Into<String>) -> WorkbenchError {
    WorkbenchError::new(code, detail)
}

#[cfg(test)]
mod tests {
    use super::{ModelIrModalWorkbenchStageV1, SESSION_SCHEMA_V1};

    #[test]
    fn modal_stage_order_and_schema_are_frozen() {
        assert!(ModelIrModalWorkbenchStageV1::Imported < ModelIrModalWorkbenchStageV1::Validated);
        assert!(ModelIrModalWorkbenchStageV1::Validated < ModelIrModalWorkbenchStageV1::Direct);
        assert!(ModelIrModalWorkbenchStageV1::Direct < ModelIrModalWorkbenchStageV1::Resumed);
        assert!(ModelIrModalWorkbenchStageV1::Resumed < ModelIrModalWorkbenchStageV1::Reported);
        assert_eq!(
            SESSION_SCHEMA_V1,
            "structural-native-model-ir-modal-workbench-session.v1"
        );
    }
}
