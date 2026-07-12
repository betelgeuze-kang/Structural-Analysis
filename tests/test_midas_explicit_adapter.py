from __future__ import annotations

from pathlib import Path

import pytest

from structural_analysis import load_model
from structural_analysis.io.midas import (
    MidasRawModel,
    canonicalize_midas_mgt,
    load_midas_mgt,
    load_midas_mgt_topology,
    parse_midas_mgt,
)
from structural_analysis.io.midas.loader import (
    load_midas_mgt as direct_topology_loader,
)


ROOT = Path(__file__).resolve().parents[1]


def _write_model(path: Path) -> Path:
    path.write_text(
        """*UNIT
KN, M, C
*NODE
1, 0.0, 0.0, 0.0
2, 1.0, 0.0, 0.0
3, 2.0, 0.0, 0.0
*ELEMENT
1, BEAM, 1, 1, 1, 2, 0.0
2, BEAM, 1, 1, 2, 3, 0.0
*STLDCASE
LC1, USER
*CONLOAD
1 to 3 by 2, 10.0, -2.0, 0.5, 1.0, 2.0, 3.0
""",
        encoding="utf-8",
    )
    return path


def test_package_import_does_not_monkeypatch_topology_loader() -> None:
    assert direct_topology_loader is load_midas_mgt_topology
    assert load_midas_mgt is not load_midas_mgt_topology

    package_source = (
        ROOT / "src/structural_analysis/io/midas/__init__.py"
    ).read_text(encoding="utf-8")
    assert "_raw_loader.load_midas_mgt" not in package_source
    assert "monkeypatch" not in package_source.lower()


def test_raw_parser_is_immutable_section_level_input(tmp_path: Path) -> None:
    path = _write_model(tmp_path / "model.mgt")

    raw = parse_midas_mgt(path)

    assert isinstance(raw, MidasRawModel)
    assert raw.source_path == str(path)
    assert raw.source_checksum.startswith("sha256:")
    assert raw.section_names == (
        "CONLOAD",
        "ELEMENT",
        "NODE",
        "STLDCASE",
        "UNIT",
    )
    assert raw.section_counts["NODE"] == 3
    assert raw.section("CONLOAD") == (
        "1 to 3 by 2, 10.0, -2.0, 0.5, 1.0, 2.0, 3.0",
    )


def test_explicit_canonicalizer_normalizes_load_ranges(tmp_path: Path) -> None:
    path = _write_model(tmp_path / "model.mgt")
    raw = parse_midas_mgt(path)
    topology = load_midas_mgt_topology(path)

    model = canonicalize_midas_mgt(raw, topology)

    assert [row["node"] for row in model.loads] == ["1", "3"]
    assert all(row["load_case"] == "LC1" for row in model.loads)
    assert model.loads[0]["components"] == {
        "FX": 10.0,
        "FY": -2.0,
        "FZ": 0.5,
        "MX": 1.0,
        "MY": 2.0,
        "MZ": 3.0,
    }
    assert model.metadata["adapter_pipeline"] == [
        "parse_midas_mgt",
        "load_midas_mgt_topology",
        "canonicalize_midas_mgt",
    ]
    assert model.metadata["raw_source_checksum"] == topology.input_checksum
    assert model.metadata["raw_section_counts"]["CONLOAD"] == 1


def test_explicit_canonicalizer_rejects_mixed_source_models(tmp_path: Path) -> None:
    raw_path = _write_model(tmp_path / "raw.mgt")
    topology_path = _write_model(tmp_path / "topology.mgt")

    raw = parse_midas_mgt(raw_path)
    topology = load_midas_mgt_topology(topology_path)

    with pytest.raises(ValueError, match="raw/topology source mismatch"):
        canonicalize_midas_mgt(raw, topology)


def test_explicit_canonicalizer_rejects_same_path_content_drift(
    tmp_path: Path,
) -> None:
    path = _write_model(tmp_path / "model.mgt")
    raw = parse_midas_mgt(path)
    path.write_text(path.read_text(encoding="utf-8") + "$ changed\n", encoding="utf-8")
    topology = load_midas_mgt_topology(path)

    with pytest.raises(ValueError, match="raw/topology checksum mismatch"):
        canonicalize_midas_mgt(raw, topology)


def test_public_loader_and_core_load_model_use_same_canonical_adapter(
    tmp_path: Path,
) -> None:
    path = _write_model(tmp_path / "model.mgt")

    direct = load_midas_mgt(path)
    public = load_model(path)

    assert public.loads == direct.loads
    assert public.metadata["adapter_pipeline"] == direct.metadata[
        "adapter_pipeline"
    ]
    assert public.metadata["load_summary"] == {
        "static_load_case_count": 1,
        "nodal_load_count": 2,
        "skipped_conload_count": 0,
    }


def test_canonical_adapter_has_no_private_raw_helper_dependency() -> None:
    source = (
        ROOT / "src/structural_analysis/io/midas/canonical.py"
    ).read_text(encoding="utf-8")

    assert "_raw._" not in source
    assert "from structural_analysis.io.midas.raw_parser import" in source
