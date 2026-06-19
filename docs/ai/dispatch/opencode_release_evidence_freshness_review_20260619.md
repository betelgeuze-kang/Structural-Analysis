# OpenCode Slice: Release Evidence Freshness Gate Review

## Goal

Review and, if needed, minimally fix the new release evidence freshness gate before Codex commits it.

## Scope

- `scripts/report_release_evidence_freshness.py`
- `scripts/report_pm_release_gate.py`
- `tests/test_report_release_evidence_freshness.py`
- `tests/test_report_pm_release_gate.py`
- Generated productization freshness/PM gate reports only if rerun is required.

## Context

The gate should make stale or reused release evidence visible. It must not promote readiness. Missing source commit, engine version, input checksum, generated_at, reuse marker, or producer-newer-than-artifact evidence must block the new `evidence_freshness` release area.

## Verification

Run:

```bash
python3 -m pytest -q tests/test_report_release_evidence_freshness.py tests/test_report_pm_release_gate.py
```

If the report generator changes, also run:

```bash
python3 scripts/report_release_evidence_freshness.py
python3 scripts/report_pm_release_gate.py
```

## Output Rules

Return only:

- changed files
- test commands and pass/fail result
- failing test names, if any
- concise diff summary
- blockers

Do not include full logs or full JSON/Markdown evidence bodies.
