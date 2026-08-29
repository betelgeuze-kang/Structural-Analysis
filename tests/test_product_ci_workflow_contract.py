from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def _read(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def test_canonical_ci_owns_structural_core_lane() -> None:
    workflow = _read("ci.yml")

    assert "name: CI" in workflow
    assert "runs-on: ubuntu-24.04" in workflow
    assert "timeout-minutes: 180" in workflow
    assert "fetch-depth: 0" in workflow
    assert "scripts/check_product_ci_boundaries.py" in workflow
    assert "scripts/run_product_ci_lane.py --lane core" in workflow
    assert "scripts/verify_quality_gate.py --mode pr" in workflow


def test_pr_quality_gate_pins_reproducible_numerical_toolchain() -> None:
    workflow = _read("ci.yml")

    install = workflow.split("- name: Install Python package", 1)[1].split(
        "- name: Install Node dependencies",
        1,
    )[0]
    assert "python -m pip install numpy==1.26.4 scipy==1.12.0" in install

    quality_gate = workflow.split("- name: PR quality gate", 1)[1].split(
        "- name: Upload quality-gate log",
        1,
    )[0]
    assert "OPENBLAS_CORETYPE: Haswell" in quality_gate
    assert 'OPENBLAS_NUM_THREADS: "1"' in quality_gate
    assert 'OMP_NUM_THREADS: "1"' in quality_gate


def test_workflow_contract_runs_raw_ancestry_regressions_from_full_checkout() -> None:
    workflow = _read("workflow-contract-ci.yml")

    assert "fetch-depth: 0" in workflow
    assert "persist-credentials: false" in workflow
    assert "git fetch" not in workflow
    assert "git cat-file -p HEAD" in workflow
    assert 'git cat-file -e "${parent}^{commit}"' in workflow
    assert 'git cat-file -p "$parent"' in workflow
    assert 'git cat-file -e "${nested_parent}^{commit}"' in workflow
    assert (
        "tests/test_external_vv_clean_runner_contract.py::"
        "test_git_ancestry_fallback_walks_raw_objects_across_shallow_boundary"
        in workflow
    )
    assert (
        "tests/test_external_vv_clean_runner_contract.py::"
        "test_git_ancestry_probe_preserves_git_errors" in workflow
    )


def test_frontend_required_lane_cannot_disappear_by_path_filter() -> None:
    canonical = _read("ci.yml")
    frontend = _read("frontend-web-ci.yml")

    assert canonical.count('- "src/structural_analysis/**"') == 2
    assert '- "src/**"' not in canonical

    trigger = frontend.split("permissions:", 1)[0]
    assert "paths:" not in trigger
    assert "pull_request:" in trigger
    assert "merge_group:" in trigger
    assert "frontend-required:" in frontend
    aggregator = frontend.split("  frontend-required:", 1)[1]
    assert "name: frontend-required" in aggregator
    assert "if: always()" in aggregator
    assert "needs: [frontend]" in aggregator


def test_frontend_lane_runs_for_every_pr_merge_and_self_push() -> None:
    workflow = _read("frontend-web-ci.yml")

    trigger = workflow.split("permissions:", 1)[0]
    assert "paths:" not in trigger
    assert "pull_request:" in trigger
    assert "merge_group:" in trigger
    assert 'branches: ["main", "codex/**", "web/**", "feat/**", "ci/**"]' in trigger


def test_frontend_dependency_audit_is_zero_vulnerability_fail_closed() -> None:
    workflow = _read("frontend-web-ci.yml")

    audit_step = workflow.split(
        "- name: Clean-copy install and dependency audit before repository code",
        1,
    )[1].split("- name: Install repository dependencies", 1)[0]
    assert audit_step.index(
        '"$TRUSTED_NPM_CLI" ci --ignore-scripts --engine-strict'
    ) < (audit_step.index('"$TRUSTED_NPM_CLI" audit --json --audit-level=info'))
    assert audit_step.index('"$TRUSTED_NPM_CLI" audit --json --audit-level=info') < (
        audit_step.index('"$TRUSTED_NPM_CLI" audit signatures --json')
    )
    assert '"$TRUSTED_NPM_CLI" audit --json --audit-level=info' in audit_step
    assert "--registry=https://registry.npmjs.org/" in audit_step
    assert "--strict-ssl=true" in audit_step
    assert not re.search(r"audit[^\n]*\|\|", audit_step)
    assert "warning" not in audit_step.lower()
    assert 'ln -s /dev/null "$audit_config/user.npmrc"' in audit_step
    assert 'ln -s /dev/null "$audit_config/global.npmrc"' in audit_step
    assert "NPM_CONFIG_USERCONFIG=$audit_config/user.npmrc" in audit_step
    assert "NPM_CONFIG_GLOBALCONFIG=$audit_config/global.npmrc" in audit_step
    assert "env -i" in audit_step
    assert '"$TRUSTED_NPM_CLI" config get proxy' in audit_step
    assert '"$TRUSTED_NPM_CLI" config get https-proxy' in audit_step
    assert '"$TRUSTED_NPM_CLI" config get cafile' in audit_step
    install_step = workflow.split(
        "- name: Install repository dependencies without lifecycle scripts", 1
    )[1].split("- name: Build evidence bundle", 1)[0]
    assert '"$TRUSTED_NPM_CLI" ci --ignore-scripts --engine-strict' in install_step
    assert workflow.index("dependency audit before repository code") < workflow.index(
        "Install repository dependencies without lifecycle scripts"
    )
    assert "permissions:\n  contents: read" in workflow
    assert "runs-on: ubuntu-24.04" in workflow
    assert "persist-credentials: false" in workflow
    assert "actions/checkout@v" not in workflow
    assert "actions/setup-node@v" not in workflow
    setup_node = workflow.split("- name: Bootstrap official Node", 1)[1].split(
        "- name: Clean-copy install", 1
    )[0]
    assert "cache: npm" not in setup_node
    assert "SHASUMS256.txt" in setup_node
    assert (
        "89af8424dd53e560b1933f87ba650d8bf57c83ca5a04600eefb31f416aabbae7" in setup_node
    )

    repository_steps = workflow.split(
        "- name: Build evidence bundle (read-only)", 1
    )[1].split("  frontend-required:", 1)[0]
    assert '"$TRUSTED_NPM_CLI" run ' not in repository_steps
    assert "npm run " not in repository_steps
    assert "npx " not in repository_steps
    assert "node_modules/.bin" not in repository_steps
    assert '"$GITHUB_WORKSPACE/node_modules/typescript/bin/tsc"' in repository_steps
    assert '"$GITHUB_WORKSPACE/node_modules/vite/bin/vite.js"' in repository_steps
    assert '"$GITHUB_WORKSPACE/node_modules/playwright/cli.js"' in repository_steps
    assert (
        '"$GITHUB_WORKSPACE/scripts/verify-workbench-v2-e2e.mjs"'
        in repository_steps
    )
    assert repository_steps.count("/usr/bin/env -i") >= 7


def test_pages_build_and_deploy_use_strict_unprivileged_handoff() -> None:
    workflow = _read("deploy-pages.yml")
    header, jobs = workflow.split("jobs:\n", maxsplit=1)
    build_job, deploy_job = jobs.split("\n  deploy:\n", maxsplit=1)

    assert "pages: write" not in header
    assert "id-token: write" not in header
    assert "    permissions:\n      contents: read\n" in build_job
    assert "pages: write" not in build_job
    assert "id-token: write" not in build_job
    assert "persist-credentials: false" in build_job
    assert "GITHUB_TOKEN" not in build_job
    assert "github.token" not in build_job
    assert "id: pages-handoff" in build_job
    assert "outputs:\n      artifact-id:" in build_job
    assert (
        "pages-${{ github.run_id }}-${{ github.run_attempt }}-${{ github.sha }}"
        in build_job
    )
    assert "      pages: write\n" in deploy_job
    assert "      id-token: write\n" in deploy_job
    assert "      actions: read\n" in deploy_job
    assert "actions/checkout@" not in deploy_job
    assert "actions/setup-node@" not in deploy_job
    assert "npm " not in deploy_job
    assert "Validate exact Pages artifact handoff" in deploy_job
    assert "PAGES_ARTIFACT_ID" in deploy_job
    assert "/actions/artifacts/{artifact_id}" in deploy_job
    assert "class NoRedirect" in deploy_job
    assert 'str(workflow_run["id"]) == os.environ["GITHUB_RUN_ID"]' in deploy_job
    assert 'workflow_run.get("head_sha") == os.environ["GITHUB_SHA"]' in deploy_job
    assert "artifact_name: ${{ needs.build.outputs.artifact-name }}" in deploy_job
    assert "runs-on: ubuntu-24.04" in deploy_job
    setup_node = build_job.split("- name: Bootstrap official Node", 1)[1].split(
        "- name: Install dependencies", 1
    )[0]
    assert "cache: npm" not in setup_node


def test_node_workflows_pin_lts_toolchain_actions_and_install_contract() -> None:
    names = {
        "ai-contract-verify.yml",
        "ci.yml",
        "current-support-bundle.yml",
        "deploy-pages.yml",
        "frontend-web-ci.yml",
        "native-frame-alpha-clean-install.yml",
        "native-pr-fast.yml",
        "nightly-full-quality.yml",
        "nightly-heavy-solver.yml",
        "release-publish.yml",
        "runtime-input-viewer-ci.yml",
        "viewer-browser-ci.yml",
    }
    for name in names:
        workflow = _read(name)
        if name in {
            "current-support-bundle.yml",
            "deploy-pages.yml",
            "frontend-web-ci.yml",
        }:
            assert "node-v24.20.0-linux-x64.tar.xz" in workflow, name
            assert "SHASUMS256.txt" in workflow, name
            assert "actions/setup-node@" not in workflow, name
        else:
            assert 'node-version: "24.20.0"' in workflow, name
        assert "20.19.0" not in workflow, name
        assert re.search(
            r"^permissions:\n(?:  .+\n)*  contents: (?:read|write)$",
            workflow,
            re.MULTILINE,
        ), name
        assert "runs-on: ubuntu-latest" not in workflow, name
        for line in workflow.splitlines():
            if "uses: actions/" in line:
                reference = line.split("@", maxsplit=1)[1].split()[0]
                assert re.fullmatch(r"[0-9a-f]{40}", reference), (name, line)
        checkout_blocks = workflow.split("uses: actions/checkout@")[1:]
        assert checkout_blocks, name
        assert all(
            "persist-credentials: false" in block[:500] for block in checkout_blocks
        ), name
        if "npm ci" in workflow:
            assert workflow.count("npm ci") <= workflow.count("--ignore-scripts"), name
            assert workflow.count("npm ci") <= workflow.count("--engine-strict"), name
            assert workflow.count("npm ci") <= workflow.count(
                "--registry=https://registry.npmjs.org/"
            ), name
        for line in workflow.splitlines():
            if "npx " in line:
                assert "npx --no-install " in line, (name, line)


def test_legacy_evidence_has_independent_hosted_lane() -> None:
    workflow = _read("legacy-evidence-ci.yml")

    assert "name: Legacy Evidence CI" in workflow
    assert "runs-on: ubuntu-24.04" in workflow
    assert "runs-on: ubuntu-latest" not in workflow
    assert "timeout-minutes: 240" in workflow
    assert "legacy-evidence-shards:" in workflow
    assert "name: legacy-evidence-shard-${{ matrix.shard }}" in workflow
    assert "fail-fast: false" in workflow
    assert "legacy-evidence-complete:" in workflow
    assert "needs: [legacy-evidence, legacy-evidence-shards]" in workflow
    assert "LEGACY_PREFLIGHT_RESULT: ${{ needs.legacy-evidence.result }}" in workflow
    assert (
        "LEGACY_SHARDS_RESULT: ${{ needs.legacy-evidence-shards.result }}" in workflow
    )
    assert "fetch-depth: 0" in workflow
    assert "python -m pip install numpy==1.26.4 scipy==1.12.0" in workflow
    assert "OPENBLAS_CORETYPE: Haswell" in workflow
    assert 'OPENBLAS_NUM_THREADS: "1"' in workflow
    assert 'OMP_NUM_THREADS: "1"' in workflow
    assert "scripts/run_product_ci_lane.py" in workflow
    assert "--lane legacy_evidence" in workflow
    assert "tests/test_build_product_readiness_snapshot.py" in workflow
    assert "tests/test_validate_external_vv_operator_attestation.py" in workflow
    assert "tests/test_promote_external_vv_level2.py" in workflow
    assert "run_clean_runner.py" in workflow
    assert "--refresh-product-replay-summary" in workflow
    assert "scripts/build_bounded_planar_external_linear_case_package.py" in workflow
    assert "scripts/build_bounded_planar_external_negative_case_package.py" in workflow
    assert "tests/test_build_bounded_planar_external_linear_case_package.py" in workflow
    assert (
        "tests/test_build_bounded_planar_external_negative_case_package.py" in workflow
    )
    assert "tests/test_ingest_bounded_planar_external_linear_results.py" in workflow
    assert "tests/test_ingest_bounded_planar_external_negative_results.py" in workflow
    assert "tests/test_build_bounded_planar_external_vv_matrix.py" in workflow

    test_modules = (
        "tests/test_build_ci_streak_intake_packet.py",
        "tests/test_build_product_readiness_snapshot.py",
        "tests/test_check_repo_hygiene.py",
        "tests/test_external_code_to_code_technical_receipt.py",
        "tests/test_external_modal_buckling_technical_receipt.py",
        "tests/test_external_vv_clean_runner_contract.py",
        "tests/test_validate_external_vv_operator_attestation.py",
        "tests/test_promote_external_vv_level2.py",
        "tests/test_build_bounded_planar_external_linear_case_package.py",
        "tests/test_build_bounded_planar_external_negative_case_package.py",
        "tests/test_build_bounded_planar_external_scaling_case_package.py",
        "tests/test_build_bounded_planar_external_modal_buckling_case_package.py",
        "tests/test_build_bounded_planar_external_nonlinear_material_recovery_case_package.py",
        "tests/test_ingest_bounded_planar_external_linear_results.py",
        "tests/test_ingest_bounded_planar_external_negative_results.py",
        "tests/test_ingest_bounded_planar_external_scaling_results.py",
        "tests/test_ingest_bounded_planar_external_modal_buckling_results.py",
        "tests/test_ingest_bounded_planar_external_nonlinear_material_recovery_results.py",
        "tests/test_build_bounded_planar_current_source_supplemental_attestation.py",
        "tests/test_build_bounded_planar_external_vv_matrix.py",
        "tests/test_source_boundary_ci_contract.py",
    )
    assert all(workflow.count(module) == 1 for module in test_modules)


def test_molecular_code_is_checked_only_as_quarantine() -> None:
    workflow = _read("science-quarantine-ci.yml")

    assert "name: Molecular Quarantine CI" in workflow
    assert "runs-on: ubuntu-24.04" in workflow
    assert "runs-on: ubuntu-latest" not in workflow
    assert "--lane molecular_quarantine" in workflow
    assert "--collect-only" in workflow
    assert "without product promotion" in workflow


def test_quarantine_control_plane_path_does_not_match_product_tokens() -> None:
    assert not (WORKFLOWS / "molecular-quarantine-ci.yml").exists()
    assert (WORKFLOWS / "science-quarantine-ci.yml").exists()


def test_pr_quality_gate_no_longer_lints_all_product_domains_together() -> None:
    gate = (ROOT / "scripts" / "verify_quality_gate.py").read_text(encoding="utf-8")

    assert '"scripts/check_product_ci_boundaries.py"' in gate
    assert '_lane_command("core")' in gate
    assert '[_python(), "-m", "ruff", "check", "."]' not in gate
    assert '_lane_command("legacy_evidence")' in gate
    assert '_lane_command("molecular_quarantine")' in gate


def test_runner_policy_allowlists_all_deterministic_product_lanes() -> None:
    policy = (ROOT / "scripts" / "check_github_actions_runner_policy.py").read_text(
        encoding="utf-8"
    )

    assert '".github/workflows/ci.yml"' in policy
    assert '".github/workflows/engine-v2-contract-ci.yml"' in policy
    assert '".github/workflows/legacy-evidence-ci.yml"' in policy
    assert '".github/workflows/medium-scale-current-source.yml"' in policy
    assert '".github/workflows/science-quarantine-ci.yml"' in policy
    assert '".github/workflows/molecular-quarantine-ci.yml"' not in policy


def test_engine_v2_contract_lane_runs_the_complete_hosted_suite() -> None:
    workflow = _read("engine-v2-contract-ci.yml")

    assert "name: Engine v2 Contract CI" in workflow
    assert "runs-on: ubuntu-latest" in workflow
    assert "python -m pip install numpy==1.26.4 scipy==1.12.0" in workflow
    assert "OPENBLAS_CORETYPE: Haswell" in workflow
    assert 'OPENBLAS_NUM_THREADS: "1"' in workflow
    assert 'OMP_NUM_THREADS: "1"' in workflow
    assert 'MKL_NUM_THREADS: "1"' in workflow
    assert 'PYTHONHASHSEED: "0"' in workflow
    assert "python -m pytest -q" in workflow
    assert "tests/test_engine_v2*.py" in workflow
    assert "tests/test_model_ir_v2_contract.py" in workflow
    assert '- "src/structural_analysis/engine_v2/**"' in workflow
    assert '- "src/structural_analysis/engine_v2_backends/**"' in workflow
    assert (
        '- "src/structural_analysis/schemas/cpu_fgmres_checkpoint_v1.schema.json"'
        in workflow
    )
    assert (
        '- "src/structural_analysis/schemas/numerical_result_ir_v1.schema.json"'
        in workflow
    )
    assert (
        '- "src/structural_analysis/schemas/diagnostic_ir_v1.schema.json"' in workflow
    )
    assert (
        '- "src/structural_analysis/schemas/engineering_result_ir_v1.schema.json"'
        in workflow
    )
    assert (
        '- "src/structural_analysis/schemas/linear_static_recovery_operator_v1.schema.json"'
        in workflow
    )
    assert "scripts/run_engine_v2_hip_primitive_parity.py --check" in workflow
    assert "scripts/run_engine_v2_hip_current_tangent_operator.py" in workflow
    assert "scripts/run_engine_v2_hip_sparse_lu_apply.py" in workflow
    assert "scripts/run_engine_v2_hip_fgmres_recurrence.py --check" in workflow
    assert "--compile-only --check" in workflow
    assert "hip_fgmres_multiblock_compile_receipt_v1.schema.json" in workflow
    assert "hip_fgmres_device_receipt_v1.schema.json" in workflow
    assert "run_engine_v2_hip_fgmres_device_receipt.py" in workflow
    assert "engine_v2_hip_fgmres_gfx1030_device_receipt.json" in workflow
    assert "Check committed gfx1030 device receipt offline" in workflow
    assert "engine_v2_hip_fgmres_multiblock_compile_receipt.json" in workflow
    assert "hip_fgmres_stage4_status_v1.schema.json" in workflow
    assert "build_engine_v2_hip_fgmres_stage4_status.py --check" in workflow
    assert "engine_v2_hip_fgmres_stage4_status.json" in workflow
    assert "hip_current_tangent_operator_compile_receipt_v1.schema.json" in (workflow)
    assert "hip_current_tangent_operator_parity_v1.schema.json" in workflow
    assert "engine_v2_current_tangent_operator.hip.cpp" in workflow
    assert "engine_v2_hip_current_tangent_operator_compile_receipt.json" in workflow
    assert "Check committed HIP current-tangent compile receipt offline" in (workflow)
    assert "build_g1_mgt_hip_current_tangent_host_parser_receipt.py" in workflow
    assert "--check-source-only" in workflow
    assert "g1_mgt_hip_current_tangent_host_parser_receipt_v1.schema.json" in workflow
    assert "g1_mgt_hip_current_tangent_host_parser_receipt.json" in workflow
    assert (
        "Check actual-MGT HIP current-tangent parser receipt sources offline"
        in workflow
    )
    assert "run_g1_mgt_hip_current_tangent_hardware_parity.py" in workflow
    assert (
        "g1_mgt_hip_current_tangent_hardware_parity_receipt_v1.schema.json" in workflow
    )
    assert "g1_mgt_hip_current_tangent_hardware_parity_receipt.json" in workflow
    assert "g1_mgt_hip_current_tangent_action.f64le" in workflow
    assert (
        "Check actual-MGT HIP current-tangent hardware receipt sources offline"
        in workflow
    )
    assert "hip_sparse_lu_apply_compile_receipt_v1.schema.json" in workflow
    assert "hip_sparse_lu_apply_parity_v1.schema.json" in workflow
    assert "engine_v2_sparse_lu_apply.hip.cpp" in workflow
    assert "engine_v2_hip_sparse_lu_apply_compile_receipt.json" in workflow
    assert "Check committed HIP sparse-LU compile receipt offline" in workflow
    assert '- "tests/test_engine_v2*.py"' in workflow
    assert '- "tests/test_model_ir_v2_contract.py"' in workflow
    assert "self-hosted" not in workflow
    assert "does not exercise" in workflow
    assert "hipcc" not in workflow
