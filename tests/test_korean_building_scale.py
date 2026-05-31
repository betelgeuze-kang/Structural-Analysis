from __future__ import annotations

from implementation.phase1.open_data.korea.korean_building_scale import (
    building_scale_band,
    is_medium_or_large,
)


def test_building_scale_band_medium() -> None:
    for band in ("mid_rise", "10_20", "20_30"):
        assert building_scale_band(band) == "medium"


def test_building_scale_band_large() -> None:
    for band in ("high_rise", "30_plus", "super_tall"):
        assert building_scale_band(band) == "large"


def test_building_scale_band_small_and_other() -> None:
    assert building_scale_band("low_rise") == "small"
    assert building_scale_band("n_a") == "other"
    assert building_scale_band("") == "other"


def test_is_medium_or_large() -> None:
    assert is_medium_or_large({"storey_band": "20_30"}) is True
    assert is_medium_or_large({"storey_band": "high_rise"}) is True
    assert is_medium_or_large({"storey_band": "low_rise"}) is False
    assert is_medium_or_large({"storey_band": "n_a"}) is False
