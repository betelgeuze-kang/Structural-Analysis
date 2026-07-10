from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_scipy_is_declared_in_primary_and_legacy_runtime_metadata() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    setup_cfg = (ROOT / "setup.cfg").read_text(encoding="utf-8")

    assert '"scipy>=1.10"' in pyproject
    assert "    scipy>=1.10" in setup_cfg
