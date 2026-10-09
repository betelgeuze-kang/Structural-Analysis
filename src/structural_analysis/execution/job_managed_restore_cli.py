"""Explicit managed restoration activation; never starts a service or worker."""

import argparse
import json
import sqlite3

from .job_managed_restore import activate_managed_restore


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="sealed managed backup")
    parser.add_argument("destination", help="existing restored directory")
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--maximum-bytes", type=int, required=True)
    parser.add_argument("--maximum-files", type=int, default=10000)
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument("--expected-generation", type=int)
    parser.add_argument("--expected-root")
    args = vars(parser.parse_args(argv))
    if (args["expected_generation"] is None) != (args["expected_root"] is None):
        parser.error("expected generation and root must be supplied together")
    try:
        receipt = activate_managed_restore(**args)
    except (OSError, ValueError, sqlite3.DatabaseError, TypeError, KeyError):
        print(
            json.dumps(
                {
                    "status": "failed",
                    "service_started": False,
                    "instruction": "Preserve both stores and the authority. After an interrupted cutover, retry the same backup, destination and expected binding. Do not recreate the authority or remove binding metadata.",
                }
            )
        )
        return 1
    except KeyboardInterrupt:
        print(json.dumps({"status": "interrupted", "service_started": False}))
        return 130
    print(json.dumps(receipt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
