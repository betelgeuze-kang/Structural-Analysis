from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _extract_job(workflow: str, job_name: str) -> str:
    """Return one top-level GitHub Actions job without relying on job order."""

    lines = workflow.splitlines()
    marker = f"  {job_name}:"
    try:
        start = lines.index(marker)
    except ValueError as exc:  # pragma: no cover
        message = f"workflow job not found: {job_name}"
        raise AssertionError(message) from exc

    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.startswith("  ") and not line.startswith("    ") and line.endswith(":"):
            end = index
            break

    return "\n".join(lines[start:end])


def test_full_pytest_refreshes_clean_runner_after_embedded_host_receipts() -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "python-test-collection.yml"
    ).read_text(encoding="utf-8")
    shard_job = _extract_job(workflow, "full_shards")
    aggregate_job = _extract_job(workflow, "full")

    code_receipt = shard_job.index(
        "python scripts/run_external_code_to_code_technical_receipt.py"
    )
    modal_receipt = shard_job.index(
        "python scripts/run_external_modal_buckling_technical_receipt.py"
    )
    clean_runner = shard_job.index(
        "python benchmarks/clean-runners/opensees-calculix/run_clean_runner.py"
    )
    first_case_package = shard_job.index(
        "python scripts/build_bounded_planar_external_linear_case_package.py"
    )

    assert code_receipt < modal_receipt < clean_runner < first_case_package
    assert "--repo-root ." in shard_job[clean_runner:first_case_package]
    assert (
        "--output-dir artifacts/vv/opensees_calculix_clean_runner"
        in shard_job[clean_runner:first_case_package]
    )
    assert (
        "--refresh-product-replay-summary"
        in shard_job[clean_runner:first_case_package]
    )

    assert "needs: full_shards" in aggregate_job
    assert "FULL_SHARDS_RESULT: ${{ needs.full_shards.result }}" in aggregate_job
    assert "run_external_code_to_code_technical_receipt.py" not in aggregate_job
