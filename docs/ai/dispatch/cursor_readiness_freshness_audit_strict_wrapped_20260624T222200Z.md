Goal: Audit the current readiness freshness refresh after commit 78e9ac22.

Scope:
- Inspect only current local files and command output.
- Do not push, merge, publish, or mutate remote state.
- Do not promote any readiness status.
- Do not edit files.

Verification criteria:
- Run or inspect: python3 scripts/report_release_evidence_freshness.py --out /tmp/worker_release_evidence_freshness_wrapped.json --out-md /tmp/worker_release_evidence_freshness_wrapped.md
- Confirm whether freshness blockers are zero.
- Confirm Developer Preview remains blocked.
- Confirm customer shadow, license server, and commercial SLA are not Developer Preview blockers.
- Confirm non-closing G1 evidence remains non-promoting.

Output format is mandatory:
- Use exactly these five headings, in this exact order:
  Changed files
  Test results
  Failed tests
  Core diff summary
  Blockers
- Put at least one concise value under every heading.
- Keep every output line under 250 characters.
- Use short bullet lines if needed.
- Do not include fenced code blocks.
- Do not include full diffs.
- Do not include any extra heading or prose before Changed files.
