from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = (
    REPO_ROOT
    / "implementation"
    / "phase1"
    / "release_evidence"
    / "productization"
    / "product_readiness_snapshot.json"
)
DEVELOPER_PREVIEW = (
    REPO_ROOT
    / "implementation"
    / "phase1"
    / "release_evidence"
    / "productization"
    / "developer_preview_readiness.json"
)
DEVELOPER_PREVIEW_REPORT = DEVELOPER_PREVIEW.with_suffix(".md")
DEVELOPER_PREVIEW_RC = (
    REPO_ROOT
    / "implementation"
    / "phase1"
    / "release_evidence"
    / "productization"
    / "developer_preview_rc_status.json"
)
DEVELOPER_PREVIEW_RC_REPORT = DEVELOPER_PREVIEW_RC.with_suffix(".md")
INDEPENDENT_PRODUCT = (
    REPO_ROOT / "implementation" / "phase1" / "release" / "independent_product_readiness.json"
)
PM_BLOCKER_REGISTER = (
    REPO_ROOT
    / "implementation"
    / "phase1"
    / "release_evidence"
    / "productization"
    / "pm_release_blocker_action_register.json"
)
FRESHNESS_REPORT = (
    REPO_ROOT
    / "implementation"
    / "phase1"
    / "release_evidence"
    / "productization"
    / "release_evidence_freshness_report.json"
)
DOCS = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "commercialization-gap-current-state.md",
]
APP = REPO_ROOT / "src" / "App.tsx"


def test_readiness_snapshot_summary_is_doc_synced() -> None:
    payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    categories = payload["blocker_categories"]
    expected = (
        "Canonical product readiness snapshot: "
        f"status `{payload['status']}`, "
        f"blocker_count `{payload['blocker_count']}`, "
        f"paid_pilot_ready=`{str(payload['paid_pilot_ready']).lower()}`, "
        f"release_ready=`{str(payload['release_ready']).lower()}`"
    )
    expected_categories = (
        "Canonical blocker categories: "
        f"numerical `{categories['numerical']['blocker_count']}`, "
        f"benchmark `{categories['benchmark']['blocker_count']}`, "
        f"software product `{categories['software product']['blocker_count']}`, "
        f"future commercial `{categories['future commercial']['blocker_count']}`"
    )

    for path in DOCS:
        text = path.read_text(encoding="utf-8")
        assert expected in text, path
        assert expected_categories in text, path
        assert "build_product_readiness_snapshot.py --json --no-write" in text, path


def test_developer_preview_readiness_summary_is_doc_synced() -> None:
    payload = json.loads(DEVELOPER_PREVIEW.read_text(encoding="utf-8"))
    categories = payload["categories"]
    scope = payload["scope"]
    freeze_policy = scope["freeze_policy"]
    scope_boundary_sync = payload["scope_boundary_sync"]
    expected_fragments = [
        "Open Benchmark Developer Preview readiness:",
        "developer_preview_readiness.json",
        "developer_preview_readiness.md",
        f"developer_preview_ready=`{str(payload['developer_preview_ready']).lower()}`",
        f"blocker_count `{payload['blocker_count']}`",
        f"future_commercial_blocker_count `{payload['future_commercial_blocker_count']}`",
        f"numerical `{categories['numerical']['blocker_count']}`",
        f"benchmark `{categories['benchmark']['blocker_count']}`",
        f"software product `{categories['software product']['blocker_count']}`",
        f"new feature freeze `{freeze_policy['new_feature_development']}`",
        f"AI training freeze `{freeze_policy['ai_training']}`",
        f"GPU/HIP track `{freeze_policy['gpu_hip']}`",
    ]
    commercial_exclusions = [
        "customer shadow",
        "license approval",
        "commercial SLA",
        "30-run CI streak",
        "external approval receipt",
    ]
    ai_freeze_boundary = [
        "AI/GNN/surrogate truth",
        "deterministic reference solver",
        "residual/Jacobian/Newton closure",
        "benchmark truth",
    ]

    for path in DOCS:
        text = path.read_text(encoding="utf-8")
        for fragment in expected_fragments:
            assert fragment in text, (path, fragment)
        for fragment in commercial_exclusions:
            assert fragment in text, (path, fragment)
        for fragment in ai_freeze_boundary:
            assert fragment in text, (path, fragment)

    report = DEVELOPER_PREVIEW_REPORT.read_text(encoding="utf-8")
    assert "# Open Benchmark Developer Preview Readiness" in report
    assert "## Included Scope" in report
    assert "## Excluded Scope" in report
    assert "## Freeze Policy" in report
    assert "| future commercial |" in report
    for key, value in freeze_policy.items():
        assert f"`{key}`: `{value}`" in report
    for fragment in scope["included"]:
        assert fragment in report, fragment
    for fragment in scope["excluded"]:
        assert fragment in report, fragment
    for fragment in ai_freeze_boundary:
        assert fragment in report, fragment

    app = APP.read_text(encoding="utf-8")
    gui_scope_contract = [
        "function buildDeveloperPreviewSnapshot",
        "getRecord(resource.data, 'scope')",
        "getArray(scope, 'included')",
        "getArray(scope, 'excluded')",
        "scope=${scopeSummary}",
        "excludes=${exclusionSummary}",
        "customer shadow, license/legal approval, commercial SLA, 30-run CI streak, and external approval receipts remain Commercial Release blockers",
    ]
    for fragment in gui_scope_contract:
        assert fragment in app, fragment
    assert scope_boundary_sync["status"] == "ready"
    assert scope_boundary_sync["contract_pass"] is True
    assert scope_boundary_sync["gui_surface"]["contract_pass"] is True
    for surface in scope_boundary_sync["doc_surfaces"].values():
        assert surface["contract_pass"] is True


def test_developer_preview_rc_status_summary_is_doc_synced() -> None:
    payload = json.loads(DEVELOPER_PREVIEW_RC.read_text(encoding="utf-8"))
    blocked_final_gates = [
        gate["item"] for gate in payload["final_gates"] if not gate["contract_pass"]
    ]
    expected_gate_labels = {
        "selected_medium_models_pass_or_approved_review": "selected medium models",
        "large_models_crash_oom_free": "large crash/OOM-free execution",
        "silent_import_loss_zero": "silent import loss zero",
        "linux_windows_reproducibility_confirmed": "Linux/Windows reproducibility",
        "new_user_core_workflow_observation_passed": "human new-user workflow observation",
        "benchmark_results_clean_checkout_regenerated": "git clean-clone benchmark regeneration",
    }
    expected_fragments = [
        "Developer Preview RC status:",
        "developer_preview_rc_status.json",
        "developer_preview_rc_status.md",
        f"status `{payload['status']}`",
        f"deliverables `{payload['deliverable_pass_count']}/{payload['deliverable_count']}`",
        f"final gates `{payload['final_gate_pass_count']}/{payload['final_gate_count']}`",
        "full Phase 3",
        "G1 full nonlinear full-mesh/material Newton",
        "Linux/Windows parity",
        "human new-user workflow observation",
        "clean-clone",
    ]

    for path in DOCS:
        text = path.read_text(encoding="utf-8")
        for fragment in expected_fragments:
            assert fragment in text, (path, fragment)
        for item in blocked_final_gates:
            assert expected_gate_labels[item] in text, (path, item)

    report = DEVELOPER_PREVIEW_RC_REPORT.read_text(encoding="utf-8")
    assert "# Developer Preview RC Status" in report
    assert "## Deliverables" in report
    assert "## Final Gates" in report
    assert "## Blockers" in report
    assert "## Claim Boundary" in report
    for item in blocked_final_gates:
        assert item in report, item
    for blocker in payload["blockers"]:
        assert blocker in report, blocker


def test_docs_do_not_claim_github_sync_complete_while_snapshot_blocks() -> None:
    payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    github_sync_blocked = any(
        str(blocker).startswith("pm_release::github_sync::")
        for blocker in payload["blockers"]
    )
    if not github_sync_blocked:
        return

    forbidden = "GitHub development sync is complete"
    for path in DOCS:
        text = path.read_text(encoding="utf-8")
        assert forbidden not in text, path


def test_readme_independent_product_score_matches_receipt() -> None:
    payload = json.loads(INDEPENDENT_PRODUCT.read_text(encoding="utf-8"))
    expected = (
        "Independent commercial product status:"
        " `python3 scripts/check_independent_product_readiness.py --json`"
    )
    expected_score = (
        f"Current status is {payload['status']} at "
        f"`{payload['readiness_score']}/100`"
    )
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert expected in readme
    assert expected_score in readme


def test_docs_pm_release_area_and_handoff_counts_match_register() -> None:
    payload = json.loads(PM_BLOCKER_REGISTER.read_text(encoding="utf-8"))
    summary = payload["summary"]
    green = int(summary["release_area_green_count"])
    total = int(summary["release_area_total_count"])
    open_count = int(summary["open_blocker_count"])
    release_area_count = int(summary["release_area_blocker_count"])
    fresh_count = int(summary["local_remediation_ready_count"])
    external_customer_count = open_count - release_area_count - fresh_count
    expected_fragments = [
        f"{green}/{total}",
        f"`{open_count}`",
        f"`{release_area_count}`",
        f"`{external_customer_count}`",
        f"`{fresh_count}`",
    ]

    for path in DOCS:
        text = path.read_text(encoding="utf-8")
        for fragment in expected_fragments:
            assert fragment in text, (path, fragment)


def test_docs_release_evidence_freshness_summary_matches_report() -> None:
    payload = json.loads(FRESHNESS_REPORT.read_text(encoding="utf-8"))
    summary = payload["summary"]
    expected_fragments = [
        "report_release_evidence_freshness.py",
        "developer_preview_rc_status.json",
        f"`{summary['pass_count']}/{summary['artifact_count']}`",
        "Developer Preview RC final gates",
    ]

    for path in DOCS:
        text = path.read_text(encoding="utf-8")
        for fragment in expected_fragments:
            assert fragment in text, (path, fragment)


def test_docs_describe_release_mode_as_non_mutating_checks() -> None:
    required_fragments = [
        "check_github_actions_self_hosted_runner_status.py",
        "--check --fail-blocked",
        "build_product_readiness_snapshot.py",
        "without rewriting tracked evidence",
    ]
    runner_query_failure_fragments = [
        "query failure remains a blocker",
        "query failure는 blocker로 남기며",
    ]
    query_error_override_fragments = [
        "--write-query-error-evidence",
    ]
    forbidden_fragments = [
        "Release mode refreshes that self-hosted runner status",
        "refreshes self-hosted runner status, rebuilds the canonical product readiness snapshot",
        "self-hosted runner 상태를 다시 수집",
    ]

    for path in DOCS:
        text = path.read_text(encoding="utf-8")
        for fragment in required_fragments[:3]:
            assert fragment in text, (path, fragment)
        assert (
            required_fragments[3] in text
            or "재작성하지 않고 `--check`로 검증" in text
        ), path
        assert any(fragment in text for fragment in runner_query_failure_fragments), path
        assert any(fragment in text for fragment in query_error_override_fragments), path
        for fragment in forbidden_fragments:
            assert fragment not in text, (path, fragment)
