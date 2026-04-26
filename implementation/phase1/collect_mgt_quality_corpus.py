#!/usr/bin/env python3
"""Collect and gate high-quality MIDAS .mgt corpus for real experiments.

Policy:
- Only accept direct .mgt text sources with verifiable provenance.
- Reject synthetic/toy sources via parser strict checks.
- Require minimum topology scale and optional shell-beam mix.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
from urllib.parse import urlparse
import urllib.request
import zipfile


REASONS = {
    "PASS": "quality mgt corpus collected",
    "ERR_INVALID_INPUT": "invalid collector input",
    "ERR_FETCH_FAIL": "failed to fetch one or more sources",
    "ERR_PARSE_FAIL": "failed to parse one or more fetched mgt files",
    "ERR_NO_QUALITY_MGT": "no source passed quality gate",
}

INPUT_SCHEMA_VERSION = "1.0"
SOURCE_SCHEMA_VERSION = "1.0"
REPORT_SCHEMA_VERSION = "1.0"


def _sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise RuntimeError(f"missing file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _run(cmd: list[str]) -> tuple[bool, float, int, str, str]:
    t0 = time.time()
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    dt = time.time() - t0
    return (
        proc.returncode == 0,
        dt,
        int(proc.returncode),
        (proc.stdout or "")[-4000:],
        (proc.stderr or "")[-4000:],
    )


def _is_http_url(url: str) -> bool:
    try:
        p = urlparse(url)
    except Exception:
        return False
    return p.scheme in {"http", "https"} and bool(p.netloc)


def _safe_name(source_id: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(source_id).strip())
    return name.strip("._") or "source"


def _download(url: str, timeout_sec: int) -> tuple[bytes, int]:
    req = urllib.request.Request(str(url), headers={"User-Agent": "phase1-mgt-quality-corpus/1.0"})
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        data = resp.read()
        status = int(getattr(resp, "status", 200))
    return data, status


def _recognized_midas_members(names: list[str]) -> list[str]:
    return [
        name
        for name in names
        if str(name).lower().endswith((".mgt", ".meb", ".mcb", ".mmbx"))
    ]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--catalog",
        default="implementation/phase1/open_data/midas/quality_mgt_source_catalog.json",
    )
    p.add_argument(
        "--out-dir",
        default="implementation/phase1/open_data/midas/quality_corpus",
    )
    p.add_argument(
        "--report-out",
        default="implementation/phase1/open_data/midas/quality_corpus_report.json",
    )
    p.add_argument("--min-node-count", type=int, default=100)
    p.add_argument("--min-element-count", type=int, default=100)
    p.add_argument("--min-accepted-count", type=int, default=1)
    p.add_argument("--require-shell-beam-mix", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--download-timeout-sec", type=int, default=60)
    args = p.parse_args()

    report_out = Path(args.report_out)
    report_out.parent.mkdir(parents=True, exist_ok=True)

    reason_code = "PASS"
    steps: list[dict] = []
    records: list[dict] = []
    accepted: list[dict] = []

    if int(args.min_node_count) <= 0 or int(args.min_element_count) <= 0 or int(args.min_accepted_count) <= 0:
        reason_code = "ERR_INVALID_INPUT"
    if int(args.download_timeout_sec) <= 0:
        reason_code = "ERR_INVALID_INPUT"

    catalog: dict = {}
    sources: list[dict] = []
    if reason_code == "PASS":
        try:
            catalog = _load_json(Path(args.catalog))
            if str(catalog.get("schema_version", "")) != SOURCE_SCHEMA_VERSION:
                reason_code = "ERR_INVALID_INPUT"
            raw_sources = catalog.get("sources")
            if not isinstance(raw_sources, list) or not raw_sources:
                reason_code = "ERR_INVALID_INPUT"
            else:
                sources = [s for s in raw_sources if isinstance(s, dict)]
                if not sources:
                    reason_code = "ERR_INVALID_INPUT"
        except Exception:
            reason_code = "ERR_INVALID_INPUT"

    out_dir = Path(args.out_dir)
    raw_dir = out_dir / "raw"
    parsed_dir = out_dir / "parsed"
    raw_dir.mkdir(parents=True, exist_ok=True)
    parsed_dir.mkdir(parents=True, exist_ok=True)

    fetch_fail_count = 0
    parse_fail_count = 0
    rejected_count = 0
    total_nodes = 0
    total_elements = 0
    shell_beam_mix_accepted_count = 0
    unknown_row_total = 0
    typed_row_total = 0
    accepted_parseable_count = 0
    accepted_archive_count = 0
    archive_member_total = 0

    for idx, src in enumerate(sources, 1):
        src_id = _safe_name(str(src.get("source_id", f"source_{idx}")))
        url = str(src.get("url", "")).strip()
        expected_sha = str(src.get("expected_sha256", "")).strip().lower()
        source_class = str(src.get("source_class", "mgt_text")).strip().lower()
        rec: dict = {
            "source_id": src_id,
            "url": url,
            "expected_sha256": expected_sha,
            "source_class": source_class,
            "http_status": 0,
            "download_ok": False,
            "sha256": "",
            "bytes": 0,
            "is_mgt_candidate": False,
            "parse_ok": False,
            "quality_pass": False,
            "reject_reason": "",
            "artifacts": {},
        }
        if reason_code != "PASS":
            rec["reject_reason"] = "collector already invalid"
            records.append(rec)
            continue

        if not _is_http_url(url):
            rec["reject_reason"] = "invalid url"
            rejected_count += 1
            records.append(rec)
            continue

        download_ok = False
        try:
            data, status = _download(url, int(args.download_timeout_sec))
            digest = _sha256_bytes(data)
            rec["http_status"] = int(status)
            rec["download_ok"] = True
            rec["sha256"] = digest
            rec["bytes"] = int(len(data))
            if expected_sha and digest.lower() != expected_sha:
                rec["reject_reason"] = "sha256 mismatch"
                rejected_count += 1
                records.append(rec)
                continue

            raw_suffix = ".mgt" if source_class == "mgt_text" else ".zip"
            raw_path = raw_dir / f"{src_id}{raw_suffix}"
            raw_path.write_bytes(data)
            rec["is_mgt_candidate"] = bool(source_class == "mgt_text")
            rec["artifacts"]["mgt"] = str(raw_path)
            download_ok = True
        except Exception as exc:
            rec["reject_reason"] = f"fetch failed: {exc}"
            fetch_fail_count += 1
            rejected_count += 1
            records.append(rec)
            continue

        if not download_ok:
            rec["reject_reason"] = "fetch failed"
            fetch_fail_count += 1
            rejected_count += 1
            records.append(rec)
            continue

        if source_class == "mgt_text":
            parse_json = parsed_dir / f"{src_id}.json"
            parse_npz = parsed_dir / f"{src_id}.npz"
            parse_edges = parsed_dir / f"{src_id}_edges.json"
            parse_report = parsed_dir / f"{src_id}_conversion_report.json"
            parse_cmd = [
                sys.executable,
                "implementation/phase1/parse_midas_mgt_to_json_npz.py",
                "--mgt",
                str(rec["artifacts"]["mgt"]),
                "--json-out",
                str(parse_json),
                "--npz-out",
                str(parse_npz),
                "--edge-list-out",
                str(parse_edges),
                "--report-out",
                str(parse_report),
                "--forbid-synthetic-source",
            ]
            if bool(args.require_shell_beam_mix):
                parse_cmd.append("--require-shell-beam-mix")
            ok, sec, rc, so, se = _run(parse_cmd)
            steps.append(
                {
                    "step": f"parse_{src_id}",
                    "seconds": float(sec),
                    "return_code": int(rc),
                    "command": shlex.join(parse_cmd),
                    "stdout_tail": so,
                    "stderr_tail": se,
                }
            )
            if not ok or not parse_report.exists():
                rec["reject_reason"] = "parse failed"
                parse_fail_count += 1
                rejected_count += 1
                records.append(rec)
                continue

            parsed = _load_json(parse_report)
            checks = parsed.get("checks") if isinstance(parsed.get("checks"), dict) else {}
            metrics = parsed.get("metrics") if isinstance(parsed.get("metrics"), dict) else {}
            diag = parsed.get("parser_diagnostics") if isinstance(parsed.get("parser_diagnostics"), dict) else {}
            try:
                node_count = int(metrics.get("node_count", 0))
            except Exception:
                node_count = 0
            try:
                element_count = int(metrics.get("element_count", 0))
            except Exception:
                element_count = 0

            parse_ok = bool(parsed.get("contract_pass", False)) and str(parsed.get("reason_code", "")) == "PASS"
            quality_pass = bool(
                parse_ok
                and bool(checks.get("has_nodes", False))
                and bool(checks.get("has_elements", False))
                and bool(checks.get("synthetic_source_blocked", False))
                and (not bool(args.require_shell_beam_mix) or bool(checks.get("shell_beam_mix_pass", False)))
                and node_count >= int(args.min_node_count)
                and element_count >= int(args.min_element_count)
            )
            rec["parse_ok"] = parse_ok
            rec["quality_pass"] = quality_pass
            rec["metrics"] = {
                "node_count": int(node_count),
                "element_count": int(element_count),
                "beam_element_count": int(metrics.get("beam_element_count", 0) or 0),
                "shell_element_count": int(metrics.get("shell_element_count", 0) or 0),
                "typed_row_total": int(diag.get("typed_row_total", 0) or 0),
                "unknown_row_total": int(diag.get("unknown_row_total", 0) or 0),
            }
            rec["checks"] = {
                "has_nodes": bool(checks.get("has_nodes", False)),
                "has_elements": bool(checks.get("has_elements", False)),
                "synthetic_source_blocked": bool(checks.get("synthetic_source_blocked", False)),
                "shell_beam_mix_pass": bool(checks.get("shell_beam_mix_pass", False)),
            }
            rec["artifacts"].update(
                {
                    "json": str(parse_json),
                    "npz": str(parse_npz),
                    "edge_list": str(parse_edges),
                    "conversion_report": str(parse_report),
                }
            )
        else:
            steps.append(
                {
                    "step": f"archive_scan_{src_id}",
                    "seconds": 0.0,
                    "return_code": 0,
                    "command": f"archive_scan {src_id}",
                    "stdout_tail": "",
                    "stderr_tail": "",
                }
            )
            try:
                with zipfile.ZipFile(str(rec["artifacts"]["mgt"])) as zf:
                    members = zf.namelist()
            except Exception:
                rec["reject_reason"] = "archive scan failed"
                parse_fail_count += 1
                rejected_count += 1
                records.append(rec)
                continue

            recognized = _recognized_midas_members(members)
            quality_pass = bool(len(recognized) > 0)
            rec["parse_ok"] = False
            rec["quality_pass"] = quality_pass
            rec["metrics"] = {
                "node_count": 0,
                "element_count": 0,
                "beam_element_count": 0,
                "shell_element_count": 0,
                "typed_row_total": 0,
                "unknown_row_total": 0,
                "archive_member_count": len(members),
                "recognized_midas_member_count": len(recognized),
            }
            rec["checks"] = {
                "has_nodes": False,
                "has_elements": False,
                "synthetic_source_blocked": True,
                "shell_beam_mix_pass": False,
                "archive_member_pass": bool(len(recognized) > 0),
            }
            rec["artifacts"]["archive_members"] = recognized
        if quality_pass:
            total_nodes += int(rec["metrics"].get("node_count", 0) or 0)
            total_elements += int(rec["metrics"].get("element_count", 0) or 0)
            shell_beam_mix_accepted_count += int(bool(rec["checks"].get("shell_beam_mix_pass", False)))
            unknown_row_total += int(rec["metrics"].get("unknown_row_total", 0) or 0)
            typed_row_total += int(rec["metrics"].get("typed_row_total", 0) or 0)
            accepted_parseable_count += int(source_class == "mgt_text")
            accepted_archive_count += int(source_class != "mgt_text")
            archive_member_total += int(rec["metrics"].get("recognized_midas_member_count", 0) or 0)
            accepted.append(
                {
                    "source_id": src_id,
                    "url": url,
                    "source_class": source_class,
                    "sha256": rec["sha256"],
                    "artifacts": rec["artifacts"],
                    "metrics": rec["metrics"],
                }
            )
        else:
            rec["reject_reason"] = "quality gate failed"
            rejected_count += 1
        records.append(rec)

    if reason_code == "PASS":
        if len(accepted) < int(args.min_accepted_count):
            reason_code = "ERR_NO_QUALITY_MGT"
        elif parse_fail_count > 0:
            reason_code = "ERR_PARSE_FAIL"
        elif fetch_fail_count > 0:
            reason_code = "ERR_FETCH_FAIL"

    checks = {
        "catalog_loaded": bool(reason_code != "ERR_INVALID_INPUT"),
        "accepted_nonzero": bool(len(accepted) > 0),
        "accepted_min_count_pass": bool(len(accepted) >= int(args.min_accepted_count)),
        "fetch_fail_zero": bool(fetch_fail_count == 0),
        "parse_fail_zero": bool(parse_fail_count == 0),
        "shell_beam_mix_accepted_pass": bool((not bool(args.require_shell_beam_mix)) or shell_beam_mix_accepted_count >= 1),
    }
    contract_pass = bool(reason_code == "PASS" and all(checks.values()))
    if reason_code == "PASS" and not contract_pass:
        reason_code = "ERR_NO_QUALITY_MGT"

    payload = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "run_id": "phase1-collect-mgt-quality-corpus",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "catalog": str(args.catalog),
            "out_dir": str(args.out_dir),
            "min_node_count": int(args.min_node_count),
            "min_element_count": int(args.min_element_count),
            "min_accepted_count": int(args.min_accepted_count),
            "require_shell_beam_mix": bool(args.require_shell_beam_mix),
            "download_timeout_sec": int(args.download_timeout_sec),
        },
        "catalog_meta": {
            "schema_version": catalog.get("schema_version", ""),
            "source_count": int(len(sources)),
        },
        "summary": {
            "accepted_count": int(len(accepted)),
            "rejected_count": int(rejected_count),
            "fetch_fail_count": int(fetch_fail_count),
            "parse_fail_count": int(parse_fail_count),
            "accepted_node_total": int(total_nodes),
            "accepted_element_total": int(total_elements),
            "shell_beam_mix_accepted_count": int(shell_beam_mix_accepted_count),
            "accepted_parseable_count": int(accepted_parseable_count),
            "accepted_archive_count": int(accepted_archive_count),
            "recognized_archive_member_total": int(archive_member_total),
            "typed_row_total": int(typed_row_total),
            "unknown_row_total": int(unknown_row_total),
        },
        "checks": checks,
        "accepted": accepted,
        "records": records,
        "steps": steps,
        "contract_pass": bool(contract_pass),
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }
    report_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote quality mgt corpus report: {report_out}")
    if not contract_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
