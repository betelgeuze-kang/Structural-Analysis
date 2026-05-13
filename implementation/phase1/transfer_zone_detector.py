"""
Phase IV-1: Transfer Zone 자동 검출 강화 모듈

기존 _zone_for_centroid()의 단순 반경 기반 분류를 다중 신호 기반으로 강화합니다.

검출 신호:
  1. Story height 불연속 (층고 급변)
  2. Element density 급변 (부재 밀도 변화)
  3. Section 급변 (단면 크기 변화)
  4. Load path 불연속 (기둥 배치 변화)

Usage:
    from transfer_zone_detector import TransferZoneDetector
    detector = TransferZoneDetector(model_data)
    zone = detector.classify(element)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StoryInfo:
    z: float
    height: float  # 해당 층 높이
    n_columns: int = 0
    n_beams: int = 0
    n_walls: int = 0
    avg_col_area: float = 0.0  # 기둥 평균 단면적 proxy
    column_positions: list[tuple[float, float]] = field(default_factory=list)


class TransferZoneDetector:
    """다중 신호 기반 Transfer Zone 자동 검출기."""

    def __init__(
        self,
        nodes: list[dict],
        elements: list[dict],
        *,
        story_height_threshold: float = 0.3,   # 30% 층고 변화시 transfer 신호
        density_change_threshold: float = 0.4,  # 40% 부재밀도 변화시 transfer 신호
        section_change_threshold: float = 0.5,  # 50% 단면 변화시 transfer 신호
        column_offset_threshold: float = 2.0,   # 2m 이상 기둥 위치 오프셋시 transfer 신호
    ):
        self.node_map = {n["id"]: n for n in nodes}
        self.elements = elements
        self.story_ht_thresh = story_height_threshold
        self.density_thresh = density_change_threshold
        self.section_thresh = section_change_threshold
        self.col_offset_thresh = column_offset_threshold

        # Pre-compute story information
        self.stories: dict[float, StoryInfo] = {}
        self._build_story_info()

    def _build_story_info(self):
        """층별 정보를 사전 계산합니다."""
        # Detect story levels from node Z coordinates
        z_levels = sorted({round(n["z"], 2) for n in self.node_map.values()})
        if len(z_levels) < 2:
            return

        story_heights = {}
        for i in range(1, len(z_levels)):
            story_heights[z_levels[i]] = z_levels[i] - z_levels[i - 1]

        for z in z_levels:
            h = story_heights.get(z, story_heights.get(z_levels[1], 3.0))
            self.stories[z] = StoryInfo(z=z, height=h)

        # Count elements per story
        for el in self.elements:
            ns = [self.node_map.get(nid) for nid in el.get("node_ids", [])]
            ns = [n for n in ns if n is not None]
            if not ns:
                continue

            avg_z = sum(n["z"] for n in ns) / len(ns)
            # Find closest story
            closest_z = min(z_levels, key=lambda z: abs(z - avg_z))
            si = self.stories.get(closest_z)
            if si is None:
                continue

            etype = el.get("type", "").lower()
            if etype == "column":
                si.n_columns += 1
                cx = sum(n["x"] for n in ns) / len(ns)
                cy = sum(n["y"] for n in ns) / len(ns)
                si.column_positions.append((cx, cy))
                # Section area proxy from section name
                si.avg_col_area += self._section_area_proxy(el.get("section", ""))
            elif etype == "beam":
                si.n_beams += 1
            elif etype == "wall":
                si.n_walls += 1

        # Normalize column area
        for si in self.stories.values():
            if si.n_columns > 0:
                si.avg_col_area /= si.n_columns

    @staticmethod
    def _section_area_proxy(section: str) -> float:
        """단면 명칭에서 대략적인 면적 proxy를 추정합니다."""
        if not section:
            return 1.0
        # Parse H-section: H{depth}x{width}...
        s = section.upper().replace("X", " ").split()
        try:
            if s[0].startswith("H") and len(s) >= 2:
                depth = float(s[0][1:])
                width = float(s[1])
                return depth * width * 0.001  # rough proxy in m²
            elif s[0].startswith("W"):
                thickness = float(s[0][1:])
                return thickness * 0.001
        except (ValueError, IndexError):
            pass
        return 1.0

    def _story_height_signal(self, z: float) -> float:
        """층고 불연속 신호 (0~1). 인접 층 대비 층고 변화율."""
        si = self.stories.get(round(z, 2))
        if si is None:
            return 0.0

        z_levels = sorted(self.stories.keys())
        idx = None
        for i, zl in enumerate(z_levels):
            if abs(zl - z) < 0.5:
                idx = i
                break
        if idx is None:
            return 0.0

        # Compare with adjacent stories
        signals = []
        for di in [-1, 1]:
            adj_idx = idx + di
            if 0 <= adj_idx < len(z_levels):
                adj_z = z_levels[adj_idx]
                adj_si = self.stories.get(adj_z)
                if adj_si and si.height > 0 and adj_si.height > 0:
                    ratio = abs(si.height - adj_si.height) / max(si.height, adj_si.height)
                    signals.append(ratio)

        return max(signals) / max(self.story_ht_thresh, 1e-6) if signals else 0.0

    def _element_density_signal(self, z: float) -> float:
        """부재 밀도 변화 신호 (0~1)."""
        z = round(z, 2)
        si = self.stories.get(z)
        if si is None:
            return 0.0

        total = si.n_columns + si.n_beams + si.n_walls
        if total == 0:
            return 0.0

        z_levels = sorted(self.stories.keys())
        idx = None
        for i, zl in enumerate(z_levels):
            if abs(zl - z) < 0.5:
                idx = i
                break
        if idx is None:
            return 0.0

        signals = []
        for di in [-1, 1]:
            adj_idx = idx + di
            if 0 <= adj_idx < len(z_levels):
                adj_si = self.stories.get(z_levels[adj_idx])
                if adj_si:
                    adj_total = adj_si.n_columns + adj_si.n_beams + adj_si.n_walls
                    if adj_total > 0:
                        ratio = abs(total - adj_total) / max(total, adj_total)
                        signals.append(ratio)

        return min(max(signals) / max(self.density_thresh, 1e-6), 1.0) if signals else 0.0

    def _section_change_signal(self, z: float) -> float:
        """단면 급변 신호 (0~1). 인접 층 대비 평균 단면적 변화."""
        z = round(z, 2)
        si = self.stories.get(z)
        if si is None or si.avg_col_area <= 0:
            return 0.0

        z_levels = sorted(self.stories.keys())
        idx = None
        for i, zl in enumerate(z_levels):
            if abs(zl - z) < 0.5:
                idx = i
                break
        if idx is None:
            return 0.0

        signals = []
        for di in [-1, 1]:
            adj_idx = idx + di
            if 0 <= adj_idx < len(z_levels):
                adj_si = self.stories.get(z_levels[adj_idx])
                if adj_si and adj_si.avg_col_area > 0:
                    ratio = abs(si.avg_col_area - adj_si.avg_col_area) / max(si.avg_col_area, adj_si.avg_col_area)
                    signals.append(ratio)

        return min(max(signals) / max(self.section_thresh, 1e-6), 1.0) if signals else 0.0

    def _column_offset_signal(self, z: float) -> float:
        """기둥 위치 오프셋 신호 (0~1). 기둥 배치 변화 검출."""
        z = round(z, 2)
        si = self.stories.get(z)
        if si is None or not si.column_positions:
            return 0.0

        z_levels = sorted(self.stories.keys())
        idx = None
        for i, zl in enumerate(z_levels):
            if abs(zl - z) < 0.5:
                idx = i
                break
        if idx is None:
            return 0.0

        # Check if columns exist below that don't exist above (or vice versa)
        max_offset = 0.0
        for di in [-1, 1]:
            adj_idx = idx + di
            if 0 <= adj_idx < len(z_levels):
                adj_si = self.stories.get(z_levels[adj_idx])
                if adj_si and adj_si.column_positions:
                    # For each column in this story, find nearest in adjacent story
                    for cx, cy in si.column_positions:
                        min_dist = min(
                            math.sqrt((cx - ax) ** 2 + (cy - ay) ** 2)
                            for ax, ay in adj_si.column_positions
                        )
                        max_offset = max(max_offset, min_dist)

        return min(max_offset / max(self.col_offset_thresh, 1e-6), 1.0)

    def classify(
        self,
        x: float,
        y: float,
        z: float,
        center_x: float,
        center_y: float,
        max_radius: float,
    ) -> str:
        """
        다중 신호 기반 zone 분류.

        Returns: "core", "intermediate", "perimeter", 또는 "transfer"
        """
        # 1. Base zone (기존 반경 기반)
        dx = float(x - center_x)
        dy = float(y - center_y)
        radius = math.sqrt(dx * dx + dy * dy)
        normalized = radius / max(max_radius, 1e-6)

        if normalized <= 0.33:
            base_zone = "core"
        elif normalized >= 0.72:
            base_zone = "perimeter"
        else:
            base_zone = "intermediate"

        # 2. Transfer zone 검출 (다중 신호 가중합)
        s1 = self._story_height_signal(z)
        s2 = self._element_density_signal(z)
        s3 = self._section_change_signal(z)
        s4 = self._column_offset_signal(z)

        transfer_score = 0.30 * s1 + 0.25 * s2 + 0.25 * s3 + 0.20 * s4

        if transfer_score >= 0.6:
            return "transfer"

        return base_zone

    def classify_all_stories(self) -> dict[float, dict[str, Any]]:
        """모든 층의 transfer 신호를 진단합니다."""
        result = {}
        for z, si in sorted(self.stories.items()):
            s1 = self._story_height_signal(z)
            s2 = self._element_density_signal(z)
            s3 = self._section_change_signal(z)
            s4 = self._column_offset_signal(z)
            score = 0.30 * s1 + 0.25 * s2 + 0.25 * s3 + 0.20 * s4
            result[z] = {
                "height": si.height,
                "n_columns": si.n_columns,
                "n_beams": si.n_beams,
                "n_walls": si.n_walls,
                "signals": {
                    "story_height": round(s1, 3),
                    "element_density": round(s2, 3),
                    "section_change": round(s3, 3),
                    "column_offset": round(s4, 3),
                },
                "transfer_score": round(score, 3),
                "is_transfer": score >= 0.6,
            }
        return result


# ─── Standalone test ───
if __name__ == "__main__":
    import json
    from pathlib import Path

    demo_path = Path(__file__).parent / "open_data" / "demo" / "demo_15f_rc_corewall.json"
    if demo_path.exists():
        data = json.loads(demo_path.read_text(encoding="utf-8"))
        detector = TransferZoneDetector(data["nodes"], data["elements"])
        diag = detector.classify_all_stories()
        print("Transfer Zone Diagnosis:")
        print(f"{'Z (m)':>8} {'Height':>8} {'Col':>4} {'Score':>7} {'Transfer':>9}")
        print("-" * 44)
        for z, info in sorted(diag.items()):
            flag = "⚠️  YES" if info["is_transfer"] else "   no"
            print(f"{z:8.1f} {info['height']:8.1f} {info['n_columns']:4d} {info['transfer_score']:7.3f} {flag}")
    else:
        print(f"Demo file not found: {demo_path}")
        print("Run generate_demo_datasets.py first.")
