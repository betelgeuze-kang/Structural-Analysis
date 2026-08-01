from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _workflow() -> str:
    return (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def test_ci_materializes_validates_and_uploads_current_head_snapshot() -> None:
    workflow = _workflow()

    assert "Build current-HEAD readiness snapshot" in workflow
    assert "python scripts/build_product_readiness_snapshot.py" in workflow
    assert "current-head-product-readiness-snapshot.json" in workflow
    assert 'payload.get("source_commit_sha")' in workflow
    assert 'os.environ["GITHUB_SHA"]' in workflow
    assert "name: current-head-product-readiness-${{ github.sha }}" in workflow
    assert (
        "path: ${{ runner.temp }}/current-head-product-readiness-snapshot.json"
        in workflow
    )


def test_ci_materializes_runtime_evidence_before_snapshot_and_quality_gate() -> None:
    workflow = _workflow()
    workflow_environment = workflow.split("concurrency:", 1)[0]
    materialize = workflow.index(
        "- name: Materialize exact current-source test evidence"
    )
    snapshot = workflow.index("- name: Build current-HEAD readiness snapshot")
    quality_gate = workflow.index("- name: PR quality gate")

    assert materialize < snapshot < quality_gate
    assert "OPENBLAS_CORETYPE: Haswell" in workflow_environment
    assert 'OPENBLAS_NUM_THREADS: "1"' in workflow_environment
    assert 'OMP_NUM_THREADS: "1"' in workflow_environment
    for command in (
        "run_external_code_to_code_technical_receipt.py",
        "run_external_modal_buckling_technical_receipt.py",
        "build_bounded_planar_external_linear_case_package.py",
        "build_bounded_planar_external_negative_case_package.py",
        "build_bounded_planar_external_scaling_case_package.py",
        "build_bounded_planar_external_modal_buckling_case_package.py",
        "build_bounded_planar_external_nonlinear_material_recovery_case_package.py",
        "build_bounded_planar_external_vv_matrix.py",
        "build_internal_license_due_diligence.py --fail-blocked",
    ):
        assert command in workflow[materialize:snapshot]


def test_current_head_snapshot_preserves_blocked_release_state() -> None:
    workflow = _workflow()
    step = workflow.split("- name: Build current-HEAD readiness snapshot", 1)[1]
    step = step.split("- name: Upload current-HEAD readiness snapshot", 1)[0]

    assert "--fail-blocked" not in step
    assert "--check" not in step
    assert "--no-write" not in step
