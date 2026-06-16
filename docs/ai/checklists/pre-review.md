# Pre-review Checklist

- [ ] Active Codex goal is clear.
- [ ] Diff is scoped to the goal.
- [ ] Delegated TASK, if any, used only goal, scope, candidate files, and verification criteria.
- [ ] Worker output, if any, is limited to changed files, test results, failed tests, core diff summary, and blockers.
- [ ] Worker output validator passed before Codex consumed the summary.
- [ ] `./scripts/ai-verify.sh` has been run.
- [ ] Relevant readiness/status gates have been run when product evidence changed.
- [ ] Codex inspected only targeted files, named failing tests, or relevant diffs unless a blocker required more.
- [ ] No forbidden external state mutation was executed.
