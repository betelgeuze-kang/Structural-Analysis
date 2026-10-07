"""Explicit local-operator backup/restore commands; never starts a service."""

from __future__ import annotations
import argparse
import json
import sqlite3
from .job_store_backup import backup_job_store, restore_job_store


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("backup", "restore"))
    parser.add_argument("source")
    parser.add_argument(
        "destination",
        help="new external directory; existing stores are never overwritten",
    )
    parser.add_argument("--maximum-bytes", type=int, required=True)
    parser.add_argument("--maximum-files", type=int, default=10000)
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument(
        "--manifest-sha256",
        help="restore only: digest retained separately after successful backup",
    )
    args = parser.parse_args(argv)
    if (args.operation == "restore") != (args.manifest_sha256 is not None):
        parser.error("--manifest-sha256 is required only for restore")
    kwargs = dict(
        maximum_bytes=args.maximum_bytes,
        maximum_files=args.maximum_files,
        timeout_seconds=args.timeout_seconds,
    )
    try:
        if args.operation == "backup":
            receipt = backup_job_store(args.source, args.destination, **kwargs)
        else:
            receipt = restore_job_store(
                args.source,
                args.destination,
                manifest_sha256=args.manifest_sha256,
                **kwargs,
            )
    except (OSError, ValueError, sqlite3.DatabaseError, KeyError, TypeError):
        print(
            json.dumps(
                {
                    "status": "failed",
                    "operation": args.operation,
                    "service_started": False,
                    "instruction": "Preserve any partial destination; verify inputs and use a new destination for another attempt.",
                }
            )
        )
        return 1
    except KeyboardInterrupt:
        print(json.dumps({"status": "interrupted", "service_started": False}))
        return 130
    print(
        json.dumps(
            {
                "status": "completed",
                "operation": args.operation,
                "service_started": False,
                **receipt,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
