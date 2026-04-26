#!/usr/bin/env python3
"""Prepare extracted binary MIDAS archive members and adapter manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import zipfile


REASONS = {
    "PASS": "binary archive adapter manifest prepared",
    "ERR_MISSING_ARCHIVE": "archive file is missing",
    "ERR_BAD_ARCHIVE": "archive could not be read",
    "ERR_NO_RECOGNIZED_MEMBERS": "no recognized binary or geometry members found",
}

RECOGNIZED_EXTENSIONS = {".meb", ".mmbx", ".mcb", ".3dm", ".gh", ".mgt"}
PRIMARY_PRIORITY = [".meb", ".mmbx", ".mcb", ".mgt", ".3dm", ".gh"]
STRUCTURAL_TOKEN_PRIORITY = [
    "__DBMS_DATA__",
    "GUID",
    "xUNIT",
    "xMATL",
    "xSECT",
    "xTHIK",
    "xPLAN",
    "xSTOR",
    "xFGRP",
    "xDSEC",
    "xMDUL",
    "xGRND",
    "xMBTP",
]


def _label_counts(counts: dict[str, int]) -> str:
    return ", ".join(
        f"{label}={count}"
        for label, count in sorted(counts.items(), key=lambda item: (-int(item[1]), str(item[0])))
    ) or "n/a"


def _recommended_adapter_family(extension_counts: dict[str, int]) -> str:
    if int(extension_counts.get(".meb", 0) or 0) > 0:
        return "midas_binary_meb_parser"
    if int(extension_counts.get(".mmbx", 0) or 0) > 0:
        return "midas_binary_mmbx_parser"
    if int(extension_counts.get(".mcb", 0) or 0) > 0:
        return "midas_binary_mcb_parser"
    if int(extension_counts.get(".3dm", 0) or 0) > 0:
        return "rhino_3dm_geometry_bridge"
    if int(extension_counts.get(".gh", 0) or 0) > 0:
        return "grasshopper_geometry_bridge"
    if int(extension_counts.get(".mgt", 0) or 0) > 0:
        return "midas_mgt_text_parser"
    return "unknown"


def _pick_primary_member(rows: list[dict[str, object]]) -> dict[str, object] | None:
    if not rows:
        return None
    for extension in PRIMARY_PRIORITY:
        for row in rows:
            if str(row.get("extension", "")) == extension:
                return row
    return rows[0]


def _unique_preserve(rows: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if row in seen:
            continue
        seen.add(row)
        out.append(row)
    return out


def _inspect_binary_member(member_path: Path) -> dict[str, object]:
    data = member_path.read_bytes()
    magic_bytes = data[:4]
    try:
        magic_ascii = magic_bytes.decode("ascii", errors="ignore")
    except Exception:
        magic_ascii = ""
    ascii_tokens = [
        token.decode("ascii", errors="ignore")
        for token in re.findall(rb"[A-Za-z_][A-Za-z0-9_]{3,15}", data)
    ]
    filtered_tokens = _unique_preserve(
        [
            token
            for token in ascii_tokens
            if (
                token == "__DBMS_DATA__"
                or token == "GUID"
                or (token.startswith("x") and token[1:].isupper())
                or token.isupper()
            )
        ]
    )
    structural_tokens = [token for token in filtered_tokens if token in STRUCTURAL_TOKEN_PRIORITY]
    probe_ready = bool(
        magic_ascii == "MBDG"
        and "__DBMS_DATA__" in filtered_tokens
        and len(structural_tokens) >= 4
    )
    return {
        "member_path": str(member_path),
        "size_bytes": int(len(data)),
        "magic_ascii": magic_ascii,
        "magic_hex": magic_bytes.hex(),
        "dbms_marker_present": "__DBMS_DATA__" in filtered_tokens,
        "table_token_rows": filtered_tokens[:40],
        "structural_token_rows": structural_tokens,
        "probe_ready": probe_ready,
        "probe_label": (
            "binary db layout signal detected"
            if probe_ready
            else "binary member extracted / table layout still uncertain"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--report-out", default=None)
    args = parser.parse_args()

    archive_path = Path(args.archive)
    source_id = str(args.source_id).strip() or "unknown_source"
    out_dir = Path(args.out_dir) if args.out_dir else Path(f"implementation/phase1/open_data/midas/quality_corpus/extracted/{source_id}")
    report_out = Path(args.report_out) if args.report_out else out_dir / "adapter_manifest.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_out.parent.mkdir(parents=True, exist_ok=True)

    reason_code = "PASS"
    extracted_rows: list[dict[str, object]] = []
    extension_counts: dict[str, int] = {}

    if not archive_path.exists():
        reason_code = "ERR_MISSING_ARCHIVE"
    else:
        try:
            with zipfile.ZipFile(archive_path) as zip_file:
                zip_file.extractall(out_dir)
                for name in zip_file.namelist():
                    extension = Path(str(name)).suffix.lower()
                    if extension not in RECOGNIZED_EXTENSIONS:
                        continue
                    extracted_path = out_dir / name
                    extension_counts[extension] = int(extension_counts.get(extension, 0) or 0) + 1
                    extracted_rows.append(
                        {
                            "member_name": str(name),
                            "extension": extension or "(no_ext)",
                            "size_bytes": int(extracted_path.stat().st_size) if extracted_path.exists() else 0,
                            "extracted_path": str(extracted_path),
                        }
                    )
        except zipfile.BadZipFile:
            reason_code = "ERR_BAD_ARCHIVE"

    if reason_code == "PASS" and not extracted_rows:
        reason_code = "ERR_NO_RECOGNIZED_MEMBERS"

    primary_member = _pick_primary_member(extracted_rows)
    primary_probe: dict[str, object] = {}
    primary_probe_path = out_dir / "primary_member_probe.json"
    if isinstance(primary_member, dict):
        extension = str(primary_member.get("extension", ""))
        if extension in {".meb", ".mmbx", ".mcb"}:
            primary_probe = _inspect_binary_member(Path(str(primary_member.get("extracted_path", ""))))
            primary_probe_path.write_text(json.dumps(primary_probe, ensure_ascii=False, indent=2), encoding="utf-8")
    adapter_family = _recommended_adapter_family(extension_counts)
    contract_pass = reason_code == "PASS"
    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-prepare-midas-binary-archive-adapter",
        "source_id": source_id,
        "archive_path": str(archive_path),
        "out_dir": str(out_dir),
        "summary": {
            "recognized_member_count": len(extracted_rows),
            "extension_label": _label_counts(extension_counts),
            "recommended_adapter_family": adapter_family,
            "recommended_parser_script": (
                "implementation/phase1/parse_midas_binary_meb_to_json_npz.py"
                if adapter_family == "midas_binary_meb_parser"
                else ""
            ),
            "recommended_primary_member": primary_member["member_name"] if isinstance(primary_member, dict) else "",
            "primary_member_probe_ready": bool(primary_probe.get("probe_ready", False)),
            "primary_member_magic": str(primary_probe.get("magic_ascii", "") or ""),
            "primary_member_structural_token_label": _label_counts(
                {token: 1 for token in primary_probe.get("structural_token_rows", [])}
            ),
        },
        "members": extracted_rows,
        "primary_member_probe": primary_probe,
        "checks": {
            "archive_exists": archive_path.exists(),
            "recognized_member_nonzero": bool(extracted_rows),
            "primary_member_selected": bool(primary_member),
            "primary_member_probe_ready": bool(primary_probe.get("probe_ready", False)) if primary_probe else False,
        },
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }
    report_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote binary archive adapter manifest: {report_out}")
    if not contract_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
