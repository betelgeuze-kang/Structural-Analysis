from __future__ import annotations

from pathlib import Path

from structural_analysis import load_model


def _write_conload_model(
    path: Path,
    target_expr: str,
    *,
    load_cases: tuple[str, ...] = (),
    components: str = "10.0, -2.0, 0.5, 1.0, 2.0, 3.0",
) -> None:
    stld = ""
    if load_cases:
        stld = "*STLDCASE\n" + "\n".join(f"{name}, USER" for name in load_cases) + "\n"
    path.write_text(
        f"""*UNIT
KN, M, C
*NODE
1, 0.0, 0.0, 0.0
2, 1.0, 0.0, 0.0
3, 2.0, 0.0, 0.0
4, 3.0, 0.0, 0.0
5, 4.0, 0.0, 0.0
{stld}*CONLOAD
{target_expr}, {components}
""",
        encoding="utf-8",
    )


def _nodal_loads(path: Path) -> list[dict[str, object]]:
    model = load_model(path)
    return [row for row in model.loads if row.get("kind") == "nodal_load"]


def test_mgt_conload_rows_expand_to_canonical_single_node_loads(tmp_path: Path) -> None:
    mgt_path = tmp_path / "conload_range.mgt"
    _write_conload_model(mgt_path, "1 to 2", load_cases=("LC1",))

    model = load_model(mgt_path)
    nodal_loads = [row for row in model.loads if row.get("kind") == "nodal_load"]

    assert [row["node"] for row in nodal_loads] == ["1", "2"]
    assert len(model.loads) == 2
    assert model.metadata["static_load_cases"][0]["name"] == "LC1"
    assert model.metadata["load_summary"] == {
        "static_load_case_count": 1,
        "nodal_load_count": 2,
        "skipped_conload_count": 0,
    }
    for row in nodal_loads:
        assert "nodes" not in row
        assert row["source"] == "midas_mgt_conload"
        assert row["load_case"] == "LC1"
        assert row["components"] == {
            "FX": 10.0,
            "FY": -2.0,
            "FZ": 0.5,
            "MX": 1.0,
            "MY": 2.0,
            "MZ": 3.0,
        }


def test_mgt_conload_rows_preserve_stepped_node_ranges(tmp_path: Path) -> None:
    mgt_path = tmp_path / "conload_stepped_range.mgt"
    _write_conload_model(mgt_path, "1 to 5 by 2")

    assert [row["node"] for row in _nodal_loads(mgt_path)] == ["1", "3", "5"]


def test_mgt_conload_rows_preserve_descending_stepped_node_ranges(tmp_path: Path) -> None:
    mgt_path = tmp_path / "conload_descending_stepped_range.mgt"
    _write_conload_model(mgt_path, "5 to 1 by 2")

    assert [row["node"] for row in _nodal_loads(mgt_path)] == ["5", "3", "1"]


def test_multiple_static_cases_block_unproven_conload_association(tmp_path: Path) -> None:
    mgt_path = tmp_path / "conload_multiple_cases.mgt"
    _write_conload_model(mgt_path, "1", load_cases=("DL", "LL"))

    model = load_model(mgt_path)

    kinds = {row.get("kind") for row in model.unsupported_features}
    assert "mgt_conload_load_case_association_missing" in kinds
    assert model.loads[0].get("load_case") is None


def test_malformed_or_nonfinite_conload_rows_are_explicitly_blocked(tmp_path: Path) -> None:
    bad_range = tmp_path / "conload_bad_range.mgt"
    _write_conload_model(bad_range, "1 to 5 by 0")
    bad_value = tmp_path / "conload_bad_value.mgt"
    _write_conload_model(
        bad_value,
        "1",
        components="10.0, nan, 0.5, 1.0, 2.0, 3.0",
    )

    for path in (bad_range, bad_value):
        model = load_model(path)
        kinds = {row.get("kind") for row in model.unsupported_features}
        assert "mgt_conload_rows_skipped" in kinds
        assert model.metadata["load_summary"]["skipped_conload_count"] == 1
        assert model.loads == []
