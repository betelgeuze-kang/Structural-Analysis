from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_full_pytest_refreshes_clean_runner_after_embedded_host_receipts() -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "python-test-collection.yml"
    ).read_text(encoding="utf-8")
    full_job = workflow.split("  full:", 1)[1]

    code_receipt = full_job.index(
        "python scripts/run_external_code_to_code_technical_receipt.py"
    )
    modal_receipt = full_job.index(
        "python scripts/run_external_modal_buckling_technical_receipt.py"
    )
    clean_runner = full_job.index(
        "python benchmarks/clean-runners/opensees-calculix/run_clean_runner.py"
    )
    first_case_package = full_job.index(
        "python scripts/build_bounded_planar_external_linear_case_package.py"
    )

    assert code_receipt < modal_receipt < clean_runner < first_case_package
    assert "--repo-root ." in full_job[clean_runner:first_case_package]
    assert (
        "--output-dir artifacts/vv/opensees_calculix_clean_runner"
        in full_job[clean_runner:first_case_package]
    )
    assert (
        "--refresh-product-replay-summary"
        in full_job[clean_runner:first_case_package]
    )
