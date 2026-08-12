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


def test_distribution_receipt_accepts_exact_hosted_cpu_contract(tmp_path: Path):
    receipt, manifest = valid_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


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
    e2e = RUN.read_text(encoding="utf-8")
    rocm_e2e = RUN_ROCM.read_text(encoding="utf-8")
    ffi = FFI_BUILD.read_text(encoding="utf-8")
    assert 'STRUCTURAL_ENABLE_HIP="$enable_hip"' in build
    assert "ROCm distribution currently requires shared linkage" in build
    assert "STRUCTURAL_NATIVE_PREFIX" in build
    assert "cargo build --manifest-path native/Cargo.toml --release --locked" in build
    assert "PATH=\"$empty_path\"" in e2e
    assert "diff -r \"$restarted\" \"$direct\"" in e2e
    assert "update --bundle" in e2e
    assert "rollback --root" in e2e
    assert "single_product_abi" in e2e
    assert "python_lookup_count" in e2e
    assert "STRUCTURAL_NATIVE_PREFIX" in ffi
    assert "rustc-link-lib=dylib=structural_c_abi_v1" in ffi
    assert "native-hip-approved" in rocm_e2e
    assert "structural_native_backend_package_consumer\" hip" in rocm_e2e
    assert '"approved_device_runner\\\":true' in rocm_e2e
