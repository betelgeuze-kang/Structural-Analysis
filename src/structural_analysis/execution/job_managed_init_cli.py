"""Initialize a new managed RC store without starting workers or saving credentials."""

import argparse
import json
from pathlib import Path
import secrets
import sqlite3

from .job_execution_authority import JobExecutionAuthority
from .job_service import DurableJobService


def initialize_managed_store(root, authority_directory, *, maximum_blob_bytes):
    """Enroll a new empty store; runtime authentication is configured on reopen.

    Constructor credentials below live only in this short-lived initialization
    object. No server starts, no jobs are submitted, and no credential or account
    configuration is written into the job database or receipt.
    """
    if type(maximum_blob_bytes) is not int or not 1 <= maximum_blob_bytes <= 2**63 - 1:
        raise ValueError("positive integer blob budget required")
    root = Path(root).absolute()
    if root.exists() or root.is_symlink():
        raise ValueError("managed initialization requires a new store root")
    authority, binding = JobExecutionAuthority.create(authority_directory, root)
    current = DurableJobService(
        root,
        tenant_tokens={"initialization": secrets.token_urlsafe(32)},
        worker_tokens={"initialization": secrets.token_urlsafe(32)},
        execution_authority=authority,
        execution_binding=binding,
        max_blob_payload_bytes=maximum_blob_bytes,
    )
    return {
        "status": "initialized",
        "root": str(current.root),
        "authority_directory": str(authority.directory),
        "authority_id": binding.authority_id,
        "generation": binding.generation,
        "maximum_blob_bytes": maximum_blob_bytes,
        "service_started": False,
        "jobs_submitted": 0,
        "credentials_persisted": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", help="new job store directory")
    parser.add_argument("authority_directory", help="new external authority directory")
    parser.add_argument("--maximum-blob-bytes", type=int, required=True)
    args = vars(parser.parse_args(argv))
    try:
        receipt = initialize_managed_store(**args)
    except (OSError, ValueError, sqlite3.DatabaseError, TypeError):
        print(
            json.dumps(
                {
                    "status": "failed",
                    "service_started": False,
                    "instruction": "Preserve any created authority and staged store. Existing stores are not adopted or overwritten; inspect partial initialization before retrying with new paths.",
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
