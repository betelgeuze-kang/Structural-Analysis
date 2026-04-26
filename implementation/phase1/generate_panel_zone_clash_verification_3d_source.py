#!/usr/bin/env python3
"""Panel-zone clash verification 3D source stub."""

from __future__ import annotations

import sys

from generate_panel_zone_3d_source_artifact import main


if __name__ == "__main__":
    sys.argv = [sys.argv[0], "--source-kind", "clash_verification", *sys.argv[1:]]
    main()
