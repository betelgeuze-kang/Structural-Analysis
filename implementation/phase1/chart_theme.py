#!/usr/bin/env python3
"""Reusable chart styling helpers for release-facing analysis figures."""

from __future__ import annotations

import math
from pathlib import Path
import warnings

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure


FIGURE_BG = "#fcfaf5"
PANEL_BG = "#fffdfa"
GRID = "#ddd4c3"
LINE = "#cfbea1"
TEXT = "#1f2937"
MUTED = "#6b7280"
SUCCESS = "#2f7d5a"
WARNING = "#b76d2d"
DANGER = "#b24b43"
ACCENT = "#1f5fa2"
ACCENT_SOFT = "#d8e7f8"
ACCENT_WARM = "#ead8c0"


def configure_analysis_chart_defaults() -> None:
    plt.rcParams.update(
        {
            "font.size": 10.5,
            "axes.titlesize": 14,
            "axes.labelsize": 10.5,
            "xtick.labelsize": 9.5,
            "ytick.labelsize": 9.5,
            "legend.fontsize": 9,
            "axes.facecolor": PANEL_BG,
            "figure.facecolor": FIGURE_BG,
            "axes.edgecolor": LINE,
            "axes.labelcolor": TEXT,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "text.color": TEXT,
            "grid.color": GRID,
            "grid.linewidth": 0.8,
            "grid.alpha": 0.28,
            "axes.grid": False,
        }
    )


def apply_analysis_axis_style(
    ax: Axes,
    *,
    xlabel: str | None = None,
    ylabel: str | None = None,
    title: str | None = None,
    x_grid: bool = False,
    y_grid: bool = True,
) -> None:
    ax.set_facecolor(PANEL_BG)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(LINE)
        ax.spines[side].set_linewidth(1.0)
    if xlabel:
        ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel(ylabel)
    if title:
        ax.set_title(title, loc="left", pad=10, fontweight="bold")
    if y_grid:
        ax.grid(True, axis="y", alpha=0.24)
    if x_grid:
        ax.grid(True, axis="x", alpha=0.18)


def add_figure_header(fig: Figure, *, title: str, subtitle: str = "") -> None:
    fig.suptitle(title, x=0.065, y=0.992, ha="left", va="top", fontsize=15.5, fontweight="bold")
    if subtitle:
        fig.text(0.065, 0.948, subtitle, ha="left", va="top", fontsize=10, color=MUTED)


def add_badge(
    ax: Axes,
    text: str,
    *,
    x: float = 0.98,
    y: float = 0.98,
    ha: str = "right",
    va: str = "top",
    facecolor: str = "#fff8ef",
    edgecolor: str = LINE,
    fontsize: float = 8.7,
) -> None:
    ax.text(
        x,
        y,
        text,
        transform=ax.transAxes,
        ha=ha,
        va=va,
        fontsize=fontsize,
        bbox={
            "boxstyle": "round,pad=0.35",
            "facecolor": facecolor,
            "edgecolor": edgecolor,
            "alpha": 0.96,
        },
    )


def save_analysis_figure(fig: Figure, path: Path, *, dpi: int = 180, rect: tuple[float, float, float, float] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="This figure includes Axes that are not compatible with tight_layout")
        try:
            if rect is None:
                fig.tight_layout()
            else:
                fig.tight_layout(rect=rect)
        except Exception:
            pass
    fig.savefig(path, dpi=dpi, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)


def empty_state_figure(*, title: str, message: str, subtitle: str = "") -> tuple[Figure, Axes]:
    configure_analysis_chart_defaults()
    fig = plt.figure(figsize=(10, 5.8))
    fig.patch.set_facecolor(FIGURE_BG)
    ax = fig.add_subplot(111)
    ax.axis("off")
    add_figure_header(fig, title=title, subtitle=subtitle)
    ax.text(0.05, 0.58, message, fontsize=13, transform=ax.transAxes)
    return fig, ax


def scale_series(values: np.ndarray, *, min_exponent: int = 3) -> tuple[np.ndarray, float, str]:
    finite = np.asarray(values, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return np.asarray(values, dtype=np.float64), 1.0, ""
    peak = float(np.max(np.abs(finite)))
    if peak <= 0.0:
        return np.asarray(values, dtype=np.float64), 1.0, ""
    exponent = int(math.floor(math.log10(peak)))
    if abs(exponent) < int(min_exponent):
        return np.asarray(values, dtype=np.float64), 1.0, ""
    scale = float(10 ** exponent)
    return np.asarray(values, dtype=np.float64) / scale, scale, f"×1e{exponent}"


def percentile_window(values: np.ndarray, *, lower: float = 1.0, upper: float = 99.0) -> tuple[float, float]:
    finite = np.asarray(values, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return -1.0, 1.0
    lo = float(np.percentile(finite, lower))
    hi = float(np.percentile(finite, upper))
    if math.isclose(lo, hi):
        pad = max(abs(lo), 1.0) * 0.15
        return lo - pad, hi + pad
    pad = max((hi - lo) * 0.1, 1e-6)
    return lo - pad, hi + pad
