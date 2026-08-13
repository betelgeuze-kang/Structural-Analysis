use std::collections::BTreeSet;
use std::net::{Ipv4Addr, SocketAddrV4, TcpListener};
use std::path::PathBuf;
use std::process::{Child, Command, ExitStatus, Stdio};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{mpsc, Arc};
use std::thread;
use std::time::Duration;

use structural_contracts::product_ir::sha256_identity;

use super::viewer_server::{
    handle_scoped_stream, handle_spa_stream, handle_stream, validate_scoped_policy,
    validate_spa_policy, validate_viewer_server_source, ViewerServerSourceV1,
};
use super::{
    read_bounded_regular_file, resolve_required_file, verify_real_directory, FrontendContractError,
};

const MAX_PLAYWRIGHT_CLI_BYTES: u64 = 4 * 1024 * 1024;
const PROCESS_POLL_INTERVAL: Duration = Duration::from_millis(10);

#[derive(Clone)]
pub(crate) enum PlaywrightServerRoute {
    Viewer(ViewerServerSourceV1),
    Scoped {
        allowed_path_prefix: String,
        root_redirect: String,
    },
    Spa {
        fallback_entry: String,
    },
}

pub(crate) struct PlaywrightPlan {
    pub root: PathBuf,
    pub server_root: PathBuf,
    pub node_launcher: String,
    pub playwright_cli_path: String,
    pub playwright_cli_command_index: usize,
    pub logical_command: Vec<String>,
    pub base_url_environment: String,
    pub base_url_path: String,
    pub extra_environment: Vec<(String, String)>,
    pub server_route: PlaywrightServerRoute,
}

pub(crate) struct PlaywrightExecution {
    pub direct_processes_spawned: u64,
    pub successful_exit_code: i32,
    pub request_error_count: u64,
    pub playwright_cli_sha256: String,
}

#[derive(Clone, Copy)]
pub(crate) enum PlaywrightErrorDomain {
    Viewer,
    WorkbenchPrototype,
    WorkbenchV2,
}

pub(crate) fn map_playwright_error(
    domain: PlaywrightErrorDomain,
    error: FrontendContractError,
) -> FrontendContractError {
    let code = match (domain, error.code) {
        (PlaywrightErrorDomain::Viewer, "playwright_plan_invalid") => {
            "viewer_browser_smoke_plan_invalid"
        }
        (PlaywrightErrorDomain::Viewer, "playwright_server_panicked") => {
            "viewer_browser_smoke_server_panicked"
        }
        (PlaywrightErrorDomain::Viewer, "playwright_bind_failed") => {
            "viewer_browser_smoke_bind_failed"
        }
        (PlaywrightErrorDomain::Viewer, "playwright_socket_config_failed") => {
            "viewer_browser_smoke_socket_config_failed"
        }
        (PlaywrightErrorDomain::Viewer, "playwright_launch_failed") => {
            "viewer_browser_smoke_launch_failed"
        }
        (PlaywrightErrorDomain::Viewer, "playwright_wait_failed") => {
            "viewer_browser_smoke_wait_failed"
        }
        (PlaywrightErrorDomain::Viewer, "playwright_server_failed") => {
            "viewer_browser_smoke_server_failed"
        }
        (PlaywrightErrorDomain::Viewer, "playwright_request_failed") => {
            "viewer_browser_smoke_request_failed"
        }
        (PlaywrightErrorDomain::Viewer, "playwright_terminated") => {
            "viewer_browser_smoke_terminated"
        }
        (PlaywrightErrorDomain::Viewer, "playwright_failed") => "viewer_browser_smoke_failed",
        (PlaywrightErrorDomain::WorkbenchPrototype, "playwright_plan_invalid") => {
            "workbench_prototype_browser_smoke_plan_invalid"
        }
        (PlaywrightErrorDomain::WorkbenchPrototype, "playwright_server_panicked") => {
            "workbench_prototype_browser_smoke_server_panicked"
        }
        (PlaywrightErrorDomain::WorkbenchPrototype, "playwright_bind_failed") => {
            "workbench_prototype_browser_smoke_bind_failed"
        }
        (PlaywrightErrorDomain::WorkbenchPrototype, "playwright_socket_config_failed") => {
            "workbench_prototype_browser_smoke_socket_config_failed"
        }
        (PlaywrightErrorDomain::WorkbenchPrototype, "playwright_launch_failed") => {
            "workbench_prototype_browser_smoke_launch_failed"
        }
        (PlaywrightErrorDomain::WorkbenchPrototype, "playwright_wait_failed") => {
            "workbench_prototype_browser_smoke_wait_failed"
        }
        (PlaywrightErrorDomain::WorkbenchPrototype, "playwright_server_failed") => {
            "workbench_prototype_browser_smoke_server_failed"
        }
        (PlaywrightErrorDomain::WorkbenchPrototype, "playwright_request_failed") => {
            "workbench_prototype_browser_smoke_request_failed"
        }
        (PlaywrightErrorDomain::WorkbenchPrototype, "playwright_terminated") => {
            "workbench_prototype_browser_smoke_terminated"
        }
        (PlaywrightErrorDomain::WorkbenchPrototype, "playwright_failed") => {
            "workbench_prototype_browser_smoke_failed"
        }
        (PlaywrightErrorDomain::WorkbenchV2, "playwright_plan_invalid") => {
            "workbench_v2_browser_smoke_plan_invalid"
        }
        (PlaywrightErrorDomain::WorkbenchV2, "playwright_server_panicked") => {
            "workbench_v2_browser_smoke_server_panicked"
        }
        (PlaywrightErrorDomain::WorkbenchV2, "playwright_bind_failed") => {
            "workbench_v2_browser_smoke_bind_failed"
        }
        (PlaywrightErrorDomain::WorkbenchV2, "playwright_socket_config_failed") => {
            "workbench_v2_browser_smoke_socket_config_failed"
        }
        (PlaywrightErrorDomain::WorkbenchV2, "playwright_launch_failed") => {
            "workbench_v2_browser_smoke_launch_failed"
        }
        (PlaywrightErrorDomain::WorkbenchV2, "playwright_wait_failed") => {
            "workbench_v2_browser_smoke_wait_failed"
        }
        (PlaywrightErrorDomain::WorkbenchV2, "playwright_server_failed") => {
            "workbench_v2_browser_smoke_server_failed"
        }
        (PlaywrightErrorDomain::WorkbenchV2, "playwright_request_failed") => {
            "workbench_v2_browser_smoke_request_failed"
        }
        (PlaywrightErrorDomain::WorkbenchV2, "playwright_terminated") => {
            "workbench_v2_browser_smoke_terminated"
        }
        (PlaywrightErrorDomain::WorkbenchV2, "playwright_failed") => {
            "workbench_v2_browser_smoke_failed"
        }
        _ => return error,
    };
    FrontendContractError::new(code, error.detail)
}

struct BrowserServer {
    port: u16,
    stop: Arc<AtomicBool>,
    request_errors: Arc<AtomicU64>,
    error_rx: mpsc::Receiver<String>,
    thread: thread::JoinHandle<()>,
}

impl BrowserServer {
    fn finish(self) -> Result<(u64, Option<String>), FrontendContractError> {
        self.stop.store(true, Ordering::Release);
        self.thread.join().map_err(|_| {
            FrontendContractError::new(
                "playwright_server_panicked",
                "Playwright static-server thread panicked",
            )
        })?;
        Ok((
            self.request_errors.load(Ordering::Relaxed),
            self.error_rx.try_recv().ok(),
        ))
    }
}

pub(crate) fn execute_playwright(
    plan: &PlaywrightPlan,
) -> Result<PlaywrightExecution, FrontendContractError> {
    validate_playwright_plan(plan)?;
    verify_real_directory(&plan.server_root, "Playwright static-server root")?;
    let playwright_cli_path = resolve_required_file(&plan.root, &plan.playwright_cli_path)?;
    let playwright_cli = read_bounded_regular_file(
        &playwright_cli_path,
        MAX_PLAYWRIGHT_CLI_BYTES,
        "Playwright CLI",
    )?;
    let server = start_server(plan)?;
    let mut child = match spawn_child(plan, server.port) {
        Ok(child) => child,
        Err(error) => {
            let _server_outcome = server.finish()?;
            return Err(error);
        }
    };
    let status_result = wait_for_child(&mut child, &server.error_rx);
    let (request_error_count, late_server_error) = server.finish()?;
    let status = status_result?;
    if let Some(detail) = late_server_error {
        return Err(FrontendContractError::new(
            "playwright_server_failed",
            detail,
        ));
    }
    if request_error_count > 0 {
        return Err(FrontendContractError::new(
            "playwright_request_failed",
            format!("Playwright static server recorded {request_error_count} request errors"),
        ));
    }
    let exit_code = status.code().ok_or_else(|| {
        FrontendContractError::new(
            "playwright_terminated",
            "Playwright terminated without an exit code",
        )
    })?;
    if !status.success() {
        return Err(FrontendContractError::new(
            "playwright_failed",
            format!("Playwright failed with exit code {exit_code}"),
        ));
    }
    Ok(PlaywrightExecution {
        direct_processes_spawned: 1,
        successful_exit_code: exit_code,
        request_error_count,
        playwright_cli_sha256: sha256_identity(&playwright_cli),
    })
}

pub(crate) fn validate_playwright_plan(plan: &PlaywrightPlan) -> Result<(), FrontendContractError> {
    let command_valid = (3..=16).contains(&plan.logical_command.len())
        && plan.logical_command.first() == Some(&plan.node_launcher)
        && (1..plan.logical_command.len()).contains(&plan.playwright_cli_command_index)
        && plan.logical_command.get(plan.playwright_cli_command_index)
            == Some(&plan.playwright_cli_path)
        && plan
            .logical_command
            .iter()
            .filter(|part| *part == &plan.playwright_cli_path)
            .count()
            == 1
        && plan.logical_command.iter().all(|part| {
            !part.is_empty() && part.len() <= 1024 && !part.chars().any(char::is_control)
        });
    let mut environment_names = BTreeSet::new();
    environment_names.insert(plan.base_url_environment.as_str());
    let environment_valid = plan.extra_environment.len() <= 16
        && valid_environment_name(&plan.base_url_environment)
        && plan.extra_environment.iter().all(|(name, value)| {
            valid_environment_name(name)
                && valid_environment_value(value)
                && environment_names.insert(name.as_str())
        });
    let base_path_valid = plan.base_url_path.is_empty()
        || (plan.base_url_path.starts_with('/')
            && !plan.base_url_path.ends_with('/')
            && plan.base_url_path.len() <= 512
            && !plan
                .base_url_path
                .bytes()
                .any(|byte| matches!(byte, b'?' | b'#' | b'\\' | b'%'))
            && plan
                .base_url_path
                .trim_start_matches('/')
                .split('/')
                .all(|part| !part.is_empty() && !matches!(part, "." | ".."))
            && !plan.base_url_path.chars().any(char::is_control));
    if !command_valid || !environment_valid || !base_path_valid {
        return Err(FrontendContractError::new(
            "playwright_plan_invalid",
            "Playwright execution plan is invalid",
        ));
    }
    match &plan.server_route {
        PlaywrightServerRoute::Viewer(source) => validate_viewer_server_source(source),
        PlaywrightServerRoute::Scoped {
            allowed_path_prefix,
            root_redirect,
        } => validate_scoped_policy(allowed_path_prefix, root_redirect),
        PlaywrightServerRoute::Spa { fallback_entry } => validate_spa_policy(fallback_entry),
    }
}

fn valid_environment_name(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value
            .as_bytes()
            .first()
            .is_some_and(|byte| byte.is_ascii_uppercase() || *byte == b'_')
        && value
            .bytes()
            .all(|byte| byte.is_ascii_uppercase() || byte.is_ascii_digit() || byte == b'_')
}

fn valid_environment_value(value: &str) -> bool {
    value.len() <= 1024 && !value.chars().any(char::is_control)
}

fn start_server(plan: &PlaywrightPlan) -> Result<BrowserServer, FrontendContractError> {
    let listener =
        TcpListener::bind(SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0)).map_err(|error| {
            FrontendContractError::new(
                "playwright_bind_failed",
                format!("bind Playwright loopback server failed: {error}"),
            )
        })?;
    listener.set_nonblocking(true).map_err(|error| {
        FrontendContractError::new(
            "playwright_socket_config_failed",
            format!("configure Playwright listener failed: {error}"),
        )
    })?;
    let port = listener
        .local_addr()
        .map_err(|error| {
            FrontendContractError::new(
                "playwright_socket_config_failed",
                format!("inspect Playwright listener failed: {error}"),
            )
        })?
        .port();
    let stop = Arc::new(AtomicBool::new(false));
    let request_errors = Arc::new(AtomicU64::new(0));
    let (error_tx, error_rx) = mpsc::channel();
    let root = plan.server_root.clone();
    let route = plan.server_route.clone();
    let server_stop = Arc::clone(&stop);
    let server_request_errors = Arc::clone(&request_errors);
    let server_thread = thread::spawn(move || {
        while !server_stop.load(Ordering::Acquire) {
            match listener.accept() {
                Ok((stream, _)) => {
                    let result = match &route {
                        PlaywrightServerRoute::Viewer(source) => {
                            handle_stream(&root, source, stream)
                        }
                        PlaywrightServerRoute::Scoped {
                            allowed_path_prefix,
                            root_redirect,
                        } => {
                            handle_scoped_stream(&root, allowed_path_prefix, root_redirect, stream)
                        }
                        PlaywrightServerRoute::Spa { fallback_entry } => {
                            handle_spa_stream(&root, fallback_entry, stream)
                        }
                    };
                    if result.is_err() {
                        server_request_errors.fetch_add(1, Ordering::Relaxed);
                    }
                }
                Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                    thread::sleep(PROCESS_POLL_INTERVAL);
                }
                Err(error) => {
                    let _ignored = error_tx.send(format!(
                        "accept Playwright browser connection failed: {error}"
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
        error_rx,
        thread: server_thread,
    })
}

fn spawn_child(plan: &PlaywrightPlan, port: u16) -> Result<Child, FrontendContractError> {
    let base_url = format!("http://127.0.0.1:{port}{}", plan.base_url_path);
    let mut command = Command::new(&plan.node_launcher);
    command
        .args(&plan.logical_command[1..])
        .current_dir(&plan.root)
        .env(&plan.base_url_environment, &base_url)
        .stdin(Stdio::null())
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit());
    for (name, value) in &plan.extra_environment {
        command.env(name, value);
    }
    command.spawn().map_err(|error| {
        FrontendContractError::new(
            "playwright_launch_failed",
            format!("launch Playwright failed: {error}"),
        )
    })
}

fn wait_for_child(
    child: &mut Child,
    server_errors: &mpsc::Receiver<String>,
) -> Result<ExitStatus, FrontendContractError> {
    loop {
        if let Ok(detail) = server_errors.try_recv() {
            let _ignored = child.kill();
            let _ignored = child.wait();
            return Err(FrontendContractError::new(
                "playwright_server_failed",
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
                    "playwright_wait_failed",
                    format!("wait for Playwright failed: {error}"),
                ));
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use std::path::PathBuf;

    use super::{
        map_playwright_error, validate_playwright_plan, PlaywrightErrorDomain, PlaywrightPlan,
        PlaywrightServerRoute,
    };
    use crate::FrontendContractError;

    #[test]
    fn execution_plan_rejects_command_environment_and_base_path_drift() {
        let mut plan = PlaywrightPlan {
            root: PathBuf::from("."),
            server_root: PathBuf::from("."),
            node_launcher: "node".to_owned(),
            playwright_cli_path: "node_modules/@playwright/test/cli.js".to_owned(),
            playwright_cli_command_index: 1,
            logical_command: vec![
                "node".to_owned(),
                "node_modules/@playwright/test/cli.js".to_owned(),
                "test".to_owned(),
            ],
            base_url_environment: "TEST_BASE_URL".to_owned(),
            base_url_path: "/prototype/structural-workbench".to_owned(),
            extra_environment: Vec::new(),
            server_route: PlaywrightServerRoute::Scoped {
                allowed_path_prefix: "prototype/structural-workbench/".to_owned(),
                root_redirect: "/prototype/structural-workbench/index.html".to_owned(),
            },
        };
        assert!(validate_playwright_plan(&plan).is_ok());
        plan.base_url_path = "/../escape".to_owned();
        assert!(validate_playwright_plan(&plan).is_err());
        plan.base_url_path = String::new();
        plan.base_url_environment = "lowercase".to_owned();
        assert!(validate_playwright_plan(&plan).is_err());
    }

    #[test]
    fn public_wrappers_keep_domain_specific_error_taxonomy() {
        let viewer = map_playwright_error(
            PlaywrightErrorDomain::Viewer,
            FrontendContractError::new("playwright_failed", "failed"),
        );
        assert_eq!(viewer.code, "viewer_browser_smoke_failed");
        let prototype = map_playwright_error(
            PlaywrightErrorDomain::WorkbenchPrototype,
            FrontendContractError::new("playwright_bind_failed", "denied"),
        );
        assert_eq!(
            prototype.code,
            "workbench_prototype_browser_smoke_bind_failed"
        );
        let workbench_v2 = map_playwright_error(
            PlaywrightErrorDomain::WorkbenchV2,
            FrontendContractError::new("playwright_failed", "failed"),
        );
        assert_eq!(workbench_v2.code, "workbench_v2_browser_smoke_failed");
    }
}
