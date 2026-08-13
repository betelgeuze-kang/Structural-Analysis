use std::net::{Ipv4Addr, SocketAddrV4, TcpListener};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, ExitStatus, Stdio};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{mpsc, Arc};
use std::thread;
use std::time::Duration;

use serde::{Deserialize, Serialize};
use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_contracts::product_ir::sha256_identity;

use super::viewer_server::{handle_stream, prepare_server, ViewerServerSourceV1};
use super::{
    canonical_struct, check_frontend_contract, parse_source_map, read_bounded_regular_file,
    resolve_required_file, verify_real_directory, FrontendContractError, SOURCE_MAP_BYTES,
};

const BROWSER_SMOKE_CONTRACT_V1: &str = "structural-native-viewer-browser-smoke-contract.v1";
const BROWSER_SMOKE_RECEIPT_V1: &str = "structural-native-viewer-browser-smoke-receipt.v1";
const MAX_SPEC_BYTES: u64 = 16 * 1024 * 1024;
const MAX_PLAYWRIGHT_CLI_BYTES: u64 = 4 * 1024 * 1024;
const PROCESS_POLL_INTERVAL: Duration = Duration::from_millis(10);
const EXPECTED_NODE_LAUNCHER: &str = "node";
const EXPECTED_PLAYWRIGHT_CLI: &str = "node_modules/@playwright/test/cli.js";
const EXPECTED_SPEC: &str = "tests/frontend/structure-viewer-smoke.spec.ts";
const EXTERNAL_NETWORK_ACCOUNTING: &str = "not_instrumented_browser_page_requests";

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ViewerBrowserSmokeSourceV1 {
    schema_version: String,
    node_launcher: String,
    playwright_cli_path: String,
    spec_path: String,
    supported_modes: Vec<String>,
    external_network_access_accounting: String,
    claim_boundary: String,
}

struct PreparedBrowserSmoke {
    root: PathBuf,
    source: ViewerBrowserSmokeSourceV1,
    server_source: ViewerServerSourceV1,
    frontend_contract_receipt_hash: String,
    spec_bytes: Vec<u8>,
    logical_command: Vec<String>,
}

struct BrowserSmokeExecution {
    dry_run: bool,
    direct_processes_spawned: u64,
    successful_exit_code: Option<i32>,
    request_error_count: u64,
    playwright_cli_sha256: Option<String>,
}

struct BrowserServer {
    port: u16,
    stop: Arc<AtomicBool>,
    request_errors: Arc<AtomicU64>,
    error_rx: mpsc::Receiver<String>,
    thread: thread::JoinHandle<()>,
}

impl BrowserServer {
    fn finish(self) -> Result<u64, FrontendContractError> {
        self.stop.store(true, Ordering::Release);
        join_server(self.thread)?;
        Ok(self.request_errors.load(Ordering::Relaxed))
    }
}

/// Canonical receipt for one planned or completed source Viewer browser smoke.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct ViewerBrowserSmokeReceiptV1 {
    pub schema_version: String,
    pub action: String,
    pub execution_mode: String,
    pub browser_smoke_mode: String,
    pub status: String,
    pub source_map_sha256: String,
    pub frontend_contract_receipt_hash: String,
    pub spec_sha256: String,
    pub playwright_cli_sha256: Option<String>,
    pub logical_command: Vec<String>,
    pub node_runtime_required: bool,
    pub browser_runtime_required: bool,
    pub loopback_listener_count: u64,
    pub direct_processes_spawned: u64,
    pub successful_exit_code: Option<i32>,
    pub request_error_count: u64,
    pub external_network_access_accounting: String,
    pub deterministic_receipt: bool,
    pub claim_boundary: String,
    pub receipt_hash: String,
}

/// Plan or execute the retained Playwright source Viewer smoke under Rust process ownership.
///
/// Dry-run validates tracked source inputs without binding a listener or spawning Node. Execution
/// binds one ephemeral IPv4 loopback listener, directly spawns the pinned Playwright CLI through
/// Node, stops the server when the child exits, and publishes a receipt only on exit code zero.
///
/// # Errors
///
/// Rejects contract or mode drift, missing runtime files, socket and process failures, nonzero
/// browser exit, and server-thread failure.
pub fn run_viewer_browser_smoke(
    root: &Path,
    mode: &str,
    dry_run: bool,
) -> Result<ViewerBrowserSmokeReceiptV1, FrontendContractError> {
    let prepared = prepare_browser_smoke(root, mode)?;
    let execution = if dry_run {
        BrowserSmokeExecution {
            dry_run: true,
            direct_processes_spawned: 0,
            successful_exit_code: None,
            request_error_count: 0,
            playwright_cli_sha256: None,
        }
    } else {
        execute_browser_smoke(&prepared, mode)?
    };
    build_receipt(prepared, mode, &execution)
}

fn prepare_browser_smoke(
    root: &Path,
    mode: &str,
) -> Result<PreparedBrowserSmoke, FrontendContractError> {
    verify_real_directory(root, "Viewer browser smoke root")?;
    let frontend_contract_receipt_hash = check_frontend_contract(root)?.receipt_hash;
    let source = parse_source_map()?.viewer_browser_smoke_contract;
    if !source.supported_modes.iter().any(|value| value == mode) {
        return Err(FrontendContractError::new(
            "viewer_browser_smoke_mode_invalid",
            "Viewer browser smoke mode must be minimal or full",
        ));
    }
    let working_root = root.canonicalize().map_err(|error| {
        FrontendContractError::new(
            "viewer_browser_smoke_root_invalid",
            format!("canonicalize Viewer browser smoke root failed: {error}"),
        )
    })?;
    let server_source = prepare_server(&working_root, "127.0.0.1", 8765)?;
    let spec_path = resolve_required_file(&working_root, &source.spec_path)?;
    let spec_bytes = read_bounded_regular_file(
        &spec_path,
        MAX_SPEC_BYTES,
        "Viewer browser smoke specification",
    )?;
    let logical_command = vec![
        source.node_launcher.clone(),
        source.playwright_cli_path.clone(),
        "test".to_owned(),
        source.spec_path.clone(),
        "--reporter=line".to_owned(),
    ];
    Ok(PreparedBrowserSmoke {
        root: working_root,
        source,
        server_source,
        frontend_contract_receipt_hash,
        spec_bytes,
        logical_command,
    })
}

fn start_browser_server(
    prepared: &PreparedBrowserSmoke,
) -> Result<BrowserServer, FrontendContractError> {
    let listener =
        TcpListener::bind(SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0)).map_err(|error| {
            FrontendContractError::new(
                "viewer_browser_smoke_bind_failed",
                format!("bind Viewer browser smoke loopback server failed: {error}"),
            )
        })?;
    listener.set_nonblocking(true).map_err(|error| {
        FrontendContractError::new(
            "viewer_browser_smoke_socket_config_failed",
            format!("configure Viewer browser smoke listener failed: {error}"),
        )
    })?;
    let port = listener
        .local_addr()
        .map_err(|error| {
            FrontendContractError::new(
                "viewer_browser_smoke_socket_config_failed",
                format!("inspect Viewer browser smoke listener failed: {error}"),
            )
        })?
        .port();
    let stop = Arc::new(AtomicBool::new(false));
    let request_errors = Arc::new(AtomicU64::new(0));
    let (server_error_tx, server_error_rx) = mpsc::channel();
    let server_root = prepared.root.clone();
    let server_source = prepared.server_source.clone();
    let server_stop = Arc::clone(&stop);
    let server_request_errors = Arc::clone(&request_errors);
    let server_thread = thread::spawn(move || {
        while !server_stop.load(Ordering::Acquire) {
            match listener.accept() {
                Ok((stream, _)) => {
                    if handle_stream(&server_root, &server_source, stream).is_err() {
                        server_request_errors.fetch_add(1, Ordering::Relaxed);
                    }
                }
                Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                    thread::sleep(PROCESS_POLL_INTERVAL);
                }
                Err(error) => {
                    let _ignored = server_error_tx.send(format!(
                        "accept Viewer browser smoke connection failed: {error}"
                    ));
                    return;
                }
            }
        }
    });
    Ok(BrowserServer {
        port,
        stop,
        request_errors,
        error_rx: server_error_rx,
        thread: server_thread,
    })
}

fn spawn_browser_child(
    prepared: &PreparedBrowserSmoke,
    mode: &str,
    port: u16,
) -> Result<Child, FrontendContractError> {
    let base_url = format!("http://127.0.0.1:{port}");
    Command::new(&prepared.source.node_launcher)
        .args(&prepared.logical_command[1..])
        .current_dir(&prepared.root)
        .env("STRUCTURE_VIEWER_BASE_URL", &base_url)
        .env("STRUCTURE_VIEWER_BROWSER_SMOKE_MODE", mode)
        .stdin(Stdio::null())
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .spawn()
        .map_err(|error| {
            FrontendContractError::new(
                "viewer_browser_smoke_launch_failed",
                format!("launch Playwright Viewer browser smoke failed: {error}"),
            )
        })
}

fn wait_for_browser(
    child: &mut Child,
    server_errors: &mpsc::Receiver<String>,
) -> Result<ExitStatus, FrontendContractError> {
    loop {
        if let Ok(detail) = server_errors.try_recv() {
            let _ignored = child.kill();
            let _ignored = child.wait();
            return Err(FrontendContractError::new(
                "viewer_browser_smoke_server_failed",
                detail,
            ));
        }
        match child.try_wait() {
            Ok(Some(status)) => return Ok(status),
            Ok(None) => thread::sleep(PROCESS_POLL_INTERVAL),
            Err(error) => {
                let _ignored = child.kill();
                let _ignored = child.wait();
                return Err(FrontendContractError::new(
                    "viewer_browser_smoke_wait_failed",
                    format!("wait for Playwright Viewer browser smoke failed: {error}"),
                ));
            }
        }
    }
}

fn execute_browser_smoke(
    prepared: &PreparedBrowserSmoke,
    mode: &str,
) -> Result<BrowserSmokeExecution, FrontendContractError> {
    let playwright_cli_path =
        resolve_required_file(&prepared.root, &prepared.source.playwright_cli_path)?;
    let playwright_cli = read_bounded_regular_file(
        &playwright_cli_path,
        MAX_PLAYWRIGHT_CLI_BYTES,
        "Playwright CLI",
    )?;
    let server = start_browser_server(prepared)?;
    let mut child = match spawn_browser_child(prepared, mode, server.port) {
        Ok(child) => child,
        Err(error) => {
            server.finish()?;
            return Err(error);
        }
    };
    let status_result = wait_for_browser(&mut child, &server.error_rx);
    let request_error_count = server.finish()?;
    let status = status_result?;
    let exit_code = status.code().ok_or_else(|| {
        FrontendContractError::new(
            "viewer_browser_smoke_terminated",
            "Playwright Viewer browser smoke terminated without an exit code",
        )
    })?;
    if !status.success() {
        return Err(FrontendContractError::new(
            "viewer_browser_smoke_failed",
            format!("Playwright Viewer browser smoke failed with exit code {exit_code}"),
        ));
    }
    Ok(BrowserSmokeExecution {
        dry_run: false,
        direct_processes_spawned: 1,
        successful_exit_code: Some(exit_code),
        request_error_count,
        playwright_cli_sha256: Some(sha256_identity(&playwright_cli)),
    })
}

/// Encode a Viewer browser-smoke receipt as canonical JSON.
///
/// # Errors
///
/// Returns an error if the receipt cannot be projected into canonical JSON.
pub fn canonical_viewer_browser_smoke_receipt_json(
    receipt: &ViewerBrowserSmokeReceiptV1,
) -> Result<String, FrontendContractError> {
    canonical_struct(receipt, "viewer_browser_smoke_receipt_encode_failed")
}

pub(crate) fn validate_viewer_browser_smoke_source(
    source: &ViewerBrowserSmokeSourceV1,
) -> Result<(), FrontendContractError> {
    if source.schema_version != BROWSER_SMOKE_CONTRACT_V1
        || source.node_launcher != EXPECTED_NODE_LAUNCHER
        || source.playwright_cli_path != EXPECTED_PLAYWRIGHT_CLI
        || source.spec_path != EXPECTED_SPEC
        || source
            .supported_modes
            .iter()
            .map(String::as_str)
            .collect::<Vec<_>>()
            != ["minimal", "full"]
        || source.external_network_access_accounting != EXTERNAL_NETWORK_ACCOUNTING
        || source.claim_boundary.trim().is_empty()
        || source.claim_boundary.len() > 16 * 1024
        || source.claim_boundary.chars().any(char::is_control)
    {
        return Err(FrontendContractError::new(
            "frontend_source_map_contract_invalid",
            "Viewer browser smoke contract is invalid",
        ));
    }
    Ok(())
}

fn build_receipt(
    prepared: PreparedBrowserSmoke,
    mode: &str,
    execution: &BrowserSmokeExecution,
) -> Result<ViewerBrowserSmokeReceiptV1, FrontendContractError> {
    let mut receipt = ViewerBrowserSmokeReceiptV1 {
        schema_version: BROWSER_SMOKE_RECEIPT_V1.to_owned(),
        action: "viewer_browser_smoke".to_owned(),
        execution_mode: if execution.dry_run {
            "dry_run"
        } else {
            "execute"
        }
        .to_owned(),
        browser_smoke_mode: mode.to_owned(),
        status: if execution.dry_run {
            "planned"
        } else {
            "passed"
        }
        .to_owned(),
        source_map_sha256: sha256_identity(SOURCE_MAP_BYTES),
        frontend_contract_receipt_hash: prepared.frontend_contract_receipt_hash,
        spec_sha256: sha256_identity(&prepared.spec_bytes),
        playwright_cli_sha256: execution.playwright_cli_sha256.clone(),
        logical_command: prepared.logical_command,
        node_runtime_required: true,
        browser_runtime_required: true,
        loopback_listener_count: u64::from(!execution.dry_run),
        direct_processes_spawned: execution.direct_processes_spawned,
        successful_exit_code: execution.successful_exit_code,
        request_error_count: execution.request_error_count,
        external_network_access_accounting: prepared.source.external_network_access_accounting,
        deterministic_receipt: execution.dry_run,
        claim_boundary: prepared.source.claim_boundary,
        receipt_hash: String::new(),
    };
    receipt.receipt_hash = hash_without_receipt_hash(&receipt)?;
    Ok(receipt)
}

fn join_server(handle: thread::JoinHandle<()>) -> Result<(), FrontendContractError> {
    handle.join().map_err(|_| {
        FrontendContractError::new(
            "viewer_browser_smoke_server_panicked",
            "Viewer browser smoke server thread panicked",
        )
    })
}

fn hash_without_receipt_hash(
    receipt: &ViewerBrowserSmokeReceiptV1,
) -> Result<String, FrontendContractError> {
    let mut value = serde_json::to_value(receipt).map_err(|error| {
        FrontendContractError::new(
            "viewer_browser_smoke_receipt_encode_failed",
            format!("project Viewer browser smoke receipt failed: {error}"),
        )
    })?;
    value
        .as_object_mut()
        .ok_or_else(|| {
            FrontendContractError::new(
                "viewer_browser_smoke_receipt_encode_failed",
                "Viewer browser smoke receipt projection is not an object",
            )
        })?
        .remove("receipt_hash");
    let canonical = canonicalize_model_ir_v2(&value).map_err(|error| {
        FrontendContractError::new(
            "viewer_browser_smoke_receipt_encode_failed",
            format!("canonicalize Viewer browser smoke receipt failed: {error}"),
        )
    })?;
    Ok(sha256_identity(canonical.as_bytes()))
}

#[cfg(test)]
mod tests {
    use super::{validate_viewer_browser_smoke_source, ViewerBrowserSmokeSourceV1};

    #[test]
    fn browser_source_contract_cannot_widen_modes_or_commands() {
        let source = ViewerBrowserSmokeSourceV1 {
            schema_version: "structural-native-viewer-browser-smoke-contract.v1".to_owned(),
            node_launcher: "node".to_owned(),
            playwright_cli_path: "node_modules/@playwright/test/cli.js".to_owned(),
            spec_path: "tests/frontend/structure-viewer-smoke.spec.ts".to_owned(),
            supported_modes: vec!["minimal".to_owned(), "full".to_owned()],
            external_network_access_accounting: "not_instrumented_browser_page_requests".to_owned(),
            claim_boundary: "bounded".to_owned(),
        };
        assert!(validate_viewer_browser_smoke_source(&source).is_ok());
        let mut drift = source;
        drift.node_launcher = "sh".to_owned();
        assert!(validate_viewer_browser_smoke_source(&drift).is_err());
    }
}
