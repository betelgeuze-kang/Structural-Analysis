#!/usr/bin/env python3
"""Verify that the bounded native MGT import-health claim has executable evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_TOKENS = {
    "native/crates/structural-contracts/src/mgt_import.rs": (
        "structural-native-mgt-import-health.v1",
        "MgtRowDispositionKindV1",
        "mgt_encoding_unsupported",
        "mgt_element_family_dropped",
        "build_model_ir",
        "source_sha256",
    ),
    "native/crates/structural-contracts/tests/mgt_import_wire.rs": (
        "all_tracked_mgt_fixtures_match_the_language_neutral_python_oracle",
        "encoding_duplicate_and_dangling_fail_closed_as_import_health",
        "source_mutation_changes_every_bound_identity",
    ),
    "native/crates/structural-cli/src/mgt_product.rs": (
        "execute_native_mgt_import",
        "publish_native_mgt_import",
        "validate_model_ir",
        "mgt_cpp_snapshot_identity_mismatch",
    ),
    "native/crates/structural-cli/tests/mgt_import_cli.rs": (
        "clean_environment_exact_import_is_cpp_validated_and_deterministic",
        "command.env_clear()",
        "--require-normalized",
        "source symlink",
    ),
    "tests/test_native_mgt_import_health_python_parity.py": (
        "test_python_raw_parser_owns_the_frozen_native_mgt_input_matrix",
        "test_exact_numeric_fixture_has_independent_closed_form_properties",
    ),
    "docs/native/mgt-import-health-v1.md": (
        "C5",
        "preserved_only",
        "Python",
        "C++",
        "C6",
    ),
}


def check_native_mgt_import(repo_root: Path = ROOT) -> dict[str, object]:
    root = repo_root.resolve()
    blockers: list[str] = []
    try:
        payload = json.loads(
            (root / "native/capabilities.json").read_text(encoding="utf-8")
        )
        row = payload["capabilities"]["mgt_import_health"]
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        blockers.append(f"mgt_import_capability_manifest_invalid:{exc}")
        row = {}
    if row.get("status") != "implemented":
        blockers.append("mgt_import_capability_not_implemented")
    if row.get("cutover_gate") != "C5":
        blockers.append("mgt_import_capability_gate_not_c5")
    if row.get("owner") != "structural-cli":
        blockers.append("mgt_import_capability_owner_invalid")
    claim = str(row.get("claim", ""))
    for token in (
        "original bytes",
        "mapped/preserved_only/dropped/unsupported",
        "C++ semantic validator",
        "Python C1",
        "CP949",
        "C6",
    ):
        if token not in claim:
            blockers.append(f"mgt_import_scope_token_missing:{token}")

    for relative, tokens in REQUIRED_TOKENS.items():
        path = root / relative
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            blockers.append(f"mgt_import_evidence_missing:{relative}")
            continue
        for token in tokens:
            if token not in text:
                blockers.append(f"mgt_import_evidence_token_missing:{relative}:{token}")

    try:
        golden = json.loads(
            (root / "native/tests/golden/mgt_import_health_v1.json").read_text(
                encoding="utf-8"
            )
        )
        cases = golden["cases"]
        if golden.get("schema_version") != "structural-native-mgt-python-oracle.v1":
            blockers.append("mgt_import_oracle_schema_invalid")
        if not isinstance(cases, list) or len(cases) != 5:
            blockers.append("mgt_import_oracle_case_count_invalid")
        elif sum(case["native_expected"]["status"] == "normalized" for case in cases) != 1:
            blockers.append("mgt_import_oracle_normalized_profile_count_invalid")
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        blockers.append("mgt_import_oracle_golden_invalid")

    blockers = sorted(set(blockers))
    return {
        "schema_version": "native-mgt-import-contract.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "cutover_gate": row.get("cutover_gate"),
        "blockers": blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = check_native_mgt_import(args.root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Native MGT import contract: {report['status']}")
        for blocker in report["blockers"]:
            print(f"- {blocker}")
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
