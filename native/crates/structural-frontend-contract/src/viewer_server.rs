use std::collections::BTreeSet;
use std::convert::Infallible;
use std::fmt::Write as _;
use std::io::{Read, Write};
use std::net::{Ipv4Addr, SocketAddrV4, TcpListener, TcpStream};
use std::path::{Component, Path};
use std::time::Duration;

use serde::{Deserialize, Serialize};
use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_contracts::product_ir::sha256_identity;

use super::{
    canonical_struct, parse_source_map, read_bounded_regular_file, resolve_required_file,
    validate_relative_path, verify_real_directory, FrontendContractError, SOURCE_MAP_BYTES,
};

const SERVER_CONTRACT_V1: &str = "structural-native-viewer-server-contract.v1";
const SERVER_RECEIPT_V1: &str = "structural-native-viewer-server-receipt.v1";
const MAX_REQUEST_HEADER_BYTES: usize = 16 * 1024;
const MAX_RESPONSE_BODY_BYTES: u64 = 64 * 1024 * 1024;
const READ_TIMEOUT: Duration = Duration::from_secs(5);
const WRITE_TIMEOUT: Duration = Duration::from_secs(30);
const EXPECTED_VIEWER_ENTRY: &str = "/src/structure-viewer/index.html";
const EXPECTED_DEFAULT_QUERY: &str =
    "project=midas33_release&drawing=midas33_optimized&variant=optimized";
const EXPECTED_ALLOWED_PREFIXES: [&str; 5] = [
    "src/structure-viewer/",
    "implementation/phase1/open_data/",
    "implementation/phase1/release/visualization/",
    "implementation/phase1/output/structural_svg/",
    "output/structural_svg/",
];

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ViewerServerSourceV1 {
    contract: String,
    default_host: String,
    default_port: u16,
    viewer_entry: String,
    default_query: String,
    allowed_path_prefixes: Vec<String>,
    claim_boundary: String,
}

/// Canonical, self-hashed startup plan for the transitional Rust Viewer server.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct ViewerServerReceiptV1 {
    pub schema_version: String,
    pub action: String,
    pub mode: String,
    pub status: String,
    pub source_map_sha256: String,
    pub host: String,
    pub port: u16,
    pub viewer_url: String,
    pub viewer_entry: String,
    pub default_query: String,
    pub allowed_path_prefixes: Vec<String>,
    pub loopback_only: bool,
    pub listener_count: u64,
    pub external_network_access_count: u64,
    pub commands_executed: u64,
    pub claim_boundary: String,
    pub receipt_hash: String,
}

#[derive(Debug, Eq, PartialEq)]
struct HttpResponse {
    status: u16,
    reason: &'static str,
    headers: Vec<(String, String)>,
    body: Vec<u8>,
    head_only: bool,
}

/// Build a deterministic no-listener startup plan for the Rust Viewer server.
///
/// # Errors
///
/// Rejects an unsafe root, non-loopback host, invalid port, missing Viewer entry, or malformed
/// embedded server contract.
pub fn plan_viewer_server(
    root: &Path,
    host: &str,
    port: u16,
) -> Result<ViewerServerReceiptV1, FrontendContractError> {
    prepare_server(root, host, port)?;
    build_receipt(host, port, true)
}

/// Bind and serve the transitional source Viewer on one IPv4 loopback address.
///
/// A canonical startup receipt is written before the accept loop. The function intentionally has
/// no success return: normal lifetime ends through process termination; listener, request, and
/// response errors fail closed.
///
/// # Errors
///
/// Rejects invalid configuration and returns stable I/O errors for bind, accept, read, or write
/// failures.
pub fn serve_viewer(
    root: &Path,
    host: &str,
    port: u16,
) -> Result<Infallible, FrontendContractError> {
    let source = prepare_server(root, host, port)?;
    let address = SocketAddrV4::new(Ipv4Addr::LOCALHOST, port);
    let listener = TcpListener::bind(address).map_err(|error| {
        FrontendContractError::new(
            "viewer_server_bind_failed",
            format!("bind Viewer loopback server failed: {error}"),
        )
    })?;
    let receipt = build_receipt(host, port, false)?;
    let encoded = canonical_viewer_server_receipt_json(&receipt)?;
    println!("{encoded}");
    std::io::stdout().flush().map_err(|error| {
        FrontendContractError::new(
            "viewer_server_output_failed",
            format!("flush Viewer server startup receipt failed: {error}"),
        )
    })?;

    loop {
        let (stream, _) = listener.accept().map_err(|error| {
            FrontendContractError::new(
                "viewer_server_accept_failed",
                format!("accept Viewer loopback connection failed: {error}"),
            )
        })?;
        handle_stream(root, &source, stream)?;
    }
}

pub(crate) fn handle_stream(
    root: &Path,
    source: &ViewerServerSourceV1,
    mut stream: TcpStream,
) -> Result<(), FrontendContractError> {
    stream.set_nonblocking(false).map_err(|error| {
        FrontendContractError::new(
            "viewer_server_socket_config_failed",
            format!("configure Viewer connection blocking mode failed: {error}"),
        )
    })?;
    stream
        .set_read_timeout(Some(READ_TIMEOUT))
        .map_err(|error| {
            FrontendContractError::new(
                "viewer_server_socket_config_failed",
                format!("set Viewer request timeout failed: {error}"),
            )
        })?;
    stream
        .set_write_timeout(Some(WRITE_TIMEOUT))
        .map_err(|error| {
            FrontendContractError::new(
                "viewer_server_socket_config_failed",
                format!("set Viewer response timeout failed: {error}"),
            )
        })?;
    let response =
        match read_request(&mut stream).and_then(|request| route_request(root, source, &request)) {
            Ok(response) => response,
            Err(error) => error_response(400, "Bad Request", &error.detail),
        };
    write_response(&mut stream, &response)
}

/// Encode a Viewer server receipt as canonical JSON.
///
/// # Errors
///
/// Returns an error if the receipt cannot be projected into canonical JSON.
pub fn canonical_viewer_server_receipt_json(
    receipt: &ViewerServerReceiptV1,
) -> Result<String, FrontendContractError> {
    canonical_struct(receipt, "viewer_server_receipt_encode_failed")
}

pub(crate) fn validate_viewer_server_source(
    source: &ViewerServerSourceV1,
) -> Result<(), FrontendContractError> {
    if source.contract != SERVER_CONTRACT_V1
        || source.default_host != "127.0.0.1"
        || source.default_port != 8765
        || source.viewer_entry != EXPECTED_VIEWER_ENTRY
        || source.default_query != EXPECTED_DEFAULT_QUERY
        || !valid_query(&source.default_query)
        || source
            .allowed_path_prefixes
            .iter()
            .map(String::as_str)
            .ne(EXPECTED_ALLOWED_PREFIXES)
        || !valid_text(&source.claim_boundary)
    {
        return Err(source_error("Viewer server contract metadata is invalid"));
    }
    validate_relative_path(source.viewer_entry.trim_start_matches('/'))?;
    let mut prefixes = BTreeSet::new();
    for prefix in &source.allowed_path_prefixes {
        if !prefix.ends_with('/') {
            return Err(source_error(
                "Viewer server allowed path prefixes must end in a slash",
            ));
        }
        validate_relative_path(prefix.trim_end_matches('/'))?;
        if !prefixes.insert(prefix) {
            return Err(source_error(
                "Viewer server allowed path prefixes must be unique",
            ));
        }
    }
    if !source.allowed_path_prefixes.iter().any(|prefix| {
        source
            .viewer_entry
            .trim_start_matches('/')
            .starts_with(prefix)
    }) {
        return Err(source_error(
            "Viewer server entry must be inside an allowed path prefix",
        ));
    }
    Ok(())
}

pub(crate) fn prepare_server(
    root: &Path,
    host: &str,
    port: u16,
) -> Result<ViewerServerSourceV1, FrontendContractError> {
    verify_real_directory(root, "Viewer server root")?;
    let source = parse_source_map()?.viewer_server_contract;
    if host != source.default_host || host != "127.0.0.1" {
        return Err(FrontendContractError::new(
            "viewer_server_host_forbidden",
            "Viewer server host must be the frozen IPv4 loopback address 127.0.0.1",
        ));
    }
    if port == 0 {
        return Err(FrontendContractError::new(
            "viewer_server_port_invalid",
            "Viewer server port must be in 1..=65535",
        ));
    }
    resolve_required_file(root, source.viewer_entry.trim_start_matches('/'))?;
    Ok(source)
}

fn build_receipt(
    host: &str,
    port: u16,
    dry_run: bool,
) -> Result<ViewerServerReceiptV1, FrontendContractError> {
    let source = parse_source_map()?.viewer_server_contract;
    let mut receipt = ViewerServerReceiptV1 {
        schema_version: SERVER_RECEIPT_V1.to_owned(),
        action: "viewer_server".to_owned(),
        mode: if dry_run { "dry_run" } else { "serve" }.to_owned(),
        status: if dry_run { "planned" } else { "listening" }.to_owned(),
        source_map_sha256: sha256_identity(SOURCE_MAP_BYTES),
        host: host.to_owned(),
        port,
        viewer_url: format!(
            "http://{host}:{port}{}?{}",
            source.viewer_entry, source.default_query
        ),
        viewer_entry: source.viewer_entry,
        default_query: source.default_query,
        allowed_path_prefixes: source.allowed_path_prefixes,
        loopback_only: true,
        listener_count: u64::from(!dry_run),
        external_network_access_count: 0,
        commands_executed: 0,
        claim_boundary: source.claim_boundary,
        receipt_hash: String::new(),
    };
    receipt.receipt_hash = hash_without_receipt_hash(&receipt)?;
    Ok(receipt)
}

fn read_request(stream: &mut TcpStream) -> Result<Vec<u8>, FrontendContractError> {
    let mut request = Vec::with_capacity(1024);
    let mut chunk = [0_u8; 1024];
    loop {
        let read = stream.read(&mut chunk).map_err(|error| {
            FrontendContractError::new(
                "viewer_server_request_read_failed",
                format!("read Viewer request failed: {error}"),
            )
        })?;
        if read == 0 {
            break;
        }
        request.extend_from_slice(&chunk[..read]);
        if request.len() > MAX_REQUEST_HEADER_BYTES {
            return Err(FrontendContractError::new(
                "viewer_server_request_too_large",
                "Viewer request headers exceed 16 KiB",
            ));
        }
        if request.windows(4).any(|window| window == b"\r\n\r\n") {
            break;
        }
    }
    if request.is_empty() || !request.windows(4).any(|window| window == b"\r\n\r\n") {
        return Err(FrontendContractError::new(
            "viewer_server_request_invalid",
            "Viewer request headers are incomplete",
        ));
    }
    Ok(request)
}

fn route_request(
    root: &Path,
    source: &ViewerServerSourceV1,
    request: &[u8],
) -> Result<HttpResponse, FrontendContractError> {
    let text = std::str::from_utf8(request).map_err(|error| {
        FrontendContractError::new(
            "viewer_server_request_invalid",
            format!("Viewer request headers are not UTF-8: {error}"),
        )
    })?;
    let line = text.lines().next().ok_or_else(|| {
        FrontendContractError::new(
            "viewer_server_request_invalid",
            "Viewer request line is missing",
        )
    })?;
    let mut fields = line.split_ascii_whitespace();
    let method = fields.next().unwrap_or_default();
    let target = fields.next().unwrap_or_default();
    let version = fields.next().unwrap_or_default();
    if fields.next().is_some()
        || !matches!(method, "GET" | "HEAD")
        || !matches!(version, "HTTP/1.0" | "HTTP/1.1")
        || !target.starts_with('/')
    {
        return Ok(error_response(
            405,
            "Method Not Allowed",
            "Only bounded GET and HEAD requests are supported",
        ));
    }
    let raw_path = target.split('?').next().unwrap_or_default();
    if matches!(raw_path, "/" | "/index.html") {
        return Ok(HttpResponse {
            status: 302,
            reason: "Found",
            headers: vec![(
                "Location".to_owned(),
                format!("{}?{}", source.viewer_entry, source.default_query),
            )],
            body: Vec::new(),
            head_only: method == "HEAD",
        });
    }
    let decoded = percent_decode_path(raw_path)?;
    let relative = decoded.trim_start_matches('/');
    if !allowed_relative_path(relative, &source.allowed_path_prefixes) {
        return Ok(error_response(403, "Forbidden", "Forbidden"));
    }
    let path = match resolve_required_file(root, relative) {
        Ok(path) => path,
        Err(error) if error.code == "frontend_required_file_missing" => {
            return Ok(error_response(404, "Not Found", "Not found"));
        }
        Err(error) => return Err(error),
    };
    let body = read_bounded_regular_file(&path, MAX_RESPONSE_BODY_BYTES, "Viewer response file")?;
    Ok(HttpResponse {
        status: 200,
        reason: "OK",
        headers: vec![("Content-Type".to_owned(), content_type(relative).to_owned())],
        body,
        head_only: method == "HEAD",
    })
}

fn allowed_relative_path(relative: &str, prefixes: &[String]) -> bool {
    if relative.is_empty()
        || relative.len() > 1024
        || relative.contains('\0')
        || relative.contains('\\')
        || relative.split('/').any(|part| part.starts_with('.'))
        || !Path::new(relative)
            .components()
            .all(|component| matches!(component, Component::Normal(_)))
    {
        return false;
    }
    prefixes.iter().any(|prefix| relative.starts_with(prefix))
}

fn percent_decode_path(value: &str) -> Result<String, FrontendContractError> {
    let bytes = value.as_bytes();
    let mut decoded = Vec::with_capacity(bytes.len());
    let mut index = 0;
    while index < bytes.len() {
        if bytes[index] != b'%' {
            decoded.push(bytes[index]);
            index += 1;
            continue;
        }
        let high = bytes.get(index + 1).and_then(|byte| hex_value(*byte));
        let low = bytes.get(index + 2).and_then(|byte| hex_value(*byte));
        let (Some(high), Some(low)) = (high, low) else {
            return Err(FrontendContractError::new(
                "viewer_server_path_invalid",
                "Viewer request path has invalid percent encoding",
            ));
        };
        decoded.push((high << 4) | low);
        index += 3;
    }
    String::from_utf8(decoded).map_err(|error| {
        FrontendContractError::new(
            "viewer_server_path_invalid",
            format!("Viewer request path is not UTF-8: {error}"),
        )
    })
}

fn hex_value(byte: u8) -> Option<u8> {
    match byte {
        b'0'..=b'9' => Some(byte - b'0'),
        b'a'..=b'f' => Some(byte - b'a' + 10),
        b'A'..=b'F' => Some(byte - b'A' + 10),
        _ => None,
    }
}

fn error_response(status: u16, reason: &'static str, detail: &str) -> HttpResponse {
    let mut body = detail.as_bytes().to_vec();
    if body.len() > 1024 {
        body.truncate(1024);
    }
    HttpResponse {
        status,
        reason,
        headers: vec![(
            "Content-Type".to_owned(),
            "text/plain; charset=utf-8".to_owned(),
        )],
        body,
        head_only: false,
    }
}

fn write_response(
    stream: &mut TcpStream,
    response: &HttpResponse,
) -> Result<(), FrontendContractError> {
    let mut head = format!("HTTP/1.1 {} {}\r\n", response.status, response.reason);
    for (name, value) in &response.headers {
        head.push_str(name);
        head.push_str(": ");
        head.push_str(value);
        head.push_str("\r\n");
    }
    write!(
        head,
        "Content-Length: {}\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\nConnection: close\r\n\r\n",
        response.body.len()
    )
    .map_err(|error| {
        FrontendContractError::new(
            "viewer_server_response_encode_failed",
            format!("encode Viewer response headers failed: {error}"),
        )
    })?;
    stream.write_all(head.as_bytes()).map_err(|error| {
        FrontendContractError::new(
            "viewer_server_response_write_failed",
            format!("write Viewer response headers failed: {error}"),
        )
    })?;
    if !response.head_only {
        stream.write_all(&response.body).map_err(|error| {
            FrontendContractError::new(
                "viewer_server_response_write_failed",
                format!("write Viewer response body failed: {error}"),
            )
        })?;
    }
    Ok(())
}

fn content_type(path: &str) -> &'static str {
    match Path::new(path).extension().and_then(|value| value.to_str()) {
        Some("css") => "text/css; charset=utf-8",
        Some("html") => "text/html; charset=utf-8",
        Some("js" | "mjs") => "text/javascript; charset=utf-8",
        Some("json") => "application/json; charset=utf-8",
        Some("png") => "image/png",
        Some("svg") => "image/svg+xml",
        Some("woff2") => "font/woff2",
        _ => "application/octet-stream",
    }
}

fn valid_query(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 2048
        && value.bytes().all(|byte| {
            byte.is_ascii_alphanumeric() || matches!(byte, b'=' | b'&' | b'-' | b'_' | b'.')
        })
}

fn valid_text(value: &str) -> bool {
    !value.trim().is_empty() && value.len() <= 16 * 1024 && !value.chars().any(char::is_control)
}

fn source_error(detail: &str) -> FrontendContractError {
    FrontendContractError::new("frontend_source_map_contract_invalid", detail)
}

fn hash_without_receipt_hash(
    receipt: &ViewerServerReceiptV1,
) -> Result<String, FrontendContractError> {
    let mut value = serde_json::to_value(receipt).map_err(|error| {
        FrontendContractError::new(
            "viewer_server_receipt_encode_failed",
            format!("project Viewer server receipt failed: {error}"),
        )
    })?;
    value
        .as_object_mut()
        .ok_or_else(|| {
            FrontendContractError::new(
                "viewer_server_receipt_encode_failed",
                "Viewer server receipt projection is not an object",
            )
        })?
        .remove("receipt_hash");
    let canonical = canonicalize_model_ir_v2(&value).map_err(|error| {
        FrontendContractError::new(
            "viewer_server_receipt_encode_failed",
            format!("canonicalize Viewer server receipt failed: {error}"),
        )
    })?;
    Ok(sha256_identity(canonical.as_bytes()))
}

#[cfg(test)]
mod tests {
    use std::sync::atomic::{AtomicU64, Ordering};

    use super::{
        allowed_relative_path, content_type, percent_decode_path, route_request,
        validate_viewer_server_source, ViewerServerSourceV1,
    };

    static TEST_SEQUENCE: AtomicU64 = AtomicU64::new(0);

    fn source() -> ViewerServerSourceV1 {
        ViewerServerSourceV1 {
            contract: "structural-native-viewer-server-contract.v1".to_owned(),
            default_host: "127.0.0.1".to_owned(),
            default_port: 8765,
            viewer_entry: "/src/structure-viewer/index.html".to_owned(),
            default_query: "project=midas33_release&drawing=midas33_optimized&variant=optimized"
                .to_owned(),
            allowed_path_prefixes: vec!["src/structure-viewer/".to_owned()],
            claim_boundary: "bounded".to_owned(),
        }
    }

    #[test]
    fn request_paths_are_decoded_and_confined_to_allowed_roots() {
        let prefixes = vec![
            "src/structure-viewer/".to_owned(),
            "implementation/phase1/open_data/".to_owned(),
        ];
        assert_eq!(
            percent_decode_path("/src/structure-viewer/index%2Ehtml").expect("decode safe path"),
            "/src/structure-viewer/index.html"
        );
        assert!(allowed_relative_path(
            "src/structure-viewer/index.html",
            &prefixes
        ));
        assert!(!allowed_relative_path(
            "src/structure-viewer/../main.tsx",
            &prefixes
        ));
        assert!(!allowed_relative_path(".git/config", &prefixes));
        assert!(!allowed_relative_path("package.json", &prefixes));
        assert!(percent_decode_path("/%GG").is_err());
        assert_eq!(content_type("asset.js"), "text/javascript; charset=utf-8");
    }

    #[test]
    fn server_contract_cannot_widen_the_frozen_path_allowlist() {
        let mut source = source();
        source.allowed_path_prefixes = vec![
            "src/structure-viewer/".to_owned(),
            "implementation/phase1/open_data/".to_owned(),
            "implementation/phase1/release/visualization/".to_owned(),
            "implementation/phase1/output/structural_svg/".to_owned(),
            "output/structural_svg/".to_owned(),
        ];
        assert!(validate_viewer_server_source(&source).is_ok());
        source.allowed_path_prefixes = vec!["src/".to_owned()];
        assert!(validate_viewer_server_source(&source).is_err());
    }

    #[test]
    fn router_serves_only_bounded_allowed_files_without_a_socket() {
        let root = std::env::temp_dir().join(format!(
            "structural-viewer-server-router-test-{}-{}",
            std::process::id(),
            TEST_SEQUENCE.fetch_add(1, Ordering::Relaxed)
        ));
        let viewer = root.join("src/structure-viewer");
        std::fs::create_dir_all(&viewer).expect("create Viewer fixture");
        std::fs::write(viewer.join("index.html"), b"<html>viewer</html>\n")
            .expect("write Viewer fixture");
        std::fs::write(root.join("secret.txt"), b"secret\n").expect("write forbidden fixture");
        let source = source();

        let get = route_request(
            &root,
            &source,
            b"GET /src/structure-viewer/index.html HTTP/1.1\r\nHost: localhost\r\n\r\n",
        )
        .expect("route GET");
        assert_eq!(get.status, 200);
        assert_eq!(get.body, b"<html>viewer</html>\n");
        assert!(!get.head_only);

        let head = route_request(
            &root,
            &source,
            b"HEAD /src/structure-viewer/index.html HTTP/1.1\r\nHost: localhost\r\n\r\n",
        )
        .expect("route HEAD");
        assert_eq!(head.status, 200);
        assert!(head.head_only);

        let redirect = route_request(&root, &source, b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
            .expect("route redirect");
        assert_eq!(redirect.status, 302);
        assert!(redirect.headers.iter().any(|(name, value)| {
            name == "Location" && value.contains("project=midas33_release")
        }));

        for target in [
            "/secret.txt",
            "/.git/config",
            "/src/structure-viewer/%2e%2e/index.html",
        ] {
            let request = format!("GET {target} HTTP/1.1\r\nHost: localhost\r\n\r\n");
            let response =
                route_request(&root, &source, request.as_bytes()).expect("route forbidden path");
            assert_eq!(response.status, 403);
            assert!(!response.body.windows(6).any(|window| window == b"secret"));
        }

        std::fs::remove_dir_all(root).expect("remove Viewer router fixture");
    }
}
