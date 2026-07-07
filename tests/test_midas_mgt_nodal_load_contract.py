from __future__ import annotations

import importlib
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

structural_analysis = importlib.import_module("structural_analysis")
load_model = structural_analysis.load_model


def test_mgt_conload_rows_expand_to_canonical_single_node_loads(tmp_path: Path) -> None:
    mgt_path = tmp_path / "conload_range.mgt"
    mgt_path.write_text(
        """*UNIT
KN, M, C
*NODE
1, 0.0, 0.0, 0.0
2, 1.0, 0.0, 0.0
*CONLOAD
1 to 2, 10.0, -2.0, 0.5, 1.0, 2.0, 3.0
""",
        encoding="utf-8",
    )

    model = load_model(mgt_path)
    nodal_loads = [row for row in model.loads if row.get("kind") == "nodal_load"]

    assert [row["node"] for row in nodal_loads] == ["1", "2"]
    assert model.metadata["load_summary"]["nodal_load_count"] == 2
    for row in nodal_loads:
        assert "nodes" not in row
        assert row["source"] == "midas_mgt_conload"
        assert row["components"] == {"FX": 10.0, "FY": -2.0, "FZ": 0.5}
        assert row["moments"] == {"MX": 1.0, "MY": 2.0, "MZ": 3.0}
