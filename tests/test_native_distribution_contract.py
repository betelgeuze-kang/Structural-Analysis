import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "scripts" / "build_native_distribution.sh"
RUN = ROOT / "scripts" / "run_native_distribution_e2e.sh"
RUN_ROCM = ROOT / "scripts" / "run_native_rocm_distribution_e2e.sh"
CHECK = ROOT / "scripts" / "check_native_distribution_receipt.py"
LIB = ROOT / "native" / "crates" / "structural-distribution" / "src" / "lib.rs"
FFI_BUILD = ROOT / "native" / "crates" / "structural-ffi" / "build.rs"
ROOTFS_RUN = ROOT / "scripts" / "run_native_rootfs_isolation_e2e.sh"


def run_checker(tmp_path: Path, receipt: dict, manifest: dict) -> subprocess.CompletedProcess[str]:
    receipt_path = tmp_path / "receipt.json"
    manifest_path = tmp_path / "structural-distribution.json"
    installed_path = tmp_path / "installed-backend.json"
    installed = {
        "schema_version": "structural-native-installed-backend.v1",
        "backend_profile": "cpu_only",
        "device_name": "deterministic-cpu-fp64",
        "cpu_backend": 1,
        "execution_backend": 1,
        "device_id": -1,
        "cpu_backend_parity": True,
        "repeat_bitwise": True,
        "fp64": True,
        "deterministic": True,
        "fallback_count": 0,
        "operator_device_resident": False,
        "h2d_bytes": 0,
        "d2h_bytes": 0,
        "synchronization_count": 0,
        "kernel_launch_count": 0,
        "device_buffer_bytes": 0,
    }
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    installed_path.write_text(json.dumps(installed), encoding="utf-8")
    receipt["bundle_manifest_sha256"] = "sha256:" + hashlib.sha256(
        manifest_path.read_bytes()
    ).hexdigest()
    receipt["installed_backend_receipt_sha256"] = "sha256:" + hashlib.sha256(
        installed_path.read_bytes()
    ).hexdigest()
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    return subprocess.run(
        [
            "python3",
            str(CHECK),
            "--receipt",
            str(receipt_path),
            "--manifest",
            str(manifest_path),
            "--installed-backend-receipt",
            str(installed_path),
            "--require-backend",
            "cpu_only",
            "--require-authority",
            "--json",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def valid_contract() -> tuple[dict, dict]:
    source = "sha256:" + "a" * 64
    manifest = {
        "backend_profile": "cpu_only",
        "release_id": "cpu-0.1.0",
        "source_sha256": source,
        "execution_authority": "cpu_build_candidate",
    }
    receipt = {
        "schema_version": "structural-native-distribution-e2e.v1",
        "backend_profile": "cpu_only",
        "linkage": "shared",
        "release_id": "cpu-0.1.0",
        "source_sha256": source,
        "bundle_manifest_sha256": "sha256:" + "0" * 64,
        "installed_backend_receipt_sha256": "sha256:" + "d" * 64,
        "c2_receipt_sha256": None,
        "approved_device_runner": False,
        "single_product_abi": True,
        "python_lookup_count": 0,
        "node_lookup_count": 0,
        "install_passed": True,
        "update_passed": True,
        "rollback_passed": True,
        "package_consumer_passed": True,
        "workbench_restart_passed": True,
        "workbench_direct_parity_passed": True,
        "result_ir_sha256": "sha256:" + "b" * 64,
        "report_pdf_sha256": "sha256:" + "c" * 64,
        "fallback_count": 0,
        "authority": "hosted_cpu_c5",
    }
    return receipt, manifest


def valid_v2_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v2",
            "mgt_workbench_restart_passed": True,
            "mgt_workbench_direct_parity_passed": True,
            "mgt_source_sha256": "sha256:" + "1" * 64,
            "mgt_import_health_sha256": "sha256:" + "2" * 64,
            "mgt_result_ir_sha256": "sha256:" + "3" * 64,
            "mgt_report_pdf_sha256": "sha256:" + "4" * 64,
        }
    )
    return receipt, manifest


def valid_v3_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v2_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v3",
            "workbench_operator_surface_passed": True,
            "workbench_review_decision": "review",
            "workbench_review_sha256": "sha256:" + "5" * 64,
            "workbench_export_sha256": "sha256:" + "6" * 64,
            "mgt_workbench_operator_surface_passed": True,
            "mgt_workbench_review_decision": "review",
            "mgt_workbench_review_sha256": "sha256:" + "7" * 64,
            "mgt_workbench_export_sha256": "sha256:" + "8" * 64,
        }
    )
    return receipt, manifest


def valid_v4_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v3_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v4",
            "workbench_catalog_surface_passed": True,
            "workbench_catalog_sha256": "sha256:" + "9" * 64,
            "workbench_evidence_surface_passed": True,
            "workbench_evidence_sha256": "sha256:" + "a" * 64,
        }
    )
    return receipt, manifest


def valid_v5_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v4_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v5",
            "evidence_builder_check_passed": True,
            "evidence_builder_check_sha256": "sha256:" + "b" * 64,
            "evidence_builder_build_passed": True,
            "evidence_builder_build_sha256": "sha256:" + "c" * 64,
            "evidence_builder_manifest_sha256": "sha256:" + "d" * 64,
        }
    )
    return receipt, manifest


def valid_v6_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v5_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v6",
            "catalog_builder_check_passed": True,
            "catalog_builder_check_sha256": "sha256:" + "e" * 64,
            "catalog_builder_build_passed": True,
            "catalog_builder_build_sha256": "sha256:" + "f" * 64,
            "catalog_builder_output_sha256": "sha256:" + "0" * 64,
        }
    )
    return receipt, manifest


def test_distribution_receipt_accepts_exact_hosted_cpu_contract(tmp_path: Path):
    receipt, manifest = valid_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_accepts_mgt_workbench_v2_contract(tmp_path: Path):
    receipt, manifest = valid_v2_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_accepts_operator_surface_v3_contract(tmp_path: Path):
    receipt, manifest = valid_v3_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_promoting_v3_review_decision(tmp_path: Path):
    receipt, manifest = valid_v3_contract()
    receipt["workbench_review_decision"] = "pass"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any("workbench_review_decision" in error for error in validation["errors"])


def test_distribution_receipt_accepts_catalog_and_evidence_v4_contract(tmp_path: Path):
    receipt, manifest = valid_v4_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_missing_v4_catalog_authority(tmp_path: Path):
    receipt, manifest = valid_v4_contract()
    receipt["workbench_catalog_surface_passed"] = False
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any("workbench_catalog_surface_passed" in error for error in validation["errors"])


def test_distribution_receipt_accepts_native_evidence_builder_v5_contract(tmp_path: Path):
    receipt, manifest = valid_v5_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_missing_v5_builder_authority(tmp_path: Path):
    receipt, manifest = valid_v5_contract()
    receipt["evidence_builder_build_passed"] = False
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any("evidence_builder_build_passed" in error for error in validation["errors"])


def test_distribution_receipt_accepts_native_catalog_builder_v6_contract(tmp_path: Path):
    receipt, manifest = valid_v6_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_missing_v6_catalog_authority(tmp_path: Path):
    receipt, manifest = valid_v6_contract()
    receipt["catalog_builder_check_passed"] = False
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any("catalog_builder_check_passed" in error for error in validation["errors"])


def test_distribution_receipt_rejects_runtime_and_manifest_drift(tmp_path: Path):
    receipt, manifest = valid_contract()
    receipt["node_lookup_count"] = 1
    receipt["single_product_abi"] = False
    manifest["release_id"] = "different"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert validation["valid"] is False
    assert any("node_lookup_count" in error for error in validation["errors"])
    assert any("single_product_abi" in error for error in validation["errors"])
    assert any("release" in error for error in validation["errors"])


def test_distribution_implementation_has_durable_and_fail_closed_boundaries():
    source = LIB.read_text(encoding="utf-8")
    for token in (
        "structural-distribution.v1",
        "structural-install-transaction.v1",
        "lock_exclusive",
        "sync_all",
        "release_id_immutable",
        "bundle_payload_hash_mismatch",
        "recovery_required",
        "AfterPrepared",
        "AfterMaterialized",
        "AfterActivated",
    ):
        assert token in source


def test_build_and_e2e_scripts_enforce_split_native_packages():
    build = BUILD.read_text(encoding="utf-8")
    catalog_wrapper = (ROOT / "scripts/build_native_benchmark_catalog.sh").read_text(
        encoding="utf-8"
    )
    evidence_wrapper = (
        ROOT / "scripts/build_native_workbench_evidence_bundle.sh"
    ).read_text(encoding="utf-8")
    e2e = RUN.read_text(encoding="utf-8")
    rocm_e2e = RUN_ROCM.read_text(encoding="utf-8")
    rootfs_e2e = ROOTFS_RUN.read_text(encoding="utf-8")
    ffi = FFI_BUILD.read_text(encoding="utf-8")
    assert 'STRUCTURAL_ENABLE_HIP="$enable_hip"' in build
    assert "ROCm distribution currently requires shared linkage" in build
    assert "rocm_runtime_rpath" in build
    assert "libamdhip64.so" in build
    assert '"-DCMAKE_INSTALL_RPATH=$install_rpath"' in build
    assert "STRUCTURAL_NATIVE_PREFIX" in build
    assert "cargo build --manifest-path native/Cargo.toml --release --locked" in build
    assert "-p structural-catalog" in build
    assert 'structural-catalog "$payload/bin/structural-catalog"' in build
    assert "-p structural-evidence" in build
    assert 'structural-evidence "$payload/bin/structural-evidence"' in build
    assert '"$1" == "--check"' in evidence_wrapper
    assert "structural-evidence -- check --root" in evidence_wrapper
    assert 'if [[ "$#" -ne 0 ]]' in evidence_wrapper
    assert "structural-evidence -- build" in evidence_wrapper
    assert '"$1" == "--check"' in catalog_wrapper
    assert "structural-catalog -- check --root" in catalog_wrapper
    assert 'if [[ "$#" -ne 0 ]]' in catalog_wrapper
    assert "structural-catalog -- build" in catalog_wrapper
    assert "PATH=\"$empty_path\"" in e2e
    assert "diff -r \"$restarted\" \"$direct\"" in e2e
    assert "workflow-mgt" in e2e
    assert "diff -r \"$mgt_restarted\" \"$mgt_direct\"" in e2e
    assert "mgt_workbench_direct_parity_passed" in e2e
    assert "exercise_operator_surface" in e2e
    assert "workbench_operator_surface_passed" in e2e
    assert "structural-native-distribution-e2e.v6" in e2e
    assert "structural-catalog" in e2e
    assert "catalog_builder_build_passed" in e2e
    assert "structural-evidence" in e2e
    assert "evidence_builder_build_passed" in e2e
    assert "structural-native-benchmark-catalog-view.v1" in e2e
    assert "structural-native-evidence-bundle-view.v1" in e2e
    assert "workbench_catalog_surface_passed" in e2e
    assert "workbench_evidence_surface_passed" in e2e
    assert "update --bundle" in e2e
    assert "rollback --root" in e2e
    assert "single_product_abi" in e2e
    assert "python_lookup_count" in e2e
    assert "STRUCTURAL_NATIVE_PREFIX" in ffi
    assert "rustc-link-lib=dylib=structural_c_abi_v1" in ffi
    assert "native-hip-approved" in rocm_e2e
    assert "ROCm product library has an unresolved runtime dependency" in rocm_e2e
    assert "structural_native_backend_package_consumer\" hip" in rocm_e2e
    assert "workflow-mgt" in rocm_e2e
    assert "mgt_workbench_direct_parity_passed" in rocm_e2e
    assert "exercise_operator_surface" in rocm_e2e
    assert "workbench_operator_surface_passed" in rocm_e2e
    assert "structural-native-distribution-e2e.v6" in rocm_e2e
    assert "structural-catalog" in rocm_e2e
    assert "catalog_builder_build_passed" in rocm_e2e
    assert "structural-evidence" in rocm_e2e
    assert "evidence_builder_build_passed" in rocm_e2e
    assert "workbench_catalog_surface_passed" in rocm_e2e
    assert "workbench_evidence_surface_passed" in rocm_e2e
    assert '"approved_device_runner\\\":true' in rocm_e2e
    assert "inspect --workspace /mnt/modelir-workbench" in rootfs_e2e
    assert "review-show --workspace /mnt/modelir-workbench" in rootfs_e2e
    assert "export --workspace /mnt/modelir-workbench" in rootfs_e2e
    assert "inspect --workspace /mnt/mgt-workbench" in rootfs_e2e
    assert "--workbench-inspect-before-review" in rootfs_e2e
    assert "--workbench-catalog" in rootfs_e2e
    assert "--workbench-evidence" in rootfs_e2e
    assert "structural-workbench catalog" in rootfs_e2e
    assert "structural-workbench evidence" in rootfs_e2e
    assert "IFS= read -r catalog_line" in rootfs_e2e
    assert "IFS= read -r evidence_line" in rootfs_e2e
    assert "grep -Fq" not in rootfs_e2e
    assert "runtime-receipt-verify" in rootfs_e2e
