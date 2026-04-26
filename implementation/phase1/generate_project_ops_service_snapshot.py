#!/usr/bin/env python3
"""Generate a release-consumable project ops service snapshot."""

from __future__ import annotations

import argparse
from pathlib import Path

try:
    from implementation.phase1.project_ops_api_service import (
        DEFAULT_PROJECT_OPS_SNAPSHOT_OUT,
        DEFAULT_RELEASE_ROOT,
        DEFAULT_SNAPSHOT_MANIFEST_GLOB,
        write_project_ops_snapshot,
    )
except ImportError:  # pragma: no cover
    from project_ops_api_service import (  # type: ignore
        DEFAULT_PROJECT_OPS_SNAPSHOT_OUT,
        DEFAULT_RELEASE_ROOT,
        DEFAULT_SNAPSHOT_MANIFEST_GLOB,
        write_project_ops_snapshot,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-root", default=str(DEFAULT_RELEASE_ROOT))
    parser.add_argument("--portfolio-json", default="")
    parser.add_argument("--registry-index-json", default="")
    parser.add_argument("--portfolio-batch-json", default="")
    parser.add_argument("--runtime-submission-json", default="")
    parser.add_argument("--runtime-writeback-depth-json", default="")
    parser.add_argument("--multi-project-runtime-writeback-json", default="")
    parser.add_argument("--solver-family-breadth-json", default="")
    parser.add_argument("--local-runtime-scenario-depth-json", default="")
    parser.add_argument("--release-registry-json", default="")
    parser.add_argument("--committee-summary-json", default="")
    parser.add_argument("--release-gap-report-json", default="")
    parser.add_argument("--snapshot-manifest-glob", default=DEFAULT_SNAPSHOT_MANIFEST_GLOB)
    parser.add_argument("--project-registry-paths", default="")
    parser.add_argument("--project-registry-dirs", default="")
    parser.add_argument("--generated-at", default="")
    parser.add_argument("--out", default=str(DEFAULT_PROJECT_OPS_SNAPSHOT_OUT))
    args = parser.parse_args()

    project_registry_paths = [Path(item.strip()) for item in str(args.project_registry_paths).split(",") if item.strip()]
    project_registry_dirs = [Path(item.strip()) for item in str(args.project_registry_dirs).split(",") if item.strip()]

    payload = write_project_ops_snapshot(
        Path(args.out),
        release_root=Path(args.release_root),
        portfolio_json_path=Path(args.portfolio_json) if str(args.portfolio_json).strip() else None,
        registry_index_json_path=Path(args.registry_index_json) if str(args.registry_index_json).strip() else None,
        portfolio_batch_json_path=Path(args.portfolio_batch_json) if str(args.portfolio_batch_json).strip() else None,
        runtime_submission_json_path=(
            Path(args.runtime_submission_json) if str(args.runtime_submission_json).strip() else None
        ),
        runtime_writeback_depth_json_path=(
            Path(args.runtime_writeback_depth_json) if str(args.runtime_writeback_depth_json).strip() else None
        ),
        multi_project_runtime_writeback_json_path=(
            Path(args.multi_project_runtime_writeback_json)
            if str(args.multi_project_runtime_writeback_json).strip()
            else None
        ),
        solver_family_breadth_json_path=(
            Path(args.solver_family_breadth_json) if str(args.solver_family_breadth_json).strip() else None
        ),
        local_runtime_scenario_depth_json_path=(
            Path(args.local_runtime_scenario_depth_json)
            if str(args.local_runtime_scenario_depth_json).strip()
            else None
        ),
        release_registry_json_path=Path(args.release_registry_json) if str(args.release_registry_json).strip() else None,
        committee_summary_json_path=Path(args.committee_summary_json) if str(args.committee_summary_json).strip() else None,
        release_gap_report_json_path=Path(args.release_gap_report_json) if str(args.release_gap_report_json).strip() else None,
        snapshot_manifest_glob=str(args.snapshot_manifest_glob).strip() or DEFAULT_SNAPSHOT_MANIFEST_GLOB,
        project_registry_paths=project_registry_paths,
        project_registry_dirs=project_registry_dirs,
        generated_at=str(args.generated_at).strip() or None,
    )
    print(payload["summary_line"])
    if not payload["contract_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
