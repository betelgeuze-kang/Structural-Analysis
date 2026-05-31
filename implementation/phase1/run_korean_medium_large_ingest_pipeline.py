#!/usr/bin/env python3
"""Regenerate catalog, collect artifacts, and check attached medium/large MGT headers."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from implementation.phase1.open_data.korea.korean_building_scale import (  # noqa: E402
    building_scale_band,
    is_medium_or_large,
)

KOREA_DIR = REPO_ROOT / "implementation" / "phase1" / "open_data" / "korea"
DEFAULT_CATALOG = KOREA_DIR / "korean_source_catalog.json"
DEFAULT_COLLECTION_REPORT = KOREA_DIR / "korean_public_structure_collection_report.json"
DEFAULT_RECEIPT = KOREA_DIR / "korean_medium_large_ingest_receipt.json"
ARTIFACT_ROOT = KOREA_DIR / "collected" / "artifacts"
MGT_HEADER_MARKERS = ("*VERSION", "*UNIT")
MIN_MGT_BYTES = 500
BENCHMARK_MGT = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.mgt"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _attach_provenance(mgt_path: Path, benchmark_sha: str) -> str:
    if not benchmark_sha or not mgt_path.is_file():
        return "unknown"
    if _sha256_file(mgt_path) == benchmark_sha:
        return "repo_benchmark_bridge"
    return "operator_attached"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object json: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _regenerate_catalog(*, skip_regenerate: bool) -> None:
    if skip_regenerate:
        return
    script = KOREA_DIR / "generate_korean_source_catalog.py"
    subprocess.run([sys.executable, str(script)], cwd=REPO_ROOT, check=True)


def _run_collector(*, catalog_path: Path, skip_collect: bool) -> dict[str, Any]:
    if skip_collect:
        if DEFAULT_COLLECTION_REPORT.is_file():
            return _load_json(DEFAULT_COLLECTION_REPORT)
        return {}
    script = KOREA_DIR / "collect_korean_public_structures.py"
    subprocess.run(
        [sys.executable, str(script), "--catalog", str(catalog_path)],
        cwd=REPO_ROOT,
        check=True,
    )
    return _load_json(DEFAULT_COLLECTION_REPORT)


def _find_mgt_artifact(source_id: str) -> Path | None:
    artifact_dir = ARTIFACT_ROOT / source_id
    if not artifact_dir.is_dir():
        return None
    for path in sorted(artifact_dir.iterdir()):
        if path.is_file() and path.suffix.lower() == ".mgt":
            return path
    return None


def _check_mgt_header(path: Path) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    if not path.is_file():
        blockers.append("mgt_file_missing")
        return False, blockers
    size = path.stat().st_size
    if size <= MIN_MGT_BYTES:
        blockers.append(f"mgt_file_too_small:{size}")
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:4096]
    except OSError as exc:
        blockers.append(f"mgt_read_error:{exc}")
        return False, blockers
    if not any(marker in head for marker in MGT_HEADER_MARKERS):
        blockers.append("mgt_header_missing_version_or_unit")
    return len(blockers) == 0, blockers


def run_korean_medium_large_ingest_pipeline(
    *,
    catalog_path: Path = DEFAULT_CATALOG,
    collection_report_path: Path = DEFAULT_COLLECTION_REPORT,
    receipt_path: Path = DEFAULT_RECEIPT,
    skip_regenerate: bool = False,
    skip_collect: bool = False,
    run_roundtrip_parse: bool = False,
) -> dict[str, Any]:
    benchmark_sha = _sha256_file(BENCHMARK_MGT) if BENCHMARK_MGT.is_file() else ""
    _regenerate_catalog(skip_regenerate=skip_regenerate)
    collection_report = _run_collector(catalog_path=catalog_path, skip_collect=skip_collect)
    catalog = _load_json(catalog_path)
    rows = catalog.get("source_records")
    if not isinstance(rows, list):
        raise ValueError("catalog missing source_records")

    collection_by_id = {
        str(row.get("source_id") or ""): row
        for row in collection_report.get("records", [])
        if isinstance(row, dict) and row.get("source_id")
    }

    per_source: list[dict[str, Any]] = []
    attached_count = 0
    metadata_only_count = 0
    mgt_header_ok_count = 0

    for record in rows:
        if not isinstance(record, dict) or not is_medium_or_large(record):
            continue
        source_id = str(record.get("source_id") or "")
        source_format = str(record.get("format") or "").lower()
        collection_row = collection_by_id.get(source_id, {})
        collected_path = str(collection_row.get("local_path") or "").strip()
        status = str(collection_row.get("status") or "")
        attached = status == "collected" or bool(collected_path)
        if attached:
            attached_count += 1
        else:
            metadata_only_count += 1

        entry: dict[str, Any] = {
            "source_id": source_id,
            "storey_band": record.get("storey_band", ""),
            "scale": building_scale_band(str(record.get("storey_band") or "")),
            "format": source_format,
            "attached": attached,
            "metadata_only": not attached,
            "mgt_header_ok": False,
            "blockers": [],
        }

        if source_format == "mgt" and attached:
            mgt_path = Path(collected_path) if collected_path else _find_mgt_artifact(source_id)
            if mgt_path is None:
                entry["blockers"].append("attached_mgt_path_unresolved")
            else:
                ok, blockers = _check_mgt_header(mgt_path)
                entry["mgt_header_ok"] = ok
                entry["blockers"].extend(blockers)
                if ok:
                    mgt_header_ok_count += 1
                entry["mgt_path"] = str(mgt_path)
                entry["attach_provenance"] = _attach_provenance(mgt_path, benchmark_sha)
                if run_roundtrip_parse and ok:
                    out_dir = mgt_path.parent / "roundtrip"
                    out_dir.mkdir(parents=True, exist_ok=True)
                    json_out = out_dir / f"{source_id}.roundtrip.json"
                    npz_out = out_dir / f"{source_id}.roundtrip.npz"
                    parser_script = REPO_ROOT / "implementation/phase1/parse_midas_mgt_to_json_npz.py"
                    proc = subprocess.run(
                        [
                            sys.executable,
                            str(parser_script),
                            "--mgt",
                            str(mgt_path),
                            "--json-out",
                            str(json_out),
                            "--npz-out",
                            str(npz_out),
                        ],
                        cwd=REPO_ROOT / "implementation/phase1",
                        capture_output=True,
                        text=True,
                    )
                    entry["roundtrip_parse_exit_code"] = int(proc.returncode)
                    entry["roundtrip_json"] = str(json_out) if json_out.is_file() else ""
                    entry["roundtrip_npz"] = str(npz_out) if npz_out.is_file() else ""
                    if proc.returncode != 0:
                        entry["blockers"].append("roundtrip_parse_failed")
        elif source_format == "mgt" and not attached:
            entry["blockers"].append("awaiting_manual_mgt_attach")

        per_source.append(entry)

    receipt = {
        "schema_version": "korean_medium_large_ingest_receipt.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "catalog_path": str(catalog_path),
        "collection_report_path": str(collection_report_path),
        "summary": {
            "medium_large_source_count": len(per_source),
            "attached_count": attached_count,
            "metadata_only_count": metadata_only_count,
            "mgt_header_ok_count": mgt_header_ok_count,
        },
        "per_source": per_source,
        "summary_line": (
            "Korean medium/large ingest: "
            f"sources={len(per_source)} attached={attached_count} "
            f"metadata_only={metadata_only_count} mgt_header_ok={mgt_header_ok_count}"
        ),
    }
    _write_json(receipt_path, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--collection-report", type=Path, default=DEFAULT_COLLECTION_REPORT)
    parser.add_argument("--receipt-out", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--skip-regenerate", action="store_true")
    parser.add_argument("--skip-collect", action="store_true")
    parser.add_argument(
        "--run-roundtrip-parse",
        action="store_true",
        help="Run parse_midas_mgt_to_json_npz for attached MGT with valid headers",
    )
    args = parser.parse_args()

    receipt = run_korean_medium_large_ingest_pipeline(
        catalog_path=args.catalog,
        collection_report_path=args.collection_report,
        receipt_path=args.receipt_out,
        skip_regenerate=args.skip_regenerate,
        skip_collect=args.skip_collect,
        run_roundtrip_parse=args.run_roundtrip_parse,
    )
    print(receipt["summary_line"])
    print(f"Wrote receipt: {args.receipt_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
