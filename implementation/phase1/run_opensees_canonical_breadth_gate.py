#!/usr/bin/env python3
"""Surface local OpenSees canonical breadth from committed real-source assets."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


CASE_SPECS: list[dict[str, Any]] = [
    {
        "case_id": "SCBF16B",
        "family_id": "sac_scbf16b",
        "path": "implementation/phase1/open_data/megastructure/opensees/SCBF16B.tcl",
        "format": "tcl",
        "origin": "global_authority",
        "parser_contract_ready": True,
    },
    {
        "case_id": "SCBF16B_shell_beam_mix",
        "family_id": "sac_scbf16b_shell_beam_mix",
        "path": "implementation/phase1/open_data/megastructure/opensees/SCBF16B_shell_beam_mix.tcl",
        "format": "tcl",
        "origin": "global_authority",
        "parser_contract_ready": True,
    },
    {
        "case_id": "luxinzheng_megatall_model1",
        "family_id": "luxinzheng_megatall",
        "path": "implementation/phase1/open_data/irregular/collected/artifacts/luxinzheng_megatall_tcl_model1_local/opensees.tcl",
        "format": "tcl",
        "origin": "public_lab_download",
        "parser_contract_ready": True,
    },
    {
        "case_id": "nheri_soft_story_podium",
        "family_id": "nheri_soft_story_podium",
        "path": "implementation/phase1/open_data/irregular/collected/artifacts/nheri_soft_story_podium_remote/main.tcl",
        "format": "tcl",
        "origin": "designsafe_publication",
        "parser_contract_ready": False,
    },
    {
        "case_id": "amaelkady_constructbrace",
        "family_id": "amaelkady_constructbrace",
        "path": "implementation/phase1/open_data/irregular/collected/artifacts/amaelkady_constructbrace_github_remote/ConstructBrace.tcl",
        "format": "tcl",
        "origin": "github_public",
        "parser_contract_ready": False,
    },
    {
        "case_id": "amaelkady_scbf16cg",
        "family_id": "amaelkady_scbf16cg",
        "path": "implementation/phase1/open_data/irregular/collected/artifacts/amaelkady_scbf16cg_github_remote/ConstructBrace.tcl",
        "format": "tcl",
        "origin": "github_public",
        "parser_contract_ready": False,
    },
    {
        "case_id": "luxinzheng_megatall_bundle",
        "family_id": "luxinzheng_megatall",
        "path": "implementation/phase1/open_data/irregular/harvested/torsionally_eccentric_core_tower/OpenSees-Mega-tall-Building.zip",
        "format": "zip",
        "origin": "public_lab_download",
        "parser_contract_ready": False,
    },
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_opensees_canonical_breadth_gate() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    family_ids: set[str] = set()
    origin_counts: Counter[str] = Counter()
    format_counts: Counter[str] = Counter()
    parser_ready_count = 0
    for spec in CASE_SPECS:
        path = Path(str(spec["path"]))
        if not path.exists():
            continue
        family_id = str(spec["family_id"])
        origin = str(spec["origin"])
        fmt = str(spec["format"])
        parser_ready = bool(spec.get("parser_contract_ready", False))
        rows.append(
            {
                "case_id": str(spec["case_id"]),
                "family_id": family_id,
                "path": str(path),
                "format": fmt,
                "origin": origin,
                "size_bytes": int(path.stat().st_size),
                "sha256": _sha256(path),
                "parser_contract_ready": parser_ready,
            }
        )
        family_ids.add(family_id)
        origin_counts[origin] += 1
        format_counts[fmt] += 1
        if parser_ready:
            parser_ready_count += 1

    canonical_case_count = len(rows)
    canonical_family_count = len(family_ids)
    reason_code = "PASS"
    if canonical_case_count < 6 or canonical_family_count < 5 or parser_ready_count < 3:
        reason_code = "ERR_OPENSEES_CANONICAL_BREADTH_LOW"
    summary = {
        "canonical_case_count": canonical_case_count,
        "canonical_family_count": canonical_family_count,
        "standalone_parser_ready_case_count": int(parser_ready_count),
        "origin_counts": dict(sorted(origin_counts.items())),
        "format_counts": dict(sorted(format_counts.items())),
    }
    summary_line = (
        f"OpenSees canonical breadth: {'PASS' if reason_code == 'PASS' else 'CHECK'} | "
        f"families={canonical_family_count} | "
        f"cases={canonical_case_count} | "
        f"parser_ready={parser_ready_count} | "
        f"origins={','.join(f'{key}={value}' for key, value in sorted(origin_counts.items())) or 'n/a'}"
    )
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": reason_code == "PASS",
        "reason_code": reason_code,
        "reason": (
            "committed OpenSees canonical asset breadth is sufficient for P1 breadth surfacing"
            if reason_code == "PASS"
            else "OpenSees canonical asset breadth is still below the current surfacing floor"
        ),
        "summary": summary,
        "summary_line": summary_line,
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        default="implementation/phase1/release/benchmark_expansion/opensees_canonical_breadth_report.json",
    )
    args = parser.parse_args(argv)
    payload = run_opensees_canonical_breadth_gate()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote OpenSees canonical breadth gate report: {out}")
    return 0 if payload.get("contract_pass", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
