from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/run_planar_verification_corpus.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "run_planar_verification_corpus_status_test",
        RUNNER,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runner = _load_runner()


def test_blocked_internal_execution_is_not_reported_as_numerical_nonconvergence() -> None:
    execution, numerical, reason = runner._classify_execution(
        "not_converged",
        {
            "status": "blocked",
            "unsupported_features": [
                {
                    "reason_code": "solver_execution_failed",
                    "detail": (
                        "corotational_general_solver_blocked@/solver: "
                        "terminal_reason=sparse_condition_diagnostic_scope_exceeded."
                    ),
                }
            ],
        },
    )

    assert execution == "blocked"
    assert numerical == "not_applicable"
    assert reason == "sparse_condition_diagnostic_scope_exceeded"


def test_completed_nonconvergence_remains_distinct() -> None:
    assert runner._classify_execution("not_converged", {"status": "completed"}) == (
        "completed",
        "not_converged",
        None,
    )


def test_required_convergence_error_preserves_failure_classes() -> None:
    error = runner._required_convergence_error(
        [
            {
                "case_id": "L2",
                "execution_status": "blocked",
                "numerical_status": "not_applicable",
            },
            {
                "case_id": "M5",
                "execution_status": "completed",
                "numerical_status": "not_converged",
            },
        ]
    )

    assert error == "corpus_cases_blocked:L2;corpus_cases_not_converged:M5"
