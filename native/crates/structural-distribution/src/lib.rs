use std::collections::BTreeSet;
use std::fmt;
use std::fs::{self, File, OpenOptions};
use std::io::{self, BufReader, BufWriter, Read, Write};
use std::path::{Component, Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

use fs2::FileExt;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

const MANIFEST_NAME: &str = "structural-distribution.json";
const PAYLOAD_DIRECTORY: &str = "payload";
const RELEASES_DIRECTORY: &str = "releases";
const STATE_DIRECTORY: &str = "state";
const ACTIVATION_NAME: &str = "activation.json";
const TRANSACTION_NAME: &str = "transaction.json";
const LOCK_NAME: &str = ".structural-install.lock";
const SCHEMA_VERSION: &str = "structural-distribution.v1";
const ACTIVATION_SCHEMA_VERSION: &str = "structural-activation.v1";
const TRANSACTION_SCHEMA_VERSION: &str = "structural-install-transaction.v1";
const BUILD_SCHEMA_VERSION: &str = "structural-native-build.v1";
const ABI_VERSION: &str = "0x0001000e";
const MAX_MANIFEST_BYTES: u64 = 16 * 1024 * 1024;
const MAX_FILE_COUNT: usize = 16_384;
const MAX_FILE_BYTES: u64 = 2 * 1024 * 1024 * 1024;
const MAX_TOTAL_BYTES: u64 = 8 * 1024 * 1024 * 1024;
const ROOTFS_RECEIPT_SCHEMA_VERSION_V1: &str = "structural-native-rootfs-isolation-e2e.v1";
const ROOTFS_RECEIPT_SCHEMA_VERSION_V2: &str = "structural-native-rootfs-isolation-e2e.v2";
const ROOTFS_RECEIPT_SCHEMA_VERSION_V3: &str = "structural-native-rootfs-isolation-e2e.v3";
const ROOTFS_RECEIPT_SCHEMA_VERSION_V4: &str = "structural-native-rootfs-isolation-e2e.v4";
const ROOTFS_RECEIPT_SCHEMA_VERSION_V5: &str = "structural-native-rootfs-isolation-e2e.v5";
const ROOTFS_RECEIPT_SCHEMA_VERSION_V6: &str = "structural-native-rootfs-isolation-e2e.v6";
const ROOTFS_RECEIPT_SCHEMA_VERSION_V7: &str = "structural-native-rootfs-isolation-e2e.v7";
const ROOTFS_RECEIPT_SCHEMA_VERSION_V8: &str = "structural-native-rootfs-isolation-e2e.v8";
const ROOTFS_RECEIPT_SCHEMA_VERSION_V9: &str = "structural-native-rootfs-isolation-e2e.v9";
const ROOTFS_RECEIPT_SCHEMA_VERSION_V10: &str = "structural-native-rootfs-isolation-e2e.v10";
const ROOTFS_RECEIPT_SCHEMA_VERSION_V11: &str = "structural-native-rootfs-isolation-e2e.v11";
const ROOTFS_RECEIPT_SCHEMA_VERSION_V12: &str = "structural-native-rootfs-isolation-e2e.v12";
const ROOTFS_RECEIPT_SCHEMA_VERSION: &str = "structural-native-rootfs-isolation-e2e.v13";
const ROOTFS_RECEIPT_AUTHORITY: &str = "local_rootfs_diagnostic_c5";
const ROOTFS_ISOLATION_TECHNOLOGY: &str = "linux_user_mount_network_namespaces";
const ROOTFS_EMPTY_PATH: &str = "/nonexistent";
const ROOTFS_RUNTIME_UID: u32 = 65_532;
const ROOTFS_RUNTIME_GID: u32 = 65_532;
const ROOTFS_REVIEWER: &str = "native-rootfs-c5";
const ROOTFS_REVIEW_COMMENT: &str =
    "Explicit isolated C5 handoff review; no engineering approval is inferred.";
const MODEL_IR_ENGINEERING_LOCALIZED_PDF_RECEIPT_SCHEMA: &str =
    "structural-native-model-ir-linear-engineering-localized-pdf-report-receipt.v3";
const MODEL_IR_ENGINEERING_LOCALIZED_PDF_PROFILE: &str =
    "model_ir_linear_cpu_engineering_summary_v1";
const MODEL_IR_ENGINEERING_LOCALIZED_PDF_CLAIM_BOUNDARY: &str = "inventory_for_one_deterministic_modelir_linear_result_recovery_reaction_bound_engineering_summary_pdf_not_a_complete_member_schedule_force_diagram_pdf_ua_accessibility_engineering_acceptance_or_design_code_compliance";
const ROOTFS_RECEIPT_CLAIM_BOUNDARY_V1: &str = "This source-bound local C5 diagnostic proves the verified native CPU bundle executed ModelIR and MGT Workbench flows as UID/GID 65532 with an empty PATH, a read-only root and payload, a writable operator workspace, and no non-loopback network interface. It is not an OCI image build, vulnerability scan, SBOM attestation, signature, customer import, protected HIP receipt, or C6 decommission receipt.";
const ROOTFS_RECEIPT_CLAIM_BOUNDARY_V2: &str = "This source-bound local C5 diagnostic proves the verified native CPU bundle executed ModelIR and MGT Workbench flows plus deterministic inspect, explicit non-promoting review, review reopen, and handoff export as UID/GID 65532 with an empty PATH, a read-only root and payload, a writable operator workspace, and no non-loopback network interface. It is not an OCI image build, vulnerability scan, SBOM attestation, signature, customer import, protected HIP receipt, engineering approval, or C6 decommission receipt.";
const ROOTFS_RECEIPT_CLAIM_BOUNDARY_V3: &str = "This source-bound local C5 diagnostic proves the verified native CPU bundle executed ModelIR and MGT Workbench flows plus deterministic inspect, explicit non-promoting review, review reopen, handoff export, embedded benchmark catalog browsing, and hash-bound copied evidence-bundle browsing as UID/GID 65532 with an empty PATH, a read-only root and payload, a writable operator workspace, and no non-loopback network interface. It does not generate or approve evidence and is not an OCI image build, vulnerability scan, SBOM attestation, signature, customer import, protected HIP receipt, engineering approval, or C6 decommission receipt.";
const ROOTFS_RECEIPT_CLAIM_BOUNDARY_V4: &str = "This source-bound local C5 diagnostic proves the verified native CPU bundle executed ModelIR, MGT and ModelIR-linear Workbench flows plus deterministic inspect, explicit non-promoting review, review reopen, handoff export, embedded benchmark catalog browsing, and hash-bound copied evidence-bundle browsing as UID/GID 65532 with an empty PATH, a read-only root and payload, a writable operator workspace, and no non-loopback network interface. The linear flow binds typed recovery, external comparison, deterministic PDF, document source and PDF/report receipts. It does not generate or approve evidence and is not an OCI image build, vulnerability scan, SBOM attestation, signature, customer import, protected HIP receipt, engineering approval, or C6 decommission receipt.";
const ROOTFS_RECEIPT_CLAIM_BOUNDARY_V5: &str = "This source-bound local C5 diagnostic proves the verified native CPU bundle executed ModelIR, MGT and ModelIR-linear Workbench flows plus deterministic inspect, explicit non-promoting review, review reopen, handoff export, embedded benchmark catalog browsing, hash-bound copied evidence-bundle browsing, and repeated en-US/ko-KR embedded-font sparse-linear PDF export as UID/GID 65532 with an empty PATH, a read-only root and payload, a writable operator workspace, and no non-loopback network interface. The linear flow binds typed recovery, external comparison, deterministic PDF, document source, PDF/report receipts, localized PDF/receipt identities, exact installed font/license/provenance and durable-session nonmutation. It does not generate or approve evidence and is not an OCI image build, vulnerability scan, SBOM attestation, signature, customer import, protected HIP receipt, engineering approval, or C6 decommission receipt.";
const ROOTFS_RECEIPT_CLAIM_BOUNDARY_V6: &str = "This source-bound local C5 diagnostic proves the verified native CPU bundle executed ModelIR, MGT, ModelIR-linear and normalized-MGT-to-ModelIR-linear Workbench flows plus deterministic inspect, explicit non-promoting review, review reopen, handoff export, embedded benchmark catalog browsing, hash-bound copied evidence-bundle browsing, and repeated en-US/ko-KR embedded-font sparse-linear PDF export as UID/GID 65532 with an empty PATH, a read-only root and payload, a writable operator workspace, and no non-loopback network interface. The exact MGT-linear flow binds original source bytes, normalized import health, typed recovery, external comparison, deterministic PDF, document source and PDF/report receipts. The ModelIR-linear flow also binds localized PDF/receipt identities, exact installed font/license/provenance and durable-session nonmutation. It does not generate or approve evidence and is not an OCI image build, vulnerability scan, SBOM attestation, signature, general customer import, protected HIP receipt, engineering approval, or C6 decommission receipt.";
const ROOTFS_RECEIPT_CLAIM_BOUNDARY_V7: &str = "This source-bound local C5 diagnostic proves the verified native CPU bundle executed ModelIR, MGT, ModelIR-linear and normalized-MGT-to-ModelIR-linear Workbench flows plus deterministic inspect, explicit non-promoting review, review reopen, handoff export, embedded benchmark catalog browsing, hash-bound copied evidence-bundle browsing, and repeated en-US/ko-KR embedded-font sparse-linear PDF export as UID/GID 65532 with an empty PATH, a read-only root and payload, a writable operator workspace, and no non-loopback network interface. Both exact linear flows bind typed recovery and constrained-reaction ResultIR through review and handoff export; the MGT-linear flow also binds original source bytes and normalized import health. The receipt additionally binds external comparison, deterministic PDF, document source, PDF/report receipts, localized PDF identities, exact installed font/license/provenance and durable-session nonmutation. It does not generate or approve evidence and is not an OCI image build, vulnerability scan, SBOM attestation, signature, general customer import, protected HIP receipt, engineering approval, or C6 decommission receipt.";
const ROOTFS_RECEIPT_CLAIM_BOUNDARY_V8: &str = "This source-bound local C5 diagnostic proves the verified native CPU bundle executed ModelIR, MGT, ModelIR-linear and normalized-MGT-to-ModelIR-linear Workbench flows plus deterministic inspect, explicit non-promoting review, review reopen, handoff export, embedded benchmark catalog browsing, hash-bound copied evidence-bundle browsing, repeated en-US/ko-KR embedded-font sparse-linear PDF export, and deterministic self-hashed en-US/ko-KR constrained-reaction views as UID/GID 65532 with an empty PATH, a read-only root and payload, a writable operator workspace, and no non-loopback network interface. Both exact linear flows bind typed recovery, constrained-reaction ResultIR and repeated reaction-view identities through review and handoff export; the strict ModelIR-linear surface also binds a bounded reaction-view window, both durable sessions remain unmodified, and the NDTHA profile is rejected. The MGT-linear flow also binds original source bytes and normalized import health. The receipt additionally binds external comparison, deterministic PDF, document source, PDF/report receipts, localized PDF identities, exact installed font/license/provenance and durable-session nonmutation. It does not generate or approve evidence and is not an OCI image build, vulnerability scan, SBOM attestation, signature, general customer import, protected HIP receipt, engineering approval, or C6 decommission receipt.";
const ROOTFS_RECEIPT_CLAIM_BOUNDARY_V9: &str = "This source-bound local C5 diagnostic proves the verified native CPU bundle executed ModelIR, MGT, ModelIR-linear and normalized-MGT-to-ModelIR-linear Workbench flows plus deterministic inspect, explicit non-promoting review, review reopen, handoff export, embedded benchmark catalog browsing, hash-bound copied evidence-bundle browsing, repeated en-US/ko-KR embedded-font sparse-linear PDF export, deterministic constrained-reaction views, and deterministic self-hashed en-US/ko-KR algebraic global reaction audits as UID/GID 65532 with an empty PATH, a read-only root and payload, a writable operator workspace, and no non-loopback network interface. Both exact linear flows bind typed recovery, constrained-reaction ResultIR, reaction views and independently verified force, global-origin moment and active-equation numeric closure; both durable sessions remain unmodified and the NDTHA profile is rejected. The MGT-linear audit retains visible nonzero FP64 roundoff within the fixed tolerance policy, original source bytes and normalized import health. The receipt additionally binds external comparison, deterministic PDF, document source, PDF/report receipts, localized PDF identities, exact installed font/license/provenance and durable-session nonmutation. It is not a support-design, stability, engineering-acceptance or HIP-parity receipt, does not generate or approve evidence, and is not an OCI image build, vulnerability scan, SBOM attestation, signature, general customer import, protected HIP receipt, or C6 decommission receipt.";
const ROOTFS_RECEIPT_CLAIM_BOUNDARY_V10: &str = "This source-bound local C5 diagnostic proves the verified native CPU bundle executed ModelIR, MGT, ModelIR-linear and normalized-MGT-to-ModelIR-linear Workbench flows plus deterministic inspect, explicit non-promoting review, review reopen, handoff export, embedded benchmark catalog browsing, hash-bound copied evidence-bundle browsing, repeated en-US/ko-KR embedded-font sparse-linear PDF export, deterministic constrained-reaction views, deterministic algebraic global reaction audits, and deterministic self-hashed en-US/ko-KR bounded nodal-displacement views as UID/GID 65532 with an empty PATH, a read-only root and payload, a writable operator workspace, and no non-loopback network interface. Both exact linear flows bind typed recovery, constrained-reaction ResultIR, reaction views, reaction audits and exact six-component nodal displacement rows; a strict-ModelIR bounded displacement window is distinct, both durable sessions remain unmodified, and the NDTHA profile is rejected. The MGT-linear evidence retains original source bytes, normalized import health and visible nonzero reaction-audit FP64 roundoff within the fixed tolerance policy. The receipt additionally binds external comparison, deterministic PDF, document source, PDF/report receipts, localized PDF identities, exact installed font/license/provenance and durable-session nonmutation. It is not a deformed-shape, stress, contour, modal, serviceability, support-design, engineering-acceptance or HIP-parity receipt, does not generate or approve evidence, and is not an OCI image build, vulnerability scan, SBOM attestation, signature, general customer import, protected HIP receipt, or C6 decommission receipt.";
const ROOTFS_RECEIPT_CLAIM_BOUNDARY_V11: &str = "This source-bound local C5 diagnostic proves the verified native CPU bundle executed the exact strict-ModelIR-linear and normalized-MGT-to-ModelIR-linear Workbench flows with deterministic self-hashed en-US/ko-KR bounded two-node original/deformed centerline projections as UID/GID 65532 with an empty PATH, a read-only root and payload, a writable operator workspace, and no non-loopback network interface. The view applies recovered UX/UY/UZ translation at a fixed visual scale, reports but does not apply RX/RY/RZ, binds backend and all model/result/recovery/execution identities, proves repeated output from resumed durable terminal sessions, preserves both sessions, distinguishes a strict-ModelIR alternate projection and rejects invalid linear state selection. It retains all v10 reaction, audit, displacement, import, comparison, PDF, report, review, catalog and evidence diagnostics. It is not member curvature, rigid-offset rotation, stress, contour, modal, serviceability, support-design, engineering-acceptance or HIP-parity evidence, does not generate or approve evidence, and is not an OCI image build, vulnerability scan, SBOM attestation, signature, general customer import, protected HIP receipt, or C6 decommission receipt.";
const ROOTFS_RECEIPT_CLAIM_BOUNDARY_V12: &str = "This source-bound local C5 diagnostic proves the verified native CPU bundle executed exact strict-ModelIR-linear and normalized-MGT-to-ModelIR-linear Workbench flows with deterministic self-hashed en-US/ko-KR bounded Frame3D element-local end-force views as UID/GID 65532 with an empty PATH, a read-only root and payload, a writable operator workspace, and no non-loopback network interface. Each installed view binds typed recovery, backend and all model/result/recovery/execution identities, proves repeated output and direct/resumed parity, preserves both durable sessions, and rejects an out-of-range element window. It retains all v11 deformed, reaction, audit, displacement, import, comparison, PDF, report, review, catalog and evidence diagnostics. Truss3D row formatting remains source-tested but is not independently exercised by this installed receipt; it is not shell, general stress, contour, design utilization, serviceability, support-design, engineering-acceptance or HIP-parity evidence, does not generate or approve evidence, and is not an OCI image build, vulnerability scan, SBOM attestation, signature, general customer import, protected HIP receipt, or C6 decommission receipt.";
const ROOTFS_RECEIPT_CLAIM_BOUNDARY: &str = "This source-bound local C5 diagnostic proves the verified native CPU bundle authored one exact six-active-DOF Frame3D ModelIR modal request, executed and resumed the installed CPU solver to byte-identical eleven-artifact directories, and rendered deterministic self-hashed en-US/ko-KR read-only modal result views as UID/GID 65532 with an empty PATH, a read-only root and payload, a writable operator workspace, and no non-loopback network interface. The receipt binds the installed structural-cli, request, request receipt, model-bound checkpoint, ResultIR and run receipt, proves repeated locale output, source-directory nonmutation and fail-closed invalid-window rejection, and retains all v12 element-recovery, deformed, reaction, audit, displacement, import, comparison, PDF, report, review, catalog and evidence diagnostics. It is not a durable modal Workbench session, geometric mode-shape, participation-mass, response-spectrum, sparse/buckling, shell, engineering-acceptance or HIP-parity receipt, does not generate or approve evidence, and is not an OCI image build, vulnerability scan, SBOM attestation, signature, general customer import, protected HIP receipt, or C6 decommission receipt.";

static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum BackendProfileV1 {
    CpuOnly,
    Rocm,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum LinkageV1 {
    Shared,
    Static,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DistributionFileV1 {
    pub path: String,
    pub size: u64,
    pub mode: u32,
    pub sha256: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
struct UnsignedDistributionManifestV1 {
    schema_version: String,
    release_id: String,
    package_version: String,
    backend_profile: BackendProfileV1,
    linkage: LinkageV1,
    abi_version: String,
    source_sha256: String,
    execution_authority: String,
    files: Vec<DistributionFileV1>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DistributionManifestV1 {
    pub schema_version: String,
    pub release_id: String,
    pub package_version: String,
    pub backend_profile: BackendProfileV1,
    pub linkage: LinkageV1,
    pub abi_version: String,
    pub source_sha256: String,
    pub execution_authority: String,
    pub files: Vec<DistributionFileV1>,
    pub manifest_hash: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ActivationStateV1 {
    pub schema_version: String,
    pub generation: u64,
    pub current_release: String,
    pub previous_release: Option<String>,
    pub current_manifest_hash: String,
}

#[derive(Clone, Debug)]
pub struct BundleCreateRequest<'a> {
    pub payload_root: &'a Path,
    pub output: &'a Path,
    pub release_id: &'a str,
    pub package_version: &'a str,
    pub backend_profile: BackendProfileV1,
    pub linkage: LinkageV1,
    pub source_sha256: &'a str,
}

#[derive(Clone, Debug)]
pub struct RootfsIsolationProbeRequest<'a> {
    pub bundle: &'a Path,
    pub payload_root: &'a Path,
    pub workspace: &'a Path,
    pub workbench_root: &'a Path,
    pub mgt_workbench_root: &'a Path,
    pub model_ir_linear_workbench_root: &'a Path,
    pub mgt_model_ir_linear_workbench_root: &'a Path,
    pub workbench_inspect_before_review: &'a Path,
    pub workbench_review_show: &'a Path,
    pub workbench_inspect_after_review: &'a Path,
    pub workbench_export: &'a Path,
    pub mgt_workbench_inspect_before_review: &'a Path,
    pub mgt_workbench_review_show: &'a Path,
    pub mgt_workbench_inspect_after_review: &'a Path,
    pub mgt_workbench_export: &'a Path,
    pub model_ir_linear_workbench_inspect_before_review: &'a Path,
    pub model_ir_linear_workbench_review_show: &'a Path,
    pub model_ir_linear_workbench_inspect_after_review: &'a Path,
    pub model_ir_linear_workbench_export: &'a Path,
    pub mgt_model_ir_linear_workbench_inspect_before_review: &'a Path,
    pub mgt_model_ir_linear_workbench_review_show: &'a Path,
    pub mgt_model_ir_linear_workbench_inspect_after_review: &'a Path,
    pub mgt_model_ir_linear_workbench_export: &'a Path,
    pub model_ir_linear_workbench_session_before_localized_pdf: &'a Path,
    pub model_ir_linear_localized_pdf_en_us_first_root: &'a Path,
    pub model_ir_linear_localized_pdf_en_us_second_root: &'a Path,
    pub model_ir_linear_localized_pdf_ko_kr_first_root: &'a Path,
    pub model_ir_linear_localized_pdf_ko_kr_second_root: &'a Path,
    pub model_ir_linear_workbench_session_before_reaction_view: &'a Path,
    pub mgt_model_ir_linear_workbench_session_before_reaction_view: &'a Path,
    pub model_ir_linear_reaction_view_en_us_first: &'a Path,
    pub model_ir_linear_reaction_view_en_us_second: &'a Path,
    pub model_ir_linear_reaction_view_ko_kr_first: &'a Path,
    pub model_ir_linear_reaction_view_ko_kr_second: &'a Path,
    pub model_ir_linear_reaction_view_window: &'a Path,
    pub mgt_model_ir_linear_reaction_view_en_us_first: &'a Path,
    pub mgt_model_ir_linear_reaction_view_en_us_second: &'a Path,
    pub mgt_model_ir_linear_reaction_view_ko_kr_first: &'a Path,
    pub mgt_model_ir_linear_reaction_view_ko_kr_second: &'a Path,
    pub workbench_reaction_view_wrong_profile_failure: &'a Path,
    pub model_ir_linear_reaction_audit_en_us_first: &'a Path,
    pub model_ir_linear_reaction_audit_en_us_second: &'a Path,
    pub model_ir_linear_reaction_audit_ko_kr_first: &'a Path,
    pub model_ir_linear_reaction_audit_ko_kr_second: &'a Path,
    pub mgt_model_ir_linear_reaction_audit_en_us_first: &'a Path,
    pub mgt_model_ir_linear_reaction_audit_en_us_second: &'a Path,
    pub mgt_model_ir_linear_reaction_audit_ko_kr_first: &'a Path,
    pub mgt_model_ir_linear_reaction_audit_ko_kr_second: &'a Path,
    pub workbench_reaction_audit_wrong_profile_failure: &'a Path,
    pub model_ir_linear_nodal_displacement_view_en_us_first: &'a Path,
    pub model_ir_linear_nodal_displacement_view_en_us_second: &'a Path,
    pub model_ir_linear_nodal_displacement_view_ko_kr_first: &'a Path,
    pub model_ir_linear_nodal_displacement_view_ko_kr_second: &'a Path,
    pub model_ir_linear_nodal_displacement_view_window: &'a Path,
    pub mgt_model_ir_linear_nodal_displacement_view_en_us_first: &'a Path,
    pub mgt_model_ir_linear_nodal_displacement_view_en_us_second: &'a Path,
    pub mgt_model_ir_linear_nodal_displacement_view_ko_kr_first: &'a Path,
    pub mgt_model_ir_linear_nodal_displacement_view_ko_kr_second: &'a Path,
    pub workbench_nodal_displacement_view_wrong_profile_failure: &'a Path,
    pub model_ir_linear_deformed_view_en_us_first: &'a Path,
    pub model_ir_linear_deformed_view_en_us_second: &'a Path,
    pub model_ir_linear_deformed_view_ko_kr_first: &'a Path,
    pub model_ir_linear_deformed_view_ko_kr_second: &'a Path,
    pub model_ir_linear_deformed_view_projection: &'a Path,
    pub mgt_model_ir_linear_deformed_view_en_us_first: &'a Path,
    pub mgt_model_ir_linear_deformed_view_en_us_second: &'a Path,
    pub mgt_model_ir_linear_deformed_view_ko_kr_first: &'a Path,
    pub mgt_model_ir_linear_deformed_view_ko_kr_second: &'a Path,
    pub workbench_linear_deformed_view_invalid_step_failure: &'a Path,
    pub model_ir_linear_element_recovery_view_en_us_first: &'a Path,
    pub model_ir_linear_element_recovery_view_en_us_second: &'a Path,
    pub model_ir_linear_element_recovery_view_ko_kr_first: &'a Path,
    pub model_ir_linear_element_recovery_view_ko_kr_second: &'a Path,
    pub mgt_model_ir_linear_element_recovery_view_en_us_first: &'a Path,
    pub mgt_model_ir_linear_element_recovery_view_en_us_second: &'a Path,
    pub mgt_model_ir_linear_element_recovery_view_ko_kr_first: &'a Path,
    pub mgt_model_ir_linear_element_recovery_view_ko_kr_second: &'a Path,
    pub workbench_linear_element_recovery_view_invalid_window_failure: &'a Path,
    pub model_modal_request_root: &'a Path,
    pub model_modal_direct_root: &'a Path,
    pub model_modal_resumed_root: &'a Path,
    pub model_modal_view_source_before: &'a Path,
    pub model_modal_direct_stdout: &'a Path,
    pub model_modal_resumed_stdout: &'a Path,
    pub model_modal_result_view_en_us_first: &'a Path,
    pub model_modal_result_view_en_us_second: &'a Path,
    pub model_modal_result_view_ko_kr_first: &'a Path,
    pub model_modal_result_view_ko_kr_second: &'a Path,
    pub model_modal_result_view_invalid_window_failure: &'a Path,
    pub workbench_catalog: &'a Path,
    pub workbench_evidence: &'a Path,
    pub receipt: &'a Path,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
#[allow(clippy::struct_excessive_bools)]
pub struct RootfsIsolationEvidenceV1 {
    pub authority: String,
    pub claim_boundary: String,
    pub isolation_technology: String,
    pub release_id: String,
    pub source_sha256: String,
    pub bundle_manifest_hash: String,
    pub bundle_manifest_file_sha256: String,
    pub installer_sha256: String,
    pub workbench_sha256: String,
    pub runtime_uid: u32,
    pub runtime_gid: u32,
    pub network_interfaces: Vec<String>,
    pub ipv4_route_count: u64,
    pub rootfs_write_errno: i32,
    pub payload_write_errno: i32,
    pub workspace_write_passed: bool,
    pub path: String,
    pub python_lookup_count: u64,
    pub node_lookup_count: u64,
    pub workbench_version: String,
    pub workbench_stage: String,
    pub workbench_terminal_status: String,
    pub workbench_comparison_passed: bool,
    pub result_ir_sha256: String,
    pub report_pdf_sha256: String,
    pub mgt_workbench_stage: String,
    pub mgt_workbench_terminal_status: String,
    pub mgt_workbench_comparison_passed: bool,
    pub mgt_source_sha256: String,
    pub mgt_import_health_sha256: String,
    pub mgt_result_ir_sha256: String,
    pub mgt_report_pdf_sha256: String,
    pub container_image_built: bool,
    pub customer_image_receipt: bool,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RootfsIsolationReceiptV1 {
    pub schema_version: String,
    pub evidence: RootfsIsolationEvidenceV1,
    pub receipt_hash: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
#[allow(clippy::struct_excessive_bools)]
pub struct RootfsIsolationEvidenceV2 {
    pub authority: String,
    pub claim_boundary: String,
    pub isolation_technology: String,
    pub release_id: String,
    pub source_sha256: String,
    pub bundle_manifest_hash: String,
    pub bundle_manifest_file_sha256: String,
    pub installer_sha256: String,
    pub workbench_sha256: String,
    pub runtime_uid: u32,
    pub runtime_gid: u32,
    pub network_interfaces: Vec<String>,
    pub ipv4_route_count: u64,
    pub rootfs_write_errno: i32,
    pub payload_write_errno: i32,
    pub workspace_write_passed: bool,
    pub path: String,
    pub python_lookup_count: u64,
    pub node_lookup_count: u64,
    pub workbench_version: String,
    pub workbench_stage: String,
    pub workbench_terminal_status: String,
    pub workbench_comparison_passed: bool,
    pub result_ir_sha256: String,
    pub report_pdf_sha256: String,
    pub workbench_operator_surface_passed: bool,
    pub workbench_review_decision: String,
    pub workbench_inspect_before_review_sha256: String,
    pub workbench_review_sha256: String,
    pub workbench_inspect_after_review_sha256: String,
    pub workbench_export_sha256: String,
    pub mgt_workbench_stage: String,
    pub mgt_workbench_terminal_status: String,
    pub mgt_workbench_comparison_passed: bool,
    pub mgt_source_sha256: String,
    pub mgt_import_health_sha256: String,
    pub mgt_result_ir_sha256: String,
    pub mgt_report_pdf_sha256: String,
    pub mgt_workbench_operator_surface_passed: bool,
    pub mgt_workbench_review_decision: String,
    pub mgt_workbench_inspect_before_review_sha256: String,
    pub mgt_workbench_review_sha256: String,
    pub mgt_workbench_inspect_after_review_sha256: String,
    pub mgt_workbench_export_sha256: String,
    pub container_image_built: bool,
    pub customer_image_receipt: bool,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RootfsIsolationReceiptV2 {
    pub schema_version: String,
    pub evidence: RootfsIsolationEvidenceV2,
    pub receipt_hash: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
#[allow(clippy::struct_excessive_bools)]
pub struct RootfsIsolationEvidenceV3 {
    pub authority: String,
    pub claim_boundary: String,
    pub isolation_technology: String,
    pub release_id: String,
    pub source_sha256: String,
    pub bundle_manifest_hash: String,
    pub bundle_manifest_file_sha256: String,
    pub installer_sha256: String,
    pub workbench_sha256: String,
    pub runtime_uid: u32,
    pub runtime_gid: u32,
    pub network_interfaces: Vec<String>,
    pub ipv4_route_count: u64,
    pub rootfs_write_errno: i32,
    pub payload_write_errno: i32,
    pub workspace_write_passed: bool,
    pub path: String,
    pub python_lookup_count: u64,
    pub node_lookup_count: u64,
    pub workbench_version: String,
    pub workbench_stage: String,
    pub workbench_terminal_status: String,
    pub workbench_comparison_passed: bool,
    pub result_ir_sha256: String,
    pub report_pdf_sha256: String,
    pub workbench_operator_surface_passed: bool,
    pub workbench_review_decision: String,
    pub workbench_inspect_before_review_sha256: String,
    pub workbench_review_sha256: String,
    pub workbench_inspect_after_review_sha256: String,
    pub workbench_export_sha256: String,
    pub mgt_workbench_stage: String,
    pub mgt_workbench_terminal_status: String,
    pub mgt_workbench_comparison_passed: bool,
    pub mgt_source_sha256: String,
    pub mgt_import_health_sha256: String,
    pub mgt_result_ir_sha256: String,
    pub mgt_report_pdf_sha256: String,
    pub mgt_workbench_operator_surface_passed: bool,
    pub mgt_workbench_review_decision: String,
    pub mgt_workbench_inspect_before_review_sha256: String,
    pub mgt_workbench_review_sha256: String,
    pub mgt_workbench_inspect_after_review_sha256: String,
    pub mgt_workbench_export_sha256: String,
    pub workbench_catalog_surface_passed: bool,
    pub workbench_catalog_sha256: String,
    pub workbench_evidence_surface_passed: bool,
    pub workbench_evidence_sha256: String,
    pub container_image_built: bool,
    pub customer_image_receipt: bool,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RootfsIsolationReceiptV3 {
    pub schema_version: String,
    pub evidence: RootfsIsolationEvidenceV3,
    pub receipt_hash: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
#[allow(clippy::struct_excessive_bools)]
pub struct RootfsIsolationEvidenceV4 {
    pub authority: String,
    pub claim_boundary: String,
    pub isolation_technology: String,
    pub release_id: String,
    pub source_sha256: String,
    pub bundle_manifest_hash: String,
    pub bundle_manifest_file_sha256: String,
    pub installer_sha256: String,
    pub workbench_sha256: String,
    pub runtime_uid: u32,
    pub runtime_gid: u32,
    pub network_interfaces: Vec<String>,
    pub ipv4_route_count: u64,
    pub rootfs_write_errno: i32,
    pub payload_write_errno: i32,
    pub workspace_write_passed: bool,
    pub path: String,
    pub python_lookup_count: u64,
    pub node_lookup_count: u64,
    pub workbench_version: String,
    pub workbench_stage: String,
    pub workbench_terminal_status: String,
    pub workbench_comparison_passed: bool,
    pub result_ir_sha256: String,
    pub report_pdf_sha256: String,
    pub workbench_operator_surface_passed: bool,
    pub workbench_review_decision: String,
    pub workbench_inspect_before_review_sha256: String,
    pub workbench_review_sha256: String,
    pub workbench_inspect_after_review_sha256: String,
    pub workbench_export_sha256: String,
    pub mgt_workbench_stage: String,
    pub mgt_workbench_terminal_status: String,
    pub mgt_workbench_comparison_passed: bool,
    pub mgt_source_sha256: String,
    pub mgt_import_health_sha256: String,
    pub mgt_result_ir_sha256: String,
    pub mgt_report_pdf_sha256: String,
    pub mgt_workbench_operator_surface_passed: bool,
    pub mgt_workbench_review_decision: String,
    pub mgt_workbench_inspect_before_review_sha256: String,
    pub mgt_workbench_review_sha256: String,
    pub mgt_workbench_inspect_after_review_sha256: String,
    pub mgt_workbench_export_sha256: String,
    pub workbench_catalog_surface_passed: bool,
    pub workbench_catalog_sha256: String,
    pub workbench_evidence_surface_passed: bool,
    pub workbench_evidence_sha256: String,
    pub model_ir_linear_workbench_stage: String,
    pub model_ir_linear_workbench_terminal_status: String,
    pub model_ir_linear_workbench_comparison_passed: bool,
    pub model_ir_linear_workbench_operator_surface_passed: bool,
    pub model_ir_linear_workbench_review_decision: String,
    pub model_ir_linear_result_ir_sha256: String,
    pub model_ir_linear_result_recovery_ir_sha256: String,
    pub model_ir_linear_comparison_ir_sha256: String,
    pub model_ir_linear_report_pdf_sha256: String,
    pub model_ir_linear_report_document_sha256: String,
    pub model_ir_linear_pdf_receipt_sha256: String,
    pub model_ir_linear_report_receipt_sha256: String,
    pub model_ir_linear_workbench_inspect_before_review_sha256: String,
    pub model_ir_linear_workbench_review_sha256: String,
    pub model_ir_linear_workbench_inspect_after_review_sha256: String,
    pub model_ir_linear_workbench_export_sha256: String,
    pub container_image_built: bool,
    pub customer_image_receipt: bool,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RootfsIsolationReceiptV4 {
    pub schema_version: String,
    pub evidence: RootfsIsolationEvidenceV4,
    pub receipt_hash: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[allow(clippy::struct_excessive_bools)]
pub struct RootfsIsolationEvidenceV5 {
    #[serde(flatten)]
    pub prior: RootfsIsolationEvidenceV4,
    pub model_ir_linear_localized_pdf_surface_passed: bool,
    pub model_ir_linear_localized_pdf_en_us_sha256: String,
    pub model_ir_linear_localized_pdf_ko_kr_sha256: String,
    pub model_ir_linear_localized_pdf_en_us_receipt_sha256: String,
    pub model_ir_linear_localized_pdf_ko_kr_receipt_sha256: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RootfsIsolationReceiptV5 {
    pub schema_version: String,
    pub evidence: RootfsIsolationEvidenceV5,
    pub receipt_hash: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[allow(clippy::struct_excessive_bools)]
pub struct RootfsIsolationEvidenceV6 {
    #[serde(flatten)]
    pub prior: RootfsIsolationEvidenceV5,
    pub mgt_model_ir_linear_workbench_stage: String,
    pub mgt_model_ir_linear_workbench_terminal_status: String,
    pub mgt_model_ir_linear_workbench_comparison_passed: bool,
    pub mgt_model_ir_linear_workbench_operator_surface_passed: bool,
    pub mgt_model_ir_linear_workbench_review_decision: String,
    pub mgt_model_ir_linear_source_sha256: String,
    pub mgt_model_ir_linear_import_health_sha256: String,
    pub mgt_model_ir_linear_result_ir_sha256: String,
    pub mgt_model_ir_linear_result_recovery_ir_sha256: String,
    pub mgt_model_ir_linear_comparison_ir_sha256: String,
    pub mgt_model_ir_linear_report_pdf_sha256: String,
    pub mgt_model_ir_linear_report_document_sha256: String,
    pub mgt_model_ir_linear_pdf_receipt_sha256: String,
    pub mgt_model_ir_linear_report_receipt_sha256: String,
    pub mgt_model_ir_linear_workbench_inspect_before_review_sha256: String,
    pub mgt_model_ir_linear_workbench_review_sha256: String,
    pub mgt_model_ir_linear_workbench_inspect_after_review_sha256: String,
    pub mgt_model_ir_linear_workbench_export_sha256: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RootfsIsolationReceiptV6 {
    pub schema_version: String,
    pub evidence: RootfsIsolationEvidenceV6,
    pub receipt_hash: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[allow(clippy::struct_excessive_bools)]
pub struct RootfsIsolationEvidenceV7 {
    #[serde(flatten)]
    pub prior: RootfsIsolationEvidenceV6,
    pub model_ir_linear_reaction_result_ir_sha256: String,
    pub mgt_model_ir_linear_reaction_result_ir_sha256: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RootfsIsolationReceiptV7 {
    pub schema_version: String,
    pub evidence: RootfsIsolationEvidenceV7,
    pub receipt_hash: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[allow(clippy::struct_excessive_bools)]
pub struct RootfsIsolationEvidenceV8 {
    #[serde(flatten)]
    pub prior: RootfsIsolationEvidenceV7,
    pub model_ir_linear_reaction_view_surface_passed: bool,
    pub model_ir_linear_reaction_view_en_us_sha256: String,
    pub model_ir_linear_reaction_view_ko_kr_sha256: String,
    pub model_ir_linear_reaction_view_window_sha256: String,
    pub mgt_model_ir_linear_reaction_view_surface_passed: bool,
    pub mgt_model_ir_linear_reaction_view_en_us_sha256: String,
    pub mgt_model_ir_linear_reaction_view_ko_kr_sha256: String,
    pub workbench_reaction_view_wrong_profile_rejected: bool,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RootfsIsolationReceiptV8 {
    pub schema_version: String,
    pub evidence: RootfsIsolationEvidenceV8,
    pub receipt_hash: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[allow(clippy::struct_excessive_bools)]
pub struct RootfsIsolationEvidenceV9 {
    #[serde(flatten)]
    pub prior: RootfsIsolationEvidenceV8,
    pub model_ir_linear_reaction_audit_surface_passed: bool,
    pub model_ir_linear_reaction_audit_en_us_sha256: String,
    pub model_ir_linear_reaction_audit_ko_kr_sha256: String,
    pub mgt_model_ir_linear_reaction_audit_surface_passed: bool,
    pub mgt_model_ir_linear_reaction_audit_en_us_sha256: String,
    pub mgt_model_ir_linear_reaction_audit_ko_kr_sha256: String,
    pub workbench_reaction_audit_wrong_profile_rejected: bool,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RootfsIsolationReceiptV9 {
    pub schema_version: String,
    pub evidence: RootfsIsolationEvidenceV9,
    pub receipt_hash: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[allow(clippy::struct_excessive_bools)]
pub struct RootfsIsolationEvidenceV10 {
    #[serde(flatten)]
    pub prior: RootfsIsolationEvidenceV9,
    pub model_ir_linear_nodal_displacement_view_surface_passed: bool,
    pub model_ir_linear_nodal_displacement_view_en_us_sha256: String,
    pub model_ir_linear_nodal_displacement_view_ko_kr_sha256: String,
    pub model_ir_linear_nodal_displacement_view_window_sha256: String,
    pub mgt_model_ir_linear_nodal_displacement_view_surface_passed: bool,
    pub mgt_model_ir_linear_nodal_displacement_view_en_us_sha256: String,
    pub mgt_model_ir_linear_nodal_displacement_view_ko_kr_sha256: String,
    pub workbench_nodal_displacement_view_wrong_profile_rejected: bool,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RootfsIsolationReceiptV10 {
    pub schema_version: String,
    pub evidence: RootfsIsolationEvidenceV10,
    pub receipt_hash: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[allow(clippy::struct_excessive_bools)]
pub struct RootfsIsolationEvidenceV11 {
    #[serde(flatten)]
    pub prior: RootfsIsolationEvidenceV10,
    pub model_ir_linear_deformed_view_surface_passed: bool,
    pub model_ir_linear_deformed_view_en_us_sha256: String,
    pub model_ir_linear_deformed_view_ko_kr_sha256: String,
    pub model_ir_linear_deformed_view_projection_sha256: String,
    pub mgt_model_ir_linear_deformed_view_surface_passed: bool,
    pub mgt_model_ir_linear_deformed_view_en_us_sha256: String,
    pub mgt_model_ir_linear_deformed_view_ko_kr_sha256: String,
    pub workbench_linear_deformed_view_invalid_step_rejected: bool,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RootfsIsolationReceiptV11 {
    pub schema_version: String,
    pub evidence: RootfsIsolationEvidenceV11,
    pub receipt_hash: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[allow(clippy::struct_excessive_bools)]
pub struct RootfsIsolationEvidenceV12 {
    #[serde(flatten)]
    pub prior: RootfsIsolationEvidenceV11,
    pub model_ir_linear_element_recovery_view_surface_passed: bool,
    pub model_ir_linear_element_recovery_view_en_us_sha256: String,
    pub model_ir_linear_element_recovery_view_ko_kr_sha256: String,
    pub mgt_model_ir_linear_element_recovery_view_surface_passed: bool,
    pub mgt_model_ir_linear_element_recovery_view_en_us_sha256: String,
    pub mgt_model_ir_linear_element_recovery_view_ko_kr_sha256: String,
    pub workbench_linear_element_recovery_view_invalid_window_rejected: bool,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RootfsIsolationReceiptV12 {
    pub schema_version: String,
    pub evidence: RootfsIsolationEvidenceV12,
    pub receipt_hash: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[allow(clippy::struct_excessive_bools)]
pub struct RootfsIsolationEvidenceV13 {
    #[serde(flatten)]
    pub prior: RootfsIsolationEvidenceV12,
    pub structural_cli_sha256: String,
    pub model_ir_modal_request_sha256: String,
    pub workbench_model_modal_request_receipt_sha256: String,
    pub model_ir_modal_checkpoint_sha256: String,
    pub model_ir_modal_result_ir_sha256: String,
    pub model_ir_modal_run_receipt_sha256: String,
    pub model_ir_modal_restart_surface_passed: bool,
    pub model_ir_modal_restart_bitwise_passed: bool,
    pub workbench_model_modal_result_view_surface_passed: bool,
    pub workbench_model_modal_result_view_en_us_sha256: String,
    pub workbench_model_modal_result_view_ko_kr_sha256: String,
    pub workbench_model_modal_result_view_read_only_passed: bool,
    pub workbench_model_modal_result_view_invalid_window_rejected: bool,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RootfsIsolationReceiptV13 {
    pub schema_version: String,
    pub evidence: RootfsIsolationEvidenceV13,
    pub receipt_hash: String,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(untagged)]
pub enum VerifiedRootfsIsolationReceipt {
    V1(Box<RootfsIsolationReceiptV1>),
    V2(Box<RootfsIsolationReceiptV2>),
    V3(Box<RootfsIsolationReceiptV3>),
    V4(Box<RootfsIsolationReceiptV4>),
    V5(Box<RootfsIsolationReceiptV5>),
    V6(Box<RootfsIsolationReceiptV6>),
    V7(Box<RootfsIsolationReceiptV7>),
    V8(Box<RootfsIsolationReceiptV8>),
    V9(Box<RootfsIsolationReceiptV9>),
    V10(Box<RootfsIsolationReceiptV10>),
    V11(Box<RootfsIsolationReceiptV11>),
    V12(Box<RootfsIsolationReceiptV12>),
    V13(Box<RootfsIsolationReceiptV13>),
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct DistributionError {
    pub code: &'static str,
    pub detail: String,
}

impl DistributionError {
    fn new(code: &'static str, detail: impl Into<String>) -> Self {
        Self {
            code,
            detail: detail.into(),
        }
    }
}

impl fmt::Display for DistributionError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{}: {}", self.code, self.detail)
    }
}

impl std::error::Error for DistributionError {}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct NativeBuildManifestV1 {
    schema_version: String,
    package_version: String,
    abi_version: String,
    c_compiler: CompilerIdentityV1,
    cxx_compiler: CompilerIdentityV1,
    build_type: String,
    hip_enabled: bool,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct CompilerIdentityV1 {
    id: String,
    version: String,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
enum TransactionOperationV1 {
    Install,
    Rollback,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
enum TransactionPhaseV1 {
    Prepared,
    Materialized,
    Activated,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
struct InstallTransactionV1 {
    schema_version: String,
    operation: TransactionOperationV1,
    phase: TransactionPhaseV1,
    release_id: String,
    manifest_hash: String,
    staging_name: Option<String>,
    desired_activation: ActivationStateV1,
}

struct InstallLock {
    file: File,
}

impl Drop for InstallLock {
    fn drop(&mut self) {
        let _ = FileExt::unlock(&self.file);
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum InstallInterruption {
    None,
    AfterPrepared,
    AfterMaterialized,
    AfterActivated,
}

/// Creates an immutable, deterministic directory bundle from a staged native payload.
///
/// # Errors
///
/// Returns an error when identities are invalid, the payload violates the product contract,
/// an unsafe filesystem entry is encountered, or durable publication fails.
pub fn create_bundle(
    request: &BundleCreateRequest<'_>,
) -> Result<DistributionManifestV1, DistributionError> {
    validate_release_id(request.release_id)?;
    validate_package_version(request.package_version)?;
    validate_sha256_identity(request.source_sha256, "source SHA-256")?;
    ensure_directory(request.payload_root, "payload root")?;
    if fs::symlink_metadata(request.output).is_ok() {
        return Err(DistributionError::new(
            "bundle_output_exists",
            "bundle output must not already exist",
        ));
    }
    let output_parent = request.output.parent().ok_or_else(|| {
        DistributionError::new(
            "bundle_output_invalid",
            "bundle output has no parent directory",
        )
    })?;
    ensure_directory(output_parent, "bundle output parent")?;
    let staging = unique_path(output_parent, ".structural-bundle-stage");
    fs::create_dir(&staging).map_err(|error| io_error("bundle_stage_create_failed", error))?;
    let outcome = create_bundle_in_staging(request, &staging);
    match outcome {
        Ok(manifest) => {
            sync_directory_tree(&staging)?;
            fs::rename(&staging, request.output)
                .map_err(|error| io_error("bundle_publish_failed", error))?;
            sync_directory(output_parent)?;
            Ok(manifest)
        }
        Err(error) => {
            let _ = fs::remove_dir_all(&staging);
            Err(error)
        }
    }
}

fn create_bundle_in_staging(
    request: &BundleCreateRequest<'_>,
    staging: &Path,
) -> Result<DistributionManifestV1, DistributionError> {
    let payload_destination = staging.join(PAYLOAD_DIRECTORY);
    fs::create_dir(&payload_destination)
        .map_err(|error| io_error("bundle_payload_create_failed", error))?;
    let source_root = request
        .payload_root
        .canonicalize()
        .map_err(|error| io_error("payload_root_resolve_failed", error))?;
    let mut sources = Vec::new();
    collect_payload_sources(&source_root, &source_root, &mut sources)?;
    if sources.is_empty() {
        return Err(DistributionError::new(
            "bundle_payload_empty",
            "payload root contains no files",
        ));
    }
    if sources.len() > MAX_FILE_COUNT {
        return Err(DistributionError::new(
            "bundle_file_count_exceeded",
            "payload file count exceeds the distribution limit",
        ));
    }
    let mut entries = Vec::with_capacity(sources.len());
    let mut total_size = 0_u64;
    for (relative, source) in sources {
        let relative_text = portable_relative_path(&relative)?;
        let destination = payload_destination.join(&relative);
        if let Some(parent) = destination.parent() {
            fs::create_dir_all(parent)
                .map_err(|error| io_error("bundle_directory_create_failed", error))?;
        }
        let (size, mode, sha256) = copy_regular_file(&source, &destination)?;
        total_size = total_size.checked_add(size).ok_or_else(|| {
            DistributionError::new("bundle_size_overflow", "payload byte count overflowed")
        })?;
        if total_size > MAX_TOTAL_BYTES {
            return Err(DistributionError::new(
                "bundle_total_size_exceeded",
                "payload bytes exceed the distribution limit",
            ));
        }
        entries.push(DistributionFileV1 {
            path: relative_text,
            size,
            mode,
            sha256,
        });
    }
    entries.sort_by(|left, right| left.path.cmp(&right.path));
    validate_payload_contract(
        &payload_destination,
        request.package_version,
        request.backend_profile,
        request.linkage,
        &entries,
    )?;
    let unsigned = UnsignedDistributionManifestV1 {
        schema_version: SCHEMA_VERSION.to_owned(),
        release_id: request.release_id.to_owned(),
        package_version: request.package_version.to_owned(),
        backend_profile: request.backend_profile,
        linkage: request.linkage,
        abi_version: ABI_VERSION.to_owned(),
        source_sha256: request.source_sha256.to_owned(),
        execution_authority: match request.backend_profile {
            BackendProfileV1::CpuOnly => "cpu_build_candidate".to_owned(),
            BackendProfileV1::Rocm => "rocm_build_candidate".to_owned(),
        },
        files: entries,
    };
    let unsigned_bytes = canonical_json(&unsigned)?;
    let manifest = DistributionManifestV1 {
        schema_version: unsigned.schema_version,
        release_id: unsigned.release_id,
        package_version: unsigned.package_version,
        backend_profile: unsigned.backend_profile,
        linkage: unsigned.linkage,
        abi_version: unsigned.abi_version,
        source_sha256: unsigned.source_sha256,
        execution_authority: unsigned.execution_authority,
        files: unsigned.files,
        manifest_hash: sha256_identity(&unsigned_bytes),
    };
    let bytes = canonical_json(&manifest)?;
    write_new_file(&staging.join(MANIFEST_NAME), &bytes, 0o444)?;
    Ok(manifest)
}

/// Verifies the canonical manifest, complete file inventory, metadata, and payload hashes.
///
/// # Errors
///
/// Returns an error for any malformed, unsupported, missing, extra, unsafe, or modified entry.
pub fn verify_bundle(bundle: &Path) -> Result<DistributionManifestV1, DistributionError> {
    ensure_directory(bundle, "bundle")?;
    let manifest_path = bundle.join(MANIFEST_NAME);
    let bytes = read_bounded_regular_file(&manifest_path, MAX_MANIFEST_BYTES)?;
    let manifest: DistributionManifestV1 = serde_json::from_slice(&bytes).map_err(|error| {
        DistributionError::new(
            "bundle_manifest_invalid",
            format!("distribution manifest is invalid JSON: {error}"),
        )
    })?;
    if canonical_json(&manifest)? != bytes {
        return Err(DistributionError::new(
            "bundle_manifest_noncanonical",
            "distribution manifest must use exact canonical JSON bytes",
        ));
    }
    validate_manifest_fields(&manifest)?;
    let unsigned = UnsignedDistributionManifestV1 {
        schema_version: manifest.schema_version.clone(),
        release_id: manifest.release_id.clone(),
        package_version: manifest.package_version.clone(),
        backend_profile: manifest.backend_profile,
        linkage: manifest.linkage,
        abi_version: manifest.abi_version.clone(),
        source_sha256: manifest.source_sha256.clone(),
        execution_authority: manifest.execution_authority.clone(),
        files: manifest.files.clone(),
    };
    let expected_hash = sha256_identity(&canonical_json(&unsigned)?);
    if manifest.manifest_hash != expected_hash {
        return Err(DistributionError::new(
            "bundle_manifest_hash_mismatch",
            "distribution manifest self-hash does not match",
        ));
    }
    verify_payload_files(bundle, &manifest)?;
    validate_payload_contract(
        &bundle.join(PAYLOAD_DIRECTORY),
        &manifest.package_version,
        manifest.backend_profile,
        manifest.linkage,
        &manifest.files,
    )?;
    Ok(manifest)
}

/// Emits a hash-bound diagnostic receipt from inside the isolated Linux root filesystem.
///
/// # Errors
///
/// Returns an error unless the process is the fixed non-root runtime identity, the verified
/// bundle and executing payload are identical, the root and payload reject writes with `EROFS`,
/// the operator workspace accepts writes, only loopback networking is visible, and all four
/// native Workbench sessions reached their reported terminal state, including the typed
/// ModelIR-linear and normalized-MGT-to-ModelIR-linear report, algebraic reaction-audit, and
/// bounded nodal-displacement, deformed, element-recovery, and modal restart/view surfaces.
#[allow(clippy::too_many_lines)]
pub fn create_rootfs_isolation_receipt(
    request: &RootfsIsolationProbeRequest<'_>,
) -> Result<RootfsIsolationReceiptV13, DistributionError> {
    #[cfg(not(target_os = "linux"))]
    return Err(DistributionError::new(
        "rootfs_platform_unsupported",
        "rootfs isolation receipts require Linux",
    ));

    let process_identity = linux_effective_ids();
    if process_identity.user_id != ROOTFS_RUNTIME_UID
        || process_identity.group_id != ROOTFS_RUNTIME_GID
    {
        return Err(DistributionError::new(
            "rootfs_runtime_identity_invalid",
            "rootfs diagnostic must execute as UID/GID 65532",
        ));
    }
    if std::env::var_os("PATH").as_deref() != Some(std::ffi::OsStr::new(ROOTFS_EMPTY_PATH)) {
        return Err(DistributionError::new(
            "rootfs_runtime_path_invalid",
            "rootfs diagnostic requires the exact empty lookup PATH",
        ));
    }

    let workspace = resolve_real_directory(request.workspace, "rootfs workspace")?;
    let receipt_parent = request.receipt.parent().ok_or_else(|| {
        DistributionError::new(
            "rootfs_receipt_path_invalid",
            "rootfs receipt must have a parent directory",
        )
    })?;
    if resolve_real_directory(receipt_parent, "rootfs receipt parent")? != workspace {
        return Err(DistributionError::new(
            "rootfs_receipt_path_invalid",
            "rootfs receipt must be created directly in the operator workspace",
        ));
    }
    if path_entry_exists(request.receipt)? {
        return Err(DistributionError::new(
            "rootfs_receipt_exists",
            "rootfs receipt output must not already exist",
        ));
    }

    let bundle_root = resolve_real_directory(request.bundle, "rootfs bundle")?;
    let payload_root = resolve_real_directory(request.payload_root, "rootfs payload")?;
    let expected_payload = resolve_real_directory(
        &bundle_root.join(PAYLOAD_DIRECTORY),
        "verified rootfs bundle payload",
    )?;
    if payload_root != expected_payload {
        return Err(DistributionError::new(
            "rootfs_payload_bundle_mismatch",
            "executing payload must be the supplied verified bundle payload",
        ));
    }
    let manifest = verify_bundle(&bundle_root)?;
    if manifest.backend_profile != BackendProfileV1::CpuOnly {
        return Err(DistributionError::new(
            "rootfs_backend_invalid",
            "local rootfs diagnostic accepts only the CPU-only bundle",
        ));
    }

    let installer = payload_root.join("bin/structural-installer");
    let structural_cli = payload_root.join("bin/structural-cli");
    let workbench = payload_root.join("bin/structural-workbench");
    let current_executable = std::env::current_exe()
        .and_then(|path| path.canonicalize())
        .map_err(|error| io_error("rootfs_current_executable_failed", error))?;
    let expected_installer = installer
        .canonicalize()
        .map_err(|error| io_error("rootfs_installer_resolve_failed", error))?;
    if current_executable != expected_installer {
        return Err(DistributionError::new(
            "rootfs_installer_identity_mismatch",
            "runtime probe must execute from the verified bundle payload",
        ));
    }
    let installer_sha256 = sha256_file(&installer)?;
    let structural_cli_sha256 = sha256_file(&structural_cli)?;
    let workbench_sha256 = sha256_file(&workbench)?;
    require_manifest_entry_hash(&manifest, "bin/structural-installer", &installer_sha256)?;
    require_manifest_entry_hash(&manifest, "bin/structural-cli", &structural_cli_sha256)?;
    require_manifest_entry_hash(&manifest, "bin/structural-workbench", &workbench_sha256)?;

    let rootfs_write_errno = require_read_only_mount(Path::new("/etc"), "root filesystem")?;
    let payload_write_errno = require_read_only_mount(&payload_root, "payload filesystem")?;
    verify_workspace_write(&workspace)?;
    let network_interfaces = linux_network_interfaces()?;
    let ipv4_route_count = linux_ipv4_route_count()?;
    if network_interfaces.len() != 1 || network_interfaces[0] != "lo" || ipv4_route_count != 0 {
        return Err(DistributionError::new(
            "rootfs_network_isolation_failed",
            "isolated runtime must expose only loopback and no IPv4 routes",
        ));
    }

    let version_output = Command::new(&workbench)
        .arg("--version")
        .env_clear()
        .env("PATH", ROOTFS_EMPTY_PATH)
        .output()
        .map_err(|error| io_error("rootfs_workbench_version_failed", error))?;
    if !version_output.status.success() || !version_output.stderr.is_empty() {
        return Err(DistributionError::new(
            "rootfs_workbench_version_failed",
            "native Workbench version command failed in the isolated runtime",
        ));
    }
    let workbench_version = String::from_utf8(version_output.stdout)
        .map_err(|_| {
            DistributionError::new(
                "rootfs_workbench_version_invalid",
                "native Workbench version output must be UTF-8",
            )
        })?
        .trim()
        .to_owned();
    if workbench_version != format!("structural-workbench {}", manifest.package_version) {
        return Err(DistributionError::new(
            "rootfs_workbench_version_invalid",
            "native Workbench version does not match the verified bundle",
        ));
    }

    let workbench_summary = inspect_reported_workbench(&workspace, request.workbench_root, None)?;
    let mgt_summary = inspect_reported_workbench(&workspace, request.mgt_workbench_root, None)?;
    let model_ir_linear_summary = inspect_reported_workbench(
        &workspace,
        request.model_ir_linear_workbench_root,
        Some("model_ir_linear_cpu_v1"),
    )?;
    let mgt_model_ir_linear_summary = inspect_reported_workbench(
        &workspace,
        request.mgt_model_ir_linear_workbench_root,
        Some("model_ir_linear_cpu_v1"),
    )?;
    let (mgt_model_ir_linear_source_sha256, mgt_model_ir_linear_import_health_sha256) =
        inspect_normalized_mgt_import_surface(
            &workspace,
            request.mgt_model_ir_linear_workbench_root,
            &mgt_model_ir_linear_summary,
        )?;
    let workbench_operator = inspect_workbench_operator_surface(
        &workspace,
        request.workbench_root,
        &workbench_summary,
        &OperatorSurfaceProbe {
            import_kind: "model_ir",
            analysis_profile: None,
            expected_export_artifact_count: 6,
            inspect_before_review: request.workbench_inspect_before_review,
            review_show: request.workbench_review_show,
            inspect_after_review: request.workbench_inspect_after_review,
            export: request.workbench_export,
        },
    )?;
    let mgt_workbench_operator = inspect_workbench_operator_surface(
        &workspace,
        request.mgt_workbench_root,
        &mgt_summary,
        &OperatorSurfaceProbe {
            import_kind: "mgt",
            analysis_profile: None,
            expected_export_artifact_count: 6,
            inspect_before_review: request.mgt_workbench_inspect_before_review,
            review_show: request.mgt_workbench_review_show,
            inspect_after_review: request.mgt_workbench_inspect_after_review,
            export: request.mgt_workbench_export,
        },
    )?;
    let model_ir_linear_workbench_operator = inspect_workbench_operator_surface(
        &workspace,
        request.model_ir_linear_workbench_root,
        &model_ir_linear_summary,
        &OperatorSurfaceProbe {
            import_kind: "model_ir",
            analysis_profile: Some("model_ir_linear_cpu_v1"),
            expected_export_artifact_count: 9,
            inspect_before_review: request.model_ir_linear_workbench_inspect_before_review,
            review_show: request.model_ir_linear_workbench_review_show,
            inspect_after_review: request.model_ir_linear_workbench_inspect_after_review,
            export: request.model_ir_linear_workbench_export,
        },
    )?;
    let mgt_model_ir_linear_workbench_operator = inspect_workbench_operator_surface(
        &workspace,
        request.mgt_model_ir_linear_workbench_root,
        &mgt_model_ir_linear_summary,
        &OperatorSurfaceProbe {
            import_kind: "mgt",
            analysis_profile: Some("model_ir_linear_cpu_v1"),
            expected_export_artifact_count: 9,
            inspect_before_review: request.mgt_model_ir_linear_workbench_inspect_before_review,
            review_show: request.mgt_model_ir_linear_workbench_review_show,
            inspect_after_review: request.mgt_model_ir_linear_workbench_inspect_after_review,
            export: request.mgt_model_ir_linear_workbench_export,
        },
    )?;
    let read_only_surfaces = inspect_workbench_read_only_surfaces(
        &workspace,
        request.workbench_catalog,
        request.workbench_evidence,
    )?;
    let localized_pdf_surface = inspect_model_ir_linear_localized_pdf_surface(
        &workspace,
        &payload_root,
        request.model_ir_linear_workbench_root,
        request.model_ir_linear_workbench_session_before_localized_pdf,
        request.model_ir_linear_localized_pdf_en_us_first_root,
        request.model_ir_linear_localized_pdf_en_us_second_root,
        request.model_ir_linear_localized_pdf_ko_kr_first_root,
        request.model_ir_linear_localized_pdf_ko_kr_second_root,
    )?;
    let mgt_root =
        resolve_workspace_child(&workspace, request.mgt_workbench_root, "MGT Workbench")?;
    let model_ir_linear_root = resolve_workspace_child(
        &workspace,
        request.model_ir_linear_workbench_root,
        "ModelIR linear Workbench",
    )?;
    let mgt_model_ir_linear_root = resolve_workspace_child(
        &workspace,
        request.mgt_model_ir_linear_workbench_root,
        "normalized MGT ModelIR linear Workbench",
    )?;
    let reaction_view_surface = inspect_rootfs_reaction_view_surface(
        &workspace,
        &model_ir_linear_root,
        &mgt_model_ir_linear_root,
        request,
    )?;
    let reaction_audit_surface = inspect_rootfs_reaction_audit_surface(
        &workspace,
        &model_ir_linear_root,
        &mgt_model_ir_linear_root,
        request,
    )?;
    let nodal_displacement_view_surface = inspect_rootfs_nodal_displacement_view_surface(
        &workspace,
        &model_ir_linear_root,
        &mgt_model_ir_linear_root,
        request,
    )?;
    let linear_deformed_view_surface = inspect_rootfs_linear_deformed_view_surface(
        &workspace,
        &model_ir_linear_root,
        &mgt_model_ir_linear_root,
        request,
    )?;
    let linear_element_recovery_view_surface = inspect_rootfs_linear_element_recovery_view_surface(
        &workspace,
        &model_ir_linear_root,
        &mgt_model_ir_linear_root,
        request,
    )?;
    let model_modal_surface = inspect_rootfs_model_modal_surface(&workspace, request)?;
    let prior = RootfsIsolationEvidenceV4 {
        authority: ROOTFS_RECEIPT_AUTHORITY.to_owned(),
        claim_boundary: ROOTFS_RECEIPT_CLAIM_BOUNDARY_V6.to_owned(),
        isolation_technology: ROOTFS_ISOLATION_TECHNOLOGY.to_owned(),
        release_id: manifest.release_id.clone(),
        source_sha256: manifest.source_sha256.clone(),
        bundle_manifest_hash: manifest.manifest_hash.clone(),
        bundle_manifest_file_sha256: sha256_file(&bundle_root.join(MANIFEST_NAME))?,
        installer_sha256,
        workbench_sha256,
        runtime_uid: process_identity.user_id,
        runtime_gid: process_identity.group_id,
        network_interfaces,
        ipv4_route_count,
        rootfs_write_errno,
        payload_write_errno,
        workspace_write_passed: true,
        path: ROOTFS_EMPTY_PATH.to_owned(),
        python_lookup_count: 0,
        node_lookup_count: 0,
        workbench_version,
        workbench_stage: workbench_summary.stage,
        workbench_terminal_status: workbench_summary.terminal_status,
        workbench_comparison_passed: workbench_summary.comparison_passed,
        result_ir_sha256: workbench_summary.result_ir_sha256,
        report_pdf_sha256: workbench_summary.report_pdf_sha256,
        workbench_operator_surface_passed: true,
        workbench_review_decision: workbench_operator.decision,
        workbench_inspect_before_review_sha256: workbench_operator.inspect_before_review_sha256,
        workbench_review_sha256: workbench_operator.review_sha256,
        workbench_inspect_after_review_sha256: workbench_operator.inspect_after_review_sha256,
        workbench_export_sha256: workbench_operator.export_sha256,
        mgt_workbench_stage: mgt_summary.stage,
        mgt_workbench_terminal_status: mgt_summary.terminal_status,
        mgt_workbench_comparison_passed: mgt_summary.comparison_passed,
        mgt_source_sha256: sha256_file(&mgt_root.join("01-import/source.mgt"))?,
        mgt_import_health_sha256: sha256_file(&mgt_root.join("01-import/import-health.json"))?,
        mgt_result_ir_sha256: mgt_summary.result_ir_sha256,
        mgt_report_pdf_sha256: mgt_summary.report_pdf_sha256,
        mgt_workbench_operator_surface_passed: true,
        mgt_workbench_review_decision: mgt_workbench_operator.decision,
        mgt_workbench_inspect_before_review_sha256: mgt_workbench_operator
            .inspect_before_review_sha256,
        mgt_workbench_review_sha256: mgt_workbench_operator.review_sha256,
        mgt_workbench_inspect_after_review_sha256: mgt_workbench_operator
            .inspect_after_review_sha256,
        mgt_workbench_export_sha256: mgt_workbench_operator.export_sha256,
        workbench_catalog_surface_passed: true,
        workbench_catalog_sha256: read_only_surfaces.catalog_sha256,
        workbench_evidence_surface_passed: true,
        workbench_evidence_sha256: read_only_surfaces.evidence_sha256,
        model_ir_linear_workbench_stage: model_ir_linear_summary.stage,
        model_ir_linear_workbench_terminal_status: model_ir_linear_summary.terminal_status,
        model_ir_linear_workbench_comparison_passed: model_ir_linear_summary.comparison_passed,
        model_ir_linear_workbench_operator_surface_passed: true,
        model_ir_linear_workbench_review_decision: model_ir_linear_workbench_operator.decision,
        model_ir_linear_result_ir_sha256: model_ir_linear_summary.result_ir_sha256,
        model_ir_linear_result_recovery_ir_sha256: model_ir_linear_summary
            .result_recovery_ir_sha256
            .ok_or_else(|| {
                DistributionError::new(
                    "rootfs_workbench_incomplete",
                    "ModelIR linear Workbench has no typed recovery artifact",
                )
            })?,
        model_ir_linear_comparison_ir_sha256: model_ir_linear_summary.comparison_ir_sha256,
        model_ir_linear_report_pdf_sha256: model_ir_linear_summary.report_pdf_sha256,
        model_ir_linear_report_document_sha256: model_ir_linear_summary
            .report_document_sha256
            .ok_or_else(|| {
                DistributionError::new(
                    "rootfs_workbench_incomplete",
                    "ModelIR linear Workbench has no report document",
                )
            })?,
        model_ir_linear_pdf_receipt_sha256: sha256_file(
            &model_ir_linear_root.join("06-report/pdf-receipt.json"),
        )?,
        model_ir_linear_report_receipt_sha256: sha256_file(
            &model_ir_linear_root.join("06-report/report-receipt.json"),
        )?,
        model_ir_linear_workbench_inspect_before_review_sha256: model_ir_linear_workbench_operator
            .inspect_before_review_sha256,
        model_ir_linear_workbench_review_sha256: model_ir_linear_workbench_operator.review_sha256,
        model_ir_linear_workbench_inspect_after_review_sha256: model_ir_linear_workbench_operator
            .inspect_after_review_sha256,
        model_ir_linear_workbench_export_sha256: model_ir_linear_workbench_operator.export_sha256,
        container_image_built: false,
        customer_image_receipt: false,
    };
    let prior = RootfsIsolationEvidenceV5 {
        prior,
        model_ir_linear_localized_pdf_surface_passed: true,
        model_ir_linear_localized_pdf_en_us_sha256: localized_pdf_surface.en_us_pdf,
        model_ir_linear_localized_pdf_ko_kr_sha256: localized_pdf_surface.ko_kr_pdf,
        model_ir_linear_localized_pdf_en_us_receipt_sha256: localized_pdf_surface.en_us_receipt,
        model_ir_linear_localized_pdf_ko_kr_receipt_sha256: localized_pdf_surface.ko_kr_receipt,
    };
    let evidence_v6 = RootfsIsolationEvidenceV6 {
        prior,
        mgt_model_ir_linear_workbench_stage: mgt_model_ir_linear_summary.stage,
        mgt_model_ir_linear_workbench_terminal_status: mgt_model_ir_linear_summary.terminal_status,
        mgt_model_ir_linear_workbench_comparison_passed: mgt_model_ir_linear_summary
            .comparison_passed,
        mgt_model_ir_linear_workbench_operator_surface_passed: true,
        mgt_model_ir_linear_workbench_review_decision: mgt_model_ir_linear_workbench_operator
            .decision,
        mgt_model_ir_linear_source_sha256,
        mgt_model_ir_linear_import_health_sha256,
        mgt_model_ir_linear_result_ir_sha256: mgt_model_ir_linear_summary.result_ir_sha256,
        mgt_model_ir_linear_result_recovery_ir_sha256: mgt_model_ir_linear_summary
            .result_recovery_ir_sha256
            .ok_or_else(|| {
                DistributionError::new(
                    "rootfs_workbench_incomplete",
                    "normalized MGT ModelIR linear Workbench has no typed recovery artifact",
                )
            })?,
        mgt_model_ir_linear_comparison_ir_sha256: mgt_model_ir_linear_summary.comparison_ir_sha256,
        mgt_model_ir_linear_report_pdf_sha256: mgt_model_ir_linear_summary.report_pdf_sha256,
        mgt_model_ir_linear_report_document_sha256: mgt_model_ir_linear_summary
            .report_document_sha256
            .ok_or_else(|| {
                DistributionError::new(
                    "rootfs_workbench_incomplete",
                    "normalized MGT ModelIR linear Workbench has no report document",
                )
            })?,
        mgt_model_ir_linear_pdf_receipt_sha256: sha256_file(
            &mgt_model_ir_linear_root.join("06-report/pdf-receipt.json"),
        )?,
        mgt_model_ir_linear_report_receipt_sha256: sha256_file(
            &mgt_model_ir_linear_root.join("06-report/report-receipt.json"),
        )?,
        mgt_model_ir_linear_workbench_inspect_before_review_sha256:
            mgt_model_ir_linear_workbench_operator.inspect_before_review_sha256,
        mgt_model_ir_linear_workbench_review_sha256: mgt_model_ir_linear_workbench_operator
            .review_sha256,
        mgt_model_ir_linear_workbench_inspect_after_review_sha256:
            mgt_model_ir_linear_workbench_operator.inspect_after_review_sha256,
        mgt_model_ir_linear_workbench_export_sha256: mgt_model_ir_linear_workbench_operator
            .export_sha256,
    };
    validate_rootfs_isolation_evidence_v6(&evidence_v6)?;
    let mut prior = evidence_v6;
    ROOTFS_RECEIPT_CLAIM_BOUNDARY_V7.clone_into(&mut prior.prior.prior.claim_boundary);
    let mut evidence_v7 = RootfsIsolationEvidenceV7 {
        prior,
        model_ir_linear_reaction_result_ir_sha256: model_ir_linear_summary
            .reaction_result_ir_sha256
            .ok_or_else(|| {
                DistributionError::new(
                    "rootfs_workbench_incomplete",
                    "ModelIR linear Workbench has no constrained-reaction ResultIR artifact",
                )
            })?,
        mgt_model_ir_linear_reaction_result_ir_sha256: mgt_model_ir_linear_summary
            .reaction_result_ir_sha256
            .ok_or_else(|| {
                DistributionError::new(
                    "rootfs_workbench_incomplete",
                    "normalized MGT ModelIR linear Workbench has no constrained-reaction ResultIR artifact",
                )
            })?,
    };
    validate_rootfs_isolation_evidence_v7(&evidence_v7)?;
    ROOTFS_RECEIPT_CLAIM_BOUNDARY_V8.clone_into(&mut evidence_v7.prior.prior.prior.claim_boundary);
    let mut evidence_v8 = RootfsIsolationEvidenceV8 {
        prior: evidence_v7,
        model_ir_linear_reaction_view_surface_passed: true,
        model_ir_linear_reaction_view_en_us_sha256: reaction_view_surface.model_en_us,
        model_ir_linear_reaction_view_ko_kr_sha256: reaction_view_surface.model_ko_kr,
        model_ir_linear_reaction_view_window_sha256: reaction_view_surface.model_window,
        mgt_model_ir_linear_reaction_view_surface_passed: true,
        mgt_model_ir_linear_reaction_view_en_us_sha256: reaction_view_surface.mgt_en_us,
        mgt_model_ir_linear_reaction_view_ko_kr_sha256: reaction_view_surface.mgt_ko_kr,
        workbench_reaction_view_wrong_profile_rejected: true,
    };
    validate_rootfs_isolation_evidence_v8(&evidence_v8)?;
    ROOTFS_RECEIPT_CLAIM_BOUNDARY_V9
        .clone_into(&mut evidence_v8.prior.prior.prior.prior.claim_boundary);
    let mut evidence_v9 = RootfsIsolationEvidenceV9 {
        prior: evidence_v8,
        model_ir_linear_reaction_audit_surface_passed: true,
        model_ir_linear_reaction_audit_en_us_sha256: reaction_audit_surface.model_en_us,
        model_ir_linear_reaction_audit_ko_kr_sha256: reaction_audit_surface.model_ko_kr,
        mgt_model_ir_linear_reaction_audit_surface_passed: true,
        mgt_model_ir_linear_reaction_audit_en_us_sha256: reaction_audit_surface.mgt_en_us,
        mgt_model_ir_linear_reaction_audit_ko_kr_sha256: reaction_audit_surface.mgt_ko_kr,
        workbench_reaction_audit_wrong_profile_rejected: true,
    };
    validate_rootfs_isolation_evidence_v9(&evidence_v9)?;
    ROOTFS_RECEIPT_CLAIM_BOUNDARY_V10
        .clone_into(&mut evidence_v9.prior.prior.prior.prior.prior.claim_boundary);
    let mut evidence_v10 = RootfsIsolationEvidenceV10 {
        prior: evidence_v9,
        model_ir_linear_nodal_displacement_view_surface_passed: true,
        model_ir_linear_nodal_displacement_view_en_us_sha256: nodal_displacement_view_surface
            .model_en_us,
        model_ir_linear_nodal_displacement_view_ko_kr_sha256: nodal_displacement_view_surface
            .model_ko_kr,
        model_ir_linear_nodal_displacement_view_window_sha256: nodal_displacement_view_surface
            .model_window,
        mgt_model_ir_linear_nodal_displacement_view_surface_passed: true,
        mgt_model_ir_linear_nodal_displacement_view_en_us_sha256: nodal_displacement_view_surface
            .mgt_en_us,
        mgt_model_ir_linear_nodal_displacement_view_ko_kr_sha256: nodal_displacement_view_surface
            .mgt_ko_kr,
        workbench_nodal_displacement_view_wrong_profile_rejected: true,
    };
    validate_rootfs_isolation_evidence_v10(&evidence_v10)?;
    ROOTFS_RECEIPT_CLAIM_BOUNDARY_V11.clone_into(
        &mut evidence_v10
            .prior
            .prior
            .prior
            .prior
            .prior
            .prior
            .claim_boundary,
    );
    let mut evidence_v11 = RootfsIsolationEvidenceV11 {
        prior: evidence_v10,
        model_ir_linear_deformed_view_surface_passed: true,
        model_ir_linear_deformed_view_en_us_sha256: linear_deformed_view_surface.model_en_us,
        model_ir_linear_deformed_view_ko_kr_sha256: linear_deformed_view_surface.model_ko_kr,
        model_ir_linear_deformed_view_projection_sha256: linear_deformed_view_surface
            .model_projection,
        mgt_model_ir_linear_deformed_view_surface_passed: true,
        mgt_model_ir_linear_deformed_view_en_us_sha256: linear_deformed_view_surface.mgt_en_us,
        mgt_model_ir_linear_deformed_view_ko_kr_sha256: linear_deformed_view_surface.mgt_ko_kr,
        workbench_linear_deformed_view_invalid_step_rejected: true,
    };
    validate_rootfs_isolation_evidence_v11(&evidence_v11)?;
    ROOTFS_RECEIPT_CLAIM_BOUNDARY_V12.clone_into(
        &mut evidence_v11
            .prior
            .prior
            .prior
            .prior
            .prior
            .prior
            .prior
            .claim_boundary,
    );
    let mut evidence_v12 = RootfsIsolationEvidenceV12 {
        prior: evidence_v11,
        model_ir_linear_element_recovery_view_surface_passed: true,
        model_ir_linear_element_recovery_view_en_us_sha256: linear_element_recovery_view_surface
            .model_en_us,
        model_ir_linear_element_recovery_view_ko_kr_sha256: linear_element_recovery_view_surface
            .model_ko_kr,
        mgt_model_ir_linear_element_recovery_view_surface_passed: true,
        mgt_model_ir_linear_element_recovery_view_en_us_sha256:
            linear_element_recovery_view_surface.mgt_en_us,
        mgt_model_ir_linear_element_recovery_view_ko_kr_sha256:
            linear_element_recovery_view_surface.mgt_ko_kr,
        workbench_linear_element_recovery_view_invalid_window_rejected: true,
    };
    validate_rootfs_isolation_evidence_v12(&evidence_v12)?;
    ROOTFS_RECEIPT_CLAIM_BOUNDARY.clone_into(
        &mut evidence_v12
            .prior
            .prior
            .prior
            .prior
            .prior
            .prior
            .prior
            .prior
            .claim_boundary,
    );
    let evidence = RootfsIsolationEvidenceV13 {
        prior: evidence_v12,
        structural_cli_sha256,
        model_ir_modal_request_sha256: model_modal_surface.request_sha256,
        workbench_model_modal_request_receipt_sha256: model_modal_surface.request_receipt_sha256,
        model_ir_modal_checkpoint_sha256: model_modal_surface.checkpoint_sha256,
        model_ir_modal_result_ir_sha256: model_modal_surface.result_ir_sha256,
        model_ir_modal_run_receipt_sha256: model_modal_surface.run_receipt_sha256,
        model_ir_modal_restart_surface_passed: true,
        model_ir_modal_restart_bitwise_passed: true,
        workbench_model_modal_result_view_surface_passed: true,
        workbench_model_modal_result_view_en_us_sha256: model_modal_surface.view_en_us_sha256,
        workbench_model_modal_result_view_ko_kr_sha256: model_modal_surface.view_ko_kr_sha256,
        workbench_model_modal_result_view_read_only_passed: true,
        workbench_model_modal_result_view_invalid_window_rejected: true,
    };
    validate_rootfs_isolation_evidence_v13(&evidence)?;
    let receipt = seal_rootfs_isolation_evidence(evidence)?;
    write_new_file(request.receipt, &canonical_json(&receipt)?, 0o444)?;
    sync_directory(&workspace)?;
    Ok(receipt)
}

/// Validates an exact rootfs isolation receipt against its complete native bundle.
///
/// # Errors
///
/// Returns an error for noncanonical bytes, unknown or weakened evidence, hash drift, or a bundle
/// identity mismatch. This remains diagnostic C5 evidence and never promotes an OCI/customer C6
/// claim.
#[allow(clippy::too_many_lines)]
pub fn verify_rootfs_isolation_receipt(
    receipt_path: &Path,
    bundle: &Path,
) -> Result<VerifiedRootfsIsolationReceipt, DistributionError> {
    let bytes = read_bounded_regular_file(receipt_path, MAX_MANIFEST_BYTES)?;
    let envelope: serde_json::Value = serde_json::from_slice(&bytes).map_err(|error| {
        DistributionError::new(
            "rootfs_receipt_schema_invalid",
            format!("rootfs receipt is invalid JSON: {error}"),
        )
    })?;
    match envelope
        .get("schema_version")
        .and_then(serde_json::Value::as_str)
    {
        Some(ROOTFS_RECEIPT_SCHEMA_VERSION_V1) => {
            let receipt: RootfsIsolationReceiptV1 =
                read_canonical_json(receipt_path, MAX_MANIFEST_BYTES)?;
            validate_rootfs_isolation_evidence_v1(&receipt.evidence)?;
            verify_rootfs_receipt_hash(&receipt.evidence, &receipt.receipt_hash)?;
            verify_rootfs_bundle_binding(
                bundle,
                &receipt.evidence.release_id,
                &receipt.evidence.source_sha256,
                &receipt.evidence.bundle_manifest_hash,
                &receipt.evidence.bundle_manifest_file_sha256,
                &receipt.evidence.installer_sha256,
                &receipt.evidence.workbench_sha256,
                &receipt.evidence.workbench_version,
            )?;
            Ok(VerifiedRootfsIsolationReceipt::V1(Box::new(receipt)))
        }
        Some(ROOTFS_RECEIPT_SCHEMA_VERSION_V2) => {
            let receipt: RootfsIsolationReceiptV2 =
                read_canonical_json(receipt_path, MAX_MANIFEST_BYTES)?;
            validate_rootfs_isolation_evidence_v2(&receipt.evidence)?;
            verify_rootfs_receipt_hash(&receipt.evidence, &receipt.receipt_hash)?;
            verify_rootfs_bundle_binding(
                bundle,
                &receipt.evidence.release_id,
                &receipt.evidence.source_sha256,
                &receipt.evidence.bundle_manifest_hash,
                &receipt.evidence.bundle_manifest_file_sha256,
                &receipt.evidence.installer_sha256,
                &receipt.evidence.workbench_sha256,
                &receipt.evidence.workbench_version,
            )?;
            Ok(VerifiedRootfsIsolationReceipt::V2(Box::new(receipt)))
        }
        Some(ROOTFS_RECEIPT_SCHEMA_VERSION_V3) => {
            let receipt: RootfsIsolationReceiptV3 =
                read_canonical_json(receipt_path, MAX_MANIFEST_BYTES)?;
            validate_rootfs_isolation_evidence_v3(&receipt.evidence)?;
            verify_rootfs_receipt_hash(&receipt.evidence, &receipt.receipt_hash)?;
            verify_rootfs_bundle_binding(
                bundle,
                &receipt.evidence.release_id,
                &receipt.evidence.source_sha256,
                &receipt.evidence.bundle_manifest_hash,
                &receipt.evidence.bundle_manifest_file_sha256,
                &receipt.evidence.installer_sha256,
                &receipt.evidence.workbench_sha256,
                &receipt.evidence.workbench_version,
            )?;
            Ok(VerifiedRootfsIsolationReceipt::V3(Box::new(receipt)))
        }
        Some(ROOTFS_RECEIPT_SCHEMA_VERSION_V4) => {
            let receipt: RootfsIsolationReceiptV4 =
                read_canonical_json(receipt_path, MAX_MANIFEST_BYTES)?;
            validate_rootfs_isolation_evidence_v4(&receipt.evidence)?;
            verify_rootfs_receipt_hash(&receipt.evidence, &receipt.receipt_hash)?;
            verify_rootfs_bundle_binding(
                bundle,
                &receipt.evidence.release_id,
                &receipt.evidence.source_sha256,
                &receipt.evidence.bundle_manifest_hash,
                &receipt.evidence.bundle_manifest_file_sha256,
                &receipt.evidence.installer_sha256,
                &receipt.evidence.workbench_sha256,
                &receipt.evidence.workbench_version,
            )?;
            Ok(VerifiedRootfsIsolationReceipt::V4(Box::new(receipt)))
        }
        Some(ROOTFS_RECEIPT_SCHEMA_VERSION_V5) => {
            let receipt: RootfsIsolationReceiptV5 =
                read_canonical_json(receipt_path, MAX_MANIFEST_BYTES)?;
            validate_rootfs_isolation_evidence_v5(&receipt.evidence)?;
            verify_rootfs_receipt_hash(&receipt.evidence, &receipt.receipt_hash)?;
            verify_rootfs_bundle_binding(
                bundle,
                &receipt.evidence.prior.release_id,
                &receipt.evidence.prior.source_sha256,
                &receipt.evidence.prior.bundle_manifest_hash,
                &receipt.evidence.prior.bundle_manifest_file_sha256,
                &receipt.evidence.prior.installer_sha256,
                &receipt.evidence.prior.workbench_sha256,
                &receipt.evidence.prior.workbench_version,
            )?;
            Ok(VerifiedRootfsIsolationReceipt::V5(Box::new(receipt)))
        }
        Some(ROOTFS_RECEIPT_SCHEMA_VERSION_V6) => {
            let receipt: RootfsIsolationReceiptV6 =
                read_canonical_json(receipt_path, MAX_MANIFEST_BYTES)?;
            validate_rootfs_isolation_evidence_v6(&receipt.evidence)?;
            verify_rootfs_receipt_hash(&receipt.evidence, &receipt.receipt_hash)?;
            verify_rootfs_bundle_binding(
                bundle,
                &receipt.evidence.prior.prior.release_id,
                &receipt.evidence.prior.prior.source_sha256,
                &receipt.evidence.prior.prior.bundle_manifest_hash,
                &receipt.evidence.prior.prior.bundle_manifest_file_sha256,
                &receipt.evidence.prior.prior.installer_sha256,
                &receipt.evidence.prior.prior.workbench_sha256,
                &receipt.evidence.prior.prior.workbench_version,
            )?;
            Ok(VerifiedRootfsIsolationReceipt::V6(Box::new(receipt)))
        }
        Some(ROOTFS_RECEIPT_SCHEMA_VERSION_V7) => {
            let receipt: RootfsIsolationReceiptV7 =
                read_canonical_json(receipt_path, MAX_MANIFEST_BYTES)?;
            validate_rootfs_isolation_evidence_v7(&receipt.evidence)?;
            verify_rootfs_receipt_hash(&receipt.evidence, &receipt.receipt_hash)?;
            verify_rootfs_bundle_binding(
                bundle,
                &receipt.evidence.prior.prior.prior.release_id,
                &receipt.evidence.prior.prior.prior.source_sha256,
                &receipt.evidence.prior.prior.prior.bundle_manifest_hash,
                &receipt
                    .evidence
                    .prior
                    .prior
                    .prior
                    .bundle_manifest_file_sha256,
                &receipt.evidence.prior.prior.prior.installer_sha256,
                &receipt.evidence.prior.prior.prior.workbench_sha256,
                &receipt.evidence.prior.prior.prior.workbench_version,
            )?;
            Ok(VerifiedRootfsIsolationReceipt::V7(Box::new(receipt)))
        }
        Some(ROOTFS_RECEIPT_SCHEMA_VERSION_V8) => {
            let receipt: RootfsIsolationReceiptV8 =
                read_canonical_json(receipt_path, MAX_MANIFEST_BYTES)?;
            validate_rootfs_isolation_evidence_v8(&receipt.evidence)?;
            verify_rootfs_receipt_hash(&receipt.evidence, &receipt.receipt_hash)?;
            verify_rootfs_bundle_binding(
                bundle,
                &receipt.evidence.prior.prior.prior.prior.release_id,
                &receipt.evidence.prior.prior.prior.prior.source_sha256,
                &receipt
                    .evidence
                    .prior
                    .prior
                    .prior
                    .prior
                    .bundle_manifest_hash,
                &receipt
                    .evidence
                    .prior
                    .prior
                    .prior
                    .prior
                    .bundle_manifest_file_sha256,
                &receipt.evidence.prior.prior.prior.prior.installer_sha256,
                &receipt.evidence.prior.prior.prior.prior.workbench_sha256,
                &receipt.evidence.prior.prior.prior.prior.workbench_version,
            )?;
            Ok(VerifiedRootfsIsolationReceipt::V8(Box::new(receipt)))
        }
        Some(ROOTFS_RECEIPT_SCHEMA_VERSION_V9) => {
            let receipt: RootfsIsolationReceiptV9 =
                read_canonical_json(receipt_path, MAX_MANIFEST_BYTES)?;
            validate_rootfs_isolation_evidence_v9(&receipt.evidence)?;
            verify_rootfs_receipt_hash(&receipt.evidence, &receipt.receipt_hash)?;
            verify_rootfs_bundle_binding(
                bundle,
                &receipt.evidence.prior.prior.prior.prior.prior.release_id,
                &receipt.evidence.prior.prior.prior.prior.prior.source_sha256,
                &receipt
                    .evidence
                    .prior
                    .prior
                    .prior
                    .prior
                    .prior
                    .bundle_manifest_hash,
                &receipt
                    .evidence
                    .prior
                    .prior
                    .prior
                    .prior
                    .prior
                    .bundle_manifest_file_sha256,
                &receipt
                    .evidence
                    .prior
                    .prior
                    .prior
                    .prior
                    .prior
                    .installer_sha256,
                &receipt
                    .evidence
                    .prior
                    .prior
                    .prior
                    .prior
                    .prior
                    .workbench_sha256,
                &receipt
                    .evidence
                    .prior
                    .prior
                    .prior
                    .prior
                    .prior
                    .workbench_version,
            )?;
            Ok(VerifiedRootfsIsolationReceipt::V9(Box::new(receipt)))
        }
        Some(ROOTFS_RECEIPT_SCHEMA_VERSION_V10) => {
            let receipt: RootfsIsolationReceiptV10 =
                read_canonical_json(receipt_path, MAX_MANIFEST_BYTES)?;
            validate_rootfs_isolation_evidence_v10(&receipt.evidence)?;
            verify_rootfs_receipt_hash(&receipt.evidence, &receipt.receipt_hash)?;
            verify_rootfs_bundle_binding(
                bundle,
                &receipt
                    .evidence
                    .prior
                    .prior
                    .prior
                    .prior
                    .prior
                    .prior
                    .release_id,
                &receipt
                    .evidence
                    .prior
                    .prior
                    .prior
                    .prior
                    .prior
                    .prior
                    .source_sha256,
                &receipt
                    .evidence
                    .prior
                    .prior
                    .prior
                    .prior
                    .prior
                    .prior
                    .bundle_manifest_hash,
                &receipt
                    .evidence
                    .prior
                    .prior
                    .prior
                    .prior
                    .prior
                    .prior
                    .bundle_manifest_file_sha256,
                &receipt
                    .evidence
                    .prior
                    .prior
                    .prior
                    .prior
                    .prior
                    .prior
                    .installer_sha256,
                &receipt
                    .evidence
                    .prior
                    .prior
                    .prior
                    .prior
                    .prior
                    .prior
                    .workbench_sha256,
                &receipt
                    .evidence
                    .prior
                    .prior
                    .prior
                    .prior
                    .prior
                    .prior
                    .workbench_version,
            )?;
            Ok(VerifiedRootfsIsolationReceipt::V10(Box::new(receipt)))
        }
        Some(ROOTFS_RECEIPT_SCHEMA_VERSION_V11) => {
            let receipt: RootfsIsolationReceiptV11 =
                read_canonical_json(receipt_path, MAX_MANIFEST_BYTES)?;
            validate_rootfs_isolation_evidence_v11(&receipt.evidence)?;
            verify_rootfs_receipt_hash(&receipt.evidence, &receipt.receipt_hash)?;
            let base = &receipt.evidence.prior.prior.prior.prior.prior.prior.prior;
            verify_rootfs_bundle_binding(
                bundle,
                &base.release_id,
                &base.source_sha256,
                &base.bundle_manifest_hash,
                &base.bundle_manifest_file_sha256,
                &base.installer_sha256,
                &base.workbench_sha256,
                &base.workbench_version,
            )?;
            Ok(VerifiedRootfsIsolationReceipt::V11(Box::new(receipt)))
        }
        Some(ROOTFS_RECEIPT_SCHEMA_VERSION_V12) => {
            let receipt: RootfsIsolationReceiptV12 =
                read_canonical_json(receipt_path, MAX_MANIFEST_BYTES)?;
            validate_rootfs_isolation_evidence_v12(&receipt.evidence)?;
            verify_rootfs_receipt_hash(&receipt.evidence, &receipt.receipt_hash)?;
            let base = &receipt
                .evidence
                .prior
                .prior
                .prior
                .prior
                .prior
                .prior
                .prior
                .prior;
            verify_rootfs_bundle_binding(
                bundle,
                &base.release_id,
                &base.source_sha256,
                &base.bundle_manifest_hash,
                &base.bundle_manifest_file_sha256,
                &base.installer_sha256,
                &base.workbench_sha256,
                &base.workbench_version,
            )?;
            Ok(VerifiedRootfsIsolationReceipt::V12(Box::new(receipt)))
        }
        Some(ROOTFS_RECEIPT_SCHEMA_VERSION) => {
            let receipt: RootfsIsolationReceiptV13 =
                read_canonical_json(receipt_path, MAX_MANIFEST_BYTES)?;
            validate_rootfs_isolation_evidence_v13(&receipt.evidence)?;
            verify_rootfs_receipt_hash(&receipt.evidence, &receipt.receipt_hash)?;
            let base = &receipt
                .evidence
                .prior
                .prior
                .prior
                .prior
                .prior
                .prior
                .prior
                .prior
                .prior;
            verify_rootfs_bundle_binding(
                bundle,
                &base.release_id,
                &base.source_sha256,
                &base.bundle_manifest_hash,
                &base.bundle_manifest_file_sha256,
                &base.installer_sha256,
                &base.workbench_sha256,
                &base.workbench_version,
            )?;
            let manifest = verify_bundle(bundle)?;
            require_manifest_entry_hash(
                &manifest,
                "bin/structural-cli",
                &receipt.evidence.structural_cli_sha256,
            )?;
            Ok(VerifiedRootfsIsolationReceipt::V13(Box::new(receipt)))
        }
        _ => Err(DistributionError::new(
            "rootfs_receipt_schema_invalid",
            "rootfs receipt schema is unsupported",
        )),
    }
}

fn verify_rootfs_receipt_hash<T: Serialize>(
    evidence: &T,
    receipt_hash: &str,
) -> Result<(), DistributionError> {
    if receipt_hash != sha256_identity(&canonical_json(evidence)?) {
        return Err(DistributionError::new(
            "rootfs_receipt_hash_mismatch",
            "rootfs receipt self-hash does not match",
        ));
    }
    Ok(())
}

#[allow(clippy::too_many_arguments)]
fn verify_rootfs_bundle_binding(
    bundle: &Path,
    release_id: &str,
    source_sha256: &str,
    bundle_manifest_hash: &str,
    bundle_manifest_file_sha256: &str,
    installer_sha256: &str,
    workbench_sha256: &str,
    workbench_version: &str,
) -> Result<(), DistributionError> {
    let manifest = verify_bundle(bundle)?;
    if manifest.backend_profile != BackendProfileV1::CpuOnly
        || release_id != manifest.release_id
        || source_sha256 != manifest.source_sha256
        || bundle_manifest_hash != manifest.manifest_hash
        || bundle_manifest_file_sha256 != sha256_file(&bundle.join(MANIFEST_NAME))?
    {
        return Err(DistributionError::new(
            "rootfs_receipt_bundle_mismatch",
            "rootfs receipt does not identify the supplied CPU bundle",
        ));
    }
    require_manifest_entry_hash(&manifest, "bin/structural-installer", installer_sha256)?;
    require_manifest_entry_hash(&manifest, "bin/structural-workbench", workbench_sha256)?;
    if workbench_version != format!("structural-workbench {}", manifest.package_version) {
        return Err(DistributionError::new(
            "rootfs_receipt_bundle_mismatch",
            "rootfs Workbench version does not match the supplied bundle",
        ));
    }
    Ok(())
}

/// Installs or updates to a verified release through an atomic, recoverable transaction.
///
/// # Errors
///
/// Returns an error when bundle verification, locking, staging, recovery, or activation fails.
pub fn install_bundle(
    bundle: &Path,
    install_root: &Path,
) -> Result<ActivationStateV1, DistributionError> {
    install_bundle_inner(bundle, install_root, InstallInterruption::None)
}

fn install_bundle_inner(
    bundle: &Path,
    install_root: &Path,
    interruption: InstallInterruption,
) -> Result<ActivationStateV1, DistributionError> {
    let manifest = verify_bundle(bundle)?;
    let _lock = lock_install_root(install_root)?;
    recover_locked(install_root)?;
    let current = read_activation_optional(install_root)?;
    if current
        .as_ref()
        .is_some_and(|state| state.current_release == manifest.release_id)
    {
        let release = release_path(install_root, &manifest.release_id);
        let installed = verify_bundle(&release)?;
        if installed.manifest_hash != manifest.manifest_hash {
            return Err(DistributionError::new(
                "release_id_immutable",
                "active release ID already names different package bytes",
            ));
        }
        return Ok(current.expect("checked active state"));
    }
    let releases = install_root.join(RELEASES_DIRECTORY);
    let staging_name = format!(".stage-{}", unique_token());
    let staging = releases.join(&staging_name);
    let target = release_path(install_root, &manifest.release_id);
    if path_entry_exists(&target)? {
        let installed = verify_bundle(&target)?;
        if installed.manifest_hash != manifest.manifest_hash {
            return Err(DistributionError::new(
                "release_id_immutable",
                "release ID already names different package bytes",
            ));
        }
    } else {
        copy_verified_bundle(bundle, &staging, &manifest)?;
    }
    let desired = ActivationStateV1 {
        schema_version: ACTIVATION_SCHEMA_VERSION.to_owned(),
        generation: next_generation(current.as_ref())?,
        current_release: manifest.release_id.clone(),
        previous_release: current.as_ref().map(|state| state.current_release.clone()),
        current_manifest_hash: manifest.manifest_hash.clone(),
    };
    let mut transaction = InstallTransactionV1 {
        schema_version: TRANSACTION_SCHEMA_VERSION.to_owned(),
        operation: TransactionOperationV1::Install,
        phase: TransactionPhaseV1::Prepared,
        release_id: manifest.release_id,
        manifest_hash: manifest.manifest_hash,
        staging_name: if path_entry_exists(&staging)? {
            Some(staging_name)
        } else {
            None
        },
        desired_activation: desired.clone(),
    };
    write_transaction(install_root, &transaction)?;
    maybe_interrupt(interruption, InstallInterruption::AfterPrepared)?;
    materialize_transaction(install_root, &mut transaction)?;
    maybe_interrupt(interruption, InstallInterruption::AfterMaterialized)?;
    activate_transaction(install_root, &mut transaction)?;
    maybe_interrupt(interruption, InstallInterruption::AfterActivated)?;
    finish_transaction(install_root)?;
    Ok(desired)
}

/// Completes an interrupted durable install transaction and returns the active release.
///
/// # Errors
///
/// Returns an error when state is corrupt, transaction bindings differ, or no release is active.
pub fn recover_install(install_root: &Path) -> Result<ActivationStateV1, DistributionError> {
    let _lock = lock_install_root(install_root)?;
    recover_locked(install_root)?;
    read_activation_optional(install_root)?.ok_or_else(|| {
        DistributionError::new(
            "activation_missing",
            "installation has no active release after recovery",
        )
    })
}

/// Atomically swaps the current and previous immutable releases.
///
/// # Errors
///
/// Returns an error when no previous release exists or its bytes fail verification.
pub fn rollback_install(install_root: &Path) -> Result<ActivationStateV1, DistributionError> {
    let _lock = lock_install_root(install_root)?;
    recover_locked(install_root)?;
    let current = read_activation_optional(install_root)?.ok_or_else(|| {
        DistributionError::new("activation_missing", "installation has no active release")
    })?;
    let previous_release = current.previous_release.clone().ok_or_else(|| {
        DistributionError::new(
            "rollback_unavailable",
            "activation state has no previous release",
        )
    })?;
    let previous_manifest = verify_bundle(&release_path(install_root, &previous_release))?;
    let desired = ActivationStateV1 {
        schema_version: ACTIVATION_SCHEMA_VERSION.to_owned(),
        generation: current.generation.checked_add(1).ok_or_else(|| {
            DistributionError::new(
                "activation_generation_overflow",
                "activation generation cannot be incremented",
            )
        })?,
        current_release: previous_release.clone(),
        previous_release: Some(current.current_release),
        current_manifest_hash: previous_manifest.manifest_hash.clone(),
    };
    let mut transaction = InstallTransactionV1 {
        schema_version: TRANSACTION_SCHEMA_VERSION.to_owned(),
        operation: TransactionOperationV1::Rollback,
        phase: TransactionPhaseV1::Materialized,
        release_id: previous_release,
        manifest_hash: previous_manifest.manifest_hash,
        staging_name: None,
        desired_activation: desired.clone(),
    };
    write_transaction(install_root, &transaction)?;
    activate_transaction(install_root, &mut transaction)?;
    finish_transaction(install_root)?;
    Ok(desired)
}

/// Returns a verified activation state without mutating or recovering the installation.
///
/// # Errors
///
/// Returns an error when recovery is pending or active state and release bytes do not agree.
pub fn installation_status(
    install_root: &Path,
) -> Result<Option<ActivationStateV1>, DistributionError> {
    ensure_directory(install_root, "install root")?;
    if path_entry_exists(&install_root.join(STATE_DIRECTORY).join(TRANSACTION_NAME))? {
        return Err(DistributionError::new(
            "recovery_required",
            "an interrupted install transaction must be recovered before status is authoritative",
        ));
    }
    let state = read_activation_optional(install_root)?;
    if let Some(active) = &state {
        let manifest = verify_bundle(&release_path(install_root, &active.current_release))?;
        if manifest.manifest_hash != active.current_manifest_hash {
            return Err(DistributionError::new(
                "activation_hash_mismatch",
                "active release does not match activation state",
            ));
        }
    }
    Ok(state)
}

/// Returns the verified active payload directory, if a release is active.
///
/// # Errors
///
/// Returns the same validation errors as [`installation_status`].
pub fn active_payload_path(install_root: &Path) -> Result<Option<PathBuf>, DistributionError> {
    installation_status(install_root).map(|state| {
        state.map(|active| {
            release_path(install_root, &active.current_release).join(PAYLOAD_DIRECTORY)
        })
    })
}

fn lock_install_root(install_root: &Path) -> Result<InstallLock, DistributionError> {
    match fs::symlink_metadata(install_root) {
        Ok(metadata) if metadata.file_type().is_symlink() || !metadata.is_dir() => {
            return Err(DistributionError::new(
                "install_root_invalid",
                "install root must be a real directory",
            ));
        }
        Ok(_) => {}
        Err(error) if error.kind() == io::ErrorKind::NotFound => {
            fs::create_dir(install_root)
                .map_err(|error| io_error("install_root_create_failed", error))?;
        }
        Err(error) => return Err(io_error("install_root_inspect_failed", error)),
    }
    create_real_subdirectory(install_root, RELEASES_DIRECTORY)?;
    create_real_subdirectory(install_root, STATE_DIRECTORY)?;
    let lock_path = install_root.join(LOCK_NAME);
    reject_symlink_if_present(&lock_path, "install lock")?;
    let file = open_install_lock(&lock_path)?;
    file.lock_exclusive()
        .map_err(|error| io_error("install_lock_failed", error))?;
    Ok(InstallLock { file })
}

fn recover_locked(install_root: &Path) -> Result<(), DistributionError> {
    let path = install_root.join(STATE_DIRECTORY).join(TRANSACTION_NAME);
    if !path_entry_exists(&path)? {
        return Ok(());
    }
    let mut transaction: InstallTransactionV1 = read_canonical_json(&path, MAX_MANIFEST_BYTES)?;
    validate_transaction(&transaction)?;
    if transaction.phase == TransactionPhaseV1::Prepared {
        materialize_transaction(install_root, &mut transaction)?;
    }
    if transaction.phase == TransactionPhaseV1::Materialized {
        activate_transaction(install_root, &mut transaction)?;
    }
    finish_transaction(install_root)
}

fn materialize_transaction(
    install_root: &Path,
    transaction: &mut InstallTransactionV1,
) -> Result<(), DistributionError> {
    if transaction.operation == TransactionOperationV1::Install {
        let target = release_path(install_root, &transaction.release_id);
        if let Some(staging_name) = &transaction.staging_name {
            validate_staging_name(staging_name)?;
            let staging = install_root.join(RELEASES_DIRECTORY).join(staging_name);
            if path_entry_exists(&target)? {
                let existing = verify_bundle(&target)?;
                if existing.manifest_hash != transaction.manifest_hash {
                    return Err(DistributionError::new(
                        "release_id_immutable",
                        "materialized release differs from transaction manifest",
                    ));
                }
                if path_entry_exists(&staging)? {
                    fs::remove_dir_all(&staging)
                        .map_err(|error| io_error("staging_cleanup_failed", error))?;
                }
            } else {
                let staged = verify_bundle(&staging)?;
                if staged.manifest_hash != transaction.manifest_hash {
                    return Err(DistributionError::new(
                        "staging_hash_mismatch",
                        "staged release differs from transaction manifest",
                    ));
                }
                fs::rename(&staging, &target)
                    .map_err(|error| io_error("release_materialize_failed", error))?;
                sync_directory(&install_root.join(RELEASES_DIRECTORY))?;
            }
        } else {
            let existing = verify_bundle(&target)?;
            if existing.manifest_hash != transaction.manifest_hash {
                return Err(DistributionError::new(
                    "release_id_immutable",
                    "existing release differs from transaction manifest",
                ));
            }
        }
    }
    transaction.phase = TransactionPhaseV1::Materialized;
    write_transaction(install_root, transaction)
}

fn activate_transaction(
    install_root: &Path,
    transaction: &mut InstallTransactionV1,
) -> Result<(), DistributionError> {
    let release = verify_bundle(&release_path(install_root, &transaction.release_id))?;
    if release.manifest_hash != transaction.manifest_hash
        || transaction.desired_activation.current_release != transaction.release_id
        || transaction.desired_activation.current_manifest_hash != transaction.manifest_hash
    {
        return Err(DistributionError::new(
            "transaction_binding_mismatch",
            "transaction, activation, and release identities differ",
        ));
    }
    let state_path = install_root.join(STATE_DIRECTORY).join(ACTIVATION_NAME);
    atomic_write_canonical(&state_path, &transaction.desired_activation)?;
    transaction.phase = TransactionPhaseV1::Activated;
    write_transaction(install_root, transaction)
}

fn finish_transaction(install_root: &Path) -> Result<(), DistributionError> {
    let path = install_root.join(STATE_DIRECTORY).join(TRANSACTION_NAME);
    match fs::remove_file(path) {
        Ok(()) => sync_directory(&install_root.join(STATE_DIRECTORY)),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(io_error("transaction_finish_failed", error)),
    }
}

fn write_transaction(
    install_root: &Path,
    transaction: &InstallTransactionV1,
) -> Result<(), DistributionError> {
    validate_transaction(transaction)?;
    atomic_write_canonical(
        &install_root.join(STATE_DIRECTORY).join(TRANSACTION_NAME),
        transaction,
    )
}

fn validate_transaction(transaction: &InstallTransactionV1) -> Result<(), DistributionError> {
    if transaction.schema_version != TRANSACTION_SCHEMA_VERSION {
        return Err(DistributionError::new(
            "transaction_schema_unsupported",
            "install transaction schema is unsupported",
        ));
    }
    validate_release_id(&transaction.release_id)?;
    validate_sha256_identity(&transaction.manifest_hash, "transaction manifest hash")?;
    validate_activation(&transaction.desired_activation)?;
    if let Some(staging) = &transaction.staging_name {
        validate_staging_name(staging)?;
    }
    Ok(())
}

fn validate_activation(activation: &ActivationStateV1) -> Result<(), DistributionError> {
    if activation.schema_version != ACTIVATION_SCHEMA_VERSION || activation.generation == 0 {
        return Err(DistributionError::new(
            "activation_invalid",
            "activation schema or generation is invalid",
        ));
    }
    validate_release_id(&activation.current_release)?;
    if let Some(previous) = &activation.previous_release {
        validate_release_id(previous)?;
    }
    validate_sha256_identity(
        &activation.current_manifest_hash,
        "activation manifest hash",
    )
}

fn read_activation_optional(
    install_root: &Path,
) -> Result<Option<ActivationStateV1>, DistributionError> {
    let path = install_root.join(STATE_DIRECTORY).join(ACTIVATION_NAME);
    if !path_entry_exists(&path)? {
        return Ok(None);
    }
    let activation: ActivationStateV1 = read_canonical_json(&path, MAX_MANIFEST_BYTES)?;
    validate_activation(&activation)?;
    Ok(Some(activation))
}

fn copy_verified_bundle(
    source: &Path,
    destination: &Path,
    manifest: &DistributionManifestV1,
) -> Result<(), DistributionError> {
    fs::create_dir(destination).map_err(|error| io_error("release_stage_create_failed", error))?;
    let payload_destination = destination.join(PAYLOAD_DIRECTORY);
    fs::create_dir(&payload_destination)
        .map_err(|error| io_error("release_payload_create_failed", error))?;
    let outcome = (|| {
        for entry in &manifest.files {
            let relative = validated_relative_path(&entry.path)?;
            let source_file = source.join(PAYLOAD_DIRECTORY).join(&relative);
            let destination_file = payload_destination.join(relative);
            if let Some(parent) = destination_file.parent() {
                fs::create_dir_all(parent)
                    .map_err(|error| io_error("release_directory_create_failed", error))?;
            }
            let (size, mode, hash) = copy_regular_file(&source_file, &destination_file)?;
            if size != entry.size || mode != entry.mode || hash != entry.sha256 {
                return Err(DistributionError::new(
                    "release_copy_mismatch",
                    format!("copied payload changed for {}", entry.path),
                ));
            }
        }
        let manifest_bytes = canonical_json(manifest)?;
        write_new_file(&destination.join(MANIFEST_NAME), &manifest_bytes, 0o444)?;
        sync_directory_tree(destination)?;
        let copied = verify_bundle(destination)?;
        if copied.manifest_hash != manifest.manifest_hash {
            return Err(DistributionError::new(
                "release_copy_mismatch",
                "copied release manifest changed",
            ));
        }
        Ok(())
    })();
    if outcome.is_err() {
        let _ = fs::remove_dir_all(destination);
    }
    outcome
}

fn collect_payload_sources(
    root: &Path,
    directory: &Path,
    output: &mut Vec<(PathBuf, PathBuf)>,
) -> Result<(), DistributionError> {
    let mut entries = fs::read_dir(directory)
        .map_err(|error| io_error("payload_directory_read_failed", error))?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|error| io_error("payload_entry_read_failed", error))?;
    entries.sort_by_key(fs::DirEntry::file_name);
    for entry in entries {
        let path = entry.path();
        let relative = path.strip_prefix(root).map_err(|_| {
            DistributionError::new("payload_path_invalid", "payload path escaped its root")
        })?;
        let metadata = fs::symlink_metadata(&path)
            .map_err(|error| io_error("payload_metadata_failed", error))?;
        if metadata.is_dir() {
            collect_payload_sources(root, &path, output)?;
        } else if metadata.is_file() {
            output.push((relative.to_path_buf(), path));
        } else if metadata.file_type().is_symlink() {
            let resolved = path
                .canonicalize()
                .map_err(|error| io_error("payload_symlink_resolve_failed", error))?;
            if !resolved.starts_with(root) {
                return Err(DistributionError::new(
                    "payload_symlink_escape",
                    "payload symlink resolves outside the payload root",
                ));
            }
            let target = fs::metadata(&resolved)
                .map_err(|error| io_error("payload_symlink_target_failed", error))?;
            if !target.is_file() {
                return Err(DistributionError::new(
                    "payload_entry_unsupported",
                    "only regular-file symlinks may be normalized into a bundle",
                ));
            }
            output.push((relative.to_path_buf(), resolved));
        } else {
            return Err(DistributionError::new(
                "payload_entry_unsupported",
                "payload contains a socket, device, FIFO, or other unsupported entry",
            ));
        }
    }
    Ok(())
}

fn verify_payload_files(
    bundle: &Path,
    manifest: &DistributionManifestV1,
) -> Result<(), DistributionError> {
    let payload = bundle.join(PAYLOAD_DIRECTORY);
    ensure_directory(&payload, "bundle payload")?;
    let mut actual = Vec::new();
    collect_strict_regular_files(&payload, &payload, &mut actual)?;
    let expected = manifest
        .files
        .iter()
        .map(|entry| entry.path.clone())
        .collect::<Vec<_>>();
    let actual = actual
        .iter()
        .map(|path| portable_relative_path(path))
        .collect::<Result<Vec<_>, _>>()?;
    if actual != expected {
        return Err(DistributionError::new(
            "bundle_inventory_mismatch",
            "payload file inventory differs from the manifest",
        ));
    }
    let mut total_size = 0_u64;
    for entry in &manifest.files {
        let relative = validated_relative_path(&entry.path)?;
        let path = payload.join(relative);
        let metadata = fs::symlink_metadata(&path)
            .map_err(|error| io_error("bundle_payload_metadata_failed", error))?;
        if !metadata.is_file() || metadata.file_type().is_symlink() {
            return Err(DistributionError::new(
                "bundle_payload_not_regular",
                format!("payload entry is not a regular file: {}", entry.path),
            ));
        }
        let mode = portable_mode(&metadata);
        let size = metadata.len();
        if size != entry.size || mode != entry.mode || sha256_file(&path)? != entry.sha256 {
            return Err(DistributionError::new(
                "bundle_payload_hash_mismatch",
                format!("payload bytes or metadata changed: {}", entry.path),
            ));
        }
        total_size = total_size.checked_add(size).ok_or_else(|| {
            DistributionError::new("bundle_size_overflow", "payload byte count overflowed")
        })?;
        if total_size > MAX_TOTAL_BYTES {
            return Err(DistributionError::new(
                "bundle_total_size_exceeded",
                "payload bytes exceed the distribution limit",
            ));
        }
    }
    Ok(())
}

fn collect_strict_regular_files(
    root: &Path,
    directory: &Path,
    output: &mut Vec<PathBuf>,
) -> Result<(), DistributionError> {
    let metadata = fs::symlink_metadata(directory)
        .map_err(|error| io_error("bundle_directory_metadata_failed", error))?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err(DistributionError::new(
            "bundle_directory_invalid",
            "bundle directory tree contains a symlink or non-directory",
        ));
    }
    let mut entries = fs::read_dir(directory)
        .map_err(|error| io_error("bundle_directory_read_failed", error))?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|error| io_error("bundle_entry_read_failed", error))?;
    entries.sort_by_key(fs::DirEntry::file_name);
    for entry in entries {
        let path = entry.path();
        let metadata = fs::symlink_metadata(&path)
            .map_err(|error| io_error("bundle_entry_metadata_failed", error))?;
        if metadata.file_type().is_symlink() {
            return Err(DistributionError::new(
                "bundle_symlink_rejected",
                "verified bundles must not contain symlinks",
            ));
        }
        if metadata.is_dir() {
            collect_strict_regular_files(root, &path, output)?;
        } else if metadata.is_file() {
            output.push(
                path.strip_prefix(root)
                    .map_err(|_| {
                        DistributionError::new(
                            "bundle_path_invalid",
                            "bundle entry escaped the payload root",
                        )
                    })?
                    .to_path_buf(),
            );
        } else {
            return Err(DistributionError::new(
                "bundle_entry_unsupported",
                "bundle contains a socket, device, FIFO, or other unsupported entry",
            ));
        }
    }
    Ok(())
}

#[derive(Debug)]
struct ReportedWorkbenchSummary {
    session_id: String,
    session_hash: String,
    stage: String,
    terminal_status: String,
    comparison_passed: bool,
    result_ir_sha256: String,
    comparison_ir_sha256: String,
    report_pdf_sha256: String,
    result_recovery_ir_sha256: Option<String>,
    reaction_result_ir_sha256: Option<String>,
    report_document_sha256: Option<String>,
    mgt_source_sha256: Option<String>,
    mgt_import_health_sha256: Option<String>,
}

struct OperatorSurfaceProbe<'a> {
    import_kind: &'static str,
    analysis_profile: Option<&'static str>,
    expected_export_artifact_count: usize,
    inspect_before_review: &'a Path,
    review_show: &'a Path,
    inspect_after_review: &'a Path,
    export: &'a Path,
}

struct OperatorSurfaceSummary {
    decision: String,
    inspect_before_review_sha256: String,
    review_sha256: String,
    inspect_after_review_sha256: String,
    export_sha256: String,
}

struct ReadOnlySurfaceSummary {
    catalog_sha256: String,
    evidence_sha256: String,
}

struct LocalizedPdfSurfaceSummary {
    en_us_pdf: String,
    ko_kr_pdf: String,
    en_us_receipt: String,
    ko_kr_receipt: String,
}

struct ReactionViewSurfaceSummary {
    model_en_us: String,
    model_ko_kr: String,
    model_window: String,
    mgt_en_us: String,
    mgt_ko_kr: String,
}

#[derive(Debug)]
struct ReactionViewArtifact {
    bytes: Vec<u8>,
    sha256: String,
}

struct ReactionViewProbe<'a> {
    label: &'a str,
    workbench_root: &'a Path,
    session_before: &'a Path,
    en_us_first: &'a Path,
    en_us_second: &'a Path,
    ko_kr_first: &'a Path,
    ko_kr_second: &'a Path,
    window: Option<&'a Path>,
}

struct NodalDisplacementViewSurfaceSummary {
    model_en_us: String,
    model_ko_kr: String,
    model_window: String,
    mgt_en_us: String,
    mgt_ko_kr: String,
}

#[derive(Debug)]
struct NodalDisplacementViewArtifact {
    bytes: Vec<u8>,
    sha256: String,
}

struct NodalDisplacementViewProbe<'a> {
    label: &'a str,
    workbench_root: &'a Path,
    session_before: &'a Path,
    en_us_first: &'a Path,
    en_us_second: &'a Path,
    ko_kr_first: &'a Path,
    ko_kr_second: &'a Path,
    window: Option<&'a Path>,
}

struct LinearDeformedViewSurfaceSummary {
    model_en_us: String,
    model_ko_kr: String,
    model_projection: String,
    mgt_en_us: String,
    mgt_ko_kr: String,
}

#[derive(Debug)]
struct LinearDeformedViewArtifact {
    bytes: Vec<u8>,
    sha256: String,
}

struct LinearDeformedViewProbe<'a> {
    label: &'a str,
    workbench_root: &'a Path,
    session_before: &'a Path,
    projection: &'a str,
    en_us_first: &'a Path,
    en_us_second: &'a Path,
    ko_kr_first: &'a Path,
    ko_kr_second: &'a Path,
    alternate_projection: Option<&'a Path>,
}

struct LinearElementRecoveryViewSurfaceSummary {
    model_en_us: String,
    model_ko_kr: String,
    mgt_en_us: String,
    mgt_ko_kr: String,
}

#[derive(Debug)]
struct LinearElementRecoveryViewArtifact {
    bytes: Vec<u8>,
    sha256: String,
}

struct LinearElementRecoveryViewProbe<'a> {
    label: &'a str,
    workbench_root: &'a Path,
    session_before: &'a Path,
    en_us_first: &'a Path,
    en_us_second: &'a Path,
    ko_kr_first: &'a Path,
    ko_kr_second: &'a Path,
}

#[allow(clippy::struct_field_names)]
struct ModelModalSurfaceSummary {
    request_sha256: String,
    request_receipt_sha256: String,
    checkpoint_sha256: String,
    result_ir_sha256: String,
    run_receipt_sha256: String,
    view_en_us_sha256: String,
    view_ko_kr_sha256: String,
}

struct ReactionAuditSurfaceSummary {
    model_en_us: String,
    model_ko_kr: String,
    mgt_en_us: String,
    mgt_ko_kr: String,
}

#[derive(Debug)]
struct ReactionAuditArtifact {
    bytes: Vec<u8>,
    sha256: String,
}

struct ReactionAuditProbe<'a> {
    label: &'a str,
    workbench_root: &'a Path,
    session_before: &'a Path,
    en_us_first: &'a Path,
    en_us_second: &'a Path,
    ko_kr_first: &'a Path,
    ko_kr_second: &'a Path,
    normalized_mgt: bool,
}

fn resolve_real_directory(path: &Path, label: &str) -> Result<PathBuf, DistributionError> {
    ensure_directory(path, label)?;
    path.canonicalize()
        .map_err(|error| io_error("directory_resolve_failed", error))
}

fn resolve_workspace_child(
    workspace: &Path,
    child: &Path,
    label: &str,
) -> Result<PathBuf, DistributionError> {
    let resolved = resolve_real_directory(child, label)?;
    if resolved == workspace || !resolved.starts_with(workspace) {
        return Err(DistributionError::new(
            "rootfs_workbench_path_invalid",
            format!("{label} must be a real child directory of the operator workspace"),
        ));
    }
    Ok(resolved)
}

fn read_direct_workspace_file(
    workspace: &Path,
    path: &Path,
    label: &str,
) -> Result<Vec<u8>, DistributionError> {
    let parent = path.parent().ok_or_else(|| {
        DistributionError::new(
            "rootfs_reaction_view_path_invalid",
            format!("{label} must have a parent directory"),
        )
    })?;
    if resolve_real_directory(parent, label)? != workspace {
        return Err(DistributionError::new(
            "rootfs_reaction_view_path_invalid",
            format!("{label} must be a direct operator-workspace file"),
        ));
    }
    read_bounded_regular_file(path, MAX_MANIFEST_BYTES)
}

fn validate_reaction_view_rows(
    text: &str,
    expected_start: usize,
    expected_count: usize,
    label: &str,
) -> Result<(), DistributionError> {
    let mut row_count = 0usize;
    for line in text.lines() {
        let line_bytes = line.as_bytes();
        if line_bytes.len() < 7
            || !line_bytes[..6].iter().all(u8::is_ascii_digit)
            || line_bytes[6] != b'\t'
        {
            continue;
        }
        let fields = line.split('\t').collect::<Vec<_>>();
        let expected_row = expected_start + row_count;
        let valid_numbers = fields.get(4..7).is_some_and(|values| {
            values
                .iter()
                .all(|value| value.parse::<f64>().is_ok_and(f64::is_finite))
        });
        if fields.len() != 8
            || fields[0] != format!("{expected_row:06}")
            || fields[1].is_empty()
            || !matches!(fields[2], "UX" | "UY" | "UZ" | "RX" | "RY" | "RZ")
            || fields[3].len() != 10
            || !fields[3].bytes().all(|byte| byte.is_ascii_digit())
            || !valid_numbers
            || !matches!(fields[7], "N" | "N*m")
        {
            return Err(DistributionError::new(
                "rootfs_reaction_view_row_invalid",
                format!("{label} has an invalid reaction row"),
            ));
        }
        row_count += 1;
    }
    if row_count != expected_count {
        return Err(DistributionError::new(
            "rootfs_reaction_view_row_invalid",
            format!("{label} has {row_count} rows instead of {expected_count}"),
        ));
    }
    Ok(())
}

fn inspect_reaction_view_artifact(
    workspace: &Path,
    path: &Path,
    locale: &str,
    expected_start: usize,
    expected_count: usize,
    expected_total: usize,
    label: &str,
) -> Result<ReactionViewArtifact, DistributionError> {
    let bytes = read_direct_workspace_file(workspace, path, label)?;
    if bytes.contains(&0x1b) {
        return Err(DistributionError::new(
            "rootfs_reaction_view_unsafe",
            format!("{label} contains an ANSI escape byte"),
        ));
    }
    let text = std::str::from_utf8(&bytes).map_err(|_| {
        DistributionError::new(
            "rootfs_reaction_view_invalid",
            format!("{label} must be UTF-8"),
        )
    })?;
    let without_final_newline = text.strip_suffix('\n').ok_or_else(|| {
        DistributionError::new(
            "rootfs_reaction_view_noncanonical",
            format!("{label} must end with one newline"),
        )
    })?;
    let final_line_start = without_final_newline
        .rfind('\n')
        .map_or(0, |position| position + 1);
    let final_line = &without_final_newline[final_line_start..];
    let hash_label = match locale {
        "en-US" => "View hash: ",
        "ko-KR" => "보기 해시: ",
        _ => {
            return Err(DistributionError::new(
                "rootfs_reaction_view_invalid",
                "reaction view locale contract is unsupported",
            ));
        }
    };
    let declared_hash = final_line.strip_prefix(hash_label).ok_or_else(|| {
        DistributionError::new(
            "rootfs_reaction_view_hash_missing",
            format!("{label} has no terminal self-hash"),
        )
    })?;
    validate_sha256_identity(declared_hash, "rootfs reaction view self-hash")?;
    if declared_hash != sha256_identity(&bytes[..final_line_start]) {
        return Err(DistributionError::new(
            "rootfs_reaction_view_hash_mismatch",
            format!("{label} self-hash does not verify"),
        ));
    }

    let (schema_line, locale_line, display_line) = if locale == "en-US" {
        (
            "Schema: structural-native-workbench-model-ir-linear-reaction-view.v1",
            "Locale: en-US",
            format!(
                "Displayed rows: {}-{} of {expected_total}",
                expected_start,
                expected_start + expected_count - 1
            ),
        )
    } else {
        (
            "스키마: structural-native-workbench-model-ir-linear-reaction-view.v1",
            "로케일: ko-KR",
            format!(
                "표시 행: {}-{} / {expected_total}",
                expected_start,
                expected_start + expected_count - 1
            ),
        )
    };
    if !text.lines().any(|line| line == schema_line)
        || !text.lines().any(|line| line == locale_line)
        || !text.lines().any(|line| line == display_line)
        || !text.contains("fallback 0")
    {
        return Err(DistributionError::new(
            "rootfs_reaction_view_contract_invalid",
            format!("{label} does not expose the exact bounded reaction-view contract"),
        ));
    }

    validate_reaction_view_rows(text, expected_start, expected_count, label)?;
    Ok(ReactionViewArtifact {
        sha256: sha256_identity(&bytes),
        bytes,
    })
}

fn inspect_reaction_view_probe(
    workspace: &Path,
    probe: &ReactionViewProbe<'_>,
) -> Result<(String, String, Option<String>), DistributionError> {
    let session_before = read_direct_workspace_file(
        workspace,
        probe.session_before,
        &format!("{} pre-view session", probe.label),
    )?;
    let session_after = read_bounded_regular_file(
        &probe.workbench_root.join("workbench-session.json"),
        MAX_MANIFEST_BYTES,
    )?;
    if session_before != session_after {
        return Err(DistributionError::new(
            "rootfs_reaction_view_session_mutated",
            format!("{} reaction view mutated its durable session", probe.label),
        ));
    }
    let en_us_first = inspect_reaction_view_artifact(
        workspace,
        probe.en_us_first,
        "en-US",
        1,
        6,
        6,
        &format!("{} en-US first reaction view", probe.label),
    )?;
    let en_us_second = inspect_reaction_view_artifact(
        workspace,
        probe.en_us_second,
        "en-US",
        1,
        6,
        6,
        &format!("{} en-US second reaction view", probe.label),
    )?;
    let ko_kr_first = inspect_reaction_view_artifact(
        workspace,
        probe.ko_kr_first,
        "ko-KR",
        1,
        6,
        6,
        &format!("{} ko-KR first reaction view", probe.label),
    )?;
    let ko_kr_second = inspect_reaction_view_artifact(
        workspace,
        probe.ko_kr_second,
        "ko-KR",
        1,
        6,
        6,
        &format!("{} ko-KR second reaction view", probe.label),
    )?;
    if en_us_first.bytes != en_us_second.bytes || ko_kr_first.bytes != ko_kr_second.bytes {
        return Err(DistributionError::new(
            "rootfs_reaction_view_determinism_failed",
            format!("{} repeated reaction views differ", probe.label),
        ));
    }
    if en_us_first.sha256 == ko_kr_first.sha256 {
        return Err(DistributionError::new(
            "rootfs_reaction_view_locale_collision",
            format!(
                "{} reaction view locales have the same identity",
                probe.label
            ),
        ));
    }
    let window = probe
        .window
        .map(|path| {
            inspect_reaction_view_artifact(
                workspace,
                path,
                "en-US",
                2,
                2,
                6,
                &format!("{} bounded reaction view", probe.label),
            )
        })
        .transpose()?;
    if window
        .as_ref()
        .is_some_and(|artifact| artifact.sha256 == en_us_first.sha256)
    {
        return Err(DistributionError::new(
            "rootfs_reaction_view_window_collision",
            format!(
                "{} bounded reaction view has the full-view identity",
                probe.label
            ),
        ));
    }
    Ok((
        en_us_first.sha256,
        ko_kr_first.sha256,
        window.map(|artifact| artifact.sha256),
    ))
}

fn inspect_reaction_view_wrong_profile_failure(
    workspace: &Path,
    path: &Path,
) -> Result<(), DistributionError> {
    let bytes = read_direct_workspace_file(workspace, path, "wrong-profile reaction failure")?;
    let canonical = bytes.strip_suffix(b"\n").ok_or_else(|| {
        DistributionError::new(
            "rootfs_reaction_view_failure_noncanonical",
            "wrong-profile reaction failure must be one JSON line",
        )
    })?;
    let value = structural_contracts::model_ir::decode_json_strict(canonical).map_err(|error| {
        DistributionError::new(
            "rootfs_reaction_view_failure_invalid",
            format!("wrong-profile reaction failure is invalid JSON: {error}"),
        )
    })?;
    let object = value.as_object().ok_or_else(|| {
        DistributionError::new(
            "rootfs_reaction_view_failure_invalid",
            "wrong-profile reaction failure must be an object",
        )
    })?;
    let actual = object.keys().map(String::as_str).collect::<BTreeSet<_>>();
    let expected = ["code", "detail", "schema_version"]
        .into_iter()
        .collect::<BTreeSet<_>>();
    if actual != expected
        || value
            .get("schema_version")
            .and_then(serde_json::Value::as_str)
            != Some("structural-native-workbench-failure.v1")
        || value.get("code").and_then(serde_json::Value::as_str)
            != Some("workbench_profile_unsupported")
        || value
            .get("detail")
            .and_then(serde_json::Value::as_str)
            .map_or(true, str::is_empty)
        || compact_operator_json(&value)? != canonical
    {
        return Err(DistributionError::new(
            "rootfs_reaction_view_failure_invalid",
            "wrong-profile reaction failure does not match the exact fail-closed contract",
        ));
    }
    Ok(())
}

fn inspect_rootfs_reaction_view_surface(
    workspace: &Path,
    model_ir_linear_root: &Path,
    mgt_model_ir_linear_root: &Path,
    request: &RootfsIsolationProbeRequest<'_>,
) -> Result<ReactionViewSurfaceSummary, DistributionError> {
    let model = inspect_reaction_view_probe(
        workspace,
        &ReactionViewProbe {
            label: "ModelIR linear",
            workbench_root: model_ir_linear_root,
            session_before: request.model_ir_linear_workbench_session_before_reaction_view,
            en_us_first: request.model_ir_linear_reaction_view_en_us_first,
            en_us_second: request.model_ir_linear_reaction_view_en_us_second,
            ko_kr_first: request.model_ir_linear_reaction_view_ko_kr_first,
            ko_kr_second: request.model_ir_linear_reaction_view_ko_kr_second,
            window: Some(request.model_ir_linear_reaction_view_window),
        },
    )?;
    let mgt = inspect_reaction_view_probe(
        workspace,
        &ReactionViewProbe {
            label: "normalized-MGT linear",
            workbench_root: mgt_model_ir_linear_root,
            session_before: request.mgt_model_ir_linear_workbench_session_before_reaction_view,
            en_us_first: request.mgt_model_ir_linear_reaction_view_en_us_first,
            en_us_second: request.mgt_model_ir_linear_reaction_view_en_us_second,
            ko_kr_first: request.mgt_model_ir_linear_reaction_view_ko_kr_first,
            ko_kr_second: request.mgt_model_ir_linear_reaction_view_ko_kr_second,
            window: None,
        },
    )?;
    inspect_reaction_view_wrong_profile_failure(
        workspace,
        request.workbench_reaction_view_wrong_profile_failure,
    )?;
    if model.0 == mgt.0 {
        return Err(DistributionError::new(
            "rootfs_reaction_view_profile_collision",
            "strict-ModelIR and normalized-MGT reaction views have the same identity",
        ));
    }
    Ok(ReactionViewSurfaceSummary {
        model_en_us: model.0,
        model_ko_kr: model.1,
        model_window: model.2.expect("ModelIR reaction window is required"),
        mgt_en_us: mgt.0,
        mgt_ko_kr: mgt.1,
    })
}

fn validate_nodal_displacement_view_rows(
    text: &str,
    expected_start: usize,
    expected_count: usize,
    label: &str,
) -> Result<(), DistributionError> {
    let mut row_count = 0usize;
    for line in text.lines() {
        let line_bytes = line.as_bytes();
        if line_bytes.len() < 7
            || !line_bytes[..6].iter().all(u8::is_ascii_digit)
            || line_bytes[6] != b'\t'
        {
            continue;
        }
        let fields = line.split('\t').collect::<Vec<_>>();
        let expected_row = expected_start + row_count;
        let valid_components = fields.get(3..9).is_some_and(|values| {
            values
                .iter()
                .all(|value| value.parse::<f64>().is_ok_and(f64::is_finite))
        });
        if fields.len() != 9
            || fields[0] != format!("{expected_row:06}")
            || fields[1].is_empty()
            || fields[2] != format!("{:010}", expected_row - 1)
            || !valid_components
        {
            return Err(DistributionError::new(
                "rootfs_nodal_displacement_view_row_invalid",
                format!("{label} has an invalid nodal displacement row"),
            ));
        }
        row_count += 1;
    }
    if row_count != expected_count {
        return Err(DistributionError::new(
            "rootfs_nodal_displacement_view_row_invalid",
            format!("{label} has {row_count} rows instead of {expected_count}"),
        ));
    }
    Ok(())
}

#[allow(clippy::too_many_arguments)]
fn inspect_nodal_displacement_view_artifact(
    workspace: &Path,
    path: &Path,
    locale: &str,
    expected_start: usize,
    expected_count: usize,
    expected_total: usize,
    label: &str,
) -> Result<NodalDisplacementViewArtifact, DistributionError> {
    let bytes = read_direct_workspace_file(workspace, path, label)?;
    if bytes.contains(&0x1b) {
        return Err(DistributionError::new(
            "rootfs_nodal_displacement_view_unsafe",
            format!("{label} contains an ANSI escape byte"),
        ));
    }
    let text = std::str::from_utf8(&bytes).map_err(|_| {
        DistributionError::new(
            "rootfs_nodal_displacement_view_invalid",
            format!("{label} must be UTF-8"),
        )
    })?;
    let without_final_newline = text.strip_suffix('\n').ok_or_else(|| {
        DistributionError::new(
            "rootfs_nodal_displacement_view_noncanonical",
            format!("{label} must end with one newline"),
        )
    })?;
    let final_line_start = without_final_newline
        .rfind('\n')
        .map_or(0, |position| position + 1);
    let final_line = &without_final_newline[final_line_start..];
    let hash_label = match locale {
        "en-US" => "View hash: ",
        "ko-KR" => "보기 해시: ",
        _ => {
            return Err(DistributionError::new(
                "rootfs_nodal_displacement_view_invalid",
                "nodal displacement view locale contract is unsupported",
            ));
        }
    };
    let declared_hash = final_line.strip_prefix(hash_label).ok_or_else(|| {
        DistributionError::new(
            "rootfs_nodal_displacement_view_hash_missing",
            format!("{label} has no terminal self-hash"),
        )
    })?;
    validate_sha256_identity(declared_hash, "rootfs nodal displacement view self-hash")?;
    if declared_hash != sha256_identity(&bytes[..final_line_start]) {
        return Err(DistributionError::new(
            "rootfs_nodal_displacement_view_hash_mismatch",
            format!("{label} self-hash does not verify"),
        ));
    }

    let (schema_line, locale_line, display_line, unit_line, boundary_token) = if locale == "en-US" {
        (
                "Schema: structural-native-workbench-model-ir-linear-nodal-displacement-view.v1",
                "Locale: en-US",
                format!(
                    "Displayed nodes: {}-{} of {expected_total}",
                    expected_start,
                    expected_start + expected_count - 1
                ),
                "Component units: UX/UY/UZ=m; RX/RY/RZ=rad",
                "not a deformed-shape, stress, contour, modal, serviceability, support-design, or engineering verdict",
            )
    } else {
        (
            "스키마: structural-native-workbench-model-ir-linear-nodal-displacement-view.v1",
            "로케일: ko-KR",
            format!(
                "표시 노드: {}-{} / {expected_total}",
                expected_start,
                expected_start + expected_count - 1
            ),
            "성분 단위: UX/UY/UZ=m; RX/RY/RZ=rad",
            "변형 형상, 응력, 등고선, 모드, 사용성, 지점 설계 또는 공학적 판정을 의미하지 않습니다",
        )
    };
    if !text.lines().any(|line| line == schema_line)
        || !text.lines().any(|line| line == locale_line)
        || !text.lines().any(|line| line == display_line)
        || !text.lines().any(|line| line == unit_line)
        || !text.contains(boundary_token)
        || !text.contains("fallback 0")
    {
        return Err(DistributionError::new(
            "rootfs_nodal_displacement_view_contract_invalid",
            format!("{label} does not expose the exact bounded displacement-view contract"),
        ));
    }
    validate_nodal_displacement_view_rows(text, expected_start, expected_count, label)?;
    Ok(NodalDisplacementViewArtifact {
        sha256: sha256_identity(&bytes),
        bytes,
    })
}

fn inspect_nodal_displacement_view_probe(
    workspace: &Path,
    probe: &NodalDisplacementViewProbe<'_>,
) -> Result<(String, String, Option<String>), DistributionError> {
    let session_before = read_direct_workspace_file(
        workspace,
        probe.session_before,
        &format!("{} pre-displacement-view session", probe.label),
    )?;
    let session_after = read_bounded_regular_file(
        &probe.workbench_root.join("workbench-session.json"),
        MAX_MANIFEST_BYTES,
    )?;
    if session_before != session_after {
        return Err(DistributionError::new(
            "rootfs_nodal_displacement_view_session_mutated",
            format!(
                "{} nodal displacement view mutated its session",
                probe.label
            ),
        ));
    }
    let inspect = |path, locale, start, count, suffix| {
        inspect_nodal_displacement_view_artifact(
            workspace,
            path,
            locale,
            start,
            count,
            2,
            &format!("{} {locale} {suffix} nodal displacement view", probe.label),
        )
    };
    let en_us_first = inspect(probe.en_us_first, "en-US", 1, 2, "first")?;
    let en_us_second = inspect(probe.en_us_second, "en-US", 1, 2, "second")?;
    let ko_kr_first = inspect(probe.ko_kr_first, "ko-KR", 1, 2, "first")?;
    let ko_kr_second = inspect(probe.ko_kr_second, "ko-KR", 1, 2, "second")?;
    if en_us_first.bytes != en_us_second.bytes || ko_kr_first.bytes != ko_kr_second.bytes {
        return Err(DistributionError::new(
            "rootfs_nodal_displacement_view_determinism_failed",
            format!("{} repeated nodal displacement views differ", probe.label),
        ));
    }
    if en_us_first.sha256 == ko_kr_first.sha256 {
        return Err(DistributionError::new(
            "rootfs_nodal_displacement_view_locale_collision",
            format!("{} displacement view locales collide", probe.label),
        ));
    }
    let window = probe
        .window
        .map(|path| inspect(path, "en-US", 2, 1, "bounded"))
        .transpose()?;
    if window
        .as_ref()
        .is_some_and(|artifact| artifact.sha256 == en_us_first.sha256)
    {
        return Err(DistributionError::new(
            "rootfs_nodal_displacement_view_window_collision",
            format!(
                "{} bounded displacement view equals its full view",
                probe.label
            ),
        ));
    }
    Ok((
        en_us_first.sha256,
        ko_kr_first.sha256,
        window.map(|artifact| artifact.sha256),
    ))
}

fn inspect_nodal_displacement_view_wrong_profile_failure(
    workspace: &Path,
    path: &Path,
) -> Result<(), DistributionError> {
    let bytes = read_direct_workspace_file(workspace, path, "wrong-profile displacement failure")?;
    let canonical = bytes.strip_suffix(b"\n").ok_or_else(|| {
        DistributionError::new(
            "rootfs_nodal_displacement_view_failure_noncanonical",
            "wrong-profile displacement failure must be one JSON line",
        )
    })?;
    let value = structural_contracts::model_ir::decode_json_strict(canonical).map_err(|error| {
        DistributionError::new(
            "rootfs_nodal_displacement_view_failure_invalid",
            format!("wrong-profile displacement failure is invalid JSON: {error}"),
        )
    })?;
    let object = value.as_object().ok_or_else(|| {
        DistributionError::new(
            "rootfs_nodal_displacement_view_failure_invalid",
            "wrong-profile displacement failure must be an object",
        )
    })?;
    let actual = object.keys().map(String::as_str).collect::<BTreeSet<_>>();
    let expected = ["code", "detail", "schema_version"]
        .into_iter()
        .collect::<BTreeSet<_>>();
    if actual != expected
        || value
            .get("schema_version")
            .and_then(serde_json::Value::as_str)
            != Some("structural-native-workbench-failure.v1")
        || value.get("code").and_then(serde_json::Value::as_str)
            != Some("workbench_profile_unsupported")
        || value
            .get("detail")
            .and_then(serde_json::Value::as_str)
            .map_or(true, str::is_empty)
        || compact_operator_json(&value)? != canonical
    {
        return Err(DistributionError::new(
            "rootfs_nodal_displacement_view_failure_invalid",
            "wrong-profile displacement failure does not match the fail-closed contract",
        ));
    }
    Ok(())
}

fn inspect_rootfs_nodal_displacement_view_surface(
    workspace: &Path,
    model_ir_linear_root: &Path,
    mgt_model_ir_linear_root: &Path,
    request: &RootfsIsolationProbeRequest<'_>,
) -> Result<NodalDisplacementViewSurfaceSummary, DistributionError> {
    let model = inspect_nodal_displacement_view_probe(
        workspace,
        &NodalDisplacementViewProbe {
            label: "ModelIR linear",
            workbench_root: model_ir_linear_root,
            session_before: request.model_ir_linear_workbench_session_before_reaction_view,
            en_us_first: request.model_ir_linear_nodal_displacement_view_en_us_first,
            en_us_second: request.model_ir_linear_nodal_displacement_view_en_us_second,
            ko_kr_first: request.model_ir_linear_nodal_displacement_view_ko_kr_first,
            ko_kr_second: request.model_ir_linear_nodal_displacement_view_ko_kr_second,
            window: Some(request.model_ir_linear_nodal_displacement_view_window),
        },
    )?;
    let mgt = inspect_nodal_displacement_view_probe(
        workspace,
        &NodalDisplacementViewProbe {
            label: "normalized-MGT linear",
            workbench_root: mgt_model_ir_linear_root,
            session_before: request.mgt_model_ir_linear_workbench_session_before_reaction_view,
            en_us_first: request.mgt_model_ir_linear_nodal_displacement_view_en_us_first,
            en_us_second: request.mgt_model_ir_linear_nodal_displacement_view_en_us_second,
            ko_kr_first: request.mgt_model_ir_linear_nodal_displacement_view_ko_kr_first,
            ko_kr_second: request.mgt_model_ir_linear_nodal_displacement_view_ko_kr_second,
            window: None,
        },
    )?;
    inspect_nodal_displacement_view_wrong_profile_failure(
        workspace,
        request.workbench_nodal_displacement_view_wrong_profile_failure,
    )?;
    if model.0 == mgt.0 {
        return Err(DistributionError::new(
            "rootfs_nodal_displacement_view_profile_collision",
            "strict-ModelIR and normalized-MGT nodal displacement views collide",
        ));
    }
    Ok(NodalDisplacementViewSurfaceSummary {
        model_en_us: model.0,
        model_ko_kr: model.1,
        model_window: model.2.expect("ModelIR displacement window is required"),
        mgt_en_us: mgt.0,
        mgt_ko_kr: mgt.1,
    })
}

fn contains_nonfinite_number_token(text: &str) -> bool {
    text.split(|character: char| {
        !(character.is_ascii_alphanumeric() || matches!(character, '+' | '-' | '.' | '_'))
    })
    .any(|token| {
        token.eq_ignore_ascii_case("nan")
            || token.eq_ignore_ascii_case("+nan")
            || token.eq_ignore_ascii_case("-nan")
            || token.eq_ignore_ascii_case("inf")
            || token.eq_ignore_ascii_case("+inf")
            || token.eq_ignore_ascii_case("-inf")
            || token.eq_ignore_ascii_case("infinity")
            || token.eq_ignore_ascii_case("+infinity")
            || token.eq_ignore_ascii_case("-infinity")
    })
}

#[allow(clippy::too_many_lines)] // Keep the independent fail-closed artifact checks auditable.
fn inspect_linear_deformed_view_artifact(
    workspace: &Path,
    path: &Path,
    locale: &str,
    projection: &str,
    label: &str,
) -> Result<LinearDeformedViewArtifact, DistributionError> {
    let bytes = read_direct_workspace_file(workspace, path, label)?;
    if bytes.contains(&0x1b) {
        return Err(DistributionError::new(
            "rootfs_linear_deformed_view_unsafe",
            format!("{label} contains an ANSI escape byte"),
        ));
    }
    let text = std::str::from_utf8(&bytes).map_err(|_| {
        DistributionError::new(
            "rootfs_linear_deformed_view_invalid",
            format!("{label} must be UTF-8"),
        )
    })?;
    let unsigned = text.strip_suffix('\n').ok_or_else(|| {
        DistributionError::new(
            "rootfs_linear_deformed_view_noncanonical",
            format!("{label} must end with one newline"),
        )
    })?;
    let final_line_start = unsigned.rfind('\n').map_or(0, |position| position + 1);
    let final_line = &unsigned[final_line_start..];
    let (hash_label, required_lines) = match locale {
        "en-US" => (
            "View hash: ",
            [
                "Schema: structural-native-workbench-model-ir-linear-deformed-view.v1",
                "Locale: en-US",
                "Authority: bounded candidate",
                "Profile: model_ir_linear_cpu_v1",
                "Viewport: 73x25 cells",
                "Selected state: 1 of 1 (terminal linear static)",
                "Visual magnification: 1.00000000000000000e3",
                "Applied components: UX/UY/UZ translational displacement in m",
                "Rotation treatment: RX/RY/RZ are reported in rad but are not applied to centerline coordinates",
                "Inventory: nodes=2 elements=1",
            ],
        ),
        "ko-KR" => (
            "보기 해시: ",
            [
                "스키마: structural-native-workbench-model-ir-linear-deformed-view.v1",
                "로케일: ko-KR",
                "권한: bounded candidate",
                "프로파일: model_ir_linear_cpu_v1",
                "뷰포트: 73x25 cells",
                "선택 상태: 1 of 1 (terminal linear static)",
                "시각 확대 배율: 1.00000000000000000e3",
                "적용 성분: UX/UY/UZ translational displacement in m",
                "회전 처리: RX/RY/RZ are reported in rad but are not applied to centerline coordinates",
                "재고: nodes=2 elements=1",
            ],
        ),
        _ => {
            return Err(DistributionError::new(
                "rootfs_linear_deformed_view_invalid",
                "linear deformed-view locale contract is unsupported",
            ));
        }
    };
    let declared_hash = final_line.strip_prefix(hash_label).ok_or_else(|| {
        DistributionError::new(
            "rootfs_linear_deformed_view_hash_missing",
            format!("{label} has no terminal self-hash"),
        )
    })?;
    validate_sha256_identity(declared_hash, "rootfs linear deformed-view self-hash")?;
    if declared_hash != sha256_identity(&bytes[..final_line_start]) {
        return Err(DistributionError::new(
            "rootfs_linear_deformed_view_hash_mismatch",
            format!("{label} self-hash does not verify"),
        ));
    }
    if required_lines
        .iter()
        .any(|required| !text.lines().any(|line| line == *required))
        || !text.lines().any(|line| {
            line == format!("Projection: {projection}")
                || line == format!("투영: {projection}")
        })
        || !text.contains("fallback 0")
        || !text.contains("H2D 0 / D2H 0 / sync 0")
        || !text.contains("bounded_read_only_modelir_linear_two_node_centerline_original_and_magnified_translational_displacement_projection_not_member_curvature_rigid_offset_rotation_stress_contour_modal_serviceability_support_design_engineering_acceptance_or_design_code_compliance")
        || contains_nonfinite_number_token(text)
    {
        return Err(DistributionError::new(
            "rootfs_linear_deformed_view_contract_invalid",
            format!("{label} does not expose the exact bounded linear deformed-view contract"),
        ));
    }

    let border = format!("+{}+", "-".repeat(73));
    let border_count = text.lines().filter(|line| *line == border).count();
    let canvas_rows = text
        .lines()
        .filter(|line| line.len() == 75 && line.starts_with('|') && line.ends_with('|'))
        .count();
    let node_rows = text
        .lines()
        .filter(|line| {
            line.starts_with("  00000")
                && line.contains(" original_xyz_m=[")
                && line.contains(" translation_m=[")
                && line.contains(" rotation_rad=[")
                && line.contains(" magnified_xyz_m=[")
                && line.contains(" original_cell=[")
                && line.contains(" deformed_cell=[")
        })
        .count();
    let element_rows = text
        .lines()
        .filter(|line| {
            line.starts_with("  000001 ")
                && line.contains(" element_index=0000000000 ")
                && (line.contains(" frame_3d ") || line.contains(" truss_3d "))
                && line.contains(" -> ")
        })
        .count();
    if border_count != 2 || canvas_rows != 25 || node_rows != 2 || element_rows != 1 {
        return Err(DistributionError::new(
            "rootfs_linear_deformed_view_geometry_invalid",
            format!("{label} has an invalid bounded canvas or topology inventory"),
        ));
    }
    Ok(LinearDeformedViewArtifact {
        sha256: sha256_identity(&bytes),
        bytes,
    })
}

fn inspect_linear_deformed_view_probe(
    workspace: &Path,
    probe: &LinearDeformedViewProbe<'_>,
) -> Result<(String, String, Option<String>), DistributionError> {
    let session_before = read_direct_workspace_file(
        workspace,
        probe.session_before,
        &format!("{} pre-deformed-view session", probe.label),
    )?;
    let session_after = read_bounded_regular_file(
        &probe.workbench_root.join("workbench-session.json"),
        MAX_MANIFEST_BYTES,
    )?;
    if session_before != session_after {
        return Err(DistributionError::new(
            "rootfs_linear_deformed_view_session_mutated",
            format!("{} linear deformed view mutated its session", probe.label),
        ));
    }
    let inspect = |path, locale, projection, suffix| {
        inspect_linear_deformed_view_artifact(
            workspace,
            path,
            locale,
            projection,
            &format!("{} {locale} {suffix} linear deformed view", probe.label),
        )
    };
    let en_us_first = inspect(probe.en_us_first, "en-US", probe.projection, "first")?;
    let en_us_second = inspect(probe.en_us_second, "en-US", probe.projection, "second")?;
    let ko_kr_first = inspect(probe.ko_kr_first, "ko-KR", probe.projection, "first")?;
    let ko_kr_second = inspect(probe.ko_kr_second, "ko-KR", probe.projection, "second")?;
    if en_us_first.bytes != en_us_second.bytes || ko_kr_first.bytes != ko_kr_second.bytes {
        return Err(DistributionError::new(
            "rootfs_linear_deformed_view_determinism_failed",
            format!("{} repeated linear deformed views differ", probe.label),
        ));
    }
    if en_us_first.sha256 == ko_kr_first.sha256 {
        return Err(DistributionError::new(
            "rootfs_linear_deformed_view_locale_collision",
            format!("{} linear deformed-view locales collide", probe.label),
        ));
    }
    let alternate = probe
        .alternate_projection
        .map(|path| inspect(path, "en-US", "xz", "alternate projection"))
        .transpose()?;
    if alternate
        .as_ref()
        .is_some_and(|artifact| artifact.sha256 == en_us_first.sha256)
    {
        return Err(DistributionError::new(
            "rootfs_linear_deformed_view_projection_collision",
            format!(
                "{} alternate projection equals its primary view",
                probe.label
            ),
        ));
    }
    Ok((
        en_us_first.sha256,
        ko_kr_first.sha256,
        alternate.map(|artifact| artifact.sha256),
    ))
}

fn inspect_linear_deformed_view_invalid_step_failure(
    workspace: &Path,
    path: &Path,
) -> Result<(), DistributionError> {
    let bytes = read_direct_workspace_file(workspace, path, "invalid-step deformed-view failure")?;
    let canonical = bytes.strip_suffix(b"\n").ok_or_else(|| {
        DistributionError::new(
            "rootfs_linear_deformed_view_failure_noncanonical",
            "invalid-step deformed-view failure must be one JSON line",
        )
    })?;
    let value = structural_contracts::model_ir::decode_json_strict(canonical).map_err(|error| {
        DistributionError::new(
            "rootfs_linear_deformed_view_failure_invalid",
            format!("invalid-step deformed-view failure is invalid JSON: {error}"),
        )
    })?;
    let object = value.as_object().ok_or_else(|| {
        DistributionError::new(
            "rootfs_linear_deformed_view_failure_invalid",
            "invalid-step deformed-view failure must be an object",
        )
    })?;
    let actual = object.keys().map(String::as_str).collect::<BTreeSet<_>>();
    let expected = ["code", "detail", "schema_version"]
        .into_iter()
        .collect::<BTreeSet<_>>();
    if actual != expected
        || value
            .get("schema_version")
            .and_then(serde_json::Value::as_str)
            != Some("structural-native-workbench-failure.v1")
        || value.get("code").and_then(serde_json::Value::as_str)
            != Some("workbench_deformed_view_step_invalid")
        || value
            .get("detail")
            .and_then(serde_json::Value::as_str)
            .map_or(true, str::is_empty)
        || compact_operator_json(&value)? != canonical
    {
        return Err(DistributionError::new(
            "rootfs_linear_deformed_view_failure_invalid",
            "invalid-step deformed-view failure does not match the fail-closed contract",
        ));
    }
    Ok(())
}

fn inspect_rootfs_linear_deformed_view_surface(
    workspace: &Path,
    model_ir_linear_root: &Path,
    mgt_model_ir_linear_root: &Path,
    request: &RootfsIsolationProbeRequest<'_>,
) -> Result<LinearDeformedViewSurfaceSummary, DistributionError> {
    let model = inspect_linear_deformed_view_probe(
        workspace,
        &LinearDeformedViewProbe {
            label: "ModelIR linear",
            workbench_root: model_ir_linear_root,
            session_before: request.model_ir_linear_workbench_session_before_reaction_view,
            projection: "xy",
            en_us_first: request.model_ir_linear_deformed_view_en_us_first,
            en_us_second: request.model_ir_linear_deformed_view_en_us_second,
            ko_kr_first: request.model_ir_linear_deformed_view_ko_kr_first,
            ko_kr_second: request.model_ir_linear_deformed_view_ko_kr_second,
            alternate_projection: Some(request.model_ir_linear_deformed_view_projection),
        },
    )?;
    let mgt = inspect_linear_deformed_view_probe(
        workspace,
        &LinearDeformedViewProbe {
            label: "normalized-MGT linear",
            workbench_root: mgt_model_ir_linear_root,
            session_before: request.mgt_model_ir_linear_workbench_session_before_reaction_view,
            projection: "xz",
            en_us_first: request.mgt_model_ir_linear_deformed_view_en_us_first,
            en_us_second: request.mgt_model_ir_linear_deformed_view_en_us_second,
            ko_kr_first: request.mgt_model_ir_linear_deformed_view_ko_kr_first,
            ko_kr_second: request.mgt_model_ir_linear_deformed_view_ko_kr_second,
            alternate_projection: None,
        },
    )?;
    inspect_linear_deformed_view_invalid_step_failure(
        workspace,
        request.workbench_linear_deformed_view_invalid_step_failure,
    )?;
    let model_projection = model.2.expect("ModelIR alternate projection is required");
    let identities = [&model.0, &model.1, &model_projection, &mgt.0, &mgt.1]
        .into_iter()
        .collect::<BTreeSet<_>>();
    if identities.len() != 5 {
        return Err(DistributionError::new(
            "rootfs_linear_deformed_view_profile_collision",
            "linear deformed-view locale, projection, or profile identities collide",
        ));
    }
    Ok(LinearDeformedViewSurfaceSummary {
        model_en_us: model.0,
        model_ko_kr: model.1,
        model_projection,
        mgt_en_us: mgt.0,
        mgt_ko_kr: mgt.1,
    })
}

#[allow(clippy::too_many_lines)] // Keep independent fail-closed artifact checks auditable.
fn inspect_linear_element_recovery_view_artifact(
    workspace: &Path,
    path: &Path,
    locale: &str,
    label: &str,
) -> Result<LinearElementRecoveryViewArtifact, DistributionError> {
    let bytes = read_direct_workspace_file(workspace, path, label)?;
    if bytes.contains(&0x1b) {
        return Err(DistributionError::new(
            "rootfs_linear_element_recovery_view_unsafe",
            format!("{label} contains an ANSI escape byte"),
        ));
    }
    let text = std::str::from_utf8(&bytes).map_err(|_| {
        DistributionError::new(
            "rootfs_linear_element_recovery_view_invalid",
            format!("{label} must be UTF-8"),
        )
    })?;
    let unsigned = text.strip_suffix('\n').ok_or_else(|| {
        DistributionError::new(
            "rootfs_linear_element_recovery_view_noncanonical",
            format!("{label} must end with one newline"),
        )
    })?;
    let final_line_start = unsigned.rfind('\n').map_or(0, |position| position + 1);
    let final_line = &unsigned[final_line_start..];
    let (hash_label, required_lines, identity_labels) = match locale {
        "en-US" => (
            "View hash: ",
            [
                "Schema: structural-native-workbench-model-ir-linear-element-recovery-view.v1",
                "Locale: en-US",
                "Authority: bounded candidate",
                "Profile: model_ir_linear_cpu_v1",
                "Selected state: 1 of 1 (terminal linear static)",
                "Elements: 1",
                "Displayed elements: 1-1 of 1",
                "Frame3d components: i_FX/i_FY/i_FZ/j_FX/j_FY/j_FZ=N; i_MX/i_MY/i_MZ/j_MX/j_MY/j_MZ=N*m",
                "Truss3d components: axial_strain=1; axial_stress=Pa; axial_force=N",
                "Coordinate frames: frame3d=element_local; truss3d=element_axis",
            ],
            [
                "Model content hash",
                "Model semantic hash",
                "Model provenance hash",
                "Source result hash",
                "Recovery hash",
                "Analysis request hash",
                "Assembly hash",
                "Sparse request hash",
                "Sparse model hash",
                "State hash",
                "Execution hash",
                "Checkpoint hash",
            ],
        ),
        "ko-KR" => (
            "보기 해시: ",
            [
                "스키마: structural-native-workbench-model-ir-linear-element-recovery-view.v1",
                "로케일: ko-KR",
                "권한: 제한된 후보",
                "프로파일: model_ir_linear_cpu_v1",
                "선택 상태: 1 of 1 (terminal linear static)",
                "요소: 1",
                "표시 요소: 1-1 of 1",
                "Frame3d 성분: i_FX/i_FY/i_FZ/j_FX/j_FY/j_FZ=N; i_MX/i_MY/i_MZ/j_MX/j_MY/j_MZ=N*m",
                "Truss3d 성분: axial_strain=1; axial_stress=Pa; axial_force=N",
                "좌표계: frame3d=element_local; truss3d=element_axis",
            ],
            [
                "모델 콘텐츠 해시",
                "모델 의미 해시",
                "모델 출처 해시",
                "소스 결과 해시",
                "복원 해시",
                "분석 요청 해시",
                "조립 해시",
                "희소 요청 해시",
                "희소 모델 해시",
                "상태 해시",
                "실행 해시",
                "체크포인트 해시",
            ],
        ),
        _ => {
            return Err(DistributionError::new(
                "rootfs_linear_element_recovery_view_invalid",
                "element recovery view locale contract is unsupported",
            ));
        }
    };
    let declared_hash = final_line.strip_prefix(hash_label).ok_or_else(|| {
        DistributionError::new(
            "rootfs_linear_element_recovery_view_hash_missing",
            format!("{label} has no terminal self-hash"),
        )
    })?;
    validate_sha256_identity(
        declared_hash,
        "rootfs linear element recovery view self-hash",
    )?;
    if declared_hash != sha256_identity(&bytes[..final_line_start]) {
        return Err(DistributionError::new(
            "rootfs_linear_element_recovery_view_hash_mismatch",
            format!("{label} self-hash does not verify"),
        ));
    }
    if required_lines
        .iter()
        .any(|required| !text.lines().any(|line| line == *required))
        || !text.contains("fallback 0")
        || !text.contains("H2D 0 / D2H 0 / sync 0")
        || !text.contains("bounded_read_only_modelir_linear_frame3d_local_end_force_and_truss3d_axis_strain_stress_force_projection_not_shell_general_stress_contour_design_utilization_support_design_engineering_acceptance_or_code_compliance")
        || contains_nonfinite_number_token(text)
    {
        return Err(DistributionError::new(
            "rootfs_linear_element_recovery_view_contract_invalid",
            format!("{label} does not expose the exact bounded element recovery contract"),
        ));
    }
    for identity_label in identity_labels {
        let prefix = format!("{identity_label}: ");
        let identity = text
            .lines()
            .find_map(|line| line.strip_prefix(&prefix))
            .ok_or_else(|| {
                DistributionError::new(
                    "rootfs_linear_element_recovery_view_identity_missing",
                    format!("{label} omits {identity_label}"),
                )
            })?;
        validate_sha256_identity(identity, "rootfs element recovery bound identity")?;
    }
    let rows = text
        .lines()
        .filter(|line| {
            let bytes = line.as_bytes();
            bytes.len() >= 7 && bytes[..6].iter().all(u8::is_ascii_digit) && bytes[6] == b'\t'
        })
        .collect::<Vec<_>>();
    if rows.len() != 1 {
        return Err(DistributionError::new(
            "rootfs_linear_element_recovery_view_row_invalid",
            format!("{label} must contain exactly one bounded element row"),
        ));
    }
    let fields = rows[0].split('\t').collect::<Vec<_>>();
    let component_names = [
        "i_FX_N", "i_FY_N", "i_FZ_N", "i_MX_N_m", "i_MY_N_m", "i_MZ_N_m", "j_FX_N", "j_FY_N",
        "j_FZ_N", "j_MX_N_m", "j_MY_N_m", "j_MZ_N_m",
    ];
    let component_values = fields
        .get(6)
        .map(|value| value.split(';').collect::<Vec<_>>())
        .unwrap_or_default();
    let components_valid = component_values.len() == component_names.len()
        && component_values
            .iter()
            .zip(component_names)
            .all(|(component, expected_name)| {
                component.split_once('=').is_some_and(|(name, value)| {
                    name == expected_name && value.parse::<f64>().is_ok_and(f64::is_finite)
                })
            });
    if fields.len() != 7
        || fields[0] != "000001"
        || fields[1].is_empty()
        || fields[2] != "0000000000"
        || fields[3] != "frame_3d"
        || !fields[4].contains("->")
        || fields[5] != "element_local"
        || !components_valid
    {
        return Err(DistributionError::new(
            "rootfs_linear_element_recovery_view_row_invalid",
            format!("{label} has an invalid Frame3D recovery row"),
        ));
    }
    Ok(LinearElementRecoveryViewArtifact {
        sha256: sha256_identity(&bytes),
        bytes,
    })
}

fn inspect_linear_element_recovery_view_probe(
    workspace: &Path,
    probe: &LinearElementRecoveryViewProbe<'_>,
) -> Result<(String, String), DistributionError> {
    let session_before = read_direct_workspace_file(
        workspace,
        probe.session_before,
        &format!("{} pre-element-recovery-view session", probe.label),
    )?;
    let session_after = read_bounded_regular_file(
        &probe.workbench_root.join("workbench-session.json"),
        MAX_MANIFEST_BYTES,
    )?;
    if session_before != session_after {
        return Err(DistributionError::new(
            "rootfs_linear_element_recovery_view_session_mutated",
            format!("{} element recovery view mutated its session", probe.label),
        ));
    }
    let inspect = |path, locale, suffix| {
        inspect_linear_element_recovery_view_artifact(
            workspace,
            path,
            locale,
            &format!("{} {locale} {suffix} element recovery view", probe.label),
        )
    };
    let en_us_first = inspect(probe.en_us_first, "en-US", "first")?;
    let en_us_second = inspect(probe.en_us_second, "en-US", "second")?;
    let ko_kr_first = inspect(probe.ko_kr_first, "ko-KR", "first")?;
    let ko_kr_second = inspect(probe.ko_kr_second, "ko-KR", "second")?;
    if en_us_first.bytes != en_us_second.bytes || ko_kr_first.bytes != ko_kr_second.bytes {
        return Err(DistributionError::new(
            "rootfs_linear_element_recovery_view_determinism_failed",
            format!("{} repeated element recovery views differ", probe.label),
        ));
    }
    if en_us_first.sha256 == ko_kr_first.sha256 {
        return Err(DistributionError::new(
            "rootfs_linear_element_recovery_view_locale_collision",
            format!("{} element recovery view locales collide", probe.label),
        ));
    }
    Ok((en_us_first.sha256, ko_kr_first.sha256))
}

fn inspect_linear_element_recovery_view_invalid_window_failure(
    workspace: &Path,
    path: &Path,
) -> Result<(), DistributionError> {
    let bytes =
        read_direct_workspace_file(workspace, path, "invalid-window element recovery failure")?;
    let canonical = bytes.strip_suffix(b"\n").ok_or_else(|| {
        DistributionError::new(
            "rootfs_linear_element_recovery_view_failure_noncanonical",
            "invalid-window element recovery failure must be one JSON line",
        )
    })?;
    let value = structural_contracts::model_ir::decode_json_strict(canonical).map_err(|error| {
        DistributionError::new(
            "rootfs_linear_element_recovery_view_failure_invalid",
            format!("invalid-window element recovery failure is invalid JSON: {error}"),
        )
    })?;
    let object = value.as_object().ok_or_else(|| {
        DistributionError::new(
            "rootfs_linear_element_recovery_view_failure_invalid",
            "invalid-window element recovery failure must be an object",
        )
    })?;
    let actual = object.keys().map(String::as_str).collect::<BTreeSet<_>>();
    let expected = ["code", "detail", "schema_version"]
        .into_iter()
        .collect::<BTreeSet<_>>();
    if actual != expected
        || value
            .get("schema_version")
            .and_then(serde_json::Value::as_str)
            != Some("structural-native-workbench-failure.v1")
        || value.get("code").and_then(serde_json::Value::as_str)
            != Some("workbench_element_recovery_view_window_invalid")
        || value
            .get("detail")
            .and_then(serde_json::Value::as_str)
            .map_or(true, str::is_empty)
        || compact_operator_json(&value)? != canonical
    {
        return Err(DistributionError::new(
            "rootfs_linear_element_recovery_view_failure_invalid",
            "invalid-window element recovery failure does not match the fail-closed contract",
        ));
    }
    Ok(())
}

fn inspect_rootfs_linear_element_recovery_view_surface(
    workspace: &Path,
    model_ir_linear_root: &Path,
    mgt_model_ir_linear_root: &Path,
    request: &RootfsIsolationProbeRequest<'_>,
) -> Result<LinearElementRecoveryViewSurfaceSummary, DistributionError> {
    let model = inspect_linear_element_recovery_view_probe(
        workspace,
        &LinearElementRecoveryViewProbe {
            label: "ModelIR linear",
            workbench_root: model_ir_linear_root,
            session_before: request.model_ir_linear_workbench_session_before_reaction_view,
            en_us_first: request.model_ir_linear_element_recovery_view_en_us_first,
            en_us_second: request.model_ir_linear_element_recovery_view_en_us_second,
            ko_kr_first: request.model_ir_linear_element_recovery_view_ko_kr_first,
            ko_kr_second: request.model_ir_linear_element_recovery_view_ko_kr_second,
        },
    )?;
    let mgt = inspect_linear_element_recovery_view_probe(
        workspace,
        &LinearElementRecoveryViewProbe {
            label: "normalized-MGT linear",
            workbench_root: mgt_model_ir_linear_root,
            session_before: request.mgt_model_ir_linear_workbench_session_before_reaction_view,
            en_us_first: request.mgt_model_ir_linear_element_recovery_view_en_us_first,
            en_us_second: request.mgt_model_ir_linear_element_recovery_view_en_us_second,
            ko_kr_first: request.mgt_model_ir_linear_element_recovery_view_ko_kr_first,
            ko_kr_second: request.mgt_model_ir_linear_element_recovery_view_ko_kr_second,
        },
    )?;
    inspect_linear_element_recovery_view_invalid_window_failure(
        workspace,
        request.workbench_linear_element_recovery_view_invalid_window_failure,
    )?;
    let identities = [&model.0, &model.1, &mgt.0, &mgt.1]
        .into_iter()
        .collect::<BTreeSet<_>>();
    if identities.len() != 4 {
        return Err(DistributionError::new(
            "rootfs_linear_element_recovery_view_profile_collision",
            "linear element recovery view locale or profile identities collide",
        ));
    }
    Ok(LinearElementRecoveryViewSurfaceSummary {
        model_en_us: model.0,
        model_ko_kr: model.1,
        mgt_en_us: mgt.0,
        mgt_ko_kr: mgt.1,
    })
}

fn inspect_exact_modal_directory(
    workspace: &Path,
    root: &Path,
    expected_names: &[&str],
    label: &str,
) -> Result<Vec<Vec<u8>>, DistributionError> {
    let root = resolve_workspace_child(workspace, root, label)?;
    let mut entries = fs::read_dir(&root)
        .map_err(|error| io_error("rootfs_model_modal_directory_read_failed", error))?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|error| io_error("rootfs_model_modal_entry_read_failed", error))?;
    entries.sort_by_key(fs::DirEntry::file_name);
    let actual_names = entries
        .iter()
        .map(|entry| entry.file_name().into_string())
        .collect::<Result<Vec<_>, _>>()
        .map_err(|_| {
            DistributionError::new(
                "rootfs_model_modal_inventory_invalid",
                format!("{label} contains a non-UTF-8 artifact name"),
            )
        })?;
    if actual_names != expected_names {
        return Err(DistributionError::new(
            "rootfs_model_modal_inventory_invalid",
            format!("{label} does not contain the exact modal artifact inventory"),
        ));
    }
    entries
        .iter()
        .map(|entry| {
            let path = entry.path();
            let metadata = fs::symlink_metadata(&path)
                .map_err(|error| io_error("rootfs_model_modal_artifact_metadata_failed", error))?;
            if !metadata.is_file() || metadata.file_type().is_symlink() {
                return Err(DistributionError::new(
                    "rootfs_model_modal_artifact_invalid",
                    format!("{label} contains a non-regular artifact"),
                ));
            }
            read_bounded_regular_file(&path, MAX_MANIFEST_BYTES)
        })
        .collect()
}

fn inspect_model_modal_view_artifact(
    workspace: &Path,
    path: &Path,
    locale: &str,
    label: &str,
) -> Result<(Vec<u8>, String), DistributionError> {
    let bytes = read_direct_workspace_file(workspace, path, label)?;
    if bytes.contains(&0x1b) {
        return Err(DistributionError::new(
            "rootfs_model_modal_view_unsafe",
            format!("{label} contains an ANSI escape byte"),
        ));
    }
    let text = std::str::from_utf8(&bytes).map_err(|_| {
        DistributionError::new(
            "rootfs_model_modal_view_invalid",
            format!("{label} must be UTF-8"),
        )
    })?;
    let without_final_newline = text.strip_suffix('\n').ok_or_else(|| {
        DistributionError::new(
            "rootfs_model_modal_view_noncanonical",
            format!("{label} must end with one newline"),
        )
    })?;
    let final_line_start = without_final_newline
        .rfind('\n')
        .map_or(0, |position| position + 1);
    let final_line = &without_final_newline[final_line_start..];
    let (hash_label, schema_line, locale_line, modes_line) = match locale {
        "en-US" => (
            "View hash: ",
            "Schema: structural-native-workbench-model-ir-modal-result-view.v1",
            "Locale: en-US",
            "Modes: 3",
        ),
        "ko-KR" => (
            "보기 해시: ",
            "스키마: structural-native-workbench-model-ir-modal-result-view.v1",
            "로케일: ko-KR",
            "모드 수: 3",
        ),
        _ => {
            return Err(DistributionError::new(
                "rootfs_model_modal_view_invalid",
                "modal result view locale contract is unsupported",
            ));
        }
    };
    let declared_hash = final_line.strip_prefix(hash_label).ok_or_else(|| {
        DistributionError::new(
            "rootfs_model_modal_view_hash_missing",
            format!("{label} has no terminal self-hash"),
        )
    })?;
    validate_sha256_identity(declared_hash, "rootfs modal result view self-hash")?;
    if declared_hash != sha256_identity(&bytes[..final_line_start]) {
        return Err(DistributionError::new(
            "rootfs_model_modal_view_hash_mismatch",
            format!("{label} self-hash does not verify"),
        ));
    }
    let modal_rows = text
        .lines()
        .filter(|line| {
            line.as_bytes().get(..4).is_some_and(|prefix| {
                prefix.iter().all(u8::is_ascii_digit)
                    && line.as_bytes().get(4).is_some_and(u8::is_ascii_whitespace)
            })
        })
        .count();
    if !text.lines().any(|line| line == schema_line)
        || !text.lines().any(|line| line == locale_line)
        || !text.lines().any(|line| line == modes_line)
        || !text.contains("cpu / fp64 / fallback 0")
        || modal_rows != 3
    {
        return Err(DistributionError::new(
            "rootfs_model_modal_view_contract_invalid",
            format!("{label} does not expose the exact bounded modal view contract"),
        ));
    }
    let artifact_sha256 = sha256_identity(text.as_bytes());
    Ok((bytes, artifact_sha256))
}

fn inspect_model_modal_invalid_window_failure(
    workspace: &Path,
    path: &Path,
) -> Result<(), DistributionError> {
    let bytes = read_direct_workspace_file(workspace, path, "invalid-window modal view failure")?;
    let canonical = bytes.strip_suffix(b"\n").ok_or_else(|| {
        DistributionError::new(
            "rootfs_model_modal_view_failure_noncanonical",
            "invalid-window modal view failure must be one JSON line",
        )
    })?;
    let value = structural_contracts::model_ir::decode_json_strict(canonical).map_err(|error| {
        DistributionError::new(
            "rootfs_model_modal_view_failure_invalid",
            format!("invalid-window modal view failure is invalid JSON: {error}"),
        )
    })?;
    let object = value.as_object().ok_or_else(|| {
        DistributionError::new(
            "rootfs_model_modal_view_failure_invalid",
            "invalid-window modal view failure must be an object",
        )
    })?;
    let actual = object.keys().map(String::as_str).collect::<BTreeSet<_>>();
    let expected = ["code", "detail", "schema_version"]
        .into_iter()
        .collect::<BTreeSet<_>>();
    if actual != expected
        || value
            .get("schema_version")
            .and_then(serde_json::Value::as_str)
            != Some("structural-native-workbench-failure.v1")
        || value.get("code").and_then(serde_json::Value::as_str)
            != Some("workbench_modal_result_view_window_invalid")
        || value
            .get("detail")
            .and_then(serde_json::Value::as_str)
            .map_or(true, str::is_empty)
        || compact_operator_json(&value)? != canonical
    {
        return Err(DistributionError::new(
            "rootfs_model_modal_view_failure_invalid",
            "invalid-window modal view failure does not match the fail-closed contract",
        ));
    }
    Ok(())
}

#[allow(clippy::too_many_lines)]
fn inspect_rootfs_model_modal_surface(
    workspace: &Path,
    request: &RootfsIsolationProbeRequest<'_>,
) -> Result<ModelModalSurfaceSummary, DistributionError> {
    const REQUEST_ARTIFACTS: [&str; 2] = ["analysis-request.json", "request-receipt.json"];
    const RESULT_ARTIFACTS: [&str; 11] = [
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
    let request_artifacts = inspect_exact_modal_directory(
        workspace,
        request.model_modal_request_root,
        &REQUEST_ARTIFACTS,
        "ModelIR modal request directory",
    )?;
    let direct = inspect_exact_modal_directory(
        workspace,
        request.model_modal_direct_root,
        &RESULT_ARTIFACTS,
        "direct ModelIR modal result directory",
    )?;
    let resumed = inspect_exact_modal_directory(
        workspace,
        request.model_modal_resumed_root,
        &RESULT_ARTIFACTS,
        "resumed ModelIR modal result directory",
    )?;
    let before_view = inspect_exact_modal_directory(
        workspace,
        request.model_modal_view_source_before,
        &RESULT_ARTIFACTS,
        "pre-view ModelIR modal result snapshot",
    )?;
    if direct != resumed {
        return Err(DistributionError::new(
            "rootfs_model_modal_restart_mismatch",
            "direct and resumed ModelIR modal result directories differ",
        ));
    }
    if direct != before_view {
        return Err(DistributionError::new(
            "rootfs_model_modal_view_mutated_source",
            "modal result view mutated its source directory",
        ));
    }
    let direct_stdout = read_direct_workspace_file(
        workspace,
        request.model_modal_direct_stdout,
        "direct ModelIR modal stdout",
    )?;
    let resumed_stdout = read_direct_workspace_file(
        workspace,
        request.model_modal_resumed_stdout,
        "resumed ModelIR modal stdout",
    )?;
    if direct_stdout != resumed_stdout {
        return Err(DistributionError::new(
            "rootfs_model_modal_restart_mismatch",
            "direct and resumed ModelIR modal stdout differs",
        ));
    }
    let result =
        structural_contracts::spectral_product::parse_dense_spectral_result_ir_v1(&direct[9])
            .map_err(|error| {
                DistributionError::new(
                    "rootfs_model_modal_result_invalid",
                    format!("rootfs modal ResultIR failed strict verification: {error}"),
                )
            })?;
    if result.result().summary.mode_count != 3
        || result.result().modes.len() != 3
        || result.result().backend_receipt.fallback_count != 0
        || result.result().analysis_kind
            != structural_contracts::spectral_product::SpectralAnalysisKindV1::Modal
    {
        return Err(DistributionError::new(
            "rootfs_model_modal_result_invalid",
            "rootfs modal ResultIR does not match the exact three-mode CPU contract",
        ));
    }
    let run_receipt =
        structural_contracts::model_ir::decode_json_strict(&direct[10]).map_err(|error| {
            DistributionError::new(
                "rootfs_model_modal_receipt_invalid",
                format!("rootfs modal run receipt is invalid JSON: {error}"),
            )
        })?;
    if run_receipt
        .get("schema_version")
        .and_then(serde_json::Value::as_str)
        != Some("structural-model-ir-modal-run-receipt.v1")
        || run_receipt
            .get("status")
            .and_then(serde_json::Value::as_str)
            != Some("completed")
        || run_receipt
            .get("fallback_count")
            .and_then(serde_json::Value::as_u64)
            != Some(0)
        || run_receipt
            .get("artifacts")
            .and_then(serde_json::Value::as_array)
            .map_or(true, |artifacts| artifacts.len() != 10)
    {
        return Err(DistributionError::new(
            "rootfs_model_modal_receipt_invalid",
            "rootfs modal run receipt does not match the completed bounded contract",
        ));
    }
    let en_us_first = inspect_model_modal_view_artifact(
        workspace,
        request.model_modal_result_view_en_us_first,
        "en-US",
        "first en-US modal result view",
    )?;
    let en_us_second = inspect_model_modal_view_artifact(
        workspace,
        request.model_modal_result_view_en_us_second,
        "en-US",
        "second en-US modal result view",
    )?;
    let ko_kr_first = inspect_model_modal_view_artifact(
        workspace,
        request.model_modal_result_view_ko_kr_first,
        "ko-KR",
        "first ko-KR modal result view",
    )?;
    let ko_kr_second = inspect_model_modal_view_artifact(
        workspace,
        request.model_modal_result_view_ko_kr_second,
        "ko-KR",
        "second ko-KR modal result view",
    )?;
    if en_us_first.0 != en_us_second.0 || ko_kr_first.0 != ko_kr_second.0 {
        return Err(DistributionError::new(
            "rootfs_model_modal_view_determinism_failed",
            "repeated modal result views differ",
        ));
    }
    if en_us_first.1 == ko_kr_first.1 {
        return Err(DistributionError::new(
            "rootfs_model_modal_view_locale_collision",
            "modal result view locales have the same identity",
        ));
    }
    inspect_model_modal_invalid_window_failure(
        workspace,
        request.model_modal_result_view_invalid_window_failure,
    )?;
    Ok(ModelModalSurfaceSummary {
        request_sha256: sha256_identity(&request_artifacts[0]),
        request_receipt_sha256: sha256_identity(&request_artifacts[1]),
        checkpoint_sha256: sha256_identity(&direct[2]),
        result_ir_sha256: sha256_identity(&direct[9]),
        run_receipt_sha256: sha256_identity(&direct[10]),
        view_en_us_sha256: en_us_first.1,
        view_ko_kr_sha256: ko_kr_first.1,
    })
}

#[allow(clippy::too_many_lines)]
fn inspect_reaction_audit_artifact(
    workspace: &Path,
    path: &Path,
    locale: &str,
    normalized_mgt: bool,
    label: &str,
) -> Result<ReactionAuditArtifact, DistributionError> {
    let bytes = read_direct_workspace_file(workspace, path, label)?;
    if bytes.contains(&0x1b) {
        return Err(DistributionError::new(
            "rootfs_reaction_audit_unsafe",
            format!("{label} contains an ANSI escape byte"),
        ));
    }
    let text = std::str::from_utf8(&bytes).map_err(|_| {
        DistributionError::new(
            "rootfs_reaction_audit_invalid",
            format!("{label} must be UTF-8"),
        )
    })?;
    let without_final_newline = text.strip_suffix('\n').ok_or_else(|| {
        DistributionError::new(
            "rootfs_reaction_audit_noncanonical",
            format!("{label} must end with one newline"),
        )
    })?;
    let final_line_start = without_final_newline
        .rfind('\n')
        .map_or(0, |position| position + 1);
    let final_line = &without_final_newline[final_line_start..];
    let hash_label = match locale {
        "en-US" => "Audit hash: ",
        "ko-KR" => "감사 해시: ",
        _ => {
            return Err(DistributionError::new(
                "rootfs_reaction_audit_invalid",
                "reaction audit locale contract is unsupported",
            ));
        }
    };
    let declared_hash = final_line.strip_prefix(hash_label).ok_or_else(|| {
        DistributionError::new(
            "rootfs_reaction_audit_hash_missing",
            format!("{label} has no terminal self-hash"),
        )
    })?;
    validate_sha256_identity(declared_hash, "rootfs reaction audit self-hash")?;
    if declared_hash != sha256_identity(&bytes[..final_line_start]) {
        return Err(DistributionError::new(
            "rootfs_reaction_audit_hash_mismatch",
            format!("{label} self-hash does not verify"),
        ));
    }

    let (schema_line, locale_line, status_lines, force_closure, moment_closure) =
        match (locale, normalized_mgt) {
            ("en-US", false) => (
                "Schema: structural-native-workbench-model-ir-linear-reaction-audit.v1",
                "Locale: en-US",
                [
                    "Force status: within_numeric_tolerance",
                    "Moment status: within_numeric_tolerance",
                    "Active equation status: within_numeric_tolerance",
                    "Overall numeric status: within_numeric_tolerance",
                ],
                "Force closure residual: X=+0.00000000000000000e0; Y=+0.00000000000000000e0; Z=+0.00000000000000000e0 N",
                "Moment closure residual: X=+0.00000000000000000e0; Y=+0.00000000000000000e0; Z=+0.00000000000000000e0 N*m",
            ),
            ("en-US", true) => (
                "Schema: structural-native-workbench-model-ir-linear-reaction-audit.v1",
                "Locale: en-US",
                [
                    "Force status: within_numeric_tolerance",
                    "Moment status: within_numeric_tolerance",
                    "Active equation status: within_numeric_tolerance",
                    "Overall numeric status: within_numeric_tolerance",
                ],
                "Force closure residual: X=-1.16415321826934814e-10; Y=+0.00000000000000000e0; Z=+0.00000000000000000e0 N",
                "Moment closure residual: X=+0.00000000000000000e0; Y=-5.82076609134674072e-10; Z=+0.00000000000000000e0 N*m",
            ),
            ("ko-KR", false) => (
                "스키마: structural-native-workbench-model-ir-linear-reaction-audit.v1",
                "로케일: ko-KR",
                [
                    "힘 상태: within_numeric_tolerance",
                    "모멘트 상태: within_numeric_tolerance",
                    "활성 방정식 상태: within_numeric_tolerance",
                    "종합 수치 상태: within_numeric_tolerance",
                ],
                "힘 폐합 잔차: X=+0.00000000000000000e0; Y=+0.00000000000000000e0; Z=+0.00000000000000000e0 N",
                "모멘트 폐합 잔차: X=+0.00000000000000000e0; Y=+0.00000000000000000e0; Z=+0.00000000000000000e0 N*m",
            ),
            ("ko-KR", true) => (
                "스키마: structural-native-workbench-model-ir-linear-reaction-audit.v1",
                "로케일: ko-KR",
                [
                    "힘 상태: within_numeric_tolerance",
                    "모멘트 상태: within_numeric_tolerance",
                    "활성 방정식 상태: within_numeric_tolerance",
                    "종합 수치 상태: within_numeric_tolerance",
                ],
                "힘 폐합 잔차: X=-1.16415321826934814e-10; Y=+0.00000000000000000e0; Z=+0.00000000000000000e0 N",
                "모멘트 폐합 잔차: X=+0.00000000000000000e0; Y=-5.82076609134674072e-10; Z=+0.00000000000000000e0 N*m",
            ),
            _ => unreachable!("locale was validated above"),
        };
    if !text.lines().any(|line| line == schema_line)
        || !text.lines().any(|line| line == locale_line)
        || !text.lines().any(|line| line == force_closure)
        || !text.lines().any(|line| line == moment_closure)
        || status_lines
            .iter()
            .any(|expected| !text.lines().any(|line| line == *expected))
        || !text.contains("256*IEEE754_BINARY64_EPSILON*max(1,absolute_contribution_scale)")
        || !text.contains("fallback 0")
    {
        return Err(DistributionError::new(
            "rootfs_reaction_audit_contract_invalid",
            format!("{label} does not expose the exact algebraic reaction-audit contract"),
        ));
    }
    Ok(ReactionAuditArtifact {
        sha256: sha256_identity(&bytes),
        bytes,
    })
}

fn inspect_reaction_audit_probe(
    workspace: &Path,
    probe: &ReactionAuditProbe<'_>,
) -> Result<(String, String), DistributionError> {
    let session_before = read_direct_workspace_file(
        workspace,
        probe.session_before,
        &format!("{} pre-audit session", probe.label),
    )?;
    let session_after = read_bounded_regular_file(
        &probe.workbench_root.join("workbench-session.json"),
        MAX_MANIFEST_BYTES,
    )?;
    if session_before != session_after {
        return Err(DistributionError::new(
            "rootfs_reaction_audit_session_mutated",
            format!("{} reaction audit mutated its durable session", probe.label),
        ));
    }
    let inspect = |path, locale, suffix| {
        inspect_reaction_audit_artifact(
            workspace,
            path,
            locale,
            probe.normalized_mgt,
            &format!("{} {locale} {suffix} reaction audit", probe.label),
        )
    };
    let en_us_first = inspect(probe.en_us_first, "en-US", "first")?;
    let en_us_second = inspect(probe.en_us_second, "en-US", "second")?;
    let ko_kr_first = inspect(probe.ko_kr_first, "ko-KR", "first")?;
    let ko_kr_second = inspect(probe.ko_kr_second, "ko-KR", "second")?;
    if en_us_first.bytes != en_us_second.bytes || ko_kr_first.bytes != ko_kr_second.bytes {
        return Err(DistributionError::new(
            "rootfs_reaction_audit_determinism_failed",
            format!("{} repeated reaction audits differ", probe.label),
        ));
    }
    if en_us_first.sha256 == ko_kr_first.sha256 {
        return Err(DistributionError::new(
            "rootfs_reaction_audit_locale_collision",
            format!(
                "{} reaction audit locales have the same identity",
                probe.label
            ),
        ));
    }
    Ok((en_us_first.sha256, ko_kr_first.sha256))
}

fn inspect_reaction_audit_wrong_profile_failure(
    workspace: &Path,
    path: &Path,
) -> Result<(), DistributionError> {
    let bytes = read_direct_workspace_file(workspace, path, "wrong-profile reaction audit")?;
    let canonical = bytes.strip_suffix(b"\n").ok_or_else(|| {
        DistributionError::new(
            "rootfs_reaction_audit_failure_noncanonical",
            "wrong-profile reaction audit failure must be one JSON line",
        )
    })?;
    let value = structural_contracts::model_ir::decode_json_strict(canonical).map_err(|error| {
        DistributionError::new(
            "rootfs_reaction_audit_failure_invalid",
            format!("wrong-profile reaction audit failure is invalid JSON: {error}"),
        )
    })?;
    let object = value.as_object().ok_or_else(|| {
        DistributionError::new(
            "rootfs_reaction_audit_failure_invalid",
            "wrong-profile reaction audit failure must be a JSON object",
        )
    })?;
    let actual = object.keys().map(String::as_str).collect::<BTreeSet<_>>();
    let expected = ["code", "detail", "schema_version"]
        .into_iter()
        .collect::<BTreeSet<_>>();
    if actual != expected {
        return Err(DistributionError::new(
            "rootfs_reaction_audit_failure_invalid",
            "wrong-profile reaction audit failure has an unexpected field set",
        ));
    }
    if value
        .get("schema_version")
        .and_then(serde_json::Value::as_str)
        != Some("structural-native-workbench-failure.v1")
        || value.get("code").and_then(serde_json::Value::as_str)
            != Some("workbench_profile_unsupported")
        || match value.get("detail").and_then(serde_json::Value::as_str) {
            Some(detail) => detail.is_empty(),
            None => true,
        }
        || compact_operator_json(&value)? != canonical
    {
        return Err(DistributionError::new(
            "rootfs_reaction_audit_failure_invalid",
            "wrong-profile reaction audit failure does not match the exact fail-closed contract",
        ));
    }
    Ok(())
}

fn inspect_rootfs_reaction_audit_surface(
    workspace: &Path,
    model_ir_linear_root: &Path,
    mgt_model_ir_linear_root: &Path,
    request: &RootfsIsolationProbeRequest<'_>,
) -> Result<ReactionAuditSurfaceSummary, DistributionError> {
    let model = inspect_reaction_audit_probe(
        workspace,
        &ReactionAuditProbe {
            label: "ModelIR linear",
            workbench_root: model_ir_linear_root,
            session_before: request.model_ir_linear_workbench_session_before_reaction_view,
            en_us_first: request.model_ir_linear_reaction_audit_en_us_first,
            en_us_second: request.model_ir_linear_reaction_audit_en_us_second,
            ko_kr_first: request.model_ir_linear_reaction_audit_ko_kr_first,
            ko_kr_second: request.model_ir_linear_reaction_audit_ko_kr_second,
            normalized_mgt: false,
        },
    )?;
    let mgt = inspect_reaction_audit_probe(
        workspace,
        &ReactionAuditProbe {
            label: "normalized-MGT linear",
            workbench_root: mgt_model_ir_linear_root,
            session_before: request.mgt_model_ir_linear_workbench_session_before_reaction_view,
            en_us_first: request.mgt_model_ir_linear_reaction_audit_en_us_first,
            en_us_second: request.mgt_model_ir_linear_reaction_audit_en_us_second,
            ko_kr_first: request.mgt_model_ir_linear_reaction_audit_ko_kr_first,
            ko_kr_second: request.mgt_model_ir_linear_reaction_audit_ko_kr_second,
            normalized_mgt: true,
        },
    )?;
    inspect_reaction_audit_wrong_profile_failure(
        workspace,
        request.workbench_reaction_audit_wrong_profile_failure,
    )?;
    if model.0 == mgt.0 {
        return Err(DistributionError::new(
            "rootfs_reaction_audit_profile_collision",
            "strict-ModelIR and normalized-MGT reaction audits have the same identity",
        ));
    }
    Ok(ReactionAuditSurfaceSummary {
        model_en_us: model.0,
        model_ko_kr: model.1,
        mgt_en_us: mgt.0,
        mgt_ko_kr: mgt.1,
    })
}

fn require_exact_json_keys(
    value: &serde_json::Value,
    expected: &[&str],
    label: &str,
) -> Result<(), DistributionError> {
    let object = value.as_object().ok_or_else(|| {
        DistributionError::new(
            "rootfs_localized_pdf_receipt_invalid",
            format!("{label} must be a JSON object"),
        )
    })?;
    let actual = object.keys().map(String::as_str).collect::<BTreeSet<_>>();
    let expected = expected.iter().copied().collect::<BTreeSet<_>>();
    if actual != expected {
        return Err(DistributionError::new(
            "rootfs_localized_pdf_receipt_invalid",
            format!("{label} has an unexpected field set"),
        ));
    }
    Ok(())
}

#[allow(clippy::too_many_lines)]
fn inspect_model_ir_engineering_localized_pdf_output(
    workspace: &Path,
    payload_root: &Path,
    output_root: &Path,
    locale: &str,
) -> Result<(Vec<u8>, Vec<u8>), DistributionError> {
    let root = resolve_workspace_child(workspace, output_root, "localized sparse PDF output")?;
    let pdf = read_bounded_regular_file(&root.join("report.pdf"), MAX_MANIFEST_BYTES)?;
    let receipt_bytes =
        read_bounded_regular_file(&root.join("pdf-receipt.json"), MAX_MANIFEST_BYTES)?;
    let receipt: serde_json::Value = serde_json::from_slice(&receipt_bytes).map_err(|error| {
        DistributionError::new(
            "rootfs_localized_pdf_receipt_invalid",
            format!("localized ModelIR engineering PDF receipt is invalid JSON: {error}"),
        )
    })?;
    if compact_operator_json(&receipt)? != receipt_bytes {
        return Err(DistributionError::new(
            "rootfs_localized_pdf_receipt_noncanonical",
            "localized ModelIR engineering PDF receipt is not canonical JSON",
        ));
    }
    require_exact_json_keys(
        &receipt,
        &[
            "artifacts",
            "case_id",
            "claim_boundary",
            "document_source_hash",
            "embedded_font",
            "locale",
            "pdf_claim_boundary",
            "pdf_hash",
            "profile",
            "receipt_hash",
            "schema_version",
            "source_reaction_hash",
            "source_recovery_hash",
            "source_report_hash",
            "source_result_hash",
        ],
        "localized ModelIR engineering PDF receipt",
    )?;
    verify_operator_self_hash(
        &receipt,
        "receipt_hash",
        "localized ModelIR engineering PDF receipt",
    )?;
    let exact_profile = require_operator_string(
        &receipt,
        "schema_version",
        "localized ModelIR engineering PDF receipt",
    )? == MODEL_IR_ENGINEERING_LOCALIZED_PDF_RECEIPT_SCHEMA
        && require_operator_string(
            &receipt,
            "profile",
            "localized ModelIR engineering PDF receipt",
        )? == MODEL_IR_ENGINEERING_LOCALIZED_PDF_PROFILE
        && require_operator_string(
            &receipt,
            "locale",
            "localized ModelIR engineering PDF receipt",
        )? == locale
        && require_operator_string(
            &receipt,
            "claim_boundary",
            "localized ModelIR engineering PDF receipt",
        )? == MODEL_IR_ENGINEERING_LOCALIZED_PDF_CLAIM_BOUNDARY;
    if !exact_profile {
        return Err(DistributionError::new(
            "rootfs_localized_pdf_receipt_invalid",
            "localized ModelIR engineering PDF receipt profile, locale, or authority boundary is invalid",
        ));
    }
    for field in [
        "source_result_hash",
        "source_recovery_hash",
        "source_reaction_hash",
        "source_report_hash",
        "document_source_hash",
        "pdf_hash",
        "receipt_hash",
    ] {
        validate_sha256_identity(
            require_operator_string(&receipt, field, "localized ModelIR engineering PDF receipt")?,
            field,
        )?;
    }
    if require_operator_string(
        &receipt,
        "pdf_hash",
        "localized ModelIR engineering PDF receipt",
    )? != sha256_identity(&pdf)
        || !pdf.starts_with(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
        || !pdf.ends_with(b"%%EOF\n")
        || !pdf
            .windows(b"/Encoding /Identity-H".len())
            .any(|window| window == b"/Encoding /Identity-H")
        || !pdf
            .windows(b"/ToUnicode 9 0 R".len())
            .any(|window| window == b"/ToUnicode 9 0 R")
    {
        return Err(DistributionError::new(
            "rootfs_localized_pdf_artifact_invalid",
            "localized ModelIR engineering PDF bytes do not match the receipt or embedded-font container",
        ));
    }

    let artifacts = receipt
        .get("artifacts")
        .and_then(serde_json::Value::as_array)
        .filter(|artifacts| artifacts.len() == 1)
        .ok_or_else(|| {
            DistributionError::new(
                "rootfs_localized_pdf_receipt_invalid",
                "localized ModelIR engineering PDF receipt must contain exactly one artifact",
            )
        })?;
    let artifact = &artifacts[0];
    require_exact_json_keys(
        artifact,
        &["byte_length", "content_hash", "file", "media_type", "role"],
        "localized ModelIR engineering PDF artifact",
    )?;
    if require_operator_string(
        artifact,
        "role",
        "localized ModelIR engineering PDF artifact",
    )? != "model_ir_linear_engineering_localized_pdf_report"
        || require_operator_string(
            artifact,
            "file",
            "localized ModelIR engineering PDF artifact",
        )? != "report.pdf"
        || require_operator_string(
            artifact,
            "media_type",
            "localized ModelIR engineering PDF artifact",
        )? != "application/pdf"
        || require_operator_string(
            artifact,
            "content_hash",
            "localized ModelIR engineering PDF artifact",
        )? != sha256_identity(&pdf)
        || artifact
            .get("byte_length")
            .and_then(serde_json::Value::as_u64)
            != u64::try_from(pdf.len()).ok()
    {
        return Err(DistributionError::new(
            "rootfs_localized_pdf_artifact_invalid",
            "localized ModelIR engineering PDF artifact inventory does not match report.pdf",
        ));
    }

    let font = receipt.get("embedded_font").ok_or_else(|| {
        DistributionError::new(
            "rootfs_localized_pdf_receipt_invalid",
            "localized sparse PDF receipt has no embedded font inventory",
        )
    })?;
    require_exact_json_keys(
        font,
        &[
            "byte_length",
            "content_hash",
            "license",
            "postscript_name",
            "provenance",
        ],
        "localized sparse PDF embedded font",
    )?;
    let font_path = payload_root.join("share/structural-report/StructuralReportKoreanSubset.ttf");
    let font_bytes = read_bounded_regular_file(&font_path, MAX_MANIFEST_BYTES)?;
    if font_bytes.is_empty()
        || require_operator_string(
            font,
            "postscript_name",
            "localized sparse PDF embedded font",
        )? != "StructuralReportKoreanSubset"
        || require_operator_string(font, "content_hash", "localized sparse PDF embedded font")?
            != sha256_identity(&font_bytes)
        || font.get("byte_length").and_then(serde_json::Value::as_u64)
            != u64::try_from(font_bytes.len()).ok()
        || !pdf
            .windows(font_bytes.len())
            .any(|window| window == font_bytes.as_slice())
    {
        return Err(DistributionError::new(
            "rootfs_localized_pdf_font_invalid",
            "localized sparse PDF does not embed the exact installed font",
        ));
    }
    for (field, path, distribution_path, id) in [
        (
            "license",
            "share/structural-report/OFL-1.1.txt",
            "share/structural-report/OFL-1.1.txt",
            Some("OFL-1.1"),
        ),
        (
            "provenance",
            "share/structural-report/StructuralReportKoreanSubset.provenance.json",
            "share/structural-report/StructuralReportKoreanSubset.provenance.json",
            None,
        ),
    ] {
        let item = font.get(field).ok_or_else(|| {
            DistributionError::new(
                "rootfs_localized_pdf_receipt_invalid",
                format!("localized sparse PDF embedded font has no {field}"),
            )
        })?;
        let expected_keys = if id.is_some() {
            &["byte_length", "content_hash", "distribution_path", "id"][..]
        } else {
            &["byte_length", "content_hash", "distribution_path"][..]
        };
        require_exact_json_keys(item, expected_keys, field)?;
        let bytes = read_bounded_regular_file(&payload_root.join(path), MAX_MANIFEST_BYTES)?;
        let valid = require_operator_string(item, "distribution_path", field)? == distribution_path
            && require_operator_string(item, "content_hash", field)? == sha256_identity(&bytes)
            && item.get("byte_length").and_then(serde_json::Value::as_u64)
                == u64::try_from(bytes.len()).ok()
            && id.map_or(true, |expected| {
                item.get("id").and_then(serde_json::Value::as_str) == Some(expected)
            });
        if !valid {
            return Err(DistributionError::new(
                "rootfs_localized_pdf_font_invalid",
                format!("localized sparse PDF {field} does not match the installed payload"),
            ));
        }
    }
    Ok((pdf, receipt_bytes))
}

#[allow(clippy::too_many_arguments)]
fn inspect_model_ir_linear_localized_pdf_surface(
    workspace: &Path,
    payload_root: &Path,
    workbench_root: &Path,
    session_before: &Path,
    en_us_first_root: &Path,
    en_us_second_root: &Path,
    ko_kr_first_root: &Path,
    ko_kr_second_root: &Path,
) -> Result<LocalizedPdfSurfaceSummary, DistributionError> {
    let model_root = resolve_workspace_child(
        workspace,
        workbench_root,
        "ModelIR linear Workbench localized PDF source",
    )?;
    let session_parent = session_before.parent().ok_or_else(|| {
        DistributionError::new(
            "rootfs_localized_pdf_session_path_invalid",
            "localized PDF session snapshot has no parent directory",
        )
    })?;
    if resolve_real_directory(session_parent, "localized PDF session snapshot parent")? != workspace
    {
        return Err(DistributionError::new(
            "rootfs_localized_pdf_session_path_invalid",
            "localized PDF session snapshot must be a direct operator-workspace file",
        ));
    }
    let before = read_bounded_regular_file(session_before, MAX_MANIFEST_BYTES)?;
    let after = read_bounded_regular_file(
        &model_root.join("workbench-session.json"),
        MAX_MANIFEST_BYTES,
    )?;
    if before != after {
        return Err(DistributionError::new(
            "rootfs_localized_pdf_session_mutated",
            "localized sparse PDF export mutated the durable ModelIR-linear session",
        ));
    }
    let (en_first_pdf, en_first_receipt) = inspect_model_ir_engineering_localized_pdf_output(
        workspace,
        payload_root,
        en_us_first_root,
        "en-US",
    )?;
    let (en_second_pdf, en_second_receipt) = inspect_model_ir_engineering_localized_pdf_output(
        workspace,
        payload_root,
        en_us_second_root,
        "en-US",
    )?;
    let (ko_first_pdf, ko_first_receipt) = inspect_model_ir_engineering_localized_pdf_output(
        workspace,
        payload_root,
        ko_kr_first_root,
        "ko-KR",
    )?;
    let (ko_second_pdf, ko_second_receipt) = inspect_model_ir_engineering_localized_pdf_output(
        workspace,
        payload_root,
        ko_kr_second_root,
        "ko-KR",
    )?;
    if en_first_pdf != en_second_pdf
        || en_first_receipt != en_second_receipt
        || ko_first_pdf != ko_second_pdf
        || ko_first_receipt != ko_second_receipt
        || en_first_pdf == ko_first_pdf
    {
        return Err(DistributionError::new(
            "rootfs_localized_pdf_determinism_failed",
            "localized sparse PDF repeats drifted or locale outputs were not distinct",
        ));
    }
    Ok(LocalizedPdfSurfaceSummary {
        en_us_pdf: sha256_identity(&en_first_pdf),
        ko_kr_pdf: sha256_identity(&ko_first_pdf),
        en_us_receipt: sha256_identity(&en_first_receipt),
        ko_kr_receipt: sha256_identity(&ko_first_receipt),
    })
}

fn inspect_reported_workbench(
    workspace: &Path,
    workbench_root: &Path,
    expected_analysis_profile: Option<&str>,
) -> Result<ReportedWorkbenchSummary, DistributionError> {
    let root = resolve_workspace_child(workspace, workbench_root, "native Workbench")?;
    let session_bytes =
        read_bounded_regular_file(&root.join("workbench-session.json"), MAX_MANIFEST_BYTES)?;
    let session: serde_json::Value = serde_json::from_slice(&session_bytes).map_err(|error| {
        DistributionError::new(
            "rootfs_workbench_session_invalid",
            format!("native Workbench session is invalid JSON: {error}"),
        )
    })?;
    let stage = session
        .get("stage")
        .and_then(serde_json::Value::as_str)
        .unwrap_or_default();
    let terminal_status = session
        .get("terminal_status")
        .and_then(serde_json::Value::as_str)
        .unwrap_or_default();
    let comparison_passed = session
        .get("comparison_passed")
        .and_then(serde_json::Value::as_bool)
        .unwrap_or(false);
    let session_id = session
        .get("session_id")
        .and_then(serde_json::Value::as_str)
        .unwrap_or_default();
    let session_hash = session
        .get("session_hash")
        .and_then(serde_json::Value::as_str)
        .unwrap_or_default();
    let analysis_profile = session
        .get("analysis_profile")
        .and_then(serde_json::Value::as_str);
    let mgt_source_sha256 = session
        .get("mgt_source_hash")
        .and_then(serde_json::Value::as_str)
        .map(ToOwned::to_owned);
    let mgt_import_health_sha256 = session
        .get("mgt_import_health_artifact_hash")
        .and_then(serde_json::Value::as_str)
        .map(ToOwned::to_owned);
    if stage != "reported"
        || terminal_status != "completed"
        || !comparison_passed
        || analysis_profile != expected_analysis_profile
    {
        return Err(DistributionError::new(
            "rootfs_workbench_incomplete",
            "native Workbench session must have the expected profile and be reported, completed and comparison-passing",
        ));
    }
    validate_sha256_identity(session_id, "rootfs Workbench session ID")?;
    validate_sha256_identity(session_hash, "rootfs Workbench session hash")?;
    if mgt_source_sha256.is_some() != mgt_import_health_sha256.is_some() {
        return Err(DistributionError::new(
            "rootfs_workbench_mgt_binding_incomplete",
            "native Workbench MGT source and import-health identities must be present together",
        ));
    }
    if let Some(value) = mgt_source_sha256.as_deref() {
        validate_sha256_identity(value, "rootfs Workbench MGT source SHA-256")?;
    }
    if let Some(value) = mgt_import_health_sha256.as_deref() {
        validate_sha256_identity(value, "rootfs Workbench MGT import-health SHA-256")?;
    }
    let (result_recovery_ir_sha256, reaction_result_ir_sha256, report_document_sha256) =
        if expected_analysis_profile == Some("model_ir_linear_cpu_v1") {
            (
                Some(sha256_file(
                    &root.join("04-resume/result-recovery-ir.json"),
                )?),
                Some(sha256_file(
                    &root.join("04-resume/reaction-result-ir.json"),
                )?),
                Some(sha256_file(&root.join("06-report/report.md"))?),
            )
        } else {
            (None, None, None)
        };
    Ok(ReportedWorkbenchSummary {
        session_id: session_id.to_owned(),
        session_hash: session_hash.to_owned(),
        stage: stage.to_owned(),
        terminal_status: terminal_status.to_owned(),
        comparison_passed,
        result_ir_sha256: sha256_file(&root.join("04-resume/result-ir.json"))?,
        comparison_ir_sha256: sha256_file(&root.join("05-compare/external-comparison-ir.json"))?,
        report_pdf_sha256: sha256_file(&root.join("06-report/report.pdf"))?,
        result_recovery_ir_sha256,
        reaction_result_ir_sha256,
        report_document_sha256,
        mgt_source_sha256,
        mgt_import_health_sha256,
    })
}

fn inspect_normalized_mgt_import_surface(
    workspace: &Path,
    workbench_root: &Path,
    reported: &ReportedWorkbenchSummary,
) -> Result<(String, String), DistributionError> {
    let root = resolve_workspace_child(workspace, workbench_root, "normalized MGT Workbench")?;
    let source = read_bounded_regular_file(&root.join("01-import/source.mgt"), MAX_MANIFEST_BYTES)?;
    let source_sha256 = sha256_identity(&source);
    let health_bytes = read_bounded_regular_file(
        &root.join("01-import/import-health.json"),
        MAX_MANIFEST_BYTES,
    )?;
    let health: serde_json::Value = serde_json::from_slice(&health_bytes).map_err(|error| {
        DistributionError::new(
            "rootfs_mgt_import_health_invalid",
            format!("normalized MGT import health is invalid JSON: {error}"),
        )
    })?;
    if compact_operator_json(&health)? != health_bytes {
        return Err(DistributionError::new(
            "rootfs_mgt_import_health_noncanonical",
            "normalized MGT import health is not canonical JSON",
        ));
    }
    verify_operator_self_hash(&health, "health_hash", "normalized MGT import health")?;
    let health_source_sha256 = health
        .get("source")
        .and_then(|source| source.get("source_hash"))
        .and_then(serde_json::Value::as_str);
    let normalized = health
        .get("schema_version")
        .and_then(serde_json::Value::as_str)
        == Some("structural-native-mgt-import-health.v1")
        && health.get("status").and_then(serde_json::Value::as_str) == Some("normalized")
        && health
            .get("blocker_count")
            .and_then(serde_json::Value::as_u64)
            == Some(0)
        && health
            .get("normalized_model")
            .is_some_and(serde_json::Value::is_object)
        && health_source_sha256 == Some(source_sha256.as_str());
    let health_sha256 = sha256_identity(&health_bytes);
    if !normalized
        || reported.mgt_source_sha256.as_deref() != Some(source_sha256.as_str())
        || reported.mgt_import_health_sha256.as_deref() != Some(health_sha256.as_str())
    {
        return Err(DistributionError::new(
            "rootfs_mgt_import_binding_mismatch",
            "original MGT source, normalized import health and durable session identities do not match",
        ));
    }
    Ok((source_sha256, health_sha256))
}

fn read_operator_cli_json(
    workspace: &Path,
    path: &Path,
    hash_field: &str,
    label: &str,
) -> Result<(serde_json::Value, String), DistributionError> {
    let parent = path.parent().ok_or_else(|| {
        DistributionError::new(
            "rootfs_operator_artifact_path_invalid",
            format!("{label} must have a parent directory"),
        )
    })?;
    if resolve_real_directory(parent, label)? != workspace {
        return Err(DistributionError::new(
            "rootfs_operator_artifact_path_invalid",
            format!("{label} must be a direct operator-workspace file"),
        ));
    }
    let bytes = read_bounded_regular_file(path, MAX_MANIFEST_BYTES)?;
    let canonical_bytes = bytes.strip_suffix(b"\n").ok_or_else(|| {
        DistributionError::new(
            "rootfs_operator_artifact_noncanonical",
            format!("{label} must be one canonical JSON line"),
        )
    })?;
    let value: serde_json::Value = serde_json::from_slice(canonical_bytes).map_err(|error| {
        DistributionError::new(
            "rootfs_operator_artifact_invalid",
            format!("{label} is invalid JSON: {error}"),
        )
    })?;
    if compact_operator_json(&value)? != canonical_bytes {
        return Err(DistributionError::new(
            "rootfs_operator_artifact_noncanonical",
            format!("{label} is not canonical JSON"),
        ));
    }
    verify_operator_self_hash(&value, hash_field, label)?;
    Ok((value, sha256_identity(&bytes)))
}

fn compact_operator_json(value: &serde_json::Value) -> Result<Vec<u8>, DistributionError> {
    structural_contracts::model_ir::canonicalize_model_ir_v2(value)
        .map(String::into_bytes)
        .map_err(|error| {
            DistributionError::new(
                "rootfs_operator_artifact_invalid",
                format!("operator artifact could not be encoded: {error}"),
            )
        })
}

fn verify_operator_self_hash(
    value: &serde_json::Value,
    hash_field: &str,
    label: &str,
) -> Result<(), DistributionError> {
    let mut unsigned = value.clone();
    let expected = unsigned
        .as_object_mut()
        .and_then(|object| object.remove(hash_field))
        .and_then(|item| item.as_str().map(ToOwned::to_owned))
        .ok_or_else(|| {
            DistributionError::new(
                "rootfs_operator_artifact_hash_missing",
                format!("{label} has no {hash_field}"),
            )
        })?;
    if expected != sha256_identity(&compact_operator_json(&unsigned)?) {
        return Err(DistributionError::new(
            "rootfs_operator_artifact_hash_mismatch",
            format!("{label} self-hash does not verify"),
        ));
    }
    Ok(())
}

fn require_operator_string<'a>(
    value: &'a serde_json::Value,
    field: &str,
    label: &str,
) -> Result<&'a str, DistributionError> {
    value
        .get(field)
        .and_then(serde_json::Value::as_str)
        .ok_or_else(|| {
            DistributionError::new(
                "rootfs_operator_artifact_contract_invalid",
                format!("{label} has no string {field}"),
            )
        })
}

fn optional_operator_string_matches(
    value: &serde_json::Value,
    field: &str,
    expected: Option<&str>,
) -> bool {
    match expected {
        Some(expected) => value.get(field).and_then(serde_json::Value::as_str) == Some(expected),
        None => value.get(field).is_none(),
    }
}

fn optional_export_artifact_matches(
    value: &serde_json::Value,
    role: &str,
    file: &str,
    expected_hash: Option<&str>,
) -> bool {
    let Some(artifacts) = value.get("artifacts").and_then(serde_json::Value::as_array) else {
        return false;
    };
    let matching = artifacts
        .iter()
        .filter(|artifact| artifact.get("role").and_then(serde_json::Value::as_str) == Some(role))
        .collect::<Vec<_>>();
    match expected_hash {
        Some(expected_hash) => {
            matching.len() == 1
                && matching[0].get("file").and_then(serde_json::Value::as_str) == Some(file)
                && matching[0]
                    .get("content_hash")
                    .and_then(serde_json::Value::as_str)
                    == Some(expected_hash)
        }
        None => matching.is_empty(),
    }
}

#[allow(clippy::too_many_lines)]
fn inspect_workbench_operator_surface(
    workspace: &Path,
    workbench_root: &Path,
    reported: &ReportedWorkbenchSummary,
    probe: &OperatorSurfaceProbe<'_>,
) -> Result<OperatorSurfaceSummary, DistributionError> {
    let root = resolve_workspace_child(workspace, workbench_root, "native Workbench")?;
    let (before, inspect_before_review_sha256) = read_operator_cli_json(
        workspace,
        probe.inspect_before_review,
        "view_hash",
        "pre-review Workbench inspection",
    )?;
    let (review_show, _) = read_operator_cli_json(
        workspace,
        probe.review_show,
        "review_hash",
        "reopened Workbench review",
    )?;
    let (after, inspect_after_review_sha256) = read_operator_cli_json(
        workspace,
        probe.inspect_after_review,
        "view_hash",
        "post-review Workbench inspection",
    )?;
    let (export, export_sha256) = read_operator_cli_json(
        workspace,
        probe.export,
        "export_hash",
        "Workbench handoff export",
    )?;

    let review_path = root.join("07-review/review.json");
    let review_bytes = read_bounded_regular_file(&review_path, MAX_MANIFEST_BYTES)?;
    let review: serde_json::Value = serde_json::from_slice(&review_bytes).map_err(|error| {
        DistributionError::new(
            "rootfs_operator_artifact_invalid",
            format!("durable Workbench review is invalid JSON: {error}"),
        )
    })?;
    if compact_operator_json(&review)? != review_bytes {
        return Err(DistributionError::new(
            "rootfs_operator_artifact_noncanonical",
            "durable Workbench review is not canonical JSON",
        ));
    }
    verify_operator_self_hash(&review, "review_hash", "durable Workbench review")?;
    if review != review_show {
        return Err(DistributionError::new(
            "rootfs_operator_review_reopen_mismatch",
            "reopened Workbench review differs from its durable artifact",
        ));
    }

    let before_valid = require_operator_string(&before, "schema_version", "pre-review inspection")?
        == "structural-native-workbench-view.v1"
        && require_operator_string(&before, "session_id", "pre-review inspection")?
            == reported.session_id
        && require_operator_string(&before, "import_kind", "pre-review inspection")?
            == probe.import_kind
        && optional_operator_string_matches(&before, "analysis_profile", probe.analysis_profile)
        && require_operator_string(&before, "next_action", "pre-review inspection")? == "review"
        && before.get("human_review") == Some(&serde_json::Value::Null);
    let review_hash = require_operator_string(&review, "review_hash", "durable review")?;
    let review_valid = require_operator_string(&review, "schema_version", "durable review")?
        == "structural-native-workbench-review.v1"
        && require_operator_string(&review, "session_id", "durable review")? == reported.session_id
        && require_operator_string(&review, "source_session_hash", "durable review")?
            == reported.session_hash
        && require_operator_string(&review, "decision", "durable review")? == "review"
        && require_operator_string(&review, "reviewer", "durable review")? == ROOTFS_REVIEWER
        && require_operator_string(&review, "comment", "durable review")? == ROOTFS_REVIEW_COMMENT
        && optional_operator_string_matches(&review, "analysis_profile", probe.analysis_profile)
        && require_operator_string(&review, "result_artifact_hash", "durable review")?
            == reported.result_ir_sha256
        && require_operator_string(&review, "comparison_artifact_hash", "durable review")?
            == reported.comparison_ir_sha256
        && require_operator_string(&review, "pdf_artifact_hash", "durable review")?
            == reported.report_pdf_sha256
        && optional_operator_string_matches(
            &review,
            "result_recovery_artifact_hash",
            reported.result_recovery_ir_sha256.as_deref(),
        )
        && optional_operator_string_matches(
            &review,
            "reaction_result_artifact_hash",
            reported.reaction_result_ir_sha256.as_deref(),
        )
        && optional_operator_string_matches(
            &review,
            "report_document_artifact_hash",
            reported.report_document_sha256.as_deref(),
        );
    let human_review = after
        .get("human_review")
        .and_then(serde_json::Value::as_object);
    let after_valid = require_operator_string(&after, "schema_version", "post-review inspection")?
        == "structural-native-workbench-view.v1"
        && require_operator_string(&after, "session_id", "post-review inspection")?
            == reported.session_id
        && require_operator_string(&after, "import_kind", "post-review inspection")?
            == probe.import_kind
        && optional_operator_string_matches(&after, "analysis_profile", probe.analysis_profile)
        && require_operator_string(&after, "next_action", "post-review inspection")? == "export"
        && human_review
            .and_then(|item| item.get("decision"))
            .and_then(serde_json::Value::as_str)
            == Some("review")
        && human_review
            .and_then(|item| item.get("automatically_inferred"))
            .and_then(serde_json::Value::as_bool)
            == Some(false);
    let export_valid = require_operator_string(&export, "schema_version", "handoff export")?
        == "structural-native-workbench-export.v1"
        && require_operator_string(&export, "session_id", "handoff export")? == reported.session_id
        && require_operator_string(&export, "decision", "handoff export")? == "review"
        && require_operator_string(&export, "review_hash", "handoff export")? == review_hash
        && optional_operator_string_matches(&export, "analysis_profile", probe.analysis_profile)
        && export
            .get("artifacts")
            .and_then(serde_json::Value::as_array)
            .is_some_and(|items| items.len() == probe.expected_export_artifact_count)
        && optional_export_artifact_matches(
            &export,
            "reaction_result_ir",
            "04-resume/reaction-result-ir.json",
            reported.reaction_result_ir_sha256.as_deref(),
        );
    if !before_valid || !review_valid || !after_valid || !export_valid {
        return Err(DistributionError::new(
            "rootfs_operator_artifact_contract_invalid",
            "Workbench inspect/review/export evidence weakens the exact isolated C5 contract",
        ));
    }
    Ok(OperatorSurfaceSummary {
        decision: "review".to_owned(),
        inspect_before_review_sha256,
        review_sha256: sha256_identity(&review_bytes),
        inspect_after_review_sha256,
        export_sha256,
    })
}

fn inspect_workbench_read_only_surfaces(
    workspace: &Path,
    catalog_path: &Path,
    evidence_path: &Path,
) -> Result<ReadOnlySurfaceSummary, DistributionError> {
    let (catalog, catalog_sha256) = read_operator_cli_json(
        workspace,
        catalog_path,
        "catalog_view_hash",
        "Workbench benchmark catalog view",
    )?;
    let catalog_valid = validate_catalog_surface_view(&catalog)?;
    let (evidence, evidence_sha256) = read_operator_cli_json(
        workspace,
        evidence_path,
        "evidence_view_hash",
        "Workbench evidence bundle view",
    )?;
    let evidence_valid = validate_evidence_surface_view(&evidence)?;
    if !catalog_valid || !evidence_valid {
        return Err(DistributionError::new(
            "rootfs_read_only_surface_contract_invalid",
            "Workbench catalog/evidence output weakens the exact isolated C5 contract",
        ));
    }
    Ok(ReadOnlySurfaceSummary {
        catalog_sha256,
        evidence_sha256,
    })
}

fn validate_catalog_surface_view(catalog: &serde_json::Value) -> Result<bool, DistributionError> {
    let catalog_summary = catalog
        .get("summary")
        .and_then(serde_json::Value::as_object);
    let catalog_filters = catalog
        .get("filters")
        .and_then(serde_json::Value::as_object);
    let catalog_cases = catalog.get("cases").and_then(serde_json::Value::as_array);
    Ok(
        require_operator_string(catalog, "schema_version", "catalog view")?
            == "structural-native-benchmark-catalog-view.v1"
            && catalog_summary
                .and_then(|summary| summary.get("total_case_count"))
                .and_then(serde_json::Value::as_u64)
                == Some(26)
            && catalog_summary
                .and_then(|summary| summary.get("matched_case_count"))
                .and_then(serde_json::Value::as_u64)
                == Some(4)
            && catalog_summary
                .and_then(|summary| summary.get("runnable_count"))
                .and_then(serde_json::Value::as_u64)
                == Some(0)
            && catalog_filters
                .and_then(|filters| filters.get("truth_class"))
                .and_then(serde_json::Value::as_str)
                == Some("geometry_only")
            && catalog_filters
                .and_then(|filters| filters.get("size_class"))
                .and_then(serde_json::Value::as_str)
                == Some("large")
            && catalog_cases.is_some_and(|cases| {
                cases.len() == 4
                    && cases.iter().all(|case| {
                        case.get("truthClass").and_then(serde_json::Value::as_str)
                            == Some("geometry_only")
                            && case.get("accuracyComparable")
                                == Some(&serde_json::Value::Bool(false))
                            && case.get("runCommand") == Some(&serde_json::Value::Null)
                    })
            }),
    )
}

fn validate_evidence_surface_view(evidence: &serde_json::Value) -> Result<bool, DistributionError> {
    let evidence_summary = evidence
        .get("summary")
        .and_then(serde_json::Value::as_object);
    let evidence_artifacts = evidence
        .get("artifacts")
        .and_then(serde_json::Value::as_array);
    Ok(
        require_operator_string(evidence, "schema_version", "evidence bundle view")?
            == "structural-native-evidence-bundle-view.v1"
            && evidence.get("commit_mismatch") == Some(&serde_json::Value::Bool(false))
            && evidence.get("bundle_consistent") == Some(&serde_json::Value::Bool(true))
            && evidence_summary
                .and_then(|summary| summary.get("artifact_count"))
                .and_then(serde_json::Value::as_u64)
                == Some(3)
            && evidence_summary
                .and_then(|summary| summary.get("ready_count"))
                .and_then(serde_json::Value::as_u64)
                == Some(1)
            && evidence_summary
                .and_then(|summary| summary.get("blocked_count"))
                .and_then(serde_json::Value::as_u64)
                == Some(1)
            && evidence_summary
                .and_then(|summary| summary.get("unavailable_count"))
                .and_then(serde_json::Value::as_u64)
                == Some(1)
            && evidence_artifacts.is_some_and(|artifacts| {
                artifacts.len() == 3
                    && ["ready", "blocked", "unavailable"]
                        .iter()
                        .zip(artifacts)
                        .all(|(expected, artifact)| {
                            artifact.get("read_only") == Some(&serde_json::Value::Bool(true))
                                && artifact
                                    .get("facts")
                                    .and_then(|facts| facts.get("gate_state"))
                                    .and_then(serde_json::Value::as_str)
                                    == Some(*expected)
                        })
            }),
    )
}

fn require_manifest_entry_hash(
    manifest: &DistributionManifestV1,
    path: &str,
    actual_hash: &str,
) -> Result<(), DistributionError> {
    let expected = manifest
        .files
        .iter()
        .find(|entry| entry.path == path)
        .map(|entry| entry.sha256.as_str())
        .ok_or_else(|| {
            DistributionError::new(
                "rootfs_manifest_entry_missing",
                format!("verified bundle does not contain {path}"),
            )
        })?;
    if expected != actual_hash {
        return Err(DistributionError::new(
            "rootfs_executable_hash_mismatch",
            format!("executing payload hash differs from the bundle for {path}"),
        ));
    }
    Ok(())
}

fn require_read_only_mount(directory: &Path, label: &str) -> Result<i32, DistributionError> {
    ensure_directory(directory, label)?;
    let probe = unique_path(directory, ".structural-read-only-probe");
    match OpenOptions::new().create_new(true).write(true).open(&probe) {
        Ok(file) => {
            drop(file);
            let _ = fs::remove_file(&probe);
            Err(DistributionError::new(
                "rootfs_write_allowed",
                format!("{label} unexpectedly accepted a write"),
            ))
        }
        Err(error) if error.raw_os_error() == Some(libc::EROFS) => Ok(libc::EROFS),
        Err(error) => Err(DistributionError::new(
            "rootfs_read_only_mount_unproven",
            format!("{label} write failed without EROFS: {error}"),
        )),
    }
}

fn verify_workspace_write(workspace: &Path) -> Result<(), DistributionError> {
    let probe = unique_path(workspace, ".structural-workspace-probe");
    write_new_file(&probe, b"structural-native-workspace-probe\n", 0o600)?;
    fs::remove_file(&probe)
        .map_err(|error| io_error("rootfs_workspace_probe_remove_failed", error))?;
    sync_directory(workspace)
}

struct LinuxProcessIdentity {
    user_id: u32,
    group_id: u32,
}

#[cfg(target_os = "linux")]
fn linux_effective_ids() -> LinuxProcessIdentity {
    // SAFETY: `geteuid` and `getegid` take no pointers and have no preconditions.
    let (uid, gid) = unsafe { (libc::geteuid(), libc::getegid()) };
    LinuxProcessIdentity {
        user_id: uid,
        group_id: gid,
    }
}

#[cfg(not(target_os = "linux"))]
fn linux_effective_ids() -> LinuxProcessIdentity {
    LinuxProcessIdentity {
        user_id: 0,
        group_id: 0,
    }
}

fn read_linux_virtual_file(path: &Path) -> Result<String, DistributionError> {
    let file = File::open(path).map_err(|error| io_error("rootfs_proc_open_failed", error))?;
    let mut bytes = Vec::new();
    file.take(1024 * 1024)
        .read_to_end(&mut bytes)
        .map_err(|error| io_error("rootfs_proc_read_failed", error))?;
    if bytes.len() == 1024 * 1024 {
        return Err(DistributionError::new(
            "rootfs_proc_size_exceeded",
            "Linux network inventory exceeded the diagnostic limit",
        ));
    }
    String::from_utf8(bytes).map_err(|_| {
        DistributionError::new(
            "rootfs_proc_encoding_invalid",
            "Linux network inventory must be UTF-8",
        )
    })
}

fn linux_network_interfaces() -> Result<Vec<String>, DistributionError> {
    let text = read_linux_virtual_file(Path::new("/proc/net/dev"))?;
    let mut interfaces = text
        .lines()
        .skip(2)
        .filter_map(|line| line.split_once(':').map(|(name, _)| name.trim().to_owned()))
        .filter(|name| !name.is_empty())
        .collect::<Vec<_>>();
    interfaces.sort();
    interfaces.dedup();
    Ok(interfaces)
}

fn linux_ipv4_route_count() -> Result<u64, DistributionError> {
    let text = read_linux_virtual_file(Path::new("/proc/net/route"))?;
    let count = text
        .lines()
        .filter(|line| {
            let trimmed = line.trim();
            !trimmed.is_empty() && !trimmed.starts_with("Iface")
        })
        .count();
    u64::try_from(count).map_err(|_| {
        DistributionError::new(
            "rootfs_network_inventory_overflow",
            "IPv4 route count overflowed",
        )
    })
}

#[cfg(test)]
fn seal_rootfs_isolation_evidence_v9(
    evidence: RootfsIsolationEvidenceV9,
) -> Result<RootfsIsolationReceiptV9, DistributionError> {
    let receipt_hash = sha256_identity(&canonical_json(&evidence)?);
    Ok(RootfsIsolationReceiptV9 {
        schema_version: ROOTFS_RECEIPT_SCHEMA_VERSION_V9.to_owned(),
        evidence,
        receipt_hash,
    })
}

#[cfg(test)]
fn seal_rootfs_isolation_evidence_v10(
    evidence: RootfsIsolationEvidenceV10,
) -> Result<RootfsIsolationReceiptV10, DistributionError> {
    let receipt_hash = sha256_identity(&canonical_json(&evidence)?);
    Ok(RootfsIsolationReceiptV10 {
        schema_version: ROOTFS_RECEIPT_SCHEMA_VERSION_V10.to_owned(),
        evidence,
        receipt_hash,
    })
}

#[cfg(test)]
fn seal_rootfs_isolation_evidence_v11(
    evidence: RootfsIsolationEvidenceV11,
) -> Result<RootfsIsolationReceiptV11, DistributionError> {
    let receipt_hash = sha256_identity(&canonical_json(&evidence)?);
    Ok(RootfsIsolationReceiptV11 {
        schema_version: ROOTFS_RECEIPT_SCHEMA_VERSION_V11.to_owned(),
        evidence,
        receipt_hash,
    })
}

#[cfg(test)]
fn seal_rootfs_isolation_evidence_v12(
    evidence: RootfsIsolationEvidenceV12,
) -> Result<RootfsIsolationReceiptV12, DistributionError> {
    let receipt_hash = sha256_identity(&canonical_json(&evidence)?);
    Ok(RootfsIsolationReceiptV12 {
        schema_version: ROOTFS_RECEIPT_SCHEMA_VERSION_V12.to_owned(),
        evidence,
        receipt_hash,
    })
}

fn seal_rootfs_isolation_evidence(
    evidence: RootfsIsolationEvidenceV13,
) -> Result<RootfsIsolationReceiptV13, DistributionError> {
    let receipt_hash = sha256_identity(&canonical_json(&evidence)?);
    Ok(RootfsIsolationReceiptV13 {
        schema_version: ROOTFS_RECEIPT_SCHEMA_VERSION.to_owned(),
        evidence,
        receipt_hash,
    })
}

fn validate_rootfs_isolation_evidence_v1(
    evidence: &RootfsIsolationEvidenceV1,
) -> Result<(), DistributionError> {
    let exact_contract = evidence.authority == ROOTFS_RECEIPT_AUTHORITY
        && evidence.claim_boundary == ROOTFS_RECEIPT_CLAIM_BOUNDARY_V1
        && evidence.isolation_technology == ROOTFS_ISOLATION_TECHNOLOGY
        && evidence.runtime_uid == ROOTFS_RUNTIME_UID
        && evidence.runtime_gid == ROOTFS_RUNTIME_GID
        && evidence.network_interfaces.len() == 1
        && evidence.network_interfaces[0] == "lo"
        && evidence.ipv4_route_count == 0
        && evidence.rootfs_write_errno == libc::EROFS
        && evidence.payload_write_errno == libc::EROFS
        && evidence.workspace_write_passed
        && evidence.path == ROOTFS_EMPTY_PATH
        && evidence.python_lookup_count == 0
        && evidence.node_lookup_count == 0
        && evidence
            .workbench_version
            .starts_with("structural-workbench ")
        && evidence.workbench_stage == "reported"
        && evidence.workbench_terminal_status == "completed"
        && evidence.workbench_comparison_passed
        && evidence.mgt_workbench_stage == "reported"
        && evidence.mgt_workbench_terminal_status == "completed"
        && evidence.mgt_workbench_comparison_passed
        && !evidence.container_image_built
        && !evidence.customer_image_receipt;
    if !exact_contract {
        return Err(DistributionError::new(
            "rootfs_receipt_contract_invalid",
            "rootfs v1 receipt weakens or exceeds its frozen local diagnostic contract",
        ));
    }
    validate_release_id(&evidence.release_id)?;
    for (value, label) in [
        (&evidence.source_sha256, "rootfs v1 source SHA-256"),
        (&evidence.bundle_manifest_hash, "rootfs v1 manifest hash"),
        (
            &evidence.bundle_manifest_file_sha256,
            "rootfs v1 manifest file SHA-256",
        ),
        (&evidence.installer_sha256, "rootfs v1 installer SHA-256"),
        (&evidence.workbench_sha256, "rootfs v1 Workbench SHA-256"),
        (&evidence.result_ir_sha256, "rootfs v1 ResultIR SHA-256"),
        (&evidence.report_pdf_sha256, "rootfs v1 report SHA-256"),
        (&evidence.mgt_source_sha256, "rootfs v1 MGT source SHA-256"),
        (
            &evidence.mgt_import_health_sha256,
            "rootfs v1 MGT import health SHA-256",
        ),
        (
            &evidence.mgt_result_ir_sha256,
            "rootfs v1 MGT ResultIR SHA-256",
        ),
        (
            &evidence.mgt_report_pdf_sha256,
            "rootfs v1 MGT report SHA-256",
        ),
    ] {
        validate_sha256_identity(value, label)?;
    }
    Ok(())
}

fn validate_rootfs_isolation_evidence_v2(
    evidence: &RootfsIsolationEvidenceV2,
) -> Result<(), DistributionError> {
    let exact_contract = evidence.authority == ROOTFS_RECEIPT_AUTHORITY
        && evidence.claim_boundary == ROOTFS_RECEIPT_CLAIM_BOUNDARY_V2
        && evidence.isolation_technology == ROOTFS_ISOLATION_TECHNOLOGY
        && evidence.runtime_uid == ROOTFS_RUNTIME_UID
        && evidence.runtime_gid == ROOTFS_RUNTIME_GID
        && evidence.network_interfaces.len() == 1
        && evidence.network_interfaces[0] == "lo"
        && evidence.ipv4_route_count == 0
        && evidence.rootfs_write_errno == libc::EROFS
        && evidence.payload_write_errno == libc::EROFS
        && evidence.workspace_write_passed
        && evidence.path == ROOTFS_EMPTY_PATH
        && evidence.python_lookup_count == 0
        && evidence.node_lookup_count == 0
        && evidence
            .workbench_version
            .starts_with("structural-workbench ")
        && evidence.workbench_stage == "reported"
        && evidence.workbench_terminal_status == "completed"
        && evidence.workbench_comparison_passed
        && evidence.workbench_operator_surface_passed
        && evidence.workbench_review_decision == "review"
        && evidence.mgt_workbench_stage == "reported"
        && evidence.mgt_workbench_terminal_status == "completed"
        && evidence.mgt_workbench_comparison_passed
        && evidence.mgt_workbench_operator_surface_passed
        && evidence.mgt_workbench_review_decision == "review"
        && !evidence.container_image_built
        && !evidence.customer_image_receipt;
    if !exact_contract {
        return Err(DistributionError::new(
            "rootfs_receipt_contract_invalid",
            "rootfs receipt weakens or exceeds the exact local diagnostic contract",
        ));
    }
    validate_release_id(&evidence.release_id)?;
    for (value, label) in [
        (&evidence.source_sha256, "rootfs source SHA-256"),
        (&evidence.bundle_manifest_hash, "rootfs manifest hash"),
        (
            &evidence.bundle_manifest_file_sha256,
            "rootfs manifest file SHA-256",
        ),
        (&evidence.installer_sha256, "rootfs installer SHA-256"),
        (&evidence.workbench_sha256, "rootfs Workbench SHA-256"),
        (&evidence.result_ir_sha256, "rootfs ResultIR SHA-256"),
        (&evidence.report_pdf_sha256, "rootfs report SHA-256"),
        (
            &evidence.workbench_inspect_before_review_sha256,
            "rootfs Workbench pre-review inspection SHA-256",
        ),
        (
            &evidence.workbench_review_sha256,
            "rootfs Workbench review SHA-256",
        ),
        (
            &evidence.workbench_inspect_after_review_sha256,
            "rootfs Workbench post-review inspection SHA-256",
        ),
        (
            &evidence.workbench_export_sha256,
            "rootfs Workbench export SHA-256",
        ),
        (&evidence.mgt_source_sha256, "rootfs MGT source SHA-256"),
        (
            &evidence.mgt_import_health_sha256,
            "rootfs MGT import health SHA-256",
        ),
        (
            &evidence.mgt_result_ir_sha256,
            "rootfs MGT ResultIR SHA-256",
        ),
        (&evidence.mgt_report_pdf_sha256, "rootfs MGT report SHA-256"),
        (
            &evidence.mgt_workbench_inspect_before_review_sha256,
            "rootfs MGT Workbench pre-review inspection SHA-256",
        ),
        (
            &evidence.mgt_workbench_review_sha256,
            "rootfs MGT Workbench review SHA-256",
        ),
        (
            &evidence.mgt_workbench_inspect_after_review_sha256,
            "rootfs MGT Workbench post-review inspection SHA-256",
        ),
        (
            &evidence.mgt_workbench_export_sha256,
            "rootfs MGT Workbench export SHA-256",
        ),
    ] {
        validate_sha256_identity(value, label)?;
    }
    Ok(())
}

fn validate_rootfs_isolation_evidence_v3(
    evidence: &RootfsIsolationEvidenceV3,
) -> Result<(), DistributionError> {
    if evidence.claim_boundary != ROOTFS_RECEIPT_CLAIM_BOUNDARY_V3
        || !evidence.workbench_catalog_surface_passed
        || !evidence.workbench_evidence_surface_passed
    {
        return Err(DistributionError::new(
            "rootfs_receipt_contract_invalid",
            "rootfs v3 receipt weakens or exceeds the exact local diagnostic contract",
        ));
    }
    validate_sha256_identity(
        &evidence.workbench_catalog_sha256,
        "rootfs Workbench catalog view SHA-256",
    )?;
    validate_sha256_identity(
        &evidence.workbench_evidence_sha256,
        "rootfs Workbench evidence view SHA-256",
    )?;

    let mut prior = serde_json::to_value(evidence).map_err(|error| {
        DistributionError::new(
            "rootfs_receipt_contract_invalid",
            format!("rootfs v3 evidence could not be projected: {error}"),
        )
    })?;
    let object = prior.as_object_mut().ok_or_else(|| {
        DistributionError::new(
            "rootfs_receipt_contract_invalid",
            "rootfs v3 evidence projection is not an object",
        )
    })?;
    object.insert(
        "claim_boundary".to_owned(),
        serde_json::Value::String(ROOTFS_RECEIPT_CLAIM_BOUNDARY_V2.to_owned()),
    );
    for field in [
        "workbench_catalog_surface_passed",
        "workbench_catalog_sha256",
        "workbench_evidence_surface_passed",
        "workbench_evidence_sha256",
    ] {
        if object.remove(field).is_none() {
            return Err(DistributionError::new(
                "rootfs_receipt_contract_invalid",
                "rootfs v3 evidence projection is incomplete",
            ));
        }
    }
    let prior: RootfsIsolationEvidenceV2 = serde_json::from_value(prior).map_err(|error| {
        DistributionError::new(
            "rootfs_receipt_contract_invalid",
            format!("rootfs v3 evidence does not preserve v2: {error}"),
        )
    })?;
    validate_rootfs_isolation_evidence_v2(&prior)
}

#[allow(clippy::too_many_lines)]
fn validate_rootfs_isolation_evidence_v4(
    evidence: &RootfsIsolationEvidenceV4,
) -> Result<(), DistributionError> {
    if evidence.claim_boundary != ROOTFS_RECEIPT_CLAIM_BOUNDARY_V4
        || evidence.model_ir_linear_workbench_stage != "reported"
        || evidence.model_ir_linear_workbench_terminal_status != "completed"
        || !evidence.model_ir_linear_workbench_comparison_passed
        || !evidence.model_ir_linear_workbench_operator_surface_passed
        || evidence.model_ir_linear_workbench_review_decision != "review"
    {
        return Err(DistributionError::new(
            "rootfs_receipt_contract_invalid",
            "rootfs v4 receipt weakens or exceeds the exact local diagnostic contract",
        ));
    }
    for (value, label) in [
        (
            &evidence.model_ir_linear_result_ir_sha256,
            "rootfs ModelIR linear ResultIR SHA-256",
        ),
        (
            &evidence.model_ir_linear_result_recovery_ir_sha256,
            "rootfs ModelIR linear recovery SHA-256",
        ),
        (
            &evidence.model_ir_linear_comparison_ir_sha256,
            "rootfs ModelIR linear comparison SHA-256",
        ),
        (
            &evidence.model_ir_linear_report_pdf_sha256,
            "rootfs ModelIR linear PDF SHA-256",
        ),
        (
            &evidence.model_ir_linear_report_document_sha256,
            "rootfs ModelIR linear report document SHA-256",
        ),
        (
            &evidence.model_ir_linear_pdf_receipt_sha256,
            "rootfs ModelIR linear PDF receipt SHA-256",
        ),
        (
            &evidence.model_ir_linear_report_receipt_sha256,
            "rootfs ModelIR linear report receipt SHA-256",
        ),
        (
            &evidence.model_ir_linear_workbench_inspect_before_review_sha256,
            "rootfs ModelIR linear pre-review inspection SHA-256",
        ),
        (
            &evidence.model_ir_linear_workbench_review_sha256,
            "rootfs ModelIR linear review SHA-256",
        ),
        (
            &evidence.model_ir_linear_workbench_inspect_after_review_sha256,
            "rootfs ModelIR linear post-review inspection SHA-256",
        ),
        (
            &evidence.model_ir_linear_workbench_export_sha256,
            "rootfs ModelIR linear export SHA-256",
        ),
    ] {
        validate_sha256_identity(value, label)?;
    }

    let mut prior = serde_json::to_value(evidence).map_err(|error| {
        DistributionError::new(
            "rootfs_receipt_contract_invalid",
            format!("rootfs v4 evidence could not be projected: {error}"),
        )
    })?;
    let object = prior.as_object_mut().ok_or_else(|| {
        DistributionError::new(
            "rootfs_receipt_contract_invalid",
            "rootfs v4 evidence projection is not an object",
        )
    })?;
    object.insert(
        "claim_boundary".to_owned(),
        serde_json::Value::String(ROOTFS_RECEIPT_CLAIM_BOUNDARY_V3.to_owned()),
    );
    for field in [
        "model_ir_linear_workbench_stage",
        "model_ir_linear_workbench_terminal_status",
        "model_ir_linear_workbench_comparison_passed",
        "model_ir_linear_workbench_operator_surface_passed",
        "model_ir_linear_workbench_review_decision",
        "model_ir_linear_result_ir_sha256",
        "model_ir_linear_result_recovery_ir_sha256",
        "model_ir_linear_comparison_ir_sha256",
        "model_ir_linear_report_pdf_sha256",
        "model_ir_linear_report_document_sha256",
        "model_ir_linear_pdf_receipt_sha256",
        "model_ir_linear_report_receipt_sha256",
        "model_ir_linear_workbench_inspect_before_review_sha256",
        "model_ir_linear_workbench_review_sha256",
        "model_ir_linear_workbench_inspect_after_review_sha256",
        "model_ir_linear_workbench_export_sha256",
    ] {
        if object.remove(field).is_none() {
            return Err(DistributionError::new(
                "rootfs_receipt_contract_invalid",
                "rootfs v4 evidence projection is incomplete",
            ));
        }
    }
    let prior: RootfsIsolationEvidenceV3 = serde_json::from_value(prior).map_err(|error| {
        DistributionError::new(
            "rootfs_receipt_contract_invalid",
            format!("rootfs v4 evidence does not preserve v3: {error}"),
        )
    })?;
    validate_rootfs_isolation_evidence_v3(&prior)
}

fn validate_rootfs_isolation_evidence_v5(
    evidence: &RootfsIsolationEvidenceV5,
) -> Result<(), DistributionError> {
    if evidence.prior.claim_boundary != ROOTFS_RECEIPT_CLAIM_BOUNDARY_V5
        || !evidence.model_ir_linear_localized_pdf_surface_passed
        || evidence.model_ir_linear_localized_pdf_en_us_sha256
            == evidence.model_ir_linear_localized_pdf_ko_kr_sha256
    {
        return Err(DistributionError::new(
            "rootfs_receipt_contract_invalid",
            "rootfs v5 receipt weakens or exceeds the exact localized-PDF diagnostic contract",
        ));
    }
    for (value, label) in [
        (
            &evidence.model_ir_linear_localized_pdf_en_us_sha256,
            "rootfs ModelIR linear localized en-US PDF SHA-256",
        ),
        (
            &evidence.model_ir_linear_localized_pdf_ko_kr_sha256,
            "rootfs ModelIR linear localized ko-KR PDF SHA-256",
        ),
        (
            &evidence.model_ir_linear_localized_pdf_en_us_receipt_sha256,
            "rootfs ModelIR linear localized en-US receipt SHA-256",
        ),
        (
            &evidence.model_ir_linear_localized_pdf_ko_kr_receipt_sha256,
            "rootfs ModelIR linear localized ko-KR receipt SHA-256",
        ),
    ] {
        validate_sha256_identity(value, label)?;
    }
    let mut prior = evidence.prior.clone();
    ROOTFS_RECEIPT_CLAIM_BOUNDARY_V4.clone_into(&mut prior.claim_boundary);
    validate_rootfs_isolation_evidence_v4(&prior)
}

fn validate_rootfs_isolation_evidence_v6(
    evidence: &RootfsIsolationEvidenceV6,
) -> Result<(), DistributionError> {
    if evidence.prior.prior.claim_boundary != ROOTFS_RECEIPT_CLAIM_BOUNDARY_V6
        || evidence.mgt_model_ir_linear_workbench_stage != "reported"
        || evidence.mgt_model_ir_linear_workbench_terminal_status != "completed"
        || !evidence.mgt_model_ir_linear_workbench_comparison_passed
        || !evidence.mgt_model_ir_linear_workbench_operator_surface_passed
        || evidence.mgt_model_ir_linear_workbench_review_decision != "review"
    {
        return Err(DistributionError::new(
            "rootfs_receipt_contract_invalid",
            "rootfs v6 receipt weakens or exceeds the exact normalized-MGT linear diagnostic contract",
        ));
    }
    for (value, label) in [
        (
            &evidence.mgt_model_ir_linear_source_sha256,
            "rootfs normalized-MGT linear source SHA-256",
        ),
        (
            &evidence.mgt_model_ir_linear_import_health_sha256,
            "rootfs normalized-MGT linear import-health SHA-256",
        ),
        (
            &evidence.mgt_model_ir_linear_result_ir_sha256,
            "rootfs normalized-MGT linear ResultIR SHA-256",
        ),
        (
            &evidence.mgt_model_ir_linear_result_recovery_ir_sha256,
            "rootfs normalized-MGT linear recovery SHA-256",
        ),
        (
            &evidence.mgt_model_ir_linear_comparison_ir_sha256,
            "rootfs normalized-MGT linear comparison SHA-256",
        ),
        (
            &evidence.mgt_model_ir_linear_report_pdf_sha256,
            "rootfs normalized-MGT linear PDF SHA-256",
        ),
        (
            &evidence.mgt_model_ir_linear_report_document_sha256,
            "rootfs normalized-MGT linear report document SHA-256",
        ),
        (
            &evidence.mgt_model_ir_linear_pdf_receipt_sha256,
            "rootfs normalized-MGT linear PDF receipt SHA-256",
        ),
        (
            &evidence.mgt_model_ir_linear_report_receipt_sha256,
            "rootfs normalized-MGT linear report receipt SHA-256",
        ),
        (
            &evidence.mgt_model_ir_linear_workbench_inspect_before_review_sha256,
            "rootfs normalized-MGT linear pre-review inspection SHA-256",
        ),
        (
            &evidence.mgt_model_ir_linear_workbench_review_sha256,
            "rootfs normalized-MGT linear review SHA-256",
        ),
        (
            &evidence.mgt_model_ir_linear_workbench_inspect_after_review_sha256,
            "rootfs normalized-MGT linear post-review inspection SHA-256",
        ),
        (
            &evidence.mgt_model_ir_linear_workbench_export_sha256,
            "rootfs normalized-MGT linear export SHA-256",
        ),
    ] {
        validate_sha256_identity(value, label)?;
    }

    let mut prior = evidence.prior.clone();
    ROOTFS_RECEIPT_CLAIM_BOUNDARY_V5.clone_into(&mut prior.prior.claim_boundary);
    validate_rootfs_isolation_evidence_v5(&prior)
}

fn validate_rootfs_isolation_evidence_v7(
    evidence: &RootfsIsolationEvidenceV7,
) -> Result<(), DistributionError> {
    if evidence.prior.prior.prior.claim_boundary != ROOTFS_RECEIPT_CLAIM_BOUNDARY_V7 {
        return Err(DistributionError::new(
            "rootfs_receipt_contract_invalid",
            "rootfs v7 receipt weakens or exceeds the exact constrained-reaction diagnostic contract",
        ));
    }
    for (value, label) in [
        (
            &evidence.model_ir_linear_reaction_result_ir_sha256,
            "rootfs ModelIR linear constrained-reaction ResultIR SHA-256",
        ),
        (
            &evidence.mgt_model_ir_linear_reaction_result_ir_sha256,
            "rootfs normalized-MGT linear constrained-reaction ResultIR SHA-256",
        ),
    ] {
        validate_sha256_identity(value, label)?;
    }

    let mut prior = evidence.prior.clone();
    ROOTFS_RECEIPT_CLAIM_BOUNDARY_V6.clone_into(&mut prior.prior.prior.claim_boundary);
    validate_rootfs_isolation_evidence_v6(&prior)
}

fn validate_rootfs_isolation_evidence_v8(
    evidence: &RootfsIsolationEvidenceV8,
) -> Result<(), DistributionError> {
    if evidence.prior.prior.prior.prior.claim_boundary != ROOTFS_RECEIPT_CLAIM_BOUNDARY_V8
        || !evidence.model_ir_linear_reaction_view_surface_passed
        || !evidence.mgt_model_ir_linear_reaction_view_surface_passed
        || !evidence.workbench_reaction_view_wrong_profile_rejected
        || evidence.model_ir_linear_reaction_view_en_us_sha256
            == evidence.model_ir_linear_reaction_view_ko_kr_sha256
        || evidence.model_ir_linear_reaction_view_en_us_sha256
            == evidence.model_ir_linear_reaction_view_window_sha256
        || evidence.mgt_model_ir_linear_reaction_view_en_us_sha256
            == evidence.mgt_model_ir_linear_reaction_view_ko_kr_sha256
        || evidence.model_ir_linear_reaction_view_en_us_sha256
            == evidence.mgt_model_ir_linear_reaction_view_en_us_sha256
    {
        return Err(DistributionError::new(
            "rootfs_receipt_contract_invalid",
            "rootfs v8 receipt weakens or exceeds the exact constrained-reaction view diagnostic contract",
        ));
    }
    for (value, label) in [
        (
            &evidence.model_ir_linear_reaction_view_en_us_sha256,
            "rootfs ModelIR linear en-US reaction view SHA-256",
        ),
        (
            &evidence.model_ir_linear_reaction_view_ko_kr_sha256,
            "rootfs ModelIR linear ko-KR reaction view SHA-256",
        ),
        (
            &evidence.model_ir_linear_reaction_view_window_sha256,
            "rootfs ModelIR linear bounded reaction view SHA-256",
        ),
        (
            &evidence.mgt_model_ir_linear_reaction_view_en_us_sha256,
            "rootfs normalized-MGT linear en-US reaction view SHA-256",
        ),
        (
            &evidence.mgt_model_ir_linear_reaction_view_ko_kr_sha256,
            "rootfs normalized-MGT linear ko-KR reaction view SHA-256",
        ),
    ] {
        validate_sha256_identity(value, label)?;
    }

    let mut prior = evidence.prior.clone();
    ROOTFS_RECEIPT_CLAIM_BOUNDARY_V7.clone_into(&mut prior.prior.prior.prior.claim_boundary);
    validate_rootfs_isolation_evidence_v7(&prior)
}

fn validate_rootfs_isolation_evidence_v9(
    evidence: &RootfsIsolationEvidenceV9,
) -> Result<(), DistributionError> {
    if evidence.prior.prior.prior.prior.prior.claim_boundary != ROOTFS_RECEIPT_CLAIM_BOUNDARY_V9
        || !evidence.model_ir_linear_reaction_audit_surface_passed
        || !evidence.mgt_model_ir_linear_reaction_audit_surface_passed
        || !evidence.workbench_reaction_audit_wrong_profile_rejected
        || evidence.model_ir_linear_reaction_audit_en_us_sha256
            == evidence.model_ir_linear_reaction_audit_ko_kr_sha256
        || evidence.mgt_model_ir_linear_reaction_audit_en_us_sha256
            == evidence.mgt_model_ir_linear_reaction_audit_ko_kr_sha256
        || evidence.model_ir_linear_reaction_audit_en_us_sha256
            == evidence.mgt_model_ir_linear_reaction_audit_en_us_sha256
    {
        return Err(DistributionError::new(
            "rootfs_receipt_contract_invalid",
            "rootfs v9 receipt weakens or exceeds the exact algebraic reaction-audit diagnostic contract",
        ));
    }
    for (value, label) in [
        (
            &evidence.model_ir_linear_reaction_audit_en_us_sha256,
            "rootfs ModelIR linear en-US reaction audit SHA-256",
        ),
        (
            &evidence.model_ir_linear_reaction_audit_ko_kr_sha256,
            "rootfs ModelIR linear ko-KR reaction audit SHA-256",
        ),
        (
            &evidence.mgt_model_ir_linear_reaction_audit_en_us_sha256,
            "rootfs normalized-MGT linear en-US reaction audit SHA-256",
        ),
        (
            &evidence.mgt_model_ir_linear_reaction_audit_ko_kr_sha256,
            "rootfs normalized-MGT linear ko-KR reaction audit SHA-256",
        ),
    ] {
        validate_sha256_identity(value, label)?;
    }

    let mut prior = evidence.prior.clone();
    ROOTFS_RECEIPT_CLAIM_BOUNDARY_V8.clone_into(&mut prior.prior.prior.prior.prior.claim_boundary);
    validate_rootfs_isolation_evidence_v8(&prior)
}

fn validate_rootfs_isolation_evidence_v10(
    evidence: &RootfsIsolationEvidenceV10,
) -> Result<(), DistributionError> {
    let identities = [
        evidence
            .model_ir_linear_nodal_displacement_view_en_us_sha256
            .as_str(),
        evidence
            .model_ir_linear_nodal_displacement_view_ko_kr_sha256
            .as_str(),
        evidence
            .model_ir_linear_nodal_displacement_view_window_sha256
            .as_str(),
        evidence
            .mgt_model_ir_linear_nodal_displacement_view_en_us_sha256
            .as_str(),
        evidence
            .mgt_model_ir_linear_nodal_displacement_view_ko_kr_sha256
            .as_str(),
    ]
    .into_iter()
    .collect::<BTreeSet<_>>();
    if evidence.prior.prior.prior.prior.prior.prior.claim_boundary
        != ROOTFS_RECEIPT_CLAIM_BOUNDARY_V10
        || !evidence.model_ir_linear_nodal_displacement_view_surface_passed
        || !evidence.mgt_model_ir_linear_nodal_displacement_view_surface_passed
        || !evidence.workbench_nodal_displacement_view_wrong_profile_rejected
        || identities.len() != 5
    {
        return Err(DistributionError::new(
            "rootfs_receipt_contract_invalid",
            "rootfs v10 receipt weakens or exceeds the exact bounded nodal-displacement-view diagnostic contract",
        ));
    }
    for (value, label) in [
        (
            &evidence.model_ir_linear_nodal_displacement_view_en_us_sha256,
            "rootfs ModelIR linear en-US nodal displacement view SHA-256",
        ),
        (
            &evidence.model_ir_linear_nodal_displacement_view_ko_kr_sha256,
            "rootfs ModelIR linear ko-KR nodal displacement view SHA-256",
        ),
        (
            &evidence.model_ir_linear_nodal_displacement_view_window_sha256,
            "rootfs ModelIR linear bounded nodal displacement view SHA-256",
        ),
        (
            &evidence.mgt_model_ir_linear_nodal_displacement_view_en_us_sha256,
            "rootfs normalized-MGT linear en-US nodal displacement view SHA-256",
        ),
        (
            &evidence.mgt_model_ir_linear_nodal_displacement_view_ko_kr_sha256,
            "rootfs normalized-MGT linear ko-KR nodal displacement view SHA-256",
        ),
    ] {
        validate_sha256_identity(value, label)?;
    }

    let mut prior = evidence.prior.clone();
    ROOTFS_RECEIPT_CLAIM_BOUNDARY_V9
        .clone_into(&mut prior.prior.prior.prior.prior.prior.claim_boundary);
    validate_rootfs_isolation_evidence_v9(&prior)
}

fn validate_rootfs_isolation_evidence_v11(
    evidence: &RootfsIsolationEvidenceV11,
) -> Result<(), DistributionError> {
    let identities = [
        evidence.model_ir_linear_deformed_view_en_us_sha256.as_str(),
        evidence.model_ir_linear_deformed_view_ko_kr_sha256.as_str(),
        evidence
            .model_ir_linear_deformed_view_projection_sha256
            .as_str(),
        evidence
            .mgt_model_ir_linear_deformed_view_en_us_sha256
            .as_str(),
        evidence
            .mgt_model_ir_linear_deformed_view_ko_kr_sha256
            .as_str(),
    ]
    .into_iter()
    .collect::<BTreeSet<_>>();
    if evidence
        .prior
        .prior
        .prior
        .prior
        .prior
        .prior
        .prior
        .claim_boundary
        != ROOTFS_RECEIPT_CLAIM_BOUNDARY_V11
        || !evidence.model_ir_linear_deformed_view_surface_passed
        || !evidence.mgt_model_ir_linear_deformed_view_surface_passed
        || !evidence.workbench_linear_deformed_view_invalid_step_rejected
        || identities.len() != 5
    {
        return Err(DistributionError::new(
            "rootfs_receipt_contract_invalid",
            "rootfs v11 receipt weakens or exceeds the exact bounded linear deformed-view diagnostic contract",
        ));
    }
    for (value, label) in [
        (
            &evidence.model_ir_linear_deformed_view_en_us_sha256,
            "rootfs ModelIR linear en-US deformed view SHA-256",
        ),
        (
            &evidence.model_ir_linear_deformed_view_ko_kr_sha256,
            "rootfs ModelIR linear ko-KR deformed view SHA-256",
        ),
        (
            &evidence.model_ir_linear_deformed_view_projection_sha256,
            "rootfs ModelIR linear alternate-projection deformed view SHA-256",
        ),
        (
            &evidence.mgt_model_ir_linear_deformed_view_en_us_sha256,
            "rootfs normalized-MGT linear en-US deformed view SHA-256",
        ),
        (
            &evidence.mgt_model_ir_linear_deformed_view_ko_kr_sha256,
            "rootfs normalized-MGT linear ko-KR deformed view SHA-256",
        ),
    ] {
        validate_sha256_identity(value, label)?;
    }

    let mut prior = evidence.prior.clone();
    ROOTFS_RECEIPT_CLAIM_BOUNDARY_V10
        .clone_into(&mut prior.prior.prior.prior.prior.prior.prior.claim_boundary);
    validate_rootfs_isolation_evidence_v10(&prior)
}

fn validate_rootfs_isolation_evidence_v12(
    evidence: &RootfsIsolationEvidenceV12,
) -> Result<(), DistributionError> {
    let identities = [
        evidence
            .model_ir_linear_element_recovery_view_en_us_sha256
            .as_str(),
        evidence
            .model_ir_linear_element_recovery_view_ko_kr_sha256
            .as_str(),
        evidence
            .mgt_model_ir_linear_element_recovery_view_en_us_sha256
            .as_str(),
        evidence
            .mgt_model_ir_linear_element_recovery_view_ko_kr_sha256
            .as_str(),
    ]
    .into_iter()
    .collect::<BTreeSet<_>>();
    if evidence
        .prior
        .prior
        .prior
        .prior
        .prior
        .prior
        .prior
        .prior
        .claim_boundary
        != ROOTFS_RECEIPT_CLAIM_BOUNDARY_V12
        || !evidence.model_ir_linear_element_recovery_view_surface_passed
        || !evidence.mgt_model_ir_linear_element_recovery_view_surface_passed
        || !evidence.workbench_linear_element_recovery_view_invalid_window_rejected
        || identities.len() != 4
    {
        return Err(DistributionError::new(
            "rootfs_receipt_contract_invalid",
            "rootfs v12 receipt weakens or exceeds the exact bounded linear element recovery view diagnostic contract",
        ));
    }
    for (value, label) in [
        (
            &evidence.model_ir_linear_element_recovery_view_en_us_sha256,
            "rootfs ModelIR linear en-US element recovery view SHA-256",
        ),
        (
            &evidence.model_ir_linear_element_recovery_view_ko_kr_sha256,
            "rootfs ModelIR linear ko-KR element recovery view SHA-256",
        ),
        (
            &evidence.mgt_model_ir_linear_element_recovery_view_en_us_sha256,
            "rootfs normalized-MGT linear en-US element recovery view SHA-256",
        ),
        (
            &evidence.mgt_model_ir_linear_element_recovery_view_ko_kr_sha256,
            "rootfs normalized-MGT linear ko-KR element recovery view SHA-256",
        ),
    ] {
        validate_sha256_identity(value, label)?;
    }
    let mut prior = evidence.prior.clone();
    ROOTFS_RECEIPT_CLAIM_BOUNDARY_V11.clone_into(
        &mut prior
            .prior
            .prior
            .prior
            .prior
            .prior
            .prior
            .prior
            .claim_boundary,
    );
    validate_rootfs_isolation_evidence_v11(&prior)
}

fn validate_rootfs_isolation_evidence_v13(
    evidence: &RootfsIsolationEvidenceV13,
) -> Result<(), DistributionError> {
    let identities = [
        evidence.structural_cli_sha256.as_str(),
        evidence.model_ir_modal_request_sha256.as_str(),
        evidence
            .workbench_model_modal_request_receipt_sha256
            .as_str(),
        evidence.model_ir_modal_checkpoint_sha256.as_str(),
        evidence.model_ir_modal_result_ir_sha256.as_str(),
        evidence.model_ir_modal_run_receipt_sha256.as_str(),
        evidence
            .workbench_model_modal_result_view_en_us_sha256
            .as_str(),
        evidence
            .workbench_model_modal_result_view_ko_kr_sha256
            .as_str(),
    ]
    .into_iter()
    .collect::<BTreeSet<_>>();
    if evidence
        .prior
        .prior
        .prior
        .prior
        .prior
        .prior
        .prior
        .prior
        .prior
        .claim_boundary
        != ROOTFS_RECEIPT_CLAIM_BOUNDARY
        || !evidence.model_ir_modal_restart_surface_passed
        || !evidence.model_ir_modal_restart_bitwise_passed
        || !evidence.workbench_model_modal_result_view_surface_passed
        || !evidence.workbench_model_modal_result_view_read_only_passed
        || !evidence.workbench_model_modal_result_view_invalid_window_rejected
        || identities.len() != 8
    {
        return Err(DistributionError::new(
            "rootfs_receipt_contract_invalid",
            "rootfs v13 receipt weakens or exceeds the exact bounded ModelIR modal restart and result-view diagnostic contract",
        ));
    }
    for (value, label) in [
        (
            &evidence.structural_cli_sha256,
            "rootfs structural-cli SHA-256",
        ),
        (
            &evidence.model_ir_modal_request_sha256,
            "rootfs ModelIR modal request SHA-256",
        ),
        (
            &evidence.workbench_model_modal_request_receipt_sha256,
            "rootfs Workbench modal request receipt SHA-256",
        ),
        (
            &evidence.model_ir_modal_checkpoint_sha256,
            "rootfs ModelIR modal checkpoint SHA-256",
        ),
        (
            &evidence.model_ir_modal_result_ir_sha256,
            "rootfs ModelIR modal ResultIR SHA-256",
        ),
        (
            &evidence.model_ir_modal_run_receipt_sha256,
            "rootfs ModelIR modal run receipt SHA-256",
        ),
        (
            &evidence.workbench_model_modal_result_view_en_us_sha256,
            "rootfs Workbench en-US modal result view SHA-256",
        ),
        (
            &evidence.workbench_model_modal_result_view_ko_kr_sha256,
            "rootfs Workbench ko-KR modal result view SHA-256",
        ),
    ] {
        validate_sha256_identity(value, label)?;
    }
    let mut prior = evidence.prior.clone();
    ROOTFS_RECEIPT_CLAIM_BOUNDARY_V12.clone_into(
        &mut prior
            .prior
            .prior
            .prior
            .prior
            .prior
            .prior
            .prior
            .prior
            .claim_boundary,
    );
    validate_rootfs_isolation_evidence_v12(&prior)
}

fn validate_manifest_fields(manifest: &DistributionManifestV1) -> Result<(), DistributionError> {
    if manifest.schema_version != SCHEMA_VERSION || manifest.abi_version != ABI_VERSION {
        return Err(DistributionError::new(
            "bundle_contract_unsupported",
            "distribution schema or ABI version is unsupported",
        ));
    }
    validate_release_id(&manifest.release_id)?;
    validate_package_version(&manifest.package_version)?;
    validate_sha256_identity(&manifest.source_sha256, "source SHA-256")?;
    validate_sha256_identity(&manifest.manifest_hash, "manifest hash")?;
    let expected_authority = match manifest.backend_profile {
        BackendProfileV1::CpuOnly => "cpu_build_candidate",
        BackendProfileV1::Rocm => "rocm_build_candidate",
    };
    if manifest.execution_authority != expected_authority {
        return Err(DistributionError::new(
            "bundle_authority_invalid",
            "execution authority is incompatible with the backend profile",
        ));
    }
    if manifest.files.is_empty() || manifest.files.len() > MAX_FILE_COUNT {
        return Err(DistributionError::new(
            "bundle_file_count_invalid",
            "distribution file count is empty or exceeds the limit",
        ));
    }
    let mut previous = None;
    let mut unique = BTreeSet::new();
    for entry in &manifest.files {
        validated_relative_path(&entry.path)?;
        validate_sha256_identity(&entry.sha256, "payload SHA-256")?;
        if entry.size > MAX_FILE_BYTES || !matches!(entry.mode, 0o444 | 0o555) {
            return Err(DistributionError::new(
                "bundle_file_metadata_invalid",
                format!("invalid size or mode for {}", entry.path),
            ));
        }
        if previous.is_some_and(|path: &String| path >= &entry.path)
            || !unique.insert(entry.path.clone())
        {
            return Err(DistributionError::new(
                "bundle_inventory_noncanonical",
                "payload inventory must be unique and bytewise sorted",
            ));
        }
        previous = Some(&entry.path);
    }
    Ok(())
}

fn validate_payload_contract(
    payload: &Path,
    package_version: &str,
    backend: BackendProfileV1,
    linkage: LinkageV1,
    entries: &[DistributionFileV1],
) -> Result<(), DistributionError> {
    let inventory = entries
        .iter()
        .map(|entry| entry.path.as_str())
        .collect::<BTreeSet<_>>();
    for required in [
        "bin/structural-cli",
        "bin/structural-catalog",
        "bin/structural-evidence",
        "bin/structural-installer",
        "bin/structural-workbench",
        "include/structural/abi_v1.h",
        "share/structural-native/structural-native-build.json",
    ] {
        if !inventory.contains(required) {
            return Err(DistributionError::new(
                "bundle_required_file_missing",
                format!("required product file is missing: {required}"),
            ));
        }
    }
    let required_library = match linkage {
        LinkageV1::Shared => "lib/libstructural_c_abi_v1.so",
        LinkageV1::Static => "lib/libstructural_c_abi_v1.a",
    };
    if !inventory.contains(required_library) {
        return Err(DistributionError::new(
            "bundle_required_file_missing",
            format!("required product library is missing: {required_library}"),
        ));
    }
    for binary in [
        "bin/structural-cli",
        "bin/structural-catalog",
        "bin/structural-evidence",
        "bin/structural-installer",
        "bin/structural-workbench",
    ] {
        let entry = entries
            .iter()
            .find(|entry| entry.path == binary)
            .expect("required entry checked");
        if entry.mode != 0o555 {
            return Err(DistributionError::new(
                "bundle_binary_not_executable",
                format!("product binary is not executable: {binary}"),
            ));
        }
    }
    let build_path = payload.join("share/structural-native/structural-native-build.json");
    let build_bytes = read_bounded_regular_file(&build_path, MAX_MANIFEST_BYTES)?;
    let build: NativeBuildManifestV1 = serde_json::from_slice(&build_bytes).map_err(|error| {
        DistributionError::new(
            "native_build_manifest_invalid",
            format!("native build manifest is invalid: {error}"),
        )
    })?;
    let expected_hip = backend == BackendProfileV1::Rocm;
    if build.schema_version != BUILD_SCHEMA_VERSION
        || build.package_version != package_version
        || build.abi_version != ABI_VERSION
        || build.hip_enabled != expected_hip
        || build.c_compiler.id.is_empty()
        || build.c_compiler.version.is_empty()
        || build.cxx_compiler.id.is_empty()
        || build.cxx_compiler.version.is_empty()
        || build.build_type != "Release"
    {
        return Err(DistributionError::new(
            "native_build_manifest_mismatch",
            "native build identity does not match the distribution profile",
        ));
    }
    Ok(())
}

fn validate_release_id(value: &str) -> Result<(), DistributionError> {
    if value.is_empty()
        || value.len() > 128
        || value == "."
        || value == ".."
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'-'))
    {
        return Err(DistributionError::new(
            "release_id_invalid",
            "release ID must use 1-128 ASCII alphanumeric, dot, underscore, or hyphen bytes",
        ));
    }
    Ok(())
}

fn validate_staging_name(value: &str) -> Result<(), DistributionError> {
    if !value.starts_with(".stage-") {
        return Err(DistributionError::new(
            "transaction_staging_invalid",
            "transaction staging name is invalid",
        ));
    }
    validate_release_id(value)
}

fn validate_package_version(value: &str) -> Result<(), DistributionError> {
    if value.is_empty()
        || value.len() > 64
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'+' | b'-'))
    {
        return Err(DistributionError::new(
            "package_version_invalid",
            "package version must be a bounded portable version token",
        ));
    }
    Ok(())
}

fn validate_sha256_identity(value: &str, label: &str) -> Result<(), DistributionError> {
    let Some(hex) = value.strip_prefix("sha256:") else {
        return Err(DistributionError::new(
            "sha256_identity_invalid",
            format!("{label} must start with sha256:"),
        ));
    };
    if hex.len() != 64
        || !hex
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return Err(DistributionError::new(
            "sha256_identity_invalid",
            format!("{label} must contain exactly 64 lowercase hexadecimal digits"),
        ));
    }
    Ok(())
}

fn validated_relative_path(value: &str) -> Result<PathBuf, DistributionError> {
    if value.is_empty() || value.contains('\\') {
        return Err(DistributionError::new(
            "bundle_path_invalid",
            "bundle paths must be non-empty portable relative paths",
        ));
    }
    let path = Path::new(value);
    if path
        .components()
        .any(|component| !matches!(component, Component::Normal(_)))
    {
        return Err(DistributionError::new(
            "bundle_path_invalid",
            "bundle path contains root, parent, current, or prefix components",
        ));
    }
    Ok(path.to_path_buf())
}

fn portable_relative_path(path: &Path) -> Result<String, DistributionError> {
    let mut components = Vec::new();
    for component in path.components() {
        let Component::Normal(value) = component else {
            return Err(DistributionError::new(
                "bundle_path_invalid",
                "payload path is not a portable relative path",
            ));
        };
        let text = value.to_str().ok_or_else(|| {
            DistributionError::new("bundle_path_utf8_required", "payload paths must be UTF-8")
        })?;
        if text.is_empty() || text.contains(['/', '\\']) {
            return Err(DistributionError::new(
                "bundle_path_invalid",
                "payload path component is invalid",
            ));
        }
        components.push(text);
    }
    if components.is_empty() {
        return Err(DistributionError::new(
            "bundle_path_invalid",
            "payload path is empty",
        ));
    }
    Ok(components.join("/"))
}

fn copy_regular_file(
    source: &Path,
    destination: &Path,
) -> Result<(u64, u32, String), DistributionError> {
    let metadata =
        fs::metadata(source).map_err(|error| io_error("payload_file_metadata_failed", error))?;
    if !metadata.is_file() || metadata.len() > MAX_FILE_BYTES {
        return Err(DistributionError::new(
            "payload_file_invalid",
            "payload source must be a bounded regular file",
        ));
    }
    let mode = if portable_mode(&metadata) & 0o111 != 0 {
        0o555
    } else {
        0o444
    };
    let source_file = open_regular_no_follow(source, "payload_file_open_failed")?;
    let source_metadata = source_file
        .metadata()
        .map_err(|error| io_error("payload_file_metadata_failed", error))?;
    if !source_metadata.is_file() || source_metadata.len() != metadata.len() {
        return Err(DistributionError::new(
            "payload_file_changed",
            "payload file changed while opening it",
        ));
    }
    let destination_file = OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(destination)
        .map_err(|error| io_error("payload_copy_open_failed", error))?;
    let mut reader = BufReader::new(source_file);
    let mut writer = BufWriter::new(destination_file);
    let mut digest = Sha256::new();
    let mut size = 0_u64;
    let mut buffer = vec![0_u8; 64 * 1024].into_boxed_slice();
    loop {
        let count = reader
            .read(&mut buffer)
            .map_err(|error| io_error("payload_copy_read_failed", error))?;
        if count == 0 {
            break;
        }
        size = size.checked_add(count as u64).ok_or_else(|| {
            DistributionError::new("payload_size_overflow", "payload file size overflowed")
        })?;
        if size > MAX_FILE_BYTES {
            return Err(DistributionError::new(
                "payload_file_size_exceeded",
                "payload file grew beyond the distribution limit",
            ));
        }
        digest.update(&buffer[..count]);
        writer
            .write_all(&buffer[..count])
            .map_err(|error| io_error("payload_copy_write_failed", error))?;
    }
    writer
        .flush()
        .map_err(|error| io_error("payload_copy_flush_failed", error))?;
    writer
        .get_ref()
        .sync_all()
        .map_err(|error| io_error("payload_copy_sync_failed", error))?;
    set_mode(destination, mode)?;
    writer
        .get_ref()
        .sync_all()
        .map_err(|error| io_error("payload_mode_sync_failed", error))?;
    Ok((size, mode, digest_identity(digest)))
}

fn sha256_file(path: &Path) -> Result<String, DistributionError> {
    let file = open_regular_no_follow(path, "payload_hash_open_failed")?;
    let mut reader = BufReader::new(file);
    let mut digest = Sha256::new();
    let mut buffer = vec![0_u8; 64 * 1024].into_boxed_slice();
    loop {
        let count = reader
            .read(&mut buffer)
            .map_err(|error| io_error("payload_hash_read_failed", error))?;
        if count == 0 {
            break;
        }
        digest.update(&buffer[..count]);
    }
    Ok(digest_identity(digest))
}

fn sha256_identity(bytes: &[u8]) -> String {
    let mut digest = Sha256::new();
    digest.update(bytes);
    digest_identity(digest)
}

fn digest_identity(digest: Sha256) -> String {
    let bytes = digest.finalize();
    let mut output = String::with_capacity(71);
    output.push_str("sha256:");
    for byte in bytes {
        use fmt::Write as _;
        write!(&mut output, "{byte:02x}").expect("writing to String cannot fail");
    }
    output
}

fn canonical_json<T: Serialize>(value: &T) -> Result<Vec<u8>, DistributionError> {
    let mut bytes = serde_json::to_vec(value).map_err(|error| {
        DistributionError::new(
            "distribution_json_encode_failed",
            format!("could not encode deterministic JSON: {error}"),
        )
    })?;
    bytes.push(b'\n');
    Ok(bytes)
}

fn atomic_write_canonical<T: Serialize>(path: &Path, value: &T) -> Result<(), DistributionError> {
    let bytes = canonical_json(value)?;
    let parent = path.parent().ok_or_else(|| {
        DistributionError::new(
            "atomic_write_invalid",
            "atomic output has no parent directory",
        )
    })?;
    reject_symlink_if_present(path, "atomic output")?;
    let temporary = unique_path(parent, ".structural-state-tmp");
    write_new_file(&temporary, &bytes, 0o600)?;
    fs::rename(&temporary, path).map_err(|error| io_error("atomic_write_rename_failed", error))?;
    sync_directory(parent)
}

fn write_new_file(path: &Path, bytes: &[u8], mode: u32) -> Result<(), DistributionError> {
    let mut file = OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(path)
        .map_err(|error| io_error("file_create_failed", error))?;
    file.write_all(bytes)
        .map_err(|error| io_error("file_write_failed", error))?;
    set_mode(path, mode)?;
    file.sync_all()
        .map_err(|error| io_error("file_sync_failed", error))
}

fn read_canonical_json<T: for<'de> Deserialize<'de> + Serialize>(
    path: &Path,
    limit: u64,
) -> Result<T, DistributionError> {
    let bytes = read_bounded_regular_file(path, limit)?;
    let value: T = serde_json::from_slice(&bytes).map_err(|error| {
        DistributionError::new(
            "state_json_invalid",
            format!("installation state JSON is invalid: {error}"),
        )
    })?;
    if canonical_json(&value)? != bytes {
        return Err(DistributionError::new(
            "state_json_noncanonical",
            "installation state must use exact canonical JSON bytes",
        ));
    }
    Ok(value)
}

fn read_bounded_regular_file(path: &Path, limit: u64) -> Result<Vec<u8>, DistributionError> {
    let metadata = fs::symlink_metadata(path)
        .map_err(|error| io_error("bounded_file_metadata_failed", error))?;
    if metadata.file_type().is_symlink() || !metadata.is_file() || metadata.len() > limit {
        return Err(DistributionError::new(
            "bounded_regular_file_required",
            "input must be a bounded regular non-symlink file",
        ));
    }
    let file = open_regular_no_follow(path, "bounded_file_open_failed")?;
    let opened_metadata = file
        .metadata()
        .map_err(|error| io_error("bounded_file_metadata_failed", error))?;
    if !opened_metadata.is_file() || opened_metadata.len() != metadata.len() {
        return Err(DistributionError::new(
            "bounded_file_changed",
            "bounded input changed while opening it",
        ));
    }
    let mut bytes = Vec::with_capacity(usize::try_from(metadata.len()).unwrap_or(0));
    file.take(limit.saturating_add(1))
        .read_to_end(&mut bytes)
        .map_err(|error| io_error("bounded_file_read_failed", error))?;
    if bytes.len() as u64 > limit {
        return Err(DistributionError::new(
            "bounded_file_size_exceeded",
            "input grew beyond the byte limit while reading",
        ));
    }
    Ok(bytes)
}

fn ensure_directory(path: &Path, label: &str) -> Result<(), DistributionError> {
    let metadata =
        fs::symlink_metadata(path).map_err(|error| io_error("directory_metadata_failed", error))?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err(DistributionError::new(
            "directory_required",
            format!("{label} must be a real directory"),
        ));
    }
    Ok(())
}

fn create_real_subdirectory(parent: &Path, name: &str) -> Result<(), DistributionError> {
    let path = parent.join(name);
    match fs::symlink_metadata(&path) {
        Ok(metadata) if metadata.file_type().is_symlink() || !metadata.is_dir() => {
            return Err(DistributionError::new(
                "install_subdirectory_invalid",
                format!("install {name} path must be a real directory"),
            ));
        }
        Ok(_) => {}
        Err(error) if error.kind() == io::ErrorKind::NotFound => {
            fs::create_dir(&path)
                .map_err(|error| io_error("install_subdirectory_create_failed", error))?;
        }
        Err(error) => return Err(io_error("install_subdirectory_inspect_failed", error)),
    }
    ensure_directory(&path, name)
}

fn path_entry_exists(path: &Path) -> Result<bool, DistributionError> {
    match fs::symlink_metadata(path) {
        Ok(_) => Ok(true),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(false),
        Err(error) => Err(io_error("path_metadata_failed", error)),
    }
}

fn reject_symlink_if_present(path: &Path, label: &str) -> Result<(), DistributionError> {
    match fs::symlink_metadata(path) {
        Ok(metadata) if metadata.file_type().is_symlink() => Err(DistributionError::new(
            "symlink_rejected",
            format!("{label} must not be a symlink"),
        )),
        Ok(_) => Ok(()),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(io_error("path_metadata_failed", error)),
    }
}

fn sync_directory(path: &Path) -> Result<(), DistributionError> {
    File::open(path)
        .and_then(|file| file.sync_all())
        .map_err(|error| io_error("directory_sync_failed", error))
}

fn sync_directory_tree(root: &Path) -> Result<(), DistributionError> {
    fn visit(path: &Path, output: &mut Vec<PathBuf>) -> io::Result<()> {
        output.push(path.to_path_buf());
        for entry in fs::read_dir(path)? {
            let entry = entry?;
            if entry.file_type()?.is_dir() {
                visit(&entry.path(), output)?;
            }
        }
        Ok(())
    }
    let mut directories = Vec::new();
    visit(root, &mut directories).map_err(|error| io_error("directory_walk_failed", error))?;
    directories.sort_by_key(|path| std::cmp::Reverse(path.components().count()));
    for directory in directories {
        sync_directory(&directory)?;
    }
    Ok(())
}

fn release_path(install_root: &Path, release_id: &str) -> PathBuf {
    install_root.join(RELEASES_DIRECTORY).join(release_id)
}

fn unique_token() -> String {
    let sequence = TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed);
    format!("{}-{sequence}", std::process::id())
}

fn unique_path(parent: &Path, prefix: &str) -> PathBuf {
    parent.join(format!("{prefix}-{}", unique_token()))
}

fn next_generation(current: Option<&ActivationStateV1>) -> Result<u64, DistributionError> {
    current.map_or(Ok(1), |state| {
        state.generation.checked_add(1).ok_or_else(|| {
            DistributionError::new(
                "activation_generation_overflow",
                "activation generation cannot be incremented",
            )
        })
    })
}

fn maybe_interrupt(
    actual: InstallInterruption,
    boundary: InstallInterruption,
) -> Result<(), DistributionError> {
    if actual == boundary {
        Err(DistributionError::new(
            "simulated_interruption",
            "test-only interruption at a durable transaction boundary",
        ))
    } else {
        Ok(())
    }
}

#[allow(clippy::needless_pass_by_value)]
fn io_error(code: &'static str, error: io::Error) -> DistributionError {
    DistributionError::new(code, error.to_string())
}

#[cfg(unix)]
fn open_regular_no_follow(path: &Path, code: &'static str) -> Result<File, DistributionError> {
    use std::os::unix::fs::OpenOptionsExt;
    OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW)
        .open(path)
        .map_err(|error| io_error(code, error))
}

#[cfg(unix)]
fn open_install_lock(path: &Path) -> Result<File, DistributionError> {
    use std::os::unix::fs::OpenOptionsExt;
    OpenOptions::new()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .mode(0o600)
        .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW)
        .open(path)
        .map_err(|error| io_error("install_lock_open_failed", error))
}

#[cfg(not(unix))]
fn open_install_lock(path: &Path) -> Result<File, DistributionError> {
    OpenOptions::new()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .open(path)
        .map_err(|error| io_error("install_lock_open_failed", error))
}

#[cfg(not(unix))]
fn open_regular_no_follow(path: &Path, code: &'static str) -> Result<File, DistributionError> {
    File::open(path).map_err(|error| io_error(code, error))
}

#[cfg(unix)]
fn portable_mode(metadata: &fs::Metadata) -> u32 {
    use std::os::unix::fs::PermissionsExt;
    metadata.permissions().mode() & 0o777
}

#[cfg(not(unix))]
fn portable_mode(_metadata: &fs::Metadata) -> u32 {
    0o444
}

#[cfg(unix)]
fn set_mode(path: &Path, mode: u32) -> Result<(), DistributionError> {
    use std::os::unix::fs::PermissionsExt;
    fs::set_permissions(path, fs::Permissions::from_mode(mode))
        .map_err(|error| io_error("file_mode_set_failed", error))
}

#[cfg(not(unix))]
fn set_mode(_path: &Path, _mode: u32) -> Result<(), DistributionError> {
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    struct TestDirectory(PathBuf);

    impl TestDirectory {
        fn create(label: &str) -> Self {
            let path = std::env::temp_dir().join(format!(
                "structural-distribution-{label}-{}",
                unique_token()
            ));
            fs::create_dir(&path).expect("create isolated distribution test directory");
            Self(path)
        }
    }

    impl Drop for TestDirectory {
        fn drop(&mut self) {
            fs::remove_dir_all(&self.0).expect("remove isolated distribution test directory");
        }
    }

    fn create_payload(root: &Path, hip_enabled: bool, linkage: LinkageV1, marker: &str) {
        for directory in [
            "bin",
            "include/structural",
            "lib",
            "share/structural-native",
        ] {
            fs::create_dir_all(root.join(directory)).expect("create payload directory");
        }
        for binary in [
            "bin/structural-cli",
            "bin/structural-catalog",
            "bin/structural-evidence",
            "bin/structural-installer",
            "bin/structural-workbench",
        ] {
            fs::write(root.join(binary), format!("#!/bin/sh\necho {marker}\n"))
                .expect("write product binary fixture");
            set_mode(&root.join(binary), 0o755).expect("mark fixture executable");
        }
        fs::write(
            root.join("include/structural/abi_v1.h"),
            "/* ABI v1.14 */\n",
        )
        .expect("write ABI header fixture");
        let library = match linkage {
            LinkageV1::Shared => "lib/libstructural_c_abi_v1.so",
            LinkageV1::Static => "lib/libstructural_c_abi_v1.a",
        };
        fs::write(root.join(library), marker).expect("write library fixture");
        let build = serde_json::json!({
            "schema_version": BUILD_SCHEMA_VERSION,
            "package_version": "0.1.0",
            "abi_version": ABI_VERSION,
            "c_compiler": {"id": "GNU", "version": "14.2"},
            "cxx_compiler": {"id": "GNU", "version": "14.2"},
            "build_type": "Release",
            "hip_enabled": hip_enabled,
        });
        fs::write(
            root.join("share/structural-native/structural-native-build.json"),
            serde_json::to_vec_pretty(&build).expect("build manifest JSON"),
        )
        .expect("write build manifest fixture");
    }

    fn make_bundle(directory: &TestDirectory, release: &str, marker: &str) -> PathBuf {
        let payload = directory.0.join(format!("payload-{release}"));
        fs::create_dir(&payload).expect("create payload root");
        create_payload(&payload, false, LinkageV1::Shared, marker);
        let bundle = directory.0.join(format!("bundle-{release}"));
        create_bundle(&BundleCreateRequest {
            payload_root: &payload,
            output: &bundle,
            release_id: release,
            package_version: "0.1.0",
            backend_profile: BackendProfileV1::CpuOnly,
            linkage: LinkageV1::Shared,
            source_sha256: &format!("sha256:{:064x}", marker.len()),
        })
        .expect("create bundle fixture");
        bundle
    }

    fn rootfs_evidence_v2() -> RootfsIsolationEvidenceV2 {
        let identity = |value: u8| format!("sha256:{value:064x}");
        RootfsIsolationEvidenceV2 {
            authority: ROOTFS_RECEIPT_AUTHORITY.to_owned(),
            claim_boundary: ROOTFS_RECEIPT_CLAIM_BOUNDARY_V2.to_owned(),
            isolation_technology: ROOTFS_ISOLATION_TECHNOLOGY.to_owned(),
            release_id: "rootfs-release-1".to_owned(),
            source_sha256: identity(1),
            bundle_manifest_hash: identity(2),
            bundle_manifest_file_sha256: identity(3),
            installer_sha256: identity(4),
            workbench_sha256: identity(5),
            runtime_uid: ROOTFS_RUNTIME_UID,
            runtime_gid: ROOTFS_RUNTIME_GID,
            network_interfaces: vec!["lo".to_owned()],
            ipv4_route_count: 0,
            rootfs_write_errno: libc::EROFS,
            payload_write_errno: libc::EROFS,
            workspace_write_passed: true,
            path: ROOTFS_EMPTY_PATH.to_owned(),
            python_lookup_count: 0,
            node_lookup_count: 0,
            workbench_version: "structural-workbench 0.1.0".to_owned(),
            workbench_stage: "reported".to_owned(),
            workbench_terminal_status: "completed".to_owned(),
            workbench_comparison_passed: true,
            result_ir_sha256: identity(6),
            report_pdf_sha256: identity(7),
            workbench_operator_surface_passed: true,
            workbench_review_decision: "review".to_owned(),
            workbench_inspect_before_review_sha256: identity(12),
            workbench_review_sha256: identity(13),
            workbench_inspect_after_review_sha256: identity(14),
            workbench_export_sha256: identity(15),
            mgt_workbench_stage: "reported".to_owned(),
            mgt_workbench_terminal_status: "completed".to_owned(),
            mgt_workbench_comparison_passed: true,
            mgt_source_sha256: identity(8),
            mgt_import_health_sha256: identity(9),
            mgt_result_ir_sha256: identity(10),
            mgt_report_pdf_sha256: identity(11),
            mgt_workbench_operator_surface_passed: true,
            mgt_workbench_review_decision: "review".to_owned(),
            mgt_workbench_inspect_before_review_sha256: identity(16),
            mgt_workbench_review_sha256: identity(17),
            mgt_workbench_inspect_after_review_sha256: identity(18),
            mgt_workbench_export_sha256: identity(19),
            container_image_built: false,
            customer_image_receipt: false,
        }
    }

    fn rootfs_evidence_v3() -> RootfsIsolationEvidenceV3 {
        let mut value =
            serde_json::to_value(rootfs_evidence_v2()).expect("project v2 rootfs evidence");
        let object = value.as_object_mut().expect("rootfs evidence object");
        object.insert(
            "claim_boundary".to_owned(),
            serde_json::Value::String(ROOTFS_RECEIPT_CLAIM_BOUNDARY_V3.to_owned()),
        );
        object.insert(
            "workbench_catalog_surface_passed".to_owned(),
            serde_json::Value::Bool(true),
        );
        object.insert(
            "workbench_catalog_sha256".to_owned(),
            serde_json::Value::String(format!("sha256:{:064x}", 20)),
        );
        object.insert(
            "workbench_evidence_surface_passed".to_owned(),
            serde_json::Value::Bool(true),
        );
        object.insert(
            "workbench_evidence_sha256".to_owned(),
            serde_json::Value::String(format!("sha256:{:064x}", 21)),
        );
        serde_json::from_value(value).expect("decode v3 rootfs evidence")
    }

    fn rootfs_evidence_v4() -> RootfsIsolationEvidenceV4 {
        let mut value =
            serde_json::to_value(rootfs_evidence_v3()).expect("project v3 rootfs evidence");
        let object = value.as_object_mut().expect("rootfs evidence object");
        object.insert(
            "claim_boundary".to_owned(),
            serde_json::Value::String(ROOTFS_RECEIPT_CLAIM_BOUNDARY_V4.to_owned()),
        );
        let identity = |value: u8| serde_json::Value::String(format!("sha256:{value:064x}"));
        object.insert(
            "model_ir_linear_workbench_stage".to_owned(),
            serde_json::Value::String("reported".to_owned()),
        );
        object.insert(
            "model_ir_linear_workbench_terminal_status".to_owned(),
            serde_json::Value::String("completed".to_owned()),
        );
        object.insert(
            "model_ir_linear_workbench_comparison_passed".to_owned(),
            serde_json::Value::Bool(true),
        );
        object.insert(
            "model_ir_linear_workbench_operator_surface_passed".to_owned(),
            serde_json::Value::Bool(true),
        );
        object.insert(
            "model_ir_linear_workbench_review_decision".to_owned(),
            serde_json::Value::String("review".to_owned()),
        );
        for (value, field) in [
            (22, "model_ir_linear_result_ir_sha256"),
            (23, "model_ir_linear_result_recovery_ir_sha256"),
            (24, "model_ir_linear_comparison_ir_sha256"),
            (25, "model_ir_linear_report_pdf_sha256"),
            (26, "model_ir_linear_report_document_sha256"),
            (27, "model_ir_linear_pdf_receipt_sha256"),
            (28, "model_ir_linear_report_receipt_sha256"),
            (29, "model_ir_linear_workbench_inspect_before_review_sha256"),
            (30, "model_ir_linear_workbench_review_sha256"),
            (31, "model_ir_linear_workbench_inspect_after_review_sha256"),
            (32, "model_ir_linear_workbench_export_sha256"),
        ] {
            object.insert(field.to_owned(), identity(value));
        }
        serde_json::from_value(value).expect("decode v4 rootfs evidence")
    }

    fn rootfs_evidence_v5() -> RootfsIsolationEvidenceV5 {
        let mut prior = rootfs_evidence_v4();
        ROOTFS_RECEIPT_CLAIM_BOUNDARY_V5.clone_into(&mut prior.claim_boundary);
        RootfsIsolationEvidenceV5 {
            prior,
            model_ir_linear_localized_pdf_surface_passed: true,
            model_ir_linear_localized_pdf_en_us_sha256: format!("sha256:{:064x}", 33),
            model_ir_linear_localized_pdf_ko_kr_sha256: format!("sha256:{:064x}", 34),
            model_ir_linear_localized_pdf_en_us_receipt_sha256: format!("sha256:{:064x}", 35),
            model_ir_linear_localized_pdf_ko_kr_receipt_sha256: format!("sha256:{:064x}", 36),
        }
    }

    fn rootfs_evidence_v6() -> RootfsIsolationEvidenceV6 {
        let mut prior = rootfs_evidence_v5();
        ROOTFS_RECEIPT_CLAIM_BOUNDARY_V6.clone_into(&mut prior.prior.claim_boundary);
        let identity = |value: u8| format!("sha256:{value:064x}");
        RootfsIsolationEvidenceV6 {
            prior,
            mgt_model_ir_linear_workbench_stage: "reported".to_owned(),
            mgt_model_ir_linear_workbench_terminal_status: "completed".to_owned(),
            mgt_model_ir_linear_workbench_comparison_passed: true,
            mgt_model_ir_linear_workbench_operator_surface_passed: true,
            mgt_model_ir_linear_workbench_review_decision: "review".to_owned(),
            mgt_model_ir_linear_source_sha256: identity(37),
            mgt_model_ir_linear_import_health_sha256: identity(38),
            mgt_model_ir_linear_result_ir_sha256: identity(39),
            mgt_model_ir_linear_result_recovery_ir_sha256: identity(40),
            mgt_model_ir_linear_comparison_ir_sha256: identity(41),
            mgt_model_ir_linear_report_pdf_sha256: identity(42),
            mgt_model_ir_linear_report_document_sha256: identity(43),
            mgt_model_ir_linear_pdf_receipt_sha256: identity(44),
            mgt_model_ir_linear_report_receipt_sha256: identity(45),
            mgt_model_ir_linear_workbench_inspect_before_review_sha256: identity(46),
            mgt_model_ir_linear_workbench_review_sha256: identity(47),
            mgt_model_ir_linear_workbench_inspect_after_review_sha256: identity(48),
            mgt_model_ir_linear_workbench_export_sha256: identity(49),
        }
    }

    fn rootfs_evidence_v7() -> RootfsIsolationEvidenceV7 {
        let mut prior = rootfs_evidence_v6();
        ROOTFS_RECEIPT_CLAIM_BOUNDARY_V7.clone_into(&mut prior.prior.prior.claim_boundary);
        RootfsIsolationEvidenceV7 {
            prior,
            model_ir_linear_reaction_result_ir_sha256: format!("sha256:{:064x}", 50),
            mgt_model_ir_linear_reaction_result_ir_sha256: format!("sha256:{:064x}", 51),
        }
    }

    fn rootfs_evidence_v8() -> RootfsIsolationEvidenceV8 {
        let mut prior = rootfs_evidence_v7();
        ROOTFS_RECEIPT_CLAIM_BOUNDARY_V8.clone_into(&mut prior.prior.prior.prior.claim_boundary);
        let identity = |value: u8| format!("sha256:{value:064x}");
        RootfsIsolationEvidenceV8 {
            prior,
            model_ir_linear_reaction_view_surface_passed: true,
            model_ir_linear_reaction_view_en_us_sha256: identity(52),
            model_ir_linear_reaction_view_ko_kr_sha256: identity(53),
            model_ir_linear_reaction_view_window_sha256: identity(54),
            mgt_model_ir_linear_reaction_view_surface_passed: true,
            mgt_model_ir_linear_reaction_view_en_us_sha256: identity(55),
            mgt_model_ir_linear_reaction_view_ko_kr_sha256: identity(56),
            workbench_reaction_view_wrong_profile_rejected: true,
        }
    }

    fn rootfs_evidence_v9() -> RootfsIsolationEvidenceV9 {
        let mut prior = rootfs_evidence_v8();
        ROOTFS_RECEIPT_CLAIM_BOUNDARY_V9
            .clone_into(&mut prior.prior.prior.prior.prior.claim_boundary);
        let identity = |value: u8| format!("sha256:{value:064x}");
        RootfsIsolationEvidenceV9 {
            prior,
            model_ir_linear_reaction_audit_surface_passed: true,
            model_ir_linear_reaction_audit_en_us_sha256: identity(57),
            model_ir_linear_reaction_audit_ko_kr_sha256: identity(58),
            mgt_model_ir_linear_reaction_audit_surface_passed: true,
            mgt_model_ir_linear_reaction_audit_en_us_sha256: identity(59),
            mgt_model_ir_linear_reaction_audit_ko_kr_sha256: identity(60),
            workbench_reaction_audit_wrong_profile_rejected: true,
        }
    }

    fn rootfs_evidence_v10() -> RootfsIsolationEvidenceV10 {
        let mut prior = rootfs_evidence_v9();
        ROOTFS_RECEIPT_CLAIM_BOUNDARY_V10
            .clone_into(&mut prior.prior.prior.prior.prior.prior.claim_boundary);
        let identity = |value: u8| format!("sha256:{value:064x}");
        RootfsIsolationEvidenceV10 {
            prior,
            model_ir_linear_nodal_displacement_view_surface_passed: true,
            model_ir_linear_nodal_displacement_view_en_us_sha256: identity(61),
            model_ir_linear_nodal_displacement_view_ko_kr_sha256: identity(62),
            model_ir_linear_nodal_displacement_view_window_sha256: identity(63),
            mgt_model_ir_linear_nodal_displacement_view_surface_passed: true,
            mgt_model_ir_linear_nodal_displacement_view_en_us_sha256: identity(64),
            mgt_model_ir_linear_nodal_displacement_view_ko_kr_sha256: identity(65),
            workbench_nodal_displacement_view_wrong_profile_rejected: true,
        }
    }

    fn rootfs_evidence() -> RootfsIsolationEvidenceV11 {
        let mut prior = rootfs_evidence_v10();
        ROOTFS_RECEIPT_CLAIM_BOUNDARY_V11
            .clone_into(&mut prior.prior.prior.prior.prior.prior.prior.claim_boundary);
        let identity = |value: u8| format!("sha256:{value:064x}");
        RootfsIsolationEvidenceV11 {
            prior,
            model_ir_linear_deformed_view_surface_passed: true,
            model_ir_linear_deformed_view_en_us_sha256: identity(66),
            model_ir_linear_deformed_view_ko_kr_sha256: identity(67),
            model_ir_linear_deformed_view_projection_sha256: identity(68),
            mgt_model_ir_linear_deformed_view_surface_passed: true,
            mgt_model_ir_linear_deformed_view_en_us_sha256: identity(69),
            mgt_model_ir_linear_deformed_view_ko_kr_sha256: identity(70),
            workbench_linear_deformed_view_invalid_step_rejected: true,
        }
    }

    fn rootfs_evidence_v12() -> RootfsIsolationEvidenceV12 {
        let mut prior = rootfs_evidence();
        ROOTFS_RECEIPT_CLAIM_BOUNDARY_V12.clone_into(
            &mut prior
                .prior
                .prior
                .prior
                .prior
                .prior
                .prior
                .prior
                .claim_boundary,
        );
        let identity = |value: u8| format!("sha256:{value:064x}");
        RootfsIsolationEvidenceV12 {
            prior,
            model_ir_linear_element_recovery_view_surface_passed: true,
            model_ir_linear_element_recovery_view_en_us_sha256: identity(71),
            model_ir_linear_element_recovery_view_ko_kr_sha256: identity(72),
            mgt_model_ir_linear_element_recovery_view_surface_passed: true,
            mgt_model_ir_linear_element_recovery_view_en_us_sha256: identity(73),
            mgt_model_ir_linear_element_recovery_view_ko_kr_sha256: identity(74),
            workbench_linear_element_recovery_view_invalid_window_rejected: true,
        }
    }

    fn rootfs_evidence_v13() -> RootfsIsolationEvidenceV13 {
        let mut prior = rootfs_evidence_v12();
        ROOTFS_RECEIPT_CLAIM_BOUNDARY.clone_into(
            &mut prior
                .prior
                .prior
                .prior
                .prior
                .prior
                .prior
                .prior
                .prior
                .claim_boundary,
        );
        let identity = |value: u8| format!("sha256:{value:064x}");
        RootfsIsolationEvidenceV13 {
            prior,
            structural_cli_sha256: identity(75),
            model_ir_modal_request_sha256: identity(76),
            workbench_model_modal_request_receipt_sha256: identity(77),
            model_ir_modal_checkpoint_sha256: identity(78),
            model_ir_modal_result_ir_sha256: identity(79),
            model_ir_modal_run_receipt_sha256: identity(80),
            model_ir_modal_restart_surface_passed: true,
            model_ir_modal_restart_bitwise_passed: true,
            workbench_model_modal_result_view_surface_passed: true,
            workbench_model_modal_result_view_en_us_sha256: identity(81),
            workbench_model_modal_result_view_ko_kr_sha256: identity(82),
            workbench_model_modal_result_view_read_only_passed: true,
            workbench_model_modal_result_view_invalid_window_rejected: true,
        }
    }

    fn reaction_view_fixture(unit: &str) -> Vec<u8> {
        let mut unsigned = String::from(
            "Schema: structural-native-workbench-model-ir-linear-reaction-view.v1\n\
             Locale: en-US\n\
             Displayed rows: 1-6 of 6\n\
             Backend: cpu / FP64 / ABI 0x0001000e / fallback 0\n",
        );
        for row in 1..=6 {
            use std::fmt::Write as _;
            writeln!(
                unsigned,
                "{row:06}\tN1\tUX\t{:010}\t+1.00000000000000000e0\t+0.00000000000000000e0\t+1.00000000000000000e0\t{unit}",
                row - 1,
            )
            .expect("write reaction fixture row");
        }
        let identity = sha256_identity(unsigned.as_bytes());
        format!("{unsigned}View hash: {identity}\n").into_bytes()
    }

    fn reaction_audit_fixture(normalized_mgt: bool) -> Vec<u8> {
        let (force_closure, moment_closure) = if normalized_mgt {
            (
                "Force closure residual: X=-1.16415321826934814e-10; Y=+0.00000000000000000e0; Z=+0.00000000000000000e0 N",
                "Moment closure residual: X=+0.00000000000000000e0; Y=-5.82076609134674072e-10; Z=+0.00000000000000000e0 N*m",
            )
        } else {
            (
                "Force closure residual: X=+0.00000000000000000e0; Y=+0.00000000000000000e0; Z=+0.00000000000000000e0 N",
                "Moment closure residual: X=+0.00000000000000000e0; Y=+0.00000000000000000e0; Z=+0.00000000000000000e0 N*m",
            )
        };
        let unsigned = format!(
            "Schema: structural-native-workbench-model-ir-linear-reaction-audit.v1\n\
             Locale: en-US\n\
             Backend: cpu / FP64 / ABI 0x0001000e / fallback 0\n\
             Tolerance policy: 256*IEEE754_BINARY64_EPSILON*max(1,absolute_contribution_scale)\n\
             {force_closure}\n\
             {moment_closure}\n\
             Force status: within_numeric_tolerance\n\
             Moment status: within_numeric_tolerance\n\
             Active equation status: within_numeric_tolerance\n\
             Overall numeric status: within_numeric_tolerance\n"
        );
        let identity = sha256_identity(unsigned.as_bytes());
        format!("{unsigned}Audit hash: {identity}\n").into_bytes()
    }

    fn nodal_displacement_view_fixture(component_units: &str) -> Vec<u8> {
        let unsigned = format!(
            "Schema: structural-native-workbench-model-ir-linear-nodal-displacement-view.v1\n\
             Locale: en-US\n\
             Displayed nodes: 1-2 of 2\n\
             Component units: {component_units}\n\
             Backend: cpu / FP64 / ABI 0x0001000e / fallback 0\n\
             000001\tN1\t0000000000\t+0.00000000000000000e0\t+0.00000000000000000e0\t+0.00000000000000000e0\t+0.00000000000000000e0\t+0.00000000000000000e0\t+0.00000000000000000e0\n\
             000002\tN2\t0000000001\t+1.00000000000000000e-3\t+0.00000000000000000e0\t+0.00000000000000000e0\t+0.00000000000000000e0\t+0.00000000000000000e0\t+0.00000000000000000e0\n\
             Boundary: bounded read-only nodal displacement components from one verified ModelIR linear CPU recovery; not a deformed-shape, stress, contour, modal, serviceability, support-design, or engineering verdict.\n"
        );
        let identity = sha256_identity(unsigned.as_bytes());
        format!("{unsigned}View hash: {identity}\n").into_bytes()
    }

    fn linear_deformed_view_fixture(projection: &str) -> Vec<u8> {
        use std::fmt::Write as _;

        let mut unsigned = format!(
            "Structural ModelIR Linear Workbench - Deformed Shape\n\
             Schema: structural-native-workbench-model-ir-linear-deformed-view.v1\n\
             Locale: en-US\n\
             Authority: bounded candidate\n\
             Profile: model_ir_linear_cpu_v1\n\
             Projection: {projection}\n\
             Viewport: 73x25 cells\n\
             Selected state: 1 of 1 (terminal linear static)\n\
             Visual magnification: 1.00000000000000000e3\n\
             Applied components: UX/UY/UZ translational displacement in m\n\
             Rotation treatment: RX/RY/RZ are reported in rad but are not applied to centerline coordinates\n\
             Inventory: nodes=2 elements=1\n\
             Backend: cpu / FP64 / ABI 0x0001000e / fallback 0\n\
             Transfer/sync counts: H2D 0 / D2H 0 / sync 0\n"
        );
        let border = format!("+{}+\n", "-".repeat(73));
        unsigned.push_str(&border);
        for _ in 0..25 {
            writeln!(unsigned, "|{}|", " ".repeat(73)).expect("write fixture canvas");
        }
        unsigned.push_str(&border);
        unsigned.push_str(concat!(
            "  000001 N1 original_xyz_m=[+0.00000000000000000e0,+0.00000000000000000e0,+0.00000000000000000e0] translation_m=[+0.00000000000000000e0,+0.00000000000000000e0,+0.00000000000000000e0] rotation_rad=[+0.00000000000000000e0,+0.00000000000000000e0,+0.00000000000000000e0] magnified_xyz_m=[+0.00000000000000000e0,+0.00000000000000000e0,+0.00000000000000000e0] original_cell=[0,0] deformed_cell=[0,0]\n",
            "  000002 N2 original_xyz_m=[+1.00000000000000000e0,+0.00000000000000000e0,+0.00000000000000000e0] translation_m=[+1.00000000000000000e-3,+0.00000000000000000e0,+0.00000000000000000e0] rotation_rad=[+0.00000000000000000e0,+0.00000000000000000e0,+0.00000000000000000e0] magnified_xyz_m=[+2.00000000000000000e0,+0.00000000000000000e0,+0.00000000000000000e0] original_cell=[72,24] deformed_cell=[72,24]\n",
            "  000001 E1 element_index=0000000000 frame_3d N1 -> N2\n",
            "Claim boundary: bounded_read_only_modelir_linear_two_node_centerline_original_and_magnified_translational_displacement_projection_not_member_curvature_rigid_offset_rotation_stress_contour_modal_serviceability_support_design_engineering_acceptance_or_design_code_compliance\n",
        ));
        let identity = sha256_identity(unsigned.as_bytes());
        format!("{unsigned}View hash: {identity}\n").into_bytes()
    }

    fn bind_rootfs_evidence_to_bundle(
        evidence: &mut RootfsIsolationEvidenceV4,
        manifest: &DistributionManifestV1,
        bundle: &Path,
    ) {
        let payload = bundle.join(PAYLOAD_DIRECTORY);
        evidence.release_id.clone_from(&manifest.release_id);
        evidence.source_sha256.clone_from(&manifest.source_sha256);
        evidence
            .bundle_manifest_hash
            .clone_from(&manifest.manifest_hash);
        evidence.bundle_manifest_file_sha256 =
            sha256_file(&bundle.join(MANIFEST_NAME)).expect("hash fixture manifest");
        evidence.installer_sha256 =
            sha256_file(&payload.join("bin/structural-installer")).expect("hash fixture installer");
        evidence.workbench_sha256 =
            sha256_file(&payload.join("bin/structural-workbench")).expect("hash fixture Workbench");
        evidence.workbench_version = "structural-workbench 0.1.0".to_owned();
    }

    fn rootfs_evidence_v1() -> RootfsIsolationEvidenceV1 {
        let mut value =
            serde_json::to_value(rootfs_evidence_v2()).expect("project v2 rootfs evidence");
        let object = value.as_object_mut().expect("rootfs evidence object");
        object.insert(
            "claim_boundary".to_owned(),
            serde_json::Value::String(ROOTFS_RECEIPT_CLAIM_BOUNDARY_V1.to_owned()),
        );
        for field in [
            "workbench_operator_surface_passed",
            "workbench_review_decision",
            "workbench_inspect_before_review_sha256",
            "workbench_review_sha256",
            "workbench_inspect_after_review_sha256",
            "workbench_export_sha256",
            "mgt_workbench_operator_surface_passed",
            "mgt_workbench_review_decision",
            "mgt_workbench_inspect_before_review_sha256",
            "mgt_workbench_review_sha256",
            "mgt_workbench_inspect_after_review_sha256",
            "mgt_workbench_export_sha256",
        ] {
            assert!(object.remove(field).is_some());
        }
        serde_json::from_value(value).expect("decode frozen v1 rootfs evidence")
    }

    #[test]
    fn bundle_is_deterministic_and_tamper_evident() {
        let temporary = TestDirectory::create("bundle");
        let first = make_bundle(&temporary, "release-1", "one");
        let payload = temporary.0.join("payload-copy");
        fs::create_dir(&payload).expect("create second payload");
        create_payload(&payload, false, LinkageV1::Shared, "one");
        let second = temporary.0.join("bundle-copy");
        let second_manifest = create_bundle(&BundleCreateRequest {
            payload_root: &payload,
            output: &second,
            release_id: "release-1",
            package_version: "0.1.0",
            backend_profile: BackendProfileV1::CpuOnly,
            linkage: LinkageV1::Shared,
            source_sha256: &format!("sha256:{:064x}", 3),
        })
        .expect("create deterministic copy");
        let first_manifest = verify_bundle(&first).expect("verify first bundle");
        assert_eq!(first_manifest, second_manifest);
        assert_eq!(
            fs::read(first.join(MANIFEST_NAME)).expect("first manifest"),
            fs::read(second.join(MANIFEST_NAME)).expect("second manifest")
        );
        let library = first
            .join(PAYLOAD_DIRECTORY)
            .join("lib/libstructural_c_abi_v1.so");
        set_mode(&library, 0o644).expect("make fixture writable for tamper");
        fs::write(&library, "tampered").expect("tamper payload");
        assert_eq!(
            verify_bundle(&first)
                .expect_err("tampered bundle must fail")
                .code,
            "bundle_payload_hash_mismatch"
        );
    }

    #[test]
    fn backend_build_identity_must_match() {
        let temporary = TestDirectory::create("backend");
        let payload = temporary.0.join("payload");
        fs::create_dir(&payload).expect("create payload");
        create_payload(&payload, false, LinkageV1::Shared, "cpu");
        let error = create_bundle(&BundleCreateRequest {
            payload_root: &payload,
            output: &temporary.0.join("bundle"),
            release_id: "rocm-1",
            package_version: "0.1.0",
            backend_profile: BackendProfileV1::Rocm,
            linkage: LinkageV1::Shared,
            source_sha256: &format!("sha256:{:064x}", 1),
        })
        .expect_err("CPU build must not become ROCm package");
        assert_eq!(error.code, "native_build_manifest_mismatch");
    }

    #[test]
    fn install_update_and_rollback_are_hash_bound() {
        let temporary = TestDirectory::create("lifecycle");
        let first = make_bundle(&temporary, "release-1", "one");
        let second = make_bundle(&temporary, "release-2", "two");
        let install = temporary.0.join("install");
        let state1 = install_bundle(&first, &install).expect("install first release");
        assert_eq!(state1.current_release, "release-1");
        assert_eq!(state1.previous_release, None);
        let state2 = install_bundle(&second, &install).expect("update second release");
        assert_eq!(state2.current_release, "release-2");
        assert_eq!(state2.previous_release.as_deref(), Some("release-1"));
        let rolled_back = rollback_install(&install).expect("rollback release");
        assert_eq!(rolled_back.current_release, "release-1");
        assert_eq!(rolled_back.previous_release.as_deref(), Some("release-2"));
        assert_eq!(
            installation_status(&install).expect("status"),
            Some(rolled_back)
        );
    }

    #[test]
    fn every_durable_install_boundary_recovers() {
        for interruption in [
            InstallInterruption::AfterPrepared,
            InstallInterruption::AfterMaterialized,
            InstallInterruption::AfterActivated,
        ] {
            let temporary = TestDirectory::create("recovery");
            let bundle = make_bundle(&temporary, "release-1", "one");
            let install = temporary.0.join("install");
            let error = install_bundle_inner(&bundle, &install, interruption)
                .expect_err("injected interruption must stop install");
            assert_eq!(error.code, "simulated_interruption");
            assert_eq!(
                installation_status(&install)
                    .expect_err("pending transaction makes status non-authoritative")
                    .code,
                "recovery_required"
            );
            let recovered = recover_install(&install).expect("recover interrupted install");
            assert_eq!(recovered.current_release, "release-1");
            assert_eq!(
                installation_status(&install).expect("status"),
                Some(recovered)
            );
        }
    }

    #[test]
    fn release_ids_are_immutable() {
        let temporary = TestDirectory::create("immutable");
        let first = make_bundle(&temporary, "release-1", "one");
        let install = temporary.0.join("install");
        install_bundle(&first, &install).expect("install release");
        let payload = temporary.0.join("replacement-payload");
        fs::create_dir(&payload).expect("replacement payload");
        create_payload(&payload, false, LinkageV1::Shared, "different");
        let replacement = temporary.0.join("replacement-bundle");
        create_bundle(&BundleCreateRequest {
            payload_root: &payload,
            output: &replacement,
            release_id: "release-1",
            package_version: "0.1.0",
            backend_profile: BackendProfileV1::CpuOnly,
            linkage: LinkageV1::Shared,
            source_sha256: &format!("sha256:{:064x}", 99),
        })
        .expect("create replacement");
        assert_eq!(
            install_bundle(&replacement, &install)
                .expect_err("release identity reuse must fail")
                .code,
            "release_id_immutable"
        );
    }

    #[test]
    fn activation_generation_overflow_fails_closed() {
        let state = ActivationStateV1 {
            schema_version: ACTIVATION_SCHEMA_VERSION.to_owned(),
            generation: u64::MAX,
            current_release: "release-1".to_owned(),
            previous_release: None,
            current_manifest_hash: format!("sha256:{:064x}", 1),
        };
        assert_eq!(
            next_generation(Some(&state))
                .expect_err("generation overflow must fail")
                .code,
            "activation_generation_overflow"
        );
    }

    #[test]
    #[allow(clippy::too_many_lines)]
    fn rootfs_receipt_is_exact_hash_bound_and_non_promoting() {
        let frozen_v1 = rootfs_evidence_v1();
        validate_rootfs_isolation_evidence_v1(&frozen_v1)
            .expect("frozen v1 evidence remains verifiable");
        let frozen_v1_hash =
            sha256_identity(&canonical_json(&frozen_v1).expect("canonical frozen v1 evidence"));
        validate_sha256_identity(&frozen_v1_hash, "frozen v1 receipt hash")
            .expect("frozen v1 receipt hash");

        validate_rootfs_isolation_evidence_v2(&rootfs_evidence_v2())
            .expect("frozen v2 evidence remains verifiable");
        validate_rootfs_isolation_evidence_v3(&rootfs_evidence_v3())
            .expect("frozen v3 evidence remains verifiable");
        validate_rootfs_isolation_evidence_v4(&rootfs_evidence_v4())
            .expect("frozen v4 evidence remains verifiable");
        validate_rootfs_isolation_evidence_v5(&rootfs_evidence_v5())
            .expect("frozen v5 evidence remains verifiable");
        validate_rootfs_isolation_evidence_v6(&rootfs_evidence_v6())
            .expect("frozen v6 evidence remains verifiable");
        validate_rootfs_isolation_evidence_v7(&rootfs_evidence_v7())
            .expect("frozen v7 evidence remains verifiable");
        validate_rootfs_isolation_evidence_v8(&rootfs_evidence_v8())
            .expect("frozen v8 evidence remains verifiable");
        validate_rootfs_isolation_evidence_v9(&rootfs_evidence_v9())
            .expect("frozen v9 evidence remains verifiable");
        validate_rootfs_isolation_evidence_v10(&rootfs_evidence_v10())
            .expect("frozen v10 evidence remains verifiable");

        let evidence = rootfs_evidence();
        validate_rootfs_isolation_evidence_v11(&evidence).expect("valid bounded evidence");
        let receipt = seal_rootfs_isolation_evidence_v11(evidence.clone()).expect("seal evidence");
        assert_eq!(receipt.schema_version, ROOTFS_RECEIPT_SCHEMA_VERSION_V11);
        assert_eq!(
            receipt.receipt_hash,
            sha256_identity(&canonical_json(&evidence).expect("canonical evidence"))
        );
        assert!(
            !receipt
                .evidence
                .prior
                .prior
                .prior
                .prior
                .prior
                .prior
                .prior
                .container_image_built
        );
        assert!(
            !receipt
                .evidence
                .prior
                .prior
                .prior
                .prior
                .prior
                .prior
                .prior
                .customer_image_receipt
        );

        let mut promoting = evidence.clone();
        promoting
            .prior
            .prior
            .prior
            .prior
            .prior
            .prior
            .prior
            .model_ir_linear_workbench_review_decision = "pass".to_owned();
        assert_eq!(
            validate_rootfs_isolation_evidence_v11(&promoting)
                .expect_err("promoting review decision must fail closed")
                .code,
            "rootfs_receipt_contract_invalid"
        );

        let mut colliding_view = evidence.clone();
        colliding_view
            .prior
            .prior
            .prior
            .model_ir_linear_reaction_view_ko_kr_sha256 = colliding_view
            .prior
            .prior
            .prior
            .model_ir_linear_reaction_view_en_us_sha256
            .clone();
        assert_eq!(
            validate_rootfs_isolation_evidence_v11(&colliding_view)
                .expect_err("colliding reaction view identities must fail closed")
                .code,
            "rootfs_receipt_contract_invalid"
        );

        let mut colliding_audit = evidence.clone();
        colliding_audit
            .prior
            .prior
            .model_ir_linear_reaction_audit_ko_kr_sha256 = colliding_audit
            .prior
            .prior
            .model_ir_linear_reaction_audit_en_us_sha256
            .clone();
        assert_eq!(
            validate_rootfs_isolation_evidence_v11(&colliding_audit)
                .expect_err("colliding reaction audit identities must fail closed")
                .code,
            "rootfs_receipt_contract_invalid"
        );

        let mut colliding_displacement = evidence.clone();
        colliding_displacement
            .prior
            .model_ir_linear_nodal_displacement_view_window_sha256 = colliding_displacement
            .prior
            .model_ir_linear_nodal_displacement_view_en_us_sha256
            .clone();
        assert_eq!(
            validate_rootfs_isolation_evidence_v11(&colliding_displacement)
                .expect_err("colliding displacement view identities must fail closed")
                .code,
            "rootfs_receipt_contract_invalid"
        );

        let mut colliding_deformed = evidence.clone();
        colliding_deformed.model_ir_linear_deformed_view_projection_sha256 = colliding_deformed
            .model_ir_linear_deformed_view_en_us_sha256
            .clone();
        assert_eq!(
            validate_rootfs_isolation_evidence_v11(&colliding_deformed)
                .expect_err("colliding deformed-view identities must fail closed")
                .code,
            "rootfs_receipt_contract_invalid"
        );

        let mut weakened = evidence;
        weakened
            .prior
            .prior
            .prior
            .prior
            .prior
            .prior
            .prior
            .network_interfaces
            .push("eth0".to_owned());
        assert_eq!(
            validate_rootfs_isolation_evidence_v11(&weakened)
                .expect_err("external interface must fail closed")
                .code,
            "rootfs_receipt_contract_invalid"
        );
    }

    #[test]
    fn rootfs_reaction_view_artifact_is_self_hashed_and_typed() {
        let temporary = TestDirectory::create("rootfs-reaction-view");
        let workspace = temporary.0.canonicalize().expect("resolve workspace");
        let view = workspace.join("reaction-view.txt");
        fs::write(&view, reaction_view_fixture("N")).expect("write valid reaction view");
        let artifact = inspect_reaction_view_artifact(
            &workspace,
            &view,
            "en-US",
            1,
            6,
            6,
            "fixture reaction view",
        )
        .expect("inspect valid reaction view");
        assert_eq!(artifact.sha256, sha256_file(&view).expect("hash fixture"));

        let mut tampered = reaction_view_fixture("N");
        tampered[0] = b'X';
        fs::write(&view, tampered).expect("write tampered reaction view");
        assert_eq!(
            inspect_reaction_view_artifact(
                &workspace,
                &view,
                "en-US",
                1,
                6,
                6,
                "tampered reaction view",
            )
            .expect_err("tampered view must fail")
            .code,
            "rootfs_reaction_view_hash_mismatch"
        );

        fs::write(&view, reaction_view_fixture("Pa")).expect("write wrong-unit view");
        assert_eq!(
            inspect_reaction_view_artifact(
                &workspace,
                &view,
                "en-US",
                1,
                6,
                6,
                "wrong-unit reaction view",
            )
            .expect_err("wrong unit must fail")
            .code,
            "rootfs_reaction_view_row_invalid"
        );
    }

    #[test]
    fn rootfs_nodal_displacement_view_artifact_is_self_hashed_and_typed() {
        let temporary = TestDirectory::create("rootfs-nodal-displacement-view");
        let workspace = temporary.0.canonicalize().expect("resolve workspace");
        let view = workspace.join("nodal-displacement-view.txt");
        fs::write(
            &view,
            nodal_displacement_view_fixture("UX/UY/UZ=m; RX/RY/RZ=rad"),
        )
        .expect("write valid nodal displacement view");
        let artifact = inspect_nodal_displacement_view_artifact(
            &workspace,
            &view,
            "en-US",
            1,
            2,
            2,
            "fixture nodal displacement view",
        )
        .expect("inspect valid nodal displacement view");
        assert_eq!(artifact.sha256, sha256_file(&view).expect("hash fixture"));

        let mut tampered = nodal_displacement_view_fixture("UX/UY/UZ=m; RX/RY/RZ=rad");
        tampered[0] = b'X';
        fs::write(&view, tampered).expect("write tampered displacement view");
        assert_eq!(
            inspect_nodal_displacement_view_artifact(
                &workspace,
                &view,
                "en-US",
                1,
                2,
                2,
                "tampered nodal displacement view",
            )
            .expect_err("tampered displacement view must fail")
            .code,
            "rootfs_nodal_displacement_view_hash_mismatch"
        );

        fs::write(
            &view,
            nodal_displacement_view_fixture("UX/UY/UZ=mm; RX/RY/RZ=rad"),
        )
        .expect("write wrong-unit displacement view");
        assert_eq!(
            inspect_nodal_displacement_view_artifact(
                &workspace,
                &view,
                "en-US",
                1,
                2,
                2,
                "wrong-unit nodal displacement view",
            )
            .expect_err("wrong displacement units must fail")
            .code,
            "rootfs_nodal_displacement_view_contract_invalid"
        );
    }

    #[test]
    fn rootfs_nodal_displacement_wrong_profile_failure_is_exact() {
        let temporary = TestDirectory::create("rootfs-nodal-displacement-failure");
        let workspace = temporary.0.canonicalize().expect("resolve workspace");
        let failure = workspace.join("nodal-displacement-failure.json");
        fs::write(
            &failure,
            b"{\"code\":\"workbench_profile_unsupported\",\"detail\":\"nodal displacement view requires ModelIR linear CPU\",\"schema_version\":\"structural-native-workbench-failure.v1\"}\n",
        )
        .expect("write exact displacement failure");
        inspect_nodal_displacement_view_wrong_profile_failure(&workspace, &failure)
            .expect("accept exact displacement failure");

        fs::write(
            &failure,
            b"{\"code\":\"workbench_profile_unsupported\",\"detail\":\"nodal displacement view requires ModelIR linear CPU\",\"extra\":true,\"schema_version\":\"structural-native-workbench-failure.v1\"}\n",
        )
        .expect("write widened displacement failure");
        assert_eq!(
            inspect_nodal_displacement_view_wrong_profile_failure(&workspace, &failure)
                .expect_err("widened displacement failure must be rejected")
                .code,
            "rootfs_nodal_displacement_view_failure_invalid"
        );
    }

    #[test]
    fn rootfs_linear_deformed_view_is_self_hashed_and_geometry_bound() {
        assert!(!contains_nonfinite_number_token(
            "Model provenance hash: sha256:0123456789abcdef"
        ));
        assert!(contains_nonfinite_number_token(
            "translation_m=[+NaN,+0.0,+0.0]"
        ));
        let temporary = TestDirectory::create("rootfs-linear-deformed-view");
        let workspace = temporary.0.canonicalize().expect("resolve workspace");
        let view = workspace.join("linear-deformed-view.txt");
        fs::write(&view, linear_deformed_view_fixture("xy"))
            .expect("write valid linear deformed view");
        let artifact = inspect_linear_deformed_view_artifact(
            &workspace,
            &view,
            "en-US",
            "xy",
            "fixture linear deformed view",
        )
        .expect("inspect valid linear deformed view");
        assert_eq!(artifact.sha256, sha256_file(&view).expect("hash fixture"));

        let mut tampered = linear_deformed_view_fixture("xy");
        tampered[0] = b'X';
        fs::write(&view, tampered).expect("write tampered linear deformed view");
        assert_eq!(
            inspect_linear_deformed_view_artifact(
                &workspace,
                &view,
                "en-US",
                "xy",
                "tampered linear deformed view",
            )
            .expect_err("tampered linear deformed view must fail")
            .code,
            "rootfs_linear_deformed_view_hash_mismatch"
        );

        fs::write(&view, linear_deformed_view_fixture("xz"))
            .expect("write wrong-projection linear deformed view");
        assert_eq!(
            inspect_linear_deformed_view_artifact(
                &workspace,
                &view,
                "en-US",
                "xy",
                "wrong-projection linear deformed view",
            )
            .expect_err("wrong projection must fail")
            .code,
            "rootfs_linear_deformed_view_contract_invalid"
        );
    }

    #[test]
    fn rootfs_linear_deformed_view_invalid_step_failure_is_exact() {
        let temporary = TestDirectory::create("rootfs-linear-deformed-view-failure");
        let workspace = temporary.0.canonicalize().expect("resolve workspace");
        let failure = workspace.join("linear-deformed-view-failure.json");
        fs::write(
            &failure,
            b"{\"code\":\"workbench_deformed_view_step_invalid\",\"detail\":\"linear static deformed view only supports step 1\",\"schema_version\":\"structural-native-workbench-failure.v1\"}\n",
        )
        .expect("write exact invalid-step failure");
        inspect_linear_deformed_view_invalid_step_failure(&workspace, &failure)
            .expect("accept exact invalid-step failure");

        fs::write(
            &failure,
            b"{\"code\":\"workbench_deformed_view_step_invalid\",\"detail\":\"linear static deformed view only supports step 1\",\"extra\":true,\"schema_version\":\"structural-native-workbench-failure.v1\"}\n",
        )
        .expect("write widened invalid-step failure");
        assert_eq!(
            inspect_linear_deformed_view_invalid_step_failure(&workspace, &failure)
                .expect_err("widened invalid-step failure must be rejected")
                .code,
            "rootfs_linear_deformed_view_failure_invalid"
        );
    }

    #[test]
    fn rootfs_reaction_audit_artifact_is_self_hashed_and_closure_bound() {
        let temporary = TestDirectory::create("rootfs-reaction-audit");
        let workspace = temporary.0.canonicalize().expect("resolve workspace");
        let audit = workspace.join("reaction-audit.txt");
        fs::write(&audit, reaction_audit_fixture(false)).expect("write valid reaction audit");
        let artifact = inspect_reaction_audit_artifact(
            &workspace,
            &audit,
            "en-US",
            false,
            "fixture reaction audit",
        )
        .expect("inspect valid reaction audit");
        assert_eq!(artifact.sha256, sha256_file(&audit).expect("hash fixture"));

        let mut tampered = reaction_audit_fixture(false);
        tampered[0] = b'X';
        fs::write(&audit, tampered).expect("write tampered reaction audit");
        assert_eq!(
            inspect_reaction_audit_artifact(
                &workspace,
                &audit,
                "en-US",
                false,
                "tampered reaction audit",
            )
            .expect_err("tampered audit must fail")
            .code,
            "rootfs_reaction_audit_hash_mismatch"
        );

        fs::write(&audit, reaction_audit_fixture(true)).expect("write wrong-closure audit");
        assert_eq!(
            inspect_reaction_audit_artifact(
                &workspace,
                &audit,
                "en-US",
                false,
                "wrong-closure reaction audit",
            )
            .expect_err("wrong closure must fail")
            .code,
            "rootfs_reaction_audit_contract_invalid"
        );
    }

    #[test]
    fn rootfs_reaction_audit_wrong_profile_failure_is_exact() {
        let temporary = TestDirectory::create("rootfs-reaction-audit-failure");
        let workspace = temporary.0.canonicalize().expect("resolve workspace");
        let failure = workspace.join("reaction-audit-failure.json");
        fs::write(
            &failure,
            b"{\"code\":\"workbench_profile_unsupported\",\"detail\":\"reaction audit requires ModelIR linear CPU\",\"schema_version\":\"structural-native-workbench-failure.v1\"}\n",
        )
        .expect("write exact wrong-profile failure");
        inspect_reaction_audit_wrong_profile_failure(&workspace, &failure)
            .expect("accept exact wrong-profile failure");

        fs::write(
            &failure,
            b"{\"code\":\"workbench_profile_unsupported\",\"detail\":\"reaction audit requires ModelIR linear CPU\",\"extra\":true,\"schema_version\":\"structural-native-workbench-failure.v1\"}\n",
        )
        .expect("write widened wrong-profile failure");
        assert_eq!(
            inspect_reaction_audit_wrong_profile_failure(&workspace, &failure)
                .expect_err("widened failure must be rejected")
                .code,
            "rootfs_reaction_audit_failure_invalid"
        );
    }

    #[test]
    fn frozen_rootfs_v5_receipt_remains_bundle_verifiable() {
        let temporary = TestDirectory::create("rootfs-v5-receipt");
        let bundle = make_bundle(&temporary, "rootfs-v5-release", "v5");
        let manifest = verify_bundle(&bundle).expect("verify v5 fixture bundle");
        let mut evidence = rootfs_evidence_v5();
        bind_rootfs_evidence_to_bundle(&mut evidence.prior, &manifest, &bundle);
        validate_rootfs_isolation_evidence_v5(&evidence).expect("validate frozen v5 evidence");
        let receipt = RootfsIsolationReceiptV5 {
            schema_version: ROOTFS_RECEIPT_SCHEMA_VERSION_V5.to_owned(),
            receipt_hash: sha256_identity(
                &canonical_json(&evidence).expect("canonical frozen v5 evidence"),
            ),
            evidence,
        };
        let receipt_path = temporary.0.join("rootfs-v5-receipt.json");
        fs::write(
            &receipt_path,
            canonical_json(&receipt).expect("canonical frozen v5 receipt"),
        )
        .expect("write frozen v5 receipt");
        assert!(matches!(
            verify_rootfs_isolation_receipt(&receipt_path, &bundle)
                .expect("verify frozen v5 receipt against its bundle"),
            VerifiedRootfsIsolationReceipt::V5(_)
        ));
    }

    #[test]
    fn frozen_rootfs_v6_receipt_remains_bundle_verifiable() {
        let temporary = TestDirectory::create("rootfs-v6-receipt");
        let bundle = make_bundle(&temporary, "rootfs-v6-release", "v6");
        let manifest = verify_bundle(&bundle).expect("verify v6 fixture bundle");
        let mut evidence = rootfs_evidence_v6();
        bind_rootfs_evidence_to_bundle(&mut evidence.prior.prior, &manifest, &bundle);
        validate_rootfs_isolation_evidence_v6(&evidence).expect("validate frozen v6 evidence");
        let receipt = RootfsIsolationReceiptV6 {
            schema_version: ROOTFS_RECEIPT_SCHEMA_VERSION_V6.to_owned(),
            receipt_hash: sha256_identity(
                &canonical_json(&evidence).expect("canonical frozen v6 evidence"),
            ),
            evidence,
        };
        let receipt_path = temporary.0.join("rootfs-v6-receipt.json");
        fs::write(
            &receipt_path,
            canonical_json(&receipt).expect("canonical frozen v6 receipt"),
        )
        .expect("write frozen v6 receipt");
        assert!(matches!(
            verify_rootfs_isolation_receipt(&receipt_path, &bundle)
                .expect("verify frozen v6 receipt against its bundle"),
            VerifiedRootfsIsolationReceipt::V6(_)
        ));
    }

    #[test]
    fn frozen_rootfs_v7_receipt_remains_bundle_verifiable() {
        let temporary = TestDirectory::create("rootfs-v7-receipt");
        let bundle = make_bundle(&temporary, "rootfs-v7-release", "v7");
        let manifest = verify_bundle(&bundle).expect("verify v7 fixture bundle");
        let mut evidence = rootfs_evidence_v7();
        bind_rootfs_evidence_to_bundle(&mut evidence.prior.prior.prior, &manifest, &bundle);
        validate_rootfs_isolation_evidence_v7(&evidence).expect("validate frozen v7 evidence");
        let receipt = RootfsIsolationReceiptV7 {
            schema_version: ROOTFS_RECEIPT_SCHEMA_VERSION_V7.to_owned(),
            receipt_hash: sha256_identity(
                &canonical_json(&evidence).expect("canonical frozen v7 evidence"),
            ),
            evidence,
        };
        let receipt_path = temporary.0.join("rootfs-v7-receipt.json");
        fs::write(
            &receipt_path,
            canonical_json(&receipt).expect("canonical v7 receipt"),
        )
        .expect("write current v7 receipt");
        assert!(matches!(
            verify_rootfs_isolation_receipt(&receipt_path, &bundle)
                .expect("verify current v7 receipt against its bundle"),
            VerifiedRootfsIsolationReceipt::V7(_)
        ));
    }

    #[test]
    fn frozen_rootfs_v8_receipt_remains_bundle_verifiable() {
        let temporary = TestDirectory::create("rootfs-v8-receipt");
        let bundle = make_bundle(&temporary, "rootfs-v8-release", "v8");
        let manifest = verify_bundle(&bundle).expect("verify v8 fixture bundle");
        let mut evidence = rootfs_evidence_v8();
        bind_rootfs_evidence_to_bundle(&mut evidence.prior.prior.prior.prior, &manifest, &bundle);
        validate_rootfs_isolation_evidence_v8(&evidence).expect("validate frozen v8 evidence");
        let receipt = RootfsIsolationReceiptV8 {
            schema_version: ROOTFS_RECEIPT_SCHEMA_VERSION_V8.to_owned(),
            receipt_hash: sha256_identity(
                &canonical_json(&evidence).expect("canonical frozen v8 evidence"),
            ),
            evidence,
        };
        let receipt_path = temporary.0.join("rootfs-v8-receipt.json");
        fs::write(
            &receipt_path,
            canonical_json(&receipt).expect("canonical v8 receipt"),
        )
        .expect("write current v8 receipt");
        assert!(matches!(
            verify_rootfs_isolation_receipt(&receipt_path, &bundle)
                .expect("verify current v8 receipt against its bundle"),
            VerifiedRootfsIsolationReceipt::V8(_)
        ));
    }

    #[test]
    fn frozen_rootfs_v9_receipt_remains_bundle_verifiable() {
        let temporary = TestDirectory::create("rootfs-v9-receipt");
        let bundle = make_bundle(&temporary, "rootfs-v9-release", "v9");
        let manifest = verify_bundle(&bundle).expect("verify v9 fixture bundle");
        let mut evidence = rootfs_evidence_v9();
        bind_rootfs_evidence_to_bundle(
            &mut evidence.prior.prior.prior.prior.prior,
            &manifest,
            &bundle,
        );
        validate_rootfs_isolation_evidence_v9(&evidence).expect("validate frozen v9 evidence");
        let receipt = seal_rootfs_isolation_evidence_v9(evidence).expect("seal v9 evidence");
        let receipt_path = temporary.0.join("rootfs-v9-receipt.json");
        fs::write(
            &receipt_path,
            canonical_json(&receipt).expect("canonical v9 receipt"),
        )
        .expect("write frozen v9 receipt");
        assert!(matches!(
            verify_rootfs_isolation_receipt(&receipt_path, &bundle)
                .expect("verify frozen v9 receipt against its bundle"),
            VerifiedRootfsIsolationReceipt::V9(_)
        ));
    }

    #[test]
    fn frozen_rootfs_v10_receipt_remains_bundle_verifiable() {
        let temporary = TestDirectory::create("rootfs-v10-receipt");
        let bundle = make_bundle(&temporary, "rootfs-v10-release", "v10");
        let manifest = verify_bundle(&bundle).expect("verify v10 fixture bundle");
        let mut evidence = rootfs_evidence_v10();
        bind_rootfs_evidence_to_bundle(
            &mut evidence.prior.prior.prior.prior.prior.prior,
            &manifest,
            &bundle,
        );
        validate_rootfs_isolation_evidence_v10(&evidence).expect("validate current v10 evidence");
        let receipt = seal_rootfs_isolation_evidence_v10(evidence).expect("seal v10 evidence");
        let receipt_path = temporary.0.join("rootfs-v10-receipt.json");
        fs::write(
            &receipt_path,
            canonical_json(&receipt).expect("canonical v10 receipt"),
        )
        .expect("write current v10 receipt");
        assert!(matches!(
            verify_rootfs_isolation_receipt(&receipt_path, &bundle)
                .expect("verify current v10 receipt against its bundle"),
            VerifiedRootfsIsolationReceipt::V10(_)
        ));
    }

    #[test]
    fn current_rootfs_v11_receipt_is_bundle_verifiable() {
        let temporary = TestDirectory::create("rootfs-v11-receipt");
        let bundle = make_bundle(&temporary, "rootfs-v11-release", "v11");
        let manifest = verify_bundle(&bundle).expect("verify v11 fixture bundle");
        let mut evidence = rootfs_evidence();
        bind_rootfs_evidence_to_bundle(
            &mut evidence.prior.prior.prior.prior.prior.prior.prior,
            &manifest,
            &bundle,
        );
        validate_rootfs_isolation_evidence_v11(&evidence).expect("validate current v11 evidence");
        let receipt = seal_rootfs_isolation_evidence_v11(evidence).expect("seal v11 evidence");
        let receipt_path = temporary.0.join("rootfs-v11-receipt.json");
        fs::write(
            &receipt_path,
            canonical_json(&receipt).expect("canonical v11 receipt"),
        )
        .expect("write current v11 receipt");
        assert!(matches!(
            verify_rootfs_isolation_receipt(&receipt_path, &bundle)
                .expect("verify current v11 receipt against its bundle"),
            VerifiedRootfsIsolationReceipt::V11(_)
        ));
    }

    #[test]
    fn current_rootfs_v12_receipt_is_bundle_verifiable_and_fail_closed() {
        let temporary = TestDirectory::create("rootfs-v12-receipt");
        let bundle = make_bundle(&temporary, "rootfs-v12-release", "v12");
        let manifest = verify_bundle(&bundle).expect("verify v12 fixture bundle");
        let mut evidence = rootfs_evidence_v12();
        bind_rootfs_evidence_to_bundle(
            &mut evidence.prior.prior.prior.prior.prior.prior.prior.prior,
            &manifest,
            &bundle,
        );
        validate_rootfs_isolation_evidence_v12(&evidence).expect("validate current v12 evidence");
        let receipt =
            seal_rootfs_isolation_evidence_v12(evidence.clone()).expect("seal v12 evidence");
        let receipt_path = temporary.0.join("rootfs-v12-receipt.json");
        fs::write(
            &receipt_path,
            canonical_json(&receipt).expect("canonical v12 receipt"),
        )
        .expect("write current v12 receipt");
        assert!(matches!(
            verify_rootfs_isolation_receipt(&receipt_path, &bundle)
                .expect("verify current v12 receipt against its bundle"),
            VerifiedRootfsIsolationReceipt::V12(_)
        ));

        let mut colliding = evidence;
        colliding.mgt_model_ir_linear_element_recovery_view_en_us_sha256 = colliding
            .model_ir_linear_element_recovery_view_en_us_sha256
            .clone();
        assert_eq!(
            validate_rootfs_isolation_evidence_v12(&colliding)
                .expect_err("colliding element recovery identities must fail closed")
                .code,
            "rootfs_receipt_contract_invalid"
        );
    }

    #[test]
    fn current_rootfs_v13_receipt_is_bundle_verifiable_and_fail_closed() {
        let temporary = TestDirectory::create("rootfs-v13-receipt");
        let bundle = make_bundle(&temporary, "rootfs-v13-release", "v13");
        let manifest = verify_bundle(&bundle).expect("verify v13 fixture bundle");
        let mut evidence = rootfs_evidence_v13();
        bind_rootfs_evidence_to_bundle(
            &mut evidence
                .prior
                .prior
                .prior
                .prior
                .prior
                .prior
                .prior
                .prior
                .prior,
            &manifest,
            &bundle,
        );
        evidence.structural_cli_sha256 =
            sha256_file(&bundle.join("payload/bin/structural-cli")).expect("hash fixture CLI");
        validate_rootfs_isolation_evidence_v13(&evidence).expect("validate current v13 evidence");
        let receipt = seal_rootfs_isolation_evidence(evidence.clone()).expect("seal v13 evidence");
        let receipt_path = temporary.0.join("rootfs-v13-receipt.json");
        fs::write(
            &receipt_path,
            canonical_json(&receipt).expect("canonical v13 receipt"),
        )
        .expect("write current v13 receipt");
        assert!(matches!(
            verify_rootfs_isolation_receipt(&receipt_path, &bundle)
                .expect("verify current v13 receipt against its bundle"),
            VerifiedRootfsIsolationReceipt::V13(_)
        ));

        let mut colliding = evidence;
        colliding.workbench_model_modal_result_view_ko_kr_sha256 = colliding
            .workbench_model_modal_result_view_en_us_sha256
            .clone();
        assert_eq!(
            validate_rootfs_isolation_evidence_v13(&colliding)
                .expect_err("colliding modal result view identities must fail closed")
                .code,
            "rootfs_receipt_contract_invalid"
        );
    }

    #[cfg(unix)]
    #[test]
    fn install_rejects_symlinked_internal_directories() {
        use std::os::unix::fs::symlink;

        for name in [RELEASES_DIRECTORY, STATE_DIRECTORY] {
            let temporary = TestDirectory::create("install-symlink");
            let bundle = make_bundle(&temporary, "release-1", "one");
            let install = temporary.0.join("install");
            let redirected = temporary.0.join("redirected");
            fs::create_dir(&install).expect("create install root");
            fs::create_dir(&redirected).expect("create redirect target");
            symlink(&redirected, install.join(name)).expect("create internal directory symlink");
            assert_eq!(
                install_bundle(&bundle, &install)
                    .expect_err("internal directory symlink must fail")
                    .code,
                "install_subdirectory_invalid"
            );
        }
    }

    #[cfg(unix)]
    #[test]
    fn bundle_creation_rejects_external_symlink() {
        use std::os::unix::fs::symlink;

        let temporary = TestDirectory::create("symlink");
        let payload = temporary.0.join("payload");
        fs::create_dir(&payload).expect("create payload");
        create_payload(&payload, false, LinkageV1::Shared, "one");
        symlink("/etc/passwd", payload.join("escaped")).expect("create external symlink fixture");
        assert_eq!(
            create_bundle(&BundleCreateRequest {
                payload_root: &payload,
                output: &temporary.0.join("bundle"),
                release_id: "release-1",
                package_version: "0.1.0",
                backend_profile: BackendProfileV1::CpuOnly,
                linkage: LinkageV1::Shared,
                source_sha256: &format!("sha256:{:064x}", 1),
            })
            .expect_err("external symlink must fail")
            .code,
            "payload_symlink_escape"
        );
    }
}
