#!/usr/bin/env python3
"""CLI: build a fill-in G7 operator attachment manifest queue."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from implementation.phase1.open_data.korea.build_operator_attachment_manifest_queue import (  # noqa: E402
    main,
)


if __name__ == "__main__":
    raise SystemExit(main())
