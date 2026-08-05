#!/usr/bin/env python3
"""Compare Linux and Windows installed-wheel planar product replay receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


EXPECTED_OS_LABELS = ("ubuntu-latest", "windows-latest")
REPLAY_ARTIFACT_FILES = {
    "model_sha256": "runtime/public-model.json",
    "result_sha256": "runtime/public-result.json",
    "report_sha256": "runtime/public-report.json",
    "checkpoint_sha256": "runtime/public-checkpoint.json",
    "workbench_case_sha256": "runtime/workbench-case.json",
}


class PlanarProductReplayComparisonError(RuntimeError):
    """Raised when cross-platform product replay evidence is incomplete."""


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PlanarProductReplayComparisonError(f"invalid_json:{path}") from error
    if not isinstance(payload, dict):
        raise PlanarProductReplayComparisonError(f"json_not_object:{path}")
    return payload


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        (
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
    )


def _discover_coordinates(root: Path) -> dict[str, Path]:
    discovered: dict[str, Path] = {}
    for receipt_path in sorted(root.glob("*/runtime/product-replay.json")):
        coordinate_root = receipt_path.parents[1]
        receipt = _load_object(receipt_path)
        coordinate = _mapping(receipt.get("coordinate"))
        os_label = coordinate.get("os_label")
        if not isinstance(os_label, str) or not os_label:
            raise PlanarProductReplayComparisonError(
                f"coordinate_os_label_missing:{receipt_path}"
            )
        if os_label in discovered:
            raise PlanarProductReplayComparisonError(
                f"duplicate_coordinate:{os_label}"
            )
        discovered[os_label] = coordinate_root
    return discovered


def _record_blocker(blockers: list[str], code: str, condition: bool) -> None:
    if not condition:
        blockers.append(code)


def compare_product_replays(
    *,
    artifacts_root: Path,
    expected_source_commit: str | None = None,
) -> dict[str, Any]:
    coordinate_roots = _discover_coordinates(artifacts_root)
    blockers: list[str] = []
    _record_blocker(
        blockers,
        "coordinate_set_mismatch",
        set(coordinate_roots) == set(EXPECTED_OS_LABELS),
    )

    rows: dict[str, dict[str, Any]] = {}
    for os_label in EXPECTED_OS_LABELS:
        coordinate_root = coordinate_roots.get(os_label)
        if coordinate_root is None:
            continue
        replay_path = coordinate_root / "runtime/product-replay.json"
        browser_path = coordinate_root / "runtime/browser-replay.json"
        replay = _load_object(replay_path)
        browser = _load_object(browser_path)
        coordinate = _mapping(replay.get("coordinate"))
        wheel = _mapping(replay.get("wheel"))
        artifacts = _mapping(replay.get("artifacts"))
        result_truth = _mapping(replay.get("result_truth"))
        browser_coordinate = _mapping(browser.get("coordinate"))

        _record_blocker(
            blockers,
            f"{os_label}:replay_contract_blocked",
            replay.get("contract_pass") is True,
        )
        _record_blocker(
            blockers,
            f"{os_label}:browser_contract_blocked",
            browser.get("contract_pass") is True,
        )
        _record_blocker(
            blockers,
            f"{os_label}:coordinate_binding_invalid",
            coordinate.get("os_label") == os_label
            and browser_coordinate.get("os_label") == os_label,
        )
        _record_blocker(
            blockers,
            f"{os_label}:browser_source_binding_invalid",
            browser.get("source_commit_sha") == replay.get("source_commit_sha"),
        )
        if expected_source_commit is not None:
            _record_blocker(
                blockers,
                f"{os_label}:source_commit_mismatch",
                replay.get("source_commit_sha") == expected_source_commit,
            )

        wheel_filename = wheel.get("filename")
        wheel_path = (
            coordinate_root / "wheel" / wheel_filename
            if isinstance(wheel_filename, str)
            else coordinate_root / "wheel/__missing__"
        )
        _record_blocker(
            blockers,
            f"{os_label}:wheel_bytes_missing_or_mismatched",
            wheel_path.is_file() and wheel.get("sha256") == _sha256(wheel_path),
        )
        for field, relative_path in REPLAY_ARTIFACT_FILES.items():
            artifact_path = coordinate_root / relative_path
            _record_blocker(
                blockers,
                f"{os_label}:{field}_bytes_missing_or_mismatched",
                artifact_path.is_file() and artifacts.get(field) == _sha256(artifact_path),
            )

        rows[os_label] = {
            "source_commit_sha": replay.get("source_commit_sha"),
            "profile": replay.get("profile"),
            "engine_version": replay.get("engine_version"),
            "wheel_filename": wheel_filename,
            "wheel_sha256": wheel.get("sha256"),
            "artifacts": dict(artifacts),
            "result_truth": dict(result_truth),
            "immutable_analysis_core_sha256": browser.get(
                "immutable_analysis_core_sha256"
            ),
            "review_envelope_sha256": browser.get("review_envelope_sha256"),
            "analysis_result_sha256": browser.get("analysis_result_sha256"),
            "product_profile": browser.get("product_profile"),
            "analysis_status": browser.get("analysis_status"),
            "provenance_contract": browser.get("provenance_contract"),
        }

    comparable_fields = (
        "source_commit_sha",
        "profile",
        "engine_version",
        "wheel_filename",
        "wheel_sha256",
        "artifacts",
        "result_truth",
        "immutable_analysis_core_sha256",
        "review_envelope_sha256",
        "analysis_result_sha256",
        "product_profile",
        "analysis_status",
        "provenance_contract",
    )
    matching: dict[str, bool] = {}
    if set(rows) == set(EXPECTED_OS_LABELS):
        reference = rows[EXPECTED_OS_LABELS[0]]
        candidate = rows[EXPECTED_OS_LABELS[1]]
        for field in comparable_fields:
            field_match = reference.get(field) == candidate.get(field)
            matching[field] = field_match
            _record_blocker(
                blockers,
                f"cross_platform_{field}_mismatch",
                field_match,
            )
    else:
        matching = {field: False for field in comparable_fields}

    contract_pass = not blockers
    return {
        "schema_version": "planar-product-replay-comparison.v1",
        "contract_pass": contract_pass,
        "expected_os_labels": list(EXPECTED_OS_LABELS),
        "coordinate_count": len(rows),
        "matching": matching,
        "coordinates": rows,
        "blockers": blockers,
        "claim_boundary": (
            "This receipt proves that one canonical pure-Python wheel and the declared "
            "bounded M2 product replay produced identical public artifacts and Workbench "
            "analysis/review envelope hashes on GitHub-hosted Linux and Windows runners. "
            "It does not establish arbitrary-model portability, external V&V, design "
            "authority, performance advantage, customer deployment, or release eligibility."
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts-root", type=Path, required=True)
    parser.add_argument("--expected-source-commit")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    args = parser.parse_args(argv)
    receipt = compare_product_replays(
        artifacts_root=args.artifacts_root,
        expected_source_commit=args.expected_source_commit,
    )
    _write_json(args.out, receipt)
    if args.json:
        print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "planar product replay comparison: "
            + ("pass" if receipt["contract_pass"] else "blocked")
        )
    if args.fail_blocked and receipt["contract_pass"] is not True:
        raise PlanarProductReplayComparisonError(
            "comparison_blocked:" + ",".join(receipt["blockers"])
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
