from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "build_engine_v2_cross_platform_determinism_receipt.py"
)
WORKFLOW = REPO_ROOT / ".github/workflows/engine-v2-determinism-ci.yml"
for candidate in (REPO_ROOT / "scripts", REPO_ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location(
    "build_engine_v2_cross_platform_determinism_receipt_goldens",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_engine_v2_cross_platform_golden_hashes_and_written_bytes(
    tmp_path: Path,
) -> None:
    goldens, binary_artifacts = module.compute_engine_v2_cross_platform_goldens(
        tmp_path,
        repo_root=REPO_ROOT,
    )

    assert goldens == module.EXPECTED_GOLDENS
    assert binary_artifacts == module.EXPECTED_BINARY_ARTIFACTS
    assert goldens["bounded_planar_result_hash"].startswith("sha256:")
    assert goldens["bounded_planar_replay_result_hash"].startswith("sha256:")
    assert goldens["bounded_planar_checkpoint_artifact_hash"].startswith("sha256:")
    assert goldens["bounded_planar_engineering_result_hash"].startswith("sha256:")
    assert goldens["bounded_planar_execution_topology_plan_hash"].startswith("sha256:")
    assert goldens["bounded_planar_model_ir_content_hash"].startswith("sha256:")
    assert goldens["bounded_planar_model_ir_adapter_hash"].startswith("sha256:")
    assert goldens["bounded_planar_execution_plan_binding_hash"].startswith("sha256:")
    assert goldens["bounded_planar_settlement_result_hash"].startswith("sha256:")
    assert goldens["bounded_planar_settlement_replay_result_hash"].startswith(
        "sha256:"
    )
    assert goldens[
        "bounded_planar_settlement_checkpoint_artifact_hash"
    ].startswith("sha256:")
    assert goldens[
        "bounded_planar_settlement_engineering_result_hash"
    ].startswith("sha256:")
    assert goldens[
        "bounded_planar_settlement_execution_plan_binding_hash"
    ].startswith("sha256:")
    assert binary_artifacts["scaling/scale_divisors_si.f64le"] == {
        "byte_length": 96,
        "data_hash": (
            "sha256:38ace1f260bbd047b5e21c3b09ba090e7004b0751cbf07ec60a43e344c6b3ff5"
        ),
    }
    assert binary_artifacts["solution/solution_free.f64le"] == {
        "byte_length": 48,
        "data_hash": (
            "sha256:78c19f52f7328f8e639debdb3ea64e9779c3cc7d7c0690bf387009355df4bc2c"
        ),
    }


def test_cross_platform_workflow_owns_receipt_backed_four_way_matrix() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    attributes = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    workflow_header = workflow.split("jobs:", 1)[0]
    attestation_job = workflow.split("  attest-current-main:", 1)[1]

    assert "os: [ubuntu-latest, windows-latest]" in workflow
    assert 'python-version: ["3.10", "3.12"]' in workflow
    assert "fail-fast: false" in workflow
    assert 'GIT_CONFIG_COUNT: "6"' in workflow
    assert "GIT_CONFIG_KEY_0: core.longpaths" in workflow
    assert "GIT_CONFIG_KEY_4: filter.lfs.process" in workflow
    assert 'GIT_CONFIG_VALUE_4: ""' in workflow
    assert "GIT_CONFIG_KEY_5: core.autocrlf" in workflow
    assert (
        "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json text eol=lf"
        in attributes
    )
    assert "examples/public_corotational_member_features.json text eol=lf" in attributes
    assert (
        "examples/bounded_planar_settlement.model-ir.v2.json text eol=lf"
        in attributes
    )
    assert (
        'ENGINE_V2_SOURCE_SHA: "${{ github.event.pull_request.head.sha || github.sha }}"'
        in workflow
    )
    assert workflow.count("ref: ${{ env.ENGINE_V2_SOURCE_SHA }}") == 2
    assert workflow.count('--source-commit "${{ env.ENGINE_V2_SOURCE_SHA }}"') == 2
    assert "build_engine_v2_cross_platform_determinism_receipt.py" in workflow
    assert "verify_bounded_planar_wheel_smoke.py --json" in workflow
    assert workflow.count('scripts/verify_bounded_planar_wheel_smoke.py') == 3
    assert "tests/test_engine_v2_cross_platform_goldens.py" in workflow
    assert "tests/test_build_engine_v2_cross_platform_determinism_receipt.py" in (
        workflow
    )
    assert "src/structural_analysis/api/**" in workflow
    assert workflow.count('src/structural_analysis/adapters/**') == 2
    assert "examples/public_corotational_member_features.json" in workflow
    assert "examples/bounded_planar_frame_alpha.model-ir.v2.json" in workflow
    assert workflow.count(
        'examples/bounded_planar_settlement.model-ir.v2.json'
    ) == 2
    assert workflow.count('tests/test_bounded_planar_wheel_smoke.py') == 2
    assert workflow.count('- "pyproject.toml"') == 2
    assert "actions/upload-artifact@v7" in workflow
    assert "actions/download-artifact@v7" in workflow
    assert "id-token: write" in workflow
    assert "attestations: write" in workflow
    assert "artifact-metadata: write" in workflow
    assert "id-token: write" not in workflow_header
    assert "attestations: write" not in workflow_header
    assert "artifact-metadata: write" not in workflow_header
    assert "attest-current-main:" in workflow
    assert "needs: matrix-receipt" in workflow
    assert "id-token: write" in attestation_job
    assert "attestations: write" in attestation_job
    assert "artifact-metadata: write" in attestation_job
    assert "uses: actions/attest@v4" in workflow
    assert "github.event_name != 'pull_request'" in workflow
    assert "steps.attest.outputs.bundle-path" in workflow
    assert "gh attestation verify" in workflow
    assert "--signer-workflow" in workflow
    assert '--source-digest "$ENGINE_V2_SOURCE_SHA"' in workflow
    assert "--source-ref refs/heads/main" in workflow
    assert "--deny-self-hosted-runners" in workflow
    assert "engine-v2-determinism-four-way-attested-" in workflow
    assert "merge-multiple: true" in workflow
    assert "--matrix-job-result" in workflow
    assert "needs.cross-platform-goldens.result" in workflow
    assert "Passing this lane is not" in workflow
    assert "CPU/HIP parity, independent V&V" in workflow
