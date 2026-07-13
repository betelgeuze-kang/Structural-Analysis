"""Immutable lossless tokens produced by the MIDAS MGT v2 lexer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class NewlineStyle(str, Enum):
    """Newline convention observed in the original byte stream."""

    NONE = "none"
    LF = "lf"
    CRLF = "crlf"
    CR = "cr"
    MIXED = "mixed"


class DiagnosticSeverity(str, Enum):
    """Severity of a recoverable lexical diagnostic."""

    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class SourceSpan:
    """Inclusive physical-line and half-open byte range in the source."""

    line_start: int
    line_end: int
    byte_start: int
    byte_end: int

    def __post_init__(self) -> None:
        if self.line_start < 1 or self.line_end < self.line_start:
            raise ValueError("source line span must be positive and ordered")
        if self.byte_start < 0 or self.byte_end < self.byte_start:
            raise ValueError("source byte span must be non-negative and ordered")


@dataclass(frozen=True, slots=True)
class SourceInfo:
    """Byte-level identity and line-ending metadata for an MGT source."""

    source_name: str
    encoding: str
    has_utf8_bom: bool
    sha256: str
    byte_count: int
    physical_line_count: int
    newline_style: NewlineStyle


@dataclass(frozen=True, slots=True)
class PhysicalLine:
    """One physical line, retaining its exact bytes including its newline."""

    number: int
    span: SourceSpan
    raw: bytes
    text: str
    newline: str
    raw_sha256: str


@dataclass(frozen=True, slots=True)
class HeaderToken:
    """A ``*HEADER,args`` directive."""

    name: str
    args: tuple[str, ...]
    comment: str | None
    span: SourceSpan
    raw_fragment: PhysicalLine
    raw_fragment_sha256: str


@dataclass(frozen=True, slots=True)
class LogicalRow:
    """One data record, possibly assembled from continuation lines."""

    section: str
    block_occurrence: int
    block_row_index: int
    logical_index: int
    text: str
    comments: tuple[str, ...]
    span: SourceSpan
    raw_fragments: tuple[PhysicalLine, ...]
    raw_fragment_sha256: str
    continued: bool


@dataclass(frozen=True, slots=True)
class MgtBlock:
    """A source block; unknown header names are intentionally retained."""

    name: str
    args: tuple[str, ...]
    occurrence_index: int
    header: HeaderToken | None
    rows: tuple[LogicalRow, ...]
    span: SourceSpan
    physical_lines: tuple[PhysicalLine, ...]


@dataclass(frozen=True, slots=True)
class LexerDiagnostic:
    """A recoverable issue that prevents a silent lexical loss."""

    code: str
    message: str
    severity: DiagnosticSeverity
    span: SourceSpan
    section: str | None = None
    block_occurrence: int | None = None


@dataclass(frozen=True, slots=True)
class MgtDocument:
    """Lossless lexical representation of an MGT byte stream."""

    source: SourceInfo
    raw_bytes: bytes
    physical_lines: tuple[PhysicalLine, ...]
    blocks: tuple[MgtBlock, ...]
    diagnostics: tuple[LexerDiagnostic, ...]
