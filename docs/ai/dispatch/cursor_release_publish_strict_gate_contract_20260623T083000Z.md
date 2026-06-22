Goal: Review the release-publish workflow strict release gate contract.

Scope:
- Inspect `.github/workflows/release-publish.yml`.
- Inspect `tests/test_release_publish_workflow.py`.
- Inspect `scripts/verify_quality_gate.py` only if needed.

Question:
- Does the workflow guarantee `python scripts/verify_quality_gate.py --mode release` must succeed before `scripts/publish_github_release_assets.py` can run?
- Are there missing regression assertions around `if: always()`, `continue-on-error`, or `|| true` on the strict gate/publish/promotion path?

Expected output:
- Recommend minimal test-only changes if the workflow is already correct.
- Do not modify release behavior unless a real bypass is found.
- Do not run or dispatch any workflow, publish assets, push, or mutate remotes.
