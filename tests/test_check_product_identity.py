from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.product_identity import (  # noqa: E402
    ANALYSIS_ENGINE_VERSION,
    DISTRIBUTION_NAME,
    EVIDENCE_ENGINE_VERSION,
)


def test_current_product_identity_surfaces_match_canonical_manifest() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_product_identity.py", "--json"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 0, payload["blockers"]
    assert payload["contract_pass"] is True
    assert payload["identity"]["distribution_name"] == "structural-analysis"
    assert payload["identity"]["version"] == "0.3.0"
    assert payload["legacy_distribution_name_hits"] == []


def test_runtime_product_identity_is_pre_1_0_and_evidence_qualified() -> None:
    assert DISTRIBUTION_NAME == "structural-analysis"
    assert ANALYSIS_ENGINE_VERSION == "0.3.0"
    assert EVIDENCE_ENGINE_VERSION == "structural-analysis@0.3.0"
