//! Loopback-only HTTP composition for the bounded native Frame Alpha Workbench flow.

use std::collections::BTreeMap;
use std::fmt::{self, Write as _};
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::{Component, Path, PathBuf};
use std::time::Duration;

use serde_json::{json, Value};
use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_contracts::native_job::{
    parse_native_frame3d_job_submission_v1, NativeFrame3dJobStatusV1,
};
use structural_runtime::NativeFrame3dJobStore;

const HEADER_MAX_BYTES: usize = 16 * 1024;
const BODY_MAX_BYTES: usize = 2 * 1024 * 1024 + 64 * 1024;
const RESPONSE_MAX_BYTES: u64 = 2 * 1024 * 1024;
const IO_TIMEOUT: Duration = Duration::from_secs(10);

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct WorkstationServeOptions {
    pub(crate) store: PathBuf,
    pub(crate) workbench: PathBuf,
    pub(crate) listen: SocketAddr,
    pub(crate) max_requests: Option<u32>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct WorkstationServeError {
    pub(crate) code: String,
    pub(crate) detail: String,
}

impl fmt::Display for WorkstationServeError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{}: {}", self.code, self.detail)
    }
}

impl std::error::Error for WorkstationServeError {}

#[derive(Clone, Debug, Eq, PartialEq)]
struct RequestError {
    status: u16,
    code: &'static str,
    detail: &'static str,
}

#[derive(Debug)]
struct HttpRequest {
    method: String,
    path: String,
    headers: BTreeMap<String, String>,
    body: Vec<u8>,
}

#[derive(Debug)]
struct HttpResponse {
    status: u16,
    content_type: &'static str,
    body: Vec<u8>,
    location: Option<String>,
    api: bool,
}

#[allow(clippy::too_many_lines)]
pub(crate) fn serve(options: &WorkstationServeOptions) -> Result<(), WorkstationServeError> {
    if !options.listen.ip().is_loopback() {
        return Err(server_error(
            "workstation_non_loopback_forbidden",
            "The bounded workstation host may bind only to a loopback address",
        ));
    }
    if options.max_requests == Some(0) {
        return Err(server_error(
            "workstation_max_requests_invalid",
            "Maximum request count must be positive when specified",
        ));
    }
    let workbench_root = std::fs::canonicalize(&options.workbench).map_err(|_| {
        server_error(
            "workstation_workbench_missing",
            "Workbench distribution directory could not be resolved",
        )
    })?;
    if !workbench_root.join("index.html").is_file() {
        return Err(server_error(
            "workstation_workbench_index_missing",
            "Workbench distribution must contain index.html",
        ));
    }
    std::fs::create_dir_all(&options.store).map_err(|_| {
        server_error(
            "workstation_store_create_failed",
            "Native workstation job store could not be created",
        )
    })?;
    let listener = TcpListener::bind(options.listen).map_err(|_| {
        server_error(
            "workstation_bind_failed",
            "Loopback workstation listener could not be bound",
        )
    })?;
    let address = listener.local_addr().map_err(|_| {
        server_error(
            "workstation_address_failed",
            "Bound workstation address could not be inspected",
        )
    })?;
    let origin = format!("http://{address}");
    let startup = canonicalize_model_ir_v2(&json!({
        "schema_version": "structural-native-frame-alpha-workstation-host.v1",
        "origin": origin,
        "workbench_url": format!("{origin}/"),
        "submission_url": format!("{origin}/api/v1/frame3d/jobs"),
        "service_profile": "loopback_single_process_synchronous.v1",
        "capabilities": {
            "browser_submission": true,
            "synchronous_run": true,
            "process_isolation": false,
            "cancellation": false,
            "resume": false,
            "crash_recovery": false,
            "multi_host": false
        },
        "authority": {
            "result": "referenced_hash_bound_bundle_contract_only",
            "external_validation": "not_established",
            "engineering_design": "not_authoritative",
            "release_readiness": "not_authoritative"
        },
        "claim_boundary": "bounded_loopback_workbench_execution_not_durable_worker_external_validation_design_or_release_authority"
    }))
    .map_err(|_| {
        server_error(
            "workstation_startup_receipt_failed",
            "Workstation startup receipt could not be serialized",
        )
    })?;
    println!("{startup}");
    std::io::stdout().flush().map_err(|_| {
        server_error(
            "workstation_startup_receipt_failed",
            "Workstation startup receipt could not be flushed",
        )
    })?;

    let store = NativeFrame3dJobStore::new(&options.store);
    let mut served = 0_u32;
    for incoming in listener.incoming() {
        let mut stream = incoming.map_err(|_| {
            server_error(
                "workstation_accept_failed",
                "Loopback workstation request could not be accepted",
            )
        })?;
        let _read_timeout = stream.set_read_timeout(Some(IO_TIMEOUT));
        let _write_timeout = stream.set_write_timeout(Some(IO_TIMEOUT));
        let response = match read_request(&mut stream) {
            Ok(request) => route(&request, &store, &workbench_root, address),
            Err(error) => error_response(error.status, error.code, error.detail),
        };
        let _response_written = write_response(&mut stream, response);
        served = served.saturating_add(1);
        if options.max_requests.is_some_and(|limit| served >= limit) {
            break;
        }
    }
    Ok(())
}

#[allow(clippy::too_many_lines)]
fn route(
    request: &HttpRequest,
    store: &NativeFrame3dJobStore,
    workbench_root: &Path,
    address: SocketAddr,
) -> HttpResponse {
    let expected_host = address.to_string();
    if request.headers.get("host") != Some(&expected_host) {
        return error_response(
            400,
            "workstation_host_invalid",
            "Host header is not the bound loopback authority",
        );
    }
    let segments = request
        .path
        .trim_start_matches('/')
        .split('/')
        .filter(|item| !item.is_empty())
        .collect::<Vec<_>>();

    if request.method == "GET" && segments == ["api", "v1", "capabilities"] {
        return json_response(
            200,
            &json!({
                "schema_version": "structural-native-frame-alpha-workstation-capabilities.v1",
                "service_profile": "loopback_single_process_synchronous.v1",
                "browser_submission": true,
                "synchronous_run": true,
                "process_isolation": false,
                "cancellation": false,
                "resume": false,
                "crash_recovery": false,
                "multi_host": false,
                "claim_boundary": "capability_declaration_not_execution_result_or_release_authority"
            }),
            None,
        );
    }
    if request.method == "POST" {
        let expected_origin = format!("http://{address}");
        if request.headers.get("origin") != Some(&expected_origin) {
            return error_response(
                403,
                "workstation_origin_forbidden",
                "Mutation requires the exact same-origin Workbench origin",
            );
        }
        if !request
            .headers
            .get("content-type")
            .is_some_and(|value| value.eq_ignore_ascii_case("application/json"))
        {
            return error_response(
                415,
                "workstation_content_type_invalid",
                "Mutation requires application/json",
            );
        }
    }
    if request.method == "POST" && segments == ["api", "v1", "frame3d", "jobs"] {
        let submission = match parse_native_frame3d_job_submission_v1(&request.body) {
            Ok(value) => value,
            Err(error) => {
                return error_response(
                    422,
                    "workstation_submission_invalid",
                    &format!("{} at {}", error.code, error.path),
                )
            }
        };
        return match store.submit(
            &submission.job_id,
            submission.model_ir_json.as_bytes(),
            submission.load_source,
            &submission.result_id,
            &submission.report_id,
        ) {
            Ok(view) => match view.canonical_json() {
                Ok(body) => HttpResponse {
                    status: 201,
                    content_type: "application/json; charset=utf-8",
                    body: body.into_bytes(),
                    location: Some(format!(
                        "/api/v1/frame3d/jobs/{}/view.json",
                        submission.job_id
                    )),
                    api: true,
                },
                Err(_) => error_response(
                    500,
                    "workstation_view_serialize_failed",
                    "Queued job view could not be serialized",
                ),
            },
            Err(error) => {
                let status = if error.code == "native_job_already_exists" {
                    409
                } else {
                    422
                };
                error_response(status, "workstation_submit_failed", &error.code)
            }
        };
    }
    if request.method == "POST"
        && segments.len() == 6
        && segments[..4] == ["api", "v1", "frame3d", "jobs"]
        && segments[5] == "run"
    {
        if !request.body.is_empty() && request.body != b"{}" {
            return error_response(
                422,
                "workstation_run_body_invalid",
                "Run request body must be an empty JSON object",
            );
        }
        return match store.run(segments[4]) {
            Ok(view) => match view.canonical_json() {
                Ok(body) => HttpResponse {
                    status: 200,
                    content_type: "application/json; charset=utf-8",
                    body: body.into_bytes(),
                    location: None,
                    api: true,
                },
                Err(_) => error_response(
                    500,
                    "workstation_view_serialize_failed",
                    "Terminal job view could not be serialized",
                ),
            },
            Err(error) => {
                let status = if error.code == "native_job_not_queued" {
                    409
                } else {
                    422
                };
                error_response(status, "workstation_run_failed", &error.code)
            }
        };
    }
    if request.method == "GET"
        && segments.len() == 6
        && segments[..4] == ["api", "v1", "frame3d", "jobs"]
        && segments[5] == "view.json"
    {
        return match store.inspect(segments[4]) {
            Ok(view) => match view.canonical_json() {
                Ok(body) => HttpResponse {
                    status: 200,
                    content_type: "application/json; charset=utf-8",
                    body: body.into_bytes(),
                    location: None,
                    api: true,
                },
                Err(_) => error_response(
                    500,
                    "workstation_view_serialize_failed",
                    "Job view could not be serialized",
                ),
            },
            Err(error) => error_response(404, "workstation_job_not_found", &error.code),
        };
    }
    if request.method == "GET"
        && segments.len() == 7
        && segments[..4] == ["api", "v1", "frame3d", "jobs"]
        && segments[5] == "bundle"
    {
        let allowed = matches!(
            segments[6],
            "manifest.json" | "model-ir.json" | "result-ir.json" | "report-ir.json" | "report.html"
        );
        if !allowed {
            return error_response(
                404,
                "workstation_artifact_not_found",
                "Requested job artifact is not published",
            );
        }
        let view = match store.inspect(segments[4]) {
            Ok(value) if value.status == NativeFrame3dJobStatusV1::Succeeded => value,
            Ok(_) => {
                return error_response(
                    409,
                    "workstation_job_not_succeeded",
                    "Job has no authoritative completed bundle",
                )
            }
            Err(error) => return error_response(404, "workstation_job_not_found", &error.code),
        };
        if view.bundle_manifest.is_none() {
            return error_response(
                409,
                "workstation_job_not_succeeded",
                "Succeeded job has no authoritative bundle reference",
            );
        }
        let path = store
            .root()
            .join(segments[4])
            .join("bundle")
            .join(segments[6]);
        return match read_regular_bounded(&path, RESPONSE_MAX_BYTES) {
            Ok(body) => HttpResponse {
                status: 200,
                content_type: if segments[6] == "report.html" {
                    "text/html; charset=utf-8"
                } else {
                    "application/json; charset=utf-8"
                },
                body,
                location: None,
                api: true,
            },
            Err(()) => error_response(
                404,
                "workstation_artifact_not_found",
                "Requested job artifact is missing or invalid",
            ),
        };
    }
    if request.method != "GET" {
        return error_response(
            405,
            "workstation_method_not_allowed",
            "HTTP method is not allowed for this route",
        );
    }
    serve_static(workbench_root, &request.path)
}

fn serve_static(root: &Path, request_path: &str) -> HttpResponse {
    if request_path.contains('%') || request_path.contains('\\') || request_path.contains('\0') {
        return error_response(
            400,
            "workstation_static_path_invalid",
            "Static path contains a forbidden encoding or separator",
        );
    }
    let relative = request_path.trim_start_matches('/');
    let requested = if relative.is_empty() {
        Path::new("index.html")
    } else {
        Path::new(relative)
    };
    if requested
        .components()
        .any(|component| !matches!(component, Component::Normal(_)))
    {
        return error_response(
            400,
            "workstation_static_path_invalid",
            "Static path is outside the Workbench root",
        );
    }
    let candidate = root.join(requested);
    let resolved = std::fs::canonicalize(&candidate).ok();
    let selected = resolved
        .filter(|path| path.starts_with(root) && path.is_file())
        .or_else(|| {
            if requested.extension().is_none() {
                Some(root.join("index.html"))
            } else {
                None
            }
        });
    let Some(path) = selected else {
        return error_response(
            404,
            "workstation_static_not_found",
            "Workbench static asset was not found",
        );
    };
    let Ok(body) = read_regular_bounded(&path, 16 * 1024 * 1024) else {
        return error_response(
            404,
            "workstation_static_not_found",
            "Workbench static asset could not be read",
        );
    };
    let content_type = match path.extension().and_then(|value| value.to_str()) {
        Some("html") => "text/html; charset=utf-8",
        Some("js") => "text/javascript; charset=utf-8",
        Some("css") => "text/css; charset=utf-8",
        Some("json") => "application/json; charset=utf-8",
        Some("svg") => "image/svg+xml",
        Some("png") => "image/png",
        Some("ico") => "image/x-icon",
        Some("woff2") => "font/woff2",
        _ => "application/octet-stream",
    };
    HttpResponse {
        status: 200,
        content_type,
        body,
        location: None,
        api: false,
    }
}

#[allow(clippy::too_many_lines)]
fn read_request(stream: &mut TcpStream) -> Result<HttpRequest, RequestError> {
    let mut bytes = Vec::new();
    let mut chunk = [0_u8; 4096];
    let header_end = loop {
        let count = stream.read(&mut chunk).map_err(|_| {
            request_error(
                400,
                "workstation_request_read_failed",
                "HTTP request could not be read",
            )
        })?;
        if count == 0 {
            return Err(request_error(
                400,
                "workstation_request_incomplete",
                "HTTP request ended before its headers",
            ));
        }
        bytes.extend_from_slice(&chunk[..count]);
        if let Some(position) = find_bytes(&bytes, b"\r\n\r\n") {
            break position + 4;
        }
        if bytes.len() > HEADER_MAX_BYTES {
            return Err(request_error(
                431,
                "workstation_headers_oversized",
                "HTTP headers exceed the bounded limit",
            ));
        }
    };
    if header_end > HEADER_MAX_BYTES {
        return Err(request_error(
            431,
            "workstation_headers_oversized",
            "HTTP headers exceed the bounded limit",
        ));
    }
    let header_text = std::str::from_utf8(&bytes[..header_end - 4]).map_err(|_| {
        request_error(
            400,
            "workstation_headers_invalid",
            "HTTP headers are not valid UTF-8",
        )
    })?;
    let mut lines = header_text.split("\r\n");
    let request_line = lines.next().ok_or_else(|| {
        request_error(
            400,
            "workstation_request_line_invalid",
            "HTTP request line is missing",
        )
    })?;
    let parts = request_line.split(' ').collect::<Vec<_>>();
    if parts.len() != 3 || !matches!(parts[2], "HTTP/1.0" | "HTTP/1.1") {
        return Err(request_error(
            400,
            "workstation_request_line_invalid",
            "HTTP request line is invalid",
        ));
    }
    if !matches!(parts[0], "GET" | "POST")
        || !parts[1].starts_with('/')
        || parts[1].len() > 2048
        || parts[1].contains('?')
    {
        return Err(request_error(
            400,
            "workstation_request_target_invalid",
            "HTTP method or request target is invalid",
        ));
    }
    let method = parts[0].to_owned();
    let path = parts[1].to_owned();
    let mut headers = BTreeMap::new();
    for line in lines {
        let (name, value) = line.split_once(':').ok_or_else(|| {
            request_error(
                400,
                "workstation_header_invalid",
                "HTTP header is malformed",
            )
        })?;
        if name.is_empty()
            || !name
                .bytes()
                .all(|item| item.is_ascii_alphanumeric() || item == b'-')
        {
            return Err(request_error(
                400,
                "workstation_header_invalid",
                "HTTP header name is invalid",
            ));
        }
        let name = name.to_ascii_lowercase();
        if headers.insert(name, value.trim().to_owned()).is_some() {
            return Err(request_error(
                400,
                "workstation_header_duplicate",
                "Duplicate HTTP headers are forbidden",
            ));
        }
    }
    if headers.contains_key("transfer-encoding") {
        return Err(request_error(
            400,
            "workstation_transfer_encoding_forbidden",
            "Transfer-Encoding is unsupported",
        ));
    }
    let content_length = match headers.get("content-length") {
        Some(value) => value.parse::<usize>().map_err(|_| {
            request_error(
                400,
                "workstation_content_length_invalid",
                "Content-Length is invalid",
            )
        })?,
        None if method == "POST" => {
            return Err(request_error(
                411,
                "workstation_content_length_required",
                "POST requires Content-Length",
            ))
        }
        None => 0,
    };
    if content_length > BODY_MAX_BYTES {
        return Err(request_error(
            413,
            "workstation_body_oversized",
            "HTTP body exceeds the bounded limit",
        ));
    }
    let total = header_end + content_length;
    if method == "GET" && content_length != 0 {
        return Err(request_error(
            400,
            "workstation_get_body_forbidden",
            "GET request bodies are forbidden",
        ));
    }
    if bytes.len() > total {
        return Err(request_error(
            400,
            "workstation_request_smuggling_forbidden",
            "Trailing bytes after the declared HTTP body are forbidden",
        ));
    }
    while bytes.len() < total {
        let count = stream.read(&mut chunk).map_err(|_| {
            request_error(
                400,
                "workstation_request_read_failed",
                "HTTP request body could not be read",
            )
        })?;
        if count == 0 {
            return Err(request_error(
                400,
                "workstation_request_incomplete",
                "HTTP request body ended early",
            ));
        }
        bytes.extend_from_slice(&chunk[..count]);
        if bytes.len() > total {
            return Err(request_error(
                400,
                "workstation_request_smuggling_forbidden",
                "Trailing bytes after the declared HTTP body are forbidden",
            ));
        }
    }
    Ok(HttpRequest {
        method,
        path,
        headers,
        body: bytes[header_end..total].to_vec(),
    })
}

fn write_response(stream: &mut TcpStream, response: HttpResponse) -> std::io::Result<()> {
    let reason = match response.status {
        200 => "OK",
        201 => "Created",
        400 => "Bad Request",
        403 => "Forbidden",
        404 => "Not Found",
        405 => "Method Not Allowed",
        409 => "Conflict",
        411 => "Length Required",
        413 => "Payload Too Large",
        415 => "Unsupported Media Type",
        422 => "Unprocessable Content",
        431 => "Request Header Fields Too Large",
        _ => "Internal Server Error",
    };
    let mut headers = format!(
        "HTTP/1.1 {} {}\r\nContent-Type: {}\r\nContent-Length: {}\r\nConnection: close\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\n",
        response.status,
        reason,
        response.content_type,
        response.body.len()
    );
    if response.api {
        headers.push_str("Cache-Control: no-store\r\n");
    } else {
        headers.push_str("Cache-Control: no-cache\r\n");
    }
    if let Some(location) = response.location {
        let _write_result = write!(&mut headers, "Location: {location}\r\n");
    }
    headers.push_str("\r\n");
    stream.write_all(headers.as_bytes())?;
    stream.write_all(&response.body)?;
    stream.flush()
}

fn json_response(status: u16, value: &Value, location: Option<String>) -> HttpResponse {
    let body = canonicalize_model_ir_v2(value)
        .unwrap_or_else(|_| "{\"success\":false}".to_owned())
        .into_bytes();
    HttpResponse {
        status,
        content_type: "application/json; charset=utf-8",
        body,
        location,
        api: true,
    }
}

fn error_response(status: u16, code: &'static str, detail: &str) -> HttpResponse {
    json_response(
        status,
        &json!({
            "schema_version": "structural-native-workstation-http-error.v1",
            "success": false,
            "issues": [{"code": code, "detail": detail.chars().take(256).collect::<String>()}],
            "claim_boundary": "http_operation_failed_closed_without_job_result_design_or_release_authority"
        }),
        None,
    )
}

fn read_regular_bounded(path: &Path, maximum: u64) -> Result<Vec<u8>, ()> {
    let metadata = std::fs::metadata(path).map_err(|_| ())?;
    if !metadata.is_file() || metadata.len() == 0 || metadata.len() > maximum {
        return Err(());
    }
    std::fs::read(path).map_err(|_| ())
}

fn find_bytes(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    haystack
        .windows(needle.len())
        .position(|window| window == needle)
}

const fn request_error(status: u16, code: &'static str, detail: &'static str) -> RequestError {
    RequestError {
        status,
        code,
        detail,
    }
}

fn server_error(code: &str, detail: &str) -> WorkstationServeError {
    WorkstationServeError {
        code: code.to_owned(),
        detail: detail.to_owned(),
    }
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;
    use std::path::{Path, PathBuf};
    use std::sync::atomic::{AtomicU64, Ordering};

    use serde_json::{json, Value};
    use structural_runtime::NativeFrame3dJobStore;

    use super::{find_bytes, route, HttpRequest};

    static NEXT_TEMP: AtomicU64 = AtomicU64::new(0);

    struct TempRoot(PathBuf);

    impl TempRoot {
        fn new() -> Self {
            let sequence = NEXT_TEMP.fetch_add(1, Ordering::Relaxed);
            let path = std::env::temp_dir().join(format!(
                "structural-workstation-route-{}-{sequence}",
                std::process::id()
            ));
            std::fs::create_dir(&path).expect("temporary route root");
            Self(path)
        }
    }

    impl Drop for TempRoot {
        fn drop(&mut self) {
            let _removed = std::fs::remove_dir_all(&self.0);
        }
    }

    fn fixture() -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../../tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json")
    }

    fn request(method: &str, path: &str, origin: Option<&str>, body: Vec<u8>) -> HttpRequest {
        let mut headers = BTreeMap::from([("host".to_owned(), "127.0.0.1:32123".to_owned())]);
        if let Some(origin) = origin {
            headers.insert("origin".to_owned(), origin.to_owned());
        }
        if method == "POST" {
            headers.insert("content-type".to_owned(), "application/json".to_owned());
        }
        HttpRequest {
            method: method.to_owned(),
            path: path.to_owned(),
            headers,
            body,
        }
    }

    #[test]
    fn byte_delimiter_search_is_exact() {
        assert_eq!(find_bytes(b"a\r\n\r\nb", b"\r\n\r\n"), Some(1));
        assert_eq!(find_bytes(b"abc", b"\r\n"), None);
    }

    #[test]
    fn routes_submit_run_and_publish_only_a_succeeded_hash_bound_bundle() {
        let temporary = TempRoot::new();
        let workbench = temporary.0.join("workbench");
        std::fs::create_dir(&workbench).expect("Workbench root");
        std::fs::write(workbench.join("index.html"), "Frame Alpha Workbench")
            .expect("Workbench index");
        let workbench = std::fs::canonicalize(workbench).expect("canonical Workbench root");
        let store = NativeFrame3dJobStore::new(temporary.0.join("jobs"));
        let address = "127.0.0.1:32123".parse().expect("loopback address");
        let origin = "http://127.0.0.1:32123";

        let mut model: Value =
            serde_json::from_slice(&std::fs::read(fixture()).expect("tracked ModelIR fixture"))
                .expect("fixture JSON");
        model["elements"][0]["formulation"] = json!("linear_timoshenko_frame3d");
        let submission = serde_json::to_vec(&json!({
            "schema_version": "structural-native-linear-frame3d-job-submission.v1",
            "job_id": "job_0123456789abcdef0123456789abcdef",
            "load_source": {"kind": "pattern", "id": "LC_AXIAL"},
            "result_id": "result.workbench.LC_AXIAL",
            "report_id": "report.workbench.LC_AXIAL",
            "model_ir_json": serde_json::to_string(&model).expect("embedded ModelIR"),
            "claim_boundary": "browser_submission_to_bounded_loopback_native_job_not_result_design_or_release_authority"
        }))
        .expect("submission JSON");

        let forbidden = route(
            &request(
                "POST",
                "/api/v1/frame3d/jobs",
                Some("http://attacker.invalid"),
                submission.clone(),
            ),
            &store,
            &workbench,
            address,
        );
        assert_eq!(forbidden.status, 403);

        let queued = route(
            &request("POST", "/api/v1/frame3d/jobs", Some(origin), submission),
            &store,
            &workbench,
            address,
        );
        assert_eq!(queued.status, 201);
        assert_eq!(
            serde_json::from_slice::<Value>(&queued.body).expect("queued JSON")["status"],
            "queued"
        );

        let job_path = "/api/v1/frame3d/jobs/job_0123456789abcdef0123456789abcdef";
        let terminal = route(
            &request(
                "POST",
                &format!("{job_path}/run"),
                Some(origin),
                b"{}".to_vec(),
            ),
            &store,
            &workbench,
            address,
        );
        assert_eq!(terminal.status, 200);
        assert_eq!(
            serde_json::from_slice::<Value>(&terminal.body).expect("terminal JSON")["status"],
            "succeeded"
        );

        let result = route(
            &request(
                "GET",
                &format!("{job_path}/bundle/result-ir.json"),
                None,
                Vec::new(),
            ),
            &store,
            &workbench,
            address,
        );
        assert_eq!(result.status, 200);
        assert_eq!(
            serde_json::from_slice::<Value>(&result.body).expect("ResultIR JSON")["authority"]
                ["release_readiness"],
            "not_authoritative"
        );

        let conflict = route(
            &request(
                "POST",
                &format!("{job_path}/run"),
                Some(origin),
                b"{}".to_vec(),
            ),
            &store,
            &workbench,
            address,
        );
        assert_eq!(conflict.status, 409);
    }
}
