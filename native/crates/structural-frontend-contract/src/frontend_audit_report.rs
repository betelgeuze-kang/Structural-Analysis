use std::collections::{BTreeMap, VecDeque};
use std::ffi::OsString;
use std::io::{self, Read};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::thread;

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use structural_contracts::model_ir::{canonicalize_model_ir_v2, decode_json_strict};
use structural_contracts::product_ir::sha256_identity;
use time::format_description::well_known::Rfc3339;
use time::OffsetDateTime;

use super::verified_publication::{
    prepare_verified_publication_target, publish_verified_outputs, VerifiedOutput,
    VerifiedPublicationCodes, VerifiedPublicationTarget, VERIFIED_PUBLICATION_STRATEGY,
};
use super::{
    canonical_struct, check_frontend_contract, parse_source_map, verify_real_directory,
    FrontendContractError, SOURCE_MAP_BYTES,
};

const CONTRACT_SCHEMA_V1: &str = "structural-native-frontend-audit-report-contract.v1";
const RECEIPT_SCHEMA_V1: &str = "structural-native-frontend-audit-report-receipt.v1";
const REPORT_SCHEMA_V1: &str = "frontend-dependency-audit-report.v1";
const EXPECTED_NPM_LAUNCHER: &str = "npm";
const EXPECTED_ARGUMENTS: [&str; 2] = ["audit", "--json"];
const EXPECTED_MAXIMUM_STDOUT_BYTES: u64 = 8 * 1024 * 1024;
const EXPECTED_STDERR_TAIL_CHARACTERS: u64 = 2_000;
const STDERR_TAIL_CHARACTERS: usize = 2_000;
const MAXIMUM_PREVIOUS_REPORT_BYTES: u64 = 32 * 1024 * 1024;
const MAXIMUM_REPORT_BYTES: usize = 16 * 1024 * 1024;
const STDERR_TAIL_BYTES: usize = 4 * STDERR_TAIL_CHARACTERS + 4;
const VULNERABILITY_LEVELS: [&str; 5] = ["info", "low", "moderate", "high", "critical"];
const REPORT_CLAIM_BOUNDARY: &str = "This report records npm audit release evidence for the frontend dependency graph. It does not replace secrets, license, SBOM, or reproducible-build checks in the PM security gate.";

const PUBLICATION_CODES: VerifiedPublicationCodes = VerifiedPublicationCodes {
    output_invalid: "frontend_audit_report_output_invalid",
    output_changed: "frontend_audit_report_output_changed",
    stage_failed: "frontend_audit_report_stage_failed",
    publish_failed: "frontend_audit_report_publish_failed",
    backup_cleanup_failed: "frontend_audit_report_backup_cleanup_failed",
};

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct FrontendAuditReportSourceV1 {
    schema_version: String,
    npm_launcher: String,
    arguments: Vec<String>,
    maximum_stdout_bytes: u64,
    stderr_tail_characters: u64,
    network_access_accounting: String,
    filesystem_mutation_accounting: String,
    environment_accounting: String,
    claim_boundary: String,
}

/// Inputs for one native frontend dependency-audit report execution.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct FrontendAuditReportOptions {
    pub root: PathBuf,
    pub package_json: PathBuf,
    pub package_lock: PathBuf,
    pub output: PathBuf,
}

impl FrontendAuditReportOptions {
    #[must_use]
    pub fn new(root: PathBuf, output: PathBuf) -> Self {
        Self {
            root,
            package_json: PathBuf::from("package.json"),
            package_lock: PathBuf::from("package-lock.json"),
            output,
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[allow(clippy::struct_excessive_bools)] // Fixed compatibility schema consumed by PM readers.
pub struct FrontendAuditReportChecksV1 {
    pub package_json_present: bool,
    pub package_lock_present: bool,
    pub npm_audit_json_parse_pass: bool,
    pub dependency_vulnerability_total_zero_pass: bool,
    pub dependency_high_or_critical_zero_pass: bool,
    pub npm_audit_exit_code_zero_pass: bool,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct FrontendAuditReportSummaryV1 {
    pub package_json: String,
    pub package_lock: String,
    pub npm_audit_exit_code: i32,
    pub vulnerability_total: u64,
    pub high_or_critical_vulnerability_count: u64,
    pub info_vulnerability_count: u64,
    pub low_vulnerability_count: u64,
    pub moderate_vulnerability_count: u64,
    pub high_vulnerability_count: u64,
    pub critical_vulnerability_count: u64,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct FrontendAuditViaV1 {
    pub title: String,
    pub severity: String,
    pub url: String,
    pub range: String,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct FrontendAuditVulnerabilityV1 {
    pub name: String,
    pub severity: String,
    pub range: String,
    pub is_direct: bool,
    pub fix_available: Value,
    pub via: Vec<FrontendAuditViaV1>,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct FrontendAuditReportDiagnosticsV1 {
    pub npm_audit_stdout_bytes: u64,
    pub npm_audit_stderr_tail: String,
}

/// Compatibility report consumed by the retained PM release-gate readers.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct FrontendDependencyAuditReportV1 {
    pub schema_version: String,
    pub generated_at: String,
    pub contract_pass: bool,
    pub reason_code: String,
    pub blockers: Vec<String>,
    pub checks: FrontendAuditReportChecksV1,
    pub summary: FrontendAuditReportSummaryV1,
    pub vulnerabilities: Vec<FrontendAuditVulnerabilityV1>,
    pub diagnostics: FrontendAuditReportDiagnosticsV1,
    pub claim_boundary: String,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct FrontendAuditPublishedReportV1 {
    pub path: String,
    pub byte_length: u64,
    pub sha256: String,
    pub publication_strategy: String,
}

/// Canonical native receipt for one published compatibility audit report.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct FrontendAuditReportReceiptV1 {
    pub schema_version: String,
    pub action: String,
    pub status: String,
    pub source_map_sha256: String,
    pub frontend_contract_receipt_hash: String,
    pub logical_command: Vec<String>,
    pub process_launcher: String,
    pub node_options_disposition: String,
    pub direct_processes_spawned: u64,
    pub observed_exit_code: i32,
    pub report: FrontendAuditPublishedReportV1,
    pub contract_pass: bool,
    pub reason_code: String,
    pub blocker_count: u64,
    pub vulnerability_total: u64,
    pub high_or_critical_vulnerability_count: u64,
    pub network_access_accounting: String,
    pub filesystem_mutation_accounting: String,
    pub environment_accounting: String,
    pub deterministic_receipt: bool,
    pub claim_boundary: String,
    pub receipt_hash: String,
}

struct PreparedFrontendAuditReport {
    source: FrontendAuditReportSourceV1,
    root: PathBuf,
    package_json: String,
    package_lock: String,
    output: VerifiedPublicationTarget,
    frontend_contract_receipt_hash: String,
}

struct PrefixCapture {
    bytes: Vec<u8>,
    total_bytes: u64,
    exceeded: bool,
}

struct TailCapture {
    bytes: Vec<u8>,
}

struct AuditChildOutput {
    exit_code: i32,
    stdout: PrefixCapture,
    stderr: TailCapture,
}

struct ParsedAudit {
    counts: BTreeMap<&'static str, u64>,
    vulnerabilities: Vec<FrontendAuditVulnerabilityV1>,
}

type VulnerabilityProjection = (
    Vec<FrontendAuditVulnerabilityV1>,
    BTreeMap<&'static str, u64>,
);

/// Run `npm audit --json`, strictly interpret bounded output, and safely publish the PM report.
///
/// # Errors
///
/// Rejects frontend-contract drift, unsafe output targets, process/capture failures, or verified
/// publication failures. Malformed audit JSON is represented as a blocked report rather than
/// silently treated as a clean dependency graph.
pub fn run_frontend_audit_report(
    options: &FrontendAuditReportOptions,
) -> Result<FrontendAuditReportReceiptV1, FrontendContractError> {
    let prepared = prepare(options)?;
    verify_inputs_unchanged(&prepared)?;
    let output = run_audit_child(&prepared)?;
    verify_inputs_unchanged(&prepared)?;
    let report = build_report(&prepared, &output)?;
    let report_bytes = encode_report(&report)?;
    let receipt = build_receipt(&prepared, output.exit_code, &report, &report_bytes)?;
    publish_verified_outputs(
        vec![VerifiedOutput {
            target: prepared.output.clone(),
            bytes: &report_bytes,
            suffix: "json",
        }],
        PUBLICATION_CODES,
    )?;
    Ok(receipt)
}

/// Encode a native frontend dependency-audit report receipt as canonical JSON.
///
/// # Errors
///
/// Returns an error if the receipt cannot be projected into canonical JSON.
pub fn canonical_frontend_audit_report_receipt_json(
    receipt: &FrontendAuditReportReceiptV1,
) -> Result<String, FrontendContractError> {
    canonical_struct(receipt, "frontend_audit_report_receipt_encode_failed")
}

fn prepare(
    options: &FrontendAuditReportOptions,
) -> Result<PreparedFrontendAuditReport, FrontendContractError> {
    verify_real_directory(&options.root, "frontend audit report root")?;
    let root = options.root.canonicalize().map_err(|error| {
        FrontendContractError::new(
            "frontend_audit_report_root_invalid",
            format!("canonicalize frontend audit report root failed: {error}"),
        )
    })?;
    let source_map = parse_source_map()?;
    let output = prepare_verified_publication_target(
        &root,
        &options.output,
        MAXIMUM_PREVIOUS_REPORT_BYTES,
        "frontend dependency audit report output",
        PUBLICATION_CODES,
    )?;
    for requested in [&options.package_json, &options.package_lock] {
        if let Some(existing) = canonical_existing_path(&root, requested)? {
            if output.path == existing {
                return Err(FrontendContractError::new(
                    "frontend_audit_report_output_invalid",
                    "frontend dependency audit report must not replace a requested package input",
                ));
            }
        }
    }
    for relative in &source_map.required_files {
        let required = root.join(relative).canonicalize().map_err(|error| {
            FrontendContractError::new(
                "frontend_audit_report_output_invalid",
                format!("canonicalize required frontend input failed: {error}"),
            )
        })?;
        if output.path == required {
            return Err(FrontendContractError::new(
                "frontend_audit_report_output_invalid",
                "frontend dependency audit report must not replace required contract input",
            ));
        }
    }
    let frontend_contract_receipt_hash = check_frontend_contract(&root)?.receipt_hash;
    Ok(PreparedFrontendAuditReport {
        source: source_map.frontend_audit_report_contract,
        root,
        package_json: portable_input_path(&options.package_json, "package JSON")?,
        package_lock: portable_input_path(&options.package_lock, "package lock")?,
        output,
        frontend_contract_receipt_hash,
    })
}

fn canonical_existing_path(
    root: &Path,
    requested: &Path,
) -> Result<Option<PathBuf>, FrontendContractError> {
    let unresolved = if requested.is_absolute() {
        requested.to_path_buf()
    } else {
        root.join(requested)
    };
    match unresolved.canonicalize() {
        Ok(path) => Ok(Some(path)),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(FrontendContractError::new(
            "frontend_audit_report_input_invalid",
            format!("canonicalize frontend dependency audit input failed: {error}"),
        )),
    }
}

fn portable_input_path(path: &Path, label: &str) -> Result<String, FrontendContractError> {
    let value = path.to_str().ok_or_else(|| {
        FrontendContractError::new(
            "frontend_audit_report_input_invalid",
            format!("{label} path must be UTF-8"),
        )
    })?;
    if value.is_empty() || value.len() > 4096 || value.chars().any(char::is_control) {
        return Err(FrontendContractError::new(
            "frontend_audit_report_input_invalid",
            format!("{label} path is empty, too long, or contains control characters"),
        ));
    }
    Ok(value.to_owned())
}

fn verify_inputs_unchanged(
    prepared: &PreparedFrontendAuditReport,
) -> Result<(), FrontendContractError> {
    if check_frontend_contract(&prepared.root)?.receipt_hash
        != prepared.frontend_contract_receipt_hash
    {
        return Err(FrontendContractError::new(
            "frontend_audit_report_contract_changed",
            "frontend package, lock, source map, or required inventory changed during audit",
        ));
    }
    Ok(())
}

fn run_audit_child(
    prepared: &PreparedFrontendAuditReport,
) -> Result<AuditChildOutput, FrontendContractError> {
    let mut child = Command::new(npm_launcher())
        .args(&prepared.source.arguments)
        .current_dir(&prepared.root)
        .env_remove("NODE_OPTIONS")
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| {
            FrontendContractError::new(
                "frontend_audit_report_launch_failed",
                format!("launch frontend dependency audit report child failed: {error}"),
            )
        })?;
    let stdout = child.stdout.take().ok_or_else(|| {
        FrontendContractError::new(
            "frontend_audit_report_capture_failed",
            "frontend dependency audit stdout pipe is unavailable",
        )
    })?;
    let stderr = child.stderr.take().ok_or_else(|| {
        FrontendContractError::new(
            "frontend_audit_report_capture_failed",
            "frontend dependency audit stderr pipe is unavailable",
        )
    })?;
    let maximum_stdout = usize::try_from(prepared.source.maximum_stdout_bytes).map_err(|_| {
        FrontendContractError::new(
            "frontend_audit_report_contract_invalid",
            "frontend dependency audit stdout bound is not addressable",
        )
    })?;
    let stdout_reader = thread::Builder::new()
        .name("frontend-audit-stdout".to_owned())
        .spawn(move || capture_prefix(stdout, maximum_stdout))
        .map_err(|error| {
            stop_child(&mut child);
            FrontendContractError::new(
                "frontend_audit_report_capture_failed",
                format!("start frontend dependency audit stdout reader failed: {error}"),
            )
        })?;
    let stderr_reader = match thread::Builder::new()
        .name("frontend-audit-stderr".to_owned())
        .spawn(move || capture_tail(stderr, STDERR_TAIL_BYTES))
    {
        Ok(reader) => reader,
        Err(error) => {
            stop_child(&mut child);
            let _ignored = stdout_reader.join();
            return Err(FrontendContractError::new(
                "frontend_audit_report_capture_failed",
                format!("start frontend dependency audit stderr reader failed: {error}"),
            ));
        }
    };
    let status = match child.wait() {
        Ok(status) => status,
        Err(error) => {
            stop_child(&mut child);
            let _ignored_stdout = stdout_reader.join();
            let _ignored_stderr = stderr_reader.join();
            return Err(FrontendContractError::new(
                "frontend_audit_report_wait_failed",
                format!("wait for frontend dependency audit child failed: {error}"),
            ));
        }
    };
    let stdout = join_capture(stdout_reader, "stdout")?;
    let stderr = join_capture(stderr_reader, "stderr")?;
    let exit_code = status.code().ok_or_else(|| {
        FrontendContractError::new(
            "frontend_audit_report_terminated",
            "frontend dependency audit terminated without an exit code",
        )
    })?;
    Ok(AuditChildOutput {
        exit_code,
        stdout,
        stderr,
    })
}

fn stop_child(child: &mut std::process::Child) {
    let _ignored_kill = child.kill();
    let _ignored_wait = child.wait();
}

fn npm_launcher() -> OsString {
    if cfg!(windows) {
        OsString::from("npm.cmd")
    } else {
        OsString::from("npm")
    }
}

fn capture_prefix(mut reader: impl Read, maximum: usize) -> io::Result<PrefixCapture> {
    let mut bytes = Vec::with_capacity(maximum.min(64 * 1024));
    let mut total_bytes = 0_u64;
    let mut buffer = [0_u8; 16 * 1024];
    loop {
        let count = reader.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        total_bytes = total_bytes.saturating_add(u64::try_from(count).unwrap_or(u64::MAX));
        if bytes.len() < maximum {
            let remaining = maximum - bytes.len();
            bytes.extend_from_slice(&buffer[..count.min(remaining)]);
        }
    }
    Ok(PrefixCapture {
        bytes,
        total_bytes,
        exceeded: total_bytes > u64::try_from(maximum).unwrap_or(u64::MAX),
    })
}

fn capture_tail(mut reader: impl Read, maximum: usize) -> io::Result<TailCapture> {
    let mut bytes = VecDeque::with_capacity(maximum);
    let mut buffer = [0_u8; 16 * 1024];
    loop {
        let count = reader.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        bytes.extend(&buffer[..count]);
        if bytes.len() > maximum {
            bytes.drain(..bytes.len() - maximum);
        }
    }
    Ok(TailCapture {
        bytes: bytes.into_iter().collect(),
    })
}

fn join_capture<T>(
    reader: thread::JoinHandle<io::Result<T>>,
    stream: &str,
) -> Result<T, FrontendContractError> {
    reader
        .join()
        .map_err(|_| {
            FrontendContractError::new(
                "frontend_audit_report_capture_failed",
                format!("frontend dependency audit {stream} reader panicked"),
            )
        })?
        .map_err(|error| {
            FrontendContractError::new(
                "frontend_audit_report_capture_failed",
                format!("read frontend dependency audit {stream} failed: {error}"),
            )
        })
}

fn build_report(
    prepared: &PreparedFrontendAuditReport,
    output: &AuditChildOutput,
) -> Result<FrontendDependencyAuditReportV1, FrontendContractError> {
    let parsed = parse_audit_payload(&output.stdout);
    let counts = parsed
        .as_ref()
        .map_or_else(zero_counts, |audit| audit.counts.clone());
    let total = VULNERABILITY_LEVELS
        .iter()
        .map(|level| counts[level])
        .sum::<u64>();
    let high_critical = counts["high"].saturating_add(counts["critical"]);
    let package_json_present = regular_file_present(&prepared.root, &prepared.package_json)?;
    let package_lock_present = regular_file_present(&prepared.root, &prepared.package_lock)?;
    let mut blockers = Vec::new();
    if !package_json_present {
        blockers.push("package_json_missing".to_owned());
    }
    if !package_lock_present {
        blockers.push("package_lock_missing".to_owned());
    }
    if parsed.is_none() {
        blockers.push("npm_audit_json_unavailable".to_owned());
    }
    if high_critical != 0 {
        blockers.push("frontend_dependency_high_or_critical_vulnerabilities_present".to_owned());
    }
    if total != 0 {
        blockers.push("frontend_dependency_vulnerabilities_present".to_owned());
    }
    if output.exit_code != 0 && total == 0 {
        blockers.push("npm_audit_exit_code_nonzero".to_owned());
    }
    let contract_pass = blockers.is_empty();
    let stderr = String::from_utf8_lossy(&output.stderr.bytes);
    let stderr_tail_characters =
        usize::try_from(prepared.source.stderr_tail_characters).map_err(|_| {
            FrontendContractError::new(
                "frontend_audit_report_contract_invalid",
                "frontend dependency audit stderr character bound is not addressable",
            )
        })?;
    Ok(FrontendDependencyAuditReportV1 {
        schema_version: REPORT_SCHEMA_V1.to_owned(),
        generated_at: generated_at()?,
        contract_pass,
        reason_code: if contract_pass {
            "PASS"
        } else {
            "ERR_FRONTEND_DEPENDENCY_AUDIT_BLOCKED"
        }
        .to_owned(),
        blockers,
        checks: FrontendAuditReportChecksV1 {
            package_json_present,
            package_lock_present,
            npm_audit_json_parse_pass: parsed.is_some(),
            dependency_vulnerability_total_zero_pass: total == 0,
            dependency_high_or_critical_zero_pass: high_critical == 0,
            npm_audit_exit_code_zero_pass: output.exit_code == 0,
        },
        summary: FrontendAuditReportSummaryV1 {
            package_json: prepared.package_json.clone(),
            package_lock: prepared.package_lock.clone(),
            npm_audit_exit_code: output.exit_code,
            vulnerability_total: total,
            high_or_critical_vulnerability_count: high_critical,
            info_vulnerability_count: counts["info"],
            low_vulnerability_count: counts["low"],
            moderate_vulnerability_count: counts["moderate"],
            high_vulnerability_count: counts["high"],
            critical_vulnerability_count: counts["critical"],
        },
        vulnerabilities: parsed.map_or_else(Vec::new, |audit| audit.vulnerabilities),
        diagnostics: FrontendAuditReportDiagnosticsV1 {
            npm_audit_stdout_bytes: output.stdout.total_bytes,
            npm_audit_stderr_tail: tail_characters(&stderr, stderr_tail_characters),
        },
        claim_boundary: REPORT_CLAIM_BOUNDARY.to_owned(),
    })
}

fn parse_audit_payload(capture: &PrefixCapture) -> Option<ParsedAudit> {
    if capture.exceeded {
        return None;
    }
    let value = decode_json_strict(&capture.bytes).ok()?;
    let object = value.as_object().filter(|object| !object.is_empty())?;
    let metadata_counts = metadata_counts(object).ok()?;
    let vulnerability_projection = vulnerability_rows(object).ok()?;
    let vulnerabilities = vulnerability_projection
        .as_ref()
        .map_or_else(Vec::new, |(rows, _)| rows.clone());
    let counts = match (metadata_counts, vulnerability_projection) {
        (Some(metadata), Some((_, rows))) if metadata == rows => metadata,
        (Some(metadata), None) if count_total(&metadata)? == 0 => metadata,
        (None, Some((_, rows))) => rows,
        (Some(_), _) | (None, None) => return None,
    };
    count_total(&counts)?;
    counts["high"].checked_add(counts["critical"])?;
    Some(ParsedAudit {
        counts,
        vulnerabilities,
    })
}

fn metadata_counts(object: &Map<String, Value>) -> Result<Option<BTreeMap<&'static str, u64>>, ()> {
    let Some(metadata_value) = object.get("metadata") else {
        return Ok(None);
    };
    let metadata = metadata_value.as_object().ok_or(())?;
    let Some(counts_value) = metadata.get("vulnerabilities") else {
        return Ok(None);
    };
    let metadata_counts = counts_value.as_object().ok_or(())?;
    let mut counts = BTreeMap::new();
    for level in VULNERABILITY_LEVELS {
        counts.insert(
            level,
            metadata_counts
                .get(level)
                .and_then(Value::as_u64)
                .ok_or(())?,
        );
    }
    let total = count_total(&counts).ok_or(())?;
    if let Some(declared_total) = metadata_counts.get("total") {
        if declared_total.as_u64() != Some(total) {
            return Err(());
        }
    }
    Ok(Some(counts))
}

fn zero_counts() -> BTreeMap<&'static str, u64> {
    VULNERABILITY_LEVELS
        .into_iter()
        .map(|level| (level, 0))
        .collect()
}

fn count_total(counts: &BTreeMap<&str, u64>) -> Option<u64> {
    VULNERABILITY_LEVELS
        .iter()
        .try_fold(0_u64, |total, level| total.checked_add(counts[level]))
}

fn vulnerability_rows(object: &Map<String, Value>) -> Result<Option<VulnerabilityProjection>, ()> {
    let Some(value) = object.get("vulnerabilities") else {
        return Ok(None);
    };
    let vulnerabilities = value.as_object().ok_or(())?;
    let mut names = vulnerabilities.keys().collect::<Vec<_>>();
    names.sort_unstable();
    let mut counts = zero_counts();
    let mut rows = Vec::with_capacity(names.len());
    for name in names {
        let row = vulnerabilities
            .get(name)
            .and_then(Value::as_object)
            .ok_or(())?;
        let severity = required_string_field(row, "severity")?.to_ascii_lowercase();
        let count = counts.get_mut(severity.as_str()).ok_or(())?;
        *count = count.checked_add(1).ok_or(())?;
        let via = match row.get("via") {
            None => Vec::new(),
            Some(value) => value
                .as_array()
                .ok_or(())?
                .iter()
                .map(via_row)
                .collect::<Result<Vec<_>, ()>>()?,
        };
        if row.get("name").is_some_and(|value| !value.is_string())
            || row.get("range").is_some_and(|value| !value.is_string())
            || row.get("isDirect").is_some_and(|value| !value.is_boolean())
        {
            return Err(());
        }
        rows.push(FrontendAuditVulnerabilityV1 {
            name: string_field(row, "name").unwrap_or_else(|| name.clone()),
            severity,
            range: string_field(row, "range").unwrap_or_default(),
            is_direct: row
                .get("isDirect")
                .and_then(Value::as_bool)
                .unwrap_or(false),
            fix_available: row
                .get("fixAvailable")
                .cloned()
                .unwrap_or(Value::Bool(false)),
            via,
        });
    }
    Ok(Some((rows, counts)))
}

fn via_row(value: &Value) -> Result<FrontendAuditViaV1, ()> {
    if let Some(title) = value.as_str() {
        return Ok(FrontendAuditViaV1 {
            title: title.to_owned(),
            severity: String::new(),
            url: String::new(),
            range: String::new(),
        });
    }
    let row = value.as_object().ok_or(())?;
    for field in ["title", "severity", "url", "range"] {
        if row.get(field).is_some_and(|value| !value.is_string()) {
            return Err(());
        }
    }
    Ok(FrontendAuditViaV1 {
        title: string_field(row, "title").unwrap_or_default(),
        severity: string_field(row, "severity").unwrap_or_default(),
        url: string_field(row, "url").unwrap_or_default(),
        range: string_field(row, "range").unwrap_or_default(),
    })
}

fn required_string_field(object: &Map<String, Value>, name: &str) -> Result<String, ()> {
    object
        .get(name)
        .and_then(Value::as_str)
        .map(str::to_owned)
        .ok_or(())
}

fn string_field(object: &Map<String, Value>, name: &str) -> Option<String> {
    object.get(name).and_then(Value::as_str).map(str::to_owned)
}

fn regular_file_present(root: &Path, requested: &str) -> Result<bool, FrontendContractError> {
    let path = Path::new(requested);
    let resolved = if path.is_absolute() {
        path.to_path_buf()
    } else {
        root.join(path)
    };
    match std::fs::symlink_metadata(&resolved) {
        Ok(metadata) => Ok(metadata.file_type().is_file()),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(false),
        Err(error) => Err(FrontendContractError::new(
            "frontend_audit_report_input_invalid",
            format!("inspect frontend dependency audit input failed: {error}"),
        )),
    }
}

fn generated_at() -> Result<String, FrontendContractError> {
    OffsetDateTime::now_utc().format(&Rfc3339).map_err(|error| {
        FrontendContractError::new(
            "frontend_audit_report_timestamp_failed",
            format!("format frontend dependency audit report timestamp failed: {error}"),
        )
    })
}

fn tail_characters(value: &str, maximum: usize) -> String {
    let count = value.chars().count();
    if count <= maximum {
        return value.to_owned();
    }
    value.chars().skip(count - maximum).collect()
}

fn encode_report(
    report: &FrontendDependencyAuditReportV1,
) -> Result<Vec<u8>, FrontendContractError> {
    let value = serde_json::to_value(report).map_err(|error| {
        FrontendContractError::new(
            "frontend_audit_report_encode_failed",
            format!("project frontend dependency audit report failed: {error}"),
        )
    })?;
    let encoded = canonicalize_model_ir_v2(&value).map_err(|error| {
        FrontendContractError::new(
            "frontend_audit_report_encode_failed",
            format!("canonicalize frontend dependency audit report failed: {error}"),
        )
    })?;
    if encoded.len() >= MAXIMUM_REPORT_BYTES {
        return Err(FrontendContractError::new(
            "frontend_audit_report_too_large",
            "frontend dependency audit report exceeds its byte bound",
        ));
    }
    let mut bytes = encoded.into_bytes();
    bytes.push(b'\n');
    Ok(bytes)
}

fn build_receipt(
    prepared: &PreparedFrontendAuditReport,
    exit_code: i32,
    report: &FrontendDependencyAuditReportV1,
    report_bytes: &[u8],
) -> Result<FrontendAuditReportReceiptV1, FrontendContractError> {
    let blocker_count = u64::try_from(report.blockers.len()).map_err(|_| {
        FrontendContractError::new(
            "frontend_audit_report_receipt_encode_failed",
            "frontend dependency audit blocker count is not addressable",
        )
    })?;
    let report_byte_length = u64::try_from(report_bytes.len()).map_err(|_| {
        FrontendContractError::new(
            "frontend_audit_report_receipt_encode_failed",
            "frontend dependency audit report length is not addressable",
        )
    })?;
    let logical_command = std::iter::once("npm".to_owned())
        .chain(prepared.source.arguments.iter().cloned())
        .collect();
    let mut receipt = FrontendAuditReportReceiptV1 {
        schema_version: RECEIPT_SCHEMA_V1.to_owned(),
        action: "frontend_audit_report".to_owned(),
        status: if report.contract_pass {
            "published_pass"
        } else {
            "published_blocked"
        }
        .to_owned(),
        source_map_sha256: sha256_identity(SOURCE_MAP_BYTES),
        frontend_contract_receipt_hash: prepared.frontend_contract_receipt_hash.clone(),
        logical_command,
        process_launcher: EXPECTED_NPM_LAUNCHER.to_owned(),
        node_options_disposition: "removed_for_direct_child".to_owned(),
        direct_processes_spawned: 1,
        observed_exit_code: exit_code,
        report: FrontendAuditPublishedReportV1 {
            path: prepared.output.requested.clone(),
            byte_length: report_byte_length,
            sha256: sha256_identity(report_bytes),
            publication_strategy: VERIFIED_PUBLICATION_STRATEGY.to_owned(),
        },
        contract_pass: report.contract_pass,
        reason_code: report.reason_code.clone(),
        blocker_count,
        vulnerability_total: report.summary.vulnerability_total,
        high_or_critical_vulnerability_count: report.summary.high_or_critical_vulnerability_count,
        network_access_accounting: prepared.source.network_access_accounting.clone(),
        filesystem_mutation_accounting: prepared.source.filesystem_mutation_accounting.clone(),
        environment_accounting: prepared.source.environment_accounting.clone(),
        deterministic_receipt: false,
        claim_boundary: prepared.source.claim_boundary.clone(),
        receipt_hash: String::new(),
    };
    receipt.receipt_hash = hash_without_receipt_hash(&receipt)?;
    Ok(receipt)
}

fn hash_without_receipt_hash(
    receipt: &FrontendAuditReportReceiptV1,
) -> Result<String, FrontendContractError> {
    let mut value = serde_json::to_value(receipt).map_err(|error| {
        FrontendContractError::new(
            "frontend_audit_report_receipt_encode_failed",
            format!("project frontend dependency audit report receipt failed: {error}"),
        )
    })?;
    value
        .as_object_mut()
        .ok_or_else(|| {
            FrontendContractError::new(
                "frontend_audit_report_receipt_encode_failed",
                "frontend dependency audit report receipt is not an object",
            )
        })?
        .remove("receipt_hash");
    let canonical = canonicalize_model_ir_v2(&value).map_err(|error| {
        FrontendContractError::new(
            "frontend_audit_report_receipt_encode_failed",
            format!("canonicalize frontend dependency audit report receipt failed: {error}"),
        )
    })?;
    Ok(sha256_identity(canonical.as_bytes()))
}

pub(crate) fn validate_frontend_audit_report_source(
    source: &FrontendAuditReportSourceV1,
) -> Result<(), FrontendContractError> {
    let valid = source.schema_version == CONTRACT_SCHEMA_V1
        && source.npm_launcher == EXPECTED_NPM_LAUNCHER
        && source.arguments == EXPECTED_ARGUMENTS
        && source.maximum_stdout_bytes == EXPECTED_MAXIMUM_STDOUT_BYTES
        && source.stderr_tail_characters == EXPECTED_STDERR_TAIL_CHARACTERS
        && valid_text(&source.network_access_accounting)
        && valid_text(&source.filesystem_mutation_accounting)
        && valid_text(&source.environment_accounting)
        && valid_text(&source.claim_boundary);
    if !valid {
        return Err(FrontendContractError::new(
            "frontend_source_map_contract_invalid",
            "frontend dependency-audit report contract is invalid",
        ));
    }
    Ok(())
}

fn valid_text(value: &str) -> bool {
    !value.trim().is_empty() && value.len() <= 16 * 1024 && !value.chars().any(char::is_control)
}

#[cfg(test)]
mod tests {
    use super::{
        capture_prefix, parse_audit_payload, tail_characters,
        validate_frontend_audit_report_source, FrontendAuditReportSourceV1,
    };

    fn source() -> FrontendAuditReportSourceV1 {
        FrontendAuditReportSourceV1 {
            schema_version: super::CONTRACT_SCHEMA_V1.to_owned(),
            npm_launcher: super::EXPECTED_NPM_LAUNCHER.to_owned(),
            arguments: super::EXPECTED_ARGUMENTS
                .iter()
                .map(|value| (*value).to_owned())
                .collect(),
            maximum_stdout_bytes: super::EXPECTED_MAXIMUM_STDOUT_BYTES,
            stderr_tail_characters: super::EXPECTED_STDERR_TAIL_CHARACTERS,
            network_access_accounting: "bounded claim".to_owned(),
            filesystem_mutation_accounting: "bounded claim".to_owned(),
            environment_accounting: "bounded claim".to_owned(),
            claim_boundary: "bounded claim".to_owned(),
        }
    }

    #[test]
    fn report_contract_rejects_command_and_capture_widening() {
        assert!(validate_frontend_audit_report_source(&source()).is_ok());
        let mut arguments = source();
        arguments.arguments.push("--omit=dev".to_owned());
        assert!(validate_frontend_audit_report_source(&arguments).is_err());
        let mut bound = source();
        bound.maximum_stdout_bytes += 1;
        assert!(validate_frontend_audit_report_source(&bound).is_err());
    }

    #[test]
    fn strict_audit_parser_rejects_duplicates_nonfinite_and_oversize() {
        let valid = capture_prefix(
            &br#"{"metadata":{"vulnerabilities":{"info":0,"low":0,"moderate":0,"high":0,"critical":0}}}"#[..],
            1024,
        )
        .expect("capture valid audit");
        assert!(parse_audit_payload(&valid).is_some());
        let duplicate = capture_prefix(
            &br#"{"metadata":{"vulnerabilities":{"info":0,"info":1,"low":0,"moderate":0,"high":0,"critical":0}}}"#[..],
            1024,
        )
        .expect("capture duplicate audit");
        assert!(parse_audit_payload(&duplicate).is_none());
        let nonfinite = capture_prefix(
            &br#"{"metadata":{"vulnerabilities":{"info":NaN,"low":0,"moderate":0,"high":0,"critical":0}}}"#[..],
            1024,
        )
        .expect("capture nonfinite audit");
        assert!(parse_audit_payload(&nonfinite).is_none());
        let inconsistent = capture_prefix(
            &br#"{"vulnerabilities":{"vite":{"severity":"high"}},"metadata":{"vulnerabilities":{"info":0,"low":0,"moderate":0,"high":0,"critical":0,"total":0}}}"#[..],
            1024,
        )
        .expect("capture inconsistent audit");
        assert!(parse_audit_payload(&inconsistent).is_none());
        let oversized = capture_prefix(&b"{}"[..], 1).expect("capture oversized audit");
        assert!(oversized.exceeded);
        assert!(parse_audit_payload(&oversized).is_none());
    }

    #[test]
    fn diagnostics_tail_is_bounded_by_characters() {
        assert_eq!(tail_characters("abcdef", 4), "cdef");
        assert_eq!(tail_characters("가나다라마", 3), "다라마");
    }
}
