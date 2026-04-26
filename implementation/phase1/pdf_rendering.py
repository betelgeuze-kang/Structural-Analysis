from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import logging
from pathlib import Path

import matplotlib
from matplotlib import font_manager


@dataclass(frozen=True)
class CjkFontConfig:
    family: str
    path: str


_CANDIDATE_FONT_PATHS = [
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",
    "/usr/share/fonts/truetype/nanum/NanumSquareR.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]

_CANDIDATE_FONT_NAMES = [
    "NanumGothic",
    "NanumBarunGothic",
    "NanumSquare",
    "Noto Sans CJK KR",
]


@lru_cache(maxsize=1)
def resolve_cjk_font() -> CjkFontConfig | None:
    for font_path in _CANDIDATE_FONT_PATHS:
        path = Path(font_path)
        if not path.exists():
            continue
        try:
            font_manager.fontManager.addfont(str(path))
            family = font_manager.FontProperties(fname=str(path)).get_name()
            if family:
                return CjkFontConfig(family=family, path=str(path))
        except Exception:
            continue
    for font in font_manager.fontManager.ttflist:
        if font.name in _CANDIDATE_FONT_NAMES:
            return CjkFontConfig(family=str(font.name), path=str(font.fname))
    return None


@lru_cache(maxsize=1)
def configure_matplotlib_cjk_pdf() -> CjkFontConfig | None:
    config = resolve_cjk_font()
    logging.getLogger("fontTools.subset").setLevel(logging.ERROR)
    matplotlib.rcParams["axes.unicode_minus"] = False
    matplotlib.rcParams["pdf.fonttype"] = 42
    matplotlib.rcParams["ps.fonttype"] = 42
    if config is not None:
        matplotlib.rcParams["font.family"] = [config.family, "DejaVu Sans"]
        matplotlib.rcParams["font.sans-serif"] = [config.family, "DejaVu Sans"]
    return config


def finalize_pdf_figure(fig, *, text_page: bool = True) -> None:
    if text_page:
        fig.subplots_adjust(left=0.04, right=0.98, top=0.97, bottom=0.05)
    else:
        fig.subplots_adjust(left=0.03, right=0.97, top=0.95, bottom=0.04)
