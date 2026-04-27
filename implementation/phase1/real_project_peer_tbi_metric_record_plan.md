# PEER TBI Metric Records And Real-Project Row Provenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split P1-2 `PEER TBI Benchmark Metric Record` and P1-3 `Real-Project Row Provenance` into executable tasks that preserve the P0 legal-provenance gate as the upstream hard gate.

**Architecture:** Treat PEER TBI as a citation-first benchmark family and treat row provenance as a derived audit report over already-reviewed source/artifact rows. P1 work may emit benchmark metrics, provenance metadata, checksums, and report surfaces, but it must never promote raw KONEPS attachments or PEER raw model bundles past the P0 gate.

**Tech Stack:** Python CLI tools under `implementation/phase1`, JSON/JSON Schema-style contract validation, pytest contract tests, existing benchmark/report/viewer generators, and the current seed manifest plus parser coverage matrix.

---

## Non-Negotiable P0 Gate

P0 remains the upstream hard gate for P1-2 and P1-3. Do not weaken this rule in implementation, tests, release packaging, or viewer/report surfacing.

- PEER TBI remains a citation-first benchmark family. The durable P1 artifact is the citation-backed metric record, not a redistributed raw model, archive, input deck, or companion file.
- Raw model redistribution is prohibited by default. Every PEER TBI metric record must carry `redistribution_allowed=false` unless a separate future per-document legal review creates a reviewed artifact row; this plan does not create that exception.
- P0 remains the upstream hard gate even when PEER source material is public. Public report access may support citation and locator extraction, but it does not grant raw redistribution rights.
- P0 remains the upstream hard gate for every promoted row. A parsed row without source family, artifact identity, checksum or checksum-withheld reason, file inventory pointer, parser identity, row pointer, and access policy cannot move beyond candidate status.
- P0 remains the upstream hard gate for release/viewer/report paths. Metadata-only display is allowed; raw restricted, unknown, redacted, or non-reviewed payload exposure is not allowed.

## Source Inputs

Implementation must read these inputs first and fail closed if their contracts are missing:

- `implementation/phase1/real_project_corpus_seed_manifest.json`
- `implementation/phase1/real_project_parser_coverage_matrix.json`
- `docs/real-project-corpus.md`
- `implementation/phase1/real_project_corpus_p1_p2_closeout_plan.md`

Current source-family assumptions to preserve:

- `peer_tbi_tall_buildings` has `access_policy.redistribution_allowed=false` and `access_policy.requires_manual_review=true`.
- `real_project_parser_coverage_matrix.json` lists the required PEER metric groups as `period`, `base_shear`, `story_drift`, `nonlinear_response`, and `citation`.
- `raw_redistribution_auto_allowed_after_p0=false` means P0 closeout still does not grant raw redistribution automatically.

## P1-2 PEER TBI Benchmark Metric Record

**Exit Gate:** PEER TBI candidates report citation-backed benchmark metric records for `period`, `base_shear`, `story_drift`, `nonlinear_response`, and `citation` before any raw model redistribution is considered.

**Implementation File Candidates:**

- Create `implementation/phase1/build_peer_tbi_benchmark_metric_records.py`.
- Output `implementation/phase1/peer_tbi_benchmark_metric_records.json`.
- Optionally add schema/contract constants inside the builder first; only create a separate `implementation/phase1/peer_tbi_benchmark_metric_records.schema.json` if the report is reused by multiple downstream validators.
- Reuse patterns from `implementation/phase1/generate_external_benchmark_kickoff_package.py`, `implementation/phase1/run_real_accuracy_validation.py`, and `implementation/phase1/run_peer_blind_prediction_compare_report.py`.
- Surface records later through `implementation/phase1/generate_external_benchmark_kickoff_package.py` or benchmark compare reports only as citation-backed metric rows, not raw redistributed bundles.

**Required Metric Groups:**

- `period`
- `base_shear`
- `story_drift`
- `nonlinear_response`
- `citation`

**Required Record Fields:**

Every row in `metric_records` must include these exact fields:

- `source_id`
- `official_url`
- `citation`
- `report_id`
- `metric_group`
- `metric_name`
- `value`
- `status`
- `unit`
- `locator`
- `benchmark_status`
- `redistribution_allowed`

`locator` must be an object with page/table/figure evidence where available:

```json
{
  "page": "p. 12",
  "table": "Table 3",
  "figure": "Figure 5"
}
```

Use `value=null` and `status="not_available"` when a metric is citation-confirmed but not numerically available. Use `status="recorded"` only when the value and locator are both present. Use `benchmark_status="citation_metric_recorded"` for complete citation-backed rows and `benchmark_status="raw_review_required"` when the row points to raw material that still needs per-document review.

Minimum output shape:

```json
{
  "schema_version": "peer_tbi_benchmark_metric_records.v1",
  "source_manifest_schema_version": "real_project_corpus_manifest.v1",
  "source_id": "peer_tbi_tall_buildings",
  "contract_pass": true,
  "reason_code": "PASS",
  "raw_redistribution_default": false,
  "p0_upstream_hard_gate": true,
  "required_metric_groups": [
    "period",
    "base_shear",
    "story_drift",
    "nonlinear_response",
    "citation"
  ],
  "metric_records": [
    {
      "source_id": "peer_tbi_tall_buildings",
      "official_url": "https://peer.berkeley.edu/research/building-systems/tall-buildings-initiative",
      "citation": "PEER Tall Buildings Initiative report citation text",
      "report_id": "peer_tbi_report_identifier",
      "metric_group": "period",
      "metric_name": "fundamental_period",
      "value": null,
      "status": "not_available",
      "unit": "s",
      "locator": {
        "page": "p. n/a",
        "table": "",
        "figure": ""
      },
      "benchmark_status": "citation_metric_recorded",
      "redistribution_allowed": false
    }
  ],
  "summary": {
    "required_metric_group_count": 5,
    "recorded_metric_group_count": 5,
    "redistribution_allowed_record_count": 0
  }
}
```

### Task 1: Write PEER Metric Contract Tests

**Files:**

- Create: `tests/test_build_peer_tbi_benchmark_metric_records.py`
- Future implementation target: `implementation/phase1/build_peer_tbi_benchmark_metric_records.py`
- Future output target: `implementation/phase1/peer_tbi_benchmark_metric_records.json`

- [ ] **Step 1: Add a fixture-driven test for required metric groups and fields.**

```python
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILDER = REPO_ROOT / "implementation/phase1/build_peer_tbi_benchmark_metric_records.py"
SEED_MANIFEST = REPO_ROOT / "implementation/phase1/real_project_corpus_seed_manifest.json"
COVERAGE_MATRIX = REPO_ROOT / "implementation/phase1/real_project_parser_coverage_matrix.json"

REQUIRED_GROUPS = {"period", "base_shear", "story_drift", "nonlinear_response", "citation"}
REQUIRED_FIELDS = {
    "source_id",
    "official_url",
    "citation",
    "report_id",
    "metric_group",
    "metric_name",
    "value",
    "status",
    "unit",
    "locator",
    "benchmark_status",
    "redistribution_allowed",
}


def test_peer_tbi_metric_records_are_citation_first_and_nonredistributable(tmp_path: Path) -> None:
    out = tmp_path / "peer_tbi_benchmark_metric_records.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(BUILDER),
            "--manifest",
            str(SEED_MANIFEST),
            "--coverage-matrix",
            str(COVERAGE_MATRIX),
            "--out",
            str(out),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["p0_upstream_hard_gate"] is True
    assert payload["raw_redistribution_default"] is False
    assert set(payload["required_metric_groups"]) == REQUIRED_GROUPS

    records = payload["metric_records"]
    assert records
    assert {row["metric_group"] for row in records} >= REQUIRED_GROUPS

    for row in records:
        assert REQUIRED_FIELDS <= set(row)
        assert row["source_id"] == "peer_tbi_tall_buildings"
        assert row["official_url"].startswith("https://")
        assert row["citation"].strip()
        assert row["report_id"].strip()
        assert row["metric_group"] in REQUIRED_GROUPS
        assert row["status"] in {"recorded", "not_available", "raw_review_required"}
        assert isinstance(row["locator"], dict)
        assert {"page", "table", "figure"} <= set(row["locator"])
        assert row["benchmark_status"] in {"citation_metric_recorded", "raw_review_required"}
        assert row["redistribution_allowed"] is False

    assert payload["summary"]["redistribution_allowed_record_count"] == 0
```

- [ ] **Step 2: Run the failing test before implementation.**

Run:

```bash
python3 -m pytest -q tests/test_build_peer_tbi_benchmark_metric_records.py
```

Expected before the builder exists: FAIL because `implementation/phase1/build_peer_tbi_benchmark_metric_records.py` is missing.

### Task 2: Implement The PEER Metric Builder

**Files:**

- Create: `implementation/phase1/build_peer_tbi_benchmark_metric_records.py`
- Read: `implementation/phase1/real_project_corpus_seed_manifest.json`
- Read: `implementation/phase1/real_project_parser_coverage_matrix.json`
- Write: `implementation/phase1/peer_tbi_benchmark_metric_records.json`

- [ ] **Step 1: Build a CLI that validates the PEER source family and metric groups.**

Implementation rules:

- Load the seed manifest and require `peer_tbi_tall_buildings`.
- Require `access_policy.redistribution_allowed` to be `false`; fail non-zero if the source family is missing or redistribution is true.
- Load `real_project_parser_coverage_matrix.json` and require the five metric groups exactly: `period`, `base_shear`, `story_drift`, `nonlinear_response`, and `citation`.
- Emit rows as source-family seed citation metric records when only the official source-family evidence exists; do not download raw PEER models.
- Set `redistribution_allowed=false` on every metric row.
- Set `p0_upstream_hard_gate=true` in the output.

Suggested implementation skeleton:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


REQUIRED_GROUPS = ["period", "base_shear", "story_drift", "nonlinear_response", "citation"]
SOURCE_ID = "peer_tbi_tall_buildings"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_records(manifest: dict[str, Any], coverage_matrix: dict[str, Any]) -> dict[str, Any]:
    sources = {
        str(row.get("source_id", "") or ""): row
        for row in manifest.get("source_families", [])
        if isinstance(row, dict)
    }
    source = sources.get(SOURCE_ID)
    if not source:
        raise ValueError(f"missing source family: {SOURCE_ID}")

    access = source.get("access_policy") if isinstance(source.get("access_policy"), dict) else {}
    if bool(access.get("redistribution_allowed", False)):
        raise ValueError("PEER TBI raw redistribution must default to false")

    matrix_rows = [
        row for row in coverage_matrix.get("source_rows", [])
        if isinstance(row, dict) and row.get("source_id") == SOURCE_ID
    ]
    matrix_metrics = {
        str(item.get("metric", "") or "")
        for row in matrix_rows
        for item in row.get("benchmark_metric_targets", [])
        if isinstance(item, dict)
    }
    missing = sorted(set(REQUIRED_GROUPS) - matrix_metrics)
    if missing:
        raise ValueError(f"missing PEER TBI metric groups in coverage matrix: {missing}")

    official_url = str(source.get("official_entrypoint_url", "") or "")
    citation = "PEER Tall Buildings Initiative, Pacific Earthquake Engineering Research Center, University of California, Berkeley; source-family seed citation record."
    records = []
    for group in REQUIRED_GROUPS:
        records.append(
            {
                "source_id": SOURCE_ID,
                "official_url": official_url,
                "citation": citation,
                "report_id": "peer_tbi_source_family_seed",
                "metric_group": group,
                "metric_name": group,
                "value": None,
                "status": "not_available" if group != "citation" else "recorded",
                "unit": "reference" if group == "citation" else "",
                "locator": {"page": "source family entrypoint", "table": "", "figure": ""},
                "benchmark_status": "citation_metric_recorded",
                "redistribution_allowed": False,
            }
        )

    return {
        "schema_version": "peer_tbi_benchmark_metric_records.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_manifest_schema_version": str(manifest.get("schema_version", "") or ""),
        "source_id": SOURCE_ID,
        "contract_pass": True,
        "reason_code": "PASS",
        "raw_redistribution_default": False,
        "p0_upstream_hard_gate": True,
        "required_metric_groups": REQUIRED_GROUPS,
        "metric_records": records,
        "summary": {
            "required_metric_group_count": len(REQUIRED_GROUPS),
            "recorded_metric_group_count": len({row["metric_group"] for row in records}),
            "redistribution_allowed_record_count": sum(
                1 for row in records if bool(row.get("redistribution_allowed", False))
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--coverage-matrix", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    try:
        payload = build_records(_load_json(args.manifest), _load_json(args.coverage_matrix))
    except Exception as exc:
        print(f"PEER TBI metric record build failed: {exc}")
        return 1
    _write_json(args.out, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run tests and inspect the output.**

Run:

```bash
python3 -m pytest -q tests/test_build_peer_tbi_benchmark_metric_records.py
python3 implementation/phase1/build_peer_tbi_benchmark_metric_records.py \
  --manifest implementation/phase1/real_project_corpus_seed_manifest.json \
  --coverage-matrix implementation/phase1/real_project_parser_coverage_matrix.json \
  --out implementation/phase1/peer_tbi_benchmark_metric_records.json
```

Expected: tests PASS, output contains five metric groups, and every metric row has `redistribution_allowed=false`.

**P1-2 Pass/Fail Metric:**

- PASS if all five metric groups are present: `period`, `base_shear`, `story_drift`, `nonlinear_response`, and `citation`.
- PASS if every metric record includes `source_id`, `official_url`, `citation`, `report_id`, `metric_group`, `metric_name`, `value`, `status`, `unit`, `locator`, `benchmark_status`, and `redistribution_allowed=false`.
- PASS if `benchmark_status` is one of `citation_metric_recorded` or `raw_review_required`, and raw review rows still do not allow redistribution.
- PASS if P0 remains the upstream hard gate in output summary fields and tests.
- FAIL if any PEER raw model/archive/input deck is packaged, linked as a downloadable release artifact, or marked redistributable without a separate artifact-level review.
- FAIL if any metric is used without citation and page/table/figure locator evidence or an explicit `not_available` status.

## P1-3 Real-Project Row Provenance

**Exit Gate:** Every parsed real-project row promoted beyond candidate status carries row-level provenance from source family to artifact, file inventory member, parser identity, row pointer, and access policy.

**Implementation File Candidates:**

- Create `implementation/phase1/build_real_project_row_provenance_report.py`.
- Output `implementation/phase1/real_project_row_provenance_report.json`.
- Extend `implementation/phase1/generate_midas_native_corpus_manifest.py` only when real-project rows are ready to carry the same required fields at source emission time.
- Surface row provenance later in `implementation/phase1/generate_structure_viewer_payloads.py` and `implementation/phase1/generate_release_gap_report.py` as metadata labels only; do not expose restricted raw payloads.

**Required Row Provenance Fields:**

Every promoted row must include these exact fields:

- `artifact_id`
- `source_id`
- `artifact_sha256`
- `checksum_withheld_reason`
- `file_inventory_path`
- `parser_name`
- `parser_version`
- `row_pointer`
- `access_policy`

At least one of `artifact_sha256` or `checksum_withheld_reason` must be non-empty. If checksum is withheld, `checksum_withheld_reason` must be explicit, for example `restricted_artifact_checksum_withheld_by_policy`. The `access_policy` object must include `classification`, `redistribution_allowed`, and `requires_manual_review`.

Minimum output shape:

```json
{
  "schema_version": "real_project_row_provenance_report.v1",
  "source_manifest_schema_version": "real_project_corpus_manifest.v1",
  "contract_pass": true,
  "reason_code": "PASS",
  "p0_upstream_hard_gate": true,
  "row_provenance_coverage": 1.0,
  "rows": [
    {
      "artifact_id": "artifact-id",
      "source_id": "koneps_turnkey_design_docs",
      "artifact_sha256": "",
      "checksum_withheld_reason": "restricted_artifact_checksum_withheld_by_policy",
      "file_inventory_path": "inventory/member/path",
      "parser_name": "parser-name",
      "parser_version": "parser-version",
      "row_pointer": "MGT:TABLE=NODE:ROW=1",
      "access_policy": {
        "classification": "unknown",
        "redistribution_allowed": false,
        "requires_manual_review": true
      }
    }
  ],
  "summary": {
    "promoted_row_count": 1,
    "complete_provenance_row_count": 1,
    "missing_provenance_row_count": 0,
    "redistribution_allowed_row_count": 0
  }
}
```

### Task 3: Write Row Provenance Contract Tests

**Files:**

- Create: `tests/test_build_real_project_row_provenance_report.py`
- Future implementation target: `implementation/phase1/build_real_project_row_provenance_report.py`
- Future output target: `implementation/phase1/real_project_row_provenance_report.json`

- [ ] **Step 1: Add tests for complete row provenance and fail-closed checksum handling.**

```python
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILDER = REPO_ROOT / "implementation/phase1/build_real_project_row_provenance_report.py"
SEED_MANIFEST = REPO_ROOT / "implementation/phase1/real_project_corpus_seed_manifest.json"

REQUIRED_FIELDS = {
    "artifact_id",
    "source_id",
    "artifact_sha256",
    "checksum_withheld_reason",
    "file_inventory_path",
    "parser_name",
    "parser_version",
    "row_pointer",
    "access_policy",
}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_row_provenance_report_requires_artifact_parser_and_row_pointer(tmp_path: Path) -> None:
    rows = tmp_path / "parsed_rows.json"
    out = tmp_path / "real_project_row_provenance_report.json"
    _write_json(
        rows,
        {
            "rows": [
                {
                    "promotion_status": "promoted",
                    "artifact_id": "artifact-001",
                    "source_id": "peer_tbi_tall_buildings",
                    "artifact_sha256": "a" * 64,
                    "checksum_withheld_reason": "",
                    "file_inventory_path": "reports/peer-tbi-report.pdf",
                    "parser_name": "peer_tbi_metric_parser",
                    "parser_version": "1.0",
                    "row_pointer": "PDF:p.12:Table 3:row 1",
                    "access_policy": {
                        "classification": "public",
                        "redistribution_allowed": False,
                        "requires_manual_review": True,
                    },
                }
            ]
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(BUILDER),
            "--manifest",
            str(SEED_MANIFEST),
            "--parsed-rows",
            str(rows),
            "--out",
            str(out),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["p0_upstream_hard_gate"] is True
    assert payload["row_provenance_coverage"] == 1.0
    assert payload["summary"]["missing_provenance_row_count"] == 0

    row = payload["rows"][0]
    assert REQUIRED_FIELDS <= set(row)
    assert row["artifact_sha256"] or row["checksum_withheld_reason"]
    assert row["access_policy"]["redistribution_allowed"] is False


def test_row_provenance_builder_rejects_promoted_row_without_checksum_or_withheld_reason(tmp_path: Path) -> None:
    rows = tmp_path / "bad_rows.json"
    out = tmp_path / "bad_report.json"
    _write_json(
        rows,
        {
            "rows": [
                {
                    "promotion_status": "promoted",
                    "artifact_id": "artifact-002",
                    "source_id": "peer_tbi_tall_buildings",
                    "artifact_sha256": "",
                    "checksum_withheld_reason": "",
                    "file_inventory_path": "reports/peer-tbi-report.pdf",
                    "parser_name": "peer_tbi_metric_parser",
                    "parser_version": "1.0",
                    "row_pointer": "PDF:p.12:Table 3:row 1",
                    "access_policy": {
                        "classification": "public",
                        "redistribution_allowed": False,
                        "requires_manual_review": True,
                    },
                }
            ]
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(BUILDER),
            "--manifest",
            str(SEED_MANIFEST),
            "--parsed-rows",
            str(rows),
            "--out",
            str(out),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "artifact_sha256 or checksum_withheld_reason is required" in proc.stderr
```

- [ ] **Step 2: Run the failing test before implementation.**

Run:

```bash
python3 -m pytest -q tests/test_build_real_project_row_provenance_report.py
```

Expected before the builder exists: FAIL because `implementation/phase1/build_real_project_row_provenance_report.py` is missing.

### Task 4: Implement The Row Provenance Builder

**Files:**

- Create: `implementation/phase1/build_real_project_row_provenance_report.py`
- Read: `implementation/phase1/real_project_corpus_seed_manifest.json`
- Read: parsed row JSON supplied by `--parsed-rows`
- Write: `implementation/phase1/real_project_row_provenance_report.json`

- [ ] **Step 1: Build a CLI that validates promoted rows only.**

Implementation rules:

- Accept `--manifest`, `--parsed-rows`, and `--out`.
- Treat rows with `promotion_status` in `{"promoted", "release_candidate", "benchmark_surface"}` as promoted rows requiring complete provenance.
- Ignore rows with `promotion_status` in `{"candidate", "blocked", "excluded"}` for the coverage denominator, but keep counts in summary if useful.
- Require `source_id` to exist in the seed manifest source families.
- Require every promoted row to include all required fields.
- Require at least one of `artifact_sha256` or `checksum_withheld_reason`.
- Require `access_policy.redistribution_allowed=false` when classification is `restricted`, `unknown`, or `redacted`.
- Emit `row_provenance_coverage=1.0` only when every promoted row is complete.
- Keep `p0_upstream_hard_gate=true` in the output.

Suggested implementation skeleton:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


PROMOTED_STATUSES = {"promoted", "release_candidate", "benchmark_surface"}
REQUIRED_FIELDS = [
    "artifact_id",
    "source_id",
    "artifact_sha256",
    "checksum_withheld_reason",
    "file_inventory_path",
    "parser_name",
    "parser_version",
    "row_pointer",
    "access_policy",
]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("rows", [])
    return [row for row in rows if isinstance(row, dict)]


def build_report(manifest: dict[str, Any], parsed_rows: dict[str, Any]) -> dict[str, Any]:
    source_ids = {
        str(row.get("source_id", "") or "")
        for row in manifest.get("source_families", [])
        if isinstance(row, dict)
    }
    promoted = [
        row for row in _rows(parsed_rows)
        if str(row.get("promotion_status", "") or "") in PROMOTED_STATUSES
    ]

    errors: list[str] = []
    normalized_rows: list[dict[str, Any]] = []
    for index, row in enumerate(promoted):
        missing = [field for field in REQUIRED_FIELDS if field not in row]
        if missing:
            errors.append(f"row {index} missing required fields: {missing}")
            continue
        if str(row.get("source_id", "") or "") not in source_ids:
            errors.append(f"row {index} references unknown source_id: {row.get('source_id')}")
        if not str(row.get("artifact_sha256", "") or "").strip() and not str(
            row.get("checksum_withheld_reason", "") or ""
        ).strip():
            errors.append(f"row {index} artifact_sha256 or checksum_withheld_reason is required")

        access = row.get("access_policy") if isinstance(row.get("access_policy"), dict) else {}
        classification = str(access.get("classification", "") or "")
        redistribution_allowed = bool(access.get("redistribution_allowed", False))
        if classification in {"restricted", "unknown", "redacted"} and redistribution_allowed:
            errors.append(f"row {index} restricted/unknown/redacted artifact cannot redistribute")

        normalized_rows.append({field: row.get(field) for field in REQUIRED_FIELDS})

    if errors:
        raise ValueError("; ".join(errors))

    complete_count = len(normalized_rows)
    promoted_count = len(promoted)
    coverage = 1.0 if promoted_count == complete_count else 0.0
    return {
        "schema_version": "real_project_row_provenance_report.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_manifest_schema_version": str(manifest.get("schema_version", "") or ""),
        "contract_pass": coverage == 1.0,
        "reason_code": "PASS" if coverage == 1.0 else "ERR_ROW_PROVENANCE_INCOMPLETE",
        "p0_upstream_hard_gate": True,
        "row_provenance_coverage": coverage,
        "rows": normalized_rows,
        "summary": {
            "promoted_row_count": promoted_count,
            "complete_provenance_row_count": complete_count,
            "missing_provenance_row_count": promoted_count - complete_count,
            "redistribution_allowed_row_count": sum(
                1 for row in normalized_rows
                if bool((row.get("access_policy") or {}).get("redistribution_allowed", False))
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--parsed-rows", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    try:
        payload = build_report(_load_json(args.manifest), _load_json(args.parsed_rows))
    except Exception as exc:
        print(f"Real-project row provenance build failed: {exc}")
        return 1
    _write_json(args.out, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run tests and generate the report.**

Run:

```bash
python3 -m pytest -q tests/test_build_real_project_row_provenance_report.py
python3 implementation/phase1/build_real_project_row_provenance_report.py \
  --manifest implementation/phase1/real_project_corpus_seed_manifest.json \
  --parsed-rows implementation/phase1/real_project_promoted_rows.json \
  --out implementation/phase1/real_project_row_provenance_report.json
```

Expected: tests PASS. The report command PASSes only when `real_project_promoted_rows.json` exists and every promoted row carries complete provenance.

**P1-3 Pass/Fail Metric:**

- PASS if `row_provenance_coverage=1.0` for every promoted parsed row.
- PASS if every promoted row includes `artifact_id`, `source_id`, `artifact_sha256` or `checksum_withheld_reason`, `file_inventory_path`, `parser_name`, `parser_version`, `row_pointer`, and `access_policy`.
- PASS if `row_pointer` is precise enough to audit the source location, for example `MGT:TABLE=...:ROW=...`, `IFC:#123`, `PDF:p.12:Table 3:row 1`, `XLSX:Sheet1!A1:D7`, `DWG:layer/entity`, `DXF:entity_handle`, or `ZIP:member/path:byte-range`.
- PASS if viewer/report/release surfaces show provenance metadata without exposing restricted raw payloads.
- PASS if P0 remains the upstream hard gate in output summary fields and tests.
- FAIL if any promoted row has missing artifact identity, missing checksum and withheld reason, missing parser identity, missing row pointer, or only a human-readable source label.
- FAIL if `restricted`, `unknown`, or `redacted` rows set `access_policy.redistribution_allowed=true`.

## Integration Order

- [ ] **Step 1: Re-run the P0 seed manifest validator before P1 implementation.**

Run:

```bash
python3 implementation/phase1/validate_real_project_corpus_manifest.py \
  --schema implementation/phase1/real_project_corpus_manifest.schema.json \
  --manifest implementation/phase1/real_project_corpus_seed_manifest.json \
  --show-summary
```

Expected: `Real project corpus manifest OK` and `p0_ready_sources=2/2`.

- [ ] **Step 2: Implement P1-2 PEER metric records first.**

Run:

```bash
python3 -m pytest -q tests/test_build_peer_tbi_benchmark_metric_records.py
```

Expected: PASS with all five required metric groups and zero redistributable PEER metric rows.

- [ ] **Step 3: Implement P1-3 row provenance second.**

Run:

```bash
python3 -m pytest -q tests/test_build_real_project_row_provenance_report.py
```

Expected: PASS with `row_provenance_coverage=1.0` for promoted rows.

- [ ] **Step 4: Re-run the combined P0/P1 gate checks.**

Run:

```bash
python3 -m pytest -q \
  tests/test_real_project_corpus_manifest.py \
  tests/test_build_peer_tbi_benchmark_metric_records.py \
  tests/test_build_real_project_row_provenance_report.py
```

Expected: PASS. If this fails because a row or metric lacks provenance, citation, locator, or non-redistribution evidence, fix the data contract instead of relaxing the P0 hard gate.

## Release And Viewer Guardrails

- Do not add PEER raw models, archives, input decks, or companion files to release packaging as part of P1-2.
- Do not add KONEPS attachments or any non-reviewed raw artifact to release packaging as part of P1-3.
- Do not turn citation records into raw redistribution permission. P0 remains the upstream hard gate.
- Do not display restricted raw payload links in viewer/report surfaces. Display source family, artifact id, checksum or withheld reason, row pointer, parser identity, benchmark status, and access policy instead.
- Do not auto-set `redistribution_allowed=true` from public availability, crawler success, parsed metric availability, or report URL availability.

## Completion Checklist

- [ ] `implementation/phase1/peer_tbi_benchmark_metric_records.json` exists and has the five required metric groups.
- [ ] Every PEER metric record has the required fields and `redistribution_allowed=false`.
- [ ] `implementation/phase1/real_project_row_provenance_report.json` exists once promoted rows are available.
- [ ] Every promoted row has the required provenance fields and checksum or explicit checksum-withheld reason.
- [ ] P0 remains the upstream hard gate in tests, output summaries, and downstream integration notes.
