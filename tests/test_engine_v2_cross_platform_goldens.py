from __future__ import annotations

import importlib.util
from pathlib import Path
import platform
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

    require_reference_numerical = platform.system() == "Linux" and sys.version_info[
        :2
    ] == (3, 12)
    assert (
        module.golden_hash_mismatches(
            goldens,
            require_reference_numerical=require_reference_numerical,
        )
        == ()
    )
    assert binary_artifacts == module.EXPECTED_BINARY_ARTIFACTS
    assert goldens["bounded_planar_result_hash"].startswith("sha256:")
    assert goldens["bounded_planar_semantic_hash"].startswith("sha256:")
    assert goldens["bounded_planar_replay_result_hash"].startswith("sha256:")
    assert goldens["bounded_planar_checkpoint_artifact_hash"].startswith("sha256:")
    assert goldens["bounded_planar_engineering_result_hash"].startswith("sha256:")
    assert goldens["bounded_planar_execution_topology_plan_hash"].startswith("sha256:")
    assert goldens["bounded_planar_model_ir_content_hash"].startswith("sha256:")
    assert goldens["bounded_planar_model_ir_adapter_hash"].startswith("sha256:")
    assert goldens["bounded_planar_execution_plan_binding_hash"].startswith("sha256:")
    assert goldens["bounded_planar_settlement_result_hash"].startswith("sha256:")
    assert goldens["bounded_planar_settlement_semantic_hash"].startswith("sha256:")
    assert goldens["bounded_planar_settlement_replay_result_hash"].startswith("sha256:")
    assert goldens["bounded_planar_settlement_checkpoint_artifact_hash"].startswith(
        "sha256:"
    )
    assert goldens["bounded_planar_settlement_engineering_result_hash"].startswith(
        "sha256:"
    )
    assert goldens["bounded_planar_settlement_execution_plan_binding_hash"].startswith(
        "sha256:"
    )
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
    assert workflow.count("python -m pip install numpy==1.26.4 scipy==1.12.0") == 2
    assert "OPENBLAS_CORETYPE: Haswell" in workflow
    assert 'OPENBLAS_NUM_THREADS: "1"' in workflow
    assert 'OMP_NUM_THREADS: "1"' in workflow
    assert 'MKL_NUM_THREADS: "1"' in workflow
    assert 'PYTHONHASHSEED: "0"' in workflow
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
        "examples/bounded_planar_settlement.model-ir.v2.json text eol=lf" in attributes
    )
    assert 'ENGINE_V2_SOURCE_SHA: "${{ github.sha }}"' in workflow
    assert "github.event.pull_request.head.sha || github.sha" not in workflow
    assert workflow.count("ref: ${{ env.ENGINE_V2_SOURCE_SHA }}") == 2
    assert workflow.count('--source-commit "${{ env.ENGINE_V2_SOURCE_SHA }}"') == 3
    assert "build_engine_v2_cross_platform_determinism_receipt.py" in workflow
    assert "build_bounded_planar_wheel_smoke_manifest.py" in workflow
    assert "verify_bounded_planar_wheel_smoke.py --json" in workflow
    assert workflow.count("scripts/verify_bounded_planar_wheel_smoke.py") == 3
    assert '--write ".ci/engine-v2-wheel-smoke/receipt.json"' in workflow
    assert '--wheel-out-dir ".ci/engine-v2-wheel-smoke/wheel"' in workflow
    assert '--os-label "${{ matrix.os }}"' in workflow
    assert '--python-version "${{ matrix.python-version }}"' in workflow
    assert (
        "name: bounded-planar-wheel-smoke-${{ matrix.os }}-python-"
        "${{ matrix.python-version }}" in workflow
    )
    assert "pattern: bounded-planar-wheel-smoke-*" in workflow
    assert "path: .ci/engine-v2-wheel-smoke/coordinates" in workflow
    assert "merge-multiple: false" in workflow
    wheel_upload = workflow.split(
        "      - name: Upload exact-source wheel smoke receipt and wheel",
        1,
    )[1].split("      - name: Replay reference-exact", 1)[0]
    assert "if-no-files-found: error" in wheel_upload
    assert "include-hidden-files: true" in wheel_upload
    wheel_download = workflow.split(
        "      - name: Download exact-source wheel smoke receipts and wheels",
        1,
    )[1].split("      - name: Aggregate four-way", 1)[0]
    assert "continue-on-error" not in wheel_download
    assert "merge-multiple: false" in wheel_download
    matrix_upload = workflow.split(
        "      - name: Upload four-way determinism receipt",
        1,
    )[1].split("      - name: Upload four-way wheel smoke manifest", 1)[0]
    assert "ENGINE_V2_MATRIX_RECEIPT" in matrix_upload
    assert "engine-v2-wheel-smoke" not in matrix_upload
    assert "include-hidden-files: true" in matrix_upload
    assert "bounded-planar-wheel-smoke-four-way-" in workflow
    assert "ENGINE_V2_WHEEL_MANIFEST" in workflow
    assert "tests/test_engine_v2_cross_platform_goldens.py" in workflow
    assert "tests/test_build_engine_v2_cross_platform_determinism_receipt.py" in (
        workflow
    )
    assert "src/structural_analysis/api/**" in workflow
    assert workflow.count("src/structural_analysis/adapters/**") == 2
    assert "examples/public_corotational_member_features.json" in workflow
    assert "examples/bounded_planar_frame_alpha.model-ir.v2.json" in workflow
    assert workflow.count("examples/bounded_planar_settlement.model-ir.v2.json") == 2
    assert workflow.count("tests/test_bounded_planar_wheel_smoke.py") == 2
    assert (
        workflow.count("tests/test_build_bounded_planar_wheel_smoke_manifest.py") == 2
    )
    assert workflow.count("ci/bounded-planar-wheel-smoke.constraints.txt") == 2
    assert workflow.count('- "pyproject.toml"') == 2
    assert (
        workflow.count(
            "actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803"
        )
        == 2
    )
    assert (
        workflow.count(
            "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1"
        )
        == 2
    )
    assert (
        workflow.count(
            "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
        )
        == 6
    )
    assert (
        workflow.count(
            "actions/download-artifact@37930b1c2abaa49bbe596cd826c3c89aef350131"
        )
        == 4
    )
    assert "Reference-coordinate exact hashes" in workflow
    assert "separately pinned P0 canonical workflow" in workflow
    assert "two byte-identical builds in one workflow execution" in workflow
    assert "Future-run and cross-platform wheel byte equality" in workflow
    assert workflow.count("retention-days: 90") >= 3
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
    assert (
        workflow.count("actions/attest@508db95dd578ae2727ebd6217d5ba78e4fbda05d")
        == 2
    )
    for mutable_ref in (
        "actions/checkout@v",
        "actions/setup-python@v",
        "actions/upload-artifact@v",
        "actions/download-artifact@v",
        "actions/attest@v",
    ):
        assert mutable_ref not in workflow
    assert "github.event_name != 'pull_request'" in workflow
    assert "steps.attest.outputs.bundle-path" in workflow
    assert "steps.attest-wheel-manifest.outputs.bundle-path" in workflow
    assert "gh attestation verify" in workflow
    assert "--signer-workflow" in workflow
    assert 'ENGINE_V2_WORKFLOW_SHA: "${{ github.workflow_sha }}"' in workflow
    assert 'ENGINE_V2_WORKFLOW_REF: "${{ github.workflow_ref }}"' in workflow
    assert 'test "$ENGINE_V2_WORKFLOW_SHA" = "$ENGINE_V2_SOURCE_SHA"' in workflow
    assert "engine-v2-determinism-ci.yml@refs/heads/main" in workflow
    assert workflow.count('--signer-digest "$ENGINE_V2_WORKFLOW_SHA"') == 2
    assert '--source-digest "$ENGINE_V2_SOURCE_SHA"' in workflow
    assert "--source-ref refs/heads/main" in workflow
    assert "--deny-self-hosted-runners" in workflow
    assert 'gh api "repos/$GITHUB_REPOSITORY/git/ref/heads/main"' in workflow
    assert 'test "$current_main_sha" = "$ENGINE_V2_SOURCE_SHA"' in workflow
    assert workflow.index("Verify current-main workflow execution identity") < (
        workflow.index("id: attest")
    )
    assert "engine-v2-determinism-four-way-attested-" in workflow
    assert "bounded-planar-wheel-smoke-four-way-attested-" in workflow
    assert "merge-multiple: true" in workflow
    assert "--matrix-job-result" in workflow
    assert "needs.cross-platform-goldens.result" in workflow
    assert "Passing this lane is not" in workflow
    assert "CPU/HIP parity, independent V&V" in workflow
