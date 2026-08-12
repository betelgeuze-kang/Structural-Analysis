//! Durable Rust-native Workbench state and product orchestration.

#![forbid(unsafe_code)]

use std::fmt;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use structural_cli::{
    execute_external_comparison, execute_model_ir_native_analysis, execute_native_mgt_import,
    execute_pdf_report, publish_external_comparison, publish_model_ir_native_analysis,
    publish_pdf_report, validate_model_bytes,
};
use structural_contracts::external_comparison::parse_external_result_v1;
use structural_contracts::model_ir::{
    canonicalize_model_ir_v2, decode_json_strict, parse_model_ir_v2,
};
use structural_contracts::product_ir::{parse_model_ir_ndtha_analysis_request_v1, sha256_identity};

const SESSION_SCHEMA_V1: &str = "structural-native-workbench-session.v1";
const IMPORT_RECEIPT_SCHEMA_V1: &str = "structural-native-workbench-import-receipt.v1";
const VALIDATION_RECEIPT_SCHEMA_V1: &str = "structural-native-workbench-validation-receipt.v1";
const CLAIM_BOUNDARY: &str = "bounded_terminal_rust_native_workbench_for_one_fixed_guided_model_ir_ndtha_profile_not_general_gui_live_external_solver_rocm_package_or_c6_decommission";
const SESSION_FILE: &str = "workbench-session.json";
const IMPORT_DIRECTORY: &str = "01-import";
const VALIDATION_DIRECTORY: &str = "02-validate";
const RUN_DIRECTORY: &str = "03-run";
const RESUME_DIRECTORY: &str = "04-resume";
const COMPARISON_DIRECTORY: &str = "05-compare";
const REPORT_DIRECTORY: &str = "06-report";
const MAX_MODEL_BYTES: u64 = 64 * 1024 * 1024;
const MAX_REQUEST_BYTES: u64 = 4 * 1024 * 1024;
const MAX_EXTERNAL_RESULT_BYTES: u64 = 1024 * 1024;
const MAX_EXTERNAL_ARTIFACT_BYTES: u64 = 64 * 1024 * 1024;
const MAX_PRODUCT_ARTIFACT_BYTES: u64 = 300 * 1024 * 1024;
static OUTPUT_SEQUENCE: AtomicU64 = AtomicU64::new(0);

/// A stable Workbench failure suitable for a CLI/API error envelope.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct WorkbenchError {
    pub code: &'static str,
    pub detail: String,
}

impl WorkbenchError {
    fn new(code: &'static str, detail: impl Into<String>) -> Self {
        Self {
            code,
            detail: detail.into(),
        }
    }
}

impl fmt::Display for WorkbenchError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{}: {}", self.code, self.detail)
    }
}

impl std::error::Error for WorkbenchError {}

/// Ordered product stages exposed by the terminal-native Workbench.
#[derive(Clone, Copy, Debug, Deserialize, Eq, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum WorkbenchStageV1 {
    Imported,
    Validated,
    Checkpointed,
    Terminal,
    Compared,
    Reported,
}

impl WorkbenchStageV1 {
    #[must_use]
    pub const fn label(self) -> &'static str {
        match self {
            Self::Imported => "imported",
            Self::Validated => "validated",
            Self::Checkpointed => "checkpointed",
            Self::Terminal => "terminal",
            Self::Compared => "compared",
            Self::Reported => "reported",
        }
    }
}

/// Self-hashed durable Workbench state. Paths are intentionally excluded.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct WorkbenchSessionV1 {
    schema_version: String,
    session_id: String,
    stage: WorkbenchStageV1,
    source_model_ir_hash: String,
    model_content_hash: String,
    model_semantic_hash: String,
    model_provenance_hash: String,
    analysis_request_hash: String,
    external_result_hash: String,
    source_artifact_hash: String,
    executable_artifact_hash: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    mgt_source_hash: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    mgt_import_health_artifact_hash: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    mgt_import_receipt_artifact_hash: Option<String>,
    terminal_status: Option<String>,
    comparison_passed: Option<bool>,
    claim_boundary: String,
    session_hash: String,
}

impl WorkbenchSessionV1 {
    #[must_use]
    pub const fn stage(&self) -> WorkbenchStageV1 {
        self.stage
    }

    #[must_use]
    pub fn session_id(&self) -> &str {
        &self.session_id
    }

    #[must_use]
    pub fn terminal_status(&self) -> Option<&str> {
        self.terminal_status.as_deref()
    }

    #[must_use]
    pub const fn comparison_passed(&self) -> Option<bool> {
        self.comparison_passed
    }
}

/// A durable controller that invokes product libraries directly, never subprocess adapters.
#[derive(Debug)]
pub struct NativeWorkbench {
    root: PathBuf,
    session: WorkbenchSessionV1,
}

#[derive(Clone, Copy, Debug)]
struct MgtImportEvidence<'a> {
    source: &'a [u8],
    health: &'a str,
    validation: &'a str,
    snapshot: &'a str,
    receipt: &'a str,
}

impl NativeWorkbench {
    /// Read bounded non-symlink input files and initialize a new Workbench.
    ///
    /// # Errors
    ///
    /// Returns the same strict input and publication errors as [`Self::initialize`].
    #[allow(clippy::too_many_arguments)]
    pub fn initialize_from_paths(
        root: &Path,
        source_model_ir_path: &Path,
        analysis_request_path: &Path,
        external_result_path: &Path,
        source_artifact_path: &Path,
        executable_artifact_path: Option<&Path>,
    ) -> Result<Self, WorkbenchError> {
        let source_model_ir = read_bounded_regular_file(source_model_ir_path, MAX_MODEL_BYTES)?;
        let analysis_request = read_bounded_regular_file(analysis_request_path, MAX_REQUEST_BYTES)?;
        let external_result =
            read_bounded_regular_file(external_result_path, MAX_EXTERNAL_RESULT_BYTES)?;
        let source_artifact =
            read_bounded_regular_file(source_artifact_path, MAX_EXTERNAL_ARTIFACT_BYTES)?;
        let executable_artifact = executable_artifact_path
            .map(|path| read_bounded_regular_file(path, MAX_EXTERNAL_ARTIFACT_BYTES))
            .transpose()?;
        Self::initialize(
            root,
            &source_model_ir,
            &analysis_request,
            &external_result,
            &source_artifact,
            executable_artifact.as_deref(),
        )
    }

    /// Read an original MGT source, retain its import-health evidence, and initialize a new
    /// Workbench from the exact normalized `ModelIR`.
    ///
    /// # Errors
    ///
    /// Rejects a blocked/unsupported MGT import, an identity-mismatched analysis request, unsafe
    /// input paths, or any durable publication failure.
    #[allow(clippy::too_many_arguments)]
    pub fn initialize_from_mgt_paths(
        root: &Path,
        source_mgt_path: &Path,
        model_id: &str,
        analysis_request_path: &Path,
        external_result_path: &Path,
        source_artifact_path: &Path,
        executable_artifact_path: Option<&Path>,
    ) -> Result<Self, WorkbenchError> {
        let source_mgt = read_bounded_regular_file(source_mgt_path, MAX_MODEL_BYTES)?;
        let analysis_request = read_bounded_regular_file(analysis_request_path, MAX_REQUEST_BYTES)?;
        let external_result =
            read_bounded_regular_file(external_result_path, MAX_EXTERNAL_RESULT_BYTES)?;
        let source_artifact =
            read_bounded_regular_file(source_artifact_path, MAX_EXTERNAL_ARTIFACT_BYTES)?;
        let executable_artifact = executable_artifact_path
            .map(|path| read_bounded_regular_file(path, MAX_EXTERNAL_ARTIFACT_BYTES))
            .transpose()?;
        Self::initialize_from_mgt(
            root,
            &source_mgt,
            model_id,
            &analysis_request,
            &external_result,
            &source_artifact,
            executable_artifact.as_deref(),
        )
    }

    /// Normalize one bounded MGT source through Rust/C++ product owners and create a durable
    /// Workbench import stage containing the original bytes and complete import evidence.
    ///
    /// # Errors
    ///
    /// Returns a stable Workbench error for blocked import health, missing normalized artifacts,
    /// identity mismatch, or publication failure.
    #[allow(clippy::too_many_arguments)]
    pub fn initialize_from_mgt(
        root: &Path,
        source_mgt: &[u8],
        model_id: &str,
        analysis_request: &[u8],
        external_result: &[u8],
        source_artifact: &[u8],
        executable_artifact: Option<&[u8]>,
    ) -> Result<Self, WorkbenchError> {
        verify_slice_bound(source_mgt, MAX_MODEL_BYTES, "MGT source")?;
        let imported = execute_native_mgt_import(source_mgt, model_id)
            .map_err(|error| input_error("workbench_mgt_import_failed", &error))?;
        if !imported.is_normalized() {
            return Err(WorkbenchError::new(
                "workbench_mgt_import_blocked",
                "MGT import health is blocked and cannot start an analysis Workbench",
            ));
        }
        let (Some(model), Some(validation), Some(snapshot)) = (
            imported.model_ir_json(),
            imported.validation_json(),
            imported.snapshot_json(),
        ) else {
            return Err(WorkbenchError::new(
                "workbench_mgt_import_incomplete",
                "normalized MGT import did not publish ModelIR and C++ validation artifacts",
            ));
        };
        Self::initialize_with_mgt_evidence(
            root,
            model.as_bytes(),
            analysis_request,
            external_result,
            source_artifact,
            executable_artifact,
            Some(MgtImportEvidence {
                source: imported.source_bytes(),
                health: imported.health_json(),
                validation,
                snapshot,
                receipt: imported.receipt_json(),
            }),
        )
    }

    /// Create a new immutable input set and publish its first durable session atomically.
    ///
    /// # Errors
    ///
    /// Rejects malformed or identity-mismatched inputs, symlinked/existing destinations and
    /// publication failures.
    #[allow(clippy::too_many_arguments, clippy::too_many_lines)]
    pub fn initialize(
        root: &Path,
        source_model_ir: &[u8],
        analysis_request: &[u8],
        external_result: &[u8],
        source_artifact: &[u8],
        executable_artifact: Option<&[u8]>,
    ) -> Result<Self, WorkbenchError> {
        Self::initialize_with_mgt_evidence(
            root,
            source_model_ir,
            analysis_request,
            external_result,
            source_artifact,
            executable_artifact,
            None,
        )
    }

    #[allow(clippy::too_many_arguments, clippy::too_many_lines)]
    fn initialize_with_mgt_evidence(
        root: &Path,
        source_model_ir: &[u8],
        analysis_request: &[u8],
        external_result: &[u8],
        source_artifact: &[u8],
        executable_artifact: Option<&[u8]>,
        mgt: Option<MgtImportEvidence<'_>>,
    ) -> Result<Self, WorkbenchError> {
        if root.exists() {
            return Err(WorkbenchError::new(
                "workbench_destination_exists",
                "the Workbench directory must not already exist",
            ));
        }
        verify_slice_bound(source_model_ir, MAX_MODEL_BYTES, "ModelIR")?;
        verify_slice_bound(
            analysis_request,
            MAX_REQUEST_BYTES,
            "model analysis request",
        )?;
        verify_slice_bound(
            external_result,
            MAX_EXTERNAL_RESULT_BYTES,
            "external result",
        )?;
        verify_slice_bound(
            source_artifact,
            MAX_EXTERNAL_ARTIFACT_BYTES,
            "external source artifact",
        )?;
        if let Some(bytes) = executable_artifact {
            verify_slice_bound(
                bytes,
                MAX_EXTERNAL_ARTIFACT_BYTES,
                "external executable artifact",
            )?;
        }
        if let Some(evidence) = mgt {
            verify_slice_bound(evidence.source, MAX_MODEL_BYTES, "MGT source")?;
            verify_slice_bound(
                evidence.health.as_bytes(),
                MAX_MODEL_BYTES,
                "MGT import health",
            )?;
            verify_slice_bound(
                evidence.validation.as_bytes(),
                MAX_MODEL_BYTES,
                "MGT native validation",
            )?;
            verify_slice_bound(
                evidence.snapshot.as_bytes(),
                MAX_MODEL_BYTES,
                "MGT native snapshot",
            )?;
            verify_slice_bound(
                evidence.receipt.as_bytes(),
                MAX_MODEL_BYTES,
                "MGT import receipt",
            )?;
        }
        let parent = output_parent(root);
        verify_directory(parent, "workbench_output_parent_invalid")?;

        let model = parse_model_ir_v2(source_model_ir)
            .map_err(|error| input_error("workbench_model_ir_invalid", &error))?;
        let request = parse_model_ir_ndtha_analysis_request_v1(analysis_request)
            .map_err(|error| input_error("workbench_analysis_request_invalid", &error))?;
        let external = parse_external_result_v1(external_result)
            .map_err(|error| input_error("workbench_external_result_invalid", &error))?;
        let requested_identity = &request.request().model_identity;
        if requested_identity.content_hash != model.content_hash()
            || requested_identity.semantic_hash != model.semantic_hash()
            || requested_identity.provenance_hash != model.provenance_hash()
        {
            return Err(WorkbenchError::new(
                "workbench_model_request_identity_mismatch",
                "the analysis request is not bound to the imported ModelIR identities",
            ));
        }
        verify_external_artifact_bindings(&external, source_artifact, executable_artifact)?;

        let source_model_ir_hash = sha256_identity(source_model_ir);
        let source_artifact_hash = sha256_identity(source_artifact);
        let executable_artifact_hash = executable_artifact.map(sha256_identity);
        let mgt_source_hash = mgt.map(|evidence| sha256_identity(evidence.source));
        let mgt_import_health_artifact_hash =
            mgt.map(|evidence| sha256_identity(evidence.health.as_bytes()));
        let mgt_import_receipt_artifact_hash =
            mgt.map(|evidence| sha256_identity(evidence.receipt.as_bytes()));
        let mut binding = json!({
            "source_model_ir_hash": source_model_ir_hash,
            "model_content_hash": model.content_hash(),
            "model_semantic_hash": model.semantic_hash(),
            "model_provenance_hash": model.provenance_hash(),
            "analysis_request_hash": request.request_hash(),
            "external_result_hash": external.external_result_hash(),
            "source_artifact_hash": source_artifact_hash,
            "executable_artifact_hash": executable_artifact_hash,
        });
        if let (Some(source_hash), Some(health_hash), Some(receipt_hash)) = (
            mgt_source_hash.as_deref(),
            mgt_import_health_artifact_hash.as_deref(),
            mgt_import_receipt_artifact_hash.as_deref(),
        ) {
            binding
                .as_object_mut()
                .expect("Workbench binding is an object")
                .insert(
                    "mgt_import".to_owned(),
                    json!({
                        "source_hash": source_hash,
                        "health_artifact_hash": health_hash,
                        "receipt_artifact_hash": receipt_hash,
                    }),
                );
        }
        let binding_json = canonical_json(&binding, "workbench_session_identity_failed")?;
        let session_id = sha256_identity(binding_json.as_bytes());
        let session = WorkbenchSessionV1 {
            schema_version: SESSION_SCHEMA_V1.to_owned(),
            session_id: session_id.clone(),
            stage: WorkbenchStageV1::Imported,
            source_model_ir_hash,
            model_content_hash: model.content_hash().to_owned(),
            model_semantic_hash: model.semantic_hash().to_owned(),
            model_provenance_hash: model.provenance_hash().to_owned(),
            analysis_request_hash: request.request_hash().to_owned(),
            external_result_hash: external.external_result_hash().to_owned(),
            source_artifact_hash,
            executable_artifact_hash,
            mgt_source_hash,
            mgt_import_health_artifact_hash,
            mgt_import_receipt_artifact_hash,
            terminal_status: None,
            comparison_passed: None,
            claim_boundary: CLAIM_BOUNDARY.to_owned(),
            session_hash: String::new(),
        };
        let session_json = canonical_session(&session)?;
        let mut inventory = vec![
            artifact_entry(
                if mgt.is_some() {
                    "normalized_source_model_ir"
                } else {
                    "original_model_ir"
                },
                "source-model-ir.json",
                "application/json",
                source_model_ir,
            )?,
            artifact_entry(
                "canonical_model_ir",
                "model-ir.json",
                "application/json",
                model.canonical_bytes(),
            )?,
            artifact_entry(
                "model_analysis_request",
                "model-analysis-request.json",
                "application/json",
                request.canonical_bytes(),
            )?,
            artifact_entry(
                "external_result",
                "external-result.json",
                "application/json",
                external.canonical_bytes(),
            )?,
            artifact_entry(
                "external_source_artifact",
                "external-source.artifact",
                "application/octet-stream",
                source_artifact,
            )?,
        ];
        if let Some(bytes) = executable_artifact {
            inventory.push(artifact_entry(
                "external_executable_artifact",
                "external-executable.artifact",
                "application/octet-stream",
                bytes,
            )?);
        }
        if let Some(evidence) = mgt {
            inventory.extend([
                artifact_entry(
                    "original_mgt_source",
                    "source.mgt",
                    "application/octet-stream",
                    evidence.source,
                )?,
                artifact_entry(
                    "mgt_import_health",
                    "import-health.json",
                    "application/json",
                    evidence.health.as_bytes(),
                )?,
                artifact_entry(
                    "mgt_cpp_validation_report",
                    "mgt-native-validation.json",
                    "application/json",
                    evidence.validation.as_bytes(),
                )?,
                artifact_entry(
                    "mgt_cpp_canonical_snapshot",
                    "mgt-native-snapshot.json",
                    "application/json",
                    evidence.snapshot.as_bytes(),
                )?,
                artifact_entry(
                    "mgt_import_receipt",
                    "mgt-import-receipt.json",
                    "application/json",
                    evidence.receipt.as_bytes(),
                )?,
            ]);
        }
        let import_receipt = canonical_self_hashed(json!({
            "schema_version": IMPORT_RECEIPT_SCHEMA_V1,
            "session_id": session_id,
            "status": "imported",
            "artifacts": inventory,
            "claim_boundary": if mgt.is_some() {
                "bounded_original_mgt_import_health_normalized_modelir_and_cpp_snapshot_bound_to_one_native_workbench_profile"
            } else {
                "strict_language_neutral_input_ingestion_only_not_cpp_validation_or_solver_execution"
            },
        }))?;
        let mut artifacts = vec![
            ("source-model-ir.json", source_model_ir),
            ("model-ir.json", model.canonical_bytes()),
            ("model-analysis-request.json", request.canonical_bytes()),
            ("external-result.json", external.canonical_bytes()),
            ("external-source.artifact", source_artifact),
        ];
        if let Some(evidence) = mgt {
            artifacts.extend([
                ("source.mgt", evidence.source),
                ("import-health.json", evidence.health.as_bytes()),
                ("mgt-native-validation.json", evidence.validation.as_bytes()),
                ("mgt-native-snapshot.json", evidence.snapshot.as_bytes()),
                ("mgt-import-receipt.json", evidence.receipt.as_bytes()),
            ]);
        }
        publish_initial_workspace(
            root,
            &artifacts,
            executable_artifact,
            import_receipt.as_bytes(),
            session_json.as_bytes(),
        )?;
        Ok(Self {
            root: root.to_path_buf(),
            session: parse_session(session_json.as_bytes())?,
        })
    }

    /// Open and verify a durable session, reconciling an atomic stage publication after a crash.
    ///
    /// # Errors
    ///
    /// Rejects a symlinked root, a tampered session/input/receipt, a stage gap or missing artifacts.
    pub fn open(root: &Path) -> Result<Self, WorkbenchError> {
        verify_directory(root, "workbench_directory_invalid")?;
        let session_bytes =
            read_bounded_regular_file(&root.join(SESSION_FILE), MAX_EXTERNAL_RESULT_BYTES)?;
        let mut session = parse_session(&session_bytes)?;
        verify_import_bindings(root, &session)?;
        let discovered = verify_stage_chain(root, session.session_id())?;
        if session.stage > discovered.stage {
            return Err(WorkbenchError::new(
                "workbench_session_ahead_of_artifacts",
                "the durable session claims a stage whose atomic artifacts are absent",
            ));
        }
        session.stage = discovered.stage;
        session.terminal_status = discovered.terminal_status;
        session.comparison_passed = discovered.comparison_passed;
        Ok(Self {
            root: root.to_path_buf(),
            session,
        })
    }

    #[must_use]
    pub const fn session(&self) -> &WorkbenchSessionV1 {
        &self.session
    }

    /// Return the reconciled, self-hashed canonical session bytes.
    ///
    /// # Errors
    ///
    /// Returns an invariant failure if the state cannot be canonically serialized.
    pub fn session_json(&self) -> Result<String, WorkbenchError> {
        canonical_session(&self.session)
    }

    /// Cross the C ABI into C++ semantic validation and publish the exact snapshot/report.
    ///
    /// # Errors
    ///
    /// Fails closed unless the current stage is `imported` and the model is analysis-ready.
    pub fn validate(&mut self) -> Result<(), WorkbenchError> {
        self.require_stage(WorkbenchStageV1::Imported)?;
        let model = self.read_import_artifact("model-ir.json", MAX_MODEL_BYTES)?;
        let validation = validate_model_bytes(&model)
            .map_err(|error| input_error("workbench_native_validation_failed", &error))?;
        if !validation.report.contract_valid || !validation.report.analysis_ready {
            return Err(WorkbenchError::new(
                "workbench_model_not_analysis_ready",
                "native C++ validation did not accept the imported model as analysis-ready",
            ));
        }
        let snapshot = validation.snapshot.canonical_bytes();
        let receipt = canonical_self_hashed(json!({
            "schema_version": VALIDATION_RECEIPT_SCHEMA_V1,
            "session_id": self.session.session_id,
            "status": "validated",
            "model_identity": {
                "content_hash": validation.report.content_hash,
                "semantic_hash": validation.report.semantic_hash,
                "provenance_hash": validation.report.provenance_hash,
            },
            "artifacts": [
                artifact_entry("cpp_validation_report", "native-validation.json", "application/json", validation.report_json.as_bytes())?,
                artifact_entry("cpp_canonical_snapshot", "native-snapshot.json", "application/json", snapshot)?,
            ],
            "claim_boundary": "one_strict_model_ir_rust_to_c_abi_to_cpp_snapshot_validation",
        }))?;
        publish_new_directory(
            &self.root.join(VALIDATION_DIRECTORY),
            &[
                ("native-validation.json", validation.report_json.as_bytes()),
                ("native-snapshot.json", snapshot),
                ("validation-receipt.json", receipt.as_bytes()),
            ],
        )?;
        self.session.stage = WorkbenchStageV1::Validated;
        self.persist()
    }

    /// Advance a fresh native analysis to a real nonterminal checkpoint.
    ///
    /// # Errors
    ///
    /// Rejects zero budget, invalid order, terminal-at-first-advance and product/runtime failures.
    pub fn run(&mut self, step_budget: u32) -> Result<(), WorkbenchError> {
        self.require_stage(WorkbenchStageV1::Validated)?;
        if step_budget == 0 {
            return Err(WorkbenchError::new(
                "workbench_run_budget_invalid",
                "Run requires a positive bounded step budget so Resume remains a real transition",
            ));
        }
        let model = self.read_import_artifact("model-ir.json", MAX_MODEL_BYTES)?;
        let request =
            self.read_import_artifact("model-analysis-request.json", MAX_REQUEST_BYTES)?;
        let outcome = execute_model_ir_native_analysis(&model, &request, None, step_budget)
            .map_err(|error| input_error("workbench_run_failed", &error))?;
        if outcome.is_terminal() {
            return Err(WorkbenchError::new(
                "workbench_run_did_not_checkpoint",
                "the bounded Run budget reached a terminal state; choose a smaller budget",
            ));
        }
        publish_model_ir_native_analysis(&self.root.join(RUN_DIRECTORY), &outcome)
            .map_err(|error| input_error("workbench_run_publish_failed", &error))?;
        self.session.stage = WorkbenchStageV1::Checkpointed;
        self.persist()
    }

    /// Resume the exact Workbench checkpoint to a terminal product result.
    ///
    /// A zero budget means the existing native unbounded-to-terminal policy.
    ///
    /// # Errors
    ///
    /// Rejects invalid order, corrupt/binding-mismatched checkpoints and nonterminal outcomes.
    pub fn resume(&mut self, step_budget: u32) -> Result<(), WorkbenchError> {
        self.require_stage(WorkbenchStageV1::Checkpointed)?;
        let model = self.read_import_artifact("model-ir.json", MAX_MODEL_BYTES)?;
        let request =
            self.read_import_artifact("model-analysis-request.json", MAX_REQUEST_BYTES)?;
        let checkpoint = read_bounded_regular_file(
            &self.root.join(RUN_DIRECTORY).join("checkpoint.ndcp"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let effective_budget = if step_budget == 0 {
            u32::MAX
        } else {
            step_budget
        };
        let outcome =
            execute_model_ir_native_analysis(&model, &request, Some(&checkpoint), effective_budget)
                .map_err(|error| input_error("workbench_resume_failed", &error))?;
        if !outcome.is_terminal() {
            return Err(WorkbenchError::new(
                "workbench_resume_not_terminal",
                "Resume exhausted its budget before reaching a terminal state",
            ));
        }
        let terminal_status = receipt_status(outcome.run_receipt_json())?;
        publish_model_ir_native_analysis(&self.root.join(RESUME_DIRECTORY), &outcome)
            .map_err(|error| input_error("workbench_resume_publish_failed", &error))?;
        self.session.stage = WorkbenchStageV1::Terminal;
        self.session.terminal_status = Some(terminal_status);
        self.persist()
    }

    /// Compare terminal `ResultIR` against a hash-bound external result and source artifact.
    ///
    /// # Errors
    ///
    /// Rejects invalid order/contracts. With `require_pass`, divergence remains published and
    /// durable but is returned as a policy failure.
    pub fn compare(&mut self, require_pass: bool) -> Result<(), WorkbenchError> {
        self.require_stage(WorkbenchStageV1::Terminal)?;
        let result = read_bounded_regular_file(
            &self.root.join(RESUME_DIRECTORY).join("result-ir.json"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let external =
            self.read_import_artifact("external-result.json", MAX_EXTERNAL_RESULT_BYTES)?;
        let source =
            self.read_import_artifact("external-source.artifact", MAX_EXTERNAL_ARTIFACT_BYTES)?;
        let executable_path = self
            .root
            .join(IMPORT_DIRECTORY)
            .join("external-executable.artifact");
        let executable = if self.session.executable_artifact_hash.is_some() {
            Some(read_bounded_regular_file(
                &executable_path,
                MAX_EXTERNAL_ARTIFACT_BYTES,
            )?)
        } else {
            None
        };
        let outcome =
            execute_external_comparison(&result, &external, &source, executable.as_deref())
                .map_err(|error| input_error("workbench_comparison_failed", &error))?;
        let passed = outcome.passed();
        publish_external_comparison(&self.root.join(COMPARISON_DIRECTORY), &outcome)
            .map_err(|error| input_error("workbench_comparison_publish_failed", &error))?;
        self.session.stage = WorkbenchStageV1::Compared;
        self.session.comparison_passed = Some(passed);
        self.persist()?;
        if require_pass && !passed {
            return Err(WorkbenchError::new(
                "workbench_comparison_diverged",
                "external comparison evidence was published but exceeded tolerance",
            ));
        }
        Ok(())
    }

    /// Render and publish a deterministic native PDF from the exact terminal artifacts.
    ///
    /// # Errors
    ///
    /// Rejects invalid order, forged projections and native PDF publication failure.
    pub fn report(&mut self) -> Result<(), WorkbenchError> {
        self.require_stage(WorkbenchStageV1::Compared)?;
        let terminal = self.root.join(RESUME_DIRECTORY);
        let result = read_bounded_regular_file(
            &terminal.join("result-ir.json"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let report = read_bounded_regular_file(
            &terminal.join("report-ir.json"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let document =
            read_bounded_regular_file(&terminal.join("report.md"), MAX_PRODUCT_ARTIFACT_BYTES)?;
        let outcome = execute_pdf_report(&result, &report, &document)
            .map_err(|error| input_error("workbench_report_failed", &error))?;
        publish_pdf_report(&self.root.join(REPORT_DIRECTORY), &outcome)
            .map_err(|error| input_error("workbench_report_publish_failed", &error))?;
        self.session.stage = WorkbenchStageV1::Reported;
        self.persist()
    }

    fn require_stage(&self, expected: WorkbenchStageV1) -> Result<(), WorkbenchError> {
        if self.session.stage == expected {
            Ok(())
        } else {
            Err(WorkbenchError::new(
                "workbench_transition_invalid",
                format!(
                    "{} is required but the durable stage is {}",
                    expected.label(),
                    self.session.stage.label()
                ),
            ))
        }
    }

    fn read_import_artifact(
        &self,
        file: &str,
        maximum_bytes: u64,
    ) -> Result<Vec<u8>, WorkbenchError> {
        read_bounded_regular_file(&self.root.join(IMPORT_DIRECTORY).join(file), maximum_bytes)
    }

    fn persist(&mut self) -> Result<(), WorkbenchError> {
        let canonical = canonical_session(&self.session)?;
        self.session = parse_session(canonical.as_bytes())?;
        write_atomic_file(&self.root.join(SESSION_FILE), canonical.as_bytes())
    }
}

#[derive(Debug)]
struct DiscoveredState {
    stage: WorkbenchStageV1,
    terminal_status: Option<String>,
    comparison_passed: Option<bool>,
}

fn verify_external_artifact_bindings(
    external: &structural_contracts::external_comparison::ExternalResultDocumentV1,
    source_artifact: &[u8],
    executable_artifact: Option<&[u8]>,
) -> Result<(), WorkbenchError> {
    let source = &external.external_result().source;
    if sha256_identity(source_artifact) != source.source_artifact_hash {
        return Err(WorkbenchError::new(
            "workbench_external_source_hash_mismatch",
            "the imported external source bytes do not match the external-result binding",
        ));
    }
    match (&source.executable_hash, executable_artifact) {
        (Some(expected), Some(bytes)) if *expected == sha256_identity(bytes) => Ok(()),
        (None, None) => Ok(()),
        (Some(_), Some(_)) => Err(WorkbenchError::new(
            "workbench_external_executable_hash_mismatch",
            "the imported executable bytes do not match the external-result binding",
        )),
        (Some(_), None) => Err(WorkbenchError::new(
            "workbench_external_executable_missing",
            "the external-result binding requires executable bytes",
        )),
        (None, Some(_)) => Err(WorkbenchError::new(
            "workbench_external_executable_unbound",
            "executable bytes were supplied without an external-result hash binding",
        )),
    }
}

fn verify_import_bindings(root: &Path, session: &WorkbenchSessionV1) -> Result<(), WorkbenchError> {
    let imported = root.join(IMPORT_DIRECTORY);
    let source_model =
        read_bounded_regular_file(&imported.join("source-model-ir.json"), MAX_MODEL_BYTES)?;
    let model = read_bounded_regular_file(&imported.join("model-ir.json"), MAX_MODEL_BYTES)?;
    let request = read_bounded_regular_file(
        &imported.join("model-analysis-request.json"),
        MAX_REQUEST_BYTES,
    )?;
    let external = read_bounded_regular_file(
        &imported.join("external-result.json"),
        MAX_EXTERNAL_RESULT_BYTES,
    )?;
    let source = read_bounded_regular_file(
        &imported.join("external-source.artifact"),
        MAX_EXTERNAL_ARTIFACT_BYTES,
    )?;
    let parsed_model = parse_model_ir_v2(&model)
        .map_err(|error| input_error("workbench_imported_model_invalid", &error))?;
    let parsed_request = parse_model_ir_ndtha_analysis_request_v1(&request)
        .map_err(|error| input_error("workbench_imported_request_invalid", &error))?;
    let parsed_external = parse_external_result_v1(&external)
        .map_err(|error| input_error("workbench_imported_external_result_invalid", &error))?;
    let executable = if session.executable_artifact_hash.is_some() {
        Some(read_bounded_regular_file(
            &imported.join("external-executable.artifact"),
            MAX_EXTERNAL_ARTIFACT_BYTES,
        )?)
    } else {
        if imported.join("external-executable.artifact").exists() {
            return Err(WorkbenchError::new(
                "workbench_import_binding_mismatch",
                "an unbound executable artifact appeared in the immutable import set",
            ));
        }
        None
    };
    let mgt_binding = verify_mgt_import_bindings(&imported, session, &parsed_model, &model)?;
    let valid = session.source_model_ir_hash == sha256_identity(&source_model)
        && session.model_content_hash == parsed_model.content_hash()
        && session.model_semantic_hash == parsed_model.semantic_hash()
        && session.model_provenance_hash == parsed_model.provenance_hash()
        && session.analysis_request_hash == parsed_request.request_hash()
        && session.external_result_hash == parsed_external.external_result_hash()
        && session.source_artifact_hash == sha256_identity(&source)
        && session.executable_artifact_hash == executable.as_deref().map(sha256_identity);
    if !valid {
        return Err(WorkbenchError::new(
            "workbench_import_binding_mismatch",
            "one or more immutable imported artifacts differ from the durable session",
        ));
    }
    let mut binding = json!({
        "source_model_ir_hash": session.source_model_ir_hash,
        "model_content_hash": session.model_content_hash,
        "model_semantic_hash": session.model_semantic_hash,
        "model_provenance_hash": session.model_provenance_hash,
        "analysis_request_hash": session.analysis_request_hash,
        "external_result_hash": session.external_result_hash,
        "source_artifact_hash": session.source_artifact_hash,
        "executable_artifact_hash": session.executable_artifact_hash,
    });
    if let Some(mgt_import) = mgt_binding {
        binding
            .as_object_mut()
            .expect("Workbench binding is an object")
            .insert("mgt_import".to_owned(), mgt_import);
    }
    let binding_json = canonical_json(&binding, "workbench_session_identity_failed")?;
    if session.session_id != sha256_identity(binding_json.as_bytes()) {
        return Err(WorkbenchError::new(
            "workbench_session_identity_mismatch",
            "the session ID is not derived from the immutable imported artifact identities",
        ));
    }
    verify_external_artifact_bindings(&parsed_external, &source, executable.as_deref())?;
    verify_receipt_directory(&imported, "import-receipt.json")?;
    Ok(())
}

fn verify_mgt_import_bindings(
    imported: &Path,
    session: &WorkbenchSessionV1,
    parsed_model: &structural_contracts::model_ir::ModelIrV2Document,
    model: &[u8],
) -> Result<Option<Value>, WorkbenchError> {
    let field_count = [
        session.mgt_source_hash.as_ref(),
        session.mgt_import_health_artifact_hash.as_ref(),
        session.mgt_import_receipt_artifact_hash.as_ref(),
    ]
    .into_iter()
    .flatten()
    .count();
    let names = [
        "source.mgt",
        "import-health.json",
        "mgt-native-validation.json",
        "mgt-native-snapshot.json",
        "mgt-import-receipt.json",
    ];
    if field_count == 0 {
        if names.iter().any(|name| imported.join(name).exists()) {
            return Err(WorkbenchError::new(
                "workbench_import_binding_mismatch",
                "unbound MGT evidence appeared in a ModelIR-only import set",
            ));
        }
        return Ok(None);
    }
    if field_count != 3 {
        return Err(WorkbenchError::new(
            "workbench_mgt_import_binding_incomplete",
            "MGT import session identities must be absent or complete",
        ));
    }

    let mgt_source = read_bounded_regular_file(&imported.join("source.mgt"), MAX_MODEL_BYTES)?;
    let mgt_health =
        read_bounded_regular_file(&imported.join("import-health.json"), MAX_MODEL_BYTES)?;
    let mgt_validation = read_bounded_regular_file(
        &imported.join("mgt-native-validation.json"),
        MAX_MODEL_BYTES,
    )?;
    let mgt_snapshot =
        read_bounded_regular_file(&imported.join("mgt-native-snapshot.json"), MAX_MODEL_BYTES)?;
    let mgt_receipt =
        read_bounded_regular_file(&imported.join("mgt-import-receipt.json"), MAX_MODEL_BYTES)?;
    let reproduced = execute_native_mgt_import(&mgt_source, parsed_model.model_id())
        .map_err(|error| input_error("workbench_mgt_revalidation_failed", &error))?;
    let reproduced_exact = reproduced.is_normalized()
        && reproduced.source_bytes() == mgt_source
        && reproduced
            .model_ir_json()
            .is_some_and(|value| value.as_bytes() == model)
        && reproduced.health_json().as_bytes() == mgt_health
        && reproduced
            .validation_json()
            .is_some_and(|value| value.as_bytes() == mgt_validation)
        && reproduced
            .snapshot_json()
            .is_some_and(|value| value.as_bytes() == mgt_snapshot)
        && reproduced.receipt_json().as_bytes() == mgt_receipt;
    let source_hash = sha256_identity(&mgt_source);
    let health_hash = sha256_identity(&mgt_health);
    let receipt_hash = sha256_identity(&mgt_receipt);
    if !reproduced_exact
        || session.mgt_source_hash.as_deref() != Some(source_hash.as_str())
        || session.mgt_import_health_artifact_hash.as_deref() != Some(health_hash.as_str())
        || session.mgt_import_receipt_artifact_hash.as_deref() != Some(receipt_hash.as_str())
    {
        return Err(WorkbenchError::new(
            "workbench_mgt_import_binding_mismatch",
            "original MGT bytes or deterministic import/C++ validation evidence changed",
        ));
    }
    Ok(Some(json!({
        "source_hash": source_hash,
        "health_artifact_hash": health_hash,
        "receipt_artifact_hash": receipt_hash,
    })))
}

fn verify_stage_chain(
    root: &Path,
    expected_session_id: &str,
) -> Result<DiscoveredState, WorkbenchError> {
    let stages = [
        (
            WorkbenchStageV1::Imported,
            IMPORT_DIRECTORY,
            "import-receipt.json",
        ),
        (
            WorkbenchStageV1::Validated,
            VALIDATION_DIRECTORY,
            "validation-receipt.json",
        ),
        (
            WorkbenchStageV1::Checkpointed,
            RUN_DIRECTORY,
            "run-receipt.json",
        ),
        (
            WorkbenchStageV1::Terminal,
            RESUME_DIRECTORY,
            "run-receipt.json",
        ),
        (
            WorkbenchStageV1::Compared,
            COMPARISON_DIRECTORY,
            "comparison-receipt.json",
        ),
        (
            WorkbenchStageV1::Reported,
            REPORT_DIRECTORY,
            "pdf-receipt.json",
        ),
    ];
    let mut discovered = WorkbenchStageV1::Imported;
    let mut gap = false;
    let mut terminal_status = None;
    let mut comparison_passed = None;
    for (stage, directory, receipt) in stages {
        let path = root.join(directory);
        if !path.exists() {
            gap = true;
            continue;
        }
        if gap {
            return Err(WorkbenchError::new(
                "workbench_stage_gap",
                format!("atomic stage directory {directory} exists after a missing predecessor"),
            ));
        }
        verify_directory(&path, "workbench_stage_directory_invalid")?;
        let receipt_value = verify_receipt_directory(&path, receipt)?;
        let (terminal, comparison) =
            verify_stage_receipt(stage, directory, &receipt_value, expected_session_id)?;
        if terminal.is_some() {
            terminal_status = terminal;
        }
        if comparison.is_some() {
            comparison_passed = comparison;
        }
        discovered = stage;
    }
    Ok(DiscoveredState {
        stage: discovered,
        terminal_status,
        comparison_passed,
    })
}

fn verify_stage_receipt(
    stage: WorkbenchStageV1,
    directory: &str,
    receipt: &Value,
    expected_session_id: &str,
) -> Result<(Option<String>, Option<bool>), WorkbenchError> {
    if receipt
        .get("session_id")
        .and_then(Value::as_str)
        .is_some_and(|session_id| session_id != expected_session_id)
    {
        return Err(WorkbenchError::new(
            "workbench_stage_session_mismatch",
            format!("stage {directory} belongs to a different Workbench session"),
        ));
    }
    let status = receipt.get("status").and_then(Value::as_str);
    let expected = match stage {
        WorkbenchStageV1::Imported => Some("imported"),
        WorkbenchStageV1::Validated => Some("validated"),
        WorkbenchStageV1::Checkpointed => Some("checkpointed"),
        WorkbenchStageV1::Terminal | WorkbenchStageV1::Compared | WorkbenchStageV1::Reported => {
            None
        }
    };
    if expected.is_some() && status != expected {
        return Err(WorkbenchError::new(
            "workbench_stage_receipt_invalid",
            format!("stage {directory} receipt has an invalid status"),
        ));
    }
    let terminal = if stage == WorkbenchStageV1::Terminal {
        Some(
            status
                .filter(|value| matches!(*value, "completed" | "collapsed"))
                .ok_or_else(|| {
                    WorkbenchError::new(
                        "workbench_terminal_receipt_invalid",
                        "terminal run receipt must say completed or collapsed",
                    )
                })?
                .to_owned(),
        )
    } else {
        None
    };
    let comparison = if stage == WorkbenchStageV1::Compared {
        Some(
            status
                .filter(|value| matches!(*value, "passed" | "diverged"))
                .ok_or_else(|| {
                    WorkbenchError::new(
                        "workbench_comparison_receipt_invalid",
                        "comparison receipt must say passed or diverged",
                    )
                })?
                == "passed",
        )
    } else {
        None
    };
    Ok((terminal, comparison))
}

fn verify_receipt_directory(directory: &Path, receipt_name: &str) -> Result<Value, WorkbenchError> {
    let receipt_bytes =
        read_bounded_regular_file(&directory.join(receipt_name), MAX_PRODUCT_ARTIFACT_BYTES)?;
    let receipt = verify_self_hashed_json(&receipt_bytes, "receipt_hash")?;
    let artifacts = receipt
        .get("artifacts")
        .and_then(Value::as_array)
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_receipt_inventory_invalid",
                "stage receipt has no artifact inventory",
            )
        })?;
    for artifact in artifacts {
        let file = artifact
            .get("file")
            .and_then(Value::as_str)
            .ok_or_else(|| {
                WorkbenchError::new(
                    "workbench_receipt_inventory_invalid",
                    "artifact inventory entry has no file",
                )
            })?;
        if !valid_flat_file_name(file) {
            return Err(WorkbenchError::new(
                "workbench_receipt_inventory_invalid",
                "artifact inventory contains a non-flat file name",
            ));
        }
        let expected_hash = artifact
            .get("content_hash")
            .and_then(Value::as_str)
            .ok_or_else(|| {
                WorkbenchError::new(
                    "workbench_receipt_inventory_invalid",
                    "artifact inventory entry has no content hash",
                )
            })?;
        let expected_length = artifact
            .get("byte_length")
            .and_then(Value::as_u64)
            .ok_or_else(|| {
                WorkbenchError::new(
                    "workbench_receipt_inventory_invalid",
                    "artifact inventory entry has no byte length",
                )
            })?;
        let bytes = read_bounded_regular_file(&directory.join(file), MAX_PRODUCT_ARTIFACT_BYTES)?;
        let actual_length = u64::try_from(bytes.len()).map_err(|_| {
            WorkbenchError::new(
                "workbench_artifact_length_invalid",
                "artifact length does not fit the receipt contract",
            )
        })?;
        if expected_length != actual_length || expected_hash != sha256_identity(&bytes) {
            return Err(WorkbenchError::new(
                "workbench_artifact_inventory_mismatch",
                format!("artifact {file} differs from its stage receipt"),
            ));
        }
    }
    Ok(receipt)
}

fn parse_session(bytes: &[u8]) -> Result<WorkbenchSessionV1, WorkbenchError> {
    let value = verify_self_hashed_json(bytes, "session_hash")?;
    let session: WorkbenchSessionV1 = serde_json::from_value(value).map_err(|_| {
        WorkbenchError::new(
            "workbench_session_decode_failed",
            "session fields are missing, mistyped or unknown",
        )
    })?;
    if session.schema_version != SESSION_SCHEMA_V1 || session.claim_boundary != CLAIM_BOUNDARY {
        return Err(WorkbenchError::new(
            "workbench_session_contract_invalid",
            "session schema or claim boundary is unsupported",
        ));
    }
    Ok(session)
}

fn canonical_session(session: &WorkbenchSessionV1) -> Result<String, WorkbenchError> {
    let mut value = serde_json::to_value(session).map_err(|_| {
        WorkbenchError::new(
            "workbench_session_serialization_failed",
            "session could not be projected to JSON",
        )
    })?;
    value
        .as_object_mut()
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_session_serialization_failed",
                "session projection is not an object",
            )
        })?
        .remove("session_hash");
    let unsigned = canonical_json(&value, "workbench_session_canonicalization_failed")?;
    value
        .as_object_mut()
        .expect("checked session object")
        .insert(
            "session_hash".to_owned(),
            Value::String(sha256_identity(unsigned.as_bytes())),
        );
    canonical_json(&value, "workbench_session_canonicalization_failed")
}

fn canonical_self_hashed(mut value: Value) -> Result<String, WorkbenchError> {
    let object = value.as_object_mut().ok_or_else(|| {
        WorkbenchError::new(
            "workbench_receipt_serialization_failed",
            "receipt projection is not an object",
        )
    })?;
    object.remove("receipt_hash");
    let unsigned = canonical_json(&value, "workbench_receipt_canonicalization_failed")?;
    value
        .as_object_mut()
        .expect("checked receipt object")
        .insert(
            "receipt_hash".to_owned(),
            Value::String(sha256_identity(unsigned.as_bytes())),
        );
    canonical_json(&value, "workbench_receipt_canonicalization_failed")
}

fn verify_self_hashed_json(bytes: &[u8], hash_field: &str) -> Result<Value, WorkbenchError> {
    let mut value = decode_json_strict(bytes)
        .map_err(|error| input_error("workbench_hashed_json_invalid", &error))?;
    let canonical = canonical_json(&value, "workbench_hashed_json_canonicalization_failed")?;
    if canonical.as_bytes() != bytes {
        return Err(WorkbenchError::new(
            "workbench_hashed_json_noncanonical",
            "durable JSON bytes are not the exact canonical representation",
        ));
    }
    let expected = value
        .as_object_mut()
        .and_then(|object| object.remove(hash_field))
        .and_then(|item| item.as_str().map(ToOwned::to_owned))
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_hashed_json_missing_hash",
                format!("durable JSON has no {hash_field}"),
            )
        })?;
    let unsigned = canonical_json(&value, "workbench_hashed_json_canonicalization_failed")?;
    if expected != sha256_identity(unsigned.as_bytes()) {
        return Err(WorkbenchError::new(
            "workbench_hashed_json_hash_mismatch",
            format!("durable JSON {hash_field} does not verify"),
        ));
    }
    value
        .as_object_mut()
        .expect("verified JSON object")
        .insert(hash_field.to_owned(), Value::String(expected));
    Ok(value)
}

fn receipt_status(receipt_json: &str) -> Result<String, WorkbenchError> {
    let value = verify_self_hashed_json(receipt_json.as_bytes(), "receipt_hash")?;
    value
        .get("status")
        .and_then(Value::as_str)
        .filter(|status| matches!(*status, "completed" | "collapsed"))
        .map(ToOwned::to_owned)
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_terminal_receipt_invalid",
                "terminal outcome has no supported status",
            )
        })
}

fn artifact_entry(
    role: &str,
    file: &str,
    media_type: &str,
    bytes: &[u8],
) -> Result<Value, WorkbenchError> {
    Ok(json!({
        "role": role,
        "file": file,
        "media_type": media_type,
        "byte_length": u64::try_from(bytes.len()).map_err(|_| WorkbenchError::new(
            "workbench_artifact_length_invalid",
            "artifact length exceeds the receipt representation",
        ))?,
        "content_hash": sha256_identity(bytes),
    }))
}

fn canonical_json(value: &Value, code: &'static str) -> Result<String, WorkbenchError> {
    canonicalize_model_ir_v2(value).map_err(|error| WorkbenchError::new(code, error.to_string()))
}

fn input_error(code: &'static str, error: &impl fmt::Display) -> WorkbenchError {
    WorkbenchError::new(code, error.to_string())
}

fn publish_initial_workspace(
    root: &Path,
    artifacts: &[(&str, &[u8])],
    executable_artifact: Option<&[u8]>,
    import_receipt: &[u8],
    session_json: &[u8],
) -> Result<(), WorkbenchError> {
    let parent = output_parent(root);
    let output_name = output_name(root)?;
    let temporary = temporary_path(parent, output_name);
    fs::create_dir(&temporary)
        .map_err(|error| io_error("create Workbench temporary root", &error))?;
    let result = (|| {
        let import = temporary.join(IMPORT_DIRECTORY);
        fs::create_dir(&import)
            .map_err(|error| io_error("create Workbench import directory", &error))?;
        for (name, bytes) in artifacts {
            write_synced_new_file(&import.join(name), bytes)?;
        }
        if let Some(bytes) = executable_artifact {
            write_synced_new_file(&import.join("external-executable.artifact"), bytes)?;
        }
        write_synced_new_file(&import.join("import-receipt.json"), import_receipt)?;
        sync_directory(&import, "sync Workbench import directory")?;
        write_synced_new_file(&temporary.join(SESSION_FILE), session_json)?;
        sync_directory(&temporary, "sync Workbench temporary root")?;
        fs::rename(&temporary, root).map_err(|error| io_error("publish Workbench root", &error))?;
        sync_directory(parent, "sync Workbench output parent")
    })();
    if result.is_err() {
        let _ignored = fs::remove_dir_all(&temporary);
    }
    result
}

fn publish_new_directory(output: &Path, artifacts: &[(&str, &[u8])]) -> Result<(), WorkbenchError> {
    if output.exists() {
        return Err(WorkbenchError::new(
            "workbench_stage_destination_exists",
            "stage output directory already exists",
        ));
    }
    let parent = output_parent(output);
    verify_directory(parent, "workbench_stage_parent_invalid")?;
    let output_name = output_name(output)?;
    let temporary = temporary_path(parent, output_name);
    fs::create_dir(&temporary)
        .map_err(|error| io_error("create Workbench stage temporary directory", &error))?;
    let result = (|| {
        for (name, bytes) in artifacts {
            if !valid_flat_file_name(name) {
                return Err(WorkbenchError::new(
                    "workbench_artifact_name_invalid",
                    "stage artifact must use a flat fixed file name",
                ));
            }
            write_synced_new_file(&temporary.join(name), bytes)?;
        }
        sync_directory(&temporary, "sync Workbench stage temporary directory")?;
        fs::rename(&temporary, output)
            .map_err(|error| io_error("publish Workbench stage directory", &error))?;
        sync_directory(parent, "sync Workbench stage parent")
    })();
    if result.is_err() {
        let _ignored = fs::remove_dir_all(&temporary);
    }
    result
}

fn write_atomic_file(path: &Path, bytes: &[u8]) -> Result<(), WorkbenchError> {
    let parent = output_parent(path);
    verify_directory(parent, "workbench_session_parent_invalid")?;
    let name = output_name(path)?;
    let temporary = temporary_path(parent, name);
    write_synced_new_file(&temporary, bytes)?;
    let result = fs::rename(&temporary, path)
        .map_err(|error| io_error("atomically replace Workbench session", &error));
    if result.is_err() {
        let _ignored = fs::remove_file(&temporary);
        return result;
    }
    sync_directory(parent, "sync Workbench session parent")
}

fn write_synced_new_file(path: &Path, bytes: &[u8]) -> Result<(), WorkbenchError> {
    let mut file = OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(path)
        .map_err(|error| io_error("create Workbench artifact", &error))?;
    file.write_all(bytes)
        .map_err(|error| io_error("write Workbench artifact", &error))?;
    file.sync_all()
        .map_err(|error| io_error("sync Workbench artifact", &error))
}

fn read_bounded_regular_file(path: &Path, maximum_bytes: u64) -> Result<Vec<u8>, WorkbenchError> {
    let metadata = fs::symlink_metadata(path)
        .map_err(|error| io_error("read Workbench artifact metadata", &error))?;
    if metadata.file_type().is_symlink() || !metadata.file_type().is_file() {
        return Err(WorkbenchError::new(
            "workbench_artifact_not_regular",
            "artifact must be a regular non-symlink file",
        ));
    }
    if metadata.len() > maximum_bytes {
        return Err(WorkbenchError::new(
            "workbench_artifact_too_large",
            "artifact exceeds its bounded byte limit",
        ));
    }
    let mut options = OpenOptions::new();
    options.read(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.custom_flags(libc::O_NOFOLLOW);
    }
    let file = options
        .open(path)
        .map_err(|error| io_error("open Workbench artifact without symlink traversal", &error))?;
    let opened = file
        .metadata()
        .map_err(|error| io_error("read opened Workbench artifact metadata", &error))?;
    if !opened.is_file() || opened.len() > maximum_bytes {
        return Err(WorkbenchError::new(
            "workbench_artifact_changed",
            "opened artifact is not the same bounded regular file class",
        ));
    }
    let capacity = usize::try_from(opened.len().min(maximum_bytes)).map_err(|_| {
        WorkbenchError::new(
            "workbench_artifact_length_invalid",
            "artifact length does not fit addressable memory",
        )
    })?;
    let mut bytes = Vec::with_capacity(capacity);
    file.take(maximum_bytes.saturating_add(1))
        .read_to_end(&mut bytes)
        .map_err(|error| io_error("read Workbench artifact", &error))?;
    if u64::try_from(bytes.len()).map_or(true, |length| length > maximum_bytes) {
        return Err(WorkbenchError::new(
            "workbench_artifact_changed",
            "artifact changed beyond its bounded byte limit while reading",
        ));
    }
    Ok(bytes)
}

fn verify_slice_bound(bytes: &[u8], maximum_bytes: u64, label: &str) -> Result<(), WorkbenchError> {
    let length = u64::try_from(bytes.len()).map_err(|_| {
        WorkbenchError::new(
            "workbench_artifact_length_invalid",
            format!("{label} length does not fit the bounded contract"),
        )
    })?;
    if length > maximum_bytes {
        return Err(WorkbenchError::new(
            "workbench_artifact_too_large",
            format!("{label} exceeds its bounded byte limit"),
        ));
    }
    Ok(())
}

fn verify_directory(path: &Path, code: &'static str) -> Result<(), WorkbenchError> {
    let metadata =
        fs::symlink_metadata(path).map_err(|error| io_error("read directory metadata", &error))?;
    if metadata.file_type().is_symlink() || !metadata.file_type().is_dir() {
        return Err(WorkbenchError::new(
            code,
            "path must be a real non-symlink directory",
        ));
    }
    Ok(())
}

fn sync_directory(path: &Path, action: &'static str) -> Result<(), WorkbenchError> {
    File::open(path)
        .and_then(|directory| directory.sync_all())
        .map_err(|error| io_error(action, &error))
}

fn output_parent(path: &Path) -> &Path {
    path.parent()
        .filter(|parent| !parent.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."))
}

fn output_name(path: &Path) -> Result<&str, WorkbenchError> {
    path.file_name()
        .and_then(|name| name.to_str())
        .filter(|name| !name.is_empty())
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_output_name_invalid",
                "output path has no valid UTF-8 file name",
            )
        })
}

fn temporary_path(parent: &Path, name: &str) -> PathBuf {
    let sequence = OUTPUT_SEQUENCE.fetch_add(1, Ordering::Relaxed);
    parent.join(format!(".{name}.tmp.{}.{}", std::process::id(), sequence))
}

fn valid_flat_file_name(name: &str) -> bool {
    !name.is_empty() && name != "." && name != ".." && !name.contains('/') && !name.contains('\\')
}

fn io_error(action: &str, error: &std::io::Error) -> WorkbenchError {
    WorkbenchError::new("workbench_io_error", format!("{action} failed: {error}"))
}

#[cfg(test)]
mod tests {
    use super::{canonical_session, parse_session, WorkbenchSessionV1, WorkbenchStageV1};

    #[test]
    fn session_hash_round_trip_is_strict_and_deterministic() {
        let session = WorkbenchSessionV1 {
            schema_version: super::SESSION_SCHEMA_V1.to_owned(),
            session_id: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                .to_owned(),
            stage: WorkbenchStageV1::Imported,
            source_model_ir_hash:
                "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb".to_owned(),
            model_content_hash:
                "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc".to_owned(),
            model_semantic_hash:
                "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd".to_owned(),
            model_provenance_hash:
                "sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee".to_owned(),
            analysis_request_hash:
                "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff".to_owned(),
            external_result_hash:
                "sha256:1111111111111111111111111111111111111111111111111111111111111111".to_owned(),
            source_artifact_hash:
                "sha256:2222222222222222222222222222222222222222222222222222222222222222".to_owned(),
            executable_artifact_hash: None,
            mgt_source_hash: None,
            mgt_import_health_artifact_hash: None,
            mgt_import_receipt_artifact_hash: None,
            terminal_status: None,
            comparison_passed: None,
            claim_boundary: super::CLAIM_BOUNDARY.to_owned(),
            session_hash: String::new(),
        };
        let first = canonical_session(&session).expect("canonical session");
        let restored = parse_session(first.as_bytes()).expect("verified session");
        let second = canonical_session(&restored).expect("re-canonical session");
        assert_eq!(first, second);

        let mut tampered = first.into_bytes();
        let offset = tampered
            .windows("imported".len())
            .position(|window| window == b"imported")
            .expect("stage token");
        tampered[offset] = b'I';
        assert!(parse_session(&tampered).is_err());
    }
}
