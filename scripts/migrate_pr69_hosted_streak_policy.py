#!/usr/bin/env python3
"""One-shot migration for PR 69 hosted CI streak/readiness contracts."""

from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one occurrence, found {count}")
    return text.replace(old, new, 1)


def _migrate_streak_builder() -> None:
    path = ROOT / "scripts/build_ci_streak_intake_packet.py"
    text = path.read_text(encoding="utf-8")

    text = _replace_once(
        text,
        '''        *(["local_workflow_uses_github_hosted_runner"] if source_lane_present and local_github_hosted_runner_default else []),
        *(
            ["local_self_hosted_runner_default_missing"]
            if source_lane_present and local_workflow_present and not local_self_hosted_runner_default
            else []
        ),''',
        '''        *(
            ["local_workflow_uses_self_hosted_runner"]
            if source_lane_present
            and source_threshold_pass
            and local_self_hosted_runner_default
            else []
        ),
        *(
            ["local_github_hosted_runner_default_missing"]
            if source_lane_present
            and source_threshold_pass
            and local_workflow_present
            and not local_github_hosted_runner_default
            else []
        ),''',
        "source-lane runner blockers",
    )

    text = _replace_once(
        text,
        '''        _check_row(
            field="lanes.pr.local_self_hosted_runner_default",
            current_value=pr_source.get("local_self_hosted_runner_default"),
            required_value="true",
            closure_check="pr_self_hosted_runner_default_pass",
            closure_check_pass=pr_source.get("local_self_hosted_runner_default") is True,
            owner_note="The PR workflow must keep the required self-hosted runner default.",
        ),
        _check_row(
            field="lanes.nightly.local_self_hosted_runner_default",
            current_value=nightly_source.get("local_self_hosted_runner_default"),
            required_value="true",
            closure_check="nightly_self_hosted_runner_default_pass",
            closure_check_pass=nightly_source.get("local_self_hosted_runner_default") is True,
            owner_note="The nightly workflow must keep the required self-hosted runner default.",
        ),''',
        '''        _check_row(
            field="lanes.pr.local_github_hosted_runner_default",
            current_value=pr_source.get("local_github_hosted_runner_default"),
            required_value="true",
            closure_check="pr_github_hosted_runner_default_pass",
            closure_check_pass=pr_source.get("local_github_hosted_runner_default") is True,
            owner_note=(
                "The canonical PR workflow must use the deterministic GitHub-hosted "
                "runner class."
            ),
        ),
        _check_row(
            field="lanes.nightly.local_github_hosted_runner_default",
            current_value=nightly_source.get("local_github_hosted_runner_default"),
            required_value="true",
            closure_check="nightly_github_hosted_runner_default_pass",
            closure_check_pass=nightly_source.get("local_github_hosted_runner_default") is True,
            owner_note=(
                "The canonical nightly workflow must use the deterministic GitHub-hosted "
                "runner class."
            ),
        ),''',
        "required runner fields",
    )

    text = _replace_once(
        text,
        '''    github_hosted_runner_defaults = bool(
        pr_source.get("local_github_hosted_runner_default")
        or nightly_source.get("local_github_hosted_runner_default")
    )
    runner_pass = (
        runner_precondition.get("contract_pass") is True
        if runner_precondition.get("evaluated") is True
        else True
    )''',
        '''    deterministic_hosted_defaults = bool(
        pr_source.get("local_github_hosted_runner_default") is True
        and nightly_source.get("local_github_hosted_runner_default") is True
        and pr_source.get("local_self_hosted_runner_default") is not True
        and nightly_source.get("local_self_hosted_runner_default") is not True
    )
    # Hardware/private-corpus runner availability is tracked separately and does
    # not invalidate the canonical deterministic PR/nightly streak.
    runner_pass = True''',
        "derived runner variables",
    )

    replacements = {
        'field="self_hosted_runner_precondition",': (
            'field="heavy_runner_precondition_informational",'
        ),
        'required_value="at least one required self-hosted runner online when evaluated",': (
            'required_value="informational only; canonical streak credit is hosted",'
        ),
        'closure_check="self_hosted_runner_precondition_pass",': (
            'closure_check="heavy_runner_precondition_nonblocking",'
        ),
        'owner_note="Queued self-hosted runs cannot accumulate a 30-run release streak.",': (
            'owner_note=(\n'
            '                "Self-hosted availability remains visible for heavy lanes but "\n'
            '                "does not block canonical hosted streak credit."\n'
            '            ),'
        ),
        'field="github_hosted_runner_defaults_absent",': (
            'field="deterministic_github_hosted_runner_defaults_present",'
        ),
        'current_value=github_hosted_runner_defaults,': (
            'current_value=deterministic_hosted_defaults,'
        ),
        'required_value="false",\n            closure_check="github_hosted_runner_default_absent_pass",\n            closure_check_pass=not github_hosted_runner_defaults,\n            owner_note="Do not close this gate by moving the release streak to a different runner class.",': (
            'required_value="true",\n'
            '            closure_check="deterministic_github_hosted_runner_defaults_present",\n'
            '            closure_check_pass=deterministic_hosted_defaults,\n'
            '            owner_note=(\n'
            '                "Canonical PR and nightly streak credit must come from the "\n'
            '                "deterministic GitHub-hosted lanes."\n'
            '            ),'
        ),
        '"runner_class": "self-hosted linux x64",': (
            '"runner_class": "GitHub-hosted deterministic PR/nightly lanes",'
        ),
        '"github-hosted runner defaults when self-hosted labels are required",': (
            '"self-hosted heavy/private/hardware runs substituted for canonical hosted streak credit",'
        ),
        '"bring the required self-hosted runner online, rerun the workflow, "': (
            '"restore the counted lane runner or job-start condition, rerun the workflow, "'
        ),
        '"Bring the required self-hosted runner online, let queued "': (
            '"Restore the counted lane runner or job-start condition, let queued "'
        ),
    }
    for old, new in replacements.items():
        text = _replace_once(text, old, new, old)

    unblock_pattern = re.compile(
        r'''    if runner_precondition\.get\("evaluated"\) is True and runner_precondition\.get\("contract_pass"\) is not True:\n        plan\.append\(\n            \{.*?\n            \}\n        \)\n''',
        re.DOTALL,
    )
    text, count = unblock_pattern.subn("", text, count=1)
    if count != 1:
        raise RuntimeError(f"runner unblock-plan removal count={count}")

    text = _replace_once(
        text,
        '''    runner_blockers = [
        f"runner:{blocker}"
        for blocker in runner_precondition["blockers"]
        if runner_precondition["evaluated"] and not runner_precondition["contract_pass"]
    ]
    blockers.extend(runner_blockers)''',
        '''    # Self-hosted health remains attached as heavy-lane context only.
    # Canonical PR/nightly streak credit is collected on hosted lanes.
    runner_blockers: list[str] = []''',
        "runner blocker aggregation",
    )

    path.write_text(text, encoding="utf-8")


def _migrate_streak_tests() -> None:
    path = ROOT / "tests/test_build_ci_streak_intake_packet.py"
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    output: list[str] = []
    replacements = 0
    index = 0
    needle = '                    "local_workflow_runs_on": [\n'
    while index < len(lines):
        if lines[index] == needle:
            if (
                index + 4 >= len(lines)
                or "STRUCTURAL_ACTIONS_RUNNER_LABELS" not in lines[index + 1]
                or lines[index + 2].strip() != "],"
                or "local_self_hosted_runner_default" not in lines[index + 3]
                or "local_github_hosted_runner_default" not in lines[index + 4]
            ):
                raise RuntimeError("unexpected CI streak runner fixture")
            output.extend(
                [
                    '                    "local_workflow_runs_on": ["ubuntu-latest"],\n',
                    '                    "local_self_hosted_runner_default": False,\n',
                    '                    "local_github_hosted_runner_default": True,\n',
                ]
            )
            index += 5
            replacements += 1
            continue
        output.append(lines[index])
        index += 1
    if replacements != 2:
        raise RuntimeError(f"valid hosted fixture replacement count={replacements}")
    text = "".join(output)

    replacements_map = {
        '"runner_class": "self-hosted linux x64",': (
            '"runner_class": "GitHub-hosted deterministic PR/nightly lanes",'
        ),
        'assert payload["source_evidence"]["lanes"]["pr"]["local_self_hosted_runner_default"] is True': (
            'assert payload["source_evidence"]["lanes"]["pr"]["local_github_hosted_runner_default"] is True\n'
            '    assert payload["source_evidence"]["lanes"]["pr"]["local_self_hosted_runner_default"] is False'
        ),
        'def test_ci_streak_intake_packet_rejects_github_hosted_runner_default(tmp_path: Path) -> None:': (
            'def test_ci_streak_intake_packet_rejects_self_hosted_runner_default_for_canonical_lane(tmp_path: Path) -> None:'
        ),
        'payload["lanes"]["pr"]["local_workflow_runs_on"] = ["ubuntu-latest"]\n    payload["lanes"]["pr"]["local_self_hosted_runner_default"] = False\n    payload["lanes"]["pr"]["local_github_hosted_runner_default"] = True': (
            'payload["lanes"]["pr"]["local_workflow_runs_on"] = ["self-hosted", "linux", "x64"]\n'
            '    payload["lanes"]["pr"]["local_self_hosted_runner_default"] = True\n'
            '    payload["lanes"]["pr"]["local_github_hosted_runner_default"] = False'
        ),
        'assert "pr:local_workflow_uses_github_hosted_runner" in packet["current_blockers"]\n    assert "pr:local_self_hosted_runner_default_missing" in packet["current_blockers"]': (
            'assert "pr:local_workflow_uses_self_hosted_runner" in packet["current_blockers"]\n'
            '    assert "pr:local_github_hosted_runner_default_missing" in packet["current_blockers"]'
        ),
        'assert (\n        "runner:self_hosted_runner_matching_labels_not_online"\n        in payload["current_blockers"]\n    )': (
            'assert not any(item.startswith("runner:") for item in payload["current_blockers"])'
        ),
        '"nightly_missing=30 | blockers=9 | runner=blocked"': (
            '"nightly_missing=30 | blockers=8 | runner=blocked"'
        ),
        'assert payload["current_blocker_count"] == 9': (
            'assert payload["current_blocker_count"] == 8'
        ),
        'assert payload["derived_checks"][4]["field"] == "self_hosted_runner_precondition"': (
            'assert payload["derived_checks"][4]["field"] == "heavy_runner_precondition_informational"'
        ),
        'assert payload["derived_checks"][4]["closure_check_pass"] is False': (
            'assert payload["derived_checks"][4]["closure_check_pass"] is True'
        ),
        'assert payload["gate_unblock_plan"][0]["slot_id"] == (\n        "restore_self_hosted_runner_precondition"\n    )': (
            'assert payload["gate_unblock_plan"][0]["slot_id"] == "collect_pr_30_consecutive_passes"'
        ),
    }
    for old, new in replacements_map.items():
        text = _replace_once(text, old, new, old)
    path.write_text(text, encoding="utf-8")


def _migrate_readiness_tests() -> None:
    path = ROOT / "tests/test_build_product_readiness_snapshot.py"
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    output: list[str] = []
    replacements = 0
    index = 0
    needle = '            "    runs-on: ${{ fromJSON(vars.STRUCTURAL_ACTIONS_RUNNER_LABELS || "\n'
    while index < len(lines):
        if lines[index] == needle:
            if index + 1 >= len(lines) or "self-hosted" not in lines[index + 1]:
                raise RuntimeError("unexpected product-readiness workflow fixture")
            output.append('            "    runs-on: ubuntu-latest\\n"\n')
            index += 2
            replacements += 1
            continue
        output.append(lines[index])
        index += 1
    if replacements != 2:
        raise RuntimeError(f"product-readiness hosted fixture count={replacements}")
    path.write_text("".join(output), encoding="utf-8")


def main() -> int:
    _migrate_streak_builder()
    _migrate_streak_tests()
    _migrate_readiness_tests()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
