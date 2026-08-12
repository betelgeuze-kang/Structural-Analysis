#!/usr/bin/env python3
"""Validate bounded R3 CPU product slices and their fail-closed claim boundaries."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

import check_structural_runtime_ffi_r2 as r2


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = r2.DEFAULT_INVENTORY

EXPECTED_R3 = {
    "family": "track_point_load",
    "capability_gate": "C1",
    "cpp_target": "structural_solver_cpu",
    "abi_version": "0x00010002",
    "api_entry": "sa_get_api_v1",
    "api_slot": "track_point_load_solve",
    "legacy_exports_preserved": True,
    "fallback_count": 0,
    "c1_profile": {
        "node_count": 9,
        "point_position_m": 5.0,
        "support_types": ["pinned", "fixed"],
        "theories": ["euler", "timoshenko"],
        "absolute_tolerance": 1.0e-15,
    },
    "product_goldens": {
        "native/tests/fixtures/solver_cpu/track_point_load_fixed_euler_python_c1.json": (
            "30412b6fe9dc1cfbe5f86336a9d89b551d69538330dd07e7322ac655920eb85e"
        ),
        "native/tests/fixtures/solver_cpu/track_point_load_fixed_timoshenko_python_c1.json": (
            "5baecde7cdc15f75433a312f0fae5565ec742544d09422808649dd1fb6b25337"
        ),
        "native/tests/fixtures/solver_cpu/track_point_load_pinned_timoshenko_python_c1.json": (
            "5151e7d13fb5e8f3843d62d16303b7eed864653b165a952330bed9d92915c185"
        ),
        "native/tests/fixtures/solver_cpu/track_point_load_python_c1.json": (
            "268ad1318cc90042ec598ebdc9ec1e15534bc8e5153c0efeccbc5faa43fad282"
        ),
    },
    "owners": {
        "cpp_cpu_kernel": "native/cpp/src/solver_cpu/track_point_load.cpp",
        "c_abi": "native/cpp/include/structural/abi_v1.h",
        "rust_safe_wrapper": "native/crates/structural-ffi/src/lib.rs",
    },
    "verification": {
        "cpp_unit": "native/cpp/tests/solver_cpu/track_point_load_test.cpp",
        "c_abi_contract": "native/cpp/tests/abi/track_point_load_contract_test.cpp",
        "rust_ffi_parity": "native/crates/structural-ffi/tests/track_point_load_parity.rs",
        "python_boundary": "tests/test_native_track_point_load_python_parity.py",
        "checker": "scripts/check_structural_runtime_ffi_r3.py",
    },
    "parity": {
        "legacy_displacement_residual": "pass",
        "legacy_rotation_interior": "pass",
        "legacy_rotation_endpoints": "intentional_product_divergence",
        "legacy_endpoint_max_abs_delta": 0.00003436580346133486,
        "python_full_vector": "pass",
        "c1_promoted": True,
        "c2_hip": "open",
    },
}

EXPECTED_NONLINEAR_STATIC_R3 = {
    "family": "nonlinear_static",
    "capability_gate": "C1",
    "cpp_target": "structural_solver_cpu",
    "abi_version": "0x00010003",
    "api_entry": "sa_get_api_v1",
    "api_slot": "nonlinear_static_solve",
    "legacy_exports_preserved": True,
    "fallback_count": 0,
    "c1_profile": {
        "case_count": 5,
        "story_counts": [1, 3],
        "displacement_absolute_tolerance_m": 1.0e-12,
        "residual_absolute_tolerance_n": 1.0e-7,
        "base_shear_absolute_tolerance_kn": 1.0e-10,
        "axes": [
            "topology",
            "elastic_plastic",
            "mixed_sign_load",
            "pdelta",
            "backtracking",
        ],
    },
    "product_goldens": {
        "native/tests/fixtures/solver_cpu/nonlinear_static_elastic_pdelta_python_c1.json": (
            "57df412800943da8fdd2214a88cadd314b1620c7b2c707a15f56f4828a3a9ab0"
        ),
        "native/tests/fixtures/solver_cpu/nonlinear_static_mixed_sign_python_c1.json": (
            "bdc3d7cc7681bf2de33fb092d3bc2eff5e057483fd00b315523a9b9e01aced85"
        ),
        "native/tests/fixtures/solver_cpu/nonlinear_static_one_story_elastic_python_c1.json": (
            "8759476e257a538d474ca9b3a3aa07ad0e19e823063f5bfadbf877131b7fcea1"
        ),
        "native/tests/fixtures/solver_cpu/nonlinear_static_one_story_pdelta_backtrack_python_c1.json": (
            "d06e605136921ded5fe8402f3494405cbddb2f27197fcad5d8360e468fd6002a"
        ),
        "native/tests/fixtures/solver_cpu/nonlinear_static_plastic_python_c1.json": (
            "4a08640068907cc7ceec32888f835a4e953caa5d33ad808cb6771e0f05553d16"
        ),
    },
    "owners": {
        "cpp_cpu_kernel": "native/cpp/src/solver_cpu/nonlinear_static.cpp",
        "c_abi": "native/cpp/include/structural/abi_v1.h",
        "rust_safe_wrapper": "native/crates/structural-ffi/src/lib.rs",
    },
    "verification": {
        "cpp_unit": "native/cpp/tests/solver_cpu/nonlinear_static_test.cpp",
        "c_abi_contract": "native/cpp/tests/abi/nonlinear_static_contract_test.cpp",
        "rust_ffi_parity": "native/crates/structural-ffi/tests/nonlinear_static_parity.rs",
        "python_oracle": "tests/native_oracles/nonlinear_static_story_frame.py",
        "python_boundary": "tests/test_native_nonlinear_static_python_parity.py",
        "checker": "scripts/check_structural_runtime_ffi_r3.py",
    },
    "parity": {
        "legacy_rust_full_result": "pass",
        "python_full_result_matrix": "pass",
        "nonconvergence_taxonomy": "pass",
        "c1_promoted": True,
        "c2_hip": "open",
    },
}

EXPECTED_NONLINEAR_NDTHA_R3 = {
    "family": "nonlinear_ndtha",
    "capability_gate": "C1",
    "cpp_target": "structural_solver_cpu",
    "abi_version": "0x00010004",
    "api_entry": "sa_get_api_v1",
    "api_slot": "nonlinear_ndtha_solve",
    "legacy_exports_preserved": True,
    "fallback_count": 0,
    "c1_profile": {
        "case_count": 5,
        "story_counts": [1, 2, 3],
        "step_counts": [3, 5, 6],
        "response_channel_count": 11,
        "displacement_absolute_tolerance_m": 1.0e-12,
        "drift_absolute_tolerance_pct": 1.0e-10,
        "force_absolute_tolerance_kn": 1.0e-8,
        "residual_absolute_tolerance_n": 1.0e-6,
        "axes": [
            "topology",
            "newmark_parameters",
            "elastic_plastic",
            "mixed_sign_acceleration",
            "pdelta",
            "damping_cap",
            "adaptive_retry",
            "line_search",
            "collapse",
        ],
    },
    "product_goldens": {
        "native/tests/fixtures/solver_cpu/nonlinear_ndtha_adaptive_retry_python_c1.json": (
            "0abbab21f4f017569aee5b47e4034fb2962805b264c2de5c7d43c45bfc913737"
        ),
        "native/tests/fixtures/solver_cpu/nonlinear_ndtha_collapse_python_c1.json": (
            "f4cb928d2a970bde5e863d35a4f5dcb0a06d2b2175c4c64bde7d5acda10c0362"
        ),
        "native/tests/fixtures/solver_cpu/nonlinear_ndtha_elastic_pdelta_python_c1.json": (
            "7db98121fd9a9a8e2aec9f08aee865e930e679cbf9dd1ff080cb8d7c929568a9"
        ),
        "native/tests/fixtures/solver_cpu/nonlinear_ndtha_one_story_elastic_python_c1.json": (
            "5872c8a89cf055096339a0e4a39b776ebf4af3060b3417ff4e9569d3de7916b5"
        ),
        "native/tests/fixtures/solver_cpu/nonlinear_ndtha_plastic_backtrack_python_c1.json": (
            "6cac3a4009aa00dece13e7a08f7aa01ca3705882e94adc93f351ff96dd83d66f"
        ),
    },
    "owners": {
        "cpp_cpu_kernel": "native/cpp/src/solver_cpu/nonlinear_ndtha.cpp",
        "shared_constitutive_assembly": "native/cpp/src/solver_cpu/story_frame.cpp",
        "c_abi": "native/cpp/include/structural/abi_v1.h",
        "rust_safe_wrapper": "native/crates/structural-ffi/src/lib.rs",
        "rust_product_wire": "native/crates/structural-contracts/src/solver_cpu.rs",
        "product_schema": "native/crates/structural-contracts/schemas/nonlinear_ndtha_cpu_v1.schema.json",
    },
    "verification": {
        "cpp_unit": "native/cpp/tests/solver_cpu/nonlinear_ndtha_test.cpp",
        "c_abi_contract": "native/cpp/tests/abi/nonlinear_ndtha_contract_test.cpp",
        "rust_ffi_parity": "native/crates/structural-ffi/tests/nonlinear_ndtha_parity.rs",
        "rust_wire": "native/crates/structural-contracts/tests/solver_cpu_wire.rs",
        "python_oracle": "tests/native_oracles/nonlinear_ndtha_story_frame.py",
        "python_boundary": "tests/test_native_nonlinear_ndtha_python_parity.py",
        "fuzz_target": "native/cpp/tests/fuzz/nonlinear_ndtha_fuzz.cpp",
        "checker": "scripts/check_structural_runtime_ffi_r3.py",
    },
    "parity": {
        "legacy_rust_full_result": "pass",
        "failure_atomicity": "pass",
        "collapse_terminal_mapping": "pass",
        "python_full_result_matrix": "pass",
        "nonconvergence_taxonomy": "pass",
        "c1_promoted": True,
        "c2_hip": "open",
    },
}


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _dynamic_exports(path: Path) -> tuple[list[str] | None, str | None]:
    if not path.is_file():
        return None, f"library_missing:{path}"
    completed = subprocess.run(
        ["nm", "-D", "--defined-only", str(path)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip().splitlines()
        return None, detail[-1] if detail else f"nm_exit_{completed.returncode}"
    return sorted(line.split()[-1] for line in completed.stdout.splitlines() if line.split()), None


def check_r3(
    repo_root: Path = ROOT,
    inventory_path: Path = DEFAULT_INVENTORY,
    legacy_library: Path | None = None,
    product_library: Path | None = None,
) -> dict[str, object]:
    repo_root = repo_root.resolve()
    resolved_inventory = (
        inventory_path if inventory_path.is_absolute() else repo_root / inventory_path
    )
    lower_gate = r2.check_r2(repo_root, resolved_inventory, legacy_library)
    blockers = [f"r3_lower_gate:{value}" for value in lower_gate["blockers"]]

    try:
        inventory = _load_json(resolved_inventory)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        blockers.append(f"r3_inventory_invalid:{exc}")
        return _report(blockers, lower_gate, None)
    if inventory.get("transition_step") != "R3":
        blockers.append("r3_inventory_transition_step_invalid")
    r3_inventory = inventory.get("r3_track_point_load")
    if r3_inventory != EXPECTED_R3:
        blockers.append("r3_track_inventory_invalid")
    nonlinear_inventory = inventory.get("r3_nonlinear_static")
    if nonlinear_inventory != EXPECTED_NONLINEAR_STATIC_R3:
        blockers.append("r3_nonlinear_static_inventory_invalid")
    ndtha_inventory = inventory.get("r3_nonlinear_ndtha")
    if ndtha_inventory != EXPECTED_NONLINEAR_NDTHA_R3:
        blockers.append("r3_nonlinear_ndtha_inventory_invalid")

    for family, expected in (
        ("track", EXPECTED_R3),
        ("nonlinear_static", EXPECTED_NONLINEAR_STATIC_R3),
        ("nonlinear_ndtha", EXPECTED_NONLINEAR_NDTHA_R3),
    ):
        for group in (expected["owners"], expected["verification"]):
            for role, relative_path in group.items():
                if not (repo_root / relative_path).is_file():
                    blockers.append(f"r3_owned_file_missing:{family}:{role}")

    for relative_path, expected_hash in EXPECTED_R3["product_goldens"].items():
        product_golden_path = repo_root / relative_path
        try:
            product_golden_bytes = product_golden_path.read_bytes()
        except OSError as exc:
            blockers.append(f"r3_product_golden_unreadable:{relative_path}:{exc}")
            continue
        actual_hash = hashlib.sha256(product_golden_bytes).hexdigest()
        if actual_hash != expected_hash:
            blockers.append(f"r3_product_golden_sha256_mismatch:{relative_path}")
        try:
            product_case = json.loads(product_golden_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            blockers.append(f"r3_product_golden_invalid:{relative_path}:{exc}")
            continue
        if (
            not isinstance(product_case, dict)
            or product_case.get("schema_version") != "structural-runtime-compat.v3"
            or product_case.get("operation") != "track_point_load"
        ):
            blockers.append(f"r3_product_golden_contract_invalid:{relative_path}")

    nonlinear_cases: list[dict[str, Any]] = []
    nonlinear_golden_bytes: dict[str, bytes] = {}
    for relative_path, expected_hash in EXPECTED_NONLINEAR_STATIC_R3[
        "product_goldens"
    ].items():
        golden_path = repo_root / relative_path
        try:
            golden_bytes = golden_path.read_bytes()
        except OSError as exc:
            blockers.append(
                f"r3_nonlinear_static_product_golden_unreadable:{relative_path}:{exc}"
            )
            continue
        nonlinear_golden_bytes[relative_path] = golden_bytes
        actual_hash = hashlib.sha256(golden_bytes).hexdigest()
        if actual_hash != expected_hash:
            blockers.append(
                f"r3_nonlinear_static_product_golden_sha256_mismatch:{relative_path}"
            )
        try:
            product_case = json.loads(golden_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            blockers.append(
                f"r3_nonlinear_static_product_golden_invalid:{relative_path}:{exc}"
            )
            continue
        if (
            not isinstance(product_case, dict)
            or product_case.get("schema_version")
            != "structural-runtime-compat.v3"
            or product_case.get("operation") != "nonlinear_static"
            or not isinstance(product_case.get("config"), dict)
            or not isinstance(product_case.get("inputs"), dict)
            or not isinstance(product_case.get("result"), dict)
        ):
            blockers.append(
                f"r3_nonlinear_static_product_golden_contract_invalid:{relative_path}"
            )
            continue
        nonlinear_cases.append(product_case)

    nonlinear_profile = EXPECTED_NONLINEAR_STATIC_R3["c1_profile"]
    if len(nonlinear_cases) != nonlinear_profile["case_count"]:
        blockers.append("r3_nonlinear_static_product_golden_case_count_invalid")
    else:
        configs = [case["config"] for case in nonlinear_cases]
        inputs = [case["inputs"] for case in nonlinear_cases]
        results = [case["result"] for case in nonlinear_cases]
        try:
            story_counts = sorted({config.get("story_count") for config in configs})
            pdelta_factors = {config.get("pdelta_factor") for config in configs}
            plastic_counts = {
                result.get("plastic_story_count") for result in results
            }
            has_mixed_sign_load = any(
                any(
                    isinstance(value, (int, float)) and value < 0.0
                    for value in row.get("floor_load_n", [])
                )
                for row in inputs
            )
            has_backtracking = any(
                isinstance(result.get("line_search_backtracks"), int)
                and result["line_search_backtracks"] > 0
                for result in results
            )
        except (TypeError, ValueError):
            blockers.append("r3_nonlinear_static_product_golden_matrix_invalid")
        else:
            if story_counts != nonlinear_profile["story_counts"]:
                blockers.append("r3_nonlinear_static_story_matrix_invalid")
            if pdelta_factors != {0.0, 1.0}:
                blockers.append("r3_nonlinear_static_pdelta_matrix_invalid")
            if plastic_counts != {0, 2, 3}:
                blockers.append("r3_nonlinear_static_material_matrix_invalid")
            if not has_mixed_sign_load:
                blockers.append("r3_nonlinear_static_load_matrix_invalid")
            if not has_backtracking:
                blockers.append("r3_nonlinear_static_backtracking_matrix_invalid")
            if not all(
                result.get("converged") is True and result.get("status_code") == 0
                for result in results
            ):
                blockers.append("r3_nonlinear_static_success_matrix_invalid")

    legacy_fixture_path = (
        repo_root / "native/tests/fixtures/legacy_runtime_v3/nonlinear_static.json"
    )
    product_legacy_copy = (
        "native/tests/fixtures/solver_cpu/"
        "nonlinear_static_elastic_pdelta_python_c1.json"
    )
    try:
        legacy_bytes = legacy_fixture_path.read_bytes()
    except OSError as exc:
        blockers.append(f"r3_nonlinear_static_legacy_fixture_unreadable:{exc}")
    else:
        if nonlinear_golden_bytes.get(product_legacy_copy) != legacy_bytes:
            blockers.append("r3_nonlinear_static_legacy_product_copy_mismatch")

    ndtha_cases: list[dict[str, Any]] = []
    ndtha_cases_by_path: dict[str, dict[str, Any]] = {}
    for relative_path, expected_hash in EXPECTED_NONLINEAR_NDTHA_R3[
        "product_goldens"
    ].items():
        golden_path = repo_root / relative_path
        try:
            golden_bytes = golden_path.read_bytes()
        except OSError as exc:
            blockers.append(
                f"r3_nonlinear_ndtha_product_golden_unreadable:{relative_path}:{exc}"
            )
            continue
        if hashlib.sha256(golden_bytes).hexdigest() != expected_hash:
            blockers.append(
                f"r3_nonlinear_ndtha_product_golden_sha256_mismatch:{relative_path}"
            )
        try:
            product_case = json.loads(golden_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            blockers.append(
                f"r3_nonlinear_ndtha_product_golden_invalid:{relative_path}:{exc}"
            )
            continue
        if (
            not isinstance(product_case, dict)
            or product_case.get("schema_version")
            != "structural-solver-cpu-nonlinear-ndtha.v1"
            or product_case.get("operation") != "nonlinear_ndtha"
            or not isinstance(product_case.get("config"), dict)
            or not isinstance(product_case.get("inputs"), dict)
            or not isinstance(product_case.get("result"), dict)
        ):
            blockers.append(
                f"r3_nonlinear_ndtha_product_golden_contract_invalid:{relative_path}"
            )
            continue
        ndtha_cases.append(product_case)
        ndtha_cases_by_path[relative_path] = product_case

    ndtha_profile = EXPECTED_NONLINEAR_NDTHA_R3["c1_profile"]
    if len(ndtha_cases) != ndtha_profile["case_count"]:
        blockers.append("r3_nonlinear_ndtha_product_golden_case_count_invalid")
    else:
        configs = [case["config"] for case in ndtha_cases]
        inputs = [case["inputs"] for case in ndtha_cases]
        results = [case["result"] for case in ndtha_cases]
        try:
            story_counts = sorted({config.get("story_count") for config in configs})
            step_counts = sorted({config.get("step_count") for config in configs})
            pdelta_factors = {config.get("pdelta_factor") for config in configs}
            newmark_beta = {config.get("newmark_beta") for config in configs}
            newmark_gamma = {config.get("newmark_gamma") for config in configs}
            damping_caps = {
                config.get("damping_force_cap_ratio") for config in configs
            }
            plastic_counts = {
                result.get("max_plastic_story_count") for result in results
            }
            collapsed_states = {result.get("collapsed") for result in results}
            has_mixed_sign_acceleration = any(
                any(
                    isinstance(value, (int, float)) and value < 0.0
                    for value in row.get("ag_g", [])
                )
                for row in inputs
            )
            has_adaptive_retry = any(
                max(result.get("response", {}).get("step_iterations", [])) > 1
                for result in results
            )
            has_backtracking = any(
                isinstance(result.get("total_line_search_backtracks"), int)
                and result["total_line_search_backtracks"] > 0
                for result in results
            )
            response_channel_counts = {
                len(result.get("response", {})) for result in results
            }
        except (TypeError, ValueError):
            blockers.append("r3_nonlinear_ndtha_product_golden_matrix_invalid")
        else:
            if story_counts != ndtha_profile["story_counts"]:
                blockers.append("r3_nonlinear_ndtha_story_matrix_invalid")
            if step_counts != ndtha_profile["step_counts"]:
                blockers.append("r3_nonlinear_ndtha_step_matrix_invalid")
            if pdelta_factors != {0.0, 1.0}:
                blockers.append("r3_nonlinear_ndtha_pdelta_matrix_invalid")
            if newmark_beta != {0.25, 0.3025} or newmark_gamma != {0.5, 0.6}:
                blockers.append("r3_nonlinear_ndtha_newmark_matrix_invalid")
            if damping_caps != {0.2, 0.6}:
                blockers.append("r3_nonlinear_ndtha_damping_cap_matrix_invalid")
            if plastic_counts != {0, 1, 2, 3}:
                blockers.append("r3_nonlinear_ndtha_material_matrix_invalid")
            if collapsed_states != {False, True}:
                blockers.append("r3_nonlinear_ndtha_termination_matrix_invalid")
            if not has_mixed_sign_acceleration:
                blockers.append("r3_nonlinear_ndtha_acceleration_matrix_invalid")
            if not has_adaptive_retry:
                blockers.append("r3_nonlinear_ndtha_adaptive_matrix_invalid")
            if not has_backtracking:
                blockers.append("r3_nonlinear_ndtha_backtracking_matrix_invalid")
            if response_channel_counts != {ndtha_profile["response_channel_count"]}:
                blockers.append("r3_nonlinear_ndtha_response_channels_invalid")
            if not all(
                result.get("converged_all_steps") is not result.get("collapsed")
                and result.get("execution_backend") == "cpu"
                and result.get("fallback_count") == 0
                for result in results
            ):
                blockers.append("r3_nonlinear_ndtha_success_matrix_invalid")

    ndtha_legacy_path = (
        repo_root / "native/tests/fixtures/legacy_runtime_v3/nonlinear_ndtha.json"
    )
    ndtha_product_legacy_copy = (
        "native/tests/fixtures/solver_cpu/"
        "nonlinear_ndtha_elastic_pdelta_python_c1.json"
    )
    try:
        ndtha_legacy_case = _load_json(ndtha_legacy_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        blockers.append(f"r3_nonlinear_ndtha_legacy_fixture_unreadable:{exc}")
    else:
        product_copy = ndtha_cases_by_path.get(ndtha_product_legacy_copy, {})
        if (
            product_copy.get("config") != ndtha_legacy_case.get("config")
            or product_copy.get("inputs") != ndtha_legacy_case.get("inputs")
        ):
            blockers.append("r3_nonlinear_ndtha_legacy_product_copy_mismatch")

    sources = {
        "cmake": repo_root / "native/cpp/CMakeLists.txt",
        "header": repo_root / "native/cpp/include/structural/abi_v1.h",
        "abi": repo_root / "native/cpp/src/abi/abi_v1.cpp",
        "kernel": repo_root / EXPECTED_R3["owners"]["cpp_cpu_kernel"],
        "rust": repo_root / EXPECTED_R3["owners"]["rust_safe_wrapper"],
    }
    source_text: dict[str, str] = {}
    for role, path in sources.items():
        try:
            source_text[role] = path.read_text(encoding="utf-8")
        except OSError as exc:
            blockers.append(f"r3_source_unreadable:{role}:{exc}")
            source_text[role] = ""
    required_tokens = {
        "cmake": ("structural_solver_cpu STATIC", "structural_solver_cpu structural_c_abi_v1"),
        "header": (
            "#define SA_ABI_V1_2 UINT32_C(0x00010002)",
            "sa_track_point_load_solve_fn_v1 track_point_load_solve",
            "SA_CAPABILITY_TRACK_POINT_LOAD_CPU",
        ),
        "abi": ("track_point_load_boundary", "SA_ERR_NONCONVERGENCE"),
        "kernel": ("solve_track_point_load", "conjugate_gradient"),
        "rust": ("pub fn load_track_point_load", "pub fn solve_track_point_load"),
    }
    for role, tokens in required_tokens.items():
        for token in tokens:
            if token not in source_text[role]:
                blockers.append(f"r3_source_token_missing:{role}:{token}")

    nonlinear_sources = {
        "cmake": sources["cmake"],
        "header": sources["header"],
        "abi": sources["abi"],
        "kernel": repo_root
        / EXPECTED_NONLINEAR_STATIC_R3["owners"]["cpp_cpu_kernel"],
        "rust": sources["rust"],
        "rust_parity": repo_root
        / EXPECTED_NONLINEAR_STATIC_R3["verification"]["rust_ffi_parity"],
        "python_oracle": repo_root
        / EXPECTED_NONLINEAR_STATIC_R3["verification"]["python_oracle"],
        "python_boundary": repo_root
        / EXPECTED_NONLINEAR_STATIC_R3["verification"]["python_boundary"],
    }
    nonlinear_required_tokens = {
        "cmake": ("src/solver_cpu/nonlinear_static.cpp",),
        "header": (
            "#define SA_ABI_V1_3 UINT32_C(0x00010003)",
            "sa_nonlinear_static_solve_fn_v1 nonlinear_static_solve",
            "SA_CAPABILITY_NONLINEAR_STATIC_CPU",
        ),
        "abi": ("nonlinear_static_boundary", "SA_ERR_NONCONVERGENCE"),
        "kernel": ("solve_nonlinear_static", "solve_tridiagonal"),
        "rust": (
            "pub fn load_nonlinear_static",
            "pub fn solve_nonlinear_static",
        ),
        "rust_parity": (
            "safe_v1_3_cpp_path_matches_the_complete_python_c1_matrix",
            "nonconverged.max_iter = 1",
            "SA_ERR_NONCONVERGENCE",
        ),
        "python_oracle": (
            "Independent dense-matrix oracle",
            "np.linalg.solve",
            "solve_nonlinear_static_oracle",
        ),
        "python_boundary": (
            "PRODUCT_FIXTURES",
            "test_dense_python_oracle_matches_the_complete_product_c1_matrix",
            "test_python_oracle_and_native_error_contract_share_the_nonconvergence_case",
        ),
    }
    nonlinear_source_text: dict[str, str] = {}
    for role, path in nonlinear_sources.items():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            blockers.append(f"r3_source_unreadable:nonlinear_static:{role}:{exc}")
            continue
        nonlinear_source_text[role] = text
        for token in nonlinear_required_tokens[role]:
            if token not in text:
                blockers.append(
                    f"r3_source_token_missing:nonlinear_static:{role}:{token}"
                )
    python_oracle_text = nonlinear_source_text.get("python_oracle", "")
    for forbidden in (
        "import ctypes",
        "import subprocess",
        "rust_nonlinear_frame_bridge",
        "structural_runtime_ffi",
        "sa_get_api_v1",
    ):
        if forbidden in python_oracle_text:
            blockers.append(
                f"r3_nonlinear_static_python_oracle_native_dependency:{forbidden}"
            )

    ndtha_sources = {
        "cmake": sources["cmake"],
        "header": sources["header"],
        "abi": sources["abi"],
        "kernel": repo_root
        / EXPECTED_NONLINEAR_NDTHA_R3["owners"]["cpp_cpu_kernel"],
        "constitutive": repo_root
        / EXPECTED_NONLINEAR_NDTHA_R3["owners"]["shared_constitutive_assembly"],
        "rust": sources["rust"],
        "rust_parity": repo_root
        / EXPECTED_NONLINEAR_NDTHA_R3["verification"]["rust_ffi_parity"],
        "rust_wire": repo_root
        / EXPECTED_NONLINEAR_NDTHA_R3["verification"]["rust_wire"],
        "python_oracle": repo_root
        / EXPECTED_NONLINEAR_NDTHA_R3["verification"]["python_oracle"],
        "python_boundary": repo_root
        / EXPECTED_NONLINEAR_NDTHA_R3["verification"]["python_boundary"],
        "abi_contract": repo_root
        / EXPECTED_NONLINEAR_NDTHA_R3["verification"]["c_abi_contract"],
        "fuzz": repo_root
        / EXPECTED_NONLINEAR_NDTHA_R3["verification"]["fuzz_target"],
    }
    ndtha_required_tokens = {
        "cmake": (
            "src/solver_cpu/nonlinear_ndtha.cpp",
            "src/solver_cpu/story_frame.cpp",
        ),
        "header": (
            "#define SA_ABI_V1_4 UINT32_C(0x00010004)",
            "sa_nonlinear_ndtha_solve_fn_v1 nonlinear_ndtha_solve",
            "SA_CAPABILITY_NONLINEAR_NDTHA_CPU",
        ),
        "abi": (
            "nonlinear_ndtha_boundary",
            "SA_ERR_NONCONVERGENCE",
            "nonlinear NDTHA output buffers overlap",
        ),
        "kernel": (
            "solve_nonlinear_ndtha",
            "solve_step",
            "recover_story_response",
        ),
        "constitutive": (
            "assemble_story_frame",
            "solve_tridiagonal",
        ),
        "rust": (
            "pub fn load_nonlinear_ndtha",
            "pub fn solve_nonlinear_ndtha",
        ),
        "rust_parity": (
            "safe_v1_4_cpp_path_matches_the_complete_frozen_legacy_rust_result",
            "safe_v1_4_cpp_path_matches_the_complete_python_c1_matrix",
            "SA_ERR_NONCONVERGENCE",
            "physical collapse is a complete terminal result",
        ),
        "rust_wire": (
            "all_nonlinear_ndtha_product_goldens_are_strict_typed_round_trips",
            "solver_cpu_terminal_state_invalid",
        ),
        "python_oracle": (
            "Independent dense-matrix oracle",
            "np.linalg.solve",
            "solve_nonlinear_ndtha_oracle",
        ),
        "python_boundary": (
            "PRODUCT_FIXTURES",
            "test_dense_python_oracle_matches_every_product_result_channel",
            "test_python_oracle_models_nonconvergence_without_committing_partial_state",
        ),
        "abi_contract": (
            "invalid_and_nonconverged_calls_are_failure_atomic",
            "output_metadata_and_aliasing_fail_closed",
            "physical_collapse_returns_a_complete_terminal_result",
        ),
        "fuzz": ("LLVMFuzzerTestOneInput", "nonlinear_ndtha_solve"),
    }
    ndtha_source_text: dict[str, str] = {}
    for role, path in ndtha_sources.items():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            blockers.append(f"r3_source_unreadable:nonlinear_ndtha:{role}:{exc}")
            continue
        ndtha_source_text[role] = text
        for token in ndtha_required_tokens[role]:
            if token not in text:
                blockers.append(
                    f"r3_source_token_missing:nonlinear_ndtha:{role}:{token}"
                )
    ndtha_oracle_text = ndtha_source_text.get("python_oracle", "")
    for forbidden in (
        "import ctypes",
        "import subprocess",
        "structural_runtime_ffi",
        "sa_get_api_v1",
    ):
        if forbidden in ndtha_oracle_text:
            blockers.append(
                f"r3_nonlinear_ndtha_python_oracle_native_dependency:{forbidden}"
            )

    try:
        capabilities = _load_json(repo_root / "native/capabilities.json")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        blockers.append(f"r3_capabilities_invalid:{exc}")
        capabilities = {}
    capability = capabilities.get("capabilities", {}).get("track_point_load_cpu", {})
    if not isinstance(capability, dict) or capability.get("status") != "implemented":
        blockers.append("r3_track_capability_not_implemented")
    else:
        if capability.get("cutover_gate") != "C1":
            blockers.append("r3_track_capability_gate_invalid")
        claim = str(capability.get("claim", ""))
        for boundary in (
            "Python C1",
            "9-node midpoint-load",
            "legacy Rust",
            "broader input-space",
            "HIP C2",
            "restart",
            "product E2E",
        ):
            if boundary not in claim:
                blockers.append(f"r3_track_claim_boundary_missing:{boundary}")

    nonlinear_capability = capabilities.get("capabilities", {}).get(
        "nonlinear_static_cpu", {}
    )
    if (
        not isinstance(nonlinear_capability, dict)
        or nonlinear_capability.get("status") != "implemented"
    ):
        blockers.append("r3_nonlinear_static_capability_not_implemented")
    else:
        if nonlinear_capability.get("cutover_gate") != "C1":
            blockers.append("r3_nonlinear_static_capability_gate_invalid")
        nonlinear_claim = str(nonlinear_capability.get("claim", ""))
        for boundary in (
            "ABI v1.3",
            "Python C1",
            "five-case",
            "elastic/plastic",
            "mixed-sign load",
            "P-delta",
            "backtracking",
            "broader nonlinear input-space",
            "HIP C2",
            "restart",
            "product E2E",
        ):
            if boundary not in nonlinear_claim:
                blockers.append(
                    f"r3_nonlinear_static_claim_boundary_missing:{boundary}"
                )

    ndtha_capability = capabilities.get("capabilities", {}).get(
        "nonlinear_ndtha_cpu", {}
    )
    if (
        not isinstance(ndtha_capability, dict)
        or ndtha_capability.get("status") != "implemented"
    ):
        blockers.append("r3_nonlinear_ndtha_capability_not_implemented")
    else:
        if ndtha_capability.get("cutover_gate") != "C1":
            blockers.append("r3_nonlinear_ndtha_capability_gate_invalid")
        ndtha_claim = str(ndtha_capability.get("claim", ""))
        for boundary in (
            "ABI v1.4",
            "shared constitutive assembly",
            "independent dense-matrix Python C1",
            "five-case",
            "adaptive retry",
            "collapse",
            "broader dynamic input-space parity",
            "HIP C2",
            "restart",
            "product E2E",
        ):
            if boundary not in ndtha_claim:
                blockers.append(
                    f"r3_nonlinear_ndtha_claim_boundary_missing:{boundary}"
                )

    product_exports: list[str] | None = None
    if product_library is not None:
        resolved_library = (
            product_library if product_library.is_absolute() else repo_root / product_library
        )
        product_exports, export_error = _dynamic_exports(resolved_library)
        if export_error is not None:
            blockers.append(f"r3_product_export_check_failed:{export_error}")
        elif product_exports != ["sa_get_api_v1"]:
            blockers.append("r3_product_export_set_mismatch")

    return _report(blockers, lower_gate, product_exports)


def _report(
    blockers: list[str],
    lower_gate: dict[str, object],
    product_exports: list[str] | None,
) -> dict[str, object]:
    blockers = sorted(dict.fromkeys(blockers))
    return {
        "schema_version": "structural-runtime-ffi-r3-check.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "lower_gate_pass": lower_gate.get("contract_pass") is True,
        "legacy_exports": lower_gate.get("expected_exports", []),
        "product_exports": product_exports,
        "capability_gate": "C1",
        "capability_gates": {
            "track_point_load_cpu": "C1",
            "nonlinear_static_cpu": "C1",
            "nonlinear_ndtha_cpu": "C1",
        },
        "blockers": blockers,
        "claim_boundary": (
            "R3 proves track Python C1 full-vector parity only for the four-case 9-node "
            "midpoint-load matrix, plus nonlinear static Python C1 full-result parity only "
            "for the five-case 1/3-story topology, elastic/plastic, mixed-sign load, P-delta "
            "and backtracking matrix through ABI v1.3. Nonlinear NDTHA proves Python C1 "
            "full-result parity only for the five-case 1/2/3-story Newmark, elastic/plastic, "
            "mixed-sign acceleration, P-delta, damping-cap, adaptive-retry, line-search and "
            "collapse matrix through ABI v1.4. Broader dynamic input-space parity, HIP C2 and "
            "runtime cutover remain open."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--legacy-library", type=Path)
    parser.add_argument("--product-library", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = check_r3(
        args.repo_root,
        args.inventory,
        args.legacy_library,
        args.product_library,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Structural runtime FFI R3: {payload['status']}")
        for blocker in payload["blockers"]:
            print(f"- {blocker}")
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
