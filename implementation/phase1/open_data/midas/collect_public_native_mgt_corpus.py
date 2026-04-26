#!/usr/bin/env python3
"""Collect relaxed public raw MIDAS native-text corpus outside support attachments."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CATALOG = "implementation/phase1/open_data/midas/public_native_mgt_source_catalog.json"
DEFAULT_OUT_DIR = "implementation/phase1/open_data/midas/public_native_corpus"
DEFAULT_REPORT_OUT = "implementation/phase1/open_data/midas/public_native_corpus_report.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", default=DEFAULT_CATALOG)
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--report-out", default=DEFAULT_REPORT_OUT)
    parser.add_argument("--min-node-count", type=int, default=8)
    parser.add_argument("--min-element-count", type=int, default=4)
    parser.add_argument("--min-accepted-count", type=int, default=1)
    parser.add_argument("--download-timeout-sec", type=int, default=60)
    args = parser.parse_args()

    cmd = [
        sys.executable,
        "implementation/phase1/collect_mgt_quality_corpus.py",
        "--catalog",
        str(args.catalog),
        "--out-dir",
        str(args.out_dir),
        "--report-out",
        str(args.report_out),
        "--min-node-count",
        str(int(args.min_node_count)),
        "--min-element-count",
        str(int(args.min_element_count)),
        "--min-accepted-count",
        str(int(args.min_accepted_count)),
        "--no-require-shell-beam-mix",
        "--download-timeout-sec",
        str(int(args.download_timeout_sec)),
    ]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, check=False)
    raise SystemExit(int(proc.returncode))


if __name__ == "__main__":
    main()
