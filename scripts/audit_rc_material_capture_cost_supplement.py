"""Read-only correction of the context roster in one frozen F/G cost packet.

The numerical producer and original audit remain at NUMERICAL_REVISION. This
audit-only child commit adds no solver or snapshot changes and writes a separate
receipt outside the original packet.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import run_rc_material_capture_cost_campaign as campaign


NUMERICAL_REVISION = "5187de5fab1e5d4403c9f8191568e2dd8ffec4a6"
AUDIT_ONLY_FILES = {
    "scripts/audit_rc_material_capture_cost_supplement.py",
    "tests/test_rc_material_capture_cost_supplement.py",
}


def _git(*args: str) -> str:
    root = Path(__file__).resolve().parents[1]
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def _audit_only_revision() -> str:
    if _git("status", "--porcelain"):
        raise ValueError("supplemental audit requires a clean checkout")
    head = _git("rev-parse", "HEAD")
    if _git("rev-parse", "HEAD^") != NUMERICAL_REVISION or set(
        _git("diff", "--name-only", "HEAD^", "HEAD").splitlines()
    ) != AUDIT_ONLY_FILES:
        raise ValueError("supplemental source must be an audit-only child commit")
    return head


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _pair_bytes(left: Path, right: Path) -> dict:
    expected_contexts = {
        name
        for index in range(12)
        for name in (f"{index:03d}-context.json", f"{index:03d}-guard-context.json")
    }
    expected_steps = {f"{index:03d}-1-step.json" for index in range(12)} | {
        "preload-step.json"
    }
    expected = expected_contexts | expected_steps
    folders = (left / "benchmark/proposal", right / "benchmark/proposal")
    observed = [
        {
            path.name
            for pattern in ("*-context.json", "*-step.json")
            for path in folder.glob(pattern)
        }
        for folder in folders
    ]
    exact_roster = all(names == expected for names in observed)
    mismatches = sorted(
        name
        for name in expected
        if any(name not in names for names in observed)
        or (folders[0] / name).read_bytes() != (folders[1] / name).read_bytes()
    )
    manifest_hashes = [
        campaign._sha(
            campaign._bytes(
                [{"name": name, "sha256": _digest(folder / name)} for name in sorted(expected)]
            )
        )
        if expected <= names
        else None
        for folder, names in zip(folders, observed)
    ]
    return {
        "exact": exact_roster and not mismatches,
        "context_file_count": len(expected_contexts),
        "step_file_count": len(expected_steps),
        "left_observed_file_count": len(observed[0]),
        "right_observed_file_count": len(observed[1]),
        "mismatch_names": mismatches,
        "left_manifest_hash": manifest_hashes[0],
        "right_manifest_hash": manifest_hashes[1],
    }


def audit_supplement(packet: Path) -> dict:
    audit_revision = _audit_only_revision()
    plan = campaign._read_plan(packet)
    if plan["source_revision"] != NUMERICAL_REVISION:
        raise ValueError("supplemental audit requires the frozen numerical revision")
    original = json.loads((packet / "audit.json").read_bytes())
    if (
        original.get("source_revision") != NUMERICAL_REVISION
        or original.get("plan_hash") != plan["plan_hash"]
        or original.get("all_pairs_exact") is not False
        or len(original.get("slots", [])) != 12
    ):
        raise ValueError("original failed audit is not the declared source")

    original_clean_head = campaign.pilot._clean_head
    original_pair_check = campaign._proposal_bytes_match
    try:
        # Only the numerical-head check and known incorrect 12-context count
        # are corrected in memory. All other original audit checks run intact.
        campaign.pilot._clean_head = lambda: NUMERICAL_REVISION
        campaign._proposal_bytes_match = lambda a, b: _pair_bytes(a, b)["exact"]
        corrected = campaign.audit(packet, write=False)
    finally:
        campaign.pilot._clean_head = original_clean_head
        campaign._proposal_bytes_match = original_pair_check

    pairs = []
    for row in corrected["pairs"]:
        case_id, repetition = row["case_id"], row["repetition_index"]
        slots = {
            slot["mode"]: packet / f"slot-{slot['slot_index']:04d}"
            for slot in plan["schedule"]
            if slot["case_id"] == case_id and slot["repetition_index"] == repetition
        }
        details = _pair_bytes(slots["uncached"], slots["cached"])
        if details["exact"] != row["contexts_and_steps_exact"]:
            raise ValueError("corrected pair result differs from raw bytes")
        pairs.append({"case_id": case_id, "repetition_index": repetition, **details})

    bound_files = [packet / "plan.json", packet / "audit.json"]
    for index in range(12):
        folder = packet / f"slot-{index:04d}"
        bound_files.extend((folder / "outcome.json", folder / "inventory.json"))
    receipt = {
        "schema_version": "rc-material-layout-cost-supplemental-audit.v1",
        "numerical_source_revision": NUMERICAL_REVISION,
        "audit_source_revision": audit_revision,
        "plan_hash": plan["plan_hash"],
        "source_packet_inventory_sha256": plan["source_packet_inventory_sha256"],
        "original_packet": str(packet.resolve()),
        "bound_file_hashes": {
            path.relative_to(packet).as_posix(): _digest(path) for path in bound_files
        },
        "correction": "original glob included 12 proposal contexts plus 12 guard contexts but required a count of 12; exact fixed roster has 24 contexts and 13 step files",
        "pairs": pairs,
        "corrected_audit": corrected,
    }
    receipt["receipt_hash"] = campaign._sha(campaign._bytes(receipt))
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(args.packet.resolve()):
        raise ValueError("supplemental receipt must be outside the original packet")
    result = audit_supplement(args.packet)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as sink:
        sink.write(campaign._bytes(result))
    print(
        json.dumps(
            {
                "receipt_hash": result["receipt_hash"],
                "audit_source_revision": result["audit_source_revision"],
                "numerical_source_revision": result["numerical_source_revision"],
                "all_pairs_exact": result["corrected_audit"]["all_pairs_exact"],
                "modes": [
                    {
                        "mode": mode["mode"],
                        "equal_case_mean_ratio": mode["equal_case_mean_ratio"],
                        "predeclared_path_screen_pass": mode["predeclared_path_screen_pass"],
                    }
                    for mode in result["corrected_audit"]["modes"]
                ],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
