//! Existing serial runtime versus bounded CPU batch throughput; not a single-solve speed claim.

use std::collections::BTreeSet;
use std::path::PathBuf;
use std::process::ExitCode;
use std::time::Instant;

use serde_json::{json, Value};
use structural_contracts::model_ir::{parse_model_ir_v2, ModelIrV2Document};
use structural_contracts::report_ir::sha256_bytes_identity;
use structural_runtime::{
    analyze_linear_frame3d_batch, LinearFrame3dBatchLoadSource, LinearFrame3dBatchRequest,
    LinearFrame3dLoadSelection, LinearFrame3dResultIrV1, Runtime, MAX_FRAME3D_BATCH_REQUESTS,
    MAX_FRAME3D_BATCH_WORKERS,
};

struct Options {
    models: Vec<PathBuf>,
    load_source: LinearFrame3dBatchLoadSource,
    jobs: usize,
    repetitions: usize,
    workers: Vec<usize>,
}

fn parse_options() -> Result<Options, String> {
    let mut arguments = std::env::args().skip(1);
    let mut models = Vec::new();
    let mut load_source = None;
    let mut jobs = 256;
    let mut repetitions = 3;
    let mut workers = vec![1, 2, 4, 8, 12];
    while let Some(flag) = arguments.next() {
        let value = arguments
            .next()
            .ok_or_else(|| format!("missing value for {flag}"))?;
        match flag.as_str() {
            "--model" => models.push(PathBuf::from(value)),
            "--load-pattern" if load_source.is_none() => {
                load_source = Some(LinearFrame3dBatchLoadSource::Pattern(value));
            }
            "--load-combination" if load_source.is_none() => {
                load_source = Some(LinearFrame3dBatchLoadSource::Combination(value));
            }
            "--jobs" => jobs = value.parse().map_err(|_| "invalid --jobs")?,
            "--repetitions" => {
                repetitions = value.parse().map_err(|_| "invalid --repetitions")?;
            }
            "--workers" => {
                workers = value
                    .split(',')
                    .map(|item| item.parse().map_err(|_| "invalid --workers".to_owned()))
                    .collect::<Result<Vec<_>, _>>()?;
            }
            _ => return Err(format!("unknown or duplicate load-selection flag {flag}")),
        }
    }
    if models.is_empty()
        || !(1..=MAX_FRAME3D_BATCH_REQUESTS).contains(&jobs)
        || !(1..=20).contains(&repetitions)
        || workers.is_empty()
        || workers
            .iter()
            .any(|count| !(1..=MAX_FRAME3D_BATCH_WORKERS).contains(count))
        || !workers.contains(&1)
    {
        return Err(
            "require --model, jobs1..1024, repetitions1..20, unique workers1..12 including1"
                .to_owned(),
        );
    }
    let mut unique = workers.clone();
    unique.sort_unstable();
    unique.dedup();
    if unique.len() != workers.len() {
        return Err("duplicate --workers entry".to_owned());
    }
    Ok(Options {
        models,
        load_source: load_source.ok_or("require exactly one load pattern or combination")?,
        jobs,
        repetitions,
        workers,
    })
}

fn serial_before(
    requests: &[LinearFrame3dBatchRequest],
) -> Result<Vec<LinearFrame3dResultIrV1>, String> {
    requests
        .iter()
        .map(|request| {
            let selection = match &request.load_source {
                LinearFrame3dBatchLoadSource::Pattern(id) => {
                    LinearFrame3dLoadSelection::Pattern(id)
                }
                LinearFrame3dBatchLoadSource::Combination(id) => {
                    LinearFrame3dLoadSelection::Combination(id)
                }
            };
            Runtime::new()
                .and_then(|runtime| {
                    runtime.analyze_linear_frame3d_load_case_result_ir(
                        &request.document,
                        selection,
                        &request.result_id,
                    )
                })
                .map_err(|error| error.to_string())
        })
        .collect()
}

fn canonical(results: &[LinearFrame3dResultIrV1]) -> Result<Vec<String>, String> {
    results
        .iter()
        .map(|result| result.canonical_json().map_err(|error| error.to_string()))
        .collect()
}

fn median(samples: &[f64]) -> f64 {
    let mut sorted = samples.to_vec();
    sorted.sort_by(f64::total_cmp);
    (sorted[(sorted.len() - 1) / 2] + sorted[sorted.len() / 2]) / 2.0
}

fn run(options: &Options) -> Result<Value, String> {
    let documents = options
        .models
        .iter()
        .map(|path| {
            let bytes = std::fs::read(path).map_err(|error| error.to_string())?;
            parse_model_ir_v2(&bytes).map_err(|error| error.to_string())
        })
        .collect::<Result<Vec<ModelIrV2Document>, String>>()?;
    let requests = (0..options.jobs)
        .map(|index| LinearFrame3dBatchRequest {
            document: documents[index % documents.len()].clone(),
            load_source: options.load_source.clone(),
            result_id: format!("frame3d-batch-bench.{index}"),
        })
        .collect::<Vec<_>>();
    let distinct_executed_models = requests
        .iter()
        .map(|request| request.document.content_hash())
        .collect::<BTreeSet<_>>();
    // Parse/load and one serial warmup are outside the timed regions for every comparison.
    let expected = canonical(&serial_before(&requests)?)?;
    let mut serial_seconds = Vec::with_capacity(options.repetitions);
    for _ in 0..options.repetitions {
        let begin = Instant::now();
        let results = serial_before(&requests)?;
        serial_seconds.push(begin.elapsed().as_secs_f64());
        if canonical(&results)? != expected {
            return Err("serial result drift from warmup".to_owned());
        }
    }
    let mut levels = Vec::with_capacity(options.workers.len());
    for workers in &options.workers {
        let mut seconds = Vec::with_capacity(options.repetitions);
        for _ in 0..options.repetitions {
            let begin = Instant::now();
            let batch = analyze_linear_frame3d_batch(&requests, *workers)
                .map_err(|error| error.to_string())?;
            seconds.push(begin.elapsed().as_secs_f64());
            let results = batch
                .outcomes
                .into_iter()
                .collect::<Result<Vec<_>, _>>()
                .map_err(|error| error.to_string())?;
            if canonical(&results)? != expected {
                return Err(format!(
                    "result order or canonical bytes drift with {workers} workers"
                ));
            }
        }
        let middle = median(&seconds);
        if middle <= 0.0 {
            return Err("timer resolution insufficient for this batch".to_owned());
        }
        levels.push(json!({
            "requested_workers": workers,
            "workers_used": (*workers).min(options.jobs),
            "seconds": seconds,
            "median_seconds": middle,
            "jobs_per_second": f64::from(u32::try_from(options.jobs).expect("bounded jobs")) / middle,
            "speedup_vs_serial_before": median(&serial_seconds) / middle,
            "all_case_canonical_results_equal": true,
        }));
    }
    let one = levels
        .iter()
        .find(|level| level["requested_workers"] == 1)
        .and_then(|level| level["median_seconds"].as_f64())
        .ok_or("missing one-worker baseline")?;
    for level in &mut levels {
        level["speedup_vs_batch_one_worker"] =
            json!(one / level["median_seconds"].as_f64().ok_or("missing timing")?);
    }
    Ok(json!({
        "schema_version": "structural-native-frame3d-cpu-batch-benchmark.v1",
        "success": true,
        "input_model_count": documents.len(),
        "input_model_content_hashes": documents.iter().map(ModelIrV2Document::content_hash).collect::<Vec<_>>(),
        "jobs_per_sample": options.jobs,
        "repetitions": options.repetitions,
        "available_parallelism": std::thread::available_parallelism().map_or(1, std::num::NonZeroUsize::get),
        "timed_scope": "already-parsed ModelIR through existing validation/native compile/solve/recovery/ResultIR; batch thread startup and runtime-internal serialization included; file IO, wire parsing, final-output serialization and comparison canonical JSON/equality checks excluded",
        "serial_before": {"runtime_initialization": "per request", "seconds": serial_seconds, "median_seconds": median(&serial_seconds)},
        "batch_after_runtime_initialization": "per worker; each request still compiles and destroys an independent native model",
        "levels": levels,
        "ordered_case_result_digest": sha256_bytes_identity(expected.join("\n").as_bytes()),
        "claim_boundary": "bounded_existing_frame3d_batch_throughput_only_not_single_model_solver_speedup_or_physical_release_qualification",
        "distinct_validation_cases_not_repeated_request_count": distinct_executed_models.len(),
        "distinct_executed_model_content_hashes": distinct_executed_models,
    }))
}

fn main() -> ExitCode {
    match parse_options().and_then(|options| run(&options)) {
        Ok(result) => match serde_json::to_string_pretty(&result) {
            Ok(text) => {
                println!("{text}");
                ExitCode::SUCCESS
            }
            Err(error) => {
                eprintln!("{error}");
                ExitCode::FAILURE
            }
        },
        Err(error) => {
            eprintln!("{error}");
            ExitCode::FAILURE
        }
    }
}
