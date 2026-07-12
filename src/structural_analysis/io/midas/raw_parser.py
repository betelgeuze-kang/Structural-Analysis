"""Public, side-effect-free MIDAS MGT raw parsing primitives."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path
import re
from typing import Any, Iterable


_RANGE_BY_RE = re.compile(
    r"^\s*(\d+)\s*to\s*(\d+)\s*by\s*(\d+)\s*$",
    re.IGNORECASE,
)
_RANGE_RE = re.compile(
    r"^\s*(\d+)\s*to\s*(\d+)\s*$",
    re.IGNORECASE,
)


def clean_mgt_line(line: str) -> str:
    raw = str(line).rstrip()
    stripped = raw.lstrip()
    if not stripped or stripped.startswith("#") or stripped.startswith("$"):
        return ""
    if ";" in raw:
        raw = raw.split(";", 1)[0]
    return raw.strip()


def split_csv_like(value: str) -> list[str]:
    return [token.strip() for token in str(value).split(",") if token.strip()]


def parse_int_token(token: Any) -> int | None:
    try:
        value = float(str(token).strip())
    except ValueError:
        return None
    if not isfinite(value):
        return None
    if abs(value - int(value)) <= 1.0e-9:
        return int(value)
    return None


def parse_float_token(token: Any) -> float | None:
    try:
        value = float(str(token).strip())
    except ValueError:
        return None
    return value


def expand_integer_expression(expr: str) -> tuple[list[int], str | None]:
    """Expand one MIDAS integer/range expression with explicit failure reasons."""

    text = str(expr).strip()
    if not text:
        return [], "empty_integer_expression"

    match = _RANGE_BY_RE.match(text)
    if match:
        start, end, step = (
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
        )
        if step <= 0:
            return [], "non_positive_range_step"
        stop = end + 1 if start <= end else end - 1
        signed_step = step if start <= end else -step
        return list(range(start, stop, signed_step)), None

    match = _RANGE_RE.match(text)
    if match:
        start, end = int(match.group(1)), int(match.group(2))
        stop = end + 1 if start <= end else end - 1
        step = 1 if start <= end else -1
        return list(range(start, stop, step)), None

    lowered = text.lower()
    if " to " in lowered or " by " in lowered:
        return [], "malformed_integer_range"

    values: list[int] = []
    seen: set[int] = set()
    for token in text.replace(",", " ").split():
        value = parse_int_token(token)
        if value is None:
            return [], "non_integer_token"
        if value not in seen:
            seen.add(value)
            values.append(value)
    return values, None


@dataclass(frozen=True)
class MidasRawModel:
    """Immutable section-level parse result before canonical normalization."""

    source_path: str
    line_count: int
    section_rows: tuple[tuple[str, tuple[str, ...]], ...]

    @property
    def section_names(self) -> tuple[str, ...]:
        return tuple(name for name, _ in self.section_rows)

    def section(self, name: str) -> tuple[str, ...]:
        key = str(name).strip().upper()
        for section_name, rows in self.section_rows:
            if section_name == key:
                return rows
        return ()

    @property
    def section_counts(self) -> dict[str, int]:
        return {name: len(rows) for name, rows in self.section_rows}

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "line_count": self.line_count,
            "sections": {
                name: list(rows)
                for name, rows in self.section_rows
            },
        }


def parse_midas_mgt(path: Path) -> MidasRawModel:
    sections: dict[str, list[str]] = {}
    current = "ROOT"
    line_count = 0
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line_count += 1
        line = clean_mgt_line(raw)
        if not line:
            continue
        if line.startswith("*"):
            header = line[1:].strip()
            current = header.split(",", 1)[0].strip().upper() or "ROOT"
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return MidasRawModel(
        source_path=str(path),
        line_count=line_count,
        section_rows=tuple(
            (name, tuple(rows))
            for name, rows in sorted(sections.items())
        ),
    )


def parse_static_load_cases(rows: Iterable[str]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for row in rows:
        tokens = split_csv_like(row)
        if not tokens:
            continue
        cases.append(
            {
                "name": str(tokens[0]).strip(),
                "type": str(tokens[1]).strip() if len(tokens) >= 2 else "",
                "raw": row,
            }
        )
    return cases
