//! Bounded parallel composition of independent, unchanged Frame Alpha analyses.

use std::fmt;
use std::thread;

use structural_contracts::model_ir::ModelIrV2Document;

use crate::{LinearFrame3dLoadSelection, LinearFrame3dResultIrV1, Runtime, RuntimeError};

/// Maximum independent workers; this does not change any single-model numerical limit.
pub const MAX_FRAME3D_BATCH_WORKERS: usize = 12;
/// Maximum requests retained in one ordered batch result.
pub const MAX_FRAME3D_BATCH_REQUESTS: usize = 1024;

/// Per-invocation worker admission for the single-threaded bounded native kernel.
///
/// This is an observed process CPU-capacity check, not a cross-process CPU quota.
/// It never changes affinity, environment variables or a foreign thread runtime.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Frame3dBatchCpuBudget {
    total_workers: usize,
    observed_available_parallelism: usize,
}

impl Frame3dBatchCpuBudget {
    /// Admit an explicit worker budget against the current process CPU capacity.
    ///
    /// # Errors
    /// Returns an error if capacity is unavailable or the budget is zero/too large.
    pub fn for_current_process(total_workers: usize) -> Result<Self, Frame3dBatchError> {
        let available = thread::available_parallelism()
            .map_err(|_| Frame3dBatchError::CpuCapacityUnavailable)?
            .get();
        Self::for_observed_capacity(total_workers, available)
    }

    fn for_observed_capacity(
        total_workers: usize,
        available: usize,
    ) -> Result<Self, Frame3dBatchError> {
        if total_workers == 0 || total_workers > available {
            return Err(Frame3dBatchError::InvalidCpuBudget {
                requested: total_workers,
                available,
            });
        }
        Ok(Self {
            total_workers,
            observed_available_parallelism: available,
        })
    }

    #[must_use]
    pub const fn total_workers(self) -> usize {
        self.total_workers
    }

    #[must_use]
    pub const fn observed_available_parallelism(self) -> usize {
        self.observed_available_parallelism
    }

    /// Run the unchanged batch computation after enforcing this invocation's budget.
    ///
    /// # Errors
    /// Rejects excess workers before native initialization, plus ordinary batch failures.
    pub fn analyze(
        self,
        requests: &[LinearFrame3dBatchRequest],
        workers: usize,
    ) -> Result<LinearFrame3dBatchResult, Frame3dBatchError> {
        if !(1..=MAX_FRAME3D_BATCH_WORKERS).contains(&workers) {
            return Err(Frame3dBatchError::InvalidWorkerCount {
                requested: workers,
                maximum: MAX_FRAME3D_BATCH_WORKERS,
            });
        }
        if workers > self.total_workers {
            return Err(Frame3dBatchError::WorkerBudgetExceeded {
                requested: workers,
                budget: self.total_workers,
            });
        }
        analyze_linear_frame3d_batch(requests, workers)
    }
}

/// Owned load selection, so a request never transports a native model handle.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum LinearFrame3dBatchLoadSource {
    Pattern(String),
    Combination(String),
}

impl LinearFrame3dBatchLoadSource {
    fn selection(&self) -> LinearFrame3dLoadSelection<'_> {
        match self {
            Self::Pattern(id) => LinearFrame3dLoadSelection::Pattern(id),
            Self::Combination(id) => LinearFrame3dLoadSelection::Combination(id),
        }
    }
}

/// A previously wire-validated document and the same selections as the serial runtime.
#[derive(Clone, Debug)]
pub struct LinearFrame3dBatchRequest {
    pub document: ModelIrV2Document,
    pub load_source: LinearFrame3dBatchLoadSource,
    pub result_id: String,
}

/// Input-ordered outcomes. Timing and worker metadata never enter an individual `ResultIR`.
#[derive(Clone, Debug, PartialEq)]
pub struct LinearFrame3dBatchResult {
    pub requested_workers: usize,
    pub workers_used: usize,
    pub outcomes: Vec<Result<LinearFrame3dResultIrV1, RuntimeError>>,
}

/// Batch admission or thread-management failure, separate from each model's runtime error.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Frame3dBatchError {
    CpuCapacityUnavailable,
    InvalidCpuBudget { requested: usize, available: usize },
    WorkerBudgetExceeded { requested: usize, budget: usize },
    InvalidWorkerCount { requested: usize, maximum: usize },
    InvalidRequestCount { requested: usize, maximum: usize },
    WorkerSpawnFailed { worker_index: usize, detail: String },
    WorkerPanicked { worker_index: usize },
    ResultCountMismatch { expected: usize, actual: usize },
    ResultIndexMismatch { expected: usize, actual: usize },
}

impl fmt::Display for Frame3dBatchError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::CpuCapacityUnavailable => {
                write!(
                    formatter,
                    "Frame3D batch process CPU capacity is unavailable"
                )
            }
            Self::InvalidCpuBudget {
                requested,
                available,
            } => write!(
                formatter,
                "Frame3D batch CPU budget must be in 1..={available}, got {requested}"
            ),
            Self::WorkerBudgetExceeded { requested, budget } => write!(
                formatter,
                "Frame3D batch workers {requested} exceed the explicit CPU budget {budget}"
            ),
            Self::InvalidWorkerCount { requested, maximum } => write!(
                formatter,
                "Frame3D batch workers must be in 1..={maximum}, got {requested}"
            ),
            Self::InvalidRequestCount { requested, maximum } => write!(
                formatter,
                "Frame3D batch request count must be in 1..={maximum}, got {requested}"
            ),
            Self::WorkerSpawnFailed {
                worker_index,
                detail,
            } => {
                write!(
                    formatter,
                    "Frame3D batch worker {worker_index} spawn failed: {detail}"
                )
            }
            Self::WorkerPanicked { worker_index } => {
                write!(
                    formatter,
                    "Frame3D batch worker {worker_index} panicked; no retry"
                )
            }
            Self::ResultCountMismatch { expected, actual } => write!(
                formatter,
                "Frame3D batch expected {expected} outcomes, received {actual}"
            ),
            Self::ResultIndexMismatch { expected, actual } => write!(
                formatter,
                "Frame3D batch expected result index {expected}, received {actual}"
            ),
        }
    }
}

impl std::error::Error for Frame3dBatchError {}

type IndexedOutcome = (usize, Result<LinearFrame3dResultIrV1, RuntimeError>);

fn run_worker(
    requests: &[LinearFrame3dBatchRequest],
    worker_index: usize,
    workers_used: usize,
) -> Vec<IndexedOutcome> {
    // Runtime/API ownership stays on this thread. Each existing analysis call also owns and
    // drops its native model locally; no Send/Sync relaxation or shared solve buffer is needed.
    let runtime = Runtime::new();
    (worker_index..requests.len())
        .step_by(workers_used)
        .map(|index| {
            let request = &requests[index];
            let outcome = match &runtime {
                Ok(runtime) => runtime.analyze_linear_frame3d_load_case_result_ir(
                    &request.document,
                    request.load_source.selection(),
                    &request.result_id,
                ),
                Err(error) => Err(error.clone()),
            };
            (index, outcome)
        })
        .collect()
}

/// Analyze independent bounded Frame Alpha models with a fixed standard-library worker pool.
///
/// Every case uses the existing serial validation, compilation, solve, recovery and promotion
/// gates. Case errors remain in their input positions and do not cause retries. Workers reuse
/// only their local API table, never a native model or mutable numerical state across cases.
/// This original composition primitive does not reserve CPU capacity; use
/// [`Frame3dBatchCpuBudget::analyze`] for explicit per-invocation CPU admission.
///
/// # Errors
///
/// Rejects empty/oversized batches, worker counts outside `1..=12`, thread creation failures,
/// worker panics and missing/duplicate result indices. Per-model failures remain in `outcomes`.
pub fn analyze_linear_frame3d_batch(
    requests: &[LinearFrame3dBatchRequest],
    workers: usize,
) -> Result<LinearFrame3dBatchResult, Frame3dBatchError> {
    if !(1..=MAX_FRAME3D_BATCH_WORKERS).contains(&workers) {
        return Err(Frame3dBatchError::InvalidWorkerCount {
            requested: workers,
            maximum: MAX_FRAME3D_BATCH_WORKERS,
        });
    }
    if !(1..=MAX_FRAME3D_BATCH_REQUESTS).contains(&requests.len()) {
        return Err(Frame3dBatchError::InvalidRequestCount {
            requested: requests.len(),
            maximum: MAX_FRAME3D_BATCH_REQUESTS,
        });
    }
    let workers_used = workers.min(requests.len());
    let mut indexed = thread::scope(|scope| {
        let mut handles = Vec::with_capacity(workers_used);
        let mut spawn_error = None;
        for worker_index in 0..workers_used {
            match thread::Builder::new()
                .name(format!("frame3d-batch-{worker_index}"))
                .spawn_scoped(scope, move || {
                    run_worker(requests, worker_index, workers_used)
                }) {
                Ok(handle) => handles.push((worker_index, handle)),
                Err(error) => {
                    spawn_error = Some(Frame3dBatchError::WorkerSpawnFailed {
                        worker_index,
                        detail: error.to_string(),
                    });
                    break;
                }
            }
        }
        let mut outcomes = Vec::with_capacity(requests.len());
        let mut panic_error = None;
        // Explicitly join every started worker even after another worker fails.
        for (worker_index, handle) in handles {
            match handle.join() {
                Ok(mut results) => outcomes.append(&mut results),
                Err(_) => {
                    panic_error.get_or_insert(Frame3dBatchError::WorkerPanicked { worker_index });
                }
            }
        }
        if let Some(error) = spawn_error.or(panic_error) {
            Err(error)
        } else {
            Ok(outcomes)
        }
    })?;
    if indexed.len() != requests.len() {
        return Err(Frame3dBatchError::ResultCountMismatch {
            expected: requests.len(),
            actual: indexed.len(),
        });
    }
    indexed.sort_unstable_by_key(|(index, _)| *index);
    let mut outcomes = Vec::with_capacity(indexed.len());
    for (expected, (actual, outcome)) in indexed.into_iter().enumerate() {
        if actual != expected {
            return Err(Frame3dBatchError::ResultIndexMismatch { expected, actual });
        }
        outcomes.push(outcome);
    }
    Ok(LinearFrame3dBatchResult {
        requested_workers: workers,
        workers_used,
        outcomes,
    })
}

#[cfg(test)]
mod cpu_budget_tests {
    use super::{Frame3dBatchCpuBudget, Frame3dBatchError};

    #[test]
    fn zero_and_excess_observed_budgets_fail_before_batch_execution() {
        for requested in [0, 5] {
            assert_eq!(
                Frame3dBatchCpuBudget::for_observed_capacity(requested, 4),
                Err(Frame3dBatchError::InvalidCpuBudget {
                    requested,
                    available: 4,
                })
            );
        }
    }

    #[test]
    fn excess_workers_fail_before_request_or_native_processing() {
        let budget = Frame3dBatchCpuBudget::for_observed_capacity(2, 4).unwrap();
        assert_eq!(budget.total_workers(), 2);
        assert_eq!(budget.observed_available_parallelism(), 4);
        assert_eq!(
            budget.analyze(&[], 3),
            Err(Frame3dBatchError::WorkerBudgetExceeded {
                requested: 3,
                budget: 2
            })
        );
    }
}
