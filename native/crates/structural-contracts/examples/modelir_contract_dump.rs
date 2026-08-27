use std::io::{self, Write as _};
use std::path::Path;

use serde::Serialize;
use structural_contracts::model_ir::parse_model_ir_v2;

#[derive(Serialize)]
struct FixtureIdentity<'a> {
    path: &'a str,
    schema_valid: bool,
    model_id: &'a str,
    capability_profile: &'a str,
    canonical_json: &'a str,
    canonical_length: usize,
    content_hash: &'a str,
    semantic_hash: &'a str,
    provenance_hash: &'a str,
    claim_boundary: &'static str,
}

fn main() {
    let paths = std::env::args().skip(1).collect::<Vec<_>>();
    if paths.is_empty() {
        eprintln!("usage: modelir_contract_dump <model-ir-v2.json> [...]");
        std::process::exit(2);
    }

    let mut output = io::BufWriter::new(io::stdout().lock());
    for path in &paths {
        let bytes = std::fs::read(Path::new(path)).unwrap_or_else(|_| {
            eprintln!("model_ir_fixture_read_failed:{path}");
            std::process::exit(2);
        });
        let document = parse_model_ir_v2(&bytes).unwrap_or_else(|error| {
            let serialized = serde_json::to_string(&error)
                .unwrap_or_else(|_| "{\"code\":\"serialization_failed\"}".to_owned());
            eprintln!("{serialized}");
            std::process::exit(3);
        });
        let identity = FixtureIdentity {
            path,
            schema_valid: true,
            model_id: document.model_id(),
            capability_profile: document.capability_profile(),
            canonical_json: document.canonical_json(),
            canonical_length: document.canonical_bytes().len(),
            content_hash: document.content_hash(),
            semantic_hash: document.semantic_hash(),
            provenance_hash: document.provenance_hash(),
            claim_boundary: "rust_wire_identity_not_cpp_semantics_or_solver_readiness",
        };
        if serde_json::to_writer(&mut output, &identity).is_err()
            || output.write_all(b"\n").is_err()
        {
            eprintln!("model_ir_fixture_output_failed");
            std::process::exit(4);
        }
    }
}
